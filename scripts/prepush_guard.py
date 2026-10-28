"""Mandatory blocking pre-push secrets/content guard (stage 10 R1, NL-BP-235).

Read-only Git operations only: this tool never pushes, commits, tags, fetches,
publishes, changes repository visibility/collaborators or rewrites history. It scans
the staged index, tracked HEAD/working tree and/or bounded history, blocking on
secrets, personal/private data, sensitive config, embedded runtimes/vendor copies,
databases/logs/build outputs and unexpected large blobs.

Secret patterns, redaction, classification and artifact rules are imported from
scripts/audit_release_secrets.py; this tool does not duplicate them. Every finding
is redacted before printing/writing. Full secret values never appear in stdout,
JSON or Markdown.

Modes:
  scan-staged | scan-head | scan-history | scan-all [--json] [--json-out P]
  install-hook [--repo PATH] [--force] [--backup]
  hook --repo PATH            (reads Git pre-push refs from stdin)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_NAME = "prepush_guard.py"
SCHEMA_VERSION = 1
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 64_000_000
MAX_FINDINGS = 500
MAX_COMMITS = 30
MAX_PATHS_PER_COMMIT = 200
MAX_HISTORY_BYTES = 32_000_000

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_OPERATIONAL = 3


class GuardError(RuntimeError):
    """Raised when a required read-only Git operation fails (fail closed)."""


def _audit():
    path = REPO_ROOT / "scripts" / "audit_release_secrets.py"
    spec = importlib.util.spec_from_file_location("nl_audit_release_secrets", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load audit_release_secrets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = _audit()
ROTATE = AUDIT.ROTATE
EXCLUDE = AUDIT.EXCLUDE_FROM_UPLOAD
REVIEW = AUDIT.REVIEW
BLOCKING = frozenset({ROTATE, EXCLUDE})
_PERSONAL_NONBLOCKING_PREFIXES = ("docs/", "tests/")

#: Narrow, documented allowlist for one known synthetic test fixture only.
#: An entry requires the exact value digest, exact path, exact rule, exact scope
#: and (optionally) the exact historical commits. It is never a blanket tests-tree
#: or rule suppression: a different digest, path, rule, scope or commit still
#: blocks normally, and staged/head findings are not exempted.
KNOWN_SYNTHETIC_FIXTURES: tuple[dict, ...] = (
    {
        "sha256": "457643f44d19aed85fd756aa50cc0cd6b57376d4e8f5a72f9f85972a522002a3",
        "path": "tests/test_prepush_guard.py",
        "rule": "aws_access_key_id",
        "scope": "history",
        "commits": (
            "d9341cd3ee869cbce5f0cb58b8946cfaa191f2d1",
            "3cae00c508e200c7ef88474b69cd1dc1dfec5304",
        ),
        "reason": ("Runtime-assembled synthetic AWS-shaped fixture that proves "
                   "detection in tests/test_prepush_guard.py; the hardcoded form "
                   "was removed in stage-10 R3 and remains only in these exact "
                   "bounded-history commits. Non-secret test value."),
    },
)


def _known_synthetic_allowlist_match(rel: str, value: str, rule: str,
                                     scope: str,
                                     commit: str | None) -> dict | None:
    """Return the matching known-synthetic allowlist entry, or None.

    Digest, path, rule and scope must all match; when the entry lists commits,
    the historical commit must be one of them too.
    """
    digest = _sha256(str(value or ""))
    rel_norm = str(rel or "").replace(os.sep, "/")
    for entry in KNOWN_SYNTHETIC_FIXTURES:
        if digest != entry["sha256"]:
            continue
        if rel_norm != entry["path"]:
            continue
        if str(rule or "") != entry["rule"]:
            continue
        if str(scope or "") != entry["scope"]:
            continue
        commits = entry.get("commits") or ()
        if commits and str(commit or "") not in commits:
            continue
        return entry
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _norm(root: Path) -> str:
    return str(root.resolve()).replace("/", "\\").lower()


def _git_env() -> dict:
    env = dict(os.environ)
    env.update(AUDIT.GIT_ENV_OVERRIDES)
    return env


def _git(root: Path, args: list, max_bytes: int = MAX_FILE_BYTES,
         *, allow_missing: bool = False) -> tuple[bytes, bool]:
    """Run one read-only Git command. Every subcommand is allowlisted locally.

    Operational failures (git missing, timeout, non-zero exit) raise GuardError so
    scan and hook modes fail closed instead of silently scanning an empty tree.
    allow_missing is used only for historical blobs: a path that did not exist at
    one bounded-history commit is expected (deleted/renamed files) and is skipped,
    while missing git/timeout/other failures still raise.
    """
    allowed = {"rev-parse", "ls-files", "show", "diff", "diff-tree", "log",
               "rev-list", "version", "cat-file"}
    if not args or args[0] not in allowed:
        raise ValueError("refusing non-read-only git command: " + " ".join(args[:1]))
    try:
        completed = subprocess.run(["git", "-C", str(root), *args],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   stdin=subprocess.DEVNULL, env=_git_env(),
                                   timeout=20.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GuardError("read-only git command failed ("
                         + args[0] + "): " + type(exc).__name__) from None
    if completed.returncode != 0:
        if allow_missing and args[0] == "show":
            return b"", False
        raise GuardError("read-only git command failed ("
                         + args[0] + ") with exit code "
                         + str(completed.returncode))
    data = completed.stdout or b""
    truncated = len(data) > max_bytes
    return data[:max_bytes], truncated


def _text(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def _is_documentation_path(rel: str) -> bool:
    low = str(rel).replace(os.sep, "/").lower()
    if low.startswith(("docs/", ".agents/", "da_eliminare/")):
        return True
    return "/" not in low and low.endswith((".md", ".rst", ".txt"))


def _is_text_path(rel: str) -> bool:
    lower = str(rel).lower()
    suffix = ""
    if "." in lower:
        suffix = "." + lower.rsplit(".", 1)[1]
    return (suffix in AUDIT.TEXT_CANDIDATE_SUFFIXES
            or lower.endswith((".env", ".gitignore", ".gitattributes"))
            or not suffix)


class Scanner:
    def __init__(self, root: Path, *, allowlist: dict | None = None) -> None:
        self.root = root
        self.allowlist = allowlist or {}
        self.findings: list[dict] = []
        self.scanned_files = 0
        self.scanned_bytes = 0
        self.truncated = False
        self.repo_norm = _norm(root)

    def _allowlisted(self, rel: str, value: str) -> bool:
        digest = _sha256(value)
        prefix = str((self.allowlist.get(digest) or {}).get("path_prefix") or "")
        if prefix and str(rel).replace(os.sep, "/").startswith(prefix):
            return True
        try:
            return bool(AUDIT._is_allowlisted_test_fixture(rel, value))
        except Exception:  # noqa: BLE001
            return False

    def add(self, *, scope: str, path: str, line: int, rule: str, kind: str,
            classification: str, action: str, value: str, context: str,
            commit: str | None = None) -> None:
        if len(self.findings) >= MAX_FINDINGS:
            self.truncated = True
            return
        known_synthetic = _known_synthetic_allowlist_match(
            path, value, rule, scope, commit)
        allowlisted = bool(known_synthetic) or self._allowlisted(path, value)
        blocking = classification in BLOCKING and not allowlisted
        if kind in ("personal_absolute_path", "private_url"):
            rel_low = str(path).replace(os.sep, "/").lower()
            blocking = classification in BLOCKING and not allowlisted
            if rel_low.startswith(_PERSONAL_NONBLOCKING_PREFIXES):
                blocking = False
        spans = []
        if value and context:
            start = 0
            while True:
                idx = context.find(value, start)
                if idx < 0:
                    break
                spans.append((idx, idx + len(value)))
                start = idx + len(value)
        finding = {
            "scope": scope,
            "path": path,
            "commit": commit,
            "line": int(line),
            "rule": rule,
            "kind": kind,
            "classification": classification,
            "blocking": bool(blocking),
            "allowlisted": bool(allowlisted),
            "action": action,
            "evidence": AUDIT.redact_value(value),
            "context": AUDIT.redact_line(context, spans),
        }
        if known_synthetic is not None:
            finding["allowlist"] = {
                "kind": "known_synthetic_fixture",
                "reason": known_synthetic["reason"],
                "digest": known_synthetic["sha256"],
                "path": known_synthetic["path"],
                "rule": known_synthetic["rule"],
                "scope": known_synthetic["scope"],
                "commits": list(known_synthetic.get("commits") or ()),
            }
        self.findings.append(finding)

    def scan_text(self, rel: str, text: str, *, scope: str,
                  commit: str | None = None) -> None:
        if not text:
            return
        data = text.encode("utf-8", "replace")
        if len(data) > MAX_FILE_BYTES:
            text = text[:MAX_FILE_BYTES]
        self.scanned_files += 1
        self.scanned_bytes += len(data)
        if self.scanned_files > 20000 or self.scanned_bytes > MAX_TOTAL_BYTES:
            self.truncated = True
            return
        documentation = _is_documentation_path(rel)
        for lineno, line in enumerate(text.splitlines(), 1):
            if len(line) > 4000:
                line = line[:4000]
            for rule in AUDIT.SECRET_RULES:
                for match in rule["regex"].finditer(line):
                    value = match.group(0)
                    if AUDIT._looks_like_placeholder(value):
                        continue
                    if AUDIT._is_fixture_context(rel, line):
                        continue
                    self.add(scope=scope, path=rel, line=lineno,
                             rule=rule["id"], kind=rule["kind"],
                             classification=rule["classification"],
                             action=AUDIT._secret_action(rule["id"],
                                                         rule["classification"]),
                             value=value, context=line, commit=commit)
            if documentation:
                continue
            for match in AUDIT.GENERIC_SECRET_RE.finditer(line):
                value = match.group(2)
                if AUDIT._looks_like_placeholder(value):
                    continue
                if AUDIT._is_fixture_context(rel, line):
                    continue
                self.add(scope=scope, path=rel, line=lineno, rule="generic_secret",
                         kind="generic_secret", classification=REVIEW,
                         action="Inspect whether this is a real secret; rotate if real, "
                                "otherwise keep fake values only in tests.",
                         value=value, context=line, commit=commit)
            if documentation:
                continue
            keyish = re.search(r"(?i)(secret|token|key|password|auth|credential)", line)
            if keyish:
                for match in AUDIT.HIGH_ENTROPY_RE.finditer(line):
                    value = match.group(1)
                    if AUDIT._looks_like_placeholder(value):
                        continue
                    if AUDIT._is_fixture_context(rel, line):
                        continue
                    if re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
                        continue
                    self.add(scope=scope, path=rel, line=lineno,
                             rule="high_entropy_secret", kind="high_entropy",
                             classification=REVIEW,
                             action="Inspect and rotate if this high-entropy value is a real credential.",
                             value=value, context=line, commit=commit)
            for rule_id, regex in AUDIT.PERSONAL_PATH_RULES:
                match = regex.search(line)
                if not match:
                    continue
                value = match.group(0)
                norm_value = value.replace("/", "\\").lower()
                if norm_value.startswith(self.repo_norm):
                    break
                if AUDIT._is_fixture_context(rel, line):
                    continue
                self.add(scope=scope, path=rel, line=lineno, rule=rule_id,
                         kind="personal_absolute_path", classification=REVIEW,
                         action="Replace machine/user-specific absolute paths with "
                                "repository-relative paths; never ship personal paths.",
                         value=value, context=line, commit=commit)
                break
            for rule_id, regex in AUDIT.PRIVATE_URL_RULES:
                match = regex.search(line)
                if not match:
                    continue
                self.add(scope=scope, path=rel, line=lineno, rule=rule_id,
                         kind="private_url", classification=REVIEW,
                         action="Confirm this private/loopback URL is intentional and "
                                "contains no credentials/internal endpoints.",
                         value=match.group(0), context=line, commit=commit)
                break

    def scan_blob(self, rel: str, data: bytes, *, scope: str,
                  commit: str | None = None, size_hint: int | None = None) -> None:
        if _is_text_path(rel) and self._looks_text(data):
            self.scan_text(rel, _text(data), scope=scope, commit=commit)
        effective_size = max(len(data), int(size_hint or 0))
        artifact = AUDIT.classify_artifact_path(rel, size=effective_size)
        if artifact is not None:
            self.add(scope=scope, path=rel, line=0, rule="artifact_path",
                     kind=artifact["kind"], classification=artifact["classification"],
                     action=artifact["action"], value=rel,
                     context="path classified as upload-exclusion artifact",
                     commit=commit)
        if effective_size > AUDIT.LARGE_BINARY_BYTES:
            self.add(scope=scope, path=rel, line=0, rule="large_blob",
                     kind="large_binary", classification=EXCLUDE,
                     action="Do not upload large blobs; keep outside the repository/approved store.",
                     value=rel, context="file larger than 5 MiB", commit=commit)

    @staticmethod
    def _looks_text(data: bytes) -> bool:
        if not data:
            return True
        sample = data[:4096]
        if b"\x00" in sample:
            return False
        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    def report(self, mode: str) -> dict:
        blocking = [item for item in self.findings if item["blocking"]]
        counts = {
            "findings": len(self.findings),
            "blocking": len(blocking),
            "allowlisted": sum(1 for item in self.findings if item["allowlisted"]),
            "files_scanned": self.scanned_files,
            "bytes_scanned": self.scanned_bytes,
            "truncated": bool(self.truncated),
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "tool": TOOL_NAME,
            "mode": mode,
            "generated_at": _now(),
            "ok": not blocking and not self.truncated,
            "blocked": bool(blocking),
            "exit_code": EXIT_OK if not blocking and not self.truncated else EXIT_FINDINGS,
            "counts": counts,
            "truncated": bool(self.truncated),
            "findings": self.findings,
            "bounds": {"max_file_bytes": MAX_FILE_BYTES,
                       "max_total_bytes": MAX_TOTAL_BYTES,
                       "max_findings": MAX_FINDINGS,
                       "max_commits": MAX_COMMITS},
            "allowlist": {
                "known_synthetic_fixtures": [
                    {
                        "sha256": entry["sha256"],
                        "path": entry["path"],
                        "rule": entry["rule"],
                        "scope": entry["scope"],
                        "commits": list(entry.get("commits") or ()),
                        "reason": entry["reason"],
                    }
                    for entry in KNOWN_SYNTHETIC_FIXTURES
                ],
            },
            "no_push": True, "no_commit": True, "no_network": True,
            "history_rewritten": False,
            "secrets_redacted": True,
        }


def _load_allowlist(path: str | None) -> dict:
    if not path:
        return {}
    source = Path(path).read_text(encoding="utf-8")
    data = json.loads(source)
    entries = data.get("fixtures") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError("allowlist must be an object with a fixtures list")
    out = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("allowlist fixture entries must be objects")
        digest = str(entry.get("sha256") or "").lower()
        reason = str(entry.get("reason") or "").strip()
        prefix = str(entry.get("path_prefix") or "").replace("\\", "/")
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not reason or not prefix:
            raise ValueError("allowlist entries need sha256, path_prefix and reason")
        if not prefix.startswith("tests/"):
            raise ValueError("allowlist is restricted to documented synthetic fixtures "
                             "under tests/")
        out[digest] = {"reason": reason, "path_prefix": prefix}
    return out


def _staged_paths(root: Path) -> list[str]:
    data, _ = _git(root, ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"])
    return [part for part in _text(data).split(chr(0)) if part]


def _tracked_paths(root: Path) -> list[str]:
    data, _ = _git(root, ["ls-files", "-z"])
    return [part for part in _text(data).split(chr(0)) if part]


def _scan_staged(root: Path, scanner: Scanner) -> None:
    for rel in sorted(_staged_paths(root)):
        data, truncated = _git(root, ["show", ":" + rel], max_bytes=MAX_FILE_BYTES)
        scanner.truncated = scanner.truncated or truncated
        size_hint = (AUDIT.LARGE_BINARY_BYTES + 1) if truncated else len(data)
        scanner.scan_blob(rel, data, scope="staged", size_hint=size_hint)


def _scan_head(root: Path, scanner: Scanner) -> None:
    for rel in sorted(_tracked_paths(root)):
        path = root / rel
        size_hint = 0
        if path.is_file() and not path.is_symlink():
            try:
                size_hint = path.stat().st_size
                data = path.read_bytes()[:MAX_FILE_BYTES]
            except OSError:
                data = b""
        else:
            data, truncated = _git(root, ["show", "HEAD:" + rel],
                                   max_bytes=MAX_FILE_BYTES)
            scanner.truncated = scanner.truncated or truncated
        scanner.scan_blob(rel, data, scope="head", size_hint=size_hint)


def _scan_history(root: Path, scanner: Scanner) -> None:
    data, _ = _git(root, ["rev-list", "--all", "--max-count=" + str(MAX_COMMITS)])
    commits = [line for line in _text(data).splitlines() if line.strip()]
    for commit in commits:
        changed, _ = _git(root, ["diff-tree", "--no-commit-id", "--name-only",
                                 "-r", "-z", commit])
        paths = [part for part in _text(changed).split(chr(0)) if part]
        for rel in paths[:MAX_PATHS_PER_COMMIT]:
            if not _is_text_path(rel):
                artifact = AUDIT.classify_artifact_path(rel, size=None)
                if artifact is not None:
                    scanner.add(scope="history", path=rel, commit=commit, line=0,
                                rule="artifact_path", kind=artifact["kind"],
                                classification=artifact["classification"],
                                action=artifact["action"], value=rel,
                                context="historical path classified as upload-exclusion artifact")
                continue
            blob, truncated = _git(root, ["show", commit + ":" + rel],
                                   max_bytes=MAX_FILE_BYTES, allow_missing=True)
            if truncated:
                scanner.truncated = True
            if blob:
                scanner.scan_blob(
                    rel, blob, scope="history", commit=commit,
                    size_hint=((AUDIT.LARGE_BINARY_BYTES + 1)
                               if truncated else len(blob)))
        if scanner.scanned_bytes > MAX_HISTORY_BYTES:
            scanner.truncated = True
            return


def _scan_all(root: Path, scanner: Scanner) -> None:
    _scan_staged(root, scanner)
    _scan_head(root, scanner)
    _scan_history(root, scanner)


def _json_dump(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + chr(10)


def _markdown(payload: dict) -> str:
    lines = ["# Pre-push guard report", "",
             "Mode: " + str(payload["mode"]),
             "Result: " + ("BLOCKED" if payload["blocked"] else "PASS"),
             "No push, commit, fetch, network operation or history rewrite was performed.",
             "", "## Counts", ""]
    for key, value in payload["counts"].items():
        lines.append("- " + key + ": " + str(value))
    lines += ["", "## Findings", "",
              "| Scope | Path | Line | Rule | Class | Blocking | Evidence |",
              "|---|---|---|---|---|---|---|"]
    for item in payload["findings"]:
        evidence = item["evidence"]
        redacted = ("sha256_12=" + evidence["sha256_12"] + "; prefix="
                    + evidence["prefix"] + "; length=" + str(evidence["length"]))
        lines.append("| " + str(item["scope"]) + " | " + str(item["path"]) + " | "
                     + str(item["line"]) + " | " + str(item["rule"]) + " | "
                     + str(item["classification"]) + " | "
                     + ("yes" if item["blocking"] else "no") + " | "
                     + redacted + " |")
    return chr(10).join(lines) + chr(10)


def _write_reports(payload: dict, json_out: str | None, markdown_out: str | None) -> None:
    if json_out:
        path = Path(json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dump(payload), encoding="utf-8")
    if markdown_out:
        path = Path(markdown_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_markdown(payload), encoding="utf-8")


def _print_summary(payload: dict, as_json: bool) -> None:
    if as_json:
        print(_json_dump(payload), end="")
        return
    print("Pre-push guard: " + str(payload["mode"]) + " -> "
          + ("BLOCKED" if payload["blocked"] else "PASS"))
    print("Files scanned: " + str(payload["counts"]["files_scanned"])
          + ", findings: " + str(payload["counts"]["findings"])
          + ", blocking: " + str(payload["counts"]["blocking"]))
    for item in payload["findings"][:20]:
        evidence = item["evidence"]
        print("  [" + str(item["scope"]) + "] " + str(item["path"])
              + ":" + str(item["line"]) + " " + str(item["rule"])
              + " " + str(item["classification"])
              + " sha256_12=" + evidence["sha256_12"])
    if len(payload["findings"]) > 20:
        print("  ... " + str(len(payload["findings"]) - 20) + " more redacted findings")
    if payload["truncated"]:
        print("WARNING: scan bounds were reached; result fails closed.", file=sys.stderr)
    print("No push/commit/network/history rewrite was performed.")


def _scan_mode(root: Path, mode: str, allowlist_path: str | None,
               json_out: str | None, markdown_out: str | None, as_json: bool) -> int:
    if not (root / ".git").exists():
        print("ERROR: not a Git repository: " + str(root), file=sys.stderr)
        return EXIT_USAGE
    try:
        allowlist = _load_allowlist(allowlist_path)
    except (OSError, ValueError) as exc:
        print("ERROR: invalid allowlist: " + str(exc), file=sys.stderr)
        return EXIT_USAGE
    scanner = Scanner(root, allowlist=allowlist)
    try:
        if mode == "scan-staged":
            _scan_staged(root, scanner)
        elif mode == "scan-head":
            _scan_head(root, scanner)
        elif mode == "scan-history":
            _scan_history(root, scanner)
        elif mode == "scan-all":
            _scan_all(root, scanner)
        else:
            return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - fail closed
        print("ERROR: scan failed: " + str(exc), file=sys.stderr)
        return EXIT_OPERATIONAL
    payload = scanner.report(mode)
    _write_reports(payload, json_out, markdown_out)
    _print_summary(payload, as_json)
    return payload["exit_code"]


def _hook_script(guard_path: Path) -> str:
    """Build the POSIX pre-push hook.

    Uses the interpreter that ran install-hook (not a bare python3, which may be
    absent on Windows/Git-for-Windows) and forward-slash absolute paths so the
    same hook works under Git Bash (Windows) and POSIX shells.
    """
    interpreter = sys.executable or "python3"
    try:
        interpreter = Path(interpreter).resolve().as_posix()
    except OSError:
        interpreter = str(interpreter).replace("\\", "/")
    try:
        guard = Path(guard_path).resolve().as_posix()
    except OSError:
        guard = str(guard_path).replace("\\", "/")
    return ("#!/bin/sh" + chr(10)
            + "# NL Coding Agent mandatory pre-push guard (blocking, read-only)." + chr(10)
            + "# Reads Git's pre-push refs from stdin; never pushes or rewrites history." + chr(10)
            + "set -eu" + chr(10)
            + "repo=$(git rev-parse --show-toplevel) || exit " + str(EXIT_OPERATIONAL) + chr(10)
            + "exec " + shlex.quote(interpreter) + " " + shlex.quote(guard)
            + " hook --repo \"$repo\" \"$@\"" + chr(10))


def _install_hook(root: Path, force: bool, backup: bool) -> int:
    if not (root / ".git").exists():
        print("ERROR: not a Git repository: " + str(root), file=sys.stderr)
        return EXIT_USAGE
    hooks_dir = root / ".git" / "hooks"
    target = hooks_dir / "pre-push"
    guard_path = Path(__file__).resolve()
    content = _hook_script(guard_path)
    if target.exists() and not force:
        print("ERROR: pre-push hook already exists at " + str(target)
              + "; use --force with --backup to replace it.", file=sys.stderr)
        return EXIT_USAGE
    print("Pre-push hook installation plan (default is dry-print only):")
    print("  hook path: " + str(target))
    print("  guard: " + str(guard_path))
    print("  mode: blocking pre-push scan")
    print("  content:")
    for line in content.rstrip(chr(10)).split(chr(10)):
        print("    " + line)
    if not force:
        print("Dry-print only; no hook was written. Re-run with --force to install.")
        return EXIT_OK
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = target.with_name("pre-push.bak." + stamp)
        if not backup:
            print("ERROR: existing hook exists; pass --backup to preserve it.", file=sys.stderr)
            return EXIT_USAGE
        target.replace(backup_path)
        print("Backed up existing hook to " + str(backup_path))
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    try:
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass
    print("Installed blocking pre-push guard hook: " + str(target))
    return EXIT_OK


def _hook_mode(root: Path, allowlist_path: str | None, as_json: bool) -> int:
    try:
        stdin_data = sys.stdin.read(65536) if not sys.stdin.isatty() else ""
    except (OSError, UnicodeError):
        stdin_data = ""
    refs = [line.split() for line in stdin_data.splitlines() if line.strip()]
    del refs  # refs are diagnostic only; the scan is the gate.
    if not (root / ".git").exists():
        print("ERROR: pre-push hook cannot find a Git repository.", file=sys.stderr)
        return EXIT_OPERATIONAL
    scanner = None
    try:
        allowlist = _load_allowlist(allowlist_path)
        scanner = Scanner(root, allowlist=allowlist)
        _scan_staged(root, scanner)
        _scan_history(root, scanner)
    except Exception as exc:  # noqa: BLE001 - fail closed
        print("ERROR: pre-push guard failed closed: " + str(exc), file=sys.stderr)
        return EXIT_OPERATIONAL
    payload = scanner.report("hook")
    _print_summary(payload, as_json)
    if payload["blocked"] or payload["truncated"]:
        print("BLOCKED: fix/remove the findings before pushing. No push was performed.",
              file=sys.stderr)
        return EXIT_FINDINGS
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mandatory blocking pre-push secrets/content guard")
    parser.add_argument("--repo", default=str(REPO_ROOT))
    parser.add_argument("--allowlist", default=None,
                        help="JSON allowlist for documented synthetic tests/ fixtures only")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--markdown-out", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan-staged", "scan-head", "scan-history", "scan-all"):
        sub.add_parser(name)
    install = sub.add_parser("install-hook")
    install.add_argument("--force", action="store_true")
    install.add_argument("--backup", action="store_true")
    hook_parser = sub.add_parser("hook")
    hook_parser.add_argument("remote", nargs="?")
    hook_parser.add_argument("remote_url", nargs="?")
    return parser


_MODES = ("scan-staged", "scan-head", "scan-history", "scan-all",
          "install-hook", "hook")
_GLOBAL_VALUE_FLAGS = ("--repo", "--allowlist", "--json-out", "--markdown-out")


def _normalise_argv(tokens: list[str]) -> list[str]:
    """Allow global flags before or after the subcommand (e.g. scan-all --json)."""
    global_tokens: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _GLOBAL_VALUE_FLAGS and i + 1 < len(tokens):
            global_tokens.extend([token, tokens[i + 1]])
            i += 2
            continue
        if token == "--json":
            global_tokens.append(token)
            i += 1
            continue
        rest.append(token)
        i += 1
    if rest and rest[0] in _MODES:
        return global_tokens + rest
    if not rest:
        return global_tokens + list(tokens)
    return tokens


def main(argv=None) -> int:
    parser = build_parser()
    raw = list(argv if argv is not None else sys.argv[1:])
    args = parser.parse_args(_normalise_argv(raw))
    root = Path(args.repo).resolve()
    if args.command in ("scan-staged", "scan-head", "scan-history", "scan-all"):
        return _scan_mode(root, args.command, args.allowlist, args.json_out,
                          args.markdown_out, args.json)
    if args.command == "install-hook":
        return _install_hook(root, args.force, args.backup)
    if args.command == "hook":
        return _hook_mode(root, args.allowlist, args.json)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())

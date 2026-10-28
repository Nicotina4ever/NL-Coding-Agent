"""Read-only repository hygiene audit (stage 5, repository hygiene / build audit).

READ-ONLY GUARANTEE: this script never deletes, moves, renames or modifies tracked
files and never starts a mission, model or network request. It only reads the
filesystem and runs local read-only git queries (rev-parse, status, worktree list).
It writes only the requested JSON/markdown report paths (default under build/phase5/).

What it measures (deterministic, bounded):
  * file counts and bytes by area (source, docs, tests, assets, runtime, vendor,
    dist, build evidence, user data, logs, caches, junk, git metadata);
  * duplicate files by size + sha256 for small/medium files only (large runtimes
    are excluded from hashing and reported separately);
  * obsolete/stale candidates: temp_*.py at the repo root, *.patch artifacts,
    applied PATCH copies, accidental %SystemDrive% tree, repository caches,
    stale generated metadata with old absolute paths, registered stale git
    worktrees, duplicated Python/CrewAI runtime copies, stray portable releases;
  * stale absolute path references (old root K:/AI/Coding Agent, other K:/AI
    siblings, hardcoded C:/Users paths) with operational vs historical
    classification;
  * launcher/dependency reference validation (launchers, CLI commands, pyproject
    pins vs installed versions, JSON/SHA256 manifests, config files, git state).

Every finding carries a recommendation class: SAFE, NEEDS-AUTHORIZATION or
DO-NOT-TOUCH. The script itself performs none of those actions.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
NL = chr(10)
BS = chr(92)

DEFAULT_JSON = Path("build") / "phase5" / "repository_hygiene.json"
DEFAULT_MD = Path("build") / "phase5" / "repository_hygiene.md"

SAFE = "SAFE"
NEEDS_AUTHORIZATION = "NEEDS-AUTHORIZATION"
DO_NOT_TOUCH = "DO-NOT-TOUCH"

PROTECTED_AREAS = frozenset({
    "python", "crewAI", "crewAI-tools", "dist", "data", "logs", "build",
    "docs", ".git",
})
HASH_EXCLUDED_AREAS = frozenset({
    ".git", "python", "crewAI", "crewAI-tools", "dist", "data", "logs",
})
CACHE_DIR_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".venv", "venv",
})
TEXT_SUFFIXES = frozenset({
    ".py", ".pyi", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".bat", ".ps1", ".patch", ".ini", ".cfg", ".svg",
})
LAUNCHER_SUFFIXES = (".bat", ".ps1")
ROOT_HISTORICAL_DOCS = (
    "AUDIT_REALE_E_LIMITI.md",
    "HANDOFF_DEEPSEEK_HARNESS.md",
    "PASTE_THIS_IN_ANTIGRAVITY.txt",
    "START_HERE_ANTIGRAVITY.md",
    "README_FIRST.txt",
    "README.txt",
)
BUILD_DOC_DUPLICATES = (
    ("build/phase2/IMPLEMENTATION_PLAN.md", "docs/PHASE2_HARNESS_INTEGRATION_PLAN.md"),
    ("build/phase3/SUPERVISOR_PLAN.md", "docs/PHASE3_SUPERVISOR_PLAN.md"),
    ("build/phase4/CREWAI_FLOWS_PLAN.md", "docs/PHASE4_CREWAI_FLOWS_PLAN.md"),
)
OLD_ROOT_PATTERN = re.compile(r"K:/+AI/+Coding[ ]+Agent", re.IGNORECASE)
CANONICAL_ROOT_PATTERN = re.compile(r"K:/+AI/+NL[ ]+Coding[ ]+Agent", re.IGNORECASE)
OTHER_K_AI_PATTERN = re.compile(r"K:/+AI/+[^ ]+", re.IGNORECASE)
USER_PATH_PATTERN = re.compile(r"C:/+Users/+[^ ]+", re.IGNORECASE)
SYSTEMDRIVE_LITERAL = "%SystemDrive%"


def default_bounds() -> dict:
    return {
        "max_seconds": 120.0,
        "max_files": 500000,
        "max_hash_bytes": 2 * 1024 * 1024,
        "max_hash_files": 5000,
        "max_hash_total_bytes": 256 * 1024 * 1024,
        "max_text_bytes": 2 * 1024 * 1024,
        "max_stale_matches": 200,
        "max_worktree_bytes": 200 * 1024 * 1024,
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def human_bytes(size: int | float) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            if unit == "B":
                return str(int(value)) + " B"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return str(int(size)) + " B"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalise(text: str) -> str:
    return text.replace(BS, "/")


def rel_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def root_entry_kind(name: str) -> tuple[str, str]:
    lower = name.lower()
    if lower.endswith((".bat", ".ps1")):
        return "launcher", "source"
    if lower.endswith((".md", ".txt")):
        return "root-documentation", "source"
    if lower.endswith(".patch"):
        return "patch-artifact", "evidence"
    if lower.endswith(".py"):
        if lower.startswith("temp_"):
            return "temp-script", "review"
        return "entrypoint", "source"
    if lower in ("pyproject.toml", ".gitignore", "sha256_manifest.json"):
        return "config", "source"
    return "other", "review"


def area_kind(name: str) -> tuple[str, str]:
    mapping = {
        "nl_coding_agent": ("source", "source"),
        "tests": ("tests", "source"),
        "scripts": ("scripts", "source"),
        "config": ("config", "source"),
        "assets": ("assets", "source"),
        ".agents": ("agent-instructions", "source"),
        "docs": ("documentation", "source"),
        "PATCH": ("patch-artifact", "evidence"),
        "build": ("build-evidence", "evidence"),
        "dist": ("release-artifact", "protected"),
        "data": ("user-data", "protected"),
        "logs": ("logs", "protected"),
        "python": ("runtime", "protected"),
        "crewAI": ("vendor", "protected"),
        "crewAI-tools": ("vendor", "protected"),
        "%SystemDrive%": ("junk", "safe"),
        ".pytest_cache": ("cache", "safe"),
        "__pycache__": ("cache", "safe"),
        ".git": ("git-metadata", "protected"),
    }
    if name in mapping:
        return mapping[name]
    return root_entry_kind(name)


def walk_files(
    base: Path,
    state: dict,
    bounds: dict,
    *,
    follow_symlinks: bool = False,
) -> list[Path]:
    """Bounded, deterministic file walk; never follows directory symlinks by default."""
    found: list[Path] = []
    stack: list[Path] = [base]
    started = state["started"]
    while stack:
        current = stack.pop()
        if time.monotonic() - started > bounds["max_seconds"]:
            state["truncated"] = True
            break
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name.lower())
        except OSError:
            continue
        for entry in entries:
            if state["files_seen"] >= bounds["max_files"]:
                state["truncated"] = True
                return found
            try:
                is_dir = entry.is_dir()
                is_file = entry.is_file()
                is_symlink = entry.is_symlink()
            except OSError:
                continue
            path = Path(entry.path)
            if is_symlink and not follow_symlinks:
                state["symlinks_skipped"] += 1
                continue
            if is_dir:
                stack.append(path)
            elif is_file:
                found.append(path)
                state["files_seen"] += 1
    return sorted(found, key=lambda item: item.as_posix().lower())


def measure_area(root: Path, name: str, state: dict, bounds: dict) -> dict:
    target = root / name
    kind, classification = area_kind(name)
    record = {
        "name": name,
        "kind": kind,
        "classification": classification,
        "files": 0,
        "bytes": 0,
        "truncated": False,
        "path": name,
    }
    if target.is_dir():
        before = state["truncated"]
        files = walk_files(target, state, bounds)
        record["files"] = len(files)
        total = 0
        for path in files:
            try:
                total += path.stat().st_size
            except OSError:
                continue
        record["bytes"] = total
        record["truncated"] = state["truncated"] and not before
    elif target.is_file():
        try:
            record["files"] = 1
            record["bytes"] = target.stat().st_size
        except OSError:
            pass
    return record


def scan_caches(root: Path, state: dict, bounds: dict) -> dict:
    entries: list[dict] = []
    started = time.monotonic()
    seen_dirs = 0
    stack: list[Path] = [root]
    while stack:
        if time.monotonic() - started > bounds["max_seconds"]:
            state["truncated"] = True
            break
        current = stack.pop()
        try:
            children = sorted(os.scandir(current), key=lambda item: item.name.lower())
        except OSError:
            continue
        for entry in children:
            try:
                if entry.is_symlink():
                    continue
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            path = Path(entry.path)
            rel = rel_posix(path, root)
            if rel.split("/", 1)[0] in (".git",):
                continue
            if entry.name in CACHE_DIR_NAMES:
                seen_dirs += 1
                clear_state = {
                    "started": time.monotonic(),
                    "files_seen": 0,
                    "truncated": False,
                    "symlinks_skipped": 0,
                }
                files = walk_files(path, clear_state, bounds)
                total = 0
                for item in files:
                    try:
                        total += item.stat().st_size
                    except OSError:
                        continue
                area = rel.split("/", 1)[0]
                protected = area in HASH_EXCLUDED_AREAS or area in ("build", "docs")
                entries.append({
                    "path": rel,
                    "files": len(files),
                    "bytes": total,
                    "area": area,
                    "protected": protected,
                    "classification": DO_NOT_TOUCH if protected else SAFE,
                })
                continue
            if seen_dirs > 5000:
                state["truncated"] = True
                break
            stack.append(path)
    entries.sort(key=lambda item: item["path"])
    repo_entries = [item for item in entries if not item["protected"]]
    return {
        "dirs": len(entries),
        "files": sum(item["files"] for item in entries),
        "bytes": sum(item["bytes"] for item in entries),
        "entries": entries[:200],
        "repo_cleanup_candidates": repo_entries,
        "repo_cleanup_files": sum(item["files"] for item in repo_entries),
        "repo_cleanup_bytes": sum(item["bytes"] for item in repo_entries),
        "truncated": state["truncated"],
    }


def scan_duplicates(root: Path, state: dict, bounds: dict) -> dict:
    groups: dict[tuple[int, str], list[str]] = {}
    hashed_files = 0
    hashed_bytes = 0
    skipped_large = 0
    truncated = False
    started = time.monotonic()
    candidates: list[Path] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        name = entry.name
        if name in HASH_EXCLUDED_AREAS:
            continue
        if entry.is_symlink():
            continue
        if entry.is_dir():
            candidates.extend(walk_files(entry, state, bounds))
        elif entry.is_file():
            candidates.append(entry)
    for path in sorted(candidates, key=lambda item: item.as_posix().lower()):
        if time.monotonic() - started > bounds["max_seconds"]:
            truncated = True
            break
        if hashed_files >= bounds["max_hash_files"]:
            truncated = True
            break
        if hashed_bytes >= bounds["max_hash_total_bytes"]:
            truncated = True
            break
        try:
            stat = path.stat()
        except OSError:
            continue
        if not stat.st_size:
            continue
        if stat.st_size > bounds["max_hash_bytes"]:
            skipped_large += 1
            continue
        try:
            digest = sha256_file(path)
        except OSError:
            continue
        hashed_files += 1
        hashed_bytes += stat.st_size
        groups.setdefault((stat.st_size, digest), []).append(rel_posix(path, root))
    duplicate_groups: list[dict] = []
    for (size, digest), paths in sorted(groups.items(), key=lambda item: (-item[0][0], item[0][1])):
        if len(paths) < 2:
            continue
        classification, reason = classify_duplicate(paths)
        duplicate_groups.append({
            "size": size,
            "sha256": digest,
            "paths": sorted(paths),
            "classification": classification,
            "reason": reason,
        })
    return {
        "groups": duplicate_groups,
        "group_count": len(duplicate_groups),
        "duplicate_files": sum(len(group["paths"]) for group in duplicate_groups),
        "hashed_files": hashed_files,
        "hashed_bytes": hashed_bytes,
        "skipped_large_files": skipped_large,
        "max_hash_bytes": bounds["max_hash_bytes"],
        "truncated": truncated,
    }


def classify_duplicate(paths: list[str]) -> tuple[str, str]:
    patched = [path for path in paths if path.startswith("PATCH/")]
    if patched and len(patched) < len(paths):
        return NEEDS_AUTHORIZATION, "applied audited patch copy is identical to the live file"
    if all(path.startswith("build/") for path in paths):
        return NEEDS_AUTHORIZATION, "duplicate generated evidence inside build/ - review before removal"
    docs_copy = [path for path in paths if path.startswith("docs/")]
    build_copy = [path for path in paths if path.startswith("build/")]
    if docs_copy and build_copy and len(docs_copy) + len(build_copy) == len(paths):
        if any(path.startswith("docs/evidence") for path in docs_copy):
            return NEEDS_AUTHORIZATION, "acceptance evidence duplicated in build/ and docs/evidence; review retention before removal"
        return SAFE, "build/ copy is identical to a tracked docs/ file; the tracked copy is authoritative"
    if all(path.endswith("__init__.py") for path in paths):
        return DO_NOT_TOUCH, "intentional empty package markers, not a cleanup target"
    return NEEDS_AUTHORIZATION, "duplicate content - review purpose before touching either copy"

def scan_obsolete(
    root: Path,
    duplicates: dict,
    caches: dict,
    worktrees: dict,
    tracked: set[str],
) -> list[dict]:
    entries: list[dict] = []

    def add(kind: str, rel: str, classification: str, reason: str, action: str,
            *, files: int = 0, bytes_: int = 0, evidence: dict | None = None) -> None:
        entries.append({
            "kind": kind,
            "path": rel,
            "classification": classification,
            "reason": reason,
            "action": action,
            "files": int(files),
            "bytes": int(bytes_),
            "tracked": rel in tracked,
            "evidence": evidence or {},
        })

    for path in sorted(root.glob("temp_*.py"), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        add("temp-repair-script", path.name, NEEDS_AUTHORIZATION,
            "one-off repair script left at the repository root; it mutates repository files "
            "or the live SQLite database when executed and is superseded by the committed tree",
            "review evidence, archive a copy under build/phase5/archive/ if desired, then delete with explicit approval",
            files=1, bytes_=size)

    for path in sorted(root.glob("*.patch"), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        add("applied-patch-artifact", path.name, NEEDS_AUTHORIZATION,
            "patch artifact from the audited safety-foundation integration; the current sources "
            "are already the applied result and the manifest records the audited hashes",
            "archive for audit history, then remove with explicit approval",
            files=1, bytes_=size)

    patch_dir = root / "PATCH"
    if patch_dir.is_dir():
        files = walk_files(patch_dir, {"started": time.monotonic(), "files_seen": 0,
                                       "truncated": False, "symlinks_skipped": 0},
                           default_bounds())
        identical = 0
        compared = 0
        for path in files:
            rel = rel_posix(path, root)
            if not rel.startswith("PATCH/"):
                continue
            counterpart = root / rel[len("PATCH/"):]
            if not counterpart.is_file():
                continue
            compared += 1
            try:
                if sha256_file(path) == sha256_file(counterpart):
                    identical += 1
            except OSError:
                continue
        total = sum(path.stat().st_size for path in files if path.is_file())
        add("applied-patch-copy-dir", "PATCH", NEEDS_AUTHORIZATION,
            "copies the audited patch files; " + str(identical) + "/" + str(compared)
            + " Python/test files are byte-identical to the live sources",
            "archive README/WINDOWS_REAUDIT plus the audited copies, then remove the directory with explicit approval",
            files=len(files), bytes_=total, evidence={"identical": identical, "compared": compared})

    system_drive = root / "%SystemDrive%"
    if system_drive.is_dir():
        files = walk_files(system_drive, {"started": time.monotonic(), "files_seen": 0,
                                          "truncated": False, "symlinks_skipped": 0},
                           default_bounds())
        total = sum(path.stat().st_size for path in files if path.is_file())
        add("accidental-path-tree", "%SystemDrive%", SAFE,
            "accidental literal %SystemDrive% directory containing copied Windows cache files; "
            "it is generated junk, not source or user data",
            "delete after confirming no process holds it; no tracked file references it",
            files=len(files), bytes_=total)

    repo_caches = caches.get("repo_cleanup_candidates") or []
    for cache in repo_caches:
        add("repository-cache", cache["path"], SAFE,
            "generated pytest/bytecode cache inside the repository; regenerated on demand",
            "delete repository cache directory; no validation needed",
            files=cache["files"], bytes_=cache["bytes"])

    for build_rel, docs_rel in BUILD_DOC_DUPLICATES:
        build_path = root / build_rel
        docs_path = root / docs_rel
        if not (build_path.is_file() and docs_path.is_file()):
            continue
        try:
            same = sha256_file(build_path) == sha256_file(docs_path)
        except OSError:
            same = False
        if not same:
            continue
        size = build_path.stat().st_size
        add("duplicate-build-evidence", build_rel, SAFE,
            "byte-identical duplicate of " + docs_rel + "; the tracked documentation copy is authoritative",
            "delete the build copy (build/ is disposable generated output)",
            files=1, bytes_=size, evidence={"tracked_copy": docs_rel})

    plan_path = root / "build" / "portable_plan.json"
    if plan_path.is_file():
        text = ""
        try:
            text = plan_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
        old_hits = len(OLD_ROOT_PATTERN.findall(normalise(text)))
        add("stale-generated-metadata", "build/portable_plan.json", NEEDS_AUTHORIZATION,
            "generated portable-build plan still records the pre-relocation source/output roots"
            + (" (" + str(old_hits) + " old-root references)" if old_hits else ""),
            "regenerate the portable build plan at stage 6 or update the stale paths after approval",
            files=1, bytes_=plan_path.stat().st_size, evidence={"old_root_references": old_hits})

    stray_script = root / "build" / "audit_payload_db.py"
    if stray_script.is_file():
        add("stray-build-script", "build/audit_payload_db.py", NEEDS_AUTHORIZATION,
            "one-off payload database audit script left in build/; it is generated scratch code, not a supported tool",
            "archive with the build evidence or delete with explicit approval",
            files=1, bytes_=stray_script.stat().st_size)

    portable = root / "dist" / "portable-release"
    if portable.is_dir():
        state = {"started": time.monotonic(), "files_seen": 0, "truncated": False,
                 "symlinks_skipped": 0}
        files = walk_files(portable, state, default_bounds())
        total = sum(path.stat().st_size for path in files if path.is_file())
        current_pkg = root / "nl_coding_agent"
        packaged_pkg = portable / "nl_coding_agent"
        missing: list[str] = []
        if current_pkg.is_dir() and packaged_pkg.is_dir():
            current_names = {item.name for item in current_pkg.iterdir()}
            packaged_names = {item.name for item in packaged_pkg.iterdir()}
            missing = sorted(name for name in current_names - packaged_names if not name.startswith("__"))
        add("stale-portable-release", "dist/portable-release", DO_NOT_TOUCH,
            "existing one-folder release artifact built before the workspace relocation and before "
            "stages 2-4; it is stale but must not be deleted without authorization"
            + (("; packaged package is missing: " + ", ".join(missing)) if missing else ""),
            "keep until stage 6 rebuilds a verified portable payload with explicit user approval; do not delete now",
            files=len(files), bytes_=total,
            evidence={"missing_packaged_entries": missing,
                      "files": len(files), "bytes": total})

    vendor_git = root / "crewAI" / ".git"
    if vendor_git.is_dir():
        state = {"started": time.monotonic(), "files_seen": 0, "truncated": False,
                 "symlinks_skipped": 0}
        files = walk_files(vendor_git, state, default_bounds())
        total = sum(path.stat().st_size for path in files if path.is_file())
        add("vendor-checkout-metadata", "crewAI/.git", DO_NOT_TOUCH,
            "the reference-only CrewAI vendor checkout carries its own git metadata ("
            + human_bytes(total) + "); it is excluded from payloads but stays protected",
            "no action; vendor checkout policy requires explicit user approval for any change",
            files=len(files), bytes_=total)

    for name in ROOT_HISTORICAL_DOCS:
        path = root / name
        if not path.is_file():
            continue
        add("historical-handoff-doc", name, NEEDS_AUTHORIZATION,
            "historical handoff/relocation note at the repository root; retained for history but may "
            "confuse operators about the current canonical state",
            "review with the Lead and archive under docs/history (or keep) after explicit approval",
            files=1, bytes_=path.stat().st_size)

    for group in duplicates.get("groups") or []:
        if group.get("classification") == DO_NOT_TOUCH:
            add("intentional-duplicate", ", ".join(group["paths"]), DO_NOT_TOUCH,
                group.get("reason") or "intentional duplicate",
                "no action; package markers are required and cheap",
                files=len(group["paths"]), bytes_=group["size"] * len(group["paths"]))

    for worktree in worktrees.get("worktrees") or []:
        if worktree.get("classification") != NEEDS_AUTHORIZATION:
            continue
        add("stale-git-worktree", str(worktree.get("path")), NEEDS_AUTHORIZATION,
            "registered git worktree is stale or outside the repository: "
            + ", ".join(worktree.get("stale_reasons") or ["unknown"]),
            "verify no process uses it, then remove the registration with git worktree remove/prune "
            "and delete the temporary directory after explicit approval",
            files=int(worktree.get("files") or 0), bytes_=int(worktree.get("bytes") or 0))

    unique: dict[tuple[str, str], dict] = {}
    for entry in entries:
        unique.setdefault((entry["kind"], entry["path"]), entry)
    result = [unique[key] for key in sorted(unique)]
    return result


def scan_stale_paths(root: Path, bounds: dict) -> dict:
    files: list[Path] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if entry.is_file() and entry.suffix.lower() in TEXT_SUFFIXES:
            files.append(entry)
    for name in ("nl_coding_agent", "tests", "scripts", "config", ".agents", "assets", "docs"):
        base = root / name
        if not base.is_dir():
            continue
        state = {"started": time.monotonic(), "files_seen": 0, "truncated": False,
                 "symlinks_skipped": 0}
        for path in walk_files(base, state, bounds):
            if path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    for rel in ("build/portable_plan.json", "build/audit_payload_db.py",
                "dist/portable-release/payload_manifest.json"):
        path = root / rel
        if path.is_file():
            files.append(path)
    build_dir = root / "build"
    if build_dir.is_dir():
        for path in sorted(build_dir.glob("*.json")):
            if path.is_file():
                files.append(path)

    seen: set[str] = set()
    matches: list[dict] = []
    counts: dict[tuple[str, str], int] = {}
    files_with_matches: set[str] = set()
    scanned = 0
    for path in sorted(files, key=lambda item: item.as_posix().lower()):
        rel = rel_posix(path, root)
        if rel in seen:
            continue
        seen.add(rel)
        try:
            if path.stat().st_size > bounds["max_text_bytes"]:
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        text = normalise(raw)
        for number, line in enumerate(text.split(NL), start=1):
            if len(line) > 4000:
                line = line[:4000]
            for pattern_name, pattern in (
                ("old_root", OLD_ROOT_PATTERN),
                ("other_k_ai_path", OTHER_K_AI_PATTERN),
                ("user_home_path", USER_PATH_PATTERN),
            ):
                for found in pattern.finditer(line):
                    value = found.group(0)
                    if pattern_name == "other_k_ai_path":
                        rest = line[found.start():]
                        if OLD_ROOT_PATTERN.match(rest) or CANONICAL_ROOT_PATTERN.match(rest):
                            continue
                    classification, reason = classify_stale_match(rel)
                    counts[(pattern_name, classification)] = counts.get((pattern_name, classification), 0) + 1
                    files_with_matches.add(rel)
                    if len(matches) < bounds["max_stale_matches"]:
                        matches.append({
                            "path": rel,
                            "line": number,
                            "pattern": pattern_name,
                            "value": value,
                            "classification": classification,
                            "reason": reason,
                            "context": line.strip()[:180],
                        })
            if SYSTEMDRIVE_LITERAL in line:
                classification, reason = classify_stale_match(rel)
                counts[("systemdrive_literal", classification)] = counts.get(("systemdrive_literal", classification), 0) + 1
                files_with_matches.add(rel)
                if len(matches) < bounds["max_stale_matches"]:
                    matches.append({
                        "path": rel, "line": number, "pattern": "systemdrive_literal",
                        "value": SYSTEMDRIVE_LITERAL, "classification": classification,
                        "reason": reason, "context": line.strip()[:180],
                    })
    by_pattern: dict[str, int] = {}
    by_classification: dict[str, int] = {}
    for (pattern_name, classification), count in counts.items():
        by_pattern[pattern_name] = by_pattern.get(pattern_name, 0) + count
        by_classification[classification] = by_classification.get(classification, 0) + count
    return {
        "scanned_files": scanned,
        "files_with_matches": len(files_with_matches),
        "matches": matches,
        "match_count": sum(counts.values()),
        "counts_by_pattern": dict(sorted(by_pattern.items())),
        "counts_by_classification": dict(sorted(by_classification.items())),
        "truncated": len(matches) >= bounds["max_stale_matches"],
    }


def classify_stale_match(rel: str) -> tuple[str, str]:
    if rel.startswith("tests/"):
        return DO_NOT_TOUCH, "intentional relocation/migration test fixture"
    if rel in ("scripts/verify_relocation.py", "scripts/migrate_project_root.py"):
        return DO_NOT_TOUCH, "intentional legacy-root constant used by migration verification"
    if rel.startswith("dist/"):
        return DO_NOT_TOUCH, "stale release-artifact metadata; regenerate with the stage-6 portable build"
    if rel == "build/portable_plan.json":
        return NEEDS_AUTHORIZATION, "stale generated metadata with old absolute paths"
    if rel.startswith("docs/") or rel.startswith("build/") or rel.startswith("PATCH/"):
        return DO_NOT_TOUCH, "historical documentation/evidence; old paths are preserved intentionally"
    if rel == "scripts/audit_repository_hygiene.py":
        return DO_NOT_TOUCH, "audit tool declares the legacy patterns it searches for"
    if rel == "config/voicebridge.yaml":
        return DO_NOT_TOUCH, "external project configuration (user data path)"
    if rel in ROOT_HISTORICAL_DOCS or rel.endswith(".patch"):
        return DO_NOT_TOUCH, "historical handoff/patch evidence"
    return NEEDS_AUTHORIZATION, "operational file references a stale absolute path"


def parse_worktrees(text: str) -> list[dict]:
    worktrees: list[dict] = []
    current: dict = {}
    for line in text.split(NL):
        stripped = line.strip()
        if not stripped:
            if current:
                worktrees.append(current)
                current = {}
            continue
        if stripped.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": stripped[len("worktree "):], "head": "", "branch": "", "detached": False}
        elif stripped.startswith("HEAD ") and current:
            current["head"] = stripped[len("HEAD "):]
        elif stripped.startswith("branch ") and current:
            current["branch"] = stripped[len("branch "):]
        elif stripped == "detached" and current:
            current["detached"] = True
    if current:
        worktrees.append(current)
    return worktrees


def run_git(root: Path, args: list[str], timeout: int = 20) -> tuple[int, str]:
    environment = dict(os.environ)
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "PAGER": "cat",
                        "NO_COLOR": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=environment,
        )
        return int(result.returncode), (result.stdout or "") + (result.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)


def scan_worktrees(root: Path, bounds: dict, worktree_text: str | None = None) -> dict:
    if worktree_text is None:
        code, output = run_git(root, ["worktree", "list", "--porcelain"])
        worktree_text = output if code == 0 else ""
    parsed = parse_worktrees(worktree_text)
    worktrees: list[dict] = []
    for item in parsed:
        path = Path(item["path"])
        exists = path.exists()
        inside = exists and under_root(path, root)
        stale_reasons: list[str] = []
        if not exists:
            stale_reasons.append("registered path does not exist")
        elif not inside:
            stale_reasons.append("registered path is outside the repository (temporary worktree)")
        files = 0
        total = 0
        measurement_truncated = False
        try:
            is_primary = path.resolve() == root.resolve()
        except OSError:
            is_primary = False
        if exists and path.is_dir() and not is_primary:
            state = {"started": time.monotonic(), "files_seen": 0, "truncated": False,
                     "symlinks_skipped": 0}
            scanned = walk_files(path, state, bounds)
            files = len(scanned)
            for scanned_path in scanned:
                try:
                    total += scanned_path.stat().st_size
                except OSError:
                    continue
            measurement_truncated = bool(state["truncated"] or total > bounds["max_worktree_bytes"])
        classification = NEEDS_AUTHORIZATION if stale_reasons else DO_NOT_TOUCH
        worktrees.append({
            "path": str(path),
            "head": item.get("head", ""),
            "branch": item.get("branch", ""),
            "detached": bool(item.get("detached")),
            "exists": bool(exists),
            "inside_repository": bool(inside),
            "stale_reasons": stale_reasons,
            "classification": classification,
            "files": files,
            "bytes": total,
            "measurement_truncated": measurement_truncated,
            "primary": bool(is_primary),
        })
    stale = [item for item in worktrees if item["classification"] == NEEDS_AUTHORIZATION]
    return {
        "registered_count": len(worktrees),
        "worktrees": worktrees,
        "stale_count": len(stale),
        "stale": stale,
    }


def scan_runtime_copies(root: Path) -> dict:
    python_copies: list[dict] = []
    candidates: list[Path] = []
    direct = root / "python" / "python.exe"
    if direct.is_file():
        candidates.append(direct)
    for pattern in ("dist/*/python/python.exe", "*/python/python.exe", "python*/python.exe"):
        for candidate in sorted(root.glob(pattern)):
            if candidate.is_file() and candidate not in candidates:
                candidates.append(candidate)
    marker_names = ("python.exe", "python312.zip", "python312.dll")
    for candidate in candidates:
        base = candidate.parent
        markers: dict[str, dict] = {}
        for name in marker_names:
            marker = base / name
            if not marker.is_file():
                continue
            try:
                markers[name] = {"size": marker.stat().st_size, "sha256": sha256_file(marker)}
            except OSError:
                continue
        python_copies.append({
            "kind": "python-runtime",
            "path": rel_posix(candidate, root),
            "markers": markers,
            "classification": DO_NOT_TOUCH,
        })
    crewai_copies: list[dict] = []
    for pattern in ("python/Lib/site-packages/crewai", "dist/*/python/Lib/site-packages/crewai"):
        for candidate in sorted(root.glob(pattern)):
            if not candidate.is_dir():
                continue
            init = candidate / "__init__.py"
            crewai_copies.append({
                "kind": "crewai-package",
                "path": rel_posix(candidate, root),
                "version_file": rel_posix(init, root) if init.is_file() else "",
                "classification": DO_NOT_TOUCH,
            })
    identical = False
    if len(python_copies) >= 2:
        first = python_copies[0]["markers"].get("python.exe", {}).get("sha256")
        identical = bool(first) and all(
            item["markers"].get("python.exe", {}).get("sha256") == first for item in python_copies[1:]
        )
    return {
        "python_copies": python_copies,
        "crewai_copies": crewai_copies,
        "duplicate_python_runtime": len(python_copies) > 1,
        "identical_python_runtime_markers": identical,
        "note": "runtime copies belong to the release/payload and are never deleted without explicit authorization",
    }


def validate_launchers(root: Path) -> list[dict]:
    checks: list[dict] = []
    cli_path = root / "nl_coding_agent" / "cli.py"
    commands: set[str] = set()
    if cli_path.is_file():
        try:
            cli_text = cli_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            cli_text = ""
        for chunk in re.findall(r"add_parser[(][^)]{0,120}", cli_text):
            for name in re.findall(r"[\"']([A-Za-z0-9_-]+)[\"']", chunk):
                commands.add(name)
    root_launchers = sorted(
        [path for path in root.glob("*.bat") if path.is_file()]
        + [path for path in root.glob("*.ps1") if path.is_file()],
        key=lambda item: item.name.lower(),
    )
    launchers: list[tuple[Path, str]] = [(path, path.name) for path in root_launchers]
    launchers_dir = root / "scripts" / "launchers"
    if launchers_dir.is_dir():
        nested = sorted(
            [item for item in launchers_dir.rglob("*.bat") if item.is_file()]
            + [item for item in launchers_dir.rglob("*.ps1") if item.is_file()],
            key=lambda item: item.as_posix().lower(),
        )
        launchers.extend((path, path.relative_to(root).as_posix()) for path in nested)
    if not launchers:
        checks.append({"check": "launchers.present", "status": "WARN",
                       "detail": "no launcher .bat/.ps1 files found at repository root or scripts/launchers"})
        return checks
    for launcher, label in launchers:
        try:
            text = launcher.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            checks.append({"check": "launcher." + label, "status": "FAIL",
                           "detail": "cannot read launcher: " + str(exc)})
            continue
        normalised = normalise(text)
        references: list[str] = []
        for candidate in re.findall(r"[^\"'\s]+[.](?:py|exe)", text, re.IGNORECASE):
            cleaned = (normalise(candidate).replace("%~dp0", "").replace("%CD%", "")
                       .replace("%ROOT%", "").lstrip("./"))
            if cleaned and cleaned not in references:
                references.append(cleaned)
        missing: list[str] = []
        for reference in references:
            target = root / reference
            if not target.exists():
                missing.append(reference)
        launcher_commands: list[str] = []
        for match in re.finditer(r"nl_agent[.]py[\"']?[ ]+([A-Za-z0-9_-]+)", normalised):
            launcher_commands.append(match.group(1))
        unknown = [command for command in launcher_commands if command not in commands]
        status = "PASS" if not missing and not unknown else "FAIL"
        detail = "refs=" + str(len(references)) + " missing=" + repr(missing)
        if launcher_commands:
            detail += " commands=" + repr(launcher_commands)
        if unknown:
            detail += " unknown_commands=" + repr(unknown)
        checks.append({"check": "launcher." + label, "status": status, "detail": detail})
    return checks


def validate_dependencies(root: Path, dependency_versions: dict | None = None) -> list[dict]:
    checks: list[dict] = []
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        checks.append({"check": "dependencies.pyproject", "status": "FAIL",
                       "detail": "pyproject.toml is missing"})
        return checks
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        checks.append({"check": "dependencies.pyproject", "status": "FAIL",
                       "detail": "cannot parse pyproject.toml: " + str(exc)})
        return checks
    project = data.get("project") or {}
    dependencies = project.get("dependencies") or []
    versions = dict(dependency_versions or {})
    for dependency in dependencies:
        text = str(dependency)
        match = re.match(r"([A-Za-z0-9_.-]+)(?:[<>=!~][^;]*)?([;].*)?$", text)
        name = match.group(1) if match else text
        spec = text
        installed = versions.get(name)
        if installed is None:
            try:
                installed = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                installed = None
        pinned = "==" in spec
        status = "PASS"
        detail = "spec=" + spec + " installed=" + str(installed)
        if installed is None:
            status = "FAIL"
            detail += " (not installed)"
        elif pinned:
            expected = spec.split("==", 1)[1].strip()
            if installed != expected:
                status = "FAIL"
                detail += " (pin mismatch)"
        else:
            status = "WARN"
            detail += " (not pinned)"
        checks.append({"check": "dependency." + name, "status": status, "detail": detail})
    requires_python = str(project.get("requires-python") or "")
    current = "{0}.{1}".format(sys.version_info[0], sys.version_info[1])
    status = "PASS"
    if requires_python.startswith(">="):
        minimum = requires_python[len(">="):].strip()
        try:
            status = "PASS" if tuple(int(part) for part in current.split(".")) >= tuple(
                int(part) for part in minimum.split(".")[:2]) else "FAIL"
        except ValueError:
            status = "WARN"
    checks.append({"check": "dependency.python_version", "status": status,
                   "detail": "requires-python=" + requires_python + " current=" + current})
    return checks


def validate_manifests(root: Path) -> list[dict]:
    checks: list[dict] = []
    sha_manifest = root / "SHA256_MANIFEST.json"
    if not sha_manifest.is_file():
        checks.append({"check": "manifest.sha256", "status": "WARN",
                       "detail": "SHA256_MANIFEST.json is missing"})
    else:
        try:
            entries = json.loads(sha_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            checks.append({"check": "manifest.sha256", "status": "FAIL",
                           "detail": "cannot parse SHA256_MANIFEST.json: " + str(exc)})
            entries = {}
        if isinstance(entries, dict) and entries:
            failures: list[str] = []
            for rel, expected in entries.items():
                path = root / rel
                if not path.is_file():
                    failures.append(rel + ": missing")
                    continue
                try:
                    actual = sha256_file(path)
                except OSError as exc:
                    failures.append(rel + ": " + str(exc))
                    continue
                if actual != expected:
                    failures.append(rel + ": hash mismatch")
            checks.append({"check": "manifest.sha256", "status": "PASS" if not failures else "FAIL",
                           "detail": str(len(entries)) + " entries; failures=" + repr(failures[:5])})

    index_path = root / "docs" / "product-blueprint" / "INDEX.json"
    if index_path.is_file():
        try:
            json.loads(index_path.read_text(encoding="utf-8"))
            checks.append({"check": "manifest.blueprint_index_json", "status": "PASS",
                           "detail": str(index_path.relative_to(root).as_posix())})
        except (OSError, json.JSONDecodeError) as exc:
            checks.append({"check": "manifest.blueprint_index_json", "status": "FAIL",
                           "detail": str(exc)})
    else:
        checks.append({"check": "manifest.blueprint_index_json", "status": "WARN",
                       "detail": "docs/product-blueprint/INDEX.json is missing"})

    payload_manifest = root / "dist" / "portable-release" / "payload_manifest.json"
    if payload_manifest.is_file():
        try:
            payload = json.loads(payload_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            checks.append({"check": "manifest.dist_payload", "status": "FAIL", "detail": str(exc)})
            payload = {}
        source = normalise(str((payload or {}).get("source") or ""))
        stale = bool(OLD_ROOT_PATTERN.search(source))
        checks.append({
            "check": "manifest.dist_payload",
            "status": "WARN" if stale else "PASS",
            "detail": "source=" + source + (" (pre-relocation root; stale)" if stale else ""),
        })
    return checks


def validate_config(root: Path) -> list[dict]:
    checks: list[dict] = []
    required = [
        "nl_agent.py",
        "pyproject.toml",
        "config/models.yaml",
        "config/voicebridge.yaml",
        ".gitignore",
    ]
    missing = [rel for rel in required if not (root / rel).exists()]
    checks.append({"check": "config.required_paths", "status": "PASS" if not missing else "FAIL",
                   "detail": "missing=" + repr(missing)})
    models_path = root / "config" / "models.yaml"
    if models_path.is_file():
        roles: list[str] = []
        try:
            import yaml
            data = yaml.safe_load(models_path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                roles = sorted(str(name) for name in (data.get("roles") or {}))
        except Exception:
            roles = []
        checks.append({"check": "config.models_yaml",
                       "status": "PASS" if roles else "WARN",
                       "detail": "roles=" + repr(roles)})
    voicebridge = root / "config" / "voicebridge.yaml"
    if voicebridge.is_file():
        external = ""
        try:
            import yaml
            data = yaml.safe_load(voicebridge.read_text(encoding="utf-8")) or {}
            external = str(((data.get("project") or {}).get("root")) or "")
        except Exception:
            external = ""
        exists = bool(external) and Path(external).exists()
        checks.append({"check": "config.external_project",
                       "status": "WARN" if external else "PASS",
                       "detail": ("external root configured: " + normalise(external)
                                  + (" (exists, user data - never touched by audits)" if exists
                                     else " (not present on this machine)")) if external else "no external project"})
    return checks


def validate_git(root: Path) -> tuple[list[dict], dict]:
    checks: list[dict] = []
    code, output = run_git(root, ["rev-parse", "--show-toplevel"])
    top = output.strip().splitlines()[-1] if output.strip() else ""
    checks.append({"check": "git.repository", "status": "PASS" if code == 0 and top else "FAIL",
                   "detail": "toplevel=" + normalise(top)})
    code, branch = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    checks.append({"check": "git.branch", "status": "PASS" if code == 0 else "FAIL",
                   "detail": branch.strip()[:120]})
    code, head = run_git(root, ["rev-parse", "HEAD"])
    checks.append({"check": "git.head", "status": "PASS" if code == 0 else "FAIL",
                   "detail": head.strip()[:60]})
    code, status = run_git(root, ["status", "--porcelain"])
    dirty = [line for line in status.splitlines() if line.strip()]
    checks.append({"check": "git.working_tree",
                   "status": "PASS" if code == 0 else "FAIL",
                   "detail": str(len(dirty)) + " uncommitted path(s)"})
    info = {
        "toplevel": normalise(top),
        "branch": branch.strip(),
        "head": head.strip(),
        "dirty_paths": len(dirty),
    }
    return checks, info


def build_recommendations(report: dict) -> list[dict]:
    recommendations: list[dict] = []

    def add(identifier: str, classification: str, title: str, paths: list[str],
            action: str, rationale: str, validation: str, bytes_affected: int = 0) -> None:
        recommendations.append({
            "id": identifier,
            "classification": classification,
            "title": title,
            "paths": paths,
            "action": action,
            "rationale": rationale,
            "validation": validation,
            "bytes_affected": int(bytes_affected),
        })

    caches = report.get("caches") or {}
    candidates = caches.get("repo_cleanup_candidates") or []
    if candidates:
        add("H-01", SAFE, "Remove generated repository caches",
            [item["path"] for item in candidates],
            "delete the listed __pycache__/.pytest_cache directories",
            "generated bytecode/pytest caches are reproducible and not source or user data",
            "no validation required; Python/pytest regenerate them on demand",
            caches.get("repo_cleanup_bytes") or 0)

    system_drive = [item for item in report.get("obsolete") or []
                    if item["kind"] == "accidental-path-tree"]
    if system_drive:
        add("H-02", SAFE, "Remove accidental %SystemDrive% cache tree",
            [item["path"] for item in system_drive],
            "delete the literal %SystemDrive% directory after confirming no process holds the files",
            "accidental Windows cache copies created by an unexpanded variable; not source, user data or evidence",
            "verify the directory is gone; no imports/launchers reference it",
            sum(item["bytes"] for item in system_drive))

    duplicates = [item for item in report.get("obsolete") or []
                  if item["kind"] == "duplicate-build-evidence"]
    if duplicates:
        add("H-03", SAFE, "Remove build/ copies identical to tracked docs/ plans",
            [item["path"] for item in duplicates],
            "delete the build/ duplicates; keep the tracked docs/ copy",
            "byte-identical duplicates; build/ is disposable generated output",
            "hash equality is re-checked by the audit; docs/ copy remains authoritative",
            sum(item["bytes"] for item in duplicates))

    temp_scripts = [item for item in report.get("obsolete") or []
                    if item["kind"] == "temp-repair-script"]
    if temp_scripts:
        add("H-04", NEEDS_AUTHORIZATION, "Archive and remove one-off root repair scripts",
            [item["path"] for item in temp_scripts],
            "archive copies under build/phase5/archive/ if the Lead wants history, then delete and commit",
            "scripts mutate repository files or the live SQLite database and are superseded by the committed tree",
            "targeted pytest + full offscreen suite; git diff shows no code change",
            sum(item["bytes"] for item in temp_scripts))

    patch_items = [item for item in report.get("obsolete") or []
                   if item["kind"] in ("applied-patch-artifact", "applied-patch-copy-dir")]
    if patch_items:
        add("H-05", NEEDS_AUTHORIZATION, "Archive and remove applied patch artifacts",
            [item["path"] for item in patch_items],
            "copy PATCH README/re-audit into build evidence, then remove FOUNDATION_CHANGES.patch and PATCH/ after approval",
            "the audited patch is already applied; SHA256_MANIFEST retains the audited hashes",
            "verify SHA256_MANIFEST still matches live files; targeted staging/recovery tests + full suite",
            sum(item["bytes"] for item in patch_items))

    worktrees = [item for item in report.get("obsolete") or []
                 if item["kind"] == "stale-git-worktree"]
    if worktrees:
        add("H-06", NEEDS_AUTHORIZATION, "Remove stale registered git worktree",
            [item["path"] for item in worktrees],
            "after confirming no process uses it: git worktree remove --force <path>, then git worktree prune",
            "temporary SH-07 worktree left registered after evidence collection; not part of the active repository",
            "git worktree list shows only the canonical worktree; git status/branch/HEAD unchanged",
            sum(item["bytes"] for item in worktrees if item["kind"] == "stale-git-worktree"))

    metadata = [item for item in report.get("obsolete") or []
                if item["kind"] in ("stale-generated-metadata", "stray-build-script")]
    if metadata:
        add("H-07", NEEDS_AUTHORIZATION, "Clean or regenerate stale build metadata",
            [item["path"] for item in metadata],
            "regenerate build/portable_plan.json at stage 6 and archive/remove build/audit_payload_db.py after approval",
            "generated metadata still references the pre-relocation root or is scratch code",
            "regenerated metadata contains the canonical root; no launcher/import references these files",
            sum(item["bytes"] for item in metadata))

    stale_operational = (report.get("stale_paths") or {}).get("matches") or []
    metadata_paths = {item["path"] for item in metadata}
    operational = [item for item in stale_operational
                   if item.get("classification") == NEEDS_AUTHORIZATION
                   and item["path"] not in metadata_paths]
    if operational:
        root_path = Path(report.get("root") or ".")
        files = sorted({item["path"] for item in operational})
        total_bytes = 0
        for rel in files:
            try:
                total_bytes += (root_path / rel).stat().st_size
            except OSError:
                continue
        add("H-08", NEEDS_AUTHORIZATION, "Fix stale absolute paths in operational files",
            files,
            "update the stale references after review; do not rewrite historical docs",
            "operational metadata/configuration must not point at the retired root",
            "python scripts/verify_relocation.py --json; grep clean; full suite",
            total_bytes)

    add("H-09", DO_NOT_TOUCH, "Preserve user data, logs and the live SQLite database",
        ["data/", "logs/"],
        "no cleanup; use the retention tooling with explicit human confirmation if ever needed",
        "user data, mission history and diagnostics are not cache and must never be deleted by a hygiene pass",
        "sqlite integrity/backups unchanged; not applicable")

    add("H-10", DO_NOT_TOUCH, "Preserve embedded Python runtime and CrewAI vendor checkout",
        ["python/", "crewAI/", "crewAI-tools/"],
        "no cleanup; vendor checkout policy requires explicit user approval for any change",
        "runtime and reference checkout are protected; deleting them breaks the application and violates workspace rules",
        "python/python.exe --version; import crewai; scripts/verify_relocation.py")

    dist = [item for item in report.get("obsolete") or []
            if item["kind"] == "stale-portable-release"]
    add("H-11", DO_NOT_TOUCH, "Do not delete the existing release artifact",
        [item["path"] for item in dist] or ["dist/"],
        "keep dist/portable-release until stage 6 rebuilds one verified portable payload with explicit authorization",
        "release outputs and acceptance evidence are protected; the current artifact is stale but cannot be removed without approval",
        "stage 6 rebuild + scripts/verify_relocation.py + launcher/import smoke + full suite")

    add("H-12", DO_NOT_TOUCH, "Preserve build/ and docs/ evidence",
        ["build/", "docs/evidence/"],
        "no cleanup; build/ and docs/evidence hold stage acceptance and audit evidence",
        "evidence must not be deleted or moved without explicit authorization",
        "not applicable")

    add("H-13", DO_NOT_TOUCH, "Preserve external project/user data paths",
        ["config/voicebridge.yaml"],
        "no cleanup; external project directories, backups and shared model caches are outside this repository's ownership",
        "the external VoiceBridge project (including archives) is user data and never touched by repository hygiene",
        "not applicable")

    add("H-14", NEEDS_AUTHORIZATION, "Review historical root handoff documents",
        [item["path"] for item in report.get("obsolete") or []
         if item["kind"] == "historical-handoff-doc"],
        "review with the Lead; archive under docs/history/ only with approval",
        "historical handoff notes are not runtime requirements but may be useful migration context",
        "documentation links/README references checked after any move")

    for recommendation in recommendations:
        if recommendation["classification"] == SAFE:
            recommendation["rationale"] += "; no user data, runtime, vendor, dist/build or evidence is affected"
    return recommendations


def audit_repository(
    root: str | Path,
    *,
    dependency_versions: dict | None = None,
    worktree_text: str | None = None,
    bounds: dict | None = None,
) -> dict:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError("repository root is not a directory: " + str(root_path))
    limit = default_bounds()
    if bounds:
        limit.update({key: value for key, value in bounds.items() if value is not None})
    started = time.monotonic()
    state = {"started": started, "files_seen": 0, "truncated": False, "symlinks_skipped": 0}
    areas: list[dict] = []
    for entry in sorted(root_path.iterdir(), key=lambda item: item.name.lower()):
        areas.append(measure_area(root_path, entry.name, state, limit))
    total_files = sum(item["files"] for item in areas)
    total_bytes = sum(item["bytes"] for item in areas)

    caches = scan_caches(root_path, state, limit)
    duplicates = scan_duplicates(root_path, state, limit)
    code, tracked_output = run_git(root_path, ["ls-files", "-z"])
    tracked = {item for item in tracked_output.split(chr(0)) if item} if code == 0 else set()
    worktrees = scan_worktrees(root_path, limit, worktree_text=worktree_text)
    obsolete = scan_obsolete(root_path, duplicates, caches, worktrees, tracked)
    stale_paths = scan_stale_paths(root_path, limit)
    runtime_copies = scan_runtime_copies(root_path)

    checks: list[dict] = []
    checks.extend(validate_launchers(root_path))
    checks.extend(validate_dependencies(root_path, dependency_versions))
    checks.extend(validate_manifests(root_path))
    checks.extend(validate_config(root_path))
    git_checks, git_info = validate_git(root_path)
    checks.extend(git_checks)
    fail = sum(1 for item in checks if item["status"] == "FAIL")
    warn = sum(1 for item in checks if item["status"] == "WARN")
    passed = sum(1 for item in checks if item["status"] == "PASS")

    elapsed = round(time.monotonic() - started, 3)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "root": str(root_path),
        "read_only": True,
        "actions_taken": [],
        "bounds": {key: limit[key] for key in (
            "max_seconds", "max_files", "max_hash_bytes", "max_hash_files",
            "max_hash_total_bytes", "max_text_bytes")},
        "totals": {
            "files": total_files,
            "bytes": total_bytes,
            "human": human_bytes(total_bytes),
            "git_files": sum(item["files"] for item in areas if item["name"] == ".git"),
            "git_bytes": sum(item["bytes"] for item in areas if item["name"] == ".git"),
            "truncated": bool(state["truncated"]),
            "symlinks_skipped": int(state["symlinks_skipped"]),
            "elapsed_seconds": elapsed,
        },
        "areas": areas,
        "caches": caches,
        "duplicates": duplicates,
        "obsolete": obsolete,
        "stale_paths": stale_paths,
        "worktrees": worktrees,
        "runtime_copies": runtime_copies,
        "git": git_info,
        "validations": {
            "checks": checks,
            "summary": {"pass": passed, "warn": warn, "fail": fail},
        },
    }
    report["recommendations"] = build_recommendations(report)
    return report

def _md_cell(value) -> str:
    return str(value).replace("|", "/").replace(chr(10), " ")


def _md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(_md_cell(item) for item in headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(item) for item in row) + " |")
    return NL.join(lines)


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    totals = report.get("totals") or {}
    areas = report.get("areas") or []
    caches = report.get("caches") or {}
    duplicates = report.get("duplicates") or {}
    obsolete = report.get("obsolete") or []
    stale = report.get("stale_paths") or {}
    worktrees = report.get("worktrees") or {}
    runtime = report.get("runtime_copies") or {}
    validations = report.get("validations") or {}
    recommendations = report.get("recommendations") or []

    lines.append("# Repository hygiene audit")
    lines.append("")
    lines.append("**Read-only audit of the canonical repository.** Generated: "
                 + str(report.get("generated_at")) + " - root: `" + normalise(str(report.get("root"))) + "`")
    lines.append("")
    lines.append("The audit never deletes, moves, renames or modifies repository files, never starts a "
                 "mission/model/network request, and performs no git write operation. It only reads the "
                 "filesystem and runs local read-only git queries (rev-parse, status, worktree list).")
    lines.append("")
    lines.append("**Actions taken by this run:** " + (
        "none (read-only)" if not report.get("actions_taken") else ", ".join(report["actions_taken"])))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    summary_rows = [
        ["Files (all areas)", totals.get("files"), human_bytes(totals.get("bytes") or 0)],
        ["Git metadata (.git)", totals.get("git_files"), human_bytes(totals.get("git_bytes") or 0)],
        ["Repository caches", caches.get("repo_cleanup_files"), human_bytes(caches.get("repo_cleanup_bytes") or 0)],
        ["Cache dirs/files (all areas)", str(caches.get("dirs")) + " dirs / " + str(caches.get("files")),
         human_bytes(caches.get("bytes") or 0)],
        ["Duplicate groups", duplicates.get("group_count"), str(duplicates.get("duplicate_files")) + " files"],
        ["Obsolete/stale candidates", len(obsolete),
         str(sum(1 for item in obsolete if item.get("classification") == SAFE)) + " SAFE / "
         + str(sum(1 for item in obsolete if item.get("classification") == NEEDS_AUTHORIZATION)) + " NEEDS-AUTHORIZATION / "
         + str(sum(1 for item in obsolete if item.get("classification") == DO_NOT_TOUCH)) + " DO-NOT-TOUCH"],
        ["Stale absolute-path matches", stale.get("match_count"),
         str(stale.get("files_with_matches")) + " files, "
         + str((stale.get("counts_by_classification") or {}).get(NEEDS_AUTHORIZATION, 0)) + " operational"],
        ["Registered git worktrees", worktrees.get("registered_count"),
         str(worktrees.get("stale_count")) + " stale"],
        ["Validation checks", str((validations.get("summary") or {}).get("pass")) + " PASS",
         str((validations.get("summary") or {}).get("warn")) + " WARN / "
         + str((validations.get("summary") or {}).get("fail")) + " FAIL"],
        ["Audit elapsed", str(totals.get("elapsed_seconds")) + " s",
         "truncated=" + str(totals.get("truncated"))],
    ]
    lines.append(_md_table(["Metric", "Count", "Size / detail"], summary_rows))
    lines.append("")
    lines.append("## Areas")
    lines.append("")
    area_rows = [[item["name"], item["kind"], item["classification"], item["files"],
                  human_bytes(item["bytes"])] for item in sorted(areas, key=lambda item: -item["bytes"])]
    lines.append(_md_table(["Area", "Kind", "Class", "Files", "Size"], area_rows))
    lines.append("")

    lines.append("## Caches")
    lines.append("")
    lines.append("All cache directories: " + str(caches.get("dirs")) + " dirs, "
                 + str(caches.get("files")) + " files, " + human_bytes(caches.get("bytes") or 0)
                 + ". Runtime/vendor/build/docs caches are protected; only repository caches are cleanup candidates.")
    lines.append("")
    cache_rows = []
    for item in (caches.get("entries") or [])[:20]:
        cache_rows.append([item["path"], item["area"], item["files"], human_bytes(item["bytes"]), item["classification"]])
    if cache_rows:
        lines.append(_md_table(["Cache directory", "Area", "Files", "Size", "Class"], cache_rows))
        lines.append("")

    lines.append("## Duplicate files (size + sha256, bounded)")
    lines.append("")
    lines.append("Hashed files: " + str(duplicates.get("hashed_files")) + " ("
                 + human_bytes(duplicates.get("hashed_bytes") or 0) + "); skipped large: "
                 + str(duplicates.get("skipped_large_files")) + " (cap "
                 + human_bytes(duplicates.get("max_hash_bytes") or 0) + " per file); truncated="
                 + str(duplicates.get("truncated")) + ".")
    lines.append("")
    duplicate_rows = []
    for group in (duplicates.get("groups") or [])[:30]:
        duplicate_rows.append([human_bytes(group["size"]), group["classification"],
                               "<br>".join(group["paths"]), group.get("reason", "")])
    if duplicate_rows:
        lines.append(_md_table(["Size", "Class", "Paths", "Reason"], duplicate_rows))
        lines.append("")

    lines.append("## Obsolete / stale candidates")
    lines.append("")
    obsolete_rows = []
    for item in obsolete:
        obsolete_rows.append([item["kind"], item["path"], item["classification"],
                              "yes" if item["tracked"] else "no", human_bytes(item["bytes"]),
                              item["reason"]])
    if obsolete_rows:
        lines.append(_md_table(["Kind", "Path", "Class", "Tracked", "Size", "Reason"], obsolete_rows))
        lines.append("")

    lines.append("## Stale absolute paths")
    lines.append("")
    lines.append("Scanned files: " + str(stale.get("scanned_files")) + "; matches: "
                 + str(stale.get("match_count")) + " in " + str(stale.get("files_with_matches")) + " files.")
    lines.append("")
    lines.append("Counts by pattern: `" + json.dumps(stale.get("counts_by_pattern") or {}, ensure_ascii=False)
                 + "`; by classification: `" + json.dumps(stale.get("counts_by_classification") or {},
                                                                   ensure_ascii=False) + "`.")
    lines.append("")
    stale_rows = []
    for match in (stale.get("matches") or []):
        if match.get("classification") != NEEDS_AUTHORIZATION:
            continue
        stale_rows.append([match["path"], match["line"], match["pattern"], match["classification"],
                           match.get("value", ""), match.get("context", "")])
    if stale_rows:
        lines.append("Operational matches (action required only after approval):")
        lines.append("")
        lines.append(_md_table(["Path", "Line", "Pattern", "Class", "Value", "Context"],
                               stale_rows[:40]))
        lines.append("")
    historical = [match for match in (stale.get("matches") or [])
                  if match.get("classification") == DO_NOT_TOUCH]
    if historical:
        lines.append("Historical/intentional references (preserved, not defects): "
                     + str(len(historical)) + " shown; full JSON keeps the first "
                     + str(len(stale.get("matches") or [])) + " matches.")
        lines.append("")

    lines.append("## Git worktrees")
    lines.append("")
    worktree_rows = []
    for item in worktrees.get("worktrees") or []:
        worktree_rows.append([normalise(item["path"]), item.get("head", "")[:12],
                              ",".join(item.get("stale_reasons") or []) or "active",
                              item["classification"], human_bytes(item.get("bytes") or 0)])
    if worktree_rows:
        lines.append(_md_table(["Path", "HEAD", "State", "Class", "Size"], worktree_rows))
        lines.append("")

    lines.append("## Runtime copies")
    lines.append("")
    lines.append("Duplicate Python runtime: " + str(runtime.get("duplicate_python_runtime"))
                 + "; identical python.exe markers: " + str(runtime.get("identical_python_runtime_markers")))
    lines.append("")
    runtime_rows = []
    for item in (runtime.get("python_copies") or []) + (runtime.get("crewai_copies") or []):
        runtime_rows.append([item["kind"], item["path"], item["classification"]])
    if runtime_rows:
        lines.append(_md_table(["Kind", "Path", "Class"], runtime_rows))
        lines.append("")

    lines.append("## Validations")
    lines.append("")
    validation_rows = [[item["check"], item["status"], item["detail"]]
                       for item in (validations.get("checks") or [])]
    if validation_rows:
        lines.append(_md_table(["Check", "Status", "Detail"], validation_rows))
        lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    order = {SAFE: 0, NEEDS_AUTHORIZATION: 1, DO_NOT_TOUCH: 2}
    for recommendation in sorted(recommendations, key=lambda item: (order.get(item["classification"], 3),
                                                                    item["id"])):
        lines.append("### " + recommendation["classification"] + " - " + recommendation["id"]
                     + ": " + recommendation["title"])
        lines.append("")
        lines.append("- **Paths:** " + (", ".join("`" + normalise(path) + "`" for path in recommendation["paths"])
                                       or "(none)"))
        lines.append("- **Action:** " + recommendation["action"])
        lines.append("- **Rationale:** " + recommendation["rationale"])
        lines.append("- **Validation:** " + recommendation["validation"])
        lines.append("- **Size affected:** " + human_bytes(recommendation.get("bytes_affected") or 0))
        lines.append("")

    lines.append("## Validation plan for approved changes")
    lines.append("")
    lines.append("Apply one recommendation class at a time and re-run the audit after each step. Before any change:")
    lines.append("")
    lines.append("1. `git status --porcelain` and `git rev-parse HEAD` are recorded; no mission/autonomous run is active.")
    lines.append("2. Back up the SQLite database and `data/selfbuild_state.json` if any DB-adjacent step is approved.")
    lines.append("3. After each approved cleanup: `python scripts/audit_repository_hygiene.py` shows the expected delta and no new operational findings.")
    lines.append("4. Launchers: start `NL Coding Agent.bat` (root GUI launcher) and `scripts/launchers/doctor.bat` / `scripts/launchers/status.bat` (or the equivalent `python nl_agent.py <command>` forms).")
    lines.append('5. Imports: `python -c "import nl_coding_agent.cli, nl_coding_agent.app.services, nl_coding_agent.agents.orchestrator"`.')
    lines.append("6. Doctor and relocation gates: `python nl_agent.py doctor`; `python scripts/verify_relocation.py --json`.")
    lines.append("7. Targeted tests for touched areas, then the full offscreen suite: `python -m pytest -q tests -p no:cacheprovider` with `PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen`.")
    lines.append("8. Report the git diff and evidence; the Lead reviews and commits. No deletion of `data/`, `python/`, `crewAI/`, `dist/`, `build/` evidence, backups or model caches is authorized by this plan.")
    lines.append("")
    lines.append("## Bounds and limitations")
    lines.append("")
    bounds = report.get("bounds") or {}
    lines.append("- Bounded runtime/hashing: max_seconds=" + str(bounds.get("max_seconds"))
                 + ", max_files=" + str(bounds.get("max_files"))
                 + ", max_hash_bytes=" + str(bounds.get("max_hash_bytes"))
                 + ", max_hash_files=" + str(bounds.get("max_hash_files"))
                 + ", max_hash_total_bytes=" + str(bounds.get("max_hash_total_bytes")) + ".")
    lines.append("- Duplicate hashing excludes runtime/vendor/dist/data/logs areas and files above the per-file cap; "
                 "large runtime copies are reported structurally instead.")
    lines.append("- No network access, no model inference, no mission or supervisor run, no git write operation.")
    lines.append("- Areas classified protected/evidence are measured but never proposed for deletion; "
                 "DO-NOT-TOUCH recommendations are informational.")
    lines.append("- The audit is evidence for a human decision: it does not itself approve or perform cleanup.")
    lines.append("")
    return NL.join(lines) + NL


def validations_summary(report: dict) -> str:
    summary = (report.get("validations") or {}).get("summary") or {}
    return ("checks pass=" + str(summary.get("pass")) + " warn=" + str(summary.get("warn"))
            + " fail=" + str(summary.get("fail")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only repository hygiene audit (sizes, duplicates, obsolete/stale candidates, validations).",
        epilog="No deletions, moves, network access, model inference or autonomous runs.",
    )
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", default=str(default_root), help="repository root (default: script parent)")
    parser.add_argument("--json-out", default=str(DEFAULT_JSON),
                        help="machine JSON report path (default: build/phase5/repository_hygiene.json)")
    parser.add_argument("--markdown-out", default=str(DEFAULT_MD),
                        help="markdown report path (default: build/phase5/repository_hygiene.md)")
    parser.add_argument("--max-seconds", type=float, default=None, help="soft deadline for walks/hashing")
    parser.add_argument("--max-files", type=int, default=None, help="maximum files walked per scan")
    parser.add_argument("--max-hash-bytes", type=int, default=None, help="maximum bytes per hashed file")
    parser.add_argument("--max-hash-files", type=int, default=None, help="maximum files hashed")
    parser.add_argument("--no-write", action="store_true", help="do not write report files")
    parser.add_argument("--quiet", action="store_true", help="only print the summary line")
    args = parser.parse_args(argv)

    bounds = {}
    if args.max_seconds is not None:
        bounds["max_seconds"] = max(1.0, args.max_seconds)
    if args.max_files is not None:
        bounds["max_files"] = max(1, args.max_files)
    if args.max_hash_bytes is not None:
        bounds["max_hash_bytes"] = max(0, args.max_hash_bytes)
    if args.max_hash_files is not None:
        bounds["max_hash_files"] = max(0, args.max_hash_files)

    try:
        report = audit_repository(args.root, bounds=bounds or None)
    except Exception as exc:  # noqa: BLE001 - CLI reports the failure
        print("hygiene audit failed: " + str(exc), file=sys.stderr)
        return 2

    summary = (validations_summary(report) + " | files=" + str(report["totals"]["files"])
               + " (" + human_bytes(report["totals"]["bytes"]) + ")"
               + " | duplicate_groups=" + str(report["duplicates"]["group_count"])
               + " | obsolete=" + str(len(report["obsolete"]))
               + " | stale_matches=" + str(report["stale_paths"]["match_count"])
               + " | worktrees_stale=" + str(report["worktrees"]["stale_count"]))
    if not args.no_write:
        json_path = Path(args.json_out)
        markdown_path = Path(args.markdown_out)
        if not json_path.is_absolute():
            json_path = default_root / json_path
        if not markdown_path.is_absolute():
            markdown_path = default_root / markdown_path
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + NL, encoding="utf-8")
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        summary += " | json=" + normalise(str(json_path)) + " | markdown=" + normalise(str(markdown_path))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



"""Pre-upload secrets/history/repository audit for the private cross-platform beta.

Implements NL-BP-162 (audit evidence) and supports NL-BP-163 (owner authorization
gate). READ-ONLY GUARANTEE: this tool never deletes, moves, renames or modifies
repository files, never writes Git state, never pushes/fetches, never changes
visibility or collaborators, never publishes a release and never opens a network
connection. It writes only the explicitly requested JSON/Markdown report paths
and does not even create those unless requested (use --no-write to suppress).

Scope (bounded and deterministic):
  * tracked files: secret patterns (cloud/API/provider tokens, private keys,
    passwords, .env content, credential URLs), private SQLite/user databases,
    embedded runtimes and venvs, vendor checkouts, model checkpoints/large
    binaries, heavyweight build outputs, personal absolute paths and private
    URLs;
  * Git history (where available, bounded): added lines in bounded history for
    the same secret patterns, and paths that ever existed in history for
    DB/runtime/vendor/model/heavy artifacts;
  * Git config remote URLs for embedded credentials.

Every matched value is REDACTED: only a SHA-256 prefix (12 hex), at most a
4-character prefix and the length are reported. Context lines are redacted
before printing. Findings are classified ROTATE, EXCLUDE-FROM-UPLOAD, REVIEW or
SAFE with a recommended owner action. The tool performs none of those actions.

Exit codes: 0 = scan completed with no blocking findings; 1 = scan completed and
blocking findings exist (upload gate NOT clear); 2 = scan could not run.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core.workspace import WORKSPACE_DIRNAME  # noqa: E402

TOOL_NAME = "audit_release_secrets.py"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = 1
NL = chr(10)

ROTATE = "ROTATE"
EXCLUDE_FROM_UPLOAD = "EXCLUDE-FROM-UPLOAD"
REVIEW = "REVIEW"
SAFE = "SAFE"
CLASS_ORDER = {ROTATE: 0, EXCLUDE_FROM_UPLOAD: 1, REVIEW: 2, SAFE: 3}
BLOCKING_CLASSES = frozenset({ROTATE, EXCLUDE_FROM_UPLOAD})

DEFAULT_JSON = Path(WORKSPACE_DIRNAME) / "build" / "phase6" / "secrets_audit.json"
DEFAULT_MD = Path(WORKSPACE_DIRNAME) / "build" / "phase6" / "secrets_audit.md"

DEFAULT_BOUNDS = {
    "max_files": 5000,
    "max_file_bytes": 2000000,
    "max_total_bytes": 64000000,
    "max_findings": 500,
    "max_seconds": 120.0,
    "max_git_commits": 200,
    "max_git_bytes": 16000000,
    "max_git_seconds": 45.0,
    "max_history_paths": 50000,
}

GIT_READONLY_COMMANDS = frozenset({
    "rev-parse", "ls-files", "log", "rev-list", "show", "cat-file", "version",
})

GIT_ENV_OVERRIDES = {
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_PAGER": "cat",
    "PAGER": "cat",
    "GIT_ASKPASS": "",
}

AUTHORIZATION_NOTE = (
    "No upload, push, fetch, tag, release, package publication, repository "
    "visibility change or collaborator invitation is performed by this audit. "
    "The repository remains private. Any upload/publish/visibility/collaborator "
    "action requires explicit repository-owner authorization (NL-BP-163); this "
    "report is evidence for that owner decision only."
)

REDACTION_NOTE = (
    "All matched values are redacted: only SHA-256[0:12], a prefix of at most 4 "
    "characters and the matched length are shown; context lines have matches "
    "replaced with [REDACTED:<hash>]. Full secrets are never written to stdout, "
    "JSON or Markdown."
)

# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------

def _secret_rules():
    return [
        {"id": "aws_access_key_id", "kind": "cloud_credential", "classification": ROTATE,
         "description": "AWS access key id",
         "regex": re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b")},
        {"id": "github_token", "kind": "provider_token", "classification": ROTATE,
         "description": "GitHub token",
         "regex": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")},
        {"id": "github_fine_grained_token", "kind": "provider_token", "classification": ROTATE,
         "description": "GitHub fine-grained token",
         "regex": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")},
        {"id": "gitlab_token", "kind": "provider_token", "classification": ROTATE,
         "description": "GitLab token",
         "regex": re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")},
        {"id": "openai_key", "kind": "provider_token", "classification": ROTATE,
         "description": "OpenAI-style API key",
         "regex": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b")},
        {"id": "anthropic_key", "kind": "provider_token", "classification": ROTATE,
         "description": "Anthropic API key",
         "regex": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")},
        {"id": "google_api_key", "kind": "provider_token", "classification": ROTATE,
         "description": "Google API key",
         "regex": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")},
        {"id": "slack_token", "kind": "provider_token", "classification": ROTATE,
         "description": "Slack token",
         "regex": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")},
        {"id": "stripe_live_key", "kind": "payment_credential", "classification": ROTATE,
         "description": "Stripe live secret/restricted key",
         "regex": re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b")},
        {"id": "sendgrid_key", "kind": "provider_token", "classification": ROTATE,
         "description": "SendGrid API key",
         "regex": re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b")},
        {"id": "npm_token", "kind": "provider_token", "classification": ROTATE,
         "description": "npm token",
         "regex": re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b")},
        {"id": "pypi_token", "kind": "provider_token", "classification": ROTATE,
         "description": "PyPI API token",
         "regex": re.compile(r"\bpypi-[A-Za-z0-9_-]{30,}\b")},
        {"id": "huggingface_token", "kind": "provider_token", "classification": ROTATE,
         "description": "Hugging Face token",
         "regex": re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")},
        {"id": "private_key_block", "kind": "private_key", "classification": ROTATE,
         "description": "PEM/OpenSSH private key block",
         "regex": re.compile(r"-----BEGIN [A-Z0-9 ]{0,24}PRIVATE KEY-----")},
        {"id": "url_embedded_credentials", "kind": "credential_url", "classification": ROTATE,
         "description": "URL with user:password credentials",
         "regex": re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]{1,12}://[^/\s:@]{1,64}:[^/\s@]{1,64}@[^\s\"'<>]{3,240}")},
        {"id": "authorization_header", "kind": "provider_token", "classification": REVIEW,
         "description": "Authorization header value",
         "regex": re.compile(r"(?i)\bauthorization\s*[:=]\s*[A-Za-z0-9._~+/=-]{16,}")},
        {"id": "jwt_token", "kind": "session_token", "classification": REVIEW,
         "description": "JWT-shaped token",
         "regex": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")},
    ]


GENERIC_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|secret[_-]?key|client[_-]?secret|access[_-]?token|"
    r"auth[_-]?token|token|password|passwd|pwd|private[_-]?key)\b"
    r"\s*(?::|=)\s*[\"']([^\"'\r\n]{8,200})[\"']"
)

HIGH_ENTROPY_RE = re.compile(r"(?<![A-Za-z0-9+/_=-])([A-Za-z0-9+/_=-]{32,200})(?![A-Za-z0-9+/_=-])")

PLACEHOLDER_MARKERS = (
    "example", "placeholder", "changeme", "change-me", "change_me", "your_", "your-",
    "dummy", "fake", "sample", "redacted", "not-a-real", "not_real", "xxxx", "****",
    "todo", "replace", "insert", "generate", "none", "null", "undefined", "secret_here",
    "token_here", "key_here", "env.", "getenv", "environ", "secretref", "<", ">", "{", "}",
    chr(36) + "{", "{{", "%s", "()", "notasecret", "not-secret", "local-only", "localonly",
)
PLACEHOLDER_VALUE_RE = re.compile(r"^(?:\$\{[^}]+\}|\{\{[^}]+\}\}|<[^>]*>|%[A-Za-z_]+%|os\.environ.*|getenv\(.*)$")

FIXTURE_MARKERS = (
    "fake", "dummy", "example", "placeholder", "redacted", "not-a-real", "not_real",
    "sample", "fixture", "test-only", "test_only", "xxxx", "for-test", "for_test",
)

# Synthetic values used by the redaction regression tests in
# tests/test_diagnostic_report.py. They are documented here by full-value SHA-256
# (never by the value itself) so the audit can downgrade these exact fixture
# matches from ROTATE to REVIEW for both tracked files and Git history without
# loosening detection for any other value. Any change to the fixtures requires
# updating this allowlist and tests/test_release_secrets_audit.py.
TEST_FIXTURE_SECRET_ALLOWLIST = {
    "c042850219b29f65dfb9dbfc08408757d88391ef0fc9e4ff82b1a132bc9be36d":
        "synthetic OpenAI-style token in tests/test_diagnostic_report.py (redaction fixture)",
    "8bcac7908eb950419537b91e19adc83ce2c9cbfdacf4f81157fdadfec11f7017":
        "synthetic private-key header in tests/test_diagnostic_report.py (redaction fixture)",
    "0c5a2a21630fdb484f156efbefd96e5d337c725fb6e85a179e679d00100b67a2":
        "synthetic credential URL in tests/test_diagnostic_report.py (redaction fixture)",
}


def _is_allowlisted_test_fixture(rel: str, value: str) -> bool:
    """True only for the documented synthetic values inside tests/."""
    path_low = (rel or "").replace(os.sep, "/").lower()
    if not (path_low.startswith("tests/") or "/tests/" in path_low):
        return False
    digest = hashlib.sha256((value or "").encode("utf-8", "replace")).hexdigest()
    return digest in TEST_FIXTURE_SECRET_ALLOWLIST

PERSONAL_PATH_RULES = [
    ("windows_user_profile", re.compile(r"\b[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"'<>|]{2,64}")),
    ("posix_home_path", re.compile(r"(?<![\w.-])/(?:home|Users)/[A-Za-z0-9._-]{2,64}")),
    ("absolute_workspace_path", re.compile(r"\b[A-Za-z]:[\\/]+AI[\\/]+[^\\/\s\"'<>|]{0,120}")),
    ("file_url_absolute", re.compile(r"\bfile:/{2,3}[A-Za-z]:/[^\s\"'<>]{2,200}")),
]

PRIVATE_URL_RULES = [
    ("private_network_url", re.compile(
        r"\b(?:https?|ftp|ws|wss)://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?::\d+)?[^\s\"'<>]{0,180}", re.I)),
    ("internal_hostname_url", re.compile(
        r"\bhttps?://[A-Za-z0-9._-]+\.(?:internal|local|corp|lan|intranet)(?::\d+)?[^\s\"'<>]{0,180}", re.I)),
]

# ---------------------------------------------------------------------------
# Artifact rules
# ---------------------------------------------------------------------------

PRIVATE_DB_SUFFIXES = (".sqlite3", ".sqlite", ".db", ".sqlite3-wal", ".sqlite3-shm",
                       ".db-wal", ".db-shm", ".mdb", ".accdb")
USER_DATA_SAFE_NAMES = ("selfbuild_state.json", "mission_baselines")
MODEL_SUFFIXES = (".gguf", ".safetensors", ".ckpt", ".pt", ".pth", ".onnx", ".pkl",
                  ".pickle", ".h5", ".tflite", ".mlmodel", ".coreml", ".npy", ".npz",
                  ".bin", ".model", ".weights", ".lora", ".adapter")
ARCHIVE_BINARY_SUFFIXES = (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz",
                           ".dmg", ".pkg", ".msi", ".exe", ".dll", ".so", ".dylib",
                           ".whl", ".jar", ".class", ".wasm", ".node", ".pyd", ".pyc",
                           ".pyo")
BUILD_OUTPUT_PARTS = frozenset({
    WORKSPACE_DIRNAME,
    # Legacy root locations retained defensively for pre-reorg checkouts.
    "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cache", ".tox", ".nox", "htmlcov", ".coverage", "node_modules",
})
RUNTIME_PARTS = frozenset({
    "python", "crewAI", "crewAI-tools", "site-packages", ".venv", "venv", "env",
    "node_modules", "runtime", "runtimes", "vendor", "third_party", "third-party",
})
RUNTIME_FILE_NAMES = frozenset({
    "pyvenv.cfg", "python.exe", "python3", "python", "python.exe.manifest",
    "libpython3.dll", "libpython3.so", "activate", "activate.bat", "Activate.ps1",
})
LOCAL_DATA_PARTS = frozenset({
    "data", "logs", "state", "backups", "recovery", "staging", "mission_baselines",
    "selfbuild_state.json",
})
KEY_MATERIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".ppk",
                         ".der", ".csr", ".ovpn")
KEY_MATERIAL_NAMES = frozenset({
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc", ".git-credentials",
    ".pypirc", ".npmrc", ".htpasswd", "credentials", "credentials.json",
    "service-account.json", "secrets.json",
})
ENV_FILE_NAMES = frozenset({".env", ".env.local", ".env.production", ".env.development",
                            ".env.test", ".env.example", ".env.template", ".env.sample"})
LARGE_BINARY_BYTES = 5 * 1024 * 1024
TEXT_CANDIDATE_SUFFIXES = frozenset({
    ".py", ".pyi", ".md", ".txt", ".rst", ".log", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".bat", ".ps1", ".sh", ".bash", ".zsh", ".cmd", ".patch", ".diff",
    ".csv", ".tsv", ".html", ".htm", ".css", ".js", ".ts", ".tsx", ".jsx", ".xml",
    ".svg", ".env", ".properties", ".gitignore", ".psm1", ".pem", ".key", ".crt",
    ".cer", ".der", ".p12", ".pfx", ".ppk", ".ovpn", ".netrc", ".npmrc", ".pypirc",
    ".htpasswd", ".git-credentials", ".keystore", ".jks",
})

PRESENT_UNTRACKED_ROOTS = [
    (".env", "secret_file", EXCLUDE_FROM_UPLOAD, "Local secret file; never upload or package; rotate values if it was ever shared."),
    (".env.local", "secret_file", EXCLUDE_FROM_UPLOAD, "Local secret file; never upload or package."),
    (".npmrc", "credential_store_file", EXCLUDE_FROM_UPLOAD, "Local credential file; never upload or package."),
    (".pypirc", "credential_store_file", EXCLUDE_FROM_UPLOAD, "Local credential file; never upload or package."),
    (".netrc", "credential_store_file", EXCLUDE_FROM_UPLOAD, "Local credential file; never upload or package."),
    (".git-credentials", "credential_store_file", ROTATE, "Credential store with tokens; rotate tokens and keep it local."),
    ("python", "embedded_runtime", EXCLUDE_FROM_UPLOAD, "Embedded runtime; never upload to the source repository; keep local/protected."),
    ("crewAI", "vendor_checkout", EXCLUDE_FROM_UPLOAD, "Vendor reference checkout; never upload or package."),
    ("crewAI-tools", "vendor_checkout", EXCLUDE_FROM_UPLOAD, "Vendor reference checkout; never upload or package."),
    (WORKSPACE_DIRNAME, "workspace_output", EXCLUDE_FROM_UPLOAD,
     "Consolidated build/dist/logs/temp/cache/state workspace; never upload, package or publish."),
    ("data", "user_data", EXCLUDE_FROM_UPLOAD, "User data/SQLite/state; never upload, package or publish."),
    ("logs", "diagnostics", EXCLUDE_FROM_UPLOAD, "Run logs; never upload, package or publish (legacy location)."),
    ("state", "user_data", EXCLUDE_FROM_UPLOAD, "Runtime state; never upload, package or publish."),
    ("dist", "build_output", EXCLUDE_FROM_UPLOAD, "Release payload; never upload to source; distribute only via the owner-authorized channel."),
    ("build", "transient_evidence", EXCLUDE_FROM_UPLOAD, "Transient audit evidence; never upload to source."),
    ("cache", "scratch", EXCLUDE_FROM_UPLOAD, "Scratch cache; never upload."),
    ("temp", "scratch", EXCLUDE_FROM_UPLOAD, "Scratch directory; never upload."),
    ("tmp", "scratch", EXCLUDE_FROM_UPLOAD, "Scratch directory; never upload."),
    ("da_eliminare", "review_staging", EXCLUDE_FROM_UPLOAD,
     "User-requested review-only staging area; never upload/package and nothing may be deleted or archived without explicit user authorization."),
]


def _sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]


def redact_value(value: str) -> dict:
    """Return only hash/prefix/length evidence for a matched value."""
    value = value or ""
    prefix = ""
    if len(value) >= 8:
        prefix = value[:4]
    return {"sha256_12": _sha12(value), "prefix": prefix, "length": len(value)}


def redact_line(line: str, spans: list) -> str:
    """Replace matched spans with [REDACTED:<hash>] and truncate."""
    if not spans:
        return line[:180]
    ordered = sorted(set(spans), key=lambda item: item[0], reverse=True)
    out = line
    for start, end in ordered:
        start = max(0, min(start, len(out)))
        end = max(start, min(end, len(out)))
        if start == end:
            continue
        token = out[start:end]
        out = out[:start] + "[REDACTED:" + _sha12(token) + "]" + out[end:]
    return out[:220]


def _looks_like_placeholder(value: str) -> bool:
    low = value.strip().lower()
    if not low:
        return True
    if PLACEHOLDER_VALUE_RE.match(low):
        return True
    return any(marker in low for marker in PLACEHOLDER_MARKERS)


def _is_fixture_context(rel: str, line: str) -> bool:
    path_low = rel.replace(os.sep, "/").lower()
    low = line.lower()
    testish = (
        path_low.startswith("tests/")
        or "/tests/" in path_low
        or path_low.startswith("docs/history/")
        or "test_" in path_low
        or "fixture" in path_low
    )
    if not testish:
        return False
    return any(marker in low for marker in FIXTURE_MARKERS)


def _secret_action(rule_id: str, classification: str) -> str:
    if classification == ROTATE:
        return ("Rotate/revoke this credential before any upload; remove it from tracked files and "
                "consider history cleanup with explicit owner authorization. Never print or upload the value.")
    if classification == EXCLUDE_FROM_UPLOAD:
        return "Remove this artifact from upload scope with owner approval; do not delete user data."
    return ("Inspect and confirm whether this is a real credential/secret; if real, rotate and remove; "
            "if a fixture/example, keep it out of release artifacts and document that it is fake.")


def classify_artifact_path(rel: str, size=None, is_dir=False) -> dict | None:
    """Classify a repository-relative path as an upload-exclusion artifact."""
    norm = rel.replace(os.sep, "/")
    if norm.startswith("./"):
        norm = norm[2:]
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return None
    lower = [p.lower() for p in parts]
    base = lower[-1]
    suffix = ""
    if "." in base:
        suffix = "." + base.rsplit(".", 1)[1]

    if base in ENV_FILE_NAMES:
        return {"kind": "secret_file", "classification": EXCLUDE_FROM_UPLOAD,
                "action": "Never upload/package an environment file; keep only a placeholder .env.example with fake values."}
    if base in KEY_MATERIAL_NAMES or suffix in KEY_MATERIAL_SUFFIXES:
        return {"kind": "key_material_file", "classification": ROTATE,
                "action": "Rotate the credential material now; remove it from tracked/upload scope with owner authorization; never upload."}
    if suffix in PRIVATE_DB_SUFFIXES or base in ("nl_coding_agent.sqlite3",):
        return {"kind": "private_database", "classification": EXCLUDE_FROM_UPLOAD,
                "action": "Never upload/package a database; exclude with owner authorization; never delete user data."}
    if base in USER_DATA_SAFE_NAMES or base.startswith("selfbuild_state"):
        return {"kind": "user_data", "classification": EXCLUDE_FROM_UPLOAD,
                "action": "Never upload/package runtime user data; keep it local."}
    if any(p in RUNTIME_PARTS for p in lower) or base in RUNTIME_FILE_NAMES:
        return {"kind": "embedded_runtime_or_vendor", "classification": EXCLUDE_FROM_UPLOAD,
                "action": "Never upload/package embedded runtimes or vendor checkouts; keep them local/protected."}
    if any(p in LOCAL_DATA_PARTS for p in lower):
        return {"kind": "user_data", "classification": EXCLUDE_FROM_UPLOAD,
                "action": "Never upload/package user data, logs or mission evidence; keep local."}
    if norm.startswith("docs/evidence/"):
        if size is not None and size > LARGE_BINARY_BYTES:
            return {"kind": "acceptance_evidence", "classification": EXCLUDE_FROM_UPLOAD,
                    "action": "Large tracked acceptance evidence; do not upload in source/packages without an owner decision."}
        return None
    if any(p in BUILD_OUTPUT_PARTS for p in lower) or suffix in (".pyc", ".pyo", ".pyd", ".log") or base.startswith(".coverage"):
        return {"kind": "build_output", "classification": EXCLUDE_FROM_UPLOAD,
                "action": "Do not upload build/cache output; ensure ignore rules cover it; no deletion required."}
    if suffix in MODEL_SUFFIXES:
        return {"kind": "model_checkpoint_or_binary", "classification": EXCLUDE_FROM_UPLOAD,
                "action": "Do not upload models/checkpoints; distribute separately only with owner authorization."}
    if size is not None and size > LARGE_BINARY_BYTES:
        return {"kind": "large_binary", "classification": EXCLUDE_FROM_UPLOAD,
                "action": "Do not upload large binaries; keep outside the repository or in an approved artifact store."}
    if suffix in ARCHIVE_BINARY_SUFFIXES:
        cls = EXCLUDE_FROM_UPLOAD if size is None or size > 1048576 else REVIEW
        return {"kind": "binary_artifact", "classification": cls,
                "action": "Do not upload binary/archive artifacts; keep only reproducible build inputs."}
    return None


# ---------------------------------------------------------------------------
# Bounded Git helpers (read-only commands only)
# ---------------------------------------------------------------------------

def _git_env() -> dict:
    env = dict(os.environ)
    env.update(GIT_ENV_OVERRIDES)
    return env


def git_read(root: Path, args: list, max_bytes: int = 4000000, timeout: float = 20.0) -> tuple:
    """Run one allowlisted read-only git command and return (text, truncated)."""
    if not args:
        raise ValueError("empty git command")
    subcommand = args[0]
    if subcommand not in GIT_READONLY_COMMANDS:
        raise ValueError("refusing non read-only git subcommand: " + subcommand)
    cmd = ["git", "-C", str(root)] + list(args)
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=_git_env(), stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return "", False
    chunks = []
    total = 0
    truncated = False
    started = time.monotonic()
    try:
        while True:
            if time.monotonic() - started > timeout:
                proc.kill()
                truncated = True
                break
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            if total + len(chunk) > max_bytes:
                chunks.append(chunk[: max_bytes - total])
                total = max_bytes
                truncated = True
                proc.kill()
                break
            chunks.append(chunk)
            total += len(chunk)
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        try:
            proc.stdout.close()
        except Exception:
            pass
    return b"".join(chunks).decode("utf-8", "replace"), truncated


def _tracked_files(root: Path, deadline: float, bounds: dict) -> tuple:
    out, truncated = git_read(root, ["ls-files", "-z"], max_bytes=max(1000000, bounds["max_total_bytes"] * 2), timeout=20.0)
    tracked = []
    if out:
        for item in out.split(chr(0)):
            if item:
                rel_item = item.replace("\\", "/")
                if rel_item.startswith("./"):
                    rel_item = rel_item[2:]
                tracked.append(rel_item)
    available = bool(tracked) or _git_available(root)
    info = {
        "available": available,
        "head": None,
        "branch": None,
        "tracked_files": len(tracked),
        "commits_scanned": 0,
        "objects_listed": 0,
        "truncated": truncated,
    }
    if available:
        head, _ = git_read(root, ["rev-parse", "HEAD"], max_bytes=4096, timeout=15.0)
        branch, _ = git_read(root, ["rev-parse", "--abbrev-ref", "HEAD"], max_bytes=4096, timeout=15.0)
        info["head"] = head.strip() or None
        info["branch"] = branch.strip() or None
    return tracked, info


def _git_available(root: Path) -> bool:
    text, _ = git_read(root, ["rev-parse", "--is-inside-work-tree"], max_bytes=4096, timeout=10.0)
    return text.strip().lower() == "true"


def _gitignore_patterns(root: Path) -> list:
    path = root / ".gitignore"
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _gitignore_covers(rel: str, patterns: list) -> bool:
    norm = rel.replace(os.sep, "/")
    for pattern in patterns:
        pat = pattern.rstrip("/")
        if pattern.endswith("/"):
            if norm == pat or norm.startswith(pat + "/"):
                return True
            continue
        if "/" not in pat:
            if fnmatch.fnmatch(norm.rsplit("/", 1)[-1], pat):
                return True
            if any(fnmatch.fnmatch(part, pat) for part in norm.split("/")):
                return True
        elif fnmatch.fnmatch(norm, pat.lstrip("/")):
            return True
    return False


# ---------------------------------------------------------------------------
# Findings collector
# ---------------------------------------------------------------------------

class Collector:
    def __init__(self, max_findings: int):
        self.max_findings = max(0, int(max_findings))
        self.items = []
        self.truncated = False
        self.seen = set()
        self.counters = {
            "tracked_total": 0,
            "tracked_scanned": 0,
            "bytes_scanned": 0,
            "binary_skipped": 0,
            "oversize_skipped": 0,
            "files_skipped_due_to_bounds": 0,
            "artifact_paths_tracked": 0,
            "history_secret_lines": 0,
            "history_artifact_paths": 0,
            "present_untracked_roots": 0,
            "secret_matches": 0,
            "review_matches": 0,
        }

    def add(self, *, classification, scope, kind, rule, action, path=None, line=None,
            commit=None, evidence=None, context_redacted=None, git_history_only=False):
        key = (classification, scope, kind, rule, path, line, commit)
        if key in self.seen:
            return None
        if len(self.items) >= self.max_findings:
            self.truncated = True
            return None
        self.seen.add(key)
        item = {
            "id": "",
            "classification": classification,
            "scope": scope,
            "kind": kind,
            "rule": rule,
            "path": path,
            "line": line,
            "commit": commit,
            "git_history_only": bool(git_history_only),
            "evidence": evidence or {},
            "context_redacted": context_redacted,
            "recommended_action": action,
        }
        self.items.append(item)
        return item


def _match_secret_rules(line: str, rel: str, lineno: int, collector: Collector,
                        scope: str, commit=None, history_only=False, entropy_budget=None):
    for rule in SECRET_RULES:
        for match in rule["regex"].finditer(line):
            value = match.group(0)
            if _looks_like_placeholder(value):
                continue
            classification = rule["classification"]
            if _is_fixture_context(rel, line):
                classification = REVIEW
            if _is_allowlisted_test_fixture(rel, value):
                classification = REVIEW
            spans = [match.span(0)]
            collector.add(
                classification=classification, scope=scope, kind=rule["kind"], rule=rule["id"],
                action=_secret_action(rule["id"], classification),
                path=rel, line=lineno, commit=commit,
                evidence={"matched": redact_value(value), "description": rule["description"]},
                context_redacted=redact_line(line, spans),
                git_history_only=history_only,
            )
            collector.counters["secret_matches"] += 1
    for match in GENERIC_SECRET_RE.finditer(line):
        key, value = match.group(1), match.group(2)
        if _looks_like_placeholder(value):
            continue
        low_line = line.lower()
        if any(marker in low_line for marker in ("os.environ", "getenv(", "environ[", "secretref", "kms://", "vault://")):
            continue
        classification = REVIEW
        action = ("Inspect: if this is a real credential, rotate and remove it; if a placeholder, "
                  "confirm it is fake and keep it out of release artifacts.")
        collector.add(
            classification=classification, scope=scope, kind="ambiguous_secret_assignment",
            rule="generic_secret_assignment", action=action,
            path=rel, line=lineno, commit=commit,
            evidence={"field": key.lower(), "value": redact_value(value), "description": "key/value assignment with secret-like name"},
            context_redacted=redact_line(line, [match.span(2)]),
            git_history_only=history_only,
        )
        collector.counters["review_matches"] += 1
    if entropy_budget is None:
        entropy_budget = [0]
    suffix = os.path.splitext(rel)[1].lower()
    heuristic_ok = suffix in (".py", ".pyi", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                              ".env", ".properties", ".sh", ".bash", ".ps1", ".bat",
                              ".js", ".ts", ".jsx", ".tsx", ".xml")
    if heuristic_ok and entropy_budget[0] < 2 and len(line) <= 2000:
        low_line = line.lower()
        if not any(marker in low_line for marker in ("sha256", "sha-256", "checksum", "digest", "fingerprint", "integrity", "hash")):
            for match in list(HIGH_ENTROPY_RE.finditer(line))[:3]:
                value = match.group(1)
                if len(value) < 32 or value.isdigit() or re.fullmatch(r"[0-9a-fA-F]+", value):
                    continue
                if "/" in value or "." in value or "\\" in value:
                    continue
                low_value = value.lower()
                if "abcdefghijklmnopqrstuvwxyz" in low_value or "0123456789" in low_value or "qwerty" in low_value:
                    continue
                classes = (any(c.islower() for c in value), any(c.isupper() for c in value), any(c.isdigit() for c in value))
                if sum(1 for c in classes if c) < 2:
                    continue
                if _entropy(value) < 4.5:
                    continue
                collector.add(
                    classification=REVIEW, scope=scope, kind="high_entropy_string",
                    rule="high_entropy_token", action=(
                        "Inspect this high-entropy string; if it is a credential, rotate it, otherwise "
                        "keep the value out of release artifacts."),
                    path=rel, line=lineno, commit=commit,
                    evidence={"matched": redact_value(value), "entropy": round(_entropy(value), 2)},
                    context_redacted=redact_line(line, [match.span(1)]),
                    git_history_only=history_only,
                )
                entropy_budget[0] += 1


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _scan_personal_and_private(line: str, rel: str, lineno: int, collector: Collector,
                               scope: str, repo_norm: str = "", reported=None):
    reported = reported if reported is not None else set()
    for rule_id, regex in PERSONAL_PATH_RULES:
        if rule_id in reported:
            continue
        match = regex.search(line)
        if not match:
            continue
        value = match.group(0)
        norm_value = value.replace("/", "\\").lower()
        if repo_norm:
            if norm_value.startswith(repo_norm):
                continue
            if repo_norm.startswith(norm_value) and norm_value.startswith("k:"):
                continue
        reported.add(rule_id)
        collector.add(
            classification=REVIEW, scope=scope, kind="personal_absolute_path", rule=rule_id,
            action=("Replace machine/user-specific absolute paths with repository-relative paths; "
                    "never ship personal filesystem paths in release artifacts."),
            path=rel, line=lineno,
            evidence={"matched": redact_personal(value), "length": len(value)},
            context_redacted=redact_line(line, [match.span(0)]),
        )
        break
    for rule_id, regex in PRIVATE_URL_RULES:
        if rule_id in reported:
            continue
        match = regex.search(line)
        if not match:
            continue
        value = match.group(0)
        reported.add(rule_id)
        collector.add(
            classification=REVIEW, scope=scope, kind="private_url", rule=rule_id,
            action=("Confirm this private/loopback URL is an intentional documented default and contains "
                    "no credentials; do not ship internal endpoints in release artifacts."),
            path=rel, line=lineno,
            evidence={"matched": value[:120], "length": len(value)},
            context_redacted=value[:120],
        )
        break


def redact_personal(value: str) -> str:
    lowered = value.lower()
    for marker in ("\\users\\", "/users/", "/home/", "\\ai\\", "/ai/"):
        idx = lowered.find(marker)
        if idx >= 0:
            head = value[: idx + len(marker)]
            tail = value[idx + len(marker):]
            tail = re.sub(r"[^\\/]+", "<redacted>", tail, count=1)
            return (head + tail)[:120]
    return value[:2] + "<redacted>" + value[-2:]


# ---------------------------------------------------------------------------
# Repository scan
# ---------------------------------------------------------------------------

def _deadline_left(deadline: float) -> float:
    return deadline - time.monotonic()


def audit_release(root, bounds=None, use_git=True) -> dict:
    started = time.monotonic()
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("repository root is not a directory: " + str(root))
    merged = dict(DEFAULT_BOUNDS)
    for key, value in (bounds or {}).items():
        if value is not None:
            merged[key] = value
    deadline = started + float(merged["max_seconds"])
    collector = Collector(merged["max_findings"])
    git_info = {"available": False, "head": None, "branch": None, "tracked_files": 0,
                "commits_scanned": 0, "objects_listed": 0, "truncated": False}
    tracked = []
    if use_git:
        tracked, git_info = _tracked_files(root, deadline, merged)
        if not git_info.get("available"):
            tracked = _fallback_walk(root, merged, deadline)
            git_info["tracked_files"] = len(tracked)
            git_info["fallback_scan"] = True
    else:
        tracked = _fallback_walk(root, merged, deadline)
        git_info["fallback_scan"] = True
        git_info["tracked_files"] = len(tracked)

    collector.counters["tracked_total"] = len(tracked)
    tracked_set = set(tracked)
    gitignore = _gitignore_patterns(root)

    _scan_tracked(root, tracked, collector, merged, deadline, gitignore)

    _scan_present_roots(root, tracked_set, collector)

    if use_git and git_info.get("available"):
        _scan_history(root, tracked_set, collector, merged, deadline, git_info, gitignore)
        _scan_git_config(root, collector)

    findings = sorted(
        collector.items,
        key=lambda item: (CLASS_ORDER.get(item["classification"], 9),
                          item["scope"], item["path"] or "", item["line"] or 0,
                          item["rule"]),
    )
    for index, item in enumerate(findings, 1):
        item["id"] = "F" + str(index).zfill(4)

    counts = {ROTATE: 0, EXCLUDE_FROM_UPLOAD: 0, REVIEW: 0, SAFE: 0}
    for item in findings:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    blocking = [
        item for item in findings
        if item["classification"] == ROTATE
        or (item["classification"] == EXCLUDE_FROM_UPLOAD
            and item["scope"] in ("tracked", "history", "git-config"))
    ]

    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": str(root),
        "git": git_info,
        "bounds": {key: merged[key] for key in DEFAULT_BOUNDS},
        "summary": {
            "findings_total": len(findings),
            "classification_counts": counts,
            "blocking_count": len(blocking),
            "upload_gate": "BLOCKED" if blocking else "CLEAR-WITH-REVIEW" if counts.get(REVIEW) else "CLEAR",
            "tracked_total": collector.counters["tracked_total"],
            "tracked_scanned": collector.counters["tracked_scanned"],
            "bytes_scanned": collector.counters["bytes_scanned"],
            "binary_skipped": collector.counters["binary_skipped"],
            "oversize_skipped": collector.counters["oversize_skipped"],
            "files_skipped_due_to_bounds": collector.counters["files_skipped_due_to_bounds"],
            "artifact_paths_tracked": collector.counters["artifact_paths_tracked"],
            "history_secret_lines": collector.counters["history_secret_lines"],
            "history_artifact_paths": collector.counters["history_artifact_paths"],
            "present_untracked_roots": collector.counters["present_untracked_roots"],
            "secret_matches": collector.counters["secret_matches"],
            "review_matches": collector.counters["review_matches"],
            "findings_truncated": collector.truncated,
            "redaction": "sha256[0:12] + <=4-char prefix + length only; no full secret values",
        },
        "redaction_note": REDACTION_NOTE,
        "authorization_note": AUTHORIZATION_NOTE,
        "findings": findings,
        "limitations": [
            "Bounded scan: limits in bounds; truncated flags mean not all content/history was inspected.",
            "Secret detection is pattern/heuristic based; it can miss custom or obfuscated secrets and can flag false positives (REVIEW).",
            "Binary files are not decoded; only path/size/artifact rules apply.",
            "Git history is inspected through added lines of bounded commits; deep history, LFS objects, submodules and encrypted content are not recovered.",
            "No upload/publish action is performed; this report supports the owner decision only.",
        ],
    }
    return report


def _fallback_walk(root: Path, bounds: dict, deadline: float) -> list:
    tracked = []
    skip_dirs = {".git"} | RUNTIME_PARTS | LOCAL_DATA_PARTS | BUILD_OUTPUT_PARTS
    for dirpath, dirnames, filenames in os.walk(root):
        if _deadline_left(deadline) <= 0:
            break
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in skip_dirs and not d.startswith(".git"))
        for filename in sorted(filenames):
            if len(tracked) >= bounds["max_files"]:
                return tracked
            rel = (filename if rel_dir == "." else rel_dir + "/" + filename).replace("\\", "/")
            tracked.append(rel)
    return tracked


def _scan_tracked(root: Path, tracked: list, collector: Collector, bounds: dict,
                  deadline: float, gitignore: list):
    for index, rel in enumerate(tracked):
        if index >= bounds["max_files"]:
            collector.counters["files_skipped_due_to_bounds"] += max(0, len(tracked) - index)
            break
        if _deadline_left(deadline) <= 0:
            collector.counters["files_skipped_due_to_bounds"] += max(0, len(tracked) - index)
            break
        path = root / rel
        try:
            lst = path.lstat()
        except OSError:
            collector.add(
                classification=REVIEW, scope="tracked", kind="unreadable_tracked_path",
                rule="unreadable_path", action="Inspect this tracked path; it could not be read by the audit.",
                path=rel, evidence={"error": "stat failed"},
            )
            continue
        if path.is_symlink():
            collector.add(
                classification=REVIEW, scope="tracked", kind="tracked_symlink",
                rule="tracked_symlink", action="Review this tracked symlink; resolve it and avoid shipping links outside the repository.",
                path=rel, evidence={"size": lst.st_size},
            )
        artifact = classify_artifact_path(rel, size=lst.st_size)
        if artifact:
            collector.counters["artifact_paths_tracked"] += 1
            collector.add(
                classification=artifact["classification"], scope="tracked", kind=artifact["kind"],
                rule="tracked_artifact_path", action=artifact["action"], path=rel,
                evidence={"size": lst.st_size, "gitignore_covered": _gitignore_covers(rel, gitignore)},
            )
        if not path.is_file() or path.is_symlink():
            continue
        size = lst.st_size
        if size > bounds["max_file_bytes"]:
            collector.counters["oversize_skipped"] += 1
            read_size = bounds["max_file_bytes"]
        else:
            read_size = size
        if collector.counters["bytes_scanned"] + read_size > bounds["max_total_bytes"]:
            collector.counters["files_skipped_due_to_bounds"] += max(0, len(tracked) - index)
            break
        try:
            with open(path, "rb") as handle:
                data = handle.read(read_size)
        except OSError:
            collector.add(
                classification=REVIEW, scope="tracked", kind="unreadable_tracked_file",
                rule="unreadable_file", action="Inspect this tracked file; it could not be read by the audit.",
                path=rel, evidence={"error": "read failed"},
            )
            continue
        collector.counters["bytes_scanned"] += len(data)
        collector.counters["tracked_scanned"] += 1
        if b"\x00" in data[:8192]:
            collector.counters["binary_skipped"] += 1
            continue
        if not _is_text_candidate(rel):
            continue
        text = data.decode("utf-8", "replace")
        repo_norm = str(root).replace("/", "\\").lower().rstrip("\\")
        reported_personal = set()
        entropy_budget = [0]
        for lineno, line in enumerate(text.splitlines(), 1):
            if len(line) > 6000:
                line = line[:6000]
            _match_secret_rules(line, rel, lineno, collector, "tracked", entropy_budget=entropy_budget)
            _scan_personal_and_private(line, rel, lineno, collector, "tracked", repo_norm, reported_personal)


def _is_text_candidate(rel: str) -> bool:
    suffix = os.path.splitext(rel)[1].lower()
    if suffix in TEXT_CANDIDATE_SUFFIXES:
        return True
    if not suffix:
        return True
    return False


def _scan_present_roots(root: Path, tracked_set: set, collector: Collector):
    tracked_top = {path.split("/", 1)[0] for path in tracked_set}
    for rel, kind, classification, action in PRESENT_UNTRACKED_ROOTS:
        try:
            exists = (root / rel).exists()
        except OSError:
            exists = False
        if not exists:
            continue
        if rel in tracked_set:
            continue
        if rel.split("/", 1)[0] in tracked_top and rel == rel.split("/", 1)[0]:
            continue
        collector.counters["present_untracked_roots"] += 1
        collector.add(
            classification=classification, scope="present-untracked", kind=kind,
            rule="local_only_tree_present",
            action=action + " Not tracked by Git, so it is out of the source upload; verify packaging excludes it.",
            path=rel, evidence={"exists": True, "tracked": False, "local_only": True},
        )


def _scan_git_config(root: Path, collector: Collector):
    config_path = root / ".git" / "config"
    if not config_path.is_file():
        return
    try:
        text = config_path.read_text(encoding="utf-8", errors="replace")[:65536]
    except OSError:
        return
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("url =") or low.startswith("url="):
            value = stripped.split("=", 1)[1].strip() if "=" in stripped else ""
            if not value:
                continue
            credential_url = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/\s@]+)@", value)
            token_like = any(rule["regex"].search(value) for rule in SECRET_RULES if rule["classification"] == ROTATE)
            if credential_url or token_like:
                collector.add(
                    classification=ROTATE, scope="git-config", kind="git_remote_credentials",
                    rule="git_remote_url_credentials",
                    action="Remote URL embeds credentials/token; rotate it and use a credential helper instead. Do not upload or push.",
                    path=".git/config", line=lineno,
                    evidence={"url": redact_value(value), "credential_userinfo": bool(credential_url)},
                )
        elif low.startswith("extraheader") or "authorization" in low:
            if len(stripped) > 20:
                collector.add(
                    classification=REVIEW, scope="git-config", kind="git_http_extraheader",
                    rule="git_config_authorization_header",
                    action="Git config carries an authorization/extraheader value; verify it is not a live token and remove it from shared tooling.",
                    path=".git/config", line=lineno,
                    evidence={"value": redact_value(stripped), "length": len(stripped)},
                )


def _scan_history(root: Path, tracked_set: set, collector: Collector, bounds: dict,
                  deadline: float, git_info: dict, gitignore: list):
    objects_text, objects_truncated = git_read(
        root, ["rev-list", "--objects", "--all"],
        max_bytes=bounds["max_git_bytes"], timeout=max(1.0, min(bounds["max_git_seconds"], _deadline_left(deadline))),
    )
    git_info["objects_truncated"] = objects_truncated
    seen_paths = set()
    for line in objects_text.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        rel = parts[1].replace("\\", "/").strip()
        if not rel or rel.endswith("/") or rel in seen_paths:
            continue
        seen_paths.add(rel)
        if len(seen_paths) > bounds["max_history_paths"]:
            git_info["objects_truncated"] = True
            break
        base = rel.rsplit("/", 1)[-1]
        if not os.path.splitext(base)[1] and base not in (".env", ".gitignore"):
            continue
        artifact = classify_artifact_path(rel)
        if not artifact or artifact["classification"] != EXCLUDE_FROM_UPLOAD:
            continue
        if rel in tracked_set:
            continue
        collector.counters["history_artifact_paths"] += 1
        collector.add(
            classification=artifact["classification"], scope="history",
            kind=artifact["kind"], rule="history_artifact_path",
            action=("This artifact path exists in Git history. Do not publish this repository/history as-is; "
                    "remove or relocate the path going forward and obtain explicit owner authorization before any history rewrite."),
            path=rel, evidence={"gitignore_covered": _gitignore_covers(rel, gitignore),
                                "present_in_working_tree": (root / rel).exists()},
        )
    git_info["objects_listed"] = len(seen_paths)

    if _deadline_left(deadline) <= 0:
        git_info["truncated"] = True
        return
    diff_text, diff_truncated = git_read(
        root,
        ["log", "--all", "--max-count=" + str(int(bounds["max_git_commits"])), "--no-merges",
         "--no-ext-diff", "--no-color", "--no-renames", "--unified=0", "--format=@@COMMIT %H"],
        max_bytes=bounds["max_git_bytes"],
        timeout=max(1.0, min(bounds["max_git_seconds"], _deadline_left(deadline))),
    )
    git_info["truncated"] = bool(git_info.get("truncated") or diff_truncated)
    commits = set()
    current_commit = None
    current_path = None
    new_line = 0
    aggregated = {}
    for line in diff_text.splitlines():
        if line.startswith("@@COMMIT "):
            current_commit = line.split(" ", 1)[1].strip()
            commits.add(current_commit)
            current_path = None
            continue
        if line.startswith("diff --git "):
            current_path = None
            continue
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                current_path = None
            elif target.startswith("b/"):
                current_path = target[2:]
            continue
        if line.startswith("--- "):
            continue
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            new_line = int(match.group(1)) if match else 0
            continue
        if line.startswith("+") and current_path:
            added = line[1:]
            new_line += 1
            if len(added) > 6000:
                added = added[:6000]
            matches = []
            for rule in SECRET_RULES:
                for match in rule["regex"].finditer(added):
                    value = match.group(0)
                    if _looks_like_placeholder(value):
                        continue
                    classification = rule["classification"]
                    if _is_fixture_context(current_path, added):
                        classification = REVIEW
                    if _is_allowlisted_test_fixture(current_path, value):
                        classification = REVIEW
                    matches.append((rule["id"], rule["kind"], rule["description"], classification, value, match.span(0)))
            for match in GENERIC_SECRET_RE.finditer(added):
                key, value = match.group(1), match.group(2)
                if _looks_like_placeholder(value):
                    continue
                matches.append(("generic_secret_assignment", "ambiguous_secret_assignment",
                                "key/value assignment with secret-like name", REVIEW, value, match.span(2)))
            for rule_id, kind, description, classification, value, span in matches:
                key = (current_path, rule_id)
                entry = aggregated.get(key)
                if entry is None:
                    aggregated[key] = {
                        "rule": rule_id, "kind": kind, "description": description,
                        "classification": classification, "path": current_path,
                        "commits": [current_commit], "line": new_line,
                        "redacted": redact_value(value),
                        "context": redact_line(added, [span]),
                    }
                else:
                    if current_commit not in entry["commits"] and len(entry["commits"]) < 3:
                        entry["commits"].append(current_commit)
    collector.counters["history_secret_lines"] += len(aggregated)
    git_info["commits_scanned"] = len(commits)
    for key in sorted(aggregated, key=lambda item: (item[0], item[1])):
        entry = aggregated[key]
        history_only = entry["path"] not in tracked_set
        collector.add(
            classification=entry["classification"], scope="history", kind=entry["kind"],
            rule="history_" + entry["rule"],
            action=(_secret_action(entry["rule"], entry["classification"])
                    + " This occurrence is in Git history" + (" and no longer tracked." if history_only else ".")),
            path=entry["path"], line=entry["line"], commit=entry["commits"][0],
            evidence={
                "matched": entry["redacted"],
                "description": entry["description"],
                "commits": [c[:12] for c in entry["commits"]],
                "history_only": history_only,
            },
            context_redacted=entry["context"],
            git_history_only=history_only,
        )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _human_bytes(value: int) -> str:
    if value >= 1073741824:
        return str(round(value / 1073741824, 2)) + " GiB"
    if value >= 1048576:
        return str(round(value / 1048576, 2)) + " MiB"
    if value >= 1024:
        return str(round(value / 1024, 1)) + " KiB"
    return str(value) + " B"


def _evidence_text(item: dict) -> str:
    evidence = item.get("evidence") or {}
    matched = evidence.get("matched")
    if isinstance(matched, dict):
        return ("sha256:" + str(matched.get("sha256_12")) + ", prefix:/" + str(matched.get("prefix"))
                + "/, len:" + str(matched.get("length")))
    if "url" in evidence and isinstance(evidence["url"], dict):
        return "url-sha256:" + str(evidence["url"].get("sha256_12")) + ", len:" + str(evidence["url"].get("length"))
    if "value" in evidence and isinstance(evidence["value"], dict):
        return "sha256:" + str(evidence["value"].get("sha256_12")) + ", len:" + str(evidence["value"].get("length"))
    if "value" in evidence and isinstance(evidence["value"], str):
        return evidence["value"][:120]
    if "matched" in evidence and isinstance(evidence["matched"], str):
        return evidence["matched"][:120]
    if "size" in evidence:
        return "size:" + _human_bytes(int(evidence.get("size") or 0)) + ", gitignore_covered=" + str(evidence.get("gitignore_covered"))
    if "exists" in evidence:
        return "exists=" + str(evidence.get("exists")) + ", tracked=" + str(evidence.get("tracked"))
    return ""


def _finding_table(findings: list) -> list:
    lines = []
    lines.append("| ID | Scope | Kind | Rule | Path / line / commit | Redacted evidence | Recommended action |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in findings:
        location = item.get("path") or ""
        if item.get("line"):
            location += ":" + str(item["line"])
        if item.get("commit"):
            location += " @" + str(item["commit"])[:12]
        lines.append("| " + " | ".join([
            str(item.get("id")),
            str(item.get("scope")),
            str(item.get("kind")),
            str(item.get("rule")),
            _escape_table(location),
            _escape_table(_evidence_text(item)),
            _escape_table(str(item.get("recommended_action"))[:220]),
        ]) + " |")
    return lines


def _escape_table(text: str) -> str:
    return (text or "").replace("|", "\\|").replace(NL, " ")[:260]


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = []
    add = lines.append
    add("# Pre-upload secrets and repository audit")
    add("")
    add("Generated by scripts/audit_release_secrets.py v" + report["tool_version"] + " at "
        + report["generated_at"] + " (UTC).")
    add("")
    add("Read-only audit: no deletion, move, rename, commit, push, fetch, tag, release, "
        "visibility change, collaborator invitation, network request or model run. "
        "It writes only this report and the requested JSON report.")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    add("| Repository root | " + _escape_table(report["root"]) + " |")
    git = report["git"]
    add("| Git available | " + str(git.get("available")) + " |")
    add("| Branch / HEAD | " + _escape_table(str(git.get("branch"))) + " / " + _escape_table(str(git.get("head"))) + " |")
    add("| Tracked files | " + str(summary["tracked_total"]) + " (content-scanned: " + str(summary["tracked_scanned"]) + ") |")
    add("| Git history | commits scanned: " + str(git.get("commits_scanned")) + ", object paths listed: " + str(git.get("objects_listed")) + " |")
    add("| Bytes content-scanned | " + _human_bytes(summary["bytes_scanned"]) + " |")
    add("| Findings | " + str(summary["findings_total"]) + " (blocking: " + str(summary["blocking_count"]) + ") |")
    add("| Upload gate | **" + str(summary["upload_gate"]) + "** |")
    add("")
    add("## Decision summary")
    add("")
    add("| Classification | Count | Blocks upload |")
    add("|---|---|---|")
    for classification in (ROTATE, EXCLUDE_FROM_UPLOAD, REVIEW, SAFE):
        add("| " + classification + " | " + str(summary["classification_counts"].get(classification, 0))
            + " | " + ("yes" if classification in BLOCKING_CLASSES else "no") + " |")
    add("")
    add("Blocking findings = ROTATE anywhere, or EXCLUDE-FROM-UPLOAD that is tracked or present in Git history. "
        "Present-but-untracked local-only trees are reported for packaging hygiene but are not part of the "
        "source upload because they are not tracked.")
    add("")
    if summary["blocking_count"]:
        add("**Conclusion / upload gate: NOT CLEAR.** " + str(summary["blocking_count"])
            + " blocking finding(s) must be resolved (rotate secrets and/or remove tracked/history artifact paths) "
            + "before the owner considers any upload. Do not publish or push this repository as-is.")
    else:
        add("**Conclusion / upload gate: CLEAR subject to review and owner authorization.** No ROTATE credential and "
            "no tracked or Git-history upload-exclusion artifact was found in the bounded scan. The "
            + str(summary["classification_counts"].get(REVIEW, 0))
            + " REVIEW item(s) below still require an owner/developer decision, and the local-only trees must stay "
            + "out of any upload or package.")
    add("")
    add("Reproduce (from the repository root; writes only the two report paths):")
    add("")
    add("    python" + chr(92) + "python.exe scripts" + chr(92) + "audit_release_secrets.py --json-out " + WORKSPACE_DIRNAME + "/build/phase6/secrets_audit.json --markdown-out docs/SECRETS_AUDIT.md")
    add("")
    add("" + report["redaction_note"])
    add("")
    add("## Blocking findings")
    add("")
    blocking = [item for item in report["findings"]
                if item["classification"] == ROTATE
                or (item["classification"] == EXCLUDE_FROM_UPLOAD and item["scope"] in ("tracked", "history", "git-config"))]
    if blocking:
        lines.extend(_finding_table(blocking))
    else:
        add("None. No ROTATE credential and no tracked/history upload-exclusion artifact was found.")
    add("")
    add("## Review findings (owner decision required, not auto-blocking)")
    add("")
    review = [item for item in report["findings"] if item["classification"] == REVIEW]
    if review:
        lines.extend(_finding_table(review))
    else:
        add("None.")
    add("")
    add("## Present-but-untracked local-only trees")
    add("")
    present = [item for item in report["findings"] if item["scope"] == "present-untracked"]
    if present:
        lines.extend(_finding_table(present))
    else:
        add("None detected.")
    add("")
    add("## Git history scope")
    add("")
    add("- Commits scanned (bounded): " + str(git.get("commits_scanned")) + ".")
    add("- Object paths listed for historical artifact detection: " + str(git.get("objects_listed")) + ".")
    add("- History truncated: " + str(bool(git.get("truncated") or git.get("objects_truncated"))) + ".")
    add("- History scan inspects added lines only; removed content is still reachable in Git objects and therefore "
        "counts as a history exposure until the owner decides on history cleanup.")
    add("")
    add("## Bounds, truncation and limitations")
    add("")
    bounds = report["bounds"]
    add("- max_files=" + str(bounds["max_files"]) + ", max_file_bytes=" + str(bounds["max_file_bytes"])
        + ", max_total_bytes=" + str(bounds["max_total_bytes"]) + ", max_seconds=" + str(bounds["max_seconds"]))
    add("- max_git_commits=" + str(bounds["max_git_commits"]) + ", max_git_bytes=" + str(bounds["max_git_bytes"])
        + ", max_git_seconds=" + str(bounds["max_git_seconds"]) + ", max_history_paths=" + str(bounds["max_history_paths"]))
    add("- binary_skipped=" + str(summary["binary_skipped"]) + ", oversize_skipped=" + str(summary["oversize_skipped"])
        + ", files_skipped_due_to_bounds=" + str(summary["files_skipped_due_to_bounds"])
        + ", findings_truncated=" + str(summary["findings_truncated"]))
    add("")
    for limitation in report["limitations"]:
        add("- " + limitation)
    add("")
    add("## Recommended owner actions")
    add("")
    add("1. Rotate/revoke every ROTATE credential before any upload; assume a credential in Git history is compromised.")
    add("2. Keep every EXCLUDE-FROM-UPLOAD artifact out of the source upload and beta packages; do not delete user data or evidence.")
    add("3. Review each REVIEW item: confirm fixtures are fake and replace machine-specific paths/URLs with portable references.")
    add("4. If the owner decides to rewrite history for leaked secrets, take a verified backup first and require explicit owner authorization.")
    add("5. Re-run this audit after each fix and attach the JSON+Markdown reports to the release authorization record.")
    add("")
    add("## Owner authorization")
    add("")
    add("" + report["authorization_note"])
    add("")
    return NL.join(lines) + NL


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only, bounded pre-upload secrets/history/repository audit (NL-BP-162).",
        epilog="No deletion, move, rename, commit, push/fetch, visibility change, release upload or network access.",
    )
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", default=str(default_root), help="repository root (default: script parent directory)")
    parser.add_argument("--json-out", default=str(DEFAULT_JSON),
                        help="JSON report path (relative to root; default .workspace/build/phase6/...) or absolute")
    parser.add_argument("--markdown-out", default=str(DEFAULT_MD), help="Markdown report path (relative to root) or absolute")
    parser.add_argument("--no-write", action="store_true", help="do not write report files (stdout summary only)")
    parser.add_argument("--no-git", action="store_true", help="skip Git metadata/history (bounded filesystem walk only)")
    parser.add_argument("--max-files", type=int, default=None, help="maximum tracked files to content-scan")
    parser.add_argument("--max-file-bytes", type=int, default=None, help="maximum bytes read per file")
    parser.add_argument("--max-total-bytes", type=int, default=None, help="maximum total content bytes read")
    parser.add_argument("--max-seconds", type=float, default=None, help="soft wall-clock budget in seconds")
    parser.add_argument("--max-git-commits", type=int, default=None, help="maximum Git commits inspected")
    parser.add_argument("--max-git-bytes", type=int, default=None, help="maximum bytes read from Git history/objects")
    parser.add_argument("--max-git-seconds", type=float, default=None, help="soft Git history time budget")
    parser.add_argument("--max-findings", type=int, default=None, help="maximum recorded findings")
    parser.add_argument("--quiet", action="store_true", help="only print the one-line summary")
    args = parser.parse_args(argv)

    bounds = {}
    for attr, key in (
        ("max_files", "max_files"),
        ("max_file_bytes", "max_file_bytes"),
        ("max_total_bytes", "max_total_bytes"),
        ("max_seconds", "max_seconds"),
        ("max_git_commits", "max_git_commits"),
        ("max_git_bytes", "max_git_bytes"),
        ("max_git_seconds", "max_git_seconds"),
        ("max_findings", "max_findings"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if key in ("max_seconds", "max_git_seconds"):
                bounds[key] = max(0.1, value)
            else:
                bounds[key] = max(0, value)

    root = Path(args.root).resolve()
    try:
        report = audit_release(root, bounds=bounds, use_git=not args.no_git)
    except Exception as exc:  # noqa: BLE001 - CLI reports the failure
        print("release secrets audit failed: " + str(exc), file=sys.stderr)
        return 2

    summary = report["summary"]
    summary_line = ("audit_release_secrets: gate=" + str(summary["upload_gate"])
                    + " findings=" + str(summary["findings_total"])
                    + " blocking=" + str(summary["blocking_count"])
                    + " rotate=" + str(summary["classification_counts"].get(ROTATE, 0))
                    + " exclude=" + str(summary["classification_counts"].get(EXCLUDE_FROM_UPLOAD, 0))
                    + " review=" + str(summary["classification_counts"].get(REVIEW, 0))
                    + " tracked=" + str(summary["tracked_scanned"]) + "/" + str(summary["tracked_total"])
                    + " commits=" + str(report["git"].get("commits_scanned")))
    if not args.no_write:
        json_path = Path(args.json_out)
        markdown_path = Path(args.markdown_out)
        if not json_path.is_absolute():
            json_path = root / json_path
        if not markdown_path.is_absolute():
            markdown_path = root / markdown_path
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + NL, encoding="utf-8")
            markdown_path.write_text(render_markdown(report), encoding="utf-8")
        except OSError as exc:
            print("release secrets audit failed to write reports: " + str(exc), file=sys.stderr)
            return 2
        if not args.quiet:
            summary_line += " | json=" + str(json_path) + " | markdown=" + str(markdown_path)
    print(summary_line)
    return 1 if summary["blocking_count"] else 0


SECRET_RULES = _secret_rules()


if __name__ == "__main__":
    raise SystemExit(main())

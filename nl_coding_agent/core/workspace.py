"""Workspace snapshots and mission-scoped diffs.

The orchestrator must be able to prove that an LLM actually changed files, and
review only the changes produced by a mission.  Relying on ``git diff`` alone is
not enough: the working tree may already contain unrelated user changes.
"""
from __future__ import annotations

import difflib
import fnmatch
import os
from pathlib import Path

IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
    "__pycache__", "node_modules", ".venv", "venv", "env", ".workspace", "dist", "build",
    "target", "bin", "obj", "python", "crewAI", "crewAI-tools", "data",
    "logs", "state",
}

IGNORED_SUFFIXES = {
    ".pyc", ".pyo", ".pyd", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm",
    ".db", ".log", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".pdf", ".zip", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib",
    ".safetensors", ".gguf", ".bin", ".pt", ".pth", ".onnx",
}

MAX_FILE_BYTES = 1_000_000

# ---------------------------------------------------------------------------
# Workspace layout policy (ROOT REORG Phase B)
# ---------------------------------------------------------------------------
# Generated build/dist/logs/temp/cache/state data lives under one configurable
# root: <repository root>/.workspace by default, overridable with
# NL_WORKSPACE_DIR. python/ is the embedded runtime shipped in the payload and
# data/ is live user data (SQLite, backups, recovery, mission baselines): both
# stay at their historical repository-relative paths, which is a hard
# relocation-acceptance dependency.
APP_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_DIRNAME = ".workspace"
WORKSPACE_ENV_VAR = "NL_WORKSPACE_DIR"
WORKSPACE_CHILDREN = ("build", "dist", "logs", "temp", "cache", "state")


def workspace_root() -> Path:
    """Return the root of generated workspace data (default <repo>/.workspace).

    NL_WORKSPACE_DIR overrides the location: absolute paths are used as-is,
    relative paths resolve against the repository root (APP_ROOT).
    """
    override = os.environ.get(WORKSPACE_ENV_VAR, "").strip()
    if not override:
        return (APP_ROOT / WORKSPACE_DIRNAME).resolve()
    candidate = Path(override).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    return candidate.resolve()


def workspace_path(*parts: str, create: bool = False) -> Path:
    """Return a path below workspace_root(); create the directory when asked."""
    path = workspace_root().joinpath(*(str(part) for part in parts))
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def build_root() -> Path:
    """Root for transient build/audit evidence."""
    return workspace_path("build")


def dist_root() -> Path:
    """Root for release candidates and portable payloads."""
    return workspace_path("dist")


def logs_root() -> Path:
    """Root for run logs and diagnostics."""
    return workspace_path("logs")


def temp_root() -> Path:
    """Root for disposable scratch files."""
    return workspace_path("temp")


def cache_root() -> Path:
    """Root for application caches."""
    return workspace_path("cache")


def state_root() -> Path:
    """Root for legacy bootstrap CLI state (audit/spec Markdown files)."""
    return workspace_path("state")


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORED_DIRS and not d.startswith(".")
        ]
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = Path(dirpath) / filename
            if path.suffix.lower() in IGNORED_SUFFIXES:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def snapshot_workspace(project_root: Path | str) -> dict[str, str]:
    """Return {relative_posix_path: text_content} for readable project files."""
    root = Path(project_root).resolve()
    snapshot: dict[str, str] = {}
    for path in _iter_files(root):
        try:
            rel = path.relative_to(root).as_posix()
            snapshot[rel] = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
    return snapshot


def diff_snapshots(
    before: dict[str, str],
    after: dict[str, str],
) -> tuple[str, list[str]]:
    """Build a unified diff between two snapshots and return (diff, changed_paths)."""
    changed = sorted(set(before) | set(after))
    chunks: list[str] = []
    changed_paths: list[str] = []

    for rel in changed:
        old = before.get(rel)
        new = after.get(rel)
        if old == new:
            continue
        changed_paths.append(rel)
        old_lines = (old or "").splitlines(keepends=True)
        new_lines = (new or "").splitlines(keepends=True)
        fromfile = f"a/{rel}" if old is not None else "/dev/null"
        tofile = f"b/{rel}" if new is not None else "/dev/null"
        chunks.extend(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=fromfile,
                tofile=tofile,
                lineterm="\n",
            )
        )

    return "".join(chunks).strip(), changed_paths


def diff_stats(diff_text: str) -> str:
    additions = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))
    files = sum(1 for line in diff_text.splitlines() if line.startswith("diff --git") or line.startswith("--- "))
    return f"{files} file(s), +{additions}/-{deletions}"


def normalize_scope(scope: str) -> str:
    return Path(scope.strip().replace("\\", "/")).as_posix().lstrip("./")


def path_in_scope(rel_path: str, scopes: list[str]) -> bool:
    """Check a changed path against declared write scopes (file, dir/ or glob)."""
    if not scopes:
        return True
    candidate = normalize_scope(rel_path).lower()
    for scope in scopes:
        normalized = normalize_scope(scope).lower()
        if not normalized:
            continue
        if normalized.endswith("/"):
            if candidate.startswith(normalized):
                return True
        elif fnmatch.fnmatch(candidate, normalized):
            return True
        elif candidate == normalized:
            return True
        elif candidate.startswith(normalized + "/"):
            return True
    return False


def out_of_scope_paths(changed_paths: list[str], scopes: list[str]) -> list[str]:
    return [p for p in changed_paths if not path_in_scope(p, scopes)]

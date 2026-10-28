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
    "__pycache__", "node_modules", ".venv", "venv", "env", "dist", "build",
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

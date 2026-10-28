"""Project-scoped filesystem tools with boundary validation and safety checks."""
from __future__ import annotations

import os
from pathlib import Path

PROTECTED_DIRS = {"python", "crewai", "crewai-tools", ".git"}


class FilesystemSecurityError(Exception):
    """Raised when a file operation attempts to violate project boundaries."""
    pass


def resolve_scoped_path(project_root: Path | str, rel_path: str, for_write: bool = False) -> Path:
    """
    Resolve rel_path against project_root and enforce boundary rules:
    1. Must resolve inside project_root.
    2. Must not target protected vendor/system directories if for_write=True.
    """
    root = Path(project_root).resolve()
    target = (root / rel_path).resolve()

    try:
        target.relative_to(root)
    except ValueError:
        raise FilesystemSecurityError(f"Access denied: '{rel_path}' resolves outside project root '{root}'")

    if for_write:
        rel_parts = [p.lower() for p in target.relative_to(root).parts]
        for part in rel_parts:
            if part in PROTECTED_DIRS:
                raise FilesystemSecurityError(f"Write denied: cannot modify protected path component '{part}'")

    return target


def scoped_read_file(project_root: Path | str, rel_path: str, max_chars: int = 100_000) -> str:
    """Read a file safely within project root."""
    target = resolve_scoped_path(project_root, rel_path, for_write=False)
    if not target.exists():
        raise FileNotFoundError(f"File not found: {rel_path}")
    if not target.is_file():
        raise ValueError(f"Not a regular file: {rel_path}")

    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... [Truncated: exceeded {max_chars} chars]"
    return text


def scoped_write_file(project_root: Path | str, rel_path: str, content: str) -> str:
    """Create or overwrite a file safely within project root."""
    target = resolve_scoped_path(project_root, rel_path, for_write=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content)} characters to {rel_path}"


def scoped_patch_file(project_root: Path | str, rel_path: str, target_snippet: str, replacement_snippet: str) -> str:
    """
    Perform an exact snippet replacement in a file safely within project root.
    """
    target = resolve_scoped_path(project_root, rel_path, for_write=True)
    if not target.exists():
        raise FileNotFoundError(f"File not found: {rel_path}")

    content = target.read_text(encoding="utf-8", errors="replace")
    if target_snippet not in content:
        raise ValueError(f"Target snippet not found in {rel_path}")

    occurrences = content.count(target_snippet)
    new_content = content.replace(target_snippet, replacement_snippet)
    target.write_text(new_content, encoding="utf-8")
    return f"Successfully replaced {occurrences} occurrence(s) in {rel_path}"


def scoped_list_dir(project_root: Path | str, rel_path: str = ".") -> list[str]:
    """List directory contents relative to project root."""
    target = resolve_scoped_path(project_root, rel_path, for_write=False)
    if not target.exists() or not target.is_dir():
        raise NotADirectoryError(f"Directory not found: {rel_path}")

    results = []
    for item in sorted(target.iterdir()):
        is_dir = item.is_dir()
        name = item.name + ("/" if is_dir else "")
        results.append(name)
    return results

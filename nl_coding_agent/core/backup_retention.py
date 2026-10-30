"""Bounded retention for automatic configuration/database backups."""
from __future__ import annotations

import os
from pathlib import Path


def keep_limit(default: int = 10) -> int:
    try:
        return max(1, min(int(os.environ.get("NL_BACKUP_KEEP", str(default))), 100))
    except ValueError:
        return default


def prune(directory: Path, prefix: str, *, keep: int | None = None) -> list[Path]:
    """Delete oldest matching backups beyond the retention limit.

    Returns the removed paths. Files are ordered by mtime then name; only the
    exact prefix/suffix pattern used by this application is touched.
    """
    if not directory.is_dir():
        return []
    limit = keep if keep is not None else keep_limit()
    candidates = sorted(
        (path for path in directory.iterdir()
         if path.is_file() and path.name.startswith(prefix) and path.suffix in (".yaml", ".json", ".sqlite3")),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    removed = []
    for path in candidates[:-limit]:
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            pass
    return removed

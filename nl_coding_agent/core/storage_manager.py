"""Read-only storage scan and explicit selective cleanup.

Never deletes source files, the live database, shared model weights, or active
mission staging unless the caller selects a dedicated temporary/build category.
Every deletion requires an explicit preview and confirmation.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

from nl_coding_agent.persistence import database


class StorageError(ValueError):
    pass


#: (category id, relative root, deletable, reason)
_CATEGORIES = (
    ("workspace-build", ".workspace/build", True, "temporary build output"),
    ("workspace-temp", ".workspace/temp", True, "temporary files"),
    ("workspace-cache", ".workspace/cache", True, "regenerated caches"),
    ("workspace-logs", ".workspace/logs", True, "runtime logs"),
    ("data-backups", "data/backups", True, "database/config backups"),
    ("data-recovery", "data/recovery", True, "recovery snapshots"),
)
_NEVER = {
    "data/nl_coding_agent.sqlite3", "data/attachments", "python", "crewAI",
    "crewAI-tools", ".git", "docs", "nl_coding_agent",
}


def _size(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        try:
            return path.stat().st_size, 1
        except OSError:
            return 0, 0
    total = 0
    files = 0
    for candidate in path.rglob("*"):
        if not candidate.is_file():
            continue
        try:
            total += candidate.stat().st_size
            files += 1
        except OSError:
            pass
    return total, files


def _root(project_root: Path | str | None = None) -> Path:
    if project_root:
        return Path(project_root).resolve()
    return Path(__file__).resolve().parents[2]


def scan(project_root: Path | str | None = None, *, data_root: Path | None = None,
         include_missions: bool = True) -> dict:
    root = _root(project_root)
    data = Path(data_root or database.data_root()).resolve()
    items: list[dict] = []
    for category, relative, deletable, reason in _CATEGORIES:
        path = (data / relative[len("data/"):]) if relative.startswith("data/") else root / relative
        if not path.exists():
            continue
        size, files = _size(path)
        items.append({"id": category + ":" + str(path), "category": category,
                      "path": str(path), "bytes": size, "files": files,
                      "deletable": bool(deletable), "reason": reason})
    if include_missions:
        staging = data / "staging"
        if staging.is_dir():
            size, files = _size(staging)
            items.append({"id": "mission-staging:" + str(staging),
                          "category": "mission-staging", "path": str(staging),
                          "bytes": size, "files": files, "deletable": True,
                          "reason": "retained staged candidates; inspect before purge"})
    return {"root": str(root), "data_root": str(data), "items": items,
            "total_bytes": sum(item["bytes"] for item in items),
            "never_delete": sorted(_NEVER)}


def purge(selected_ids: Iterable[str], *, confirm: bool = False,
          project_root: Path | str | None = None) -> dict:
    if not confirm:
        raise StorageError("Explicit confirmation is required for storage cleanup")
    scan_result = scan(project_root)
    by_id = {item["id"]: item for item in scan_result["items"]}
    removed = []
    freed = 0
    for item_id in selected_ids:
        item = by_id.get(str(item_id))
        if not item:
            raise StorageError("Unknown storage item: " + str(item_id))
        if not item.get("deletable"):
            raise StorageError("Storage item is protected: " + str(item["path"]))
        if item["category"] == "mission-staging":
            from nl_coding_agent.persistence.missions import list_missions
            if any(m.get("status") in ("pending", "running") for m in list_missions()):
                raise StorageError("Refusing staging cleanup while a mission is active")
        path = Path(item["path"]).resolve()
        data = Path(scan_result["data_root"]).resolve()
        # Fail closed if a crafted id resolves to a protected path.
        protected = [data / "nl_coding_agent.sqlite3", data / "attachments",
                     Path(scan_result["root"]) / "nl_coding_agent",
                     Path(scan_result["root"]) / "docs"]
        if any(path == candidate or candidate in path.parents for candidate in protected):
            raise StorageError("Refusing protected storage path: " + str(path))
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
        removed.append(path)
        freed += int(item["bytes"])
    return {"ok": True, "removed": [str(path) for path in removed],
            "freed_bytes": freed, "scanned": len(scan_result["items"])}

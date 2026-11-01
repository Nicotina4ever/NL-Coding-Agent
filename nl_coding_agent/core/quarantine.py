"""Safe delete quarantine.

Auto-review and coding agents must not erase project files directly. When a
delete is authorized, move the target into ``<project>/da_eliminare`` with a
timestamped manifest. The operation is reversible by the owner and never
follows symlinks outside the project.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path


class QuarantineError(RuntimeError):
    pass


def _safe_relative(root: Path, target: Path) -> Path:
    try:
        relative = target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise QuarantineError("target escapes the project root") from exc
    if not relative.parts:
        raise QuarantineError("refusing to quarantine the project root")
    return relative


def quarantine_paths(root: str | Path, paths, *, reason: str = "delete") -> dict:
    """Move paths into da_eliminare, preserving unique relative locations."""
    project_root = Path(root).resolve()
    if not project_root.is_dir():
        raise QuarantineError("project root is not a directory")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    label = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(reason))[:60]
    destination_root = project_root / "da_eliminare" / f"{stamp}-{label or 'delete'}"
    moved: list[dict] = []
    skipped: list[dict] = []
    for raw in paths or []:
        target = Path(raw)
        if not target.is_absolute():
            target = project_root / target
        target = target.resolve()
        if target == project_root or project_root not in target.parents:
            skipped.append({"path": str(target), "reason": "outside-project"})
            continue
        if not target.exists() and not target.is_symlink():
            skipped.append({"path": str(target), "reason": "missing"})
            continue
        relative = _safe_relative(project_root, target)
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination = destination.with_name(destination.name + ".duplicate")
        try:
            shutil.move(str(target), str(destination))
        except OSError as exc:
            skipped.append({"path": str(target), "reason": "move-failed:" + str(exc)})
            continue
        moved.append({"from": str(relative), "to": str(destination.relative_to(project_root))})
    if moved:
        manifest = destination_root / "manifest.json"
        manifest.write_text(json.dumps({
            "reason": str(reason), "created_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(project_root), "moved": moved, "skipped": skipped,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": not skipped, "destination": str(destination_root.relative_to(project_root)),
            "moved": moved, "skipped": skipped}


def is_quarantine_path(root: str | Path, path: str | Path) -> bool:
    root_path = Path(root).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = root_path / target
    try:
        return target.resolve().relative_to(root_path / "da_eliminare") is not None
    except ValueError:
        return False

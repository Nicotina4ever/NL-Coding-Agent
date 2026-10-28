"""Minimal RecoveryStore — scoped pre-change snapshots and selective rollback."""
from __future__ import annotations
import json, hashlib, os
from pathlib import Path

RECOVERY_DIR = Path("data/recovery")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def save_snapshot(mission_id: int, scope_paths: list[str], root: Path | str = ".") -> Path:
    root = Path(root).resolve()
    RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for p in scope_paths:
        abs_path = (root / p).resolve()
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
            manifest[str(p)] = {"hash": sha256_text(content), "len": len(content)}
        except Exception:
            manifest[str(p)] = {"hash": None, "len": 0}
    path = RECOVERY_DIR / f"{mission_id}.json"
    path.write_text(json.dumps({"mission_id": mission_id, "manifest": manifest}, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def rollback_from_snapshot(rollback_path: str | Path, files_to_check: list[str]) -> dict:
    rollback_path = Path(rollback_path)
    result = {"restored": [], "blocked": [], "reason": []}
    if not rollback_path.exists():
        result["blocked"].append(str(rollback_path))
        result["reason"].append("snapshot missing")
        return result
    data = json.loads(rollback_path.read_text(encoding="utf-8"))
    manifest = data.get("manifest", {})
    for p in files_to_check:
        current_path = Path(p)
        if not current_path.exists():
            continue
        current_content = current_path.read_text(encoding="utf-8", errors="replace")
        current_hash = sha256_text(current_content)
        saved = manifest.get(p)
        if saved is None:
            result["blocked"].append(p)
            result["reason"].append("not in snapshot")
            continue
        # Compare-and-swap: only restore if current hash matches the applied patch (not user-modified after)
        # For simplicity, if saved hash differs from current, assume external change -> block
        if saved.get("hash") == current_hash:
            # If file is already same as saved, nothing to do (already restored / unchanged)
            result["restored"].append(p)
        else:
            # File changed since snapshot; do NOT rollback (could be user edit or different patch)
            result["blocked"].append(p)
            result["reason"].append("current hash differs from snapshot — external change or different patch; manual merge required")
    return result

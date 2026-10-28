"""Small, scoped recovery points with explicit post-image compare-and-swap.

Never infer the post-image hash from the current file: the current file might be a
human edit.  The caller must provide the hash of the bytes it actually wrote.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


class RecoveryConflict(RuntimeError):
    pass


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _relative(root: Path, path: str) -> tuple[str, Path]:
    if not path or Path(path).is_absolute() or Path(path).drive:
        raise ValueError(f"Expected a project-relative path: {path!r}")
    target = (root / path).resolve()
    try:
        rel = target.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {path!r}") from exc
    if not rel or rel == ".":
        raise ValueError("Cannot snapshot the whole project as a file")
    return rel, target


def _atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.nl-recovery.tmp")
    try:
        with tmp.open("xb") as fh:
            fh.write(contents)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def save_snapshot(
    mission_id: int,
    scope_paths: list[str],
    root: Path | str = ".",
    *,
    recovery_dir: Path | str | None = None,
) -> Path:
    """Capture pre-image bytes of individual files; never copy environments/models.

    Snapshot paths are scoped under the selected root.  Existing symlinks are not
    followed: callers cannot use them to snapshot files outside the project.
    """
    root = Path(root).resolve()
    dest = Path(recovery_dir) if recovery_dir is not None else root / "data" / "recovery"
    dest.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    for path in scope_paths:
        rel, target = _relative(root, path)
        if target.is_symlink() or (root / path).is_symlink():
            raise ValueError(f"Cannot snapshot symlink: {path}")
        if target.exists() and not target.is_file():
            raise ValueError(f"Not a file: {path}")
        pre = target.read_bytes() if target.exists() else None
        if pre is not None and len(pre) > 1_000_000:
            raise ValueError(f"Refusing large recovery point: {path}")
        manifest[rel] = {
            "before_sha256": sha256_bytes(pre) if pre is not None else None,
            "before_hex": pre.hex() if pre is not None else None,
        }
    payload = {"version": 2, "mission_id": mission_id, "root": str(root), "files": manifest}
    path = dest / f"{mission_id}.json"
    if path.exists():
        raise FileExistsError(f"Existing recovery point must not be overwritten: {path}")
    _atomic_write(path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return path


def rollback_from_snapshot(
    rollback_path: str | Path,
    files_to_check: list[str],
    *,
    expected_post_hashes: dict[str, str | None] | None = None,
    project_root: str | Path | None = None,
) -> dict:
    """Restore only if current bytes match the *recorded* agent post-image.

    A hash of None represents an agent-created deletion/nonexistent file.  If no
    post-image is supplied, changed files cannot be safely restored and are
    blocked. No speculative rollback of unrelated human edits is allowed.
    """
    result: dict[str, list[str]] = {"restored": [], "blocked": [], "reason": []}
    try:
        payload = json.loads(Path(rollback_path).read_text(encoding="utf-8"))
        if payload.get("version") != 2:
            raise ValueError("Unsupported recovery format")
    except Exception as exc:
        return {"restored": [], "blocked": [str(rollback_path)], "reason": [str(exc)]}
    root = Path(project_root or payload["root"]).resolve()
    if root != Path(payload["root"]).resolve():
        raise ValueError("Snapshot belongs to a different project root")
    expected_post_hashes = expected_post_hashes or {}
    for request in files_to_check:
        try:
            rel, target = _relative(root, request)
            entry = payload["files"].get(rel)
            if entry is None:
                raise RecoveryConflict("File missing from recovery scope")
            original = bytes.fromhex(entry["before_hex"]) if entry["before_hex"] is not None else None
            if (sha256_bytes(original) if original is not None else None) != entry["before_sha256"]:
                raise RecoveryConflict("Corrupt recovery snapshot")
            current = target.read_bytes() if target.exists() else None
            current_hash = sha256_bytes(current) if current is not None else None
            if current_hash == entry["before_sha256"]:
                result["restored"].append(rel)
                continue
            if rel not in expected_post_hashes or current_hash != expected_post_hashes[rel]:
                raise RecoveryConflict("Current file is not the recorded agent post-image; preserving changes")
            if target.is_symlink() or (root / request).is_symlink():
                raise RecoveryConflict("Refusing rollback through symlink")
            if original is None:
                target.unlink(missing_ok=True)
            else:
                _atomic_write(target, original)
            result["restored"].append(rel)
        except (ValueError, RecoveryConflict, OSError) as exc:
            result["blocked"].append(request)
            result["reason"].append(f"{request}: {exc}")
    return result

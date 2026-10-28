"""Recovery-point retention: read-only audit, verified archive, guarded cleanup.

SPEC-02A sections 5, 6 and 8 (recovery hygiene, retention, compressed archive).
This module never touches the live project tree. It operates only on the
application-owned recovery and verification directories:

* audit_recovery is strictly read-only (stat/read, never mkdir/delete);
* archive_recovery writes a verified .zip (manifest + sha256 + size + timestamp)
  through a temporary file and an atomic replace;
* cleanup_after_archive deletes only regular files that are listed in a verified
  archive manifest, are contained in the recovery directory and still match the
  archived hash. It requires confirm=True and is all-or-nothing: any mismatch or
  unsafe manifest entry refuses the whole cleanup.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ARCHIVE_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
MAX_AUDIT_FILE_BYTES = 10 * 1024 * 1024
_MISSION_FILE_RE = re.compile(r"^mission-(\d+)\.json$")


class RetentionError(RuntimeError):
    """Raised when a retention operation would be unsafe or inconsistent."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _utc_iso(timestamp: float | None = None) -> str:
    moment = (
        datetime.now(timezone.utc)
        if timestamp is None
        else datetime.fromtimestamp(timestamp, timezone.utc)
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _recovery_files(recovery_dir: Path) -> list[Path]:
    """Direct, regular *.json children of the recovery directory (no recursion)."""
    files: list[Path] = []
    for path in sorted(recovery_dir.glob("*.json")):
        if _is_regular_file(path):
            files.append(path)
    return files


def _mission_id_from(name: str, payload: dict | None) -> int | None:
    if isinstance(payload, dict):
        value = payload.get("mission_id")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        try:
            return int(str(value))
        except (TypeError, ValueError):
            pass
    match = _MISSION_FILE_RE.match(name)
    if match:
        return int(match.group(1))
    try:
        return int(Path(name).stem)
    except ValueError:
        return None


def _read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _file_entry(path: Path, recovery_dir: Path) -> dict:
    payload = _read_json(path)
    size = path.stat().st_size
    return {
        "name": path.name,
        "path": str(path),
        "size": size,
        "sha256": _sha256_file(path),
        "created_at": _utc_iso(path.stat().st_mtime),
        "mission_id": _mission_id_from(path.name, payload),
        "format_version": (payload or {}).get("version"),
        "file_count": len((payload or {}).get("files") or {}),
        "valid": payload is not None,
    }


def audit_recovery(
    recovery_dir: Path | str,
    verification_dir: Path | str | None = None,
) -> dict:
    """Read-only audit of recovery points and verification evidence.

    Never creates, modifies or deletes anything; missing directories are reported
    as warnings with an empty inventory.
    """
    recovery = Path(recovery_dir)
    verification = Path(verification_dir) if verification_dir is not None else None
    report: dict = {
        "recovery_dir": str(recovery),
        "verification_dir": str(verification) if verification is not None else None,
        "recovery_files": [],
        "verification_files": [],
        "totals": {
            "recovery_count": 0,
            "recovery_bytes": 0,
            "verification_count": 0,
            "verification_bytes": 0,
        },
        "warnings": [],
    }

    if not recovery.is_dir():
        report["warnings"].append(f"Recovery directory does not exist: {recovery}")
    else:
        for path in _recovery_files(recovery):
            try:
                report["recovery_files"].append(_file_entry(path, recovery))
            except OSError as exc:
                report["warnings"].append(f"Cannot read recovery point {path.name}: {exc}")
        report["totals"]["recovery_count"] = len(report["recovery_files"])
        report["totals"]["recovery_bytes"] = sum(
            entry["size"] for entry in report["recovery_files"]
        )

    if verification is None:
        pass
    elif not verification.is_dir():
        report["warnings"].append(
            f"Verification directory does not exist: {verification}"
        )
    else:
        entries: list[dict] = []
        for path in sorted(verification.glob("*.json")):
            if not _is_regular_file(path):
                continue
            try:
                payload = _read_json(path)
                data = path.read_bytes()
                entries.append({
                    "name": path.name,
                    "path": str(path),
                    "size": len(data),
                    "sha256": _sha256_bytes(data),
                    "created_at": _utc_iso(path.stat().st_mtime),
                    "mission_id": _mission_id_from(path.name, payload),
                    "status": (payload or {}).get("status"),
                    "error": None if payload is not None else "invalid JSON payload",
                })
            except OSError as exc:
                report["warnings"].append(f"Cannot read verification file {path.name}: {exc}")
        report["verification_files"] = entries
        report["totals"]["verification_count"] = len(entries)
        report["totals"]["verification_bytes"] = sum(entry["size"] for entry in entries)

    return report


def _safe_recovery_name(name: object) -> bool:
    if not isinstance(name, str) or not name:
        return False
    if name in (".", "..") or "/" in name or "\\" in name:
        return False
    if Path(name).is_absolute() or Path(name).drive:
        return False
    if Path(name).name != name:
        return False
    return name.lower().endswith(".json")


def _normalize_mission_ids(mission_ids: Iterable[int] | None) -> list[int] | None:
    if mission_ids is None:
        return None
    normalized: list[int] = []
    for value in mission_ids:
        if isinstance(value, bool):
            raise RetentionError(f"Invalid mission id: {value!r}")
        try:
            mission = int(value)
        except (TypeError, ValueError) as exc:
            raise RetentionError(f"Invalid mission id: {value!r}") from exc
        if mission not in normalized:
            normalized.append(mission)
    return sorted(normalized)


def _select_recovery_files(
    recovery_dir: Path,
    mission_ids: list[int] | None,
) -> list[tuple[Path, dict]]:
    selected: list[tuple[Path, dict]] = []
    available: dict[int, Path] = {}
    for path in _recovery_files(recovery_dir):
        payload = _read_json(path) or {}
        mission = _mission_id_from(path.name, payload)
        if mission is not None:
            available.setdefault(mission, path)
        entry = _file_entry(path, recovery_dir)
        if mission_ids is not None and mission not in mission_ids:
            continue
        selected.append((path, entry))
    if mission_ids is not None:
        missing = [mission for mission in mission_ids if mission not in available]
        if missing:
            raise RetentionError(
                "No recovery point for mission id(s): "
                + ", ".join(str(mission) for mission in missing)
            )
    return selected


def _verify_archive(path: Path) -> list[str]:
    """Return a list of problems; an empty list means the archive is fully verified."""
    problems: list[str] = []
    if not Path(path).is_file():
        return [f"Archive does not exist: {path}"]
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            name_set = set(names)
            if len(names) != len(name_set):
                problems.append("Archive contains duplicate entries")
            bad_member = archive.testzip()
            if bad_member:
                problems.append(f"CRC verification failed for {bad_member}")
            if MANIFEST_NAME not in name_set:
                problems.append(f"{MANIFEST_NAME} missing from archive")
                return problems
            try:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            except Exception as exc:
                return problems + [f"Invalid manifest: {exc}"]
            if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
                return problems + ["Manifest has no files list"]
            expected = {MANIFEST_NAME}
            for entry in manifest["files"]:
                if not isinstance(entry, dict) or not _safe_recovery_name(entry.get("name")):
                    problems.append(f"Unsafe manifest entry: {entry!r}")
                    continue
                name = entry["name"]
                expected.add(name)
                if name not in name_set:
                    problems.append(f"Manifest file missing from archive: {name}")
                    continue
                data = archive.read(name)
                if len(data) != entry.get("size"):
                    problems.append(f"Size mismatch for {name}")
                if _sha256_bytes(data) != entry.get("sha256"):
                    problems.append(f"SHA-256 mismatch for {name}")
            extra = name_set - expected
            if extra:
                problems.append("Unexpected archive entries: " + ", ".join(sorted(extra)))
    except (zipfile.BadZipFile, OSError) as exc:
        return [f"Unreadable archive: {exc}"]
    return problems


def _read_manifest_from_archive(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as archive:
        raw = archive.read(MANIFEST_NAME)
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise RetentionError("Archive manifest is malformed")
    return manifest


def archive_recovery(
    recovery_dir: Path | str,
    archive_path: Path | str,
    mission_ids: Iterable[int] | None = None,
) -> dict:
    """Archive selected recovery points into a verified .zip.

    The archive contains the selected recovery JSON files plus manifest.json with
    sha256, size and creation timestamp for every entry. Publication is atomic and
    verified by reading the archive back before returning.
    """
    recovery = Path(recovery_dir).resolve()
    if not recovery.is_dir():
        raise RetentionError(f"Recovery directory does not exist: {recovery}")
    archive = Path(archive_path)
    selected_ids = _normalize_mission_ids(mission_ids)
    selected = _select_recovery_files(recovery, selected_ids)
    if not selected:
        raise RetentionError("No recovery points selected for archiving")

    total_bytes = sum(entry["size"] for _path, entry in selected)
    manifest = {
        "version": ARCHIVE_FORMAT_VERSION,
        "created_at": _utc_iso(),
        "recovery_dir": str(recovery),
        "mission_ids": sorted(
            {
                entry["mission_id"]
                for _path, entry in selected
                if entry["mission_id"] is not None
            }
        ),
        "files": [
            {
                "name": entry["name"],
                "mission_id": entry["mission_id"],
                "size": entry["size"],
                "sha256": entry["sha256"],
                "created_at": entry["created_at"],
            }
            for _path, entry in selected
        ],
        "count": len(selected),
        "total_bytes": total_bytes,
    }

    archive.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = archive.with_name(f".{archive.name}.{os.getpid()}.nl-archive.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                MANIFEST_NAME,
                json.dumps(manifest, indent=2, ensure_ascii=False),
            )
            for path, entry in selected:
                zf.write(path, arcname=entry["name"])
        problems = _verify_archive(tmp_path)
        if problems:
            raise RetentionError(
                "Archive verification failed; nothing was published: "
                + "; ".join(problems)
            )
        os.replace(tmp_path, archive)
    finally:
        tmp_path.unlink(missing_ok=True)

    problems = _verify_archive(archive)
    if problems:
        raise RetentionError(
            "Published archive failed read-back verification: " + "; ".join(problems)
        )

    return {
        "archive": str(archive),
        "count": len(selected),
        "total_bytes": total_bytes,
        "mission_ids": manifest["mission_ids"],
        "manifest": manifest,
        "verified": True,
    }


def _archive_source_files(
    recovery: Path,
    archive: Path,
    manifest: dict,
) -> tuple[list[tuple[Path, dict]], list[str]]:
    """Validate every manifest entry against the recovery directory."""
    problems: list[str] = []
    validated: list[tuple[Path, dict]] = []
    archive_resolved = archive.resolve()
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            problems.append(f"Invalid manifest entry: {entry!r}")
            continue
        name = entry.get("name")
        if not _safe_recovery_name(name):
            problems.append(f"Unsafe manifest entry (outside recovery dir): {name!r}")
            continue
        target = (recovery / name).resolve()
        if target.parent != recovery:
            problems.append(f"Entry escapes recovery directory: {name}")
            continue
        if target == archive_resolved:
            problems.append(f"Manifest entry refers to the archive itself: {name}")
            continue
        if target.is_symlink() or not target.is_file():
            problems.append(f"Archived recovery point is missing or not a regular file: {name}")
            continue
        try:
            size = target.stat().st_size
            digest = _sha256_file(target)
        except OSError as exc:
            problems.append(f"Cannot read recovery point {name}: {exc}")
            continue
        if size != entry.get("size"):
            problems.append(f"Size does not match archive manifest: {name}")
            continue
        if digest != entry.get("sha256"):
            problems.append(f"Content changed since archive; refusing to delete: {name}")
            continue
        validated.append((target, entry))
    return validated, problems


def cleanup_after_archive(
    recovery_dir: Path | str,
    archive_path: Path | str,
    *,
    confirm: bool = False,
) -> dict:
    """Delete recovery points only when a verified archive covers them.

    Safe by construction: requires confirm=True, is all-or-nothing, refuses on any
    hash/size mismatch or path outside the recovery directory, and never touches
    files that are not listed in the archive manifest.
    """
    recovery = Path(recovery_dir).resolve()
    archive = Path(archive_path)
    result: dict = {
        "archive": str(archive),
        "recovery_dir": str(recovery),
        "deleted": [],
        "kept": [],
        "freed_bytes": 0,
        "refused": None,
        "errors": [],
    }

    if not confirm:
        result["refused"] = "confirm=True is required to delete archived recovery points"
        result["kept"] = sorted(path.name for path in _recovery_files(recovery))
        return result
    if not recovery.is_dir():
        result["refused"] = f"Recovery directory does not exist: {recovery}"
        return result
    if not archive.is_file():
        result["refused"] = f"Archive does not exist: {archive}"
        return result

    problems = _verify_archive(archive)
    if problems:
        result["errors"] = problems
        result["refused"] = "Archive failed integrity verification; nothing was deleted"
        result["kept"] = sorted(path.name for path in _recovery_files(recovery))
        return result

    try:
        manifest = _read_manifest_from_archive(archive)
    except (RetentionError, KeyError, OSError, ValueError) as exc:
        result["errors"] = [str(exc)]
        result["refused"] = "Archive manifest cannot be read; nothing was deleted"
        result["kept"] = sorted(path.name for path in _recovery_files(recovery))
        return result

    validated, problems = _archive_source_files(recovery, archive, manifest)
    if problems:
        result["errors"] = problems
        result["refused"] = (
            "Archived recovery points do not match the recovery directory; "
            "nothing was deleted"
        )
        result["kept"] = sorted(path.name for path in _recovery_files(recovery))
        return result

    archived_names = {entry["name"] for _path, entry in validated}
    for path, entry in validated:
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError as exc:
            result["errors"].append(f"Could not delete {path.name}: {exc}")
            continue
        result["deleted"].append(entry["name"])
        result["freed_bytes"] += size

    result["kept"] = sorted(
        path.name
        for path in _recovery_files(recovery)
        if path.name not in archived_names
    )
    if result["errors"]:
        result["refused"] = "Some archived files could not be deleted"
    return result

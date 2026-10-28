"""Stage-2: recovery retention, verified archive and guarded cleanup (SPEC-02A / SH-06)."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from nl_coding_agent.core import retention


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_recovery_point(
    recovery_dir: Path,
    mission_id: int,
    *,
    rel_path: str = "src/app.py",
) -> Path:
    recovery_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "mission_id": mission_id,
        "root": "C:/demo/project",
        "files": {
            rel_path: {"before_sha256": "a" * 64, "before_hex": "00"},
            "tests/test_app.py": {"before_sha256": "b" * 64, "before_hex": "11"},
        },
    }
    path = recovery_dir / (str(mission_id) + ".json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_verification_evidence(
    verification_dir: Path,
    mission_id: int,
    *,
    status: str = "completed",
) -> Path:
    verification_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "mission_id": mission_id,
        "status": status,
        "harness_version": 2,
        "changed_paths": ["src/app.py"],
    }
    path = verification_dir / ("mission-" + str(mission_id) + ".json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def snapshot_tree(root: Path) -> dict:
    """Capture path kind, size, mtime and content hash for every entry."""
    entries: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_dir():
            entries[rel] = ("dir", path.stat().st_mtime_ns)
        else:
            data = path.read_bytes()
            entries[rel] = ("file", path.stat().st_mtime_ns, len(data), sha256_bytes(data))
    return entries


def test_audit_recovery_is_read_only_and_reports_integrity_metadata(tmp_path):
    recovery = tmp_path / "data" / "recovery"
    verification = tmp_path / "data" / "verification"
    write_recovery_point(recovery, 41)
    write_recovery_point(recovery, 42, rel_path="src/other.py")
    write_verification_evidence(verification, 41)
    write_verification_evidence(verification, 42, status="blocked")
    (recovery / "broken.json").write_text("{not json", encoding="utf-8")
    (recovery / "archives").mkdir()
    (recovery / "archives" / "old.zip").write_bytes(b"PK-archive")

    before = snapshot_tree(tmp_path)
    report = retention.audit_recovery(recovery, verification)
    after = snapshot_tree(tmp_path)

    assert after == before, "audit_recovery must not modify anything"
    assert report["totals"]["recovery_count"] == 3
    assert report["totals"]["recovery_bytes"] == sum(
        entry["size"] for entry in report["recovery_files"]
    )
    by_name = {entry["name"]: entry for entry in report["recovery_files"]}
    assert by_name["41.json"]["mission_id"] == 41
    assert by_name["41.json"]["valid"] is True
    assert by_name["41.json"]["file_count"] == 2
    assert by_name["41.json"]["size"] == (recovery / "41.json").stat().st_size
    assert by_name["41.json"]["sha256"] == sha256_bytes((recovery / "41.json").read_bytes())
    assert by_name["41.json"]["created_at"].endswith("Z")
    assert by_name["broken.json"]["valid"] is False
    assert "old.zip" not in by_name

    assert report["totals"]["verification_count"] == 2
    evidence = {entry["name"]: entry for entry in report["verification_files"]}
    assert evidence["mission-41.json"]["mission_id"] == 41
    assert evidence["mission-41.json"]["status"] == "completed"
    assert evidence["mission-42.json"]["status"] == "blocked"
    assert evidence["mission-41.json"]["sha256"] == sha256_bytes(
        (verification / "mission-41.json").read_bytes()
    )


def test_audit_recovery_does_not_create_missing_directories(tmp_path):
    recovery = tmp_path / "missing-recovery"
    verification = tmp_path / "missing-verification"

    report = retention.audit_recovery(recovery, verification)

    assert not recovery.exists()
    assert not verification.exists()
    assert report["totals"]["recovery_count"] == 0
    assert report["totals"]["verification_count"] == 0
    assert len(report["warnings"]) == 2


def test_archive_round_trip_is_verified_with_manifest_hashes(tmp_path):
    recovery = tmp_path / "recovery"
    write_recovery_point(recovery, 41)
    write_recovery_point(recovery, 42)
    archive = tmp_path / "archives" / "recovery-2026.zip"

    result = retention.archive_recovery(recovery, archive)

    assert result["verified"] is True
    assert result["count"] == 2
    assert result["mission_ids"] == [41, 42]
    assert archive.is_file()
    assert not list(archive.parent.glob("*.tmp"))
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["version"] == retention.ARCHIVE_FORMAT_VERSION
        assert manifest["count"] == 2
        assert manifest["mission_ids"] == [41, 42]
        assert {entry["name"] for entry in manifest["files"]} == {"41.json", "42.json"}
        for entry in manifest["files"]:
            data = zf.read(entry["name"])
            assert entry["sha256"] == sha256_bytes(data)
            assert entry["size"] == len(data)
            assert entry["created_at"].endswith("Z")
    # Archiving is additive: the recovery points are still present.
    assert (recovery / "41.json").is_file()
    assert (recovery / "42.json").is_file()


def test_archive_mission_id_filter_and_missing_id(tmp_path):
    recovery = tmp_path / "recovery"
    write_recovery_point(recovery, 41)
    write_recovery_point(recovery, 42)

    result = retention.archive_recovery(
        recovery, tmp_path / "one.zip", mission_ids=[41]
    )

    assert result["mission_ids"] == [41]
    assert [entry["name"] for entry in result["manifest"]["files"]] == ["41.json"]

    with pytest.raises(retention.RetentionError):
        retention.archive_recovery(
            recovery, tmp_path / "missing.zip", mission_ids=[99]
        )
    assert not (tmp_path / "missing.zip").exists()


def test_archive_requires_existing_recovery_points(tmp_path):
    with pytest.raises(retention.RetentionError):
        retention.archive_recovery(tmp_path / "nope", tmp_path / "empty.zip")
    assert not (tmp_path / "empty.zip").exists()


def test_cleanup_requires_confirm_and_keeps_recovery_points(tmp_path):
    recovery = tmp_path / "recovery"
    write_recovery_point(recovery, 41)
    archive = tmp_path / "recovery.zip"
    retention.archive_recovery(recovery, archive)

    result = retention.cleanup_after_archive(recovery, archive)

    assert result["deleted"] == []
    assert "confirm" in (result["refused"] or "").lower()
    assert (recovery / "41.json").is_file()


def test_cleanup_deletes_only_validated_archived_files(tmp_path):
    recovery = tmp_path / "recovery"
    first = write_recovery_point(recovery, 41)
    second = write_recovery_point(recovery, 42)
    archive = tmp_path / "recovery.zip"
    retention.archive_recovery(recovery, archive)
    unarchived = write_recovery_point(recovery, 43)
    archived_bytes = first.stat().st_size + second.stat().st_size

    result = retention.cleanup_after_archive(recovery, archive, confirm=True)

    assert result["deleted"] == ["41.json", "42.json"]
    assert result["kept"] == ["43.json"]
    assert result["refused"] is None
    assert result["freed_bytes"] == archived_bytes
    assert not first.exists()
    assert not second.exists()
    assert unarchived.is_file()
    assert archive.is_file()


def test_cleanup_refuses_all_files_when_one_changed_after_archive(tmp_path):
    recovery = tmp_path / "recovery"
    first = write_recovery_point(recovery, 41)
    second = write_recovery_point(recovery, 42)
    archive = tmp_path / "recovery.zip"
    retention.archive_recovery(recovery, archive)
    first.write_text(json.dumps({"version": 2, "mission_id": 41, "files": {}}), encoding="utf-8")

    result = retention.cleanup_after_archive(recovery, archive, confirm=True)

    assert result["deleted"] == []
    assert "nothing was deleted" in (result["refused"] or "")
    assert any("41.json" in error for error in result["errors"])
    assert first.is_file()
    assert second.is_file()


def test_cleanup_refuses_tampered_archive_and_keeps_recovery_points(tmp_path):
    recovery = tmp_path / "recovery"
    write_recovery_point(recovery, 41)
    archive = tmp_path / "recovery.zip"
    retention.archive_recovery(recovery, archive)
    with zipfile.ZipFile(archive) as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    members["41.json"] = b'{"tampered": true}'
    with zipfile.ZipFile(archive, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)

    result = retention.cleanup_after_archive(recovery, archive, confirm=True)

    assert result["deleted"] == []
    assert "integrity verification" in (result["refused"] or "")
    assert any("SHA-256 mismatch" in error for error in result["errors"])
    assert (recovery / "41.json").is_file()


def test_cleanup_rejects_manifest_entries_outside_recovery_dir(tmp_path):
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"version": 2, "mission_id": 99}), encoding="utf-8")
    archive = tmp_path / "bad.zip"
    manifest = {
        "version": retention.ARCHIVE_FORMAT_VERSION,
        "created_at": "2026-10-28T00:00:00Z",
        "recovery_dir": str(recovery),
        "mission_ids": [99],
        "files": [{
            "name": "../outside.json",
            "mission_id": 99,
            "size": outside.stat().st_size,
            "sha256": sha256_bytes(outside.read_bytes()),
            "created_at": "2026-10-28T00:00:00Z",
        }],
        "count": 1,
        "total_bytes": outside.stat().st_size,
    }
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("../outside.json", outside.read_bytes())

    result = retention.cleanup_after_archive(recovery, archive, confirm=True)

    assert result["deleted"] == []
    assert result["refused"]
    assert any("Unsafe manifest entry" in error for error in result["errors"])
    assert outside.is_file()


def test_cleanup_missing_archive_is_refused_not_raised(tmp_path):
    recovery = tmp_path / "recovery"
    write_recovery_point(recovery, 41)

    result = retention.cleanup_after_archive(
        recovery, tmp_path / "missing.zip", confirm=True
    )

    assert result["deleted"] == []
    assert "does not exist" in (result["refused"] or "")
    assert (recovery / "41.json").is_file()

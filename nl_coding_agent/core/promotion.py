"""Mission-scoped candidate lifecycle: stage -> validate -> verify -> promote.

No live write without a verified candidate, an explicit recovery point and a
journal/compare-and-swap promotion. This module is DB-free and model-free: every
function is deterministic and testable with temporary directories.

The only code path here that writes to the live project is promote(), and it
refuses unless the broker marked the candidate validated and an independent
verifier marked it verified.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from nl_coding_agent.core.recovery_store import (
    _atomic_write,
    rollback_from_snapshot,
    save_snapshot,
    sha256_bytes,
    sha256_text,
)
from nl_coding_agent.core.staging_broker import (
    StagingRejected,
    mark_verified as _broker_mark_verified,
    promote_staged,
    rollback_from_staged,
    stage_candidate,
    validate_candidate,
)
from nl_coding_agent.core.workspace import diff_snapshots, diff_stats, snapshot_workspace

HARNESS_VERSION = 2
PROMOTION_JOURNAL = "promotion-journal.json"
MAX_ROLLBACK_FILE_BYTES = 1_000_000
PROTECTED_DELTA_PREFIXES = (
    "python/", "crewai/", "crewai-tools/", ".git/", "data/", ".workspace/",
    "logs/", "state/", "dist/", "build/", "patch/",
)
PROTECTED_DELTA_FILES = ("sha256_manifest.json", "foundation_changes.patch")
MISSION_INPUT_DENY = ("docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md",)
TERMINAL_MISSION_STATUSES = ("completed", "failed", "blocked", "interrupted")

_STAGE_NAME_RE = re.compile(r"^mission-(\d+)-")


class PromotionError(RuntimeError):
    """Base class for candidate-lifecycle failures."""


class GateFailure(PromotionError):
    def __init__(self, message: str, *, code: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class Stage:
    mission_id: int
    project_root: Path
    stage_dir: Path
    scope: tuple[str, ...]

    @property
    def workspace(self) -> Path:
        return self.stage_dir / "workspace"

    @property
    def manifest_path(self) -> Path:
        return self.stage_dir / "manifest.json"


# ---- loading / creation -------------------------------------------------------

def begin_stage(project_root: Path | str, mission_id: int, scope_paths: list[str]) -> Stage:
    root = Path(project_root).resolve()
    if not scope_paths:
        raise GateFailure(
            "Missing explicit write scope for mission #" + str(mission_id),
            code="scope",
        )
    stage_dir = stage_candidate(root, int(mission_id), list(scope_paths))
    return load_stage(stage_dir)


def load_stage(stage_dir: Path | str) -> Stage:
    stage_dir = Path(stage_dir).resolve()
    manifest_path = stage_dir / "manifest.json"
    if not manifest_path.is_file():
        raise GateFailure("Missing stage manifest: " + str(manifest_path), code="stage-invalid")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GateFailure("Unreadable stage manifest: " + str(exc), code="stage-invalid") from exc
    if manifest.get("version") != 2:
        raise GateFailure(
            "Unsupported stage manifest version: " + repr(manifest.get("version")),
            code="stage-invalid",
        )
    match = _STAGE_NAME_RE.match(stage_dir.name)
    if match is None:
        raise GateFailure("Cannot derive mission id from stage dir " + stage_dir.name, code="stage-invalid")
    return Stage(
        mission_id=int(match.group(1)),
        project_root=Path(manifest["project_root"]).resolve(),
        stage_dir=stage_dir,
        scope=tuple(manifest.get("scope") or ()),
    )


def find_stage(project_root: Path | str, mission_id: int) -> Stage | None:
    root = Path(project_root).resolve()
    basedir = root / "data" / "staging"
    matches = sorted(basedir.glob("mission-" + str(int(mission_id)) + "-*")) if basedir.is_dir() else []
    matches = [m for m in matches if m.is_dir()]
    if not matches:
        return None
    if len(matches) > 1:
        raise GateFailure(
            "Ambiguous staging dirs for mission #" + str(mission_id) + ": "
            + repr([m.name for m in matches]),
            code="stage-ambiguous",
        )
    return load_stage(matches[0])


def canonical_scope_paths(project_root: Path | str, paths: list[str]) -> list[str]:
    """Convert project-owned absolute paths to relative scope; root is context."""
    root = Path(project_root).resolve()
    result = []
    for value in paths:
        raw = str(value).replace("\\", "/").strip()
        target = (root / raw).resolve()
        try:
            relative = target.relative_to(root).as_posix()
        except ValueError as exc:
            raise GateFailure("Path is outside the project: " + raw, code="scope") from exc
        if relative != "." and relative not in result:
            result.append(relative)
    return result


def derive_scope(project_root: Path | str, write_paths: list[str]) -> list[str]:
    root = Path(project_root).resolve()
    write_paths = canonical_scope_paths(root, write_paths)
    if write_paths:
        return list(write_paths)
    snapshot = snapshot_workspace(root)
    top: set[str] = set()
    for rel in snapshot:
        head = rel.split("/", 1)[0]
        if not head or head.startswith("."):
            continue
        lowered = (head + "/").lower()
        if any(lowered.startswith(prefix) for prefix in PROTECTED_DELTA_PREFIXES):
            continue
        top.add(head)
    if not top:
        raise GateFailure("Cannot derive a write scope from the project", code="scope-missing")
    return sorted(top)


def read_manifest(stage: Stage) -> dict:
    return json.loads(stage.manifest_path.read_text(encoding="utf-8"))


def _save_manifest(stage: Stage, manifest: dict) -> None:
    _atomic_write(stage.manifest_path, json.dumps(manifest, ensure_ascii=False).encode("utf-8"))


# ---- staged delta / policy ----------------------------------------------------

def candidate_snapshot(stage: Stage) -> dict[str, str]:
    return snapshot_workspace(stage.workspace)


def candidate_delta(
    stage: Stage,
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, str | None]]]:
    manifest = read_manifest(stage)
    baseline = dict(manifest.get("baseline") or {})
    staged = candidate_snapshot(stage)
    _, changed = diff_snapshots(baseline, staged)
    hashes: dict[str, dict[str, str | None]] = {}
    for rel in changed:
        hashes[rel] = {
            "before": sha256_text(baseline[rel]) if rel in baseline else None,
            "after": sha256_text(staged[rel]) if rel in staged else None,
        }
    return baseline, staged, hashes


def candidate_diff(stage: Stage) -> tuple[str, list[str], str]:
    baseline = dict(read_manifest(stage).get("baseline") or {})
    staged = candidate_snapshot(stage)
    diff, changed = diff_snapshots(baseline, staged)
    return diff, changed, diff_stats(diff)


def normalize_staged_newlines(stage: Stage) -> list[str]:
    changed: list[str] = []
    workspace = stage.workspace.resolve()
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\r\n" not in data:
            continue
        path.write_bytes(data.replace(b"\r\n", b"\n"))
        changed.append(path.relative_to(workspace).as_posix())
    return changed


def check_delta_policy(stage: Stage, *, deny_paths: list[str] = ()) -> list[str]:
    manifest = read_manifest(stage)
    changed = (manifest.get("changed") or {})
    if not changed:
        return ["No staged changes recorded in the manifest"]
    errors: list[str] = []
    deny_lower = [str(p).lower().replace("\\", "/") for p in deny_paths]
    for rel in changed:
        lowered = str(rel).lower().replace("\\", "/")
        if "\\" in str(rel) or Path(str(rel)).is_absolute():
            errors.append("Invalid staged path (absolute/backslash): " + str(rel))
            continue
        if any(lowered.startswith(prefix) for prefix in PROTECTED_DELTA_PREFIXES):
            errors.append("Protected path changed: " + str(rel))
        if lowered in PROTECTED_DELTA_FILES:
            errors.append("Protected file changed: " + str(rel))
        for deny in deny_lower:
            if lowered == deny or lowered.startswith(deny.rstrip("/") + "/"):
                errors.append("Mission input changed: " + str(rel))
    return errors


def validate(stage: Stage, *, deny_paths: list[str] = ()) -> dict:
    verdict = validate_candidate(stage.stage_dir, scope_paths=list(stage.scope))
    extra = check_delta_policy(stage, deny_paths=deny_paths)
    if extra:
        verdict = dict(verdict)
        verdict["valid"] = False
        verdict["errors"] = list(verdict.get("errors") or []) + extra
        manifest = read_manifest(stage)
        manifest["validated"] = False
        manifest["verified"] = False
        _save_manifest(stage, manifest)
    return verdict


def assert_byte_hash_invariant(stage: Stage) -> None:
    manifest = read_manifest(stage)
    changed = manifest.get("changed") or {}
    if not changed:
        raise GateFailure("No changed files to promote", code="no-changes")
    workspace = stage.workspace
    for rel, hashes in changed.items():
        path = (workspace / rel)
        if path.is_symlink() or not path.is_file():
            raise GateFailure("Staged file missing: " + str(rel), code="byte-invariant")
        actual = sha256_bytes(path.read_bytes())
        expected = sha256_text(path.read_text(encoding="utf-8"))
        if not (actual == expected == hashes.get("after")):
            raise GateFailure(
                "Byte/text hash invariant violated for " + str(rel),
                code="byte-invariant",
                details={"actual": actual, "expected": expected, "manifest": hashes.get("after")},
            )


# ---- live-tree safety ---------------------------------------------------------

def check_live_drift(stage: Stage) -> list[str]:
    manifest = read_manifest(stage)
    drifted: list[str] = []
    for rel, hashes in (manifest.get("changed") or {}).items():
        live = stage.project_root / rel
        current = sha256_text(live.read_text(encoding="utf-8", errors="replace")) if live.exists() else None
        if current != hashes.get("before"):
            drifted.append(str(rel))
    return drifted


def _recovery_path(stage: Stage, recovery_dir: Path | str | None) -> Path:
    if recovery_dir is None:
        return stage.project_root / "data" / "recovery" / (str(stage.mission_id) + ".json")
    return Path(recovery_dir) / (str(stage.mission_id) + ".json")


def ensure_recovery_point(stage: Stage, recovery_dir: Path | str | None = None) -> Path:
    path = _recovery_path(stage, recovery_dir)
    manifest = read_manifest(stage)
    changed = sorted((manifest.get("changed") or {}).keys())
    if not changed:
        raise GateFailure("No changed files for recovery point", code="no-changes")
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise GateFailure("Unreadable recovery point: " + str(exc), code="recovery-conflict") from exc
        if payload.get("version") != 2 or Path(payload.get("root", "")).resolve() != stage.project_root:
            raise GateFailure("Existing recovery point does not match this project", code="recovery-conflict")
        files = payload.get("files") or {}
        for rel in changed:
            entry = files.get(rel)
            if entry is None:
                raise GateFailure("Recovery point misses changed file: " + rel, code="recovery-conflict")
            live = stage.project_root / rel
            expected = sha256_bytes(live.read_bytes()) if live.exists() else None
            if entry.get("before_sha256") != expected:
                raise GateFailure(
                    "Recovery point conflicts with current live file: " + rel,
                    code="recovery-conflict",
                )
        return path
    return save_snapshot(
        int(stage.mission_id),
        changed,
        root=stage.project_root,
        recovery_dir=recovery_dir,
    )


def invalidate_validation(stage: Stage, reason: str = "") -> dict:
    """Reopen the gate after a post-validation hook rejects the candidate."""
    manifest = read_manifest(stage)
    if manifest.get("validated") or manifest.get("verified"):
        manifest["validated"] = False
        manifest["verified"] = False
        if reason:
            manifest["validation_error"] = str(reason)[:1000]
        _save_manifest(stage, manifest)
    return manifest


def mark_verified(stage: Stage, *, passed: bool, evidence: str) -> None:
    _broker_mark_verified(stage.stage_dir, passed=passed, evidence=evidence)


def is_live_promoted(stage: Stage) -> bool:
    manifest = read_manifest(stage)
    changed = manifest.get("changed") or {}
    if not changed:
        return False
    for rel, hashes in changed.items():
        live = stage.project_root / rel
        if not live.is_file():
            return False
        if sha256_text(live.read_text(encoding="utf-8", errors="replace")) != hashes.get("after"):
            return False
    return True


def promote(stage: Stage, *, recovery_dir: Path | str | None = None) -> dict:
    manifest = read_manifest(stage)
    if not (manifest.get("validated") and manifest.get("verified")):
        raise GateFailure(
            "Candidate is not validated and independently verified; promotion denied",
            code="not-verified",
        )
    assert_byte_hash_invariant(stage)
    if is_live_promoted(stage):
        changed = sorted((manifest.get("changed") or {}).keys())
        return {"promoted": changed, "blocked": [], "reason": [], "already": True}
    drift = check_live_drift(stage)
    if drift:
        raise GateFailure(
            "Live files changed after staging; CAS promotion denied",
            code="cas-conflict",
            details={"drifted": drift},
        )
    recovery_path = ensure_recovery_point(stage, recovery_dir)
    try:
        result = promote_staged(stage.stage_dir, stage.project_root)
    except StagingRejected as exc:
        outcome = reconcile(stage, recovery_dir=recovery_dir)
        raise GateFailure(
            "Promotion conflict: " + str(exc),
            code="promotion-conflict",
            details={"reconcile": outcome},
        ) from exc
    result = dict(result)
    result["recovery_path"] = str(recovery_path)
    result["hashes"] = {
        rel: hashes.get("after") for rel, hashes in (manifest.get("changed") or {}).items()
    }
    return result


def reconcile(stage: Stage, *, recovery_dir: Path | str | None = None) -> dict:
    manifest = read_manifest(stage)
    changed = manifest.get("changed") or {}
    journal = stage.stage_dir / PROMOTION_JOURNAL
    if not journal.exists():
        if is_live_promoted(stage):
            return {"state": "promotion-complete", "journal": False}
        return {"state": "no-journal", "journal": False}
    try:
        journal_payload = json.loads(journal.read_text(encoding="utf-8"))
        journal_changed = journal_payload.get("changed") or {}
    except Exception:
        return {"state": "conflict", "journal": True, "reason": "unreadable journal"}
    if not journal_changed:
        journal_changed = changed

    states: dict[str, str] = {}
    reasons: list[str] = []
    for rel, hashes in journal_changed.items():
        live = stage.project_root / rel
        current = sha256_text(live.read_text(encoding="utf-8", errors="replace")) if live.exists() else None
        if current == hashes.get("after"):
            states[rel] = "after"
        elif current == hashes.get("before"):
            states[rel] = "before"
        else:
            states[rel] = "conflict"
            reasons.append("Concurrent edit preserved: " + str(rel))

    if all(state == "after" for state in states.values()):
        journal.unlink(missing_ok=True)
        return {"state": "promotion-complete", "journal": False, "files": sorted(states)}
    if all(state == "before" for state in states.values()):
        journal.unlink(missing_ok=True)
        return {"state": "never-promoted", "journal": False}
    if "conflict" in states.values():
        return {"state": "conflict", "journal": True, "blocked": reasons, "states": states}

    recovery_path = _recovery_path(stage, recovery_dir)
    if not recovery_path.exists():
        return {"state": "conflict", "journal": True, "blocked": ["missing recovery point"], "states": states}
    after_files = [rel for rel, state in states.items() if state == "after"]
    expected = {
        rel: sha256_bytes((stage.workspace / rel).read_bytes()) for rel in after_files
    }
    rollback = rollback_from_snapshot(
        recovery_path,
        after_files,
        expected_post_hashes=expected,
        project_root=stage.project_root,
    )
    recheck: dict[str, str] = {}
    for rel in after_files:
        live = stage.project_root / rel
        current = sha256_text(live.read_text(encoding="utf-8", errors="replace")) if live.exists() else None
        recheck[rel] = "before" if current == journal_changed[rel].get("before") else "other"
    if all(state == "before" for state in recheck.values()):
        journal.unlink(missing_ok=True)
        return {"state": "rolled-back", "restored": after_files, "rollback": rollback}
    return {
        "state": "conflict",
        "journal": True,
        "blocked": list(rollback.get("blocked") or []),
        "states": states,
    }


def rollback(stage: Stage, *, recovery_dir: Path | str | None = None) -> dict:
    manifest = read_manifest(stage)
    changed = manifest.get("changed") or {}
    recovery_path = _recovery_path(stage, recovery_dir)
    if recovery_path.exists():
        expected = {rel: hashes.get("after") for rel, hashes in changed.items()}
        return rollback_from_snapshot(
            recovery_path,
            sorted(changed),
            expected_post_hashes=expected,
            project_root=stage.project_root,
        )
    if (stage.stage_dir / PROMOTION_JOURNAL).exists():
        return rollback_from_staged(stage.stage_dir, stage.project_root)
    raise GateFailure("No recovery point or journal available for rollback", code="no-recovery-point")


# ---- evidence / cleanup -------------------------------------------------------

def evidence_payload(
    stage: Stage,
    *,
    status: str,
    verification: dict | None = None,
    extra: dict | None = None,
) -> dict:
    diff, changed, stat = candidate_diff(stage)
    payload = {
        "harness_version": HARNESS_VERSION,
        "mission_id": stage.mission_id,
        "project_root": str(stage.project_root),
        "stage_dir": str(stage.stage_dir),
        "status": status,
        "changed_paths": changed,
        "diff_stat": stat,
        "diff": diff,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if verification is not None:
        payload["verification"] = verification
    if extra:
        payload.update(extra)
    return payload


def retain_evidence(evidence_dir: Path | str, payload: dict) -> Path:
    dest = Path(evidence_dir)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / ("mission-" + str(payload.get("mission_id", "unknown")) + ".json")
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    return path


def discard_stage(stage: Stage) -> None:
    if (stage.stage_dir / PROMOTION_JOURNAL).exists():
        raise GateFailure("Refusing to discard a stage with a promotion journal", code="journal-present")
    shutil.rmtree(stage.stage_dir, ignore_errors=False)


def cleanup_after_terminal(
    stage: Stage,
    *,
    mission_status: str,
    evidence_dir: Path | str | None = None,
    verification: dict | None = None,
) -> None:
    if evidence_dir is None:
        from nl_coding_agent.persistence.database import db_path

        evidence_dir = db_path().parent / "verification"
    retain_evidence(
        evidence_dir,
        evidence_payload(stage, status=mission_status, verification=verification),
    )
    if mission_status in TERMINAL_MISSION_STATUSES and not (stage.stage_dir / PROMOTION_JOURNAL).exists():
        discard_stage(stage)


def sweep_stale_stages(
    project_root: Path | str,
    *,
    mission_lookup: Callable[[str], dict | None],
    retention_days: int = 7,
    now: float | None = None,
) -> list[str]:
    import time

    root = Path(project_root).resolve()
    basedir = root / "data" / "staging"
    if not basedir.is_dir():
        return []
    reference = time.time() if now is None else now
    removed: list[str] = []
    for manifest_path in sorted(basedir.glob("*/manifest.json")):
        stage_dir = manifest_path.parent
        if (stage_dir / PROMOTION_JOURNAL).exists():
            continue
        try:
            stage = load_stage(stage_dir)
        except GateFailure:
            continue
        mission = mission_lookup(str(stage_dir))
        status = str((mission or {}).get("status") or "")
        if mission is not None and status not in TERMINAL_MISSION_STATUSES:
            continue
        try:
            age_days = (reference - manifest_path.stat().st_mtime) / 86400.0
        except OSError:
            continue
        if age_days < retention_days:
            continue
        shutil.rmtree(stage_dir, ignore_errors=True)
        removed.append(str(stage_dir))
    return removed


def preflight(project_root: Path | str, *, mission_lookup: Callable[[str], dict | None]) -> list[str]:
    root = Path(project_root).resolve()
    basedir = root / "data" / "staging"
    if not basedir.is_dir():
        return []
    messages: list[str] = []
    for journal in sorted(basedir.glob("*/" + PROMOTION_JOURNAL)):
        stage_dir = journal.parent
        mission = mission_lookup(str(stage_dir))
        match = _STAGE_NAME_RE.match(stage_dir.name)
        mission_id = match.group(1) if match else "?"
        if mission is None:
            messages.append(
                "Promotion journal present for unknown mission " + str(mission_id)
                + " in " + str(stage_dir) + "; reconcile before starting a new mission."
            )
            continue
        status = str(mission.get("status") or "")
        if status in TERMINAL_MISSION_STATUSES:
            messages.append(
                "Promotion journal present for terminal mission #" + str(mission_id)
                + " (" + status + "); reconcile before starting a new mission."
            )
        else:
            messages.append(
                "Mission #" + str(mission_id) + " has an unreconciled promotion journal; resume it before starting new work."
            )
    return messages

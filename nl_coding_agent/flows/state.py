"""C4b Flow state: MissionState(FlowState) + deterministic phase derivation.

The CrewAI flow state is a small, reference-only snapshot; authoritative mission
facts stay in SQLite (missions, tasks, verification_runs, handoffs, promotion
journal). derive_phase() accepts a MissionFacts snapshot and lets durable facts
win over stale flow state, returning a conflict decision instead of guessing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from crewai.flow.flow import FlowState
from pydantic import ConfigDict, Field, field_validator, model_validator

SUPPORTED_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 256 * 1024
PHASES: tuple[str, ...] = (
    "planned", "developing", "verifying", "repairing", "reviewing",
    "promoting", "waiting_approval", "completed", "blocked", "interrupted",
)
TERMINAL_PHASES: tuple[str, ...] = ("completed", "blocked", "interrupted")
_PROMOTED_STATUSES = frozenset({"promoted", "live_promoted", "promoted_live"})
_PROMOTING_STATUSES = frozenset({
    "promoting", "journal_pending", "pending_journal", "mixed", "reconciling",
})
_DEVELOPER_DONE_STATES = frozenset({"completed", "done", "skipped"})
_MISSION_TERMINAL = frozenset({"completed", "blocked", "failed", "interrupted"})


class StateValidationError(ValueError):
    """The flow state is invalid or contradicts durable facts."""


class UnsupportedStateSchemaError(StateValidationError):
    """The persisted state was written by a newer schema version (fail closed)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_state_json(state_data: dict) -> str:
    """Canonical JSON used for the size guard and state_sha256."""
    return json.dumps(
        state_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    )


def state_sha256(state_data: dict) -> str:
    return hashlib.sha256(canonical_state_json(state_data).encode("utf-8")).hexdigest()


class MissionState(FlowState):
    """Reference state for one mission flow (max 256 KiB, versioned, additive)."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = SUPPORTED_SCHEMA_VERSION
    project_id: int = 0
    mission_id: int = 0
    queue_id: int | None = None
    supervisor_run_id: int | None = None
    requirement_id: str | None = None
    goal: str = ""
    write_scope: list[str] = Field(default_factory=list)
    phase: str = "planned"
    attempt: int = 0
    repair_round: int = 0
    max_repairs: int = 2
    stage_dir: str | None = None
    baseline_sha256: str | None = None
    changed_paths: list[str] = Field(default_factory=list)
    diff_stat: str | None = None
    promotion_status: str | None = None
    verification_ref: str | None = None
    review_verdict: str | None = None
    review_ref: str | None = None
    last_error: str | None = None
    error_code: str | None = None
    failure_stage: str | None = None
    error_traceback: str | None = None
    exception_type: str | None = None
    approval_id: int | None = None
    approval_action: str | None = None
    model_bindings: list[dict] = Field(default_factory=list)
    config_sha256: str | None = None
    idempotency_key: str | None = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    @field_validator("phase")
    @classmethod
    def _validate_phase(cls, value: str) -> str:
        text = str(value or "").strip()
        if text not in PHASES:
            raise ValueError("Invalid flow phase: " + repr(value))
        return text

    @field_validator("schema_version")
    @classmethod
    def _validate_schema(cls, value: int) -> int:
        if int(value) > SUPPORTED_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported state schema_version " + str(value)
                + " (supported <= " + str(SUPPORTED_SCHEMA_VERSION) + ")"
            )
        if int(value) < 1:
            raise ValueError("schema_version must be >= 1")
        return int(value)

    @field_validator("attempt", "repair_round", "max_repairs")
    @classmethod
    def _validate_counters(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("Flow counters must be non-negative")
        return int(value)

    @field_validator("write_scope", "changed_paths")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        return [str(item) for item in (value or [])]

    @model_validator(mode="after")
    def _validate_bounds(self):
        if self.repair_round > self.max_repairs:
            raise ValueError("repair_round exceeds max_repairs")
        self.assert_size()
        return self

    @property
    def flow_id(self) -> str:
        return str(self.id)

    def as_durable_dict(self) -> dict:
        return self.model_dump(mode="json")

    def assert_size(self) -> int:
        size = len(canonical_state_json(self.as_durable_dict()).encode("utf-8"))
        if size > MAX_STATE_BYTES:
            raise StateValidationError(
                "Flow state is " + str(size) + " bytes; limit is "
                + str(MAX_STATE_BYTES)
            )
        return size

    def with_updates(self, **updates) -> "MissionState":
        updates.setdefault("updated_at", _now_iso())
        return self.model_copy(update=updates)


# --------------------------------------------------------------------------- #
# Durable facts and phase derivation
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MissionFacts:
    """Authoritative durable facts read from SQLite (never from model output)."""

    mission_id: int | None = None
    project_id: int | None = None
    mission_status: str | None = None
    developer_status: str | None = None
    verification_persisted: bool = False
    candidate_passed: bool | None = None
    oracle_passed: bool | None = None
    review_verdict: str | None = None
    promotion_status: str | None = None
    promotion_reconciled: bool = False
    live_promoted: bool = False
    repair_round: int = 0
    max_repairs: int = 2
    approval_pending: bool = False
    interrupted: bool = False
    last_error: str | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict) -> "MissionFacts":
        if not isinstance(data, dict):
            raise StateValidationError("MissionFacts mapping must be a dict")
        allowed = {name for name in cls.__dataclass_fields__ if name != "extra"}
        values = {name: data[name] for name in allowed if name in data}
        extra = {key: value for key, value in data.items() if key not in allowed}
        return cls(**values, extra=extra)

    @classmethod
    def from_durable(cls, mission_id: int) -> "MissionFacts":
        """Build facts from existing durable tables (read-only)."""
        from nl_coding_agent.persistence import missions

        mission = missions.get_mission(int(mission_id))
        if mission is None:
            raise StateValidationError("Mission not found: " + str(mission_id))
        tasks = missions.get_tasks(int(mission_id))
        runs = missions.get_verification_runs(int(mission_id))
        handoffs = missions.get_handoffs(int(mission_id))
        developer = next(
            (task for task in tasks if str(task.get("agent_role") or "") == "developer"),
            None,
        )
        developer_tasks = [task for task in tasks if task.get("agent_role") == "developer"]
        if developer_tasks and any(task.get("status") not in _DEVELOPER_DONE_STATES for task in developer_tasks):
            developer = next(task for task in developer_tasks if task.get("status") not in _DEVELOPER_DONE_STATES)
        tester = next((task for task in tasks if task.get("agent_role") == "tester"), None)
        reviewer = next((task for task in tasks if task.get("agent_role") == "reviewer"), None)
        candidate_runs = [r for r in runs if str(r.get("command") or "").startswith("verify:candidate")]
        oracle_runs = [r for r in runs if str(r.get("command") or "").startswith("verify:oracle")]
        review = next(
            (h for h in reversed(handoffs) if str(h.get("from_role") or "") == "reviewer"),
            None,
        )
        verdict = None
        if review is not None and (reviewer is None or reviewer.get("status") == "completed"):
            verdict = (review.get("payload") or {}).get("verdict")
        if verdict is None and (reviewer is None or reviewer.get("status") == "completed"):
            verdict = mission.get("review_verdict")
        promotion_status = mission.get("promotion_status")
        return cls(
            mission_id=int(mission_id),
            project_id=mission.get("project_id"),
            mission_status=str(mission.get("status") or "") or None,
            developer_status=(
                str(developer.get("status")) if developer else None
            ),
            verification_persisted=bool(candidate_runs or oracle_runs) and (not developer_tasks or all(task.get("status") in _DEVELOPER_DONE_STATES for task in developer_tasks)) and (tester is None or tester.get("status") != "pending"),
            candidate_passed=(
                bool(candidate_runs[-1].get("passed")) if candidate_runs else None
            ),
            oracle_passed=(
                bool(oracle_runs[-1].get("passed")) if oracle_runs else None
            ),
            review_verdict=str(verdict).strip().upper() if verdict else None,
            promotion_status=str(promotion_status) if promotion_status else None,
            promotion_reconciled=str(promotion_status or "") in _PROMOTED_STATUSES,
            live_promoted=str(promotion_status or "") in _PROMOTED_STATUSES,
            last_error=mission.get("result_summary"),
        )


@dataclass(frozen=True)
class PhaseDecision:
    phase: str
    reason: str
    conflicts: tuple[str, ...] = ()

    @property
    def reconciled(self) -> bool:
        return bool(self.conflicts)

    @property
    def is_terminal(self) -> bool:
        return self.phase in TERMINAL_PHASES


def derive_phase(state: MissionState, facts: MissionFacts) -> PhaseDecision:
    """Deterministically derive the next phase; durable facts win over state."""
    conflicts: list[str] = []
    if int(state.schema_version) > SUPPORTED_SCHEMA_VERSION:
        return PhaseDecision("blocked", "unsupported state schema", ("schema",))
    if facts.mission_id is not None and state.mission_id and int(facts.mission_id) != int(state.mission_id):
        conflicts.append("mission_id mismatch")
    if facts.project_id is not None and state.project_id and int(facts.project_id) != int(state.project_id):
        conflicts.append("project_id mismatch")
    if conflicts:
        return PhaseDecision("blocked", "durable facts contradict pinned flow identity",
                             tuple(conflicts))

    mission_status = str(facts.mission_status or "").strip().lower()
    promotion = str(facts.promotion_status or "").strip().lower()
    verdict = str(facts.review_verdict or "").strip().upper()

    if facts.interrupted or mission_status == "interrupted":
        phase, reason = "interrupted", "mission interrupted"
    elif mission_status == "completed":
        if facts.live_promoted or promotion in _PROMOTED_STATUSES:
            phase, reason = "completed", "mission completed and promotion recorded"
        else:
            conflicts.append("completed mission without promotion evidence")
            phase, reason = "blocked", "completed mission lacks promotion evidence"
    elif mission_status in ("blocked", "failed"):
        phase, reason = "blocked", "mission is " + mission_status
    elif facts.live_promoted or promotion in _PROMOTED_STATUSES:
        phase, reason = "completed", "promotion is recorded live"
    elif promotion in _PROMOTING_STATUSES or verdict == "APPROVE":
        phase, reason = "promoting", "review approved or promotion journal pending"
    elif verdict == "REJECT":
        phase, reason = "blocked", "reviewer rejected the candidate"
    elif facts.verification_persisted:
        candidate_ok = facts.candidate_passed is True
        oracle_ok = facts.oracle_passed is True
        if candidate_ok and oracle_ok:
            phase, reason = "reviewing", "candidate and oracle verification passed"
        elif facts.repair_round >= max(0, int(facts.max_repairs)):
            phase, reason = "blocked", "verification failed and repair budget exhausted"
        else:
            phase, reason = "repairing", "verification failed; bounded repair pending"
    elif facts.developer_status and str(facts.developer_status).lower() in _DEVELOPER_DONE_STATES:
        phase, reason = "verifying", "developer work is durable; verification pending"
    elif str(state.phase) in ("developing", "verifying"):
        phase, reason = str(state.phase), "state phase retained (no contradicting facts)"
    else:
        phase, reason = "planned", "no durable progress recorded"

    if facts.approval_pending and phase not in TERMINAL_PHASES:
        phase, reason = "waiting_approval", "durable approval is pending"

    if str(state.phase) in ("completed", "blocked") and phase != str(state.phase):
        conflicts.append("terminal state phase " + str(state.phase)
                         + " contradicted by facts")
        phase, reason = "blocked", "stale terminal flow state reconciled against facts"

    return PhaseDecision(phase, reason, tuple(conflicts))

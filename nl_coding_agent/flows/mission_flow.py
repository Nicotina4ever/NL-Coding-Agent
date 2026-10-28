"""C4b MissionFlow skeleton: developer -> verify/repair -> review -> promote.

The flow is deterministic policy around an injected MissionStageExecutor. Every
step is guarded by authoritative durable facts (re-derived on resume), the flow
writes only its own flow state via AppFlowPersistence, and it never writes
mission/queue/promotion status itself. The default sequential orchestrator and
supervisor do not import or wire this module (C4c adds an explicit pipeline).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable

from crewai.flow.flow import Flow, start
from crewai.flow.persistence import persist
from pydantic import ConfigDict, Field

from nl_coding_agent.core.run_control import RunStopped
from nl_coding_agent.flows.persistence import AppFlowPersistence
from nl_coding_agent.flows.state import (
    TERMINAL_PHASES,
    MissionFacts,
    MissionState,
    PhaseDecision,
    derive_phase,
)

__all__ = [
    "MissionFlowError", "StepResult", "MissionStageExecutor", "MissionFlow",
    "STEP_STATUSES",
]

STEP_STATUSES: tuple[str, ...] = (
    "ok", "needs_repair", "blocked", "interrupted", "waiting_approval",
)
_PHASE_TO_STATUS = {
    "completed": "completed",
    "blocked": "blocked",
    "interrupted": "interrupted",
    "waiting_approval": "waiting_approval",
}
_MAX_PIPELINE_ITERATIONS = 8
_PROJECTION_KEYS = (
    "stage_dir", "baseline_sha256", "changed_paths", "diff_stat",
    "promotion_status", "verification_ref", "review_verdict", "review_ref",
    "approval_id", "approval_action",
)


class MissionFlowError(RuntimeError):
    """The flow cannot safely continue."""


@dataclass(frozen=True)
class StepResult:
    status: str = "ok"
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        status = str(self.status or "").strip()
        if status not in STEP_STATUSES:
            raise MissionFlowError("Invalid step status: " + repr(self.status))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "payload", dict(self.payload or {}))

    @classmethod
    def ok(cls, **payload) -> "StepResult":
        return cls("ok", payload)

    @classmethod
    def needs_repair(cls, **payload) -> "StepResult":
        return cls("needs_repair", payload)

    @classmethod
    def blocked(cls, error: str = "", *, error_code: str | None = None, **payload) -> "StepResult":
        payload.setdefault("error", error)
        if error_code:
            payload.setdefault("error_code", error_code)
        return cls("blocked", payload)

    @classmethod
    def interrupted(cls, **payload) -> "StepResult":
        return cls("interrupted", payload)

    @classmethod
    def waiting_approval(cls, **payload) -> "StepResult":
        return cls("waiting_approval", payload)


@runtime_checkable
class MissionStageExecutor(Protocol):
    """Deterministic policy calls; implementations own all model/stage work."""

    def run_developer(self, state: MissionState) -> StepResult: ...
    def run_verification(self, state: MissionState) -> StepResult: ...
    def run_repair(self, state: MissionState) -> StepResult: ...
    def run_reviewer(self, state: MissionState) -> StepResult: ...
    def promote(self, state: MissionState) -> StepResult: ...


#: Class-level persistence metadata only; each MissionFlow instance must supply its
#: own app-owned persistence (never the CrewAI default store).
_DEFINITION_PERSISTENCE = AppFlowPersistence()


@persist(_DEFINITION_PERSISTENCE)
class MissionFlow(Flow[MissionState]):
    """Flow[MissionState] with pinned-id durable-state resume and fact guards."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    _skip_auto_memory: ClassVar[bool] = True

    executor: Any = Field(default=None, exclude=True)
    facts_provider: Any = Field(default=None, exclude=True)
    control: Any = Field(default=None, exclude=True)

    # ------------------------------------------------------------------ helpers

    def _executor(self) -> MissionStageExecutor:
        if self.executor is None:
            raise MissionFlowError("MissionFlow requires an executor")
        return self.executor

    def _facts(self) -> MissionFacts:
        state = self.state
        provider = self.facts_provider
        if provider is not None:
            raw = provider(state)
            if isinstance(raw, MissionFacts):
                return raw
            if isinstance(raw, dict):
                return MissionFacts.from_mapping(raw)
            raise MissionFlowError("facts_provider must return MissionFacts or dict")
        if int(state.mission_id) > 0:
            return MissionFacts.from_durable(int(state.mission_id))
        raise MissionFlowError("MissionFlow requires facts_provider or mission_id")

    @staticmethod
    def _normalize(result: Any) -> StepResult:
        if isinstance(result, StepResult):
            return result
        if isinstance(result, dict):
            return StepResult(str(result.get("status") or "ok"), result.get("payload") or {})
        raise MissionFlowError("Executor returned an unsupported result")

    def _save(self, method_name: str) -> None:
        persistence = self.persistence
        if persistence is None:
            raise MissionFlowError("MissionFlow requires app-owned persistence")
        persistence.save_state(self.state.flow_id, method_name, self.state)

    def _apply(self, *, phase: str | None = None,
               result: StepResult | None = None,
               error: str | None = None,
               error_code: str | None = None) -> None:
        updates: dict[str, Any] = {}
        if phase is not None:
            updates["phase"] = phase
        if result is not None:
            for key in _PROJECTION_KEYS:
                if key in result.payload:
                    updates[key] = result.payload[key]
            if result.status == "blocked":
                updates["last_error"] = str(
                    error or result.payload.get("error") or "blocked"
                )
                updates["error_code"] = str(
                    error_code or result.payload.get("error_code") or "blocked"
                )
        if error is not None:
            updates["last_error"] = str(error)
        if error_code is not None:
            updates["error_code"] = str(error_code)
        self._state = self.state.with_updates(**updates)

    def _checkpoint(self, stage: str) -> None:
        control = self.control
        if control is None:
            return
        checkpoint = getattr(control, "checkpoint", None)
        if checkpoint is not None:
            checkpoint(stage)

    def _decision(self) -> PhaseDecision:
        return derive_phase(self.state, self._facts())

    # ------------------------------------------------------------------ graph

    @start()
    def run(self) -> dict:
        """Single deterministic pipeline; durable facts decide where it resumes."""
        try:
            decision = self._decision()
            self._apply(phase=decision.phase)
            self._save("begin")
            if decision.conflicts:
                self._apply(
                    phase="blocked",
                    error="; ".join(decision.conflicts),
                    error_code="reconciliation_conflict",
                )
                return self._finish("blocked", payload={"conflicts": list(decision.conflicts)})
            return self._drive(decision.phase)
        except RunStopped as exc:
            self._apply(phase="interrupted", error=str(exc) or "stopped",
                        error_code="run_stopped")
            self._save("interrupted")
            return self._finish("interrupted")

    def _drive(self, phase: str) -> dict:
        for _ in range(_MAX_PIPELINE_ITERATIONS):
            if phase in TERMINAL_PHASES or phase == "waiting_approval":
                return self._finish(phase)
            if phase in ("planned", "developing"):
                phase = self._step_developer()
            elif phase == "verifying":
                phase = self._step_verification()
            elif phase == "repairing":
                phase = self._step_repair()
            elif phase == "reviewing":
                phase = self._step_review()
            elif phase == "promoting":
                phase = self._step_promote()
            else:
                return self._finish("blocked", payload={"error": "unknown phase " + str(phase)})
        self._apply(phase="blocked", error="flow pipeline exceeded its safe step bound",
                    error_code="pipeline_loop")
        self._save("blocked")
        return self._finish("blocked")

    # --- steps -------------------------------------------------------------

    def _step_developer(self) -> str:
        facts = self._facts()
        if facts.developer_status and str(facts.developer_status).lower() in (
            "completed", "done", "skipped",
        ):
            result = StepResult.ok(changed_paths=list(self.state.changed_paths))
        else:
            result = self._normalize(self._executor().run_developer(self.state))
        if result.status != "ok":
            self._apply(phase="blocked" if result.status == "blocked" else "interrupted",
                        result=result)
            self._save("developer")
            return self.state.phase
        self._apply(result=result)
        self._checkpoint("developer")
        self._apply(phase="verifying")
        self._save("developer")
        return "verifying"

    def _step_verification(self) -> str:
        result = self._normalize(self._executor().run_verification(self.state))
        self._apply(result=result)
        if result.status == "needs_repair":
            if int(self.state.repair_round) < int(self.state.max_repairs):
                self._apply(phase="repairing")
                self._save("verify")
                return "repairing"
            self._apply(phase="blocked",
                        error="verification failed; repair budget exhausted",
                        error_code="repair_budget")
            self._save("verify")
            return "blocked"
        if result.status != "ok":
            self._apply(phase="blocked" if result.status == "blocked" else "interrupted",
                        result=result)
            self._save("verify")
            return self.state.phase
        self._checkpoint("tester")
        self._apply(phase="reviewing")
        self._save("verify")
        return "reviewing"

    def _step_repair(self) -> str:
        if int(self.state.repair_round) >= int(self.state.max_repairs):
            self._apply(phase="blocked", error="repair budget exhausted",
                        error_code="repair_budget")
            self._save("repair")
            return "blocked"
        result = self._normalize(self._executor().run_repair(self.state))
        if result.status != "ok":
            self._apply(phase="blocked" if result.status == "blocked" else "interrupted",
                        result=result)
            self._save("repair")
            return self.state.phase
        self._state = self.state.with_updates(
            repair_round=int(self.state.repair_round) + 1,
            attempt=int(self.state.attempt) + 1,
        )
        self._apply(result=result)
        self._apply(phase="verifying")
        self._save("repair")
        return "verifying"

    def _step_review(self) -> str:
        facts = self._facts()
        if facts.review_verdict:
            verdict = str(facts.review_verdict).upper()
            result = StepResult.ok(review_verdict=verdict)
        else:
            result = self._normalize(self._executor().run_reviewer(self.state))
        verdict = str(result.payload.get("review_verdict")
                      or result.payload.get("verdict") or "").upper()
        self._apply(result=result)
        if result.status != "ok":
            self._apply(phase="blocked" if result.status == "blocked" else "interrupted",
                        result=result)
            self._save("review")
            return self.state.phase
        if verdict == "REJECT":
            self._apply(phase="blocked", error="reviewer rejected the candidate",
                        error_code="review_rejected")
            self._save("review")
            return "blocked"
        if verdict != "APPROVE":
            self._apply(phase="blocked", error="reviewer verdict is missing/ambiguous",
                        error_code="review_ambiguous")
            self._save("review")
            return "blocked"
        self._checkpoint("reviewer")
        self._apply(phase="promoting")
        self._save("review")
        return "promoting"

    def _step_promote(self) -> str:
        facts = self._facts()
        if facts.live_promoted:
            result = StepResult.ok(promotion_status=facts.promotion_status or "promoted")
        else:
            result = self._normalize(self._executor().promote(self.state))
        self._apply(result=result)
        if result.status != "ok":
            self._apply(phase="blocked" if result.status == "blocked" else "interrupted",
                        result=result)
            self._save("promote")
            return self.state.phase
        self._apply(phase="completed")
        self._save("promote")
        return "completed"

    def _finish(self, phase: str, *, payload: dict | None = None) -> dict:
        target = phase if phase in TERMINAL_PHASES else (
            "waiting_approval" if phase == "waiting_approval" else "blocked"
        )
        self._apply(phase=target)
        self._save("finish")
        state = self.state
        return {
            "flow_id": state.flow_id,
            "status": _PHASE_TO_STATUS.get(target, "blocked"),
            "phase": target,
            "mission_id": state.mission_id,
            "project_id": state.project_id,
            "changed_paths": list(state.changed_paths),
            "diff_stat": state.diff_stat,
            "promotion_status": state.promotion_status,
            "review_verdict": state.review_verdict,
            "error": state.last_error,
            "error_code": state.error_code,
            **(payload or {}),
        }

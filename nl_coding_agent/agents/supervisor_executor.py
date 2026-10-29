"""C4c: MissionStageExecutor adapter over the REAL staged-candidate orchestrator.

MissionFlow calls these methods; they invoke the same orchestrator stage methods,
validators, verifier, reviewer and promotion/CAS machinery as the sequential path.
The adapter never writes mission status: only the supervisor (via finalize(), which
calls the orchestrator's terminal finalizers) writes terminal mission state.
"""
from __future__ import annotations

import json
from typing import Any

from nl_coding_agent.agents.orchestrator import (
    DEFAULT_DEBUG_MODEL,
    DEFAULT_DEVELOPER_MODEL,
    DEFAULT_REVIEWER_MODEL,
    DeveloperNoChangeError,
    MultiAgentOrchestrator,
    ScopeViolationError,
    VerificationError,
    _truncate,
)
from nl_coding_agent.core import promotion
from nl_coding_agent.core.promotion import GateFailure
from nl_coding_agent.core.run_control import RunStopped
from nl_coding_agent.flows.mission_flow import StepResult

__all__ = ["SupervisorMissionExecutor", "ExecutorError"]


class ExecutorError(RuntimeError):
    """The flow executor cannot prepare a mission safely."""


class SupervisorMissionExecutor:
    """One executor per mission; drives real orchestrator stages for MissionFlow."""

    def __init__(self, orchestrator: MultiAgentOrchestrator, mission_id: int,
                 goal: str, *, control=None,
                 developer_model: str | None = None,
                 reviewer_model: str | None = None,
                 debug_model: str | None = None,
                 architect_model: str | None = None) -> None:
        self.orchestrator = orchestrator
        self.mission_id = int(mission_id)
        self.goal = str(goal or "")
        self.control = control
        self.developer_model = developer_model or DEFAULT_DEVELOPER_MODEL
        self.reviewer_model = reviewer_model or DEFAULT_REVIEWER_MODEL
        self.debug_model = debug_model or DEFAULT_DEBUG_MODEL
        self.architect_model = architect_model or self.developer_model
        self.stage = None
        self.baseline: dict[str, str] = {}
        self.mission: dict = {}
        self.tasks: dict[str, dict] = {}
        self.review_text = ""
        self._prepared = False

    # ------------------------------------------------------------------ setup

    def _checkpoint(self, stage: str) -> None:
        self.orchestrator._checkpoint(self.control, stage)

    def prepare(self) -> None:
        if self._prepared:
            return
        orch = self.orchestrator
        from nl_coding_agent.persistence.missions import (
            get_mission, get_tasks, increment_resume_count, record_handoff,
            reset_interrupted_tasks,
        )

        mission = get_mission(self.mission_id) or {}
        if not mission:
            raise ExecutorError("Mission not found: " + str(self.mission_id))
        orch._assert_harness_mission(mission)
        existing_tasks = get_tasks(self.mission_id)
        if existing_tasks:
            reset_ids = reset_interrupted_tasks(self.mission_id)
            if reset_ids or mission.get("status") in ("running", "interrupted", "failed", "blocked"):
                increment_resume_count(self.mission_id)
                record_handoff(self.mission_id, "system", "orchestrator",
                               "Flow resume from persisted state",
                               {"reset_tasks": reset_ids})
        tasks = get_tasks(self.mission_id) if existing_tasks else orch._plan_tasks(self.mission_id, self.goal)
        orch._validate_plan(tasks)
        planned_roles = {str(task.get("agent_role") or "") for task in tasks}
        assignment_routes = {
            "architect": self.architect_model,
            "developer": self.developer_model,
            "reviewer": self.reviewer_model,
            "debugger": self.debug_model,
        }
        if "auditor" in planned_roles:
            assignment_routes["auditor"] = self.developer_model
        orch._record_model_assignments(self.mission_id, assignment_routes)
        if existing_tasks:
            baseline = orch._load_baseline(self.mission_id)
            if baseline is None:
                baseline = orch._snapshot()
        else:
            baseline = orch._snapshot()
            orch._save_baseline(self.mission_id, baseline)
        task_map = {t["agent_role"]: t for t in tasks}
        stage = orch._ensure_stage(self.mission_id, task_map.get("developer"), self.goal)
        outcome = promotion.reconcile(stage, recovery_dir=orch._recovery_dir())
        if outcome.get("state") == "conflict":
            raise GateFailure("Promotion journal conflict: " + json.dumps(outcome, default=str),
                              code="rollback-conflict", details=outcome)
        if outcome.get("state") == "promotion-complete" or promotion.is_live_promoted(stage):
            orch._save_promotion_status(self.mission_id, "promoted")
        self.mission = mission
        self.tasks = task_map
        self.baseline = baseline
        self.stage = stage
        self._prepared = True

    def _blocked(self, exc: Exception) -> StepResult:
        if isinstance(exc, GateFailure):
            return StepResult.blocked(str(exc), error_code=exc.code)
        if isinstance(exc, VerificationError):
            return StepResult.blocked(str(exc), error_code="verification-failed")
        if isinstance(exc, DeveloperNoChangeError):
            return StepResult.blocked(str(exc), error_code="developer-no-change")
        if isinstance(exc, ScopeViolationError):
            return StepResult.blocked(str(exc), error_code="scope-violation")
        raise exc

    def _candidate_payload(self) -> dict:
        diff, changed, stat = promotion.candidate_diff(self.stage)
        return {
            "changed_paths": list(changed), "diff_stat": stat,
            "stage_dir": str(self.stage.stage_dir),
        }

    # -------------------------------------------------------------- executor API

    def run_developer(self, state) -> StepResult:
        try:
            self.prepare()
            self._checkpoint("before-architect")
            planned_tasks = list(self.tasks.values())
            architecture_notes = self.orchestrator._run_planned_analysis(
                self.mission_id, planned_tasks, self.goal,
                {"architect": self.architect_model, "auditor": self.developer_model},
            )
            self._checkpoint("after-architect")
            self._checkpoint("before-developer")
            task = self.tasks.get("developer")
            if task and task["status"] != "completed":
                self.orchestrator._run_developer_stage(
                    self.mission_id, task, self.goal,
                    self.developer_model, self.baseline, self.stage,
                    architecture_notes=architecture_notes,
                )
            elif task:
                verdict = self.orchestrator._validate_stage(self.stage)
                if not verdict["valid"]:
                    raise GateFailure(
                        "Persisted staged candidate no longer validates: "
                        + "; ".join(verdict["errors"]), code="candidate-rejected",
                        details={"errors": verdict["errors"]},
                    )
            self._checkpoint("after-developer")
            return StepResult.ok(**self._candidate_payload())
        except RunStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - classified by the flow/supervisor
            return self._blocked(exc)

    def run_verification(self, state) -> StepResult:
        try:
            self.prepare()
            self._checkpoint("before-tester")
            task = self.tasks.get("tester")
            if task and task["status"] != "completed":
                self.orchestrator._run_tester_stage(
                    self.mission_id, task,
                    self.debug_model, self.baseline, self.stage,
                )
            elif task:
                self.orchestrator._rebind_persisted_verification(self.mission_id, self.stage)
            runs = __import__("nl_coding_agent.persistence.missions", fromlist=["get_verification_runs"]).get_verification_runs(self.mission_id)
            self._checkpoint("after-tester")
            return StepResult.ok(
                verification_ref=("runs:" + str(len(runs))),
                **self._candidate_payload(),
            )
        except RunStopped:
            raise
        except Exception as exc:  # noqa: BLE001
            return self._blocked(exc)

    def run_repair(self, state) -> StepResult:
        # The real tester stage already performs bounded debugger repairs; MissionFlow's
        # outer repair loop is therefore a no-op here (no duplicate repair loop).
        return StepResult.ok()

    def run_reviewer(self, state) -> StepResult:
        try:
            self.prepare()
            self._checkpoint("before-reviewer")
            task = self.tasks.get("reviewer")
            if task and task["status"] != "completed":
                review_text, verdict = self.orchestrator._run_reviewer_stage(
                    self.mission_id, task,
                    self.reviewer_model, self.baseline, self.stage,
                )
            else:
                review_text, verdict = self.orchestrator._persisted_review(self.mission_id)
            self.review_text = _truncate(review_text, 4000)
            return StepResult.ok(review_verdict=str(verdict),
                                 review_ref="handoff", **self._candidate_payload())
        except RunStopped:
            raise
        except Exception as exc:  # noqa: BLE001
            return self._blocked(exc)

    def promote(self, state) -> StepResult:
        try:
            self.prepare()
            self._checkpoint("before-promotion")
            result = self.orchestrator._promote_candidate(self.stage)
            payload = self._candidate_payload()
            payload.update({
                "promotion_status": "promoted",
                "promoted": list(result.get("promoted") or []),
            })
            return StepResult.ok(**payload)
        except RunStopped:
            raise
        except Exception as exc:  # noqa: BLE001
            return self._blocked(exc)

    # -------------------------------------------------------------- finalization

    def finalize(self, flow_result: dict) -> dict:
        """Called ONLY by the supervisor after MissionFlow returns (writes terminal status)."""
        self.prepare()
        status = str(flow_result.get("status") or "blocked")
        if status == "completed":
            result = self.orchestrator._finalize_completed(
                self.mission_id, self.goal, self.baseline,
                review_text=self.review_text,
                verdict=str(flow_result.get("review_verdict") or "APPROVE"),
                summary="Flow pipeline completed; candidate promoted.",
            )
            try:
                promotion.cleanup_after_terminal(
                    self.stage, mission_status="completed",
                    evidence_dir=self.orchestrator._evidence_dir(),
                    verification=self.orchestrator._last_verification_dict(),
                )
            except Exception:
                pass
            return result
        if status == "interrupted":
            return self.orchestrator._finalize_interrupted(
                self.mission_id, self.stage,
                summary="Flow pipeline interrupted at a safe checkpoint.",
            )
        if status == "waiting_approval":
            return self.orchestrator._finalize_interrupted(
                self.mission_id, self.stage,
                summary="Flow pipeline waiting for human approval.",
            )
        error = str(flow_result.get("error") or "Flow pipeline blocked")
        code = str(flow_result.get("error_code") or "flow-blocked")
        return self.orchestrator._finalize_blocked(
            self.mission_id, error,
            str(flow_result.get("review_verdict") or "REJECT"),
            stage=self.stage, code=code,
        )

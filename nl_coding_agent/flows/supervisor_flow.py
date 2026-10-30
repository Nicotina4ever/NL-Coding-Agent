"""C4c: SupervisorRunFlow - run-level Flow coordinator.

Selects nothing itself (the supervisor remains the only selector/status writer);
it owns exactly one SupervisorMissionExecutor per mission, pins one durable Flow id
per mission, runs MissionFlow, records flow evidence and exposes read-only flow
state for status APIs. The supervisor decides whether this path is enabled.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from nl_coding_agent.flows.mission_flow import MissionFlow
from nl_coding_agent.flows.persistence import AppFlowPersistence
from nl_coding_agent.flows.state import MissionFacts, MissionState
from nl_coding_agent.persistence import missions
from nl_coding_agent.persistence import supervisor_store as store

__all__ = ["SupervisorRunFlow"]


class SupervisorRunFlow:
    """Exactly-one-executor-per-mission coordinator around MissionFlow."""

    def __init__(self, supervisor: Any, *, persistence: AppFlowPersistence | None = None):
        self.supervisor = supervisor
        self._persistence = persistence
        self._executors: dict[int, Any] = {}
        self._flows: dict[int, MissionFlow] = {}

    # ---------------------------------------------------------------- helpers

    @property
    def persistence(self) -> AppFlowPersistence:
        if self._persistence is None:
            self._persistence = AppFlowPersistence()
        return self._persistence

    def executor_for(self, mission_id: int, goal: str):
        key = int(mission_id)
        if key not in self._executors:
            executor = self.supervisor._build_executor(key, goal)
            if executor is None:  # pragma: no cover - flow path always has one
                raise RuntimeError("Flow pipeline requires a MissionStageExecutor")
            self._executors[key] = executor
        return self._executors[key]

    def flow_id_for(self, mission: dict) -> str:
        mission_id = int(mission["id"])
        existing = mission.get("flow_id")
        if existing:
            return str(existing)
        flow_id = uuid.uuid4().hex
        missions.set_mission_flow(mission_id, flow_id)
        return flow_id

    def flow_for(self, mission_id: int) -> MissionFlow | None:
        return self._flows.get(int(mission_id))

    def active_flow_ids(self) -> list[str]:
        """Flows currently owned by this live runner (never reconciled away)."""
        return [str(flow_id) for flow_id in list(self._flows)]

    # ------------------------------------------------------------------ run

    def run_mission(self, mission_id: int, goal: str | None = None) -> dict:
        mission = missions.get_mission(int(mission_id))
        if mission is None:
            raise RuntimeError("Mission not found: " + str(mission_id))
        mission_id = int(mission["id"])
        effective_goal = str(goal or mission.get("goal") or "").strip()
        status = str(mission.get("status") or "")
        if status in ("completed", "blocked", "failed"):
            return {
                "status": status, "mission_id": mission_id, "executor": None,
                "flow_id": mission.get("flow_id"),
                "flow_result": {"status": status, "phase": status},
            }
        executor = self.executor_for(mission_id, effective_goal)
        flow_id = self.flow_id_for(mission)
        store.start_flow_run(
            flow_id, int(self.supervisor.project_id), mission_id=mission_id,
            pipeline="mission", status="RUNNING",
            owner_pid=int(getattr(self.supervisor, "owner_pid", os.getpid())),
            owner_id=str(getattr(self.supervisor, "owner_id", "") or ""),
        )
        initial = MissionState(
            id=flow_id, project_id=int(self.supervisor.project_id),
            mission_id=mission_id, goal=effective_goal,
            requirement_id=mission.get("requirement_id"),
            supervisor_run_id=mission.get("supervisor_run_id"),
            max_repairs=int(self.supervisor.config.max_attempts_per_requirement),
        )
        flow = MissionFlow(
            initial_state=initial, persistence=self.persistence, executor=executor,
            facts_provider=lambda state: MissionFacts.from_durable(mission_id),
            suppress_flow_events=True, tracing=False,
        )
        self._flows[mission_id] = flow
        try:
            result = flow.kickoff(inputs={"id": flow_id})
        except Exception as exc:  # noqa: BLE001 - persist before finalizing
            from nl_coding_agent.core.failure_evidence import record_exception

            payload = record_exception(
                mission_id, exc, source="flow_kickoff", method="kickoff",
                flow_id=flow_id, phase=str(getattr(flow.state, "phase", "") or ""),
            )
            try:
                store.finish_flow_run(
                    flow_id, "FAILED", error_code="executor_exception",
                    error_message=payload["exception_type"] + ": " + payload["message"],
                    last_method="exception",
                )
            except Exception:
                pass
            self._flows.pop(mission_id, None)
            raise
        self.record_evidence(mission_id, flow_id, result)
        try:
            result_status = str(result.get("status") or "blocked").lower()
            if str(result.get("error_code") or "") == "executor_exception":
                result_status = "failed"
            target = {
                "completed": "COMPLETED", "failed": "FAILED", "blocked": "BLOCKED",
                "interrupted": "INTERRUPTED",
                "waiting_approval": "PAUSED_WAITING_APPROVAL",
            }.get(result_status, "BLOCKED")
            store.finish_flow_run(
                flow_id, target,
                error_code=str(result.get("error_code") or "") or None,
                error_message=(str(result.get("error") or "")[:8000] or None),
                last_method=str(result.get("phase") or "finish"),
            )
        except Exception:
            pass
        finally:
            self._flows.pop(mission_id, None)
        return {
            "status": str(result.get("status") or "blocked"),
            "mission_id": mission_id, "executor": executor, "flow_id": flow_id,
            "flow_result": result,
        }

    def record_evidence(self, mission_id: int, flow_id: str, result: dict) -> None:
        try:
            store.record_evidence(
                int(mission_id), kind="flow", record_key="flow:" + str(flow_id),
                payload={
                    "flow_id": flow_id,
                    "status": result.get("status"),
                    "phase": result.get("phase"),
                    "promotion_status": result.get("promotion_status"),
                    "changed_paths": list(result.get("changed_paths") or []),
                },
            )
        except Exception:
            pass

    def status(self, *, flow_id: str | None = None, limit: int = 20) -> dict:
        project_id = int(self.supervisor.project_id)
        runs = store.list_flow_runs(project_id=project_id)
        if flow_id:
            runs = [row for row in runs if row.get("flow_id") == flow_id]
        counts: dict[str, int] = {}
        for row in runs:
            state = str(row.get("status") or "")
            counts[state] = counts.get(state, 0) + 1
        return {
            "pipeline": "flow",
            "flow_runs": runs[: int(limit)],
            "flow_counts": counts,
            "active_flows": [row for row in runs
                             if row.get("status") == "RUNNING"][: int(limit)],
        }

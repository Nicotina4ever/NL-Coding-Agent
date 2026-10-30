"""C4b: pinned-id durable-state resume/restart for MissionFlow (fake executor)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from nl_coding_agent.core.run_control import RunControl
from nl_coding_agent.flows.mission_flow import MissionFlow, StepResult
from nl_coding_agent.flows.persistence import AppFlowPersistence
from nl_coding_agent.flows.state import MissionFacts, MissionState
from nl_coding_agent.persistence import database, missions
from nl_coding_agent.persistence import supervisor_store as store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    database.init_db().close()


class FactsBox:
    def __init__(self):
        self.facts = MissionFacts(mission_id=1, project_id=1, mission_status="running")

    def update(self, **changes):
        self.facts = replace(self.facts, **changes)
        return self.facts

    def provider(self, _state=None):
        return self.facts


class CrashExecutor:
    """Updates durable facts like the real pipeline, then crashes in a chosen step."""

    def __init__(self, box: FactsBox, *, crash_in: str | None = None):
        self.box = box
        self.crash_in = crash_in
        self.calls: list[str] = []

    def _crash(self, name: str) -> None:
        if self.crash_in == name:
            raise RuntimeError("simulated crash in " + name)

    def run_developer(self, state):
        self.calls.append("developer")
        self._crash("developer")
        self.box.update(developer_status="completed")
        return StepResult.ok(changed_paths=["src/flow.py"], diff_stat="1 file")

    def run_verification(self, state):
        self.calls.append("verification")
        self._crash("verification")
        self.box.update(verification_persisted=True, candidate_passed=True,
                        oracle_passed=True)
        return StepResult.ok(verification_ref="verify-1")

    def run_repair(self, state):
        self.calls.append("repair")
        self._crash("repair")
        return StepResult.ok()

    def run_reviewer(self, state):
        self.calls.append("reviewer")
        self._crash("reviewer")
        self.box.update(review_verdict="APPROVE")
        return StepResult.ok(review_verdict="APPROVE")

    def promote(self, state):
        self.calls.append("promotion")
        self._crash("promotion")
        self.box.update(promotion_status="promoted", live_promoted=True)
        return StepResult.ok(promotion_status="promoted")


def make_flow(flow_id: str, box: FactsBox, executor, persistence: AppFlowPersistence,
              control=None) -> MissionFlow:
    return MissionFlow(
        initial_state=MissionState(id=flow_id, project_id=1, mission_id=1),
        persistence=persistence, executor=executor,
        facts_provider=box.provider, control=control,
        suppress_flow_events=True, tracing=False,
    )


def test_crash_then_failure_is_persisted_without_promotion():
    box = FactsBox()
    persistence = AppFlowPersistence()
    flow_id = "flow-resume-crash"
    first = make_flow(flow_id, box, CrashExecutor(box, crash_in="reviewer"), persistence)
    result = first.kickoff(inputs={})
    assert result["status"] == "failed"
    assert result["error_code"] == "executor_exception"
    assert first.state.phase == "blocked"
    assert persistence.snapshot_count(flow_id) >= 3
    run = store.get_flow_run(flow_id)
    assert run["status"] == "FAILED"
    assert run["error_code"] == "executor_exception"
    assert "simulated crash in reviewer" in (run["error_message"] or "")
    latest = persistence.load_state(flow_id)
    assert latest["phase"] == "blocked"
    assert latest["error_code"] == "executor_exception"
    assert latest["mission_id"] == 1
    assert not any(name == "promotion" for name in first.executor.calls)


def test_restart_after_completion_is_a_no_op_for_the_executor():
    box = FactsBox()
    persistence = AppFlowPersistence()
    flow_id = "flow-resume-done"
    first = make_flow(flow_id, box, CrashExecutor(box), persistence)
    assert first.kickoff(inputs={})["status"] == "completed"
    snapshots = persistence.snapshot_count(flow_id)
    second_executor = CrashExecutor(box)
    second = make_flow(flow_id, box, second_executor, persistence)
    result = second.kickoff(inputs={"id": flow_id})
    assert result["status"] == "completed"
    assert second_executor.calls == []
    # begin + finish + the engine's final persist: no new step executions.
    assert persistence.snapshot_count(flow_id) >= snapshots + 2
    assert store.get_flow_run(flow_id)["status"] == "COMPLETED"


def test_crash_before_developer_is_persisted_and_never_promotes():
    box = FactsBox()
    persistence = AppFlowPersistence()
    flow_id = "flow-resume-begin"
    first = make_flow(flow_id, box, CrashExecutor(box, crash_in="developer"), persistence)
    result = first.kickoff(inputs={})
    assert result["status"] == "failed"
    assert result["error_code"] == "executor_exception"
    assert "simulated crash in developer" in (result["error"] or "")
    assert persistence.load_state(flow_id)["phase"] == "blocked"
    assert store.get_flow_run(flow_id)["status"] == "FAILED"
    assert first.executor.calls == ["developer"]


def test_stop_then_resume_after_developer_does_not_repeat_developer():
    box = FactsBox()
    persistence = AppFlowPersistence()
    flow_id = "flow-resume-stop"
    control = RunControl()
    control.request_stop("operator")
    first = make_flow(flow_id, box, CrashExecutor(box), persistence, control=control)
    result = first.kickoff(inputs={})
    assert result["status"] == "interrupted"
    assert persistence.load_state(flow_id)["phase"] == "interrupted"
    assert store.get_flow_run(flow_id)["status"] == "INTERRUPTED"
    resumed_executor = CrashExecutor(box)
    resumed = make_flow(flow_id, box, resumed_executor, persistence)
    resumed_result = resumed.kickoff(inputs={"id": flow_id})
    assert resumed_result["status"] == "completed"
    assert resumed_executor.calls == ["verification", "reviewer", "promotion"]


def test_caught_crash_does_not_rewrite_live_mission_status_or_create_second_mission():
    box = FactsBox()
    persistence = AppFlowPersistence()
    mission_id = missions.create_mission(None, "resume mission", "goal")
    flow_id = "flow-resume-mission"
    first = MissionFlow(
        initial_state=MissionState(id=flow_id, project_id=1, mission_id=mission_id),
        persistence=persistence, executor=CrashExecutor(box, crash_in="reviewer"),
        facts_provider=box.provider, suppress_flow_events=True, tracing=False,
    )
    result = first.kickoff(inputs={})
    assert result["status"] == "failed"
    assert missions.get_mission(mission_id)["status"] == "pending"
    assert len(missions.list_missions()) == 1
    assert len(store.list_flow_runs(project_id=1)) == 1

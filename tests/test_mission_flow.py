"""C4b: MissionFlow skeleton - guarded step mapping, no direct status writes, stop."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from nl_coding_agent.core.run_control import RunControl, RunStopped
from nl_coding_agent.flows.mission_flow import MissionFlow, StepResult
from nl_coding_agent.flows.persistence import AppFlowPersistence
from nl_coding_agent.flows.state import MissionState, MissionFacts
from nl_coding_agent.persistence import database, missions
from nl_coding_agent.persistence import supervisor_store as store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    database.init_db().close()


class FactsBox:
    def __init__(self, facts: MissionFacts):
        self.facts = facts

    def update(self, **changes) -> MissionFacts:
        self.facts = replace(self.facts, **changes)
        return self.facts

    def provider(self, _state=None):
        return self.facts


class FakeExecutor:
    def __init__(self, box: FactsBox):
        self.box = box
        self.calls: list[str] = []
        self.overrides: dict[str, StepResult] = {}
        self.promote_handler = None

    def _run(self, name: str, state):
        self.calls.append(name)
        if name in self.overrides:
            return self.overrides[name]
        if name == "developer":
            self.box.update(developer_status="completed")
            return StepResult.ok(changed_paths=["src/flow.py"], diff_stat="1 file")
        if name == "verification":
            self.box.update(verification_persisted=True, candidate_passed=True,
                            oracle_passed=True)
            return StepResult.ok(verification_ref="verify-1")
        if name == "repair":
            return StepResult.ok()
        if name == "reviewer":
            self.box.update(review_verdict="APPROVE")
            return StepResult.ok(review_verdict="APPROVE", review_ref="review-1")
        if name == "promotion":
            if self.promote_handler is not None:
                return self.promote_handler(state)
            self.box.update(promotion_status="promoted", live_promoted=True)
            return StepResult.ok(promotion_status="promoted")
        raise AssertionError("unknown executor call " + name)

    def run_developer(self, state):
        return self._run("developer", state)

    def run_verification(self, state):
        return self._run("verification", state)

    def run_repair(self, state):
        return self._run("repair", state)

    def run_reviewer(self, state):
        return self._run("reviewer", state)

    def promote(self, state):
        return self._run("promotion", state)


def make_flow(flow_id: str, box: FactsBox, executor: FakeExecutor, *,
              max_repairs: int = 2, control=None, mission_id: int = 1,
              persistence: AppFlowPersistence | None = None) -> MissionFlow:
    persistence = persistence or AppFlowPersistence()
    initial = MissionState(
        id=flow_id, project_id=1, mission_id=mission_id, goal="flow goal",
        max_repairs=max_repairs,
    )
    return MissionFlow(
        initial_state=initial, persistence=persistence, executor=executor,
        facts_provider=box.provider, control=control,
        suppress_flow_events=True, tracing=False,
    )


def fresh_box(**overrides) -> FactsBox:
    facts = MissionFacts(mission_id=1, project_id=1, mission_status="running")
    if overrides:
        facts = replace(facts, **overrides)
    return FactsBox(facts)


def test_happy_path_maps_developer_verify_review_promote():
    box = fresh_box()
    executor = FakeExecutor(box)
    persistence = AppFlowPersistence()
    flow = make_flow("flow-happy", box, executor, persistence=persistence)
    result = flow.kickoff(inputs={})
    assert executor.calls == ["developer", "verification", "reviewer", "promotion"]
    assert result["status"] == "completed"
    assert result["phase"] == "completed"
    assert result["changed_paths"] == ["src/flow.py"]
    assert result["promotion_status"] == "promoted"
    assert result["review_verdict"] == "APPROVE"
    assert flow.state.phase == "completed"
    assert persistence.snapshot_count("flow-happy") >= 4
    run = store.get_flow_run("flow-happy")
    assert run["status"] == "COMPLETED"
    # The real graph ends at the explicit finish node.
    assert run["last_method"] == "finish"


@pytest.mark.parametrize("durable, expected_calls", [
    ({"developer_status": "completed"}, ["verification", "reviewer", "promotion"]),
    ({"developer_status": "completed", "verification_persisted": True,
      "candidate_passed": True, "oracle_passed": True},
     ["reviewer", "promotion"]),
    ({"developer_status": "completed", "verification_persisted": True,
      "candidate_passed": True, "oracle_passed": True,
      "review_verdict": "APPROVE"}, ["promotion"]),
    ({"developer_status": "completed", "verification_persisted": True,
      "candidate_passed": True, "oracle_passed": True,
      "review_verdict": "APPROVE", "promotion_status": "promoted",
      "live_promoted": True}, []),
])
def test_durable_fact_guards_skip_completed_steps(durable, expected_calls):
    box = fresh_box(**durable)
    executor = FakeExecutor(box)
    flow = make_flow("flow-guards", box, executor)
    result = flow.kickoff(inputs={})
    assert executor.calls == expected_calls
    assert result["status"] == "completed"


def test_reviewer_reject_blocks_without_promotion():
    box = fresh_box()
    executor = FakeExecutor(box)
    executor.overrides["reviewer"] = StepResult.ok(review_verdict="REJECT")
    flow = make_flow("flow-reject", box, executor)
    result = flow.kickoff(inputs={})
    assert executor.calls == ["developer", "verification", "reviewer"]
    assert result["status"] == "blocked"
    assert result["error_code"] == "review_rejected"
    assert flow.state.phase == "blocked"
    assert store.get_flow_run("flow-reject")["status"] == "BLOCKED"


def test_bounded_repair_loop_then_success():
    box = fresh_box()
    executor = FakeExecutor(box)
    verification_calls = {"count": 0}
    original = executor.run_verification

    def flaky(state):
        verification_calls["count"] += 1
        if verification_calls["count"] == 1:
            executor.calls.append("verification")
            return StepResult.needs_repair(error="candidate failed")
        return original(state)

    executor.run_verification = flaky
    flow = make_flow("flow-repair", box, executor, max_repairs=2)
    result = flow.kickoff(inputs={})
    assert executor.calls == [
        "developer", "verification", "repair", "verification", "reviewer",
        "promotion",
    ]
    assert result["status"] == "completed"
    assert flow.state.repair_round == 1


def test_repair_budget_exhausted_blocks_without_extra_repair():
    box = fresh_box()
    executor = FakeExecutor(box)
    executor.overrides["verification"] = StepResult.needs_repair(error="still red")
    flow = make_flow("flow-budget", box, executor, max_repairs=1)
    result = flow.kickoff(inputs={})
    assert executor.calls == ["developer", "verification", "repair", "verification"]
    assert "promotion" not in executor.calls and "reviewer" not in executor.calls
    assert result["status"] == "blocked"
    assert result["error_code"] == "repair_budget"
    assert flow.state.phase == "blocked"


def test_stop_at_safe_checkpoint_interrupts_flow():
    box = fresh_box()
    executor = FakeExecutor(box)
    control = RunControl()
    control.request_stop("operator stop")
    flow = make_flow("flow-stop", box, executor, control=control)
    result = flow.kickoff(inputs={})
    assert executor.calls == ["developer"]
    assert result["status"] == "interrupted"
    assert flow.state.phase == "interrupted"
    assert flow.state.error_code == "run_stopped"
    assert store.get_flow_run("flow-stop")["status"] == "INTERRUPTED"


def test_flow_writes_no_mission_or_queue_status():
    box = fresh_box()
    mission_id = missions.create_mission(None, "flow mission", "goal")
    executor = FakeExecutor(box)
    persistence = AppFlowPersistence()
    flow = make_flow("flow-no-writes", box, executor, mission_id=mission_id,
                     persistence=persistence)
    boom = AssertionError("flow must not write business status")
    with patch.object(missions, "update_mission_status", side_effect=boom), \
         patch.object(missions, "update_mission_result", side_effect=boom), \
         patch.object(missions, "set_promotion_status", side_effect=boom), \
         patch.object(missions, "mark_mission_started", side_effect=boom), \
         patch.object(store, "update_queue_item", side_effect=boom), \
         patch.object(store, "finish_run", side_effect=boom):
        result = flow.kickoff(inputs={})
    assert result["status"] == "completed"
    mission = missions.get_mission(mission_id)
    assert mission["status"] == "pending"
    assert mission["promotion_status"] is None

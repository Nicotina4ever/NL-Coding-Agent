"""C4b: MissionState(FlowState), size/version guards and derive_phase semantics."""
from __future__ import annotations

import os

import pytest

from nl_coding_agent.flows.state import (
    MAX_STATE_BYTES,
    MissionFacts,
    MissionState,
    StateValidationError,
    derive_phase,
)
from nl_coding_agent.persistence import database, missions


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    database.init_db().close()


def facts(**overrides) -> MissionFacts:
    base = dict(mission_id=7, project_id=3, mission_status="running")
    base.update(overrides)
    return MissionFacts(**base)


def state(**overrides) -> MissionState:
    base = dict(id="flow-abc", project_id=3, mission_id=7, goal="goal")
    base.update(overrides)
    return MissionState(**base)


def test_mission_state_defaults_identity_and_updates():
    item = state()
    assert item.flow_id == "flow-abc"
    assert item.schema_version == 1
    assert item.phase == "planned"
    assert item.repair_round == 0 and item.max_repairs == 2
    updated = item.with_updates(phase="verifying", attempt=1)
    assert updated.phase == "verifying" and updated.attempt == 1
    assert updated.id == item.id
    assert updated.updated_at >= item.updated_at
    assert item.as_durable_dict()["id"] == "flow-abc"


def test_state_validation_and_size_guard():
    with pytest.raises(ValueError):
        state(phase="flying")
    with pytest.raises(ValueError):
        state(schema_version=99)
    with pytest.raises(ValueError):
        MissionState(id="x", attempt=-1)
    with pytest.raises(ValueError):
        MissionState(id="x", repair_round=3, max_repairs=2)
    # Pydantic wraps the model-validator error in ValidationError (a ValueError).
    with pytest.raises(ValueError):
        MissionState(id="x", goal="g", write_scope=["path-" + "x" * 200] * 1400)
    assert MAX_STATE_BYTES == 256 * 1024


def test_mission_facts_from_mapping_keeps_known_fields_and_extra():
    snapshot = MissionFacts.from_mapping({
        "mission_id": 5, "mission_status": "running",
        "verification_persisted": True, "candidate_passed": True,
        "unknown_fact": "kept-as-extra",
    })
    assert snapshot.mission_id == 5
    assert snapshot.verification_persisted is True
    assert snapshot.extra == {"unknown_fact": "kept-as-extra"}
    with pytest.raises(StateValidationError):
        MissionFacts.from_mapping(["not", "a", "dict"])


def test_derive_planned_developing_and_verifying():
    assert derive_phase(state(), facts()).phase == "planned"
    assert derive_phase(state(phase="developing"), facts()).phase == "developing"
    decision = derive_phase(
        state(), facts(developer_status="completed"),
    )
    assert decision.phase == "verifying"
    assert not decision.conflicts


def test_derive_verification_outcomes():
    verifying = derive_phase(state(), facts(
        developer_status="completed", verification_persisted=True,
        candidate_passed=True, oracle_passed=True,
    ))
    assert verifying.phase == "reviewing"
    repairing = derive_phase(state(), facts(
        developer_status="completed", verification_persisted=True,
        candidate_passed=True, oracle_passed=False, repair_round=0, max_repairs=2,
    ))
    assert repairing.phase == "repairing"
    exhausted = derive_phase(state(), facts(
        verification_persisted=True, candidate_passed=False,
        repair_round=2, max_repairs=2,
    ))
    assert exhausted.phase == "blocked"


def test_derive_review_and_promotion_outcomes():
    approving = derive_phase(state(), facts(
        verification_persisted=True, candidate_passed=True,
        oracle_passed=True, review_verdict="APPROVE",
    ))
    assert approving.phase == "promoting"
    rejecting = derive_phase(state(), facts(
        verification_persisted=True, candidate_passed=True,
        oracle_passed=True, review_verdict="REJECT",
    ))
    assert rejecting.phase == "blocked"
    promoted = derive_phase(state(), facts(
        review_verdict="APPROVE", promotion_status="promoted",
        live_promoted=True, promotion_reconciled=True,
    ))
    assert promoted.phase == "completed"


def test_derive_terminal_facts_win_and_conflicts_fail_closed():
    completed = derive_phase(state(), facts(
        mission_status="completed", promotion_status="promoted",
        live_promoted=True,
    ))
    assert completed.phase == "completed"

    missing_promotion = derive_phase(state(), facts(mission_status="completed"))
    assert missing_promotion.phase == "blocked"
    assert missing_promotion.conflicts

    mismatch = derive_phase(state(), facts(mission_id=999))
    assert mismatch.phase == "blocked"
    assert "mission_id mismatch" in mismatch.conflicts

    stale_completed = derive_phase(state(phase="completed"), facts())
    assert stale_completed.phase == "blocked"
    assert stale_completed.conflicts

    interrupted = derive_phase(state(), facts(mission_status="interrupted"))
    assert interrupted.phase == "interrupted"

    # An interrupted phase is resumable, not a contradiction.
    resumed = derive_phase(state(phase="interrupted"), facts(
        developer_status="completed",
    ))
    assert resumed.phase == "verifying"


def test_derive_waiting_approval_overrides_progress():
    decision = derive_phase(state(), facts(
        verification_persisted=True, candidate_passed=True,
        oracle_passed=True, review_verdict="APPROVE", approval_pending=True,
    ))
    assert decision.phase == "waiting_approval"


def test_facts_from_durable_rows():
    mission_id = missions.create_mission(None, "flow mission", "goal")
    developer_task = missions.add_task(
        mission_id, "Implement", "desc", agent_role="developer",
    )
    missions.update_task_status(developer_task, "completed")
    missions.record_verification_run(
        mission_id, developer_task, "verify:candidate", 0, "", "", True,
    )
    missions.record_verification_run(
        mission_id, developer_task, "verify:oracle", 0, "", "", True,
    )
    missions.record_handoff(
        mission_id, "reviewer", "orchestrator", "APPROVE",
        {"verdict": "APPROVE"},
    )
    missions.set_promotion_status(mission_id, "promoted")
    snapshot = MissionFacts.from_durable(mission_id)
    assert snapshot.mission_id == mission_id
    assert snapshot.developer_status == "completed"
    assert snapshot.verification_persisted is True
    assert snapshot.candidate_passed and snapshot.oracle_passed
    assert snapshot.review_verdict == "APPROVE"
    assert snapshot.live_promoted is True
    decision = derive_phase(
        MissionState(id="flow-durable", mission_id=mission_id), snapshot,
    )
    assert decision.phase == "completed"

    with pytest.raises(StateValidationError):
        MissionFacts.from_durable(999999)

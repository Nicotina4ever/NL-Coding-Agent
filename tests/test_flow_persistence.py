"""C4b: app-owned Flow persistence - migrations, atomicity, resume guard, no default store."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nl_coding_agent.flows.persistence import (
    AppFlowPersistence,
    FlowPersistenceError,
    OversizedFlowStateError,
    UnsupportedStateSchemaError,
)
from nl_coding_agent.flows.state import MissionState
from nl_coding_agent.persistence import database
from nl_coding_agent.persistence import supervisor_store as store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    database.init_db().close()


def state(flow_id="flow-persist-1", **overrides) -> MissionState:
    base = dict(id=flow_id, project_id=4, mission_id=2, goal="goal")
    base.update(overrides)
    return MissionState(**base)


def test_flow_migrations_are_additive_and_idempotent():
    database.init_db().close()
    database.init_db().close()
    conn = database.get_connection()
    try:
        tables = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("flow_states", "flow_pending_feedback", "flow_runs"):
            assert table in tables
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(missions)")}
        assert "flow_id" in columns
        indexes = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        for index in ("idx_flow_states_uuid", "idx_flow_runs_mission",
                      "idx_flow_runs_status"):
            assert index in indexes
        with conn:
            conn.execute("INSERT INTO missions (project_id, title, status) "
                         "VALUES (NULL, 'pre-existing', 'pending')")
    finally:
        conn.close()
    database.init_db().close()
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM missions WHERE title='pre-existing'").fetchone()
        assert row is not None
        assert row["flow_id"] is None
    finally:
        conn.close()


def test_save_load_round_trip_latest_snapshot_and_run_row():
    persistence = AppFlowPersistence()
    persistence.init_db()
    persistence.save_state("flow-persist-1", "begin", state(phase="planned"))
    persistence.save_state("flow-persist-1", "verify", state(
        phase="reviewing", verification_ref="v1",
    ))
    loaded = persistence.load_state("flow-persist-1")
    assert loaded is not None
    assert loaded["phase"] == "reviewing"
    assert loaded["verification_ref"] == "v1"
    assert persistence.snapshot_count("flow-persist-1") == 2
    run = store.get_flow_run("flow-persist-1")
    assert run["status"] == "RUNNING"
    assert run["last_method"] == "verify"
    assert run["mission_id"] == 2 and run["project_id"] == 4
    assert run["state_sha256"] == persistence.list_snapshots("flow-persist-1")[-1]["state_sha256"]
    assert persistence.load_state("missing-flow") is None


def test_terminal_status_and_snapshot_pruning():
    persistence = AppFlowPersistence()
    completed = state(
        flow_id="flow-terminal", phase="completed",
        promotion_status="promoted",
    )
    for index in range(56):
        completed = completed.with_updates(attempt=index)
        persistence.save_state("flow-terminal", "finish", completed)
    assert persistence.snapshot_count("flow-terminal") == 50
    run = store.get_flow_run("flow-terminal")
    assert run["status"] == "COMPLETED"
    assert run["finished_at"] is not None


def test_oversized_and_unserializable_states_are_rejected_atomically():
    persistence = AppFlowPersistence()
    persistence.save_state("flow-atomic", "begin", state(flow_id="flow-atomic"))
    before = persistence.snapshot_count("flow-atomic")
    huge = state(flow_id="flow-atomic").with_updates(
        goal="x" * (300 * 1024),
    )
    with pytest.raises(OversizedFlowStateError):
        persistence.save_state("flow-atomic", "huge", huge)
    assert persistence.snapshot_count("flow-atomic") == before
    assert store.get_flow_run("flow-atomic")["last_method"] == "begin"

    with pytest.raises(FlowPersistenceError):
        persistence.save_state("flow-atomic", "bad", {"id": "flow-atomic", "obj": object()})
    with pytest.raises(FlowPersistenceError):
        persistence.save_state("flow-atomic", "bad", "not-a-state")
    with pytest.raises(FlowPersistenceError):
        persistence.save_state("flow-atomic", "bad", {"id": "other-flow"})
    assert persistence.snapshot_count("flow-atomic") == before


def test_newer_state_schema_fails_closed_on_load():
    persistence = AppFlowPersistence()
    conn = database.get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO flow_states (flow_uuid, method_name, timestamp, "
                "state_sha256, state_json) VALUES (?,?,?,?,?)",
                ("flow-newer", "begin", "2026-01-01T00:00:00",
                 "sha", json.dumps({"id": "flow-newer", "schema_version": 99})),
            )
    finally:
        conn.close()
    with pytest.raises(UnsupportedStateSchemaError):
        persistence.load_state("flow-newer")


def test_pending_feedback_round_trip_and_clear():
    from crewai.flow.async_feedback.types import PendingFeedbackContext

    persistence = AppFlowPersistence()
    context = PendingFeedbackContext(
        flow_id="flow-pending", flow_class="tests.MissionFlow",
        method_name="review", method_output={"verdict": "APPROVE"},
        message="approve?", emit=["approved", "rejected"],
    )
    item = state(flow_id="flow-pending", phase="waiting_approval")
    persistence.save_pending_feedback("flow-pending", context, item)
    loaded = persistence.load_pending_feedback("flow-pending")
    assert loaded is not None
    loaded_state, loaded_context = loaded
    assert loaded_state["phase"] == "waiting_approval"
    assert loaded_context.flow_id == "flow-pending"
    assert loaded_context.method_name == "review"
    assert store.get_flow_run("flow-pending")["status"] == "PAUSED_WAITING_APPROVAL"
    persistence.clear_pending_feedback("flow-pending")
    assert persistence.load_pending_feedback("flow-pending") is None


def test_persistence_never_uses_crewai_default_store(tmp_path, monkeypatch):
    from crewai.flow.persistence import factory

    def _forbidden():
        raise AssertionError("default_flow_persistence must never be used")

    monkeypatch.setattr(factory, "default_flow_persistence", _forbidden)
    local_app_data = tmp_path / "localappdata"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    persistence = AppFlowPersistence()
    persistence.save_state("flow-nodflt", "begin", state(flow_id="flow-nodflt"))
    assert persistence.load_state("flow-nodflt")["id"] == "flow-nodflt"
    assert not (local_app_data / "CrewAI").exists()
    assert not (local_app_data / "CrewAI" / "flow_states.db").exists()


def test_migration_preserves_rows_and_flow_link_helpers(tmp_path):
    from nl_coding_agent.persistence.missions import (
        create_mission, find_mission_by_flow_id, get_mission, get_mission_flow,
        set_mission_flow,
    )

    mission_id = create_mission(None, "linked", "goal")
    assert get_mission_flow(mission_id) is None
    set_mission_flow(mission_id, "flow-link-1")
    assert get_mission_flow(mission_id) == "flow-link-1"
    assert find_mission_by_flow_id("flow-link-1")["id"] == mission_id
    database.init_db().close()
    assert get_mission(mission_id)["flow_id"] == "flow-link-1"
    set_mission_flow(mission_id, None)
    assert get_mission_flow(mission_id) is None


def test_full_flow_writes_no_crewai_default_storage(tmp_path, monkeypatch):
    """A real Flow[MissionState] run must never fall back to the CrewAI store."""
    from crewai.flow.persistence import factory
    from nl_coding_agent.flows.mission_flow import MissionFlow
    from nl_coding_agent.flows.state import MissionFacts

    def _forbidden():
        raise AssertionError("default_flow_persistence must never be used")

    monkeypatch.setattr(factory, "default_flow_persistence", _forbidden)
    local_app_data = tmp_path / "localappdata"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    flow_id = "flow-no-default-store"
    facts = MissionFacts(
        mission_id=2, project_id=4, mission_status="running",
        developer_status="completed", verification_persisted=True,
        candidate_passed=True, oracle_passed=True, review_verdict="APPROVE",
        promotion_status="promoted", live_promoted=True,
        promotion_reconciled=True,
    )
    flow = MissionFlow(
        initial_state=MissionState(id=flow_id, project_id=4, mission_id=2),
        persistence=AppFlowPersistence(),
        facts_provider=lambda _state: facts,
        suppress_flow_events=True, tracing=False,
    )
    result = flow.kickoff(inputs={"id": flow_id})
    assert result["status"] == "completed"
    assert not (local_app_data / "CrewAI").exists()


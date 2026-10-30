"""Reliability acceptance for unexpected executor/Flow failures and reconciliation.

These tests inject exceptions at three distinct boundaries:
1. before the stage executor prepared any task/attempt;
2. after a task was created and marked running, before its attempt was recorded;
3. after the Flow started but before it could finalize, forcing the Supervisor path.

They also prove that reconciliation finalizes a provably abandoned run but never
touches a Flow still owned by a live process.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.app.services import AppServices
from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
from nl_coding_agent.persistence import missions
from nl_coding_agent.persistence import supervisor_store as store

DEVELOPER = "ollama/qwen2.5-coder:7b-instruct-q4_K_M"
REVIEWER = "ollama/qwen2.5-coder:7b-instruct-q4_K_M"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8")
    services = AppServices()
    opened = services.open_project(root)
    try:
        yield services, opened, root
    finally:
        services._db.close()


def _mission(project, title: str = "reliability") -> int:
    _, opened, _ = project
    return missions.create_mission(
        int(opened["id"]), title,
        "Update src/app.py to add sub(a, b) returning a - b; preserve add.",
    )


def _supervisor(project, *, pipeline: str = "flow") -> Supervisor:
    _, opened, root = project
    config = SupervisorConfig(
        mode="automatic", pipeline=pipeline,
        developer_model=DEVELOPER, reviewer_model=REVIEWER,
        debug_model=DEVELOPER, architect_model=DEVELOPER,
        max_attempts_per_requirement=2,
    )
    return Supervisor(root, project_id=int(opened["id"]), config=config)


def _execution_errors(services, mission_id: int) -> list[dict]:
    details = services.get_mission_details(mission_id) or {}
    return [item for item in details.get("execution_errors", [])
            if str(item.get("kind")) == "execution_error"]


def test_prepare_crash_before_any_task_attempt_is_persisted(project, monkeypatch):
    services, opened, root = project
    mission_id = _mission(project)
    supervisor = _supervisor(project)

    from nl_coding_agent.agents.supervisor_executor import SupervisorMissionExecutor

    def crash_prepare(self):
        raise RuntimeError("injected prepare crash before task planning")

    monkeypatch.setattr(SupervisorMissionExecutor, "prepare", crash_prepare)
    result = supervisor._invoke_flow_mission(mission_id, None)

    assert result["status"] == "failed"
    mission = missions.get_mission(mission_id)
    assert mission["status"] == "failed"
    assert "injected prepare crash" in str(mission.get("result_summary") or "")
    assert missions.get_tasks(mission_id) == []
    errors = _execution_errors(services, mission_id)
    assert errors, "exception evidence must exist even with no task attempt"
    payload = errors[0]["payload"]
    assert payload["source"] in ("flow", "supervisor")
    assert payload["exception_type"] == "RuntimeError"
    assert "injected prepare crash" in payload["traceback"]
    flow = store.get_flow_run(str(mission["flow_id"]))
    assert flow["status"] == "FAILED"
    assert flow["error_code"] == "executor_exception"
    assert flow["error_message"]


def test_crash_after_task_created_before_attempt_records_failed_attempt(project, monkeypatch):
    services, opened, root = project
    mission_id = _mission(project)
    supervisor = _supervisor(project)

    def crash_analysis(self, *args, **kwargs):
        raise RuntimeError("injected analysis crash after planning")

    monkeypatch.setattr(MultiAgentOrchestrator, "_run_planned_analysis", crash_analysis)
    result = supervisor._invoke_flow_mission(mission_id, None)

    assert result["status"] == "failed"
    mission = missions.get_mission(mission_id)
    assert mission["status"] == "failed"
    tasks = missions.get_tasks(mission_id)
    assert tasks, "planner created tasks before the injected crash"
    assert all(str(task["status"]) != "running" for task in tasks)
    errors = _execution_errors(services, mission_id)
    assert errors
    flow = store.get_flow_run(str(mission["flow_id"]))
    assert flow["status"] == "FAILED"
    assert flow["error_message"]


def test_crash_after_task_running_records_attempt_and_evidence(project, monkeypatch):
    services, opened, root = project
    mission_id = _mission(project)
    supervisor = _supervisor(project)

    def crash_developer(self, mission_id_arg, tasks, goal, model_name, baseline, stage, **kwargs):
        developer = next(task for task in tasks if task.get("agent_role") == "developer")
        missions.update_task_status(int(developer["id"]), "running")
        raise RuntimeError("injected developer crash with running task")

    monkeypatch.setattr(MultiAgentOrchestrator, "_run_developer_tasks", crash_developer)
    result = supervisor._invoke_flow_mission(mission_id, None)

    assert result["status"] == "failed"
    tasks = missions.get_tasks(mission_id)
    developer = next(task for task in tasks if task.get("agent_role") == "developer")
    assert developer["status"] == "failed"
    attempts = missions.get_task_attempts(int(developer["id"]))
    assert attempts, "a failed attempt must be created for the running task"
    assert any(str(item.get("status")) == "failed" for item in attempts)
    errors = _execution_errors(services, mission_id)
    assert errors
    flow = store.get_flow_run(str(missions.get_mission(mission_id)["flow_id"]))
    assert flow["status"] == "FAILED"


def test_exception_escaping_flow_kickoff_finalizes_supervisor_and_flow(project, monkeypatch):
    services, opened, root = project
    mission_id = _mission(project)
    supervisor = _supervisor(project)

    from nl_coding_agent.flows.mission_flow import MissionFlow

    def crash_kickoff(self, *args, **kwargs):
        raise RuntimeError("injected crash escaping MissionFlow.kickoff")

    monkeypatch.setattr(MissionFlow, "kickoff", crash_kickoff)
    result = supervisor._invoke_flow_mission(mission_id, None)

    assert result["status"] == "failed"
    mission = missions.get_mission(mission_id)
    assert mission["status"] == "failed"
    assert "injected crash escaping" in str(mission.get("result_summary") or "")
    flow = store.get_flow_run(str(mission["flow_id"]))
    assert flow["status"] == "FAILED"
    assert flow["error_code"] == "executor_exception"
    errors = _execution_errors(services, mission_id)
    assert any(item["payload"]["source"] == "flow_kickoff" for item in errors)


def _running_mission_with_flow(project, *, flow_id: str, owner_pid: int | None) -> tuple[int, int, str]:
    _, opened, _ = project
    mission_id = missions.create_mission(int(opened["id"]), "abandoned", "work")
    task_id = missions.add_task(mission_id, "dev", "work", "developer", write_paths=["src/app.py"])
    missions.mark_mission_started(mission_id)
    missions.update_task_status(task_id, "running")
    missions.set_mission_flow(mission_id, flow_id)
    store.start_flow_run(
        flow_id, int(opened["id"]), mission_id=mission_id, pipeline="mission",
        owner_pid=owner_pid, owner_id="test-owner",
    )
    return mission_id, task_id, flow_id


def test_reconciliation_finalizes_dead_owner_flow(project):
    services, opened, root = project
    mission_id, task_id, flow_id = _running_mission_with_flow(
        project, flow_id="flow-dead-owner", owner_pid=999_999_999,
    )
    actions = store.reconcile_flow_runs(
        project_id=int(opened["id"]), active_flow_ids=(), now="2026-10-30T12:00:00+00:00",
    )
    assert any("flow-dead-owner" in action for action in actions)
    flow = store.get_flow_run(flow_id)
    assert flow["status"] == "INTERRUPTED"
    assert flow["error_code"] == "abandoned"
    assert flow["finished_at"]
    mission = missions.get_mission(mission_id)
    assert mission["status"] == "interrupted"
    assert "abandoned" in str(mission.get("result_summary") or "").lower()
    task = missions.get_task(task_id)
    assert task["status"] == "failed"
    evidence = [item for item in store.list_evidence(mission_id)
                if item["kind"] == "reconciliation"]
    assert evidence
    assert evidence[0]["payload"]["previous_owner_pid"] == 999_999_999


def test_supervisor_reconcile_uses_the_same_durable_flow_recovery(project):
    services, opened, root = project
    mission_id, _task_id, flow_id = _running_mission_with_flow(
        project, flow_id="flow-supervisor-reconcile", owner_pid=999_999_999,
    )
    supervisor = _supervisor(project)
    actions = supervisor._reconcile_flow_runs()
    assert any("flow-supervisor-reconcile" in action for action in actions)
    assert store.get_flow_run(flow_id)["status"] == "INTERRUPTED"
    assert missions.get_mission(mission_id)["status"] == "interrupted"


def test_reconciliation_never_touches_live_owner_or_active_flow(project):
    services, opened, root = project
    live_pid = os.getpid()
    mission_id, task_id, flow_id = _running_mission_with_flow(
        project, flow_id="flow-live-owner", owner_pid=live_pid,
    )
    actions = store.reconcile_flow_runs(
        project_id=int(opened["id"]), active_flow_ids=(), now="2026-10-30T12:00:00+00:00",
    )
    assert actions == []
    assert store.get_flow_run(flow_id)["status"] == "RUNNING"
    assert missions.get_mission(mission_id)["status"] == "running"

    second_mission, second_task, second_flow = _running_mission_with_flow(
        project, flow_id="flow-active-map", owner_pid=999_999_999,
    )
    actions = store.reconcile_flow_runs(
        project_id=int(opened["id"]), active_flow_ids=[second_flow],
        now="2026-10-30T12:00:00+00:00",
    )
    assert actions == []
    assert store.get_flow_run(second_flow)["status"] == "RUNNING"
    assert missions.get_mission(second_mission)["status"] == "running"
    assert missions.get_task(second_task)["status"] == "running"


def test_terminal_mission_finalizes_stale_flow_row_without_touching_mission(project):
    services, opened, root = project
    mission_id, _task_id, flow_id = _running_mission_with_flow(
        project, flow_id="flow-terminal-mission", owner_pid=999_999_999,
    )
    missions.update_mission_status(mission_id, "failed")
    actions = store.reconcile_flow_runs(
        project_id=int(opened["id"]), active_flow_ids=(), now="2026-10-30T12:00:00+00:00",
    )
    assert any("flow-terminal-mission" in action for action in actions)
    flow = store.get_flow_run(flow_id)
    assert flow["status"] == "FAILED"
    assert missions.get_mission(mission_id)["status"] == "failed"

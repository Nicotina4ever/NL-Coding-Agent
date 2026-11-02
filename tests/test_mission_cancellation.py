"""Durable cancellation across clients without overriding automatic recovery."""
import pytest

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.core.run_control import RunControl, RunStopped, acknowledge_mission_resume
from nl_coding_agent.persistence import database
from nl_coding_agent.persistence.missions import create_mission, get_mission, update_mission_status


@pytest.fixture
def mission(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    root.mkdir()
    services = AppServices()
    project = services.open_project(root)
    mid = create_mission(project["id"], "Task", "Update calculation")
    yield services, project, mid
    services._db.close()


def test_cancel_is_durable_and_scoped_without_mutating_source(mission):
    services, project, mid = mission
    with pytest.raises(ValueError, match="selected project"):
        services.cancel_mission(mid, project_id=project["id"] + 1)
    assert not database.get_setting("mission.stop." + str(mid), "")
    result = services.cancel_mission(mid, project_id=project["id"])
    assert result["accepted"] and result["cooperative"]
    control = RunControl()
    with control.observe_mission_stop(mid):
        with pytest.raises(RunStopped):
            control.checkpoint("before-model")
    assert get_mission(mid)["status"] == "pending"  # Request alone is not completion.
    control.clear_stop()
    control.checkpoint("another-mission")  # The previous mission's poll hook was removed.


def test_automatic_supervisor_recovery_preserves_stop(mission, monkeypatch):
    from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
    services, project, mid = mission
    services.cancel_mission(mid, project_id=project["id"])
    update_mission_status(mid, "interrupted")
    supervisor = Supervisor(project["root"], project_id=project["id"], config=SupervisorConfig())
    monkeypatch.setattr(supervisor, "_invoke_orchestrator",
                        lambda *args: supervisor.control.checkpoint("before-model"))
    with pytest.raises(RunStopped):
        supervisor._invoke_mission(mid, None)
    assert database.get_setting("mission.stop." + str(mid), "")
    acknowledge_mission_resume(mid, project_id=project["id"])
    supervisor.control.clear_stop()
    supervisor._invoke_mission(mid, None)
    assert database.get_setting("mission.stop." + str(mid), "") == ""


def test_resume_cannot_clear_stop_while_writer_holds_lock(mission):
    from nl_coding_agent.core.mission_lock import mission_lock, MissionLockError
    services, project, mid = mission
    services.cancel_mission(mid, project_id=project["id"])
    update_mission_status(mid, "interrupted")
    with mission_lock(mid):
        with pytest.raises(MissionLockError):
            acknowledge_mission_resume(mid, project_id=project["id"])
    assert database.get_setting("mission.stop." + str(mid), "")


def test_terminal_mission_not_changed_by_cancel(mission):
    services, project, mid = mission
    update_mission_status(mid, "completed")
    assert not services.cancel_mission(mid, project_id=project["id"])["accepted"]
    assert not database.get_setting("mission.stop." + str(mid), "")


def test_wrong_root_cannot_consume_owner_cancellation(mission, tmp_path):
    services, project, mid = mission
    services.cancel_mission(mid, project_id=project["id"])
    update_mission_status(mid, "interrupted")
    with pytest.raises(ValueError, match="requested project"):
        services.run_mission(mid, tmp_path / "other")
    assert database.get_setting("mission.stop." + str(mid), "")


def test_wall_time_deadline_is_enforced_only_at_checkpoints(mission):
    """mission_wall_time_s used to be descriptive; it now stops at a safe boundary."""
    clock = [0.0]
    control = RunControl(clock=lambda: clock[0])
    control.set_deadline(1800)
    control.checkpoint("start")  # inside budget
    clock[0] = 1801.0
    with pytest.raises(RunStopped) as excinfo:
        control.checkpoint("after-model")
    assert "wall-time" in str(excinfo.value).lower()
    assert control.deadline_exceeded
    # Resumption clears the deadline so the next run is not immediately stopped.
    control.clear_deadline()
    assert control.deadline_remaining_s is None
    control.checkpoint("resumed")


def test_supervisor_applies_and_clears_the_configured_wall_time(mission, monkeypatch):
    from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
    services, project, mid = mission
    supervisor = Supervisor(
        project["root"], project_id=project["id"],
        config=SupervisorConfig(mission_wall_time_s=42))
    seen = {}

    def invoke(mission_id, goal):
        seen["remaining"] = supervisor.control.deadline_remaining_s
        return {"status": "completed", "mission_id": mission_id}

    monkeypatch.setattr(supervisor, "_invoke_orchestrator", invoke)
    result = supervisor._invoke_mission(mid, None)
    assert result["status"] == "completed"
    assert seen["remaining"] is not None
    assert 0 < seen["remaining"] <= 42
    assert supervisor.control.deadline_remaining_s is None

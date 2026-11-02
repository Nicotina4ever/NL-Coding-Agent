from datetime import datetime
from pathlib import Path

import pytest

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.persistence import database
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_mission,
    update_mission_status,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    root.mkdir()
    source = root / "keep.txt"
    source.write_text("project source", encoding="utf-8")
    services = AppServices()
    registered = services.open_project(root)
    yield services, registered, source
    services._db.close()


def test_pending_mission_can_be_deleted_without_archiving(project, tmp_path):
    services, registered, source = project
    mission_id = create_mission(registered["id"], "Planned", "Not started")
    baseline = tmp_path / "state" / "mission_baselines" / f"{mission_id}.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text("{}", encoding="utf-8")
    database.set_setting(f"mission.stop.{mission_id}", "stale stop")
    database.set_setting(f"mission.steer.{mission_id}", "stale steering")

    deleted = services.delete_mission(mission_id, project_id=registered["id"])

    assert deleted["status"] == "pending"
    assert get_mission(mission_id) is None
    assert not baseline.exists()
    assert database.get_setting(f"mission.stop.{mission_id}", "") == ""
    assert database.get_setting(f"mission.steer.{mission_id}", "") == ""
    assert source.read_text(encoding="utf-8") == "project source"


def test_batch_delete_is_atomic_and_refuses_running_missions(project):
    services, registered, _ = project
    first = create_mission(registered["id"], "Ready", "Not started")
    second = create_mission(registered["id"], "Running", "Do work")
    update_mission_status(second, "running")

    with pytest.raises(ValueError, match="Stop running"):
        services.delete_missions([first, second], project_id=registered["id"])

    assert get_mission(first) is not None
    assert get_mission(second)["status"] == "running"


def test_delete_removes_disposable_staging_but_keeps_project_files(project, tmp_path):
    """Deleting a mission must not leave candidate copies behind nor touch live files."""
    services, registered, source = project
    mission_id = create_mission(registered["id"], "Staged", "Do work")
    staging = Path(registered["root"]) / "data" / "staging" / f"mission-{mission_id}-abc"
    staging.mkdir(parents=True)
    (staging / "calc.py").write_text("candidate copy", encoding="utf-8")

    services.delete_mission(mission_id, project_id=registered["id"])

    assert not staging.exists()
    assert source.read_text(encoding="utf-8") == "project source"
    assert get_mission(mission_id) is None


def test_delete_keeps_staging_with_unreconciled_promotion_journal(project):
    """A journaled stage is recovery evidence, not disposable garbage."""
    services, registered, _ = project
    mission_id = create_mission(registered["id"], "Journaled", "Do work")
    staging = Path(registered["root"]) / "data" / "staging" / f"mission-{mission_id}-def"
    staging.mkdir(parents=True)
    (staging / "promotion-journal.json").write_text("{}", encoding="utf-8")

    services.delete_mission(mission_id, project_id=registered["id"])

    assert staging.is_dir()


def test_delete_cleans_goal_links_and_resets_milestone(project):
    services, registered, _ = project
    mission_id = create_mission(registered["id"], "Goal mission", "Complete milestone")
    update_mission_status(mission_id, "completed")
    now = datetime.now().isoformat(timespec="seconds")
    with database.get_connection() as conn:
        goal_id = conn.execute(
            "INSERT INTO goals(project_id,title,objective,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (registered["id"], "Goal", "Objective", "completed", now, now),
        ).lastrowid
        milestone_id = conn.execute(
            "INSERT INTO milestones(goal_id,title,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?)",
            (goal_id, "Milestone", "completed", now, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO goal_missions(goal_id,milestone_id,mission_id,role,created_at) "
            "VALUES(?,?,?,?,?)",
            (goal_id, milestone_id, mission_id, "primary", now),
        )
        conn.commit()

    services.delete_mission(mission_id, project_id=registered["id"])

    with database.get_connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM goal_missions WHERE mission_id=?", (mission_id,)
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT status FROM milestones WHERE id=?", (milestone_id,)
        ).fetchone()[0] == "pending"
        assert conn.execute(
            "SELECT status FROM goals WHERE id=?", (goal_id,)
        ).fetchone()[0] == "active"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

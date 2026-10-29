"""A promoted candidate remains reviewable after disposable stage cleanup."""
from pathlib import Path

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.core import promotion
from nl_coding_agent.persistence.missions import create_mission, set_mission_staging


def test_retained_candidate_diff_after_terminal_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "project"
    root.mkdir()
    (root / "calc.py").write_text("value = 1\n")
    services = AppServices()
    try:
        project = services.open_project(root)
        mid = create_mission(project["id"], "Task", "Update calc.py")
        stage = promotion.begin_stage(root, mid, ["calc.py"])
        set_mission_staging(mid, str(stage.stage_dir))
        (stage.workspace / "calc.py").write_text("value = 2\n")
        before = services.mission_candidate_diff(mid, project_id=project["id"])
        promotion.cleanup_after_terminal(stage, mission_status="completed")
        assert not stage.stage_dir.exists()
        result = services.mission_candidate_diff(mid, project_id=project["id"])
        assert result["retained"] and result["diff"] == before["diff"]
        assert result["changed_paths"] == ["calc.py"]
        assert (root / "calc.py").read_text() == "value = 1\n"
    finally:
        services._db.close()

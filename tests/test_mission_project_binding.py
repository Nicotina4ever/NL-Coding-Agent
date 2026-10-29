"""Mission execution must preserve project identity and project provider policy."""
from pathlib import Path

import pytest

from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.agents.crew_backend import CrewRuntimeRefusedError
from nl_coding_agent.core import permissions
from nl_coding_agent.core.promotion import GateFailure
from nl_coding_agent.persistence.missions import create_mission, get_mission, get_tasks
from nl_coding_agent.projects.registry import open_project


@pytest.fixture
def projects(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    result = []
    for name in ("owner", "other"):
        root = tmp_path / name
        root.mkdir()
        (root / "calc.py").write_text("value = 1\n")
        result.append(open_project(root))
    return result


def test_wrong_project_is_denied_before_tasks_or_staging(projects):
    owner, other = projects
    mission_id = create_mission(owner["id"], "Modify calculation", "Update calc.py")
    before = get_mission(mission_id)
    result = MultiAgentOrchestrator(other["root"]).run_mission(mission_id)
    assert result["status"] == "blocked"
    assert "requested project" in result["error"]
    assert get_tasks(mission_id) == []
    assert get_mission(mission_id) == before
    assert not (Path(other["root"]) / "data/staging").exists()


def test_explicit_wrong_policy_identity_is_denied(projects):
    owner, other = projects
    mission_id = create_mission(owner["id"], "Calculation", "Update calc.py")
    orch = MultiAgentOrchestrator(owner["root"], project_id=other["id"])
    with pytest.raises(GateFailure, match="requested project"):
        orch._assert_harness_mission(get_mission(mission_id))


def test_cli_resume_refuses_other_project_without_changing_mission(projects):
    from nl_coding_agent.cli import main

    owner, other = projects
    mission_id = create_mission(owner["id"], "Calculation", "Update calc.py")
    before = get_mission(mission_id)
    with pytest.raises(SystemExit, match="different project"):
        main(["mission", "--project", other["root"], "--resume", str(mission_id)])
    assert get_mission(mission_id) == before


def test_implicit_identity_uses_project_cloud_denial_before_llm(projects):
    owner, _ = projects
    permissions.grant(permissions.CLOUD)
    permissions.revoke(permissions.CLOUD, project_id=owner["id"])
    mission_id = create_mission(owner["id"], "Calculation", "Update calc.py")
    orch = MultiAgentOrchestrator(owner["root"])
    # Exercise the same binding used by both sequential and Flow execution.
    orch._assert_harness_mission(get_mission(mission_id))
    assert orch.project_id == owner["id"]
    with pytest.raises(CrewRuntimeRefusedError, match="cloud|CLOUD"):
        orch._call_model("Implementation Developer", "ollama/gpt-oss:120b-cloud", "Update calc.py",
                         goal="Modify calculation", backstory="Developer", expected_output="Diff")


@pytest.mark.parametrize("scope", [permissions.READ, permissions.WRITE, permissions.EXECUTE])
def test_direct_mission_respects_revoked_execution_policy(projects, monkeypatch, scope):
    owner, _ = projects
    permissions.revoke(scope, project_id=owner["id"])
    mission_id = create_mission(owner["id"], "Calculation", "Update calc.py")
    orch = MultiAgentOrchestrator(owner["root"])
    calls = []
    monkeypatch.setattr(orch, "_call_model", lambda *args, **kw: calls.append(args))
    result = orch.run_mission(mission_id)
    assert result["status"] == "blocked", result
    assert scope.upper() in result["error"]
    assert calls == []
    assert get_tasks(mission_id) == []
    assert get_mission(mission_id)["staging_dir"] is None
    assert (Path(owner["root"]) / "calc.py").read_text() == "value = 1\n"

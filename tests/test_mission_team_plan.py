"""Proportional mission team policy and read-only analysis tools (no model calls)."""
from pathlib import Path

from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.app.services import AppServices
from nl_coding_agent.persistence.missions import create_mission
from nl_coding_agent.tools.crew_tools import get_project_tools


def _project(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (root / "src" / "stats.py").write_text("# stats\n")
    (root / "tests" / "test_calc.py").write_text("")
    services = AppServices()
    project = services.open_project(root)
    return services, project, root


def _roles(plan):
    return [task["agent_role"] for task in plan]


def test_single_file_mission_keeps_three_role_team(tmp_path, monkeypatch):
    services, project, root = _project(tmp_path, monkeypatch)
    try:
        goal = "In src/calc.py add sub(a, b) returning a - b. Change only src/calc.py."
        mission_id = create_mission(project["id"], "single", goal)
        plan = MultiAgentOrchestrator(root, project_id=project["id"])._plan_tasks(mission_id, goal)
        assert _roles(plan) == ["developer", "tester", "reviewer"]
        assert plan[0]["depends_on"] == []
        assert plan[1]["depends_on"] == [plan[0]["id"]]
        assert plan[2]["depends_on"] == [plan[1]["id"]]
    finally:
        services._db.close()


def test_tests_only_do_not_force_an_architect(tmp_path, monkeypatch):
    services, project, root = _project(tmp_path, monkeypatch)
    try:
        goal = ("Change src/calc.py and its tests/test_calc.py for the new sub function. "
                "Change only src/calc.py and tests/test_calc.py.")
        mission_id = create_mission(project["id"], "source+test", goal)
        plan = MultiAgentOrchestrator(root, project_id=project["id"])._plan_tasks(mission_id, goal)
        assert _roles(plan) == ["developer", "developer", "tester", "reviewer"]
        assert plan[0]["write_paths"] == ["src/calc.py"]
        assert plan[1]["write_paths"] == ["tests/test_calc.py"]
        assert plan[1]["depends_on"] == [plan[0]["id"]]
        assert plan[2]["depends_on"] == [plan[1]["id"]]
    finally:
        services._db.close()


def test_multi_file_mission_adds_read_only_architect(tmp_path, monkeypatch):
    services, project, root = _project(tmp_path, monkeypatch)
    try:
        goal = ("In src/calc.py add sub(a, b). In src/stats.py add mean(values). "
                "Change only src/calc.py and src/stats.py.")
        mission_id = create_mission(project["id"], "multi", goal)
        plan = MultiAgentOrchestrator(root, project_id=project["id"])._plan_tasks(mission_id, goal)
        assert _roles(plan) == ["architect", "developer", "developer", "tester", "reviewer"]
        assert plan[0]["write_paths"] == []
        assert plan[1]["depends_on"] == [plan[0]["id"]]
        assert plan[2]["depends_on"] == [plan[1]["id"]]
        assert plan[3]["depends_on"] == [plan[2]["id"]]
        assert plan[4]["depends_on"] == [plan[3]["id"]]
        assert plan[1]["write_paths"] == ["src/calc.py"]
        assert plan[2]["write_paths"] == ["src/stats.py"]
    finally:
        services._db.close()


def test_security_objective_adds_auditor_to_the_team(tmp_path, monkeypatch):
    services, project, root = _project(tmp_path, monkeypatch)
    try:
        goal = ("Audit dependency and security risks while adding sub to src/calc.py and "
                "mean to src/stats.py. Change only src/calc.py and src/stats.py.")
        mission_id = create_mission(project["id"], "security", goal)
        plan = MultiAgentOrchestrator(root, project_id=project["id"])._plan_tasks(mission_id, goal)
        assert _roles(plan) == ["architect", "auditor", "developer", "developer",
                                "tester", "reviewer"]
        assert plan[1]["depends_on"] == [plan[0]["id"]]
        assert plan[2]["depends_on"] == [plan[1]["id"]]
        assert plan[3]["depends_on"] == [plan[2]["id"]]
        assert plan[4]["depends_on"] == [plan[3]["id"]]
    finally:
        services._db.close()


def test_read_only_analysis_tools_exclude_writes(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    tools = get_project_tools(root, read_only=True)
    names = {getattr(tool, "name", "") for tool in tools}
    assert names == {"read_file", "list_dir"}
    writable = {getattr(tool, "name", "") for tool in get_project_tools(root)}
    assert {"read_file", "list_dir", "write_file", "patch_file"} <= writable
    assert {"run_command", "run_tests", "git_status", "git_diff"} <= writable

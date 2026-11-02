"""Proportional mission team policy and read-only analysis tools (no model calls)."""
import json
from pathlib import Path
from types import SimpleNamespace

from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.agents.crew_backend import FakeCrewRuntime
from nl_coding_agent.app.services import AppServices, _team_plan_documents
from nl_coding_agent.core import permissions
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_handoffs,
    get_mission,
    get_task_attempts,
    get_tasks,
)
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


def test_team_plan_scan_prunes_runtime_data_and_nested_repositories(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "README.md").write_text("# project", encoding="utf-8")
    (root / "python").mkdir()
    (root / "python" / "python312._pth").write_text("python312.zip", encoding="utf-8")
    (root / "python" / "Lib").mkdir()
    (root / "python" / "Lib" / "runtime.py").write_text("runtime", encoding="utf-8")
    (root / "da_eliminare" / "vendor").mkdir(parents=True)
    (root / "da_eliminare" / "vendor" / "reference.py").write_text("vendor", encoding="utf-8")
    (root / "nested" / ".git").mkdir(parents=True)
    (root / "nested" / "project.py").write_text("nested checkout", encoding="utf-8")

    docs = _team_plan_documents(root)

    assert [item["path"] for item in docs] == ["README.md"]


def test_team_plan_timeout_returns_deterministic_team(tmp_path, monkeypatch):
    services, project, _ = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(services, "discover_models", lambda **kwargs: SimpleNamespace(
        providers=[SimpleNamespace(
            provider_id="ollama", label="Ollama", models=[SimpleNamespace(
                name="local-model", size_gb=1.0, loaded=False, capabilities=())]
        )]
    ))
    from nl_coding_agent.core import resource_monitor
    monkeypatch.setattr(resource_monitor, "snapshot", lambda: {"gpus": [], "ram": {}})

    def timeout(*args, **kwargs):
        raise TimeoutError("model timed out")

    monkeypatch.setattr(services, "_generate_with_fallback", timeout)
    try:
        result = services.team_plan(project["id"], "ollama/local-model")
        assert result["fallback"] is True
        assert result["analysis_error"] == "TimeoutError: model timed out"
        assert len(result["roles"]) == 5
        assert all(item["model"] == "ollama/local-model" for item in result["roles"])
    finally:
        services._db.close()


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


def test_generated_team_is_project_scoped_persisted_and_used_in_mission(
        tmp_path, monkeypatch):
    services, project, root = _project(tmp_path, monkeypatch)
    (root / "nl_coding_agent").mkdir()
    (root / "nl_coding_agent" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    plan_roles = [
        {"role_id": "developer", "name": "Project Developer", "role": "developer",
         "model": "ollama/team-dev", "tools": ["read_file", "write_file", "patch_file"],
         "instructions": "Implement only the declared mission scope."},
        {"role_id": "reviewer", "name": "Project Reviewer", "role": "reviewer",
         "model": "ollama/team-review", "tools": ["read_file", "list_dir"],
         "instructions": "Review the staged diff and cite concrete evidence."},
    ]
    monkeypatch.setattr(services, "discover_models", lambda **kwargs: SimpleNamespace(
        providers=[SimpleNamespace(
            provider_id="ollama", label="Ollama", models=[
                SimpleNamespace(name="team-dev", size_gb=1.0, loaded=False, capabilities=()),
                SimpleNamespace(name="team-review", size_gb=1.0, loaded=False, capabilities=()),
            ]
        )]
    ))
    monkeypatch.setattr(services, "_generate_with_fallback", lambda *args, **kwargs: {
        "reply": json.dumps({"summary": "Project-specific implementation and review.",
                             "roles": plan_roles})
    })
    from nl_coding_agent.core import resource_monitor
    monkeypatch.setattr(resource_monitor, "snapshot", lambda: {"gpus": [], "ram": {}})
    try:
        plan = services.team_plan(project["id"], "ollama/team-dev")
        persisted = services.assign_project_team(project["id"], plan["roles"])
        assert persisted["created"] == 2
        assert {item["role_id"] for item in persisted["agents"]} == {"developer", "reviewer"}
        assert all(item["project_id"] == project["id"] and item["team_active"]
                   for item in persisted["agents"])
        assert all("permissions" not in item for item in services.list_custom_agents())
        regenerated = services.assign_project_team(project["id"], plan["roles"])
        assert regenerated["created"] == 0
        assert regenerated["updated"] == 2
        assert len(services.list_custom_agents()) == 2

        for scope in (permissions.READ, permissions.WRITE, permissions.EXECUTE):
            permissions.grant(scope, project_id=project["id"], source="test")
        mission_id = create_mission(
            project["id"], "Team execution", "Add a subtract function to src/calc.py")
        runtime = FakeCrewRuntime({
            "developer": [
                "```write:src/calc.py\ndef add(a, b):\n    return a + b\n\n"
                "def sub(a, b):\n    return a - b\n```"
            ],
            "reviewer": ["APPROVE\nThe staged implementation and verification are sound.\n"],
        })
        orchestrator = MultiAgentOrchestrator(
            root, project_id=project["id"], crew_runtime=runtime)
        result = orchestrator.run_mission(mission_id)

        assert result["status"] == "completed", result
        assert get_mission(mission_id)["status"] == "completed"
        assert [call["role_id"] for call in runtime.calls] == ["developer", "reviewer"]
        calls_by_role = {call["role_id"]: call for call in runtime.calls}
        assert calls_by_role["developer"]["model_name"] == "ollama/team-dev"
        assert calls_by_role["reviewer"]["model_name"] == "ollama/team-review"
        assert "Implement only the declared mission scope." in calls_by_role["developer"]["backstory"]
        assert "Review the staged diff" in calls_by_role["reviewer"]["backstory"]
        assert {tool.name for tool in calls_by_role["developer"]["tools"]} == {
            "read_file", "write_file", "patch_file"}
        assert {tool.name for tool in calls_by_role["reviewer"]["tools"]} == {
            "read_file", "list_dir"}
        assert [task["agent_role"] for task in get_tasks(mission_id)] == [
            "developer", "tester", "reviewer"]
        attempts = get_task_attempts(mission_id)
        assert {attempt["agent_role"] for attempt in attempts} == {
            "developer", "tester", "reviewer"}
        handoffs = get_handoffs(mission_id)
        assert any(item["from_role"] == "developer" and item["to_role"] == "tester"
                   for item in handoffs)
        assert any(item["from_role"] == "reviewer" and item["to_role"] == "orchestrator"
                   for item in handoffs)
    finally:
        services._db.close()

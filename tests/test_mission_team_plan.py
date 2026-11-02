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
    assert names == {"read_file", "list_dir", "search_symbols", "lsp_diagnostics"}
    writable = {getattr(tool, "name", "") for tool in get_project_tools(root)}
    assert {"read_file", "list_dir", "write_file", "patch_file"} <= writable
    assert {"run_command", "run_tests", "git_status", "git_diff",
            "search_symbols", "lsp_diagnostics"} <= writable


def test_team_tool_catalog_matches_runtime_and_editor_tools(tmp_path):
    """Every tool a Supervisor role may keep must exist at runtime (no dead options)."""
    from nl_coding_agent.app.services import _TEAM_ROLE_TOOLS
    from nl_coding_agent.tools.crew_tools import get_project_tools

    root = tmp_path / "project"
    root.mkdir()
    runtime_tools = {getattr(tool, "name", "") for tool in get_project_tools(root)}
    for role_id, tools in _TEAM_ROLE_TOOLS.items():
        assert tools, role_id
        missing = [name for name in tools if name not in runtime_tools]
        assert not missing, f"{role_id} declares tools the runtime does not expose: {missing}"
    # A debugger must be able to read the failing code it is asked to repair.
    assert {"read_file", "list_dir"} <= set(_TEAM_ROLE_TOOLS["debugger"])
    assert "run_tests" in _TEAM_ROLE_TOOLS["debugger"]
    # A developer must be able to self-check before the independent tester runs.
    assert "run_tests" in _TEAM_ROLE_TOOLS["developer"]
    # Read-only roles never get mutation tools.
    for role_id in ("architect", "reviewer", "auditor"):
        assert not ({"write_file", "patch_file"} & set(_TEAM_ROLE_TOOLS[role_id])), role_id


def test_ungoverned_mission_offers_prompted_tools(tmp_path, monkeypatch):
    """When no specialist overrides the role, stages expose the tools their prompt promises."""
    services, project, root = _project(tmp_path, monkeypatch)
    (root / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    for scope in (permissions.READ, permissions.WRITE, permissions.EXECUTE):
        permissions.grant(scope, project_id=project["id"], source="test")
    mission_id = create_mission(
        project["id"], "Developer tool parity", "Add a subtract function to src/calc.py")
    runtime = FakeCrewRuntime({
        "developer": [
            "```write:src/calc.py\ndef add(a, b):\n    return a + b\n\n"
            "def sub(a, b):\n    return a - b\n```"
        ],
        "reviewer": ["APPROVE\nLooks correct.\n"],
    })
    try:
        orchestrator = MultiAgentOrchestrator(
            root, project_id=project["id"], crew_runtime=runtime)
        result = orchestrator.run_mission(mission_id)
        assert result["status"] == "completed", result
        calls_by_role = {call["role_id"]: call for call in runtime.calls}
        developer_tools = {tool.name for tool in calls_by_role["developer"]["tools"]}
        assert {"read_file", "list_dir", "write_file", "patch_file",
                "run_tests", "run_command"} <= developer_tools
        reviewer_tools = {tool.name for tool in calls_by_role["reviewer"]["tools"]}
        assert reviewer_tools == {"read_file", "list_dir", "search_symbols",
                                  "lsp_diagnostics"}
    finally:
        services._db.close()



def test_team_plan_reports_dropped_and_remapped_specialists(tmp_path, monkeypatch):
    services, project, _root = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(services, "discover_models", lambda **kwargs: SimpleNamespace(
        providers=[SimpleNamespace(
            provider_id="ollama", label="Ollama", models=[SimpleNamespace(
                name="local-model", size_gb=1.0, loaded=False, capabilities=())]
        )]
    ))
    monkeypatch.setattr(services, "_generate_with_fallback", lambda *args, **kwargs: {
        "reply": json.dumps({"summary": "team", "roles": [
            {"role_id": "developer", "name": "Core Developer", "role": "developer",
             "model": "ollama/local-model", "instructions": "implement",
             "tools": ["read_file"]},
            {"role_id": "tester", "name": "QA Engineer", "role": "test engineer",
             "model": "ollama/local-model", "instructions": "test",
             "tools": ["read_file"]},
            {"name": "UX Designer", "role": "design", "model": "ollama/local-model",
             "instructions": "design", "tools": ["read_file"]},
        ]})
    })
    from nl_coding_agent.core import resource_monitor
    monkeypatch.setattr(resource_monitor, "snapshot", lambda: {"gpus": [], "ram": {}})
    try:
        result = services.team_plan(project["id"], "ollama/local-model")
    finally:
        services._db.close()
    dropped = {item["name"] for item in result["dropped_roles"]}
    assert "QA Engineer" in dropped
    assert any(item["declared_role_id"] == "" and item["role_id"] == "architect"
               for item in result["remapped_roles"])
    developer = next(item for item in result["roles"] if item["role_id"] == "developer")
    # A writer must never be persisted without its write capability.
    assert {"read_file", "write_file", "patch_file"} <= set(developer["tools"])
    assert "developer" in result["tool_adjustments"]


def test_assigned_team_drives_planned_tasks_and_specialist_routes(tmp_path, monkeypatch):
    """The active team is an operational assignment: auditor/architect get tasks and models."""
    services, project, root = _project(tmp_path, monkeypatch)
    (root / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    plan_roles = [
        {"role_id": "architect", "name": "Project Architect", "role": "architect",
         "model": "ollama/team-arch", "tools": ["read_file", "list_dir"],
         "instructions": "Produce a bounded architectural outline."},
        {"role_id": "auditor", "name": "Risk Auditor", "role": "auditor",
         "model": "ollama/team-audit", "tools": ["read_file"],
         "instructions": "Audit risks and constraints."},
        {"role_id": "developer", "name": "Lead Developer", "role": "developer",
         "model": "ollama/team-dev", "tools": ["read_file"],
         "instructions": "Implement only the declared scope."},
        {"role_id": "reviewer", "name": "Code Reviewer", "role": "reviewer",
         "model": "ollama/team-review", "tools": ["read_file", "list_dir"],
         "instructions": "Review the staged diff."},
        {"role_id": "debugger", "name": "Repair Engineer", "role": "debugger",
         "model": "ollama/team-debug", "tools": ["patch_file"],
         "instructions": "Repair verification failures."},
    ]
    monkeypatch.setattr(services, "discover_models", lambda **kwargs: SimpleNamespace(
        providers=[SimpleNamespace(
            provider_id="ollama", label="Ollama", models=[
                SimpleNamespace(name=name, size_gb=1.0, loaded=False, capabilities=())
                for name in ("team-arch", "team-audit", "team-dev", "team-review",
                             "team-debug")
            ]
        )]
    ))
    monkeypatch.setattr(services, "_generate_with_fallback", lambda *args, **kwargs: {
        "reply": json.dumps({"summary": "project team", "roles": plan_roles})
    })
    from nl_coding_agent.core import resource_monitor
    monkeypatch.setattr(resource_monitor, "snapshot", lambda: {"gpus": [], "ram": {}})
    for scope in (permissions.READ, permissions.WRITE, permissions.EXECUTE):
        permissions.grant(scope, project_id=project["id"], source="test")
    try:
        plan = services.team_plan(project["id"], "ollama/team-dev")
        persisted = services.assign_project_team(project["id"], plan["roles"])
        by_role = {item["role_id"]: item for item in persisted["agents"]}
        assert {"read_file", "write_file", "patch_file"} <= set(by_role["developer"]["tools"])
        assert {"read_file", "write_file", "patch_file"} <= set(by_role["debugger"]["tools"])

        mission_id = create_mission(
            project["id"], "Team mission", "Add a subtract function to src/calc.py")
        runtime = FakeCrewRuntime({
            "architect": ["Architecture: keep src/calc.py API stable."],
            "auditor": ["Audit: no dependencies; keep add() intact."],
            "developer": [
                "```write:src/calc.py\ndef add(a, b):\n    return a + b\n\n"
                "def sub(a, b):\n    return a - b\n```"
            ],
            "reviewer": ["APPROVE\nScope and tests are consistent.\n"],
        })
        orchestrator = MultiAgentOrchestrator(
            root, project_id=project["id"], crew_runtime=runtime)
        result = orchestrator.run_mission(mission_id)
        assert result["status"] == "completed", result

        tasks = get_tasks(mission_id)
        roles = [task["agent_role"] for task in tasks]
        assert roles[:2] == ["architect", "auditor"]
        calls = {call["role_id"]: call for call in runtime.calls}
        assert calls["architect"]["model_name"] == "ollama/team-arch"
        assert calls["auditor"]["model_name"] == "ollama/team-audit"
        assert calls["developer"]["model_name"] == "ollama/team-dev"
        assert calls["reviewer"]["model_name"] == "ollama/team-review"
        # The developer profile declared only read_file; write capability is restored.
        assert {"write_file", "patch_file"} <= {
            tool.name for tool in calls["developer"]["tools"]}
        specialists = {item["role_id"]: item for item in result["specialists"]}
        assert set(specialists) == {"architect", "auditor", "developer", "reviewer",
                                    "debugger"}
        assert specialists["architect"]["task_ids"]
        assert specialists["auditor"]["task_ids"]
        assert specialists["debugger"]["standby"] is True
        assert "verification fails" in specialists["debugger"]["standby_reason"]
    finally:
        services._db.close()


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

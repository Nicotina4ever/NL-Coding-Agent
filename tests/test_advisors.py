"""P3 dynamic advisors: multiple read-only specialists, isolated sub-agent execution."""
from __future__ import annotations

import json

import pytest

from nl_coding_agent.agents.crew_backend import FakeCrewRuntime
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.app.services import AppServices, project_team_agents
from nl_coding_agent.core import permissions
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_handoffs,
    get_mission,
    get_tasks,
)

CALC = "def add(a, b):\n    return a + b\n"
CALC_WITH_DOUBLE = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def double(x):\n    return x * 2\n"
)
TEST = "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


def write_block(rel_path: str, content: str) -> str:
    return "```write:" + rel_path + "\n" + content.rstrip("\n") + "\n```"


@pytest.fixture
def advisor_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "calc.py").write_text(CALC, encoding="utf-8")
    (root / "tests" / "test_calc.py").write_text(TEST, encoding="utf-8")
    services = AppServices()
    project = services.open_project(root)
    for scope in (permissions.READ, permissions.WRITE, permissions.EXECUTE):
        permissions.grant(scope, project_id=project["id"], source="test")
    yield services, project, root
    services._db.close()


def _advisor(name, route, instructions, tools=None):
    return {"role_id": "advisor", "name": name,
            "model": route, "role": name.lower(),
            "instructions": instructions,
            "tools": tools or ["read_file", "list_dir", "git_diff"]}


def test_assign_multiple_advisors_and_reject_ambiguous_duplicates(advisor_env):
    services, project, _root = advisor_env
    result = services.assign_project_team(project["id"], [
        _advisor("Security Advisor", "ollama/advisor-a", "Focus on injection and secrets."),
        _advisor("Performance Advisor", "ollama/advisor-b", "Focus on complexity and IO."),
        {"role_id": "developer", "name": "Dev", "model": "ollama/dev",
         "tools": ["read_file", "write_file", "patch_file", "run_tests"]},
    ])
    assert result["created"] >= 3
    profiles = [item for item in project_team_agents(project["id"])
                if item["role_id"] == "advisor"]
    assert {item["name"] for item in profiles} == {"Security Advisor", "Performance Advisor"}
    with pytest.raises(ValueError):
        services.assign_project_team(project["id"], [
            _advisor("Security Advisor", "ollama/a", "one"),
            _advisor("security advisor", "ollama/b", "two"),
        ])
    with pytest.raises(ValueError):
        services.assign_project_team(project["id"], [
            {"role_id": "developer", "name": "Dev A", "model": "ollama/a"},
            {"role_id": "developer", "name": "Dev B", "model": "ollama/b"},
        ])


def test_mission_runs_isolated_advisors_and_consumes_their_handoffs(advisor_env):
    services, project, root = advisor_env
    services.assign_project_team(project["id"], [
        _advisor("Security Advisor", "ollama/advisor-a", "Focus on injection and secrets."),
        _advisor("Performance Advisor", "ollama/advisor-b", "Focus on complexity and IO."),
        {"role_id": "developer", "name": "Dev", "model": "ollama/dev",
         "tools": ["read_file", "write_file", "patch_file", "run_tests"]},
        {"role_id": "reviewer", "name": "Reviewer", "model": "ollama/rev",
         "tools": ["read_file", "list_dir", "git_diff"]},
    ])
    goal = "In src/calc.py add double(x) returning x * 2. Change only src/calc.py."
    runtime = FakeCrewRuntime({
        "advisor": [
            "```json\n" + json.dumps({
                "summary": "Security review: no secrets in scope.",
                "facts": ["calc.py has no IO"], "decisions": ["keep pure functions"],
                "risks": ["none"], "next_steps": ["add docstring"],
            }) + "\n```",
            "```json\n" + json.dumps({
                "summary": "Performance review: constant time operation.",
                "facts": ["double is O(1)"], "decisions": ["no caching needed"],
                "risks": ["none"], "next_steps": ["keep it simple"],
            }) + "\n```",
        ],
        "developer": [write_block("src/calc.py", CALC_WITH_DOUBLE)],
        "reviewer": ["APPROVE\nAdvisor findings considered; change is minimal.\n"],
    })
    mission_id = create_mission(project["id"], "Advisors mission", goal)
    orchestrator = MultiAgentOrchestrator(root, project_id=project["id"],
                                          crew_runtime=runtime)
    result = orchestrator.run_mission(mission_id, developer_model="ollama/dev",
                                      reviewer_model="ollama/rev",
                                      debug_model="ollama/dev")
    assert result["status"] == "completed", result
    assert result["promotion_status"] == "promoted"
    advisor_calls = [call for call in runtime.calls if call["role_id"] == "advisor"]
    assert len(advisor_calls) == 2
    for call in advisor_calls:
        assert "startup transcript" not in call["prompt"].lower()
    developer_prompts = [call["prompt"] for call in runtime.calls
                         if call["role_id"] == "developer"]
    assert developer_prompts
    joined = "\n".join(developer_prompts)
    assert "ADVISOR Security Advisor" in joined
    assert "ADVISOR Performance Advisor" in joined
    assert "no secrets in scope" in joined
    handoffs = [item for item in get_handoffs(mission_id)
                if item.get("from_role") == "advisor"]
    assert len(handoffs) == 2
    assert {item["payload"]["advisor"] for item in handoffs} == {
        "Security Advisor", "Performance Advisor"}
    assignments = orchestrator._specialist_assignments(get_tasks(mission_id))
    advisory = [item for item in assignments if item.get("advisory")]
    assert len(advisory) == 2
    mission = get_mission(mission_id)
    assert mission["status"] == "completed"

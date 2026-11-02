"""P2: autonomous detection and repair of an error introduced by the agent itself.

Uses the real staged-candidate executor, validator, verifier and promotion code with a
scripted model seam: the developer introduces a semantic regression (syntactically
valid, so the static post-write gate passes), the deterministic tester fails, the
MissionFlow repair branch runs the debugger, verification passes and the candidate is
promoted. A second case proves the static diagnostics hook blocks an introduced syntax
error before the tester.
"""
from __future__ import annotations

import json

import pytest

from nl_coding_agent.agents.crew_backend import FakeCrewRuntime
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.agents.supervisor_executor import SupervisorMissionExecutor
from nl_coding_agent.app.services import AppServices
from nl_coding_agent.core import permissions
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_handoffs,
    get_mission,
    get_verification_runs,
)

CALC_GOOD = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def subtract(a, b):\n    return a - b\n"
)
CALC_REGRESSION = (
    "# src/calc.py\n"
    "def add(a, b):\n    return a + b\n\n\n"
    "def subtract(a, b):\n    # agent regression: sum instead of difference\n    return a + b\n"
)
CALC_FIXED = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def subtract(a, b):\n    return a - b\n\n\n"
    "def double(x):\n    return x * 2\n"
)


def _write_block(path: str, content: str) -> str:
    return "```write:" + path + "\n" + content.rstrip("\n") + "\n```"


@pytest.fixture
def repair_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "calc.py").write_text(CALC_GOOD, encoding="utf-8")
    (root / "tests" / "test_calc.py").write_text(
        "from src.calc import add, subtract\n\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n\n\n"
        "def test_subtract():\n    assert subtract(5, 2) == 3\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# repair fixture\n", encoding="utf-8")
    services = AppServices()
    project = services.open_project(root)
    for scope in (permissions.READ, permissions.WRITE, permissions.EXECUTE):
        permissions.grant(scope, project_id=project["id"], source="test")
    yield services, project, root
    services._db.close()


def _executor(root, project_id, goal, scripts):
    runtime = FakeCrewRuntime(scripts)
    orchestrator = MultiAgentOrchestrator(root, project_id=project_id,
                                          crew_runtime=runtime)
    mission_id = create_mission(project_id, "Agent regression repair", goal)
    executor = SupervisorMissionExecutor(
        orchestrator, mission_id, goal,
        developer_model="ollama/fake-dev", reviewer_model="ollama/fake-review",
        debug_model="ollama/fake-debug",
    )
    return executor, mission_id, runtime


def test_flow_repairs_an_agent_introduced_semantic_error(repair_env):
    services, project, root = repair_env
    goal = ("In src/calc.py add double(x) returning x * 2 and keep existing behaviour. "
            "Change only src/calc.py.")
    executor, mission_id, runtime = _executor(root, project["id"], goal, {
        # First developer turn introduces a regression while adding the feature.
        "developer": [_write_block("src/calc.py", CALC_REGRESSION)],
        "debugger": [_write_block("src/calc.py", CALC_FIXED)],
        "reviewer": ["APPROVE\nThe regression was repaired and double() added.\n"],
    })
    executor.prepare()
    developed = executor.run_developer(None)
    assert developed.status == "ok", developed
    broken = executor.run_verification(None)
    assert broken.status == "needs_repair", broken
    assert (root / "src" / "calc.py").read_text(encoding="utf-8") == CALC_GOOD
    repaired = executor.run_repair(None)
    assert repaired.status == "ok", repaired
    verified = executor.run_verification(None)
    assert verified.status == "ok", verified
    reviewed = executor.run_reviewer(None)
    assert reviewed.status == "ok", reviewed
    assert reviewed.payload.get("review_verdict") == "APPROVE"
    promoted = executor.promote(None)
    assert promoted.status == "ok", promoted
    result = executor.finalize({
        "status": "completed", "review_verdict": "APPROVE",
        "changed_paths": ["src/calc.py"],
    })
    assert result["status"] == "completed", result
    live = (root / "src" / "calc.py").read_text(encoding="utf-8")
    assert "def double" in live and "return a - b" in live
    mission = get_mission(mission_id)
    assert mission["status"] == "completed"
    assert mission["promotion_status"] == "promoted"
    runs = get_verification_runs(mission_id)
    assert any(run["passed"] == 0 for run in runs)
    assert any(run["passed"] == 1 for run in runs)
    handoffs = get_handoffs(mission_id)
    assert any(item["from_role"] == "debugger" and item["to_role"] == "tester"
               for item in handoffs)
    assert any(call["role_id"] == "debugger" for call in runtime.calls)


def test_static_hook_blocks_an_agent_introduced_syntax_error(repair_env):
    services, project, root = repair_env
    goal = "In src/calc.py fix subtract and change only src/calc.py."
    executor, mission_id, _runtime = _executor(root, project["id"], goal, {
        "developer": [_write_block("src/calc.py", "def subtract(a, b)\n    return a - b\n"),
                      _write_block("src/calc.py", "def subtract(a, b)\n    return a - b\n")],
    })
    executor.prepare()
    blocked = executor.run_developer(None)
    assert blocked.status == "blocked", blocked
    message = str(blocked.payload.get("error", "")).lower()
    assert "syntax" in message or "diagnostic" in message
    assert blocked.payload.get("error_code") == "candidate-rejected"
    assert (root / "src" / "calc.py").read_text(encoding="utf-8") == CALC_GOOD
    assert get_mission(mission_id)["status"] == "pending"


def test_static_hook_rejects_invalid_structured_file_before_tester(repair_env):
    """JSON/TOML changes are covered by the post-write hook, not the Python AST gate."""
    services, project, root = repair_env
    (root / "config.json").write_text('{"feature": false}\n', encoding="utf-8")
    goal = "In config.json set the feature flag to true. Change only config.json."
    executor, mission_id, _runtime = _executor(root, project["id"], goal, {
        "developer": ["```write:config.json\n{\"feature\": }\n```"],
    })
    executor.prepare()
    blocked = executor.run_developer(None)
    assert blocked.status == "blocked", blocked
    assert "post-write diagnostics" in str(blocked.payload.get("error", "")).lower()
    assert json.loads((root / "config.json").read_text(encoding="utf-8")) == {"feature": False}
    assert get_mission(mission_id)["status"] == "pending"

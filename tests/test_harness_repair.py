"""Stage-2 evidence: bounded repair loop on staged candidates (NL-BP-065, SH-06).

Fake-model tests only: no Ollama, no CrewAI call, no autonomous self-build run.
The real candidate/oracle suites run in disposable copies of a tiny demo project.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl_coding_agent.agents import orchestrator as orchestrator_module
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.persistence import database
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_handoffs,
    get_mission,
    get_verification_runs,
)
from nl_coding_agent.projects.registry import open_project

CALC_SOURCE = "def add(a, b):\n    return a + b\n"
# The developer's first candidate breaks the existing behaviour and ships a wrong
# subtract: both the candidate and the pinned oracle suites must fail.
BROKEN_SOURCE = (
    "def add(a, b):\n"
    "    return a - b\n"
    "\n"
    "\n"
    "def sub(a, b):\n"
    "    return a + b\n"
)
BROKEN_REPAIR = (
    "def add(a, b):\n"
    "    return a - b\n"
    "\n"
    "\n"
    "def sub(a, b):\n"
    "    return b - a\n"
)
FIXED_SOURCE = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "\n"
    "def sub(a, b):\n"
    "    return a - b\n"
)
TEST_SOURCE = "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
GOAL = "Add a subtract function to src/calc.py"

MODEL_DEVELOPER = "Implementation Developer"
MODEL_DEBUGGER = "Software Debugger"
MODEL_REVIEWER = "Code Reviewer & Quality Gatekeeper"


def write_block(rel_path: str, content: str) -> str:
    """Model output that the staged text-action fallback applies to the workspace."""
    return "```write:" + rel_path + "\n" + content.rstrip("\n") + "\n```"


class ScriptedModel:
    """Scripted fake for the single _call_model seam (no Ollama, no CrewAI call)."""

    def __init__(self, scripts: dict[str, list[str]], hooks=None):
        self.scripts = {role: list(outputs) for role, outputs in scripts.items()}
        self.hooks = hooks or {}
        self.calls: list[dict] = []

    def __call__(
        self,
        role,
        model_name,
        prompt,
        *,
        goal="",
        backstory="",
        expected_output="",
        tools=None,
    ):
        self.calls.append({
            "role": role,
            "model_name": model_name,
            "prompt": prompt,
            "goal": goal,
            "backstory": backstory,
            "expected_output": expected_output,
            "tools": tools,
        })
        hook = self.hooks.get(role)
        if hook is not None:
            hook()
        outputs = self.scripts.get(role)
        if not outputs:
            raise AssertionError(
                "Unexpected model call for role " + repr(role)
                + "; roles so far: " + repr(self.roles)
            )
        return outputs.pop(0)

    @property
    def roles(self) -> list[str]:
        return [call["role"] for call in self.calls]

    def prompts_for(self, role: str) -> list[str]:
        return [call["prompt"] for call in self.calls if call["role"] == role]


def install_fake(orch: MultiAgentOrchestrator, scripts, hooks=None) -> ScriptedModel:
    model = ScriptedModel(scripts, hooks=hooks)
    orch._call_model = model  # instance attribute shadows the real seam
    return model


def new_mission(project_root: Path, goal: str = GOAL) -> int:
    project = open_project(project_root)
    return create_mission(project["id"], "Stage-2 repair evidence", goal)


def stage_dirs(project_root: Path) -> list[Path]:
    root = project_root / "data" / "staging"
    if not root.is_dir():
        return []
    return sorted(path for path in root.glob("mission-*") if path.is_dir())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def verification_passes(mission_id: int) -> tuple[list[bool], list[bool]]:
    runs = get_verification_runs(mission_id)
    candidate = [
        bool(run["passed"]) for run in runs
        if run["command"].startswith("verify:candidate ")
    ]
    oracle = [
        bool(run["passed"]) for run in runs
        if run["command"].startswith("verify:oracle ")
    ]
    return candidate, oracle


@pytest.fixture(autouse=True)
def no_llm_and_bounded_verification(monkeypatch):
    """Any hidden CrewAI/LLM path fails loudly; verification timeouts stay low."""

    def _boom(*args, **kwargs):
        raise AssertionError("_make_llm must not be called: tests install a fake _call_model")

    monkeypatch.setattr(orchestrator_module, "_make_llm", _boom)
    monkeypatch.setattr(orchestrator_module, "VERIFY_TIMEOUT_S", 30)


@pytest.fixture()
def mission_env(tmp_path, monkeypatch):
    """Isolated app data dir: SQLite, mission locks, recovery and evidence live here."""
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setenv("NL_DATA_DIR", str(data))
    database.init_db().close()
    return data


@pytest.fixture()
def project(mission_env, tmp_path):
    """Minimal project whose staged copy can run the real candidate/oracle suites."""
    root = tmp_path / "project"
    package = root / "nl_coding_agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8", newline="")
    src = root / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8", newline="")
    (src / "calc.py").write_text(CALC_SOURCE, encoding="utf-8", newline="")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text(TEST_SOURCE, encoding="utf-8", newline="")
    return root


def test_repair_success_after_failed_verification_promotes_once(project, mission_env):
    mission_id = new_mission(project)
    live_path = project / "src" / "calc.py"
    live_before = read_text(live_path)
    observed: dict[str, str] = {}

    def at_review():
        # Promotion is the last gate: the live tree is still untouched here.
        observed["live_at_review"] = read_text(live_path)

    orch = MultiAgentOrchestrator(project)
    model = install_fake(
        orch,
        {
            MODEL_DEVELOPER: [write_block("src/calc.py", BROKEN_SOURCE)],
            MODEL_DEBUGGER: [write_block("src/calc.py", FIXED_SOURCE)],
            MODEL_REVIEWER: ["APPROVE\nRepaired candidate verified by candidate+oracle suites.\n"],
        },
        hooks={MODEL_REVIEWER: at_review},
    )

    result = orch.run_mission(mission_id)

    assert result["status"] == "completed", result
    assert result["promotion_status"] == "promoted"
    assert observed["live_at_review"] == live_before

    # Exactly one debugger repair; reviewer only after verification passed.
    assert model.roles == [MODEL_DEVELOPER, MODEL_DEBUGGER, MODEL_REVIEWER]
    assert model.roles.count(MODEL_DEBUGGER) == 1
    debugger_prompt = model.prompts_for(MODEL_DEBUGGER)[0]
    assert "TEST FAILURE LOGS" in debugger_prompt
    assert "src/calc.py" in debugger_prompt

    candidate_passes, oracle_passes = verification_passes(mission_id)
    assert candidate_passes == [False, True]
    assert oracle_passes == [False, True]

    live = read_text(live_path)
    assert "return a + b" in live
    assert "return a - b" in live
    assert "return b - a" not in live

    mission = get_mission(mission_id)
    assert mission["status"] == "completed"
    assert mission["promotion_status"] == "promoted"
    assert json.loads(mission["changed_paths"]) == ["src/calc.py"]

    promoted_handoffs = [
        handoff for handoff in get_handoffs(mission_id)
        if (handoff.get("payload") or {}).get("promoted")
    ]
    assert len(promoted_handoffs) == 1
    assert stage_dirs(project) == []

    # SH-06: one economic, delta-only recovery point for the promoted file.
    recovery_path = mission_env / "recovery" / (str(mission_id) + ".json")
    assert recovery_path.is_file()
    recovery = json.loads(read_text(recovery_path))
    assert sorted(recovery["files"].keys()) == ["src/calc.py"]
    assert recovery_path.stat().st_size < 100_000
    assert (mission_env / "verification" / ("mission-" + str(mission_id) + ".json")).is_file()


def test_repair_budget_exhaustion_blocks_without_promotion(project, mission_env, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "MAX_REPAIR_ATTEMPTS", 1)
    mission_id = new_mission(project)
    live_path = project / "src" / "calc.py"
    live_before = read_text(live_path)

    orch = MultiAgentOrchestrator(project)
    model = install_fake(
        orch,
        {
            MODEL_DEVELOPER: [write_block("src/calc.py", BROKEN_SOURCE)],
            # The bounded debugger also fails to repair; after the last attempt the
            # mission must block instead of looping forever.
            MODEL_DEBUGGER: [write_block("src/calc.py", BROKEN_REPAIR)],
        },
    )

    result = orch.run_mission(mission_id)

    assert result["status"] == "blocked", result
    assert "Verification failed after 2 attempt(s)" in result["error"]
    assert model.roles == [MODEL_DEVELOPER, MODEL_DEBUGGER]
    assert model.roles.count(MODEL_DEBUGGER) == 1
    assert read_text(live_path) == live_before

    candidate_passes, oracle_passes = verification_passes(mission_id)
    assert candidate_passes == [False, False]
    assert oracle_passes == [False, False]

    mission = get_mission(mission_id)
    assert mission["status"] == "blocked"
    assert mission["promotion_status"] == "verification_failed"
    assert json.loads(mission["changed_paths"]) == []
    assert Path(mission["staging_dir"]).is_dir()
    assert not (mission_env / "recovery" / (str(mission_id) + ".json")).exists()

    promoted_handoffs = [
        handoff for handoff in get_handoffs(mission_id)
        if (handoff.get("payload") or {}).get("promoted")
    ]
    assert promoted_handoffs == []

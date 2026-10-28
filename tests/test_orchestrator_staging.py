"""C6: staged-candidate lifecycle wired into MultiAgentOrchestrator (fake model)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from nl_coding_agent.agents import orchestrator as orchestrator_module
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.persistence import database
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_handoffs,
    get_mission,
    get_tasks,
    get_verification_runs,
)
from nl_coding_agent.projects.registry import open_project

CALC_SOURCE = "def add(a, b):\n    return a + b\n"
CALC_WITH_SUB = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
CALC_STUB = "def add(a, b):\n    pass\n"
TEST_SOURCE = "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
GOAL = "Add a subtract function to src/calc.py"

MODEL_DEVELOPER = "Implementation Developer"
MODEL_REVIEWER = "Code Reviewer & Quality Gatekeeper"


def write_block(rel_path: str, content: str) -> str:
    """Model output that the text-action fallback applies inside the stage workspace."""
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
                f"Unexpected model call for role {role!r}; roles so far: {self.roles}"
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
    return create_mission(project["id"], "C6 staged candidate mission", goal)


def stages_root(project_root: Path) -> Path:
    return project_root / "data" / "staging"


def stage_dirs(project_root: Path) -> list[Path]:
    root = stages_root(project_root)
    if not root.is_dir():
        return []
    return sorted(path for path in root.glob("mission-*") if path.is_dir())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def no_llm_and_bounded_verification(monkeypatch):
    """Any hidden CrewAI/LLM path fails loudly; verification is time-bounded."""

    def _boom(*args, **kwargs):
        raise AssertionError("_make_llm must not be called: tests install a fake _call_model")

    monkeypatch.setattr(orchestrator_module, "_make_llm", _boom)
    monkeypatch.setattr(orchestrator_module, "VERIFY_TIMEOUT_S", 60)


@pytest.fixture()
def mission_env(tmp_path, monkeypatch):
    """Isolated app data dir: SQLite, mission lock, recovery and evidence live here."""
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setenv("NL_DATA_DIR", str(data))
    database.init_db().close()
    return data


@pytest.fixture()
def project(mission_env, tmp_path):
    """Minimal project whose staged copy can run the real verifier (candidate + oracle)."""
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


def test_happy_path_promotes_only_after_review_approval(project, mission_env):
    mission_id = new_mission(project)
    live_path = project / "src" / "calc.py"
    live_before = read_text(live_path)
    observed: dict[str, str] = {}

    def at_review():
        # Promotion must be the last gate: the live tree is still untouched here.
        observed["live_at_review"] = read_text(live_path)

    orch = MultiAgentOrchestrator(project)
    model = install_fake(
        orch,
        {
            MODEL_DEVELOPER: [write_block("src/calc.py", CALC_WITH_SUB)],
            MODEL_REVIEWER: ["APPROVE\nCandidate is correct and verified.\n"],
        },
        hooks={MODEL_REVIEWER: at_review},
    )
    started = time.monotonic()
    result = orch.run_mission(mission_id)
    assert time.monotonic() - started < 120

    assert result["status"] == "completed", result
    assert result["promotion_status"] == "promoted"
    assert observed["live_at_review"] == live_before
    assert "def sub(a, b):" in read_text(live_path)
    assert model.roles == [MODEL_DEVELOPER, MODEL_REVIEWER]
    assert len(model.calls[0]["tools"]) == 4

    mission = get_mission(mission_id)
    assert mission["status"] == "completed"
    assert mission["promotion_status"] == "promoted"
    assert json.loads(mission["changed_paths"]) == ["src/calc.py"]
    assert "promoted 1 file(s)" in (mission["result_summary"] or "")
    stage_dir = Path(mission["staging_dir"])
    assert stage_dir.is_absolute()
    assert not stage_dir.exists()  # stage cleaned after completion
    assert stage_dirs(project) == []

    recovery = mission_env / "recovery" / f"{mission_id}.json"
    assert recovery.is_file()
    evidence = mission_env / "verification" / f"mission-{mission_id}.json"
    assert evidence.is_file()
    evidence_payload = json.loads(read_text(evidence))
    assert evidence_payload["status"] == "completed"
    assert evidence_payload["harness_version"] == 2
    assert evidence_payload["changed_paths"] == ["src/calc.py"]
    assert evidence_payload["verification"]["passed"] is True

    runs = get_verification_runs(mission_id)
    commands = [run["command"] for run in runs]
    assert any(command.startswith("verify:candidate ") for command in commands)
    assert any(command.startswith("verify:oracle ") for command in commands)
    assert all(run["passed"] for run in runs)

    conn = database.init_db()
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
    finally:
        conn.close()
    assert count == 1


def test_stub_candidate_blocks_without_promotion(project, mission_env):
    mission_id = new_mission(project)
    live_path = project / "src" / "calc.py"
    live_before = read_text(live_path)
    orch = MultiAgentOrchestrator(project)
    model = install_fake(
        orch, {MODEL_DEVELOPER: [write_block("src/calc.py", CALC_STUB)]}
    )

    result = orch.run_mission(mission_id)

    assert result["status"] == "blocked", result
    assert "validation gate" in result["error"]
    assert result["changed_paths"] == []
    assert read_text(live_path) == live_before
    assert model.roles == [MODEL_DEVELOPER]  # reviewer/tester never reached
    assert get_verification_runs(mission_id) == []
    assert not (mission_env / "recovery" / f"{mission_id}.json").exists()

    mission = get_mission(mission_id)
    assert mission["status"] == "blocked"
    assert mission["promotion_status"] == "candidate_rejected"
    assert json.loads(mission["changed_paths"]) == []
    assert (mission["diff_stat"] or "") == ""
    stage_dir = Path(mission["staging_dir"])
    assert stage_dir.is_dir()  # staged candidate retained for diagnosis
    assert "pass" in read_text(stage_dir / "workspace" / "src" / "calc.py")
    assert [path.name for path in stage_dirs(project)] == [stage_dir.name]
    assert not (stage_dir / "promotion-journal.json").exists()


def test_reviewer_reject_blocks_and_leaves_live_unchanged(project, mission_env):
    mission_id = new_mission(project)
    live_path = project / "src" / "calc.py"
    live_before = read_text(live_path)
    orch = MultiAgentOrchestrator(project)
    model = install_fake(
        orch,
        {
            MODEL_DEVELOPER: [write_block("src/calc.py", CALC_WITH_SUB)],
            MODEL_REVIEWER: ["REJECT: missing docs\n"],
        },
    )

    result = orch.run_mission(mission_id)

    assert result["status"] == "blocked", result
    assert "Reviewer REJECTED" in result["error"]
    assert read_text(live_path) == live_before
    assert model.roles == [MODEL_DEVELOPER, MODEL_REVIEWER]
    review_prompt = model.prompts_for(MODEL_REVIEWER)[0]
    assert "NOT yet applied" in review_prompt
    assert "CANDIDATE DIFF TO REVIEW" in review_prompt
    assert not (mission_env / "recovery" / f"{mission_id}.json").exists()

    mission = get_mission(mission_id)
    assert mission["status"] == "blocked"
    assert mission["promotion_status"] == "review_rejected"
    assert Path(mission["staging_dir"]).is_dir()
    assert json.loads(mission["changed_paths"]) == []

    commands = [run["command"] for run in get_verification_runs(mission_id)]
    assert any(command.startswith("verify:candidate ") for command in commands)
    assert any(command.startswith("verify:oracle ") for command in commands)


def test_stop_after_developer_retains_staged_candidate(project, mission_env):
    mission_id = new_mission(project)
    live_path = project / "src" / "calc.py"
    live_before = read_text(live_path)
    orch = MultiAgentOrchestrator(project)
    model = install_fake(
        orch, {MODEL_DEVELOPER: [write_block("src/calc.py", CALC_WITH_SUB)]}
    )

    result = orch.run_mission(mission_id, stop_after="developer")

    assert result["status"] == "interrupted", result
    assert result["changed_paths"] == []
    assert result["diff_stat"] == ""
    assert read_text(live_path) == live_before
    assert model.roles == [MODEL_DEVELOPER]
    assert get_verification_runs(mission_id) == []

    mission = get_mission(mission_id)
    assert mission["status"] == "interrupted"
    assert mission["promotion_status"] == "validated"
    stage_dir = Path(mission["staging_dir"])
    assert stage_dir.is_dir()
    assert "def sub(a, b):" in read_text(stage_dir / "workspace" / "src" / "calc.py")
    assert json.loads(mission["changed_paths"]) == []

    interrupted = [
        handoff for handoff in get_handoffs(mission_id)
        if (handoff.get("payload") or {}).get("status") == "interrupted"
    ]
    assert interrupted
    payload = interrupted[-1]["payload"]
    assert payload["staged_paths"] == ["src/calc.py"]
    assert payload["live_changes"] == "none"


def test_resume_after_developer_interruption_promotes_once(project, mission_env):
    mission_id = new_mission(project)
    live_path = project / "src" / "calc.py"
    live_before = read_text(live_path)
    first = MultiAgentOrchestrator(project)
    install_fake(first, {MODEL_DEVELOPER: [write_block("src/calc.py", CALC_WITH_SUB)]})
    interrupted = first.run_mission(mission_id, stop_after="developer")
    assert interrupted["status"] == "interrupted"
    assert read_text(live_path) == live_before
    assert len(get_tasks(mission_id)) == 3

    # Resume in a fresh instance (simulated restart); developer must be reused.
    resumed = MultiAgentOrchestrator(project)
    model = install_fake(resumed, {MODEL_REVIEWER: ["APPROVE\nresumed review ok\n"]})
    result = resumed.run_mission(mission_id)

    assert result["status"] == "completed", result
    assert model.roles == [MODEL_REVIEWER]
    assert "def sub(a, b):" in read_text(live_path)
    tasks = get_tasks(mission_id)
    assert len(tasks) == 3  # no duplicated tasks
    assert all(task["status"] == "completed" for task in tasks)
    mission = get_mission(mission_id)
    assert mission["status"] == "completed"
    assert mission["promotion_status"] == "promoted"
    promoted_handoffs = [
        handoff for handoff in get_handoffs(mission_id)
        if (handoff.get("payload") or {}).get("promoted")
    ]
    assert len(promoted_handoffs) == 1
    assert not stage_dirs(project)


@pytest.mark.parametrize("harness_version", [None, 1])
def test_legacy_mission_is_blocked_without_writes(project, mission_env, harness_version):
    project_row = open_project(project)
    if harness_version is None:
        conn = database.init_db()
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO missions (project_id, title, goal, status) "
                    "VALUES (?, ?, ?, 'pending')",
                    (project_row["id"], "Legacy mission", "Legacy goal"),
                )
            mission_id = cursor.lastrowid
        finally:
            conn.close()
    else:
        mission_id = create_mission(
            project_row["id"],
            "Legacy mission",
            "Legacy goal",
            harness_version=harness_version,
        )

    live_path = project / "src" / "calc.py"
    live_before = read_text(live_path)
    orch = MultiAgentOrchestrator(project)
    model = install_fake(orch, {})

    result = orch.run_mission(mission_id)

    assert result["status"] == "blocked", result
    assert "predates the staged-candidate harness" in result["error"]
    assert result["promotion_status"] == "legacy_mission"
    assert model.calls == []  # no model call, no stage
    mission = get_mission(mission_id)
    assert mission["status"] == "blocked"
    assert mission["harness_version"] == harness_version
    assert mission["staging_dir"] is None
    assert read_text(live_path) == live_before
    assert not stages_root(project).exists()
    assert get_verification_runs(mission_id) == []


def test_human_edit_during_review_blocks_cas_promotion(project, mission_env):
    mission_id = new_mission(project)
    live_path = project / "src" / "calc.py"
    human_content = CALC_SOURCE + "# concurrent human edit\n"

    def human_edit():
        # Simulates a human touching the live file after staging, before promotion.
        live_path.write_text(human_content, encoding="utf-8", newline="")

    orch = MultiAgentOrchestrator(project)
    install_fake(
        orch,
        {
            MODEL_DEVELOPER: [write_block("src/calc.py", CALC_WITH_SUB)],
            MODEL_REVIEWER: ["APPROVE\nCandidate approved before the conflict was noticed.\n"],
        },
        hooks={MODEL_REVIEWER: human_edit},
    )

    result = orch.run_mission(mission_id)

    assert result["status"] == "blocked", result
    assert "CAS promotion denied" in result["error"]
    assert read_text(live_path) == human_content  # concurrent edit preserved
    mission = get_mission(mission_id)
    assert mission["status"] == "blocked"
    assert mission["promotion_status"] == "cas_conflict"
    assert json.loads(mission["changed_paths"]) == []
    assert Path(mission["staging_dir"]).is_dir()
    assert not (mission_env / "recovery" / f"{mission_id}.json").exists()


def test_documentation_only_candidate_is_blocked_for_requirement_mission(project, mission_env):
    """SH-07 Tier B #1 regression: docs-only candidates must not satisfy functional requirements."""
    project_row = open_project(project)
    goal = "Update docs/notes.md with a summary of durable mission persistence."
    mission_id = create_mission(
        project_row["id"],
        "NL-BP-051 Durable mission persistence",
        goal,
        requirement_id="NL-BP-051",
    )
    live_doc = project / "docs" / "notes.md"
    orch = MultiAgentOrchestrator(project)
    install_fake(
        orch,
        {
            MODEL_DEVELOPER: [write_block("docs/notes.md", "# Notes\n\nNothing implemented.\n")],
            MODEL_REVIEWER: ["APPROVE\n"],
        },
    )

    result = orch.run_mission(mission_id)

    assert result["status"] == "blocked", result
    assert "Documentation-only candidate rejected" in result["error"]
    assert not live_doc.exists()
    mission = get_mission(mission_id)
    assert mission["status"] == "blocked"
    assert Path(mission["staging_dir"]).is_dir()

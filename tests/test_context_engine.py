"""Context Engine P1: measured budget, project profile, retrieval, memory."""
from __future__ import annotations

import json

import pytest

from nl_coding_agent.context.budget import compact_chat, estimate_tokens
from nl_coding_agent.context.engine import ContextEngine
from nl_coding_agent.context import memory as project_memory
from nl_coding_agent.context.profile import (
    build_profile,
    ensure_profile,
    load_profile,
    select_relevant_files,
)
from nl_coding_agent.persistence import database


def _big(text: str, size: int) -> str:
    return (text + " ") * (size // (len(text) + 1))


def _transcript(turns: int, payload: int = 4_000) -> list[dict]:
    messages = [{"role": "system", "content": "SYSTEM CONTRACT"}]
    for index in range(turns):
        messages.append({"role": "user", "content": f"request {index} " + _big("u", payload)})
        messages.append({"role": "assistant", "content": f"answer {index} " + _big("a", payload)})
        messages.append({"role": "tool", "name": "read_file", "content": _big("t", payload)})
    messages.append({"role": "user", "content": "CURRENT REQUEST: change src/calc.py"})
    return messages


def test_chat_budget_compacts_instead_of_failing():
    messages = _transcript(20)
    result = compact_chat(messages, tools=[], max_chars=20_000)
    assert result.degraded
    assert result.chars <= 20_000
    assert result.summarized
    assert result.summary
    assert result.messages[0]["content"] == "SYSTEM CONTRACT"
    assert any("CURRENT REQUEST" in str(item.get("content") or "")
               for item in result.messages)
    # No orphan tool result may survive without the assistant turn that requested it.
    for index, message in enumerate(result.messages):
        if message.get("role") == "tool":
            assert index > 0 and result.messages[index - 1].get("role") in ("assistant", "tool")
    assert result.estimated_tokens > 0
    assert estimate_tokens("abcd") >= 1


def test_chat_budget_keeps_tool_schemas_and_shortens_descriptions():
    tools = [{
        "type": "function",
        "function": {
            "name": f"tool_{index}",
            "description": "D" * 5_000,
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
    } for index in range(10)]
    result = compact_chat(_transcript(4, payload=500), tools, max_chars=20_000,
                          tool_char_budget=10_000)
    assert result.tools
    for tool in result.tools:
        assert tool["function"]["parameters"]["properties"]["path"]["type"] == "string"
        assert len(tool["function"]["description"]) <= 403
    assert any("tool-descriptions" in item for item in result.trimmed)


def test_empty_transcript_is_safe():
    result = compact_chat([], [], max_chars=1_000)
    assert result.messages == []
    assert result.chars <= 4  # JSON bracket overhead only
    assert result.estimated_tokens >= 1


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
        encoding="utf-8")
    (root / "src" / "stats.py").write_text(
        "def mean(values):\n    return sum(values) / len(values)\n", encoding="utf-8")
    (root / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8")
    (root / "README.md").write_text("# Fixture project\n", encoding="utf-8")
    from nl_coding_agent.app.services import AppServices
    services = AppServices()
    opened = services.open_project(root)
    yield services, opened, root
    services._db.close()


def test_project_profile_is_persisted_and_refreshable(project, tmp_path):
    services, opened, root = project
    profile = load_profile(opened["id"])
    assert profile is not None
    assert profile.root == str(root.resolve())
    assert "src/calc.py" in [item["path"] for item in profile.source_files]
    assert "pytest" in profile.test_command
    (root / "src" / "new_module.py").write_text("VALUE = 1\n", encoding="utf-8")
    refreshed = ensure_profile(opened["id"], root, max_age_s=0)
    assert "src/new_module.py" in [item["path"] for item in refreshed.source_files]
    # A staged/mission copy must not overwrite the registered project's profile.
    staged = tmp_path / "staged"
    staged.mkdir()
    files = select_relevant_files(staged, "src/calc.py add", refreshed)
    assert files == []


def test_selective_retrieval_prefers_the_named_file(project):
    services, opened, root = project
    profile = load_profile(opened["id"]) or build_profile(root)
    files = select_relevant_files(root, "In src/calc.py add a subtract(a, b) function. "
                                       "Change only src/calc.py.", profile)
    assert files[0]["path"] == "src/calc.py"
    assert "explicitly named" in files[0]["reason"]
    assert "def subtract" in files[0]["excerpt"] or "def add" in files[0]["excerpt"]


def test_mission_context_contains_profile_files_and_memory(project):
    services, opened, root = project
    project_memory.record(opened["id"], "failure",
                          "src/calc.py: previous attempt removed the add() test",
                          tags=["src/calc.py"], confidence=0.8)
    engine = ContextEngine(opened["id"], root)
    context = engine.mission_context("In src/calc.py add subtract(a, b)", budget_chars=12_000)
    assert "PROJECT PROFILE" in context.text
    assert "PROJECT MEMORY" in context.text
    assert "removed the add() test" in context.text
    assert context.files and context.files[0]["path"] == "src/calc.py"
    assert context.memory_entries >= 1


def test_memory_is_deduplicated_and_recallable(project):
    services, opened, root = project
    first = project_memory.record(opened["id"], "decision",
                                  "Use pytest for src/calc.py verification")
    second = project_memory.record(opened["id"], "decision",
                                   "use pytest for src/calc.py verification")
    assert first is not None and second is not None
    assert first["id"] == second["id"]
    found = project_memory.recall(opened["id"], "calc verification")
    assert found and found[0]["kind"] == "decision"
    assert project_memory.recall(opened["id"], "", limit=1)


def test_memory_redacts_secret_like_values(project):
    services, opened, _root = project
    entry = project_memory.record(opened["id"], "note",
                                  "api_key=super-secret-value and token: abc123")
    assert entry is not None
    assert "super-secret-value" not in entry["text"]
    assert "[redacted]" in entry["text"]


def test_chat_summary_round_trip_and_no_duplicate(project):
    services, opened, root = project
    engine = ContextEngine(opened["id"], root)
    messages = _transcript(12)
    first = engine.chat_turn(messages, [], session_id="session-a", max_chars=12_000)
    assert first.degraded and first.summary
    stored = engine.latest_summary("session-a")
    assert stored and stored["summary"] == first.summary
    # The same compaction must not append duplicate summaries.
    engine.chat_turn(messages, [], session_id="session-a", max_chars=12_000)
    conn = database.init_db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM context_summaries WHERE project_id=? AND session_id=?",
            (opened["id"], "session-a")).fetchone()[0]
    finally:
        conn.close()
    assert count == 1
    status = engine.status()
    assert status["profile"]["available"] is True
    assert status["summary"]["summary"] == first.summary


def test_mission_outcome_memory_is_recorded(project):
    from nl_coding_agent.persistence.missions import (
        create_mission, update_mission_result,
    )
    services, opened, _root = project
    mission_id = create_mission(opened["id"], "Outcome", "Change src/calc.py")
    update_mission_result(mission_id, "completed", result_summary="promoted 1 file")
    saved = project_memory.attach_mission_outcome(mission_id)
    assert saved
    assert any(entry["kind"] == "mission_outcome" for entry in saved)
    entries = project_memory.recall(opened["id"], "calc mission", kinds=["mission_outcome"])
    assert entries
    # Re-attaching the same finished mission is idempotent.
    again = project_memory.attach_mission_outcome(mission_id)
    assert len(again) == len(saved)


def test_completed_mission_writes_project_memory(project):
    """A real orchestrator run persists a cross-mission lesson automatically."""
    from nl_coding_agent.agents.crew_backend import FakeCrewRuntime
    from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
    from nl_coding_agent.core import permissions
    from nl_coding_agent.persistence.missions import create_mission, get_mission

    services, opened, root = project
    (root / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    for scope in (permissions.READ, permissions.WRITE, permissions.EXECUTE):
        permissions.grant(scope, project_id=opened["id"], source="test")
    mission_id = create_mission(opened["id"], "Remembered", "Add subtract to src/calc.py")
    runtime = FakeCrewRuntime({
        "developer": [
            "```write:src/calc.py\ndef add(a, b):\n    return a + b\n\n"
            "def subtract(a, b):\n    return a - b\n```"
        ],
        "reviewer": ["APPROVE\nok\n"],
    })
    orchestrator = MultiAgentOrchestrator(root, project_id=opened["id"],
                                          crew_runtime=runtime)
    result = orchestrator.run_mission(mission_id)
    assert result["status"] == "completed", result
    assert get_mission(mission_id)["status"] == "completed"
    entries = project_memory.recall(opened["id"], "calc",
                                    kinds=["mission_outcome"])
    assert entries, "completed mission must be remembered for later missions"
    assert entries[0]["mission_id"] == mission_id


def test_window_limits_are_dynamic_and_reserve_output_and_thinking(monkeypatch):
    from nl_coding_agent.context import window as window_module

    monkeypatch.setattr(window_module, "_generation_window", lambda *a: 8_192)
    limits = window_module.limits_for("ollama", "any-model")
    assert limits.window_tokens == 8_192
    assert limits.source == "generation-params"
    assert limits.reserve_output_tokens > 0
    assert limits.reserve_think_tokens > 0
    assert limits.prompt_tokens < limits.window_tokens
    assert limits.prompt_tokens >= window_module.MIN_PROMPT_TOKENS

    monkeypatch.setattr(window_module, "_generation_window", lambda *a: None)
    monkeypatch.setattr(window_module, "_capability_window", lambda *a: None)
    monkeypatch.setattr(window_module, "_provider_config_window", lambda *a: None)
    monkeypatch.setattr(window_module, "_cached_measured_window", lambda *a: None)
    fallback = window_module.limits_for("openai_compatible", "unknown-model")
    assert fallback.window_tokens is None
    assert fallback.source == "fallback"
    assert fallback.prompt_chars > 60_000  # generous, not the old fixed wall
    assert any("fallback" in note for note in fallback.notes)


def test_calibration_improves_the_token_estimate(project, monkeypatch):
    from nl_coding_agent.context import window as window_module

    services, opened, root = project
    monkeypatch.setattr(window_module, "_generation_window", lambda *a: 16_384)
    ratio = window_module.calibrate("ollama", "calibrated", prompt_tokens=1_000,
                                    chars_sent=4_200)
    assert ratio and 4.0 <= ratio <= 4.5
    limits = window_module.limits_for("ollama", "calibrated")
    assert limits.chars_per_token == ratio
    assert limits.prompt_tokens < 16_384


def test_thinking_tokens_are_counted_in_the_estimate():
    from nl_coding_agent.context.budget import estimate_tokens

    plain = {"role": "assistant", "content": "answer " * 100}
    thinking = dict(plain, _thinking="reasoning " * 400)
    assert estimate_tokens(thinking) > estimate_tokens(plain) * 1.5
    assert estimate_tokens("x" * 3_400) == 1_000


def test_digest_preserves_decisions_results_and_errors():
    from nl_coding_agent.context.budget import compact_chat

    messages = [{"role": "system", "content": "SYSTEM"}]
    for index in range(5):
        messages.append({"role": "user", "content": f"routine question {index} " + "x" * 3_000})
        messages.append({"role": "assistant", "content": "routine answer " + "y" * 3_000})
    messages.append({
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "c1", "function": {
            "name": "patch_file", "arguments": {"path": "src/calc.py"}}}],
    })
    messages.append({"role": "tool", "name": "patch_file", "tool_call_id": "c1",
                     "content": json.dumps({"ok": True, "result": {"patched": True}})})
    messages.append({"role": "user",
                     "content": "DECISION: use patch_file, do not rewrite the whole file"})
    messages.append({"role": "tool", "name": "run_tests", "tool_call_id": "c2",
                     "content": json.dumps({"ok": False, "result": {"returncode": 1,
                                                                   "error": "FAILED test_add"}})})
    messages.append({"role": "user", "content": "CURRENT REQUEST: fix the failing test"})
    result = compact_chat(messages, [], max_tokens=800)
    digest = result.summary
    joined = json.dumps(result.messages, ensure_ascii=False)
    # The digest keeps the routine objectives; decisions/results/errors are preserved
    # verbatim as critical turns rather than being paraphrased away.
    assert "OBJECTIVES" in digest
    assert "src/calc.py" in joined
    assert "do not rewrite" in joined or "DECISION" in joined
    assert "FAILED" in joined or "fail" in joined.lower()
    assert "fix the failing test" in joined
    assert result.preserved_messages >= 1


def test_mission_pack_slices_the_same_context_per_role(project):
    services, opened, root = project
    project_memory.record(opened["id"], "failure",
                          "src/calc.py: keep add() intact", tags=["src/calc.py"])
    engine = ContextEngine(opened["id"], root)
    pack = engine.build_mission_pack("In src/calc.py add subtract(a, b)", budget_chars=10_000)
    architect = pack.for_role("architect")
    developer = pack.for_role("developer")
    reviewer = pack.for_role("reviewer")
    assert "PROJECT PROFILE" in architect and "def add" not in architect
    assert "def add" in developer and "PROJECT PROFILE" in developer
    assert "def add" not in reviewer and "keep add()" in reviewer
    assert pack.file_paths() and pack.file_paths()[0] == "src/calc.py"


"""Chat model-call orchestration: scope, budgets, actual MCP and recovery."""
import json
import sys
from pathlib import Path

import pytest

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.app.chat_tools import load_state
from nl_coding_agent.core import permissions


class Provider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def chat_turn(self, model, messages, tools, **kwargs):
        self.requests.append((json.loads(json.dumps(messages)), tools))
        item = next(self.responses)
        return item(tools) if callable(item) else item


def call(name, **arguments):
    return {"tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    root.mkdir()
    (root / "calc.py").write_text("value = 7\n")
    services = AppServices()
    project = services.open_project(root)
    def run(responses, text="Question", **options):
        provider = Provider(responses)
        monkeypatch.setattr(services, "_resolve_chat_provider", lambda *a, **kw: (provider, "model", "test", ""))
        return services.chat_conversation(project, text, tools_enabled=True, model_spec="test/model", **options), provider
    yield services, project, run
    services._db.close()


def test_ordinary_question_does_not_discover_or_invoke(chat, monkeypatch):
    services, project, run = chat
    monkeypatch.setattr("nl_coding_agent.app.mcp.McpManager.list_tools", lambda *a: pytest.fail("unnecessary discovery"))
    result, _ = run([{"content": "Quattro"}], text="Quanto fa due più due?")
    assert result["ok"] and result["reply"] == "Quattro"
    assert load_state(project["id"])["used_calls"] == 0
    assert services.list_missions(project["id"]) == []


def test_source_tool_and_result_interpretation(chat):
    services, project, run = chat
    result, provider = run([call("read_source", path="calc.py"), {"content": "value vale 7"}])
    assert result["ok"]
    tool_result = next(item for item in reversed(provider.requests[1][0]) if item["role"] == "tool")
    assert "value = 7" in tool_result["content"]
    assert json.loads(tool_result["content"])["untrusted"]
    assert services.list_chat_messages(project_id=project["id"])[-1]["role"] == "assistant"


def test_denied_source_and_coding_do_not_escape(chat, tmp_path):
    services, project, run = chat
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    result, provider = run([call("read_source", path="../secret.txt"), {"content": "Access denied"}])
    assert "secret\"" not in provider.requests[1][0][-1]["content"]
    assert '"error"' in provider.requests[1][0][-1]["content"]
    result, _ = run([call("start_coding", goal="Change calc.py"), {"content": "Not authorized"}])
    assert services.list_missions(project["id"]) == []
    assert any(a["status"] == "error" for a in load_state(project["id"])["activity"])


def test_cancel_before_tool_and_resume_without_replaying_completed_call(chat):
    services, project, run = chat
    def cancelled(tools):
        services.cancel_chat_tools(project["id"])
        return call("read_source", path="calc.py")
    result, _ = run([cancelled])
    assert result["status"] == "cancelled"
    assert load_state(project["id"])["used_calls"] == 0
    result, provider = run([{"content": "Read completed"}], resume=True)
    assert result["ok"]
    state = load_state(project["id"])
    assert state["used_calls"] == 1
    assert sum(a == {"tool": "read_source", "status": "completed"} for a in state["activity"]) == 1


def test_budget_persists_pending_calls_and_resume(chat):
    services, project, run = chat
    result, _ = run([call("read_source", path="calc.py")], max_calls=1)
    assert result["status"] == "budget_exhausted"
    result, _ = run([{"content": "Result"}], resume=True)
    assert result["ok"] and load_state(project["id"])["used_calls"] == 1


def test_uncertain_call_is_not_replayed(chat):
    services, project, run = chat
    run([call("read_source", path="calc.py")], max_calls=1)
    from nl_coding_agent.app.chat_tools import state_path
    state = load_state(project["id"])
    state["in_flight"] = "unknown-outcome"
    state_path(project["id"]).write_text(json.dumps(state))
    result, _ = run([], resume=True)
    assert not result["ok"] and "uncertain" in result["reply"]


def test_real_mcp_discovered_selected_invoked_and_interpreted(chat):
    pytest.importorskip("mcp")
    services, project, run = chat
    from nl_coding_agent.persistence.database import data_root
    fixture = Path(__file__).parent / "fixtures/mcp_sdk_server.py"
    (data_root() / "mcp_servers.json").write_text(json.dumps({"servers": {"fixture": {
        "command": sys.executable, "args": [str(fixture)], "trusted": True,
        "allowed_tools": ["echo"]}}}))
    def selected(tools):
        tool = next(t for t in tools if t["function"]["name"].startswith("mcp_"))
        assert tool["function"]["parameters"]["properties"]["text"]["type"] == "string"
        return call(tool["function"]["name"], text="real MCP")
    result, provider = run([call("discover_mcp", server="fixture"), selected, {"content": "Tool returned real MCP"}])
    assert result["ok"]
    assert "real MCP" in provider.requests[2][0][-1]["content"]
    assert any(a["tool"].startswith("mcp_") and a["status"] == "completed" for a in load_state(project["id"])["activity"])


def test_project_identity_and_revocation(chat):
    services, project, run = chat
    foreign = {**project, "root": str(Path(project["root"]).parent)}
    result = services.chat_conversation(foreign, "Read files", tools_enabled=True, model_spec="test/model")
    assert not result["ok"] and "mismatch" in result["reply"]
    permissions.revoke(permissions.READ, project_id=project["id"])
    result, _ = run([call("read_source", path="calc.py")])
    assert not result["ok"]


def test_duplicate_call_ids_fail_before_any_invocation(chat):
    services, project, run = chat
    response = call("read_source", path="calc.py")
    response["tool_calls"][0]["id"] = "duplicate"
    response["tool_calls"] *= 2
    result, _ = run([response])
    assert not result["ok"] and "Duplicate" in result["reply"]
    assert load_state(project["id"])["used_calls"] == 0


def test_cross_process_writer_lock_prevents_transcript_replacement(chat):
    from nl_coding_agent.core.mission_lock import mission_lock
    from nl_coding_agent.app.chat_tools import state_path
    services, project, run = chat
    with mission_lock(project["id"], path=state_path(project["id"]).with_suffix(".lock")):
        result, _ = run([{"content": "Should not execute"}])
    assert not result["ok"] and "Another mission" in result["reply"]
    assert load_state(project["id"]) is None


def test_cancel_during_creation_never_dispatches_mission(chat, monkeypatch):
    services, project, run = chat
    original = services.create_mission
    def create(*args):
        mid = original(*args)
        services.cancel_chat_tools(project["id"])
        return mid
    monkeypatch.setattr(services, "create_mission", create)
    monkeypatch.setattr(services, "run_mission", lambda *a, **kw: pytest.fail("Cancelled before dispatch"))
    result, _ = run([call("start_coding", goal="Update calc.py")], allow_coding=True)
    assert result["status"] == "cancelled"
    from nl_coding_agent.persistence.database import get_setting
    mid = services.list_missions(project["id"])[0]["id"]
    assert get_setting("mission.stop." + str(mid), "")


def test_json_fallback_is_explicit_and_schema_validated(chat, monkeypatch):
    services, project, run = chat
    provider = Provider([])
    replies = iter([json.dumps({"tool_calls": [{"name": "read_source", "arguments": {"path": "calc.py"}}]}),
                    json.dumps({"reply": "Value is 7"})])
    provider.generate = lambda *args, **kwargs: next(replies)
    monkeypatch.setattr(services, "_resolve_chat_provider", lambda *a, **kw: (provider, "model", "test", ""))
    result = services.chat_conversation(project, "Read source", tools_enabled=True,
                                       model_spec="test/model", tool_protocol="json")
    assert result["ok"] and result["reply"] == "Value is 7"
    assert load_state(project["id"])["used_calls"] == 1


def test_native_textual_tool_request_is_recovered_and_executed(chat):
    services, project, run = chat
    result, provider = run([
        {"content": json.dumps({"name": "read_source", "arguments": {"path": "calc.py"}})},
        {"content": "value vale 7"},
    ])
    assert result["ok"] and result["reply"] == "value vale 7"
    assert load_state(project["id"])["used_calls"] == 1
    tool_result = next(item for item in reversed(provider.requests[1][0]) if item["role"] == "tool")
    assert "value = 7" in tool_result["content"]


def test_discovered_tools_need_current_explicit_allowlist(chat, monkeypatch):
    from nl_coding_agent.app import mcp
    services, project, run = chat
    config = {"servers": {"fixture": {"command": "never-start", "trusted": True, "allowed_tools": ["echo"]}}}
    monkeypatch.setattr(mcp, "load_mcp_config", lambda: config)
    monkeypatch.setattr(mcp.McpManager, "list_tools", lambda *a: [{"name": "echo", "qualified_name": "fixture::echo",
        "description": "Echo", "input_schema": {"type": "object"}}])
    monkeypatch.setattr(mcp.McpManager, "invoke_tool", lambda *a, **kw: pytest.fail("Removed allowlist must deny"))
    def selected(tools):
        config["servers"]["fixture"].pop("allowed_tools")
        name = next(t["function"]["name"] for t in tools if t["function"]["name"].startswith("mcp_"))
        return call(name)
    result, provider = run([call("discover_mcp", server="fixture"), selected, {"content": "Tool denied"}])
    assert result["ok"]
    assert "no longer explicitly allowlisted" in provider.requests[-1][0][-1]["content"]

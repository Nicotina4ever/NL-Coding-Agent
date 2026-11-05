"""Chat model-call orchestration: scope, budgets, actual MCP and recovery."""
import time
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import struct
import zlib
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


def _one_pixel_png():
    def chunk(kind, payload):
        body = kind + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + chunk(b"IEND", b""))


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


@pytest.mark.parametrize("text", [
    "Scrivi una spiegazione del testing. Non modificare file e non usare strumenti.",
    "Write an explanation of the code. Do not modify files.",
    "Spiega questo codice, non toccare i sorgenti.",
])
def test_prose_or_explicit_read_only_request_cannot_start_a_mission(chat, text):
    services, project, run = chat
    def answer(tools):
        assert "start_coding" not in {item["function"]["name"] for item in tools}
        return {"content": "Spiegazione senza modifiche."}
    result, _ = run([answer], text=text, allow_coding=True)
    assert result["ok"]
    assert not services.list_missions(project["id"])


def test_scoped_no_edit_constraint_keeps_the_positive_coding_request():
    from nl_coding_agent.app.chat_tools import explicitly_read_only, looks_like_coding_request
    text = "Aggiungi subtract in src/calc.py. Non modificare i file di test."
    assert not explicitly_read_only(text)
    assert looks_like_coding_request(text)
    assert explicitly_read_only("Analizza il progetto. Non modificare nessun file.")


def test_explicit_no_tools_and_xml_draft_must_end_in_a_real_answer(chat):
    services, project, run = chat
    def xml_draft(tools):
        assert tools == []
        return {"content": "<tool_call><function=read_file><parameter=path>calc.py</parameter></function></tool_call>"}
    result, provider = run([xml_draft, {"content": "Il testing verifica il comportamento del software."}],
                           text="Scrivi una spiegazione del testing. Non usare strumenti.", allow_coding=True)
    assert result["ok"] and "testing" in result["reply"]
    assert "<tool_call>" not in result["reply"]
    assert len(provider.requests) == 2
    assert not services.list_missions(project["id"])


def test_new_session_continuity_uses_persisted_digest(chat, monkeypatch):
    """A new Chat session continues from the persisted digest of earlier work."""
    services, project, run = chat
    root = Path(project["root"])
    for index in range(8):
        (root / f"ctx{index}.py").write_text("x = 1\n" * 3_000, encoding="utf-8")

    def read(index):
        return lambda tools: call("read_source", path=f"ctx{index}.py")

    provider = Provider([read(index) for index in range(8)] + [{"content": "ok"}])
    monkeypatch.setattr(services, "_resolve_chat_provider",
                        lambda *a, **kw: (provider, "model", "test", ""))
    session_one = services.create_chat_session(project["id"], "long session")["id"]
    first = services.chat_conversation(
        project, "Read all context files", tools_enabled=True,
        model_spec="test/model", session_id=session_one, max_calls=24)
    assert first["ok"], first
    from nl_coding_agent.context.engine import ContextEngine
    assert ContextEngine(project["id"], root).latest_summary(None), \
        "the long session must persist a digest"

    provider2 = Provider([{"content": "continuing"}])
    monkeypatch.setattr(services, "_resolve_chat_provider",
                        lambda *a, **kw: (provider2, "model", "test", ""))
    session_two = services.create_chat_session(project["id"], "new session")["id"]
    second = services.chat_conversation(
        project, "What did we do before?", tools_enabled=True,
        model_spec="test/model", session_id=session_two)
    assert second["ok"], second
    injected = json.dumps(provider2.requests[0][0], ensure_ascii=False)
    assert "EARLIER CONVERSATION DIGEST" in injected
    assert "previous session" in injected


def test_long_tool_turn_is_compacted_instead_of_failing(chat):
    """A long tool turn is compacted with a persisted digest, not refused."""
    services, project, run = chat
    root = Path(project["root"])
    for index in range(8):
        (root / f"big{index}.py").write_text(
            ("x = 1  # padding line for the context budget test\n" * 400),
            encoding="utf-8")

    def read(index):
        return lambda tools: call("read_source", path=f"big{index}.py")

    responses = [read(index) for index in range(8)] + [{"content": "Final summary."}]
    result, provider = run(responses, text="Read all big files, then summarize", max_calls=24)
    assert result["ok"], result
    assert result["reply"] == "Final summary."
    final_messages = provider.requests[-1][0]
    # The prompt fits the dynamically derived budget (chars are bounded by the
    # calibrated ratio; never the old fixed 60k wall).
    assert len(json.dumps(final_messages, ensure_ascii=False)) < 200_000
    state = load_state(project["id"])
    assert any(item.get("tool") == "context" for item in state.get("activity", []))
    from nl_coding_agent.context.engine import ContextEngine
    summary = ContextEngine(project["id"], root).latest_summary("")
    assert summary and summary["summary"]



def test_source_tool_and_result_interpretation(chat):
    services, project, run = chat
    result, provider = run([call("read_source", path="calc.py"), {"content": "value vale 7"}])
    assert result["ok"]
    tool_result = next(item for item in reversed(provider.requests[1][0]) if item["role"] == "tool")
    assert "value = 7" in tool_result["content"]
    assert json.loads(tool_result["content"])["untrusted"]
    assert services.list_chat_messages(project_id=project["id"])[-1]["role"] == "assistant"


def test_followup_replays_persisted_research_attachment_and_uses_github_lookup(chat, monkeypatch):
    from nl_coding_agent.app.attachments import prepare_text

    services, project, run = chat
    saved = prepare_text(
        "Repository: acme/demo\nREADME:\n# Demo project\nThis repository contains the actual source.",
        name="github:acme/demo",
        project_id=project["id"])
    first, _ = run([{"content": "What would you like to know?"}],
                   text="https://github.com/acme/demo",
                   attachment_ids=[saved["id"]])
    assert first["ok"]

    observed = {}

    def github_lookup(**kwargs):
        observed.update(kwargs)
        return {"ok": True, "untrusted": True,
                "result": {"kind": "readme", "data": {"text": "# Demo project"}}}

    monkeypatch.setattr(services, "research_github_lookup", github_lookup)

    def request_readme(tools):
        github_tool = next(tool for tool in tools
                           if tool["function"]["name"] == "github_lookup")
        assert "contents" in github_tool["function"]["parameters"]["properties"]["action"]["enum"]
        return call("github_lookup", action="readme", full_name="acme/demo")

    result, provider = run([request_readme, {"content": "The README describes the demo project."}],
                           text="Explore it and tell me what you find")
    assert result["ok"]
    assert observed == {"action": "readme", "full_name": "acme/demo", "query": None,
                        "path": None, "ref": None, "number": None, "state": "open",
                        "limit": 20, "project_id": project["id"]}
    prior_user = next(message for message in provider.requests[0][0]
                      if message["role"] == "user" and "github.com/acme/demo" in message["content"])
    assert "This repository contains the actual source." in prior_user["content"]
    tool_output = next(message for message in provider.requests[1][0]
                       if message["role"] == "tool")
    assert "# Demo project" in tool_output["content"]
    assert json.loads(tool_output["content"])["untrusted"] is True


def test_general_web_research_searches_then_fetches_a_page(chat, monkeypatch):
    services, project, run = chat
    permissions.set_access_mode("auto-review")
    observed_search = {}

    def search(**kwargs):
        observed_search.update(kwargs)
        return {"ok": True, "untrusted": True, "results": [{
            "title": "Example page", "url": "https://example.com/page",
            "snippet": "A public example page."}]}

    class FakeResearchService:
        _fetch_transport = object()
        profile = ""

        def fetch_read(self, url, *, project_id):
            return {"operation": "fetch_read", "outcome": "allowed",
                    "allowed": True, "capability": "web-fetch",
                    "payload": {"url": url, "text": "Retrieved page body.",
                                "untrusted": True}}

    monkeypatch.setattr(services, "research_search", search)
    monkeypatch.setattr(services, "_research_service", lambda: FakeResearchService())
    query = "Who publishes the example page?"

    def search_tool(tools):
        names = {tool["function"]["name"] for tool in tools}
        assert {"web_search", "fetch_url", "github_lookup"} <= names
        return call("web_search", query=query, search_type="web", max_results=3)

    def fetch_tool(tools):
        return call("fetch_url", url="https://example.com/page")

    provider = None
    result, provider = run(
        [search_tool, fetch_tool, {"content": "The example page publishes this content."}],
        text=query)
    assert result["ok"]
    system = next(message["content"] for message in provider.requests[0][0]
                  if message["role"] == "system")
    assert "general web research" in system
    assert observed_search == {
        "query": query, "search_type": "web", "max_results": 3,
        "project_id": project["id"]}
    search_output = next(message["content"] for message in provider.requests[1][0]
                         if message["role"] == "tool")
    assert "https://example.com/page" in search_output
    fetch_output = [message["content"] for message in provider.requests[2][0]
                    if message["role"] == "tool"][-1]
    assert "Retrieved page body." in fetch_output
    assert json.loads(fetch_output)["untrusted"] is True


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
    permissions.set_access_mode("read-only")
    result, _ = run([call("read_source", path="calc.py"), {"content": "Read only still allows analysis"}])
    assert result["ok"]


def test_duplicate_call_ids_fail_before_any_invocation(chat):
    services, project, run = chat
    response = call("read_source", path="calc.py")
    response["tool_calls"][0]["id"] = "duplicate"
    response["tool_calls"] *= 2
    result, _ = run([response])
    assert not result["ok"] and "Duplicate" in result["reply"]
    assert load_state(project["id"])["used_calls"] == 0


def test_concurrent_queue_enqueues_preserve_every_message(chat, monkeypatch):
    from nl_coding_agent.app import chat_tools

    services, project, _ = chat
    original_load_queue = chat_tools.load_queue

    def delayed_load(project_id):
        items = original_load_queue(project_id)
        time.sleep(0.01)
        return items

    monkeypatch.setattr(chat_tools, "load_queue", delayed_load)

    def enqueue(index):
        return chat_tools.enqueue(services, project["id"], f"queued {index}")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(enqueue, range(24)))

    queued = chat_tools.list_queue(project["id"])
    assert queued["count"] == 24
    assert {item["text"] for item in queued["items"]} == {
        f"queued {index}" for index in range(24)
    }


def test_vision_handoff_requires_measured_capability_and_sends_image_to_specialist(chat, monkeypatch):
    from types import SimpleNamespace
    from nl_coding_agent.app import attachments
    from nl_coding_agent.models.capabilities import CapabilityRecord, record_capabilities

    services, project, _ = chat
    image = attachments.AttachmentStore().prepare_clipboard_image(
        _one_pixel_png(), project_id=project["id"])

    class VisionProvider:
        provider_id = "ollama"
        kind = "ollama"
        base_url = "http://127.0.0.1:11434"

        def __init__(self):
            self.calls = []

        def generate(self, model, prompt, **kwargs):
            self.calls.append((model, kwargs))
            return "A red one-pixel image."

    provider = VisionProvider()
    snapshot = SimpleNamespace(providers=[SimpleNamespace(
        provider_id="ollama", reachable=True, base_url=provider.base_url,
        models=[SimpleNamespace(name="vision-model", size_gb=1.0)]
    )])
    monkeypatch.setattr(services, "discover_models", lambda **kwargs: snapshot)
    monkeypatch.setattr(services, "get_model_config", lambda: {"providers": {
        "ollama": {"kind": "ollama", "enabled": True,
                  "base_url": provider.base_url}
    }})
    monkeypatch.setattr("nl_coding_agent.app.services.build_providers", lambda config: [provider])

    refused = services._vision_handoff(project["id"], [image])
    assert refused and not refused["ok"]
    assert provider.calls == []

    record_capabilities([CapabilityRecord(
        "ollama", "vision-model", "vision", "measured")])
    handoff = services._vision_handoff(project["id"], [image])
    assert handoff and handoff["ok"]
    assert handoff["model"] == "vision-model"
    assert handoff["analysis"] == "A red one-pixel image."
    messages = provider.calls[0][1]["messages"]
    assert len(messages[0]["images"]) == 1
    assert messages[0]["content"].startswith("Analyze the attached user images")


def test_chat_passes_vision_handoff_as_untrusted_text(chat, monkeypatch):
    services, project, _ = chat
    observed = {}
    monkeypatch.setattr(services, "_vision_handoff", lambda project_id, attachments: {
        "ok": True, "provider_id": "ollama", "model": "vision-model",
        "analysis": "The screenshot shows a red error banner."
    })

    def fake_reply(**kwargs):
        observed["text"] = kwargs["text"]
        return {"reply": "I can see the error banner.", "route": {
            "provider_id": "ollama", "model": "chat-model", "automatic": False
        }}

    monkeypatch.setattr(services, "_chat_reply", fake_reply)
    result = services.chat_conversation(
        project, "What is shown?", model_spec="ollama/chat-model", tools_enabled=False)

    assert result["ok"]
    assert result["vision"]["model"] == "vision-model"
    assert "UNTRUSTED vision-specialist handoff" in observed["text"]
    assert "The screenshot shows a red error banner." in observed["text"]


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


def test_discovered_tools_use_global_mode_without_an_allowlist(chat, monkeypatch):
    from nl_coding_agent.app import mcp
    services, project, run = chat
    config = {"servers": {"fixture": {"command": "never-start", "trusted": True, "allowed_tools": ["echo"]}}}
    monkeypatch.setattr(mcp, "load_mcp_config", lambda: config)
    monkeypatch.setattr(mcp.McpManager, "list_tools", lambda *a: [{"name": "echo", "qualified_name": "fixture::echo",
        "description": "Echo", "input_schema": {"type": "object"}}])
    monkeypatch.setattr(mcp.McpManager, "invoke_tool", lambda *a, **kw: {"content": [{"type": "text", "text": "allowed by global mode"}]})
    def selected(tools):
        config["servers"]["fixture"].pop("allowed_tools")
        name = next(t["function"]["name"] for t in tools if t["function"]["name"].startswith("mcp_"))
        return call(name)
    result, provider = run([call("discover_mcp", server="fixture"), selected, {"content": "Tool denied"}])
    assert result["ok"]
    assert "allowed by global mode" in provider.requests[-1][0][-1]["content"]

def test_natural_language_coding_request_starts_one_mission(chat, monkeypatch):
    """A clear build request must not require /apply or /runplan."""
    services, project, run = chat
    permissions.set_access_mode("workspace-write")
    permissions.set_access_mode("workspace-write")
    started = []
    teams = []
    monkeypatch.setattr(services, "run_mission",
                        lambda mission_id, root, **kwargs: started.append((mission_id, kwargs)))
    monkeypatch.setattr(services, "assign_project_team",
                        lambda project_id, roles: teams.append((project_id, roles)))
    monkeypatch.setattr("nl_coding_agent.app.services.project_team_agents", lambda project_id: [])
    result, _ = run([{"content": "Va bene, procedo."}],
                    text="Aggiungi una funzione subtract a calc.py che restituisce a meno b",
                    allow_coding=True)
    assert result["ok"], result
    assert result["missions"], result
    assert "Missione #" in result["reply"] and "in coda" in result["reply"]
    assert len(started) == 1
    assert started[0][0] == result["missions"][0]
    assert teams and teams[0][0] == project["id"]
    assert any(role.get("role_id") == "developer" for role in teams[0][1])
    rows = services.list_missions(project["id"])
    assert rows and rows[0]["goal"].startswith("Aggiungi una funzione subtract")

def test_natural_language_question_does_not_start_mission(chat, monkeypatch):
    services, project, run = chat
    permissions.set_access_mode("workspace-write")
    permissions.set_access_mode("workspace-write")
    monkeypatch.setattr(services, "run_mission", lambda *a, **kw: pytest.fail("question started a mission"))
    result, _ = run([{"content": "Sette."}],
                    text="Come funziona attualmente calc.py?", allow_coding=True)
    assert result["ok"]
    assert result["missions"] == []

def test_chat_queue_is_durable_fifo_and_reorderable(chat):
    from nl_coding_agent.app import chat_tools
    services, project, run = chat
    for text in ("prima", "seconda", "terza"):
        chat_tools.enqueue(services, project["id"], text)
    first = chat_tools.take_next(project["id"])
    assert first and first["text"] == "prima"
    remaining = chat_tools.list_queue(project["id"])["items"]
    assert [item["text"] for item in remaining] == ["seconda", "terza"]
    reordered = chat_tools.reorder_queue(project["id"], [remaining[1]["id"], remaining[0]["id"]])
    assert [item["text"] for item in reordered["items"]] == ["terza", "seconda"]
    chat_tools.remove_queued(project["id"], reordered["items"][0]["id"])
    assert [item["text"] for item in chat_tools.list_queue(project["id"])["items"]] == ["seconda"]

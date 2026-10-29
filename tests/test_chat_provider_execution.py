"""Behavioral chat integration: real loopback HTTP, durable context and route gates.

HTTP responses here are synthetic; live Ollama acceptance is recorded separately.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.core import permissions
from nl_coding_agent.models.providers import OllamaProvider, OpenAICompatibleProvider
from nl_coding_agent.projects.registry import open_project


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))
    root = tmp_path / "project"
    root.mkdir()
    project = open_project(root)
    services = AppServices()
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            calls.append(("GET", self.path, None))
            if self.path.endswith("/models"):
                payload = {"data": [{"id": "demo"}]}
            elif self.path == "/api/tags":
                payload = {"models": [{"name": "demo", "size": 1}]}
            elif self.path == "/api/ps":
                payload = {"models": []}
            else:
                payload = {"version": "test"}
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(("POST", self.path, body))
            payload = ({"message": {"content": "Ollama response"}} if self.path == "/api/chat"
                       else {"choices": [{"message": {"content": "Compatible response"}}]})
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:" + str(server.server_port)
    monkeypatch.setattr(services, "get_model_config", lambda: {
        "providers": {"local": {"kind": "ollama", "base_url": base}},
        "roles": {"chat": {"model": "local/demo"}}})
    yield services, project, calls, base
    services._db.close()
    server.shutdown(); server.server_close(); thread.join(3)


def test_chat_uses_actual_provider_and_history_survives_restart(context):
    services, project, calls, _ = context
    assert services.chat_conversation(project, "Remember violet")["reply"] == "Ollama response"
    rebuilt = AppServices()
    rebuilt.get_model_config = services.get_model_config
    try:
        result = rebuilt.chat_conversation(project, "Which color?")
        assert result["ok"], result
        posts = [body for method, path, body in calls if method == "POST"]
        assert [m["role"] for m in posts[-1]["messages"]] == ["system", "user", "assistant", "user"]
        assert posts[-1]["messages"][1]["content"] == "Remember violet"
        assert len(result["messages"]) == 4
        assert services.list_missions(project["id"]) == []
    finally:
        rebuilt._db.close()


def test_compatible_generation_uses_chat_completions(context):
    _, project, calls, base = context
    provider = OpenAICompatibleProvider("local", "Local API", base + "/v1")
    assert provider.generate("demo", "Hello", project_id=project["id"]) == "Compatible response"
    assert calls[-1][1] == "/v1/chat/completions"


def test_explicit_chat_route_overrides_default_without_fallback(context, monkeypatch):
    services, project, calls, _ = context
    config = services.get_model_config()
    config["roles"]["chat"]["model"] = "unavailable/other"
    monkeypatch.setattr(services, "get_model_config", lambda: config)
    assert services.chat_conversation(project, "Hello", model_spec="local/demo")["ok"]
    assert [body for method, _, body in calls if method == "POST"][-1]["model"] == "demo"


def test_followup_replays_scoped_attachment_context_after_restart(context):
    services, project, calls, _ = context
    attachment = services.prepare_attachment_text(project["id"], "def violet_token(): return 47")
    assert services.chat_conversation(project, "Read this function", [attachment["id"]])["ok"]
    rebuilt = AppServices()
    rebuilt.get_model_config = services.get_model_config
    try:
        assert rebuilt.chat_conversation(project, "What value did it return?")["ok"]
        messages = [body for method, _, body in calls if method == "POST"][-1]["messages"]
        assert "def violet_token(): return 47" in messages[1]["content"]
        assert "UNTRUSTED attachment" in messages[1]["content"]
    finally:
        rebuilt._db.close()


def test_unknown_route_never_falls_back_or_performs_io(context, monkeypatch):
    services, project, calls, _ = context
    config = services.get_model_config()
    config["roles"]["chat"]["model"] = "missing/demo"
    monkeypatch.setattr(services, "get_model_config", lambda: config)
    result = services.chat_conversation(project, "private project context")
    assert not result["ok"]
    assert "Unknown or disabled" in result["reply"]
    assert calls == []
    assert [m["role"] for m in services.list_chat_messages(project_id=project["id"])] == ["user"]


@pytest.mark.parametrize("kind,url,model", [
    ("ollama", "http://127.0.0.1:11434", "some:cloud"),
    ("openai_compatible", "https://external.invalid/v1", "model")])
def test_denied_cloud_route_is_blocked_before_probe(context, monkeypatch, kind, url, model):
    services, project, calls, _ = context
    monkeypatch.setattr(services, "get_model_config", lambda: {
        "providers": {"remote": {"kind": kind, "base_url": url}},
        "roles": {"chat": {"model": "remote/" + model}}})
    monkeypatch.setattr(OllamaProvider, "probe", lambda *a, **kw: pytest.fail("Discovery before authorization"))
    monkeypatch.setattr(OpenAICompatibleProvider, "probe", lambda *a, **kw: pytest.fail("Discovery before authorization"))
    result = services.chat_conversation(project, "private source")
    assert not result["ok"] and result["error"]["type"] == "PermissionDenied"
    assert calls == []


def test_remote_named_model_requires_cloud_even_with_network_grant(context):
    _, project, _, _ = context
    permissions.grant(permissions.NETWORK, project_id=project["id"])
    provider = OpenAICompatibleProvider("api", "API", "https://external.invalid/v1")
    with pytest.raises(permissions.PermissionDenied):
        provider.generate("ordinary-name", "private source", project_id=project["id"])


def test_cross_project_attachments_are_refused_without_io(context, tmp_path):
    services, project, calls, _ = context
    other = tmp_path / "other"; other.mkdir()
    other_project = open_project(other)
    item = services.prepare_attachment_text(other_project["id"], "private other-project text")
    result = services.chat_conversation(project, "summarize", [item["id"]])
    assert not result["ok"] and "another project" in result["reply"]
    assert calls == []
    assert services.list_chat_messages(project_id=project["id"]) == []


def test_corrupt_history_is_preserved_and_not_replaced(context):
    services, project, calls, _ = context
    path = services._chat_history_path(project["id"])
    path.write_text("{broken history")
    result = services.chat_conversation(project, "Hello")
    assert not result["ok"]
    assert path.read_text() == "{broken history"
    assert calls == []

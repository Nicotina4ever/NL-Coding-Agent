"""Persistent generation parameters; optional explicit Ollama context override."""
from __future__ import annotations

import pytest

from nl_coding_agent.models import generation_params as gp


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.persistence import database
    database.init_db().close()
    return tmp_path / "data"


def test_merge_global_role_model_and_persist(db):
    gp.save_params({"temperature": 0.4}, scope="global")
    gp.save_params({"top_p": 0.8}, scope="role", role="developer")
    gp.save_params({"top_k": 32, "seed": 7}, scope="model",
                   model_name="ollama/qwen3.5:9b")
    effective = gp.effective_params(model_name="ollama/qwen3.5:9b", role="developer")
    assert effective == {"temperature": 0.4, "top_p": 0.8, "top_k": 32, "seed": 7}
    assert gp.effective_params(model_name="other") == {"temperature": 0.4}


def test_num_ctx_is_optional_and_only_forwarded_when_set(db):
    gp.save_params({"num_ctx": 8192}, scope="model", model_name="m")
    assert gp.effective_params(model_name="m") == {"num_ctx": 8192}
    gp.save_params({"num_ctx": None}, scope="model", model_name="m")
    assert gp.effective_params(model_name="m") == {}


def test_validation_ranges_and_unknown_keys(db):
    with pytest.raises(gp.GenerationParamsError):
        gp.save_params({"temperature": 3.0}, scope="model", model_name="m")
    with pytest.raises(gp.GenerationParamsError):
        gp.save_params({"top_k": -1}, scope="model", model_name="m")
    with pytest.raises(gp.GenerationParamsError):
        gp.save_params({"invented": 1}, scope="model", model_name="m")


def test_null_removes_value(db):
    gp.save_params({"temperature": 0.3, "top_p": 0.9}, scope="model", model_name="m")
    gp.save_params({"temperature": None}, scope="model", model_name="m")
    assert gp.effective_params(model_name="m") == {"top_p": 0.9}


def test_make_llm_omits_context_until_explicitly_configured(db, monkeypatch):
    import nl_coding_agent.agents.orchestrator as orchestrator

    recorded = {}

    class FakeLLM:
        def __init__(self, **kwargs):
            recorded.update(kwargs)

    monkeypatch.setattr(orchestrator, "LLM", FakeLLM)
    orchestrator._make_llm("ollama/qwen3.5:9b", role="developer")
    assert "extra_body" not in recorded
    assert "num_ctx" not in str(recorded)

    gp.save_params({"temperature": 0.2, "top_k": 20, "num_ctx": 16384},
                   scope="role", role="developer")
    orchestrator._make_llm("ollama/qwen3.5:9b", role="developer")
    assert recorded["temperature"] == 0.2
    assert recorded["top_k"] == 20
    assert recorded["num_ctx"] == 16384
    assert "extra_body" not in recorded


def test_make_llm_resolves_custom_provider_route_and_keeps_project_access_gate(
        db, tmp_path, monkeypatch):
    import nl_coding_agent.agents.orchestrator as orchestrator
    from nl_coding_agent.core.permissions import PermissionDenied
    from nl_coding_agent.models import model_config_store

    config_path = tmp_path / "models.yaml"
    monkeypatch.setenv("NL_MODELS_CONFIG", str(config_path))
    monkeypatch.setenv("LOCAL_TEST_API_KEY", "local-test-key")
    config = {
        "providers": {
            "custom_local": {
                "kind": "openai_compatible",
                "enabled": True,
                "base_url": "http://127.0.0.1:1234/v1",
                "api_key_env": "LOCAL_TEST_API_KEY",
            },
        },
        "roles": {},
    }
    model_config_store.save(config, config_path)
    captured = {}

    class FakeLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(orchestrator, "LLM", FakeLLM)
    orchestrator._make_llm(
        "custom_local/assigned-model", project_id=41, role="developer")
    assert captured["model"] == "openai/assigned-model"
    assert captured["base_url"] == "http://127.0.0.1:1234/v1"
    assert captured["api_key"] == "local-test-key"

    config["providers"]["custom_local"]["base_url"] = "https://models.example/v1"
    model_config_store.save(config, config_path)
    with pytest.raises(PermissionDenied) as exc_info:
        orchestrator._make_llm("custom_local/assigned-model", project_id=41)
    assert exc_info.value.scope == "network"


def test_ollama_provider_omits_context_until_configured(db, monkeypatch):
    from nl_coding_agent.models import providers

    captured = {}

    def fake_post(url, body, timeout):
        captured.update(body)
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(providers, "_post_json", fake_post)
    provider = providers.OllamaProvider()
    provider._capabilities = {"qwen3.5:9b": ("tools", "completion")}
    provider.chat_turn("qwen3.5:9b", [{"role": "user", "content": "hi"}], [])
    assert "num_ctx" not in str(captured)
    assert "options" not in captured

    gp.save_params({"temperature": 0.2, "top_k": 10, "num_ctx": 32768},
                   scope="role", role="chat")
    provider.chat_turn("qwen3.5:9b", [{"role": "user", "content": "hi"}], [])
    assert captured["options"] == {"temperature": 0.2, "top_k": 10, "num_ctx": 32768}


def test_crewai_ollama_context_override_reaches_the_http_request(db, monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from nl_coding_agent.agents.orchestrator import _make_llm
    from nl_coding_agent.models import model_config_store
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({"model": "test", "message": {"role": "assistant", "content": "ok"},
                               "done": True, "prompt_eval_count": 2, "eval_count": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(model_config_store, "load", lambda *a, **kw: {"providers": {"ollama": {"base_url": base}}})
    gp.save_params({"num_ctx": 8192}, scope="global")
    try:
        llm = _make_llm("ollama/test", role="developer")
        assert llm.call([{"role": "user", "content": "hi"}]) == "ok"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
    assert requests and requests[0]["options"]["num_ctx"] == 8192

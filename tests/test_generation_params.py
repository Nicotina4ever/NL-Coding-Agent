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
    assert recorded["extra_body"] == {"options": {"top_k": 20, "num_ctx": 16384}}


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

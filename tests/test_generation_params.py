"""Persistent generation parameters; Ollama context stays server-owned."""
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


def test_num_ctx_is_rejected_not_forwarded(db):
    with pytest.raises(gp.GenerationParamsError, match="num_ctx"):
        gp.save_params({"num_ctx": 8192}, scope="model", model_name="m")


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


def test_make_llm_sends_only_configured_params_without_num_ctx(db, monkeypatch):
    import nl_coding_agent.agents.orchestrator as orchestrator

    recorded = {}

    class FakeLLM:
        def __init__(self, **kwargs):
            recorded.update(kwargs)

    monkeypatch.setattr(orchestrator, "LLM", FakeLLM)
    orchestrator._make_llm("ollama/qwen3.5:9b", role="developer")
    assert "extra_body" not in recorded
    assert "num_ctx" not in str(recorded)

    gp.save_params({"temperature": 0.2, "top_k": 20}, scope="role", role="developer")
    orchestrator._make_llm("ollama/qwen3.5:9b", role="developer")
    assert recorded["temperature"] == 0.2
    assert recorded["extra_body"] == {"options": {"top_k": 20}}
    assert "num_ctx" not in str(recorded)


def test_ollama_provider_does_not_send_num_ctx(db, monkeypatch):
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

    gp.save_params({"temperature": 0.2, "top_k": 10}, scope="role", role="chat")
    provider.chat_turn("qwen3.5:9b", [{"role": "user", "content": "hi"}], [])
    assert captured["options"] == {"temperature": 0.2, "top_k": 10}
    assert "num_ctx" not in str(captured)

"""P4: Chat route ranking uses the same ModelRouter evidence as Mission roles."""
from __future__ import annotations

from types import SimpleNamespace

from nl_coding_agent.app import services as services_module


def _provider(provider_id="ollama", base_url="http://127.0.0.1:11434"):
    return SimpleNamespace(
        provider_id=provider_id, base_url=base_url, kind="ollama",
        assert_generation_permitted=lambda *a, **k: None,
        probe=lambda timeout=5.0: SimpleNamespace(
            reachable=True,
            models=[SimpleNamespace(name="model-a"), SimpleNamespace(name="model-b")],
            error=""),
    )


def _fake_binding(provider_id="ollama", model_name="model-b"):
    return SimpleNamespace(
        provider_id=provider_id, model_name=model_name,
        selection={"strategy": "measured_capabilities+historical_results", "score": 77.0},
        capabilities={"tool_calling": {"supported": True, "source": "probe"}},
    )


def test_chat_route_ranking_is_recorded_and_ordered(monkeypatch):
    first, second = _provider(), _provider()
    monkeypatch.setattr(
        services_module.AppServices, "_chat_candidates",
        lambda self, spec: [
            {"provider": first, "model": "model-a", "provider_id": "ollama",
             "spec": "ollama/model-a", "cloud": False},
            {"provider": second, "model": "model-b", "provider_id": "ollama",
             "spec": "ollama/model-b", "cloud": False},
        ])
    monkeypatch.setattr(
        services_module.AppServices, "_rank_chat_candidates",
        lambda self, candidates, project_id=None, tools_enabled=False, preserve_order=False: (
            list(reversed(candidates)),
            {"strategy": "model_router.auto_select", "role": "chat",
             "selected": "ollama/model-b", "tools_enabled": tools_enabled},
        ))
    service = services_module.AppServices()
    try:
        provider, model, provider_id, error = service._resolve_chat_provider(
            "auto", project_id=None, tools_enabled=True)
        assert not error
        assert model == "model-b"
        assert provider_id == "ollama"
        routing = service._last_chat_routing
        assert routing["strategy"] == "model_router.auto_select"
        assert routing["tools_enabled"] is True
        assert routing["resolved_spec"] == "ollama/model-b"
    finally:
        service._db.close()


def test_chat_ranking_uses_model_router(monkeypatch):
    provider = _provider()
    candidates = [{"provider": provider, "model": "model-a",
                   "provider_id": "ollama", "spec": "ollama/model-a", "cloud": False}]
    binding = _fake_binding()

    class _Router:
        def __init__(self, *a, **k):
            pass

        def auto_select(self, role, items, **kwargs):
            assert role == "chat"
            assert kwargs["prefer_capabilities"][0] == "tool_calling"
            return binding

    monkeypatch.setattr("nl_coding_agent.models.model_router.ModelRouter", _Router)
    service = services_module.AppServices()
    try:
        ranked, routing = service._rank_chat_candidates(
            candidates, project_id=None, tools_enabled=True)
        assert routing["strategy"] == "model_router.auto_select"
        assert routing["selected"] == "ollama/model-b"
        assert ranked[0]["model"] == "model-a"
        assert ranked[0]["routing"]["role"] == "chat"
    finally:
        service._db.close()


def test_chat_ranking_falls_back_to_configured_order(monkeypatch):
    provider = _provider()
    candidates = [{"provider": provider, "model": "model-a",
                   "provider_id": "ollama", "spec": "ollama/model-a", "cloud": False}]

    class _Router:
        def __init__(self, *a, **k):
            pass

        def auto_select(self, role, items, **kwargs):
            raise RuntimeError("capability probe unavailable")

    monkeypatch.setattr("nl_coding_agent.models.model_router.ModelRouter", _Router)
    service = services_module.AppServices()
    try:
        ranked, routing = service._rank_chat_candidates(candidates)
        assert routing["strategy"] == "configured_order"
        assert "capability probe unavailable" in routing["reason"]
        assert ranked[0]["model"] == "model-a"
    finally:
        service._db.close()

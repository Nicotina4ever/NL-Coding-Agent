import pytest
from nl_coding_agent.core import permissions
from nl_coding_agent.models.capabilities import CapabilityRecord
from nl_coding_agent.models.model_router import ModelRouter, RouteRefused, RouteResourceUnavailable


def _caps(model="m1"):
    from types import SimpleNamespace
    return {model: "x"}


def test_router_resolution_refusals_fallback_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.persistence import database
    database.init_db().close()
    from nl_coding_agent.models.capabilities import CapabilitySet
    measured = CapabilitySet("ollama", "local-a", {"tool_calling": CapabilityRecord("ollama", "local-a", "tool_calling", "measured")})
    router = ModelRouter(role_bindings={"developer": {"provider_id": "ollama", "model_name": "local-a", "base_url": "http://127.0.0.1:11434"}},
                         fallback_chain=[{"provider_id": "cloud", "model_name": "gpt-cloud", "base_url": "https://api.example.com"}],
                         capability_records={("ollama", "local-a"): measured}, project_id=None)
    binding = router.resolve("developer", required_capabilities=["tool_calling"])
    assert binding.model_name == "local-a" and binding.source in ("role_config", "fallback")
    assert router.resolve("developer", override={"model_name": "local-a"}).source == "explicit_override"
    with pytest.raises(RouteRefused):
        ModelRouter(role_bindings={}).resolve("developer")
    with pytest.raises(RouteRefused):
        ModelRouter(role_bindings={"developer": {"model_name": "local-a"}},
                    capability_records={("ollama", "local-a"): CapabilitySet("ollama", "local-a", {})}).resolve(
                        "developer", required_capabilities=["vision"])
    assert router.record_mission_snapshot(1, {"developer": binding}) == 1
    assert router.load_mission_snapshot(1)["developer"]["model_name"] == "local-a"
    class Wait:
        action = "wait"; reason = "busy"
    with pytest.raises(RouteResourceUnavailable):
        ModelRouter(role_bindings={"developer": {"model_name": "local-a"}},
                    capability_records={("ollama", "local-a"): measured},
                    resource_gate=lambda: Wait()).resolve("developer")

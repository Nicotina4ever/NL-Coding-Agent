"""Permission-checked, role-aware local recovery after an exhausted model route."""
from nl_coding_agent.core.permissions import is_cloud_model, is_remote_endpoint


def cloud_route(route, config):
    provider_id, _, model = str(route).partition("/")
    provider = (config.get("providers") or {}).get(provider_id) or {}
    return is_cloud_model(model or route) or is_remote_endpoint(provider.get("base_url") or "")


def local_equivalent(role, failed_route, project_id, config=None):
    from nl_coding_agent.models.model_config_store import load
    from nl_coding_agent.models.model_router import ModelRouter
    from nl_coding_agent.models.ollama_registry import list_models
    config = config or load()
    ollama = (config.get("providers") or {}).get("ollama") or config.get("ollama") or {}
    endpoint = ollama.get("base_url") or "http://127.0.0.1:11434"
    if is_remote_endpoint(endpoint) or ollama.get("enabled") is False:
        raise ValueError("No enabled local Ollama recovery route")
    models = [model for model in list_models(endpoint, timeout=5) if
              not is_cloud_model(model.name) and "embed" not in model.name.lower()
              and "ollama/" + model.name != failed_route]
    try:
        from nl_coding_agent.core.resource_monitor import snapshot
        budget = max([float(item.get("total_mb") or 0) for item in snapshot().get("gpus", [])] or [0]) / 1024
        fits = [model for model in models if not model.size_gb or model.size_gb <= budget * .85]
        if fits:
            models = fits
    except Exception:
        pass
    models.sort(key=lambda model: (0 if "coder" in model.name.lower() and role in ("developer", "debugger") else 1, model.size_gb))
    preferred = ("tool_calling", "structured_output", "patch_quality") if role in ("developer", "debugger") else ("structured_output", "reasoning")
    router = ModelRouter(project_id=project_id)
    binding = router.auto_select(role,
        [{"provider_id": "ollama", "model_name": model.name, "base_url": endpoint} for model in models],
        prefer_capabilities=preferred, project_id=project_id)
    if not binding.selection.get("attempts") and not binding.selection.get("capability_score"):
        # Unknown evidence must not turn an alphabetical model name into a
        # quality ranking. Prefer a coding family, then an already loaded/small
        # compatible model, without pretending this is a measured capability.
        models.sort(key=lambda model: (0 if "coder" in model.name.lower() and role in ("developer", "debugger") else 1,
                                       not bool(model.loaded), model.size_gb))
        if models:
            binding = router.auto_select(role,
                [{"provider_id": "ollama", "model_name": models[0].name, "base_url": endpoint}],
                prefer_capabilities=preferred, project_id=project_id)
    return binding

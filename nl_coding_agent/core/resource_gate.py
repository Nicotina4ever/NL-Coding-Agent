"""Minimal local resource/permission gate for the C3 supervisor (C3c).

The supervisor never starts a mission that cannot run safely:

* base scopes (READ/WRITE/EXECUTE) and model-route permissions are checked through
  nl_coding_agent.core.permissions (no bypass);
* local Ollama reachability and the configured role models are probed through the
  existing registry (read-only: no model is loaded or downloaded here);
* a machine-wide "inference" lease serializes local inference across projects that
  share the app-data database.

Unknown telemetry stays unknown; nothing here invents VRAM numbers or kills
processes. Full resource-aware scheduling remains NL-BP-070/071 (stage 4).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nl_coding_agent.models import ollama_registry
from nl_coding_agent.persistence import supervisor_store

__all__ = [
    "ResourceDecision", "probe_local_models", "missing_role_models",
    "acquire_inference_slot", "release_inference_slot", "decide",
]

INFERENCE_RESOURCE = "inference"
DEFAULT_RETRY_AFTER_S = 30


@dataclass
class ResourceDecision:
    action: str                    # "run" | "wait" | "blocked"
    reason: str = ""
    retry_after_s: int | None = None
    observed: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "retry_after_s": self.retry_after_s,
            "observed": dict(self.observed or {}),
        }


def _config_value(config, name: str, default=None):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def _raw_model_name(model_name) -> str:
    text = str(model_name or "").strip()
    if text.startswith("ollama/"):
        return text[len("ollama/"):]
    return text


def _required_models(config) -> list[str]:
    required: list[str] = []
    for field_name in ("developer_model", "reviewer_model", "debug_model"):
        raw = _raw_model_name(_config_value(config, field_name, ""))
        if raw and raw not in required:
            required.append(raw)
    return required


def _backoff(config) -> int:
    schedule = _config_value(config, "backoff_schedule_s", (30, 120, 600, 1800))
    try:
        values = [int(item) for item in schedule]
    except (TypeError, ValueError):
        values = [DEFAULT_RETRY_AFTER_S]
    positive = [value for value in values if value >= 0]
    return positive[0] if positive else DEFAULT_RETRY_AFTER_S


def probe_local_models(config) -> dict:
    """Probe Ollama reachability and available model names without loading anything."""
    base_url = ollama_registry.OLLAMA_BASE_URL
    required = _required_models(config)
    observed: dict = {
        "base_url": base_url,
        "required_models": list(required),
        "reachable": False,
        "available_models": [],
        "loaded_models": [],
        "missing_models": list(required),
        "error": "",
    }
    try:
        reachable = bool(ollama_registry.check_ollama_reachable(base_url))
    except Exception as exc:  # pragma: no cover - defensive
        observed["error"] = str(exc)
        return observed
    observed["reachable"] = reachable
    if not reachable:
        observed["error"] = "Ollama is not reachable at " + str(base_url)
        return observed
    try:
        available = [model.name for model in ollama_registry.list_models(base_url)]
        loaded = [model.name for model in ollama_registry.list_loaded_models(base_url)]
    except Exception as exc:
        observed["error"] = "Ollama discovery failed: " + str(exc)
        return observed
    observed["available_models"] = list(available)
    observed["loaded_models"] = list(loaded)
    available_set = set(available)
    observed["missing_models"] = [name for name in required if name not in available_set]
    return observed


def missing_role_models(config, available: list[str] | None = None) -> list[str]:
    required = _required_models(config)
    if available is None:
        observed = probe_local_models(config)
        available = list(observed.get("available_models") or [])
    available_set = set(available)
    return [name for name in required if name not in available_set]


def acquire_inference_slot(owner_id: str, owner_pid: int, owner_host: str, *,
                           ttl_s: float) -> bool:
    try:
        lease = supervisor_store.acquire_machine_lease(
            INFERENCE_RESOURCE,
            owner_id=owner_id,
            owner_pid=int(owner_pid),
            owner_host=str(owner_host),
            ttl_s=float(ttl_s),
        )
    except supervisor_store.StoreError:
        return False
    return lease is not None


def release_inference_slot(owner_id: str) -> None:
    supervisor_store.release_machine_lease(INFERENCE_RESOURCE, owner_id=owner_id)


def _model_permission_blocker(config, project_id: int | None) -> str | None:
    """Return a blocker message when a configured model route is not permitted."""
    from nl_coding_agent.core.permissions import PermissionDenied, assert_model_permitted

    base_url = ollama_registry.OLLAMA_BASE_URL
    for field_name in ("developer_model", "reviewer_model", "debug_model"):
        model_name = str(_config_value(config, field_name, "") or "").strip()
        if not model_name:
            continue
        try:
            assert_model_permitted(model_name, base_url, project_id=project_id)
        except PermissionDenied as exc:
            return str(exc)
    return None


def decide(config, *, project_id: int | None) -> ResourceDecision:
    """Decide whether a mission may start now, must wait, or is blocked by policy."""
    observed: dict = {}
    permission_blocker = _model_permission_blocker(config, project_id)
    if permission_blocker:
        observed["permission"] = permission_blocker
        return ResourceDecision("blocked", permission_blocker, None, observed)

    try:
        observed.update(probe_local_models(config))
    except Exception as exc:  # pragma: no cover - defensive
        return ResourceDecision(
            "wait", "Model probe failed: " + str(exc), _backoff(config), observed
        )
    if not observed.get("reachable"):
        return ResourceDecision(
            "wait",
            str(observed.get("error") or "Local model provider is not reachable"),
            _backoff(config),
            observed,
        )
    missing = list(observed.get("missing_models") or [])
    if missing:
        return ResourceDecision(
            "wait",
            "Required local model(s) not installed: " + ", ".join(missing),
            _backoff(config),
            observed,
        )

    try:
        held = supervisor_store.get_machine_lease(INFERENCE_RESOURCE)
    except supervisor_store.StoreError:
        held = None
    if held is not None:
        expired = False
        try:
            from datetime import datetime
            expired = datetime.fromisoformat(str(held.get("expires_at"))) < datetime.now()
        except (TypeError, ValueError):
            expired = False
        same_host = str(held.get("owner_host") or "") == supervisor_store._hostname()
        owner_alive = same_host and supervisor_store._pid_alive(
            int(held.get("owner_pid") or 0))
        if expired and not owner_alive:
            # A dead/expired owner must not block every project forever. The
            # acquire path already has this rule; the decision path must mirror it.
            try:
                supervisor_store.release_machine_lease(
                    INFERENCE_RESOURCE, owner_id=str(held.get("owner_id")))
            except supervisor_store.StoreError:
                pass
            held = None
        observed["machine_lease"] = held
    else:
        observed["machine_lease"] = None
    if held is not None:
        return ResourceDecision(
            "wait",
            "Another project currently holds the machine inference slot (owner "
            + str(held.get("owner_id")) + ").",
            _backoff(config),
            observed,
        )
    return ResourceDecision("run", "", None, observed)

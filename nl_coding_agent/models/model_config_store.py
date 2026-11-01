"""Atomic writer for `config/models.yaml` provider/role/cloud settings.

The file remains the single authoritative model configuration used by every
entry point. Writes are validated, backed up under `data/backups/` and replaced
atomically; comments/formatting may be normalized by PyYAML.
"""
from __future__ import annotations

import os
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from nl_coding_agent.core.recovery_store import _atomic_write
from nl_coding_agent.persistence import database

PROVIDER_KINDS = {"ollama", "openai_compatible"}
ROLE_NAMES = {"architect", "developer", "debugger", "reviewer", "chat", "fallback_cloud"}
MODEL_RE = re.compile(r"^[A-Za-z0-9_.:/@+-]+$")


class ModelConfigError(ValueError):
    pass


def default_path() -> Path:
    override = os.environ.get("NL_MODELS_CONFIG")
    return Path(override) if override else Path(__file__).resolve().parents[2] / "config" / "models.yaml"


def load(path: Path | None = None) -> dict:
    target = Path(path) if path else default_path()
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) if target.is_file() else {}
    except (OSError, yaml.YAMLError) as exc:
        raise ModelConfigError("Cannot read model config: " + str(exc)) from exc
    if not isinstance(data, dict):
        raise ModelConfigError("Model config must be a mapping")
    data.setdefault("providers", {})
    data.setdefault("roles", {})
    return data


def _backup(path: Path, config: Mapping[str, Any]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = database.data_root() / "backups" / f"models-{stamp}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, yaml.safe_dump(dict(config), sort_keys=False,
                                        allow_unicode=True).encode("utf-8"))
    try:
        from nl_coding_agent.core.backup_retention import prune
        prune(target.parent, "models-")
    except Exception:
        pass
    return target


def save(config: Mapping[str, Any], path: Path | None = None) -> dict:
    target = Path(path) if path else default_path()
    validated = validate(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        _backup(target, load(target))
    _atomic_write(target, yaml.safe_dump(validated, sort_keys=False,
                                        allow_unicode=True).encode("utf-8"))
    return validated


def validate(config: Mapping[str, Any]) -> dict:
    if not isinstance(config, Mapping):
        raise ModelConfigError("Model config must be a mapping")
    data = deepcopy(dict(config))
    providers = data.get("providers") or {}
    roles = data.get("roles") or {}
    if not isinstance(providers, dict) or not isinstance(roles, dict):
        raise ModelConfigError("providers and roles must be mappings")
    for provider_id, entry in providers.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(provider_id)):
            raise ModelConfigError("Invalid provider id: " + str(provider_id))
        if not isinstance(entry, dict):
            raise ModelConfigError("Provider entry must be an object: " + str(provider_id))
        kind = str(entry.get("kind") or provider_id)
        if kind not in PROVIDER_KINDS:
            raise ModelConfigError("Unsupported provider kind: " + kind)
        if "enabled" in entry and not isinstance(entry["enabled"], bool):
            raise ModelConfigError("Provider enabled must be a boolean")
        url = str(entry.get("base_url") or "").strip()
        if url and not re.match(r"^https?://[^\s]+$", url):
            raise ModelConfigError("Provider base_url must be an http(s) URL")
        if "@" in url.split("://", 1)[-1].split("/", 1)[0]:
            raise ModelConfigError("Provider URL must not embed credentials")
        if "api_key_env" in entry:
            value = str(entry.get("api_key_env") or "").strip()
            if value and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
                raise ModelConfigError("api_key_env must be an environment variable name")
            if not value:
                entry.pop("api_key_env", None)
    for role, entry in roles.items():
        if role not in ROLE_NAMES:
            raise ModelConfigError("Unsupported role: " + str(role))
        if not isinstance(entry, dict):
            raise ModelConfigError("Role entry must be an object: " + str(role))
        if role == "fallback_cloud":
            if "enabled" in entry and not isinstance(entry["enabled"], bool):
                raise ModelConfigError("fallback_cloud.enabled must be boolean")
            continue
        model = str(entry.get("model") or "").strip()
        if not model:
            raise ModelConfigError(f"Role {role} requires a model")
        if not MODEL_RE.match(model):
            raise ModelConfigError(f"Invalid model route for role {role}: {model}")
        if "temperature" in entry:
            try:
                value = float(entry["temperature"])
            except (TypeError, ValueError):
                raise ModelConfigError("temperature must be numeric") from None
            if not 0.0 <= value <= 2.0:
                raise ModelConfigError("temperature must be within 0..2")
            entry["temperature"] = value
    data["providers"] = providers
    data["roles"] = roles
    return data


def update_provider(provider_id: str, **changes: Any) -> dict:
    """Update only whitelisted provider fields; never expose secrets."""
    allowed = {"enabled", "base_url", "label", "kind", "api_key_env"}
    unknown = set(changes) - allowed
    if unknown:
        raise ModelConfigError("Unsupported provider fields: " + ", ".join(sorted(unknown)))
    config = load()
    providers = config.setdefault("providers", {})
    entry = providers.setdefault(str(provider_id), {})
    if not isinstance(entry, dict):
        raise ModelConfigError("Provider entry must be an object")
    for key, value in changes.items():
        if value is None:
            entry.pop(key, None)
        else:
            entry[key] = value
    if "kind" not in entry:
        entry["kind"] = str(provider_id)
    return save(config)


def update_role(role: str, **changes: Any) -> dict:
    allowed = {"model", "temperature"}
    unknown = set(changes) - allowed
    if unknown:
        raise ModelConfigError("Unsupported role fields: " + ", ".join(sorted(unknown)))
    config = load()
    roles = config.setdefault("roles", {})
    entry = roles.setdefault(str(role), {})
    if not isinstance(entry, dict):
        raise ModelConfigError("Role entry must be an object")
    for key, value in changes.items():
        if value is None:
            entry.pop(key, None)
        else:
            entry[key] = value
    return save(config)


def set_cloud_escalation(enabled: bool) -> dict:
    if not isinstance(enabled, bool):
        raise ModelConfigError("enabled must be a boolean")
    config = load()
    fallback = config.setdefault("roles", {}).setdefault("fallback_cloud", {})
    fallback["enabled"] = enabled
    return save(config)

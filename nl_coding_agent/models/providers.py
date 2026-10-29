"""Provider-agnostic model discovery for the Model Hub."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from nl_coding_agent.models.ollama_registry import (
    check_ollama_reachable,
    list_loaded_models as ollama_loaded_models,
    list_models as ollama_models,
    stop_model as ollama_stop_model,
)


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


@dataclass
class ModelInfo:
    provider_id: str
    provider_label: str
    name: str
    size_gb: float = 0.0
    loaded: bool = False
    family: str = ""
    modified_at: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderSnapshot:
    provider_id: str
    label: str
    kind: str
    base_url: str
    reachable: bool
    models: list[ModelInfo] = field(default_factory=list)
    loaded: list[ModelInfo] = field(default_factory=list)
    error: str = ""
    elapsed_ms: int = 0


@dataclass
class ModelHubSnapshot:
    providers: list[ProviderSnapshot] = field(default_factory=list)

    @property
    def models(self) -> list[ModelInfo]:
        result: list[ModelInfo] = []
        for provider in self.providers:
            result.extend(provider.models)
        return result

    @property
    def loaded(self) -> list[ModelInfo]:
        result: list[ModelInfo] = []
        for provider in self.providers:
            result.extend(provider.loaded)
        return result

    @property
    def reachable(self) -> bool:
        return any(provider.reachable for provider in self.providers)

    @property
    def errors(self) -> list[str]:
        return [f"{p.label}: {p.error}" for p in self.providers if p.error]


def _base_url(value: str) -> str:
    return value.rstrip("/")


def _http_json(url: str, timeout: float, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def _post_json(url: str, body: dict, timeout: float, headers=None) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Unexpected provider response")
    if data.get("error"):
        raise ValueError(str(data["error"]))
    return data


class OllamaProvider:
    kind = "ollama"

    def __init__(
        self,
        provider_id: str = "ollama",
        label: str = "Ollama",
        base_url: str = DEFAULT_OLLAMA_URL,
    ):
        self.provider_id = provider_id
        self.label = label
        self.base_url = _base_url(base_url)

    def probe(self, timeout: float = 5.0) -> ProviderSnapshot:
        started = time.perf_counter()
        if not check_ollama_reachable(self.base_url, timeout=timeout):
            return ProviderSnapshot(
                provider_id=self.provider_id,
                label=self.label,
                kind=self.kind,
                base_url=self.base_url,
                reachable=False,
                error=f"Ollama is not reachable at {self.base_url}.",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        try:
            available = ollama_models(self.base_url, timeout=timeout)
            loaded = ollama_loaded_models(self.base_url, timeout=timeout)
            loaded_names = {item.name for item in loaded}
            models = [
                ModelInfo(
                    provider_id=self.provider_id,
                    provider_label=self.label,
                    name=item.name,
                    size_gb=item.size_gb,
                    loaded=item.name in loaded_names or item.loaded,
                    family=item.family,
                    modified_at=item.modified_at,
                    metadata={"source": "ollama"},
                )
                for item in available
            ]
            loaded_models = [
                ModelInfo(
                    provider_id=self.provider_id,
                    provider_label=self.label,
                    name=item.name,
                    size_gb=item.size_gb,
                    loaded=True,
                    metadata={"source": "ollama"},
                )
                for item in loaded
            ]
            return ProviderSnapshot(
                provider_id=self.provider_id,
                label=self.label,
                kind=self.kind,
                base_url=self.base_url,
                reachable=True,
                models=models,
                loaded=loaded_models,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                label=self.label,
                kind=self.kind,
                base_url=self.base_url,
                reachable=False,
                error=f"Ollama discovery failed: {exc}",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )

    def assert_generation_permitted(self, model: str, project_id=None) -> None:
        from nl_coding_agent.core.permissions import assert_model_permitted
        assert_model_permitted(model, self.base_url, project_id=project_id)

    def generate(self, model: str, prompt: str, timeout: float = 120.0, *,
                 project_id=None, messages=None) -> str:
        self.assert_generation_permitted(model, project_id)
        body = {"model": model, "stream": False}
        if messages is not None:
            body["messages"] = messages
            endpoint = "/api/chat"
        else:
            body["prompt"] = prompt
            endpoint = "/api/generate"
        data = _post_json(self.base_url + endpoint, body, timeout)
        if messages is not None:
            return str((data.get("message") or {}).get("content") or "")
        return str(data.get("response") or "")

    def unload(self, name: str) -> bool:
        return ollama_stop_model(name)


class OpenAICompatibleProvider:
    kind = "openai_compatible"

    def __init__(
        self,
        provider_id: str,
        label: str,
        base_url: str,
        api_key_env: str = "",
    ):
        self.provider_id = provider_id
        self.label = label
        self.base_url = _base_url(base_url)
        self.api_key_env = api_key_env

    def _headers(self) -> dict[str, str]:
        if not self.api_key_env:
            return {}
        token = os.environ.get(self.api_key_env, "")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def probe(self, timeout: float = 5.0) -> ProviderSnapshot:
        started = time.perf_counter()
        try:
            payload = _http_json(
                f"{self.base_url}/models",
                timeout=timeout,
                headers=self._headers(),
            )
            entries = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(entries, list):
                raise ValueError("unexpected /models response")
            models: list[ModelInfo] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("id") or entry.get("name") or ""
                if not name:
                    continue
                size = entry.get("size", 0)
                try:
                    size_gb = round(float(size) / 1e9, 2)
                except (TypeError, ValueError):
                    size_gb = 0.0
                models.append(
                    ModelInfo(
                        provider_id=self.provider_id,
                        provider_label=self.label,
                        name=str(name),
                        size_gb=size_gb,
                        family=str(entry.get("owned_by") or ""),
                        metadata={
                            "source": "openai_compatible",
                            "owned_by": entry.get("owned_by"),
                        },
                    )
                )
            return ProviderSnapshot(
                provider_id=self.provider_id,
                label=self.label,
                kind=self.kind,
                base_url=self.base_url,
                reachable=True,
                models=models,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        except urllib.error.HTTPError as exc:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                label=self.label,
                kind=self.kind,
                base_url=self.base_url,
                reachable=False,
                error=f"{self.label} returned HTTP {exc.code}.",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                label=self.label,
                kind=self.kind,
                base_url=self.base_url,
                reachable=False,
                error=f"{self.label} is not reachable at {self.base_url}: {exc}",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )

    def assert_generation_permitted(self, model: str, project_id=None) -> None:
        from nl_coding_agent.core import permissions
        permissions.assert_model_permitted(model, self.base_url, project_id=project_id)
        # A remote compatible endpoint may be a hosted model with an arbitrary
        # name. Never infer local inference from the absence of a ':cloud' suffix.
        if permissions.is_remote_endpoint(self.base_url):
            permissions.require(permissions.CLOUD, project_id=project_id)

    def generate(self, model: str, prompt: str, timeout: float = 120.0, *,
                 project_id=None, messages=None) -> str:
        self.assert_generation_permitted(model, project_id)
        data = _post_json(
            self.base_url + "/chat/completions",
            {"model": model, "messages": messages or [{"role": "user", "content": prompt}],
             "stream": False}, timeout, self._headers())
        choices = data.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            if isinstance(message, dict):
                return str(message.get("content") or "")
        raise ValueError("Provider returned no chat completion")

    def unload(self, name: str) -> bool:
        return False


def build_providers(config: dict[str, Any] | None = None) -> list[Any]:
    config = config or {}
    provider_config = config.get("providers")
    if not isinstance(provider_config, dict) or not provider_config:
        ollama_config = config.get("ollama") or {}
        return [
            OllamaProvider(
                base_url=str(ollama_config.get("base_url") or DEFAULT_OLLAMA_URL)
            )
        ]

    providers: list[Any] = []
    for provider_id, raw in provider_config.items():
        if not isinstance(raw, dict) or not raw.get("enabled", True):
            continue
        kind = str(raw.get("kind") or "openai_compatible")
        label = str(raw.get("label") or provider_id)
        base_url = str(raw.get("base_url") or "")
        if kind == "ollama":
            providers.append(
                OllamaProvider(
                    provider_id=provider_id,
                    label=label,
                    base_url=base_url or DEFAULT_OLLAMA_URL,
                )
            )
        elif kind in {"openai_compatible", "openai", "lm_studio", "llama_cpp"}:
            if not base_url:
                continue
            providers.append(
                OpenAICompatibleProvider(
                    provider_id=provider_id,
                    label=label,
                    base_url=base_url,
                    api_key_env=str(raw.get("api_key_env") or ""),
                )
            )
    return providers


class ModelHub:
    def __init__(self, providers: list[Any]):
        self.providers = providers

    def discover(self, timeout: float = 5.0) -> ModelHubSnapshot:
        return ModelHubSnapshot([provider.probe(timeout=timeout) for provider in self.providers])

    def unload(self, provider_id: str, name: str) -> bool:
        for provider in self.providers:
            if provider.provider_id == provider_id:
                return bool(provider.unload(name))
        return False
def generate_ollama_text(base_url: str, model: str, prompt: str, *,
                        timeout: float = 120.0, project_id=None) -> str:
    """Compatibility wrapper over the permission-checked Ollama provider."""
    return OllamaProvider(base_url=base_url).generate(
        model, prompt, timeout=timeout, project_id=project_id)

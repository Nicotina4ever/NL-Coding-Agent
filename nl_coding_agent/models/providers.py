"""Provider-agnostic model discovery for the Model Hub."""
from __future__ import annotations

import json
import os
import time
import socket
import threading
from contextlib import contextmanager
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


_MAX_STREAM_LINE = 4 * 1024 * 1024


@contextmanager
def _stream_response(request, timeout, cancelled):
    """Wake a blocked stream read when its owner requests cancellation."""
    with urllib.request.urlopen(request, timeout=timeout) as response:
        finished = threading.Event()
        def observe():
            while not finished.wait(0.05):
                if cancelled and cancelled():
                    try:
                        response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
                    except (AttributeError, OSError):
                        pass
                    return
        watcher = threading.Thread(target=observe, daemon=True) if cancelled else None
        if watcher:
            watcher.start()
        try:
            yield response
        except (OSError, ValueError):
            _check_cancelled(cancelled)
            raise
        finally:
            finished.set()
            if watcher:
                watcher.join(0.2)


def _check_cancelled(cancelled) -> None:
    if cancelled is not None and cancelled():
        raise InterruptedError("Model stream was cancelled")


def _iter_stream_lines(response, cancelled, deadline=None):
    """Yield complete lines from a live HTTP response using bounded reads.

    ``read1`` performs at most one underlying socket read, which keeps the
    stream incremental instead of buffering the whole response. The caller's
    socket timeout still applies to each read.
    """
    reader = getattr(response, "read1", None) or response.read
    buffer = b""
    total = 0
    while True:
        _check_cancelled(cancelled)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Provider stream exceeded its turn deadline")
        chunk = reader(8192)
        _check_cancelled(cancelled)
        if not chunk:
            break
        total += len(chunk)
        if total > 16 * 1024 * 1024:
            raise ValueError("Provider stream exceeds the response safety limit")
        buffer += chunk
        if len(buffer) > _MAX_STREAM_LINE and b"\n" not in buffer:
            raise ValueError("Provider stream line exceeds the safety limit")
        while True:
            newline = buffer.find(b"\n")
            if newline < 0:
                break
            line = buffer[:newline]
            buffer = buffer[newline + 1:]
            _check_cancelled(cancelled)
            yield line.rstrip(b"\r")
    if buffer:
        _check_cancelled(cancelled)
        yield buffer.rstrip(b"\r")


def _iter_ndjson(response, cancelled, deadline=None):
    for raw in _iter_stream_lines(response, cancelled, deadline):
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            continue
        try:
            yield json.loads(text)
        except ValueError as exc:
            raise ValueError("Malformed provider stream line") from exc


def _iter_sse(response, cancelled, deadline=None):
    """Yield SSE data payloads (``None`` for the terminating [DONE] marker)."""
    for raw in _iter_stream_lines(response, cancelled, deadline):
        text = raw.decode("utf-8", "replace").strip()
        if not text or text.startswith(":"):
            continue
        if text.startswith("data:"):
            text = text[5:].lstrip()
        elif not text.startswith("{"):
            # Ignore other SSE fields (event/id/retry); raw JSON lines are
            # tolerated for providers that do not emit the data: prefix.
            continue
        if not text:
            continue
        if text == "[DONE]":
            yield None
            continue
        yield text


class _ToolCallAccumulator:
    """Merge streamed tool-call fragments by index and parse their arguments."""

    def __init__(self) -> None:
        self._calls: dict[int, dict] = {}
        self._next_index = 0

    def add(self, call, index=None) -> None:
        if not isinstance(call, dict):
            return
        if index is None:
            index = call.get("index")
        if index is None:
            call_id = call.get("id")
            if call_id:
                for existing_index, existing in self._calls.items():
                    if existing.get("id") == call_id:
                        index = existing_index
                        break
            if index is None:
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                if len(self._calls) == 1 and not function.get("name"):
                    # No index/id and no name: this is an arguments continuation.
                    index = next(iter(self._calls))
                else:
                    index = self._next_index
                    self._next_index += 1
        else:
            try:
                index = int(index)
            except (TypeError, ValueError):
                index = self._next_index
                self._next_index += 1
            else:
                self._next_index = max(self._next_index, index + 1)
        item = self._calls.setdefault(index, {
            "id": "",
            "type": "",
            "function": {"name": "", "arguments": ""},
        })
        if call.get("id"):
            item["id"] = str(call["id"])
        if call.get("type"):
            item["type"] = str(call["type"])
        function = call.get("function")
        if not isinstance(function, dict):
            return
        name = function.get("name")
        if isinstance(name, str) and name:
            item["function"]["name"] += name
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            item["function"]["arguments"] += arguments
        elif isinstance(arguments, dict):
            item["_arguments_object"] = arguments

    def finish(self) -> list[dict]:
        result: list[dict] = []
        for index in sorted(self._calls):
            item = self._calls[index]
            function = item["function"]
            raw_arguments = function.get("arguments", "")
            arguments_object = item.pop("_arguments_object", None)
            if raw_arguments:
                try:
                    arguments = json.loads(raw_arguments)
                except ValueError as exc:
                    raise ValueError("Malformed streamed tool-call arguments") from exc
            elif arguments_object is not None:
                arguments = arguments_object
            else:
                arguments = {}
            call = {"function": {"name": function.get("name", ""),
                                 "arguments": arguments}}
            if item.get("id"):
                call["id"] = item["id"]
            if item.get("type"):
                call["type"] = item["type"]
            result.append(call)
        return result


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
                    capabilities=tuple(getattr(item, "capabilities", ())),
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
            self._capabilities = {item.name: item.capabilities for item in models}
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

    def _generation_options(self, model: str, role: str = "chat") -> dict:
        """Return explicitly persisted generation options, including optional num_ctx."""
        try:
            from nl_coding_agent.models.generation_params import effective_params
            params = effective_params(model_name=model, role=role)
        except Exception:
            return {}
        allowed = {"temperature", "top_p", "top_k", "min_p", "repeat_penalty",
                   "repeat_last_n", "seed", "num_predict", "frequency_penalty",
                   "presence_penalty", "tfs_z", "typical_p", "mirostat",
                   "mirostat_tau", "mirostat_eta", "num_ctx"}
        return {key: value for key, value in params.items() if key in allowed}

    def generate(self, model: str, prompt: str, timeout: float = 120.0, *,
                 project_id=None, messages=None, role: str = "chat") -> str:
        self.assert_generation_permitted(model, project_id)
        body = {"model": model, "stream": False}
        options = self._generation_options(model, role=role)
        if options:
            body["options"] = options
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

    def chat_turn(self, model, messages, tools, *, project_id=None, timeout=120,
                  role: str = "chat"):
        """Preserve actual native tool calls; never parse prose as execution."""
        self.assert_generation_permitted(model, project_id)
        capabilities = getattr(self, "_capabilities", {}).get(model, ())
        if tools and capabilities and "tools" not in capabilities:
            raise ValueError("Selected model reports no native tools capability; select validated JSON mode explicitly")
        wire_messages = [{key: value for key, value in
                          {**m, **({"tool_name": m.get("name", "")} if m["role"] == "tool" else {})}.items()
                          if not str(key).startswith("_")}
                         for m in messages]
        body = {
            "model": model, "messages": wire_messages, "tools": tools,
            "stream": False, "think": False,
        }
        options = self._generation_options(model, role=role)
        if options:
            body["options"] = options
        data = _post_json(self.base_url + "/api/chat", body, timeout)
        message = dict(data.get("message") or {})
        # Provider-reported usage lets the context estimator calibrate itself.
        message["_usage"] = {
            "prompt_tokens": data.get("prompt_eval_count"),
            "output_tokens": data.get("eval_count"),
        }
        if message.get("thinking"):
            message["_thinking"] = str(message.get("thinking") or "")
        return message

    def chat_turn_stream(self, model, messages, tools, *, project_id=None,
                         timeout=120, role: str = "chat", on_delta=None,
                         cancelled=None):
        """Stream one native tool-capable chat turn over Ollama NDJSON.

        ``on_delta`` receives each content fragment exactly when it arrives from
        the provider. Cancellation is checked between bounded socket reads and
        raises ``InterruptedError``. A stream that ends without its completion
        marker is rejected instead of being reported as a complete answer.
        """
        self.assert_generation_permitted(model, project_id)
        _check_cancelled(cancelled)
        capabilities = getattr(self, "_capabilities", {}).get(model, ())
        if tools and capabilities and "tools" not in capabilities:
            raise ValueError("Selected model reports no native tools capability; select validated JSON mode explicitly")
        wire_messages = [{key: value for key, value in
                          {**m, **({"tool_name": m.get("name", "")} if m["role"] == "tool" else {})}.items()
                          if not str(key).startswith("_")}
                         for m in messages]
        body = {
            "model": model, "messages": wire_messages, "tools": tools,
            "stream": True, "think": False,
        }
        options = self._generation_options(model, role=role)
        if options:
            body["options"] = options
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        message_role = "assistant"
        tool_calls = _ToolCallAccumulator()
        usage = {"prompt_tokens": None, "output_tokens": None}
        completed = False
        request = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with _stream_response(request, timeout, cancelled) as response:
            for event in _iter_ndjson(response, cancelled, time.monotonic() + timeout):
                if not isinstance(event, dict):
                    continue
                if event.get("error"):
                    raise ValueError(str(event["error"]))
                delta = event.get("message")
                if isinstance(delta, dict):
                    message_role = str(delta.get("role") or message_role)
                    text = delta.get("content")
                    if isinstance(text, str) and text:
                        content_parts.append(text)
                        if on_delta is not None:
                            on_delta(text)
                    thinking = delta.get("thinking")
                    if isinstance(thinking, str) and thinking:
                        thinking_parts.append(thinking)
                    for call in delta.get("tool_calls") or []:
                        tool_calls.add(call)
                if event.get("done"):
                    completed = True
                    usage["prompt_tokens"] = event.get("prompt_eval_count")
                    usage["output_tokens"] = event.get("eval_count")
                    break
        if not completed:
            raise ConnectionError("Ollama stream ended before the completion marker")
        message = {"role": message_role, "content": "".join(content_parts)}
        assembled = tool_calls.finish()
        if assembled:
            message["tool_calls"] = assembled
        if thinking_parts:
            thinking = "".join(thinking_parts)
            message["thinking"] = thinking
            message["_thinking"] = thinking
        message["_usage"] = usage
        return message


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

    def chat_turn(self, model, messages, tools, *, project_id=None, timeout=120):
        self.assert_generation_permitted(model, project_id)
        wire_messages = []
        for message in messages:
            item = {key: value for key, value in dict(message).items()
                    if not str(key).startswith("_")}
            if item.get("tool_calls"):
                item["tool_calls"] = [{**call, "function": {**call["function"], "arguments":
                    json.dumps(call["function"]["arguments"]) if isinstance(call["function"]["arguments"], dict)
                    else call["function"]["arguments"]}} for call in item["tool_calls"]]
            wire_messages.append(item)
        data = _post_json(self.base_url + "/chat/completions", {
            "model": model, "messages": wire_messages, "tools": tools,
            "stream": False}, timeout, self._headers())
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Provider returned no chat completion")
        message = dict(choices[0].get("message") or {})
        usage = data.get("usage") or {}
        message["_usage"] = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if reasoning:
            message["_thinking"] = str(reasoning)
        return message

    def chat_turn_stream(self, model, messages, tools, *, project_id=None,
                         timeout=120, role: str = "chat", on_delta=None,
                         cancelled=None):
        """Stream one native tool-capable chat turn over SSE ``/chat/completions``.

        Fragmented ``tool_calls`` are accumulated by index, their arguments are
        assembled and JSON-decoded before returning, and the provider-assigned
        ids are preserved. ``on_delta`` only receives real content fragments.
        """
        self.assert_generation_permitted(model, project_id)
        _check_cancelled(cancelled)
        wire_messages = []
        for message in messages:
            item = {key: value for key, value in dict(message).items()
                    if not str(key).startswith("_")}
            if item.get("tool_calls"):
                item["tool_calls"] = [{**call, "function": {**call["function"], "arguments":
                    json.dumps(call["function"]["arguments"]) if isinstance(call["function"]["arguments"], dict)
                    else call["function"]["arguments"]}} for call in item["tool_calls"]]
            wire_messages.append(item)
        body = {
            "model": model, "messages": wire_messages, "tools": tools,
            "stream": True, "stream_options": {"include_usage": True},
        }
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        reasoning_key = ""
        message_role = "assistant"
        tool_calls = _ToolCallAccumulator()
        usage = {"prompt_tokens": None, "output_tokens": None}
        completed = False
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", **self._headers()},
            method="POST")
        with _stream_response(request, timeout, cancelled) as response:
            for payload in _iter_sse(response, cancelled, time.monotonic() + timeout):
                if payload is None:
                    completed = True
                    break
                try:
                    event = json.loads(payload)
                except ValueError as exc:
                    raise ValueError("Malformed provider stream event") from exc
                if not isinstance(event, dict):
                    continue
                if event.get("error"):
                    raise ValueError(str(event["error"]))
                event_usage = event.get("usage")
                if isinstance(event_usage, dict):
                    usage["prompt_tokens"] = event_usage.get(
                        "prompt_tokens", usage["prompt_tokens"])
                    usage["output_tokens"] = event_usage.get(
                        "completion_tokens", usage["output_tokens"])
                choices = event.get("choices") or []
                if not choices or not isinstance(choices[0], dict):
                    continue
                choice = choices[0]
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    delta = choice.get("message")
                if isinstance(delta, dict):
                    message_role = str(delta.get("role") or message_role)
                    text = delta.get("content")
                    if isinstance(text, str) and text:
                        content_parts.append(text)
                        if on_delta is not None:
                            on_delta(text)
                    reasoning = delta.get("reasoning_content")
                    if isinstance(reasoning, str) and reasoning:
                        reasoning_key = "reasoning_content"
                        reasoning_parts.append(reasoning)
                    else:
                        reasoning = delta.get("reasoning")
                        if isinstance(reasoning, str) and reasoning:
                            reasoning_key = "reasoning"
                            reasoning_parts.append(reasoning)
                    for call in delta.get("tool_calls") or []:
                        tool_calls.add(call, index=call.get("index")
                                       if isinstance(call, dict) else None)
                if choice.get("finish_reason") is not None:
                    completed = True
        if not completed:
            raise ConnectionError("OpenAI-compatible stream ended before completion")
        message = {"role": message_role, "content": "".join(content_parts)}
        assembled = tool_calls.finish()
        if assembled:
            message["tool_calls"] = assembled
        if reasoning_parts:
            reasoning = "".join(reasoning_parts)
            message[reasoning_key or "reasoning_content"] = reasoning
            message["_thinking"] = reasoning
        message["_usage"] = usage
        return message


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

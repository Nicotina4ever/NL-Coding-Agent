"""Operational Ollama probes: what a model can actually do with tools.

Probes are explicit, bounded, local-only by default and never execute model prose.
They call the existing provider seam and validate the returned arguments against a
fixed schema/fixture. Results are stored in the existing capability ledger; the
router consumes them, no second model registry is introduced.
"""
from __future__ import annotations

import json
import time
from typing import Any, Mapping

from nl_coding_agent.models.capabilities import (
    CapabilityRecord,
    probe_capabilities,
    record_capabilities,
)
from nl_coding_agent.models.ollama_registry import list_models
from nl_coding_agent.models.providers import OllamaProvider

PROBE_PATH = "probe_target.py"
PROBE_TARGET = "VALUE = 1"
PROBE_REPLACEMENT = "VALUE = 2"


def _tool_schema(name: str, description: str, properties: Mapping[str, Any]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": dict(properties),
                       "required": list(properties), "additionalProperties": False},
    }}


def _calls(response: Mapping[str, Any]) -> list[dict]:
    raw = response.get("tool_calls") or []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _call_parts(call: Mapping[str, Any]) -> tuple[str, dict]:
    fn = call.get("function") or call
    name = str(fn.get("name") or call.get("name") or "")
    args = fn.get("arguments", call.get("arguments", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    return name, dict(args) if isinstance(args, Mapping) else {}


def _textual_call(content: str) -> tuple[str, dict]:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return "", {}
    if not isinstance(data, Mapping):
        return "", {}
    fn = data.get("function") if isinstance(data.get("function"), Mapping) else data
    name = str(fn.get("name") or "")
    args = fn.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    return name, dict(args) if isinstance(args, Mapping) else {}


def _extract_call(response: Mapping[str, Any]) -> tuple[str, dict, str]:
    calls = _calls(response)
    if calls:
        name, args = _call_parts(calls[0])
        return name, args, "native"
    name, args = _textual_call(str(response.get("content") or ""))
    return name, args, "textual" if name else "none"


def _tool_calling_probe(provider: OllamaProvider, model: str, timeout: float) -> dict:
    schema = _tool_schema("record_probe", "Record the probe value.", {
        "value": {"type": "integer"},
    })
    response = provider.chat_turn(
        model,
        [{"role": "user", "content":
          "Call record_probe exactly once with value 42. Return a tool call, not prose."}],
        [schema], timeout=timeout,
    )
    name, args, source = _extract_call(response)
    ok = name == "record_probe" and args.get("value") == 42
    return {"supported": ok, "metadata": {"source": source, "call": name}}


def _patch_quality_probe(provider: OllamaProvider, model: str, timeout: float) -> dict:
    schema = _tool_schema("patch_file", "Replace an exact snippet in a file.", {
        "path": {"type": "string"},
        "target": {"type": "string"},
        "replacement": {"type": "string"},
    })
    response = provider.chat_turn(
        model,
        [{"role": "user", "content":
          f"File {PROBE_PATH} contains exactly `{PROBE_TARGET}`. Use patch_file with "
          f"path={PROBE_PATH}, target={PROBE_TARGET!r}, replacement={PROBE_REPLACEMENT!r}. "
          "Return one native tool call. Do not write anything else."}],
        [schema], timeout=timeout,
    )
    name, args, source = _extract_call(response)
    exact = (name == "patch_file"
             and args.get("path") == PROBE_PATH
             and args.get("target") == PROBE_TARGET
             and args.get("replacement") == PROBE_REPLACEMENT)
    valid = (name == "patch_file"
             and isinstance(args.get("path"), str)
             and isinstance(args.get("target"), str)
             and isinstance(args.get("replacement"), str)
             and bool(args.get("target")))
    score = 1.0 if exact else (0.5 if valid else 0.0)
    return {
        "supported": score >= 0.5,
        "metadata": {"score": score, "source": source, "call": name,
                     "arguments_valid": valid, "exact_fixture": exact},
    }


def _structured_probe(provider: OllamaProvider, model: str, timeout: float) -> dict:
    text = provider.generate(
        model,
        'Return exactly one JSON object, no prose: {"ok": true, "n": 7}',
        timeout=timeout,
    )
    try:
        parsed = json.loads(str(text or "").strip().strip("`").removeprefix("json").strip())
    except ValueError:
        parsed = None
    ok = isinstance(parsed, Mapping) and parsed.get("ok") is True and parsed.get("n") == 7
    return {"supported": ok, "metadata": {"valid_json": isinstance(parsed, Mapping)}}


def probe_model(model: str, *, base_url: str = "http://127.0.0.1:11434",
                timeout: float = 90.0, persist: bool = True,
                allow_cloud: bool = False) -> list[CapabilityRecord]:
    """Measure tool-calling/patch/structured quality for one local Ollama model."""
    if (not allow_cloud and ("cloud" in str(model).lower()
                              or str(model).lower().endswith(":cloud"))):
        raise ValueError("Cloud model probes require explicit allow_cloud=True")
    provider = OllamaProvider(base_url=base_url)
    records = probe_capabilities(
        "ollama", model,
        {
            "tool_calling": lambda: _tool_calling_probe(provider, model, timeout),
            "patch_quality": lambda: _patch_quality_probe(provider, model, timeout),
            "structured_output": lambda: _structured_probe(provider, model, timeout),
        },
        backend_version="ollama",
        probe_id="operational-" + str(int(time.time())),
    )
    if persist:
        record_capabilities(records)
    return records


def probe_available_models(*, base_url: str = "http://127.0.0.1:11434",
                           limit: int = 6, timeout: float = 90.0,
                           allow_cloud: bool = False,
                           persist: bool = True) -> list[dict]:
    """Probe up to ``limit`` local models and return a JSON-safe measured summary."""
    summaries: list[dict] = []
    for item in list_models(base_url=base_url):
        if len(summaries) >= max(1, min(int(limit), 32)):
            break
        name = str(getattr(item, "name", "") or "")
        if not name:
            continue
        if not allow_cloud and "cloud" in name.lower():
            continue
        try:
            records = probe_model(name, base_url=base_url, timeout=timeout,
                                  persist=persist, allow_cloud=allow_cloud)
        except Exception as exc:  # probe failure is evidence, not a crash
            summaries.append({"model": name, "error": type(exc).__name__ + ": " + str(exc)})
            continue
        by_name = {record.capability: record for record in records}
        quality = by_name.get("patch_quality")
        summaries.append({
            "model": name,
            "tool_calling": by_name["tool_calling"].state if "tool_calling" in by_name else "unknown",
            "structured_output": (
                by_name["structured_output"].state if "structured_output" in by_name else "unknown"),
            "patch_quality": quality.state if quality else "unknown",
            "patch_score": float((quality.metadata or {}).get("score") or 0.0) if quality else 0.0,
            "capabilities": {key: value.to_dict() for key, value in by_name.items()},
        })
    return summaries

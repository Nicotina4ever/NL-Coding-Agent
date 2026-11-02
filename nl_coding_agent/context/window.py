"""Dynamic, model-aware context limits (P1 hardening).

The first Context Engine version used a fixed 60,000-character wall and a rough
chars/4 estimate. This module derives the prompt budget from what the runtime
actually knows about the selected model instead:

1. an explicit ``num_ctx`` generation parameter (user configuration);
2. the measured capability ledger (``context_limit`` from probes);
3. a previously measured/cached model window;
4. provider configuration;
5. a bounded Ollama ``/api/show`` probe (local, offline, 2 s);
6. only then a generous fallback that is reported as such.

The budget always reserves room for generated output and for the model's thinking
tokens, and it is calibrated from provider-reported prompt token counts so the
estimator improves with use. There is no product-level hard window: if the model
window is unknown the engine degrades gracefully instead of refusing the turn.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field

DEFAULT_CHARS_PER_TOKEN = 3.4   # conservative mix of code, prose, JSON
FALLBACK_WINDOW_TOKENS = 32_768  # only when the provider reports no window at all
MIN_PROMPT_TOKENS = 2_048
DEFAULT_OUTPUT_RESERVE = 2_048
MAX_OUTPUT_RESERVE = 16_384
THINK_FRACTION = 0.20
MARGIN_FRACTION = 0.05
PROBE_TIMEOUT_S = 2.0
CACHE_TTL_S = 6 * 3600
_MEASURED_WINDOW_CACHE: dict[tuple[str, str], tuple[float, int | None]] = {}
_WINDOW_SETTING = "context.window."
_CALIBRATION_SETTING = "context.calibration."


@dataclass(frozen=True)
class ContextLimits:
    """One prompt budget derived from the selected provider/model."""

    provider_id: str
    model_name: str
    window_tokens: int | None
    prompt_tokens: int
    prompt_chars: int
    reserve_output_tokens: int
    reserve_think_tokens: int
    chars_per_token: float
    source: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "window_tokens": self.window_tokens,
            "prompt_tokens": self.prompt_tokens,
            "prompt_chars": self.prompt_chars,
            "reserve_output_tokens": self.reserve_output_tokens,
            "reserve_think_tokens": self.reserve_think_tokens,
            "chars_per_token": round(self.chars_per_token, 3),
            "source": self.source,
            "notes": list(self.notes),
        }


def _settings_get(key: str):
    try:
        from nl_coding_agent.persistence import database

        raw = database.get_setting(key, "")
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _settings_set(key: str, value) -> None:
    try:
        from nl_coding_agent.persistence import database

        database.set_setting(key, json.dumps(value, ensure_ascii=False))
    except Exception:
        pass


def calibration_ratio(provider_id: str, model_name: str) -> float | None:
    """Observed chars-per-token for this model (EWMA), when already measured."""
    data = _settings_get(_CALIBRATION_SETTING + provider_id + "." + model_name)
    try:
        ratio = float((data or {}).get("chars_per_token") or 0.0)
    except (TypeError, ValueError):
        return None
    return ratio if 1.0 <= ratio <= 9.0 else None


def calibrate(provider_id: str, model_name: str, *,
              prompt_tokens: int | None, chars_sent: int) -> float | None:
    """Update the measured chars-per-token ratio from real provider usage data."""
    if not prompt_tokens or prompt_tokens <= 0 or chars_sent <= 0:
        return None
    ratio = max(1.0, min(9.0, float(chars_sent) / float(prompt_tokens)))
    previous = calibration_ratio(provider_id, model_name)
    blended = ratio if previous is None else (previous * 0.7 + ratio * 0.3)
    _settings_set(_CALIBRATION_SETTING + provider_id + "." + model_name, {
        "chars_per_token": round(blended, 4),
        "last_ratio": round(ratio, 4),
        "samples": int((( _settings_get(_CALIBRATION_SETTING + provider_id + "." + model_name)
                         or {}).get("samples") or 0)) + 1,
        "updated_at": int(time.time()),
    })
    return blended


def _capability_window(provider_id: str, model_name: str) -> int | None:
    try:
        from nl_coding_agent.models.capabilities import load_capabilities

        caps = load_capabilities(provider_id, model_name)
        limits = [record.context_limit for record in caps.records.values()
                  if getattr(record, "context_limit", None)]
        return max(limits) if limits else None
    except Exception:
        return None


def _generation_window(provider_id: str, model_name: str) -> int | None:
    try:
        from nl_coding_agent.models.generation_params import effective_params

        params = effective_params(model_name=model_name, provider_id=provider_id)
        value = params.get("num_ctx")
        return int(value) if value else None
    except Exception:
        return None


def _provider_config_window(provider_id: str) -> int | None:
    try:
        from nl_coding_agent.models.model_config_store import load

        config = load() or {}
        provider = (config.get("providers") or {}).get(provider_id) or {}
        value = provider.get("context_window") or provider.get("num_ctx")
        return int(value) if value else None
    except Exception:
        return None


def _cached_measured_window(provider_id: str, model_name: str) -> int | None:
    key = (provider_id, model_name)
    cached = _MEASURED_WINDOW_CACHE.get(key)
    if cached and time.monotonic() - cached[0] <= CACHE_TTL_S:
        return cached[1]
    stored = _settings_get(_WINDOW_SETTING + provider_id + "." + model_name) or {}
    value = stored.get("window_tokens")
    try:
        window = int(value) if value else None
    except (TypeError, ValueError):
        window = None
    _MEASURED_WINDOW_CACHE[key] = (time.monotonic(), window)
    return window


def _store_measured_window(provider_id: str, model_name: str, window: int) -> None:
    _MEASURED_WINDOW_CACHE[(provider_id, model_name)] = (time.monotonic(), window)
    _settings_set(_WINDOW_SETTING + provider_id + "." + model_name, {
        "window_tokens": int(window),
        "source": "ollama-show",
        "measured_at": int(time.time()),
    })


def _probe_ollama_window(model_name: str, base_url: str = "") -> int | None:
    """Read the model's real context length from the local Ollama server."""
    url = (base_url or "").rstrip("/") or "http://127.0.0.1:11434"
    body = json.dumps({"model": model_name}).encode("utf-8")
    request = urllib.request.Request(
        url + "/api/show", data=body, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_S) as response:
            payload = json.loads(response.read(512_000))
    except Exception:
        return None
    info = payload.get("model_info") if isinstance(payload, dict) else None
    if not isinstance(info, dict):
        return None
    values = [int(value) for key, value in info.items()
              if str(key).endswith(".context_length")
              and isinstance(value, (int, float)) and int(value) > 0]
    return max(values) if values else None


def model_window(provider_id: str, model_name: str, *, base_url: str = "") -> tuple[int | None, str]:
    """Return (window tokens, source) using the strongest available evidence."""
    provider_id = str(provider_id or "ollama")
    model_name = str(model_name or "")
    if not model_name:
        return None, "unknown-model"
    explicit = _generation_window(provider_id, model_name)
    if explicit:
        return explicit, "generation-params"
    measured = _capability_window(provider_id, model_name)
    if measured:
        return measured, "capability-ledger"
    configured = _provider_config_window(provider_id)
    if configured:
        return configured, "provider-config"
    cached = _cached_measured_window(provider_id, model_name)
    if cached:
        return cached, "measured-cache"
    if provider_id == "ollama":
        probed = _probe_ollama_window(model_name, base_url)
        if probed:
            _store_measured_window(provider_id, model_name, probed)
            return probed, "measured-ollama"
    return None, "fallback"


def _reserve_tokens(window: int, output_tokens: int | None) -> tuple[int, int]:
    if output_tokens:
        output = max(256, int(output_tokens))
    else:
        output = int(window * 0.18)
        output = max(512, min(MAX_OUTPUT_RESERVE, output))
    thinking = int(output * THINK_FRACTION) if THINK_FRACTION else 0
    return output, max(128, thinking)


def limits_for(provider_id: str, model_name: str, *, base_url: str = "",
               output_tokens: int | None = None) -> ContextLimits:
    """Compute the prompt budget; never fails and never returns an invalid one."""
    window, source = model_window(provider_id, model_name, base_url=base_url)
    notes: list[str] = []
    effective_window = window
    if effective_window is None:
        effective_window = FALLBACK_WINDOW_TOKENS
        notes.append("model window not reported by the provider; using a generous "
                     "fallback and degrading only when necessary")
    output_reserve, think_reserve = _reserve_tokens(effective_window, output_tokens)
    margin = int(effective_window * MARGIN_FRACTION)
    available = effective_window - output_reserve - think_reserve - margin
    prompt_tokens = max(256, int(available))
    if window is not None and window >= MIN_PROMPT_TOKENS + output_reserve + think_reserve + margin:
        prompt_tokens = max(prompt_tokens, MIN_PROMPT_TOKENS)
    ratio = calibration_ratio(provider_id, model_name) or DEFAULT_CHARS_PER_TOKEN
    return ContextLimits(
        provider_id=str(provider_id or "ollama"),
        model_name=str(model_name or ""),
        window_tokens=window,
        prompt_tokens=int(prompt_tokens),
        prompt_chars=int(prompt_tokens * ratio),
        reserve_output_tokens=int(output_reserve),
        reserve_think_tokens=int(think_reserve),
        chars_per_token=float(ratio),
        source=source,
        notes=tuple(notes),
    )

"""Ollama model registry — dynamic discovery via CLI and HTTP API."""
from __future__ import annotations

import json
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from datetime import datetime


OLLAMA_BASE_URL = "http://localhost:11434"


@dataclass
class OllamaModel:
    name: str
    size_gb: float
    loaded: bool
    modified_at: str = ""
    family: str = ""
    capabilities: tuple[str, ...] = ()


def _run_ollama(*args: str, timeout: int = 15) -> tuple[int, str, str]:
    """Run an ollama command, return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            ["ollama", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", "ollama not found"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"
    except Exception as e:
        return -3, "", str(e)


def check_ollama_reachable(base_url: str = OLLAMA_BASE_URL, timeout: float = 5.0) -> bool:
    """Returns True if Ollama API is reachable."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_models(base_url: str = OLLAMA_BASE_URL, timeout: float = 10.0) -> list[OllamaModel]:
    """Query Ollama for available models. Tries HTTP API first, falls back to CLI."""
    models: list[OllamaModel] = []

    # Try HTTP API
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read())
        loaded_names = {m.name for m in list_loaded_models(base_url, timeout=timeout)}
        for m in data.get("models", []):
            name = m.get("name", "")
            size = m.get("size", 0) / 1e9
            family = m.get("details", {}).get("family", "")
            modified = m.get("modified_at", "")
            models.append(OllamaModel(
                name=name, size_gb=round(size, 2),
                loaded=(name in loaded_names), modified_at=modified, family=family,
                capabilities=tuple(m.get("capabilities") or ())
            ))
        return models
    except Exception:
        pass

    # Fallback: parse CLI output
    rc, out, _ = _run_ollama("list")
    if rc != 0:
        return []
    loaded_names = {m.name for m in list_loaded_models(base_url, timeout=timeout)}
    for line in out.strip().splitlines()[1:]:  # skip header
        parts = line.split()
        if parts:
            name = parts[0]
            models.append(OllamaModel(
                name=name, size_gb=0.0, loaded=(name in loaded_names)
            ))
    return models


def list_loaded_models(base_url: str = OLLAMA_BASE_URL, timeout: float = 5.0) -> list[OllamaModel]:
    """Query which models are currently loaded (running) in Ollama."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/ps", timeout=timeout) as resp:
            data = json.loads(resp.read())
        result = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size = m.get("size", 0) / 1e9
            result.append(OllamaModel(name=name, size_gb=round(size, 2), loaded=True))
        return result
    except Exception:
        pass

    # CLI fallback
    rc, out, _ = _run_ollama("ps")
    if rc != 0:
        return []
    result = []
    for line in out.strip().splitlines()[1:]:
        parts = line.split()
        if parts:
            result.append(OllamaModel(name=parts[0], size_gb=0.0, loaded=True))
    return result


def loaded_model_context(name: str, base_url: str = OLLAMA_BASE_URL,
                         timeout: float = 5.0) -> int | None:
    """Read the effective context length Ollama reports for a loaded model.

    Read-only diagnostic: this never changes the server/model configuration.
    """
    try:
        with urllib.request.urlopen(f"{base_url}/api/ps", timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    for item in data.get("models", []) if isinstance(data, dict) else []:
        if str(item.get("name") or "") != str(name):
            continue
        for key in ("context_length", "context", "num_ctx"):
            value = item.get(key)
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                continue
    return None


def stop_model(name: str) -> bool:
    """Request Ollama to unload a model."""
    rc, _, _ = _run_ollama("stop", name)
    return rc == 0

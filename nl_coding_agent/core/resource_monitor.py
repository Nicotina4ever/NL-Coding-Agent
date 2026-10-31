"""Local machine capacity snapshot for the workbench HUD.

This is deliberately observational: it never starts a model, loads a GPU or
changes a scheduler decision. It reports RAM, CPU, NVIDIA memory (when
``nvidia-smi`` is present), currently loaded Ollama models and bounded warnings.
Long local model runs are expected; these numbers help the user decide when to
wait instead of using a fixed timeout.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from typing import Any


def _memory() -> dict:
    try:
        import psutil
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "total_mb": round(vm.total / 1048576, 1),
            "available_mb": round(vm.available / 1048576, 1),
            "used_percent": round(float(vm.percent), 1),
            "swap_used_mb": round(float(swap.used) / 1048576, 1),
        }
    except Exception:
        return {}


def _cpu() -> dict:
    try:
        import psutil
        return {"percent": round(float(psutil.cpu_percent(interval=0.2)), 1),
                "count": int(psutil.cpu_count() or 0)}
    except Exception:
        return {}


def _gpu() -> list[dict]:
    if shutil.which("nvidia-smi") is None:
        return []
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return []
    if result.returncode != 0:
        return []
    gpus = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            total, used, util = float(parts[2]), float(parts[3]), float(parts[4])
        except ValueError:
            continue
        gpus.append({
            "index": int(parts[0]) if parts[0].isdigit() else 0,
            "name": parts[1],
            "total_mb": total,
            "used_mb": used,
            "free_mb": round(total - used, 1),
            "utilization_percent": util,
        })
    return gpus


def _loaded_models() -> list[str]:
    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(base + "/api/ps", timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
        return [str(item.get("name") or item.get("model") or "")
                for item in data.get("models") or [] if isinstance(item, dict)]
    except Exception:
        return []


def snapshot() -> dict[str, Any]:
    ram = _memory()
    gpus = _gpu()
    warnings: list[str] = []
    min_free_ram = float(os.environ.get("NL_MIN_FREE_RAM_MB", "1024"))
    min_free_vram = float(os.environ.get("NL_MIN_FREE_VRAM_MB", "512"))
    if ram and float(ram.get("available_mb") or 0) < min_free_ram:
        warnings.append("RAM disponibile sotto " + str(int(min_free_ram)) + " MB")
    for gpu in gpus:
        if float(gpu.get("free_mb") or 0) < min_free_vram:
            warnings.append("VRAM libera bassa su " + str(gpu.get("name") or "GPU") +
                            ": " + str(int(float(gpu.get("free_mb") or 0))) + " MB")
    return {
        "checked_at": time.time(),
        "ram": ram,
        "cpu": _cpu(),
        "gpus": gpus,
        "loaded_models": _loaded_models(),
        "warnings": warnings,
    }

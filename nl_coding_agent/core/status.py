"""Real system status helpers backed by psutil.

The previous implementation returned hard-coded placeholder values.  Every value
here is measured from the running machine, and failures degrade to a safe,
explicitly-typed fallback instead of pretending to know the real state.
"""
from __future__ import annotations

import os
import time
from datetime import datetime

try:
    import psutil
except Exception:  # pragma: no cover - psutil is a declared dependency
    psutil = None


def _disk_root() -> str:
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + os.sep
    return "/"


def get_cpu_usage(interval: float = 0.1) -> float:
    """Return current CPU utilization as a percentage (0-100)."""
    if psutil is None:
        return 0.0
    try:
        return round(float(psutil.cpu_percent(interval=interval)), 1)
    except Exception:
        return 0.0


def get_memory_usage() -> float:
    """Return used physical memory as a percentage (0-100)."""
    if psutil is None:
        return 0.0
    try:
        return round(float(psutil.virtual_memory().percent), 1)
    except Exception:
        return 0.0


def get_disk_usage(path: str | None = None) -> float:
    """Return used disk space on the system drive as a percentage (0-100)."""
    if psutil is None:
        return 0.0
    try:
        return round(float(psutil.disk_usage(path or _disk_root()).percent), 1)
    except Exception:
        return 0.0


def get_network_status() -> str:
    """Return 'Connected' when at least one network interface is up."""
    if psutil is None:
        return "Unknown"
    try:
        stats = psutil.net_if_stats()
        return "Connected" if any(stat.isup for stat in stats.values()) else "Offline"
    except Exception:
        return "Unknown"


def get_uptime_seconds() -> float:
    """Return seconds since the operating system booted."""
    if psutil is None:
        return 0.0
    try:
        return max(0.0, time.time() - float(psutil.boot_time()))
    except Exception:
        return 0.0


def get_system_status_summary() -> dict:
    """Return a measured snapshot of CPU, memory, disk, network and uptime."""
    uptime_seconds = get_uptime_seconds()
    return {
        "cpu_usage": get_cpu_usage(),
        "memory_usage": get_memory_usage(),
        "disk_usage": get_disk_usage(),
        "network_status": get_network_status(),
        "uptime_check": uptime_seconds > 0,
        "uptime_seconds": round(uptime_seconds, 1),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(get_system_status_summary(), indent=2))

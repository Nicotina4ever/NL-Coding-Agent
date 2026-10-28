"""F3b: debugger/DAP readiness with an explicit, fail-closed session adapter.

Detection is read-only. No debugger starts silently: starting a session is an explicit
human action, and when no supported local debugger is available the adapter fails closed
with deterministic codes. The in-app debug UI is intentionally minimal in F3b; the DAP
transport is a documented seam for F3c.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Protocol

__all__ = ["DebugError", "DebugAdapter", "DebugManager", "detect_debuggers"]


class DebugError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


def _available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def detect_debuggers() -> dict:
    debugpy = _available("debugpy")
    pdb_available = _available("pdb")
    pick = "debugpy" if debugpy else ("pdb" if pdb_available else None)
    return {"debugpy": debugpy, "pdb": pdb_available, "selected": pick,
            "dap": debugpy,
            "available": bool(pick),
            "message": "" if pick else
            "No local debugger is available (debugpy/pdb); no in-app debugging is offered.",
            "manual_debugging": "pdb requires an interactive console and is not started in-app."}


class DebugAdapter(Protocol):
    def start(self, *, script: str | None = None, args: list[str] | None = None) -> dict: ...
    def stop(self) -> dict: ...
    def status(self) -> dict: ...


class DebugManager:
    """Explicit session manager; adapters are injected in tests."""

    def __init__(self, *, detector=None) -> None:
        self._detector = detector or detect_debuggers
        self._adapter = None

    def status(self) -> dict:
        data = dict(self._detector())
        data.update({"session_active": self._adapter is not None})
        return data

    def start(self, *, script: str | None = None, args: list[str] | None = None,
              adapter: DebugAdapter | None = None) -> dict:
        if self._adapter is not None:
            raise DebugError("session-active", "A debug session is already active.")
        selected = adapter
        if selected is None:
            status = self.status()
            if not status.get("available"):
                raise DebugError("debugger-unavailable",
                                 "No local debugger is available; nothing was started.")
            if status.get("selected") == "pdb":
                raise DebugError(
                    "pdb-manual-only",
                    "pdb is available only in an interactive console; the app does not "
                    "start it silently. Use an explicit terminal for pdb.")
            raise DebugError("adapter-not-configured",
                             "debugpy is installed but no explicit adapter was configured yet.")
        self._adapter = selected
        try:
            return selected.start(script=script, args=args or [])
        except Exception:
            self._adapter = None
            raise

    def stop(self) -> dict:
        if self._adapter is None:
            return {"stopped": False, "reason": "no active debug session"}
        result = self._adapter.stop()
        self._adapter = None
        return result or {"stopped": True}

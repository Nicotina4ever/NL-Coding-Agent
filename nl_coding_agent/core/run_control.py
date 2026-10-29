"""Cooperative stop/pause control for a supervised mission (C3c).

The persistent supervisor polls its durable command table and translates commands
into a RunControl shared with the orchestrator. The orchestrator calls
RunControl.checkpoint() only at safe stage boundaries, so a stop request never
interrupts a promotion write or a journaled CAS operation.
"""
from __future__ import annotations

import threading
from typing import Callable

__all__ = ["RunStopped", "RunControl"]


class RunStopped(RuntimeError):
    """Raised at a safe checkpoint when a stop was requested."""

    def __init__(self, stage: str, reason: str = "") -> None:
        self.stage = str(stage)
        self.reason = str(reason or "")
        message = "Run stopped at checkpoint " + repr(self.stage)
        if self.reason:
            message += ": " + self.reason
        super().__init__(message)


class RunControl:
    """Thread-safe stop/pause flags shared by the supervisor and orchestrator.

    stop: consumed by checkpoint() -> raises RunStopped (safe boundary only).
    pause: intentionally NOT raised inside the orchestrator in C3; the supervisor
           honours it at mission boundaries so no half-written mission is paused.
    """

    def __init__(
        self,
        *,
        stop_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        on_checkpoint: Callable[[str], None] | None = None,
    ) -> None:
        self._stop = stop_event if stop_event is not None else threading.Event()
        self._pause = pause_event if pause_event is not None else threading.Event()
        self._reason = ""
        self._checkpoint_hook = on_checkpoint
        self._checkpoint_hooks = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ flags

    @property
    def stop_requested(self) -> bool:
        return bool(self._stop.is_set())

    @property
    def pause_requested(self) -> bool:
        return bool(self._pause.is_set())

    @property
    def stop_reason(self) -> str:
        with self._lock:
            return self._reason

    def request_stop(self, reason: str = "") -> None:
        with self._lock:
            if reason:
                self._reason = str(reason)
            elif not self._reason:
                self._reason = "stop requested"
        self._stop.set()

    def request_pause(self) -> None:
        self._pause.set()

    def clear_pause(self) -> None:
        self._pause.clear()

    def clear_stop(self) -> None:
        """Resume support: clear a previous stop request (a new run must start clean)."""
        with self._lock:
            self._reason = ""
        self._stop.clear()

    def reset(self) -> None:
        self.clear_pause()
        self.clear_stop()

    # ------------------------------------------------------------ checkpoints

    def add_checkpoint_hook(self, hook: Callable[[str], None]) -> None:
        """Compose backend policy hooks with caller-supplied stop/pause control."""
        with self._lock:
            if hook not in self._checkpoint_hooks:
                self._checkpoint_hooks.append(hook)

    def checkpoint(self, stage: str) -> None:
        """Call at safe stage boundaries; raises RunStopped when stop is requested."""
        with self._lock:
            hooks = list(self._checkpoint_hooks)
        if self._checkpoint_hook is not None:
            self._checkpoint_hook(str(stage))
        for hook in hooks:
            hook(str(stage))
        if self._stop.is_set():
            raise RunStopped(stage, self.stop_reason)

    def wait_if_paused(self) -> bool:
        """Best-effort pause helper (not used by the C3 orchestrator hook)."""
        if not self._pause.is_set():
            return True
        return False

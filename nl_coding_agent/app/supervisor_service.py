"""Background thread lifecycle for the persistent stage-3 supervisor (C3d).

The GUI/CLI never block on a supervisor run: SupervisorService owns one daemon
thread per project, emits structured events on the application event bus, keeps
the last result for display, and forwards stop/pause/resume through the durable
supervisor command table (so they also work from another process/CLI).

No supervisor policy lives here: this is only lifecycle + result/event plumbing.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from nl_coding_agent.app.services import Event, get_event_bus

__all__ = ["SupervisorService"]


class SupervisorService:
    """One background supervisor thread per project with a small status/result cache."""

    def __init__(
        self,
        project_root: str | Path,
        project_id: int | None = None,
        *,
        config_overrides: dict | None = None,
        orchestrator_factory: Callable | None = None,
        supervisor_runner: Callable | None = None,
        event_bus=None,
        on_result: Callable[[dict], None] | None = None,
    ) -> None:
        self.root = Path(project_root).resolve()
        self.project_id = int(project_id) if project_id is not None else None
        self.config_overrides = dict(config_overrides or {})
        self.orchestrator_factory = orchestrator_factory
        self._supervisor_runner = supervisor_runner
        self._bus = event_bus or get_event_bus()
        self._on_result = on_result

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state = "idle"
        self._last_result: dict | None = None
        self._last_error = ""
        self._stop_requested = False

    # ---------------------------------------------------------------- lifecycle

    def _runner(self) -> Callable:
        if self._supervisor_runner is not None:
            return self._supervisor_runner
        from nl_coding_agent.core.supervisor import run_supervisor

        return run_supervisor

    def _emit(self, level: str, message: str, payload: dict | None = None) -> None:
        try:
            self._bus.emit(Event(source="supervisor", level=level, message=message,
                                 payload=payload))
        except Exception:
            pass

    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def start(self, *, mode: str | None = None, max_missions: int | None = None) -> dict:
        with self._lock:
            if self.is_running():
                return {"ok": False, "reason": "Supervisor is already running.",
                        "state": self._state}
            self._state = "starting"
            self._last_error = ""
            self._stop_requested = False
            thread = threading.Thread(
                target=self._run, kwargs={"mode": mode, "max_missions": max_missions},
                name="supervisor-service", daemon=True,
            )
            self._thread = thread
            thread.start()
        self._emit("info", "Supervisor run scheduled in the background.")
        return {"ok": True, "state": "starting", "project_id": self.project_id,
                "thread": thread.name}

    def _run(self, *, mode: str | None, max_missions: int | None) -> None:
        self._emit("info", "Supervisor run started.",
                   {"project_id": self.project_id, "mode": mode,
                    "max_missions": max_missions})
        try:
            runner = self._runner()
            result = runner(
                self.root,
                project_id=self.project_id,
                mode=mode,
                max_missions=max_missions,
                config_overrides=self.config_overrides,
                orchestrator_factory=self.orchestrator_factory,
                event_sink=lambda payload: self._emit(
                    str((payload or {}).get("level") or "info"),
                    str((payload or {}).get("message") or ""),
                    (payload or {}).get("payload"),
                ),
            )
            with self._lock:
                self._last_result = dict(result or {})
                status = str((result or {}).get("status") or "unknown")
                self._state = status
            level = "info" if status in ("completed", "idle", "off") else "warning"
            self._emit(level, "Supervisor run finished: " + status,
                       {"status": status, "result": self._last_result})
            if self._on_result is not None:
                try:
                    self._on_result(self._last_result)
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001 - surfaced through status/event bus
            with self._lock:
                self._last_error = str(exc)
                self._state = "failed"
            self._emit("error", "Supervisor run failed: " + str(exc))
        finally:
            self._stop_requested = False

    # ------------------------------------------------------------ controls

    def _command(self, name: str, *, reason: str = "") -> dict:
        if self.project_id is None:
            return {"ok": False, "reason": "No project selected."}
        try:
            from nl_coding_agent.core.supervisor import supervisor_command

            result = supervisor_command(
                self.root, name, requested_by="app", reason=reason,
            )
            if name == "stop":
                self._stop_requested = True
            return result
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def stop(self, *, reason: str = "") -> dict:
        self._emit("warning", "Supervisor stop requested.", {"reason": reason})
        return self._command("stop", reason=reason)

    def pause(self) -> dict:
        self._emit("info", "Supervisor pause requested.")
        return self._command("pause")

    def resume(self) -> dict:
        self._emit("info", "Supervisor resume requested.")
        return self._command("resume")

    def status(self) -> dict:
        service = {
            "thread_running": self.is_running(),
            "state": self._state,
            "stop_requested": self._stop_requested,
            "last_error": self._last_error,
        }
        try:
            from nl_coding_agent.core.supervisor import supervisor_status

            snapshot = supervisor_status(self.root, project_id=self.project_id)
        except Exception as exc:
            snapshot = {"status": "unknown", "error": str(exc)}
        snapshot["service"] = service
        snapshot["last_result"] = self._last_result
        return snapshot

    def wait(self, timeout: float | None = None) -> dict | None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        return self._last_result

    @property
    def last_result(self) -> dict | None:
        return self._last_result

    def shutdown(self) -> None:
        """Best-effort controlled shutdown for app exit (never kills other processes)."""
        if self.is_running():
            self.stop(reason="application shutdown")
            self.wait(timeout=10)

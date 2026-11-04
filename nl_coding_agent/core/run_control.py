"""Cooperative stop/pause control for a supervised mission (C3c).

The persistent supervisor polls its durable command table and translates commands
into a RunControl shared with the orchestrator. The orchestrator calls
RunControl.checkpoint() only at safe stage boundaries, so a stop request never
interrupts a promotion write or a journaled CAS operation.
"""
from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from contextlib import closing
from typing import Callable

__all__ = ["RunStopped", "RunControl", "acknowledge_mission_resume"]


def persist_mission_resume(conn, mission_id):
    """Record a new authorized attempt together with consumption of the old Stop."""
    mission = conn.execute("SELECT review_verdict FROM missions WHERE id=?", (mission_id,)).fetchone()
    conn.execute("UPDATE tasks SET status='pending',last_error=NULL WHERE mission_id=? AND agent_role='tester' AND status IN ('failed','running','interrupted')", (mission_id,))
    if mission and mission["review_verdict"] == "REJECT":
        reviewed = conn.execute("SELECT 1 FROM tasks WHERE mission_id=? AND agent_role='reviewer' AND status='completed'", (mission_id,)).fetchone()
        if reviewed:
            conn.execute("UPDATE tasks SET status='pending',last_error=NULL WHERE mission_id=? AND agent_role IN ('developer','tester','reviewer')", (mission_id,))
        conn.execute("UPDATE missions SET review_verdict=NULL WHERE id=?", (mission_id,))
    for key, value in (("mission.stop." + str(mission_id), ""), ("mission.resume." + str(mission_id), uuid.uuid4().hex)):
        conn.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, value))


def acknowledge_mission_resume(mission_id: int, *, project_id: int) -> None:
    """Consume a cancellation only at an explicit GUI/CLI/client resume boundary.

    Automatic supervisor recovery must not erase the owner's durable stop request.
    The existing writer lock prevents clearing a flag while a mission is running.
    """
    from nl_coding_agent.core import permissions
    from nl_coding_agent.core.mission_lock import mission_lock
    from nl_coding_agent.persistence import database
    from nl_coding_agent.persistence.missions import get_mission
    for scope in (permissions.READ, permissions.WRITE, permissions.EXECUTE):
        permissions.require(scope, project_id=project_id)
    with mission_lock(mission_id):
        mission = get_mission(mission_id)
        if not mission or mission.get("project_id") != project_id:
            raise ValueError("Mission does not belong to the selected project")
        if mission["status"] in ("interrupted", "blocked", "failed"):
            with closing(database.get_connection()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute("SELECT 1 FROM app_settings WHERE key=? AND value!=''", ("mission.resume." + str(mission_id),)).fetchone():
                    persist_mission_resume(conn, mission_id)


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
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._stop = stop_event if stop_event is not None else threading.Event()
        self._pause = pause_event if pause_event is not None else threading.Event()
        self._reason = ""
        self._checkpoint_hook = on_checkpoint
        self._checkpoint_hooks = []
        self._lock = threading.Lock()
        self._clock = clock or time.monotonic
        self._deadline: float | None = None

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

    # --------------------------------------------------------------- deadline

    def set_deadline(self, seconds: float | None) -> None:
        """Bound one mission's wall time; the deadline is raised at a safe checkpoint.

        The Supervisor owns ``mission_wall_time_s``; without this the setting was only
        descriptive metadata, so a stuck model or an endless retry loop could keep a
        mission "running" indefinitely. The deadline never interrupts a promotion or a
        journaled CAS write: it is only evaluated inside checkpoint().
        """
        with self._lock:
            if seconds is None or float(seconds) <= 0:
                self._deadline = None
            else:
                self._deadline = self._clock() + float(seconds)

    def clear_deadline(self) -> None:
        with self._lock:
            self._deadline = None

    @property
    def deadline_remaining_s(self) -> float | None:
        with self._lock:
            deadline = self._deadline
        if deadline is None:
            return None
        return max(0.0, deadline - float(self._clock()))

    @property
    def deadline_exceeded(self) -> bool:
        remaining = self.deadline_remaining_s
        return remaining is not None and remaining <= 0.0

    # ------------------------------------------------------------ checkpoints

    def add_checkpoint_hook(self, hook: Callable[[str], None]) -> None:
        """Compose backend policy hooks with caller-supplied stop/pause control."""
        with self._lock:
            if hook not in self._checkpoint_hooks:
                self._checkpoint_hooks.append(hook)

    @contextmanager
    def observe_mission_stop(self, mission_id: int):
        """Translate the existing durable settings flag into a safe-point stop.

        GUI, CLI and external clients refer to the same mission id. Remove the
        hook afterward because a Supervisor reuses this control across missions.
        """
        from nl_coding_agent.persistence.database import get_setting
        def poll(stage):
            reason = get_setting("mission.stop." + str(int(mission_id)), "")
            if reason:
                self.request_stop(reason)
        self.add_checkpoint_hook(poll)
        try:
            yield self
        finally:
            with self._lock:
                self._checkpoint_hooks = [hook for hook in self._checkpoint_hooks if hook is not poll]

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
        if self.deadline_exceeded:
            raise RunStopped(
                stage,
                "Mission wall-time budget exceeded; staged work is retained and the "
                "mission can be resumed. Increase mission_wall_time_s to allow more time.",
            )

    def wait_if_paused(self) -> bool:
        """Best-effort pause helper (not used by the C3 orchestrator hook)."""
        if not self._pause.is_set():
            return True
        return False

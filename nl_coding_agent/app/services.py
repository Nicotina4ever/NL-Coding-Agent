"""Application services facade — single interface for GUI and CLI."""
from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from nl_coding_agent.persistence.database import init_db, log_event
from nl_coding_agent.projects.registry import (
    open_project as _open_project,
    list_recent as _list_recent,
    remove_project as _remove_project,
    get_project_facts as _get_project_facts,
)
from nl_coding_agent.models.ollama_registry import (
    check_ollama_reachable, list_models, list_loaded_models,
)
from nl_coding_agent.resources.scheduler import get_scheduler


@dataclass
class Event:
    source: str
    level: str
    message: str
    payload: dict | None = None


class EventBus:
    """Simple in-process pub/sub for structured events."""

    def __init__(self):
        self._subscribers: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s is not fn]

    def emit(self, event: Event) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for sub in subs:
            try:
                sub(event)
            except Exception:
                pass


# Global event bus
_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


class AppServices:
    """Facade for all application-level operations."""

    def __init__(self):
        self._db = init_db()
        self._bus = _bus

    # --- Project ---

    def open_project(self, path: str | Path) -> dict:
        result = _open_project(path)
        self._bus.emit(Event(
            source="projects",
            level="info",
            message=f"Opened project: {result['name']}",
            payload={"project_id": result["id"], "root": result["root"]},
        ))
        log_event(self._db, f"Opened project: {result['name']}", source="app")
        return result

    def list_recent_projects(self, limit: int = 20) -> list[dict]:
        return _list_recent(limit)

    def remove_project(self, project_id: int) -> bool:
        ok = _remove_project(project_id)
        if ok:
            self._bus.emit(Event(
                source="projects", level="info",
                message=f"Removed project id={project_id}",
            ))
        return ok

    def get_project_facts(self, project_id: int) -> dict:
        return _get_project_facts(project_id)

    # --- Ollama / Models ---

    def check_ollama(self) -> bool:
        return check_ollama_reachable()

    def list_models(self):
        return list_models()

    def list_loaded_models(self):
        return list_loaded_models()

    # --- Audit ---

    def create_mission(self, project_id: int | None, title: str, goal: str) -> int:
        from nl_coding_agent.persistence.missions import create_mission as _create_m
        m_id = _create_m(project_id, title, goal)
        self._bus.emit(Event(
            source="missions", level="info",
            message=f"Created mission #{m_id}: {title}",
            payload={"mission_id": m_id, "project_id": project_id},
        ))
        log_event(self._db, f"Created mission #{m_id}: {title}", source="missions")
        return m_id

    def list_missions(self, project_id: int | None = None) -> list[dict]:
        from nl_coding_agent.persistence.missions import list_missions as _list_m
        return _list_m(project_id)

    def get_mission_details(self, mission_id: int) -> dict | None:
        from nl_coding_agent.persistence.missions import get_mission, get_tasks, get_handoffs, get_verification_runs
        m = get_mission(mission_id)
        if not m:
            return None
        m["tasks"] = get_tasks(mission_id)
        m["handoffs"] = get_handoffs(mission_id)
        m["verification_runs"] = get_verification_runs(mission_id)
        return m

    def run_mission(
        self,
        mission_id: int,
        project_root: str | Path,
        goal: str,
        on_done: Callable | None = None,
    ) -> str:
        """Schedule autonomous multi-agent mission execution on the sequential scheduler."""
        task_id = f"mission-{mission_id}"
        root = Path(project_root).resolve()

        def _do_mission():
            from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
            orch = MultiAgentOrchestrator(root)
            try:
                res = orch.run_mission(mission_id=mission_id, goal=goal)
                if on_done:
                    on_done(res)
                return res
            except Exception as e:
                self._bus.emit(Event(
                    source="orchestrator", level="error",
                    message=f"Mission #{mission_id} failed: {e}",
                ))
                if on_done:
                    on_done({"status": "failed", "error": str(e)})
                raise

        scheduler = get_scheduler()
        scheduler.submit(task_id, _do_mission, label=f"Mission #{mission_id}: {goal[:30]}")
        return task_id

    # --- Audit ---

    def run_audit(self, project_id: int, on_done: Callable | None = None) -> str:
        """
        Schedule an audit task. Returns the task_id.
        The audit reads the project facts and emits structured events.
        Does NOT modify the target project.
        """
        from nl_coding_agent.projects.registry import get_project

        project = get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        task_id = f"audit-{project_id}"
        root = Path(project["root"])

        def _do_audit():
            from nl_coding_agent.projects.scanner import scan_project
            self._bus.emit(Event(
                source="audit", level="info",
                message=f"Starting audit of {root.name}",
                payload={"project_id": project_id},
            ))
            try:
                facts = scan_project(root)
                summary = (
                    f"Audit complete: {facts['file_count']} files, "
                    f"primary language: {facts['primary_language']}, "
                    f"frameworks: {', '.join(facts['frameworks']) or 'none detected'}"
                )
                self._bus.emit(Event(
                    source="audit", level="info",
                    message=summary,
                    payload={"project_id": project_id, "facts": {
                        "file_count": facts["file_count"],
                        "primary_language": facts["primary_language"],
                        "frameworks": facts["frameworks"],
                        "top_build_files": facts["top_build_files"],
                    }},
                ))
                log_event(self._db, summary, source="audit")
                if on_done:
                    on_done({"status": "ok", "facts": facts})
                return facts
            except Exception as e:
                msg = f"Audit failed: {e}"
                self._bus.emit(Event(source="audit", level="error", message=msg))
                log_event(self._db, msg, source="audit", level="error")
                if on_done:
                    on_done({"status": "error", "error": str(e)})
                raise

        scheduler = get_scheduler()
        scheduler.submit(task_id, _do_audit, label=f"Audit: {root.name}")
        return task_id

    # --- Events ---

    def recent_events(self, limit: int = 200) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


# Singleton
_services: AppServices | None = None
_services_lock = threading.Lock()


def get_services() -> AppServices:
    global _services
    with _services_lock:
        if _services is None:
            _services = AppServices()
        return _services

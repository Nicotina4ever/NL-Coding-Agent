"""Application services facade — single interface for GUI and CLI."""
from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from nl_coding_agent.persistence.database import db_path, init_db, log_event
from nl_coding_agent.projects.registry import (
    open_project as _open_project,
    list_recent as _list_recent,
    remove_project as _remove_project,
    get_project_facts as _get_project_facts,
)
from nl_coding_agent.models.ollama_registry import (
    check_ollama_reachable, list_models, list_loaded_models,
)
from nl_coding_agent.models.providers import ModelHub, build_providers
from nl_coding_agent.resources.scheduler import get_scheduler


APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_CONFIG = APP_ROOT / "config" / "models.yaml"


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
        self._supervisor_services: dict[int, object] = {}
        self._supervisor_lock = threading.Lock()

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

    def get_project(self, project_id: int) -> dict | None:
        from nl_coding_agent.projects.registry import get_project
        return get_project(project_id)

    def read_project_file(self, project_root: str | Path, rel_path: str) -> str:
        from nl_coding_agent.tools.filesystem import scoped_read_file
        return scoped_read_file(project_root, rel_path)

    def list_project_dir(self, project_root: str | Path, rel_path: str = ".") -> list[str]:
        from nl_coding_agent.tools.filesystem import scoped_list_dir
        return scoped_list_dir(project_root, rel_path)

    # --- External tools (SPEC-25 / NL-BP-073) ---

    def list_external_tools(self, probe: bool = True) -> list[dict]:
        """Read-only external tool discovery for Settings -> Permissions & External Tools.

        Probes are fixed, bounded version commands or a health GET; no tool is
        installed, copied, modified or handed arbitrary arguments.
        """
        from nl_coding_agent.tools.registry import ToolRegistry
        return ToolRegistry().describe_all(probe=probe)

    # --- Ollama / Models ---

    def check_ollama(self) -> bool:
        return check_ollama_reachable(self.get_ollama_url())

    def list_models(self):
        return list_models(self.get_ollama_url())

    def list_loaded_models(self):
        return list_loaded_models(self.get_ollama_url())

    def discover_models(self, timeout: float = 5.0):
        providers = build_providers(self.get_model_config())
        return ModelHub(providers).discover(timeout=timeout)

    def unload_model(self, provider_id: str, name: str) -> bool:
        providers = build_providers(self.get_model_config())
        return ModelHub(providers).unload(provider_id, name)

    def get_model_config_path(self) -> Path:
        override = os.environ.get("NL_MODELS_CONFIG")
        return Path(override) if override else DEFAULT_MODELS_CONFIG

    def get_model_config(self) -> dict:
        try:
            import yaml
            with self.get_model_config_path().open("r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:
            return {}

    def get_database_path(self) -> Path:
        return db_path()

    def get_ollama_url(self) -> str:
        config = self.get_model_config()
        return str((config.get("ollama") or {}).get("base_url") or "http://127.0.0.1:11434")

    def is_cloud_escalation_enabled(self) -> bool:
        config = self.get_model_config()
        fallback = (config.get("roles") or {}).get("fallback_cloud") or {}
        return bool(fallback.get("enabled", False))

    def get_agent_roles(self) -> list[dict]:
        roles = self.get_model_config().get("roles") or {}

        def role_model(role: str) -> str:
            return str((roles.get(role) or {}).get("model") or "")

        developer_model = role_model("developer")
        debugger_model = role_model("debugger") or developer_model
        return [
            {"role": "architect", "model": role_model("architect"), "kind": "llm"},
            {"role": "developer", "model": developer_model, "kind": "llm"},
            {
                "role": "tester",
                "model": "Deterministic verification",
                "kind": "deterministic",
            },
            {
                "role": "debugger",
                "model": debugger_model,
                "kind": "llm",
                "note": "" if role_model("debugger") else "defaults to developer",
            },
            {"role": "reviewer", "model": role_model("reviewer"), "kind": "llm"},
        ]

    def get_runtime_settings(self, project_root: str | Path | None = None) -> dict:
        root = None
        if project_root:
            try:
                root = str(Path(project_root).resolve())
            except Exception:
                root = str(project_root)
        return {
            "project_root": root,
            "database_path": str(self.get_database_path().resolve()),
            "ollama_base_url": self.get_ollama_url(),
            "model_config_path": str(self.get_model_config_path().resolve()),
            "cloud_escalation_enabled": self.is_cloud_escalation_enabled(),
        }

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
        from nl_coding_agent.persistence.missions import (
            get_mission, get_tasks, get_handoffs, get_verification_runs,
            get_task_attempts, mission_progress,
        )
        m = get_mission(mission_id)
        if not m:
            return None
        m["tasks"] = get_tasks(mission_id)
        m["handoffs"] = get_handoffs(mission_id)
        m["verification_runs"] = get_verification_runs(mission_id)
        m["attempts"] = get_task_attempts(mission_id)
        m["progress"] = mission_progress(mission_id)
        return m

    def next_roadmap_mission(self, project_root: str | Path) -> dict:
        from nl_coding_agent.core.roadmap import next_mission
        return next_mission(project_root)

    def run_mission(
        self,
        mission_id: int,
        project_root: str | Path,
        goal: str | None = None,
        on_done: Callable | None = None,
        developer_model: str | None = None,
        reviewer_model: str | None = None,
        debug_model: str | None = None,
        stop_after: str | None = None,
    ) -> str:
        """Schedule autonomous multi-agent mission execution on the sequential scheduler."""
        task_id = f"mission-{mission_id}"
        root = Path(project_root).resolve()

        def _do_mission():
            from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
            orch = MultiAgentOrchestrator(root)
            try:
                res = orch.run_mission(
                    mission_id=mission_id,
                    goal=goal,
                    developer_model=developer_model,
                    reviewer_model=reviewer_model,
                    debug_model=debug_model,
                    stop_after=stop_after,
                )
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

    # --- Persistent supervisor (stage 3) ---

    def _supervisor_service(self, project_id: int):
        from nl_coding_agent.app.supervisor_service import SupervisorService

        key = int(project_id)
        with self._supervisor_lock:
            service = self._supervisor_services.get(key)
            if service is not None:
                return service
            project = self.get_project(key)
            if not project:
                raise ValueError(f"Project {project_id} not found")
            service = SupervisorService(Path(project["root"]), key)
            self._supervisor_services[key] = service
            return service

    def supervisor_start(self, project_id: int, *, mode: str | None = None,
                         max_missions: int | None = None) -> dict:
        """Start the persistent supervisor in a background thread (non-blocking)."""
        return self._supervisor_service(project_id).start(
            mode=mode, max_missions=max_missions,
        )

    def supervisor_stop(self, project_id: int, *, reason: str = "") -> dict:
        with self._supervisor_lock:
            service = self._supervisor_services.get(int(project_id))
        if service is not None:
            return service.stop(reason=reason)
        return self._supervisor_command(project_id, "stop", reason=reason)

    def supervisor_pause(self, project_id: int) -> dict:
        with self._supervisor_lock:
            service = self._supervisor_services.get(int(project_id))
        if service is not None:
            return service.pause()
        return self._supervisor_command(project_id, "pause")

    def supervisor_resume(self, project_id: int) -> dict:
        with self._supervisor_lock:
            service = self._supervisor_services.get(int(project_id))
        if service is not None:
            return service.resume()
        return self._supervisor_command(project_id, "resume")

    def _supervisor_command(self, project_id: int, name: str, *,
                            reason: str = "") -> dict:
        project = self.get_project(int(project_id))
        if not project:
            return {"ok": False, "reason": "Project not found"}
        try:
            from nl_coding_agent.core.supervisor import supervisor_command

            return supervisor_command(
                Path(project["root"]), name, requested_by="app", reason=reason,
            )
        except Exception as exc:  # surfaced to the caller, never raised into Qt
            return {"ok": False, "error": str(exc)}

    def supervisor_status(self, project_id: int) -> dict:
        with self._supervisor_lock:
            service = self._supervisor_services.get(int(project_id))
        if service is not None:
            return service.status()
        project = self.get_project(int(project_id))
        if not project:
            return {"status": "idle", "error": "Project not found"}
        try:
            from nl_coding_agent.core.supervisor import supervisor_status

            return supervisor_status(Path(project["root"]), project_id=int(project_id))
        except Exception as exc:
            return {"status": "unknown", "error": str(exc)}

    def supervisor_preflight(self, project_id: int) -> dict:
        project = self.get_project(int(project_id))
        if not project:
            return {"ok": False, "blockers": ["Project not found"]}
        try:
            from nl_coding_agent.core.supervisor import Supervisor

            supervisor = Supervisor(Path(project["root"]), project_id=int(project_id))
            return supervisor.preflight().to_dict()
        except Exception as exc:
            return {"ok": False, "blockers": [str(exc)]}

    def supervisor_queue(self, project_id: int, *, limit: int = 50) -> list[dict]:
        try:
            from nl_coding_agent.persistence import supervisor_store

            return supervisor_store.list_queue(int(project_id), limit=int(limit))
        except Exception:
            return []

    def supervisor_approvals(self, project_id: int, *, status: str | None = None) -> list[dict]:
        try:
            from nl_coding_agent.persistence import supervisor_store
            return supervisor_store.list_approvals(int(project_id), status=status)
        except Exception:
            return []

    def supervisor_decide_approval(self, project_id: int, approval_id: int, *,
                                   approved: bool, reason: str = "",
                                   decided_by: str = "human") -> dict:
        from nl_coding_agent.core.supervisor import Supervisor
        from nl_coding_agent.projects.registry import get_project
        project = get_project(int(project_id))
        if not project:
            return {"ok": False, "error": "Project not found"}
        supervisor = Supervisor(Path(project["root"]), project_id=int(project_id))
        return supervisor.decide_approval(int(approval_id), approved=approved,
                                          decided_by=decided_by, reason=reason)

    def supervisor_flow_runs(self, project_id: int, *, limit: int = 20) -> list[dict]:
        """Read-only durable Flow run rows for one project (C4c)."""
        try:
            from nl_coding_agent.persistence import supervisor_store

            return supervisor_store.list_flow_runs(project_id=int(project_id))[: int(limit)]
        except Exception:
            return []

    def supervisor_flow_status(self, project_id: int, *, flow_id: str | None = None) -> dict:
        """Read-only Flow pipeline status: configured pipeline + runs (+ one state)."""
        pipeline = "sequential"
        try:
            from nl_coding_agent.persistence import database

            config = database.get_json_setting(
                "supervisor.project." + str(int(project_id))
            )
            pipeline = str(config.get("pipeline") or "sequential")
        except Exception:
            pipeline = "sequential"
        runs = self.supervisor_flow_runs(project_id)
        counts: dict[str, int] = {}
        for row in runs:
            state = str(row.get("status") or "")
            counts[state] = counts.get(state, 0) + 1
        payload: dict = {
            "pipeline": pipeline,
            "flow_runs": runs,
            "flow_counts": counts,
            "read_only": True,
        }
        if flow_id:
            payload["flow_id"] = str(flow_id)
            try:
                from nl_coding_agent.flows.persistence import AppFlowPersistence

                payload["state"] = AppFlowPersistence().load_state(str(flow_id))
            except Exception as exc:  # noqa: BLE001 - read-only best effort
                payload["state_error"] = str(exc)
        return payload

    def get_permissions(self, project_id: int | None = None) -> dict:
        """Read-only effective permission policy for the GUI/settings view."""
        try:
            from nl_coding_agent.core import permissions

            return {
                "scopes": list(permissions.SCOPES),
                "policy": permissions.get_policy(project_id),
                "cloud_escalation_enabled": self.is_cloud_escalation_enabled(),
            }
        except Exception as exc:
            return {"scopes": [], "policy": {}, "error": str(exc)}

    def shutdown_supervisors(self) -> None:
        with self._supervisor_lock:
            services = list(self._supervisor_services.values())
            self._supervisor_services.clear()
        for service in services:
            try:
                service.shutdown()
            except Exception:
                pass

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

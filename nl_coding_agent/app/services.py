"""Application services facade — single interface for GUI and CLI."""
from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

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


_CHAT_STORE_LOCK = threading.RLock()
_CHAT_TURN_LOCKS: dict[str, threading.Lock] = {}

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
            self._subscribers = [s for s in self._subscribers if s != fn]

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
        # Research facade is lazy: no research service, store scan or network
        # transport is created until a research method/status is requested.
        self._research_service_obj = None
        self._research_lock = threading.Lock()
        self._research_config: dict = {}
        self._research_network_configured = False
        self.research = _ResearchFacade(self)
        # Goal Mode G2 facade is lazy as well; no goal schema/DB work happens
        # until a goal method is invoked.
        self._goal_service_obj = None
        self._goal_lock = threading.Lock()

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
        # If a previous engine process died mid-Flow, finalize its abandoned row
        # now.  reconcile_flow_runs only touches rows whose owner PID is dead or
        # whose mission is already terminal; a live owner is never modified.
        try:
            from nl_coding_agent.persistence import supervisor_store

            supervisor_store.reconcile_flow_runs(
                project_id=int(result["id"]), active_flow_ids=(),
            )
        except Exception:
            pass
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

    # ----------------------------------------------------- LSP/MCP/debug (F3b)
    def _lsp_manager(self, project_root):
        root = str(Path(project_root).resolve())
        managers = getattr(self, "_lsp_managers", None)
        if managers is None:
            managers = self._lsp_managers = {}
        if root not in managers:
            from nl_coding_agent.app.lsp import LspManager
            managers[root] = LspManager(Path(root))
        return managers[root]

    def lsp_catalog(self) -> list[dict]:
        from nl_coding_agent.app.lsp import detect_language_servers
        return [server.to_dict() for server in detect_language_servers()]

    def lsp_start(self, project_root, language: str) -> dict:
        return self._lsp_manager(project_root).start(language)

    def lsp_diagnostics(self, project_root, language: str) -> dict:
        return self._lsp_manager(project_root).diagnostics(language)

    def lsp_problems(self, project_root, language: str) -> list[dict]:
        rows = []
        diagnostics = self.lsp_diagnostics(project_root, language)
        for uri, items in diagnostics.items():
            for item in items:
                rows.append({"severity": "error" if int(item.get("severity") or 1) <= 2 else "warning",
                             "source": "lsp", "message": str(item.get("message") or ""),
                             "path": uri, "line": item.get("line")})
        return rows

    def mcp_servers(self, *, project_id=None) -> list[dict]:
        from nl_coding_agent.app.mcp import McpManager
        return McpManager(project_id).servers()

    def mcp_tools(self, server_name: str, *, project_id=None) -> list[dict]:
        from nl_coding_agent.app.mcp import McpManager
        return McpManager(project_id).list_tools(server_name)

    def mcp_invoke_tool(self, server_name: str, tool_name: str, arguments=None, *,
                        project_id=None, human_approved: bool = False) -> dict:
        from nl_coding_agent.app.mcp import McpManager
        return McpManager(project_id).invoke_tool(
            server_name, tool_name, arguments or {}, human_approved=human_approved)

    def debug_status(self) -> dict:
        from nl_coding_agent.app.debug import DebugManager
        manager = getattr(self, "_debug_manager", None)
        if manager is None:
            manager = self._debug_manager = DebugManager()
        return manager.status()

    def debug_start(self, *, adapter=None, script=None) -> dict:
        from nl_coding_agent.app.debug import DebugManager
        manager = getattr(self, "_debug_manager", None)
        if manager is None:
            manager = self._debug_manager = DebugManager()
        return manager.start(script=script, adapter=adapter)

    def debug_stop(self) -> dict:
        manager = getattr(self, "_debug_manager", None)
        return manager.stop() if manager is not None else {"stopped": False}

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

    def generation_params(self, *, model_name: str = "", role: str = "",
                          provider_id: str = "ollama") -> dict:
        from nl_coding_agent.models.generation_params import (
            effective_params, list_params,
        )
        return {
            "effective": effective_params(model_name=model_name, role=role,
                                          provider_id=provider_id),
            "configured": list_params(),
        }

    def save_generation_params(self, params: dict, *, scope: str = "model",
                               provider_id: str = "ollama",
                               model_name: str = "", role: str = "") -> dict:
        from nl_coding_agent.models.generation_params import save_params
        saved = save_params(params, scope=scope, provider_id=provider_id,
                            model_name=model_name, role=role)
        self._bus.emit(Event(
            source="model_hub", level="info",
            message="Generation parameters saved",
            payload={"scope": scope, "provider_id": provider_id,
                     "model_name": model_name, "role": role, "params": saved},
        ))
        return saved

    def save_provider_settings(self, provider_id: str, **changes) -> dict:
        from nl_coding_agent.models.model_config_store import update_provider
        config = update_provider(provider_id, **changes)
        self._bus.emit(Event(source="model_hub", level="info",
                             message="Provider settings saved",
                             payload={"provider_id": provider_id, "changes": changes}))
        return config

    def save_role_settings(self, role: str, **changes) -> dict:
        from nl_coding_agent.models.model_config_store import update_role
        config = update_role(role, **changes)
        self._bus.emit(Event(source="model_hub", level="info",
                             message="Role model settings saved",
                             payload={"role": role, "changes": changes}))
        return config

    def save_cloud_escalation(self, enabled: bool) -> dict:
        from nl_coding_agent.models.model_config_store import set_cloud_escalation
        config = set_cloud_escalation(bool(enabled))
        self._bus.emit(Event(source="model_hub", level="info",
                             message="Cloud escalation setting saved",
                             payload={"enabled": bool(enabled)}))
        return config

    def set_permission_scope(self, scope: str, granted: bool, *,
                             project_id: int | None = None,
                             source: str = "gui") -> dict:
        from nl_coding_agent.core import permissions
        if bool(granted):
            permissions.grant(scope, project_id=project_id, source=source)
        else:
            permissions.revoke(scope, project_id=project_id, source=source)
        self._bus.emit(Event(source="permissions", level="info",
                             message=("Permission granted" if granted else "Permission revoked"),
                             payload={"scope": str(scope), "project_id": project_id}))
        return self.get_permissions(project_id)

    def probe_model_capabilities(self, model: str, *, timeout: float = 90.0,
                                 allow_cloud: bool = False) -> dict:
        from nl_coding_agent.core import permissions
        permissions.require(permissions.EXECUTE)
        from nl_coding_agent.models.operational_probes import probe_model_with_provider
        from nl_coding_agent.models.providers import build_providers
        route = str(model or "").strip()
        provider_id = "ollama"
        model_name = route
        if "/" in route:
            provider_id, model_name = route.split("/", 1)
        if not model_name:
            raise ValueError("A model name is required")
        config = self.get_model_config()
        providers = build_providers(config)
        provider = next(
            (item for item in providers if str(getattr(item, "provider_id", "")) == provider_id),
            None)
        if provider is None and provider_id == "ollama":
            provider = next(
                (item for item in providers if getattr(item, "kind", "") == "ollama"),
                None)
        if provider is None:
            raise ValueError("Provider is not configured: " + provider_id)
        records = probe_model_with_provider(
            provider, provider_id, model_name,
            timeout=max(5.0, min(float(timeout), 300.0)),
            allow_cloud=bool(allow_cloud),
        )
        by_name = {record.capability: record for record in records}
        quality = by_name.get("patch_quality")
        return {
            "model": model_name,
            "provider_id": provider_id,
            "tool_calling": by_name["tool_calling"].state if "tool_calling" in by_name else "unknown",
            "structured_output": (by_name["structured_output"].state
                                  if "structured_output" in by_name else "unknown"),
            "patch_quality": quality.state if quality else "unknown",
            "patch_score": float((quality.metadata or {}).get("score") or 0.0) if quality else 0.0,
            "capabilities": {key: value.to_dict() for key, value in by_name.items()},
        }

    def get_database_path(self) -> Path:
        return db_path()

    def _chat_store_dir(self) -> Path:
        path = db_path().parent / "chat"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _chat_history_path(self, project_id: int | None = None) -> Path:
        if project_id is None:
            return self._chat_store_dir() / "global.json"
        return self._chat_store_dir() / f"project-{int(project_id)}.json"

    def list_chat_messages(self, *, project_id: int | None = None,
                           session_id: str | None = None) -> list[dict]:
        from nl_coding_agent.app import chat_sessions
        if project_id is None:
            return self._legacy_list_chat_messages(project_id)
        return chat_sessions.messages(int(project_id), session_id=session_id)

    def _legacy_list_chat_messages(self, project_id: int | None = None) -> list[dict]:
        path = self._chat_history_path(project_id)
        with _CHAT_STORE_LOCK:
            if not path.is_file():
                return []
            data = json.loads(path.read_text(encoding="utf-8"))
            messages = data if isinstance(data, list) else data.get("messages") if isinstance(data, dict) else None
            if not isinstance(messages, list) or any(
                    not isinstance(item, dict) or item.get("role") not in ("user", "assistant", "system")
                    or not isinstance(item.get("content"), str) for item in messages):
                raise ValueError("Invalid chat history; original file preserved")
            return [dict(item) for item in messages]

    def _append_chat_message(self, project_id: int | None, role: str, content: str,
                             session_id: str | None = None, **metadata) -> dict:
        from nl_coding_agent.app import chat_sessions
        if project_id is None:
            from datetime import datetime
            item = {"role": role, "content": str(content or ""),
                    "created_at": datetime.now().isoformat(timespec="seconds"), **metadata}
            path = self._chat_history_path(None)
            with _CHAT_STORE_LOCK:
                messages = self._legacy_list_chat_messages(None)
                messages.append(item)
                from nl_coding_agent.core.recovery_store import _atomic_write
                _atomic_write(path, json.dumps(messages, ensure_ascii=False, indent=2).encode("utf-8"))
            return item
        return chat_sessions.append_message(
            int(project_id), role, content, session_id=session_id, **metadata)

    def list_chat_sessions(self, project_id: int, *, include_archived: bool = False) -> list[dict]:
        from nl_coding_agent.app import chat_sessions
        return chat_sessions.list_sessions(int(project_id), include_archived=include_archived)

    def create_chat_session(self, project_id: int, title: str = "New conversation") -> dict:
        from nl_coding_agent.app import chat_sessions
        return chat_sessions.create_session(int(project_id), title)

    def rename_chat_session(self, session_id: str, title: str) -> dict:
        from nl_coding_agent.app import chat_sessions
        return chat_sessions.rename_session(session_id, title)

    def archive_chat_session(self, session_id: str) -> dict:
        from nl_coding_agent.app import chat_sessions
        return chat_sessions.archive_session(session_id)

    def delete_chat_session(self, project_id: int, session_id: str) -> dict:
        from nl_coding_agent.app import chat_sessions
        return chat_sessions.delete_session(int(project_id), session_id)

    def search_chat_messages(self, project_id: int, query: str, limit: int = 100) -> list[dict]:
        from nl_coding_agent.app import chat_sessions
        return chat_sessions.search(int(project_id), query, limit=limit)

    def get_mcp_config(self) -> dict:
        from nl_coding_agent.app.mcp import load_mcp_config
        return load_mcp_config()

    def save_mcp_config(self, payload: dict) -> dict:
        from nl_coding_agent.app.mcp import save_mcp_config
        saved = save_mcp_config(payload)
        self._bus.emit(Event(source="mcp", level="info",
                             message="MCP server configuration saved",
                             payload={"servers": sorted((saved.get("servers") or {}).keys())}))
        return saved

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
        ] + self._custom_agent_role_entries()

    def _custom_agent_role_entries(self) -> list[dict]:
        entries: list[dict] = []
        for item in self.list_custom_agents():
            if not item.get("enabled", True):
                continue
            entries.append({
                "role": str(item.get("name") or item.get("role") or "custom"),
                "model": str(item.get("model") or ""),
                "kind": "llm",
                "note": "Configuration profile; custom execution is not connected yet",
                "execution_supported": False,
                "custom_agent_id": item.get("id"),
                "instructions": item.get("instructions", ""),
                "tools": item.get("tools", []),
                "permissions": item.get("permissions", []),
            })
        return entries

    def _custom_agents_path(self) -> Path:
        path = db_path().parent / "custom_agents.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def list_custom_agents(self) -> list[dict]:
        path = self._custom_agents_path()
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return [dict(item) for item in (data if isinstance(data, list) else [])
                if isinstance(item, dict)]

    def get_custom_agent(self, agent_id) -> dict | None:
        for item in self.list_custom_agents():
            if str(item.get("id")) == str(agent_id):
                return dict(item)
        return None

    def create_custom_agent(self, name: str, **fields) -> dict:
        import uuid
        agent = {
            "id": uuid.uuid4().hex[:12],
            "name": str(name or "Custom agent").strip() or "Custom agent",
            "enabled": True,
            "provider": str(fields.pop("provider", "ollama") or "ollama"),
            "model": str(fields.pop("model", "") or ""),
            "role": str(fields.pop("role", "") or ""),
            "instructions": str(fields.pop("instructions", "") or ""),
            "tools": list(fields.pop("tools", []) or []),
            "permissions": list(fields.pop("permissions", []) or []),
            "role_id": str(fields.pop("role_id", "") or ""),
        }
        agent.update({k: v for k, v in fields.items() if v is not None})
        agents = self.list_custom_agents()
        agents.append(agent)
        self._custom_agents_path().write_text(
            json.dumps(agents, ensure_ascii=False, indent=2), encoding="utf-8")
        self._bus.emit(Event(source="agents", level="info",
                            message=f"Created custom agent {agent['name']}",
                            payload={"agent_id": agent["id"]}))
        return agent

    def update_custom_agent(self, agent_id, **fields) -> dict | None:
        agents = self.list_custom_agents()
        updated = None
        for item in agents:
            if str(item.get("id")) == str(agent_id):
                item.update({k: v for k, v in fields.items() if v is not None})
                if "name" in fields:
                    item["name"] = str(item.get("name") or "Custom agent")
                updated = dict(item)
        if updated is None:
            return None
        self._custom_agents_path().write_text(
            json.dumps(agents, ensure_ascii=False, indent=2), encoding="utf-8")
        return updated

    def delete_custom_agent(self, agent_id) -> bool:
        agents = self.list_custom_agents()
        before = len(agents)
        agents = [item for item in agents if str(item.get("id")) != str(agent_id)]
        if len(agents) == before:
            return False
        self._custom_agents_path().write_text(
            json.dumps(agents, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    def duplicate_custom_agent(self, agent_id, name: str | None = None) -> dict | None:
        item = self.get_custom_agent(agent_id)
        if item is None:
            return None
        clone = dict(item)
        clone.pop("id", None)
        clone["name"] = name or (str(clone.get("name") or "Custom agent") + " copy")
        clone["enabled"] = True
        return self.create_custom_agent(clone.pop("name"), **clone)

    def list_agents(self, *args, **kwargs):
        return self.list_custom_agents(*args, **kwargs)

    def get_agent(self, *args, **kwargs):
        return self.get_custom_agent(*args, **kwargs)

    def add_custom_agent(self, *args, **kwargs):
        return self.create_custom_agent(*args, **kwargs)

    def save_custom_agent(self, *args, **kwargs):
        return self.update_custom_agent(*args, **kwargs)

    def remove_custom_agent(self, *args, **kwargs):
        return self.delete_custom_agent(*args, **kwargs)

    def clone_custom_agent(self, *args, **kwargs):
        return self.duplicate_custom_agent(*args, **kwargs)

    # Aliases are defined in AppServices after all method declarations.

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

    def goal_create_from_document_plan(self, plan_id: int, *,
                                      project_id: int | None = None,
                                      project_root=None,
                                      activate: bool = False) -> dict:
        """Bootstrap a Goal from an approved document plan's provenance metadata.

        The selected plan remains metadata: this only creates a normal goal and
        its milestones. No execution, code editing or mission is started.
        """
        try:
            plan_result = self.docs_plan_get(int(plan_id))
        except Exception as exc:
            return self._goal_error(exc)
        if not isinstance(plan_result, dict) or not plan_result.get("ok"):
            return plan_result if isinstance(plan_result, dict) else self._goal_error(
                RuntimeError("document plan unavailable"))
        try:
            plan = plan_result["plan"]
            current = plan.get("current") or {}
            if activate:
                raise ValueError("Import does not activate a goal; use the normal goal lifecycle")
            if (plan.get("status") != "approved" or not current.get("approved_at")
                    or current.get("version") != plan.get("current_version")):
                raise ValueError("Only an approved current document-plan version can be imported")
            resolved_project_id = project_id if project_id is not None else plan.get("project_id")
            if resolved_project_id is None:
                raise ValueError("Select a registered project before importing the plan")
            if plan.get("project_id") is not None and int(plan["project_id"]) != int(resolved_project_id):
                raise ValueError("Document plan belongs to another project")
            project = self.get_project(int(resolved_project_id))
            if not project:
                raise ValueError("Project is not registered")
            root = Path(project["root"]).resolve()
            if not plan.get("project_root") or Path(plan["project_root"]).resolve() != root:
                raise ValueError("Document plan root differs from the selected project")
            if project_root is not None and Path(project_root).resolve() != root:
                raise ValueError("Requested project root differs from the registered project")

            def criteria(items):
                return [item.get("text", "") if isinstance(item, dict) else item
                        for item in (items or [])]

            milestones = []
            for item in current.get("milestones") or []:
                if not isinstance(item, dict):
                    raise ValueError("Invalid document milestone")
                milestones.append({
                    "key": item.get("key"), "title": item.get("title"),
                    "description": item.get("description") or "",
                    "priority": item.get("priority") or "P1",
                    "dependencies": item.get("dependencies") or [],
                    "acceptance_criteria": criteria(item.get("acceptance_criteria")),
                    "risk": item.get("risk") or "",
                    "validation_strategy": item.get("validation_strategy") or item.get("validation") or "",
                })
            goal = self._goal_service().create_goal_from_plan(
                current.get("objective") or plan.get("objective") or "",
                title=current.get("title") or plan.get("title") or "",
                project_id=int(resolved_project_id),
                acceptance_criteria=criteria(current.get("acceptance_criteria")),
                reference_metadata={"source": "document_plan", "document_plan_id": int(plan_id),
                                    "plan_version": current["version"],
                                    "project_root": str(root)}, milestones=milestones)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "goal": goal, "plan_id": int(plan_id),
                "milestones": len(milestones), "executed": False}

    def chat_document_plan(self, project: dict, text: str, attachment_ids=None) -> dict:
        """Use the existing corpus/plan lifecycle; never create a coding mission."""
        from nl_coding_agent.app.attachments import get_attachment
        paths = []
        for attachment_id in attachment_ids or []:
            item = get_attachment(int(attachment_id))
            if item.get("project_id") != project["id"]:
                return self._document_plan_error(ValueError("Attachment belongs to another project"))
            if not item.get("has_text"):
                return self._document_plan_error(ValueError(
                    "Document planning requires readable text attachments"))
            paths.append(item["stored_path"])
        return self.docs_plan_generate(
            project_root=project["root"], project_id=project["id"],
            objective=text, paths=paths, consent=True)

    def chat_conversation(self, project: dict, text: str, attachment_ids=None, *, model_spec=None,
                          tools_enabled=False, max_calls=8, max_seconds=180,
                          allow_coding=False, resume=False, tool_protocol="native",
                          research_profile="manual", session_id: str | None = None) -> dict:
        """Persist a real conversation; attachment context never grants execution."""
        project_id = (project or {}).get("id")
        key = str(self._chat_history_path(project_id))
        with _CHAT_STORE_LOCK:
            turn_lock = _CHAT_TURN_LOCKS.setdefault(key, threading.Lock())
        if not turn_lock.acquire(blocking=False):
            return {"ok": False, "reply": "A reply is already running for this project."}
        try:
            from nl_coding_agent.app.attachments import get_attachment
            from nl_coding_agent.core import permissions
            permissions.require(permissions.READ, project_id=project_id)
            if session_id:
                from nl_coding_agent.app import chat_sessions
                session = chat_sessions.get_session(session_id)
                if session.get("project_id") != project_id:
                    raise ValueError("Chat session belongs to another project")
            attachments = []
            for attachment_id in attachment_ids or []:
                item = get_attachment(int(attachment_id))
                if item.get("project_id") != project_id:
                    raise ValueError("Attachment belongs to another project")
                attachments.append(item)
            history = self.list_chat_messages(project_id=project_id, session_id=session_id)
            if resume and not tools_enabled:
                raise ValueError("Resume requires explicit tool authorization")
            if not resume:
                self._append_chat_message(project_id, "user", text, session_id=session_id,
                                      attachment_ids=[item["id"] for item in attachments])
            if tools_enabled:
                from nl_coding_agent.app.chat_tools import converse
                result = converse(self, project, text, attachments, history, model_spec=model_spec,
                                  max_calls=max_calls, max_seconds=max_seconds, allow_coding=allow_coding,
                                  resume=resume, protocol=tool_protocol, research_profile=research_profile)
                if result.get("ok"):
                    route = result.get("route") or {}
                    self._append_chat_message(
                        project_id, "assistant", result["reply"], session_id=session_id,
                        run_id=result["run_id"],
                        model=route.get("model"), provider_id=route.get("provider_id"),
                        automatic=route.get("automatic"),
                    )
                    result["messages"] = self.list_chat_messages(
                        project_id=project_id, session_id=session_id)
                return result
            reply_info = self._chat_reply(project=project, text=text, attachments=attachments,
                                          tool_activity="", history=history,
                                          model_spec=model_spec)
            reply = reply_info["reply"]
            route = reply_info.get("route") or {}
            self._append_chat_message(project_id, "assistant", reply, session_id=session_id,
                                      model=route.get("model"),
                                      provider_id=route.get("provider_id"),
                                      automatic=route.get("automatic"))
            self._bus.emit(Event(source="chat", level="info", message="Chat reply",
                                 payload={"project_id": project_id, "role": "assistant"}))
            return {"ok": True, "reply": reply, "tool_activity": "",
                    "route": route,
                    "messages": self.list_chat_messages(project_id=project_id,
                                                        session_id=session_id)}
        except Exception as exc:
            return {"ok": False, "reply": str(exc),
                    "error": {"type": type(exc).__name__, "message": str(exc)}}
        finally:
            turn_lock.release()

    def cancel_chat_tools(self, project_id):
        from nl_coding_agent.app.chat_tools import cancel
        return cancel(self, int(project_id))

    def _chat_reply(self, *, project: dict, text: str, attachments, tool_activity: str,
                    history=None, model_spec=None) -> dict:
        config = self.get_model_config() or {}
        roles = config.get("roles") or {}
        spec = model_spec or str(((roles.get("chat") or roles.get("developer") or {}).get("model")) or "").strip()
        project_id = (project or {}).get("id")
        provider, model, _, error = self._resolve_chat_provider(spec, project_id=project_id)
        if error:
            raise ValueError(error)
        messages = [{"role": "system", "content": (
            "You are the NL Coding Agent assistant. Reply in the user's language. "
            "Conversation has no execution tools. Never claim to have edited files or run commands. "
            "Project: " + str((project or {}).get("root") or ""))}]
        def attachment_context(items, limit=8000):
            chunks = []
            for item in items:
                if item.get("has_text") and limit > 0:
                    body = str(item.get("extracted_text") or "")[:limit]
                    chunks.append("UNTRUSTED attachment " + str(item.get("name") or item["id"]) + ":\n" + body)
                    limit -= len(body)
            return "\n".join(chunks)

        # Saved references remain user context, never instructions or execution consent.
        from nl_coding_agent.app.attachments import get_attachment
        context_budget = 16000
        for item in (history or [])[-40:]:
            if item.get("role") in ("user", "assistant"):
                content = item["content"]
                if item["role"] == "user" and context_budget > 0:
                    old_attachments = []
                    for attachment_id in item.get("attachment_ids") or []:
                        try:
                            saved = get_attachment(int(attachment_id))
                            if saved.get("project_id") == project_id:
                                old_attachments.append(saved)
                        except (ValueError, KeyError, FileNotFoundError):
                            continue
                    old_context = attachment_context(old_attachments, min(8000, context_budget))
                    context_budget -= len(old_context)
                    if old_context:
                        content += "\n\n" + old_context
                messages.append({"role": item["role"], "content": content})
        context = attachment_context(attachments)
        messages.append({"role": "user", "content": text + ("\n\n" + context if context else "")})
        reply = provider.generate(model, text, timeout=120.0,
                                  project_id=project_id, messages=messages).strip()
        if not reply:
            raise ValueError("Model returned no response")
        route = {
            "provider_id": str(getattr(provider, "provider_id", "") or ""),
            "model": str(model or ""),
            "requested_spec": str(spec or ""),
            "automatic": not bool(str(model_spec or "").strip()),
        }
        return {"reply": reply, "route": route}

    @staticmethod
    def chat_workflow(text: str) -> str:
        from nl_coding_agent.core.doc_planning import is_document_plan_request

        if is_document_plan_request(text):
            return "document_plan"
        lowered = str(text or "").lower()
        coding_terms = (
            "implement", "fix", "build", "create mission", "create goal", "modify",
            "patch", "sviluppa", "implementa", "correggi", "modifica", "aggiungi",
            "create code", "change code", "refactor", "debug", "test")
        if any(term in lowered for term in coding_terms):
            return "coding"
        return "chat"

    def _resolve_chat_provider(self, provider_spec: str, *, project_id=None):
        """Resolve exactly one configured route and enforce permissions before I/O."""
        providers = build_providers(self.get_model_config() or {})
        by_id = {provider.provider_id: provider for provider in providers}
        if not provider_spec:
            return None, "", None, "No chat model configured."
        if "/" in provider_spec:
            provider_id, model = provider_spec.split("/", 1)
        elif len(providers) == 1:
            provider_id, model = providers[0].provider_id, provider_spec
        else:
            return None, provider_spec, None, "Select an explicit provider/model route."
        provider = by_id.get(provider_id)
        if provider is None:
            return None, model, provider_id, "Unknown or disabled provider: " + provider_id
        if not model.strip():
            return None, model, provider_id, "No chat model configured."
        provider.assert_generation_permitted(model, project_id)
        snapshot = provider.probe(timeout=5.0)
        if not snapshot.reachable:
            return None, model, provider_id, snapshot.error or "Provider unavailable"
        if model not in {item.name for item in snapshot.models}:
            return None, model, provider_id, "Model unavailable on selected provider: " + model
        return provider, model, provider_id, ""

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

    # ------------------------------------------------------- mission attachments
    def prepare_attachment_paths(self, project_id: int | None, paths,
                                 *, mission_id: int | None = None,
                                 source: str = "drop") -> dict:
        from nl_coding_agent.app import attachments
        return attachments.AttachmentStore().prepare_paths(
            paths, source=source, project_id=project_id, mission_id=mission_id)

    def prepare_attachment_text(self, project_id: int | None, text: str,
                                *, mission_id: int | None = None,
                                name: str = "pasted-text.txt") -> dict:
        from nl_coding_agent.app import attachments
        return attachments.AttachmentStore().prepare_text(
            text, name=name, project_id=project_id, mission_id=mission_id)

    def prepare_attachment_clipboard_image(self, project_id: int | None,
                                           image_bytes: bytes,
                                           *, mission_id: int | None = None) -> dict:
        from nl_coding_agent.app import attachments
        return attachments.AttachmentStore().prepare_clipboard_image(
            image_bytes, project_id=project_id, mission_id=mission_id)

    def list_mission_attachments(self, *, mission_id: int | None = None,
                                 project_id: int | None = None) -> list[dict]:
        from nl_coding_agent.app import attachments
        return attachments.list_attachments(mission_id=mission_id,
                                            project_id=project_id)

    def attach_attachments_to_mission(self, mission_id: int,
                                      attachment_ids: list[int]) -> int:
        from nl_coding_agent.app import attachments
        return attachments.attach_to_mission(int(mission_id), attachment_ids)

    def delete_attachment(self, attachment_id: int) -> bool:
        from nl_coding_agent.app import attachments
        return attachments.delete_attachment(int(attachment_id))

    # ------------------------------------------------------------- speech (F2)
    def speech_manager(self):
        manager = getattr(self, "_speech_manager", None)
        if manager is None:
            from nl_coding_agent.app.speech import SpeechManager
            manager = SpeechManager()
            self._speech_manager = manager
        return manager

    def speech_status(self) -> dict:
        manager = self.speech_manager()
        return {"capabilities": manager.capabilities.to_dict(),
                "audio_backend": manager.audio_backend(),
                "audio_available": manager.audio_backend() is not None,
                "active_model": manager.active_model(),
                "tts": manager.tts_status(), "cloud_asr": False, "telemetry": False}

    def speech_catalog(self) -> dict:
        return self.speech_manager().catalog()

    def speech_install_plan(self, engine: str) -> dict:
        return self.speech_manager().install_plan(engine)

    def speech_switch_model(self, model_id: str) -> dict:
        return self.speech_manager().switch_model(model_id)

    def speech_unload_model(self) -> dict:
        return self.speech_manager().unload_model()

    def speech_devices(self) -> dict:
        return self.speech_manager().list_input_devices()

    def speech_start_recording(self, *, max_seconds: int = 60) -> dict:
        return self.speech_manager().start_recording(max_seconds=max_seconds)

    def speech_stop_recording(self, session_id: str) -> dict:
        return self.speech_manager().stop_recording(session_id)

    def speech_transcribe(self, wav_path: str, *, language: str | None = None) -> dict:
        return self.speech_manager().transcribe(wav_path, language=language)

    def speech_tts_status(self) -> dict:
        return self.speech_manager().tts_status()

    def speech_speak(self, text: str) -> dict:
        return self.speech_manager().speak(text)


    # ------------------------------------------------------- Studio IDE (F3a)
    _EDITABLE_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
                          ".ini", ".cfg", ".csv", ".log", ".js", ".ts", ".css",
                          ".html", ".xml", ".sql", ".sh", ".bat", ".ps1", ".c",
                          ".h", ".cpp", ".java", ".cs", ".go", ".rs", ".rb", ".vue"}
    _MAX_EDITOR_BYTES = 2 * 1024 * 1024

    @staticmethod
    def _resolve_project_rel(project_root, rel_path):
        from pathlib import Path
        root = Path(project_root).resolve()
        target = (root / str(rel_path or "")).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("Path escapes the open project: " + repr(rel_path)) from exc
        return root, target

    def load_editor_file(self, project_root, rel_path):
        import hashlib
        root, target = self._resolve_project_rel(project_root, rel_path)
        if not target.is_file():
            return {"rel_path": str(rel_path), "error": "File not found",
                    "error_code": "not-found", "read_only": True}
        size = target.stat().st_size
        read_only = target.suffix.lower() not in self._EDITABLE_SUFFIXES or size > self._MAX_EDITOR_BYTES
        reason = "" if not read_only else ("File type/size is read-only in the editor (preview only).")
        raw = target.read_bytes()
        if b"\x00" in raw[:4096]:
            read_only = True
            reason = "Binary content cannot be edited as text."
        content = ""
        for encoding in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                content = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        return {"rel_path": target.relative_to(root).as_posix(), "content": content,
                "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": size,
                "read_only": read_only, "read_only_reason": reason,
                "suffix": target.suffix.lower()}

    def save_editor_file(self, project_root, rel_path, content, *, expected_sha256=None):
        import hashlib, json
        from nl_coding_agent.persistence import database
        root, target = self._resolve_project_rel(project_root, rel_path)
        if target.suffix.lower() not in self._EDITABLE_SUFFIXES:
            return {"ok": False, "error": "File type is read-only in the editor.",
                    "error_code": "read-only"}
        if not target.is_file():
            return {"ok": False, "error": "File not found", "error_code": "not-found"}
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected_sha256 and expected_sha256 != current:
            return {"ok": False, "error_code": "stale-content",
                    "error": "The file changed on disk. Reload before saving.", "sha256": current}
        data = str(content).encode("utf-8")
        if len(data) > self._MAX_EDITOR_BYTES:
            return {"ok": False, "error_code": "file-too-large"}
        target.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        try:
            database.log_event(self._db, "Saved editor file: " + str(rel_path),
                               source="editor", event_kind="file-save",
                               payload=json.dumps({"rel_path": str(rel_path), "sha256": digest}))
        except Exception:
            pass
        return {"ok": True, "sha256": digest, "size_bytes": len(data)}

    # --------------------------------------------------------- terminal policy
    _NETWORK_COMMANDS = {"curl", "wget", "ssh", "scp", "sftp", "ftp", "telnet",
                         "nc", "ncat", "ping", "tracert", "nslookup", "dig",
                         "invoke-webrequest", "invoke-restmethod", "iwr", "irm", "pip"}
    _DESTRUCTIVE_COMMANDS = {"rm", "del", "erase", "rmdir", "rd", "format", "mkfs",
                             "fdisk", "diskpart", "dd", "shutdown", "reboot", "taskkill",
                             "stop-process", "kill", "killall", "cipher", "takeown",
                             "icacls", "reg", "bcdedit", "schtasks", "wmic", "mklink",
                             "chmod", "chown", "sudo", "runas", "su"}
    _SHELL_COMMANDS = {"cmd", "powershell", "pwsh", "bash", "sh", "zsh", "fish", "csh"}
    _DESTRUCTIVE_GIT = {"reset", "clean", "rebase", "filter-branch", "checkout",
                        "restore", "branch", "tag", "worktree"}
    _SAFE_READ_GIT = {"status", "diff", "log", "show", "branch", "rev-parse"}
    _NETWORK_GIT = {"push", "fetch", "pull", "clone", "remote", "ls-remote", "submodule"}

    def terminal_policy(self, project_id, argv):
        from nl_coding_agent.core import permissions
        policy = permissions.get_policy(project_id)
        parts = [str(item) for item in (argv or []) if str(item or "").strip()]
        result = {"allowed": False, "argv": parts, "reason": "", "error_code": ""}
        if not parts:
            result.update(error_code="empty-command", reason="No command was provided.")
            return result
        if not policy.get(permissions.EXECUTE):
            result.update(error_code="execute-denied",
                          reason="The EXECUTE permission is not granted for this project.")
            return result
        command = parts[0].lower()
        if command in self._SHELL_COMMANDS or any(ch in " ".join(parts) for ch in ";|&$><"):
            result.update(error_code="shell-unsafe",
                          reason="Shell interpreters and shell metacharacters are not allowed.")
            return result
        if command in self._DESTRUCTIVE_COMMANDS:
            result.update(error_code="destructive-denied",
                          reason="Destructive command is denied by the terminal policy.")
            return result
        if command == "git" and len(parts) > 1:
            sub = parts[1].lower()
            if sub in self._DESTRUCTIVE_GIT:
                result.update(error_code="destructive-git-denied",
                              reason="Destructive git subcommand is denied.")
                return result
            if sub in self._NETWORK_GIT:
                if not policy.get(permissions.NETWORK):
                    result.update(error_code="network-denied",
                                  reason="Network command requires an explicit NETWORK grant "
                                         "(denied by default).")
                    return result
                result.update(error_code="network-explicit",
                              reason="This command requires NETWORK; an explicit grant is present.")
                return result
            if sub not in self._SAFE_READ_GIT and sub not in {"add", "commit"}:
                result.update(error_code="git-not-allowlisted",
                              reason="Only read-only/allowlisted git subcommands are permitted.")
                return result
        network = command in self._NETWORK_COMMANDS
        if network:
            if not policy.get(permissions.NETWORK):
                result.update(error_code="network-denied",
                              reason="Network command requires an explicit NETWORK grant "
                                     "(denied by default).")
                return result
            result.update(error_code="network-explicit",
                          reason="This command requires NETWORK; an explicit grant is present.")
        result.update(allowed=True, reason="allowed")
        return result

    def run_terminal_command(self, project_id, project_root, argv, *, cwd_rel=".",
                             timeout=30, runner=None):
        import json, shlex, subprocess
        from pathlib import Path
        from nl_coding_agent.persistence import database
        root = Path(project_root).resolve()
        parts = shlex.split(argv) if isinstance(argv, str) else [str(item) for item in (argv or [])]
        policy = self.terminal_policy(project_id, parts)
        cwd = (root / str(cwd_rel or ".")).resolve()
        try:
            cwd.relative_to(root)
        except ValueError:
            policy = {"allowed": False, "error_code": "cwd-escape",
                      "reason": "Working directory must stay inside the open project.",
                      "argv": parts}
        audit = {"argv": parts, "allowed": policy["allowed"], "project_id": project_id}
        if not policy["allowed"]:
            try:
                database.log_event(self._db, "Terminal command refused: " + " ".join(parts)[:500],
                                   source="terminal", level="warning",
                                   event_kind="terminal-refused",
                                   payload=json.dumps(audit, default=str))
            except Exception:
                pass
            return {"ok": False, "error_code": policy["error_code"], "error": policy["reason"],
                    "argv": parts, "stdout": "", "stderr": "", "exit_code": None,
                    "audited": True}
        try:
            database.log_event(self._db, "Terminal command started: " + " ".join(parts)[:500],
                               source="terminal", event_kind="terminal-start",
                               payload=json.dumps(audit, default=str))
        except Exception:
            pass
        try:
            if runner is not None:
                captured = runner(parts, cwd, timeout)
            else:
                captured = subprocess.run(parts, cwd=str(cwd), shell=False,
                                          capture_output=True, text=True, timeout=int(timeout),
                                          encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return {"ok": False, "error_code": "timeout", "error": "Command timed out.",
                    "argv": parts, "stdout": "", "stderr": "", "exit_code": None, "audited": True}
        except FileNotFoundError as exc:
            return {"ok": False, "error_code": "command-not-found", "error": str(exc),
                    "argv": parts, "stdout": "", "stderr": "", "exit_code": None, "audited": True}
        except Exception as exc:
            return {"ok": False, "error_code": "execution-failed", "error": str(exc),
                    "argv": parts, "stdout": "", "stderr": "", "exit_code": None, "audited": True}
        if isinstance(captured, dict):
            stdout = str(captured.get("stdout") or "")
            stderr = str(captured.get("stderr") or "")
            code = captured.get("returncode", captured.get("exit_code"))
        else:
            stdout, stderr = str(captured.stdout or ""), str(captured.stderr or "")
            code = captured.returncode
        limit = 100000
        try:
            database.log_event(self._db, "Terminal command finished (exit " + str(code) + "): "
                               + " ".join(parts)[:400], source="terminal",
                               event_kind="terminal-end",
                               payload=json.dumps({**audit, "exit_code": code}, default=str))
        except Exception:
            pass
        return {"ok": int(code or 0) == 0, "exit_code": code, "stdout": stdout[:limit],
                "stderr": stderr[:limit], "stdout_truncated": len(stdout) > limit,
                "stderr_truncated": len(stderr) > limit, "argv": parts, "audited": True}

    @staticmethod
    def _run_git_readonly(project_root, args):
        import subprocess
        from pathlib import Path
        root = Path(project_root).resolve()
        try:
            completed = subprocess.run(["git", "-C", str(root), *args],
                                       capture_output=True, text=True, timeout=20,
                                       encoding="utf-8", errors="replace", shell=False)
        except FileNotFoundError:
            return {"ok": False, "error_code": "git-not-installed",
                    "error": "git executable not found", "output": ""}
        except Exception as exc:
            return {"ok": False, "error_code": "git-failed", "error": str(exc), "output": ""}
        return {"ok": completed.returncode == 0, "output": completed.stdout or "",
                "error": completed.stderr.strip(),
                "error_code": None if completed.returncode == 0 else "git-error"}

    def git_status(self, project_root):
        branch = self._run_git_readonly(project_root, ["rev-parse", "--abbrev-ref", "HEAD"])
        status = self._run_git_readonly(project_root, ["status", "--porcelain=v1"])
        log = self._run_git_readonly(project_root, ["log", "-1", "--oneline"])
        if not status["ok"]:
            return {"ok": False, "error_code": status["error_code"],
                    "error": status["error"], "branch": None, "changes": []}
        changes = []
        for line in status["output"].splitlines():
            if line.strip():
                changes.append({"code": line[:2].strip() or "?", "path": line[3:]})
        return {"ok": True, "branch": branch["output"].strip() if branch["ok"] else None,
                "changes": changes, "last_commit": log["output"].strip() if log["ok"] else None}

    def git_diff(self, project_root, *, staged=False):
        args = ["diff", "--cached"] if staged else ["diff"]
        result = self._run_git_readonly(project_root, args)
        return {"ok": result["ok"], "diff": result["output"], "error": result.get("error") or ""}

    def git_log(self, project_root, *, limit=20):
        result = self._run_git_readonly(project_root,
                                        ["log", "--oneline", "--decorate", "-n", str(int(limit))])
        return {"ok": result["ok"], "log": result["output"], "error": result.get("error") or ""}

    def verification_problems(self, project_id=None):
        from nl_coding_agent.persistence import missions
        rows = []
        for mission in missions.list_missions(project_id)[:50]:
            mission_id = int(mission["id"])
            for run in missions.get_verification_runs(mission_id):
                if int(run.get("passed") or 0):
                    continue
                rows.append({"severity": "error", "source": "verification",
                             "mission_id": mission_id,
                             "message": str(run.get("command") or "verification failed")
                                        + " (exit " + str(run.get("exit_code")) + ")",
                             "created_at": run.get("created_at")})
        return rows

    def scan_project_problems(self, project_root, *, limit=50):
        import ast
        from pathlib import Path
        root = Path(project_root).resolve()
        findings = []
        from itertools import islice
        from nl_coding_agent.core.workspace import _iter_files
        # Apply exclusions within the selected root, never to its ancestors.
        # Reuse the bounded-size, non-following workspace traversal.
        py_files = islice((path for path in _iter_files(root)
                           if path.suffix.lower() == ".py"
                           and path.resolve().is_relative_to(root)), 200)
        for path in py_files:
            try:
                ast.parse(path.read_text(encoding="utf-8", errors="replace"),
                          filename=str(path))
            except SyntaxError as exc:
                findings.append({"severity": "error", "source": "scan",
                                 "message": "Syntax error in "
                                            + path.relative_to(root).as_posix()
                                            + ": " + str(exc.msg) + " (line "
                                            + str(exc.lineno) + ")",
                                 "path": path.relative_to(root).as_posix()})
            except OSError as exc:
                findings.append({"severity": "warning", "source": "scan",
                                 "message": "Unreadable file " + path.name + ": " + str(exc)})
            if len(findings) >= limit:
                break
        if not (root / "README.md").is_file():
            findings.append({"severity": "info", "source": "scan",
                             "message": "Project has no README.md; documentation discovery is limited."})
        return findings[:limit]

    def project_problems(self, project_id, project_root):
        verification = self.verification_problems(project_id)
        scan = self.scan_project_problems(project_root)
        problems = verification + scan
        return {"problems": problems,
                "counts": {"errors": sum(1 for row in problems
                                         if row.get("severity") == "error"),
                           "warnings": sum(1 for row in problems
                                           if row.get("severity") == "warning")}}

    def list_missions(self, project_id: int | None = None, *,
                      include_archived: bool = True,
                      status: str | None = None,
                      query: str | None = None) -> list[dict]:
        from nl_coding_agent.persistence.missions import list_missions as _list_m
        items = _list_m(project_id)
        if not include_archived:
            items = [item for item in items if not item.get("archived_at")]
        if status:
            items = [item for item in items if item.get("status") == status]
        if query:
            needle = str(query).lower()
            items = [item for item in items
                     if needle in str(item.get("title") or "").lower()
                     or needle in str(item.get("goal") or "").lower()]
        return items

    def archive_mission(self, mission_id: int, *, project_id: int | None = None) -> dict:
        from nl_coding_agent.persistence.missions import archive_mission as _archive
        return _archive(mission_id, project_id=project_id)

    def unarchive_mission(self, mission_id: int) -> dict:
        from nl_coding_agent.persistence.missions import unarchive_mission as _unarchive
        return _unarchive(mission_id)

    def delete_mission(self, mission_id: int, *, project_id: int | None = None) -> dict:
        from nl_coding_agent.persistence.missions import delete_mission as _delete
        return _delete(mission_id, project_id=project_id)

    def steer_mission(self, mission_id: int, text: str, *,
                      project_id: int | None = None) -> dict:
        from nl_coding_agent.persistence.missions import get_mission
        from nl_coding_agent.persistence import database
        message = str(text or "").strip()
        if not message:
            raise ValueError("Steering text is required")
        mission = get_mission(mission_id)
        if not mission:
            raise ValueError("Mission not found")
        if project_id is not None and mission.get("project_id") != project_id:
            raise ValueError("Mission belongs to another project")
        if mission.get("status") not in ("pending", "running", "interrupted", "blocked"):
            raise ValueError("Mission is not steerable in its current state")
        database.set_setting("mission.steer." + str(mission_id), message[:8000])
        self._bus.emit(Event(source="mission", level="info",
                             message=f"Steering recorded for mission #{mission_id}",
                             payload={"mission_id": int(mission_id)}))
        return {"ok": True, "mission_id": int(mission_id),
                "status": mission.get("status"), "characters": min(len(message), 8000)}

    def storage_scan(self, project_root: str | Path | None = None) -> dict:
        from nl_coding_agent.core.storage_manager import scan
        return scan(project_root)

    def storage_purge(self, selected_ids: list[str], *, confirm: bool = False,
                      project_root: str | Path | None = None) -> dict:
        from nl_coding_agent.core.storage_manager import purge
        result = purge(selected_ids, confirm=confirm, project_root=project_root)
        self._bus.emit(Event(source="storage", level="info",
                             message="Selective storage cleanup completed",
                             payload={"freed_bytes": result.get("freed_bytes"),
                                      "removed": result.get("removed")}))
        return result

    def storage_vacuum(self, *, confirm: bool = False) -> dict:
        from nl_coding_agent.core.storage_manager import vacuum_database
        result = vacuum_database(confirm=confirm)
        self._bus.emit(Event(source="storage", level="info",
                             message="SQLite compaction attempted",
                             payload={"freed_bytes": result.get("freed_bytes"),
                                      "ok": result.get("ok")}))
        return result

    def mission_candidate_diff(self, mission_id: int, *, project_id: int) -> dict:
        """Read an existing candidate without approving, promoting or executing it."""
        from nl_coding_agent.core import permissions, promotion
        from nl_coding_agent.persistence.missions import get_mission
        permissions.require(permissions.READ, project_id=project_id)
        mission = get_mission(mission_id)
        project = self.get_project(project_id)
        if not mission or not project or mission.get("project_id") != project_id:
            raise ValueError("Mission does not belong to the selected project")
        root = Path(project["root"]).resolve()
        if not mission.get("staging_dir"):
            return {"ok": False, "error": "No staged candidate is available"}
        stage_path = Path(mission["staging_dir"]).resolve()
        if not stage_path.is_relative_to(root / "data" / "staging"):
            raise ValueError("Candidate directory is outside project staging")
        if not stage_path.exists():
            # Successful promotion normally removes the disposable stage. Read
            # retained evidence, never substitute the current working-tree diff.
            from nl_coding_agent.persistence.database import db_path
            evidence_path = db_path().parent / "verification" / f"mission-{mission_id}.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.is_file() else {}
            if evidence and (evidence.get("mission_id") != mission_id or
                             Path(evidence.get("project_root", "")).resolve() != root):
                raise ValueError("Retained candidate evidence belongs to another project or mission")
            if "diff" not in evidence:
                return {"ok": False, "mission_id": mission_id,
                        "error": "Candidate stage was removed; this historical record has no retained diff"}
            return {"ok": True, "mission_id": mission_id, "diff": evidence["diff"],
                    "changed_paths": evidence.get("changed_paths", []),
                    "stat": evidence.get("diff_stat", ""), "status": mission["status"],
                    "verdict": mission.get("review_verdict"),
                    "promotion_status": mission.get("promotion_status"), "retained": True}
        stage = promotion.load_stage(stage_path)
        if stage.project_root != root or stage.mission_id != mission_id:
            raise ValueError("Candidate manifest belongs to another project or mission")
        diff, changed, stat = promotion.candidate_diff(stage)
        return {"ok": True, "mission_id": mission_id, "diff": diff,
                "changed_paths": changed, "stat": stat,
                "status": mission["status"], "verdict": mission.get("review_verdict"),
                "promotion_status": mission.get("promotion_status")}

    def mission_model_bindings(self, mission_id: int) -> dict[str, dict]:
        """Read the ModelRouter bindings persisted for a mission (read-only)."""
        from nl_coding_agent.models.model_router import ModelRouter
        try:
            return ModelRouter(project_id=None).load_mission_snapshot(int(mission_id))
        except Exception:
            return {}

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
        try:
            from nl_coding_agent.persistence import supervisor_store

            rows = supervisor_store.list_evidence(mission_id)
            m["execution_errors"] = [
                {"id": row.get("id"), "kind": row.get("kind"),
                 "record_key": row.get("record_key"),
                 "created_at": row.get("created_at"),
                 "payload": row.get("payload")}
                for row in rows
                if str(row.get("kind") or "") in ("execution_error", "reconciliation")
            ]
        except Exception:
            m["execution_errors"] = []
        try:
            from nl_coding_agent.core.tool_invocations import list_invocations
            m["tool_invocations"] = list_invocations(mission_id=mission_id, limit=500)
        except Exception:
            m["tool_invocations"] = []
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
        architect_model: str | None = None,
        stop_after: str | None = None,
        pipeline: str | None = None,
    ) -> str:
        """Schedule autonomous multi-agent mission execution on the sequential scheduler."""
        task_id = f"mission-{mission_id}"
        root = Path(project_root).resolve()
        from nl_coding_agent.persistence.missions import get_mission
        mission = get_mission(mission_id)
        project = self.get_project(mission["project_id"]) if mission else None
        if not project or Path(project["root"]).resolve() != root:
            raise ValueError("Mission does not belong to the requested project")
        if mission and mission["status"] == "interrupted":
            from nl_coding_agent.core.run_control import acknowledge_mission_resume
            acknowledge_mission_resume(mission_id, project_id=mission["project_id"])

        def _do_mission():
            from functools import partial
            from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
            from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
            from nl_coding_agent.persistence.missions import get_mission
            mission = get_mission(mission_id) or {}
            try:
                overrides = {key: value for key, value in {
                    "developer_model": developer_model, "reviewer_model": reviewer_model,
                    "debug_model": debug_model, "architect_model": architect_model,
                    "pipeline": pipeline}.items()
                    if value is not None}
                config = SupervisorConfig.load(mission.get("project_id"), overrides=overrides)
                def factory(project_root):
                    orchestrator = MultiAgentOrchestrator(project_root, project_id=mission.get("project_id"))
                    if stop_after:
                        orchestrator.run_mission = partial(orchestrator.run_mission, stop_after=stop_after)
                    return orchestrator
                res = Supervisor(root, project_id=mission.get("project_id"), config=config,
                                 orchestrator_factory=factory).execute_mission(mission_id)
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
        scheduler.submit(task_id, _do_mission, label=f"Mission #{mission_id}: {(goal or '')[:30]}")
        return task_id

    def cancel_mission(self, mission_id: int, *, project_id: int, reason="User cancellation") -> dict:
        """Request a durable cooperative stop; never kill a promotion write."""
        from nl_coding_agent.core import permissions
        from nl_coding_agent.persistence.database import set_setting
        from nl_coding_agent.persistence.missions import get_mission
        permissions.require(permissions.READ, project_id=project_id)
        mission = get_mission(mission_id)
        if not mission or mission.get("project_id") != project_id:
            raise ValueError("Mission does not belong to the selected project")
        if mission["status"] not in ("pending", "running"):
            return {"ok": True, "accepted": False, "status": mission["status"], "mission_id": mission_id}
        set_setting("mission.stop." + str(int(mission_id)), str(reason or "User cancellation")[:500])
        payload = {"mission_id": mission_id, "project_id": project_id, "cooperative": True}
        log_event(self._db, "Mission stop requested at the next safe checkpoint", source="missions",
                  event_kind="mission-stop-requested", project_id=project_id, mission_id=mission_id,
                  payload=json.dumps(payload))
        self._bus.emit(Event("missions", "info", "Stop requested; waiting for a safe checkpoint", payload))
        return {"ok": True, "accepted": True, "status": "stop_requested", **payload}

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
                         max_missions: int | None = None,
                         work_source: str | None = None) -> dict:
        """Start the persistent supervisor in a background thread (non-blocking)."""
        return self._supervisor_service(project_id).start(
            mode=mode, max_missions=max_missions,
            **({"work_source": work_source} if work_source is not None else {}),
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

    # --- Autonomy modes, budgets, preview and history (stage-4 GUI controls) ---
    #
    # These wrappers exist so GUI widgets never import supervisor/store modules and
    # never contain supervisor policy. Nothing here starts a run or calls a model:
    # saving persists validated settings only, and the preview/history calls are
    # read-only snapshots for display.

    AUTONOMY_MODES = ("off", "assisted", "automatic")

    def _autonomy_project(self, project_id: int) -> dict | None:
        from nl_coding_agent.projects.registry import get_project

        return get_project(int(project_id))

    def autonomy_settings(self, project_id: int) -> dict:
        """Return the persisted autonomy mode/budgets for one project (read-only)."""
        defaults = {
            "mode": "off",
            "max_missions_per_run": 1,
            "max_attempts_per_requirement": 2,
            "max_wall_time_s": 3600,
            "mission_wall_time_s": 1800,
            "pipeline": "sequential",
            "backlog_path": "docs/product-blueprint/INDEX.json",
            "resume_command": "",
        }
        try:
            from nl_coding_agent.core.supervisor import SupervisorConfig, resume_command

            config = SupervisorConfig.load(int(project_id))
            project = self._autonomy_project(project_id)
            resume = ""
            if project:
                resume = resume_command(
                    project["root"], mode=config.mode,
                    max_missions=config.max_missions_per_run,
                )
            return {
                "ok": True,
                "read_only": True,
                "starts_automatically": False,
                "project_id": int(project_id),
                "mode": config.mode,
                "max_missions_per_run": int(config.max_missions_per_run),
                "max_attempts_per_requirement": int(config.max_attempts_per_requirement),
                "max_wall_time_s": int(config.max_wall_time_s),
                "mission_wall_time_s": int(config.mission_wall_time_s),
                "pipeline": config.pipeline,
                "backlog_path": str(config.backlog_path),
                "resume_command": resume,
                "modes": list(self.AUTONOMY_MODES),
            }
        except Exception as exc:  # noqa: BLE001 - GUI boundary reports, never raises
            return {
                "ok": False,
                "read_only": True,
                "starts_automatically": False,
                "project_id": int(project_id),
                "error": str(exc),
                "modes": list(self.AUTONOMY_MODES),
                **defaults,
            }

    def save_autonomy_settings(
        self,
        project_id: int,
        *,
        mode: str | None = None,
        max_missions: int | None = None,
        attempts: int | None = None,
        max_wall_time_s: int | None = None,
        mission_wall_time_s: int | None = None,
    ) -> dict:
        """Persist validated autonomy settings. Never starts a run or a model."""
        updates: dict = {}
        if mode is not None:
            updates["mode"] = str(mode).strip().lower()
        if max_missions is not None:
            updates["max_missions_per_run"] = int(max_missions)
        if attempts is not None:
            updates["max_attempts_per_requirement"] = int(attempts)
        if max_wall_time_s is not None:
            updates["max_wall_time_s"] = int(max_wall_time_s)
        if mission_wall_time_s is not None:
            updates["mission_wall_time_s"] = int(mission_wall_time_s)
        if not updates:
            return {"ok": False, "started": False,
                    "error": "No autonomy settings to save."}
        try:
            from nl_coding_agent.core.supervisor import SupervisorConfig
            from nl_coding_agent.persistence import database

            # Validation is the supervisor's own contract (modes, 1..5 budgets,
            # positive wall clocks); invalid input fails closed here.
            config = SupervisorConfig.load(int(project_id), overrides=updates)
            key = "supervisor.project." + str(int(project_id))
            persisted = database.get_json_setting(key)
            persisted.update(updates)
            database.set_json_setting(key, persisted)
            return {
                "ok": True,
                "started": False,
                "project_id": int(project_id),
                "saved": {name: getattr(config, name) for name in updates},
                "mode": config.mode,
            }
        except Exception as exc:  # noqa: BLE001 - validation/DB error reported to the caller
            return {"ok": False, "started": False, "error": str(exc)}

    def autonomy_plan(self, project_id: int) -> dict:
        """Read-only execution preview built from persisted settings, queue and backlog.

        No supervisor run is created, no command is written and no backlog sync or
        other SQLite write happens here.
        """
        project = self._autonomy_project(project_id)
        if not project:
            return {
                "ok": False,
                "read_only": True,
                "starts_automatically": False,
                "error": "Project not found",
            }
        settings = self.autonomy_settings(project_id)
        plan: dict = {
            "ok": True,
            "read_only": True,
            "starts_automatically": False,
            "project_id": int(project_id),
            "project_root": str(project.get("root") or ""),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "mode": settings.get("mode", "off"),
            "settings": settings,
            "program_stage": None,
            "queue_counts": {},
            "next_requirements": [],
            "active_run": None,
            "resume_command": settings.get("resume_command", ""),
        }
        try:
            from nl_coding_agent.persistence import supervisor_store

            queue = supervisor_store.list_queue(int(project_id), limit=200) or []
            counts: dict[str, int] = {}
            for item in queue:
                state = str(item.get("state") or "?")
                counts[state] = counts.get(state, 0) + 1
            plan["queue_counts"] = counts
            plan["active_run"] = supervisor_store.get_active_run(int(project_id))
            backlog = supervisor_store.list_backlog() or []
            open_items = [
                item for item in backlog
                if str(item.get("supervisor_status") or "").strip().upper()
                not in ("VERIFIED", "COMPLETED", "SKIPPED")
            ]
            stage = next(
                (item.get("program_stage") for item in open_items
                 if item.get("program_stage") is not None),
                None,
            )
            plan["program_stage"] = stage
            if stage is not None:
                same_stage = [
                    item for item in open_items
                    if item.get("program_stage") in (None, int(stage))
                ]
                if same_stage:
                    open_items = same_stage
            plan["next_requirements"] = [
                {
                    "requirement_id": item.get("requirement_id"),
                    "title": item.get("title"),
                    "priority": item.get("priority"),
                    "program_stage": item.get("program_stage"),
                    "status": item.get("status"),
                }
                for item in open_items[:5]
            ]
        except Exception as exc:  # noqa: BLE001 - partial read-only preview stays usable
            plan["error"] = str(exc)
        return plan

    def autonomy_history(self, project_id: int, *, limit: int = 10) -> list[dict]:
        """Read-only supervisor run history for one project from SQLite."""
        try:
            from nl_coding_agent.persistence import database

            conn = database.get_connection()
            try:
                rows = conn.execute(
                    "SELECT id, project_id, mode, status, missions_completed, "
                    "missions_failed, started_at, finished_at, stopped_reason "
                    "FROM supervisor_runs WHERE project_id=? ORDER BY id DESC LIMIT ?",
                    (int(project_id), max(1, int(limit))),
                ).fetchall()
            finally:
                conn.close()
            return [dict(row) for row in rows]
        except Exception:  # noqa: BLE001 - empty history is a valid GUI state
            return []

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

    # ------------------------------------------------------------ research
    def configure_research(self, *, service=None, network_configured=None,
                           **options) -> dict:
        """Explicitly configure the research backend (no network is created here)."""
        with self._research_lock:
            self._research_config = dict(options)
            self._research_service_obj = service
            if network_configured is None:
                network_configured = any(
                    options.get(key) is not None for key in (
                        "fetch_transport", "http_transport", "github_client",
                        "huggingface_client"))
                if service is not None:
                    network_configured = any(
                        getattr(service, attr, None) is not None for attr in (
                            "_fetch_transport", "_http_transport",
                            "_github_client", "_huggingface_client"))
            self._research_network_configured = bool(network_configured)
        return self.research_status()

    def _research_service(self):
        with self._research_lock:
            if self._research_service_obj is not None:
                return self._research_service_obj
            from nl_coding_agent.research.providers import KnownUrl, default_registry
            from nl_coding_agent.research.service import ResearchService
            from nl_coding_agent.research.store import ResearchStore
            config = dict(self._research_config)
            config.pop("service", None)
            store = config.pop("store", None) or ResearchStore(db_path())
            try:
                rows = store.list_sources(limit=100)
            except Exception:
                rows = []
            known = [KnownUrl(row["canonical_url"], title=row.get("title") or "",
                              snippet=(row.get("excerpt") or "")[:200])
                     for row in rows if row.get("canonical_url")]
            registry = config.pop("registry", None) or default_registry(known_urls=known)
            self._research_service_obj = ResearchService(store=store,
                                                         registry=registry,
                                                         **config)
            return self._research_service_obj

    def _research_status_providers(self, service) -> list[dict]:
        providers = []
        try:
            for provider_id in service.registry.provider_ids():
                definition = service.registry.definition(provider_id)
                if definition is None:
                    continue
                status = service.registry.status(provider_id)
                caps = definition.capabilities
                providers.append({
                    "provider_id": provider_id, "name": caps.name,
                    "available": bool(status.available),
                    "status": "available" if status.available else status.reason,
                    "reason": status.detail or status.reason,
                    "offline": bool(caps.offline or not self._research_network_configured),
                    "auth_required": bool(caps.auth_required),
                    "cost_class": caps.cost_class,
                    "latency_class": caps.latency_class,
                    "search_types": list(caps.search_types),
                    "capabilities": list(caps.search_types),
                    "permission": "web-search",
                    "limitations": list(caps.limitations),
                })
        except Exception as exc:
            return providers + [{
                "provider_id": "unavailable", "name": "Research providers",
                "available": False, "status": "unavailable",
                "reason": type(exc).__name__ + ": " + str(exc),
                "offline": True, "auth_required": False,
                "capabilities": [], "permission": "web-search"}]
        return providers

    def research_status(self) -> dict:
        try:
            service = self._research_service()
            providers = self._research_status_providers(service)
            store_ok = True
            store_error = ""
        except Exception as exc:
            providers = []
            store_ok = False
            store_error = type(exc).__name__ + ": " + str(exc)
        offline = not self._research_network_configured
        return {
            "ok": store_ok, "status": "offline" if offline else "available",
            "offline": offline,
            "network_configured": bool(self._research_network_configured),
            "providers": providers, "provider_count": len(providers),
            "store_ok": store_ok, "store_error": store_error,
            "permission_state": "checked per action",
            "permission_guidance": (
                "web-search and web-fetch require explicit capability/auto-review "
                "approval; no default network transport is configured"),
            "untrusted": True,
            "reason": ("no explicit network transport/client configured; offline/"
                       "known-URL research only" if offline
                       else "explicit research transport/client configured"),
        }

    def _research_payload(self, result) -> dict:
        base = result.to_dict() if hasattr(result, "to_dict") else dict(result or {})
        payload = dict(base.get("payload") or {})
        offline = not self._research_network_configured
        output = {
            "ok": bool(base.get("allowed")),
            "outcome": str(base.get("outcome") or ""),
            "capability": str(base.get("capability") or ""),
            "reason": str(base.get("reason") or ""),
            "boundary": dict(base.get("boundary") or {}),
            "offline": bool(offline and base.get("outcome") in
                            ("allowed", "unavailable", "error")),
            "untrusted": True,
        }
        if base.get("needs_approval"):
            output["permission_needed"] = (base.get("reason")
                                             or "research capability approval required")
        if base.get("denied"):
            output["denied"] = True
            output["reason"] = base.get("reason") or "denied by policy"
        if base.get("error") and not output.get("permission_needed"):
            output["error"] = base.get("reason") or "research operation failed"
        for key, value in payload.items():
            if key not in output:
                output[key] = value
        return output

    def _research_offline_payload(self, operation: str) -> dict:
        return {
            "ok": False,
            "outcome": "unavailable",
            "offline": True,
            "operation": operation,
            "error": ("Research offline: no explicit research network transport/"
                      "client is configured. Configure one explicitly; no implicit "
                      "urllib/cloud request is made."),
            "untrusted": True,
        }

    def research_search(self, query: str, provider_id: str | None = None, *,
                        project_id: int | None = None, mission_id: int | None = None,
                        task_id: int | None = None, max_results: int = 10) -> dict:
        if not self._research_network_configured:
            return self._research_offline_payload("search")
        try:
            service = self._research_service()
            result = service.search(query, provider=provider_id,
                                    project_id=project_id, mission_id=mission_id,
                                    task_id=task_id, max_results=max_results)
        except Exception as exc:
            return self._research_failure("search", exc)
        payload = self._research_payload(result)
        routing = payload.get("routing") or {}
        payload["provider_id"] = routing.get("selected_provider")
        payload["results"] = list(payload.get("results") or [])
        return payload

    def research_fetch_read(self, url: str, *, project_id: int | None = None,
                            mission_id: int | None = None,
                            task_id: int | None = None,
                            headers: dict | None = None) -> dict:
        if not self._research_network_configured:
            return self._research_offline_payload("fetch_read")
        try:
            service = self._research_service()
            result = service.fetch_read(url, project_id=project_id,
                                        mission_id=mission_id, task_id=task_id,
                                        headers=headers)
        except Exception as exc:
            return self._research_failure("fetch_read", exc)
        payload = self._research_payload(result)
        page = payload.get("page") or {}
        text = str(page.get("text") or "")
        chunks = [line for line in text.splitlines() if line.strip()][:40]
        payload.setdefault("title", page.get("title") or payload.get("title") or "")
        payload["url"] = payload.get("canonical_url") or url
        payload["text"] = text
        payload["chunks"] = chunks
        payload["metadata"] = {"kind": page.get("kind") or "",
                               "truncated": bool(page.get("truncated")),
                               "supported": bool(payload.get("supported", False))}
        payload["provenance"] = dict(payload.get("provenance") or {})
        payload["redirects"] = list(payload["provenance"].get("redirect_chain") or [])
        return payload

    def research_github_lookup(self, *, action: str = "repository", **kwargs) -> dict:
        project_id = kwargs.pop("project_id", None)
        mission_id = kwargs.pop("mission_id", None)
        task_id = kwargs.pop("task_id", None)
        if not self._research_network_configured:
            return self._research_offline_payload("github_lookup")
        try:
            service = self._research_service()
            result = service.github_lookup(action=action, project_id=project_id,
                                           mission_id=mission_id,
                                           task_id=task_id, **kwargs)
        except Exception as exc:
            return self._research_failure("github_lookup", exc)
        payload = self._research_payload(result)
        payload["provider"] = "github"
        return payload

    def research_huggingface_lookup(self, *, action: str = "search_models",
                                    **kwargs) -> dict:
        project_id = kwargs.pop("project_id", None)
        mission_id = kwargs.pop("mission_id", None)
        task_id = kwargs.pop("task_id", None)
        if not self._research_network_configured:
            return self._research_offline_payload("huggingface_lookup")
        try:
            service = self._research_service()
            result = service.huggingface_lookup(action=action, project_id=project_id,
                                                mission_id=mission_id,
                                                task_id=task_id, **kwargs)
        except Exception as exc:
            return self._research_failure("huggingface_lookup", exc)
        payload = self._research_payload(result)
        payload["provider"] = "huggingface"
        return payload

    def research_save_finding(self, question: str, answer: str = "", *,
                              source_ids=None, confidence: float = 0.5,
                              project_id: int | None = None,
                              mission_id: int | None = None,
                              task_id: int | None = None,
                              metadata: dict | None = None) -> dict:
        try:
            service = self._research_service()
            result = service.save_finding(
                question, answer, source_ids=source_ids or (),
                confidence=confidence, project_id=project_id,
                mission_id=mission_id, task_id=task_id, metadata=metadata)
        except Exception as exc:
            return self._research_failure("save_finding", exc)
        payload = self._research_payload(result)
        payload["id"] = payload.get("finding_id")
        return payload

    def research_list_findings(self, *, project_id: int | None = None,
                               mission_id: int | None = None,
                               task_id: int | None = None,
                               text: str | None = None,
                               include_stale: bool = True, limit: int = 50,
                               offset: int = 0) -> dict:
        try:
            service = self._research_service()
            result = service.list_findings(
                project_id=project_id, mission_id=mission_id, task_id=task_id,
                text=text, include_stale=include_stale, limit=limit, offset=offset)
        except Exception as exc:
            return self._research_failure("list_findings", exc)
        payload = self._research_payload(result)
        payload["findings"] = list(payload.get("findings") or [])
        return payload

    def research_search_saved(self, text: str = "", *, project_id: int | None = None,
                              mission_id: int | None = None,
                              task_id: int | None = None,
                              include_stale: bool = True, limit: int = 50,
                              offset: int = 0) -> dict:
        try:
            service = self._research_service()
            result = service.search_saved(
                text, project_id=project_id, mission_id=mission_id, task_id=task_id,
                include_stale=include_stale, limit=limit, offset=offset)
        except Exception as exc:
            return self._research_failure("search_saved", exc)
        payload = self._research_payload(result)
        payload["sources"] = list(payload.get("sources") or [])
        payload["findings"] = list(payload.get("findings") or [])
        return payload

    def research_mark_stale(self, *, source_id: int | None = None,
                            finding_id: int | None = None,
                            reason: str = "") -> dict:
        try:
            service = self._research_service()
            result = service.mark_stale(source_id=source_id, finding_id=finding_id,
                                        reason=reason)
        except Exception as exc:
            return self._research_failure("mark_stale", exc)
        return self._research_payload(result)

    def research_refresh_source(self, source_id: int, *, excerpt: str | None = None,
                                content_sha256: str | None = None) -> dict:
        try:
            service = self._research_service()
            result = service.refresh_source(source_id, excerpt=excerpt,
                                            content_sha256=content_sha256)
        except Exception as exc:
            return self._research_failure("refresh_source", exc)
        return self._research_payload(result)

    @staticmethod
    def _research_permission_refusal(decision, operation: str) -> dict | None:
        if getattr(decision, "allowed", False):
            return None
        outcome = str(getattr(decision, "outcome", "denied") or "denied")
        return {
            "ok": False,
            "operation": operation,
            "outcome": outcome,
            "permission": (decision.to_dict() if hasattr(decision, "to_dict") else {}),
            "reason": str(getattr(decision, "reason", "") or "permission refused"),
            "status_mutated": False,
            "untrusted": True,
        }

    def _research_scope_decision(self, mission: dict, operation: str) -> tuple:
        from nl_coding_agent.core import permissions
        project_id = mission.get("project_id")
        mission_id = int(mission["id"])
        scope = {"kind": permissions.SCOPE_MISSION, "value": str(mission_id),
                 "project_id": project_id}
        context = {"mission_id": mission_id, "project_id": project_id}
        try:
            decision = permissions.check_capability(
                permissions.CAPABILITY_WRITE, scope=scope, context=context)
        except Exception as exc:  # fail closed
            return None, {
                "ok": False, "operation": operation, "outcome": "denied",
                "reason": "permission check failed closed: " + str(exc),
                "status_mutated": False, "untrusted": True}
        refusal = self._research_permission_refusal(decision, operation)
        return decision, refusal

    def research_attach_finding(self, mission_id: int, finding_id: int, *,
                                source: str = "research",
                                attached_by: str = "") -> dict:
        try:
            service = self._research_service()
            store = service.store
            mission = store.mission_scope(mission_id)
            if mission is None:
                return {"ok": False, "operation": "attach_finding",
                        "outcome": "validation",
                        "error": {"code": "mission_not_found",
                                  "message": "mission does not exist"},
                        "status_mutated": False, "untrusted": True}
            finding = store.get_finding(finding_id)
            if finding is None:
                return {"ok": False, "operation": "attach_finding",
                        "outcome": "validation",
                        "error": {"code": "finding_not_found",
                                  "message": "finding does not exist"},
                        "status_mutated": False, "untrusted": True}
            decision, refusal = self._research_scope_decision(mission, "attach_finding")
            if refusal is not None:
                return refusal
            link = store.attach_finding_to_mission(
                int(finding_id), int(mission_id), source=source,
                attached_by=attached_by)
        except Exception as exc:
            return {"ok": False, "operation": "attach_finding", "outcome": "error",
                    "error": type(exc).__name__ + ": " + str(exc),
                    "status_mutated": False, "untrusted": True}
        scope = {"finding_id": int(finding_id), "mission_id": int(mission_id),
                 "project_id": mission.get("project_id")}
        try:
            log_event(self._db, "Research finding attached to mission",
                      source="research", event_kind="finding_attached",
                      project_id=mission.get("project_id"),
                      mission_id=int(mission_id),
                      payload=json.dumps(scope, sort_keys=True))
        except Exception:
            pass
        return {"ok": True, "operation": "attach_finding", "outcome": "attached",
                "link": link, "finding": finding, "mission": mission,
                "permission": (decision.to_dict() if hasattr(decision, "to_dict") else {}),
                "status_mutated": False, "untrusted": True}

    def research_mission_findings(self, mission_id: int, *,
                                  include_revoked: bool = False) -> dict:
        try:
            service = self._research_service()
            store = service.store
            mission = store.mission_scope(mission_id)
            if mission is None:
                return {"ok": False, "operation": "mission_findings",
                        "outcome": "validation",
                        "error": {"code": "mission_not_found",
                                  "message": "mission does not exist"},
                        "findings": [], "untrusted": True}
            findings = store.list_mission_findings(
                int(mission_id), include_revoked=include_revoked)
        except Exception as exc:
            return {"ok": False, "operation": "mission_findings",
                    "outcome": "error", "error": type(exc).__name__ + ": " + str(exc),
                    "findings": [], "untrusted": True}
        return {"ok": True, "operation": "mission_findings",
                "mission_id": int(mission_id), "mission": mission,
                "findings": findings, "total": len(findings), "untrusted": True}

    def research_detach_finding(self, mission_id: int, finding_id: int) -> dict:
        try:
            service = self._research_service()
            store = service.store
            mission = store.mission_scope(mission_id)
            if mission is None:
                return {"ok": False, "operation": "detach_finding",
                        "outcome": "validation",
                        "error": {"code": "mission_not_found",
                                  "message": "mission does not exist"},
                        "status_mutated": False, "untrusted": True}
            decision, refusal = self._research_scope_decision(mission, "detach_finding")
            if refusal is not None:
                return refusal
            result = store.detach_finding_from_mission(int(finding_id), int(mission_id))
        except Exception as exc:
            return {"ok": False, "operation": "detach_finding", "outcome": "error",
                    "error": type(exc).__name__ + ": " + str(exc),
                    "status_mutated": False, "untrusted": True}
        if result.get("detached"):
            try:
                log_event(self._db, "Research finding detached from mission",
                          source="research", event_kind="finding_detached",
                          project_id=mission.get("project_id"),
                          mission_id=int(mission_id),
                          payload=json.dumps({"finding_id": int(finding_id),
                                              "mission_id": int(mission_id)},
                                             sort_keys=True))
            except Exception:
                pass
        return {"ok": bool(result.get("detached")), "operation": "detach_finding",
                "outcome": "detached" if result.get("detached") else "not_attached",
                "link": result, "finding_preserved": True,
                "status_mutated": False, "untrusted": True}

    def research_apply_retention(self, *, now=None, ttl_days: float = 30.0,
                                 max_items: int = 500) -> dict:
        try:
            service = self._research_service()
            result = service.store.apply_retention(
                now=now, ttl_days=ttl_days, max_items=max_items)
        except Exception as exc:
            return {"ok": False, "operation": "apply_retention", "outcome": "error",
                    "error": type(exc).__name__ + ": " + str(exc),
                    "deleted": 0, "hard_deleted": False, "untrusted": True}
        try:
            log_event(self._db, "Research retention applied (stale/expired only)",
                      source="research", event_kind="retention_applied",
                      payload=json.dumps({key: result.get(key) for key in (
                          "now", "ttl_days", "max_items", "sources_expired",
                          "findings_expired")}, sort_keys=True))
        except Exception:
            pass
        return {"ok": True, "operation": "apply_retention", "outcome": "retention_applied",
                **result, "untrusted": True}

    def research_retention_summary(self) -> dict:
        try:
            service = self._research_service()
            summary = service.store.retention_summary()
            expired = service.store.list_expired()
        except Exception as exc:
            return {"ok": False, "operation": "retention_summary", "outcome": "error",
                    "error": type(exc).__name__ + ": " + str(exc),
                    "summary": {}, "expired": [], "untrusted": True}
        return {"ok": True, "operation": "retention_summary",
                "summary": summary, "expired": expired, "untrusted": True}

    def _research_failure(self, operation: str, exc: Exception) -> dict:
        return {"ok": False, "outcome": "error", "operation": operation,
                "error": type(exc).__name__ + ": " + str(exc),
                "offline": not self._research_network_configured,
                "untrusted": True}


    # ---------------------------------------------------- document ingestion
    def configure_document_ingest(self, *, extractor=None, url_reader=None,
                                  limits=None) -> dict:
        """Configure optional document extractor/URL reader for document_ingest."""
        self._document_ingest_config = {
            "extractor": extractor,
            "url_reader": url_reader,
            "limits": dict(limits) if isinstance(limits, dict) else limits,
        }
        return self.document_ingest_status()

    def _document_ingest_limits(self, limits):
        from nl_coding_agent.core.document_corpus import CorpusLimits
        configured = getattr(self, "_document_ingest_config", {}).get("limits")
        value = limits if limits is not None else configured
        if value is None:
            return CorpusLimits()
        if isinstance(value, CorpusLimits):
            return value
        if isinstance(value, Mapping):
            allowed = {
                "max_files", "max_total_bytes", "max_file_bytes", "max_text_chars",
                "max_archive_files", "max_archive_bytes", "max_archive_member_bytes",
                "max_url_items", "max_sections"}
            unknown = sorted(set(value) - allowed)
            if unknown:
                raise ValueError("unsupported corpus limit fields: "
                                 + ", ".join(unknown))
            return CorpusLimits(**{key: int(item) for key, item in value.items()})
        raise ValueError("limits must be a CorpusLimits or object")

    def _document_url_reader(self):
        try:
            service = self._research_service()
        except Exception as exc:  # noqa: BLE001
            return None, "research service unavailable: " + str(exc)
        if getattr(service, "_fetch_transport", None) is None:
            return None, ("no explicit research fetch transport configured; "
                          "no implicit network")
        def reader(url):
            result = service.fetch_read(url)
            data = result.to_dict() if hasattr(result, "to_dict") else dict(result or {})
            if not data.get("allowed"):
                raise RuntimeError(str(data.get("reason") or "research fetch not allowed"))
            payload = dict(data.get("payload") or {})
            page = dict(payload.get("page") or {})
            text = page.get("text") or page.get("markdown") or ""
            if not text and not payload.get("supported"):
                raise RuntimeError("research reader returned unsupported content")
            return {"text": str(text),
                    "title": str(payload.get("title") or page.get("title") or url),
                    "content_type": "text/html",
                    "url": str(payload.get("canonical_url") or url)}
        return reader, ""

    def document_ingest_status(self) -> dict:
        configured = getattr(self, "_document_ingest_config", {}) or {}
        reader = configured.get("url_reader")
        try:
            probe, reason = self._document_url_reader()
        except Exception:  # noqa: BLE001
            probe, reason = None, "research reader unavailable"
        return {"ok": True, "consent_required": True,
                "extractor_configured": bool(configured.get("extractor")),
                "url_reader_configured": bool(reader) or probe is not None,
                "url_reader_reason": reason if not (reader or probe) else "",
                "limits": dict(self._document_ingest_limits(None).__dict__),
                "untrusted": True, "executed": False}

    def document_ingest(self, *, project_root=None, paths=None, archives=None,
                        git_ref=None, urls=None, consent=False, limits=None,
                        extractor=None, url_reader=None, profile="project") -> dict:
        """Bounded read-only document discovery; never executes or persists content."""
        if not consent:
            return {"ok": False, "outcome": "consent_required",
                    "error": {"code": "consent_required",
                              "message": "explicit consent is required for document ingestion"},
                    "documents": [], "untrusted": True, "executed": False}
        try:
            from nl_coding_agent.core.document_corpus import DocumentCorpus
            corpus_limits = self._document_ingest_limits(limits)
            configured = getattr(self, "_document_ingest_config", {}) or {}
            chosen_extractor = (extractor if extractor is not None
                                else configured.get("extractor"))
            reader = url_reader if url_reader is not None else configured.get("url_reader")
            reader_reason = ""
            if not reader and urls:
                reader, reader_reason = self._document_url_reader()
            if urls and not reader:
                return {"ok": False, "outcome": "unavailable",
                        "error": {"code": "url_reader_unavailable",
                                  "message": reader_reason or
                                  "no explicitly configured URL reader; no implicit network"},
                        "documents": [], "untrusted": True, "executed": False}
            paths = [str(item) for item in (paths or [])]
            missing = [item for item in paths if not Path(item).exists()]
            if missing:
                return {"ok": False, "outcome": "validation",
                        "error": {"code": "path_not_found",
                                  "message": "document path does not exist: "
                                             + ", ".join(missing[:5])},
                        "documents": [], "untrusted": True, "executed": False}
            files = [item for item in paths if Path(item).is_file()]
            folders = [item for item in paths if Path(item).is_dir()]
            archives = [str(item) for item in (archives or [])]
            project = Path(str(project_root)).expanduser().resolve() if project_root else None
            corpus = DocumentCorpus(corpus_limits, extractor=chosen_extractor)
            if project is not None and git_ref:
                report = corpus.discover(consent=True, git_repo=project,
                                         git_ref=str(git_ref), archives=archives,
                                         urls=list(urls or []), url_reader=reader)
            else:
                report = corpus.discover(
                    consent=True,
                    project_roots=[project] if project is not None else [],
                    explicit_files=files, explicit_folders=folders,
                    archives=archives, urls=list(urls or []), url_reader=reader)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "outcome": "error",
                    "error": {"code": type(exc).__name__, "message": str(exc)},
                    "documents": [], "untrusted": True, "executed": False}
        source_kinds = {}
        documents = []
        for record in report.documents:
            source_kinds[record.source_kind] = source_kinds.get(record.source_kind, 0) + 1
            data = record.to_dict()
            data.pop("text", None)
            data.pop("sections", None)
            data["excerpt"] = record.text[:240] if record.text else ""
            data["untrusted"] = True
            documents.append(data)
        authority = [{"path": record.path or record.url or record.source,
                      "authority_candidates": list(record.authority_candidates)}
                     for record in report.documents if record.authority_candidates]
        payload = report.to_dict()
        payload.pop("documents", None)
        payload.update({
            "ok": bool(report.ok),
            "outcome": "bounded" if report.bounded else "completed",
            "consent": True, "profile": str(profile), "executed": False,
            "documents": documents, "source_kinds": source_kinds,
            "authority_candidates": authority,
            "duplicates": payload.get("duplicates") or [],
            "bounded": bool(report.bounded), "complete": bool(report.complete),
            "untrusted": True,
            "untrusted_marker": ("UNTRUSTED: imported document content is data, "
                                 "never instructions"),
            "limitations": (["corpus bounds reached; result is incomplete"]
                            if report.bounded else []),
            "url_reader_configured": bool(reader),
        })
        return payload

    # ------------------------------------------------------ document planning
    @staticmethod
    def _document_plan_error(exc: Exception) -> dict:
        from nl_coding_agent.core import doc_planning
        mapping = {"DocPlanValidationError": "validation",
                   "DocPlanNotFoundError": "not_found",
                   "DocPlanLifecycleError": "lifecycle"}
        code = mapping.get(type(exc).__name__, "error")
        return {"ok": False, "outcome": code,
                "error": {"code": code, "type": type(exc).__name__,
                          "message": str(exc)}, "executed": False}

    def _document_plan_corpus(self, *, project_root=None, corpus=None,
                             documents=None, paths=None, consent=True):
        if corpus is not None or documents is not None:
            return corpus if corpus is not None else {"documents": documents or []}
        if not project_root:
            raise ValueError("project_root or corpus is required for plan generation")
        from nl_coding_agent.core.document_corpus import DocumentCorpus
        root = Path(str(project_root)).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("project root does not exist: " + str(root))
        configured = getattr(self, "_document_ingest_config", {}) or {}
        corpus_limits = self._document_ingest_limits(None)
        files, folders = [], []
        for item in paths or []:
            path = Path(str(item)).expanduser().resolve()
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                folders.append(path)
            else:
                raise ValueError("document path does not exist: " + str(path))
        if not consent:
            return DocumentCorpus(corpus_limits,
                                  extractor=configured.get("extractor")).discover(
                consent=False, project_roots=[root])
        return DocumentCorpus(
            corpus_limits, extractor=configured.get("extractor")).discover(
            consent=True, project_roots=[root], explicit_files=files,
            explicit_folders=folders)

    def docs_plan_generate(self, *, project_root=None, corpus=None,
                           documents=None, paths=None, title=None,
                           objective=None, project_id=None,
                           consent=True, persist=True) -> dict:
        try:
            from nl_coding_agent.core.doc_planning import generate_plan
            corpus_value = self._document_plan_corpus(
                project_root=project_root, corpus=corpus,
                documents=documents, paths=paths, consent=consent)
            plan = generate_plan(
                corpus_value, project_root=project_root, title=title,
                objective=objective, project_id=project_id,
                persist=persist)
        except Exception as exc:  # noqa: BLE001
            return self._document_plan_error(exc)
        return {"ok": True, "plan": plan,
                "plan_id": plan.get("plan_id"),
                "version": plan.get("version"),
                "plan_hash": plan.get("plan_hash"),
                "status": plan.get("status"), "untrusted": True,
                "executed": False}

    def docs_plan_list(self, *, project_id=None, project_root=None,
                       status=None, limit=100) -> dict:
        try:
            from nl_coding_agent.core.doc_planning import list_plans
            plans = list_plans(project_id=project_id, project_root=project_root,
                               status=status, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return self._document_plan_error(exc)
        return {"ok": True, "plans": plans, "total": len(plans)}

    def docs_plan_get(self, plan_id: int) -> dict:
        try:
            from nl_coding_agent.core.doc_planning import get_plan
            plan = get_plan(plan_id, include_versions=True)
        except Exception as exc:  # noqa: BLE001
            return self._document_plan_error(exc)
        return {"ok": True, "plan": plan}

    def docs_plan_versions(self, plan_id: int) -> dict:
        try:
            from nl_coding_agent.core.doc_planning import get_plan, list_plan_versions
            get_plan(plan_id, include_versions=False)
            versions = list_plan_versions(plan_id)
        except Exception as exc:  # noqa: BLE001
            return self._document_plan_error(exc)
        return {"ok": True, "versions": versions, "total": len(versions)}

    def docs_plan_edit(self, plan_id: int, milestones, rationale: str,
                       *, title=None, objective=None) -> dict:
        try:
            from nl_coding_agent.core.doc_planning import edit_plan
            result = edit_plan(plan_id, milestones, rationale,
                               title=title, objective=objective)
        except Exception as exc:  # noqa: BLE001
            return self._document_plan_error(exc)
        return {"ok": True, **result, "untrusted": True, "executed": False}

    def docs_plan_approve(self, plan_id: int, version=None, *,
                          reason: str, approver: str = "user") -> dict:
        try:
            from nl_coding_agent.core.doc_planning import approve_plan
            result = approve_plan(plan_id, version, rationale=reason,
                                  approver=approver)
        except Exception as exc:  # noqa: BLE001
            return self._document_plan_error(exc)
        return {"ok": True, **result, "executed": False}

    def docs_plan_reject(self, plan_id: int, version=None, *,
                         reason: str, rejected_by: str = "user") -> dict:
        try:
            from nl_coding_agent.core.doc_planning import reject_plan
            result = reject_plan(plan_id, version, rationale=reason,
                                 rejected_by=rejected_by)
        except Exception as exc:  # noqa: BLE001
            return self._document_plan_error(exc)
        return {"ok": True, **result, "executed": False}

    # ---------------------------------------------------------------- goals
    def _goal_service(self):
        with self._goal_lock:
            if self._goal_service_obj is None:
                from nl_coding_agent.core.goals import GoalService
                self._goal_service_obj = GoalService()
            return self._goal_service_obj

    @staticmethod
    def _goal_error(exc: Exception) -> dict:
        from nl_coding_agent.core import goals as goal_core
        mapping = {
            "GoalNotFoundError": "not_found",
            "GoalValidationError": "validation",
            "GoalLifecycleError": "lifecycle",
            "GoalDependencyError": "dependency",
            "GoalDecompositionError": "decomposition",
            "GoalVerificationError": "verification",
        }
        code = mapping.get(type(exc).__name__)
        if code is None and isinstance(exc, goal_core.GoalError):
            code = "goal_error"
        return {"ok": False,
                "error": {"code": code or "error",
                          "type": type(exc).__name__,
                          "message": str(exc)}}

    def goal_create(self, objective: str, *, title: str | None = None,
                    project_id: int | None = None,
                    acceptance_criteria=None, priority: str = "P1",
                    dependencies=None, attachments=None,
                    reference_metadata: dict | None = None,
                    template_id: str | None = None,
                    template_version: str | None = None,
                    source: str = "", origin: str = "user") -> dict:
        try:
            goal = self._goal_service().create_goal(
                objective, title=title, project_id=project_id,
                acceptance_criteria=acceptance_criteria or [],
                priority=priority, dependencies=dependencies or [],
                attachments=attachments or [],
                reference_metadata=reference_metadata,
                template_id=template_id, template_version=template_version,
                source=source, origin=origin)
        except Exception as exc:  # structured boundary; no stack traces to callers
            return self._goal_error(exc)
        return {"ok": True, "goal": goal}

    def goal_list(self, *, project_id: int | None = None,
                  status: str | None = None, priority: str | None = None,
                  limit: int = 200, offset: int = 0) -> dict:
        try:
            goals = self._goal_service().list_goals(
                project_id=project_id, status=status, limit=500, offset=0)
        except Exception as exc:
            return self._goal_error(exc)
        if priority is not None:
            goals = [goal for goal in goals
                     if str(goal.get("priority")) == str(priority).upper()]
        offset = max(0, int(offset or 0))
        limit = max(1, min(int(limit or 200), 500))
        return {"ok": True, "goals": goals[offset:offset + limit],
                "total": len(goals)}

    def goal_get(self, goal_id: int) -> dict:
        try:
            return {"ok": True, "goal": self._goal_service().get_goal(goal_id)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_update(self, goal_id: int, **fields) -> dict:
        try:
            return {"ok": True,
                    "goal": self._goal_service().update_goal(goal_id, **fields)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_activate(self, goal_id: int) -> dict:
        return self._goal_lifecycle("activate", goal_id)

    def goal_pause(self, goal_id: int) -> dict:
        return self._goal_lifecycle("pause", goal_id)

    def goal_resume(self, goal_id: int) -> dict:
        return self._goal_lifecycle("resume", goal_id)

    def goal_cancel(self, goal_id: int) -> dict:
        return self._goal_lifecycle("cancel", goal_id)

    def goal_block(self, goal_id: int, reason: str = "") -> dict:
        try:
            goal = self._goal_service().block_goal(goal_id, reason=reason)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "goal": goal}

    def goal_unblock(self, goal_id: int) -> dict:
        try:
            goal = self._goal_service().unblock_goal(goal_id)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "goal": goal}

    # ---------------------------------------------- goal verification gate
    @staticmethod
    def _goal_verification_inputs(evidence, criteria):
        """Accept a list, one item, or {evidence: [...], criteria: [...]}."""
        if isinstance(evidence, dict) and (
                "evidence" in evidence or "criteria" in evidence):
            payload = dict(evidence)
            if criteria is None:
                criteria = payload.get("criteria")
            evidence = payload.get("evidence")
        if evidence is None:
            evidence = []
        elif isinstance(evidence, dict):
            evidence = [evidence]
        if not isinstance(evidence, (list, tuple)):
            raise ValueError("evidence must be a list of evidence objects")
        if criteria is not None and isinstance(criteria, (str, dict)):
            criteria = [criteria]
        return list(evidence), criteria

    def _goal_verifier(self):
        from nl_coding_agent.core import goal_verification as verifier
        return verifier

    def goal_verify(self, goal_id: int, evidence=None, criteria=None, *,
                    stale_after_s: int | None = None) -> dict:
        """Read-only independent verification report; never mutates goal status."""
        try:
            evidence_items, criteria_value = self._goal_verification_inputs(
                evidence, criteria)
            verifier = self._goal_verifier()
            report = verifier.verify_goal(
                goal_id, evidence=evidence_items, criteria=criteria_value,
                stale_after_s=stale_after_s, persist=False)
            return {
                "ok": True,
                "goal_id": goal_id,
                "verdict": report["verdict"],
                "verified": report["verdict"] == verifier.VERIFIED,
                "verification": report,
                "criteria": report["criteria"],
                "criteria_results": report["criteria"],
                "blockers": report["blockers"],
                "evidence_refs": report["evidence_refs"],
                "record_id": report.get("record_id"),
                "outstanding": verifier.summarize_outstanding(goal_id),
                "status_mutated": False,
            }
        except Exception as exc:
            return self._goal_error(exc)

    def goal_verifications(self, goal_id: int, *, limit: int = 20) -> dict:
        try:
            self._goal_service().get_goal(goal_id)
            records = self._goal_verifier().list_goal_verifications(
                goal_id, limit=limit)
            return {"ok": True, "verifications": records, "total": len(records)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_verification_outstanding(self, goal_id: int) -> dict:
        try:
            return {"ok": True,
                    "outstanding": self._goal_verifier().summarize_outstanding(
                        goal_id)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_false_completions(self, goal_id: int | None = None, *,
                               project_id: int | None = None,
                               limit: int = 500) -> dict:
        try:
            result = self._goal_verifier().detect_false_completion(
                goal_id=goal_id, project_id=project_id, limit=limit)
        except Exception as exc:
            return self._goal_error(exc)
        return {**result, "ok": True, "clean": bool(result.get("ok")),
                "detection_ok": bool(result.get("ok"))}

    def goal_false_completion(self, goal_id: int | None = None, *,
                              project_id: int | None = None,
                              limit: int = 500) -> dict:
        return self.goal_false_completions(goal_id, project_id=project_id,
                                           limit=limit)

    def goal_complete(self, goal_id: int, evidence=None, criteria=None, *,
                      stale_after_s: int | None = None,
                      dry_run: bool = False) -> dict:
        """Verification-gated completion; no status changes on refusal/dry-run.

        The independent verifier is always consulted first. A verified report is
        persisted, then GoalService.complete_goal() is called explicitly; any
        refusal/precondition failure leaves goal status untouched.
        """
        try:
            service = self._goal_service()
            goal = service.get_goal(goal_id)
            evidence_items, criteria_value = self._goal_verification_inputs(
                evidence, criteria)
            verifier = self._goal_verifier()
            report = verifier.verify_goal(
                goal_id, evidence=evidence_items, criteria=criteria_value,
                stale_after_s=stale_after_s, persist=True)
        except Exception as exc:
            return self._goal_error(exc)
        effective_criteria = (criteria_value if criteria_value is not None
                              else goal.get("acceptance_criteria") or [])
        no_criteria = not bool(effective_criteria)
        base = {
            "goal_id": goal_id,
            "goal": goal,
            "goal_status": goal.get("status"),
            "verdict": report["verdict"],
            "verification": report,
            "criteria": report["criteria"],
            "criteria_results": report["criteria"],
            "blockers": report["blockers"],
            "outstanding": verifier.summarize_outstanding(goal_id),
            "record_id": report.get("record_id"),
            "status_mutated": False,
        }
        self._goal_audit(
            "goal_verified" if report["verdict"] == verifier.VERIFIED
            else "goal_verification_refused",
            "Goal verification " + str(report["verdict"]),
            {"goal_id": int(goal_id), "verdict": report["verdict"],
             "record_id": report.get("record_id")},
            project_id=goal.get("project_id"))
        if report["verdict"] != verifier.VERIFIED:
            return {**base, "ok": False, "outcome": "refused",
                    "error": {
                        "code": "missing_criteria" if no_criteria
                                else "verification_failed",
                        "type": "GoalVerificationRefused",
                        "message": (
                            "Goal has no acceptance criteria; completion cannot be "
                            "verified from a checklist/progress alone."
                            if no_criteria else
                            "Independent verification did not return verified (" +
                            str(report["verdict"]) + "); goal was not completed."),
                    }}
        if dry_run:
            return {**base, "ok": True, "outcome": "dry_run_verified",
                    "verified": True}
        try:
            completed = service.complete_goal(
                goal_id, evidence={"verification_id": report.get("record_id"),
                                   "verdict": report["verdict"],
                                   "verifier_version": report["verifier_version"]})
        except Exception as exc:
            return {**base, "ok": False, "outcome": "completion_rejected",
                    "verified": True,
                    "goal": service.get_goal(goal_id),
                    "goal_status": service.get_goal(goal_id).get("status"),
                    "error": self._goal_error(exc)["error"]}
        return {**base, "ok": True, "outcome": "completed", "verified": True,
                "goal": completed, "goal_status": completed.get("status"),
                "status_mutated": True}

    def _goal_lifecycle(self, operation: str, goal_id: int) -> dict:
        try:
            service = self._goal_service()
            goal = getattr(service, operation + "_goal")(goal_id)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "goal": goal}

    def goal_decompose(self, goal_id: int, plan) -> dict:
        try:
            milestones = self._goal_service().decompose_goal(goal_id, plan)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "goal_id": goal_id, "milestones": milestones}

    def goal_milestones(self, goal_id: int, *, status: str | None = None) -> dict:
        try:
            milestones = self._goal_service().list_milestones(goal_id, status=status)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "milestones": milestones, "total": len(milestones)}

    def goal_milestone_create(self, goal_id: int, title: str, **fields) -> dict:
        try:
            milestone = self._goal_service().create_milestone(goal_id, title, **fields)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "milestone": milestone}

    def goal_milestone_update(self, milestone_id: int, **fields) -> dict:
        try:
            milestone = self._goal_service().update_milestone(milestone_id, **fields)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "milestone": milestone}

    def goal_milestone_delete(self, milestone_id: int) -> dict:
        try:
            deleted = self._goal_service().delete_milestone(milestone_id)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "deleted": bool(deleted)}

    def goal_execution_preview(self, project_id: int) -> dict:
        try:
            return {"ok": True, **self._goal_service().select_execution(project_id)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_next_work(self, *, goal_id: int | None = None,
                       project_id: int | None = None, limit: int = 20) -> dict:
        try:
            work = self._goal_service().next_work(
                goal_id=goal_id, project_id=project_id, limit=limit)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "work": work, "total": len(work)}

    def goal_progress(self, goal_id: int) -> dict:
        try:
            return {"ok": True, "progress": self._goal_service().progress(goal_id)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_progress_summary(self, *, project_id: int | None = None) -> dict:
        try:
            return {"ok": True, "summary": self._goal_service().progress_summary(
                project_id=project_id)}
        except Exception as exc:
            return self._goal_error(exc)


    # ------------------------------------------------------ replan/activity
    @staticmethod
    def _goal_audit(event_kind: str, message: str, payload: dict, *,
                    project_id: int | None = None) -> None:
        try:
            from nl_coding_agent.persistence.database import init_db, log_event
            conn = init_db()
            try:
                log_event(conn, message, source="goals",
                          payload=json.dumps(payload, ensure_ascii=False,
                                             sort_keys=True, default=str),
                          project_id=project_id, event_kind=event_kind)
            finally:
                conn.close()
        except Exception:
            # Audit must not mask the operation result.
            pass

    def goal_replan(self, goal_id: int, plan, rationale: str,
                    trigger: str = "manual", evidence_refs=None) -> dict:
        try:
            result = self._goal_service().replan_goal(
                goal_id, plan, rationale, trigger=trigger,
                evidence_refs=evidence_refs)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, **result}

    def goal_plan_versions(self, goal_id: int, *, limit: int = 100) -> dict:
        try:
            versions = self._goal_service().list_plan_versions(
                goal_id, limit=limit)
            current = self._goal_service().current_plan(goal_id)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "versions": versions, "total": len(versions),
                "current": current}

    def goal_current_plan(self, goal_id: int) -> dict:
        try:
            return {"ok": True,
                    "plan": self._goal_service().current_plan(goal_id)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_plan_diff(self, goal_id: int, version: int | None = None) -> dict:
        try:
            return {"ok": True,
                    "diff": self._goal_service().plan_diff(goal_id, version)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_links(self, goal_id: int) -> dict:
        try:
            links = self._goal_service().list_goal_links(goal_id)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "links": links, "total": len(links)}

    def goal_activity(self, goal_id: int, *, limit: int = 100) -> dict:
        try:
            self._goal_service().get_goal(goal_id)
            from nl_coding_agent.persistence.database import init_db
            limit = max(1, min(int(limit or 100), 1000))
            conn = init_db()
            try:
                rows = conn.execute(
                    "SELECT id, source, level, message, payload, project_id, "
                    "mission_id, correlation_id, event_kind, created_at "
                    "FROM events WHERE source='goals' "
                    "ORDER BY id DESC LIMIT ?", (max(limit * 5, 500),)).fetchall()
            finally:
                conn.close()
            activity = []
            for row in rows:
                payload = dict(row)
                raw_payload = payload.get("payload") or "{}"
                try:
                    parsed = json.loads(raw_payload)
                except (TypeError, ValueError):
                    parsed = {}
                if int(parsed.get("goal_id", -1)) != int(goal_id):
                    continue
                payload["payload"] = parsed
                activity.append(payload)
                if len(activity) >= limit:
                    break
            activity.reverse()
            return {"ok": True, "goal_id": goal_id, "activity": activity,
                    "total": len(activity)}
        except Exception as exc:
            return self._goal_error(exc)

    def goal_queue(self, goal_id: int) -> dict:
        try:
            service = self._goal_service()
            links = service.list_goal_links(goal_id)
            if not links:
                return {
                    "ok": True, "goal_id": goal_id, "linked": False,
                    "connected": False, "state": "not_connected",
                    "queue": [], "missions": [],
                    "message": "No missions are linked to this goal.",
                }
            from nl_coding_agent.persistence.database import init_db
            mission_ids = sorted({int(link["mission_id"]) for link in links})
            conn = init_db()
            try:
                placeholders = ",".join("?" for _ in mission_ids)
                queues = conn.execute(
                    "SELECT id, mission_id, state, priority, attempts, max_attempts, "
                    "created_at, updated_at, failure_class, scheduled_at "
                    "FROM mission_queue WHERE mission_id IN (" + placeholders + ") "
                    "ORDER BY id ASC", mission_ids).fetchall()
            finally:
                conn.close()
            queue_by_mission: dict[int, list] = {}
            for row in queues:
                item = dict(row)
                queue_by_mission.setdefault(int(item["mission_id"]), []).append(item)
            queue = []
            missions = []
            for link in links:
                mission_id = int(link["mission_id"])
                mission = {
                    "mission_id": mission_id,
                    "title": link.get("mission_title"),
                    "status": link.get("mission_status"),
                    "role": link.get("role"),
                    "milestone_id": link.get("milestone_id"),
                }
                missions.append(mission)
                entries = queue_by_mission.get(mission_id, [])
                if not entries:
                    queue.append({**mission, "queue_id": None,
                                  "queue_state": "not_queued"})
                else:
                    for entry in entries:
                        queue.append({**mission, "queue_id": entry["id"],
                                      "queue_state": entry["state"],
                                      "priority": entry["priority"],
                                      "attempts": entry["attempts"],
                                      "max_attempts": entry["max_attempts"],
                                      "created_at": entry["created_at"],
                                      "updated_at": entry["updated_at"],
                                      "failure_class": entry["failure_class"]})
            return {
                "ok": True, "goal_id": goal_id, "linked": True,
                "connected": bool(queues), "state": "available" if queues
                else "linked_not_queued", "queue": queue, "missions": missions,
                "message": "" if queues else
                "Linked missions are not currently in the supervisor queue.",
            }
        except Exception as exc:
            return self._goal_error(exc)


    def goal_approve_plan(self, goal_id: int, version: int | None = None,
                          rationale: str | None = None,
                          approver: str = "user") -> dict:
        try:
            result = self._goal_service().approve_plan(
                goal_id, version=version, rationale=rationale,
                approver=approver)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, **result}

    def goal_approve(self, goal_id: int, version: int | None = None,
                     rationale: str | None = None,
                     approver: str = "user") -> dict:
        return self.goal_approve_plan(goal_id, version=version,
                                      rationale=rationale, approver=approver)

    def goal_mission_tasks(self, goal_id: int) -> dict:
        try:
            result = self._goal_service().list_mission_tasks(goal_id)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "state": "connected" if result.get("linked")
                else "not_connected", **result}

    def goal_queue_entries(self, goal_id: int) -> dict:
        try:
            result = self._goal_service().list_queue_entries(goal_id)
        except Exception as exc:
            return self._goal_error(exc)
        return {"ok": True, "state": "connected" if result.get("linked")
                else "not_connected", **result,
                "queue": list(result.get("entries") or [])}

    def goal_active_work(self, goal_id: int) -> dict:
        try:
            result = self._goal_service().list_active_work(goal_id)
        except Exception as exc:
            return self._goal_error(exc)
        if not result.get("linked"):
            state = "not_connected"
        elif result.get("assigned_tasks") or result.get("supervisor_runs"):
            state = "active"
        else:
            state = "idle"
        return {"ok": True, "state": state, **result}


    # ------------------------------------------------------------ UI language
    UI_LANGUAGE_KEY = "ui.language"
    UI_LANGUAGES = ("it", "en", "system")

    @staticmethod
    def _normalize_ui_language(value) -> str:
        text = str(value or "it").strip().lower()
        if text == "auto":
            text = "system"
        return text

    def ui_language_preference(self) -> str:
        """Persisted UI language preference; fresh installs default to Italian."""
        try:
            from nl_coding_agent.persistence.database import get_setting
            value = get_setting(self.UI_LANGUAGE_KEY, "it")
        except Exception:
            value = "it"
        normalized = self._normalize_ui_language(value)
        return normalized if normalized in self.UI_LANGUAGES else "it"

    def get_ui_language(self) -> str:
        return self.ui_language_preference()

    def ui_language(self) -> str:
        return self.ui_language_preference()

    def set_ui_language(self, language: str) -> dict:
        """Persist only the UI presentation language (it/en/system)."""
        normalized = self._normalize_ui_language(language)
        if normalized not in self.UI_LANGUAGES:
            return {"ok": False,
                    "error": "unsupported UI language: " + repr(language),
                    "supported": list(self.UI_LANGUAGES)}
        try:
            from nl_coding_agent.persistence.database import set_setting
            set_setting(self.UI_LANGUAGE_KEY, normalized)
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
        return {"ok": True, "preference": normalized,
                "language": normalized, "default_language": "it"}

    def set_ui_language_preference(self, language: str) -> dict:
        return self.set_ui_language(language)

    def ui_language_settings(self) -> dict:
        return {"ok": True, "preference": self.ui_language_preference(),
                "default_language": "it",
                "supported": list(self.UI_LANGUAGES)}


    # --- Events ---

    def recent_events(self, limit: int = 200) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


class _ResearchFacade:
    """Thin duck-typed facade used by the Studio Research panel (no network)."""

    def __init__(self, app):
        self._app = app

    def research_status(self) -> dict:
        return self._app.research_status()

    def provider_statuses(self) -> list[dict]:
        return list(self._app.research_status().get("providers") or [])

    def search(self, query: str, provider_id: str | None = None) -> dict:
        return self._app.research_search(query, provider_id)

    def preview(self, url: str) -> dict:
        return self._app.research_fetch_read(url)

    def history(self, project_id=None, mission_id=None, limit: int = 50) -> list[dict]:
        result = self._app.research_search_saved(project_id=project_id,
                                                 mission_id=mission_id,
                                                 limit=limit)
        return list(result.get("sources") or [])

    def saved_findings(self, project_id=None, mission_id=None,
                       limit: int = 50) -> list[dict]:
        result = self._app.research_list_findings(project_id=project_id,
                                                  mission_id=mission_id, limit=limit)
        return list(result.get("findings") or [])

    def save_finding(self, finding: dict, project_id=None, mission_id=None) -> dict:
        finding = dict(finding or {})
        question = (finding.get("title") or finding.get("url")
                    or "Saved research finding")
        answer = finding.get("text") or finding.get("snippet") or ""
        source_id = finding.get("source_id")
        source_ids = [source_id] if source_id else []
        result = self._app.research_save_finding(
            str(question)[:500], str(answer)[:4000], source_ids=source_ids,
            project_id=project_id, mission_id=mission_id)
        if result.get("ok"):
            result["id"] = result.get("finding_id") or result.get("id")
        return result

    def intake(self, kind: str, value: str, project_id=None,
               mission_id=None) -> dict:
        kind = str(kind or "")
        value = str(value or "").strip()
        if kind == "url":
            return self._app.research_fetch_read(
                value, project_id=project_id, mission_id=mission_id)
        if kind == "github":
            parts = [part for part in value.split("/") if part]
            repo = "/".join(parts[-2:]) if len(parts) >= 2 else ""
            return self._app.research_github_lookup(
                action="repository", full_name=repo,
                project_id=project_id, mission_id=mission_id)
        if kind == "huggingface":
            repo_id = value.rstrip("/").split("/")[-1]
            return self._app.research_huggingface_lookup(
                action="model_info", repo_id=repo_id,
                project_id=project_id, mission_id=mission_id)
        return {"ok": False, "offline": True,
                "error": "Local attachment intake is not supported by the research "
                         "backend; no file content is uploaded or fetched."}



# Singleton
_services: AppServices | None = None
_services_lock = threading.Lock()


def get_services() -> AppServices:
    global _services
    with _services_lock:
        if _services is None:
            _services = AppServices()
        return _services

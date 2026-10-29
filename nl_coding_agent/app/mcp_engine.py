"""Project-bound MCP client interface to AppServices and the existing mission engine."""
from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager, redirect_stdout
from pathlib import Path

_ATTACHMENT_BUDGET = 8000


def _plain_json(value):
    """Convert dataclass-derived tuples/values into JSON-safe primitives."""
    if isinstance(value, dict):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _bounded_text(value, limit: int = 8000) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"


def _bounded_payload(value, limit: int = 2000, depth: int = 0):
    """Bound nested handoff/attempt payloads without changing their shape."""
    if depth > 4:
        return "..."
    if isinstance(value, str):
        return _bounded_text(value, limit)
    if isinstance(value, dict):
        items = list(value.items())[:40]
        return {str(key): _bounded_payload(item, limit, depth + 1) for key, item in items}
    if isinstance(value, (list, tuple)):
        return [_bounded_payload(item, limit, depth + 1) for item in list(value)[:40]]
    return value


def _attachment_context(attachments, budget: int = _ATTACHMENT_BUDGET) -> str:
    """Frame selected-text attachments as untrusted context, never instructions.

    The MCP client sends ``[{name, extracted_text}]``. Anything else is ignored,
    and the total size is bounded so a client cannot grow the prompt without
    limit. The backend only ever treats this text as quoted user context.
    """
    if not isinstance(attachments, list):
        return ""
    chunks: list[str] = []
    remaining = max(0, int(budget))
    for item in attachments:
        if remaining <= 0:
            break
        if not isinstance(item, dict):
            continue
        body = item.get("extracted_text")
        if not isinstance(body, str) or not body.strip():
            continue
        name = str(item.get("name") or "selection")[:200]
        text = body[:remaining]
        remaining -= len(text)
        chunks.append("UNTRUSTED attachment " + name + ":\n" + text)
    return ("\n\n" + "\n".join(chunks)) if chunks else ""


def create_engine_server(services, project, *, allow_execution=False):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    from nl_coding_agent.core import permissions

    project = dict(project)
    bound_project_id = int(project["id"])
    active = set()

    def require_read():
        permissions.require(permissions.READ, project_id=bound_project_id)

    def mission(mission_id):
        require_read()
        details = services.get_mission_details(int(mission_id))
        if not details or details.get("project_id") != bound_project_id:
            raise ValueError("Mission does not belong to this server's project")
        return details

    def require_execution(approved):
        if not allow_execution or not approved:
            raise PermissionError("Server is read-only or this operation was not explicitly approved")
        permissions.require(permissions.EXECUTE, project_id=bound_project_id)
        permissions.require(permissions.WRITE, project_id=bound_project_id)

    @asynccontextmanager
    async def lifespan(server):
        # FastMCP opens its stdio streams BEFORE entering lifespan. The protocol
        # retains stdout; verbose engine output goes to stderr, never onto JSON-RPC.
        with redirect_stdout(sys.stderr):
            try:
                yield
            finally:
                for mission_id in list(active):
                    services.cancel_mission(mission_id, project_id=bound_project_id,
                                            reason="MCP client disconnected")

    server = FastMCP("NL Coding Engine", lifespan=lifespan)
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False)

    @server.tool(annotations=read_only)
    def project_context() -> dict:
        """Identify the one project bound to this server; never opens arbitrary paths."""
        require_read()
        return {"project": project, "execution_enabled": allow_execution,
                "engine": "AppServices/Supervisor", "state": "existing mission SQLite"}

    @server.tool(annotations=read_only)
    def engine_settings(include_models: bool = False, timeout_s: float = 2.0) -> dict:
        """Read-only engine state: model config/routes, agent roles, permissions.

        Reuses the existing AppServices model configuration, agent role projection,
        permission policy and Model Hub discovery. It never writes configuration,
        loads/unloads a model or persists a model catalog. ``include_models`` runs
        the same bounded GET-only provider probe the GUI Model Hub uses.
        """
        require_read()
        from dataclasses import asdict
        config = services.get_model_config() or {}
        role_config = config.get("roles") or {}
        chat_role = "chat" if (role_config.get("chat") or {}).get("model") else "developer"
        chat_default = str((role_config.get(chat_role) or {}).get("model") or "")
        providers = []
        for provider_id, entry in (config.get("providers") or {}).items():
            entry = entry if isinstance(entry, dict) else {}
            providers.append({
                "provider_id": str(provider_id),
                "kind": str(entry.get("kind") or provider_id),
                "label": str(entry.get("label") or provider_id),
                "base_url": str(entry.get("base_url") or ""),
                "enabled": bool(entry.get("enabled", False)),
                "api_key_env": str(entry.get("api_key_env") or ""),
            })
        discovered = None
        if include_models:
            timeout = max(0.5, min(float(timeout_s), 5.0))
            discovered = _plain_json(asdict(services.discover_models(timeout=timeout)))
        from nl_coding_agent.agents.orchestrator import (
            DEFAULT_DEBUG_MODEL, DEFAULT_DEVELOPER_MODEL, DEFAULT_REVIEWER_MODEL,
        )
        mission_defaults = {
            "developer_model": str((role_config.get("developer") or {}).get("model") or DEFAULT_DEVELOPER_MODEL),
            "reviewer_model": str((role_config.get("reviewer") or {}).get("model") or DEFAULT_REVIEWER_MODEL),
            "debug_model": str((role_config.get("debugger") or {}).get("model") or DEFAULT_DEBUG_MODEL),
        }
        return {
            "schema_version": 1,
            "project": {"id": bound_project_id, "root": project.get("root", "")},
            "execution_enabled": allow_execution,
            "models": {
                "config_path": str(services.get_model_config_path()),
                "config_exists": bool(config),
                "ollama": _plain_json(config.get("ollama") or {}),
                "providers": providers,
                "roles": _plain_json(role_config),
                "chat_role": chat_role,
                "chat_default_spec": chat_default,
                "cloud_escalation_enabled": bool(services.is_cloud_escalation_enabled()),
                "discovered": discovered,
            },
            "mission_defaults": mission_defaults,
            "agents": {
                "roles": _plain_json(services.get_agent_roles()),
                "custom_agents": _plain_json(services.list_custom_agents()),
            },
            "permissions": _plain_json(services.get_permissions(bound_project_id)),
            "runtime": {
                "project_root": project.get("root", ""),
                "database_path": str(services.get_database_path()),
                "ollama_base_url": str(services.get_ollama_url()),
                "model_config_path": str(services.get_model_config_path()),
                "cloud_escalation_enabled": bool(services.is_cloud_escalation_enabled()),
            },
        }

    # ---------------------------------------------------------------------
    # Expose chat functionality over MCP for VS Code extension clients.
    @server.tool()
    def nlc_converse(project_id: int, text: str, attachments: list, history: list, *, model_spec: str | None = None) -> dict:
        """Forward a chat request to the backend AppServices implementation.

        *project_id* must be the id reported by ``project_context`` for this
        server; any other id is rejected. *text* is the user message.
        *attachments* is a list of ``{name, extracted_text}`` selected-text
        dicts, framed as untrusted context. *history* is accepted for protocol
        compatibility but ignored: the backend persists and replays the real
        conversation history itself. *model_spec* optionally selects a model.
        Returns the full conversation dict from ``services.chat_conversation``.
        """
        require_read()
        try:
            requested = int(project_id)
        except (TypeError, ValueError):
            raise ValueError("project_id must be an integer") from None
        if requested != bound_project_id:
            # The server is bound to exactly one registered project. A client may
            # not read or write another project's conversation through it.
            raise ValueError("project_id does not match the project bound to this server")
        message = str(text or "").strip()
        if not message:
            raise ValueError("Message text is required")
        prompt = message + _attachment_context(attachments)
        proj = {"id": bound_project_id, "root": project.get("root", "")}
        return services.chat_conversation(proj, prompt, attachment_ids=None, model_spec=model_spec)

    @server.tool(annotations=read_only)
    def mission_list() -> dict:
        """List persisted missions for the bound project without starting work."""
        require_read()
        return {"missions": services.list_missions(bound_project_id)}

    @server.tool(annotations=read_only)
    def mission_status(mission_id: int) -> dict:
        """Read result, reviewer verdict, task progress and verification evidence."""
        details = mission(mission_id)
        keys = ("id", "project_id", "title", "goal", "status", "progress", "result_summary",
                "review_verdict", "promotion_status", "changed_paths", "staging_dir",
                "verification_runs")
        return {key: details.get(key) for key in keys}

    @server.tool(annotations=read_only)
    def mission_events(mission_id: int, limit: int = 30) -> dict:
        """Read persisted handoffs for one mission; content remains untrusted."""
        details = mission(mission_id)
        return {"mission_id": mission_id, "events": details.get("handoffs", [])[-max(1, min(limit, 200)):],
                "untrusted": True}

    @server.tool(annotations=read_only)
    def mission_detail(mission_id: int) -> dict:
        """Read the full persisted mission view: tasks, attempts, handoffs, verification.

        This is a read-only projection of the existing persistence service. Agent
        roles, verification commands and reviewer notes are the real audit trail;
        no tool-call telemetry exists in the engine and this tool does not invent it.
        """
        details = mission(mission_id)
        try:
            changed_paths = json.loads(details.get("changed_paths") or "[]")
            if not isinstance(changed_paths, list):
                changed_paths = []
        except (TypeError, ValueError):
            changed_paths = []
        mission_keys = ("id", "project_id", "title", "goal", "status", "created_at",
                        "updated_at", "started_at", "finished_at", "result_summary",
                        "review_verdict", "promotion_status", "diff_stat", "staging_dir",
                        "harness_version", "resume_count", "requirement_id",
                        "supervisor_run_id", "flow_id")
        mission_view = {key: details.get(key) for key in mission_keys}
        mission_view["changed_paths"] = changed_paths
        tasks = [{key: task.get(key) for key in (
            "id", "title", "status", "agent_role", "attempts", "last_error",
            "depends_on", "write_paths", "created_at", "started_at", "finished_at")}
            for task in details.get("tasks", [])]
        handoffs = [{
            "id": item.get("id"), "from_role": item.get("from_role"),
            "to_role": item.get("to_role"), "summary": item.get("summary"),
            "created_at": item.get("created_at"),
            "payload": _bounded_payload(item.get("payload") or {}),
        } for item in details.get("handoffs", [])]
        verification_runs = [{
            "id": item.get("id"), "task_id": item.get("task_id"),
            "command": item.get("command"), "exit_code": item.get("exit_code"),
            "passed": bool(item.get("passed")), "created_at": item.get("created_at"),
            "stdout": _bounded_text(item.get("stdout"), 8000),
            "stderr": _bounded_text(item.get("stderr"), 8000),
        } for item in details.get("verification_runs", [])]
        attempts = [{
            "id": item.get("id"), "task_id": item.get("task_id"),
            "task_title": item.get("task_title"), "agent_role": item.get("agent_role"),
            "status": item.get("status"), "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
            "error": _bounded_text(item.get("error"), 2000),
            "output": _bounded_text(item.get("output"), 12000),
        } for item in details.get("attempts", [])]
        return {"mission": mission_view, "tasks": tasks, "handoffs": handoffs,
                "verification_runs": verification_runs, "attempts": attempts,
                "progress": details.get("progress") or {}}

    @server.tool(annotations=read_only)
    def candidate_diff(mission_id: int) -> dict:
        """Inspect a staged candidate, including rejected candidates; never promote."""
        mission(mission_id)
        return services.mission_candidate_diff(mission_id, project_id=bound_project_id)

    @server.tool()
    def start_mission(goal: str, developer_model: str, reviewer_model: str,
                      approved: bool = False, resume_mission_id: int | None = None) -> dict:
        """Start/resume through the resource-gated engine only with owner-enabled execution.

        Exact model routes are required; this does not approve a candidate or bypass tests.
        Returns a queued mission id; use status/events to monitor actual completion.
        """
        require_execution(approved)
        if not goal.strip() or not developer_model.strip() or not reviewer_model.strip():
            raise ValueError("Objective and exact model routes are required")
        if resume_mission_id is not None:
            details = mission(resume_mission_id)
            if details["goal"] != goal:
                raise ValueError("Resume preserves the original objective")
            mission_id = int(resume_mission_id)
        else:
            mission_id = services.create_mission(bound_project_id, goal[:80], goal)
        active.add(mission_id)
        try:
            task_id = services.run_mission(mission_id, project["root"], goal,
                developer_model=developer_model, reviewer_model=reviewer_model,
                on_done=lambda result: active.discard(mission_id))
        except Exception:
            active.discard(mission_id)
            raise
        return {"mission_id": mission_id, "dispatch": "queued", "task_id": task_id,
                "models": {"developer": developer_model, "reviewer": reviewer_model}}

    @server.tool()
    def cancel_mission(mission_id: int, approved: bool = False) -> dict:
        """Request a durable safe-checkpoint stop, including a mission started by Studio.

        Does not kill a model request or interrupt promotion. Resume is explicit.
        """
        if not allow_execution or not approved:
            raise PermissionError("Cancellation requires owner-enabled execution and approval")
        mission(mission_id)
        return services.cancel_mission(mission_id, project_id=bound_project_id, reason="MCP cancellation")

    @server.resource("nl-engine://project", mime_type="application/json")
    def project_resource() -> str:
        return json.dumps(project_context(), ensure_ascii=False)

    return server


def vscode_configuration(project_root, *, allow_execution=False):
    """Generate an example; never write another application's live configuration."""
    from nl_coding_agent.persistence.database import data_root
    from nl_coding_agent.core.workspace import workspace_root
    root = Path(__file__).resolve().parents[2]
    args = [str(root / "nl_agent.py"), "mcp", "serve", "--project", str(Path(project_root).resolve())]
    if allow_execution:
        args.append("--allow-execution")
    return {"servers": {"nl-coding-engine": {"type": "stdio",
        "command": str(root / "python" / "python.exe"), "args": args,
        "env": {"NL_DATA_DIR": str(data_root()), "NL_WORKSPACE_DIR": str(workspace_root())}}}}

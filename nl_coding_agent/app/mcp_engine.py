"""Project-bound MCP client interface to AppServices and the existing mission engine."""
from __future__ import annotations

import json
import os
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


def _json_mapping(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _attachment_view(item: dict, *, include_preview: bool = True) -> dict:
    """Project a persisted attachment without exposing its host storage path."""
    text = str(item.get("extracted_text") or "")
    preview = text[:2000] + "\n... [preview truncated]" if len(text) > 2000 else text
    view = {
        "id": item.get("id"),
        "project_id": item.get("project_id"),
        "name": item.get("name"),
        "kind": item.get("kind"),
        "mime": item.get("mime"),
        "size_bytes": item.get("size_bytes"),
        "sha256": item.get("sha256"),
        "source": item.get("source"),
        "extraction_status": item.get("extraction_status"),
        "text_chars": item.get("text_chars"),
        "has_text": bool(item.get("has_text")),
        "metadata": _bounded_payload(item.get("metadata") or {}),
        "error": item.get("error"),
        "created_at": item.get("created_at"),
    }
    if include_preview:
        view["preview"] = preview
        view["preview_truncated"] = len(text) > 2000
    return view


def _research_view(payload: dict, *, text_limit: int = 20000) -> dict:
    """Bound the research service result; never expose raw HTML or headers."""
    payload = dict(payload or {})
    text = str(payload.get("text") or "")
    truncated = len(text) > text_limit or bool((payload.get("metadata") or {}).get("truncated"))
    view = {
        "ok": bool(payload.get("ok") or payload.get("allowed")),
        "outcome": payload.get("outcome"),
        "capability": payload.get("capability"),
        "reason": payload.get("reason"),
        "url": payload.get("url") or payload.get("canonical_url") or "",
        "title": payload.get("title") or "",
        "text": text[:text_limit],
        "text_truncated": truncated,
        "metadata": _bounded_payload(payload.get("metadata") or {}),
        "provenance": _bounded_payload(payload.get("provenance") or {}),
        "redirects": list(payload.get("redirects") or [])[:10],
        "source_id": payload.get("source_id"),
        "citation_id": payload.get("citation_id"),
        "untrusted": True,
        "injection_warnings": list(payload.get("injection_warnings") or [])[:10],
        "offline": bool(payload.get("offline")),
        "permission_needed": payload.get("permission_needed"),
        "denied": bool(payload.get("denied")),
        "error": _bounded_payload(payload.get("error") or {}),
    }
    return view


def _scoped_attachment_file(root: Path, raw: str) -> Path:
    """Resolve one explicit attachment path strictly inside the bound project."""
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Attachment path is empty")
    if "://" in text or "\x00" in text:
        raise ValueError("Attachment path must be a local file path")
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_symlink():
        raise ValueError("Symlinks are not accepted as attachments: " + str(candidate))
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Attachment file not found: " + str(candidate)) from exc
    if resolved != root and root not in resolved.parents:
        raise ValueError("Path is outside the bound project: " + str(candidate))
    if not resolved.is_file():
        raise ValueError("Attachment path is not a regular file: " + str(candidate))
    return resolved


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


def create_engine_server(services, project, *, allow_execution=False, research_profile="manual"):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    from nl_coding_agent.core import permissions

    project = dict(project)
    bound_project_id = int(project["id"])
    active = set()

    def require_read():
        permissions.require(permissions.READ, project_id=bound_project_id)

    def _configure_research():
        """Wire the existing stdlib transport under the existing permission gates."""
        try:
            from nl_coding_agent.core import auto_review
            from nl_coding_agent.research.transport import StdlibHttpTransport
            try:
                import certifi
                if not os.environ.get("SSL_CERT_FILE"):
                    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
            except Exception:
                pass

            def gate(url):
                permissions.require(permissions.NETWORK, project_id=bound_project_id)
                return True

            services.configure_research(
                fetch_transport=StdlibHttpTransport(gate),
                profile=auto_review.normalize_profile(research_profile),
            )
        except Exception as exc:  # research remains offline; tool reports it
            print("research configuration unavailable: " + type(exc).__name__, file=sys.stderr)

    _configure_research()

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
        try:
            research_status = services.research_status()
        except Exception as exc:
            research_status = {"status": "error", "error": type(exc).__name__}
        research = {
            "profile": str(research_profile),
            "status": research_status.get("status"),
            "offline": bool(research_status.get("offline")),
            "network_configured": bool(research_status.get("network_configured")),
            "network_granted": bool(permissions.get_policy(bound_project_id).get("network")),
            "permission_guidance": research_status.get("permission_guidance", ""),
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
                "generation_parameters": _plain_json(services.generation_params()),
            },
            "mission_defaults": mission_defaults,
            "agents": {
                "roles": _plain_json(services.get_agent_roles()),
                "custom_agents": _plain_json(services.list_custom_agents()),
            },
            "permissions": _plain_json(services.get_permissions(bound_project_id)),
            "research": research,
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
    @server.tool(annotations=read_only)
    def generation_parameters(model_name: str = "", role: str = "",
                              provider_id: str = "ollama") -> dict:
        """Read effective persistent generation parameters for a model/role."""
        require_read()
        return services.generation_params(
            model_name=model_name, role=role, provider_id=provider_id)

    @server.tool()
    def save_generation_parameters(parameters: dict, scope: str = "model",
                                   model_name: str = "", role: str = "",
                                   provider_id: str = "ollama",
                                   approved: bool = False) -> dict:
        """Persist explicit generation params; no num_ctx or Ollama server mutation."""
        require_execution(approved)
        return {"ok": True, "saved": services.save_generation_params(
            parameters, scope=scope, provider_id=provider_id,
            model_name=model_name, role=role)}

    @server.tool()
    def nlc_converse(project_id: int, text: str, attachments: list, history: list, *,
                     model_spec: str | None = None,
                     attachment_ids: list[int] | None = None,
                     tools_enabled: bool = True,
                     allow_coding: bool = False,
                     max_calls: int = 8, max_seconds: int = 180,
                     resume: bool = False,
                     tool_protocol: str = "native") -> dict:
        """Forward a chat request to the backend AppServices implementation.

        *project_id* must be the id reported by ``project_context`` for this
        server; any other id is rejected. *text* is the user message.
        *attachment_ids* references files ingested through ``attachment_ingest``;
        the backend validates project ownership and applies its own extraction
        budget. *history* is accepted for protocol compatibility but ignored:
        the backend persists and replays the real conversation history itself.
        *model_spec* optionally selects an exact provider/model route.

        Chat is agentic by default with read-only project tools. *allow_coding*
        only enables the explicit start_coding delegation; it never bypasses the
        Supervisor or mission verification.
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
        ids: list[int] = []
        for value in attachment_ids or []:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                raise ValueError("attachment_ids must be integers") from None
        prompt = message + ("" if ids else _attachment_context(attachments))
        proj = {"id": bound_project_id, "root": project.get("root", "")}
        return services.chat_conversation(
            proj, prompt, attachment_ids=ids or None, model_spec=model_spec,
            tools_enabled=bool(tools_enabled), max_calls=int(max_calls),
            max_seconds=int(max_seconds), allow_coding=bool(allow_coding),
            resume=bool(resume), tool_protocol=str(tool_protocol),
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                             idempotentHint=False, openWorldHint=False))
    def attachment_ingest(paths: list[str] | None = None, text: str | None = None,
                          name: str = "") -> dict:
        """Ingest explicit files strictly inside the bound project, or pasted text.

        Files are copied into the engine's existing attachment store and their
        text is extracted by the existing attachment pipeline; arbitrary paths,
        symlinks and files outside the workspace are rejected before reading.
        Returns attachment ids for ``nlc_converse`` and a bounded preview.
        """
        require_read()
        root = Path(str(project.get("root") or "")).resolve()
        gathered: list[dict] = []
        errors: list[dict] = []
        total_bytes = 0
        raw_paths = list(paths or [])
        if len(raw_paths) > 20:
            raise ValueError("At most 20 attachments can be ingested at once")
        if raw_paths:
            resolved = [_scoped_attachment_file(root, item) for item in raw_paths]
            batch = services.prepare_attachment_paths(bound_project_id, resolved,
                                                      source="vscode")
            for item in batch.get("attachments") or []:
                gathered.append(_attachment_view(item))
            errors.extend(batch.get("errors") or [])
            total_bytes += int(batch.get("total_bytes") or 0)
        if text is not None and str(text).strip():
            item = services.prepare_attachment_text(
                bound_project_id, str(text),
                name=(str(name).strip() or "pasted-context.txt"))
            gathered.append(_attachment_view(item))
            total_bytes += int(item.get("size_bytes") or 0)
        if not raw_paths and not (text is not None and str(text).strip()):
            raise ValueError("Provide at least one file path or text to ingest")
        return {"ok": bool(gathered), "attachments": gathered, "errors": errors,
                "total_bytes": total_bytes,
                "limits": {"max_file_bytes": 25 * 1024 * 1024,
                           "max_total_bytes": 100 * 1024 * 1024,
                           "max_files_per_batch": 20}}

    @server.tool(annotations=read_only)
    def chat_history(limit: int = 200, before_index: int | None = None) -> dict:
        """Read the bound project's persisted conversation thread (no new archive).

        Uses the same per-project JSON persistence as the Studio and returns
        attachment metadata plus the model/provider recorded for assistant turns.
        """
        require_read()
        from nl_coding_agent.app.attachments import get_attachment
        messages = services.list_chat_messages(project_id=bound_project_id)
        total = len(messages)
        requested_limit = max(1, min(int(limit), 1000))
        end = total if before_index is None else max(0, min(int(before_index), total))
        start = max(0, end - requested_limit)
        page = []
        for index in range(start, end):
            item = messages[index]
            content = str(item.get("content") or "")
            row = {
                "index": index,
                "role": str(item.get("role") or ""),
                "content": content[:20000],
                "content_truncated": len(content) > 20000,
                "created_at": item.get("created_at"),
            }
            if len(content) > 20000:
                row["content"] += "\n... [truncated]"
            attachments = []
            for attachment_id in item.get("attachment_ids") or []:
                try:
                    saved = get_attachment(int(attachment_id))
                except Exception:
                    continue
                if saved.get("project_id") != bound_project_id:
                    continue
                attachments.append(_attachment_view(saved, include_preview=False))
            if attachments:
                row["attachments"] = attachments
            if item.get("attachment_ids"):
                row["attachment_ids"] = [int(value) for value in item.get("attachment_ids") or []]
            for key in ("run_id", "model", "provider_id", "automatic"):
                if item.get(key) is not None:
                    row[key] = item.get(key)
            if item.get("tool_activity"):
                row["tool_activity"] = True
            page.append(row)
        return {"ok": True, "project_id": bound_project_id,
                "thread": "chat/project-" + str(bound_project_id) + ".json",
                "count": total, "offset": start, "returned": len(page),
                "has_more": start > 0, "messages": page}

    @server.tool(annotations=read_only)
    def chat_queue() -> dict:
        """List persistent messages queued while a Chat turn is running."""
        require_read()
        from nl_coding_agent.app.chat_tools import list_queue
        return list_queue(bound_project_id)

    @server.tool()
    def chat_enqueue(text: str, attachment_ids: list[int] | None = None,
                     mode: str = "queue") -> dict:
        """Persist a user message without interrupting the running Chat turn.

        ``mode=steer`` injects the message at the next Chat checkpoint; ordinary
        ``queue`` messages are drained as the next turn by the client.
        """
        require_read()
        from nl_coding_agent.app.chat_tools import enqueue, load_state
        state = load_state(bound_project_id)
        if mode == "steer" and (not state or state.get("status") != "running"):
            mode = "queue"
        return enqueue(services, bound_project_id, text, attachment_ids=attachment_ids, mode=mode)

    @server.tool()
    def chat_queue_remove(item_id: str) -> dict:
        """Remove one queued Chat message by id."""
        require_read()
        from nl_coding_agent.app.chat_tools import remove_queued
        return remove_queued(bound_project_id, item_id)

    @server.tool()
    def chat_queue_reorder(ids: list[str]) -> dict:
        """Reorder every queued Chat message; all ids must be present exactly once."""
        require_read()
        from nl_coding_agent.app.chat_tools import reorder_queue
        return reorder_queue(bound_project_id, ids)

    @server.tool()
    def chat_steer(text: str) -> dict:
        """Inject a steering instruction into the running Chat at its next checkpoint."""
        require_read()
        from nl_coding_agent.app.chat_tools import enqueue, load_state
        state = load_state(bound_project_id)
        mode = "steer" if state and state.get("status") == "running" else "queue"
        return enqueue(services, bound_project_id, text, mode=mode)

    @server.tool()
    def chat_cancel() -> dict:
        """Request cooperative cancellation of the current Chat tool run."""
        require_read()
        return services.cancel_chat_tools(bound_project_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                             idempotentHint=True, openWorldHint=True))
    def research_fetch_url(url: str) -> dict:
        """Fetch one public URL through the existing Research service and permissions.

        Requires an explicit NETWORK grant; the configured research profile and
        any web-fetch capability grant decide whether the fetch is allowed or
        needs approval. The returned page text is UNTRUSTED data; raw HTML is not
        exposed and nothing from the page is executed or followed as instructions.
        """
        require_read()
        permissions.require(permissions.NETWORK, project_id=bound_project_id)
        target = str(url or "").strip()
        if not target:
            raise ValueError("URL is required")
        if len(target) > 2000:
            raise ValueError("URL is too long")
        if not target.startswith(("https://", "http://")):
            raise ValueError("Only http(s) URLs are supported")
        payload = services.research_fetch_read(target, project_id=bound_project_id)
        return _research_view(payload)

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

    @server.tool()
    def mission_steer(mission_id: int, text: str) -> dict:
        """Queue a steering instruction for the next safe mission stage checkpoint."""
        details = mission(mission_id)
        status = str(details.get("status") or "")
        if status not in ("pending", "running", "interrupted", "blocked"):
            raise ValueError("Mission is not active; steering only queues for a resumable mission")
        message = str(text or "").strip()
        if not message:
            raise ValueError("Steering text is required")
        from nl_coding_agent.persistence.database import set_setting
        set_setting("mission.steer." + str(int(mission_id)), message[:8000])
        return {"ok": True, "mission_id": int(mission_id), "queued": True,
                "note": "Applied at the next agent stage prompt/checkpoint; not instant."}

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
            "metadata": _bounded_payload(_json_mapping(item.get("metadata_json"))),
        } for item in details.get("attempts", [])]
        execution_errors = []
        for item in details.get("execution_errors", []):
            payload = item.get("payload") or {}
            execution_errors.append({
                "id": item.get("id"), "kind": item.get("kind"),
                "record_key": item.get("record_key"),
                "created_at": item.get("created_at"),
                "source": payload.get("source"),
                "method": payload.get("method"),
                "flow_id": payload.get("flow_id"),
                "task_id": payload.get("task_id"),
                "exception_type": payload.get("exception_type"),
                "message": _bounded_text(payload.get("message"), 4000),
                "traceback": _bounded_text(payload.get("traceback"), 16000),
                "traceback_truncated": bool(payload.get("traceback_truncated")),
                "pid": payload.get("pid"),
                "reason": payload.get("reason"),
                "previous_status": payload.get("previous_status"),
                "new_status": payload.get("new_status"),
            })
        tool_invocations = [{
            "id": item.get("id"),
            "tool_name": item.get("tool_name"),
            "source": item.get("source"),
            "status": item.get("status"),
            "role": item.get("role"),
            "model": item.get("model"),
            "arguments": _bounded_payload(item.get("arguments_json") or {}),
            "result": _bounded_payload(item.get("result_json") or {}),
            "error": _bounded_text(item.get("error"), 2000),
            "duration_ms": item.get("duration_ms"),
            "call_id": item.get("call_id"),
            "created_at": item.get("created_at"),
        } for item in (details.get("tool_invocations") or [])]
        return {"mission": mission_view, "tasks": tasks, "handoffs": handoffs,
                "verification_runs": verification_runs, "attempts": attempts,
                "execution_errors": execution_errors,
                "tool_invocations": tool_invocations,
                "model_bindings": services.mission_model_bindings(mission_id),
                "progress": details.get("progress") or {}}

    @server.tool(annotations=read_only)
    def candidate_diff(mission_id: int) -> dict:
        """Inspect a staged candidate, including rejected candidates; never promote."""
        mission(mission_id)
        return services.mission_candidate_diff(mission_id, project_id=bound_project_id)

    @server.tool()
    def start_mission(goal: str, developer_model: str, reviewer_model: str,
                      approved: bool = False, resume_mission_id: int | None = None,
                      architect_model: str | None = None,
                      pipeline: str = "flow") -> dict:
        """Start/resume through the resource-gated engine only with owner-enabled execution.

        Exact model routes are required; this does not approve a candidate or bypass tests.
        *architect_model* is optional; when omitted the developer route is used for the
        read-only architecture stage. ``pipeline`` selects the real CrewAI Flow graph
        (default) or the legacy sequential driver. Returns a queued mission id; use
        status/events to monitor actual completion.
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
                architect_model=architect_model, pipeline=pipeline,
                on_done=lambda result: active.discard(mission_id))
        except Exception:
            active.discard(mission_id)
            raise
        return {"mission_id": mission_id, "dispatch": "queued", "task_id": task_id,
                "models": {"developer": developer_model, "reviewer": reviewer_model,
                           "architect": architect_model or developer_model}}

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

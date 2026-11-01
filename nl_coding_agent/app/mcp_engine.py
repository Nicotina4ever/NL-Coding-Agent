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

    @server.tool(annotations=read_only)
    def mcp_servers() -> dict:
        """Read the trusted MCP server configuration (secret values never returned)."""
        require_read()
        return {"ok": True, "config": services.get_mcp_config()}

    @server.tool()
    def save_mcp_servers(config: dict, approved: bool = False) -> dict:
        """Validate and persist MCP server configuration; no secrets are accepted."""
        require_execution(approved)
        saved = services.save_mcp_config(config)
        return {"ok": True, "servers": sorted((saved.get("servers") or {}).keys())}

    @server.tool()
    def save_generation_parameters(parameters: dict, scope: str = "model",
                                   model_name: str = "", role: str = "",
                                   provider_id: str = "ollama",
                                   approved: bool = False) -> dict:
        """Persist explicit generation params; unset num_ctx preserves Ollama defaults."""
        require_read()
        return {"ok": True, "saved": services.save_generation_params(
            parameters, scope=scope, provider_id=provider_id,
            model_name=model_name, role=role)}

    @server.tool()
    def save_provider_settings(provider_id: str, enabled: bool | None = None,
                               base_url: str | None = None, label: str | None = None,
                               kind: str | None = None,
                               api_key_env: str | None = None,
                               approved: bool = False) -> dict:
        """Persist provider enabled/endpoint/label/kind; never returns or stores secrets."""
        require_read()
        changes = {key: value for key, value in {
            "enabled": enabled, "base_url": base_url, "label": label,
            "kind": kind, "api_key_env": api_key_env,
        }.items() if value is not None}
        services.save_provider_settings(provider_id, **changes)
        return {"ok": True, "provider": provider_id, "changes": changes}

    @server.tool()
    def save_role_settings(role: str, model: str | None = None,
                           temperature: float | None = None,
                           approved: bool = False) -> dict:
        """Persist a role's model route and optional generation temperature."""
        require_read()
        changes = {key: value for key, value in {
            "model": model, "temperature": temperature,
        }.items() if value is not None}
        services.save_role_settings(role, **changes)
        return {"ok": True, "role": role, "changes": changes}

    @server.tool()
    def set_cloud_escalation(enabled: bool, approved: bool = False) -> dict:
        """Persist the explicit cloud-escalation policy (default off)."""
        require_execution(approved)
        services.save_cloud_escalation(bool(enabled))
        return {"ok": True, "cloud_escalation_enabled": bool(enabled)}

    @server.tool()
    def probe_model_capabilities(model: str, timeout_s: float = 90.0,
                                 approved: bool = False) -> dict:
        """Measure real tool-calling/structured/patch capabilities for one local model."""
        require_execution(approved)
        return services.probe_model_capabilities(model, timeout=timeout_s)

    @server.tool()
    def save_permission_scope(scope: str, granted: bool,
                              approved: bool = False) -> dict:
        """Explicitly grant/revoke one project permission and return fresh policy."""
        # Research/network is a read-only capability, not code execution. Let the
        # owner grant NETWORK from a read-only session so pasted URLs can be fetched;
        # write/execute/cloud still require an execution-enabled server.
        if str(scope).lower() in ("read", "network", "cloud"):
            require_read()
        else:
            require_execution(approved)
        return {"ok": True, "permissions": services.set_permission_scope(
            str(scope), bool(granted), project_id=bound_project_id, source="mcp-approved")}

    @server.tool(annotations=read_only)
    def custom_agents() -> dict:
        """List specialist agent profiles (configuration presets, not hidden execution)."""
        require_read()
        return {"ok": True, "agents": services.list_custom_agents()}

    @server.tool(annotations=read_only)
    def consult_specialist(agent: str, question: str, context: str = "",
                           timeout_s: int = 120) -> dict:
        """Ask one specialist profile for a read-only second opinion."""
        require_read()
        return {"ok": True, "consultation": services.consult_specialist(
            bound_project_id, agent, question, context=context,
            timeout=max(5, min(int(timeout_s), 300)))}

    @server.tool()
    def agent_task(agent: str, task: str, session_id: str | None = None) -> dict:
        """Send one task directly to a named specialist, executed alone and persisted."""
        require_read()
        return {"ok": True, "task": services.agent_task(
            bound_project_id, agent, task, session_id=session_id,
            timeout=180.0)}

    @server.tool()
    def save_custom_agent(agent_id: str | None = None,
                          name: str = "Specialist agent",
                          provider: str = "ollama",
                          model: str = "",
                          role: str = "assistant",
                          instructions: str = "",
                          tools: list[str] | None = None,
                          permissions: list[str] | None = None,
                          enabled: bool = True,
                          approved: bool = False) -> dict:
        """Create or update a specialist agent profile with a model assignment."""
        require_read()
        fields = {
            "name": str(name or "Specialist agent").strip() or "Specialist agent",
            "provider": str(provider or "ollama"),
            "model": str(model or ""),
            "role": str(role or "assistant"),
            "instructions": str(instructions or ""),
            "tools": [str(item) for item in (tools or [])],
            "permissions": [str(item) for item in (permissions or [])],
            "enabled": bool(enabled),
        }
        if agent_id:
            saved = services.update_custom_agent(str(agent_id), **fields)
            if saved is None:
                raise ValueError("Custom agent not found")
        else:
            saved = services.create_custom_agent(fields.pop("name"), **fields)
        return {"ok": True, "agent": saved}

    @server.tool()
    def delete_custom_agent(agent_id: str, approved: bool = False) -> dict:
        """Delete one specialist agent profile."""
        require_read()
        if not services.delete_custom_agent(str(agent_id)):
            raise ValueError("Custom agent not found")
        return {"ok": True}

    @server.tool()
    def duplicate_custom_agent(agent_id: str, name: str | None = None,
                               approved: bool = False) -> dict:
        """Duplicate one specialist agent profile under a new name."""
        require_read()
        saved = services.duplicate_custom_agent(str(agent_id), name=name)
        if saved is None:
            raise ValueError("Custom agent not found")
        return {"ok": True, "agent": saved}

    @server.tool(annotations=read_only)
    def autonomy_settings() -> dict:
        """Read persisted autonomy mode/budgets for the bound project."""
        require_read()
        return services.autonomy_settings(bound_project_id)

    @server.tool()
    def save_autonomy_settings(mode: str | None = None,
                               max_missions: int | None = None,
                               attempts: int | None = None,
                               max_wall_time_s: int | None = None,
                               mission_wall_time_s: int | None = None,
                               approved: bool = False) -> dict:
        """Persist validated autonomy settings; never starts a run."""
        require_read()
        return services.save_autonomy_settings(
            bound_project_id, mode=mode, max_missions=max_missions,
            attempts=attempts, max_wall_time_s=max_wall_time_s,
            mission_wall_time_s=mission_wall_time_s)

    @server.tool()
    def nlc_converse(project_id: int, text: str, attachments: list, history: list, *,
                     model_spec: str | None = None,
                     attachment_ids: list[int] | None = None,
                     tools_enabled: bool = True,
                     allow_coding: bool = False,
                     max_calls: int = 8, max_seconds: int = 900,
                     resume: bool = False,
                     tool_protocol: str = "native",
                     session_id: str | None = None) -> dict:
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
            session_id=session_id,
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
    def chat_history(limit: int = 200, before_index: int | None = None,
                     session_id: str | None = None) -> dict:
        """Read one persisted conversation session (default: latest active)."""
        require_read()
        from nl_coding_agent.app.attachments import get_attachment
        messages = services.list_chat_messages(project_id=bound_project_id,
                                               session_id=session_id)
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
                "session_id": session_id,
                "thread": "chat/session:" + str(session_id) if session_id else "chat/latest",
                "count": total, "offset": start, "returned": len(page),
                "has_more": start > 0, "messages": page}

    @server.tool(annotations=read_only)
    def chat_sessions(include_archived: bool = False) -> dict:
        """List durable Chat sessions for the bound project."""
        require_read()
        return {"ok": True, "sessions": services.list_chat_sessions(
            bound_project_id, include_archived=bool(include_archived))}

    @server.tool()
    def chat_session_create(title: str = "New conversation",
                            approved: bool = False) -> dict:
        """Create a durable Chat session; history works in read-only mode."""
        require_read()
        return {"ok": True, "session": services.create_chat_session(
            bound_project_id, title)}

    @server.tool()
    def chat_session_rename(session_id: str, title: str,
                            approved: bool = False) -> dict:
        """Rename a Chat session; history works in read-only mode."""
        require_read()
        return {"ok": True, "session": services.rename_chat_session(session_id, title)}

    @server.tool()
    def chat_session_archive(session_id: str, approved: bool = False) -> dict:
        """Archive one Chat session; history is retained and allowed in read-only mode."""
        require_read()
        return {"ok": True, "session": services.archive_chat_session(session_id)}

    @server.tool()
    def chat_session_delete(session_id: str, approved: bool = False) -> dict:
        """Delete one previously archived Chat session and its messages."""
        require_read()
        return {"ok": True, "session": services.delete_chat_session(
            bound_project_id, session_id)}

    @server.tool()
    def chat_rewind(session_id: str, message_id: int, replacement: str = "",
                    approved: bool = False) -> dict:
        """Delete one persisted message and everything after it; optional edited user text."""
        require_read()
        return services.rewind_chat_session(
            bound_project_id, session_id, int(message_id),
            replacement=(str(replacement) if str(replacement).strip() else None))

    @server.tool(annotations=read_only)
    def speech_status() -> dict:
        """Report local ASR/TTS availability without downloading anything."""
        require_read()
        return {"ok": True, "speech": services.speech_status(),
                "catalog": services.speech_catalog()}

    @server.tool()
    def speech_start_recording(max_seconds: int = 60) -> dict:
        """Start one explicit local microphone recording."""
        require_read()
        return {"ok": True, "recording": services.speech_start_recording(
            max_seconds=max(1, min(int(max_seconds), 120)))}

    @server.tool()
    def speech_stop_recording(session_id: str) -> dict:
        """Stop a recording and return its local WAV path."""
        require_read()
        return {"ok": True, "recording": services.speech_stop_recording(str(session_id))}

    @server.tool()
    def speech_switch_model(model_id: str) -> dict:
        """Select one discovered local ASR model."""
        require_read()
        return {"ok": True, "model": services.speech_switch_model(str(model_id)),
                "catalog": services.speech_catalog()}

    @server.tool()
    def speech_set_external_home(path: str) -> dict:
        """Register an existing external ASR folder (for example Qwen3-ASR) in place."""
        require_read()
        return {"ok": True, "speech": services.speech_manager().set_external_home(str(path))}

    @server.tool()
    def speech_transcribe(wav_path: str, language: str = "") -> dict:
        """Transcribe an existing local WAV with the selected local ASR model."""
        require_read()
        return {"ok": True, "transcript": services.speech_transcribe(
            str(wav_path), language=(str(language) or None))}

    @server.tool(annotations=read_only)
    def chat_search(query: str, limit: int = 100) -> dict:
        """Search persisted Chat messages in the bound project."""
        require_read()
        return {"ok": True, "messages": services.search_chat_messages(
            bound_project_id, query, limit=int(limit))}

    @server.tool()
    def chat_cleanup(scope: str = "orphaned", approved: bool = False) -> dict:
        """Delete archived sessions or conversations whose project was removed."""
        require_read()
        if str(scope) == "archived":
            project_id = bound_project_id
        else:
            project_id = None
        return {"ok": True, "result": services.cleanup_chat_sessions(
            str(scope), project_id=project_id)}


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
    def mission_list(include_archived: bool = True, status: str | None = None,
                     query: str | None = None) -> dict:
        """List persisted missions for the bound project without starting work."""
        require_read()
        return {"missions": services.list_missions(
            bound_project_id, include_archived=bool(include_archived),
            status=status, query=query)}

    @server.tool()
    def accept_mission(mission_id: int, approved: bool = False) -> dict:
        """Explicitly keep a promoted mission's changes; no files are modified."""
        mission(mission_id)
        return services.accept_mission(int(mission_id), project_id=bound_project_id)

    @server.tool()
    def revert_mission(mission_id: int, approved: bool = False) -> dict:
        """Reject a promoted mission and restore its pre-mission baseline."""
        require_execution(approved)
        mission(mission_id)
        return services.revert_mission(int(mission_id), project_id=bound_project_id)

    @server.tool()
    def archive_mission(mission_id: int, approved: bool = False) -> dict:
        """Archive a terminal mission; data is retained and the action is reversible."""
        require_execution(approved)
        mission(mission_id)
        return {"ok": True, "mission": services.archive_mission(
            int(mission_id), project_id=bound_project_id)}

    @server.tool()
    def unarchive_mission(mission_id: int, approved: bool = False) -> dict:
        """Restore an archived mission to the active list."""
        require_execution(approved)
        mission(mission_id)
        return {"ok": True, "mission": services.unarchive_mission(int(mission_id))}

    @server.tool()
    def delete_mission(mission_id: int, approved: bool = False) -> dict:
        """Delete only an already archived terminal mission; never live/staged files."""
        require_execution(approved)
        mission(mission_id)
        return {"ok": True, "mission": services.delete_mission(
            int(mission_id), project_id=bound_project_id)}

    @server.tool()
    def job_start(argv: list[str], label: str = "", timeout_s: int = 900,
                  approved: bool = False) -> dict:
        """Run one allowlisted argv in the project root as a background job."""
        require_execution(approved)
        from nl_coding_agent.core import job_manager
        return {"ok": True, "job": job_manager.start_job(
            bound_project_id, project["root"], list(argv or []),
            label=label, timeout_s=int(timeout_s))}

    @server.tool(annotations=read_only)
    def job_list() -> dict:
        """List background jobs for the bound project."""
        require_read()
        from nl_coding_agent.core import job_manager
        return {"ok": True, "jobs": job_manager.list_jobs(bound_project_id)}

    @server.tool(annotations=read_only)
    def job_output(job_id: str, max_bytes: int = 20000) -> dict:
        """Read bounded output from one project background job."""
        require_read()
        from nl_coding_agent.core import job_manager
        return {"ok": True, **job_manager.output(
            bound_project_id, str(job_id), max_bytes=int(max_bytes))}

    @server.tool()
    def job_stop(job_id: str, approved: bool = False) -> dict:
        """Stop one project background job."""
        require_execution(approved)
        from nl_coding_agent.core import job_manager
        return {"ok": True, "job": job_manager.stop_job(bound_project_id, str(job_id))}

    @server.tool(annotations=read_only)
    def resource_status() -> dict:
        """Read RAM, CPU, GPU memory and loaded local models (observation only)."""
        require_read()
        from nl_coding_agent.core import resource_monitor
        return {"ok": True, **resource_monitor.snapshot()}

    @server.tool(annotations=read_only)
    def storage_scan() -> dict:
        """Read-only size scan of temporary/build/backup/staging categories."""
        require_read()
        return services.storage_scan(project["root"])

    @server.tool()
    def storage_purge(selected_ids: list[str], confirm: bool = False,
                      approved: bool = False) -> dict:
        """Delete only explicitly selected, non-protected storage categories."""
        require_execution(approved)
        if not confirm:
            raise ValueError("Storage cleanup requires confirm=true")
        return services.storage_purge(
            selected_ids, confirm=True, project_root=project["root"])

    @server.tool()
    def storage_vacuum(confirm: bool = False, approved: bool = False) -> dict:
        """Compact SQLite with a bounded backup after explicit confirmation."""
        require_execution(approved)
        if not confirm:
            raise ValueError("SQLite compaction requires confirm=true")
        return services.storage_vacuum(confirm=True)

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
                        "supervisor_run_id", "flow_id", "archived_at")
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
                      pipeline: str = "flow",
                      from_task_id: int | None = None) -> dict:
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
            if from_task_id is not None:
                from nl_coding_agent.persistence.missions import reset_tasks_from
                reset_ids = reset_tasks_from(mission_id, int(from_task_id))
                if not reset_ids:
                    raise ValueError("No task at or after the requested retry point")
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

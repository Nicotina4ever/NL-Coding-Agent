"""Project-bound MCP client interface to AppServices and the existing mission engine."""
from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager, redirect_stdout
from pathlib import Path


def create_engine_server(services, project, *, allow_execution=False):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    from nl_coding_agent.core import permissions

    project = dict(project)
    project_id = int(project["id"])
    active = set()

    def require_read():
        permissions.require(permissions.READ, project_id=project_id)

    def mission(mission_id):
        require_read()
        details = services.get_mission_details(int(mission_id))
        if not details or details.get("project_id") != project_id:
            raise ValueError("Mission does not belong to this server's project")
        return details

    def require_execution(approved):
        if not allow_execution or not approved:
            raise PermissionError("Server is read-only or this operation was not explicitly approved")
        permissions.require(permissions.EXECUTE, project_id=project_id)
        permissions.require(permissions.WRITE, project_id=project_id)

    @asynccontextmanager
    async def lifespan(server):
        # FastMCP opens its stdio streams BEFORE entering lifespan. The protocol
        # retains stdout; verbose engine output goes to stderr, never onto JSON-RPC.
        with redirect_stdout(sys.stderr):
            try:
                yield
            finally:
                for mission_id in list(active):
                    services.cancel_mission(mission_id, project_id=project_id,
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
    def mission_list() -> dict:
        """List persisted missions for the bound project without starting work."""
        require_read()
        return {"missions": services.list_missions(project_id)}

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
    def candidate_diff(mission_id: int) -> dict:
        """Inspect a staged candidate, including rejected candidates; never promote."""
        mission(mission_id)
        return services.mission_candidate_diff(mission_id, project_id=project_id)

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
            mission_id = services.create_mission(project_id, goal[:80], goal)
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
        return services.cancel_mission(mission_id, project_id=project_id, reason="MCP cancellation")

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

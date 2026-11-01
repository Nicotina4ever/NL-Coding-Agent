"""End-to-end smoke test for the project-bound NL Code MCP server."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


async def run(project: Path) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=str(ROOT / "python" / "python.exe"),
        args=[str(ROOT / "nl_agent.py"), "mcp", "serve", "--project", str(project)],
        cwd=str(ROOT),
        env=None,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            context = await session.call_tool("project_context", {})
            settings = await session.call_tool("engine_settings", {})
            return {
                "ok": True,
                "tool_count": len(names),
                "has_project_context": "project_context" in names,
                "has_engine_settings": "engine_settings" in names,
                "has_plan_generate": "plan_generate" in names,
                "has_team_plan": "team_plan" in names,
                "has_checkpoints": "checkpoint_create" in names,
                "context_is_error": bool(context.isError),
                "settings_is_error": bool(settings.isError),
                "context": context.content[0].text[:500] if context.content else "",
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=str(ROOT / "ParcoTest"))
    args = parser.parse_args()
    try:
        result = asyncio.run(run(Path(args.project).resolve()))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__ + ": " + str(exc)},
                         ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") and not result.get("context_is_error") else 2


if __name__ == "__main__":
    raise SystemExit(main())

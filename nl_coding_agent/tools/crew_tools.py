"""CrewAI tool bindings for project-scoped development.

Model-facing file tools are scoped to the staged candidate. The additional execution
tools are deliberately bounded: tests and a small argv allowlist (git/read-only
inspection/python compile) with shell=False, so a model cannot turn the tool layer
into an unrestricted shell. Research uses the existing authorized service.
MCP discovery uses the existing local stdio client; MCP invocation remains
human-approval-gated by that client and is never silently approved here.
"""
from __future__ import annotations

import shlex
import sys
from pathlib import Path

from crewai.tools import tool

from nl_coding_agent.tools.filesystem import (
    scoped_read_file,
    scoped_write_file,
    scoped_patch_file,
    scoped_list_dir,
)
from nl_coding_agent.tools.git_tools import get_git_diff, get_git_status
from nl_coding_agent.tools.shell import scoped_run_argv, scoped_run_command
from nl_coding_agent.tools.verification import detect_test_command


def _bounded(value: str, limit: int = 8000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [output truncated]"


def _command_result(result: dict) -> str:
    parts = [
        "exit_code: " + str(result.get("returncode")),
        "duration_s: " + str(result.get("duration_s")),
    ]
    if result.get("timed_out"):
        parts.append("timed_out: true")
    parts.append("stdout:\n" + _bounded(result.get("stdout") or ""))
    if result.get("stderr"):
        parts.append("stderr:\n" + _bounded(result.get("stderr")))
    return "\n".join(parts)


def _allowed_argv(command: str) -> list[str] | None:
    """Return an argv vector for a read-only/bounded command, or None if denied."""
    text = str(command or "").strip()
    if not text or any(marker in text for marker in ("|", "&", ";", ">", "<", "`", "$(")):
        return None
    try:
        args = shlex.split(text, posix=False)
    except ValueError:
        return None
    args = [part.strip('"') for part in args]
    if not args:
        return None
    head = Path(args[0]).name.lower()
    if head in ("python", "python.exe", "py", "py.exe"):
        args[0] = sys.executable
        if len(args) < 3 or args[1] != "-m" or args[2] not in ("pytest", "py_compile", "compileall"):
            return None
        return args
    if head in ("pytest", "pytest.exe"):
        return args
    if head in ("git", "git.exe"):
        if len(args) < 2 or args[1].lower() not in (
            "status", "diff", "log", "show", "rev-parse", "ls-files",
        ):
            return None
        return args
    if head in ("ls", "dir", "findstr", "rg", "grep", "cat", "type"):
        return args
    return None


def get_project_tools(project_root: Path | str, *, read_only: bool = False,
                      project_id: int | None = None) -> list:
    """Create the model-facing tool suite scoped strictly to project_root.

    read_only=True removes write/execution tools for analysis roles.
    """
    root = Path(project_root).resolve()

    @tool("read_file")
    def read_file(path: str) -> str:
        """Read text content from a file relative to the project root."""
        try:
            return scoped_read_file(root, path)
        except Exception as e:
            return f"Error reading file '{path}': {e}"

    @tool("write_file")
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file relative to the project root with the given content."""
        try:
            return scoped_write_file(root, path, content)
        except Exception as e:
            return f"Error writing file '{path}': {e}"

    @tool("patch_file")
    def patch_file(path: str, target: str, replacement: str) -> str:
        """Replace exact snippet 'target' with 'replacement' in the specified file."""
        try:
            return scoped_patch_file(root, path, target, replacement)
        except Exception as e:
            return f"Error patching file '{path}': {e}"

    @tool("list_dir")
    def list_dir(path: str = ".") -> str:
        """List files and folders inside a relative directory in the project."""
        try:
            entries = scoped_list_dir(root, path)
            return "\n".join(entries) if entries else "(Empty directory)"
        except Exception as e:
            return f"Error listing directory '{path}': {e}"

    tools = [read_file, list_dir]
    if read_only:
        return tools

    @tool("run_command")
    def run_command(command: str, timeout: int = 30) -> str:
        """Run one bounded command in the staged workspace (pytest, python -m py_compile,
        git status/diff/log/show, or read-only listing/inspection). Shell metacharacters
        and arbitrary executables are rejected; shell=False is used."""
        args = _allowed_argv(command)
        if args is None:
            return (
                "Command denied by the tool policy. Allowed: pytest, python -m pytest/"
                "py_compile/compileall, git status/diff/log/show/rev-parse/ls-files, "
                "and read-only ls/dir/rg/grep/cat/type/findstr."
            )
        result = scoped_run_argv(root, args, timeout=max(1, min(int(timeout), 120)))
        return _command_result(result)

    @tool("run_tests")
    def run_tests(timeout: int = 120) -> str:
        """Run the project's detected test command inside the staged workspace and return
        the real exit code, stdout and stderr. This is a self-check; the independent
        tester still runs the candidate and oracle suites."""
        command = detect_test_command(root)
        result = scoped_run_command(root, command, timeout=max(1, min(int(timeout), 240)))
        return "command: " + command + "\n" + _command_result(result)

    @tool("git_status")
    def git_status() -> str:
        """Return the real git working-tree status for the staged workspace (if it is a repo)."""
        return _bounded(get_git_status(root), 4000)

    @tool("git_diff")
    def git_diff() -> str:
        """Return the real unified git diff for the staged workspace (if it is a repo)."""
        return _bounded(get_git_diff(root), 12000)

    @tool("research_fetch_url")
    def research_fetch_url(url: str) -> str:
        """Fetch one URL through the existing authorized Research service and return
        bounded text plus metadata. Does not bypass NETWORK/web-fetch grants."""
        try:
            from nl_coding_agent.research.service import ResearchService
            payload = ResearchService().fetch_read(str(url), project_id=project_id)
            return _bounded(
                "ok: " + str(payload.get("ok")) + "\n"
                "url: " + str(payload.get("url") or url) + "\n"
                "title: " + str(payload.get("title") or "") + "\n"
                "text:\n" + str(payload.get("text") or "")
                + "\nmetadata: " + str(payload.get("metadata") or {}),
                12000,
            )
        except Exception as exc:
            return "Research fetch failed: " + type(exc).__name__ + ": " + str(exc)

    @tool("mcp_list_tools")
    def mcp_list_tools(server: str) -> str:
        """Discover tools advertised by one configured local MCP stdio server. Invocation
        remains human-approval-gated by the existing MCP client."""
        try:
            from nl_coding_agent.app.mcp import McpManager
            manager = McpManager(project_id=project_id)
            rows = manager.list_tools(server)
            return _bounded("\n".join(
                str(row.get("qualified_name") or row.get("name")) + " :: "
                + str(row.get("description") or "") for row in rows
            ) or "(no tools advertised)")
        except Exception as exc:
            return "MCP discovery failed: " + type(exc).__name__ + ": " + str(exc)

    tools.extend([write_file, patch_file, run_command, run_tests, git_status, git_diff,
                  research_fetch_url, mcp_list_tools])
    return tools

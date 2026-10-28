"""CrewAI tool bindings for project-scoped development."""
from __future__ import annotations

from pathlib import Path
from crewai.tools import tool
from nl_coding_agent.tools.filesystem import (
    scoped_read_file,
    scoped_write_file,
    scoped_patch_file,
    scoped_list_dir,
)
from nl_coding_agent.tools.shell import scoped_run_command
from nl_coding_agent.tools.git_tools import get_git_diff, get_git_status
from nl_coding_agent.tools.verification import run_verification


def get_project_tools(project_root: Path | str) -> list:
    """Create a suite of CrewAI tools scoped strictly to the given project_root."""
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

    @tool("run_command")
    def run_command(command: str) -> str:
        """Run a shell command in the project root and return stdout and stderr."""
        try:
            res = scoped_run_command(root, command)
            return f"Exit code: {res['returncode']}\nSTDOUT:\n{res['stdout']}\nSTDERR:\n{res['stderr']}"
        except Exception as e:
            return f"Error running command: {e}"

    @tool("git_diff")
    def git_diff() -> str:
        """Inspect uncommitted git changes in the project."""
        try:
            return get_git_diff(root)
        except Exception as e:
            return f"Error getting git diff: {e}"

    @tool("run_tests")
    def run_tests() -> str:
        """Run the project's automated test suite and report results."""
        try:
            res = run_verification(root)
            status = "PASSED" if res["passed"] else "FAILED"
            return f"Test status: {status} (code {res['exit_code']})\nOutput:\n{res['stdout']}\nErrors:\n{res['stderr']}"
        except Exception as e:
            return f"Error running tests: {e}"

    return [read_file, write_file, patch_file, list_dir, run_command, git_diff, run_tests]

"""CrewAI tool bindings for project-scoped development.

Model-facing tools are deliberately limited to file read/write/patch/list. Generic
shell execution (run_command) and test execution (run_tests, git_diff) are NOT
exposed to the model: they are arbitrary code execution and there is no OS sandbox
in this phase (SPEC-28 SH-05). Verification is performed by the independent
verifier stage, never by the model.
"""
from __future__ import annotations

from pathlib import Path
from crewai.tools import tool
from nl_coding_agent.tools.filesystem import (
    scoped_read_file,
    scoped_write_file,
    scoped_patch_file,
    scoped_list_dir,
)


def get_project_tools(project_root: Path | str) -> list:
    """Create the model-facing tool suite scoped strictly to project_root."""
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

    return [read_file, write_file, patch_file, list_dir]

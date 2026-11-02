"""Unit tests for operational filesystem, shell, git, and verification tools."""
import tempfile
from pathlib import Path
import pytest
from nl_coding_agent.tools.filesystem import (
    scoped_read_file,
    scoped_write_file,
    scoped_patch_file,
    scoped_list_dir,
    FilesystemSecurityError,
)
from nl_coding_agent.tools.shell import scoped_run_command
from nl_coding_agent.tools.git_tools import get_git_status, get_git_diff
from nl_coding_agent.tools.verification import run_verification
from nl_coding_agent.tools.crew_tools import get_project_tools


def test_scoped_filesystem_operations():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)

        # Write
        msg = scoped_write_file(root, "src/hello.py", "print('hello world')\n")
        assert "Successfully wrote" in msg
        assert (root / "src" / "hello.py").exists()

        # Read
        content = scoped_read_file(root, "src/hello.py")
        assert "print('hello world')" in content

        # Patch
        patch_msg = scoped_patch_file(root, "src/hello.py", "hello world", "hello agent")
        assert "Successfully replaced" in patch_msg
        assert scoped_read_file(root, "src/hello.py") == "print('hello agent')\n"

        # List
        files = scoped_list_dir(root, "src")
        assert "hello.py" in files


def test_scoped_filesystem_security():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)

        # Disallow directory traversal outside root
        with pytest.raises(FilesystemSecurityError):
            scoped_write_file(root, "../outside.txt", "exploit")

        # Disallow modifying protected folders
        with pytest.raises(FilesystemSecurityError):
            scoped_write_file(root, "python/exploit.py", "malicious")

        with pytest.raises(FilesystemSecurityError):
            scoped_write_file(root, ".git/hooks/pre-commit", "malicious")


def test_scoped_shell_execution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        scoped_write_file(root, "test.txt", "sample data")

        res = scoped_run_command(root, "dir")
        assert res["returncode"] == 0
        assert "test.txt" in res["stdout"]


def test_crew_tools_binding_is_bounded_and_explicit():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        tools = get_project_tools(root)
        tool_names = [t.name for t in tools]
        assert {"read_file", "write_file", "patch_file", "list_dir"} <= set(tool_names)
        assert {"run_command", "run_tests", "git_status", "git_diff",
                "research_fetch_url", "mcp_list_tools"} <= set(tool_names)
        assert {"search_symbols", "lsp_diagnostics", "list_skills", "load_skill"} <= set(tool_names)
        assert len(tools) == 14
        # Execution is exposed only through the bounded argv/test wrappers, never
        # as an unrestricted model-supplied shell command.
        source = Path("nl_coding_agent/tools/crew_tools.py").read_text(encoding="utf-8")
        assert "shell=False" in source
        assert "_allowed_argv" in source


def test_scoped_write_file_writes_lf_bytes_without_newline_translation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        scoped_write_file(root, "src/lf.py", "a = 1\nb = 2\n")
        raw = (root / "src" / "lf.py").read_bytes()
        assert b"\r\n" not in raw
        assert raw == b"a = 1\nb = 2\n"

        scoped_patch_file(root, "src/lf.py", "a = 1", "a = 3")
        raw = (root / "src" / "lf.py").read_bytes()
        assert b"\r\n" not in raw
        assert raw == b"a = 3\nb = 2\n"

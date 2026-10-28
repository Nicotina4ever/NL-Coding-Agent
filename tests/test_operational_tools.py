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


def test_crew_tools_binding():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        tools = get_project_tools(root)
        assert len(tools) == 7
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "patch_file" in tool_names
        assert "run_tests" in tool_names

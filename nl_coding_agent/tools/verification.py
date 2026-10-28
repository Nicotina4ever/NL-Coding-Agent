"""Verification engine for build, test, and syntax validation."""
from __future__ import annotations

import sys
from pathlib import Path
from nl_coding_agent.tools.shell import scoped_run_command


def detect_test_command(project_root: Path | str) -> str:
    """Auto-detect test command based on files present in project_root."""
    root = Path(project_root).resolve()

    # Check for embedded Python in project or parent
    embedded_py = root / "python" / "python.exe"
    if not embedded_py.exists():
        embedded_py = Path(sys.executable)

    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or (root / "tests").is_dir():
        return f'"{embedded_py}" -m pytest'
    if (root / "Cargo.toml").exists():
        return "cargo test"
    if (root / "package.json").exists():
        return "npm test"
    if (root / "CMakeLists.txt").exists():
        return "ctest"
    return f'"{embedded_py}" -m pytest'


def run_verification(
    project_root: Path | str,
    command: str | None = None,
    timeout: int = 120,
) -> dict:
    """
    Run verification tests on project_root.
    Returns:
        {
            "passed": bool,
            "exit_code": int,
            "stdout": str,
            "stderr": str,
            "command": str,
            "duration_s": float,
        }
    """
    cmd = command or detect_test_command(project_root)
    res = scoped_run_command(project_root, cmd, timeout=timeout)
    passed = (res["returncode"] == 0)

    return {
        "passed": passed,
        "exit_code": res["returncode"],
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "command": cmd,
        "duration_s": res["duration_s"],
    }

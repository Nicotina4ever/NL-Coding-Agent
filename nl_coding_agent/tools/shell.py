"""Project-scoped shell execution tool."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path


def scoped_run_command(
    project_root: Path | str,
    command: str,
    timeout: int = 60,
    env: dict | None = None,
) -> dict:
    """
    Execute a shell command with the current working directory set to project_root.
    Returns:
        {
            "returncode": int,
            "stdout": str,
            "stderr": str,
            "duration_s": float,
            "timed_out": bool,
        }
    """
    root = Path(project_root).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Invalid project root: {root}")

    start_time = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=str(root),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        duration = round(time.time() - start_time, 3)
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_s": duration,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        duration = round(time.time() - start_time, 3)
        stdout = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", errors="replace") if e.stdout else "")
        stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", errors="replace") if e.stderr else "")
        return {
            "returncode": -1,
            "stdout": stdout,
            "stderr": (stderr + f"\n[Command timed out after {timeout}s]").strip(),
            "duration_s": duration,
            "timed_out": True,
        }
    except Exception as e:
        duration = round(time.time() - start_time, 3)
        return {
            "returncode": -2,
            "stdout": "",
            "stderr": str(e),
            "duration_s": duration,
            "timed_out": False,
        }

"""Project-scoped shell execution tool."""
from __future__ import annotations

import locale
import os
import subprocess
import time
from pathlib import Path

_UTF8_CHILD_ENV = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "NO_COLOR": "1",
    "GIT_PAGER": "cat",
    "PAGER": "cat",
}


def _windows_oem_encoding() -> str | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except Exception:
        return None


def decode_output(data: bytes | None) -> str:
    """Decode console bytes using UTF-8, then the Windows OEM code page, then locale."""
    if not data:
        return ""
    if isinstance(data, str):
        return data

    candidates = ["utf-8", _windows_oem_encoding(), locale.getpreferredencoding(False), "cp1252"]
    seen: set[str] = set()
    for encoding in candidates:
        if not encoding or encoding.lower() in seen:
            continue
        seen.add(encoding.lower())
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _build_env(env: dict | None) -> dict[str, str]:
    merged = dict(os.environ)
    for key, value in _UTF8_CHILD_ENV.items():
        merged.setdefault(key, value)
    if env:
        merged.update({str(k): str(v) for k, v in env.items()})
    return merged


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
            text=False,
            timeout=timeout,
            env=_build_env(env),
            stdin=subprocess.DEVNULL,
        )
        duration = round(time.time() - start_time, 3)
        return {
            "returncode": proc.returncode,
            "stdout": decode_output(proc.stdout),
            "stderr": decode_output(proc.stderr),
            "duration_s": duration,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        duration = round(time.time() - start_time, 3)
        stdout = decode_output(e.stdout)
        stderr = decode_output(e.stderr)
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

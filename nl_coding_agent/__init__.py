"""NL Coding Agent package bootstrap.

Configures UTF-8 I/O before any third-party library (CrewAI/Rich) is imported.
On Windows the default console encoding is often cp1252/cp850, which cannot
encode the emoji and box-drawing characters CrewAI prints.  Doing this here is
intentional: ``nl_agent.py`` imports the package first, so the environment is
already correct when CrewAI is loaded.
"""
from __future__ import annotations

import os
import sys

_UTF8_ENV = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "NO_COLOR": "1",
}


def configure_utf8_environment() -> None:
    """Make current-process and child-process text I/O UTF-8 safe."""
    for key, value in _UTF8_ENV.items():
        os.environ.setdefault(key, value)

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


configure_utf8_environment()

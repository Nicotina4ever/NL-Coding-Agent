"""Workspace launcher for the embedded Python runtime.

The bundled embedded Python is configured with ``isolated=1`` and a ``._pth``
file, so it intentionally ignores ``PYTHONPATH`` and does not add the current
directory to ``sys.path``.  This tiny launcher adds the workspace root before
importing the CLI, which keeps ``python\\python.exe nl_agent.py <command>``
working without modifying the runtime internals.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nl_coding_agent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

"""Lightweight, per-user bootstrapper for NL Coding Agent (stage 6a foundation).

This package installs an inspectable application payload into a user-selected
directory. It never installs system-wide, never requires a global Python/pip/uv/
conda, and never executes downloaded code during installation.

Design constraints:
  * standard library only (works with any Python >= 3.10);
  * manifest-driven: platform manifest JSON lists base URLs, component ids,
    versions, sha256 and size, and per-platform runtime entries;
  * downloads are streamed through urllib with hash+size verification and atomic
    staging; a verified shared cache is reused across isolated installs;
  * offline bundles are directories containing the same manifest plus local
    artifacts, and are the supported no-network path;
  * install/update/repair never delete user data: target directories are
    application payloads only; user data belongs outside the target and is
    configured through NL_DATA_DIR by the application launchers.
"""
from __future__ import annotations

TOOL_NAME = "nl-coding-agent-bootstrapper"
TOOL_VERSION = "0.1.0"

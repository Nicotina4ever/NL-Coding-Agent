"""Read-only discovery registry for external tools (SPEC-25, NL-BP-073).

The registry is deliberately passive:

* discovery never installs, copies or modifies a tool;
* a probe runs only a fixed, read-only version command as an argv list with
  shell=False, bounded to a few seconds, or a single HTTP GET to the tool's own
  health endpoint;
* there is no public API that executes an arbitrary command string, so a model or
  planner cannot turn the registry into a shell.

Capabilities describe what a tool can do; they are not grants. A future
permission layer may hand out execute without implying write on the tool
directory (SPEC-25 acceptance gate).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from nl_coding_agent.tools.shell import decode_output

#: Hard upper bound for any single probe, in seconds (SPEC-25: non-destructive).
PROBE_TIMEOUT_S = 5.0
MAX_HTTP_BYTES = 64 * 1024
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


class ToolCapability:
    """Capability tokens used by permission grants (SPEC-25 capability table)."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    NETWORK = "network"
    INSTALL = "install"
    SECRETS = "secrets"
    CLOUD = "cloud"

    ALL = frozenset({
        READ, WRITE, EXECUTE, DELETE, NETWORK, INSTALL, SECRETS, CLOUD,
    })

    @classmethod
    def normalize(cls, values: Iterable[str] | None) -> tuple[str, ...]:
        """Validate and de-duplicate capability tokens, preserving order."""
        normalized: list[str] = []
        for value in values or ():
            token = str(value).strip().lower()
            if token not in cls.ALL:
                raise ValueError(f"Unknown tool capability: {value!r}")
            if token not in normalized:
                normalized.append(token)
        return tuple(normalized)


@dataclass(frozen=True)
class ExternalTool:
    """Descriptor for a discoverable executable or HTTP endpoint.

    probe_argv is the complete argument vector of the read-only version command
    (element 0 is the executable). probe_url is an optional health endpoint used
    when the executable is not installed.
    """

    tool_id: str
    display_name: str
    kind: str = "executable"  # "executable" | "endpoint"
    executable: str | None = None
    endpoint: str | None = None
    probe_argv: tuple[str, ...] = ()
    probe_url: str | None = None
    platform: str = field(default_factory=lambda: sys.platform)
    owner: str = "nl_coding_agent"
    capabilities: tuple[str, ...] = ()
    description: str = ""
    env_policy: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.tool_id).strip():
            raise ValueError("ExternalTool requires a non-empty tool_id")
        if self.kind not in ("executable", "endpoint"):
            raise ValueError(f"Unsupported tool kind: {self.kind!r}")
        if self.kind == "executable" and not self.executable:
            raise ValueError(f"Executable tool {self.tool_id!r} requires executable")
        object.__setattr__(self, "capabilities", ToolCapability.normalize(self.capabilities))
        object.__setattr__(self, "probe_argv", tuple(self.probe_argv or ()))
        object.__setattr__(self, "env_policy", dict(self.env_policy or {}))

    def describe(self) -> dict:
        """Return a JSON-safe descriptor (no probe performed)."""
        return {
            "tool_id": self.tool_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "executable": self.executable,
            "endpoint": self.endpoint,
            "platform": self.platform,
            "owner": self.owner,
            "capabilities": list(self.capabilities),
            "description": self.description,
            "probe_argv": list(self.probe_argv),
            "probe_url": self.probe_url,
            "env_policy": dict(self.env_policy),
        }


def builtin_tools(
    *,
    python_executable: str | None = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> list[ExternalTool]:
    """Descriptors for the builtin tools discoverable without user setup."""
    python = str(python_executable or sys.executable)
    return [
        ExternalTool(
            tool_id="git",
            display_name="Git",
            executable="git",
            probe_argv=("git", "--version"),
            capabilities=(
                ToolCapability.READ,
                ToolCapability.WRITE,
                ToolCapability.EXECUTE,
            ),
            description="Version control executable used for read-only diff/status inspection.",
        ),
        ExternalTool(
            tool_id="python",
            display_name="Embedded Python",
            executable=python,
            probe_argv=(python, "--version"),
            capabilities=(
                ToolCapability.READ,
                ToolCapability.WRITE,
                ToolCapability.EXECUTE,
            ),
            description="Application-owned Python runtime used for verification subprocesses.",
        ),
        ExternalTool(
            tool_id="pytest",
            display_name="pytest",
            executable=python,
            probe_argv=(python, "-m", "pytest", "--version"),
            capabilities=(ToolCapability.EXECUTE,),
            description="Test runner used by the independent candidate/oracle verification.",
        ),
        ExternalTool(
            tool_id="ollama",
            display_name="Ollama",
            kind="endpoint",
            executable="ollama",
            endpoint=str(ollama_url).rstrip("/") + "/api/tags",
            probe_argv=("ollama", "--version"),
            probe_url=str(ollama_url).rstrip("/") + "/api/tags",
            capabilities=(ToolCapability.EXECUTE, ToolCapability.NETWORK),
            description="Local model runtime; probed through the CLI or the read-only /api/tags endpoint.",
        ),
        ExternalTool(
            tool_id="ffmpeg",
            display_name="FFmpeg",
            executable="ffmpeg",
            probe_argv=("ffmpeg", "-version"),
            capabilities=(
                ToolCapability.READ,
                ToolCapability.WRITE,
                ToolCapability.EXECUTE,
            ),
            description="Media transcoder; discovery only, never invoked by mission agents.",
        ),
    ]


def _resolve_executable(executable: str | None) -> str | None:
    if not executable:
        return None
    candidate = Path(executable)
    if candidate.is_absolute():
        return str(candidate) if candidate.is_file() else None
    return shutil.which(executable)


def _resolved_argv(tool: ExternalTool) -> tuple[str | None, list[str]]:
    argv = list(tool.probe_argv)
    resolved = _resolve_executable(tool.executable)
    if resolved and argv and not Path(argv[0]).is_absolute():
        argv[0] = resolved
    return resolved, argv


def _parse_version(text: str) -> str | None:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:300]
    return None


def _probe_http(url: str, timeout: float) -> tuple[bool, str | None]:
    """Single bounded GET; returns (reachable, error)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            response.read(MAX_HTTP_BYTES)
        if 200 <= status < 300:
            return True, None
        return False, f"HTTP {status}"
    except Exception as exc:  # noqa: BLE001 - probe failure is data, not a crash
        return False, str(exc)


class ToolRegistry:
    """In-memory registry of known external tools with safe probes.

    The registry never accepts a command string: probes are derived only from the
    registered ExternalTool descriptor.
    """

    def __init__(
        self,
        tools: Iterable[ExternalTool] | None = None,
        *,
        probe_timeout_s: float = PROBE_TIMEOUT_S,
    ) -> None:
        selected = builtin_tools() if tools is None else list(tools)
        self.probe_timeout_s = min(max(float(probe_timeout_s), 0.1), PROBE_TIMEOUT_S)
        self._tools: dict[str, ExternalTool] = {}
        for tool in selected:
            if tool.tool_id in self._tools:
                raise ValueError(f"Duplicate tool_id in registry: {tool.tool_id!r}")
            self._tools[tool.tool_id] = tool

    # ------------------------------------------------------------------ catalog

    def tools(self) -> list[ExternalTool]:
        return list(self._tools.values())

    def get(self, tool_id: str) -> ExternalTool | None:
        return self._tools.get(str(tool_id))

    def describe(self, tool_id: str) -> dict:
        return self._require(tool_id).describe()

    def describe_all(self, *, probe: bool = True) -> list[dict]:
        items: list[dict] = []
        for tool in self._tools.values():
            item = tool.describe()
            if probe:
                item["probe"] = self.probe(tool.tool_id)
            items.append(item)
        return items

    def find(
        self,
        query: str | None = None,
        *,
        capability: str | None = None,
    ) -> list[ExternalTool]:
        """Case-insensitive substring search over id/display/description."""
        needle = str(query or "").strip().lower()
        wanted = str(capability).strip().lower() if capability else None
        matches: list[ExternalTool] = []
        for tool in self._tools.values():
            if wanted and wanted not in tool.capabilities:
                continue
            haystack = " ".join(
                (tool.tool_id, tool.display_name, tool.description)
            ).lower()
            if needle and needle not in haystack:
                continue
            matches.append(tool)
        return matches

    # ------------------------------------------------------------------- probes

    def probe(self, tool_id: str) -> dict:
        tool = self._require(tool_id)
        started = time.monotonic()
        result: dict = {
            "tool_id": tool.tool_id,
            "display_name": tool.display_name,
            "available": False,
            "version": None,
            "path": None,
            "endpoint_reachable": None,
            "duration_s": 0.0,
            "error": None,
        }

        if tool.executable:
            resolved, argv = _resolved_argv(tool)
            result["path"] = resolved
            if resolved is None:
                result["error"] = f"{tool.executable} not found on PATH"
            elif tool.probe_argv:
                try:
                    proc = subprocess.run(
                        argv,
                        shell=False,
                        capture_output=True,
                        text=False,
                        timeout=self.probe_timeout_s,
                        stdin=subprocess.DEVNULL,
                        check=False,
                    )
                    stdout = decode_output(proc.stdout)
                    stderr = decode_output(proc.stderr)
                    result["version"] = _parse_version(stdout or stderr)
                    result["available"] = int(proc.returncode) == 0
                    if not result["available"]:
                        result["error"] = (
                            f"probe exit {proc.returncode}: {stderr.strip()[:300]}"
                        )
                except FileNotFoundError:
                    result["error"] = f"{tool.executable} not found on PATH"
                except subprocess.TimeoutExpired:
                    result["error"] = (
                        f"probe timed out after {self.probe_timeout_s:g}s"
                    )
                except OSError as exc:
                    result["error"] = f"probe failed: {exc}"

        if tool.probe_url:
            reachable, http_error = _probe_http(tool.probe_url, self.probe_timeout_s)
            result["endpoint_reachable"] = reachable
            if reachable:
                result["available"] = True
                if result["version"] is None:
                    result["version"] = "http-api"
                result["error"] = None
            elif http_error:
                if result["error"]:
                    result["error"] = result["error"] + "; endpoint: " + http_error
                else:
                    result["error"] = http_error

        result["duration_s"] = round(time.monotonic() - started, 3)
        return result

    def probe_all(self) -> list[dict]:
        return [self.probe(tool.tool_id) for tool in self._tools.values()]

    # ------------------------------------------------------------------ helpers

    def _require(self, tool_id: str) -> ExternalTool:
        tool = self._tools.get(str(tool_id))
        if tool is None:
            raise KeyError(f"Unknown external tool: {tool_id!r}")
        return tool

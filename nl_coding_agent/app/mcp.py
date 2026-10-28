"""F3b: local stdio MCP configuration, read-only tool discovery, gated invocation.

No auto-execution and no network: discovery/invocation only when the caller explicitly
requests them, tool calls require explicit human approval, and a server declared as
network-capable additionally requires the NETWORK permission grant. Config is local
JSON only; unavailable/invalid configuration fails closed with clear codes.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from nl_coding_agent.persistence import database

__all__ = ["McpError", "McpServerSpec", "load_mcp_config", "discover_servers",
           "McpClient", "McpManager"]


class McpError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class McpServerSpec:
    name: str
    command: str
    args: tuple[str, ...]
    env: dict
    network: bool
    source: str

    def to_dict(self) -> dict:
        return {"name": self.name, "command": self.command, "args": list(self.args),
                "network": self.network, "source": self.source}


def load_mcp_config(path: str | Path | None = None) -> dict:
    import os
    candidates = []
    if path is not None:
        candidates = [Path(path)]
    else:
        env_path = os.environ.get("NL_MCP_CONFIG", "").strip()
        if env_path:
            candidates.append(Path(env_path))
        candidates.extend([database.data_root() / "mcp_servers.json",
                           Path("config") / "mcp_servers.json"])
    for candidate in candidates:
        if candidate.is_file():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise McpError("config-invalid", "MCP config is not valid JSON: " + str(exc)) from exc
            if not isinstance(payload, dict):
                raise McpError("config-invalid", "MCP config must be a JSON object.")
            return payload
    return {"servers": {}}


def discover_servers(config: dict | None = None) -> list[McpServerSpec]:
    payload = config if config is not None else load_mcp_config()
    raw = payload.get("servers", payload) if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        raise McpError("config-invalid", "MCP servers must be a mapping.")
    servers = []
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise McpError("config-invalid", "MCP server entry must be an object: " + str(name))
        transport = str(entry.get("transport") or "stdio").lower()
        if transport != "stdio":
            raise McpError("unsupported-transport",
                           "Only local stdio MCP servers are supported (got "
                           + repr(transport) + ").")
        command = str(entry.get("command") or "").strip()
        if not command:
            raise McpError("config-invalid", "MCP server command is required: " + str(name))
        servers.append(McpServerSpec(
            str(name), command, tuple(str(a) for a in (entry.get("args") or ())),
            dict(entry.get("env") or {}), bool(entry.get("network")),
            str(entry.get("source") or "local-config")))
    return servers


class _StdioTransport:
    def __init__(self, server: McpServerSpec) -> None:
        import os
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in server.env.items()})
        self._process = subprocess.Popen(
            [server.command, *server.args], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, shell=False)
        self._queue = queue.Queue()
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        buffer = b""
        while True:
            chunk = self._process.stdout.read(4096) if self._process.stdout else b""
            if not chunk:
                return
            buffer += chunk
            while True:
                marker = buffer.find(b"\r\n\r\n")
                if marker < 0:
                    break
                length = None
                for line in buffer[:marker].decode("ascii", "replace").splitlines():
                    if line.lower().startswith("content-length:"):
                        length = int(line.split(":", 1)[1])
                if length is None or len(buffer) < marker + 4 + length:
                    break
                body = buffer[marker + 4:marker + 4 + length]
                try:
                    self._queue.put(json.loads(body.decode("utf-8")))
                except ValueError:
                    pass
                buffer = buffer[marker + 4 + length:]

    def send(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._process.stdin.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        self._process.stdin.flush()

    def receive(self, timeout: float) -> dict:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise McpError("timeout", "MCP server did not answer in time") from exc

    def close(self):
        try:
            self._process.terminate()
            self._process.wait(timeout=3)
        except Exception:
            pass


class McpClient:
    def __init__(self, server: McpServerSpec, *, transport=None, timeout: float = 5.0):
        self.server = server
        self.timeout = float(timeout)
        self._transport = transport
        self._next_id = 1

    def _send(self, payload):
        if self._transport is None:
            self._transport = _StdioTransport(self.server)
        self._transport.send(payload)

    def _request(self, method: str, params: dict | None = None) -> dict:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method,
                    "params": params or {}})
        while True:
            message = self._transport.receive(self.timeout)
            if message.get("id") == request_id:
                if "error" in message:
                    raise McpError("rpc-error", str(message["error"]))
                return dict(message.get("result") or {})

    def initialize(self) -> dict:
        result = self._request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "NL Coding Agent", "version": "1.0"},
        })
        return result

    def list_tools(self) -> list[dict]:
        result = self._request("tools/list")
        tools = result.get("tools") or []
        return [{"name": str(item.get("name") or ""),
                 "description": str(item.get("description") or ""),
                 "input_schema": item.get("inputSchema") or {}}
                for item in tools if isinstance(item, dict)]

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self._request("tools/call", {"name": str(name),
                                            "arguments": dict(arguments or {})})

    def close(self):
        if self._transport is not None and hasattr(self._transport, "close"):
            self._transport.close()
        self._transport = None


class McpManager:
    def __init__(self, project_id: int | None = None, *, config=None,
                 config_loader=None, transport_factory=None):
        self.project_id = int(project_id) if project_id is not None else None
        self._config = config
        self._loader = config_loader or load_mcp_config
        self._factory = transport_factory
        self._clients: dict[str, McpClient] = {}

    def servers(self) -> list[dict]:
        return [server.to_dict() for server in discover_servers(
            self._config if self._config is not None else self._loader())]

    def _server(self, name: str) -> McpServerSpec:
        for server in discover_servers(self._config if self._config is not None else self._loader()):
            if server.name == name:
                return server
        raise McpError("server-not-found", "MCP server is not configured: " + repr(name))

    def list_tools(self, server_name: str) -> list[dict]:
        server = self._server(server_name)
        transport = self._factory(server) if self._factory else None
        client = McpClient(server, transport=transport)
        try:
            client.initialize()
            return client.list_tools()
        finally:
            client.close()

    def invoke_tool(self, server_name: str, tool_name: str, arguments: dict | None = None, *,
                    human_approved: bool = False) -> dict:
        import json
        from nl_coding_agent.core import permissions
        if not human_approved:
            raise McpError("human-approval-required",
                           "MCP tool invocation requires explicit human approval.")
        server = self._server(server_name)
        if server.network and not permissions.get_policy(self.project_id).get(permissions.NETWORK):
            raise McpError("network-denied",
                           "MCP server " + repr(server_name)
                           + " declares network use and no NETWORK grant exists.")
        try:
            database.log_event(
                database.init_db(), "MCP tool invocation approved: "
                + server_name + "/" + tool_name, source="mcp", event_kind="mcp-invoke",
                payload=json.dumps({"server": server_name, "tool": tool_name,
                                    "project_id": self.project_id}))
        except Exception:
            pass
        transport = self._factory(server) if self._factory else None
        client = McpClient(server, transport=transport)
        try:
            client.initialize()
            return client.call_tool(tool_name, arguments or {})
        finally:
            client.close()

    def close(self):
        for client in self._clients.values():
            client.close()
        self._clients.clear()

"""F3b: local stdio MCP configuration, read-only tool discovery, gated invocation.

Explicit trusted-server discovery and approved calls through the official SDK.
Stdio process startup requires EXECUTE/READ; HTTP and network-capable servers require
NETWORK, remote HTTP additionally CLOUD. Local process trust is not an OS sandbox.
Tool annotations and results never authorize execution or candidate promotion.
"""
from __future__ import annotations

import json
import queue
import re
from contextlib import asynccontextmanager, AsyncExitStack, closing
from datetime import timedelta
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
    transport: str = "stdio"
    url: str = ""
    enabled: bool = True
    trusted: bool = False
    timeout: float = 10.0
    cwd: str | None = None
    allowed_tools: tuple[str, ...] | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "command": self.command, "args": list(self.args),
                "network": self.network, "source": self.source,
                "transport": self.transport, "url": self.url,
                "enabled": self.enabled, "trusted": self.trusted}


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
                           Path(__file__).resolve().parents[2] / "config" / "mcp_servers.json"])
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
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", str(name)):
            raise McpError("config-invalid", "MCP server name must be a namespace identifier")
        transport = str(entry.get("transport") or "stdio").lower()
        if transport == "streamable-http":
            transport = "http"
        if transport not in ("stdio", "http"):
            raise McpError("unsupported-transport", "Supported transports: stdio, streamable-http")
        command = str(entry.get("command") or "").strip()
        url = str(entry.get("url") or "").strip()
        if transport == "stdio" and not command:
            raise McpError("config-invalid", "MCP server command is required: " + str(name))
        if transport == "http":
            from urllib.parse import urlsplit
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise McpError("config-invalid", "MCP HTTP endpoint must be an http(s) URL without embedded credentials")
        args = entry.get("args") or []
        if not isinstance(args, (list, tuple)) or not isinstance(entry.get("env") or {}, dict):
            raise McpError("config-invalid", "MCP args must be a list and env an object")
        try:
            timeout = float(entry.get("timeout", 10))
            if not 0 < timeout < float("inf"):
                raise ValueError()
        except (TypeError, ValueError):
            raise McpError("config-invalid", "MCP timeout must be finite and positive") from None
        allowed = entry.get("allowed_tools")
        if allowed is not None and (not isinstance(allowed, list) or not all(isinstance(t, str) for t in allowed)):
            raise McpError("config-invalid", "allowed_tools must be a list of exact names")
        servers.append(McpServerSpec(
            str(name), command, tuple(str(a) for a in args),
            dict(entry.get("env") or {}), bool(entry.get("network")),
            str(entry.get("source") or "local-config"), transport, url,
            entry.get("enabled", True) is True, entry.get("trusted", False) is True,
            timeout, str(entry["cwd"]) if entry.get("cwd") else None,
            tuple(allowed) if allowed is not None else None))
    return servers


@asynccontextmanager
async def _sdk_session(server):
    # The official SDK owns framing, initialized notification and lifecycle.
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        raise McpError("sdk-unavailable", "Install the optional mcp dependency in the dedicated runtime") from exc
    from nl_coding_agent.core.workspace import logs_root
    from uuid import uuid4
    log_path = logs_root() / "mcp" / (server.name + "-" + uuid4().hex + ".stderr.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncExitStack() as stack:
        if server.transport == "http":
            import httpx
            http_client = await stack.enter_async_context(httpx.AsyncClient(timeout=server.timeout))
            streams = await stack.enter_async_context(streamable_http_client(
                server.url, http_client=http_client))
        else:
            errlog = stack.enter_context(log_path.open("w", encoding="utf-8"))
            parameters = StdioServerParameters(command=server.command, args=list(server.args),
                env=server.env, cwd=server.cwd or str(Path(__file__).resolve().parents[2]))
            streams = await stack.enter_async_context(stdio_client(parameters, errlog=errlog))
        session = await stack.enter_async_context(ClientSession(
            streams[0], streams[1], read_timeout_seconds=timedelta(seconds=server.timeout)))
        yield session


def _connection_error(exc):
    leaf = exc
    while isinstance(leaf, BaseExceptionGroup) and leaf.exceptions:
        leaf = leaf.exceptions[0]
    if isinstance(leaf, McpError):
        return leaf
    return McpError("timeout" if isinstance(leaf, TimeoutError) else "connection-failed",
                    type(leaf).__name__ + ": " + str(leaf))


class _SdkTransport:
    """Compatibility adapter from the existing sync client to official SDK sessions.

    A blocking portal keeps the async context in one task until close. It supports
    stdio and Streamable HTTP; no hand-written wire protocol remains in production.
    """
    def __init__(self, server):
        from anyio.from_thread import start_blocking_portal
        self.server = server
        self._queue = queue.Queue()
        self._portal_owner = start_blocking_portal()
        self._portal = self._portal_owner.__enter__()
        self._session_owner = self._portal.wrap_async_context_manager(_sdk_session(server))
        try:
            self._session = self._session_owner.__enter__()
        except BaseException as exc:
            self._portal_owner.__exit__(None, None, None)
            if isinstance(exc, Exception):
                raise _connection_error(exc) from exc
            raise

    def send(self, payload):
        async def operation():
            import anyio
            from pydantic import AnyUrl
            method, params = payload["method"], payload.get("params") or {}
            with anyio.fail_after(self.server.timeout):
                if method == "initialize":
                    result = await self._session.initialize()
                elif method == "tools/list":
                    result = await self._session.list_tools(cursor=params.get("cursor"))
                elif method == "tools/call":
                    result = await self._session.call_tool(params["name"], params.get("arguments") or {})
                elif method == "resources/list":
                    result = await self._session.list_resources(cursor=params.get("cursor"))
                elif method == "resources/read":
                    result = await self._session.read_resource(AnyUrl(params["uri"]))
                else:
                    raise McpError("unsupported-method", "Unsupported MCP method: " + method)
                return result.model_dump(mode="json", exclude_none=True)
        try:
            result = self._portal.call(operation)
        except Exception as exc:
            raise _connection_error(exc) from exc
        self._queue.put({"jsonrpc": "2.0", "id": payload["id"], "result": result})

    def receive(self, timeout):
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise McpError("timeout", "MCP server did not answer in time") from exc

    def close(self):
        try:
            self._session_owner.__exit__(None, None, None)
        finally:
            self._portal_owner.__exit__(None, None, None)


class McpClient:
    def __init__(self, server: McpServerSpec, *, transport=None, timeout: float = 5.0):
        self.server = server
        self.timeout = float(server.timeout if timeout == 5.0 else timeout)
        self._transport = transport
        self._next_id = 1

    def _send(self, payload):
        if self._transport is None:
            self._transport = _SdkTransport(self.server)
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

    def _list(self, method, key):
        items, cursor, seen = [], None, set()
        while True:
            result = self._request(method, {"cursor": cursor} if cursor else {})
            items.extend(result.get(key) or [])
            cursor = result.get("nextCursor")
            if not cursor:
                return items
            if cursor in seen:
                raise McpError("pagination-cycle", "MCP server repeated its page cursor")
            seen.add(cursor)

    def list_tools(self) -> list[dict]:
        return [{"name": str(item.get("name") or ""),
                 "description": str(item.get("description") or ""),
                 "input_schema": item.get("inputSchema") or {}}
                for item in self._list("tools/list", "tools") if isinstance(item, dict)]

    def list_resources(self):
        return self._list("resources/list", "resources")

    def read_resource(self, uri):
        return self._request("resources/read", {"uri": str(uri)})

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

    def _gate(self, server):
        from nl_coding_agent.core import permissions
        if not server.enabled:
            raise McpError("server-disabled", "MCP server is disabled: " + server.name)
        if not server.trusted:
            raise McpError("server-untrusted", "Explicitly trust the configured server before starting it")
        permissions.require(permissions.EXECUTE, project_id=self.project_id)
        permissions.require(permissions.READ, project_id=self.project_id)
        if server.network or server.transport == "http":
            if not permissions.get_policy(self.project_id).get(permissions.NETWORK):
                raise McpError("network-denied", "MCP connection requires the project's NETWORK grant")
        if server.transport == "http" and permissions.is_remote_endpoint(server.url):
            permissions.require(permissions.CLOUD, project_id=self.project_id)

    def _audit(self, server, operation, *, ok, tool=None, arguments=None, error=None):
        import hashlib
        payload = {"server": server.name, "operation": operation, "tool": tool,
                   "project_id": self.project_id, "ok": ok,
                   "arguments_sha256": hashlib.sha256(json.dumps(arguments or {}, sort_keys=True).encode()).hexdigest(),
                   "error_code": getattr(error, "code", type(error).__name__) if error else None}
        with closing(database.init_db()) as conn:
            database.log_event(conn, "MCP " + operation + ": " + server.name + ("/" + tool if tool else ""),
                source="mcp", level="info" if ok else "error", event_kind="mcp-" + operation,
                project_id=self.project_id, payload=json.dumps(payload))

    def _operate(self, server_name, operation, callback, *, tool=None, arguments=None):
        server = self._server(server_name)
        self._gate(server)  # Before process startup, discovery or HTTP connection.
        transport = self._factory(server) if self._factory else None
        client = McpClient(server, transport=transport)
        self._audit(server, operation + "-start", ok=True, tool=tool, arguments=arguments)
        try:
            client.initialize()
            result = callback(client, server)
            self._audit(server, operation, ok=True, tool=tool, arguments=arguments)
            return result
        except Exception as exc:
            self._audit(server, operation, ok=False, tool=tool, arguments=arguments, error=exc)
            raise
        finally:
            client.close()

    def list_tools(self, server_name: str) -> list[dict]:
        def discover(client, server):
            return [{**tool, "qualified_name": server.name + "::" + tool["name"]}
                    for tool in client.list_tools()
                    if server.allowed_tools is None or tool["name"] in server.allowed_tools]
        return self._operate(server_name, "discover-tools", discover)

    def list_resources(self, server_name):
        return self._operate(server_name, "discover-resources", lambda client, server:
            [{**item, "server": server.name} for item in client.list_resources()])

    @staticmethod
    def _validate_arguments(schema, arguments):
        from jsonschema.validators import validator_for
        from referencing import Registry
        from referencing.exceptions import NoSuchResource
        def no_remote_schema(uri):
            raise NoSuchResource(ref=uri)
        try:
            validator = validator_for(schema)
            validator.check_schema(schema)
            validator(schema, registry=Registry(retrieve=no_remote_schema)).validate(arguments)
        except Exception as exc:
            raise McpError("arguments-invalid", "Arguments do not match the advertised local schema: " + str(exc)) from exc

    def invoke_tool(self, server_name: str, tool_name: str, arguments: dict | None = None, *,
                    human_approved: bool = False) -> dict:
        from nl_coding_agent.core import permissions
        if not human_approved:
            raise McpError("human-approval-required", "MCP tool invocation requires explicit human approval")
        # A server's annotations cannot prove that a tool is harmless.
        permissions.require(permissions.WRITE, project_id=self.project_id)
        if "::" in tool_name:
            namespace, tool_name = tool_name.split("::", 1)
            if namespace != server_name:
                raise McpError("namespace-mismatch", "Tool belongs to another server")
        def invoke(client, server):
            tools = {tool["name"]: tool for tool in client.list_tools()}
            if tool_name not in tools or (server.allowed_tools is not None and tool_name not in server.allowed_tools):
                raise McpError("tool-denied", "Tool is not advertised or explicitly allowed")
            self._validate_arguments(tools[tool_name]["input_schema"], arguments or {})
            self._gate(server)  # Policy may have changed during discovery.
            permissions.require(permissions.WRITE, project_id=self.project_id)
            result = client.call_tool(tool_name, arguments or {})
            # Tool annotations/results never grant permission or authorize promotion.
            return {**result, "server": server.name, "qualified_name": server.name + "::" + tool_name,
                    "untrusted": True}
        return self._operate(server_name, "invoke", invoke, tool=tool_name, arguments=arguments)

    def read_resource(self, server_name, uri, *, human_approved=False):
        if not human_approved:
            raise McpError("human-approval-required", "Resource reads require explicit approval")
        def read(client, server):
            if uri not in {str(item.get("uri")) for item in client.list_resources()}:
                raise McpError("resource-denied", "Resource was not advertised by the selected server")
            self._gate(server)
            return {**client.read_resource(uri), "server": server.name, "untrusted": True}
        return self._operate(server_name, "read-resource", read, arguments={"uri": uri})

    def close(self):
        for client in self._clients.values():
            client.close()
        self._clients.clear()

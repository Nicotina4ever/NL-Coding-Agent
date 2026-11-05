"""F3b MCP: local config, fake-transport discovery and permission-gated invocation."""
from __future__ import annotations
import json
import pytest

from nl_coding_agent.app import mcp
from nl_coding_agent.core import permissions
from nl_coding_agent.persistence import database


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    database.init_db().close()


class FakeMcpTransport:
    def __init__(self, tools=None, tool_result=None):
        self.sent = []
        self.tools = tools or [{"name": "read_file", "description": "Read a file",
                                "inputSchema": {"type": "object"}}]
        self.tool_result = tool_result or {"content": [{"type": "text", "text": "ok"}]}

    def send(self, payload):
        self.sent.append(payload)
        if payload.get("method") == "initialize":
            self._reply = {"jsonrpc": "2.0", "id": payload["id"],
                           "result": {"protocolVersion": "2024-11-05"}}
        elif payload.get("method") == "tools/list":
            self._reply = {"jsonrpc": "2.0", "id": payload["id"],
                           "result": {"tools": self.tools}}
        elif payload.get("method") == "tools/call":
            self._reply = {"jsonrpc": "2.0", "id": payload["id"],
                           "result": self.tool_result}

    def receive(self, timeout):
        return self._reply

    def close(self):
        pass


def test_config_validation_and_discovery(tmp_path):
    config = {"servers": {"files": {"command": "mcp-files", "args": ["--root", "."]}}}
    servers = mcp.discover_servers(config)
    assert servers[0].name == "files" and servers[0].network is False
    assert servers[0].to_dict()["args"] == ["--root", "."]
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    loaded = mcp.load_mcp_config(path)
    assert "servers" in loaded
    with pytest.raises(mcp.McpError) as bad:
        mcp.discover_servers({"servers": {"x": {"command": ""}}})
    assert bad.value.code == "config-invalid"
    with pytest.raises(mcp.McpError):
        mcp.discover_servers({"servers": {"x": {"command": "x", "transport": "http"}}})
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(mcp.McpError):
        mcp.load_mcp_config(path)


def test_tool_listing_and_gated_invocation_with_fake_transport():
    config = {"servers": {"files": {"command": "mcp-files", "trusted": True}}}
    tools = []
    transports = []

    def factory(server):
        transport = FakeMcpTransport()
        transports.append(transport)
        return transport

    manager = mcp.McpManager(config=config, transport_factory=factory)
    listed = manager.list_tools("files")
    assert listed[0]["name"] == "read_file"
    assert manager.invoke_tool("files", "read_file", {"path": "x"})["content"][0]["text"] == "ok"
    permissions.set_access_mode("read-only")
    with pytest.raises(permissions.PermissionDenied):
        manager.invoke_tool("files", "read_file", {"path": "x"}, human_approved=True)
    permissions.set_access_mode("workspace-write")
    result = manager.invoke_tool("files", "read_file", {"path": "x"}, human_approved=True)
    assert result["content"][0]["text"] == "ok"
    assert any(payload.get("method") == "tools/call"
               for payload in transports[-1].sent)


def test_network_server_requires_grant(tmp_path, monkeypatch):
    config = {"servers": {"remote": {"command": "mcp-remote", "network": True, "trusted": True}}}
    transports = []
    manager = mcp.McpManager(config=config,
                             transport_factory=lambda server: transports.append(FakeMcpTransport()) or FakeMcpTransport())
    with pytest.raises(mcp.McpError) as denied:
        manager.invoke_tool("remote", "read_file", {}, human_approved=True)
    assert denied.value.code == "network-denied"
    assert transports == []
    monkeypatch.setattr(permissions, "get_policy", lambda pid=None: {
        "read": True, "write": True, "execute": True, "delete": False,
        "network": True, "cloud": False})
    result = manager.invoke_tool("remote", "read_file", {}, human_approved=True)
    assert result["content"][0]["text"] == "ok"

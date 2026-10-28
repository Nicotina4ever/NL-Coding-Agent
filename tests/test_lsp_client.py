"""F3b LSP: detection, framing, fake-transport requests and diagnostics."""
from __future__ import annotations
import json
import pytest

from nl_coding_agent.app import lsp


class FakeTransport:
    def __init__(self, replies=None):
        self.sent = []
        self.replies = list(replies or [])

    def send(self, payload):
        self.sent.append(payload)
        if payload.get("method") == "initialize":
            self.replies.insert(0, {"jsonrpc": "2.0", "id": payload["id"],
                                    "result": {"capabilities": {}}})
        elif payload.get("method") == "textDocument/hover":
            self.replies.insert(0, {"jsonrpc": "2.0", "id": payload["id"],
                                    "result": {"contents": "hover text"}})

    def receive(self, timeout):
        if self.replies:
            return self.replies.pop(0)
        raise lsp.LspError("timeout", "no message")

    def close(self):
        pass


def test_framing_round_trip_and_catalog_detection(tmp_path):
    encoded = lsp.encode_message({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    messages, rest = lsp.decode_messages(encoded + b"Content-Len")
    assert messages == [{"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}]
    seen = []

    def fake_which(command):
        seen.append(command)
        return "/usr/bin/" + command if command == "pylsp" else None

    servers = lsp.detect_language_servers(which=fake_which)
    assert any(server.server_id == "pylsp" and server.available for server in servers)
    assert any(server.server_id == "clangd" and not server.available for server in servers)


def test_client_initialize_hover_and_diagnostics(tmp_path):
    transport = FakeTransport()
    server = lsp.LspServerSpec("pylsp", "pylsp", (), ("python",), True)
    client = lsp.LspClient(server, tmp_path, transport=transport)
    assert client.initialize() == {"capabilities": {}}
    assert transport.sent[0]["method"] == "initialize"
    assert transport.sent[1]["method"] == "initialized"
    # a diagnostics notification and then a hover response
    transport.replies.extend([
        {"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
         "params": {"uri": "file:///p/app.py", "diagnostics": [
             {"severity": 1, "message": "undefined name", "range": {"start": {"line": 4}}}]}},
        {"jsonrpc": "2.0", "id": 99, "result": {"contents": "hover text"}},
    ])
    transport.sent.append({"jsonrpc": "2.0", "id": 99, "method": "textDocument/hover"})
    diagnostics = client.diagnostics()
    assert diagnostics["file:///p/app.py"][0]["message"] == "undefined name"
    assert diagnostics["file:///p/app.py"][0]["line"] == 5
    result = client.hover("app.py", 5, 1)
    assert result["contents"] == "hover text"
    with pytest.raises(lsp.LspError):
        client._uri("../escape.py")


def test_manager_fail_closed_and_explicit_start(tmp_path):
    manager = lsp.LspManager(
        tmp_path, detector=lambda: [lsp.LspServerSpec(
            "pylsp", "pylsp", (), ("python",), True)],
        transport_factory=lambda server: FakeTransport())
    started = manager.start("python")
    assert started["started"] is True
    assert manager.diagnostics("python") == {}
    missing = lsp.LspManager(tmp_path, detector=lambda: [lsp.LspServerSpec(
        "pylsp", "pylsp", (), ("python",), False)])
    with pytest.raises(lsp.LspError) as caught:
        missing.start("python")
    assert caught.value.code == "server-unavailable"


def test_manager_fake_transport_initializes_without_real_server(tmp_path):
    transports = []

    def factory(server):
        transport = FakeTransport()
        transports.append(transport)
        return transport

    manager = lsp.LspManager(tmp_path, detector=lambda: [lsp.LspServerSpec(
        "pylsp", "pylsp", (), ("python",), True)], transport_factory=factory)
    assert manager.start("python")["started"] is True
    assert transports[0].sent[0]["method"] == "initialize"
    assert manager.diagnostics("python") == {}

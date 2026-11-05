"""Real SDK wire/lifecycle coverage and policy-before-start regression checks."""
from pathlib import Path
import json
import struct
import sys
import zlib

import pytest

from nl_coding_agent.app.mcp import McpError, McpManager
from nl_coding_agent.core import permissions
from nl_coding_agent.persistence import database


def tool_payload(result):
    assert not result.get("isError"), result
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def _one_pixel_png() -> bytes:
    def chunk(kind, payload):
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + chunk(b"IEND", b""))


@pytest.fixture
def manager(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    database.init_db().close()
    return McpManager(config={"servers": {"fixture": {
        "command": sys.executable,
        "args": [str(Path(__file__).parent / "fixtures" / "mcp_sdk_server.py")],
        "trusted": True, "timeout": 10}}})


def test_real_stdio_tools_resources_and_diagnostics(manager, tmp_path):
    tools = manager.list_tools("fixture")
    assert {t["qualified_name"] for t in tools} == {"fixture::echo", "fixture::slow"}
    result = manager.invoke_tool("fixture", "fixture::echo", {"text": "ciao"}, human_approved=True)
    assert tool_payload(result) == {"echo": "ciao"}
    assert result["untrusted"] and not result["isError"]
    resources = manager.list_resources("fixture")
    assert str(resources[0]["uri"]) == "fixture://context"
    result = manager.read_resource("fixture", "fixture://context", human_approved=True)
    assert result["contents"][0]["text"] == "untrusted fixture context"
    logs = list((tmp_path / "workspace" / "logs" / "mcp").glob("*.stderr.log"))
    assert any("fixture diagnostics" in p.read_text(encoding="utf-8") for p in logs)
    with pytest.raises(McpError, match="not advertised"):
        manager.read_resource("fixture", "file:///secret", human_approved=True)


def test_github_mcp_payload_preserves_bounded_file_text():
    from nl_coding_agent.app.mcp_engine import _bounded_github_payload

    text = "x" * 15000
    result = _bounded_github_payload({
        "result": {"kind": "file_contents", "data": {"text": text, "path": "README.md"},
                   "provenance": {"untrusted": True}},
        "untrusted": True,
    })
    assert len(result["result"]["data"]["text"]) == 12000 + len("\n... [truncated]")
    assert result["result"]["data"]["path"] == "README.md"
    assert result["untrusted"] is True


def test_schema_rejection_before_invocation(manager):
    with pytest.raises(McpError) as error:
        manager.invoke_tool("fixture", "echo", {"text": 123}, human_approved=True)
    assert error.value.code == "arguments-invalid"
    with pytest.raises(McpError) as error:
        manager.invoke_tool("fixture", "other::echo", {}, human_approved=True)
    assert error.value.code == "namespace-mismatch"


@pytest.mark.parametrize("change,code", [({"enabled": False}, "server-disabled")])
def test_trust_gate_precedes_process_start(manager, change, code):
    manager._config["servers"]["fixture"].update(change)
    manager._factory = lambda server: pytest.fail("No process may start")
    with pytest.raises(McpError) as error:
        manager.list_tools("fixture")
    assert error.value.code == code


def test_local_schema_never_fetches_remote_reference():
    with pytest.raises(McpError) as error:
        McpManager._validate_arguments({"$ref": "https://invalid.example/schema"}, {})
    assert error.value.code == "arguments-invalid"


def test_project_policy_used_before_start(manager):
    manager.project_id = 83
    permissions.set_access_mode("read-only")
    manager._factory = lambda server: pytest.fail("Denied project must not launch a process")
    with pytest.raises(permissions.PermissionDenied):
        manager.list_tools("fixture")


def test_tool_approval_does_not_override_denied_write(manager):
    permissions.set_access_mode("read-only")
    manager._factory = lambda server: pytest.fail("Denied WRITE must precede startup")
    with pytest.raises(permissions.PermissionDenied):
        manager.invoke_tool("fixture", "echo", {"text": "test"}, human_approved=True)


def test_real_streamable_http_requires_network_then_connects(manager):
    import socket
    import subprocess
    import time
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    fixture = Path(__file__).parent / "fixtures" / "mcp_sdk_server.py"
    process = subprocess.Popen([sys.executable, str(fixture), str(port)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                assert process.poll() is None, "Fixture HTTP server failed to start"
                assert time.monotonic() < deadline, "Fixture HTTP startup timeout"
                time.sleep(.05)
        manager._config = {"servers": {"fixture": {"transport": "http", "trusted": True,
            "url": f"http://127.0.0.1:{port}/mcp", "timeout": 10}}}
        with pytest.raises(McpError) as denied:
            manager.list_tools("fixture")
        assert denied.value.code == "network-denied"
        permissions.set_access_mode("auto-review")
        result = manager.invoke_tool("fixture", "echo", {"text": "HTTP"}, human_approved=True)
        assert tool_payload(result) == {"echo": "HTTP"}
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_real_engine_stdio_readonly_project_binding(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.app.mcp_engine import create_engine_server, vscode_configuration
    from nl_coding_agent.persistence.missions import create_mission, get_mission

    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "project"
    other = tmp_path / "other"
    root.mkdir()
    other.mkdir()
    services = AppServices()
    try:
        project = services.open_project(root)
        foreign = services.open_project(other)
        create_engine_server(services, project)
        own = create_mission(project["id"], "Own task", "Never execute automatically")
        foreign_id = create_mission(foreign["id"], "Foreign", "Private")
        spec = vscode_configuration(root)["servers"]["nl-coding-engine"]
        assert "--allow-execution" not in spec["args"]
        spec.pop("type")
        manager = McpManager(config={"servers": {"engine": {**spec, "trusted": True, "timeout": 20}}})
        names = {t["name"] for t in manager.list_tools("engine")}
        assert {"project_context", "mission_status", "start_mission", "cancel_mission",
                "engine_settings", "mission_detail", "attachment_ingest",
            "chat_history", "research_fetch_url", "speech_download_model",
                "research_github_lookup", "delete_missions"} <= names
        assert services._research_network_configured
        assert services._research_service()._http_transport is not None
        settings = manager.invoke_tool("engine", "engine_settings", {}, human_approved=True)
        settings_payload = tool_payload(settings)
        assert settings_payload["project"]["id"] == project["id"]
        assert "read" in settings_payload["permissions"]["scopes"]
        assert settings_payload["mission_defaults"]["developer_model"]
        assert settings_payload["models"]["discovered"] is None
        assert settings_payload["research"]["profile"] == "manual"
        assert settings_payload["research"]["network_granted"] is False
        notes = root / "notes.txt"
        notes.write_bytes(b"hello attachment\nsecond line\n")
        ingest = manager.invoke_tool("engine", "attachment_ingest",
                                     {"paths": ["notes.txt"]}, human_approved=True)
        ingest_payload = tool_payload(ingest)
        assert ingest_payload["ok"] and len(ingest_payload["attachments"]) == 1
        attachment = ingest_payload["attachments"][0]
        assert attachment["name"] == "notes.txt"
        assert attachment["kind"] == "text"
        assert attachment["has_text"] is True
        assert attachment["preview"] == "hello attachment\nsecond line\n"
        assert "stored_path" not in attachment
        pasted = manager.invoke_tool("engine", "attachment_ingest", {
            "image_base64": __import__("base64").b64encode(_one_pixel_png()).decode("ascii")
        }, human_approved=True)
        pasted_payload = tool_payload(pasted)
        image = pasted_payload["attachments"][0]
        assert image["kind"] == "image"
        assert image["mime"] == "image/png"
        assert image["has_text"] is False
        assert image["metadata"]["width"] == 1
        assert image["metadata"]["height"] == 1
        invalid_image = manager.invoke_tool("engine", "attachment_ingest", {
            "image_base64": "not base64"
        }, human_approved=True)
        assert invalid_image["isError"]
        assert "valid base64" in invalid_image["content"][0]["text"]
        outside = tmp_path / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        rejected_path = manager.invoke_tool("engine", "attachment_ingest",
                                            {"paths": [str(outside)]}, human_approved=True)
        assert rejected_path["isError"]
        assert "outside the bound project" in rejected_path["content"][0]["text"]
        history = manager.invoke_tool("engine", "chat_history", {}, human_approved=True)
        history_payload = tool_payload(history)
        assert history_payload["ok"] is True
        assert history_payload["messages"] == []
        denied_research = manager.invoke_tool("engine", "research_fetch_url",
                                              {"url": "https://example.com/"},
                                              human_approved=True)
        assert denied_research["isError"]
        assert "NETWORK" in denied_research["content"][0]["text"]
        detail = manager.invoke_tool("engine", "mission_detail", {"mission_id": own},
                                     human_approved=True)
        detail_payload = tool_payload(detail)
        assert detail_payload["mission"]["id"] == own
        assert detail_payload["mission"]["status"] == "pending"
        assert detail_payload["tasks"] == [] and detail_payload["progress"]["total"] == 0
        denied_asr_download = manager.invoke_tool("engine", "speech_download_model", {
            "model_id": "vosk-model-small-it-0.22"
        }, human_approved=True)
        assert denied_asr_download["isError"]
        assert "NETWORK" in denied_asr_download["content"][0]["text"]
        context = manager.invoke_tool("engine", "project_context", {}, human_approved=True)
        assert tool_payload(context)["project"]["id"] == project["id"]
        assert tool_payload(context)["execution_enabled"]
        status = manager.invoke_tool("engine", "mission_status", {"mission_id": own}, human_approved=True)
        assert tool_payload(status)["status"] == "pending"
        foreign_result = manager.invoke_tool("engine", "mission_status", {"mission_id": foreign_id}, human_approved=True)
        assert foreign_result["isError"]
        # No legacy CLI execution flag is required; the global mode is live.
        permissions.set_access_mode("read-only")
        with pytest.raises(permissions.PermissionDenied):
            manager.invoke_tool("engine", "start_mission", {
                "goal": "Change code", "developer_model": "local/model", "reviewer_model": "local/reviewer"})
        permissions.set_access_mode("workspace-write")
        # Workspace Write is enough for mission deletion: it is an application
        # operation gated by EXECUTE plus the explicit approved flag, not an OS
        # file delete.
        deleted = manager.invoke_tool("engine", "delete_missions", {
            "mission_ids": [own], "approved": True}, human_approved=True)
        assert tool_payload(deleted)["deleted_count"] == 1
        assert get_mission(own) is None

        pending = create_mission(project["id"], "Pending task", "Delete without execution")
        permissions.set_access_mode(permissions.ACCESS_READ_ONLY)
        with pytest.raises(permissions.PermissionDenied):
            manager.invoke_tool("engine", "delete_missions", {
                "mission_ids": [pending], "approved": True}, human_approved=True)
        assert get_mission(pending)["status"] == "pending"

        permissions.set_access_mode(permissions.ACCESS_WORKSPACE_WRITE)
        unapproved_delete = manager.invoke_tool("engine", "delete_missions", {
            "mission_ids": [pending], "approved": False}, human_approved=True)
        assert tool_payload(unapproved_delete)["deleted_count"] == 1
        assert get_mission(pending) is None
        resource = manager.read_resource("engine", "nl-engine://project", human_approved=True)
        assert json.loads(resource["contents"][0]["text"])["project"]["id"] == project["id"]
        # A client may not converse as another project or as the unregistered id 0.
        for rejected_id in (foreign["id"], 0):
            rejected = manager.invoke_tool("engine", "nlc_converse", {
                "project_id": rejected_id, "text": "never reaches a model",
                "attachments": [], "history": []}, human_approved=True)
            assert rejected["isError"], rejected
            assert "bound to this server" in rejected["content"][0]["text"]
        chat_dir = tmp_path / "data" / "chat"
        assert not (chat_dir / ("project-" + str(foreign["id"]) + ".json")).exists()
        assert not (chat_dir / "project-0.json").exists()
    finally:
        services._db.close()

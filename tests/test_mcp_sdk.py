"""Real SDK wire/lifecycle coverage and policy-before-start regression checks."""
from pathlib import Path
import json
import sys

import pytest

from nl_coding_agent.app.mcp import McpError, McpManager
from nl_coding_agent.core import permissions
from nl_coding_agent.persistence import database


def tool_payload(result):
    assert not result.get("isError"), result
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


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


def test_schema_rejection_before_invocation(manager):
    with pytest.raises(McpError) as error:
        manager.invoke_tool("fixture", "echo", {"text": 123}, human_approved=True)
    assert error.value.code == "arguments-invalid"
    with pytest.raises(McpError) as error:
        manager.invoke_tool("fixture", "other::echo", {}, human_approved=True)
    assert error.value.code == "namespace-mismatch"


@pytest.mark.parametrize("change,code", [({"trusted": False}, "server-untrusted"),
                                        ({"enabled": False}, "server-disabled")])
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
    permissions.revoke(permissions.EXECUTE, project_id=83)
    manager._factory = lambda server: pytest.fail("Denied project must not launch a process")
    with pytest.raises(permissions.PermissionDenied):
        manager.list_tools("fixture")


def test_tool_approval_does_not_override_denied_write(manager):
    permissions.revoke(permissions.WRITE)
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
        permissions.grant(permissions.NETWORK)
        result = manager.invoke_tool("fixture", "echo", {"text": "HTTP"}, human_approved=True)
        assert tool_payload(result) == {"echo": "HTTP"}
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_real_engine_stdio_readonly_project_binding(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.app.mcp_engine import vscode_configuration
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
        own = create_mission(project["id"], "Own task", "Never execute automatically")
        foreign_id = create_mission(foreign["id"], "Foreign", "Private")
        spec = vscode_configuration(root)["servers"]["nl-coding-engine"]
        assert "--allow-execution" not in spec["args"]
        spec.pop("type")
        manager = McpManager(config={"servers": {"engine": {**spec, "trusted": True, "timeout": 20}}})
        names = {t["name"] for t in manager.list_tools("engine")}
        assert {"project_context", "mission_status", "start_mission", "cancel_mission",
                "engine_settings", "mission_detail"} <= names
        settings = manager.invoke_tool("engine", "engine_settings", {}, human_approved=True)
        settings_payload = tool_payload(settings)
        assert settings_payload["project"]["id"] == project["id"]
        assert "read" in settings_payload["permissions"]["scopes"]
        assert settings_payload["mission_defaults"]["developer_model"]
        assert settings_payload["models"]["discovered"] is None
        detail = manager.invoke_tool("engine", "mission_detail", {"mission_id": own},
                                     human_approved=True)
        detail_payload = tool_payload(detail)
        assert detail_payload["mission"]["id"] == own
        assert detail_payload["mission"]["status"] == "pending"
        assert detail_payload["tasks"] == [] and detail_payload["progress"]["total"] == 0
        context = manager.invoke_tool("engine", "project_context", {}, human_approved=True)
        assert tool_payload(context)["project"]["id"] == project["id"]
        assert not tool_payload(context)["execution_enabled"]
        status = manager.invoke_tool("engine", "mission_status", {"mission_id": own}, human_approved=True)
        assert tool_payload(status)["status"] == "pending"
        foreign_result = manager.invoke_tool("engine", "mission_status", {"mission_id": foreign_id}, human_approved=True)
        assert foreign_result["isError"]
        denied = manager.invoke_tool("engine", "start_mission", {
            "goal": "Change code", "developer_model": "local/model", "reviewer_model": "local/reviewer",
            "approved": True}, human_approved=True)
        assert denied["isError"]
        assert len(services.list_missions(project["id"])) == 1
        assert get_mission(own)["status"] == "pending"
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

"""Gate B/D management: model config writes, sessions, missions, storage."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "workspace"))
    from nl_coding_agent.persistence import database
    database.init_db().close()
    return tmp_path


def test_model_config_store_updates_provider_role_cloud_atomically(isolated, monkeypatch):
    path = isolated / "models.yaml"
    monkeypatch.setenv("NL_MODELS_CONFIG", str(path))
    from nl_coding_agent.models import model_config_store as store

    config = {
        "providers": {"ollama": {"enabled": True, "kind": "ollama",
                                 "base_url": "http://127.0.0.1:11434"}},
        "roles": {"developer": {"model": "ollama/a", "temperature": 0.1},
                  "fallback_cloud": {"enabled": False}},
    }
    store.save(config)
    store.update_provider("ollama", enabled=False, base_url="http://127.0.0.1:11434")
    assert store.load()["providers"]["ollama"]["enabled"] is False
    store.update_provider("lm_studio_custom", enabled=False,
                          base_url="http://127.0.0.1:1234/v1",
                          label="Custom", kind="openai_compatible",
                          api_key_env="CUSTOM_API_KEY")
    custom = store.load()["providers"]["lm_studio_custom"]
    assert custom["kind"] == "openai_compatible"
    assert custom["api_key_env"] == "CUSTOM_API_KEY"
    store.update_role("developer", model="ollama/b", temperature=0.2)
    assert store.load()["roles"]["developer"]["model"] == "ollama/b"
    store.set_cloud_escalation(True)
    assert store.load()["roles"]["fallback_cloud"]["enabled"] is True
    backups = list((isolated / "data" / "backups").glob("models-*.yaml"))
    assert backups
    with pytest.raises(store.ModelConfigError):
        store.update_role("developer", model="bad model with spaces")


def test_custom_agent_profiles_crud_persist_in_engine_state(isolated):
    from nl_coding_agent.app.services import AppServices
    services = AppServices()
    first = services.create_custom_agent(
        "Security reviewer", provider="ollama", model="ollama/qwen3.5:9b",
        role="security", instructions="Review injection and permission boundaries.",
        tools=["read", "diff"], permissions=["read-only"])
    assert first["id"]
    second = services.duplicate_custom_agent(first["id"], name="Security reviewer copy")
    assert second["id"] != first["id"]
    updated = services.update_custom_agent(first["id"], model="openai_compatible/gpt-5")
    assert updated["model"] == "openai_compatible/gpt-5"
    profiles = {str(item.get("custom_agent_id")): item for item in services.get_agent_roles()}
    assert profiles[first["id"]]["role"] == "Security reviewer"
    assert profiles[first["id"]]["execution_supported"] is False
    assert services.delete_custom_agent(second["id"]) is True
    assert services.get_custom_agent(second["id"]) is None
    services._db.close()


def test_operational_probe_runs_through_an_openai_compatible_provider():
    import json
    from nl_coding_agent.models.operational_probes import probe_model_with_provider

    class FakeProvider:
        def chat_turn(self, model, messages, tools, **kwargs):
            name = tools[0]["function"]["name"]
            args = {"value": 42} if name == "record_probe" else {
                "path": "probe_target.py", "target": "VALUE = 1",
                "replacement": "VALUE = 2"}
            return {"tool_calls": [{"function": {"name": name,
                                                 "arguments": json.dumps(args)}}]}

        def generate(self, model, prompt, **kwargs):
            return '{"ok": true, "n": 7}'

    records = probe_model_with_provider(
        FakeProvider(), "openai_compatible", "hosted-model", persist=False)
    by_name = {record.capability: record for record in records}
    assert by_name["tool_calling"].state == "measured"
    assert by_name["patch_quality"].state == "measured"
    assert by_name["structured_output"].state == "measured"


def test_backup_retention_is_bounded(isolated):
    from nl_coding_agent.core.backup_retention import prune
    backups = isolated / "data" / "backups"
    backups.mkdir(parents=True)
    for index in range(15):
        (backups / f"models-{index:02d}.yaml").write_text("x", encoding="utf-8")
    removed = prune(backups, "models-", keep=5)
    assert len(removed) == 10
    assert len(list(backups.glob("models-*.yaml"))) == 5


def test_storage_vacuum_is_guarded_and_returns_result(isolated):
    from nl_coding_agent.core import storage_manager
    from nl_coding_agent.persistence import database
    conn = database.init_db()
    conn.close()
    with pytest.raises(storage_manager.StorageError):
        storage_manager.vacuum_database(confirm=False)
    result = storage_manager.vacuum_database(confirm=True)
    assert "ok" in result
    assert isinstance(result.get("freed_bytes"), int)


def test_chat_sessions_are_persistent_and_migrate_legacy(isolated):
    from nl_coding_agent.app import chat_sessions

    legacy_dir = isolated / "data" / "chat"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "project-1.json").write_text(json.dumps([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]), encoding="utf-8")
    sessions = chat_sessions.list_sessions(1)
    assert sessions
    assert len(chat_sessions.messages(1)) == 2
    created = chat_sessions.create_session(1, "Second")
    chat_sessions.append_message(1, "user", "new", session_id=created["id"])
    assert chat_sessions.messages(1, session_id=created["id"])[0]["content"] == "new"
    renamed = chat_sessions.rename_session(created["id"], "Renamed")
    assert renamed["title"] == "Renamed"
    chat_sessions.archive_session(created["id"])
    chat_sessions.delete_session(1, created["id"])
    assert all(item["id"] != created["id"] for item in chat_sessions.list_sessions(1, include_archived=True))
    # Deleting every session must not silently re-import the retained legacy file.
    for session in chat_sessions.list_sessions(1):
        chat_sessions.archive_session(session["id"])
        chat_sessions.delete_session(1, session["id"])
    assert chat_sessions.messages(1) == []


def test_mission_archive_then_delete_requires_archived(isolated):
    from nl_coding_agent.persistence import missions

    mission_id = missions.create_mission(None, "test", "goal")
    missions.update_mission_status(mission_id, "completed")
    with pytest.raises(ValueError, match="Archive"):
        missions.delete_mission(mission_id)
    missions.archive_mission(mission_id)
    missions.delete_mission(mission_id)
    assert missions.get_mission(mission_id) is None


def test_storage_scan_and_selective_purge_are_guarded(isolated):
    from nl_coding_agent.core import storage_manager

    workspace = isolated / "workspace"
    (workspace / ".workspace" / "temp").mkdir(parents=True)
    (workspace / ".workspace" / "temp" / "junk.bin").write_bytes(b"x" * 32)
    result = storage_manager.scan(workspace)
    item = next(item for item in result["items"] if item["category"] == "workspace-temp")
    with pytest.raises(storage_manager.StorageError):
        storage_manager.purge([item["id"]], confirm=False, project_root=workspace)
    out = storage_manager.purge([item["id"]], confirm=True, project_root=workspace)
    assert out["freed_bytes"] == 32
    assert not (workspace / ".workspace" / "temp").exists()


def test_models_panel_saves_generation_params(isolated):
    from PySide6.QtWidgets import QApplication
    from nl_coding_agent.gui.widgets.models_panel import ModelsPanel

    class FakeServices:
        def __init__(self):
            self.saved = None

        def discover_models(self, timeout=5.0):
            return None

        def save_generation_params(self, params, **kwargs):
            self.saved = (params, kwargs)
            return params

    app = QApplication.instance() or QApplication([])
    services = FakeServices()
    panel = ModelsPanel(services)
    panel._gp_scope.setCurrentText("model")
    panel._gp_model.setText("ollama/m")
    panel._gp_fields["temperature"].setText("0.2")
    panel._save_parameters()
    assert services.saved[0]["temperature"] == 0.2
    panel.shutdown()


def test_settings_panel_persists_provider_and_cloud(isolated, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel
    import shutil

    source = Path(__file__).resolve().parents[1] / "config" / "models.yaml"
    target = isolated / "models.yaml"
    shutil.copyfile(source, target)
    monkeypatch.setenv("NL_MODELS_CONFIG", str(target))
    app = QApplication.instance() or QApplication([])
    services = AppServices()
    panel = SettingsPanel(services)
    assert panel._provider_combo.count() >= 1
    panel._provider_combo.setCurrentText("ollama")
    panel._provider_enabled.setChecked(False)
    panel._cloud_enabled.setChecked(True)
    panel._save_provider()
    from nl_coding_agent.models.model_config_store import load
    assert load()["providers"]["ollama"]["enabled"] is False
    assert load()["roles"]["fallback_cloud"]["enabled"] is True
    assert "saved" in panel._provider_status.text().lower()
    panel.deleteLater()


def test_agents_panel_persists_role_model(isolated):
    from PySide6.QtWidgets import QApplication
    from nl_coding_agent.gui.widgets.agents_panel import AgentsPanel

    class FakeServices:
        def __init__(self):
            self.saved = None

        def get_agent_roles(self):
            return [{"role": "developer", "model": "ollama/old", "kind": "llm"}]

        def check_ollama(self):
            return False

        def list_models(self):
            return []

        def get_model_config(self):
            return {"roles": {"developer": {"model": "ollama/old"}}}

        def save_role_settings(self, role, **changes):
            self.saved = (role, changes)
            return {}

    app = QApplication.instance() or QApplication([])
    services = FakeServices()
    panel = AgentsPanel(services)
    panel._role_editor.setCurrentText("developer")
    panel._model_editor.setCurrentText("ollama/new")
    panel._save_role_model()
    assert services.saved == ("developer", {"model": "ollama/new"})
    assert "Saved" in panel._status_label.text()
    panel.deleteLater()


def test_mcp_config_is_validated_and_persisted(isolated, monkeypatch):
    target = isolated / "mcp_servers.json"
    monkeypatch.setenv("NL_MCP_CONFIG", str(target))
    from nl_coding_agent.app import mcp
    payload = {"servers": {"demo": {"transport": "stdio", "command": "python",
                                    "args": ["server.py"]}}}
    mcp.save_mcp_config(payload)
    assert mcp.load_mcp_config()["servers"]["demo"]["command"] == "python"
    with pytest.raises(mcp.McpError):
        mcp.save_mcp_config({"servers": {"bad": {"transport": "stdio"}}})
    with pytest.raises(mcp.McpError):
        mcp.save_mcp_config({"servers": {"bad name": {"transport": "stdio",
                                                      "command": "python"}}})


def test_chat_panel_creates_and_selects_durable_session(isolated):
    from PySide6.QtWidgets import QApplication
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel

    app = QApplication.instance() or QApplication([])
    services = AppServices()
    panel = ChatPanel(services)
    panel.set_project({"id": 1, "root": str(isolated), "name": "demo"})
    assert panel._session_combo.count() >= 1
    first = panel.current_session_id()
    assert first
    panel._new_session()
    assert panel.current_session_id() != first
    assert len(services.list_chat_sessions(1)) >= 2
    # Simulate a restart: a fresh service instance must see the same sessions.
    from nl_coding_agent.app.services import AppServices as FreshServices
    assert len(FreshServices().list_chat_sessions(1)) >= 2
    panel.deleteLater()


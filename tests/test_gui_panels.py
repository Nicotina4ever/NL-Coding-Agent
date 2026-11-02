import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices

    app_services = AppServices()
    yield app_services
    try:
        app_services._db.close()
    except Exception:
        pass


def test_agent_roles_and_availability_render(services):
    from nl_coding_agent.gui.widgets.agents_panel import AgentsPanel

    _app()
    panel = AgentsPanel(services)
    roles = services.get_agent_roles()

    assert [r["role"] for r in roles] == [
        "architect", "developer", "tester", "debugger", "reviewer",
    ]
    assert roles[2]["kind"] == "deterministic"
    assert panel._table.rowCount() == 5

    developer_model = roles[1]["model"]
    model_name = developer_model.removeprefix("ollama/")
    panel._on_data_ready(
        roles,
        [SimpleNamespace(name=model_name, loaded=False)],
        True,
    )
    statuses = [
        panel._table.item(row, 2).text() for row in range(panel._table.rowCount())
    ]
    assert "Deterministic" in statuses
    assert "Available" in statuses
    panel.shutdown()


def test_settings_panel_is_read_only_and_tracks_project(services):
    from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel

    _app()
    panel = SettingsPanel(services)
    assert panel._project_value.text() == "No project open"
    assert "nl_coding_agent.sqlite3" in panel._database_value.text()
    assert panel._models_value.text().endswith("models.yaml")
    assert "READ" in panel._permissions_value.text().upper()

    root = str(Path.cwd().resolve())
    panel.set_project({"id": 1, "root": root})
    assert panel._project_value.text() == root
    assert "opt-in" in panel._cloud_value.text()
    assert "human/backend" in panel._permissions_value.text().lower()
    assert panel._autonomy_btn is not None


def test_autonomy_panel_is_non_blocking_and_project_scoped(services, tmp_path):
    from nl_coding_agent.gui.widgets.autonomy_panel import AutonomyPanel

    _app()
    panel = AutonomyPanel(services)
    assert panel._mode_combo.count() == 3
    assert panel._mode_combo.itemData(0) == "off"
    assert panel._missions_spin.value() == 1
    assert panel._queue_table.rowCount() == 0
    assert panel._start_btn.isEnabled() is False

    panel.set_project({"id": 999, "root": str(tmp_path)})
    assert panel._start_btn.isEnabled() is True
    assert "Supervisor:" in panel._status_label.text()
    panel.set_project(None)
    assert panel._start_btn.isEnabled() is False
    panel.shutdown()




def test_goals_panel_exposes_all_sections_without_project():
    from nl_coding_agent.gui.widgets.goals_panel import GoalsPanel

    _app()
    panel = GoalsPanel(SimpleNamespace())
    assert [panel._tabs.tabText(i) for i in range(panel._tabs.count())] == [
        "Overview", "Milestones", "Missions & Queue", "Activity & Decisions",
        "Tasks & Active Workers", "Plan Versions", "Evidence & Verification", "Next Work"]
    assert panel._create_btn.isEnabled() is False
    assert panel._verify_btn.isEnabled() is False
    assert panel._replan_btn.isEnabled() is False
    panel.close()
    panel.deleteLater()
    QApplication.processEvents()


def test_panels_do_not_import_database_or_crewai():
    widgets = Path("nl_coding_agent/gui/widgets")
    for name in ("agents_panel.py", "settings_panel.py", "autonomy_panel.py",
                 "task_board.py", "chat_panel.py", "editor_panel.py",
                 "terminal_panel.py", "git_panel.py", "problems_panel.py",
                 "command_palette.py", "research_panel.py", "goals_panel.py"):
        source = (widgets / name).read_text(encoding="utf-8")
        assert "PyQt5" not in source
        assert "sqlite3" not in source
        assert "crewai" not in source
        for network in ("import requests", "from requests", "urllib.request",
                        "http.client", "import socket"):
            assert network not in source, (name, network)


def test_task_board_filters_and_deletes_selected_pending_missions(
        services, tmp_path, monkeypatch):
    from nl_coding_agent.gui.widgets.task_board import TaskBoardWidget
    from nl_coding_agent.persistence.missions import (
        create_mission, get_mission, update_mission_status,
    )

    _app()
    project_root = tmp_path / "project"
    other_root = tmp_path / "other"
    project_root.mkdir()
    other_root.mkdir()
    project_file = project_root / "keep.txt"
    project_file.write_text("keep project source", encoding="utf-8")
    project = services.open_project(project_root)
    other_project = services.open_project(other_root)
    first = create_mission(project["id"], "Plan alpha", "Implement alpha")
    second = create_mission(project["id"], "Plan beta", "Implement beta")
    archived = create_mission(project["id"], "Archived plan", "Already complete")
    update_mission_status(archived, "completed")
    services.archive_mission(archived, project_id=project["id"])
    other = create_mission(other_project["id"], "Other project", "Do not touch")
    board = TaskBoardWidget(services)
    board.set_project(project)
    try:
        board._search_filter.setText("alpha")
        board.refresh()
        assert board._mission_list.count() == 1
        assert board._mission_list.item(0).data(Qt.ItemDataRole.UserRole) == first

        board._search_filter.clear()
        board._status_filter.setCurrentIndex(
            board._status_filter.findData("completed"))
        assert board._mission_list.count() == 0
        board._archived_toggle.setChecked(True)
        assert board._mission_list.count() == 1
        assert board._mission_list.item(0).data(Qt.ItemDataRole.UserRole) == archived
        board._archived_toggle.setChecked(False)
        board._status_filter.setCurrentIndex(0)
        board.refresh()
        assert board._mission_list.count() == 2
        board._select_filtered_missions()
        assert set(board._selected_mission_ids()) == {first, second}
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
        board._delete_selected()

        assert get_mission(first) is None
        assert get_mission(second) is None
        assert get_mission(archived)["archived_at"]
        assert get_mission(other)["project_id"] == other_project["id"]
        assert project_file.read_text(encoding="utf-8") == "keep project source"
    finally:
        board.close()
        board.deleteLater()
        QApplication.processEvents()


def test_task_board_waits_for_cooperative_stop_before_archiving(
        services, tmp_path, monkeypatch):
    from nl_coding_agent.gui.widgets.task_board import TaskBoardWidget
    from nl_coding_agent.persistence import database
    from nl_coding_agent.persistence.missions import (
        create_mission, get_mission, update_mission_status,
    )

    _app()
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = services.open_project(project_root)
    mission_id = create_mission(project["id"], "Active", "Run safely")
    update_mission_status(mission_id, "running")
    board = TaskBoardWidget(services)
    board.set_project(project)
    try:
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
        board._stop_selected()
        assert board._bulk_operation is not None
        assert board._bulk_operation["action"] == "stop"
        assert get_mission(mission_id)["status"] == "running"
        assert database.get_setting(f"mission.stop.{mission_id}", "")

        update_mission_status(mission_id, "interrupted")
        board._poll_bulk_operation()
        assert board._bulk_operation is None
        assert get_mission(mission_id)["archived_at"] is None

        board._archive_selected()
        assert get_mission(mission_id)["archived_at"]
    finally:
        board._bulk_timer.stop()
        board.close()
        board.deleteLater()
        QApplication.processEvents()


def test_agents_generate_and_persist_active_project_team(services, tmp_path, monkeypatch):
    from nl_coding_agent.gui.widgets.agents_panel import AgentsPanel

    _app()
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = services.open_project(project_root)
    roles = [
        {
            "role_id": "architect", "name": "Project architect",
            "role": "architect", "model": "ollama/test-model",
            "tools": ["read_file", "list_dir"], "instructions": "Inspect the project.",
        },
        {
            "role_id": "developer", "name": "Project developer",
            "role": "developer", "model": "ollama/test-model",
            "tools": ["read_file", "write_file", "patch_file"],
            "instructions": "Implement the requested task.",
        },
    ]
    calls = []

    def team_plan(project_id, model):
        calls.append((project_id, model))
        return {"ok": True, "roles": roles, "summary": "A focused team"}

    monkeypatch.setattr(services, "team_plan", team_plan)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    panel = AgentsPanel(services)
    panel.set_project(project)
    panel._model_editor.setCurrentText("ollama/test-model")
    try:
        panel._generate_team()
        def finish_generation():
            thread = panel._team_thread
            assert thread is not None
            assert thread.wait(5000)
            for _ in range(5):
                QApplication.processEvents()

        finish_generation()

        active = [
            item for item in services.list_custom_agents()
            if item.get("team_active") is True
            and str(item.get("project_id")) == str(project["id"])
        ]
        first_ids = {item["id"] for item in active}
        assert calls == [(project["id"], "ollama/test-model")]
        assert {item["role_id"] for item in active} == {"architect", "developer"}
        assert "Project architect" in panel._team_status.text()
        assert all(item.get("tools") for item in active)

        panel._generate_team()
        finish_generation()
        active = [
            item for item in services.list_custom_agents()
            if item.get("team_active") is True
            and str(item.get("project_id")) == str(project["id"])
        ]
        assert calls == [
            (project["id"], "ollama/test-model"),
            (project["id"], "ollama/test-model"),
        ]
        assert {item["id"] for item in active} == first_ids
        assert len(active) == 2
        assert "0 created, 2 updated" in panel._status_label.text()
    finally:
        panel.shutdown()
        panel.close()
        panel.deleteLater()
        QApplication.processEvents()


def test_custom_agent_editor_does_not_duplicate_project_permissions():
    from nl_coding_agent.gui.dialogs.custom_agents import _EditDialog

    _app()
    dialog = _EditDialog({"permissions": ["project-write"]})
    try:
        assert not hasattr(dialog, "_permissions")
        assert "permissions" not in dialog.values()
    finally:
        dialog.close()
        dialog.deleteLater()
        QApplication.processEvents()

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


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

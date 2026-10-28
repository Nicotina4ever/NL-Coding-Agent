import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.gui.widgets.agents_panel import AgentsPanel
from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel


def _app():
    return QApplication.instance() or QApplication([])


def test_agent_roles_and_availability_render():
    _app()
    services = AppServices()
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


def test_settings_panel_is_read_only_and_tracks_project():
    _app()
    services = AppServices()
    panel = SettingsPanel(services)
    assert panel._project_value.text() == "No project open"
    assert "nl_coding_agent.sqlite3" in panel._database_value.text()
    assert panel._models_value.text().endswith("models.yaml")

    root = str(Path.cwd().resolve())
    panel.set_project({"root": root})
    assert panel._project_value.text() == root
    assert "opt-in" in panel._cloud_value.text()


def test_panels_do_not_import_database_or_crewai():
    widgets = Path("nl_coding_agent/gui/widgets")
    for name in ("agents_panel.py", "settings_panel.py"):
        source = (widgets / name).read_text(encoding="utf-8")
        assert "PyQt5" not in source
        assert "sqlite3" not in source
        assert "crewai" not in source

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.gui.main_window import MainWindow
from nl_coding_agent.gui.widgets.agents_panel import AgentsPanel
from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel


def test_main_window_constructs_and_closes_cleanly():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(AppServices())
    assert window._stack.count() == 6
    assert window._page_index == {
        "projects": 0,
        "files": 1,
        "tasks": 2,
        "agents": 3,
        "settings": 4,
        "models": 5,
    }
    assert isinstance(window._stack.widget(3), AgentsPanel)
    assert isinstance(window._stack.widget(4), SettingsPanel)
    assert window._agents_panel._table.rowCount() == 5
    assert window._settings_panel._project_value.text() == "No project open"
    window.close()
    app.processEvents()

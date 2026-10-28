import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


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


def test_main_window_constructs_and_closes_cleanly(services, tmp_path):
    from nl_coding_agent.gui.main_window import MainWindow
    from nl_coding_agent.gui.widgets.agents_panel import AgentsPanel
    from nl_coding_agent.gui.widgets.autonomy_panel import AutonomyPanel
    from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel

    app = QApplication.instance() or QApplication([])
    window = MainWindow(services)
    assert window._stack.count() == 8
    assert window._page_index == {
        "projects": 0,
        "files": 1,
        "tasks": 2,
        "agents": 3,
        "settings": 4,
        "models": 5,
        "autonomy": 6,
        "chat": 7,
    }
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
    assert isinstance(window._stack.widget(7), ChatPanel)
    # F2 voice controls are present and honest about their state (no hardware touched).
    assert window._chat_panel._mic_btn.accessibleName() == "Start or stop dictation"
    assert window._chat_panel._voice_stop_btn.isEnabled() is False
    assert window._chat_panel._tts_toggle.accessibleName() == "Read transcript aloud"
    assert "Voice: idle" in window._chat_panel._voice_status.text()
    assert isinstance(window._stack.widget(3), AgentsPanel)
    assert isinstance(window._stack.widget(4), SettingsPanel)
    assert isinstance(window._stack.widget(6), AutonomyPanel)
    assert window._agents_panel._table.rowCount() == 5
    assert window._settings_panel._project_value.text() == "No project open"
    assert window._autonomy_panel._mode_combo.count() == 3
    assert window._stop_supervisor_btn.isEnabled() is False
    window._switch_page("autonomy")
    assert window._stack.currentIndex() == 6
    window.close()
    app.processEvents()

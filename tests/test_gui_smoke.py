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
    # Construction must never start autonomy/self-build (NL-BP-023): any attempt
    # to call the start wrapper during window construction fails the test.
    started: list = []
    services.supervisor_start = lambda *a, **k: started.append(1) or {"ok": True}
    window = MainWindow(services)
    assert started == [], "autonomy/self-build must never start on app open"
    assert window._stack.count() == 11
    assert window._page_index == {
        "projects": 0,
        "files": 1,
        "tasks": 2,
        "agents": 3,
        "settings": 4,
        "models": 5,
        "autonomy": 6,
        "chat": 7,
        "ide": 8,
        "research": 9,
        "goals": 10,
    }
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
    assert isinstance(window._stack.widget(7), ChatPanel)
    from PySide6.QtWidgets import QTabWidget, QTableWidget
    from nl_coding_agent.gui.widgets.editor_panel import EditorPanel
    from nl_coding_agent.gui.widgets.terminal_panel import TerminalPanel
    from nl_coding_agent.gui.widgets.git_panel import GitPanel
    from nl_coding_agent.gui.widgets.problems_panel import ProblemsPanel
    ide = window._stack.widget(8)
    assert isinstance(ide, QTabWidget) and ide.count() == 4
    assert isinstance(ide.widget(0), EditorPanel)
    assert isinstance(ide.widget(1), TerminalPanel)
    assert isinstance(ide.widget(2), GitPanel)
    assert isinstance(ide.widget(3), ProblemsPanel)
    assert window._editor_panel._tabs_widget.accessibleName() == "Open editor tabs"
    assert window._terminal_panel._output.isReadOnly() is True
    assert window._git_panel._diff.isReadOnly() is True
    assert window._problems_panel._table.rowCount() == 0
    from nl_coding_agent.gui.widgets.research_panel import ResearchPanel
    research = window._stack.widget(9)
    assert isinstance(research, ResearchPanel)
    assert research._results_table.rowCount() == 0
    assert research._query.accessibleName() == "Research query"
    assert research._provider_combo.accessibleName() == "Research provider and route"
    assert research._preview_text.isReadOnly() is True
    assert "offline" in research._service_label.text().lower()
    from nl_coding_agent.gui.widgets.goals_panel import GoalsPanel
    goals = window._stack.widget(10)
    assert isinstance(goals, GoalsPanel)
    assert goals._create_btn.isEnabled() is False
    assert goals._goals_table.rowCount() == 0
    assert goals._goals_table.editTriggers() == (
        QTableWidget.EditTrigger.NoEditTriggers)
    assert "No project" in goals._scope_label.text()
    from nl_coding_agent.gui.widgets.command_palette import CommandPalette
    actions = window._command_palette_actions()
    assert any(action.action_id == "doctor" and action.enabled for action in actions)
    assert any(action.action_id == "open-project" for action in actions)
    debug_action = next(action for action in actions if action.action_id == "debug-start")
    assert debug_action.enabled is False and debug_action.disabled_reason
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
    window._switch_page("autonomy")
    assert window._stack.currentIndex() == 6

    # --- Settings > Advanced self-build controls (NL-BP-023) ---------------
    settings = window._settings_panel
    assert settings._advanced_group.accessibleName()
    assert settings._advanced_mode_combo.count() == 3
    assert [settings._advanced_mode_combo.itemData(i) for i in range(3)] == [
        "off", "assisted", "automatic"]
    assert settings._advanced_plan_preview.isReadOnly() is True
    assert settings._advanced_history_table.editTriggers() == (
        QTableWidget.EditTrigger.NoEditTriggers)
    assert settings._advanced_plan_preview.toPlainText().startswith("Open a project")
    for button in (settings._save_advanced_btn, settings._pause_advanced_btn,
                   settings._stop_advanced_btn, settings._refresh_advanced_btn):
        assert button.accessibleName()
    assert not hasattr(settings, "_start_btn")

    # The autonomy page is now a read-only status view: interactive controls live
    # only under Settings > Advanced.
    assert window._autonomy_panel._mode_combo.count() == 3
    assert window._autonomy_panel._controls_container.isHidden() is True
    assert window._autonomy_panel._start_btn.isEnabled() is False

    # --- Always-reachable emergency Pause/Stop outside settings (NL-BP-024) --
    assert window._emergency_widget.isHidden() is True
    assert window._emergency_widget.parent() is window.statusBar()
    assert window._pause_supervisor_btn.accessibleName()
    assert window._stop_supervisor_btn.accessibleName()
    assert window._stop_supervisor_btn.isEnabled() is False
    assert "Ctrl+Alt+P" in window._pause_supervisor_btn.toolTip()
    assert "Ctrl+Alt+S" in window._stop_supervisor_btn.toolTip()
    assert window._emergency_pause_shortcut.key().toString() in ("Ctrl+Alt+P",)
    assert window._emergency_stop_shortcut.key().toString() in ("Ctrl+Alt+S",)

    window.close()
    app.processEvents()


def test_gui_widgets_have_no_direct_database_or_crewai_imports():
    from pathlib import Path

    gui = Path("nl_coding_agent/gui")
    sources = [gui / "main_window.py"] + sorted((gui / "widgets").glob("*.py"))
    for path in sources:
        lowered = path.read_text(encoding="utf-8").lower()
        assert "import sqlite3" not in lowered, path.name
        assert "from sqlite3" not in lowered, path.name
        assert "import crewai" not in lowered, path.name
        assert "from crewai" not in lowered, path.name
        for network in ("import requests", "from requests", "urllib.request",
                        "http.client", "import socket"):
            assert network not in lowered, (path.name, network)

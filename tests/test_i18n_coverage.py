"""Representative translation/live-retranslation coverage for secondary Studio panels (U3)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PANEL_FILES = [
    "task_board.py", "chat_panel.py", "agents_panel.py", "models_panel.py",
    "autonomy_panel.py", "log_panel.py", "editor_panel.py",
    "terminal_panel.py", "git_panel.py", "problems_panel.py",
    "command_palette.py", "goals_panel.py", "research_panel.py",
]


@pytest.fixture()
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui import i18n
    i18n.reset_i18n()
    app_services = AppServices()
    yield app_services
    try:
        app_services._db.close()
    except Exception:
        pass
    i18n.reset_i18n()


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_all_secondary_panel_keys_exist_in_both_catalogs():
    keys = set()
    for name in PANEL_FILES:
        source = (REPO_ROOT / "nl_coding_agent" / "gui" / "widgets" /
                  name).read_text(encoding="utf-8")
        for match in re.finditer(r'_tr\(\s*"([^"]+)"', source):
            key = match.group(1)
            if key.endswith("_"):
                continue
            keys.add(key)
    assert keys
    for catalog_name in ("it.json", "en.json"):
        catalog = json.loads((REPO_ROOT / "nl_coding_agent" / "gui" /
                              "locales" / catalog_name).read_text(
                                  encoding="utf-8"))
        missing = sorted(keys - set(catalog["strings"]))
        assert not missing, (catalog_name, missing[:20])
        assert catalog["locale"] == catalog_name[:2]


def test_secondary_panels_have_italian_english_and_live_retranslation(services):
    app = _app()
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui.i18n import get_i18n
    from nl_coding_agent.gui.widgets.agents_panel import AgentsPanel
    from nl_coding_agent.gui.widgets.autonomy_panel import AutonomyPanel
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
    from nl_coding_agent.gui.widgets.command_palette import CommandAction, CommandPalette
    from nl_coding_agent.gui.widgets.editor_panel import EditorPanel
    from nl_coding_agent.gui.widgets.git_panel import GitPanel
    from nl_coding_agent.gui.widgets.goals_panel import GoalsPanel
    from nl_coding_agent.gui.widgets.log_panel import LogPanel
    from nl_coding_agent.gui.widgets.models_panel import ModelsPanel
    from nl_coding_agent.gui.widgets.problems_panel import ProblemsPanel
    from nl_coding_agent.gui.widgets.research_panel import ResearchPanel
    from nl_coding_agent.gui.widgets.task_board import TaskBoardWidget
    from nl_coding_agent.gui.widgets.terminal_panel import TerminalPanel

    translator = get_i18n(services)
    assert translator.current_language == "it"

    panels = {}
    try:
        panels["task_board"] = TaskBoardWidget(services)
        panels["chat"] = ChatPanel(services)
        panels["agents"] = AgentsPanel(services)
        panels["models"] = ModelsPanel(services)
        panels["autonomy"] = AutonomyPanel(services)
        panels["log"] = LogPanel()
        panels["editor"] = EditorPanel(services)
        panels["terminal"] = TerminalPanel(services)
        panels["git"] = GitPanel(services)
        panels["problems"] = ProblemsPanel(services)
        panels["command_palette"] = CommandPalette(
            [CommandAction("safe-action", "Safe action")])
        panels["goals"] = GoalsPanel(SimpleNamespace())
        panels["research"] = ResearchPanel(services)
        app.processEvents()

        checks = {
            "task_board": (lambda p: p._title.text(), "Missioni e attività"),
            "chat": (lambda p: p._title.text(), "CHAT MISSIONE"),
            "agents": (lambda p: p._title.text(), "Agenti"),
            "models": (lambda p: p._title.text(), "Hub modelli"),
            "autonomy": (lambda p: p._title.text(), "Stato autonomia (sola lettura)"),
            "log": (lambda p: p._title.text(), "Log"),
            "editor": (lambda p: p._title.text(), "EDITOR"),
            "terminal": (lambda p: p._title.text(), "TERMINALE"),
            "git": (lambda p: p._title.text(), "GIT"),
            "problems": (lambda p: p._title.text(), "PROBLEMI"),
            "command_palette": (lambda p: p.windowTitle(), "Tavolozza comandi"),
            "goals": (lambda p: p._title.text(), "OBIETTIVI"),
            "research": (lambda p: p._title.text(), "RICERCA"),
        }
        for name, (getter, expected) in checks.items():
            assert getter(panels[name]) == expected, (name, getter(panels[name]))
        # Representative secondary strings/table headers/buttons.
        assert panels["task_board"]._refresh_btn.text() == "Aggiorna"
        assert panels["chat"]._submit_btn.text() == "Invia missione"
        assert panels["agents"]._table.horizontalHeaderItem(0).text() == "Ruolo"
        assert panels["models"]._tabs.tabText(0) == "Modelli"
        assert panels["terminal"]._run_btn.text() == "Esegui"
        assert panels["git"]._tabs.tabText(0) == "Diff"
        assert panels["problems"]._table.horizontalHeaderItem(0).text() == "Gravità"
        assert panels["command_palette"]._title.text() == "TAVOLOZZA COMANDI"
        assert panels["goals"]._tabs.tabText(0) == "Panoramica"
        assert panels["research"]._search_btn.text() == "Cerca"

        # Live switch to English must update every registered panel synchronously.
        translator.set_language("en")
        app.processEvents()
        english = {
            "task_board": (lambda p: p._title.text(), "Missions & Tasks"),
            "chat": (lambda p: p._title.text(), "MISSION CHAT"),
            "agents": (lambda p: p._title.text(), "Agents"),
            "models": (lambda p: p._title.text(), "Model Hub"),
            "autonomy": (lambda p: p._title.text(), "Autonomy status (read-only)"),
            "log": (lambda p: p._title.text(), "Logs"),
            "editor": (lambda p: p._title.text(), "EDITOR"),
            "terminal": (lambda p: p._title.text(), "TERMINAL"),
            "git": (lambda p: p._title.text(), "GIT"),
            "problems": (lambda p: p._title.text(), "PROBLEMS"),
            "command_palette": (lambda p: p.windowTitle(), "Command Palette"),
            "goals": (lambda p: p._title.text(), "GOALS"),
            "research": (lambda p: p._title.text(), "RESEARCH"),
        }
        for name, (getter, expected) in english.items():
            assert getter(panels[name]) == expected, (name, getter(panels[name]))
        assert panels["task_board"]._refresh_btn.text() == "Refresh"
        assert panels["goals"]._tabs.tabText(0) == "Overview"
        assert panels["research"]._search_btn.text() == "Search"
        assert services.ui_language_preference() == "en"
    finally:
        for panel in panels.values():
            shutdown = getattr(panel, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    pass
            close = getattr(panel, "close", None)
            if callable(close):
                close()
            panel.deleteLater()
        app.processEvents()


def test_secondary_panels_fallback_without_active_translator(services):
    """Direct widget construction stays English/source when no app translator is active."""
    from nl_coding_agent.gui import i18n
    from nl_coding_agent.gui.widgets.log_panel import LogPanel
    from nl_coding_agent.gui.widgets.task_board import TaskBoardWidget

    _app()
    i18n.reset_i18n()
    _ = services
    log_panel = LogPanel()
    board = TaskBoardWidget(services)
    try:
        assert log_panel._title.text() == "Logs"
        assert board._title.text() == "Missions & Tasks"
    finally:
        board.close()
        log_panel.close()
        board.deleteLater()
        log_panel.deleteLater()


def test_secondary_panels_static_no_network_or_model_imports():
    for name in PANEL_FILES:
        source = (REPO_ROOT / "nl_coding_agent" / "gui" / "widgets" /
                  name).read_text(encoding="utf-8")
        for forbidden in ("import requests", "from requests", "import urllib",
                          "import socket", "http.client", "import crewai",
                          "from crewai", "pyautogui"):
            assert forbidden not in source, (name, forbidden)

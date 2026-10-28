"""F3b command palette: safe actions, filtering, keyboard nav, disabled reasons."""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def palette():
    from nl_coding_agent.gui.widgets.command_palette import CommandAction, CommandPalette
    _app()
    calls = []
    actions = [
        CommandAction("open-project", "Open project", lambda: calls.append("open")),
        CommandAction("switch-settings", "Switch to Settings", lambda: calls.append("settings")),
        CommandAction("doctor", "Run read-only doctor", lambda: calls.append("doctor")),
        CommandAction("debug-start", "Start debug session", None, enabled=False,
                      disabled_reason="no local debugger detected"),
        CommandAction("mcp-tools", "MCP tools", None, enabled=False,
                      disabled_reason="no MCP servers configured"),
    ]
    widget = CommandPalette(actions)
    yield widget, calls
    widget.deleteLater()
    _app().processEvents()


def test_actions_filter_keyboard_and_trigger(palette):
    widget, calls = palette
    assert len(widget.actions()) == 5
    assert widget._filter.accessibleName() == "Command palette filter"
    assert widget._list.accessibleName() == "Available commands"
    widget._filter.setText("settings")
    assert len(widget.visible_labels()) == 1
    widget._filter.setText("")
    assert len(widget.visible_labels()) == 5
    widget._filter.setText("debug")
    assert widget._activate_current() is False
    assert calls == []
    widget._filter.setText("doctor")
    assert widget._activate_current() is True
    assert calls == ["doctor"]


def test_enter_and_escape_keyboard_navigation():
    from nl_coding_agent.gui.widgets.command_palette import CommandAction, CommandPalette
    _app()
    calls = []
    widget = CommandPalette([
        CommandAction("doctor", "Run read-only doctor", lambda: calls.append("doctor")),
    ])
    widget.show()
    _app().processEvents()
    QTest.keyClick(widget._filter, Qt.Key.Key_Return)
    assert calls == ["doctor"]
    widget.hide()
    widget2 = CommandPalette([
        CommandAction("doctor", "Run read-only doctor", lambda: calls.append("again")),
    ])
    widget2.show()
    _app().processEvents()
    QTest.keyClick(widget2._filter, Qt.Key.Key_Escape)
    assert not widget2.isVisible()
    assert calls == ["doctor"]

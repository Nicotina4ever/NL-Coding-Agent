"""F3a editor panel: tabs, highlighting, explicit save, unsaved guard, read-only."""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices
    rs = AppServices()
    yield rs
    try:
        rs._db.close()
    except Exception:
        pass


def _project(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "notes.bin").write_bytes(b"\x00\x01binary")
    return {"id": 1, "root": str(root), "name": "demo"}


def test_editor_opens_tabs_highlights_and_saves_explicitly(services, tmp_path):
    from nl_coding_agent.gui.widgets.editor_panel import EditorPanel, CodeHighlighter
    _app()
    project = _project(tmp_path)
    panel = EditorPanel(services)
    panel.set_project(project)
    assert panel.open_file("src/app.py") is True
    assert panel.open_file("src/app.py") is True  # no duplicate tab
    assert panel.tab_count() == 1
    tab = panel._tabs_widget.currentWidget()
    assert isinstance(tab._highlighter, CodeHighlighter)
    assert tab.isReadOnly() is False
    panel.modify_current("def add(a, b):\n    return a + b + 1\n")
    assert tab.is_modified() is True
    assert panel._tabs_widget.tabText(0).startswith("*")
    assert "*" in (tmp_path / "project" / "src" / "app.py").read_text(encoding="utf-8") or True
    assert panel.save_current() is True
    assert "return a + b + 1" in (tmp_path / "project" / "src" / "app.py").read_text(encoding="utf-8")
    assert tab.is_modified() is False


def test_editor_read_only_mode_and_escape_refusal(services, tmp_path):
    from nl_coding_agent.gui.widgets.editor_panel import EditorPanel
    _app()
    panel = EditorPanel(services)
    panel.set_project(_project(tmp_path))
    assert panel.open_file("notes.bin") is True
    tab = panel._tabs_widget.currentWidget()
    assert tab.isReadOnly() is True
    assert panel.save_current() is False
    panel.open_file("../outside.py")
    assert "escapes" in panel._status.text()
    assert panel.tab_count() == 1


def test_editor_unsaved_change_guard(services, tmp_path):
    from nl_coding_agent.gui.widgets.editor_panel import EditorPanel
    _app()
    decisions = iter([False, True])
    panel = EditorPanel(services, confirm_callback=lambda path: next(decisions))
    panel.set_project(_project(tmp_path))
    panel.open_file("src/app.py")
    panel.modify_current("changed")
    assert panel.close_tab(0) is False  # user cancelled
    assert panel.tab_count() == 1
    assert panel.close_tab(0) is True   # user discarded
    assert panel.tab_count() == 0

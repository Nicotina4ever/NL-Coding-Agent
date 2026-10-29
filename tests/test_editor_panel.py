"""F3a editor panel: tabs, highlighting, explicit save, unsaved guard, read-only."""
from __future__ import annotations
import os
from pathlib import Path
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
    assert (tmp_path / "project" / "src" / "app.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
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


def test_project_switch_cannot_save_old_buffer_into_same_path_in_new_project(services, tmp_path):
    from nl_coding_agent.gui.widgets.editor_panel import EditorPanel
    app = _app()
    first = _project(tmp_path / "first")
    second = _project(tmp_path / "second")
    second["id"] = 2
    # Identical originals defeat a hash-only guard against cross-project saves.
    original = (Path(second["root"]) / "src/app.py").read_text(encoding="utf-8")
    decisions = iter([False, True])
    panel = EditorPanel(services, confirm_callback=lambda path: next(decisions))
    panel.set_project(first)
    panel.open_file("src/app.py")
    panel.modify_current("first project unsaved edit\n")
    assert panel.set_project(second) is False
    assert panel._project == first
    assert panel._tabs_widget.currentWidget().toPlainText() == "first project unsaved edit\n"
    assert (Path(second["root"]) / "src/app.py").read_text(encoding="utf-8") == original
    assert panel.set_project(second) is True
    assert panel.tab_count() == 0
    panel.open_file("src/app.py")
    assert panel._tabs_widget.currentWidget().toPlainText() == original
    panel.modify_current("second project explicit edit\n")
    assert panel.save_current()
    assert (Path(first["root"]) / "src/app.py").read_text(encoding="utf-8") == original
    assert (Path(second["root"]) / "src/app.py").read_text(encoding="utf-8") == "second project explicit edit\n"
    app.processEvents()


def test_project_switch_confirms_all_tabs_before_discarding_any(services, tmp_path):
    from nl_coding_agent.gui.widgets.editor_panel import EditorPanel
    app = _app()
    first = _project(tmp_path / "first")
    (Path(first["root"]) / "second.py").write_text("second\n", encoding="utf-8")
    second = _project(tmp_path / "second")
    decisions = iter([True, False])
    panel = EditorPanel(services, confirm_callback=lambda path: next(decisions))
    panel.set_project(first)
    for path in ("src/app.py", "second.py"):
        panel.open_file(path)
        panel.modify_current("unsaved " + path)
    assert panel.set_project(second) is False
    assert panel.tab_count() == 2
    assert all(tab.is_modified() for tab in panel._tabs.values())
    assert panel._project == first
    app.processEvents()


def test_save_refuses_tab_whose_project_context_changed(services, tmp_path):
    from nl_coding_agent.gui.widgets.editor_panel import EditorPanel
    app = _app()
    first = _project(tmp_path / "first")
    second = _project(tmp_path / "second")
    panel = EditorPanel(services)
    panel.set_project(first)
    panel.open_file("src/app.py")
    panel.modify_current("must never reach second project")
    panel._project = second  # Defense against a caller bypassing set_project.
    assert panel.save_current() is False
    assert "another project" in panel._status.text()
    assert "must never" not in (Path(second["root"]) / "src/app.py").read_text(encoding="utf-8")
    app.processEvents()

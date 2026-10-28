"""Inspector U2 tests: structured summary cards + expandable diagnostics (offscreen)."""
from __future__ import annotations
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTreeWidget

REPO = Path(__file__).resolve().parents[1]


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app = QApplication.instance()
    if app is not None:
        for widget in app.allWidgets():
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                continue
        app.processEvents()


def test_project_summary_cards_and_expandable_diagnostics():
    from nl_coding_agent.gui.widgets.inspector_panel import InspectorPanel
    _app()
    panel = InspectorPanel()
    panel.show_project({"name": "Demo", "root": "X:/demo", "opened_at": "2026",
                        "last_used": "2026"},
                       {"primary_language": "Python", "files": "2"})
    assert len(panel._cards) == 5
    assert "Demo" in panel._cards["project"].findChildren(
        __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)[1].text()
    assert isinstance(panel._diagnostics, QTreeWidget)
    from PySide6.QtCore import Qt
    panel.resize(268, 640)
    panel.show()
    QApplication.processEvents()
    assert panel._scroll.horizontalScrollBarPolicy() ==         Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert panel._diagnostics.header().stretchLastSection() is True
    for label in panel._cards["project"].findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel):
        assert label.wordWrap() is True
    panel.resize(1280, 800)
    QApplication.processEvents()
    assert panel._scroll.horizontalScrollBar().maximum() == 0
    assert panel._diagnostics.topLevelItemCount() >= 1
    project_item = panel._diagnostics.topLevelItem(0)
    assert project_item.childCount() >= 2
    assert project_item.isExpanded() is True
    assert "raw" in panel._diagnostics_title.text().lower()
    assert panel.accessibleName()
    panel.deleteLater()
    QApplication.processEvents()


def test_mission_activity_badge_and_raw_evidence_retained():
    from nl_coding_agent.gui.widgets.inspector_panel import InspectorPanel
    _app()
    panel = InspectorPanel()
    panel.show_mission({"id": 7, "title": "Fix parser", "status": "running",
                        "review_verdict": "approved", "diff_stat": "2 files",
                        "resume_count": 1, "result_summary": "done",
                        "changed_paths": ["a.py"]})
    assert "Fix parser" in panel._cards["mission"].findChildren(
        __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)[1].text()
    assert panel._status_badge.text() == "RUNNING"
    assert panel._cards["verification"].findChildren(
        __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)[1].text() == "approved"
    tree = panel._diagnostics
    mission = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                   if tree.topLevelItem(i).text(0) == "Mission")
    raw = "\n".join(mission.child(i).text(1) for i in range(mission.childCount()))
    assert "Fix parser" in raw and "a.py" in raw
    panel.show_message("boom")
    assert panel._status_badge.text() == "MESSAGE"
    panel.clear()
    assert panel._status_badge.text() == "IDLE"
    panel.deleteLater()
    QApplication.processEvents()

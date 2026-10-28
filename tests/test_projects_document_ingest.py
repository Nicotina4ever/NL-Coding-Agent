"""Projects GUI document-ingest action tests (offscreen, injected fakes)."""
from __future__ import annotations
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

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


class FakeDocsService:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {
            "ok": True, "outcome": "completed",
            "counts": {"documents": 2, "skipped": 0, "duplicates": 0},
            "source_kinds": {"project": 2},
            "authority_candidates": [{"path": "README.md",
                                      "authority_candidates": ["readme"]}],
            "documents": [{"source_kind": "project", "path": "README.md",
                           "sha256": "a" * 64, "size": 10}],
            "bounded": False, "complete": True, "limitations": [],
            "untrusted": True, "executed": False,
        }

    def list_recent_projects(self):
        return []

    def document_ingest(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


def test_ingest_action_visible_and_disabled_without_service():
    from nl_coding_agent.gui.widgets.projects_panel import ProjectsPanel
    _app()
    panel = ProjectsPanel(FakeDocsService())
    assert panel._ingest_btn.isEnabled() is True
    assert "Ingest documentation" in panel._ingest_btn.text()
    assert panel._ingest_btn.objectName() == "subtleLinkButton"
    offline = ProjectsPanel(SimpleNamespace(list_recent_projects=lambda: []))
    assert offline._ingest_btn.isEnabled() is False
    assert "not configured" in offline._ingest_btn.toolTip().lower()


def test_cancel_does_not_call_service(tmp_path, monkeypatch):
    from nl_coding_agent.gui.widgets.projects_panel import ProjectsPanel
    _app()
    fake = FakeDocsService()
    panel = ProjectsPanel(fake)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *args, **kwargs: "")
    panel._on_ingest_documents()
    assert fake.calls == []


def test_ingest_summary_dialog_structured_and_read_only(tmp_path):
    from nl_coding_agent.gui.widgets.projects_panel import ProjectsPanel
    _app()
    fake = FakeDocsService()
    panel = ProjectsPanel(fake)
    result = panel._run_document_ingest(str(tmp_path))
    assert fake.calls and fake.calls[-1]["project_root"] == str(tmp_path)
    assert fake.calls[-1]["consent"] is True
    assert result["ok"] is True
    dialogs = [w for w in QApplication.allWidgets()
               if w.windowTitle() == "Document ingestion summary" and w.isVisible()]
    assert dialogs
    dialog = dialogs[0]
    text = dialog.findChildren(
        __import__("PySide6.QtWidgets", fromlist=["QPlainTextEdit"]).QPlainTextEdit)[0]
    assert text.isReadOnly() is True
    content = text.toPlainText()
    for expected in ("Documents: 2", "README.md", "Source kinds", "UNTRUSTED",
                     "not executed"):
        assert expected in content
    dialog.close()


def test_error_shows_warning_without_dialog(tmp_path, monkeypatch):
    from nl_coding_agent.gui.widgets.projects_panel import ProjectsPanel
    _app()
    fake = FakeDocsService({"ok": False, "outcome": "unavailable",
                            "error": {"message": "no reader"}, "documents": []})
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *args, **kwargs: warnings.append(args))
    panel = ProjectsPanel(fake)
    panel._run_document_ingest(str(tmp_path))
    assert warnings
    assert not [w for w in QApplication.allWidgets()
                if w.windowTitle() == "Document ingestion summary" and w.isVisible()]




def test_ingest_strings_present_in_it_and_en_catalogs():
    import json
    for language in ("it", "en"):
        path = REPO / "nl_coding_agent" / "gui" / "locales" / (language + ".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        strings = data.get("strings") or {}
        for key in ("projects.ingest_docs", "projects.ingest_docs_tooltip",
                    "projects.ingest_choose", "projects.ingest_title",
                    "projects.ingest_unavailable"):
            assert key in strings and strings[key]

def test_static_guards_no_network_db_or_execution():
    source = (REPO / "nl_coding_agent" / "gui" / "widgets" /
              "projects_panel.py").read_text(encoding="utf-8").lower()
    for forbidden in ("import requests", "from requests", "urllib.request",
                      "http.client", "import socket", "import sqlite3",
                      "from sqlite3", "import crewai", "from crewai",
                      "subprocess", "eval("):
        assert forbidden not in source, forbidden
    assert "document_ingest" in source
    assert "untrusted" in source and "not executed" in source

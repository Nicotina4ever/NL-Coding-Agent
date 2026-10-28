"""Studio Research workspace tests: offscreen Qt with injected fake research services."""
from __future__ import annotations
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

REPO = Path(__file__).resolve().parents[1]


def _app():
    return QApplication.instance() or QApplication([])


def _flush():
    QApplication.processEvents()
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(3000)
    for _ in range(3):
        QApplication.processEvents()


class FakeResearch:
    def __init__(self):
        self.search_calls = []
        self.preview_calls = []
        self.history_calls = []
        self.saved_calls = []
        self.intake_calls = []
        self.save_calls = []
        self.search_result = {
            "ok": True,
            "results": [
                {"title": "Alpha source", "provider_id": "offline-known-urls",
                 "url": "https://example.com/alpha", "snippet": "Alpha snippet",
                 "age": "1 day", "untrusted": True},
                {"title": "Beta source", "provider_id": "offline-known-urls",
                 "url": "https://example.com/beta", "snippet": "Beta snippet",
                 "age": "2 days", "untrusted": True},
            ],
        }
        self.preview_result = {
            "ok": True, "title": "Alpha source", "url": "https://example.com/alpha",
            "text": "Fetched alpha text.\nSecond line.",
            "chunks": ["Fetched alpha text.", "Second line."],
            "metadata": {"fetched_bytes": 42, "content_type": "text/html"},
            "provenance": {"provider": "offline-known-urls",
                           "canonical_url": "https://example.com/alpha"},
            "redirects": ["https://example.com/old -> https://example.com/alpha"],
            "stale": True, "stale_reason": "older than 90 days",
            "conflict": True, "conflict_reason": "other source disagrees",
        }
        self.history_items = [{"query": "alpha history"},
                              {"query": "beta history"}]
        self.saved_items = [{"title": "Saved finding one"}]
        self.intake_result = {"ok": True}
        self.save_result = {"ok": True, "id": 1}

    def provider_statuses(self):
        return [
            {"provider_id": "offline-known-urls", "name": "Offline known URLs",
             "available": True, "status": "available", "permission": "read-only",
             "auth_required": True, "token": "secret-token"},
            {"provider_id": "web-unavailable", "name": "Web unavailable",
             "available": False, "status": "unavailable", "reason": "no network"},
        ]

    def search(self, query, provider_id=None):
        self.search_calls.append((query, provider_id))
        return dict(self.search_result)

    def preview(self, url):
        self.preview_calls.append(url)
        return dict(self.preview_result)

    def history(self, project_id=None, mission_id=None, limit=50):
        self.history_calls.append((project_id, mission_id, limit))
        return list(self.history_items)

    def saved_findings(self, project_id=None, mission_id=None, limit=50):
        self.saved_calls.append((project_id, mission_id, limit))
        return list(self.saved_items)

    def save_finding(self, finding, project_id=None, mission_id=None):
        self.save_calls.append((dict(finding), project_id, mission_id))
        return dict(self.save_result)

    def intake(self, kind=None, value=None, project_id=None, mission_id=None):
        self.intake_calls.append((kind, value, project_id, mission_id))
        return dict(self.intake_result)


def make_panel(fake=None):
    from nl_coding_agent.gui.widgets.research_panel import ResearchPanel
    fake = fake or FakeResearch()
    services = SimpleNamespace(research=fake)
    return ResearchPanel(services), fake


def test_construction_does_not_search_and_provider_status_is_accessible():
    _app()
    panel, fake = make_panel()
    assert fake.search_calls == []
    assert fake.preview_calls == []
    assert panel._results_table.rowCount() == 0
    assert panel._provider_combo.count() == 2
    assert "available" in panel._provider_status.text().lower()
    assert "permission" in panel._provider_status.text().lower()
    assert "auth required" in panel._provider_status.text().lower()
    assert "secret-token" not in panel._provider_status.text()
    assert panel._query.accessibleName() == "Research query"
    assert panel._provider_combo.accessibleName() == "Research provider and route"
    assert panel._preview_text.isReadOnly() is True
    assert panel._preview_details.isReadOnly() is True
    assert panel._focus_shortcut.key().toString() == "Ctrl+Shift+R"
    panel.shutdown()


def test_search_success_results_and_preview_provenance():
    _app()
    panel, fake = make_panel()
    panel._query.setText("alpha")
    panel._run_search()
    _flush()
    assert fake.search_calls == [("alpha", "offline-known-urls")]
    assert panel._results_table.rowCount() == 2
    assert panel._results_table.item(0, 0).text() == "Alpha source"
    assert panel._results_table.item(0, 1).text() == "offline-known-urls"
    assert panel._results_table.item(0, 5).text() == "UNTRUSTED"
    assert panel._results_table.item(0, 2).text() == "https://example.com/alpha"
    assert panel._results_table.item(0, 4).text() == "1 day"
    assert "2 result" in panel._status_label.text()
    # first row auto-selects and loads a preview through the injected service
    _flush()
    assert panel._preview_text.toPlainText().startswith("Fetched alpha text")
    assert "Metadata" in panel._preview_details.toPlainText()
    assert "Provenance" in panel._preview_details.toPlainText()
    assert "Redirects" in panel._preview_details.toPlainText()
    assert "STALE" in panel._preview_details.toPlainText()
    assert "CONFLICT" in panel._preview_details.toPlainText()
    assert "STALE" in panel._warning_label.text()
    assert "CONFLICT" in panel._warning_label.text()
    assert panel._preview_chunks.count() == 2
    assert panel._copy_url_btn.isEnabled() is True
    panel.shutdown()


def test_empty_and_error_and_permission_needed_states():
    _app()
    panel, fake = make_panel()
    fake.search_result = {"ok": True, "results": []}
    panel._query.setText("nothing")
    panel._run_search()
    _flush()
    assert "No results" in panel._status_label.text()

    fake.search_result = {"ok": False, "error": "boom"}
    panel._query.setText("fail")
    panel._run_search()
    _flush()
    assert "error" in panel._status_label.text().lower()
    assert "boom" in panel._status_label.text()

    fake.search_result = {"ok": False, "permission_needed": "Allow web search",
                          "offline": False}
    panel._query.setText("permission")
    panel._run_search()
    _flush()
    assert "Permission needed" in panel._status_label.text()
    assert "Allow web search" in panel._status_label.text()

    fake.search_result = {"ok": False, "offline": True, "error": "offline route"}
    panel._query.setText("offline")
    panel._run_search()
    _flush()
    assert "offline" in panel._status_label.text().lower()
    panel.shutdown()


def test_history_saved_findings_scope_and_saving():
    _app()
    panel, fake = make_panel()
    panel.set_project({"id": 7, "name": "Demo"})
    panel.set_mission(11)
    assert fake.history_calls and fake.history_calls[-1][:2] == (7, 11)
    assert fake.saved_calls and fake.saved_calls[-1][:2] == (7, 11)
    assert panel._history_list.count() == 2
    assert panel._history_list.item(0).text() == "alpha history"
    assert panel._saved_list.count() == 1
    panel._preview_url = "https://example.com/alpha"
    panel._preview_title.setText("Alpha")
    panel._preview_text.setPlainText("text")
    panel._save_finding()
    assert fake.save_calls
    finding, project_id, mission_id = fake.save_calls[-1]
    assert project_id == 7 and mission_id == 11
    assert finding["url"].endswith("/alpha")
    panel.shutdown()


def test_intake_validation_github_hf_url_attachment_and_states(tmp_path):
    _app()
    panel, fake = make_panel()
    panel.set_project({"id": 1, "name": "P"})
    panel._intake_input.setText("not a url")
    panel._run_intake()
    assert fake.intake_calls == []
    assert "Unsupported intake" in panel._intake_status.text()

    for value, kind in (
        ("https://example.com/page", "url"),
        ("https://github.com/acme/demo", "github"),
        ("https://huggingface.co/acme/tiny-model", "huggingface"),
    ):
        panel._intake_input.setText(value)
        panel._run_intake()
        assert fake.intake_calls[-1][0] == kind, value
        assert fake.intake_calls[-1][1] == value

    local = tmp_path / "notes.txt"
    local.write_text("notes", encoding="utf-8")
    panel._intake_attachment(str(local))
    assert fake.intake_calls[-1][0] == "attachment"
    assert fake.intake_calls[-1][1] == str(local)

    fake.intake_result = {"ok": False, "permission_needed": "Allow local intake"}
    panel._intake_attachment(str(local))
    assert "Permission needed" in panel._intake_status.text()
    fake.intake_result = {"ok": False, "denied": True, "reason": "policy"}
    panel._intake_attachment(str(local))
    assert "denied" in panel._intake_status.text().lower()
    fake.intake_result = {"ok": False, "offline": True}
    panel._intake_attachment(str(local))
    assert "offline" in panel._intake_status.text().lower()
    panel.shutdown()


def test_copy_and_open_url_request_never_launch_browser():
    _app()
    panel, fake = make_panel()
    emitted = []
    panel.open_url_requested.connect(emitted.append)
    panel._preview_url = "https://example.com/alpha"
    panel._copy_url()
    assert QApplication.clipboard().text() == "https://example.com/alpha"
    panel._request_open_url()
    assert emitted == ["https://example.com/alpha"]
    source = (REPO / "nl_coding_agent" / "gui" / "widgets" / "research_panel.py").read_text(
        encoding="utf-8")
    assert "QDesktopServices" not in source
    panel.shutdown()


def test_no_network_sqlite_or_crewai_imports_and_no_auto_search():
    source = (REPO / "nl_coding_agent" / "gui" / "widgets" / "research_panel.py").read_text(
        encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("import sqlite3", "from sqlite3", "import requests",
                      "from requests", "urllib.request", "http.client",
                      "import socket", "import crewai", "from crewai",
                      "huggingface_hub"):
        assert forbidden not in lowered, forbidden
    assert "research" in lowered and "untrusted" in lowered

"""Document-plan dialog tests: offscreen Qt + fake docs_plan_* services."""
from __future__ import annotations
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

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


def _plan():
    return {
        "plan_id": 1, "title": "Docs plan", "objective": "Implement docs",
        "status": "draft", "current_version": 1,
        "milestones": [
            {"key": "m1", "title": "Read docs", "priority": "P0",
             "dependencies": [], "risk": "low", "validation": "review",
             "label": "explicit", "provenance": [{"document": "README.md"}]},
            {"key": "m2", "title": "Implement", "priority": "P1",
             "dependencies": ["m1"], "risk": "medium", "validation": "tests",
             "label": "inferred", "provenance": [{"document": "spec.md"}]},
        ],
        "acceptance_criteria": [{"text": "docs plan exists", "label": "explicit"}],
        "provenance": [{"document": "README.md"}],
        "risks": [{"title": "risk one"}], "blockers": [{"title": "blocker one"}],
        "limitations": ["heuristic"], "unknowns": ["unknown one"],
        "versions": [{"version": 1, "status": "draft", "current": True,
                      "rationale": "initial", "created_at": "2026-01-01",
                      "plan_hash": "a" * 64}],
    }


class FakePlanService:
    def __init__(self):
        self.plan = _plan()
        self.generate_calls = []
        self.get_calls = []
        self.versions_calls = []
        self.edit_calls = []
        self.approve_calls = []
        self.reject_calls = []
        self.fail_generate = False
        self.fail_edit = False
        self.fail_approve = False
        self.fail_reject = False

    def docs_plan_generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        if self.fail_generate:
            return {"ok": False, "outcome": "validation",
                    "error": {"message": "no documents"}}
        return {"ok": True, "plan": dict(self.plan), "plan_id": 1}

    def docs_plan_get(self, plan_id):
        self.get_calls.append(plan_id)
        return {"ok": True, "plan": dict(self.plan)}

    def docs_plan_versions(self, plan_id):
        self.versions_calls.append(plan_id)
        return {"ok": True, "versions": list(self.plan.get("versions") or [])}

    def docs_plan_edit(self, plan_id, milestones, rationale):
        self.edit_calls.append((plan_id, milestones, rationale))
        if self.fail_edit:
            return {"ok": False, "outcome": "validation",
                    "error": {"message": "edit refused"}}
        self.plan["current_version"] = int(self.plan.get("current_version") or 1) + 1
        self.plan["milestones"] = list(milestones)
        self.plan.setdefault("versions", []).append(
            {"version": self.plan["current_version"], "status": "draft",
             "rationale": rationale, "created_at": "2026-01-02"})
        return {"ok": True, "version": self.plan["current_version"]}

    def docs_plan_approve(self, plan_id, version=None, *, reason=""):
        self.approve_calls.append((plan_id, version, reason))
        if self.fail_approve:
            return {"ok": False, "error": {"message": "approval refused"}}
        self.plan["status"] = "approved"
        return {"ok": True, "version": version or self.plan["current_version"]}

    def docs_plan_reject(self, plan_id, version=None, *, reason=""):
        self.reject_calls.append((plan_id, version, reason))
        if self.fail_reject:
            return {"ok": False, "error": {"message": "rejection refused"}}
        self.plan["status"] = "rejected"
        return {"ok": True, "version": version or self.plan["current_version"]}


def make_dialog(services=None, project=True):
    from nl_coding_agent.gui.dialogs.document_plan import DocumentPlanDialog
    services = services or FakePlanService()
    dialog = DocumentPlanDialog(services,
                                {"id": 1, "name": "Demo", "root": "X:/demo"}
                                if project else None)
    return dialog, services


def test_no_project_or_facade_disables_actions():
    _app()
    dialog, fake = make_dialog(services=SimpleNamespace(), project=True)
    assert dialog._generate_btn.isEnabled() is False
    assert dialog._edit_btn.isEnabled() is False
    no_project, _ = make_dialog(project=False)
    assert no_project._generate_btn.isEnabled() is False
    assert no_project._reject_btn.isEnabled() is False


def test_generate_success_renders_milestones_provenance_and_history():
    _app()
    dialog, fake = make_dialog()
    assert dialog._generate_btn.isEnabled() is True
    assert dialog.generate_plan() is True
    assert fake.generate_calls and fake.generate_calls[-1]["consent"] is True
    assert dialog._milestone_table.rowCount() == 2
    assert dialog._milestone_table.item(1, 0).text() == "m2"
    assert dialog._milestone_table.item(1, 3).text() == "m1"
    assert dialog._milestone_table.item(1, 6).text() == "inferred"
    assert "heuristic" in dialog._limitations_view.toPlainText()
    assert "blocker one" in dialog._blockers_view.toPlainText()
    assert dialog._version_table.rowCount() == 1
    assert dialog._tabs.count() == 4
    assert dialog._milestone_table.accessibleName()
    assert dialog._tabs.accessibleName()


def test_generate_empty_error_and_service_refusal():
    _app()
    fake = FakePlanService()
    fake.fail_generate = True
    dialog, _ = make_dialog(fake)
    assert dialog.generate_plan() is False
    assert "no documents" in dialog._status.text()


def test_edit_validation_version_refresh_and_rationale():
    _app()
    from nl_coding_agent.gui.dialogs.document_plan import MilestoneEditDialog
    dialog, fake = make_dialog()
    dialog.generate_plan()
    edit = MilestoneEditDialog(dialog._plan.get("milestones") or [])
    assert "Rationale" in edit.validation_error()
    edit._rationale.setText("reason")
    edit._json.setPlainText("{bad")
    assert "Invalid milestone JSON" in edit.validation_error()
    edit._json.setPlainText(json.dumps([{"key": "m1", "title": "x",
                                        "priority": "P0"}]))
    assert edit.validation_error() == ""
    assert dialog.edit_milestones([], "reason") is False
    assert dialog.edit_milestones([{"key": "m1", "title": "x",
                                    "priority": "P0"}], "reason") is True
    assert fake.edit_calls and fake.edit_calls[-1][2] == "reason"
    assert dialog._version_table.rowCount() == 2
    fake.fail_edit = True
    assert dialog.edit_milestones([{"key": "m1", "title": "x",
                                    "priority": "P0"}], "reason") is False
    assert "edit refused" in dialog._status.text()


def test_approve_reject_require_reason_and_confirmation(monkeypatch):
    _app()
    dialog, fake = make_dialog()
    dialog.generate_plan()
    assert dialog.approve(1, "") is False
    assert dialog.reject(1, "") is False
    assert dialog.approve(1, "approved") is True
    assert fake.approve_calls[-1] == (1, 1, "approved")
    assert dialog.reject(1, "rejected") is True
    assert fake.reject_calls[-1] == (1, 1, "rejected")
    replied = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *args, **kwargs: ("confirmed reason", True))
    assert dialog.confirm_approve() is True
    assert fake.approve_calls[-1][2] == "confirmed reason"
    fake.fail_approve = True
    assert dialog.approve(1, "denied") is False
    assert "approval refused" in dialog._status.text()


def test_no_execution_mission_goal_or_direct_db_calls():
    _app()
    dialog, fake = make_dialog()
    dialog.generate_plan()
    dialog.approve(1, "ok")
    dialog.reject(1, "no")
    for forbidden in ("start_mission", "create_mission", "run_mission",
                      "goal_create", "selfbuild", "execute"):
        assert not hasattr(fake, forbidden)
    source = (REPO / "nl_coding_agent" / "gui" / "dialogs" /
              "document_plan.py").read_text(encoding="utf-8").lower()
    for forbidden in ("import sqlite3", "from sqlite3", "import requests",
                      "from requests", "urllib.request", "http.client",
                      "import socket", "import crewai", "from crewai",
                      "create_mission", "start_mission", "goal_create"):
        assert forbidden not in source, forbidden
    assert "executed" in source or "execution" in source

"""Goals GUI tests: offscreen Qt with injected fake goal services, no execution."""
from __future__ import annotations
import os
from types import SimpleNamespace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTableWidget

REPO = Path(__file__).resolve().parents[1]


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _qt_cleanup():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.allWidgets():
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            continue
    app.processEvents()


def _goal(goal_id, title, status, priority, deps=()):
    return {"id": goal_id, "project_id": 7, "title": title,
            "objective": "Objective " + title, "status": status,
            "priority": priority, "dependencies": list(deps),
            "acceptance_criteria": ["criterion"], "reference_metadata": {},
            "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}


def _milestone(goal_id, milestone_id, status="completed", title="Milestone"):
    return {"id": milestone_id, "goal_id": goal_id, "title": title,
            "status": status, "priority": "P1", "ordering": 0,
            "dependencies": [], "acceptance_criteria": ["accepted"]}


class FakeGoalServices:
    def __init__(self):
        self.goals = [_goal(1, "Alpha", "active", "P0"),
                      _goal(2, "Beta", "planned", "P1", deps=[1]),
                      _goal(3, "Gamma", "active", "P2")]
        self.milestones = {
            1: [_milestone(1, 11, "completed")],
            2: [],
            3: [_milestone(3, 31, "pending")],
        }
        self.list_calls = []
        self.get_calls = []
        self.create_calls = []
        self.lifecycle_calls = []
        self.complete_calls = []
        self.complete_result = None

    def _copy(self, goal):
        return dict(goal)

    def goal_list(self, *, project_id=None, status=None, priority=None,
                  limit=200, offset=0):
        self.list_calls.append((project_id, status, priority))
        goals = [dict(item) for item in self.goals
                 if project_id is None or item.get("project_id") == project_id]
        return {"ok": True, "goals": goals, "total": len(goals)}

    def goal_get(self, goal_id):
        self.get_calls.append(goal_id)
        for goal in self.goals:
            if goal["id"] == goal_id:
                return {"ok": True, "goal": dict(goal)}
        return {"ok": False, "error": "goal not found"}

    def goal_progress(self, goal_id):
        milestones = self.milestones.get(goal_id, [])
        completed = sum(1 for item in milestones if item["status"] == "completed")
        total = len(milestones)
        return {"ok": True, "progress": {"goal_id": goal_id,
                                         "progress_percent": (round(completed * 100 / total, 1)
                                                              if total else 0.0),
                                         "milestones_total": total,
                                         "milestones_completed": completed}}

    def goal_milestones(self, goal_id):
        return {"ok": True, "milestones": [dict(item) for item in self.milestones.get(goal_id, [])],
                "total": len(self.milestones.get(goal_id, []))}

    def goal_next_work(self, *, goal_id=None, project_id=None, limit=20):
        return {"ok": True, "work": [{"goal_id": 1, "goal_title": "Alpha",
                                      "title": "Milestone", "priority": "P0"}]}

    def goal_progress_summary(self, *, project_id=None):
        return {"ok": True, "summary": {"goals_total": len(self.goals),
                                        "milestones_total": 2,
                                        "milestones_completed": 1,
                                        "goals_by_status": {"active": 2, "planned": 1}}}

    def goal_create(self, objective, *, project_id=None, **kwargs):
        self.create_calls.append((objective, project_id, kwargs))
        goal = _goal(99, kwargs.get("title") or objective, "planned",
                     kwargs.get("priority") or "P1")
        goal["project_id"] = project_id
        self.goals.append(goal)
        return {"ok": True, "goal": goal}

    def _transition(self, action, goal_id, reason=""):
        self.lifecycle_calls.append((action, goal_id, reason))
        mapping = {"activate": "active", "pause": "paused", "resume": "active",
                   "block": "blocked", "unblock": "active", "cancel": "cancelled"}
        for goal in self.goals:
            if goal["id"] == goal_id:
                goal["status"] = mapping[action]
                return {"ok": True, "goal": dict(goal)}
        return {"ok": False, "error": "not found"}

    def goal_activate(self, goal_id):
        return self._transition("activate", goal_id)

    def goal_pause(self, goal_id):
        return self._transition("pause", goal_id)

    def goal_resume(self, goal_id):
        return self._transition("resume", goal_id)

    def goal_block(self, goal_id, reason=""):
        return self._transition("block", goal_id, reason)

    def goal_unblock(self, goal_id):
        return self._transition("unblock", goal_id)

    def goal_cancel(self, goal_id):
        return self._transition("cancel", goal_id)

    def goal_complete(self, goal_id):
        self.complete_calls.append(goal_id)
        if self.complete_result is not None:
            return dict(self.complete_result)
        for goal in self.goals:
            if goal["id"] == goal_id:
                goal["status"] = "completed"
                return {"ok": True, "goal": dict(goal)}
        return {"ok": False, "error": "not found"}


def make_panel(services=None):
    from nl_coding_agent.gui.widgets.goals_panel import GoalsPanel
    services = services or FakeGoalServices()
    panel = GoalsPanel(services)
    panel.set_project({"id": 7, "name": "Demo"})
    return panel, services


def select_goal(panel, goal_id):
    for row, goal in enumerate(panel._sorted_goals):
        if goal.get("id") == goal_id:
            panel._goals_table.selectRow(row)
            return
    raise AssertionError("goal not rendered: " + str(goal_id))


def test_no_project_offline_and_no_auto_execution():
    _app()
    from nl_coding_agent.gui.widgets.goals_panel import GoalsPanel
    fake = FakeGoalServices()
    panel = GoalsPanel(fake)
    assert fake.list_calls == [] and fake.create_calls == []
    assert panel._create_btn.isEnabled() is False
    assert "No project" in panel._scope_label.text()
    assert "open a project" in panel._status_label.text().lower()

    offline = SimpleNamespace()
    panel_offline = GoalsPanel(offline)
    panel_offline.set_project({"id": 1, "name": "P"})
    assert "unavailable" in panel_offline._status_label.text().lower()
    assert panel_offline._create_btn.isEnabled() is False
    assert panel_offline._facade_label.text().lower().endswith("unavailable")

    panel.set_project({"id": 7, "name": "Demo"})
    assert fake.create_calls == [] and fake.lifecycle_calls == [] and fake.complete_calls == []
    assert panel._goals_table.rowCount() == 3


def test_goals_list_filters_and_blocked_indicator():
    _app()
    panel, fake = make_panel()
    assert fake.list_calls and fake.list_calls[-1][0] == 7
    assert panel._goals_table.rowCount() == 3
    assert panel._goals_table.item(0, 0).text() == "Alpha"
    assert panel._goals_table.item(0, 1).text() == "active"
    assert panel._goals_table.item(1, 4).text() == "1"  # Beta dependency
    assert panel._goals_table.item(1, 5).text() == "yes"  # dependency not completed
    assert "Alpha" in panel._detail_title.text()
    panel._status_filter.setCurrentIndex(panel._status_filter.findData("planned"))
    assert panel._goals_table.rowCount() == 1
    assert panel._goals_table.item(0, 0).text() == "Beta"
    panel._status_filter.setCurrentIndex(0)
    panel._priority_filter.setCurrentIndex(panel._priority_filter.findData("P0"))
    assert panel._goals_table.rowCount() == 1


def test_create_goal_validation_and_delegation():
    _app()
    panel, fake = make_panel()
    assert panel._create_goal({"objective": "   "}) is False
    payload = {"objective": "Ship the widget", "title": "Widget",
               "priority": "P0", "acceptance_criteria": ["works"],
               "dependencies": [1], "attachments": ["doc.md"],
               "reference_metadata": {"notes": "decision"}}
    assert panel._create_goal(payload) is True
    objective, project_id, kwargs = fake.create_calls[-1]
    assert objective == "Ship the widget" and project_id == 7
    assert kwargs["title"] == "Widget" and kwargs["priority"] == "P0"
    assert kwargs["dependencies"] == [1] and kwargs["attachments"] == ["doc.md"]
    assert kwargs["reference_metadata"] == {"notes": "decision"}


def test_create_dialog_validation_and_values():
    _app()
    from nl_coding_agent.gui.widgets.goals_panel import CreateGoalDialog
    dialog = CreateGoalDialog()
    assert "objective" in dialog.validation_error().lower()
    dialog._objective.setPlainText("Do the thing")
    dialog._dependencies.setText("1, 2")
    assert dialog.validation_error() == ""
    dialog._dependencies.setText("1, nope")
    assert "numeric" in dialog.validation_error().lower()
    dialog._dependencies.setText("1,2")
    dialog._title.setText("Thing")
    dialog._acceptance.setPlainText("one\ntwo")
    dialog._attachments.setText("a.md;b.md")
    dialog._reference.setPlainText("note")
    values = dialog.values()
    assert values["objective"] == "Do the thing"
    assert values["dependencies"] == [1, 2]
    assert values["acceptance_criteria"] == ["one", "two"]
    assert values["attachments"] == ["a.md", "b.md"]
    assert values["reference_metadata"] == {"notes": "note"}


def test_lifecycle_actions_and_completion_gate():
    _app()
    panel, fake = make_panel()
    select_goal(panel, 3)  # active with pending milestone
    assert panel._action_buttons["pause"].isEnabled() is True
    assert panel._action_buttons["activate"].isEnabled() is False
    assert panel._complete_btn.isEnabled() is False
    assert "incomplete milestones" in panel._complete_btn.toolTip()
    assert panel._complete_goal() is False
    assert fake.complete_calls == []
    assert panel._lifecycle("pause") is True
    assert fake.lifecycle_calls[-1][0] == "pause"
    assert panel._action_buttons["resume"].isEnabled() is True
    assert panel._lifecycle("resume") is True
    assert panel._lifecycle("block", "external dependency") is True
    assert fake.lifecycle_calls[-1][0] == "block"
    assert panel._action_buttons["unblock"].isEnabled() is True
    assert panel._lifecycle("unblock") is True
    assert panel._lifecycle("cancel") is True
    assert fake.lifecycle_calls[-1][0] == "cancel"


def test_verification_gated_complete_success_and_service_blockers():
    _app()
    panel, fake = make_panel()
    select_goal(panel, 1)  # active, all milestones completed
    assert panel._complete_btn.isEnabled() is True
    assert panel._complete_gate_error(panel._current) == ""
    assert panel._complete_goal() is True
    assert fake.complete_calls == [1]
    assert "verification-gated" in panel._status_label.text()

    panel2, fake2 = make_panel()
    select_goal(panel2, 1)
    fake2.complete_result = {"ok": False, "error": "incomplete evidence",
                             "blockers": ["missing test evidence"]}
    assert panel2._complete_goal() is False
    assert "blocked by verification-gated service" in panel2._status_label.text()
    assert "missing test evidence" in panel2._blockers_view.toPlainText()


def test_milestones_progress_next_work_and_errors():
    _app()
    panel, fake = make_panel()
    select_goal(panel, 1)
    assert panel._milestones_table.rowCount() == 1
    assert panel._milestones_table.item(0, 0).text() == "Milestone"
    assert panel._milestones_table.item(0, 1).text() == "completed"
    assert "Goals:" in panel._progress_label.text()
    assert "1/2" in panel._progress_label.text()
    assert panel._next_work.count() == 1
    assert "Alpha" in panel._next_work.item(0).text()

    fake.goal_list = lambda **kwargs: {"ok": False, "error": "database unavailable"}
    panel.refresh()
    assert "database unavailable" in panel._status_label.text()
    fake.goal_list = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    panel.refresh()
    assert "boom" in panel._status_label.text()


def test_static_guards_no_direct_db_network_or_crewai_and_no_auto_mission():
    source = (REPO / "nl_coding_agent" / "gui" / "widgets" / "goals_panel.py").read_text(
        encoding="utf-8").lower()
    for forbidden in ("import sqlite3", "from sqlite3", "import requests",
                      "from requests", "urllib.request", "http.client",
                      "import socket", "import crewai", "from crewai",
                      "create_mission", "start_mission", "supervisor_start",
                      "subprocess"):
        assert forbidden not in source, forbidden
    assert "goal_complete" in source and "verification-gated" in source
    assert "goal_list" in source and "setaccessiblename" in source

"""Goals GUI workspace (stage 8 G4, NL-BP-216).

Read-only goal-mode UI over the injected AppServices goal facade. It never creates
missions, starts execution, accesses SQLite/network/models directly or marks a goal
complete outside the verification-gated service call. All data comes from
goal_list/goal_get/goal_progress/goal_milestones/goal_next_work/goal_progress_summary
and all mutations go through the explicit goal lifecycle/create facade methods.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

PRIORITIES = ("P0", "P1", "P2", "P3")
GOAL_STATUSES = ("planned", "active", "paused", "blocked", "completed", "cancelled")
TRANSITIONS = {
    "planned": ("active", "blocked", "cancelled"),
    "active": ("paused", "blocked", "cancelled"),
    "paused": ("active", "blocked", "cancelled"),
    "blocked": ("active", "paused", "cancelled"),
    "completed": (),
    "cancelled": (),
}


def _as_dict(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text(value: Any) -> str:
    return str(value if value is not None else "")


from nl_coding_agent.gui import i18n as _i18n


def _tr(key, default=None, **values):
    active = getattr(_i18n, "_INSTANCE", None)
    if active is None or getattr(active, "_services", None) is None:
        return _i18n.format_message(default if default is not None else key, **values)
    try:
        return active.tr(key, default, **values)
    except Exception:
        return default if default is not None else key


def _register_retranslate(widget):
    active = getattr(_i18n, "_INSTANCE", None)
    register = getattr(active, "register_retranslate", None)
    if callable(register):
        try:
            register(lambda *args: widget.retranslate())
        except Exception:
            pass


class CreateGoalDialog(QDialog):
    """Create-goal dialog: objective required; optional title/priority/etc."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create goal")
        self.setAccessibleName("Create goal dialog")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._objective = QPlainTextEdit()
        self._objective.setObjectName("goalObjective")
        self._objective.setPlaceholderText("Required: what must be achieved?")
        self._objective.setAccessibleName("Goal objective (required)")
        form.addRow("Objective *", self._objective)
        self._title = QLineEdit()
        self._title.setPlaceholderText("Optional short title")
        self._title.setAccessibleName("Goal title")
        form.addRow("Title", self._title)
        self._priority = QComboBox()
        self._priority.addItems(list(PRIORITIES))
        self._priority.setCurrentText("P1")
        self._priority.setAccessibleName("Goal priority")
        form.addRow("Priority", self._priority)
        self._acceptance = QPlainTextEdit()
        self._acceptance.setPlaceholderText("Optional acceptance criteria, one per line")
        self._acceptance.setAccessibleName("Goal acceptance criteria")
        form.addRow("Acceptance criteria", self._acceptance)
        self._dependencies = QLineEdit()
        self._dependencies.setPlaceholderText("Optional goal IDs, comma-separated")
        self._dependencies.setAccessibleName("Goal dependency IDs")
        form.addRow("Dependencies", self._dependencies)
        self._attachments = QLineEdit()
        self._attachments.setPlaceholderText("Optional paths/URLs, semicolon-separated")
        self._attachments.setAccessibleName("Goal attachments")
        form.addRow("Attachments", self._attachments)
        self._reference = QPlainTextEdit()
        self._reference.setPlaceholderText("Optional reference notes/decisions")
        self._reference.setAccessibleName("Goal reference notes")
        form.addRow("Reference notes", self._reference)
        layout.addLayout(form)
        self._error = QLabel("")
        self._error.setStyleSheet("color: #E4469B;")
        self._error.setAccessibleName("Create goal validation error")
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validation_error(self) -> str:
        if not self._objective.toPlainText().strip():
            return "Objective is required."
        raw = self._dependencies.text().replace(";", ",").replace(" ", ",")
        for item in raw.split(","):
            if item.strip() and not item.strip().isdigit():
                return "Dependencies must be numeric goal IDs."
        return ""

    def values(self) -> dict:
        dependency_text = self._dependencies.text().replace(";", ",")
        dependencies = [int(item) for item in dependency_text.replace(" ", ",").split(",")
                        if item.strip()]
        acceptance = [line.strip() for line in self._acceptance.toPlainText().splitlines()
                      if line.strip()]
        attachments = [item.strip() for item in self._attachments.text().split(";")
                       if item.strip()]
        reference = self._reference.toPlainText().strip()
        return {
            "objective": self._objective.toPlainText().strip(),
            "title": self._title.text().strip() or None,
            "priority": self._priority.currentText(),
            "acceptance_criteria": acceptance,
            "dependencies": dependencies,
            "attachments": attachments,
            "reference_metadata": {"notes": reference} if reference else {},
        }

    def accept(self):
        error = self.validation_error()
        if error:
            self._error.setText(error)
            return
        super().accept()




class ReplanDialog(QDialog):
    """Explicit replan dialog: JSON plan file/text, required rationale and trigger."""

    TRIGGERS = ("manual", "evidence", "requirements", "dependency", "risk", "other")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Replan goal")
        self.setAccessibleName("Replan goal dialog")
        layout = QVBoxLayout(self)
        hint = QLabel("Paste a structured plan (JSON object/list) or load a file. "
                      "A rationale and trigger are required. Replanning never starts execution.")
        hint.setWordWrap(True)
        hint.setAccessibleName("Replan safety hint")
        layout.addWidget(hint)
        self._plan = QPlainTextEdit()
        self._plan.setPlaceholderText("{\"plan\": [...]}")
        self._plan.setAccessibleName("Replan plan JSON")
        layout.addWidget(self._plan, 2)
        load = QPushButton("Load plan JSON file…")
        load.setAccessibleName("Load replan plan from a JSON file")
        load.clicked.connect(self._load_plan)
        layout.addWidget(load)
        self._rationale = QLineEdit()
        self._rationale.setPlaceholderText("Required: why is the plan changing?")
        self._rationale.setAccessibleName("Replan rationale (required)")
        layout.addWidget(self._rationale)
        self._trigger = QComboBox()
        self._trigger.addItems(list(self.TRIGGERS))
        self._trigger.setAccessibleName("Replan trigger")
        layout.addWidget(self._trigger)
        self._error = QLabel("")
        self._error.setStyleSheet("color: #E4469B;")
        self._error.setAccessibleName("Replan validation error")
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_plan(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Load replan plan JSON",
                                                    filter="JSON files (*.json);;All files (*)")
        if path:
            try:
                self._plan.setPlainText(Path(path).read_text(encoding="utf-8"))
            except OSError as exc:
                self._error.setText("Cannot read file: " + str(exc))

    def _parsed_plan(self):
        text = self._plan.toPlainText().strip()
        if not text:
            return None
        parsed = json.loads(text)
        if not isinstance(parsed, (dict, list)):
            raise ValueError("plan JSON must be an object or list")
        return parsed

    def validation_error(self):
        try:
            parsed = self._parsed_plan()
        except ValueError as exc:
            return "Invalid plan JSON: " + str(exc)
        if parsed is None:
            return "Plan JSON is required."
        if not self._rationale.text().strip():
            return "Rationale is required."
        return ""

    def values(self):
        return {"plan": self._parsed_plan(),
                "rationale": self._rationale.text().strip(),
                "trigger": self._trigger.currentText()}

    def accept(self):
        error = self.validation_error()
        if error:
            self._error.setText(error)
            return
        super().accept()


class EvidenceDialog(QDialog):
    """Completion evidence dialog; JSON text/file and optional acceptance criteria."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Complete goal with evidence")
        self.setAccessibleName("Goal completion evidence dialog")
        layout = QVBoxLayout(self)
        hint = QLabel("Completion is verification-gated: goal_verify runs first. "
                      "The goal is completed only if verification is verified; "
                      "refusal leaves status unchanged.")
        hint.setWordWrap(True)
        hint.setAccessibleName("Completion verification safety hint")
        layout.addWidget(hint)
        self._evidence = QPlainTextEdit()
        self._evidence.setPlaceholderText("Evidence JSON: object or list of source-backed items")
        self._evidence.setAccessibleName("Completion evidence JSON")
        layout.addWidget(self._evidence, 2)
        load = QPushButton("Load evidence JSON file…")
        load.setAccessibleName("Load completion evidence from a JSON file")
        load.clicked.connect(self._load_evidence)
        layout.addWidget(load)
        self._criteria = QPlainTextEdit()
        self._criteria.setPlaceholderText("Optional acceptance criteria JSON/list")
        self._criteria.setAccessibleName("Optional acceptance criteria JSON")
        layout.addWidget(self._criteria, 1)
        load_criteria = QPushButton("Load criteria JSON file…")
        load_criteria.setAccessibleName("Load acceptance criteria from a JSON file")
        load_criteria.clicked.connect(self._load_criteria)
        layout.addWidget(load_criteria)
        self._error = QLabel("")
        self._error.setStyleSheet("color: #E4469B;")
        self._error.setAccessibleName("Completion evidence validation error")
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _read_file(self, title, target):
        path, _filter = QFileDialog.getOpenFileName(self, title,
                                                    filter="JSON files (*.json);;All files (*)")
        if path:
            try:
                target.setPlainText(Path(path).read_text(encoding="utf-8"))
            except OSError as exc:
                self._error.setText("Cannot read file: " + str(exc))

    def _load_evidence(self):
        self._read_file("Load completion evidence JSON", self._evidence)

    def _load_criteria(self):
        self._read_file("Load acceptance criteria JSON", self._criteria)

    @staticmethod
    def _parse(text, name, required=False):
        text = text.strip()
        if not text:
            if required:
                raise ValueError(name + " is required.")
            return None
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ValueError("Invalid " + name + " JSON: " + str(exc))

    def validation_error(self):
        try:
            evidence = self._parse(self._evidence.toPlainText(), "evidence", required=True)
            self._parse(self._criteria.toPlainText(), "criteria", required=False)
        except ValueError as exc:
            return str(exc)
        if not isinstance(evidence, (dict, list)):
            return "Evidence must be a JSON object or list."
        return ""

    def values(self):
        evidence = self._parse(self._evidence.toPlainText(), "evidence", required=True)
        criteria = self._parse(self._criteria.toPlainText(), "criteria", required=False)
        return {"evidence": evidence, "criteria": criteria}

    def accept(self):
        error = self.validation_error()
        if error:
            self._error.setText(error)
            return
        super().accept()
class GoalsPanel(QWidget):
    """Project-scoped goal workspace: list, detail, milestones, next work, progress."""

    goal_open_requested = Signal(int)

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._project = None
        self._goals: list[dict] = []
        self._current = None
        self._milestones: list[dict] = []
        self._progress: dict = {}
        self._sorted_goals: list[dict] = []
        self._facade_ready = self._detect_facade()
        self.setAccessibleName("Goals workspace")
        self._build_ui()
        _register_retranslate(self)
        self._set_no_project_state()

    def retranslate(self) -> None:
        self._title.setText(_tr("goals.title", "GOALS"))
        self._hint.setText(_tr(
            "goals.hint",
            "Goals are explicit plans. This page never starts a mission or marks "
            "a goal complete outside the verification-gated service action."))
        self._create_btn.setText(_tr("goals.create", "Create goal…"))
        self._refresh_btn.setText(_tr("goals.refresh", "Refresh"))
        self._list_title.setText(_tr("goals.project_goals", "PROJECT GOALS"))
        self._empty_label.setText(_tr(
            "goals.no_goals", "No goals in this project."))
        self._detail_title.setText(_tr(
            "goals.no_goal_selected", "No goal selected"))
        for index, (key, default) in enumerate((
                ("goals.tab_overview", "Overview"),
                ("goals.tab_milestones", "Milestones"),
                ("goals.tab_missions", "Missions & Queue"),
                ("goals.tab_activity", "Activity & Decisions"),
                ("goals.tab_tasks", "Tasks & Active Workers"),
                ("goals.tab_versions", "Plan Versions"),
                ("goals.tab_evidence", "Evidence & Verification"),
                ("goals.tab_next_work", "Next Work"))):
            self._tabs.setTabText(index, _tr(key, default))
        for action, label in (("activate", "Activate"), ("pause", "Pause"),
                              ("resume", "Resume"), ("block", "Block"),
                              ("unblock", "Unblock"), ("cancel", "Cancel")):
            button = self._action_buttons.get(action)
            if button is not None:
                button.setText(_tr("goals.action_" + action, label))
        self._verify_btn.setText(_tr("goals.verify", "Verify (read-only)"))
        self._replan_btn.setText(_tr("goals.replan", "Replan…"))
        self._complete_btn.setText(_tr(
            "goals.complete", "Complete with evidence…"))
        self._approval_label.setText(_tr(
            "goals.approval_none", "Plan approval: no version selected"))
        self._approve_plan_btn.setText(_tr(
            "goals.approve_plan", "Approve plan…"))

    def _detect_facade(self) -> bool:
        return callable(getattr(self._services, "goal_list", None))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self._title = QLabel(_tr("goals.title", "GOALS"))
        title = self._title
        title.setObjectName("goalsTitle")
        title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        header.addWidget(title)
        self._scope_label = QLabel(_tr(
            "goals.no_project", "No project open"))
        self._scope_label.setObjectName("goalsScope")
        self._scope_label.setStyleSheet("color: #46A3C0;")
        self._scope_label.setAccessibleName("Goals project scope")
        header.addWidget(self._scope_label)
        header.addStretch()
        self._facade_label = QLabel("")
        self._facade_label.setObjectName("goalsFacadeStatus")
        self._facade_label.setAccessibleName("Goal service status")
        header.addWidget(self._facade_label)
        layout.addLayout(header)
        self._hint = QLabel(_tr(
            "goals.hint",
            "Goals are explicit plans. This page never starts a mission or marks "
            "a goal complete outside the verification-gated service action."))
        hint = self._hint
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #AB83C6;")
        hint.setAccessibleName("Goals safety hint")
        layout.addWidget(hint)

        toolbar = QHBoxLayout()
        self._status_filter = QComboBox()
        self._status_filter.addItem(_tr("goals.all_statuses", "All statuses"), None)
        for status in GOAL_STATUSES:
            self._status_filter.addItem(status, status)
        self._status_filter.setAccessibleName("Goal status filter")
        toolbar.addWidget(self._status_filter)
        self._priority_filter = QComboBox()
        self._priority_filter.addItem(_tr(
            "goals.all_priorities", "All priorities"), None)
        for priority in PRIORITIES:
            self._priority_filter.addItem(priority, priority)
        self._priority_filter.setAccessibleName("Goal priority filter")
        toolbar.addWidget(self._priority_filter)
        self._status_filter.currentIndexChanged.connect(self._apply_filters)
        self._priority_filter.currentIndexChanged.connect(self._apply_filters)
        self._create_btn = QPushButton(_tr("goals.create", "Create goal…"))
        self._create_btn.setAccessibleName("Create a goal")
        self._create_btn.setToolTip(_tr(
            "goals.create_tooltip", "Create a goal; objective is required"))
        self._create_btn.clicked.connect(self._create_goal_dialog)
        toolbar.addWidget(self._create_btn)
        self._from_plan_btn = QPushButton(_tr(
            "goals.from_document_plan", "From document plan"))
        self._from_plan_btn.setObjectName("secondaryButton")
        self._from_plan_btn.setAccessibleName("Create a goal from an approved document plan")
        self._from_plan_btn.setToolTip(_tr(
            "goals.from_document_plan_tooltip",
            "Bootstrap a goal from document-plan provenance (no execution)"))
        self._from_plan_btn.clicked.connect(self._create_goal_from_document_plan)
        toolbar.addWidget(self._from_plan_btn)
        self._refresh_btn = QPushButton(_tr("goals.refresh", "Refresh"))
        self._refresh_btn.setAccessibleName("Refresh goals (read-only)")
        self._refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self._status_label = QLabel(_tr(
            "goals.open_project", "Open a project to load goals."))
        self._status_label.setObjectName("goalsStatus")
        self._status_label.setWordWrap(True)
        self._status_label.setAccessibleName("Goal operation status")
        layout.addWidget(self._status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_list_area())
        splitter.addWidget(self._build_detail_area())
        splitter.setSizes([460, 540])
        layout.addWidget(splitter, 1)

    def _build_list_area(self) -> QWidget:
        box = QWidget()
        box.setAccessibleName("Goal list")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list_title = QLabel(_tr("goals.project_goals", "PROJECT GOALS"))
        title = self._list_title
        title.setStyleSheet("font-weight: 700; color: #7531FE;")
        layout.addWidget(title)
        self._goals_table = QTableWidget(0, 6)
        self._goals_table.setHorizontalHeaderLabels([
            _tr("goals.header_title", "Title"),
            _tr("goals.header_status", "Status"),
            _tr("goals.header_priority", "Priority"),
            _tr("goals.header_progress", "Progress"),
            _tr("goals.header_dependencies", "Dependencies"),
            _tr("goals.header_blocked", "Blocked")])
        self._goals_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._goals_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._goals_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self._goals_table.setAccessibleName("Project goals")
        self._goals_table.itemSelectionChanged.connect(self._on_goal_selected)
        layout.addWidget(self._goals_table, 1)
        self._empty_label = QLabel(_tr(
            "goals.no_goals", "No goals in this project."))
        self._empty_label.setStyleSheet("color: #AB83C6;")
        self._empty_label.setAccessibleName("Goals empty state")
        layout.addWidget(self._empty_label)
        return box

    def _build_detail_area(self) -> QWidget:
        box = QWidget()
        box.setAccessibleName("Goal detail")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        self._detail_title = QLabel(_tr(
            "goals.no_goal_selected", "No goal selected"))
        self._detail_title.setStyleSheet("font-weight: 700; color: #46A3C0;")
        self._detail_title.setAccessibleName("Selected goal")
        layout.addWidget(self._detail_title)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("goalDetailTabs")
        self._tabs.setAccessibleName("Goal detail tabs")
        self._tabs.addTab(self._build_goal_tab(), _tr("goals.tab_overview", "Overview"))
        self._tabs.addTab(self._build_milestones_tab(), _tr("goals.tab_milestones", "Milestones"))
        self._tabs.addTab(self._build_missions_tab(), _tr("goals.tab_missions", "Missions & Queue"))
        self._tabs.addTab(self._build_activity_tab(), _tr("goals.tab_activity", "Activity & Decisions"))
        self._tabs.addTab(self._build_tasks_tab(), _tr("goals.tab_tasks", "Tasks & Active Workers"))
        self._tabs.addTab(self._build_versions_tab(), _tr("goals.tab_versions", "Plan Versions"))
        self._tabs.addTab(self._build_evidence_tab(), _tr("goals.tab_evidence", "Evidence & Verification"))
        self._tabs.addTab(self._build_next_work_tab(), _tr("goals.tab_next_work", "Next Work"))
        layout.addWidget(self._tabs, 1)
        return box

    def _build_goal_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._meta_label = QLabel("")
        self._meta_label.setWordWrap(True)
        self._meta_label.setAccessibleName("Goal status, priority and dependencies")
        layout.addWidget(self._meta_label)
        self._objective_view = QPlainTextEdit()
        self._objective_view.setReadOnly(True)
        self._objective_view.setAccessibleName("Goal objective (read-only)")
        layout.addWidget(self._objective_view, 1)
        actions = QHBoxLayout()
        self._action_buttons = {}
        for action, label in (("activate", "Activate"), ("pause", "Pause"),
                              ("resume", "Resume"), ("block", "Block"),
                              ("unblock", "Unblock"), ("cancel", "Cancel")):
            button = QPushButton(_tr("goals.action_" + action, label))
            button.setAccessibleName(label + " goal")
            button.clicked.connect(lambda checked=False, a=action: self._lifecycle(a))
            actions.addWidget(button)
            self._action_buttons[action] = button
        self._verify_btn = QPushButton(_tr(
            "goals.verify", "Verify (read-only)"))
        self._verify_btn.setAccessibleName("Verify goal evidence (read-only)")
        self._verify_btn.clicked.connect(self._verify_goal)
        actions.addWidget(self._verify_btn)
        self._replan_btn = QPushButton(_tr("goals.replan", "Replan…"))
        self._replan_btn.setAccessibleName("Replan goal with rationale")
        self._replan_btn.clicked.connect(self._open_replan)
        actions.addWidget(self._replan_btn)
        self._complete_btn = QPushButton(_tr(
            "goals.complete", "Complete with evidence…"))
        self._complete_btn.setAccessibleName("Complete goal with verification evidence")
        self._complete_btn.clicked.connect(self._open_evidence_dialog)
        actions.addWidget(self._complete_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self._blockers_view = QPlainTextEdit()
        self._blockers_view.setReadOnly(True)
        self._blockers_view.setAccessibleName("Goal blockers and completion gate")
        layout.addWidget(self._blockers_view, 1)
        return box



    def _build_missions_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._missions_label = QLabel(_tr(
            "goals.linked_missions",
            "Linked missions (read-only; no mission is created here)"))
        layout.addWidget(self._missions_label)
        self._missions_list = QListWidget()
        self._missions_list.setAccessibleName("Linked goal missions")
        layout.addWidget(self._missions_list, 1)
        self._queue_label = QLabel(_tr(
            "goals.queue_label",
            "Queue (read-only; explicit not-connected/empty state)"))
        layout.addWidget(self._queue_label)
        self._queue_list = QListWidget()
        self._queue_list.setAccessibleName("Goal mission queue")
        layout.addWidget(self._queue_list, 1)
        return box

    def _build_activity_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._activity_list = QListWidget()
        self._activity_list.setAccessibleName("Goal activity audit entries")
        layout.addWidget(self._activity_list, 1)
        self._progress_label = QLabel("")
        self._progress_label.setWordWrap(True)
        self._progress_label.setAccessibleName("Project goal progress summary")
        layout.addWidget(self._progress_label)
        self._decisions_view = QPlainTextEdit()
        self._decisions_view.setReadOnly(True)
        self._decisions_view.setAccessibleName("Read-only decisions, status and blockers")
        layout.addWidget(self._decisions_view, 1)
        return box



    def _build_tasks_tab(self) -> QWidget:
        box = QWidget()
        box.setAccessibleName("Goal tasks, queue and active workers")
        layout = QVBoxLayout(box)
        self._tasks_label = QLabel(_tr(
            "goals.tasks_label",
            "Linked mission tasks (read-only; no task is created/started here)"))
        layout.addWidget(self._tasks_label)
        self._task_table = QTableWidget(0, 5)
        self._task_table.setHorizontalHeaderLabels(
            [_tr("goals.h_task_id", "ID"), _tr("goals.h_task_title", "Title"),
             _tr("goals.h_task_status", "Status"), _tr("goals.h_task_role", "Agent role"),
             _tr("goals.h_task_depends", "Depends on")])
        self._task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._task_table.setAccessibleName("Linked mission tasks")
        layout.addWidget(self._task_table, 1)
        self._queue_entries_label = QLabel(_tr(
            "goals.queue_entries_label",
            "Mission queue (read-only state/priority/attempts/lease)"))
        layout.addWidget(self._queue_entries_label)
        self._queue_table = QTableWidget(0, 8)
        self._queue_table.setHorizontalHeaderLabels(
            [_tr("goals.h_queue_mission", "Mission"), _tr("goals.h_queue_id", "Queue ID"),
             _tr("goals.h_queue_state", "State"), _tr("goals.h_queue_priority", "Priority"),
             _tr("goals.h_queue_attempts", "Attempts"), _tr("goals.h_queue_lease", "Lease owner"),
             _tr("goals.h_queue_created", "Created"), _tr("goals.h_queue_updated", "Updated")])
        self._queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._queue_table.setAccessibleName("Mission queue entries")
        layout.addWidget(self._queue_table, 1)
        self._workers_label = QLabel(_tr(
            "goals.workers_label", "Active supervisor runs/work (read-only)"))
        layout.addWidget(self._workers_label)
        self._workers_table = QTableWidget(0, 5)
        self._workers_table.setHorizontalHeaderLabels(
            [_tr("goals.h_worker_id", "ID"), _tr("goals.h_worker_mode", "Mode"),
             _tr("goals.h_worker_status", "Status"), _tr("goals.h_worker_owner", "Owner"),
             _tr("goals.h_worker_heartbeat", "Heartbeat")])
        self._workers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._workers_table.setAccessibleName("Active supervisor runs and work")
        layout.addWidget(self._workers_table, 1)
        self._refresh_tasks_btn = QPushButton(_tr(
            "goals.refresh_tasks", "Refresh tasks/queue/workers"))
        refresh = self._refresh_tasks_btn
        refresh.setAccessibleName("Refresh tasks, queue and active workers (read-only)")
        refresh.setToolTip("Read-only facade refresh; never starts a mission or worker.")
        refresh.clicked.connect(self._refresh_tasks_workers)
        layout.addWidget(refresh)
        return box

    def _build_versions_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._versions_table = QTableWidget(0, 5)
        self._versions_table.setHorizontalHeaderLabels(
            [_tr("goals.h_version", "Version"), _tr("goals.h_current", "Current"),
             _tr("goals.h_trigger", "Trigger"), _tr("goals.h_rationale", "Rationale"),
             _tr("goals.h_diff", "Milestone diff")])
        self._versions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._versions_table.setAccessibleName("Goal plan versions")
        self._versions_table.itemSelectionChanged.connect(self._on_version_selected)
        layout.addWidget(self._versions_table, 1)
        approval = QHBoxLayout()
        self._approval_label = QLabel(_tr(
            "goals.approval_none", "Plan approval: no version selected"))
        self._approval_label.setWordWrap(True)
        self._approval_label.setAccessibleName("Current plan approval state")
        approval.addWidget(self._approval_label, 1)
        self._approve_plan_btn = QPushButton(_tr(
            "goals.approve_plan", "Approve plan…"))
        self._approve_plan_btn.setEnabled(False)
        self._approve_plan_btn.setAccessibleName("Approve selected goal plan version")
        self._approve_plan_btn.setToolTip(
            "Approves the selected/current plan version through the goal facade; "
            "never executes or creates a mission.")
        self._approve_plan_btn.clicked.connect(self._confirm_approve_plan)
        approval.addWidget(self._approve_plan_btn)
        layout.addLayout(approval)
        self._version_detail = QPlainTextEdit()
        self._version_detail.setReadOnly(True)
        self._version_detail.setAccessibleName("Selected plan version rationale and diff")
        layout.addWidget(self._version_detail, 1)
        return box

    def _build_evidence_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._verification_status = QLabel(_tr(
            "goals.no_verification", "No verification report loaded."))
        self._verification_status.setWordWrap(True)
        self._verification_status.setAccessibleName("Verification verdict and outstanding status")
        layout.addWidget(self._verification_status)
        self._criteria_table = QTableWidget(0, 3)
        self._criteria_table.setHorizontalHeaderLabels(
            [_tr("goals.h_criterion", "Criterion"), _tr("goals.h_criterion_status", "Status"),
             _tr("goals.h_blockers", "Blockers")])
        self._criteria_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._criteria_table.setAccessibleName("Acceptance criteria verification status")
        layout.addWidget(self._criteria_table, 1)
        self._verification_blockers = QPlainTextEdit()
        self._verification_blockers.setReadOnly(True)
        self._verification_blockers.setAccessibleName(
            "Verification records and outstanding blockers (read-only)")
        layout.addWidget(self._verification_blockers, 1)
        refresh = QPushButton("Refresh verification evidence")
        refresh.setAccessibleName("Refresh verification evidence (read-only)")
        refresh.clicked.connect(self._refresh_evidence)
        layout.addWidget(refresh)
        return box
    def _build_milestones_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._milestones_table = QTableWidget(0, 6)
        self._milestones_table.setHorizontalHeaderLabels(
            [_tr("goals.h_ms_title", "Title"), _tr("goals.h_ms_status", "Status"),
             _tr("goals.h_ms_priority", "Priority"), _tr("goals.h_ms_depends", "Depends"),
             _tr("goals.h_ms_order", "Order"), _tr("goals.h_ms_acceptance", "Acceptance")])
        self._milestones_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._milestones_table.setAccessibleName("Goal milestones")
        layout.addWidget(self._milestones_table, 1)
        return box

    def _build_next_work_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._next_work = QListWidget()
        self._next_work.setAccessibleName("Eligible next work; read-only")
        layout.addWidget(self._next_work, 1)
        return box

    def _build_progress_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._progress_label = QLabel("")
        self._progress_label.setWordWrap(True)
        self._progress_label.setAccessibleName("Project goal progress summary")
        layout.addWidget(self._progress_label)
        self._decisions_view = QPlainTextEdit()
        self._decisions_view.setReadOnly(True)
        self._decisions_view.setAccessibleName("Read-only decisions, status and blockers")
        layout.addWidget(self._decisions_view, 1)
        return box

    # ---------------------------------------------------- facade adapter/extras
    def _adapter_call(self, names, *args, **kwargs):
        for name in names:
            fn = getattr(self._services, name, None)
            if callable(fn):
                try:
                    return _as_dict(fn(*args, **kwargs))
                except Exception as exc:  # noqa: BLE001 - read-only display state
                    return {"ok": False, "error": str(exc)}
        return None

    def _verification_ready(self):
        return (callable(getattr(self._services, "goal_verify", None))
                and callable(getattr(self._services, "goal_complete", None)))

    def _load_extras(self, goal_id):
        project_id = self._project.get("id") if self._project else None
        missions = self._adapter_call(("goal_missions", "goal_links"), goal_id=goal_id)
        self._missions = []
        self._missions_state = "not-connected"
        if missions is not None and missions.get("ok"):
            values = missions.get("missions") or missions.get("links") or []
            self._missions = [dict(item) for item in values if isinstance(item, Mapping)]
            self._missions_state = "loaded"
        queue = self._adapter_call(("goal_queue", "goal_queue_entries",
                                   "goal_mission_queue"), goal_id=goal_id)
        if queue is not None and not queue.get("ok"):
            queue = None
        self._queue = []
        self._queue_state = "not-connected"
        if queue is not None and queue.get("ok"):
            values = queue.get("queue") or queue.get("items") or []
            self._queue = [dict(item) for item in values if isinstance(item, Mapping)]
            self._queue_state = "loaded"
        tasks = self._adapter_call(("goal_tasks", "goal_mission_tasks"),
                                   goal_id=goal_id)
        self._tasks = []
        self._tasks_state = "not-connected"
        if tasks is not None and tasks.get("ok"):
            values = tasks.get("tasks") or tasks.get("items") or []
            self._tasks = [dict(item) for item in values if isinstance(item, Mapping)]
            self._tasks_state = "loaded"
        workers = self._adapter_call(("goal_active_work", "goal_active_workers",
                                      "goal_workers", "goal_work"), goal_id=goal_id)
        self._workers = []
        self._workers_state = "not-connected"
        if workers is not None and workers.get("ok"):
            if workers.get("assigned_tasks") or workers.get("supervisor_runs"):
                merged = []
                for task in workers.get("assigned_tasks") or []:
                    if isinstance(task, Mapping):
                        item = dict(task)
                        item.setdefault("kind", "task")
                        item.setdefault("owner", task.get("agent_role"))
                        merged.append(item)
                for run in workers.get("supervisor_runs") or []:
                    if isinstance(run, Mapping):
                        item = dict(run)
                        item.setdefault("kind", run.get("mode") or "supervisor")
                        merged.append(item)
                self._workers = merged
            else:
                values = (workers.get("workers") or workers.get("work")
                          or workers.get("runs") or workers.get("items") or [])
                self._workers = [dict(item) for item in values
                                 if isinstance(item, Mapping)]
            self._workers_state = "loaded"
        activity = self._adapter_call(("goal_activity",), goal_id=goal_id, limit=50)
        self._activity = []
        self._activity_state = "not-connected"
        if activity is not None and activity.get("ok"):
            values = activity.get("activity") or activity.get("entries") or []
            self._activity = [dict(item) for item in values if isinstance(item, Mapping)]
            self._activity_state = "loaded"
        versions = self._adapter_call(("goal_plan_versions", "goal_versions"),
                                      goal_id=goal_id)
        self._versions = []
        self._versions_current = None
        self._versions_state = "not-connected"
        if versions is not None and versions.get("ok"):
            values = versions.get("versions") or versions.get("items") or []
            self._versions = [dict(item) for item in values if isinstance(item, Mapping)]
            self._versions_current = versions.get("current") or versions.get("current_version")
            self._versions_state = "loaded"
        verifications = self._adapter_call(("goal_verifications",), goal_id=goal_id,
                                           limit=20)
        self._verifications = []
        self._verifications_state = "not-connected"
        if verifications is not None and verifications.get("ok"):
            values = verifications.get("verifications") or verifications.get("records") or []
            self._verifications = [dict(item) for item in values if isinstance(item, Mapping)]
            self._verifications_state = "loaded"
        outstanding = self._adapter_call(("goal_verification_outstanding",),
                                         goal_id=goal_id)
        self._outstanding = _as_dict((outstanding or {}).get("outstanding"))
        self._render_missions()
        self._render_activity()
        self._render_tasks_workers()
        self._render_versions()
        self._render_verifications()

    def _render_missions(self):
        self._missions_list.clear()
        if self._missions_state == "not-connected":
            self._missions_list.addItem("Linked missions are not connected by the goal service.")
        elif not self._missions:
            self._missions_list.addItem("No linked missions for this goal.")
        for item in self._missions:
            self._missions_list.addItem(
                "Mission " + _text(item.get("mission_id") or item.get("id"))
                + " — " + _text(item.get("title") or item.get("status") or "linked")
                + " [" + _text(item.get("status") or "unknown") + "]"
                + "  role: " + _text(item.get("role") or "—"))
        self._queue_list.clear()
        if self._queue_state == "not-connected":
            self._queue_list.addItem("Mission queue is not connected (read-only).")
        elif not self._queue:
            self._queue_list.addItem("Queue is empty (no missions are queued/created by this page).")
        for item in self._queue:
            self._queue_list.addItem(
                "Mission " + _text(item.get("mission_id") or item.get("id"))
                + " — " + _text(item.get("title") or item.get("status") or "queued")
                + " [" + _text(item.get("status") or "unknown") + "]")

    def _render_activity(self):
        self._activity_list.clear()
        if self._activity_state == "not-connected":
            self._activity_list.addItem("Goal activity is not connected by the goal service.")
        elif not self._activity:
            self._activity_list.addItem("No activity entries recorded for this goal.")
        for item in self._activity:
            self._activity_list.addItem(
                _text(item.get("created_at") or item.get("timestamp") or "")
                + "  " + _text(item.get("event_kind") or item.get("kind") or "activity")
                + " — " + _text(item.get("message") or item.get("summary") or ""))

    def _render_tasks_workers(self):
        self._task_table.setRowCount(len(self._tasks))
        for row, item in enumerate(self._tasks):
            dependencies = item.get("depends_on") or item.get("dependencies") or []
            values = [_text(item.get("id") or item.get("task_id")),
                      _text(item.get("title")), _text(item.get("status")),
                      _text(item.get("agent_role") or item.get("role")),
                      ", ".join(str(dep) for dep in dependencies) or "—"]
            for column, value in enumerate(values):
                self._task_table.setItem(row, column, QTableWidgetItem(str(value)))
        if self._tasks_state == "not-connected":
            self._task_table.setRowCount(1)
            self._task_table.setSpan(0, 0, 1, 5)
            self._task_table.setItem(0, 0, QTableWidgetItem(
                "Tasks are not connected by the goal service."))
        elif not self._tasks:
            self._task_table.setRowCount(1)
            self._task_table.setSpan(0, 0, 1, 5)
            self._task_table.setItem(0, 0, QTableWidgetItem(
                "No linked mission tasks in this goal scope."))

        queue = self._queue
        self._queue_table.setRowCount(len(queue))
        for row, item in enumerate(queue):
            mission_id = item.get("mission_id") or item.get("id")
            values = [_text(mission_id), _text(item.get("queue_id") or "—"),
                      _text(item.get("queue_state") or item.get("state") or "not_queued"),
                      _text(item.get("priority") or "—"),
                      _text(item.get("attempts") or 0)
                      + ("/" + _text(item.get("max_attempts"))
                         if item.get("max_attempts") is not None else ""),
                      _text(item.get("lease_owner") or item.get("owner") or "—"),
                      _text(item.get("created_at") or "—"),
                      _text(item.get("updated_at") or "—")]
            for column, value in enumerate(values):
                self._queue_table.setItem(row, column, QTableWidgetItem(str(value)))
        if self._queue_state == "not-connected":
            self._queue_table.setRowCount(1)
            self._queue_table.setSpan(0, 0, 1, 8)
            self._queue_table.setItem(0, 0, QTableWidgetItem(
                "Mission queue is not connected (read-only)."))
        elif not queue:
            self._queue_table.setRowCount(1)
            self._queue_table.setSpan(0, 0, 1, 8)
            self._queue_table.setItem(0, 0, QTableWidgetItem(
                "Queue is empty (nothing is queued/created by this page)."))

        self._workers_table.setRowCount(len(self._workers))
        for row, item in enumerate(self._workers):
            values = [_text(item.get("id") or item.get("run_id")
                            or item.get("worker_id")),
                      _text(item.get("mode") or item.get("kind") or "—"),
                      _text(item.get("status") or "unknown"),
                      _text(item.get("owner") or item.get("owner_id") or "—"),
                      _text(item.get("heartbeat") or item.get("heartbeat_at")
                            or item.get("updated_at") or "—")]
            for column, value in enumerate(values):
                self._workers_table.setItem(row, column, QTableWidgetItem(str(value)))
        if self._workers_state == "not-connected":
            self._workers_table.setRowCount(1)
            self._workers_table.setSpan(0, 0, 1, 5)
            self._workers_table.setItem(0, 0, QTableWidgetItem(
                "Active workers are not connected by the goal service."))
        elif not self._workers:
            self._workers_table.setRowCount(1)
            self._workers_table.setSpan(0, 0, 1, 5)
            self._workers_table.setItem(0, 0, QTableWidgetItem(
                "No active supervisor runs/work for this goal."))
        self._refresh_tasks_workers_controls()

    def _refresh_tasks_workers_controls(self):
        if not hasattr(self, "_approve_plan_btn"):
            return
        has_goal = bool((self._current or {}).get("id"))
        approve = callable(getattr(self._services, "goal_approve_plan", None))
        reason = ""
        if not has_goal:
            reason = "Select a goal first."
        elif not approve:
            reason = "Plan approval is not connected by the goal service."
        self._approve_plan_btn.setEnabled(
            not reason or (has_goal and approve))
        if has_goal and approve and not self._selected_version:
            self._selected_version = self._versions_current
        self._approve_plan_btn.setToolTip(
            "No version selected." if not self._selected_version and not reason
            else (reason or "Approve the selected/current plan version (confirmation + "
                            "optional rationale); never executes a mission."))

    def _on_version_selected(self):
        rows = self._versions_table.selectionModel().selectedRows()
        if not rows or not (0 <= rows[0].row() < len(self._versions)):
            self._selected_version = None
            return
        item = self._versions[rows[0].row()]
        self._selected_version = (item.get("version") or item.get("version_id")
                                  or item.get("id"))
        self._refresh_tasks_workers_controls()

    def _confirm_approve_plan(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        version = self._selected_version or self._versions_current
        answer = QMessageBox.question(
            self, "Approve goal plan",
            "Approve plan version " + _text(version) + "?\n\n"
            "This records approval only; it never executes work or creates a mission.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        rationale, ok = QInputDialog.getText(
            self, "Plan approval rationale", "Optional rationale:")
        self._approve_plan(version, rationale if ok else "")

    def _approve_plan(self, version=None, rationale: str = "") -> bool:
        goal = self._current or {}
        goal_id = goal.get("id")
        method = None
        for name in ("goal_approve_plan", "approve_plan"):
            fn = getattr(self._services, name, None)
            if callable(fn):
                method = fn
                break
        if goal_id is None:
            self._status_label.setText("Approve unavailable: select a goal first.")
            return False
        if method is None:
            self._status_label.setText(
                "Approve unavailable: plan approval is not connected.")
            return False
        version = version if version is not None else self._selected_version
        try:
            result = _as_dict(method(int(goal_id), version=version,
                                     rationale=str(rationale or "").strip()))
        except TypeError:
            try:
                result = _as_dict(method(int(goal_id), version=version))
            except Exception as exc:  # noqa: BLE001
                self._status_label.setText("Approve failed: " + _text(exc))
                return False
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText("Approve failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._approval_label.setText(
                "Plan approval refused: " + _text(result.get("error") or "unknown error"))
            return False
        approved = result.get("approved_version") or result.get("version") or version
        idempotent = bool(result.get("idempotent"))
        self._load_goal(goal)
        self._approval_label.setText(
            "Plan approval: version " + _text(approved) + " approved"
            + (" (already approved)" if idempotent else "")
            + ((" — " + _text(rationale).strip()) if str(rationale or "").strip() else ""))
        self._status_label.setText(
            "Plan approved through the goal facade; no mission was created or executed.")
        return True

    def _render_versions(self):
        versions = self._versions
        self._versions_table.setRowCount(len(versions))
        for row, item in enumerate(versions):
            number = item.get("version") or item.get("version_id") or item.get("id")
            is_current = (str(number) == str(self._versions_current)
                          or bool(item.get("current")))
            diff = item.get("diff") or item.get("milestone_diff") or {}
            if isinstance(diff, Mapping):
                diff_text = ", ".join(str(key) + "=" + str(value)
                                      for key, value in sorted(diff.items()))
            else:
                diff_text = _text(diff)
            values = [str(number), "yes" if is_current else "no",
                      _text(item.get("trigger") or "—"),
                      _text(item.get("rationale") or "—"), diff_text or "—"]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, number)
                self._versions_table.setItem(row, column, cell)
        approved_version = None
        for item in versions:
            if item.get("approved") or item.get("is_approved"):
                approved_version = (item.get("version") or item.get("version_id")
                                    or item.get("id"))
                break
        if approved_version is not None:
            self._approval_label.setText(
                "Plan approval: version " + _text(approved_version) + " approved.")
        elif versions:
            self._approval_label.setText("Plan approval: no approved version yet.")
        else:
            self._approval_label.setText("Plan approval: no plan version available.")
        if not self._selected_version:
            self._selected_version = self._versions_current
        self._refresh_tasks_workers_controls()
        if self._versions_state == "not-connected":
            self._version_detail.setPlainText(
                "Plan versions are not connected by the goal service.")
        elif not versions:
            self._version_detail.setPlainText("No plan versions recorded for this goal.")
        else:
            self._version_detail.setPlainText(
                "Current version: " + _text(self._versions_current)
                + "\nSelect/replan to review rationale, trigger and milestone diffs. "
                  "This view is read-only; replanning is explicit.")

    def _refresh_tasks_workers(self):
        """Read-only facade refresh for tasks/queue/workers; never starts work."""
        if self._current and self._project:
            self._load_goal(self._current)
        else:
            self._status_label.setText("Select a goal to refresh tasks and workers.")

    def _render_verifications(self):
        self._criteria_table.setRowCount(0)
        if self._verifications_state == "not-connected":
            self._verification_status.setText(
                "Verification records are not connected by the goal service.")
            self._verification_blockers.setPlainText(
                "Verification is not connected; completion cannot be attempted here.")
            return
        self._criteria_table.setRowCount(0)
        latest = self._verifications[0] if self._verifications else {}
        verdict = latest.get("verdict") or latest.get("status") or "no records"
        self._verification_status.setText(
            "Latest verification: " + _text(verdict)
            + "  |  records: " + str(len(self._verifications))
            + "  |  outstanding: " + _text(self._outstanding.get("outstanding")
                                           if isinstance(self._outstanding, Mapping)
                                           else self._outstanding))
        criteria = latest.get("criteria") or latest.get("criteria_results") or []
        self._criteria_table.setRowCount(len(criteria))
        for row, criterion in enumerate(criteria):
            item = _as_dict(criterion)
            blockers = item.get("blockers") or []
            blocker_text = "; ".join(_text(b.get("detail") if isinstance(b, Mapping) else b)
                                     for b in blockers) or "—"
            values = [_text(item.get("criterion_id") or item.get("id")),
                      _text(item.get("status") or "unknown"), blocker_text]
            for column, value in enumerate(values):
                self._criteria_table.setItem(row, column, QTableWidgetItem(str(value)))
        lines = []
        for record in self._verifications:
            lines.append("Verification " + _text(record.get("id") or record.get("record_id"))
                         + " — " + _text(record.get("verdict") or "unknown")
                         + " at " + _text(record.get("created_at") or ""))
        if self._outstanding:
            lines.append("Outstanding: " + json.dumps(self._outstanding, ensure_ascii=False,
                                                      sort_keys=True))
        self._verification_blockers.setPlainText(
            "\n".join(lines) if lines else "No verification records yet.")

    # ------------------------------------------------------------- lifecycle
    def _set_no_project_state(self) -> None:
        self._project = None
        self._current = None
        self._goals = []
        self._sorted_goals = []
        self._milestones = []
        self._progress = {}
        self._missions = []
        self._queue = []
        self._activity = []
        self._versions = []
        self._versions_current = None
        self._selected_version = None
        self._tasks: list[dict] = []
        self._workers: list[dict] = []
        self._tasks_state = "not-connected"
        self._workers_state = "not-connected"
        self._verifications = []
        self._outstanding = {}
        self._missions_state = "not-connected"
        self._queue_state = "not-connected"
        self._activity_state = "not-connected"
        self._versions_state = "not-connected"
        self._verifications_state = "not-connected"
        self._last_verification = {}
        self._scope_label.setText(_tr(
            "goals.no_project", "No project open"))
        self._goals_table.setRowCount(0)
        self._empty_label.setText(_tr(
            "goals.open_project", "Open a project to load goals."))
        self._empty_label.show()
        self._facade_label.setText(
            "Goal service: available" if self._facade_ready else "Goal service: unavailable")
        for button in [self._create_btn, self._refresh_btn, *self._action_buttons.values(),
                       self._complete_btn]:
            button.setEnabled(False)
        self._create_btn.setToolTip("Open a project first.")
        self._refresh_btn.setToolTip("Open a project first.")
        self._status_label.setText(_tr(
            "goals.open_project", "Open a project to load goals."))
        self._detail_title.setText(_tr(
            "goals.no_goal_selected", "No goal selected"))
        self._meta_label.setText("")
        self._objective_view.setPlainText("")
        self._blockers_view.setPlainText("")
        self._milestones_table.setRowCount(0)
        self._next_work.clear()
        self._progress_label.setText("No project progress.")
        self._decisions_view.setPlainText("")
        self._missions_list.clear()
        self._queue_list.clear()
        self._activity_list.clear()
        self._versions_table.setRowCount(0)
        self._version_detail.setPlainText("No plan versions.")
        self._task_table.setRowCount(0)
        self._queue_table.setRowCount(0)
        self._workers_table.setRowCount(0)
        self._approval_label.setText("Plan approval: no version selected")
        self._approve_plan_btn.setEnabled(False)
        self._criteria_table.setRowCount(0)
        self._verification_status.setText("No verification report loaded.")
        self._verification_blockers.setPlainText("")
        self._verify_btn.setEnabled(False)
        self._replan_btn.setEnabled(False)
        self._complete_btn.setEnabled(False)

    def set_project(self, project) -> None:
        if not project:
            self._set_no_project_state()
            return
        self._project = dict(project)
        self._scope_label.setText("Project: " + _text(
            self._project.get("name") or self._project.get("id")))
        self._facade_label.setText(
            "Goal service: available" if self._facade_ready else "Goal service: unavailable")
        self._create_btn.setEnabled(self._facade_ready)
        self._refresh_btn.setEnabled(self._facade_ready)
        self.refresh()

    def refresh(self) -> None:
        if not self._project:
            self._set_no_project_state()
            return
        if not self._facade_ready:
            self._status_label.setText(
                "Goals unavailable: the goal service facade is not configured.")
            self._create_btn.setEnabled(False)
            self._refresh_btn.setEnabled(False)
            return
        project_id = self._project.get("id")
        try:
            result = _as_dict(self._services.goal_list(project_id=project_id,
                                                       limit=500, offset=0))
        except Exception as exc:  # noqa: BLE001 - displayed as deterministic state
            self._status_label.setText("Goals error: " + _text(exc))
            return
        if not result.get("ok", False):
            self._status_label.setText(
                "Goals error: " + _text(result.get("error") or "unknown error"))
            self._goals = []
            self._render_goals()
            return
        self._goals = [dict(item) for item in result.get("goals") or []
                       if isinstance(item, Mapping)]
        self._status_label.setText(
            str(len(self._goals)) + " goal(s) in this project (read-only list).")
        self._refresh_progress_summary(project_id)
        self._refresh_next_work(project_id)
        self._apply_filters()
        if self._goals:
            self._goals_table.selectRow(0)

    def _goal_progress(self, goal_id) -> dict:
        try:
            result = _as_dict(self._services.goal_progress(int(goal_id)))
        except Exception:  # noqa: BLE001
            return {}
        return _as_dict(result.get("progress")) if result.get("ok") else {}

    def _apply_filters(self) -> None:
        status = self._status_filter.currentData()
        priority = self._priority_filter.currentData()
        goals = [goal for goal in self._goals
                 if (not status or goal.get("status") == status)
                 and (not priority or goal.get("priority") == priority)]
        self._goals.sort(key=lambda item: (
            {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(item.get("priority"), 9),
            int(item.get("id") or 0)))
        self._sorted_goals = goals
        self._render_goals()

    def _render_goals(self) -> None:
        all_goals = {int(goal.get("id")): goal for goal in self._goals
                     if goal.get("id") is not None}
        goals = self._sorted_goals
        self._goals_table.setRowCount(len(goals))
        for row, goal in enumerate(goals):
            dependencies = [int(item) for item in goal.get("dependencies") or []]
            blocked = (goal.get("status") == "blocked"
                       or any(all_goals.get(dep, {}).get("status") != "completed"
                              for dep in dependencies))
            progress = goal.get("progress") or self._goal_progress(goal.get("id"))
            if not isinstance(progress, dict):
                progress = {}
            percent = progress.get("progress_percent")
            values = [_text(goal.get("title")), _text(goal.get("status")),
                      _text(goal.get("priority")),
                      (str(percent) + "%" if percent is not None else "—"),
                      ", ".join(str(item) for item in dependencies) or "—",
                      "yes" if blocked else "no"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, goal.get("id"))
                self._goals_table.setItem(row, column, item)
        self._empty_label.setVisible(not goals)
        if not goals:
            self._empty_label.setText(
                "No goals match the current filters." if self._goals
                else "No goals in this project. Create one explicitly.")
        if self._current:
            for row, goal in enumerate(goals):
                if goal.get("id") == self._current.get("id"):
                    self._goals_table.blockSignals(True)
                    self._goals_table.selectRow(row)
                    self._goals_table.blockSignals(False)
                    break

    def _on_goal_selected(self) -> None:
        rows = self._goals_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if not (0 <= row < len(self._sorted_goals)):
            return
        goal = self._sorted_goals[row]
        self._load_goal(goal)

    def _load_goal(self, goal: dict) -> None:
        goal_id = goal.get("id")
        if goal_id is None:
            return
        try:
            result = _as_dict(self._services.goal_get(int(goal_id)))
            if result.get("ok") and isinstance(result.get("goal"), Mapping):
                goal = dict(result["goal"])
        except Exception:  # noqa: BLE001
            pass
        self._current = goal
        self._progress = self._goal_progress(goal_id)
        try:
            milestones_result = _as_dict(self._services.goal_milestones(int(goal_id)))
        except Exception as exc:  # noqa: BLE001
            milestones_result = {"ok": False, "error": str(exc)}
        if milestones_result.get("ok"):
            self._milestones = [dict(item) for item in
                                milestones_result.get("milestones") or []
                                if isinstance(item, Mapping)]
        else:
            self._milestones = []
            self._status_label.setText("Milestones error: " + _text(
                milestones_result.get("error") or "unknown error"))
        self._load_extras(goal_id)
        self._render_detail()

    def _render_detail(self) -> None:
        goal = self._current or {}
        self._detail_title.setText(_text(goal.get("title") or "Goal"))
        dependencies = [int(item) for item in goal.get("dependencies") or []]
        self._meta_label.setText(
            "Status: " + _text(goal.get("status")) + "  |  Priority: "
            + _text(goal.get("priority")) + "  |  Dependencies: "
            + (", ".join(str(item) for item in dependencies) or "none"))
        objective = _text(goal.get("objective"))
        acceptance = goal.get("acceptance_criteria") or []
        if acceptance:
            objective += "\n\nAcceptance criteria:\n" + "\n".join(
                "- " + _text(item) for item in acceptance)
        self._objective_view.setPlainText(objective)
        status = _text(goal.get("status"))
        allowed = TRANSITIONS.get(status, ())
        for action, button in self._action_buttons.items():
            if action == "activate":
                enabled = "active" in allowed
            elif action == "pause":
                enabled = "paused" in allowed
            elif action == "resume":
                enabled = status == "paused"
            elif action == "block":
                enabled = "blocked" in allowed and status in ("planned", "active", "paused")
            elif action == "unblock":
                enabled = status == "blocked"
            elif action == "cancel":
                enabled = "cancelled" in allowed
            else:
                enabled = False
            button.setEnabled(enabled and bool(goal.get("id")))
            button.setToolTip(
                "" if button.isEnabled()
                else "Not available while goal status is " + (status or "unknown"))
        self._render_milestones()
        goal_id = goal.get("id")
        verification_available = self._verification_ready()
        if not verification_available:
            complete_error = "verification API is not available"
        elif status != "active":
            complete_error = "goal must be active (current: " + (status or "unknown") + ")"
        else:
            complete_error = ""
        self._complete_btn.setEnabled(not bool(complete_error) and bool(goal_id))
        self._complete_btn.setToolTip(
            complete_error or "Requires active status; verification (goal_verify) runs first "
            "and completion is allowed only when verdict is verified.")
        self._verify_btn.setEnabled(bool(goal_id)
                                    and callable(getattr(self._services, "goal_verify", None)))
        self._replan_btn.setEnabled(bool(goal_id)
                                    and callable(getattr(self._services, "goal_replan", None)))
        self._verify_btn.setToolTip(
            "" if self._verify_btn.isEnabled() else "Verification is not connected.")
        self._replan_btn.setToolTip(
            "" if self._replan_btn.isEnabled() else "Replanning is not connected.")
        blockers = self._blockers(goal)
        if complete_error:
            blockers.append("Completion gate: " + complete_error)
        self._blockers_view.setPlainText(
            "\n".join(blockers) if blockers else "No blockers reported by the service.")
        decisions = goal.get("reference_metadata") or {}
        decision_text = json.dumps(decisions, ensure_ascii=False, sort_keys=True,
                                   indent=2) if decisions else "No decisions/reference notes."
        self._decisions_view.setPlainText(
            "Read-only decisions/status/blockers\nStatus: " + status
            + "\nPriority: " + _text(goal.get("priority"))
            + "\nCreated: " + _text(goal.get("created_at"))
            + "\nUpdated: " + _text(goal.get("updated_at"))
            + "\n\nReference metadata:\n" + decision_text
            + "\n\nBlockers:\n" + ("\n".join(blockers) if blockers else "none"))

    def _render_milestones(self) -> None:
        milestones = self._milestones
        self._milestones_table.setRowCount(len(milestones))
        for row, item in enumerate(milestones):
            values = [_text(item.get("title")), _text(item.get("status")),
                      _text(item.get("priority")),
                      ", ".join(str(dep) for dep in item.get("dependencies") or []) or "—",
                      _text(item.get("ordering")),
                      "; ".join(_text(c) for c in item.get("acceptance_criteria") or [])
                      or "—"]
            for column, value in enumerate(values):
                self._milestones_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _blockers(self, goal: dict) -> list[str]:
        blockers = []
        if goal.get("status") == "blocked":
            blockers.append("Goal is blocked.")
        dependencies = [int(item) for item in goal.get("dependencies") or []]
        by_id = {int(item.get("id")): item for item in self._goals
                 if item.get("id") is not None}
        for dep in dependencies:
            if by_id.get(dep, {}).get("status") != "completed":
                blockers.append("Dependency goal " + str(dep) + " is not completed.")
        incomplete = [item for item in self._milestones
                      if item.get("status") != "completed"]
        if incomplete:
            blockers.append("Incomplete milestones: " + ", ".join(
                _text(item.get("id")) for item in incomplete))
        return blockers

    def _complete_gate_error(self, goal: dict) -> str:
        if goal.get("status") != "active":
            return "goal must be active (current: " + _text(goal.get("status")) + ")"
        if not self._milestones:
            return "goal has no milestones"
        incomplete = [item for item in self._milestones
                      if item.get("status") != "completed"]
        if incomplete:
            return "incomplete milestones: " + ", ".join(
                _text(item.get("id")) for item in incomplete)
        return ""

    # ------------------------------------------------------------- actions
    def _create_goal_from_document_plan(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        project = getattr(self, "_project", None)
        project_id = project.get("id") if isinstance(project, dict) else None
        if project_id is None:
            self._scope_label.setText("Open a project before importing a plan.")
            return
        plan_id, ok = QInputDialog.getInt(
            self, "Import approved document plan",
            "Document plan ID:", 0, 0, 10**9, 1)
        if not ok:
            return
        result = self._services.goal_create_from_document_plan(
            int(plan_id), project_id=int(project_id))
        if not result.get("ok"):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Goal import failed",
                                str(result.get("error", {}).get("message", result)))
            return
        self._refresh_data(suppress_errors=True)
        self._detail_tabs.setCurrentIndex(0)

    def _create_goal_dialog(self, *, objective="", attachment_ids=()) -> bool:
        if not self._project or not self._facade_ready:
            return
        dialog = CreateGoalDialog(self)
        dialog._objective.setPlainText(objective)
        dialog._attachments.setText("; ".join("attachment:" + str(i) for i in attachment_ids))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return self._create_goal(dialog.values())
        return False

    def _create_goal(self, payload: dict) -> bool:
        if not self._project or not self._facade_ready:
            self._status_label.setText("Open a project and configure the goal service first.")
            return False
        objective = str(payload.get("objective") or "").strip()
        if not objective:
            self._status_label.setText("Goal objective is required.")
            return False
        kwargs = {key: value for key, value in payload.items()
                  if key in ("title", "priority", "acceptance_criteria", "dependencies",
                             "attachments", "reference_metadata")}
        try:
            result = _as_dict(self._services.goal_create(
                objective, project_id=self._project.get("id"), **kwargs))
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText("Create goal failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._status_label.setText(
                "Create goal failed: " + _text(result.get("error") or "unknown error"))
            return False
        self._status_label.setText("Goal created.")
        self.refresh()
        goal = result.get("goal") or {}
        if goal.get("id") is not None:
            self._select_goal_id(goal.get("id"))
        return True

    def _select_goal_id(self, goal_id) -> None:
        for row, goal in enumerate(self._sorted_goals):
            if goal.get("id") == goal_id:
                self._goals_table.selectRow(row)
                return

    def _lifecycle(self, action: str, reason: str = "") -> bool:
        goal = self._current or {}
        goal_id = goal.get("id")
        if goal_id is None:
            return False
        method = getattr(self._services, "goal_" + action, None)
        if not callable(method):
            self._status_label.setText("Lifecycle action unavailable: " + action)
            return False
        try:
            if action == "block":
                result = _as_dict(method(int(goal_id), reason=reason))
            else:
                result = _as_dict(method(int(goal_id)))
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText("Goal action failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._status_label.setText(
                "Goal action failed: " + _text(result.get("error") or "unknown error"))
            return False
        if isinstance(result.get("goal"), Mapping):
            self._current = dict(result["goal"])
        self.refresh()
        self._restore_selection(goal_id)
        self._status_label.setText("Goal " + action + " completed.")
        return True

    def _restore_selection(self, goal_id) -> None:
        self._select_goal_id(goal_id)
    def _open_evidence_dialog(self) -> None:
        if not self._current or not self._project:
            return
        dialog = EvidenceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self._complete_with_evidence(values["evidence"], values["criteria"])

    def _show_verification_payload(self, payload, prefix="Verification"):
        payload = _as_dict(payload)
        self._last_verification = payload
        verdict = _text(payload.get("verdict") or "unknown")
        verified = bool(payload.get("verified"))
        self._verification_status.setText(
            prefix + ": " + verdict
            + "  |  verified: " + ("yes" if verified else "no")
            + "  |  outcome: " + _text(payload.get("outcome") or "—"))
        criteria = payload.get("criteria") or payload.get("criteria_results") or []
        self._criteria_table.setRowCount(len(criteria))
        for row, criterion in enumerate(criteria):
            item = _as_dict(criterion)
            blockers = item.get("blockers") or []
            blocker_text = "; ".join(
                _text(blocker.get("detail") if isinstance(blocker, Mapping) else blocker)
                for blocker in blockers) or "—"
            values = [_text(item.get("criterion_id") or item.get("id")),
                      _text(item.get("status") or item.get("verdict") or "unknown"),
                      blocker_text]
            for column, value in enumerate(values):
                self._criteria_table.setItem(row, column, QTableWidgetItem(str(value)))
        lines = []
        for blocker in payload.get("blockers") or []:
            if isinstance(blocker, Mapping):
                lines.append(_text(blocker.get("detail") or blocker.get("message")
                                   or json.dumps(blocker, ensure_ascii=False, sort_keys=True)))
            else:
                lines.append(_text(blocker))
        outstanding = payload.get("outstanding")
        if outstanding:
            lines.append("Outstanding: " + json.dumps(outstanding, ensure_ascii=False,
                                                      sort_keys=True))
        text = "\n".join(lines) if lines else "No blockers in this verification report."
        self._verification_blockers.setPlainText(text)
        self._blockers_view.setPlainText(text)

    def _verify_goal(self, evidence=None, criteria=None) -> bool:
        goal = self._current or {}
        goal_id = goal.get("id")
        method = getattr(self._services, "goal_verify", None)
        if not callable(method):
            self._status_label.setText("Verify unavailable: goal_verify is not connected.")
            return False
        if goal_id is None:
            return False
        try:
            result = _as_dict(method(int(goal_id), evidence=evidence, criteria=criteria))
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText("Verify failed: " + _text(exc))
            return False
        self._show_verification_payload(result, "Verification")
        if not result.get("ok"):
            self._status_label.setText(
                "Verify error: " + _text(result.get("error") or "unknown error"))
            return False
        self._status_label.setText(
            "Verification " + _text(result.get("verdict") or "unknown")
            + " (read-only; status unchanged).")
        return True

    def _complete_with_evidence(self, evidence, criteria=None) -> bool:
        goal = self._current or {}
        goal_id = goal.get("id")
        if goal_id is None:
            return False
        if goal.get("status") != "active":
            self._status_label.setText(
                "Complete disabled: goal must be active (current: "
                + _text(goal.get("status")) + ").")
            return False
        verify = getattr(self._services, "goal_verify", None)
        complete = getattr(self._services, "goal_complete", None)
        if not callable(verify) or not callable(complete):
            self._status_label.setText(
                "Complete unavailable: verification API is not connected.")
            return False
        try:
            verification = _as_dict(verify(int(goal_id), evidence=evidence,
                                           criteria=criteria))
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText("Verification failed: " + _text(exc))
            return False
        self._show_verification_payload(verification, "Pre-completion verification")
        if not verification.get("ok") or not verification.get("verified"):
            self._status_label.setText(
                "Completion refused: verification " + _text(
                    verification.get("verdict") or "unverified")
                + "; goal status unchanged.")
            return False
        try:
            result = _as_dict(complete(int(goal_id), evidence=evidence,
                                       criteria=criteria))
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText("Completion failed safely: " + _text(exc))
            return False
        if not result.get("ok"):
            self._status_label.setText(
                "Completion refused: " + _text(result.get("error") or "unknown error")
                + "; goal status unchanged.")
            blockers = result.get("blockers") or result.get("blocking") or []
            if blockers:
                self._verification_blockers.setPlainText(
                    "Completion blockers:\n" + "\n".join(_text(item) for item in blockers))
            return False
        self.refresh()
        self._restore_selection(goal_id)
        self._status_label.setText(
            "Goal completed after verified evidence (status mutated by the service).")
        return True

    def _complete_goal(self) -> bool:
        return self._complete_with_evidence([], None)

    def _open_replan(self) -> None:
        if not self._current or not self._project:
            return
        dialog = ReplanDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self._replan(values["plan"], values["rationale"], values["trigger"])

    def _replan(self, plan, rationale: str, trigger: str = "manual") -> bool:
        goal = self._current or {}
        goal_id = goal.get("id")
        if goal_id is None:
            return False
        if not rationale or not str(rationale).strip():
            self._status_label.setText("Replan refused: rationale is required.")
            return False
        if not isinstance(plan, (dict, list)) or not plan:
            self._status_label.setText("Replan refused: structured plan is required.")
            return False
        method = getattr(self._services, "goal_replan", None)
        if not callable(method):
            self._status_label.setText("Replan unavailable: goal_replan is not connected.")
            return False
        try:
            result = _as_dict(method(int(goal_id), plan=plan,
                                     rationale=str(rationale).strip(),
                                     trigger=str(trigger or "manual")))
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText("Replan failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._status_label.setText(
                "Replan refused: " + _text(result.get("error") or "unknown error"))
            return False
        self._last_replan = result
        diff = result.get("diff") or result.get("milestone_diff") or {}
        version = result.get("version") or result.get("version_id") or "new"
        lines = ["Replan applied as version " + _text(version) + ".",
                 "Trigger: " + _text(result.get("trigger") or trigger),
                 "Rationale: " + _text(result.get("rationale") or rationale)]
        if isinstance(diff, Mapping):
            lines.append("Milestone diff: " + json.dumps(diff, ensure_ascii=False,
                                                         sort_keys=True))
        else:
            lines.append("Milestone diff: " + _text(diff))
        self._version_detail.setPlainText("\n".join(lines))
        self._status_label.setText("Replan applied; plan versions refreshed.")
        self.refresh()
        self._restore_selection(goal_id)
        return True

    def _refresh_evidence(self) -> None:
        goal = self._current or {}
        if goal.get("id") is None:
            return
        self._load_goal(goal)


    def _complete_goal_legacy_removed(self) -> bool:
        goal = self._current or {}
        goal_id = goal.get("id")
        error = self._complete_gate_error(goal)
        if error:
            self._status_label.setText("Complete disabled: " + error)
            return False
        try:
            result = _as_dict(self._services.goal_complete(int(goal_id)))
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText("Completion failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._status_label.setText(
                "Completion blocked by verification-gated service: "
                + _text(result.get("error") or "unknown error"))
            blockers = result.get("blockers") or result.get("blocking") or []
            if blockers:
                self._blockers_view.setPlainText("Completion blockers:\n" + "\n".join(
                    _text(item) for item in blockers))
            return False
        self.refresh()
        self._restore_selection(goal_id)
        self._status_label.setText("Goal completed through the verification-gated service.")
        return True

    # --------------------------------------------------------------- data
    def _refresh_progress_summary(self, project_id) -> None:
        try:
            result = _as_dict(self._services.goal_progress_summary(project_id=project_id))
        except Exception:  # noqa: BLE001
            self._progress_label.setText("Progress summary unavailable.")
            return
        if not result.get("ok"):
            self._progress_label.setText(
                "Progress summary error: " + _text(result.get("error") or "unknown"))
            return
        summary = _as_dict(result.get("summary"))
        counts = summary.get("goals_by_status") or {}
        self._progress_label.setText(
            "Goals: " + _text(summary.get("goals_total", 0))
            + "  |  Milestones: " + _text(summary.get("milestones_completed", 0))
            + "/" + _text(summary.get("milestones_total", 0))
            + "  |  Status: " + ", ".join(
                _text(k) + "=" + _text(v) for k, v in sorted(counts.items()) if v))

    def _refresh_next_work(self, project_id) -> None:
        try:
            result = _as_dict(self._services.goal_next_work(project_id=project_id, limit=20))
        except Exception:  # noqa: BLE001
            self._next_work.clear()
            self._next_work.addItem("Next work unavailable.")
            return
        self._next_work.clear()
        if not result.get("ok"):
            self._next_work.addItem("Next work error: " + _text(
                result.get("error") or "unknown"))
            return
        items = result.get("work") or []
        if not items:
            self._next_work.addItem("No eligible next work (read-only).")
        for item in items:
            row = _as_dict(item)
            self._next_work.addItem(
                _text(row.get("goal_title") or "goal") + " — "
                + _text(row.get("title") or "milestone")
                + " [" + _text(row.get("priority") or "") + "]")

    def on_page_shown(self) -> None:
        """Read-only refresh when the page is revealed; never starts execution."""
        if self._project:
            self.refresh()

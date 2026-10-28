"""Goals GUI workspace (stage 8 G4, NL-BP-216).

Read-only goal-mode UI over the injected AppServices goal facade. It never creates
missions, starts execution, accesses SQLite/network/models directly or marks a goal
complete outside the verification-gated service call. All data comes from
goal_list/goal_get/goal_progress/goal_milestones/goal_next_work/goal_progress_summary
and all mutations go through the explicit goal lifecycle/create facade methods.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPlainTextEdit, QPushButton, QSplitter,
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
        self._set_no_project_state()

    def _detect_facade(self) -> bool:
        return callable(getattr(self._services, "goal_list", None))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("GOALS")
        title.setObjectName("goalsTitle")
        title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        header.addWidget(title)
        self._scope_label = QLabel("No project open")
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
        hint = QLabel("Goals are explicit plans. This page never starts a mission or marks "
                      "a goal complete outside the verification-gated service action.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #AB83C6;")
        hint.setAccessibleName("Goals safety hint")
        layout.addWidget(hint)

        toolbar = QHBoxLayout()
        self._status_filter = QComboBox()
        self._status_filter.addItem("All statuses", None)
        for status in GOAL_STATUSES:
            self._status_filter.addItem(status, status)
        self._status_filter.setAccessibleName("Goal status filter")
        toolbar.addWidget(self._status_filter)
        self._priority_filter = QComboBox()
        self._priority_filter.addItem("All priorities", None)
        for priority in PRIORITIES:
            self._priority_filter.addItem(priority, priority)
        self._priority_filter.setAccessibleName("Goal priority filter")
        toolbar.addWidget(self._priority_filter)
        self._status_filter.currentIndexChanged.connect(self._apply_filters)
        self._priority_filter.currentIndexChanged.connect(self._apply_filters)
        self._create_btn = QPushButton("Create goal…")
        self._create_btn.setAccessibleName("Create a goal")
        self._create_btn.setToolTip("Create a goal; objective is required")
        self._create_btn.clicked.connect(self._create_goal_dialog)
        toolbar.addWidget(self._create_btn)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setAccessibleName("Refresh goals (read-only)")
        self._refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self._status_label = QLabel("Open a project to load goals.")
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
        title = QLabel("PROJECT GOALS")
        title.setStyleSheet("font-weight: 700; color: #7531FE;")
        layout.addWidget(title)
        self._goals_table = QTableWidget(0, 6)
        self._goals_table.setHorizontalHeaderLabels(
            ["Title", "Status", "Priority", "Progress", "Dependencies", "Blocked"])
        self._goals_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._goals_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._goals_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self._goals_table.setAccessibleName("Project goals")
        self._goals_table.itemSelectionChanged.connect(self._on_goal_selected)
        layout.addWidget(self._goals_table, 1)
        self._empty_label = QLabel("No goals in this project.")
        self._empty_label.setStyleSheet("color: #AB83C6;")
        self._empty_label.setAccessibleName("Goals empty state")
        layout.addWidget(self._empty_label)
        return box

    def _build_detail_area(self) -> QWidget:
        box = QWidget()
        box.setAccessibleName("Goal detail")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        self._detail_title = QLabel("No goal selected")
        self._detail_title.setStyleSheet("font-weight: 700; color: #46A3C0;")
        self._detail_title.setAccessibleName("Selected goal")
        layout.addWidget(self._detail_title)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("goalDetailTabs")
        self._tabs.setAccessibleName("Goal detail tabs")
        self._tabs.addTab(self._build_goal_tab(), "Goal")
        self._tabs.addTab(self._build_milestones_tab(), "Milestones")
        self._tabs.addTab(self._build_next_work_tab(), "Next work")
        self._tabs.addTab(self._build_progress_tab(), "Progress & decisions")
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
            button = QPushButton(label)
            button.setAccessibleName(label + " goal")
            button.clicked.connect(lambda checked=False, a=action: self._lifecycle(a))
            actions.addWidget(button)
            self._action_buttons[action] = button
        self._complete_btn = QPushButton("Complete (verification-gated)")
        self._complete_btn.setAccessibleName("Complete goal (verification-gated)")
        self._complete_btn.clicked.connect(self._complete_goal)
        actions.addWidget(self._complete_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self._blockers_view = QPlainTextEdit()
        self._blockers_view.setReadOnly(True)
        self._blockers_view.setAccessibleName("Goal blockers and completion gate")
        layout.addWidget(self._blockers_view, 1)
        return box

    def _build_milestones_tab(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self._milestones_table = QTableWidget(0, 6)
        self._milestones_table.setHorizontalHeaderLabels(
            ["Title", "Status", "Priority", "Depends", "Order", "Acceptance"])
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

    # ------------------------------------------------------------- lifecycle
    def _set_no_project_state(self) -> None:
        self._project = None
        self._current = None
        self._goals = []
        self._sorted_goals = []
        self._milestones = []
        self._progress = {}
        self._scope_label.setText("No project open")
        self._goals_table.setRowCount(0)
        self._empty_label.setText("Open a project to load goals.")
        self._empty_label.show()
        self._facade_label.setText(
            "Goal service: available" if self._facade_ready else "Goal service: unavailable")
        for button in [self._create_btn, self._refresh_btn, *self._action_buttons.values(),
                       self._complete_btn]:
            button.setEnabled(False)
        self._create_btn.setToolTip("Open a project first.")
        self._refresh_btn.setToolTip("Open a project first.")
        self._status_label.setText("Open a project to load goals.")
        self._detail_title.setText("No goal selected")
        self._meta_label.setText("")
        self._objective_view.setPlainText("")
        self._blockers_view.setPlainText("")
        self._milestones_table.setRowCount(0)
        self._next_work.clear()
        self._progress_label.setText("No project progress.")
        self._decisions_view.setPlainText("")

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
        complete_error = self._complete_gate_error(goal)
        self._complete_btn.setEnabled(not bool(complete_error) and bool(goal.get("id")))
        self._complete_btn.setToolTip(
            complete_error or "Requires active status, milestones, and all milestones completed; "
            "the service verifies completion.")
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
    def _create_goal_dialog(self) -> None:
        if not self._project or not self._facade_ready:
            return
        dialog = CreateGoalDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._create_goal(dialog.values())

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

    def _complete_goal(self) -> bool:
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

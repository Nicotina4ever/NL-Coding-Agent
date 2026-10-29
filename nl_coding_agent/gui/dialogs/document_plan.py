"""Document-driven plan preview/edit/approve/reject dialog (NL-BP-221 GUI).

All operations go through injected AppServices docs_plan_* methods. The dialog is a
read-only planning workspace: it never executes a plan, creates/starts a mission or
goal, calls a model, accesses SQLite/network directly, or edits documents.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from nl_coding_agent.gui.components import section_header, status_badge


def _dict(value: Any) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value if value is not None else "")


class MilestoneEditDialog(QDialog):
    """Validated JSON/text milestone editor; every edit requires a rationale."""

    def __init__(self, milestones, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit plan milestones")
        self.setAccessibleName("Edit document plan milestones")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Edit the milestone JSON list. Required fields: key, title, priority "
            "(P0-P3); optional dependencies/risk/validation/provenance. "
            "Every edit creates an immutable new version and requires a rationale."))
        self._json = QPlainTextEdit()
        self._json.setAccessibleName("Milestones JSON editor")
        self._json.setPlainText(json.dumps(list(milestones or []), indent=2,
                                            ensure_ascii=False))
        self._initial_json = self._json.toPlainText()
        layout.addWidget(self._json, 2)
        self._rationale = QLineEdit()
        self._rationale.setAccessibleName("Edit rationale (required)")
        self._rationale.setPlaceholderText("Required: why is this plan changing?")
        layout.addWidget(self._rationale)
        self._error = QLabel("")
        self._error.setStyleSheet("color: #E4469B;")
        self._error.setAccessibleName("Milestone edit validation error")
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validation_error(self) -> str:
        if not self._rationale.text().strip():
            return "Rationale is required."
        try:
            parsed = json.loads(self._json.toPlainText())
        except ValueError as exc:
            return "Invalid milestone JSON: " + str(exc)
        if not isinstance(parsed, list) or not parsed:
            return "Milestones must be a non-empty JSON list."
        for item in parsed:
            if not isinstance(item, Mapping):
                return "Each milestone must be an object."
            if not str(item.get("key") or "").strip():
                return "Each milestone needs a key."
            if not str(item.get("title") or "").strip():
                return "Each milestone needs a title."
            if str(item.get("priority") or "") not in ("P0", "P1", "P2", "P3"):
                return "Milestone priority must be P0-P3."
        return ""

    def accept(self):
        error = self.validation_error()
        if error:
            self._error.setText(error)
            return
        super().accept()

    def values(self) -> dict:
        return {"milestones": json.loads(self._json.toPlainText()),
                "rationale": self._rationale.text().strip()}

    def reject(self) -> None:
        if self._json.toPlainText() != self._initial_json or self._rationale.text():
            answer = QMessageBox.question(
                self, "Unsaved plan edits", "Discard unsaved milestone edits?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                return
        super().reject()


class DocumentPlanDialog(QDialog):
    """Read-only planning workspace with explicit edit/approve/reject actions."""

    def __init__(self, services, project=None, parent=None, *, plan_id=None):
        super().__init__(parent)
        self._services = services
        self._project = dict(project) if project else None
        self._plan = {}
        self._plan_id = int(plan_id) if plan_id is not None else None
        self._versions: list[dict] = []
        self._loading = False
        self.setWindowTitle("Document plan")
        self.setAccessibleName("Document plan preview, edit, approve and reject")
        self.resize(980, 720)
        self._build_ui()
        self._update_controls()
        if self._plan_id is not None:
            self.load_plan(self._plan_id)
        elif self._project:
            self._status.setText("Generate a draft plan from the project's documents "
                                 "(explicit action; nothing is executed).")
        else:
            self._status.setText("Open/select a project first.")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(section_header(
            "DOCUMENT PLAN",
            "Draft plan from project documentation. Notes are UNTRUSTED; "
            "approval records metadata and never executes anything."))
        top = QHBoxLayout()
        self._project_label = QLabel(
            "Project: " + (_text((self._project or {}).get("name")) or "—"))
        self._project_label.setAccessibleName("Document plan project")
        top.addWidget(self._project_label)
        top.addStretch()
        self._generate_btn = QPushButton("Generate plan…")
        self._generate_btn.setAccessibleName("Generate document-driven draft plan")
        self._generate_btn.clicked.connect(self.generate_plan)
        top.addWidget(self._generate_btn)
        self._edit_btn = QPushButton("Edit milestones…")
        self._edit_btn.setAccessibleName("Edit document plan milestones")
        self._edit_btn.clicked.connect(self.open_edit_dialog)
        top.addWidget(self._edit_btn)
        self._approve_btn = QPushButton("Approve…")
        self._approve_btn.setAccessibleName("Approve current document plan version")
        self._approve_btn.clicked.connect(lambda: self.confirm_approve())
        top.addWidget(self._approve_btn)
        self._reject_btn = QPushButton("Reject…")
        self._reject_btn.setAccessibleName("Reject current document plan version")
        self._reject_btn.clicked.connect(lambda: self.confirm_reject())
        top.addWidget(self._reject_btn)
        layout.addLayout(top)
        self._status = QLabel("No plan loaded.")
        self._status.setWordWrap(True)
        self._status.setAccessibleName("Document plan status")
        layout.addWidget(self._status)
        self._tabs = QTabWidget()
        self._tabs.setAccessibleName("Document plan sections")
        self._tabs.addTab(self._build_summary_tab(), "Summary")
        self._tabs.addTab(self._build_milestones_tab(), "Milestones")
        self._tabs.addTab(self._build_risks_tab(), "Reconciliation")
        self._tabs.addTab(self._build_versions_tab(), "Versions")
        layout.addWidget(self._tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._shortcut_generate = QShortcut(QKeySequence("Ctrl+G"), self,
                                            activated=self.generate_plan)
        self._shortcut_edit = QShortcut(QKeySequence("Ctrl+E"), self,
                                        activated=self.open_edit_dialog)

    def _build_summary_tab(self):
        box = QWidget()
        layout = QFormLayout(box)
        self._title_value = QLabel("—")
        self._title_value.setWordWrap(True)
        self._title_value.setAccessibleName("Plan title")
        layout.addRow("Title", self._title_value)
        self._objective_value = QLabel("—")
        self._objective_value.setWordWrap(True)
        self._objective_value.setAccessibleName("Plan objective")
        layout.addRow("Objective", self._objective_value)
        self._status_badge = status_badge("DRAFT", "idle")
        layout.addRow("Status", self._status_badge)
        self._acceptance_view = QPlainTextEdit()
        self._acceptance_view.setReadOnly(True)
        self._acceptance_view.setAccessibleName("Acceptance criteria with provenance")
        self._acceptance_view.setMaximumHeight(120)
        layout.addRow("Acceptance", self._acceptance_view)
        self._limitations_view = QPlainTextEdit()
        self._limitations_view.setReadOnly(True)
        self._limitations_view.setAccessibleName("Plan limitations and unknowns")
        self._limitations_view.setMaximumHeight(120)
        layout.addRow("Limitations", self._limitations_view)
        self._provenance_view = QPlainTextEdit()
        self._provenance_view.setReadOnly(True)
        self._provenance_view.setAccessibleName("Plan provenance references")
        layout.addRow("Provenance", self._provenance_view)
        return box

    def _build_milestones_tab(self):
        box = QWidget()
        layout = QVBoxLayout(box)
        self._milestone_table = QTableWidget(0, 8)
        self._milestone_table.setHorizontalHeaderLabels(
            ["Key", "Title", "Priority", "Dependencies", "Risk", "Validation",
             "Explicit/Inferred", "Provenance"])
        self._milestone_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._milestone_table.setAccessibleName("Plan milestones")
        layout.addWidget(self._milestone_table)
        return box

    def _build_risks_tab(self):
        box = QWidget()
        layout = QVBoxLayout(box)
        self._blockers_view = QPlainTextEdit()
        self._blockers_view.setReadOnly(True)
        self._blockers_view.setAccessibleName("Reconciliation blockers and risks")
        layout.addWidget(self._blockers_view)
        return box

    def _build_versions_tab(self):
        box = QWidget()
        layout = QVBoxLayout(box)
        self._version_table = QTableWidget(0, 6)
        self._version_table.setHorizontalHeaderLabels(
            ["Version", "Status", "Current", "Rationale", "Created", "Hash"])
        self._version_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._version_table.setAccessibleName("Immutable plan version history")
        layout.addWidget(self._version_table)
        self._immutability = QLabel(
            "Versions are immutable snapshots; edit creates a new version. "
            "Approval/rejection metadata stays on its version.")
        self._immutability.setWordWrap(True)
        layout.addWidget(self._immutability)
        return box

    # ------------------------------------------------------------- lifecycle
    def _facade(self, suffix: str):
        return getattr(self._services, "docs_plan_" + suffix, None)

    def _update_controls(self):
        has_project = bool(self._project)
        has_plan = bool(self._plan_id)
        generate = callable(self._facade("generate"))
        edit = callable(self._facade("edit"))
        approve = callable(self._facade("approve"))
        reject = callable(self._facade("reject"))
        self._generate_btn.setEnabled(has_project and generate and not self._loading)
        self._edit_btn.setEnabled(has_plan and edit and not self._loading)
        self._approve_btn.setEnabled(has_plan and approve and not self._loading)
        self._reject_btn.setEnabled(has_plan and reject and not self._loading)
        for button, enabled, reason in (
                (self._generate_btn, self._generate_btn.isEnabled(),
                 "Select a project and configure the document-plan facade."),
                (self._edit_btn, self._edit_btn.isEnabled(),
                 "Generate/load a plan and configure docs_plan_edit."),
                (self._approve_btn, self._approve_btn.isEnabled(),
                 "Generate/load a plan and configure docs_plan_approve."),
                (self._reject_btn, self._reject_btn.isEnabled(),
                 "Generate/load a plan and configure docs_plan_reject.")):
            button.setToolTip("" if enabled else reason)

    def generate_plan(self) -> bool:
        if not self._project:
            self._set_error("Open or select a project first.")
            return False
        method = self._facade("generate")
        if not callable(method):
            self._set_error("Document-plan generation is not configured.")
            return False
        root = str(self._project.get("root") or "")
        self._loading = True
        self._update_controls()
        self._status.setText("Generating draft plan from documents…")
        try:
            result = _dict(method(project_root=root, consent=True))
        except Exception as exc:  # noqa: BLE001
            self._loading = False
            self._update_controls()
            self._set_error("Generation failed: " + _text(exc))
            return False
        self._loading = False
        if not result.get("ok"):
            self._update_controls()
            self._show_service_error(result, "Generation failed")
            return False
        plan = _dict(result.get("plan"))
        self._plan_id = int(plan.get("plan_id") or result.get("plan_id") or 0) or None
        self._load_plan(plan)
        self._status.setText("Draft plan generated. Review, edit, approve or reject explicitly.")
        return True

    def load_plan(self, plan_id: int) -> bool:
        method = self._facade("get")
        if not callable(method):
            self._set_error("Document-plan loading is not configured.")
            return False
        try:
            result = _dict(method(int(plan_id)))
        except Exception as exc:  # noqa: BLE001
            self._set_error("Loading failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._show_service_error(result, "Loading failed")
            return False
        self._plan_id = int(plan_id)
        self._load_plan(_dict(result.get("plan")))
        return True

    def _load_plan(self, plan: dict):
        # The persistence facade returns a plan header with its immutable current
        # version nested under `current`; freshly generated plans are flat.
        plan = dict(plan)
        current = _dict(plan.get("current"))
        for field in ("milestones", "acceptance_criteria", "limitations", "unknowns",
                      "provenance", "blockers", "risks", "objective", "title"):
            if field in current:
                plan[field] = current[field]
        self._plan = plan
        self._plan_id = int(plan.get("plan_id") or self._plan_id or 0) or None
        self._title_value.setText(_text(plan.get("title") or "—"))
        objective = _text(plan.get("objective") or "")
        self._objective_value.setText(objective or
                                      "No documented objective found (not fabricated).")
        current_version = plan.get("current_version") or plan.get("version")
        self._status_badge.setText(_text(plan.get("status") or "draft").upper())
        self._status_badge.setProperty(
            "tone", "ok" if plan.get("status") == "approved"
            else "error" if plan.get("status") == "rejected" else "info")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        milestones = list(plan.get("milestones") or [])
        self._milestone_table.setRowCount(len(milestones))
        for row, item in enumerate(milestones):
            values = [_text(item.get("key")), _text(item.get("title")),
                      _text(item.get("priority")),
                      ", ".join(_text(dep) for dep in item.get("dependencies") or [])
                      or "—",
                      _text(item.get("risk") or "—"),
                      _text(item.get("validation") or item.get("validation_strategy") or "—"),
                      _text(item.get("label") or item.get("mode") or "unknown"),
                      _text(item.get("provenance") or "—")]
            for column, value in enumerate(values):
                self._milestone_table.setItem(row, column, QTableWidgetItem(str(value)))
        acceptance = plan.get("acceptance_criteria") or []
        self._acceptance_view.setPlainText(
            "\n".join(
                "• " + _text(item.get("text") if isinstance(item, Mapping) else item)
                + " [" + _text(item.get("label") if isinstance(item, Mapping)
                               else "unknown") + "]"
                for item in acceptance) or "No explicit acceptance criteria.")
        limitations = list(plan.get("limitations") or []) + list(plan.get("unknowns") or [])
        self._limitations_view.setPlainText(
            "\n".join("• " + _text(item) for item in limitations)
            or "No limitations/unknowns recorded.")
        self._provenance_view.setPlainText(
            json.dumps(plan.get("provenance") or [], indent=2, ensure_ascii=False,
                       default=str))
        blockers = list(plan.get("blockers") or [])
        risks = list(plan.get("risks") or [])
        self._blockers_view.setPlainText(
            "BLOCKERS\n" + ("\n".join("• " + json.dumps(item, ensure_ascii=False,
                                                        default=str)
                                       for item in blockers) or "none") +
            "\n\nRISKS\n" + ("\n".join("• " + json.dumps(item, ensure_ascii=False,
                                                         default=str)
                                        for item in risks) or "none") +
            "\n\nNo execution, mission creation or goal creation is performed.")
        self._load_versions()
        self._update_controls()
        self._tabs.setCurrentIndex(0)

    def _load_versions(self):
        versions = []
        method = self._facade("versions")
        if callable(method) and self._plan_id:
            try:
                result = _dict(method(self._plan_id))
                if result.get("ok"):
                    versions = list(result.get("versions") or [])
            except Exception:  # noqa: BLE001
                versions = []
        if not versions:
            versions = list(self._plan.get("versions") or [])
        self._versions = [dict(item) for item in versions if isinstance(item, Mapping)]
        current = self._plan.get("current_version") or self._plan.get("version")
        self._version_table.setRowCount(len(self._versions))
        for row, item in enumerate(self._versions):
            number = item.get("version") or item.get("version_id")
            values = [_text(number), _text(item.get("status") or "draft"),
                      "yes" if str(number) == str(current) or item.get("is_current")
                      else "no",
                      _text(item.get("rationale") or "—"),
                      _text(item.get("created_at") or "—"),
                      _text(item.get("plan_hash") or "—")[:16]]
            for column, value in enumerate(values):
                self._version_table.setItem(row, column, QTableWidgetItem(str(value)))

    def open_edit_dialog(self) -> bool:
        if not self._plan_id:
            return False
        dialog = MilestoneEditDialog(self._plan.get("milestones") or [], self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            if self.edit_milestones(values["milestones"], values["rationale"]):
                return True
            # Preserve the edited values when the backend rejects saving them.
            dialog._error.setText(self._status.text())
        return False

    def edit_milestones(self, milestones, rationale: str) -> bool:
        method = self._facade("edit")
        if not callable(method) or not self._plan_id:
            self._set_error("Editing requires a loaded plan and docs_plan_edit.")
            return False
        if not str(rationale or "").strip():
            self._set_error("Edit refused: a rationale is required.")
            return False
        if not isinstance(milestones, list) or not milestones:
            self._set_error("Edit refused: milestones must be a non-empty list.")
            return False
        for item in milestones:
            if not isinstance(item, Mapping):
                self._set_error("Edit refused: each milestone must be an object.")
                return False
            if not str(item.get("key") or "").strip() or not str(
                    item.get("title") or "").strip():
                self._set_error("Edit refused: each milestone needs key and title.")
                return False
            if str(item.get("priority") or "") not in ("P0", "P1", "P2", "P3"):
                self._set_error("Edit refused: milestone priority must be P0-P3.")
                return False
        try:
            result = _dict(method(self._plan_id, milestones, str(rationale).strip()))
        except Exception as exc:  # noqa: BLE001
            self._set_error("Edit failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._show_service_error(result, "Edit refused")
            return False
        self.load_plan(self._plan_id)
        self._status.setText("New immutable plan version created: "
                             + str(result.get("version") or result.get("current_version")
                                   or "next"))
        return True

    def _selected_version(self):
        row = self._version_table.currentRow()
        if 0 <= row < len(self._versions):
            return self._versions[row].get("version")
        return None

    def confirm_approve(self, version=None, reason=None) -> bool:
        target = version if version is not None else (
            self._plan.get("current_version") or self._plan.get("version"))
        answer = QMessageBox.question(
            self, "Approve document plan",
            "Approve plan version " + _text(target) + "?\n\n"
            "Approval records metadata only; it never executes the plan or starts a mission.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return False
        if reason is None:
            reason, ok = QInputDialog.getText(
                self, "Plan approval reason", "Required reason:")
            if not ok:
                return False
        return self.approve(version=target, reason=reason)

    def confirm_reject(self, version=None, reason=None) -> bool:
        target = version if version is not None else (
            self._plan.get("current_version") or self._plan.get("version"))
        answer = QMessageBox.question(
            self, "Reject document plan",
            "Reject plan version " + _text(target) + "?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return False
        if reason is None:
            reason, ok = QInputDialog.getText(
                self, "Plan rejection reason", "Required reason:")
            if not ok:
                return False
        return self.reject_plan(version=target, reason=reason)

    def approve(self, version=None, reason: str = "") -> bool:
        method = self._facade("approve")
        if not callable(method) or not self._plan_id:
            self._set_error("Approval requires a loaded plan and docs_plan_approve.")
            return False
        if not str(reason or "").strip():
            self._set_error("Approval refused: a reason is required.")
            return False
        try:
            result = _dict(method(self._plan_id, version, reason=str(reason).strip()))
        except Exception as exc:  # noqa: BLE001
            self._set_error("Approval failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._show_service_error(result, "Approval refused")
            return False
        self.load_plan(self._plan_id)
        self._status.setText("Plan approved (metadata only; nothing executed).")
        return True

    def reject_plan(self, version=None, reason: str = "") -> bool:
        method = self._facade("reject")
        if not callable(method) or not self._plan_id:
            self._set_error("Rejection requires a loaded plan and docs_plan_reject.")
            return False
        if not str(reason or "").strip():
            self._set_error("Rejection refused: a reason is required.")
            return False
        try:
            result = _dict(method(self._plan_id, version, reason=str(reason).strip()))
        except Exception as exc:  # noqa: BLE001
            self._set_error("Rejection failed: " + _text(exc))
            return False
        if not result.get("ok"):
            self._show_service_error(result, "Rejection refused")
            return False
        self.load_plan(self._plan_id)
        self._status.setText("Plan rejected (metadata only; nothing executed).")
        return True

    # -------------------------------------------------------------- errors
    def _set_error(self, message: str):
        self._status.setText(message)
        self._status.setStyleSheet("color: #E26472;")

    def _show_service_error(self, result: dict, prefix: str):
        error = result.get("error")
        if isinstance(error, Mapping):
            message = str(error.get("message") or error.get("code") or "unknown error")
        else:
            message = str(error or result.get("outcome") or "unknown error")
        self._set_error(prefix + ": " + message)

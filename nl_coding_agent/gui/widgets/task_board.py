"""Mission and task board backed by AppServices (no direct database access)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from nl_coding_agent.app.services import AppServices

_STATUS_ORDER = ["running", "pending", "failed", "blocked", "completed"]


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


class TaskBoardWidget(QWidget):
    """Displays missions, their task graph, progress, and run/resume controls."""

    mission_selected = Signal(int)
    mission_finished = Signal(dict)
    document_plan_requested = Signal()
    review_requested = Signal(int)

    def __init__(self, services: AppServices, parent=None):
        super().__init__(parent)
        self._services = services
        self._project: dict | None = None
        self._selected_mission_id: int | None = None
        self._build_ui()
        _register_retranslate(self)
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self._title = QLabel(_tr("task_board.title", "Missions & Tasks"))
        title = self._title
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        self._roadmap_btn = QPushButton(_tr(
            "task_board.load_roadmap", "Load Roadmap Mission"))
        self._roadmap_btn.setToolTip(_tr(
            "task_board.load_roadmap_tooltip",
            "Create a mission from docs/NEXT_SELF_BUILD_MISSION.md"))
        self._roadmap_btn.clicked.connect(self._load_roadmap)
        header.addWidget(self._roadmap_btn)

        self._queue_label = QLabel(_tr("task_board.queue_empty", "Queue: empty"))
        self._queue_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        header.addWidget(self._queue_label)

        self._refresh_btn = QPushButton(_tr("task_board.refresh", "Refresh"))
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        self._history_toggle = QCheckBox(_tr("task_board.history", "History"))
        self._history_toggle.toggled.connect(self.refresh)
        header.addWidget(self._history_toggle)
        self._document_btn = QPushButton(_tr("workspace.documents", "Document plan"))
        self._document_btn.clicked.connect(self.document_plan_requested)
        header.addWidget(self._document_btn)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._mission_list = QListWidget()
        self._mission_list.setMinimumWidth(260)
        self._mission_list.currentItemChanged.connect(self._on_mission_selected)
        splitter.addWidget(self._mission_list)

        right = QSplitter(Qt.Orientation.Vertical)

        self._task_tree = QTreeWidget()
        self._task_tree.setHeaderLabels([
            _tr("task_board.header_task", "Task"),
            _tr("task_board.header_role", "Role"),
            _tr("task_board.header_status", "Status"),
            _tr("task_board.header_attempts", "Attempts")])
        self._task_tree.setColumnWidth(0, 300)
        self._task_tree.setColumnWidth(1, 90)
        self._task_tree.setColumnWidth(2, 90)
        self._task_tree.setAlternatingRowColors(True)
        right.addWidget(self._task_tree)

        self._details = QTextEdit()
        self._details.setReadOnly(True)
        self._details.setObjectName("logOutput")
        right.addWidget(self._details)
        right.setSizes([360, 180])
        splitter.addWidget(right)
        splitter.setSizes([300, 700])
        layout.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setMaximumWidth(220)
        footer.addWidget(self._progress)

        self._status_label = QLabel(_tr(
            "task_board.select_mission", "Select a mission"))
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        footer.addWidget(self._status_label)
        footer.addStretch()

        self._run_btn = QPushButton(_tr("task_board.run_resume", "Run / Resume"))
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_selected)
        self._review_btn = QPushButton(_tr("task_board.review", "Review candidate"))
        self._review_btn.clicked.connect(lambda: self.review_requested.emit(self._selected_mission_id)
                                         if self._selected_mission_id else None)
        self._archive_btn = QPushButton("Archive")
        self._archive_btn.setObjectName("archiveMissionButton")
        self._archive_btn.setEnabled(False)
        self._archive_btn.clicked.connect(self._archive_selected)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setObjectName("deleteMissionButton")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_selected)
        self._steer_btn = QPushButton("Steer")
        self._steer_btn.setObjectName("steerMissionButton")
        self._steer_btn.setEnabled(False)
        self._steer_btn.clicked.connect(self._steer_selected)
        footer.addWidget(self._review_btn)
        footer.addWidget(self._steer_btn)
        footer.addWidget(self._archive_btn)
        footer.addWidget(self._delete_btn)
        footer.addWidget(self._run_btn)
        layout.insertLayout(1, footer)

    def retranslate(self) -> None:
        self._title.setText(_tr("task_board.title", "Missions & Tasks"))
        self._roadmap_btn.setText(_tr(
            "task_board.load_roadmap", "Load Roadmap Mission"))
        self._roadmap_btn.setToolTip(_tr(
            "task_board.load_roadmap_tooltip",
            "Create a mission from docs/NEXT_SELF_BUILD_MISSION.md"))
        self._refresh_btn.setText(_tr("task_board.refresh", "Refresh"))
        self._review_btn.setText(_tr("task_board.review", "Review candidate"))
        self._history_toggle.setText(_tr("task_board.history", "History"))
        self._document_btn.setText(_tr("workspace.documents", "Document plan"))
        self._run_btn.setText(_tr("task_board.run_resume", "Run / Resume"))
        self._task_tree.setHeaderLabels([
            _tr("task_board.header_task", "Task"),
            _tr("task_board.header_role", "Role"),
            _tr("task_board.header_status", "Status"),
            _tr("task_board.header_attempts", "Attempts")])
        self._update_queue_summary()

    # ------------------------------------------------------------------ project

    def set_project(self, project: dict | None):
        self._project = project
        self.refresh()

    def _project_root(self) -> Path | None:
        if self._project and self._project.get("root"):
            return Path(self._project["root"])
        return None

    # ------------------------------------------------------------------ refresh

    @Slot()
    def refresh(self):
        selected = self._selected_mission_id
        self._mission_list.clear()
        project_id = self._project["id"] if self._project else None
        missions = self._services.list_missions(project_id)
        if project_id is not None and not missions:
            missions = [
                m for m in self._services.list_missions(None)
                if m.get("project_id") is None
            ]
        from nl_coding_agent.core.doc_planning import is_document_plan_request
        visible = [m for m in missions if self._history_toggle.isChecked() or not (
            m.get("status") == "blocked" and is_document_plan_request(m.get("goal") or ""))]
        for mission in visible:
            requirement = mission.get("requirement_id")
            suffix = ("  [" + str(requirement) + "]") if requirement else ""
            label = (
                f"#{mission['id']}  [{mission['status']}]  "
                f"{mission.get('title', '')[:70]}{suffix}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, mission["id"])
            self._mission_list.addItem(item)
            if selected == mission["id"]:
                self._mission_list.setCurrentItem(item)
        self._update_queue_summary()
        if visible and self._mission_list.currentRow() < 0:
            self._mission_list.setCurrentRow(0)
        elif not visible:
            self._selected_mission_id = None
            self._run_btn.setEnabled(False)
            self._task_tree.clear()
            self._details.setPlainText(_tr(
                "task_board.no_missions_detail",
                "No missions yet. Create one from the CLI or load a roadmap mission."))
            self._status_label.setText(_tr(
                "task_board.no_missions", "No missions"))
            self._progress.setValue(0)

    def _queue_by_mission(self, project_id: int) -> dict[int, dict]:
        queue: dict[int, dict] = {}
        try:
            items = self._services.supervisor_queue(project_id, limit=50)
        except Exception:
            items = []
        for item in items:
            mission_id = item.get("mission_id")
            if mission_id is not None:
                queue[int(mission_id)] = item
        return queue

    def _update_queue_summary(self):
        project_id = self._project["id"] if self._project else None
        if project_id is None:
            self._queue_label.setText(_tr(
                "task_board.queue_no_project", "Queue: no project"))
            return
        try:
            items = self._services.supervisor_queue(project_id, limit=50)
        except Exception:
            items = []
        if not items:
            self._queue_label.setText(_tr(
                "task_board.queue_empty", "Queue: empty"))
            return
        counts: dict[str, int] = {}
        for item in items:
            state = str(item.get("state") or "?")
            counts[state] = counts.get(state, 0) + 1
        text = ", ".join(f"{state} {count}" for state, count in sorted(counts.items()))
        self._queue_label.setText(_tr(
            "task_board.queue_prefix", "Queue: ") + text)

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_mission_selected(self, current, previous):
        if current is None:
            self._selected_mission_id = None
            self._run_btn.setEnabled(False)
            return
        mission_id = current.data(Qt.ItemDataRole.UserRole)
        self._selected_mission_id = mission_id
        self.mission_selected.emit(mission_id)
        self._show_mission(mission_id)

    def _show_mission(self, mission_id: int):
        details = self._services.get_mission_details(mission_id)
        if not details:
            self._details.setPlainText(f"Mission #{mission_id} not found")
            return

        self._task_tree.clear()
        tasks = details.get("tasks", [])
        grouped: dict[str, list[dict]] = {}
        for task in tasks:
            grouped.setdefault(task.get("status") or "pending", []).append(task)

        for status in _STATUS_ORDER:
            if status not in grouped:
                continue
            parent = QTreeWidgetItem([f"{status.title()} ({len(grouped[status])})", "", "", ""])
            parent.setFirstColumnSpanned(True)
            self._task_tree.addTopLevelItem(parent)
            for task in grouped[status]:
                role = task.get("agent_role") or "—"
                item = QTreeWidgetItem([
                    task.get("title", ""),
                    role,
                    task.get("status", ""),
                    str(task.get("attempts", 0)),
                ])
                if task.get("last_error"):
                    item.setToolTip(0, str(task["last_error"])[:1000])
                parent.addChild(item)
            parent.setExpanded(True)

        progress = details.get("progress") or {}
        self._progress.setValue(int(progress.get("percent", 0)))
        self._status_label.setText(_tr("task_board.mission_state",
            "Mission #{id}: {status} · {completed}/{total} tasks · resumes: {resumes}",
            id=mission_id, status=_tr("mission.state_" + str(details.get("status")), str(details.get("status"))),
            completed=progress.get("completed", 0), total=progress.get("total", 0),
            resumes=details.get("resume_count", 0)))
        from nl_coding_agent.core.doc_planning import is_document_plan_request
        document_only = is_document_plan_request(details.get("goal") or "")
        self._review_btn.setEnabled(bool(details.get("staging_dir")))
        self._document_btn.setVisible(document_only)
        self._run_btn.setToolTip(_tr("task_board.document_only", "Historical document request: open Document plan; coding execution is unavailable.") if document_only else "")
        self._run_btn.setEnabled(not document_only and details.get("status") in ("pending", "interrupted", "failed", "blocked"))
        terminal = details.get("status") in ("completed", "failed", "blocked", "interrupted")
        self._archive_btn.setEnabled(terminal and not details.get("archived_at"))
        self._delete_btn.setEnabled(terminal and bool(details.get("archived_at")))
        self._steer_btn.setEnabled(details.get("status") in ("pending", "running", "interrupted", "blocked"))

        queue_item = None
        project_id = details.get("project_id")
        if project_id is not None:
            queue_item = self._queue_by_mission(int(project_id)).get(int(mission_id))
        lines = [
            f"Mission #{mission_id} — {details.get('title', '')}",
            f"Status: {details.get('status')}",
            f"Requirement: {details.get('requirement_id') or '(none)'}",
            "Queue state: " + (
                str(queue_item.get("state")) + " / attempts "
                + str(queue_item.get("attempts") or 0)
                if queue_item else "(not queued)"
            ),
            f"Goal: {details.get('goal', '')}",
            "",
            f"Result: {details.get('result_summary') or '(none yet)'}",
            f"Review verdict: {details.get('review_verdict') or '(none yet)'}",
            f"Diff: {details.get('diff_stat') or '(none yet)'}",
            f"Changed paths: {details.get('changed_paths') or '[]'}",
            "",
            "Handoffs:",
        ]
        for handoff in details.get("handoffs", []):
            lines.append(
                f"  [{handoff.get('created_at', '')}] {handoff.get('from_role')} -> "
                f"{handoff.get('to_role')}: {handoff.get('summary', '')}"
            )
        runs = details.get("verification_runs", [])
        if runs:
            lines.append("")
            lines.append("Verification runs:")
            for run in runs[-5:]:
                lines.append(
                    f"  #{run.get('id')} exit={run.get('exit_code')} "
                    f"passed={bool(run.get('passed'))} {run.get('command')}"
                )
        self._details.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------ actions

    def _resolve_root(self, details: dict) -> Path | None:
        project_id = details.get("project_id")
        if project_id:
            project = self._services.get_project(project_id)
            if project and project.get("root"):
                return Path(project["root"])
        return self._project_root()

    @Slot()
    def _archive_selected(self) -> None:
        mission_id = self._selected_mission_id
        if not mission_id:
            return
        answer = QMessageBox.question(
            self, "Archive mission",
            f"Archive mission #{mission_id}? Data and evidence are retained."
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            details = self._services.get_mission_details(mission_id) or {}
            self._services.archive_mission(mission_id, project_id=details.get("project_id"))
        except Exception as exc:
            QMessageBox.warning(self, "Archive failed", str(exc))
            return
        self.refresh()

    def _delete_selected(self) -> None:
        mission_id = self._selected_mission_id
        if not mission_id:
            return
        answer = QMessageBox.question(
            self, "Delete archived mission",
            f"Delete mission #{mission_id} from the mission database? "
            "Staged files remain and are handled only by the Storage Manager."
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            details = self._services.get_mission_details(mission_id) or {}
            self._services.delete_mission(mission_id, project_id=details.get("project_id"))
        except Exception as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))
            return
        self._selected_mission_id = None
        self.refresh()

    def _steer_selected(self) -> None:
        mission_id = self._selected_mission_id
        if not mission_id:
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Steer mission",
            "Instruction consumed at the next developer/reviewer checkpoint:")
        if not ok or not str(text).strip():
            return
        try:
            details = self._services.get_mission_details(mission_id) or {}
            self._services.steer_mission(
                mission_id, str(text), project_id=details.get("project_id"))
        except Exception as exc:
            QMessageBox.warning(self, "Steering failed", str(exc))
            return
        self._status_label.setText(f"Steering queued for mission #{mission_id}.")

    def _run_selected(self):
        if not self._selected_mission_id:
            return
        details = self._services.get_mission_details(self._selected_mission_id)
        if not details:
            return
        from nl_coding_agent.core.doc_planning import is_document_plan_request
        if is_document_plan_request(details.get("goal") or ""):
            self.document_plan_requested.emit()
            return
        root = self._resolve_root(details)
        if root is None:
            QMessageBox.warning(self, "No project", "Open a project before running a mission.")
            return
        if details.get("status") == "running":
            QMessageBox.information(self, "Mission running", "This mission is already running.")
            return

        self._run_btn.setEnabled(False)
        self._status_label.setText(f"Scheduling mission #{self._selected_mission_id}…")

        def _done(result: dict):
            self.mission_finished.emit(result)

        try:
            self._services.run_mission(
                mission_id=self._selected_mission_id,
                project_root=root,
                goal=details.get("goal"),
                on_done=_done,
            )
        except Exception as exc:
            self._run_btn.setEnabled(True)
            QMessageBox.critical(self, "Mission error", str(exc))

    @Slot()
    def _load_roadmap(self):
        root = self._project_root()
        if root is None:
            QMessageBox.warning(self, "No project", "Open a project before loading a roadmap mission.")
            return
        try:
            roadmap = self._services.next_roadmap_mission(root)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "Roadmap missing", str(exc))
            return
        project_id = self._project["id"] if self._project else None
        mission_id = self._services.create_mission(
            project_id=project_id,
            title=roadmap["title"],
            goal=roadmap["goal"],
        )
        self._selected_mission_id = mission_id
        self.refresh()
        self._status_label.setText(f"Created mission #{mission_id} from roadmap")

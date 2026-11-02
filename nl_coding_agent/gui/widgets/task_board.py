"""Mission and task board backed by AppServices (no direct database access)."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
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
        self._mission_cache: dict[int, dict] = {}
        self._bulk_operation: dict | None = None
        self._bulk_deadline = 0.0
        self._bulk_timer = QTimer(self)
        self._bulk_timer.setInterval(1000)
        self._bulk_timer.timeout.connect(self._poll_bulk_operation)
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

        filters = QHBoxLayout()
        self._search_filter = QLineEdit()
        self._search_filter.setObjectName("missionSearchFilter")
        self._search_filter.setAccessibleName("Search missions")
        self._search_filter.setPlaceholderText(_tr(
            "task_board.filter_placeholder", "Filter missions by title or goal"))
        self._search_filter.editingFinished.connect(self.refresh)
        filters.addWidget(self._search_filter, 1)
        self._status_filter = QComboBox()
        self._status_filter.setObjectName("missionStatusFilter")
        self._status_filter.setAccessibleName("Filter missions by status")
        self._status_filter.addItem(_tr("task_board.all_states", "All states"), "")
        for status in ("running", "pending", "interrupted", "blocked", "failed", "completed"):
            self._status_filter.addItem(
                _tr("task_board.status_" + status, status.capitalize()), status)
        self._status_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self._status_filter)
        self._archived_toggle = QCheckBox(_tr(
            "task_board.include_archived", "Include archived"))
        self._archived_toggle.setObjectName("includeArchivedMissions")
        self._archived_toggle.setAccessibleName("Include archived missions")
        self._archived_toggle.toggled.connect(self.refresh)
        filters.addWidget(self._archived_toggle)
        self._select_filtered_btn = QPushButton(_tr(
            "task_board.select_filtered", "Select filtered"))
        self._select_filtered_btn.setObjectName("selectFilteredMissionsButton")
        self._select_filtered_btn.clicked.connect(self._select_filtered_missions)
        filters.addWidget(self._select_filtered_btn)
        self._clear_selection_btn = QPushButton(_tr(
            "task_board.clear_selection", "Clear selection"))
        self._clear_selection_btn.setObjectName("clearMissionSelectionButton")
        self._clear_selection_btn.clicked.connect(self._clear_mission_selection)
        filters.addWidget(self._clear_selection_btn)
        self._selection_summary = QLabel(_tr(
            "task_board.selection_count", "{count} selected", count=0))
        self._selection_summary.setStyleSheet("color: #7E8798; font-size: 12px;")
        filters.addWidget(self._selection_summary)
        layout.addLayout(filters)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._mission_list = QListWidget()
        self._mission_list.setMinimumWidth(260)
        self._mission_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._mission_list.currentItemChanged.connect(self._on_mission_selected)
        self._mission_list.itemSelectionChanged.connect(self._update_selection_actions)
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
        self._stop_btn = QPushButton(_tr("task_board.stop", "Stop"))
        self._stop_btn.setObjectName("stopMissionButton")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_selected)
        self._archive_btn = QPushButton(_tr("task_board.archive", "Archive"))
        self._archive_btn.setObjectName("archiveMissionButton")
        self._archive_btn.setEnabled(False)
        self._archive_btn.clicked.connect(self._archive_selected)
        self._delete_btn = QPushButton(_tr("task_board.delete", "Delete"))
        self._delete_btn.setObjectName("deleteMissionButton")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_selected)
        self._steer_btn = QPushButton(_tr("task_board.steer", "Steer"))
        self._steer_btn.setObjectName("steerMissionButton")
        self._steer_btn.setEnabled(False)
        self._steer_btn.clicked.connect(self._steer_selected)
        footer.addWidget(self._review_btn)
        footer.addWidget(self._steer_btn)
        footer.addWidget(self._stop_btn)
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
        self._stop_btn.setText(_tr("task_board.stop", "Stop"))
        self._archive_btn.setText(_tr("task_board.archive", "Archive"))
        self._delete_btn.setText(_tr("task_board.delete", "Delete"))
        self._steer_btn.setText(_tr("task_board.steer", "Steer"))
        self._search_filter.setPlaceholderText(_tr(
            "task_board.filter_placeholder", "Filter missions by title or goal"))
        self._archived_toggle.setText(_tr(
            "task_board.include_archived", "Include archived"))
        self._select_filtered_btn.setText(_tr(
            "task_board.select_filtered", "Select filtered"))
        self._clear_selection_btn.setText(_tr(
            "task_board.clear_selection", "Clear selection"))
        self._selection_summary.setText(_tr(
            "task_board.selection_count", "{count} selected",
            count=len(self._selected_mission_ids())))
        self._status_filter.setItemText(
            0, _tr("task_board.all_states", "All states"))
        for index in range(1, self._status_filter.count()):
            status = str(self._status_filter.itemData(index) or "")
            self._status_filter.setItemText(
                index, _tr("task_board.status_" + status, status.capitalize()))
        self._task_tree.setHeaderLabels([
            _tr("task_board.header_task", "Task"),
            _tr("task_board.header_role", "Role"),
            _tr("task_board.header_status", "Status"),
            _tr("task_board.header_attempts", "Attempts")])
        self._review_btn.setText(_tr("task_board.review", "Review candidate"))
        self._update_queue_summary()

    # ------------------------------------------------------------------ project

    def set_project(self, project: dict | None):
        previous_id = (self._project or {}).get("id")
        self._project = dict(project) if project else None
        if previous_id != (self._project or {}).get("id"):
            self._selected_mission_id = None
        self.refresh()

    def _project_root(self) -> Path | None:
        if self._project and self._project.get("root"):
            return Path(self._project["root"])
        return None

    # ------------------------------------------------------------------ refresh

    @Slot()
    def refresh(self):
        previous_selected_id = self._selected_mission_id
        selected_ids = {
            int(item.data(Qt.ItemDataRole.UserRole))
            for item in self._mission_list.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole) is not None
        }
        if self._selected_mission_id is not None:
            selected_ids.add(int(self._selected_mission_id))
        self._mission_list.blockSignals(True)
        self._mission_list.clear()
        project_id = int(self._project["id"]) if self._project else None
        missions = self._services.list_missions(project_id) if project_id else []
        if not self._archived_toggle.isChecked():
            missions = [mission for mission in missions if not mission.get("archived_at")]
        selected_status = str(self._status_filter.currentData() or "")
        if selected_status:
            missions = [mission for mission in missions
                        if mission.get("status") == selected_status]
        query = self._search_filter.text().strip().casefold()
        if query:
            missions = [
                mission for mission in missions
                if query in str(mission.get("title") or "").casefold()
                or query in str(mission.get("goal") or "").casefold()
            ]
        from nl_coding_agent.core.doc_planning import is_document_plan_request
        visible = [
            mission for mission in missions
            if self._history_toggle.isChecked() or not (
                mission.get("status") == "blocked"
                and is_document_plan_request(mission.get("goal") or ""))
        ]
        self._mission_cache = {int(mission["id"]): mission for mission in visible}
        for mission in visible:
            requirement = mission.get("requirement_id")
            suffix = ("  [" + str(requirement) + "]") if requirement else ""
            archived = "  [archived]" if mission.get("archived_at") else ""
            label = (
                f"#{mission['id']}  [{mission['status']}]  "
                f"{mission.get('title', '')[:70]}{suffix}{archived}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, mission["id"])
            self._mission_list.addItem(item)
            if int(mission["id"]) in selected_ids:
                item.setSelected(True)
        self._update_queue_summary()
        if visible and not self._mission_list.selectedItems():
            first = self._mission_list.item(0)
            if first is not None:
                first.setSelected(True)
                self._mission_list.setCurrentItem(first)
        current = self._mission_list.currentItem()
        if current is None and self._mission_list.selectedItems():
            current = self._mission_list.selectedItems()[-1]
            self._mission_list.setCurrentItem(current)
        self._mission_list.blockSignals(False)
        if current is None:
            self._selected_mission_id = None
            self._task_tree.clear()
            self._details.setPlainText(_tr(
                "task_board.no_missions_detail",
                "No missions yet. Create one from the CLI or load a roadmap mission."))
            self._status_label.setText(_tr(
                "task_board.no_missions", "No missions matching these filters"))
            self._progress.setValue(0)
            self._review_btn.setEnabled(False)
            self._document_btn.setVisible(False)
            self._run_btn.setEnabled(False)
            self._steer_btn.setEnabled(False)
        else:
            mission_id = current.data(Qt.ItemDataRole.UserRole)
            self._selected_mission_id = int(mission_id) if mission_id is not None else None
            if self._selected_mission_id is not None:
                self._show_mission(self._selected_mission_id)
                if self._selected_mission_id != previous_selected_id:
                    self.mission_selected.emit(self._selected_mission_id)
        self._select_filtered_btn.setEnabled(project_id is not None and bool(visible))
        self._update_selection_actions()

    def _selected_mission_ids(self) -> list[int]:
        return list(dict.fromkeys(
            int(item.data(Qt.ItemDataRole.UserRole))
            for item in self._mission_list.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole) is not None
        ))

    @Slot()
    def _select_filtered_missions(self) -> None:
        if not self._project:
            return
        self._mission_list.selectAll()
        self._update_selection_actions()

    @Slot()
    def _clear_mission_selection(self) -> None:
        self._mission_list.clearSelection()
        self._mission_list.setCurrentItem(None)
        self._selected_mission_id = None
        self._task_tree.clear()
        self._details.setPlainText(_tr("task_board.select_mission", "Select a mission"))
        self._progress.setValue(0)
        self._status_label.setText(_tr("task_board.select_mission", "Select a mission"))
        self._update_selection_actions()

    @Slot()
    def _update_selection_actions(self) -> None:
        selected_ids = self._selected_mission_ids()
        self._selection_summary.setText(_tr(
            "task_board.selection_count", "{count} selected", count=len(selected_ids)))
        single = len(selected_ids) == 1
        busy = self._bulk_operation is not None
        running = any(
            self._mission_cache.get(mission_id, {}).get("status") == "running"
            for mission_id in selected_ids
        )
        self._stop_btn.setEnabled(bool(selected_ids and running and not busy))
        self._archive_btn.setEnabled(bool(selected_ids and not busy))
        self._delete_btn.setEnabled(bool(selected_ids and not busy))
        self._clear_selection_btn.setEnabled(bool(selected_ids) and not busy)
        self._select_filtered_btn.setEnabled(
            bool(self._project and self._mission_list.count()) and not busy)
        if not single:
            self._run_btn.setEnabled(False)
            self._review_btn.setEnabled(False)
            self._steer_btn.setEnabled(False)
            self._document_btn.setVisible(False)
        else:
            mission_id = selected_ids[0]
            self._selected_mission_id = mission_id
            mission = self._mission_cache.get(mission_id) or {}
            from nl_coding_agent.core.doc_planning import is_document_plan_request
            document_only = is_document_plan_request(mission.get("goal") or "")
            status = mission.get("status")
            self._run_btn.setToolTip(
                _tr("task_board.document_only",
                    "Historical document request: open Document plan; coding execution is unavailable.")
                if document_only else "")
            self._run_btn.setEnabled(
                not busy and not document_only
                and status in ("pending", "interrupted", "failed", "blocked"))
            self._review_btn.setEnabled(not busy and bool(mission.get("staging_dir")))
            self._steer_btn.setEnabled(
                not busy and status in ("pending", "running", "interrupted", "blocked"))
            self._document_btn.setVisible(document_only)

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
            selected = self._mission_list.selectedItems()
            current = selected[-1] if selected else None
        if current is None:
            self._selected_mission_id = None
            self._task_tree.clear()
            self._details.setPlainText("Select a mission")
            self._progress.setValue(0)
            self._update_selection_actions()
            return
        mission_id = current.data(Qt.ItemDataRole.UserRole)
        if mission_id is not None:
            self._selected_mission_id = int(mission_id)
            self.mission_selected.emit(int(mission_id))
            self._show_mission(int(mission_id))
        self._update_selection_actions()

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
        self._document_btn.setVisible(document_only)

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

    def _confirm_bulk_action(self, action: str, missions: list[dict]) -> bool:
        labels = [
            f"#{item['id']} [{item.get('status')}] {str(item.get('title') or '')[:80]}"
            for item in missions[:8]
        ]
        if len(missions) > len(labels):
            labels.append(f"... and {len(missions) - len(labels)} more")
        selected = "\n".join(labels)
        count = len(missions)
        if action == "stop":
            title = _tr("task_board.stop_title", "Stop missions")
            message = (
                _tr("task_board.stop_confirm",
                    "Request a cooperative stop for {count} running mission(s)? "
                    "Each will stop at its next safe checkpoint.", count=count)
            )
        elif action == "archive":
            title = _tr("task_board.archive_title", "Archive missions")
            message = (
                _tr("task_board.archive_confirm",
                    "Archive {count} selected mission(s)? Mission data and evidence are retained.",
                    count=count)
            )
        else:
            title = _tr("task_board.delete_title", "Delete missions")
            message = (
                _tr("task_board.delete_confirm",
                    "Delete {count} selected mission(s) and their NL database records? "
                    "Project files are not deleted. Staged files remain under Storage Manager control.",
                    count=count)
            )
        answer = QMessageBox.question(
            self, title, message + "\n\n" + selected,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _begin_bulk_action(self, action: str) -> None:
        ids = self._selected_mission_ids()
        project_id = int(self._project["id"]) if self._project else None
        if not ids or project_id is None:
            return
        try:
            missions = [self._services.get_mission_details(mission_id) for mission_id in ids]
            if any(mission is None for mission in missions):
                raise ValueError("One or more selected missions no longer exist")
            if any(int(mission.get("project_id") or -1) != project_id for mission in missions):
                raise ValueError("A selected mission belongs to another project")
            running = [mission for mission in missions if mission.get("status") == "running"]
            if action == "stop":
                missions = running
                if not missions:
                    QMessageBox.information(
                        self,
                        _tr("task_board.no_running_title", "No running missions"),
                        _tr("task_board.no_running_detail",
                            "The selection contains no running missions."),
                    )
                    return
            if not self._confirm_bulk_action(action, missions):
                return
            if running:
                for mission in running:
                    response = self._services.cancel_mission(
                        int(mission["id"]), project_id=project_id)
                    if not response.get("ok"):
                        raise RuntimeError(
                            f"Stop request failed for mission #{mission['id']}")
                self._bulk_operation = {
                    "action": action,
                    "mission_ids": ids,
                    "project_id": project_id,
                    "running_ids": [int(item["id"]) for item in running],
                }
                self._bulk_deadline = time.monotonic() + 600
                self._set_bulk_busy(True)
                self._status_label.setText(
                        _tr("task_board.waiting_stop",
                            "Waiting for {count} mission(s) to stop safely…",
                            count=len(running)))
                self._bulk_timer.start()
                self._poll_bulk_operation()
                return
            if action == "stop":
                return
            self._apply_bulk_action(action, ids, project_id)
        except Exception as exc:
            QMessageBox.warning(self, f"{action.title()} failed", str(exc))

    def _set_bulk_busy(self, busy: bool) -> None:
        for widget in (
            self._refresh_btn, self._history_toggle, self._search_filter,
            self._status_filter, self._archived_toggle, self._select_filtered_btn,
            self._clear_selection_btn, self._stop_btn, self._archive_btn,
            self._delete_btn, self._run_btn, self._review_btn, self._steer_btn,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._update_selection_actions()

    @Slot()
    def _poll_bulk_operation(self) -> None:
        operation = self._bulk_operation
        if operation is None:
            self._bulk_timer.stop()
            return
        try:
            current = [
                self._services.get_mission_details(mission_id)
                for mission_id in operation["running_ids"]
            ]
            if any(mission is None for mission in current):
                raise ValueError("A mission disappeared while waiting for its stop")
            still_running = [
                mission for mission in current if mission.get("status") == "running"
            ]
            if still_running and time.monotonic() < self._bulk_deadline:
                self._status_label.setText(
                    _tr("task_board.waiting_checkpoint",
                        "Waiting for {count} mission(s) to reach a safe stop…",
                        count=len(still_running)))
                return
            if still_running:
                self._bulk_operation = None
                self._bulk_timer.stop()
                self._set_bulk_busy(False)
                self.refresh()
                QMessageBox.warning(
                    self, _tr("task_board.stop_pending_title", "Stop still pending"),
                    _tr("task_board.stop_pending_detail",
                        "The cooperative stop was requested, but the mission has not reached "
                        "a safe checkpoint yet. No archive or delete action was performed."),
                )
                return
            action = operation["action"]
            ids = operation["mission_ids"]
            project_id = operation["project_id"]
            self._bulk_operation = None
            self._bulk_timer.stop()
            self._set_bulk_busy(False)
            if action == "stop":
                self._status_label.setText(
                    _tr("task_board.stop_complete",
                        "Stop reached a safe terminal state for {count} mission(s).",
                        count=len(operation["running_ids"])))
                self.refresh()
            else:
                self._apply_bulk_action(action, ids, project_id)
        except Exception as exc:
            self._bulk_operation = None
            self._bulk_timer.stop()
            self._set_bulk_busy(False)
            self.refresh()
            QMessageBox.warning(
                self, _tr("task_board.action_failed", "Mission action failed"), str(exc))

    def _apply_bulk_action(self, action: str, ids: list[int], project_id: int) -> None:
        try:
            if action == "archive":
                changed = self._services.archive_missions(ids, project_id=project_id)
            elif action == "delete":
                changed = self._services.delete_missions(ids, project_id=project_id)
            else:
                raise ValueError("Unknown mission action: " + action)
        except Exception as exc:
            self.refresh()
            QMessageBox.warning(self, f"{action.title()} failed", str(exc))
            return
        self._selected_mission_id = None
        self._status_label.setText(_tr(
            "task_board.archive_complete" if action == "archive"
            else "task_board.delete_complete",
            "Archived {count} mission(s)." if action == "archive"
            else "Deleted {count} mission(s).",
            count=len(changed)))
        self.refresh()

    def _resolve_root(self, details: dict) -> Path | None:
        project_id = details.get("project_id")
        if project_id:
            project = self._services.get_project(project_id)
            if project and project.get("root"):
                return Path(project["root"])
        return self._project_root()

    @Slot()
    def _archive_selected(self) -> None:
        self._begin_bulk_action("archive")

    @Slot()
    def _delete_selected(self) -> None:
        self._begin_bulk_action("delete")

    @Slot()
    def _stop_selected(self) -> None:
        self._begin_bulk_action("stop")

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

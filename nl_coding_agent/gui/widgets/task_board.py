"""Mission and task board backed by AppServices (no direct database access)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QProgressBar, QPushButton, QSplitter, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from nl_coding_agent.app.services import AppServices

_STATUS_ORDER = ["running", "pending", "failed", "blocked", "completed"]


class TaskBoardWidget(QWidget):
    """Displays missions, their task graph, progress, and run/resume controls."""

    mission_selected = Signal(int)
    mission_finished = Signal(dict)

    def __init__(self, services: AppServices, parent=None):
        super().__init__(parent)
        self._services = services
        self._project: dict | None = None
        self._selected_mission_id: int | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Missions & Tasks")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        self._roadmap_btn = QPushButton("Load Roadmap Mission")
        self._roadmap_btn.setToolTip("Create a mission from docs/NEXT_SELF_BUILD_MISSION.md")
        self._roadmap_btn.clicked.connect(self._load_roadmap)
        header.addWidget(self._roadmap_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._mission_list = QListWidget()
        self._mission_list.setMinimumWidth(260)
        self._mission_list.currentItemChanged.connect(self._on_mission_selected)
        splitter.addWidget(self._mission_list)

        right = QSplitter(Qt.Orientation.Vertical)

        self._task_tree = QTreeWidget()
        self._task_tree.setHeaderLabels(["Task", "Role", "Status", "Attempts"])
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

        self._status_label = QLabel("Select a mission")
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        footer.addWidget(self._status_label)
        footer.addStretch()

        self._run_btn = QPushButton("Run / Resume")
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_selected)
        footer.addWidget(self._run_btn)
        layout.addLayout(footer)

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
        visible = missions
        for mission in visible:
            label = f"#{mission['id']}  [{mission['status']}]  {mission.get('title', '')[:70]}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, mission["id"])
            self._mission_list.addItem(item)
            if selected == mission["id"]:
                self._mission_list.setCurrentItem(item)
        if visible and self._mission_list.currentRow() < 0:
            self._mission_list.setCurrentRow(0)
        elif not visible:
            self._selected_mission_id = None
            self._run_btn.setEnabled(False)
            self._task_tree.clear()
            self._details.setPlainText("No missions yet. Create one from the CLI or load a roadmap mission.")
            self._status_label.setText("No missions")
            self._progress.setValue(0)

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
        self._status_label.setText(
            f"Mission #{mission_id}: {details.get('status')}  •  "
            f"{progress.get('completed', 0)}/{progress.get('total', 0)} tasks  •  "
            f"resumes: {details.get('resume_count', 0)}"
        )
        self._run_btn.setEnabled(details.get("status") in ("pending", "interrupted", "failed", "blocked"))

        lines = [
            f"Mission #{mission_id} — {details.get('title', '')}",
            f"Status: {details.get('status')}",
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
    def _run_selected(self):
        if not self._selected_mission_id:
            return
        details = self._services.get_mission_details(self._selected_mission_id)
        if not details:
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

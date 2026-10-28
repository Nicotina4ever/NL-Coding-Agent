"""Projects panel — shows recent projects with open/remove actions."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog, QFrame,
)
from PySide6.QtCore import Signal, Qt


class ProjectsPanel(QWidget):
    """Center panel for the Projects page."""

    project_opened = Signal(dict)   # emits project record
    audit_requested = Signal(int)   # emits project_id

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("Projects")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        self_build_btn = QPushButton("Self-Build (This Agent)")
        self_build_btn.setStyleSheet("color: #46A3C0; border-color: #46A3C0;")
        self_build_btn.clicked.connect(self._on_self_build_open)
        header.addWidget(self_build_btn)

        open_btn = QPushButton("Open Project…")
        open_btn.setObjectName("primaryButton")
        open_btn.clicked.connect(self._on_open_project)
        header.addWidget(open_btn)
        layout.addLayout(header)

        # Recent projects list
        recent_label = QLabel("Recent Projects")
        recent_label.setStyleSheet("font-size: 12px; color: #7E8798; font-weight: 600;")
        layout.addWidget(recent_label)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        # Action buttons
        btns = QHBoxLayout()
        self._audit_btn = QPushButton("Run Audit")
        self._audit_btn.setEnabled(False)
        self._audit_btn.clicked.connect(self._on_audit)
        btns.addWidget(self._audit_btn)

        self._mission_btn = QPushButton("New Mission…")
        self._mission_btn.setEnabled(False)
        self._mission_btn.setObjectName("primaryButton")
        self._mission_btn.clicked.connect(self._on_new_mission)
        btns.addWidget(self._mission_btn)

        btns.addStretch()
        self._remove_btn = QPushButton("Remove from List")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._on_remove)
        btns.addWidget(self._remove_btn)
        layout.addLayout(btns)

        self._list.currentItemChanged.connect(self._on_selection_changed)
        self.refresh()

    def refresh(self):
        self._list.clear()
        projects = self._services.list_recent_projects()
        for p in projects:
            meta = {}
            try:
                meta = json.loads(p.get("metadata") or "{}")
            except Exception:
                pass
            lang = meta.get("primary_language", "?")
            frameworks = ", ".join(meta.get("frameworks", [])) or "-"
            display = f"{p['name']}   [{lang}]   {p['root']}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(
                f"Root: {p['root']}\n"
                f"Language: {lang}\n"
                f"Frameworks: {frameworks}\n"
                f"Last used: {p['last_used']}"
            )
            self._list.addItem(item)

    def _on_open_project(self):
        from nl_coding_agent.gui.dialogs.open_project import OpenProjectDialog
        dlg = OpenProjectDialog(self._services, self)
        if dlg.exec():
            self.refresh()
            # Select the newly opened project
            project = dlg.opened_project
            if project:
                self.project_opened.emit(project)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        project = item.data(Qt.ItemDataRole.UserRole)
        if project:
            self.project_opened.emit(project)

    def _on_selection_changed(self, current, previous):
        has_sel = current is not None
        self._audit_btn.setEnabled(has_sel)
        self._mission_btn.setEnabled(has_sel)
        self._remove_btn.setEnabled(has_sel)

    def _on_self_build_open(self):
        root = Path(__file__).resolve().parents[3]
        project = self._services.open_project(root)
        self.refresh()
        self.project_opened.emit(project)

    def _on_new_mission(self):
        item = self._list.currentItem()
        if not item:
            return
        project = item.data(Qt.ItemDataRole.UserRole)
        goal, ok = QInputDialog.getText(
            self, f"New Mission for {project['name']}",
            "Describe the goal for the autonomous multi-agent team:"
        )
        if ok and goal.strip():
            m_id = self._services.create_mission(
                project_id=project["id"],
                title=goal.strip()[:40],
                goal=goal.strip()
            )
            self._services.run_mission(
                mission_id=m_id,
                project_root=project["root"],
                goal=goal.strip()
            )

    def _on_audit(self):
        item = self._list.currentItem()
        if not item:
            return
        project = item.data(Qt.ItemDataRole.UserRole)
        self.audit_requested.emit(project["id"])

    def _on_remove(self):
        item = self._list.currentItem()
        if not item:
            return
        project = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Remove Project",
            f"Remove '{project['name']}' from the list?\n"
            f"This does NOT delete any files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._services.remove_project(project["id"])
            self.refresh()

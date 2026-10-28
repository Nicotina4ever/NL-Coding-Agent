"""Projects panel — shows recent projects with open/remove actions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog, QFrame,
    QFileDialog, QDialog, QDialogButtonBox, QPlainTextEdit,
)
from PySide6.QtCore import Signal, Qt

from nl_coding_agent.gui.components import empty_state
from nl_coding_agent.gui.i18n import tr_for


class ProjectsPanel(QWidget):
    """Center panel for the Projects page."""

    project_opened = Signal(dict)   # emits project record
    audit_requested = Signal(int)   # emits project_id

    def __init__(self, services, parent=None, *, translator=None):
        super().__init__(parent)
        self._services = services
        self._i18n = translator
        self._opened_project = None
        self._selected_project = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        self._title = QLabel(tr_for(self._i18n, "projects.title", "Projects"))
        self._title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(self._title)
        header.addStretch()
        self._open_btn = QPushButton(tr_for(
            self._i18n, "projects.open", "Open Project…"))
        open_btn = self._open_btn
        open_btn.setObjectName("primaryButton")
        open_btn.clicked.connect(self._on_open_project)
        header.addWidget(open_btn)
        layout.addLayout(header)
        identity = QLabel("Opened: —    |    Selected: —")
        identity.setObjectName("nlProjectIdentity")
        identity.setAccessibleName("Opened project and selected project identity")
        self._identity_label = identity
        layout.addWidget(identity)
        self._self_build_btn = QPushButton("Advanced self-build…")
        self._self_build_btn.setObjectName("subtleLinkButton")
        self._self_build_btn.setFlat(True)
        self._self_build_btn.setAccessibleName(
            "Unobtrusive advanced self-build link (controls live in Settings Advanced)")
        self._self_build_btn.setToolTip(
            "Self-build is intentionally unobtrusive. Configure it in "
            "Settings > Advanced > Autonomous Development.")
        self._self_build_btn.clicked.connect(self._on_self_build_open)
        dev_row = QHBoxLayout()
        dev_row.addStretch()
        self._ingest_btn = QPushButton(tr_for(
            self._i18n, "projects.ingest_docs", "Ingest documentation…"))
        self._ingest_btn.setObjectName("subtleLinkButton")
        self._ingest_btn.setFlat(True)
        self._ingest_btn.setAccessibleName("Ingest project documentation (read-only)")
        self._ingest_btn.setToolTip(tr_for(
            self._i18n, "projects.ingest_docs_tooltip",
            "Read-only bounded documentation discovery. Documents are UNTRUSTED "
            "and are never executed; no model/network is started."))
        self._ingest_btn.clicked.connect(self._on_ingest_documents)
        self._ingest_btn.setEnabled(
            callable(getattr(services, "document_ingest", None)))
        if not self._ingest_btn.isEnabled():
            self._ingest_btn.setToolTip("Document ingestion is not configured.")
        dev_row.addWidget(self._ingest_btn)
        dev_row.addWidget(self._self_build_btn)
        layout.addLayout(dev_row)

        # Recent projects list
        self._recent_label = QLabel(tr_for(
            self._i18n, "projects.recent", "Recent Projects"))
        self._recent_label.setStyleSheet(
            "font-size: 12px; color: #7E8798; font-weight: 600;")
        layout.addWidget(self._recent_label)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list, 1)
        self._empty_card = QFrame()
        self._empty_card.setObjectName("nlSummaryCard")
        self._empty_card.setMaximumHeight(220)
        self._empty_card.setAccessibleName("No projects yet guidance")
        empty_layout = QVBoxLayout(self._empty_card)
        empty_layout.setContentsMargins(12, 12, 12, 12)
        empty_layout.addWidget(empty_state(
            "No projects yet. Open a project to start the Studio, or pick one "
            "from Recent Projects once available."))
        empty_open = QPushButton(tr_for(self._i18n, "projects.open",
                                        "Open Project…"))
        empty_open.setObjectName("primaryButton")
        empty_open.setAccessibleName("Open project from empty state")
        empty_open.clicked.connect(self._on_open_project)
        empty_layout.addWidget(empty_open, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._empty_card)
        layout.addStretch(1)

        # Action buttons
        btns = QHBoxLayout()
        self._audit_btn = QPushButton(tr_for(
            self._i18n, "projects.audit", "Run Audit"))
        self._audit_btn.setEnabled(False)
        self._audit_btn.clicked.connect(self._on_audit)
        btns.addWidget(self._audit_btn)

        self._mission_btn = QPushButton(tr_for(
            self._i18n, "projects.new_mission", "New Mission…"))
        self._mission_btn.setEnabled(False)
        self._mission_btn.setObjectName("primaryButton")
        self._mission_btn.clicked.connect(self._on_new_mission)
        btns.addWidget(self._mission_btn)

        btns.addStretch()
        self._remove_btn = QPushButton(tr_for(
            self._i18n, "projects.remove", "Remove from List"))
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._on_remove)
        btns.addWidget(self._remove_btn)
        layout.addLayout(btns)

        self._list.currentItemChanged.connect(self._on_selection_changed)
        self.refresh()

    def retranslate(self) -> None:
        self._title.setText(tr_for(self._i18n, "projects.title", "Projects"))
        self._open_btn.setText(tr_for(
            self._i18n, "projects.open", "Open Project…"))
        self._recent_label.setText(tr_for(
            self._i18n, "projects.recent", "Recent Projects"))
        self._audit_btn.setText(tr_for(self._i18n, "projects.audit", "Run Audit"))
        self._mission_btn.setText(tr_for(
            self._i18n, "projects.new_mission", "New Mission…"))
        self._remove_btn.setText(tr_for(
            self._i18n, "projects.remove", "Remove from List"))
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
                tr_for(self._i18n, "projects.tooltip_root", "Root: {root}",
                       root=p["root"]) + "\n"
                + tr_for(self._i18n, "projects.tooltip_language",
                          "Language: {language}", language=lang) + "\n"
                + tr_for(self._i18n, "projects.tooltip_frameworks",
                          "Frameworks: {frameworks}", frameworks=frameworks) + "\n"
                + tr_for(self._i18n, "projects.tooltip_last_used",
                          "Last used: {last_used}", last_used=p["last_used"])
            )
            self._list.addItem(item)
        has_projects = self._list.count() > 0
        self._list.setVisible(has_projects)
        self._empty_card.setVisible(not has_projects)
        self._recent_label.setVisible(has_projects)

    def _on_open_project(self):
        from nl_coding_agent.gui.dialogs.open_project import OpenProjectDialog
        dlg = OpenProjectDialog(self._services, self,
                                translator=self._i18n)
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
        selected = (current.data(Qt.ItemDataRole.UserRole)
                    if current is not None else None)
        self._selected_project = selected
        self._update_identity_label()

    def set_opened_project(self, project) -> None:
        """Make the opened project unambiguously distinct from list selection."""
        self._opened_project = dict(project) if project else None
        self._update_identity_label()

    def _update_identity_label(self) -> None:
        opened = (self._opened_project or {}).get("name") or "—"
        selected = (self._selected_project or {}).get("name") or "—"
        label = "Opened: " + str(opened) + "    |    Selected: " + str(selected)
        if self._selected_project and self._opened_project:
            if self._selected_project.get("id") != self._opened_project.get("id"):
                label += "    (selection differs from opened project)"
        self._identity_label.setText(label)
        self._identity_label.setToolTip(
            "Opened = the project currently loaded in the Studio; "
            "Selected = highlighted list item.")


    def _on_ingest_documents(self) -> None:
        if not callable(getattr(self._services, "document_ingest", None)):
            return
        folder = QFileDialog.getExistingDirectory(
            self, tr_for(self._i18n, "projects.ingest_choose",
                         "Choose documentation folder"))
        if not folder:
            return
        self._run_document_ingest(folder)

    def _run_document_ingest(self, folder) -> dict:
        try:
            result = self._services.document_ingest(
                project_root=folder, consent=True)
        except Exception as exc:  # noqa: BLE001 - displayed, failed closed
            result = {"ok": False, "outcome": "error",
                      "error": {"message": str(exc)}, "documents": []}
        if isinstance(result, Mapping) and not result.get("ok"):
            error = result.get("error")
            message = error.get("message") if isinstance(error, Mapping) else None
            QMessageBox.warning(
                self, tr_for(self._i18n, "projects.ingest_unavailable",
                             "Document ingestion unavailable"),
                str(message or "Document ingestion could not run."))
        else:
            self._show_ingest_summary(result)
        return dict(result) if isinstance(result, Mapping) else {}

    def _ingest_summary_text(self, result: dict) -> str:
        counts = result.get("counts") or {}
        lines = [
            "Document ingestion: " + str(result.get("outcome") or "unknown"),
            "Documents: " + str(counts.get("documents", len(result.get("documents") or []))),
            "Skipped: " + str(counts.get("skipped", 0)),
            "Duplicates: " + str(counts.get("duplicates", 0)),
            "Source kinds: " + json.dumps(result.get("source_kinds") or {},
                                          sort_keys=True),
            "Bounded: " + str(bool(result.get("bounded")))
            + "   Complete: " + str(bool(result.get("complete"))),
            "",
            "Authority candidates (flags, not truth claims):",
        ]
        for item in result.get("authority_candidates") or []:
            lines.append("  " + str(item.get("path")) + " — "
                         + ", ".join(item.get("authority_candidates") or []))
        if not result.get("authority_candidates"):
            lines.append("  none")
        lines.extend(["", "Limitations:"])
        for limitation in result.get("limitations") or []:
            lines.append("  " + str(limitation))
        if not result.get("limitations"):
            lines.append("  none reported")
        lines.extend([
            "", "Documents (bounded provenance):",
        ])
        for document in (result.get("documents") or [])[:50]:
            lines.append("  " + str(document.get("source_kind")) + "  "
                         + str(document.get("path") or document.get("url"))
                         + "  sha256=" + str(document.get("sha256"))[:12]
                         + "  size=" + str(document.get("size")))
        lines.extend(["", "UNTRUSTED data; imported content was not executed. "
                          "No mission or model was started."])
        return "\n".join(lines)

    def _show_ingest_summary(self, result: dict) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr_for(self._i18n, "projects.ingest_title",
                                     "Document ingestion summary"))
        dialog.setAccessibleName("Read-only document ingestion summary")
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)
        summary = QPlainTextEdit()
        summary.setReadOnly(True)
        summary.setAccessibleName("Document ingestion counts and provenance")
        summary.setPlainText(self._ingest_summary_text(result))
        layout.addWidget(summary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.show()
        return dialog

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
            self,
            tr_for(self._i18n, "projects.new_mission_title",
                   "New Mission for {name}", name=project["name"]),
            tr_for(self._i18n, "projects.new_mission_prompt",
                   "Describe the goal for the autonomous multi-agent team:")
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
            self,
            tr_for(self._i18n, "projects.remove_title", "Remove Project"),
            tr_for(self._i18n, "projects.remove_confirm",
                   "Remove '{name}' from the list?\nThis does NOT delete any files.",
                   name=project["name"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._services.remove_project(project["id"])
            self.refresh()

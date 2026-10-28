"""Open Project dialog."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt

from nl_coding_agent.gui.i18n import tr_for


class OpenProjectDialog(QDialog):
    """Dialog to select a folder and open it as a project."""

    def __init__(self, services, parent=None, *, translator=None):
        super().__init__(parent)
        self._i18n = translator
        self.setWindowTitle(tr_for(
            self._i18n, "dialog.open_project_title", "Open Project"))
        self.setMinimumWidth(520)
        self._services = services
        self.opened_project: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self._prompt = QLabel(tr_for(
            self._i18n, "dialog.select_folder",
            "Select the folder containing your project:"))
        layout.addWidget(self._prompt)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText(tr_for(
            self._i18n, "dialog.path_placeholder", "Path to project folder…"))
        path_row.addWidget(self._path_edit)
        self._browse_btn = QPushButton(tr_for(
            self._i18n, "dialog.browse", "Browse…"))
        browse_btn = self._browse_btn
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._status_label)

        btns = QHBoxLayout()
        btns.addStretch()
        self._cancel_btn = QPushButton(tr_for(
            self._i18n, "dialog.cancel", "Cancel"))
        cancel_btn = self._cancel_btn
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        self._open_btn = QPushButton(tr_for(
            self._i18n, "dialog.open", "Open Project"))
        self._open_btn.setObjectName("primaryButton")
        self._open_btn.clicked.connect(self._open)
        btns.addWidget(self._open_btn)
        layout.addLayout(btns)

    def retranslate(self) -> None:
        self.setWindowTitle(tr_for(
            self._i18n, "dialog.open_project_title", "Open Project"))
        self._prompt.setText(tr_for(
            self._i18n, "dialog.select_folder",
            "Select the folder containing your project:"))
        self._path_edit.setPlaceholderText(tr_for(
            self._i18n, "dialog.path_placeholder", "Path to project folder…"))
        self._browse_btn.setText(tr_for(self._i18n, "dialog.browse", "Browse…"))
        self._cancel_btn.setText(tr_for(self._i18n, "dialog.cancel", "Cancel"))
        self._open_btn.setText(tr_for(
            self._i18n, "dialog.open", "Open Project"))

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr_for(self._i18n, "dialog.select_folder_title",
                         "Select Project Folder"),
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self._path_edit.setText(folder)

    def _open(self):
        path_str = self._path_edit.text().strip()
        if not path_str:
            self._status_label.setText(tr_for(
                self._i18n, "dialog.path_required",
                "Please enter a folder path."))
            return
        path = Path(path_str)
        if not path.exists() or not path.is_dir():
            self._status_label.setText(tr_for(
                self._i18n, "dialog.folder_missing",
                "Folder does not exist."))
            return
        self._status_label.setText(tr_for(
            self._i18n, "dialog.scanning", "Scanning project…"))
        self._open_btn.setEnabled(False)
        try:
            project = self._services.open_project(path)
            self.opened_project = project
            self.accept()
        except Exception as e:
            self._status_label.setText(tr_for(
                self._i18n, "dialog.error", "Error: {error}", error=e))
            self._open_btn.setEnabled(True)

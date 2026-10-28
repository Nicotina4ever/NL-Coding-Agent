"""Open Project dialog."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt


class OpenProjectDialog(QDialog):
    """Dialog to select a folder and open it as a project."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Project")
        self.setMinimumWidth(520)
        self._services = services
        self.opened_project: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("Select the folder containing your project:"))

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Path to project folder…")
        path_row.addWidget(self._path_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._status_label)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        self._open_btn = QPushButton("Open Project")
        self._open_btn.setObjectName("primaryButton")
        self._open_btn.clicked.connect(self._open)
        btns.addWidget(self._open_btn)
        layout.addLayout(btns)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Project Folder",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self._path_edit.setText(folder)

    def _open(self):
        path_str = self._path_edit.text().strip()
        if not path_str:
            self._status_label.setText("Please enter a folder path.")
            return
        path = Path(path_str)
        if not path.exists() or not path.is_dir():
            self._status_label.setText("Folder does not exist.")
            return
        self._status_label.setText("Scanning project…")
        self._open_btn.setEnabled(False)
        try:
            project = self._services.open_project(path)
            self.opened_project = project
            self.accept()
        except Exception as e:
            self._status_label.setText(f"Error: {e}")
            self._open_btn.setEnabled(True)

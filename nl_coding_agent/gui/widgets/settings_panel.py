"""Settings panel - read-only runtime paths and configuration state."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class SettingsPanel(QWidget):
    """Read-only view of non-secret runtime settings."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._project_root: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Runtime paths and configuration state. Read-only; no secrets are displayed."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._project_value = self._path_label()
        self._database_value = self._path_label()
        self._ollama_value = self._path_label()
        self._models_value = self._path_label()
        self._cloud_value = QLabel()
        self._cloud_value.setWordWrap(True)

        form.addRow("Project root", self._project_value)
        form.addRow("SQLite database", self._database_value)
        form.addRow("Ollama base URL", self._ollama_value)
        form.addRow("Model config", self._models_value)
        form.addRow("Cloud escalation", self._cloud_value)
        layout.addLayout(form)

        note = QLabel(
            "Cloud escalation remains disabled unless explicitly enabled for a project. "
            "This panel does not change any setting."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #AB83C6; font-size: 12px; padding: 8px; "
            "border: 1px solid #343947; border-radius: 6px;"
        )
        layout.addWidget(note)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

        self.refresh()

    @staticmethod
    def _path_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def set_project(self, project: dict | None):
        self._project_root = project.get("root") if project else None
        self.refresh()

    def refresh(self):
        settings = self._services.get_runtime_settings(self._project_root)
        root = settings.get("project_root")
        self._project_value.setText(root or "No project open")
        self._database_value.setText(str(settings.get("database_path") or ""))
        self._ollama_value.setText(str(settings.get("ollama_base_url") or ""))
        self._models_value.setText(str(settings.get("model_config_path") or ""))
        if settings.get("cloud_escalation_enabled"):
            self._cloud_value.setText("Enabled")
            self._cloud_value.setStyleSheet("color: #E26472;")
        else:
            self._cloud_value.setText("Disabled - opt-in per project")
            self._cloud_value.setStyleSheet("color: #55C58A;")

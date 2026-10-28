"""Inspector panel — shows project/mission/agent/verification details."""
from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame,
    QTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt


class InspectorPanel(QWidget):
    """Right inspector panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inspectorPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Inspector")
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #7E8798;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #343947;")
        layout.addWidget(sep)

        self._content = QTextEdit()
        self._content.setReadOnly(True)
        self._content.setObjectName("logOutput")  # monospace, no glow
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._content)

    def show_project(self, project: dict, facts: dict | None = None):
        lines = [f"<b>{project['name']}</b>", f"<span style='color:#7E8798;'>{project['root']}</span>", ""]
        if facts:
            lines.append("<b>Facts</b>")
            for k, v in facts.items():
                try:
                    parsed = json.loads(v)
                    v = json.dumps(parsed, indent=2)
                except Exception:
                    pass
                lines.append(f"<span style='color:#AB83C6;'>{k}:</span> {v}")
        else:
            meta = {}
            try:
                meta = json.loads(project.get("metadata") or "{}")
            except Exception:
                pass
            for k, v in meta.items():
                lines.append(f"<span style='color:#AB83C6;'>{k}:</span> {v}")
        lines.append("")
        lines.append(f"<span style='color:#7E8798;'>Last used: {project.get('last_used', '?')}</span>")
        self._content.setHtml("<br>".join(lines))

    def show_message(self, msg: str):
        self._content.setPlainText(msg)

    def clear(self):
        self._content.clear()

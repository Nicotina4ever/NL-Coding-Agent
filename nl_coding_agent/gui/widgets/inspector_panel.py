"""Inspector panel - shows project/mission/agent/verification details."""
from __future__ import annotations

import html
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame,
    QTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt

from nl_coding_agent.gui.i18n import tr_for


class InspectorPanel(QWidget):
    """Right inspector panel."""

    def __init__(self, parent=None, *, translator=None):
        super().__init__(parent)
        self._i18n = translator
        self._last_render = None
        self.setObjectName("inspectorPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._title = QLabel(tr_for(self._i18n, "inspector.title", "Inspector"))
        self._title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #7E8798;")
        layout.addWidget(self._title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #343947;")
        layout.addWidget(sep)

        self._content = QTextEdit()
        self._content.setReadOnly(True)
        self._content.setObjectName("logOutput")  # monospace, no glow
        self._content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._content)

    def retranslate(self) -> None:
        self._title.setText(tr_for(
            self._i18n, "inspector.title", "Inspector"))
        last = self._last_render
        if last:
            method = getattr(self, "show_" + last[0], None)
            if method is not None:
                method(*last[1:])

    def show_project(self, project: dict, facts: dict | None = None):
        self._last_render = ("project", project, facts)
        lines = [f"<b>{project['name']}</b>",
                 f"<span style='color:#7E8798;'>{project['root']}</span>", ""]
        if facts:
            lines.append("<b>" + tr_for(
                self._i18n, "inspector.facts", "Facts") + "</b>")
            for key, value in facts.items():
                try:
                    parsed = json.loads(value)
                    value = json.dumps(parsed, indent=2)
                except Exception:
                    pass
                lines.append(
                    f"<span style='color:#AB83C6;'>{key}:</span> {value}")
        else:
            meta = {}
            try:
                meta = json.loads(project.get("metadata") or "{}")
            except Exception:
                pass
            for key, value in meta.items():
                lines.append(
                    f"<span style='color:#AB83C6;'>{key}:</span> {value}")
        lines.append("")
        lines.append("<span style='color:#7E8798;'>"
                     + tr_for(self._i18n, "inspector.last_used",
                              "Last used: {value}",
                              value=project.get("last_used", "?"))
                     + "</span>")
        self._content.setHtml("<br>".join(lines))

    def show_file(self, rel_path: str, content: str | None = None):
        self._last_render = ("file", rel_path, content)
        lines = [
            "<b>" + tr_for(self._i18n, "inspector.file", "File") + "</b>",
            f"<span style='color:#7E8798;'>{rel_path}</span>",
        ]
        if content is not None:
            preview = content[:8000]
            suffix = "\n… truncated …" if len(content) > len(preview) else ""
            lines.extend([
                "",
                f"<pre style='white-space:pre-wrap;'>{html.escape(preview)}"
                f"{suffix}</pre>",
            ])
        self._content.setHtml("<br>".join(lines))

    def show_mission(self, mission: dict):
        self._last_render = ("mission", mission)
        lines = [
            "<b>" + tr_for(self._i18n, "inspector.mission",
                            "Mission #{id}", id=mission.get("id")) + "</b>",
            f"<span style='color:#7E8798;'>{mission.get('title', '')}</span>",
            "",
            "<span style='color:#AB83C6;'>"
            + tr_for(self._i18n, "inspector.status", "Status:")
            + "</span> " + str(mission.get("status", "?")),
            "<span style='color:#AB83C6;'>"
            + tr_for(self._i18n, "inspector.verdict", "Verdict:")
            + "</span> " + str(mission.get("review_verdict") or "—"),
            "<span style='color:#AB83C6;'>"
            + tr_for(self._i18n, "inspector.diff", "Diff:")
            + "</span> " + str(mission.get("diff_stat") or "—"),
            "<span style='color:#AB83C6;'>"
            + tr_for(self._i18n, "inspector.resumes", "Resumes:")
            + "</span> " + str(mission.get("resume_count", 0)),
        ]
        if mission.get("result_summary"):
            lines.extend(["", "<b>" + tr_for(
                self._i18n, "inspector.result", "Result") + "</b>",
                str(mission["result_summary"])])
        if mission.get("changed_paths"):
            lines.extend(["", "<b>" + tr_for(
                self._i18n, "inspector.changed_paths", "Changed paths")
                + "</b>", str(mission["changed_paths"])])
        self._content.setHtml("<br>".join(lines))

    def show_message(self, msg: str):
        self._content.setPlainText(msg)

    def clear(self):
        self._content.clear()

"""Inspector panel - structured summary cards plus expandable diagnostics.

U2 replaces the raw QTextEdit wall with scannable project/mission/agent/
verification/activity cards and a tree of expandable raw/evidence/error details.
No information is lost: full raw values remain in the diagnostics tree.
"""
from __future__ import annotations

from nl_coding_agent.gui.i18n import ui_text

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QScrollArea, QSizePolicy, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from nl_coding_agent.gui.components import (empty_state, section_header,
                                            status_badge, summary_card)
from nl_coding_agent.gui.i18n import tr_for


class InspectorPanel(QWidget):
    """Right inspector: summary cards + expandable diagnostics."""

    def __init__(self, parent=None, *, translator=None):
        super().__init__(parent)
        self._i18n = translator
        self._last_render = None
        self.setObjectName("inspectorPanel")
        self.setAccessibleName("Inspector: summaries and expandable diagnostics")
        self.setMinimumWidth(268)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(section_header(
            tr_for(self._i18n, "inspector.title", ui_text("Inspector")),
            ui_text("Summaries first; raw evidence is available below.")))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAccessibleName("Inspector summary and diagnostics scroll")
        self._scroll = scroll
        body = QWidget()
        body.setMinimumWidth(0)
        body.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Preferred)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)
        body_layout.setSizeConstraint(
            __import__("PySide6.QtWidgets", fromlist=["QLayout"]).QLayout
            .SizeConstraint.SetNoConstraint)
        self._cards: dict[str, QFrame] = {}
        for key, title in (("project", ui_text("Project")), ("mission", ui_text("Mission")),
                           ("agent", ui_text("Agent")), ("verification", ui_text("Verification")),
                           ("activity", ui_text("Activity"))):
            card = summary_card(title, "—", ui_text("No data yet"), accessible_name=title)
            card.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Minimum)
            self._cards[key] = card
            body_layout.addWidget(card)
        self._status_badge = status_badge(ui_text("IDLE"), "idle")
        body_layout.addWidget(self._status_badge)
        self._diagnostics_title = QLabel(ui_text("DIAGNOSTICS (expand for raw/evidence/errors)"))
        self._diagnostics_title.setObjectName("nlCardTitle")
        self._diagnostics_title.setAccessibleName("Expandable inspector diagnostics")
        self._diagnostics = QTreeWidget()
        self._diagnostics.setHeaderLabels([ui_text("Section"), ui_text("Detail")])
        self._diagnostics.setAccessibleName("Expandable raw diagnostics tree")
        self._diagnostics.setMinimumHeight(220)
        self._diagnostics.setMinimumWidth(0)
        self._diagnostics.setWordWrap(True)
        self._diagnostics.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._diagnostics.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._diagnostics.header().setStretchLastSection(True)
        self._diagnostics.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive)
        self._diagnostics.setColumnWidth(0, 92)
        self._diagnostics.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Expanding)
        self._diagnostics.setEditTriggers(
            QTreeWidget.EditTrigger.NoEditTriggers)
        diagnostics_box = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_box)
        diagnostics_layout.setContentsMargins(0, 0, 0, 0)
        diagnostics_layout.setSpacing(4)
        diagnostics_layout.addWidget(self._diagnostics_title)
        diagnostics_layout.addWidget(self._diagnostics, 1)
        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        scroll.setWidget(body)
        split.addWidget(scroll)
        split.addWidget(diagnostics_box)
        split.setSizes([430, 260])
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        self._split = split
        layout.addWidget(split, 1)

    # ---------------------------------------------------------------- helpers
    def _set_card(self, key: str, value: str, detail: str = "") -> None:
        card = self._cards[key]
        labels = [child for child in card.findChildren(QLabel)]
        if len(labels) >= 2:
            labels[1].setText(str(value))
        if len(labels) >= 3:
            labels[2].setText(str(detail))

    def _add_diag(self, section: str, lines) -> None:
        item = QTreeWidgetItem([section, ""])
        item.setFirstColumnSpanned(False)
        for line in lines:
            child = QTreeWidgetItem(["", str(line)[:4000]])
            item.addChild(child)
        self._diagnostics.addTopLevelItem(item)
        item.setExpanded(section in (ui_text("Project"), ui_text("Mission")))

    def _reset(self) -> None:
        self._diagnostics.clear()
        for key in self._cards:
            self._set_card(key, "—", ui_text("No data yet"))
        self._status_badge.setText(ui_text("IDLE"))
        self._status_badge.setProperty("tone", "idle")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

    def _set_activity(self, state: str, detail: str = "") -> None:
        tone = {"running": "ok", "blocked": "error", "paused": "warn"}.get(
            state.lower(), "idle")
        self._status_badge.setText(str(state).upper())
        self._status_badge.setProperty("tone", tone)
        self._status_badge.setToolTip(detail)
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._set_card("activity", str(state).title(), detail or ui_text("No active mission"))

    def retranslate(self) -> None:
        last = self._last_render
        if last:
            method = getattr(self, "show_" + last[0], None)
            if method is not None:
                method(*last[1:])

    # ------------------------------------------------------------------ APIs
    def show_project(self, project: dict, facts: dict | None = None):
        self._last_render = ("project", project, facts)
        self._reset()
        meta = {}
        try:
            meta = json.loads(project.get("metadata") or "{}")
        except Exception:  # noqa: BLE001
            meta = {}
        self._set_card("project", project.get("name", "?"),
                       "Selected/opened project: " + str(project.get("root", "")))
        self._set_card("mission", "No mission selected",
                       "Open a mission from Tasks to inspect progress")
        self._set_card("agent", "No agent activity", "Read-only agent/worker summaries")
        self._set_card("verification", "Not loaded", "Evidence appears after a run")
        self._set_activity("idle", ui_text("No active mission"))
        lines = ["Name: " + str(project.get("name")),
                 "Root: " + str(project.get("root")),
                 "Opened: " + str(project.get("opened_at") or "?"),
                 "Last used: " + str(project.get("last_used") or "?")]
        if facts:
            lines.append("Facts:")
            for key, value in facts.items():
                lines.append("  " + str(key) + ": " + str(value))
        elif meta:
            for key, value in meta.items():
                lines.append("  " + str(key) + ": " + str(value))
        self._add_diag(ui_text("Project"), lines)

    def show_file(self, rel_path: str, content: str | None = None):
        self._last_render = ("file", rel_path, content)
        self._set_card("project", rel_path, "Selected file preview")
        self._add_diag("File", ["Path: " + str(rel_path)] +
                       ([str(content)[:8000]] if content is not None else []))

    def show_mission(self, mission: dict):
        self._last_render = ("mission", mission)
        self._set_card("mission",
                       "#" + str(mission.get("id")) + " " + str(mission.get("title") or ""),
                       "Status: " + str(mission.get("status") or "?"))
        self._set_card("agent", str(mission.get("agent_role") or "No agent summary"),
                       "Read-only mission/agent status")
        self._set_card("verification",
                       str(mission.get("review_verdict") or "Not verified"),
                       "Result: " + str(mission.get("result_summary") or "—"))
        state = str(mission.get("status") or "idle").lower()
        if state in ("running", "active"):
            self._set_activity("running", "Current mission: " + str(mission.get("title") or ""))
        elif state in ("blocked", "failed", "interrupted"):
            self._set_activity("blocked", "Current mission: " + str(mission.get("title") or ""))
        elif state in ("paused",):
            self._set_activity("paused", "Current mission: " + str(mission.get("title") or ""))
        else:
            self._set_activity("idle", "Last mission: " + str(mission.get("title") or ""))
        lines = ["ID: " + str(mission.get("id")),
                 "Title: " + str(mission.get("title")),
                 "Status: " + str(mission.get("status")),
                 "Review verdict: " + str(mission.get("review_verdict")),
                 "Diff: " + str(mission.get("diff_stat")),
                 "Resumes: " + str(mission.get("resume_count", 0))]
        if mission.get("result_summary"):
            lines.append("Result: " + str(mission["result_summary"]))
        if mission.get("changed_paths"):
            lines.append("Changed paths: " + str(mission["changed_paths"]))
        self._add_diag(ui_text("Mission"), lines)

    def show_message(self, msg: str):
        self._set_card("activity", "Message", str(msg)[:300])
        self._status_badge.setText(ui_text("MESSAGE"))
        self._status_badge.setProperty("tone", "error")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._add_diag("Error/Message", [str(msg)])

    def clear(self):
        self._last_render = None
        self._reset()

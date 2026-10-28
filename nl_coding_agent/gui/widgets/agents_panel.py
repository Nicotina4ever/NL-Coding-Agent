"""Agents panel - configured roles and local model availability."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


class AgentFetchThread(QThread):
    data_ready = Signal(list, list, bool)

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services

    def run(self):
        roles = []
        try:
            roles = self._services.get_agent_roles()
            reachable = self._services.check_ollama()
            models = self._services.list_models() if reachable else []
            if not self.isInterruptionRequested():
                self.data_ready.emit(roles, models, reachable)
        except Exception:
            if not self.isInterruptionRequested():
                self.data_ready.emit(roles, [], False)


class AgentsPanel(QWidget):
    """Read-only view of agent roles, models, and resource policy."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._thread: AgentFetchThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QVBoxLayout()
        title = QLabel("Agents")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        subtitle = QLabel(
            "Configured roles and local Ollama model availability. "
            "This panel never starts models or changes configuration."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #7E8798; font-size: 12px;")
        header.addWidget(subtitle)
        layout.addLayout(header)

        self._status_label = QLabel("Availability not checked yet.")
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._status_label)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Role", "Model", "Availability"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        policy = QLabel(
            "Resource policy: local model stages run sequentially. "
            "Cloud escalation is opt-in and disabled by default."
        )
        policy.setWordWrap(True)
        policy.setStyleSheet(
            "color: #AB83C6; font-size: 12px; padding: 8px; "
            "border: 1px solid #343947; border-radius: 6px;"
        )
        layout.addWidget(policy)

        refresh_btn = QPushButton("Refresh availability")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._render(self._services.get_agent_roles(), [], None)

    def refresh(self):
        if self._thread is not None and self._thread.isRunning():
            return
        self._status_label.setText("Checking Ollama model availability...")
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        self._thread = AgentFetchThread(self._services)
        self._thread.data_ready.connect(self._on_data_ready)
        self._thread.start()

    def shutdown(self):
        thread = self._thread
        if thread is not None:
            thread.requestInterruption()
            if not thread.wait(30000):
                thread.terminate()
                thread.wait(1000)
            self._thread = None

    def _on_data_ready(self, roles: list, models: list, reachable: bool):
        self._render(roles or self._services.get_agent_roles(), models, reachable)
        if reachable:
            self._status_label.setText(
                f"Ollama reachable - {len(models)} model(s) available."
            )
            self._status_label.setStyleSheet("color: #55C58A; font-size: 12px;")
        else:
            self._status_label.setText(
                "Ollama unreachable - model availability is unknown."
            )
            self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")

    def _render(self, roles: list, models: list, reachable: bool | None):
        available = {m.name: m for m in models}
        self._table.setRowCount(len(roles))
        for row, role in enumerate(roles):
            name = str(role.get("role") or "")
            model = str(role.get("model") or "")
            self._table.setItem(row, 0, QTableWidgetItem(name.capitalize()))
            self._table.setItem(row, 1, QTableWidgetItem(model or "not configured"))

            status, color = self._availability(role, available, reachable)
            item = QTableWidgetItem(status)
            item.setForeground(color)
            if role.get("note"):
                item.setToolTip(str(role["note"]))
            self._table.setItem(row, 2, item)

    def _availability(self, role: dict, available: dict, reachable: bool | None):
        if role.get("kind") == "deterministic":
            return "Deterministic", Qt.GlobalColor.darkCyan
        model = str(role.get("model") or "")
        if not model:
            return "Not configured", Qt.GlobalColor.red
        if reachable is None:
            return "Checking...", Qt.GlobalColor.gray
        if not reachable:
            return "Unknown (offline)", Qt.GlobalColor.darkYellow
        key = model[len("ollama/"):] if model.startswith("ollama/") else model
        installed = available.get(key)
        if installed is None:
            return "Not installed", Qt.GlobalColor.red
        if getattr(installed, "loaded", False):
            return "Running", Qt.GlobalColor.green
        return "Available", Qt.GlobalColor.darkGreen

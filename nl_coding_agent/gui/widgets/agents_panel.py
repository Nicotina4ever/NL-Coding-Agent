"""Agents panel - configured roles and local model availability."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


from nl_coding_agent.gui import i18n as _i18n


def _tr(key, default=None, **values):
    active = getattr(_i18n, "_INSTANCE", None)
    if active is None or getattr(active, "_services", None) is None:
        return _i18n.format_message(default if default is not None else key, **values)
    try:
        return active.tr(key, default, **values)
    except Exception:
        return default if default is not None else key


def _register_retranslate(widget):
    active = getattr(_i18n, "_INSTANCE", None)
    register = getattr(active, "register_retranslate", None)
    if callable(register):
        try:
            register(lambda *args: widget.retranslate())
        except Exception:
            pass


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
        self._title = QLabel(_tr("agents.title", "Agents"))
        title = self._title
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        self._subtitle = QLabel(_tr(
            "agents.subtitle",
            "Configured roles and local Ollama model availability. "
            "This panel never starts models or changes configuration."))
        subtitle = self._subtitle
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #7E8798; font-size: 12px;")
        header.addWidget(subtitle)
        layout.addLayout(header)

        self._status_label = QLabel(_tr(
            "agents.status_unknown", "Availability not checked yet."))
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._status_label)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels([
            _tr("agents.header_role", "Role"),
            _tr("agents.header_model", "Model"),
            _tr("agents.header_availability", "Availability")])
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

        self._policy = QLabel(_tr(
            "agents.policy",
            "Resource policy: local model stages run sequentially. "
            "Cloud escalation is opt-in and disabled by default."))
        policy = self._policy
        policy.setWordWrap(True)
        policy.setStyleSheet(
            "color: #AB83C6; font-size: 12px; padding: 8px; "
            "border: 1px solid #343947; border-radius: 6px;"
        )
        layout.addWidget(policy)

        self._refresh_btn = QPushButton(_tr(
            "agents.refresh", "Refresh availability"))
        refresh_btn = self._refresh_btn
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._configure_btn = QPushButton(_tr(
            "agents.configure", "Configure custom agents"))
        self._configure_btn.setObjectName("secondaryButton")
        self._configure_btn.setAccessibleName("Configure custom agents")
        self._configure_btn.clicked.connect(self._open_custom_agents)
        layout.addWidget(self._configure_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        editor = QHBoxLayout()
        self._role_editor = QComboBox()
        self._role_editor.setObjectName("roleModelRoleCombo")
        self._role_editor.setAccessibleName("Role to assign a model")
        for role in ("architect", "developer", "debugger", "reviewer", "chat"):
            self._role_editor.addItem(role, role)
        self._model_editor = QComboBox()
        self._model_editor.setObjectName("roleModelModelCombo")
        self._model_editor.setEditable(True)
        self._model_editor.setAccessibleName("Model route for selected role")
        self._save_role_btn = QPushButton("Save role model")
        self._save_role_btn.setObjectName("saveRoleModelButton")
        self._save_role_btn.clicked.connect(self._save_role_model)
        editor.addWidget(QLabel("Role model"))
        editor.addWidget(self._role_editor)
        editor.addWidget(self._model_editor, 1)
        editor.addWidget(self._save_role_btn)
        layout.addLayout(editor)
        self._role_editor.currentIndexChanged.connect(self._sync_role_model)

        self._render(self._services.get_agent_roles(), [], None)
        _register_retranslate(self)

    def retranslate(self) -> None:
        self._title.setText(_tr("agents.title", "Agents"))
        self._subtitle.setText(_tr(
            "agents.subtitle",
            "Configured roles and local Ollama model availability. "
            "This panel never starts models or changes configuration."))
        self._policy.setText(_tr(
            "agents.policy",
            "Resource policy: local model stages run sequentially. "
            "Cloud escalation is opt-in and disabled by default."))
        self._refresh_btn.setText(_tr(
            "agents.refresh", "Refresh availability"))
        self._table.setHorizontalHeaderLabels([
            _tr("agents.header_role", "Role"),
            _tr("agents.header_model", "Model"),
            _tr("agents.header_availability", "Availability")])

    def _open_custom_agents(self) -> None:
        from nl_coding_agent.gui.dialogs.custom_agents import CustomAgentsDialog

        dialog = CustomAgentsDialog(self._services, self)
        dialog.exec()
        self.refresh()

    def _sync_role_model(self, *_args) -> None:
        role = self._role_editor.currentData() or self._role_editor.currentText()
        config = self._services.get_model_config() or {}
        model = str(((config.get("roles") or {}).get(role) or {}).get("model") or "")
        index = self._model_editor.findText(model)
        if index >= 0:
            self._model_editor.setCurrentIndex(index)
        elif model:
            self._model_editor.setCurrentText(model)

    def _save_role_model(self) -> None:
        role = str(self._role_editor.currentData() or self._role_editor.currentText())
        model = str(self._model_editor.currentText() or "").strip()
        if not role or not model:
            self._status_label.setText("Role and model are required.")
            self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")
            return
        try:
            self._services.save_role_settings(role, model=model)
        except Exception as exc:
            self._status_label.setText("Save failed: " + str(exc))
            self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")
            return
        self._status_label.setText(f"Saved model for {role}: {model}")
        self._status_label.setStyleSheet("color: #55C58A; font-size: 12px;")

    def refresh(self):
        if self._thread is not None and self._thread.isRunning():
            return
        self._status_label.setText(_tr(
            "agents.checking", "Checking Ollama model availability..."))
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
        if self._model_editor.count() == 0:
            for name in sorted(available):
                self._model_editor.addItem(name, "ollama/" + name)
            self._sync_role_model()
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
        if role.get("custom_agent_id"):
            return _tr("agents.status_profile_only", "Profile only (execution pending)"), Qt.GlobalColor.gray
        if role.get("kind") == "deterministic":
            return _tr("agents.status_deterministic", "Deterministic"), Qt.GlobalColor.darkCyan
        model = str(role.get("model") or "")
        if not model:
            return _tr("agents.status_not_configured", "Not configured"), Qt.GlobalColor.red
        if reachable is None:
            return _tr("agents.status_checking", "Checking..."), Qt.GlobalColor.gray
        if not reachable:
            return _tr("agents.status_unknown_offline", "Unknown (offline)"), Qt.GlobalColor.darkYellow
        key = model[len("ollama/"):] if model.startswith("ollama/") else model
        installed = available.get(key)
        if installed is None:
            return _tr("agents.status_not_installed", "Not installed"), Qt.GlobalColor.red
        if getattr(installed, "loaded", False):
            return _tr("agents.status_running", "Running"), Qt.GlobalColor.green
        return _tr("agents.status_available", "Available"), Qt.GlobalColor.darkGreen

"""Agents panel - configured roles and local model availability."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QVBoxLayout, QWidget,
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
    data_ready = Signal(list, list, bool, list, str)

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services

    def run(self):
        roles = []
        try:
            roles = self._services.get_agent_roles()
            reachable = self._services.check_ollama()
            models = self._services.list_models() if reachable else []
            routes = {
                "ollama/" + str(model.name)
                for model in models
            }
            route_error = ""
            try:
                snapshot = self._services.discover_models(timeout=5.0)
                routes.update(
                    str(provider.provider_id) + "/" + str(model.name)
                    for provider in snapshot.providers
                    for model in provider.models
                )
            except Exception as exc:
                route_error = str(exc)
            if not self.isInterruptionRequested():
                self.data_ready.emit(
                    roles, models, reachable, sorted(routes), route_error)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.data_ready.emit(
                    roles, [], False, [], "Model availability check failed: " + str(exc))


class TeamPlanThread(QThread):
    completed = Signal(int, dict)
    failed = Signal(int, str)

    def __init__(self, services, project_id: int, model: str, parent=None):
        super().__init__(parent)
        self._services = services
        self._project_id = project_id
        self._model = model

    def run(self):
        try:
            result = self._services.team_plan(self._project_id, self._model)
        except Exception as exc:
            self.failed.emit(self._project_id, str(exc))
            return
        if not isinstance(result, dict) or not result.get("roles"):
            self.failed.emit(self._project_id, "Team Architect returned no usable specialist roles.")
            return
        self.completed.emit(self._project_id, result)


class AgentsPanel(QWidget):
    """Configured roles, project team generation, and local model availability."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._thread: AgentFetchThread | None = None
        self._team_thread: TeamPlanThread | None = None
        self._project: dict | None = None

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
            "Configure role models, generate a project team, and check local model availability."))
        subtitle = self._subtitle
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #7E8798; font-size: 12px;")
        header.addWidget(subtitle)
        layout.addLayout(header)

        self._status_label = QLabel(_tr(
            "agents.status_unknown", "Availability not checked yet."))
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._status_label)

        self._team_status = QLabel(_tr(
            "agents.no_active_team", "No active specialist team for this project."))
        self._team_status.setObjectName("activeProjectTeamStatus")
        self._team_status.setWordWrap(True)
        self._team_status.setStyleSheet("color: #AB83C6; font-size: 12px;")
        layout.addWidget(self._team_status)

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

        self._configure_btn = QPushButton(_tr(
            "agents.configure", "Configure custom agents"))
        self._configure_btn.setObjectName("secondaryButton")
        self._configure_btn.setAccessibleName("Configure custom agents")
        self._configure_btn.clicked.connect(self._open_custom_agents)

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

        self._generate_team_btn = QPushButton("Generate team for project")
        self._generate_team_btn.setObjectName("generateProjectTeamButton")
        self._generate_team_btn.setToolTip(_tr(
            "agents.team_tooltip",
            "Analyze this project with the selected provider/model, then preview and assign "
            "the specialists the Supervisor can execute."))
        self._generate_team_btn.setEnabled(False)
        self._generate_team_btn.clicked.connect(self._generate_team)
        layout.addWidget(self._generate_team_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self._table, 1)
        layout.addWidget(self._policy)
        actions = QHBoxLayout()
        actions.addWidget(self._refresh_btn)
        actions.addWidget(self._configure_btn)
        actions.addStretch()
        layout.addLayout(actions)

        self._render(self._services.get_agent_roles(), [], None)
        _register_retranslate(self)

    def retranslate(self) -> None:
        self._title.setText(_tr("agents.title", "Agents"))
        self._subtitle.setText(_tr(
            "agents.subtitle",
            "Configure role models, generate a project team, and check local model availability."))
        self._policy.setText(_tr(
            "agents.policy",
            "Resource policy: local model stages run sequentially. "
            "Cloud escalation is opt-in and disabled by default."))
        self._refresh_btn.setText(_tr(
            "agents.refresh", "Refresh availability"))
        self._generate_team_btn.setText(
            _tr("agents.generate_team", "Generate team for project"))
        self._generate_team_btn.setToolTip(_tr(
            "agents.team_tooltip",
            "Analyze this project with the selected provider/model, then preview and assign "
            "the specialists the Supervisor can execute."))
        self._table.setHorizontalHeaderLabels([
            _tr("agents.header_role", "Role"),
            _tr("agents.header_model", "Model"),
            _tr("agents.header_availability", "Availability")])

    def _open_custom_agents(self) -> None:
        from nl_coding_agent.gui.dialogs.custom_agents import CustomAgentsDialog

        project_id = (self._project or {}).get("id")
        dialog = CustomAgentsDialog(
            self._services, self,
            project_id=int(project_id) if project_id is not None else None)
        dialog.exec()
        self.refresh()
        self._refresh_team_status()

    def set_project(self, project: dict | None) -> None:
        old_id = (self._project or {}).get("id")
        self._project = dict(project) if project else None
        self._generate_team_btn.setEnabled(
            bool(self._project) and not (
                self._team_thread is not None and self._team_thread.isRunning()))
        if old_id != (self._project or {}).get("id"):
            self._refresh_team_status()

    def _refresh_team_status(self) -> None:
        project_id = (self._project or {}).get("id")
        if project_id is None:
            self._team_status.setText(_tr(
                "agents.open_project_team",
                "Open a project to view or generate its active team."))
            return
        try:
            active = [
                profile for profile in self._services.list_custom_agents()
                if profile.get("enabled", True)
                and profile.get("team_active") is True
                and str(profile.get("project_id") or "") == str(project_id)
            ]
        except Exception as exc:
            self._team_status.setText(_tr(
                "agents.team_read_failed",
                "Could not read the active project team: {error}",
                error=str(exc)))
            self._team_status.setToolTip(str(exc))
            return
        self._team_status.setToolTip("")
        if not active:
            self._team_status.setText(_tr(
                "agents.no_active_team", "No active specialist team for this project."))
            return
        active.sort(key=lambda item: str(item.get("role_id") or item.get("role") or ""))
        lines = [
            _tr("agents.active_team",
                "Active team for {name} ({count} specialist(s)):",
                name=self._project.get("name") or "project", count=len(active))
        ]
        lines.extend(
            f"- {item.get('name') or item.get('role_id')} "
            f"[{item.get('role_id') or item.get('role')}] - "
            f"{item.get('model') or item.get('provider') or 'model not set'}"
            for item in active
        )
        self._team_status.setText("\n".join(lines))

    def _generate_team(self) -> None:
        project_id = (self._project or {}).get("id")
        if project_id is None:
            QMessageBox.information(
                self, _tr("agents.team_no_project_title", "No project"),
                _tr("agents.team_no_project", "Open a project before generating its team."))
            return
        if self._team_thread is not None and self._team_thread.isRunning():
            return
        model = str(self._model_editor.currentText() or "").strip()
        if not model:
            model = str(self._model_editor.currentData() or "").strip()
        if model and "/" not in model:
            model = "ollama/" + model
        if not model:
            QMessageBox.warning(
                self, _tr("agents.team_model_title", "Model required"),
                _tr("agents.team_model_required",
                    "Choose or enter a provider/model route for Team Architect."))
            return
        self._generate_team_btn.setEnabled(False)
        self._team_status.setText(_tr(
            "agents.team_analyzing", "Team Architect is analyzing the project…"))
        self._status_label.setText(_tr(
            "agents.team_generating", "Generating a project-specific specialist team…"))
        thread = TeamPlanThread(self._services, int(project_id), model, self)
        thread.completed.connect(self._on_team_plan_ready)
        thread.failed.connect(self._on_team_plan_failed)
        thread.finished.connect(lambda thread=thread: self._team_thread_finished(thread))
        self._team_thread = thread
        thread.start()

    def _team_thread_finished(self, thread: TeamPlanThread) -> None:
        if self._team_thread is thread:
            self._team_thread = None
            self._generate_team_btn.setEnabled(self._project is not None)
        thread.deleteLater()

    def _on_team_plan_failed(self, project_id: int, error: str) -> None:
        if int((self._project or {}).get("id") or -1) != project_id:
            self._team_status.setText(_tr(
                "agents.team_failed_project",
                "Team analysis for project #{project_id} failed: {error}",
                project_id=project_id, error=error))
            return
        self._team_status.setText(_tr(
            "agents.team_generation_failed", "Team generation failed") + ": " + error)
        self._status_label.setText(_tr(
            "agents.team_generation_failed", "Team generation failed"))
        self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")
        QMessageBox.warning(
            self, _tr("agents.team_generation_failed", "Team generation failed"), error)

    def _on_team_plan_ready(self, project_id: int, plan: dict) -> None:
        if int((self._project or {}).get("id") or -1) != project_id:
            self._team_status.setText(_tr(
                "agents.team_reopen_project",
                "Team analysis for project #{project_id} finished. Reopen that project to assign it.",
                project_id=project_id))
            return
        roles = plan.get("roles") or []
        summary = str(plan.get("summary") or "").strip()
        preview = [
            f"{item.get('name') or item.get('role_id')} "
            f"[{item.get('role_id')}] — {item.get('model')}"
            f"\n  Tools: {', '.join(item.get('tools') or [])}"
            for item in roles
        ]
        if plan.get("fallback"):
            summary = (summary + "\n\n" if summary else "") + (
                _tr("agents.team_fallback",
                    "Team Architect used the deterministic fallback."))
        if plan.get("analysis_error"):
            summary = (summary + "\n\n" if summary else "") + _tr(
                "agents.team_analysis_error",
                "Analysis detail: {error}",
                error=str(plan["analysis_error"])[:800])
        message = (summary + "\n\n" if summary else "") + "\n".join(preview)
        answer = QMessageBox.question(
            self, _tr("agents.team_assign_title", "Assign generated team"),
            _tr("agents.team_assign_prompt",
                "Review the proposed project team. Project Access remains the sole permission policy.")
            + "\n\n"
            + message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._team_status.setText(_tr(
                "agents.team_not_assigned", "Generated team was not assigned."))
            return
        try:
            saved = self._services.assign_project_team(project_id, roles)
        except Exception as exc:
            failure = _tr("agents.team_assign_failed", "Team assignment failed")
            self._team_status.setText(failure + ": " + str(exc))
            self._status_label.setText(failure)
            self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")
            QMessageBox.warning(
                self, failure, str(exc))
            return
        self._refresh_team_status()
        self._status_label.setText(_tr(
            "agents.team_assigned",
            "Team assigned: {created} created, {updated} updated.",
            created=saved.get("created", 0), updated=saved.get("updated", 0)))
        self._status_label.setStyleSheet("color: #55C58A; font-size: 12px;")
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
        self._refresh_team_status()
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
        team_thread = self._team_thread
        if team_thread is not None:
            team_thread.requestInterruption()
            if not team_thread.wait(100000):
                team_thread.wait()
            self._team_thread = None

    def _on_data_ready(self, roles: list, models: list, reachable: bool,
                       routes: list[str] | None = None, route_error: str = ""):
        self._render(roles or self._services.get_agent_roles(), models, reachable, routes or [])
        if reachable:
            text = f"Ollama reachable - {len(models)} model(s) available."
            color = "#55C58A"
            if route_error:
                text += " Provider route discovery failed: " + route_error
                color = "#E26472"
            self._status_label.setText(text)
            self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        else:
            text = "Ollama unreachable - model availability is unknown."
            if route_error:
                text += " Provider route discovery failed: " + route_error
            self._status_label.setText(text)
            self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")

    def _render(self, roles: list, models: list, reachable: bool | None,
                routes: list[str] | None = None):
        available = {m.name: m for m in models}
        self._available_routes = set(routes or ())
        selected_route = str(
            self._model_editor.currentText() or self._model_editor.currentData() or "")
        route_options = set(routes or ())
        route_options.update("ollama/" + name for name in available)
        self._model_editor.blockSignals(True)
        self._model_editor.clear()
        for route in sorted(route_options):
            self._model_editor.addItem(route, route)
        selected_index = self._model_editor.findText(selected_route)
        if selected_route and selected_index < 0:
            self._model_editor.setCurrentText(selected_route)
        elif selected_index >= 0:
            self._model_editor.setCurrentIndex(selected_index)
        else:
            self._sync_role_model()
        self._model_editor.blockSignals(False)
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
        if "/" in model and not model.startswith("ollama/"):
            if model in getattr(self, "_available_routes", set()):
                return _tr("agents.status_available", "Available"), Qt.GlobalColor.darkGreen
            return _tr(
                "agents.status_route_unavailable", "Provider route not discovered"
            ), Qt.GlobalColor.darkYellow
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

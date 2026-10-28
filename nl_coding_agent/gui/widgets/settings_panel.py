"""Settings panel - runtime configuration plus Advanced self-build controls."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from nl_coding_agent.gui.i18n import tr_for

_AUTONOMY_MODES = [("Off", "off"), ("Assisted", "assisted"), ("Automatic", "automatic")]
_ACTIVE_STATUSES = {
    "running", "starting", "paused", "waiting_for_resources",
    "waiting_for_approval", "stopping", "recovering",
}
_HISTORY_COLUMNS = ["Run", "Mode", "Status", "Missions", "Started", "Finished"]


class SettingsPanel(QWidget):
    """Read-only runtime settings plus the Advanced self-build/autonomy controls.

    The Advanced section is the only place where autonomy settings can be changed.
    Nothing here starts a run or a model: Save persists validated limits, while
    Pause/Stop forward a cooperative command to the supervisor backend.
    """

    autonomy_requested = Signal()

    def __init__(self, services, parent=None, *, translator=None):
        super().__init__(parent)
        self._services = services
        self._i18n = translator
        self._form_labels: list[tuple[QLabel, str, str]] = []
        self._project_root: str | None = None
        self._project_id: int | None = None
        self._advanced_active = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._title = QLabel(tr_for(self._i18n, "settings.title", "Settings"))
        self._title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(self._title)

        self._subtitle = QLabel(tr_for(
            self._i18n, "settings.subtitle",
            "Runtime paths and configuration state. Read-only; no secrets are displayed. "
            "Self-build/autonomy controls live only under Advanced below."))
        subtitle = self._subtitle
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
        self._permissions_value = QLabel()
        self._permissions_value.setWordWrap(True)
        self._permissions_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._language_value = QComboBox()
        self._language_value.setObjectName("uiLanguageCombo")
        self._language_combo = self._language_value
        self._language_value.setAccessibleName("UI language")
        self._language_value.setToolTip(tr_for(
            self._i18n, "settings.language_tooltip",
            "Presentation language only. It does not change agent responses, "
            "generated code or documentation."))
        for key, default, code in (
                ("settings.language_italian", "Italiano", "it"),
                ("settings.language_english", "English", "en"),
                ("settings.language_system", "System (auto)", "system")):
            self._language_value.addItem(
                tr_for(self._i18n, key, default), code)
        self._language_value.currentIndexChanged.connect(
            self._on_language_changed)
        for label_key, default, widget in (
                ("settings.project_root", "Project root", self._project_value),
                ("settings.database", "SQLite database", self._database_value),
                ("settings.ollama", "Ollama base URL", self._ollama_value),
                ("settings.models", "Model config", self._models_value),
                ("settings.cloud", "Cloud escalation", self._cloud_value),
                ("settings.permissions", "Permissions", self._permissions_value),
                ("settings.language", "UI language", self._language_value)):
            label = QLabel(tr_for(self._i18n, label_key, default))
            self._form_labels.append((label, label_key, default))
            form.addRow(label, widget)
        layout.addLayout(form)

        self._advanced_group = self._build_advanced_group()
        layout.addWidget(self._advanced_group)

        self._note = QLabel(tr_for(
            self._i18n, "settings.cloud_note",
            "Cloud escalation remains disabled unless explicitly enabled for a project. "
            "Saving Advanced settings never starts autonomy by itself."))
        note = self._note
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #AB83C6; font-size: 12px; padding: 8px; "
            "border: 1px solid #343947; border-radius: 6px;"
        )
        layout.addWidget(note)

        self._refresh_btn = QPushButton(tr_for(
            self._i18n, "settings.refresh", "Refresh"))
        refresh_btn = self._refresh_btn
        refresh_btn.setAccessibleName("Refresh settings and autonomy preview")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

        self.refresh()
        self._sync_language_combo()

    # ------------------------------------------------------------------ advanced UI

    def _build_advanced_group(self) -> QGroupBox:
        self._advanced_group_box = QGroupBox(tr_for(
            self._i18n, "settings.advanced_group",
            "Advanced - self-build and autonomy"))
        group = self._advanced_group_box
        group.setObjectName("advancedAutonomyGroup")
        group.setAccessibleName("Advanced self-build and autonomy controls")
        outer = QVBoxLayout(group)
        outer.setSpacing(8)
        self._self_build_heading = QLabel(tr_for(
            self._i18n, "settings.self_build_heading",
            "Self-Build (This Agent) — Advanced controls"))
        self._self_build_heading.setObjectName("advancedSelfBuildHeading")
        self._self_build_heading.setAccessibleName(
            "Self-Build (This Agent) activation and configuration")
        outer.addWidget(self._self_build_heading)

        intro = QLabel(
            "Nothing starts automatically when the app opens or when settings are saved. "
            "Save/Apply persists the mode and limits; Pause/Stop are cooperative and are "
            "honoured at safe mission boundaries. External processes are never killed."
        )
        intro.setWordWrap(True)
        intro.setObjectName("advancedAutonomyIntro")
        outer.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)

        self._advanced_mode_combo = QComboBox()
        self._advanced_mode_combo.setObjectName("advancedModeCombo")
        self._advanced_mode_combo.setAccessibleName("Self-build autonomy mode")
        self._advanced_mode_combo.setToolTip(
            "Off is the default. Assisted/Automatic apply only to explicitly started runs."
        )
        self._advanced_mode_labels = []
        for label, value in _AUTONOMY_MODES:
            display = tr_for(self._i18n, "settings.mode_" + value, label)
            self._advanced_mode_combo.addItem(display, value)
            self._advanced_mode_labels.append((display, value))
        self._advanced_form_labels = []
        mode_label = QLabel(tr_for(self._i18n, "settings.autonomy_mode", "Autonomy mode"))
        self._advanced_form_labels.append((mode_label, "settings.autonomy_mode", "Autonomy mode"))
        form.addRow(mode_label, self._advanced_mode_combo)

        self._advanced_missions_spin = QSpinBox()
        self._advanced_missions_spin.setObjectName("advancedMissionsSpin")
        self._advanced_missions_spin.setAccessibleName("Maximum missions per supervisor run")
        self._advanced_missions_spin.setRange(1, 5)
        self._advanced_missions_spin.setValue(1)
        missions_label = QLabel(tr_for(self._i18n, "settings.missions_per_run", "Missions per run"))
        self._advanced_form_labels.append((missions_label, "settings.missions_per_run", "Missions per run"))
        form.addRow(missions_label, self._advanced_missions_spin)

        self._advanced_attempts_spin = QSpinBox()
        self._advanced_attempts_spin.setObjectName("advancedAttemptsSpin")
        self._advanced_attempts_spin.setAccessibleName("Maximum repair attempts per requirement")
        self._advanced_attempts_spin.setRange(1, 5)
        self._advanced_attempts_spin.setValue(2)
        attempts_label = QLabel(tr_for(self._i18n, "settings.attempts_per_requirement", "Attempts per requirement"))
        self._advanced_form_labels.append((attempts_label, "settings.attempts_per_requirement", "Attempts per requirement"))
        form.addRow(attempts_label, self._advanced_attempts_spin)

        self._advanced_wall_spin = QSpinBox()
        self._advanced_wall_spin.setObjectName("advancedWallSpin")
        self._advanced_wall_spin.setAccessibleName("Wall-clock limit per run in minutes")
        self._advanced_wall_spin.setRange(5, 480)
        self._advanced_wall_spin.setValue(60)
        self._advanced_wall_spin.setSuffix(" min")
        wall_label = QLabel(tr_for(self._i18n, "settings.wall_clock", "Run wall-clock limit"))
        self._advanced_form_labels.append((wall_label, "settings.wall_clock", "Run wall-clock limit"))
        form.addRow(wall_label, self._advanced_wall_spin)
        outer.addLayout(form)

        self._preview_caption = QLabel(tr_for(
            self._i18n, "settings.preview_caption",
            "Execution preview (read-only; no run starts)"))
        preview_caption = self._preview_caption
        preview_caption.setStyleSheet("font-size: 12px; font-weight: 600;")
        outer.addWidget(preview_caption)
        self._advanced_plan_preview = QPlainTextEdit()
        self._advanced_plan_preview.setObjectName("advancedPlanPreview")
        self._advanced_plan_preview.setAccessibleName("Read-only autonomous execution preview")
        self._advanced_plan_preview.setReadOnly(True)
        self._advanced_plan_preview.setMinimumHeight(110)
        self._advanced_plan_preview.setPlaceholderText(tr_for(
            self._i18n, "settings.preview_placeholder",
            "Open a project to preview the next supervised work."
        ))
        outer.addWidget(self._advanced_plan_preview)

        self._history_caption = QLabel(tr_for(
            self._i18n, "settings.history_caption",
            "Autonomy history (read-only, from SQLite)"))
        history_caption = self._history_caption
        history_caption.setStyleSheet("font-size: 12px; font-weight: 600;")
        outer.addWidget(history_caption)
        self._advanced_history_table = QTableWidget(0, len(_HISTORY_COLUMNS))
        self._advanced_history_table.setObjectName("advancedHistoryTable")
        self._advanced_history_table.setAccessibleName("Read-only autonomy run history")
        self._advanced_history_table.setHorizontalHeaderLabels([
            tr_for(self._i18n, "settings.history_" + column.lower().replace(" ", "_"), column)
            for column in _HISTORY_COLUMNS])
        self._advanced_history_table.verticalHeader().setVisible(False)
        self._advanced_history_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._advanced_history_table.horizontalHeader().setStretchLastSection(True)
        self._advanced_history_table.setMinimumHeight(90)
        outer.addWidget(self._advanced_history_table)

        self._advanced_notice = QLabel("")
        self._advanced_notice.setObjectName("advancedNotice")
        self._advanced_notice.setWordWrap(True)
        self._advanced_notice.setAccessibleName("Advanced autonomy status message")
        self._advanced_notice.setStyleSheet("font-size: 12px; color: #7E8798;")
        outer.addWidget(self._advanced_notice)

        buttons = QHBoxLayout()
        self._save_advanced_btn = QPushButton(tr_for(
            self._i18n, "settings.save_apply", "Save / Apply"))
        self._save_advanced_btn.setObjectName("primaryButton")
        self._save_advanced_btn.setAccessibleName(
            "Save autonomy mode and limits (does not start a run)"
        )
        self._save_advanced_btn.setToolTip(tr_for(
            self._i18n, "settings.save_apply_tooltip",
            "Persist the mode and limits for this project. Does not start a run."
        ))
        self._save_advanced_btn.clicked.connect(self._save_advanced)

        self._pause_advanced_btn = QPushButton(tr_for(
            self._i18n, "settings.advanced_pause", "Pause"))
        self._pause_advanced_btn.setObjectName("secondaryButton")
        self._pause_advanced_btn.setAccessibleName("Pause the active supervisor run")
        self._pause_advanced_btn.setToolTip(tr_for(
            self._i18n, "settings.advanced_pause_tooltip",
            "Cooperative pause at the next safe mission boundary (Ctrl+Alt+P)."
        ))
        self._pause_advanced_btn.setEnabled(False)
        self._pause_advanced_btn.clicked.connect(self._pause_advanced)

        self._stop_advanced_btn = QPushButton(tr_for(
            self._i18n, "settings.advanced_stop", "Stop…"))
        self._stop_advanced_btn.setObjectName("dangerButton")
        self._stop_advanced_btn.setAccessibleName(
            "Stop the active supervisor run after confirmation"
        )
        self._stop_advanced_btn.setToolTip(tr_for(
            self._i18n, "settings.advanced_stop_tooltip",
            "Request a cooperative stop; asks for confirmation and never kills "
            "external processes (Ctrl+Alt+S)."
        ))
        self._stop_advanced_btn.setEnabled(False)
        self._stop_advanced_btn.clicked.connect(self._stop_advanced)

        self._refresh_advanced_btn = QPushButton(tr_for(
            self._i18n, "settings.refresh_preview", "Refresh preview"))
        self._refresh_advanced_btn.setAccessibleName(
            "Refresh the read-only autonomy preview and history"
        )
        self._refresh_advanced_btn.clicked.connect(self._load_advanced)

        for button in (self._save_advanced_btn, self._pause_advanced_btn,
                       self._stop_advanced_btn, self._refresh_advanced_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        outer.addLayout(buttons)

        # Backwards-compatible navigation affordance (kept for existing callers/tests).
        self._autonomy_btn = QPushButton(tr_for(
            self._i18n, "settings.open_autonomy",
            "Open autonomy status page…"))
        self._autonomy_btn.setAccessibleName("Open the read-only autonomy status page")
        self._autonomy_btn.clicked.connect(self.autonomy_requested.emit)
        outer.addWidget(self._autonomy_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        return group

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _path_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _sync_language_combo(self) -> None:
        if self._i18n is None:
            preference = getattr(self._services, "ui_language_preference", lambda: "it")()
        else:
            preference = self._i18n.preference
        index = self._language_value.findData(preference)
        if index >= 0 and index != self._language_value.currentIndex():
            self._language_value.blockSignals(True)
            self._language_value.setCurrentIndex(index)
            self._language_value.blockSignals(False)

    def _on_language_changed(self, _index: int) -> None:
        if self._i18n is None:
            return
        code = str(self._language_value.currentData() or "it")
        try:
            result = self._i18n.set_language(code)
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            self._set_advanced_notice(str(exc), ok=False)
            return
        if not result.get("ok", True):
            self._set_advanced_notice(
                str(result.get("error") or "language change failed"), ok=False)

    def retranslate(self) -> None:
        self._title.setText(tr_for(self._i18n, "settings.title", "Settings"))
        self._subtitle.setText(tr_for(
            self._i18n, "settings.subtitle",
            "Runtime paths and configuration state. Read-only; no secrets are displayed. "
            "Self-build/autonomy controls live only under Advanced below."))
        for label, key, default in self._form_labels:
            label.setText(tr_for(self._i18n, key, default))
        labels = (("settings.language_italian", "Italiano"),
                  ("settings.language_english", "English"),
                  ("settings.language_system", "System (auto)"))
        for index, (key, default) in enumerate(labels):
            if index < self._language_value.count():
                self._language_value.setItemText(
                    index, tr_for(self._i18n, key, default))
        self._language_value.setToolTip(tr_for(
            self._i18n, "settings.language_tooltip",
            "Presentation language only. It does not change agent responses, "
            "generated code or documentation."))
        self._refresh_btn.setText(tr_for(self._i18n, "settings.refresh", "Refresh"))
        self._advanced_group_box.setTitle(tr_for(
            self._i18n, "settings.advanced_group",
            "Advanced - self-build and autonomy"))
        self._note.setText(tr_for(
            self._i18n, "settings.cloud_note",
            "Cloud escalation remains disabled unless explicitly enabled for a project. "
            "Saving Advanced settings never starts autonomy by itself."))
        self._autonomy_btn.setText(tr_for(
            self._i18n, "settings.open_autonomy",
            "Open autonomy status page…"))
        self._self_build_heading.setText(tr_for(
            self._i18n, "settings.self_build_heading",
            "Self-Build (This Agent) — Advanced controls"))
        self._preview_caption.setText(tr_for(
            self._i18n, "settings.preview_caption",
            "Execution preview (read-only; no run starts)"))
        self._history_caption.setText(tr_for(
            self._i18n, "settings.history_caption",
            "Autonomy history (read-only, from SQLite)"))
        self._save_advanced_btn.setText(tr_for(
            self._i18n, "settings.save_apply", "Save / Apply"))
        self._pause_advanced_btn.setText(tr_for(
            self._i18n, "settings.advanced_pause", "Pause"))
        self._stop_advanced_btn.setText(tr_for(
            self._i18n, "settings.advanced_stop", "Stop…"))
        self._refresh_advanced_btn.setText(tr_for(
            self._i18n, "settings.refresh_preview", "Refresh preview"))
        for label, key, default in getattr(self, "_advanced_form_labels", []):
            label.setText(tr_for(self._i18n, key, default))
        for index, (label, value) in enumerate(
                getattr(self, "_advanced_mode_labels", [])):
            if index < self._advanced_mode_combo.count():
                self._advanced_mode_combo.setItemText(
                    index, tr_for(self._i18n, "settings.mode_" + value, label))
        self._advanced_history_table.setHorizontalHeaderLabels([
            tr_for(self._i18n,
                   "settings.history_" + column.lower().replace(" ", "_"),
                   column)
            for column in _HISTORY_COLUMNS])
        self._sync_language_combo()
        self.refresh()

    def set_project(self, project: dict | None):
        self._project_root = project.get("root") if project else None
        self._project_id = int(project["id"]) if project and project.get("id") is not None else None
        self.refresh()

    # ------------------------------------------------------------------ refresh

    def refresh(self):
        settings = self._services.get_runtime_settings(self._project_root)
        root = settings.get("project_root")
        self._project_value.setText(root or tr_for(
            self._i18n, "settings.no_project", "No project open"))
        self._database_value.setText(str(settings.get("database_path") or ""))
        self._ollama_value.setText(str(settings.get("ollama_base_url") or ""))
        self._models_value.setText(str(settings.get("model_config_path") or ""))
        if settings.get("cloud_escalation_enabled"):
            self._cloud_value.setText(tr_for(
                self._i18n, "settings.enabled", "Enabled"))
            self._cloud_value.setStyleSheet("color: #E26472;")
        else:
            self._cloud_value.setText(tr_for(
                self._i18n, "settings.disabled",
                "Disabled - opt-in per project"))
            self._cloud_value.setStyleSheet("color: #55C58A;")
        self._refresh_permissions()
        self._load_advanced()

    def _refresh_permissions(self):
        scopes: list[str] = []
        policy: dict = {}
        try:
            permissions = self._services.get_permissions(self._project_id)
            scopes = list(permissions.get("scopes") or [])
            policy = dict(permissions.get("policy") or {})
        except Exception:
            scopes = []
            policy = {}
        if not scopes:
            self._permissions_value.setText(tr_for(
                self._i18n, "settings.unavailable", "Unavailable"))
            return
        granted = [scope.upper() for scope in scopes if policy.get(scope)]
        denied = [scope.upper() for scope in scopes if not policy.get(scope)]
        scope_text = "Granted: " + (", ".join(granted) or "none")
        if denied:
            scope_text += "  |  Denied: " + ", ".join(denied)
        scope_text += "  (human/backend owned; read-only here)"
        self._permissions_value.setText(scope_text)

    # ------------------------------------------------------------------ advanced

    def _load_advanced(self) -> None:
        project_id = self._project_id
        if project_id is None:
            self._advanced_mode_combo.setCurrentIndex(0)
            self._advanced_plan_preview.setPlainText(tr_for(
                self._i18n, "settings.open_project_preview",
                "Open a project to preview the supervised execution plan."
            ))
            self._advanced_history_table.setRowCount(0)
            self._save_advanced_btn.setEnabled(False)
            self._pause_advanced_btn.setEnabled(False)
            self._stop_advanced_btn.setEnabled(False)
            self._refresh_advanced_btn.setEnabled(False)
            self._advanced_notice.setText(tr_for(
                self._i18n, "settings.no_project_notice",
                "No project open."))
            return
        self._save_advanced_btn.setEnabled(True)
        self._refresh_advanced_btn.setEnabled(True)
        try:
            settings = self._services.autonomy_settings(project_id) or {}
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            settings = {"ok": False, "error": str(exc)}
        if settings.get("ok", True):
            self._apply_settings_to_controls(settings)
        else:
            self._advanced_notice.setText(
                tr_for(self._i18n, "settings.unavailable_prefix",
                       "Settings unavailable: ")
                + str(settings.get("error") or tr_for(
                    self._i18n, "common.unknown_error", "unknown error"))
            )
        try:
            plan = self._services.autonomy_plan(project_id) or {}
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            plan = {"ok": False, "error": str(exc)}
        self._advanced_plan_preview.setPlainText(self._format_plan(plan, settings))
        try:
            history = self._services.autonomy_history(project_id) or []
        except Exception:  # noqa: BLE001 - empty history is valid
            history = []
        self._fill_history(history)
        active = False
        try:
            status = self._services.supervisor_status(project_id) or {}
            active = self._status_is_active(status)
        except Exception:  # noqa: BLE001 - controls fail closed
            active = False
        self._advanced_active = bool(active)
        self._pause_advanced_btn.setEnabled(active)
        self._stop_advanced_btn.setEnabled(active)
        if not self._advanced_notice.text():
            self._set_advanced_notice(
                tr_for(self._i18n, "settings.read_only_preview",
                       "Read-only preview. Nothing starts automatically."), ok=True
            )

    @staticmethod
    def _status_is_active(status: dict) -> bool:
        run = status.get("run") or {}
        service = status.get("service") or {}
        label = str(run.get("status") or status.get("status") or "idle").strip().lower()
        return bool(service.get("thread_running")) or label in _ACTIVE_STATUSES

    def _apply_settings_to_controls(self, settings: dict) -> None:
        mode = str(settings.get("mode") or "off")
        for index in range(self._advanced_mode_combo.count()):
            if self._advanced_mode_combo.itemData(index) == mode:
                self._advanced_mode_combo.setCurrentIndex(index)
                break
        else:
            self._advanced_mode_combo.setCurrentIndex(0)
        try:
            self._advanced_missions_spin.setValue(
                int(settings.get("max_missions_per_run") or 1))
            self._advanced_attempts_spin.setValue(
                int(settings.get("max_attempts_per_requirement") or 2))
            wall = int(settings.get("max_wall_time_s") or 3600)
            self._advanced_wall_spin.setValue(max(5, min(480, round(wall / 60))))
        except (TypeError, ValueError):
            pass

    def _format_plan(self, plan: dict, settings: dict) -> str:
        lines: list[str] = []
        if not plan.get("ok", True):
            lines.append("Preview unavailable: " + str(plan.get("error") or "unknown error"))
        mode = str(plan.get("mode") or settings.get("mode") or "off").upper()
        lines.append("Mode: " + mode + "  |  starts automatically: no")
        try:
            lines.append(
                "Limits: missions/run=" + str(plan.get("settings", {}).get(
                    "max_missions_per_run", "?"))
                + ", attempts/requirement=" + str(plan.get("settings", {}).get(
                    "max_attempts_per_requirement", "?"))
                + ", wall clock=" + str(round(int(plan.get("settings", {}).get(
                    "max_wall_time_s", 0)) / 60)) + " min"
            )
        except (TypeError, ValueError):
            pass
        stage = plan.get("program_stage")
        lines.append("Program stage: " + (str(stage) if stage is not None else "not synced"))
        counts = plan.get("queue_counts") or {}
        queue_text = ", ".join(key + "=" + str(value) for key, value in sorted(counts.items()))
        lines.append("Mission queue: " + (queue_text or "empty"))
        requirements = plan.get("next_requirements") or []
        if requirements:
            lines.append("Next requirements:")
            for item in requirements:
                lines.append(
                    "  - " + str(item.get("requirement_id") or "?")
                    + "  " + str(item.get("title") or "")
                    + (("  [" + str(item.get("priority")) + "]")
                       if item.get("priority") else "")
                )
        else:
            lines.append("Next requirements: none pending in the indexed backlog.")
        active_run = plan.get("active_run") or {}
        if active_run:
            lines.append(
                "Active run: #" + str(active_run.get("id"))
                + " " + str(active_run.get("status") or "")
                + " (mode " + str(active_run.get("mode") or "?") + ")"
            )
        else:
            lines.append("Active run: none")
        resume = str(plan.get("resume_command") or "")
        if resume:
            lines.append("Backend/CLI start command: " + resume)
        lines.append("Read-only preview: no mission or model run is started from this panel.")
        return chr(10).join(lines)

    def _fill_history(self, history: list[dict]) -> None:
        self._advanced_history_table.setRowCount(len(history))
        for row, item in enumerate(history):
            missions = (str(item.get("missions_completed") or 0) + "/"
                        + str(item.get("missions_failed") or 0))
            values = [
                "#" + str(item.get("id") or "-"),
                str(item.get("mode") or "-"),
                str(item.get("status") or "-"),
                missions,
                str(item.get("started_at") or "-"),
                str(item.get("finished_at") or "-"),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                self._advanced_history_table.setItem(row, column, cell)
        self._advanced_history_table.resizeColumnsToContents()

    def _set_advanced_notice(self, text: str, *, ok: bool = True) -> None:
        self._advanced_notice.setText(text)
        self._advanced_notice.setStyleSheet(
            "font-size: 12px; color: " + ("#55C58A" if ok else "#E26472") + ";"
        )

    def _save_advanced(self) -> None:
        project_id = self._project_id
        if project_id is None:
            self._set_advanced_notice(tr_for(
                self._i18n, "settings.open_project_save",
                "Open a project before saving settings."), ok=False)
            return
        mode = str(self._advanced_mode_combo.currentData() or "off")
        try:
            result = self._services.save_autonomy_settings(
                project_id,
                mode=mode,
                max_missions=self._advanced_missions_spin.value(),
                attempts=self._advanced_attempts_spin.value(),
                max_wall_time_s=self._advanced_wall_spin.value() * 60,
            ) or {}
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            result = {"ok": False, "error": str(exc)}
        if result.get("ok"):
            self._set_advanced_notice(
                tr_for(self._i18n, "settings.saved_notice",
                       "Saved. Mode/limits apply at the next safe mission boundary; "
                       "no run was started."), ok=True
            )
        else:
            self._set_advanced_notice(
                tr_for(self._i18n, "settings.save_failed", "Save failed: ")
                + str(result.get("error") or tr_for(
                    self._i18n, "common.unknown_error", "unknown error")), ok=False
            )
        self._load_advanced()

    def _pause_advanced(self) -> None:
        project_id = self._project_id
        if project_id is None:
            return
        try:
            result = self._services.supervisor_pause(project_id) or {}
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            result = {"ok": False, "error": str(exc)}
        if result.get("ok", True):
            self._set_advanced_notice(
                tr_for(self._i18n, "settings.pause_requested",
                       "Pause requested - honoured at the next safe mission boundary."), ok=True
            )
        else:
            self._set_advanced_notice(
                tr_for(self._i18n, "settings.pause_failed", "Pause failed: ")
                + str(result.get("error") or tr_for(
                    self._i18n, "common.unknown_error", "unknown error")), ok=False
            )
        self._load_advanced()

    def _stop_advanced(self) -> None:
        project_id = self._project_id
        if project_id is None:
            return
        answer = QMessageBox.question(
            self,
            tr_for(self._i18n, "settings.stop_title", "Stop autonomous run"),
            tr_for(self._i18n, "settings.stop_body",
                   "Request a cooperative stop of the active supervisor run?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._set_advanced_notice(tr_for(
                self._i18n, "settings.stop_cancelled", "Stop cancelled."), ok=True)
            return
        try:
            result = self._services.supervisor_stop(
                project_id, reason="operator stop from Settings > Advanced",
            ) or {}
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            result = {"ok": False, "error": str(exc)}
        if result.get("ok", True):
            self._set_advanced_notice(
                tr_for(self._i18n, "settings.stop_requested",
                       "Stop requested - the current mission reaches a safe state first; "
                       "external processes are not killed."), ok=True
            )
        else:
            self._set_advanced_notice(
                tr_for(self._i18n, "settings.stop_failed", "Stop failed: ")
                + str(result.get("error") or tr_for(
                    self._i18n, "common.unknown_error", "unknown error")), ok=False
            )
        self._load_advanced()

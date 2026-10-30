"""F1: multimodal mission chat input (drag/drop, paste, previews, explicit submit)."""
from __future__ import annotations

from nl_coding_agent.gui.widgets.studio_workspace import studio_settings
# Expose ModelHubFetchThread at module scope for test monkey‑patching and runtime use.
from nl_coding_agent.gui.widgets.models_panel import ModelHubFetchThread

from PySide6.QtCore import (QBuffer, QIODevice, QObject, QRunnable, QSize, Qt,
                            QThreadPool, Signal, Slot)
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
                               QInputDialog)
from PySide6.QtWidgets import QSpinBox


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


class _Signals(QObject):
    done = Signal(dict)
    voice_done = Signal(dict)
    voice_failed = Signal(str)


class _VoiceTask(QRunnable):
    def __init__(self, fn, signals: _Signals) -> None:
        super().__init__()
        self._fn, self._signals = fn, signals

    def run(self) -> None:
        try:
            self._signals.voice_done.emit(self._fn() or {})
        except Exception as exc:  # noqa: BLE001 - shown as deterministic status
            self._signals.voice_failed.emit(
                getattr(exc, "code", "voice-unavailable") + ": " + str(exc))


class _Prepare(QRunnable):
    def __init__(self, fn, signals: _Signals) -> None:
        super().__init__()
        self._fn, self._signals = fn, signals

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - surfaced in the status label
            result = {"attachments": [], "errors": [{"name": "attachment",
                                                     "error": str(exc)}]}
        self._signals.done.emit(result or {})


class ChatInput(QTextEdit):
    attachment_paste = Signal()
    submit_requested = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.ControlModifier:
                self.insertPlainText("\n")
                event.accept()
                return
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source) -> None:  # noqa: N802 - Qt override
        if source is not None and (source.hasImage() or source.hasUrls()):
            self.attachment_paste.emit()
            return
        super().insertFromMimeData(source)


class ChatPanel(QWidget):
    """Mission chat composer; attachment preparation runs off the UI thread."""

    submitted = Signal(dict)
    context_requested = Signal()
    cancel_tools_requested = Signal()
    resume_tools_requested = Signal()
    session_selected = Signal(str)

    def __init__(self, services, parent=None, *, speech=None) -> None:
        super().__init__(parent)
        self._services = services
        self._speech = speech
        self._project = None
        self._attachments: list[dict] = []
        self._pending = 0
        self._voice_session = None
        self._voice_busy = False
        self._last_transcript = ""
        self._pool = QThreadPool.globalInstance()
        self._signals = _Signals()
        self._signals.done.connect(self._on_prepared)
        self._signals.voice_done.connect(self._on_voice_done)
        self._signals.voice_failed.connect(self._on_voice_failed)
        self.setAcceptDrops(True)
        self.setAccessibleName("Project chat")
        self._build_ui()
        _register_retranslate(self)
        self.retranslate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self._title = QLabel(_tr("chat.title", "CHAT"))
        title = self._title
        title.setObjectName("chatTitle")
        title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        header.addWidget(title)
        header.addStretch()
        self._project_label = QLabel(_tr(
            "chat.no_project", "No project open"))
        self._project_label.setObjectName("chatProject")
        self._project_label.setMaximumWidth(160)
        header.addWidget(self._project_label)
        layout.addLayout(header)

        session_row = QHBoxLayout()
        self._session_combo = QComboBox()
        self._session_combo.setObjectName("chatSessionCombo")
        self._session_combo.setAccessibleName("Chat session")
        self._session_combo.currentIndexChanged.connect(self._on_session_changed)
        session_row.addWidget(QLabel("Session"))
        session_row.addWidget(self._session_combo, 1)
        for label, slot, name in (
                ("New", self._new_session, "chatNewSessionButton"),
                ("Rename", self._rename_session, "chatRenameSessionButton"),
                ("Archive", self._archive_session, "chatArchiveSessionButton"),
                ("Delete", self._delete_session, "chatDeleteSessionButton")):
            button = QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(slot)
            session_row.addWidget(button)
        layout.addLayout(session_row)
        self._hint = QLabel(
            "Drop files or folders here, or paste with Ctrl+V (text, files, images, "
            "Windows screenshots). Enter sends; Ctrl+Enter adds a newline.")
        self._hint.setObjectName("chatHint")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: #AB83C6;")
        self._hint.setAccessibleName("Mission chat hint")
        layout.addWidget(self._hint)
        self._transcript = QTextBrowser()
        self._transcript.setObjectName("chatTranscript")
        self._transcript.setReadOnly(True)
        self._transcript.setAccessibleName("Chat transcript")
        self._transcript.setMinimumHeight(80)
        layout.addWidget(self._transcript, 1)
        self._input = ChatInput()
        self._input.setObjectName("chatInput")
        self.setFocusProxy(self._input)
        self._input.setPlaceholderText(_tr(
            "chat.placeholder",
            "Ask a question…"))
        self._input.setMinimumHeight(64)
        self._input.setMaximumHeight(140)
        self._input.setAccessibleName("Chat message")
        self._input.setAccessibleDescription(
            "Type the mission goal. Drop files/folders or paste attachments.")
        self._input.attachment_paste.connect(self._paste_attachments)
        self._input.submit_requested.connect(self._submit)
        layout.addWidget(self._input)
        self._attachments_list = QListWidget()
        self._attachments_list.setObjectName("chatAttachments")
        self._attachments_list.setMaximumHeight(150)
        self._attachments_list.setIconSize(QSize(48, 48))
        self._attachments_list.setAccessibleName("Prepared attachments")

        self._attachments_list.hide()
        layout.addWidget(self._attachments_list)

        self._voice_options = QWidget()
        voice = QHBoxLayout(self._voice_options)
        voice.setContentsMargins(0, 0, 0, 0)
        self._mic_btn = QPushButton(_tr("chat.dictate", "Dictate"))
        self._mic_btn.setObjectName("voiceButton")
        self._mic_btn.setAccessibleName("Start or stop dictation")
        self._mic_btn.setToolTip(_tr(
            "chat.dictate_tooltip",
            "Start/stop local microphone dictation (Ctrl+Shift+M)"))
        self._mic_btn.clicked.connect(self._toggle_voice)
        voice.addWidget(self._mic_btn)
        self._voice_stop_btn = QPushButton(_tr("chat.stop", "Stop"))
        self._voice_stop_btn.setObjectName("secondaryButton")
        self._voice_stop_btn.setAccessibleName("Stop voice recording")
        self._voice_stop_btn.setEnabled(False)
        self._voice_stop_btn.clicked.connect(self._stop_voice)
        voice.addWidget(self._voice_stop_btn)
        self._voice_status = QLabel(_tr("chat.voice_idle", "Voice: idle"))
        self._voice_status.setObjectName("voiceStatus")
        self._voice_status.setStyleSheet("color: #AB83C6;")
        self._voice_status.setAccessibleName("Voice status")
        voice.addWidget(self._voice_status, 1)
        self._tts_toggle = QCheckBox(_tr(
            "chat.read_aloud", "Read transcript aloud"))
        self._tts_toggle.setObjectName("ttsToggle")
        self._tts_toggle.setAccessibleName("Read transcript aloud")
        voice.addWidget(self._tts_toggle)
        self._voice_options.setVisible(False)
        layout.addWidget(self._voice_options)
        route = QHBoxLayout()
        self._action = QComboBox()
        for key, label in (("chat", "Conversation"), ("document_plan", "Document plan"),
                           ("coding", "Coding task"), ("goal", "Autonomous Goal")):
            self._action.addItem(_tr("chat.action_" + key, label), key)
        self._action.setToolTip(_tr("chat.action_hint", "Only explicit actions create plans or tasks"))
        route.addWidget(self._action)
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.setMinimumWidth(80)
        self._model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._model.setMinimumContentsLength(12)
        self._model.setToolTip(_tr("chat.model_hint", "Exact provider/model route; project permissions apply"))
        self._model.setAccessibleName("Chat provider/model")
        self._model.addItem(_tr("chat.model_default", "Configured model"), "")
        config = self._services.get_model_config() if callable(getattr(self._services, "get_model_config", None)) else {}
        roles = (config or {}).get("roles") or {}
        self._configured_route = str((roles.get("chat") or roles.get("developer") or {}).get("model") or "")
        if self._configured_route:
            self._model.setItemText(0, self._configured_route)
        for role in roles.values():
            route_name = str((role or {}).get("model") or "")
            if route_name and self._model.findText(route_name) < 0:
                self._model.addItem(route_name, route_name)
        route.addWidget(self._model, 1)
        self._discover_btn = QPushButton(_tr("chat.models_refresh", "Models…"))
        self._discover_btn.clicked.connect(self._discover_models)
        route.addWidget(self._discover_btn)
        layout.addLayout(route)
        tools_row = QHBoxLayout()
        self._tools_enabled = QCheckBox(_tr("chat.tools_authorize", "Authorize tools this turn"))
        self._tools_enabled.setToolTip(_tr("chat.tools_warning", "Allows source reads, Research and trusted MCP calls under project permissions. External servers use your OS privileges."))
        tools_row.addWidget(self._tools_enabled)
        self._coding_enabled = QCheckBox(_tr("chat.coding_authorize", "Allow coding missions"))
        tools_row.addWidget(self._coding_enabled)
        self._tool_budget = QSpinBox()
        self._tool_budget.setRange(1, 32)
        self._tool_budget.setValue(8)
        self._tool_budget.setToolTip(_tr("chat.tool_budget", "Maximum model requests plus tool calls per turn"))
        tools_row.addWidget(self._tool_budget)
        self._tool_protocol = QComboBox()
        self._tool_protocol.addItem(_tr("chat.native_tools", "Native tools"), "native")
        self._tool_protocol.addItem(_tr("chat.json_tools", "Validated JSON"), "json")
        tools_row.addWidget(self._tool_protocol)
        layout.addLayout(tools_row)
        tool_controls = QHBoxLayout()
        self._cancel_tools = QPushButton(_tr("chat.cancel_tools", "Stop tools"))
        self._cancel_tools.clicked.connect(lambda: self.cancel_tools_requested.emit())
        self._resume_tools = QPushButton(_tr("chat.resume_tools", "Resume tools"))
        self._resume_tools.clicked.connect(lambda: self.resume_tools_requested.emit())
        self._research_profile = QComboBox()
        for value, key, label in (("manual", "manual", "Manual Research"),
                                  ("trusted-auto-review", "trusted", "Trusted Research")):
            self._research_profile.addItem(_tr("chat.research_" + key, label), value)
        self._research_profile.setToolTip(_tr("chat.research_policy", "Research autonomy profile for this turn; capability and network grants remain required"))
        tool_controls.addWidget(self._cancel_tools)
        tool_controls.addWidget(self._resume_tools)
        tool_controls.addWidget(self._research_profile)
        self._tool_seconds = QSpinBox()
        self._tool_seconds.setRange(5, 600)
        self._tool_seconds.setValue(180)
        self._tool_seconds.setSuffix(" s")
        self._tool_seconds.setToolTip(_tr("chat.tool_seconds", "Tool conversation time budget; active calls stop at safe boundaries"))
        tool_controls.addWidget(self._tool_seconds)
        tool_controls.addStretch()
        layout.addLayout(tool_controls)
        footer = QHBoxLayout()
        self._attach_btn = QPushButton(_tr(
            "chat.attach_files", "Attach files…"))
        self._attach_btn.setObjectName("secondaryButton")
        self._attach_btn.setAccessibleName("Attach files")
        self._attach_btn.setToolTip(_tr(
            "chat.attach_tooltip", "Choose files (Ctrl+O)"))
        self._attach_btn.clicked.connect(self._choose_files)
        footer.addWidget(self._attach_btn)
        self._remove_btn = QPushButton(_tr("chat.remove", "Remove"))
        self._remove_btn.setObjectName("secondaryButton")
        self._remove_btn.setAccessibleName("Remove selected attachment")
        self._remove_btn.setToolTip(_tr(
            "chat.remove_tooltip", "Remove selected attachment (Delete)"))
        self._remove_btn.clicked.connect(self._remove_selected)
        footer.addWidget(self._remove_btn)
        self._context_btn = QPushButton(_tr("chat.open_file", "Open file"))
        self._context_btn.setToolTip(_tr("chat.context_hint", "Attach a snapshot of the active editor file or selection"))
        self._context_btn.clicked.connect(self.context_requested)
        footer.addWidget(self._context_btn)
        self._voice_toggle = QPushButton(_tr("chat.voice_options", "Voice"))
        self._voice_toggle.setMaximumWidth(55)
        self._voice_toggle.setCheckable(True)
        self._voice_toggle.toggled.connect(self._voice_options.setVisible)
        footer.addWidget(self._voice_toggle)
        footer.addStretch()
        self._status = QLabel(_tr("chat.ready", "Ready"))
        self._status.setObjectName("chatStatus")
        self._status.setStyleSheet("color: #46A3C0;")
        self._status.setAccessibleName("Attachment preparation status")
        layout.addWidget(self._status)
        self._submit_btn = QPushButton(_tr(
            "chat.send_mission", "Invia"))
        self._submit_btn.setObjectName("primaryButton")
        self._submit_btn.setAccessibleName("Send message")
        self._submit_btn.setToolTip(_tr(
            "chat.submit_tooltip", "Send (Enter); newline (Ctrl+Enter)"))
        self._submit_btn.clicked.connect(self._submit)
        self._queue_btn = QPushButton("Queue")
        self._queue_btn.setObjectName("chatQueueButton")
        self._queue_btn.setToolTip("Persist this text as the next Chat turn")
        self._queue_btn.clicked.connect(lambda: self._queue_text("queue"))
        self._steer_btn = QPushButton("Steer")
        self._steer_btn.setObjectName("chatSteerButton")
        self._steer_btn.setToolTip("Inject this text into the running Chat turn")
        self._steer_btn.clicked.connect(lambda: self._queue_text("steer"))
        footer.addWidget(self._queue_btn)
        footer.addWidget(self._steer_btn)
        footer.addWidget(self._submit_btn)
        layout.addLayout(footer)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._choose_files, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Ctrl+Shift+M"), self, activated=self._toggle_voice, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Delete"), self._attachments_list,
                  activated=self._remove_selected, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # ------------------------------------------------------------- project
    def retranslate(self) -> None:
        self._title.setText(_tr("chat.title", "CHAT"))
        if hasattr(self, "_action"):
            for attribute, key, label in (("_tools_enabled", "tools_authorize", "Authorize tools this turn"),
                                          ("_coding_enabled", "coding_authorize", "Allow coding missions"),
                                          ("_cancel_tools", "cancel_tools", "Stop tools"),
                                          ("_resume_tools", "resume_tools", "Resume tools")):
                getattr(self, attribute).setText(_tr("chat." + key, label))
            for index, key, label in ((0, "native_tools", "Native tools"), (1, "json_tools", "Validated JSON")):
                self._tool_protocol.setItemText(index, _tr("chat." + key, label))
            for index, key, label in ((0, "research_manual", "Manual Research"), (1, "research_trusted", "Trusted Research")):
                self._research_profile.setItemText(index, _tr("chat." + key, label))
            for index, label in enumerate(("Conversation", "Document plan", "Coding task", "Autonomous Goal")):
                self._action.setItemText(index, _tr("chat.action_" + self._action.itemData(index), label))
            self._discover_btn.setText(_tr("chat.models_refresh", "Models…"))
            self._context_btn.setText(_tr("chat.open_file", "Open file"))
            self._voice_toggle.setText(_tr("chat.voice_options", "Voice"))
            self._submit_btn.setToolTip(_tr("chat.submit_tooltip", "Send (Enter); newline (Ctrl+Enter)"))
        self._hint.setText(_tr(
            "chat.hint",
            "Drop files or folders here, or paste with Ctrl+V (text, files, images, "
            "Windows screenshots). Enter sends; Ctrl+Enter adds a newline."))
        self._input.setPlaceholderText(_tr(
            "chat.placeholder",
            "Ask a question…"))
        self._mic_btn.setText(_tr("chat.dictate", "Dictate"))
        self._voice_stop_btn.setText(_tr("chat.stop", "Stop"))
        self._tts_toggle.setText(_tr(
            "chat.read_aloud", "Read transcript aloud"))
        self._attach_btn.setText(_tr("chat.attach_files", "Attach files…"))
        self._remove_btn.setText(_tr("chat.remove", "Remove"))
        self._submit_btn.setText(_tr("chat.send_mission", "Invia"))
        self.set_project(self._project)

    def set_project(self, project) -> None:
        old_id = (self._project or {}).get("id")
        self._project = dict(project) if project else None
        if old_id != (self._project or {}).get("id") and hasattr(self, "_model"):
            self._tools_enabled.setChecked(False)
            self._coding_enabled.setChecked(False)
            self._research_profile.setCurrentIndex(0)
            route = studio_settings().value(
                "workspace/chat_model/" + str((self._project or {}).get("id")), "")
            self._model.setCurrentIndex(0)
            if route:
                self._model.setCurrentText(route)
            self._attachments.clear()
            self._refresh()
        self._project_label.setToolTip((self._project or {}).get("root", ""))
        self._project_label.setText(
            (self._project or {}).get("name") or _tr(
                "chat.no_project", "No project open"))
        self._status.setText(_tr("chat.ready", "Ready") if project else _tr(
            "chat.open_project", "Open a project to submit a mission"))
        self._refresh_sessions()

    def _refresh_sessions(self, select_id: str | None = None) -> None:
        if not self._project or not hasattr(self, "_session_combo"):
            return
        try:
            sessions = self._services.list_chat_sessions(self._project["id"])
        except Exception:
            sessions = []
        current = select_id or self.current_session_id()
        self._session_combo.blockSignals(True)
        self._session_combo.clear()
        for session in sessions:
            self._session_combo.addItem(str(session.get("title") or "Conversation"),
                                        str(session.get("id") or ""))
        index = self._session_combo.findData(current)
        if index >= 0:
            self._session_combo.setCurrentIndex(index)
        self._session_combo.blockSignals(False)

    def current_session_id(self) -> str | None:
        if not hasattr(self, "_session_combo"):
            return None
        return self._session_combo.currentData()

    def _on_session_changed(self, _index: int) -> None:
        session_id = self.current_session_id()
        if session_id:
            self.session_selected.emit(str(session_id))

    def _new_session(self) -> None:
        if not self._project:
            return
        try:
            session = self._services.create_chat_session(self._project["id"])
        except Exception as exc:
            self._status.setText("Create session failed: " + str(exc))
            return
        self._refresh_sessions(str(session.get("id")))
        self.session_selected.emit(str(session.get("id")))
        self.clear_transcript()

    def _rename_session(self) -> None:
        session_id = self.current_session_id()
        if not session_id:
            return
        title, ok = QInputDialog.getText(self, "Rename session", "Title:")
        if not ok or not str(title).strip():
            return
        try:
            self._services.rename_chat_session(str(session_id), str(title))
        except Exception as exc:
            self._status.setText("Rename failed: " + str(exc))
            return
        self._refresh_sessions(str(session_id))

    def _archive_session(self) -> None:
        session_id = self.current_session_id()
        if not session_id:
            return
        try:
            self._services.archive_chat_session(str(session_id))
        except Exception as exc:
            self._status.setText("Archive failed: " + str(exc))
            return
        self._refresh_sessions()
        self.session_selected.emit(str(self.current_session_id() or ""))
        self.clear_transcript()

    def _delete_session(self) -> None:
        session_id = self.current_session_id()
        if not session_id:
            return
        answer = QMessageBox.question(
            self, "Delete archived session",
            "Delete this Chat session and its messages? Archive it first.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._services.delete_chat_session(self._project["id"], str(session_id))
        except Exception as exc:
            self._status.setText("Delete failed: " + str(exc))
            return
        self._refresh_sessions()
        self.session_selected.emit(str(self.current_session_id() or ""))
        self.clear_transcript()

    def _queue_text(self, mode: str) -> None:
        if not self._project:
            return
        text = str(self._input.toPlainText() or "").strip()
        if not text:
            self._status.setText("Type a message before queueing it.")
            return
        try:
            from nl_coding_agent.app.chat_tools import enqueue
            result = enqueue(self._services, self._project["id"], text, mode=mode)
        except Exception as exc:
            self._status.setText("Queue failed: " + str(exc))
            return
        self._input.clear()
        self._status.setText(
            f"Stored {mode} message ({result.get('count', 0)} queued).")

    def _discover_models(self):
        """Refresh the model list and let the user pick a model.

        The existing UI only refreshed the combo; we now present a modal
        selection dialog (QInputDialog) populated with the discovered routes.
        The chosen model is set as the current combo entry, persisted via
        ``studio_settings`` and reflected in the payload sent to the backend.
        """
        # Use the module‑level ModelHubFetchThread and QInputDialog for model selection.
        from PySide6.QtWidgets import QInputDialog

        if getattr(self, "_model_thread", None) and self._model_thread.isRunning():
            return
        self._discover_btn.setEnabled(False)
        self._model_thread = ModelHubFetchThread(self._services, parent=self)

        def loaded(snapshot):
            # Build a flat list of provider/model routes.
            routes = []
            for provider in snapshot.providers:
                for model in provider.models:
                    route = f"{provider.provider_id}/{model.name}"
                    routes.append(route)
                    if self._model.findText(route) < 0:
                        self._model.addItem(route, route)
            # If no routes are available, just restore UI state.
            if not routes:
                self._model.setCurrentIndex(0)
                self._discover_btn.setEnabled(True)
                return
            # Show selection dialog – in tests this can be monkey‑patched.
            current = self._model.currentText()
            selected, ok = QInputDialog.getItem(
                self,
                _tr("chat.select_model", "Select Model"),
                _tr("chat.select_model_prompt", "Choose a model:"),
                routes,
                editable=False,
                current=routes.index(current) if current in routes else 0,
            )
            if ok and selected:
                # Update combo and persist selection. Use index to ensure the selection changes
                # even when the combo is not editable.
                idx = self._model.findText(selected)
                if idx >= 0:
                    self._model.setCurrentIndex(idx)
                project_id = (self._project or {}).get("id")
                if project_id:
                    studio_settings().setValue(
                        f"workspace/chat_model/{project_id}", selected
                    )
            else:
                # Restore previous selection if cancelled.
                idx = self._model.findText(current)
                if idx >= 0:
                    self._model.setCurrentIndex(idx)

        self._model_thread.snapshot_ready.connect(loaded)
        self._model_thread.failed.connect(self._set_status)
        # Re‑enable the button when the thread finishes.
        # Some thread implementations (e.g., test dummies) may not provide a ``finished`` signal.
        # Guard against AttributeError by checking before connecting.
        if hasattr(self._model_thread, "finished"):
            self._model_thread.finished.connect(lambda: self._discover_btn.setEnabled(True))
        else:
            # If no finished signal, re‑enable the button immediately after start.
            self._model_thread.start()
            self._discover_btn.setEnabled(True)
            return
        self._model_thread.start()

    def selected_model(self):
        if self._model.currentIndex() == 0 and self._model.currentText() == self._model.itemText(0):
            return self._configured_route
        return self._model.currentText().strip()

    @property
    def attachments(self) -> list[dict]:
        return list(self._attachments)

    def _set_status(self, text: str) -> None:
        self._status.setText(str(text))

    # ---------------------------------------------------------- preparation
    def _start(self, fn) -> None:
        self._pending += 1
        self._submit_btn.setEnabled(False)
        self._set_status("Preparing attachment(s)…")
        project_id = (self._project or {}).get("id")
        def prepare():
            result = dict(fn() or {})
            result["_project_id"] = project_id
            return result
        self._pool.start(_Prepare(prepare, self._signals))

    @Slot(dict)
    def _on_prepared(self, result: dict) -> None:
        self._pending = max(0, self._pending - 1)
        if "_project_id" in result and result["_project_id"] != (self._project or {}).get("id"):
            self._submit_btn.setEnabled(self._pending == 0 and not getattr(self, "_reply_pending", False))
            return
        items = list(result.get("attachments") or [])
        errors = list(result.get("errors") or [])
        self._attachments.extend(items)
        self._refresh()
        if errors:
            self._set_status("Rejected: " + str(errors[0].get("error"))[:140])
        elif items:
            self._set_status("Added " + str(len(items)) + " attachment(s)")
        else:
            self._set_status("Ready")
        self._submit_btn.setEnabled(self._pending == 0 and not getattr(self, "_reply_pending", False))

    def set_reply_pending(self, pending: bool) -> None:
        """Keep shortcut submissions and attachment callbacks serialized too."""
        self._reply_pending = bool(pending)
        self._set_status(_tr("chat.waiting", "Waiting for model…") if pending else _tr("chat.ready", "Ready"))
        self._input.setEnabled(not pending)
        self._submit_btn.setEnabled(not pending and self._pending == 0)

    def add_paths(self, paths, *, source: str = "drop") -> None:
        cleaned = [str(item) for item in (paths or []) if str(item or "").strip()]
        if not cleaned:
            return
        project_id = (self._project or {}).get("id")
        self._start(lambda: self._services.prepare_attachment_paths(
            project_id, cleaned, source=source))

    def add_text(self, text: str) -> None:
        if not str(text or "").strip():
            return
        project_id = (self._project or {}).get("id")
        self._start(lambda: {"attachments": [
            self._services.prepare_attachment_text(project_id, str(text))],
            "errors": []})

    def add_clipboard_image(self, image: QImage) -> None:
        if image is None or image.isNull():
            self._set_status("Clipboard image is empty")
            return
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        payload = bytes(buffer.data())
        project_id = (self._project or {}).get("id")
        self._start(lambda: {"attachments": [
            self._services.prepare_attachment_clipboard_image(project_id, payload)],
            "errors": []})

    # ------------------------------------------------------------ clipboard
    @Slot()
    def _paste_attachments(self) -> None:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is not None and mime.hasImage():
            self.add_clipboard_image(clipboard.image())
        elif mime is not None and mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            self.add_paths(paths, source="paste")
        elif clipboard.text().strip():
            self.add_text(clipboard.text())

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Attach files")
        if files:
            self.add_paths(files, source="upload")

    # ------------------------------------------------------------ previews
    def _remove_selected(self) -> None:
        item = self._attachments_list.currentItem()
        if item is None:
            return
        attachment_id = item.data(Qt.ItemDataRole.UserRole)
        self._attachments = [a for a in self._attachments
                             if a.get("id") != attachment_id]
        self._refresh()
        self._set_status("Attachment removed")

    def append_user_message(self, text: str) -> None:
        from html import escape
        self._transcript.append("<b>" + _tr("chat.you", "You") + ":</b><br>" + escape(str(text)).replace("\n", "<br>"))

    def append_assistant_message(self, text: str, *, tool_activity: str = "") -> None:
        from html import escape
        markup = "<b>" + _tr("chat.assistant", "Assistant") + ":</b><br>" + escape(str(text)).replace("\n", "<br>")
        if tool_activity:
            markup += f"<br><i>Strumenti: {escape(tool_activity)}</i>"
        self._transcript.append(markup)

    def append_system_message(self, text: str) -> None:
        from html import escape
        self._transcript.append(f"<i>{escape(str(text))}</i>")

    def clear_attachments(self) -> None:
        self._attachments.clear()
        self._refresh()

    def clear_transcript(self) -> None:
        self._transcript.clear()

    def _refresh(self) -> None:
        self._attachments_list.clear()
        self._attachments_list.setVisible(bool(self._attachments))
        for entry in self._attachments:
            label = (str(entry.get("name") or "attachment") + "  ·  "
                     + str(entry.get("kind") or "?") + "  ·  "
                     + str(entry.get("size_bytes") or 0) + " B")
            if entry.get("error"):
                label += "  ·  extraction unavailable"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.get("id"))
            item.setToolTip(str(entry.get("error") or entry.get("stored_path") or ""))
            if entry.get("kind") == "image" and entry.get("stored_path"):
                pixmap = QPixmap(str(entry.get("stored_path")))
                if not pixmap.isNull():
                    item.setIcon(pixmap.scaled(
                        48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
            self._attachments_list.addItem(item)

    # ------------------------------------------------------------ drag/drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        mime = event.mimeData()
        if mime.hasUrls():
            self.add_paths([u.toLocalFile() for u in mime.urls() if u.isLocalFile()],
                           source="drop")
            event.acceptProposedAction()
        elif mime.hasImage():
            self.add_clipboard_image(QImage(mime.imageData()))
            event.acceptProposedAction()

    # --------------------------------------------------------------- submit
    def _submit(self) -> None:
        if getattr(self, "_reply_pending", False):
            return
        if not self._project:
            self._set_status(_tr("chat.open_project", "Open a project to chat"))
            return
        if self._pending > 0:
            self._set_status("Wait for attachment preparation to finish")
            return
        text = self._input.toPlainText().strip()
        if not text and not self._attachments:
            self._set_status("Write a mission or attach at least one file")
            return
        if text:
            self.append_user_message(text)
        payload = {
            "text": text,
            "action": self._action.currentData(),
            "model": self.selected_model(),
            "tool_options": self.tool_options(),
            "project_id": (self._project or {}).get("id"),
            "attachments": [{"id": a.get("id"), "name": a.get("name"),
                             "kind": a.get("kind"), "size_bytes": a.get("size_bytes"),
                             "extraction_status": a.get("extraction_status")}
                            for a in self._attachments],
            "attachment_ids": [a.get("id") for a in self._attachments],
        }
        studio_settings().setValue(
            "workspace/chat_model/" + str((self._project or {}).get("id")), self.selected_model())
        self._input.clear()
        self._tools_enabled.setChecked(False)
        self._coding_enabled.setChecked(False)
        self.clear_attachments()
        self._set_status(_tr("chat.sent", "Message sent"))
        self.submitted.emit(payload)

    def tool_options(self):
        return {"tools_enabled": self._tools_enabled.isChecked(),
                "allow_coding": self._coding_enabled.isChecked(),
                "max_calls": self._tool_budget.value(),
                "max_seconds": self._tool_seconds.value(),
                "research_profile": self._research_profile.currentData(),
                "tool_protocol": self._tool_protocol.currentData()}

    # ------------------------------------------------------------------ voice
    def _speech_backend(self):
        if self._speech is not None:
            return self._speech
        return self._services.speech_manager()

    def _toggle_voice(self) -> None:
        if self._voice_session is None:
            self._start_voice()
        else:
            self._stop_voice()

    def _start_voice(self) -> None:
        try:
            session = self._speech_backend().start_recording(max_seconds=60)
        except Exception as exc:  # noqa: BLE001 - deterministic UI status
            code = getattr(exc, "code", "voice-unavailable")
            self._voice_status.setText("Voice: " + code + " — " + str(exc))
            return
        self._voice_session = session
        self._mic_btn.setText("Dictating…")
        self._voice_stop_btn.setEnabled(True)
        self._voice_status.setText("Voice: recording (max 60 s) — click Dictate again to stop")

    def _stop_voice(self) -> None:
        session = self._voice_session
        if session is None:
            return
        self._voice_session = None
        self._mic_btn.setText("Dictate")
        self._voice_stop_btn.setEnabled(False)
        self._voice_status.setText("Voice: transcribing locally…")
        speech = self._speech_backend()

        def _work():
            recorded = speech.stop_recording(session["session_id"])
            transcript = speech.transcribe(recorded["wav_path"])
            return {"recorded": recorded, "transcript": transcript}

        self._voice_busy = True
        self._pool.start(_VoiceTask(_work, self._signals))

    def _on_voice_done(self, result: dict) -> None:
        self._voice_busy = False
        if "spoken_result" in result:
            self._voice_status.setText("Voice: spoken locally")
            return
        transcript = dict(result.get("transcript") or {})
        text = str(transcript.get("text") or "").strip()
        self._last_transcript = text
        if text:
            current = self._input.toPlainText()
            separator = "\n" if current.strip() else ""
            self._input.setPlainText(current + separator + text)
            self._voice_status.setText(
                "Voice: transcript inserted (editable; nothing submitted)")
            if self._tts_toggle.isChecked():
                self._speak(text)
        else:
            self._voice_status.setText("Voice: no speech detected in the recording")

    def _on_voice_failed(self, message: str) -> None:
        self._voice_busy = False
        self._voice_session = None
        self._mic_btn.setText("Dictate")
        self._voice_stop_btn.setEnabled(False)
        self._voice_status.setText("Voice unavailable: " + str(message)[:160])

    def _speak(self, text: str = "") -> None:
        content = str(text or self._last_transcript or "").strip()
        if not content:
            self._voice_status.setText("Voice: nothing to speak yet")
            return
        speech = self._speech_backend()
        self._voice_busy = True
        self._pool.start(_VoiceTask(
            lambda: {"spoken_result": speech.speak(content)}, self._signals))

    def wait_for_idle(self, timeout_ms: int = 5000) -> bool:
        import time
        deadline = time.monotonic() + max(0.1, timeout_ms / 1000.0)
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if self._pending == 0 and not self._voice_busy:
                QApplication.processEvents()
                return True
            time.sleep(0.01)
        return False

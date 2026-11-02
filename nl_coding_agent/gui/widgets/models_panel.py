"""Model Hub - provider-agnostic model discovery and status."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)


from nl_coding_agent.gui import i18n as _i18n
from nl_coding_agent.persistence import database


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


class ModelHubFetchThread(QThread):
    snapshot_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, services, timeout: float = 5.0, parent=None):
        super().__init__(parent)
        self._services = services
        self._timeout = timeout

    def run(self):
        try:
            snapshot = self._services.discover_models(timeout=self._timeout)
            self.snapshot_ready.emit(snapshot)
        except Exception as exc:
            self.failed.emit(str(exc))


class SpeechActionThread(QThread):
    completed = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, action: str, operation, parent=None):
        super().__init__(parent)
        self._action = action
        self._operation = operation

    def run(self):
        try:
            self.completed.emit(self._action, self._operation())
        except Exception as exc:
            self.failed.emit(self._action, str(exc))


class ModelsPanel(QWidget):
    """Center panel for provider, model, speech, hardware and storage status."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._thread: ModelHubFetchThread | None = None
        self._speech_thread: SpeechActionThread | None = None
        self._snapshot = None
        self._speech_catalog = {}
        self._speech_refresh_pending = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self._title = QLabel(_tr("model_hub.title", "Model Hub"))
        title = self._title
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        self._refresh_btn = QPushButton(_tr("model_hub.refresh", "Refresh"))
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        self._subtitle = subtitle = QLabel(
            "Inference providers, local models, speech engines and resource status."
        )
        subtitle.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(subtitle)

        self._status_label = QLabel(_tr(
            "model_hub.discovering", "Discovering providers."))
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._status_label)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_models_tab(), _tr("model_hub.tab_models", "Models"))
        self._tabs.addTab(self._build_parameters_tab(), "Generation")
        self._tabs.addTab(self._build_speech_tab(), _tr("model_hub.tab_speech", "Speech"))
        self._tabs.addTab(self._build_hardware_tab(), _tr("model_hub.tab_hardware", "Hardware"))
        self._tabs.addTab(self._build_storage_tab(), _tr("model_hub.tab_storage", "Storage"))
        layout.addWidget(self._tabs, 1)
        _register_retranslate(self)

    def retranslate(self) -> None:
        self._title.setText(_tr("model_hub.title", "Model Hub"))
        self._subtitle.setText(_tr(
            "model_hub.subtitle",
            "Inference providers, local models, speech engines and resource status."))
        self._refresh_btn.setText(_tr("model_hub.refresh", "Refresh"))
        self._tabs.setTabText(0, _tr("model_hub.tab_models", "Models"))
        self._tabs.setTabText(2, _tr("model_hub.tab_speech", "Speech"))
        self._tabs.setTabText(3, _tr("model_hub.tab_hardware", "Hardware"))
        self._tabs.setTabText(4, _tr("model_hub.tab_storage", "Storage"))

    def _build_models_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        self._provider_label = QLabel(_tr("model_hub.provider", "Provider"))
        filter_row.addWidget(self._provider_label)
        self._provider_filter = QComboBox()
        self._provider_filter.addItem(_tr("model_hub.all_providers", "All providers"), "")
        self._provider_filter.currentIndexChanged.connect(self._render_models)
        filter_row.addWidget(self._provider_filter, 1)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Provider", "Model", "Size (GB)", "Status", "Family", "Capabilities"]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table, 1)

        self._empty_label = QLabel(_tr(
            "model_hub.no_models", "No models discovered yet."))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._empty_label)
        return tab

    def _build_parameters_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        heading = QLabel("Persistent generation parameters")
        heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(heading)
        note = QLabel(
            "Blank fields leave the provider/Ollama default untouched. Context length "
            "is owned by Ollama application settings and is never sent by NL Code."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(note)

        form = QFormLayout()
        self._gp_scope = QComboBox()
        self._gp_scope.addItems(["model", "role", "global"])
        form.addRow("Scope", self._gp_scope)
        self._gp_model = QLineEdit()
        self._gp_model.setPlaceholderText("ollama/model:tag for model scope")
        form.addRow("Model", self._gp_model)
        self._gp_role = QComboBox()
        self._gp_role.setEditable(True)
        self._gp_role.addItems(["", "architect", "developer", "debugger", "reviewer", "chat"])
        form.addRow("Role", self._gp_role)
        self._gp_fields: dict[str, QLineEdit] = {}
        for key, placeholder in (
            ("temperature", "e.g. 0.2"), ("top_p", "e.g. 0.9"),
            ("top_k", "e.g. 40"), ("min_p", "e.g. 0.05"),
            ("repeat_penalty", "e.g. 1.1"), ("seed", "e.g. 42"),
            ("max_tokens", "optional output cap"),
        ):
            field = QLineEdit()
            field.setPlaceholderText(placeholder)
            self._gp_fields[key] = field
            form.addRow(key, field)
        layout.addLayout(form)

        actions = QHBoxLayout()
        save = QPushButton("Save parameters")
        save.clicked.connect(self._save_parameters)
        clear = QPushButton("Clear fields")
        clear.clicked.connect(self._clear_parameter_fields)
        actions.addWidget(save)
        actions.addWidget(clear)
        actions.addStretch()
        layout.addLayout(actions)
        self._gp_status = QLabel(
            "Explicit values are stored in SQLite; untouched values remain provider defaults.")
        self._gp_status.setWordWrap(True)
        self._gp_status.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._gp_status)
        layout.addStretch()
        return tab

    def _clear_parameter_fields(self) -> None:
        for field in self._gp_fields.values():
            field.clear()
        self._gp_status.setText("Fields cleared. Save to remove configured values.")

    def _save_parameters(self) -> None:
        values: dict = {}
        for key, field in self._gp_fields.items():
            text = field.text().strip()
            if not text:
                continue
            try:
                values[key] = int(text) if key in ("top_k", "seed", "max_tokens") else float(text)
            except ValueError:
                self._gp_status.setText(f"{key} must be numeric.")
                return
        scope = self._gp_scope.currentText()
        try:
            saved = self._services.save_generation_params(
                values, scope=scope,
                model_name=self._gp_model.text().strip(),
                role=self._gp_role.currentText().strip(),
            )
        except Exception as exc:
            self._gp_status.setText(f"Save failed: {exc}")
            return
        self._gp_status.setText(
            "Saved " + (", ".join(f"{k}={v}" for k, v in saved.items()) or "(none)")
            + ". Unconfigured parameters remain provider defaults.")

    def _build_speech_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        heading = QLabel("Speech and transcription")
        heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(heading)
        self._speech_status = QLabel("Loading local speech engines and models.")
        self._speech_status.setWordWrap(True)
        self._speech_status.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._speech_status)

        selectors = QHBoxLayout()
        self._speech_engine = QComboBox()
        self._speech_engine.setAccessibleName("Speech engine")
        self._speech_engine.currentIndexChanged.connect(self._render_speech_models)
        selectors.addWidget(self._speech_engine, 1)
        self._speech_model = QComboBox()
        self._speech_model.setAccessibleName("Speech model")
        selectors.addWidget(self._speech_model, 2)
        self._speech_use = QPushButton("Use model")
        self._speech_use.clicked.connect(self._use_speech_model)
        selectors.addWidget(self._speech_use)
        self._speech_refresh = QPushButton("Refresh")
        self._speech_refresh.clicked.connect(self._refresh_speech_catalog)
        selectors.addWidget(self._speech_refresh)
        layout.addLayout(selectors)

        external = QHBoxLayout()
        self._speech_external_path = QLineEdit()
        self._speech_external_path.setPlaceholderText(
            "Folder containing a local ASR model (external models stay in place)")
        self._speech_external_path.setAccessibleName("External ASR model folder")
        external.addWidget(self._speech_external_path, 1)
        self._speech_browse = QPushButton("Browse…")
        self._speech_browse.clicked.connect(self._browse_speech_model)
        external.addWidget(self._speech_browse)
        self._speech_add_external = QPushButton("Add external model")
        self._speech_add_external.clicked.connect(self._add_external_speech_model)
        external.addWidget(self._speech_add_external)
        layout.addLayout(external)

        self._speech_engine_details = QLabel("")
        self._speech_engine_details.setWordWrap(True)
        self._speech_engine_details.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._speech_engine_details)
        layout.addStretch()
        return tab

    def _render_speech_models(self, *_args) -> None:
        catalog = self._speech_catalog
        engine = str(self._speech_engine.currentData() or "")
        previous = self._speech_model.currentData()
        active = catalog.get("active_model") or {}
        self._speech_model.blockSignals(True)
        self._speech_model.clear()
        models = [item for item in catalog.get("models", [])
                  if item.get("engine") == engine]
        for model in models:
            label = f"{model.get('model_id', '')} · local"
            self._speech_model.addItem(label, model.get("model_id", ""))
            self._speech_model.setItemData(
                self._speech_model.count() - 1, model.get("path", ""), Qt.ItemDataRole.ToolTipRole)
        selected_id = previous if any(item.get("model_id") == previous for item in models) else ""
        if active.get("engine") == engine and any(
                item.get("model_id") == active.get("model_id") for item in models):
            selected_id = active.get("model_id", "")
        if selected_id:
            self._speech_model.setCurrentIndex(self._speech_model.findData(selected_id))
        self._speech_model.blockSignals(False)
        self._speech_use.setEnabled(self._speech_model.currentIndex() >= 0)
        selected_engine = next(
            (item for item in catalog.get("engines", []) if item.get("engine") == engine), {})
        installed = bool(selected_engine.get("installed"))
        self._speech_use.setEnabled(
            self._speech_model.currentIndex() >= 0 and installed)
        detail = selected_engine.get("hint") or ""
        if not installed:
            detail = "Engine not detected; install its local runtime before using a model. " + detail
        elif not models:
            detail = "No local models found for this engine. Add an external model folder below. " + detail
        self._speech_engine_details.setText(detail)

    def _render_speech_catalog(self, catalog: dict) -> None:
        self._speech_catalog = catalog if isinstance(catalog, dict) else {}
        engines = self._speech_catalog.get("engines") or []
        current_engine = self._speech_engine.currentData()
        active = self._speech_catalog.get("active_model") or {}
        self._speech_engine.blockSignals(True)
        self._speech_engine.clear()
        for item in engines:
            state = "installed" if item.get("installed") else "not installed"
            self._speech_engine.addItem(f"{item.get('engine', '')} · {state}", item.get("engine", ""))
        engine_id = active.get("engine") or current_engine
        index = self._speech_engine.findData(engine_id)
        self._speech_engine.setCurrentIndex(index if index >= 0 else (0 if engines else -1))
        self._speech_engine.blockSignals(False)
        self._render_speech_models()
        model_count = len(self._speech_catalog.get("models") or [])
        self._speech_status.setText(
            f"{model_count} local ASR model(s); active: "
            f"{active.get('model_id') or 'none'}"
            + (f" ({active.get('path')})" if active.get("path") else ""))

    def _start_speech_action(self, action: str, operation) -> None:
        if self._speech_thread is not None and self._speech_thread.isRunning():
            return
        self._speech_status.setText("Refreshing local speech models…" if action == "refresh"
                                    else "Working with the selected speech model…")
        self._speech_use.setEnabled(False)
        self._speech_add_external.setEnabled(False)
        self._speech_refresh.setEnabled(False)
        self._speech_thread = SpeechActionThread(action, operation, parent=self)
        self._speech_thread.completed.connect(self._on_speech_action_completed)
        self._speech_thread.failed.connect(self._on_speech_action_failed)
        self._speech_thread.finished.connect(self._on_speech_action_finished)
        self._speech_thread.start()

    def _refresh_speech_catalog(self) -> None:
        self._start_speech_action("refresh", self._services.speech_catalog)

    def _browse_speech_model(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select external ASR model folder")
        if folder:
            self._speech_external_path.setText(folder)

    def _add_external_speech_model(self) -> None:
        folder = self._speech_external_path.text().strip()
        if not folder:
            self._speech_status.setText("Choose a folder containing a local ASR model first.")
            return
        self._start_speech_action(
            "external", lambda: self._services.speech_set_external_home(folder))

    def _use_speech_model(self) -> None:
        model_id = str(self._speech_model.currentData() or "")
        if not model_id:
            self._speech_status.setText("Select a local model for the chosen engine.")
            return
        engine = str(self._speech_engine.currentData() or "")
        self._start_speech_action(
            "select", lambda: self._services.speech_switch_model(model_id, engine))

    def _on_speech_action_completed(self, action: str, result) -> None:
        if action == "refresh":
            self._render_speech_catalog(result)
        elif action == "external":
            catalog = result.get("catalog") if isinstance(result, dict) else None
            if isinstance(catalog, dict):
                self._render_speech_catalog(catalog)
            models = result.get("models") if isinstance(result, dict) else []
            self._speech_status.setText(
                f"Added {len(models or [])} external model(s) in place; files were not copied.")
        else:
            self._speech_status.setText("Speech model selected.")
            self._speech_refresh_pending = True

    def _on_speech_action_failed(self, action: str, message: str) -> None:
        self._speech_status.setText(f"{action.capitalize()} failed: {message}")

    def _on_speech_action_finished(self) -> None:
        self._speech_thread = None
        self._speech_use.setEnabled(self._speech_model.currentIndex() >= 0)
        self._speech_add_external.setEnabled(True)
        self._speech_refresh.setEnabled(True)
        if self._speech_refresh_pending:
            self._speech_refresh_pending = False
            self._refresh_speech_catalog()

    def _build_hardware_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        form = QFormLayout()
        self._ram_value = QLabel("See status bar")
        self._gpu_value = QLabel("See status bar")
        self._loaded_value = QLabel("No loaded models reported")
        self._provider_value = QLabel("No provider data")
        form.addRow("System RAM", self._ram_value)
        form.addRow("GPU / VRAM", self._gpu_value)
        form.addRow("Loaded models", self._loaded_value)
        form.addRow("Providers", self._provider_value)
        layout.addLayout(form)
        note = QLabel(
            "Estimates must remain separate from measured values. Live RAM and VRAM "
            "are measured by the application status bar; provider-reported loaded "
            "models are shown here."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(note)
        layout.addStretch()
        return tab

    def _build_storage_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        self._storage_value = QLabel(
            "Read-only size scan of temporary/build/backup/staging categories. "
            "Sources, the live database, attachments and shared model files are protected."
        )
        self._storage_value.setWordWrap(True)
        self._storage_value.setStyleSheet("color: #B8BECA; font-size: 12px;")
        layout.addWidget(self._storage_value)
        self._storage_table = QTableWidget(0, 4)
        self._storage_table.setHorizontalHeaderLabels(
            ["Category", "Size (MB)", "Files", "Deletable"])
        self._storage_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._storage_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._storage_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._storage_table, 1)
        actions = QHBoxLayout()
        self._storage_scan_btn = QPushButton("Scan storage")
        self._storage_scan_btn.clicked.connect(self._scan_storage)
        self._storage_purge_btn = QPushButton("Purge selected")
        self._storage_purge_btn.setEnabled(False)
        self._storage_purge_btn.clicked.connect(self._purge_storage)
        actions.addWidget(self._storage_scan_btn)
        actions.addWidget(self._storage_purge_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self._storage_status = QLabel("")
        self._storage_status.setWordWrap(True)
        self._storage_status.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._storage_status)
        return tab

    def _scan_storage(self) -> None:
        try:
            result = self._services.storage_scan()
        except Exception as exc:
            self._storage_status.setText("Scan failed: " + str(exc))
            return
        items = result.get("items") or []
        self._storage_table.setRowCount(len(items))
        for row, item in enumerate(items):
            category = QTableWidgetItem(str(item.get("category") or ""))
            category.setData(Qt.ItemDataRole.UserRole, item.get("id"))
            size = QTableWidgetItem(f"{int(item.get('bytes') or 0) / 1024 / 1024:.2f}")
            files = QTableWidgetItem(str(item.get("files") or 0))
            deletable = QTableWidgetItem("yes" if item.get("deletable") else "protected")
            self._storage_table.setItem(row, 0, category)
            self._storage_table.setItem(row, 1, size)
            self._storage_table.setItem(row, 2, files)
            self._storage_table.setItem(row, 3, deletable)
        self._storage_purge_btn.setEnabled(any(i.get("deletable") for i in items))
        self._storage_status.setText(
            f"{len(items)} categor(ies), "
            f"{int(result.get('total_bytes') or 0) / 1024 / 1024:.2f} MB total.")

    def _purge_storage(self) -> None:
        selected = set()
        for index in self._storage_table.selectionModel().selectedRows():
            item = self._storage_table.item(index.row(), 0)
            if item and item.data(Qt.ItemDataRole.UserRole):
                selected.add(str(item.data(Qt.ItemDataRole.UserRole)))
        if not selected:
            self._storage_status.setText("Select one or more storage rows first.")
            return
        answer = QMessageBox.question(
            self, "Purge selected storage",
            "Delete the selected temporary/build/backup categories permanently?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self._services.storage_purge(
                sorted(selected), confirm=True)
        except Exception as exc:
            self._storage_status.setText("Purge failed: " + str(exc))
            return
        self._storage_status.setText(
            f"Removed {len(result.get('removed') or [])} item(s), "
            f"{int(result.get('freed_bytes') or 0) / 1024 / 1024:.2f} MB freed.")
        self._scan_storage()


    def shutdown(self):
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.wait(30000)
        self._thread = None
        speech_thread = self._speech_thread
        if speech_thread is not None and speech_thread.isRunning():
            speech_thread.requestInterruption()
            speech_thread.wait(30000)
        self._speech_thread = None

    def refresh(self):
        if self._thread is not None and self._thread.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._status_label.setText("Discovering providers. Network calls run off the GUI thread.")
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        self._table.setRowCount(0)
        self._empty_label.setText("Discovering models.")
        self._empty_label.show()
        self._thread = ModelHubFetchThread(self._services, parent=self)
        self._thread.snapshot_ready.connect(self._on_snapshot)
        self._thread.failed.connect(self._on_error)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()
        self._refresh_speech_catalog()

    def _on_thread_finished(self):
        self._thread = None

    def _on_error(self, message: str):
        self._refresh_btn.setEnabled(True)
        self._table.setRowCount(0)
        self._empty_label.setText("Model discovery failed. Check provider settings and retry.")
        self._empty_label.show()
        self._status_label.setText(f"Model discovery failed: {message}")
        self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")

    def _on_snapshot(self, snapshot):
        self._snapshot = snapshot
        self._refresh_btn.setEnabled(True)
        self._update_provider_filter(snapshot)
        self._render_models()
        self._update_hardware(snapshot)
        self._update_storage(snapshot)
        total = len(snapshot.models)
        loaded = len(snapshot.loaded)
        if snapshot.reachable:
            text = f"{total} model(s) across {len(snapshot.providers)} provider(s); {loaded} loaded."
            if total == 0:
                text += " Start a provider or configure config/models.yaml."
            if snapshot.errors:
                text += " " + " ".join(snapshot.errors)
            self._status_label.setText(text)
            self._status_label.setStyleSheet("color: #55C58A; font-size: 12px;")
        else:
            detail = " ".join(snapshot.errors) or "No configured provider is reachable."
            self._status_label.setText(detail)
            self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")

    def _update_provider_filter(self, snapshot):
        current = self._provider_filter.currentData()
        self._provider_filter.blockSignals(True)
        self._provider_filter.clear()
        self._provider_filter.addItem("All providers", "")
        for provider in snapshot.providers:
            self._provider_filter.addItem(provider.label, provider.provider_id)
        index = self._provider_filter.findData(current)
        self._provider_filter.setCurrentIndex(index if index >= 0 else 0)
        self._provider_filter.blockSignals(False)

    def _render_models(self):
        if self._snapshot is None:
            return
        selected = self._provider_filter.currentData() or ""
        models = [
            model for model in self._snapshot.models
            if not selected or model.provider_id == selected
        ]
        self._table.setRowCount(len(models))
        for row, model in enumerate(models):
            self._table.setItem(row, 0, QTableWidgetItem(model.provider_label))
            self._table.setItem(row, 1, QTableWidgetItem(model.name))
            size = f"{model.size_gb:.2f}" if model.size_gb else "-"
            self._table.setItem(row, 2, QTableWidgetItem(size))
            status = QTableWidgetItem("Loaded" if model.loaded else "Available")
            if model.loaded:
                status.setForeground(Qt.GlobalColor.green)
            self._table.setItem(row, 3, status)
            self._table.setItem(row, 4, QTableWidgetItem(model.family or "-"))
            self._table.setItem(
                row, 5, QTableWidgetItem(", ".join(model.capabilities) or "-")
            )
        if models:
            self._empty_label.hide()
        else:
            self._empty_label.setText(
                "No models match this provider. Refresh or configure another provider."
            )
            self._empty_label.show()

    def _update_hardware(self, snapshot):
        self._loaded_value.setText(
            ", ".join(model.name for model in snapshot.loaded) or "No loaded models reported"
        )
        self._provider_value.setText(
            ", ".join(
                f"{provider.label} ({'online' if provider.reachable else 'offline'})"
                for provider in snapshot.providers
            ) or "No providers configured"
        )

    def _update_storage(self, snapshot):
        lines = [
            f"{provider.label}: {provider.base_url} - {len(provider.models)} model(s)"
            for provider in snapshot.providers
        ]
        self._storage_status.setText(
            "Provider endpoints:\n" + "\n".join(lines) if lines else "")

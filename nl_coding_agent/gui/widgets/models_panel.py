"""Model Hub - provider-agnostic model discovery and status."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
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


class ModelsPanel(QWidget):
    """Center panel for provider, model, speech, hardware and storage status."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._thread: ModelHubFetchThread | None = None
        self._snapshot = None

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

        subtitle = QLabel(
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
        self._tabs.setTabText(1, _tr("model_hub.tab_speech", "Speech"))
        self._tabs.setTabText(2, _tr("model_hub.tab_hardware", "Hardware"))
        self._tabs.setTabText(3, _tr("model_hub.tab_storage", "Storage"))

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

    def _build_speech_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        heading = QLabel("Speech and transcription engines")
        heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(heading)
        body = QLabel(
            "No speech engine is installed. The optional ASR Manager will support "
            "Qwen3-ASR, Faster-Whisper, WhisperX and Vosk without becoming a "
            "requirement for the coding engine. Model installation and transcription "
            "tests will be explicit user actions."
        )
        body.setWordWrap(True)
        body.setStyleSheet("color: #B8BECA; font-size: 12px;")
        layout.addWidget(body)
        layout.addStretch()
        return tab

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
            "Model files are owned and managed by their inference providers. "
            "A read-only space audit with ownership and actual sizes will be added "
            "before any cleanup action is offered."
        )
        self._storage_value.setWordWrap(True)
        self._storage_value.setStyleSheet("color: #B8BECA; font-size: 12px;")
        layout.addWidget(self._storage_value)
        self._storage_providers = QLabel("")
        self._storage_providers.setWordWrap(True)
        self._storage_providers.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._storage_providers)
        layout.addStretch()
        return tab

    def shutdown(self):
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.wait(30000)
        self._thread = None

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
        self._storage_providers.setText(
            "Provider endpoints:\n" + "\n".join(lines) if lines else ""
        )

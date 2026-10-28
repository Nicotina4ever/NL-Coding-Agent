"""Models panel — shows available and loaded Ollama models."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, QThread, Signal


class ModelFetchThread(QThread):
    models_ready = Signal(list, list)  # (all_models, loaded_models)

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services

    def run(self):
        try:
            models = self._services.list_models()
            loaded = self._services.list_loaded_models()
            self.models_ready.emit(models, loaded)
        except Exception:
            self.models_ready.emit([], [])


class ModelsPanel(QWidget):
    """Center panel for the Models page."""

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._thread: ModelFetchThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Ollama Models")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        self._status_label = QLabel("Checking Ollama…")
        self._status_label.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(self._status_label)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Name", "Size (GB)", "Loaded", "Family"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

        self.refresh()

    def refresh(self):
        self._status_label.setText("Fetching models…")
        self._table.setRowCount(0)
        if self._thread and self._thread.isRunning():
            return
        self._thread = ModelFetchThread(self._services, self)
        self._thread.models_ready.connect(self._on_models_ready)
        self._thread.start()

    def _on_models_ready(self, models: list, loaded: list):
        loaded_names = {m.name for m in loaded}
        self._table.setRowCount(len(models))
        for row, m in enumerate(models):
            self._table.setItem(row, 0, QTableWidgetItem(m.name))
            self._table.setItem(row, 1, QTableWidgetItem(f"{m.size_gb:.2f}"))
            loaded_text = "● Running" if m.name in loaded_names else ""
            loaded_item = QTableWidgetItem(loaded_text)
            if m.name in loaded_names:
                loaded_item.setForeground(Qt.GlobalColor.green)
            self._table.setItem(row, 2, loaded_item)
            self._table.setItem(row, 3, QTableWidgetItem(getattr(m, "family", "")))

        reachable = self._services.check_ollama()
        if reachable:
            self._status_label.setText(f"Ollama reachable — {len(models)} model(s) available, {len(loaded)} loaded")
            self._status_label.setStyleSheet("color: #55C58A; font-size: 12px;")
        else:
            self._status_label.setText("Ollama not reachable (degraded mode)")
            self._status_label.setStyleSheet("color: #E26472; font-size: 12px;")

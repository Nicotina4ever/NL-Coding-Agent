"""F3a: read-only problems panel (verification runs + project scan findings)."""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)


class _Signals(QObject):
    done = Signal(dict)


class _Task(QRunnable):
    def __init__(self, fn, signals):
        super().__init__()
        self._fn, self._signals = fn, signals

    def run(self):
        try:
            self._signals.done.emit(self._fn() or {})
        except Exception as exc:  # noqa: BLE001
            self._signals.done.emit({"problems": [], "counts": {},
                                     "error": str(exc)})


class ProblemsPanel(QWidget):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._project = None
        self._pool = QThreadPool.globalInstance()
        self._signals = _Signals()
        self._signals.done.connect(self._on_data)
        self.setAccessibleName("Problems and verification status")
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("PROBLEMS")
        title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        header.addWidget(title)
        self._counts = QLabel("No problems loaded")
        self._counts.setStyleSheet("color: #AB83C6;")
        header.addWidget(self._counts, 1)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setAccessibleName("Refresh problems")
        self._refresh_btn.setToolTip("Read-only verification + project scan refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)
        self._status = QLabel("Read-only: failed verification runs and bounded project scan findings.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Severity", "Source", "Message"])
        self._table.setAccessibleName("Problems table")
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table, 1)

    def set_project(self, project):
        self._project = dict(project) if project else None
        if project:
            self.refresh()
        else:
            self._table.setRowCount(0)
            self._counts.setText("No problems loaded")
            self._status.setText("Open a project to inspect verification/test status.")

    def set_lsp_diagnostics(self, findings) -> None:
        """Merge read-only language-server diagnostics into the current table."""
        self._lsp_rows = list(findings or [])
        self._render_problems(self._lsp_rows)

    def _render_problems(self, lsp_rows=None) -> None:
        rows = list(lsp_rows if lsp_rows is not None else self._lsp_rows or [])
        if not rows:
            return
        existing = getattr(self, "_last_rows", [])
        merged = existing + rows if existing else rows
        self._last_rows = merged
        self._table.setRowCount(0)
        for row in merged:
            index = self._table.rowCount()
            self._table.insertRow(index)
            for column, value in enumerate((row.get("severity"), row.get("source"),
                                            row.get("message"))):
                from PySide6.QtWidgets import QTableWidgetItem
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(value or ""))
                self._table.setItem(index, column, item)
        self._counts.setText(str(len(merged)) + " finding(s) including LSP diagnostics")
        self._status.setText("Read-only findings loaded (verification + scan + LSP).")

    def refresh(self):
        if not self._project:
            self._status.setText("Open a project to inspect verification/test status.")
            return
        self._status.setText("Scanning (read-only)…")
        project = self._project
        self._pool.start(_Task(
            lambda: self._services.project_problems(project.get("id"), project["root"]),
            self._signals))

    @Slot(dict)
    def _on_data(self, data):
        problems = list(data.get("problems") or [])
        self._table.setRowCount(0)
        for row in problems:
            index = self._table.rowCount()
            self._table.insertRow(index)
            for column, value in enumerate((row.get("severity"), row.get("source"),
                                            row.get("message"))):
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(value or ""))
                self._table.setItem(index, column, item)
        counts = data.get("counts") or {}
        self._counts.setText(str(len(problems)) + " finding(s) — errors "
                             + str(counts.get("errors", 0)) + ", warnings "
                             + str(counts.get("warnings", 0)))
        if not problems:
            self._status.setText("No problems found (verification runs + project scan).")
        else:
            self._status.setText("Read-only findings loaded. Nothing was modified.")

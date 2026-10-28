"""F3a: read-only Git status/branch/diff/log panel (explicit refresh)."""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QTabWidget, QPlainTextEdit, QVBoxLayout, QWidget)


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
            self._signals.done.emit({"ok": False, "error": str(exc)})


class GitPanel(QWidget):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._project = None
        self._pool = QThreadPool.globalInstance()
        self._signals = _Signals()
        self._signals.done.connect(self._on_data)
        self.setAccessibleName("Read-only Git panel")
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("GIT")
        title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        header.addWidget(title)
        self._branch = QLabel("No repository loaded")
        self._branch.setStyleSheet("color: #AB83C6;")
        header.addWidget(self._branch, 1)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setAccessibleName("Refresh read-only git data")
        self._refresh_btn.setToolTip("Explicit refresh of branch/status/diff/log (read-only)")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)
        self._status = QLabel("Read-only: status, branch, diff and log. "
                              "No commit/push/reset/checkout is available.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._changes = QListWidget()
        self._changes.setAccessibleName("Git working tree changes")
        layout.addWidget(self._changes, 1)
        self._tabs = QTabWidget()
        self._diff = QPlainTextEdit()
        self._diff.setReadOnly(True)
        self._diff.setAccessibleName("Working tree diff")
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setAccessibleName("Recent Git log")
        self._tabs.addTab(self._diff, "Diff")
        self._tabs.addTab(self._log, "Log")
        layout.addWidget(self._tabs, 2)

    def set_project(self, project):
        self._project = dict(project) if project else None
        if project:
            self.refresh()
        else:
            self._branch.setText("No repository loaded")
            self._changes.clear()
            self._diff.clear()
            self._log.clear()
            self._status.setText("Open a project to inspect its repository.")

    def refresh(self):
        if not self._project:
            self._status.setText("Open a project to inspect its repository.")
            return
        self._status.setText("Loading Git data (read-only)…")
        root = self._project["root"]
        self._pool.start(_Task(lambda: {
            "status": self._services.git_status(root),
            "diff": self._services.git_diff(root),
            "log": self._services.git_log(root),
        }, self._signals))

    @Slot(dict)
    def _on_data(self, data):
        status = dict(data.get("status") or {})
        if not status.get("ok"):
            self._status.setText("Git unavailable: " + str(status.get("error")
                                                           or status.get("error_code")))
            return
        self._branch.setText("Branch: " + str(status.get("branch") or "(detached)")
                             + "  Last: " + str(status.get("last_commit") or "—"))
        self._changes.clear()
        for change in status.get("changes") or []:
            self._changes.addItem(str(change.get("code")) + "  " + str(change.get("path")))
        if not status.get("changes"):
            self._changes.addItem("(clean working tree)")
        diff = dict(data.get("diff") or {})
        log = dict(data.get("log") or {})
        self._diff.setPlainText(diff.get("diff") or "(no unstaged diff)")
        self._log.setPlainText(log.get("log") or "(no log)")
        self._status.setText("Read-only Git data refreshed. No destructive operation was executed.")

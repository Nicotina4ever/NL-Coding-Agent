"""F3a: terminal with explicit human execution, EXECUTE policy, non-blocking QProcess."""
from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)


class _Signals(QObject):
    result = Signal(dict)


class _RunTask(QRunnable):
    def __init__(self, fn, signals):
        super().__init__()
        self._fn, self._signals = fn, signals

    def run(self):
        try:
            self._signals.result.emit(self._fn() or {})
        except Exception as exc:  # noqa: BLE001 - surfaced as error state
            self._signals.result.emit({"ok": False, "error_code": "execution-failed",
                                       "error": str(exc), "stdout": "", "stderr": ""})


class TerminalPanel(QWidget):
    """Human-only command surface: policy-checked, shell-free, audited."""

    def __init__(self, services, parent=None, *, runner=None):
        super().__init__(parent)
        self._services = services
        self._runner = runner
        self._project = None
        self._process = None
        self._pool = QThreadPool.globalInstance()
        self._signals = _Signals()
        self._signals.result.connect(self._on_result)
        self.setAccessibleName("Project terminal")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("TERMINAL")
        title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        header.addWidget(title)
        self._cwd_label = QLabel("No project open")
        self._cwd_label.setStyleSheet("color: #AB83C6;")
        header.addWidget(self._cwd_label, 1)
        layout.addLayout(header)
        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Command (argument vector, no shell)…")
        self._input.setAccessibleName("Terminal command")
        self._input.setToolTip("Runs as an argument vector without a shell; "
                               "destructive/network commands are refused by policy.")
        self._input.returnPressed.connect(self.run_command)
        row.addWidget(self._input, 1)
        self._run_btn = QPushButton("Run")
        self._run_btn.setAccessibleName("Run terminal command")
        self._run_btn.setToolTip("Run the explicit human command (Ctrl+Enter)")
        self._run_btn.clicked.connect(self.run_command)
        row.addWidget(self._run_btn)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setAccessibleName("Clear terminal output")
        self._clear_btn.clicked.connect(lambda: self._output.clear())
        row.addWidget(self._clear_btn)
        layout.addLayout(row)
        self._status = QLabel("Explicit human commands only. No model executes terminal commands.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setObjectName("terminalOutput")
        self._output.setAccessibleName("Terminal output")
        layout.addWidget(self._output, 1)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.run_command)

    def set_project(self, project):
        self._project = dict(project) if project else None
        self._cwd_label.setText("cwd: " + (self._project or {}).get("root", "no project"))
        self._status.setText("Explicit human commands only; policy-checked."
                             if project else "Open a project to use the terminal.")

    def run_command(self, argv=None, *, cwd_rel="."):
        if not self._project:
            self._status.setText("Open a project before running commands.")
            return
        command = argv if argv is not None else self._input.text().strip()
        if not command:
            self._status.setText("Enter a command first.")
            return
        parts = command if isinstance(command, list) else None
        try:
            import shlex
            parts = parts or shlex.split(command)
        except ValueError as exc:
            self._status.setText("Invalid command: " + str(exc))
            return
        policy = self._services.terminal_policy(self._project.get("id"), parts)
        if not policy["allowed"]:
            self._status.setText("Refused (" + str(policy.get("error_code")) + "): "
                                 + str(policy.get("reason")))
            self._output.appendPlainText("REFUSED: " + str(policy.get("reason")))
            return
        self._status.setText("Running: " + " ".join(parts))
        root = self._project["root"]
        if self._runner is not None:
            self._pool.start(_RunTask(
                lambda: self._runner(parts, root, cwd_rel), self._signals))
            return
        # Non-blocking QProcess path (no shell, cwd scoped to the project).
        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(root))
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read_process)
        self._process.finished.connect(self._process_finished)
        self._process.start(parts[0], parts[1:])

    def _read_process(self):
        if self._process is not None:
            self._output.insertPlainText(
                bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace"))

    def _process_finished(self, code, _status):
        if self._process is not None:
            self._read_process()
            self._status.setText("Finished with exit code " + str(code) + " (audited).")
            self._process = None

    @Slot(dict)
    def _on_result(self, result):
        if not result.get("ok") and result.get("error"):
            self._output.appendPlainText("ERROR " + str(result.get("error_code")) + ": "
                                         + str(result.get("error")))
        if result.get("stdout"):
            self._output.appendPlainText(str(result["stdout"]).rstrip())
        if result.get("stderr"):
            self._output.appendPlainText(str(result["stderr"]).rstrip())
        self._status.setText("Exit code " + str(result.get("exit_code"))
                             + " (audited in SQLite events).")

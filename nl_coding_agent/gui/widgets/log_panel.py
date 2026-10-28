"""Log / event stream panel."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel, QPushButton
from PySide6.QtCore import Qt, QMetaObject, Q_ARG, Slot
from PySide6.QtGui import QTextCursor, QColor


LEVEL_COLORS = {
    "info":    "#B8BECA",
    "warning": "#E6B85C",
    "error":   "#E26472",
    "debug":   "#7E8798",
}


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


class LogPanel(QWidget):
    """Bottom log / event stream panel. Thread-safe via invokeMethod."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        header = QHBoxLayout()
        self._title = QLabel(_tr("log.title", "Logs"))
        lbl = self._title
        lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #7E8798;")
        header.addWidget(lbl)
        header.addStretch()
        self._clear_btn = QPushButton(_tr("log.clear", "Clear"))
        clear_btn = self._clear_btn
        clear_btn.setFixedSize(48, 20)
        clear_btn.setStyleSheet("font-size: 10px; padding: 1px 4px;")
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self._output = QPlainTextEdit()
        self._output.setObjectName("logOutput")
        self._output.setReadOnly(True)
        self._output.setMaximumBlockCount(2000)
        layout.addWidget(self._output)
        _register_retranslate(self)

    def retranslate(self) -> None:
        self._title.setText(_tr("log.title", "Logs"))
        self._clear_btn.setText(_tr("log.clear", "Clear"))

    @Slot(str, str, str)
    def append_log(self, source: str, level: str, message: str) -> None:
        """Append a log line. Safe to call from any thread."""
        if not self._is_main_thread():
            QMetaObject.invokeMethod(
                self, "append_log",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, source),
                Q_ARG(str, level),
                Q_ARG(str, message),
            )
            return
        color = LEVEL_COLORS.get(level, "#B8BECA")
        line = f'<span style="color:{color};">[{source}/{level}] {message}</span>'
        self._output.appendHtml(line)
        self._output.moveCursor(QTextCursor.MoveOperation.End)

    def _clear(self):
        self._output.clear()

    def _is_main_thread(self) -> bool:
        from PySide6.QtCore import QThread
        return QThread.currentThread() is self.thread()

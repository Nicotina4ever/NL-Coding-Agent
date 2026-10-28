"""Autonomy panel - start/stop/pause/resume the persistent supervisor (C3d).

The panel is a thin, non-blocking view over AppServices.supervisor_*: buttons
only enqueue/command, a QTimer polls lightweight status/queue snapshots, and no
supervisor policy or blocking wait lives in the widget.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

_MODES = [("Off", "off"), ("Assisted", "assisted"), ("Automatic", "automatic")]
_ACTIVE_STATUSES = {
    "running", "starting", "paused", "waiting_for_resources",
    "waiting_for_approval", "stopping", "recovering", "blocked",
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


class AutonomyPanel(QWidget):
    """Minimal autonomous-development controls backed by the supervisor service."""

    status_changed = Signal(dict)

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._project: dict | None = None
        self._last_status: dict = {}
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._title = QLabel(_tr(
            "autonomy.title", "Autonomy status (read-only)"))
        title = self._title
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        self._subtitle = QLabel(_tr(
            "autonomy.subtitle",
            "Read-only supervisor status and mission queue. Mode, limits and Pause/Stop "
            "live under Settings > Advanced; nothing starts automatically. Off is the "
            "default; cloud/network/delete still require explicit permission grants."))
        subtitle = self._subtitle
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #7E8798; font-size: 12px;")
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)

        self._mode_combo = QComboBox()
        for label, value in _MODES:
            self._mode_combo.addItem(label, value)
        self._mode_combo.setCurrentIndex(0)
        form.addRow("Mode", self._mode_combo)

        self._missions_spin = QSpinBox()
        self._missions_spin.setRange(1, 5)
        self._missions_spin.setValue(1)
        form.addRow("Missions per run", self._missions_spin)

        self._attempts_spin = QSpinBox()
        self._attempts_spin.setRange(1, 5)
        self._attempts_spin.setValue(2)
        form.addRow("Attempts per requirement", self._attempts_spin)

        buttons = QHBoxLayout()
        self._start_btn = QPushButton(_tr("autonomy.start", "Start"))
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.clicked.connect(self._start)
        self._pause_btn = QPushButton(_tr("autonomy.pause", "Pause"))
        self._pause_btn.clicked.connect(self._pause)
        self._resume_btn = QPushButton(_tr("autonomy.resume", "Resume"))
        self._resume_btn.clicked.connect(self._resume)
        self._stop_btn = QPushButton(_tr("autonomy.stop", "Stop"))
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.clicked.connect(self._stop)
        for button in (self._start_btn, self._pause_btn, self._resume_btn, self._stop_btn):
            buttons.addWidget(button)
        buttons.addStretch()

        # User-facing self-build controls live only under Settings > Advanced
        # (NL-BP-023). This page is a read-only status view; the widgets remain as
        # hidden attributes so the established service contract/tests stay valid.
        self._controls_container = QWidget()
        controls_layout = QVBoxLayout(self._controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addLayout(form)
        controls_layout.addLayout(buttons)
        self._controls_container.setVisible(False)
        layout.addWidget(self._controls_container)
        self._controls_pointer = QLabel(
            "Self-build controls are under Settings > Advanced; nothing starts automatically. "
            "This page shows read-only supervisor status and the mission queue."
        )
        self._controls_pointer.setWordWrap(True)
        self._controls_pointer.setStyleSheet("font-size: 12px; color: #AB83C6;")
        layout.addWidget(self._controls_pointer)

        self._status_label = QLabel(_tr(
            "autonomy.supervisor_idle", "Supervisor: idle"))
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-size: 12px; color: #AB83C6;")
        layout.addWidget(self._status_label)

        self._notice_label = QLabel("")
        self._notice_label.setWordWrap(True)
        self._notice_label.setStyleSheet("font-size: 12px; color: #7E8798;")
        layout.addWidget(self._notice_label)

        self._queue_table = QTableWidget(0, 5)
        self._queue_table.setHorizontalHeaderLabels([
            _tr("autonomy.header_requirement", "Requirement"),
            _tr("autonomy.header_state", "State"),
            _tr("autonomy.header_priority", "Priority"),
            _tr("autonomy.header_attempts", "Attempts"),
            _tr("autonomy.header_mission", "Mission")])
        self._queue_table.verticalHeader().setVisible(False)
        self._queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._queue_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._queue_table, 1)
        _register_retranslate(self)

    def retranslate(self) -> None:
        self._title.setText(_tr(
            "autonomy.title", "Autonomy status (read-only)"))
        self._subtitle.setText(_tr(
            "autonomy.subtitle",
            "Read-only supervisor status and mission queue. Mode, limits and Pause/Stop "
            "live under Settings > Advanced; nothing starts automatically. Off is the "
            "default; cloud/network/delete still require explicit permission grants."))
        self._start_btn.setText(_tr("autonomy.start", "Start"))
        self._pause_btn.setText(_tr("autonomy.pause", "Pause"))
        self._resume_btn.setText(_tr("autonomy.resume", "Resume"))
        self._stop_btn.setText(_tr("autonomy.stop", "Stop"))
        self._queue_table.setHorizontalHeaderLabels([
            _tr("autonomy.header_requirement", "Requirement"),
            _tr("autonomy.header_state", "State"),
            _tr("autonomy.header_priority", "Priority"),
            _tr("autonomy.header_attempts", "Attempts"),
            _tr("autonomy.header_mission", "Mission")])

    # ----------------------------------------------------------------- project

    def set_project(self, project: dict | None) -> None:
        self._project = project
        if not project:
            self._status_label.setText(_tr(
                "autonomy.no_project", "Supervisor: no project open"))
        self._update_controls()
        self.refresh()

    def set_mode(self, mode: str) -> None:
        for index in range(self._mode_combo.count()):
            if self._mode_combo.itemData(index) == mode:
                self._mode_combo.setCurrentIndex(index)
                return

    def _project_id(self) -> int | None:
        if self._project and self._project.get("id") is not None:
            return int(self._project["id"])
        return None

    # ----------------------------------------------------------------- actions

    def _start(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            self._notice_label.setText("Open a project before starting the supervisor.")
            return
        mode = str(self._mode_combo.currentData() or "off")
        try:
            result = self._services.supervisor_start(
                project_id, mode=mode, max_missions=self._missions_spin.value(),
            )
        except Exception as exc:
            self._notice_label.setText("Start failed: " + str(exc))
            return
        if result.get("ok"):
            self._notice_label.setText(
                "Supervisor run scheduled in the background (" + mode + ")."
            )
        else:
            self._notice_label.setText(str(result.get("reason") or "Supervisor is busy."))
        self.refresh()

    def _pause(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            return
        try:
            result = self._services.supervisor_pause(project_id)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        self._notice_label.setText(
            "Pause requested - honoured at the mission boundary."
            if result.get("ok", True) else "Pause failed: " + str(result.get("error"))
        )
        self.refresh()

    def _resume(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            return
        try:
            result = self._services.supervisor_resume(project_id)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        self._notice_label.setText(
            "Resume requested." if result.get("ok", True)
            else "Resume failed: " + str(result.get("error"))
        )
        self.refresh()

    def _stop(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            return
        try:
            result = self._services.supervisor_stop(project_id, reason="operator stop")
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        self._notice_label.setText(
            "Stop requested - the current mission reaches a safe state first."
            if result.get("ok", True) else "Stop failed: " + str(result.get("error"))
        )
        self.refresh()

    # ----------------------------------------------------------------- refresh

    def _update_controls(self) -> None:
        project_id = self._project_id()
        enabled = project_id is not None
        for button in (self._start_btn, self._pause_btn,
                       self._resume_btn, self._stop_btn):
            button.setEnabled(enabled)

    def refresh(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            self._update_controls()
            return
        status: dict = {}
        try:
            status = self._services.supervisor_status(project_id) or {}
        except Exception as exc:
            status = {"status": "unknown", "error": str(exc)}
        self._last_status = status
        run = status.get("run") or {}
        run_status = str(run.get("status") or status.get("status") or "idle")
        service = status.get("service") or {}
        lease = status.get("lease")
        queue_counts = status.get("queue_counts") or {}
        queue_text = ", ".join(
            key + " " + str(value) for key, value in sorted(queue_counts.items())
        ) or "empty"
        self._status_label.setText(
            "Supervisor: " + run_status
            + (" (background thread running)" if service.get("thread_running") else "")
            + "  |  queue: " + queue_text
            + ("  |  lease: " + str(lease.get("owner_id")) + " until "
               + str(lease.get("expires_at")) if lease else "")
        )
        try:
            queue = self._services.supervisor_queue(project_id) or []
        except Exception:
            queue = []
        self._queue_table.setRowCount(len(queue))
        for row, item in enumerate(queue):
            values = [
                str(item.get("requirement_id") or "-"),
                str(item.get("state") or "-"),
                str(item.get("priority") or "-"),
                str(item.get("attempts") or 0),
                ("#" + str(item.get("mission_id")))
                if item.get("mission_id") is not None else "-",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setToolTip(str(item.get("goal") or ""))
                self._queue_table.setItem(row, column, cell)
        self._start_btn.setEnabled(project_id is not None)
        self._stop_btn.setEnabled(
            project_id is not None and (
                bool(service.get("thread_running")) or run_status.lower() in _ACTIVE_STATUSES
            )
        )
        self.status_changed.emit(status)

    def shutdown(self) -> None:
        self._timer.stop()

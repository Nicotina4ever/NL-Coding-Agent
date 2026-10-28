"""Main application window."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QMessageBox, QStackedWidget, QStatusBar,
    QPushButton, QFrame, QSizePolicy, QTabWidget,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtSvgWidgets import QSvgWidget

from nl_coding_agent.app.services import AppServices, Event, get_event_bus
from nl_coding_agent.gui.i18n import get_i18n, tr_for
from nl_coding_agent.gui.widgets.sidebar import SidebarWidget
from nl_coding_agent.gui.widgets.log_panel import LogPanel
from nl_coding_agent.gui.widgets.projects_panel import ProjectsPanel
from nl_coding_agent.gui.widgets.inspector_panel import InspectorPanel
from nl_coding_agent.gui.widgets.models_panel import ModelsPanel
from nl_coding_agent.gui.widgets.file_viewer import FileViewerWidget
from nl_coding_agent.gui.widgets.task_board import TaskBoardWidget
from nl_coding_agent.gui.widgets.agents_panel import AgentsPanel
from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel
from nl_coding_agent.gui.widgets.autonomy_panel import AutonomyPanel
from nl_coding_agent.gui.widgets.research_panel import ResearchPanel
from nl_coding_agent.gui.widgets.goals_panel import GoalsPanel
from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
from nl_coding_agent.gui.widgets.editor_panel import EditorPanel
from nl_coding_agent.gui.widgets.terminal_panel import TerminalPanel
from nl_coding_agent.gui.widgets.git_panel import GitPanel
from nl_coding_agent.gui.widgets.problems_panel import ProblemsPanel
from nl_coding_agent.gui.widgets.command_palette import CommandAction, CommandPalette


_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "LogoMio.svg"


class OllamaCheckThread(QThread):
    result_ready = Signal(bool)

    def __init__(self, services: AppServices, parent=None):
        super().__init__(parent)
        self._services = services

    def run(self):
        self.result_ready.emit(self._services.check_ollama())


class AuditThread(QThread):
    done = Signal(dict)

    def __init__(self, services: AppServices, project_id: int, parent=None):
        super().__init__(parent)
        self._services = services
        self._project_id = project_id

    def run(self):
        try:
            task_id = self._services.run_audit(self._project_id)
            self.done.emit({"status": "scheduled", "task_id": task_id})
        except Exception as e:
            self.done.emit({"status": "error", "error": str(e)})


_ACTIVE_SUPERVISOR_STATUSES = {
    "running", "starting", "paused", "waiting_for_resources",
    "waiting_for_approval", "stopping", "recovering",
}


class EmergencyControls(QWidget):
    """Always-reachable, cooperative Pause/Stop for an active supervisor run.

    NL-BP-024: the widget lives in the main-window status bar (outside Settings),
    is visible only while a supervisor run/mission is active, and only forwards the
    existing backend command (no process kill, no wait). Stop always asks for
    confirmation. The backend persists the command and honours it at safe mission
    boundaries, so the GUI never claims an immediate kill.
    """

    message = Signal(str, str)  # (level, text)

    def __init__(self, services, parent=None, *, translator=None):
        super().__init__(parent)
        self._services = services
        self._i18n = translator
        self._project: dict | None = None
        self._active = False
        self._last_status = None

        self.setObjectName("emergencyControls")
        self.setAccessibleName("Active mission emergency pause and stop controls")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._status_label = QLabel(tr_for(
            self._i18n, "emergency.idle", "Supervisor: idle"))
        self._status_label.setObjectName("supervisorLabel")
        self._status_label.setAccessibleName("Active supervisor status")

        self._pause_btn = QPushButton(tr_for(
            self._i18n, "emergency.pause", "Pause"))
        self._pause_btn.setObjectName("secondaryButton")
        self._pause_btn.setAccessibleName("Emergency pause of the active mission")
        self._pause_btn.setToolTip(tr_for(
            self._i18n, "emergency.pause_tooltip",
            "Cooperative pause at the next safe mission boundary; external processes "
            "are never killed (Ctrl+Alt+P)."))
        self._pause_btn.setEnabled(False)
        self._pause_btn.clicked.connect(self.request_pause)

        self._stop_btn = QPushButton(tr_for(
            self._i18n, "emergency.stop", "STOP"))
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setAccessibleName("Emergency stop of the active mission")
        self._stop_btn.setToolTip(tr_for(
            self._i18n, "emergency.stop_tooltip",
            "Request a cooperative stop; confirmation required; the current mission "
            "reaches a safe state first and external processes are never killed "
            "(Ctrl+Alt+S)."))
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.request_stop)

        layout.addWidget(self._status_label)
        layout.addWidget(self._pause_btn)
        layout.addWidget(self._stop_btn)
        self.setVisible(False)

    # ---------------------------------------------------------------- state

    def _project_id(self) -> int | None:
        if self._project and self._project.get("id") is not None:
            return int(self._project["id"])
        return None

    def is_active(self) -> bool:
        return bool(self._active)

    def set_project(self, project: dict | None) -> None:
        self._project = project
        if project is None:
            self.update_status(None)

    def update_status(self, status: dict | None) -> bool:
        """Apply one supervisor status snapshot; returns True when a run is active."""
        if not self._project or not status:
            self._active = False
            self._status_label.setText(tr_for(
                self._i18n, "emergency.idle", "Supervisor: idle"))
            self._pause_btn.setEnabled(False)
            self._stop_btn.setEnabled(False)
            self.setVisible(False)
            return False
        run = status.get("run") or {}
        service = status.get("service") or {}
        label = str(run.get("status") or status.get("status") or "idle").strip() or "idle"
        active = bool(service.get("thread_running")) or label.lower() in _ACTIVE_SUPERVISOR_STATUSES
        self._active = bool(active)
        self._last_status = status
        self._status_label.setText(tr_for(
            self._i18n, "emergency.supervisor_prefix", "Supervisor: ") + label)
        self._status_label.setToolTip(str(status.get("resume_command") or ""))
        self._pause_btn.setEnabled(active)
        self._stop_btn.setEnabled(active)
        self.setVisible(active)
        return self._active

    def retranslate(self) -> None:
        self._pause_btn.setText(tr_for(
            self._i18n, "emergency.pause", "Pause"))
        self._stop_btn.setText(tr_for(
            self._i18n, "emergency.stop", "STOP"))
        self._pause_btn.setToolTip(tr_for(
            self._i18n, "emergency.pause_tooltip",
            "Cooperative pause at the next safe mission boundary; external processes "
            "are never killed (Ctrl+Alt+P)."))
        self._stop_btn.setToolTip(tr_for(
            self._i18n, "emergency.stop_tooltip",
            "Request a cooperative stop; confirmation required; the current mission "
            "reaches a safe state first and external processes are never killed "
            "(Ctrl+Alt+S)."))
        if self._last_status is not None:
            self.update_status(self._last_status)
        else:
            self._status_label.setText(tr_for(
                self._i18n, "emergency.idle", "Supervisor: idle"))

    # -------------------------------------------------------------- commands

    def _active_project_id(self) -> int | None:
        return self._project_id() if self._active else None

    def request_pause(self) -> dict:
        project_id = self._active_project_id()
        if project_id is None:
            result = {"ok": False, "error": tr_for(
                self._i18n, "emergency.no_active_pause",
                "No active mission or supervisor run to pause.")}
            self.message.emit("info", result["error"])
            return result
        try:
            result = self._services.supervisor_pause(project_id) or {}
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            result = {"ok": False, "error": str(exc)}
        if result.get("ok", True):
            self._status_label.setText(tr_for(
                self._i18n, "emergency.pausing", "Supervisor: pausing…"))
            self.message.emit(
                "info",
                tr_for(self._i18n, "emergency.pause_requested",
                       "Pause requested - honoured at the next safe mission boundary."),
            )
        else:
            self.message.emit(
                "warning",
                tr_for(self._i18n, "emergency.pause_failed", "Pause failed: ")
                + str(result.get("error") or result.get("reason")
                      or tr_for(self._i18n, "common.unknown_error", "unknown error")),
            )
        return result

    def request_stop(self, *, confirm: bool | None = None) -> dict:
        project_id = self._active_project_id()
        if project_id is None:
            result = {"ok": False, "error": tr_for(
                self._i18n, "emergency.no_active_stop",
                "No active mission or supervisor run to stop.")}
            self.message.emit("info", result["error"])
            return result
        if confirm is None:
            answer = QMessageBox.question(
                self,
                tr_for(self._i18n, "emergency.stop_title", "Emergency stop"),
                tr_for(self._i18n, "emergency.stop_body",
                       "Stop the active supervisor run?\n\n"
                       "The command is cooperative: the current mission reaches a safe state "
                       "first, state is persisted, and external processes are never killed."),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            confirm = answer == QMessageBox.StandardButton.Yes
        if not confirm:
            self.message.emit("info", tr_for(
                self._i18n, "emergency.stop_cancelled",
                "Emergency stop cancelled."))
            return {"ok": False, "cancelled": True}
        try:
            result = self._services.supervisor_stop(
                project_id, reason="emergency stop from main window",
            ) or {}
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            result = {"ok": False, "error": str(exc)}
        if result.get("ok", True):
            self._status_label.setText(tr_for(
                self._i18n, "emergency.stopping", "Supervisor: stopping…"))
            self.message.emit(
                "warning",
                tr_for(self._i18n, "emergency.stop_requested",
                       "Emergency stop requested - the current mission reaches a safe state "
                       "first; external processes are not killed."),
            )
        else:
            self.message.emit(
                "warning",
                tr_for(self._i18n, "emergency.stop_failed",
                       "Emergency stop failed: ")
                + str(result.get("error")
                      or tr_for(self._i18n, "common.unknown_error",
                                "unknown error")),
            )
        return result


class MainWindow(QMainWindow):
    def __init__(self, services: AppServices):
        super().__init__()
        self._services = services
        self._current_project: dict | None = None
        self._ollama_thread: OllamaCheckThread | None = None
        self._audit_thread: AuditThread | None = None
        self._closing = False
        self._i18n = get_i18n(services)
        try:
            self._i18n.install()
        except Exception:
            pass
        self._i18n.language_changed.connect(self._retranslate_ui)

        self.setWindowTitle(tr_for(self._i18n, "app.window_title",
                                   "NL Coding Agent"))
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        if _LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(_LOGO_PATH)))

        self._build_ui()
        self._connect_event_bus()

        # Start Ollama check (stoppable single-shot, not a bare singleShot)
        self._initial_ollama_timer = QTimer(self)
        self._initial_ollama_timer.setSingleShot(True)
        self._initial_ollama_timer.timeout.connect(self._check_ollama)
        self._initial_ollama_timer.start(500)
        # Periodic Ollama status refresh
        self._ollama_timer = QTimer(self)
        self._ollama_timer.timeout.connect(self._check_ollama)
        self._ollama_timer.start(30_000)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Header bar ──────────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("headerBar")
        header.setFixedHeight(44)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 16, 0)
        header_layout.setSpacing(8)

        # Logo
        if _LOGO_PATH.exists():
            logo = QSvgWidget(str(_LOGO_PATH))
            logo.setFixedSize(28, 28)
            header_layout.addWidget(logo)
        else:
            logo_lbl = QLabel("NL")
            logo_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #7531FE;")
            header_layout.addWidget(logo_lbl)

        self._app_title = QLabel(tr_for(
            self._i18n, "app.header_title", "NL CODING AGENT"))
        self._app_title.setObjectName("appTitle")
        header_layout.addWidget(self._app_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #343947;")
        header_layout.addWidget(sep)

        self._project_label = QLabel(tr_for(
            self._i18n, "app.no_project", "No project open"))
        self._project_label.setObjectName("projectLabel")
        self._project_label.setAccessibleName("Opened project")
        self._project_label.setMaximumWidth(310)
        header_layout.addWidget(self._project_label)
        self._activity_state = "idle"
        self._activity_detail = tr_for(
            self._i18n, "activity.no_active", "No active mission")
        self._activity_mission_title = ""
        self._activity_label = QLabel(
            tr_for(self._i18n, "activity.idle", "IDLE") + " · "
            + self._activity_detail)
        self._activity_label.setMaximumWidth(250)
        self._activity_label.setObjectName("nlActivityBadge")
        self._activity_label.setProperty("state", "idle")
        self._activity_label.setAccessibleName("Studio activity and current mission")
        header_layout.addWidget(self._activity_label)

        self._autonomy_btn = QPushButton(tr_for(
            self._i18n, "app.autonomy_status", "Autonomy status"))
        self._autonomy_btn.setObjectName("autonomyButton")
        self._autonomy_btn.setToolTip(
            "Read-only autonomy status; self-build controls live under Settings > Advanced"
        )
        self._autonomy_btn.clicked.connect(lambda: self._switch_page("autonomy"))
        header_layout.addWidget(self._autonomy_btn)

        header_layout.addStretch()

        self._ollama_label = QLabel("Ollama ●")
        self._ollama_label.setObjectName("ollamaStatus")
        self._ollama_label.setProperty("reachable", "false")
        self._ollama_label.setToolTip(tr_for(
            self._i18n, "app.ollama_status", "Ollama status"))
        header_layout.addWidget(self._ollama_label)

        root_layout.addWidget(header)

        # ── Main area (sidebar + center + inspector) ─────────────────────────
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        # Sidebar
        self._sidebar = SidebarWidget(translator=self._i18n)
        self._sidebar.page_changed.connect(self._switch_page)
        main_splitter.addWidget(self._sidebar)

        # Center stacked widget
        self._stack = QStackedWidget()
        self._stack.setObjectName("mainWorkspace")

        self._projects_panel = ProjectsPanel(
            services=self._services, translator=self._i18n)
        self._projects_panel.project_opened.connect(self._on_project_opened)
        self._projects_panel.audit_requested.connect(self._on_audit_requested)
        self._stack.addWidget(self._projects_panel)  # index 0 = projects

        self._files_panel = FileViewerWidget(services=self._services)
        self._files_panel.file_opened.connect(self._on_file_opened)
        self._stack.addWidget(self._files_panel)  # index 1 = files

        self._tasks_panel = TaskBoardWidget(services=self._services)
        self._tasks_panel.mission_selected.connect(self._on_mission_selected)
        self._tasks_panel.mission_finished.connect(self._on_mission_finished)
        self._stack.addWidget(self._tasks_panel)  # index 2 = tasks

        self._agents_panel = AgentsPanel(services=self._services)
        self._stack.addWidget(self._agents_panel)  # index 3 = agents

        self._settings_panel = SettingsPanel(
            services=self._services, translator=self._i18n)
        self._stack.addWidget(self._settings_panel)  # index 4 = settings

        # Models page
        self._models_panel = ModelsPanel(services=self._services)
        self._stack.addWidget(self._models_panel)

        # Autonomous development page
        self._autonomy_panel = AutonomyPanel(services=self._services)
        self._stack.addWidget(self._autonomy_panel)

        # Multimodal mission chat (F1): local attachment pipeline + explicit submit.
        self._chat_panel = ChatPanel(services=self._services)
        self._chat_panel.submitted.connect(self._on_chat_submitted)
        self._stack.addWidget(self._chat_panel)  # index 7 = chat

        # Studio IDE (F3a): editor / terminal / read-only Git / problems.
        self._editor_panel = EditorPanel(self._services)
        self._terminal_panel = TerminalPanel(self._services)
        self._git_panel = GitPanel(self._services)
        self._problems_panel = ProblemsPanel(self._services)
        self._ide_tabs = QTabWidget()
        self._ide_tabs.setObjectName("ideTabs")
        self._ide_tabs.setAccessibleName("Studio IDE tabs")
        self._ide_tabs.addTab(self._editor_panel, "Editor")
        self._ide_tabs.addTab(self._terminal_panel, "Terminal")
        self._ide_tabs.addTab(self._git_panel, "Git")
        self._ide_tabs.addTab(self._problems_panel, "Problems")
        self._stack.addWidget(self._ide_tabs)  # index 8 = IDE

        # Studio Research workspace (R5): explicit search/intake only.
        self._research_panel = ResearchPanel(self._services)
        self._stack.addWidget(self._research_panel)  # index 9 = research

        # Goals workspace (G4): project-scoped plans, no autonomous execution.
        self._goals_panel = GoalsPanel(self._services)
        self._stack.addWidget(self._goals_panel)  # index 10 = goals

        main_splitter.addWidget(self._stack)

        # Inspector panel
        self._inspector = InspectorPanel(translator=self._i18n)
        main_splitter.addWidget(self._inspector)

        main_splitter.setSizes([180, 760, 300])
        self._inspector.setMinimumWidth(268)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setStretchFactor(2, 0)

        # ── Vertical splitter (main area + log panel) ─────────────────────────
        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.setChildrenCollapsible(False)
        v_splitter.addWidget(main_splitter)

        self._log_panel = LogPanel()
        v_splitter.addWidget(self._log_panel)
        v_splitter.setSizes([580, 150])
        v_splitter.setStretchFactor(0, 1)
        v_splitter.setStretchFactor(1, 0)

        root_layout.addWidget(v_splitter)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = QStatusBar()
        sb.setObjectName("statusBar")
        self.setStatusBar(sb)
        self._vram_label = QLabel(tr_for(self._i18n, "status.vram", "VRAM: —"))
        self._vram_label.setObjectName("vramLabel")
        self._ram_label = QLabel(tr_for(self._i18n, "status.ram", "RAM: —"))
        self._ram_label.setObjectName("ramLabel")
        self._tasks_label = QLabel(tr_for(self._i18n, "status.tasks", "Tasks: 0"))
        self._tasks_label.setObjectName("tasksLabel")
        self._emergency_controls = EmergencyControls(
            self._services, translator=self._i18n)
        self._emergency_controls.message.connect(self._on_emergency_message)
        self._emergency_widget = self._emergency_controls
        # Compatibility aliases: the label/buttons now live inside the
        # always-reachable emergency widget (outside Settings, NL-BP-024).
        self._supervisor_label = self._emergency_controls._status_label
        self._pause_supervisor_btn = self._emergency_controls._pause_btn
        self._stop_supervisor_btn = self._emergency_controls._stop_btn
        sb.addPermanentWidget(self._vram_label)
        sb.addPermanentWidget(self._ram_label)
        sb.addPermanentWidget(self._tasks_label)
        sb.addPermanentWidget(self._emergency_controls)

        self._supervisor_timer = QTimer(self)
        self._supervisor_timer.timeout.connect(self._update_supervisor_status)
        self._supervisor_timer.start(5_000)
        QTimer.singleShot(1500, self._update_supervisor_status)

        # Global emergency shortcuts; both handlers fail closed when nothing is active.
        self._emergency_pause_shortcut = QShortcut(
            QKeySequence("Ctrl+Alt+P"), self,
            activated=self._emergency_controls.request_pause,
        )
        self._emergency_stop_shortcut = QShortcut(
            QKeySequence("Ctrl+Alt+S"), self,
            activated=self._emergency_controls.request_stop,
        )

        # Resource timer
        self._res_timer = QTimer(self)
        self._res_timer.timeout.connect(self._update_resources)
        self._res_timer.start(5000)
        QTimer.singleShot(1000, self._update_resources)

        # Page key → stack index map (autonomy page is reachable from the header and
        # from Settings > Autonomous Development; the sidebar keeps its six pages).
        self._page_index = {
            "projects": 0,
            "files":    1,
            "tasks":    2,
            "agents":   3,
            "settings": 4,
            "models":   5,
            "autonomy": 6,
            "chat":     7,
            "ide":      8,
            "research": 9,
            "goals":    10,
        }
        self._settings_panel.autonomy_requested.connect(
            lambda: self._switch_page("autonomy")
        )
        # Command-palette stub: visible affordance for the F3b palette.
        QShortcut(QKeySequence("Ctrl+Shift+P"), self,
                  activated=self._show_command_palette)

    def _retranslate_ui(self, _language: str | None = None) -> None:
        self.setWindowTitle(tr_for(
            self._i18n, "app.window_title", "NL Coding Agent"))
        self._app_title.setText(tr_for(
            self._i18n, "app.header_title", "NL CODING AGENT"))
        if not self._current_project:
            self._project_label.setText(tr_for(
                self._i18n, "app.no_project", "No project open"))
        self._autonomy_btn.setText(tr_for(
            self._i18n, "app.autonomy_status", "Autonomy status"))
        self._autonomy_btn.setToolTip(tr_for(
            self._i18n, "app.autonomy_tooltip",
            "Read-only autonomy status; self-build controls live under Settings > Advanced"))
        self._ollama_label.setToolTip(tr_for(
            self._i18n, "app.ollama_status", "Ollama status"))
        if hasattr(self, "_emergency_controls"):
            self._emergency_controls.retranslate()
        if hasattr(self, "_activity_label"):
            if self._activity_state == "idle":
                detail = tr_for(
                    self._i18n, "activity.no_active", "No active mission")
            else:
                detail = tr_for(
                    self._i18n, "activity.current_mission",
                    "Current mission: {title}",
                    title=(self._activity_mission_title or "—"))
            self._set_activity(self._activity_state, detail)
        self._sidebar.retranslate()
        self._projects_panel.retranslate()
        self._settings_panel.retranslate()
        self._inspector.retranslate()
        if hasattr(self, "_ide_tabs") and self._ide_tabs is not None:
            for index, key, default in (
                    (0, "ide.editor", "Editor"),
                    (1, "ide.terminal", "Terminal"),
                    (2, "ide.git", "Git"),
                    (3, "ide.problems", "Problems")):
                self._ide_tabs.setTabText(
                    index, tr_for(self._i18n, key, default))
        # Keep the empty-state status labels translated; runtime values remain.
        if self._vram_label.text() in ("VRAM: —", "VRAM:"):
            self._vram_label.setText(tr_for(self._i18n, "status.vram", "VRAM: —"))
        if self._ram_label.text() in ("RAM: —", "RAM:"):
            self._ram_label.setText(tr_for(self._i18n, "status.ram", "RAM: —"))
        if self._tasks_label.text() in ("Tasks: 0", "Attività: 0"):
            self._tasks_label.setText(tr_for(
                self._i18n, "status.tasks", "Tasks: 0"))

    def _command_palette_actions(self):
        """Safe actions only: open/project navigation/refresh/settings/read-only doctor."""
        actions = []
        pages = [("projects", "Projects"), ("files", "Files"), ("tasks", "Tasks"),
                 ("chat", "Mission Chat"), ("ide", "Studio IDE"),
                 ("research", "Research"), ("goals", "Goals"),
                 ("settings", "Settings"), ("autonomy", "Autonomy")]
        for key, label in pages:
            target = tr_for(self._i18n, "sidebar." + key, label)
            actions.append(CommandAction(
                "page-" + key,
                tr_for(self._i18n, "command_palette.switch_to",
                       "Switch to {target}", target=target),
                (lambda k=key: self._switch_page(k)),
                category="navigation"))
        actions.append(CommandAction(
            "open-project",
            tr_for(self._i18n, "command_palette.open_project",
                   "Open project…"),
            lambda: self._switch_page("projects"), shortcut="", category="project"))
        actions.append(CommandAction(
            "refresh-ide",
            tr_for(self._i18n, "command_palette.refresh_ide",
                   "Refresh IDE panels"),
            self._refresh_ide_panels, category="refresh"))
        actions.append(CommandAction(
            "doctor",
            tr_for(self._i18n, "command_palette.doctor",
                   "Run read-only doctor"),
            self._run_readonly_doctor,
            category="diagnostics"))
        try:
            debug = self._services.debug_status()
            available = bool(debug.get("available"))
        except Exception:
            available = False
        actions.append(CommandAction(
            "debug-start",
            tr_for(self._i18n, "command_palette.debug_start",
                   "Start debug session"),
            None, enabled=False,
            disabled_reason=(
                tr_for(self._i18n, "command_palette.no_debugger",
                       "no local debugger detected (F3b adapter interface only)")
                if not available else
                tr_for(self._i18n, "command_palette.no_debug_adapter",
                       "explicit debug adapter not configured")),
            category="debug"))
        try:
            servers = self._services.lsp_catalog()
            lsp_available = any(server.get("available") for server in servers)
        except Exception:
            lsp_available = False
        actions.append(CommandAction(
            "lsp-diagnostics",
            tr_for(self._i18n, "command_palette.lsp",
                   "Refresh LSP diagnostics"),
            lambda: self.statusBar().showMessage(tr_for(
                self._i18n, "status.lsp_unavailable",
                "LSP diagnostics require an installed local server; none started silently."), 6000),
            enabled=lsp_available,
            disabled_reason=tr_for(
                self._i18n, "command_palette.no_lsp",
                "no local language server detected"),
            category="diagnostics"))
        return actions

    def _refresh_ide_panels(self):
        if not self._current_project:
            self.statusBar().showMessage(tr_for(
                self._i18n, "status.open_project_first",
                "Open a project first."), 4000)
            return
        self._git_panel.refresh()
        self._problems_panel.refresh()

    def _run_readonly_doctor(self):
        try:
            settings = self._services.get_runtime_settings()
            summary = tr_for(
                self._i18n, "status.doctor_summary",
                "doctor: database={path}",
                path=str(settings.get("database_path")))
        except Exception as exc:
            summary = tr_for(
                self._i18n, "status.doctor_unavailable",
                "doctor: unavailable ({error})", error=str(exc))
        read_only = tr_for(self._i18n, "status.read_only_prefix", "Read-only ")
        self.statusBar().showMessage(read_only + summary, 8000)
        self._log_panel.append_log(
            "doctor", "info",
            tr_for(self._i18n, "status.doctor_log",
                   "Read-only doctor: {summary}", summary=summary))

    def _show_command_palette(self):
        palette = CommandPalette(self._command_palette_actions(), self)
        palette.triggered.connect(lambda action_id: self._log_panel.append_log(
            "palette", "info", tr_for(
                self._i18n, "status.command_log", "Command: {id}",
                id=str(action_id))))
        palette.exec()

    def _connect_event_bus(self):
        bus = get_event_bus()
        bus.subscribe(self._on_bus_event)

    def _on_bus_event(self, event: Event):
        self._log_panel.append_log(event.source, event.level, event.message)

    @Slot(str)
    def _switch_page(self, key: str):
        idx = self._page_index.get(key, 0)
        self._stack.setCurrentIndex(idx)
        if key == "models":
            self._models_panel.refresh()
        elif key == "files":
            self._files_panel.refresh()
        elif key == "tasks":
            self._tasks_panel.refresh()
        elif key == "agents":
            self._agents_panel.refresh()
        elif key == "settings":
            self._settings_panel.refresh()
        elif key == "autonomy":
            self._autonomy_panel.refresh()
        elif key == "research":
            self._research_panel.on_page_shown()
        elif key == "goals":
            self._goals_panel.on_page_shown()

    @Slot(dict)
    def _on_project_opened(self, project: dict):
        self._current_project = project
        self._project_label.setText(tr_for(
            self._i18n, "activity.opened", "Opened: {name}",
            name=str(project["name"])))
        self._projects_panel.set_opened_project(project)
        self._set_activity("idle", tr_for(
            self._i18n, "activity.no_active", "No active mission"))
        facts = self._services.get_project_facts(project["id"])
        self._inspector.show_project(project, facts)
        self._files_panel.set_project(project)
        self._tasks_panel.set_project(project)
        self._settings_panel.set_project(project)
        self._autonomy_panel.set_project(project)
        self._chat_panel.set_project(project)
        self._editor_panel.set_project(project)
        self._terminal_panel.set_project(project)
        self._git_panel.set_project(project)
        self._problems_panel.set_project(project)
        self._research_panel.set_project(project)
        self._goals_panel.set_project(project)
        self._update_supervisor_status()
        self._log_panel.append_log(
            "projects", "info",
            tr_for(self._i18n, "status.project_opened_log",
                   "Project opened: {name}", name=str(project["name"])))

    @Slot(str)
    def _on_file_opened(self, rel_path: str):
        content = None
        if self._current_project:
            try:
                content = self._services.read_project_file(
                    self._current_project["root"], rel_path,
                )
            except Exception as exc:
                content = f"[unreadable] {exc}"
        self._inspector.show_file(rel_path, content)
        if self._current_project:
            self._editor_panel.set_project(self._current_project)
            self._editor_panel.open_file(rel_path)
        self._log_panel.append_log(
            "files", "info",
            tr_for(self._i18n, "status.file_opened_log",
                   "Opened file: {path}", path=rel_path))

    @Slot(dict)
    def _on_chat_submitted(self, payload: dict):
        """Persist a chat mission + attachment provenance; never starts a model run."""
        if not self._current_project:
            self._log_panel.append_log(
                "chat", "warning",
                tr_for(self._i18n, "status.open_project_mission",
                       "Open a project before submitting a mission."))
            return
        text = str(payload.get("text") or "").strip()
        attachment_ids = [int(item) for item in payload.get("attachment_ids") or []
                          if item is not None]
        title = (text[:60] if text else "Mission with attachments") or "Mission"
        goal = text or "Review the attached files and describe the requested change."
        try:
            mission_id = self._services.create_mission(
                self._current_project["id"], title, goal)
            if attachment_ids:
                self._services.attach_attachments_to_mission(
                    mission_id, attachment_ids)
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            self._log_panel.append_log(
                "chat", "error",
                tr_for(self._i18n, "status.mission_submit_failed",
                       "Mission submit failed: ") + str(exc))
            return
        self._tasks_panel.refresh()
        self._switch_page("tasks")
        self.statusBar().showMessage(tr_for(
            self._i18n, "status.mission_created",
            "Mission #{mission_id} created with {count} attachment(s)",
            mission_id=str(mission_id), count=str(len(attachment_ids))), 6000)
        self._log_panel.append_log(
            "chat", "info",
            tr_for(self._i18n, "status.mission_created_log",
                   "Mission #{mission_id} created from chat with {count} "
                   "attachment(s) (no model run).",
                   mission_id=str(mission_id), count=str(len(attachment_ids))))

    @Slot(int)
    def _on_mission_selected(self, mission_id: int):
        details = self._services.get_mission_details(mission_id)
        if details:
            self._inspector.show_mission(details)

    @Slot(dict)
    def _on_mission_finished(self, result: dict):
        mission_id = result.get("mission_id")
        status = result.get("status", "unknown")
        self._log_panel.append_log(
            "orchestrator", "info" if status == "completed" else "warning",
            tr_for(self._i18n, "status.mission_finished_log",
                   "Mission #{mission_id} finished: {status}",
                   mission_id=str(mission_id), status=str(status)),
        )
        self._tasks_panel.refresh()
        if mission_id:
            details = self._services.get_mission_details(mission_id)
            if details:
                self._inspector.show_mission(details)

    @Slot(int)
    def _on_audit_requested(self, project_id: int):
        if self._audit_thread and self._audit_thread.isRunning():
            self._log_panel.append_log(
                "audit", "warning",
                tr_for(self._i18n, "status.audit_running",
                       "Audit already running, please wait."))
            return
        self._log_panel.append_log(
            "audit", "info",
            tr_for(self._i18n, "status.audit_starting",
                   "Starting audit for project id={project_id}…",
                   project_id=str(project_id)))
        self._services.run_audit(project_id)

    def _check_ollama(self):
        if self._closing:
            return
        if self._ollama_thread and self._ollama_thread.isRunning():
            return
        self._ollama_thread = OllamaCheckThread(self._services, self)
        self._ollama_thread.result_ready.connect(self._on_ollama_result)
        self._ollama_thread.start()

    @Slot(bool)
    def _on_ollama_result(self, reachable: bool):
        self._ollama_label.setProperty("reachable", "true" if reachable else "false")
        self._ollama_label.setText(tr_for(
            self._i18n, "status.ollama_reachable" if reachable
            else "status.ollama_unreachable",
            "Ollama ●" if reachable else "Ollama ○"))
        # Force style refresh (Qt property-based styling needs this)
        self._ollama_label.style().unpolish(self._ollama_label)
        self._ollama_label.style().polish(self._ollama_label)
        if reachable:
            self._ollama_label.setStyleSheet("color: #55C58A; font-size: 12px;")
        else:
            self._ollama_label.setStyleSheet("color: #E26472; font-size: 12px;")

    def _update_resources(self):
        try:
            import psutil
            ram = psutil.virtual_memory()
            used_gb = ram.used / 1e9
            total_gb = ram.total / 1e9
            self._ram_label.setText(tr_for(
                self._i18n, "status.ram_usage", "RAM: {used}/{total} GB",
                used=f"{used_gb:.1f}", total=f"{total_gb:.0f}"))
        except Exception:
            self._ram_label.setText(tr_for(
                self._i18n, "status.ram", "RAM: —"))

        try:
            import subprocess
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0 and r.stdout.strip():
                used, total = r.stdout.strip().split(",")
                used_gb = int(used.strip()) / 1024
                total_gb = int(total.strip()) / 1024
                self._vram_label.setText(tr_for(
                    self._i18n, "status.vram_usage",
                    "VRAM: {used}/{total} GB",
                    used=f"{used_gb:.1f}", total=f"{total_gb:.0f}"))
            else:
                self._vram_label.setText(tr_for(
                    self._i18n, "status.vram", "VRAM: —"))
        except Exception:
            self._vram_label.setText(tr_for(
                self._i18n, "status.vram", "VRAM: —"))

        # Tasks count
        from nl_coding_agent.resources.scheduler import get_scheduler
        scheduler = get_scheduler()
        running = sum(1 for t in scheduler.list_tasks() if t.status == "running")
        pending = sum(1 for t in scheduler.list_tasks() if t.status == "pending")
        self._tasks_label.setText(tr_for(
            self._i18n, "status.tasks_count",
            "Tasks: {running} running, {pending} pending",
            running=str(running), pending=str(pending)))

    def _update_supervisor_status(self):
        if self._closing:
            return
        project = self._current_project
        if not project:
            self._emergency_controls.set_project(None)
            return
        self._emergency_controls.set_project(project)
        try:
            status = self._services.supervisor_status(int(project["id"])) or {}
        except Exception:
            status = {}
        self._emergency_controls.update_status(status)
        run = status.get("run") or {}
        run_status = str(run.get("status") or status.get("status") or "idle").lower()
        mission = run.get("mission") or status.get("mission") or {}
        mission_title = str(mission.get("title") or run.get("mission_title")
                            or status.get("mission_title") or "")
        if run_status in ("running", "active", "starting"):
            self._activity_mission_title = mission_title
            self._set_activity("running", tr_for(
                self._i18n, "activity.current_mission",
                "Current mission: {title}", title=(mission_title or "—")))
        elif run_status in ("blocked", "failed", "interrupted", "error"):
            self._activity_mission_title = mission_title
            self._set_activity("blocked", tr_for(
                self._i18n, "activity.current_mission",
                "Current mission: {title}", title=(mission_title or "—")))
        elif run_status in ("paused", "pausing"):
            self._activity_mission_title = mission_title
            self._set_activity("paused", tr_for(
                self._i18n, "activity.current_mission",
                "Current mission: {title}", title=(mission_title or "—")))
        else:
            self._activity_mission_title = ""
            self._set_activity("idle", tr_for(
                self._i18n, "activity.no_active", "No active mission"))

    def _set_activity(self, state: str, detail: str = "") -> None:
        """Unambiguous selected/opened activity label in the Studio header."""
        if not hasattr(self, "_activity_label"):
            return
        state = str(state or "idle").lower()
        self._activity_state = state
        self._activity_detail = str(detail or "")
        state_key = {"running": "activity.running",
                     "blocked": "activity.blocked",
                     "paused": "activity.paused",
                     "idle": "activity.idle"}.get(state, "activity.idle")
        state_label = tr_for(self._i18n, state_key, state.upper())
        label = state_label + (" · " + self._activity_detail
                               if self._activity_detail else "")
        self._activity_label.setText(label)
        self._activity_label.setProperty("state", state)
        self._activity_label.setToolTip(detail)
        self._activity_label.style().unpolish(self._activity_label)
        self._activity_label.style().polish(self._activity_label)

    @Slot(str, str)
    def _on_emergency_message(self, level: str, text: str) -> None:
        self.statusBar().showMessage(text, 8000)
        self._log_panel.append_log("supervisor", level, text)

    @Slot()
    def _emergency_pause_supervisor(self):
        return self._emergency_controls.request_pause()

    @Slot()
    def _emergency_stop_supervisor(self):
        return self._emergency_controls.request_stop()

    def _stop_threads(self):
        self._closing = True
        self._initial_ollama_timer.stop()
        self._ollama_timer.stop()
        self._res_timer.stop()
        self._supervisor_timer.stop()
        for panel in (self._models_panel, self._agents_panel, self._research_panel):
            shutdown = getattr(panel, "shutdown", None)
            if shutdown:
                shutdown()
        for attr in ("_ollama_thread", "_audit_thread"):
            thread = getattr(self, attr, None)
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
                thread.wait(10000)
            setattr(self, attr, None)
        shutdown = getattr(self._services, "shutdown_supervisors", None)
        if shutdown:
            try:
                shutdown()
            except Exception:
                pass
        autonomy_shutdown = getattr(self._autonomy_panel, "shutdown", None)
        if autonomy_shutdown:
            autonomy_shutdown()

    def closeEvent(self, event):
        from PySide6.QtCore import QCoreApplication
        from nl_coding_agent.app.services import get_event_bus
        self._stop_threads()
        QCoreApplication.processEvents()
        get_event_bus().unsubscribe(self._on_bus_event)
        event.accept()

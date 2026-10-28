"""Main application window."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QStackedWidget, QStatusBar,
    QPushButton, QFrame, QSizePolicy, QTabWidget,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtSvgWidgets import QSvgWidget

from nl_coding_agent.app.services import AppServices, Event, get_event_bus
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


class MainWindow(QMainWindow):
    def __init__(self, services: AppServices):
        super().__init__()
        self._services = services
        self._current_project: dict | None = None
        self._ollama_thread: OllamaCheckThread | None = None
        self._audit_thread: AuditThread | None = None
        self._closing = False

        self.setWindowTitle("NL Coding Agent")
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

        app_title = QLabel("NL CODING AGENT")
        app_title.setObjectName("appTitle")
        header_layout.addWidget(app_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #343947;")
        header_layout.addWidget(sep)

        self._project_label = QLabel("No project open")
        self._project_label.setObjectName("projectLabel")
        header_layout.addWidget(self._project_label)

        self._autonomy_btn = QPushButton("Autonomy")
        self._autonomy_btn.setObjectName("autonomyButton")
        self._autonomy_btn.setToolTip("Persistent autonomous supervisor controls")
        self._autonomy_btn.clicked.connect(lambda: self._switch_page("autonomy"))
        header_layout.addWidget(self._autonomy_btn)

        header_layout.addStretch()

        self._ollama_label = QLabel("Ollama ●")
        self._ollama_label.setObjectName("ollamaStatus")
        self._ollama_label.setProperty("reachable", "false")
        self._ollama_label.setToolTip("Ollama status")
        header_layout.addWidget(self._ollama_label)

        root_layout.addWidget(header)

        # ── Main area (sidebar + center + inspector) ─────────────────────────
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        # Sidebar
        self._sidebar = SidebarWidget()
        self._sidebar.page_changed.connect(self._switch_page)
        main_splitter.addWidget(self._sidebar)

        # Center stacked widget
        self._stack = QStackedWidget()
        self._stack.setObjectName("mainWorkspace")

        self._projects_panel = ProjectsPanel(services=self._services)
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

        self._settings_panel = SettingsPanel(services=self._services)
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

        main_splitter.addWidget(self._stack)

        # Inspector panel
        self._inspector = InspectorPanel()
        main_splitter.addWidget(self._inspector)

        main_splitter.setSizes([180, 780, 260])
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
        self._vram_label = QLabel("VRAM: —")
        self._vram_label.setObjectName("vramLabel")
        self._ram_label = QLabel("RAM: —")
        self._ram_label.setObjectName("ramLabel")
        self._tasks_label = QLabel("Tasks: 0")
        self._tasks_label.setObjectName("tasksLabel")
        self._supervisor_label = QLabel("Supervisor: idle")
        self._supervisor_label.setObjectName("supervisorLabel")
        self._stop_supervisor_btn = QPushButton("STOP")
        self._stop_supervisor_btn.setObjectName("dangerButton")
        self._stop_supervisor_btn.setToolTip("Emergency stop: current mission reaches a safe state first")
        self._stop_supervisor_btn.setEnabled(False)
        self._stop_supervisor_btn.clicked.connect(self._emergency_stop_supervisor)
        sb.addPermanentWidget(self._vram_label)
        sb.addPermanentWidget(self._ram_label)
        sb.addPermanentWidget(self._tasks_label)
        sb.addPermanentWidget(self._supervisor_label)
        sb.addPermanentWidget(self._stop_supervisor_btn)

        self._supervisor_timer = QTimer(self)
        self._supervisor_timer.timeout.connect(self._update_supervisor_status)
        self._supervisor_timer.start(10_000)
        QTimer.singleShot(1500, self._update_supervisor_status)

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
        }
        self._settings_panel.autonomy_requested.connect(
            lambda: self._switch_page("autonomy")
        )
        # Command-palette stub: visible affordance for the F3b palette.
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence("Ctrl+Shift+P"), self,
                  activated=self._show_command_palette)

    def _command_palette_actions(self):
        """Safe actions only: open/project navigation/refresh/settings/read-only doctor."""
        actions = []
        pages = [("projects", "Projects"), ("files", "Files"), ("tasks", "Tasks"),
                 ("chat", "Mission Chat"), ("ide", "Studio IDE"),
                 ("settings", "Settings"), ("autonomy", "Autonomy")]
        for key, label in pages:
            actions.append(CommandAction("page-" + key, "Switch to " + label,
                                         (lambda k=key: self._switch_page(k)),
                                         category="navigation"))
        actions.append(CommandAction(
            "open-project", "Open project…",
            lambda: self._switch_page("projects"), shortcut="", category="project"))
        actions.append(CommandAction(
            "refresh-ide", "Refresh IDE panels",
            self._refresh_ide_panels, category="refresh"))
        actions.append(CommandAction(
            "doctor", "Run read-only doctor", self._run_readonly_doctor,
            category="diagnostics"))
        try:
            debug = self._services.debug_status()
            available = bool(debug.get("available"))
        except Exception:
            available = False
        actions.append(CommandAction(
            "debug-start", "Start debug session",
            None, enabled=False,
            disabled_reason=("no local debugger detected (F3b adapter interface only)"
                             if not available else
                             "explicit debug adapter not configured"),
            category="debug"))
        try:
            servers = self._services.lsp_catalog()
            lsp_available = any(server.get("available") for server in servers)
        except Exception:
            lsp_available = False
        actions.append(CommandAction(
            "lsp-diagnostics", "Refresh LSP diagnostics",
            lambda: self.statusBar().showMessage(
                "LSP diagnostics require an installed local server; none started silently.", 6000),
            enabled=lsp_available,
            disabled_reason="no local language server detected",
            category="diagnostics"))
        return actions

    def _refresh_ide_panels(self):
        if not self._current_project:
            self.statusBar().showMessage("Open a project first.", 4000)
            return
        self._git_panel.refresh()
        self._problems_panel.refresh()

    def _run_readonly_doctor(self):
        try:
            settings = self._services.get_runtime_settings()
            summary = "doctor: database=" + str(settings.get("database_path"))
        except Exception as exc:
            summary = "doctor: unavailable (" + str(exc) + ")"
        self.statusBar().showMessage("Read-only " + summary, 8000)
        self._log_panel.append_log("doctor", "info", "Read-only doctor: " + summary)

    def _show_command_palette(self):
        palette = CommandPalette(self._command_palette_actions(), self)
        palette.triggered.connect(lambda action_id: self._log_panel.append_log(
            "palette", "info", "Command: " + str(action_id)))
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

    @Slot(dict)
    def _on_project_opened(self, project: dict):
        self._current_project = project
        self._project_label.setText(project["name"])
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
        self._update_supervisor_status()
        self._log_panel.append_log("projects", "info", f"Project opened: {project['name']}")

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
        self._log_panel.append_log("files", "info", f"Opened file: {rel_path}")

    @Slot(dict)
    def _on_chat_submitted(self, payload: dict):
        """Persist a chat mission + attachment provenance; never starts a model run."""
        if not self._current_project:
            self._log_panel.append_log(
                "chat", "warning", "Open a project before submitting a mission.")
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
            self._log_panel.append_log("chat", "error",
                                       "Mission submit failed: " + str(exc))
            return
        self._tasks_panel.refresh()
        self._switch_page("tasks")
        self.statusBar().showMessage(
            "Mission #" + str(mission_id) + " created with "
            + str(len(attachment_ids)) + " attachment(s)", 6000)
        self._log_panel.append_log(
            "chat", "info",
            "Mission #" + str(mission_id) + " created from chat with "
            + str(len(attachment_ids)) + " attachment(s) (no model run).")

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
            f"Mission #{mission_id} finished: {status}",
        )
        self._tasks_panel.refresh()
        if mission_id:
            details = self._services.get_mission_details(mission_id)
            if details:
                self._inspector.show_mission(details)

    @Slot(int)
    def _on_audit_requested(self, project_id: int):
        if self._audit_thread and self._audit_thread.isRunning():
            self._log_panel.append_log("audit", "warning", "Audit already running, please wait.")
            return
        self._log_panel.append_log("audit", "info", f"Starting audit for project id={project_id}…")
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
        self._ollama_label.setText("Ollama ●" if reachable else "Ollama ○")
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
            self._ram_label.setText(f"RAM: {used_gb:.1f}/{total_gb:.0f} GB")
        except Exception:
            self._ram_label.setText("RAM: —")

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
                self._vram_label.setText(f"VRAM: {used_gb:.1f}/{total_gb:.0f} GB")
            else:
                self._vram_label.setText("VRAM: —")
        except Exception:
            self._vram_label.setText("VRAM: —")

        # Tasks count
        from nl_coding_agent.resources.scheduler import get_scheduler
        scheduler = get_scheduler()
        running = sum(1 for t in scheduler.list_tasks() if t.status == "running")
        pending = sum(1 for t in scheduler.list_tasks() if t.status == "pending")
        self._tasks_label.setText(f"Tasks: {running} running, {pending} pending")

    def _update_supervisor_status(self):
        if self._closing:
            return
        project = self._current_project
        if not project:
            self._supervisor_label.setText("Supervisor: idle")
            self._stop_supervisor_btn.setEnabled(False)
            return
        try:
            status = self._services.supervisor_status(int(project["id"])) or {}
        except Exception:
            status = {}
        run = status.get("run") or {}
        service = status.get("service") or {}
        label = str(run.get("status") or status.get("status") or "idle")
        self._supervisor_label.setText("Supervisor: " + label)
        active = bool(service.get("thread_running")) or label.lower() in {
            "running", "starting", "paused", "waiting_for_resources",
            "waiting_for_approval", "stopping", "recovering",
        }
        self._stop_supervisor_btn.setEnabled(active)
        self._supervisor_label.setToolTip(str(status.get("resume_command") or ""))

    @Slot()
    def _emergency_stop_supervisor(self):
        project = self._current_project
        if not project:
            return
        try:
            result = self._services.supervisor_stop(
                int(project["id"]), reason="emergency stop from main window",
            )
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        self._log_panel.append_log(
            "supervisor", "warning",
            "Emergency stop requested."
            if result.get("ok", True) else "Emergency stop failed: " + str(result.get("error")),
        )
        self._update_supervisor_status()

    def _stop_threads(self):
        self._closing = True
        self._initial_ollama_timer.stop()
        self._ollama_timer.stop()
        self._res_timer.stop()
        self._supervisor_timer.stop()
        for panel in (self._models_panel, self._agents_panel):
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

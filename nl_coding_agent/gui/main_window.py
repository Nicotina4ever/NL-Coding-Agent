"""Main application window."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QStackedWidget, QStatusBar,
    QPushButton, QFrame, QSizePolicy,
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


_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "LogoMio.svg"
_PLACEHOLDER_PAGES = ["files", "tasks", "agents", "settings"]


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

        self.setWindowTitle("NL Coding Agent")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        if _LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(_LOGO_PATH)))

        self._build_ui()
        self._connect_event_bus()

        # Start Ollama check
        QTimer.singleShot(500, self._check_ollama)
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

        for _ in _PLACEHOLDER_PAGES:
            placeholder = QLabel("Coming soon…")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #7E8798; font-size: 14px;")
            self._stack.addWidget(placeholder)

        # Models page (last)
        self._models_panel = ModelsPanel(services=self._services)
        self._stack.addWidget(self._models_panel)

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
        sb.addPermanentWidget(self._vram_label)
        sb.addPermanentWidget(self._ram_label)
        sb.addPermanentWidget(self._tasks_label)

        # Resource timer
        self._res_timer = QTimer(self)
        self._res_timer.timeout.connect(self._update_resources)
        self._res_timer.start(5000)
        QTimer.singleShot(1000, self._update_resources)

        # Page key → stack index map
        self._page_index = {
            "projects": 0,
            "files":    1,
            "tasks":    2,
            "agents":   3,
            "settings": 4,
            "models":   5,
        }

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

    @Slot(dict)
    def _on_project_opened(self, project: dict):
        self._current_project = project
        self._project_label.setText(project["name"])
        facts = self._services.get_project_facts(project["id"])
        self._inspector.show_project(project, facts)
        self._log_panel.append_log("projects", "info", f"Project opened: {project['name']}")

    @Slot(int)
    def _on_audit_requested(self, project_id: int):
        if self._audit_thread and self._audit_thread.isRunning():
            self._log_panel.append_log("audit", "warning", "Audit already running, please wait.")
            return
        self._log_panel.append_log("audit", "info", f"Starting audit for project id={project_id}…")
        self._services.run_audit(project_id)

    def _check_ollama(self):
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

    def closeEvent(self, event):
        from nl_coding_agent.app.services import get_event_bus
        get_event_bus().unsubscribe(self._on_bus_event)
        event.accept()

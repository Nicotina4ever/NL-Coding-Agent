"""Studio Research workspace (stage 7 R5, NL-BP-210).

Read-only research UI. Every research action is delegated to an injected research
service reached through AppServices; the panel never imports a network client,
SQLite, CrewAI or a model runtime. Search/preview/intake run on a QThreadPool and
all content is rendered as untrusted data. No credentials are displayed, and no
research starts when the app opens or the page is constructed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPlainTextEdit, QPushButton, QSplitter,
                               QTabWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

_CRED_RE = re.compile(
    r"(?i)\b(authorization|api[_-]?key|token|secret|password)\b\s*[:=]\s*\S+")
_UNTRUSTED = "UNTRUSTED"
_KINDS = ("Auto-detect", "Web URL", "GitHub repo", "Hugging Face model",
          "Local attachment")


def _redact(value: Any) -> str:
    text = str(value if value is not None else "")
    return _CRED_RE.sub(lambda m: m.group(1) + "=[redacted]", text)


def _dict(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        try:
            return dict(as_dict())
        except Exception:  # noqa: BLE001 - display fallback only
            return {}
    return {}


class _Signals(QObject):
    done = Signal(dict)


class _Task(QRunnable):
    def __init__(self, fn, signals: _Signals):
        super().__init__()
        self._fn, self._signals = fn, signals

    def run(self):
        try:
            self._signals.done.emit(_dict(self._fn()) or {"ok": True})
        except Exception as exc:  # noqa: BLE001 - shown as deterministic UI state
            self._signals.done.emit({"ok": False, "error": _redact(exc)})


class _ResearchAdapter:
    """Duck-typed bridge to AppServices.research; no backend imports."""

    def __init__(self, services):
        self._services = services
        candidates = []
        for attr in ("research", "research_service"):
            value = getattr(services, attr, None)
            if value is not None:
                candidates.append(value)
        candidates.append(services)
        self._targets = candidates

    def method(self, *names):
        for target in self._targets:
            for name in names:
                fn = getattr(target, name, None)
                if callable(fn):
                    return fn
        return None

    def status(self):
        fn = self.method("research_status", "status")
        return fn() if fn is not None else None

    def provider_statuses(self):
        fn = self.method("provider_statuses", "providers", "research_provider_statuses")
        if fn is None:
            return []
        return fn() or []

    def search(self, query: str, provider_id: str | None):
        fn = self.method("search", "research_search")
        if fn is None:
            return {"ok": False, "offline": True,
                    "error": "Research service is unavailable."}
        return fn(query, provider_id)

    def preview(self, url: str):
        fn = self.method("preview", "preview_source", "research_preview")
        return fn(url) if fn is not None else None

    def history(self, project_id, mission_id):
        fn = self.method("history", "research_history")
        return fn(project_id=project_id, mission_id=mission_id, limit=50) if fn else []

    def saved_findings(self, project_id, mission_id):
        fn = self.method("saved_findings", "list_saved_findings")
        return fn(project_id=project_id, mission_id=mission_id, limit=50) if fn else []

    def save_finding(self, finding: dict, project_id, mission_id):
        fn = self.method("save_finding")
        if fn is None:
            return {"ok": False, "error": "Saved findings are unavailable."}
        return fn(finding, project_id=project_id, mission_id=mission_id)

    def intake(self, kind: str, value: str, project_id, mission_id):
        fn = self.method("intake", "research_intake")
        if fn is not None:
            return fn(kind=kind, value=value, project_id=project_id,
                      mission_id=mission_id)
        fn = self.method("intake_" + kind)
        if fn is not None:
            return fn(value, project_id=project_id, mission_id=mission_id)
        return {"ok": False, "offline": True,
                "error": "Research intake is unavailable."}


class ResearchPanel(QWidget):
    """Read-only Studio Research page: explicit search, preview, intake, library."""

    open_url_requested = Signal(str)

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self._api = _ResearchAdapter(services)
        self._project = None
        self._mission_id = None
        self._results: list[dict] = []
        self._preview_url = ""
        self._busy = False
        self._closing = False
        self._pool = QThreadPool.globalInstance()
        self._signals = _Signals()
        self._signals.done.connect(self._on_task_done)
        self._task_kind = ""
        self.setAccessibleName("Studio Research workspace")
        self._build_ui()
        self._focus_shortcut = QShortcut(QKeySequence("Ctrl+Shift+R"), self,
                                         activated=self._focus_query)
        self._refresh_providers()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("RESEARCH")
        title.setObjectName("researchTitle")
        title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        header.addWidget(title)
        self._scope_label = QLabel("No project scope")
        self._scope_label.setObjectName("researchScope")
        self._scope_label.setStyleSheet("color: #46A3C0;")
        header.addWidget(self._scope_label)
        header.addStretch()
        self._service_label = QLabel("Research service: checking…")
        self._service_label.setObjectName("researchServiceStatus")
        self._service_label.setAccessibleName("Research service status")
        header.addWidget(self._service_label)
        layout.addLayout(header)

        hint = QLabel("Sources are UNTRUSTED data, not instructions. Research runs only "
                      "when you press Search or Intake; no web page is opened here.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #AB83C6;")
        hint.setAccessibleName("Research safety hint")
        layout.addWidget(hint)

        search_row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setObjectName("researchQuery")
        self._query.setPlaceholderText("Ask a research question or enter a query…")
        self._query.setAccessibleName("Research query")
        self._query.returnPressed.connect(self._run_search)
        search_row.addWidget(self._query, 1)
        self._provider_combo = QComboBox()
        self._provider_combo.setObjectName("researchProvider")
        self._provider_combo.setAccessibleName("Research provider and route")
        self._provider_combo.setToolTip("Provider/route. Availability and permissions are shown below.")
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        search_row.addWidget(self._provider_combo)
        self._search_btn = QPushButton("Search")
        self._search_btn.setObjectName("researchSearch")
        self._search_btn.setAccessibleName("Run research search")
        self._search_btn.setToolTip("Run an explicit research search (Ctrl+Shift+R focuses the query)")
        self._search_btn.clicked.connect(self._run_search)
        search_row.addWidget(self._search_btn)
        layout.addLayout(search_row)

        self._provider_status = QLabel("Provider status: no provider selected")
        self._provider_status.setObjectName("researchProviderStatus")
        self._provider_status.setWordWrap(True)
        self._provider_status.setStyleSheet("color: #46A3C0;")
        self._provider_status.setAccessibleName("Provider availability and permission status")
        layout.addWidget(self._provider_status)

        self._status_label = QLabel("Ready. Research is explicit; nothing has been fetched.")
        self._status_label.setObjectName("researchStatus")
        self._status_label.setWordWrap(True)
        self._status_label.setAccessibleName("Research operation status")
        layout.addWidget(self._status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_results_area())
        splitter.addWidget(self._build_preview_area())
        splitter.setSizes([470, 530])
        layout.addWidget(splitter, 1)

        self._build_intake(layout)

    def _build_results_area(self) -> QWidget:
        box = QWidget()
        box.setAccessibleName("Research results and library")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("SOURCES")
        title.setStyleSheet("font-weight: 700; color: #7531FE;")
        layout.addWidget(title)
        self._results_table = QTableWidget(0, 6)
        self._results_table.setHorizontalHeaderLabels(
            ["Title", "Provider", "URL", "Snippet", "Age", "Untrusted"])
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._results_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._results_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self._results_table.setAccessibleName("Research result sources")
        self._results_table.itemSelectionChanged.connect(self._on_result_selected)
        layout.addWidget(self._results_table, 2)
        self._empty_label = QLabel("No results yet. Press Search to query explicitly.")
        self._empty_label.setObjectName("researchEmpty")
        self._empty_label.setStyleSheet("color: #AB83C6;")
        self._empty_label.setAccessibleName("Research empty state")
        layout.addWidget(self._empty_label)
        self._library_tabs = QTabWidget()
        self._library_tabs.setObjectName("researchLibrary")
        self._library_tabs.setAccessibleName("Research history and saved findings")
        self._history_list = QListWidget()
        self._history_list.setAccessibleName("Project and mission research history")
        self._saved_list = QListWidget()
        self._saved_list.setAccessibleName("Saved research findings")
        self._library_tabs.addTab(self._history_list, "History")
        self._library_tabs.addTab(self._saved_list, "Saved findings")
        self._library_tabs.currentChanged.connect(self._on_library_changed)
        layout.addWidget(self._library_tabs, 1)
        refresh = QHBoxLayout()
        self._refresh_library_btn = QPushButton("Refresh history/findings")
        self._refresh_library_btn.setAccessibleName("Refresh research history and saved findings")
        self._refresh_library_btn.clicked.connect(self._refresh_library)
        refresh.addWidget(self._refresh_library_btn)
        refresh.addStretch()
        layout.addLayout(refresh)
        return box

    def _build_preview_area(self) -> QWidget:
        box = QWidget()
        box.setAccessibleName("Research source preview")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        self._preview_title = QLabel("No source selected")
        self._preview_title.setStyleSheet("font-weight: 700; color: #46A3C0;")
        self._preview_title.setAccessibleName("Selected research source")
        layout.addWidget(self._preview_title)
        self._preview_tabs = QTabWidget()
        self._preview_text = QPlainTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setAccessibleName("Read-only fetched source text")
        self._preview_chunks = QListWidget()
        self._preview_chunks.setAccessibleName("Read-only source chunks")
        self._preview_details = QPlainTextEdit()
        self._preview_details.setReadOnly(True)
        self._preview_details.setAccessibleName(
            "Source metadata, citation provenance and redirects")
        self._preview_tabs.addTab(self._preview_text, "Text")
        self._preview_tabs.addTab(self._preview_chunks, "Chunks")
        self._preview_tabs.addTab(self._preview_details, "Details")
        layout.addWidget(self._preview_tabs, 1)
        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #E4469B;")
        self._warning_label.setAccessibleName("Source warning, stale or conflict indicator")
        layout.addWidget(self._warning_label)
        actions = QHBoxLayout()
        self._copy_url_btn = QPushButton("Copy URL")
        self._copy_url_btn.setEnabled(False)
        self._copy_url_btn.setAccessibleName("Copy selected source URL")
        self._copy_url_btn.clicked.connect(self._copy_url)
        actions.addWidget(self._copy_url_btn)
        self._open_url_btn = QPushButton("Request open URL")
        self._open_url_btn.setEnabled(False)
        self._open_url_btn.setToolTip(
            "Emits a host request; this panel never opens a browser.")
        self._open_url_btn.setAccessibleName("Request host open of selected source URL")
        self._open_url_btn.clicked.connect(self._request_open_url)
        actions.addWidget(self._open_url_btn)
        self._save_btn = QPushButton("Save finding")
        self._save_btn.setEnabled(False)
        self._save_btn.setAccessibleName("Save selected source as a scoped finding")
        self._save_btn.clicked.connect(self._save_finding)
        actions.addWidget(self._save_btn)
        actions.addStretch()
        layout.addLayout(actions)
        return box

    def _build_intake(self, layout) -> None:
        group = QGroupBox("Intake: pasted URL, GitHub repo, Hugging Face model or local file")
        group.setAccessibleName("Research intake")
        group_layout = QVBoxLayout(group)
        row = QHBoxLayout()
        self._intake_kind = QComboBox()
        self._intake_kind.addItems(list(_KINDS))
        self._intake_kind.setAccessibleName("Research intake type")
        row.addWidget(self._intake_kind)
        self._intake_input = QLineEdit()
        self._intake_input.setPlaceholderText(
            "Paste https://…, https://github.com/owner/repo, https://huggingface.co/…")
        self._intake_input.setAccessibleName("Research intake URL or path")
        self._intake_input.returnPressed.connect(self._run_intake)
        row.addWidget(self._intake_input, 1)
        self._intake_btn = QPushButton("Intake")
        self._intake_btn.setAccessibleName("Send intake to the research service")
        self._intake_btn.clicked.connect(self._run_intake)
        row.addWidget(self._intake_btn)
        self._attach_btn = QPushButton("Choose attachment…")
        self._attach_btn.setAccessibleName("Choose local attachment for research intake")
        self._attach_btn.clicked.connect(self._choose_attachment)
        row.addWidget(self._attach_btn)
        group_layout.addLayout(row)
        self._intake_status = QLabel("No intake yet. Intake is explicit and permission-checked.")
        self._intake_status.setObjectName("researchIntakeStatus")
        self._intake_status.setWordWrap(True)
        self._intake_status.setAccessibleName("Research intake status")
        group_layout.addWidget(self._intake_status)
        layout.addWidget(group)

    # ------------------------------------------------------------- providers
    def _refresh_providers(self) -> None:
        backend_status = {}
        try:
            backend_status = _dict(self._api.status())
        except Exception:  # noqa: BLE001 - offline metadata is optional
            backend_status = {}
        try:
            statuses = self._api.provider_statuses()
        except Exception as exc:  # noqa: BLE001 - shown as unavailable
            statuses = []
            self._service_label.setText("Research service: unavailable")
            self._status_label.setText("Research unavailable: " + _redact(exc))
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()
        for raw in statuses or []:
            item = _dict(raw)
            provider_id = str(item.get("provider_id") or item.get("id") or "")
            if not provider_id:
                continue
            name = str(item.get("name") or provider_id)
            available = bool(item.get("available", item.get("ok", True)))
            state = str(item.get("status") or ("available" if available else "unavailable"))
            label = name + " — " + state
            self._provider_combo.addItem(label, provider_id)
            idx = self._provider_combo.count() - 1
            self._provider_combo.setItemData(idx, _redact(item.get("reason") or state),
                                             Qt.ItemDataRole.ToolTipRole)
        if self._provider_combo.count() == 0:
            self._provider_combo.addItem("No research provider configured", None)
        self._provider_combo.blockSignals(False)
        if backend_status.get("offline") and not backend_status.get("network_configured"):
            self._service_label.setText(
                "Research service: offline (no network transport configured)")
        elif backend_status.get("permission_needed"):
            self._service_label.setText("Research service: permission needed")
        else:
            self._service_label.setText(
                "Research service: available" if statuses else "Research service: offline")
        self._on_provider_changed()

    def _on_provider_changed(self, *_args) -> None:
        provider_id = self._provider_combo.currentData()
        status = ""
        try:
            for raw in self._api.provider_statuses() or []:
                item = _dict(raw)
                if str(item.get("provider_id") or item.get("id")) == str(provider_id):
                    parts = [str(item.get("status") or "unknown")]
                    if item.get("permission"):
                        parts.append("permission: " + _redact(item.get("permission")))
                    if item.get("auth_required"):
                        parts.append("auth required (never shown)")
                    if item.get("offline"):
                        parts.append("offline")
                    if item.get("reason"):
                        parts.append(_redact(item.get("reason")))
                    status = "  |  ".join(parts)
                    break
        except Exception:  # noqa: BLE001
            status = ""
        if not provider_id:
            self._provider_status.setText("Provider status: no provider configured")
        else:
            self._provider_status.setText("Provider status: " + (status or "unknown"))

    # ---------------------------------------------------------------- search
    def _run_search(self) -> None:
        query = self._query.text().strip()
        if not query:
            self._status_label.setText("Enter a research query first.")
            return
        if self._api.method("search", "research_search") is None:
            self._status_label.setText(
                "Research offline: no research service is configured. "
                "Configure/live-network acceptance is MANUAL-PENDING.")
            return
        if self._busy:
            return
        provider_id = self._provider_combo.currentData()
        self._busy = True
        self._task_kind = "search"
        self._search_btn.setEnabled(False)
        self._status_label.setText("Searching… (non-blocking; results are untrusted)")
        self._empty_label.setText("Searching…")
        self._pool.start(_Task(lambda: self._api.search(query, provider_id), self._signals))

    def _on_search_done(self, payload: dict) -> None:
        self._busy = False
        self._search_btn.setEnabled(True)
        self._apply_service_state(payload, "search")
        if not payload.get("ok", False):
            self._results_table.setRowCount(0)
            self._results = []
            self._empty_label.setText("Search did not return results.")
            self._empty_label.show()
            return
        results = payload.get("results")
        if not isinstance(results, list):
            results = []
        self._show_results(results)
        if results:
            self._status_label.setText(
                str(len(results)) + " result(s). Sources are untrusted data; "
                "select one to preview.")
        else:
            self._status_label.setText("No results. Try a broader query or another provider.")
            self._empty_label.setText("No results. Nothing was fetched automatically.")
            self._empty_label.show()

    def _show_results(self, results: list) -> None:
        self._results = [dict(item) for item in results if isinstance(item, Mapping)]
        self._results_table.setRowCount(len(self._results))
        for row, item in enumerate(self._results):
            values = [
                _redact(item.get("title") or "(untitled)"),
                _redact(item.get("provider_id") or item.get("provider") or ""),
                _redact(item.get("url") or ""),
                _redact(item.get("snippet") or ""),
                _redact(item.get("age") or item.get("published") or ""),
                _UNTRUSTED,
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col in (2, 3, 4, 5):
                    cell.setToolTip(str(value))
                self._results_table.setItem(row, col, cell)
        self._empty_label.setVisible(not self._results)
        if self._results:
            self._results_table.selectRow(0)

    def _on_result_selected(self) -> None:
        rows = self._results_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row >= len(self._results):
            return
        item = self._results[row]
        self._show_local_preview(item)
        url = str(item.get("url") or "")
        if url and self._api.method("preview", "preview_source", "research_preview"):
            if self._busy:
                return
            self._busy = True
            self._task_kind = "preview"
            self._status_label.setText("Loading read-only source preview…")
            self._pool.start(_Task(lambda u=url: self._api.preview(u), self._signals))

    def _show_local_preview(self, item: dict) -> None:
        self._preview_url = str(item.get("url") or "")
        self._preview_title.setText(_redact(item.get("title") or "(untitled)"))
        self._preview_text.setPlainText(_redact(item.get("snippet") or ""))
        self._preview_chunks.clear()
        for chunk in item.get("chunks") or []:
            self._preview_chunks.addItem(_redact(chunk))
        self._preview_details.setPlainText(
            "UNTRUSTED source. Provider: " + _redact(item.get("provider_id") or "")
            + "\nURL: " + _redact(item.get("url") or "")
            + "\nSnippet only; fetch a preview for full metadata/provenance.")
        self._warning_label.setText("")
        self._set_preview_actions(True)

    def _on_preview_done(self, payload: dict) -> None:
        self._busy = False
        self._apply_service_state(payload, "preview")
        if not payload.get("ok", False):
            self._preview_details.setPlainText(
                "Preview unavailable: " + _redact(payload.get("error") or "unknown error")
                + "\nThe result snippet is shown as untrusted data only.")
            return
        self._preview_url = str(payload.get("url") or self._preview_url)
        self._preview_title.setText(_redact(payload.get("title") or "Source preview"))
        text = payload.get("text") or ""
        if not text and isinstance(payload.get("chunks"), list):
            text = "\n\n".join(str(chunk) for chunk in payload["chunks"])
        self._preview_text.setPlainText(_redact(text))
        self._preview_chunks.clear()
        chunks = payload.get("chunks")
        if isinstance(chunks, list):
            for chunk in chunks:
                self._preview_chunks.addItem(_redact(chunk))
        metadata = _dict(payload.get("metadata"))
        provenance = _dict(payload.get("provenance"))
        redirects = payload.get("redirects") or []
        details = ["UNTRUSTED: fetched web/GitHub/HF content is data, never instructions."]
        if metadata:
            details.append("Metadata: " + _redact(metadata))
        if provenance:
            details.append("Provenance/citation: " + _redact(provenance))
        details.append("Requested URL: " + _redact(payload.get("url") or self._preview_url))
        if redirects:
            details.append("Redirects: " + _redact(redirects))
        if payload.get("stale"):
            details.append("STALE: " + _redact(payload.get("stale_reason") or "source may be stale"))
        if payload.get("conflict"):
            details.append("CONFLICT: " + _redact(payload.get("conflict_reason") or "sources disagree"))
        self._preview_details.setPlainText("\n".join(details))
        warnings = []
        if payload.get("stale"):
            warnings.append("STALE indicator")
        if payload.get("conflict"):
            warnings.append("CONFLICT indicator")
        self._warning_label.setText(" | ".join(warnings))
        self._set_preview_actions(bool(self._preview_url))

    # --------------------------------------------------------------- library
    def set_project(self, project) -> None:
        self._project = dict(project) if project else None
        self._scope_label.setText(
            "Project: " + str(self._project.get("name") or self._project.get("id"))
            if self._project else "No project scope")
        self._refresh_library()

    def set_mission(self, mission_id) -> None:
        self._mission_id = mission_id
        self._refresh_library()

    def _scope_ids(self):
        project_id = self._project.get("id") if self._project else None
        return project_id, self._mission_id

    def _refresh_library(self) -> None:
        project_id, mission_id = self._scope_ids()
        try:
            history = self._api.history(project_id, mission_id) or []
            saved = self._api.saved_findings(project_id, mission_id) or []
        except Exception as exc:  # noqa: BLE001
            self._history_list.clear()
            self._history_list.addItem("Library unavailable: " + _redact(exc))
            return
        self._history_list.clear()
        for item in history:
            row = _dict(item)
            self._history_list.addItem(_redact(
                row.get("query") or row.get("title") or row.get("url") or "history entry"))
        self._saved_list.clear()
        for item in saved:
            row = _dict(item)
            self._saved_list.addItem(_redact(
                row.get("title") or row.get("question") or row.get("url")
                or "saved finding"))
        if not history:
            self._history_list.addItem("No history in this project/mission scope.")
        if not saved:
            self._saved_list.addItem("No saved findings in this scope.")

    def _on_library_changed(self, *args) -> None:
        self._refresh_library()

    def on_page_shown(self) -> None:
        """Explicit page reveal: refresh scoped library only; never auto-search."""
        self._refresh_library()

    # ---------------------------------------------------------------- preview
    def _set_preview_actions(self, enabled: bool) -> None:
        self._copy_url_btn.setEnabled(enabled)
        self._open_url_btn.setEnabled(enabled)
        self._save_btn.setEnabled(enabled and bool(self._api.method("save_finding")))

    def _copy_url(self) -> None:
        if self._preview_url:
            QApplication.clipboard().setText(self._preview_url)
            self._status_label.setText("Source URL copied (untrusted source).")

    def _request_open_url(self) -> None:
        if self._preview_url:
            self.open_url_requested.emit(self._preview_url)
            self._status_label.setText(
                "Open-URL request emitted to the host; this panel never opens a browser.")

    def _save_finding(self) -> None:
        if not self._preview_url:
            return
        project_id, mission_id = self._scope_ids()
        finding = {"url": self._preview_url,
                   "title": self._preview_title.text(),
                   "text": self._preview_text.toPlainText()[:4000]}
        try:
            result = _dict(self._api.save_finding(finding, project_id, mission_id))
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": str(exc)}
        if result.get("ok"):
            self._status_label.setText("Finding saved in the current project/mission scope.")
            self._refresh_library()
        else:
            self._apply_service_state(result, "save")

    # ---------------------------------------------------------------- intake
    def _detect_intake_kind(self, value: str) -> str:
        text = value.strip()
        lowered = text.lower()
        if lowered.startswith(("http://", "https://")):
            if "github.com/" in lowered:
                return "github"
            if "huggingface.co/" in lowered:
                return "huggingface"
            return "url"
        try:
            if text and Path(text).expanduser().exists():
                return "attachment"
        except OSError:
            pass
        return ""

    def _run_intake(self) -> None:
        value = self._intake_input.text().strip()
        kind_label = self._intake_kind.currentText()
        mapping = {"Web URL": "url", "GitHub repo": "github",
                   "Hugging Face model": "huggingface",
                   "Local attachment": "attachment"}
        kind = mapping.get(kind_label, "")
        if not kind:
            kind = self._detect_intake_kind(value)
        if not value:
            self._set_intake_state("Enter a URL, repository/model link or attachment path.")
            return
        if not kind:
            self._set_intake_state(
                "Unsupported intake: use an http(s) URL, GitHub repo, Hugging Face model "
                "link or an existing local file.")
            return
        project_id, mission_id = self._scope_ids()
        self._intake_status.setText("Routing intake to the research service…")
        try:
            result = _dict(self._api.intake(kind, value, project_id, mission_id))
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": str(exc)}
        self._apply_service_state(result, "intake")
        if result.get("ok"):
            self._set_intake_state("Intake accepted for " + kind + ". Review is explicit.")
        elif result.get("permission_needed"):
            self._set_intake_state(
                "Permission needed: " + _redact(result.get("permission_needed")))
        elif result.get("denied"):
            self._set_intake_state("Intake denied by policy: " + _redact(
                result.get("reason") or "not permitted"))
        elif result.get("offline"):
            self._set_intake_state("Research offline: this intake cannot be fetched now.")
        else:
            self._set_intake_state("Intake failed: " + _redact(
                result.get("error") or "unknown error"))

    def _choose_attachment(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Choose research attachment")
        if path:
            self._intake_kind.setCurrentText("Local attachment")
            self._intake_input.setText(path)
            self._intake_attachment(path)

    def _intake_attachment(self, path: str) -> None:
        project_id, mission_id = self._scope_ids()
        try:
            result = _dict(self._api.intake("attachment", str(path), project_id, mission_id))
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": str(exc)}
        self._apply_service_state(result, "intake")
        if result.get("ok"):
            self._set_intake_state("Attachment routed for explicit review.")
        elif result.get("permission_needed"):
            self._set_intake_state("Permission needed: " + _redact(result.get("permission_needed")))
        elif result.get("denied"):
            self._set_intake_state("Attachment intake denied by policy: " + _redact(
                result.get("reason") or "not permitted"))
        elif result.get("offline"):
            self._set_intake_state("Research offline: attachment intake unavailable.")
        else:
            self._set_intake_state("Attachment intake failed: " + _redact(
                result.get("error") or "unknown error"))

    def _set_intake_state(self, text: str) -> None:
        self._intake_status.setText(_redact(text))

    # ----------------------------------------------------------------- state
    def _apply_service_state(self, payload: dict, operation: str) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("permission_needed"):
            self._status_label.setText(
                "Permission needed: " + _redact(payload.get("permission_needed")))
        elif payload.get("denied"):
            self._status_label.setText(
                "Denied by policy: " + _redact(payload.get("reason") or "not permitted"))
        elif payload.get("offline"):
            self._status_label.setText(
                "Research offline: " + _redact(payload.get("error")
                                                or "no network/route available"))
        elif not payload.get("ok", False) and payload.get("error"):
            self._status_label.setText(
                "Research " + operation + " error: " + _redact(payload.get("error")))
        if payload.get("permission_needed"):
            self._service_label.setText("Research service: permission needed")
        elif payload.get("denied"):
            self._service_label.setText("Research service: denied by policy")
        elif payload.get("offline"):
            self._service_label.setText("Research service: offline")
        elif payload.get("ok"):
            self._service_label.setText("Research service: available")

    @Slot(dict)
    def _on_task_done(self, payload: dict) -> None:
        if self._closing:
            return
        if self._task_kind == "preview":
            self._on_preview_done(payload)
        else:
            self._on_search_done(payload)

    def _focus_query(self) -> None:
        self._query.setFocus()

    def shutdown(self) -> None:
        self._closing = True
        self._pool.waitForDone(1000)

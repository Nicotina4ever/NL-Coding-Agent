"""Project-scoped file browser and read-only viewer."""
from __future__ import annotations

from nl_coding_agent.gui.i18n import ui_text

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QSortFilterProxyModel, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFileSystemModel, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QSplitter, QTreeView, QVBoxLayout, QWidget,
)

from nl_coding_agent.app.services import AppServices
from nl_coding_agent.gui.i18n import get_i18n

_BLOCKED_NAMES = {
    "python", "crewai", "crewai-tools", ".git", "data", "logs", "state",
    "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache",
    ".mypy_cache", ".workspace", "dist", "build",
}
_BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".7z",
    ".rar", ".exe", ".dll", ".so", ".dylib", ".pyc", ".pyd", ".sqlite3",
    ".db", ".safetensors", ".gguf", ".bin", ".pt", ".pth", ".onnx", ".mp3",
    ".mp4", ".wav", ".webm",
}
_MAX_PREVIEW_CHARS = 400_000


class _ProjectFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self.project_root = None

    def set_filter_text(self, text: str):
        self._text = (text or "").strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if self.project_root is not None:
            path = Path(model.filePath(index)).resolve()
            if path == self.project_root or path in self.project_root.parents:
                return True
        name = model.fileName(index)
        lowered = name.lower()
        if lowered in _BLOCKED_NAMES or lowered.startswith("."):
            return False
        if not self._text:
            return True
        if self._text in lowered:
            return True
        return model.isDir(index)


class FileViewerWidget(QWidget):
    """Browse the open project and preview text files safely."""

    file_opened = Signal(str)

    def __init__(self, services: AppServices, parent=None):
        super().__init__(parent)
        self._services = services
        self._project: dict | None = None
        self._root: Path | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(ui_text("Project Files"))
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        header.addWidget(title)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText(ui_text("Filter files…"))
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._on_filter_changed)

        self._refresh_btn = QPushButton(ui_text("Refresh"))
        self._refresh_btn.clicked.connect(self.refresh)
        header.addStretch()
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)
        layout.addWidget(self._filter)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._model = QFileSystemModel(self)
        self._model.directoryLoaded.connect(self._directory_loaded)
        self._model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self._model.setReadOnly(True)
        self._proxy = _ProjectFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._tree = QTreeView()
        self._tree.setModel(self._proxy)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(False)
        self._tree.setUniformRowHeights(True)
        for column in range(1, 4):
            self._tree.hideColumn(column)
        self._tree.clicked.connect(self._on_clicked)
        self._tree.doubleClicked.connect(self._on_double_clicked)
        splitter.addWidget(self._tree)

        right = QWidget()
        self._preview_panel = right
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self._path_label = QLabel(ui_text("Select a file"))
        self._path_label.setStyleSheet("color: #B8BECA; font-size: 12px;")
        right_layout.addWidget(self._path_label)

        self._viewer = QPlainTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setObjectName("logOutput")
        self._viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        right_layout.addWidget(self._viewer, 1)
        splitter.addWidget(right)
        splitter.setSizes([320, 700])
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------ project

    def set_browser_only(self, enabled=True):
        self._preview_panel.setVisible(not enabled)
        self._filter.setPlaceholderText(get_i18n().tr("files.filter", ui_text("Filter files…")))

    def set_project(self, project: dict | None):
        self._project = project
        self._root = Path(project["root"]).resolve() if project and project.get("root") else None
        self._proxy.project_root = self._root
        self._proxy.invalidateFilter()
        self.refresh()

    @Slot(str)
    def _directory_loaded(self, path):
        if self._root and Path(path).resolve() == self._root:
            index = self._model.index(str(self._root))
            self._tree.setRootIndex(self._proxy.mapFromSource(index))

    @Slot()
    def refresh(self):
        if self._root is None or not self._root.exists():
            self._tree.setRootIndex(QModelIndex())
            self._path_label.setText(ui_text("Open a project to browse its files"))
            self._viewer.clear()
            return
        source_root = self._model.setRootPath(str(self._root))
        self._tree.setRootIndex(self._proxy.mapFromSource(source_root))
        self._path_label.setText(str(self._root))

    @Slot(str)
    def _on_filter_changed(self, text: str):
        self._proxy.set_filter_text(text)

    # ------------------------------------------------------------------ viewing

    def _source_path(self, proxy_index: QModelIndex) -> Path | None:
        if not proxy_index.isValid():
            return None
        source_index = self._proxy.mapToSource(proxy_index)
        return Path(self._model.filePath(source_index))

    @Slot(QModelIndex)
    def _on_clicked(self, index: QModelIndex):
        path = self._source_path(index)
        if path is None or path.is_dir():
            return
        self._open_path(path)

    @Slot(QModelIndex)
    def _on_double_clicked(self, index: QModelIndex):
        path = self._source_path(index)
        if path is not None and path.is_file():
            self._open_path(path)

    def _open_path(self, path: Path):
        if self._root is None:
            return
        try:
            rel_path = path.relative_to(self._root).as_posix()
        except ValueError:
            self._path_label.setText(ui_text("Path is outside the project root"))
            return

        self._path_label.setText(rel_path)
        self.file_opened.emit(rel_path)
        if not self._preview_panel.isVisible():
            return

        if path.suffix.lower() in _BINARY_SUFFIXES:
            self._viewer.setPlainText(
                f"Binary file preview is not available.\n\nPath: {rel_path}\nSize: {path.stat().st_size:,} bytes"
            )
            return
        try:
            text = self._services.read_project_file(self._root, rel_path)
        except Exception as exc:
            self._viewer.setPlainText(f"Could not read {rel_path}:\n{exc}")
            return
        if len(text) > _MAX_PREVIEW_CHARS:
            text = text[:_MAX_PREVIEW_CHARS] + "\n… [preview truncated]"
        self._viewer.setPlainText(text)

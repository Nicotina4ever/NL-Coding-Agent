"""F3a: project editor tabs, Qt syntax highlighting, explicit save, unsaved guards."""
from __future__ import annotations

from nl_coding_agent.gui.i18n import ui_text

import re
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

_RULES = {
    "python": [(r"\b(def|class|import|from|return|if|else|elif|for|while|try|except|finally|with|as|in|is|not|and|or|None|True|False|pass|raise|lambda|async|await)\b", "#E4469B"),
               (r"#[^\n]*", "#6B7280"),
               (r'"[^"\n]*"|\'[^\'\n]*\'', "#AB83C6")],
    "javascript": [(r"\b(function|class|const|let|var|return|if|else|for|while|new|import|export|async|await|true|false|null)\b", "#E4469B"),
                   (r"//[^\n]*", "#6B7280"),
                   (r'"[^"\n]*"|\'[^\'\n]*\'', "#AB83C6")],
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


class CodeHighlighter(QSyntaxHighlighter):
    def __init__(self, document, language="python"):
        super().__init__(document)
        self._rules = []
        for pattern, colour in _RULES.get(language, _RULES["python"]):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colour))
            self._rules.append((re.compile(pattern), fmt))

    def highlightBlock(self, text):  # noqa: N802 - Qt override
        for expression, fmt in self._rules:
            for match in expression.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class EditorTab(QPlainTextEdit):
    modified_changed = Signal(bool)

    def __init__(self, rel_path, content, *, read_only=False, language="python", reason=""):
        super().__init__()
        self.rel_path = rel_path
        self.read_only = bool(read_only)
        self.base_sha256 = ""
        self.setPlainText(content)
        self.setReadOnly(self.read_only)
        self.setAccessibleName("Editor: " + rel_path)
        self.setToolTip(reason or ("Read-only" if read_only else "Editable project file"))
        self.setObjectName("codeEditor")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self._highlighter = CodeHighlighter(self.document(), language)
        self.textChanged.connect(lambda: self.modified_changed.emit(self.is_modified()))

    def is_modified(self):
        return bool(self.document().isModified()) and not self.read_only

    def mark_saved(self):
        self.document().setModified(False)


class EditorPanel(QWidget):
    ask_chat_requested = Signal(str, str)

    def __init__(self, services, parent=None, *, confirm_callback=None):
        super().__init__(parent)
        self._services = services
        self._project = None
        self._tabs = {}
        self._confirm = confirm_callback or self._default_confirm
        self.setAccessibleName("Project editor")
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self._title = QLabel(_tr("editor.title", "EDITOR"))
        title = self._title
        title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        header.addWidget(title)
        self._path_label = QLabel(_tr(
            "editor.no_file", "No file open"))
        self._path_label.setStyleSheet("color: #AB83C6;")
        header.addWidget(self._path_label, 1)
        self._save_btn = QPushButton(_tr("editor.save", "Save"))
        self._save_btn.setAccessibleName("Save current file")
        self._save_btn.setToolTip(_tr(
            "editor.save_tooltip", "Explicit save of the current file (Ctrl+S)"))
        self._save_btn.clicked.connect(self.save_current)
        header.addWidget(self._save_btn)
        self._ask_chat_btn = QPushButton(_tr("editor.ask_chat", "Ask in Chat"))
        self._ask_chat_btn.setObjectName("secondaryButton")
        self._ask_chat_btn.setAccessibleName("Ask in Chat about the selected code")
        self._ask_chat_btn.setToolTip(_tr(
            "editor.ask_chat_tooltip",
            "Send the selected code to Chat as context"))
        self._ask_chat_btn.clicked.connect(self._ask_chat_about_selection)
        header.addWidget(self._ask_chat_btn)
        layout.addLayout(header)
        self._tabs_widget = QTabWidget()
        self._tabs_widget.setTabsClosable(True)
        self._tabs_widget.setAccessibleName("Open editor tabs")
        self._tabs_widget.tabCloseRequested.connect(self.close_tab)
        self._tabs_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs_widget, 1)
        self._status = QLabel(_tr(
            "editor.open_file", "Open a file from the Files panel or the IDE page."))
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_current)
        _register_retranslate(self)

    def retranslate(self) -> None:
        self._title.setText(_tr("editor.title", "EDITOR"))
        self._save_btn.setText(_tr("editor.save", "Save"))
        self._save_btn.setToolTip(_tr(
            "editor.save_tooltip", "Explicit save of the current file (Ctrl+S)"))

    def _default_confirm(self, rel_path):
        answer = QMessageBox.question(self, ui_text("Unsaved changes"),
                                      ui_text("Close ") + rel_path + ui_text(" and discard unsaved changes?"),
                                      QMessageBox.StandardButton.Discard
                                      | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard

    def set_project(self, project):
        old_root = (self._project or {}).get("root")
        new_root = (project or {}).get("root")
        changed = ((Path(old_root).resolve() if old_root else None)
                   != (Path(new_root).resolve() if new_root else None))
        if changed:
            if not self.confirm_close():
                return False
            # Confirm every dirty tab before removing any, so Cancel is atomic.
            while self._tabs_widget.count():
                tab = self._tabs_widget.widget(0)
                self._tabs_widget.removeTab(0)
                tab.deleteLater()
            self._tabs.clear()
        self._project = dict(project) if project else None
        self._status.setText(ui_text("Project: ") + (self._project or {}).get("root", ui_text("none")))
        return True

    def confirm_close(self) -> bool:
        return all(not tab.is_modified() or self._confirm(tab.rel_path)
                   for tab in self._tabs.values())

    def open_file(self, rel_path):
        if not self._project:
            self._status.setText(_tr(
                "editor.open_project",
                "Open a project before opening files."))
            return False
        if rel_path in self._tabs:
            self._tabs_widget.setCurrentWidget(self._tabs[rel_path])
            return True
        try:
            info = self._services.load_editor_file(self._project["root"], rel_path)
        except Exception as exc:  # noqa: BLE001 - error state
            self._status.setText("Cannot open " + rel_path + ": " + str(exc))
            return False
        if info.get("error"):
            self._status.setText("Cannot open " + rel_path + ": " + str(info["error"]))
            return False
        suffix = str(info.get("suffix") or Path(rel_path).suffix).lower()
        language = "python" if suffix == ".py" else "javascript" if suffix in (".js", ".ts") else "python"
        tab = EditorTab(info["rel_path"], info.get("content") or "",
                        read_only=bool(info.get("read_only")), language=language,
                        reason=str(info.get("read_only_reason") or ""))
        tab.base_sha256 = str(info.get("sha256") or "")
        tab.project_root = Path(self._project["root"]).resolve()
        tab.modified_changed.connect(self._update_titles)
        self._tabs[info["rel_path"]] = tab
        self._tabs_widget.addTab(tab, info["rel_path"])
        self._tabs_widget.setCurrentWidget(tab)
        self._save_btn.setEnabled(not tab.read_only)
        self._status.setText(ui_text("Read-only preview: ") + str(info.get("read_only_reason"))
                             if tab.read_only else ui_text("Editing ") + info["rel_path"])
        return True

    def _update_titles(self, *_args):
        for index in range(self._tabs_widget.count()):
            tab = self._tabs_widget.widget(index)
            title = tab.rel_path if not tab.is_modified() else "* " + tab.rel_path
            self._tabs_widget.setTabText(index, title)

    def _on_tab_changed(self, index):
        tab = self._tabs_widget.widget(index) if index >= 0 else None
        self._path_label.setText(getattr(tab, "rel_path", "No file open") if tab else "No file open")
        self._save_btn.setEnabled(bool(tab is not None and not getattr(tab, "read_only", False)))

    def modify_current(self, text):
        tab = self._tabs_widget.currentWidget()
        if tab is not None and not tab.read_only:
            tab.setPlainText(text)
            tab.document().setModified(True)

    def _ask_chat_about_selection(self) -> None:
        tab = self._tabs_widget.currentWidget()
        if tab is None:
            self._status.setText("No file is open.")
            return
        text = tab.textCursor().selectedText().replace("\u2029", "\n").strip()
        if not text:
            self._status.setText("Select code before asking in Chat.")
            return
        self.ask_chat_requested.emit(text, tab.rel_path)
        self._status.setText("Selected code from " + tab.rel_path +
                             " sent to Chat.")

    def save_current(self):
        tab = self._tabs_widget.currentWidget()
        if tab is None or tab.read_only:
            self._status.setText("This file is read-only; nothing was saved.")
            return False
        if (not self._project or Path(self._project["root"]).resolve() != tab.project_root):
            self._status.setText("Save refused: file belongs to another project.")
            return False
        if not tab.is_modified():
            self._status.setText("No unsaved changes.")
            return True
        result = self._services.save_editor_file(
            tab.project_root, tab.rel_path, tab.toPlainText(),
            expected_sha256=tab.base_sha256)
        if not result.get("ok"):
            self._status.setText("Save refused: " + str(result.get("error")
                                                        or result.get("error_code")))
            return False
        tab.base_sha256 = str(result.get("sha256") or "")
        tab.mark_saved()
        self._update_titles()
        self._status.setText("Saved " + tab.rel_path + " (explicit human action).")
        return True

    def close_tab(self, index):
        tab = self._tabs_widget.widget(index)
        if tab is None:
            return True
        if tab.is_modified() and not self._confirm(tab.rel_path):
            return False
        self._tabs_widget.removeTab(index)
        self._tabs.pop(tab.rel_path, None)
        tab.deleteLater()
        return True

    def tab_count(self):
        return self._tabs_widget.count()

    def current_path(self):
        tab = self._tabs_widget.currentWidget()
        return tab.rel_path if tab else ""

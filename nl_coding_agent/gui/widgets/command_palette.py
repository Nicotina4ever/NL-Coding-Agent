"""F3b: keyboard command palette for safe application actions only."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QVBoxLayout)


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


@dataclass
class CommandAction:
    action_id: str
    label: str
    callback: Callable[[], None] | None = None
    shortcut: str = ""
    enabled: bool = True
    disabled_reason: str = ""
    category: str = "app"


class CommandPalette(QDialog):
    """Filterable list of safe actions; Enter triggers one, Escape closes."""

    triggered = Signal(str)

    def __init__(self, actions=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_tr(
            "command_palette.window_title", "Command Palette"))
        self.setModal(True)
        self.setObjectName("commandPalette")
        self.setAccessibleName("Command palette")
        self.resize(620, 420)
        self._actions: list[CommandAction] = []
        layout = QVBoxLayout(self)
        self._title = QLabel(_tr(
            "command_palette.title", "COMMAND PALETTE"))
        self._title.setStyleSheet("font-weight: 800; letter-spacing: 1px; color: #7531FE;")
        layout.addWidget(self._title)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(_tr(
            "command_palette.filter",
            "Type to filter safe commands… (Enter runs, Esc closes)"))
        self._filter.setAccessibleName("Command palette filter")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)
        self._list = QListWidget()
        self._list.setAccessibleName("Available commands")
        self._list.itemActivated.connect(lambda _item: self._activate_current())
        layout.addWidget(self._list, 1)
        self._hint = QLabel(_tr(
            "command_palette.hint",
            "Safe actions only: open/switch/refresh/settings/read-only doctor. "
            "Destructive and model actions are never exposed here."))
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)
        if actions:
            self.set_actions(actions)
        _register_retranslate(self)

    def retranslate(self) -> None:
        self.setWindowTitle(_tr(
            "command_palette.window_title", "Command Palette"))
        self._title.setText(_tr(
            "command_palette.title", "COMMAND PALETTE"))
        self._filter.setPlaceholderText(_tr(
            "command_palette.filter",
            "Type to filter safe commands… (Enter runs, Esc closes)"))
        self._hint.setText(_tr(
            "command_palette.hint",
            "Safe actions only: open/switch/refresh/settings/read-only doctor. "
            "Destructive and model actions are never exposed here."))

    def set_actions(self, actions) -> None:
        self._actions = list(actions)
        self._apply_filter(self._filter.text())
        for index, action in enumerate(self._actions):
            if action.enabled:
                self._list.setCurrentRow(index)
                break

    def _apply_filter(self, text: str) -> None:
        query = str(text or "").strip().lower()
        self._list.clear()
        for action in self._actions:
            haystack = (action.label + " " + action.category + " " + action.action_id).lower()
            if query and query not in haystack:
                continue
            label = action.label
            if action.shortcut:
                label += "    " + action.shortcut
            if not action.enabled and action.disabled_reason:
                label += "    (disabled: " + action.disabled_reason + ")"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, action.action_id)
            item.setToolTip(action.disabled_reason or action.label)
            if not action.enabled:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._list.addItem(item)
        if self._list.count() and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)

    def _selected_action(self) -> CommandAction | None:
        item = self._list.currentItem()
        if item is None:
            return None
        action_id = item.data(Qt.ItemDataRole.UserRole)
        return next((a for a in self._actions if a.action_id == action_id), None)

    def _activate_current(self) -> bool:
        action = self._selected_action()
        if action is None or not action.enabled:
            return False
        self.triggered.emit(action.action_id)
        if action.callback is not None:
            try:
                action.callback()
            except Exception:
                pass
        self.accept()
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._activate_current():
                return
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._filter.setFocus()
        self._filter.selectAll()

    def actions(self) -> list[CommandAction]:
        return list(self._actions)

    def visible_labels(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

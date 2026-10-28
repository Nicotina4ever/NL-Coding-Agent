"""Sidebar navigation widget."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup, QSpacerItem, QSizePolicy
from PySide6.QtCore import Signal, Qt


PAGES = [
    ("Projects",  "projects"),
    ("Files",     "files"),
    ("Tasks",     "tasks"),
    ("Agents",    "agents"),
    ("Model Hub", "models"),
    ("Settings",  "settings"),
]


class SidebarWidget(QWidget):
    """Left navigation sidebar."""

    page_changed = Signal(str)  # emits page key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        self._buttons: dict[str, QPushButton] = {}
        for label, key in PAGES:
            btn = QPushButton(label)
            btn.setObjectName("sidebarButton")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("page_key", key)
            btn.clicked.connect(lambda checked, k=key: self.page_changed.emit(k))
            self._group.addButton(btn)
            layout.addWidget(btn)
            self._buttons[key] = btn

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Select first page by default
        if self._buttons:
            first = list(self._buttons.values())[0]
            first.setChecked(True)

    def select_page(self, key: str):
        btn = self._buttons.get(key)
        if btn:
            btn.setChecked(True)

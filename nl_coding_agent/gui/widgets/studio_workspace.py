"""Composition of existing Studio widgets using Qt's native dock persistence."""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDockWidget, QFrame, QMainWindow, QScrollArea, QTabWidget


def studio_settings():
    # Explicit local INI storage also works in portable/restricted Windows sessions.
    # Qt's organization constructor otherwise uses the registry and can fail silently.
    from nl_coding_agent.persistence.database import data_root
    return QSettings(str(data_root() / "studio.ini"), QSettings.Format.IniFormat)


class StudioWorkspace(QMainWindow):
    def __init__(self, editor, panels, translate, parent=None):
        super().__init__(parent)
        self.setObjectName("studioWorkspace")
        self.setDockNestingEnabled(True)
        self.setDockOptions(self.DockOption.AllowNestedDocks | self.DockOption.AllowTabbedDocks
                            | self.DockOption.AnimatedDocks)
        self.tabs = QTabWidget()
        self.tabs.addTab(editor, translate("workspace.editor", "Editor"))
        self.setCentralWidget(self.tabs)
        self.docks = {}
        self._titles = {}
        bottom = None
        for key, title, widget, area in panels:
            dock = QDockWidget(translate("workspace." + key, title), self)
            dock.setObjectName("studioDock_" + key)
            dock.panel = widget
            if key in ("goals", "research", "agents"):
                # Large focused workspaces must not dictate the editor's minimum height.
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setWidget(widget)
                dock.setWidget(scroll)
            else:
                dock.setWidget(widget)
            self.addDockWidget(area, dock)
            self.docks[key] = dock
            self._titles[key] = title
            if area == Qt.DockWidgetArea.BottomDockWidgetArea:
                if bottom is None:
                    bottom = dock
                else:
                    self.tabifyDockWidget(bottom, dock)
        self.docks["terminal"].raise_()
        self.docks["inspector"].hide()
        self.resizeDocks([self.docks["files"], self.docks["chat"]], [230, 390],
                         Qt.Orientation.Horizontal)
        self.resizeDocks([self.docks["terminal"]], [200], Qt.Orientation.Vertical)

    def reveal(self, key):
        dock = self.docks[key]
        dock.show()
        dock.raise_()
        dock.panel.setFocus()

    def retranslate(self, translate):
        self.tabs.setTabText(0, translate("workspace.editor", "Editor"))
        for key, dock in self.docks.items():
            dock.setWindowTitle(translate("workspace." + key, self._titles[key]))

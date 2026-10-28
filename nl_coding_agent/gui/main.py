"""GUI entry point."""
from __future__ import annotations

import sys
from pathlib import Path


def run_gui() -> int:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NL Coding Agent")
    app.setApplicationDisplayName("NL Coding Agent")
    app.setOrganizationName("NLCodingAgent")

    # Apply theme
    from nl_coding_agent.gui.theme import apply_theme
    apply_theme(app)

    # Boot services
    from nl_coding_agent.app.services import get_services
    services = get_services()

    # Create and show main window
    from nl_coding_agent.gui.main_window import MainWindow
    window = MainWindow(services)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_gui())

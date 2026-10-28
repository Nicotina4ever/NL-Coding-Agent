"""U2 project/activity state, self-build placement and design-token guards."""
from __future__ import annotations
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

REPO = Path(__file__).resolve().parents[1]


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app = QApplication.instance()
    if app is not None:
        for widget in app.allWidgets():
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                continue
        app.processEvents()


def test_projects_self_build_absent_from_prominent_actions_but_available():
    from nl_coding_agent.gui.widgets.projects_panel import ProjectsPanel

    _app()
    services = SimpleNamespace(list_recent_projects=lambda: [])
    panel = ProjectsPanel(services)
    assert panel._self_build_btn.objectName() == "subtleLinkButton"
    assert "Advanced self-build" in panel._self_build_btn.text()
    assert "Self-Build (This Agent)" not in panel._self_build_btn.text()
    assert "Settings > Advanced" in panel._self_build_btn.toolTip()
    assert "Self-Build (This Agent)" not in [
        button.text() for button in panel.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)]


def test_selected_vs_opened_project_identity_is_unambiguous():
    from nl_coding_agent.gui.widgets.projects_panel import ProjectsPanel

    _app()
    projects = [{"id": 1, "name": "One", "root": "X:/one", "last_used": "now"},
                {"id": 2, "name": "Two", "root": "X:/two", "last_used": "now"}]
    services = SimpleNamespace(list_recent_projects=lambda: [dict(p) for p in projects])
    panel = ProjectsPanel(services)
    panel.set_opened_project(projects[0])
    panel._list.setCurrentRow(1)
    text = panel._identity_label.text()
    assert "Opened: One" in text
    assert "Selected: Two" in text
    assert "differs" in text
    assert panel._identity_label.accessibleName()


def test_settings_advanced_contains_self_build_activation_and_design_tokens():
    from nl_coding_agent.gui.theme import component_qss, design_tokens, load_tokens

    _app()
    import tempfile
    os.environ["NL_DATA_DIR"] = tempfile.mkdtemp(prefix="nl-u2-")
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel
    services = AppServices()
    settings = SettingsPanel(services)
    try:
        assert settings._advanced_group is not None
        assert "Self-Build (This Agent)" in settings._self_build_heading.text()
        assert "Advanced" in settings._advanced_group.accessibleName()
    finally:
        settings.deleteLater()
        services._db.close()
        QApplication.processEvents()
    tokens = load_tokens()
    derived = design_tokens(tokens)
    assert derived["typography"]["title"] == "16px"
    assert derived["spacing"]["md"] == 12
    qss = component_qss(tokens)
    assert "#nlSummaryCard" in qss and "#nlStatusBadge" in qss
    for forbidden in ("#ff0000", "#00ff00", "#0000ff", "text-shadow", "box-shadow"):
        assert forbidden not in qss.lower()

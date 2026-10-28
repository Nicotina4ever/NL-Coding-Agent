"""Tests for Studio UI internationalization (U1)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture()
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui import i18n
    i18n.reset_i18n()
    app_services = AppServices()
    yield app_services
    try:
        app_services._db.close()
    except Exception:
        pass
    i18n.reset_i18n()


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_catalog_loader_defaults_and_supported_languages(services):
    from nl_coding_agent.gui.i18n import TranslationService
    service = TranslationService(services)
    assert service.current_language == "it"
    assert service.preference == "it"
    assert service.supported_codes()[:2] == ["it", "en"]
    names = {item["code"]: item["name"] for item in service.supported_languages()}
    assert names["it"] == "Italiano"
    assert names["en"] == "English"
    assert service.tr("sidebar.projects", "Projects") == "Progetti"
    assert service.tr("projects.open", "Open Project…") == "Apri progetto…"
    assert service.tr("settings.title", "Settings") == "Impostazioni"


def test_english_catalog_and_english_fallback(services, tmp_path):
    from nl_coding_agent.gui.i18n import TranslationService
    # A catalog with a missing Italian key falls back to English, then source.
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    (locale_dir / "it.json").write_text(json.dumps({
        "locale": "it", "name": "Italiano", "version": 1,
        "strings": {"only.italian": "Solo italiano"}}), encoding="utf-8")
    (locale_dir / "en.json").write_text(json.dumps({
        "locale": "en", "name": "English", "version": 1,
        "strings": {"only.english": "English fallback", "both": "Both"}}),
        encoding="utf-8")
    service = TranslationService(services, catalog_dir=locale_dir)
    assert service.tr("only.english") == "English fallback"
    assert service.tr("only.italian") == "Solo italiano"
    assert service.tr("missing.key", "Source fallback") == "Source fallback"
    assert service.tr("missing.key") == "missing.key"
    settings = service.set_language("en")
    assert settings["language"] == "en"
    assert service.tr("only.english") == "English fallback"
    assert service.set_language("it")["language"] == "it"


def test_placeholders_and_missing_placeholder_safety(services):
    from nl_coding_agent.gui.i18n import TranslationService, format_message
    service = TranslationService(services)
    assert service.tr("status.tasks_count", "Tasks: {running} running, {pending} pending",
                      running=2, pending=3) == "Attività: 2 in esecuzione, 3 in attesa"
    assert service.tr("inspector.last_used", "Last used: {value}",
                      value="now") == "Ultimo utilizzo: now"
    assert format_message("Hello {name} {unknown}", name="x") == "Hello x {unknown}"
    assert "{name}" in service.tr("no.placeholder", default="Value {name}")


def test_resolution_preference_system_and_default(services):
    from nl_coding_agent.gui.i18n import TranslationService
    assert TranslationService(services).current_language == "it"
    services.set_ui_language("en")
    assert TranslationService(services).current_language == "en"
    services.set_ui_language("system")
    assert TranslationService(services, system_locale="en_US").current_language == "en"
    assert TranslationService(services, system_locale="it_IT").current_language == "it"
    assert TranslationService(services, system_locale="de_DE").current_language == "it"
    assert TranslationService(
        services, system_locale="de_DE").resolve_language("bogus") == "it"


def test_persistence_restart_and_appservices_reconstruction(services):
    assert services.ui_language_preference() == "it"
    assert services.get_ui_language() == "it"
    assert services.set_ui_language("en")["ok"] is True
    assert services.ui_language_preference() == "en"
    # Reconstruct AppServices against the same NL_DATA_DIR.
    from nl_coding_agent.app.services import AppServices
    services._db.close()
    rebuilt = AppServices()
    try:
        assert rebuilt.get_ui_language() == "en"
        assert rebuilt.get_runtime_settings().get("model_config_path")
    finally:
        rebuilt._db.close()
    # Unsupported values are rejected without a destructive DB change.
    assert rebuilt.set_ui_language("de")["ok"] is False
    assert services.set_ui_language("it")["ok"] is True


def test_ui_language_is_separate_from_agent_and_code_settings(services):
    before = dict(services.get_runtime_settings())
    services.set_ui_language("en")
    after = dict(services.get_runtime_settings())
    for key in ("model_config_path", "ollama_base_url", "database_path"):
        assert before.get(key) == after.get(key)
    # No agent response/code language fields are changed by the UI preference.
    assert "agent_language" not in after
    assert "response_language" not in after
    source = (REPO_ROOT / "nl_coding_agent" / "gui" / "i18n.py").read_text(
        encoding="utf-8")
    for forbidden in ("prompt", "ollama", "crewai", "requests", "urllib",
                      "socket", "http.client"):
        assert forbidden not in source.lower()


def test_qtranslator_retranslation_and_live_widget_switch(services):
    app = _app()
    from PySide6.QtCore import QCoreApplication
    from nl_coding_agent.gui.i18n import get_i18n
    from nl_coding_agent.gui.main_window import MainWindow
    from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel

    i18n = get_i18n(services)
    i18n.install(app)
    assert i18n.current_language == "it"
    window = MainWindow(services)
    try:
        assert window._settings_panel._title.text() == "Impostazioni"
        assert window._settings_panel._project_value.text() == "Nessun progetto aperto"
        assert window._project_label.text() == "Nessun progetto aperto"
        assert window._sidebar._buttons["projects"].text() == "Progetti"
        assert window._i18n.current_language == "it"
        assert QCoreApplication.translate("ctx", "Projects") == "Progetti"
        combo = window._settings_panel._language_value
        combo.setCurrentIndex(combo.findData("en"))
        app.processEvents()
        assert window._i18n.current_language == "en"
        assert window._settings_panel._title.text() == "Settings"
        assert window._settings_panel._project_value.text() == "No project open"
        assert window._project_label.text() == "No project open"
        assert window._sidebar._buttons["projects"].text() == "Projects"
        assert QCoreApplication.translate("ctx", "Projects") == "Projects"
        assert services.ui_language_preference() == "en"
        combo.setCurrentIndex(combo.findData("system"))
        app.processEvents()
        assert window._i18n.preference == "system"
        assert window._i18n.current_language in ("it", "en")
    finally:
        window.close()
        app.processEvents()


def test_open_project_dialog_principal_strings_live_switch(services):
    from nl_coding_agent.gui.dialogs.open_project import OpenProjectDialog
    from nl_coding_agent.gui.i18n import TranslationService
    _app()
    translator = TranslationService(services)
    dialog = OpenProjectDialog(services, translator=translator)
    try:
        assert dialog.windowTitle() == "Apri progetto"
        assert dialog._prompt.text().startswith("Seleziona la cartella")
        translator.set_language("en")
        dialog.retranslate()
        assert dialog.windowTitle() == "Open Project"
        assert dialog._prompt.text().startswith("Select the folder")
    finally:
        dialog.close()
        dialog.deleteLater()



def test_language_selection_survives_restart(services):
    app = _app()
    from nl_coding_agent.gui.i18n import get_i18n, reset_i18n
    from nl_coding_agent.gui.main_window import MainWindow
    from nl_coding_agent.app.services import AppServices

    get_i18n(services).set_language("en")
    services._db.close()
    rebuilt = AppServices()
    try:
        reset_i18n()
        window = MainWindow(rebuilt)
        try:
            assert window._i18n.current_language == "en"
            assert window._settings_panel._title.text() == "Settings"
            assert window._settings_panel._project_value.text() == "No project open"
        finally:
            window.close()
            app.processEvents()
    finally:
        rebuilt._db.close()

def test_static_no_network_or_model_in_gui_i18n():
    gui = REPO_ROOT / "nl_coding_agent" / "gui"
    for name in ("i18n.py", "main_window.py", "widgets/sidebar.py",
                 "widgets/settings_panel.py", "widgets/projects_panel.py",
                 "widgets/inspector_panel.py", "dialogs/open_project.py"):
        source = (gui / name).read_text(encoding="utf-8")
        for forbidden in ("import requests", "from requests", "import urllib",
                          "import socket", "http.client", "import crewai",
                          "from crewai"):
            assert forbidden not in source, (name, forbidden)

"""F1 chat panel: drag/drop, Ctrl+V, previews/removal, explicit submit, integration."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices

    instance = AppServices()
    yield instance
    try:
        instance._db.close()
    except Exception:
        pass


@pytest.fixture()
def panel(services, tmp_path):
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel

    _app()
    widget = ChatPanel(services)
    widget.set_project({"id": 1, "root": str(tmp_path), "name": "demo"})
    yield widget
    widget.deleteLater()
    _app().processEvents()


class FakeDropEvent:
    def __init__(self, mime):
        self._mime = mime
        self.accepted = False

    def mimeData(self):  # noqa: N802 - Qt API shape
        return self._mime

    def acceptProposedAction(self):  # noqa: N802 - Qt API shape
        self.accepted = True


def test_panel_has_accessible_controls_and_shortcuts(panel):
    from PySide6.QtGui import QShortcut

    assert panel._input.accessibleName() == "Chat message"
    assert panel._attach_btn.accessibleName() == "Attach files"
    assert panel._submit_btn.accessibleName() == "Send message"
    assert panel._attachments_list.accessibleName() == "Prepared attachments"
    assert "Ctrl+Enter" in panel._hint.text()
    shortcuts = {shortcut.key().toString() for shortcut in panel.findChildren(QShortcut)}
    assert not any("Ctrl+Enter" in item or "Ctrl+Return" in item for item in shortcuts)


def test_tool_consent_is_one_turn_and_clears_on_project_switch(panel):
    payloads = []
    panel.submitted.connect(payloads.append)
    panel._tools_enabled.setChecked(True)
    panel._coding_enabled.setChecked(True)
    panel._input.setPlainText("Change source with tools")
    panel._submit()
    assert payloads[-1]["tool_options"]["tools_enabled"]
    assert payloads[-1]["tool_options"]["allow_coding"]
    assert not panel._tools_enabled.isChecked()
    assert not panel._coding_enabled.isChecked()
    panel._tools_enabled.setChecked(True)
    panel._coding_enabled.setChecked(True)
    panel._research_profile.setCurrentIndex(1)
    panel.set_project({"id": 2, "root": "other", "name": "other"})
    assert not panel._tools_enabled.isChecked() and not panel._coding_enabled.isChecked()
    assert panel._research_profile.currentData() == "manual"
    assert panel._project_label.text()  # project root is displayed


def test_add_text_and_paths_prepare_in_background_and_preview(panel, tmp_path):
    panel.add_text("pasted context")
    assert panel._pending == 1
    assert panel.wait_for_idle()
    assert len(panel.attachments) == 1 and panel.attachments[0]["kind"] == "text"
    assert panel._attachments_list.count() == 1

    (tmp_path / "one.py").write_text("x = 1\n", encoding="utf-8")
    folder = tmp_path / "bundle"
    folder.mkdir()
    (folder / "two.txt").write_text("two", encoding="utf-8")
    panel.add_paths([tmp_path / "one.py", folder], source="drop")
    assert panel.wait_for_idle()
    names = {item["name"] for item in panel.attachments}
    assert {"pasted-text.txt", "one.py", "two.txt"} <= names
    assert panel._attachments_list.count() == len(panel.attachments)

    panel._attachments_list.setCurrentRow(0)
    panel._remove_selected()
    assert panel._attachments_list.count() == len(panel.attachments)


def test_drag_drop_urls_are_accepted(panel, tmp_path):
    file_path = tmp_path / "dropped.log"
    file_path.write_text("log line", encoding="utf-8")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(file_path))])
    event = FakeDropEvent(mime)
    panel.dropEvent(event)
    assert event.accepted is True
    assert panel.wait_for_idle()
    assert panel.attachments and panel.attachments[-1]["kind"] == "log"


def test_ctrl_v_pastes_text_files_and_images(panel, tmp_path):
    clipboard = QApplication.clipboard()
    clipboard.setText("clipboard mission text")
    QTest.keyClick(panel._input, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert "clipboard mission text" in panel._input.toPlainText()
    assert panel.attachments == []  # plain text pastes into the message, not an attachment

    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.magenta)
    clipboard.setImage(image)
    QTest.keyClick(panel._input, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert panel.wait_for_idle()
    assert panel.attachments[-1]["kind"] == "image"

    file_path = tmp_path / "pasted.json"
    file_path.write_text('{"a": 1}', encoding="utf-8")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(file_path))])
    clipboard.setMimeData(mime)
    QTest.keyClick(panel._input, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert panel.wait_for_idle()
    assert panel.attachments[-1]["kind"] == "json"
    # Clipboard owns mime data; clear it before Qt teardown to avoid a stale-object crash.
    clipboard.clear()


def test_explicit_submit_emits_once_and_never_auto_submits(panel):
    received = []
    panel.submitted.connect(received.append)
    panel._input.setPlainText("Build the feature")
    _app().processEvents()
    assert received == []  # typing never submits
    panel.add_text("attachment body")
    assert panel.wait_for_idle()
    panel._submit()
    assert len(received) == 1
    payload = received[0]
    assert payload["text"] == "Build the feature"
    assert len(payload["attachment_ids"]) == 1
    assert panel.attachments == []

    panel._input.clear()
    panel._submit()  # nothing to submit: no second signal
    assert len(received) == 1


def test_enter_sends_and_ctrl_enter_inserts_newline(panel):
    received = []
    panel.submitted.connect(received.append)
    panel._input.setPlainText("A question about tests")
    QTest.keyClick(panel._input, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert received == []
    assert "\n" in panel._input.toPlainText()
    QTest.keyClick(panel._input, Qt.Key.Key_Return)
    assert len(received) == 1
    assert received[0]["action"] == "chat"


def test_main_window_integration_persists_mission_and_attachments(services, tmp_path):
    from nl_coding_agent.gui.main_window import MainWindow
    from nl_coding_agent.persistence.missions import list_missions
    from nl_coding_agent.projects.registry import open_project

    app = _app()
    root = tmp_path / "project"
    root.mkdir()
    project = open_project(root)
    attachment = services.prepare_attachment_text(project["id"], "attached context")
    # The GUI must not call any model/network in this test: stub the local status prober.
    services.check_ollama = lambda: False
    window = MainWindow(services)
    window._on_project_opened(project)
    window._on_chat_submitted({"text": "Implement the mission", "action": "coding",
                               "attachment_ids": [attachment["id"]]})
    missions = list_missions(int(project["id"]))
    assert missions and missions[0]["goal"] == "Implement the mission"
    stored = services.list_mission_attachments(mission_id=missions[0]["id"])
    assert len(stored) == 1 and stored[0]["extracted_text"] == "attached context"
    assert window._stack.currentWidget() is window._workspace
    assert window._workspace.docks["tasks"].panel is window._tasks_panel
    window.close()
    app.processEvents()
    from nl_coding_agent.gui.i18n import reset_i18n
    reset_i18n()


def test_main_window_document_request_opens_plan_without_coding(services, tmp_path, monkeypatch):
    from nl_coding_agent.gui.main_window import MainWindow
    from nl_coding_agent.gui.dialogs.document_plan import DocumentPlanDialog
    from nl_coding_agent.projects.registry import open_project
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# Requirements\n- The system must work offline.\n")
    project = open_project(root)
    services.check_ollama = lambda: False

    window = MainWindow(services)
    window._on_project_opened(project)
    window._on_chat_submitted({"text": "Analizza la documentazione e prepara un piano", "action": "document_plan"})
    assert window._document_panel._generation_thread.wait(5000)
    _app().processEvents()
    assert window._document_panel._embedded
    assert window._ide_tabs.currentWidget() is window._document_panel
    assert services.docs_plan_get(window._document_panel._plan_id)["plan"]["status"] == "draft"
    assert services.list_missions(project["id"]) == []
    window.close()
    _app().processEvents()


def test_model_selector_updates_payload_and_settings(services, tmp_path):
    """Selecting a model in the chat panel should be reflected in the
    submitted payload and persisted in workspace settings.

    The test creates a ChatPanel, injects a dummy model entry into the
    combo, selects it, and verifies that the emitted payload contains the
    chosen model. It also checks that the model string is stored via
    ``studio_settings`` under the ``workspace/chat_model/<project_id>`` key.
    """
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
    from nl_coding_agent.gui.widgets.studio_workspace import studio_settings

    _app()
    widget = ChatPanel(services)
    # Simulate opening a project with a known ID.
    widget.set_project({"id": 42, "root": str(tmp_path), "name": "demo"})

    # Ensure the combo is editable and add a dummy model entry.
    dummy_route = "ollama/qwen3.5:9b"
    widget._model.addItem(dummy_route, dummy_route)
    # Select the dummy model explicitly.
    widget._model.setCurrentText(dummy_route)

    # Capture the submitted payload.
    received = []
    widget.submitted.connect(received.append)

    # Provide a simple message and submit.
    widget._input.setPlainText("Test model selection")
    widget._submit()

    assert len(received) == 1, "ChatPanel should emit exactly one payload"
    payload = received[0]
    assert payload["model"] == dummy_route, "Payload should contain the selected model"

    # Verify the model was persisted in workspace settings.
    stored = studio_settings().value(f"workspace/chat_model/{widget._project['id']}")
    assert stored == dummy_route, "Selected model must be saved in settings"

    # Clean up the widget.
    widget.deleteLater()
    _app().processEvents()


def test_model_button_opens_selection_and_persists(monkeypatch, services, tmp_path):
    """Pressing the *Models…* button should open a selection dialog, update the combo
    and persist the choice via ``studio_settings``.
    """
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
    from nl_coding_agent.gui.widgets.studio_workspace import studio_settings
    from nl_coding_agent.gui.widgets.models_panel import ModelHubFetchThread

    # Stub the thread to emit a deterministic snapshot.
    class DummySignal:
        def __init__(self):
            self._cb = None
        def connect(self, cb):
            self._cb = cb
        def emit(self, *args):
            if self._cb:
                self._cb(*args)

    class DummyThread:
        def __init__(self, services, parent=None):
            self.services = services
            self.parent = parent
            self.snapshot_ready = DummySignal()
            self.failed = DummySignal()
        def isRunning(self):
            return False
        def start(self):
            # Simple snapshot with one local model.
            class Model:
                def __init__(self, name):
                    self.name = name
            class Provider:
                def __init__(self, pid, models):
                    self.provider_id = pid
                    self.models = models
            snapshot = type('Snap', (), {'providers': [Provider('local', [Model('demo')])]} )()
            self.snapshot_ready.emit(snapshot)

    monkeypatch.setattr('nl_coding_agent.gui.widgets.chat_panel.ModelHubFetchThread', DummyThread)

    # Stub QInputDialog to auto‑select the offered model.
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs: ('local/demo', True))

    _app()
    widget = ChatPanel(services)
    widget.set_project({"id": 99, "root": str(tmp_path), "name": "demo"})
    # Ensure no prior setting.
    settings = studio_settings()
    settings.remove(f"workspace/chat_model/99")
    # Click the discover button which triggers the dialog.
    widget._discover_btn.click()
    # The combo should now reflect the chosen model.
    assert widget._model.currentText() == "local/demo"
    # And the setting should be persisted.
    assert settings.value(f"workspace/chat_model/99") == "local/demo"
    widget.deleteLater()
    _app().processEvents()

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

    assert panel._input.accessibleName() == "Mission message"
    assert panel._attach_btn.accessibleName() == "Attach files"
    assert panel._submit_btn.accessibleName() == "Submit mission"
    assert panel._attachments_list.accessibleName() == "Prepared attachments"
    assert "Ctrl+Enter" in panel._hint.text()
    shortcuts = {shortcut.key().toString() for shortcut in panel.findChildren(QShortcut)}
    assert any("Ctrl+Enter" in item or "Ctrl+Return" in item for item in shortcuts)
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


def test_ctrl_enter_shortcut_is_wired_to_explicit_submit(panel):
    from PySide6.QtGui import QShortcut

    received = []
    panel.submitted.connect(received.append)
    panel._input.setPlainText("ctrl enter mission")
    shortcut = next(
        item for item in panel.findChildren(QShortcut)
        if "Ctrl+Enter" in item.key().toString()
        or "Ctrl+Return" in item.key().toString()
    )
    shortcut.activated.emit()
    assert len(received) == 1


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
    window._on_chat_submitted({"text": "Implement the mission",
                               "attachment_ids": [attachment["id"]]})
    missions = list_missions(int(project["id"]))
    assert missions and missions[0]["goal"] == "Implement the mission"
    stored = services.list_mission_attachments(mission_id=missions[0]["id"])
    assert len(stored) == 1 and stored[0]["extracted_text"] == "attached context"
    assert window._stack.currentIndex() == window._page_index["tasks"]
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
    opened = []
    monkeypatch.setattr(DocumentPlanDialog, "exec", lambda self: opened.append(self._plan_id))
    window = MainWindow(services)
    window._on_project_opened(project)
    window._on_chat_submitted({"text": "Analizza la documentazione e prepara un piano"})
    assert len(opened) == 1
    assert services.docs_plan_get(opened[0])["plan"]["status"] == "draft"
    assert services.list_missions(project["id"]) == []
    window.close()
    _app().processEvents()

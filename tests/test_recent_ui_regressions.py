"""Exercise actual widgets at the boundaries missed by construction smoke tests."""
import threading
import time

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QDialog


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    services = AppServices()
    monkeypatch.setattr(services, "check_ollama", lambda: False)
    widget = MainWindow(services)
    widget._initial_ollama_timer.stop()
    widget._current_project = {"id": 1, "root": str(tmp_path), "name": "demo"}
    yield widget
    widget.close()
    app.processEvents()


def test_file_open_reuses_editor_without_sending_chat_context(window, tmp_path):
    (tmp_path / "sample.py").write_text("value = 1\n", encoding="utf-8")
    window._on_file_opened("sample.py")
    assert window._editor_panel._tabs_widget.currentWidget().toPlainText() == "value = 1\n"
    assert window._stack.currentWidget() is window._workspace
    assert window._ide_tabs.currentWidget() is window._editor_panel
    assert window._sidebar._buttons["ide"].isChecked()
    assert window._chat_panel.attachments == []
    assert window._chat_panel._pending == 0


def test_new_custom_agent_saves_values_once(window, monkeypatch):
    from nl_coding_agent.gui.dialogs import custom_agents

    class Edit:
        def __init__(self, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"name": "My reviewer", "role": "reviewer", "model": "local-model"}

    monkeypatch.setattr(custom_agents, "_EditDialog", Edit)
    dialog = custom_agents.CustomAgentsDialog(window._services)
    dialog._new()
    agents = window._services.list_custom_agents()
    assert [(item["name"], item["model"]) for item in agents] == [("My reviewer", "local-model")]
    assert dialog._list.count() == 1


def test_pending_reply_cannot_leak_into_another_project_or_destroy_running_thread(window, monkeypatch):
    release = threading.Event()

    def reply(*args):
        assert release.wait(5), "test did not release chat worker"
        return {"ok": True, "reply": "Reply for project one"}

    monkeypatch.setattr(window._services, "chat_conversation", reply)
    window._run_chat_conversation("hello", [])
    thread = window._chat_reply_threads[0]
    try:
        assert not window._chat_panel._input.isEnabled()
        submissions = []
        window._chat_panel.submitted.connect(submissions.append)
        window._chat_panel._input.setPlainText("Do not send twice")
        window._chat_panel._on_prepared({"attachments": [], "errors": []})
        assert not window._chat_panel._submit_btn.isEnabled()
        window._chat_panel._submit()
        assert submissions == []
        assert window._chat_panel._input.toPlainText() == "Do not send twice"
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted()
        assert not window._closing
        window._current_project = {"id": 2, "root": "other-project"}
    finally:
        release.set()
        assert thread.wait(5000)
    deadline = time.monotonic() + 3
    while window._chat_reply_threads and time.monotonic() < deadline:
        QApplication.processEvents()
    assert window._chat_reply_threads == []
    assert window._chat_panel._input.isEnabled()
    assert "Reply for project one" not in window._chat_panel._transcript.toPlainText()


def test_dirty_editor_cancel_preserves_entire_window_project_and_close(window, tmp_path):
    (tmp_path / "sample.py").write_text("original\n", encoding="utf-8")
    first = window._current_project
    window._editor_panel.set_project(first)
    window._editor_panel.open_file("sample.py")
    window._editor_panel.modify_current("unsaved\n")
    window._editor_panel._confirm = lambda path: False
    label_before = window._project_label.text()
    window._on_project_opened({"id": 2, "root": str(tmp_path / "other"), "name": "other"})
    assert window._current_project == first
    assert window._project_label.text() == label_before
    assert window._editor_panel._project == first
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert not window._closing
    assert window._editor_panel._tabs_widget.currentWidget().toPlainText() == "unsaved\n"


def test_mission_delete_refreshes_chat_goals_inspector_and_task_board(
        window, tmp_path, monkeypatch):
    from nl_coding_agent.persistence.missions import create_mission

    root = tmp_path / "mission-project"
    root.mkdir()
    project = window._services.open_project(root)
    window._on_project_opened(project)
    mission_id = create_mission(project["id"], "Remove me", "Delete this mission")
    mission = window._services.get_mission_details(mission_id)
    window._inspector.show_mission(mission)

    goal_refreshes = []
    task_refreshes = []
    monkeypatch.setattr(
        window._goals_panel, "refresh", lambda: goal_refreshes.append(True))
    monkeypatch.setattr(
        window._tasks_panel, "refresh", lambda: task_refreshes.append(True))
    window._services.delete_mission(mission_id, project_id=project["id"])
    QApplication.processEvents()

    assert "Deleted mission #" + str(mission_id) in (
        window._chat_panel._transcript.toPlainText())
    assert goal_refreshes
    assert task_refreshes
    assert window._inspector._last_render[0] == "project"
    window._editor_panel._confirm = lambda path: True

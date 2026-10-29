"""Project-context and keyboard acceptance across real composed Studio panels."""
import threading

import pytest
from PySide6.QtCore import Qt
from nl_coding_agent.gui.widgets.studio_workspace import studio_settings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "generated"))
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    services = AppServices()
    monkeypatch.setattr(services, "check_ollama", lambda: False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "code.py").write_text("value = 1\n")
    (root / "README.md").write_text("# Requirements\n- The system must work offline.\n")
    window = MainWindow(services)
    window._initial_ollama_timer.stop()
    window.resize(1500, 950)
    window.show()
    window._on_project_opened(services.open_project(root))
    QTest.qWait(20)
    yield window
    window._editor_panel._confirm = lambda path: True
    window.close()
    app.processEvents()
    services._db.close()


def test_chat_shortcut_cannot_activate_visible_terminal(studio, monkeypatch):
    terminal_calls = []
    # Intercept the execution boundary; this must never be reached by Chat keys.
    monkeypatch.setattr(studio._services, "terminal_policy",
                        lambda *args: terminal_calls.append(args) or {"allowed": False})
    studio._terminal_panel._input.setText("python --version")
    studio._switch_page("chat")
    composer = studio._chat_panel._input
    composer.setFocus()
    composer.setPlainText("A question about tests")
    QTest.qWait(20)
    QTest.keyClick(composer, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert "\n" in composer.toPlainText()
    assert not terminal_calls
    assert not studio._services.list_missions(studio._current_project["id"])
    studio._terminal_panel._input.setFocus()
    QTest.qWait(20)
    QTest.keyClick(studio._terminal_panel._input, Qt.Key.Key_Return,
                   Qt.KeyboardModifier.ControlModifier)
    assert len(terminal_calls) == 1


def test_questions_and_unknown_actions_do_not_create_missions(studio, monkeypatch):
    conversations = []
    monkeypatch.setattr(studio, "_run_chat_conversation", lambda *args: conversations.append(args))
    for text in ("How do these tests build the project?", "Analizza la documentazione e prepara un piano"):
        studio._on_chat_submitted({"text": text})
    studio._on_chat_submitted({"text": "do something", "action": "unsupported"})
    assert len(conversations) == 2
    assert studio._services.list_missions(studio._current_project["id"]) == []


def test_cancel_goal_preserves_actual_composer_request(studio, monkeypatch):
    from nl_coding_agent.gui.widgets.goals_panel import CreateGoalDialog
    seen = []
    def cancel(dialog):
        seen.append(dialog._objective.toPlainText())
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(CreateGoalDialog, "exec", cancel)
    composer = studio._chat_panel
    composer._action.setCurrentIndex(composer._action.findData("goal"))
    composer._input.setPlainText("My objective must survive Cancel")
    composer._submit()
    assert seen == ["My objective must survive Cancel"]
    assert composer._input.toPlainText() == seen[0]
    assert studio._services.list_missions(studio._current_project["id"]) == []


def test_late_attachment_result_cannot_cross_projects(studio, monkeypatch):
    composer = studio._chat_panel
    started, release = threading.Event(), threading.Event()
    def prepare():
        started.set()
        assert release.wait(3)
        return {"attachments": [{"id": 123, "name": "old project context"}]}
    composer._start(prepare)
    assert started.wait(3)
    composer.set_project({"id": 9999, "name": "Other", "root": "."})
    release.set()
    assert composer.wait_for_idle()
    assert composer.attachments == []


def test_saved_plan_loads_in_tab_with_consistent_status(studio):
    project = studio._current_project
    plan = studio._services.docs_plan_generate(project_root=project["root"], project_id=project["id"])
    assert plan["ok"]
    studio._open_document_plan()
    panel = studio._document_panel
    assert panel._plan_id == plan["plan_id"]
    assert panel._milestone_table.rowCount() > 0
    assert "DRAFT" in panel._status.text()
    assert "No plan loaded" not in panel._status.text()
    QTest.keyClick(panel, Qt.Key.Key_Escape)
    assert not panel.isVisible()
    assert studio._document_panel is panel
    studio._switch_page("ide")
    assert studio._ide_tabs.currentWidget() is studio._editor_panel
    assert studio._chat_panel.isVisible()


def test_close_reopen_restores_project_file_and_hidden_dock(studio):
    from nl_coding_agent.gui.main_window import MainWindow
    studio._on_file_opened("code.py")
    studio._workspace.docks["files"].hide()
    project = dict(studio._current_project)
    studio.close()
    app = QApplication.instance()
    app.processEvents()
    reopened = MainWindow(studio._services)
    reopened.show()
    QTest.qWait(40)
    try:
        assert reopened._current_project is not None, (studio_settings().value("workspace/project"), reopened._log_panel._output.toPlainText())
        assert reopened._current_project["id"] == project["id"]
        assert reopened._editor_panel._tabs_widget.currentWidget().rel_path == "code.py"
        assert reopened._workspace.docks["files"].isHidden()
        reopened._switch_page("files")
        assert reopened._files_panel.isVisible()
        assert reopened._chat_panel.isVisible()
        assert reopened._editor_panel.isVisible()
    finally:
        reopened.close()
        app.processEvents()


def test_historical_document_mission_is_hidden_and_never_rerun(studio):
    from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
    from nl_coding_agent.persistence.missions import get_handoffs
    project = studio._current_project
    mission = studio._services.create_mission(project["id"], "Old document request",
                                              "Analizza la documentazione e prepara un piano")
    orchestrator = MultiAgentOrchestrator(project["root"], project_id=project["id"])
    assert orchestrator.run_mission(mission)["status"] == "blocked"
    count = len(get_handoffs(mission))
    assert count > 0
    assert orchestrator.run_mission(mission)["status"] == "blocked"
    assert len(get_handoffs(mission)) == count
    studio._on_project_opened(project)
    assert studio._tasks_panel._mission_list.count() == 0
    studio._tasks_panel._history_toggle.setChecked(True)
    assert studio._tasks_panel._mission_list.count() == 1
    assert not studio._tasks_panel._run_btn.isEnabled()
    assert len(get_handoffs(mission)) == count


def test_event_bus_unsubscribes_bound_method():
    from nl_coding_agent.app.services import Event, EventBus
    class Listener:
        def __init__(self):
            self.events = []
        def receive(self, event):
            self.events.append(event)
    listener, bus = Listener(), EventBus()
    bus.subscribe(listener.receive)
    bus.unsubscribe(listener.receive)
    bus.emit(Event("test", "info", "once"))
    assert listener.events == []

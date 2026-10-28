"""Tests for the stage-4 GUI safety controls (NL-BP-023/024).

Covered here:
* Settings > Advanced self-build controls (mode, limits, read-only plan/history,
  explicit Save/Apply, cooperative Pause/Stop) and the guarantee that nothing
  starts automatically when a panel/window is constructed or settings are saved.
* The always-reachable emergency Pause/Stop widget outside Settings: hidden while
  idle, visible only for an active supervisor run, confirmation on stop,
  cooperative backend calls, clear result/error messages and accessibility labels.
* AppServices wrappers around the existing supervisor/backlog/history APIs.

No model, network or real supervisor process is started by any test: all GUI tests
use a fake services object, and the AppServices tests only read/write settings in a
throw-away SQLite database under NL_DATA_DIR.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTableWidget


class FakeServices:
    """Deterministic stand-in for AppServices; records every backend call."""

    def __init__(self) -> None:
        self.saved: list[dict] = []
        self.pause_calls: list[int] = []
        self.stop_calls: list[dict] = []
        self.start_calls: list[dict] = []
        self.status_calls = 0
        self.mode = "off"
        self.max_missions = 1
        self.attempts = 2
        self.wall_s = 3600
        self.save_error: str | None = None
        self.pause_error: str | None = None
        self.stop_error: str | None = None
        self.history: list[dict] = []
        self.plan_override: dict | None = None
        self.status = {
            "status": "idle",
            "run": None,
            "service": {"thread_running": False},
            "resume_command": "",
        }

    # ---- read-only runtime settings shown by the SettingsPanel
    def get_runtime_settings(self, project_root=None) -> dict:
        return {
            "project_root": project_root or "",
            "database_path": "db.sqlite3",
            "ollama_base_url": "http://127.0.0.1:11434",
            "model_config_path": "models.yaml",
            "cloud_escalation_enabled": False,
        }

    def get_permissions(self, project_id=None) -> dict:
        return {
            "scopes": ["read", "write", "execute", "delete", "network", "cloud"],
            "policy": {"read": True, "write": True, "execute": True,
                       "delete": False, "network": False, "cloud": False},
        }

    # ---- autonomy backend surface
    def autonomy_settings(self, project_id: int) -> dict:
        return {
            "ok": True, "read_only": True, "starts_automatically": False,
            "project_id": int(project_id), "mode": self.mode,
            "max_missions_per_run": self.max_missions,
            "max_attempts_per_requirement": self.attempts,
            "max_wall_time_s": self.wall_s,
            "mission_wall_time_s": 1800,
            "resume_command": "python nl_agent.py supervisor run",
        }

    def save_autonomy_settings(self, project_id: int, **kwargs) -> dict:
        self.saved.append({"project_id": int(project_id), "kwargs": dict(kwargs)})
        if self.save_error:
            return {"ok": False, "started": False, "error": self.save_error}
        if "mode" in kwargs:
            self.mode = str(kwargs["mode"])
        if "max_missions" in kwargs:
            self.max_missions = int(kwargs["max_missions"])
        if "attempts" in kwargs:
            self.attempts = int(kwargs["attempts"])
        if "max_wall_time_s" in kwargs:
            self.wall_s = int(kwargs["max_wall_time_s"])
        return {"ok": True, "started": False, "project_id": int(project_id),
                "saved": dict(kwargs), "mode": self.mode}

    def autonomy_plan(self, project_id: int) -> dict:
        if self.plan_override is not None:
            return dict(self.plan_override)
        return {
            "ok": True, "read_only": True, "starts_automatically": False,
            "project_id": int(project_id), "mode": self.mode,
            "settings": self.autonomy_settings(project_id),
            "program_stage": 1,
            "queue_counts": {"READY": 2, "VERIFIED": 1},
            "next_requirements": [
                {"requirement_id": "NL-BP-023",
                 "title": "Self-build controls under Settings > Advanced",
                 "priority": "P1"},
            ],
            "active_run": None,
            "resume_command": "python nl_agent.py supervisor run",
        }

    def autonomy_history(self, project_id: int, limit: int = 10) -> list[dict]:
        return list(self.history)[: int(limit)]

    def supervisor_status(self, project_id: int) -> dict:
        self.status_calls += 1
        return dict(self.status)

    def supervisor_start(self, project_id: int, *, mode=None, max_missions=None) -> dict:
        self.start_calls.append({"project_id": project_id, "mode": mode,
                                 "max_missions": max_missions})
        return {"ok": True, "state": "running"}

    def supervisor_pause(self, project_id: int) -> dict:
        self.pause_calls.append(int(project_id))
        if self.pause_error:
            return {"ok": False, "error": self.pause_error}
        return {"ok": True, "command_id": 1}

    def supervisor_stop(self, project_id: int, *, reason: str = "") -> dict:
        self.stop_calls.append({"project_id": int(project_id), "reason": reason})
        if self.stop_error:
            return {"ok": False, "error": self.stop_error}
        return {"ok": True, "command_id": 2}


def _active_status() -> dict:
    return {
        "status": "running",
        "run": {"id": 3, "status": "RUNNING", "mode": "assisted"},
        "service": {"thread_running": True},
        "resume_command": "python nl_agent.py supervisor run --resume",
    }


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def fake() -> FakeServices:
    return FakeServices()


def _panel(fake: FakeServices, *, project: bool = True):
    from nl_coding_agent.gui.widgets.settings_panel import SettingsPanel

    panel = SettingsPanel(fake)
    if project:
        panel.set_project({"id": 1, "root": "/tmp/project"})
    return panel


def _emergency(fake: FakeServices, *, project: bool = True):
    from nl_coding_agent.gui.main_window import EmergencyControls

    widget = EmergencyControls(fake)
    if project:
        widget.set_project({"id": 1, "root": "/tmp/project"})
    return widget


# --------------------------------------------------------------------------- #
# Settings > Advanced controls
# --------------------------------------------------------------------------- #

def test_advanced_controls_exist_and_are_read_only(qapp, fake):
    panel = _panel(fake)

    assert panel._advanced_group.accessibleName() == "Advanced self-build and autonomy controls"
    assert panel._advanced_mode_combo.count() == 3
    assert [panel._advanced_mode_combo.itemData(i) for i in range(3)] == [
        "off", "assisted", "automatic"]
    assert panel._advanced_mode_combo.currentData() == "off"
    assert panel._advanced_missions_spin.minimum() == 1
    assert panel._advanced_missions_spin.maximum() == 5
    assert panel._advanced_attempts_spin.minimum() == 1
    assert panel._advanced_attempts_spin.maximum() == 5

    assert panel._advanced_plan_preview.isReadOnly() is True
    assert panel._advanced_plan_preview.accessibleName()
    assert panel._advanced_history_table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers
    assert panel._advanced_history_table.accessibleName()

    for button in (panel._save_advanced_btn, panel._pause_advanced_btn,
                   panel._stop_advanced_btn, panel._refresh_advanced_btn):
        assert button.accessibleName(), button.text()
    # No start control anywhere in Settings: nothing can auto-start a run.
    assert not hasattr(panel, "_start_advanced_btn")
    assert not hasattr(panel, "_start_btn")


def test_constructing_and_saving_never_starts_autonomy(qapp, fake):
    panel = _panel(fake)
    fake.mode = "assisted"
    panel._advanced_mode_combo.setCurrentIndex(1)
    panel._advanced_missions_spin.setValue(2)
    panel._save_advanced_btn.click()
    panel.refresh()
    assert fake.start_calls == []
    assert fake.saved, "save must go through the backend wrapper"


def test_save_applies_mode_and_limits_without_starting(qapp, fake):
    panel = _panel(fake)
    panel._advanced_mode_combo.setCurrentIndex(1)  # Assisted
    panel._advanced_missions_spin.setValue(3)
    panel._advanced_attempts_spin.setValue(4)
    panel._advanced_wall_spin.setValue(10)  # minutes
    panel._save_advanced_btn.click()

    assert fake.saved[-1]["project_id"] == 1
    assert fake.saved[-1]["kwargs"] == {
        "mode": "assisted",
        "max_missions": 3,
        "attempts": 4,
        "max_wall_time_s": 600,
    }
    assert "Saved" in panel._advanced_notice.text()
    assert fake.start_calls == []
    assert fake.mode == "assisted"
    assert fake.max_missions == 3
    assert fake.attempts == 4
    assert fake.wall_s == 600


def test_save_error_is_reported_and_never_starts(qapp, fake):
    fake.save_error = "max_missions_per_run must be within 1..5"
    panel = _panel(fake)
    panel._save_advanced_btn.click()
    notice = panel._advanced_notice.text()
    assert "Save failed" in notice
    assert "max_missions_per_run must be within 1..5" in notice
    assert fake.start_calls == []


def test_plan_and_history_are_read_only_previews(qapp, fake):
    fake.history = [
        {"id": 7, "mode": "assisted", "status": "COMPLETED",
         "missions_completed": 2, "missions_failed": 0,
         "started_at": "2026-10-28T10:00:00", "finished_at": "2026-10-28T10:10:00"},
        {"id": 6, "mode": "off", "status": "STOPPED",
         "missions_completed": 0, "missions_failed": 1,
         "started_at": "2026-10-27T09:00:00", "finished_at": "2026-10-27T09:01:00"},
    ]
    panel = _panel(fake)

    preview = panel._advanced_plan_preview.toPlainText()
    assert "Mode: OFF" in preview
    assert "starts automatically: no" in preview
    assert "NL-BP-023" in preview
    assert "no run is started" in preview.lower() or "no mission" in preview.lower()

    table = panel._advanced_history_table
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "#7"
    assert table.item(0, 1).text() == "assisted"
    assert table.item(0, 2).text() == "COMPLETED"
    assert table.item(0, 3).text() == "2/0"
    assert table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers
    assert fake.start_calls == []


def test_advanced_preview_handles_unavailable_plan(qapp, fake):
    fake.plan_override = {"ok": False, "read_only": True,
                          "starts_automatically": False,
                          "error": "backlog index missing"}
    panel = _panel(fake)
    preview = panel._advanced_plan_preview.toPlainText()
    assert "Preview unavailable" in preview
    assert "backlog index missing" in preview


def test_advanced_pause_uses_cooperative_backend(qapp, fake):
    fake.status = _active_status()
    panel = _panel(fake)
    assert panel._pause_advanced_btn.isEnabled() is True
    panel._pause_advanced_btn.click()
    assert fake.pause_calls == [1]
    assert "Pause requested" in panel._advanced_notice.text()
    assert fake.stop_calls == []
    assert fake.start_calls == []


def test_advanced_stop_requires_confirmation(qapp, fake, monkeypatch):
    import nl_coding_agent.gui.widgets.settings_panel as settings_panel

    fake.status = _active_status()
    panel = _panel(fake)
    assert panel._stop_advanced_btn.isEnabled() is True

    monkeypatch.setattr(
        settings_panel.QMessageBox, "question",
        staticmethod(lambda *a, **k: settings_panel.QMessageBox.StandardButton.No),
    )
    panel._stop_advanced_btn.click()
    assert fake.stop_calls == []
    assert "cancelled" in panel._advanced_notice.text().lower()

    monkeypatch.setattr(
        settings_panel.QMessageBox, "question",
        staticmethod(lambda *a, **k: settings_panel.QMessageBox.StandardButton.Yes),
    )
    panel._stop_advanced_btn.click()
    assert len(fake.stop_calls) == 1
    assert fake.stop_calls[0]["project_id"] == 1
    assert "Settings > Advanced" in fake.stop_calls[0]["reason"]
    assert "Stop requested" in panel._advanced_notice.text()
    assert fake.start_calls == []


# --------------------------------------------------------------------------- #
# Global emergency Pause/Stop widget (outside Settings)
# --------------------------------------------------------------------------- #

def test_emergency_controls_hidden_while_idle(qapp, fake):
    widget = _emergency(fake)
    assert widget.isHidden() is True
    assert widget.is_active() is False
    assert widget._pause_btn.isEnabled() is False
    assert widget._stop_btn.isEnabled() is False

    widget.update_status({"status": "idle", "run": None,
                          "service": {"thread_running": False}})
    assert widget.isHidden() is True

    widget.set_project(None)
    assert widget.isHidden() is True


def test_emergency_controls_visible_only_when_active(qapp, fake):
    widget = _emergency(fake)
    assert widget.update_status(_active_status()) is True
    assert widget.isHidden() is False
    assert widget._pause_btn.isEnabled() is True
    assert widget._stop_btn.isEnabled() is True
    assert "RUNNING" in widget._status_label.text()

    assert widget.update_status({"status": "idle", "run": None,
                                 "service": {"thread_running": False}}) is False
    assert widget.isHidden() is True


def test_emergency_pause_is_cooperative_and_reports_errors(qapp, fake):
    widget = _emergency(fake)
    widget.update_status(_active_status())
    messages: list[tuple[str, str]] = []
    widget.message.connect(lambda level, text: messages.append((level, text)))

    result = widget.request_pause()
    assert result["ok"] is True
    assert fake.pause_calls == [1]
    assert any("Pause requested" in text for _level, text in messages)
    assert widget._pause_btn.isEnabled() is True  # hidden only after a status refresh

    fake.pause_error = "supervisor lease lost"
    result = widget.request_pause()
    assert result["ok"] is False
    assert any("lease lost" in text for _level, text in messages)


def test_emergency_stop_requires_confirmation_and_never_kills(monkeypatch, qapp, fake):
    import nl_coding_agent.gui.main_window as main_window

    widget = _emergency(fake)
    widget.update_status(_active_status())
    messages: list[tuple[str, str]] = []
    widget.message.connect(lambda level, text: messages.append((level, text)))

    monkeypatch.setattr(
        main_window.QMessageBox, "question",
        staticmethod(lambda *a, **k: main_window.QMessageBox.StandardButton.No),
    )
    result = widget.request_stop()
    assert result.get("cancelled") is True
    assert fake.stop_calls == []
    assert any("cancelled" in text.lower() for _level, text in messages)

    monkeypatch.setattr(
        main_window.QMessageBox, "question",
        staticmethod(lambda *a, **k: main_window.QMessageBox.StandardButton.Yes),
    )
    result = widget.request_stop()
    assert result["ok"] is True
    assert len(fake.stop_calls) == 1
    assert fake.stop_calls[0]["project_id"] == 1
    assert "emergency" in fake.stop_calls[0]["reason"].lower()
    assert any("Emergency stop requested" in text for _level, text in messages)

    fake.stop_error = "nothing to stop"
    result = widget.request_stop(confirm=True)
    assert result["ok"] is False
    assert any("nothing to stop" in text for _level, text in messages)


def test_emergency_controls_fail_closed_when_idle(qapp, fake):
    widget = _emergency(fake)
    result = widget.request_pause()
    assert result["ok"] is False
    assert "No active mission" in result["error"]
    result = widget.request_stop(confirm=True)
    assert result["ok"] is False
    assert fake.pause_calls == []
    assert fake.stop_calls == []


def test_emergency_controls_accessibility(qapp, fake):
    widget = _emergency(fake)
    assert "emergency" in widget.accessibleName().lower()
    assert "emergency pause" in widget._pause_btn.accessibleName().lower()
    assert "emergency stop" in widget._stop_btn.accessibleName().lower()
    assert "Ctrl+Alt+P" in widget._pause_btn.toolTip()
    assert "Ctrl+Alt+S" in widget._stop_btn.toolTip()
    assert "never killed" in widget._pause_btn.toolTip().lower()
    assert widget._status_label.accessibleName()


# --------------------------------------------------------------------------- #
# AppServices wrappers (no Qt; throw-away SQLite database)
# --------------------------------------------------------------------------- #

@pytest.fixture()
def app_services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices

    services = AppServices()
    yield services
    try:
        services._db.close()
    except Exception:
        pass


def _new_project(services, tmp_path) -> dict:
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    return services.open_project(root)


def test_appservices_autonomy_defaults_are_off_and_read_only(app_services, tmp_path):
    project = _new_project(app_services, tmp_path)
    settings = app_services.autonomy_settings(project["id"])
    assert settings["ok"] is True
    assert settings["mode"] == "off"
    assert settings["read_only"] is True
    assert settings["starts_automatically"] is False
    assert settings["max_missions_per_run"] == 1

    plan = app_services.autonomy_plan(project["id"])
    assert plan["ok"] is True
    assert plan["read_only"] is True
    assert plan["starts_automatically"] is False
    assert plan["mode"] == "off"
    assert isinstance(plan["queue_counts"], dict)
    assert isinstance(plan["next_requirements"], list)

    assert app_services.autonomy_history(project["id"]) == []


def test_appservices_save_persists_limits_and_never_starts(app_services, tmp_path):
    project = _new_project(app_services, tmp_path)
    started: list = []
    app_services.supervisor_start = lambda *a, **k: started.append(1) or {"ok": True}

    result = app_services.save_autonomy_settings(
        project["id"], mode="assisted", max_missions=3, attempts=4,
        max_wall_time_s=600,
    )
    assert result["ok"] is True
    assert result["started"] is False
    assert started == []

    reloaded = app_services.autonomy_settings(project["id"])
    assert reloaded["mode"] == "assisted"
    assert reloaded["max_missions_per_run"] == 3
    assert reloaded["max_attempts_per_requirement"] == 4
    assert reloaded["max_wall_time_s"] == 600

    # A new AppServices instance (new process equivalent) sees the same policy.
    from nl_coding_agent.app.services import AppServices

    fresh = AppServices()
    try:
        persisted = fresh.autonomy_settings(project["id"])
    finally:
        fresh._db.close()
    assert persisted["mode"] == "assisted"
    assert persisted["max_missions_per_run"] == 3
    assert started == []


def test_appservices_save_rejects_invalid_mode_and_limits(app_services, tmp_path):
    project = _new_project(app_services, tmp_path)
    result = app_services.save_autonomy_settings(project["id"], mode="yolo")
    assert result["ok"] is False
    assert result["started"] is False
    assert "mode" in str(result["error"]).lower()
    assert app_services.autonomy_settings(project["id"])["mode"] == "off"

    result = app_services.save_autonomy_settings(
        project["id"], mode="assisted", max_missions=99)
    assert result["ok"] is False
    assert app_services.autonomy_settings(project["id"])["max_missions_per_run"] == 1


def test_appservices_plan_and_history_do_not_start_a_run(app_services, tmp_path):
    project = _new_project(app_services, tmp_path)
    started: list = []
    app_services.supervisor_start = lambda *a, **k: started.append(1) or {"ok": True}

    app_services.autonomy_plan(project["id"])
    app_services.autonomy_history(project["id"])
    app_services.autonomy_settings(project["id"])
    assert started == []


def test_appservices_history_reads_supervisor_runs_read_only(app_services, tmp_path):
    from nl_coding_agent.persistence import supervisor_store

    project = _new_project(app_services, tmp_path)
    run_id = supervisor_store.start_run(
        project["id"], mode="assisted", config={}, owner_id="test", owner_pid=1234)
    supervisor_store.finish_run(run_id, status="COMPLETED", reason="done")

    history = app_services.autonomy_history(project["id"])
    assert len(history) == 1
    assert history[0]["id"] == run_id
    assert history[0]["mode"] == "assisted"
    assert history[0]["status"] == "COMPLETED"
    # Reading history is read-only: no new run row appears and the run is unchanged.
    assert app_services.autonomy_history(project["id"]) == history
    assert supervisor_store.get_run(run_id)["status"] == "COMPLETED"


def test_appservices_plan_reports_active_run_without_mutating_it(app_services, tmp_path):
    from nl_coding_agent.persistence import supervisor_store

    project = _new_project(app_services, tmp_path)
    run_id = supervisor_store.start_run(
        project["id"], mode="automatic", config={}, owner_id="test", owner_pid=1234)
    plan = app_services.autonomy_plan(project["id"])
    assert plan["read_only"] is True
    assert plan["starts_automatically"] is False
    assert plan["active_run"] is not None
    assert plan["active_run"]["id"] == run_id
    # The read-only preview must not have changed run state or written any command.
    assert supervisor_store.get_run(run_id)["status"] == "STARTING"
    assert supervisor_store.get_active_run(project["id"])["id"] == run_id

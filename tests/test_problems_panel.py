"""F3a problems panel: read-only verification runs + bounded project scan."""
from __future__ import annotations
import os, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _app().processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture()
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices
    rs = AppServices()
    yield rs
    try:
        rs._db.close()
    except Exception:
        pass


def test_verification_problems_and_project_scan(services, tmp_path):
    from nl_coding_agent.persistence import database, missions
    database.init_db().close()
    root = tmp_path / "project"
    root.mkdir()
    (root / "ok.py").write_text("value = 1\n", encoding="utf-8")
    (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    mission_id = missions.create_mission(None, "failed mission", "goal")
    missions.record_verification_run(mission_id, None, "verify:candidate", 1,
                                     "", "failed assertion", False)
    verification = services.verification_problems(None)
    assert any("verify:candidate" in row["message"] for row in verification)
    scan = services.scan_project_problems(root)
    assert any("Syntax error" in row["message"] and "broken.py" in row["message"]
               for row in scan)
    assert any("README" in row["message"] for row in scan)
    combined = services.project_problems(None, root)
    assert combined["counts"]["errors"] >= 1


def test_problems_panel_is_read_only_and_shows_findings(services, tmp_path):
    from nl_coding_agent.gui.widgets.problems_panel import ProblemsPanel
    from nl_coding_agent.persistence import database, missions
    database.init_db().close()
    root = tmp_path / "project"
    root.mkdir()
    (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    mission_id = missions.create_mission(None, "failed", "goal")
    missions.record_verification_run(mission_id, None, "pytest -q", 1, "", "1 failed", False)
    _app()
    panel = ProblemsPanel(services)
    panel.set_project({"id": None, "root": str(root)})
    assert _wait(lambda: panel._table.rowCount() > 0)
    assert panel._table.editTriggers() == panel._table.EditTrigger.NoEditTriggers
    messages = [panel._table.item(row, 2).text() for row in range(panel._table.rowCount())]
    assert any("pytest -q" in message for message in messages)
    assert any("Syntax error" in message for message in messages)
    assert "read-only" in panel._status.text().lower()
    panel.set_project(None)
    assert panel._table.rowCount() == 0

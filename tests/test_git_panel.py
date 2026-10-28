"""F3a read-only Git panel/backend over a temporary repository."""
from __future__ import annotations
import os, subprocess, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def _git(root, *args):
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


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


def _repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Tester")
    (root / "hello.txt").write_text("hello\n", encoding="utf-8")
    _git(root, "add", "hello.txt")
    _git(root, "commit", "-m", "initial commit")
    return root


def test_backend_status_diff_log_are_read_only(services, tmp_path):
    root = _repo(tmp_path)
    status = services.git_status(root)
    assert status["ok"] is True
    assert status["branch"] == "master" or status["branch"] == "main"
    assert status["changes"] == []
    (root / "hello.txt").write_text("changed\n", encoding="utf-8")
    changed = services.git_status(root)
    assert any("hello.txt" in item["path"] for item in changed["changes"])
    diff = services.git_diff(root)
    assert diff["ok"] and "changed" in diff["diff"]
    log = services.git_log(root)
    assert log["ok"] and "initial commit" in log["log"]
    # no destructive git surface is offered by services
    assert not hasattr(services, "git_reset")


def test_git_panel_refresh_shows_branch_changes_diff_log(services, tmp_path):
    from nl_coding_agent.gui.widgets.git_panel import GitPanel
    _app()
    root = _repo(tmp_path)
    (root / "hello.txt").write_text("changed\n", encoding="utf-8")
    panel = GitPanel(services)
    panel.set_project({"id": 1, "root": str(root)})
    assert _wait(lambda: "Branch:" in panel._branch.text())
    assert "hello.txt" in " ".join(panel._changes.item(i).text()
                                   for i in range(panel._changes.count()))
    assert "changed" in panel._diff.toPlainText()
    assert "initial commit" in panel._log.toPlainText()
    assert panel._diff.isReadOnly() and panel._log.isReadOnly()


def test_git_panel_empty_state_without_project(services):
    from nl_coding_agent.gui.widgets.git_panel import GitPanel
    _app()
    panel = GitPanel(services)
    panel.set_project(None)
    assert "No repository loaded" in panel._branch.text()
    assert panel._changes.count() == 0

"""F3a terminal policy: EXECUTE gate, destructive/network refusals, injected runner."""
from __future__ import annotations
import json
import pytest


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


def test_policy_allows_safe_commands_and_denies_destructive_or_network(services, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    allowed = services.terminal_policy(None, ["python", "--version"])
    assert allowed["allowed"] is True
    for argv, code in (
        (["rm", "-rf", "x"], "destructive-denied"),
        (["del", "x"], "destructive-denied"),
        (["cmd", "/c", "dir"], "shell-unsafe"),
        (["powershell", "-Command", "x"], "shell-unsafe"),
        (["echo", "a", "|", "b"], "shell-unsafe"),
        (["curl", "http://example.invalid"], "network-denied"),
        (["git", "push"], "network-denied"),
        (["git", "reset", "--hard"], "destructive-git-denied"),
        (["git", "clone", "x"], "network-denied"),
    ):
        result = services.terminal_policy(None, argv)
        assert result["allowed"] is False, argv
        assert result["error_code"] == code, (argv, result)


def test_execute_permission_denied_is_refused(services, monkeypatch):
    from nl_coding_agent.core import permissions
    monkeypatch.setattr(permissions, "get_policy", lambda pid=None: {
        "read": True, "write": True, "execute": False, "delete": False,
        "network": False, "cloud": False})
    result = services.terminal_policy(None, ["python", "--version"])
    assert result["allowed"] is False
    assert result["error_code"] == "execute-denied"


def test_run_terminal_command_uses_injected_runner_and_audits(services, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    calls = []

    def runner(argv, cwd, timeout):
        calls.append((argv, cwd))
        return {"stdout": "hello\n", "stderr": "", "returncode": 0}

    result = services.run_terminal_command(None, root, "python script.py", runner=runner)
    assert result["ok"] is True and result["stdout"] == "hello\n"
    assert calls and calls[0][0] == ["python", "script.py"]
    assert str(calls[0][1]) == str(root.resolve())

    refused_calls = []
    refused = services.run_terminal_command(
        None, root, ["rm", "-rf", "x"],
        runner=lambda *args: refused_calls.append(args) or {"returncode": 0})
    assert refused["ok"] is False and refused["error_code"] == "destructive-denied"
    assert refused_calls == []
    conn = services._db
    rows = conn.execute("SELECT message, event_kind FROM events WHERE source='terminal'").fetchall()
    assert any("refused" in row["message"].lower() or row["event_kind"] == "terminal-refused"
               for row in rows)


def test_cwd_escape_is_refused(services, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    result = services.run_terminal_command(
        None, root, ["python", "--version"], cwd_rel="..",
        runner=lambda *args: {"returncode": 0})
    assert result["ok"] is False and result["error_code"] == "cwd-escape"

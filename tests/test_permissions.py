"""Tests for the universal permission model and cloud-escalation enforcement.

Covers NL-BP-072 (scopes read/write/execute/delete/network/cloud plus persisted
grants and audit) and NL-BP-076 (local-only default, explicit cloud escalation).

Every test redirects NL_DATA_DIR to a throw-away directory before the permission
module opens a connection, so the live data/nl_coding_agent.sqlite3 is never
read or written by this file.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CLOUD_MODEL = "ollama/gpt-oss:120b-cloud"
LOCAL_MODEL = "ollama/qwen2.5-coder:7b-instruct-q4_K_M"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def perms(data_dir):
    from nl_coding_agent.core import permissions

    return permissions


# --------------------------------------------------------------------------- #
# SQLite helpers (read-only after the permission calls under test)
# --------------------------------------------------------------------------- #

def _db_file(data_dir: Path) -> Path:
    return data_dir / "nl_coding_agent.sqlite3"


def _query(data_dir: Path, sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(str(_db_file(data_dir)))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def _execute(data_dir: Path, sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(str(_db_file(data_dir)))
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _settings(data_dir: Path) -> dict[str, dict]:
    return {
        row["key"]: json.loads(row["value"])
        for row in _query(data_dir, "SELECT key, value FROM app_settings")
    }


def _audit_rows(data_dir: Path) -> list[dict]:
    return _query(
        data_dir,
        "SELECT source, level, message, payload FROM events "
        "WHERE source='permissions' ORDER BY id",
    )


# --------------------------------------------------------------------------- #
# Defaults and validation
# --------------------------------------------------------------------------- #

def test_defaults_are_fail_closed(perms):
    assert perms.SCOPES == ("read", "write", "execute", "delete", "network", "cloud")
    assert perms.get_policy() == {
        "read": True,
        "write": True,
        "execute": True,
        "delete": False,
        "network": False,
        "cloud": False,
    }
    for scope in ("read", "write", "execute"):
        assert perms.is_granted(scope) is True
        perms.require(scope)
    for scope in ("delete", "network", "cloud"):
        assert perms.is_granted(scope) is False
        with pytest.raises(perms.PermissionDenied) as excinfo:
            perms.require(scope)
        assert scope.upper() in str(excinfo.value)
        assert "auto review" in str(excinfo.value).lower()


def test_unknown_scope_is_rejected_by_every_api(perms):
    calls = (
        lambda: perms.grant("teleport"),
        lambda: perms.revoke("teleport"),
        lambda: perms.is_granted("teleport"),
        lambda: perms.require("teleport"),
        lambda: perms.grant(""),
        lambda: perms.is_granted(None),
    )
    for call in calls:
        with pytest.raises(ValueError):
            call()


def test_default_reads_do_not_write_policy_or_audit_rows(perms, data_dir):
    perms.get_policy()
    assert perms.is_granted("cloud") is False
    assert perms.get_policy(project_id=3)["cloud"] is False
    assert _settings(data_dir) == {}
    assert _audit_rows(data_dir) == []


# --------------------------------------------------------------------------- #
# Grant / revoke persistence and audit
# --------------------------------------------------------------------------- #



def test_grant_persists_across_a_fresh_process(perms, data_dir):
    perms.set_access_mode("auto-review", source="pytest")
    code = (
        f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r}); "
        "from nl_coding_agent.core.permissions import is_granted; "
        "print(is_granted('network'))"
    )
    env = dict(os.environ)
    env["NL_DATA_DIR"] = str(data_dir)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_corrupt_or_partial_policy_rows_fail_closed(perms, data_dir):
    perms.get_policy()  # create the schema first
    _execute(
        data_dir,
        "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?,?,?)",
        (perms.GLOBAL_POLICY_KEY, "not-json", "now"),
    )
    corrupt = perms.get_policy()
    assert corrupt["read"] is True
    assert corrupt["delete"] is False
    assert corrupt["network"] is False
    assert corrupt["cloud"] is False

    _execute(
        data_dir,
        "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?,?,?)",
        (
            perms.GLOBAL_POLICY_KEY,
            json.dumps({"cloud": "yes", "delete": True, "teleport": True}),
            "now",
        ),
    )
    partial = perms.get_policy()
    assert partial["delete"] is False
    assert partial["cloud"] is False  # non-boolean value is ignored, never granted
    assert "teleport" not in partial


# --------------------------------------------------------------------------- #
# Project-scoped policy
# --------------------------------------------------------------------------- #



# --------------------------------------------------------------------------- #
# Cloud model / remote endpoint classification and enforcement
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("name", "expected"),
    (
        ("ollama/gpt-oss:120b-cloud", True),
        ("gpt-oss:120b-cloud", True),
        ("cloud", True),
        ("cloud/some-model", True),
        ("CLOUD/Some-Model", True),
        ("ollama/qwen3.5:9b", False),
        ("ollama/qwen2.5-coder:7b-instruct-q4_K_M", False),
        ("cloudless-local-model", False),
        ("", False),
        (None, False),
    ),
)
def test_is_cloud_model_heuristic(perms, name, expected):
    assert perms.is_cloud_model(name) is expected


@pytest.mark.parametrize(
    ("base_url", "expected"),
    (
        ("http://127.0.0.1:11434", False),
        ("http://127.0.0.2:11434", False),
        ("HTTP://127.0.0.1:11434/", False),
        ("http://localhost:11434", False),
        ("http://LOCALHOST:11434", False),
        ("http://[::1]:11434", False),
        ("", False),
        (None, False),
        ("https://api.openai.com/v1", True),
        ("http://192.168.1.50:11434", True),
        ("http://10.0.0.2:8080", True),
    ),
)
def test_is_remote_endpoint(perms, base_url, expected):
    assert perms.is_remote_endpoint(base_url) is expected


def test_cloud_model_denied_by_default_then_allowed_after_explicit_grant(perms):
    assert perms.is_cloud_model(CLOUD_MODEL) is True
    with pytest.raises(perms.PermissionDenied) as excinfo:
        perms.assert_model_permitted(CLOUD_MODEL, "http://127.0.0.1:11434")
    message = str(excinfo.value).lower()
    assert "cloud" in message
    assert "auto review" in message
    assert "global access mode" in message
    assert excinfo.value.scope == "cloud"

    perms.set_access_mode("auto-review", source="settings-ui")
    perms.assert_model_permitted(CLOUD_MODEL, "http://127.0.0.1:11434")


def test_remote_endpoint_denied_then_allowed_after_network_grant(perms):
    remote = "http://192.168.1.50:11434"
    assert perms.is_remote_endpoint(remote) is True
    with pytest.raises(perms.PermissionDenied) as excinfo:
        perms.assert_model_permitted(LOCAL_MODEL, remote)
    assert excinfo.value.scope == "network"
    assert "auto review" in str(excinfo.value).lower()

    perms.set_access_mode("auto-review", source="settings-ui")
    perms.assert_model_permitted(LOCAL_MODEL, remote)


def test_cloud_model_on_remote_endpoint_uses_global_mode(perms):
    with pytest.raises(perms.PermissionDenied):
        perms.assert_model_permitted(CLOUD_MODEL, "https://models.example.com")
    perms.set_access_mode("auto-review")
    perms.assert_model_permitted(CLOUD_MODEL, "https://models.example.com", project_id=6)
    perms.assert_model_permitted(CLOUD_MODEL, "https://models.example.com", project_id=72)


def test_local_loopback_ollama_models_always_pass(perms):
    for base_url in (
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://[::1]:11434",
        "http://127.0.0.1:11434/",
    ):
        assert perms.is_remote_endpoint(base_url) is False
        perms.assert_model_permitted(LOCAL_MODEL, base_url)
        perms.assert_model_permitted(LOCAL_MODEL)


def test_no_environment_variable_or_flag_bypasses_the_gate(perms, monkeypatch):
    for variable in (
        "NL_ALLOW_CLOUD",
        "NL_CLOUD_ESCALATION",
        "NL_PERMISSIONS_BYPASS",
        "CLOUD_ESCALATION_ENABLED",
    ):
        monkeypatch.setenv(variable, "1")
    with pytest.raises(perms.PermissionDenied):
        perms.assert_model_permitted(CLOUD_MODEL, "http://127.0.0.1:11434")

    source = Path(perms.__file__).read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "getenv" not in source


def test_permission_api_is_not_model_facing():
    crew_tools = REPO_ROOT / "nl_coding_agent" / "tools" / "crew_tools.py"
    source = crew_tools.read_text(encoding="utf-8")
    assert "permissions.grant" not in source and "permissions.set_access_mode" not in source


# --------------------------------------------------------------------------- #
# Wiring: orchestrator._make_llm and cli.make_llm
# --------------------------------------------------------------------------- #

def test_orchestrator_make_llm_denies_cloud_model_without_grant(perms):
    from nl_coding_agent.agents.orchestrator import _make_llm

    with pytest.raises(perms.PermissionDenied) as excinfo:
        _make_llm(CLOUD_MODEL, "http://127.0.0.1:11434")
    assert excinfo.value.scope == "cloud"


def test_orchestrator_make_llm_local_model_passes_and_keeps_signature(perms, monkeypatch):
    import nl_coding_agent.agents.orchestrator as orchestrator_module

    recorded: dict = {}

    class FakeLLM:
        def __init__(self, **kwargs):
            recorded.update(kwargs)

    monkeypatch.setattr(orchestrator_module, "LLM", FakeLLM)
    llm = orchestrator_module._make_llm(
        LOCAL_MODEL, "http://127.0.0.1:11434", temperature=0.25
    )
    assert isinstance(llm, FakeLLM)
    assert recorded == {
        "model": LOCAL_MODEL,
        "base_url": "http://127.0.0.1:11434",
        "temperature": 0.25,
    }


def test_orchestrator_make_llm_opens_only_after_explicit_cloud_grant(perms, monkeypatch):
    import nl_coding_agent.agents.orchestrator as orchestrator_module

    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(orchestrator_module, "LLM", FakeLLM)
    with pytest.raises(perms.PermissionDenied):
        orchestrator_module._make_llm(CLOUD_MODEL, "http://127.0.0.1:11434")

    perms.set_access_mode("auto-review", source="settings-ui")
    llm = orchestrator_module._make_llm(CLOUD_MODEL, "http://127.0.0.1:11434")
    assert isinstance(llm, FakeLLM)
    assert llm.kwargs["model"] == CLOUD_MODEL


def test_cli_make_llm_enforces_the_same_gate(perms, monkeypatch):
    from nl_coding_agent import cli

    monkeypatch.setattr(cli, "LLM", lambda **kwargs: kwargs)

    with pytest.raises(perms.PermissionDenied):
        cli.make_llm({"model": CLOUD_MODEL}, "http://127.0.0.1:11434")
    with pytest.raises(perms.PermissionDenied):
        cli.make_llm({"model": LOCAL_MODEL}, "https://api.example.invalid/v1")

    perms.set_access_mode("auto-review")
    perms.set_access_mode("auto-review")
    built = cli.make_llm(
        {"model": CLOUD_MODEL, "temperature": 0.0}, "https://api.example.invalid/v1"
    )
    assert built["model"] == CLOUD_MODEL
    assert built["temperature"] == 0.0

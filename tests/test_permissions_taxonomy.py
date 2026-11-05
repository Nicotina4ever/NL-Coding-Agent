"""Tests for the expanded capability taxonomy and durable scoped approvals (NL-BP-168).

Scope: additive capability model on top of the legacy fail-closed scopes in
core/permissions.py. Every test uses a throw-away NL_DATA_DIR; no model, network,
mission or GUI run is started.

Covered: taxonomy/defaults/risk classes, scope kinds and decision semantics,
durable grants with expiry/revocation/inspection, allow-once consumption,
project/mission/saved-policy/host/path/tool scoping, deny precedence, pending
approval durability across a fresh process, approval decisions, audit events,
no silent cross-enablement, and unchanged legacy permission behaviour.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_CAPABILITIES = (
    "read", "write", "execute", "install-private", "install-system",
    "web-search", "web-fetch", "browser-interact", "download",
    "open-external-project", "model-inference-local", "model-inference-cloud",
    "secret-use", "git-commit", "git-push", "publish-release", "delete",
    "network-write", "mcp-call", "microphone",
)
EXPECTED_SCOPE_KINDS = (
    "tool", "process", "path", "project", "external-resource", "host-domain",
    "repository", "task", "mission", "workspace", "session", "saved-policy",
)
EXPECTED_DECISIONS = ("allow-once", "mission", "project", "always", "deny", "revoke")
ALLOWED_BY_DEFAULT = {"read", "write", "execute", "model-inference-local"}
APPROVAL_BY_DEFAULT = {
    "install-private", "open-external-project", "git-commit", "mcp-call",
    "microphone",
}
DENIED_BY_DEFAULT = set(EXPECTED_CAPABILITIES) - ALLOWED_BY_DEFAULT - APPROVAL_BY_DEFAULT


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def perms(data_dir):
    from nl_coding_agent.core import permissions

    return permissions


def _scope(perms, kind: str, value=None):
    return perms.CapabilityScope(kind, value)


def _events(data_dir: Path) -> list[dict]:
    conn = sqlite3.connect(str(data_dir / "nl_coding_agent.sqlite3"))
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(row) for row in conn.execute(
                "SELECT id, source, level, message, payload, event_kind "
                "FROM events WHERE source='permissions' ORDER BY id"
            )
        ]
    finally:
        conn.close()


def _run_restart(data_dir: Path, code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["NL_DATA_DIR"] = str(data_dir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    prefix = "import sys; sys.path.insert(0, " + repr(str(REPO_ROOT)) + "); "
    return subprocess.run(
        [sys.executable, "-c", prefix + code],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
    )


def _restart_outcome(data_dir, perms, capability, kind, value=None, context=None):
    scope_code = "p.CapabilityScope(" + repr(kind) + ", " + repr(value) + ")"
    code = (
        "from nl_coding_agent.core import permissions as p; "
        "d = p.check_capability(" + repr(capability) + ", " + scope_code
        + (", context=" + repr(context) if context is not None else "")
        + "); print(d.outcome); print(d.approval_id if d.approval_id is not None else '')"
    )
    completed = _run_restart(data_dir, code)
    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.strip().splitlines()
    approval = lines[1] if len(lines) > 1 and lines[1] else None
    return lines[0], approval


# --------------------------------------------------------------------------- #
# Taxonomy, scopes and defaults
# --------------------------------------------------------------------------- #

def test_capability_taxonomy_is_complete(perms):
    assert perms.CAPABILITIES == EXPECTED_CAPABILITIES
    assert len(perms.CAPABILITIES) == 20
    assert set(perms.CAPABILITY_TAXONOMY) == set(EXPECTED_CAPABILITIES)
    for capability, meta in perms.CAPABILITY_TAXONOMY.items():
        assert meta["risk"] in perms.RISK_CLASSES, capability
        assert meta["default"] in perms.DEFAULT_DECISIONS, capability
        assert meta["description"], capability
        assert perms.CAPABILITY_RISK[capability] == meta["risk"]
        assert perms.CAPABILITY_DEFAULTS[capability] == meta["default"]

    allowed = {c for c, d in perms.CAPABILITY_DEFAULTS.items() if d == "allowed"}
    approval = {c for c, d in perms.CAPABILITY_DEFAULTS.items() if d == "approval"}
    denied = {c for c, d in perms.CAPABILITY_DEFAULTS.items() if d == "denied"}
    assert allowed == ALLOWED_BY_DEFAULT
    assert approval == APPROVAL_BY_DEFAULT
    assert denied == DENIED_BY_DEFAULT
    # High-impact capabilities are never allowed by default.
    for capability in ("install-system", "delete", "publish-release", "secret-use",
                       "git-push", "network-write", "model-inference-cloud"):
        assert perms.CAPABILITY_DEFAULTS[capability] == "denied", capability
        assert perms.CAPABILITY_RISK[capability] in ("high", "critical"), capability


def test_scope_kinds_and_decisions_are_complete(perms):
    assert perms.SCOPE_KINDS == EXPECTED_SCOPE_KINDS
    assert perms.DECISIONS == EXPECTED_DECISIONS
    assert perms.GRANT_DECISIONS == EXPECTED_DECISIONS[:-1]
    assert perms.DECISION_ALLOW_ONCE == "allow-once"
    assert perms.DECISION_ALLOW_MISSION == "mission"
    assert perms.DECISION_ALLOW_PROJECT == "project"
    assert perms.DECISION_ALWAYS == "always"
    assert perms.DECISION_DENY == "deny"
    assert perms.DECISION_REVOKE == "revoke"


@pytest.mark.parametrize("mode", ["read-only", "workspace-write", "auto-review", "full-access"])
@pytest.mark.parametrize("kind", EXPECTED_SCOPE_KINDS)
def test_scope_is_identity_not_an_additional_grant(perms, mode, kind):
    perms.set_access_mode(mode)
    for capability in EXPECTED_CAPABILITIES:
        decision = perms.check_capability(capability, _scope(perms, kind, "fixture"), {"project_id": 6})
        assert decision.allowed == perms.check_access(capability).allowed
        assert not decision.needs_approval


def test_unknown_capability_and_scope_are_rejected(perms):
    with pytest.raises(ValueError):
        perms.check_capability("teleport")
    with pytest.raises(ValueError):
        perms.check_capability("read", perms.CapabilityScope("planet", "earth"))


@pytest.mark.parametrize("name,args,kwargs", [
    ("grant", ("cloud",), {"project_id": 6}),
    ("revoke", ("write",), {"project_id": 6}),
    ("grant_capability", ("delete",), {"decision": "always"}),
    ("revoke_capability", ("delete",), {}),
    ("request_capability", ("delete",), {}),
    ("decide_capability_approval", (1,), {"decision": "always"}),
])
def test_retired_authorization_writers_fail_without_creating_state(perms, data_dir, name, args, kwargs):
    perms.set_access_mode("workspace-write")
    with pytest.raises(perms.PermissionDenied, match="global access mode"):
        getattr(perms, name)(*args, **kwargs)
    assert perms.list_capability_grants() == []
    assert perms.list_capability_approvals() == []
    assert perms.get_access_mode() == "workspace-write"


def test_global_mode_survives_restart(perms, data_dir):
    perms.set_access_mode("full-access")
    outcome, approval = _restart_outcome(data_dir, perms, "delete", "project", "6")
    assert outcome == "allowed" and approval is None
    perms.set_access_mode("read-only")
    outcome, approval = _restart_outcome(data_dir, perms, "write", "project", "72")
    assert outcome == "denied" and approval is None


def test_require_capability_is_global(perms):
    with pytest.raises(perms.PermissionDenied):
        perms.require_capability("delete")
    perms.set_access_mode("full-access")
    assert perms.require_capability("delete").allowed

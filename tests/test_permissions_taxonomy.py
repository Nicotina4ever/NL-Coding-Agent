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


def test_defaults_are_fail_closed(perms):
    for capability in ALLOWED_BY_DEFAULT:
        decision = perms.check_capability(capability)
        assert isinstance(decision, perms.Allowed), capability
        assert decision.allowed is True
        assert decision.outcome == "allowed"
        assert decision.reason
    for capability in DENIED_BY_DEFAULT:
        decision = perms.check_capability(capability)
        assert isinstance(decision, perms.Denied), capability
        assert decision.allowed is False
        assert decision.needs_approval is False
        assert decision.reason
    for capability in APPROVAL_BY_DEFAULT:
        decision = perms.check_capability(capability)
        assert isinstance(decision, perms.NeedsApproval), capability
        assert decision.needs_approval is True
        assert decision.reason


def test_unknown_capability_scope_and_decision_are_rejected(perms):
    with pytest.raises(ValueError):
        perms.check_capability("teleport")
    with pytest.raises(ValueError):
        perms.normalize_capability("")
    with pytest.raises(ValueError):
        perms.check_capability("read", perms.CapabilityScope("planet", "earth"))
    with pytest.raises(ValueError):
        perms.grant_capability("read", decision="sometimes")
    with pytest.raises(ValueError):
        perms.grant_capability("read", scope=object())
    with pytest.raises(ValueError):
        perms.normalize_decision("allow")
    assert perms.check_capability("read", {"kind": "project", "value": "1"}).allowed


# --------------------------------------------------------------------------- #
# Scopes, consumption and matching
# --------------------------------------------------------------------------- #

def test_tool_scope_and_allow_once_consumption(perms, data_dir):
    perms.grant_capability(
        "download", _scope(perms, "tool", "curl"), decision="allow-once")

    first = perms.check_capability("download", _scope(perms, "tool", "curl"))
    assert isinstance(first, perms.Allowed)
    assert first.policy_id is not None
    assert isinstance(
        perms.check_capability("download", _scope(perms, "tool", "wget")),
        perms.Denied,
    )
    second = perms.check_capability("download", _scope(perms, "tool", "curl"))
    assert isinstance(second, perms.Denied)
    grants = perms.list_capability_grants("download")
    assert grants and grants[0]["consumed_at"]
    kinds = {row["event_kind"] for row in _events(data_dir)}
    assert "capability_consume" in kinds


def test_path_scope_prefix_matching(perms):
    perms.grant_capability(
        "delete", _scope(perms, "path", "/tmp/proj"), decision="always")
    assert isinstance(
        perms.check_capability("delete", _scope(perms, "path", "/tmp/proj/a/b.py")),
        perms.Allowed,
    )
    assert isinstance(
        perms.check_capability("delete", _scope(perms, "path", "/tmp/proj-other/x")),
        perms.Denied,
    )


def test_host_domain_scope_and_no_cross_enable(perms):
    perms.grant_capability(
        "web-fetch", _scope(perms, "host-domain", "example.com"),
        decision="always",
    )
    assert isinstance(
        perms.check_capability("web-fetch", _scope(perms, "host-domain", "api.example.com")),
        perms.Allowed,
    )
    assert isinstance(
        perms.check_capability("web-fetch", _scope(perms, "host-domain", "example.com.evil.com")),
        perms.Denied,
    )
    # Enabling web-fetch never enables other outbound capabilities.
    assert isinstance(perms.check_capability("web-search"), perms.Denied)
    assert isinstance(perms.check_capability("browser-interact"), perms.Denied)
    assert isinstance(perms.check_capability("network-write"), perms.Denied)


def test_project_and_mission_scope_isolation(perms):
    perms.grant_capability(
        "web-search", _scope(perms, "project", "1"),
        decision="project", project_id=1,
    )
    assert isinstance(
        perms.check_capability("web-search", context={"project_id": 1}),
        perms.Allowed,
    )
    assert isinstance(
        perms.check_capability("web-search", context={"project_id": 2}),
        perms.Denied,
    )

    perms.grant_capability(
        "mcp-call", _scope(perms, "mission", "7"), decision="mission",
    )
    assert isinstance(
        perms.check_capability("mcp-call", context={"mission_id": 7}),
        perms.Allowed,
    )
    assert not isinstance(
        perms.check_capability("mcp-call", context={"mission_id": 8}),
        perms.Allowed,
    )


def test_project_and_mission_decisions_without_explicit_scope(perms):
    perms.grant_capability("web-search", decision="project", project_id=1)
    assert isinstance(perms.check_capability("web-search", context={"project_id": 1}),
                      perms.Allowed)
    assert isinstance(perms.check_capability("web-search", context={"project_id": 2}),
                      perms.Denied)

    perms.grant_capability("mcp-call", decision="mission", context={"mission_id": 9})
    assert isinstance(perms.check_capability("mcp-call", context={"mission_id": 9}),
                      perms.Allowed)
    other = perms.check_capability("mcp-call", context={"mission_id": 10})
    assert not isinstance(other, perms.Allowed)


def test_saved_policy_scope(perms):
    perms.grant_capability(
        "browser-interact", _scope(perms, "saved-policy", "research-policy"),
        decision="always",
    )
    assert isinstance(
        perms.check_capability("browser-interact", context={"saved_policy": "research-policy"}),
        perms.Allowed,
    )
    assert isinstance(
        perms.check_capability("browser-interact", context={"saved_policy": "other"}),
        perms.Denied,
    )


def test_all_scope_kinds_can_be_granted_and_checked(perms):
    samples = {
        "tool": ("pytest", {"tool": "pytest"}),
        "process": ("4242", {"process_id": 4242}),
        "path": ("/tmp/scope-all", {"path": "/tmp/scope-all/file.py"}),
        "project": ("1", {"project_id": 1}),
        "external-resource": ("https://example.com/x", {"external_resource": "https://example.com/x"}),
        "host-domain": ("example.org", {"host": "api.example.org"}),
        "repository": ("K:/repo", {"repository": "K:/repo"}),
        "task": ("12", {"task_id": 12}),
        "mission": ("34", {"mission_id": 34}),
        "workspace": ("/tmp/ws", {"workspace": "/tmp/ws"}),
        "session": ("s-1", {"session_id": "s-1"}),
        "saved-policy": ("policy-a", {"saved_policy": "policy-a"}),
    }
    assert set(samples) == set(EXPECTED_SCOPE_KINDS)
    for kind, (value, context) in samples.items():
        result = perms.grant_capability("delete", _scope(perms, kind, value),
                                        decision="allow-once")
        assert result["ok"] is True, kind
        granted = perms.get_capability_grant(result["grant_id"])
        assert granted["scope_kind"] == kind
        decision = perms.check_capability("delete", context=context)
        assert isinstance(decision, perms.Allowed), (kind, decision)


# --------------------------------------------------------------------------- #
# Expiry, revocation, deny precedence, inspection
# --------------------------------------------------------------------------- #

def test_expiry_and_inspection(perms):
    future = (datetime.now() + timedelta(minutes=5)).isoformat(timespec="seconds")
    past = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    live = perms.grant_capability("delete", _scope(perms, "path", "/tmp/live"),
                                  decision="always", expires_at=future)
    expired = perms.grant_capability("delete", _scope(perms, "path", "/tmp/expired"),
                                     decision="always", expires_at=past)
    assert isinstance(
        perms.check_capability("delete", _scope(perms, "path", "/tmp/live/x")),
        perms.Allowed,
    )
    assert isinstance(
        perms.check_capability("delete", _scope(perms, "path", "/tmp/expired/x")),
        perms.Denied,
    )
    listed = {row["id"]: row for row in perms.list_capability_grants("delete")}
    assert listed[live["grant_id"]]["expires_at"] == future
    assert listed[expired["grant_id"]]["expires_at"] == past


def test_revocation_is_durable_and_audited(perms, data_dir):
    granted = perms.grant_capability(
        "web-fetch", _scope(perms, "host-domain", "docs.example.com"),
        decision="always",
    )
    assert isinstance(
        perms.check_capability("web-fetch", _scope(perms, "host-domain", "docs.example.com")),
        perms.Allowed,
    )
    revoked = perms.revoke_capability("web-fetch")
    assert revoked["ok"] is True
    assert revoked["revoked"] >= 1
    assert isinstance(
        perms.check_capability("web-fetch", _scope(perms, "host-domain", "docs.example.com")),
        perms.Denied,
    )
    row = perms.get_capability_grant(granted["grant_id"])
    assert row and row["revoked_at"]
    kinds = {entry["event_kind"] for entry in _events(data_dir)}
    assert {"capability_grant", "capability_revoke"} <= kinds

    # A new explicit grant works again; the previous one stays revoked.
    perms.grant_capability(
        "web-fetch", _scope(perms, "host-domain", "docs.example.com"),
        decision="always",
    )
    assert isinstance(
        perms.check_capability("web-fetch", _scope(perms, "host-domain", "docs.example.com")),
        perms.Allowed,
    )


def test_deny_precedence_over_allow(perms):
    scope = _scope(perms, "path", "/tmp/deny")
    allow = perms.grant_capability("delete", scope, decision="always")
    deny = perms.grant_capability("delete", scope, decision="deny")
    decision = perms.check_capability("delete", _scope(perms, "path", "/tmp/deny/file"))
    assert isinstance(decision, perms.Denied)
    assert decision.policy_id == deny["grant_id"]
    assert decision.policy_id != allow["grant_id"]

    # An allow-once grant cannot override an explicit deny either.
    perms.grant_capability("delete", scope, decision="allow-once")
    assert isinstance(
        perms.check_capability("delete", _scope(perms, "path", "/tmp/deny/file")),
        perms.Denied,
    )


# --------------------------------------------------------------------------- #
# Durability and restart survival
# --------------------------------------------------------------------------- #

def test_grant_survives_restart_and_allow_once_is_consumed_once(perms, data_dir):
    perms.grant_capability(
        "delete", _scope(perms, "path", "/tmp/restart"), decision="allow-once")
    outcome, _ = _restart_outcome(data_dir, perms, "delete", "path", "/tmp/restart/a.txt")
    assert outcome == "allowed"
    outcome, _ = _restart_outcome(data_dir, perms, "delete", "path", "/tmp/restart/a.txt")
    assert outcome == "denied"


def test_pending_approval_survives_restart_and_decision_applies(perms, data_dir):
    request = perms.request_capability(
        "delete", _scope(perms, "path", "/tmp/approval"), reason="cleanup proposal")
    assert request["ok"] is True
    pending = perms.check_capability(
        "delete", _scope(perms, "path", "/tmp/approval"))
    assert isinstance(pending, perms.NeedsApproval)
    assert pending.approval_id == request["approval_id"]

    outcome, approval_id = _restart_outcome(
        data_dir, perms, "delete", "path", "/tmp/approval")
    assert outcome == "needs_approval"
    assert approval_id == str(request["approval_id"])

    decided = perms.decide_capability_approval(
        request["approval_id"], True, decision="allow-once", decided_by="test")
    assert decided["ok"] is True
    assert decided["status"] == "approved"
    assert decided["grant_id"]

    outcome, _ = _restart_outcome(data_dir, perms, "delete", "path", "/tmp/approval/a")
    assert outcome == "allowed"
    approval = perms.get_capability_approval(request["approval_id"])
    assert approval["status"] == "approved"
    assert approval["decided_by"] == "test"


def test_denied_approval_fails_closed_without_a_grant(perms, data_dir):
    request = perms.request_capability(
        "git-push", _scope(perms, "repository", "owner/repo"))
    decided = perms.decide_capability_approval(
        request["approval_id"], False, decided_by="test")
    assert decided["ok"] is True
    assert decided["status"] == "denied"
    assert decided["grant_id"] is None

    decision = perms.check_capability(
        "git-push", _scope(perms, "repository", "owner/repo"))
    assert isinstance(decision, perms.Denied)
    assert str(request["approval_id"]) in decision.reason
    assert perms.list_capability_grants("git-push") == []
    outcome, _ = _restart_outcome(
        data_dir, perms, "git-push", "repository", "owner/repo")
    assert outcome == "denied"


def test_expired_pending_approval_falls_back_to_default(perms):
    past = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    request = perms.request_capability(
        "microphone", _scope(perms, "tool", "record"),
        expires_at=past,
    )
    decision = perms.check_capability(
        "microphone", _scope(perms, "tool", "record"))
    assert isinstance(decision, perms.NeedsApproval)
    assert decision.approval_id is None  # overdue pending request no longer applies
    assert perms.expire_capability_approvals() >= 1
    approval = perms.get_capability_approval(request["approval_id"])
    assert approval["status"] == "expired"


# --------------------------------------------------------------------------- #
# Audit and fail-closed writing behaviour
# --------------------------------------------------------------------------- #

def test_audit_events_and_no_secret_or_context_leak(perms, data_dir):
    granted = perms.grant_capability(
        "web-fetch", _scope(perms, "host-domain", "audit.example.com"),
        decision="always", context={"saved_policy": "do-not-log-me"},
    )
    perms.revoke_capability("web-fetch")
    request = perms.request_capability(
        "git-commit", _scope(perms, "repository", "owner/repo"), reason="commit")
    perms.decide_capability_approval(request["approval_id"], True,
                                     decision="allow-once")
    assert isinstance(
        perms.check_capability("git-commit", _scope(perms, "repository", "owner/repo")),
        perms.Allowed,
    )
    events = _events(data_dir)
    kinds = {entry["event_kind"] for entry in events}
    assert {"capability_grant", "capability_revoke", "capability_request",
            "capability_decision", "capability_consume"} <= kinds
    for entry in events:
        assert entry["source"] == "permissions"
        payload = json.loads(entry["payload"] or "{}")
        assert "do-not-log-me" not in json.dumps(payload)
        assert "secret" not in json.dumps(payload).lower()
    assert granted["grant_id"]


def test_default_checks_do_not_write_state(perms, data_dir):
    perms.list_capability_grants()  # initialize the additive schema/DB first
    before_events = len(_events(data_dir))
    assert isinstance(perms.check_capability("read"), perms.Allowed)
    assert isinstance(perms.check_capability("web-fetch"), perms.Denied)
    assert len(_events(data_dir)) == before_events
    assert perms.list_capability_grants() == []


# --------------------------------------------------------------------------- #
# No cross-enable + legacy compatibility
# --------------------------------------------------------------------------- #

def test_no_silent_cross_enable_between_capabilities(perms):
    perms.grant_capability(
        "web-fetch", _scope(perms, "host-domain", "one.example.com"),
        decision="always",
    )
    perms.grant_capability(
        "install-private", _scope(perms, "tool", "pip"), decision="always")
    state = {capability: perms.check_capability(capability).outcome
             for capability in EXPECTED_CAPABILITIES}
    # A scoped grant only allows its own scope/capability; the unscoped default
    # remains fail-closed for every other capability.
    assert state["web-fetch"] == "denied"
    assert state["install-private"] == "needs_approval"
    assert isinstance(
        perms.check_capability("web-fetch",
                               _scope(perms, "host-domain", "one.example.com")),
        perms.Allowed,
    )
    assert isinstance(
        perms.check_capability("install-private", _scope(perms, "tool", "pip")),
        perms.Allowed,
    )
    for capability in ("web-search", "browser-interact", "download",
                       "network-write", "install-system", "secret-use",
                       "model-inference-cloud", "publish-release", "git-push",
                       "delete"):
        assert state[capability] == "denied", capability
    for capability in ("git-commit", "mcp-call", "microphone",
                       "open-external-project"):
        assert state[capability] == "needs_approval", capability


def test_legacy_permission_behaviour_is_unchanged(perms, data_dir):
    # Legacy scope policy defaults are untouched.
    assert perms.is_granted("read") is True
    assert perms.is_granted("write") is True
    assert perms.is_granted("execute") is True
    for scope in ("delete", "network", "cloud"):
        assert perms.is_granted(scope) is False
        with pytest.raises(perms.PermissionDenied):
            perms.require(scope)

    # Cloud/remote model gates are untouched.
    with pytest.raises(perms.PermissionDenied):
        perms.assert_model_permitted("ollama/gpt-oss:120b-cloud",
                                     "http://127.0.0.1:11434")
    perms.grant("cloud")
    perms.grant("network")
    perms.assert_model_permitted("ollama/gpt-oss:120b-cloud",
                                 "http://127.0.0.1:11434")

    # Legacy grants never silently enable the new capability taxonomy.
    assert isinstance(perms.check_capability("web-fetch"), perms.Denied)
    assert isinstance(perms.check_capability("model-inference-cloud"), perms.Denied)
    assert isinstance(perms.check_capability("network-write"), perms.Denied)
    # ... and capability grants never mutate the legacy policy.
    before = perms.get_policy()
    perms.grant_capability("read", _scope(perms, "tool", "reader"),
                           decision="always")
    assert perms.get_policy() == before
    assert perms.is_granted("cloud") is True


def test_require_capability_raises_unless_allowed(perms):
    with pytest.raises(perms.PermissionDenied):
        perms.require_capability("delete")
    allowed = perms.require_capability("read")
    assert isinstance(allowed, perms.Allowed)
    perms.grant_capability(
        "delete", _scope(perms, "path", "/tmp/required"), decision="always")
    result = perms.require_capability(
        "delete", _scope(perms, "path", "/tmp/required/file"))
    assert isinstance(result, perms.Allowed)

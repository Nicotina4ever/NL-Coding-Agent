"""Global-mode authorization, action integrity, independent review and audit.

Legacy profile/controls metadata is accepted for API compatibility and never
creates a second approval boundary. All tests use isolated data.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from nl_coding_agent.core import auto_review
from nl_coding_agent.core import permissions

HIGH_IMPACT = (
    "delete", "publish-release", "secret-use", "install-system", "git-push",
    "network-write",
)

@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path))
    return tmp_path

def _action(capability: str, **kwargs):
    return auto_review.ActionDescriptor(capability=capability, **kwargs)

def _events(data_dir) -> list[dict]:
    conn = sqlite3.connect(str(data_dir / "nl_coding_agent.sqlite3"))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(
            "SELECT id, source, level, message, payload, event_kind FROM events "
            "WHERE source='permissions' AND event_kind='capability_auto_review' "
            "ORDER BY id"
        )]
    finally:
        conn.close()

# --------------------------------------------------------------------------- #
# Profiles, controls and truthful disclosures
# --------------------------------------------------------------------------- #

def test_profile_catalog_is_complete_and_truthful():
    assert auto_review.PROFILES == (
        "manual", "assisted", "trusted-auto-review", "full-autonomy")
    assert auto_review.DEFAULT_PROFILE == "manual"
    assert auto_review.CONTROLS == (
        "tool_auto_authorization", "automated_review", "background_continuation",
        "external_network", "cloud_llm", "user_file_access", "release_deployment",
    )
    descriptors = auto_review.list_profiles()
    assert len(descriptors) == 4
    for descriptor in descriptors:
        assert set(descriptor["controls"]) == set(auto_review.CONTROLS)
        assert descriptor["label"]
        assert descriptor["description"]
        assert "not an OS sandbox" in descriptor["os_rights_disclosure"]
        assert "user" in descriptor["os_rights_disclosure"].lower()
        assert descriptor["limits"]
    full = auto_review.profile_descriptor("full-autonomy")
    assert all(full["controls"].values())
    limits = " ".join(full["limits"]).lower()
    assert "os sandbox" in limits
    assert "high-impact" in limits
    assert "independent review" in limits
    trusted = auto_review.profile_descriptor("trusted-auto-review")
    assert trusted["controls"]["external_network"] is True
    assert trusted["controls"]["cloud_llm"] is False
    assert trusted["controls"]["release_deployment"] is False
    manual = auto_review.profile_descriptor("manual")
    assert not any(manual["controls"].values())
    # Descriptors are copies: mutating one never changes profile state.
    manual["controls"]["tool_auto_authorization"] = True
    assert auto_review.profile_descriptor("manual")["controls"][
        "tool_auto_authorization"] is False

def test_unknown_profile_or_control_is_rejected():
    with pytest.raises(ValueError):
        auto_review.normalize_profile("yolo")
    with pytest.raises(ValueError):
        auto_review.profile_descriptor("")
    with pytest.raises(ValueError):
        auto_review.controls_for_profile("manual", {"turbo": True})
    with pytest.raises(ValueError):
        auto_review.evaluate_action(_action("teleport"))
    with pytest.raises(ValueError):
        auto_review.evaluate_action(_action("read", scope_kind="planet"))

# --------------------------------------------------------------------------- #
# Manual / Assisted
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Trusted Auto Review
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Full Autonomy
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Grants, denials, expiry, approvals and allow-once
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Controls stay separate (no silent cross-enable)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Inconsistent descriptors, independent review, audit, determinism, legacy
# --------------------------------------------------------------------------- #

def test_inconsistent_action_descriptors_are_denied(data_dir):
    for action in (
        _action("read", publish=True),
        _action("read", delete=True),
        _action("write", secret_access=True),
        _action("write", install=True),
    ):
        decision = auto_review.evaluate_action(action, profile="full-autonomy")
        assert decision.outcome == "denied"
        assert decision.reason_code == "inconsistent_action_descriptor"

def test_independent_review_required_for_code_and_staged_promotions(data_dir):
    cases = [
        (_action("read"), False),
        (_action("execute", tests=True), False),
        (_action("write"), True),
        (_action("write", staged_code_edit=True), True),
        (_action("git-commit", scope_kind="repository",
                 scope_value="owner/repo"), True),
        (_action("execute", staged_code_edit=True), True),
    ]
    for action, expected in cases:
        decision = auto_review.evaluate_action(action, profile="full-autonomy")
        assert decision.independent_review_required is expected, action

def test_every_decision_is_audited_without_leaking_secrets(data_dir):
    action = _action(
        "write", staged_code_edit=True,
        tool="curl", command="curl -H 'Authorization: SECRET-COMMAND'",
        target_paths=("/secret/path/file.py",),
        host="secret.example", description="SECRET-DESCRIPTION",
        scope_kind="path", scope_value="/secret/scope",
        context={"secret": "SECRET-CONTEXT"},
    )
    decisions = [
        auto_review.evaluate_action(_action("read"), profile="manual"),
        auto_review.evaluate_action(_action("delete"), profile="full-autonomy"),
        auto_review.evaluate_action(action, profile="full-autonomy"),
    ]
    rows = _events(data_dir)
    assert len(rows) == len(decisions)
    blob = json.dumps(rows)
    assert "SECRET" not in blob
    assert "/secret/path" not in blob
    assert "secret.example" not in blob
    for row, decision in zip(rows, decisions):
        payload = json.loads(row["payload"])
        assert row["source"] == "permissions"
        assert row["event_kind"] == "capability_auto_review"
        assert payload["outcome"] == decision.outcome
        assert payload["capability"] == decision.capability
        assert payload["profile"] == decision.profile
        assert payload["risk"] == decision.risk
        assert "scope_value" not in payload
        assert "command" not in payload
        assert "target_paths" not in payload

def test_audit_failure_fails_closed(monkeypatch, data_dir):
    monkeypatch.setattr(auto_review, "_emit_audit", lambda decision: None)
    decision = auto_review.evaluate_action(_action("read"), profile="full-autonomy")
    assert decision.outcome == "denied"
    assert decision.reason_code == "audit_unavailable"

@pytest.mark.parametrize("mode,capability,allowed", [
    ("read-only", "read", True), ("read-only", "write", False),
    ("workspace-write", "write", True), ("workspace-write", "delete", False),
    ("auto-review", "web-fetch", True), ("auto-review", "model-inference-cloud", True),
    ("auto-review", "delete", False), ("full-access", "delete", True),
    ("full-access", "git-push", True), ("full-access", "publish-release", True),
])
def test_legacy_profiles_controls_do_not_override_mode(data_dir, mode, capability, allowed):
    permissions.set_access_mode(mode)
    for profile in auto_review.PROFILES:
        decision = auto_review.evaluate_action(_action(capability), profile,
            controls={name: False for name in auto_review.CONTROLS})
        assert decision.auto_approved == allowed
        assert not decision.needs_human_approval

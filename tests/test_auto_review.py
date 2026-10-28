"""Tests for the independent auto-review policy engine and autonomy profiles.

NL-BP-166/167 first increment. All tests use a throw-away NL_DATA_DIR; no model,
network, mission or GUI run is started. Permission grants/approvals go through the
existing NL-BP-168 durable capability API.
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


def _grant(capability, kind, value, *, decision="always", project_id=None, **kwargs):
    return permissions.grant_capability(
        capability,
        permissions.CapabilityScope(kind, value),
        decision=decision,
        project_id=project_id,
        **kwargs,
    )


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


def test_profile_aliases_and_dict_action_input(data_dir):
    decision = auto_review.evaluate_action(
        {"capability": "read", "staged_code_edit": True}, profile="trusted")
    assert decision.profile == "trusted-auto-review"
    assert decision.independent_review_required is True
    assert decision.grant_id is None and decision.policy_id is None
    assert decision.risk_class == "low"
    assert auto_review.evaluate(_action("read"), profile="off").profile == "manual"
    with pytest.raises(ValueError):
        auto_review.evaluate_action(
            {"capability": "read", "bogus_field": 1}, profile="manual")


# --------------------------------------------------------------------------- #
# Manual / Assisted
# --------------------------------------------------------------------------- #

def test_manual_requires_human_for_routine_work(data_dir):
    decision = auto_review.evaluate_action(_action("read"), profile="manual")
    assert decision.outcome == "needs_human_approval"
    assert decision.needs_human_approval is True
    assert decision.reason_code == "profile_requires_human_approval"
    assert decision.independent_review_required is False

    write = auto_review.evaluate_action(
        _action("write", staged_code_edit=True, target_paths=("src/app.py",)),
        profile="manual")
    assert write.outcome == "needs_human_approval"
    assert write.independent_review_required is True

    # High-impact capability defaults stay denied unless an explicit grant exists.
    denied = auto_review.evaluate_action(_action("delete"), profile="manual")
    assert denied.outcome == "denied"
    assert denied.reason_code == "capability_denied"


def test_assisted_auto_approves_reads_and_tests_but_not_writes(data_dir):
    read = auto_review.evaluate_action(_action("read"), profile="assisted")
    assert read.outcome == "auto_approved"
    assert read.reason_code == "profile_auto_approved_routine"

    tests = auto_review.evaluate_action(
        _action("execute", tests=True, tool="pytest"), profile="assisted")
    assert tests.outcome == "auto_approved"

    local_model = auto_review.evaluate_action(
        _action("model-inference-local", tool="ollama"), profile="assisted")
    assert local_model.outcome == "auto_approved"

    write = auto_review.evaluate_action(
        _action("write", staged_code_edit=True), profile="assisted")
    assert write.outcome == "needs_human_approval"
    assert write.independent_review_required is True

    background = auto_review.evaluate_action(
        _action("read", background=True), profile="assisted")
    assert background.outcome == "needs_human_approval"
    assert "background_continuation" in background.required_controls
    assert "background_continuation" in background.reason_code


def test_assisted_never_auto_approves_granted_medium_or_network(data_dir):
    _grant("install-private", "tool", "pip")
    install = auto_review.evaluate_action(
        _action("install-private", scope_kind="tool", scope_value="pip",
                tool="pip"), profile="assisted")
    assert install.outcome == "needs_human_approval"

    _grant("web-fetch", "host-domain", "docs.example.com")
    network = auto_review.evaluate_action(
        _action("web-fetch", scope_kind="host-domain",
                scope_value="docs.example.com"),
        profile="assisted", controls={"external_network": True})
    assert network.outcome == "needs_human_approval"


# --------------------------------------------------------------------------- #
# Trusted Auto Review
# --------------------------------------------------------------------------- #

def test_trusted_auto_approves_routine_scoped_work_with_mandatory_review(data_dir):
    for capability in ("read", "execute", "model-inference-local"):
        decision = auto_review.evaluate_action(
            _action(capability), profile="trusted-auto-review")
        assert decision.outcome == "auto_approved", capability

    write = auto_review.evaluate_action(
        _action("write", staged_code_edit=True, target_paths=("src/mod.py",)),
        profile="trusted-auto-review")
    assert write.outcome == "auto_approved"
    assert write.independent_review_required is True
    assert "independent review" in write.reason.lower()

    commit = auto_review.evaluate_action(
        _action("git-commit", scope_kind="repository",
                scope_value="owner/repo"),
        profile="trusted-auto-review")
    # No owner grant yet -> capability boundary asks for approval.
    assert commit.outcome == "needs_human_approval"
    assert commit.independent_review_required is True


def test_trusted_auto_approves_granted_medium_but_not_cloud_or_high_impact(data_dir):
    _grant("install-private", "tool", "pip")
    install = auto_review.evaluate_action(
        _action("install-private", scope_kind="tool", scope_value="pip",
                tool="pip", install=True),
        profile="trusted-auto-review")
    assert install.outcome == "auto_approved"
    assert install.reason_code == "profile_auto_approved_granted"

    _grant("web-fetch", "host-domain", "docs.example.com")
    research = auto_review.evaluate_action(
        _action("web-fetch", scope_kind="host-domain",
                scope_value="docs.example.com"),
        profile="trusted-auto-review")
    assert research.outcome == "auto_approved"
    # The external-network control is on for Trusted; cloud/LLM remains separate.
    assert research.controls["external_network"] is True

    _grant("model-inference-cloud", "tool", "cloud-model")
    cloud = auto_review.evaluate_action(
        _action("model-inference-cloud", scope_kind="tool",
                scope_value="cloud-model", tool="cloud-model"),
        profile="trusted-auto-review")
    assert cloud.outcome == "needs_human_approval"
    assert "cloud_llm" in cloud.reason_code

    _grant("open-external-project", "path", "/external/project")
    external = auto_review.evaluate_action(
        _action("open-external-project", scope_kind="path",
                scope_value="/external/project"),
        profile="trusted-auto-review")
    assert external.outcome == "needs_human_approval"
    assert "user_file_access" in external.reason_code

    _grant("delete", "path", "/tmp/trusted-delete")
    delete = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/trusted-delete"),
        profile="trusted-auto-review")
    assert delete.outcome == "needs_human_approval"
    assert delete.reason_code == "profile_requires_human_for_high_impact"

    _grant("publish-release", "repository", "owner/repo")
    publish = auto_review.evaluate_action(
        _action("publish-release", scope_kind="repository",
                scope_value="owner/repo", publish=True),
        profile="trusted-auto-review")
    assert publish.outcome == "needs_human_approval"
    assert "release_deployment" in publish.reason_code


# --------------------------------------------------------------------------- #
# Full Autonomy
# --------------------------------------------------------------------------- #

def test_full_autonomy_auto_approves_routine_code_with_review(data_dir):
    write = auto_review.evaluate_action(
        _action("write", staged_code_edit=True), profile="full-autonomy")
    assert write.outcome == "auto_approved"
    assert write.independent_review_required is True
    assert write.reason_code == "profile_auto_approved_routine_independent_review"

    read = auto_review.evaluate_action(_action("read"), profile="full-autonomy")
    assert read.outcome == "auto_approved"
    assert read.independent_review_required is False


def test_full_autonomy_high_impact_requires_exact_owner_grant(data_dir):
    for capability in HIGH_IMPACT:
        granted = auto_review.evaluate_action(_action(capability),
                                              profile="full-autonomy")
        assert granted.outcome == "denied", capability
        assert granted.reason_code == "capability_denied", capability

    _grant("delete", "path", "/tmp/allowed")
    allowed = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/allowed/file.py"),
        profile="full-autonomy")
    assert allowed.outcome == "auto_approved"
    assert allowed.reason_code == "profile_auto_approved_high_impact_grant"
    assert allowed.matched_policy_id is not None
    assert allowed.independent_review_required is False

    outside = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/other/file.py"),
        profile="full-autonomy")
    assert outside.outcome == "denied"
    assert outside.reason_code == "capability_denied"


def test_full_autonomy_high_impact_respects_own_controls(data_dir):
    _grant("publish-release", "repository", "owner/repo")
    publish = auto_review.evaluate_action(
        _action("publish-release", scope_kind="repository",
                scope_value="owner/repo", publish=True),
        profile="full-autonomy")
    assert publish.outcome == "auto_approved"
    assert publish.controls["release_deployment"] is True

    blocked = auto_review.evaluate_action(
        _action("publish-release", scope_kind="repository",
                scope_value="owner/repo", publish=True),
        profile="full-autonomy",
        controls={"release_deployment": False})
    assert blocked.outcome == "needs_human_approval"
    assert "release_deployment" in blocked.reason_code
    # Disabling release does not disable any other control.
    assert blocked.controls["external_network"] is True
    assert blocked.controls["cloud_llm"] is True


def test_full_autonomy_granted_medium_and_cloud_actions(data_dir):
    _grant("model-inference-cloud", "tool", "cloud-model")
    cloud = auto_review.evaluate_action(
        _action("model-inference-cloud", scope_kind="tool",
                scope_value="cloud-model", tool="cloud-model"),
        profile="full-autonomy")
    assert cloud.outcome == "auto_approved"
    assert cloud.controls["cloud_llm"] is True

    blocked = auto_review.evaluate_action(
        _action("model-inference-cloud", scope_kind="tool",
                scope_value="cloud-model", tool="cloud-model"),
        profile="full-autonomy", controls={"cloud_llm": False})
    assert blocked.outcome == "needs_human_approval"
    assert "cloud_llm" in blocked.reason_code

    _grant("open-external-project", "path", "/external/project")
    external = auto_review.evaluate_action(
        _action("open-external-project", scope_kind="path",
                scope_value="/external/project"),
        profile="full-autonomy")
    assert external.outcome == "auto_approved"

    background = auto_review.evaluate_action(
        _action("read", background=True), profile="full-autonomy")
    assert background.outcome == "auto_approved"


# --------------------------------------------------------------------------- #
# Grants, denials, expiry, approvals and allow-once
# --------------------------------------------------------------------------- #

def test_explicit_deny_and_expiry_are_respected(data_dir):
    _grant("delete", "path", "/tmp/deny", decision="deny")
    _grant("delete", "path", "/tmp/deny", decision="always")
    denied = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/deny/x"),
        profile="full-autonomy")
    assert denied.outcome == "denied"
    assert denied.reason_code == "capability_denied"

    future = (datetime.now() + timedelta(minutes=5)).isoformat(timespec="seconds")
    past = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    _grant("git-push", "repository", "owner/future", expires_at=future)
    live = auto_review.evaluate_action(
        _action("git-push", scope_kind="repository", scope_value="owner/future"),
        profile="full-autonomy")
    assert live.outcome == "auto_approved"
    _grant("git-push", "repository", "owner/past", expires_at=past)
    expired = auto_review.evaluate_action(
        _action("git-push", scope_kind="repository", scope_value="owner/past"),
        profile="full-autonomy")
    assert expired.outcome == "denied"

    permissions.revoke_capability("git-push")
    revoked = auto_review.evaluate_action(
        _action("git-push", scope_kind="repository", scope_value="owner/future"),
        profile="full-autonomy")
    assert revoked.outcome == "denied"


def test_allow_once_grant_is_single_use(data_dir):
    _grant("delete", "path", "/tmp/once", decision="allow-once")
    first = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/once/file"),
        profile="full-autonomy")
    assert first.outcome == "auto_approved"
    second = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/once/file"),
        profile="full-autonomy")
    assert second.outcome == "denied"


def test_pending_approval_is_durable_and_respected(data_dir):
    request = permissions.request_capability(
        "delete", permissions.CapabilityScope("path", "/tmp/approval"),
        reason="cleanup")
    pending = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/approval/x"),
        profile="full-autonomy")
    assert pending.outcome == "needs_human_approval"
    assert pending.approval_id == request["approval_id"]
    assert pending.reason_code == "capability_needs_approval"

    permissions.decide_capability_approval(
        request["approval_id"], True, decision="allow-once")
    approved = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/approval/x"),
        profile="full-autonomy")
    assert approved.outcome == "auto_approved"
    consumed = auto_review.evaluate_action(
        _action("delete", scope_kind="path", scope_value="/tmp/approval/x"),
        profile="full-autonomy")
    assert consumed.outcome == "denied"


# --------------------------------------------------------------------------- #
# Controls stay separate (no silent cross-enable)
# --------------------------------------------------------------------------- #

def test_controls_are_independent_no_cross_enable(data_dir):
    controls = auto_review.controls_for_profile("assisted")
    assert controls["external_network"] is False
    controls["external_network"] = True
    # The stored profile and the other controls are untouched.
    assert auto_review.controls_for_profile("assisted")["external_network"] is False
    assert auto_review.controls_for_profile("assisted")["cloud_llm"] is False

    # Enabling the network control does not enable cloud/release/user-file.
    effective = auto_review.controls_for_profile(
        "assisted", {"external_network": True})
    assert effective["external_network"] is True
    assert effective["cloud_llm"] is False
    assert effective["release_deployment"] is False
    assert effective["user_file_access"] is False

    # A web-fetch grant does not allow other network/research capabilities.
    _grant("web-fetch", "host-domain", "docs.example.com")
    web_fetch = auto_review.evaluate_action(
        _action("web-fetch", scope_kind="host-domain",
                scope_value="docs.example.com"),
        profile="trusted-auto-review")
    assert web_fetch.outcome == "auto_approved"
    web_search = auto_review.evaluate_action(
        _action("web-search", scope_kind="host-domain",
                scope_value="docs.example.com"),
        profile="trusted-auto-review")
    assert web_search.outcome == "denied"
    browser = auto_review.evaluate_action(
        _action("browser-interact", scope_kind="host-domain",
                scope_value="docs.example.com"),
        profile="trusted-auto-review")
    assert browser.outcome == "denied"

    # A publish grant does not allow git-push (and vice versa).
    _grant("publish-release", "repository", "owner/repo")
    assert auto_review.evaluate_action(
        _action("git-push", scope_kind="repository", scope_value="owner/repo"),
        profile="full-autonomy").outcome == "denied"


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


def test_decisions_are_deterministic_and_do_not_mutate_grants(data_dir):
    _grant("web-fetch", "host-domain", "docs.example.com")
    action = _action("web-fetch", scope_kind="host-domain",
                     scope_value="docs.example.com")
    first = auto_review.evaluate_action(action, profile="trusted-auto-review")
    second = auto_review.evaluate_action(action, profile="trusted-auto-review")
    assert first.to_dict() == second.to_dict()
    assert first.audit_event_id != second.audit_event_id  # audits are append-only
    # Decision dict itself is deterministic (audit id excluded from to_dict).
    assert "audit_event_id" not in first.to_dict()
    grants_after = permissions.list_capability_grants("web-fetch")
    assert len(grants_after) == 1


def test_audit_failure_fails_closed(monkeypatch, data_dir):
    monkeypatch.setattr(auto_review, "_emit_audit", lambda decision: None)
    decision = auto_review.evaluate_action(_action("read"), profile="full-autonomy")
    assert decision.outcome == "denied"
    assert decision.reason_code == "audit_unavailable"


def test_legacy_permission_behaviour_is_untouched(data_dir):
    before = permissions.get_policy()
    assert before["read"] is True and before["delete"] is False
    auto_review.evaluate_action(_action("delete"), profile="full-autonomy")
    auto_review.evaluate_action(_action("read"), profile="manual")
    assert permissions.get_policy() == before
    assert permissions.list_capability_grants() == []
    with pytest.raises(permissions.PermissionDenied):
        permissions.require("delete")
    with pytest.raises(permissions.PermissionDenied):
        permissions.assert_model_permitted(
            "ollama/gpt-oss:120b-cloud", "http://127.0.0.1:11434")

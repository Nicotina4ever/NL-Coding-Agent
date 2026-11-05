"""Independent auto-review policy engine and autonomy profiles (NL-BP-166/167).

This is a deterministic policy layer on top of the capability taxonomy and durable
approvals from NL-BP-168 (nl_coding_agent.core.permissions). It does not execute
tools and is not wired into the GUI or the supervisor yet: callers evaluate one
proposed action descriptor and receive a structured decision.

Non-negotiable rules implemented here
-------------------------------------
* The existing fail-closed capability boundary (permissions.check_capability) is
  always consulted; this module never reimplements or bypasses grant/approval
  matching, deny precedence, expiry or revocation.
* High-impact capabilities (delete, publish-release, secret-use, install-system,
  git-push, network-write) are never auto-approved without an explicit
  owner-scoped durable grant covering that exact capability and scope. Default
  decisions for them stay Denied.
* Independent review and the staged-candidate/regression gates remain mandatory
  for code/source modifications and staged promotions even when tool actions are
  auto-approved; independent_review_required stays True in the decision.
* Seven independent controls (tool auto-authorization, automated code review,
  background mission continuation, external network, cloud LLM use, user-file
  access, release/deployment) are separate profile/overrides bits. Enabling one
  never enables another and an action may require more than one.
* Full Autonomy is explicitly not an OS sandbox: it runs with the current user's
  operating-system rights, application-level filters cannot reliably sandbox
  arbitrary shell processes, high-impact actions remain separately gated and
  code review/regression gates still apply.
* Every decision is audited as an events row (source 'permissions',
  event_kind 'capability_auto_review') without logging secrets, commands, target
  paths, hosts, descriptions or arbitrary context values.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from nl_coding_agent.core import permissions
from nl_coding_agent.persistence import database

# --- profiles and controls --------------------------------------------------

PROFILE_MANUAL = "manual"
PROFILE_ASSISTED = "assisted"
PROFILE_TRUSTED = "trusted-auto-review"
PROFILE_FULL = "full-autonomy"
PROFILES: tuple[str, ...] = (
    PROFILE_MANUAL, PROFILE_ASSISTED, PROFILE_TRUSTED, PROFILE_FULL,
)
DEFAULT_PROFILE = PROFILE_MANUAL

#: Accepted profile aliases (legacy/UI wording); unknown ids still fail closed.
PROFILE_ALIASES: dict[str, str] = {
    PROFILE_MANUAL: PROFILE_MANUAL,
    "off": PROFILE_MANUAL,
    PROFILE_ASSISTED: PROFILE_ASSISTED,
    PROFILE_TRUSTED: PROFILE_TRUSTED,
    "trusted": PROFILE_TRUSTED,
    "trusted_auto_review": PROFILE_TRUSTED,
    PROFILE_FULL: PROFILE_FULL,
    "full": PROFILE_FULL,
    "full_autonomy": PROFILE_FULL,
    "unrestricted": PROFILE_FULL,
}

CONTROL_TOOL_AUTO_AUTH = "tool_auto_authorization"
CONTROL_AUTOMATED_REVIEW = "automated_review"
CONTROL_BACKGROUND = "background_continuation"
CONTROL_EXTERNAL_NETWORK = "external_network"
CONTROL_CLOUD_LLM = "cloud_llm"
CONTROL_USER_FILE = "user_file_access"
CONTROL_RELEASE = "release_deployment"
CONTROLS: tuple[str, ...] = (
    CONTROL_TOOL_AUTO_AUTH,
    CONTROL_AUTOMATED_REVIEW,
    CONTROL_BACKGROUND,
    CONTROL_EXTERNAL_NETWORK,
    CONTROL_CLOUD_LLM,
    CONTROL_USER_FILE,
    CONTROL_RELEASE,
)

OUTCOME_AUTO_APPROVED = "auto_approved"
OUTCOME_NEEDS_HUMAN_APPROVAL = "needs_human_approval"
OUTCOME_DENIED = "denied"
OUTCOMES: tuple[str, ...] = (
    OUTCOME_AUTO_APPROVED, OUTCOME_NEEDS_HUMAN_APPROVAL, OUTCOME_DENIED,
)

DEFAULT_AUDIT_EVENT_KIND = "capability_auto_review"

#: High-impact capabilities: never auto-approved without an exact owner-scoped grant.
HIGH_IMPACT_CAPABILITIES: frozenset[str] = frozenset({
    permissions.CAPABILITY_DELETE,
    permissions.CAPABILITY_PUBLISH_RELEASE,
    permissions.CAPABILITY_SECRET_USE,
    permissions.CAPABILITY_INSTALL_SYSTEM,
    permissions.CAPABILITY_GIT_PUSH,
    permissions.CAPABILITY_NETWORK_WRITE,
})

#: Local reversible capabilities auto-approved by Assisted/Trusted/Full profiles.
#: Assisted excludes write; code edits require the Trusted/Full profile.
ROUTINE_CAPABILITIES: frozenset[str] = frozenset({
    permissions.CAPABILITY_READ,
    permissions.CAPABILITY_EXECUTE,
    permissions.CAPABILITY_MODEL_INFERENCE_LOCAL,
})

#: Capabilities that additionally require the external_network control.
NETWORK_CAPABILITIES: frozenset[str] = frozenset({
    permissions.CAPABILITY_WEB_SEARCH,
    permissions.CAPABILITY_WEB_FETCH,
    permissions.CAPABILITY_BROWSER_INTERACT,
    permissions.CAPABILITY_DOWNLOAD,
    permissions.CAPABILITY_NETWORK_WRITE,
})

_ALLOW_DECISIONS = frozenset({
    permissions.DECISION_ALLOW_ONCE,
    permissions.DECISION_ALLOW_MISSION,
    permissions.DECISION_ALLOW_PROJECT,
    permissions.DECISION_ALWAYS,
})

_FLAG_CAPABILITIES: dict[str, frozenset[str]] = {
    "publish": frozenset({permissions.CAPABILITY_PUBLISH_RELEASE}),
    "delete": frozenset({permissions.CAPABILITY_DELETE}),
    "secret_access": frozenset({permissions.CAPABILITY_SECRET_USE}),
    "install": frozenset({
        permissions.CAPABILITY_INSTALL_PRIVATE,
        permissions.CAPABILITY_INSTALL_SYSTEM,
    }),
}

_OS_RIGHTS_DISCLOSURE = (
    "Runs as the current Windows user with the same operating-system rights as "
    "the application. Capability grants, approvals and path filters are an "
    "application-level policy, not an OS sandbox: arbitrary subprocesses or code "
    "executed with user privileges can bypass them. Use isolated/disposable "
    "workspaces for risky work; total reversibility is not claimed."
)


@dataclass(frozen=True)
class AutonomyProfile:
    """One selectable autonomy profile (deterministic descriptor)."""

    id: str
    label: str
    description: str
    controls: dict[str, bool]
    auto_routine_capabilities: frozenset[str]
    auto_approve_medium_with_grant: bool
    auto_approve_high_impact_with_grant: bool
    os_rights_disclosure: str
    limits: tuple[str, ...]

    def descriptor(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "controls": dict(self.controls),
            "auto_routine_capabilities": sorted(self.auto_routine_capabilities),
            "auto_approve_medium_with_grant": self.auto_approve_medium_with_grant,
            "auto_approve_high_impact_with_grant": (
                self.auto_approve_high_impact_with_grant),
            "os_rights_disclosure": self.os_rights_disclosure,
            "limits": list(self.limits),
        }


_COMMON_LIMITS = (
    "Application-level filter only: not an OS sandbox and no network isolation.",
    "Code/source modifications and staged promotions still require the existing "
    "independent review and staged-candidate/regression gates.",
    "High-impact capabilities always require an explicit owner-scoped grant.",
)

AUTONOMY_PROFILES: dict[str, AutonomyProfile] = {
    PROFILE_MANUAL: AutonomyProfile(
        id=PROFILE_MANUAL,
        label="Manual",
        description=(
            "Every potentially mutating tool action requires explicit human "
            "approval; only read-only policy inspection is automatic here."
        ),
        controls={control: False for control in CONTROLS},
        auto_routine_capabilities=frozenset(),
        auto_approve_medium_with_grant=False,
        auto_approve_high_impact_with_grant=False,
        os_rights_disclosure=_OS_RIGHTS_DISCLOSURE,
        limits=_COMMON_LIMITS + (
            "No tool action is auto-approved; durable approvals are still needed.",
        ),
    ),
    PROFILE_ASSISTED: AutonomyProfile(
        id=PROFILE_ASSISTED,
        label="Assisted",
        description=(
            "Autonomous planning, reads, local inference and test execution; "
            "writes, installs, publishes and unusual changes ask a human."
        ),
        controls={
            CONTROL_TOOL_AUTO_AUTH: True,
            CONTROL_AUTOMATED_REVIEW: True,
            CONTROL_BACKGROUND: False,
            CONTROL_EXTERNAL_NETWORK: False,
            CONTROL_CLOUD_LLM: False,
            CONTROL_USER_FILE: False,
            CONTROL_RELEASE: False,
        },
        auto_routine_capabilities=ROUTINE_CAPABILITIES,
        auto_approve_medium_with_grant=False,
        auto_approve_high_impact_with_grant=False,
        os_rights_disclosure=_OS_RIGHTS_DISCLOSURE,
        limits=_COMMON_LIMITS + (
            "Writes, installs, network research, cloud and releases need a human.",
        ),
    ),
    PROFILE_TRUSTED: AutonomyProfile(
        id=PROFILE_TRUSTED,
        label="Trusted Auto Review",
        description=(
            "Routine authorized project work (reads, patches/staged edits, tests, "
            "debugging, local private installs, approved network research and "
            "next-mission progress) is auto-approved without per-action prompts; "
            "mandatory independent code review and every staged-candidate gate "
            "remain in force."
        ),
        controls={
            CONTROL_TOOL_AUTO_AUTH: True,
            CONTROL_AUTOMATED_REVIEW: True,
            CONTROL_BACKGROUND: True,
            CONTROL_EXTERNAL_NETWORK: True,
            CONTROL_CLOUD_LLM: False,
            CONTROL_USER_FILE: False,
            CONTROL_RELEASE: False,
        },
        auto_routine_capabilities=ROUTINE_CAPABILITIES | {
            permissions.CAPABILITY_WRITE,
        },
        auto_approve_medium_with_grant=True,
        auto_approve_high_impact_with_grant=False,
        os_rights_disclosure=_OS_RIGHTS_DISCLOSURE,
        limits=_COMMON_LIMITS + (
            "Cloud LLM, user-file access, release/deployment and high-impact "
            "actions stay human-gated unless their own control/grant exists.",
        ),
    ),
    PROFILE_FULL: AutonomyProfile(
        id=PROFILE_FULL,
        label="Full Autonomy",
        description=(
            "Explicit user-opt-in broad execution across registered project/tool "
            "scopes. Routine work is auto-approved; high-impact actions are "
            "auto-approved only with an explicit owner-scoped grant and the "
            "matching profile control. Code review and regression gates remain "
            "mandatory and the OS-rights disclosure below remains accurate."
        ),
        controls={control: True for control in CONTROLS},
        auto_routine_capabilities=ROUTINE_CAPABILITIES | {
            permissions.CAPABILITY_WRITE,
        },
        auto_approve_medium_with_grant=True,
        auto_approve_high_impact_with_grant=True,
        os_rights_disclosure=_OS_RIGHTS_DISCLOSURE,
        limits=_COMMON_LIMITS + (
            "Broad execution, not unrestricted: Full Autonomy is still an "
            "application-level filter, not an OS sandbox.",
            "Independent review can reject even in Full Autonomy; no forced "
            "unlimited mission count is granted by this profile descriptor.",
            "Emergency stop, durable approvals and owner revocation remain "
            "authoritative.",
        ),
    ),
}


def normalize_profile(profile: object = None) -> str:
    """Validate a profile id; None selects the fail-closed default (Manual)."""
    if profile is None:
        return DEFAULT_PROFILE
    if not isinstance(profile, str) or not profile.strip():
        raise ValueError(
            "Unknown autonomy profile: " + repr(profile) + "; expected one of "
            + ", ".join(PROFILES)
        )
    normalized = profile.strip().lower()
    normalized = PROFILE_ALIASES.get(normalized, normalized)
    if normalized not in AUTONOMY_PROFILES:
        raise ValueError(
            "Unknown autonomy profile: " + repr(profile) + "; expected one of "
            + ", ".join(PROFILES)
        )
    return normalized


def profile_descriptor(profile: object = None) -> dict:
    """Return one complete, truthful profile descriptor (controls + limits)."""
    return AUTONOMY_PROFILES[normalize_profile(profile)].descriptor()


def list_profiles() -> list[dict]:
    return [AUTONOMY_PROFILES[profile].descriptor() for profile in PROFILES]


def controls_for_profile(profile: object = None,
                         overrides: dict | None = None) -> dict[str, bool]:
    """Return effective controls; every control is independent (no cross-enable)."""
    normalized = normalize_profile(profile)
    controls = dict(AUTONOMY_PROFILES[normalized].controls)
    for name, value in dict(overrides or {}).items():
        if name not in CONTROLS:
            raise ValueError(
                "Unknown autonomy control: " + repr(name) + "; expected one of "
                + ", ".join(CONTROLS)
            )
        controls[name] = bool(value)
    return controls


def is_high_impact(capability: object) -> bool:
    return permissions.normalize_capability(capability) in HIGH_IMPACT_CAPABILITIES


# --- action and decision descriptors ---------------------------------------

@dataclass(frozen=True)
class ActionDescriptor:
    """One proposed tool/action evaluated by the policy engine.

    capability: taxonomy id (required). scope_kind/scope_value: permission scope
    under which the action would run. command/paths/host/description are used
    only for evaluation and are never written to the audit log.
    """

    capability: str
    scope_kind: str = permissions.SCOPE_PROJECT
    scope_value: str | None = None
    tool: str = ""
    command: str = ""
    target_paths: tuple[str, ...] = ()
    host: str = ""
    staged_code_edit: bool = False
    tests: bool = False
    install: bool = False
    publish: bool = False
    delete: bool = False
    secret_access: bool = False
    background: bool = False
    user_file: bool = False
    description: str = ""
    context: dict = field(default_factory=dict)

    def scope(self) -> permissions.CapabilityScope:
        return permissions.CapabilityScope(
            self.scope_kind,
            self.scope_value,
            self.context.get("project_id") if isinstance(self.context, dict) else None,
        )


@dataclass(frozen=True)
class AutoReviewDecision:
    """Structured auto-review result (deterministic for identical inputs)."""

    outcome: str
    reason: str
    reason_code: str
    profile: str
    capability: str
    risk: str
    matched_policy_id: int | None
    approval_id: int | None
    required_controls: tuple[str, ...]
    controls: dict[str, bool]
    independent_review_required: bool
    audit_event_id: int | None = None
    scope_kind: str = ""

    @property
    def auto_approved(self) -> bool:
        return self.outcome == OUTCOME_AUTO_APPROVED

    @property
    def needs_human_approval(self) -> bool:
        return self.outcome == OUTCOME_NEEDS_HUMAN_APPROVAL

    @property
    def denied(self) -> bool:
        return self.outcome == OUTCOME_DENIED

    @property
    def grant_id(self) -> int | None:
        """Alias for the matched policy/grant id."""
        return self.matched_policy_id

    @property
    def policy_id(self) -> int | None:
        """Alias for the matched policy/grant id."""
        return self.matched_policy_id

    @property
    def risk_class(self) -> str:
        """Alias for the capability risk class."""
        return self.risk

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "auto_approved": self.auto_approved,
            "needs_human_approval": self.needs_human_approval,
            "denied": self.denied,
            "reason": self.reason,
            "reason_code": self.reason_code,
            "profile": self.profile,
            "capability": self.capability,
            "risk": self.risk,
            "matched_policy_id": self.matched_policy_id,
            "approval_id": self.approval_id,
            "required_controls": list(self.required_controls),
            "controls": dict(self.controls),
            "independent_review_required": self.independent_review_required,
            "scope_kind": self.scope_kind,
        }


def _decision(
    action: ActionDescriptor,
    profile: str,
    *,
    outcome: str,
    reason: str,
    reason_code: str,
    controls: dict[str, bool],
    required_controls: tuple[str, ...],
    independent_review_required: bool,
    matched_policy_id: int | None = None,
    approval_id: int | None = None,
) -> AutoReviewDecision:
    return AutoReviewDecision(
        outcome=outcome,
        reason=reason,
        reason_code=reason_code,
        profile=profile,
        capability=action.capability,
        risk=permissions.CAPABILITY_RISK.get(action.capability, "unknown"),
        matched_policy_id=matched_policy_id,
        approval_id=approval_id,
        required_controls=required_controls,
        controls=dict(controls),
        independent_review_required=bool(independent_review_required),
        scope_kind=action.scope_kind,
    )


# --- helpers ----------------------------------------------------------------

def _independent_review_required(action: ActionDescriptor) -> bool:
    # Code/source modifications and staged promotions must stay independently
    # reviewed even when the tool call itself is auto-approved.
    if action.staged_code_edit:
        return True
    return action.capability in (
        permissions.CAPABILITY_WRITE,
        permissions.CAPABILITY_GIT_COMMIT,
    )


def _inconsistent_flags(action: ActionDescriptor) -> str | None:
    for flag, allowed in _FLAG_CAPABILITIES.items():
        if bool(getattr(action, flag, False)) and action.capability not in allowed:
            return flag
    return None


def _required_controls(action: ActionDescriptor) -> tuple[str, ...]:
    required: list[str] = []
    if action.background:
        required.append(CONTROL_BACKGROUND)
    if (action.capability in NETWORK_CAPABILITIES
            or (bool(action.host) and action.capability in NETWORK_CAPABILITIES)):
        required.append(CONTROL_EXTERNAL_NETWORK)
    if action.capability == permissions.CAPABILITY_MODEL_INFERENCE_CLOUD:
        required.append(CONTROL_CLOUD_LLM)
    if (action.capability == permissions.CAPABILITY_OPEN_EXTERNAL_PROJECT
            or action.user_file):
        required.append(CONTROL_USER_FILE)
    if action.capability == permissions.CAPABILITY_PUBLISH_RELEASE or action.publish:
        required.append(CONTROL_RELEASE)
    return tuple(dict.fromkeys(required))


def _expired(row: dict, *keys: str) -> bool:
    now = datetime.now().isoformat(timespec="seconds")
    for key in keys:
        value = row.get(key)
        if value and str(value) <= now:
            return True
    return False


def _active_owner_grant(row: dict) -> bool:
    if str(row.get("decision")) not in _ALLOW_DECISIONS:
        return False
    if row.get("revoked_at") or row.get("consumed_at"):
        return False
    if _expired(row, "expires_at"):
        return False
    source = str(row.get("source") or "human").strip().lower()
    return source not in ("model", "agent", "llm")


def _explicit_owner_grant(
    action: ActionDescriptor, context: dict,
) -> dict | None:
    """Find a durable owner grant covering this exact capability and scope kind."""
    try:
        grants = permissions.list_capability_grants(action.capability, limit=500)
    except Exception:
        return None
    action_scope = action.scope()
    context_project = context.get("project_id")
    if context_project is None:
        context_project = action_scope.project_id
    for row in grants:
        if not _active_owner_grant(row):
            continue
        if str(row.get("scope_kind")) != action_scope.kind:
            continue
        row_project = row.get("project_id")
        if row_project is not None:
            if context_project is None or int(context_project) != int(row_project):
                continue
        row_value = row.get("scope_value")
        if row_value is None:
            return row
        if action_scope.value is None:
            continue
        try:
            matches = permissions._value_matches(
                action_scope.kind, row_value, action_scope.value)
        except Exception:
            matches = str(row_value) == str(action_scope.value)
        if matches:
            return row
    return None


def _emit_audit(decision: AutoReviewDecision) -> int | None:
    """Append one capability_auto_review event; never logs secrets/context.

    Payload is deliberately limited to policy metadata: no command, target paths,
    host, description, scope value or arbitrary context value is written.
    """
    payload = {
        "kind": "auto_review",
        "outcome": decision.outcome,
        "reason_code": decision.reason_code,
        "profile": decision.profile,
        "capability": decision.capability,
        "risk": decision.risk,
        "scope_kind": decision.scope_kind,
        "required_controls": list(decision.required_controls),
        "controls": dict(decision.controls),
        "independent_review_required": bool(decision.independent_review_required),
        "policy_id": decision.matched_policy_id,
        "approval_id": decision.approval_id,
    }
    level = {
        OUTCOME_AUTO_APPROVED: "info",
        OUTCOME_NEEDS_HUMAN_APPROVAL: "warning",
        OUTCOME_DENIED: "warning",
    }.get(decision.outcome, "info")
    try:
        conn = database.init_db()
        try:
            before = conn.execute("SELECT MAX(id) FROM events").fetchone()[0] or 0
            database.log_event(
                conn,
                "Auto-review " + decision.outcome + ": " + decision.capability
                + " (" + decision.profile + "; " + decision.reason_code + ")",
                source="permissions",
                level=level,
                payload=json.dumps(payload, sort_keys=True),
                event_kind=DEFAULT_AUDIT_EVENT_KIND,
            )
            after = conn.execute("SELECT MAX(id) FROM events").fetchone()[0] or 0
            return int(after) if after > before else None
        finally:
            conn.close()
    except Exception:
        return None


# --- evaluation -------------------------------------------------------------

def evaluate_action(
    action: ActionDescriptor,
    profile: object = None,
    *,
    controls: dict | None = None,
    capability_checker: Any = None,
) -> AutoReviewDecision:
    """Evaluate one proposed action against the capability boundary and profile.

    Deterministic for identical persisted state + inputs. Every outcome writes one
    audit event; an audit-write failure fails closed as Denied.
    """
    if isinstance(action, dict):
        data = dict(action)
        unknown = sorted(set(data) - set(ActionDescriptor.__dataclass_fields__))
        if unknown:
            raise ValueError("Unknown action descriptor field(s): " + ", ".join(unknown))
        if isinstance(data.get("target_paths"), list):
            data["target_paths"] = tuple(data["target_paths"])
        action = ActionDescriptor(**data)
    if not isinstance(action, ActionDescriptor):
        raise ValueError(
            "action must be an ActionDescriptor or a mapping: " + repr(action))
    profile_id = normalize_profile(profile)
    effective_controls = controls_for_profile(profile_id, controls)
    # Validate capability/scope through the existing taxonomy (raises ValueError).
    capability = permissions.normalize_capability(action.capability)
    if capability != action.capability:
        action = replace(action, capability=capability)
    action.scope()  # validates scope kind/values
    review_required = _independent_review_required(action)

    inconsistent = _inconsistent_flags(action)
    if inconsistent is not None:
        decision = _decision(
            action, profile_id,
            outcome=OUTCOME_DENIED,
            reason=(
                "Denied: action flag '" + inconsistent + "' is inconsistent with "
                "capability '" + action.capability + "'."
            ),
            reason_code="inconsistent_action_descriptor",
            controls=effective_controls,
            required_controls=_required_controls(action),
            independent_review_required=review_required,
        )
        return _finalize(decision)

    context = dict(action.context or {})
    required = _required_controls(action)
    high_impact = action.capability in HIGH_IMPACT_CAPABILITIES
    capability_decision = (capability_checker or permissions.check_access)(
        action.capability, action.scope(), context)
    allowed = isinstance(capability_decision, permissions.Allowed)
    return _finalize(_decision(
        action, profile_id,
        outcome=OUTCOME_AUTO_APPROVED if allowed else OUTCOME_DENIED,
        reason=capability_decision.reason,
        reason_code="access_mode_allowed" if allowed else "capability_denied",
        controls=effective_controls, required_controls=required,
        independent_review_required=review_required,
        matched_policy_id=None,
    ))


def _finalize(decision: AutoReviewDecision) -> AutoReviewDecision:
    event_id = _emit_audit(decision)
    if event_id is None:
        # Fail closed: a decision that cannot be audited is not executed as approved.
        return replace(
            decision,
            outcome=OUTCOME_DENIED,
            reason=(
                "Denied: auto-review decision could not be audited "
                "(fail-closed). " + decision.reason
            ),
            reason_code="audit_unavailable",
            audit_event_id=None,
        )
    return replace(decision, audit_event_id=event_id)

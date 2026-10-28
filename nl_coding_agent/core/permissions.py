"""Universal permission model and cloud/network escalation enforcement.

Single source of truth for capability permissions (SPEC-25 / NL-BP-072) and
for the cloud-escalation gate (SPEC-15, SPEC-13A / NL-BP-076).

Design rules
------------
* Permissions are owned by the human/backend. The model-facing tool surface
  (nl_coding_agent.tools.crew_tools) does not import this module, so an agent
  cannot grant itself a capability and no "request permission" tool is exposed
  to the model.
* Fail-closed defaults: READ/WRITE/EXECUTE are granted locally so the staged
  developer/debugger pipeline keeps working, while DELETE/NETWORK/CLOUD are
  denied until an explicit grant is recorded.
* Persistence reuses the existing app_settings table (no DB migration).
  Keys: permissions.policy.global and the optional
  permissions.policy.project.<project_id>. The stored JSON maps contain only
  *explicit* decisions; defaults and the global layer are merged in code.
  A missing or malformed row therefore falls back to the deny-by-default
  policy instead of granting anything.
* Every grant/revoke appends one events row with source 'permissions'
  (scope, project, actor and resulting decision; never file contents or
  secrets).
* No environment variable or feature flag disables these checks.

Classification heuristics
-------------------------
* A model name is cloud when it contains the token 'cloud' (Ollama marks
  cloud models with the '-cloud' suffix, e.g. gpt-oss:120b-cloud). The name is
  split on non-alphanumeric characters so local names such as 'cloudless' are
  not misclassified.
* Endpoint locality is classified separately: loopback hosts (127.0.0.0/8,
  localhost, ::1) are local; any other non-empty endpoint is remote and
  requires an explicit NETWORK grant. An empty/None base_url is "unknown" and
  does not by itself trigger the network gate (a cloud model name still does).
"""
from __future__ import annotations

import ipaddress
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar, Iterator
from urllib.parse import urlparse

from nl_coding_agent.persistence.database import init_db

# --------------------------------------------------------------------------- #
# Scopes and defaults
# --------------------------------------------------------------------------- #

READ = "read"
WRITE = "write"
EXECUTE = "execute"
DELETE = "delete"
NETWORK = "network"
CLOUD = "cloud"

SCOPES: tuple[str, ...] = (READ, WRITE, EXECUTE, DELETE, NETWORK, CLOUD)

#: Default effective policy. Fail-closed for destructive/outbound capabilities.
DEFAULT_GRANTS: dict[str, bool] = {
    READ: True,
    WRITE: True,
    EXECUTE: True,
    DELETE: False,
    NETWORK: False,
    CLOUD: False,
}

#: app_settings keys. The stored value is a JSON map of explicit scope decisions.
GLOBAL_POLICY_KEY = "permissions.policy.global"
PROJECT_POLICY_KEY_PREFIX = "permissions.policy.project."

AUDIT_SOURCE = "permissions"
DEFAULT_GRANT_SOURCE = "human"

_LOCAL_HOSTNAMES = frozenset({"localhost", "::1", "127.0.0.1"})
_NAME_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


class PermissionDenied(RuntimeError):
    """Raised when an operation is not covered by an explicit permission grant."""

    def __init__(
        self,
        message: str,
        *,
        scope: str | None = None,
        project_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.scope = scope
        self.project_id = project_id


# --------------------------------------------------------------------------- #
# Validation and persistence helpers
# --------------------------------------------------------------------------- #

def normalize_scope(scope: object) -> str:
    """Validate and normalize a scope name.

    Unknown/non-string scopes raise ValueError (never silently grant).
    """
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError(
            f"Unknown permission scope: {scope!r}; expected one of {', '.join(SCOPES)}"
        )
    normalized = scope.strip().lower()
    if normalized not in SCOPES:
        raise ValueError(
            f"Unknown permission scope: {scope!r}; expected one of {', '.join(SCOPES)}"
        )
    return normalized


def _normalize_project_id(project_id: object) -> int | None:
    if project_id is None:
        return None
    if isinstance(project_id, bool):
        raise ValueError(f"Invalid project_id: {project_id!r}")
    try:
        return int(project_id)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid project_id: {project_id!r}") from None


def _normalize_source(source: object) -> str:
    text = str(source or "").strip()
    return text or DEFAULT_GRANT_SOURCE


def policy_key(project_id: int | None = None) -> str:
    """Return the app_settings key holding the policy for this scope."""
    project_id = _normalize_project_id(project_id)
    if project_id is None:
        return GLOBAL_POLICY_KEY
    return f"{PROJECT_POLICY_KEY_PREFIX}{project_id}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def _connection() -> Iterator:
    conn = init_db()
    try:
        yield conn
    finally:
        conn.close()


def _read_raw(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row is not None else None


def _parse_overrides(raw: str | None) -> dict[str, bool]:
    """Parse one stored override map; malformed data yields {} (fail-closed)."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        scope: value
        for scope, value in data.items()
        if scope in SCOPES and isinstance(value, bool)
    }


def _effective_policy(conn, project_id: int | None = None) -> dict[str, bool]:
    """Defaults <- global overrides <- optional per-project overrides."""
    policy = dict(DEFAULT_GRANTS)
    policy.update(_parse_overrides(_read_raw(conn, GLOBAL_POLICY_KEY)))
    if project_id is not None:
        policy.update(
            _parse_overrides(_read_raw(conn, policy_key(project_id)))
        )
    return policy


def _stored_overrides(conn, project_id: int | None) -> dict[str, bool]:
    return _parse_overrides(_read_raw(conn, policy_key(project_id)))


def _write_overrides(conn, overrides: dict[str, bool], project_id: int | None) -> str:
    key = policy_key(project_id)
    value = json.dumps(overrides, sort_keys=True)
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, _now()),
    )
    return key


def _audit(
    conn,
    key: str,
    scope: str,
    *,
    granted: bool,
    project_id: int | None,
    source: str,
) -> None:
    action = "granted" if granted else "revoked"
    message = f"Permission {action}: {scope}"
    if project_id is not None:
        message += f" (project {project_id})"
    message += f" [source: {source}]"
    payload = json.dumps(
        {
            "action": action,
            "scope": scope,
            "granted": granted,
            "project_id": project_id,
            "source": source,
            "policy_key": key,
        },
        sort_keys=True,
    )
    conn.execute(
        "INSERT INTO events (source, level, message, payload) VALUES (?,?,?,?)",
        (AUDIT_SOURCE, "info" if granted else "warning", message, payload),
    )


# --------------------------------------------------------------------------- #
# Public permission API (human/backend owned)
# --------------------------------------------------------------------------- #

def grant(
    scope: str,
    project_id: int | None = None,
    source: str = DEFAULT_GRANT_SOURCE,
) -> None:
    """Explicitly grant one scope and append an audit event.

    project_id=None grants globally; a project id stores an override that
    applies only to that project. The grant is persisted immediately.
    """
    scope = normalize_scope(scope)
    project_id = _normalize_project_id(project_id)
    source = _normalize_source(source)
    with _connection() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        overrides = _stored_overrides(conn, project_id)
        overrides[scope] = True
        key = _write_overrides(conn, overrides, project_id)
        _audit(conn, key, scope, granted=True, project_id=project_id, source=source)


def revoke(
    scope: str,
    project_id: int | None = None,
    source: str = DEFAULT_GRANT_SOURCE,
) -> None:
    """Explicitly revoke one scope and append an audit event (fail-closed)."""
    scope = normalize_scope(scope)
    project_id = _normalize_project_id(project_id)
    source = _normalize_source(source)
    with _connection() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        overrides = _stored_overrides(conn, project_id)
        overrides[scope] = False
        key = _write_overrides(conn, overrides, project_id)
        _audit(conn, key, scope, granted=False, project_id=project_id, source=source)


def is_granted(scope: str, project_id: int | None = None) -> bool:
    """Return True only when the scope is explicitly granted (defaults applied)."""
    scope = normalize_scope(scope)
    project_id = _normalize_project_id(project_id)
    with _connection() as conn:
        return _effective_policy(conn, project_id)[scope]


def get_policy(project_id: int | None = None) -> dict[str, bool]:
    """Return the effective policy for the global or a project scope."""
    project_id = _normalize_project_id(project_id)
    with _connection() as conn:
        return _effective_policy(conn, project_id)


def require(scope: str, project_id: int | None = None) -> None:
    """Raise PermissionDenied unless the scope is explicitly granted."""
    scope = normalize_scope(scope)
    project_id = _normalize_project_id(project_id)
    with _connection() as conn:
        granted = _effective_policy(conn, project_id)[scope]
    if not granted:
        raise PermissionDenied(
            _denied_message(scope, project_id),
            scope=scope,
            project_id=project_id,
        )


def _denied_message(scope: str, project_id: int | None) -> str:
    scope_text = scope.upper()
    where = "globally" if project_id is None else f"for project {project_id}"
    return (
        f"Permission denied: {scope_text} access is not granted {where}. "
        f"An explicit {scope_text} grant is required; permissions are owned by "
        f"the human/backend and cannot be granted by a model."
    )


# --------------------------------------------------------------------------- #
# Model / endpoint classification and enforcement
# --------------------------------------------------------------------------- #

def is_cloud_model(model_name: object) -> bool:
    """Return True when the model name denotes a cloud-hosted model.

    Documented heuristic: the name is split on non-alphanumeric characters and
    must contain the exact token 'cloud' (e.g. gpt-oss:120b-cloud or
    cloud/some-model). This avoids false positives such as 'cloudless'.
    """
    if not isinstance(model_name, str) or not model_name.strip():
        return False
    return "cloud" in _NAME_TOKEN_SPLIT.split(model_name.strip().lower())


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().rstrip(".")
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    if normalized in _LOCAL_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def is_remote_endpoint(base_url: object) -> bool:
    """Return True for a non-loopback model endpoint.

    Empty/None means "unknown" and is not remote by itself; a non-empty value
    that cannot be parsed as a host is treated as remote (fail-closed).
    """
    if not isinstance(base_url, str) or not base_url.strip():
        return False
    candidate = base_url.strip()
    parsed = urlparse(candidate)
    host = parsed.hostname
    if host is None:
        # Tolerate bare "host:port" values without an explicit scheme.
        parsed = urlparse("//" + candidate)
        host = parsed.hostname
    if host is None:
        return True
    return not _is_loopback_host(host)


def assert_model_permitted(
    model_name: str,
    base_url: str | None = None,
    project_id: int | None = None,
) -> None:
    """Fail-closed model route gate used before every LLM construction.

    * Local loopback (non-cloud) models always pass, even with an empty policy.
    * A cloud model requires an explicit CLOUD grant.
    * A remote (non-loopback) endpoint requires an explicit NETWORK grant.
    * Both checks stack for a cloud model reached through a remote endpoint.

    Raises PermissionDenied with the missing scope recorded on the exception;
    there is no bypass flag or environment variable.
    """
    project_id = _normalize_project_id(project_id)
    cloud = is_cloud_model(model_name)
    remote = is_remote_endpoint(base_url)
    if not cloud and not remote:
        return
    with _connection() as conn:
        policy = _effective_policy(conn, project_id)
    missing: list[str] = []
    if cloud and not policy[CLOUD]:
        missing.append(CLOUD)
    if remote and not policy[NETWORK]:
        missing.append(NETWORK)
    if not missing:
        return
    raise PermissionDenied(
        _model_denied_message(model_name, base_url, missing, project_id),
        scope=missing[0],
        project_id=project_id,
    )


def _model_denied_message(
    model_name: str,
    base_url: str | None,
    missing: list[str],
    project_id: int | None,
) -> str:
    reasons: list[str] = []
    if CLOUD in missing:
        reasons.append(
            f"cloud model {model_name!r} requires an explicit CLOUD grant"
        )
    if NETWORK in missing:
        reasons.append(
            f"remote endpoint {base_url!r} requires an explicit NETWORK grant"
        )
    where = "globally" if project_id is None else f"for project {project_id}"
    return (
        f"Model access denied {where}: " + "; ".join(reasons) + ". "
        "Cloud escalation and network access are off by default and explicit "
        "grant required; permissions are owned by the human/backend and cannot "
        "be granted by a model."
    )

# ===========================================================================
# Stage-7 capability taxonomy and durable scoped approvals (NL-BP-168)
# ===========================================================================
#
# Additive layer on top of the legacy scopes above. Nothing in this section
# changes READ/WRITE/EXECUTE/DELETE/NETWORK/CLOUD policy, grant/revoke/require,
# the app_settings persistence or assert_model_permitted(): existing deny and
# escalation gates stay authoritative and independent.
#
# The capability API is the single fail-closed evaluation entry point for future
# research/tool code:
#
#   decision = check_capability(capability, scope, context)
#   if isinstance(decision, Allowed): ...
#   elif isinstance(decision, NeedsApproval): ... durable approval id ...
#   else: ... Denied (reason / policy id) ...
#
# Rules:
# * every capability has an explicit risk class and default decision;
# * high-impact capabilities default denied; medium capabilities require an
#   explicit approval/grant; only the legacy-equivalent local reversible ones
#   (read/write/execute/local model inference) default allowed;
# * one capability never enables another (no cross-enable); project/mission
#   scoped grants never leak to other projects/missions;
# * deny always wins over allow;
# * grants and pending approvals are durable SQLite rows (expiry, revocation,
#   allow-once consumption, inspection) and append events audit rows;
# * store failures fail closed (Denied, never Allowed).

# --- capability identifiers -------------------------------------------------

CAPABILITY_READ = "read"
CAPABILITY_WRITE = "write"
CAPABILITY_EXECUTE = "execute"
CAPABILITY_INSTALL_PRIVATE = "install-private"
CAPABILITY_INSTALL_SYSTEM = "install-system"
CAPABILITY_WEB_SEARCH = "web-search"
CAPABILITY_WEB_FETCH = "web-fetch"
CAPABILITY_BROWSER_INTERACT = "browser-interact"
CAPABILITY_DOWNLOAD = "download"
CAPABILITY_OPEN_EXTERNAL_PROJECT = "open-external-project"
CAPABILITY_MODEL_INFERENCE_LOCAL = "model-inference-local"
CAPABILITY_MODEL_INFERENCE_CLOUD = "model-inference-cloud"
CAPABILITY_SECRET_USE = "secret-use"
CAPABILITY_GIT_COMMIT = "git-commit"
CAPABILITY_GIT_PUSH = "git-push"
CAPABILITY_PUBLISH_RELEASE = "publish-release"
CAPABILITY_DELETE = "delete"
CAPABILITY_NETWORK_WRITE = "network-write"
CAPABILITY_MCP_CALL = "mcp-call"
CAPABILITY_MICROPHONE = "microphone"

CAPABILITIES: tuple[str, ...] = (
    CAPABILITY_READ,
    CAPABILITY_WRITE,
    CAPABILITY_EXECUTE,
    CAPABILITY_INSTALL_PRIVATE,
    CAPABILITY_INSTALL_SYSTEM,
    CAPABILITY_WEB_SEARCH,
    CAPABILITY_WEB_FETCH,
    CAPABILITY_BROWSER_INTERACT,
    CAPABILITY_DOWNLOAD,
    CAPABILITY_OPEN_EXTERNAL_PROJECT,
    CAPABILITY_MODEL_INFERENCE_LOCAL,
    CAPABILITY_MODEL_INFERENCE_CLOUD,
    CAPABILITY_SECRET_USE,
    CAPABILITY_GIT_COMMIT,
    CAPABILITY_GIT_PUSH,
    CAPABILITY_PUBLISH_RELEASE,
    CAPABILITY_DELETE,
    CAPABILITY_NETWORK_WRITE,
    CAPABILITY_MCP_CALL,
    CAPABILITY_MICROPHONE,
)

#: Risk classes; high/critical capabilities are never allowed by default.
RISK_CLASSES: tuple[str, ...] = ("low", "medium", "high", "critical")

#: Default decisions used by check_capability when no grant/approval applies.
DEFAULT_ALLOW = "allowed"
DEFAULT_DENY = "denied"
DEFAULT_APPROVAL = "approval"
DEFAULT_DECISIONS: tuple[str, ...] = (DEFAULT_ALLOW, DEFAULT_DENY, DEFAULT_APPROVAL)

CAPABILITY_TAXONOMY: dict[str, dict] = {
    CAPABILITY_READ: {
        "risk": "low", "default": DEFAULT_ALLOW,
        "description": "Read files/search/status inside the active project.",
    },
    CAPABILITY_WRITE: {
        "risk": "medium", "default": DEFAULT_ALLOW,
        "description": "Reversible project writes (staged candidate pipeline).",
    },
    CAPABILITY_EXECUTE: {
        "risk": "medium", "default": DEFAULT_ALLOW,
        "description": "Execute known-safe project verification commands.",
    },
    CAPABILITY_INSTALL_PRIVATE: {
        "risk": "high", "default": DEFAULT_APPROVAL,
        "description": "Install dependencies/tools into a private project location.",
    },
    CAPABILITY_INSTALL_SYSTEM: {
        "risk": "critical", "default": DEFAULT_DENY,
        "description": "Install or modify system-wide software/services.",
    },
    CAPABILITY_WEB_SEARCH: {
        "risk": "high", "default": DEFAULT_DENY,
        "description": "Send search queries to configured web-search providers.",
    },
    CAPABILITY_WEB_FETCH: {
        "risk": "high", "default": DEFAULT_DENY,
        "description": "Fetch HTTP(S) resources from external hosts.",
    },
    CAPABILITY_BROWSER_INTERACT: {
        "risk": "high", "default": DEFAULT_DENY,
        "description": "Drive a real browser (click/type/forms/screenshots).",
    },
    CAPABILITY_DOWNLOAD: {
        "risk": "high", "default": DEFAULT_DENY,
        "description": "Download files from external origins to local storage.",
    },
    CAPABILITY_OPEN_EXTERNAL_PROJECT: {
        "risk": "medium", "default": DEFAULT_APPROVAL,
        "description": "Open/manage a project rooted outside the current workspace.",
    },
    CAPABILITY_MODEL_INFERENCE_LOCAL: {
        "risk": "medium", "default": DEFAULT_ALLOW,
        "description": "Local model inference through the local runtime.",
    },
    CAPABILITY_MODEL_INFERENCE_CLOUD: {
        "risk": "high", "default": DEFAULT_DENY,
        "description": "Cloud model inference (source data leaves the machine).",
    },
    CAPABILITY_SECRET_USE: {
        "risk": "critical", "default": DEFAULT_DENY,
        "description": "Read or use stored API keys/secrets/credentials.",
    },
    CAPABILITY_GIT_COMMIT: {
        "risk": "medium", "default": DEFAULT_APPROVAL,
        "description": "Create git commits in the active repository.",
    },
    CAPABILITY_GIT_PUSH: {
        "risk": "high", "default": DEFAULT_DENY,
        "description": "Push commits/branches to a remote repository.",
    },
    CAPABILITY_PUBLISH_RELEASE: {
        "risk": "critical", "default": DEFAULT_DENY,
        "description": "Publish/upload releases or packages to external channels.",
    },
    CAPABILITY_DELETE: {
        "risk": "high", "default": DEFAULT_DENY,
        "description": "Delete files, branches or user data.",
    },
    CAPABILITY_NETWORK_WRITE: {
        "risk": "high", "default": DEFAULT_DENY,
        "description": "Write to external services (POST/PUT/PATCH/DELETE over network).",
    },
    CAPABILITY_MCP_CALL: {
        "risk": "high", "default": DEFAULT_APPROVAL,
        "description": "Call a configured MCP server/tool with arbitrary effects.",
    },
    CAPABILITY_MICROPHONE: {
        "risk": "high", "default": DEFAULT_APPROVAL,
        "description": "Capture microphone audio (dictation/voice input).",
    },
}

CAPABILITY_RISK: dict[str, str] = {
    capability: str(meta["risk"]) for capability, meta in CAPABILITY_TAXONOMY.items()
}
CAPABILITY_DEFAULTS: dict[str, str] = {
    capability: str(meta["default"]) for capability, meta in CAPABILITY_TAXONOMY.items()
}

# --- scope kinds and decision semantics ------------------------------------

SCOPE_TOOL = "tool"
SCOPE_PROCESS = "process"
SCOPE_PATH = "path"
SCOPE_PROJECT = "project"
SCOPE_EXTERNAL_RESOURCE = "external-resource"
SCOPE_HOST_DOMAIN = "host-domain"
SCOPE_REPOSITORY = "repository"
SCOPE_TASK = "task"
SCOPE_MISSION = "mission"
SCOPE_WORKSPACE = "workspace"
SCOPE_SESSION = "session"
SCOPE_SAVED_POLICY = "saved-policy"

SCOPE_KINDS: tuple[str, ...] = (
    SCOPE_TOOL,
    SCOPE_PROCESS,
    SCOPE_PATH,
    SCOPE_PROJECT,
    SCOPE_EXTERNAL_RESOURCE,
    SCOPE_HOST_DOMAIN,
    SCOPE_REPOSITORY,
    SCOPE_TASK,
    SCOPE_MISSION,
    SCOPE_WORKSPACE,
    SCOPE_SESSION,
    SCOPE_SAVED_POLICY,
)

DECISION_ALLOW_ONCE = "allow-once"
DECISION_ALLOW_MISSION = "mission"
DECISION_ALLOW_PROJECT = "project"
DECISION_ALWAYS = "always"
DECISION_DENY = "deny"
DECISION_REVOKE = "revoke"

DECISIONS: tuple[str, ...] = (
    DECISION_ALLOW_ONCE,
    DECISION_ALLOW_MISSION,
    DECISION_ALLOW_PROJECT,
    DECISION_ALWAYS,
    DECISION_DENY,
    DECISION_REVOKE,
)
GRANT_DECISIONS: tuple[str, ...] = DECISIONS[:-1]

OUTCOME_ALLOWED = "allowed"
OUTCOME_DENIED = "denied"
OUTCOME_NEEDS_APPROVAL = "needs_approval"

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_DENIED = "denied"
APPROVAL_EXPIRED = "expired"

_CONTEXT_KEYS: dict[str, tuple[str, ...]] = {
    SCOPE_TOOL: ("tool", "tool_id"),
    SCOPE_PROCESS: ("process", "process_id", "pid"),
    SCOPE_PATH: ("path", "target_path", "file_path"),
    SCOPE_PROJECT: ("project_id",),
    SCOPE_EXTERNAL_RESOURCE: ("external_resource", "resource", "url"),
    SCOPE_HOST_DOMAIN: ("host", "hostname", "domain"),
    SCOPE_REPOSITORY: ("repository", "repo"),
    SCOPE_TASK: ("task_id",),
    SCOPE_MISSION: ("mission_id",),
    SCOPE_WORKSPACE: ("workspace", "workspace_root"),
    SCOPE_SESSION: ("session_id",),
    SCOPE_SAVED_POLICY: ("saved_policy", "policy"),
}
_INT_KEYS = ("project_id", "mission_id", "task_id", "process_id", "pid")
_NUMERIC_SCOPE_KINDS = (SCOPE_PROJECT, SCOPE_TASK, SCOPE_MISSION, SCOPE_PROCESS)


# --- decision objects -------------------------------------------------------

@dataclass(frozen=True)
class CapabilityDecision:
    """One fail-closed capability evaluation result."""

    capability: str
    reason: str
    policy_id: int | None = None
    approval_id: int | None = None
    scope_kind: str | None = None
    scope_value: str | None = None
    project_id: int | None = None
    outcome: ClassVar[str] = ""
    allowed: ClassVar[bool] = False
    needs_approval: ClassVar[bool] = False

    def to_dict(self) -> dict:
        return {
            "capability": self.capability,
            "outcome": self.outcome,
            "allowed": bool(self.allowed),
            "needs_approval": bool(self.needs_approval),
            "reason": self.reason,
            "policy_id": self.policy_id,
            "approval_id": self.approval_id,
            "scope_kind": self.scope_kind,
            "scope_value": self.scope_value,
            "project_id": self.project_id,
            "risk": CAPABILITY_RISK.get(self.capability),
        }


class Allowed(CapabilityDecision):
    """The capability is explicitly allowed by policy/approval."""

    outcome: ClassVar[str] = OUTCOME_ALLOWED
    allowed: ClassVar[bool] = True


class Denied(CapabilityDecision):
    """The capability is denied by default, revocation or an explicit deny."""

    outcome: ClassVar[str] = OUTCOME_DENIED


class NeedsApproval(CapabilityDecision):
    """The capability requires a durable human/backend approval decision."""

    outcome: ClassVar[str] = OUTCOME_NEEDS_APPROVAL
    needs_approval: ClassVar[bool] = True


@dataclass(frozen=True)
class CapabilityScope:
    """Scope descriptor for one capability check/grant.

    kind: one of SCOPE_KINDS. value: tool/process/path/host/repository/task/
    mission/workspace/session/policy identifier (or None for a wildcard within
    the scope kind). project_id: optional project isolation column.
    """

    kind: str
    value: str | None = None
    project_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _validate_scope_kind(self.kind))
        if self.value is not None:
            object.__setattr__(self, "value", str(self.value))
        object.__setattr__(self, "project_id", _normalize_project_id(self.project_id))

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "project_id": self.project_id}


# --- validation helpers -----------------------------------------------------

def normalize_capability(capability: object) -> str:
    """Validate/normalize one capability id; unknown ids raise ValueError."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError(
            "Unknown capability: " + repr(capability) + "; expected one of "
            + ", ".join(CAPABILITIES)
        )
    normalized = capability.strip().lower()
    if normalized not in CAPABILITIES:
        raise ValueError(
            "Unknown capability: " + repr(capability) + "; expected one of "
            + ", ".join(CAPABILITIES)
        )
    return normalized


def _validate_scope_kind(kind: object) -> str:
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError(
            "Unknown capability scope kind: " + repr(kind) + "; expected one of "
            + ", ".join(SCOPE_KINDS)
        )
    normalized = kind.strip().lower()
    if normalized not in SCOPE_KINDS:
        raise ValueError(
            "Unknown capability scope kind: " + repr(kind) + "; expected one of "
            + ", ".join(SCOPE_KINDS)
        )
    return normalized


def normalize_decision(decision: object) -> str:
    """Validate one decision keyword (allow-once/mission/project/always/deny/revoke)."""
    if not isinstance(decision, str) or not decision.strip():
        raise ValueError(
            "Unknown capability decision: " + repr(decision) + "; expected one of "
            + ", ".join(DECISIONS)
        )
    normalized = decision.strip().lower().replace("_", "-")
    if normalized not in DECISIONS:
        raise ValueError(
            "Unknown capability decision: " + repr(decision) + "; expected one of "
            + ", ".join(DECISIONS)
        )
    return normalized


def normalize_capability_scope(
    scope: object = None,
    context: dict | None = None,
) -> CapabilityScope:
    """Normalize a CapabilityScope/mapping; None becomes a project scope."""
    ctx = _normalize_context(context)
    if scope is None:
        project_value = ctx.get("project_id")
        return CapabilityScope(
            SCOPE_PROJECT,
            str(project_value) if project_value is not None else None,
            project_value,
        )
    if isinstance(scope, CapabilityScope):
        return scope
    if isinstance(scope, dict):
        return CapabilityScope(
            scope.get("kind"),
            scope.get("value"),
            scope.get("project_id"),
        )
    raise ValueError(
        "scope must be a CapabilityScope or a mapping with a 'kind' key: "
        + repr(scope)
    )


def _normalize_context(context: object) -> dict:
    if not isinstance(context, dict):
        return {}
    normalized: dict = {}
    for key, value in context.items():
        if value is None:
            continue
        if key in _INT_KEYS:
            try:
                normalized[key] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            normalized[key] = value
    return normalized


def _context_value(kind: str, context: dict):
    for key in _CONTEXT_KEYS.get(kind, ()):
        if key in context and context[key] is not None:
            return context[key]
    return None


def _normalize_path(value: object) -> str:
    return str(value or "").replace(chr(92), "/").rstrip("/").casefold()


def _normalize_host(value: object) -> str:
    return str(value or "").strip().lower().rstrip(".")


def _value_matches(kind: str, grant_value: object, candidate: object) -> bool:
    grant_text = str(grant_value)
    candidate_text = str(candidate)
    if kind == SCOPE_PATH:
        grant_path = _normalize_path(grant_text)
        candidate_path = _normalize_path(candidate_text)
        if not grant_path or not candidate_path:
            return False
        return candidate_path == grant_path or candidate_path.startswith(grant_path + "/")
    if kind == SCOPE_HOST_DOMAIN:
        grant_host = _normalize_host(grant_text)
        candidate_host = _normalize_host(candidate_text)
        if not grant_host or not candidate_host:
            return False
        return candidate_host == grant_host or candidate_host.endswith("." + grant_host)
    if kind in _NUMERIC_SCOPE_KINDS:
        return candidate_text == grant_text
    return candidate_text == grant_text


def _row_scope_matches(row: dict, scope: CapabilityScope, context: dict) -> bool:
    """True when a persisted grant/approval scope applies to this check."""
    row_kind = str(row.get("scope_kind") or "")
    row_value = row.get("scope_value")
    row_project = row.get("project_id")
    context_project = context.get("project_id")
    scope_project = scope.project_id
    effective_project = context_project if context_project is not None else scope_project
    if effective_project is None and scope.kind == SCOPE_PROJECT and scope.value is not None:
        try:
            effective_project = int(scope.value)
        except (TypeError, ValueError):
            effective_project = None
    if row_project is not None:
        if effective_project is None or int(effective_project) != int(row_project):
            return False
    if row_kind == scope.kind:
        candidate = scope.value if scope.value is not None else _context_value(row_kind, context)
        if row_value is None:
            return True
        if candidate is None:
            return False
        return _value_matches(row_kind, row_value, candidate)
    # A grant created for another scope kind only matches when the context
    # supplies that scope's own identity (e.g. a host-domain policy checked from
    # a request scope of external-resource still matches by context host).
    candidate = _context_value(row_kind, context)
    if row_value is None:
        return candidate is not None
    if candidate is None:
        return False
    return _value_matches(row_kind, row_value, candidate)


def _scope_dict(scope: CapabilityScope) -> dict:
    return {"kind": scope.kind, "value": scope.value, "project_id": scope.project_id}


# --- persistence bridge ----------------------------------------------------

def _capability_store():
    from nl_coding_agent.persistence import permissions_store

    return permissions_store


def _capability_audit(conn, *, level: str, message: str, kind: str, payload: dict) -> None:
    _capability_store().audit(
        conn, level=level, message=message, kind=kind, payload=payload,
    )


def _expiry_from(ttl_s: int | float | None, expires_at: object = None) -> str | None:
    if ttl_s is not None and expires_at is not None:
        raise ValueError("pass either ttl_s or expires_at, not both")
    if ttl_s is not None:
        try:
            seconds = float(ttl_s)
        except (TypeError, ValueError):
            raise ValueError("ttl_s must be a positive number of seconds") from None
        if seconds <= 0:
            raise ValueError("ttl_s must be a positive number of seconds")
        return (datetime.now() + timedelta(seconds=seconds)).isoformat(timespec="seconds")
    if expires_at is None:
        return None
    if isinstance(expires_at, datetime):
        return expires_at.isoformat(timespec="seconds")
    text = str(expires_at).strip()
    if not text:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("expires_at must be an ISO-8601 datetime") from None
    return text


def _decision_project_id(
    scope: CapabilityScope,
    project_id: int | None,
) -> int | None:
    normalized = _normalize_project_id(project_id)
    if normalized is not None:
        return normalized
    if scope.project_id is not None:
        return int(scope.project_id)
    if scope.kind == SCOPE_PROJECT and scope.value is not None:
        return _normalize_project_id(scope.value)
    return None


# --- public inspection API --------------------------------------------------

def capability_catalog() -> dict[str, dict]:
    """Return a copy of the capability taxonomy (risk + default + description)."""
    return {
        capability: dict(meta)
        for capability, meta in CAPABILITY_TAXONOMY.items()
    }


def list_capability_grants(
    capability: str | None = None,
    *,
    limit: int = 200,
) -> list[dict]:
    """Inspect durable grants (newest first), including expired/revoked rows."""
    if capability is not None:
        capability = normalize_capability(capability)
    store = _capability_store()
    conn = store.connect()
    try:
        return store.list_grants(conn, capability=capability, limit=limit)
    finally:
        conn.close()


def get_capability_grant(grant_id: int) -> dict | None:
    store = _capability_store()
    conn = store.connect()
    try:
        return store.get_grant(conn, int(grant_id))
    finally:
        conn.close()


def list_capability_approvals(
    capability: str | None = None,
    *,
    limit: int = 200,
) -> list[dict]:
    """Inspect durable approval requests (newest first)."""
    if capability is not None:
        capability = normalize_capability(capability)
    store = _capability_store()
    conn = store.connect()
    try:
        return store.list_approvals(conn, capability=capability, limit=limit)
    finally:
        conn.close()


def get_capability_approval(approval_id: int) -> dict | None:
    store = _capability_store()
    conn = store.connect()
    try:
        return store.get_approval(conn, int(approval_id))
    finally:
        conn.close()


def capability_audit_events(*, limit: int = 100) -> list[dict]:
    """Read the events audit rows written by the capability API."""
    store = _capability_store()
    conn = store.connect()
    try:
        return store.list_events(conn, limit=limit)
    finally:
        conn.close()


# --- durable approvals ------------------------------------------------------

def request_capability(
    capability: str,
    scope: object = None,
    context: dict | None = None,
    *,
    reason: str = "",
    project_id: int | None = None,
    ttl_s: int | float | None = None,
    expires_at: object = None,
    source: str = DEFAULT_GRANT_SOURCE,
) -> dict:
    """Persist one durable WAIT_APPROVAL request; never executes the capability."""
    capability = normalize_capability(capability)
    cap_scope = normalize_capability_scope(scope, context)
    ctx = _normalize_context(context)
    effective_project = _decision_project_id(cap_scope, project_id)
    expiry = _expiry_from(ttl_s, expires_at)
    store = _capability_store()
    conn = store.connect()
    try:
        approval_id = store.insert_approval(
            conn,
            capability=capability,
            scope_kind=cap_scope.kind,
            scope_value=cap_scope.value,
            project_id=effective_project,
            context=ctx,
            reason=str(reason or ""),
            expires_at=expiry,
            source=_normalize_source(source),
        )
        _capability_audit(
            conn,
            level="info",
            message="Capability approval requested: " + capability,
            kind="capability_request",
            payload={
                "capability": capability,
                "approval_id": approval_id,
                "scope_kind": cap_scope.kind,
                "scope_value": cap_scope.value,
                "project_id": effective_project,
                "expires_at": expiry,
            },
        )
        return {
            "ok": True,
            "approval_id": approval_id,
            "status": APPROVAL_PENDING,
            "capability": capability,
            "scope": _scope_dict(cap_scope),
            "project_id": effective_project,
            "expires_at": expiry,
            "starts_or_runs": False,
        }
    finally:
        conn.close()


def decide_capability_approval(
    approval_id: int,
    approved: bool,
    *,
    decision: str = DECISION_ALLOW_ONCE,
    decided_by: str = DEFAULT_GRANT_SOURCE,
    ttl_s: int | float | None = None,
    source: str = DEFAULT_GRANT_SOURCE,
) -> dict:
    """Record a durable approval decision and, when approved, its scoped grant."""
    approval_id = int(approval_id)
    store = _capability_store()
    conn = store.connect()
    try:
        approval = store.get_approval(conn, approval_id)
        if approval is None:
            return {"ok": False, "error": "Approval not found: " + str(approval_id)}
        if str(approval.get("status")) != APPROVAL_PENDING:
            return {
                "ok": False,
                "error": "Approval is not pending",
                "status": approval.get("status"),
                "approval_id": approval_id,
            }
        if not approved:
            changed = store.decide_approval(
                conn,
                approval_id,
                status=APPROVAL_DENIED,
                decided_by=str(decided_by or DEFAULT_GRANT_SOURCE),
                decision=None,
                grant_id=None,
            )
            _capability_audit(
                conn,
                level="warning",
                message="Capability approval denied: " + str(approval["capability"]),
                kind="capability_decision",
                payload={
                    "capability": approval["capability"],
                    "approval_id": approval_id,
                    "status": APPROVAL_DENIED,
                    "decided_by": str(decided_by or DEFAULT_GRANT_SOURCE),
                },
            )
            return {
                "ok": bool(changed),
                "approval_id": approval_id,
                "status": APPROVAL_DENIED,
                "grant_id": None,
            }
        decision = normalize_decision(decision)
        if decision not in (DECISION_ALLOW_ONCE, DECISION_ALLOW_MISSION,
                            DECISION_ALLOW_PROJECT, DECISION_ALWAYS):
            raise ValueError(
                "An approved capability requires an allow decision "
                "(allow-once/mission/project/always)"
            )
        scope = CapabilityScope(
            str(approval["scope_kind"]),
            approval.get("scope_value"),
            approval.get("project_id"),
        )
        expires_at = _expiry_from(ttl_s) if ttl_s is not None else approval.get("expires_at")
        grant_id = store.insert_grant(
            conn,
            capability=str(approval["capability"]),
            scope_kind=scope.kind,
            scope_value=scope.value,
            project_id=approval.get("project_id"),
            decision=decision,
            source=_normalize_source(source),
            context=approval.get("context") or {},
            expires_at=expires_at,
        )
        changed = store.decide_approval(
            conn,
            approval_id,
            status=APPROVAL_APPROVED,
            decided_by=str(decided_by or DEFAULT_GRANT_SOURCE),
            decision=decision,
            grant_id=grant_id,
        )
        _capability_audit(
            conn,
            level="info",
            message="Capability approval granted: " + str(approval["capability"]),
            kind="capability_decision",
            payload={
                "capability": approval["capability"],
                "approval_id": approval_id,
                "grant_id": grant_id,
                "status": APPROVAL_APPROVED,
                "decision": decision,
                "scope_kind": scope.kind,
                "scope_value": scope.value,
                "decided_by": str(decided_by or DEFAULT_GRANT_SOURCE),
            },
        )
        return {
            "ok": bool(changed),
            "approval_id": approval_id,
            "status": APPROVAL_APPROVED,
            "grant_id": grant_id,
            "decision": decision,
            "expires_at": expires_at,
        }
    finally:
        conn.close()


def expire_capability_approvals() -> int:
    """Persist expiry for overdue pending approvals; returns the number changed."""
    store = _capability_store()
    conn = store.connect()
    try:
        return store.expire_approvals(conn)
    finally:
        conn.close()


# --- grants and revocation --------------------------------------------------

def grant_capability(
    capability: str,
    scope: object = None,
    *,
    decision: str = DECISION_ALLOW_ONCE,
    project_id: int | None = None,
    expires_at: object = None,
    ttl_s: int | float | None = None,
    source: str = DEFAULT_GRANT_SOURCE,
    context: dict | None = None,
) -> dict:
    """Persist one scoped capability decision (human/backend only).

    decision='revoke' is accepted as a convenience and revokes the matching
    active grants instead of inserting a new allow/deny row.
    """
    capability = normalize_capability(capability)
    decision = normalize_decision(decision)
    cap_scope = normalize_capability_scope(scope, context)
    ctx = _normalize_context(context)
    effective_project = _decision_project_id(cap_scope, project_id)
    if decision == DECISION_REVOKE:
        revoked = _revoke_capability_rows(
            capability=capability,
            scope=cap_scope if scope is not None else None,
            project_id=effective_project,
            source=source,
        )
        return {
            "ok": True,
            "capability": capability,
            "revoked": revoked,
            "decision": DECISION_REVOKE,
            "starts_or_runs": False,
        }
    if (decision in (DECISION_ALLOW_PROJECT, DECISION_ALLOW_MISSION)
            and not ctx and scope is None and project_id is None):
        raise ValueError(
            "project/mission decisions require an explicit scope or id"
        )
    if decision == DECISION_ALLOW_PROJECT and effective_project is None:
        raise ValueError("project decision requires project_id")
    if decision == DECISION_ALLOW_MISSION:
        mission_value = (
            cap_scope.value if cap_scope.kind == SCOPE_MISSION else ctx.get("mission_id")
        )
        if mission_value is None:
            raise ValueError("mission decision requires a mission scope/value")
    # Project/mission decisions are persisted on their own scope kind so they can
    # never widen into the generic default (project wildcard) scope.
    if decision == DECISION_ALLOW_PROJECT:
        cap_scope = CapabilityScope(
            SCOPE_PROJECT, str(effective_project), effective_project)
    elif decision == DECISION_ALLOW_MISSION:
        try:
            mission_int = int(mission_value)
        except (TypeError, ValueError):
            raise ValueError("mission decision requires a numeric mission id") from None
        cap_scope = CapabilityScope(
            SCOPE_MISSION, str(mission_int), effective_project)
    expiry = _expiry_from(ttl_s, expires_at)
    store = _capability_store()
    conn = store.connect()
    try:
        grant_id = store.insert_grant(
            conn,
            capability=capability,
            scope_kind=cap_scope.kind,
            scope_value=cap_scope.value,
            project_id=effective_project,
            decision=decision,
            source=_normalize_source(source),
            context=ctx,
            expires_at=expiry,
        )
        _capability_audit(
            conn,
            level="warning" if decision == DECISION_DENY else "info",
            message="Capability " + decision + ": " + capability,
            kind="capability_grant",
            payload={
                "capability": capability,
                "grant_id": grant_id,
                "decision": decision,
                "scope_kind": cap_scope.kind,
                "scope_value": cap_scope.value,
                "project_id": effective_project,
                "expires_at": expiry,
                "source": _normalize_source(source),
            },
        )
        return {
            "ok": True,
            "grant_id": grant_id,
            "capability": capability,
            "decision": decision,
            "scope": _scope_dict(cap_scope),
            "project_id": effective_project,
            "expires_at": expiry,
            "starts_or_runs": False,
        }
    finally:
        conn.close()


def _revoke_capability_rows(
    *,
    capability: str,
    scope: CapabilityScope | None = None,
    project_id: int | None = None,
    source: str = DEFAULT_GRANT_SOURCE,
) -> int:
    store = _capability_store()
    conn = store.connect()
    try:
        rows = store.revoke_grants(
            conn,
            capability=capability,
            scope_kind=scope.kind if scope is not None else None,
            scope_value=scope.value if scope is not None else None,
            project_id=project_id,
        )
        for row in rows:
            _capability_audit(
                conn,
                level="warning",
                message="Capability revoked: " + capability + " (grant #" + str(row["id"]) + ")",
                kind="capability_revoke",
                payload={
                    "capability": capability,
                    "grant_id": row["id"],
                    "scope_kind": row.get("scope_kind"),
                    "scope_value": row.get("scope_value"),
                    "project_id": row.get("project_id"),
                    "source": _normalize_source(source),
                },
            )
        return len(rows)
    finally:
        conn.close()


def revoke_capability(
    capability: str,
    scope: object = None,
    *,
    project_id: int | None = None,
    source: str = DEFAULT_GRANT_SOURCE,
) -> dict:
    """Revoke matching active grants (durable, audited). Returns the count."""
    capability = normalize_capability(capability)
    cap_scope = normalize_capability_scope(scope) if scope is not None else None
    effective_project = _decision_project_id(cap_scope, project_id) if cap_scope else _normalize_project_id(project_id)
    revoked = _revoke_capability_rows(
        capability=capability,
        scope=cap_scope,
        project_id=effective_project,
        source=source,
    )
    return {"ok": True, "capability": capability, "revoked": revoked}


# --- fail-closed evaluation -------------------------------------------------

def _grant_specificity(row: dict, scope: CapabilityScope) -> int:
    if str(row.get("decision")) == DECISION_ALLOW_ONCE:
        return 6
    if str(row.get("scope_kind")) == scope.kind and row.get("scope_value") is not None:
        return 5
    if str(row.get("scope_kind")) == scope.kind:
        return 4
    if str(row.get("decision")) in (DECISION_ALLOW_PROJECT, DECISION_ALLOW_MISSION):
        return 3
    if row.get("scope_value") is not None:
        return 2
    return 1


def _match_latest(rows: list[dict], scope: CapabilityScope, context: dict) -> dict | None:
    matching = [row for row in rows if _row_scope_matches(row, scope, context)]
    if not matching:
        return None
    return sorted(matching, key=lambda row: int(row.get("id") or 0))[-1]


def check_capability(
    capability: str,
    scope: object = None,
    context: dict | None = None,
) -> CapabilityDecision:
    """Single fail-closed capability evaluation used by future tool/research code.

    Order of precedence: explicit deny > scoped allow/allow-once (durable) >
    durable pending/denied approvals > capability default. Any store error is
    reported as Denied (never Allowed); unknown capability/scope values raise
    ValueError so programming errors fail loudly before execution.
    """
    capability = normalize_capability(capability)
    cap_scope = normalize_capability_scope(scope, context)
    ctx = _normalize_context(context)
    scope_kwargs = {
        "scope_kind": cap_scope.kind,
        "scope_value": cap_scope.value,
        "project_id": cap_scope.project_id,
    }
    store = _capability_store()
    try:
        conn = store.connect()
    except Exception as exc:  # fail closed: the store is unavailable
        return Denied(
            capability,
            "Fail-closed: capability permission store unavailable (" + str(exc) + ")",
            scope_kind=cap_scope.kind,
            scope_value=cap_scope.value,
            project_id=cap_scope.project_id,
        )
    try:
        grants = store.fetch_grants(conn, capability, active_only=True)
        matching = [row for row in grants if _row_scope_matches(row, cap_scope, ctx)]
        denies = [row for row in matching if str(row.get("decision")) == DECISION_DENY]
        if denies:
            policy = sorted(denies, key=lambda row: int(row.get("id") or 0))[-1]
            return Denied(
                capability,
                "Denied by explicit policy grant #" + str(policy.get("id")) + ".",
                policy_id=int(policy["id"]),
                scope_kind=cap_scope.kind,
                scope_value=cap_scope.value,
                project_id=cap_scope.project_id,
            )
        allows = [row for row in matching if str(row.get("decision")) != DECISION_DENY]
        allows.sort(key=lambda row: (
            -_grant_specificity(row, cap_scope),
            int(row.get("id") or 0),
        ))
        for row in allows:
            decision = str(row.get("decision"))
            if decision == DECISION_ALLOW_ONCE:
                if not store.consume_grant(conn, int(row["id"])):
                    continue
                _capability_audit(
                    conn,
                    level="info",
                    message="Capability allow-once consumed: " + capability,
                    kind="capability_consume",
                    payload={
                        "capability": capability,
                        "grant_id": int(row["id"]),
                        "scope_kind": row.get("scope_kind"),
                        "scope_value": row.get("scope_value"),
                    },
                )
                return Allowed(
                    capability,
                    "Allowed once by policy grant #" + str(row.get("id")) + ".",
                    policy_id=int(row["id"]),
                    **scope_kwargs,
                )
            return Allowed(
                capability,
                "Allowed by " + decision + " policy grant #" + str(row.get("id")) + ".",
                policy_id=int(row["id"]),
                **scope_kwargs,
            )
        approvals = store.fetch_approvals(
            conn, capability, statuses=(APPROVAL_PENDING, APPROVAL_DENIED),
        )
        pending = [
            row for row in approvals
            if str(row.get("status")) == APPROVAL_PENDING
            and _row_scope_matches(row, cap_scope, ctx)
        ]
        if pending:
            latest = sorted(pending, key=lambda row: int(row.get("id") or 0))[-1]
            return NeedsApproval(
                capability,
                "Durable approval #" + str(latest.get("id"))
                + " is pending for this capability/scope.",
                approval_id=int(latest["id"]),
                **scope_kwargs,
            )
        denied_approvals = [
            row for row in approvals
            if str(row.get("status")) == APPROVAL_DENIED
            and _row_scope_matches(row, cap_scope, ctx)
        ]
        if denied_approvals:
            latest = sorted(denied_approvals, key=lambda row: int(row.get("id") or 0))[-1]
            return Denied(
                capability,
                "Durable approval #" + str(latest.get("id")) + " was denied.",
                approval_id=int(latest["id"]),
                **scope_kwargs,
            )
        default = CAPABILITY_DEFAULTS[capability]
        risk = CAPABILITY_RISK[capability]
        if default == DEFAULT_ALLOW:
            return Allowed(
                capability,
                "Default allow for " + capability + " (" + risk + " risk).",
                **scope_kwargs,
            )
        if default == DEFAULT_APPROVAL:
            return NeedsApproval(
                capability,
                "Explicit approval required for " + capability
                + " (" + risk + " risk); request a durable approval.",
                **scope_kwargs,
            )
        return Denied(
            capability,
            "Default deny for " + capability + " (" + risk
            + " risk); request an explicit approval or grant.",
            **scope_kwargs,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed, never allow on error
        return Denied(
            capability,
            "Fail-closed: capability evaluation error (" + str(exc) + ")",
            scope_kind=cap_scope.kind,
            scope_value=cap_scope.value,
            project_id=cap_scope.project_id,
        )
    finally:
        conn.close()


def require_capability(
    capability: str,
    scope: object = None,
    context: dict | None = None,
) -> CapabilityDecision:
    """Raise PermissionDenied unless the capability is Allowed (fail closed)."""
    decision = check_capability(capability, scope, context)
    if not isinstance(decision, Allowed):
        raise PermissionDenied(
            decision.reason,
            scope=decision.capability,
            project_id=decision.project_id,
        )
    return decision


"""One persisted global access mode for Chat, missions, agents and tools.

The four GUI modes are the sole authorization source. Legacy scoped records
remain readable for audit, but cannot grant, deny or request authorization.
Local inference and project work are the default; network/cloud require an
explicit global Auto Review or Full Access selection. Integrity, isolation,
verification and recovery checks remain independent technical gates.
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

# --------------------------------------------------------------------------- #
# Global access mode: the single authorization policy for the whole product.
# --------------------------------------------------------------------------- #
#
# The four GUI modes are the only permission source. per-project policies and
# capability grants are legacy compatibility data: they are ignored as soon as
# an access mode is stored (the GUI/backend migrates the old access.profile rows
# once, on first read).
ACCESS_READ_ONLY = "read-only"
ACCESS_WORKSPACE_WRITE = "workspace-write"
ACCESS_AUTO_REVIEW = "auto-review"
ACCESS_FULL_ACCESS = "full-access"
ACCESS_MODES: tuple[str, ...] = (
    ACCESS_READ_ONLY,
    ACCESS_WORKSPACE_WRITE,
    ACCESS_AUTO_REVIEW,
    ACCESS_FULL_ACCESS,
)
DEFAULT_ACCESS_MODE = ACCESS_WORKSPACE_WRITE

ACCESS_MODE_KEY = "access.mode"
LEGACY_ACCESS_PROFILE_PREFIX = "access.profile."

ACCESS_MODE_SCOPES: dict[str, dict[str, bool]] = {
    ACCESS_READ_ONLY: {
        READ: True, WRITE: False, EXECUTE: False,
        DELETE: False, NETWORK: False, CLOUD: False,
    },
    ACCESS_WORKSPACE_WRITE: {
        READ: True, WRITE: True, EXECUTE: True,
        DELETE: False, NETWORK: False, CLOUD: False,
    },
    ACCESS_AUTO_REVIEW: {
        READ: True, WRITE: True, EXECUTE: True,
        DELETE: False, NETWORK: True, CLOUD: True,
    },
    ACCESS_FULL_ACCESS: {
        READ: True, WRITE: True, EXECUTE: True,
        DELETE: True, NETWORK: True, CLOUD: True,
    },
}

ACCESS_MODE_LABELS: dict[str, str] = {
    ACCESS_READ_ONLY: "Read Only",
    ACCESS_WORKSPACE_WRITE: "Workspace Write",
    ACCESS_AUTO_REVIEW: "Auto Review",
    ACCESS_FULL_ACCESS: "Full Access",
}

ACCESS_MODE_DESCRIPTIONS: dict[str, str] = {
    ACCESS_READ_ONLY: (
        "Analysis only: read project files and run local inference. No file "
        "changes, commands, missions, network or cloud access."
    ),
    ACCESS_WORKSPACE_WRITE: (
        "Project work: read, write/execute inside the project and create, "
        "modify, stop, resume or delete missions. No network or cloud access."
    ),
    ACCESS_AUTO_REVIEW: (
        "Workspace work plus explicit network/cloud research and downloads. "
        "Independent code review, integrity and regression gates still apply."
    ),
    ACCESS_FULL_ACCESS: (
        "Every operation available to the current OS user, including delete, "
        "system install, secrets, git push and release publishing."
    ),
}

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


def normalize_access_mode(mode: object) -> str:
    """Validate one of the four global GUI access modes."""
    if not isinstance(mode, str) or not mode.strip():
        raise ValueError(
            "Unknown access mode: " + repr(mode) + "; expected one of "
            + ", ".join(ACCESS_MODES)
        )
    normalized = mode.strip().lower()
    if normalized not in ACCESS_MODES:
        raise ValueError(
            "Unknown access mode: " + repr(mode) + "; expected one of "
            + ", ".join(ACCESS_MODES)
        )
    return normalized


def _parse_access_mode(raw: str | None) -> str | None:
    if not raw:
        return None
    candidate = raw.strip()
    if candidate.startswith('"'):
        try:
            candidate = str(json.loads(candidate))
        except (TypeError, ValueError):
            return None
    if candidate in ACCESS_MODES:
        return candidate
    return None


def _legacy_access_mode(conn) -> str | None:
    """Preserve any legacy Read Only choice during first initialization.

    A former project-specific opt-in cannot broaden the new global policy.
    Once the global key exists these rows are never consulted again.
    """
    try:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM app_settings "
            "WHERE key LIKE ? ORDER BY updated_at DESC, key DESC",
            (LEGACY_ACCESS_PROFILE_PREFIX + "%",),
        ).fetchall()
    except Exception:
        return None
    for row in rows:
        try:
            data = json.loads(row["value"] or "")
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        profile = str(data.get("profile") or "").strip().lower()
        if profile == ACCESS_READ_ONLY:
            return ACCESS_READ_ONLY
    return None


def _resolve_access_mode(conn, *, persist_legacy: bool = False) -> str | None:
    """Return the explicit global mode, migrating a legacy profile if needed."""
    raw = _read_raw(conn, ACCESS_MODE_KEY)
    if raw is not None:
        # Corrupt global state must never reactivate legacy project grants.
        return _parse_access_mode(raw) or ACCESS_READ_ONLY
    legacy = _legacy_access_mode(conn)
    # A former project opt-in cannot authorize cloud/system access for all
    # projects. Preserve read-only; otherwise start at the local default.
    legacy = ACCESS_READ_ONLY if legacy == ACCESS_READ_ONLY else DEFAULT_ACCESS_MODE
    if persist_legacy:
        conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (ACCESS_MODE_KEY, legacy, _now()),
        )
    return legacy


def _effective_policy(conn, project_id: int | None = None) -> dict[str, bool]:
    """Return the single global access-mode policy.

    Project, mission, agent and capability grant rows are audit-only data.
    No caller needs to initialize the GUI before the global policy applies.
    """
    return dict(ACCESS_MODE_SCOPES[_resolve_access_mode(conn)])


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


def _audit_access_mode(conn, mode: str, source: str) -> None:
    payload = json.dumps(
        {
            "action": "set_access_mode",
            "mode": mode,
            "source": source,
            "policy_key": ACCESS_MODE_KEY,
        },
        sort_keys=True,
    )
    conn.execute(
        "INSERT INTO events (source, level, message, payload) VALUES (?,?,?,?)",
        (
            AUDIT_SOURCE,
            "info",
            "Access mode set: " + mode + " [source: " + source + "]",
            payload,
        ),
    )


# --------------------------------------------------------------------------- #
# Public permission API (human/backend owned)
# --------------------------------------------------------------------------- #

def get_access_mode(*, persist: bool = False) -> str:
    """Return the global access mode.

    ``persist=True`` is used by the GUI/access-profile endpoint: it migrates the
    local default (preserving a legacy Read Only choice) without broadening a
    former project opt-in to every project. Checks use the same policy before
    initialization. Malformed global state fails closed to Read Only.
    """
    with _connection() as conn, conn:
        if persist:
            conn.execute("BEGIN IMMEDIATE")
        mode = _resolve_access_mode(conn, persist_legacy=persist)
        if mode is not None:
            return mode
        mode = DEFAULT_ACCESS_MODE
        if persist:
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (ACCESS_MODE_KEY, mode, _now()),
            )
        return mode


def set_access_mode(mode: str, source: str = DEFAULT_GRANT_SOURCE) -> str:
    """Persist one of the four global GUI access modes and audit the change."""
    mode = normalize_access_mode(mode)
    source = _normalize_source(source)
    with _connection() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (ACCESS_MODE_KEY, mode, _now()),
        )
        _audit_access_mode(conn, mode, source)
    return mode


def access_mode_descriptors() -> list[dict]:
    """Return the four GUI modes with their scope policy and description."""
    return [
        {
            "id": mode,
            "label": ACCESS_MODE_LABELS[mode],
            "description": ACCESS_MODE_DESCRIPTIONS[mode],
            "scopes": dict(ACCESS_MODE_SCOPES[mode]),
        }
        for mode in ACCESS_MODES
    ]


def _retired_permission(*args, **kwargs):
    raise PermissionDenied(
        "Scoped grants and approvals are retired. Select one global access mode: "
        "Read Only, Workspace Write, Auto Review or Full Access.")


# Compatibility names fail explicitly instead of creating a second policy.
def grant(scope, project_id=None, source=DEFAULT_GRANT_SOURCE):
    normalize_scope(scope)
    _retired_permission()


def revoke(scope, project_id=None, source=DEFAULT_GRANT_SOURCE):
    normalize_scope(scope)
    _retired_permission()


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
        "Select Workspace Write, Auto Review or Full Access in Global access "
        "as appropriate; models cannot change the mode."
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
    * A cloud model requires Auto Review or Full Access.
    * A remote (non-loopback) endpoint requires Auto Review or Full Access.
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
            f"CLOUD: model {model_name!r} requires Auto Review or Full Access"
        )
    if NETWORK in missing:
        reasons.append(
            f"NETWORK: remote endpoint {base_url!r} requires Auto Review or Full Access"
        )
    where = "globally" if project_id is None else f"for project {project_id}"
    return (
        f"Model access denied {where}: " + "; ".join(reasons) + ". "
        "Select a global access mode that permits cloud/network access. "
        "Models cannot change the access mode."
    )

# ===========================================================================
# Capability taxonomy and legacy audit compatibility
# ===========================================================================
# Scope descriptors retain identity/context validation. Authorization for every
# capability is derived exclusively from _MODE_CAPABILITIES. Historical grant
# and approval records remain readable, without influencing current decisions.

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

#: Historical taxonomy defaults retained for audit compatibility only.
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


def expire_capability_approvals() -> int:
    """Persist expiry for overdue pending approvals; returns the number changed."""
    store = _capability_store()
    conn = store.connect()
    try:
        return store.expire_approvals(conn)
    finally:
        conn.close()


# --- grants and revocation --------------------------------------------------


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


_MODE_CAPABILITIES: dict[str, frozenset[str]] = {
    ACCESS_READ_ONLY: frozenset({
        CAPABILITY_READ,
        CAPABILITY_MODEL_INFERENCE_LOCAL,
        # Dictation is local user input, available in every conversation mode.
        CAPABILITY_MICROPHONE,
    }),
    ACCESS_WORKSPACE_WRITE: frozenset({
        CAPABILITY_READ,
        CAPABILITY_WRITE,
        CAPABILITY_EXECUTE,
        CAPABILITY_MODEL_INFERENCE_LOCAL,
        CAPABILITY_INSTALL_PRIVATE,
        CAPABILITY_GIT_COMMIT,
        CAPABILITY_MCP_CALL,
        CAPABILITY_MICROPHONE,
    }),
    ACCESS_AUTO_REVIEW: frozenset({
        CAPABILITY_READ,
        CAPABILITY_WRITE,
        CAPABILITY_EXECUTE,
        CAPABILITY_MODEL_INFERENCE_LOCAL,
        CAPABILITY_MODEL_INFERENCE_CLOUD,
        CAPABILITY_INSTALL_PRIVATE,
        CAPABILITY_GIT_COMMIT,
        CAPABILITY_WEB_SEARCH,
        CAPABILITY_WEB_FETCH,
        CAPABILITY_BROWSER_INTERACT,
        CAPABILITY_DOWNLOAD,
        CAPABILITY_OPEN_EXTERNAL_PROJECT,
        CAPABILITY_NETWORK_WRITE,
        CAPABILITY_MCP_CALL,
        CAPABILITY_MICROPHONE,
    }),
    ACCESS_FULL_ACCESS: frozenset(CAPABILITIES),
}


def check_access(
    capability: str,
    scope: object = None,
    context: dict | None = None,
) -> CapabilityDecision:
    """Evaluate a capability against the single global access mode.

    This and the compatibility alias ``check_capability`` consult no per-project,
    per-mission, per-agent or per-capability grants. Only the four GUI modes decide.
    """
    capability = normalize_capability(capability)
    cap_scope = normalize_capability_scope(scope, context)
    try:
        mode = get_access_mode()
    except Exception as exc:  # fail closed
        return Denied(
            capability,
            "Fail-closed: access mode unavailable (" + str(exc) + ")",
            scope_kind=cap_scope.kind,
            scope_value=cap_scope.value,
            project_id=cap_scope.project_id,
        )
    scope_kwargs = {
        "scope_kind": cap_scope.kind,
        "scope_value": cap_scope.value,
        "project_id": cap_scope.project_id,
    }
    if capability in _MODE_CAPABILITIES[mode]:
        return Allowed(
            capability,
            "Allowed by access mode " + repr(mode) + ".",
            **scope_kwargs,
        )
    return Denied(
        capability,
        "Denied by access mode " + repr(mode) + ". Select Auto Review or "
        "Full Access if this operation should be allowed.",
        **scope_kwargs,
    )


def require_access(
    capability: str,
    scope: object = None,
    context: dict | None = None,
) -> CapabilityDecision:
    """Raise PermissionDenied unless the global access mode allows the capability."""
    decision = check_access(capability, scope, context)
    if not isinstance(decision, Allowed):
        raise PermissionDenied(
            decision.reason,
            scope=decision.capability,
            project_id=decision.project_id,
        )
    return decision


def check_capability(capability: str, scope: object = None,
                     context: dict | None = None) -> CapabilityDecision:
    """Compatibility alias; durable legacy grants never affect authorization."""
    return check_access(capability, scope, context)


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


# Old records remain available for audit; new approvals/grants are not writable.
request_capability = _retired_permission
decide_capability_approval = _retired_permission
grant_capability = _retired_permission
revoke_capability = _retired_permission

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
from datetime import datetime
from typing import Iterator
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

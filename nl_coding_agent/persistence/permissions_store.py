"""Durable SQLite store for capability grants and approvals (NL-BP-168, additive).

Persistence only: the taxonomy, scope matching, precedence rules and the
fail-closed check_capability() decision live in nl_coding_agent.core.permissions.
Tables are created additively by persistence.database.init_db so existing
databases keep their legacy app_settings policy untouched.

Tables:
* capability_grants   - durable scoped allow/deny decisions (expiry, revocation,
                        allow-once consumption, project/mission scoping).
* capability_approvals - durable pending/approved/denied approval requests
                        (survive crash/restart; WAIT_APPROVAL is never in-memory).

Every write appends one events row with source 'permissions' and an
event_kind prefixed capability_; audit payloads never contain file contents,
secrets or full context values.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from nl_coding_agent.persistence.database import init_db

AUDIT_SOURCE = "permissions"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect():
    """Open the application database (schema is created/migrated idempotently)."""
    return init_db()


def _decode(row) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    try:
        data["context"] = json.loads(data.get("context_json") or "{}")
    except (TypeError, ValueError):
        data["context"] = {}
    return data


def audit(conn, *, level: str, message: str, kind: str, payload: dict) -> None:
    """Append one capability audit row to the existing events table."""
    body = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False)
    with conn:
        conn.execute(
            "INSERT INTO events (source, level, message, payload, event_kind) "
            "VALUES (?,?,?,?,?)",
            (AUDIT_SOURCE, str(level or "info"), str(message), body, str(kind)),
        )


# --------------------------------------------------------------------------- #
# Grants
# --------------------------------------------------------------------------- #

def insert_grant(
    conn,
    *,
    capability: str,
    scope_kind: str,
    scope_value: str | None,
    project_id: int | None,
    decision: str,
    source: str,
    context: dict,
    expires_at: str | None,
) -> int:
    created = now_iso()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO capability_grants
                (capability, scope_kind, scope_value, project_id, decision,
                 source, context_json, created_at, expires_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                capability, scope_kind, scope_value, project_id, decision,
                source, json.dumps(context or {}, sort_keys=True), created,
                expires_at,
            ),
        )
        return int(cursor.lastrowid)


def get_grant(conn, grant_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM capability_grants WHERE id=?", (int(grant_id),)
    ).fetchone()
    return _decode(row)


def fetch_grants(
    conn,
    capability: str,
    *,
    active_only: bool = True,
    include_expired: bool = False,
    include_revoked: bool = False,
    now: str | None = None,
) -> list[dict]:
    """Return grants for one capability ordered by id ascending (oldest first)."""
    moment = str(now or now_iso())
    rows = conn.execute(
        "SELECT * FROM capability_grants WHERE capability=? ORDER BY id ASC",
        (capability,),
    ).fetchall()
    grants: list[dict] = []
    for row in rows:
        data = _decode(row)
        if active_only:
            if data.get("revoked_at"):
                continue
            if data.get("consumed_at"):
                continue
            expiry = data.get("expires_at")
            if expiry and str(expiry) <= moment:
                continue
        else:
            if data.get("revoked_at") and not include_revoked:
                continue
            expiry = data.get("expires_at")
            if expiry and str(expiry) <= moment and not include_expired:
                continue
        grants.append(data)
    return grants


def revoke_grants(
    conn,
    *,
    capability: str | None = None,
    scope_kind: str | None = None,
    scope_value: str | None = None,
    project_id: int | None = None,
    now: str | None = None,
) -> list[dict]:
    """Revoke every matching active grant; return the affected rows."""
    moment = str(now or now_iso())
    clauses = ["revoked_at IS NULL", "consumed_at IS NULL",
               "(expires_at IS NULL OR expires_at > ?)"]
    params: list[Any] = [moment]
    if capability is not None:
        clauses.append("capability=?")
        params.append(capability)
    if scope_kind is not None:
        clauses.append("scope_kind=?")
        params.append(scope_kind)
    if scope_value is not None:
        clauses.append("scope_value=?")
        params.append(scope_value)
    if project_id is not None:
        clauses.append("project_id=?")
        params.append(int(project_id))
    query = "SELECT * FROM capability_grants WHERE " + " AND ".join(clauses) + " ORDER BY id ASC"
    rows = [_decode(row) for row in conn.execute(query, params).fetchall()]
    if not rows:
        return []
    ids = [int(row["id"]) for row in rows]
    with conn:
        conn.execute(
            "UPDATE capability_grants SET revoked_at=? WHERE id IN ("
            + ",".join("?" for _ in ids) + ")",
            (moment, *ids),
        )
    return [row for row in rows]


def consume_grant(conn, grant_id: int, *, now: str | None = None) -> bool:
    """Atomically consume an allow-once grant. Returns True only for one caller."""
    moment = str(now or now_iso())
    with conn:
        cursor = conn.execute(
            "UPDATE capability_grants SET consumed_at=? "
            "WHERE id=? AND consumed_at IS NULL AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > ?)",
            (moment, int(grant_id), moment),
        )
        return cursor.rowcount == 1


# --------------------------------------------------------------------------- #
# Approvals (durable pending WAIT_APPROVAL)
# --------------------------------------------------------------------------- #

def insert_approval(
    conn,
    *,
    capability: str,
    scope_kind: str,
    scope_value: str | None,
    project_id: int | None,
    context: dict,
    reason: str,
    expires_at: str | None,
    source: str,
) -> int:
    requested = now_iso()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO capability_approvals
                (capability, scope_kind, scope_value, project_id, context_json,
                 reason, status, requested_at, expires_at, source)
            VALUES (?,?,?,?,?,?, 'pending', ?, ?, ?)
            """,
            (
                capability, scope_kind, scope_value, project_id,
                json.dumps(context or {}, sort_keys=True), str(reason or ""),
                requested, expires_at, source,
            ),
        )
        return int(cursor.lastrowid)


def get_approval(conn, approval_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM capability_approvals WHERE id=?", (int(approval_id),)
    ).fetchone()
    return _decode(row)


def fetch_approvals(
    conn,
    capability: str | None = None,
    *,
    statuses: tuple[str, ...] | None = None,
    project_id: int | None = None,
    now: str | None = None,
) -> list[dict]:
    moment = str(now or now_iso())
    clauses: list[str] = []
    params: list[Any] = []
    if capability is not None:
        clauses.append("capability=?")
        params.append(capability)
    if statuses:
        clauses.append("status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    if project_id is not None:
        clauses.append("project_id=?")
        params.append(int(project_id))
    query = "SELECT * FROM capability_approvals"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id ASC"
    approvals: list[dict] = []
    for row in conn.execute(query, params).fetchall():
        data = _decode(row)
        expiry = data.get("expires_at")
        if data.get("status") == "pending" and expiry and str(expiry) <= moment:
            data["status"] = "expired"
        approvals.append(data)
    return approvals


def decide_approval(
    conn,
    approval_id: int,
    *,
    status: str,
    decided_by: str,
    decision: str | None = None,
    grant_id: int | None = None,
    now: str | None = None,
) -> bool:
    moment = str(now or now_iso())
    with conn:
        cursor = conn.execute(
            "UPDATE capability_approvals SET status=?, decided_at=?, decided_by=?, "
            "decision=?, grant_id=? WHERE id=? AND status='pending'",
            (str(status), moment, str(decided_by), decision, grant_id,
             int(approval_id)),
        )
        return cursor.rowcount == 1


def expire_approvals(conn, *, now: str | None = None) -> int:
    """Mark overdue pending approvals expired; returns the number changed."""
    moment = str(now or now_iso())
    with conn:
        cursor = conn.execute(
            "UPDATE capability_approvals SET status='expired', decided_at=? "
            "WHERE status='pending' AND expires_at IS NOT NULL AND expires_at <= ?",
            (moment, moment),
        )
        return int(cursor.rowcount)


# --------------------------------------------------------------------------- #
# Inspection helpers
# --------------------------------------------------------------------------- #

def list_grants(conn, *, capability: str | None = None, limit: int = 200) -> list[dict]:
    if capability is not None:
        rows = conn.execute(
            "SELECT * FROM capability_grants WHERE capability=? ORDER BY id DESC LIMIT ?",
            (capability, max(1, int(limit))),
        )
    else:
        rows = conn.execute(
            "SELECT * FROM capability_grants ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        )
    return [_decode(row) for row in rows]


def list_approvals(conn, *, capability: str | None = None,
                   limit: int = 200) -> list[dict]:
    if capability is not None:
        rows = conn.execute(
            "SELECT * FROM capability_approvals WHERE capability=? ORDER BY id DESC LIMIT ?",
            (capability, max(1, int(limit))),
        )
    else:
        rows = conn.execute(
            "SELECT * FROM capability_approvals ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        )
    return [_decode(row) for row in rows]


def list_events(conn, *, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT id, source, level, message, payload, event_kind, created_at "
        "FROM events WHERE source=? AND event_kind LIKE 'capability_%' "
        "ORDER BY id DESC LIMIT ?",
        (AUDIT_SOURCE, max(1, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]

"""Durable stage-3 supervisor store (C3a).

Fail-closed persistence for the persistent supervisor: lease + heartbeat rows,
durable mission queue with claim tokens/idempotency keys, supervisor runs and
control commands, the indexed-backlog SQLite mirror, the per-mission evidence
ledger and risky-action approvals.

This module owns SQL only; policy (whether to run, what to select, retry rules)
lives in the future core/supervisor.py and core/backlog.py. Every mutation is
additive/idempotent so a crashed supervisor can be reconciled from durable facts
(missions, stage manifests, promotion journals) instead of guessing.
"""
from __future__ import annotations

import json
import os
import sqlite3
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator

from nl_coding_agent.persistence.database import init_db

__all__ = [
    "RUN_MODES", "RUN_STATES", "TERMINAL_RUN_STATES", "ACTIVE_RUN_STATES",
    "QUEUE_STATES", "QUEUE_TERMINAL_STATES", "QUEUE_CLAIMABLE_STATES",
    "QUEUE_TRANSITIONS", "BACKLOG_SUPERVISOR_STATES", "APPROVAL_STATUSES",
    "StoreError", "LeaseConflict", "Lease",
    "acquire_lease", "renew_lease", "release_lease", "get_lease",
    "acquire_machine_lease", "renew_machine_lease", "release_machine_lease",
    "get_machine_lease",
    "start_run", "update_run", "finish_run", "get_run", "get_active_run",
    "set_run_flags", "request_command", "take_pending_commands",
    "enqueue_mission", "get_queue_item", "find_queue_item", "list_queue",
    "claim_queue_item", "update_queue_item",
    "sync_backlog", "get_backlog_item", "list_backlog", "set_backlog_progress",
    "record_evidence", "list_evidence",
    "create_approval", "decide_approval", "get_approval", "list_approvals",
    "pending_approvals",
    "create_flow_approval", "get_approval_by_flow", "decide_flow_approval",
    "flow_approval_outcome", "pending_flow_approvals",
    "FLOW_RUN_STATES", "start_flow_run", "update_flow_run", "get_flow_run",
    "list_flow_runs",
]


# --------------------------------------------------------------------------- #
# Vocabulary and validation tables
# --------------------------------------------------------------------------- #

RUN_MODES: tuple[str, ...] = ("off", "assisted", "automatic")

RUN_STATES: tuple[str, ...] = (
    "STARTING", "RUNNING", "PAUSED", "WAITING_FOR_RESOURCES",
    "WAITING_FOR_APPROVAL", "STOPPING", "STOPPED", "BLOCKED", "COMPLETED",
    "RECOVERING",
)
ACTIVE_RUN_STATES: tuple[str, ...] = (
    "STARTING", "RUNNING", "PAUSED", "WAITING_FOR_RESOURCES",
    "WAITING_FOR_APPROVAL", "STOPPING", "RECOVERING",
)
TERMINAL_RUN_STATES: tuple[str, ...] = ("STOPPED", "BLOCKED", "COMPLETED")

QUEUE_STATES: tuple[str, ...] = (
    "PROPOSED", "READY", "CLAIMED", "RUNNING", "VERIFYING", "REVIEWING",
    "VERIFIED", "NEEDS_FIX", "BLOCKED", "INTERRUPTED", "CANCELLED",
)
QUEUE_TERMINAL_STATES: tuple[str, ...] = ("VERIFIED", "BLOCKED", "CANCELLED")
QUEUE_CLAIMABLE_STATES: tuple[str, ...] = ("READY", "INTERRUPTED", "NEEDS_FIX")

QUEUE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "PROPOSED": ("READY", "CANCELLED"),
    "READY": ("CLAIMED", "BLOCKED", "CANCELLED"),
    "CLAIMED": ("RUNNING", "READY", "BLOCKED", "INTERRUPTED", "CANCELLED"),
    "RUNNING": ("VERIFYING", "NEEDS_FIX", "BLOCKED", "INTERRUPTED", "CANCELLED"),
    "VERIFYING": ("REVIEWING", "NEEDS_FIX", "BLOCKED", "INTERRUPTED", "CANCELLED"),
    "REVIEWING": ("VERIFIED", "NEEDS_FIX", "BLOCKED", "INTERRUPTED", "CANCELLED"),
    "NEEDS_FIX": ("CLAIMED", "READY", "BLOCKED", "CANCELLED"),
    "INTERRUPTED": ("CLAIMED", "READY", "BLOCKED", "CANCELLED"),
    "VERIFIED": (),
    "BLOCKED": (),
    "CANCELLED": (),
}

BACKLOG_SUPERVISOR_STATES: tuple[str, ...] = (
    "READY", "IN_FLIGHT", "VERIFIED", "NEEDS_FIX", "BLOCKED", "SKIPPED",
)
FLOW_RUN_STATES: tuple[str, ...] = (
    "RUNNING", "PAUSED_WAITING_APPROVAL", "INTERRUPTED", "COMPLETED",
    "BLOCKED", "FAILED",
)
FLOW_RUN_PIPELINES: tuple[str, ...] = ("mission", "supervisor", "audit")
FLOW_TERMINAL_STATES: tuple[str, ...] = (
    "INTERRUPTED", "COMPLETED", "BLOCKED", "FAILED",
)

APPROVAL_STATUSES: tuple[str, ...] = ("pending", "approved", "denied", "expired")
APPROVAL_ACTIONS: tuple[str, ...] = (
    "delete", "network", "cloud", "install", "publish", "migrate", "external_tool",
    "review",
)

_RUN_UPDATABLE = frozenset({
    "mode", "status", "owner_id", "owner_pid", "config_json",
    "stop_requested", "pause_requested", "missions_completed",
    "missions_failed", "heartbeat_at", "finished_at", "stopped_reason",
})
_QUEUE_FIELD_COLUMNS = frozenset({
    "mission_id", "priority", "goal", "budget_json", "payload_json",
    "failure_class", "failure_signature", "scheduled_at", "heartbeat_at",
    "finished_at", "lease_owner", "claim_token",
})
_BACKLOG_JSON_FIELDS = ("dependencies", "acceptance", "source_refs")


class StoreError(RuntimeError):
    """Base class for durable-store contract failures."""


class LeaseConflict(StoreError):
    """Raised when another live owner holds the project/machine lease."""

    def __init__(self, message: str, *, project_id: int | None = None,
                 owner_id: str | None = None, owner_pid: int | None = None,
                 owner_host: str | None = None,
                 expires_at: str | None = None) -> None:
        super().__init__(message)
        self.project_id = project_id
        self.owner_id = owner_id
        self.owner_pid = owner_pid
        self.owner_host = owner_host
        self.expires_at = expires_at


@dataclass(frozen=True)
class Lease:
    project_id: int
    owner_id: str
    version: int
    expires_at: str


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _iso_after(seconds: float) -> str:
    return (datetime.now() + timedelta(seconds=float(seconds))).isoformat(timespec="seconds")


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:  # pragma: no cover - defensive
        return "unknown-host"


def _pid_alive(pid: int) -> bool:
    """Return True only when the process is provably alive on this host."""
    if pid <= 0:
        return False
    try:
        import psutil

        return bool(psutil.pid_exists(pid))
    except Exception:
        pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = init_db()
    try:
        yield conn
    finally:
        conn.close()


def _dumps(value) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _loads(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError):
        return default


def _decode(row: sqlite3.Row, json_fields: dict[str, str]) -> dict:
    data = dict(row)
    for source, target in json_fields.items():
        data[target] = _loads(data.get(source), [] if target in
                              ("dependencies", "acceptance", "source_refs") else {})
    return data


def _require_text(value, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise StoreError(name + " is required")
    return text


# --------------------------------------------------------------------------- #
# Project leases (one supervisor per project)
# --------------------------------------------------------------------------- #

def _lease_row_text(row: sqlite3.Row) -> dict:
    return {
        "project_id": row["project_id"],
        "owner_id": row["owner_id"],
        "owner_pid": row["owner_pid"],
        "owner_host": row["owner_host"],
        "version": row["version"],
        "acquired_at": row["acquired_at"],
        "heartbeat_at": row["heartbeat_at"],
        "expires_at": row["expires_at"],
    }


def acquire_lease(project_id: int, *, owner_id: str, owner_pid: int,
                  owner_host: str, ttl_s: float) -> Lease:
    """Acquire or renew the single project lease with compare-and-swap semantics.

    A live, non-expired owner always wins (LeaseConflict). An expired lease is
    stolen only when remapping is provable: the recorded owner runs on another
    host, or the recorded pid is not alive on this host. The caller never kills
    another process; a conflicting owner must be stopped through the supervisor
    commands or by the OS.
    """
    project = int(project_id)
    owner = _require_text(owner_id, "owner_id")
    pid = int(owner_pid)
    if pid <= 0:
        raise StoreError("owner_pid must be a positive process id")
    host = str(owner_host or _hostname()).strip() or _hostname()
    now = _now()
    expires = _iso_after(ttl_s)
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM supervisor_leases WHERE project_id=?", (project,)
        ).fetchone()
        if row is not None:
            if str(row["owner_id"]) == owner:
                version = int(row["version"]) + 1
                conn.execute(
                    """
                    UPDATE supervisor_leases
                       SET owner_pid=?, owner_host=?, version=?, heartbeat_at=?, expires_at=?
                     WHERE project_id=?
                    """,
                    (pid, host, version, now, expires, project),
                )
                return Lease(project, owner, version, expires)
            if str(row["expires_at"]) >= now:
                raise LeaseConflict(
                    "Supervisor lease for project " + str(project) + " is held by "
                    "owner " + str(row["owner_id"]) + " (pid " + str(row["owner_pid"])
                    + ", host " + str(row["owner_host"]) + ") until "
                    + str(row["expires_at"]) + ".",
                    project_id=project, owner_id=str(row["owner_id"]),
                    owner_pid=int(row["owner_pid"]), owner_host=str(row["owner_host"]),
                    expires_at=str(row["expires_at"]),
                )
            if str(row["owner_host"]) == host and _pid_alive(int(row["owner_pid"])):
                raise LeaseConflict(
                    "Supervisor lease for project " + str(project) + " expired but "
                    "its recorded owner process (pid " + str(row["owner_pid"])
                    + ") is still alive; refusing to steal the lease.",
                    project_id=project, owner_id=str(row["owner_id"]),
                    owner_pid=int(row["owner_pid"]), owner_host=str(row["owner_host"]),
                    expires_at=str(row["expires_at"]),
                )
            version = int(row["version"]) + 1
            conn.execute(
                """
                UPDATE supervisor_leases
                   SET owner_id=?, owner_pid=?, owner_host=?, version=?,
                       acquired_at=?, heartbeat_at=?, expires_at=?
                 WHERE project_id=?
                """,
                (owner, pid, host, version, now, now, expires, project),
            )
            return Lease(project, owner, version, expires)
        conn.execute(
            """
            INSERT INTO supervisor_leases
                (project_id, owner_id, owner_pid, owner_host, version,
                 acquired_at, heartbeat_at, expires_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (project, owner, pid, host, 1, now, now, expires),
        )
        return Lease(project, owner, 1, expires)


def renew_lease(project_id: int, *, owner_id: str, version: int,
                ttl_s: float) -> Lease | None:
    """Renew a held lease; None means the lease was lost (do not keep writing)."""
    project = int(project_id)
    owner = _require_text(owner_id, "owner_id")
    expected = int(version)
    now = _now()
    expires = _iso_after(ttl_s)
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            UPDATE supervisor_leases
               SET heartbeat_at=?, expires_at=?, version=version+1
             WHERE project_id=? AND owner_id=? AND version=?
            """,
            (now, expires, project, owner, expected),
        )
        if cursor.rowcount != 1:
            return None
        return Lease(project, owner, expected + 1, expires)


def release_lease(project_id: int, *, owner_id: str) -> None:
    owner = _require_text(owner_id, "owner_id")
    with _db() as conn, conn:
        conn.execute(
            "DELETE FROM supervisor_leases WHERE project_id=? AND owner_id=?",
            (int(project_id), owner),
        )


def get_lease(project_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM supervisor_leases WHERE project_id=?", (int(project_id),)
        ).fetchone()
        return _lease_row_text(row) if row is not None else None


# --------------------------------------------------------------------------- #
# Machine-level inference lease (serializes local inference across projects)
# --------------------------------------------------------------------------- #

def _machine_lease_row(row: sqlite3.Row) -> dict:
    return {
        "resource": row["resource"],
        "owner_id": row["owner_id"],
        "owner_pid": row["owner_pid"],
        "owner_host": row["owner_host"],
        "version": row["version"],
        "acquired_at": row["acquired_at"],
        "heartbeat_at": row["heartbeat_at"],
        "expires_at": row["expires_at"],
    }


def acquire_machine_lease(resource: str, *, owner_id: str, owner_pid: int,
                          owner_host: str, ttl_s: float) -> Lease | None:
    """Acquire a machine resource lease; None means another live owner holds it."""
    name = _require_text(resource, "resource")
    owner = _require_text(owner_id, "owner_id")
    pid = int(owner_pid)
    if pid <= 0:
        raise StoreError("owner_pid must be a positive process id")
    host = str(owner_host or _hostname()).strip() or _hostname()
    now = _now()
    expires = _iso_after(ttl_s)
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM machine_leases WHERE resource=?", (name,)
        ).fetchone()
        if row is not None:
            if str(row["owner_id"]) == owner:
                version = int(row["version"]) + 1
                conn.execute(
                    """
                    UPDATE machine_leases
                       SET owner_pid=?, owner_host=?, version=?, heartbeat_at=?, expires_at=?
                     WHERE resource=?
                    """,
                    (pid, host, version, now, expires, name),
                )
                return Lease(0, owner, version, expires)
            if str(row["expires_at"]) >= now:
                return None
            if str(row["owner_host"]) == host and _pid_alive(int(row["owner_pid"])):
                return None
            version = int(row["version"]) + 1
            conn.execute(
                """
                UPDATE machine_leases
                   SET owner_id=?, owner_pid=?, owner_host=?, version=?,
                       acquired_at=?, heartbeat_at=?, expires_at=?
                 WHERE resource=?
                """,
                (owner, pid, host, version, now, now, expires, name),
            )
            return Lease(0, owner, version, expires)
        conn.execute(
            """
            INSERT INTO machine_leases
                (resource, owner_id, owner_pid, owner_host, version,
                 acquired_at, heartbeat_at, expires_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (name, owner, pid, host, 1, now, now, expires),
        )
        return Lease(0, owner, 1, expires)


def renew_machine_lease(resource: str, *, owner_id: str, version: int,
                        ttl_s: float) -> bool:
    name = _require_text(resource, "resource")
    owner = _require_text(owner_id, "owner_id")
    now = _now()
    expires = _iso_after(ttl_s)
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            UPDATE machine_leases
               SET heartbeat_at=?, expires_at=?, version=version+1
             WHERE resource=? AND owner_id=? AND version=?
            """,
            (now, expires, name, owner, int(version)),
        )
        return cursor.rowcount == 1


def release_machine_lease(resource: str, *, owner_id: str) -> None:
    name = _require_text(resource, "resource")
    owner = _require_text(owner_id, "owner_id")
    with _db() as conn, conn:
        conn.execute(
            "DELETE FROM machine_leases WHERE resource=? AND owner_id=?",
            (name, owner),
        )


def get_machine_lease(resource: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM machine_leases WHERE resource=?", (_require_text(resource, "resource"),)
        ).fetchone()
        return _machine_lease_row(row) if row is not None else None


# --------------------------------------------------------------------------- #
# Supervisor runs and control commands
# --------------------------------------------------------------------------- #

def _run_values(fields: dict) -> dict:
    """Validate and normalize a supervisor_runs update mapping."""
    values: dict = {}
    for key, raw in fields.items():
        if key not in _RUN_UPDATABLE:
            raise StoreError("Unsupported supervisor_runs column: " + str(key))
        if key in ("stop_requested", "pause_requested"):
            values[key] = 1 if raw else 0
        elif key == "config_json":
            values[key] = _dumps(raw) if isinstance(raw, dict) else str(raw)
        else:
            values[key] = raw
    return values


def start_run(project_id: int, *, mode: str, config: dict, owner_id: str,
              owner_pid: int) -> int:
    mode_text = str(mode or "").strip()
    if mode_text not in RUN_MODES:
        raise StoreError("Invalid supervisor mode: " + repr(mode))
    own = _require_text(owner_id, "owner_id")
    now = _now()
    with _db() as conn, conn:
        cursor = conn.execute(
            """
            INSERT INTO supervisor_runs
                (project_id, mode, status, owner_id, owner_pid, config_json,
                 started_at, heartbeat_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (int(project_id), mode_text, "STARTING", own, int(owner_pid),
             _dumps(config or {}), now, now),
        )
        return int(cursor.lastrowid)


def update_run(run_id: int, *, status: str | None = None, **fields) -> bool:
    values = _run_values(fields)
    if status is not None:
        state = str(status).strip()
        if state not in RUN_STATES:
            raise StoreError("Invalid supervisor run status: " + repr(status))
        values["status"] = state
    if not values:
        return False
    assignments = ", ".join(column + "=?" for column in values)
    params = list(values.values()) + [int(run_id)]
    with _db() as conn, conn:
        cursor = conn.execute(
            "UPDATE supervisor_runs SET " + assignments + " WHERE id=?", params
        )
        return cursor.rowcount == 1


def finish_run(run_id: int, *, status: str, reason: str = "") -> None:
    state = str(status).strip()
    if state not in TERMINAL_RUN_STATES:
        raise StoreError("finish_run requires a terminal status, got " + repr(status))
    with _db() as conn, conn:
        conn.execute(
            """
            UPDATE supervisor_runs
               SET status=?, finished_at=?, stopped_reason=?
             WHERE id=?
            """,
            (state, _now(), str(reason or ""), int(run_id)),
        )


def get_run(run_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM supervisor_runs WHERE id=?", (int(run_id),)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["config"] = _loads(data.get("config_json"), {})
        return data


def get_active_run(project_id: int) -> dict | None:
    placeholders = ",".join("?" for _ in TERMINAL_RUN_STATES)
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM supervisor_runs WHERE project_id=? AND status NOT IN ("
            + placeholders + ") ORDER BY id DESC LIMIT 1",
            (int(project_id), *TERMINAL_RUN_STATES),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["config"] = _loads(data.get("config_json"), {})
        return data


# --------------------------------------------------------------------------- #
# CrewAI Flow runs (C4b additive; app-owned SQLite only)
# --------------------------------------------------------------------------- #

def _validate_flow_status(status: str) -> str:
    text = str(status or "").strip().upper()
    if text not in FLOW_RUN_STATES:
        raise StoreError("Invalid flow run status: " + repr(status))
    return text


def start_flow_run(flow_id: str, project_id: int, *, mission_id: int | None = None,
                   queue_id: int | None = None,
                   supervisor_run_id: int | None = None,
                   pipeline: str = "mission",
                   status: str = "RUNNING") -> dict:
    """Create or re-open one durable flow run row (idempotent by flow_id)."""
    flow_key = _require_text(flow_id, "flow_id")
    project_value = int(project_id)
    pipeline_text = str(pipeline or "").strip()
    if pipeline_text not in FLOW_RUN_PIPELINES:
        raise StoreError("Invalid flow pipeline: " + repr(pipeline))
    status_text = _validate_flow_status(status)
    now = _now()
    with _db() as conn, conn:
        conn.execute(
            """
            INSERT INTO flow_runs
                (flow_id, project_id, mission_id, queue_id, supervisor_run_id,
                 pipeline, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(flow_id) DO UPDATE SET
                status=excluded.status,
                updated_at=excluded.updated_at,
                mission_id=COALESCE(excluded.mission_id, flow_runs.mission_id),
                queue_id=COALESCE(excluded.queue_id, flow_runs.queue_id),
                supervisor_run_id=COALESCE(excluded.supervisor_run_id,
                                           flow_runs.supervisor_run_id)
            """,
            (flow_key, project_value,
             int(mission_id) if mission_id is not None else None,
             int(queue_id) if queue_id is not None else None,
             int(supervisor_run_id) if supervisor_run_id is not None else None,
             pipeline_text, status_text, now, now),
        )
    return get_flow_run(flow_key)


def update_flow_run(flow_id: str, *, status: str | None = None,
                    last_method: str | None = None,
                    state_sha256: str | None = None,
                    finished_at: str | None = None,
                    mission_id: int | None = None) -> bool:
    """Update selected flow-run columns; terminal status stamps finished_at once."""
    flow_key = _require_text(flow_id, "flow_id")
    values: dict[str, object] = {}
    if status is not None:
        values["status"] = _validate_flow_status(status)
    if last_method is not None:
        values["last_method"] = str(last_method)
    if state_sha256 is not None:
        values["state_sha256"] = str(state_sha256)
    if finished_at is not None:
        values["finished_at"] = str(finished_at)
    if mission_id is not None:
        values["mission_id"] = int(mission_id)
    if not values:
        return False
    values["updated_at"] = _now()
    assignments = ", ".join(column + "=?" for column in values)
    with _db() as conn, conn:
        cursor = conn.execute(
            "UPDATE flow_runs SET " + assignments + " WHERE flow_id=?",
            (*values.values(), flow_key),
        )
        return cursor.rowcount == 1


def get_flow_run(flow_id: str) -> dict | None:
    flow_key = str(flow_id or "").strip()
    if not flow_key:
        raise StoreError("flow_id is required")
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM flow_runs WHERE flow_id=?", (flow_key,)
        ).fetchone()
        return dict(row) if row else None


def list_flow_runs(*, project_id: int | None = None,
                   status: str | None = None) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if project_id is not None:
        clauses.append("project_id=?")
        params.append(int(project_id))
    if status is not None:
        clauses.append("status=?")
        params.append(_validate_flow_status(status))
    query = "SELECT * FROM flow_runs"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY updated_at DESC, flow_id DESC"
    with _db() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def set_run_flags(run_id: int, *, pause: bool | None = None,
                  stop: bool | None = None) -> bool:
    values: dict = {}
    if pause is not None:
        values["pause_requested"] = 1 if pause else 0
    if stop is not None:
        values["stop_requested"] = 1 if stop else 0
    if not values:
        return False
    assignments = ", ".join(column + "=?" for column in values)
    with _db() as conn, conn:
        cursor = conn.execute(
            "UPDATE supervisor_runs SET " + assignments + " WHERE id=?",
            (*values.values(), int(run_id)),
        )
        return cursor.rowcount == 1


def request_command(project_id: int, command: str, *, requested_by: str,
                    run_id: int | None = None) -> int:
    name = _require_text(command, "command").lower()
    if name not in ("start", "stop", "pause", "resume", "kick"):
        raise StoreError("Unsupported supervisor command: " + repr(command))
    with _db() as conn, conn:
        cursor = conn.execute(
            """
            INSERT INTO supervisor_commands
                (project_id, run_id, command, requested_by, created_at)
            VALUES (?,?,?,?,?)
            """,
            (int(project_id), int(run_id) if run_id is not None else None,
             name, _require_text(requested_by, "requested_by"), _now()),
        )
        return int(cursor.lastrowid)


def take_pending_commands(project_id: int, run_id: int | None = None) -> list[dict]:
    """Return unconsumed commands once and mark them consumed atomically."""
    project = int(project_id)
    now = _now()
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if run_id is None:
            rows = conn.execute(
                "SELECT * FROM supervisor_commands WHERE project_id=? AND consumed_at IS NULL ORDER BY id",
                (project,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM supervisor_commands
                 WHERE project_id=? AND consumed_at IS NULL
                   AND (run_id IS NULL OR run_id=?)
                 ORDER BY id
                """,
                (project, int(run_id)),
            ).fetchall()
        ids = [int(row["id"]) for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                "UPDATE supervisor_commands SET consumed_at=? WHERE id IN (" + placeholders + ")",
                (now, *ids),
            )
        return [dict(row) for row in rows]


# --------------------------------------------------------------------------- #
# Durable mission queue
# --------------------------------------------------------------------------- #

def _validate_queue_state(state: str) -> str:
    text = str(state or "").strip().upper()
    if text not in QUEUE_STATES:
        raise StoreError("Invalid mission_queue state: " + repr(state))
    return text


def _queue_row(row: sqlite3.Row) -> dict:
    return _decode(row, {"budget_json": "budget", "payload_json": "payload"})


def enqueue_mission(project_id: int, *, requirement_id: str | None, goal: str,
                    priority: str, idempotency_key: str, max_attempts: int,
                    budget: dict, payload: dict | None = None,
                    state: str = "READY") -> int:
    """Insert one queue item; a duplicate idempotency key returns the existing row."""
    state_text = _validate_queue_state(state)
    key = _require_text(idempotency_key, "idempotency_key")
    goal_text = _require_text(goal, "goal")
    priority_text = str(priority or "P1").strip().upper()
    if priority_text not in ("P0", "P1", "P2", "P3"):
        raise StoreError("Invalid queue priority: " + repr(priority))
    attempts = int(max_attempts)
    if attempts < 1:
        raise StoreError("max_attempts must be >= 1")
    now = _now()
    with _db() as conn:
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO mission_queue
                        (project_id, requirement_id, state, priority, idempotency_key,
                         attempts, max_attempts, budget_json, goal, payload_json,
                         created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (int(project_id), str(requirement_id) if requirement_id else None,
                     state_text, priority_text, key, 0, attempts, _dumps(budget),
                     goal_text, _dumps(payload or {}), now, now),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id FROM mission_queue WHERE project_id=? AND idempotency_key=?",
                (int(project_id), key),
            ).fetchone()
            if row is None:  # pragma: no cover - defensive
                raise
            return int(row["id"])


def get_queue_item(queue_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM mission_queue WHERE id=?", (int(queue_id),)
        ).fetchone()
        return _queue_row(row) if row is not None else None


def find_queue_item(project_id: int, idempotency_key: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM mission_queue WHERE project_id=? AND idempotency_key=?",
            (int(project_id), str(idempotency_key)),
        ).fetchone()
        return _queue_row(row) if row is not None else None


def list_queue(project_id: int, *, states: tuple[str, ...] | None = None,
               limit: int = 100) -> list[dict]:
    if limit <= 0:
        return []
    query = "SELECT * FROM mission_queue WHERE project_id=?"
    params: list = [int(project_id)]
    if states:
        normalized = tuple(_validate_queue_state(state) for state in states)
        query += " AND state IN (" + ",".join("?" for _ in normalized) + ")"
        params.extend(normalized)
    query += " ORDER BY id ASC LIMIT ?"
    params.append(int(limit))
    with _db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_queue_row(row) for row in rows]


def claim_queue_item(queue_id: int, *, claim_token: str, owner_id: str) -> bool:
    """CAS-claim the queue item; a non-claimable state or token mismatch returns False."""
    token = _require_text(claim_token, "claim_token")
    owner = _require_text(owner_id, "owner_id")
    now = _now()
    placeholders = ",".join("?" for _ in QUEUE_CLAIMABLE_STATES)
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "UPDATE mission_queue SET state='CLAIMED', claim_token=?, lease_owner=?, "
            "claimed_at=?, updated_at=? "
            "WHERE id=? AND state IN (" + placeholders + ") "
            "AND (claim_token IS NULL OR claim_token=?)",
            (token, owner, now, now, int(queue_id), *QUEUE_CLAIMABLE_STATES, token),
        )
        return cursor.rowcount == 1


def update_queue_item(queue_id: int, *, claim_token: str | None = None,
                      state: str | None = None, mission_id: int | None = None,
                      failure_class: str | None = None,
                      failure_signature: str | None = None,
                      increment_attempts: bool = False, **fields) -> bool:
    """Compare-and-swap queue transition; invalid transitions raise, token loss returns False."""
    item = get_queue_item(queue_id)
    if item is None:
        return False
    current = str(item["state"])
    target = current if state is None else _validate_queue_state(state)
    if target != current and target not in QUEUE_TRANSITIONS.get(current, ()):
        raise StoreError("Illegal mission_queue transition: " + current + " -> " + target)
    recorded = item.get("claim_token")
    if recorded is not None:
        # A claimed row may only be transitioned by the owner holding its token.
        if claim_token is None or str(recorded) != str(claim_token):
            return False
    values: dict = {"updated_at": _now()}
    if state is not None:
        values["state"] = target
        if target in QUEUE_TERMINAL_STATES:
            values.setdefault("finished_at", _now())
    if mission_id is not None:
        values["mission_id"] = int(mission_id)
    if failure_class is not None:
        values["failure_class"] = str(failure_class)
    if failure_signature is not None:
        values["failure_signature"] = str(failure_signature)
    for key, raw in fields.items():
        if key not in _QUEUE_FIELD_COLUMNS:
            raise StoreError("Unsupported mission_queue column: " + str(key))
        values[key] = _dumps(raw) if key in ("budget_json", "payload_json") and isinstance(raw, dict) else raw
    parts = [column + "=?" for column in values]
    if increment_attempts:
        parts.append("attempts=attempts+1")
    sql = "UPDATE mission_queue SET " + ", ".join(parts) + " WHERE id=?"
    params = list(values.values()) + [int(queue_id)]
    if claim_token is not None:
        sql += " AND (claim_token IS NULL OR claim_token=?)"
        params.append(str(claim_token))
    with _db() as conn, conn:
        cursor = conn.execute(sql, params)
        return cursor.rowcount == 1


# --------------------------------------------------------------------------- #
# Backlog mirror (SQLite operational copy of the authored INDEX.json)
# --------------------------------------------------------------------------- #

def _backlog_payload(item: dict) -> dict:
    requirement_id = _require_text(item.get("requirement_id") or item.get("id"), "requirement_id")
    return {
        "requirement_id": requirement_id,
        "title": _require_text(item.get("title"), "title"),
        "area": str(item.get("area") or ""),
        "priority": str(item.get("priority") or ""),
        "program_stage": int(item["program_stage"]) if item.get("program_stage") is not None else None,
        "program_stage_name": item.get("program_stage_name"),
        "status": _require_text(item.get("status"), "status"),
        "dependencies": list(item.get("dependencies") or []),
        "acceptance": list(item.get("acceptance") or []),
        "source_refs": list(item.get("source_refs") or []),
        "content_hash": _require_text(item.get("content_hash"), "content_hash"),
    }


def _backlog_row(row: sqlite3.Row) -> dict:
    return _decode(row, {
        "dependencies_json": "dependencies",
        "acceptance_json": "acceptance",
        "source_refs_json": "source_refs",
    })


def sync_backlog(requirements: list[dict], *, source_fingerprint: str) -> dict:
    """Upsert the authored backlog mirror and mark previously known but absent IDs SKIPPED."""
    now = _now()
    report = {"inserted": [], "updated": [], "unchanged": [], "skipped": [],
              "source_fingerprint": str(source_fingerprint or "")}
    seen: list[str] = []
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        for raw in requirements:
            item = _backlog_payload(raw)
            requirement_id = item["requirement_id"]
            seen.append(requirement_id)
            existing = conn.execute(
                "SELECT * FROM backlog_items WHERE requirement_id=?", (requirement_id,)
            ).fetchone()
            columns = {
                "title": item["title"],
                "area": item["area"],
                "priority": item["priority"],
                "program_stage": item["program_stage"],
                "program_stage_name": item["program_stage_name"],
                "status": item["status"],
                "dependencies_json": _dumps(item["dependencies"]),
                "acceptance_json": _dumps(item["acceptance"]),
                "source_refs_json": _dumps(item["source_refs"]),
                "content_hash": item["content_hash"],
                "source_fingerprint": report["source_fingerprint"],
                "last_synced_at": now,
            }
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO backlog_items
                        (requirement_id, title, area, priority, program_stage,
                         program_stage_name, status, dependencies_json, acceptance_json,
                         source_refs_json, content_hash, source_fingerprint,
                         last_synced_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (requirement_id, columns["title"], columns["area"], columns["priority"],
                     columns["program_stage"], columns["program_stage_name"],
                     columns["status"], columns["dependencies_json"],
                     columns["acceptance_json"], columns["source_refs_json"],
                     columns["content_hash"], columns["source_fingerprint"], now),
                )
                report["inserted"].append(requirement_id)
                continue
            stable_columns = (
                "title", "area", "priority", "program_stage", "program_stage_name",
                "status", "dependencies_json", "acceptance_json", "source_refs_json",
                "content_hash",
            )
            changed = any(
                (existing[column] if column in existing.keys() else None) != columns[column]
                for column in stable_columns
            )
            if not changed:
                report["unchanged"].append(requirement_id)
                continue
            assignments = ", ".join(column + "=?" for column in columns)
            conn.execute(
                "UPDATE backlog_items SET " + assignments + " WHERE requirement_id=?",
                (*columns.values(), requirement_id),
            )
            report["updated"].append(requirement_id)
        if seen:
            placeholders = ",".join("?" for _ in seen)
            cursor = conn.execute(
                "UPDATE backlog_items SET supervisor_status='SKIPPED' "
                "WHERE requirement_id NOT IN (" + placeholders + ") "
                "AND (supervisor_status IS NULL OR supervisor_status <> 'SKIPPED')",
                tuple(seen),
            )
            if cursor.rowcount:
                rows = conn.execute(
                    "SELECT requirement_id FROM backlog_items WHERE supervisor_status='SKIPPED'"
                ).fetchall()
                report["skipped"] = [row["requirement_id"] for row in rows]
    return report


def get_backlog_item(requirement_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM backlog_items WHERE requirement_id=?",
            (_require_text(requirement_id, "requirement_id"),),
        ).fetchone()
        return _backlog_row(row) if row is not None else None


def list_backlog(*, program_stage: int | None = None) -> list[dict]:
    with _db() as conn:
        if program_stage is None:
            rows = conn.execute(
                "SELECT * FROM backlog_items ORDER BY program_stage IS NULL, program_stage, priority, requirement_id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM backlog_items WHERE program_stage=? "
                "ORDER BY priority, requirement_id",
                (int(program_stage),),
            ).fetchall()
        return [_backlog_row(row) for row in rows]


def set_backlog_progress(requirement_id: str, *, supervisor_status: str,
                         mission_id: int | None = None,
                         note: str | None = None) -> bool:
    status = str(supervisor_status or "").strip().upper()
    if status not in BACKLOG_SUPERVISOR_STATES:
        raise StoreError("Invalid backlog supervisor status: " + repr(supervisor_status))
    updates = {"supervisor_status": status}
    if mission_id is not None:
        updates["last_mission_id"] = int(mission_id)
    if note is not None:
        updates["note"] = str(note)
    assignments = ", ".join(column + "=?" for column in updates)
    with _db() as conn, conn:
        cursor = conn.execute(
            "UPDATE backlog_items SET " + assignments + " WHERE requirement_id=?",
            (*updates.values(), _require_text(requirement_id, "requirement_id")),
        )
        return cursor.rowcount == 1


# --------------------------------------------------------------------------- #
# Mission evidence ledger
# --------------------------------------------------------------------------- #

def record_evidence(mission_id: int, *, kind: str, record_key: str, payload: dict,
                    queue_id: int | None = None, sha256: str | None = None,
                    path: str | None = None) -> int:
    """Idempotently append one evidence row (same mission/kind/record_key returns existing)."""
    mission = int(mission_id)
    if mission <= 0:
        raise StoreError("mission_id must be positive")
    evidence_kind = _require_text(kind, "kind")
    key = _require_text(record_key, "record_key")
    with _db() as conn:
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO mission_evidence
                        (mission_id, queue_id, kind, record_key, sha256, path,
                         payload_json, created_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (mission, int(queue_id) if queue_id is not None else None,
                     evidence_kind, key, sha256, path, _dumps(payload or {}), _now()),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id FROM mission_evidence WHERE mission_id=? AND kind=? AND record_key=?",
                (mission, evidence_kind, key),
            ).fetchone()
            if row is None:  # pragma: no cover - defensive
                raise
            return int(row["id"])


def list_evidence(mission_id: int) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM mission_evidence WHERE mission_id=? ORDER BY id ASC",
            (int(mission_id),),
        ).fetchall()
        return [_decode(row, {"payload_json": "payload"}) for row in rows]


# --------------------------------------------------------------------------- #
# Approvals for risky operations (delete/network/cloud/install/...)
# --------------------------------------------------------------------------- #

def _approval_row(row: sqlite3.Row) -> dict:
    data = _decode(row, {"scope_json": "scope"})
    scope = data.get("scope")
    if isinstance(scope, dict):
        data["requested_by"] = scope.get("_requested_by")
        data["decision_reason"] = scope.get("_decision_reason")
    return data


def create_approval(project_id: int, *, action: str, scope: dict, reason: str,
                    mission_id: int | None = None, requested_by: str = "system",
                    expires_at: str | None = None) -> int:
    action_text = _require_text(action, "action").lower()
    if action_text not in APPROVAL_ACTIONS:
        raise StoreError("Unsupported approval action: " + repr(action))
    request_scope = dict(scope or {})
    request_scope["_requested_by"] = _require_text(requested_by, "requested_by")
    with _db() as conn, conn:
        cursor = conn.execute(
            """
            INSERT INTO approvals
                (project_id, mission_id, action, scope_json, reason, status,
                 requested_at, expires_at)
            VALUES (?,?,?,?,?,'pending',?,?)
            """,
            (int(project_id), int(mission_id) if mission_id is not None else None,
             action_text, _dumps(request_scope), str(reason or ""), _now(),
             str(expires_at) if expires_at else None),
        )
        return int(cursor.lastrowid)


def create_flow_approval(project_id: int, *, flow_id: str, method_name: str,
                         action: str, reason: str = "", mission_id: int | None = None,
                         queue_id: int | None = None,
                         supervisor_run_id: int | None = None,
                         requested_by: str = "flow", ttl_s: int | None = None) -> int:
    """Create a HITL approval linked to a Flow (durable; no model involvement)."""
    from datetime import datetime, timedelta

    expires_at = None
    if ttl_s is not None:
        expires_at = (datetime.now() + timedelta(seconds=int(ttl_s))).isoformat(timespec="seconds")
    scope = {
        "flow_id": _require_text(flow_id, "flow_id"),
        "method": str(method_name or ""),
        "queue_id": int(queue_id) if queue_id is not None else None,
        "supervisor_run_id": int(supervisor_run_id) if supervisor_run_id is not None else None,
    }
    return create_approval(
        int(project_id), action=action, scope=scope, reason=reason,
        mission_id=mission_id, requested_by=requested_by, expires_at=expires_at,
    )


def get_approval_by_flow(flow_id: str) -> dict | None:
    rows = list_approvals_for_flow(flow_id)
    return rows[-1] if rows else None


def list_approvals_for_flow(flow_id: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals ORDER BY id ASC"
        ).fetchall()
    result = []
    for row in rows:
        data = _approval_row(row)
        if (data.get("scope") or {}).get("flow_id") == str(flow_id):
            result.append(data)
    return result


def decide_flow_approval(approval_id: int, *, approved: bool, decided_by: str,
                         reason: str = "") -> dict:
    ok = decide_approval(int(approval_id), approved=approved,
                         decided_by=decided_by, reason=reason)
    approval = get_approval(int(approval_id))
    return {"ok": bool(ok), "approval": approval}


def flow_approval_outcome(flow_id: str) -> str:
    approvals = list_approvals_for_flow(flow_id)
    if not approvals:
        return "missing"
    for approval in reversed(approvals):
        status = str(approval.get("status") or "")
        if status in ("approved", "denied", "expired"):
            return status
    return "pending"


def pending_flow_approvals(project_id: int) -> list[dict]:
    return [row for row in pending_approvals(int(project_id))
            if (row.get("scope") or {}).get("flow_id")]


def _expire_stale_approvals(conn: sqlite3.Connection, project_id: int) -> None:
    conn.execute(
        """
        UPDATE approvals SET status='expired', decided_at=?, decided_by='system'
         WHERE project_id=? AND status='pending'
           AND expires_at IS NOT NULL AND expires_at < ?
        """,
        (_now(), int(project_id), _now()),
    )


def decide_approval(approval_id: int, *, approved: bool, decided_by: str,
                    reason: str = "") -> bool:
    decision = "approved" if approved else "denied"
    decision_reason = str(reason or "")
    now = _now()
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT scope_json FROM approvals WHERE id=? AND status='pending'",
            (int(approval_id),),
        ).fetchone()
        if row is None:
            return False
        scope = _loads(row["scope_json"], {})
        if not isinstance(scope, dict):
            scope = {}
        scope["_decision_reason"] = decision_reason
        cursor = conn.execute(
            """
            UPDATE approvals
               SET status=?, decided_at=?, decided_by=?, scope_json=?
             WHERE id=? AND status='pending'
            """,
            (decision, now, _require_text(decided_by, "decided_by"),
             _dumps(scope), int(approval_id)),
        )
        return cursor.rowcount == 1


def get_approval(approval_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM approvals WHERE id=?", (int(approval_id),)
        ).fetchone()
        return _approval_row(row) if row is not None else None


def list_approvals(project_id: int, *, status: str | None = None) -> list[dict]:
    with _db() as conn:
        if status is None:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE project_id=? ORDER BY id ASC",
                (int(project_id),),
            ).fetchall()
        else:
            state = str(status).strip().lower()
            if state not in APPROVAL_STATUSES:
                raise StoreError("Invalid approval status: " + repr(status))
            rows = conn.execute(
                "SELECT * FROM approvals WHERE project_id=? AND status=? ORDER BY id ASC",
                (int(project_id), state),
            ).fetchall()
        return [_approval_row(row) for row in rows]


def pending_approvals(project_id: int) -> list[dict]:
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        _expire_stale_approvals(conn, project_id)
        rows = conn.execute(
            "SELECT * FROM approvals WHERE project_id=? AND status='pending' ORDER BY id ASC",
            (int(project_id),),
        ).fetchall()
        return [_approval_row(row) for row in rows]

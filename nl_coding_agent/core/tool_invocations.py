"""Durable tool-invocation ledger shared by missions, Flows and Chat.

This module records what actually ran, not the catalog of available tools.
Arguments/results are bounded JSON values and are never executed. Native calls
are recorded from CrewAI task messages; validated textual/JSON calls use the
same rows with source ``fallback``; catalog-only exposures use ``available``
only in the transient API response and are not inserted here.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from nl_coding_agent.persistence import database

MAX_JSON_CHARS = 16_000


def _bounded_json(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except Exception:
        text = json.dumps({"_unserializable": type(value).__name__})
    return text[:MAX_JSON_CHARS]


def record_invocation(
    tool_name: str,
    *,
    arguments: Any = None,
    result: Any = None,
    status: str = "completed",
    source: str = "native",
    project_id: int | None = None,
    mission_id: int | None = None,
    session_id: str | None = None,
    role: str | None = None,
    model: str | None = None,
    error: str | None = None,
    duration_ms: float | None = None,
    call_id: str | None = None,
) -> int:
    """Insert one invocation row and return its id. Never raises to callers."""
    if source not in ("native", "fallback", "manual"):
        source = "native"
    if status not in ("requested", "completed", "failed", "denied", "unknown"):
        status = "unknown"
    with database.get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO tool_invocations
               (project_id, mission_id, session_id, role, model, tool_name, source,
                arguments_json, result_json, status, error, duration_ms, call_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                project_id, mission_id, session_id, role, model, str(tool_name or "")[:200],
                source, _bounded_json(arguments), _bounded_json(result), status,
                str(error or "")[:4000] or None, duration_ms, call_id,
            ),
        )
        return int(cur.lastrowid)


def record_many(
    invocations: Iterable[Mapping[str, Any]],
    *,
    project_id: int | None = None,
    mission_id: int | None = None,
    session_id: str | None = None,
    role: str | None = None,
    model: str | None = None,
    source: str = "native",
) -> list[int]:
    ids: list[int] = []
    for item in invocations or ():
        try:
            ids.append(record_invocation(
                str(item.get("tool_name") or item.get("name") or "unknown"),
                arguments=item.get("arguments"),
                result=item.get("result"),
                status=str(item.get("status") or "completed"),
                source=source,
                project_id=project_id,
                mission_id=mission_id,
                session_id=session_id,
                role=role,
                model=model,
                error=item.get("error"),
                duration_ms=item.get("duration_ms"),
                call_id=item.get("call_id"),
            ))
        except Exception:
            # Ledger failure must not corrupt a mission; the event bus still
            # carries the tool result and the caller can surface the warning.
            continue
    return ids


def list_invocations(*, mission_id: int | None = None, project_id: int | None = None,
                     session_id: str | None = None, limit: int = 200) -> list[dict]:
    limit = max(1, min(int(limit), 1000))
    clauses: list[str] = []
    params: list[Any] = []
    if mission_id is not None:
        clauses.append("mission_id = ?")
        params.append(int(mission_id))
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(int(project_id))
    if session_id:
        clauses.append("session_id = ?")
        params.append(str(session_id))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tool_invocations" + where + " ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        for key in ("arguments_json", "result_json"):
            try:
                item[key] = json.loads(item.get(key) or "{}")
            except ValueError:
                pass
        items.append(item)
    return items

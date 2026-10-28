"""Additive SQLite persistence for stage-8 goals and milestones (G1).

This module owns SQL only. Validation, lifecycle transitions, dependency cycles,
decomposition rules and audit events live in nl_coding_agent.core.goals; the
existing missions/tasks tables are reused (never forked) and linked through the
goal_missions table.

Schema creation goes through the normal app database init_db path (additive
CREATE TABLE/INDEX IF NOT EXISTS), so old databases and existing data are
preserved. There is no destructive migration, no goal deletion function and no
mission/task creation or execution here.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, Iterator

from nl_coding_agent.persistence.database import init_db

GOAL_JSON_FIELDS = ("acceptance_criteria", "dependencies", "attachments",
                    "reference_metadata")
GOAL_COLUMNS = (
    "project_id", "title", "objective", "acceptance_criteria_json", "priority",
    "status", "dependencies_json", "template_id", "template_version", "source",
    "origin", "attachments_json", "reference_metadata_json", "created_at",
    "updated_at",
)
GOAL_UPDATABLE = frozenset({
    "title", "objective", "acceptance_criteria", "priority", "dependencies",
    "template_id", "template_version", "source", "origin", "attachments",
    "reference_metadata", "updated_at",
})
MILESTONE_JSON_FIELDS = ("dependencies", "acceptance_criteria", "evidence_refs")
MILESTONE_UPDATABLE = frozenset({
    "title", "description", "priority", "status", "ordering", "dependencies",
    "acceptance_criteria", "evidence_refs", "updated_at",
})


class GoalStoreError(RuntimeError):
    """Raised for persistence-level goal/milestone contract failures."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def _db() -> Iterator:
    conn = init_db()
    try:
        yield conn
    finally:
        conn.close()


def _json_load_list(value) -> list:
    if isinstance(value, list):
        return list(value)
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _json_load_dict(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _goal_from_row(row) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["acceptance_criteria"] = _json_load_list(data.pop("acceptance_criteria_json", "[]"))
    data["dependencies"] = _json_load_list(data.pop("dependencies_json", "[]"))
    data["attachments"] = _json_load_list(data.pop("attachments_json", "[]"))
    data["reference_metadata"] = _json_load_dict(data.pop("reference_metadata_json", "{}"))
    data["priority_rank"] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(
        str(data.get("priority")), 9)
    return data


def _milestone_from_row(row) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["dependencies"] = _json_load_list(data.pop("dependencies_json", "[]"))
    data["acceptance_criteria"] = _json_load_list(
        data.pop("acceptance_criteria_json", "[]"))
    data["evidence_refs"] = _json_load_list(data.pop("evidence_refs_json", "[]"))
    data["priority_rank"] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(
        str(data.get("priority")), 9)
    return data


def ensure_schema() -> tuple[str, ...]:
    """Ensure the additive goal schema exists through the app database."""
    conn = init_db()
    try:
        return tuple(sorted(
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                "('goals','milestones','goal_missions')")))
    finally:
        conn.close()


# ------------------------------------------------------------------ goals
def create_goal(project_id: int | None, title: str, objective: str, *,
                acceptance_criteria: Iterable[str] = (), priority: str = "P1",
                status: str = "planned", dependencies: Iterable[int] = (),
                template_id: str | None = None, template_version: str | None = None,
                source: str = "", origin: str = "user",
                attachments: Iterable = (), reference_metadata: dict | None = None,
                created_at: str | None = None) -> int:
    now = created_at or _now()
    with _db() as conn, conn:
        cursor = conn.execute(
            "INSERT INTO goals (project_id, title, objective, acceptance_criteria_json, "
            "priority, status, dependencies_json, template_id, template_version, source, "
            "origin, attachments_json, reference_metadata_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(project_id) if project_id is not None else None, str(title),
             str(objective), _json_dump(list(acceptance_criteria)), str(priority),
             str(status), _json_dump(sorted({int(item) for item in dependencies})),
             template_id, template_version, str(source or ""), str(origin or "user"),
             _json_dump(list(attachments)), _json_dump(reference_metadata or {}),
             now, now))
        return int(cursor.lastrowid)


def get_goal(goal_id: int) -> dict | None:
    with _db() as conn:
        return _goal_from_row(conn.execute("SELECT * FROM goals WHERE id=?",
                                           (int(goal_id),)).fetchone())


def list_goals(*, project_id: int | None = None, status: str | None = None,
               limit: int = 200, offset: int = 0) -> list[dict]:
    clauses, params = [], []
    if project_id is not None:
        clauses.append("project_id=?")
        params.append(int(project_id))
    if status is not None:
        clauses.append("status=?")
        params.append(str(status))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = ("SELECT * FROM goals" + where +
           " ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 "
           "WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 9 END, id ASC LIMIT ? OFFSET ?")
    params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
    with _db() as conn:
        return [_goal_from_row(row) for row in conn.execute(sql, params).fetchall()]


def update_goal(goal_id: int, fields: dict) -> dict | None:
    unknown = sorted(set(fields) - GOAL_UPDATABLE)
    if unknown:
        raise GoalStoreError("unknown goal fields: " + ", ".join(unknown))
    if not fields:
        return get_goal(goal_id)
    columns, values = [], []
    for name, value in fields.items():
        if name in ("acceptance_criteria", "attachments"):
            columns.append(name + "_json")
            values.append(_json_dump(list(value or ())))
        elif name == "reference_metadata":
            columns.append("reference_metadata_json")
            values.append(_json_dump(dict(value or {})))
        elif name == "dependencies":
            columns.append("dependencies_json")
            values.append(_json_dump(sorted({int(item) for item in value or ()})))
        else:
            columns.append(name)
            values.append(value)
    if "updated_at" not in fields:
        columns.append("updated_at")
        values.append(_now())
    values.append(int(goal_id))
    with _db() as conn, conn:
        conn.execute("UPDATE goals SET " + ", ".join(c + "=?" for c in columns)
                     + " WHERE id=?", values)
    return get_goal(goal_id)


def set_goal_status(goal_id: int, status: str) -> dict | None:
    with _db() as conn, conn:
        conn.execute("UPDATE goals SET status=?, updated_at=? WHERE id=?",
                     (str(status), _now(), int(goal_id)))
    return get_goal(goal_id)


# -------------------------------------------------------------- milestones
def enumerate_goal_ids() -> list[int]:
    with _db() as conn:
        return [int(row["id"]) for row in conn.execute("SELECT id FROM goals")]


def next_milestone_order(goal_id: int) -> int:
    with _db() as conn:
        row = conn.execute("SELECT MAX(ordering) AS max_order FROM milestones "
                           "WHERE goal_id=?", (int(goal_id),)).fetchone()
        current = int(row["max_order"]) if row and row["max_order"] is not None else -1
        return current + 1


def create_milestone(goal_id: int, title: str, *, description: str = "",
                     priority: str = "P1", status: str = "pending",
                     ordering: int | None = None,
                     dependencies: Iterable[int] = (),
                     acceptance_criteria: Iterable[str] = (),
                     evidence_refs: Iterable = (), created_at: str | None = None) -> int:
    now = created_at or _now()
    order = next_milestone_order(goal_id) if ordering is None else int(ordering)
    with _db() as conn, conn:
        cursor = conn.execute(
            "INSERT INTO milestones (goal_id, title, description, priority, status, "
            "ordering, dependencies_json, acceptance_criteria_json, evidence_refs_json, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (int(goal_id), str(title), str(description or ""), str(priority),
             str(status), order, _json_dump(sorted({int(item) for item in dependencies})),
             _json_dump(list(acceptance_criteria)), _json_dump(list(evidence_refs)),
             now, now))
        return int(cursor.lastrowid)


def create_milestones_bulk(goal_id: int, specs: list[dict]) -> list[dict]:
    """Insert already-validated specifications atomically, preserving list order."""
    created_at = _now()
    with _db() as conn, conn:
        ids = []
        for spec in specs:
            cursor = conn.execute(
                "INSERT INTO milestones (goal_id, title, description, priority, status, "
                "ordering, dependencies_json, acceptance_criteria_json, "
                "evidence_refs_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (int(goal_id), str(spec["title"]), str(spec.get("description") or ""),
                 str(spec.get("priority") or "P1"), str(spec.get("status") or "pending"),
                 int(spec["ordering"]),
                 _json_dump(sorted({int(item) for item in spec.get("dependencies") or ()})),
                 _json_dump(list(spec.get("acceptance_criteria") or ())),
                 _json_dump(list(spec.get("evidence_refs") or ())), created_at, created_at))
            ids.append(int(cursor.lastrowid))
    return [get_milestone(mid) for mid in ids]


def get_milestone(milestone_id: int) -> dict | None:
    with _db() as conn:
        return _milestone_from_row(conn.execute(
            "SELECT * FROM milestones WHERE id=?", (int(milestone_id),)).fetchone())


def list_milestones(goal_id: int, *, status: str | None = None) -> list[dict]:
    clauses = ["goal_id=?"]
    params: list = [int(goal_id)]
    if status is not None:
        clauses.append("status=?")
        params.append(str(status))
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM milestones WHERE " + " AND ".join(clauses)
            + " ORDER BY ordering ASC, id ASC", params).fetchall()
        return [_milestone_from_row(row) for row in rows]


def update_milestone(milestone_id: int, fields: dict) -> dict | None:
    unknown = sorted(set(fields) - MILESTONE_UPDATABLE)
    if unknown:
        raise GoalStoreError("unknown milestone fields: " + ", ".join(unknown))
    if not fields:
        return get_milestone(milestone_id)
    columns, values = [], []
    for name, value in fields.items():
        if name in MILESTONE_JSON_FIELDS:
            columns.append(name + "_json")
            if name == "dependencies":
                values.append(_json_dump(sorted({int(item) for item in value or ()})))
            else:
                values.append(_json_dump(list(value or ())))
        else:
            columns.append(name)
            values.append(value)
    if "updated_at" not in fields:
        columns.append("updated_at")
        values.append(_now())
    values.append(int(milestone_id))
    with _db() as conn, conn:
        conn.execute("UPDATE milestones SET " + ", ".join(c + "=?" for c in columns)
                     + " WHERE id=?", values)
    return get_milestone(milestone_id)


def set_milestone_status(milestone_id: int, status: str) -> dict | None:
    with _db() as conn, conn:
        conn.execute("UPDATE milestones SET status=?, updated_at=? WHERE id=?",
                     (str(status), _now(), int(milestone_id)))
    return get_milestone(milestone_id)


def delete_milestone(milestone_id: int) -> bool:
    with _db() as conn, conn:
        cursor = conn.execute("DELETE FROM milestones WHERE id=?",
                              (int(milestone_id),))
        return cursor.rowcount > 0


def milestones_depending_on(milestone_id: int) -> list[dict]:
    target = int(milestone_id)
    with _db() as conn:
        rows = conn.execute("SELECT * FROM milestones").fetchall()
    result = []
    for row in rows:
        item = _milestone_from_row(row)
        if target in item["dependencies"]:
            result.append(item)
    return result


# ----------------------------------------------------------- mission links
def mission_exists(mission_id: int) -> bool:
    with _db() as conn:
        return conn.execute("SELECT 1 FROM missions WHERE id=?",
                            (int(mission_id),)).fetchone() is not None


def link_mission(goal_id: int, mission_id: int, *,
                 milestone_id: int | None = None, role: str = "primary") -> int:
    now = _now()
    with _db() as conn, conn:
        row = conn.execute(
            "SELECT id FROM goal_missions WHERE goal_id=? AND milestone_id IS ? "
            "AND mission_id=?", (int(goal_id), milestone_id, int(mission_id))).fetchone()
        if row is not None:
            conn.execute("UPDATE goal_missions SET role=? WHERE id=?",
                         (str(role), int(row["id"])))
            return int(row["id"])
        cursor = conn.execute(
            "INSERT INTO goal_missions (goal_id, milestone_id, mission_id, role, "
            "created_at) VALUES (?,?,?,?,?)",
            (int(goal_id), milestone_id, int(mission_id), str(role), now))
        return int(cursor.lastrowid)


def list_goal_missions(goal_id: int) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM goal_missions WHERE goal_id=? ORDER BY id ASC",
            (int(goal_id),)).fetchall()
        return [dict(row) for row in rows]


def counts() -> dict:
    with _db() as conn:
        return {
            "goals": int(conn.execute("SELECT COUNT(1) FROM goals").fetchone()[0]),
            "milestones": int(conn.execute("SELECT COUNT(1) FROM milestones").fetchone()[0]),
            "goal_missions": int(conn.execute(
                "SELECT COUNT(1) FROM goal_missions").fetchone()[0]),
        }

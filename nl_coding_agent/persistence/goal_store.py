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
    "acceptance_criteria", "evidence_refs", "risk", "validation_strategy",
    "mission_intent", "updated_at",
})
PLAN_VERSION_JSON_FIELDS = ("milestones", "evidence_refs", "diff")


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


def create_goal_with_milestones(goal: dict, specs: list[dict]) -> int:
    """Persist a validated imported goal and its dependencies in one transaction."""
    now = _now()
    with _db() as conn, conn:
        cursor = conn.execute(
            "INSERT INTO goals (project_id,title,objective,acceptance_criteria_json,"
            "priority,status,dependencies_json,source,origin,attachments_json,"
            "reference_metadata_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (goal["project_id"], goal["title"], goal["objective"],
             _json_dump(goal["acceptance_criteria"]), "P1", "planned", "[]",
             "document_plan", "import", "[]", _json_dump(goal["reference_metadata"]), now, now))
        goal_id = int(cursor.lastrowid)
        by_title = {}
        for order, spec in enumerate(specs):
            cursor = conn.execute(
                "INSERT INTO milestones (goal_id,title,description,priority,status,ordering,"
                "dependencies_json,acceptance_criteria_json,evidence_refs_json,risk,"
                "validation_strategy,mission_intent,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (goal_id, spec["title"], spec["description"], spec["priority"], "pending", order,
                 "[]", _json_dump(spec["acceptance_criteria"]), _json_dump(spec["evidence_refs"]),
                 spec["risk"], spec["validation_strategy"], spec["mission_intent"], now, now))
            by_title[spec["title"]] = int(cursor.lastrowid)
        for spec in specs:
            conn.execute("UPDATE milestones SET dependencies_json=? WHERE id=?",
                         (_json_dump([by_title[title] for title in spec["dependency_titles"]]),
                          by_title[spec["title"]]))
        return goal_id


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
                     evidence_refs: Iterable = (), risk: str = "",
                     validation_strategy: str = "", mission_intent: str = "",
                     created_at: str | None = None) -> int:
    now = created_at or _now()
    order = next_milestone_order(goal_id) if ordering is None else int(ordering)
    with _db() as conn, conn:
        cursor = conn.execute(
            "INSERT INTO milestones (goal_id, title, description, priority, status, "
            "ordering, dependencies_json, acceptance_criteria_json, evidence_refs_json, "
            "risk, validation_strategy, mission_intent, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(goal_id), str(title), str(description or ""), str(priority),
             str(status), order, _json_dump(sorted({int(item) for item in dependencies})),
             _json_dump(list(acceptance_criteria)), _json_dump(list(evidence_refs)),
             str(risk or ""), str(validation_strategy or ""),
             str(mission_intent or ""), now, now))
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
                "evidence_refs_json, risk, validation_strategy, mission_intent, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (int(goal_id), str(spec["title"]), str(spec.get("description") or ""),
                 str(spec.get("priority") or "P1"), str(spec.get("status") or "pending"),
                 int(spec["ordering"]),
                 _json_dump(sorted({int(item) for item in spec.get("dependencies") or ()})),
                 _json_dump(list(spec.get("acceptance_criteria") or ())),
                 _json_dump(list(spec.get("evidence_refs") or ())),
                 str(spec.get("risk") or ""),
                 str(spec.get("validation_strategy") or ""),
                 str(spec.get("mission_intent") or ""), created_at, created_at))
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


# ------------------------------------------------------ plan versions (G6)
def next_plan_version(goal_id: int) -> int:
    with _db() as conn:
        row = conn.execute("SELECT MAX(version) AS value FROM goal_plan_versions "
                           "WHERE goal_id=?", (int(goal_id),)).fetchone()
        return (int(row["value"]) if row and row["value"] is not None else 0) + 1


def create_plan_version(goal_id: int, version: int, objective_snapshot: str,
                        milestones: list, rationale: str, trigger: str,
                        evidence_refs: list, diff: dict, *,
                        supersedes: int | None = None,
                        is_current: bool = True,
                        created_at: str | None = None) -> dict:
    now = created_at or _now()
    with _db() as conn, conn:
        if is_current:
            conn.execute("UPDATE goal_plan_versions SET is_current=0 WHERE goal_id=?",
                         (int(goal_id),))
        cursor = conn.execute(
            "INSERT INTO goal_plan_versions (goal_id, version, objective_snapshot, "
            "milestones_json, rationale, trigger, evidence_refs_json, diff_json, "
            "supersedes, is_current, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (int(goal_id), int(version), str(objective_snapshot),
             _json_dump(list(milestones)), str(rationale), str(trigger),
             _json_dump(list(evidence_refs)), _json_dump(dict(diff)),
             int(supersedes) if supersedes is not None else None,
             1 if is_current else 0, now))
        version_id = int(cursor.lastrowid)
    return get_plan_version(goal_id, version)


def _plan_version_from_row(row) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    for column, key in (("milestones_json", "milestones"),
                        ("evidence_refs_json", "evidence_refs"),
                        ("diff_json", "diff")):
        raw = data.pop(column, "[]" if key != "diff" else "{}")
        try:
            data[key] = json.loads(raw)
        except (TypeError, ValueError):
            data[key] = [] if key != "diff" else {}
    data["is_current"] = bool(data.get("is_current"))
    data["approved"] = bool(data.get("approved"))
    data["approval_status"] = "approved" if data.get("approved") else "pending"
    return data


def get_plan_version(goal_id: int, version: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM goal_plan_versions WHERE goal_id=? AND version=?",
            (int(goal_id), int(version))).fetchone()
        return _plan_version_from_row(row)


def list_plan_versions(goal_id: int, *, limit: int = 100,
                       current_only: bool = False) -> list[dict]:
    clause = " AND is_current=1" if current_only else ""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM goal_plan_versions WHERE goal_id=?" + clause
            + " ORDER BY version DESC LIMIT ?",
            (int(goal_id), max(1, min(int(limit), 500)))).fetchall()
        return [_plan_version_from_row(row) for row in rows]


def get_current_plan_version(goal_id: int) -> dict | None:
    rows = list_plan_versions(goal_id, limit=1, current_only=True)
    return rows[0] if rows else None


def approve_plan_version(goal_id: int, version: int, *, approved_by: str,
                         approval_note: str = "") -> dict | None:
    """Approve one existing plan version idempotently (never changes goals)."""
    current = get_plan_version(int(goal_id), int(version))
    if current is None:
        return None
    if bool(current.get("approved")):
        return {"already_approved": True, "version": current}
    now = _now()
    with _db() as conn, conn:
        conn.execute(
            "UPDATE goal_plan_versions SET approved=1, approved_at=?, "
            "approved_by=?, approval_note=? WHERE goal_id=? AND version=?",
            (now, str(approved_by or "")[:200], str(approval_note or "")[:4000],
             int(goal_id), int(version)))
    updated = get_plan_version(int(goal_id), int(version))
    return {"already_approved": False, "version": updated}


# ------------------------------------------------------- mission links (G6)
def list_goal_links(goal_id: int) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT gm.id AS link_id, gm.goal_id, gm.milestone_id, gm.mission_id, "
            "gm.role, m.title AS mission_title, m.status AS mission_status, "
            "m.project_id AS mission_project_id "
            "FROM goal_missions gm LEFT JOIN missions m ON m.id=gm.mission_id "
            "WHERE gm.goal_id=? ORDER BY gm.id ASC", (int(goal_id),)).fetchall()
        return [dict(row) for row in rows]



# ---------------------------------------------- linked work inspection (G8)
def list_linked_mission_tasks(goal_id: int) -> dict:
    links = list_goal_links(goal_id)
    missions: dict[int, dict] = {}
    for link in links:
        mission_id = link.get("mission_id")
        if mission_id is None:
            continue
        mission_id = int(mission_id)
        mission = missions.setdefault(mission_id, {
            "mission_id": mission_id,
            "title": link.get("mission_title"),
            "status": link.get("mission_status"),
            "roles": [], "tasks": []})
        role = str(link.get("role") or "primary")
        if role not in mission["roles"]:
            mission["roles"].append(role)
    mission_ids = sorted(missions)
    tasks: list[dict] = []
    if mission_ids:
        placeholders = ",".join("?" for _ in mission_ids)
        with _db() as conn:
            rows = conn.execute(
                "SELECT id, mission_id, title, status, agent_role, depends_on "
                "FROM tasks WHERE mission_id IN (" + placeholders + ") "
                "ORDER BY mission_id ASC, id ASC", mission_ids).fetchall()
        for row in rows:
            item = dict(row)
            item["depends_on"] = _json_load_list(item.get("depends_on"))
            tasks.append(item)
            mission = missions.get(int(item["mission_id"]))
            if mission is not None:
                mission["tasks"].append(item)
    return {"linked": bool(missions), "missions": list(missions.values()),
            "tasks": tasks}


def list_linked_queue_entries(goal_id: int) -> dict:
    links = list_goal_links(goal_id)
    mission_ids = sorted({int(link["mission_id"]) for link in links
                          if link.get("mission_id") is not None})
    entries: list[dict] = []
    if mission_ids:
        placeholders = ",".join("?" for _ in mission_ids)
        with _db() as conn:
            rows = conn.execute(
                "SELECT id, project_id, requirement_id, mission_id, state, priority, "
                "attempts, max_attempts, lease_owner, claimed_at, scheduled_at, "
                "finished_at, failure_class, created_at, updated_at "
                "FROM mission_queue WHERE mission_id IN (" + placeholders + ") "
                "ORDER BY id ASC", mission_ids).fetchall()
        entries = [dict(row) for row in rows]
    return {"linked": bool(mission_ids), "mission_ids": mission_ids,
            "entries": entries}


def list_linked_active_work(goal_id: int) -> dict:
    links = list_goal_links(goal_id)
    mission_ids = sorted({int(link["mission_id"]) for link in links
                          if link.get("mission_id") is not None})
    assigned: list[dict] = []
    if mission_ids:
        placeholders = ",".join("?" for _ in mission_ids)
        with _db() as conn:
            rows = conn.execute(
                "SELECT id, mission_id, title, status, agent_role, depends_on "
                "FROM tasks WHERE mission_id IN (" + placeholders + ") "
                "AND TRIM(COALESCE(agent_role, '')) != '' "
                "ORDER BY mission_id ASC, id ASC", mission_ids).fetchall()
        for row in rows:
            item = dict(row)
            item["depends_on"] = _json_load_list(item.get("depends_on"))
            assigned.append(item)
    # Supervisor runs have no mission_id; scope by the goal/mission project where
    # available. If no project scope exists, return an explicit no-scope result.
    project_ids: list[int] = []
    goal = get_goal(int(goal_id))
    if goal and goal.get("project_id") is not None:
        project_ids.append(int(goal["project_id"]))
    if mission_ids:
        placeholders = ",".join("?" for _ in mission_ids)
        with _db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project_id FROM missions WHERE id IN ("
                + placeholders + ") AND project_id IS NOT NULL", mission_ids).fetchall()
        project_ids.extend(int(row["project_id"]) for row in rows)
    project_ids = sorted(set(project_ids))
    runs: list[dict] = []
    if project_ids:
        placeholders = ",".join("?" for _ in project_ids)
        with _db() as conn:
            rows = conn.execute(
                "SELECT id, project_id, mode, status, owner_id, owner_pid, "
                "heartbeat_at, started_at, finished_at "
                "FROM supervisor_runs WHERE project_id IN (" + placeholders + ") "
                "ORDER BY id DESC", project_ids).fetchall()
        runs = [dict(row) for row in rows]
    return {"linked": bool(mission_ids), "mission_ids": mission_ids,
            "assigned_tasks": assigned, "supervisor_runs": runs,
            "scope_available": bool(project_ids)}


def counts() -> dict:
    with _db() as conn:
        return {
            "goals": int(conn.execute("SELECT COUNT(1) FROM goals").fetchone()[0]),
            "milestones": int(conn.execute("SELECT COUNT(1) FROM milestones").fetchone()[0]),
            "goal_missions": int(conn.execute(
                "SELECT COUNT(1) FROM goal_missions").fetchone()[0]),
            "goal_plan_versions": int(conn.execute(
                "SELECT COUNT(1) FROM goal_plan_versions").fetchone()[0]),
        }

"""Persistent missions, task tracking, handoffs, and verification records."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from nl_coding_agent.persistence.database import init_db


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def _db() -> Iterator:
    conn = init_db()
    try:
        yield conn
    finally:
        conn.close()


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


# Mirrors nl_coding_agent.core.promotion.HARNESS_VERSION without importing it
# (persistence must not depend on orchestration modules).
HARNESS_VERSION = 2


def create_mission(
    project_id: int | None,
    title: str,
    goal: str,
    *,
    harness_version: int = HARNESS_VERSION,
    requirement_id: str | None = None,
    supervisor_run_id: int | None = None,
) -> int:
    """Create a new mission record in SQLite and return its ID.

    Stage-3 supervisor fields (requirement_id / supervisor_run_id) are additive and
    optional; existing callers keep the previous behaviour.
    """
    with _db() as conn, conn:
        return insert_mission(conn, project_id, title, goal,
                              harness_version=harness_version,
                              requirement_id=requirement_id,
                              supervisor_run_id=supervisor_run_id)


def insert_mission(conn, project_id, title, goal, *, harness_version=HARNESS_VERSION,
                   requirement_id=None, supervisor_run_id=None) -> int:
    """Insert inside the caller's transaction (queue/link creation must be atomic)."""
    now = _now()
    cur = conn.execute(
        "INSERT INTO missions (project_id, title, goal, status, created_at, updated_at, "
        "harness_version, requirement_id, supervisor_run_id) "
        "VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
        (project_id, title, goal, now, now, int(harness_version),
         str(requirement_id) if requirement_id else None,
         int(supervisor_run_id) if supervisor_run_id is not None else None))
    return int(cur.lastrowid)


def set_mission_staging(mission_id: int, staging_dir: str | None) -> None:
    """Record the staging directory owned by a mission (NULL clears it)."""
    with _db() as conn, conn:
        conn.execute(
            "UPDATE missions SET staging_dir=?, updated_at=? WHERE id=?",
            (staging_dir, _now(), mission_id),
        )


def set_promotion_status(mission_id: int, promotion_status: str | None) -> None:
    """Record the durable candidate-promotion state of a mission."""
    with _db() as conn, conn:
        conn.execute(
            "UPDATE missions SET promotion_status=?, updated_at=? WHERE id=?",
            (promotion_status, _now(), mission_id),
        )


def set_mission_flow(mission_id: int, flow_id: str | None) -> None:
    """Link a mission to its durable CrewAI Flow run (NULL clears the link)."""
    with _db() as conn, conn:
        conn.execute(
            "UPDATE missions SET flow_id=?, updated_at=? WHERE id=?",
            (str(flow_id) if flow_id else None, _now(), mission_id),
        )


def get_mission_flow(mission_id: int) -> str | None:
    """Return the linked Flow id for a mission, or None for sequential missions."""
    with _db() as conn:
        row = conn.execute(
            "SELECT flow_id FROM missions WHERE id=?", (int(mission_id),)
        ).fetchone()
        return str(row["flow_id"]) if row and row["flow_id"] else None


def find_mission_by_flow_id(flow_id: str) -> dict | None:
    """Find the mission linked to a durable Flow run id."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM missions WHERE flow_id=? ORDER BY id DESC LIMIT 1",
            (str(flow_id),),
        ).fetchone()
        return dict(row) if row else None


def find_mission_by_staging_dir(staging_dir: str) -> dict | None:
    """Find the mission owning a staging directory (used by promotion preflight)."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM missions WHERE staging_dir=? ORDER BY id DESC LIMIT 1",
            (staging_dir,),
        ).fetchone()
        return dict(row) if row else None


def get_mission(mission_id: int) -> dict | None:
    """Fetch mission details by ID."""
    with _db() as conn:
        row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
        return dict(row) if row else None


def list_missions_by_requirement(requirement_id: str) -> list[dict]:
    """Return every mission linked to one indexed-backlog requirement (newest first)."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM missions WHERE requirement_id=? ORDER BY id DESC",
            (str(requirement_id),),
        ).fetchall()
        return [dict(row) for row in rows]


def get_active_mission_for_requirement(requirement_id: str) -> dict | None:
    """Return the newest resumable mission for a requirement (adoption on reconcile)."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM missions WHERE requirement_id=? "
            "AND status IN ('pending','running','interrupted') "
            "ORDER BY id DESC LIMIT 1",
            (str(requirement_id),),
        ).fetchone()
        return dict(row) if row else None


def list_missions(project_id: int | None = None) -> list[dict]:
    """List missions, optionally filtered by project_id."""
    with _db() as conn:
        if project_id is not None:
            rows = conn.execute(
                "SELECT * FROM missions WHERE project_id=? ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM missions ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def archive_mission(mission_id: int, *, project_id: int | None = None) -> dict:
    """Archive one non-running mission without deleting data."""
    return archive_missions([mission_id], project_id=project_id)[0]


def archive_missions(mission_ids, *, project_id: int | None = None) -> list[dict]:
    """Atomically archive selected missions that are not currently running."""
    ids = list(dict.fromkeys(int(value) for value in (mission_ids or [])))
    if not ids or any(value <= 0 for value in ids):
        raise ValueError("Select at least one valid mission")
    placeholders = ",".join("?" for _ in ids)
    now = _now()
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            f"SELECT * FROM missions WHERE id IN ({placeholders})", ids
        ).fetchall()
        if len(rows) != len(ids):
            raise ValueError("One or more selected missions no longer exist")
        missions = [dict(row) for row in rows]
        if project_id is not None and any(
                item.get("project_id") != project_id for item in missions):
            raise ValueError("A selected mission belongs to another project")
        running = [item["id"] for item in missions if item.get("status") == "running"]
        if running:
            raise ValueError(
                "Stop running missions before archiving them: "
                + ", ".join(str(value) for value in running)
            )
        conn.execute(
            f"UPDATE missions SET archived_at=?, updated_at=? "
            f"WHERE id IN ({placeholders})",
            [now, now, *ids],
        )
    return missions


def unarchive_mission(mission_id: int) -> dict:
    with _db() as conn, conn:
        conn.execute("UPDATE missions SET archived_at=NULL, updated_at=? WHERE id=?",
                     (_now(), int(mission_id)))
    return get_mission(mission_id) or {}


def delete_mission(mission_id: int, *, project_id: int | None = None) -> dict:
    """Delete one mission and its dependent records, without touching project files."""
    return delete_missions([mission_id], project_id=project_id)[0]


def delete_missions(mission_ids, *, project_id: int | None = None) -> list[dict]:
    """Atomically delete selected non-running missions and detach retained evidence."""
    ids = list(dict.fromkeys(int(value) for value in (mission_ids or [])))
    if not ids or any(value <= 0 for value in ids):
        raise ValueError("Select at least one valid mission")
    placeholders = ",".join("?" for _ in ids)
    now = _now()
    with _db() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            f"SELECT * FROM missions WHERE id IN ({placeholders})", ids
        ).fetchall()
        if len(rows) != len(ids):
            raise ValueError("One or more selected missions no longer exist")
        missions = [dict(row) for row in rows]
        if project_id is not None and any(
                item.get("project_id") != project_id for item in missions):
            raise ValueError("A selected mission belongs to another project")
        running = [item["id"] for item in missions if item.get("status") == "running"]
        if running:
            raise ValueError(
                "Stop running missions before deleting them: "
                + ", ".join(str(value) for value in running)
            )
        linked_milestones = conn.execute(
            f"SELECT DISTINCT goal_id, milestone_id FROM goal_missions "
            f"WHERE mission_id IN ({placeholders}) AND milestone_id IS NOT NULL",
            ids,
        ).fetchall()

        conn.execute(
            f"UPDATE mission_queue SET mission_id=NULL WHERE mission_id IN ({placeholders})",
            ids,
        )
        conn.execute(
            f"UPDATE backlog_items SET last_mission_id=NULL "
            f"WHERE last_mission_id IN ({placeholders})", ids,
        )
        conn.execute(
            f"UPDATE approvals SET mission_id=NULL WHERE mission_id IN ({placeholders})",
            ids,
        )
        conn.execute(
            f"UPDATE events SET mission_id=NULL WHERE mission_id IN ({placeholders})",
            ids,
        )
        conn.execute(
            f"UPDATE flow_runs SET mission_id=NULL WHERE mission_id IN ({placeholders})",
            ids,
        )
        conn.execute(
            f"UPDATE mission_attachments SET mission_id=NULL "
            f"WHERE mission_id IN ({placeholders})", ids,
        )
        conn.execute(
            f"UPDATE research_finding_attachments SET revoked_at=COALESCE(revoked_at, ?) "
            f"WHERE mission_id IN ({placeholders})", [now, *ids],
        )
        for mission_id in ids:
            conn.execute(
                "DELETE FROM app_settings WHERE key IN (?, ?)",
                ("mission.stop." + str(mission_id), "mission.steer." + str(mission_id)),
            )
        conn.execute(
            f"DELETE FROM missions WHERE id IN ({placeholders})", ids,
        )

        affected_goals: set[int] = set()
        for link in linked_milestones:
            milestone_id = int(link["milestone_id"])
            remaining = conn.execute(
                "SELECT m.status FROM goal_missions gm "
                "JOIN missions m ON m.id=gm.mission_id WHERE gm.milestone_id=?",
                (milestone_id,),
            ).fetchall()
            if not remaining:
                conn.execute(
                    "UPDATE milestones SET status='pending', evidence_refs_json='[]', "
                    "updated_at=? WHERE id=?",
                    (now, milestone_id),
                )
            else:
                statuses = [str(row["status"] or "") for row in remaining]
                if all(status == "completed" for status in statuses):
                    milestone_status = "completed"
                elif any(status == "running" for status in statuses):
                    milestone_status = "in_progress"
                elif any(status in ("blocked", "failed") for status in statuses):
                    milestone_status = "blocked"
                else:
                    milestone_status = "pending"
                conn.execute(
                    "UPDATE milestones SET status=?, updated_at=? WHERE id=?",
                    (milestone_status, now, milestone_id),
                )
            affected_goals.add(int(link["goal_id"]))
        for goal_id in affected_goals:
            goal = conn.execute(
                "SELECT status FROM goals WHERE id=?", (goal_id,)
            ).fetchone()
            incomplete = conn.execute(
                "SELECT 1 FROM milestones WHERE goal_id=? AND status!='completed' LIMIT 1",
                (goal_id,),
            ).fetchone()
            if goal and goal["status"] == "completed" and incomplete:
                conn.execute(
                    "UPDATE goals SET status='active', updated_at=? WHERE id=?",
                    (now, goal_id),
                )
    return missions


def set_mission_project(mission_id: int, project_id: int) -> None:
    with _db() as conn, conn:
        conn.execute(
            "UPDATE missions SET project_id=? WHERE id=?",
            (project_id, mission_id),
        )


def update_mission_status(mission_id: int, status: str) -> None:
    """Update mission status ('pending', 'running', 'completed', 'failed', 'blocked', 'interrupted')."""
    now = _now()
    with _db() as conn, conn:
        conn.execute(
            "UPDATE missions SET status=?, updated_at=?, finished_at=CASE WHEN ? IN ('completed','failed','blocked','interrupted') THEN ? ELSE finished_at END WHERE id=?",
            (status, now, status, now, mission_id),
        )


def mark_mission_started(mission_id: int) -> None:
    now = _now()
    with _db() as conn, conn:
        conn.execute(
            "UPDATE missions SET status='running', started_at=COALESCE(started_at, ?), updated_at=? WHERE id=?",
            (now, now, mission_id),
        )


def increment_resume_count(mission_id: int) -> None:
    with _db() as conn, conn:
        conn.execute(
            "UPDATE missions SET resume_count=resume_count+1, updated_at=? WHERE id=?",
            (_now(), mission_id),
        )


def update_mission_result(
    mission_id: int,
    status: str,
    result_summary: str | None = None,
    review_verdict: str | None = None,
    diff_stat: str | None = None,
    changed_paths: list[str] | None = None,
) -> None:
    now = _now()
    with _db() as conn, conn:
        conn.execute(
            """
            UPDATE missions
               SET status=?,
                   result_summary=COALESCE(?, result_summary),
                   review_verdict=COALESCE(?, review_verdict),
                   diff_stat=COALESCE(?, diff_stat),
                   changed_paths=COALESCE(?, changed_paths),
                   updated_at=?,
                   finished_at=CASE WHEN ? IN ('completed','failed','blocked','interrupted') THEN ? ELSE finished_at END
             WHERE id=?
            """,
            (
                status,
                result_summary,
                review_verdict,
                diff_stat,
                json.dumps(changed_paths) if changed_paths is not None else None,
                now,
                status,
                now,
                mission_id,
            ),
        )


def add_task(
    mission_id: int,
    title: str,
    description: str,
    agent_role: str,
    depends_on: list[int] | None = None,
    write_paths: list[str] | None = None,
) -> int:
    """Add a task with dependency and write-scope links to a mission."""
    now = _now()
    deps_json = json.dumps(depends_on or [])
    writes_json = json.dumps(write_paths or [])
    with _db() as conn, conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (mission_id, title, description, status, agent_role,
                               depends_on, write_paths, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
            """,
            (mission_id, title, description, agent_role, deps_json, writes_json, now, now),
        )
        return cur.lastrowid


def get_task(task_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["depends_on"] = _json_list(d.get("depends_on"))
        d["write_paths"] = _json_list(d.get("write_paths"))
        return d


def get_tasks(mission_id: int) -> list[dict]:
    """Retrieve all tasks for a mission ordered by creation."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE mission_id=? ORDER BY id ASC",
            (mission_id,),
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["depends_on"] = _json_list(d.get("depends_on"))
            d["write_paths"] = _json_list(d.get("write_paths"))
            results.append(d)
        return results


def update_task_status(task_id: int, status: str, error: str | None = None) -> None:
    """Update task status ('pending', 'running', 'completed', 'failed', 'blocked')."""
    now = _now()
    with _db() as conn, conn:
        conn.execute(
            """
            UPDATE tasks
               SET status=?,
                   last_error=COALESCE(?, last_error),
                   updated_at=?,
                   started_at=CASE WHEN ?='running' THEN COALESCE(started_at, ?) ELSE started_at END,
                   finished_at=CASE WHEN ? IN ('completed','failed','blocked') THEN ? ELSE finished_at END
             WHERE id=?
            """,
            (status, error, now, status, now, status, now, task_id),
        )


def reset_interrupted_tasks(mission_id: int) -> list[int]:
    """Reset tasks left in 'running' by a crashed process. Returns reset task ids."""
    now = _now()
    with _db() as conn:
        rows = conn.execute(
            "SELECT id FROM tasks WHERE mission_id=? AND status='running'",
            (mission_id,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            with conn:
                conn.execute(
                    f"UPDATE tasks SET status='pending', updated_at=? WHERE id IN ({','.join('?' for _ in ids)})",
                    (now, *ids),
                )
        return ids


def reset_tasks_from(mission_id: int, task_id: int, *, connection=None) -> list[int]:
    """Reset one task and every later task to pending for an explicit retry."""
    if connection is None:
        with _db() as conn, conn:
            return reset_tasks_from(mission_id, task_id, connection=conn)
    now = _now()
    rows = connection.execute(
        "SELECT id FROM tasks WHERE mission_id=? AND id>=? ORDER BY id",
        (int(mission_id), int(task_id)),
    ).fetchall()
    ids = [int(r["id"]) for r in rows]
    if ids:
        connection.execute(
            "UPDATE tasks SET status='pending', last_error=NULL, "
            "started_at=NULL, finished_at=NULL, updated_at=? "
            f"WHERE id IN ({','.join('?' for _ in ids)})",
            (now, *ids),
        )
    return ids


def record_task_attempt(
    task_id: int,
    status: str,
    output: str = "",
    error: str = "",
    metadata: dict | None = None,
) -> int:
    """Record an execution attempt for a task and bump its attempt counter."""
    now = _now()
    metadata_json = json.dumps(dict(metadata or {}), ensure_ascii=False)
    with _db() as conn, conn:
        cur = conn.execute(
            """
            INSERT INTO task_attempts (task_id, started_at, finished_at, status, output, error,
                                       metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, now, now, status, output, error, metadata_json),
        )
        conn.execute(
            "UPDATE tasks SET attempts=attempts+1, last_error=CASE WHEN ?<>'' THEN ? ELSE last_error END, updated_at=? WHERE id=?",
            (error, error, now, task_id),
        )
        return cur.lastrowid


def get_task_attempts(mission_id: int) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT a.*, t.agent_role, t.title AS task_title
              FROM task_attempts a
              JOIN tasks t ON t.id = a.task_id
             WHERE t.mission_id=?
             ORDER BY a.id ASC
            """,
            (mission_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_attempt(task_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM task_attempts WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None


def record_handoff(
    mission_id: int,
    from_role: str,
    to_role: str,
    summary: str,
    payload: dict | None = None,
) -> int:
    """Record an agent-to-agent handoff in SQLite."""
    now = _now()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with _db() as conn, conn:
        cur = conn.execute(
            """
            INSERT INTO handoffs (mission_id, from_role, to_role, summary, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mission_id, from_role, to_role, summary, payload_json, now),
        )
        return cur.lastrowid


def get_handoffs(mission_id: int) -> list[dict]:
    """Retrieve handoffs for a mission in chronological order."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM handoffs WHERE mission_id=? ORDER BY id ASC",
            (mission_id,),
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"] or "{}")
            except Exception:
                pass
            results.append(d)
        return results


def record_verification_run(
    mission_id: int | None,
    task_id: int | None,
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    passed: bool,
) -> int:
    """Record build/test verification results."""
    now = _now()
    with _db() as conn, conn:
        cur = conn.execute(
            """
            INSERT INTO verification_runs (mission_id, task_id, command, exit_code, stdout, stderr, passed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mission_id, task_id, command, exit_code, stdout, stderr, 1 if passed else 0, now),
        )
        return cur.lastrowid


def get_verification_runs(mission_id: int) -> list[dict]:
    """Retrieve verification runs for a mission."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM verification_runs WHERE mission_id=? ORDER BY id ASC",
            (mission_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def mission_progress(mission_id: int) -> dict:
    """Return task counts used by the GUI progress display."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks WHERE mission_id=? GROUP BY status",
            (mission_id,),
        ).fetchall()
        counts = {r["status"]: r["n"] for r in rows}
        total = sum(counts.values())
        completed = counts.get("completed", 0)
        return {
            "total": total,
            "completed": completed,
            "failed": counts.get("failed", 0),
            "running": counts.get("running", 0),
            "pending": counts.get("pending", 0),
            "percent": round((completed / total) * 100) if total else 0,
        }

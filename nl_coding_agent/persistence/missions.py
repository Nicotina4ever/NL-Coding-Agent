"""Persistent missions, task tracking, handoffs, and verification records."""
from __future__ import annotations

import json
from datetime import datetime
from nl_coding_agent.persistence.database import init_db


def create_mission(project_id: int | None, title: str, goal: str) -> int:
    """Create a new mission record in SQLite and return its ID."""
    conn = init_db()
    now = datetime.now().isoformat()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO missions (project_id, title, goal, status, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (project_id, title, goal, now, now),
        )
        return cur.lastrowid


def get_mission(mission_id: int) -> dict | None:
    """Fetch mission details by ID."""
    conn = init_db()
    row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    return dict(row) if row else None


def list_missions(project_id: int | None = None) -> list[dict]:
    """List missions, optionally filtered by project_id."""
    conn = init_db()
    if project_id is not None:
        rows = conn.execute(
            "SELECT * FROM missions WHERE project_id=? ORDER BY id DESC",
            (project_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM missions ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def update_mission_status(mission_id: int, status: str) -> None:
    """Update mission status ('pending', 'running', 'completed', 'failed', 'blocked')."""
    conn = init_db()
    now = datetime.now().isoformat()
    with conn:
        conn.execute(
            "UPDATE missions SET status=?, updated_at=? WHERE id=?",
            (status, now, mission_id),
        )


def add_task(
    mission_id: int,
    title: str,
    description: str,
    agent_role: str,
    depends_on: list[int] | None = None,
) -> int:
    """Add a task with dependency links to a mission."""
    conn = init_db()
    now = datetime.now().isoformat()
    deps_json = json.dumps(depends_on or [])
    with conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (mission_id, title, description, status, agent_role, depends_on, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (mission_id, title, description, agent_role, deps_json, now, now),
        )
        return cur.lastrowid


def get_tasks(mission_id: int) -> list[dict]:
    """Retrieve all tasks for a mission ordered by creation."""
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE mission_id=? ORDER BY id ASC",
        (mission_id,),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["depends_on"] = json.loads(d["depends_on"] or "[]")
        results.append(d)
    return results


def update_task_status(task_id: int, status: str) -> None:
    """Update task status ('pending', 'running', 'completed', 'failed', 'blocked')."""
    conn = init_db()
    now = datetime.now().isoformat()
    with conn:
        conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (status, now, task_id),
        )


def record_task_attempt(
    task_id: int,
    status: str,
    output: str = "",
    error: str = "",
) -> int:
    """Record an execution attempt for a task."""
    conn = init_db()
    now = datetime.now().isoformat()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO task_attempts (task_id, started_at, finished_at, status, output, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, now, now, status, output, error),
        )
        return cur.lastrowid


def record_handoff(
    mission_id: int,
    from_role: str,
    to_role: str,
    summary: str,
    payload: dict | None = None,
) -> int:
    """Record an agent-to-agent handoff in SQLite."""
    conn = init_db()
    now = datetime.now().isoformat()
    payload_json = json.dumps(payload or {})
    with conn:
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
    conn = init_db()
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
    conn = init_db()
    now = datetime.now().isoformat()
    with conn:
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
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM verification_runs WHERE mission_id=? ORDER BY id ASC",
        (mission_id,),
    ).fetchall()
    return [dict(r) for r in rows]

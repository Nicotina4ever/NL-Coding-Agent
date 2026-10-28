"""Project registry — open, list, remove projects via SQLite."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from nl_coding_agent.persistence.database import get_connection, init_db, log_event
from nl_coding_agent.projects.scanner import scan_project


def _ensure_conn() -> sqlite3.Connection:
    return init_db()


def open_project(root: str | Path) -> dict:
    """
    Register or update a project in the database.
    Runs the scanner and stores facts.
    Returns the project record dict.
    """
    root = Path(root).resolve()
    facts = scan_project(root)
    name = root.name

    conn = _ensure_conn()
    now = datetime.now().isoformat(timespec="seconds")
    metadata = json.dumps({
        "primary_language": facts["primary_language"],
        "frameworks": facts["frameworks"],
        "file_count": facts["file_count"],
    })

    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (name, root, opened_at, last_used, metadata)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(root) DO UPDATE SET
                    last_used = excluded.last_used,
                    metadata  = excluded.metadata
                """,
                (name, str(root), now, now, metadata)
            )
            project_id = cursor.lastrowid or conn.execute(
                "SELECT id FROM projects WHERE root=?", (str(root),)
            ).fetchone()["id"]

            # Upsert project facts
            for key, value in {
                "primary_language": facts["primary_language"],
                "frameworks": json.dumps(facts["frameworks"]),
                "top_build_files": json.dumps(facts["top_build_files"]),
                "doc_files": json.dumps(facts["doc_files"][:50]),
                "file_count": str(facts["file_count"]),
                "languages": json.dumps(facts["languages"]),
            }.items():
                conn.execute(
                    """
                    INSERT INTO project_facts (project_id, key, value, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(project_id, key) DO UPDATE SET value=excluded.value
                    """,
                    (project_id, key, value, now)
                )

            log_event(conn, f"Opened project: {name} at {root}", source="registry")

        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_recent(limit: int = 20) -> list[dict]:
    """Return most recently used projects."""
    conn = _ensure_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY last_used DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_project(project_id: int) -> dict | None:
    conn = _ensure_conn()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_project_facts(project_id: int) -> dict:
    conn = _ensure_conn()
    try:
        rows = conn.execute(
            "SELECT key, value FROM project_facts WHERE project_id=?", (project_id,)
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


def remove_project(project_id: int) -> bool:
    """Remove a project from the registry. Does NOT delete any files."""
    conn = _ensure_conn()
    try:
        with conn:
            cursor = conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            log_event(conn, f"Removed project id={project_id}", source="registry")
        return cursor.rowcount > 0
    finally:
        conn.close()

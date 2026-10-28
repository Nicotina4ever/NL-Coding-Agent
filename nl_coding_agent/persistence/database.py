"""SQLite persistence layer for NL Coding Agent."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "nl_coding_agent.sqlite3"
_LOCK = threading.Lock()


def db_path() -> Path:
    return _DB_PATH


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    p = path or _DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    root        TEXT NOT NULL UNIQUE,
    opened_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_used   TEXT NOT NULL DEFAULT (datetime('now')),
    metadata    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS project_facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, key)
);

CREATE TABLE IF NOT EXISTS model_inventory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    provider    TEXT NOT NULL DEFAULT 'ollama',
    size_gb     REAL,
    loaded      INTEGER NOT NULL DEFAULT 0,
    last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
    metadata    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS missions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    title       TEXT NOT NULL,
    goal        TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id  INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    agent_role  TEXT,
    depends_on  TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    output      TEXT,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL DEFAULT 'system',
    level       TEXT NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL,
    payload     TEXT DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS handoffs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id  INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    from_role   TEXT NOT NULL,
    to_role     TEXT NOT NULL,
    summary     TEXT NOT NULL,
    payload     TEXT DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS verification_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id  INTEGER REFERENCES missions(id) ON DELETE CASCADE,
    task_id     INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    command     TEXT NOT NULL,
    exit_code   INTEGER NOT NULL,
    stdout      TEXT,
    stderr      TEXT,
    passed      INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db(path: Path | None = None) -> sqlite3.Connection:
    """Initialize database, run schema migrations, return connection."""
    conn = get_connection(path)
    with _LOCK:
        with conn:
            for statement in _SCHEMA.split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)
    return conn


def log_event(conn: sqlite3.Connection, message: str, source: str = "system",
              level: str = "info", payload: str = "{}") -> None:
    with conn:
        conn.execute(
            "INSERT INTO events (source, level, message, payload) VALUES (?,?,?,?)",
            (source, level, message, payload)
        )

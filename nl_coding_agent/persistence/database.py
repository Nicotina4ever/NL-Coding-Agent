"""SQLite persistence layer for NL Coding Agent."""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA_ROOT = APP_ROOT / "data"
_DB_PATH = _DEFAULT_DATA_ROOT / "nl_coding_agent.sqlite3"
_LOCK = threading.Lock()


def data_root() -> Path:
    override = os.environ.get("NL_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _DB_PATH.parent


def db_path() -> Path:
    override = os.environ.get("NL_DATA_DIR")
    if override:
        return data_root() / "nl_coding_agent.sqlite3"
    return _DB_PATH


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
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

# Columns added after the first operational baseline.  Migrations are additive
# and idempotent so existing mission history is preserved.
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("missions", "result_summary", "TEXT"),
    ("missions", "review_verdict", "TEXT"),
    ("missions", "diff_stat", "TEXT"),
    ("missions", "changed_paths", "TEXT DEFAULT '[]'"),
    ("missions", "resume_count", "INTEGER NOT NULL DEFAULT 0"),
    ("missions", "started_at", "TEXT"),
    ("missions", "finished_at", "TEXT"),
    ("tasks", "write_paths", "TEXT DEFAULT '[]'"),
    ("tasks", "attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "last_error", "TEXT"),
    ("tasks", "started_at", "TEXT"),
    ("tasks", "finished_at", "TEXT"),
]

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_missions_project ON missions(project_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_mission ON tasks(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_attempts_task ON task_attempts(task_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_handoffs_mission ON handoffs(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_verification_mission ON verification_runs(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(id DESC);
"""


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, column, declaration in _MIGRATIONS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    for statement in _INDEXES.split(";"):
        stmt = statement.strip()
        if stmt:
            conn.execute(stmt)


def init_db(path: Path | None = None) -> sqlite3.Connection:
    """Initialize database, run schema migrations, return connection."""
    conn = get_connection(path)
    with _LOCK:
        with conn:
            for statement in _SCHEMA.split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)
            _apply_migrations(conn)
    return conn


def log_event(conn: sqlite3.Connection, message: str, source: str = "system",
              level: str = "info", payload: str = "{}") -> None:
    with conn:
        conn.execute(
            "INSERT INTO events (source, level, message, payload) VALUES (?,?,?,?)",
            (source, level, message, payload)
        )

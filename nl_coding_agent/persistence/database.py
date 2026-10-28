"""SQLite persistence layer for NL Coding Agent."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
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

CREATE TABLE IF NOT EXISTS supervisor_leases (
    project_id  INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    owner_id    TEXT NOT NULL,
    owner_pid   INTEGER NOT NULL,
    owner_host  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supervisor_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    mode                TEXT NOT NULL,
    status              TEXT NOT NULL,
    owner_id            TEXT,
    owner_pid           INTEGER,
    config_json         TEXT NOT NULL DEFAULT '{}',
    stop_requested      INTEGER NOT NULL DEFAULT 0,
    pause_requested     INTEGER NOT NULL DEFAULT 0,
    missions_completed  INTEGER NOT NULL DEFAULT 0,
    missions_failed     INTEGER NOT NULL DEFAULT 0,
    started_at          TEXT NOT NULL,
    heartbeat_at        TEXT,
    finished_at         TEXT,
    stopped_reason      TEXT
);

CREATE TABLE IF NOT EXISTS mission_queue (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    requirement_id    TEXT,
    mission_id        INTEGER REFERENCES missions(id) ON DELETE SET NULL,
    state             TEXT NOT NULL,
    priority          TEXT NOT NULL DEFAULT 'P1',
    idempotency_key   TEXT NOT NULL,
    claim_token       TEXT,
    lease_owner       TEXT,
    attempts          INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 2,
    budget_json       TEXT NOT NULL DEFAULT '{}',
    goal              TEXT NOT NULL,
    payload_json      TEXT NOT NULL DEFAULT '{}',
    failure_class     TEXT,
    failure_signature TEXT,
    scheduled_at      TEXT,
    claimed_at        TEXT,
    heartbeat_at      TEXT,
    finished_at       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(project_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS backlog_items (
    requirement_id       TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    area                 TEXT,
    priority             TEXT,
    program_stage        INTEGER,
    program_stage_name   TEXT,
    status               TEXT NOT NULL,
    dependencies_json    TEXT NOT NULL DEFAULT '[]',
    acceptance_json      TEXT NOT NULL DEFAULT '[]',
    source_refs_json     TEXT NOT NULL DEFAULT '[]',
    content_hash         TEXT NOT NULL,
    source_fingerprint   TEXT,
    last_synced_at       TEXT NOT NULL,
    supervisor_status    TEXT,
    last_mission_id      INTEGER,
    attempts             INTEGER NOT NULL DEFAULT 0,
    note                 TEXT
);

CREATE TABLE IF NOT EXISTS mission_evidence (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id   INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    queue_id     INTEGER,
    kind         TEXT NOT NULL,
    record_key   TEXT NOT NULL,
    sha256       TEXT,
    path         TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    UNIQUE(mission_id, kind, record_key)
);

CREATE TABLE IF NOT EXISTS approvals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    mission_id   INTEGER,
    action       TEXT NOT NULL,
    scope_json   TEXT NOT NULL DEFAULT '{}',
    reason       TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    requested_at TEXT NOT NULL,
    decided_at   TEXT,
    decided_by   TEXT,
    expires_at   TEXT
);

CREATE TABLE IF NOT EXISTS supervisor_commands (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id       INTEGER,
    command      TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    consumed_at  TEXT
);

CREATE TABLE IF NOT EXISTS machine_leases (
    resource    TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL,
    owner_pid   INTEGER NOT NULL,
    owner_host  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

-- Stage-4 CrewAI Flow state (C4b additive, app-owned SQLite only).
CREATE TABLE IF NOT EXISTS flow_states (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_uuid    TEXT NOT NULL,
    method_name  TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    state_sha256 TEXT NOT NULL,
    state_json   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flow_pending_feedback (
    flow_uuid    TEXT PRIMARY KEY,
    approval_id  INTEGER,
    method_name  TEXT NOT NULL,
    context_json TEXT NOT NULL,
    state_json   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mission_attachments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER,
    mission_id        INTEGER,
    name              TEXT NOT NULL,
    kind              TEXT NOT NULL,
    mime              TEXT,
    size_bytes        INTEGER NOT NULL,
    sha256            TEXT NOT NULL,
    source            TEXT NOT NULL DEFAULT 'upload',
    stored_path       TEXT NOT NULL,
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    text_chars        INTEGER NOT NULL DEFAULT 0,
    extracted_text    TEXT,
    error             TEXT,
    metadata_json     TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flow_runs (
    flow_id           TEXT PRIMARY KEY,
    project_id        INTEGER NOT NULL,
    mission_id        INTEGER,
    queue_id          INTEGER,
    supervisor_run_id INTEGER,
    pipeline          TEXT NOT NULL,
    status            TEXT NOT NULL,
    last_method       TEXT,
    state_sha256      TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    finished_at       TEXT
);

-- Stage-7 capability taxonomy: durable scoped approvals/grants (NL-BP-168).
-- Additive tables only - legacy app_settings policies stay authoritative for the
-- read/write/execute/delete/network/cloud scopes in core/permissions.py.
CREATE TABLE IF NOT EXISTS capability_grants (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    capability   TEXT NOT NULL,
    scope_kind   TEXT NOT NULL,
    scope_value  TEXT,
    project_id   INTEGER,
    decision     TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'human',
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    expires_at   TEXT,
    consumed_at  TEXT,
    revoked_at   TEXT
);

CREATE TABLE IF NOT EXISTS capability_approvals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    capability   TEXT NOT NULL,
    scope_kind   TEXT NOT NULL,
    scope_value  TEXT,
    project_id   INTEGER,
    context_json TEXT NOT NULL DEFAULT '{}',
    reason       TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    requested_at TEXT NOT NULL,
    decided_at   TEXT,
    decided_by   TEXT,
    decision     TEXT,
    grant_id     INTEGER,
    expires_at   TEXT,
    source       TEXT NOT NULL DEFAULT 'human'
);

-- Stage-8 Universal Goal Mode (G1, additive only - goal_store/GoalService own
-- validation and lifecycle). Existing missions/tasks are reused via goal_missions.
CREATE TABLE IF NOT EXISTS goals (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id              INTEGER,
    title                   TEXT NOT NULL,
    objective               TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
    priority                TEXT NOT NULL DEFAULT 'P1',
    status                  TEXT NOT NULL DEFAULT 'planned',
    dependencies_json       TEXT NOT NULL DEFAULT '[]',
    template_id             TEXT,
    template_version        TEXT,
    source                  TEXT NOT NULL DEFAULT '',
    origin                  TEXT NOT NULL DEFAULT 'user',
    attachments_json        TEXT NOT NULL DEFAULT '[]',
    reference_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS milestones (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id                INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    title                  TEXT NOT NULL,
    description            TEXT NOT NULL DEFAULT '',
    priority               TEXT NOT NULL DEFAULT 'P1',
    status                 TEXT NOT NULL DEFAULT 'pending',
    ordering               INTEGER NOT NULL DEFAULT 0,
    dependencies_json      TEXT NOT NULL DEFAULT '[]',
    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json     TEXT NOT NULL DEFAULT '[]',
    risk                   TEXT NOT NULL DEFAULT '',
    validation_strategy    TEXT NOT NULL DEFAULT '',
    mission_intent         TEXT NOT NULL DEFAULT '',
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_milestones_goal_order
    ON milestones(goal_id, ordering);
CREATE TABLE IF NOT EXISTS goal_missions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id      INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    milestone_id INTEGER REFERENCES milestones(id) ON DELETE SET NULL,
    mission_id   INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'primary',
    created_at   TEXT NOT NULL,
    UNIQUE(goal_id, milestone_id, mission_id)
);

-- Stage-8 G3 independent goal completion verification (NL-BP-215, additive only).
-- Append-only verification evidence records - goal status is never mutated here.
CREATE TABLE IF NOT EXISTS goal_verifications (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id               INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    verifier_version      TEXT NOT NULL,
    verdict               TEXT NOT NULL,
    criteria_json         TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json    TEXT NOT NULL DEFAULT '[]',
    blockers_json         TEXT NOT NULL DEFAULT '[]',
    self_declared         INTEGER NOT NULL DEFAULT 0,
    self_declared_mismatch INTEGER NOT NULL DEFAULT 0,
    goal_status           TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL
);

-- Stage-8 G6 versioned goal plans (append-only snapshots - goal objective is immutable).
CREATE TABLE IF NOT EXISTS goal_plan_versions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id           INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    version           INTEGER NOT NULL,
    objective_snapshot TEXT NOT NULL,
    milestones_json   TEXT NOT NULL DEFAULT '[]',
    rationale         TEXT NOT NULL,
    trigger           TEXT NOT NULL DEFAULT 'manual',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    diff_json         TEXT NOT NULL DEFAULT '{}',
    supersedes        INTEGER,
    is_current        INTEGER NOT NULL DEFAULT 0,
    approved          INTEGER NOT NULL DEFAULT 0,
    approved_at       TEXT,
    approved_by       TEXT NOT NULL DEFAULT '',
    approval_note     TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    UNIQUE(goal_id, version)
);

-- Stage-8 document planning D2: deterministic reconciliation run history.
CREATE TABLE IF NOT EXISTS doc_reconciliation_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER,
    project_ref  TEXT NOT NULL DEFAULT '',
    corpus_hash  TEXT NOT NULL,
    report_hash  TEXT NOT NULL,
    report_json  TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_doc_reconciliation_runs_project
    ON doc_reconciliation_runs(project_id, id DESC);
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
    # Staged-candidate harness identity/metadata (phase 2, additive only).
    ("missions", "harness_version", "INTEGER"),
    ("missions", "staging_dir", "TEXT"),
    ("missions", "promotion_status", "TEXT"),
    # Stage-3 supervisor identity/correlation (phase 3, additive only; C3a).
    ("missions", "requirement_id", "TEXT"),
    ("missions", "supervisor_run_id", "INTEGER"),
    ("events", "project_id", "INTEGER"),
    ("events", "mission_id", "INTEGER"),
    ("events", "correlation_id", "TEXT"),
    ("events", "event_kind", "TEXT"),
    # Stage-4 Flow run link (C4b, additive; NULL for sequential missions).
    ("missions", "flow_id", "TEXT"),
    # Stage-8 G6 milestone replan metadata (additive; existing rows default empty).
    ("milestones", "risk", "TEXT NOT NULL DEFAULT ''"),
    ("milestones", "validation_strategy", "TEXT NOT NULL DEFAULT ''"),
    ("milestones", "mission_intent", "TEXT NOT NULL DEFAULT ''"),
    # Stage-8 G8 explicit plan approval metadata (additive; old plans pending).
    ("goal_plan_versions", "approved", "INTEGER NOT NULL DEFAULT 0"),
    ("goal_plan_versions", "approved_at", "TEXT"),
    ("goal_plan_versions", "approved_by", "TEXT NOT NULL DEFAULT ''"),
    ("goal_plan_versions", "approval_note", "TEXT NOT NULL DEFAULT ''"),
]

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_missions_project ON missions(project_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_mission ON tasks(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_attempts_task ON task_attempts(task_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_handoffs_mission ON handoffs(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_verification_mission ON verification_runs(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(id DESC);
CREATE INDEX IF NOT EXISTS idx_missions_staging ON missions(staging_dir);
CREATE INDEX IF NOT EXISTS idx_missions_requirement ON missions(requirement_id);
CREATE INDEX IF NOT EXISTS idx_queue_project_state ON mission_queue(project_id, state, id);
CREATE INDEX IF NOT EXISTS idx_queue_requirement ON mission_queue(project_id, requirement_id);
CREATE INDEX IF NOT EXISTS idx_backlog_stage ON backlog_items(program_stage, priority);
CREATE INDEX IF NOT EXISTS idx_evidence_mission ON mission_evidence(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(project_id, status, id);
CREATE INDEX IF NOT EXISTS idx_runs_project ON supervisor_runs(project_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_flow_states_uuid ON flow_states(flow_uuid, id DESC);
CREATE INDEX IF NOT EXISTS idx_flow_runs_mission ON flow_runs(mission_id);
CREATE INDEX IF NOT EXISTS idx_flow_runs_status ON flow_runs(status);
CREATE INDEX IF NOT EXISTS idx_attachments_mission ON mission_attachments(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_attachments_project ON mission_attachments(project_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_attachments_sha ON mission_attachments(sha256);
CREATE INDEX IF NOT EXISTS idx_capability_grants_cap
    ON capability_grants(capability, revoked_at, expires_at);
CREATE INDEX IF NOT EXISTS idx_capability_grants_project
    ON capability_grants(project_id, capability, id DESC);
CREATE INDEX IF NOT EXISTS idx_capability_approvals_status
    ON capability_approvals(capability, status, id DESC);
CREATE INDEX IF NOT EXISTS idx_capability_approvals_project
    ON capability_approvals(project_id, status, id DESC);
CREATE INDEX IF NOT EXISTS idx_goals_project_status
    ON goals(project_id, status, id DESC);
CREATE INDEX IF NOT EXISTS idx_goals_priority
    ON goals(priority, id);
CREATE INDEX IF NOT EXISTS idx_milestones_goal_status
    ON milestones(goal_id, status, ordering, id);
CREATE INDEX IF NOT EXISTS idx_goal_missions_goal
    ON goal_missions(goal_id, milestone_id, mission_id);
CREATE INDEX IF NOT EXISTS idx_goal_verifications_goal
    ON goal_verifications(goal_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_goal_plan_versions_goal
    ON goal_plan_versions(goal_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_goal_plan_versions_current
    ON goal_plan_versions(goal_id, is_current);


-- Stage-7 R8 saved research finding to existing mission links (additive only)
-- Revoked links are preserved and there is no hard-delete research API.
CREATE TABLE IF NOT EXISTS research_finding_attachments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id   INTEGER NOT NULL,
    mission_id   INTEGER NOT NULL,
    source       TEXT NOT NULL DEFAULT 'research',
    attached_by  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    revoked_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_research_finding_attachments_active
    ON research_finding_attachments(finding_id, mission_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_research_finding_attachments_mission
    ON research_finding_attachments(mission_id, revoked_at, id DESC);
CREATE INDEX IF NOT EXISTS idx_research_finding_attachments_finding
    ON research_finding_attachments(finding_id, revoked_at, id DESC);
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


def get_setting(key: str, default: str | None = None) -> str | None:
    """Return a raw app_settings value, or the default when unset."""
    conn = init_db()
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    """Persist one raw app_settings value (upsert)."""
    now = _now()
    conn = init_db()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, now),
            )
    finally:
        conn.close()


def get_json_setting(key: str, default: dict | None = None) -> dict:
    """Return a JSON-object app_settings value; corrupt/absent values fail closed to the default."""
    fallback = dict(default or {})
    raw = get_setting(key)
    if raw is None:
        return fallback
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return fallback
    return parsed if isinstance(parsed, dict) else fallback


def set_json_setting(key: str, value: dict) -> None:
    """Persist one JSON-object app_settings value."""
    if not isinstance(value, dict):
        raise ValueError("JSON settings values must be objects")
    set_setting(key, json.dumps(value, ensure_ascii=False, sort_keys=True))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log_event(conn: sqlite3.Connection, message: str, source: str = "system",
              level: str = "info", payload: str = "{}", *,
              project_id: int | None = None,
              mission_id: int | None = None,
              correlation_id: str | None = None,
              event_kind: str | None = None) -> None:
    """Append one audit event; stage-3 correlation fields are optional."""
    with conn:
        conn.execute(
            """
            INSERT INTO events (source, level, message, payload,
                                project_id, mission_id, correlation_id, event_kind)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (source, level, message, payload, project_id, mission_id,
             correlation_id, event_kind)
        )

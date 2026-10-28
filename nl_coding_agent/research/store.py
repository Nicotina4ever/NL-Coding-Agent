"""Local research knowledge store (stage 7 research R2, NL-BP-174 foundation).

Additive, idempotent SQLite persistence in the application database. The store
keeps only research evidence metadata/excerpts/citations/findings, never
credentials, cookies, tokens or wholesale project source content.

Tables created here (all CREATE ... IF NOT EXISTS; safe to run repeatedly):
  research_sources    - canonical/requested/final URL, redirect chain, provider,
                        title, bounded excerpt, content sha256, metadata,
                        retrieved/created/updated timestamps, project/mission/task
                        links, confidence, stale/refresh state
  research_findings   - question/answer excerpt, confidence, scope links,
                        source ids metadata, stale state
  research_citations  - source/finding citation with bounded quote/locator/note
  research_conflicts  - recorded disagreement between two sources for a finding

Deduplication:
  * sources are unique by canonical URL; the same content hash is idempotent,
    changed content refreshes the row (preserving the id) and clears stale;
  * citations/findings/conflicts use deterministic content keys and are
    idempotent on repeated saves.

There is no network, model, GUI or fetcher call in this module, and no deletion
API: rows can be marked stale/refreshed but not silently discarded.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

from nl_coding_agent.persistence.database import db_path, init_db

from .models import ResearchModelError, canonicalize_url, sha256_hex

STORE_SCHEMA_VERSION = 1
MAX_EXCERPT_CHARS = 4000
MAX_ANSWER_CHARS = 4000
MAX_QUOTE_CHARS = 2000
MAX_TITLE_CHARS = 300
MAX_QUESTION_CHARS = 500
MAX_METADATA_JSON_CHARS = 4000
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_META_PARTS = ("password", "passwd", "secret", "token", "api_key", "apikey",
                      "authorization", "cookie", "private_key", "credential")
_ALLOWED_SCHEMES = ("http", "https")


class ResearchStoreError(ValueError):
    """Raised for invalid/unsafe research store input."""


def _utc(value: datetime | str | None = None, field_name: str = "timestamp") -> str:
    if value is None:
        moment = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value.strip():
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ResearchStoreError(field_name + " must be ISO-8601") from exc
    else:
        raise ResearchStoreError(field_name + " must be a timestamp")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _url(value: str | None, field_name: str = "url") -> str | None:
    if value in (None, ""):
        return None
    try:
        canonical = canonicalize_url(str(value))
    except ResearchModelError as exc:
        raise ResearchStoreError(field_name + " is not a safe URL: " + str(exc)) from exc
    scheme = canonical.split(":", 1)[0].lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ResearchStoreError(field_name + " scheme must be http/https")
    return canonical


def _text(value, field_name: str, *, max_len: int, allow_empty: bool = True) -> str:
    text = str(value or "").strip()
    if not allow_empty and not text:
        raise ResearchStoreError(field_name + " must not be empty")
    if len(text) > max_len:
        raise ResearchStoreError(field_name + " exceeds " + str(max_len) + " characters")
    return text


def _sha(value, field_name: str) -> str:
    text = str(value or "").strip().lower()
    if not _SHA256_RE.match(text):
        raise ResearchStoreError(field_name + " must be 64 lower-case hex characters")
    return text


def _int_or_none(value, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ResearchStoreError(field_name + " must be an integer") from exc
    if parsed < 1:
        raise ResearchStoreError(field_name + " must be positive")
    return parsed


def _confidence(value) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchStoreError("confidence must be a number between 0 and 1") from exc
    if not 0.0 <= parsed <= 1.0:
        raise ResearchStoreError("confidence must be between 0 and 1")
    return round(parsed, 6)


def _metadata(value) -> str:
    if value in (None, ""):
        return "{}"
    if not isinstance(value, Mapping):
        raise ResearchStoreError("metadata must be an object")
    clean = {}
    for key, item in value.items():
        name = str(key or "").strip()
        if not name:
            raise ResearchStoreError("metadata keys must not be empty")
        lowered = name.lower()
        if any(part in lowered for part in _SECRET_META_PARTS):
            raise ResearchStoreError("metadata key looks secret and is refused: " + name)
        text = str(item).strip()
        if len(text) > 500:
            raise ResearchStoreError("metadata value is too long: " + name)
        clean[name] = text
    encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True)
    if len(encoded) > MAX_METADATA_JSON_CHARS:
        raise ResearchStoreError("metadata is too large")
    return encoded


def _limit(value, default: int = DEFAULT_LIMIT) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise ResearchStoreError("limit must be an integer") from exc
    if parsed < 1:
        raise ResearchStoreError("limit must be positive")
    return min(parsed, MAX_LIMIT)


def _offset(value) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ResearchStoreError("offset must be an integer") from exc
    if parsed < 0:
        raise ResearchStoreError("offset must be non-negative")
    return parsed


def _json_list(value) -> str:
    if value in (None, ""):
        return "[]"
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError as exc:
            raise ResearchStoreError("expected a JSON list") from exc
        value = parsed
    if not isinstance(value, (list, tuple)):
        raise ResearchStoreError("expected a list")
    clean = []
    for item in value:
        if isinstance(item, Mapping):
            clean.append({str(key): str(val) for key, val in sorted(item.items())})
        else:
            clean.append(str(item))
    return json.dumps(clean, ensure_ascii=False, sort_keys=True)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_url TEXT NOT NULL UNIQUE,
    requested_url TEXT,
    final_url TEXT,
    redirect_chain_json TEXT NOT NULL DEFAULT '[]',
    provider TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    excerpt TEXT NOT NULL DEFAULT '',
    content_sha256 TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    retrieved_at TEXT NOT NULL,
    project_id INTEGER,
    mission_id INTEGER,
    task_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.5,
    stale INTEGER NOT NULL DEFAULT 0,
    stale_reason TEXT,
    expired INTEGER NOT NULL DEFAULT 0,
    expired_at TEXT,
    refreshed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_key TEXT NOT NULL UNIQUE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    project_id INTEGER,
    mission_id INTEGER,
    task_id INTEGER,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    stale INTEGER NOT NULL DEFAULT 0,
    stale_reason TEXT,
    expired INTEGER NOT NULL DEFAULT 0,
    expired_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citation_key TEXT NOT NULL UNIQUE,
    source_id INTEGER NOT NULL REFERENCES research_sources(id) ON DELETE CASCADE,
    finding_id INTEGER REFERENCES research_findings(id) ON DELETE CASCADE,
    quote TEXT NOT NULL DEFAULT '',
    locator TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conflict_key TEXT NOT NULL UNIQUE,
    finding_id INTEGER REFERENCES research_findings(id) ON DELETE SET NULL,
    source_id_a INTEGER REFERENCES research_sources(id) ON DELETE SET NULL,
    source_id_b INTEGER REFERENCES research_sources(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_sources_scope
    ON research_sources(project_id, mission_id, task_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_research_sources_stale
    ON research_sources(stale, retrieved_at);
CREATE INDEX IF NOT EXISTS idx_research_sources_sha
    ON research_sources(content_sha256);
CREATE INDEX IF NOT EXISTS idx_research_findings_scope
    ON research_findings(project_id, mission_id, task_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_research_findings_stale
    ON research_findings(stale, updated_at);
CREATE INDEX IF NOT EXISTS idx_research_citations_source
    ON research_citations(source_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_research_citations_finding
    ON research_citations(finding_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_research_conflicts_finding
    ON research_conflicts(finding_id, id DESC);
CREATE TABLE IF NOT EXISTS research_finding_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES research_findings(id) ON DELETE CASCADE,
    mission_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'research',
    attached_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_research_finding_attachments_active
    ON research_finding_attachments(finding_id, mission_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_research_finding_attachments_mission
    ON research_finding_attachments(mission_id, revoked_at, id DESC);
CREATE INDEX IF NOT EXISTS idx_research_finding_attachments_finding
    ON research_finding_attachments(finding_id, revoked_at, id DESC);
"""

_RETENTION_MIGRATIONS = (
    ("research_sources", "expired", "INTEGER NOT NULL DEFAULT 0"),
    ("research_sources", "expired_at", "TEXT"),
    ("research_findings", "expired", "INTEGER NOT NULL DEFAULT 0"),
    ("research_findings", "expired_at", "TEXT"),
)


def _statements(script: str) -> Iterable[str]:
    for statement in script.split(";"):
        stmt = statement.strip()
        if stmt:
            yield stmt


class ResearchStore:
    """Additive research evidence store using the application SQLite database."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).expanduser().resolve() if path else db_path()
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        # init_db creates the additive application schema (existing tables are
        # preserved) and returns a row-factory connection for the app database.
        conn = init_db(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> tuple[str, ...]:
        conn = self._connect()
        try:
            with conn:
                for statement in _statements(_SCHEMA):
                    conn.execute(statement)
                for table, column, declaration in _RETENTION_MIGRATIONS:
                    existing = {row[1] for row in conn.execute(
                        "PRAGMA table_info(" + table + ")")}
                    if column not in existing:
                        conn.execute("ALTER TABLE " + table + " ADD COLUMN "
                                     + column + " " + declaration)
            tables = tuple(sorted(
                row["name"] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'research_%'")
            ))
            return tables
        finally:
            conn.close()

    # ---------------------------------------------------------------- sources
    def save_source(self, canonical_url: str, *, content_sha256: str | None = None,
                    excerpt: str = "", title: str = "", provider: str = "",
                    requested_url: str | None = None, final_url: str | None = None,
                    redirect_chain: Iterable[str] = (), content_type: str = "",
                    size_bytes: int | None = None,
                    metadata: Mapping | None = None,
                    retrieved_at: datetime | str | None = None,
                    project_id: int | None = None, mission_id: int | None = None,
                    task_id: int | None = None, confidence: float = 0.5,
                    stale: bool = False, stale_reason: str | None = None) -> dict:
        canonical = _url(canonical_url, "canonical_url")
        assert canonical is not None
        excerpt_text = _text(excerpt, "excerpt", max_len=MAX_EXCERPT_CHARS)
        digest = _sha(content_sha256, "content_sha256") if content_sha256 else \
            sha256_hex(excerpt_text.encode("utf-8"))
        requested = _url(requested_url, "requested_url") or canonical
        final = _url(final_url, "final_url") or canonical
        chain = []
        for item in redirect_chain or ():
            canonical_hop = _url(str(item), "redirect_chain")
            if canonical_hop:
                chain.append(canonical_hop)
        if not chain:
            chain = [final]
        chain_json = _json_list(chain)
        retrieved = _utc(retrieved_at, "retrieved_at")
        now = _utc(None, "now")
        title_text = _text(title, "title", max_len=MAX_TITLE_CHARS)
        provider_text = _text(provider, "provider", max_len=120)
        content_type_text = _text(content_type, "content_type", max_len=120)
        try:
            size = int(size_bytes) if size_bytes is not None else len(excerpt_text.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ResearchStoreError("size_bytes must be a non-negative integer") from exc
        if size < 0:
            raise ResearchStoreError("size_bytes must be non-negative")
        metadata_json = _metadata(metadata)
        project = _int_or_none(project_id, "project_id")
        mission = _int_or_none(mission_id, "mission_id")
        task = _int_or_none(task_id, "task_id")
        score = _confidence(confidence)
        stale_value = 1 if stale else 0
        reason = _text(stale_reason, "stale_reason", max_len=300) if stale_reason else None
        conn = self._connect()
        try:
            with conn:
                row = conn.execute("SELECT * FROM research_sources WHERE canonical_url=?",
                                   (canonical,)).fetchone()
                if row is not None:
                    existing_id = int(row["id"])
                    if str(row["content_sha256"]) == digest:
                        return {"id": existing_id, "created": False, "updated": False,
                                "deduped": True, "canonical_url": canonical}
                    conn.execute(
                        "UPDATE research_sources SET requested_url=?, final_url=?, "
                        "redirect_chain_json=?, provider=?, title=?, excerpt=?, "
                        "content_sha256=?, content_type=?, size_bytes=?, metadata_json=?, "
                        "retrieved_at=?, project_id=?, mission_id=?, task_id=?, "
                        "confidence=?, stale=?, stale_reason=?, refreshed_at=?, updated_at=? "
                        "WHERE id=?",
                        (requested, final, chain_json, provider_text, title_text, excerpt_text,
                         digest, content_type_text, size, metadata_json, retrieved, project,
                         mission, task, score, stale_value, reason, now, now, existing_id))
                    return {"id": existing_id, "created": False, "updated": True,
                            "deduped": True, "canonical_url": canonical}
                cursor = conn.execute(
                    "INSERT INTO research_sources (canonical_url, requested_url, final_url, "
                    "redirect_chain_json, provider, title, excerpt, content_sha256, "
                    "content_type, size_bytes, metadata_json, retrieved_at, project_id, "
                    "mission_id, task_id, confidence, stale, stale_reason, refreshed_at, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (canonical, requested, final, chain_json, provider_text, title_text,
                     excerpt_text, digest, content_type_text, size, metadata_json, retrieved,
                     project, mission, task, score, stale_value, reason, None, now, now))
                return {"id": int(cursor.lastrowid), "created": True, "updated": False,
                        "deduped": False, "canonical_url": canonical}
        finally:
            conn.close()

    def _source_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": int(row["id"]), "canonical_url": row["canonical_url"],
            "requested_url": row["requested_url"], "final_url": row["final_url"],
            "redirect_chain": json.loads(row["redirect_chain_json"] or "[]"),
            "provider": row["provider"], "title": row["title"], "excerpt": row["excerpt"],
            "content_sha256": row["content_sha256"], "content_type": row["content_type"],
            "size_bytes": int(row["size_bytes"]), "metadata": json.loads(row["metadata_json"] or "{}"),
            "retrieved_at": row["retrieved_at"], "project_id": row["project_id"],
            "mission_id": row["mission_id"], "task_id": row["task_id"],
            "confidence": float(row["confidence"]), "stale": bool(row["stale"]),
            "stale_reason": row["stale_reason"], "expired": bool(row["expired"]),
            "expired_at": row["expired_at"], "refreshed_at": row["refreshed_at"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def get_source(self, source_id: int) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM research_sources WHERE id=?",
                               (_int_or_none(source_id, "source_id"),)).fetchone()
            return self._source_row(row) if row else None
        finally:
            conn.close()

    def source_by_url(self, url: str) -> dict | None:
        canonical = _url(url)
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM research_sources WHERE canonical_url=?",
                               (canonical,)).fetchone()
            return self._source_row(row) if row else None
        finally:
            conn.close()

    def find_by_content_hash(self, content_sha256: str, *, limit: int = DEFAULT_LIMIT) -> list[dict]:
        digest = _sha(content_sha256, "content_sha256")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM research_sources WHERE content_sha256=? ORDER BY id DESC LIMIT ?",
                (digest, _limit(limit))).fetchall()
            return [self._source_row(row) for row in rows]
        finally:
            conn.close()

    def list_sources(self, *, project_id: int | None = None, mission_id: int | None = None,
                     task_id: int | None = None, text: str | None = None,
                     include_stale: bool = True, limit: int = DEFAULT_LIMIT,
                     offset: int = 0) -> list[dict]:
        clauses, params = [], []
        for column, value in (("project_id", project_id), ("mission_id", mission_id),
                              ("task_id", task_id)):
            if value is not None:
                clauses.append(column + "=?")
                params.append(_int_or_none(value, column))
        if not include_stale:
            clauses.append("stale=0")
        if text:
            needle = "%" + str(text).strip().lower() + "%"
            clauses.append("(lower(title) LIKE ? OR lower(excerpt) LIKE ? OR lower(canonical_url) LIKE ?)")
            params.extend([needle, needle, needle])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = "SELECT * FROM research_sources" + where + " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([_limit(limit), _offset(offset)])
        conn = self._connect()
        try:
            return [self._source_row(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def search_sources(self, text: str, **kwargs) -> list[dict]:
        kwargs["text"] = text
        return self.list_sources(**kwargs)

    def mark_source_stale(self, source_id: int, reason: str = "") -> bool:
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE research_sources SET stale=1, stale_reason=?, updated_at=? WHERE id=?",
                    (_text(reason, "reason", max_len=300), _utc(), _int_or_none(source_id, "source_id")))
            return cursor.rowcount > 0
        finally:
            conn.close()

    def refresh_source(self, source_id: int, *, content_sha256: str | None = None,
                       excerpt: str | None = None, title: str | None = None,
                       metadata: Mapping | None = None,
                       retrieved_at: datetime | str | None = None) -> dict | None:
        existing = self.get_source(source_id)
        if existing is None:
            return None
        new_excerpt = existing["excerpt"] if excerpt is None else _text(
            excerpt, "excerpt", max_len=MAX_EXCERPT_CHARS)
        digest = (_sha(content_sha256, "content_sha256") if content_sha256
                  else sha256_hex(new_excerpt.encode("utf-8")))
        metadata_json = (json.dumps(existing["metadata"], ensure_ascii=False, sort_keys=True)
                         if metadata is None else _metadata(metadata))
        now = _utc()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "UPDATE research_sources SET content_sha256=?, excerpt=?, title=?, "
                    "metadata_json=?, retrieved_at=?, refreshed_at=?, stale=0, "
                    "stale_reason=NULL, updated_at=? WHERE id=?",
                    (digest, new_excerpt,
                     existing["title"] if title is None else _text(title, "title", max_len=MAX_TITLE_CHARS),
                     metadata_json, _utc(retrieved_at, "retrieved_at") if retrieved_at else existing["retrieved_at"],
                     now, now, _int_or_none(source_id, "source_id")))
            return self.get_source(source_id)
        finally:
            conn.close()

    def stale_sources(self, *, now: datetime | str | None = None, max_age_days: float = 30.0,
                      limit: int = DEFAULT_LIMIT) -> list[dict]:
        try:
            days = float(max_age_days)
        except (TypeError, ValueError) as exc:
            raise ResearchStoreError("max_age_days must be a number") from exc
        if days < 0:
            raise ResearchStoreError("max_age_days must be non-negative")
        cutoff = (datetime.fromisoformat(_utc(now, "now").replace("Z", "+00:00"))
                  - timedelta(days=days)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM research_sources WHERE retrieved_at < ? ORDER BY retrieved_at ASC LIMIT ?",
                (cutoff, _limit(limit))).fetchall()
            return [self._source_row(row) for row in rows]
        finally:
            conn.close()

    def mark_expired(self, *, now: datetime | str | None = None,
                     max_age_days: float = 90.0) -> int:
        rows = self.stale_sources(now=now, max_age_days=max_age_days, limit=MAX_LIMIT)
        conn = self._connect()
        try:
            with conn:
                for row in rows:
                    conn.execute(
                        "UPDATE research_sources SET stale=1, stale_reason=?, updated_at=? "
                        "WHERE id=? AND stale=0",
                        ("expired: retrieved more than " + str(max_age_days) + " days ago",
                         _utc(), int(row["id"])))
            return len(rows)
        finally:
            conn.close()

    # --------------------------------------------------------------- findings
    def save_finding(self, question: str, answer: str = "", *,
                     source_ids: Iterable[int] = (), confidence: float = 0.5,
                     project_id: int | None = None, mission_id: int | None = None,
                     task_id: int | None = None, metadata: Mapping | None = None,
                     created_at: datetime | str | None = None) -> dict:
        question_text = _text(question, "question", max_len=MAX_QUESTION_CHARS, allow_empty=False)
        answer_text = _text(answer, "answer", max_len=MAX_ANSWER_CHARS)
        source_list = []
        conn = self._connect()
        try:
            for item in source_ids or ():
                source_id = _int_or_none(item, "source_id")
                row = conn.execute("SELECT id FROM research_sources WHERE id=?", (source_id,)).fetchone()
                if row is None:
                    raise ResearchStoreError("citation source does not exist: " + str(source_id))
                source_list.append(source_id)
        finally:
            conn.close()
        source_json = json.dumps(sorted(set(source_list)))
        project = _int_or_none(project_id, "project_id")
        mission = _int_or_none(mission_id, "mission_id")
        task = _int_or_none(task_id, "task_id")
        score = _confidence(confidence)
        metadata_json = _metadata(metadata)
        key_source = chr(10).join([question_text, answer_text, str(project), str(mission),
                                   str(task), source_json])
        finding_key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
        created = _utc(created_at, "created_at")
        now = _utc()
        conn = self._connect()
        try:
            with conn:
                row = conn.execute("SELECT id FROM research_findings WHERE finding_key=?",
                                   (finding_key,)).fetchone()
                if row is not None:
                    return {"id": int(row["id"]), "created": False, "deduped": True}
                cursor = conn.execute(
                    "INSERT INTO research_findings (finding_key, question, answer, confidence, "
                    "project_id, mission_id, task_id, source_ids_json, metadata_json, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (finding_key, question_text, answer_text, score, project, mission, task,
                     source_json, metadata_json, created, now))
                return {"id": int(cursor.lastrowid), "created": True, "deduped": False}
        finally:
            conn.close()

    def _finding_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": int(row["id"]), "question": row["question"], "answer": row["answer"],
            "confidence": float(row["confidence"]), "project_id": row["project_id"],
            "mission_id": row["mission_id"], "task_id": row["task_id"],
            "source_ids": json.loads(row["source_ids_json"] or "[]"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "stale": bool(row["stale"]), "stale_reason": row["stale_reason"],
            "expired": bool(row["expired"]), "expired_at": row["expired_at"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def get_finding(self, finding_id: int) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM research_findings WHERE id=?",
                               (_int_or_none(finding_id, "finding_id"),)).fetchone()
            return self._finding_row(row) if row else None
        finally:
            conn.close()

    def list_findings(self, *, project_id: int | None = None, mission_id: int | None = None,
                      task_id: int | None = None, text: str | None = None,
                      include_stale: bool = True, limit: int = DEFAULT_LIMIT,
                      offset: int = 0) -> list[dict]:
        clauses, params = [], []
        for column, value in (("project_id", project_id), ("mission_id", mission_id),
                              ("task_id", task_id)):
            if value is not None:
                clauses.append(column + "=?")
                params.append(_int_or_none(value, column))
        if not include_stale:
            clauses.append("stale=0")
        if text:
            needle = "%" + str(text).strip().lower() + "%"
            clauses.append("(lower(question) LIKE ? OR lower(answer) LIKE ?)")
            params.extend([needle, needle])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = "SELECT * FROM research_findings" + where + " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([_limit(limit), _offset(offset)])
        conn = self._connect()
        try:
            return [self._finding_row(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def mark_finding_stale(self, finding_id: int, reason: str = "") -> bool:
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE research_findings SET stale=1, stale_reason=?, updated_at=? WHERE id=?",
                    (_text(reason, "reason", max_len=300), _utc(),
                     _int_or_none(finding_id, "finding_id")))
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ------------------------------------------------- mission attachments
    def mission_scope(self, mission_id: int) -> dict | None:
        mission = _int_or_none(mission_id, "mission_id")
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, project_id, title, status FROM missions WHERE id=?",
                (mission,)).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def _link_row(self, row: sqlite3.Row) -> dict:
        return {"id": int(row["id"]), "finding_id": int(row["finding_id"]),
                "mission_id": int(row["mission_id"]), "source": row["source"],
                "attached_by": row["attached_by"], "created_at": row["created_at"],
                "revoked_at": row["revoked_at"],
                "active": row["revoked_at"] is None}

    def attach_finding_to_mission(self, finding_id: int, mission_id: int, *,
                                  source: str = "research",
                                  attached_by: str = "") -> dict:
        finding_value = _int_or_none(finding_id, "finding_id")
        mission_value = _int_or_none(mission_id, "mission_id")
        finding = self.get_finding(finding_value)
        if finding is None:
            raise ResearchStoreError("finding does not exist: " + str(finding_value))
        mission = self.mission_scope(mission_value)
        if mission is None:
            raise ResearchStoreError("mission does not exist: " + str(mission_value))
        finding_project = finding.get("project_id")
        mission_project = mission.get("project_id")
        if (finding_project is not None and mission_project is not None
                and int(finding_project) != int(mission_project)):
            raise ResearchStoreError("finding and mission belong to different projects")
        finding_mission = finding.get("mission_id")
        if finding_mission is not None and int(finding_mission) != mission_value:
            raise ResearchStoreError("finding belongs to a different mission scope")
        source_text = _text(source, "source", max_len=100) or "research"
        actor = _text(attached_by, "attached_by", max_len=200)
        now = _utc()
        conn = self._connect()
        try:
            with conn:
                existing = conn.execute(
                    "SELECT * FROM research_finding_attachments WHERE finding_id=? "
                    "AND mission_id=? AND revoked_at IS NULL ORDER BY id DESC LIMIT 1",
                    (finding_value, mission_value)).fetchone()
                if existing is not None:
                    result = self._link_row(existing)
                    result.update({"created": False, "idempotent": True,
                                   "finding": finding, "mission": mission})
                    return result
                cursor = conn.execute(
                    "INSERT INTO research_finding_attachments "
                    "(finding_id, mission_id, source, attached_by, created_at) "
                    "VALUES (?,?,?,?,?)",
                    (finding_value, mission_value, source_text, actor, now))
                result = {"id": int(cursor.lastrowid), "finding_id": finding_value,
                          "mission_id": mission_value, "source": source_text,
                          "attached_by": actor, "created_at": now,
                          "revoked_at": None, "active": True,
                          "created": True, "idempotent": False,
                          "finding": finding, "mission": mission}
                return result
        finally:
            conn.close()

    def detach_finding_from_mission(self, finding_id: int, mission_id: int) -> dict:
        finding_value = _int_or_none(finding_id, "finding_id")
        mission_value = _int_or_none(mission_id, "mission_id")
        now = _utc()
        conn = self._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT * FROM research_finding_attachments WHERE finding_id=? "
                    "AND mission_id=? AND revoked_at IS NULL ORDER BY id DESC LIMIT 1",
                    (finding_value, mission_value)).fetchone()
                if row is None:
                    return {"detached": False, "link_id": None,
                            "finding_id": finding_value, "mission_id": mission_value}
                conn.execute(
                    "UPDATE research_finding_attachments SET revoked_at=? WHERE id=?",
                    (now, int(row["id"])))
                return {"detached": True, "link_id": int(row["id"]),
                        "finding_id": finding_value, "mission_id": mission_value,
                        "revoked_at": now, "finding_preserved": True}
        finally:
            conn.close()

    def list_mission_findings(self, mission_id: int, *,
                              include_revoked: bool = False) -> list[dict]:
        mission_value = _int_or_none(mission_id, "mission_id")
        clauses = ["a.mission_id=?"]
        if not include_revoked:
            clauses.append("a.revoked_at IS NULL")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT f.*, a.id AS attachment_id, a.source AS attachment_source, "
                "a.attached_by AS attachment_attached_by, a.created_at AS attached_at, "
                "a.revoked_at AS attachment_revoked_at "
                "FROM research_finding_attachments a "
                "JOIN research_findings f ON f.id = a.finding_id "
                "WHERE " + " AND ".join(clauses)
                + " ORDER BY a.created_at DESC, a.id DESC", (mission_value,)).fetchall()
            output = []
            for row in rows:
                finding = self._finding_row(row)
                finding.update({
                    "attachment_id": int(row["attachment_id"]),
                    "attachment_source": row["attachment_source"],
                    "attached_by": row["attachment_attached_by"],
                    "attached_at": row["attached_at"],
                    "revoked_at": row["attachment_revoked_at"],
                    "active": row["attachment_revoked_at"] is None,
                })
                output.append(finding)
            return output
        finally:
            conn.close()

    def list_finding_missions(self, finding_id: int, *,
                              include_revoked: bool = False) -> list[dict]:
        finding_value = _int_or_none(finding_id, "finding_id")
        clauses = ["a.finding_id=?"]
        if not include_revoked:
            clauses.append("a.revoked_at IS NULL")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT a.* FROM research_finding_attachments a WHERE "
                + " AND ".join(clauses) + " ORDER BY a.id DESC", (finding_value,)).fetchall()
            return [self._link_row(row) for row in rows]
        finally:
            conn.close()

    def attachment_status(self, finding_id: int, mission_id: int) -> dict:
        finding_value = _int_or_none(finding_id, "finding_id")
        mission_value = _int_or_none(mission_id, "mission_id")
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM research_finding_attachments WHERE finding_id=? "
                "AND mission_id=? AND revoked_at IS NULL ORDER BY id DESC LIMIT 1",
                (finding_value, mission_value)).fetchone()
            if row is None:
                return {"attached": False, "finding_id": finding_value,
                        "mission_id": mission_value, "link": None}
            return {"attached": True, "finding_id": finding_value,
                    "mission_id": mission_value, "link": self._link_row(row)}
        finally:
            conn.close()

    # -------------------------------------------------------------- retention
    @staticmethod
    def _older_than(value: str, cutoff: datetime) -> bool:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment < cutoff

    def apply_retention(self, now: datetime | str | None = None,
                        ttl_days: float = 30.0,
                        max_items: int = 500) -> dict:
        """Mark old sources/findings stale+expired. Never deletes rows or evidence."""
        try:
            ttl = float(ttl_days)
        except (TypeError, ValueError) as exc:
            raise ResearchStoreError("ttl_days must be a number") from exc
        if ttl <= 0:
            raise ResearchStoreError("ttl_days must be positive")
        try:
            limit = int(max_items)
        except (TypeError, ValueError) as exc:
            raise ResearchStoreError("max_items must be an integer") from exc
        if limit <= 0:
            raise ResearchStoreError("max_items must be positive")
        now_value = _utc(now, "now")
        cutoff = datetime.fromisoformat(now_value.replace("Z", "+00:00")) - timedelta(days=ttl)
        conn = self._connect()
        sources_expired = findings_expired = 0
        try:
            with conn:
                source_rows = conn.execute(
                    "SELECT id, retrieved_at FROM research_sources "
                    "WHERE expired=0 ORDER BY retrieved_at ASC LIMIT ?", (limit,)).fetchall()
                for row in source_rows:
                    if not self._older_than(row["retrieved_at"], cutoff):
                        continue
                    conn.execute(
                        "UPDATE research_sources SET stale=1, expired=1, expired_at=?, "
                        "stale_reason=?, updated_at=? WHERE id=?",
                        (now_value, "expired: retention ttl_days=" + str(ttl),
                         now_value, int(row["id"])))
                    sources_expired += 1
                finding_rows = conn.execute(
                    "SELECT id, updated_at FROM research_findings "
                    "WHERE expired=0 ORDER BY updated_at ASC LIMIT ?", (limit,)).fetchall()
                for row in finding_rows:
                    if not self._older_than(row["updated_at"], cutoff):
                        continue
                    conn.execute(
                        "UPDATE research_findings SET stale=1, expired=1, expired_at=?, "
                        "stale_reason=?, updated_at=? WHERE id=?",
                        (now_value, "expired: retention ttl_days=" + str(ttl),
                         now_value, int(row["id"])))
                    findings_expired += 1
            return {"now": now_value, "ttl_days": ttl, "max_items": limit,
                    "sources_expired": sources_expired,
                    "findings_expired": findings_expired,
                    "citations_preserved": int(conn.execute(
                        "SELECT COUNT(1) FROM research_citations").fetchone()[0]),
                    "findings_preserved": int(conn.execute(
                        "SELECT COUNT(1) FROM research_findings").fetchone()[0]),
                    "sources_preserved": int(conn.execute(
                        "SELECT COUNT(1) FROM research_sources").fetchone()[0]),
                    "deleted": 0, "hard_deleted": False}
        finally:
            conn.close()

    def list_expired(self) -> list[dict]:
        conn = self._connect()
        try:
            output = []
            for row in conn.execute(
                    "SELECT * FROM research_sources WHERE expired=1 ORDER BY id").fetchall():
                item = self._source_row(row)
                item["kind"] = "source"
                output.append(item)
            for row in conn.execute(
                    "SELECT * FROM research_findings WHERE expired=1 ORDER BY id").fetchall():
                item = self._finding_row(row)
                item["kind"] = "finding"
                output.append(item)
            return output
        finally:
            conn.close()

    def retention_summary(self) -> dict:
        conn = self._connect()
        try:
            def count(sql, params=()):
                return int(conn.execute(sql, params).fetchone()[0])
            return {
                "sources_total": count("SELECT COUNT(1) FROM research_sources"),
                "sources_stale": count("SELECT COUNT(1) FROM research_sources WHERE stale=1"),
                "sources_expired": count("SELECT COUNT(1) FROM research_sources WHERE expired=1"),
                "findings_total": count("SELECT COUNT(1) FROM research_findings"),
                "findings_stale": count("SELECT COUNT(1) FROM research_findings WHERE stale=1"),
                "findings_expired": count("SELECT COUNT(1) FROM research_findings WHERE expired=1"),
                "citations_total": count("SELECT COUNT(1) FROM research_citations"),
                "attachments_total": count(
                    "SELECT COUNT(1) FROM research_finding_attachments"),
                "attachments_active": count(
                    "SELECT COUNT(1) FROM research_finding_attachments WHERE revoked_at IS NULL"),
                "attachments_revoked": count(
                    "SELECT COUNT(1) FROM research_finding_attachments WHERE revoked_at IS NOT NULL"),
                "hard_deleted": False, "delete_api": False,
            }
        finally:
            conn.close()

    # -------------------------------------------------------------- citations
    def save_citation(self, source_id: int, *, quote: str = "", locator: str = "",
                      note: str = "", finding_id: int | None = None) -> dict:
        source = self.get_source(source_id)
        if source is None:
            raise ResearchStoreError("citation source does not exist: " + str(source_id))
        finding = None
        if finding_id is not None:
            finding_value = _int_or_none(finding_id, "finding_id")
            if self.get_finding(finding_value) is None:
                raise ResearchStoreError("citation finding does not exist: " + str(finding_value))
            finding = finding_value
        quote_text = _text(quote, "quote", max_len=MAX_QUOTE_CHARS)
        locator_text = _text(locator, "locator", max_len=300)
        note_text = _text(note, "note", max_len=1000)
        key_source = chr(10).join([str(source["id"]), str(finding or ""), quote_text,
                                   locator_text, note_text])
        citation_key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
        now = _utc()
        conn = self._connect()
        try:
            with conn:
                row = conn.execute("SELECT id FROM research_citations WHERE citation_key=?",
                                   (citation_key,)).fetchone()
                if row is not None:
                    return {"id": int(row["id"]), "created": False, "deduped": True}
                cursor = conn.execute(
                    "INSERT INTO research_citations (citation_key, source_id, finding_id, "
                    "quote, locator, note, created_at) VALUES (?,?,?,?,?,?,?)",
                    (citation_key, source["id"], finding, quote_text, locator_text,
                     note_text, now))
                return {"id": int(cursor.lastrowid), "created": True, "deduped": False}
        finally:
            conn.close()

    def list_citations(self, *, source_id: int | None = None,
                       finding_id: int | None = None,
                       limit: int = DEFAULT_LIMIT) -> list[dict]:
        clauses, params = [], []
        if source_id is not None:
            clauses.append("source_id=?")
            params.append(_int_or_none(source_id, "source_id"))
        if finding_id is not None:
            clauses.append("finding_id=?")
            params.append(_int_or_none(finding_id, "finding_id"))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM research_citations" + where + " ORDER BY id DESC LIMIT ?",
                params + [_limit(limit)]).fetchall()
            return [{"id": int(row["id"]), "source_id": int(row["source_id"]),
                     "finding_id": row["finding_id"], "quote": row["quote"],
                     "locator": row["locator"], "note": row["note"],
                     "created_at": row["created_at"]} for row in rows]
        finally:
            conn.close()

    # -------------------------------------------------------------- conflicts
    def record_conflict(self, finding_id: int, source_id_a: int, source_id_b: int,
                        description: str) -> dict:
        finding = _int_or_none(finding_id, "finding_id")
        if self.get_finding(finding) is None:
            raise ResearchStoreError("conflict finding does not exist: " + str(finding))
        a = _int_or_none(source_id_a, "source_id_a")
        b = _int_or_none(source_id_b, "source_id_b")
        for source_id in (a, b):
            if self.get_source(source_id) is None:
                raise ResearchStoreError("conflict source does not exist: " + str(source_id))
        description_text = _text(description, "description", max_len=1000, allow_empty=False)
        key = hashlib.sha256(chr(10).join([str(finding), str(a), str(b),
                                           description_text]).encode("utf-8")).hexdigest()
        conn = self._connect()
        try:
            with conn:
                row = conn.execute("SELECT id FROM research_conflicts WHERE conflict_key=?",
                                   (key,)).fetchone()
                if row is not None:
                    return {"id": int(row["id"]), "created": False, "deduped": True}
                cursor = conn.execute(
                    "INSERT INTO research_conflicts (conflict_key, finding_id, source_id_a, "
                    "source_id_b, description, created_at) VALUES (?,?,?,?,?,?)",
                    (key, finding, a, b, description_text, _utc()))
                return {"id": int(cursor.lastrowid), "created": True, "deduped": False}
        finally:
            conn.close()

    def list_conflicts(self, *, finding_id: int | None = None,
                       limit: int = DEFAULT_LIMIT) -> list[dict]:
        params = []
        where = ""
        if finding_id is not None:
            where = " WHERE finding_id=?"
            params.append(_int_or_none(finding_id, "finding_id"))
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM research_conflicts" + where + " ORDER BY id DESC LIMIT ?",
                params + [_limit(limit)]).fetchall()
            return [{"id": int(row["id"]), "finding_id": row["finding_id"],
                     "source_id_a": row["source_id_a"], "source_id_b": row["source_id_b"],
                     "description": row["description"], "created_at": row["created_at"]}
                    for row in rows]
        finally:
            conn.close()

    def counts(self) -> dict:
        conn = self._connect()
        try:
            result = {}
            for name in ("research_sources", "research_findings", "research_citations",
                         "research_conflicts"):
                result[name] = int(conn.execute("SELECT COUNT(*) FROM " + name).fetchone()[0])
            return result
        finally:
            conn.close()

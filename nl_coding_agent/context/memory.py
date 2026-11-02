"""Durable cross-mission project memory (P1).

Handoffs and verification evidence already exist per mission, but nothing survived
between missions: a later mission could not know that a file is fragile, that a
test is flaky, or why a previous attempt was rejected. This module stores small,
bounded, deduplicated memory entries and recalls them by keyword for the next
mission prompt. It is deliberately text-only and never stores credentials,
attachments or full file contents.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable

from nl_coding_agent.persistence.database import init_db

MAX_ENTRY_CHARS = 900
MAX_RECALL_ENTRIES = 8
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"
)


def _db():
    return init_db()


def _sanitize(text: str, limit: int = MAX_ENTRY_CHARS) -> str:
    value = " ".join(str(text or "").split())
    value = _SECRET_RE.sub(r"\1: [redacted]", value)
    return value[:limit]


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9_]+", str(text or "").lower())
            if len(token) >= 3]


def _fingerprint(kind: str, text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return hashlib.sha256((kind + "\n" + normalized).encode("utf-8")).hexdigest()


@dataclass
class MemoryEntry:
    id: int
    project_id: int
    mission_id: int | None
    kind: str
    text: str
    tags: list
    confidence: float
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "kind": self.kind,
            "text": self.text,
            "tags": list(self.tags),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


def record(project_id: int | None, kind: str, text: str, *,
           mission_id: int | None = None, tags: Iterable[str] = (),
           confidence: float = 0.5) -> dict | None:
    """Store one deduplicated memory entry; returns the stored row or None."""
    if project_id is None:
        return None
    cleaned = _sanitize(text)
    if not cleaned:
        return None
    kind_value = str(kind or "note")[:40]
    tag_list = [str(tag)[:60] for tag in tags if str(tag).strip()][:12]
    fingerprint = _fingerprint(kind_value, cleaned)
    conn = _db()
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO project_memory"
                "(project_id, mission_id, kind, text, tags, confidence, fingerprint, created_at) "
                "VALUES(?,?,?,?,?,?,?, datetime('now'))",
                (int(project_id), int(mission_id) if mission_id is not None else None,
                 kind_value, cleaned, json.dumps(tag_list, ensure_ascii=False),
                 max(0.0, min(1.0, float(confidence))), fingerprint),
            )
        row = conn.execute(
            "SELECT * FROM project_memory WHERE project_id=? AND fingerprint=?",
            (int(project_id), fingerprint),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_entry(row).to_dict() if row else None


def _row_to_entry(row) -> MemoryEntry:
    try:
        tags = json.loads(row["tags"] or "[]")
    except (TypeError, ValueError):
        tags = []
    return MemoryEntry(
        id=int(row["id"]), project_id=int(row["project_id"]),
        mission_id=int(row["mission_id"]) if row["mission_id"] is not None else None,
        kind=str(row["kind"] or ""), text=str(row["text"] or ""),
        tags=tags if isinstance(tags, list) else [],
        confidence=float(row["confidence"] or 0.5),
        created_at=str(row["created_at"] or ""),
    )


def recall(project_id: int | None, query: str = "", *, limit: int = MAX_RECALL_ENTRIES,
           kinds: Iterable[str] | None = None) -> list[dict]:
    """Rank stored entries against a query by token overlap, confidence and recency."""
    if project_id is None:
        return []
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT * FROM project_memory WHERE project_id=? ORDER BY id DESC LIMIT 400",
            (int(project_id),),
        ).fetchall()
    finally:
        conn.close()
    wanted_kinds = {str(kind) for kind in (kinds or [])}
    query_tokens = set(_tokens(query))
    ranked: list[tuple[float, int, MemoryEntry]] = []
    for index, row in enumerate(rows):
        entry = _row_to_entry(row)
        if wanted_kinds and entry.kind not in wanted_kinds:
            continue
        haystack = (entry.text + " " + " ".join(entry.tags)).lower()
        hits = len(query_tokens & set(_tokens(haystack))) if query_tokens else 0
        score = float(hits) * 10.0 + entry.confidence * 2.0 - index * 0.01
        # Newer entries win ties; exact kind queries keep their recency ordering.
        ranked.append((score, index, entry))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [entry.to_dict() for _, _, entry in ranked[:max(1, min(int(limit), 50))]]


def recall_text(project_id: int | None, query: str = "", *,
                limit: int = 6) -> str:
    """Compact block for prompts; empty when the project has no relevant memory."""
    entries = recall(project_id, query, limit=limit)
    if not entries:
        return ""
    lines = ["PROJECT MEMORY (persisted from earlier missions; verify before relying on it):"]
    for entry in entries:
        lines.append(
            "- [" + entry["kind"] + "] " + entry["text"]
            + ((" (mission #" + str(entry["mission_id"]) + ")")
               if entry.get("mission_id") else "")
        )
    return "\n".join(lines)


def record_mission_outcome(mission_id: int, *, status: str, goal: str = "",
                           summary: str = "", changed_paths: Iterable[str] = (),
                           verdict: str = "", failure: str = "",
                           project_id: int | None = None) -> list[dict]:
    """Persist a compact lesson for a finished mission (best effort, never raises)."""
    saved: list[dict] = []
    try:
        changed = [str(path) for path in (changed_paths or [])][:20]
        detail = _sanitize(
            "Mission #" + str(int(mission_id)) + " [" + str(status) + "]"
            + (" goal: " + str(goal)[:220] if goal else "")
            + (" changed: " + ", ".join(changed[:8]) if changed else "")
            + (" verdict: " + str(verdict) if verdict else "")
            + (" summary: " + str(summary)[:200] if summary else ""),
            MAX_ENTRY_CHARS,
        )
        entry = record(project_id, "mission_outcome", detail,
                       mission_id=mission_id, tags=changed[:6], confidence=0.6)
        if entry:
            saved.append(entry)
        if failure:
            failed = record(project_id, "failure", _sanitize(str(failure)),
                            mission_id=mission_id, tags=changed[:4], confidence=0.7)
            if failed:
                saved.append(failed)
    except Exception:
        return saved
    return saved


def attach_mission_outcome(mission_id: int) -> list[dict]:
    """Read a persisted mission row and store its outcome/failure memory."""
    try:
        from nl_coding_agent.persistence.missions import get_mission, get_task_attempts
    except Exception:
        return []
    mission = get_mission(int(mission_id)) or {}
    if not mission:
        return []
    changed: list[str] = []
    try:
        changed = json.loads(mission.get("changed_paths") or "[]")
    except (TypeError, ValueError):
        changed = []
    failure = ""
    try:
        for attempt in get_task_attempts(int(mission_id)):
            if str(attempt.get("status") or "") == "failed" and attempt.get("error"):
                failure = str(attempt["error"])[:600]
                break
    except Exception:
        failure = ""
    return record_mission_outcome(
        int(mission_id),
        status=str(mission.get("status") or "unknown"),
        goal=str(mission.get("goal") or ""),
        summary=str(mission.get("result_summary") or ""),
        changed_paths=changed,
        verdict=str(mission.get("review_verdict") or ""),
        failure=failure,
        project_id=int(mission["project_id"]) if mission.get("project_id") is not None else None,
    )


def clear_project(project_id: int) -> int:
    """Delete one project's memory (used by explicit user data cleanup only)."""
    conn = _db()
    try:
        with conn:
            cursor = conn.execute("DELETE FROM project_memory WHERE project_id=?",
                                  (int(project_id),))
        return int(cursor.rowcount or 0)
    finally:
        conn.close()

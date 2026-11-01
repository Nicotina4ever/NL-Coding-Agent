"""SQLite-backed multi-session Chat persistence.

The former one-thread-per-project JSON is migrated once into a default session
on first access; no transcript is deleted during migration. Deleting a session
requires archiving it first and never touches missions or project files.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from nl_coding_agent.persistence import database


class ChatSessionError(ValueError):
    pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _legacy_path(project_id: int) -> Path:
    return database.data_root() / "chat" / f"project-{int(project_id)}.json"


def _legacy_messages(project_id: int) -> list[dict]:
    path = _legacy_path(project_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ChatSessionError(
            "Invalid chat history; original file preserved") from exc
    messages = data if isinstance(data, list) else data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list) or any(
            not isinstance(item, dict) or item.get("role") not in ("user", "assistant", "system")
            or not isinstance(item.get("content"), str) for item in messages):
        raise ChatSessionError("Invalid chat history; original file preserved")
    return [dict(item) for item in messages]


def _insert_message(conn, session_id: str, item: dict) -> None:
    role = str(item.get("role") or "")
    if role not in ("user", "assistant", "system"):
        return
    metadata = {key: value for key, value in item.items()
                if key not in ("role", "content", "created_at")}
    conn.execute(
        "INSERT INTO chat_messages(session_id, role, content, metadata_json, created_at) "
        "VALUES (?,?,?,?,?)",
        (session_id, role, str(item.get("content") or ""),
         json.dumps(metadata, ensure_ascii=False, default=str),
         str(item.get("created_at") or _now())),
    )


def ensure_default_session(project_id: int) -> dict:
    """Return the latest active session, creating/migrating one if necessary."""
    conn = database.init_db()
    try:
        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE project_id=? AND archived_at IS NULL "
            "ORDER BY updated_at DESC, created_at DESC LIMIT 1",
            (int(project_id),),
        ).fetchone()
        if row:
            return dict(row)
        legacy = [] if database.get_setting(
            "chat.legacy_migrated." + str(int(project_id))) == "1" else _legacy_messages(project_id)
        session_id = "legacy-" + str(int(project_id)) if legacy else uuid.uuid4().hex
        title = "Imported conversation" if legacy else "Main"
        if legacy:
            first_user = next((m for m in legacy if m.get("role") == "user"), None)
            if first_user:
                title = str(first_user.get("content") or "Conversation")[:80]
        with conn:
            conn.execute(
                "INSERT INTO chat_sessions(id, project_id, title, created_at, updated_at) "
                "VALUES (?,?,?,?,?)",
                (session_id, int(project_id), title, _now(), _now()),
            )
            for item in legacy:
                _insert_message(conn, session_id, item)
            conn.execute(
                "INSERT INTO app_settings(key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                ("chat.legacy_migrated." + str(int(project_id)), "1", _now()),
            )
        row = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_sessions(project_id: int, *, include_archived: bool = False) -> list[dict]:
    ensure_default_session(project_id)
    conn = database.init_db()
    try:
        clause = "" if include_archived else " AND archived_at IS NULL"
        rows = conn.execute(
            "SELECT * FROM chat_sessions WHERE project_id=?" + clause +
            " ORDER BY updated_at DESC, created_at DESC",
            (int(project_id),),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            count = conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id=?",
                (item["id"],),
            ).fetchone()[0]
            item["message_count"] = int(count)
            result.append(item)
        return result
    finally:
        conn.close()


def create_session(project_id: int, title: str = "New conversation") -> dict:
    session_id = uuid.uuid4().hex
    conn = database.init_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO chat_sessions(id, project_id, title, created_at, updated_at) "
                "VALUES (?,?,?,?,?)",
                (session_id, int(project_id), str(title or "New conversation")[:200],
                 _now(), _now()),
            )
    finally:
        conn.close()
    return get_session(session_id)


def get_session(session_id: str) -> dict:
    conn = database.init_db()
    try:
        row = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (str(session_id),)).fetchone()
        if not row:
            raise ChatSessionError("Chat session not found")
        return dict(row)
    finally:
        conn.close()


def rename_session(session_id: str, title: str) -> dict:
    title = str(title or "").strip()
    if not title:
        raise ChatSessionError("Session title is required")
    conn = database.init_db()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=?",
                (title[:200], _now(), str(session_id)),
            )
            if cur.rowcount == 0:
                raise ChatSessionError("Chat session not found")
    finally:
        conn.close()
    return get_session(session_id)


def archive_session(session_id: str) -> dict:
    conn = database.init_db()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE chat_sessions SET archived_at=?, updated_at=? WHERE id=?",
                (_now(), _now(), str(session_id)),
            )
            if cur.rowcount == 0:
                raise ChatSessionError("Chat session not found")
    finally:
        conn.close()
    return get_session(session_id)


def delete_session(project_id: int, session_id: str) -> dict:
    session = get_session(session_id)
    if session.get("project_id") != int(project_id):
        raise ChatSessionError("Session belongs to another project")
    if not session.get("archived_at"):
        raise ChatSessionError("Archive the session before deleting it")
    conn = database.init_db()
    try:
        with conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id=?", (str(session_id),))
            conn.execute("DELETE FROM chat_sessions WHERE id=?", (str(session_id),))
    finally:
        conn.close()
    ensure_default_session(project_id)
    return session


def messages(project_id: int, session_id: str | None = None) -> list[dict]:
    session = get_session(session_id) if session_id else ensure_default_session(project_id)
    if session.get("project_id") != int(project_id):
        raise ChatSessionError("Session belongs to another project")
    conn = database.init_db()
    try:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id",
            (session["id"],),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        item = {"id": row["id"], "role": row["role"], "content": row["content"],
                "created_at": row["created_at"]}
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except ValueError:
            metadata = {}
        if isinstance(metadata, dict):
            item.update(metadata)
        result.append(item)
    return result


def append_message(project_id: int, role: str, content: str,
                   session_id: str | None = None, **metadata) -> dict:
    session = get_session(session_id) if session_id else ensure_default_session(project_id)
    if session.get("project_id") != int(project_id):
        raise ChatSessionError("Session belongs to another project")
    item = {"role": str(role), "content": str(content or ""),
            "created_at": _now(), **metadata}
    conn = database.init_db()
    try:
        with conn:
            _insert_message(conn, session["id"], item)
            conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?",
                         (_now(), session["id"]))
    finally:
        conn.close()
    return item


def rewind(project_id: int, session_id: str, message_id: int,
           replacement: str | None = None) -> dict:
    """Delete one message and everything after it, after backing the session up."""
    session = get_session(session_id)
    if session.get("project_id") != int(project_id):
        raise ChatSessionError("Session belongs to another project")
    conn = database.init_db()
    try:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id",
            (str(session_id),),
        ).fetchall()
        backup_rows = [dict(row) for row in rows]
        target = next((row for row in rows if int(row["id"]) == int(message_id)), None)
        if target is None:
            raise ChatSessionError("Chat message not found in this session")
        from datetime import datetime
        backup = database.db_path().parent / "backups" / "chat" / (
            "rewind-" + str(session_id) + "-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps(backup_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        with conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id=? AND id>=?",
                         (str(session_id), int(message_id)))
            if replacement is not None and str(replacement).strip():
                _insert_message(conn, str(session_id), {
                    "role": "user", "content": str(replacement).strip(), "created_at": _now(),
                })
            conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?",
                         (_now(), str(session_id)))
    finally:
        conn.close()
    return {"ok": True, "session_id": str(session_id), "rewound_from": int(message_id),
            "backup": str(backup), "messages": messages(int(project_id), str(session_id))}


def search(project_id: int, query: str, *, limit: int = 100) -> list[dict]:
    needle = str(query or "").strip()
    if not needle:
        return []
    conn = database.init_db()
    try:
        rows = conn.execute(
            "SELECT m.*, s.title FROM chat_messages m JOIN chat_sessions s "
            "ON s.id=m.session_id WHERE s.project_id=? AND m.content LIKE ? "
            "ORDER BY m.id DESC LIMIT ?",
            (int(project_id), "%" + needle + "%", max(1, min(int(limit), 500))),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def cleanup_sessions(scope: str = "orphaned", project_id: int | None = None) -> dict:
    """Delete archived conversations or conversations of deleted projects.

    Orphaned sessions have a project_id that is no longer in the project registry;
    archived sessions are deleted only when explicitly requested. Active sessions
    and active projects are never touched.
    """
    normalized = str(scope or "orphaned").strip().lower()
    if normalized not in ("orphaned", "archived"):
        raise ChatSessionError("Cleanup scope must be 'orphaned' or 'archived'")
    conn = database.init_db()
    try:
        if normalized == "orphaned":
            condition = ("project_id IS NOT NULL AND project_id NOT IN "
                         "(SELECT id FROM projects)")
            params: tuple = ()
        else:
            condition = "archived_at IS NOT NULL"
            params = ()
            if project_id is not None:
                condition += " AND project_id=?"
                params = (int(project_id),)
        rows = conn.execute(
            "SELECT id FROM chat_sessions WHERE " + condition, params).fetchall()
        ids = [str(row["id"]) for row in rows]
        if not ids:
            return {"scope": normalized, "sessions": 0, "messages": 0,
                    "project_id": project_id}
        placeholders = ",".join("?" for _ in ids)
        message_count = int(conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id IN (" +
            placeholders + ")", ids).fetchone()[0])
        with conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id IN (" +
                         placeholders + ")", ids)
            conn.execute("DELETE FROM chat_sessions WHERE id IN (" +
                         placeholders + ")", ids)
        return {"scope": normalized, "sessions": len(ids),
                "messages": message_count, "project_id": project_id}
    finally:
        conn.close()


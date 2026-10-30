"""C4b app-owned Flow persistence: the full CrewAI FlowPersistence interface
backed only by the application SQLite database.

No CrewAI default store is ever used: no SQLiteFlowPersistence, no
default_flow_persistence() fallback, no %LOCALAPPDATA%/CrewAI path. Snapshots are
small, atomic and pruned per flow; flow_runs keeps the audit row.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crewai.flow.persistence.base import FlowPersistence
from pydantic import ConfigDict

from nl_coding_agent.flows.state import (
    MAX_STATE_BYTES,
    SUPPORTED_SCHEMA_VERSION,
    UnsupportedStateSchemaError,
    canonical_state_json,
)
from nl_coding_agent.persistence import database

__all__ = [
    "FlowPersistenceError", "OversizedFlowStateError",
    "UnsupportedStateSchemaError", "AppFlowPersistence",
]

SNAPSHOT_KEEP = 50
_TERMINAL_FLOW_STATUSES = ("INTERRUPTED", "COMPLETED", "BLOCKED", "FAILED")
_PHASE_STATUS = {
    "planned": "RUNNING",
    "developing": "RUNNING",
    "verifying": "RUNNING",
    "repairing": "RUNNING",
    "reviewing": "RUNNING",
    "promoting": "RUNNING",
    "waiting_approval": "PAUSED_WAITING_APPROVAL",
    "interrupted": "INTERRUPTED",
    "completed": "COMPLETED",
    "blocked": "BLOCKED",
}


class FlowPersistenceError(RuntimeError):
    """Flow state could not be persisted/loaded safely."""


class OversizedFlowStateError(FlowPersistenceError):
    """The serialized state exceeds the 256 KiB guard (failure, not truncation)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state_payload(state_data: Any) -> dict:
    if hasattr(state_data, "model_dump"):
        payload = state_data.model_dump(mode="json")
    elif isinstance(state_data, dict):
        payload = dict(state_data)
    else:
        raise FlowPersistenceError(
            "Flow state must be a dict or a Pydantic model, got "
            + type(state_data).__name__
        )
    if not isinstance(payload, dict):
        raise FlowPersistenceError("Serialized flow state must be a JSON object")
    return payload


def _serialize_state(state_data: Any) -> tuple[dict, str, str, int]:
    payload = _state_payload(state_data)
    try:
        text = canonical_state_json(payload)
        # A second strict pass rejects NaN/Infinity and other non-JSON values.
        json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FlowPersistenceError("Flow state is not JSON-serializable: " + str(exc)) from exc
    size = len(text.encode("utf-8"))
    if size > MAX_STATE_BYTES:
        raise OversizedFlowStateError(
            "Flow state is " + str(size) + " bytes; limit is " + str(MAX_STATE_BYTES)
        )
    return payload, text, hashlib.sha256(text.encode("utf-8")).hexdigest(), size


class AppFlowPersistence(FlowPersistence):
    """FlowPersistence implementation writing only to the app SQLite database."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    persistence_type: str = "app_sqlite"
    db_path: str | None = None

    # ------------------------------------------------------------------ setup

    def _path(self) -> Path:
        return Path(self.db_path) if self.db_path else database.db_path()

    def _connect(self):
        return database.init_db(self._path())

    def init_db(self) -> None:
        conn = self._connect()
        try:
            pass
        finally:
            conn.close()

    # --------------------------------------------------------------- snapshots

    def save_state(self, flow_uuid: str, method_name: str,
                   state_data: dict[str, Any] | Any) -> None:
        flow_key = str(flow_uuid or "").strip()
        if not flow_key:
            raise FlowPersistenceError("flow_uuid is required")
        payload, state_json, sha, _size = _serialize_state(state_data)
        self._require_identity(flow_key, payload)
        conn = self._connect()
        try:
            with conn:
                self._insert_snapshot(conn, flow_key, str(method_name), state_json, sha)
                status = _PHASE_STATUS.get(str(payload.get("phase") or ""), "RUNNING")
                if str(payload.get("error_code") or "") == "executor_exception":
                    status = "FAILED"
                self._upsert_run(conn, flow_key, payload, str(method_name), sha, status)
                if status in _TERMINAL_FLOW_STATUSES:
                    self._prune_snapshots(conn, flow_key)
        finally:
            conn.close()

    def load_state(self, flow_uuid: str) -> dict[str, Any] | None:
        flow_key = str(flow_uuid or "").strip()
        if not flow_key:
            raise FlowPersistenceError("flow_uuid is required")
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM flow_states WHERE flow_uuid=? ORDER BY id DESC LIMIT 1",
                (flow_key,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["state_json"]))
        except ValueError as exc:
            raise FlowPersistenceError("Corrupt persisted flow state") from exc
        if not isinstance(payload, dict):
            raise FlowPersistenceError("Persisted flow state is not an object")
        schema = int(payload.get("schema_version") or 1)
        if schema > SUPPORTED_SCHEMA_VERSION:
            raise UnsupportedStateSchemaError(
                "Persisted flow state schema_version " + str(schema)
                + " is newer than supported " + str(SUPPORTED_SCHEMA_VERSION)
            )
        if str(payload.get("id") or "") != flow_key:
            raise FlowPersistenceError("Persisted flow state id does not match flow_uuid")
        return payload

    def snapshot_count(self, flow_uuid: str) -> int:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM flow_states WHERE flow_uuid=?",
                (str(flow_uuid),),
            ).fetchone()
            return int(row["n"])
        finally:
            conn.close()

    def list_snapshots(self, flow_uuid: str) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM flow_states WHERE flow_uuid=? ORDER BY id ASC",
                (str(flow_uuid),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # --------------------------------------------------------- pending feedback

    def save_pending_feedback(self, flow_uuid: str, context: Any,
                              state_data: Any) -> None:
        flow_key = str(flow_uuid or "").strip()
        if not flow_key:
            raise FlowPersistenceError("flow_uuid is required")
        payload, state_json, sha, _size = _serialize_state(state_data)
        self._require_identity(flow_key, payload)
        if hasattr(context, "to_dict"):
            context_data = context.to_dict()
        elif hasattr(context, "model_dump"):
            context_data = context.model_dump(mode="json")
        elif isinstance(context, dict):
            context_data = dict(context)
        else:
            raise FlowPersistenceError("Unsupported pending-feedback context")
        method_name = str(getattr(context, "method_name", "") or "pending_feedback")
        approval_id = getattr(context, "approval_id", None)
        context_json = json.dumps(context_data, ensure_ascii=False, sort_keys=True)
        now = _now_iso()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO flow_pending_feedback
                        (flow_uuid, approval_id, method_name, context_json,
                         state_json, created_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(flow_uuid) DO UPDATE SET
                        approval_id=excluded.approval_id,
                        method_name=excluded.method_name,
                        context_json=excluded.context_json,
                        state_json=excluded.state_json,
                        created_at=excluded.created_at
                    """,
                    (flow_key, int(approval_id) if approval_id is not None else None,
                     method_name, context_json, state_json, now),
                )
                self._insert_snapshot(conn, flow_key, method_name, state_json, sha)
                self._upsert_run(conn, flow_key, payload, method_name, sha,
                                 "PAUSED_WAITING_APPROVAL")
        finally:
            conn.close()

    def load_pending_feedback(self, flow_uuid: str):
        flow_key = str(flow_uuid or "").strip()
        if not flow_key:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM flow_pending_feedback WHERE flow_uuid=?", (flow_key,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            state = json.loads(str(row["state_json"]))
            context_data = json.loads(str(row["context_json"]))
        except ValueError as exc:
            raise FlowPersistenceError("Corrupt pending feedback row") from exc
        if int(state.get("schema_version") or 1) > SUPPORTED_SCHEMA_VERSION:
            raise UnsupportedStateSchemaError("Pending feedback state schema is newer")
        from crewai.flow.async_feedback.types import PendingFeedbackContext

        try:
            context = PendingFeedbackContext.from_dict(context_data)
        except Exception as exc:  # noqa: BLE001 - fail closed on corrupt context
            raise FlowPersistenceError("Corrupt pending feedback context") from exc
        return state, context

    def clear_pending_feedback(self, flow_uuid: str) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "DELETE FROM flow_pending_feedback WHERE flow_uuid=?",
                    (str(flow_uuid or "").strip(),),
                )
        finally:
            conn.close()

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _require_identity(flow_uuid: str, payload: dict) -> None:
        state_id = str(payload.get("id") or "").strip()
        if state_id and state_id != flow_uuid:
            raise FlowPersistenceError(
                "Flow state id " + state_id + " does not match flow_uuid " + flow_uuid
            )

    @staticmethod
    def _insert_snapshot(conn, flow_uuid: str, method_name: str,
                         state_json: str, sha: str) -> None:
        conn.execute(
            """
            INSERT INTO flow_states
                (flow_uuid, method_name, timestamp, state_sha256, state_json)
            VALUES (?,?,?,?,?)
            """,
            (flow_uuid, method_name, _now_iso(), sha, state_json),
        )

    @staticmethod
    def _upsert_run(conn, flow_uuid: str, payload: dict, method_name: str,
                    sha: str, status: str) -> None:
        now = _now_iso()
        existing = conn.execute(
            "SELECT status FROM flow_runs WHERE flow_id=?", (flow_uuid,)
        ).fetchone()
        final_status = status
        finished_at = (now if status in _TERMINAL_FLOW_STATUSES else None)
        if existing is not None:
            old = str(existing["status"] or "")
            if old in _TERMINAL_FLOW_STATUSES and status not in _TERMINAL_FLOW_STATUSES:
                # Durable-state-first: never regress a terminal run to RUNNING.
                final_status = old
            if old in _TERMINAL_FLOW_STATUSES:
                finished_at = None  # keep the recorded finish timestamp
        values = {
            "flow_id": flow_uuid,
            "project_id": int(payload.get("project_id") or 0),
            "mission_id": payload.get("mission_id"),
            "queue_id": payload.get("queue_id"),
            "supervisor_run_id": payload.get("supervisor_run_id"),
            "pipeline": "mission",
            "status": final_status,
            "last_method": method_name,
            "state_sha256": sha,
            "created_at": now,
            "updated_at": now,
            "finished_at": finished_at,
            "error_code": payload.get("error_code"),
            "error_message": payload.get("last_error"),
            "heartbeat_at": now,
        }
        conn.execute(
            """
            INSERT INTO flow_runs
                (flow_id, project_id, mission_id, queue_id, supervisor_run_id,
                 pipeline, status, last_method, state_sha256, created_at,
                 updated_at, finished_at, error_code, error_message, heartbeat_at)
            VALUES (:flow_id, :project_id, :mission_id, :queue_id,
                    :supervisor_run_id, :pipeline, :status, :last_method,
                    :state_sha256, :created_at, :updated_at, :finished_at,
                    :error_code, :error_message, :heartbeat_at)
            ON CONFLICT(flow_id) DO UPDATE SET
                status=excluded.status,
                last_method=excluded.last_method,
                state_sha256=excluded.state_sha256,
                updated_at=excluded.updated_at,
                heartbeat_at=excluded.heartbeat_at,
                error_code=COALESCE(excluded.error_code, flow_runs.error_code),
                error_message=COALESCE(excluded.error_message, flow_runs.error_message),
                finished_at=CASE WHEN flow_runs.finished_at IS NULL
                                 THEN excluded.finished_at
                                 ELSE flow_runs.finished_at END,
                mission_id=COALESCE(flow_runs.mission_id, excluded.mission_id),
                queue_id=COALESCE(flow_runs.queue_id, excluded.queue_id),
                supervisor_run_id=COALESCE(flow_runs.supervisor_run_id,
                                           excluded.supervisor_run_id)
            """,
            values,
        )

    @staticmethod
    def _prune_snapshots(conn, flow_uuid: str) -> None:
        conn.execute(
            """
            DELETE FROM flow_states
             WHERE flow_uuid=? AND id NOT IN (
                SELECT id FROM flow_states WHERE flow_uuid=?
                 ORDER BY id DESC LIMIT ?
             )
            """,
            (flow_uuid, flow_uuid, SNAPSHOT_KEEP),
        )

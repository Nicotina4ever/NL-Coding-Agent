"""Durable execution-failure evidence for missions, Flow runs and stage executors.

The engine must never lose the cause of an unexpected termination just because the
run died before a task attempt could be written.  This module is the single
place that captures an exception as bounded JSON Evidence, records it through the
existing mission evidence ledger, and leaves a human-readable handoff.  It does
not change mission status on its own; callers finalize state with their existing
single-writer APIs.
"""
from __future__ import annotations

import os
import socket
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "capture_exception",
    "record_exception",
    "record_running_task_failures",
]

MAX_TRACEBACK_CHARS = 64_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def capture_exception(exc: BaseException, *, source: str, method: str,
                      flow_id: str | None = None, mission_id: int | None = None,
                      task_id: int | None = None, phase: str | None = None,
                      extra: dict | None = None) -> dict:
    """Return a bounded, recoverable exception record (never raises)."""
    try:
        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception:
        text = repr(exc)
    chain: list[str] = []
    probe = exc
    for _ in range(8):
        linked = getattr(probe, "__cause__", None) or getattr(probe, "__context__", None)
        if linked is None or linked is probe:
            break
        chain.append(type(linked).__name__ + ": " + str(linked)[:2000])
        probe = linked
    payload = {
        "schema": "execution_error.v1",
        "source": str(source or "unknown"),
        "method": str(method or "unknown"),
        "flow_id": str(flow_id) if flow_id else None,
        "mission_id": int(mission_id) if mission_id is not None else None,
        "task_id": int(task_id) if task_id is not None else None,
        "phase": str(phase) if phase is not None else None,
        "exception_type": type(exc).__name__,
        "exception_module": type(exc).__module__,
        "message": str(exc)[:8000],
        "traceback": text[:MAX_TRACEBACK_CHARS],
        "traceback_truncated": len(text) > MAX_TRACEBACK_CHARS,
        "exception_chain": chain,
        "pid": os.getpid(),
        "host": socket.gethostname() or "unknown-host",
        "created_at": _now_iso(),
    }
    if extra:
        payload["extra"] = dict(extra)
    return payload


def record_exception(mission_id: int, exc: BaseException, *, source: str,
                     method: str, flow_id: str | None = None,
                     task_id: int | None = None, phase: str | None = None,
                     extra: dict | None = None) -> dict:
    """Persist one exception in the mission evidence ledger and a user handoff.

    Duplicate calls are intentionally separate records: each source (flow,
    supervisor, executor) represents a real observation of the same failure.
    Returns the bounded payload; storage errors are swallowed after a best effort
    because failure logging must never mask the original exception.
    """
    payload = capture_exception(
        exc, source=source, method=method, flow_id=flow_id, mission_id=mission_id,
        task_id=task_id, phase=phase, extra=extra,
    )
    record_key = "exec-" + uuid.uuid4().hex
    try:
        from nl_coding_agent.persistence import supervisor_store

        supervisor_store.record_evidence(
            int(mission_id), kind="execution_error", record_key=record_key,
            payload=payload,
        )
    except Exception:
        pass
    try:
        from nl_coding_agent.persistence.missions import record_handoff

        record_handoff(
            int(mission_id), "system", "user",
            "Execution failure at " + payload["source"] + "/" + payload["method"]
            + ": " + payload["exception_type"] + ": " + payload["message"][:500],
            {
                "kind": "execution_error",
                "evidence_key": record_key,
                "source": payload["source"],
                "method": payload["method"],
                "exception_type": payload["exception_type"],
                "message": payload["message"],
                "traceback_sample": payload["traceback"][-4000:],
                "task_id": payload["task_id"],
                "flow_id": payload["flow_id"],
            },
        )
    except Exception:
        pass
    return payload


def record_running_task_failures(mission_id: int, exc: BaseException, *,
                                 source: str, traceback_text: str = "") -> list[int]:
    """Fail tasks left in `running` and ensure an attempt exists for each.

    This covers the exact window observed in mission #1: a developer stage had
    already set its task to running (or was inside preparation) and the process
    failed before the normal attempt record was written.
    """
    failed: list[int] = []
    try:
        from nl_coding_agent.persistence.missions import (
            get_task_attempts,
            get_tasks,
            record_task_attempt,
            update_task_status,
        )

        for task in get_tasks(int(mission_id)):
            if str(task.get("status") or "") != "running":
                continue
            task_id = int(task["id"])
            attempts = get_task_attempts(task_id)
            has_failed_attempt = any(
                str(item.get("status") or "") == "failed" for item in attempts
            )
            if not has_failed_attempt:
                record_task_attempt(
                    task_id, "failed", output="",
                    error=type(exc).__name__ + ": " + str(exc)[:4000],
                    metadata={
                        "failure_source": source,
                        "failure_phase": "before_attempt_record",
                        "exception_type": type(exc).__name__,
                        "traceback_sample": (traceback_text or "")[-4000:],
                    },
                )
            update_task_status(task_id, "failed",
                               error=type(exc).__name__ + ": " + str(exc)[:4000])
            failed.append(task_id)
    except Exception:
        pass
    return failed

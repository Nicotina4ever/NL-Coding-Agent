"""C4b CrewAI Flow event -> application event/evidence bridge.

The bridge is read-only with respect to business state: it maps CrewAI flow
events to app Event objects and optional evidence records, deduplicates by
event identity and carries a correlation id. It never updates mission/queue/
promotion status.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Callable

__all__ = ["FlowEventBridge", "MAPPED_EVENT_TYPES"]

MAPPED_EVENT_TYPES: dict[str, tuple[str, str]] = {
    # CrewAI event type -> (app level, short kind)
    "flow_created": ("debug", "flow.created"),
    "flow_started": ("info", "flow.started"),
    "flow_finished": ("info", "flow.finished"),
    "flow_failed": ("error", "flow.failed"),
    "method_execution_started": ("debug", "flow.method.started"),
    "method_execution_finished": ("info", "flow.method.finished"),
    "method_execution_failed": ("error", "flow.method.failed"),
    "method_execution_paused": ("warning", "flow.paused"),
    "human_feedback_requested": ("info", "flow.approval.requested"),
    "human_feedback_received": ("info", "flow.approval.received"),
}

_MESSAGES: dict[str, str] = {
    "flow.created": "Flow created: {flow_name}",
    "flow.started": "Flow started: {flow_name}",
    "flow.finished": "Flow finished: {flow_name}",
    "flow.failed": "Flow failed: {flow_name}: {error}",
    "flow.method.started": "Flow method started: {method_name}",
    "flow.method.finished": "Flow method finished: {method_name}",
    "flow.method.failed": "Flow method failed: {method_name}: {error}",
    "flow.paused": "Flow paused waiting for human feedback: {method_name}",
    "flow.approval.requested": "Flow approval requested: {method_name}",
    "flow.approval.received": "Flow approval received: {method_name}",
}


def _as_dict(value: Any) -> dict | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="json")
            return dumped if isinstance(dumped, dict) else None
        except Exception:
            return None
    return dict(value) if isinstance(value, dict) else None


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


class FlowEventBridge:
    """Deterministic, idempotent CrewAI -> app event/evidence mapper."""

    def __init__(self, *, event_sink: Callable[[Any], None] | None = None,
                 evidence_sink: Callable[[dict], None] | None = None,
                 project_id: int | None = None,
                 mission_id: int | None = None,
                 flow_id: str | None = None,
                 source: str = "flow") -> None:
        self.event_sink = event_sink
        self.evidence_sink = evidence_sink
        self.project_id = int(project_id) if project_id is not None else None
        self.mission_id = int(mission_id) if mission_id is not None else None
        self.flow_id = str(flow_id) if flow_id else None
        self.source = str(source or "flow")
        self.seen_event_ids: set[str] = set()
        self.mapped: list[dict] = []

    # ------------------------------------------------------------------ mapping

    @staticmethod
    def _event_identity(event: Any) -> str:
        event_id = str(getattr(event, "event_id", "") or "").strip()
        if event_id:
            return event_id
        state = _as_dict(getattr(event, "state", None)) or {}
        parts = [
            str(getattr(event, "type", "") or ""),
            str(getattr(event, "flow_name", "") or ""),
            str(getattr(event, "method_name", "") or ""),
            str(state.get("id") or ""),
            _iso(getattr(event, "timestamp", None)) or "",
            str(getattr(event, "emission_sequence", "") or ""),
        ]
        return "sha256:" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _correlation_id(event: Any, fallback: str | None) -> str:
        state = _as_dict(getattr(event, "state", None)) or {}
        for candidate in (
            state.get("id"),
            getattr(event, "flow_id", None),
            getattr(event, "source_fingerprint", None),
            fallback,
            getattr(event, "flow_name", None),
        ):
            if candidate:
                return str(candidate)
        return "flow:" + str(getattr(event, "type", "unknown"))

    def handle(self, event: Any) -> dict | None:
        """Map one event; duplicate event identities return None (no double emit)."""
        event_type = str(getattr(event, "type", "") or "").strip()
        mapping = MAPPED_EVENT_TYPES.get(event_type)
        if mapping is None:
            return None
        identity = self._event_identity(event)
        if identity in self.seen_event_ids:
            return None
        self.seen_event_ids.add(identity)
        level, kind = mapping
        correlation_id = self._correlation_id(event, self.flow_id)
        flow_name = str(getattr(event, "flow_name", "") or "")
        method_name = str(getattr(event, "method_name", "") or "")
        error = getattr(event, "error", None)
        message = _MESSAGES.get(kind, kind).format(
            flow_name=flow_name or "?",
            method_name=method_name or "?",
            error=str(error) if error is not None else "",
        ).strip()
        state = _as_dict(getattr(event, "state", None)) or {}
        payload = {
            "event_type": event_type,
            "event_id": identity,
            "correlation_id": correlation_id,
            "flow_id": correlation_id if state.get("id") else self.flow_id,
            "flow_name": flow_name,
            "method_name": method_name or None,
            "phase": state.get("phase"),
            "mission_id": state.get("mission_id", self.mission_id),
            "project_id": state.get("project_id", self.project_id),
            "timestamp": _iso(getattr(event, "timestamp", None)),
        }
        mapped = {
            "source": self.source,
            "level": level,
            "message": message,
            "payload": payload,
            "kind": kind,
            "correlation_id": correlation_id,
            "event_id": identity,
        }
        self.mapped.append(mapped)
        if self.event_sink is not None:
            try:
                self.event_sink(_app_event(mapped))
            except Exception:
                pass
        if self.evidence_sink is not None:
            evidence = {
                "kind": "flow_event",
                "record_key": identity,
                "event_type": event_type,
                "correlation_id": correlation_id,
                "flow_id": payload.get("flow_id"),
                "method_name": method_name or None,
                "phase": payload.get("phase"),
                "level": level,
                "message": message,
            }
            try:
                self.evidence_sink(evidence)
            except Exception:
                pass
        return mapped

    def listener(self, source: Any, event: Any) -> dict | None:
        """CrewAI event-bus handler signature (source, event)."""
        return self.handle(event)

    def attach(self, bus: Any | None = None) -> "FlowEventBridge":
        """Register the bridge on a CrewAI event bus (no global default write)."""
        if bus is None:
            return self
        from crewai.events.types.flow_events import FlowEvent

        bus.on(FlowEvent)(self.listener)
        return self


def _app_event(mapped: dict):
    from nl_coding_agent.app.services import Event

    payload = dict(mapped["payload"])
    payload["kind"] = mapped["kind"]
    payload["correlation_id"] = mapped["correlation_id"]
    return Event(source=mapped["source"], level=mapped["level"],
                 message=mapped["message"], payload=payload)

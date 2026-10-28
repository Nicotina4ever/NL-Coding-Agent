"""C4d: deterministic HITL approval provider for CrewAI Flow human feedback.

The provider maps a pause request to a durable approvals row (no LLM involved),
optionally flags the durable queue/run as WAIT_APPROVAL, emits an application event
and raises CrewAI's HumanFeedbackPending. Decision/outcome matching is exact-label,
deterministic and default-deny; a model can never collapse/approve a risky request.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from crewai.flow.async_feedback.types import HumanFeedbackPending, PendingFeedbackContext
from nl_coding_agent.persistence import supervisor_store as store

__all__ = [
    "classify_approval", "normalize_feedback", "GuiApprovalProvider",
    "ApprovalOutcome", "DEFAULT_EMIT",
]

DEFAULT_EMIT = ["approved", "rejected", "changes_requested"]
_ACTION_TOKENS = (
    ("delete", "delete"), ("network", "network"), ("cloud", "cloud"),
    ("install", "install"), ("publish", "publish"), ("migrate", "migrate"),
    ("external_tool", "external_tool"), ("external tool", "external_tool"),
    ("approval", "review"), ("review", "review"),
)


class ApprovalOutcome:
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CHANGES = "changes_requested"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def classify_approval(method_name: str, phase: str = "", last_error: str = "") -> str:
    """Deterministic method/phase/error -> approval action (never model-derived)."""
    text = " ".join((str(method_name or ""), str(phase or ""), str(last_error or ""))).lower()
    for token, action in _ACTION_TOKENS:
        if token in text:
            return action
    return "review"


def normalize_feedback(feedback: Any, emit=None) -> str:
    """Exact/label match against the declared outcomes; anything else is rejected."""
    labels = [str(item) for item in (emit or DEFAULT_EMIT)]
    text = _norm(feedback if isinstance(feedback, str) else str(feedback or ""))
    for label in labels:
        candidate = _norm(label)
        if text == candidate or text.startswith(candidate + " "):
            return label
        if text in {"yes", "approve", "approved", "ok", "accept", "accepted"} and candidate.startswith("approv"):
            return label
        if text in {"no", "reject", "rejected", "deny", "denied", "refuse", "refused"} and candidate.startswith("reject"):
            return label
        if text in {"changes", "change", "changes requested", "request changes"} and candidate.startswith("changes"):
            return label
    return "rejected"


class GuiApprovalProvider:
    """Durable approval provider (GUI/CLI/backend); interactive input is never used."""

    def __init__(self, project_id: int, *, mission_id: int | None = None,
                 queue_id: int | None = None, supervisor_run_id: int | None = None,
                 requested_by: str = "flow", ttl_s: int = 3600,
                 event_sink: Callable[[Any], None] | None = None,
                 store_module=store) -> None:
        self.project_id = int(project_id)
        self.mission_id = int(mission_id) if mission_id is not None else None
        self.queue_id = int(queue_id) if queue_id is not None else None
        self.supervisor_run_id = int(supervisor_run_id) if supervisor_run_id is not None else None
        self.requested_by = str(requested_by)
        self.ttl_s = int(ttl_s)
        self.event_sink = event_sink
        self.store = store_module

    # ------------------------------------------------------------ request side

    def request_feedback(self, context: PendingFeedbackContext, flow: Any = None):
        state = getattr(flow, "state", None)
        phase = str(getattr(state, "phase", "") or "")
        last_error = str(getattr(state, "last_error", "") or "")
        action = classify_approval(context.method_name, phase, last_error)
        mission_id = getattr(state, "mission_id", None) or self.mission_id
        queue_id = getattr(state, "queue_id", None) or self.queue_id
        supervisor_run_id = getattr(state, "supervisor_run_id", None) or self.supervisor_run_id
        approval_id = self.store.create_flow_approval(
            self.project_id, flow_id=str(context.flow_id),
            mission_id=mission_id, queue_id=queue_id,
            supervisor_run_id=supervisor_run_id, method_name=str(context.method_name),
            action=action, reason=str(context.message or "")[:2000],
            requested_by=self.requested_by, ttl_s=self.ttl_s,
        )
        if queue_id is not None:
            try:
                self.store.update_queue_item(int(queue_id), state="INTERRUPTED",
                                             failure_class="WAIT_APPROVAL")
            except Exception:
                pass
        if supervisor_run_id is not None:
            try:
                self.store.update_run(int(supervisor_run_id),
                                      status="WAITING_FOR_APPROVAL")
            except Exception:
                pass
        try:
            from nl_coding_agent.app.services import Event, get_event_bus

            bus = get_event_bus()
            if self.event_sink is not None:
                self.event_sink(Event(
                    source="flow", level="warning",
                    message="Flow approval requested: " + str(context.method_name),
                    payload={"kind": "flow.approval.requested", "approval_id": approval_id,
                             "flow_id": str(context.flow_id), "action": action},
                ))
            else:
                bus.emit(Event(
                    source="flow", level="warning",
                    message="Flow approval requested: " + str(context.method_name),
                    payload={"kind": "flow.approval.requested", "approval_id": approval_id,
                             "flow_id": str(context.flow_id), "action": action},
                ))
        except Exception:
            pass
        raise HumanFeedbackPending(
            context=context,
            callback_info={"approval_id": approval_id, "action": action,
                           "flow_id": str(context.flow_id)},
        )

    # ----------------------------------------------------------- decide/resume

    def outcome(self, approval_id: int) -> dict:
        approval = self.store.get_approval(int(approval_id))
        if approval is None:
            return {"approval_id": int(approval_id), "outcome": "missing"}
        return {
            "approval_id": int(approval_id), "outcome": str(approval["status"]),
            "action": approval.get("action"), "mission_id": approval.get("mission_id"),
            "flow_id": (approval.get("scope") or {}).get("flow_id"),
            "reason": (approval.get("scope") or {}).get("_decision_reason") or "",
        }

    def resume_outcome(self, flow_id: str) -> str:
        return self.store.flow_approval_outcome(str(flow_id))

    def decide(self, approval_id: int, *, approved: bool, decided_by: str,
               reason: str = "") -> dict:
        ok = self.store.decide_approval(int(approval_id), approved=approved,
                                        decided_by=decided_by, reason=reason)
        return {"ok": bool(ok), **self.outcome(approval_id)}

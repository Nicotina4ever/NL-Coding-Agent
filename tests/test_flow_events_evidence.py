"""C4b: CrewAI Flow event -> app event/evidence bridge (dedupe, no status writes)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from crewai.events.types.flow_events import (
    FlowFailedEvent,
    FlowFinishedEvent,
    FlowStartedEvent,
    HumanFeedbackRequestedEvent,
    MethodExecutionFailedEvent,
    MethodExecutionFinishedEvent,
    MethodExecutionStartedEvent,
)
from nl_coding_agent.app.services import Event
from nl_coding_agent.flows.events import FlowEventBridge
from nl_coding_agent.persistence import missions
from nl_coding_agent.persistence import supervisor_store as store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))


def make_bridge(flow_id="flow-events-1"):
    events: list[Event] = []
    evidence: list[dict] = []
    bridge = FlowEventBridge(
        event_sink=events.append, evidence_sink=evidence.append,
        flow_id=flow_id, mission_id=5, project_id=2,
    )
    return bridge, events, evidence


def test_flow_started_maps_to_app_event_with_correlation():
    bridge, events, evidence = make_bridge()
    event = FlowStartedEvent(flow_name="MissionFlow", inputs={"id": "flow-events-1"})
    mapped = bridge.handle(event)
    assert mapped is not None
    assert mapped["level"] == "info"
    assert "Flow started" in mapped["message"]
    assert mapped["correlation_id"] == "flow-events-1"
    assert len(events) == 1
    assert isinstance(events[0], Event)
    assert events[0].source == "flow"
    assert events[0].payload["event_type"] == "flow_started"
    assert events[0].payload["event_id"] == event.event_id
    assert evidence[0]["kind"] == "flow_event"
    assert evidence[0]["record_key"] == event.event_id
    assert evidence[0]["flow_id"] == "flow-events-1"


def test_method_events_carry_flow_state_correlation_and_dedupe():
    bridge, events, evidence = make_bridge()
    event = MethodExecutionFinishedEvent(
        flow_name="MissionFlow", method_name="verify",
        state={"id": "flow-state-id", "phase": "reviewing"}, result="ok",
    )
    first = bridge.handle(event)
    second = bridge.handle(event)
    assert first is not None and second is None
    assert len(events) == 1 and len(evidence) == 1
    assert first["correlation_id"] == "flow-state-id"
    assert first["payload"]["method_name"] == "verify"
    assert first["payload"]["phase"] == "reviewing"
    started = MethodExecutionStartedEvent(
        flow_name="MissionFlow", method_name="review",
        state={"id": "flow-state-id", "phase": "reviewing"},
    )
    assert bridge.handle(started)["level"] == "debug"


def test_failure_events_map_to_error_level():
    bridge, events, _ = make_bridge()
    bridge.handle(FlowFailedEvent(flow_name="MissionFlow",
                                  error=RuntimeError("flow exploded")))
    bridge.handle(MethodExecutionFailedEvent(
        flow_name="MissionFlow", method_name="promote",
        error=RuntimeError("promotion failed"),
    ))
    assert [event.level for event in events] == ["error", "error"]
    assert "flow exploded" in events[0].message
    assert "promotion failed" in events[1].message


def test_human_feedback_requested_maps_without_writing_status():
    bridge, events, evidence = make_bridge()
    event = HumanFeedbackRequestedEvent(
        flow_name="MissionFlow", method_name="review",
        output={"draft": "candidate"}, message="approve?",
    )
    with patch.object(missions, "update_mission_status",
                      side_effect=AssertionError("no status write")), \
         patch.object(missions, "update_mission_result",
                      side_effect=AssertionError("no status write")), \
         patch.object(missions, "set_promotion_status",
                      side_effect=AssertionError("no status write")), \
         patch.object(store, "update_queue_item",
                      side_effect=AssertionError("no status write")):
        bridge.handle(event)
    assert events[0].level == "info"
    assert "approval requested" in events[0].message.lower()
    assert evidence[0]["method_name"] == "review"


def test_unknown_events_are_ignored():
    bridge, events, evidence = make_bridge()

    class PlotEvent:
        type = "flow_plot"
        event_id = "plot-1"
        flow_name = "MissionFlow"

    assert bridge.handle(PlotEvent()) is None
    assert events == [] and evidence == []


def test_correlation_falls_back_to_bridge_flow_id_and_attach_works():
    bridge, _, _ = make_bridge(flow_id="fallback-flow")
    mapped = bridge.handle(FlowFinishedEvent(flow_name="MissionFlow",
                                             result="done", state={}))
    assert mapped["correlation_id"] == "fallback-flow"

    class FakeBus:
        def __init__(self):
            self.handlers = []

        def on(self, event_type):
            def register(handler):
                self.handlers.append(handler)
                return handler
            return register

    bus = FakeBus()
    assert bridge.attach(bus) is bridge
    assert len(bus.handlers) == 1
    fresh_event = FlowStartedEvent(flow_name="MissionFlow")
    assert bus.handlers[0](None, fresh_event)["level"] == "info"

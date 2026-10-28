"""C4e: CrewAI SBOM/compat gate - pins, API baseline, deterministic artifact, no vendor import."""
from __future__ import annotations

import importlib.metadata as metadata
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_crewai_upgrade.py"
SBOM = REPO / "docs" / "evidence" / "crewai_sbom.json"


def load_script():
    spec = importlib.util.spec_from_file_location("check_crewai_upgrade", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sbom_is_deterministic_and_matches_installed_pins():
    script = load_script()
    first = script.build_sbom()
    second = script.build_sbom()
    assert script._canonical(first) == script._canonical(second)
    chain = first["pinned_chain"]
    assert set(chain) == {"crewai", "crewai-core", "crewai-cli"}
    assert chain["crewai"] == metadata.version("crewai")
    assert chain["crewai-core"] == metadata.version("crewai-core")
    assert chain["crewai"] == chain["crewai-core"]
    assert first["app_pins"]["crewai_pin_matches_installed"] is True
    assert first["app_pins"]["crewai_core_pin"] is None
    assert first["app_pins"]["crewai_core_pin_gap"] is True
    assert first["pinned_chain_versions_aligned"] is True
    assert first["license_evidence"]["unknown_licenses"] == [
        "crewai", "crewai-cli", "crewai-core",
    ]
    assert first["import_path_evidence"]["vendor_checkout_import"] is False
    assert first["import_path_evidence"]["under_site_packages"] is True
    assert first["rollout_decision"]["default_pipeline"] == "sequential"
    assert first["rollout_decision"]["flow_pipeline"] == "opt-in only"


def test_committed_sbom_verifies_and_detects_tampering(tmp_path):
    script = load_script()
    ok, detail = script.verify_sbom(SBOM)
    assert ok is True, detail
    payload = json.loads(SBOM.read_text(encoding="utf-8"))
    payload["pinned_chain"]["crewai-core"] = "0.0.0-tampered"
    tampered = tmp_path / "sbom.json"
    tampered.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    ok, detail = script.verify_sbom(tampered)
    assert ok is False and "drift" in detail.lower()


def test_api_compat_baseline_used_by_backend_is_complete():
    script = load_script()
    results = script.build_sbom()["api_compat"]
    missing = [item["target"] for item in results if not item["ok"]]
    assert missing == []
    targets = {item["target"] for item in results}
    for required in (
        "crewai.Agent", "crewai.Crew", "crewai.Task", "crewai.LLM", "crewai.Process",
        "crewai.flow.flow.Flow", "crewai.flow.flow.FlowState",
        "crewai.flow.persistence.FlowPersistence", "crewai.flow.persistence.persist",
        "crewai.flow.async_feedback.HumanFeedbackPending",
    ):
        assert required in targets


def test_installed_crewai_surface_and_no_vendor_import():
    import crewai
    from crewai import Agent, Crew, LLM, Process, Task
    from crewai.flow.flow import Flow, FlowState, listen, router, start
    from crewai.flow.persistence import FlowPersistence, persist
    from crewai.flow.async_feedback.types import (
        HumanFeedbackPending, HumanFeedbackProvider, PendingFeedbackContext,
    )
    from crewai.events.types.flow_events import (
        FlowEvent, FlowStartedEvent, MethodExecutionFinishedEvent,
    )
    for symbol in (Agent, Crew, LLM, Process, Task, Flow, FlowState, listen, router,
                   start, FlowPersistence, persist, HumanFeedbackPending,
                   HumanFeedbackProvider, PendingFeedbackContext, FlowEvent,
                   FlowStartedEvent, MethodExecutionFinishedEvent):
        assert symbol is not None
    crewai_file = Path(crewai.__file__).resolve()
    assert "python" in [part.lower() for part in crewai_file.parts[:2]] or "site-packages" in str(crewai_file)
    assert "crewAI" not in crewai_file.parts
    assert metadata.version("crewai") == "1.15.32"


def test_sbom_generation_does_not_use_network(monkeypatch):
    script = load_script()

    def _no_network(*args, **kwargs):
        raise AssertionError("SBOM generation must not use the network")

    monkeypatch.setattr(socket, "socket", _no_network)
    payload = script.build_sbom()
    assert payload["api_compat"]

"""C2: deterministic model-invocation seam (no LLM calls)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.agents import orchestrator as orchestrator_module
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator


class FakeCrew:
    instances = []

    def __init__(self, agents, tasks, process, verbose):
        self.agents = agents
        self.tasks = tasks
        self.process = process
        self.verbose = verbose
        self.kicked = False
        FakeCrew.instances.append(self)

    def kickoff(self):
        self.kicked = True
        return "APPROVE\nfake review output"


def test_call_model_uses_crewai_seam():
    FakeCrew.instances.clear()
    with tempfile.TemporaryDirectory() as tmp:
        orch = MultiAgentOrchestrator(Path(tmp))
        with patch.object(orchestrator_module, "Crew", FakeCrew):
            result = orch._call_model("agent", "task")
    assert result == "APPROVE\nfake review output"
    assert len(FakeCrew.instances) == 1
    assert FakeCrew.instances[0].kicked is True


def test_call_model_is_monkeypatchable_for_fake_models():
    with tempfile.TemporaryDirectory() as tmp:
        orch = MultiAgentOrchestrator(Path(tmp))
        calls = {}

        def fake(agent, task):
            calls["agent"] = agent
            calls["task"] = task
            return "```write:nl_coding_agent/example.py\ndef f():\n    return 1\n```"

        orch._call_model = fake
        output = orch._call_model("developer", "task")
    assert "write:nl_coding_agent/example.py" in output
    assert calls == {"agent": "developer", "task": "task"}

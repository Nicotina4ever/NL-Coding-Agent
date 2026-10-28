"""C2/C6: deterministic model-invocation seam (single CrewAI construction point)."""
from __future__ import annotations

import re
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
            result = orch._call_model(
                "Implementation Developer",
                "ollama/test-model",
                "PROMPT BODY",
                goal="Implement the change",
                backstory="Senior engineer",
                expected_output="APPROVE or REJECT",
            )
    assert result == "APPROVE\nfake review output"
    assert len(FakeCrew.instances) == 1
    crew = FakeCrew.instances[0]
    assert crew.kicked is True
    assert crew.process is orchestrator_module.Process.sequential
    assert len(crew.agents) == 1
    assert len(crew.tasks) == 1
    assert crew.agents[0].role == "Implementation Developer"
    assert crew.agents[0].goal == "Implement the change"
    assert crew.tasks[0].description == "PROMPT BODY"
    assert crew.tasks[0].expected_output == "APPROVE or REJECT"


def test_call_model_passes_tools_through_to_the_agent():
    FakeCrew.instances.clear()
    with tempfile.TemporaryDirectory() as tmp:
        orch = MultiAgentOrchestrator(Path(tmp))
        sentinel_tools = []
        with patch.object(orchestrator_module, "Crew", FakeCrew):
            orch._call_model(
                "Software Debugger",
                "ollama/test-model",
                "prompt",
                goal="g",
                backstory="b",
                expected_output="e",
                tools=sentinel_tools,
            )
    assert FakeCrew.instances[0].agents[0].tools == sentinel_tools


def test_call_model_is_monkeypatchable_for_fake_models():
    with tempfile.TemporaryDirectory() as tmp:
        orch = MultiAgentOrchestrator(Path(tmp))
        calls = {}

        def fake(role, model_name, prompt, *, goal, backstory, expected_output, tools=None):
            calls.update({
                "role": role,
                "model_name": model_name,
                "prompt": prompt,
                "goal": goal,
                "backstory": backstory,
                "expected_output": expected_output,
                "tools": tools,
            })
            return "```write:nl_coding_agent/example.py\ndef f():\n    return 1\n```"

        orch._call_model = fake
        output = orch._call_model(
            "developer",
            "ollama/test-model",
            "task prompt",
            goal="goal",
            backstory="backstory",
            expected_output="expected",
        )
    assert "write:nl_coding_agent/example.py" in output
    assert calls["role"] == "developer"
    assert calls["model_name"] == "ollama/test-model"
    assert calls["prompt"] == "task prompt"
    assert calls["goal"] == "goal"
    assert calls["backstory"] == "backstory"
    assert calls["expected_output"] == "expected"
    assert calls["tools"] is None


def test_agent_task_crew_construction_only_in_call_model():
    """No stage method may build CrewAI objects: the seam is the only construction point."""
    source = Path(orchestrator_module.__file__).read_text(encoding="utf-8")
    assert len(re.findall(r"\bAgent\(", source)) == 1
    assert len(re.findall(r"\bTask\(", source)) == 1
    assert len(re.findall(r"\bCrew\(", source)) == 1

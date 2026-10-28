"""C2/C6/C4a: deterministic model-invocation seam and CrewRuntime construction point."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl_coding_agent.agents import crew_backend as backend_module
from nl_coding_agent.agents import orchestrator as orchestrator_module
from nl_coding_agent.agents.crew_backend import (
    CrewAIBackend,
    CrewRuntime,
    FakeCrewRuntime,
)
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.agents.specs import UnknownRoleError, get_role


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("_make_llm must not be called: tests inject a fake runtime")

    monkeypatch.setattr(orchestrator_module, "_make_llm", _boom)


class FakeAgent:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeAgent.instances.append(self)


class FakeTask:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeTask.instances.append(self)


class FakeCrew:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.kicked = False
        FakeCrew.instances.append(self)

    def kickoff(self):
        self.kicked = True
        return "APPROVE\nfake review output"


def test_call_model_uses_injected_crew_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = FakeCrewRuntime({"Implementation Developer": ["APPROVE\nfake"]})
        orch = MultiAgentOrchestrator(Path(tmp), crew_runtime=runtime)
        result = orch._call_model(
            "Implementation Developer",
            "ollama/test-model",
            "PROMPT BODY",
            goal="Implement the change",
            backstory="Senior engineer",
            expected_output="APPROVE or REJECT",
        )
    assert result == "APPROVE\nfake"
    assert runtime.calls[0]["role_id"] == "developer"
    assert runtime.calls[0]["prompt"] == "PROMPT BODY"
    assert runtime.calls[0]["expected_output"] == "APPROVE or REJECT"


def test_call_model_passes_tools_through_the_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = FakeCrewRuntime({"Software Debugger": ["fixed"]})
        orch = MultiAgentOrchestrator(Path(tmp), crew_runtime=runtime)
        sentinel_tools = [SimpleNamespace(name="read_file")]
        output = orch._call_model(
            "Software Debugger", "ollama/test-model", "prompt",
            goal="g", backstory="b", expected_output="e", tools=sentinel_tools,
        )
    assert output == "fixed"
    assert runtime.calls[0]["tools"] is sentinel_tools
    assert runtime.calls[0]["role_id"] == "debugger"


def test_call_model_rejects_unknown_roles():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = FakeCrewRuntime({})
        orch = MultiAgentOrchestrator(Path(tmp), crew_runtime=runtime)
        with pytest.raises(UnknownRoleError):
            orch._call_model("Nope", "ollama/m", "p", goal="g", backstory="b",
                             expected_output="e")
    assert runtime.calls == []


def test_call_model_is_monkeypatchable_for_fake_models():
    with tempfile.TemporaryDirectory() as tmp:
        orch = MultiAgentOrchestrator(Path(tmp), crew_runtime=FakeCrewRuntime({}))
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
            "developer", "ollama/test-model", "task prompt",
            goal="goal", backstory="backstory", expected_output="expected",
        )
    assert "write:nl_coding_agent/example.py" in output
    assert calls["role"] == "developer"
    assert calls["model_name"] == "ollama/test-model"
    assert calls["prompt"] == "task prompt"
    assert calls["goal"] == "goal"
    assert calls["backstory"] == "backstory"
    assert calls["expected_output"] == "expected"
    assert calls["tools"] is None


def test_default_runtime_is_crewai_backend_with_project_scope():
    with tempfile.TemporaryDirectory() as tmp:
        orch = MultiAgentOrchestrator(Path(tmp), project_id=5)
        assert isinstance(orch.crew_runtime, CrewRuntime)
        assert isinstance(orch.crew_runtime, CrewAIBackend)
        assert orch.crew_runtime.project_id == 5
        orch.crew_runtime.close()


def test_crew_backend_builds_one_single_agent_sequential_crew(monkeypatch):
    FakeAgent.instances.clear()
    FakeTask.instances.clear()
    FakeCrew.instances.clear()
    monkeypatch.setattr(backend_module, "Agent", FakeAgent)
    monkeypatch.setattr(backend_module, "Task", FakeTask)
    monkeypatch.setattr(backend_module, "Crew", FakeCrew)
    backend = CrewAIBackend(llm_factory=lambda *a, **k: "fake-llm")
    result = backend.run_agent(
        get_role("developer"), "PROMPT BODY",
        goal="Implement the change", backstory="Senior engineer",
        model_name="ollama/test-model", expected_output="APPROVE or REJECT",
    )
    assert result.text == "APPROVE\nfake review output"
    assert len(FakeCrew.instances) == 1
    crew = FakeCrew.instances[0]
    assert crew.kicked is True
    assert crew.kwargs["process"] is backend_module.Process.sequential
    assert crew.kwargs["verbose"] is True
    assert len(crew.kwargs["agents"]) == 1
    assert len(crew.kwargs["tasks"]) == 1
    agent = crew.kwargs["agents"][0]
    assert agent.kwargs["role"] == "Implementation Developer"
    assert agent.kwargs["goal"] == "Implement the change"
    assert agent.kwargs["backstory"] == "Senior engineer"
    assert agent.kwargs["llm"] == "fake-llm"
    assert agent.kwargs["allow_delegation"] is False
    assert crew.kwargs["tasks"][0].kwargs["description"] == "PROMPT BODY"
    assert crew.kwargs["tasks"][0].kwargs["expected_output"] == "APPROVE or REJECT"


def test_agent_task_crew_construction_lives_only_in_the_backend():
    """No stage/orchestrator code may construct CrewAI objects."""
    orchestrator_source = Path(orchestrator_module.__file__).read_text(encoding="utf-8")
    assert len(re.findall(r"\bAgent\(", orchestrator_source)) == 0
    assert len(re.findall(r"\bTask\(", orchestrator_source)) == 0
    assert len(re.findall(r"\bCrew\(", orchestrator_source)) == 0
    assert "crew_runtime.run_agent(" in orchestrator_source
    backend_source = Path(backend_module.__file__).read_text(encoding="utf-8")
    assert len(re.findall(r"\bAgent\(", backend_source)) == 1
    assert len(re.findall(r"\bTask\(", backend_source)) == 1
    assert len(re.findall(r"\bCrew\(", backend_source)) == 2

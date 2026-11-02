"""C4a: CrewRuntime seam, CrewAI construction mapping, typed specs, fake runtime.

No Ollama/CrewAI network call is made: the production backend's LLM factory and
CrewAI objects are injected/patched; FakeCrewRuntime is the fake seam.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from nl_coding_agent.agents import crew_backend as backend_module
from nl_coding_agent.agents import orchestrator as orchestrator_module
from nl_coding_agent.agents.crew_backend import (
    AgentResult,
    CrewAIBackend,
    CrewRuntime,
    CrewRuntimeError,
    CrewRuntimeRefusedError,
    CrewRuntimeUnavailableError,
    FakeCrewRuntime,
    build_agent,
    build_crew,
    build_task,
    crew_runtime_env,
)
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.agents.specs import (
    AgentSpec,
    CrewSpec,
    DelegationPolicy,
    MemoryPolicy,
    ROLE_CATALOG,
    SpecError,
    TaskSpec,
    UnknownRoleError,
    all_roles,
    get_role,
    resolve_role,
    write_stage_roles,
)
from nl_coding_agent.core.permissions import PermissionDenied


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Any hidden LLM construction in this module fails loudly."""

    def _boom(*args, **kwargs):
        raise AssertionError("_make_llm must not be called in C4a tests")

    monkeypatch.setattr(orchestrator_module, "_make_llm", _boom)


class RecordingAgent:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        RecordingAgent.instances.append(self)


class RecordingTask:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        RecordingTask.instances.append(self)


class RecordingCrew:
    instances: list = []
    output: str = "APPROVE\nfake backend output"
    raises: Exception | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.kicked = False
        RecordingCrew.instances.append(self)

    def kickoff(self):
        self.kicked = True
        if RecordingCrew.raises is not None:
            raise RecordingCrew.raises
        return RecordingCrew.output


@pytest.fixture()
def recording_crewai(monkeypatch):
    RecordingAgent.instances.clear()
    RecordingTask.instances.clear()
    RecordingCrew.instances.clear()
    RecordingCrew.output = "APPROVE\nfake backend output"
    RecordingCrew.raises = None
    monkeypatch.setattr(backend_module, "Agent", RecordingAgent)
    monkeypatch.setattr(backend_module, "Task", RecordingTask)
    monkeypatch.setattr(backend_module, "Crew", RecordingCrew)
    return SimpleNamespace(
        Agent=RecordingAgent, Task=RecordingTask, Crew=RecordingCrew,
    )


def llm_sentinel(*args, **kwargs):
    return "fake-llm"


# --------------------------------------------------------------------------- #
# Environment and specs
# --------------------------------------------------------------------------- #

def test_crew_runtime_env_flags_and_freshness():
    expected = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "1",
        "OTEL_SDK_DISABLED": "1",
        "CREWAI_DISABLE_TELEMETRY": "1",
        "CREWAI_DISABLE_TRACKING": "1",
    }
    first = crew_runtime_env()
    second = crew_runtime_env()
    assert first == expected
    assert second == expected
    assert first is not second


def test_agent_spec_validation_and_goal_template():
    spec = AgentSpec(
        role_id="developer", display_role="Implementation Developer",
        goal_template="Implement: {goal}", backstory="Engineer",
        model_role="developer", tools_policy="stage_write",
    )
    assert spec.build_goal("X") == "Implement: X"
    assert spec.capability_requirements == ()

    bad_cases = [
        dict(role_id="Bad-Role", display_role="D", goal_template="g",
             backstory="b", model_role="developer"),
        dict(role_id="x", display_role="", goal_template="g", backstory="b",
             model_role="developer"),
        dict(role_id="x", display_role="D", goal_template="g", backstory="b",
             model_role="developer", tools_policy="shell"),
        dict(role_id="x", display_role="D", goal_template="g", backstory="b",
             model_role="developer", tools_policy="stage_write",
             allow_delegation=True),
        dict(role_id="x", display_role="D", goal_template="g", backstory="b",
             model_role=None),
        dict(role_id="x", display_role="D", goal_template="g", backstory="b",
             model_role="developer", max_iter=0),
        dict(role_id="x", display_role="D", goal_template="g", backstory="b",
             model_role="developer", temperature=2.5),
        dict(role_id="x", display_role="D", goal_template="g", backstory="b",
             model_role="developer", capability_requirements=("",)),
    ]
    for kwargs in bad_cases:
        with pytest.raises(SpecError):
            AgentSpec(**kwargs)

    deterministic = AgentSpec(
        role_id="tester", display_role="Deterministic Tester",
        goal_template="Verify", backstory="Deterministic",
        requires_llm=False, tools_policy="none",
    )
    assert deterministic.requires_llm is False


def test_role_catalog_and_resolution():
    developer = get_role("developer")
    assert developer.display_role == "Implementation Developer"
    assert developer.tools_policy == "stage_write"
    assert developer.allow_delegation is False
    assert resolve_role("developer") is developer
    assert resolve_role("Implementation Developer") is developer
    assert resolve_role("Code Reviewer & Quality Gatekeeper").role_id == "reviewer"
    with pytest.raises(UnknownRoleError):
        get_role("no-such-role")
    with pytest.raises(UnknownRoleError):
        resolve_role("No Such Display Role")
    assert len(all_roles()) == len(ROLE_CATALOG) == 7
    assert {spec.role_id for spec in write_stage_roles()} == {"developer", "debugger"}
    with pytest.raises(TypeError):
        ROLE_CATALOG["hacker"] = developer  # type: ignore[index]
    assert get_role("tester").requires_llm is False


def test_task_and_crew_spec_validation():
    developer = get_role("developer")
    reviewer = get_role("reviewer")
    task = TaskSpec(
        task_id="impl", description_template="Do {goal}", expected_output="done",
        agent_role_id="developer", context=("a",),
        output_json={"type": "object"},
    )
    assert task.render_description(goal="X") == "Do X"
    with pytest.raises(TypeError):
        task.output_json["x"] = 1  # type: ignore[index]

    crew = CrewSpec(
        crew_id="write-stage", agents=(developer,), tasks=(task,),
    )
    assert crew.process == "sequential"
    assert crew.memory_policy == "off"
    assert crew.memory.enabled is False

    with pytest.raises(SpecError):
        CrewSpec(crew_id="x", process="parallel", agents=(developer,), tasks=(task,))
    with pytest.raises(SpecError):
        CrewSpec(crew_id="x", agents=(developer, developer), tasks=(task,))
    with pytest.raises(SpecError):
        CrewSpec(crew_id="x", agents=(reviewer,), tasks=(task,))
    with pytest.raises(SpecError):
        CrewSpec(crew_id="x", process="hierarchical", agents=(developer,),
                 tasks=(task,))
    with pytest.raises(SpecError):
        CrewSpec(crew_id="x", memory_policy="local", agents=(developer,),
                 tasks=(task,))
    with pytest.raises(SpecError):
        MemoryPolicy(enabled=True)
    with pytest.raises(SpecError):
        DelegationPolicy(allow=True, max_depth=1, allowlist=())
    with pytest.raises(SpecError):
        TaskSpec(task_id="t", description_template="", expected_output="e",
                 agent_role_id="developer")


# --------------------------------------------------------------------------- #
# Builders and production backend
# --------------------------------------------------------------------------- #

def test_build_agent_task_crew_mapping(recording_crewai):
    developer = get_role("developer")
    tools = [SimpleNamespace(name="read_file")]
    agent = build_agent(
        developer, goal="goal", backstory="backstory", model_name="ollama/dev",
        project_id=3, tools=tools, llm_factory=llm_sentinel,
    )
    assert isinstance(agent, RecordingAgent)
    assert agent.kwargs["role"] == "Implementation Developer"
    assert agent.kwargs["goal"] == "goal"
    assert agent.kwargs["backstory"] == "backstory"
    assert agent.kwargs["llm"] == "fake-llm"
    assert agent.kwargs["tools"] == tools
    assert agent.kwargs["verbose"] is True
    assert agent.kwargs["allow_delegation"] is False
    assert "max_iter" not in agent.kwargs

    task_spec = TaskSpec(task_id="t", description_template="desc",
                         expected_output="expected", agent_role_id="developer")
    task = build_task(task_spec, agent, description="desc")
    assert isinstance(task, RecordingTask)
    assert task.kwargs == {"description": "desc", "expected_output": "expected",
                           "agent": agent}

    crew = build_crew(
        CrewSpec(crew_id="c", agents=(developer,), tasks=(task_spec,), verbose=True),
        [agent], [task],
    )
    assert isinstance(crew, RecordingCrew)
    assert crew.kwargs["agents"] == [agent]
    assert crew.kwargs["tasks"] == [task]
    assert crew.kwargs["process"] is backend_module.Process.sequential
    assert crew.kwargs["verbose"] is True
    assert crew.kwargs["memory"] is False

    with pytest.raises(SpecError):
        build_agent(get_role("tester"), goal="g", backstory="b",
                    model_name="ollama/x", llm_factory=llm_sentinel)


def test_backend_run_agent_returns_typed_result_and_closes(recording_crewai):
    backend = CrewAIBackend(project_id=7, llm_factory=llm_sentinel)
    tools = [SimpleNamespace(name="read_file"), SimpleNamespace(name="write_file")]
    result = backend.run_agent(
        get_role("developer"), "PROMPT",
        goal="goal", backstory="backstory", model_name="ollama/dev",
        expected_output="expected", tools=tools,
    )
    assert result.text == "APPROVE\nfake backend output"
    assert result.model == "ollama/dev"
    assert result.provider == "ollama"
    assert result.tools_used == ()
    assert result.available_tools == ("read_file", "write_file")
    assert result.duration_s is not None
    crew = RecordingCrew.instances[-1]
    assert crew.kicked is True
    agent = RecordingAgent.instances[-1]
    assert agent.kwargs["role"] == "Implementation Developer"
    assert crew.kwargs["agents"] == [agent]
    assert len(crew.kwargs["tasks"]) == 1
    assert crew.kwargs["tasks"][0].kwargs["description"] == "PROMPT"
    backend.close()
    with pytest.raises(CrewRuntimeError):
        backend.run_agent(get_role("developer"), "p", goal="g", backstory="b",
                          model_name="ollama/dev", expected_output="e")


def test_backend_exception_mapping(recording_crewai):
    backend = CrewAIBackend(llm_factory=llm_sentinel)
    RecordingCrew.raises = PermissionDenied("cloud denied", scope="cloud")
    with pytest.raises(CrewRuntimeRefusedError) as refused:
        backend.run_agent(get_role("developer"), "p", goal="g", backstory="b",
                          model_name="ollama/dev", expected_output="e")
    assert "cloud denied" in str(refused.value)
    assert refused.value.__cause__ is not None

    RecordingCrew.raises = TimeoutError("model timed out")
    with pytest.raises(CrewRuntimeUnavailableError):
        backend.run_agent(get_role("developer"), "p", goal="g", backstory="b",
                          model_name="ollama/dev", expected_output="e")

    RecordingCrew.raises = ValueError("bad output")
    with pytest.raises(CrewRuntimeError) as generic:
        backend.run_agent(get_role("developer"), "p", goal="g", backstory="b",
                          model_name="ollama/dev", expected_output="e")
    assert not isinstance(generic.value, CrewRuntimeRefusedError)


def test_default_llm_factory_goes_through_make_llm(monkeypatch, recording_crewai):
    recorded: dict = {}

    def fake_make_llm(model_name, base_url="x", temperature=0.1, *, project_id=None):
        recorded.update({"model_name": model_name, "base_url": base_url,
                         "temperature": temperature, "project_id": project_id})
        return "permission-checked-llm"

    monkeypatch.setattr(orchestrator_module, "_make_llm", fake_make_llm)
    backend = CrewAIBackend(project_id=9)
    agent = build_agent(
        get_role("developer"), goal="g", backstory="b", model_name="ollama/dev",
        project_id=9, llm_factory=None,
    )
    assert recorded["model_name"] == "ollama/dev"
    assert recorded["project_id"] == 9
    assert agent.kwargs["llm"] == "permission-checked-llm"


def test_memory_and_flow_are_not_enabled_in_c4a(recording_crewai):
    developer = get_role("developer")
    task_spec = TaskSpec(task_id="t", description_template="d",
                         expected_output="e", agent_role_id="developer")
    local_memory = MemoryPolicy(enabled=True, storage_dir="x", embedder="local")
    crew_spec = CrewSpec(crew_id="c", agents=(developer,), tasks=(task_spec,),
                         memory_policy="local", memory=local_memory)
    with pytest.raises(CrewRuntimeError) as exc:
        build_crew(crew_spec, [], [])
    assert "memory" in str(exc.value).lower()
    assert not hasattr(CrewAIBackend, "run_flow")
    assert "@flow" not in Path(backend_module.__file__).read_text(encoding="utf-8").lower()


# --------------------------------------------------------------------------- #
# Fake runtime
# --------------------------------------------------------------------------- #

def test_fake_runtime_scripts_parity_and_call_log():
    spec = get_role("developer")
    reviewer = get_role("reviewer")
    hooks: list[str] = []
    runtime = FakeCrewRuntime(
        {
            "developer": ["out-a", "out-b"],
            "Code Reviewer & Quality Gatekeeper": ["APPROVE"],
            "*": ["default"],
        },
        hooks={"developer": lambda spec, prompt: hooks.append("developer")},
    )
    tools = [SimpleNamespace(name="read_file")]
    first = runtime.run_agent(spec, "prompt-1", goal="goal", backstory="backstory",
                              model_name="ollama/dev", expected_output="expected",
                              tools=tools, project_id=4)
    second = runtime.run_agent(spec, "prompt-2", goal="goal", backstory="backstory",
                               model_name="ollama/dev", expected_output="expected")
    review = runtime.run_agent(reviewer, "review", goal="g", backstory="b",
                               model_name="ollama/rev", expected_output="e")
    wildcard = runtime.run_agent(get_role("architect"), "arch", goal="g",
                                 backstory="b", model_name="ollama/arch",
                                 expected_output="e")
    assert (first.text, second.text, review.text, wildcard.text) == (
        "out-a", "out-b", "APPROVE", "default")
    assert runtime.roles == ["developer", "developer", "reviewer", "architect"]
    assert runtime.calls[0]["goal"] == "goal"
    assert runtime.calls[0]["backstory"] == "backstory"
    assert runtime.calls[0]["tools"] is tools
    assert runtime.calls[0]["project_id"] == 4
    assert hooks == ["developer", "developer"]
    assert runtime.prompts_for("developer") == ["prompt-1", "prompt-2"]
    assert runtime.prompts_for("reviewer") == ["review"]
    with pytest.raises(AssertionError):
        runtime.run_agent(spec, "p", goal="g", backstory="b",
                          model_name="m", expected_output="e")
    runtime.close()
    assert runtime.closed is True
    with pytest.raises(CrewRuntimeError):
        runtime.run_agent(spec, "p", goal="g", backstory="b",
                          model_name="m", expected_output="e")


def test_fake_runtime_is_a_crew_runtime_and_has_no_network(monkeypatch):
    import socket

    def _no_network(*args, **kwargs):
        raise AssertionError("fake runtime must not touch the network")

    monkeypatch.setattr(socket, "socket", _no_network)
    runtime = FakeCrewRuntime({"developer": ["ok"]})
    assert isinstance(runtime, CrewRuntime)
    result = runtime.run_agent(get_role("developer"), "p", goal="g",
                               backstory="b", model_name="m", expected_output="e")
    assert isinstance(result, AgentResult)
    assert result.text == "ok"
    assert result.provider == "fake"


# --------------------------------------------------------------------------- #
# Orchestrator seam
# --------------------------------------------------------------------------- #

def test_orchestrator_call_model_uses_injected_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = FakeCrewRuntime({"Implementation Developer": ["APPROVE\nok"]})
        orch = MultiAgentOrchestrator(Path(tmp), crew_runtime=runtime)
        tools = [SimpleNamespace(name="read_file")]
        output = orch._call_model(
            "Implementation Developer", "ollama/test-model", "PROMPT BODY",
            goal="Implement the change", backstory="Senior engineer",
            expected_output="APPROVE or REJECT", tools=tools,
        )
    assert output == "APPROVE\nok"
    assert len(runtime.calls) == 1
    call = runtime.calls[0]
    assert call["role_id"] == "developer"
    assert call["prompt"] == "PROMPT BODY"
    assert call["goal"] == "Implement the change"
    # Every model seam receives the canonical NL Code contract (core.instructions);
    # the call-specific backstory is appended as its final block, not replaced.
    assert call["backstory"].startswith("You are NL Code")
    assert "Current role: Implementation Developer" in call["backstory"]
    assert call["backstory"].rstrip().endswith("Senior engineer")
    assert call["model_name"] == "ollama/test-model"
    assert call["expected_output"] == "APPROVE or REJECT"
    assert call["tools"] is tools
    assert orch.crew_runtime is runtime


def test_orchestrator_rejects_unknown_role_before_runtime_call():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = FakeCrewRuntime({})
        orch = MultiAgentOrchestrator(Path(tmp), crew_runtime=runtime)
        with pytest.raises(UnknownRoleError):
            orch._call_model("No Such Role", "ollama/x", "p", goal="g",
                             backstory="b", expected_output="e")
    assert runtime.calls == []


def test_orchestrator_default_runtime_is_crewai_backend():
    with tempfile.TemporaryDirectory() as tmp:
        orch = MultiAgentOrchestrator(Path(tmp), project_id=12)
        assert isinstance(orch.crew_runtime, CrewAIBackend)
        assert orch.crew_runtime.project_id == 12
        orch.crew_runtime.close()


def test_orchestrator_call_model_is_still_monkeypatchable():
    with tempfile.TemporaryDirectory() as tmp:
        orch = MultiAgentOrchestrator(Path(tmp), crew_runtime=FakeCrewRuntime({}))
        calls = {}

        def fake(role, model_name, prompt, *, goal, backstory, expected_output,
                 tools=None):
            calls.update({"role": role, "prompt": prompt, "tools": tools})
            return "scripted"

        orch._call_model = fake
        assert orch._call_model("developer", "m", "p", goal="g", backstory="b",
                                expected_output="e") == "scripted"
    assert calls == {"role": "developer", "prompt": "p", "tools": None}


def test_kickoff_storage_is_contained_without_inference(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(tmp_path / "generated"))
    monkeypatch.delenv("CREWAI_STORAGE_DIR", raising=False)
    CrewAIBackend()
    from crewai.memory.storage.kickoff_task_outputs_storage import KickoffTaskOutputsSQLiteStorage
    storage = KickoffTaskOutputsSQLiteStorage()
    assert Path(storage.db_path).is_relative_to(tmp_path / "generated/state/crewai")
    assert Path(storage.db_path).is_file()


def test_explicit_crewai_storage_override_is_preserved(tmp_path, monkeypatch):
    import os
    target = str(tmp_path / "explicit-state")
    monkeypatch.setenv("CREWAI_STORAGE_DIR", target)
    CrewAIBackend()
    assert os.environ["CREWAI_STORAGE_DIR"] == target

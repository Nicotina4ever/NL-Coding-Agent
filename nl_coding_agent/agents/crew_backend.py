"""CrewAI runtime seam: the single place that constructs Agent/Task/Crew (C4a).

Everything above this seam is deterministic policy code (specs, staged-candidate
gates, supervisor). The default CrewAIBackend preserves the previous single-agent
Crew behavior exactly; tests inject FakeCrewRuntime so no Ollama/CrewAI call is
made. No Flow runtime and no safety flag live here yet (C4b+).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from crewai import Agent, Crew, LLM, Process, Task

from nl_coding_agent.agents.specs import (
    AgentSpec,
    CrewSpec,
    SpecError,
    TaskSpec,
    resolve_role,
)

__all__ = [
    "DEFAULT_BASE_URL", "CrewRuntimeError", "CrewRuntimeRefusedError",
    "CrewRuntimeUnavailableError", "AgentResult", "CrewResult", "FlowResult",
    "CrewRuntime", "CrewAIBackend", "FakeCrewRuntime", "crew_runtime_env",
    "build_agent", "build_task", "build_crew",
]

DEFAULT_BASE_URL = "http://127.0.0.1:11434"


# --------------------------------------------------------------------------- #
# Typed results and exceptions
# --------------------------------------------------------------------------- #

class CrewRuntimeError(RuntimeError):
    """The CrewAI backend failed to execute a stage task."""


class CrewRuntimeRefusedError(CrewRuntimeError):
    """A permission/policy refusal (e.g. cloud/network escalation without a grant)."""


class CrewRuntimeUnavailableError(CrewRuntimeError):
    """The model/provider is currently unavailable (timeout, connection, ...)."""


@dataclass(frozen=True)
class AgentResult:
    text: str
    model: str | None = None
    provider: str | None = None
    usage: Mapping | None = None
    duration_s: float | None = None
    tools_used: tuple[str, ...] = ()
    raw_events: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", str(self.text or ""))
        object.__setattr__(self, "tools_used", tuple(str(item) for item in (self.tools_used or ())))
        object.__setattr__(self, "raw_events", tuple(self.raw_events or ()))
        if self.usage is not None:
            object.__setattr__(self, "usage", MappingProxyType(dict(self.usage)))


@dataclass(frozen=True)
class CrewResult:
    output: str
    task_outputs: tuple[str, ...] = ()
    usage: Mapping | None = None
    duration_s: float | None = None
    raw_events: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", str(self.output or ""))
        object.__setattr__(self, "task_outputs",
                           tuple(str(item) for item in (self.task_outputs or ())))
        object.__setattr__(self, "raw_events", tuple(self.raw_events or ()))
        if self.usage is not None:
            object.__setattr__(self, "usage", MappingProxyType(dict(self.usage)))


@dataclass(frozen=True)
class FlowResult:
    """Reserved for C4b/C4c; no Flow runtime is enabled in C4a."""

    output: str
    flow_id: str | None = None
    state: Mapping | None = None
    pending_feedback: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", str(self.output or ""))
        if self.state is not None:
            object.__setattr__(self, "state", MappingProxyType(dict(self.state)))


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #

@runtime_checkable
class CrewRuntime(Protocol):
    """Runtime seam used by the orchestrator (and, later, the mission stage engine)."""

    def run_agent(self, spec: AgentSpec, prompt: str, *, goal: str, backstory: str,
                  model_name: str, expected_output: str,
                  tools: list | None = None,
                  project_id: int | None = None) -> AgentResult:
        ...

    def run_crew(self, spec: CrewSpec, inputs: Mapping[str, Any], *,
                 bindings: Mapping[str, str] | None = None,
                 project_id: int | None = None) -> CrewResult:
        ...

    def close(self) -> None:
        ...


# --------------------------------------------------------------------------- #
# Environment + object builders
# --------------------------------------------------------------------------- #

def crew_runtime_env() -> dict[str, str]:
    """The single env builder for CrewAI work: UTF-8, no telemetry, no colour."""
    return {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "1",
        "OTEL_SDK_DISABLED": "1",
        "CREWAI_DISABLE_TELEMETRY": "1",
        "CREWAI_DISABLE_TRACKING": "1",
    }


def _tool_names(tools: list | None) -> tuple[str, ...]:
    names = []
    for tool in tools or ():
        names.append(str(getattr(tool, "name", type(tool).__name__)))
    return tuple(names)


def _default_llm_factory(model_name: str, *, base_url: str, temperature: float,
                         project_id: int | None = None) -> LLM:
    # Lazy import avoids an orchestrator <-> backend import cycle; the permission
    # gate remains inside orchestrator._make_llm (single construction point).
    from nl_coding_agent.agents.orchestrator import _make_llm

    return _make_llm(
        model_name, base_url, temperature=temperature, project_id=project_id,
    )


def build_agent(spec: AgentSpec, *, goal: str, backstory: str,
                model_name: str, base_url: str = DEFAULT_BASE_URL,
                temperature: float = 0.1, project_id: int | None = None,
                tools: list | None = None,
                llm_factory=None, verbose: bool = True) -> Agent:
    """Build one CrewAI Agent from a reviewed AgentSpec (production path)."""
    if not isinstance(spec, AgentSpec):
        raise SpecError("build_agent requires an AgentSpec")
    if not spec.requires_llm:
        raise SpecError("Deterministic role " + spec.role_id + " does not use an LLM")
    factory = llm_factory or _default_llm_factory
    llm = factory(
        model_name, base_url=base_url, temperature=temperature, project_id=project_id,
    )
    kwargs: dict[str, Any] = {
        "role": spec.display_role,
        "goal": goal,
        "backstory": backstory,
        "llm": llm,
        "tools": list(tools or []),
        "verbose": bool(verbose),
        "allow_delegation": bool(spec.allow_delegation),
    }
    if spec.max_iter is not None:
        kwargs["max_iter"] = spec.max_iter
    return Agent(**kwargs)


def build_task(spec: TaskSpec, agent: Agent, *, description: str,
               expected_output: str | None = None) -> Task:
    if not isinstance(spec, TaskSpec):
        raise SpecError("build_task requires a TaskSpec")
    return Task(
        description=str(description),
        expected_output=str(expected_output if expected_output is not None
                            else spec.expected_output),
        agent=agent,
    )


_CLOUD_EMBEDDER_TOKENS = ("openai", "cloud", "remote", "azure", "http://", "https://")


def is_cloud_embedder(embedder: str | None) -> bool:
    text = str(embedder or "").strip().lower()
    return any(token in text for token in _CLOUD_EMBEDDER_TOKENS)


def validate_memory_policy(spec: CrewSpec) -> dict:
    """Memory is off by default; if enabled it must be fully local and explicit."""
    if not isinstance(spec, CrewSpec):
        raise SpecError("validate_memory_policy requires a CrewSpec")
    if not spec.memory.enabled and spec.memory_policy != "local":
        return {"enabled": False}
    memory = spec.memory
    if not memory.enabled:
        raise CrewRuntimeError("memory_policy='local' requires an enabled MemoryPolicy")
    if is_cloud_embedder(memory.embedder):
        raise CrewRuntimeError(
            "CrewAI memory must not use a cloud/remote embedder: " + repr(memory.embedder)
        )
    if not str(memory.storage_dir or "").strip():
        raise CrewRuntimeError("CrewAI memory requires an explicit local storage_dir")
    return {"enabled": True, "storage_dir": memory.storage_dir,
            "embedder": memory.embedder}


def _enforce_delegation(spec: CrewSpec) -> None:
    """Write roles never delegate; read-only delegation is allowlisted and depth 1."""
    delegation = spec.delegation
    if delegation.max_depth > 1:
        raise CrewRuntimeError("Delegation max_depth must be <= 1")
    for agent in spec.agents:
        if agent.tools_policy == "stage_write" and (
            agent.allow_delegation or delegation.allow
        ):
            raise CrewRuntimeError(
                "Write-capable agent " + agent.role_id + " must not delegate"
            )
        if agent.allow_delegation and agent.role_id not in delegation.allowlist:
            raise CrewRuntimeError(
                "Delegating agent " + agent.role_id + " is not in the delegation allowlist"
            )


def build_crew(spec: CrewSpec, agents: list, tasks: list) -> Crew:
    if not isinstance(spec, CrewSpec):
        raise SpecError("build_crew requires a CrewSpec")
    memory_policy = validate_memory_policy(spec)
    _enforce_delegation(spec)
    if memory_policy.get("enabled"):
        raise CrewRuntimeError(
            "Local CrewAI memory policy validated (explicit storage_dir/embedder), but the "
            "memory wiring is deferred to C4e; memory remains off in C4d."
        )
    process = Process.sequential if spec.process == "sequential" else Process.hierarchical
    kwargs: dict[str, Any] = {
        "agents": list(agents),
        "tasks": list(tasks),
        "process": process,
        "verbose": bool(spec.verbose),
        "memory": False,
    }
    if spec.max_rpm is not None:
        kwargs["max_rpm"] = int(spec.max_rpm)
    return Crew(**kwargs)


# --------------------------------------------------------------------------- #
# Production backend
# --------------------------------------------------------------------------- #

class CrewAIBackend:
    """Production CrewRuntime: one single-agent sequential Crew per stage step."""

    provider = "ollama"

    def __init__(self, *, base_url: str = DEFAULT_BASE_URL, temperature: float = 0.1,
                 project_id: int | None = None, llm_factory=None,
                 verbose: bool = True) -> None:
        self.base_url = str(base_url or DEFAULT_BASE_URL)
        self.temperature = float(temperature)
        self.project_id = int(project_id) if project_id is not None else None
        self.llm_factory = llm_factory
        self.verbose = bool(verbose)
        self.closed = False

    def run_agent(self, spec: AgentSpec, prompt: str, *, goal: str, backstory: str,
                  model_name: str, expected_output: str,
                  tools: list | None = None,
                  project_id: int | None = None) -> AgentResult:
        if self.closed:
            raise CrewRuntimeError("CrewAIBackend is closed")
        effective_project = project_id if project_id is not None else self.project_id
        started = time.monotonic()
        try:
            agent = build_agent(
                spec, goal=goal, backstory=backstory, model_name=model_name,
                base_url=self.base_url, temperature=self.temperature,
                project_id=effective_project, tools=tools,
                llm_factory=self.llm_factory, verbose=self.verbose,
            )
            task_spec = TaskSpec(
                task_id="stage-" + spec.role_id,
                description_template=str(prompt or ""),
                expected_output=str(expected_output or ""),
                agent_role_id=spec.role_id,
            )
            task = build_task(task_spec, agent, description=str(prompt or ""),
                              expected_output=str(expected_output or ""))
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=self.verbose,
            )
            output = crew.kickoff()
        except Exception as exc:  # classified below, message always preserved
            raise _map_backend_exception(exc) from exc
        return AgentResult(
            text=str(output),
            model=str(model_name),
            provider=self.provider,
            duration_s=round(time.monotonic() - started, 3),
            tools_used=_tool_names(tools),
        )

    def run_crew(self, spec: CrewSpec, inputs: Mapping[str, Any], *,
                 bindings: Mapping[str, str] | None = None,
                 project_id: int | None = None) -> CrewResult:
        if self.closed:
            raise CrewRuntimeError("CrewAIBackend is closed")
        if not isinstance(spec, CrewSpec):
            raise SpecError("run_crew requires a CrewSpec")
        bindings = dict(bindings or {})
        effective_project = project_id if project_id is not None else self.project_id
        started = time.monotonic()
        try:
            agents_by_role: dict[str, Agent] = {}
            for agent_spec in spec.agents:
                model_name = str(
                    bindings.get(agent_spec.role_id)
                    or bindings.get(str(agent_spec.model_role or ""))
                    or ""
                )
                if agent_spec.requires_llm and not model_name:
                    raise CrewRuntimeError(
                        "No model binding for crew role " + agent_spec.role_id
                    )
                if not agent_spec.requires_llm:
                    continue
                agents_by_role[agent_spec.role_id] = build_agent(
                    agent_spec,
                    goal=agent_spec.build_goal(str(inputs.get("goal") or "")),
                    backstory=agent_spec.backstory,
                    model_name=model_name,
                    base_url=self.base_url,
                    temperature=(agent_spec.temperature
                                 if agent_spec.temperature is not None else self.temperature),
                    project_id=effective_project,
                    llm_factory=self.llm_factory,
                    verbose=self.verbose,
                )
            tasks = []
            for task_spec in spec.tasks:
                agent = agents_by_role.get(task_spec.agent_role_id)
                if agent is None:
                    raise CrewRuntimeError(
                        "CrewSpec task " + task_spec.task_id
                        + " has no built LLM agent for role " + task_spec.agent_role_id
                    )
                tasks.append(build_task(
                    task_spec, agent,
                    description=task_spec.render_description(**dict(inputs)),
                ))
            crew = build_crew(spec, list(agents_by_role.values()), tasks)
            output = crew.kickoff()
        except Exception as exc:
            raise _map_backend_exception(exc) from exc
        task_outputs: list[str] = []
        for item in getattr(output, "tasks_output", None) or ():
            raw = getattr(item, "raw", None)
            if raw is not None:
                task_outputs.append(str(raw))
        return CrewResult(
            output=str(output),
            task_outputs=tuple(task_outputs),
            duration_s=round(time.monotonic() - started, 3),
        )

    def close(self) -> None:
        self.closed = True


def _map_backend_exception(exc: Exception) -> CrewRuntimeError:
    from nl_coding_agent.core.permissions import PermissionDenied

    if isinstance(exc, PermissionDenied):
        return CrewRuntimeRefusedError(str(exc))
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return CrewRuntimeUnavailableError(str(exc))
    return CrewRuntimeError(str(exc))


# --------------------------------------------------------------------------- #
# Test fake
# --------------------------------------------------------------------------- #

class FakeCrewRuntime:
    """Scripted CrewRuntime: no LLM, no network, full call log and hooks."""

    def __init__(self, scripts: Mapping[str, Any] | None = None, *,
                 crew_scripts: Mapping[str, Any] | None = None,
                 hooks: Mapping[str, Any] | None = None) -> None:
        self.calls: list[dict] = []
        self.crew_calls: list[dict] = []
        self.closed = False
        self._scripts: dict[str, list[str]] = {}
        for key, value in dict(scripts or {}).items():
            self._scripts[str(key)] = self._as_list(value)
        self._crew_scripts: dict[str, list[str]] = {}
        for key, value in dict(crew_scripts or {}).items():
            self._crew_scripts[str(key)] = self._as_list(value)
        self._hooks = dict(hooks or {})

    @staticmethod
    def _as_list(value) -> list[str]:
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]

    def _next(self, scripts: dict[str, list[str]], keys: list[str], label: str) -> str:
        for key in keys:
            outputs = scripts.get(key)
            if outputs:
                return outputs.pop(0)
        raise AssertionError(
            "Unexpected " + label + " call; available scripts: " + repr(sorted(scripts))
        )

    def run_agent(self, spec: AgentSpec, prompt: str, *, goal: str, backstory: str,
                  model_name: str, expected_output: str,
                  tools: list | None = None,
                  project_id: int | None = None) -> AgentResult:
        if self.closed:
            raise CrewRuntimeError("FakeCrewRuntime is closed")
        self.calls.append({
            "spec": spec,
            "role_id": spec.role_id,
            "display_role": spec.display_role,
            "prompt": prompt,
            "goal": goal,
            "backstory": backstory,
            "model_name": model_name,
            "expected_output": expected_output,
            "tools": tools,
            "project_id": project_id,
        })
        hook = (self._hooks.get(spec.role_id)
                or self._hooks.get(spec.display_role)
                or self._hooks.get("*"))
        if hook is not None:
            hook(spec, prompt)
        text = self._next(
            self._scripts, [spec.role_id, spec.display_role, "*"], "agent")
        return AgentResult(
            text=text, model=str(model_name), provider="fake",
            tools_used=_tool_names(tools),
        )

    def run_crew(self, spec: CrewSpec, inputs: Mapping[str, Any], *,
                 bindings: Mapping[str, str] | None = None,
                 project_id: int | None = None) -> CrewResult:
        if self.closed:
            raise CrewRuntimeError("FakeCrewRuntime is closed")
        self.crew_calls.append({
            "spec": spec, "inputs": dict(inputs),
            "bindings": dict(bindings or {}), "project_id": project_id,
        })
        text = self._next(self._crew_scripts, [spec.crew_id, "*"], "crew")
        return CrewResult(output=text)

    def close(self) -> None:
        self.closed = True

    @property
    def roles(self) -> list[str]:
        return [call["role_id"] for call in self.calls]

    def prompts_for(self, role: str) -> list[str]:
        try:
            key = resolve_role(str(role)).role_id
        except SpecError:
            key = str(role)
        return [call["prompt"] for call in self.calls if call["role_id"] == key]

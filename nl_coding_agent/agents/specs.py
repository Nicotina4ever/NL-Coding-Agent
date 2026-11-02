"""Declarative agent/task/crew specifications and the product role catalog (C4a).

The catalog is code-reviewed policy, not model-generated: it defines which roles
exist, whether they may use an LLM, which tool policy applies, and the hard
delegation/memory defaults. CrewAI objects are built from these specs by
nl_coding_agent.agents.crew_backend (the CrewRuntime seam), never ad hoc inside
stage methods.

C4a is additive only: the orchestrator keeps its current prompts and gates; the
catalog currently supplies role identity/policy for the runtime adapter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "SpecError", "UnknownRoleError", "TOOLS_POLICIES", "CREW_PROCESSES",
    "MEMORY_POLICIES", "AgentSpec", "TaskSpec", "MemoryPolicy",
    "DelegationPolicy", "CrewSpec", "ROLE_CATALOG", "get_role", "resolve_role",
    "all_roles", "write_stage_roles",
]

_ROLE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TOOLS_POLICIES: tuple[str, ...] = ("stage_write", "read_only", "none")
CREW_PROCESSES: tuple[str, ...] = ("sequential", "hierarchical")
MEMORY_POLICIES: tuple[str, ...] = ("off", "local")


class SpecError(ValueError):
    """A declarative spec is invalid."""


class UnknownRoleError(SpecError):
    """A role id / display role is not in the reviewed catalog."""


def _require_text(value, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SpecError(field_name + " is required")
    return text


@dataclass(frozen=True)
class MemoryPolicy:
    """CrewAI memory is opt-in, local-only and explicit-path only."""

    enabled: bool = False
    storage_dir: str | None = None
    embedder: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise SpecError("MemoryPolicy.enabled must be a bool")
        if self.enabled and not str(self.storage_dir or "").strip():
            raise SpecError(
                "MemoryPolicy.storage_dir is required when memory is enabled"
            )
        if self.enabled and not str(self.embedder or "").strip():
            raise SpecError(
                "MemoryPolicy.embedder is required when memory is enabled"
            )


@dataclass(frozen=True)
class DelegationPolicy:
    """Write-capable agents never delegate; read-only roles may, bounded."""

    allow: bool = False
    allowlist: tuple[str, ...] = ()
    max_depth: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.allow, bool):
            raise SpecError("DelegationPolicy.allow must be a bool")
        allowlist = tuple(str(item) for item in (self.allowlist or ()))
        object.__setattr__(self, "allowlist", allowlist)
        if not self.allow:
            return
        if int(self.max_depth) < 1:
            raise SpecError("DelegationPolicy.max_depth must be >= 1 when delegation is allowed")
        if not allowlist:
            raise SpecError("DelegationPolicy.allowlist must not be empty when delegation is allowed")
        for role in allowlist:
            if not _ROLE_ID_RE.match(role):
                raise SpecError("Invalid delegation allowlist role id: " + repr(role))


@dataclass(frozen=True)
class AgentSpec:
    role_id: str
    display_role: str
    goal_template: str
    backstory: str
    model_role: str | None = None
    tools_policy: str = "none"
    allow_delegation: bool = False
    max_iter: int | None = None
    temperature: float | None = None
    capability_requirements: tuple[str, ...] = ()
    requires_llm: bool = True

    def __post_init__(self) -> None:
        role_id = _require_text(self.role_id, "AgentSpec.role_id")
        if not _ROLE_ID_RE.match(role_id):
            raise SpecError("Invalid role_id: " + repr(role_id))
        object.__setattr__(self, "role_id", role_id)
        object.__setattr__(self, "display_role",
                           _require_text(self.display_role, "AgentSpec.display_role"))
        object.__setattr__(self, "goal_template",
                           _require_text(self.goal_template, "AgentSpec.goal_template"))
        object.__setattr__(self, "backstory",
                           _require_text(self.backstory, "AgentSpec.backstory"))
        if self.tools_policy not in TOOLS_POLICIES:
            raise SpecError("Invalid tools_policy: " + repr(self.tools_policy))
        if not isinstance(self.requires_llm, bool):
            raise SpecError("AgentSpec.requires_llm must be a bool")
        if not isinstance(self.allow_delegation, bool):
            raise SpecError("AgentSpec.allow_delegation must be a bool")
        if self.requires_llm:
            if not str(self.model_role or "").strip():
                raise SpecError("AgentSpec.model_role is required when requires_llm=True")
        else:
            if self.model_role is not None:
                raise SpecError("AgentSpec.model_role must be None when requires_llm=False")
            if self.tools_policy == "stage_write":
                raise SpecError("A deterministic (no-LLM) role cannot write stage files")
        if self.tools_policy == "stage_write":
            if self.allow_delegation:
                raise SpecError("Write-capable agents must not allow delegation")
            if not self.requires_llm:
                raise SpecError("Write-capable agents require an LLM")
        if self.max_iter is not None:
            if isinstance(self.max_iter, bool) or int(self.max_iter) < 1:
                raise SpecError("AgentSpec.max_iter must be a positive integer or None")
            object.__setattr__(self, "max_iter", int(self.max_iter))
        if self.temperature is not None:
            value = float(self.temperature)
            if not 0.0 <= value <= 2.0:
                raise SpecError("AgentSpec.temperature must be within 0..2")
            object.__setattr__(self, "temperature", value)
        capabilities = tuple(str(item).strip() for item in (self.capability_requirements or ()))
        if any(not item for item in capabilities):
            raise SpecError("AgentSpec.capability_requirements entries must be non-empty")
        object.__setattr__(self, "capability_requirements", capabilities)

    def build_goal(self, goal: str) -> str:
        try:
            return str(self.goal_template).format(goal=str(goal or ""))
        except (KeyError, IndexError):
            return str(self.goal_template)


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    description_template: str
    expected_output: str
    agent_role_id: str
    context: tuple[str, ...] = ()
    output_json: Mapping | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("task_id", self.task_id),
            ("description_template", self.description_template),
            ("expected_output", self.expected_output),
            ("agent_role_id", self.agent_role_id),
        ):
            object.__setattr__(self, name, _require_text(value, "TaskSpec." + name))
        context = tuple(str(item) for item in (self.context or ()))
        if any(not item for item in context):
            raise SpecError("TaskSpec.context entries must be non-empty strings")
        object.__setattr__(self, "context", context)
        if self.output_json is not None:
            if not isinstance(self.output_json, Mapping):
                raise SpecError("TaskSpec.output_json must be a mapping or None")
            object.__setattr__(self, "output_json", MappingProxyType(dict(self.output_json)))

    def render_description(self, **values) -> str:
        try:
            return str(self.description_template).format(**values)
        except (KeyError, IndexError):
            return str(self.description_template)


@dataclass(frozen=True)
class CrewSpec:
    crew_id: str
    process: str = "sequential"
    agents: tuple[AgentSpec, ...] = ()
    tasks: tuple[TaskSpec, ...] = ()
    memory_policy: str = "off"
    memory: MemoryPolicy = field(default_factory=MemoryPolicy)
    delegation: DelegationPolicy = field(default_factory=DelegationPolicy)
    max_rpm: int | None = None
    verbose: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "crew_id", _require_text(self.crew_id, "CrewSpec.crew_id"))
        if self.process not in CREW_PROCESSES:
            raise SpecError("Invalid crew process: " + repr(self.process))
        if self.memory_policy not in MEMORY_POLICIES:
            raise SpecError("Invalid memory_policy: " + repr(self.memory_policy))
        agents = tuple(self.agents or ())
        tasks = tuple(self.tasks or ())
        for agent in agents:
            if not isinstance(agent, AgentSpec):
                raise SpecError("CrewSpec.agents entries must be AgentSpec instances")
        for task in tasks:
            if not isinstance(task, TaskSpec):
                raise SpecError("CrewSpec.tasks entries must be TaskSpec instances")
        agent_ids = [agent.role_id for agent in agents]
        if len(set(agent_ids)) != len(agent_ids):
            raise SpecError("CrewSpec.agents must have unique role ids")
        task_ids = [task.task_id for task in tasks]
        if len(set(task_ids)) != len(task_ids):
            raise SpecError("CrewSpec.tasks must have unique task ids")
        for task in tasks:
            if task.agent_role_id not in agent_ids:
                raise SpecError(
                    "CrewSpec task " + task.task_id + " references unknown agent role "
                    + task.agent_role_id
                )
        if self.process == "hierarchical":
            if any(agent.tools_policy == "stage_write" for agent in agents):
                raise SpecError(
                    "hierarchical crews are read-only: no stage_write agent is allowed"
                )
        if self.memory_policy == "local" and not self.memory.enabled:
            raise SpecError("memory_policy='local' requires an enabled MemoryPolicy")
        if self.max_rpm is not None:
            if isinstance(self.max_rpm, bool) or int(self.max_rpm) < 1:
                raise SpecError("CrewSpec.max_rpm must be a positive integer or None")
            object.__setattr__(self, "max_rpm", int(self.max_rpm))
        object.__setattr__(self, "agents", agents)
        object.__setattr__(self, "tasks", tasks)


# --------------------------------------------------------------------------- #
# Reviewed product role catalog
# --------------------------------------------------------------------------- #

_DEVELOPER = AgentSpec(
    role_id="developer",
    display_role="Implementation Developer",
    goal_template="Implement the requested code change in the staged candidate: {goal}",
    backstory=(
        "You are an expert autonomous software engineer. You inspect existing code using "
        "read_file or list_dir, and you write the necessary files or patches using "
        "write_file or patch_file. You can also use write-block output. You must produce "
        "real file changes in the staged workspace, not only a plan."
    ),
    model_role="developer",
    tools_policy="stage_write",
    allow_delegation=False,
    capability_requirements=("tool_calling",),
)

_DEBUGGER = AgentSpec(
    role_id="debugger",
    display_role="Software Debugger",
    goal_template="Analyze the verification failure and fix the staged candidate.",
    backstory=(
        "You are an expert troubleshooter. You read error logs, locate broken code, and "
        "apply precise fixes using write_file or patch_file in the staged workspace."
    ),
    model_role="debugger",
    tools_policy="stage_write",
    allow_delegation=False,
    capability_requirements=("tool_calling",),
)

_REVIEWER = AgentSpec(
    role_id="reviewer",
    display_role="Code Reviewer & Quality Gatekeeper",
    goal_template=(
        "Verify code quality, adherence to scope, and absence of regressions in the "
        "candidate diff."
    ),
    backstory=(
        "You are a strict, diligent senior engineer. You review only the candidate diff. "
        "You give an APPROVE or REJECT verdict on the first line."
    ),
    model_role="reviewer",
    tools_policy="none",
    allow_delegation=False,
)

_TESTER = AgentSpec(
    role_id="tester",
    display_role="Deterministic Tester",
    goal_template="Run the independent candidate and oracle verification suites.",
    backstory=(
        "The tester is deterministic verification code, not an LLM: it runs the real "
        "candidate and oracle pytest suites in disposable copies."
    ),
    model_role=None,
    tools_policy="none",
    allow_delegation=False,
    requires_llm=False,
)

_ARCHITECT = AgentSpec(
    role_id="architect",
    display_role="Software Architect",
    goal_template="Analyze the project architecture for: {goal}",
    backstory=(
        "You are a read-only architecture analyst. You may inspect files and summarise "
        "structure; you never modify the project."
    ),
    model_role="architect",
    tools_policy="read_only",
    allow_delegation=False,
)

_AUDITOR = AgentSpec(
    role_id="auditor",
    display_role="Repository Auditor",
    goal_template="Audit the repository for: {goal}",
    backstory=(
        "You are a read-only repository auditor. You report findings with evidence and "
        "never modify the project."
    ),
    model_role="auditor",
    tools_policy="read_only",
    allow_delegation=False,
)

_ADVISOR = AgentSpec(
    role_id="advisor",
    display_role="Project Advisor",
    goal_template="Advise the mission on: {goal}",
    backstory=(
        "You are an isolated, read-only project advisor. You analyse the mission with "
        "your own context and return a structured handoff: summary, facts, decisions, "
        "risks and next steps. You never modify files or grant permissions."
    ),
    model_role="advisor",
    tools_policy="read_only",
    allow_delegation=False,
    capability_requirements=("tool_calling",),
)

_PLANNER = AgentSpec(
    role_id="planner",
    display_role="Mission Planner",
    goal_template="Plan the next small verifiable mission for: {goal}",
    backstory=(
        "You are a read-only planner. You propose small, verifiable next steps from the "
        "indexed backlog without executing changes."
    ),
    model_role="planner",
    tools_policy="read_only",
    allow_delegation=False,
)

ROLE_CATALOG: Mapping[str, AgentSpec] = MappingProxyType({
    "developer": _DEVELOPER,
    "debugger": _DEBUGGER,
    "reviewer": _REVIEWER,
    "tester": _TESTER,
    "architect": _ARCHITECT,
    "auditor": _AUDITOR,
    "advisor": _ADVISOR,
    "planner": _PLANNER,
})


def get_role(role_id: str) -> AgentSpec:
    text = str(role_id or "").strip()
    try:
        return ROLE_CATALOG[text]
    except KeyError as exc:
        raise UnknownRoleError("Unknown agent role id: " + repr(role_id)) from exc


def resolve_role(role: str) -> AgentSpec:
    """Resolve a role id or an exact display role (the orchestrator passes display roles)."""
    text = str(role or "").strip()
    if text in ROLE_CATALOG:
        return ROLE_CATALOG[text]
    for spec in ROLE_CATALOG.values():
        if spec.display_role == text:
            return spec
    raise UnknownRoleError("Unknown agent role: " + repr(role))


def all_roles() -> tuple[AgentSpec, ...]:
    return tuple(ROLE_CATALOG.values())


def write_stage_roles() -> tuple[AgentSpec, ...]:
    return tuple(spec for spec in ROLE_CATALOG.values()
                 if spec.tools_policy == "stage_write")

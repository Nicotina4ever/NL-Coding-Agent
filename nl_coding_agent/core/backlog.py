"""Indexed-blueprint backlog loader and deterministic mission planner (C3b).

Stage 3 replaces the fixed Markdown roadmap with the authored, machine-readable
INDEX.json backlog:

* load_index() / validate_index() are fail-closed: a missing, corrupt, wrong-schema
  or structurally invalid index raises BacklogError instead of falling back to any
  legacy roadmap file;
* the authored program order (stages + dependencies) gates which requirements are
  eligible;
* selection is deterministic and non-LLM: effective status (authored + supervisor
  mirror), dependency closure, priority, stable id ordering, attempts and in-flight
  exclusion;
* compose_mission_goal() builds the compact mission contract for the orchestrator,
  and sync_backlog_mirror() optionally copies the index into the SQLite mirror
  owned by nl_coding_agent.persistence.supervisor_store.

There is no dependency on any fixed Markdown mission file and no fallback to one.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "INDEX_RELATIVE_PATH", "SUPPORTED_SCHEMA_VERSIONS", "STAGE_STATUSES",
    "REQUIREMENT_STATUSES", "PRIORITIES", "PRIORITY_RANK",
    "BacklogError", "BacklogValidationError", "ProgramStage", "BacklogRequirement",
    "BacklogIndex", "PlannerConfig",
    "resolve_index_path", "load_project_index", "load_index", "validate_index",
    "requirement_content_hash", "program_stages", "iter_requirements",
    "current_program_stage", "effective_status", "select_next_requirement",
    "build_mission_payload", "idempotency_key", "compose_mission_goal",
    "sync_backlog_mirror", "mirror_source_fingerprint",
]

INDEX_RELATIVE_PATH = Path("docs") / "product-blueprint" / "INDEX.json"
SUPPORTED_SCHEMA_VERSIONS = (1,)

STAGE_STATUSES: tuple[str, ...] = ("completed", "in_progress", "pending", "blocked")
REQUIREMENT_STATUSES: tuple[str, ...] = ("verified", "partial", "planned", "blocked")
PRIORITIES: tuple[str, ...] = ("P0", "P1", "P2", "P3")
PRIORITY_RANK: dict[str, int] = {priority: rank for rank, priority in enumerate(PRIORITIES)}

#: Supervisor-owned mirror statuses that make an item ineligible (see plan 10.4).
_MIRROR_BLOCKED = ("VERIFIED", "BLOCKED", "SKIPPED", "IN_FLIGHT")


class BacklogError(RuntimeError):
    """Base class for fail-closed backlog failures."""


class BacklogValidationError(BacklogError):
    """The index content is not a valid, supported blueprint index."""


@dataclass(frozen=True)
class ProgramStage:
    stage: int
    name: str
    status: str
    depends_on_stages: tuple[int, ...]
    requirement_ids: tuple[str, ...]


@dataclass(frozen=True)
class BacklogRequirement:
    requirement_id: str
    title: str
    area: str
    priority: str
    status: str
    dependencies: tuple[str, ...]
    acceptance: tuple[str, ...]
    source_refs: tuple[str, ...]
    program_stage: int | None
    program_stage_name: str
    content_hash: str
    authored_index: int
    raw: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class BacklogIndex:
    schema_version: int
    requirements: tuple[BacklogRequirement, ...]
    stages: tuple[ProgramStage, ...]
    source_fingerprint: str
    source_path: str
    warnings: tuple[str, ...] = ()

    def by_id(self) -> dict[str, BacklogRequirement]:
        return {requirement.requirement_id: requirement for requirement in self.requirements}


@dataclass(frozen=True)
class PlannerConfig:
    """Planner inputs; the future supervisor config may also be a mapping/object."""

    program_stage_override: int | None = None
    max_attempts_per_requirement: int = 2
    git_head: str = ""


# --------------------------------------------------------------------------- #
# Loading and validation
# --------------------------------------------------------------------------- #

def resolve_index_path(project_root: str | Path, override: str | Path | None = None) -> Path:
    """Resolve the index path inside the project root (no escaping the root)."""
    root = Path(project_root).resolve()
    if override is None:
        return root / INDEX_RELATIVE_PATH
    candidate = Path(override)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise BacklogValidationError(
            "Backlog index must live inside the project root: " + str(resolved)
        ) from exc
    return resolved


def load_project_index(project_root: str | Path, *,
                       override: str | Path | None = None) -> BacklogIndex:
    return load_index(resolve_index_path(project_root, override))


def load_index(path: str | Path = INDEX_RELATIVE_PATH) -> BacklogIndex:
    """Load and validate INDEX.json; every failure raises BacklogError."""
    index_path = Path(path)
    try:
        raw_bytes = index_path.read_bytes()
    except FileNotFoundError as exc:
        raise BacklogError("Backlog index not found: " + str(index_path)) from exc
    except OSError as exc:
        raise BacklogError("Cannot read backlog index " + str(index_path) + ": " + str(exc)) from exc
    fingerprint = hashlib.sha256(raw_bytes).hexdigest()
    try:
        decoded = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BacklogValidationError(
            "Backlog index is not valid UTF-8: " + str(index_path)
        ) from exc
    try:
        data = json.loads(decoded)
    except ValueError as exc:
        raise BacklogValidationError(
            "Backlog index is not valid JSON (" + str(index_path) + "): " + str(exc)
        ) from exc
    return validate_index(
        data, source_fingerprint=fingerprint, source_path=str(index_path)
    )


def _schema_version(raw) -> int:
    """Accept the authored integer 1 or the JSON string "1.0"; everything else fails closed."""
    if isinstance(raw, bool) or raw is None:
        raise BacklogValidationError(
            "Unsupported schema_version (expected 1): " + repr(raw)
        )
    if isinstance(raw, str):
        try:
            numeric = float(raw.strip())
        except (TypeError, ValueError) as exc:
            raise BacklogValidationError(
                "Unsupported schema_version (expected 1): " + repr(raw)
            ) from exc
    elif isinstance(raw, (int, float)):
        numeric = float(raw)
    else:
        raise BacklogValidationError(
            "Unsupported schema_version (expected 1): " + repr(raw)
        )
    integer = int(numeric)
    if numeric != float(integer) or integer not in SUPPORTED_SCHEMA_VERSIONS:
        raise BacklogValidationError(
            "Unsupported schema_version (expected one of "
            + repr(SUPPORTED_SCHEMA_VERSIONS) + "): " + repr(raw)
        )
    return integer


def _str_list(raw, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise BacklogValidationError(field_name + " must be a list")
    values = []
    for item in raw:
        if not isinstance(item, (str, int, float)):
            raise BacklogValidationError(field_name + " entries must be strings")
        text = str(item).strip()
        if text:
            values.append(text)
    return tuple(values)


def _int_list(raw, field_name: str) -> tuple[int, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise BacklogValidationError(field_name + " must be a list")
    values = []
    for item in raw:
        if isinstance(item, bool):
            raise BacklogValidationError(field_name + " entries must be integers")
        try:
            values.append(int(item))
        except (TypeError, ValueError) as exc:
            raise BacklogValidationError(field_name + " entries must be integers") from exc
    return tuple(values)


def _optional_int(raw, field_name: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise BacklogValidationError(field_name + " must be an integer or null")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise BacklogValidationError(field_name + " must be an integer or null") from exc


def _parse_stage(raw: dict, position: int) -> ProgramStage:
    if "stage" not in raw:
        raise BacklogValidationError("program_order stage #" + str(position) + " has no stage number")
    stage = _optional_int(raw.get("stage"), "program_order stage")
    if stage is None:
        raise BacklogValidationError("program_order stage number is required")
    name = str(raw.get("name") or "Stage " + str(stage)).strip()
    status = str(raw.get("status") or "").strip().lower()
    if status not in STAGE_STATUSES:
        raise BacklogValidationError(
            "Invalid status for program stage " + str(stage) + ": " + repr(status)
        )
    dependencies = _int_list(raw.get("depends_on_stages"), "depends_on_stages")
    requirement_ids = _str_list(raw.get("requirement_ids"), "requirement_ids")
    return ProgramStage(stage, name, status, dependencies, requirement_ids)


def _parse_requirement(raw: dict, position: int,
                       stage_names: dict[int, str]) -> BacklogRequirement:
    requirement_id = str(raw.get("id") or "").strip()
    if not requirement_id:
        raise BacklogValidationError("Requirement #" + str(position) + " has no id")
    title = str(raw.get("title") or "").strip()
    if not title:
        raise BacklogValidationError(requirement_id + ": title is required")
    status = str(raw.get("status") or "").strip().lower()
    if status not in REQUIREMENT_STATUSES:
        raise BacklogValidationError(
            requirement_id + ": invalid status " + repr(raw.get("status"))
        )
    priority = str(raw.get("priority") or "").strip().upper()
    if priority not in PRIORITIES:
        raise BacklogValidationError(
            requirement_id + ": invalid priority " + repr(raw.get("priority"))
        )
    program_stage = _optional_int(raw.get("program_stage"), requirement_id + ": program_stage")
    stage_name = str(raw.get("program_stage_name") or "").strip()
    if not stage_name and program_stage is not None:
        stage_name = stage_names.get(program_stage, "")
    return BacklogRequirement(
        requirement_id=requirement_id,
        title=title,
        area=str(raw.get("area") or "").strip(),
        priority=priority,
        status=status,
        dependencies=_str_list(raw.get("dependencies"), requirement_id + ": dependencies"),
        acceptance=_str_list(raw.get("acceptance"), requirement_id + ": acceptance"),
        source_refs=_str_list(raw.get("source_refs"), requirement_id + ": source_refs"),
        program_stage=program_stage,
        program_stage_name=stage_name,
        content_hash=requirement_content_hash(raw),
        authored_index=position,
        raw=dict(raw),
    )


def validate_index(data, *, source_fingerprint: str = "",
                   source_path: str = "") -> BacklogIndex:
    """Validate one decoded INDEX.json object and build the typed index."""
    if not isinstance(data, dict):
        raise BacklogValidationError("Backlog index root must be a JSON object")
    schema_version = _schema_version(data.get("schema_version"))
    program_order = data.get("program_order")
    if not isinstance(program_order, dict):
        raise BacklogValidationError("program_order must be an object")
    raw_stages = program_order.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise BacklogValidationError("program_order.stages must be a non-empty list")
    stages: list[ProgramStage] = []
    seen_stages: set[int] = set()
    for position, raw_stage in enumerate(raw_stages):
        if not isinstance(raw_stage, dict):
            raise BacklogValidationError("program_order.stages entries must be objects")
        stage = _parse_stage(raw_stage, position)
        if stage.stage in seen_stages:
            raise BacklogValidationError("Duplicate program stage number: " + str(stage.stage))
        seen_stages.add(stage.stage)
        stages.append(stage)
    warnings: list[str] = []
    for stage in stages:
        for dependency in stage.depends_on_stages:
            if dependency not in seen_stages:
                warnings.append(
                    "Program stage " + str(stage.stage)
                    + " depends on unknown stage " + str(dependency)
                )
    stage_names = {stage.stage: stage.name for stage in stages}

    raw_requirements = data.get("requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise BacklogValidationError("requirements must be a non-empty list")
    requirements: list[BacklogRequirement] = []
    seen_ids: set[str] = set()
    for position, raw_requirement in enumerate(raw_requirements):
        if not isinstance(raw_requirement, dict):
            raise BacklogValidationError("requirements entries must be objects")
        requirement = _parse_requirement(raw_requirement, position, stage_names)
        if requirement.requirement_id in seen_ids:
            raise BacklogValidationError(
                "Duplicate requirement id: " + requirement.requirement_id
            )
        seen_ids.add(requirement.requirement_id)
        requirements.append(requirement)

    # Cross-reference stage membership; unknown or mismatched entries become
    # warnings because selection must stay fail-closed (never guess eligibility).
    stage_membership: dict[str, list[int]] = {}
    for stage in stages:
        for requirement_id in stage.requirement_ids:
            stage_membership.setdefault(requirement_id, []).append(stage.stage)
    normalized: list[BacklogRequirement] = []
    for requirement in requirements:
        memberships = stage_membership.get(requirement.requirement_id, [])
        for unknown in sorted(set(memberships)):
            if unknown not in seen_stages:  # pragma: no cover - defensive
                warnings.append("Unknown stage membership for " + requirement.requirement_id)
        if requirement.program_stage is None and len(memberships) == 1:
            stage_id = memberships[0]
            requirement = BacklogRequirement(
                requirement_id=requirement.requirement_id,
                title=requirement.title,
                area=requirement.area,
                priority=requirement.priority,
                status=requirement.status,
                dependencies=requirement.dependencies,
                acceptance=requirement.acceptance,
                source_refs=requirement.source_refs,
                program_stage=stage_id,
                program_stage_name=stage_names.get(stage_id, ""),
                content_hash=requirement.content_hash,
                authored_index=requirement.authored_index,
                raw=requirement.raw,
            )
        elif requirement.program_stage is not None and memberships:
            if requirement.program_stage not in memberships:
                warnings.append(
                    requirement.requirement_id + " declares program_stage "
                    + str(requirement.program_stage) + " but is listed in stage(s) "
                    + repr(sorted(memberships))
                )
        normalized.append(requirement)
    for requirement_id in sorted(set(stage_membership) - seen_ids):
        warnings.append("Stage lists unknown requirement id: " + requirement_id)
    for requirement in normalized:
        for dependency in requirement.dependencies:
            if dependency not in seen_ids:
                warnings.append(
                    requirement.requirement_id + " depends on unknown requirement id "
                    + dependency
                )
    return BacklogIndex(
        schema_version=schema_version,
        requirements=tuple(normalized),
        stages=tuple(stages),
        source_fingerprint=str(source_fingerprint or ""),
        source_path=str(source_path or ""),
        warnings=tuple(warnings),
    )


def requirement_content_hash(raw: dict) -> str:
    """Deterministic hash of the fields that define a requirement's work contract."""
    canonical = {
        "title": str(raw.get("title") or ""),
        "priority": str(raw.get("priority") or "").strip().upper(),
        "status": str(raw.get("status") or "").strip().lower(),
        "dependencies": list(_str_list(raw.get("dependencies"), "dependencies")),
        "acceptance": list(_str_list(raw.get("acceptance"), "acceptance")),
        "program_stage": _optional_int(raw.get("program_stage"), "program_stage"),
        "source_refs": list(_str_list(raw.get("source_refs"), "source_refs")),
    }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Program-stage gate and selection
# --------------------------------------------------------------------------- #

def program_stages(index: BacklogIndex) -> tuple[ProgramStage, ...]:
    return tuple(sorted(index.stages, key=lambda stage: stage.stage))


def iter_requirements(index: BacklogIndex) -> tuple[BacklogRequirement, ...]:
    return index.requirements


def current_program_stage(index: BacklogIndex, *,
                          override: int | None = None) -> ProgramStage | None:
    """Lowest non-completed stage whose declared dependencies are all completed."""
    stages = program_stages(index)
    if override is not None:
        wanted = int(override)
        for stage in stages:
            if stage.stage == wanted:
                return stage
        raise BacklogValidationError(
            "program_stage_override refers to unknown stage: " + repr(override)
        )
    completed = {stage.stage for stage in stages if stage.status == "completed"}
    for stage in stages:
        if stage.status == "completed":
            continue
        if all(dependency in completed for dependency in stage.depends_on_stages):
            return stage
    return None


def effective_status(requirement: BacklogRequirement, row: dict | None) -> str:
    """Authored status, upgraded to verified when the supervisor mirror says VERIFIED."""
    mirror_status = str((row or {}).get("supervisor_status") or "").strip().upper()
    if requirement.status == "verified" or mirror_status == "VERIFIED":
        return "verified"
    return requirement.status


def _config_value(config, name: str, default):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def _read_git_head(project_root: str | Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(project_root)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return str(completed.stdout or "").strip()


def _mirror_rows() -> dict[str, dict]:
    """Read the optional SQLite backlog mirror; DB failures stay fail-closed."""
    try:
        from nl_coding_agent.persistence import supervisor_store
    except Exception as exc:  # pragma: no cover - import guard
        raise BacklogError("Cannot import the supervisor store for the backlog mirror: " + str(exc)) from exc
    try:
        rows = supervisor_store.list_backlog()
    except Exception as exc:
        raise BacklogError("Cannot read the SQLite backlog mirror: " + str(exc)) from exc
    return {str(row.get("requirement_id")): row for row in rows}


def _idempotency_scope(stage: ProgramStage) -> str:
    payload = json.dumps(
        {"stage": stage.stage, "requirements": sorted(stage.requirement_ids)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def idempotency_key(requirement: BacklogRequirement, stage: ProgramStage, *,
                    git_head: str = "") -> str:
    """Stable dedupe key: requirement contract + program stage + code base head."""
    canonical = "|".join((
        requirement.requirement_id,
        requirement.content_hash,
        str(stage.stage),
        _idempotency_scope(stage),
        str(git_head or ""),
    ))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def select_next_requirement(project_id: int, *, project_root: str | Path,
                            index: BacklogIndex, config=None,
                            in_flight_requirement_ids=None) -> dict | None:
    """Return the next eligible requirement (+ mission payload), or None.

    Eligibility: current program stage; authored status partial/planned and not
    effectively verified; dependencies effectively verified; supervisor mirror not
    VERIFIED/BLOCKED/SKIPPED/IN_FLIGHT; attempts below the configured limit; and
    not currently in flight. Ordering: priority, requirement id, authored order.
    """
    if not isinstance(index, BacklogIndex):
        raise BacklogError("select_next_requirement requires a validated BacklogIndex")
    stage = current_program_stage(
        index, override=_config_value(config, "program_stage_override", None)
    )
    if stage is None:
        return None
    max_attempts = int(_config_value(config, "max_attempts_per_requirement", 2))
    if max_attempts < 1:
        raise BacklogValidationError("max_attempts_per_requirement must be >= 1")
    in_flight = {str(item) for item in (in_flight_requirement_ids or ())}
    mirror = _mirror_rows()
    effective = {
        requirement.requirement_id: effective_status(requirement, mirror.get(requirement.requirement_id))
        for requirement in index.requirements
    }
    candidates: list[BacklogRequirement] = []
    for requirement in index.requirements:
        if requirement.program_stage != stage.stage:
            continue
        row = mirror.get(requirement.requirement_id) or {}
        supervisor_status = str(row.get("supervisor_status") or "").strip().upper()
        if effective[requirement.requirement_id] == "verified":
            continue
        if requirement.status not in ("partial", "planned"):
            continue
        if supervisor_status in _MIRROR_BLOCKED:
            continue
        if requirement.requirement_id in in_flight:
            continue
        if int(row.get("attempts") or 0) >= max_attempts:
            continue
        if any(effective.get(dependency) != "verified"
               for dependency in requirement.dependencies):
            continue
        candidates.append(requirement)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (
        PRIORITY_RANK.get(item.priority, len(PRIORITIES)),
        item.requirement_id,
        item.authored_index,
    ))
    chosen = candidates[0]
    row = mirror.get(chosen.requirement_id) or {}
    git_head = str(_config_value(config, "git_head", "") or "") or _read_git_head(project_root)
    key = idempotency_key(chosen, stage, git_head=git_head)
    mission = build_mission_payload(
        chosen, stage, project_id=int(project_id), max_attempts=max_attempts,
        git_head=git_head,
    )
    return {
        "requirement_id": chosen.requirement_id,
        "title": chosen.title,
        "area": chosen.area,
        "priority": chosen.priority,
        "authored_status": chosen.status,
        "program_stage": stage.stage,
        "program_stage_name": stage.name,
        "content_hash": chosen.content_hash,
        "idempotency_key": key,
        "attempts": int(row.get("attempts") or 0),
        "max_attempts": max_attempts,
        "dependencies": list(chosen.dependencies),
        "acceptance": list(chosen.acceptance),
        "source_refs": list(chosen.source_refs),
        "goal": mission["goal"],
        "mission": mission,
    }


def compose_mission_goal(requirement: BacklogRequirement, stage: ProgramStage) -> str:
    """Compact deterministic mission contract (blueprint on demand, not wholesale)."""
    lines = [
        "[" + requirement.requirement_id + "] " + requirement.title,
        "",
        "Program stage " + str(stage.stage) + ": " + stage.name,
        "Area: " + (requirement.area or "unspecified") + "; Priority: "
        + requirement.priority + "; Authored status: " + requirement.status,
        "",
        "Acceptance gates (must pass independently; reviewer APPROVE alone is not sufficient):",
    ]
    if requirement.acceptance:
        lines.extend("- " + gate for gate in requirement.acceptance)
    else:
        lines.append(
            "- (no explicit acceptance gates recorded; derive verifiable checks from the source references)"
        )
    # Source references are deliberately NOT included in the goal: they are
    # read-only pointers (often specification paths). Including them let the
    # orchestrator derive a documentation-only write scope and models emitted
    # docs-only candidates that passed verification trivially (SH-07 Tier B #1).
    lines.extend([
        "",
        "Reference material: consult the blueprint and specifications on demand; source references",
        "are read-only and must not be created or modified as the deliverable.",
        "",
        "Implementation requirement: the deliverable is working code and tests that satisfy the",
        "acceptance gates. A documentation-only or comment-only change does not satisfy this",
        "requirement.",
        "",
        "Scope: implement the smallest verifiable change that satisfies the gates.",
        "Do not perform destructive actions, installs, network access or cloud calls.",
        "The candidate is staged; nothing is live until promotion.",
    ])
    return "\n".join(lines)


def build_mission_payload(requirement: BacklogRequirement, stage: ProgramStage, *,
                          project_id: int, max_attempts: int = 2,
                          git_head: str = "") -> dict:
    """Deterministic mission creation payload for the supervisor (C3c consumer)."""
    return {
        "project_id": int(project_id),
        "requirement_id": requirement.requirement_id,
        "title": ("[" + requirement.requirement_id + "] " + requirement.title)[:200],
        "goal": compose_mission_goal(requirement, stage),
        "priority": requirement.priority,
        "program_stage": stage.stage,
        "program_stage_name": stage.name,
        "content_hash": requirement.content_hash,
        "idempotency_key": idempotency_key(requirement, stage, git_head=git_head),
        "max_attempts": int(max_attempts),
        "budget": {},
    }


# --------------------------------------------------------------------------- #
# Optional SQLite mirror sync (operational copy for the C3c supervisor)
# --------------------------------------------------------------------------- #

def _mirror_key(project_id: int | None) -> str:
    scope = "global" if project_id is None else str(int(project_id))
    return "supervisor.backlog." + scope


def sync_backlog_mirror(project_id: int | None, index: BacklogIndex, *,
                        config=None) -> dict:
    """Upsert the typed index into supervisor_store.backlog_items and record its fingerprint."""
    if not isinstance(index, BacklogIndex):
        raise BacklogError("sync_backlog_mirror requires a validated BacklogIndex")
    from nl_coding_agent.persistence import database, supervisor_store

    stage_names = {stage.stage: stage.name for stage in index.stages}
    items = [
        {
            "requirement_id": requirement.requirement_id,
            "title": requirement.title,
            "area": requirement.area,
            "priority": requirement.priority,
            "program_stage": requirement.program_stage,
            "program_stage_name": requirement.program_stage_name
            or stage_names.get(requirement.program_stage or -1, ""),
            "status": requirement.status,
            "dependencies": list(requirement.dependencies),
            "acceptance": list(requirement.acceptance),
            "source_refs": list(requirement.source_refs),
            "content_hash": requirement.content_hash,
        }
        for requirement in index.requirements
    ]
    report = supervisor_store.sync_backlog(
        items, source_fingerprint=index.source_fingerprint
    )
    database.set_json_setting(
        _mirror_key(project_id),
        {
            "source_fingerprint": index.source_fingerprint,
            "source_path": index.source_path,
            "requirement_count": len(index.requirements),
        },
    )
    return report


def mirror_source_fingerprint(project_id: int | None) -> str:
    from nl_coding_agent.persistence import database

    value = database.get_json_setting(_mirror_key(project_id))
    return str(value.get("source_fingerprint") or "")

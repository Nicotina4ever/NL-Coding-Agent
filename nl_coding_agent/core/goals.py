"""Goal Mode G1: durable goals, milestones and decomposition (NL-BP-212/213).

Thin service layer over nl_coding_agent.persistence.goal_store. It reuses the
existing supervisor/SQLite/Flow substrate (missions/tasks/goal_missions links) and
does not create a competing scheduler: no mission is created, started or executed
here, no model/network/GUI is touched.

Durable lifecycle is explicit:
  planned -> active -> paused -> active ...; explicit block/unblock/cancel;
  completed only through complete_goal() with every milestone completed.
No operation silently completes a goal, and progress/next-work queries are
read-only.
"""
from __future__ import annotations

import json
from typing import Iterable, Mapping, Sequence

from nl_coding_agent.persistence import goal_store
from nl_coding_agent.persistence.database import init_db, log_event

GOAL_STATUSES: tuple[str, ...] = ("planned", "active", "paused", "blocked",
                                  "completed", "cancelled")
MILESTONE_STATUSES: tuple[str, ...] = ("pending", "active", "paused", "blocked",
                                       "completed", "cancelled")
PRIORITIES: tuple[str, ...] = ("P0", "P1", "P2", "P3")
PRIORITY_RANK = {priority: rank for rank, priority in enumerate(PRIORITIES)}
ORIGINS: tuple[str, ...] = ("user", "import", "template")
GOAL_TRIGGERS: tuple[str, ...] = ("manual", "evidence", "failure", "constraint")
TERMINAL_GOAL_STATUSES: tuple[str, ...] = ("completed", "cancelled")
GOAL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "planned": ("active", "blocked", "cancelled"),
    "active": ("paused", "blocked", "cancelled"),
    "paused": ("active", "blocked", "cancelled"),
    "blocked": ("active", "paused", "cancelled"),
    "completed": (),
    "cancelled": (),
}
PLAN_ITEM_FIELDS = ("key", "title", "description", "priority", "dependencies",
                    "acceptance_criteria", "evidence_refs", "risk",
                    "validation_strategy", "mission_intent")


class GoalError(RuntimeError):
    """Base class for goal/milestone contract failures."""


class GoalValidationError(GoalError):
    """A field or structured plan failed validation."""


class GoalNotFoundError(GoalError):
    """The requested goal/milestone does not exist."""


class GoalLifecycleError(GoalError):
    """An invalid status transition was requested."""


class GoalDependencyError(GoalError):
    """A goal/milestone dependency is missing or cyclic."""


class GoalDecompositionError(GoalError):
    """A structured decomposition plan is empty/invalid/duplicated/cyclic."""


def _text(value, field_name: str, *, max_len: int, allow_empty: bool = False) -> str:
    text = str(value or "").strip()
    if not text and not allow_empty:
        raise GoalValidationError(field_name + " must not be empty")
    if len(text) > max_len:
        raise GoalValidationError(field_name + " exceeds " + str(max_len) + " characters")
    return text


def _priority(value) -> str:
    text = str(value or "P1").strip().upper()
    if text not in PRIORITIES:
        raise GoalValidationError("priority must be one of " + ", ".join(PRIORITIES))
    return text


def _status(value, allowed: Sequence[str], field_name: str) -> str:
    text = str(value or "").strip().lower()
    if text not in allowed:
        raise GoalValidationError(field_name + " must be one of " + ", ".join(allowed))
    return text


def _int_id(value, field_name: str) -> int:
    if isinstance(value, bool):
        raise GoalValidationError(field_name + " must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise GoalValidationError(field_name + " must be an integer") from exc
    if parsed < 1:
        raise GoalValidationError(field_name + " must be positive")
    return parsed


def _string_list(value, field_name: str, *, max_items: int = 200,
                 max_item_len: int = 1000) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise GoalValidationError(field_name + " must be a list of strings")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise GoalValidationError(field_name + " must contain strings only")
        text = item.strip()
        if not text:
            continue
        if len(text) > max_item_len:
            raise GoalValidationError(field_name + " item is too long")
        result.append(text)
    if len(result) > max_items:
        raise GoalValidationError(field_name + " has too many items")
    return result


def _attachments(value) -> list:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise GoalValidationError("attachments must be a list")
    result = []
    for item in value:
        if isinstance(item, Mapping):
            result.append({str(key): str(val)[:500]
                           for key, val in item.items()})
        elif isinstance(item, str):
            result.append(item[:1000])
        else:
            raise GoalValidationError("attachments contain only strings/objects")
    if len(result) > 100:
        raise GoalValidationError("too many attachments")
    return result


def _metadata(value) -> dict:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise GoalValidationError("reference_metadata must be an object")
    result = {str(key)[:100]: str(item)[:1000] for key, item in value.items()}
    if len(result) > 100:
        raise GoalValidationError("reference_metadata is too large")
    return result


def _audit(event_kind: str, message: str, payload: Mapping | None = None, *,
           project_id: int | None = None) -> None:
    try:
        conn = init_db()
        try:
            log_event(conn, message, source="goals",
                      payload=json.dumps(dict(payload or {}), ensure_ascii=False,
                                         sort_keys=True, default=str),
                      project_id=project_id, event_kind=event_kind)
        finally:
            conn.close()
    except Exception:
        # Audit persistence must not corrupt the operation result; the operation
        # itself is already durable and can be audited from goals/milestones rows.
        pass


def _cycle(graph: Mapping[int, set[int]], start: int | None = None) -> list[int] | None:
    """Return one dependency cycle (list) or None. Deterministic DFS order."""
    visiting: set[int] = set()
    visited: set[int] = set()
    stack: list[int] = []

    def dfs(node: int) -> list[int] | None:
        if node in visited:
            return None
        if node in visiting:
            return stack[stack.index(node):] + [node]
        visiting.add(node)
        stack.append(node)
        for dep in sorted(graph.get(node, set())):
            found = dfs(dep)
            if found:
                return found
        stack.pop()
        visiting.discard(node)
        visited.add(node)
        return None

    nodes = [start] if start is not None else sorted(graph)
    for node in nodes:
        found = dfs(node)
        if found:
            return found
    return None


class GoalService:
    """Durable goal/milestone service; no scheduler or mission execution."""

    def __init__(self):
        goal_store.ensure_schema()

    # --------------------------------------------------------------- goals
    def create_goal(self, objective: str, *, title: str | None = None,
                    project_id: int | None = None,
                    acceptance_criteria: Iterable[str] = (),
                    priority: str = "P1", dependencies: Iterable[int] = (),
                    template_id: str | None = None,
                    template_version: str | None = None,
                    source: str = "", origin: str = "user",
                    attachments: Iterable = (),
                    reference_metadata: Mapping | None = None) -> dict:
        objective_text = _text(objective, "objective", max_len=4000)
        title_text = _text(title if title is not None else objective_text,
                           "title", max_len=300)
        priority_text = _priority(priority)
        origin_text = _status(origin, ORIGINS, "origin")
        if project_id is not None:
            project_id = _int_id(project_id, "project_id")
        criteria = _string_list(acceptance_criteria, "acceptance_criteria")
        attachments_value = _attachments(attachments)
        metadata = _metadata(reference_metadata)
        dependency_ids = sorted({_int_id(item, "goal dependency")
                                 for item in dependencies or ()})
        if dependency_ids:
            existing = {goal["id"] for goal in goal_store.list_goals(limit=500)}
            missing = [item for item in dependency_ids if item not in existing]
            if missing:
                raise GoalDependencyError("missing dependency goal(s): "
                                          + ", ".join(str(item) for item in missing))
        source_text = _text(source, "source", max_len=500, allow_empty=True) \
            if source else ""
        template_text = _text(template_id, "template_id", max_len=200, allow_empty=True) \
            if template_id else None
        version_text = _text(template_version, "template_version", max_len=100,
                             allow_empty=True) if template_version else None
        goal_id = goal_store.create_goal(
            project_id, title_text, objective_text,
            acceptance_criteria=criteria, priority=priority_text, status="planned",
            dependencies=dependency_ids, template_id=template_text,
            template_version=version_text, source=source_text, origin=origin_text,
            attachments=attachments_value, reference_metadata=metadata)
        _audit("goal_created", "Goal created: " + title_text,
               {"goal_id": goal_id, "priority": priority_text,
                "dependencies": dependency_ids}, project_id=project_id)
        return self.get_goal(goal_id)

    def get_goal(self, goal_id: int) -> dict:
        goal = goal_store.get_goal(_int_id(goal_id, "goal_id"))
        if goal is None:
            raise GoalNotFoundError("goal not found: " + str(goal_id))
        return goal

    def list_goals(self, *, project_id: int | None = None,
                   status: str | None = None, limit: int = 200,
                   offset: int = 0) -> list[dict]:
        if status is not None:
            status = _status(status, GOAL_STATUSES, "status")
        return goal_store.list_goals(project_id=project_id, status=status,
                                     limit=limit, offset=offset)

    def update_goal(self, goal_id: int, **fields) -> dict:
        goal = self.get_goal(goal_id)
        if goal["status"] in TERMINAL_GOAL_STATUSES:
            raise GoalLifecycleError("cannot update a terminal goal: " + goal["status"])
        allowed = {"title", "objective", "acceptance_criteria", "priority",
                   "dependencies", "template_id", "template_version", "source",
                   "origin", "attachments", "reference_metadata"}
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise GoalValidationError("unsupported goal fields: " + ", ".join(unknown))
        changes = {}
        if "title" in fields:
            changes["title"] = _text(fields["title"], "title", max_len=300)
        if "objective" in fields:
            changes["objective"] = _text(fields["objective"], "objective",
                                         max_len=4000)
        if "acceptance_criteria" in fields:
            changes["acceptance_criteria"] = _string_list(
                fields["acceptance_criteria"], "acceptance_criteria")
        if "priority" in fields:
            changes["priority"] = _priority(fields["priority"])
        if "origin" in fields:
            changes["origin"] = _status(fields["origin"], ORIGINS, "origin")
        if "template_id" in fields:
            changes["template_id"] = (str(fields["template_id"]).strip() or None)
        if "template_version" in fields:
            changes["template_version"] = (str(fields["template_version"]).strip()
                                            or None)
        if "source" in fields:
            changes["source"] = str(fields["source"] or "").strip()[:500]
        if "attachments" in fields:
            changes["attachments"] = _attachments(fields["attachments"])
        if "reference_metadata" in fields:
            changes["reference_metadata"] = _metadata(fields["reference_metadata"])
        if "dependencies" in fields:
            dependencies = sorted({_int_id(item, "goal dependency")
                                   for item in fields["dependencies"] or ()})
            self._validate_goal_dependencies(goal_id, dependencies)
            changes["dependencies"] = dependencies
        updated = goal_store.update_goal(goal_id, changes)
        _audit("goal_updated", "Goal updated: " + str(goal_id),
               {"goal_id": goal_id, "fields": sorted(changes)},
               project_id=goal.get("project_id"))
        return updated

    def _validate_goal_dependencies(self, goal_id: int | None,
                                    dependencies: Iterable[int]) -> None:
        requested = list(dependencies)
        if goal_id is not None and goal_id in requested:
            raise GoalDependencyError("goal cannot depend on itself")
        goals = {goal["id"]: set(int(item) for item in goal["dependencies"])
                 for goal in goal_store.list_goals(limit=500)}
        if goal_id is not None and goal_id in goals:
            goals[goal_id] = set(requested)
        else:
            goals[-1] = set(requested)  # temporary node for a not-yet-created goal
        missing = sorted(dep for dep in requested if dep not in goals
                         and dep != -1)
        if missing:
            raise GoalDependencyError("missing dependency goal(s): "
                                      + ", ".join(str(item) for item in missing))
        cycle = _cycle(goals)
        if cycle:
            raise GoalDependencyError("goal dependency cycle: "
                                      + " -> ".join(str(item) for item in cycle))

    def _transition(self, goal_id: int, target: str) -> dict:
        goal = self.get_goal(goal_id)
        current = goal["status"]
        if target not in GOAL_TRANSITIONS.get(current, ()):
            raise GoalLifecycleError(
                "invalid goal transition: " + current + " -> " + target)
        updated = goal_store.set_goal_status(goal_id, target)
        _audit("goal_lifecycle", "Goal " + current + " -> " + target,
               {"goal_id": goal_id, "from": current, "to": target},
               project_id=goal.get("project_id"))
        return updated

    def activate_goal(self, goal_id: int) -> dict:
        return self._transition(goal_id, "active")

    def pause_goal(self, goal_id: int) -> dict:
        return self._transition(goal_id, "paused")

    def resume_goal(self, goal_id: int) -> dict:
        goal = self.get_goal(goal_id)
        if goal["status"] != "paused":
            raise GoalLifecycleError("only a paused goal can be resumed")
        return self._transition(goal_id, "active")

    def block_goal(self, goal_id: int, reason: str = "") -> dict:
        goal = self.get_goal(goal_id)
        if goal["status"] not in ("planned", "active", "paused"):
            raise GoalLifecycleError("cannot block goal in status " + goal["status"])
        updated = goal_store.set_goal_status(goal_id, "blocked")
        _audit("goal_lifecycle", "Goal blocked",
               {"goal_id": goal_id, "reason": str(reason or "")[:300]},
               project_id=goal.get("project_id"))
        return updated

    def unblock_goal(self, goal_id: int) -> dict:
        goal = self.get_goal(goal_id)
        if goal["status"] != "blocked":
            raise GoalLifecycleError("only a blocked goal can be unblocked")
        return self._transition(goal_id, "active")

    def cancel_goal(self, goal_id: int) -> dict:
        return self._transition(goal_id, "cancelled")

    def complete_goal(self, goal_id: int, evidence: Mapping | None = None) -> dict:
        """Explicit completion only: every milestone must already be completed."""
        goal = self.get_goal(goal_id)
        if goal["status"] != "active":
            raise GoalLifecycleError("goal completion requires active status, got "
                                     + goal["status"])
        milestones = goal_store.list_milestones(goal_id)
        if not milestones:
            raise GoalLifecycleError("goal cannot complete without milestones")
        incomplete = [item["id"] for item in milestones
                      if item["status"] != "completed"]
        if incomplete:
            raise GoalLifecycleError("goal has incomplete milestone(s): "
                                     + ", ".join(str(item) for item in incomplete))
        updated = goal_store.set_goal_status(goal_id, "completed")
        _audit("goal_completed", "Goal completed explicitly",
               {"goal_id": goal_id, "evidence": dict(evidence or {})},
               project_id=goal.get("project_id"))
        return updated

    # ----------------------------------------------------------- milestones
    def _validate_milestone_dependencies(self, goal_id: int,
                                         dependencies: Iterable[int],
                                         milestone_id: int | None = None) -> None:
        existing = {item["id"]: set(int(dep) for dep in item["dependencies"])
                    for item in goal_store.list_milestones(goal_id)}
        if milestone_id is not None and milestone_id not in existing:
            raise GoalNotFoundError("milestone not found in goal: " + str(milestone_id))
        requested = sorted({_int_id(item, "milestone dependency")
                            for item in dependencies or ()})
        if milestone_id is not None and milestone_id in requested:
            raise GoalDependencyError("milestone cannot depend on itself")
        for dep in requested:
            if dep not in existing:
                raise GoalDependencyError("missing milestone dependency: " + str(dep))
        graph = dict(existing)
        if milestone_id is not None:
            graph[milestone_id] = set(requested)
        else:
            graph[-1] = set(requested)
        cycle = _cycle(graph)
        if cycle:
            raise GoalDependencyError("milestone dependency cycle: "
                                      + " -> ".join(str(item) for item in cycle))

    def create_milestone(self, goal_id: int, title: str, *, description: str = "",
                         priority: str = "P1", status: str = "pending",
                         dependencies: Iterable[int] = (),
                         acceptance_criteria: Iterable[str] = (),
                         evidence_refs: Iterable = (),
                         risk: str = "", validation_strategy: str = "",
                         mission_intent: str = "",
                         ordering: int | None = None) -> dict:
        goal = self.get_goal(goal_id)
        if goal["status"] in TERMINAL_GOAL_STATUSES:
            raise GoalLifecycleError("cannot add milestones to a terminal goal")
        priority_text = _priority(priority)
        status_text = _status(status, MILESTONE_STATUSES, "milestone status")
        dependency_ids = sorted({_int_id(item, "milestone dependency")
                                 for item in dependencies or ()})
        self._validate_milestone_dependencies(goal_id, dependency_ids)
        milestone_id = goal_store.create_milestone(
            goal_id, _text(title, "title", max_len=300),
            description=_text(description, "description", max_len=4000,
                              allow_empty=True),
            priority=priority_text, status=status_text,
            ordering=ordering, dependencies=dependency_ids,
            acceptance_criteria=_string_list(acceptance_criteria,
                                             "acceptance_criteria"),
            evidence_refs=_string_list(evidence_refs, "evidence_refs",
                                       max_items=500),
            risk=str(risk or "")[:1000],
            validation_strategy=str(validation_strategy or "")[:2000],
            mission_intent=str(mission_intent or "")[:2000])
        _audit("milestone_created", "Milestone created",
               {"goal_id": goal_id, "milestone_id": milestone_id,
                "priority": priority_text})
        return self.get_milestone(milestone_id)

    def list_milestones(self, goal_id: int, *, status: str | None = None) -> list[dict]:
        self.get_goal(goal_id)
        if status is not None:
            status = _status(status, MILESTONE_STATUSES, "milestone status")
        return goal_store.list_milestones(goal_id, status=status)

    def get_milestone(self, milestone_id: int) -> dict:
        milestone = goal_store.get_milestone(_int_id(milestone_id, "milestone_id"))
        if milestone is None:
            raise GoalNotFoundError("milestone not found: " + str(milestone_id))
        return milestone

    def update_milestone(self, milestone_id: int, **fields) -> dict:
        milestone = self.get_milestone(milestone_id)
        goal = self.get_goal(milestone["goal_id"])
        if goal["status"] in TERMINAL_GOAL_STATUSES:
            raise GoalLifecycleError("cannot update milestones of a terminal goal")
        allowed = {"title", "description", "priority", "status", "ordering",
                   "dependencies", "acceptance_criteria", "evidence_refs",
                   "risk", "validation_strategy", "mission_intent"}
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise GoalValidationError("unsupported milestone fields: "
                                      + ", ".join(unknown))
        changes = {}
        if "title" in fields:
            changes["title"] = _text(fields["title"], "title", max_len=300)
        if "description" in fields:
            changes["description"] = _text(fields["description"], "description",
                                            max_len=4000, allow_empty=True)
        if "priority" in fields:
            changes["priority"] = _priority(fields["priority"])
        if "status" in fields:
            changes["status"] = _status(fields["status"], MILESTONE_STATUSES,
                                        "milestone status")
        if "ordering" in fields:
            try:
                ordering = int(fields["ordering"])
            except (TypeError, ValueError) as exc:
                raise GoalValidationError("ordering must be an integer") from exc
            if ordering < 0:
                raise GoalValidationError("ordering must be non-negative")
            changes["ordering"] = ordering
        if "dependencies" in fields:
            self._validate_milestone_dependencies(
                milestone["goal_id"], fields["dependencies"], milestone_id)
            changes["dependencies"] = sorted(
                {_int_id(item, "milestone dependency")
                 for item in fields["dependencies"] or ()})
        if "acceptance_criteria" in fields:
            changes["acceptance_criteria"] = _string_list(
                fields["acceptance_criteria"], "acceptance_criteria")
        if "evidence_refs" in fields:
            changes["evidence_refs"] = _string_list(
                fields["evidence_refs"], "evidence_refs", max_items=500)
        for name, limit in (("risk", 1000), ("validation_strategy", 2000),
                            ("mission_intent", 2000)):
            if name in fields:
                changes[name] = str(fields[name] or "")[:limit]
        updated = goal_store.update_milestone(milestone_id, changes)
        _audit("milestone_updated", "Milestone updated",
               {"goal_id": milestone["goal_id"], "milestone_id": milestone_id,
                "fields": sorted(changes)})
        return updated

    def delete_milestone(self, milestone_id: int) -> bool:
        milestone = self.get_milestone(milestone_id)
        goal = self.get_goal(milestone["goal_id"])
        if goal["status"] in TERMINAL_GOAL_STATUSES:
            raise GoalLifecycleError("cannot delete milestones of a terminal goal")
        dependents = goal_store.milestones_depending_on(milestone_id)
        if dependents:
            raise GoalDependencyError(
                "milestone is a dependency of other milestones: "
                + ", ".join(str(item["id"]) for item in dependents))
        deleted = goal_store.delete_milestone(milestone_id)
        _audit("milestone_deleted", "Milestone deleted",
               {"goal_id": milestone["goal_id"], "milestone_id": milestone_id})
        return deleted

    # -------------------------------------------------------- decomposition
    def decompose_goal(self, goal_id: int, plan: Sequence[Mapping]) -> list[dict]:
        goal = self.get_goal(goal_id)
        if goal["status"] in TERMINAL_GOAL_STATUSES:
            raise GoalDecompositionError("cannot decompose a terminal goal")
        if not isinstance(plan, (list, tuple)):
            raise GoalDecompositionError("plan must be a non-empty list")
        if not plan:
            raise GoalDecompositionError("plan must not be empty")
        def _decomp(call, field_name: str):
            try:
                return call()
            except GoalValidationError as exc:
                raise GoalDecompositionError(
                    field_name + ": " + str(exc)) from exc

        existing = goal_store.list_milestones(goal_id)
        existing_by_id = {item["id"]: item for item in existing}
        existing_titles = {str(item["title"]).strip().casefold() for item in existing}
        keys: list[str] = []
        titles: list[str] = []
        specs: list[dict] = []
        for index, raw in enumerate(plan):
            if not isinstance(raw, Mapping):
                raise GoalDecompositionError("plan item #" + str(index + 1)
                                             + " must be an object")
            unknown = sorted(set(raw) - set(PLAN_ITEM_FIELDS))
            if unknown:
                raise GoalDecompositionError("unknown plan fields: "
                                             + ", ".join(str(item) for item in unknown))
            key = str(raw.get("key") or ("m" + str(index + 1))).strip()
            if not key or len(key) > 100:
                raise GoalDecompositionError("plan key is invalid")
            key_folded = key.casefold()
            if key_folded in {item.casefold() for item in keys}:
                raise GoalDecompositionError("duplicate plan key: " + key)
            keys.append(key)
            title = _decomp(lambda: _text(raw.get("title"), "title", max_len=300), "title")
            title_folded = title.casefold()
            if title_folded in existing_titles or title_folded in {
                    item.casefold() for item in titles}:
                raise GoalDecompositionError("duplicate milestone title: " + title)
            titles.append(title)
            specs.append({
                "key": key, "title": title,
                "description": _decomp(lambda: _text(
                    raw.get("description"), "description", max_len=4000,
                    allow_empty=True), "description"),
                "priority": _decomp(lambda: _priority(
                    raw.get("priority") or "P1"), "priority"),
                "acceptance_criteria": _decomp(lambda: _string_list(
                    raw.get("acceptance_criteria"), "acceptance_criteria"),
                    "acceptance_criteria"),
                "evidence_refs": _decomp(lambda: _string_list(
                    raw.get("evidence_refs"), "evidence_refs", max_items=500),
                    "evidence_refs"),
                "risk": str(raw.get("risk") or "")[:1000],
                "validation_strategy": str(raw.get("validation_strategy") or "")[:2000],
                "mission_intent": str(raw.get("mission_intent") or "")[:2000],
                "raw_dependencies": list(raw.get("dependencies") or []),
            })
        existing_ids = set(existing_by_id)
        dependency_map: dict[str, list[int]] = {}
        for spec in specs:
            resolved: list[int] = []
            seen: set[int] = set()
            for item in spec["raw_dependencies"]:
                if isinstance(item, str) and item in keys:
                    if item == spec["key"]:
                        raise GoalDecompositionError("milestone cannot depend on itself: "
                                                     + spec["key"])
                    resolved.append(-(keys.index(item) + 1))  # temporary marker
                elif isinstance(item, int) and not isinstance(item, bool):
                    if item not in existing_ids:
                        raise GoalDecompositionError(
                            "plan references missing existing milestone: " + str(item))
                    resolved.append(item)
                else:
                    raise GoalDecompositionError(
                        "plan dependency must be an existing milestone id or plan key: "
                        + repr(item))
            if len(resolved) != len(set(resolved)):
                raise GoalDecompositionError("duplicate dependency in plan key: "
                                             + spec["key"])
            dependency_map[spec["key"]] = resolved
        # Cycle detection over plan keys (temporary markers 1..n map to keys order).
        graph: dict[int, set[int]] = {-(index + 1): set()
                                      for index in range(len(specs))}
        key_index = {key: -(index + 1) for index, key in enumerate(keys)}
        for spec in specs:
            node = key_index[spec["key"]]
            for item in spec["raw_dependencies"]:
                if isinstance(item, str) and item in key_index:
                    graph[node].add(key_index[item])
        cycle = _cycle(graph)
        if cycle:
            readable = [keys[-index - 1] if index < 0 else str(index)
                        for index in cycle]
            raise GoalDecompositionError("plan dependency cycle: "
                                         + " -> ".join(readable))
        # Resolve existing dependencies; create milestones first with no deps.
        ordering = goal_store.next_milestone_order(goal_id)
        bulk_specs = []
        for index, spec in enumerate(specs):
            existing_deps = [item for item in dependency_map[spec["key"]]
                             if isinstance(item, int) and item in existing_ids]
            bulk_specs.append({
                "title": spec["title"], "description": spec["description"],
                "priority": spec["priority"], "status": "pending",
                "ordering": ordering + index, "dependencies": existing_deps,
                "acceptance_criteria": spec["acceptance_criteria"],
                "evidence_refs": spec["evidence_refs"],
                "risk": spec["risk"],
                "validation_strategy": spec["validation_strategy"],
                "mission_intent": spec["mission_intent"],
            })
        created = goal_store.create_milestones_bulk(goal_id, bulk_specs)
        created_by_key = {keys[index]: created[index]["id"]
                          for index in range(len(created))}
        for spec in specs:
            resolved = []
            for item in spec["raw_dependencies"]:
                if isinstance(item, str):
                    resolved.append(created_by_key[item])
                else:
                    resolved.append(int(item))
            if resolved:
                goal_store.update_milestone(created_by_key[spec["key"]],
                                            {"dependencies": sorted(set(resolved))})
        _audit("goal_decomposed", "Goal decomposed into milestones",
               {"goal_id": goal_id, "milestone_ids": [item["id"] for item in created]})
        return goal_store.list_milestones(goal_id)

    # ------------------------------------------------------------- replanning
    @staticmethod
    def _plan_milestone_snapshot(milestone: Mapping) -> dict:
        fields = ("id", "title", "description", "priority", "status", "ordering",
                  "dependencies", "acceptance_criteria", "evidence_refs", "risk",
                  "validation_strategy", "mission_intent")
        return {name: milestone.get(name) for name in fields}

    @staticmethod
    def _replan_evidence(evidence_refs) -> list:
        if evidence_refs is None:
            return []
        if not isinstance(evidence_refs, (list, tuple)):
            raise GoalValidationError("evidence_refs must be a list")
        result = []
        for item in evidence_refs:
            if isinstance(item, Mapping):
                result.append({str(key)[:100]: str(value)[:1000]
                               for key, value in item.items()})
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    result.append(text[:1000])
            else:
                raise GoalValidationError(
                    "evidence_refs contain only strings or objects")
        if len(result) > 100:
            raise GoalValidationError("too many evidence_refs")
        return result

    @staticmethod
    def _replan_trigger(trigger) -> str:
        value = str(trigger or "manual").strip().lower()
        if value not in GOAL_TRIGGERS:
            raise GoalValidationError(
                "trigger must be one of " + ", ".join(GOAL_TRIGGERS))
        return value

    def _parse_replan_plan(self, goal: dict, plan: Sequence[Mapping]) -> tuple[list[dict], dict]:
        if not isinstance(plan, (list, tuple)):
            raise GoalDecompositionError("plan must be a non-empty list")
        if not plan:
            raise GoalDecompositionError("plan must not be empty")
        existing = goal_store.list_milestones(goal["id"])
        existing_by_title = {str(item["title"]).strip().casefold(): item
                             for item in existing}
        existing_by_id = {int(item["id"]): item for item in existing}

        def _decomp(call, field_name: str):
            try:
                return call()
            except GoalValidationError as exc:
                raise GoalDecompositionError(
                    field_name + ": " + str(exc)) from exc

        keys: list[str] = []
        titles: list[str] = []
        specs: list[dict] = []
        for index, raw in enumerate(plan):
            if not isinstance(raw, Mapping):
                raise GoalDecompositionError("plan item #" + str(index + 1)
                                             + " must be an object")
            unknown = sorted(set(raw) - set(PLAN_ITEM_FIELDS))
            if unknown:
                raise GoalDecompositionError("unknown plan fields: "
                                             + ", ".join(str(item) for item in unknown))
            key = str(raw.get("key") or ("m" + str(index + 1))).strip()
            if not key or len(key) > 100:
                raise GoalDecompositionError("plan key is invalid")
            if key.casefold() in {item.casefold() for item in keys}:
                raise GoalDecompositionError("duplicate plan key: " + key)
            keys.append(key)
            title = _decomp(lambda: _text(raw.get("title"), "title", max_len=300), "title")
            if title.casefold() in {item.casefold() for item in titles}:
                raise GoalDecompositionError("duplicate milestone title: " + title)
            titles.append(title)
            specs.append({
                "key": key,
                "title": title,
                "description": _decomp(lambda: _text(
                    raw.get("description"), "description", max_len=4000,
                    allow_empty=True), "description"),
                "priority": _decomp(lambda: _priority(
                    raw.get("priority") or "P1"), "priority"),
                "acceptance_criteria": _decomp(lambda: _string_list(
                    raw.get("acceptance_criteria"), "acceptance_criteria"),
                    "acceptance_criteria"),
                "evidence_refs": _decomp(lambda: _string_list(
                    raw.get("evidence_refs"), "evidence_refs", max_items=500),
                    "evidence_refs"),
                "risk": str(raw.get("risk") or "")[:1000],
                "validation_strategy": str(raw.get("validation_strategy") or "")[:2000],
                "mission_intent": str(raw.get("mission_intent") or "")[:2000],
                "raw_dependencies": list(raw.get("dependencies") or []),
            })
        key_index = {key: index for index, key in enumerate(keys)}
        title_index = {title.casefold(): index for index, title in enumerate(titles)}
        for spec in specs:
            targets: list[int] = []
            for item in spec["raw_dependencies"]:
                if isinstance(item, str) and item in key_index:
                    target = key_index[item]
                    if target == key_index[spec["key"]]:
                        raise GoalDecompositionError(
                            "milestone cannot depend on itself: " + spec["key"])
                elif isinstance(item, int) and not isinstance(item, bool):
                    existing_item = existing_by_id.get(int(item))
                    if existing_item is None:
                        raise GoalDecompositionError(
                            "plan references missing existing milestone: " + str(item))
                    folded = str(existing_item["title"]).strip().casefold()
                    if folded not in title_index:
                        raise GoalDecompositionError(
                            "plan dependency references a milestone removed by this "
                            "plan: " + str(item))
                    target = title_index[folded]
                else:
                    raise GoalDecompositionError(
                        "plan dependency must be an existing milestone id or plan key: "
                        + repr(item))
                targets.append(target)
            if len(targets) != len(set(targets)):
                raise GoalDecompositionError("duplicate dependency in plan key: "
                                             + spec["key"])
            spec["dependency_titles"] = [titles[index] for index in sorted(set(targets))]
        graph = {index: set() for index in range(len(specs))}
        for index, spec in enumerate(specs):
            for title in spec["dependency_titles"]:
                graph[index].add(title_index[title.casefold()])
        cycle = _cycle(graph)
        if cycle:
            readable = [titles[index] for index in cycle]
            raise GoalDecompositionError("plan dependency cycle: "
                                         + " -> ".join(readable))
        return specs, {"existing": existing, "existing_by_id": existing_by_id}

    @staticmethod
    def _diff_plan(old_milestones: list, new_milestones: list) -> dict:
        old_by_title = {str(item["title"]).strip().casefold(): item
                        for item in old_milestones}
        new_by_title = {str(item["title"]).strip().casefold(): item
                        for item in new_milestones}
        added = [item["title"] for item in new_milestones
                 if str(item["title"]).strip().casefold() not in old_by_title]
        removed = [item["title"] for item in old_milestones
                   if str(item["title"]).strip().casefold() not in new_by_title]
        changed = []
        unchanged = []
        for new_item in new_milestones:
            folded = str(new_item["title"]).strip().casefold()
            old_item = old_by_title.get(folded)
            if old_item is None:
                continue
            fields = {}
            for name in ("description", "priority", "acceptance_criteria",
                         "evidence_refs", "risk", "validation_strategy",
                         "mission_intent"):
                if old_item.get(name) != new_item.get(name):
                    fields[name] = {"from": old_item.get(name),
                                    "to": new_item.get(name)}
            if old_item.get("ordering") != new_item.get("ordering"):
                fields["ordering"] = {"from": old_item.get("ordering"),
                                      "to": new_item.get("ordering")}
            old_deps = sorted(str(item) for item in old_item.get("dependencies") or [])
            new_deps = sorted(str(item) for item in new_item.get("dependencies") or [])
            if old_deps != new_deps:
                fields["dependencies"] = {"from": old_deps, "to": new_deps}
            if fields:
                changed.append({"title": new_item["title"], "fields": fields})
            else:
                unchanged.append(new_item["title"])
        return {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
            "counts": {"added": len(added), "removed": len(removed),
                       "changed": len(changed), "unchanged": len(unchanged)},
        }

    def replan_goal(self, goal_id: int, plan: Sequence[Mapping], rationale: str,
                    trigger: str = "manual", evidence_refs=None) -> dict:
        """Versioned replanning: replace current milestones, preserve prior versions.

        The goal objective/title are immutable here. Only existing mission links are
        retained/created elsewhere; no mission is created or executed.
        """
        goal = self.get_goal(goal_id)
        if goal["status"] in TERMINAL_GOAL_STATUSES:
            raise GoalLifecycleError("cannot replan a terminal goal")
        rationale_text = _text(rationale, "rationale", max_len=4000)
        trigger_text = self._replan_trigger(trigger)
        evidence = self._replan_evidence(evidence_refs)
        if trigger_text == "evidence" and not evidence:
            raise GoalValidationError(
                "an evidence-triggered replan requires non-empty evidence_refs")
        specs, context = self._parse_replan_plan(goal, plan)
        existing = context["existing"]
        existing_by_title = {str(item["title"]).strip().casefold(): item
                             for item in existing}
        old_snapshot = [self._plan_milestone_snapshot(item) for item in existing]
        versions = goal_store.list_plan_versions(goal_id, limit=500)
        if versions:
            next_version = max(int(item["version"]) for item in versions) + 1
            previous_current = versions[0] if versions else None
        else:
            next_version = 1
            previous_current = None
        # Provisional orderings avoid the unique(goal_id, ordering) index while
        # matching/creating/deleting the new current set.
        matched: dict[str, dict] = {}
        for index, spec in enumerate(specs):
            folded = spec["title"].casefold()
            current = existing_by_title.get(folded)
            if current is not None:
                matched[folded] = current
                goal_store.update_milestone(current["id"], {"ordering": 10000 + index})
        kept_titles = {spec["title"].casefold() for spec in specs}
        for item in existing:
            if str(item["title"]).strip().casefold() not in kept_titles:
                goal_store.delete_milestone(item["id"])
        created_by_title: dict[str, int] = {}
        for index, spec in enumerate(specs):
            if spec["title"].casefold() in matched:
                created_by_title[spec["title"].casefold()] = matched[
                    spec["title"].casefold()]["id"]
                continue
            milestone_id = goal_store.create_milestone(
                goal_id, spec["title"], description=spec["description"],
                priority=spec["priority"], status="pending",
                ordering=10000 + index, dependencies=[],
                acceptance_criteria=spec["acceptance_criteria"],
                evidence_refs=spec["evidence_refs"], risk=spec["risk"],
                validation_strategy=spec["validation_strategy"],
                mission_intent=spec["mission_intent"])
            created_by_title[spec["title"].casefold()] = milestone_id
        title_to_id = dict(created_by_title)
        for spec in specs:
            milestone_id = title_to_id[spec["title"].casefold()]
            dependencies = sorted({title_to_id[title.casefold()]
                                   for title in spec["dependency_titles"]})
            goal_store.update_milestone(milestone_id, {
                "description": spec["description"], "priority": spec["priority"],
                "ordering": specs.index(spec), "dependencies": dependencies,
                "acceptance_criteria": spec["acceptance_criteria"],
                "evidence_refs": spec["evidence_refs"], "risk": spec["risk"],
                "validation_strategy": spec["validation_strategy"],
                "mission_intent": spec["mission_intent"]})
        current_milestones = goal_store.list_milestones(goal_id)
        new_snapshot = [self._plan_milestone_snapshot(item)
                        for item in current_milestones]
        diff = self._diff_plan(old_snapshot, new_snapshot)
        version = goal_store.create_plan_version(
            goal_id, next_version, str(goal["objective"]), new_snapshot,
            rationale_text, trigger_text, evidence, diff,
            supersedes=(int(previous_current["version"])
                        if previous_current is not None else None),
            is_current=True)
        _audit("goal_replanned", "Goal replanned to version " + str(next_version),
               {"goal_id": goal_id, "version": next_version,
                "trigger": trigger_text, "rationale": rationale_text[:500],
                "diff": diff["counts"]}, project_id=goal.get("project_id"))
        return {
            "goal": self.get_goal(goal_id),
            "version": version,
            "current_plan": version,
            "milestones": current_milestones,
            "diff": diff,
            "versions": goal_store.list_plan_versions(goal_id, limit=500),
        }

    def list_plan_versions(self, goal_id: int, *, limit: int = 100) -> list[dict]:
        self.get_goal(goal_id)
        return goal_store.list_plan_versions(goal_id, limit=limit)

    def current_plan(self, goal_id: int) -> dict:
        goal = self.get_goal(goal_id)
        current = goal_store.get_current_plan_version(goal_id)
        if current is not None:
            return current
        milestones = goal_store.list_milestones(goal_id)
        return {
            "goal_id": goal_id, "version": None,
            "objective_snapshot": str(goal["objective"]),
            "milestones": [self._plan_milestone_snapshot(item)
                           for item in milestones],
            "rationale": "", "trigger": "baseline", "evidence_refs": [],
            "diff": {}, "supersedes": None, "is_current": True,
            "created_at": goal.get("created_at"),
        }

    def plan_diff(self, goal_id: int, version: int | None = None) -> dict:
        goal = self.get_goal(goal_id)
        if version is None:
            current = self.current_plan(goal_id)
            return current.get("diff") or {}
        record = goal_store.get_plan_version(goal_id, version)
        if record is None:
            raise GoalNotFoundError("plan version not found: " + str(version))
        return record.get("diff") or {}

    def list_goal_links(self, goal_id: int) -> list[dict]:
        self.get_goal(goal_id)
        return goal_store.list_goal_links(goal_id)

    # ------------------------------------------------------------- progress
    def _goal_dependencies_met(self, goal: dict, all_goals: Mapping[int, dict]) -> bool:
        return all(all_goals.get(dep, {}).get("status") == "completed"
                   for dep in goal.get("dependencies") or [])

    def _milestone_dependencies_met(self, milestone: dict,
                                    milestones: Mapping[int, dict]) -> bool:
        return all(milestones.get(dep, {}).get("status") == "completed"
                   for dep in milestone.get("dependencies") or [])

    def eligible_milestones(self, goal_id: int) -> list[dict]:
        goal = self.get_goal(goal_id)
        all_goals = {item["id"]: item for item in goal_store.list_goals(limit=500)}
        if goal["status"] != "active" or not self._goal_dependencies_met(goal, all_goals):
            return []
        milestones = goal_store.list_milestones(goal_id)
        by_id = {item["id"]: item for item in milestones}
        return [item for item in milestones
                if item["status"] == "pending"
                and self._milestone_dependencies_met(item, by_id)]

    def next_work(self, *, goal_id: int | None = None, project_id: int | None = None,
                  limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        goals = {item["id"]: item for item in goal_store.list_goals(limit=500)}
        if goal_id is not None:
            self.get_goal(goal_id)
        candidates = []
        for goal in goals.values():
            if goal["status"] != "active":
                continue
            if project_id is not None and goal.get("project_id") != project_id:
                continue
            if goal_id is not None and goal["id"] != goal_id:
                continue
            if not self._goal_dependencies_met(goal, goals):
                continue
            milestones = goal_store.list_milestones(goal["id"])
            by_id = {item["id"]: item for item in milestones}
            for milestone in milestones:
                if milestone["status"] != "pending":
                    continue
                if not self._milestone_dependencies_met(milestone, by_id):
                    continue
                candidates.append({
                    "goal_id": goal["id"], "milestone_id": milestone["id"],
                    "title": milestone["title"],
                    "goal_title": goal["title"],
                    "priority": goal["priority"],
                    "milestone_priority": milestone["priority"],
                    "ordering": milestone["ordering"],
                    "goal_priority_rank": PRIORITY_RANK.get(goal["priority"], 9),
                    "milestone_priority_rank": PRIORITY_RANK.get(
                        milestone["priority"], 9),
                })
        candidates.sort(key=lambda item: (
            item["goal_priority_rank"], item["milestone_priority_rank"],
            item["goal_id"], item["ordering"], item["milestone_id"]))
        return candidates[:limit]

    def progress(self, goal_id: int) -> dict:
        goal = self.get_goal(goal_id)
        milestones = goal_store.list_milestones(goal_id)
        counts = {status: 0 for status in MILESTONE_STATUSES}
        for milestone in milestones:
            counts[milestone["status"]] = counts.get(milestone["status"], 0) + 1
        completed = counts["completed"]
        total = len(milestones)
        return {
            "goal_id": goal_id, "status": goal["status"],
            "priority": goal["priority"], "milestones_total": total,
            "milestones_completed": completed,
            "milestones_by_status": counts,
            "progress_percent": (round(completed * 100.0 / total, 1)
                                 if total else 0.0),
            "eligible_next_work": [item["id"]
                                   for item in self.eligible_milestones(goal_id)],
            "goal_dependencies_met": self._goal_dependencies_met(
                goal, {item["id"]: item for item in goal_store.list_goals(limit=500)}),
        }

    goal_progress = progress

    def progress_summary(self, *, project_id: int | None = None) -> dict:
        goals = goal_store.list_goals(project_id=project_id, limit=500)
        status_counts = {status: 0 for status in GOAL_STATUSES}
        total_milestones = completed_milestones = 0
        for goal in goals:
            status_counts[goal["status"]] = status_counts.get(goal["status"], 0) + 1
            milestones = goal_store.list_milestones(goal["id"])
            total_milestones += len(milestones)
            completed_milestones += sum(1 for item in milestones
                                        if item["status"] == "completed")
        return {
            "goals_total": len(goals), "goals_by_status": status_counts,
            "milestones_total": total_milestones,
            "milestones_completed": completed_milestones,
            "next_work": self.next_work(project_id=project_id, limit=20),
        }

    # -------------------------------------------------------------- links
    def link_goal_mission(self, goal_id: int, mission_id: int, *,
                          milestone_id: int | None = None,
                          role: str = "primary") -> dict:
        goal = self.get_goal(goal_id)
        mission_id = _int_id(mission_id, "mission_id")
        if not goal_store.mission_exists(mission_id):
            raise GoalNotFoundError("mission not found: " + str(mission_id))
        if milestone_id is not None:
            milestone = self.get_milestone(milestone_id)
            if milestone["goal_id"] != goal_id:
                raise GoalValidationError("milestone does not belong to the goal")
        link_id = goal_store.link_mission(goal_id, mission_id,
                                          milestone_id=milestone_id,
                                          role=str(role or "primary")[:50])
        _audit("goal_mission_linked", "Goal linked to existing mission",
               {"goal_id": goal_id, "mission_id": mission_id,
                "milestone_id": milestone_id}, project_id=goal.get("project_id"))
        return {"id": link_id, "goal_id": goal_id, "milestone_id": milestone_id,
                "mission_id": mission_id, "role": str(role or "primary")}

    def list_goal_missions(self, goal_id: int) -> list[dict]:
        self.get_goal(goal_id)
        return goal_store.list_goal_missions(goal_id)

    # convenience aliases (explicit names remain the primary API)
    activate = activate_goal
    pause = pause_goal
    resume = resume_goal
    cancel = cancel_goal
    complete = complete_goal
    add_milestone = create_milestone
    next_eligible_work = next_work
    eligible_next_work = next_work
    summary = progress_summary
    list_eligible = eligible_milestones

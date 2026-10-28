"""Bounded autonomous self-build loop with durable selection and recovery."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from nl_coding_agent.core import promotion
from nl_coding_agent.core.roadmap import next_mission
from nl_coding_agent.persistence.database import db_path
from nl_coding_agent.persistence.missions import (
    create_mission,
    find_mission_by_staging_dir,
    get_mission,
    list_missions,
)
from nl_coding_agent.projects.registry import open_project

MAX_AUTONOMOUS_MISSIONS = 5
RESUMABLE_STATUSES = ("running", "interrupted", "pending")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def state_path() -> Path:
    return db_path().parent / "selfbuild_state.json"


def _load_state() -> dict:
    path = state_path()
    if not path.exists():
        return {"projects": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"projects": {}}
    if not isinstance(data, dict):
        return {"projects": {}}
    data.setdefault("projects", {})
    return data


def _save_state(state: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def roadmap_fingerprint(roadmap: dict) -> str:
    source = Path(str(roadmap.get("source") or ""))
    if source.is_file():
        payload = source.read_text(encoding="utf-8", errors="replace")
    else:
        payload = f"{roadmap.get('title', '')}\n{roadmap.get('goal', '')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_harness_mission(mission: dict, harness_version: int) -> bool:
    return mission.get("harness_version") == harness_version


def select_resumable_mission(
    missions: list[dict], *, harness_version: int = promotion.HARNESS_VERSION
) -> dict | None:
    """Select resumable work, never a mission that predates the staged-candidate harness."""
    for status in RESUMABLE_STATUSES:
        for mission in missions:
            if mission.get("status") != status:
                continue
            if not _is_harness_mission(mission, harness_version):
                continue
            return mission
    return None


def completed_roadmap_mission(missions: list[dict], roadmap: dict) -> dict | None:
    title = str(roadmap.get("title") or "")
    goal = str(roadmap.get("goal") or "")
    for mission in missions:
        if mission.get("status") != "completed":
            continue
        if str(mission.get("title") or "") != title:
            continue
        if str(mission.get("goal") or "") != goal:
            continue
        return mission
    return None


def pending_roadmap_mission(
    missions: list[dict],
    roadmap: dict,
    *,
    harness_version: int = promotion.HARNESS_VERSION,
) -> dict | None:
    title = str(roadmap.get("title") or "")
    goal = str(roadmap.get("goal") or "")
    for mission in missions:
        if mission.get("status") != "pending":
            continue
        if not _is_harness_mission(mission, harness_version):
            continue
        if str(mission.get("title") or "") != title:
            continue
        if str(mission.get("goal") or "") != goal:
            continue
        return mission
    return None


def reconcile_completed_mission(
    project_state: dict, root: Path, mission: dict
) -> bool:
    try:
        roadmap = next_mission(root)
    except FileNotFoundError:
        return False
    if str(mission.get("title") or "") != str(roadmap.get("title") or ""):
        return False
    if str(mission.get("goal") or "") != str(roadmap.get("goal") or ""):
        return False
    project_state["last_completed_fingerprint"] = roadmap_fingerprint(roadmap)
    project_state["last_completed_mission_id"] = mission["id"]
    project_state["updated_at"] = _now()
    return True


def _log(message: str, on_event: Callable | None = None) -> None:
    line = f"[{_now()}] {message}"
    print(line, flush=True)
    log_dir = db_path().parent.parent / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "selfbuild.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    if on_event:
        on_event(message)


def _resume_command(root: Path, mission_id: int | None = None) -> str:
    base = (
        f'python\\python.exe nl_agent.py selfbuild --autonomous '
        f'--project "{root}"'
    )
    if mission_id is not None:
        return f"{base} --resume {mission_id}"
    return base


def _first_journal_mission_id(root: Path) -> int | None:
    basedir = root / "data" / "staging"
    if not basedir.is_dir():
        return None
    for journal in sorted(basedir.glob("*/promotion-journal.json")):
        match = re.match(r"mission-(\d+)-", journal.parent.name)
        if match:
            return int(match.group(1))
    return None


def _stage_dirs(root: Path) -> list[Path]:
    """Return candidate staging directories present under the project tree."""
    basedir = root / "data" / "staging"
    if not basedir.is_dir():
        return []
    return sorted(path for path in basedir.iterdir() if path.is_dir())


def _resume_command_for_results(
    root: Path, status: str, results: list[dict]
) -> str:
    mission_id = None
    if status == "blocked" and results:
        mission_id = results[-1].get("id")
    return _resume_command(root, mission_id)


def run_autonomous(
    project_root: str | Path,
    max_missions: int = 1,
    resume_mission_id: int | None = None,
    developer_model: str | None = None,
    reviewer_model: str | None = None,
    debug_model: str | None = None,
    stop_after: str | None = None,
    on_event: Callable | None = None,
    orchestrator_factory: Callable | None = None,
) -> dict:
    """Run bounded self-build missions, resuming durable work before creating new work."""
    root = Path(project_root).resolve()
    limit = max(1, min(int(max_missions), MAX_AUTONOMOUS_MISSIONS))
    project = open_project(root)
    project_id = int(project["id"])
    state = _load_state()
    project_state = state["projects"].setdefault(str(root), {})
    results: list[dict] = []
    stopped_reason = ""
    next_resume_id = resume_mission_id

    _log(f"Self-Build Mode starting in {root} (max missions: {limit})", on_event)

    missions_at_start = list_missions(project_id)
    legacy_resumable = [
        mission
        for mission in missions_at_start
        if mission.get("status") in RESUMABLE_STATUSES
        and not _is_harness_mission(mission, promotion.HARNESS_VERSION)
    ]
    if legacy_resumable:
        _log(
            "Ignoring legacy mission(s) from before the staged-candidate harness: "
            + ", ".join("#" + str(m["id"]) for m in legacy_resumable),
            on_event,
        )
    blocking = promotion.preflight(root, mission_lookup=find_mission_by_staging_dir)
    if blocking:
        stopped_reason = (
            "Unresolved candidate promotion state: " + " | ".join(blocking)
            + "; resume the mission to reconcile before starting new work."
        )
        _log(stopped_reason, on_event)
        return {
            "status": "blocked",
            "missions": [],
            "stopped_reason": stopped_reason,
            "resume_command": _resume_command(root, _first_journal_mission_id(root)),
        }

    for index in range(limit):
        missions = list_missions(project_id)
        mission = None
        selected_roadmap = None

        if next_resume_id is not None:
            mission = get_mission(next_resume_id)
            if not mission:
                raise ValueError(f"Mission #{next_resume_id} not found")
            if not _is_harness_mission(mission, promotion.HARNESS_VERSION):
                stopped_reason = (
                    f"Mission #{mission['id']} predates the staged-candidate harness "
                    "(harness_version != 2) and cannot be resumed safely. "
                    "Create a new mission instead."
                )
                _log(stopped_reason, on_event)
                _save_state(state)
                return {
                    "status": "blocked",
                    "missions": [],
                    "stopped_reason": stopped_reason,
                    "resume_command": _resume_command(root),
                }
            if mission.get("project_id") is None:
                from nl_coding_agent.persistence.missions import set_mission_project

                set_mission_project(next_resume_id, project_id)
                mission = get_mission(next_resume_id)
            next_resume_id = None
            _log(f"Selected explicit mission #{mission['id']} for resume", on_event)
        else:
            mission = select_resumable_mission(
                missions, harness_version=promotion.HARNESS_VERSION
            )
            if mission is not None:
                _log(
                    f"Selected durable mission #{mission['id']} "
                    f"({mission.get('status')})",
                    on_event,
                )

        if mission is None:
            try:
                roadmap = next_mission(root)
            except FileNotFoundError as exc:
                stopped_reason = str(exc)
                _log(f"No roadmap mission available: {stopped_reason}", on_event)
                break

            selected_roadmap = roadmap
            if roadmap.get("all_gates_done"):
                stopped_reason = "Roadmap acceptance gates are already marked complete."
                _log(stopped_reason, on_event)
                break

            fingerprint = roadmap_fingerprint(roadmap)
            if project_state.get("last_completed_fingerprint") == fingerprint:
                stopped_reason = (
                    "The current roadmap mission was already completed as "
                    f"mission #{project_state.get('last_completed_mission_id', '?')}. "
                    "Update docs/NEXT_SELF_BUILD_MISSION.md before continuing."
                )
                _log(stopped_reason, on_event)
                break

            completed = completed_roadmap_mission(missions, roadmap)
            if completed is not None:
                project_state["last_completed_fingerprint"] = fingerprint
                project_state["last_completed_mission_id"] = completed["id"]
                project_state["updated_at"] = _now()
                _save_state(state)
                stopped_reason = (
                    f"The current roadmap mission is already completed as mission "
                    f"#{completed['id']}. Update docs/NEXT_SELF_BUILD_MISSION.md."
                )
                _log(stopped_reason, on_event)
                break

            pending = pending_roadmap_mission(
                missions, roadmap, harness_version=promotion.HARNESS_VERSION
            )
            if pending is not None:
                mission = pending
                _log(f"Reusing pending roadmap mission #{mission['id']}", on_event)
            else:
                mission_id = create_mission(
                    project_id=project_id,
                    title=roadmap["title"],
                    goal=roadmap["goal"],
                )
                mission = get_mission(mission_id)
                _log(f"Created roadmap mission #{mission_id}", on_event)

        if mission.get("status") == "completed":
            results.append({
                "id": mission["id"],
                "status": "completed",
                "verdict": mission.get("review_verdict"),
                "diff_stat": mission.get("diff_stat"),
            })
            if selected_roadmap is not None:
                project_state["last_completed_fingerprint"] = roadmap_fingerprint(selected_roadmap)
                project_state["last_completed_mission_id"] = mission["id"]
                project_state["updated_at"] = _now()
                _save_state(state)
            elif reconcile_completed_mission(project_state, root, mission):
                _save_state(state)
            continue

        _log(
            f"Running mission #{mission['id']}: {str(mission.get('title') or '')[:100]}",
            on_event,
        )
        if orchestrator_factory:
            orch = orchestrator_factory(root)
        else:
            from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator

            orch = MultiAgentOrchestrator(root)

        result = orch.run_mission(
            mission_id=mission["id"],
            goal=mission.get("goal"),
            developer_model=developer_model,
            reviewer_model=reviewer_model,
            debug_model=debug_model,
            stop_after=stop_after,
        )
        results.append({
            "id": mission["id"],
            "status": result.get("status"),
            "verdict": result.get("verdict"),
            "diff_stat": result.get("diff_stat"),
            "error": result.get("error"),
        })

        if result.get("status") != "completed":
            stopped_reason = (
                f"Mission #{mission['id']} ended with status "
                f"{result.get('status')}."
            )
            if result.get("error"):
                stopped_reason += f" {result['error']}"
            _log(stopped_reason, on_event)
            break

        if selected_roadmap is not None:
            project_state["last_completed_fingerprint"] = roadmap_fingerprint(selected_roadmap)
            project_state["last_completed_mission_id"] = mission["id"]
            project_state["updated_at"] = _now()
            _save_state(state)
        elif reconcile_completed_mission(project_state, root, mission):
            _save_state(state)

        if index + 1 >= limit:
            stopped_reason = f"Reached the requested limit of {limit} mission(s)."
            break

    _save_state(state)
    statuses = {item.get("status") for item in results}
    if not results:
        status = "idle"
    elif statuses == {"completed"}:
        status = "completed"
    else:
        status = "blocked"
    return {
        "status": status,
        "missions": results,
        "stopped_reason": stopped_reason,
        "resume_command": _resume_command_for_results(root, status, results),
    }

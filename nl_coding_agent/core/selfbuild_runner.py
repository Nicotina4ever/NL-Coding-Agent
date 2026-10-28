"""Legacy bounded self-build loop - deprecated compatibility shim (stage 3 C3d).

The persistent supervisor (nl_coding_agent.core.supervisor) now owns mission
selection and execution. run_autonomous() remains as a thin adapter so existing
CLI launchers/tests keep working: it preserves the C5/C7 fail-closed guards
(promotion journal preflight, legacy harness refusal) and maps the supervisor
result to the legacy {status, missions, stopped_reason, resume_command} shape.
"""
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
from nl_coding_agent.core.supervisor import run_supervisor
from nl_coding_agent.core.workspace import logs_root
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
    log_dir = logs_root()
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


def _map_supervisor_result(result: dict, root: Path) -> dict:
    """Map a Supervisor.run() result to the legacy run_autonomous result shape."""
    sup_status = str(result.get("status") or "blocked")
    if sup_status in ("completed",):
        status = "completed"
    elif sup_status in ("idle", "off"):
        status = "idle"
    else:
        status = "blocked"
    missions = []
    for mission in result.get("missions") or []:
        missions.append({
            "id": mission.get("id"),
            "status": mission.get("status"),
            "verdict": mission.get("verdict"),
            "diff_stat": mission.get("diff_stat"),
            "error": mission.get("error"),
        })
    return {
        "status": status,
        "missions": missions,
        "stopped_reason": str(result.get("stopped_reason") or ""),
        "resume_command": str(result.get("resume_command") or _resume_command(root)),
        "supervisor": {
            "status": sup_status,
            "run_id": result.get("run_id"),
            "mode": result.get("mode"),
            "completed": result.get("completed"),
            "failed": result.get("failed"),
            "retry_after_s": result.get("retry_after_s"),
        },
    }


def _blocked_result(root: Path, reason: str, mission_id: int | None = None) -> dict:
    return {
        "status": "blocked",
        "missions": [],
        "stopped_reason": reason,
        "resume_command": _resume_command(root, mission_id),
    }


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
    """Deprecated adapter: delegate bounded self-build work to the stage-3 supervisor."""
    root = Path(project_root).resolve()
    limit = max(1, min(int(max_missions), MAX_AUTONOMOUS_MISSIONS))
    _log(
        "Self-Build Mode is deprecated; delegating to the persistent stage-3 supervisor "
        "(use: nl_agent.py supervisor run).",
        on_event,
    )
    if stop_after:
        _log(
            "--stop-after is a legacy recovery-test flag; the persistent supervisor stops "
            "at safe boundaries through supervisor stop/pause instead.",
            on_event,
        )

    # C7 guard: an explicitly selected legacy mission is never resumed by the new harness.
    if resume_mission_id is not None:
        mission = get_mission(resume_mission_id)
        if not mission:
            raise ValueError(f"Mission #{resume_mission_id} not found")
        if not _is_harness_mission(mission, promotion.HARNESS_VERSION):
            reason = (
                f"Mission #{mission['id']} predates the staged-candidate harness "
                "(harness_version != 2) and cannot be resumed safely. "
                "Create a new mission instead."
            )
            _log(reason, on_event)
            return _blocked_result(root, reason)
        if str(mission.get("status") or "") == "completed":
            _log(
                f"Mission #{mission['id']} is already completed; no new work is started.",
                on_event,
            )
            return {
                "status": "completed",
                "missions": [{
                    "id": mission["id"],
                    "status": "completed",
                    "verdict": mission.get("review_verdict"),
                    "diff_stat": mission.get("diff_stat"),
                    "error": None,
                }],
                "stopped_reason": f"Mission #{mission['id']} was already completed.",
                "resume_command": _resume_command(root),
            }
        if mission.get("project_id") is None:
            from nl_coding_agent.persistence.missions import set_mission_project

            project = open_project(root)
            set_mission_project(int(mission["id"]), int(project["id"]))
        _log(
            f"Selected explicit mission #{mission['id']}; the supervisor queue will "
            "resume it before selecting new work.",
            on_event,
        )

    project = open_project(root)
    project_id = int(project["id"])
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

    # C5 guard: unresolved promotion journals block new work before any model call.
    blocking = promotion.preflight(root, mission_lookup=find_mission_by_staging_dir)
    if blocking:
        reason = (
            "Unresolved candidate promotion state: " + " | ".join(blocking)
            + "; resume the mission to reconcile before starting new work."
        )
        _log(reason, on_event)
        return _blocked_result(root, reason, _first_journal_mission_id(root))

    event_sink = None
    if on_event is not None:
        def event_sink(payload: dict) -> None:  # type: ignore[no-redef]
            try:
                on_event(str((payload or {}).get("message") or ""))
            except Exception:
                pass

    try:
        supervisor_result = run_supervisor(
            root,
            project_id=project_id,
            mode="automatic",
            max_missions=limit,
            developer_model=developer_model,
            reviewer_model=reviewer_model,
            debug_model=debug_model,
            orchestrator_factory=orchestrator_factory,
            event_sink=event_sink,
        )
    except Exception as exc:  # noqa: BLE001 - legacy adapter surfaces a blocked result
        reason = "Supervisor delegation failed: " + str(exc)
        _log(reason, on_event)
        return _blocked_result(root, reason)

    mapped = _map_supervisor_result(supervisor_result, root)
    _log(
        "Supervisor delegation finished: " + mapped["status"]
        + (" (" + mapped["stopped_reason"] + ")" if mapped["stopped_reason"] else ""),
        on_event,
    )
    return mapped

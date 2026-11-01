"""Generate a goal plan and launch the persistent supervisor for one project.

Examples
--------
python scripts/nlcode/autopilot.py --project K:\\AI\\NL Coding Agent\\ParcoTest \
    --objective "Analizza la documentazione e avvia lo sviluppo" --dry-run

The dry run only reads and plans. Without --dry-run the script creates a Goal,
activates it and starts the normal Supervisor with --work-source goals. The
Supervisor owns retries, staged verification and reviewer handoffs; this script
does not babysit the run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nl_coding_agent.app.services import AppServices  # noqa: E402
from nl_coding_agent.persistence import database  # noqa: E402
from nl_coding_agent.projects.registry import open_project  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="NL Code plan-and-run autopilot")
    parser.add_argument("--project", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-missions", type=int, default=1)
    parser.add_argument("--mode", choices=("automatic", "assisted"), default="automatic")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    args = parser.parse_args()
    project_root = Path(args.project).resolve()
    database.init_db().close()
    project = open_project(project_root)
    services = AppServices()
    # Auto review is project-wide; plan generation itself remains read-only.
    services.set_access_profile(int(project["id"]), "auto-review")
    job_root = ROOT / ".workspace" / "jobs" / (
        "autopilot-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    job_root.mkdir(parents=True, exist_ok=False)
    plan = services.plan_generate(int(project["id"]), args.model, args.objective)
    (job_root / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print(json.dumps({"phase": "planned", "job_root": str(job_root),
                      "milestones": len(plan["milestones"]),
                      "title": plan["title"]}, ensure_ascii=False))
    if args.dry_run:
        return 0
    applied = services.plan_apply(int(project["id"]), plan, activate=True)
    (job_root / "goal.json").write_text(json.dumps(applied, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print(json.dumps({"phase": "goal_applied", "goal_id": applied["goal"]["id"],
                      "status": applied["status"]}, ensure_ascii=False))
    if args.no_launch:
        return 0
    command = [
        sys.executable, str(ROOT / "nl_agent.py"), "supervisor", "run",
        "--project", str(project_root),
        "--mode", args.mode,
        "--max-missions", str(max(1, min(args.max_missions, 5))),
        "--work-source", "goals",
    ]
    log_path = job_root / "supervisor.log"
    state_path = job_root / "state.json"
    with log_path.open("a", encoding="utf-8") as log:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, creationflags=creationflags,
                                   env={**os.environ, "NL_AUTOPILOT_JOB": str(job_root)})
    state_path.write_text(json.dumps({
        "pid": process.pid, "command": command, "started_at": datetime.now().isoformat(
            timespec="seconds"), "goal_id": applied["goal"]["id"], "status": "launched",
        "log": str(log_path),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"phase": "launched", "pid": process.pid,
                      "state": str(state_path), "log": str(log_path)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Detached supervisor wrapper with bounded automatic recovery.

This is not a model agent: it owns only the process lifecycle. The Supervisor
already performs mission-level retries, model fallback and staged verification;
this wrapper restarts a fresh Supervisor run after a non-recoverable process
exit, up to a bounded number of attempts, before reporting a block.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_state(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--goal-id", type=int, required=True)
    parser.add_argument("--max-missions", type=int, default=1)
    parser.add_argument("--mode", default="automatic")
    parser.add_argument("--recoveries", type=int, default=2)
    parser.add_argument("--job-root", required=True)
    args = parser.parse_args()
    job_root = Path(args.job_root)
    job_root.mkdir(parents=True, exist_ok=True)
    log_path = job_root / "supervisor.log"
    state_path = job_root / "state.json"
    stop_path = job_root / "STOP"
    command = [
        sys.executable, str(ROOT / "nl_agent.py"), "supervisor", "run",
        "--project", str(Path(args.project).resolve()),
        "--mode", str(args.mode),
        "--max-missions", str(max(1, min(int(args.max_missions), 5))),
        "--work-source", "goals",
    ]
    state = {"goal_id": args.goal_id, "attempts": 0, "status": "starting",
             "started_at": datetime.now().isoformat(timespec="seconds")}
    write_state(state_path, state)
    for attempt in range(1, max(1, int(args.recoveries)) + 2):
        if stop_path.exists():
            state.update(status="stopped", stop_reason="STOP sentinel",
                         finished_at=datetime.now().isoformat(timespec="seconds"))
            write_state(state_path, state)
            return 3
        state.update(attempts=attempt, status="running",
                     attempt_started_at=datetime.now().isoformat(timespec="seconds"))
        write_state(state_path, state)
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n=== NL Code supervisor attempt " + str(attempt) + " ===\n")
            log.flush()
            code = subprocess.call(command, cwd=str(ROOT), stdout=log,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   env={**os.environ, "NL_AUTOPILOT_JOB": str(job_root)})
        if code == 0:
            state.update(status="completed", exit_code=0,
                         finished_at=datetime.now().isoformat(timespec="seconds"))
            write_state(state_path, state)
            return 0
        state.update(last_exit_code=code)
        write_state(state_path, state)
        if attempt <= int(args.recoveries):
            time.sleep(3)
    state.update(status="blocked", exit_code=state.get("last_exit_code"),
                 finished_at=datetime.now().isoformat(timespec="seconds"),
                 reason="supervisor returned non-zero after bounded recovery attempts")
    write_state(state_path, state)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

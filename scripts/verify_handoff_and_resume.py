"""Verify Self-Build Mode handoff, autonomous state, SQLite records, and recovery evidence."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nl_coding_agent.core.roadmap import next_mission
from nl_coding_agent.core.selfbuild_runner import roadmap_fingerprint
from nl_coding_agent.persistence.database import db_path
from nl_coding_agent.persistence.missions import (
    get_handoffs,
    get_tasks,
    get_verification_runs,
    list_missions,
)
from nl_coding_agent.projects.registry import open_project

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"PASS: {message}")
    else:
        print(f"FAIL: {message}")
        FAILURES.append(message)


def run_tests() -> None:
    command = [sys.executable, "-m", "pytest", "-q"]
    print(f"\nRunning: {' '.join(command)}")
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    print(output)
    check(result.returncode == 0, "full test suite passes")


def main() -> int:
    project = open_project(ROOT)
    project_id = int(project["id"])
    missions = list_missions(project_id)

    print("=== Self-Build Mode launcher ===")
    launcher = ROOT / "scripts" / "launchers" / "Self-Build Mode.bat"
    check(launcher.exists(), "scripts/launchers/Self-Build Mode.bat exists")
    if launcher.exists():
        content = launcher.read_text(encoding="utf-8")
        for token in ("nl_agent.py", "selfbuild", "--autonomous", "--project"):
            check(token in content, f"launcher references {token}")

    print("\n=== Autonomous CLI ===")
    result = subprocess.run(
        [sys.executable, "nl_agent.py", "selfbuild", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    output = result.stdout + result.stderr
    check(result.returncode == 0, "selfbuild --help exits 0")
    check("--autonomous" in output, "selfbuild --help exposes --autonomous")
    check("--max-missions" in output, "selfbuild --help exposes --max-missions")
    check("--resume" in output, "selfbuild --help exposes --resume")

    print("\n=== Autonomous completion evidence ===")
    smoke = next(
        (
            m
            for m in missions
            if m.get("title") == "Self-Build Mode Regression Test"
            and m.get("status") == "completed"
        ),
        None,
    )
    check(smoke is not None, "completed Self-Build Mode Regression Test mission exists")
    if smoke:
        check(smoke.get("review_verdict") == "APPROVE", "smoke mission was approved")
        try:
            changed_paths = json.loads(smoke.get("changed_paths") or "[]")
        except Exception:
            changed_paths = []
        check(
            changed_paths == ["tests/test_selfbuild_mode.py"],
            "smoke mission only changed tests/test_selfbuild_mode.py",
        )
        tasks = get_tasks(smoke["id"])
        check(
            bool(tasks) and all(t["status"] == "completed" for t in tasks),
            "all smoke mission tasks completed",
        )
        handoffs = get_handoffs(smoke["id"])
        roles = {(h["from_role"], h["to_role"]) for h in handoffs}
        check(("developer", "tester") in roles, "developer -> tester handoff recorded")
        check(("tester", "reviewer") in roles, "tester -> reviewer handoff recorded")
        check(("reviewer", "orchestrator") in roles, "reviewer -> orchestrator handoff recorded")
        runs = get_verification_runs(smoke["id"])
        check(
            any(v["passed"] and "pytest" in v["command"] for v in runs),
            "smoke mission recorded a passing pytest run",
        )

    state_file = db_path().parent / "selfbuild_state.json"
    check(state_file.exists(), "data/selfbuild_state.json exists")
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        project_state = state.get("projects", {}).get(str(ROOT), {})
        current = next_mission(ROOT)
        state_mission_id = project_state.get("last_completed_mission_id")
        state_mission = next(
            (m for m in missions if m["id"] == state_mission_id),
            None,
        )
        check(
            state_mission is not None,
            "autonomous state points at an existing mission",
        )
        if state_mission:
            check(
                state_mission.get("status") == "completed",
                "autonomous state mission is completed",
            )
            check(
                state_mission.get("title") == current.get("title"),
                "autonomous state matches the current roadmap title",
            )
        check(
            project_state.get("last_completed_fingerprint")
            == roadmap_fingerprint(current),
            "autonomous state fingerprint matches the current roadmap",
        )

    print("\n=== Recovery / resume evidence ===")
    resumed = next(
        (
            m
            for m in missions
            if m.get("status") == "completed"
            and int(m.get("resume_count") or 0) > 0
            and m.get("review_verdict") == "APPROVE"
        ),
        None,
    )
    check(resumed is not None, "completed mission with resume_count > 0 exists")
    if resumed:
        print(f"Resume evidence: mission #{resumed['id']} ({resumed['title']})")
        tasks = get_tasks(resumed["id"])
        check(
            bool(tasks) and all(t["status"] == "completed" for t in tasks),
            "resumed mission has all tasks completed",
        )
        summaries = [h["summary"] for h in get_handoffs(resumed["id"])]
        check(
            any("recovered from persistence" in s for s in summaries),
            "resume handoff records developer-stage recovery",
        )
        runs = get_verification_runs(resumed["id"])
        check(
            any(v["passed"] and "pytest" in v["command"] for v in runs),
            "resumed mission recorded a passing pytest run",
        )

    print("\n=== Lock hygiene ===")
    for name in ("mission.lock", "selfbuild.lock"):
        lock = db_path().parent / name
        check(not lock.exists(), f"{name} is not left behind")
    all_missions = list_missions()
    check(
        not any(m.get("status") == "running" for m in all_missions),
        "no mission is stuck in running state",
    )
    legacy = [
        m
        for m in all_missions
        if m.get("project_id") is None and m.get("title") == "Self Build Test"
    ]
    print(f"Legacy unassigned test missions: {len(legacy)} (ignored by project-scoped runs)")

    print("\n=== Test suite ===")
    max_before = max((m["id"] for m in all_missions), default=0)
    run_tests()
    max_after = max((m["id"] for m in list_missions()), default=0)
    check(max_after == max_before, "full test suite does not create mission rows")

    print("\n=== RESULT ===")
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed.")
        return 1
    print("All handoff, state, recovery, and test checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

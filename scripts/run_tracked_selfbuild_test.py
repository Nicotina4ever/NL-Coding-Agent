"""Launch one real, tracked Self-Build Mode cycle through the autonomous CLI."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nl_coding_agent.persistence.missions import list_missions
from nl_coding_agent.projects.registry import open_project


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=str(ROOT))
    parser.add_argument("--max-missions", type=int, default=1)
    parser.add_argument("--resume", type=int, default=None)
    parser.add_argument(
        "--developer-model",
        default=os.environ.get("NL_SELFBUILD_DEVELOPER_MODEL", ""),
    )
    parser.add_argument(
        "--reviewer-model",
        default=os.environ.get("NL_SELFBUILD_REVIEWER_MODEL", "ollama/qwen3.5:9b"),
    )
    parser.add_argument("--timeout", type=int, default=1800)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.project).resolve()
    record = open_project(project)
    project_id = int(record["id"])
    before = {m["id"] for m in list_missions(project_id)}

    command = [
        sys.executable,
        "nl_agent.py",
        "selfbuild",
        "--autonomous",
        "--project",
        str(project),
        "--max-missions",
        str(args.max_missions),
        "--reviewer-model",
        args.reviewer_model,
    ]
    if args.developer_model:
        command.extend(["--dev-model", args.developer_model])
    if args.resume is not None:
        command.extend(["--resume", str(args.resume)])

    print(f"Launching: {' '.join(command)}", flush=True)
    result = subprocess.run(command, cwd=ROOT, timeout=args.timeout, check=False)

    missions = list_missions(project_id)
    new_missions = [m for m in missions if m["id"] not in before]
    latest = new_missions[0] if new_missions else (missions[0] if missions else None)

    print("\n=== TRACKED SELF-BUILD RESULT ===")
    print(f"CLI exit code: {result.returncode}")
    if latest:
        print(f"Mission: #{latest['id']} [{latest['status']}] {latest['title']}")
        print(f"Verdict: {latest.get('review_verdict')}")
        print(f"Diff: {latest.get('diff_stat')}")
        print(f"Changed paths: {latest.get('changed_paths')}")
        print(f"Resume count: {latest.get('resume_count')}")
    else:
        print("No mission record found for this project.")

    if result.returncode != 0:
        return result.returncode
    if latest and latest.get("status") != "completed":
        return 1
    if latest and latest.get("review_verdict") not in (None, "APPROVE"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

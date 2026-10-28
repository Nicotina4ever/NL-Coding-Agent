r"""Reconcile the NL Coding Agent project registry after a repository rename.

Dry-run is the default. Nothing is written unless --apply is passed. On --apply the
SQLite database and selfbuild_state.json are backed up first, then:

* the original project row id keeps its missions; only its root/name/metadata change;
* a duplicate new-root project row (if one appeared before this migration) is merged
  into the original id and deleted, so a single project identity remains;
* the selfbuild_state.json project key is renamed to the canonical resolved root,
  preserving last_completed_mission_id, fingerprint and audit notes.

Run from anywhere; paths are resolved from this file's repository root.

Examples:
  python\python.exe scripts\migrate_project_root.py
  python\python.exe scripts\migrate_project_root.py --apply
  python\python.exe scripts\migrate_project_root.py --old-root "K:\AI\Coding Agent" --apply --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core.relocation import (  # noqa: E402
    RelocationError,
    apply_migration,
    canonical,
    detect_old_root,
    format_plan,
    verify_identity,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate NL Coding Agent project identity and self-build state to a new repository root."
    )
    parser.add_argument("--old-root", help="Previous repository root (auto-detected from SQLite when omitted)")
    parser.add_argument("--new-root", help="Canonical repository root (defaults to this checkout)")
    parser.add_argument("--data-dir", help="Directory containing the SQLite DB and selfbuild_state.json (default: <repo>/data)")
    parser.add_argument("--db", help="Explicit SQLite path (default: <data-dir>/nl_coding_agent.sqlite3)")
    parser.add_argument("--state", help="Explicit selfbuild_state.json path (default: <data-dir>/selfbuild_state.json)")
    parser.add_argument("--name", help="Registered project name (default: new folder name)")
    parser.add_argument("--apply", action="store_true", help="Apply the migration (default is a read-only dry run)")
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    parser.add_argument("--force", action="store_true", help="Proceed even if a selfbuild.lock file exists")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    new_root = canonical(args.new_root or REPO_ROOT)
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else (REPO_ROOT / "data")
    db_path = Path(args.db).expanduser().resolve() if args.db else data_dir / "nl_coding_agent.sqlite3"
    state_path = Path(args.state).expanduser().resolve() if args.state else data_dir / "selfbuild_state.json"

    lock_path = data_dir / "selfbuild.lock"
    if lock_path.exists() and args.apply and not args.force:
        print(
            "ERROR: " + str(lock_path) + " exists; a self-build run may be active. "
            "Stop it or pass --force.",
            file=sys.stderr,
        )
        return 2

    try:
        old_root = args.old_root or detect_old_root(db_path, new_root)
        report = apply_migration(
            db_path,
            state_path,
            old_root,
            new_root,
            new_name=args.name,
            data_dir=data_dir,
            dry_run=not args.apply,
        )
    except RelocationError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_plan(report))
        if report.get("applied"):
            print("")
            print("APPLIED")
            print("  Backup: " + str(report.get("backup_dir")))
            print("  DB    : " + json.dumps(report.get("db_result"), ensure_ascii=False))
            print("  State : " + json.dumps(report.get("state_result"), ensure_ascii=False))
        else:
            print("")
            print("DRY RUN: no files were changed. Re-run with --apply to migrate.")

    verification = report.get("verification")
    verify_now = bool(report.get("applied") or not report["requires_apply"])
    if verification is None and verify_now:
        try:
            verification = verify_identity(db_path, state_path, new_root)
        except RelocationError as exc:
            print("VERIFICATION ERROR: " + str(exc), file=sys.stderr)
            return 3
    if not args.json:
        print("")
        if verification is None:
            print("Post-migration verification: SKIPPED (dry run; run with --apply to migrate)")
        else:
            print("Post-migration verification: " + ("OK" if verification.get("ok") else "FAILED"))
            if verification.get("project"):
                print("  Project id: " + str(verification["project"]["id"])
                      + " root: " + str(verification["project"]["root"]))
            print("  Missions total: " + str(verification.get("missions_total"))
                  + " owned by project: " + str(verification.get("owned_missions")))
            print("  State keys: " + json.dumps(verification.get("state_keys"), ensure_ascii=False))
            for error in verification.get("errors", []):
                print("  ERROR: " + str(error))
    if verify_now and verification is not None and not verification.get("ok"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

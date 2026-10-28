r"""Read-only stage-3 supervisor diagnostic gate (C3e).

Checks durable supervisor state without modifying it: schema tables present, no
active lease, no unreconciled promotion journal, queue/backlog consistency, no
running supervisor process, default mode off, and a valid indexed backlog.

Usage:
  python\python.exe scripts\verify_supervisor.py [--project .] [--json]

Exit codes: 0 = all checks pass, 1 = at least one check failed.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

SUPERVISOR_TABLES = (
    "supervisor_leases", "supervisor_runs", "mission_queue", "backlog_items",
    "mission_evidence", "approvals", "supervisor_commands", "machine_leases",
)
ACTIVE_RUN_STATUSES = {
    "STARTING", "RUNNING", "PAUSED", "WAITING_FOR_RESOURCES",
    "WAITING_FOR_APPROVAL", "STOPPING", "RECOVERING",
}
ACTIVE_QUEUE_STATES = {"CLAIMED", "RUNNING", "VERIFYING", "REVIEWING"}
TERMINAL_QUEUE_STATES = {"VERIFIED", "BLOCKED", "CANCELLED"}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pid_alive(pid: int) -> bool:
    if int(pid) <= 0:
        return False
    try:
        import psutil

        return bool(psutil.pid_exists(int(pid)))
    except Exception:
        pass
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _readonly_connection(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.is_file():
        return None
    uri = "file:" + db_path.as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row["name"]) for row in rows}


def _setting(conn: sqlite3.Connection, key: str) -> dict:
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return {}
    try:
        parsed = json.loads(str(row["value"]))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def collect_report(project_root: Path) -> dict:
    from nl_coding_agent.persistence.database import db_path

    data_db = Path(db_path())
    checks: list[dict] = []
    warnings: list[str] = []

    def record(name: str, ok: bool, detail: str, *, warning: bool = False) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail,
                       "level": "warning" if warning else "error"})
        if not ok and warning:
            warnings.append(name + ": " + detail)

    conn = _readonly_connection(data_db)
    try:
        record("database", conn is not None,
               "found " + str(data_db) if conn is not None else "missing " + str(data_db))
        tables: set[str] = _table_names(conn) if conn is not None else set()
        missing_tables = [name for name in SUPERVISOR_TABLES if name not in tables]
        record("schema", not missing_tables,
               "all supervisor tables present" if not missing_tables
               else "missing tables: " + ", ".join(missing_tables))

        if conn is not None and "supervisor_leases" in tables:
            lease_rows = conn.execute("SELECT * FROM supervisor_leases").fetchall()
            now = _now_iso()
            active = [row for row in lease_rows if str(row["expires_at"]) >= now]
            if active:
                row = active[0]
                record("no-active-lease", False,
                       "lease held by " + str(row["owner_id"]) + " pid "
                       + str(row["owner_pid"]) + " until " + str(row["expires_at"]))
            else:
                record("no-active-lease", True,
                       "no unexpired lease" + (
                           " (" + str(len(lease_rows)) + " expired row(s))"
                           if lease_rows else ""))
        else:
            record("no-active-lease", False, "lease table unavailable")

        if conn is not None and "supervisor_runs" in tables:
            rows = conn.execute(
                "SELECT id, status, owner_pid FROM supervisor_runs ORDER BY id DESC"
            ).fetchall()
            running = [
                row for row in rows
                if str(row["status"]) in ACTIVE_RUN_STATUSES
                and _pid_alive(int(row["owner_pid"] or 0))
            ]
            if running:
                record("no-running-supervisor", False,
                       "active run #" + str(running[0]["id"]) + " status "
                       + str(running[0]["status"]) + " pid "
                       + str(running[0]["owner_pid"]))
            else:
                record("no-running-supervisor", True, "no live supervisor run row")
        else:
            record("no-running-supervisor", False, "run table unavailable")

        staging = project_root / "data" / "staging"
        journals = sorted(
            str(path.relative_to(project_root))
            for path in staging.glob("*/promotion-journal.json")
        ) if staging.is_dir() else []
        record("no-unreconciled-journal", not journals,
               "no promotion journal in data/staging" if not journals
               else "unreconciled promotion journal(s): " + ", ".join(journals))

        if conn is not None and "mission_queue" in tables and "backlog_items" in tables:
            queue = [dict(row) for row in conn.execute("SELECT * FROM mission_queue")]
            backlog = {str(row["requirement_id"]): dict(row)
                       for row in conn.execute("SELECT * FROM backlog_items")}
            problems: list[str] = []
            for item in queue:
                requirement_id = item.get("requirement_id")
                if requirement_id and requirement_id not in backlog:
                    problems.append("queue #" + str(item["id"]) + " requirement "
                                    + str(requirement_id) + " missing from backlog_items")
                if str(item.get("state")) in TERMINAL_QUEUE_STATES and not item.get("finished_at"):
                    problems.append("terminal queue #" + str(item["id"]) + " has no finished_at")
            for requirement_id, row in backlog.items():
                if str(row.get("supervisor_status")) == "IN_FLIGHT":
                    has_active = any(
                        item.get("requirement_id") == requirement_id
                        and str(item.get("state")) in ACTIVE_QUEUE_STATES
                        for item in queue
                    )
                    if not has_active:
                        problems.append("backlog " + requirement_id
                                        + " is IN_FLIGHT with no active queue row")
            record("queue-backlog-consistency", not problems,
                   "consistent" if not problems else "; ".join(problems))
        else:
            record("queue-backlog-consistency", False, "queue/backlog tables unavailable")

        if conn is not None and "app_settings" in tables:
            global_config = _setting(conn, "supervisor.global")
            default_mode = str(global_config.get("mode") or "off")
            record("default-mode-off", default_mode == "off",
                   "supervisor.global mode=" + repr(default_mode))
            project_modes = []
            for row in conn.execute(
                "SELECT key FROM app_settings WHERE key LIKE 'supervisor.project.%'"
            ):
                key = str(row["key"])
                if str(_setting(conn, key).get("mode") or "off") != "off":
                    project_modes.append(key)
            if project_modes:
                warnings.append(
                    "project override(s) enable autonomy: " + ", ".join(project_modes)
                )
        else:
            record("default-mode-off", False, "app_settings unavailable")
    finally:
        if conn is not None:
            conn.close()

    try:
        from nl_coding_agent.core import backlog

        index = backlog.load_project_index(project_root)
        stage = backlog.current_program_stage(index)
        record("index-valid", True,
               str(len(index.requirements)) + " requirements, schema "
               + str(index.schema_version) + ", current stage "
               + (str(stage.stage) if stage is not None else "none"))
        warnings.extend(index.warnings)
    except Exception as exc:
        record("index-valid", False, "backlog index invalid: " + str(exc))

    failed = [check for check in checks if not check["ok"] and check["level"] == "error"]
    return {
        "ok": not failed,
        "project": str(project_root),
        "database": str(data_db),
        "checks": checks,
        "warnings": warnings,
        "failed": [check["name"] for check in failed],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only supervisor diagnostic gate")
    parser.add_argument("--project", default=str(REPO_ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = collect_report(Path(args.project).resolve())
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        print("Supervisor diagnostic gate: " + ("PASS" if report["ok"] else "FAIL"))
        for check in report["checks"]:
            print("  [" + ("OK  " if check["ok"] else "FAIL") + "] "
                  + check["name"] + ": " + check["detail"])
        for warning in report["warnings"]:
            print("  WARNING: " + warning)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

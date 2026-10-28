r"""Dry-run relocation verification for NL Coding Agent.

READ-ONLY: this script never starts a mission, never runs Self-Build Mode and never
writes to the database or selfbuild_state.json. It is the gate that must pass before
any autonomous self-build operation is permitted after a repository relocation.

It verifies, from the new canonical repository root:

1. Git repository identity and working-tree status.
2. Embedded Python runtime and CrewAI import.
3. Ollama reachability and installed model count.
4. SQLite project identity: one project row at the canonical root, mission history
   preserved and associated with the original project id, no orphan missions.
5. selfbuild_state.json: canonical key, preserved fingerprint/mission id/audit notes.
6. No old absolute workspace root in the project registry, state keys, operational
   documentation, launchers or runtime code.
7. No leftover self-build/mission locks, no mission stuck in 'running', no live
   NL Coding Agent process.
8. CLI entry point and GUI modules still import; optional offscreen GUI smoke test.
9. The dry run itself did not modify the database or state file.

Usage:
  python\python.exe scripts\verify_relocation.py
  python\python.exe scripts\verify_relocation.py --json --report build/relocation/verify_relocation_report.json
  python\python.exe scripts\verify_relocation.py --full-gui
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core.relocation import (  # noqa: E402
    RelocationError,
    canonical,
    norm,
    verify_identity,
)

OLD_ROOT = r"K:\AI\Coding Agent"
OLD_ROOT_PATTERNS = (
    re.compile(r"K:[\\/]+AI[\\/]+Coding\s+Agent", re.IGNORECASE),
    re.compile(r"K%3A%5CAI%5CCoding%20Agent", re.IGNORECASE),
)
HISTORICAL_MISSION_IDS = (3, 7, 16, 24, 30, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45)
MIN_MISSIONS_TOTAL = 45
MIN_OWNED_MISSIONS = 15
MIN_COMPLETED_MISSIONS = 13

OPERATIONAL_GLOBS = (
    "AGENTS.md",
    "README*.txt",
    "START_HERE_ANTIGRAVITY.md",
    "PASTE_THIS_IN_ANTIGRAVITY.txt",
    ".agents/**/*.md",
    "docs/0[2-9]_*.md",
    "docs/CURRENT_STATE.md",
    "docs/PORTABLE_BUILD.md",
    "docs/WORKSPACE_MIGRATION.md",
    "docs/NEXT_SELF_BUILD_MISSION.md",
)
HISTORICAL_DOCS = {
    "docs/COMPLETED_MISSIONS.md",
    "docs/09_ANTIGRAVITY_EXECUTION_MISSION.md",
}

CODE_GLOBS = (
    "nl_coding_agent/**/*.py",
)
HARDCODED_DRIVE_PATTERN = re.compile(r"[A-Za-z]:\\\\|/AI/")

CHECKS: list[dict] = []


def record(name: str, ok: bool, detail: str = "", warning: bool = False) -> None:
    status = "PASS" if ok and not warning else ("WARN" if warning else "FAIL")
    CHECKS.append({"check": name, "status": status, "detail": detail})


def run_command(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        return -1, str(exc)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_paths_for_old_root(paths: list[Path], repo_root: Path, old_root: str = OLD_ROOT) -> list[dict]:
    """Return [{path, line, match}] for old-root (and legacy absolute) references."""
    hits: list[dict] = []
    old_norm = norm(old_root)
    for path in paths:
        try:
            text = read_text(path)
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in OLD_ROOT_PATTERNS):
                hits.append({"path": str(path.relative_to(repo_root)), "line": number,
                             "match": line.strip()[:200]})
            elif old_norm and old_norm in norm(line):
                hits.append({"path": str(path.relative_to(repo_root)), "line": number,
                             "match": line.strip()[:200]})
    return hits


def operational_file_paths(repo_root: Path) -> list[Path]:
    found: set[Path] = set()
    for pattern in OPERATIONAL_GLOBS:
        for path in repo_root.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root).as_posix()
            if rel in HISTORICAL_DOCS:
                continue
            found.add(path)
    return sorted(found)


def launcher_paths(repo_root: Path) -> list[Path]:
    paths = list(repo_root.glob("*.bat")) + list(repo_root.glob("*.ps1"))
    paths += list((repo_root / "scripts").glob("*.ps1"))
    return sorted({p for p in paths if p.is_file()})


def code_paths(repo_root: Path) -> list[Path]:
    found: set[Path] = set()
    for pattern in CODE_GLOBS:
        for path in repo_root.glob(pattern):
            if path.is_file():
                found.add(path)
    return sorted(found)


def read_only_query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        return [tuple(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def check_git(repo_root: Path) -> None:
    rc, out = run_command(["git", "rev-parse", "--show-toplevel"], repo_root)
    top = out.strip().splitlines()[-1] if out.strip() else ""
    record(
        "git.repository",
        rc == 0 and norm(top) == norm(repo_root),
        "toplevel=" + repr(top),
    )
    rc, out = run_command(["git", "status", "--porcelain"], repo_root)
    count = len([line for line in out.splitlines() if line.strip()])
    record(
        "git.working_tree",
        rc == 0,
        str(count) + " uncommitted path(s)" + ("" if count == 0 else " (checkpoint/commit recommended)"),
        warning=rc == 0 and count > 0,
    )
    rc, out = run_command(["git", "log", "-1", "--format=%h %s"], repo_root)
    record("git.history", rc == 0 and bool(out.strip()), out.strip()[:200])


def check_runtime(repo_root: Path) -> None:
    exe = Path(sys.executable).resolve()
    python_dir = (repo_root / "python").resolve()
    try:
        exe.relative_to(python_dir)
        under = True
    except ValueError:
        under = False
    record(
        "python.embedded_runtime",
        under,
        str(exe) + " / " + sys.version.split()[0],
    )
    try:
        import crewai  # noqa: F401

        version = getattr(crewai, "__version__", "unknown")
        record("python.crewai_import", True, "crewai " + str(version))
    except Exception as exc:  # noqa: BLE001
        record("python.crewai_import", False, str(exc))


def check_ollama(repo_root: Path) -> None:
    url = "http://127.0.0.1:11434/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - localhost only
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("models") or []
        record("ollama.reachable", True, str(len(models)) + " model(s) listed via " + url)
    except Exception as exc:  # noqa: BLE001
        record("ollama.reachable", False, str(exc))


def check_database(repo_root: Path) -> None:
    data_dir = repo_root / "data"
    db = data_dir / "nl_coding_agent.sqlite3"
    state = data_dir / "selfbuild_state.json"
    if not db.is_file():
        record("sqlite.present", False, "missing " + str(db))
        return
    record("sqlite.present", True, str(db))
    try:
        verification = verify_identity(db, state, repo_root)
    except RelocationError as exc:
        record("sqlite.identity", False, str(exc))
        return
    record("sqlite.identity", verification.get("ok", False),
           json.dumps({k: verification.get(k) for k in (
               "owned_missions", "missions_total", "orphan_missions", "integrity")},
               ensure_ascii=False))
    project = verification.get("project") or {}
    record("sqlite.canonical_root", bool(project.get("root")) and norm(project["root"]) == norm(repo_root),
           "project_id=" + str(project.get("id")) + " root=" + repr(project.get("root")))

    projects = read_only_query(db, "SELECT id, name, root FROM projects ORDER BY id")
    record("sqlite.single_project_identity", len(projects) == 1,
           "projects=" + repr(projects))
    totals = read_only_query(db, "SELECT COUNT(*) FROM missions")[0][0]
    owned = read_only_query(db, "SELECT COUNT(*) FROM missions WHERE project_id = ?",
                            (project.get("id"),))[0][0] if project.get("id") is not None else 0
    completed = read_only_query(db, "SELECT COUNT(*) FROM missions WHERE status='completed'")[0][0]
    record("sqlite.mission_history_preserved",
           totals >= MIN_MISSIONS_TOTAL and owned >= MIN_OWNED_MISSIONS and completed >= MIN_COMPLETED_MISSIONS,
           "total=" + str(totals) + " owned=" + str(owned) + " completed=" + str(completed)
           + " (floors: " + str(MIN_MISSIONS_TOTAL) + "/" + str(MIN_OWNED_MISSIONS) + "/"
           + str(MIN_COMPLETED_MISSIONS) + ")")
    placed = {}
    if project.get("id") is not None:
        for mission_id in HISTORICAL_MISSION_IDS:
            rows = read_only_query(db, "SELECT project_id FROM missions WHERE id=?", (mission_id,))
            placed[mission_id] = rows[0][0] if rows else None
    missing = [mid for mid, pid in placed.items() if pid != project.get("id")]
    record("sqlite.historical_missions_associated", not missing,
           "mission ids " + repr(list(HISTORICAL_MISSION_IDS)) + " owner mismatch: " + repr(missing))
    running = read_only_query(db, "SELECT COUNT(*) FROM missions WHERE status='running'")[0][0]
    record("sqlite.no_running_mission", int(running) == 0, "running=" + str(running))


def check_state(repo_root: Path) -> None:
    state_file = repo_root / "data" / "selfbuild_state.json"
    if not state_file.is_file():
        record("state.present", False, "missing " + str(state_file))
        return
    try:
        state = json.loads(read_text(state_file))
    except Exception as exc:  # noqa: BLE001
        record("state.json_valid", False, str(exc))
        return
    record("state.json_valid", True, str(state_file))
    projects = state.get("projects") or {}
    keys = list(projects) if isinstance(projects, dict) else []
    expected = canonical(repo_root)
    record("state.canonical_key", len(keys) == 1 and keys[0] == expected,
           "keys=" + repr(keys) + " expected=" + repr(expected))
    entry = projects.get(expected) or {}
    mission_id = entry.get("last_completed_mission_id")
    fingerprint = entry.get("last_completed_fingerprint")
    notes = sorted(k for k in entry if str(k).startswith("audit_note_"))
    record("state.fingerprint_and_mission_preserved",
           isinstance(mission_id, int) and isinstance(fingerprint, str) and len(fingerprint) == 64,
           "last_completed_mission_id=" + repr(mission_id)
           + " fingerprint=" + (str(fingerprint)[:12] + "..." if fingerprint else repr(fingerprint))
           + " audit_notes=" + repr(notes))
    db = repo_root / "data" / "nl_coding_agent.sqlite3"
    status = None
    if db.is_file() and isinstance(mission_id, int):
        rows = read_only_query(db, "SELECT status FROM missions WHERE id=?", (mission_id,))
        status = rows[0][0] if rows else None
    record("state.mission_exists", status is not None,
           "mission #" + repr(mission_id) + " status=" + repr(status))
    record("state.preserved_relocation_note", "relocated_from" in entry or not keys == [expected],
           "relocated_from=" + repr(entry.get("relocated_from")), warning=False)


def check_old_path_references(repo_root: Path) -> None:
    db = repo_root / "data" / "nl_coding_agent.sqlite3"
    if db.is_file():
        rows = read_only_query(db, "SELECT id, root FROM projects")
        stale = [row for row in rows if norm(row[1]) == norm(OLD_ROOT)]
        record("paths.database_no_old_root", not stale, "stale project rows=" + repr(stale))
    state_file = repo_root / "data" / "selfbuild_state.json"
    if state_file.is_file():
        try:
            projects = (json.loads(read_text(state_file)).get("projects") or {})
        except Exception:  # noqa: BLE001
            projects = {}
        stale_keys = [key for key in projects if norm(key) == norm(OLD_ROOT)]
        record("paths.state_no_old_key", not stale_keys, "stale state keys=" + repr(stale_keys))
    operational = operational_file_paths(repo_root)
    hits = scan_paths_for_old_root(operational, repo_root)
    record("paths.operational_docs_clean", not hits,
           "checked " + str(len(operational)) + " file(s); hits="
           + json.dumps(hits[:10], ensure_ascii=False))
    launchers = launcher_paths(repo_root)
    launcher_hits = scan_paths_for_old_root(launchers, repo_root)
    record("paths.launchers_clean", not launcher_hits,
           "checked " + str(len(launchers)) + " launcher(s); hits="
           + json.dumps(launcher_hits[:10], ensure_ascii=False))
    code = code_paths(repo_root)
    hardcoded = []
    for path in code:
        try:
            text = read_text(path)
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if HARDCODED_DRIVE_PATTERN.search(line):
                hardcoded.append({"path": str(path.relative_to(repo_root)), "line": number,
                                  "match": line.strip()[:160]})
    record("paths.runtime_code_dynamic", not hardcoded,
           "absolute windows path literals in runtime code=" + json.dumps(hardcoded[:10], ensure_ascii=False))


def check_hygiene(repo_root: Path) -> None:
    data_dir = repo_root / "data"
    for name in ("selfbuild.lock", "mission.lock"):
        record("hygiene." + name, not (data_dir / name).exists(), str(data_dir / name))
    try:
        import psutil  # noqa: F401

        live = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or [])
            except Exception:  # noqa: BLE001
                continue
            if "nl_agent.py" in cmdline and "selfbuild" in cmdline:
                live.append({"pid": proc.info.get("pid"), "cmdline": cmdline[:300]})
        record("hygiene.no_live_selfbuild_process", not live, json.dumps(live, ensure_ascii=False))
    except ImportError:
        record("hygiene.no_live_selfbuild_process", True, "psutil unavailable; process check skipped", warning=True)


def check_entry_points(repo_root: Path, full_gui: bool) -> None:
    rc, out = run_command([sys.executable, "nl_agent.py", "selfbuild", "--help"], repo_root, timeout=120)
    record("entry.cli_selfbuild_help", rc == 0 and "--autonomous" in out, "exit=" + str(rc))
    try:
        import PySide6  # noqa: F401
        from nl_coding_agent.gui.main_window import MainWindow  # noqa: F401

        record("entry.gui_import", True, "PySide6 + MainWindow importable")
    except Exception as exc:  # noqa: BLE001
        record("entry.gui_import", False, str(exc))
        return
    if full_gui:
        rc, out = run_command([sys.executable, "-m", "pytest", "tests/test_gui_smoke.py", "-q"],
                              repo_root, timeout=300)
        record("entry.gui_offscreen_smoke", rc == 0,
               (out.strip().splitlines()[-1] if out.strip() else "exit=" + str(rc))[:300])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only relocation verification (dry run).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--report", help="Write the JSON report to this path")
    parser.add_argument("--full-gui", action="store_true", help="Also run the offscreen GUI smoke test")
    parser.add_argument("--skip-ollama", action="store_true", help="Skip the local Ollama reachability check")
    return _main(parser.parse_args(argv))


def _main(args: argparse.Namespace) -> int:
    repo_root = REPO_ROOT
    db = repo_root / "data" / "nl_coding_agent.sqlite3"
    state = repo_root / "data" / "selfbuild_state.json"
    before = {"db": file_sha256(db), "state": file_sha256(state)}

    check_git(repo_root)
    check_runtime(repo_root)
    if not args.skip_ollama:
        check_ollama(repo_root)
    check_database(repo_root)
    check_state(repo_root)
    check_old_path_references(repo_root)
    check_hygiene(repo_root)
    check_entry_points(repo_root, args.full_gui)

    after = {"db": file_sha256(db), "state": file_sha256(state)}
    record("dryrun.read_only", before == after,
           "database/state hashes unchanged; before=" + json.dumps(before) + " after=" + json.dumps(after))

    failures = [item for item in CHECKS if item["status"] == "FAIL"]
    warnings = [item for item in CHECKS if item["status"] == "WARN"]
    report = {
        "ok": not failures,
        "repo_root": str(repo_root),
        "old_root": OLD_ROOT,
        "checked_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "checks": CHECKS,
        "counts": {
            "passed": len([c for c in CHECKS if c["status"] == "PASS"]),
            "failed": len(failures),
            "warnings": len(warnings),
        },
    }
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = repo_root / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=== NL Coding Agent relocation verification (dry run, read-only) ===")
        print("Repo root: " + str(repo_root))
        print("Old root : " + OLD_ROOT)
        print("")
        for item in CHECKS:
            print("[" + item["status"] + "] " + item["check"] + " :: " + item["detail"])
        print("")
        print("Summary: " + str(report["counts"]["passed"]) + " passed, "
              + str(report["counts"]["failed"]) + " failed, "
              + str(report["counts"]["warnings"]) + " warning(s)")
        if failures:
            print("RESULT: FAILED - do not permit self-build until fixed.")
        else:
            print("RESULT: PASSED - relocation reconciled; self-build may be permitted.")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

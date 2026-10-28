"""Project-root relocation reconciliation for NL Coding Agent.

The repository may be renamed on disk at any time. Two durable stores hard-code
the workspace root as an identity key:

* the 'projects.root' column in SQLite (UNIQUE) - opening the new path would
  otherwise create a *second* project row and orphan every mission that
  references the original project_id;
* 'selfbuild_state.json' - keyed by the resolved project root, holding the
  roadmap fingerprint, last completed mission id and recovery notes.

This module plans and applies those two migrations in a conservative,
idempotent way:

* the database is backed up with the SQLite backup API and the state file is
  copied before anything is changed;
* the original project row id is preserved, so missions.project_id history is
  kept and no duplicate project identity is created;
* historical evidence rows (events, verification runs, stdout, handoffs) are
  never rewritten - only the registry identity and the state key change;
* a second run detects the migrated state and does nothing.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class RelocationError(RuntimeError):
    """Raised when a relocation cannot be planned or applied safely."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def canonical(path: str | Path) -> str:
    """Absolute, normalized path string (does not require the target to exist)."""
    return str(Path(path).expanduser().resolve())


def norm(path: str | Path) -> str:
    """Comparison key: canonical form, case-normalized on Windows."""
    return os.path.normcase(canonical(path))


def _sqlite_uri(path: str | Path, readonly: bool = False) -> str:
    uri = Path(path).resolve().as_uri()
    return uri + ("?mode=ro" if readonly else "")


def _connect(db_path: str | Path, readonly: bool = False) -> sqlite3.Connection:
    p = Path(db_path)
    if not p.is_file():
        raise RelocationError("SQLite database not found: " + str(p))
    conn = sqlite3.connect(_sqlite_uri(p, readonly=readonly), uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _mapping(value: Any) -> dict:
    """Decode a JSON object column without ever raising on corrupt history."""
    if not value:
        return {}
    try:
        data = json.loads(value) if isinstance(value, (str, bytes)) else value
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _project_rows(conn: sqlite3.Connection) -> list[dict]:
    if not _table_exists(conn, "projects"):
        raise RelocationError("The database has no projects table")
    return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY id")]


def _mission_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not _table_exists(conn, "missions"):
        return counts
    for row in conn.execute(
        "SELECT project_id, COUNT(*) AS c FROM missions GROUP BY project_id"
    ):
        counts[str(row["project_id"])] = int(row["c"])
    return counts


def _facts_count(conn: sqlite3.Connection, project_id: int) -> int:
    if not _table_exists(conn, "project_facts"):
        return 0
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM project_facts WHERE project_id=?", (project_id,)
    ).fetchone()
    return int(row["c"]) if row else 0


def detect_old_root(db_path: str | Path, new_root: str | Path) -> str:
    """Return the single registered root that is not the new canonical root."""
    new_key = norm(new_root)
    conn = _connect(db_path, readonly=True)
    try:
        candidates = [r["root"] for r in _project_rows(conn) if norm(r["root"]) != new_key]
    finally:
        conn.close()
    if len(candidates) == 1:
        return str(candidates[0])
    if not candidates:
        raise RelocationError(
            "No un-migrated project root found in the database; nothing to relocate."
        )
    raise RelocationError(
        "Multiple project roots could be relocated ("
        + ", ".join(sorted(candidates))
        + "); pass --old-root explicitly."
    )


def plan_migration(
    db_path: str | Path,
    state_path: str | Path,
    old_root: str | Path,
    new_root: str | Path,
    new_name: str | None = None,
) -> dict:
    """Read-only plan. Never writes to the database or the state file."""
    db = Path(db_path)
    state_file = Path(state_path)
    old = canonical(old_root)
    new = canonical(new_root)
    name = (new_name or Path(new).name).strip() or Path(new).name
    report: dict[str, Any] = {
        "old_root": old,
        "new_root": new,
        "new_name": name,
        "db_path": str(db),
        "state_path": str(state_file),
        "db": {"exists": db.is_file(), "actions": [], "project": None, "duplicate": None,
               "mission_counts": {}, "warnings": []},
        "state": {"exists": state_file.is_file(), "actions": [], "keys": [],
                  "entry": None, "warnings": []},
        "warnings": [],
        "requires_apply": False,
        "already_migrated": False,
    }
    if not db.is_file():
        raise RelocationError("SQLite database not found: " + str(db))
    if not state_file.is_file():
        report["state"]["warnings"].append("State file not found: " + str(state_file))

    conn = _connect(db, readonly=True)
    try:
        rows = _project_rows(conn)
        old_key, new_key = norm(old), norm(new)
        old_row = next((r for r in rows if norm(r["root"]) == old_key), None)
        new_row = next(
            (r for r in rows
             if norm(r["root"]) == new_key and (old_row is None or r["id"] != old_row["id"])),
            None,
        )
        counts = _mission_counts(conn)
        report["db"]["mission_counts"] = counts
        report["db"]["projects_total"] = len(rows)

        if old_row is not None and new_row is not None:
            survivor, loser = old_row, new_row
            report["db"]["project"] = {
                "id": survivor["id"], "name": survivor["name"], "root": survivor["root"],
                "missions": counts.get(str(survivor["id"]), 0),
                "facts": _facts_count(conn, survivor["id"]),
            }
            report["db"]["duplicate"] = {
                "id": loser["id"], "name": loser["name"], "root": loser["root"],
                "missions": counts.get(str(loser["id"]), 0),
                "facts": _facts_count(conn, loser["id"]),
            }
            report["db"]["actions"].append({
                "type": "merge_duplicate_project",
                "survivor_id": survivor["id"],
                "duplicate_id": loser["id"],
                "description": (
                    "Keep original project id " + str(survivor["id"]) + " ("
                    + str(survivor["root"]) + "), move missions/facts from duplicate id "
                    + str(loser["id"]) + " (" + str(loser["root"]) + "), delete the duplicate "
                    "row, then rename id " + str(survivor["id"]) + " to " + new + "."
                ),
            })
            report["db"]["actions"].append({
                "type": "rename_project_root",
                "project_id": survivor["id"],
                "from": survivor["root"],
                "to": new,
                "name": name,
                "previous_name": survivor["name"],
            })
        elif old_row is not None:
            report["db"]["project"] = {
                "id": old_row["id"], "name": old_row["name"], "root": old_row["root"],
                "missions": counts.get(str(old_row["id"]), 0),
                "facts": _facts_count(conn, old_row["id"]),
            }
            report["db"]["actions"].append({
                "type": "rename_project_root",
                "project_id": old_row["id"],
                "from": old_row["root"],
                "to": new,
                "name": name,
                "previous_name": old_row["name"],
                "description": (
                    "Keep project id " + str(old_row["id"]) + " and its "
                    + str(counts.get(str(old_row["id"]), 0)) + " mission(s); rename root "
                    + repr(old_row["root"]) + " -> " + repr(new) + " and name "
                    + repr(old_row["name"]) + " -> " + repr(name) + "."
                ),
            })
        elif new_row is not None:
            report["db"]["project"] = {
                "id": new_row["id"], "name": new_row["name"], "root": new_row["root"],
                "missions": counts.get(str(new_row["id"]), 0),
                "facts": _facts_count(conn, new_row["id"]),
            }
            report["db"]["actions"].append({
                "type": "noop_already_migrated",
                "project_id": new_row["id"],
                "description": "Project id " + str(new_row["id"]) + " already uses "
                               + str(new_row["root"]) + ".",
            })
        else:
            raise RelocationError(
                "No project row matches the old root " + repr(old)
                + " and no row uses the new root " + repr(new) + "."
            )
    finally:
        conn.close()

    # ---- selfbuild_state.json -------------------------------------------------
    projects: dict = {}
    if state_file.is_file():
        state = _load_state(state_file)
        raw_projects = state.get("projects")
        if isinstance(raw_projects, dict):
            projects = raw_projects
        else:
            report["state"]["warnings"].append(
                "State file has no object 'projects'; not migrating it."
            )
    report["state"]["keys"] = sorted(projects.keys())
    old_state_key = next((k for k in projects if norm(k) == norm(old)), None)
    new_state_key = next((k for k in projects if norm(k) == norm(new)), None)

    if old_state_key is not None and new_state_key is not None and old_state_key != new_state_key:
        entry, warnings = _merge_state_entries(projects[old_state_key], projects[new_state_key])
        report["state"]["entry"] = entry
        report["state"]["warnings"].extend(warnings)
        report["state"]["actions"].append({
            "type": "merge_state_keys",
            "keys": [old_state_key, new_state_key],
            "to": new,
            "description": (
                "Merge state entries " + repr(old_state_key) + " and " + repr(new_state_key)
                + " into the canonical key " + repr(new) + ", keeping the furthest mission id "
                "and every audit note."
            ),
        })
    elif old_state_key is not None and old_state_key != new:
        entry = dict(projects[old_state_key]) if isinstance(projects[old_state_key], dict) else {}
        report["state"]["entry"] = entry
        report["state"]["actions"].append({
            "type": "rename_state_key",
            "from": old_state_key,
            "to": new,
            "description": (
                "Rename selfbuild_state project key " + repr(old_state_key) + " to " + repr(new)
                + ", preserving last_completed_mission_id="
                + repr(entry.get("last_completed_mission_id")) + ", fingerprint and audit notes."
            ),
        })
    elif old_state_key is not None and old_state_key == new:
        report["state"]["actions"].append({
            "type": "noop_already_migrated",
            "description": "State key " + repr(new) + " already uses the canonical path.",
        })
    elif new_state_key is not None:
        report["state"]["actions"].append({
            "type": "noop_already_migrated",
            "description": "State key " + repr(new) + " already exists.",
        })
    elif state_file.is_file():
        report["state"]["warnings"].append(
            "No selfbuild_state entry found for " + repr(old)
            + " (existing keys: " + repr(sorted(projects)) + ")."
        )

    report["requires_apply"] = bool(
        any(not a["type"].startswith("noop") for a in report["db"]["actions"])
        or any(not a["type"].startswith("noop") for a in report["state"]["actions"])
    )
    report["already_migrated"] = not report["requires_apply"]
    return report


def _load_state(state_path: Path) -> dict:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:  # corrupt state must block, not be silently reset
        raise RelocationError("Cannot read state file " + str(state_path) + ": " + str(exc)) from exc
    if not isinstance(data, dict):
        raise RelocationError("State file " + str(state_path) + " does not contain a JSON object")
    return data


def _entry_rank(entry: dict) -> tuple[int, str]:
    mission_id = entry.get("last_completed_mission_id")
    try:
        mid = int(mission_id)
    except (TypeError, ValueError):
        mid = -1
    return mid, str(entry.get("updated_at") or "")


def _merge_state_entries(a: Any, b: Any) -> tuple[dict, list[str]]:
    left = dict(a) if isinstance(a, dict) else {}
    right = dict(b) if isinstance(b, dict) else {}
    warnings: list[str] = []
    base, other = (left, right) if _entry_rank(left) >= _entry_rank(right) else (right, left)
    merged = dict(base)
    for key, value in other.items():
        if key not in merged:
            merged[key] = value
        elif merged[key] != value:
            warnings.append(
                "State field " + repr(key) + " differs between duplicate keys; kept "
                + repr(merged[key]) + " (dropped " + repr(value) + ")."
            )
    return merged, warnings


def _backup(db: Path, state_file: Path, data_dir: Path, plan: dict) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = Path(data_dir) / "backups" / ("relocation-" + stamp)
    dest.mkdir(parents=True, exist_ok=False)
    src = sqlite3.connect(str(db))
    dst = sqlite3.connect(str(dest / db.name))
    try:
        with dst:
            src.backup(dst)
        dst.execute("PRAGMA integrity_check")
    finally:
        src.close()
        dst.close()
    if state_file.is_file():
        shutil.copy2(state_file, dest / state_file.name)
    (dest / "migration_plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return dest


def _apply_db(conn: sqlite3.Connection, report: dict, new: str, name: str, when: str) -> dict:
    """Apply the database part inside a caller-provided transaction."""
    rows = _project_rows(conn)
    old_key, new_key = norm(report["old_root"]), norm(new)
    old_row = next((r for r in rows if norm(r["root"]) == old_key), None)
    duplicate = next(
        (r for r in rows
         if norm(r["root"]) == new_key and (old_row is None or r["id"] != old_row["id"])),
        None,
    )
    if old_row is None:
        if duplicate is not None:
            return {"changed": False, "action": "noop_already_migrated",
                    "project_id": duplicate["id"]}
        raise RelocationError("Project row vanished between plan and apply; aborting.")

    survivor = old_row
    has_missions = _table_exists(conn, "missions")
    missions_before = 0
    duplicate_missions = 0
    if has_missions:
        missions_before = int(conn.execute(
            "SELECT COUNT(*) FROM missions WHERE project_id=?", (survivor["id"],)
        ).fetchone()[0])
        if duplicate is not None:
            duplicate_missions = int(conn.execute(
                "SELECT COUNT(*) FROM missions WHERE project_id=?", (duplicate["id"],)
            ).fetchone()[0])

    if duplicate is not None:
        if has_missions:
            conn.execute(
                "UPDATE missions SET project_id=? WHERE project_id=?",
                (survivor["id"], duplicate["id"]),
            )
        if _table_exists(conn, "project_facts"):
            for fact in conn.execute(
                "SELECT key, value, created_at FROM project_facts WHERE project_id=?",
                (duplicate["id"],),
            ).fetchall():
                conn.execute(
                    "INSERT INTO project_facts (project_id, key, value, created_at) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(project_id, key) DO NOTHING",
                    (survivor["id"], fact["key"], fact["value"], fact["created_at"]),
                )
            conn.execute("DELETE FROM project_facts WHERE project_id=?", (duplicate["id"],))
        conn.execute("DELETE FROM projects WHERE id=?", (duplicate["id"],))

    metadata = _mapping(survivor["metadata"])
    metadata.update({
        "relocated_from": survivor["root"],
        "relocated_at": when,
        "previous_name": survivor["name"],
    })
    conn.execute(
        "UPDATE projects SET root=?, name=?, metadata=? WHERE id=?",
        (new, name, json.dumps(metadata, ensure_ascii=False), survivor["id"]),
    )
    if _table_exists(conn, "events"):
        try:
            conn.execute(
                "INSERT INTO events (source, level, message, payload) VALUES (?,?,?,?)",
                (
                    "migration",
                    "info",
                    "Project registry relocated: " + str(survivor["root"]) + " -> " + new
                    + " (project id " + str(survivor["id"]) + ")",
                    json.dumps({
                        "project_id": survivor["id"],
                        "old_root": survivor["root"],
                        "new_root": new,
                        "previous_name": survivor["name"],
                        "new_name": name,
                        "duplicate_project_id": duplicate["id"] if duplicate else None,
                        "timestamp": when,
                    }, ensure_ascii=False),
                ),
            )
        except sqlite3.Error:
            pass

    missions_after = missions_before + duplicate_missions
    if has_missions:
        actual = int(conn.execute(
            "SELECT COUNT(*) FROM missions WHERE project_id=?", (survivor["id"],)
        ).fetchone()[0])
        if actual != missions_after:
            raise RelocationError(
                "Mission ownership count mismatch after merge: expected "
                + str(missions_after) + ", found " + str(actual)
            )
    return {
        "changed": True,
        "action": "merge_and_rename" if duplicate is not None else "rename",
        "project_id": survivor["id"],
        "duplicate_project_id": duplicate["id"] if duplicate else None,
        "old_root": survivor["root"],
        "new_root": new,
        "new_name": name,
        "missions_before": missions_before,
        "missions_after": missions_after,
    }


def _apply_state(state_path: Path, report: dict, new: str, when: str) -> dict:
    state = _load_state(state_path)
    projects = state.setdefault("projects", {})
    if not isinstance(projects, dict):
        raise RelocationError("State file " + str(state_path) + " has a non-object 'projects' value")
    old = report["old_root"]
    old_key = next((k for k in projects if norm(k) == norm(old)), None)
    new_key = next((k for k in projects if norm(k) == norm(new)), None)
    changed = False
    if old_key is not None and new_key is not None and old_key != new_key:
        entry, _ = _merge_state_entries(projects[old_key], projects[new_key])
        entry["relocated_from"] = old_key
        entry["relocated_at"] = when
        projects.pop(old_key, None)
        projects.pop(new_key, None)
        projects[new] = entry
        changed = True
    elif old_key is not None and old_key != new:
        raw_entry = projects.pop(old_key)
        entry = dict(raw_entry) if isinstance(raw_entry, dict) else {}
        entry["relocated_from"] = old_key
        entry["relocated_at"] = when
        projects[new] = entry
        changed = True
    if not changed:
        return {"changed": False, "action": "noop_already_migrated"}
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, state_path)
    return {"changed": True, "action": "state_key_migrated", "new_key": new}


def apply_migration(
    db_path: str | Path,
    state_path: str | Path,
    old_root: str | Path,
    new_root: str | Path,
    new_name: str | None = None,
    data_dir: str | Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Plan, and unless dry_run, apply the relocation. Returns an evidence report."""
    db = Path(db_path)
    state_file = Path(state_path)
    data_dir = Path(data_dir) if data_dir is not None else db.parent
    plan = plan_migration(db, state_file, old_root, new_root, new_name)
    if dry_run or not plan["requires_apply"]:
        plan["applied"] = False
        return plan

    backup_dir = _backup(db, state_file, data_dir, plan)
    when = _now()
    new = plan["new_root"]
    name = plan["new_name"]
    conn = sqlite3.connect(str(db), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            db_result = _apply_db(conn, plan, new, name, when)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RelocationError("SQLite integrity_check failed: " + str(integrity))
            fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_rows:
                raise RelocationError(
                    "SQLite foreign_key_check found " + str(len(fk_rows)) + " issue(s)"
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()

    state_result = _apply_state(state_file, plan, new, when)
    verification = verify_identity(db, state_file, new)
    report = dict(plan)
    report["applied"] = True
    report["applied_at"] = when
    report["backup_dir"] = str(backup_dir)
    report["db_result"] = db_result
    report["state_result"] = state_result
    report["verification"] = verification
    (backup_dir / "migration_result.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def verify_identity(db_path: str | Path, state_path: str | Path, new_root: str | Path) -> dict:
    """Read-only post-migration verification of the two durable stores."""
    db = Path(db_path)
    state_file = Path(state_path)
    new = canonical(new_root)
    result: dict[str, Any] = {"ok": True, "errors": [], "new_root": new}
    conn = _connect(db, readonly=True)
    try:
        rows = _project_rows(conn)
        matching = [r for r in rows if norm(r["root"]) == norm(new)]
        if len(matching) != 1:
            result["ok"] = False
            result["errors"].append(
                "Expected exactly one project row for " + repr(new) + ", found "
                + str(len(matching)) + "."
            )
        project = matching[0] if matching else None
        result["project"] = {
            "id": project["id"] if project else None,
            "name": project["name"] if project else None,
            "root": project["root"] if project else None,
            "metadata": _mapping(project["metadata"]) if project else None,
        }
        if len(rows) != 1:
            result["ok"] = False
            result["errors"].append(
                "Expected one project identity total, found " + str(len(rows)) + ": "
                + repr([r["root"] for r in rows])
            )
        counts = _mission_counts(conn)
        result["mission_counts_by_project"] = counts
        result["missions_total"] = sum(counts.values())
        if project is not None:
            result["owned_missions"] = counts.get(str(project["id"]), 0)
        if _table_exists(conn, "missions"):
            orphans = conn.execute(
                "SELECT COUNT(*) FROM missions WHERE project_id IS NOT NULL "
                "AND project_id NOT IN (SELECT id FROM projects)"
            ).fetchone()[0]
            result["orphan_missions"] = int(orphans)
            if orphans:
                result["ok"] = False
                result["errors"].append(str(orphans) + " mission(s) reference a missing project.")
        result["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result["integrity"] != "ok":
            result["ok"] = False
            result["errors"].append("integrity_check: " + str(result["integrity"]))
    finally:
        conn.close()

    if state_file.is_file():
        state = _load_state(state_file)
        projects = state.get("projects") or {}
        keys = list(projects) if isinstance(projects, dict) else []
        result["state_keys"] = keys
        matched = [k for k in keys if norm(k) == norm(new)]
        if len(matched) != 1:
            result["ok"] = False
            result["errors"].append(
                "Expected exactly one selfbuild_state key for " + repr(new) + ", found "
                + repr(matched) + "."
            )
        non_canonical = [k for k in keys if norm(k) == norm(new) and k != new]
        if non_canonical:
            result["ok"] = False
            result["errors"].append("Non-canonical state keys remain: " + repr(non_canonical))
        if matched:
            entry = projects[matched[0]]
            result["state_entry"] = entry if isinstance(entry, dict) else None
    return result


def restore_provenance(
    db_path: str | Path, project_id: int | None = None
) -> dict:
    """Re-merge relocation provenance into projects.metadata when it is missing.

    A normal project OPEN used to replace the metadata column, which could drop the
    relocated_from bookkeeping written by the migration. The migration event
    payload is the durable source of truth; this repair is idempotent and never
    changes the project root or name.
    """
    db = Path(db_path)
    if not db.is_file():
        raise RelocationError("SQLite database not found: " + str(db))
    conn = sqlite3.connect(str(db), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        rows = _project_rows(conn)
        if project_id is not None:
            rows = [r for r in rows if int(r["id"]) == int(project_id)]
        if len(rows) != 1:
            raise RelocationError(
                "Expected exactly one project row to repair, found " + str(len(rows))
            )
        row = rows[0]
        metadata = _mapping(row["metadata"])
        payload: dict = {}
        if _table_exists(conn, "events"):
            event = conn.execute(
                "SELECT payload FROM events WHERE source='migration' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if event:
                payload = _mapping(event["payload"])
        old_root = metadata.get("relocated_from") or payload.get("old_root")
        if not old_root:
            raise RelocationError(
                "No relocation provenance found: projects.metadata has no relocated_from "
                "and no migration event exists."
            )
        changed = False
        wanted = {
            "relocated_from": old_root,
            "relocated_at": metadata.get("relocated_at") or payload.get("timestamp"),
            "previous_name": metadata.get("previous_name") or payload.get("previous_name"),
        }
        for key, value in wanted.items():
            if value and not metadata.get(key):
                metadata[key] = value
                changed = True
        if changed:
            with conn:
                conn.execute(
                    "UPDATE projects SET metadata=? WHERE id=?",
                    (json.dumps(metadata, ensure_ascii=False), row["id"]),
                )
        return {
            "changed": changed,
            "project_id": row["id"],
            "project_root": row["root"],
            "metadata": metadata,
        }
    finally:
        conn.close()


def check_selfbuild_readiness(
    db_path: str | Path,
    state_path: str | Path,
    project_root: str | Path,
) -> dict:
    """Fail-closed guard used before any Self-Build Mode run.

    Refuses to start autonomous work while the durable stores still describe a
    different (typically pre-rename) project root.  A completely fresh install
    is allowed: an absent database/state file simply means there is no history
    to protect yet.
    """
    root = canonical(project_root)
    result: dict[str, Any] = {
        "ok": True,
        "errors": [],
        "warnings": [],
        "project_root": root,
    }
    db = Path(db_path)
    state_file = Path(state_path)
    if not db.is_file():
        result["warnings"].append(
            "No project database yet; the first self-build run will create it."
        )
    else:
        conn = _connect(db, readonly=True)
        try:
            rows = _project_rows(conn)
        finally:
            conn.close()
        result["registered_projects"] = [
            {"id": r["id"], "name": r["name"], "root": r["root"]} for r in rows
        ]
        match = [r for r in rows if norm(r["root"]) == norm(root)]
        if match:
            result["project_id"] = match[0]["id"]
        elif rows:
            stale = [r for r in rows if not Path(r["root"]).exists()]
            if len(stale) == len(rows):
                result["ok"] = False
                result["errors"].append(
                    "Project registry points only at path(s) that no longer exist: "
                    + ", ".join(repr(r["root"]) for r in rows)
                    + ". The workspace was probably renamed; run "
                    "scripts/migrate_project_root.py --apply before self-build."
                )
            else:
                result["warnings"].append(
                    "This project root is not registered yet; it will be registered "
                    "on the first run."
                )
    if state_file.is_file():
        try:
            state = _load_state(state_file)
        except RelocationError as exc:
            result["ok"] = False
            result["errors"].append(str(exc))
            return result
        projects = state.get("projects") or {}
        if isinstance(projects, dict) and projects:
            result["state_keys"] = sorted(projects.keys())
            match_state = [k for k in projects if norm(k) == norm(root)]
            if match_state:
                entry = projects[match_state[0]]
                if isinstance(entry, dict):
                    result["state"] = {
                        "last_completed_mission_id": entry.get("last_completed_mission_id"),
                        "last_completed_fingerprint": entry.get("last_completed_fingerprint"),
                    }
            else:
                result["ok"] = False
                result["errors"].append(
                    "data/selfbuild_state.json has no entry for " + repr(root)
                    + " (existing keys: " + repr(sorted(projects)) + "). "
                    "Run scripts/migrate_project_root.py --apply before self-build."
                )
    return result


def format_plan(plan: dict) -> str:
    lines = [
        "=== NL Coding Agent - project root relocation plan ===",
        "Old root : " + str(plan["old_root"]),
        "New root : " + str(plan["new_root"]),
        "New name : " + str(plan["new_name"]),
        "Database : " + str(plan["db_path"]),
        "State    : " + str(plan["state_path"]),
    ]
    project = plan.get("db", {}).get("project")
    if project:
        lines.append(
            "Project  : id=" + str(project["id"]) + " name=" + repr(project["name"])
            + " missions=" + str(project["missions"]) + " facts=" + str(project["facts"])
        )
    duplicate = plan.get("db", {}).get("duplicate")
    if duplicate:
        lines.append(
            "Duplicate: id=" + str(duplicate["id"]) + " name=" + repr(duplicate["name"])
            + " missions=" + str(duplicate["missions"]) + " (will be merged into the original id)"
        )
    if plan.get("already_migrated"):
        lines.append("Status   : ALREADY MIGRATED (no changes required)")
    for section in ("db", "state"):
        lines.append(section.upper() + " actions:")
        data = plan.get(section, {})
        actions = data.get("actions", [])
        if not actions:
            lines.append("  - none")
        for action in actions:
            lines.append("  - " + str(action["type"]) + ": " + str(action.get("description", "")))
        for warning in data.get("warnings", []):
            lines.append("  WARNING: " + str(warning))
    for warning in plan.get("warnings", []):
        lines.append("WARNING: " + str(warning))
    lines.append(
        "Apply    : "
        + ("required (run again with --apply)" if plan["requires_apply"] else "not required")
    )
    return "\n".join(lines)

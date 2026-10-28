"""Tests for project-root relocation reconciliation (SQLite identity + self-build state)."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from nl_coding_agent.core import relocation as rel


SCHEMA = """
CREATE TABLE projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    root        TEXT NOT NULL UNIQUE,
    opened_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_used   TEXT NOT NULL DEFAULT (datetime('now')),
    metadata    TEXT DEFAULT '{}'
);
CREATE TABLE project_facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, key)
);
CREATE TABLE missions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER,
    title       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL DEFAULT 'system',
    level       TEXT NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL,
    payload     TEXT DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class RelocationTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.data = self.tmp / "data"
        self.data.mkdir()
        self.db = self.data / "nl_coding_agent.sqlite3"
        self.state = self.data / "selfbuild_state.json"
        self.old = self.tmp / "AI" / "Coding Agent"
        self.new = self.tmp / "AI" / "NL Coding Agent"
        self.new.mkdir(parents=True)

    def make_db(self, projects, missions=()):
        conn = sqlite3.connect(self.db)
        try:
            conn.executescript(SCHEMA)
            for project in projects:
                conn.execute(
                    "INSERT INTO projects (id, name, root, opened_at, last_used, metadata) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        project.get("id"),
                        project.get("name", "Coding Agent"),
                        project["root"],
                        project.get("opened_at", "2026-10-28T04:00:00"),
                        project.get("last_used", "2026-10-28T14:00:00"),
                        json.dumps(project.get("metadata", {}), ensure_ascii=False),
                    ),
                )
            for mission in missions:
                conn.execute(
                    "INSERT INTO missions (id, project_id, title) VALUES (?,?,?)",
                    (mission[0], mission[1], mission[2] if len(mission) > 2 else "mission"),
                )
            conn.commit()
        finally:
            conn.close()

    def write_state(self, projects: dict):
        self.state.write_text(
            json.dumps({"projects": projects}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def state_data(self) -> dict:
        return json.loads(self.state.read_text(encoding="utf-8"))

    def project_rows(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY id")]
        finally:
            conn.close()

    def mission_rows(self):
        conn = sqlite3.connect(self.db)
        try:
            return [tuple(r) for r in conn.execute("SELECT id, project_id FROM missions ORDER BY id")]
        finally:
            conn.close()

    def events(self):
        conn = sqlite3.connect(self.db)
        try:
            return [tuple(r) for r in conn.execute("SELECT id, source, message FROM events ORDER BY id")]
        finally:
            conn.close()


class PlanTests(RelocationTestBase):
    def test_plan_is_read_only_and_reports_rename(self):
        self.make_db(
            [{"id": 1, "name": "Coding Agent", "root": str(self.old)}],
            [(3, 1), (7, 1), (44, 1)],
        )
        self.write_state({
            str(self.old): {
                "last_completed_fingerprint": "abc123",
                "last_completed_mission_id": 43,
                "updated_at": "2026-10-28T13:37:24",
                "audit_note_43": "kept",
            }
        })
        before = self.db.read_bytes()
        plan = rel.plan_migration(self.db, self.state, self.old, self.new)
        self.assertTrue(plan["requires_apply"])
        self.assertFalse(plan["already_migrated"])
        actions = [a["type"] for a in plan["db"]["actions"]]
        self.assertIn("rename_project_root", actions)
        state_actions = [a["type"] for a in plan["state"]["actions"]]
        self.assertIn("rename_state_key", state_actions)
        self.assertEqual(plan["db"]["project"]["id"], 1)
        self.assertEqual(plan["db"]["project"]["missions"], 3)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertIn(str(self.old), self.state_data()["projects"])
        self.assertFalse((self.data / "backups").exists())

    def test_forward_slashes_match_windows_separators(self):
        self.make_db([{"id": 1, "name": "Coding Agent", "root": str(self.old)}])
        self.write_state({str(self.old): {"last_completed_mission_id": 43}})
        plan = rel.plan_migration(
            self.db, self.state, str(self.old).replace("\\", "/"), self.new
        )
        self.assertTrue(plan["requires_apply"])

    def test_missing_project_row_raises(self):
        self.make_db([{"id": 1, "name": "Other", "root": str(self.tmp / "unrelated")}])
        self.write_state({str(self.old): {"last_completed_mission_id": 1}})
        with self.assertRaises(rel.RelocationError):
            rel.plan_migration(self.db, self.state, self.old, self.new)


class ApplyTests(RelocationTestBase):
    def setUp(self):
        super().setUp()
        self.make_db(
            [{"id": 1, "name": "Coding Agent", "root": str(self.old),
              "metadata": {"primary_language": "Python", "file_count": 221}}],
            [(3, 1), (7, 1), (16, 1), (24, 1), (30, 1), (36, 1), (44, 1), (45, 1)],
        )
        self.write_state({
            str(self.old): {
                "last_completed_fingerprint": "dc9d7903",
                "last_completed_mission_id": 43,
                "updated_at": "2026-10-28T13:37:24",
                "audit_note_42": "note 42",
                "audit_note_43": "note 43",
            }
        })

    def test_apply_preserves_project_id_missions_and_fingerprint(self):
        report = rel.apply_migration(self.db, self.state, self.old, self.new)
        self.assertTrue(report["applied"])
        self.assertTrue(report["verification"]["ok"])
        rows = self.project_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[0]["root"], rel.canonical(self.new))
        self.assertEqual(rows[0]["name"], "NL Coding Agent")
        metadata = json.loads(rows[0]["metadata"])
        self.assertEqual(metadata["primary_language"], "Python")
        self.assertEqual(metadata["relocated_from"], str(self.old))
        self.assertEqual(metadata["previous_name"], "Coding Agent")
        self.assertEqual(
            self.mission_rows(),
            [(3, 1), (7, 1), (16, 1), (24, 1), (30, 1), (36, 1), (44, 1), (45, 1)],
        )
        state = self.state_data()["projects"]
        self.assertNotIn(str(self.old), state)
        entry = state[rel.canonical(self.new)]
        self.assertEqual(entry["last_completed_mission_id"], 43)
        self.assertEqual(entry["last_completed_fingerprint"], "dc9d7903")
        self.assertEqual(entry["audit_note_42"], "note 42")
        self.assertEqual(entry["audit_note_43"], "note 43")
        self.assertEqual(entry["relocated_from"], str(self.old))
        backup_dir = Path(report["backup_dir"])
        self.assertTrue((backup_dir / "nl_coding_agent.sqlite3").is_file())
        self.assertTrue((backup_dir / "selfbuild_state.json").is_file())
        self.assertTrue((backup_dir / "migration_plan.json").is_file())
        self.assertTrue((backup_dir / "migration_result.json").is_file())
        events = self.events()
        self.assertEqual(events[-1][1], "migration")
        self.assertIn("Project registry relocated", events[-1][2])

    def test_second_apply_is_a_noop(self):
        rel.apply_migration(self.db, self.state, self.old, self.new)
        backups_after_first = sorted((self.data / "backups").iterdir())
        report = rel.apply_migration(self.db, self.state, self.old, self.new)
        self.assertFalse(report["applied"])
        self.assertFalse(report["requires_apply"])
        self.assertTrue(report["already_migrated"])
        self.assertEqual(sorted((self.data / "backups").iterdir()), backups_after_first)
        self.assertEqual(len(self.project_rows()), 1)
        self.assertEqual(list(self.state_data()["projects"]), [rel.canonical(self.new)])

    def test_historical_rows_are_not_rewritten(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "INSERT INTO events (source, level, message, payload) VALUES (?,?,?,?)",
                ("registry", "info", "Opened project: Coding Agent at " + str(self.old), "{}"),
            )
            conn.commit()
        finally:
            conn.close()
        rel.apply_migration(self.db, self.state, self.old, self.new)
        first = self.events()[0]
        self.assertEqual(first[2], "Opened project: Coding Agent at " + str(self.old))
        self.assertEqual(self.mission_rows()[0], (3, 1))

    def test_dry_run_does_not_apply(self):
        report = rel.apply_migration(self.db, self.state, self.old, self.new, dry_run=True)
        self.assertFalse(report["applied"])
        self.assertTrue(report["requires_apply"])
        self.assertEqual(self.project_rows()[0]["root"], str(self.old))


class DuplicateMergeTests(RelocationTestBase):
    def test_duplicate_project_merged_into_original_id(self):
        self.make_db(
            [
                {"id": 1, "name": "Coding Agent", "root": str(self.old)},
                {"id": 2, "name": "NL Coding Agent", "root": str(self.new)},
            ],
            [(3, 1), (44, 1), (99, 2)],
        )
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("INSERT INTO project_facts (project_id, key, value) VALUES (1, 'k1', 'v1')")
            conn.execute("INSERT INTO project_facts (project_id, key, value) VALUES (2, 'k1', 'v2')")
            conn.execute("INSERT INTO project_facts (project_id, key, value) VALUES (2, 'k2', 'v3')")
            conn.commit()
        finally:
            conn.close()
        self.write_state({str(self.old): {"last_completed_mission_id": 43}})
        plan = rel.plan_migration(self.db, self.state, self.old, self.new)
        self.assertIn("merge_duplicate_project", [a["type"] for a in plan["db"]["actions"]])
        report = rel.apply_migration(self.db, self.state, self.old, self.new)
        self.assertTrue(report["verification"]["ok"], report["verification"]["errors"])
        rows = self.project_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[0]["root"], rel.canonical(self.new))
        self.assertEqual(self.mission_rows(), [(3, 1), (44, 1), (99, 1)])
        conn = sqlite3.connect(self.db)
        try:
            facts = conn.execute(
                "SELECT project_id, key, value FROM project_facts ORDER BY key"
            ).fetchall()
            self.assertEqual(len(facts), 2)
            self.assertTrue(all(row[0] == 1 for row in facts))
            values = {row[1]: row[2] for row in facts}
            self.assertEqual(values["k1"], "v1")
            self.assertEqual(values["k2"], "v3")
        finally:
            conn.close()


class StateMergeTests(RelocationTestBase):
    def test_merge_keeps_furthest_mission_and_all_notes(self):
        self.make_db([{"id": 1, "name": "Coding Agent", "root": str(self.old)}], [(44, 1)])
        self.write_state({
            str(self.old): {
                "last_completed_mission_id": 43,
                "last_completed_fingerprint": "old-fp",
                "updated_at": "2026-10-28T13:00:00",
                "audit_note_43": "old note",
            },
            rel.canonical(self.new): {
                "last_completed_mission_id": 44,
                "last_completed_fingerprint": "new-fp",
                "updated_at": "2026-10-28T13:30:00",
                "audit_note_44": "new note",
            },
        })
        report = rel.apply_migration(self.db, self.state, self.old, self.new)
        self.assertTrue(report["applied"])
        projects = self.state_data()["projects"]
        self.assertEqual(list(projects), [rel.canonical(self.new)])
        entry = projects[rel.canonical(self.new)]
        self.assertEqual(entry["last_completed_mission_id"], 44)
        self.assertEqual(entry["last_completed_fingerprint"], "new-fp")
        self.assertEqual(entry["audit_note_43"], "old note")
        self.assertEqual(entry["audit_note_44"], "new note")
        self.assertIn("relocated_from", entry)


class CliTests(RelocationTestBase):
    def _cli(self):
        import importlib.util

        path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_project_root.py"
        spec = importlib.util.spec_from_file_location("migrate_project_root", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def _argv(self):
        return [
            "--db", str(self.db),
            "--state", str(self.state),
            "--data-dir", str(self.data),
            "--new-root", str(self.new),
        ]

    def test_plain_dry_run_on_migrated_repo_says_already_migrated(self):
        import contextlib
        import io

        self.make_db([{"id": 1, "name": "NL Coding Agent", "root": str(self.new)}], [(43, 1)])
        self.write_state({
            rel.canonical(self.new): {
                "last_completed_mission_id": 43,
                "last_completed_fingerprint": "a" * 64,
            }
        })
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = self._cli().main(self._argv())
        self.assertEqual(exit_code, 0)
        self.assertIn("ALREADY MIGRATED", buffer.getvalue())
        self.assertIn("Missions total: 1", buffer.getvalue())

    def test_apply_migrates_a_stale_root(self):
        import contextlib
        import io

        self.make_db([{"id": 1, "name": "Coding Agent", "root": str(self.old)}], [(43, 1)])
        self.write_state({str(self.old): {"last_completed_mission_id": 43}})
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = self._cli().main(self._argv() + ["--apply"])
        self.assertEqual(exit_code, 0)
        self.assertIn("APPLIED", buffer.getvalue())
        self.assertEqual(self.project_rows()[0]["root"], rel.canonical(self.new))
        self.assertEqual(list(self.state_data()["projects"]), [rel.canonical(self.new)])


class ReadinessTests(RelocationTestBase):
    def test_fresh_install_is_allowed(self):
        result = rel.check_selfbuild_readiness(self.db, self.state, self.new)
        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(result["warnings"])

    def test_stale_state_key_blocks_selfbuild(self):
        self.make_db([{"id": 1, "root": str(self.new)}], [(44, 1)])
        self.write_state({str(self.old): {"last_completed_mission_id": 43}})
        result = rel.check_selfbuild_readiness(self.db, self.state, self.new)
        self.assertFalse(result["ok"])
        self.assertIn("no entry", result["errors"][0])

    def test_stale_registry_blocks_selfbuild(self):
        self.make_db([{"id": 1, "root": str(self.old)}], [(44, 1)])
        result = rel.check_selfbuild_readiness(self.db, self.state, self.new)
        self.assertFalse(result["ok"])
        self.assertIn("no longer exist", result["errors"][0])

    def test_reconciled_state_allows_selfbuild(self):
        self.make_db([{"id": 1, "root": str(self.new)}], [(43, 1)])
        self.write_state({
            rel.canonical(self.new): {
                "last_completed_mission_id": 43,
                "last_completed_fingerprint": "a" * 64,
            }
        })
        result = rel.check_selfbuild_readiness(self.db, self.state, self.new)
        self.assertTrue(result["ok"], result["errors"])


if __name__ == "__main__":
    unittest.main()

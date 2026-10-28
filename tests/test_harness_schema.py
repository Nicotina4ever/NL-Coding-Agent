"""C5: additive harness schema migrations and persistence helpers."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.persistence import database
from nl_coding_agent.persistence.missions import (
    create_mission,
    find_mission_by_staging_dir,
    get_mission,
    set_mission_staging,
    set_promotion_status,
)


class HarnessSchemaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self._env = patch.dict(os.environ, {"NL_DATA_DIR": str(self.data)})
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_additive_columns_exist_and_migrations_are_idempotent(self):
        database.init_db().close()
        database.init_db().close()
        conn = database.get_connection()
        try:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(missions)")}
            self.assertIn("harness_version", columns)
            self.assertIn("staging_dir", columns)
            self.assertIn("promotion_status", columns)
            conn.execute(
                "INSERT INTO missions (project_id, title, status) VALUES (NULL, 'legacy', 'pending')"
            )
            conn.commit()
        finally:
            conn.close()
        database.init_db().close()
        legacy = get_mission(1)
        self.assertEqual(legacy["title"], "legacy")
        self.assertIsNone(legacy["harness_version"])

    def test_create_mission_defaults_to_harness_version_2(self):
        mission_id = create_mission(None, "new mission", "goal")
        self.assertEqual(get_mission(mission_id)["harness_version"], 2)
        legacy_id = create_mission(None, "legacy mission", "goal", harness_version=1)
        self.assertEqual(get_mission(legacy_id)["harness_version"], 1)

    def test_staging_and_promotion_helpers_round_trip(self):
        mission_id = create_mission(None, "staged mission", "goal")
        staging = str(self.data / "staging" / "mission-77-abcd")
        set_mission_staging(mission_id, staging)
        set_promotion_status(mission_id, "verified")
        found = find_mission_by_staging_dir(staging)
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], mission_id)
        self.assertEqual(found["promotion_status"], "verified")
        set_mission_staging(mission_id, None)
        self.assertIsNone(find_mission_by_staging_dir(staging))

    def test_supervisor_schema_is_additive_and_idempotent(self):
        database.init_db().close()
        conn = database.get_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO missions (project_id, title, status) "
                    "VALUES (NULL, 'legacy supervisor row', 'pending')"
                )
        finally:
            conn.close()
        database.init_db().close()  # a second init must not lose rows or fail

        expected_tables = {
            "supervisor_leases", "supervisor_runs", "mission_queue",
            "backlog_items", "mission_evidence", "approvals",
            "supervisor_commands", "machine_leases",
        }
        conn = database.get_connection()
        try:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            self.assertTrue(expected_tables <= tables, expected_tables - tables)
            mission_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(missions)")
            }
            self.assertIn("requirement_id", mission_columns)
            self.assertIn("supervisor_run_id", mission_columns)
            event_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(events)")
            }
            for column in ("project_id", "mission_id", "correlation_id", "event_kind"):
                self.assertIn(column, event_columns)
            indexes = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
            for index in (
                "idx_missions_requirement", "idx_queue_project_state",
                "idx_backlog_stage", "idx_evidence_mission",
                "idx_approvals_status", "idx_runs_project",
                "idx_events_correlation",
            ):
                self.assertIn(index, indexes)
            legacy = conn.execute(
                "SELECT * FROM missions WHERE title='legacy supervisor row'"
            ).fetchone()
            self.assertIsNotNone(legacy)
            self.assertIsNone(legacy["requirement_id"])
        finally:
            conn.close()

    def test_settings_helpers_round_trip_and_fail_closed(self):
        database.set_setting("supervisor.global", '{"mode": "off"}')
        self.assertEqual(database.get_setting("supervisor.global"), '{"mode": "off"}')
        self.assertEqual(database.get_setting("missing", "fallback"), "fallback")
        database.set_setting("supervisor.global", '{"mode": "assisted"}')
        self.assertEqual(
            database.get_json_setting("supervisor.global"), {"mode": "assisted"}
        )
        database.set_json_setting("supervisor.project.1", {"max_missions_per_run": 2})
        self.assertEqual(
            database.get_json_setting("supervisor.project.1"),
            {"max_missions_per_run": 2},
        )
        self.assertEqual(database.get_json_setting("missing.json", {"ok": True}), {"ok": True})
        database.set_setting("corrupt.json", "{not-json")
        self.assertEqual(database.get_json_setting("corrupt.json", {"safe": True}), {"safe": True})
        database.set_setting("list.json", "[1, 2, 3]")
        self.assertEqual(database.get_json_setting("list.json", {"safe": True}), {"safe": True})
        with self.assertRaises(ValueError):
            database.set_json_setting("not-an-object", ["nope"])

    def test_log_event_supports_optional_correlation_fields(self):
        conn = database.init_db()
        try:
            database.log_event(conn, "legacy event", source="legacy")
            database.log_event(
                conn, "correlated event", source="supervisor", level="warning",
                payload='{"phase": "preflight"}', project_id=1, mission_id=2,
                correlation_id="run-abc", event_kind="preflight",
            )
        finally:
            conn.close()
        conn = database.get_connection()
        try:
            legacy = conn.execute(
                "SELECT * FROM events WHERE message='legacy event'"
            ).fetchone()
            self.assertIsNone(legacy["correlation_id"])
            self.assertIsNone(legacy["event_kind"])
            correlated = conn.execute(
                "SELECT * FROM events WHERE message='correlated event'"
            ).fetchone()
            self.assertEqual(correlated["project_id"], 1)
            self.assertEqual(correlated["mission_id"], 2)
            self.assertEqual(correlated["correlation_id"], "run-abc")
            self.assertEqual(correlated["event_kind"], "preflight")
            self.assertEqual(correlated["level"], "warning")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

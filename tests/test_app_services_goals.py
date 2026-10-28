"""Tests for the AppServices goal facade (G2, temp NL_DATA_DIR)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.app.services import AppServices  # noqa: E402
from nl_coding_agent.persistence.database import init_db  # noqa: E402


class AppGoalsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name) / "data"
        self._old_env = os.environ.get("NL_DATA_DIR")
        os.environ["NL_DATA_DIR"] = str(self.data_dir)
        self.services = AppServices()

    def tearDown(self):
        try:
            self.services._db.close()
        except Exception:
            pass
        if self._old_env is None:
            os.environ.pop("NL_DATA_DIR", None)
        else:
            os.environ["NL_DATA_DIR"] = self._old_env

    def create(self, **overrides):
        values = dict(objective="Ship G2", title="G2", priority="P1",
                      acceptance_criteria=["cli"])
        values.update(overrides)
        return self.services.goal_create(**values)

    def test_lazy_service_and_structured_crud(self):
        self.assertIsNone(self.services._goal_service_obj)
        created = self.create(priority="P0")
        self.assertTrue(created["ok"])
        self.assertIsNotNone(self.services._goal_service_obj)
        goal = created["goal"]
        self.assertEqual(goal["status"], "planned")
        listed = self.services.goal_list()
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["total"], 1)
        self.assertEqual(self.services.goal_get(goal["id"])["goal"]["title"], "G2")
        updated = self.services.goal_update(goal["id"], title="G2 v2",
                                             priority="P3")
        self.assertTrue(updated["ok"])
        self.assertEqual(updated["goal"]["title"], "G2 v2")
        self.assertEqual(self.services.goal_list(priority="P3")["total"], 1)
        self.assertEqual(self.services.goal_list(priority="P0")["total"], 0)
        missing = self.services.goal_get(9999)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "not_found")

    def test_lifecycle_and_errors(self):
        goal = self.create()["goal"]
        self.assertEqual(self.services.goal_activate(goal["id"])["goal"]["status"],
                         "active")
        self.assertEqual(self.services.goal_pause(goal["id"])["goal"]["status"],
                         "paused")
        self.assertEqual(self.services.goal_resume(goal["id"])["goal"]["status"],
                         "active")
        self.assertEqual(self.services.goal_block(goal["id"], "wait")["goal"]["status"],
                         "blocked")
        self.assertEqual(self.services.goal_unblock(goal["id"])["goal"]["status"],
                         "active")
        self.assertEqual(self.services.goal_cancel(goal["id"])["goal"]["status"],
                         "cancelled")
        invalid = self.services.goal_activate(goal["id"])
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["error"]["code"], "lifecycle")
        bad = self.services.goal_update(goal["id"], status="active")
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["error"]["code"], "lifecycle")

    def test_decompose_milestones_next_work_progress(self):
        goal = self.create()["goal"]
        self.services.goal_activate(goal["id"])
        decomposed = self.services.goal_decompose(goal["id"], [
            {"key": "a", "title": "A"},
            {"key": "b", "title": "B", "dependencies": ["a"]},
        ])
        self.assertTrue(decomposed["ok"])
        self.assertEqual(len(decomposed["milestones"]), 2)
        milestones = self.services.goal_milestones(goal["id"])
        self.assertEqual(milestones["total"], 2)
        work = self.services.goal_next_work(goal_id=goal["id"])
        self.assertEqual(work["total"], 1)
        self.assertEqual(work["work"][0]["title"], "A")
        first_id = work["work"][0]["milestone_id"]
        updated = self.services.goal_milestone_update(first_id, status="completed")
        self.assertTrue(updated["ok"])
        next_work = self.services.goal_next_work(goal_id=goal["id"])
        self.assertEqual(next_work["work"][0]["title"], "B")
        progress = self.services.goal_progress(goal["id"])["progress"]
        self.assertEqual(progress["milestones_total"], 2)
        self.assertEqual(progress["milestones_completed"], 1)
        self.assertEqual(progress["progress_percent"], 50.0)
        summary = self.services.goal_progress_summary()["summary"]
        self.assertEqual(summary["goals_total"], 1)
        self.assertEqual(summary["milestones_total"], 2)
        bad = self.services.goal_decompose(goal["id"], [])
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["error"]["code"], "decomposition")

    def test_persistence_across_instances_and_db_isolation(self):
        goal = self.create()["goal"]
        self.services._db.close()
        second = AppServices()
        try:
            self.assertEqual(second.goal_get(goal["id"])["goal"]["title"], "G2")
        finally:
            second._db.close()
        other_dir = Path(self._tmp.name) / "other"
        old = os.environ["NL_DATA_DIR"]
        os.environ["NL_DATA_DIR"] = str(other_dir)
        try:
            other = AppServices()
            try:
                self.assertEqual(other.goal_list()["total"], 0)
                self.assertFalse(other.goal_get(goal["id"])["ok"])
            finally:
                other._db.close()
        finally:
            os.environ["NL_DATA_DIR"] = old

    def test_no_mission_creation_or_execution(self):
        conn = init_db()
        try:
            before = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        finally:
            conn.close()
        goal = self.create()["goal"]
        self.services.goal_activate(goal["id"])
        self.services.goal_decompose(goal["id"], [{"title": "M"}])
        self.services.goal_next_work()
        self.services.goal_progress(goal["id"])
        conn = init_db()
        try:
            after = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
            goal_row = conn.execute("SELECT status FROM goals WHERE id=?",
                                    (goal["id"],)).fetchone()
        finally:
            conn.close()
        self.assertEqual(after, before)
        self.assertEqual(goal_row["status"], "active")

    def test_facade_is_thin_and_import_safe(self):
        source = (REPO_ROOT / "nl_coding_agent" / "app" / "services.py").read_text(
            encoding="utf-8")
        block_start = source.index("def _goal_service(self):")
        block_end = source.index("def _goal_error(", block_start)
        block = source[block_start:block_end]
        self.assertIn("from nl_coding_agent.core.goals import GoalService", block)
        self.assertNotIn("sqlite3", block.lower())
        self.assertNotIn("requests", block.lower())
        self.assertNotIn("urllib", block.lower())
        self.assertNotIn("subprocess", block.lower())


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

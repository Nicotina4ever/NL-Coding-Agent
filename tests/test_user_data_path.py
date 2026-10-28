import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.core.selfbuild_runner import state_path
from nl_coding_agent.persistence.database import APP_ROOT, db_path, get_connection


class TestUserDataPath(unittest.TestCase):
    def test_default_database_stays_in_workspace_data(self):
        previous = os.environ.pop("NL_DATA_DIR", None)
        try:
            self.assertEqual(
                db_path(),
                APP_ROOT / "data" / "nl_coding_agent.sqlite3",
            )
        finally:
            if previous is not None:
                os.environ["NL_DATA_DIR"] = previous

    def test_override_moves_database_and_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.dict(os.environ, {"NL_DATA_DIR": str(root)}):
                self.assertEqual(db_path(), root / "nl_coding_agent.sqlite3")
                connection = get_connection()
                connection.close()
                self.assertTrue(root.is_dir())
                self.assertTrue((root / "nl_coding_agent.sqlite3").is_file())

    def test_selfbuild_state_follows_database_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.dict(os.environ, {"NL_DATA_DIR": str(root)}):
                self.assertEqual(state_path(), root / "selfbuild_state.json")


if __name__ == "__main__":
    unittest.main()

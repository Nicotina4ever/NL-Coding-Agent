import tempfile
import unittest
from pathlib import Path

from nl_coding_agent.cli import ensure_project, load_yaml


class TestCliConfig(unittest.TestCase):
    def test_missing_yaml_returns_empty_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.yaml"
            self.assertEqual(load_yaml(missing), {})

    def test_missing_project_root_is_a_clear_startup_error(self):
        with self.assertRaises(SystemExit) as caught:
            ensure_project({})
        self.assertIn("Project root not configured", str(caught.exception))

    def test_configured_project_root_is_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(ensure_project({"project": {"root": str(root)}}), root.resolve())


if __name__ == "__main__":
    unittest.main()

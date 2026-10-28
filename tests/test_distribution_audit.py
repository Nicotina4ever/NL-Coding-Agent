import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_distribution.py"


class TestDistributionAudit(unittest.TestCase):
    def test_json_audit_on_temp_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "c.txt").write_text("different", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "ignored.txt").write_text("x" * 100, encoding="utf-8")
            (root / "pyproject.toml").write_text(
                '[project]\nname = "sample"\nversion = "0"\n'
                'dependencies = ["alpha>=1", "beta"]\n',
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["root"], str(root.resolve()))
            expected_size = sum(
                path.stat().st_size
                for path in root.rglob("*")
                if path.is_file() and ".git" not in path.parts
            )
            self.assertEqual(result["total_size"], expected_size)
            self.assertEqual(result["duplicate_groups"][0]["size"], 4)
            self.assertEqual(
                {Path(path).name for path in result["duplicate_groups"][0]["paths"]},
                {"a.txt", "b.txt"},
            )
            self.assertEqual(result["dependencies"], ["alpha>=1", "beta"])
            self.assertNotIn(".git", [item["path"] for item in result["top_directories"]])


if __name__ == "__main__":
    unittest.main()

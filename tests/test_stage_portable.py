import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stage_portable.py"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run(source: Path, output: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--output",
            str(output),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


class TestPortableStaging(unittest.TestCase):
    def _source_tree(self, root: Path) -> None:
        _write(root / "nl_agent.py", "print('app')\n")
        _write(root / "nl_coding_agent" / "__init__.py", "VERSION = '0'\n")
        _write(root / "nl_coding_agent" / "__pycache__" / "ignored.pyc", "cache")
        _write(root / "python" / "python.exe", "fake-runtime")
        _write(root / "python" / "Scripts" / "pytest.exe", "console-script")
        _write(root / "python" / "Lib" / "site-packages" / "pkg" / "mod.py", "VALUE = 1\n")
        _write(root / "assets" / "logo.svg", "<svg/>")
        _write(root / "config" / "models.yaml", "models: []\n")
        _write(root / "config" / "voicebridge.yaml", "project:\n  root: 'C:/private'\n")
        _write(root / "pyproject.toml", "[project]\nname='x'\n")
        _write(root / "Self-Build Mode.bat", "@echo off\n")
        _write(root / "NL Coding Agent.bat", "@echo off\n")
        _write(root / "crewAI" / "vendor.py", "vendor")
        _write(root / "data" / "db.sqlite3", "user-data")
        _write(root / "logs" / "app.log", "log")
        _write(root / "tests" / "test_x.py", "def test_x(): pass\n")
        _write(root / ".git" / "config", "git")
        _write(root / "scripts" / "ignored.py", "script")
        _write(root / "docs" / "ignored.md", "doc")
        _write(root / "dist" / "old.txt", "old-build")
        _write(root / "build" / "tmp.txt", "temp-build")

    def test_staging_excludes_vendor_user_data_and_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "payload"
            self._source_tree(source)

            completed = _run(source, output, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads(completed.stdout)

            self.assertTrue((output / "nl_agent.py").is_file())
            self.assertTrue((output / "nl_coding_agent" / "__init__.py").is_file())
            self.assertTrue((output / "python" / "python.exe").is_file())
            self.assertTrue((output / "assets" / "logo.svg").is_file())
            self.assertTrue((output / "config" / "models.yaml").is_file())
            self.assertFalse((output / "crewAI").exists())
            self.assertFalse((output / "data").exists())
            self.assertFalse((output / "logs").exists())
            self.assertFalse((output / "tests").exists())
            self.assertFalse((output / ".git").exists())
            self.assertFalse((output / "scripts").exists())
            self.assertFalse((output / "docs").exists())
            self.assertFalse((output / "nl_coding_agent" / "__pycache__").exists())
            self.assertFalse((output / "python" / "Scripts").exists())
            self.assertFalse((output / "dist").exists())
            self.assertFalse((output / "build").exists())
            self.assertFalse((output / "config" / "voicebridge.yaml").exists())

            self.assertEqual(manifest["file_count"], 9)
            self.assertIn("config/voicebridge.yaml", manifest["excluded_files"])
            self.assertGreater(manifest["total_size"], 0)
            self.assertIn("crewAI", manifest["excluded_roots"])
            self.assertIn("data", manifest["excluded_roots"])
            self.assertEqual(
                {entry["path"] for entry in manifest["top_level"]},
                {
                    "NL Coding Agent.bat",
                    "Self-Build Mode.bat",
                    "assets",
                    "config",
                    "nl_agent.py",
                    "nl_coding_agent",
                    "pyproject.toml",
                    "python",
                },
            )
            self.assertTrue((output / "payload_manifest.json").is_file())

    def test_dry_run_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "payload"
            self._source_tree(source)

            completed = _run(source, output, "--dry-run", "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads(completed.stdout)
            self.assertTrue(manifest["dry_run"])
            self.assertFalse(output.exists())

    def test_non_empty_output_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "payload"
            self._source_tree(source)
            output.mkdir()
            _write(output / "existing.txt", "keep")

            completed = _run(source, output)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("not empty", completed.stderr)

    def test_default_output_is_under_dist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._source_tree(source)

            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--source", str(source), "--dry-run", "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads(completed.stdout)
            self.assertEqual(
                Path(manifest["output"]),
                (source / "dist" / "portable-release").resolve(),
            )
            self.assertFalse((source / "dist" / "portable-release").exists())

    def test_dist_output_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._source_tree(source)
            output = source / "dist" / "payload"

            completed = _run(source, output, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output / "nl_agent.py").is_file())

    def test_output_inside_source_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._source_tree(source)

            completed = _run(source, source / "build")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("outside the source tree", completed.stderr)


if __name__ == "__main__":
    unittest.main()

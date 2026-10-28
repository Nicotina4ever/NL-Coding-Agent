import json
import os
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
        timeout=120,
    )


class TestPortableStaging(unittest.TestCase):
    def _source_tree(self, root: Path) -> None:
        _write(root / "README.md", "# Demo app\n")
        _write(root / "nl_agent.py", "print('app')\n")
        _write(root / "nl_coding_agent" / "__init__.py", "VERSION = '0'\n")
        _write(root / "nl_coding_agent" / "flows" / "__init__.py", "FLOWS = True\n")
        _write(root / "nl_coding_agent" / "__pycache__" / "ignored.pyc", "cache")
        _write(root / "python" / "python.exe", "fake-runtime")
        _write(root / "python" / "Scripts" / "pytest.exe", "console-script")
        _write(root / "python" / "Lib" / "site-packages" / "pkg" / "mod.py", "VALUE = 1\n")
        _write(root / "python" / "Lib" / "site-packages" / "crewai" / "__init__.py", "VERSION = 1\n")
        _write(root / "python" / "_sqlite3.pyd", "fake-extension")
        _write(root / "assets" / "logo.svg", "<svg/>")
        _write(root / "config" / "models.yaml", "models: []\n")
        _write(root / "config" / "extra.yaml", "should: be-excluded\n")
        _write(root / "config" / "voicebridge.yaml", "project:\n  root: 'C:/private'\n")
        _write(root / "pyproject.toml", "[project]\nname='x'\n")
        _write(root / "NL Coding Agent.bat", "@echo off\n")
        _write(root / "scripts" / "launchers" / "Self-Build Mode.bat", "@echo off\n")
        _write(root / "scripts" / "launchers" / "doctor.bat", "@echo off\n")
        _write(root / "scripts" / "launchers" / "status.bat", "@echo off\n")
        for name in ("NL Coding Agent.sh", "doctor.sh", "status.sh",
                     "Self-Build Mode.sh", "NL Coding Agent.command"):
            _write(root / "scripts" / "launchers" / name,
                   "#!/usr/bin/env sh\nexec echo \"$@\"\n")
        _write(root / "AGENTS.md", "dev rules")
        _write(root / "installer" / "bootstrap.py", "installer")
        _write(root / "PATCH" / "old.py", "patch evidence")
        _write(root / "crewAI" / "vendor.py", "vendor")
        _write(root / "data" / "db.sqlite3", "user-data")
        _write(root / ".workspace" / "logs" / "app.log", "log")
        _write(root / "tests" / "test_x.py", "def test_x(): pass\n")
        _write(root / ".git" / "config", "git")
        _write(root / "scripts" / "ignored.py", "script")
        _write(root / "docs" / "ignored.md", "doc")
        _write(root / ".workspace" / "build" / "tmp.txt", "temp-build")

    def test_staging_uses_stage6b_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "payload"
            self._source_tree(source)

            completed = _run(source, output, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads(completed.stdout)

            for included in (
                "README.md", "nl_agent.py", "python/_sqlite3.pyd", "nl_coding_agent/__init__.py",
                "nl_coding_agent/flows/__init__.py", "python/python.exe",
                "assets/logo.svg", "config/models.yaml", "pyproject.toml",
                "Self-Build Mode.bat", "NL Coding Agent.bat", "doctor.bat",
                "status.bat", "NL Coding Agent.sh", "NL Coding Agent.command",
                "doctor.sh", "status.sh", "Self-Build Mode.sh",
            ):
                self.assertTrue((output / included).is_file(), included)
            # Sources under scripts/launchers/ are re-mapped to the payload root.
            self.assertTrue((source / "scripts" / "launchers" / "doctor.bat").is_file())
            self.assertFalse((output / "scripts").exists())
            for excluded in (
                "crewAI", "data", ".workspace", "tests", ".git", "scripts", "docs",
                "installer", "PATCH", "AGENTS.md",
            ):
                self.assertFalse((output / excluded).exists(), excluded)
            self.assertFalse((output / "config" / "voicebridge.yaml").exists())
            self.assertFalse((output / "config" / "extra.yaml").exists())
            self.assertFalse((output / "nl_coding_agent" / "__pycache__").exists())
            self.assertFalse((output / "python" / "Scripts").exists())
            self.assertFalse((output / "SHA256_MANIFEST.json").exists())

            self.assertEqual(manifest["payload_manifest_version"], 1)
            self.assertEqual(manifest["file_count"], 20)
            self.assertEqual(manifest["source_name"], "source")
            self.assertEqual(manifest["output_name"], "payload")
            self.assertEqual(manifest["output_location"], "external")
            self.assertEqual(len(manifest["tree_sha256"]), 64)
            self.assertIn("README.md", manifest["included_roots"])
            self.assertIn("scripts/launchers/doctor.bat", manifest["launcher_source_to_payload"])
            self.assertEqual(
                manifest["launcher_source_to_payload"]["scripts/launchers/doctor.bat"],
                "doctor.bat",
            )
            self.assertIn("installer", manifest["excluded_roots"])
            self.assertIn(".workspace", manifest["excluded_roots"])
            self.assertIn("PATCH", manifest["excluded_roots"])
            self.assertIn("AGENTS.md", manifest["excluded_roots"])
            checks = manifest["payload_checks"]
            self.assertTrue(checks["checked"])
            self.assertTrue(checks["runtime"]["single_runtime_copy"])
            self.assertEqual(checks["runtime"]["python_runtime_copies"], 1)
            self.assertEqual(checks["runtime"]["crewai_package_copies"], 1)
            self.assertEqual(checks["absolute_path_hits"], [])
            self.assertEqual(checks["excluded_top_level_present"], [])
            self.assertNotIn(str(source), json.dumps(manifest))
            self.assertTrue((output / "payload_manifest.json").is_file())
            self.assertEqual(
                {entry["path"] for entry in manifest["top_level"]},
                {
                    "README.md",
                    "NL Coding Agent.bat",
                    "Self-Build Mode.bat",
                    "assets",
                    "config",
                    "doctor.bat",
                    "nl_agent.py",
                    "nl_coding_agent",
                    "pyproject.toml",
                    "python",
                    "status.bat",
                    "NL Coding Agent.sh",
                    "NL Coding Agent.command",
                    "doctor.sh",
                    "status.sh",
                    "Self-Build Mode.sh",
                },
            )

    def test_posix_launchers_are_staged_at_payload_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "payload"
            self._source_tree(source)
            completed = _run(source, output, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads(completed.stdout)
            self.assertFalse((output / "scripts").exists())
            for name in ("NL Coding Agent.sh", "NL Coding Agent.command",
                         "doctor.sh", "status.sh", "Self-Build Mode.sh"):
                self.assertTrue((output / name).is_file(), name)
                self.assertIn("scripts/launchers/" + name,
                              manifest["launcher_source_to_payload"])
                self.assertEqual(
                    manifest["launcher_source_to_payload"]["scripts/launchers/" + name],
                    name,
                )
            if os.name != "nt":
                for name in ("NL Coding Agent.sh", "doctor.sh", "status.sh",
                             "Self-Build Mode.sh", "NL Coding Agent.command"):
                    self.assertTrue(os.access(output / name, os.X_OK), name)
            self.assertEqual(manifest["payload_checks"]["absolute_path_hits"], [])

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
            self.assertEqual(manifest["file_count"], 20)
            self.assertFalse(manifest["output_location"] == "dist")

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

    def test_default_output_is_under_workspace_dist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._source_tree(source)

            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--source", str(source), "--dry-run", "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads(completed.stdout)
            self.assertEqual(manifest["output_name"], "portable-release")
            self.assertEqual(manifest["output_location"], "dist")
            self.assertFalse((source / ".workspace" / "dist" / "portable-release").exists())

    def test_workspace_dist_output_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._source_tree(source)
            output = source / ".workspace" / "dist" / "payload"

            completed = _run(source, output, "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads(completed.stdout)
            self.assertEqual(manifest["output_location"], "dist")
            self.assertTrue((output / "nl_agent.py").is_file())

    def test_output_inside_source_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._source_tree(source)

            completed = _run(source, source / ".workspace" / "build")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("outside the source tree", completed.stderr)

    def test_absolute_workspace_paths_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "payload"
            self._source_tree(source)
            _write(source / "nl_coding_agent" / "bad.py", "ROOT = '" + str(source) + "'\n")

            completed = _run(source, output)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("absolute workspace paths", completed.stderr)
            self.assertFalse(output.exists())

    def test_duplicate_runtime_copy_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "payload"
            self._source_tree(source)
            _write(source / "python" / "Lib" / "site-packages" / "nested" / "python.exe", "second")

            completed = _run(source, output)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("exactly one embedded Python runtime", completed.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

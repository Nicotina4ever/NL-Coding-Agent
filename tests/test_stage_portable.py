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



def _find_posix_shell() -> str | None:
    import os
    import shutil

    if os.name == "nt":
        # Prefer Git Bash (MSYS) over the WindowsApps bash.exe WSL launcher,
        # whose POSIX paths do not map onto Windows temp directories.
        candidates = [r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files\Git\usr\bin\sh.exe"]
        for candidate in candidates:
            if Path(candidate).is_file():
                return candidate
        for candidate in (shutil.which("bash"), shutil.which("sh")):
            if candidate and "WindowsApps" not in candidate and Path(candidate).is_file():
                return candidate
        return None
    candidates = [shutil.which("bash"), shutil.which("sh"), "/bin/sh", "/bin/bash"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


POSIX_SHELL = _find_posix_shell()


def _shell_path(path) -> str:
    """Return a path usable by the detected shell (MSYS form for Git Bash on Windows)."""
    import re

    text = str(path)
    if os.name == "nt" and POSIX_SHELL and "Git" in str(POSIX_SHELL):
        match = re.match(r"^([A-Za-z]):\\?(.*)$", text)
        if match:
            return "/" + match.group(1).lower() + "/" + match.group(2).replace("\\", "/")
    return text


@unittest.skipUnless(POSIX_SHELL, "no usable POSIX shell (sh/bash) available")
class TestPosixLaunchers(unittest.TestCase):
    """Execute the POSIX launchers in a dependency-free synthetic layout."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        launchers = self.src / "scripts" / "launchers"
        launchers.mkdir(parents=True)
        for path in sorted((ROOT / "scripts" / "launchers").glob("*.sh")):
            target = launchers / path.name
            target.write_bytes(path.read_bytes())
        fake_python = self.src / "python" / "bin" / "python3"
        fake_python.parent.mkdir(parents=True)
        fake_python.write_bytes(
            ("#!/bin/sh" + chr(10)
             + 'echo "FAKE_PY cwd=$(pwd) args=$*"' + chr(10)).encode("utf-8"))
        os.chmod(fake_python, 0o755)
        (self.src / "nl_agent.py").write_bytes(b"print('fake agent')" + bytes([10]))
        self.env = dict(os.environ)
        self.env.pop("NL_SELFBUILD_REVIEWER_MODEL", None)
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def _run(self, launcher: Path, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run([POSIX_SHELL, _shell_path(launcher)], cwd=str(cwd),
                              env=self.env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)

    def _launcher(self, name: str) -> Path:
        return self.src / "scripts" / "launchers" / name

    def test_gui_doctor_status_launchers_resolve_root_and_argv(self):
        expectations = {
            "NL Coding Agent.sh": "gui",
            "doctor.sh": "doctor",
            "status.sh": "status",
        }
        for name, command in expectations.items():
            completed = self._run(self._launcher(name), self.root)
            output = completed.stdout + completed.stderr
            self.assertEqual(completed.returncode, 0, name + ": " + output)
            self.assertIn("FAKE_PY", output, name)
            self.assertTrue("cwd=" + str(self.src) in output
                            or "cwd=" + _shell_path(self.src) in output,
                            name + ": unexpected cwd in " + output)
            self.assertIn("nl_agent.py", output, name)
            self.assertIn(command, output, name)

    def test_self_build_launcher_expands_default_reviewer_model(self):
        completed = self._run(self._launcher("Self-Build Mode.sh"), self.root)
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertIn("FAKE_PY", output)
        self.assertIn("selfbuild", output)
        self.assertIn("--autonomous", output)
        self.assertIn("--reviewer-model", output)
        self.assertIn("ollama/qwen3.5:9b", output)

    def test_payload_without_runtime_fails_closed(self):
        payload = self.root / "payload"
        payload.mkdir()
        launcher = payload / "doctor.sh"
        launcher.write_bytes(self._launcher("doctor.sh").read_bytes())
        (payload / "nl_agent.py").write_bytes(b"print('x')" + bytes([10]))
        completed = self._run(launcher, self.root)
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 2, output)
        self.assertIn("no provisioned POSIX Python runtime", output)

    def test_posix_launchers_have_no_malformed_parameter_expansions(self):
        for path in sorted((ROOT / "scripts" / "launchers").glob("*")):
            if path.suffix not in (".sh", ".command"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("$${", text, "malformed parameter expansion in " + path.name)

    def test_payload_manifest_is_lf_only(self):
        source = self.root / "staged-source"
        output = self.root / "payload-out"
        self._write_source_tree(source)
        completed = _run(source, output, "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        manifest = (output / "payload_manifest.json").read_bytes()
        self.assertNotIn(b"\r", manifest)

    def _write_source_tree(self, root: Path) -> None:
        _write(root / "nl_agent.py", "print('app')" + chr(10))
        _write(root / "nl_coding_agent" / "__init__.py", "VERSION = '0'" + chr(10))
        _write(root / "python" / "python.exe", "fake-runtime")
        _write(root / "assets" / "logo.svg", "<svg/>")
        _write(root / "config" / "models.yaml", "models: []" + chr(10))
        _write(root / "pyproject.toml", "[project]" + chr(10) + "name='x'" + chr(10))
        _write(root / "Self-Build Mode.bat", "@echo off" + chr(10))
        _write(root / "NL Coding Agent.bat", "@echo off" + chr(10))


if __name__ == "__main__":
    unittest.main()

"""Tests for the read-only relocation verification helpers."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_relocation.py"
spec = importlib.util.spec_from_file_location("verify_relocation", SCRIPT)
verify = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(verify)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)

    def write(self, rel: str, text: str) -> Path:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_detects_backslash_forward_slash_and_escaped_forms(self):
        self.write("a.md", "root is K:\\AI\\Coding Agent now")
        self.write("b.md", "root is K:/AI/Coding Agent now")
        self.write("c.json", json.dumps({"root": "K:\\AI\\Coding Agent"}))
        hits = verify.scan_paths_for_old_root(
            [self.repo / "a.md", self.repo / "b.md", self.repo / "c.json"], self.repo
        )
        self.assertEqual({hit["path"] for hit in hits}, {"a.md", "b.md", "c.json"})
        self.assertTrue(all(hit["line"] == 1 for hit in hits))

    def test_does_not_match_new_canonical_root(self):
        self.write("a.md", "root is K:\\AI\\NL Coding Agent now")
        hits = verify.scan_paths_for_old_root([self.repo / "a.md"], self.repo)
        self.assertEqual(hits, [])

    def test_operational_paths_ignore_historical_docs(self):
        self.write("AGENTS.md", "K:\\AI\\Coding Agent")
        self.write("docs/COMPLETED_MISSIONS.md", "K:\\AI\\Coding Agent")
        self.write("docs/CURRENT_STATE.md", "K:\\AI\\NL Coding Agent")
        paths = verify.operational_file_paths(self.repo)
        names = [path.relative_to(self.repo).as_posix() for path in paths]
        self.assertIn("AGENTS.md", names)
        self.assertIn("docs/CURRENT_STATE.md", names)
        self.assertNotIn("docs/COMPLETED_MISSIONS.md", names)

    def test_launcher_paths_include_root_and_consolidated_bat_files(self):
        self.write("NL Coding Agent.bat", "cd /d \"%~dp0\"")
        self.write("scripts/launchers/Self-Build Mode.bat", "K:\\AI\\Coding Agent")
        paths = [
            path.relative_to(self.repo).as_posix()
            for path in verify.launcher_paths(self.repo)
        ]
        self.assertIn("NL Coding Agent.bat", paths)
        self.assertIn("scripts/launchers/Self-Build Mode.bat", paths)
        hits = verify.scan_paths_for_old_root(verify.launcher_paths(self.repo), self.repo)
        expected = str(Path("scripts") / "launchers" / "Self-Build Mode.bat")
        self.assertEqual([hit["path"] for hit in hits], [expected])


class WorkspaceLayoutTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        (self.repo / "python").mkdir()
        (self.repo / "data").mkdir()
        verify.CHECKS.clear()
        self.addCleanup(verify.CHECKS.clear)

    def _checks(self) -> dict:
        return {item["check"]: item["status"] for item in verify.CHECKS}

    def test_detects_missing_workspace_and_legacy_output_dirs(self):
        (self.repo / "build").mkdir()
        verify.check_workspace_layout(self.repo)
        checks = self._checks()
        self.assertEqual(checks["workspace.root"], "FAIL")
        self.assertEqual(checks["workspace.no_legacy_root_outputs"], "FAIL")
        self.assertEqual(checks["workspace.python_preserved"], "PASS")
        self.assertEqual(checks["workspace.data_preserved"], "PASS")

    def test_passes_for_consolidated_workspace_layout(self):
        for name in ("build", "dist", "logs", "temp", "cache", "state"):
            (self.repo / ".workspace" / name).mkdir(parents=True)
        (self.repo / "python").mkdir(exist_ok=True)
        (self.repo / "data").mkdir(exist_ok=True)
        verify.check_workspace_layout(self.repo)
        checks = self._checks()
        self.assertEqual(checks["workspace.root"], "PASS")
        self.assertEqual(checks["workspace.no_legacy_root_outputs"], "PASS")
        self.assertEqual(checks["workspace.python_preserved"], "PASS")
        self.assertEqual(checks["workspace.data_preserved"], "PASS")


if __name__ == "__main__":
    unittest.main()

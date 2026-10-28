"""CLI docs ingest tests: temp dirs, no network/model, exit codes."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "nl_agent.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class DocsCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "project"
        _write(self.root / "README.md", "# CLI docs\n\nBody.\n")
        _write(self.root / "docs" / "architecture.md", "# Arch\n")
        self.env = dict(os.environ)
        self.env["NL_DATA_DIR"] = str(Path(self._tmp.name) / "data")
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, str(CLI), "docs", "ingest", *args],
            cwd=str(REPO), env=self.env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)

    def test_json_success_counts_and_untrusted(self):
        completed = self._run("--project", str(self.root), "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["counts"]["documents"], 2)
        self.assertTrue(payload["untrusted"])
        self.assertFalse(payload["executed"])
        self.assertIn("project", payload["source_kinds"])
        self.assertTrue(all("text" not in doc for doc in payload["documents"]))

    def test_text_output_and_explicit_paths_archive(self):
        archive = Path(self._tmp.name) / "docs.zip"
        import zipfile
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("guide.md", "# Guide\n")
        completed = self._run("--project", str(self.root), "--path",
                              str(self.root / "README.md"),
                              "--archive", str(archive))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Document ingestion: completed", completed.stdout)
        self.assertIn("UNTRUSTED", completed.stdout)
        self.assertIn("not executed", completed.stdout)
        self.assertIn("source kinds", completed.stdout)

    def test_url_without_reader_exits_1_without_network(self):
        completed = self._run("--project", str(self.root),
                              "--url", "https://example.com/doc", "--json")
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["outcome"], "unavailable")
        self.assertIn("no implicit network", payload["error"]["message"])

    def test_usage_error_exit_2_and_help_untrusted(self):
        missing = subprocess.run([sys.executable, str(CLI), "docs"],
                                 cwd=str(REPO), env=self.env, capture_output=True,
                                 text=True, encoding="utf-8", timeout=60)
        self.assertEqual(missing.returncode, 2)
        help_run = subprocess.run(
            [sys.executable, str(CLI), "docs", "ingest", "--help"],
            cwd=str(REPO), env=self.env, capture_output=True, text=True,
            encoding="utf-8", timeout=60)
        self.assertEqual(help_run.returncode, 0)
        text = help_run.stdout.lower()
        for expected in ("untrusted", "never executed", "--path", "--archive",
                         "--url", "--git-ref", "--json"):
            self.assertIn(expected, text)

    def test_no_default_network_or_mission_in_docs_dispatch(self):
        source = (REPO / "nl_coding_agent" / "cli.py").read_text(encoding="utf-8")
        section = source[source.index("def _dispatch_docs"):source.index(
            "def main", source.index("def _dispatch_docs"))]
        for forbidden in ("requests", "urllib", "socket", "make_llm", "run_mission",
                          "selfbuild", "create_mission"):
            self.assertNotIn(forbidden, section)


if __name__ == "__main__":
    unittest.main()

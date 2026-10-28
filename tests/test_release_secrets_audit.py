"""Tests for the read-only pre-upload secrets/history audit (NL-BP-162).

Covers: detection + classification of secret patterns and heavy artifacts,
redaction of evidence, bounded limits, Git-history-only leaks, present-but-
untracked trees, read-only behaviour (no Git writes, no repo mutations, no
deletions), and static no-network/no-destructive-command guards.

The audit must never modify the repository under test; every fixture is created
in a temporary directory and every scan writes reports only to an explicit
temporary output directory.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit_release_secrets.py"
sys.dont_write_bytecode = True

_spec = importlib.util.spec_from_file_location("audit_release_secrets", SCRIPT)
audit = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(audit)

GIT = shutil.which("git")
BS = chr(92)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

class GitFixture:
    """A temporary Git repository used as the audit target."""

    def __init__(self, testcase: unittest.TestCase):
        self._tmp = tempfile.TemporaryDirectory()
        testcase.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.root = base / "repo"
        self.root.mkdir()
        self.home = base / "home"
        self.home.mkdir()
        self.env = dict(os.environ)
        self.env.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Audit Test",
            "GIT_AUTHOR_EMAIL": "audit@example.invalid",
            "GIT_COMMITTER_NAME": "Audit Test",
            "GIT_COMMITTER_EMAIL": "audit@example.invalid",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.git("init", "-q")

    def git(self, *args: str) -> subprocess.CompletedProcess:
        completed = subprocess.run(
            ["git", "-C", str(self.root)] + list(args),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=self.env, timeout=120, check=False,
        )
        return completed

    def write(self, rel: str, data) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8", newline="")
        return path

    def write_bytes(self, rel: str, data: bytes) -> Path:
        return self.write(rel, data)

    def commit(self, message: str = "fixture") -> str:
        self.git("add", "-A")
        completed = self.git("commit", "-q", "-m", message)
        assert completed.returncode == 0, completed.stderr
        out = self.git("rev-parse", "HEAD")
        return out.stdout.strip()


def run_cli(repo: Path, *extra: str, out_dir: Path | None = None) -> subprocess.CompletedProcess:
    command = [sys.executable, str(SCRIPT), "--root", str(repo)]
    if out_dir is None:
        command.append("--no-write")
    else:
        command.extend(["--json-out", str(out_dir / "report.json"),
                        "--markdown-out", str(out_dir / "report.md")])
    command.extend(extra)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, env=env, check=False)


def read_reports(out_dir: Path) -> tuple:
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "report.md").read_text(encoding="utf-8")
    return report, markdown


def snapshot_tree(root: Path) -> dict:
    entries = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            entries[rel] = ("dir",)
        elif path.is_file():
            data = path.read_bytes()
            entries[rel] = ("file", len(data), hashlib.sha256(data).hexdigest())
    return entries


def fake_aws_key() -> str:
    # Assembled at runtime so this test file never contains a contiguous key literal.
    return "AKIA" + "ABCDEFGHIJKLMNOP"


def fake_github_token() -> str:
    return "ghp_" + ("A" * 36)


def fake_private_key_block() -> str:
    return "-----BEGIN " + "RSA PRIVATE KEY-----" + chr(10) + "MIIFAKEFAKEFAKEFAKE" + chr(10)


def fake_password_value() -> str:
    return "S3cret" + "Value" + "ForTest"


def build_secret_and_artifact_fixture(fixture: GitFixture) -> None:
    """Fixture repo with fake secrets and heavy/private artifacts."""
    fixture.write("config/settings.py",
                  "# application settings" + chr(10)
                  + "aws_access_key_id = \"" + fake_aws_key() + "\"" + chr(10)
                  + "github_token = \"" + fake_github_token() + "\"" + chr(10)
                  + "password = \"" + fake_password_value() + "\"" + chr(10))
    fixture.write("certs/server.pem", fake_private_key_block())
    fixture.write("README.md",
                  "Example machine path: " + "C:" + BS + "Users" + BS + "alice" + BS + "project" + chr(10)
                  + "Local endpoint: " + "http://127." + "0.0.1:11434" + chr(10))
    fixture.write_bytes("data/app.sqlite3", b"SQLite format 3" + bytes([0]) + b"\x00" * 128)
    fixture.write_bytes("large.dat", b"\x01" * (6 * 1024 * 1024))
    fixture.write("models/tiny.gguf", "model-marker")
    fixture.write("python/embedded.txt", "runtime-marker")
    fixture.write("crewAI/vendor.txt", "vendor-marker")
    fixture.write(".workspace/dist/payload.txt", "build-output-marker")
    fixture.write(".env", "API_TOKEN=" + fake_password_value() + chr(10))
    fixture.commit("fixture with secrets and artifacts")


class AuditTestBase(unittest.TestCase):
    def setUp(self):
        if GIT is None:
            self.skipTest("git executable not available")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "out"
        self.out.mkdir()


# ---------------------------------------------------------------------------
# Detection and classification
# ---------------------------------------------------------------------------

class TestDetectionAndClassification(AuditTestBase):
    def test_detects_secrets_artifacts_and_classifies(self):
        fixture = GitFixture(self)
        build_secret_and_artifact_fixture(fixture)
        completed = run_cli(fixture.root, out_dir=self.out)
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        report, markdown = read_reports(self.out)
        rules = {item["rule"] for item in report["findings"]}
        for expected in ("aws_access_key_id", "github_token", "private_key_block",
                         "generic_secret_assignment", "windows_user_profile",
                         "private_network_url"):
            self.assertIn(expected, rules, "missing rule: " + expected)
        classes = {(item["kind"], item["classification"]) for item in report["findings"]}
        for expected in (
            ("private_database", "EXCLUDE-FROM-UPLOAD"),
            ("embedded_runtime_or_vendor", "EXCLUDE-FROM-UPLOAD"),
            ("build_output", "EXCLUDE-FROM-UPLOAD"),
            ("model_checkpoint_or_binary", "EXCLUDE-FROM-UPLOAD"),
            ("large_binary", "EXCLUDE-FROM-UPLOAD"),
            ("secret_file", "EXCLUDE-FROM-UPLOAD"),
            ("key_material_file", "ROTATE"),
            ("cloud_credential", "ROTATE"),
            ("provider_token", "ROTATE"),
        ):
            self.assertIn(expected, classes, "missing classification: " + str(expected))
        self.assertGreaterEqual(report["summary"]["blocking_count"], 1)
        self.assertEqual(report["summary"]["upload_gate"], "BLOCKED")
        self.assertIn("Owner authorization", markdown)
        self.assertIn("owner authorization", markdown.lower())
        self.assertIn("redacted", markdown.lower())


class TestRedaction(AuditTestBase):
    def test_full_secrets_never_appear_in_reports_or_stdout(self):
        fixture = GitFixture(self)
        build_secret_and_artifact_fixture(fixture)
        completed = run_cli(fixture.root, out_dir=self.out)
        report, markdown = read_reports(self.out)
        combined = completed.stdout + completed.stderr + json.dumps(report) + markdown
        for secret in (fake_aws_key(), fake_github_token(), fake_password_value(),
                       "MIIFAKEFAKEFAKEFAKE"):
            self.assertNotIn(secret, combined, "full secret leaked: " + secret[:6] + "...")
        for item in report["findings"]:
            evidence = item.get("evidence") or {}
            matched = evidence.get("matched")
            if isinstance(matched, dict):
                self.assertIn("sha256_12", matched)
                self.assertLessEqual(len(matched.get("prefix", "")), 4)
                self.assertEqual(len(matched["sha256_12"]), 12)
            if item.get("context_redacted"):
                self.assertLessEqual(len(item["context_redacted"]), 220)
        self.assertIn("[REDACTED:", markdown)


class TestHistoryOnlySecret(AuditTestBase):
    def test_removed_secret_is_reported_from_git_history(self):
        fixture = GitFixture(self)
        fixture.write("old_settings.py", "aws_access_key_id = \"" + fake_aws_key() + "\"" + chr(10))
        first = fixture.commit("add old settings with secret")
        (fixture.root / "old_settings.py").unlink()
        second = fixture.commit("remove old settings")
        self.assertNotEqual(first, second)
        completed = run_cli(fixture.root, out_dir=self.out)
        self.assertEqual(completed.returncode, 1)
        report, _ = read_reports(self.out)
        history = [item for item in report["findings"] if item["scope"] == "history"]
        self.assertTrue(any(item["rule"] == "history_aws_access_key_id" for item in history))
        entry = next(item for item in history if item["rule"] == "history_aws_access_key_id")
        self.assertEqual(entry["classification"], "ROTATE")
        self.assertTrue(entry["git_history_only"])
        self.assertIn(entry["commit"][:12], [c[:12] for c in entry["evidence"]["commits"]])


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

class TestBounds(AuditTestBase):
    def test_limits_are_enforced_and_reported(self):
        fixture = GitFixture(self)
        for index in range(12):
            fixture.write("src/module_" + str(index).zfill(2) + ".py",
                          "value_" + str(index) + " = \"" + ("x" * 160) + "\"" + chr(10))
        fixture.write("aa_big.py", "y" * 400)
        fixture.commit("many files")
        completed = run_cli(fixture.root, "--max-files", "3", "--max-file-bytes", "64",
                            "--max-git-commits", "1", out_dir=self.out)
        report, markdown = read_reports(self.out)
        summary = report["summary"]
        self.assertLessEqual(summary["tracked_scanned"], 3)
        self.assertGreaterEqual(summary["oversize_skipped"], 1)
        self.assertGreaterEqual(summary["files_skipped_due_to_bounds"], 1)
        self.assertLessEqual(report["git"]["commits_scanned"], 1)
        self.assertIn("max_file_bytes=64", markdown.replace(" ", " "))

    def test_finding_cap_is_bounded(self):
        fixture = GitFixture(self)
        for index in range(8):
            fixture.write("secrets/file_" + str(index) + ".py",
                          "token_" + str(index) + " = \"" + fake_github_token() + "\"" + chr(10))
        fixture.commit("many secrets")
        completed = run_cli(fixture.root, "--max-findings", "2", out_dir=self.out)
        report, _ = read_reports(self.out)
        self.assertLessEqual(report["summary"]["findings_total"], 2)
        self.assertTrue(report["summary"]["findings_truncated"])


# ---------------------------------------------------------------------------
# Read-only and no-network guarantees
# ---------------------------------------------------------------------------

class TestReadOnly(AuditTestBase):
    def test_scan_does_not_modify_repository_or_git_state(self):
        fixture = GitFixture(self)
        build_secret_and_artifact_fixture(fixture)
        self.git_status = fixture.git("status", "--porcelain").stdout
        before_tree = snapshot_tree(fixture.root)
        before_head = fixture.git("rev-parse", "HEAD").stdout.strip()
        before_index = hashlib.sha256((fixture.root / ".git" / "index").read_bytes()).hexdigest()
        run_cli(fixture.root, out_dir=self.out)
        after_tree = snapshot_tree(fixture.root)
        after_head = fixture.git("rev-parse", "HEAD").stdout.strip()
        after_index = hashlib.sha256((fixture.root / ".git" / "index").read_bytes()).hexdigest()
        self.assertEqual(before_tree, after_tree, "audit mutated the working tree")
        self.assertEqual(before_head, after_head, "audit changed HEAD")
        self.assertEqual(before_index, after_index, "audit modified the Git index")
        self.assertEqual(fixture.git("status", "--porcelain").stdout, self.git_status)
        self.assertFalse((fixture.root / ".git" / "index.lock").exists())

    def test_no_write_mode_creates_no_files(self):
        fixture = GitFixture(self)
        build_secret_and_artifact_fixture(fixture)
        before = snapshot_tree(fixture.root)
        completed = run_cli(fixture.root)
        self.assertIn("gate=", completed.stdout)
        self.assertEqual(before, snapshot_tree(fixture.root))
        self.assertFalse((fixture.root / ".workspace" / "build").exists())

    def test_static_no_network_no_destructive_commands(self):
        source = SCRIPT.read_text(encoding="utf-8")
        forbidden_imports = ("import socket", "import urllib", "import http.client",
                             "import requests", "import httpx", "import aiohttp",
                             "urlopen(", "socket.socket")
        for token in forbidden_imports:
            self.assertNotIn(token, source, "network primitive in audit: " + token)
        forbidden_actions = ("os.remove(", "os.unlink(", "shutil.rmtree", "shutil.move",
                             ".unlink(", "git push", "git commit", "git tag",
                             "git remote add", "gh release", "git reset", "git clean",
                             "git update-ref")
        for token in forbidden_actions:
            self.assertNotIn(token, source, "destructive/Git-write primitive: " + token)
        self.assertNotIn("shutil", source)
        self.assertEqual(
            audit.GIT_READONLY_COMMANDS,
            frozenset({"rev-parse", "ls-files", "log", "rev-list", "show", "cat-file", "version"}),
        )
        with self.assertRaises(ValueError):
            audit.git_read(Path("."), ["push"])
        with self.assertRaises(ValueError):
            audit.git_read(Path("."), ["commit", "-m", "x"])

    def test_scan_runs_with_network_sockets_blocked(self):
        fixture = GitFixture(self)
        fixture.write("README.md", "clean repository" + chr(10))
        fixture.commit("clean")
        with mock.patch("socket.socket", side_effect=AssertionError("network call attempted")):
            report = audit.audit_release(fixture.root)
        self.assertIn("summary", report)


# ---------------------------------------------------------------------------
# Clean repository and untracked local-only trees
# ---------------------------------------------------------------------------

class TestCleanAndLocalOnlyTrees(AuditTestBase):
    def test_clean_repository_is_clear(self):
        fixture = GitFixture(self)
        fixture.write("README.md", "A clean repository with no secrets." + chr(10))
        fixture.write("app/module.py", "def add(a, b):" + chr(10) + "    return a + b" + chr(10))
        fixture.commit("clean")
        completed = run_cli(fixture.root, out_dir=self.out)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        report, markdown = read_reports(self.out)
        self.assertEqual(report["summary"]["blocking_count"], 0)
        self.assertEqual(report["summary"]["classification_counts"]["ROTATE"], 0)
        self.assertEqual(report["summary"]["classification_counts"]["EXCLUDE-FROM-UPLOAD"], 0)
        self.assertIn("CLEAR", markdown)

    def test_present_untracked_local_trees_are_reported_not_blocking(self):
        fixture = GitFixture(self)
        fixture.write("README.md", "clean" + chr(10))
        fixture.commit("clean")
        (fixture.root / "data").mkdir()
        (fixture.root / "data" / "nl_coding_agent.sqlite3").write_bytes(b"SQLite format 3" + bytes([0]))
        (fixture.root / ".workspace" / "logs").mkdir(parents=True)
        (fixture.root / ".workspace" / "logs" / "run.log").write_text("log line", encoding="utf-8")
        (fixture.root / "python").mkdir()
        (fixture.root / "python" / "python.exe").write_text("binary", encoding="utf-8")
        completed = run_cli(fixture.root, out_dir=self.out)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        report, markdown = read_reports(self.out)
        present = [item for item in report["findings"] if item["scope"] == "present-untracked"]
        paths = {item["path"] for item in present}
        for expected in ("data", ".workspace", "python"):
            self.assertIn(expected, paths)
        self.assertTrue(all(item["classification"] == "EXCLUDE-FROM-UPLOAD" for item in present))
        self.assertEqual(report["summary"]["blocking_count"], 0)
        self.assertIn("Present-but-untracked local-only trees", markdown)


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------

class TestOutputContract(AuditTestBase):
    def test_reports_have_schema_redaction_and_authorization_notes(self):
        fixture = GitFixture(self)
        fixture.write("README.md", "clean" + chr(10))
        fixture.commit("clean")
        completed = run_cli(fixture.root, out_dir=self.out)
        self.assertEqual(completed.returncode, 0)
        report, markdown = read_reports(self.out)
        for key in ("schema_version", "tool", "tool_version", "generated_at", "root",
                    "git", "bounds", "summary", "redaction_note",
                    "authorization_note", "findings", "limitations"):
            self.assertIn(key, report)
        self.assertEqual(report["tool"], "audit_release_secrets.py")
        self.assertEqual(report["schema_version"], 1)
        self.assertIn("Full secrets are never written", report["redaction_note"])
        self.assertIn("no upload", report["authorization_note"].lower())
        self.assertIn("owner authorization", markdown.lower())
        self.assertIn("Read-only audit", markdown)


class TestFixtureAllowlist(AuditTestBase):
    """Documented synthetic redaction fixtures are REVIEW, never blocking."""

    FIXTURE_VALUE = "sk-TESTSECRET1234567890"

    def test_allowlist_hashes_match_documented_fixtures(self):
        self.assertIn(
            hashlib.sha256(self.FIXTURE_VALUE.encode("utf-8")).hexdigest(),
            audit.TEST_FIXTURE_SECRET_ALLOWLIST,
        )

    def test_allowlisted_value_in_tests_is_review_not_rotate(self):
        collector = audit.Collector(50)
        line = "SECRET_SK = \"" + self.FIXTURE_VALUE + "\"" + chr(10)
        audit._match_secret_rules(line, "tests/test_diagnostic_report.py", 32, collector, "tracked")
        tokens = [item for item in collector.items if item["rule"] == "openai_key"]
        self.assertTrue(tokens)
        self.assertTrue(all(item["classification"] == audit.REVIEW for item in tokens))

    def test_same_value_outside_tests_remains_blocking(self):
        collector = audit.Collector(50)
        line = "SECRET_SK = \"" + self.FIXTURE_VALUE + "\"" + chr(10)
        audit._match_secret_rules(line, "nl_coding_agent/app.py", 1, collector, "tracked")
        tokens = [item for item in collector.items if item["rule"] == "openai_key"]
        self.assertTrue(tokens)
        self.assertTrue(all(item["classification"] == audit.ROTATE for item in tokens))


if __name__ == "__main__":
    unittest.main()

"""Tests for the opt-in redacted diagnostic report generator (NL-BP-161).

The fixtures deliberately contain API keys, tokens, private-key material, personal absolute
paths, cloud identifiers, project content and database rows so the redaction and
"not collected" guarantees are proven, not just claimed.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnostic_report.py"
spec = importlib.util.spec_from_file_location("diagnostic_report", SCRIPT)
diag = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(diag)

BS = chr(92)
NL = chr(10)

SECRET_SK = "sk-TESTSECRET1234567890"
SECRET_GH = "ghp_" + ("A" * 30)
SECRET_AWS = "AKIA" + ("B" * 16)
SECRET_KEY_BLOCK = (
    "-----BEGIN RSA PRIVATE KEY-----" + NL
    + "MIIBOgIBAAJBAKfakefakefakefakefake" + NL
    + "-----END RSA PRIVATE KEY-----"
)
PROJECT_SECRET = "TOPSECRET-PROJECT-CONTENT"
DB_SECRET = "sk-DBSECRET9999999999"
ARN = "arn:aws:iam::123456789012:user/someuser"
GUID = "123e4567-e89b-12d3-a456-426614174000"
HOME_USER = "tester"
WINDOWS_PROJECT = "C:" + BS + "Users" + BS + HOME_USER + BS + "Private Project"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class DiagnosticFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = self.base / "install"
        self.home = self.base / "home" / HOME_USER
        self.home.mkdir(parents=True)
        self.pub = self.base / "public"

        write(self.root / "nl_agent.py", "print('entry')" + NL)
        write(self.root / "README.md", "# NL Coding Agent" + NL)
        write(self.root / "pyproject.toml",
              "[project]" + NL + "name = 'nl-coding-agent'" + NL + "version = '0.9.9'" + NL)
        write(self.root / "nl_coding_agent" / "core" / "version.py",
              "APP_VERSION = '9.9.9'" + NL + "__version__ = APP_VERSION" + NL)
        release = {
            "version": "9.9.9",
            "archive": {
                "name": "nl-coding-agent-9.9.9-source.zip",
                "sha256": "ab" * 32,
                "size": 4242,
                "file_count": 7,
            },
        }
        write(self.root / "release-manifest.json", json.dumps(release))
        models = NL.join([
            "ollama:",
            "  base_url: \"http://127.0.0.1:11434\"",
            "providers:",
            "  ollama:",
            "    enabled: true",
            "    kind: ollama",
            "  lm_studio:",
            "    enabled: false",
            "    kind: openai_compatible",
            "roles:",
            "  developer:",
            "    model: \"ollama/model-" + SECRET_SK + "\"",
            "  fallback_cloud:",
            "    enabled: false",
            "    model: \"ollama/gpt-oss:120b-cloud\"",
            "  reviewer:",
            "    model: \"ollama/qwen3.5:9b\"",
        ]) + NL
        write(self.root / "config" / "models.yaml", models)
        voicebridge = NL.join([
            "project:",
            "  name: \"Beta " + ARN + " " + GUID + "\"",
            "  root: '" + WINDOWS_PROJECT + "'",
            "  protected_paths:",
            "    - '" + WINDOWS_PROJECT + BS + "backup.rar'",
            "  docs_globs:",
            "    - \"*.md\"",
        ]) + NL
        write(self.root / "config" / "voicebridge.yaml", voicebridge)
        write(self.root / "secret_project" / "notes.txt",
              "private notes: " + PROJECT_SECRET + " token " + SECRET_GH + NL)
        db = self.root / "data" / "nl_coding_agent.sqlite3"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("CREATE TABLE secrets (value TEXT)")
            conn.execute("INSERT INTO secrets VALUES (?)", (DB_SECRET,))
            conn.commit()
        finally:
            conn.close()

    def report(self, **kwargs):
        environ = kwargs.pop("environ", {})
        return diag.build_report(root=self.root, home=self.home, environ=environ, **kwargs)

    def report_json(self, report=None) -> str:
        return diag.render_json(report if report is not None else self.report())

    def report_markdown(self, report=None) -> str:
        return diag.render_markdown(report if report is not None else self.report())


class TestNoNetworkAndOptIn(DiagnosticFixture):
    def test_script_has_no_network_or_process_imports(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {
            "socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib",
            "smtplib", "paramiko", "subprocess", "webbrowser",
        }
        self.assertEqual(imported & forbidden, set())
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("urlopen", source)
        self.assertNotIn("requests.", source)

    def test_report_builds_with_socket_blocked(self):
        with mock.patch("socket.socket", side_effect=AssertionError("network used")):
            report = self.report()
        self.assertEqual(report["kind"], diag.REPORT_KIND)

    def test_privacy_block_is_explicit(self):
        privacy = self.report()["privacy"]
        self.assertTrue(privacy["opt_in"])
        self.assertFalse(privacy["uploaded"])
        self.assertFalse(privacy["telemetry"])
        self.assertFalse(privacy["network_used"])
        self.assertTrue(privacy["manual_attachment_only"])
        self.assertTrue(privacy["redacted"])
        joined = " ".join(privacy["not_collected"]).lower()
        self.assertIn("database", joined)
        self.assertIn("project", joined)

    def test_cli_requires_an_explicit_mode(self):
        with mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                diag.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_rejects_dry_run_and_output_together(self):
        with mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                diag.main(["--dry-run", "--output", str(self.pub / "r.md")])
        self.assertEqual(raised.exception.code, 2)

    def test_dry_run_writes_nothing(self):
        before = sorted(p.relative_to(self.base).as_posix() for p in self.base.rglob("*"))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = diag.main(["--dry-run", "--format", "json", "--root", str(self.root)])
        after = sorted(p.relative_to(self.base).as_posix() for p in self.base.rglob("*"))
        self.assertEqual(code, 0)
        self.assertEqual(before, after)
        self.assertIn('"kind": "nl-coding-agent-diagnostic-report"', buffer.getvalue())


class TestRedaction(DiagnosticFixture):
    def test_config_secret_is_redacted(self):
        text = self.report_json() + self.report_markdown()
        self.assertNotIn(SECRET_SK, text)
        self.assertNotIn("TESTSECRET", text)
        self.assertIn("<redacted>", text)

    def test_environment_allowlist_only(self):
        report = self.report(environ={
            "OPENAI_API_KEY": SECRET_SK,
            "GITHUB_TOKEN": SECRET_GH,
            "RANDOM_UNKNOWN_VAR": SECRET_AWS,
            "NL_DEVELOPER_MODEL": "ollama/" + SECRET_SK,
            "OLLAMA_HOST": "http://user:pass@127.0.0.1:11434",
        })
        environment = report["environment"]
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("RANDOM_UNKNOWN_VAR", environment)
        self.assertIn("NL_DEVELOPER_MODEL", environment)
        self.assertIn("OLLAMA_HOST", environment)
        text = json.dumps(report)
        self.assertNotIn(SECRET_SK, text)
        self.assertNotIn("TESTSECRET", text)
        self.assertNotIn("user:pass", text)

    def test_home_username_and_windows_paths_are_redacted(self):
        text = self.report_json() + self.report_markdown()
        self.assertNotIn(HOME_USER, text)
        self.assertNotIn("Private Project", text)
        self.assertNotIn(str(self.home), text)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("C:" + BS, text)
        self.assertEqual(diag.redact_text(WINDOWS_PROJECT, self.home), diag.PATH_MARK)
        self.assertEqual(diag.redact_text("K:" + BS + "AI" + BS + "other", self.home), diag.PATH_MARK)
        self.assertEqual(diag.redact_text(str(self.home) + BS + "project", self.home), diag.HOME_MARK)

    def test_cloud_identifiers_are_redacted(self):
        text = self.report_json() + self.report_markdown()
        self.assertNotIn(ARN, text)
        self.assertNotIn("arn:aws", text)
        self.assertNotIn(GUID, text)
        self.assertNotIn("123e4567", text)

    def test_redact_text_handles_credentials_and_urls(self):
        home = self.home
        self.assertNotIn(SECRET_SK, diag.redact_text("key=" + SECRET_SK, home))
        self.assertNotIn(SECRET_GH, diag.redact_text("token: " + SECRET_GH, home))
        self.assertNotIn(SECRET_AWS, diag.redact_text("aws " + SECRET_AWS, home))
        self.assertNotIn("user:pass", diag.redact_text("http://user:pass@example.com/x", home))
        self.assertNotIn("MIIBOgIBAAJBAK", diag.redact_text(SECRET_KEY_BLOCK, home))
        self.assertNotIn("Bearer abcdefghijklmnopqrstuvwxyz", diag.redact_text(
            "Bearer abcdefghijklmnopqrstuvwxyz012345", home))
        self.assertNotIn(ARN, diag.redact_text("id " + ARN, home))
        self.assertNotIn(GUID, diag.redact_text("id " + GUID, home))
        self.assertNotIn(HOME_USER, diag.redact_text("path " + WINDOWS_PROJECT, home))


class TestNotCollected(DiagnosticFixture):
    def test_project_content_is_not_included(self):
        text = self.report_json() + self.report_markdown()
        self.assertNotIn(PROJECT_SECRET, text)
        self.assertNotIn("secret_project", text)
        self.assertNotIn("private notes", text)

    def test_database_rows_are_not_read_or_included(self):
        report = self.report()
        database = report["database"]
        self.assertTrue(database["present"])
        self.assertFalse(database["content_collected"])
        text = self.report_json(report) + self.report_markdown(report)
        self.assertNotIn(DB_SECRET, text)
        self.assertNotIn("DBSECRET", text)

    def test_checksums_are_limited_to_allowlisted_metadata_files(self):
        report = self.report()
        paths = [item["path"] for item in report["installation"]["checksums"]["files"]]
        self.assertTrue(paths)
        for item in paths:
            self.assertIn(item, diag.CHECKSUM_CANDIDATES)


class TestReportContent(DiagnosticFixture):
    def test_application_version_and_install_method(self):
        report = self.report()
        self.assertEqual(report["application"]["version"], "9.9.9")
        self.assertEqual(report["application"]["install_method"], "release-candidate")
        self.assertTrue(report["application"]["entry_point_present"])

    def test_checksum_matches_real_file_hash(self):
        report = self.report()
        rows = {item["path"]: item for item in report["installation"]["checksums"]["files"]}
        expected = hashlib.sha256((self.root / "pyproject.toml").read_bytes()).hexdigest()
        self.assertEqual(rows["pyproject.toml"]["sha256"], expected)
        self.assertEqual(rows["pyproject.toml"]["size"], (self.root / "pyproject.toml").stat().st_size)

    def test_release_manifest_package_checksum_is_reported(self):
        summary = self.report()["installation"]["release"]["release_manifest"]
        self.assertEqual(summary["archive"]["sha256"], "ab" * 32)
        self.assertEqual(summary["archive"]["size"], 4242)
        self.assertEqual(summary["version"], "9.9.9")

    def test_configuration_summary_structure(self):
        config = self.report()["configuration"]
        roles = [row["role"] for row in config["models"]["roles"]]
        self.assertEqual(roles, ["developer", "fallback_cloud", "reviewer"])
        providers = {row["name"]: row["enabled"] for row in config["models"]["providers"]}
        self.assertTrue(providers["ollama"])
        self.assertFalse(providers["lm_studio"])
        self.assertTrue(config["models"]["cloud_fallback_configured"])
        self.assertFalse(config["models"]["cloud_fallback_enabled"])
        self.assertTrue(config["voicebridge"]["present"])
        self.assertTrue(config["voicebridge"]["external_root_configured"])
        self.assertEqual(config["voicebridge"]["protected_paths_count"], 1)

    def test_capability_probes_are_presence_only(self):
        capabilities = self.report()["capabilities"]
        self.assertEqual(
            sorted(capabilities["modules_available"]), sorted(diag.CAPABILITY_MODULES))
        self.assertEqual(
            sorted(capabilities["executables_on_path"]), sorted(diag.CAPABILITY_EXECUTABLES))
        notes = " ".join(capabilities["probe_notes"]).lower()
        self.assertIn("manual-pending", notes)
        self.assertIn("no network request", notes)

    def test_platform_block(self):
        platform_info = self.report()["platform"]
        self.assertIn("system", platform_info)
        self.assertIn("machine", platform_info)
        self.assertIn("python", platform_info)

    def test_report_is_deterministic(self):
        first = self.report()
        second = self.report()
        self.assertEqual(first, second)
        self.assertEqual(diag.render_json(first), diag.render_json(second))
        self.assertEqual(diag.render_markdown(first), diag.render_markdown(second))

    def test_no_timestamps_in_report(self):
        text = self.report_json()
        self.assertNotIn("created_at", text)
        self.assertNotIn("generated_at", text)
        self.assertIsNone(re.search("[0-9]{4}-[0-9]{2}-[0-9]{2}T", text))

    def test_json_is_valid_and_sorted(self):
        text = self.report_json()
        parsed = json.loads(text)
        self.assertEqual(parsed["tool"]["schema_version"], diag.SCHEMA_VERSION)
        self.assertEqual(text, json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False) + NL)

    def test_markdown_sections_and_no_secrets(self):
        text = self.report_markdown()
        for heading in ("## Summary", "## Package checksums", "## Configuration summary",
                        "## Capability probes", "## Database", "## Not collected", "## How to share"):
            self.assertIn(heading, text)
        self.assertNotIn(SECRET_SK, text)
        self.assertNotIn(PROJECT_SECRET, text)
        self.assertNotIn(DB_SECRET, text)
        self.assertNotIn(ARN, text)


class TestBoundsAndModes(DiagnosticFixture):
    def test_checksum_file_bound(self):
        report = self.report(max_checksum_files=1)
        checksums = report["installation"]["checksums"]
        self.assertEqual(checksums["files_hashed"], 1)
        self.assertTrue(checksums["truncated"])
        self.assertGreaterEqual(checksums["files_skipped"], 1)

    def test_oversized_metadata_file_is_skipped(self):
        big = self.root / "release-manifest.json"
        big.write_bytes(b"{" + (b"x" * (diag.MAX_CHECKSUM_BYTES + 64)) + b"}")
        report = self.report()
        checksums = report["installation"]["checksums"]
        paths = [item["path"] for item in checksums["files"]]
        self.assertNotIn("release-manifest.json", paths)
        self.assertGreaterEqual(checksums["files_skipped"], 1)

    def test_install_method_detection(self):
        source_root = self.base / "source"
        write(source_root / "pyproject.toml", "[project]" + NL + "version = '1.0.0'" + NL)
        self.assertEqual(diag.build_report(root=source_root, home=self.home, environ={})[
            "application"]["install_method"], "source-checkout")
        bare_root = self.base / "bare"
        bare_root.mkdir()
        self.assertEqual(diag.build_report(root=bare_root, home=self.home, environ={})[
            "application"]["install_method"], "unknown")

    def test_version_fallback_to_pyproject(self):
        source_root = self.base / "source2"
        write(source_root / "pyproject.toml",
              "[project]" + NL + "name = 'x'" + NL + "version = '0.7.7'" + NL)
        report = diag.build_report(root=source_root, home=self.home, environ={})
        self.assertEqual(report["application"]["version"], "0.7.7")


class TestCli(DiagnosticFixture):
    def test_output_writes_redacted_markdown(self):
        output = self.pub / "nested" / "beta-diagnostic.md"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = diag.main(["--output", str(output), "--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertTrue(output.is_file())
        content = output.read_text(encoding="utf-8")
        self.assertIn("## Summary", content)
        self.assertNotIn(SECRET_SK, content)
        self.assertNotIn(SECRET_GH, content)
        self.assertNotIn(PROJECT_SECRET, content)
        self.assertNotIn(DB_SECRET, content)
        self.assertNotIn(ARN, content)
        self.assertNotIn("C:" + BS, content)

    def test_output_refuses_to_overwrite_without_flag(self):
        output = self.pub / "beta-diagnostic.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("existing" + NL, encoding="utf-8")
        with mock.patch("sys.stderr", new=io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = diag.main(["--output", str(output), "--root", str(self.root)])
        self.assertEqual(code, 1)
        self.assertEqual(output.read_text(encoding="utf-8"), "existing" + NL)
        with contextlib.redirect_stdout(io.StringIO()):
            code = diag.main(["--output", str(output), "--overwrite", "--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn("## Summary", output.read_text(encoding="utf-8"))

    def test_json_output_format(self):
        output = self.pub / "beta-diagnostic.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = diag.main(["--format", "json", "--output", str(output), "--root", str(self.root)])
        self.assertEqual(code, 0)
        parsed = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(parsed["kind"], diag.REPORT_KIND)
        self.assertFalse(parsed["privacy"]["uploaded"])


if __name__ == "__main__":
    unittest.main()

"""AppServices document_ingest tests: temp dirs, fake reader/extractor, no network."""
from __future__ import annotations
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
import sys
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class DocumentIngestServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["NL_DATA_DIR"] = str(Path(self._tmp.name) / "data")
        from nl_coding_agent.app.services import AppServices
        self.services = AppServices()

    def tearDown(self):
        try:
            self.services._db.close()
        except Exception:
            pass
        os.environ.pop("NL_DATA_DIR", None)

    def _project(self):
        root = Path(self._tmp.name) / "project"
        _write(root / "README.md", "# Project\n\nOverview.\n")
        _write(root / "docs" / "architecture.md", "# Architecture\n")
        _write(root / "specs" / "spec.md", "# Spec\n")
        _write(root / "data" / "private.md", "# private\n")
        return root

    def test_consent_project_summary_untrusted_and_no_execution(self):
        denied = self.services.document_ingest(project_root=self._project())
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["outcome"], "consent_required")
        result = self.services.document_ingest(project_root=self._project(), consent=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["outcome"], "completed")
        self.assertGreaterEqual(result["counts"]["documents"], 3)
        self.assertEqual(result["source_kinds"]["project"], result["counts"]["documents"])
        self.assertTrue(result["untrusted"])
        self.assertFalse(result["executed"])
        self.assertTrue(result["untrusted_marker"])
        paths = {doc["path"] for doc in result["documents"]}
        self.assertIn("README.md", paths)
        self.assertIn("docs/architecture.md", paths)
        self.assertNotIn("data/private.md", paths)
        self.assertTrue(all("text" not in doc for doc in result["documents"]))
        self.assertTrue(any(item["authority_candidates"] for item in result["authority_candidates"]))
        json.dumps(result)

    def test_explicit_file_archive_bounds_and_unsafe_archive(self):
        root = self._project()
        result = self.services.document_ingest(
            paths=[root / "README.md"], consent=True,
            limits={"max_files": 1, "max_total_bytes": 1000000})
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["documents"], 1)
        bounded = self.services.document_ingest(
            project_root=root, consent=True, limits={"max_files": 1})
        self.assertTrue(bounded["bounded"])
        self.assertFalse(bounded["complete"])

        import zipfile
        safe = Path(self._tmp.name) / "docs.zip"
        with zipfile.ZipFile(safe, "w") as zf:
            zf.writestr("guide.md", "# Guide\n")
        archive = self.services.document_ingest(archives=[safe], consent=True)
        self.assertTrue(archive["ok"])
        self.assertEqual(archive["documents"][0]["source_kind"], "archive")
        slip = Path(self._tmp.name) / "slip.zip"
        with zipfile.ZipFile(slip, "w") as zf:
            zf.writestr("../evil.md", "# evil\n")
        unsafe = self.services.document_ingest(archives=[slip], consent=True)
        self.assertFalse(unsafe["documents"])
        self.assertTrue(any("traversal" in item["reason"] for item in unsafe["skipped"]))

    def test_pdf_office_fake_and_fail_closed(self):
        pdf = Path(self._tmp.name) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        fake = lambda data, name, kind: {"ok": True, "text": "# Extracted",
                                         "content_type": "text/plain"}
        result = self.services.document_ingest(
            paths=[pdf], consent=True, extractor=fake)
        self.assertTrue(result["ok"])
        self.assertEqual(result["documents"][0]["title"], "Extracted")
        unavailable = self.services.document_ingest(
            paths=[pdf], consent=True,
            extractor=lambda data, name, kind: {"ok": False,
                                                "reason": "optional-extractor-unavailable"})
        self.assertFalse(unavailable["documents"])
        self.assertTrue(any("optional-extractor" in item["reason"]
                            for item in unavailable["skipped"]))

    def test_urls_require_reader_and_injected_reader_succeeds(self):
        result = self.services.document_ingest(
            urls=["https://example.com/doc"], consent=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["outcome"], "unavailable")
        self.assertIn("no implicit network", result["error"]["message"])
        reader = lambda url: {"text": "# Fetched\n\nremote docs", "title": "Fetched",
                              "content_type": "text/plain", "url": url}
        self.services.configure_document_ingest(url_reader=reader)
        result = self.services.document_ingest(
            urls=["https://example.com/doc"], consent=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_kinds"]["url"], 1)
        self.assertTrue(result["documents"][0]["untrusted"])
        self.assertEqual(result["documents"][0]["url"], "https://example.com/doc")

    def test_git_ref_provenance(self):
        repo = Path(self._tmp.name) / "gitrepo"
        repo.mkdir()
        _write(repo / "docs" / "guide.md", "# Guide\n\nCommitted.\n")
        try:
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True,
                           capture_output=True, timeout=30)
            subprocess.run(["git", "-C", str(repo), "config", "user.email",
                            "test@example.invalid"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                           capture_output=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "docs"],
                           check=True, capture_output=True)
        except (OSError, subprocess.SubprocessError) as exc:
            self.skipTest("git unavailable: " + str(exc))
        result = self.services.document_ingest(
            project_root=repo, git_ref="HEAD", consent=True)
        self.assertTrue(result["ok"])
        doc = next(item for item in result["documents"] if item["path"] == "docs/guide.md")
        self.assertEqual(doc["source_kind"], "git")
        self.assertEqual(doc["git_ref"], "HEAD")
        self.assertEqual(len(doc["git_commit"]), 40)


if __name__ == "__main__":
    unittest.main()

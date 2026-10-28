"""Tests for the local research knowledge store (temp NL_DATA_DIR, no network)."""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.research.store import (  # noqa: E402
    MAX_ANSWER_CHARS,
    MAX_EXCERPT_CHARS,
    ResearchStore,
    ResearchStoreError,
)


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name) / "data"
        self.data_dir.mkdir()
        self._old_env = os.environ.get("NL_DATA_DIR")
        os.environ["NL_DATA_DIR"] = str(self.data_dir)
        self.store = ResearchStore()

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("NL_DATA_DIR", None)
        else:
            os.environ["NL_DATA_DIR"] = self._old_env

    def source(self, **overrides):
        values = dict(canonical_url="https://example.com/doc", excerpt="public excerpt",
                      title="Doc", provider="fake-provider", project_id=1,
                      mission_id=2, task_id=3, confidence=0.7,
                      metadata={"kind": "docs"}, retrieved_at="2026-01-01T00:00:00Z")
        values.update(overrides)
        return self.store.save_source(**values)

    def finding(self, **overrides):
        values = dict(question="What is X?", answer="X is bounded evidence",
                      confidence=0.6, project_id=1, mission_id=2, task_id=3)
        values.update(overrides)
        return self.store.save_finding(**values)


class SchemaTests(StoreTestCase):
    def test_additive_schema_is_idempotent_and_restart_persists(self):
        tables = self.store.ensure_schema()
        self.assertEqual(tables, ("research_citations", "research_conflicts",
                                  "research_finding_attachments",
                                  "research_findings", "research_sources"))
        self.assertEqual(self.store.ensure_schema(), tables)
        saved = self.source()
        finding = self.finding(source_ids=[saved["id"]])
        reopened = ResearchStore()
        self.assertEqual(reopened.ensure_schema(), tables)
        self.assertEqual(reopened.counts()["research_sources"], 1)
        self.assertEqual(reopened.counts()["research_findings"], 1)
        self.assertEqual(reopened.get_source(saved["id"])["canonical_url"],
                         "https://example.com/doc")
        self.assertEqual(reopened.get_finding(finding["id"])["question"], "What is X?")
        self.assertTrue((self.data_dir / "nl_coding_agent.sqlite3").is_file())

    def test_legacy_tables_are_untouched(self):
        conn = sqlite3.connect(str(self.data_dir / "nl_coding_agent.sqlite3"))
        try:
            names = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        for expected in ("projects", "missions", "tasks", "events"):
            self.assertIn(expected, names)


class SourceTests(StoreTestCase):
    def test_save_dedupe_canonical_url_and_refresh(self):
        first = self.source()
        self.assertTrue(first["created"])
        again = self.source()
        self.assertEqual(again["id"], first["id"])
        self.assertTrue(again["deduped"])
        self.assertFalse(again["updated"])
        # fragment/default port are canonicalised away
        other = self.source(canonical_url="HTTPS://Example.com:443/doc#section")
        self.assertEqual(other["id"], first["id"])
        changed = self.source(excerpt="new bounded excerpt", title="Doc v2")
        self.assertEqual(changed["id"], first["id"])
        self.assertTrue(changed["updated"])
        row = self.store.get_source(first["id"])
        self.assertEqual(row["excerpt"], "new bounded excerpt")
        self.assertEqual(row["title"], "Doc v2")
        self.assertEqual(row["metadata"], {"kind": "docs"})
        self.assertEqual(row["redirect_chain"], ["https://example.com/doc"])
        self.assertTrue(row["content_sha256"])

    def test_sources_reject_unsafe_or_wholesale_content(self):
        with self.assertRaises(ResearchStoreError):
            self.source(canonical_url="https://user:secret@example.com/doc")
        with self.assertRaises(ResearchStoreError):
            self.source(canonical_url="javascript:alert(1)")
        with self.assertRaises(ResearchStoreError):
            self.source(canonical_url="ftp://example.com/doc")
        with self.assertRaises(ResearchStoreError):
            self.source(excerpt="x" * (MAX_EXCERPT_CHARS + 1))
        with self.assertRaises(ResearchStoreError):
            self.source(metadata={"api_token": "secret"})
        with self.assertRaises(ResearchStoreError):
            self.source(metadata={"authorization": "Bearer value"})
        with self.assertRaises(ResearchStoreError):
            self.source(confidence=1.5)
        with self.assertRaises(ResearchStoreError):
            self.source(project_id=0)

    def test_list_search_isolation_and_bounds(self):
        self.source(canonical_url="https://example.com/one", excerpt="alpha project one",
                    project_id=1)
        self.source(canonical_url="https://example.com/two", excerpt="beta project two",
                    project_id=2, mission_id=None, task_id=None)
        self.assertEqual(len(self.store.list_sources(project_id=1)), 1)
        self.assertEqual(len(self.store.list_sources(project_id=2)), 1)
        self.assertEqual(len(self.store.search_sources("alpha")), 1)
        self.assertEqual(len(self.store.search_sources("beta", project_id=1)), 0)
        many = []
        for index in range(5):
            many.append(self.source(canonical_url="https://example.com/many-" + str(index),
                                    excerpt="bounded excerpt " + str(index)))
        self.assertLessEqual(len(self.store.list_sources(limit=2)), 2)
        self.assertLessEqual(len(self.store.list_sources(limit=10_000)), 200)
        first_page = self.store.list_sources(limit=2, offset=0)
        second_page = self.store.list_sources(limit=2, offset=2)
        self.assertEqual(len(first_page), 2)
        self.assertEqual(len(second_page), 2)
        self.assertNotEqual(first_page[0]["id"], second_page[0]["id"])

    def test_staleness_refresh_and_expiry(self):
        saved = self.source(retrieved_at="2020-01-01T00:00:00Z")
        stale = self.store.stale_sources(now="2026-01-01T00:00:00Z", max_age_days=30)
        self.assertEqual([row["id"] for row in stale], [saved["id"]])
        self.assertTrue(self.store.mark_source_stale(saved["id"], "outdated"))
        row = self.store.get_source(saved["id"])
        self.assertTrue(row["stale"])
        self.assertEqual(row["stale_reason"], "outdated")
        refreshed = self.store.refresh_source(saved["id"], excerpt="fresh excerpt")
        self.assertFalse(refreshed["stale"])
        self.assertIsNone(refreshed["stale_reason"])
        self.assertEqual(refreshed["excerpt"], "fresh excerpt")
        old = self.source(canonical_url="https://example.com/old",
                          retrieved_at="2019-01-01T00:00:00Z")
        marked = self.store.mark_expired(now="2026-01-01T00:00:00Z", max_age_days=90)
        self.assertGreaterEqual(marked, 1)
        self.assertTrue(self.store.get_source(old["id"])["stale"])
        finding = self.finding()
        self.assertTrue(self.store.mark_finding_stale(finding["id"], "needs refresh"))
        self.assertTrue(self.store.get_finding(finding["id"])["stale"])

    def test_content_hash_index_and_dedupe(self):
        saved = self.source(excerpt="same evidence")
        digest = self.store.get_source(saved["id"])["content_sha256"]
        matches = self.store.find_by_content_hash(digest)
        self.assertEqual([row["id"] for row in matches], [saved["id"]])
        self.assertEqual(self.store.save_source(
            "https://another.example.com/page", excerpt="same evidence")["id"] != saved["id"], True)


class FindingCitationTests(StoreTestCase):
    def test_findings_dedupe_and_isolation(self):
        one = self.finding()
        again = self.finding()
        self.assertEqual(again["id"], one["id"])
        self.assertTrue(again["deduped"])
        other = self.finding(project_id=2, mission_id=None, task_id=None)
        self.assertNotEqual(other["id"], one["id"])
        self.assertEqual(len(self.store.list_findings(project_id=1)), 1)
        self.assertEqual(len(self.store.list_findings(project_id=2)), 1)
        self.assertEqual(len(self.store.list_findings(text="bounded")), 2)
        with self.assertRaises(ResearchStoreError):
            self.finding(question="x" * 501)
        with self.assertRaises(ResearchStoreError):
            self.finding(answer="x" * (MAX_ANSWER_CHARS + 1))

    def test_citations_and_conflicts(self):
        source_a = self.source()
        source_b = self.source(canonical_url="https://example.com/other",
                               excerpt="different evidence")
        finding = self.finding(source_ids=[source_a["id"], source_b["id"]])
        citation = self.store.save_citation(source_a["id"], quote="quoted evidence",
                                            locator="p.1", finding_id=finding["id"])
        self.assertTrue(citation["created"])
        duplicate = self.store.save_citation(source_a["id"], quote="quoted evidence",
                                             locator="p.1", finding_id=finding["id"])
        self.assertEqual(duplicate["id"], citation["id"])
        self.assertTrue(duplicate["deduped"])
        self.assertEqual(len(self.store.list_citations(finding_id=finding["id"])), 1)
        conflict = self.store.record_conflict(finding["id"], source_a["id"], source_b["id"],
                                              "sources disagree on the value")
        again = self.store.record_conflict(finding["id"], source_a["id"], source_b["id"],
                                           "sources disagree on the value")
        self.assertEqual(again["id"], conflict["id"])
        self.assertEqual(len(self.store.list_conflicts(finding_id=finding["id"])), 1)
        with self.assertRaises(ResearchStoreError):
            self.store.save_citation(9999)
        with self.assertRaises(ResearchStoreError):
            self.store.save_citation(source_a["id"], finding_id=9999)
        with self.assertRaises(ResearchStoreError):
            self.store.record_conflict(9999, source_a["id"], source_b["id"], "bad")

    def test_no_secret_or_wholesale_project_content_stored(self):
        source = self.source(excerpt="bounded public excerpt only")
        row = self.store.get_source(source["id"])
        self.assertLessEqual(len(row["excerpt"]), MAX_EXCERPT_CHARS)
        self.assertNotIn("password", row["excerpt"].lower())
        with self.assertRaises(ResearchStoreError):
            self.source(metadata={"password": "hidden"})
        with self.assertRaises(ResearchStoreError):
            self.finding(answer="x" * (MAX_ANSWER_CHARS + 1))
        self.assertEqual(self.store.counts()["research_sources"], 1)



class AttachmentAndRetentionTests(StoreTestCase):
    def _mission(self, *, project_id=None):
        from nl_coding_agent.persistence import database
        conn = database.init_db(self.store.path)
        try:
            with conn:
                if project_id is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO projects (id, name, root) VALUES (?,?,?)",
                        (project_id, "Project " + str(project_id),
                         "C:/tmp/project-" + str(project_id)))
                cursor = conn.execute(
                    "INSERT INTO missions (project_id, title, goal, status) "
                    "VALUES (?,?,?,?)", (project_id, "Mission", "goal", "pending"))
                return int(cursor.lastrowid)
        finally:
            conn.close()

    def test_attach_is_idempotent_revocable_and_preserves_finding(self):
        finding = self.finding(mission_id=None)
        mission = self._mission()
        first = self.store.attach_finding_to_mission(finding["id"], mission,
                                                     source="test", attached_by="tester")
        self.assertTrue(first["created"])
        again = self.store.attach_finding_to_mission(finding["id"], mission)
        self.assertFalse(again["created"])
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(len(self.store.list_mission_findings(mission)), 1)
        self.assertEqual(len(self.store.list_finding_missions(finding["id"])), 1)
        detach = self.store.detach_finding_from_mission(finding["id"], mission)
        self.assertTrue(detach["detached"])
        self.assertIsNotNone(self.store.get_finding(finding["id"]))
        self.assertEqual(self.store.list_mission_findings(mission), [])
        revoked = self.store.list_finding_missions(finding["id"], include_revoked=True)
        self.assertEqual(len(revoked), 1)
        self.assertFalse(revoked[0]["active"])
        reattached = self.store.attach_finding_to_mission(finding["id"], mission)
        self.assertTrue(reattached["created"])
        self.assertNotEqual(reattached["id"], first["id"])
        self.assertIsNotNone(self.store.get_finding(finding["id"]))
        self.assertFalse(self.store.attachment_status(finding["id"], mission)["attached"] is False)

    def test_attach_validates_finding_mission_and_scope_isolation(self):
        finding = self.finding(project_id=1)
        mission = self._mission(project_id=None)
        with self.assertRaises(ResearchStoreError):
            self.store.attach_finding_to_mission(9999, mission)
        with self.assertRaises(ResearchStoreError):
            self.store.attach_finding_to_mission(finding["id"], 9999)
        other_mission = self._mission(project_id=2)
        with self.assertRaises(ResearchStoreError):
            self.store.attach_finding_to_mission(finding["id"], other_mission)

    def test_attachment_survives_restart_and_retention_marks_but_never_deletes(self):
        source = self.source(retrieved_at="2020-01-01T00:00:00Z")
        finding = self.finding(mission_id=None)
        mission = self._mission()
        link = self.store.attach_finding_to_mission(finding["id"], mission)
        citation = self.store.save_citation(source["id"], quote="quote", finding_id=finding["id"])
        conn = self.store._connect()
        try:
            with conn:
                conn.execute("UPDATE research_findings SET created_at=?, updated_at=? WHERE id=?",
                             ("2020-01-01T00:00:00Z", "2020-01-01T00:00:00Z", finding["id"]))
        finally:
            conn.close()
        reopened = ResearchStore()
        self.assertEqual(len(reopened.list_mission_findings(mission)), 1)
        before = reopened.counts()
        result = reopened.apply_retention(now="2026-01-01T00:00:00Z", ttl_days=1)
        self.assertGreaterEqual(result["sources_expired"], 1)
        self.assertGreaterEqual(result["findings_expired"], 1)
        self.assertEqual(result["deleted"], 0)
        self.assertTrue(reopened.get_source(source["id"])["expired"])
        self.assertTrue(reopened.get_finding(finding["id"])["expired"])
        self.assertEqual(reopened.get_source(source["id"])["canonical_url"],
                         "https://example.com/doc")
        self.assertEqual(len(reopened.list_citations(finding_id=finding["id"])), 1)
        self.assertEqual(len(reopened.list_mission_findings(mission)), 1)
        self.assertEqual(reopened.counts()["research_sources"], before["research_sources"])
        self.assertEqual(reopened.counts()["research_findings"], before["research_findings"])
        self.assertEqual(reopened.counts()["research_citations"], before["research_citations"])
        expired = reopened.list_expired()
        self.assertTrue(any(item["kind"] == "source" for item in expired))
        self.assertTrue(any(item["kind"] == "finding" for item in expired))
        summary = reopened.retention_summary()
        self.assertEqual(summary["attachments_total"], 1)
        self.assertFalse(summary["hard_deleted"])
        self.assertFalse(hasattr(reopened, "delete_finding"))
        self.assertFalse(hasattr(reopened, "delete_source"))

class StaticGuardTests(unittest.TestCase):
    def test_store_has_no_network_or_file_content_reads(self):
        source = (REPO_ROOT / "nl_coding_agent" / "research" / "store.py").read_text(
            encoding="utf-8")
        for forbidden in ("import urllib", "import requests", "import socket",
                          "http.client", "import subprocess", "os.system(",
                          "read_text(", ".read_bytes("):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertIn("CREATE TABLE IF NOT EXISTS research_sources", source)
        self.assertIn("research_citations", source)
        self.assertIn("research_findings", source)


if __name__ == "__main__":
    unittest.main()

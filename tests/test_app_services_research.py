"""Tests for the AppServices research facade (offline default + injected fakes)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core import auto_review, permissions  # noqa: E402
from nl_coding_agent.research import fetch  # noqa: E402
from nl_coding_agent.research.providers import (  # noqa: E402
    KnownUrl,
    default_registry,
)
from nl_coding_agent.research.service import ResearchService  # noqa: E402
from nl_coding_agent.research.store import ResearchStore  # noqa: E402

HTML = (b"<html><head><title>Example Title</title></head><body>"
        b"<h1>Heading</h1><p>Hello research world.</p></body></html>")


class FakeFetchTransport:
    def __init__(self):
        self.calls = []

    def open(self, request):
        self.calls.append(request)
        return fetch.TransportResponse(
            status_code=200,
            headers=(("content-type", "text/html; charset=utf-8"),),
            body=HTML)


class PermissionStub:
    def __init__(self, factory=None):
        self.factory = factory or (lambda capability, scope, context:
                                   permissions.Allowed(capability, "allowed by test"))
        self.calls = []

    def __call__(self, capability, scope, context):
        self.calls.append((capability, scope.kind))
        return self.factory(capability, scope, context)


class ReviewStub:
    def __init__(self, outcome=auto_review.OUTCOME_AUTO_APPROVED):
        self.outcome = outcome
        self.calls = []

    def __call__(self, action, profile=None, controls=None):
        self.calls.append(action.capability)
        return {"outcome": self.outcome, "reason": "fake " + self.outcome}


class AppResearchTests(unittest.TestCase):
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

    def fake_service(self, *, permission=None, review=None, known=True):
        permission = permission or PermissionStub()
        review = review or ReviewStub()
        transport = FakeFetchTransport()
        registry = default_registry(known_urls=[
            KnownUrl("https://example.com/docs", "Alpha docs", "alpha known doc")]) \
            if known else default_registry()
        service = ResearchService(
            store=ResearchStore(), registry=registry, fetch_transport=transport,
            permission_checker=permission, auto_reviewer=review,
            profile=auto_review.PROFILE_TRUSTED)
        return service, transport, permission, review

    def test_default_offline_and_no_implicit_network(self):
        status = self.services.research_status()
        self.assertTrue(status["offline"])
        self.assertFalse(status["network_configured"])
        self.assertEqual(status["provider_count"], 0)
        self.assertIn("no explicit network", status["reason"])
        search = self.services.research_search("anything")
        self.assertFalse(search["ok"])
        self.assertTrue(search["offline"])
        self.assertIn("no explicit research network transport", search["error"])
        fetch_result = self.services.research_fetch_read("https://example.com/x")
        self.assertTrue(fetch_result["offline"])
        github = self.services.research_github_lookup(action="repository",
                                                     full_name="owner/repo")
        self.assertTrue(github["offline"])
        hf = self.services.research_huggingface_lookup(action="search_models",
                                                       query="model")
        self.assertTrue(hf["offline"])
        service = self.services._research_service()
        self.assertIsNone(getattr(service, "_fetch_transport", None))
        self.assertIsNone(getattr(service, "_http_transport", None))

    def test_configured_fake_service_search_fetch_provenance_store_citations(self):
        service, transport, permission, review = self.fake_service()
        status = self.services.configure_research(service=service)
        self.assertFalse(status["offline"])
        self.assertTrue(status["network_configured"])
        self.assertEqual(status["provider_count"], 1)
        self.assertEqual(status["providers"][0]["provider_id"], "offline-known-urls")
        search = self.services.research_search("alpha", project_id=1)
        self.assertTrue(search["ok"])
        self.assertEqual(search["outcome"], "allowed")
        self.assertEqual(search["provider_id"], "offline-known-urls")
        self.assertTrue(search["results"])
        self.assertEqual(search["results"][0]["url"], "https://example.com/docs")
        fetch = self.services.research_fetch_read("https://example.com/page",
                                                 project_id=1, mission_id=2,
                                                 task_id=3)
        self.assertTrue(fetch["ok"])
        self.assertEqual(fetch["url"], "https://example.com/page")
        self.assertIn("Hello research world", fetch["text"])
        self.assertTrue(fetch["provenance"])
        self.assertTrue(fetch["redirects"])
        source = self.services._research_service().store.get_source(fetch["source_id"])
        self.assertEqual(source["project_id"], 1)
        self.assertEqual(source["mission_id"], 2)
        self.assertEqual(source["task_id"], 3)
        citations = self.services._research_service().store.list_citations()
        self.assertTrue(citations)
        saved_search = self.services.research_search_saved("Hello", project_id=1)
        self.assertTrue(saved_search["ok"])
        self.assertTrue(saved_search["sources"])
        self.assertTrue(transport.calls)
        capabilities = [call[0] for call in permission.calls]
        self.assertIn(permissions.CAPABILITY_WEB_SEARCH, capabilities)
        self.assertIn(permissions.CAPABILITY_WEB_FETCH, capabilities)

    def test_permission_needed_and_denied_results_are_exposed(self):
        needs = PermissionStub(factory=lambda c, s, ctx: permissions.NeedsApproval(
            c, "human approval for " + c))
        service, _transport, _p, _r = self.fake_service(permission=needs)
        self.services.configure_research(service=service)
        search = self.services.research_search("alpha")
        self.assertFalse(search["ok"])
        self.assertEqual(search["outcome"], "needs_approval")
        self.assertIn("permission_needed", search)
        self.assertIn("human approval", search["permission_needed"])
        denied = PermissionStub(factory=lambda c, s, ctx: permissions.Denied(
            c, "policy denies " + c))
        service2, _t, _p2, _r2 = self.fake_service(permission=denied)
        self.services.configure_research(service=service2)
        fetch = self.services.research_fetch_read("https://example.com/page")
        self.assertFalse(fetch["ok"])
        self.assertEqual(fetch["outcome"], "denied")
        self.assertTrue(fetch["denied"])
        self.assertIn("denies", fetch["reason"].lower())

    def test_auto_review_needs_approval_and_denied_states(self):
        review = ReviewStub(auto_review.OUTCOME_NEEDS_HUMAN_APPROVAL)
        service, _transport, _p, _r = self.fake_service(review=review)
        self.services.configure_research(service=service)
        result = self.services.research_search("alpha")
        self.assertEqual(result["outcome"], "needs_approval")
        self.assertTrue(result.get("permission_needed"))
        review2 = ReviewStub(auto_review.OUTCOME_DENIED)
        service2, _t2, _p2, _r2 = self.fake_service(review=review2)
        self.services.configure_research(service=service2)
        result2 = self.services.research_fetch_read("https://example.com/page")
        self.assertEqual(result2["outcome"], "denied")
        self.assertTrue(result2["denied"])

    def test_saved_findings_scope_and_no_token_leak(self):
        service, _transport, _p, _r = self.fake_service()
        self.services.configure_research(service=service)
        saved = self.services.research_save_finding(
            "What is alpha?", "Bounded answer", confidence=0.7,
            project_id=1, mission_id=2, task_id=3)
        self.assertTrue(saved["ok"])
        findings = self.services.research_list_findings(project_id=1)
        self.assertTrue(findings["ok"])
        self.assertEqual(len(findings["findings"]), 1)
        self.assertEqual(findings["findings"][0]["question"], "What is alpha?")
        text = json.dumps(self.services.research_status())
        self.assertNotIn("secret", text.lower())
        facade = self.services.research
        self.assertTrue(hasattr(facade, "provider_statuses"))
        self.assertTrue(hasattr(facade, "search"))
        self.assertTrue(hasattr(facade, "preview"))
        self.assertTrue(hasattr(facade, "history"))
        self.assertTrue(hasattr(facade, "saved_findings"))
        self.assertTrue(hasattr(facade, "save_finding"))

    def test_facade_methods_are_thin_and_panel_shaped(self):
        service, _transport, _p, _r = self.fake_service()
        self.services.configure_research(service=service)
        facade = self.services.research
        statuses = facade.provider_statuses()
        self.assertEqual(statuses[0]["provider_id"], "offline-known-urls")
        search = facade.search("alpha", None)
        self.assertTrue(search["ok"])
        self.assertTrue(facade.preview("https://example.com/page")["ok"])
        history = facade.history(project_id=1, mission_id=2)
        self.assertIsInstance(history, list)
        saved = facade.saved_findings(project_id=1, mission_id=2)
        self.assertIsInstance(saved, list)
        save = facade.save_finding({"title": "T", "text": "A"}, project_id=1,
                                   mission_id=2)
        self.assertTrue(save["ok"])
        intake = facade.intake("url", "https://example.com/page", project_id=1)
        self.assertTrue(intake["ok"])

    def test_attach_detach_mission_findings_audit_and_retention(self):
        from unittest.mock import patch
        service, _transport, _p, _r = self.fake_service()
        self.services.configure_research(service=service)
        finding = self.services.research_save_finding(
            "Attach me?", "Evidence", project_id=None)
        self.assertTrue(finding["ok"], finding)
        finding_id = finding["id"]
        mission_id = self.services.create_mission(None, "Mission", "goal")
        attached = self.services.research_attach_finding(mission_id, finding_id)
        self.assertTrue(attached["ok"], attached)
        self.assertTrue(attached["link"]["created"])
        again = self.services.research_attach_finding(mission_id, finding_id)
        self.assertTrue(again["ok"])
        self.assertTrue(again["link"]["idempotent"])
        mission_findings = self.services.research_mission_findings(mission_id)
        self.assertTrue(mission_findings["ok"])
        self.assertEqual([item["id"] for item in mission_findings["findings"]],
                         [finding_id])
        detached = self.services.research_detach_finding(mission_id, finding_id)
        self.assertTrue(detached["ok"])
        self.assertTrue(detached["finding_preserved"])
        self.assertEqual(self.services.research_mission_findings(mission_id)["findings"], [])
        self.assertIsNotNone(service.store.get_finding(finding_id))
        rows = self.services._db.execute(
            "SELECT event_kind, payload FROM events WHERE source='research'").fetchall()
        kinds = {row["event_kind"] for row in rows}
        self.assertIn("finding_attached", kinds)
        self.assertIn("finding_detached", kinds)
        for row in rows:
            self.assertNotIn("secret", str(row["payload"]).lower())

        with patch.object(permissions, "check_capability",
                          return_value=permissions.Denied("write", "denied by test")):
            denied = self.services.research_attach_finding(mission_id, finding_id)
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["outcome"], "denied")
        self.assertEqual(service.store.list_mission_findings(mission_id), [])
        with patch.object(permissions, "check_capability",
                          return_value=permissions.NeedsApproval(
                              "write", "approval required", approval_id=1)):
            pending = self.services.research_attach_finding(mission_id, finding_id)
        self.assertFalse(pending["ok"])
        self.assertEqual(pending["outcome"], "needs_approval")
        self.assertEqual(service.store.list_mission_findings(mission_id), [])

        store = service.store
        source = store.save_source("https://example.com/old", excerpt="old",
                                   project_id=None,
                                   retrieved_at="2020-01-01T00:00:00Z")
        old_finding = store.save_finding("Old?", "Old evidence", project_id=None)
        conn = store._connect()
        try:
            with conn:
                conn.execute("UPDATE research_findings SET created_at=?, updated_at=? "
                             "WHERE id=?", ("2020-01-01T00:00:00Z",
                                            "2020-01-01T00:00:00Z", old_finding["id"]))
        finally:
            conn.close()
        store.attach_finding_to_mission(old_finding["id"], mission_id)
        applied = self.services.research_apply_retention(
            now="2026-01-01T00:00:00Z", ttl_days=1, max_items=10)
        self.assertTrue(applied["ok"], applied)
        self.assertEqual(applied["deleted"], 0)
        self.assertFalse(applied["hard_deleted"])
        self.assertTrue(store.get_source(source["id"])["expired"])
        self.assertTrue(store.get_finding(old_finding["id"])["expired"])
        summary = self.services.research_retention_summary()
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["summary"]["attachments_total"], 2)
        self.assertEqual(summary["summary"]["attachments_active"], 1)
        self.assertEqual(summary["summary"]["attachments_revoked"], 1)
        self.assertFalse(summary["summary"]["hard_deleted"])

    def test_attach_validates_missing_finding_and_mission_scope(self):
        service, _transport, _p, _r = self.fake_service()
        self.services.configure_research(service=service)
        mission_id = self.services.create_mission(None, "Mission", "goal")
        missing_finding = self.services.research_attach_finding(mission_id, 9999)
        self.assertFalse(missing_finding["ok"])
        self.assertEqual(missing_finding["outcome"], "validation")
        finding = self.services.research_save_finding("Q", "A", project_id=None)
        missing_mission = self.services.research_attach_finding(9999, finding["id"])
        self.assertFalse(missing_mission["ok"])
        self.assertEqual(missing_mission["outcome"], "validation")

    def test_static_no_default_research_network_in_services(self):
        source = (REPO_ROOT / "nl_coding_agent" / "app" / "services.py").read_text(
            encoding="utf-8")
        lowered = source.lower()
        for forbidden in ("urllib.request", "requests.get", "httpx", "aiohttp",
                          "sqlite3.connect(", "default transport"):
            self.assertNotIn(forbidden, lowered)
        self.assertIn("no explicit research network transport", source)
        self.assertIn("configure_research", source)


if __name__ == "__main__":
    unittest.main()

"""Tests for the research provider registry/router (fake providers only, no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.research.providers import (  # noqa: E402
    CapabilityMatrix,
    KnownUrl,
    NoKeySearchAdapter,
    OfflineKnownUrlProvider,
    ProviderDefinition,
    ProviderError,
    ProviderRegistry,
    ProviderStatus,
    RoutingPolicy,
    SearchProvider,
    SearchQuery,
    SearchResponse,
    SearchResult,
    UnavailableNoKeyAdapter,
    default_registry,
    multi_source_search,
    registry_from_config,
    route,
    search_routed,
    select_provider,
    verify_multi_source,
)


def caps(provider_id: str, *, search_types=("web",), cost="free", latency="low",
         auth=False, reliability=0.8, privacy="public", offline=False,
         rate=60, languages=(), recency=None) -> CapabilityMatrix:
    return CapabilityMatrix(
        provider_id=provider_id, name=provider_id.title(), search_types=search_types,
        cost_class=cost, latency_class=latency, auth_required=auth,
        auth_kinds=("api-key",) if auth else ("none",), reliability=reliability,
        privacy_class=privacy, offline=offline, rate_limit_per_min=rate,
        languages=languages, recency_days=recency,
        limitations=("fake provider used in tests",),
    )


class FakeProvider:
    def __init__(self, provider_id: str, *, available=True, results=None,
                 fail=None, **kwargs):
        self.provider_id = provider_id
        self.capabilities = caps(provider_id, **kwargs)
        self._available = available
        self._results = list(results or [])
        self._fail = fail
        self.calls = 0

    def status(self) -> ProviderStatus:
        if self._available:
            return ProviderStatus(self.provider_id, True, "available")
        return ProviderStatus(self.provider_id, False, "offline-source-unavailable",
                              "fake provider marked unavailable")

    def search(self, query: SearchQuery) -> SearchResponse:
        self.calls += 1
        if self._fail:
            raise RuntimeError(self._fail)
        if not self._available:
            return SearchResponse.unavailable(self.provider_id, query,
                                              "offline-source-unavailable", "fake unavailable")
        results = []
        for index, item in enumerate(self._results[:query.max_results], start=1):
            results.append(SearchResult(provider_id=self.provider_id,
                                        title=item.get("title", "result " + str(index)),
                                        url=item["url"],
                                        snippet=item.get("snippet", ""), rank=index))
        return SearchResponse.ok(self.provider_id, query, results)


def result(url: str, title: str = "title") -> dict:
    return {"url": url, "title": title}


class CapabilityTests(unittest.TestCase):
    def test_capability_matrix_validates_and_reports(self):
        matrix = caps("fake-a", search_types=("web", "docs", "code"), languages=("en",),
                      recency=30)
        self.assertTrue(matrix.supports("web"))
        self.assertTrue(matrix.supports("web", language="en"))
        self.assertFalse(matrix.supports("web", language="it"))
        self.assertTrue(matrix.supports("docs", recent_days=30))
        self.assertFalse(matrix.supports("docs", recent_days=60))
        payload = matrix.as_dict()
        self.assertEqual(payload["provider_id"], "fake-a")
        self.assertEqual(payload["search_types"], ["web", "docs", "code"])
        self.assertIn("limitations", payload)
        with self.assertRaises(ProviderError):
            caps("bad", search_types=("telepathy",))
        with self.assertRaises(ProviderError):
            caps("bad", cost="cheap")
        with self.assertRaises(ProviderError):
            caps("bad", reliability=1.5)
        with self.assertRaises(ProviderError):
            CapabilityMatrix(provider_id="bad", name="Bad", search_types=("web",),
                             auth_required=True, auth_kinds=())

    def test_search_query_and_result_validate(self):
        query = SearchQuery("hello", "web", language="en", recent_days=7, max_results=5)
        self.assertEqual(query.as_dict()["max_results"], 5)
        with self.assertRaises(ProviderError):
            SearchQuery("hello", "telepathy")
        with self.assertRaises(ProviderError):
            SearchQuery("hello", max_results=0)
        item = SearchResult("p", "Title", "HTTPS://Example.COM:443/a#frag", rank=1)
        self.assertEqual(item.url, "https://example.com/a")
        self.assertTrue(item.untrusted)
        with self.assertRaises(ProviderError):
            SearchResult("p", "Title", "https://user:secret@example.com/", rank=1)


class RegistryTests(unittest.TestCase):
    def test_registry_from_config_injected_and_statuses(self):
        fake = FakeProvider("enabled")
        config = {"providers": {
            "enabled": {"kind": "no-key", "capabilities": fake.capabilities.as_dict()},
            "disabled": {"enabled": False, "kind": "no-key", "capabilities": {
                "search_types": ["web"]}},
            "declared-only": {"kind": "placeholder", "capabilities": {
                "search_types": ["web"], "auth_required": True,
                "auth_kinds": ["api-key"]}},
        }}
        registry = registry_from_config(config, providers=[fake])
        self.assertEqual(registry.provider_ids(), ("declared-only", "disabled", "enabled"))
        self.assertTrue(registry.status("enabled").available)
        self.assertEqual(registry.status("disabled").reason, "disabled")
        self.assertEqual(registry.status("declared-only").reason, "adapter-missing")
        self.assertEqual(registry.status("missing").reason, "adapter-missing")
        offline = OfflineKnownUrlProvider([KnownUrl("https://example.com/a")])
        reg2 = default_registry(providers=[offline])
        self.assertEqual(reg2.available_ids(), ("offline-known-urls",))
        self.assertIsInstance(offline, SearchProvider)

    def test_injected_capability_mismatch_is_refused(self):
        config = {"providers": {"fake": {"capabilities": {"search_types": ["web"],
                                                          "reliability": 0.1}}}}
        with self.assertRaises(ProviderError):
            registry_from_config(config, providers=[FakeProvider("fake")])

    def test_registry_rejects_duplicates(self):
        registry = ProviderRegistry()
        definition = ProviderDefinition("p", caps("p"))
        registry.add_definition(definition)
        with self.assertRaises(ProviderError):
            registry.add_definition(definition)


class OfflineAndNoKeyTests(unittest.TestCase):
    def test_offline_known_url_provider(self):
        provider = OfflineKnownUrlProvider([
            KnownUrl("https://example.com/beta", "Beta doc", "beta snippet", ("docs",)),
            KnownUrl("https://example.com/alpha", "Alpha doc", "alpha snippet", ("docs",)),
        ])
        self.assertTrue(provider.status().available)
        response = provider.search(SearchQuery("alpha", "web"))
        self.assertTrue(response.status.available)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].url, "https://example.com/alpha")
        self.assertTrue(response.results[0].untrusted)
        empty = provider.search(SearchQuery("no-match", "web"))
        self.assertEqual(empty.results, ())
        refused = provider.search(SearchQuery("alpha", "academic"))
        self.assertFalse(refused.status.available)
        self.assertEqual(refused.status.reason, "policy-denied")
        with self.assertRaises(ProviderError):
            KnownUrl("https://user:pass@example.com/x")

    def test_no_key_adapter_interface_is_honestly_unavailable(self):
        adapter = UnavailableNoKeyAdapter(caps("public-no-key"))
        self.assertIsInstance(adapter, NoKeySearchAdapter)
        self.assertFalse(adapter.status().available)
        self.assertEqual(adapter.status().reason, "no-network-transport")
        response = adapter.search(SearchQuery("q"))
        self.assertFalse(response.status.available)
        self.assertIn("no approved network transport", response.status.detail)
        with self.assertRaises(ProviderError):
            UnavailableNoKeyAdapter(caps("auth", auth=True))


class RoutingTests(unittest.TestCase):
    def test_deterministic_routing_and_explanation(self):
        weak = FakeProvider("weak", reliability=0.2, latency="high", cost="freemium")
        strong = FakeProvider("strong", reliability=0.9, latency="low", cost="free")
        registry = default_registry(providers=[weak, strong])
        decision = route(registry, SearchQuery("q", "web"))
        self.assertEqual(decision.selected_provider, "strong")
        self.assertTrue(decision.available)
        self.assertGreater(decision.score, 0)
        self.assertTrue(any("strong" in line for line in decision.explanation))
        self.assertEqual(decision.candidates[0][0], "strong")
        self.assertEqual(dict(decision.rejected)["weak"], "cost-class-above-policy")

    def test_policy_filters_and_explanations(self):
        auth = FakeProvider("auth", auth=True)
        offline = FakeProvider("offline", offline=True, privacy="local")
        paid = FakeProvider("paid", cost="paid")
        registry = default_registry(providers=[auth, offline, paid])
        policy = RoutingPolicy(require_offline=True, max_cost="free", allow_auth=False)
        decision = route(registry, SearchQuery("q"), policy)
        self.assertEqual(decision.selected_provider, "offline")
        reasons = dict(decision.rejected)
        self.assertIn("auth-required", reasons["auth"])
        self.assertIn("cost", reasons["paid"])
        no_offline = route(registry, SearchQuery("q"), RoutingPolicy(allow_auth=True,
                                                                     max_cost="paid"))
        self.assertIn(no_offline.selected_provider, ("auth", "offline"))

    def test_no_provider_and_unavailable_provider(self):
        empty = route(ProviderRegistry(), SearchQuery("q"))
        self.assertIsNone(empty.selected_provider)
        self.assertEqual(empty.status.reason, "no-suitable-provider")
        unavailable = FakeProvider("down", available=False)
        registry = default_registry(providers=[unavailable])
        decision, response = search_routed(registry, SearchQuery("q"))
        self.assertIsNone(decision.selected_provider)
        self.assertFalse(response.status.available)

    def test_explicit_selection_and_refusal_no_fallback(self):
        available = FakeProvider("good", reliability=0.9)
        disabled = FakeProvider("disabled", reliability=0.9)
        registry = default_registry(providers=[available, disabled])
        selected = select_provider(registry, "good", SearchQuery("q"))
        self.assertEqual(selected.selected_provider, "good")
        self.assertTrue(selected.explicit)
        refused = select_provider(registry, "missing", SearchQuery("q"))
        self.assertIsNone(refused.selected_provider)
        self.assertEqual(refused.status.reason, "adapter-missing")
        auth_provider = FakeProvider("auth", auth=True)
        registry2 = default_registry(providers=[available, auth_provider])
        refused_auth = select_provider(registry2, "auth", SearchQuery("q"),
                                       RoutingPolicy(allow_auth=False))
        self.assertIsNone(refused_auth.selected_provider)
        self.assertEqual(refused_auth.status.reason, "explicit-provider-refused")
        self.assertFalse(refused_auth.available)

    def test_search_routed_does_not_fallback_on_provider_error(self):
        good = FakeProvider("good", results=[result("https://example.com/a")])
        bad = FakeProvider("bad", fail="boom", reliability=1.0)
        registry = default_registry(providers=[good, bad])
        decision, response = search_routed(registry, SearchQuery("q"),
                                           preferred_provider="bad")
        self.assertEqual(decision.selected_provider, "bad")
        self.assertFalse(response.status.available)
        self.assertEqual(response.status.reason, "provider-error")
        self.assertEqual(good.calls, 0)


class MultiSourceTests(unittest.TestCase):
    def test_agreement_and_metadata_disagreement(self):
        one = FakeProvider("one", results=[result("https://example.com/a", "Alpha"),
                                           result("https://example.com/b", "Beta")])
        two = FakeProvider("two", results=[result("https://EXAMPLE.com/a", "Alpha title"),
                                           result("https://example.com/c", "Gamma")])
        query = SearchQuery("q")
        report = verify_multi_source(query, [one.search(query), two.search(query)])
        self.assertTrue(report.verified)
        self.assertEqual(report.corroborated, ("https://example.com/a",))
        self.assertIn("https://example.com/b", report.single_source)
        self.assertIn("https://example.com/c", report.single_source)
        self.assertEqual(len(report.disagreements), 1)
        self.assertEqual(report.disagreements[0][0], "https://example.com/a")
        payload = report.as_dict()
        self.assertTrue(payload["verified"])
        self.assertEqual(len(payload["disagreements"]), 1)

    def test_multi_source_unavailable_and_min_sources(self):
        one = FakeProvider("one", results=[result("https://example.com/a")])
        down = FakeProvider("down", available=False)
        registry = default_registry(providers=[one, down])
        report = multi_source_search(registry, SearchQuery("q"))
        self.assertIn("down", report.unavailable)
        self.assertEqual(report.corroborated, ())
        with self.assertRaises(ProviderError):
            verify_multi_source(SearchQuery("q"), [], min_sources=1)


class StaticGuardTests(unittest.TestCase):
    def test_providers_have_no_network_or_sdk_dependency(self):
        source = (REPO_ROOT / "nl_coding_agent" / "research" / "providers.py").read_text(
            encoding="utf-8")
        for forbidden in ("import urllib", "import requests", "import socket",
                          "http.client", "httpx", "aiohttp", "import subprocess",
                          "os.system(", "download(", "https://"):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertIn("class SearchProvider(Protocol)", source)
        self.assertIn("class NoKeySearchAdapter(Protocol)", source)
        self.assertIn("class OfflineKnownUrlProvider", source)


if __name__ == "__main__":
    unittest.main()

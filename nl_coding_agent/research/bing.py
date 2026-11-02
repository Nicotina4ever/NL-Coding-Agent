"""Bing HTML search adapter over the permission-gated Research transport."""
from __future__ import annotations

import base64
import binascii
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from .github import HttpRequest
from .providers import (
    CapabilityMatrix,
    ProviderError,
    ProviderStatus,
    SearchQuery,
    SearchResponse,
    SearchResult,
    STATUS_AVAILABLE,
    STATUS_NO_NETWORK_TRANSPORT,
    STATUS_POLICY_DENIED,
)


class BingHtmlProvider:
    """Read-only public web search using Bing's HTML endpoint."""

    provider_id = "bing-html"
    endpoint = "https://www.bing.com/search"

    def __init__(self, transport=None):
        self._transport = transport
        self.capabilities = CapabilityMatrix(
            provider_id=self.provider_id, name="Bing web search",
            search_types=("web",), coverage=("web",), languages=(),
            auth_required=False, auth_kinds=("none",), cost_class="free",
            latency_class="medium", rate_limit_per_min=30, reliability=0.7,
            privacy_class="public", offline=False,
            limitations=("search query is sent to Microsoft Bing",
                         "HTML result format may change"),
        )

    def status(self) -> ProviderStatus:
        if self._transport is None:
            return ProviderStatus(self.provider_id, False, STATUS_NO_NETWORK_TRANSPORT,
                                  "no approved Research HTTP transport is configured")
        return ProviderStatus(self.provider_id, True, STATUS_AVAILABLE,
                              "uses the configured permission-gated Research transport")

    def search(self, query: SearchQuery) -> SearchResponse:
        if not self.capabilities.supports(query.search_type):
            return SearchResponse.unavailable(
                self.provider_id, query, STATUS_POLICY_DENIED,
                "Bing adapter supports general web search only")
        if self._transport is None:
            return SearchResponse.unavailable(
                self.provider_id, query, STATUS_NO_NETWORK_TRANSPORT,
                "no approved Research HTTP transport is configured")
        url = self.endpoint + "?" + urlencode({"q": query.text})
        response = self._transport.request(HttpRequest(
            method="GET", url=url, headers=(("Accept", "text/html"),),
            timeout_s=15.0, max_bytes=1_000_000))
        if response.status_code != 200:
            return SearchResponse.unavailable(
                self.provider_id, query, "http-" + str(response.status_code),
                "Bing search endpoint returned a non-success status")

        parser = _BingResultsParser(query.max_results)
        try:
            parser.feed(response.body.decode("utf-8", errors="replace"))
            parser.close()
        except (ValueError, TypeError) as exc:
            return SearchResponse.unavailable(
                self.provider_id, query, "invalid-response",
                "could not parse search response (" + type(exc).__name__ + ")")
        return SearchResponse.ok(
            self.provider_id, query, parser.results,
            note="Search results are untrusted; fetch result URLs for page contents.")


class _BingResultsParser(HTMLParser):
    """Extract bounded title, destination URL and snippet fields."""

    def __init__(self, limit: int):
        super().__init__(convert_charrefs=True)
        self.limit = int(limit)
        self.results: list[SearchResult] = []
        self._current: dict | None = None
        self._capture = ""
        self._in_caption = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = set(str(values.get("class") or "").split())
        if tag == "li" and "b_algo" in classes:
            if self._current:
                self._append_current()
            self._current = {"href": "", "title": [], "snippet": []}
            self._capture = ""
            self._in_caption = False
            return
        if not self._current:
            return
        if tag == "h2":
            self._capture = "title"
        elif tag == "a" and self._capture == "title" and not self._current["href"]:
            self._current["href"] = str(values.get("href") or "")
        elif tag == "div" and "b_caption" in classes:
            self._in_caption = True
        elif tag == "p" and self._in_caption:
            self._capture = "snippet"

    def handle_endtag(self, tag):
        if tag == "h2" and self._capture == "title":
            self._capture = ""
        elif tag == "p" and self._capture == "snippet":
            self._capture = ""
        elif tag == "div" and self._in_caption:
            self._in_caption = False
        elif tag == "li" and self._current:
            self._append_current()
            self._current = None
            self._capture = ""
            self._in_caption = False

    def handle_data(self, data):
        if self._current and self._capture:
            self._current[self._capture].append(data)

    @staticmethod
    def _destination_url(href: str) -> str:
        url = urljoin(BingHtmlProvider.endpoint, href.strip())
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if (host == "bing.com" or host.endswith(".bing.com")) and \
                parts.path.startswith("/ck/a"):
            encoded = parse_qs(parts.query).get("u", [""])[0]
            if not encoded.startswith("a1"):
                raise ProviderError("Bing result link has no destination URL")
            value = encoded[2:]
            padding = "=" * (-len(value) % 4)
            return base64.urlsafe_b64decode(value + padding).decode("utf-8")
        return url

    def _append_current(self):
        if not self._current or len(self.results) >= self.limit:
            return
        try:
            result = SearchResult(
                provider_id=BingHtmlProvider.provider_id,
                title=" ".join("".join(self._current["title"]).split())[:500],
                url=self._destination_url(self._current["href"]),
                snippet=" ".join("".join(self._current["snippet"]).split())[:1200],
                rank=len(self.results) + 1,
            )
        except (ProviderError, ValueError, TypeError, binascii.Error,
                UnicodeDecodeError):
            return
        if result.title:
            self.results.append(result)

    def close(self):
        super().close()
        if self._current:
            self._append_current()

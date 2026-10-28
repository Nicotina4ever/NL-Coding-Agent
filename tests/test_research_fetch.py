"""Safe fetcher tests: scripted fake transports only, no real network.

The Fetcher has no default network transport: every test injects FakeTransport
and a deterministic clock.  Nothing in this module opens a socket, resolves DNS
or contacts an external service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from nl_coding_agent.research import fetch as f
from nl_coding_agent.research.models import KIND_HTML, KIND_JSON, sha256_hex
from nl_coding_agent.research.policy import (
    REASON_CONTENT_TYPE_DENIED,
    REASON_CONTENT_TYPE_MISSING,
    REASON_HOST_DENIED,
    REASON_PRIVATE_NETWORK,
    REASON_RATE_LIMITED,
    REASON_REDIRECT_LIMIT,
    REASON_SCHEME_DENIED,
    RetrievalPolicy,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_SOURCE = REPO_ROOT / "nl_coding_agent" / "research" / "fetch.py"
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
URL = "https://example.com/docs/page"


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def open(self, request):
        self.requests.append(request)
        value = self.responses[request.url]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class FakeClock:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.values:
            return self.values.pop(0)
        return 0.0


def response(status=200, body=b"", content_type="text/html; charset=utf-8",
             location=None, headers=None):
    pairs = []
    if content_type is not None:
        pairs.append(("Content-Type", content_type))
    if location is not None:
        pairs.append(("Location", location))
    for name, value in (headers or {}).items():
        pairs.append((name, value))
    return f.TransportResponse(status_code=status, headers=tuple(pairs), body=body)


def make_fetcher(responses, policy=None, gate=None, clock_values=None):
    transport = FakeTransport(responses)
    clock = FakeClock(clock_values if clock_values is not None else [0.0] * 20)
    fetcher = f.Fetcher(policy or RetrievalPolicy(), transport,
                        permission_gate=gate, clock=clock,
                        now=lambda: NOW)
    return fetcher, transport


def test_successful_fetch_provenance_and_untrusted_marker():
    body = b"<html><body><h1>Hello</h1></body></html>"
    fetcher, transport = make_fetcher({URL: response(body=body, headers={"ETag": '"abc"'})},
                                      clock_values=[0.0, 0.0, 0.01])
    document = fetcher.fetch(URL)
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url == URL
    assert request.timeout_s == 10.0
    assert request.max_bytes == 2_000_000
    assert "NL-Coding-Agent" in request.header_dict["User-Agent"]
    assert "text/html" in request.header_dict["Accept"]
    assert document.content == body.decode("utf-8")
    assert document.kind == KIND_HTML
    assert document.source.requested_url == URL
    assert document.source.canonical_url == URL
    assert document.source.redirect_chain == (URL,)
    assert document.source.fetched_at == NOW
    assert document.source.sha256 == sha256_hex(body)
    assert document.source.size == len(body)
    assert document.source.provenance.untrusted is True
    assert document.untrusted is True
    assert document.metadata_dict().get("etag") == '"abc"'
    assert document.citation.url == URL


def test_manual_redirect_chain_is_recorded_and_policy_checked():
    first = "https://example.com/start"
    second = "https://example.com/next"
    transport_responses = {
        first: response(302, location="/next"),
        second: response(200, body=b"ok", content_type="text/plain; charset=utf-8"),
    }
    fetcher, transport = make_fetcher(transport_responses,
                                      clock_values=[0.0, 0.0, 0.01, 0.01, 0.01, 0.02])
    document = fetcher.fetch(first)
    assert [request.url for request in transport.requests] == [first, second]
    assert document.source.redirect_chain == (first, second)
    assert document.source.requested_url == first
    assert document.source.canonical_url == second
    assert document.kind == "text"


def test_redirect_to_private_ip_is_denied_before_the_second_request():
    url = "https://example.com/start"
    responses = {url: response(302, location="https://127.0.0.1/secret")}
    fetcher, transport = make_fetcher(responses)
    with pytest.raises(f.FetchDenied) as excinfo:
        fetcher.fetch(url)
    assert excinfo.value.reason == REASON_PRIVATE_NETWORK
    assert len(transport.requests) == 1
    assert excinfo.value.redirect_chain == (url,)


def test_redirect_to_denied_domain_is_denied():
    url = "https://example.com/start"
    responses = {url: response(302, location="https://evil.test/x")}
    policy = RetrievalPolicy(denied_domains=("evil.test",))
    fetcher, transport = make_fetcher(responses, policy=policy)
    with pytest.raises(f.FetchDenied) as excinfo:
        fetcher.fetch(url)
    assert excinfo.value.reason == REASON_HOST_DENIED
    assert len(transport.requests) == 1


def test_redirect_to_http_is_scheme_denied():
    url = "https://example.com/start"
    responses = {url: response(302, location="http://example.com/insecure")}
    fetcher, transport = make_fetcher(responses)
    with pytest.raises(f.FetchDenied) as excinfo:
        fetcher.fetch(url)
    assert excinfo.value.reason == REASON_SCHEME_DENIED
    assert len(transport.requests) == 1


def test_max_redirects_is_enforced():
    a = "https://example.com/a"
    b = "https://example.com/b"
    c = "https://example.com/c"
    responses = {a: response(302, location="/b"), b: response(302, location="/c")}
    fetcher, transport = make_fetcher(responses, policy=RetrievalPolicy(max_redirects=1))
    with pytest.raises(f.FetchDenied) as excinfo:
        fetcher.fetch(a)
    assert excinfo.value.reason == REASON_REDIRECT_LIMIT
    assert [request.url for request in transport.requests] == [a, b]
    assert c not in [request.url for request in transport.requests]


def test_redirect_loop_fails_closed():
    url = "https://example.com/a"
    responses = {url: response(302, location=url)}
    fetcher, transport = make_fetcher(responses)
    with pytest.raises(f.FetchFailed) as excinfo:
        fetcher.fetch(url)
    assert excinfo.value.reason == "redirect_loop"
    assert len(transport.requests) == 1


def test_timeout_is_enforced_with_deterministic_clock():
    fetcher, transport = make_fetcher({URL: response(body=b"x")},
                                      policy=RetrievalPolicy(request_timeout_s=10.0),
                                      clock_values=[0.0, 0.0, 11.0])
    with pytest.raises(f.FetchFailed) as excinfo:
        fetcher.fetch(URL)
    assert excinfo.value.reason == "timeout"


def test_body_size_limit_is_enforced():
    fetcher, transport = make_fetcher({URL: response(body=b"12345")},
                                      policy=RetrievalPolicy(max_bytes=4),
                                      clock_values=[0.0, 0.0, 0.01])
    with pytest.raises(f.FetchFailed) as excinfo:
        fetcher.fetch(URL)
    assert excinfo.value.reason == "size_limit_exceeded"


def test_declared_content_length_over_limit_is_rejected():
    fetcher, transport = make_fetcher(
        {URL: response(body=b"123", headers={"Content-Length": "1000000"})},
        policy=RetrievalPolicy(max_bytes=10),
        clock_values=[0.0, 0.0, 0.01])
    with pytest.raises(f.FetchFailed) as excinfo:
        fetcher.fetch(URL)
    assert excinfo.value.reason == "size_limit_exceeded"


def test_content_type_allowlist_and_missing_content_type_fail_closed():
    fetcher, transport = make_fetcher({URL: response(body=b"pdf", content_type="application/pdf")})
    with pytest.raises(f.FetchDenied) as excinfo:
        fetcher.fetch(URL)
    assert excinfo.value.reason == REASON_CONTENT_TYPE_DENIED

    fetcher2, _ = make_fetcher({URL: response(body=b"x", content_type=None)})
    with pytest.raises(f.FetchDenied) as excinfo2:
        fetcher2.fetch(URL)
    assert excinfo2.value.reason == REASON_CONTENT_TYPE_MISSING


def test_permission_gate_denies_before_transport_and_on_redirects():
    calls = []
    fetcher, transport = make_fetcher(
        {URL: response(body=b"ok")}, gate=lambda url: calls.append(url) or False)
    with pytest.raises(f.FetchDenied) as excinfo:
        fetcher.fetch(URL)
    assert excinfo.value.reason == "permission_denied"
    assert calls == [URL]
    assert transport.requests == []

    def raising_gate(url):
        raise PermissionError("denied by broker")

    fetcher2, transport2 = make_fetcher({URL: response(body=b"ok")}, gate=raising_gate)
    with pytest.raises(f.FetchDenied) as excinfo2:
        fetcher2.fetch(URL)
    assert excinfo2.value.reason == "permission_denied"
    assert transport2.requests == []

    hop_calls = []
    a = "https://example.com/a"
    b = "https://example.com/b"
    fetcher3, transport3 = make_fetcher(
        {a: response(302, location="/b"), b: response(200, body=b"ok")},
        gate=lambda url: hop_calls.append(url) or True,
        clock_values=[0.0, 0.0, 0.01, 0.01, 0.01, 0.02])
    fetcher3.fetch(a)
    assert hop_calls == [a, b]


def test_rate_limit_is_shared_across_requests_of_one_fetcher():
    policy = RetrievalPolicy(rate_limit_per_minute=1, rate_limit_burst=1)
    fetcher, transport = make_fetcher(
        {URL: response(body=b"ok")}, policy=policy,
        clock_values=[0.0, 0.0, 0.01, 10.0])
    fetcher.fetch(URL)
    with pytest.raises(f.FetchDenied) as excinfo:
        fetcher.fetch(URL)
    assert excinfo.value.reason == REASON_RATE_LIMITED
    assert len(transport.requests) == 1


def test_transport_errors_and_http_errors_are_fetch_failures():
    fetcher, _ = make_fetcher({URL: OSError("connection refused")})
    with pytest.raises(f.FetchFailed) as excinfo:
        fetcher.fetch(URL)
    assert excinfo.value.reason == "transport_error"

    fetcher2, _ = make_fetcher({URL: response(status=500, body=b"err")})
    with pytest.raises(f.FetchFailed) as excinfo2:
        fetcher2.fetch(URL)
    assert excinfo2.value.reason == "http_error"


def test_non_utf8_charset_is_decoded_and_recorded():
    body = "caf\u00e9".encode("iso-8859-1")
    fetcher, _ = make_fetcher({URL: response(body=body,
                                             content_type="text/plain; charset=ISO-8859-1")})
    document = fetcher.fetch(URL)
    assert document.content == "caf\u00e9"
    assert document.source.provenance.charset == "iso-8859-1"


def test_json_media_type_is_classified_for_the_reader():
    fetcher, _ = make_fetcher({URL: response(body=b'{"ok": true}',
                                             content_type="application/json")})
    document = fetcher.fetch(URL)
    assert document.kind == KIND_JSON
    assert document.content == '{"ok": true}'


def test_fetcher_requires_an_injected_transport_and_rejects_bad_headers():
    with pytest.raises(ValueError):
        f.Fetcher(RetrievalPolicy(), None)
    fetcher, transport = make_fetcher({URL: response(body=b"ok")})
    with pytest.raises(ValueError):
        fetcher.fetch(URL, headers={"X-Test": "bad\r\nInjected: 1"})
    assert transport.requests == []


def test_fetch_module_has_no_default_network_transport_or_network_imports():
    source = FETCH_SOURCE.read_text(encoding="utf-8")
    assert "requires an injected transport" in source
    for forbidden in ("import socket", "urllib.request", "import requests",
                      "import httpx", "urlopen(", "create_connection("):
        assert forbidden not in source, forbidden

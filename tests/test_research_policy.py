"""Research retrieval policy tests: pure logic, no sockets, no network.

Every URL is handled locally by RetrievalPolicy; DNS is exercised only through
an injected fake resolver.  No HTTP request, socket, model or application
service is touched.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nl_coding_agent.research import policy as p
from nl_coding_agent.research.models import (
    canonicalize_url,
    domain_matches,
    host_from_url,
    normalize_host,
    ResearchModelError,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_SOURCE = REPO_ROOT / "nl_coding_agent" / "research" / "policy.py"


def test_canonical_url_and_domain_helpers():
    assert canonicalize_url("HTTPS://Example.COM:443/a/../b?q=1#frag") == \
        "https://example.com/a/../b?q=1"
    assert canonicalize_url("https://example.com") == "https://example.com/"
    assert canonicalize_url("https://example.com:8443/x") == "https://example.com:8443/x"
    assert host_from_url("https://Sub.Example.COM/x") == "sub.example.com"
    assert normalize_host("Example.COM.") == "example.com"
    assert domain_matches("docs.example.com", "example.com") is True
    assert domain_matches("example.com", "example.com") is True
    assert domain_matches("badexample.com", "example.com") is False
    assert domain_matches("example.com.evil.test", "example.com") is False
    with pytest.raises(ResearchModelError):
        canonicalize_url("https://user:pass@example.com/x")
    with pytest.raises(ResearchModelError):
        canonicalize_url("not-a-url")
    with pytest.raises(ResearchModelError):
        canonicalize_url("")


def test_default_policy_is_https_only_and_fail_closed():
    policy = p.RetrievalPolicy()
    https = policy.evaluate_url("https://example.com/docs")
    assert https.allowed is True and https.reason == p.REASON_OK
    http = policy.evaluate_url("http://example.com/docs")
    assert http.allowed is False and http.reason == p.REASON_SCHEME_DENIED
    file_url = policy.evaluate_url("file:///etc/passwd")
    assert file_url.allowed is False
    assert policy.evaluate_url("").reason == p.REASON_INVALID_URL
    assert policy.evaluate_url("https://").reason == p.REASON_INVALID_URL
    assert policy.evaluate_url("https://user:pass@example.com/").reason == \
        p.REASON_CREDENTIALS_IN_URL
    assert policy.evaluate_url("https://example.com:9999/").reason == p.REASON_PORT_DENIED


def test_scheme_and_port_configuration():
    policy = p.RetrievalPolicy(allowed_schemes=("https", "http"),
                               allowed_ports=(443, 8080))
    assert policy.evaluate_url("https://example.com/").allowed is True
    assert policy.evaluate_url("https://example.com:8080/").allowed is True
    assert policy.evaluate_url("http://example.com:8080/").allowed is True
    assert policy.evaluate_url("http://example.com/").allowed is False
    assert policy.evaluate_url("https://example.com:80/").allowed is False


def test_domain_allow_and_deny_with_subdomain_matching():
    policy = p.RetrievalPolicy(allowed_domains=("example.com",))
    assert policy.evaluate_url("https://example.com/a").allowed is True
    assert policy.evaluate_url("https://docs.example.com/a").allowed is True
    denied = policy.evaluate_url("https://other.test/a")
    assert denied.allowed is False and denied.reason == p.REASON_HOST_NOT_ALLOWED

    deny_policy = p.RetrievalPolicy(denied_domains=("evil.test",))
    assert deny_policy.evaluate_url("https://evil.test/a").reason == p.REASON_HOST_DENIED
    assert deny_policy.evaluate_url("https://sub.evil.test/a").reason == p.REASON_HOST_DENIED
    assert deny_policy.evaluate_url("https://example.com/a").allowed is True

    precedence = p.RetrievalPolicy(allowed_domains=("example.com",),
                                   denied_domains=("api.example.com",))
    assert precedence.evaluate_url("https://api.example.com/").reason == p.REASON_HOST_DENIED
    assert precedence.evaluate_url("https://docs.example.com/").allowed is True


@pytest.mark.parametrize("url,reason", [
    ("https://127.0.0.1/", p.REASON_PRIVATE_NETWORK),
    ("https://10.0.0.1/", p.REASON_PRIVATE_NETWORK),
    ("https://172.16.4.5/", p.REASON_PRIVATE_NETWORK),
    ("https://192.168.1.10/", p.REASON_PRIVATE_NETWORK),
    ("https://169.254.1.1/", p.REASON_PRIVATE_NETWORK),
    ("https://224.0.0.1/", p.REASON_PRIVATE_NETWORK),
    ("https://0.0.0.0/", p.REASON_PRIVATE_NETWORK),
    ("https://[::1]/", p.REASON_PRIVATE_NETWORK),
    ("https://[fc00::1]/", p.REASON_PRIVATE_NETWORK),
    ("https://localhost/", p.REASON_PRIVATE_NETWORK),
    ("https://localhost.localdomain/", p.REASON_PRIVATE_NETWORK),
    ("https://api.localhost/", p.REASON_PRIVATE_NETWORK),
])
def test_ssrf_blocks_loopback_private_link_local_multicast_and_hostnames(url, reason):
    decision = p.RetrievalPolicy().evaluate_url(url)
    assert decision.allowed is False
    assert decision.reason == reason


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "172.16.1.1", "192.168.0.1", "169.254.10.10",
    "224.0.0.1", "0.0.0.0", "::1", "fc00::1", "fe80::1", "not-an-ip",
])
def test_is_public_ip_is_fail_closed(address):
    assert p.is_public_ip(address) is False
    assert p.is_blocked_ip(address) is True


def test_ssrf_explicit_exceptions_authorize_private_targets():
    by_host = p.RetrievalPolicy(ssrf_exceptions=("localhost",))
    assert by_host.evaluate_url("https://localhost/").allowed is True
    by_ip = p.RetrievalPolicy(ssrf_exceptions=("127.0.0.1/32",))
    assert by_ip.evaluate_url("https://127.0.0.1/").allowed is True
    by_cidr = p.RetrievalPolicy(ssrf_exceptions=("10.0.0.0/8",))
    assert by_cidr.evaluate_url("https://10.1.2.3/").allowed is True
    assert by_cidr.evaluate_url("https://192.168.1.1/").allowed is False


def test_injected_resolver_blocks_private_addresses_and_fails_closed():
    private = p.RetrievalPolicy(host_resolver=lambda host: ("10.1.2.3",))
    decision = private.evaluate_url("https://docs.example.com/page")
    assert decision.allowed is False and decision.reason == p.REASON_PRIVATE_NETWORK

    public = p.RetrievalPolicy(host_resolver=lambda host: ("93.184.216.34",))
    assert public.evaluate_url("https://docs.example.com/page").allowed is True

    empty = p.RetrievalPolicy(host_resolver=lambda host: ())
    assert empty.evaluate_url("https://docs.example.com/page").reason == \
        p.REASON_RESOLVER_EMPTY

    def boom(host):
        raise RuntimeError("dns down")

    broken = p.RetrievalPolicy(host_resolver=boom)
    decision = broken.evaluate_url("https://docs.example.com/page")
    assert decision.allowed is False and decision.reason == p.REASON_RESOLVER_ERROR

    excepted = p.RetrievalPolicy(host_resolver=lambda host: ("10.0.0.5",),
                                 ssrf_exceptions=("docs.example.com",))
    assert excepted.evaluate_url("https://docs.example.com/page").allowed is True


def test_redirect_budget_and_redirect_target_policy():
    policy = p.RetrievalPolicy(max_redirects=2)
    assert policy.evaluate_redirect("https://example.com/a", "https://example.com/b",
                                    redirect_count=0).allowed is True
    assert policy.evaluate_redirect("https://example.com/a", "https://example.com/b",
                                    redirect_count=1).allowed is True
    denied = policy.evaluate_redirect("https://example.com/a", "https://example.com/b",
                                      redirect_count=2)
    assert denied.allowed is False and denied.reason == p.REASON_REDIRECT_LIMIT
    private = policy.evaluate_redirect("https://example.com/a", "https://127.0.0.1/",
                                       redirect_count=0)
    assert private.allowed is False and private.reason == p.REASON_PRIVATE_NETWORK
    assert policy.evaluate_url("https://example.com/x", redirect_count=3).reason == \
        p.REASON_REDIRECT_LIMIT


def test_content_type_allowlist_is_fail_closed():
    policy = p.RetrievalPolicy()
    assert policy.evaluate_content_type("text/html; charset=utf-8").allowed is True
    assert policy.evaluate_content_type("application/json").allowed is True
    assert policy.evaluate_content_type("application/pdf").allowed is False
    denied = policy.evaluate_content_type("application/pdf")
    assert denied.reason == p.REASON_CONTENT_TYPE_DENIED
    assert policy.evaluate_content_type(None).reason == p.REASON_CONTENT_TYPE_MISSING
    assert policy.evaluate_content_type("").reason == p.REASON_CONTENT_TYPE_MISSING
    assert p.RetrievalPolicy(allowed_content_types=("text/csv",)
                             ).evaluate_content_type("TEXT/CSV").allowed is True


def test_token_bucket_is_deterministic_and_does_not_sleep():
    bucket = p.TokenBucket(capacity=2, refill_per_second=1.0)
    first = bucket.consume(0.0)
    second = bucket.consume(0.0)
    third = bucket.consume(0.0)
    assert first.allowed is True and second.allowed is True
    assert third.allowed is False and third.reason == p.REASON_RATE_LIMITED
    assert third.retry_after_s == pytest.approx(1.0)
    fourth = bucket.consume(1.0)
    assert fourth.allowed is True
    policy_bucket = p.RetrievalPolicy(rate_limit_per_minute=60,
                                      rate_limit_burst=1).rate_limiter()
    assert policy_bucket.consume(0.0).allowed is True
    assert policy_bucket.consume(0.5).allowed is False
    assert policy_bucket.consume(60.0).allowed is True


def test_policy_validation_is_strict():
    with pytest.raises(ValueError):
        p.RetrievalPolicy(allowed_schemes=())
    with pytest.raises(ValueError):
        p.RetrievalPolicy(max_bytes=0)
    with pytest.raises(ValueError):
        p.RetrievalPolicy(request_timeout_s=0)
    with pytest.raises(ValueError):
        p.RetrievalPolicy(max_redirects=-1)
    with pytest.raises(ValueError):
        p.RetrievalPolicy(rate_limit_burst=0)
    with pytest.raises(ValueError):
        p.RetrievalPolicy(denied_domains=("http://example.com",))
    with pytest.raises(ValueError):
        p.RetrievalPolicy(allowed_ports=(70000,))
    with pytest.raises(ValueError):
        p.TokenBucket(capacity=0, refill_per_second=1.0)


def test_policy_is_immutable():
    policy = p.RetrievalPolicy()
    with pytest.raises(FrozenInstanceError):
        policy.max_bytes = 1  # type: ignore[misc]
    decision = policy.evaluate_url("https://example.com/")
    assert bool(decision) is True
    assert decision.host == "example.com"


def test_policy_module_has_no_network_imports_or_calls():
    source = POLICY_SOURCE.read_text(encoding="utf-8")
    for forbidden in ("import socket", "urllib.request", "import requests",
                      "import httpx", "urlopen(", "create_connection("):
        assert forbidden not in source, forbidden

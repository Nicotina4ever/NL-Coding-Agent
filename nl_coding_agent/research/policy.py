"""Fail-closed retrieval policy for the research engine (NL-BP-206).

This module is pure logic: it performs no network calls, no DNS lookups by
default and no sleeping.  DNS-based SSRF checks are available through an
injected host_resolver callback so tests (and future integration) can decide how
names are resolved without this module opening a socket itself.

Decision rule: anything unexpected, unsupported or ambiguous is denied.  Every
decision carries a stable reason code and a human-readable detail for auditing.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Callable, Sequence
from urllib.parse import urlsplit

from .models import (
    ResearchModelError,
    canonicalize_url,
    domain_matches,
    normalize_host,
)

REASON_OK = "ok"
REASON_INVALID_URL = "invalid_url"
REASON_CREDENTIALS_IN_URL = "credentials_in_url"
REASON_SCHEME_DENIED = "scheme_denied"
REASON_HOST_DENIED = "host_denied"
REASON_HOST_NOT_ALLOWED = "host_not_allowed"
REASON_PRIVATE_NETWORK = "private_network_blocked"
REASON_PORT_DENIED = "port_denied"
REASON_REDIRECT_LIMIT = "redirect_limit_exceeded"
REASON_CONTENT_TYPE_MISSING = "content_type_missing"
REASON_CONTENT_TYPE_DENIED = "content_type_denied"
REASON_RATE_LIMITED = "rate_limited"
REASON_RESOLVER_ERROR = "resolver_error"
REASON_RESOLVER_EMPTY = "resolver_empty"

DEFAULT_ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "application/json",
)
DEFAULT_ALLOWED_SCHEMES = ("https",)
_HOSTNAME_BLOCKLIST = frozenset({
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
})


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Allowed/denied decision with a stable reason and audit detail."""

    allowed: bool
    reason: str
    detail: str
    canonical_url: str = ""
    host: str = ""

    def __bool__(self) -> bool:
        return self.allowed


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Deterministic token-bucket decision (no sleeping, no wall clock)."""

    allowed: bool
    reason: str
    detail: str
    remaining: float = 0.0
    retry_after_s: float | None = None


def _is_safe_public(address: ipaddress._BaseAddress) -> bool:
    return bool(address.is_global and not address.is_multicast
                and not address.is_reserved and not address.is_unspecified)


def is_public_ip(value: str) -> bool:
    """True only for globally routable unicast addresses."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return _is_safe_public(address)


def is_blocked_ip(value: str) -> bool:
    """True for loopback/private/link-local/multicast/reserved/non-public IPs."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    return not _is_safe_public(address)


def _describe_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return value
    labels = []
    if address.is_loopback:
        labels.append("loopback")
    if address.is_private:
        labels.append("private")
    if address.is_link_local:
        labels.append("link-local")
    if address.is_multicast:
        labels.append("multicast")
    if address.is_reserved:
        labels.append("reserved")
    if address.is_unspecified:
        labels.append("unspecified")
    if not labels:
        labels.append("non-public")
    return value + " (" + ", ".join(labels) + ")"


@dataclass
class TokenBucket:
    """Deterministic token bucket: caller supplies monotonic timestamps."""

    capacity: float
    refill_per_second: float
    tokens: float = field(init=False)
    updated_at: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if self.refill_per_second < 0:
            raise ValueError("refill_per_second must be non-negative")
        self.tokens = float(self.capacity)

    def _refill(self, now: float) -> None:
        if now < 0:
            raise ValueError("now must be non-negative")
        if self.updated_at is None:
            self.updated_at = float(now)
            return
        elapsed = max(0.0, float(now) - float(self.updated_at))
        self.updated_at = max(float(now), self.updated_at)
        if self.refill_per_second > 0:
            self.tokens = min(float(self.capacity),
                              self.tokens + elapsed * self.refill_per_second)

    def consume(self, now: float) -> RateLimitDecision:
        """Consume one token at the caller-supplied time."""
        self._refill(now)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return RateLimitDecision(True, REASON_OK, "token available",
                                     remaining=self.tokens)
        if self.refill_per_second > 0:
            retry_after = (1.0 - self.tokens) / self.refill_per_second
        else:
            retry_after = None
        return RateLimitDecision(
            False, REASON_RATE_LIMITED,
            "rate limit exceeded; no token available in this mission/request budget",
            remaining=self.tokens, retry_after_s=retry_after,
        )


@dataclass(frozen=True)
class RetrievalPolicy:
    """Immutable, fail-closed policy for one research retrieval mission.

    The default is HTTPS-only, any public domain, no private/loopback targets,
    five redirects, 10 s per request, 2 MB body cap, text-only content types and
    a deterministic 30/minute token bucket with a burst of five.
    """

    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()
    ssrf_exceptions: tuple[str, ...] = ()
    allowed_ports: tuple[int, ...] = ()
    host_resolver: Callable[[str], Sequence[str]] | None = field(
        default=None, compare=False, repr=False)
    max_redirects: int = 5
    request_timeout_s: float = 10.0
    max_bytes: int = 2_000_000
    allowed_content_types: tuple[str, ...] = DEFAULT_ALLOWED_CONTENT_TYPES
    rate_limit_per_minute: int = 30
    rate_limit_burst: int = 5

    def __post_init__(self) -> None:
        schemes = tuple(dict.fromkeys(str(item).strip().lower()
                                      for item in self.allowed_schemes))
        if not schemes or any(not item for item in schemes):
            raise ValueError("allowed_schemes must contain at least one scheme")
        object.__setattr__(self, "allowed_schemes", schemes)
        object.__setattr__(self, "allowed_domains", self._normalize_domains(self.allowed_domains))
        object.__setattr__(self, "denied_domains", self._normalize_domains(self.denied_domains))
        object.__setattr__(self, "ssrf_exceptions",
                           self._normalize_exceptions(self.ssrf_exceptions))
        ports = tuple(dict.fromkeys(int(item) for item in self.allowed_ports))
        if any(port < 1 or port > 65535 for port in ports):
            raise ValueError("allowed_ports must contain valid TCP ports")
        object.__setattr__(self, "allowed_ports", ports)
        if not isinstance(self.max_redirects, int) or self.max_redirects < 0:
            raise ValueError("max_redirects must be a non-negative integer")
        if not isinstance(self.request_timeout_s, (int, float)) or self.request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be positive")
        if not isinstance(self.max_bytes, int) or self.max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        content_types = tuple(dict.fromkeys(
            str(item).strip().lower() for item in self.allowed_content_types))
        if not content_types or any("/" not in item for item in content_types):
            raise ValueError("allowed_content_types must contain media types")
        object.__setattr__(self, "allowed_content_types", content_types)
        if not isinstance(self.rate_limit_per_minute, int) or self.rate_limit_per_minute < 0:
            raise ValueError("rate_limit_per_minute must be a non-negative integer")
        if not isinstance(self.rate_limit_burst, int) or self.rate_limit_burst < 1:
            raise ValueError("rate_limit_burst must be a positive integer")

    @staticmethod
    def _normalize_domains(values: Sequence[str]) -> tuple[str, ...]:
        result = []
        for value in values:
            text = str(value or "").strip().lower().strip(".")
            if not text:
                raise ValueError("domain entries must not be empty")
            if "://" in text or "/" in text or ":" in text:
                raise ValueError("domain entries must be host/domain names: " + text)
            try:
                text = normalize_host(text)
            except ResearchModelError as exc:
                raise ValueError("invalid domain entry: " + text) from exc
            result.append(text)
        return tuple(dict.fromkeys(result))

    @staticmethod
    def _normalize_exceptions(values: Sequence[str]) -> tuple[str, ...]:
        result = []
        for value in values:
            text = str(value or "").strip().lower()
            if not text:
                raise ValueError("ssrf_exceptions entries must not be empty")
            try:
                ipaddress.ip_network(text, strict=False)
            except ValueError:
                try:
                    text = normalize_host(text)
                except ResearchModelError as exc:
                    raise ValueError("invalid ssrf exception: " + text) from exc
            result.append(text)
        return tuple(dict.fromkeys(result))

    def rate_limiter(self) -> TokenBucket:
        """Create a fresh deterministic limiter for one mission/request scope."""
        return TokenBucket(
            capacity=float(self.rate_limit_burst),
            refill_per_second=float(self.rate_limit_per_minute) / 60.0,
        )

    def _allowed_port(self, scheme: str, port: int | None) -> bool:
        effective = port if port is not None else (443 if scheme == "https" else 80)
        if self.allowed_ports:
            return effective in self.allowed_ports
        return effective == (443 if scheme == "https" else 80)

    def _is_exception(self, host: str, addresses: Sequence[str]) -> bool:
        if not self.ssrf_exceptions:
            return False
        for entry in self.ssrf_exceptions:
            if domain_matches(host, entry):
                return True
            try:
                network = ipaddress.ip_network(entry, strict=False)
            except ValueError:
                continue
            for address in addresses:
                try:
                    if ipaddress.ip_address(address) in network:
                        return True
                except ValueError:
                    continue
        return False

    def _env_domains_allowed(self, host: str) -> bool:
        for domain in self.denied_domains:
            if domain_matches(host, domain):
                return False
        if not self.allowed_domains:
            return True
        return any(domain_matches(host, domain) for domain in self.allowed_domains)

    def evaluate_url(self, url: str, *, redirect_count: int = 0) -> PolicyDecision:
        """Evaluate one URL before any network activity; fail closed on error."""
        if redirect_count > self.max_redirects:
            return PolicyDecision(False, REASON_REDIRECT_LIMIT,
                                  "maximum redirects exceeded before request")
        if not isinstance(url, str) or not url.strip():
            return PolicyDecision(False, REASON_INVALID_URL, "URL must be a non-empty string")
        try:
            parts = urlsplit(url.strip())
        except ValueError as exc:
            return PolicyDecision(False, REASON_INVALID_URL, "cannot parse URL: " + str(exc))
        scheme = parts.scheme.lower()
        if not scheme or not parts.netloc:
            return PolicyDecision(False, REASON_INVALID_URL, "URL must be absolute with a host")
        if parts.username is not None or parts.password is not None:
            return PolicyDecision(False, REASON_CREDENTIALS_IN_URL,
                                  "URL must not embed credentials")
        if scheme not in self.allowed_schemes:
            return PolicyDecision(False, REASON_SCHEME_DENIED,
                                  "scheme " + scheme + " is not allowed by this policy")
        try:
            host = normalize_host(parts.hostname or "")
        except ResearchModelError as exc:
            return PolicyDecision(False, REASON_INVALID_URL, str(exc))
        try:
            canonical = canonicalize_url(url)
        except ResearchModelError as exc:
            return PolicyDecision(False, REASON_INVALID_URL, str(exc))
        try:
            port = parts.port
        except ValueError as exc:
            return PolicyDecision(False, REASON_INVALID_URL, "invalid port: " + str(exc),
                                  canonical_url=canonical, host=host)
        if not self._allowed_port(scheme, port):
            return PolicyDecision(False, REASON_PORT_DENIED,
                                  "port is not allowed by this policy",
                                  canonical_url=canonical, host=host)
        if not self._env_domains_allowed(host):
            reason = (REASON_HOST_DENIED if any(domain_matches(host, item)
                                                for item in self.denied_domains)
                      else REASON_HOST_NOT_ALLOWED)
            return PolicyDecision(False, reason,
                                  "host " + host + " is not permitted",
                                  canonical_url=canonical, host=host)

        literal_ip = None
        try:
            literal_ip = ipaddress.ip_address(host)
        except ValueError:
            literal_ip = None
        addresses: list[str] = []
        if literal_ip is not None:
            addresses.append(str(literal_ip))
            if is_blocked_ip(str(literal_ip)) and not self._is_exception(host, addresses):
                return PolicyDecision(False, REASON_PRIVATE_NETWORK,
                                      "blocked non-public IP " + _describe_ip(str(literal_ip)),
                                      canonical_url=canonical, host=host)
        elif host in _HOSTNAME_BLOCKLIST or host.endswith(".localhost"):
            if not self._is_exception(host, ()):
                return PolicyDecision(False, REASON_PRIVATE_NETWORK,
                                      "localhost/loopback hostname is blocked",
                                      canonical_url=canonical, host=host)
        elif self.host_resolver is not None and not self._is_exception(host, ()):
            try:
                resolved = [str(item) for item in self.host_resolver(host)]
            except Exception as exc:
                return PolicyDecision(False, REASON_RESOLVER_ERROR,
                                      "host resolution failed closed: " + type(exc).__name__,
                                      canonical_url=canonical, host=host)
            if not resolved:
                return PolicyDecision(False, REASON_RESOLVER_EMPTY,
                                      "resolver returned no addresses for " + host,
                                      canonical_url=canonical, host=host)
            addresses = resolved
            if not self._is_exception(host, addresses):
                blocked = [address for address in addresses if is_blocked_ip(address)]
                if blocked:
                    return PolicyDecision(False, REASON_PRIVATE_NETWORK,
                                          "resolved to blocked address " + _describe_ip(blocked[0]),
                                          canonical_url=canonical, host=host)
        return PolicyDecision(True, REASON_OK, "allowed by retrieval policy",
                              canonical_url=canonical, host=host)

    def evaluate_redirect(self, current_url: str, next_url: str, *,
                          redirect_count: int) -> PolicyDecision:
        """Evaluate a redirect target, including the redirect budget."""
        if redirect_count >= self.max_redirects:
            return PolicyDecision(False, REASON_REDIRECT_LIMIT,
                                  "maximum redirects (" + str(self.max_redirects) + ") exceeded")
        decision = self.evaluate_url(next_url, redirect_count=redirect_count + 1)
        if not decision.allowed:
            return decision
        return PolicyDecision(True, REASON_OK, "redirect target allowed",
                              canonical_url=decision.canonical_url, host=decision.host)

    def evaluate_content_type(self, content_type: str | None) -> PolicyDecision:
        """Fail closed unless the response media type is on the allowlist."""
        if content_type is None or not str(content_type).strip():
            return PolicyDecision(False, REASON_CONTENT_TYPE_MISSING,
                                  "response has no Content-Type")
        media_type = str(content_type).split(";", 1)[0].strip().lower()
        if not media_type:
            return PolicyDecision(False, REASON_CONTENT_TYPE_MISSING,
                                  "response has an empty Content-Type")
        if media_type not in self.allowed_content_types:
            return PolicyDecision(False, REASON_CONTENT_TYPE_DENIED,
                                  "media type " + media_type + " is not on the allowlist")
        return PolicyDecision(True, REASON_OK, "content type allowed")

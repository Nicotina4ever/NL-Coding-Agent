"""Safe HTTP fetcher for the research foundation (NL-BP-170 / NL-BP-206).

The fetcher NEVER opens a connection itself: a transport/opener must be injected
by the caller. Production uses a bounded stdlib transport only after the
ResearchService permission gate approves each URL; tests inject scripted
transports.  Tests pass a scripted fake transport.

Security flow for every hop (initial request and each redirect):
1. RetrievalPolicy.evaluate_url / evaluate_redirect (scheme, domain, SSRF,
   ports, redirect budget);
2. permission-gate callback (NETWORK/web-fetch capability and auto-review);
3. deterministic token-bucket rate limit;
4. transport request with timeout and max-bytes budget;
5. elapsed-time, HTTP status, content-type and body-size enforcement.

Failures always raise FetchDenied or FetchFailed with a stable reason; no
partial document is returned on failure.  Retrieved content is marked untrusted.
"""
from __future__ import annotations

import codecs
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping, Protocol
from urllib.parse import urljoin

from .models import (
    KIND_BINARY,
    KIND_HTML,
    KIND_JSON,
    KIND_MARKDOWN,
    KIND_TEXT,
    Provenance,
    RetrievedDocument,
    Source,
    canonicalize_url,
    freeze_metadata,
    sha256_hex,
    utc_now,
)
from .policy import (
    REASON_RATE_LIMITED,
    REASON_REDIRECT_LIMIT,
    PolicyDecision,
    RetrievalPolicy,
)

DEFAULT_USER_AGENT = "NL-Coding-Agent-Research/0.1 (foundation; source-level only)"
DEFAULT_ACCEPT = ("text/html,application/xhtml+xml,text/plain,text/markdown,"
                  "application/json;q=0.9,*/*;q=0.1")
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
SAFE_METADATA_HEADERS = ("content-language", "date", "etag", "last-modified")


@dataclass(frozen=True, slots=True)
class TransportRequest:
    """One HTTP GET request handed to an injected transport."""

    url: str
    method: str = "GET"
    headers: tuple[tuple[str, str], ...] = ()
    timeout_s: float = 10.0
    max_bytes: int = 2_000_000

    @property
    def header_dict(self) -> dict[str, str]:
        return {name: value for name, value in self.headers}


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """Raw transport response; redirects are NOT followed by the transport."""

    status_code: int
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes = b""

    def header(self, name: str, default: str | None = None) -> str | None:
        wanted = name.strip().lower()
        for key, value in self.headers:
            if key.strip().lower() == wanted:
                return value
        return default


class Transport(Protocol):
    """Injected HTTP transport protocol (no default network implementation)."""

    def open(self, request: TransportRequest) -> TransportResponse:
        ...


class FetchError(Exception):
    """Base retrieval failure with a stable reason and audit context."""

    def __init__(self, reason: str, detail: str, *, canonical_url: str = "",
                 redirect_chain: tuple[str, ...] = (), attempts: int = 0,
                 decision: PolicyDecision | None = None) -> None:
        super().__init__(reason + ": " + detail)
        self.reason = reason
        self.detail = detail
        self.canonical_url = canonical_url
        self.redirect_chain = tuple(redirect_chain)
        self.attempts = attempts
        self.decision = decision


class FetchDenied(FetchError):
    """Policy, permission-gate, rate-limit or redirect-budget denial."""


class FetchFailed(FetchError):
    """Transport, timeout, HTTP-status, content-type or body-size failure."""


def parse_content_type(content_type: str | None) -> tuple[str, str | None]:
    """Return (lower-case media type, charset) from a Content-Type value."""
    if not content_type or not str(content_type).strip():
        return "", None
    parts = str(content_type).split(";")
    media_type = parts[0].strip().lower()
    charset = None
    for parameter in parts[1:]:
        key, _, value = parameter.partition("=")
        if key.strip().lower() == "charset":
            candidate = value.strip().strip('"').strip("'").lower()
            if candidate:
                charset = candidate
    return media_type, charset


def _decode_body(body: bytes, charset: str | None) -> tuple[str, str | None]:
    encoding = "utf-8"
    used_charset = None
    if charset:
        try:
            codecs.lookup(charset)
        except LookupError:
            used_charset = None
        else:
            encoding = charset
            used_charset = charset
    text = bytes(body).decode(encoding, errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text, used_charset


def classify_kind(media_type: str) -> str:
    """Classify a media type for the reader without downloading dependencies."""
    media_type = (media_type or "").lower()
    if media_type in ("text/html", "application/xhtml+xml"):
        return KIND_HTML
    if media_type in ("text/markdown", "text/x-markdown"):
        return KIND_MARKDOWN
    if media_type == "application/json" or media_type.endswith("+json"):
        return KIND_JSON
    if media_type.startswith("text/"):
        return KIND_TEXT
    return KIND_BINARY


class Fetcher:
    """Policy-enforcing fetcher with an injected transport and deterministic clock.

    The clock argument is a monotonic seconds callable used for rate limiting
    and elapsed timeout checks; now supplies the wall-clock UTC fetched_at
    timestamp.  The optional permission_gate receives the URL of every attempted
    hop and must return exactly True to allow it; False or an exception denies
    closed.
    """

    def __init__(self, policy: RetrievalPolicy | None = None,
                 transport: Transport | None = None, *,
                 permission_gate: Callable[[str], bool] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = utc_now) -> None:
        if transport is None:
            raise ValueError(
                "Fetcher requires an injected transport; no real network "
                "transport is bundled in the foundation increment")
        if policy is None:
            policy = RetrievalPolicy()
        if not isinstance(policy, RetrievalPolicy):
            raise TypeError("policy must be a RetrievalPolicy")
        self.policy = policy
        self.transport = transport
        self.permission_gate = permission_gate
        self._clock = clock
        self._now = now
        self._limiter = policy.rate_limiter()

    @staticmethod
    def _validate_headers(headers: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
        result: list[tuple[str, str]] = []
        if headers:
            for name, value in headers.items():
                name = str(name).strip()
                value = str(value).strip()
                if not name or not value:
                    raise ValueError("request headers must have a name and value")
                if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                    raise ValueError("request headers must not contain CR/LF")
                result.append((name, value))
        return tuple(result)

    def _build_request(self, url: str, user_headers: tuple[tuple[str, str], ...]
                       ) -> TransportRequest:
        defaults = [("User-Agent", DEFAULT_USER_AGENT), ("Accept", DEFAULT_ACCEPT),
                    ("Accept-Encoding", "identity")]
        merged = {name.lower(): (name, value) for name, value in defaults}
        for name, value in user_headers:
            merged[name.lower()] = (name, value)
        headers = tuple(merged[key] for key in sorted(merged))
        return TransportRequest(url=url, headers=headers,
                                timeout_s=float(self.policy.request_timeout_s),
                                max_bytes=int(self.policy.max_bytes))

    def _check_permission(self, url: str) -> None:
        if self.permission_gate is None:
            return
        try:
            decision = self.permission_gate(url)
        except Exception as exc:
            raise FetchDenied("permission_denied",
                              "web-fetch permission gate raised: " + type(exc).__name__,
                              canonical_url=url) from exc
        if decision is not True:
            raise FetchDenied("permission_denied",
                              "web-fetch capability was not granted for this request",
                              canonical_url=url)

    def _deny(self, decision: PolicyDecision, chain: tuple[str, ...], attempts: int
              ) -> FetchDenied:
        return FetchDenied(decision.reason, decision.detail,
                           canonical_url=decision.canonical_url,
                           redirect_chain=chain, attempts=attempts,
                           decision=decision)

    def fetch(self, url: str, *, headers: Mapping[str, str] | None = None
              ) -> RetrievedDocument:
        """Fetch one URL under policy control and return an untrusted document."""
        if not isinstance(url, str):
            raise FetchDenied("invalid_url", "URL must be a string")
        requested_url = url.strip()
        user_headers = self._validate_headers(headers)
        visited: list[str] = []
        redirects_followed = 0
        attempts = 0
        current_url = requested_url

        while True:
            if current_url in visited:
                raise FetchFailed("redirect_loop",
                                  "redirect loop detected at " + current_url,
                                  redirect_chain=tuple(visited), attempts=attempts)
            decision = self.policy.evaluate_url(current_url,
                                                redirect_count=redirects_followed)
            if not decision.allowed:
                raise self._deny(decision, tuple(visited), attempts)
            self._check_permission(current_url)
            rate = self._limiter.consume(self._clock())
            if not rate.allowed:
                raise FetchDenied(
                    REASON_RATE_LIMITED, rate.detail,
                    canonical_url=decision.canonical_url,
                    redirect_chain=tuple(visited), attempts=attempts,
                    decision=PolicyDecision(False, REASON_RATE_LIMITED, rate.detail,
                                            canonical_url=decision.canonical_url,
                                            host=decision.host))
            visited.append(current_url)
            attempts += 1
            request = self._build_request(current_url, user_headers)
            started = self._clock()
            try:
                response = self.transport.open(request)
            except FetchError:
                raise
            except Exception as exc:
                raise FetchFailed(
                    "transport_error",
                    "transport failed: " + type(exc).__name__ + ": " + str(exc),
                    canonical_url=decision.canonical_url,
                    redirect_chain=tuple(visited), attempts=attempts) from exc
            elapsed = self._clock() - started
            if elapsed > float(self.policy.request_timeout_s):
                raise FetchFailed(
                    "timeout",
                    "request exceeded " + str(self.policy.request_timeout_s)
                    + " s (elapsed " + format(elapsed, ".3f") + " s)",
                    canonical_url=decision.canonical_url,
                    redirect_chain=tuple(visited), attempts=attempts)

            if not isinstance(response, TransportResponse):
                raise FetchFailed("invalid_transport_response",
                                  "transport returned an unexpected response object",
                                  canonical_url=decision.canonical_url,
                                  redirect_chain=tuple(visited), attempts=attempts)
            status = int(response.status_code)
            if status in REDIRECT_STATUSES:
                location = response.header("location")
                if not location or not str(location).strip():
                    raise FetchFailed("redirect_missing_location",
                                      "redirect response has no Location header",
                                      canonical_url=decision.canonical_url,
                                      redirect_chain=tuple(visited), attempts=attempts)
                if redirects_followed >= self.policy.max_redirects:
                    raise FetchDenied(REASON_REDIRECT_LIMIT,
                                      "maximum redirects (" + str(self.policy.max_redirects)
                                      + ") exceeded",
                                      canonical_url=decision.canonical_url,
                                      redirect_chain=tuple(visited), attempts=attempts,
                                      decision=PolicyDecision(False, REASON_REDIRECT_LIMIT,
                                                              "redirect budget exceeded"))
                next_url = urljoin(current_url, str(location).strip())
                redirect_decision = self.policy.evaluate_redirect(
                    current_url, next_url, redirect_count=redirects_followed)
                if not redirect_decision.allowed:
                    raise self._deny(redirect_decision, tuple(visited), attempts)
                current_url = next_url
                redirects_followed += 1
                continue
            if status < 200 or status >= 300:
                raise FetchFailed("http_error",
                                  "unexpected HTTP status " + str(status),
                                  canonical_url=decision.canonical_url,
                                  redirect_chain=tuple(visited), attempts=attempts)
            content_type_raw = response.header("content-type")
            content_decision = self.policy.evaluate_content_type(content_type_raw)
            if not content_decision.allowed:
                raise FetchDenied(content_decision.reason, content_decision.detail,
                                  canonical_url=decision.canonical_url,
                                  redirect_chain=tuple(visited), attempts=attempts,
                                  decision=content_decision)
            media_type, charset = parse_content_type(content_type_raw)
            try:
                body = bytes(response.body or b"")
            except (TypeError, ValueError) as exc:
                raise FetchFailed("invalid_transport_response",
                                  "transport body must be bytes",
                                  canonical_url=decision.canonical_url,
                                  redirect_chain=tuple(visited), attempts=attempts) from exc
            content_length = response.header("content-length")
            if content_length:
                try:
                    declared = int(str(content_length).strip())
                except ValueError:
                    declared = None
                if declared is not None and declared > self.policy.max_bytes:
                    raise FetchFailed("size_limit_exceeded",
                                      "declared Content-Length " + str(declared)
                                      + " exceeds policy max_bytes "
                                      + str(self.policy.max_bytes),
                                      canonical_url=decision.canonical_url,
                                      redirect_chain=tuple(visited), attempts=attempts)
            if len(body) > self.policy.max_bytes:
                raise FetchFailed("size_limit_exceeded",
                                  "downloaded body " + str(len(body))
                                  + " bytes exceeds policy max_bytes "
                                  + str(self.policy.max_bytes),
                                  canonical_url=decision.canonical_url,
                                  redirect_chain=tuple(visited), attempts=attempts)
            text, charset_used = _decode_body(body, charset)
            final_canonical = canonicalize_url(current_url)
            metadata = freeze_metadata(
                (name, value) for name, value in
                ((header, response.header(header)) for header in SAFE_METADATA_HEADERS)
                if value
            )
            provenance = Provenance(
                requested_url=requested_url,
                canonical_url=final_canonical,
                final_url=final_canonical,
                redirect_chain=tuple(visited),
                fetched_at=self._now(),
                content_type=media_type,
                charset=charset_used,
                sha256=sha256_hex(body),
                size=len(body),
                status_code=status,
                untrusted=True,
            )
            source = Source(provenance=provenance, metadata=metadata)
            return RetrievedDocument(source=source, content=text,
                                     kind=classify_kind(media_type),
                                     metadata=metadata, untrusted=True)


#: Descriptive alias used in documentation and future integration code.
SafeFetcher = Fetcher

"""Universal Web Research engine - foundation increment (stage 7 research R1).

This package currently provides retrieval foundations only:
- immutable provenance/source/document/citation models;
- a fail-closed retrieval policy (scheme/domain/SSRF/redirect/rate/size rules);
- a transport-injected safe fetcher with manual redirect handling;
- a stdlib HTML reader plus plain/markdown/JSON passthrough and fail-closed
  PDF/Office/unknown formats.

It is NOT a complete research engine: there are no search providers, no browser
automation, no real network transport, no PDF/Office extraction, no knowledge
store, no GUI integration and no model/agent integration yet.  Real-network
acceptance remains MANUAL-PENDING (see docs/RESEARCH_ENGINE.md).
"""
from __future__ import annotations

from .fetch import (
    DEFAULT_ACCEPT,
    DEFAULT_USER_AGENT,
    REDIRECT_STATUSES,
    FetchDenied,
    FetchError,
    FetchFailed,
    Fetcher,
    SafeFetcher,
    Transport,
    TransportRequest,
    TransportResponse,
    classify_kind,
    parse_content_type,
)
from .models import (
    KIND_BINARY,
    KIND_HTML,
    KIND_JSON,
    KIND_MARKDOWN,
    KIND_TEXT,
    KIND_UNSUPPORTED,
    RESEARCH_SCHEMA_VERSION,
    TRUST_MARKER,
    Citation,
    Provenance,
    ResearchModelError,
    RetrievedDocument,
    Source,
    canonicalize_url,
    domain_matches,
    freeze_metadata,
    host_from_url,
    metadata_dict,
    normalize_host,
    sha256_hex,
    utc_now,
)
from .policy import (
    DEFAULT_ALLOWED_CONTENT_TYPES,
    DEFAULT_ALLOWED_SCHEMES,
    REASON_CONTENT_TYPE_DENIED,
    REASON_CONTENT_TYPE_MISSING,
    REASON_CREDENTIALS_IN_URL,
    REASON_HOST_DENIED,
    REASON_HOST_NOT_ALLOWED,
    REASON_INVALID_URL,
    REASON_OK,
    REASON_PORT_DENIED,
    REASON_PRIVATE_NETWORK,
    REASON_RATE_LIMITED,
    REASON_REDIRECT_LIMIT,
    REASON_SCHEME_DENIED,
    PolicyDecision,
    RateLimitDecision,
    RetrievalPolicy,
    TokenBucket,
    is_blocked_ip,
    is_public_ip,
)
from .reader import (
    MAX_LINKS,
    MAX_TEXT_CHARS,
    CodeBlock,
    Heading,
    Link,
    ListBlock,
    ReadablePage,
    Table,
    UnsupportedDocument,
    read_document,
)

__all__ = [
    "KIND_BINARY", "KIND_HTML", "KIND_JSON", "KIND_MARKDOWN", "KIND_TEXT",
    "KIND_UNSUPPORTED", "RESEARCH_SCHEMA_VERSION", "TRUST_MARKER", "Citation",
    "Provenance", "ResearchModelError", "RetrievedDocument", "Source",
    "canonicalize_url", "domain_matches", "freeze_metadata", "host_from_url",
    "metadata_dict", "normalize_host", "sha256_hex", "utc_now",
    "FetchDenied", "FetchError", "FetchFailed", "Fetcher", "SafeFetcher",
    "Transport", "TransportRequest", "TransportResponse", "DEFAULT_ACCEPT",
    "DEFAULT_USER_AGENT", "REDIRECT_STATUSES", "classify_kind",
    "parse_content_type", "DEFAULT_ALLOWED_CONTENT_TYPES",
    "DEFAULT_ALLOWED_SCHEMES", "PolicyDecision", "RateLimitDecision",
    "RetrievalPolicy", "TokenBucket", "is_blocked_ip", "is_public_ip",
    "REASON_OK", "REASON_INVALID_URL", "REASON_CREDENTIALS_IN_URL",
    "REASON_SCHEME_DENIED", "REASON_HOST_DENIED", "REASON_HOST_NOT_ALLOWED",
    "REASON_PRIVATE_NETWORK", "REASON_PORT_DENIED", "REASON_REDIRECT_LIMIT",
    "REASON_CONTENT_TYPE_MISSING", "REASON_CONTENT_TYPE_DENIED",
    "REASON_RATE_LIMITED", "MAX_LINKS", "MAX_TEXT_CHARS", "CodeBlock",
    "Heading", "Link", "ListBlock", "ReadablePage", "Table",
    "UnsupportedDocument", "read_document",
]

"""Universal Web Research engine - R1 foundation, R2 providers/store, R3 investigators.

Increments:
- R1: immutable provenance/source/document/citation models, fail-closed retrieval
  policy, transport-injected safe fetcher and stdlib HTML/plain/Markdown/JSON
  reader;
- R2: declarative search-provider registry/router (validated capability matrix,
  offline known-URL provider, no-key adapter interface, deterministic explainable
  routing, multi-source verification) and an additive local SQLite research
  knowledge store (sources/citations/findings/conflicts). No real provider
  transport or SDK exists;
- R3: read-only GitHub and Hugging Face Hub investigator clients through injected
  transports (no network library import, no real network in tests).

Still absent: a real network transport/acceptance, browser automation,
PDF/Office extraction, research planning/GUI and model/agent integration.
Real-network acceptance remains MANUAL-PENDING (see docs/RESEARCH_ENGINE.md).
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
from .github import (
    GitHubAuthError,
    GitHubError,
    GitHubNotFoundError,
    GitHubProvenance,
    GitHubRateLimitError,
    GitHubResearchClient,
    GitHubResponseError,
    GitHubResult,
    GitHubTransportError,
    HttpRequest,
    HttpResponse,
    HttpTransport,
)
from .huggingface import (
    HFProvenance,
    HFResult,
    HuggingFaceAuthError,
    HuggingFaceError,
    HuggingFaceGatedError,
    HuggingFaceNotFoundError,
    HuggingFaceRateLimitError,
    HuggingFaceResearchClient,
    HuggingFaceResponseError,
    HuggingFaceTransportError,
    estimate_resources,
)

from .providers import (
    AUTH_KINDS,
    COST_CLASSES,
    LATENCY_CLASSES,
    PRIVACY_CLASSES,
    SEARCH_TYPES,
    CapabilityMatrix,
    KnownUrl,
    MultiSourceReport,
    NoKeySearchAdapter,
    OfflineKnownUrlProvider,
    ProviderDefinition,
    ProviderError,
    ProviderRegistry,
    ProviderStatus,
    RoutingDecision,
    RoutingPolicy,
    SearchProvider,
    SearchQuery,
    SearchResponse,
    SearchResult,
    UnavailableNoKeyAdapter,
    capability_from_config,
    default_registry,
    multi_source_search,
    registry_from_config,
    route,
    search_routed,
    select_provider,
    verify_multi_source,
)
from .store import (
    DEFAULT_LIMIT as RESEARCH_STORE_DEFAULT_LIMIT,
    MAX_EXCERPT_CHARS as RESEARCH_STORE_MAX_EXCERPT_CHARS,
    MAX_LIMIT as RESEARCH_STORE_MAX_LIMIT,
    STORE_SCHEMA_VERSION,
    ResearchStore,
    ResearchStoreError,
)

from .transport import (
    StdlibHttpTransport,
    TransportError,
    TransportLimitError,
    TransportPermissionError,
    TransportRequestError,
)
from .service import (
    CAPABILITY_BY_OPERATION,
    ResearchResult,
    ResearchService,
)
from .tools import (
    READ_ONLY_TOOL_NAMES,
    RESEARCH_TOOL_DESCRIPTORS,
    ResearchToolDescriptor,
    ResearchToolError,
    ResearchToolRegistry,
    describe_research_tools,
    register_research_tools,
    research_tool,
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
    "HttpRequest", "HttpResponse", "HttpTransport", "GitHubError",
    "GitHubTransportError", "GitHubAuthError", "GitHubRateLimitError",
    "GitHubNotFoundError", "GitHubResponseError", "GitHubProvenance",
    "GitHubResult", "GitHubResearchClient", "HFProvenance", "HFResult",
    "HuggingFaceError", "HuggingFaceTransportError", "HuggingFaceAuthError",
    "HuggingFaceRateLimitError", "HuggingFaceNotFoundError",
    "HuggingFaceGatedError", "HuggingFaceResponseError",
    "HuggingFaceResearchClient", "estimate_resources",
    "SEARCH_TYPES", "AUTH_KINDS", "COST_CLASSES", "LATENCY_CLASSES",
    "PRIVACY_CLASSES", "CapabilityMatrix", "KnownUrl", "ProviderStatus",
    "ProviderError", "SearchQuery", "SearchResult", "SearchResponse",
    "SearchProvider", "NoKeySearchAdapter", "UnavailableNoKeyAdapter",
    "OfflineKnownUrlProvider", "ProviderDefinition", "ProviderRegistry",
    "capability_from_config", "registry_from_config", "default_registry",
    "RoutingPolicy", "RoutingDecision", "select_provider", "route",
    "search_routed", "MultiSourceReport", "verify_multi_source",
    "multi_source_search", "ResearchStore", "ResearchStoreError",
    "STORE_SCHEMA_VERSION", "RESEARCH_STORE_MAX_EXCERPT_CHARS",
    "RESEARCH_STORE_MAX_LIMIT", "RESEARCH_STORE_DEFAULT_LIMIT",
    "StdlibHttpTransport", "TransportError", "TransportPermissionError",
    "TransportRequestError", "TransportLimitError", "ResearchService",
    "ResearchResult", "CAPABILITY_BY_OPERATION", "ResearchToolDescriptor",
    "ResearchToolError", "ResearchToolRegistry", "RESEARCH_TOOL_DESCRIPTORS",
    "READ_ONLY_TOOL_NAMES", "research_tool", "register_research_tools",
    "describe_research_tools",
]

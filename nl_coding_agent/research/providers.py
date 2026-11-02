"""Search provider capability registry and deterministic research router.

Stage 7 research R2 (NL-BP-169/205). Standard library only: this module
declares and routes providers but contains no network transport or provider SDK.
Network adapters live in separate modules and receive an explicit transport;
the registry never constructs a transport implicitly. Tests use fake providers.

Contract:
  * every provider declares a validated CapabilityMatrix (search types,
    coverage/languages/recency, auth, cost class, rate limit, latency, privacy,
    reliability and known limitations);
  * ProviderRegistry is built from config definitions plus injected provider
    instances (enabled/disabled, known ids, no network construction);
  * routing is explicit or deterministic (capability eligibility then a stable
    score with provider-id tie-break) and carries human-readable explanations
    and honest refusal/unavailability reasons;
  * multi-source verification aggregates results by canonical URL, marks
    corroborated vs single-source URLs and metadata disagreements;
  * no provider is called unless explicitly routed/selected; unavailable
    providers never silently fall back.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol, Sequence, runtime_checkable

from .models import ResearchModelError, TRUST_MARKER, canonicalize_url

SEARCH_TYPES = ("web", "docs", "code", "academic", "news", "known-url", "local")
AUTH_KINDS = ("none", "api-key", "oauth", "local")
COST_CLASSES = ("free", "freemium", "paid")
LATENCY_CLASSES = ("low", "medium", "high")
PRIVACY_CLASSES = ("public", "local", "no-query-retention")
STATUS_AVAILABLE = "available"
STATUS_DISABLED = "disabled"
STATUS_ADAPTER_MISSING = "adapter-missing"
STATUS_NO_KEY = "no-key-required"
STATUS_AUTH_MISSING = "auth-missing"
STATUS_OFFLINE_UNAVAILABLE = "offline-source-unavailable"
STATUS_NO_NETWORK_TRANSPORT = "no-network-transport"
STATUS_RATE_LIMITED = "rate-limited"
STATUS_POLICY_DENIED = "policy-denied"
STATUS_NO_PROVIDER = "no-suitable-provider"
STATUS_EXPLICIT_REFUSED = "explicit-provider-refused"
UNTRUSTED_MARKER = TRUST_MARKER


class ProviderError(ValueError):
    """Raised for invalid provider/registry/routing data."""


def _text(value, field_name: str, *, max_len: int = 500) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProviderError(field_name + " must not be empty")
    if len(text) > max_len:
        raise ProviderError(field_name + " is too long")
    return text


def _tuple_of(value, field_name: str, allowed: Sequence[str] | None = None) -> tuple[str, ...]:
    if value is None:
        return ()
    items = [str(item).strip() for item in value if str(item).strip()]
    if allowed is not None:
        unknown = [item for item in items if item not in allowed]
        if unknown:
            raise ProviderError(field_name + " contains unsupported values: "
                                + ", ".join(unknown))
    return tuple(items)


@dataclass(frozen=True, slots=True)
class CapabilityMatrix:
    """Declared, validated provider capabilities (no implementation claim)."""

    provider_id: str
    name: str
    search_types: tuple[str, ...]
    coverage: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    recency_days: int | None = None
    auth_required: bool = False
    auth_kinds: tuple[str, ...] = ("none",)
    cost_class: str = "free"
    latency_class: str = "medium"
    rate_limit_per_min: int = 60
    reliability: float = 0.5
    privacy_class: str = "public"
    offline: bool = False
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _text(self.provider_id, "provider_id", max_len=80))
        object.__setattr__(self, "name", _text(self.name, "capability.name", max_len=120))
        types = _tuple_of(self.search_types, "search_types", SEARCH_TYPES)
        if not types:
            raise ProviderError("provider must declare at least one search type")
        object.__setattr__(self, "search_types", types)
        object.__setattr__(self, "coverage", _tuple_of(self.coverage, "coverage"))
        object.__setattr__(self, "languages", _tuple_of(self.languages, "languages"))
        if self.recency_days is not None:
            if not isinstance(self.recency_days, int) or self.recency_days < 0:
                raise ProviderError("recency_days must be null or a non-negative integer")
        if not isinstance(self.auth_required, bool):
            raise ProviderError("auth_required must be a boolean")
        auth = _tuple_of(self.auth_kinds or (("none",) if not self.auth_required else ()),
                         "auth_kinds", AUTH_KINDS)
        if self.auth_required and not auth:
            raise ProviderError("auth_required providers must declare auth_kinds")
        if not self.auth_required and auth == ("none",):
            pass
        if self.cost_class not in COST_CLASSES:
            raise ProviderError("invalid cost_class: " + str(self.cost_class))
        if self.latency_class not in LATENCY_CLASSES:
            raise ProviderError("invalid latency_class: " + str(self.latency_class))
        if not isinstance(self.rate_limit_per_min, int) or self.rate_limit_per_min <= 0:
            raise ProviderError("rate_limit_per_min must be a positive integer")
        if not isinstance(self.reliability, (int, float)) or not 0.0 <= float(self.reliability) <= 1.0:
            raise ProviderError("reliability must be between 0 and 1")
        if self.privacy_class not in PRIVACY_CLASSES:
            raise ProviderError("invalid privacy_class: " + str(self.privacy_class))
        if not isinstance(self.offline, bool):
            raise ProviderError("offline must be a boolean")
        object.__setattr__(self, "auth_kinds", auth)
        object.__setattr__(self, "reliability", float(self.reliability))
        object.__setattr__(self, "limitations",
                           _tuple_of(self.limitations, "limitations"))

    def supports(self, search_type: str, *, language: str | None = None,
                 recent_days: int | None = None) -> bool:
        if search_type not in self.search_types:
            return False
        if language and self.languages and language.lower() not in [
                item.lower() for item in self.languages]:
            return False
        if recent_days is not None and self.recency_days is not None \
                and recent_days > self.recency_days:
            return False
        return True

    def as_dict(self) -> dict:
        return {
            "provider_id": self.provider_id, "name": self.name,
            "search_types": list(self.search_types), "coverage": list(self.coverage),
            "languages": list(self.languages), "recency_days": self.recency_days,
            "auth_required": self.auth_required, "auth_kinds": list(self.auth_kinds),
            "cost_class": self.cost_class, "latency_class": self.latency_class,
            "rate_limit_per_min": self.rate_limit_per_min,
            "reliability": self.reliability, "privacy_class": self.privacy_class,
            "offline": self.offline, "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    provider_id: str
    available: bool
    reason: str
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", str(self.provider_id or "").strip())
        object.__setattr__(self, "reason", _text(self.reason, "status.reason", max_len=80))
        if not isinstance(self.available, bool):
            raise ProviderError("status.available must be a boolean")

    def as_dict(self) -> dict:
        return {"provider_id": self.provider_id, "available": self.available,
                "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class SearchQuery:
    text: str
    search_type: str = "web"
    language: str | None = None
    recent_days: int | None = None
    max_results: int = 10

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _text(self.text, "query.text", max_len=2000))
        if self.search_type not in SEARCH_TYPES:
            raise ProviderError("unsupported search_type: " + str(self.search_type))
        if self.language is not None:
            object.__setattr__(self, "language", _text(self.language, "query.language", max_len=20))
        if self.recent_days is not None:
            if not isinstance(self.recent_days, int) or self.recent_days < 0:
                raise ProviderError("query.recent_days must be a non-negative integer")
        if not isinstance(self.max_results, int) or not 1 <= self.max_results <= 100:
            raise ProviderError("query.max_results must be between 1 and 100")

    def as_dict(self) -> dict:
        return {"text": self.text, "search_type": self.search_type,
                "language": self.language, "recent_days": self.recent_days,
                "max_results": self.max_results}


@dataclass(frozen=True, slots=True)
class SearchResult:
    provider_id: str
    title: str
    url: str
    snippet: str = ""
    rank: int = 1
    published_at: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()
    untrusted: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _text(self.provider_id, "result.provider_id", max_len=80))
        object.__setattr__(self, "title", str(self.title or "").strip())
        try:
            canonical = canonicalize_url(str(self.url or ""))
        except ResearchModelError as exc:
            raise ProviderError("result.url is not a safe canonical URL: " + str(exc)) from exc
        object.__setattr__(self, "url", canonical)
        object.__setattr__(self, "snippet", str(self.snippet or "").strip())
        if not isinstance(self.rank, int) or self.rank < 1:
            raise ProviderError("result.rank must be a positive integer")
        object.__setattr__(self, "metadata", tuple(sorted(
            (str(name).strip(), str(value).strip())
            for name, value in (self.metadata or ()) if str(name).strip())))
        if self.untrusted is not True:
            raise ProviderError("search results are untrusted data and cannot be marked trusted")

    def as_dict(self) -> dict:
        return {"provider_id": self.provider_id, "title": self.title, "url": self.url,
                "snippet": self.snippet, "rank": self.rank,
                "published_at": self.published_at, "metadata": [list(p) for p in self.metadata],
                "untrusted": True}


@dataclass(frozen=True, slots=True)
class SearchResponse:
    provider_id: str
    query: SearchQuery
    status: ProviderStatus
    results: tuple[SearchResult, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(self.results or ()))
        for result in self.results:
            if result.provider_id != self.provider_id:
                raise ProviderError("response result belongs to another provider")
        limit = self.query.max_results
        if len(self.results) > limit:
            raise ProviderError("provider returned more results than requested")
        if not self.status.available and self.results:
            raise ProviderError("unavailable provider must not return results")

    @classmethod
    def unavailable(cls, provider_id: str, query: SearchQuery, reason: str,
                    detail: str = "") -> "SearchResponse":
        return cls(provider_id=provider_id, query=query,
                   status=ProviderStatus(provider_id, False, reason, detail))

    @classmethod
    def ok(cls, provider_id: str, query: SearchQuery,
           results: Iterable[SearchResult], note: str = "") -> "SearchResponse":
        return cls(provider_id=provider_id, query=query,
                   status=ProviderStatus(provider_id, True, STATUS_AVAILABLE), results=tuple(results),
                   note=note)

    def as_dict(self) -> dict:
        return {"provider_id": self.provider_id, "query": self.query.as_dict(),
                "status": self.status.as_dict(),
                "results": [item.as_dict() for item in self.results], "note": self.note}


@runtime_checkable
class SearchProvider(Protocol):
    """Minimal provider interface; no network or SDK is implied by this protocol."""

    provider_id: str
    capabilities: CapabilityMatrix

    def status(self) -> ProviderStatus:
        ...

    def search(self, query: SearchQuery) -> SearchResponse:
        ...


@runtime_checkable
class NoKeySearchAdapter(Protocol):
    """Declared interface for providers that need no credentials.

    Adapters must still declare capabilities and must fail honestly (unavailable)
    when no approved transport/config exists; this increment includes no real
    no-key adapter implementation.
    """

    provider_id: str
    capabilities: CapabilityMatrix

    def status(self) -> ProviderStatus:
        ...

    def search(self, query: SearchQuery) -> SearchResponse:
        ...


class UnavailableNoKeyAdapter:
    """Declared no-key adapter with no transport: honestly unavailable."""

    def __init__(self, capabilities: CapabilityMatrix,
                 reason: str = STATUS_NO_NETWORK_TRANSPORT, detail: str = ""):
        if capabilities.auth_required:
            raise ProviderError("UnavailableNoKeyAdapter requires a no-key capability matrix")
        self.capabilities = capabilities
        self.provider_id = capabilities.provider_id
        self._reason = reason
        self._detail = detail or ("no approved network transport/provider SDK in this "
                                  "increment; adapter interface only")

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.provider_id, False, self._reason, self._detail)

    def search(self, query: SearchQuery) -> SearchResponse:
        return SearchResponse.unavailable(self.provider_id, query, self._reason, self._detail)


@dataclass(frozen=True, slots=True)
class KnownUrl:
    url: str
    title: str = ""
    snippet: str = ""
    tags: tuple[str, ...] = ()
    retrieved: bool = True

    def __post_init__(self) -> None:
        try:
            canonical = canonicalize_url(str(self.url or ""))
        except ResearchModelError as exc:
            raise ProviderError("known URL is not safe/canonical: " + str(exc)) from exc
        object.__setattr__(self, "url", canonical)
        object.__setattr__(self, "title", str(self.title or "").strip())
        object.__setattr__(self, "snippet", str(self.snippet or "").strip())
        object.__setattr__(self, "tags", _tuple_of(self.tags, "known_url.tags"))


class OfflineKnownUrlProvider:
    """Deterministic offline provider over URLs already known to the system."""

    def __init__(self, known_urls: Sequence[KnownUrl | str],
                 provider_id: str = "offline-known-urls"):
        entries: list[KnownUrl] = []
        for item in known_urls or ():
            entries.append(item if isinstance(item, KnownUrl) else KnownUrl(url=str(item)))
        self._entries = tuple(sorted(entries, key=lambda entry: entry.url))
        self.provider_id = provider_id
        self.capabilities = CapabilityMatrix(
            provider_id=provider_id, name="Offline known-URL provider",
            search_types=("known-url", "web", "docs"), coverage=("local-known-urls",),
            languages=(), recency_days=None, auth_required=False, auth_kinds=("none",),
            cost_class="free", latency_class="low", rate_limit_per_min=1000,
            reliability=1.0, privacy_class="local", offline=True,
            limitations=("only URLs already known/retrieved in this process or store",
                         "no discovery, no ranking beyond deterministic title/tag matching"),
        )

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.provider_id, True, STATUS_AVAILABLE,
                              "offline known-URL provider; no network")

    def search(self, query: SearchQuery) -> SearchResponse:
        if not self.capabilities.supports(query.search_type, language=query.language,
                                          recent_days=query.recent_days):
            return SearchResponse.unavailable(self.provider_id, query, STATUS_POLICY_DENIED,
                                              "search type/language not supported")
        terms = [term.lower() for term in query.text.split() if term.strip()]
        matches: list[SearchResult] = []
        for entry in self._entries:
            haystack = " ".join((entry.url, entry.title, entry.snippet,
                                 " ".join(entry.tags))).lower()
            if terms and not all(term in haystack for term in terms):
                continue
            rank = len(matches) + 1
            matches.append(SearchResult(
                provider_id=self.provider_id, title=entry.title or entry.url,
                url=entry.url, snippet=entry.snippet, rank=rank,
                metadata=(("source", "offline-known-urls"),
                          ("tags", ",".join(entry.tags))),
            ))
            if len(matches) >= query.max_results:
                break
        return SearchResponse.ok(self.provider_id, query, matches,
                                 note="offline/known-url results only; no network")


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    provider_id: str
    capabilities: CapabilityMatrix
    enabled: bool = True
    kind: str = "no-key"
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _text(self.provider_id, "definition.provider_id", max_len=80))
        if self.capabilities.provider_id != self.provider_id:
            raise ProviderError("definition/capability provider_id mismatch")
        if self.kind not in ("placeholder", "no-key", "offline", "unavailable"):
            raise ProviderError("unsupported provider definition kind: " + str(self.kind))
        if not isinstance(self.enabled, bool):
            raise ProviderError("definition.enabled must be a boolean")


def capability_from_config(provider_id: str, value: Mapping) -> CapabilityMatrix:
    if not isinstance(value, Mapping):
        raise ProviderError("capability definition must be an object: " + provider_id)
    return CapabilityMatrix(
        provider_id=provider_id, name=str(value.get("name") or provider_id),
        search_types=value.get("search_types") or ("web",),
        coverage=value.get("coverage") or (), languages=value.get("languages") or (),
        recency_days=value.get("recency_days"), auth_required=bool(value.get("auth_required", False)),
        auth_kinds=tuple(value.get("auth_kinds") or (("api-key",) if value.get("auth_required") else ("none",))),
        cost_class=str(value.get("cost_class") or "free"),
        latency_class=str(value.get("latency_class") or "medium"),
        rate_limit_per_min=int(value.get("rate_limit_per_min") or 60),
        reliability=float(value.get("reliability", 0.5)),
        privacy_class=str(value.get("privacy_class") or "public"),
        offline=bool(value.get("offline", False)),
        limitations=tuple(value.get("limitations") or ()) or ("capabilities are declarative only",),
    )


class ProviderRegistry:
    """Validated provider definitions plus optional injected implementations."""

    def __init__(self) -> None:
        self._definitions: dict[str, ProviderDefinition] = {}
        self._providers: dict[str, SearchProvider] = {}

    def add_definition(self, definition: ProviderDefinition) -> None:
        if definition.provider_id in self._definitions:
            raise ProviderError("duplicate provider definition: " + definition.provider_id)
        self._definitions[definition.provider_id] = definition

    def add_provider(self, provider: SearchProvider) -> None:
        provider_id = str(provider.provider_id)
        if provider_id in self._providers:
            raise ProviderError("duplicate provider instance: " + provider_id)
        if provider_id in self._definitions:
            if self._definitions[provider_id].capabilities != provider.capabilities:
                raise ProviderError("provider instance capabilities do not match definition: "
                                    + provider_id)
        else:
            self.add_definition(ProviderDefinition(
                provider_id, provider.capabilities, enabled=True,
                kind=("offline" if provider.capabilities.offline else "no-key"),
                note="injected provider"))
        self._providers[provider_id] = provider

    def definition(self, provider_id: str) -> ProviderDefinition | None:
        return self._definitions.get(provider_id)

    def provider(self, provider_id: str) -> SearchProvider | None:
        return self._providers.get(provider_id)

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def available_ids(self) -> tuple[str, ...]:
        return tuple(sorted(pid for pid in self._definitions
                            if self._definitions[pid].enabled))

    def status(self, provider_id: str) -> ProviderStatus:
        definition = self._definitions.get(str(provider_id))
        if definition is None:
            return ProviderStatus(str(provider_id), False, STATUS_ADAPTER_MISSING,
                                  "provider is not registered")
        if not definition.enabled:
            return ProviderStatus(str(provider_id), False, STATUS_DISABLED,
                                  definition.note or "provider disabled by configuration")
        provider = self._providers.get(str(provider_id))
        if provider is None:
            return ProviderStatus(str(provider_id), False, STATUS_ADAPTER_MISSING,
                                  "declared provider has no executable adapter in this increment")
        return provider.status()

    def statuses(self) -> tuple[ProviderStatus, ...]:
        return tuple(self.status(pid) for pid in self.provider_ids())

    def providers_in_order(self) -> tuple[SearchProvider, ...]:
        return tuple(self._providers[pid] for pid in sorted(self._providers)
                     if self._definitions[pid].enabled)


def registry_from_config(config: Mapping | None = None,
                         providers: Sequence[SearchProvider] = ()) -> ProviderRegistry:
    """Build a registry from config definitions plus injected fake/local providers."""
    registry = ProviderRegistry()
    providers_map = {str(item.provider_id): item for item in providers or ()}
    raw_providers = (config or {}).get("providers") if isinstance(config, Mapping) else None
    if raw_providers is None:
        raw_providers = {}
    if isinstance(raw_providers, list):
        entries = {}
        for item in raw_providers:
            if not isinstance(item, Mapping):
                raise ProviderError("provider config entries must be objects")
            provider_id = _text(item.get("id") or item.get("provider_id"),
                                "provider.id", max_len=80)
            entries[provider_id] = item
        raw_providers = entries
    if not isinstance(raw_providers, Mapping):
        raise ProviderError("config.providers must be an object/list")
    for provider_id, item in raw_providers.items():
        if not isinstance(item, Mapping):
            raise ProviderError("provider definition must be an object: " + str(provider_id))
        capabilities = capability_from_config(str(provider_id), item.get("capabilities") or {})
        definition = ProviderDefinition(
            str(provider_id), capabilities,
            enabled=bool(item.get("enabled", True)),
            kind=str(item.get("kind") or "placeholder"),
            note=str(item.get("note") or ""),
        )
        registry.add_definition(definition)
    for provider_id, provider in providers_map.items():
        if provider_id not in registry._definitions:  # injected provider may self-declare
            registry.add_provider(provider)
        else:
            registry._providers[provider_id] = provider
            if registry._definitions[provider_id].capabilities != provider.capabilities:
                raise ProviderError("injected provider capabilities do not match config: "
                                    + provider_id)
    return registry


def default_registry(known_urls: Sequence[KnownUrl | str] = (),
                     providers: Sequence[SearchProvider] = ()) -> ProviderRegistry:
    """Registry with only local/declared providers (no network adapters exist)."""
    registry = ProviderRegistry()
    if known_urls:
        registry.add_provider(OfflineKnownUrlProvider(known_urls))
    for provider in providers or ():
        registry.add_provider(provider)
    return registry


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    priorities: tuple[str, ...] = ("reliability", "latency", "cost")
    allow_auth: bool = False
    max_cost: str = "free"
    privacy_mode: str = "any"
    require_offline: bool = False
    provider_allowlist: tuple[str, ...] = ()
    provider_denylist: tuple[str, ...] = ()
    min_reliability: float = 0.0

    def __post_init__(self) -> None:
        allowed = ("reliability", "latency", "cost", "coverage", "rate", "privacy")
        object.__setattr__(self, "priorities", _tuple_of(self.priorities, "priorities", allowed)
                           or ("reliability",))
        if self.max_cost not in COST_CLASSES:
            raise ProviderError("invalid max_cost: " + str(self.max_cost))
        if self.privacy_mode not in ("any", "local", "no-query-retention"):
            raise ProviderError("invalid privacy_mode: " + str(self.privacy_mode))
        if not 0.0 <= float(self.min_reliability) <= 1.0:
            raise ProviderError("min_reliability must be between 0 and 1")
        object.__setattr__(self, "provider_allowlist",
                           _tuple_of(self.provider_allowlist, "provider_allowlist"))
        object.__setattr__(self, "provider_denylist",
                           _tuple_of(self.provider_denylist, "provider_denylist"))


def _cost_rank(value: str) -> int:
    return {"free": 0, "freemium": 1, "paid": 2}.get(value, 9)


def _latency_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(value, 9)


def _eligible(registry: ProviderRegistry, capabilities: CapabilityMatrix,
              status: ProviderStatus, query: SearchQuery,
              policy: RoutingPolicy) -> list[str]:
    reasons: list[str] = []
    if not status.available:
        reasons.append("unavailable:" + status.reason)
    if policy.provider_allowlist and capabilities.provider_id not in policy.provider_allowlist:
        reasons.append("not-in-allowlist")
    if capabilities.provider_id in policy.provider_denylist:
        reasons.append("denylisted")
    if not capabilities.supports(query.search_type, language=query.language,
                                 recent_days=query.recent_days):
        reasons.append("unsupported-query-type/language/recency")
    if capabilities.auth_required and not policy.allow_auth:
        reasons.append("auth-required-but-auth-disabled")
    if _cost_rank(capabilities.cost_class) > _cost_rank(policy.max_cost):
        reasons.append("cost-class-above-policy")
    if policy.privacy_mode != "any":
        if policy.privacy_mode == "local" and capabilities.privacy_class != "local":
            reasons.append("privacy-not-local")
        if policy.privacy_mode == "no-query-retention" and capabilities.privacy_class == "public":
            reasons.append("privacy-public-retention")
    if policy.require_offline and not capabilities.offline:
        reasons.append("not-offline")
    if capabilities.reliability < float(policy.min_reliability):
        reasons.append("reliability-below-minimum")
    return reasons


def _score(capabilities: CapabilityMatrix, policy: RoutingPolicy) -> float:
    score = 0.0
    for priority in policy.priorities:
        if priority == "reliability":
            score += capabilities.reliability * 100.0
        elif priority == "latency":
            score += (2 - _latency_rank(capabilities.latency_class)) * 10.0
        elif priority == "cost":
            score += (2 - _cost_rank(capabilities.cost_class)) * 5.0
        elif priority == "coverage":
            score += min(len(capabilities.coverage), 5) * 2.0
        elif priority == "rate":
            score += min(capabilities.rate_limit_per_min, 120) / 60.0
        elif priority == "privacy":
            score += {"local": 10.0, "no-query-retention": 5.0, "public": 0.0}.get(
                capabilities.privacy_class, 0.0)
    return round(score, 6)


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    query: SearchQuery
    selected_provider: str | None
    status: ProviderStatus
    score: float = 0.0
    explanation: tuple[str, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()
    candidates: tuple[tuple[str, float], ...] = ()
    explicit: bool = False

    @property
    def available(self) -> bool:
        return self.selected_provider is not None and self.status.available

    def as_dict(self) -> dict:
        return {"query": self.query.as_dict(), "selected_provider": self.selected_provider,
                "status": self.status.as_dict(), "score": self.score,
                "explanation": list(self.explanation),
                "rejected": [list(item) for item in self.rejected],
                "candidates": [list(item) for item in self.candidates],
                "explicit": self.explicit,
                "available": self.available}


def select_provider(registry: ProviderRegistry, provider_id: str,
                    query: SearchQuery, policy: RoutingPolicy | None = None) -> RoutingDecision:
    """Explicit selection: never silently falls back to another provider."""
    policy = policy or RoutingPolicy()
    definition = registry.definition(provider_id)
    if definition is None:
        return RoutingDecision(query, None, ProviderStatus(provider_id, False,
                                                           STATUS_ADAPTER_MISSING,
                                                           "provider is not registered"),
                               explanation=("explicit selection refused: unknown provider "
                                            + str(provider_id),), explicit=True)
    status = registry.status(provider_id)
    reasons = _eligible(registry, definition.capabilities, status, query, policy)
    if reasons:
        return RoutingDecision(query, None, ProviderStatus(provider_id, False,
                                                           STATUS_EXPLICIT_REFUSED,
                                                           ", ".join(reasons)),
                               explanation=("explicit selection refused for " + provider_id
                                            + ": " + ", ".join(reasons),),
                               rejected=((provider_id, ",".join(reasons)),), explicit=True)
    return RoutingDecision(query, provider_id, ProviderStatus(provider_id, True,
                                                              STATUS_AVAILABLE),
                           score=_score(definition.capabilities, policy),
                           explanation=("explicit selection: " + provider_id,
                                        "capabilities: " + ", ".join(definition.capabilities.search_types)),
                           explicit=True)


def route(registry: ProviderRegistry, query: SearchQuery,
          policy: RoutingPolicy | None = None,
          preferred_provider: str | None = None) -> RoutingDecision:
    """Deterministic explainable routing; explicit preference is honoured/refused."""
    policy = policy or RoutingPolicy()
    if preferred_provider:
        return select_provider(registry, preferred_provider, query, policy)
    if not registry.provider_ids():
        return RoutingDecision(query, None, ProviderStatus("", False, STATUS_NO_PROVIDER,
                                                           "no providers are registered"),
                               explanation=("no providers are registered",))
    rejected: list[tuple[str, str]] = []
    candidates: list[tuple[str, float]] = []
    eligible: list[tuple[str, CapabilityMatrix, float]] = []
    for provider_id in registry.provider_ids():
        definition = registry.definition(provider_id)
        if definition is None:
            continue
        reasons = _eligible(registry, definition.capabilities,
                            registry.status(provider_id), query, policy)
        if reasons:
            rejected.append((provider_id, ",".join(reasons)))
            continue
        score = _score(definition.capabilities, policy)
        eligible.append((provider_id, definition.capabilities, score))
        candidates.append((provider_id, score))
    if not eligible:
        reasons = "; ".join(provider + "=" + why for provider, why in rejected[:8])
        return RoutingDecision(query, None, ProviderStatus("", False, STATUS_NO_PROVIDER,
                                                           "no provider satisfies routing policy"),
                               explanation=("no eligible provider; rejected: " + reasons,),
                               rejected=tuple(rejected))
    eligible.sort(key=lambda item: (-item[2], item[0]))
    winner_id, winner_caps, winner_score = eligible[0]
    explanation = [
        "routing policy priorities: " + ", ".join(policy.priorities),
        "eligible providers: " + ", ".join(e[0] + "=" + str(e[2]) for e in eligible),
        "selected " + winner_id + ": score " + str(winner_score)
        + ", reliability " + str(winner_caps.reliability)
        + ", cost " + winner_caps.cost_class
        + ", latency " + winner_caps.latency_class,
    ]
    if rejected:
        explanation.append("rejected: " + "; ".join(p + "=" + why for p, why in rejected[:8]))
    return RoutingDecision(query, winner_id,
                           ProviderStatus(winner_id, True, STATUS_AVAILABLE),
                           score=winner_score, explanation=tuple(explanation),
                           rejected=tuple(rejected), candidates=tuple(candidates))


def search_routed(registry: ProviderRegistry, query: SearchQuery,
                  policy: RoutingPolicy | None = None,
                  preferred_provider: str | None = None) -> tuple[RoutingDecision, SearchResponse]:
    """Route first, then call exactly the chosen provider (no fallback on failure)."""
    decision = route(registry, query, policy, preferred_provider=preferred_provider)
    if not decision.available or not decision.selected_provider:
        return decision, SearchResponse.unavailable("", query, decision.status.reason,
                                                    decision.status.detail)
    provider = registry.provider(decision.selected_provider)
    if provider is None:
        return decision, SearchResponse.unavailable(decision.selected_provider, query,
                                                    STATUS_ADAPTER_MISSING,
                                                    "selected provider has no executable adapter")
    try:
        response = provider.search(query)
    except Exception as exc:
        return decision, SearchResponse.unavailable(decision.selected_provider, query,
                                                    "provider-error",
                                                    type(exc).__name__ + ": " + str(exc))
    return decision, response


@dataclass(frozen=True, slots=True)
class MultiSourceReport:
    query: SearchQuery
    responses: tuple[SearchResponse, ...]
    by_url: tuple[tuple[str, tuple[str, ...]], ...]
    corroborated: tuple[str, ...]
    single_source: tuple[str, ...]
    disagreements: tuple[tuple[str, tuple[str, ...]], ...]
    provider_statuses: tuple[ProviderStatus, ...]
    unavailable: tuple[str, ...]
    min_sources: int = 2

    @property
    def verified(self) -> bool:
        return bool(self.corroborated)

    def as_dict(self) -> dict:
        return {"query": self.query.as_dict(),
                "responses": [item.as_dict() for item in self.responses],
                "by_url": [{"url": url, "providers": list(provider_ids)}
                           for url, provider_ids in self.by_url],
                "corroborated": list(self.corroborated),
                "single_source": list(self.single_source),
                "disagreements": [{"url": url, "titles": list(titles)}
                                  for url, titles in self.disagreements],
                "provider_statuses": [item.as_dict() for item in self.provider_statuses],
                "unavailable": list(self.unavailable),
                "min_sources": self.min_sources, "verified": self.verified}


def verify_multi_source(query: SearchQuery, responses: Sequence[SearchResponse],
                        *, min_sources: int = 2) -> MultiSourceReport:
    """Group results by canonical URL and report corroboration/disagreement."""
    if not isinstance(min_sources, int) or min_sources < 2:
        raise ProviderError("min_sources must be an integer >= 2")
    provider_statuses: list[ProviderStatus] = []
    unavailable: list[str] = []
    grouped: dict[str, set[str]] = {}
    titles: dict[str, set[str]] = {}
    results: dict[str, SearchResult] = {}
    for response in responses or ():
        provider_statuses.append(response.status)
        if not response.status.available:
            unavailable.append(response.provider_id)
            continue
        for item in response.results:
            grouped.setdefault(item.url, set()).add(response.provider_id)
            if item.title:
                titles.setdefault(item.url, set()).add(item.title)
            results.setdefault(item.url, item)
    corroborated = tuple(sorted(url for url, providers in grouped.items()
                                if len(providers) >= min_sources))
    single = tuple(sorted(url for url, providers in grouped.items()
                          if len(providers) == 1))
    disagreements = tuple(sorted(
        (url, tuple(sorted(values)))
        for url, values in titles.items() if len(values) > 1
    ))
    return MultiSourceReport(
        query=query, responses=tuple(responses or ()),
        by_url=tuple(sorted((url, tuple(sorted(providers)))
                            for url, providers in grouped.items())),
        corroborated=corroborated, single_source=single, disagreements=disagreements,
        provider_statuses=tuple(provider_statuses), unavailable=tuple(sorted(unavailable)),
        min_sources=min_sources,
    )


def multi_source_search(registry: ProviderRegistry, query: SearchQuery,
                        policy: RoutingPolicy | None = None, *,
                        limit_providers: int = 3, min_sources: int = 2) -> MultiSourceReport:
    """Call up to limit_providers of the best eligible providers and verify results."""
    if not isinstance(limit_providers, int) or limit_providers < 1:
        raise ProviderError("limit_providers must be a positive integer")
    policy = policy or RoutingPolicy()
    eligible: list[tuple[str, float]] = []
    for provider_id in registry.provider_ids():
        definition = registry.definition(provider_id)
        if definition is None:
            continue
        if not _eligible(registry, definition.capabilities,
                         registry.status(provider_id), query, policy):
            eligible.append((provider_id, _score(definition.capabilities, policy)))
    eligible.sort(key=lambda item: (-item[1], item[0]))
    responses: list[SearchResponse] = []
    for provider_id in registry.provider_ids():
        registry_status = registry.status(provider_id)
        if not registry_status.available:
            responses.append(SearchResponse(
                provider_id=provider_id, query=query, status=registry_status))
    for provider_id, _score_value in eligible[:limit_providers]:
        provider = registry.provider(provider_id)
        if provider is None:
            responses.append(SearchResponse.unavailable(
                provider_id, query, STATUS_ADAPTER_MISSING,
                "declared provider has no executable adapter"))
            continue
        try:
            responses.append(provider.search(query))
        except Exception as exc:
            responses.append(SearchResponse.unavailable(
                provider_id, query, "provider-error", type(exc).__name__ + ": " + str(exc)))
    return verify_multi_source(query, responses, min_sources=min_sources)

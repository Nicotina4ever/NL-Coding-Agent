# Universal Web Research engine - foundation (stage 7 research R1)

**Status:** FOUNDATION ONLY - first implementation increment. This is **not** a complete web-research engine. There are no search providers, no browser automation, no real network transport, no PDF/Office extraction, no knowledge store, no GUI and no model/agent integration. Real-network acceptance remains **MANUAL-PENDING** (NL-BP-203/211); fixture tests never count as real-network verification.

**Implemented requirements:** retrieval foundations for **NL-BP-170** (web page/document reader), **NL-BP-175** (untrusted-source handling) and **NL-BP-206** (retrieval safety policy). The search router (NL-BP-169/205), GitHub/Hugging Face investigators (NL-BP-171/172/207/208/209), research store (NL-BP-174), research planning (NL-BP-176), research GUI (NL-BP-210) and real-network acceptance (NL-BP-203/211) remain queued.

**Package:** `nl_coding_agent/research/` (new, standard library only). It does not modify existing app/tools files and imports no GUI, CrewAI, model, database or network library.

---

## 1. Architecture and boundaries

| Module | Responsibility |
|---|---|
| `models.py` | Immutable `Provenance`, `Source`, `RetrievedDocument`, `Citation` records; canonical URL, redirect chain, `fetched_at`, content type/charset, sha256/size, metadata, status code and the literal untrusted marker. |
| `policy.py` | Fail-closed `RetrievalPolicy`: scheme allowlist (HTTPS only by default), domain allow/deny with subdomain matching, SSRF blocking (loopback/private/link-local/multicast/reserved/non-public literal IPs and localhost names, with explicit exceptions), redirect budget, per-request timeout, max bytes, content-type allowlist, deterministic token bucket. Pure logic; DNS only through an injected resolver callback. |
| `fetch.py` | Transport-injected HTTP fetcher: manual redirect following, policy checks before and after every redirect, optional permission-gate callback, rate limiting, timeout/size/content-type enforcement, sha256/size, provenance, untrusted tagging. **No default network transport exists**; callers must inject one. |
| `reader.py` | Standard-library `HTMLParser` readable extraction: title, metadata, headings, paragraphs, lists, code/pre, links (resolved), basic tables, deterministic text + Markdown; plain text/markdown/JSON passthrough; PDF/Office/unknown formats return an explicit `UnsupportedDocument`. Scripts/iframes/styles are never executed and their content is dropped. |

### Retrieval policy defaults

| Setting | Default | Notes |
|---|---|---|
| Schemes | `https` only | add `http` explicitly only for a mission that needs it |
| Domains | any public host; optional allow/deny lists | deny wins; allow-list matches subdomains |
| SSRF | all non-public IPs and localhost names blocked | exceptions: exact host, IP or CIDR; optional resolver callback for DNS checks |
| Redirects | 5 | each redirect target is re-evaluated with the full policy |
| Timeout | 10 s per request | enforced by the fetcher with its monotonic clock |
| Body cap | 2,000,000 bytes | declared Content-Length and actual bytes checked |
| Content types | HTML/XHTML, text/plain, text/markdown, JSON | other types fail closed |
| Rate limit | 30/min, burst 5 | deterministic token bucket; shared per `Fetcher`; no sleeping |
| Ports | scheme default only unless `allowed_ports` is set | URL credentials always rejected |

Every decision carries a stable reason code (`scheme_denied`, `host_denied`, `private_network_blocked`, `redirect_limit_exceeded`, `content_type_denied`, `rate_limited`, `permission_denied`, ...) and an audit detail.

## 2. Fetch flow (no hidden network)

For every hop (initial request and each redirect):

1. `RetrievalPolicy.evaluate_url / evaluate_redirect` (scheme, credentials, domain, SSRF, port, redirect budget);
2. optional `permission_gate(url)` callback - future integration point for the existing permission broker/capability (web-fetch + NETWORK); `False`, a non-True value or an exception denies closed;
3. deterministic token-bucket rate limit;
4. injected `Transport.open(TransportRequest)` with `timeout_s` and `max_bytes`;
5. elapsed-time check, manual redirect handling (`Location` resolved with `urljoin`), HTTP status, content-type allowlist, declared and actual body size;
6. provenance: requested URL, final canonical URL, full redirect chain, UTC `fetched_at`, media type/charset, sha256, byte size, status code and `untrusted=True`;
7. return `RetrievedDocument` (decoded text) or raise `FetchDenied` / `FetchFailed` with the reason and partial redirect chain. No partial document is returned on failure.

The production URLLIB (or other) transport is deliberately **not** part of this increment: adding it requires the permission-broker integration and real-network acceptance. The fetcher requires an explicitly injected transport, so tests and accidental callers cannot reach the network.

**Not implemented in this increment:** caching, response-size resumable streaming, compression, cookies/auth headers, robots.txt, proxies, browser/JavaScript, PDF/Office conversion, search queries/providers, knowledge storage/embeddings and GUI.

## 3. Reader behaviour

- HTML is parsed locally with `html.parser`; the parser never executes scripts or loads resources.
- Extracts title (`title` then `og:title`/`twitter:title` then first heading), metadata (`meta name/property`), headings, paragraphs, ordered/unordered lists, code/pre blocks (language from `class=language-*`), links resolved against the final URL, and basic tables (header row detected).
- Produces deterministic plain text and Markdown; links are preserved as citations, tables become Markdown tables, code blocks are fenced (language preserved).
- Script/style/template/noscript/iframe/object/embed/svg/video content is dropped and the removed tag names are recorded; unsafe link schemes (`javascript:`, `data:`, `vbscript:`) are not preserved as links.
- Plain text, Markdown and valid JSON pass through unchanged (invalid JSON fails closed); PDF, Office and unknown binary media types return `UnsupportedDocument` with a clear reason - no external converter, macro execution or sample download.
- Output is bounded (`MAX_TEXT_CHARS = 500000`) and flagged with `truncated=True` when shortened.
- Every `ReadablePage`/`UnsupportedDocument` keeps the source and a `Citation`; the untrusted marker cannot be disabled.

## 4. Untrusted-content contract (NL-BP-175 foundation)

- `Provenance.untrusted`, `Source.untrusted`, `RetrievedDocument.untrusted`, `ReadablePage.untrusted` and `UnsupportedDocument.untrusted` are always `True`; constructing them with `False` raises `ResearchModelError`.
- Retrieved text is data, not instructions. The reader structures it; it never executes it, follows its links, changes permissions or calls models/tools.
- Prompt-injection resistance at the agent/model boundary (NL-BP-175 acceptance) and research decisions audit logging are **not** implemented here; this increment only provides the data marker and the retrieval-side enforcement.

## 5. Tests and evidence

Targeted tests (fixtures/fake transports only):

```
python -m pytest -q tests/test_research_policy.py tests/test_research_fetch.py tests/test_research_reader.py
# 69 passed
```

Coverage:
- policy: canonical URLs, default HTTPS-only, allow/deny/subdomain precedence, SSRF literal IPs/hostnames/resolver exceptions, redirect budget, content-type allowlist, deterministic token bucket, config validation/immutability and a static no-network-imports guard;
- fetch: success provenance (sha256/size/timestamp/redirect chain/untrusted), manual redirect chains, denied redirects (private IP/domain/http), max redirects/loops, timeout, size caps, content-type failures, permission-gate deny/raise/per-hop calls, shared rate limiting, transport/HTTP errors, charset decoding, JSON classification, required injected transport and static no-default-network guard;
- reader: local HTML fixture (title/metadata/headings/paragraphs/lists/code/links/tables), script/style/iframe dropped and not executed, Markdown structure, plain/Markdown/JSON passthrough, invalid JSON/PDF/Office/unknown fail-closed, title fallbacks, determinism/truncation and a static no-exec/third-party guard.

No test opens a socket, performs DNS, runs a model or touches the GUI.

## 6. MANUAL-PENDING: real-network acceptance

The following are explicitly not verified by this increment and must not be claimed as working:

- **Real HTTP(S) retrieval** needs a real transport plus an explicit NETWORK/web-fetch permission grant, owner authorization and external URLs. Fixtures only exercise the policy/fetcher logic.
- **Real-network research acceptance** (NL-BP-203/211) including live redirects/TLS/DNS, real rate limits, provider failures, HTML in the wild, PDFs/Office, JavaScript-heavy pages, caching/provenance retention and injection fixtures.
- **Platform behaviour** on real machines is unaffected by these pure-Python modules.
- **No platform support, release acceptance or research-quality claim** is made.

Any future evidence must label cases fixture-verified vs real-network-verified vs manual-pending; a fixture PASS never counts as real-network verification.

## 7. Security limitations (foundation honesty)

- DNS rebinding/TOCTOU: the policy can check injected resolver results, but a real transport must re-check the connected peer IP or use a pinned-IP/socket strategy; this increment cannot enforce that without a network transport.
- Policy URL checks are pre-request; redirects are re-checked manually, but no caching or TLS pinning exists.
- Content-type is header-derived; the reader refuses unknown/binary formats, but MIME spoofing remains possible (treated as untrusted anyway).
- No robots.txt/terms-of-service automation, no auth/cookie handling, no compression, no resume/range, no cache expiry (deferred to NL-BP-174/206 caching work).
- No prompt-injection model-level defence, no agent integration, no persistence/audit store.
- The allowed-domain/exception semantics are exact host/subdomain matching; wildcard/glob patterns and wildcard ports are intentionally not implemented.

## 8. Next increments (queued, not implemented)

1. Permission-broker integration: a NETWORK/web-fetch capability gate wired to the existing `core.permissions` broker and app services (read-only, fail-closed, audited).
2. Real transport adapter (stdlib opener or approved HTTP client) with connect-time SSRF re-check, TLS verification, compression, bounded streaming and cancellation.
3. Search provider registry/router (NL-BP-169/205), research cache/knowledge store and citations persistence (NL-BP-174/206), PDF/Office extraction via the existing local attachment pipeline only, and browser/JS automation under a separate grant (NL-BP-170 browser part).
4. GitHub/HF/ecosystem connectors (NL-BP-171/172/207/208/209), research-aware planning (NL-BP-176), Studio research workspace (NL-BP-210) and the fixture-vs-real-network acceptance matrix (NL-BP-203/211).

## 9. Files

| Path | Content |
|---|---|
| `nl_coding_agent/research/__init__.py` | public exports and foundation-status docstring |
| `nl_coding_agent/research/models.py` | provenance/source/document/citation models, canonical URL helpers |
| `nl_coding_agent/research/policy.py` | fail-closed retrieval policy, token bucket, decisions |
| `nl_coding_agent/research/fetch.py` | transport-injected safe fetcher, manual redirects, provenance |
| `nl_coding_agent/research/reader.py` | stdlib HTML reader, passthrough, unsupported-format result |
| `tests/test_research_policy.py` | policy/SSRF/rate/validation tests |
| `tests/test_research_fetch.py` | fake-transport fetch/redirect/limit/permission tests |
| `tests/test_research_reader.py` | local HTML fixture/reader/passthrough/unsupported tests |

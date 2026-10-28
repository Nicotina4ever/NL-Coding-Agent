# Universal Web Research engine - R1 foundation, R2 providers/store, R3 investigators, R4 service/transport, R7 injection resistance, R8 mission attachments/retention (stage 7 research)

**Status:** R1 FOUNDATION + R2 PROVIDERS/STORE + R3 READ-ONLY INVESTIGATORS + R4 SERVICE/TRANSPORT + R7 INJECTION RESISTANCE + R8 MISSION ATTACHMENTS/RETENTION (fixtures/fake transports only). This is **not** a complete web-research engine. R4 adds an explicitly constructed, permission-gated stdlib HTTP transport, the ResearchService permission/auto-review boundary and typed read-only research tool descriptors. There is still no implicit/default network transport, no live provider adapter, no real-network acceptance, browser automation, PDF/Office extraction, GUI or full model/agent integration. Provider capabilities remain declarative; live provider/network acceptance remains **MANUAL-PENDING** (NL-BP-203/211), and fixture tests never count as real-network verification.

**Implemented requirements:** retrieval foundations for **NL-BP-170** (web page/document reader), **NL-BP-175** (untrusted-source handling) and **NL-BP-206** (retrieval safety policy); R2 provider registry/router and local knowledge store for **NL-BP-169/205/174**; R3 read-only GitHub/HF investigator contracts for **NL-BP-171/172/207**; R4 permission-bounded ResearchService, explicit stdlib HTTP transport path and typed read-only research tool descriptors for **NL-BP-170/174/175/205/207**; R7 completion of **NL-BP-175** untrusted-source/prompt-injection detection, redacted warnings and audit on the same stack; R8 revocable finding-to-mission attachments, non-destructive stale/expired retention and the Research workspace attachment/retention UI for **NL-BP-210** (GUI slice with injected fake services). Remaining: live provider adapters/live network acceptance (NL-BP-203/211), research planning (NL-BP-176), remaining ecosystem connectors (NL-BP-208/209), GUI/model wiring of the tool descriptors, real-network GUI acceptance and the cache/embeddings extensions.

**Package:** `nl_coding_agent/research/` (standard library only). It imports no GUI, CrewAI, model or network library; R2's store uses the existing application SQLite database additively (new `research_*` tables only).

---

## 1. Architecture and boundaries

| Module | Responsibility |
|---|---|
| `models.py` | Immutable `Provenance`, `Source`, `RetrievedDocument`, `Citation` records; canonical URL, redirect chain, `fetched_at`, content type/charset, sha256/size, metadata, status code and the literal untrusted marker. |
| `policy.py` | Fail-closed `RetrievalPolicy`: scheme allowlist (HTTPS only by default), domain allow/deny with subdomain matching, SSRF blocking (loopback/private/link-local/multicast/reserved/non-public literal IPs and localhost names, with explicit exceptions), redirect budget, per-request timeout, max bytes, content-type allowlist, deterministic token bucket. Pure logic; DNS only through an injected resolver callback. |
| `fetch.py` | Transport-injected HTTP fetcher: manual redirect following, policy checks before and after every redirect, optional permission-gate callback, rate limiting, timeout/size/content-type enforcement, sha256/size, provenance, untrusted tagging. **No default network transport exists**; callers must inject one. |
| `reader.py` | Standard-library `HTMLParser` readable extraction: title, metadata, headings, paragraphs, lists, code/pre, links (resolved), basic tables, deterministic text + Markdown; plain text/markdown/JSON passthrough; PDF/Office/unknown formats return an explicit `UnsupportedDocument`. Scripts/iframes/styles are never executed and their content is dropped. |
| `providers.py` | Declarative search-provider contract: validated `CapabilityMatrix` (search types, coverage/languages/recency, auth, cost, rate, latency, privacy, reliability, limitations), `SearchProvider`/`NoKeySearchAdapter` protocols, config+injected `ProviderRegistry`, offline known-URL provider, honest unavailability statuses, deterministic policy routing with explanations/refusals and multi-source corroboration/disagreement verification. No real network transport or provider SDK exists. |
| `store.py` | Additive, idempotent SQLite research store through the application database: bounded `research_sources` (canonical URL/redirect chain/provider/title/excerpt/content sha256/metadata/retrieved timestamps/scope/confidence/stale/expired state), `research_findings`, `research_citations`, `research_conflicts` and append-only `research_finding_attachments` (finding/mission link, source, attached_by, created_at, revoked_at; unique active pair). Dedupe by canonical URL/content hash, stale/expiry/refresh queries, bounded project/mission/text search, revocable mission attachments and non-destructive retention. No secrets, credentials or wholesale project content and no hard-delete API. |
| `transport.py` | Explicit stdlib urllib transport implementing the injected HttpTransport contract: permission gate required at construction, GET/HEAD only, https default (http only if explicitly enabled), URL credentials rejected, no CR/LF headers, bounded timeout/bytes, redirects returned as 3xx (never followed) for the fetcher to re-evaluate. No module-level opener and no implicit network use. |
| `service.py` | Permission-bounded ResearchService: provider routing, policy fetcher, reader, store, GitHub/HF investigators. Every network-capable operation calls permissions.check_capability and auto_review.evaluate_action first and returns explicit allowed/needs_approval/denied/error results (no exception leakage for normal policy decisions). Search/fetch/lookups store provenance + citations; save/list/search/mark-stale/refresh findings are exposed. No default transport, cloud call, secret logging or silent fallback. |
| `tools.py` | Typed read-only descriptors for web_search/web_fetch/github_lookup/huggingface_lookup with capability/scope mapping, bounded input/output schemas, citation/provenance requirements and a register function. Explicitly no write/install/publish/upload/download tool; descriptors contain no execution or network implementation. |
| `github.py` | Read-only GitHub REST investigator through an injected `HttpTransport`: repo metadata/README/license, branches/tags, commits, issues+comments, PRs+reviews, releases, workflows, file contents at a pinned ref, repository search. Every result carries canonical API URL, repo full name, requested ref, resolved commit SHA (when resolvable), timestamp and untrusted marker. Optional token is injected/env and never logged; bounded pagination/size; typed auth/rate-limit/not-found/response errors; GET-only, no repository copy/execution/writes. |
| `huggingface.py` | Read-only Hub API investigator through the same injected transport: model/dataset/Space search+metadata, model card text, revision/sha, files (paths/sizes/formats/quantizations), license/gated/private flags and pipeline/tags. Coarse RAM/VRAM/disk estimates derive from file metadata and are explicitly marked estimates with uncertainty. No checkpoint retrieval, no license acceptance, no code execution; bounded/typed errors; optional token never logged. |

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
- R7 now adds content-side prompt-injection detection, redacted warnings and source='research' injection audit events on top of this trust marker (section 4f). Model/agent-level prompt isolation is still **not** implemented; content detection is heuristic, not a sandbox.


## 4b. Search-provider registry and routing (R2, NL-BP-169/205 foundation)

- Every provider declares a validated `CapabilityMatrix`: supported search
  types (web/docs/code/academic/news/known-url/local), coverage, languages,
  recency, auth requirement/kinds, cost class, latency class, per-minute rate
  limit, reliability 0-1, privacy class and known limitations.
- `ProviderRegistry` is built from config definitions plus injected provider
  instances. Config entries are validated; disabled definitions report
  disabled; definitions without an executable adapter report adapter-missing;
  injected capabilities must match the config declaration.
- The only built-in executable provider is `OfflineKnownUrlProvider`, which
  searches URLs already known/retrieved locally and never touches the network.
  `NoKeySearchAdapter` is the declared interface for future credential-free
  providers; `UnavailableNoKeyAdapter` reports no-network-transport honestly.
- Routing is explicit (`select_provider`) or deterministic (`route`):
  eligible providers are filtered by search type/language/recency,
  auth/cost/privacy/reliability policy, allow/deny lists and offline
  requirements; the score is a stable weighted sum with provider-id tie-break,
  and every decision carries candidate scores, rejected reasons and a
  human-readable explanation. Explicit selection never silently falls back; a
  provider error returns an unavailable response for the selected provider.
- `verify_multi_source` groups results by canonical URL and reports
  corroborated URLs (>= min_sources distinct providers), single-source URLs,
  metadata disagreements, provider statuses and honest unavailability.
  `multi_source_search` calls up to N best eligible providers; fixture
  providers are never treated as real agreement.

## 4c. Local research knowledge store (R2, NL-BP-174 foundation)

- Additive tables are created with `CREATE TABLE/INDEX IF NOT EXISTS` on the
  existing application SQLite database; the store calls the normal
  `init_db` path, preserves existing tables and is idempotent across restarts.
- `research_sources` stores canonical URL (unique), requested/final URL,
  redirect chain, provider, title, bounded excerpt, content sha256, content
  type, size, sorted metadata, retrieval/created/updated timestamps,
  project/mission/task links, confidence and stale/refresh state. The same
  canonical URL plus content hash is idempotent; changed content refreshes the
  same row and clears stale.
- `research_findings` (bounded question/answer excerpt, confidence, scope,
  source ids, stale state), `research_citations` (source/finding with
  bounded quote/locator/note) and `research_conflicts` (two sources
  disagreeing on a finding) use deterministic keys and are idempotent.
- Listing/search is bounded (limit <= 200) and scoped by project/mission/task
  and text; stale/expiry queries and explicit `mark_source_stale` /
  `mark_finding_stale` / `refresh_source` / `mark_expired` are
  supported.
- Rejected input: credentials in URLs, non-http(s) schemes, excerpt/answer over
  4,000 characters, metadata keys that look secret (password/token/api-key/
  cookie/authorization/credential) and invalid confidence/scope ids. There is no
  deletion API and no whole-project source ingestion.


## 4d. ResearchService and permission boundary (R4, NL-BP-170/174/175/205/207 foundation)

- `ResearchService` combines `ProviderRegistry` routing, the policy fetcher,
  the reader, the research store and the GitHub/Hugging Face investigators.
- Before any network-capable operation it calls both
  `permissions.check_capability` (web-search/web-fetch/download/model-inference-
  local/cloud mapping as applicable) and `auto_review.evaluate_action` with the
  capability/scope/action descriptor. Normal policy outcomes are explicit
  `ResearchResult` objects: allowed, needs_approval, denied, unavailable or
  error; they are not raised past the boundary.
- `fetch_read` wires the fetcher permission gate to the same boundary for every
  URL/redirect hop, returns the boundary decision when approval/denial stops the
  fetch, then reads the page with the existing reader and stores canonical URL/
  redirect chain/provider/fetched-at/content sha256/title/metadata/bounded excerpt/
  project/mission/task links plus a citation. Unsupported formats are stored as
  explicit unsupported sources, never silently converted.
- `search` routes through declared providers (offline known-URL provider in this
  increment); `github_lookup`/`huggingface_lookup` call the read-only
  investigators only through an injected explicit HTTP transport and persist
  their provenance/citations. `save_finding`, `list_findings`,
  `search_saved`, `mark_stale` and `refresh_source` wrap the local store.
- No fetch or HTTP transport is created by default; service construction with no
  transport reports honest unavailability. Tokens are optional explicit
  constructor inputs and never appear in `repr`, results or errors.

## 4e. Explicit HTTP transport and typed tools (R4)

- `StdlibHttpTransport` is urllib-based, but construction requires an explicit
  permission gate and an injected opener is supported for tests. It is read-only
  (GET/HEAD), rejects credentials/non-allowed schemes/unsafe headers, caps
  timeout/bytes, calls the gate before I/O and returns 3xx responses instead of
  following redirects (the policy fetcher handles redirects).
- `tools.py` declares web_search/web_fetch/github_lookup/huggingface_lookup as
  read-only descriptors with capability/scope mapping, input/output schemas,
  citation/provenance requirements and a small registry/register helper. There is
  no write/install/publish/upload/download tool, and descriptors do not execute
  anything or import a provider SDK.
- These tools are not yet wired to the GUI/model-facing tool surface; that
  integration remains future work and must preserve the same boundary.

## 4f. Prompt-injection resistance (R7, NL-BP-175)

The new `nl_coding_agent/research/injection.py` scanner treats all fetched/searched
content as data, never as instructions. It is bounded, deterministic and passive:
it never executes commands, evaluates HTML/JS, calls tools, follows links or touches
the network. It scans text/markdown/HTML and recursively scans result payloads for:

- instruction/system-prompt overrides ("ignore previous instructions", system/developer prompt);
- role overrides ("you are now", pretend/act-as/developer role);
- tool/command execution requests (shell, terminal, subprocess, eval/exec, powershell, curl, rm -rf);
- secret/exfiltration requests (API keys, tokens, passwords, env vars, credentials, .env, SSH keys);
- URL-assisted instructions and javascript:/data:/file: links;
- hidden/zero-width HTML/markdown text (HTML comments, display:none/visibility:hidden/
  font-size:0/opacity:0, hidden attributes, zero-width Unicode) including zero-width
  obfuscation of instruction phrases.

Each immutable `InjectionSignal` carries kind, severity, a redacted bounded excerpt
(the matched span and surrounding instruction/URL content are replaced with [REDACTED]),
a SHA-256 of the matched span, offset and source path. `InjectionScan` carries bounded
signals, scanned size/truncation, content SHA-256 and untrusted=True. Warnings returned
to callers are capped at 10 and never contain the raw instruction payload.

Integration (ResearchService):
- `fetch_read` scans the raw decoded document plus reader text/markdown/metadata before
  returning; results include `untrusted=True`, `injection_warnings` and a bounded
  `injection_scan` summary. The page payload also carries the warnings.
- `search` scans result titles/snippets and returns the same warning fields.
- `github_lookup` / `huggingface_lookup` scan investigator result payloads (README,
  model card, metadata) before returning.
- For every detected signal, an `events` row with `source='research'` and
  `event_kind='research_injection'` records only operation, URL, ref/source id, kind,
  SHA-256/hash; no instruction text, excerpt or arbitrary content is audited. Audit rows
  survive restart and are bounded per result.
- Permission/auto-review remains a separate, earlier gate: denied/needs-approval operations
  return no content, no warnings and write no injection audit events. No content trust is
  inferred from a successful permission check.

Limits: this is heuristic detection, **not a sandbox or a guarantee**. It does not prove
content safe, cannot catch every paraphrase/encoding, and never sanitizes or executes
anything. Instructions found in content must continue to be ignored by callers; no model
is called by the scanner or service integration.

## 5. Tests and evidence

Targeted tests (fixtures/fake transports only):

```
python -m pytest -q tests/test_research_policy.py tests/test_research_fetch.py tests/test_research_reader.py tests/test_research_github.py tests/test_research_huggingface.py tests/test_research_providers.py tests/test_research_store.py tests/test_research_transport.py tests/test_research_service.py tests/test_research_tools.py tests/test_research_injection.py
# R7 adds tests/test_research_injection.py (scanner + integration); see the file table below
```

Coverage:
- policy: canonical URLs, default HTTPS-only, allow/deny/subdomain precedence, SSRF literal IPs/hostnames/resolver exceptions, redirect budget, content-type allowlist, deterministic token bucket, config validation/immutability and a static no-network-imports guard;
- fetch: success provenance (sha256/size/timestamp/redirect chain/untrusted), manual redirect chains, denied redirects (private IP/domain/http), max redirects/loops, timeout, size caps, content-type failures, permission-gate deny/raise/per-hop calls, shared rate limiting, transport/HTTP errors, charset decoding, JSON classification, required injected transport and static no-default-network guard;
- reader: local HTML fixture (title/metadata/headings/paragraphs/lists/code/links/tables), script/style/iframe dropped and not executed, Markdown structure, plain/Markdown/JSON passthrough, invalid JSON/PDF/Office/unknown fail-closed, title fallbacks, determinism/truncation and a static no-exec/third-party guard.
- providers: capability validation, config/injected registry and statuses, offline known-URL provider, no-key adapter honesty, deterministic routing/explanation/policy filters, explicit selection/refusal/no fallback, multi-source corroboration/disagreement/unavailability and static no-network/SDK guards;
- store: idempotent additive schema+legacy table preservation, restart persistence, canonical URL/content-hash dedupe and refresh, project/mission isolation, bounded text search/list, stale/expiry/mark-stale/refresh, citations/findings dedupe, conflicts, unsafe/secret/oversized-content rejection and static no-network/no-file-read guards.
- transport: explicit permission-gate requirement, GET/HEAD-only, scheme/credential/header validation before I/O, response byte caps, redirect-not-followed, fake opener only and static no-implicit-network guards;
- service: allowed/needs-approval/denied/auto-review outcomes, no default transport, fetch permission gate per hop, reader+store provenance/citations, GitHub/HF provenance persistence, finding/store wrappers, token redaction and no secret logging;
- tools: descriptor uniqueness/read-only/capability-scope/schema mapping, registry/register compatibility, forbidden write/install/publish/download names and static no-exec/no-network guards.

No test opens a socket, performs DNS, runs a model or touches the GUI.

## 6. MANUAL-PENDING: real-network acceptance

The following are explicitly not verified by this increment and must not be claimed as working:

- **Real HTTP(S) retrieval** needs a real transport plus an explicit NETWORK/web-fetch permission grant, owner authorization and external URLs. Fixtures only exercise the policy/fetcher logic.
- **Real-network research acceptance** (NL-BP-203/211) including live redirects/TLS/DNS, real rate limits, provider failures, HTML in the wild, PDFs/Office, JavaScript-heavy pages, caching/provenance retention and injection fixtures.
- **Real search providers**: R2 provider capabilities are declarative; there is no
  real transport/key adapter, no provider uptime/latency/quality measurement and no
  real multi-source agreement claim.
- **Store acceptance**: tables/citations persist locally with fixture data only;
  encryption-at-rest, retention/GC policy, cross-process contention and real
  provenance acceptance are NOT verified.
- **Live network acceptance (R4)**: the explicit StdlibHttpTransport exists but is
  never exercised against a real socket in this increment; real TLS/DNS/redirects/
  rate limits, live provider adapters and real permission grants remain
  MANUAL-PENDING (NL-BP-203/211). Fixture tests prove wiring only.
- **Tool-surface integration**: research tool descriptors are typed but not yet
  wired to the model/GUI tool surface, so no end-to-end agent research action is
  claimed.
- **Platform behaviour** on real machines is unaffected by these pure-Python modules.
- **No platform support, release acceptance or research-quality claim** is made.

Any future evidence must label cases fixture-verified vs real-network-verified vs manual-pending; a fixture PASS never counts as real-network verification.

## 7. Security limitations (foundation honesty)

- **Prompt-injection detection is heuristic, not a sandbox.** R7 flags instruction-like
  content and redacts warnings/audit, but cannot prove a page safe, cannot catch every
  paraphrase/encoding and does not sanitize or follow content. Callers must still treat all
  retrieved content as data and never execute instructions found in it.

- DNS rebinding/TOCTOU: the policy can check injected resolver results, but a real transport must re-check the connected peer IP or use a pinned-IP/socket strategy; this increment cannot enforce that without a network transport.
- Policy URL checks are pre-request; redirects are re-checked manually, but no caching or TLS pinning exists.
- Content-type is header-derived; the reader refuses unknown/binary formats, but MIME spoofing remains possible (treated as untrusted anyway).
- No robots.txt/terms-of-service automation, no auth/cookie handling, no compression, no resume/range, no cache expiry (deferred to NL-BP-174/206 caching work).
- No model/agent-level prompt-injection defence or agent integration; R7 only provides content-side detection/redacted warnings and an injection-signal audit log (not a full research-decision audit).
- Provider capability matrices are declarations, not verified contracts; routing is
  deterministic over those declarations, not evidence of provider quality.
- The research store is local SQLite only: no encryption at rest, retention policy,
  dedupe across databases or provenance signature; excerpts are bounded but the
  database still contains research evidence the owner may consider sensitive.
- The service deliberately calls both the capability boundary and auto-review; a
  consumed allow-once grant can make a second real permission evaluation fail, so
  durable mission/project grants (not one-shot grants) should be used for research
  workflows until the boundary is consolidated.
- The stdlib transport is not a security sandbox: policy/redirect/size checks are
  application-level, real DNS rebinding/TLS pinning/peer-IP verification are not
  implemented and the transport must only be constructed by trusted service code
  with a real permission gate.
- The allowed-domain/exception semantics are exact host/subdomain matching; wildcard/glob patterns and wildcard ports are intentionally not implemented.

## 8. Next increments (queued, not implemented)

1. Permission-broker integration: a NETWORK/web-fetch capability gate wired to the existing `core.permissions` broker and app services (read-only, fail-closed, audited).
2. Real transport adapter (stdlib opener or approved HTTP client) with connect-time SSRF re-check, TLS verification, compression, bounded streaming and cancellation.
3. Live provider adapters using the R4 explicit transport (permission/NETWORK gating, capability verification, real rate limits), tool-surface integration of the R4 descriptors, store UI/retention/encryption and cache/embeddings extensions (NL-BP-169/205/174/206), PDF/Office extraction via the existing local attachment pipeline only, and browser/JS automation under a separate grant (NL-BP-170 browser part).
4. Remaining ecosystem connectors (NL-BP-208/209), real-network transport/permission integration for the GitHub/HF clients and real-network acceptance (NL-BP-203/211), research-aware planning (NL-BP-176), Studio research workspace (NL-BP-210) and the fixture-vs-real-network acceptance matrix.

## 9. Files

| Path | Content |
|---|---|
| `nl_coding_agent/research/__init__.py` | public exports and foundation-status docstring |
| `nl_coding_agent/research/models.py` | provenance/source/document/citation models, canonical URL helpers |
| `nl_coding_agent/research/policy.py` | fail-closed retrieval policy, token bucket, decisions |
| `nl_coding_agent/research/fetch.py` | transport-injected safe fetcher, manual redirects, provenance |
| `nl_coding_agent/research/reader.py` | stdlib HTML reader, passthrough, unsupported-format result |
| `tests/test_research_policy.py` | policy/SSRF/rate/validation tests |
| `github.py` / `tests/test_research_github.py` | GitHub read-only REST contract, injected fake transport, ref pinning/provenance/auth/pagination/errors/static guards (8 tests) |
| `huggingface.py` / `tests/test_research_huggingface.py` | Hub API metadata/model card/files/estimates/license/gated flags/errors/no-retrieval/static guards (7 tests) |
| `tests/test_research_fetch.py` | fake-transport fetch/redirect/limit/permission tests |
| `tests/test_research_reader.py` | local HTML fixture/reader/passthrough/unsupported tests |
| `nl_coding_agent/research/providers.py` | declarative provider registry/router, offline known-URL provider, multi-source verification (no network/SDK) |
| `nl_coding_agent/research/store.py` | additive research sources/citations/findings/conflicts SQLite store, dedupe/staleness/search |
| `tests/test_research_providers.py` | capability/selection/routing/refusal/offline/multi-source/static tests (15) |
| `tests/test_research_store.py` | schema/dedupe/citation/isolation/staleness/search/persistence/static tests (11) |
| `nl_coding_agent/research/transport.py` | explicit permission-gated stdlib urllib HttpTransport; no implicit network |
| `nl_coding_agent/research/service.py` | ResearchService permission/auto-review boundary, search/fetch/read/store/investigators |
| `nl_coding_agent/research/tools.py` | typed read-only research tool descriptors and registry (no execution) |
| `tests/test_research_transport.py` | fake-opener transport/scheme/credential/limit/redirect/static tests (8) |
| `tests/test_research_service.py` | boundary/allowed/approval/denied/fetch/store/investigator/static tests (11) |
| `tests/test_research_tools.py` | descriptor/capability/schema/registry/static tests (7) |
| `nl_coding_agent/research/injection.py` | bounded deterministic prompt-injection scanner, immutable redacted signals/warnings (no execution) |
| `tests/test_research_injection.py` | injection scanner/HTML/GitHub/HF/service integration/audit/redaction/no-execution tests (R7) |

# Universal Web Research & Intelligence Engine - Capability Audit (read-only)

**Task:** shared task-60. **Date:** 2026-10-28 (Europe/Rome). **Repository:** `K:\AI\NL Coding Agent` at git HEAD `e88dfd8` (clean working tree before this task).
**Type:** read-only capability audit + queue-only backlog input. **No feature was implemented, no application code was modified, and no model, mission or network run was started.**
**User directive under audit:** "Universal Web Research & Intelligence Engine" (2026-10-28, high priority; queue only).

---

## 1. Executive summary

The application has **no external web-research capability today**. What exists is limited to:

1. **Loopback HTTP probes via Python stdlib `urllib`** for Ollama/model-provider discovery and fixed external-tool health checks - never a general web fetch, search or page reader.
2. **A local stdio MCP client/manager** that reads a local JSON config, performs read-only `tools/list`, and requires explicit human approval (+ NETWORK grant for network-declared servers) for `tools/call`. **No GitHub/HF/web MCP server is bundled or configured by default** (`config/mcp_servers.json` and `data/mcp_servers.json` do not exist).
3. **Permission scopes for NETWORK and CLOUD** (fail-closed, default denied) that are enforced for cloud/remote model routes, network-declared MCP servers and terminal network commands. They are **not yet applied to any web-research tool because no such tool exists**.
4. **A local-only multimodal attachment pipeline** (files/folders/clipboard, text/PDF/XLSX/DOCX/PPTX/image extraction when optional libraries are present; audio/video deferred) with SQLite provenance. It accepts existing local paths only - there is no URL intake.

Absent: web search/router/providers, page/HTML/PDF/JS reader, browser automation, GitHub API client, Hugging Face Hub client, ecosystem/package research, research knowledge store or embeddings, research GUI workspace, domain/SSRF/rate policy for retrieval.

The existing addendum-imported requirements **NL-BP-169..176 and NL-BP-203** already cover most of the requested research engine. Seven genuine remaining gaps were registered as pending requirements **NL-BP-205..211** (stage 7) after the dedupe mapping in section 5.

## 2. Method and evidence rules

- Static read-only inspection of the product tree (`nl_coding_agent/**`) plus `pyproject.toml`, `config/` and `data/`; commands used are listed in section 8.
- Line references are to the current files at the audit HEAD.
- "Implemented" means code exists in the product tree; it does **not** mean real-network research was exercised. No HTTP request, model inference, mission or install was performed by this audit.
- The user directive's premises were cross-checked and are confirmed below, with two precision notes: (a) attachment extraction of PDF/Office exists locally when optional libraries are installed; (b) the permission engine is enforced for model routes/MCP/terminal network commands but remains unused for web research because no web-research tools exist.

## 3. Existing capability evidence

### 3.1 Stdlib urllib HTTP - local model/provider probes only

| Evidence | Finding |
|---|---|
| `nl_coding_agent/models/ollama_registry.py:6-7` | imports only `urllib.request` / `urllib.error` (stdlib); no third-party HTTP client |
| `nl_coding_agent/models/ollama_registry.py:12` | default endpoint is `http://localhost:11434` (loopback) |
| `nl_coding_agent/models/ollama_registry.py:45-51` | `check_ollama_reachable` GETs `{base_url}/api/tags` only |
| `nl_coding_agent/models/ollama_registry.py:54-88` | model list GETs `{base_url}/api/tags`, falls back to the local `ollama list` CLI |
| `nl_coding_agent/models/ollama_registry.py:91-100` | loaded models GET `{base_url}/api/ps` only |
| `nl_coding_agent/models/providers.py:7-8, 80-84` | shared `_http_json()` helper builds a `urllib.request.Request` and reads JSON; no HTML parsing, no search, no download API |
| `nl_coding_agent/models/providers.py:20, 186-240` | Ollama/OpenAI-compatible providers call only the configured provider's `/models` (and Ollama `/api/tags`, `/api/ps`); errors are returned as snapshots |
| `nl_coding_agent/tools/registry.py:22, 206-220` | `_probe_http()` GETs a single registered health endpoint with timeout; used only for the Ollama entry |
| `nl_coding_agent/tools/registry.py:115-175` | builtin tools are fixed argv probes for git/python/pytest/ollama/ffmpeg; the only `probe_url` is `<loopback ollama>/api/tags` at lines 160-162 |

**Conclusion:** `urllib` is used exclusively as a small JSON/health probe client for local model providers and the Ollama tool entry. There is no generic URL fetch API, no search-provider integration, no HTML-to-text layer and no browser transport.

### 3.2 Local stdio MCP client/manager - gated, no bundled research servers

| Evidence | Finding |
|---|---|
| `nl_coding_agent/app/mcp.py:1-7` | module contract: "No auto-execution and no network" (network-capable servers require NETWORK grant); local JSON config only |
| `nl_coding_agent/app/mcp.py:43-63` | config loaded from `NL_MCP_CONFIG`, `data/mcp_servers.json` or `config/mcp_servers.json`; returns `{"servers": {}}` when none exists |
| `nl_coding_agent/app/mcp.py:66-87` | only `transport == "stdio"` accepted (lines 75-79); server command/args/env/network flag are local config |
| `nl_coding_agent/app/mcp.py:90-134` | `_StdioTransport` launches the configured local command as a subprocess and speaks JSON on stdio |
| `nl_coding_agent/app/mcp.py:212-220` | `list_tools()` performs read-only `tools/list` and closes the client |
| `nl_coding_agent/app/mcp.py:222-248` | `invoke_tool()` refuses without `human_approved=True` (226-228), requires NETWORK grant when the server declares `network` (229-233), writes an audit event (234-241), then calls `tools/call` |
| `nl_coding_agent/app/services.py:137-149` | service facade exposes `mcp_servers()`, `mcp_tools()`, `mcp_invoke_tool(..., human_approved=...)` |
| `config/ (dir listing)`; checks for `config/mcp_servers.json` and `data/mcp_servers.json` | **both absent** - no MCP server is bundled/configured by default |
| `nl_coding_agent/core/platform_support.py` (message near `mcp_servers.json`) | setup requires the user to configure local stdio MCP servers manually |

**Conclusion:** MCP is local-only, stdio-only, discovery is read-only and invocation is human-gated + network-gated + audited. There is **no bundled GitHub, Hugging Face or web-search MCP server**, and remote MCP transports are unsupported.

### 3.3 Permission scopes - defined and enforced elsewhere, unused for research

| Evidence | Finding |
|---|---|
| `nl_coding_agent/core/permissions.py:1-24` | single source of truth for capability permissions (SPEC-25/NL-BP-072) and cloud/network escalation; fail-closed by design |
| `nl_coding_agent/core/permissions.py:53-70` | scopes `read/write/execute/delete/network/cloud`; defaults grant read/write/execute, **deny DELETE/NETWORK/CLOUD** |
| `nl_coding_agent/core/permissions.py:366-399` | `assert_model_permitted()`: cloud model requires CLOUD grant, remote endpoint requires NETWORK grant |
| `nl_coding_agent/core/permissions.py:402-423` | human-readable denial; no bypass flag or environment override |
| `nl_coding_agent/app/mcp.py:230-233` | NETWORK grant enforced for network-declared MCP servers |
| `nl_coding_agent/app/services.py:444-510` | terminal policy: network commands/git-network require NETWORK grant; shell/destructive commands denied |
| `nl_coding_agent/core/supervisor.py:726-727` | supervisor exposes policy snapshot for network/cloud |
| grep result (section 8) | no web-research module imports/consumes these scopes - the gate exists but no research tool uses it yet; there are no domain allow/deny, redirect/SSRF, rate or download-size controls |

**Conclusion:** permissions are real and fail-closed for model/MCP/terminal paths, but **web-research permission integration, domain policy, SSRF/private-IP enforcement and retrieval rate/size caps do not exist**.

### 3.4 Attachments pipeline - local files and clipboard only

| Evidence | Finding |
|---|---|
| `nl_coding_agent/app/attachments.py:1-28` | F1 attachment pipeline; durable store in `data/attachments`, provenance in app SQLite |
| `nl_coding_agent/app/attachments.py:415-430` | `prepare_path()` requires an existing **local file** (`Path(path).expanduser()`, `item.is_file()`); no URL handling |
| `nl_coding_agent/app/attachments.py:432-450` | folder expansion of **local** paths with a max-file batch limit |
| `nl_coding_agent/app/attachments.py:77-87` | extraction availability: text on, PDF/XLSX/DOCX/PPTX/image-metadata behind optional libraries, audio/video false |
| `nl_coding_agent/app/attachments.py:233-267` | extracts text/PDF/XLSX/Office; images metadata-only; audio/video "deferred"; unsupported types rejected |
| `nl_coding_agent/app/attachments.py:293-311` | SQLite provenance: project/mission, name/kind/mime/size, sha256, source, stored path, extraction status/text chars |
| `nl_coding_agent/app/services.py:291-325` | service facade for paths/text/clipboard image/list/attach/delete |
| `nl_coding_agent/gui/widgets/chat_panel.py:93-130` | Studio chat supports drop files/folders, Ctrl+V text/files/images, previews, dictation - all local |
| `nl_coding_agent/gui/widgets/chat_panel.py:210-236` | local path/text/clipboard-image preparation; no URL or remote fetch |

**Conclusion:** attachments are a local-file clipboard/ingestion pipeline with provenance. It can be the **intake surface for pasted files** and a basis for a research workspace, but it cannot fetch URLs, pages, repositories or model cards.

### 3.5 Explicitly absent capabilities

The following were searched in the product tree; results are "none" unless stated:

| Capability | Evidence / result |
|---|---|
| Web search / search-provider router | none (no provider clients, keys, ranking or query routing) |
| Web page / HTML / PDF URL reader | none (PDF extraction exists only for local attachment bytes; no HTTP->text path) |
| JavaScript rendering / browser automation | none; `pyproject.toml:10-14` deps are only PySide6, psutil, crewai==1.15.32, PyYAML; no playwright/selenium/bs4/requests/httpx/pypdf in product code |
| GitHub API/GraphQL client | none (only the string ".github" as a DevOps scanner indicator, `nl_coding_agent/projects/scanner.py`) |
| Hugging Face Hub client / model-card reader | none |
| Ecosystem/package documentation discovery | none |
| Research knowledge store / embeddings-for-research | none (project context/search exists at NL-BP-043, not research evidence) |
| Research GUI/workspace | none (GUI widgets list: agents, autonomy, chat, command palette, editor, file viewer, git, inspector, log, models, problems, projects, settings, sidebar, task board, terminal) |
| Bundled web/GitHub/HF MCP servers | none (no config/data `mcp_servers.json`; local stdio only) |
| Domain allow/deny, SSRF/private-IP, retrieval rate/download caps | none |
| Research acceptance on real network | none; NL-BP-203 is planned only |

## 4. What the directive asked vs what exists

| Directive capability | Exists today? | Where |
|---|---|---|
| Multi-provider web search router | **No** | planned only: NL-BP-169 |
| Web page/document reader + JS browser | **No** | planned only: NL-BP-170 |
| GitHub repository investigator | **No** (generic MCP plumbing only) | planned: NL-BP-171; MCP infra: `app/mcp.py` |
| Hugging Face model investigator | **No** | planned: NL-BP-172 |
| Ecosystem/package docs discovery | **No** | planned: NL-BP-173 |
| Local-first research knowledge store | **No** | planned: NL-BP-174 |
| Injection-resistant untrusted-source handling | **No** | planned: NL-BP-175 (partial policy concept only) |
| Research-aware planning | **No** | planned: NL-BP-176 |
| Real-network research acceptance | **No** | planned: NL-BP-203 |
| Search provider registry/capability matrix/no-key modes | **No** | **new NL-BP-205** |
| Retrieval safety (domain/SSRF/rate/cache/provenance) | **No** | **new NL-BP-206** |
| Connectors via tool registry/MCP with typed read-only permissions | **Partial infrastructure** | MCP/registry: NL-BP-042/073; research connectors **new NL-BP-207** |
| HF acquisition workflow (license/compat/download/cache) | **No** | **new NL-BP-208** |
| Version-aware official docs research | **No** | **new NL-BP-209** |
| Studio research workspace | **No** | **new NL-BP-210** |
| Research acceptance extension matrix | **No** | **new NL-BP-211** |

## 5. Dedupe mapping (user sub-capability -> existing ID / new ID)

| User sub-capability | Existing requirement(s) | New requirement | Decision |
|---|---|---|---|
| Multi-provider web search router | NL-BP-169 | NL-BP-205 | 169 owns the router; 205 adds the provider capability matrix/no-key modes/explicit routing policy |
| Provider capability matrix, availability/no-key/public modes | - | NL-BP-205 | genuinely new |
| Explicit selection + intelligent routing | NL-BP-169 (query reformulation/ranking) | NL-BP-205 (routing policy + selection UX) | split at policy boundary |
| Cost/privacy/rate policy; no silent paid service | NL-BP-168/072 (permissions) | NL-BP-205 | 205 owns provider cost/privacy/rate policy |
| Web page/document reader (HTML->text/code/tables/PDF/metadata) | NL-BP-170 | - | covered |
| JavaScript browser automation | NL-BP-170 | - | covered |
| Domain allow/deny, redirect/SSRF/private-IP, rate/download caps, caching/provenance | NL-BP-175 (untrusted content only) | NL-BP-206 | safety policy is genuinely new |
| GitHub repository investigator | NL-BP-171 | - | covered |
| Hugging Face model investigator (metadata/cards/license) | NL-BP-172 | - | covered |
| HF acquisition/compatibility/license/download/cache | NL-BP-008/124/183 (adjacent) | NL-BP-208 | acquisition workflow is genuinely new |
| Ecosystem/package docs discovery | NL-BP-173 | - | covered |
| Version-aware official docs/changelogs/migration guides | NL-BP-173 (ecosystem discovery) | NL-BP-209 | version-awareness/conflict/uncertainty is new |
| Local-first research knowledge store/citations/embeddings | NL-BP-174 | - | covered |
| Prompt-injection/untrusted-source resistance | NL-BP-175 | NL-BP-206 (enforcement policy) | 175 owns model/agent trust boundary; 206 owns retrieval enforcement |
| Research-aware planning/update checks | NL-BP-176 | - | covered |
| Research connectors through tool registry/MCP, typed read-only permissions | NL-BP-042/073 (MCP/registry), NL-BP-171/172 | NL-BP-207 | connector registration/permission separation is new |
| Studio research workspace/search history/previews/saved findings | NL-BP-043 (project search only), NL-BP-026..030 (local attachment intake) | NL-BP-210 | research GUI is genuinely new |
| Research acceptance fixture-vs-real-network matrix | NL-BP-203 | NL-BP-211 | 203 owns the scenario; 211 owns the full acceptance matrix |
| Paired attachments/URL intake for research | NL-BP-026..030 (local files) | NL-BP-210 (pasted URLs/repo/model links intake) | intake extension to research references is new |

## 6. New requirements registered (status planned, program stage 7)

| ID | Priority | Area | Dependencies | Summary |
|---|---|---|---|---|
| NL-BP-205 | P0 | autonomy | 169, 168 | Search Provider Registry: capability matrix, availability/no-key/public modes, explicit selection + routing, cost/privacy/rate policy, no silent paid use |
| NL-BP-206 | P0 | autonomy | 170, 175 | Web retrieval safety policy: domain allow/deny, redirect/SSRF/private-IP, rate/download caps, caching/provenance, untrusted content |
| NL-BP-207 | P1 | autonomy | 171, 172, 073 | Research connectors registered through the existing tool registry/MCP with typed read-only permissions and provenance separated from write/install/publish |
| NL-BP-208 | P0 | core | 172, 183, 124, 008 | Hugging Face acquisition workflow: compatibility evidence into Model Registry/Competence Index/Scheduler, license/gated approval, optional verified resumable downloads to approved locations, shared cache |
| NL-BP-209 | P1 | autonomy | 170, 173, 174 | Version-aware official documentation research: SDK/API versions, changelogs, migration guides, primary-source preference, conflict/uncertainty |
| NL-BP-210 | P1 | studio | 169, 170, 171, 172, 173, 174, 175, 176 | Studio Research workspace: search/history, source/GitHub/HF previews, permission status, saved findings, intake of pasted URLs/repo/model links/attachments |
| NL-BP-211 | P1 | release | 203, 205, 206, 207, 208, 209, 210 | Research acceptance extension: fixture-vs-real-network matrix (provider failures, rate limits, offline/denied network, domain restrictions, injection, evidence reuse across projects) |

Full acceptance criteria, evidence pointers and audit references live in the machine-readable registry `docs/product-blueprint/INDEX.json` and in `docs/PRODUCT_BACKLOG.md` (v3.8 section).

## 7. Blockers, risks and human/external decisions

- **No provider credentials/API keys** are configured; the directive requires no-key/public/offline modes to work before paid providers. Paid/cloud/API use needs explicit owner authorization (existing owner gates apply).
- **Network is denied by default** (permissions NETWORK=false; `core/permissions.py:63-70`). Enabling research requires a deliberate grant; retrieval tools must consume the same gate once implemented (NL-BP-206/207).
- **SSRF/domain safety must exist before any real web fetch is enabled** (NL-BP-206); no code currently enforces domain allow/deny or private-IP blocking.
- **Hugging Face gated/licensed models** require explicit user approval; no auto-accept/download of huge checkpoints (NL-BP-208).
- **Real-network research acceptance** (NL-BP-203/211) cannot be claimed from fixtures and needs explicit network permission/credentials; remains MANUAL-PENDING.
- **MCP is stdio-only and unbundled**; a web/GitHub/HF MCP server would need to be installed/configured by the user (no bundled servers), and remote MCP transports are unsupported.
- **Stage 7 is pending**; SH-07 Tier B (`NL-BP-063`) stays blocked. This directive grants no deletion/publication/cloud authorization and does not relax staged-candidate gates.

## 8. Verification commands used (read-only; no network/model runs)

- `findstr /s /i /n ... nl_coding_agent\*.py` / repository grep for `urlopen`, `urllib.request`, `playwright`, `selenium`, `beautifulsoup`, `requests|httpx|aiohttp`, `PyPDF|pypdf|pdfminer`, `github`, `huggingface|hf_hub`, `embedding`, `research`, `readability` - only the stdlib probe uses found; no browser/HTTP-client/PDF-remote/GitHub/HF/research modules.
- `nl_coding_agent/models/ollama_registry.py:6-7,12,45-51,54-100`; `models/providers.py:7-8,20,80-84,186-240`; `tools/registry.py:22,115-175,206-220,283-348`.
- `nl_coding_agent/app/mcp.py:1-7,43-87,90-134,196-248`; `app/services.py:137-149,184-193,291-325,444-510`.
- `nl_coding_agent/core/permissions.py:1-24,53-70,366-423`; `core/supervisor.py:726-727`.
- `nl_coding_agent/app/attachments.py:1-28,77-87,90-134,233-267,293-311,415-450`; `gui/widgets/chat_panel.py:93-130,210-236`.
- Existence checks: `config/mcp_servers.json` absent, `data/mcp_servers.json` absent; `config/` contains only `models.yaml` and `voicebridge.yaml`.
- Dependency check: `pyproject.toml:10-14` (PySide6, psutil, crewai==1.15.32, PyYAML only).
- Backlog cross-check: `docs/product-blueprint/INDEX.json` (156 requirements at audit time incl. NL-BP-169..176/203), `docs/PRODUCT_BACKLOG.md`, program stage 7.

## 9. Change record

This audit is a **new documentation file** and the queue-only backlog update that it justifies. The addendum bundle under `docs/product-blueprint/addenda/` was preserved unchanged (not edited). No application code, tests, configuration, models, missions or network state were changed, and no commit was created by this task.

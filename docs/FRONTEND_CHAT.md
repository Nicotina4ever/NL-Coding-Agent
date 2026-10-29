# NL Coder — completed VS Code chat surface (`frontend/` 0.3.0)

This is the operator guide for the chat capabilities completed on 2026-10-29. The VS Code extension is a
thin client over the existing MCP engine; models, permissions, attachments, Research, chat history and
missions remain owned by `nl_coding_agent/` and its SQLite/JSON persistence. See
[FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md) for the protocol and [FRONTEND_MISSIONS.md](FRONTEND_MISSIONS.md)
for mission control.

## Real controls (no decorative buttons)

| Control | What actually feeds it | Verified behaviour |
|---|---|---|
| Provider / model picker + **Automatic** | `engine_settings.models` (configured roles + live Ollama catalog). Explicit selection is sent as `model_spec`; Automatic omits it and the engine resolves `roles.chat` → `roles.developer`. | Real turn with `ollama/granite4.2:3b` returned `route.model="granite4.2:3b"`, `automatic=false`; Automatic returned `route.automatic=true` with `qwen2.5-coder:7b-instruct-q4_K_M`. |
| Attach **File** / drag & drop | Extension filters to file URIs inside the opened workspace, then `attachment_ingest(paths)`. The engine re-validates containment, rejects symlinks/directories/outside paths, and copies bytes into its existing attachment store. | `notes.txt` preview contained the token; the real model read the token (`NL-EDITOR-TOKEN-52`); outside-project path rejected. |
| **Current file** / **Selection** | `vscode.window.activeTextEditor` document text or selection; `attachment_ingest(text, name)`. | Selection line 1 of `notes.txt` became `notes.txt _selection 1-1_`, preview contained the token. |
| URL detection + fetch | URLs in messages become links; clicking one asks for explicit confirmation, then `research_fetch_url(url)` uses the existing Research `StdlibHttpTransport`/`Fetcher` policy. | `https://example.com/` returned `allowed`, title `Example Domain`, source #1; the fetched text was attached and the model echoed `Example Domain`. |
| Research card → **Use as chat context** | `attachment_ingest(text, name=<url>)`; the next `nlc_converse` receives the attachment id. | Model answered from the attached fetched page; `research_sources`/`research_citations` persisted in the engine DB. |
| Conversation | `chat_history(limit, before_index)` reads the existing per-project `data/chat/project-<id>.json`; the webview no longer keeps a parallel transcript archive. | 6 persisted messages returned with roles, attachment metadata and assistant `model`; reload after turns uses the canonical file. |
| Mission start/status/events/cancel/diff/verification | Existing `start_mission`, `mission_status`, `mission_events`, `cancel_mission`, `candidate_diff`, `mission_detail`; no second orchestrator. | Mission #1 completed with reviewer `APPROVE`, candidate+oracle `PASS`, diff `1 file(s), +3/-0`, live `src/calc.py` change; stop→resume also passed. |

## Backend additions (minimum needed)

All additions are in the existing engine; no new persistence store was introduced.

- `nlc_converse(..., attachment_ids=[...])` validates project ownership and passes ids to
  `AppServices.chat_conversation`; it returns the `route` actually used
  (`provider_id`, `model`, `requested_spec`, `automatic`). Assistant turns persist `model`,
  `provider_id` and `automatic` in the existing chat JSON.
- `attachment_ingest(paths?, text?, name?)`: project-bound `READ`, strict path containment, rejects
  symlinks/directories, reuses `prepare_attachment_paths()` / `prepare_attachment_text()`, returns
  bounded previews and ids but never `stored_path`.
- `chat_history(limit=200, before_index?)`: existing `list_chat_messages()` plus attachment metadata,
  assistant route metadata and bounded content. It does not create another archive.
- `research_fetch_url(url)`: `READ` + explicit `NETWORK`; calls the existing
  `AppServices.research_fetch_read()` with the existing Research `Fetcher`/policy. Raw HTML is never
  returned; text is bounded to 20,000 chars and marked `untrusted: true`.
- `mcp serve --research-profile manual|trusted-auto-review` and the matching
  `nlCodingAgent.researchProfile` setting. The MCP server wires the existing `StdlibHttpTransport`
  under a `NETWORK` gate and sets `SSL_CERT_FILE` to the bundled certifi bundle when available.

The MCP surface is now **13 tools**: the previous 10 plus `attachment_ingest`, `chat_history`,
`research_fetch_url`.

## Permissions and trust boundaries

- The extension **never grants or edits permissions**, config, the engine DB or missions.
- URL fetch requires all of:
  1. `NETWORK` granted for the project (otherwise the tool returns a clear permission error);
  2. a `web-fetch` capability grant (owned by the backend/human; project/external-resource decisions
     work, a host-domain grant does not match this service scope);
  3. a research profile that can approve the action. `manual` returns `needs_approval`; the owner can
     select `trusted-auto-review` in the Engine tab/setting. Every fetch is still an explicit click.
- `research_fetch_read` enforces HTTPS, blocks literal loopback/private/link-local/multicast/reserved
  IPs and `localhost*`, limits redirects to 5 with per-hop policy, 2 MB body, 10 s policy timeout,
  500k extracted chars and a 4k stored excerpt. DNS/peer-IP verification remains a documented residual
  limit. Fetched pages are untrusted data; HTML/JS is neither rendered nor executed.
- Attachments are prompt context only for chat; they are not sent to mission agents. Files are copied
  into the engine's existing store; images are metadata-only; unsupported Office/PDF extraction is
  reported honestly rather than invented.

## UI

The Chat tab now has a modern composer with a provider/model bar, Automatic toggle, visible
editor/selection context, attachment chips with bounded previews and removal, drag & drop, research
cards, message links and model badges, engine-persisted history, and an execution/Research status area.
The layout uses VS Code theme variables and the existing `#7531FE` accent as a restrained rule/border.
No model text is inserted with `innerHTML`.

## Acceptance evidence (2026-10-29, 0.3.0)

| Gate | Command | Result |
|---|---|---|
| TypeScript | `npm run compile` | exit 0 |
| Webview | `node test/webview.cjs` | `WEBVIEW-TESTS-PASS` |
| Node MCP + Ollama + attachment + history | `node test/integration.cjs` | `INTEGRATION-ACCEPTANCE-PASS`: 13 tools, explicit route + attachment token, history metadata, outside path rejected, research denied without `NETWORK`, project isolation |
| Real Insiders chat flows | `node test/runChatFeatureTests.cjs` | `CHAT-FEATURE-ACCEPTANCE-PASS`: model → conversation, file + editor selection attachments, authorized URL → context, 6-message history, automatic route |
| Installed VSIX chat | `node test/runInstalledChatFeatureTests.cjs .workspace/dist/NL-Coding-Agent-0.3.0.vsix` | `VSIX-CHAT-FEATURE-PASS` from the installed payload |
| Mission / stop-resume | `node test/runMissionTests.cjs`, `node test/runResumeTests.cjs` | `MISSION-ACCEPTANCE-PASS`, `STOP-RESUME-ACCEPTANCE-PASS` |
| Installed VSIX mission | `node test/runInstalledVsixTests.cjs .workspace/dist/NL-Coding-Agent-0.3.0.vsix` | `VSIX-INSTALLED-MISSION-PASS` |
| Python focused | 11 relevant test modules | 140 passed |

VSIX: `.workspace\dist\NL-Coding-Agent-0.3.0.vsix`, 4,699,386 bytes, SHA-256
`d5d0ad89413ad461755478fead7002b6a4cc568702973d3d9a6c1b2e850f8c7c`. The installed extension appears as
**NL Coder** (`displayName`), with the real product logo at `assets/icon.png` and the unchanged extension
id `nlcodingagent.nl-coding-agent`. Logs and machine-readable evidence:
`docs/evidence/frontend/chat-features-evidence.json` plus `CHAT_FEATURES_ACCEPTANCE_DEV.log`,
`VSIX_CHAT_FEATURE_ACCEPTANCE.log`, `MISSION_ACCEPTANCE_DEV_V030.log`,
`VSIX_INSTALLED_MISSION_ACCEPTANCE_V030.log`, `STOP_RESUME_ACCEPTANCE_V030.log`,
`EXTENSION_ACCEPTANCE_V030.log`, `INTEGRATION_ACCEPTANCE_V030.log`, `WEBVIEW_TESTS.log`.

## Known limits

- No streaming; one request/response per chat turn.
- URL fetch is deliberately off without owner grants and an approving research profile. The UI reports
  the exact backend reason; it never retries through another transport or writes permissions.
- Research error details are collapsed by the existing service (`transport_error` can mean TLS, DNS or
  connection); the UI does not invent a cause.
- Attachments are text/context, not vision; images are metadata-only.
- Single-folder workspaces; changing folders restarts/rebinds the engine.

*Last updated: 2026-10-29, after chat feature and installed-VSIX acceptance.*

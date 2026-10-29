# Frontend Architecture — VS Code / NL Chat

**Status:** accepted on 2026-10-29 against a real **VS Code Insiders 1.145.0-insider** extension host
and the existing Python engine. This document replaces the earlier draft that described a
`vscode-languageclient`/LSP connection; that draft was wrong and its code was removed.

The frontend is `frontend/`: a VS Code extension that speaks the Model Context Protocol to the
authoritative Python engine. It owns **no** models, missions, permissions, conversations or
persistence. Everything remains in `nl_coding_agent/` and `data/`, exactly as the PySide6 Studio
sees it. The Studio is untouched and remains the compatibility UI.

## Non-negotiables kept

- One engine installation (`nl_agent.py` + `python\python.exe`), never a duplicate runtime.
- No second settings store, mission engine or model framework.
- The engine is resolved from the **extension installation**, not from the user's opened project.
- One MCP process per workspace folder, bound to exactly one registered project.
- Model-generated text is rendered as text, never as HTML.
- Shutdown releases the MCP session and the Python child process.

## Components

| File | Responsibility |
|---|---|
| `frontend/src/backend.ts` | `EngineConnection`: engine-location resolution, official MCP SDK client, stdio transport, idempotent connect, tool calls, project context, chat turn, close/restart. No `vscode` import, so the same code is reusable by the future Code - OSS build and by plain-Node tests. |
| `frontend/src/chatProvider.ts` | `WebviewViewProvider` for `nlCodingAgent.chat`; message protocol, busy state, errors, selected-text attachment, project/engine announcement. |
| `frontend/src/webview.ts` | Pure HTML builder with a strict CSP and HTML escaping. |
| `frontend/src/extension.ts` | Activation, commands, configuration, workspace-folder rebinding, webview registration, deactivation. |
| `frontend/media/main.js` | Plain browser JavaScript for the chat transcript and composer. |
| `frontend/media/style.css` | Theme-aware layout using `--vscode-*` variables; brand accent `#7531FE` used only as a user-message rule. |

## Protocol contract (verified against the live server)

Python side: `FastMCP` from the installed `mcp==1.30.0`, started with
`python\python.exe nl_agent.py mcp serve --project <folder>` (read-only by default; `--allow-execution`
is owner-gated). Negotiated protocol in testing: `2025-11-25`. Stdout carries only JSON-RPC; engine
logging is redirected to stderr.

The extension uses the official **`@modelcontextprotocol/sdk@1.32.2`** client (`Client` +
`StdioClientTransport`), imported by subpath:

```ts
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
```

The SDK is dual-published (CJS + ESM), so the extension's CommonJS build uses it directly without a
bundler. The bare root specifier is **not** used (its `exports` root points at files that do not exist
in 1.32.2); subpaths are required.

Discovered tools and contracts:

| Tool | Arguments | Notes |
|---|---|---|
| `project_context` | none | Returns the bound project (`id`, `root`, `name`, …) and `execution_enabled`. |
| `nlc_converse` | `project_id` (required, must equal the bound project), `text`, `attachments` (array of `{name, extracted_text}`), `history` (accepted, ignored), optional `model_spec` | Runs the existing `AppServices.chat_conversation` and returns `{ok, reply, messages, ...}`. |
| `mission_list` | none | Read-only. |
| `mission_status` | `mission_id` | Read-only; rejects foreign missions. |
| `mission_events` | `mission_id`, optional `limit` | Read-only. |
| `candidate_diff` | `mission_id` | Read-only. |
| `start_mission` | `goal`, `developer_model`, `reviewer_model`, optional `approved`, `resume_mission_id` | Requires `--allow-execution` + explicit approval + permissions. |
| `cancel_mission` | `mission_id`, optional `approved` | Requires owner-enabled execution + approval. |

Tool results arrive as a text content block containing JSON (no `structuredContent`); the client parses
it, treats MCP `isError` and application `ok:false` as failures, and uses a ≥180 s request timeout
because a cold local model can take ~15 s and there is no streaming.

## Engine location (`resolveEngineLocation`)

Resolution order:

1. `nlCodingAgent.engineRoot` setting (authoritative: an invalid path fails closed; no silent fallback).
2. `NL_ENGINE_ROOT` environment variable (same authority).
3. This extension's own folder and its parents (repository layout, or a future bundled Code - OSS
   layout). This is why the engine is found at `K:\AI\NL Coding Agent` from
   `K:\AI\NL Coding Agent\frontend`.

The opened user project is **never** used to locate the engine. `nlCodingAgent.pythonPath`
(or `NL_PYTHON_PATH`) can override `python.exe`; `NL_DATA_DIR`, `NL_WORKSPACE_DIR` and
`NL_MODELS_CONFIG` are forwarded to the child when present (the SDK transport only inherits a small
whitelist, so these are passed explicitly). The NL Code portable launcher uses `NL_ENGINE_ROOT` to
point the bundled extension at the existing engine installation, so no per-machine setting is needed
(see [NL_CODE_STANDALONE.md](NL_CODE_STANDALONE.md)).

## Project identity and isolation

- The workspace folder is passed as `--project`; the server registers/binds that one project.
- The client learns the id from `project_context` and sends **only** that id to `nlc_converse`.
  There is no hard-coded project id.
- The server now validates `project_id` against the bound project and rejects anything else
  (previously `0` and other ids silently proceeded and even wrote separate chat histories).
- Changing workspace folders restarts the session and rebinds; the client also compares the
  announced root with the open folder and refuses to chat on a mismatch.

## Webview security

- `default-src 'none'`, `script-src`/`style-src` limited to the webview CSP source, no
  `'unsafe-inline'`, no inline script, no inline event handlers.
- The script is an external extension media file.
- Model and project text is inserted with `textContent`; a hostile `<img onerror>`/`<script>` sample
  is rendered verbatim as text and executes nothing (covered by `test/webview.cjs`).
- Selected editor text is capped at 8,000 chars and framed as `UNTRUSTED attachment` context by the
  server; history supplied by the client is ignored because the backend persists the real history.

## Lifecycle

`connect()` is idempotent and concurrency-safe. The session is created lazily on the first webview
`ready`/command. `close()` calls the SDK transport's `close()`, which ends stdin, waits for a clean
exit, then escalates to SIGTERM/SIGKILL; verified to release the Python child. Deactivation closes the
session; a workspace-folder change restarts it. Engine stderr is streamed to the "NL Coding Agent"
output channel.

## Build and run

```powershell
cd frontend
npm install
npm run compile
code-insiders --extensionDevelopmentPath="K:\AI\NL Coding Agent\frontend" "K:\path\to\project"
```

Then run **NL Coding Agent: Start Chat** (or **NL Coding Agent: Show Backend Status**). The default
layout needs no settings; `nlCodingAgent.engineRoot` exists for non-standard installs. `npm run
test:integration`, `npm run test:webview` and `npm run test:extension` are the acceptance harnesses.

## Acceptance evidence (2026-10-29)

| Gate | Command | Result |
|---|---|---|
| TypeScript build | `npm run compile` | exit 0, no diagnostics |
| Webview safety/behaviour | `node test/webview.cjs` | `WEBVIEW-TESTS-PASS`, exit 0 |
| Real MCP + Ollama | `node test/integration.cjs` | `INTEGRATION-ACCEPTANCE-PASS`, exit 0: initialize `NL Coding Engine 1.30.0`, 8 tools, project #1/#2 isolation, reply `NLCHAT-OK`, cross-project refusal, child processes 3144/14860 released |
| Real VS Code host | `node test/runExtensionTests.cjs` | `EXTENSION-HOST-TEST-PASS`, exit 0: activated `nlcodingagent.nl-coding-agent`, workspace mapped to project #1, NL Chat webview created and received project+tools, reply `EXT-OK` delivered, cross-project id refused, child released |
| GUI (visual) | driven Insiders window | see `docs/evidence/frontend/NL_CHAT_GUI_ACCEPTANCE.png`: connected panel (`project #1 · 8 tools`), user message, assistant reply `NLCHAT-GUI-OK` |

Python coverage added for the binding rule: `pytest tests/test_mcp_engine_converse.py
tests/test_mcp_sdk.py::test_real_engine_stdio_readonly_project_binding` → 5 passed.

## Known limits / next increments

- No streaming: a turn is one request/response; the UI shows a busy state.
- Chat only: missions, candidate diffs and status are exposed by the server but not yet surfaced in
  the webview (the status command lists tools and project identity).
- Single-folder workspaces; no multi-root project switching yet.
- No packaged VSIX yet (a bundling pass with esbuild and `vsce package` is the next distribution step;
  the SDK is CJS-compatible, so packaging is not blocked).
- The Studio (PySide6) and all existing user data remain the compatibility path.
- `vscode/` in the repository root is a local Code - OSS reference checkout; it is not part of this
  extension and is not shipped.

*Last updated: 2026-10-29, after real VS Code Insiders acceptance.*

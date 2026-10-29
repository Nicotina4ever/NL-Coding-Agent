# Frontend Architecture — VS Code / NL Chat

**Status:** extended on 2026-10-29 (extension `0.2.0`) from chat-only to **chat + model choice + real
mission control + diff/verification review**, packaged as an installable VSIX and accepted against a
real **VS Code Insiders 1.145.0-insider** extension host and the existing Python engine. This document
replaces the earlier draft that described a `vscode-languageclient`/LSP connection; that draft was
wrong and its code was removed.

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
| `frontend/src/backend.ts` | `EngineConnection`: engine-location resolution, official MCP SDK client, stdio transport, idempotent connect, tool calls, project context, chat turn, **engine settings/model catalog, mission list/status/detail/diff, mission start/cancel**, execution flag, close/restart. No `vscode` import, so the same code is reusable by the future Code - OSS build and by plain-Node tests. |
| `frontend/src/chatProvider.ts` | Webview controller for `nlCodingAgent.chat`: dashboard state, chat, model choice, mission start/resume/stop, progress polling, diff/verification rendering, approvals and errors. |
| `frontend/src/webview.ts` | Pure HTML builder with a strict CSP and HTML escaping (Chat / Missions / Engine tabs). |
| `frontend/src/extension.ts` | Activation, commands, configuration (`allowExecution`), workspace-folder rebinding, webview registration, deactivation, public test/automation API. |
| `frontend/media/main.js` | Plain browser JavaScript: transcript, mission composer, mission list/detail, verification/diff views, engine settings; all engine text via `textContent`. |
| `frontend/media/style.css` | Theme-aware layout using `--vscode-*` variables; brand accent `#7531FE` as a restrained rule/progress accent. |

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
| `engine_settings` | optional `include_models` (default `false`), `timeout_s` (0.5–5 s) | Read-only projection of the existing model config, configured providers/roles, chat default, agent roles/custom agents, effective permissions, runtime paths and mission route defaults. `include_models` runs the same bounded GET-only Model Hub probe as the Studio; it never loads a model. |
| `nlc_converse` | `project_id` (required, must equal the bound project), `text`, `attachments` (array of `{name, extracted_text}`), `history` (accepted, ignored), optional `model_spec` | Runs the existing `AppServices.chat_conversation` and returns `{ok, reply, messages, ...}`. |
| `mission_list` | none | Read-only. |
| `mission_status` | `mission_id` | Read-only; rejects foreign missions. |
| `mission_detail` | `mission_id` | Read-only persisted view: tasks, task attempts, handoffs, verification runs, progress, timestamps, parsed `changed_paths`. |
| `mission_events` | `mission_id`, optional `limit` | Read-only handoffs. |
| `candidate_diff` | `mission_id` | Read-only staged or retained historical unified diff; `ok:false` is a real answer. |
| `start_mission` | `goal`, `developer_model`, `reviewer_model`, optional `approved`, `resume_mission_id` | Requires `--allow-execution` + explicit approval + permissions. Creates a new mission **or** resumes the same persisted mission with the identical goal. |
| `cancel_mission` | `mission_id`, optional `approved` | Requires owner-enabled execution + approval; durable cooperative stop at the next safe checkpoint. |

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

## Mission and settings surface (`0.2.0`)

The webview has three sections:

- **Chat:** existing chat turn with a model selector. Model options are the configured role models plus
  live discovered local models (embedding-only models are filtered out). "Engine default" omits
  `model_spec`, so the engine's own `roles.chat`/`roles.developer` fallback remains authoritative.
- **Missions:** the project's persisted missions with status/verdict/diff stat, Open/Stop/Resume
  actions, and a detail view containing the objective, progress, tasks/agents, handoffs, candidate and
  oracle verification runs, reviewer notes, attempts and the candidate/retained diff. Mission mode in
  the chat composer starts a mission through `start_mission`; `/mission <objective>` is a shortcut.
- **Engine:** project identity, execution mode, read-only permission policy, agent roles,
  providers/models, configured mission route defaults and a "Probe models" action. Configuration is
  **read-only here**; the extension never writes `config/models.yaml`, permissions or the engine DB.

### Mission lifecycle and approvals

- The engine is started **read-only** by default. `nlCodingAgent.allowExecution` adds
  `--allow-execution`; changing it restarts the engine session. Enabling is an explicit modal warning.
- Starting a mission always opens a modal confirmation showing objective, developer/reviewer route and
  that the existing Supervisor/staging/reviewer gates will modify the project.
- Stopping is also confirmed; it requests the engine's durable safe-checkpoint stop. It never kills a
  model call or a promotion write.
- Resume reuses the same mission id/goal through `start_mission(resume_mission_id=…)`. The UI waits
  through the stale `interrupted` row until the resumed run actually starts before treating a status as
  terminal.
- `READ`/`WRITE`/`EXECUTE` permissions are enforced by the engine; a read-only server refuses
  `start_mission` before creating anything (integration test asserts the mission table stays empty).
- The opened workspace is bound to the engine process; a project-root mismatch is refused and asks for
  "Reconnect Backend". Multi-root remains unsupported.

### Audit trail honesty

Missions expose the engine's **persisted** audit trail: task rows (`agent_role`, status, attempts),
agent handoffs (with payload/actions/summary), task attempts (model output/error), verification
commands/results and the reviewer verdict. The engine does **not** persist per-tool-call telemetry
(`read_file`/`write_file`/`patch_file` invocations are discarded by the CrewAI seam), so the dashboard
does not invent tool calls; only `actions` recorded by the existing text-block fallback appear in a
handoff payload. See [FRONTEND_MISSIONS.md](FRONTEND_MISSIONS.md).



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

## Build, package and run

```powershell
cd frontend
npm install
npm run compile
npm run package:vsix        # -> ..\.workspace\dist\NL-Coding-Agent-0.2.0.vsix

# local install in an isolated Insiders profile (does not touch the default profile)
& "$env:LOCALAPPDATA\Programs\Microsoft VS Code Insiders\bin\code-insiders.cmd" `
  --install-extension "..\.workspace\dist\NL-Coding-Agent-0.2.0.vsix" --force `
  --user-data-dir "$PWD\..\.workspace\temp\frontend-accept\vsix-profile\user-data" `
  --extensions-dir "$PWD\..\.workspace\temp\frontend-accept\vsix-profile\extensions"
```

For a normal user install, `code-insiders --install-extension <vsix>` (or the VS Code Extensions view
"Install from VSIX…") is enough; set `nlCodingAgent.engineRoot` when the engine is not resolvable from
the extension location. Mission execution is opt-in through `nlCodingAgent.allowExecution`.

Acceptance harnesses:

| Script | Purpose |
|---|---|
| `npm run test:integration` | Node-only real MCP + Ollama + project isolation + read-only refusal. |
| `npm run test:webview` | CSP, no HTML sink, dashboard state/chat/mission rendering. |
| `npm run test:extension` | Real Insiders extension host: activation, tools, settings, chat, shutdown. |
| `node test/runMissionTests.cjs` | Real isolated-project mission: complete change, diff, candidate/oracle tests, reviewer verdict, promotion. |
| `node test/runResumeTests.cjs` | Real stop→interrupted→resume→completed lifecycle. |
| `node test/runInstalledVsixTests.cjs` | Installs the VSIX in an isolated profile and runs the mission acceptance from the installed payload. |

## Acceptance evidence (2026-10-29, `0.2.0`)

| Gate | Command | Result |
|---|---|---|
| TypeScript build | `npm run compile` | exit 0, no diagnostics |
| Webview safety/behaviour | `node test/webview.cjs` | `WEBVIEW-TESTS-PASS`, exit 0 (state, chat, mission mode/detail, CSP/no HTML sink) |
| Real MCP + Ollama | `node test/integration.cjs` | `INTEGRATION-ACCEPTANCE-PASS`, exit 0: initialize `NL Coding Engine 1.30.0`, **10 tools**, `engine_settings`, project #1/#2 isolation, read-only `start_mission` refused with no mission row, reply `NLCHAT-OK`, children released |
| Real mission (dev host) | `node test/runMissionTests.cjs` | `MISSION-ACCEPTANCE-PASS`, exit 0: mission #1 completed, verdict `APPROVE`, promotion `promoted`, candidate+oracle passed, live `src/calc.py` changed, retained diff returned, dashboard got detail+diff, child released |
| Stop + resume | `node test/runResumeTests.cjs` | `STOP-RESUME-ACCEPTANCE-PASS`, exit 0: stop accepted → `interrupted` with live tree untouched → resume → completed/APPROVE/promoted, `resume_count 1` |
| VSIX package/install | `npm run package:vsix` + Insiders CLI | `NL-Coding-Agent-0.2.0.vsix` (4.46 MB) installed and listed as `nlcodingagent.nl-coding-agent` in an isolated profile |
| Installed VSIX mission | `node test/runInstalledVsixTests.cjs` | `VSIX-INSTALLED-MISSION-PASS`, exit 0: same real mission, diff, verification and dashboard checks from the **installed** VSIX payload |
| Python binding | `pytest tests/test_mcp_sdk.py::test_real_engine_stdio_readonly_project_binding tests/test_mcp_engine_converse.py` | 5 passed (includes `engine_settings`/`mission_detail`) |

Logs and the exported mission record are under `docs/evidence/frontend/` (`MISSION_ACCEPTANCE_DEV.log`,
`STOP_RESUME_ACCEPTANCE.log`, `VSIX_INSTALLED_MISSION_ACCEPTANCE.log`, `INTEGRATION_ACCEPTANCE.log`,
`WEBVIEW_TESTS.log`, `mission-evidence.json`). The earlier chat-only GUI screenshot is
`docs/evidence/frontend/NL_CHAT_GUI_ACCEPTANCE.png`.

## Known limits / next increments

- No streaming: a chat turn is one request/response; mission progress is polled every 2 s.
- No per-tool-call telemetry exists in the engine, so the dashboard shows persisted task/handoff/
  attempt/verification evidence rather than fabricated tool calls.
- Single-folder workspaces; changing folders restarts and rebinds the engine.
- The VSIX is locally built and unsigned (normal for a personal extension); it is verified by install
  and extension-host acceptance, not by a marketplace signature.
- Mission success depends on installed local models and reviewer judgment; a rejected candidate is a
  legitimate `blocked` result with its diff/verification still visible.
- Legacy missions (`harness_version != 2`) are listed but cannot be run/resumed by the current harness.
- Mission detail strings are bounded by the MCP tool (attempt output 12k, verification 8k, handoff
  payload 2k) to keep the webview responsive.
- The NL Code standalone distribution built earlier still bundles extension 0.1.0 (chat-only); it must
  be rebuilt to include this mission UI when objective-2 packaging resumes.
- The Studio (PySide6) and all existing user data remain the compatibility path.
- `vscode/` in the repository root is a local Code - OSS reference checkout; it is not part of this
  extension and is not shipped.

*Last updated: 2026-10-29, after mission control, VSIX packaging and installed-VSIX acceptance.*

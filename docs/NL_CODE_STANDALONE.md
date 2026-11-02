# NL Code — standalone Code - OSS distribution

**Status:** objective 2 accepted on 2026-10-29. The portable distribution was built from Code - OSS
1.145.0 (commit `7801f8a5…`) and verified in a real desktop session: NL Code starts with its own
portable profile, loads the NL Chat extension, maps the opened folder to the backend project,
receives a real Ollama reply, keeps the existing engine settings and releases the Python child on
shutdown. See the acceptance record below.

## Purpose

NL Code is the standalone Windows IDE shell for NL Coding Agent. It is a **code-oss application**,
branded and packaged locally, that reuses:

- the existing VS Code extension in `frontend/` (NL Chat),
- the existing Python engine at the repository root (`nl_agent.py`, `nl_coding_agent/`, `python/`),
- the existing user data (`data/`: settings, agents, models, permissions, missions, history).

The older PySide6 Studio is legacy and is not part of normal development or acceptance. NL Code is
one of the two supported interfaces, sharing the Python engine with NL Coder for VS Code Insiders.
This is objective 2 of the product plan; objective 3
(verified autonomous development of the frontend and the distribution) is specified at the end but is
**not started** until this distribution passes its own acceptance.

## Architecture decisions

| Decision | Reason |
|---|---|
| Code - OSS source is built from a copy under `.workspace/build/nl-code-oss/src` | Keeps the external `vscode/` checkout untouched and keeps generated artifacts out of Git. |
| Branding is an overlay on `product.json` (`nameShort/nameLong = NL Code`, `applicationName = nl-code`, portable data folder `.nl-code`, own protocol/AppUserModelId/mutex) | No fork of the vendor source; the overlay is reproducible by the build script. |
| The application is staged to `.workspace/dist/NL Code` with a `data/` folder | Code - OSS portable mode: user data and extensions live next to the application, no global install. |
| The NL extension is installed in `data/extensions/nlcodingagent.nl-coding-agent-<version>` | The same built extension as the Insiders setup; production dependencies only. |
| The Python engine is **not duplicated**; the launcher sets `NL_ENGINE_ROOT` to the existing installation | Avoids a second 1.6 GB Python/CrewAI runtime and keeps one model/agent/permission/history database. |
| `NL_DATA_DIR` defaults to `<engine>\data` if present | Same SQLite data the Studio already uses; a user-provided `NL_DATA_DIR` still wins. |
| Desktop build only: `remote/`, `test/*` and `.vscode/*` dependencies are not installed | They are development/remote-server trees, not part of a local desktop package. |

## Build

Prerequisites: Windows x64, the repository's protected `python/` runtime, the local `vscode/`
checkout, Node.js **24.22.1** (the script downloads a portable copy into `.workspace/tools` if
missing), a C++ MSVC toolchain (VS 2022 Build Tools present on this machine) and network access for
npm/Electron artifacts.

```powershell
pwsh -File scripts/nlcode/build_nl_code.ps1 -ResyncSource
```

The script performs:

1. copy `vscode/` → `.workspace/build/nl-code-oss/src` (excluding `.git`);
2. apply the product branding and generate the NL Code `.ico`/window PNGs
   (`scripts/nlcode/make_brand_icon.py`, brand palette from `assets/theme.tokens.json`);
3. `npm ci --ignore-scripts` with portable Node;
4. install Electron 43.8.3 headers directly with node-gyp;
5. patch `binding.gyp` `SpectreMitigation` to `false` **in the build tree only**;
6. build the native modules against the Electron headers;
7. install `build/` and `extensions/*` dependencies with scripts disabled;
8. `npm run gulp compile`;
9. `npm run gulp vscode-win32-x64-min`;
10. stage the portable distribution, the compiled extension, `NL Code.bat` and `BUILD_INFO.json`.

### Local machine workarounds (documented, not hidden)

- **Path spaces:** upstream `build/npm/preinstall.ts` invokes node-gyp unquoted and fails on
  `K:\AI\NL Coding Agent\...`; the script skips that entry point and runs the same header install
  with correct quoting.
- **Spectre libraries:** the installed MSVC toolchains do not include the Spectre-mitigated
  libraries, so native binding files are patched in the build tree. This weakens Spectre mitigations
  for those Node/Electron addons only; the Python engine and the extension code are unaffected.
- **npm 11 allowScripts:** the root lifecycle (`npm rebuild`) is rejected by npm 11.19 for this
  repository layout; native modules are therefore built with node-gyp explicitly.
- **No postinstall:** upstream postinstall also installs `remote/`, test trees and writes **global**
  Git config. The build installs only `build/`, built-in extension and selfhost-typecheck
  dependencies.
- **Copilot packaging step:** the Copilot SDK is not bundled, so the upstream post-package ripgrep
  shim task is skipped in the build tree. It runs after the application is fully packaged and does
  not affect NL Chat or the editor.
- **Optional native modules:** `node_modules/cpu-features` and `ssh2`'s optional crypto addon fail to
  build; both have pure-JS fallbacks and are not needed by NL Chat.

### First-run behaviour

The portable profile seeds `chat.disableAIFeatures: true`, so the GitHub Copilot chat and inline
suggestions are hidden on a fresh profile; the NL Chat secondary sidebar takes that place. The
upstream agent-host fields remain in `product.json` because this 1.145 build expects them, but the
workbench does not prompt for GitHub sign-in during the NL Code acceptance run. Users can re-enable
the built-in AI features from Settings without affecting NL Chat.

### Workbench layout (Gate E)

The standalone shell keeps the complete Code - OSS workbench and only reorganizes the experience:

| Area | Content |
|---|---|
| Center editor | `NL Code — Home` dashboard on startup: live project/engine state, Chat, new mission, Mission Control, Model Hub, agents, settings, storage, and the normal development commands. The panel can be closed and reopened with `Ctrl+Alt+H`. |
| Left | Standard Explorer and all built-in developer views. |
| Right secondary sidebar | The shared NL Chat webview with **Chat**, **Missions**, **Agents** and **Settings** tabs. It replaces the upstream Copilot Chat panel. |
| Bottom / panels | Terminal, Output, Problems, Debug Console and the rest of Code - OSS are unchanged. |
| Editor watermark | The Code - OSS letterpress is replaced by the NL Code mark in dark, light and high-contrast variants. |

The extension uses the same `EngineConnection`/MCP contract in VS Code and NL Code. Standalone-only
personalization is limited to default layout/profile seeding, the Home editor panel, the product
branding, the NL Code Dark theme and the watermark. No editor, terminal, Git, debugger, search or
extension subsystem is reimplemented or removed.

### Models, providers and specialist agents

- Any number of `ollama` and `openai_compatible` providers can be configured; each provider has its
  own endpoint, label, enabled flag and API-key environment variable. Model routes are
  `provider/model`, so local and online models can be assigned to different roles, missions or
  specialist profiles.
- The **Agents** tab assigns models to architect/developer/debugger/reviewer/chat and manages
  specialist profiles (name, provider, model, specialty, instructions, tools, permissions, enabled).
  Profiles are stored by the Python engine in `data/custom_agents.json` and exposed through the
  `custom_agents`/`save_custom_agent`/`duplicate_custom_agent`/`delete_custom_agent` MCP tools.
- Custom specialist profiles are currently configuration presets; the built-in mission stages remain
  the execution path until the engine exposes specialist execution explicitly.


## Run

```powershell
.\.workspace\dist\NL Code\NL Code.bat
```

The launcher starts `NL Code.exe` with the portable `data/` profile and points the extension at the
existing engine. Override the engine with `NLCODE_ENGINE_ROOT`; existing `NL_DATA_DIR` values are
respected.

## Local capacity HUD and long-running work

The Home dashboard reads a read-only `resource_status` snapshot from the engine: RAM, CPU,
NVIDIA VRAM/utilization when `nvidia-smi` is available, currently loaded Ollama models and
bounded capacity warnings. It never loads a model or changes scheduling.

Local inference is expected to be slow. The chat turn timeout defaults to 1800 seconds
(30 minutes, configurable up to 7200 seconds) and the verification timeout defaults to
3600 seconds (`NL_VERIFY_TIMEOUT_S`). A long model run is not treated as a failure merely
because it takes minutes. The HUD exists so the operator can see whether the machine is
actually saturated instead of guessing.

Context length is optional and task/profile-scoped. **Application default** omits `num_ctx`, so
the Ollama application setting remains authoritative; choosing 4k–256k sends an explicit override
for that model/role only. The default is never silently changed.

## VS Code extension 0.4.0

The current extension build is `frontend` version `0.7.1`, packaged as
`.workspace/dist/NL-Coding-Agent-0.7.1.vsix`. Install it through VS Code's
“Install from VSIX…” so the extensions metadata is updated.

If a portable profile was edited by copying an extension directory manually and
the Chat panel stays empty, VS Code is still using stale `data/extensions/extensions.json`
or `data/extensions/.obsolete` entries. Close NL Code, remove those two metadata files
(and the extension cache directories), then restart; the new extension is rescanned.

## Unified operational Chat and background jobs

When mission execution is enabled, Chat exposes **Auto-code**. The model can call
`start_coding` for an explicit coding goal; the engine creates the mission, defers dispatch until the
Chat turn releases the shared inference slot, then runs the normal Supervisor/staging/verification/
reviewer path. Chat itself never writes the live tree directly. The toggle is persisted per
workspace, is disabled automatically in read-only sessions, and every mission still requires the
existing permissions and gates.

Chat can also start, list, read and stop project-scoped background jobs through `job_start`,
`job_list`, `job_output` and `job_stop`. Jobs are allowlisted argv vectors (no shell interpolation),
run with the project root as cwd, keep bounded logs under `data/jobs/<project_id>/`, and reject
inline Python/Node code and scripts outside the project. They are the local equivalent of background
terminals, with the engine as owner.

Conversation history is project-scoped and supports multiple sessions per project. Orphaned and
archived sessions can be cleaned from Storage Manager; active projects and conversations are never
touched.



Command:

```powershell
pwsh -File scripts/nlcode/accept_nl_code.ps1 -SeedFromLiveData
```

Result: `== NLCODE-STANDALONE-ACCEPTANCE-PASS ==`, exit 0, on the clean build staged on
2026-10-29. Evidence: `docs/evidence/nlcode/NL_CODE_GUI_ACCEPTANCE.png` and
`docs/evidence/nlcode/acceptance-result.json`.

| Gate | Evidence |
|---|---|
| Packaged `NL Code.exe` starts with its own portable profile | PASS — window from `.workspace/dist/NL Code`, `data/user-data` + `data/extensions` used |
| NL Coding Agent extension is discovered and activated | PASS — NL Chat view rendered `Connected · project #75 · 8 tools` |
| Real project and 8 tools reported | PASS — `project_context`/`mission_*`/`candidate_diff`/`start_mission`/`cancel_mission` + `nlc_converse` listed |
| NL Chat sends a message and receives a real Ollama reply | PASS — user message and model reply `NLCODE-GUI-OK` visible in the webview |
| Workspace maps to the correct backend project | PASS — acceptance folder mapped to project #75 |
| Existing settings/models/agents/permissions/history remain the engine's | PASS — seeded live-data copy; `app_settings` hash unchanged after the session; same `config/models.yaml` |
| Closing the window releases the Python child process | PASS — child pid 46536 gone after close |
| Build is reproducible by the script (`BUILD_INFO.json` records source commit) | PARTIAL — dependency install, native build, compile, package and stage each ran with exit 0, and `BUILD_INFO.json` records source/tool/extension identity; one single full `-ResyncSource` rerun after the final fixes was not repeated (only packaging+staging). |

Note: the first launch on a fresh portable profile shows the upstream Copilot onboarding dialog; the
acceptance harness dismisses it with Escape. See “First-run behaviour” above.

## Objective 3 — verified autonomous development (not started)

Once objective 2 is accepted, the engine may modify its own frontend and this distribution through
the **existing** mission engine, never through a parallel system:

1. Mission objectives target `frontend/` and `scripts/nlcode/` with explicit authorized paths.
2. Development runs in a separate build tree / isolated project, not the live distribution.
3. Candidate, oracle and reviewer gates run real TypeScript, extension-host and packaging tests.
4. Independent reviewer approval plus the existing permission/promotion gates are required before a
   change can reach the standalone distribution.
5. Promotion produces a new staged release candidate and repeats the objective-2 acceptance gates.

Nothing in objective 3 is implemented yet; no new mission engine, model framework or settings store
will be introduced for it.

## Current limits

- No installer/auto-update: the distribution is a portable folder.
- 95 built-in extensions are bundled (including js-debug); the upstream Copilot extension is present
  but its SDK is not bundled, so native Copilot chat is not part of this build. NL Chat is the
  supported assistant.
- Remote development dependencies are not installed.
- Engine path is external by design; moving the distribution to another machine requires a reachable
  engine installation or `NLCODE_ENGINE_ROOT`.
- Branding uses the generated NL Code icon and product names; deeper UI theming and removal of the
  upstream Copilot onboarding dialog are later increments.

## REA MCP server

The installed `rea` package is registered as the trusted local stdio server `rea`
in the active user configuration `data/mcp_servers.json`. It exposes a curated
read-only allowlist (binary/Mach-O/WASM/JavaScript inspection, disassembly,
xrefs and analysis) so Chat can discover it without loading 229 tools into one
context. Tool invocation remains permission-gated; no execution permission is
granted just by configuring it.

## Executables

The staged standalone folder contains:

- NL Code.exe — Code - OSS workbench;
- NL Code Launcher.exe — sets NL_ENGINE_ROOT/NL_DATA_DIR from BUILD_INFO.json and starts the workbench;
- NL Code Launcher.lnk — shortcut for the launcher;
- NL Code.bat — fallback batch launcher.

Double-click NL Code Launcher.exe (or the .lnk). The launcher keeps the existing engine installation and its data; it does not duplicate the Python runtime.

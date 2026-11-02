# NL Coding Agent

**Local-first, multi-agent software-development orchestrator for Windows.**

NL Coding Agent opens an existing project, discovers its documentation and codebase, builds a
project profile automatically, and runs a multi-agent **Developer -> Tester -> Debugger -> Reviewer**
cycle against it using local Ollama models. State, missions, verification runs and diffs are
persisted in SQLite, so work survives restarts and interruptions. The orchestrator can also develop
**itself** under the same verification gates (Self-Build Mode).

The product is not a chat wrapper and not a cloud coding assistant. Its defining capability is
**orchestration**: task decomposition, precise handoffs, resource-aware scheduling, verification,
conflict prevention, persistent state and controlled self-development.

## Download and install

Latest beta packages are published on the
[GitHub Releases page](https://github.com/Nicotina4ever/NL-Coding-Agent/releases):

- **Windows portable** (`NL-Code-Portable.zip`) — unpack and run `NL Code.bat`.
- **Windows setup** (`NL-Code-Setup.exe`) — small bootstrapper; downloads the portable payload
  from the same release and installs it under `%LOCALAPPDATA%\Programs\NL Code`, with Desktop and
  Start shortcuts. It carries no duplicated engine/runtime.
- **NL Coder extension** (`NL-Coder.vsix`) — install into VS Code Insiders, or use
  `Installa NL Coder.cmd`.

Platform status: **Windows x64 is built and verified locally** (launch, embedded engine, PowerShell
and Command Prompt terminals, Chat, clean process shutdown). macOS and Linux packages are **not
published yet**: they require their own build/validation runners and are not declared available.

## Quick start (this checkout)

From the repository root (no absolute path is stored in the launchers):

- `Avvia NL Code.cmd` — starts the local standalone payload, resolving it relative to this file.
- `Apri Installer.cmd` — opens `.workspace\releases\windows`.
- `Installa NL Coder.cmd` — installs the VSIX into VS Code Insiders.
- `GitHub Releases.cmd` — opens the public releases page.
- `scripts\nlcode\install_shortcuts.ps1` — creates/removes the corresponding Desktop and Start-menu
  shortcuts. `scripts\nlcode\build_release.ps1` assembles the local release folder.
- The legacy `NL Coding Agent.bat` starts the old PySide6 GUI; it is not part of the new
  standalone/extension distribution.

## Repository vs packages

Release packages contain only the standalone payload with its one embedded engine runtime and the
NL Coder VSIX. The `tests/` suite and the legacy PySide6 source are **development/verification
assets, not shipped in the installers**; they stay in the repository so the engine and extension can
be validated. `da_eliminare/` is local review staging only and is no longer tracked. Models remain in
Ollama; no model weights are packaged.

## Documentation

- [Current state and verified limits](docs/CURRENT_STATE.md)
- [Operational plan and acceptance gates](docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md)
- [Next self-build mission](docs/NEXT_SELF_BUILD_MISSION.md)
- [Safety, storage and packaging rules](docs/SAFETY_AND_STORAGE.md)
- [Documentation index](docs/README.md)


## Status

Early-stage but functionally exercised: the end-to-end developer/tester/debugger/reviewer cycle has
been run with a live local model and an interruption/resume cycle. Safety staging, rollback and the
persistent supervisor are implemented with gate evidence; the CrewAI/Flows runtime seam and model
intelligence are integrated. The supported interfaces are the NL Coder VS Code extension and the
NL Code Code - OSS workbench; both use the same Python engine. The PySide6 GUI remains in the
repository as a legacy interface and is excluded from normal development and acceptance.

Baseline at the 2 November 2026 checkpoint: the Python suite passes (1387 tests at the previous
checkpoint, see `docs/CURRENT_STATE.md` for the final count). Recent work fixed the Team Architect
-> specialist execution path, restored the tools each agent stage is promised, enforced the mission
wall-time budget, removed orphan staging copies on mission delete, and implemented P1-P5:

- a per-model dynamic Context Engine (measured/configured window, output and thinking tokens
  reserved, loss-minimising incremental digest) with a persisted project profile, selective file
  retrieval and shared project memory;
- code intelligence as read-only `search_symbols`/`lsp_diagnostics` model tools (real `pylsp`
  diagnostics with file/line/column), plus a static post-write gate that rejects a candidate before
  the tester and a verified autonomous repair path (`tests/test_flow_repair.py`);
- progressive project skills, isolated sub-agents with structured handoffs, and dynamic multiple
  read-only advisors consumed by the Supervisor;
- one ModelRouter-based routing evidence path shared by Chat and Missions, with explicit requests
  preserved and cloud escalation still opt-in;
- a rebuilt VSIX (installed acceptance passed) and a rebuilt Code - OSS standalone (GUI acceptance
  `NLCODE-STANDALONE-ACCEPTANCE-PASS`) with a regenerated portable ZIP. The standalone acceptance
  now runs real commands in both the PowerShell and Command Prompt terminals and fails if either
  does not work; the terminal regression was traced to the packaged `product.json` missing
  insider quality/version/commit fields (fixed in the build branding).

Real local-model evidence (mission with advisor and skills, repair, Chat continuity) is under
`docs/evidence/nlcode/`. Multimodal attachments, Vision handoff, local ASR and web research are
implemented and tested. See `docs/CURRENT_STATE.md` for what is verified and what is still missing.

Remaining declared gaps: the repair branch has not yet been exercised with a real model when the
candidate itself introduces the failure (deterministic seam plus a real pre-existing red test are
verified); the standalone payload references the repository engine (`engineRoot`) instead of
embedding an independent runtime; a full team mission has not yet been run from the installed
standalone UI. No release claim is made until the acceptance gates in
`docs/08_ACCEPTANCE_GATES.md` and the release requirements in `docs/PRODUCT_BACKLOG.md` pass.

## Requirements

- Windows 11 is the primary verified development target (Windows-first CI/startup evidence).
- Windows: the embedded Python runtime and dependencies are **already included** under `python/`;
  do not create a venv/conda environment.
- Linux/macOS: POSIX `.sh` launchers are now shipped for the private beta, but the provisioned
  native runtime is still unmeasured/MANUAL-PENDING and no support claim is made. Packaged beta
  installs must use `python/bin/python3` from the payload; system Python is a source-checkout
  developer fallback only.
- Ollama installed and running locally for local-model inference (models are discovered
  dynamically and are never hard-coded). Cloud escalation is opt-in only.
- NVIDIA RTX 4060 Ti 8 GB VRAM / 32 GB RAM is the reference target; the app degrades gracefully.

## Quick start

All commands run from the repository root (the folder containing this file). Launchers resolve
their own location, so they can be double-clicked or started from any working directory.

| Entry point | Purpose |
|---|---|
| `NL Coding Agent.bat` | Legacy PySide6 GUI launcher; retained but not a supported development or acceptance surface. |
| `scripts\launchers\doctor.bat` | Windows environment diagnostics (runtime, CrewAI, Ollama, project state). |
| `scripts\launchers\status.bat` | Windows persisted projects/missions/state summary. |
| `scripts\launchers\Self-Build Mode.bat` | Windows one guided self-build mission with persisted state and resume hint. |
| `scripts/launchers/NL Coding Agent.sh` | Legacy PySide6 GUI launcher for Linux/macOS beta (staged to the payload root). |
| `scripts/launchers/doctor.sh` | POSIX read-only environment diagnostics (payload root: `doctor.sh`). |
| `scripts/launchers/status.sh` | POSIX persisted-state summary (payload root: `status.sh`). |
| `scripts/launchers/Self-Build Mode.sh` | POSIX explicit one-mission launcher (payload root, preserves exit codes). |
| `scripts/launchers/NL Coding Agent.command` | macOS Finder wrapper that execs `NL Coding Agent.sh`. |
| `scripts\launchers\voicebridge\audit_voicebridge.bat` | Read-only audit of the external NL VoiceBridge Studio project. |
| `scripts\launchers\voicebridge\work_voicebridge.bat` | Prepare a task for the external VoiceBridge project. |

The diagnostics/status/self-build launchers are developed under `scripts/launchers/`; the portable
payload stages them back to the payload root under the same user-facing names, for both Windows
(`doctor.bat`, `status.bat`, `Self-Build Mode.bat`) and POSIX (`doctor.sh`, `status.sh`,
`Self-Build Mode.sh`, `NL Coding Agent.sh`, plus the `.command` Finder wrapper). The POSIX
launchers look for the provisioned runtime at `python/bin/python3` (compatibly
`runtime/bin/python3`); in a source checkout only they may warn and fall back to system
`python3` for development. A packaged payload without the runtime fails closed with installer
instructions. Launchers pass all arguments through, preserve exit codes and never start a model
mission except when the user explicitly runs Self-Build Mode.

## Supported editor interfaces

Use **NL Code** for the standalone Code - OSS workbench, or install **NL Coder** in VS Code
Insiders. They share the Python engine, model configuration and persistent data; there is no
separate supported PySide6 product UI. See [NL Code standalone](docs/NL_CODE_STANDALONE.md) for
build and acceptance requirements. The repository-root `NL Coding Agent.bat` remains only as a
legacy launcher.

Equivalent CLI form (use the embedded runtime explicitly):

```powershell
python\python.exe nl_agent.py doctor
python\python.exe nl_agent.py --help
```

For structured delegation from Codex or another CLI client, use the existing mission
executor (choose installed models explicitly; Ollama must be running):

```powershell
python\python.exe nl_agent.py mission --project "C:\path\to\project" --goal "Implement the requested change and preserve existing tests" --dev-model "ollama/qwen2.5-coder:7b-instruct-q4_K_M" --reviewer-model "ollama/qwen2.5-coder:7b-instruct-q4_K_M" --debug-model "ollama/qwen2.5-coder:7b-instruct-q4_K_M" --json
```

This executes source changes under the project's existing permissions and resource
controls. Stdout is one JSON result with changed paths, verdict, promotion status and
paths to managed logs/full verification evidence. Exit status is nonzero unless the
mission completed. Independently inspect the diff and evidence; test execution uses
your OS privileges. Cloud routes still require explicit project permission. Resume
with `--resume <id>` and the same project instead of supplying a new goal.

External clients can inspect this same engine through MCP (optional dependencies
`mcp>=1.30,<2` and `jsonschema`; already present in the development runtime):

```powershell
python\python.exe nl_agent.py mcp serve --project "C:\path\to\project"
python\python.exe nl_agent.py mcp vscode-config --project "C:\path\to\project"
```

`serve` uses stdio and defaults to read-only mission/context/diff access. The second
command prints a VS Code configuration example with actual installation paths;
it never edits another application's configuration. Owner opt-in `--allow-execution`
enables start/cancel tools, whose calls still require approval and project permissions.
Clients must keep the server connection open while a mission runs; disconnect requests
a cooperative stop. Stop is observed at safe checkpoints, not by killing model requests.
Status, events, candidate diff and verification evidence refer to the existing SQLite
missions and Supervisor, including rejected candidates. No additional editor or engine
is installed. Pinned upstream source findings: [external references](docs/EXTERNAL_SOURCE_REFERENCES.md).

For external tools, `mcp tools --project <folder> --server <name>` discovers and
`mcp invoke --project <folder> --server <name> --tool <name> --arguments '{}' --approve`
invokes a configured server. Configuration is `data/mcp_servers.json` or explicit
`--config`; entries need `trusted: true`. Stdio entries specify `command`/`args`, HTTP
entries `transport: "http"`/`url`. Optional `allowed_tools` restricts exact tool names.
Startup requires READ/EXECUTE; invocation also WRITE; HTTP requires NETWORK and remote
HTTP also CLOUD. Arguments are schema-validated without fetching remote schemas.
External servers run with OS user privileges: trust is not an OS sandbox, and their
results remain untrusted. Model-driven automatic selection/invocation is not integrated.

CLI commands: `doctor`, `audit`, `work`, `status`, `roadmap`, `mission`, `mcp`,
`selfbuild`, `supervisor`, `gui`.

## NL Coder (VS Code extension)

`frontend/` is the VS Code / VS Code Insiders extension **NL Coder** (`0.7.2`, extension ID
`nlcodingagent.nl-coding-agent`): complete NL Chat plus real mission control over MCP. It has no models,
missions, permissions or persistence of its own; the Python engine remains the single source of truth
for both supported editor interfaces. The PySide6 GUI is legacy and is not part of routine acceptance.

```powershell
cd frontend
npm install
npm run compile
code-insiders --extensionDevelopmentPath="K:\AI\NL Coding Agent\frontend" "K:\path\to\a\project"
```

The **NL** activity-bar view has **Chat / Missions / Engine** tabs. Chat supports provider/model
selection with an **Automatic** engine-default mode, project-scoped file attachments (picker, drag &
drop, current file, selection, `@file` autocomplete, and pasted screenshots with Ctrl+V), visible editor context, URLs fetched
only on explicit confirmation through the existing Research service/permissions, and engine-persisted
history. Images go only to a measured Vision-capable specialist; its text handoff is marked untrusted
for the selected Chat model and other agents. The **Engine** tab
shows the existing model/agent/permission configuration, local ASR engine/model catalog and the
read-only research profile/NETWORK status. Choose an ASR engine and one of its local models before
dictation; curated downloads appear in the same model menu and require the project NETWORK grant and
explicit confirmation. External Faster-Whisper, Vosk, Qwen3-ASR and whisper.cpp model folders are
registered and reused in place, never copied. Switch the composer
to **Mission** (or use `/mission <objective>`) to start a real Supervisor
mission on the opened project. Missions show progress, task/agent handoffs, candidate + oracle
verification, reviewer verdict and the candidate or retained diff; Stop and Resume use the engine's
existing cooperative lifecycle. Mission execution is opt-in with `nlCodingAgent.allowExecution` (each
start/stop still asks for confirmation); without it the engine is read-only. URL fetch uses the
built-in bounded HTTPS transport and requires the project NETWORK grant; the matching `web-fetch`
capability follows that same Project Access scope. The Research profile still controls automatic
approval. Web search additionally requires a configured provider. The mission planner is proportional:
the core developer/tester/reviewer team gains
a read-only architect for multi-file/design work and an auditor for security/audit objectives; the
multi-agent runtime audit is in `docs/ARCHITECTURE_AND_ENGINE.md`. Commands: **Start Chat**, **Start
Mission…**, **Show Missions**, **Show Engine Settings**, **Toggle Mission Execution**, **Show Backend
Status**, **Reconnect Backend**.

A locally installable VSIX is produced with:

```powershell
cd frontend
npm run package:vsix      # .workspace\dist\NL-Coding-Agent-0.7.2.vsix
code-insiders --install-extension ..\.workspace\dist\NL-Coding-Agent-0.7.2.vsix
```

Set `nlCodingAgent.engineRoot` when installing on a machine where the engine is not resolvable from the
extension folder. The installed extension is **NL Coder** (extension ID `nlcodingagent.nl-coding-agent`)
and uses the real product logo as its icon. Real acceptance (isolated project mission completed with diff, candidate/oracle tests
PASS and reviewer `APPROVE`; stop→resume; model→conversation; attachment/editor context; authorized
URL fetch→context; installed-VSIX chat and mission acceptance) is recorded in
`docs/CHAT_AND_SESSIONS.md` and `docs/evidence/frontend/`; protocol/architecture
details are in `docs/FRONTEND_ARCHITECTURE.md`. A standalone distribution is current only when its
portable profile contains the same accepted NL Coder VSIX version.

## NL Code standalone (objective 2)

The standalone Windows distribution is built from the local Code - OSS checkout and reuses the same
extension and the same Python engine installation (no duplicated runtime or database). Accepted on
2026-10-29: it starts from its portable profile, loads NL Chat with the real backend project and
tools, returns a real Ollama reply and releases the engine child on close.

```powershell
pwsh -File scripts/nlcode/build_nl_code.ps1 -ResyncSource
.\.workspace\dist\NL Code\NL Code.bat
pwsh -File scripts/nlcode/accept_nl_code.ps1 -SeedFromLiveData
```

Build pipeline, branding overlay, portable-profile design, verification gates and the objective-3
(verified autonomous development) plan are in `docs/NL_CODE_STANDALONE.md`. Generated sources,
dependencies and the release candidate stay under `.workspace/`; the vendor `vscode/` checkout is not
modified.

## Repository layout

| Path | Role |
|---|---|
| `python/` | Embedded Python 3.12 runtime and installed packages. **Protected** — never edited or committed. |
| `nl_coding_agent/` | Application source (CLI, GUI, orchestration, supervisor, flows, project registry, persistence, tools). |
| `frontend/` | VS Code extension frontend (NL Chat over MCP). Source only; `node_modules/` and `out/` are generated locally. |
| `nl_agent.py` | CLI entry point. |
| `tests/` | Automated test suite. |
| `scripts/` | Development and verification tools (read-only audits, gates, portable staging). |
| `scripts/launchers/` | Diagnostics/status/self-build/VoiceBridge launchers; the portable payload re-stages the portable ones to the payload root. |
| `da_eliminare/` | Review-only staging for no-longer-needed material; git-ignored except its README, never shipped, nothing deleted without explicit user authorization. |
| `config/` | Runtime configuration (models, external project paths). |
| `assets/` | Real product logo and theme tokens. |
| `.agents/` | Agent definitions, rules and skills used by agentic development sessions. |
| `docs/` | Consolidated operational documentation; authority order is defined in `docs/README.md`. |
| `data/` | SQLite database, self-build state, backups, mission baselines. **User data — never shipped.** Deliberately outside `.workspace/` (live-data path is a relocation-acceptance dependency). |
| `.workspace/` | Single generated-data root (git-ignored): `build/` transient evidence, `dist/` release payloads (at most one verified candidate), `logs/`, `temp/`, `cache/`, `state/`. Default `<repo>/.workspace`; override with `NL_WORKSPACE_DIR`. |
| `installer/` | Lightweight bootstrapper/installer tooling (stage-6 work in progress). |
| `da_eliminare/crewAI/` | Reference-only CrewAI vendor checkout (own nested `.git`), staged for review by ROOT REORG Phase C (task-46). **Not imported** — the application uses the installed `crewai==1.15.32` package; nothing here is shipped or deleted without owner authorization. |
| `docs/evidence/` | Acceptance and SBOM evidence kept for audit traceability. |

Directory ownership, retention/cleanup policy and the portable-build exclusion list are documented
in `docs/SAFETY_AND_STORAGE.md` and `docs/README.md`.

## Documentation map

| Document | Read it for |
|---|---|
| `AGENTS.md` | **Binding workspace rules**: containment, verification invariant, vendor policy, resource policy. |
| `docs/README.md` | Entry point and authority of the consolidated documentation corpus. |
| `docs/CURRENT_STATE.md` | What is actually implemented and verified today. |
| `docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md` | **Single 1.0 operational plan**, order of work and next self-build mission. |
| `docs/08_ACCEPTANCE_GATES.md` | Real acceptance gates before any stable claim. |
| `docs/OPERATIONS_AND_RESTART.md` | Resume commands, CI/reproducibility rules, what not to touch. |
| `docs/ARCHITECTURE_AND_ENGINE.md` | Engine, CrewAI, Flows, Supervisor and handoff architecture. |
| `docs/CHAT_AND_SESSIONS.md` | Agentic Chat, context, history, queue, steering and stop. |
| `docs/MODELS_TOOLS_AND_SETTINGS.md` | Model Hub, routing, tools, permissions and settings. |
| `docs/PRODUCT_AND_UX.md` | NL identity, mission-first UX and brand tokens. |
| `docs/SAFETY_AND_STORAGE.md` | Storage, privacy, archive/purge and exclusions. |
| `docs/RELEASE_AND_STANDALONE.md` | Standalone NL Code, packaging and release policy. |
| `docs/PRODUCT_BACKLOG.md` | Historical `NL-BP-*` requirements (IDs preserved; source of truth is the live test). |
| `docs/product-blueprint/INDEX.json` | Machine-readable requirement index and program order. |
| `docs/evidence/` | Acceptance and SBOM evidence kept for audit traceability. |

## Verification

Read-only gates (never start a mission or a model run):

```powershell
python\python.exe nl_agent.py doctor
python\python.exe scripts\verify_relocation.py
python\python.exe scripts\verify_supervisor.py
python\python.exe scripts\check_crewai_upgrade.py --verify-sbom
```

Test suite (offscreen GUI):

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONDONTWRITEBYTECODE='1'
python\python.exe -m pytest -q
```

## Safety and containment

- Local models are the default; cloud models require explicit opt-in per project/task.
- User data (`data/`), logs, the embedded runtime, the vendor checkout, release payloads and
  acceptance evidence are protected and are never deleted by repository hygiene.
- `da_eliminare/` is review-only staging: nothing in it is shipped or deleted/archived without
  explicit user authorization.
- Destructive operations are gated; self-build runs are staged and verified with rollback rather
  than applied to a live process.
- Keep permanent project files inside this repository; no sibling workspaces without explicit
  user approval. The full rule set lives in `AGENTS.md`.

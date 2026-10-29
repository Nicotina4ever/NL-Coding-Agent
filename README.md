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

## Status

Early-stage but functionally exercised: the end-to-end developer/tester/debugger/reviewer cycle has
been run with a live local model and an interruption/resume cycle. Safety staging, rollback and the
persistent supervisor are implemented with gate evidence; the CrewAI/Flows runtime seam and model
intelligence are integrated. The Studio GUI, multimodal chat/attachments, voice/ASR and the final
portable release are still in progress (see the program plan in
`docs/product-blueprint/INDEX.json` and the current state in `docs/CURRENT_STATE.md`).
No release claim is made until the acceptance gates in `docs/08_ACCEPTANCE_GATES.md` and the
release requirements in `docs/PRODUCT_BACKLOG.md` pass.

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
| `NL Coding Agent.bat` | Windows desktop GUI (PySide6) — the obvious launcher at the repository root. |
| `scripts\launchers\doctor.bat` | Windows environment diagnostics (runtime, CrewAI, Ollama, project state). |
| `scripts\launchers\status.bat` | Windows persisted projects/missions/state summary. |
| `scripts\launchers\Self-Build Mode.bat` | Windows one guided self-build mission with persisted state and resume hint. |
| `scripts/launchers/NL Coding Agent.sh` | POSIX desktop GUI launcher for Linux/macOS beta (staged to the payload root). |
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

Equivalent CLI form (use the embedded runtime explicitly):

Studio opens a dockable project workspace: files on the left, the existing editor
in the center, persistent Chat on the right and tools/activity in bottom tabs.
Use **Panels** to show, move or reset panels; layout, project and open files restore
after restart. **Enter** sends Chat, **Ctrl+Enter** adds a newline. Ordinary messages
stay conversational. Select the explicit document-plan, coding-task or Goal action
to prepare work; a coding mission starts only through **Run / Resume**.
**Ask in Chat** references selected code; **Open file** in Chat attaches the active
editor snapshot. **Review candidate** displays staged changes and verdicts even when
promotion is blocked. **Ctrl+Alt+C/E/D** focus Chat/editor/document planning.

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

## Repository layout

| Path | Role |
|---|---|
| `python/` | Embedded Python 3.12 runtime and installed packages. **Protected** — never edited or committed. |
| `nl_coding_agent/` | Application source (CLI, GUI, orchestration, supervisor, flows, project registry, persistence, tools). |
| `nl_agent.py` | CLI entry point. |
| `tests/` | Automated test suite. |
| `scripts/` | Development and verification tools (read-only audits, gates, portable staging). |
| `scripts/launchers/` | Diagnostics/status/self-build/VoiceBridge launchers; the portable payload re-stages the portable ones to the payload root. |
| `da_eliminare/` | Review-only staging for no-longer-needed material; git-ignored except its README, never shipped, nothing deleted without explicit user authorization. |
| `config/` | Runtime configuration (models, external project paths). |
| `assets/` | Real product logo and theme tokens. |
| `.agents/` | Agent definitions, rules and skills used by agentic development sessions. |
| `docs/` | Documentation; dated historical bundles live under `docs/history/legacy/`. |
| `data/` | SQLite database, self-build state, backups, mission baselines. **User data — never shipped.** Deliberately outside `.workspace/` (live-data path is a relocation-acceptance dependency). |
| `.workspace/` | Single generated-data root (git-ignored): `build/` transient evidence, `dist/` release payloads (at most one verified candidate), `logs/`, `temp/`, `cache/`, `state/`. Default `<repo>/.workspace`; override with `NL_WORKSPACE_DIR`. |
| `installer/` | Lightweight bootstrapper/installer tooling (stage-6 work in progress). |
| `da_eliminare/crewAI/` | Reference-only CrewAI vendor checkout (own nested `.git`), staged for review by ROOT REORG Phase C (task-46). **Not imported** — the application uses the installed `crewai==1.15.32` package; nothing here is shipped or deleted without owner authorization. |
| `docs/evidence/` | Acceptance and SBOM evidence kept for audit traceability. |

Directory ownership, retention/cleanup policy and the portable-build exclusion list are documented
in `docs/REPOSITORY_STRUCTURE.md`.

## Documentation map

| Document | Read it for |
|---|---|
| `AGENTS.md` | **Binding workspace rules**: containment, verification invariant, vendor policy, resource policy. |
| `docs/CURRENT_STATE.md` | What is actually implemented and verified today. |
| `docs/02_SELF_BUILD_ROADMAP.md` | Product phases and roadmap. |
| `docs/NEXT_SELF_BUILD_MISSION.md` | The next actionable self-build mission. |
| `docs/08_ACCEPTANCE_GATES.md` | Gate definitions for a usable desktop milestone. |
| `docs/PRODUCT_BACKLOG.md` | Consolidated, evidence-based product backlog. |
| `docs/BLUEPRINT_INDEX.md` | Traceability index from the original blueprint to current requirements. |
| `docs/product-blueprint/INDEX.json` | Machine-readable requirement status and **program order** (stages 1-6). |
| `docs/REPOSITORY_STRUCTURE.md` | Directory ownership, build/data/log policy, packaging exclusions. |
| `docs/REPOSITORY_HYGIENE.md` | Stage-5 read-only repository audit (historical measurement). |
| `docs/REPOSITORY_HYGIENE_FOLLOWUP.md` | Structural consolidation performed after that audit. |
| `docs/WORKSPACE_MIGRATION.md` | Completed workspace relocation record and rollback procedure. |
| `docs/COMPLETED_MISSIONS.md` | Verified self-build mission history. |
| `docs/CREWAI_RUNTIME.md`, `docs/PORTABLE_BUILD.md` | CrewAI runtime policy and portable staging evidence. |
| `docs/history/legacy/INDEX.md` | Map of archived legacy documents, patch evidence and the archived one-off repair scripts (`docs/history/legacy/temp-scripts/`). |

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

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

- Windows 11 (the current launchers, installer bootstrap and GUI are Windows-first).
- The embedded Python runtime and dependencies are **already included** under `python/`; do not
  create a venv/conda environment.
- Ollama installed and running locally for local-model inference (models are discovered
  dynamically and are never hard-coded). Cloud escalation is opt-in only.
- NVIDIA RTX 4060 Ti 8 GB VRAM / 32 GB RAM is the reference target; the app degrades gracefully.

## Quick start

All commands run from the repository root (the folder containing this file). Launchers resolve
their own location, so they can be double-clicked or started from any working directory.

| Entry point | Purpose |
|---|---|
| `NL Coding Agent.bat` | Desktop GUI (PySide6) — the single obvious launcher at the repository root. |
| `scripts\launchers\doctor.bat` | Environment diagnostics (runtime, CrewAI, Ollama, project state). |
| `scripts\launchers\status.bat` | Persisted projects/missions/state summary. |
| `scripts\launchers\Self-Build Mode.bat` | One guided self-build mission with persisted state and resume hint. |
| `scripts\launchers\voicebridge\audit_voicebridge.bat` | Read-only audit of the external NL VoiceBridge Studio project. |
| `scripts\launchers\voicebridge\work_voicebridge.bat` | Prepare a task for the external VoiceBridge project. |

The diagnostics/status/self-build launchers are developed under `scripts/launchers/`; the portable
payload stages them back to the payload root under the same user-facing names (`doctor.bat`,
`status.bat`, `Self-Build Mode.bat`), so a portable install keeps the familiar launch files
beside `NL Coding Agent.bat`. See `scripts/launchers/README.md`.

Equivalent CLI form (use the embedded runtime explicitly):

```powershell
python\python.exe nl_agent.py doctor
python\python.exe nl_agent.py --help
```

CLI commands: `doctor`, `audit`, `work`, `status`, `roadmap`, `mission`,
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
| `data/` | SQLite database, self-build state, backups, mission baselines. **User data — never shipped.** |
| `logs/` | Run logs and historical mission output. **Never shipped.** |
| `build/` | Transient build/audit evidence and scratch output (git-ignored). |
| `dist/` | Release payloads; at most one verified candidate (git-ignored). |
| `installer/` | Lightweight bootstrapper/installer tooling (stage-6 work in progress). |
| `crewAI/` | Reference-only vendor checkout of CrewAI. **Protected; not imported** — the application uses the installed `crewai==1.15.32` package. |
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

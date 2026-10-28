# Current State — NL Coding Agent

## Overview

NL Coding Agent is a local-first, multi-agent software development workstation. It opens existing projects, discovers their structure and documentation, persists missions in SQLite, and runs a real `Developer -> Tester -> Debugger -> Reviewer` cycle using local Ollama models. The current implementation has been exercised end-to-end with a live local model and a real interruption/resume cycle.

## Verified Operational Capabilities

### 1. Dedicated Runtime
- **Python**: embedded Python 3.12 at `python\python.exe`.
- **Launcher**: `python\python.exe nl_agent.py <command>` because the embedded runtime is isolated and does not add the workspace to `sys.path`. All `.bat` launchers use this path.
- **Dependencies**: `PySide6`, `psutil`, `crewai`, `pytest`, `sqlite3` verified.
- **Vendor Integrity**: `python/`, `crewAI/`, and `crewAI-tools/` are treated as protected vendor trees.

### 2. Project Registry & Discovery (Zero Per-Project YAML)
- **Module**: `nl_coding_agent.projects` (`scanner.py`, `registry.py`).
- Automatic detection of project language, frameworks, build systems, and documentation.
- Persistence in SQLite (`data/nl_coding_agent.sqlite3`).
- Projects can be opened from arbitrary paths, listed in Recent Projects, and removed without deleting files.

### 3. Model Registry & Resource Monitoring
- **Module**: `nl_coding_agent.models.ollama_registry`.
- Dynamic query of installed Ollama models via HTTP API and CLI fallback (`ollama list`).
- Real-time detection of currently loaded models (`ollama ps`).
- Hardware monitoring via `psutil` (system RAM) and `nvidia-smi` (GPU VRAM).
- Developer/reviewer/debugger models can be overridden per mission with `--dev-model`, `--reviewer-model`, `--debug-model`, or `NL_DEVELOPER_MODEL`, `NL_REVIEWER_MODEL`, `NL_DEBUG_MODEL`.

### 4. Operational Coding Tools (Project-Scoped Safety)
- **Module**: `nl_coding_agent.tools`.
  - `filesystem.py`: scoped read/write/patch/list with traversal protection and protected-path denial.
  - `shell.py`: binary-safe command execution with UTF-8/OEM decoding fallback; fixes Windows `charmap` and `UnicodeDecodeError` failures.
  - `git_tools.py`: UTF-8-safe `get_git_status`, `get_git_diff` including untracked source/test files.
  - `verification.py`: auto-detects `pytest`, `cargo`, `npm`, or `ctest` and runs real verification.
  - `crew_tools.py`: exposes the tools to CrewAI agents.

### 5. Multi-Agent Orchestration & Self-Build Cycle
- **Module**: `nl_coding_agent.agents.orchestrator`.
- **Pipeline**: `Developer -> Tester -> Debugger -> Reviewer`.
- **Change evidence**: workspace snapshots prove that an LLM actually modified files; a mission-scoped unified diff is persisted and reviewed. A developer stage with no file change fails instead of being reported as complete.
- **Review gate**: only a parsed `APPROVE` marks a mission `completed`; `REJECT` marks it `blocked`.
- **Write scope**: mission paths are extracted from the goal/roadmap and enforced against actual changes.
- **Single-writer lock**: `nl_coding_agent.core.mission_lock` prevents two processes from modifying the same working tree.
- **Persistence**: missions, tasks, attempts, handoffs, verification runs, diffs, changed paths, verdicts and resume counts are stored in SQLite.
- **Recovery**: interrupted tasks are reset; a persisted mission baseline allows the reviewer to see the original mission diff after a restart. `--stop-after developer|tester` supports deliberate interruption tests.
- **Roadmap (legacy manual path)**: `nl_coding_agent.core.roadmap` parses `docs/NEXT_SELF_BUILD_MISSION.md`; `selfbuild --from-roadmap` creates and runs the next mission without per-project YAML. The persistent supervisor does **not** read this file.
- **Self-Build Mode (deprecated shim)**: `selfbuild --autonomous` / `--loop` now delegates to the stage-3 supervisor through `nl_coding_agent.core.selfbuild_runner` (legacy result shape preserved; C5/C7 fail-closed guards retained; `data/selfbuild_state.json` remains historical). It prints a deprecation warning; use `supervisor run`.
- **Persistent supervisor (stage 3)**: `nl_coding_agent.core.supervisor` with durable `mission_queue`, `supervisor_leases`/`supervisor_runs`, `backlog_items` mirror, `mission_evidence` and `approvals`; selection comes from `docs/product-blueprint/INDEX.json` program order (no fixed Markdown dependency); CLI/service/GUI surfaces start/stop/pause/resume it. See the new section 8 and `docs/PHASE3_SUPERVISOR_PLAN.md`.
- **Handoff verification**: `scripts/verify_handoff_and_resume.py` checks launcher wiring, CLI flags, SQLite handoffs, autonomous state, recovery evidence, lock hygiene, and the full test suite. `scripts/run_tracked_selfbuild_test.py` launches one real tracked cycle through the autonomous CLI. Stage-3 acceptance uses `tests/test_supervisor_sh07.py`, `scripts/run_supervisor_sh07.py` and the read-only `scripts/verify_supervisor.py`.

### 6. Desktop GUI (PySide6)
- **Entry**: `NL Coding Agent.bat` or `python\python.exe nl_agent.py gui`.
- Real brand identity using `assets/LogoMio.svg` and `assets/theme.tokens.json`.
- Electric violet accents, dark layered surfaces, high-contrast monospace log/inspector typography, zero glow on code or text.
- Interactive panels:
  - **Sidebar**: Projects, Files, Tasks, Agents, Models, Settings.
  - **Projects Panel**: Open Project, Recent Projects, Self-Build, Audit, New Mission.
  - **Files**: read-only `QFileSystemModel` browser with protected-directory filtering and safe preview via `AppServices`.
  - **Tasks**: mission list, task tree grouped by state, progress, handoffs, verification runs, and Run/Resume action.
  - **Agents**: read-only role/model table for architect, developer, tester, debugger, and reviewer, with dynamic Ollama availability and resource policy.
  - **Settings**: read-only project root, SQLite path, Ollama URL, model-config path, and cloud-escalation state.
  - **Inspector**: project facts, selected file, or mission result/verdict/diff.
  - **Log Panel**: real-time backend event stream.
  - **Status Bar**: live RAM, VRAM, and task queue counts; Ollama connection state.

### 7. CLI Entry Points
- Preserved legacy commands: `doctor`, `audit`, `work`, `status`.
- Operational commands:
  - `roadmap [--project <path>]`
  - `mission --project <path> --goal <text>`
  - `mission --resume <id> --project <path>`
  - `mission --list` / `mission --show <id>`
  - `selfbuild --from-roadmap`
  - `selfbuild --goal <text>`
  - `selfbuild --autonomous [--resume <id>] [--max-missions <1-5>]`
  - `gui`
- Shared flags: `--stop-after`, `--dev-model`, `--reviewer-model`, `--debug-model`.
- Dedicated launcher: `scripts\launchers\Self-Build Mode.bat` (embedded Python, default reviewer
  `ollama/qwen3.5:9b`; the portable payload re-stages it to the payload root as `Self-Build Mode.bat`).
- Persistent supervisor (stage 3): `supervisor run|start|stop|pause|resume|status|index|recover|advance-stage`
  with `--project/--mode/--max-missions/--json/--confirm-assisted` and documented exit codes
  0/1/2/3/4; `selfbuild --autonomous` is a deprecated compatibility shim.

### 8. Persistent Autonomous Supervisor (Stage 3, C3a-C3d)
- **Module**: `nl_coding_agent.core.supervisor` + `persistence.supervisor_store` + `core.backlog`,
  `core.run_control` and `core.resource_gate`.
- **Durable state**: `mission_queue` (idempotency keys, claim tokens, retry/back-off,
  dead-letter), `supervisor_leases`/`supervisor_runs` (CAS lease + heartbeat), `backlog_items`
  (SQLite mirror of the authored index), `mission_evidence`, `approvals`, `supervisor_commands`.
- **Selection**: `docs/product-blueprint/INDEX.json` program order + requirement dependencies;
  the supervisor does not consume `docs/NEXT_SELF_BUILD_MISSION.md` and fails closed on a
  missing/corrupt index.
- **Preflight**: relocation readiness, promotion journals, stale stage sweep, mission lock,
  legacy missions, backlog sync, permissions (read/write/execute), model/resource gate, config
  sanity, read-only git state; blockers return an exact resume command.
- **Execution**: one mission at a time drives the staged-candidate orchestrator; queue,
  backlog, evidence and run counters are updated after each outcome; repair/retry is bounded
  and hard failures stop fail-fast.
- **Control**: Off/Assisted/Automatic modes, budgets, durable stop/pause/resume commands,
  deterministic exit codes; stop is cooperative at safe checkpoints (never mid-promotion).
- **GUI/service**: background `SupervisorService` thread (non-blocking), Autonomy page,
  status-bar supervisor state and emergency STOP; Settings shows the read-only permission
  policy.
- **Evidence**: SH-07 **Tier A verified** (`tests/test_supervisor_sh07.py`, 7 tests; runner
  evidence in `.workspace/build/phase3/evidence/`); **Tier B (real local models) pending explicit
  authorization** — NL-BP-063 stays blocked and automatic mode remains opt-in.

### 9. Stage-4 CrewAI/Flows integration (C4a-C4e, engineering record)
- **CrewRuntime seam**: ```agents/crew_backend.py``` + typed ```agents/specs.py```; orchestrator
  model calls route through an injectable runtime; production path stays one single-agent
  sequential Crew per stage; staged-candidate gates/promotion unchanged.
- **Flows (opt-in)**: ```nl_coding_agent/flows/``` implements ```MissionState```, app-owned
  ```AppFlowPersistence``` (application SQLite only, pinned ids, durable-state resume),
  ```MissionFlow```, ```SupervisorRunFlow``` and the CrewAI event bridge;
  ```agents/supervisor_executor.py``` drives the real orchestrator stages. Enabled only by
  ```pipeline="flow"``` / CLI ```--pipeline flow```.
- **HITL**: deterministic ```flows/approval_provider.py``` maps pause requests to durable
  approvals rows; CLI/backend decisions audit human actions; deny blocks with live unchanged;
  no model-collapsed risk approval.
- **Model intelligence**: ```models/capabilities.py``` (measured/declared/unknown) and
  ```models/model_router.py``` (ModelBinding, capability filter, permission gate, no silent
  cloud fallback, mission model snapshots); memory remains off (local policy deferred).
- **Acceptance**: fake-model stage-4 suites green; deterministic SBOM
  ```docs/evidence/crewai_sbom.json``` verified (pins crewai/crewai-core/crewai-cli 1.15.32;
  ```--compat``` PASS). No real-model Flow run.
- **Rollout decision**: sequential stays default; Flow is opt-in only because real-model Flow
  acceptance evidence is absent. No gate weakened. Stage 4 remains in progress for the remaining
  GUI/multimodal/voice area-4 requirements.

## Verified Evidence

- Full test suite: **65 passed** (`python\python.exe -m pytest`).
- Mission **#40** (Self-Build Resume Command Accuracy):
  - `nl_coding_agent/core/selfbuild_runner.py`: blocked autonomous results now return an exact
    `--resume <mission_id>` command; completed and idle results keep the base command.
  - `tests/test_selfbuild_runner.py`: covers blocked, completed, idle, and explicit-resume
    command construction.
  - The first autonomous developer attempt replaced the runner with a stub and failed verification;
    the original was restored from `data/mission_baselines/40.json`, the change was implemented
    manually, and the mission was resumed through tester and reviewer.
  - Persisted result: `status=completed`, `review_verdict=APPROVE`, `diff_stat=2 file(s), +34/-1`,
    `changed_paths=["nl_coding_agent/core/selfbuild_runner.py",
    "tests/test_selfbuild_runner.py"]`.
- Mission **#39** (Portable User-Data Override):
  - `nl_coding_agent/persistence/database.py` now honors `NL_DATA_DIR`; `db_path()` resolves to
    `<NL_DATA_DIR>\nl_coding_agent.sqlite3` and `selfbuild_state.json` follows the database
    parent. The default remains `APP_ROOT/data` for development compatibility.
  - `tests/test_user_data_path.py` covers the default path, override with directory creation, and
    self-build state placement; `tests/test_foundation.py` and `tests/test_missions_graph.py`
    still patch `_DB_PATH` successfully.
  - `docs/PORTABLE_BUILD.md` documents the override and states that launcher changes, migration,
    and installer work remain pending.
  - Persisted result: `status=completed`, `review_verdict=APPROVE`, `diff_stat=3 file(s), +73/-4`,
    `changed_paths=["docs/PORTABLE_BUILD.md", "nl_coding_agent/persistence/database.py",
    "tests/test_user_data_path.py"]`.
- Mission **#38** (Portable Payload Staging):
  - Added `scripts/stage_portable.py`, `tests/test_stage_portable.py`, and
    `docs/PORTABLE_BUILD.md`; the staged payload excludes `crewAI/`, `crewAI-tools/`, user data,
    logs, tests, docs, scripts, `.git`, caches, and bytecode.
  - Dry-run plan: 23,711 files, 1,547,268,760 bytes (1.44 GiB); embedded runtime is 23,656 of
    those files and 1.44 GiB of the total.
  - The script refuses output inside the source tree or a non-empty output directory, skips
    symlinks, excludes machine-local `config/voicebridge.yaml`, and writes
    `payload_manifest.json` only on a real staging run.
  - Persisted result: `status=completed`, `review_verdict=APPROVE`,
    `diff_stat=3 file(s), +414/-0`, `changed_paths=["docs/PORTABLE_BUILD.md",
    "scripts/stage_portable.py", "tests/test_stage_portable.py"]`.
- Post-#38 portable hardening:
  - `nl_coding_agent/cli.py` now treats a missing YAML file as empty and reports
    `Project: not configured (Project root not configured)` instead of raising a traceback;
    `tests/test_cli_config.py` covers missing config and valid project roots.
  - Real payload staged at `K:\AI\nl-coding-agent-portable-final`: 23,711 payload files plus
    `payload_manifest.json`, 1.44 GiB, no `crewAI/`, `data/`, `.workspace/`, `tests/`, `docs/`,
    `scripts/`, or `config/voicebridge.yaml`.
  - From that payload: `doctor` exited 0 with `CrewAI: OK (1.15.32)`, Ollama reachable, and
    `Project: not configured`; offscreen `MainWindow` constructed six pages and closed cleanly.
  - A smoke project opened through the payload, persisted in its own `data/nl_coding_agent.sqlite3`,
    and was still listed after a second process started.
- Live mission **#16** (local `qwen2.5-coder:7b-instruct-q4_K_M`):
  - Developer created `nl_coding_agent/core/version.py` and `tests/test_version.py`.
  - Mission was intentionally stopped after the developer stage.
  - A new process resumed mission #16; tester ran the full suite; reviewer returned `APPROVE`.
  - Persisted result: `status=completed`, `review_verdict=APPROVE`, `diff_stat=2 file(s), +8/-0`, `changed_paths=["nl_coding_agent/core/version.py","tests/test_version.py"]`.
- Live mission **#24** (Agents & Settings panels):
  - Developer added `AgentsPanel`, `SettingsPanel`, service accessors, MainWindow wiring, and tests.
  - Tester ran the full suite; reviewer initially rejected with false import claims, then a stronger
    reviewer model returned `APPROVE`.
  - Persisted result: `status=completed`, `review_verdict=APPROVE`, `diff_stat=6 file(s), +420/-15`.
- Mission **#37** (Native CrewAI Runtime Integration):
  - `pyproject.toml` now pins `crewai==1.15.32`; `tests/test_crewai_runtime.py` proves the
    runtime import path and version; `docs/CREWAI_RUNTIME.md` records the vendor-exclusion and
    license follow-up.
  - The autonomous developer initially overwrote `pyproject.toml` and broke pytest collection;
    the developer output was manually corrected before the tester and reviewer stages.
  - Persisted result: `status=completed`, `review_verdict=APPROVE`,
    `diff_stat=3 file(s), +84/-1`, `changed_paths=["docs/CREWAI_RUNTIME.md","pyproject.toml",
    "tests/test_crewai_runtime.py"]`.
- Mission **#36** (Distribution Audit and Size-Reduction Plan):
  - Manually completed after the autonomous developer produced placeholders and no tests; the
    developer task was marked completed with a recorded manual handoff.
  - Added `scripts/audit_distribution.py`, `tests/test_distribution_audit.py`, and
    `docs/DISTRIBUTION_AUDIT.md`; diff was `3 file(s), +550/-0`.
  - Tester ran the full suite; reviewer returned `APPROVE`.
  - Audit result: total `2,215,430,573` bytes (2.06 GiB), protected trees `2,209,811,571` bytes
    (99.75%), duplicate reclaimable space `270` B, runtime `crewai` 1.15.32 imported from
    `python/Lib/site-packages`, and `crewAI-tools` absent.
- Autonomous mission **#30** (Self-Build Mode Regression Test):
  - Created only `tests/test_selfbuild_mode.py`; post-mission hardening made the test resolve the
    repository root via `Path(__file__).resolve().parents[1]` instead of `os.getcwd()`.
  - Persisted result: `status=completed`, `review_verdict=APPROVE`,
    `diff_stat=1 file(s), +35/-0`, `changed_paths=["tests/test_selfbuild_mode.py"]`.
  - `data/selfbuild_state.json` now points at mission #40 after the completed-roadmap guard
    reconciled state on the next idle run; rerunning the same roadmap returns `idle` instead of
    duplicating work.
- Handoff verification:
  - `python\python.exe scripts\verify_handoff_and_resume.py` passed launcher, CLI, SQLite,
    autonomous-state, recovery, lock-hygiene, and full-suite checks.
  - `scripts/run_tracked_selfbuild_test.py --max-missions 1` returned `idle` with mission #30
    completed and `APPROVE`, proving the duplicate-work guard.
- Legacy mission **#7** remains in the database as historical evidence of an earlier interrupted run. Its old developer output replaced `status.py` with placeholders; that file has since been replaced by the real psutil implementation.
- GUI smoke test: offscreen `MainWindow` constructs with seven stack pages (including the
  Autonomy page), opens the project, previews `nl_coding_agent/core/version.py`, shows mission
  #16, and closes cleanly (exit 0).
- Models page smoke test: Ollama reachable, 18 models listed, 0 loaded at check time; GUI teardown no longer crashes after waiting for the model-fetch thread.

## Roadmap

- Completed: Task Board & File Viewer integration, Agents & Settings panels, Self-Build Mode
  Regression Test, Distribution Audit and Size-Reduction Plan, Native CrewAI Runtime Integration,
  Portable Payload Staging, Portable User-Data Override, Self-Build Resume Command Accuracy
  (`docs/COMPLETED_MISSIONS.md`).
- Handoff gate: verified. The autonomous engine, durable resume, launcher, SQLite evidence,
  duplicate-work guard, and exact blocked-resume command have all been exercised.
- **Program stage 3 (persistent supervisor and verified handoff) - in progress:** C3a-C3d are
  implemented (durable queue/lease/preflight/backlog planner, CLI/service/GUI control surfaces,
  selfbuild shim) and SH-07 **Tier A** (fake model, two consecutive staged-candidate missions)
  is verified by `tests/test_supervisor_sh07.py` (7 tests) with runner evidence under
  `.workspace/build/phase3/evidence/`. **Tier B** (real local models on an isolated worktree) is NOT yet
  executed and requires explicit Lead/user authorization; until then NL-BP-063 stays blocked,
  program stage 3 stays in progress, and automatic mode remains opt-in/off by default.
- Next: run/authorize Tier B SH-07 evidence, then close program stage 3. Packaging, installer,
  licensing, and final clean-directory acceptance remain future work.
- Deferred: lightweight cross-platform bootstrapper and native platform validation
  (`docs/09_DISTRIBUTION.md` and the future backlog).

## Known Boundaries

- Hardware behavior (ASIO, audio latency, browser media sync, device routing) is not verified by compilation or unit tests and must remain marked pending.
- Cloud models remain opt-in; the verified cycle used local Ollama only.
- Reviewer quality depends on the selected local model; the default reviewer is now
  `ollama/qwen3.5:9b`, and the verdict parser intentionally treats ambiguity as `REJECT`.
- `selfbuild --autonomous --stop-after developer|tester` is accepted by the CLI but is not yet
  forwarded through `run_autonomous`; deliberate interruption testing currently relies on a
  failed or externally interrupted mission.
- State reconciliation after a resumed mission currently happens on the next idle autonomous run,
  not immediately when the resumed mission completes.
- Persistent supervisor limitations: it is a process/thread loop, not an OS service (no reboot
  survival); stop is cooperative at safe checkpoints and can wait for a running model call;
  candidate/test code still runs with the user's OS privileges (no OS sandbox/network
  isolation); the machine inference slot serializes local inference only within one app-data
  database. Tier B real-model acceptance is outstanding.
- The distribution audit, native CrewAI integration, and portable payload staging are complete.
  Clean-directory validation, installer, licensing, and final acceptance remain deferred.


- Mission #41 (Self-Build Recovery Control Accuracy):
  - `nl_coding_agent/core/selfbuild_runner.py`: `reconcile_completed_mission()` validates roadmap match before updating `data/selfbuild_state.json`; `run_autonomous()` accepts and forwards `stop_after`; both resumed-completed and normal-completion paths save state.
  - `nl_coding_agent/cli.py`: autonomous `selfbuild --autonomous` now passes `stop_after=args.stop_after` to `run_autonomous()`.
  - `tests/test_selfbuild_runner.py`: 4 new tests cover forwarding and reconciliation.
  - `tests/test_selfbuild_mode.py`: `test_autonomous_selfbuild_forwards_stop_after` verifies CLI propagation.
  - Developer task #93 failed initially (tool repetition); restored manually, completed with output; resumed through tester/reviewer via autonomous CLI.
  - Live stop-after developer run returned `blocked` with `--resume 41`; resume completed `APPROVE` (`6 file(s), +284/-0`).
  - State reconciled immediately to mission #41 fingerprint `16e8502...` (`updated_at` 2026-10-28T10:01:29); external `docs/product-blueprint/` files (copy-in at 09:37) archived as `data/mission_baselines/41.mission_start.json`; review baseline rebuilt to exclude them from mission diff.
  - Full test suite: **69 passed**.
  - Next command: `python\python.exe nl_agent.py selfbuild --autonomous --project "K:\AI\NL Coding Agent"` (update `docs/NEXT_SELF_BUILD_MISSION.md` before continuing).


## Staged-Candidate Harness (2026-10-28)

The mission pipeline is now transactional (phase-2 commits C1-C7; see
`docs/PHASE2_HARNESS_INTEGRATION_PLAN.md`):

- every model write goes to a staged workspace, never directly to the live tree;
- validation (AST stub/weak-test, scope, protected paths) runs before any live write;
- the tester gate runs independent candidate + oracle regression suites in
  disposable copies of the staged workspace; the oracle pins baseline tests;
- the reviewer reviews the candidate diff and verification evidence before promotion;
- promotion is the last gate: recovery point + compare-and-swap + journal, with
  reconcile-on-resume; a REJECT or gate failure leaves the live tree unchanged;
- `completed` is written only after verified promotion; blocked/interrupted
  missions record staged paths as candidate evidence, not as applied changes.

Database additions (additive): `missions.harness_version`,
`missions.staging_dir`, `missions.promotion_status`. Legacy missions
(without `harness_version`) are refused for resume. The post-hoc runner gate that
used to rescan and rewrite the live tree after a mission was removed; the gate now
exists inside the orchestrator before promotion.

Evidence (2026-10-28): full suite **149 passed** (23 s) including 8 fake-model
end-to-end staging tests (happy path, stub blocked, reviewer reject, stop-after/
resume, human-edit CAS conflict, legacy refusal), promotion/candidate-verification
tests and 4 model-seam tests. The relocation gate remains 30/30 PASS.


## Permissions, External Tools and Retention (2026-10-28)

Stage-2 closure (C9a/C9b):

- **Permission model** (`nl_coding_agent/core/permissions.py`): read/write/execute/delete/
  network/cloud scopes with fail-closed defaults (delete/network/cloud denied until an
  explicit human grant), persisted in `app_settings` (global + optional per-project
  overrides), transactional grant/revoke with audit events, no environment/flag bypass.
- **Cloud escalation gate**: a cloud model requires an explicit CLOUD grant and a
  non-loopback endpoint requires NETWORK; enforced in `_make_llm`/CLI before any LLM is
  constructed. Local loopback Ollama models are unaffected.
- **External tool registry** (`nl_coding_agent/tools/registry.py`): passive, read-only
  discovery of git, embedded Python, pytest, Ollama and ffmpeg with fixed-argv,
  shell-free, time-bounded probes; capabilities are descriptors, not grants;
  `AppServices.list_external_tools()` exposes them read-only.
- **Recovery retention** (`nl_coding_agent/core/retention.py`): read-only audit, verified
  zip archive with per-file sha256 manifest, and all-or-nothing guarded cleanup that
  requires confirmation and a validated archive; recovery points stay delta-only and
  small.
- **Repair evidence**: scripted failing candidate -> one debugger repair -> candidate+
  oracle pass -> reviewer APPROVE -> promotion -> completed (verification rows show
  fail, fail, pass, pass); repair-budget exhaustion blocks with the live tree
  unchanged.

Full suite: **215 passed**. Relocation gate: **30/30 PASS**. Stage 2 is complete except
NL-BP-003 (real local-model end-to-end), which is the stage-3 SH-07 acceptance gate.

### SH-07 Tier B evidence (2026-10-28)

Two real local-model SH-07 attempts were executed in isolated git worktrees with temp
NL_DATA_DIR (no cloud/network, no commits, no live-repo writes). Attempt 1 revealed and led
to fixing a documentation-only candidate hole (commit 2a44460); attempt 2 then BLOCKED
honestly: the local developer model weakened tests/test_selfbuild_mode.py, both attempts
were rejected by validation, the supervisor fail-fast stopped the run, zero promotions and a
clean worktree. NL-BP-063 remains blocked; supervisor default mode remains off and automatic
mode is opt-in. Evidence: docs/SH07_TIERB_EVIDENCE.md and docs/evidence/sh07/.

Program-status correction (2026-10-28)

Stage 4 remains in progress: the C4a-C4e work delivered the CrewAI runtime/Flows/model-intelligence
portion, while the Studio GUI, multimodal chat/attachments, voice/ASR/TTS and IDE surfaces mapped to
program stage 4 are still outstanding. Stage 5 (repository hygiene) is complete and stage 6
(distribution foundation) started early; final release acceptance stays gated on completing the
outstanding stage-4 GUI/multimodal work and on explicit authorization for replacing the stale
.workspace/dist/portable-release payload. No safety gate was weakened and the sequential pipeline remains the
default (Flow opt-in).


### 10. Stage-4 F3b: LSP / MCP / debugger readiness / command palette (2026-10-28)
- **LSP**: read-only detection of locally installed servers (pylsp/pyright/basedpyright/
  clangd/typescript/gopls) and a minimal JSON-RPC stdio client scoped to the open project.
  Diagnostics flow into the Problems panel; hover/completion/symbols are explicit actions.
  No server is installed, downloaded or started automatically; when absent the feature fails
  closed with a clear message. Manual-pending: real language-server diagnostics/hover latency
  was not hardware-verified; tests use a fake transport.
- **MCP**: local JSON config for stdio servers is read-only; tool listing is explicit, and
  tool invocation requires explicit human approval plus the NETWORK grant for
  network-declared servers. No auto-execution and no model-issued tool calls.
- **Debugger/DAP readiness**: read-only debugpy/pdb detection; explicit adapter interface with
  fail-closed behaviour. No debugger starts silently and no arbitrary code is executed by
  detection; full DAP UI remains future work.
- **Command palette**: Ctrl+Shift+P opens a filterable keyboard palette of safe actions only
  (page switching, open-project page, refresh IDE panels, read-only doctor, disabled
  LSP/debug entries with reasons). Destructive/model actions are never listed.
- **Accessibility/responsiveness**: accessible names/tooltips/shortcuts, loading/empty/error
  states and non-blocking refresh paths. DPI scaling and real keyboard focus order remain
  manual-pending on the reference machine.

Stage-4 engineering closure (2026-10-28)

Stage 4 is engineering-complete: CrewAI runtime/Flows/model intelligence (C4a-C4e), multimodal
mission chat with attachments and capability-aware routing (F1), local speech dictation/TTS
foundation (F2), and Studio IDE surfaces (F3a editor/terminal/Git/problems, F3b LSP/MCP/debug
readiness/command palette). Requirements remain partial where acceptance needs real hardware or a
real desktop session: microphone/ASR/TTS hardware, Windows clipboard screenshots, real DPI/focus,
live language-server/MCP/debugger sessions, PTY/OS-sandbox claims. Those items are manual-pending and
must be verified by the user before any release claim; automated evidence (offscreen Qt, fake
transports, temp SQLite) is recorded in docs/HARNESS_ACCEPTANCE.md and the tests. Stage 6 release
acceptance evidence is still in progress.

### Stage-6b portable release acceptance (2026-10-28, measured)

- **Candidate**: .workspace/dist/stage6b-portable-candidate, 23,682 payload files / 1,508,402,351 B
  (1.40 GiB), tree sha256 80e4664618a165d49e7375fc1441a27e1b8416be1eb7206cda8bbe347ffa7b03, payload_manifest sha256
  8b89a2f6...8d7b3; exactly one embedded python runtime copy and one CrewAI package copy.
- **Allowlist**: scripts/stage_portable.py now ships README.md, nl_agent.py, the supported launchers
  (main GUI/self-build + doctor/status), nl_coding_agent incl. flows/, one embedded python runtime,
  assets/, config/models.yaml and pyproject.toml; tests/scripts/installer/docs/.workspace/AGENTS/PATCH/
  data/.workspace/caches/vendor are excluded; staging fails closed on duplicate runtimes and absolute
  workspace paths. Native .pyd extension modules were accidentally excluded and this was fixed
  before the accepted candidate; tests/test_stage_portable.py covers it (8 targeted tests passed).
- **Reproducibility**: two independent stagings produced identical file_count/total_size/tree_sha256
  (80e4664618a165d49e7375fc1441a27e1b8416be1eb7206cda8bbe347ffa7b03); candidate app files match HEAD 7dbd40b byte-for-byte (99/99 non-runtime files).
- **Smoke from a managed non-default temp path**: --help PASS, doctor PASS (read-only ollama list),
  imports incl. flows PASS (all modules resolve inside the temp payload), offscreen GUI construction
  PASS, mission persistence PASS (project+mission created and read back from temp SQLite via
  NL_DATA_DIR), no-dev-only-files PASS, single-runtime PASS, relocation-safe scan PASS, payload
  unchanged by smoke PASS; temp dir removed (23,689 files/1,508,650,018 B) and live data/ untouched.
- **FAIL / release-blocking**: default status/status.bat exits 1 with KeyError 'project' because
  cli.status assumes the machine-local config/voicebridge.yaml, which is correctly not shipped.
  Release acceptance is PARTIAL; a small cli.py fix is outside this task's write scope and is
  requested in docs/RELEASE_ACCEPTANCE.md.
- **Manual-pending**: clean Windows without global Python, clipboard screenshot/drag-drop,
  microphone/ASR/TTS hardware, real multimodal latency, signed installer/published downloads,
  runtime provenance, uninstall/OS integration, GUI full interaction, full pytest baseline (Lead-run).
- **Authorization pending**: replace/remove stale .workspace/dist/portable-release (23,639 files/1,507,677,689 B)
  after final acceptance and retire the extra stage-6a source candidate; no deletion/replacement was
  performed. Evidence: docs/RELEASE_ACCEPTANCE.md and docs/HARNESS_ACCEPTANCE.md.

Stage-6 engineering closure (2026-10-28)

Stage 6 is engineering-complete. The per-user bootstrapper and reproducible source builder (6a)
and the portable payload candidate r2 (23,682 files / 1.40 GiB, one embedded runtime, current
application incl. flows, README, launchers, no development-only files, relocation-safe) were
verified from a managed non-default temporary path: status/--help/doctor/imports/offscreen GUI
PASS, reproducible payload tree hash. The revision-1 release-blocking default-status portability
defect was fixed with regression tests (full suite 513 passed). Release acceptance is explicitly
PARTIAL: clean Windows without global Python, real Windows clipboard screenshot/drag-drop, real
microphone/ASR/TTS hardware, signed installer/update, and full desktop mission execution cannot be
verified in this environment and remain manual-pending. The stale .workspace/dist/portable-release, the
revision-1 candidate and the stage-6a source candidate are retained until the user authorizes
retirement/replacement.

Cross-platform private beta program (2026-10-28)

The repository owner requested a private cross-platform beta for two trusted external testers
(one Linux, one macOS), with Windows x64/ARM64, Linux x86_64/ARM64 and macOS Intel/Apple Silicon
support targets. This extends stage 6 (reopened as in_progress) and adds NL-BP-152..165 to the
persistent indexed backlog (total 117 requirements): compatibility audit/matrix, platform
abstraction with unsupported-configuration handling, native verified runtime/dependency manifests
(never reusing the Windows embedded runtime on Linux/macOS), native bootstrapper/application
candidates, GitHub Actions CI matrix (unit/integration/headless GUI/bootstrapper checks), optional
CPU/GPU/ASR/TTS components with graceful degradation (no mandatory CUDA/ROCm/Metal/MLX), macOS
Universal 2 evaluation or architecture-specific builds, private beta packages with checksums and
non-developer instructions, compatibility matrix, GitHub-Issues feedback workflow and an opt-in
diagnostic report generator with redaction, a pre-upload secrets/history/repository audit, owner-only
authorization gates (no push, visibility change, collaborator invite or release upload), and
MANUAL-PENDING clean-machine/real-hardware acceptance. No cross-platform support is claimed until
CI builds and real-hardware beta tests pass.

Cross-platform private beta progress (2026-10-28, C1-C5)

Implemented and committed: evidence-based six-target compatibility matrix + stdlib platform support
layer (31 tests); six-target native runtime/dependency manifests and provisioner with measured-only
hashes, native-identity guards and offline/cache/repair paths (57 tests); GitHub Actions CI matrix
(Windows x64/experimental ARM64, Ubuntu x86_64/experimental ARM64, macOS arm64/Intel) with unit,
integration, headless GUI and bootstrapper checks (7 tests, CI not executed here); private-beta
feedback workflow with opt-in redacted diagnostic report generator (31 tests) and tester/owner
runbooks; pre-upload secrets/history/repository audit (12 tests, snapshot gate CLEAR-WITH-REVIEW);
and root reorganization Phase A (one root GUI launcher, CLI launchers under scripts/launchers/,
repair scripts archived to docs/history/legacy/temp-scripts/, da_eliminare review staging).

Not yet done / MANUAL-PENDING: real native runtime archives for any non-Windows target, actual
GitHub Actions execution, clean-machine installs, macOS/ARM64 builds, real clipboard/microphone/
GPU/ASR/TTS hardware, per-platform beta packages/checksums and real-hardware beta acceptance. The
secrets audit must be re-run before any upload, and the repository owner must explicitly authorize
any push, visibility change, collaborator invitation or release upload. No non-Windows support is
claimed.

Root reorganization implemented (2026-10-28)

The repository root is now clean and policy-driven: one GUI launcher (NL Coding Agent.bat), CLI and
VoiceBridge launchers under scripts/launchers/, archived repair scripts under
docs/history/legacy/temp-scripts/, the unused crewAI checkout staged in da_eliminare/crewAI/, and
generated outputs consolidated under .workspace/{build,dist,logs,temp,cache,state} with
NL_WORKSPACE_DIR override (nl_coding_agent/core/workspace.py). python/ (embedded runtime) and data/
(live SQLite/user data) stay at their historical paths by design. Root items went 32 -> 21 with no
deletions. Verification: full suite 628 passed, relocation 33/0/1, supervisor gate ok, SBOM OK,
doctor/CLI/GUI smoke PASS, portable staging and release-builder smoke PASS, SHA256_MANIFEST 5/5, and
the pre-upload secrets/history audit re-run at final HEAD is CLEAR-WITH-REVIEW with 0 blocking
findings after a documented synthetic-test-fixture allowlist. Stale release candidates under
.workspace/dist/, da_eliminare/crewAI/ and any upload/publish action still require explicit owner
authorization. See docs/ROOT_REORGANIZATION_REPORT.md.

Stage-6 acceptance tooling (2026-10-28, round 2)

Added and verified the remaining automatable stage-6 distribution/acceptance tooling:
- scripts/build_beta_packages.py builds a deterministic private-beta package from a measured source
  candidate (SHA256SUMS, beta-manifest with the six-target matrix marked unmeasured/release_ready
  false, installer manifest templates without fabricated hashes, INSTALL.md plus six per-platform
  install docs, source zip); the real .workspace/dist/beta-0.2.0 package has 13 verified checksum
  entries and rebuilds byte-identically.
- scripts/release_acceptance.py provides matrix/record/verify commands, enforces explicit
  MANUAL-PENDING states and rejects false CI-as-hardware support; the tracked matrix evidence
  (docs/evidence/beta_acceptance/) records all six targets as MANUAL-PENDING and 0 invalid records.
- scripts/fetch_native_runtimes.py + installer/runtime_sources.json provide the release-runner path
  to acquire and measure real native runtimes for all six targets (dry-run/offline/download, measured
  manifest draft, no fabricated hashes); no real archives were downloaded here.

Final verification for this round: full suite 677 passed; relocation gate 34/0; supervisor gate ok;
SBOM OK; doctor/CLI/GUI smoke/portable staging dry-run/release-builder/beta-package checksums green.
Remaining stage-6 items are external/manual: real native runtime archives and native candidates,
actual GitHub Actions execution, clean-machine and real-hardware beta acceptance, signing/notarization,
and explicit owner authorization for any upload/publish/distribution. No platform support is claimed.

Stage-6 POSIX launchers and CI package smoke (2026-10-28, round 3)

Linux/macOS launchers are now shipped: scripts/launchers/NL Coding Agent.sh, doctor.sh, status.sh,
Self-Build Mode.sh and a macOS Finder NL Coding Agent.command wrapper. They resolve both the source
and portable-payload layouts, use the provisioned python/bin/python3 runtime when present, warn only
for an explicit developer system-python fallback, fail closed with installer/bootstrapper guidance
when a packaged payload has no runtime, forward arguments, preserve exit codes and never auto-start
a model mission. stage_portable maps them to the payload root and stages them executable; shell
syntax is validated and the declarations/tests/matrix were updated, but no real non-Windows runtime
exists here so execution remains MANUAL-PENDING.

CI now also has a blocking package-smoke job (ubuntu-latest) which builds a source release candidate
and a deterministic beta package in a managed temp workspace, runs the acceptance matrix (six
targets, all MANUAL-PENDING, no CI hardware claim) and the native-runtime dry-run plan, then uploads
reports only (package_smoke.json + SHA256SUMS, short retention). It is statically validated and
locally PASS (9 CI tests, 6/6 smoke checks) but no actual GitHub Actions run has occurred.
Full suite: 682 passed; relocation gate clean at the previous check. Real measured native runtime
archives, native candidates, real CI runs, clean-machine/hardware beta acceptance, signing and owner
distribution authorization remain MANUAL-PENDING; no platform support is claimed.

Stage-6 pipeline rehearsal and reproducibility (2026-10-28, round 4)

Two further automatable stage-6 gaps are closed:
- scripts/rehearse_release.py exercises the complete release chain with unmistakably synthetic runtime
  fixtures (no real runtimes): offline fetch/measure -> six-target measured draft (release_ready at
  6/6) -> build_release native candidate with per-target runtime archives -> manifest/hash validation
  -> beta package -> offline provision install/verify for all six targets -> acceptance matrix with a
  temp-only synthetic record. It reports synthetic_rehearsal=true, per-stage PASS/FAIL, an explicit
  NOT-A-RELEASE/no-platform-support statement, leaves canonical installer manifests byte-identical
  and always cleans its temp workspace.
- scripts/ci/reproducibility_check.py builds the source release twice and verifies archive sha256/
  size/member equality plus byte-identical release/platform/runtime manifests and forbidden-content
  exclusions (40/40 checks locally); a new blocking CI job runs it on ubuntu-latest, windows-latest
  and macos-14 with reports-only artifacts.

Round-4 verification: full suite 693 passed; relocation gate 34/0; supervisor gate ok; SBOM OK;
local synthetic rehearsal PASS (8/8 stages); reproducibility PASS 40/40; package smoke PASS;
root remains clean with no legacy output directories. Real six-target runtime archives and hashes,
actual GitHub Actions execution on real runners, clean-machine and hardware beta acceptance, real
tester records, signing/notarization and owner distribution authorization remain MANUAL-PENDING.
No platform or release support is claimed.

GUI safety controls and genuine Linux execution evidence (2026-10-28, round 5)

- Settings > Advanced is now the only autonomy control surface (mode Off/Assisted/Automatic,
  limits, read-only plan/history, Save/Apply, Pause, confirmed Stop) with no autostart and no GUI
  Start; the main window status bar has an always-reachable EmergencyControls Pause/Stop outside
  settings for active supervisor runs, using the cooperative durable command path (safe boundaries,
  never process kills). 20 new offscreen tests cover the controls and idle/active/error states.
- Genuine Linux x86_64 execution evidence was captured through the existing WSL2 Ubuntu distro
  (source-level, no PySide6/crewai/native runtimes/network): shell syntax and POSIX launcher
  execution/fail-closed checks, reproducibility, package smoke, synthetic rehearsal, acceptance
  matrix, fetch/beta plans. It found and fixed a real bad-substitution bug in
  scripts/launchers/Self-Build Mode.sh; generated release/platform/runtime manifests and the beta
  package are now byte-identical Windows vs Linux (source archive byte-identical).
- The user-supplied universal-autonomy/research Mega Suite addendum is preserved under
  docs/product-blueprint/addenda/ as queue-only input with a manifest; its requirements are to be
  deduplicated into the indexed backlog without interrupting current work.

Round-5 verification: full suite 722 passed; relocation gate 33/0/1 expected dirty-tree warning;
supervisor gate ok; SBOM OK; Linux evidence runs all exit 0. WSL2 is not GitHub Actions; no
GUI/native-runtime/clean-machine/hardware/platform support is claimed. External/manual acceptance
items and owner authorizations remain pending.

Stage-7 first implementation increments (2026-10-28)

Two foundation increments from the queued Universal Autonomy/Research addendum are implemented,
tested and committed, without claiming the broader capabilities complete:
- Autonomy A1 (NL-BP-168): a 20-capability taxonomy with risk classes and fail-closed defaults, 12
  permission scopes, six decision semantics, durable SQLite capability grants/approvals with expiry,
  revocation, restart survival, audit events and a single check_capability API; legacy permissions and
  cloud/network gates are unchanged. Not yet wired into GUI or tool execution; Trusted Auto Review and
  Full Autonomy profiles remain planned (NL-BP-166/167).
- Research R1 (NL-BP-170/175/206 foundation): stdlib-only research package with immutable provenance,
  fail-closed RetrievalPolicy (HTTPS default, domain allow/deny, SSRF/private-IP blocking, redirects,
  time/size/content-type caps, deterministic rate limiting), an injectable-transport fetcher that
  re-checks policy on every redirect, tags content untrusted and records redirect provenance, and an
  HTML reader producing text/Markdown with metadata/headings/lists/code/links/tables while dropping
  script/iframe content. No default network transport, no search providers, browser, PDF/Office
  extraction, cache/store or GUI yet; real-network acceptance remains MANUAL-PENDING (NL-BP-203/211).

Verification: full suite 814 passed; relocation/supervisor gates green; no network/model/GUI runs.

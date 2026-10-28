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
- **Roadmap**: `nl_coding_agent.core.roadmap` parses `docs/NEXT_SELF_BUILD_MISSION.md`; `selfbuild --from-roadmap` creates and runs the next mission without per-project YAML.
- **Self-Build Mode**: `selfbuild --autonomous` / `--loop` resumes durable work, then runs the next roadmap mission in a bounded loop (`--max-missions` 1-5, default 1). State is `data/selfbuild_state.json`; lock is `data/selfbuild.lock`; log is `logs/selfbuild.log`.
- **Autonomous completion guard**: a completed roadmap fingerprint is not rerun; the runner reports the completed mission and asks for a new `docs/NEXT_SELF_BUILD_MISSION.md`.
- **Handoff verification**: `scripts/verify_handoff_and_resume.py` checks launcher wiring, CLI flags, SQLite handoffs, autonomous state, recovery evidence, lock hygiene, and the full test suite. `scripts/run_tracked_selfbuild_test.py` launches one real tracked cycle through the autonomous CLI.

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
- Dedicated launcher: `Self-Build Mode.bat` (embedded Python, default reviewer `ollama/qwen3.5:9b`).

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
    `payload_manifest.json`, 1.44 GiB, no `crewAI/`, `data/`, `logs/`, `tests/`, `docs/`,
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
- GUI smoke test: offscreen `MainWindow` constructs with six stack pages, opens the project, previews `nl_coding_agent/core/version.py`, shows mission #16, and closes cleanly (exit 0).
- Models page smoke test: Ollama reachable, 18 models listed, 0 loaded at check time; GUI teardown no longer crashes after waiting for the model-fetch thread.

## Roadmap

- Completed: Task Board & File Viewer integration, Agents & Settings panels, Self-Build Mode
  Regression Test, Distribution Audit and Size-Reduction Plan, Native CrewAI Runtime Integration,
  Portable Payload Staging, Portable User-Data Override, Self-Build Resume Command Accuracy
  (`docs/COMPLETED_MISSIONS.md`).
- Handoff gate: verified. The autonomous engine, durable resume, launcher, SQLite evidence,
  duplicate-work guard, and exact blocked-resume command have all been exercised.
- Next: define and run the next small self-build mission. Packaging, installer, licensing, and
  final clean-directory acceptance remain future work and must not start until the handoff is
  accepted.
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


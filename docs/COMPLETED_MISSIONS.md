# Completed Missions — NL Coding Agent

> **Relocation note (2026-10-28):** this repository was renamed from `K:\AI\Coding Agent` to
> `K:\AI\NL Coding Agent`. Any pre-rename path quoted in the mission records below is historical
> evidence preserved verbatim; the current canonical root is `K:\AI\NL Coding Agent`.

This file records self-build missions that have been implemented and verified. The active
roadmap lives in `docs/NEXT_SELF_BUILD_MISSION.md`.

## Self-Build Resume Command Accuracy

**Status:** completed and approved by the reviewer gate (mission #40).

**Delivered:**
- `nl_coding_agent/core/selfbuild_runner.py`: blocked autonomous results now return an exact
  `--resume <mission_id>` command; completed and idle results keep the base command.
- `tests/test_selfbuild_runner.py`: coverage for blocked, completed, idle, and explicit-resume
  command construction.

**Verification:**
- Mission #40 persisted result: `status=completed`, `review_verdict=APPROVE`,
  `diff_stat=2 file(s), +34/-1`, `changed_paths=["nl_coding_agent/core/selfbuild_runner.py",
  "tests/test_selfbuild_runner.py"]`.
- `python\python.exe -m pytest tests\test_selfbuild_runner.py` - 8 passed.
- `python\python.exe -m pytest` - 65 passed.
- `python\python.exe scripts\verify_handoff_and_resume.py` - all handoff, state, recovery,
  lock-hygiene, and full-suite checks passed.
- The first autonomous developer attempt replaced the runner with a stub and failed verification.
  The original file was restored from `data/mission_baselines/40.json`; the change was implemented
  manually and the mission was resumed through the tester and reviewer stages.
- Known follow-up: the autonomous `--stop-after` flag is not yet forwarded to
  `run_autonomous`, and state reconciliation after a resumed mission occurs on the next idle run.

## Portable User-Data Override

**Status:** completed and approved by the reviewer gate (mission #39).

**Delivered:**
- `nl_coding_agent/persistence/database.py`: `NL_DATA_DIR` override for the SQLite database;
  `db_path()` follows the override while preserving `_DB_PATH` compatibility for existing tests;
  `selfbuild_state.json` follows the database parent.
- `tests/test_user_data_path.py`: default path, override with directory creation, and self-build
  state placement.
- `docs/PORTABLE_BUILD.md`: user-data override instructions and remaining launcher/migration
  work.

**Verification:**
- Mission #39 persisted result: `status=completed`, `review_verdict=APPROVE`,
  `diff_stat=3 file(s), +73/-4`, `changed_paths=["docs/PORTABLE_BUILD.md",
  "nl_coding_agent/persistence/database.py", "tests/test_user_data_path.py"]`.
- `python\python.exe -m pytest tests\test_user_data_path.py` - 3 passed.
- `python\python.exe -m pytest` - 52 passed.
- The mission was implemented manually and resumed through the tester and reviewer stages.

## Portable Payload Staging

**Status:** completed and approved by the reviewer gate (mission #38).

**Delivered:**
- `scripts/stage_portable.py`: read-only source staging with `--source`, `--output`,
  `--dry-run`, and `--json`; includes the application, embedded runtime, assets, config, and
  launchers; excludes vendor checkouts, user data, logs, tests, docs, scripts, `.git`, caches,
  bytecode, and machine-local `config/voicebridge.yaml`; refuses output inside the source tree or
  a non-empty destination; skips symlinks.
- `tests/test_stage_portable.py`: temporary-tree coverage for exclusions, manifest generation,
  dry-run behavior, non-empty output refusal, and source-relative output refusal.
- `docs/PORTABLE_BUILD.md`: measured staging plan, included/excluded roots, manifest fields,
  safety boundaries, and next validation steps.

**Verification:**
- Mission #38 persisted result: `status=completed`, `review_verdict=APPROVE`,
  `diff_stat=3 file(s), +414/-0`, `changed_paths=["docs/PORTABLE_BUILD.md",
  "scripts/stage_portable.py", "tests/test_stage_portable.py"]`.
- `python\python.exe -m pytest tests\test_stage_portable.py` - 4 passed.
- `python\python.exe -m pytest` - 49 passed.
- Dry-run plan: 23,711 files, 1,547,268,760 bytes (1.44 GiB); runtime `python/` accounts for
  23,656 files and 1.44 GiB.
- Post-mission hardening excludes `config/voicebridge.yaml` so a private project path cannot
  enter the payload; `nl_coding_agent/cli.py` now reports a missing project config without a
  traceback; `tests/test_cli_config.py` covers the startup path.
- Real payload validation: `doctor` exited 0 from `K:\AI\nl-coding-agent-portable-final`, the
  offscreen GUI constructed six pages, and a smoke project persisted across process restart.
- The mission was created with a pre-deliverable baseline, implemented manually, and resumed
  through the tester and reviewer stages.

## Native CrewAI Runtime Integration

**Status:** completed and approved by the reviewer gate (mission #37).

**Delivered:**
- `pyproject.toml`: pins `crewai==1.15.32` while preserving the existing project metadata and
  pytest configuration.
- `tests/test_crewai_runtime.py`: proves `crewai` imports from the embedded runtime's
  `site-packages`, not the repository's `crewAI/` checkout, and asserts the pinned version.
- `docs/CREWAI_RUNTIME.md`: records the runtime evidence, vendor-exclusion policy, license
  follow-up, and verification commands.

**Verification:**
- Mission #37 persisted result: `status=completed`, `review_verdict=APPROVE`,
  `diff_stat=3 file(s), +84/-1`, `changed_paths=["docs/CREWAI_RUNTIME.md","pyproject.toml",
  "tests/test_crewai_runtime.py"]`.
- `python\python.exe -m pytest tests\test_crewai_runtime.py` - 1 passed.
- `python\python.exe -m pytest` - 42 passed.
- The autonomous developer initially replaced `pyproject.toml` with a minimal file and broke
  pytest collection; the output was manually corrected before the tester and reviewer stages.

## Distribution Audit and Size-Reduction Plan

**Status:** completed and approved by the reviewer gate (mission #36).

**Delivered:**
- `scripts/audit_distribution.py`: read-only audit with `--root` and `--json`, single-pass tree
  walking, protected-tree separation, generated-cache accounting, duplicate hashing limited to
  files at most 5 MiB, and `pyproject.toml` dependency extraction.
- `tests/test_distribution_audit.py`: temporary-workspace JSON audit test covering duplicate
  detection, `.git` exclusion, dependency parsing, and size totals.
- `docs/DISTRIBUTION_AUDIT.md`: measured report, cleanup classifications, and the safe
  size-reduction plan.

**Verification:**
- Mission #36 persisted result: `status=completed`, `review_verdict=APPROVE`,
  `diff_stat=3 file(s), +550/-0`.
- `python\python.exe -m pytest` - 41 passed.
- Audit evidence: total `2,215,430,573` bytes; protected trees `2,209,811,571` bytes (99.75%);
  duplicate reclaimable space `270` B; runtime `crewai` 1.15.32 imported from
  `python/Lib/site-packages`; `crewAI-tools` absent.
- The mission was implemented manually after the autonomous developer produced placeholders and
  no tests; the developer task was marked completed with a recorded manual handoff before the
  tester and reviewer stages ran.

## Self-Build Mode Regression Test

**Status:** completed and approved by the reviewer gate (mission #30).

**Delivered:**
- `tests/test_selfbuild_mode.py`: verifies the dedicated launcher exists and references
  `nl_agent.py`, `selfbuild`, `--autonomous`, and `--project`; verifies `selfbuild --help` exits 0
  and exposes `--autonomous` and `--max-missions`.
- Post-mission hardening: the test resolves the repository root from
  `Path(__file__).resolve().parents[1]` instead of `os.getcwd()`, so it is independent of the
  pytest working directory.

**Verification:**
- Mission #30 persisted result: `status=completed`, `review_verdict=APPROVE`,
  `diff_stat=1 file(s), +35/-0`, `changed_paths=["tests/test_selfbuild_mode.py"]`.
- `python\python.exe -m pytest` - 40 passed.
- `python\python.exe scripts\verify_handoff_and_resume.py` - all launcher, CLI, SQLite, state,
  recovery, lock-hygiene, and test checks passed.
- `scripts/run_tracked_selfbuild_test.py --max-missions 1` returned `idle` with mission #30
  completed and `APPROVE`, proving the duplicate-work guard.

## Agents & Settings Panels

**Status:** completed and approved by the reviewer gate (mission #24).

**Delivered:**
- `nl_coding_agent/gui/widgets/agents_panel.py`: read-only role/model table with dynamic Ollama
  availability and resource policy.
- `nl_coding_agent/gui/widgets/settings_panel.py`: read-only project/database/Ollama/model-config
  paths and cloud-escalation state.
- `nl_coding_agent/app/services.py`: config and runtime accessors for the panels.
- `nl_coding_agent/gui/main_window.py`: panels wired at stack indices 3 and 4, refresh on page
  selection/project open, safe teardown timer.
- `tests/test_gui_panels.py` and `tests/test_gui_smoke.py`: panel rendering, forbidden-import,
  stack wiring, and offscreen teardown coverage.

**Verification:**
- `python\python.exe -m pytest` - 34 passed.
- Mission #24 persisted result: `status=completed`, `review_verdict=APPROVE`,
  `diff_stat=6 file(s), +420/-15`.
- Reviewer quality issue recorded: the default reviewer model produced false import claims; a
  stronger reviewer model returned `APPROVE` after reviewing the same diff.

## Task Board & File Viewer Integration

**Status:** implemented and verified manually; reviewer gate exercised separately on mission #16.

**Delivered:**
- `nl_coding_agent/gui/widgets/task_board.py`: mission list, grouped task tree, progress,
  handoffs, verification runs, Run/Resume action, roadmap mission creation.
- `nl_coding_agent/gui/widgets/file_viewer.py`: read-only `QFileSystemModel` browser with
  protected-directory filtering and safe preview.
- `nl_coding_agent/gui/main_window.py`: wired Files and Tasks at stack indices 1 and 2.
- `nl_coding_agent/gui/widgets/inspector_panel.py`: selected file content preview and mission
  details.
- `nl_coding_agent/gui/widgets/models_panel.py`: safe shutdown of the model-fetch thread.
- `tests/test_gui_smoke.py`: offscreen construction/teardown regression test.

**Verification:**
- `python\python.exe -m pytest` — 31 passed.
- Offscreen GUI smoke: 6 stack pages, project opened, `nl_coding_agent/core/version.py`
  previewed, mission #16 displayed, process exited 0.
- Models page: Ollama reachable, 18 models listed, clean teardown.

**Reviewer evidence:**
Mission #16 (separate, isolated change) completed the full live cycle:
developer created `nl_coding_agent/core/version.py` and `tests/test_version.py`, the mission was
interrupted after the developer stage, resumed in a new process, tested, and approved by the
reviewer. Persisted result: `APPROVE`, `2 file(s), +8/-0`.


## Mission #41 — Self-Build Recovery Control Accuracy (APPROVE)
- Status: completed / APPROVE; resume_count=2; diff `6 file(s), +284/-0`; changed paths = 4 mission-scoped source/test files.
- Tasks: #93 developer completed (attempt 2, manual takeaway after tool failure); #94 tester completed (1 attempt, exit 0); #95 reviewer completed (1 attempt, verdict APPROVE).
- Key fixes: `stop_after` forwarded through CLI -> `run_autonomous()` -> `orch.run_mission()`; `reconcile_completed_mission()` updates `selfbuild_state.json` immediately on resumed-completion; regression tests added; live `--stop-after developer` produced blocked resume command; external `docs/product-blueprint/` excluded from review baseline (original baseline preserved at `data/mission_baselines/41.mission_start.json`).


# Workspace Relocation — Completed Record

## Status

- **Relocation state:** completed, verified and recorded.
- **Canonical repository root:** `K:\AI\NL Coding Agent`.
- **Folder name before the relocation:** `Coding Agent` (repository under `K:\AI`).
- **Timeline:** the folder rename happened in place between the pre-relocation checkpoint commit
  `84907e9` (2026-10-28 15:18:48) and the first post-rename read-only audit (15:22:21). The
  SQLite/state identity migration was applied at local time `15:23:01` (SQLite event timestamp
  `2026-10-28 14:23:01` UTC); documentation update and independent verification followed.
- **Mode:** in-place folder rename plus SQLite/state identity migration. No copy of the workspace
  was created; the folder rename and data-identity steps modified no source code, test, vendor
  runtime or external sibling project, and no self-build mission ran during the relocation. The
  relocation reconciliation that followed (commits `d471e79` / `c10e769`) did add the
  relocation module, migration/gate scripts and their tests; see "Relocation tooling" below.

This document was previously a *future migration readiness checklist*. It is now the completed
relocation record: decision and authorization, pre-migration audit, actions performed, preserved
historical evidence, rollback procedure and verification evidence.

## Decision and authorization

- The user authorized renaming the repository to the canonical root `K:\AI\NL Coding Agent`.
- The relocation was executed as two coordinated parts:
  1. **Data identity** — SQLite project registry and `data/selfbuild_state.json` (performed by the
     Lead on 2026-10-28).
  2. **Documentation / instruction layer** — operational docs, agent instructions and product
     blueprint path references (this record).
- **Historical policy (superseded):** the earlier readiness checklist required explicit user
  authorization and a full stop of OpenCode, NL Coding Agent, Self-Build Mode, Ollama clients,
  terminals and build/packaging processes before any rename, together with a verified SQLite backup
  and an understood Git worktree. The purpose was to avoid split project identity in SQLite, stale
  state keys, orphan missions and hardcoded paths pointing at a non-existent folder. The
  authorization was given and those preconditions were applied; the checklist below is retained as
  the pre-migration policy record, **not** as a live prohibition.

## Pre-migration readiness checklist (historical — satisfied)

- [x] User explicitly authorized the rename and the target path.
- [x] Self-build/mission processes stopped; no mission `running`; no `mission.lock` or
      `selfbuild.lock` left in `data/`.
- [x] Verified SQLite backup taken before the migration.
- [x] Git worktree understood: pre-existing uncommitted/untracked work preserved; no
      `git clean -fd` or `git reset --hard`.
- [x] Build outputs reviewed: `dist/`, `build/` and `data/` were not moved or duplicated.
- [x] OpenCode configuration/session data not relocated or modified.
- [x] Rename performed in place on the single existing repository; no second copy of the workspace
      was created.

## Pre-migration audit summary

Read-only inventory: `.workspace/build/relocation/audit_paths.json` (generated
`2026-10-28T15:22:21+01:00`, after the folder rename and before the SQLite/state data-identity
migration).

| Metric | Value |
|---|---|
| Files scanned | 230 |
| Files with at least one pre-relocation path match | 70 |
| Total pre-relocation path matches | 527 |
| Matches by form | 518 backslash; 9 JSON-double-escaped |
| Matches by category | 482 historical evidence; 25 instruction; 16 operational doc; 2 config; 1 launcher; 1 code/runtime |

Scanned files by category: config 7, instruction 59, historical evidence 46, launcher 7,
operational doc 25, code/runtime 86. Only two path forms actually occurred (plain backslash and
JSON-double-escaped); no forward-slash, URL-encoded or file-URL occurrence of the pre-relocation
root was found.

The same audit inventoried 129 other absolute-path occurrences (12 other absolute Windows paths,
104 external sibling-project paths under `K:\AI`, 12 already-canonical root paths and 1 user
profile path). Those are external/environment references or already-correct paths and were
deliberately not rewritten.

Scan scope: repository text files, excluding `.git`, vendor checkouts (`crewAI/`,
`crewAI-tools/`), the embedded `python/` runtime, `assets/`, `build/`, `dist/`,
`node_modules`, caches and the multi-MB `data/mission_baselines/`, consistent with the
workspace-containment rules in `AGENTS.md`.

## Actions performed — data identity (2026-10-28 15:23:01)

- **SQLite** `data/nl_coding_agent.sqlite3`:
  - project row **id=1** retained; `root` set to the canonical root; project `name` set to
    `NL Coding Agent` (previous name `Coding Agent`); the 6 `project_facts` rows preserved;
  - **15 missions** owned by project id=1 preserved (`missions_before` = `missions_after` = 15);
    45 mission rows in total; the 30 legacy rows with no project association left unchanged;
    **0 orphan missions**; `PRAGMA integrity_check` = `ok`;
  - no duplicate or new project row was created (`duplicate_project_id` = `null`); a single
    project identity remains;
  - relocation metadata added to the project row: `relocated_from` (historical path string),
    `relocated_at`, `previous_name`;
  - migration event written to `events`: **id 75**, source `migration`, level `info`, message
    "Project registry relocated: <previous root> -> K:\AI\NL Coding Agent (project id 1)". The
    previous-root literal is stored inside that event row as historical metadata only.
- **`data/selfbuild_state.json`**: project key renamed to the canonical root; preserved
  `last_completed_mission_id=43`, the 64-character `last_completed_fingerprint` beginning
  `dc9d7903...`, and `audit_note_42` / `audit_note_43`; `relocated_from` / `relocated_at`
  metadata added.
- **Backups:**
  - `data/backups/relocation-20261028T152301/` — database snapshot taken with the SQLite
    backup API (one consolidated `.sqlite3` file; no `-wal`/`-shm` existed at snapshot time),
    plus `selfbuild_state.json`, `migration_plan.json` and `migration_result.json`. Any
    `-wal`/`-shm` files visible in that folder today were materialised by later read-only
    opens, not by the snapshot;
  - `data/backups/pre-relocation-20261028T151847/` — independent earlier snapshot of the database
    and state file.

## Actions performed — documentation / instruction layer

Updated to the canonical root, or to dynamic/relative wording where a document only needs to
describe a command:

- `AGENTS.md` — workspace root and canonical source repository.
- `README.txt`, `README_FIRST.txt` — install destination and workspace references.
- `START_HERE_ANTIGRAVITY.md`, `PASTE_THIS_IN_ANTIGRAVITY.txt` — bootstrap instructions.
- `.agents/rules/python-runtime.md` — target Python path.
- `docs/02_SELF_BUILD_ROADMAP.md` — Phase 7 self-build example; the stale "do not rename now"
  prohibition is replaced by a completed-relocation section that keeps the historical rationale,
  marked superseded.
- `docs/08_ACCEPTANCE_GATES.md`, `docs/CURRENT_STATE.md` — launcher and next-command paths.
- `docs/PORTABLE_BUILD.md` — staging command now runs from the repository root; `--source`
  defaults to `.`, so no hardcoded root is needed.
- `docs/CREWAI_RUNTIME.md` — quoted pre-relocation output preserved as evidence, with an inline
  note giving the current runtime root.
- `docs/README_AGGIUNTA.md` — install destination path.
- `HANDOFF_DEEPSEEK_HARNESS.md` — "RELOCATION UPDATE (2026-10-28)" note added at the top; the
  historical mission narrative is unchanged.
- `docs/product-blueprint/` — `README_IMPORTANTE.md`, `01_DECISIONI_E_PRIORITA.md`,
  `02_STATO_REALE_DA_VERIFICARE.md`, `04_HANDOFF_MINIMO.md`,
  `06_UNICO_HANDOFF_AUTONOMIA.md`, `NOTE_SULLE_SPECIFICHE_PRECEDENTI.md`,
  `AUDIT_E_MIGRAZIONE_SENZA_RISCHI.md`, `specifiche/01_ARCHITETTURA_E_RUNTIME.md`,
  `specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md`,
  `specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md`,
  `specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md`; `MANIFEST.json` (canonical root, migration
  flags and refreshed SHA-256 entries for the edited blueprint files);
  `tools/audit_external_builds.ps1` (repository root now resolved from `$PSScriptRoot` instead of
  being hardcoded).
- `docs/COMPLETED_MISSIONS.md` — one relocation note added at the top; the mission records were
  not rewritten.

Relocation tooling: the folder rename and the data-identity migration did not edit source
code, tests, vendor runtimes, `PATCH/**`, `config/voicebridge.yaml`, `logs/**`, `.git/**` or
`assets/**`. The reconciliation that followed (commit `d471e79`, plus the CLI fix in
`c10e769`) added or modified the relocation tooling itself:
`nl_coding_agent/core/relocation.py`, `nl_coding_agent/cli.py` (fail-closed self-build guard),
`scripts/migrate_project_root.py`, `scripts/verify_relocation.py`,
`tests/test_project_root_migration.py` and `tests/test_verify_relocation.py`; `data/`
received only the completed data-identity migration and a provenance-metadata repair.

## Historical evidence preserved verbatim

- `logs/**` — all self-build run logs and JSON staging/audit outputs (482 of the 527 audited
  matches are historical evidence).
- `data/**` — including `data/backups/**` snapshots and the `relocated_from` metadata.
- `docs/COMPLETED_MISSIONS.md` mission narrative (only the top relocation note was added).
- `AUDIT_REALE_E_LIMITI.md`.
- `docs/DISTRIBUTION_AUDIT.md`.
- `docs/product-blueprint/V4_CHANGELOG.md`.
- `docs/09_ANTIGRAVITY_EXECUTION_MISSION.md`.
- Quoted past command output inside otherwise-current documents (for example the CrewAI runtime
  import evidence), preserved with an inline note that points to the current root.

## Known remaining historical references

Deliberately kept; none of them is an operational instruction for new work:

- `logs/**` and `data/backups/**` — immutable run history and snapshots.
- `data/selfbuild_state.json` — the `relocated_from` metadata value.
- SQLite — the `events` migration payload (event id 75) and older historical event rows.
- `data/mission_baselines/**` — preserved mission-start snapshots (excluded from the
  pre-migration audit by design).
- `AUDIT_REALE_E_LIMITI.md`, `docs/DISTRIBUTION_AUDIT.md`,
  `docs/product-blueprint/V4_CHANGELOG.md` — dated historical records.
- `HANDOFF_DEEPSEEK_HARNESS.md` — the original handoff context line, superseded by the top
  relocation note.
- `docs/CREWAI_RUNTIME.md` — the observed pre-relocation output block.
- `scripts/migrate_project_root.py` — the `OLD_ROOT` constant required to recognise the previous
  identity during a migration/rollback; `scripts/verify_relocation.py` and
  `tests/test_verify_relocation.py` contain the previous-root constant and expected fixture strings
  required by the relocation gate itself. Code and tests were not edited in this documentation task.
- Outside the documentation scope: `config/voicebridge.yaml` points at the external NL VoiceBridge
  Studio project, and `tests/test_stage_portable.py` contains an unrelated synthetic path inside a
  test fixture; neither concerns the repository root and neither was modified.

## Rollback procedure

Preconditions: stop NL Coding Agent and any Self-Build run; no `mission.lock` or
`selfbuild.lock` in `data/`; do not run while a mission is active.

1. **Restore the data identity** from the migration backup:
   - stop the application, delete any stale `data/nl_coding_agent.sqlite3-wal` and
     `data/nl_coding_agent.sqlite3-shm`, then copy
     `data/backups/relocation-20261028T152301/nl_coding_agent.sqlite3` over
     `data/nl_coding_agent.sqlite3`; do not copy `-wal`/`-shm` from the backup folder;
   - copy `data/backups/relocation-20261028T152301/selfbuild_state.json` over
     `data/selfbuild_state.json`.
   If the migration backup is unavailable, use the independent snapshot in
   `data/backups/pre-relocation-20261028T151847/` instead.
2. **Revert the documentation changes**:
   - if they are still uncommitted: `git checkout -- AGENTS.md README.txt README_FIRST.txt
     START_HERE_ANTIGRAVITY.md PASTE_THIS_IN_ANTIGRAVITY.txt .agents docs
     HANDOFF_DEEPSEEK_HARNESS.md`;
   - if they were committed: `git revert <documentation-migration-commit>` (revert only the
     documentation commit, not the code/test history).
3. **Restore the repository identity**: rename the repository folder back, in place, to its
   previous name and location, so that the restored SQLite root, the `selfbuild_state.json` key
   and the reverted documents agree again. Do not copy the repository: a copy would duplicate
   ~2 GB and orphan the Git worktree rollback.
4. **Verify the rollback**:
   - `python\python.exe scripts\migrate_project_root.py` — dry run must report the old identity
     as still pending (it must not report `ALREADY MIGRATED`);
   - `python\python.exe scripts\verify_relocation.py` — may report the expected failures recorded
     in `.workspace/build/relocation/verify_relocation_pre_migration.json`;
   - `python\python.exe nl_agent.py doctor` must exit 0.
5. Keep `data/backups/` and `.workspace/build/relocation/` after a rollback: they are the audit trail.

## Verification commands and evidence

The gate is read-only: it never starts a mission, never runs Self-Build Mode and never writes to
the database or `data/selfbuild_state.json`.

### Relocation gate

```powershell
python\python.exe scripts\verify_relocation.py --report .workspace\build\relocation\verify_relocation_final_docs.json
```

| Stage | Report | Result |
|---|---|---|
| Before the data-identity migration (after the folder rename) | `.workspace/build/relocation/verify_relocation_pre_migration.json` | 19 passed, **9 failed**, 1 warning |
| After data-identity migration, before the docs update | `.workspace/build/relocation/verify_relocation_post_migration.json` | 27 passed, **1 failed** — only `paths.operational_docs_clean` — 1 warning |
| After the documentation update (final) | `.workspace/build/relocation/verify_relocation_final_docs.json` | 28 passed, **0 failed**, 1 warning; `RESULT: PASSED` — the warning is `git.working_tree` (uncommitted documentation changes, cleared by the checkpoint commit) |

The final gate run also re-verifies: single project row id=1 at the canonical root, 15 owned
missions, 0 orphan missions, `state.canonical_key`, preserved mission id/fingerprint/audit notes,
launchers clean, runtime code free of hardcoded drive literals, no mission locks, read-only dry run
(database/state hashes unchanged) and CLI/GUI importability.

### Migration dry run

```powershell
python\python.exe scripts\migrate_project_root.py --old-root "<previous repository root>"
```

Observed on the migrated workspace: `Status   : ALREADY MIGRATED (no changes required)` and
`Post-migration verification: OK` with project id 1 at `K:\AI\NL Coding Agent`, 15 missions
owned and the state key equal to the canonical root.

On a fully migrated database the plain form exits 0 and reports
`Status   : ALREADY MIGRATED (no changes required)` with `Post-migration verification: OK`;
`--old-root` is only needed to name a specific historical identity explicitly. The previous root
remains recoverable from the SQLite migration event (id 75 payload), from
`data/selfbuild_state.json` (`relocated_from`) and from the project-row metadata
(`relocated_from`, preserved by the registry metadata-merge fix and restorable with
`scripts/migrate_project_root.py --repair-provenance`). `--apply` is only needed to re-run the
migration from a restored backup; it backs up the database and state first and refuses to run
while `data/selfbuild.lock` exists (unless `--force` is passed).

Full plan/apply evidence: `.workspace/build/relocation/migration_plan.json` and
`.workspace/build/relocation/migration_result.json` (`applied: true`, `applied_at: 2026-10-28T15:23:01`,
backup directory, `db_result`, `state_result` and the post-apply verification block).

## Post-relocation verification checklist (completed)

- [x] Relocation gate reports `RESULT: PASSED` with 0 failed checks.
- [x] Migration dry run reports `ALREADY MIGRATED` (plain form, and with the explicit
  `--old-root`, see above).
- [x] SQLite single project identity preserved with 15 owned missions and 0 orphans.
- [x] `selfbuild_state.json` canonical key with preserved mission id, fingerprint and audit notes.
- [x] Operational documentation, instructions and blueprint examples updated.
- [x] Historical evidence preserved verbatim.
- [x] The folder rename and data-identity migration changed no source code, tests, `data/`
  content (outside the completed data migration), `logs/`, vendor runtimes or external sibling
  projects; the relocation tooling added by `d471e79`/`c10e769` is listed above.
## Independent verification and follow-up fixes (2026-10-28)

Read-only independent verification from the new root: `.workspace/build/relocation/verification_report.md`
and `.workspace/build/relocation/verification_report.json`.

- **Verdict:** relocation data identity **VERIFIED** — one project identity (id=1), 45 missions
  (15 owned, 0 orphans), state key/fingerprint/mission-43/audit notes preserved, gate green on two
  consecutive runs, fail-closed refusal of a stale pre-relocation dataset (exit 2, before any model
  call), safe pytest baseline 90 passed, offscreen GUI smoke passed, blueprint MANIFEST 47/47
  SHA-256 entries verified, no historical rows rewritten, no duplicate project identity.
- **Findings and resolution:**
  - **F1 (fixed):** `registry.open_project()` replaced the whole `projects.metadata` column, so the
    next normal project open dropped the migration provenance keys. The registry now merges the
    scan cache into the existing metadata; `scripts/migrate_project_root.py --repair-provenance`
    restores missing provenance from the SQLite migration event (idempotent); the gate now checks
    `sqlite.relocation_provenance`.
  - **F2–F6 (fixed):** this record now distinguishes the folder rename from the 15:23:01 data-identity
    migration, states the real backup provenance (one consolidated SQLite backup file; later
    read-only opens materialised the `-wal`/`-shm` files), gives a safe rollback restore
    procedure (copy the database only, remove stale `-wal`/`-shm`), scopes the "untouched by
    design" claim to the rename/data steps and lists the relocation tooling added afterwards, and
    points at the migration event/state file for the previous root.
- **O6 (addressed):** the new provenance gate check originally accepted the migration event as a
  fallback. It now requires `projects.metadata.relocated_from` on the canonical project row and
  only warns when a legacy database has to fall back to the migration event (id 75). After this
  hardening the gate reports 30 passed, 0 failed, 0 warnings.
- **Remaining historical references:** unchanged and intentional (see "Known remaining historical
  references"); the gate's operational-document scan is clean.

## ROOT REORG Phase B - .workspace consolidation (2026-10-28, shared task-45)

The root reorganization Phase B moved the generated roots under one configurable
workspace directory (same-volume renames; no copies and no deletion of user data):

| Before (repository root) | After | Files | Bytes |
|---|---|---|---|
| `build/` | `.workspace/build/` | 333 | 9,708,087 |
| `dist/` | `.workspace/dist/` | 71,008 | 4,525,591,017 |
| `logs/` | `.workspace/logs/` | 33 | 2,658,024 |
| `state/` (absent) | `.workspace/state/` (created empty) | 0 | 0 |
| `temp/`, `cache/` (absent) | `.workspace/temp/`, `.workspace/cache/` (created empty) | 0 | 0 |

File counts and byte totals matched before/after for every moved directory and the
free-space delta was zero. `python/` (embedded runtime) and `data/` (live SQLite
user data, backups, mission baselines) deliberately stay at the repository root:
their paths are a relocation-acceptance dependency, and the gate now checks them.

The single path policy is `nl_coding_agent/core/workspace.py`
(`workspace_root()`, `workspace_path()`, `build_root()`, `dist_root()`,
`logs_root()`, `temp_root()`, `cache_root()`, `state_root()`): default
`<repository>/.workspace`, override `NL_WORKSPACE_DIR`. `.workspace/` is
git-ignored, excluded from the portable payload (`scripts/stage_portable.py`) and
from the source-release builder (`scripts/build_release.py`), and a regression
test (`tests/test_workspace_paths.py`) fails if a legacy root output directory
reappears.

The earlier sections above remain the dated record of the previous relocation; the
evidence paths they cite are now under `.workspace/build/relocation/`.



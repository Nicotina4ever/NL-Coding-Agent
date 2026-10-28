# Workspace Relocation — Completed Record

## Status

- **Relocation state:** completed, verified and recorded.
- **Canonical repository root:** `K:\AI\NL Coding Agent`.
- **Folder name before the relocation:** `Coding Agent` (repository under `K:\AI`).
- **Relocation performed:** 2026-10-28, local time `15:23:01` (SQLite event timestamp
  `2026-10-28 14:23:01` UTC).
- **Mode:** in-place folder rename plus SQLite/state identity migration. No copy of the workspace
  was created, no source code, test, vendor runtime or external sibling project was modified, and
  no self-build mission ran during the relocation.

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

Read-only inventory: `build/relocation/audit_paths.json` (generated
`2026-10-28T15:22:21+01:00`, before the rename).

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
  - `data/backups/relocation-20261028T152301/` — database (+`-wal`/`-shm`) and
    `selfbuild_state.json` snapshot taken by the migration tool, plus `migration_plan.json` and
    `migration_result.json`;
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

Untouched by design: `nl_coding_agent/**`, `tests/**`, `scripts/**` (except this record's
read-only evidence references), `PATCH/**`, `config/voicebridge.yaml`, `data/**` (except the
already-completed data-identity migration), `logs/**`, `.git/**`, `assets/**`.

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
   - copy `data/backups/relocation-20261028T152301/nl_coding_agent.sqlite3` (and the matching
     `-wal`/`-shm` files when present) over `data/nl_coding_agent.sqlite3`;
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
     in `build/relocation/verify_relocation_pre_migration.json`;
   - `python\python.exe nl_agent.py doctor` must exit 0.
5. Keep `data/backups/` and `build/relocation/` after a rollback: they are the audit trail.

## Verification commands and evidence

The gate is read-only: it never starts a mission, never runs Self-Build Mode and never writes to
the database or `data/selfbuild_state.json`.

### Relocation gate

```powershell
python\python.exe scripts\verify_relocation.py --report build\relocation\verify_relocation_final_docs.json
```

| Stage | Report | Result |
|---|---|---|
| Before relocation (pre-relocation root still live) | `build/relocation/verify_relocation_pre_migration.json` | 19 passed, **9 failed**, 1 warning |
| After data-identity migration, before the docs update | `build/relocation/verify_relocation_post_migration.json` | 27 passed, **1 failed** — only `paths.operational_docs_clean` — 1 warning |
| After the documentation update (final) | `build/relocation/verify_relocation_final_docs.json` | 28 passed, **0 failed**, 1 warning; `RESULT: PASSED` — the warning is `git.working_tree` (uncommitted documentation changes, cleared by the checkpoint commit) |

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

The plain form without `--old-root` exits 1 with `ERROR: No un-migrated project root found in the
database; nothing to relocate.` on a fully migrated database, because the previous root is no
longer inferable from the project registry. Pass `--old-root` explicitly; the previous root value
is recorded in the SQLite migration event and in the `relocated_from` metadata. `--apply` is only
needed to re-run the migration from a restored backup; it backs up the database and state first
and refuses to run while `data/selfbuild.lock` exists (unless `--force` is passed).

Full plan/apply evidence: `build/relocation/migration_plan.json` and
`build/relocation/migration_result.json` (`applied: true`, `applied_at: 2026-10-28T15:23:01`,
backup directory, `db_result`, `state_result` and the post-apply verification block).

## Post-relocation verification checklist (completed)

- [x] Relocation gate reports `RESULT: PASSED` with 0 failed checks.
- [x] Migration dry run reports `ALREADY MIGRATED` (with the explicit `--old-root`, see above).
- [x] SQLite single project identity preserved with 15 owned missions and 0 orphans.
- [x] `selfbuild_state.json` canonical key with preserved mission id, fingerprint and audit notes.
- [x] Operational documentation, instructions and blueprint examples updated.
- [x] Historical evidence preserved verbatim.
- [x] No changes to source code, tests, `data/` content (outside the completed data migration),
  `logs/`, vendor runtimes or external sibling projects.

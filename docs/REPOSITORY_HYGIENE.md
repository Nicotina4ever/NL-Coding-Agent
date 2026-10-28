# Repository Hygiene Audit - Stage 5 (measured, read-only)

**Status:** measured audit + recommendations. No deletion, move, rename, commit, network request, model inference, mission or autonomous run was performed by this task.
**Task:** shared `task-31` (stage 5: repository hygiene audit and safe consolidation report). Owner: runner-integrator.
**Repository:** `K:/AI/NL Coding Agent` at HEAD `69c59198eecba055f61e15e04cd6932682a89f2e` (`master`). The working tree was clean before this task; the audit tool, its tests and this document are the only new files and are uncommitted for Lead review.
**Deliverables:** `scripts/audit_repository_hygiene.py` (read-only audit tool), `tests/test_repository_hygiene.py` (20 tests), machine report `build/phase5/repository_hygiene.json`, rendered report `build/phase5/repository_hygiene.md` (git-ignored generated evidence) and this document.

## Executive summary

- The audit measured **99,991 files / 4,071,534,730 B (3.79 GiB)** in **6.1 s**, without truncation and without following symlinks. `.git` accounts for 303 files / 2.44 MiB; the remaining bytes are dominated by the embedded runtime (1,644.25 MiB), the stale portable release (1,437.83 MiB) and the reference CrewAI checkout (770.39 MiB).
- **Safe, no-information-loss candidates (SAFE): 21 findings / 3,097,633 B**: repository caches (17 dirs, 1,793,300 B), the accidental `%SystemDrive%` tree (993,304 B) and 3 build/ copies of tracked docs plans (311,029 B).
- **Requires explicit authorization (NEEDS-AUTHORIZATION): 15 findings / 14,581,743 B**, dominated by the stale temp git worktree (908 files / 14,481,309 B); the rest are 4 one-off root repair scripts, the applied patch artifact + `PATCH/` copies (5/5 files byte-identical to live), stale build metadata/scratch script and historical root handoff docs.
- **Protected (DO-NOT-TOUCH): 3 findings**: the stale portable release `dist/portable-release` (23,639 files / 1,437.83 MiB, missing the current `flows` package; rebuild only at stage 6 with approval), the vendor `crewAI/.git` metadata (318,009,648 B) and 10 intentional empty `__init__.py` package markers. In addition, `data/`, `logs/`, `python/`, `crewAI/`, `build/` evidence, `docs/evidence/`, external VoiceBridge user data/backups/models and the live SQLite DB are explicitly excluded from any cleanup.
- **Stale absolute paths:** 116 matches in 31 files; 114 are historical/intentional (relocation test fixtures, docs history, build evidence, external project config) and only 2 are operational, both in `build/portable_plan.json` (covered by H-07). The `dist` payload manifest is stale release metadata protected by H-11.
- **Worktrees:** 2 registered; the canonical worktree is active, the second is a stale SH-07 temp worktree outside the repository (H-06).
- **Runtime copies:** 2 embedded Python runtimes with identical markers and 2 `crewai` package copies (embedded + stale release); protected.
- **Validation:** 21 checks - 16 PASS, 5 WARN, 0 FAIL. Warnings: PySide6/psutil/PyYAML unpinned, stale `dist` payload-manifest source, and the external VoiceBridge project root (user data). Launchers, CLI command references, git state, `crewai==1.15.32` pin, `SHA256_MANIFEST` (5/5), blueprint JSON and config all pass.
- **Actions taken: none.** Every recommendation below is a proposal for Lead/user decision; nothing was deleted, moved or committed. See sections "Actions taken" and "Validation plan" at the end.

## Method and classification

Command used for the measured run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python\python.exe scripts\audit_repository_hygiene.py --quiet
```

The audit is deterministic and bounded: soft deadline 120 s, max 500,000 files walked, duplicate hashing limited to files <= 2 MiB (max 5,000 files / 256 MiB total), text scanning <= 2 MiB per file. It reads the filesystem and runs only local read-only git queries (`rev-parse`, `status`, `worktree list`, `ls-files`); it performs no network, model, mission or git-write operation. Snapshot scope: this run was taken with the audit tool and its tests present but this document not yet created; the totals therefore count one fewer file, the working tree shows those two new files as uncommitted, and docs/ grows by this document (~36 KB). All area, duplicate, obsolete and validation findings are unaffected by that difference. The 20 targeted tests in `tests/test_repository_hygiene.py` cover read-only behaviour, determinism, bounds, duplicate groups, obsolete/stale candidates, stale-path classification, injected worktree registrations, launcher/dependency/manifest validation, CLI JSON/markdown output and static no-network/no-destructive guards: `20 passed`.

Classification used for every finding:

| Class | Meaning |
|---|---|
| `SAFE` | Generated/regenerated-only content; removing it loses nothing and needs no user-data or evidence decision. |
| `NEEDS-AUTHORIZATION` | Tracked files, git registrations, release metadata or potentially valuable artifacts; requires a human/Lead decision plus a stated validation run before any change. |
| `DO-NOT-TOUCH` | User data, logs, embedded runtime, vendor checkouts, release/build outputs, acceptance evidence, backups, shared models or external project data. Never a cleanup target. |

## Measured findings (generated report)

### Repository hygiene audit

**Read-only audit of the canonical repository.** Generated: 2026-10-28T17:18:31Z - root: `K:/AI/NL Coding Agent`

The audit never deletes, moves, renames or modifies repository files, never starts a mission/model/network request, and performs no git write operation. It only reads the filesystem and runs local read-only git queries (rev-parse, status, worktree list).

**Actions taken by this run:** none (read-only)

### Summary

| Metric | Count | Size / detail |
|---|---|---|
| Files (all areas) | 99991 | 3.79 GiB |
| Git metadata (.git) | 303 | 2.44 MiB |
| Repository caches | 134 | 1.71 MiB |
| Cache dirs/files (all areas) | 1873 dirs / 13075 | 171.18 MiB |
| Duplicate groups | 15 | 38 files |
| Obsolete/stale candidates | 39 | 21 SAFE / 15 NEEDS-AUTHORIZATION / 3 DO-NOT-TOUCH |
| Stale absolute-path matches | 116 | 31 files, 2 operational |
| Registered git worktrees | 2 | 1 stale |
| Validation checks | 16 PASS | 5 WARN / 0 FAIL |
| Audit elapsed | 6.125 s | truncated=False |

### Areas

| Area | Kind | Class | Files | Size |
|---|---|---|---|---|
| python | runtime | protected | 36596 | 1.61 GiB |
| dist | release-artifact | protected | 23639 | 1.40 GiB |
| crewAI | vendor | protected | 38926 | 770.39 MiB |
| data | user-data | protected | 34 | 16.91 MiB |
| logs | logs | protected | 33 | 2.53 MiB |
| .git | git-metadata | protected | 303 | 2.44 MiB |
| build | build-evidence | evidence | 53 | 2.26 MiB |
| nl_coding_agent | source | source | 154 | 1.75 MiB |
| docs | documentation | source | 88 | 1.67 MiB |
| tests | tests | source | 97 | 1014.85 KiB |
| %SystemDrive% | junk | safe | 5 | 970.02 KiB |
| assets | assets | source | 2 | 576.93 KiB |
| scripts | scripts | source | 16 | 264.83 KiB |
| FOUNDATION_CHANGES.patch | patch-artifact | evidence | 1 | 42.33 KiB |
| PATCH | patch-artifact | evidence | 6 | 29.14 KiB |
| .pytest_cache | cache | safe | 5 | 9.62 KiB |
| AGENTS.md | root-documentation | source | 1 | 7.14 KiB |
| .agents | agent-instructions | source | 9 | 6.84 KiB |
| AUDIT_REALE_E_LIMITI.md | root-documentation | source | 1 | 6.00 KiB |
| HANDOFF_DEEPSEEK_HARNESS.md | root-documentation | source | 1 | 4.28 KiB |
| START_HERE_ANTIGRAVITY.md | root-documentation | source | 1 | 3.76 KiB |
| temp_restore.py | temp-script | review | 1 | 2.76 KiB |
| README_FIRST.txt | root-documentation | source | 1 | 1.93 KiB |
| README.txt | root-documentation | source | 1 | 1.79 KiB |
| config | config | source | 2 | 1.63 KiB |
| PASTE_THIS_IN_ANTIGRAVITY.txt | root-documentation | source | 1 | 1.37 KiB |
| __pycache__ | cache | safe | 1 | 1.05 KiB |
| temp_restore_planner.py | temp-script | review | 1 | 902 B |
| Self-Build Mode.bat | launcher | source | 1 | 738 B |
| nl_agent.py | entrypoint | source | 1 | 690 B |
| temp_fix_planner.py | temp-script | review | 1 | 572 B |
| SHA256_MANIFEST.json | config | source | 1 | 566 B |
| work_voicebridge.bat | launcher | source | 1 | 559 B |
| pyproject.toml | config | source | 1 | 506 B |
| audit_voicebridge.bat | launcher | source | 1 | 436 B |
| temp_fix_title.py | temp-script | review | 1 | 343 B |
| NL Coding Agent.bat | launcher | source | 1 | 229 B |
| doctor.bat | launcher | source | 1 | 163 B |
| status.bat | launcher | source | 1 | 163 B |
| .gitignore | config | source | 1 | 137 B |

### Caches

All cache directories: 1873 dirs, 13075 files, 171.18 MiB. Runtime/vendor/build/docs caches are protected; only repository caches are cleanup candidates.

| Cache directory | Area | Files | Size | Class |
|---|---|---|---|---|
| .pytest_cache | .pytest_cache | 5 | 9.62 KiB | SAFE |
| __pycache__ | __pycache__ | 1 | 1.05 KiB | SAFE |
| crewAI/__pycache__ | crewAI | 1 | 23.98 KiB | DO-NOT-TOUCH |
| nl_coding_agent/__pycache__ | nl_coding_agent | 3 | 78.02 KiB | SAFE |
| nl_coding_agent/agents/__pycache__ | nl_coding_agent | 5 | 125.46 KiB | SAFE |
| nl_coding_agent/app/__pycache__ | nl_coding_agent | 3 | 38.31 KiB | SAFE |
| nl_coding_agent/core/__pycache__ | nl_coding_agent | 20 | 342.20 KiB | SAFE |
| nl_coding_agent/flows/__pycache__ | nl_coding_agent | 7 | 81.23 KiB | SAFE |
| nl_coding_agent/gui/__pycache__ | nl_coding_agent | 5 | 40.85 KiB | SAFE |
| nl_coding_agent/gui/dialogs/__pycache__ | nl_coding_agent | 2 | 4.95 KiB | SAFE |
| nl_coding_agent/gui/widgets/__pycache__ | nl_coding_agent | 11 | 110.49 KiB | SAFE |
| nl_coding_agent/models/__pycache__ | nl_coding_agent | 5 | 50.95 KiB | SAFE |
| nl_coding_agent/persistence/__pycache__ | nl_coding_agent | 4 | 103.97 KiB | SAFE |
| nl_coding_agent/projects/__pycache__ | nl_coding_agent | 3 | 12.63 KiB | SAFE |
| nl_coding_agent/resources/__pycache__ | nl_coding_agent | 2 | 4.85 KiB | SAFE |
| nl_coding_agent/tools/__pycache__ | nl_coding_agent | 6 | 19.56 KiB | SAFE |
| python/Lib/site-packages/PIL/__pycache__ | python | 97 | 1.33 MiB | DO-NOT-TOUCH |
| python/Lib/site-packages/PySide6/QtAsyncio/__pycache__ | python | 4 | 57.13 KiB | DO-NOT-TOUCH |
| python/Lib/site-packages/PySide6/__pycache__ | python | 3 | 8.20 KiB | DO-NOT-TOUCH |
| python/Lib/site-packages/PySide6/scripts/__pycache__ | python | 7 | 87.81 KiB | DO-NOT-TOUCH |

### Duplicate files (size + sha256, bounded)

Hashed files: 457 (8.57 MiB); skipped large: 0 (cap 2.00 MiB per file); truncated=False.

| Size | Class | Paths | Reason |
|---|---|---|---|
| 217.31 KiB | NEEDS-AUTHORIZATION | build/phase3/evidence/sh07-live-20261028T161911Z/evidence.json<br>docs/evidence/sh07/attempt1/evidence.json | acceptance evidence duplicated in build/ and docs/evidence; review retention before removal |
| 200.77 KiB | NEEDS-AUTHORIZATION | build/phase3/evidence/sh07-live-20261028T163128Z/evidence.json<br>docs/evidence/sh07/attempt2/evidence.json | acceptance evidence duplicated in build/ and docs/evidence; review retention before removal |
| 125.69 KiB | NEEDS-AUTHORIZATION | build/phase3/tierb_console2.log<br>docs/evidence/sh07/attempt2/console.log | acceptance evidence duplicated in build/ and docs/evidence; review retention before removal |
| 118.15 KiB | SAFE | build/phase2/IMPLEMENTATION_PLAN.md<br>docs/PHASE2_HARNESS_INTEGRATION_PLAN.md | build/ copy is identical to a tracked docs/ file; the tracked copy is authoritative |
| 115.54 KiB | NEEDS-AUTHORIZATION | build/phase3/tierb_console.log<br>docs/evidence/sh07/attempt1/console.log | acceptance evidence duplicated in build/ and docs/evidence; review retention before removal |
| 92.94 KiB | SAFE | build/phase4/CREWAI_FLOWS_PLAN.md<br>docs/PHASE4_CREWAI_FLOWS_PLAN.md | build/ copy is identical to a tracked docs/ file; the tracked copy is authoritative |
| 92.65 KiB | SAFE | build/phase3/SUPERVISOR_PLAN.md<br>docs/PHASE3_SUPERVISOR_PLAN.md | build/ copy is identical to a tracked docs/ file; the tracked copy is authoritative |
| 9.65 KiB | NEEDS-AUTHORIZATION | PATCH/nl_coding_agent/core/staging_broker.py<br>nl_coding_agent/core/staging_broker.py | applied audited patch copy is identical to the live file |
| 5.64 KiB | NEEDS-AUTHORIZATION | PATCH/nl_coding_agent/core/recovery_store.py<br>nl_coding_agent/core/recovery_store.py | applied audited patch copy is identical to the live file |
| 4.98 KiB | NEEDS-AUTHORIZATION | PATCH/tests/test_staging_broker_adversarial.py<br>tests/test_staging_broker_adversarial.py | applied audited patch copy is identical to the live file |
| 3.32 KiB | NEEDS-AUTHORIZATION | PATCH/nl_coding_agent/core/code_integrity_gate.py<br>nl_coding_agent/core/code_integrity_gate.py | applied audited patch copy is identical to the live file |
| 2.18 KiB | NEEDS-AUTHORIZATION | PATCH/tests/test_rollback_stub.py<br>tests/test_rollback_stub.py | applied audited patch copy is identical to the live file |
| 328 B | NEEDS-AUTHORIZATION | build/phase3/evidence/sh07-live-20261028T161911Z/summary.md<br>docs/evidence/sh07/attempt1/summary.md | acceptance evidence duplicated in build/ and docs/evidence; review retention before removal |
| 327 B | NEEDS-AUTHORIZATION | build/phase3/evidence/sh07-live-20261028T163128Z/summary.md<br>docs/evidence/sh07/attempt2/summary.md | acceptance evidence duplicated in build/ and docs/evidence; review retention before removal |
| 30 B | DO-NOT-TOUCH | nl_coding_agent/app/__init__.py<br>nl_coding_agent/core/__init__.py<br>nl_coding_agent/gui/__init__.py<br>nl_coding_agent/gui/dialogs/__init__.py<br>nl_coding_agent/gui/widgets/__init__.py<br>nl_coding_agent/models/__init__.py<br>nl_coding_agent/persistence/__init__.py<br>nl_coding_agent/projects/__init__.py<br>nl_coding_agent/resources/__init__.py<br>tests/__init__.py | intentional empty package markers, not a cleanup target |

### Obsolete / stale candidates

| Kind | Path | Class | Tracked | Size | Reason |
|---|---|---|---|---|---|
| accidental-path-tree | %SystemDrive% | SAFE | no | 970.02 KiB | accidental literal %SystemDrive% directory containing copied Windows cache files; it is generated junk, not source or user data |
| applied-patch-artifact | FOUNDATION_CHANGES.patch | NEEDS-AUTHORIZATION | yes | 42.33 KiB | patch artifact from the audited safety-foundation integration; the current sources are already the applied result and the manifest records the audited hashes |
| applied-patch-copy-dir | PATCH | NEEDS-AUTHORIZATION | no | 29.14 KiB | copies the audited patch files; 5/5 Python/test files are byte-identical to the live sources |
| duplicate-build-evidence | build/phase2/IMPLEMENTATION_PLAN.md | SAFE | no | 118.15 KiB | byte-identical duplicate of docs/PHASE2_HARNESS_INTEGRATION_PLAN.md; the tracked documentation copy is authoritative |
| duplicate-build-evidence | build/phase3/SUPERVISOR_PLAN.md | SAFE | no | 92.65 KiB | byte-identical duplicate of docs/PHASE3_SUPERVISOR_PLAN.md; the tracked documentation copy is authoritative |
| duplicate-build-evidence | build/phase4/CREWAI_FLOWS_PLAN.md | SAFE | no | 92.94 KiB | byte-identical duplicate of docs/PHASE4_CREWAI_FLOWS_PLAN.md; the tracked documentation copy is authoritative |
| historical-handoff-doc | AUDIT_REALE_E_LIMITI.md | NEEDS-AUTHORIZATION | yes | 6.00 KiB | historical handoff/relocation note at the repository root; retained for history but may confuse operators about the current canonical state |
| historical-handoff-doc | HANDOFF_DEEPSEEK_HARNESS.md | NEEDS-AUTHORIZATION | yes | 4.28 KiB | historical handoff/relocation note at the repository root; retained for history but may confuse operators about the current canonical state |
| historical-handoff-doc | PASTE_THIS_IN_ANTIGRAVITY.txt | NEEDS-AUTHORIZATION | yes | 1.37 KiB | historical handoff/relocation note at the repository root; retained for history but may confuse operators about the current canonical state |
| historical-handoff-doc | README.txt | NEEDS-AUTHORIZATION | yes | 1.79 KiB | historical handoff/relocation note at the repository root; retained for history but may confuse operators about the current canonical state |
| historical-handoff-doc | README_FIRST.txt | NEEDS-AUTHORIZATION | yes | 1.93 KiB | historical handoff/relocation note at the repository root; retained for history but may confuse operators about the current canonical state |
| historical-handoff-doc | START_HERE_ANTIGRAVITY.md | NEEDS-AUTHORIZATION | yes | 3.76 KiB | historical handoff/relocation note at the repository root; retained for history but may confuse operators about the current canonical state |
| intentional-duplicate | nl_coding_agent/app/__init__.py, nl_coding_agent/core/__init__.py, nl_coding_agent/gui/__init__.py, nl_coding_agent/gui/dialogs/__init__.py, nl_coding_agent/gui/widgets/__init__.py, nl_coding_agent/models/__init__.py, nl_coding_agent/persistence/__init__.py, nl_coding_agent/projects/__init__.py, nl_coding_agent/resources/__init__.py, tests/__init__.py | DO-NOT-TOUCH | no | 300 B | intentional empty package markers, not a cleanup target |
| repository-cache | .pytest_cache | SAFE | no | 9.62 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | __pycache__ | SAFE | no | 1.05 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/__pycache__ | SAFE | no | 78.02 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/agents/__pycache__ | SAFE | no | 125.46 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/app/__pycache__ | SAFE | no | 38.31 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/core/__pycache__ | SAFE | no | 342.20 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/flows/__pycache__ | SAFE | no | 81.23 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/gui/__pycache__ | SAFE | no | 40.85 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/gui/dialogs/__pycache__ | SAFE | no | 4.95 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/gui/widgets/__pycache__ | SAFE | no | 110.49 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/models/__pycache__ | SAFE | no | 50.95 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/persistence/__pycache__ | SAFE | no | 103.97 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/projects/__pycache__ | SAFE | no | 12.63 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/resources/__pycache__ | SAFE | no | 4.85 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | nl_coding_agent/tools/__pycache__ | SAFE | no | 19.56 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | scripts/__pycache__ | SAFE | no | 93.41 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| repository-cache | tests/__pycache__ | SAFE | no | 633.74 KiB | generated pytest/bytecode cache inside the repository; regenerated on demand |
| stale-generated-metadata | build/portable_plan.json | NEEDS-AUTHORIZATION | no | 1.64 KiB | generated portable-build plan still records the pre-relocation source/output roots (2 old-root references) |
| stale-git-worktree | C:\Users\Nicola\AppData\Local\Temp\nl-sh07-worktree-20261028T173117 | NEEDS-AUTHORIZATION | no | 13.81 MiB | registered git worktree is stale or outside the repository: registered path is outside the repository (temporary worktree) |
| stale-portable-release | dist/portable-release | DO-NOT-TOUCH | no | 1.40 GiB | existing one-folder release artifact built before the workspace relocation and before stages 2-4; it is stale but must not be deleted without authorization; packaged package is missing: flows |
| stray-build-script | build/audit_payload_db.py | NEEDS-AUTHORIZATION | no | 1.32 KiB | one-off payload database audit script left in build/; it is generated scratch code, not a supported tool |
| temp-repair-script | temp_fix_planner.py | NEEDS-AUTHORIZATION | yes | 572 B | one-off repair script left at the repository root; it mutates repository files or the live SQLite database when executed and is superseded by the committed tree |
| temp-repair-script | temp_fix_title.py | NEEDS-AUTHORIZATION | yes | 343 B | one-off repair script left at the repository root; it mutates repository files or the live SQLite database when executed and is superseded by the committed tree |
| temp-repair-script | temp_restore.py | NEEDS-AUTHORIZATION | yes | 2.76 KiB | one-off repair script left at the repository root; it mutates repository files or the live SQLite database when executed and is superseded by the committed tree |
| temp-repair-script | temp_restore_planner.py | NEEDS-AUTHORIZATION | yes | 902 B | one-off repair script left at the repository root; it mutates repository files or the live SQLite database when executed and is superseded by the committed tree |
| vendor-checkout-metadata | crewAI/.git | DO-NOT-TOUCH | no | 303.28 MiB | the reference-only CrewAI vendor checkout carries its own git metadata (303.28 MiB); it is excluded from payloads but stays protected |

### Stale absolute paths

Scanned files: 261; matches: 116 in 31 files.

Counts by pattern: `{"old_root": 31, "other_k_ai_path": 32, "systemdrive_literal": 10, "user_home_path": 43}`; by classification: `{"DO-NOT-TOUCH": 114, "NEEDS-AUTHORIZATION": 2}`.

Operational matches (action required only after approval):

| Path | Line | Pattern | Class | Value | Context |
|---|---|---|---|---|---|
| build/portable_plan.json | 2 | old_root | NEEDS-AUTHORIZATION | K://AI//Coding Agent | "source": "K://AI//Coding Agent", |
| build/portable_plan.json | 3 | old_root | NEEDS-AUTHORIZATION | K://AI//Coding Agent | "output": "K://AI//Coding Agent//dist//portable-release", |

Historical/intentional references (preserved, not defects): 114 shown; full JSON keeps the first 116 matches.

### Git worktrees

| Path | HEAD | State | Class | Size |
|---|---|---|---|---|
| K:/AI/NL Coding Agent | 69c59198eecb | active | DO-NOT-TOUCH | 0 B |
| C:/Users/Nicola/AppData/Local/Temp/nl-sh07-worktree-20261028T173117 | 2a44460d0aab | registered path is outside the repository (temporary worktree) | NEEDS-AUTHORIZATION | 13.81 MiB |

### Runtime copies

Duplicate Python runtime: True; identical python.exe markers: True

| Kind | Path | Class |
|---|---|---|
| python-runtime | python/python.exe | DO-NOT-TOUCH |
| python-runtime | dist/portable-release/python/python.exe | DO-NOT-TOUCH |
| crewai-package | python/Lib/site-packages/crewai | DO-NOT-TOUCH |
| crewai-package | dist/portable-release/python/Lib/site-packages/crewai | DO-NOT-TOUCH |

### Validations

| Check | Status | Detail |
|---|---|---|
| launcher.audit_voicebridge.bat | PASS | refs=2 missing=[] commands=['audit'] |
| launcher.doctor.bat | PASS | refs=2 missing=[] commands=['doctor'] |
| launcher.NL Coding Agent.bat | PASS | refs=2 missing=[] commands=['gui'] |
| launcher.Self-Build Mode.bat | PASS | refs=2 missing=[] commands=['selfbuild', 'selfbuild'] |
| launcher.status.bat | PASS | refs=2 missing=[] commands=['status'] |
| launcher.work_voicebridge.bat | PASS | refs=2 missing=[] commands=['work'] |
| dependency.PySide6 | WARN | spec=PySide6 installed=6.12.0 (not pinned) |
| dependency.psutil | WARN | spec=psutil installed=7.2.2 (not pinned) |
| dependency.crewai | PASS | spec=crewai==1.15.32 installed=1.15.32 |
| dependency.PyYAML | WARN | spec=PyYAML installed=6.0.3 (not pinned) |
| dependency.python_version | PASS | requires-python=>=3.12 current=3.12 |
| manifest.sha256 | PASS | 5 entries; failures=[] |
| manifest.blueprint_index_json | PASS | docs/product-blueprint/INDEX.json |
| manifest.dist_payload | WARN | source=K:/AI/Coding Agent (pre-relocation root; stale) |
| config.required_paths | PASS | missing=[] |
| config.models_yaml | PASS | roles=['architect', 'developer', 'fallback_cloud', 'reviewer'] |
| config.external_project | WARN | external root configured: K:/AI/NL VoiceBridge Studio (exists, user data - never touched by audits) |
| git.repository | PASS | toplevel=K:/AI/NL Coding Agent |
| git.branch | PASS | master |
| git.head | PASS | 69c59198eecba055f61e15e04cd6932682a89f2e |
| git.working_tree | PASS | 2 uncommitted path(s) |

### Recommendations

### SAFE - H-01: Remove generated repository caches

- **Paths:** `.pytest_cache`, `__pycache__`, `nl_coding_agent/__pycache__`, `nl_coding_agent/agents/__pycache__`, `nl_coding_agent/app/__pycache__`, `nl_coding_agent/core/__pycache__`, `nl_coding_agent/flows/__pycache__`, `nl_coding_agent/gui/__pycache__`, `nl_coding_agent/gui/dialogs/__pycache__`, `nl_coding_agent/gui/widgets/__pycache__`, `nl_coding_agent/models/__pycache__`, `nl_coding_agent/persistence/__pycache__`, `nl_coding_agent/projects/__pycache__`, `nl_coding_agent/resources/__pycache__`, `nl_coding_agent/tools/__pycache__`, `scripts/__pycache__`, `tests/__pycache__`
- **Action:** delete the listed __pycache__/.pytest_cache directories
- **Rationale:** generated bytecode/pytest caches are reproducible and not source or user data; no user data, runtime, vendor, dist/build or evidence is affected
- **Validation:** no validation required; Python/pytest regenerate them on demand
- **Size affected:** 1.71 MiB

### SAFE - H-02: Remove accidental %SystemDrive% cache tree

- **Paths:** `%SystemDrive%`
- **Action:** delete the literal %SystemDrive% directory after confirming no process holds the files
- **Rationale:** accidental Windows cache copies created by an unexpanded variable; not source, user data or evidence; no user data, runtime, vendor, dist/build or evidence is affected
- **Validation:** verify the directory is gone; no imports/launchers reference it
- **Size affected:** 970.02 KiB

### SAFE - H-03: Remove build/ copies identical to tracked docs/ plans

- **Paths:** `build/phase2/IMPLEMENTATION_PLAN.md`, `build/phase3/SUPERVISOR_PLAN.md`, `build/phase4/CREWAI_FLOWS_PLAN.md`
- **Action:** delete the build/ duplicates; keep the tracked docs/ copy
- **Rationale:** byte-identical duplicates; build/ is disposable generated output; no user data, runtime, vendor, dist/build or evidence is affected
- **Validation:** hash equality is re-checked by the audit; docs/ copy remains authoritative
- **Size affected:** 303.74 KiB

### NEEDS-AUTHORIZATION - H-04: Archive and remove one-off root repair scripts

- **Paths:** `temp_fix_planner.py`, `temp_fix_title.py`, `temp_restore.py`, `temp_restore_planner.py`
- **Action:** archive copies under build/phase5/archive/ if the Lead wants history, then delete and commit
- **Rationale:** scripts mutate repository files or the live SQLite database and are superseded by the committed tree
- **Validation:** targeted pytest + full offscreen suite; git diff shows no code change
- **Size affected:** 4.53 KiB

### NEEDS-AUTHORIZATION - H-05: Archive and remove applied patch artifacts

- **Paths:** `FOUNDATION_CHANGES.patch`, `PATCH`
- **Action:** copy PATCH README/re-audit into build evidence, then remove FOUNDATION_CHANGES.patch and PATCH/ after approval
- **Rationale:** the audited patch is already applied; SHA256_MANIFEST retains the audited hashes
- **Validation:** verify SHA256_MANIFEST still matches live files; targeted staging/recovery tests + full suite
- **Size affected:** 71.46 KiB

### NEEDS-AUTHORIZATION - H-06: Remove stale registered git worktree

- **Paths:** `C:/Users/Nicola/AppData/Local/Temp/nl-sh07-worktree-20261028T173117`
- **Action:** after confirming no process uses it: git worktree remove --force <path>, then git worktree prune
- **Rationale:** temporary SH-07 worktree left registered after evidence collection; not part of the active repository
- **Validation:** git worktree list shows only the canonical worktree; git status/branch/HEAD unchanged
- **Size affected:** 13.81 MiB

### NEEDS-AUTHORIZATION - H-07: Clean or regenerate stale build metadata

- **Paths:** `build/portable_plan.json`, `build/audit_payload_db.py`
- **Action:** regenerate build/portable_plan.json at stage 6 and archive/remove build/audit_payload_db.py after approval
- **Rationale:** generated metadata still references the pre-relocation root or is scratch code
- **Validation:** regenerated metadata contains the canonical root; no launcher/import references these files
- **Size affected:** 2.96 KiB

### NEEDS-AUTHORIZATION - H-14: Review historical root handoff documents

- **Paths:** `AUDIT_REALE_E_LIMITI.md`, `HANDOFF_DEEPSEEK_HARNESS.md`, `PASTE_THIS_IN_ANTIGRAVITY.txt`, `README.txt`, `README_FIRST.txt`, `START_HERE_ANTIGRAVITY.md`
- **Action:** review with the Lead; archive under docs/history/ only with approval
- **Rationale:** historical handoff notes are not runtime requirements but may be useful migration context
- **Validation:** documentation links/README references checked after any move
- **Size affected:** 0 B

### DO-NOT-TOUCH - H-09: Preserve user data, logs and the live SQLite database

- **Paths:** `data/`, `logs/`
- **Action:** no cleanup; use the retention tooling with explicit human confirmation if ever needed
- **Rationale:** user data, mission history and diagnostics are not cache and must never be deleted by a hygiene pass
- **Validation:** sqlite integrity/backups unchanged; not applicable
- **Size affected:** 0 B

### DO-NOT-TOUCH - H-10: Preserve embedded Python runtime and CrewAI vendor checkout

- **Paths:** `python/`, `crewAI/`, `crewAI-tools/`
- **Action:** no cleanup; vendor checkout policy requires explicit user approval for any change
- **Rationale:** runtime and reference checkout are protected; deleting them breaks the application and violates workspace rules
- **Validation:** python/python.exe --version; import crewai; scripts/verify_relocation.py
- **Size affected:** 0 B

### DO-NOT-TOUCH - H-11: Do not delete the existing release artifact

- **Paths:** `dist/portable-release`
- **Action:** keep dist/portable-release until stage 6 rebuilds one verified portable payload with explicit authorization
- **Rationale:** release outputs and acceptance evidence are protected; the current artifact is stale but cannot be removed without approval
- **Validation:** stage 6 rebuild + scripts/verify_relocation.py + launcher/import smoke + full suite
- **Size affected:** 0 B

### DO-NOT-TOUCH - H-12: Preserve build/ and docs/ evidence

- **Paths:** `build/`, `docs/evidence/`
- **Action:** no cleanup; build/ and docs/evidence hold stage acceptance and audit evidence
- **Rationale:** evidence must not be deleted or moved without explicit authorization
- **Validation:** not applicable
- **Size affected:** 0 B

### DO-NOT-TOUCH - H-13: Preserve external project/user data paths

- **Paths:** `config/voicebridge.yaml`
- **Action:** no cleanup; external project directories, backups and shared model caches are outside this repository's ownership
- **Rationale:** the external VoiceBridge project (including archives) is user data and never touched by repository hygiene
- **Validation:** not applicable
- **Size affected:** 0 B

### Validation plan for approved changes

Apply one recommendation class at a time and re-run the audit after each step. Before any change:

1. `git status --porcelain` and `git rev-parse HEAD` are recorded; no mission/autonomous run is active.
2. Back up the SQLite database and `data/selfbuild_state.json` if any DB-adjacent step is approved.
3. After each approved cleanup: `python scripts/audit_repository_hygiene.py` shows the expected delta and no new operational findings.
4. Launchers: start `NL Coding Agent.bat`, `doctor.bat`, `status.bat` (or the equivalent `python nl_agent.py <command>` forms).
5. Imports: `python -c "import nl_coding_agent.cli, nl_coding_agent.app.services, nl_coding_agent.agents.orchestrator"`.
6. Doctor and relocation gates: `python nl_agent.py doctor`; `python scripts/verify_relocation.py --json`.
7. Targeted tests for touched areas, then the full offscreen suite: `python -m pytest -q tests -p no:cacheprovider` with `PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen`.
8. Report the git diff and evidence; the Lead reviews and commits. No deletion of `data/`, `python/`, `crewAI/`, `dist/`, `build/` evidence, backups or model caches is authorized by this plan.

### Bounds and limitations

- Bounded runtime/hashing: max_seconds=120.0, max_files=500000, max_hash_bytes=2097152, max_hash_files=5000, max_hash_total_bytes=268435456.
- Duplicate hashing excludes runtime/vendor/dist/data/logs areas and files above the per-file cap; large runtime copies are reported structurally instead.
- No network access, no model inference, no mission or supervisor run, no git write operation.
- Areas classified protected/evidence are measured but never proposed for deletion; DO-NOT-TOUCH recommendations are informational.
- The audit is evidence for a human decision: it does not itself approve or perform cleanup.

## Actions taken by this task

**No destructive action was performed.** No file/directory was deleted, moved or renamed; no git commit, index write or worktree change occurred; no build/dist/vendor/data/runtime/model/backup content was touched; no network, model, mission, supervisor or autonomous run was started; the live SQLite database was not opened by the audit tool (areas are measured by file stats only).

Files created by this task (uncommitted, for Lead review/commit):

| File | Purpose |
|---|---|
| `scripts/audit_repository_hygiene.py` | read-only audit tool (JSON + markdown reports) |
| `tests/test_repository_hygiene.py` | 20 targeted tests with temp fixtures |
| `docs/REPOSITORY_HYGIENE.md` | this measured report |
| `build/phase5/repository_hygiene.json` / `.md` | generated evidence (git-ignored `build/`) |

## Validation plan for approved changes

Apply one recommendation class at a time: H-01/H-02/H-03 (SAFE) first, then the authorized items H-04/H-05/H-06/H-07/H-14, re-running the audit after each batch. Before any change: record `git status --porcelain` and `git rev-parse HEAD`; confirm no mission/supervisor is running; back up the SQLite database and `data/selfbuild_state.json` if a DB-adjacent step is approved (none of H-01..H-07 touches the DB, but the temp repair scripts could if accidentally executed).

1. Re-run `python\python.exe scripts\audit_repository_hygiene.py --quiet` and confirm the expected delta with no new operational finding.
2. Launchers: `NL Coding Agent.bat`, `doctor.bat`, `status.bat` start correctly (or `python\python.exe nl_agent.py gui|doctor|status`).
3. Imports: `python\python.exe -c "import nl_coding_agent.cli, nl_coding_agent.app.services, nl_coding_agent.agents.orchestrator, nl_coding_agent.core.supervisor"`.
4. Gates: `python\python.exe nl_agent.py doctor`; `python\python.exe scripts\verify_relocation.py --json`; `python\python.exe scripts\verify_supervisor.py`.
5. Targeted tests for the touched area, then the full offscreen suite: `python\python.exe -m pytest -q tests -p no:cacheprovider` with `PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen` (Lead-reported baseline at this HEAD: 397 tests green; not re-run by this read-only task).
6. Report the git diff/evidence; Lead reviews and commits. The audit never performs these changes itself.
7. H-06: confirm no process holds the temp worktree, `git worktree remove --force <path>`, `git worktree prune`, then re-check `git worktree list` and `git status`.
8. H-05: after archiving, re-run the audit; `SHA256_MANIFEST` targets are live files and must still match.

## Limitations

- Duplicate hashing excludes runtime/vendor/dist/data/logs areas and files above 2 MiB; large binary copies are reported structurally (runtime markers) instead of content-hashed.
- Stale-path detection is text-only, bounded to 2 MiB per file and to repository-owned text; binary payloads are not decoded.
- The audit does not open SQLite, execute models/network or validate runtime behaviour; H-09..H-13 are policy decisions, not technical findings.
- Counts are a Windows-specific snapshot at the stated HEAD/timestamp and change with commits, test runs (caches) or new evidence.
- The audit reports expected `git working tree` dirtiness while this task's files are uncommitted; a fresh audit after the Lead commit should show 0 uncommitted paths.
- The full test suite was not run here (targeted tests only); the 397-test baseline is Lead-reported.

# Repository Hygiene Follow-up — Structural Consolidation (stage 5)

**Status:** structural hygiene pass performed (documentation consolidation only; nothing deleted, no
commit, no autonomous/model/network run).
**Task:** shared `task-34` (stage-5 follow-up queued by the user; owner: docs-migrator).
**Date:** 2026-10-28. **Repository:** canonical repository checkout, branch `master`.
**Baseline for the audit measurements:** HEAD `bf2a616` at the start of the pass. Concurrent
stage-4/6 tasks committed during the pass (HEAD advanced `bf2a616` -> `4787c30` -> `8040022` ->
`771ecd1`; see [Concurrent-activity caveats](#concurrent-activity-caveats)) — no commit was made by
this task.
**Read this with:** `docs/REPOSITORY_HYGIENE.md` (the stage-5 read-only audit and its authorized
safe cleanups), `docs/REPOSITORY_STRUCTURE.md` (resulting ownership policy) and
`docs/history/legacy/INDEX.md` (map of everything moved).

## Executive summary

- The repository root was consolidated to **one authoritative user entry point** (`README.md`) plus
  the binding agent rules (`AGENTS.md`); 6 dated bootstrap/handoff documents and the audited patch
  evidence were moved (never deleted) into `docs/history/legacy/` with a mapping index.
- Root inventory: **38 -> 31 top-level items** (22 -> 16 files, 16 -> 15 directories). Pre-existing
  root content moved into history: **92,759 B**; new navigation/index documentation added:
  **4,374 B** (legacy index) + README; **0 B deleted**.
- `.gitignore` now covers the generated/cache/coverage/scratch/editor categories that actually
  reappear in this workspace; no package-structure change.
- `docs/REPOSITORY_STRUCTURE.md` now records directory ownership, retention/cleanup policy, backup
  rule and the development-only exclusion list for the stage-6 portable payload.
- `crewAI/` audited read-only: **770.39 MiB** reference checkout that is **not imported** (the
  installed `crewai==1.15.32` package is used). Protected; **not removed**; an optional archival
  proposal is listed for explicit user authorization.
- All requested read-only gates pass: relocation gate **29 PASS / 0 FAIL / 1 warning**, supervisor
  gate **PASS**, CrewAI SBOM **OK**, `doctor` **OK**, targeted structure/relocation tests
  **24 passed**, mission persistence and SHA-256 manifest intact. The full suite is intentionally
  left to the Lead.

## Measured before / after

### Repository-wide read-only audit snapshots

Both snapshots were produced by the existing read-only tool
`scripts/audit_repository_hygiene.py` (16 validation checks, no network/model/mission, no git write):

| Metric | BEFORE (`build/phase5b/hygiene_before.json`) | AFTER (`build/phase5b/hygiene_after.json`) |
|---|---|---|
| Files / size (all areas) | 99,935 / 4,069,968,404 B (3.79 GiB) | 100,236 / 4,078,391,438 B (3.80 GiB) |
| Git-tracked files | 321 / 2,860,846 B | 343 / 2,905,832 B |
| Duplicate groups | 12 (32 files) | 236 (505 files) — increase from concurrent stage-6 build artifacts |
| Obsolete/stale candidates | 28 | 24 — 8 legacy/patch findings resolved, 4 concurrent package-marker groups added |
| Stale absolute-path matches | 126, all `DO-NOT-TOUCH` (0 operational) | 137, all `DO-NOT-TOUCH` (0 operational) |
| Validation checks | 16 PASS / 5 WARN / 0 FAIL | 16 PASS / 5 WARN / 0 FAIL |
| Stale worktrees | 0 | 0 |

The 5 warnings are unchanged pre-existing conditions: PySide6/psutil/PyYAML are not version-pinned,
the protected stale `dist/portable-release` payload manifest still names the pre-relocation source
root, and `config/voicebridge.yaml` points at the external NL VoiceBridge Studio project (user
data). None is caused by this pass.

The 8 resolved obsolete findings are exactly the moved items: 6 `historical-handoff-doc` entries,
`applied-patch-artifact` (`FOUNDATION_CHANGES.patch`) and `applied-patch-copy-dir` (`PATCH/`).
The duplicate/stale-path and file-count increases are **not** attributable to this pass; they come
from the concurrently running stage-6 reproducible-build work writing under `build/` (and 3 files
under `dist/`) during the measurement window. See the caveats section.

### Root inventory — every top-level item before the pass

Measured at the start of the pass; "Action" describes what this task did. Items marked *kept* were
not modified by this pass (their owners/other tasks may still change them).

| Root item | Class | Git | Before (files / bytes) | Action / reference evidence | After |
|---|---|---|---|---|---|
| `.agents/` | agent instructions | tracked | 9 / 7,008 | kept; one agent prompt updated to point at `README.md` | kept |
| `.git/` | git metadata | ignored | 321 / 2,860,846 | kept, untouched | kept |
| `.gitignore` | config | tracked | 1 / 137 | updated with generated/cache categories | 779 B |
| `AGENTS.md` | governance | tracked | 1 / 7,312 | updated: docs entry points, root README rule, vendor crewAI status | 8,198 B |
| `AUDIT_REALE_E_LIMITI.md` | historical handoff doc | tracked | 1 / 6,142 | **git mv** -> `docs/history/legacy/` | moved |
| `FOUNDATION_CHANGES.patch` | applied patch evidence | tracked | 1 / 43,343 | **git mv** -> `docs/history/legacy/patch-evidence/` | moved |
| `HANDOFF_DEEPSEEK_HARNESS.md` | historical handoff doc | tracked | 1 / 4,379 | **git mv** -> `docs/history/legacy/` | moved |
| `NL Coding Agent.bat` | launcher | tracked | 1 / 229 | kept (live GUI entry point) | kept |
| `PATCH/` | applied patch evidence | tracked | 6 / 29,835 | **git mv** -> `docs/history/legacy/patch-evidence/PATCH/` | moved |
| `PASTE_THIS_IN_ANTIGRAVITY.txt` | historical handoff doc | tracked | 1 / 1,402 | **git mv** -> `docs/history/legacy/` | moved |
| `README.txt` | historical bootstrap readme | tracked | 1 / 1,836 | **git mv** -> `docs/history/legacy/` (replaced by root `README.md`) | moved |
| `README_FIRST.txt` | historical bootstrap readme | tracked | 1 / 1,974 | **git mv** -> `docs/history/legacy/` | moved |
| `SHA256_MANIFEST.json` | integrity metadata | tracked | 1 / 566 | kept (live certification of 5 audited files; 5/5 verified) | kept |
| `START_HERE_ANTIGRAVITY.md` | historical handoff doc | tracked | 1 / 3,848 | **git mv** -> `docs/history/legacy/` | moved |
| `Self-Build Mode.bat` | launcher | tracked | 1 / 738 | kept (live self-build entry point) | kept |
| `audit_voicebridge.bat` | launcher | tracked | 1 / 436 | kept (live external-project audit entry point) | kept |
| `doctor.bat` | launcher | tracked | 1 / 163 | kept (live diagnostics entry point) | kept |
| `nl_agent.py` | entry point | tracked | 1 / 690 | kept | kept |
| `pyproject.toml` | config | tracked | 1 / 506 | kept | kept |
| `status.bat` | launcher | tracked | 1 / 163 | kept | kept |
| `temp_fix_planner.py` | one-off repair script | tracked | 1 / 572 | **kept — proposal P-01** (mutates source) | kept |
| `temp_fix_title.py` | one-off repair script | tracked | 1 / 343 | **kept — proposal P-01** (mutates live SQLite) | kept |
| `temp_restore.py` | one-off repair script | tracked | 1 / 2,825 | **kept — proposal P-01** (restores source/docs from baseline) | kept |
| `temp_restore_planner.py` | one-off repair script | tracked | 1 / 902 | **kept — proposal P-01** | kept |
| `work_voicebridge.bat` | launcher | tracked | 1 / 559 | kept (live external-project work entry point) | kept |
| `assets/` | assets | tracked | 2 / 590,775 | kept | kept |
| `build/` | build evidence | ignored | 50 / 2,214,734 | kept; **not touched** (concurrent stage-6 work grew it) | 315 / 9,314,608* |
| `config/` | runtime config | tracked | 2 / 1,673 | kept (`voicebridge.yaml` is machine-local user data) | kept |
| `crewAI/` | vendor checkout | ignored | 38,926 / 807,816,022 | kept; audited read-only (see below) | kept |
| `data/` | user data | ignored | 34 / 17,727,025 | **never touched** | kept |
| `dist/` | release artifacts | ignored | 23,639 / 1,507,677,689 | **never touched** (stale payload; proposal P-05) | 23,642 / 1,508,780,252* |
| `docs/` | documentation | tracked | 89 / 1,797,593 | +4 new docs, +14 files moved in under `docs/history/legacy/` | 105 / 1,924,056 |
| `installer/` | distribution tooling | untracked (stage 6) | 5 / 65,698 | **not touched** (owned by stage-6 task) | owned elsewhere |
| `logs/` | diagnostics | ignored | 33 / 2,658,024 | **never touched** | kept |
| `nl_coding_agent/` | application source | tracked | 80 / 843,423 | **not touched** (stage-4 work owns it) | owned elsewhere |
| `python/` | embedded runtime | ignored | 36,596 / 1,724,118,083 | **never touched** | kept |
| `scripts/` | developer tooling | tracked | 11 / 175,537 | **not touched** (stage-4/6 tasks add scripts) | owned elsewhere |
| `tests/` | tests | tracked | 52 / 403,893 | **not touched** (stage-4 work owns it) | owned elsewhere |

Notes: asterisked after-values changed during the pass because a concurrent stage-6 task wrote under
`dist/` and `build/`; not by this task.

After: **31 root items = 16 files + 15 directories**. New root file: `README.md` (7,001 B).
New documentation: `README.md`, `docs/REPOSITORY_STRUCTURE.md` (8,962 B),
`docs/REPOSITORY_HYGIENE_FOLLOWUP.md` (this file) and `docs/history/legacy/INDEX.md` (4,374 B).
`docs/history/legacy/` bundle: **14 files / 97,133 B**, of which **92,759 B** is moved pre-existing
content and **4,374 B** is the new index.

## Actual changes

### Moves (git mv — history preserved, nothing deleted)

| Old path | New path |
|---|---|
| `README.txt` | `docs/history/legacy/README.txt` |
| `README_FIRST.txt` | `docs/history/legacy/README_FIRST.txt` |
| `START_HERE_ANTIGRAVITY.md` | `docs/history/legacy/START_HERE_ANTIGRAVITY.md` |
| `PASTE_THIS_IN_ANTIGRAVITY.txt` | `docs/history/legacy/PASTE_THIS_IN_ANTIGRAVITY.txt` |
| `AUDIT_REALE_E_LIMITI.md` | `docs/history/legacy/AUDIT_REALE_E_LIMITI.md` |
| `HANDOFF_DEEPSEEK_HARNESS.md` | `docs/history/legacy/HANDOFF_DEEPSEEK_HARNESS.md` |
| `FOUNDATION_CHANGES.patch` | `docs/history/legacy/patch-evidence/FOUNDATION_CHANGES.patch` |
| `PATCH/WINDOWS_REAUDIT.md` | `docs/history/legacy/patch-evidence/PATCH/WINDOWS_REAUDIT.md` |
| `PATCH/nl_coding_agent/core/code_integrity_gate.py` | `docs/history/legacy/patch-evidence/PATCH/nl_coding_agent/core/code_integrity_gate.py` |
| `PATCH/nl_coding_agent/core/recovery_store.py` | `docs/history/legacy/patch-evidence/PATCH/nl_coding_agent/core/recovery_store.py` |
| `PATCH/nl_coding_agent/core/staging_broker.py` | `docs/history/legacy/patch-evidence/PATCH/nl_coding_agent/core/staging_broker.py` |
| `PATCH/tests/test_rollback_stub.py` | `docs/history/legacy/patch-evidence/PATCH/tests/test_rollback_stub.py` |
| `PATCH/tests/test_staging_broker_adversarial.py` | `docs/history/legacy/patch-evidence/PATCH/tests/test_staging_broker_adversarial.py` |

Content of the moved files was not rewritten. `AUDIT_REALE_E_LIMITI.md` and
`HANDOFF_DEEPSEEK_HARNESS.md` become historical evidence; `SHA256_MANIFEST.json` at the root still
certifies the live files (5/5 verified after the move), and the moved `PATCH/**` copies still match
those hashes (5/5 verified), so the patch evidence remains verifiable.

### New / rewritten documents

| File | Purpose |
|---|---|
| `README.md` (root) | Single authoritative overview: capabilities, status, requirements, launchers/CLI quick start, repository layout, documentation map, verification commands, safety rules. No absolute workspace paths. |
| `docs/REPOSITORY_STRUCTURE.md` | Directory ownership matrix (class/git/owner/purpose/retention/packaging), generated-cache policy, backup rule, development-only exclusion list for the stage-6 portable payload, relocation-safety rule. |
| `docs/REPOSITORY_HYGIENE_FOLLOWUP.md` | This measured follow-up report: before/after inventory, changes, crewAI audit, proposals, validation, caveats. |
| `docs/history/legacy/INDEX.md` | Old -> new mapping, purpose and status of every archived document/patch, plus the list of references updated and of dated documents intentionally left untouched. |

### References updated for the moved files

- `AGENTS.md` — "Read `README.md` / `docs/REPOSITORY_STRUCTURE.md`…" replaces the root handoff
  pointer; new "Documentation entry points" section; vendor `crewAI/` note corrected (reference-only,
  not imported); all engineering rules preserved.
- `.agents/agents/nl-self-build-lead/agent.md` — agent prompt now points at `README.md` (legacy
  documents under `docs/history/legacy/` are evidence only).
- `docs/BLUEPRINT_INDEX.md` — evidence rows for the two historical audits now use
  `docs/history/legacy/...` paths.
- `docs/PRODUCT_BACKLOG.md` — the 6 audit citations point at `docs/history/legacy/...`.
- `docs/product-blueprint/INDEX.json` — `source_inventory` paths for the two historical audits
  updated (JSON revalidated; the supervisor gate reports the index valid: 103 requirements).

References intentionally **not** rewritten (dated records; see `docs/history/legacy/INDEX.md`):
`docs/WORKSPACE_MIGRATION.md`, `docs/REPOSITORY_HYGIENE.md`, `docs/PHASE2_HARNESS_INTEGRATION_PLAN.md`,
`docs/09_ANTIGRAVITY_EXECUTION_MISSION.md`, the two blueprint provenance notes and the raw
`docs/evidence/sh07/attempt2/console.log`.

### .gitignore additions

Semantics of the original entries are preserved; grouped comments and generated/cache categories were
added: `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.coverage`, `.coverage.*`, `htmlcov/`,
`.venv/`, `venv/`, `cache/`, `temp/`, `tmp/`, `*.tmp`, `*.bak`, `nul`, `%SystemDrive%/`,
`.idea/`, `.vscode/`, `.DS_Store`, `Thumbs.db`. No package-structure change and no source file
excluded.

### Explicitly not changed by this task

`nl_coding_agent/**`, `installer/**`, `scripts/build_release.py`, the GUI/app/core/persistence/
agents packages, `data/**`, `logs/**`, `python/**`, `crewAI/**`, `dist/**`, `build/**` evidence,
`config/voicebridge.yaml`, `assets/**`. Nothing was deleted, no mission/model/network run was
started and **no git commit was made**.

## crewAI/ checkout audit (read-only)

**Size:** `crewAI/` = **38,926 files / 807,816,022 B (770.39 MiB)** — the second-largest protected
tree after the runtime and the stale `dist/` payload. It is git-ignored, so it never enters repository
packaging by accident.

| Component | Files | Bytes | Notes |
|---|---:|---:|---|
| `crewAI/.git` | 28 | 318,009,648 | embedded git metadata of the vendor checkout (dominant cost) |
| `crewAI/docs` | 36,613 | 437,382,240 | upstream documentation tree |
| `crewAI/lib` | 2,234 | 50,303,068 | upstream source |
| `crewAI/pyproject.toml` | 1 | 20,033 | upstream project metadata |
| `crewAI/uv.lock` | 1 | 1,812,025 | upstream lockfile |
| `crewAI/.github`, `scripts`, `UNKNOWN.egg-info`, `__pycache__` | — | ~245 KiB | upstream CI/scripts/build metadata |
| `crewAI/README.md`, `LICENSE` | 2 | 34,569 | upstream docs/license evidence |

**Is it imported or required?**

- The application imports the **installed** `crewai` package from `python/Lib/site-packages`; the
  import smoke check reported `imports OK; crewai 1.15.32`, and the dependency pin in
  `pyproject.toml` is `crewai==1.15.32`.
- A grep of all tracked files found **no application/API import from the vendor path**. References
  are limited to: tests using `crewAI/crewai.py` as a *forbidden-path fixture*
  (`tests/test_scope_permission.py`, `tests/test_roadmap.py`); the SBOM/compat checker reading
  `crewAI/LICENSE` as license evidence (`scripts/check_crewai_upgrade.py`); the hygiene audit
  classifying `crewAI/.git` as protected; and `.gitignore`/`AGENTS.md` vendor policy.
- The packaging allowlist (`scripts/stage_portable.py`) excludes `crewAI/`; the package finder in
  `pyproject.toml` includes only `nl_coding_agent*`; the portable payload bundles the installed
  package through the embedded runtime.
- Replacement status: **already replaced** — the runtime uses installed `crewai==1.15.32` plus the
  app-owned `nl_coding_agent.agents.crew_backend` seam; the checkout is reference-only.
- License evidence for distribution: `crewAI/LICENSE` (MIT-style) remains in the checkout and the
  dependency/license inventory is captured by `docs/evidence/crewai_sbom.json` (SBOM verify: OK).

**Recommendation (no action taken):** keep the checkout as protected reference material. If disk
reclamation is wanted later, the only defensible options require explicit user authorization:
archive `crewAI/.git` (318 MB of metadata) and/or `crewAI/docs` (437 MB upstream docs) outside the
repository while retaining `LICENSE` and the SBOM evidence; never delete or rewrite the checkout as
part of repository hygiene.

## Proposals requiring explicit authorization (nothing in this section was executed)

| ID | Item(s) | Finding | Proposed action — requires user/Lead authorization |
|---|---|---|---|
| P-01 | `temp_fix_planner.py`, `temp_fix_title.py`, `temp_restore.py`, `temp_restore_planner.py` (4 tracked root scripts, 4,642 B) | One-off repair scripts that **mutate source files and the live SQLite DB** when executed; superseded by the committed tree. Still flagged `NEEDS-AUTHORIZATION` by the audit. | Keep out of any execution path. Either move to `docs/history/legacy/temp-scripts/` or `git rm` them in an authorized commit. Do not run. |
| P-02 | `SHA256_MANIFEST.json` (root) | Live integrity metadata: certifies the 5 audited safety-foundation files, all 5 match now. Referenced by `scripts/audit_repository_hygiene.py` and `docs/PHASE2_HARNESS_INTEGRATION_PLAN.md`. | **Recommend keeping at the root.** Removal would require migrating the certification evidence first; not proposed now. |
| P-03 | `audit_voicebridge.bat`, `work_voicebridge.bat` | Live, validated launchers for the external NL VoiceBridge Studio project (`config/voicebridge.yaml`, user data). Not obsolete. | Keep at root as user-facing entry points. Optional later cleanup: group/rename launchers for clarity — requires authorization and a user-facing doc update. |
| P-04 | `crewAI/` vendor checkout (770.39 MiB) | Reference-only; not imported. | Keep (see crewAI audit). Optional user-authorized archival of `crewAI/.git`/`crewAI/docs` outside the repository; never delete/rewrite. |
| P-05 | `dist/portable-release` (stale payload, 1.40 GiB) | Built before the relocation and before stages 2-4; missing the `flows` package. Protected `DO-NOT-TOUCH`. | Rebuild/replace only at stage 6 after explicit authorization (matches the stage-6 program note). Not touched. |
| P-06 | `build/` evidence (incl. now-empty `build/phase2`, `build/phase4`) | Evidence for completed stages and the relocation; safe to prune only after the corresponding acceptance decisions are closed and the Lead agrees. | Keep through release acceptance; prune in a later authorized pass. `build/phase5b/` holds this follow-up's audit snapshots. |
| P-07 | Portable payload user documentation | The staging allowlist ships launchers/runtime but not the new root `README.md`. | The stage-6 build owner should add `README.md` to the payload allowlist in an authorized change; not edited here (`scripts/` owned by stage 6). |
| P-08 | Patch evidence location (`docs/history/legacy/patch-evidence/`) | Moved, not deleted, so the audited patch + re-audit remain verifiable. | If the Lead/user prefer the evidence at the root, reverse with `git mv` — content is intact and hashes still match `SHA256_MANIFEST.json`. Listed here because the task description named `PATCH/` and `FOUNDATION_CHANGES.patch` as potentially valuable evidence. |

## Validation results (after the changes)

| Check | Command | Result |
|---|---|---|
| Embedded Python | `python\python.exe -c "import sys; print(sys.version)"` | **3.12.10** (embedded runtime) |
| CrewAI import/version | `python\python.exe -c "import crewai; print(crewai.__version__)"` | **1.15.32 OK** |
| Application imports | `nl_coding_agent.cli, .main, .flows, .core.supervisor, .agents.crew_backend, .models.model_router, .tools.registry` | **OK** |
| Launchers | 6 `.bat` entry points | All use `cd /d "%~dp0"`, reference `python\python.exe` + `nl_agent.py`, no absolute paths |
| Doctor | `python\python.exe nl_agent.py doctor` | **exit 0** — Ollama OK, project OK, 3 configured model roles OK |
| Relocation gate | `python\python.exe scripts\verify_relocation.py` | **29 passed, 0 failed, 1 warning** (`git.working_tree`: 10 uncommitted paths — this task's documentation changes, expected); `paths.operational_docs_clean`: 22 files checked, 0 hits; read-only DB/state hashes unchanged |
| Supervisor gate | `python\python.exe scripts\verify_supervisor.py` | **PASS** (8/8: schema, no lease, no running supervisor, no unreconciled journal, queue consistent, default mode off, blueprint index valid — 103 requirements, schema 1, current stage 4) |
| CrewAI SBOM | `python\python.exe scripts\check_crewai_upgrade.py --verify-sbom` | **SBOM OK: SBOM matches installed runtime** |
| Mission persistence (read-only) | SQLite `mode=ro` query + state JSON | **1 project (id=1) at canonical root; 45 missions total, 15 owned, 13 completed, 0 running; integrity `ok`; state key canonical, `last_completed_mission_id=43`, audit notes 42/43 preserved** |
| SHA-256 manifest | hash of all 5 entries | **5/5 match** live files; moved PATCH evidence copies **5/5 match** the same hashes |
| Blueprint JSON | JSON parse + supervisor gate | **valid** |
| Targeted tests | `pytest -q tests\test_repository_hygiene.py tests\test_verify_relocation.py` | **24 passed** in 3.86 s |
| Full test suite | — | **Not run by this task** (per instructions; Lead runs it) |

## Concurrent-activity caveats

- During this pass other teammates committed stage-4/6 work: HEAD moved
  `bf2a616` -> `4787c30` (stage 4 F1) -> `8040022` (stage 4 F2) -> `771ecd1` (stage 6a). The
  stage-4 F1 commit `4787c30` **also swept up the already-staged `git mv` renames of this pass**
  (the renames were staged when that commit was created; this task made no commit). The moves are
  therefore tracked in `4787c30` rather than in a dedicated hygiene commit — the Lead may want to
  note that in the stage history. By the end of the pass the other tasks' work was committed and
  `git status` showed only this task's uncommitted documentation changes.
- The same window saw active stage-4/6 work: uncommitted modifications under `nl_coding_agent/` and
  `tests/`, new `installer/`, `scripts/build_release.py`, `docs/BOOTSTRAPPER.md`, and stage-6
  reproducible-build artifacts under `build/phase6a/` (315 `build/` files at the after snapshot).
  Consequently: repository-wide file counts, duplicate groups (12 -> 236) and stale-path matches
  (126 -> 137) in the before/after audit snapshots are **not** a clean delta for this pass. The
  isolated deltas reported in this document (root inventory, moved bytes, resolved obsolete
  findings, reference updates, documentation sizes) are the attributable changes.
- The relocation/supervisor/doctor gates and targeted tests were run while that concurrent work was
  present; they passed. The Lead's full-suite run should be executed after all active tasks are
  quiet.

## Baseline artifacts

- `build/phase5b/hygiene_before.json` / `.md` — read-only audit snapshot before the changes.
- `build/phase5b/hygiene_after.json` / `.md` — read-only audit snapshot after the moves and new docs.
- `docs/history/legacy/INDEX.md` — the authoritative old -> new mapping.
- `docs/REPOSITORY_STRUCTURE.md` — resulting directory ownership/policy.

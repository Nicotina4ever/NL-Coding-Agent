# Root Reorganization Report (2026-10-28)

**Status:** implemented and verified. This is the concrete root-reorganization pass requested by the
repository owner, not a classification-only audit. No user data, runtime, evidence, vendor material
or release candidate was deleted.

## Target outcome

```text
K:\AI\NL Coding Agent\
├── .agents/  .github/  .workspace/  assets/  config/  da_eliminare/
├── data/  docs/  installer/  nl_coding_agent/  python/  scripts/  tests/
├── .gitignore  AGENTS.md  NL Coding Agent.bat  nl_agent.py  pyproject.toml
├── README.md  SHA256_MANIFEST.json
```

- **One obvious application launcher:** `NL Coding Agent.bat`; CLI/external launchers live under
  `scripts/launchers/` and are re-mapped to the portable payload root by `scripts/stage_portable.py`.
- **Generated outputs consolidated** under `.workspace/` with one configurable policy
  (`NL_WORKSPACE_DIR`, default `<repo>/.workspace`): `build/`, `dist/`, `logs/`, `temp/`,
  `cache/`, `state/`.
- **Deliberate exceptions:** `python/` (embedded runtime shipped with the app) and `data/`
  (live SQLite/mission history; relocation-acceptance dependency) stay at their historical paths.
- **Review-only staging:** `da_eliminare/` holds material that appears no longer needed
  (`da_eliminare/crewAI`, 770.39 MiB vendor checkout). Nothing inside may be deleted, archived or
  removed from Git without explicit owner authorization.
- **Distribution separation:** the portable payload (stage_portable) excludes `.workspace/`,
  `da_eliminare/`, tests, scripts, docs, installer, data, caches, build and vendor material; it
  ships the app sources, one embedded runtime, README, launchers, assets, config/models.yaml and
  pyproject.

## BEFORE / AFTER root tree (measured)

| Moment | Top-level items | Files | Dirs |
|---|---|---|---|
| Before Phase A (original cluttered root) | **32** | 16 | 16 |
| After Phase A (launchers/scripts archived) | **24** | 7 | 17 |
| **After Phase B (final)** | **21** | **7** | **14** |

Before Phase B the root also contained `build/` (333 files / 9,708,087 B), `dist/` (71,008 files /
4,525,591,017 B) and `logs/` (33 files / 2,658,024 B). After the migration the root contains only
`.agents`, `.git`, `.github`, `.workspace`, `assets`, `config`, `da_eliminare`, `data`,
`docs`, `installer`, `nl_coding_agent`, `python`, `scripts` and `tests`, plus the seven root
files listed above. Root file bytes: 24,670 (pre-Phase-A) -> **22,399**.

## Actual changes

### Files moved (git mv, content preserved)
| From (root) | To | Purpose |
|---|---|---|
| `temp_fix_planner.py`, `temp_fix_title.py`, `temp_restore.py`, `temp_restore_planner.py` | `docs/history/legacy/temp-scripts/` | dated one-off repair scripts; evidence only, never execute |
| `doctor.bat`, `status.bat`, `Self-Build Mode.bat` | `scripts/launchers/` | CLI launchers, behaviour and exit codes preserved |
| `audit_voicebridge.bat`, `work_voicebridge.bat` | `scripts/launchers/voicebridge/` | external-project launchers, paths preserved |

### Directories consolidated (same-volume moves, no copies/deletion)
| From | To | Measured before |
|---|---|---|
| `build/` | `.workspace/build/` | 333 files / 9,708,087 B |
| `dist/` | `.workspace/dist/` | 71,008 files / 4,525,591,017 B |
| `logs/` | `.workspace/logs/` | 33 files / 2,658,024 B |
| absent | `.workspace/temp/`, `cache/`, `state/` | created empty |

### Vendor checkout staged (moved, never deleted)
| From | To | Size |
|---|---|---|
| `crewAI/` | `da_eliminare/crewAI/` | 38,926 files / 807,816,022 B (770.39 MiB) |

Evidence that it is unused by the application, its nested Git state, hashes, reversibility and the
open authorization item are recorded in `docs/CREWAI_CHECKOUT_REMOVAL_PROPOSAL.md`; the SBOM/license
gate resolves the staged LICENSE path and remains green.

### Removed / deleted
**Nothing.** No file, directory, build artefact, database, evidence or vendor material was deleted.
`da_eliminare/` is the only staging area and is excluded from Git (except its README), packaging and
the release builder.

## Disk-space changes (measured)

- Root generated data **relocated**: 4,537,957,128 B (build+dist+logs) moved out of the root; the
  final `.workspace/` holds 71,382 files / **4,540,182,558 B**, including post-migration evidence.
- Same-volume renames: **0 bytes freed**; the benefit is layout clarity, not reclaimed space.
- `da_eliminare/crewAI`: 770.39 MiB relocated, 0 bytes freed; permanent deletion would reclaim it
  only after explicit owner authorization.
- Root file bytes: 24,670 -> **22,399**; root items: 32 -> **21**.

## Verification (final tree)

| Check | Result |
|---|---|
| Full offscreen test suite | **628 passed** |
| Relocation gate (incl. new workspace checks) | **33 passed, 0 failed, 1 expected warning (uncommitted tree at measurement)** |
| Supervisor gate | **ok** |
| CrewAI SBOM verify | **OK** |
| Doctor / CLI help / CLI status | PASS (state resolves under `.workspace/state`) |
| Headless GUI smoke | **PASS 9/9** |
| Portable staging dry run | 23,683 files / 1,508,446,416 B; single runtime; `.workspace` excluded; no absolute paths |
| Release-builder smoke | 315 tracked files; archive built with no `.workspace` paths |
| SHA256_MANIFEST | **5/5** unchanged |
| Secrets/history audit (re-run at final HEAD) | **CLEAR-WITH-REVIEW, blocking 0** (66 findings: 0 rotate, 3 exclude present-untracked, 63 review; one documented fixture allowlist for synthetic redaction-test values) |
| Root layout regression | new `tests/test_workspace_paths.py` fails if legacy root `build/dist/logs/temp/cache` reappear |

## Actions requiring owner authorization (nothing executed)

1. **Delete or replace stale release candidates** under `.workspace/dist/`: the pre-relocation
   `portable-release` (23,639 files / 1,507,677,689 B) and the stage-6a/6b candidates retained as
   evidence; keep at most one verified candidate after the release decision.
2. **Delete `da_eliminare/crewAI`** (770.39 MiB): before any deletion preserve LICENSE evidence in a
   tracked location and re-verify the SBOM.
3. **Clean `da_eliminare/`** generally: nothing may be deleted/archived/removed from Git without
   explicit owner authorization.
4. **Upload/publish gate:** the secrets audit must be re-run immediately before any upload; no
   push/publish/visibility change/collaborator invitation/release upload without explicit owner
   authorization (see `docs/PRIVATE_BETA_RUNBOOK.md`).

## Historical notes

Dated evidence documents (repository hygiene reports, completed-mission records, phase plans,
acceptance logs) intentionally keep pre-migration paths; `docs/WORKSPACE_MIGRATION.md` carries the
Phase A/B record and explains that those references are historical. Generic project scanners keep
legacy `build/dist/logs` names only in ignore/protection lists for arbitrary managed projects.

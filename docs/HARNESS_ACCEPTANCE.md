# Staged-Candidate Harness - Acceptance Evidence and SH Mapping

Date: 2026-10-28. Program stages 2 (transactional staging/safety/self-healing, complete)
and 3 (persistent supervisor and verified handoff, in progress).
Canonical plans: `docs/PHASE2_HARNESS_INTEGRATION_PLAN.md` and
`docs/PHASE3_SUPERVISOR_PLAN.md`. Backlog IDs: `docs/PRODUCT_BACKLOG.md`
(NL-BP-055..060, 061..065, 072..076, 147).

## Component commits

| Step | Commit | Scope |
|---|---|---|
| C1a | cb5184e | audited staging broker / recovery store / integrity gate v2 applied byte-verified |
| C1b | 451211c | Windows newline re-audit of the audited recovery test (fixture only) |
| C2 | 8871145 | deterministic model seam, 4-tool model surface, LF-safe scoped writes |
| C3 | 7372128 | promotion lifecycle (stage/validate/verify/recovery/CAS/journal/reconcile) |
| C4 | 10aa437 | candidate + oracle disposable-copy regression verification |
| C5 | 7e778da | additive harness DB schema, persistence helpers, legacy/preflight gates |
| C6 | bce3b71 | staged-candidate lifecycle wired into MultiAgentOrchestrator |
| C7 | 3790aaf | post-hoc runner gate removed; legacy resume refused in CLI |
| C9a | 641c333 | universal permission model + fail-closed cloud/network escalation |
| C9b | 283a94e | external tool registry, verified recovery retention, repair evidence |
| C3a | d81a168 | stage-3 additive supervisor schema, durable store, settings helpers |
| C3b | c91e0c9 | indexed-blueprint backlog loader and deterministic mission planner |
| C3c | b9ec909 | supervisor core: lease/heartbeat, preflight, reconcile, loop, run control, resource gate |
| C3d | dbe3c3b | supervisor CLI/service/GUI surfaces and selfbuild compatibility shim |
| C3e | this change | SH-07 Tier A acceptance suite, acceptance/verification scripts, docs and evidence |

## SH-01..SH-07 status

| Gate | Requirement | Evidence (tests) | Status |
|---|---|---|---|
| SH-01 | planner replaced by stub; live files intact | tests/test_staging_broker_adversarial.py::test_sh01_stub_never_touches_live_source; tests/test_orchestrator_staging.py stub scenario | VERIFIED (fake model) |
| SH-02 | dirty/untracked + external conflict; CAS preserves human edits | tests/test_promotion_stage.py::test_external_live_edit_blocks_promotion, ::test_mixed_journal_is_rolled_back_with_cas; staging human-edit scenario | VERIFIED |
| SH-03 | interruption/kill between stages; resume reconciles | tests/test_promotion_stage.py journal tests; tests/test_orchestrator_staging.py stop-after/resume; promotion preflight | VERIFIED (fake model) |
| SH-04 | green but weakened tests caught by oracle | tests/test_candidate_verification.py::test_oracle_catches_green_but_weakened_candidate | VERIFIED |
| SH-05 | out-of-scope/shell writes rejected | tests/test_promotion_stage.py scope/protected tests; 4-tool surface test; seam static guard | VERIFIED (tool broker; no OS sandbox claimed) |
| SH-06 | economic/integrity recovery points | tests/test_retention.py (11: read-only audit, verified zip archive, guarded all-or-nothing cleanup); tests/test_rollback_stub.py; tests/test_promotion_stage.py recovery/CAS; staging excludes python/crewAI/dist/data | VERIFIED (archive + retention implemented; no blob dedup by design) |
| SH-07 | two consecutive missions without manual repair | Tier A (fake model): `tests/test_supervisor_sh07.py` 7 tests PASS - two consecutive staged-candidate missions, promotion only per mission, restart/pause/resume idempotency, fail-closed invalid candidate and oracle-red negatives; `scripts/run_supervisor_sh07.py --mode fake` evidence under `build/phase3/evidence/`. Tier B (real local models) pending explicit Lead authorization. | TIER A VERIFIED / TIER B PENDING (NL-BP-063 stays blocked) |

## Stage-3 SH-07 acceptance (2026-10-28)

### Tier A - deterministic fake-model end-to-end (executed, PASS)

- Test: `tests/test_supervisor_sh07.py` (7 tests, 15.5 s), on a tiny temp project with a
  fixture `INDEX.json` and a scripted model seam; the real staged-candidate pipeline
  (candidate + oracle verification, reviewer, promotion) runs for real, only the model is fake.
- Cases: two consecutive requirement missions complete with no manual repair and exactly one
  promotion/handoff per mission; queue/backlog/evidence/run transitions verified; restart
  between missions resumes the next requirement without duplicate missions or queue rows; a third
  run is a no-op; pause at the mission boundary then resume completes the remaining mission;
  stop at the after-developer checkpoint keeps the staged candidate and resumes it without a
  second promotion; invalid candidate and oracle-red candidate fail closed (live tree unchanged,
  no promotion, no recovery point, blocked queue/backlog); default mode off runs nothing.
- Evidence generator: `python\python.exe scripts\run_supervisor_sh07.py --mode fake`
  -> PASS, machine-readable evidence in `build/phase3/evidence/sh07-fake-<UTC>/evidence.json`
  (pytest result + `scripts/verify_supervisor.py --json` report + git HEAD + file hashes).
- Read-only gate: `python\python.exe scripts/verify_supervisor.py --project . --json`
  -> PASS (schema tables present, no active lease, no live supervisor, no unreconciled journal,
  queue/backlog consistent, default mode off, indexed backlog valid).

### Tier B - real local-model evidence (NOT executed; requires explicit authorization)

- Command (run only after the Lead/user authorizes it; never in CI):
  `python\python.exe scripts\run_supervisor_sh07.py --mode live --confirm-live --worktree <isolated-worktree-path>`
- Preconditions enforced by the runner: `--confirm-live`; an isolated `git worktree`
  outside the repository, clean and at the same HEAD; temporary `NL_DATA_DIR`;
  permissions cloud/network revoked in that temporary app data (the runner refuses grants);
  local-only model config (no cloud model for any role, no enabled remote provider, no cloud
  fallback); Ollama reachable with every configured role model installed; no commit; the
  worktree is never modified outside the normal staged-candidate promotion.
- Required artifacts: `build/phase3/evidence/sh07-live-<UTC>/evidence.json` (run result,
  missions, queue, backlog, evidence rows), `summary.md`, `git.diff`,
  `supervisor.sqlite3` snapshot; the authored backlog update is produced only after a
  human review.
- Pass criteria: two consecutive real local-model missions complete with passing candidate+oracle
  verification and promotion, automatic backlog progress in SQLite, restart survival, no manual
  code repair, no cloud/network use, no unresolved journal/lock.
- If Tier B fails, the evidence is recorded and NL-BP-063 stays `blocked`; gates are never
  weakened and the live repository is never the target.

## Stage-2 closure (2026-10-28)

C9a/C9b completed the remaining stage-2 requirements: permissions + cloud gate (NL-BP-072/076), tool registry (NL-BP-073), retention archive/cleanup (SH-06) and repair success/budget evidence (NL-BP-065). Full suite: **215 passed**. Relocation gate: 30/30 PASS. Stage 2 is complete except NL-BP-003 real-model end-to-end evidence, which is the stage-3 SH-07 acceptance gate.

## Verification commands (safe, read-only for the live tree)

`powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
python\python.exe -m pytest -q tests -p no:cacheprovider     # full suite (Lead-run; 310 passed at C3d)
python\python.exe -m pytest -q tests/test_supervisor_sh07.py -p no:cacheprovider        # Tier A: 7 passed
python\python.exe -m pytest -q tests/test_supervisor_core.py tests/test_supervisor_cli.py -p no:cacheprovider
python\python.exe -m pytest -q tests/test_orchestrator_staging.py -p no:cacheprovider  # 8 passed
python\python.exe -m pytest -q tests/test_promotion_stage.py tests/test_candidate_verification.py -p no:cacheprovider
python\python.exe scripts\run_supervisor_sh07.py --mode fake                           # Tier A evidence PASS
python\python.exe scripts\verify_supervisor.py --project . --json                      # read-only gate PASS
python\python.exe scripts\verify_relocation.py                          # 30/30 PASS
`

## Declared limitations

- Candidate code executes with user privileges; no OS sandbox (mitigations only).
- Network is not isolated.
- Oracle pinning blocks legitimate behaviour/test changes until a human-reviewed baseline update.
- Promoted files are LF-normalized (Windows CRLF adaptation).
- Persistent supervisor (stage 3): the supervisor is a process/thread loop, not an OS service
  (no reboot survival); stop is cooperative at safe checkpoints (a running model call finishes
  first); automatic mode is off by default and cloud/network/delete still require grants.
- No autonomous self-build mission has been run on the new supervisor yet; Tier A SH-07 is
  verified with a fake model, Tier B (real local models) is the gate before unattended autonomy.

# Staged-Candidate Harness - Acceptance Evidence and SH Mapping

Date: 2026-10-28. Program stage 2 (transactional staging, safety, self-healing).
Canonical plan: `docs/PHASE2_HARNESS_INTEGRATION_PLAN.md`. Backlog IDs:
`docs/PRODUCT_BACKLOG.md` (NL-BP-055..060, 074, 147).

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

## SH-01..SH-07 status

| Gate | Requirement | Evidence (tests) | Status |
|---|---|---|---|
| SH-01 | planner replaced by stub; live files intact | tests/test_staging_broker_adversarial.py::test_sh01_stub_never_touches_live_source; tests/test_orchestrator_staging.py stub scenario | VERIFIED (fake model) |
| SH-02 | dirty/untracked + external conflict; CAS preserves human edits | tests/test_promotion_stage.py::test_external_live_edit_blocks_promotion, ::test_mixed_journal_is_rolled_back_with_cas; staging human-edit scenario | VERIFIED |
| SH-03 | interruption/kill between stages; resume reconciles | tests/test_promotion_stage.py journal tests; tests/test_orchestrator_staging.py stop-after/resume; promotion preflight | VERIFIED (fake model) |
| SH-04 | green but weakened tests caught by oracle | tests/test_candidate_verification.py::test_oracle_catches_green_but_weakened_candidate | VERIFIED |
| SH-05 | out-of-scope/shell writes rejected | tests/test_promotion_stage.py scope/protected tests; 4-tool surface test; seam static guard | VERIFIED (tool broker; no OS sandbox claimed) |
| SH-06 | economic/integrity recovery points | tests/test_rollback_stub.py; tests/test_promotion_stage.py recovery/CAS; staging excludes python/crewAI/dist/data | PARTIAL (archive/dedup/retention UX is future scope) |
| SH-07 | two consecutive missions without manual repair | not executed on the reworked supervisor yet | PENDING stage 3 (NL-BP-063) |

## Verification commands (safe, read-only for the live tree)

`powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
python\python.exe -m pytest -q tests -p no:cacheprovider     # 149 passed (2026-10-28)
python\python.exe -m pytest -q tests/test_orchestrator_staging.py -p no:cacheprovider  # 8 passed
python\python.exe -m pytest -q tests/test_promotion_stage.py tests/test_candidate_verification.py -p no:cacheprovider
python\python.exe scriptserify_relocation.py              # 30/30 PASS
`

## Declared limitations

- Candidate code executes with user privileges; no OS sandbox (mitigations only).
- Network is not isolated.
- Oracle pinning blocks legitimate behaviour/test changes until a human-reviewed baseline update.
- Promoted files are LF-normalized (Windows CRLF adaptation).
- No autonomous self-build mission has been run on the new harness yet; SH-07 is the gate before unattended autonomy (stage 3).

# Final Release Hygiene & GitHub Publication Gate - Capability Audit (read-only)

**Task:** shared task-70. **Date:** 2026-10-28 (Europe/Rome). **Repository:** `K:\AI\NL Coding Agent` at git HEAD `a93162e` (clean working tree before this task).
**Type:** read-only capability audit + queue-only backlog input. **No implementation, no publication/push, no code change, and no model/network/mission run was performed.**
**Directive under audit:** Final Release Hygiene & GitHub Publication Gate + mandatory pre-push secrets/content scan (2026-10-28, queue only).

---

## 1. Executive summary

The repository already has a strong **read-only audit, release-acceptance and authorization** foundation, but it does **not** yet have a single final release-readiness milestone or a *mandatory blocking* pre-push publication gate:

- **Hygiene/audit:** read-only distribution audit, repository-hygiene audit (classifications SAFE/NEEDS-AUTHORIZATION/DO-NOT-TOUCH, actions taken: none), root-reorganization reports and cleanup proposals exist; requirements NL-BP-090/091/095 are verified, NL-BP-092/093/094/096/097 partial. All cleanup remains authorization-gated, and no integrated BEFORE/AFTER readiness milestone with exact move/delete/consolidation report + disk/Git-history analysis + full regression/packaging verdict exists.
- **Distribution/portable/installer:** staging, source release, beta packaging, synthetic rehearsal and acceptance-matrix tooling exist (NL-BP-110/112 verified; 111/115/120/121/122 partial; 113/114/116-119/123/124 planned; 140 verified; 149/141/150/151 partial; 195-197 planned). There is no consolidated "final repository/distribution readiness" pass.
- **Secrets/history audit:** NL-BP-162 is **verified**: `scripts/audit_release_secrets.py` performs a bounded read-only scan of tracked files, Git history, present roots and Git config, with redacted evidence, findings classifications and an **exit-code upload gate**; `docs/SECRETS_AUDIT.md` records a measured run (CLEAR-WITH-REVIEW, 0 blocking) and `docs/PRIVATE_BETA_RUNBOOK.md` requires running it before sharing/uploading. **However:** it is not wired into CI (no secrets/audit step in `.github/workflows/ci.yml`), no Git hook or `core.hooksPath` is configured (only `.git/hooks/*.sample`), it has no explicit staged-change pre-push mode/fail-closed policy, and the report must be re-run manually at the final HEAD. The *mandatory blocking pre-push gate* is therefore missing.
- **Publication/authorization:** NL-BP-163 documents owner gates G-1..G-10 (no push, visibility change, collaborator invite, release upload, history rewrite, evidence deletion), the repository has **no configured remote**, and NL-BP-164/165 track real-hardware/CI/beta acceptance as **MANUAL-PENDING**. NL-BP-197 (source-vs-binary separation) and NL-BP-198 (readiness taxonomy) are planned. There is no explicit, recorded **publication-readiness verdict** artifact that must remain "not ready" while external acceptance is unresolved, with authorization/residual-risk sign-off.
- **Constraints confirmed:** no push/publish without explicit owner authorization; SH-07 Tier B remains blocked (NL-BP-063); real hardware/clean-machine/external CI/beta records remain MANUAL-PENDING (152-158/164/165). No code/model/network/publish is authorized by a queued backlog item.

Three genuine gaps were registered as planned **NL-BP-234..236** in new **program stage 10** after the dedupe mapping in section 5.

## 2. Method and evidence rules

- Static read-only inspection of `scripts/**`, `docs/**`, `.github/workflows/ci.yml`, `.git/hooks`, Git remote/hooks configuration and `docs/product-blueprint/INDEX.json`; commands in section 8.
- No audit script, test, model, mission, publish or network operation was executed by this task. Existing reports were read, not regenerated.
- "Implemented" does not mean the final publication milestone passed; no publication readiness is claimed here.

## 3. Existing capability evidence

### 3.1 Repository hygiene/audit tooling and requirements 090-097

| Evidence | Finding |
|---|---|
| `scripts/audit_distribution.py`; `tests/test_distribution_audit.py` | read-only distribution/dependency audit producing measured reports; NL-BP-090 verified |
| `scripts/audit_repository_hygiene.py:3-6, 1459-1466, 1656-1666` | **read-only guarantee** (never deletes/moves/renames/modifies tracked files; local read-only git queries), classifications SAFE / NEEDS-AUTHORIZATION / DO-NOT-TOUCH, JSON/Markdown reports; actions taken: none |
| `docs/REPOSITORY_HYGIENE.md:1-18` | measured stage-5 audit: 99,991 files / 3.79 GiB; 21 findings; "Actions taken: none"; all recommendations are proposals; protected assets (runtime, stale release, vendor checkout, data, evidence) explicitly excluded |
| `docs/REPOSITORY_HYGIENE_FOLLOWUP.md:1-33` | structural consolidation pass (docs only; nothing deleted; root 38→31 items; crewAI audited and kept; read-only gates pass) |
| `docs/REPOSITORY_STRUCTURE.md`; `docs/ROOT_REORGANIZATION_REPORT.md:1-60` | ownership/retention/authorization policy; implemented root reorganization (32→21 root items, .workspace/ consolidation, launchers, `da_eliminare/` review staging; no user data/runtime/evidence deleted) |
| `docs/history/legacy/INDEX.md` | dated legacy documents/temp scripts preserved (never deleted, never executed) |
| Requirements | NL-BP-090 verified; 091 verified; 092/093/094/096/097 partial; 095 verified - individual audits/containment exist, but no single integrated final readiness milestone |

### 3.2 Distribution / portable / installer / release-candidate evidence (110-124, 149, 195-197)

| Evidence | Finding |
|---|---|
| `scripts/stage_portable.py`; `tests/test_stage_portable.py` | portable payload staging with allowlist, fail-closed checks, manifest (NL-BP-110 verified) |
| `docs/RELEASE_ACCEPTANCE.md:1-63` | candidate identity/reproducibility/acceptance from a non-default temp path; **release acceptance PARTIAL**, manual-pending explicitly listed; stale candidates retained pending authorization |
| `docs/BOOTSTRAPPER.md`; `scripts/build_release.py`, `scripts/build_beta_packages.py`, `scripts/rehearse_release.py` | reproducible source release, beta package builder and synthetic end-to-end rehearsal (explicitly **NOT-A-RELEASE**, synthetic fixtures) |
| `scripts/release_acceptance.py:45-333` | acceptance matrix from committed evidence + validated tester records; CI shown as partial/never hardware; secrets gate read from docs/SECRETS_AUDIT.md; all six targets MANUAL-PENDING |
| `docs/RELEASE_ACCEPTANCE.md:220-243` | cross-platform extension 152-165: partial + MANUAL-PENDING; no cross-platform support claimed; NL-BP-162 verified tooling, NL-BP-164 partial |
| Requirements | 110/112 verified; 111/115/120/121/122 partial; 113/114/116-119/123/124 planned; 140 verified; 141/149/150/151 partial; 195/196/197 planned - no consolidated final repository/distribution readiness pass |

### 3.3 Secrets/history audit and pre-upload hooks (162/163 + scripts/docs)

| Evidence | Finding |
|---|---|
| `scripts/audit_release_secrets.py:108-202, 302-365, 591-723` | secret rules, test-fixture allowlist, redaction helpers, artifact-path classification; bounded read-only scan |
| `scripts/audit_release_secrets.py:743-841, 857-960` | `audit_release()` scans tracked files, present roots and Git config; report with counters/findings/gate |
| `scripts/audit_release_secrets.py:996-1134` | bounded Git-history scan of added lines (commits, object paths, budgets) - history covered |
| `scripts/audit_release_secrets.py:1313-1334` | CLI with bounds/quiet/no-write; writes report paths only; **no push/publish action** |
| `docs/SECRETS_AUDIT.md:1-29, 128-147` | measured HEAD 259eda5: 335 tracked files, 59 commits/390 object paths, 66 findings (0 blocking), **Upload gate CLEAR-WITH-REVIEW**; explicitly says report must be re-run and owner authorization remains required; tool limits documented (pattern-based, bounded, no LFS/submodules) |
| `docs/PRIVATE_BETA_RUNBOOK.md:24-40, 50-79` | owner gates G-1..G-10 (push/visibility/collaborators/upload/history/evidence), pre-upload checklist includes hygiene audit, secrets audit and `git grep` patterns |
| `.github/workflows/ci.yml` (jobs at lines 23/115/148) | CI runs unit/integration/GUI/bootstrapper checks, package smoke and reproducible source release; **no `audit_release_secrets.py` step and no blocking secrets gate** |
| `.git/hooks` + `git config --get core.hooksPath` | only `.sample` hooks; **core.hooksPath unset** - no enforced pre-push hook |
| `git remote -v` | **empty** - no configured remote; nothing to push today |
| Requirements | NL-BP-162 **verified** (audit tooling + bounded history + exit-code gate); NL-BP-163 partial (owner gates documented, no standing authorization) |

**Conclusion:** the scanner and a read-only "upload gate" exist, but the directive's **mandatory blocking pre-push gate** (CLI + Git hook/CI wiring, staged-change coverage, fail-closed enforcement, never deferred, never pushes) is genuinely missing.

### 3.4 Acceptance/readiness and current constraints

| Evidence | Finding |
|---|---|
| `scripts/release_acceptance.py:252-333` | matrix includes CI and secrets gates, six targets, MANUAL-PENDING for missing hardware records |
| `docs/RELEASE_ACCEPTANCE.md:3-9, 220-243` | status PARTIAL; manual-pending listed; no release/publication claim |
| `docs/BETA_ACCEPTANCE.md:1-29` | tester-record workflow; CI never hardware; non-Windows targets MANUAL-PENDING |
| `docs/CURRENT_STATE.md:407-497` (grep hits) | constraints: no push/visibility change/collaborator invite/release upload without owner authorization; manual/hardware acceptance pending; no platform support claimed |
| `docs/PRIVATE_BETA_RUNBOOK.md:24-40` | forbidden actions G-1..G-10; no configured remote/private repo |
| `docs/product-blueprint/INDEX.json` | NL-BP-063 blocked (SH-07 Tier B); 152-165 partial/MANUAL-PENDING; 164/165 partial; 197/198 planned |

**Conclusion:** acceptance evidence and authorization gates exist, but there is no explicit recorded **publication readiness verdict** with a hard external-acceptance gate that must stay "not ready" while MANUAL-PENDING items remain, plus authorization/residual-risk sign-off.

## 4. Directive capabilities vs current state

| Directive capability | Exists today? | Comment |
|---|---|---|
| Final repository/distribution readiness milestone with full audit/refactor scope and BEFORE/AFTER deliverable | **No (components only)** | per-domain audits (090/095/096), root-reorg report and release acceptance exist; no integrated milestone producing exact move/delete/consolidation report + disk/Git-history analysis + security/licensing + regression/packaging + readiness verdict |
| Mandatory blocking pre-push secrets/content scan gate | **Partial** | NL-BP-162 scanner covers tracked files + history with exit-code gate, but no hook/CI enforcement, no staged-mode, no fail-closed mandatory policy; runbook is manual |
| Publication readiness verdict + external-acceptance gate | **No** | acceptance matrix/manual-pending + owner gates exist; no verdict artifact/sign-off; release acceptance is PARTIAL |
| Source repo vs local workspace vs distributable app separation | **Partial** | root reorg/.workspace/ allowlist + source-vs-binary requirement 197 planned; not consolidated into final readiness evidence |
| No deletion of protected/user/model/runtime/evidence/stale candidates without authorization | **Yes (policy)** | REPOSITORY_STRUCTURE / runbook G-8 / da_eliminare rules; retained unchanged |
| Code removal only after dependency analysis + regression | **Policy only** | no final readiness milestone enforcing this sequence |

## 5. Dedupe mapping (directive sub-capability -> existing ID / new ID)

| Sub-capability | Existing coverage | New requirement | Decision |
|---|---|---|---|
| Repository hygiene/distribution audits (read-only) | NL-BP-090/091/095 verified; 092/093/094/096/097 partial | NL-BP-234 | 234 integrates them into a final readiness milestone; no individual requirement rewritten |
| Final integrated readiness milestone + BEFORE/AFTER report + exact moves/deletes/consolidations + disk/Git-history analysis + security/licensing + regression/packaging + verdict | - (per-domain reports only) | NL-BP-234 | genuinely new program-level deliverable |
| Duplicate runtimes/models/assets/dependencies, build/cache/logs/dev data | NL-BP-096/094/097, NL-BP-121/122/124 | NL-BP-234 | subtasks covered, integrated analysis/refactor plan new |
| Distribution allowlist/package/launchers/installer | NL-BP-110-124, 149, 195-197 | NL-BP-234 | integration/readiness verdict new; requirements retained |
| Publication constraints / owner gates / no deletion of protected assets | NL-BP-163 (partial), 092/093/094 | - | policy retained; 234 must respect, not duplicate |
| Pre-push secrets/content scan tooling | NL-BP-162 **verified** (tracked+history+bounded+redacted+exit-code) | NL-BP-235 | 162 retained as scanner; 235 adds mandatory blocking hook/CI/staged gate |
| Staged changes scan + fail-closed blocking + never deferred + never pushes | - | NL-BP-235 | genuinely new enforcement layer |
| Secrets/history audit evidence at final HEAD | NL-BP-162 + docs/SECRETS_AUDIT.md | NL-BP-235/236 | rerun at final HEAD becomes mandatory gate evidence |
| Owner authorization gates (push/visibility/upload/history) | NL-BP-163 partial + PRIVATE_BETA_RUNBOOK G-1..G-10 | NL-BP-236 | retained; 236 adds verdict/sign-off artifact |
| Acceptance matrix / readiness labels | NL-BP-140 verified, NL-BP-198 planned | NL-BP-236 | matrix retained; explicit publication verdict + external-acceptance gate new |
| Real hardware/clean-machine/CI/beta external acceptance | NL-BP-152-165 (partial/MANUAL-PENDING) | NL-BP-236 | must remain a blocker for any ready verdict; no duplication |
| Source-vs-binary release separation / public repository readiness | NL-BP-197 planned | NL-BP-234/236 | consumed by final milestone/verdict; retained |
| Cleanup/refactor execution (structure, obsolete code, temp, redundant components) | NL-BP-094/095 partial + root reorg implemented | NL-BP-234 | broader final refactor with authorization/regression gates is new |
| Protected assets (data/models/runtime/evidence/stale candidates) | NL-BP-092/093/094/163 | - | retained policy; 234 must not duplicate authorization |

## 6. New requirements registered (status planned, program stage 10)

| ID | Priority | Area | Dependencies | Summary |
|---|---|---|---|---|
| NL-BP-234 | P0 | hygiene | 090, 095, 096, 110, 140, 149, 162, 197, 198 | Final repository/distribution readiness milestone: full audit and, where justified, refactor/consolidation of structure/root/obsolete/temp/redundant components; dependencies/runtimes/compatibility/licensing; shared-vs-duplicated models/env/assets; build/cache/logs/dev data; packaging allowlist/launchers/installer; tracked files/history/large blobs/credentials/personal paths; docs (README/contributor/platform/troubleshooting/limitations/release notes); cross-platform reproducibility/real-machine acceptance; BEFORE/AFTER tree + exact move/delete/consolidation report + disk & Git-history analysis + security/licensing audit + full regression/packaging results + public-source/beta readiness verdict with blockers; source repo/local workspace/distributable app separated; no deletion of protected/user/model/runtime/evidence/stale candidates without authorization; code removal only after dependency analysis + regression |
| NL-BP-235 | P0 | release | 162, 163 | Mandatory blocking pre-push secrets/content scan gate: CLI + Git hook/CI, staged+tracked+history scan for credentials/tokens/secrets, private data, personal paths/sensitive config, embedded runtimes/vendor/large blobs/dev data; fail closed with redacted findings; runnable before ANY public upload, never deferred; never pushes/publishes |
| NL-BP-236 | P1 | release | 140, 162, 163, 164, 165, 197, 198 | Publication readiness verdict + external-acceptance gate: evidence-backed public-source/beta-release decision with explicit blockers; no ready verdict while external acceptance unresolved/unverified; authorization + residual-risk sign-off recorded |

## 7. Blockers, risks and human/external decisions

- **Stage 10 pending** and depends on stages 6,7,8,9; several of those are in progress/pending. No stage status was changed by this import.
- **Publication remains forbidden without explicit owner authorization** (NL-BP-163/PRIVATE_BETA_RUNBOOK G-1..G-10); the repository has no configured remote; nothing in the queued requirements authorizes push/publish.
- **Real external acceptance remains MANUAL-PENDING**: real hardware, clean machines, actual GitHub CI execution, non-Windows builds and beta tester records (152-165/164/165). No publication-ready verdict may be recorded while those are unresolved (NL-BP-236).
- **Secrets audit must be re-run at final HEAD** - the committed docs/SECRETS_AUDIT.md snapshot was measured at HEAD 259eda5 and states it must be repeated; the bounded scan cannot prove absence of custom/obfuscated secrets, LFS/submodules or deep history. The blocking gate must fail closed and never publish the finding contents.
- **No deletion without authorization** of user data, live SQLite/mission history, `python/` runtime, `data/`, `da_eliminare/crewAI`, models, evidence, backups or stale release candidates (092/093/094/163; REPOSITORY_STRUCTURE).
- **SH-07 Tier B (NL-BP-063) stays BLOCKED**; no final readiness verdict can ignore it.
- **Code removal only after dependency analysis + regression**, and in a separate authorized scope; 234 must not silently refactor during a readiness audit.
- **No git-history rewrite** without a verified backup and explicit owner authorization (runbook G-7); a leaked secret found in history is presumed compromised and rotation is required.
- **CI wiring lands only when a real CI runner executes**; local static tests are not GitHub CI evidence (existing NL-BP-165 constraint).

## 8. Verification commands used (read-only; no model/network/publish)

- `cmd /c findstr` / file reads over `scripts/audit_release_secrets.py:108-1334`, `scripts/audit_repository_hygiene.py:3-6,1459-1466,1656-1666`, `scripts/release_acceptance.py:45-333`, `scripts/rehearse_release.py`, `scripts/build_beta_packages.py`, `scripts/audit_distribution.py`.
- Docs read: `docs/SECRETS_AUDIT.md:1-29,128-147`, `docs/PRIVATE_BETA_RUNBOOK.md:1-79`, `docs/RELEASE_ACCEPTANCE.md:1-63,220-243`, `docs/BETA_ACCEPTANCE.md:1-29`, `docs/REPOSITORY_HYGIENE.md:1-18`, `docs/REPOSITORY_HYGIENE_FOLLOWUP.md:1-33`, `docs/REPOSITORY_STRUCTURE.md`, `docs/ROOT_REORGANIZATION_REPORT.md:1-60`, `docs/CURRENT_STATE.md` (publication/acceptance constraints), `docs/history/legacy/INDEX.md`.
- Config state: `git remote -v` (empty), `git config --get core.hooksPath` (unset), `.git/hooks` listing (only *.sample), `.github/workflows/ci.yml` job list (no secrets-audit step).
- `docs/product-blueprint/INDEX.json` statuses for 090-097, 110-124, 140-165, 162/163, 195-198 and the blocked NL-BP-063.
- No script, test, model, mission, network, push or publish operation was executed.

## 9. Change record

New documentation file and the queue-only backlog update it justifies. The preserved addendum bundle under `docs/product-blueprint/addenda/` is unchanged. No application code, tests, configuration, Git remote/hooks, models, missions or network state were changed, and no commit was created by this task.

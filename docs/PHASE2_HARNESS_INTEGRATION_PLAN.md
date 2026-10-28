# Phase 2 - Implementation Plan: wire the audited Safety Foundation Patch into the real runtime

**Type:** design only. This document changes no tracked file and the PATCH is **not** applied yet.
**Repo:** K:\AI\NL Coding Agent. Design started at git `c10e769`; the Lead's relocation commit `6cfacfa` landed during design and every anchor below was measured at `6cfacfa`. After the Lead's final relocation gate the repo HEAD is `338def0` (relocation P0 verified, gate 30/30 PASS): re-check the anchors at `338def0` before editing (function names, not line numbers, are authoritative).
**Gate:** task-6 is still blocked by task-4 (relocation verification). This document is the mechanical implementation specification for task-6.
**Author:** harness-architect (phase 2), 2026-10-28.
**Constraints honored:** no tracked-file edits, no self-build/autonomous mission, no run of the root unsafe `tests/test_staging_broker_adversarial.py`, no patch application. All prototypes ran under the user temp directory; the live repo stayed `git status` clean after every prototype.

---

## 0. Executive summary

The audited Safety Foundation Patch (`PATCH/**`, hash-certified by `SHA256_MANIFEST.json`) is **not wired** into the runtime:

- the runtime still imports the old, weaker modules at the root paths;
- no model-facing write goes through staging (tools are bound to the live root at `orchestrator.py:631` and `:799`);
- `recovery_store` is imported at `selfbuild_runner.py:12` but has **no call site**;
- `code_integrity_gate.detect_stub` is used only *after* the mission already reported `completed` (`selfbuild_runner.py:308`), and `selfbuild_runner.py:310` rewrites a live source file directly;
- scope violations are detected only *after* files are already modified (`orchestrator.py:676-682`, `:837-842`).

Phase 2 turns the audited modules into the **single write path** of a mission and makes `completed` impossible without an independently verified, compare-and-swap-promoted candidate.

Top five design decisions (full rationale in sections 2-5):

1. **Model tools are bound to a staged workspace, never to the live project root.** `get_project_tools(stage.workspace)` for developer and debugger; `_apply_text_actions(stage.workspace, output)` for the text fallback. The generic `run_command` and `run_tests` tools are **removed** from the model-facing set: both are arbitrary code execution (pytest imports and runs candidate code), and there is no OS sandbox (SPEC-28 SH-05 note). The model sees exactly `read_file`, `write_file`, `patch_file`, `list_dir`.
2. **Promotion is the last gate, not the first.** New order: `STAGED -> VALIDATED (AST/stub/scope) -> VERIFIED (independent regression on candidate) -> REVIEWED (LLM) -> PROMOTED (recovery point + journal + CAS) -> COMPLETED (SQLite)`. The reviewer sees the *candidate* diff before promotion; a REJECT leaves the live tree byte-identical.
3. **Independent verification runs in two disposable copies of the staged workspace:** a *candidate* copy (candidate source + candidate tests) and an *oracle* copy (candidate source + **baseline pinned tests**). Both must pass. The oracle copy defeats exactly the real incident class of missions #42/#43 (green weakened tests, broken feature); this was proven with a prototype (candidate green, oracle red).
4. **The live tree is protected by an explicit recovery point and compare-and-swap.** `save_snapshot(mission_id, delta, root=project_root, recovery_dir=<app-data>/recovery)` is taken after all gates pass and immediately before the first live write; `promote_staged` performs per-file CAS plus a journal; on failure only files whose current bytes equal the recorded post-image are restored (`rollback_from_snapshot(..., expected_post_hashes=...)`), never a guess, never a human edit.
5. **Crash safety is a first-class state: a promotion journal blocks resume until reconciled.** `reconcile()` classifies each journal file as `before`/`after`/`conflict`. All-after means promotion had completed (finalize without re-running models); all-before means safe retry; mixed means automatic CAS rollback of after-files, then retry or `rollback-conflict` blocked. The mission `status` becomes `completed` only in the finalize step after promotion is confirmed; every gate failure becomes `blocked`, never `completed`/`APPROVE`.

**The hard-problem answer in one line:** run the repo pytest suite with the real embedded interpreter in a disposable ~1.3 MB copy of the staged workspace, `cwd=<copy>`, `NL_DATA_DIR=<throw-away dir>`, `QT_QPA_PLATFORM=offscreen`, `-p no:cacheprovider`: once with the candidate tests, once with the baseline tests overlaid on the candidate source (oracle). No `python/`, `crewAI/`, `dist/`, or `data/` copy is ever made (measured: 182 files / 1.32 MB, about 14 s per suite).

---

## 1. Baseline facts (read-only evidence)

### 1.1 Repository state

| Item | Value |
|---|---|
| git HEAD | `6cfacfa` "fix(relocation): durable project provenance and accurate migration record" at design time; final verified HEAD is `338def0` (Lead relocation gate 30/30 PASS) |
| dirty files | none (`git status --porcelain` empty) |
| live pytest baseline | 97 tests collected at HEAD; in a staging-shaped copy 96 pass and 1 fails (root `tests/test_rollback_stub.py` needs `data/mission_baselines/42.json`, which a staging copy correctly does not contain; this file is replaced by the PATCH) |
| missions DB | 1 project (id=1, root K:\AI\NL Coding Agent), 45 missions: 13 completed, 2 blocked (#44, #45), 1 interrupted (#5), 29 pending (mostly legacy "Self Build Test" rows) |
| data/ size | 16.1 MB total: mission_baselines 14.4 MB (15 files, 0.91-1.28 MB each), backups 1.1 MB, recovery 1 file, staging leftover `data/staging/999` (old unsafe test artifact) |
| vendor trees | `python/` 1.64 GB, `crewAI/` 467 MB, `dist/` 1.44 GB - none of this is ever copied by the new verification environment |

### 1.2 Measured prototypes (all under the temp directory; live repo untouched)

| Prototype | Result |
|---|---|
| source-only copy of the repo (exclude `.git`, `python`, `crewAI`, `crewAI-tools`, `dist`, `build`, `data`, `logs`, `state`, `PATCH`, caches) | **182 files, 1.32 MB** |
| full pytest in that copy with embedded `python\python.exe` and `NL_DATA_DIR=<temp>` | **13.5 s**; 93 passed, 1 failed (the old rollback test's `data/` dependency) |
| PATCH applied in the same copy (PATCH tests included), full pytest | **13.8 s**; 103 collected, **102 passed, 1 failed** - a Windows newline bug in `PATCH/tests/test_rollback_stub.py` (section 4.7) |
| `stage_candidate` on the real-size tree (181 baseline files, 2-path scope) | **0.59 s**; `manifest.json` **1.47 MB**; workspace 181 files |
| `validate_candidate` -> `mark_verified` -> `save_snapshot` -> `promote_staged` -> rollback | all successful; 2-file recovery point **18 KB**; journal created and deleted correctly; live file restored byte-identically |
| oracle-overlay prototype (bug in source + weakened test) | candidate suite **green**, oracle suite **red** -> independent verification catches exactly the missions #42/#43 failure class |
| CRLF probe through the model-tool path | model-tool writes are **CRLF on Windows**, while broker hashes are LF-normalized -> promotion would write CRLF and recovery CAS would refuse to roll back; a normalization step is mandatory (section 4.7) |

### 1.3 PATCH status (from `build/relocation/patch_integration.md`, re-checked)

- `SHA256_MANIFEST.json`: 5/5 PATCH files match; root counterparts are older/unsafe.
- Runtime imports: `staging_broker` **not imported anywhere**; `recovery_store` imported in `selfbuild_runner.py:12` but never called; `code_integrity_gate.detect_stub` used only post-hoc at `selfbuild_runner.py:308`; `detect_weak_test` imported but unused.
- Model write path today: `crew_tools` -> `filesystem.scoped_write_file/scoped_patch_file` -> live file; scope is checked only *after* the writes.

---

## 2. Target architecture

### 2.1 Component map

~~~text
                      +-----------------------------------------------------------+
                      | MultiAgentOrchestrator (CHG)                              |
                      |  run_mission / _run_locked / _run_*_stage / _call_model   |
                      +-------+-------------------------------+-------------------+
                              | staged tools                  | policy / DB / events
            +-----------------v--------------+   +------------v-------------------+
            | tools/crew_tools (CHG)         |   | persistence.missions (CHG)     |
            |  get_project_tools(workspace)  |   |  harness_version, staging_dir, |
            |  4 tools, no shell / no tests  |   |  promotion_status              |
            +-----------------+--------------+   +------------+-------------------+
                              | writes                    |
            +-----------------v---------------------------v-----------------------+
            | core/promotion.py (NEW) - candidate lifecycle, DB-free                |
            |  begin/load/derive_scope/normalize/validate/recovery point/           |
            |  mark_verified/promote(journal+CAS)/reconcile/rollback/discard         |
            +------+--------------------------+-------------------------+-----------+
                   | uses                     | uses                    | uses
     +-------------v-----------+  +---------v--------------+  +-------v------------------------+
     | core/staging_broker.py  |  | core/recovery_store.py |  | core/candidate_verification.py |
     | PATCH v2, applied       |  | PATCH v2, applied      |  | NEW: disposable copies,        |
     | stage/validate/promote  |  | snapshot/rollback CAS  |  | candidate+oracle pytest,       |
     | journal/mark_verified   |  | atomic write           |  | junit, env scrub, timeouts     |
     +-------------------------+  +------------------------+  +--------------------------------+
                   |
     +-------------v----------------+   +------------------------------------------+
     | core/code_integrity_gate.py  |   | core/workspace.py (unchanged)             |
     | PATCH v2, AST stub/weak-test |   | snapshot / diff / scope primitives        |
     +------------------------------+   +------------------------------------------+
~~~

### 2.2 Mission state machine (mapping to SPEC-28 section 4)

~~~text
READY -> BASELINED -> STAGED -> VALIDATING -> VERIFIED -> REVIEWED -> PROMOTING -> PROMOTED -> COMPLETED
                         |                        |
                         +-- FAIL -> REPAIRING ---+ (bounded, max NL_MAX_REPAIRS=2)
                         |               |
                         +-- budget out -> BLOCKED (stage retained)      PROMOTING --(journal)--> reconcile
                                                                          reconcile -> PROMOTED | ROLLED_BACK | BLOCKED_ROLLBACK_CONFLICT
~~~

Durable markers:

| Phase | Carrier | Value |
|---|---|---|
| BASELINED | `data/mission_baselines/<mission_id>.json` (existing) | live text snapshot at mission start |
| STAGED | `missions.staging_dir` + `data/staging/mission-<id>-xxxx/manifest.json` | stage dir path, baseline, scope |
| VALIDATING | manifest `validated` | true/false |
| VERIFIED | manifest `verified` + `evidence` | only after candidate+oracle pass |
| REVIEWED | handoff `reviewer -> orchestrator` payload verdict | APPROVE/REJECT |
| PROMOTING | `missions.promotion_status='promoting'` + `promotion-journal.json` | files + before/after hashes |
| PROMOTED | manifest `promoted` + live CAS-verified hashes | durable after last write |
| COMPLETED | `missions.status='completed'` via `_finalize_completed` | final DB write |

### 2.3 End-to-end data flow (one mission)

1. `run_mission` acquires `mission_lock`, `mark_mission_started`.
2. Plan tasks (unchanged), save the live mission baseline (unchanged).
3. **Create or reload the stage**: `stage_candidate(project_root, mission_id, scope)`; `missions.staging_dir` set; `promotion_status='staged'`; handoff `orchestrator -> developer`.
4. **Reconcile** any leftover journal / already-promoted state before running any model (see section 5.4).
5. **Developer stage**: tools and text fallback write **only inside** `stage/workspace`; then `normalize_staged_newlines`, `validate` (scope + AST stub + weak test + policy deny list); on success `promotion_status='validated'`; no live write.
6. **Tester stage**: re-validate after each repair; run `candidate_verification.verify_candidate` (candidate + oracle suites in disposable copies); on pass `mark_verified(stage, passed=True, evidence=...)` binds the exact staged hashes; `promotion_status='verified'`.
7. **Debugger** (bounded): repairs only the stage; tester loop re-validates and re-verifies; budget `NL_MAX_REPAIRS`.
8. **Reviewer stage**: receives the candidate diff (baseline vs staged) plus validation/verification evidence; verdict APPROVE/REJECT. REJECT -> blocked, live untouched.
9. **Promotion** (only after APPROVE): preflight live CAS -> save recovery point -> set `promotion_status='promoting'` -> `promote_staged` (journal + per-file CAS + atomic writes) -> `promotion_status='promoted'`; handoff with promoted paths and hashes.
10. **Finalize**: the single writer of `missions.status='completed'`; then evidence retention and stage cleanup.
11. Any gate failure: `blocked` plus a reason code; stage kept for inspection; no live file modified (unless failure happened mid-promotion, in which case section 5 applies).

### 2.4 Artifacts and where they live

| Artifact | Location | Owner | Cleanup |
|---|---|---|---|
| staged candidate workspace | `<project_root>/data/staging/mission-<id>-xxxxx/` (PATCH semantics) | promotion.py | discarded after terminal status; swept if orphaned |
| stage manifest (baseline + hashes) | same dir, `manifest.json` (about 1.5 MB) | staging_broker | same |
| promotion journal | same dir, `promotion-journal.json` | staging_broker | deleted only after successful promote or proven reconciliation |
| verification copies + junit | `<stage_dir>/verification/{candidate,oracle,data,evidence}/` | candidate_verification.py | removed right after the report is persisted |
| recovery point (pre-images) | **app data** `<db_path().parent>/recovery/<mission_id>.json` | recovery_store | retained (SPEC-02A policy); not in the user project |
| verification evidence record | **app data** `<db_path().parent>/verification/mission-<id>.json` | promotion.py | retained (small) |
| mission baseline | `<db_path().parent>/mission_baselines/<id>.json` (existing) | orchestrator | existing behavior (P1 retention) |
| DB state | `missions.harness_version / staging_dir / promotion_status`, `verification_runs`, `handoffs`, `events` | persistence | existing |

**Known deviation (open question R1):** the audited `stage_candidate` hard-codes `<project_root>/data/staging`, so staging artifacts appear inside a target project. That is acceptable for NL Coding Agent itself (`data/` is gitignored) and is documented/cleaned for external projects; moving staging to an app-owned root would require a broker API change and re-audit.

### 2.5 Security boundaries (be explicit, do not overclaim)

- The broker protects **text edits made through the tool layer**; it does not sandbox arbitrary code. Verification runs candidate tests, i.e. candidate code executes with user privileges. This is inherent to any pytest-based gate; mitigations are: no shell/test tool exposed to the model, disposable copy, scrubbed env, `NL_DATA_DIR` redirect, cwd = copy, timeout, no live write before promotion.
- Deletes are refused by the broker for unattended missions (existing PATCH behavior).
- Symlinks are refused on stage/promote paths (PATCH `_safe_path`).
- Windows byte/text newline semantics required an integration normalization step (section 4.7); this is a real gap in the audited PATCH, not a hypothetical.

---
## 3. File-by-file change list

### 3.0 Change map (commit per row, details in section 9)

| # | File | Action | Commit |
|---|---|---|---|
| 1 | `PATCH/nl_coding_agent/core/staging_broker.py` -> `nl_coding_agent/core/staging_broker.py` | replace with audited v2 | C1a |
| 2 | `PATCH/nl_coding_agent/core/recovery_store.py` -> root path | replace with audited v2 | C1a |
| 3 | `PATCH/nl_coding_agent/core/code_integrity_gate.py` -> root path | replace with audited v2 | C1a |
| 4 | `PATCH/tests/test_staging_broker_adversarial.py` -> root path | replace unsafe live-repo test with isolated temp-dir test | C1a |
| 5 | `PATCH/tests/test_rollback_stub.py` -> root path | replace real-repo read test with isolated recovery test (+Windows newline fix) | C1a/C1b |
| 6 | `nl_coding_agent/core/promotion.py` | **new** candidate lifecycle / gate orchestration | C3 |
| 7 | `nl_coding_agent/core/candidate_verification.py` | **new** hermetic independent verification | C4 |
| 8 | `nl_coding_agent/tools/crew_tools.py` | remove generic shell + run_tests + git_diff; keep 4 tools | C2 |
| 9 | `nl_coding_agent/tools/filesystem.py` | write LF bytes explicitly (2 write functions) | C2 |
| 10 | `nl_coding_agent/agents/orchestrator.py` | staged pipeline, verification, review-before-promote, DB sequencing, `_call_model` seam | C2/C6a-c |
| 11 | `nl_coding_agent/core/selfbuild_runner.py` | delete post-hoc gate; preflight; legacy mission guard | C7 |
| 12 | `nl_coding_agent/persistence/database.py` | additive migrations (3 columns) | C5 |
| 13 | `nl_coding_agent/persistence/missions.py` | harness/staging/promotion helpers + harness-aware creation | C5 |
| 14 | `nl_coding_agent/cli.py` | legacy resume refusal, preflight messages, optional abandon-stage | C6c/C7 |
| 15 | `tests/**` | see section 7 | all |
| 16 | `SHA256_MANIFEST.json`, `docs/07_SAFETY.md`, `docs/CURRENT_STATE.md`, `docs/02_SELF_BUILD_ROADMAP.md`, `docs/product-blueprint/specifiche/28_SELF_HEALING_AGENT_HARNESS.md` | manifest re-cert + docs after wiring is real | C1b/C8 |

No other runtime file writes to the live tree after this change set: verify with the static checks in section 9 (acceptance commands).

---

### 3.1 Apply the five audited files (C1a)

Mechanical: copy each `PATCH/<path>` over `<path>` byte-for-byte, verify SHA-256 against `SHA256_MANIFEST.json`, commit the five files only (no other edits). Do **not** touch the root unsafe tests before the replacement is in the same commit - they are replaced by the PATCH test files.

Verification at this point (measured on a temp copy at HEAD):

- `tests/test_staging_broker_adversarial.py`: 7 tests, all pass;
- `tests/test_rollback_stub.py`: 3 tests, 2 pass, 1 fails on Windows (section 4.7);
- full suite: 103 collected, 102 pass, 1 fail (the same newline bug).

**C1b (separate, auditable commit):** fix the PATCH test's Windows newline bug without changing the audited library modules. Minimal diff: in `tests/test_rollback_stub.py` write fixture text with explicit LF, e.g. a local helper

~~~python
def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")
~~~

and use it for both writes; update the manifest hash of that test file; add a one-paragraph re-audit note in `build/phase2/PATCH_WINDOWS_REAUDIT.md` (design record) and in the C1b commit message. After C1b the full suite is 103/103 green (measured semantics; the newline probe with `newline=""` passed).

Do not change `recovery_store.py`, `staging_broker.py`, or `code_integrity_gate.py` in C1b: their hashes stay as certified.

---

### 3.2 `nl_coding_agent/core/staging_broker.py` - applied as-is, integration constraints

Contract used by the integration (do not modify the module):

- `stage_candidate(project_root, mission_id, scope_paths) -> Path`: creates `<root>/data/staging/mission-<id>-<rand>/workspace`, writes baseline text snapshot, `manifest.json` v2 with `project_root, scope, baseline, validated, verified, changed`.
- `validate_candidate(stage_dir, baseline_path=None, scope_paths=None) -> dict`: returns `{valid, errors, changed_paths, unauthorized, stub_files, weak_tests}`; refuses deletes, out-of-scope, protected roots, stubs, weakened tests; writes `validated`, `changed`, `verified=False` into the manifest.
- `mark_verified(stage_dir, *, passed, evidence) -> None`: raises `StagingRejected` unless validated+passed+non-empty evidence; re-hashes the staged workspace and raises if any changed file moved since validation; writes `verified=True`, `evidence`.
- `promote_staged(stage_dir, project_root) -> {promoted, blocked, reason}`: refuses unless validated+verified, refuses if a journal exists, full preflight CAS on every destination, writes `promotion-journal.json`, then per-file CAS + `_atomic_write`; deletes journal; sets `promoted=True`.
- `rollback_from_staged(stage_dir, project_root, baseline_path=None) -> {restored, blocked, reason}`: stage-local rollback; only restores when live hash equals recorded `after`; preserves human edits as `blocked`.

Integration constraints discovered (important, all measured):

1. **Newline semantics:** all broker hashes are `sha256_text` of text read with universal-newline translation; staged file *bytes* on Windows come from `Path.write_text` (CRLF by default). The integration must normalize staged bytes to LF before validate/mark/promote and must verify `sha256_bytes(staged_bytes) == delta[rel]["after"]` before promotion (section 4.7).
2. **Staging lives under the project root** (see R1).
3. Broker imports the private `recovery_store._atomic_write`; the two modules must be applied together (they are, in C1a).
4. `promote_staged` does **not** re-verify after mark; the CAS check on the staged file (`current_candidate == after`) is the second line of defense. Our `assert_byte_hash_invariant` is the third.

---

### 3.3 `nl_coding_agent/core/recovery_store.py` - applied as-is, integration constraints

- `save_snapshot(mission_id, scope_paths, root=".", *, recovery_dir=None) -> Path`: v2 payload with `before_sha256` + `before_hex` per file; refuses overwrite of an existing recovery point, symlinks, non-files, files > 1 MB; default dir `<root>/data/recovery`.
- `rollback_from_snapshot(rollback_path, files_to_check, *, expected_post_hashes=None, project_root=None) -> {restored, blocked, reason}`: restores only when current raw-bytes hash equals the caller-supplied post-image hash (or file is already at before); no post-image means blocked; preserves human edits.
- **Integration rule:** runtime always passes an explicit `recovery_dir = <db_path().parent>/recovery` (app-owned; avoids writing into external projects) and always passes `expected_post_hashes` computed from the *staged bytes that were actually promoted* (`sha256_bytes`), not from the current file. Because of the normalization invariant in section 4.7, those hashes equal the broker's `delta[rel]["after"]` text hashes; the promotion preflight asserts that equality.
- Existing-file policy: because `save_snapshot` refuses overwrite, the integration adds `ensure_recovery_point()` (in `promotion.py`) that reuses a matching existing point (same root, same before-hashes) instead of failing a retried promotion; a mismatching existing point is a hard conflict.

---

### 3.4 `nl_coding_agent/core/code_integrity_gate.py` - applied as-is, usage rules

- `detect_stub(content, baseline=None)`: invalid Python, vanished public defs, body reduced to `pass`/`...`/`raise NotImplementedError`, >70% shrink.
- `detect_weak_test(baseline, current)`: removed test function, or every test body is only `assert True`.
- Used **only** through `validate_candidate`; the integration never calls them directly (single gate, one policy). This also removes the current post-hoc `detect_stub` usage in `selfbuild_runner.py`.

---

### 3.5 NEW `nl_coding_agent/core/promotion.py` (C3)

DB-free, model-free, deterministic; everything is testable with temp directories. Module docstring must state: "no live write without verified candidate + recovery point + journal".

~~~python
"""Mission-scoped candidate lifecycle: stage -> validate -> verify -> promote.

Fail-closed: the only code path that writes to the live project is
promote(), which requires validation, independent verification, a recovery
point and a compare-and-swap preflight.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from nl_coding_agent.core.recovery_store import (
    _atomic_write, rollback_from_snapshot, save_snapshot, sha256_bytes, sha256_text,
)
from nl_coding_agent.core.staging_broker import (
    StagingRejected, mark_verified as _broker_mark_verified, promote_staged,
    rollback_from_staged, stage_candidate, validate_candidate,
)
from nl_coding_agent.core.workspace import diff_snapshots, diff_stats, snapshot_workspace

HARNESS_VERSION = 2
PROMOTION_JOURNAL = "promotion-journal.json"
MAX_ROLLBACK_FILE_BYTES = 1_000_000
PROTECTED_DELTA_PREFIXES = (
    "python/", "crewai/", "crewai-tools/", ".git/", "data/", "logs/", "state/",
    "dist/", "build/", "patch/",
)
PROTECTED_DELTA_FILES = ("SHA256_MANIFEST.json", "FOUNDATION_CHANGES.patch")
MISSION_INPUT_DENY = ("docs/NEXT_SELF_BUILD_MISSION.md",)


class PromotionError(RuntimeError):
    """Base class for candidate-lifecycle failures."""


class GateFailure(PromotionError):
    def __init__(self, message: str, *, code: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class Stage:
    mission_id: int
    project_root: Path
    stage_dir: Path
    scope: tuple[str, ...]

    @property
    def workspace(self) -> Path: return self.stage_dir / "workspace"

    @property
    def manifest_path(self) -> Path: return self.stage_dir / "manifest.json"


# ---- loading / creation -------------------------------------------------------
def begin_stage(project_root: Path | str, mission_id: int, scope_paths: list[str]) -> Stage
def load_stage(stage_dir: Path | str) -> Stage
def find_stage(project_root: Path | str, mission_id: int) -> Stage | None
def derive_scope(project_root: Path | str, write_paths: list[str]) -> list[str]
def read_manifest(stage: Stage) -> dict
def _save_manifest(stage: Stage, manifest: dict) -> None

# ---- staged delta / policy ----------------------------------------------------
def candidate_snapshot(stage: Stage) -> dict[str, str]
def candidate_delta(stage: Stage) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, str | None]]]
def candidate_diff(stage: Stage) -> tuple[str, list[str], str]
def normalize_staged_newlines(stage: Stage) -> list[str]
def check_delta_policy(stage: Stage, *, deny_paths: list[str] = ()) -> list[str]
def validate(stage: Stage, *, deny_paths: list[str] = ()) -> dict
def assert_byte_hash_invariant(stage: Stage) -> None

# ---- live-tree safety ---------------------------------------------------------
def check_live_drift(stage: Stage) -> list[str]
def ensure_recovery_point(stage: Stage, recovery_dir: Path | str | None = None) -> Path
def mark_verified(stage: Stage, *, passed: bool, evidence: str) -> None
def promote(stage: Stage, *, recovery_dir: Path | str | None = None) -> dict
def is_live_promoted(stage: Stage) -> bool
def reconcile(stage: Stage, *, recovery_dir: Path | str | None = None) -> dict
def rollback(stage: Stage, *, recovery_dir: Path | str | None = None) -> dict

# ---- evidence / cleanup -------------------------------------------------------
def evidence_payload(stage: Stage, *, status: str, verification: dict | None = None,
                     extra: dict | None = None) -> dict
def retain_evidence(evidence_dir: Path | str, payload: dict) -> Path
def discard_stage(stage: Stage) -> None
def cleanup_after_terminal(stage: Stage, *, mission_status: str,
                           evidence_dir: Path | str | None = None,
                           verification: dict | None = None) -> None
def sweep_stale_stages(project_root: Path | str, *,
                       mission_lookup: Callable[[str], dict | None],
                       retention_days: int = 7,
                       now: float | None = None) -> list[str]
def preflight(project_root: Path | str, *,
              mission_lookup: Callable[[str], dict | None]) -> list[str]
~~~

Function behavior (implementation notes, all mechanical):

- `begin_stage`: calls `stage_candidate`, then `load_stage`; refuses (GateFailure `scope`) if `scope` empty.
- `load_stage`: reads manifest, verifies `manifest["version"] == 2`, returns `Stage(mission_id=<parsed from dir name or manifest? -> store mission_id in manifest via a sidecar? no: parse "mission-<id>-" prefix>`, `project_root`, `stage_dir`, `scope=tuple(manifest["scope"])`). **Do not modify the broker manifest schema**; the mission id is already in the directory name.
- `find_stage`: glob `<root>/data/staging/mission-<id>-*`, return the single match; >1 -> GateFailure `stage-ambiguous` (fail closed; operator must resolve).
- `derive_scope`: non-empty `write_paths` returned as-is; otherwise fall back to top-level entries of `snapshot_workspace(root)` minus protected prefixes and dot entries; empty -> GateFailure `scope-missing`.
- `candidate_delta`: `baseline = manifest["baseline"]`; `staged = snapshot_workspace(stage.workspace)`; use `diff_snapshots`; the third element is the per-file `{before, after}` sha256_text map (authoritative = same computation the broker does; do not persist it here).
- `candidate_diff`: `diff_snapshots(baseline, staged)`; return `(diff_text, changed_paths, diff_stats(diff))`; used for reviewer prompt and handoffs.
- `normalize_staged_newlines`: for every regular file under `stage.workspace` (skip symlinks), if `b"\r\n" in data` rewrite with `data.replace(b"\r\n", b"\n")` via `path.write_bytes`; return changed relative paths. Idempotent; about 1.3 MB scanned per call.
- `check_delta_policy`: iterate `manifest["changed"]`; error on protected prefixes/files (lower-cased comparison for prefixes), on `deny_paths` (exact or directory prefix), and on absolute/backslash paths. Returns list of errors (never raises).
- `validate`: `verdict = validate_candidate(stage.stage_dir, scope_paths=list(stage.scope))`; append `check_delta_policy(...)` errors; if extras exist, force the manifest back to `validated=False, verified=False` (the broker only knows its own checks) and set `verdict["valid"]=False`; return the enriched dict. The broker's `changed` map is the source of hashes.
- `assert_byte_hash_invariant`: for each `rel, hashes` in manifest `changed`: if the staged file is missing -> GateFailure `byte-invariant`; `actual = sha256_bytes(staged.read_bytes())`; `expected = sha256_text(staged.read_text(encoding="utf-8"))`; raise GateFailure `byte-invariant` unless `actual == expected == hashes["after"]`. This is the Windows CRLF guard.
- `check_live_drift`: for each changed path, compute `sha256_text(live.read_text())` (or None); compare with `hashes["before"]`; return drifted paths.
- `ensure_recovery_point`: if `recovery_dir/<mission_id>.json` exists, load it; accept only if payload `version==2`, `root` matches, and for every changed rel `before_sha256` equals `sha256_bytes(live.read_bytes())` when the live file exists (absolute path check); otherwise GateFailure `recovery-conflict`. If absent, `save_snapshot(mission_id, sorted(delta), root=project_root, recovery_dir=recovery_dir)`. **Called before any live write.**
- `mark_verified`: thin wrapper over the broker function; evidence string is `json.dumps({"candidate": "...", "oracle": "...", "report": "<path>"})` truncated to 2000 chars.
- `promote` (the only live-write path):
  1. manifest must be `validated and verified`; else GateFailure `not-verified`.
  2. `assert_byte_hash_invariant(stage)`.
  3. if `is_live_promoted(stage)` -> return `{"promoted": sorted(delta), "blocked": [], "reason": [], "already": True}` (idempotent resume).
  4. `drift = check_live_drift(stage)`; non-empty -> GateFailure `cas-conflict` with details paths (no recovery point needed yet).
  5. `ensure_recovery_point(stage, recovery_dir)`.
  6. `_save_manifest` unchanged; `promote_staged(stage.stage_dir, stage.project_root)`.
  7. on `StagingRejected` as exc: call `reconcile(stage, recovery_dir=recovery_dir)`; raise GateFailure `promotion-conflict` with reconcile outcome (journal is kept if reconciliation cannot prove safety).
  8. return broker result plus `{"recovery_path": str(path), "hashes": {rel: after}}` so the caller can record evidence.
- `is_live_promoted`: all delta paths exist-or-not exactly as `after` (hash compare, `None` for deleted - deletes are impossible here) and at least one file; returns bool.
- `reconcile` (journal algorithm; callable at resume and after a promotion exception):
  1. `journal = stage.stage_dir / PROMOTION_JOURNAL`; if missing: if `is_live_promoted(stage)` -> `{"state":"promotion-complete","journal":False}`; else `{"state":"no-journal","journal":False}`.
  2. load journal (`changed` map); malformed journal -> `{"state":"conflict","journal":True,"reason":"unreadable journal"}` (never delete a malformed journal automatically).
  3. classify every rel: `current = live hash or None`; `"after"` if `current == after`; `"before"` if `current == before`; else `"conflict"`.
  4. all `after` -> delete journal, return `{"state":"promotion-complete"}` (finalize path; live is complete and byte-correct).
  5. all `before` -> delete journal, return `{"state":"never-promoted"}`.
  6. mixed: `after_files = [rel for after]`; recovery point must exist; `expected = {rel: sha256_bytes((stage.workspace/rel).read_bytes()) for rel in after_files}`; `rollback_from_snapshot(recovery, after_files, expected_post_hashes=expected, project_root=stage.project_root)`; re-read journal delta and re-classify; if every file is now `before` -> delete journal, return `{"state":"rolled-back","restored":after_files}`; otherwise return `{"state":"conflict","blocked":[...],"journal":True}` and **keep the journal**.
  7. `conflict` classification always keeps journal + returns `{"state":"conflict"}` (no writes to conflicting files).
- `rollback`: operator/`GUI path (not used by the automatic mission flow except reconcile): if recovery point exists -> `rollback_from_snapshot(recovery, sorted(delta), expected_post_hashes={rel: after}, project_root=root)`; elif journal exists -> `rollback_from_staged`; else GateFailure `no-recovery-point`.
- `cleanup_after_terminal`: write `<db_path().parent>/verification/mission-<id>.json` (payload from `evidence_payload`), then if `mission_status in {"completed","blocked-review","verification-exhausted"}` and no journal -> `discard_stage`; on conflict statuses keep the stage for manual merge.
- `sweep_stale_stages`: scan `<root>/data/staging/*/manifest.json`; for each, find mission by staging_dir; if mission terminal (completed/failed/blocked/interrupted) or unknown, and no journal, and dir mtime older than `retention_days` -> delete; return removed dirs. Never delete a dir with a journal.
- `preflight`: scan stages for journals; for each journal -> if `mission_lookup(stage_dir)` is missing or mission terminal -> append a blocking message; if mission resumable -> append a "must resume mission #N" message. Return list of messages (empty = safe to start). Never mutate.

---

### 3.6 NEW `nl_coding_agent/core/candidate_verification.py` (C4)

See section 4 for the full environment analysis. API:

~~~python
"""Independent regression verification of a staged candidate (SPEC-28 TestGate)."""
from __future__ import annotations
import json, os, shutil, subprocess, sys, xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ORACLE_TESTS_DIR = "tests"
ORACLE_PINNED_FILES = ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "conftest.py")
ORACLE_PINNED_INPUTS = ("docs/NEXT_SELF_BUILD_MISSION.md",)
RUNNER_NAME = "_pytest_runner.py"
ENV_DROP = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE")
DEFAULT_TIMEOUT_S = 600
RESOLUTION_GUARD_EXIT = 86

@dataclass
class SuiteResult:
    suite: str                 # "candidate" | "oracle"
    command: list[str]
    cwd: str
    exit_code: int | None
    passed: bool
    timed_out: bool
    duration_s: float
    stdout_tail: str
    stderr_tail: str
    failures: list[str]
    junit_path: str | None
    error: str | None = None

@dataclass
class VerificationReport:
    passed: bool
    candidate: SuiteResult
    oracle: SuiteResult
    verify_dir: Path
    started_at: str
    finished_at: str
    oracle_overlay: list[str]
    error: str | None = None

def verify_candidate(stage_workspace: Path, stage_dir: Path, baseline: dict[str, str],
                     *, python_executable: str | None = None,
                     timeout_s: int = DEFAULT_TIMEOUT_S,
                     report_path: Path | None = None) -> VerificationReport
def run_suite(copy_root: Path, *, suite: str, python_executable: str,
              data_dir: Path, timeout_s: int, junit_path: Path) -> SuiteResult
def prepare_copies(stage_workspace: Path, stage_dir: Path,
                   baseline: dict[str, str]) -> tuple[Path, Path, list[str]]
def overlay_oracle(copy_root: Path, baseline: dict[str, str]) -> list[str]
def scrubbed_env(data_dir: Path) -> dict[str, str]
def parse_junit(junit_path: Path) -> tuple[int, int, list[str]]
def cleanup_verification(verify_dir: Path, *, keep: bool = False) -> None
~~~

Control flow of `verify_candidate`:

1. `python_executable = python_executable or sys.executable`.
2. `verify_dir = stage_dir / "verification"`; if it exists from a crashed attempt, remove it first.
3. `prepare_copies`: `copytree(stage_workspace, verify_dir/"candidate")`; `copytree(stage_workspace, verify_dir/"oracle")`; `overlay_oracle(verify_dir/"oracle", baseline)`; create `verify_dir/"data"/"candidate"`, `verify_dir/"data"/"oracle"`, `verify_dir/"evidence"`; write the runner script into each copy root; return paths and overlay log.
4. `candidate = run_suite(copy, suite="candidate", ...)`.
5. `oracle = run_suite(copy_oracle, suite="oracle", ...)` (always run, even if candidate failed, unless candidate timed out; a timeout is already a fail and skipping saves wall time - document the choice).
6. `passed = candidate.passed and oracle.passed and not candidate.timed_out and not oracle.timed_out and not candidate.error and not oracle.error`.
7. write `verify_dir/"evidence"/"report.json"` (dataclass as dict, suite tails truncated to 8 000 chars each, failures list, durations, overlay ops) and copy it to `report_path` if given.
8. do **not** delete the copies here; `cleanup_verification` is called by the orchestrator after persisting evidence (keeps the report file). Any exception -> raise GateFailure-like `VerificationError` from the caller; no partial pass.

Runner script content (generated, deterministic):

~~~python
import sys
from pathlib import Path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
import nl_coding_agent
package = Path(nl_coding_agent.__file__).resolve()
if not package.is_relative_to(root):
    print("FATAL: imported package outside verification copy: " + str(package), file=sys.stderr)
    raise SystemExit(86)
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
~~~

This explicit guard is required because the embedded Python uses a `._pth` file (isolated path handling); it proves the suite ran against the copy rather than the live repo. Exit code 86 = infrastructure failure (report `error`), never a pass.

Run command per suite:

~~~text
<python.exe> <copy>/_pytest_runner.py -q -p no:cacheprovider --no-header
             --junitxml=<verify_dir>/evidence/junit-<suite>.xml tests
cwd = <copy>
timeout = NL_VERIFY_TIMEOUT_S (default 600)
env   = scrubbed (see section 4.4)
~~~

Pass rule per suite: exit code 0 **and** junit exists and `tests>0` **and** no `failure/error` elements. A zero-test run is a failure (protects against a candidate that empties the test tree; the oracle overlay also makes that hard).

`overlay_oracle` (SH-04 protection):

1. `shutil.rmtree(copy_root/"tests")`;
2. for every `rel, content` in `baseline` where `rel == "tests" or rel.startswith("tests/")`: write with `newline=""` under `copy_root/rel`;
3. for every pinned file: if baseline has it -> write with `newline=""`; else unlink candidate copy if present;
4. write pinned inputs (`docs/NEXT_SELF_BUILD_MISSION.md`) from baseline if present;
5. remove any candidate-added `conftest.py` anywhere outside the restored `tests/` tree (walk; unlink when rel not in baseline and rel not a pinned file);
6. return human-readable ops list for the evidence report.

`scrubbed_env`: `{k: v for k, v in os.environ.items() if k not in ENV_DROP}` then `NL_DATA_DIR=<data_dir>`, `QT_QPA_PLATFORM=offscreen`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `PYTHONHASHSEED=0`, `NO_COLOR=1`, `GIT_PAGER=cat`, `PAGER=cat`. Output decoding reuses `nl_coding_agent.tools.shell.decode_output` (Windows OEM fallback already solved there).

`parse_junit`: tolerate missing/failed XML -> return `(0, 0, [])` and the caller's pass rule fails on `tests == 0`.

---

### 3.7 `nl_coding_agent/tools/crew_tools.py` (C2)

Replace the module body with four tools; signatures unchanged where used:

~~~python
def get_project_tools(project_root: Path | str) -> list:
    """CrewAI tools scoped to a project root (in practice: a staged workspace)."""
    root = Path(project_root).resolve()

    @tool("read_file")
    def read_file(path: str) -> str: ...
    @tool("write_file")
    def write_file(path: str, content: str) -> str: ...
    @tool("patch_file")
    def patch_file(path: str, target: str, replacement: str) -> str: ...
    @tool("list_dir")
    def list_dir(path: str = ".") -> str: ...
    return [read_file, write_file, patch_file, list_dir]
~~~

Deleted: `run_command` (arbitrary shell), `run_tests` (runs arbitrary candidate code and, if bound to the live root, bypasses staging entirely), `git_diff` (reads the live tree while tools write the stage - confusing and unnecessary). Imports for `scoped_run_command`, `run_verification`, `get_git_diff`, `get_git_status` are removed from this module. The deterministic tester keeps using `run_verification`/pytest internally (orchestrator code, not a model tool).

Acceptance assertion: `tests/test_operational_tools.py` becomes `assert len(tools) == 4` and `{"read_file","write_file","patch_file","list_dir"} == {t.name ...}`; explicit negative assertions for `run_command`/`run_tests`/`git_diff`; the rest of that file (filesystem/shell unit tests) stays unchanged.

---

### 3.8 `nl_coding_agent/tools/filesystem.py` (C2)

The two writers must stop introducing CRLF on Windows (they write only to staged workspaces after wiring, so this is safe):

~~~python
def scoped_write_file(project_root, rel_path, content) -> str:
    ...
    target.write_text(content, encoding="utf-8", newline="")
    ...

def scoped_patch_file(project_root, rel_path, target_snippet, replacement_snippet) -> str:
    ...
    target.write_text(new_content, encoding="utf-8", newline="")
    ...
~~~

Keep signatures and return strings identical. This is defense-in-depth on top of `normalize_staged_newlines`; unit test `tests/test_operational_tools.py::test_scoped_filesystem_operations` still passes (it asserts text content) and a new assertion checks bytes contain no CRLF.

---

### 3.9 `nl_coding_agent/agents/orchestrator.py` (C2 seam, C6a-c wiring) - detailed

Current anchors (HEAD `6cfacfa`, 962 lines): imports 49-52; `_apply_text_actions` 146-215; class 218; `_check_scope` 350-359; `_finalize` 361-418; `run_mission` 422-480; `_run_locked` 482-609; `_run_developer_stage` 613-719; `_run_tester_stage` 721-788; `_run_debugger` 790-861; `_run_reviewer_stage` 863-962.

#### 3.9.1 Imports and module constants

Add:

~~~python
import os
from nl_coding_agent.core import candidate_verification, promotion
from nl_coding_agent.core.promotion import GateFailure
from nl_coding_agent.persistence.database import db_path
from nl_coding_agent.persistence.missions import (
    ... existing ...,
    set_mission_staging, set_promotion_status, get_task,
)
VERIFY_TIMEOUT_S = int(os.environ.get("NL_VERIFY_TIMEOUT_S", "600"))
MAX_REPAIR_ATTEMPTS = int(os.environ.get("NL_MAX_REPAIRS", "2"))
MAX_TOTAL_STAGE_ATTEMPTS = MAX_REPAIR_ATTEMPTS + 3   # hard ceiling across resumes
HARNESS_VERSION = promotion.HARNESS_VERSION
~~~

Remove/stop using: `scoped_patch_file, scoped_write_file` imports are still needed by the text fallback, but it is called with the stage workspace; `out_of_scope_paths` stays for `_check_scope` (kept for deterministic non-stage callers) but the staged path uses `promotion.validate`.

New exception:

~~~python
class GateFailure(...)  # imported from promotion (single type)
# keep DeveloperNoChangeError, ScopeViolationError, VerificationError
~~~

#### 3.9.2 Testability seam `_call_model` (C2)

Extract every CrewAI invocation into one method:

~~~python
def _call_model(
    self,
    role: str,
    model_name: str,
    prompt: str,
    *,
    goal: str,
    backstory: str,
    expected_output: str,
    tools: list | None = None,
) -> str:
    """Single invocation seam; tests monkeypatch this to return scripted text."""
    agent = Agent(
        role=role, goal=goal, backstory=backstory,
        llm=_make_llm(model_name, self.base_url),
        tools=tools or [], verbose=True, allow_delegation=False,
    )
    task = Task(description=prompt, expected_output=expected_output, agent=agent)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
    return str(crew.kickoff())
~~~

All four stages call it; no direct `Agent/Crew/Task` construction remains in stage methods. This is the only seam the SH tests need (plus `_make_llm` guarded to raise if called).

#### 3.9.3 New helpers

~~~python
def _mission_input_paths(self) -> list[str]:
    """Files that are mission input and must never be modified by the model."""
    return [p for p in promotion.MISSION_INPUT_DENY if (self.root / p).is_file()]

def _recovery_dir(self) -> Path:
    return db_path().parent / "recovery"

def _evidence_dir(self) -> Path:
    return db_path().parent / "verification"

def _save_promotion_status(self, mission_id: int, status: str | None) -> None:
    set_promotion_status(mission_id, status)
    self._emit("harness", "info", f"Promotion state: {status}", mission_id=mission_id)

def _assert_harness_mission(self, mission: dict) -> None:
    if mission.get("harness_version") != HARNESS_VERSION:
        raise GateFailure(
            f"Mission #{mission['id']} predates the staged-candidate harness "
            f"(harness_version={mission.get('harness_version')!r}); create a new mission "
            "instead of resuming it.",
            code="legacy-mission",
        )

def _ensure_stage(self, mission_id: int, dev_task: dict | None, goal: str) -> promotion.Stage:
    mission = get_mission(mission_id) or {}
    stored = mission.get("staging_dir")
    if stored:
        stage = promotion.load_stage(stored)
        if stage.project_root != self.root:
            raise GateFailure("Staged candidate belongs to a different project root", code="stage-mismatch")
        return stage
    write_paths = list((dev_task or {}).get("write_paths") or [])
    scope = promotion.derive_scope(self.root, write_paths or extract_paths(goal))
    stage = promotion.begin_stage(self.root, mission_id, scope)
    set_mission_staging(mission_id, str(stage.stage_dir))
    self._save_promotion_status(mission_id, "staged")
    record_handoff(mission_id, "orchestrator", "developer",
                   f"Candidate stage created: {stage.stage_dir.name}",
                   {"stage_dir": str(stage.stage_dir), "scope": list(stage.scope)})
    return stage

def _validate_stage(self, stage: promotion.Stage) -> dict:
    verdict = promotion.validate(stage, deny_paths=self._mission_input_paths())
    if verdict["valid"]:
        self._save_promotion_status(stage.mission_id, "validated")
    return verdict

def _run_verification(self, stage: promotion.Stage, task_id: int) -> VerificationReport:
    baseline = promotion.read_manifest(stage)["baseline"]
    report = candidate_verification.verify_candidate(
        stage.workspace, stage.stage_dir, baseline,
        timeout_s=VERIFY_TIMEOUT_S,
        report_path=stage.stage_dir / "verification" / "report.json",
    )
    for suite in (report.candidate, report.oracle):
        record_verification_run(
            mission_id=stage.mission_id, task_id=task_id,
            command=f"verify:{suite.suite} " + " ".join(suite.command),
            exit_code=suite.exit_code if suite.exit_code is not None else -1,
            stdout=_truncate(suite.stdout_tail, 40_000),
            stderr=_truncate(suite.stderr_tail, 40_000),
            passed=suite.passed,
        )
    if report.passed:
        promotion.mark_verified(
            stage, passed=True,
            evidence=json.dumps({
                "candidate": report.candidate.failures or "pass",
                "oracle": report.oracle.failures or "pass",
                "duration_s": round(report.candidate.duration_s + report.oracle.duration_s, 2),
            })[:2000],
        )
        self._save_promotion_status(stage.mission_id, "verified")
    return report

def _promote_candidate(self, stage: promotion.Stage) -> dict:
    self._save_promotion_status(stage.mission_id, "promoting")
    try:
        result = promotion.promote(stage, recovery_dir=self._recovery_dir())
    except GateFailure as exc:
        self._save_promotion_status(stage.mission_id, "cas-conflict" if exc.code == "cas-conflict" else "promotion-failed")
        raise
    self._save_promotion_status(stage.mission_id, "promoted")
    record_handoff(stage.mission_id, "orchestrator", "user",
                   f"Promoted {len(result['promoted'])} file(s) to the live tree",
                   {"promoted": result["promoted"], "hashes": result.get("hashes", {})})
    return result
~~~

#### 3.9.4 Rewritten `_run_developer_stage` (C6a)

Signature: `_run_developer_stage(self, mission_id, task_rec, goal, model_name, baseline, stage) -> str`.

Flow:

1. `task_id`, `write_paths = task_rec.get("write_paths") or list(stage.scope)`, `update_task_status(running)`, emit.
2. `tools = get_project_tools(stage.workspace)`.
3. Prompt: same content as today but `WORKSPACE (staged copy; write relative paths here): {stage.workspace}`; explicitly forbid editing files outside the declared scope and state that nothing is live until review.
4. `output = self._call_model("Implementation Developer", model_name, prompt, goal=..., backstory=..., expected_output=..., tools=tools)`.
5. `actions = _apply_text_actions(stage.workspace, output)` (unchanged function, new root).
6. `promotion.normalize_staged_newlines(stage)`.
7. `verdict = self._validate_stage(stage)`.
8. If not valid: `record_task_attempt(task_id,"failed",output=_truncate(output), error=_truncate("; ".join(verdict["errors"]),2000))`; `update_task_status(task_id,"failed",...) `; raise `GateFailure(code="candidate-rejected", details={"errors": verdict["errors"]})`.
9. If no changed paths: raise `DeveloperNoChangeError` (existing message, include actions).
10. `record_task_attempt(task_id,"completed",output=_truncate(output))`; `update_task_status(task_id,"completed")`.
11. Handoff `developer -> tester` with `changed_paths=verdict["changed_paths"]`, `actions`, `diff_sample=_truncate(candidate_diff[0],4000)`, `output_sample`.
12. Return output. **No live snapshot/diff, no live write, no `_check_scope` on live.**

#### 3.9.5 Rewritten `_run_tester_stage` (C6b)

Signature: `_run_tester_stage(self, mission_id, task_rec, debug_model, baseline, stage, max_attempts: int | None = None) -> dict`.

Flow:

1. `task_id`; `fresh = get_task(task_id) or task_rec`; `attempts_used = int(fresh.get("attempts") or 0)`; `max_attempts = max_attempts if max_attempts is not None else MAX_REPAIR_ATTEMPTS`; if `attempts_used > MAX_TOTAL_STAGE_ATTEMPTS` -> `VerificationError("repair budget exhausted")`.
2. `update_task_status(running)`, emit.
3. Loop `attempt in range(max_attempts + 1)`:
   a. `verdict = self._validate_stage(stage)`.
   b. if not valid: `record_verification_run(..., command="harness:validate", exit_code=1, stdout="", stderr="; ".join(verdict["errors"]), passed=False)`; if attempt limit not reached -> handoff `tester->debugger` + `self._run_debugger(..., stage)` and continue; else break.
   c. `report = self._run_verification(stage, task_id)`; keep `self._last_verification = report`.
   d. if `report.passed`: `record_task_attempt(task_id,"completed",output=summary)`; `update_task_status(completed)`; handoff `tester->reviewer` with `{"oracle": ..., "candidate": ..., "report": path}`; emit; return `{"report": report}`.
   e. if attempt limit reached -> break; else handoff `tester->debugger` with failure text + `self._run_debugger(..., stage)`.
4. `record_task_attempt(task_id,"failed", error=...)`; `update_task_status(failed,...)`; `self._save_promotion_status(mission_id,"verification-failed")`; raise `VerificationError` with oracle/candidate failure summary.

#### 3.9.6 Rewritten `_run_debugger` (C6b)

Signature: `_run_debugger(self, mission_id, model_name, error_msg, write_paths, baseline, stage) -> None`.

Flow: tools bound to `stage.workspace`; prompt includes failure logs and stage scope; `_call_model("Software Debugger", ...)`; `_apply_text_actions(stage.workspace, output)`; `normalize_staged_newlines`; record handoff with `candidate_diff` summary (do not raise on invalid candidate: the next tester iteration validates and reports it). No live snapshots.

#### 3.9.7 Rewritten `_run_reviewer_stage` (C6b)

Signature: `_run_reviewer_stage(self, mission_id, task_rec, model_name, baseline, stage) -> tuple[str, str]`.

Flow: `update_task_status(running)`; `diff, changed, stat = promotion.candidate_diff(stage)`; `validation` summary from stage manifest; verification evidence from `get_verification_runs(mission_id)` (all rows, including `verify:*` and `harness:validate`); prompt contains `CANDIDATE CHANGED FILES`, `VALIDATION RESULT`, `VERIFICATION RUNS`, `CANDIDATE DIFF`, plus a note that the candidate is **not yet applied** and a REJECT keeps it unapplied; `_call_model("Code Reviewer & Quality Gatekeeper", ...)`; `verdict = parse_reviewer_verdict(review_text)`; record attempt/status/handoff; `self._save_promotion_status(mission_id, "reviewed" if verdict=="APPROVE" else "review-rejected")`; return.

#### 3.9.8 `_run_locked` new sequence (C6c)

~~~python
def _run_locked(self, mission_id, goal, developer_model, reviewer_model, debug_model, stop_after):
    mission = get_mission(mission_id) or {}
    self._assert_harness_mission(mission)
    # ... existing resume logging / reset_interrupted_tasks / mark_mission_started / plan / baseline ...
    stage = None
    try:
        stage = self._ensure_stage(mission_id, dev_task, goal)
        outcome = promotion.reconcile(stage, recovery_dir=self._recovery_dir())
        if outcome["state"] == "conflict":
            self._save_promotion_status(mission_id, "rollback-conflict")
            return self._finalize_blocked(mission_id, f"Promotion journal conflict: {outcome}", "REJECT")
        if outcome["state"] == "promotion-complete" or promotion.is_live_promoted(stage):
            self._save_promotion_status(mission_id, "promoted")
            result = self._finalize_completed(mission_id, goal, review_text="", verdict="APPROVE",
                                              summary="Promotion recovered after crash.")
            promotion.cleanup_after_terminal(stage, mission_status="completed",
                                             evidence_dir=self._evidence_dir())
            return result
        # developer
        if dev_task and dev_task["status"] != "completed":
            self._run_developer_stage(mission_id, dev_task, goal, developer_model, baseline, stage)
        elif dev_task:
            emit "Developer stage already completed; reusing staged candidate"
            self._validate_stage(stage)   # re-validate persisted candidate
        if stop_after == "developer":
            return self._finalize_interrupted(mission_id, stage,
                summary="Interrupted after developer stage (staged candidate retained).")
        # tester
        if test_task and test_task["status"] != "completed":
            self._run_tester_stage(mission_id, test_task, debug_model, baseline, stage)
        elif test_task:
            emit "Tester stage already completed; reusing verification evidence"
        if stop_after == "tester":
            return self._finalize_interrupted(mission_id, stage,
                summary="Interrupted after tester stage (verified candidate retained).")
        # reviewer
        if rev_task and rev_task["status"] != "completed":
            review_text, verdict = self._run_reviewer_stage(mission_id, rev_task, reviewer_model, baseline, stage)
        else:
            review_text, verdict = self._persisted_review(mission_id)
        if verdict != "APPROVE":
            self._save_promotion_status(mission_id, "review-rejected")
            return self._finalize_blocked(mission_id, "Reviewer REJECTED the candidate diff.", "REJECT",
                                           review_text=review_text, stage=stage)
        # promotion: last gate
        promotion_result = self._promote_candidate(stage)
        result = self._finalize_completed(mission_id, goal, review_text=review_text,
                                          verdict="APPROVE",
                                          summary=f"Reviewer APPROVED; promoted {len(promotion_result['promoted'])} file(s).")
        promotion.cleanup_after_terminal(stage, mission_status="completed",
                                         evidence_dir=self._evidence_dir(),
                                         verification=self._last_verification_dict())
        return result
    except GateFailure as exc:
        self._save_promotion_status(mission_id, exc.code.replace("-", "_"))
        return self._finalize_blocked(mission_id, str(exc), "REJECT", stage=stage,
                                       code=exc.code, details=exc.details)
    except (VerificationError, DeveloperNoChangeError, ScopeViolationError) as exc:
        return self._finalize_blocked(mission_id, str(exc), "REJECT", stage=stage,
                                       code=type(exc).__name__)
    except Exception as exc:
        # unexpected: keep stage for reconcile; never completed
        self._emit("orchestrator", "error", f"Mission #{mission_id} failed: {exc}", mission_id=mission_id)
        record_handoff(mission_id, "orchestrator", "user", f"Mission failed: {exc}", {"error": str(exc)})
        update_mission_status(mission_id, "failed")
        return {**self._failed_result(mission_id, exc), "promotion_status": "error"}
~~~

`_persisted_review`: read the latest reviewer->orchestrator handoff payload verdict; fall back to `parse_reviewer_verdict(_latest_output(rev_task_id))` for compatibility; default REJECT.

#### 3.9.9 Finalize split (C6c)

Replace the single `_finalize` with three explicit writers, all sharing `_result_payload`:

~~~python
def _finalize_completed(self, mission_id, goal, *, review_text, verdict, summary) -> dict:
    # existing _finalize body for status "completed": live diff, changed paths, DB via update_mission_result
def _finalize_blocked(self, mission_id, reason, verdict, *, review_text="", stage=None,
                      code=None, details=None) -> dict:
    # update_mission_result(status="blocked", result_summary=reason, review_verdict=verdict,
    #                       diff_stat="", changed_paths=[])  # NOTHING was applied
    # record_handoff(orchestrator->user, reason, {"code": code, "details": details,
    #                 "staged_paths": manifest changed, "stage_dir": str(stage.stage_dir)})
    # emit warning; return payload with status blocked, error=reason, promotion_status from DB
def _finalize_interrupted(self, mission_id, stage, *, summary) -> dict:
    # update_mission_status("interrupted"); record handoff with staged candidate info;
    # changed_paths NOT recorded as applied changes
~~~

Rationale: today `_finalize` calls `_collect_changed_paths` (which unions handoff `changed_paths`), so a staged-but-unapplied candidate would be reported as a mission change. Blocked/interrupted results must report **no** live changes and list the staged paths only in the handoff payload (`staged_paths`). `_finalize_completed` keeps the existing `_collect_changed_paths` behavior because after promotion the live diff is authoritative.

#### 3.9.10 `run_mission` / `_run_locked` error semantics

- `MissionLockError` -> existing blocked behavior (unchanged).
- Legacy mission (harness_version != 2): `_assert_harness_mission` raises GateFailure -> blocked with clear message; no live writes, no stage created.
- `stop_after` values unchanged (`developer`, `tester`), now meaning "staged candidate retained, live tree unchanged".
- `mission.status == "completed"` short-circuit unchanged.

#### 3.9.11 Prompts

Update developer/debugger instructions: state the workspace is a staged copy, every write is a candidate, files outside the declared scope are rejected, there is no shell. Reviewer prompt: candidate not applied; base verdict on candidate diff + validation + verification evidence; do not claim tests ran if no verification rows exist (there always are).

---

### 3.10 `nl_coding_agent/core/selfbuild_runner.py` (C7)

Changes:

1. **Delete lines 293-326** (the "SPEC-28 harness gate" post-hoc block: baseline read, `detect_stub`, `p.write_text(baseline_content)`, swallowed `except Exception: _log("Harness gate error (ignored)")`). Nothing replaces it in the runner: the gate is now inside the orchestrator before promotion.
2. **Delete imports** at lines 12-13 (`save_snapshot`, `rollback_from_snapshot`, `detect_stub`, `detect_weak_test`); no runner file writes remain.
3. Add `from nl_coding_agent.core import promotion` and `from nl_coding_agent.persistence.missions import find_mission_by_staging_dir`.
4. Replace `select_resumable_mission(missions)` with `select_resumable_mission(missions, *, harness_version: int = promotion.HARNESS_VERSION)` -> skip missions whose `harness_version != harness_version`. Same for `pending_roadmap_mission(missions, roadmap, *, harness_version=...)`; `completed_roadmap_mission` unchanged (legacy completions may block a rerun; that is desirable).
5. `run_autonomous`: after `project = open_project(root); project_id = ...; state = ...`:
   - log skipped legacy resumables (ids), never select them;
   - `blocking = promotion.preflight(root, mission_lookup=find_mission_by_staging_dir)`; if non-empty: `stopped_reason = "Unresolved candidate promotion state: " + " | ".join(blocking) + "; resume the mission to reconcile before starting new work."`; log; return blocked result with `resume_command=_resume_command(root, inferred_id)` (infer from message or first journal's mission row);
   - explicit legacy `--resume <id>`: if mission.harness_version != 2 -> stopped_reason + blocked result (no exception, no live writes).
6. Keep the rest of the selection/state logic unchanged; remove the post-hoc result override (lines 311-320 area) but keep `results[-1]` bookkeeping for statuses coming from the orchestrator.
7. Add a tiny helper `_stage_dirs(root)` used by tests to assert no stage leaks.

Acceptance static checks (documented in section 9): no `p.write_text(baseline_content`, no `detect_stub(` in the runner, no `rollback_from_snapshot(` in the runner.

---

### 3.11 `nl_coding_agent/persistence/database.py` (C5)

Add three additive migrations to `_MIGRATIONS` (idempotent, existing rows untouched, no backfill):

~~~python
("missions", "harness_version", "INTEGER"),
("missions", "staging_dir", "TEXT"),
("missions", "promotion_status", "TEXT"),
~~~

No index needed (queries are by mission id; `find_mission_by_staging_dir` does a table scan over <= tens of rows, acceptable; if desired add `CREATE INDEX IF NOT EXISTS idx_missions_staging ON missions(staging_dir)` to `_INDEXES`).

**Operational note:** the first process that calls `init_db()` after C5 migrates the real DB. Migrations are additive-only (existing pattern) and tested against a copy of the legacy schema; take a SQLite backup before deploying C5 (Lead already has relocation backups; add a new one at implementation time; design does not perform it).

---

### 3.12 `nl_coding_agent/persistence/missions.py` (C5)

~~~python
HARNESS_VERSION = 2  # mirrors promotion.HARNESS_VERSION (avoid import cycle)

def create_mission(project_id: int | None, title: str, goal: str, *,
                   harness_version: int = HARNESS_VERSION) -> int:
    # add harness_version to the INSERT

def set_mission_staging(mission_id: int, staging_dir: str | None) -> None:
    with _db() as conn, conn:
        conn.execute("UPDATE missions SET staging_dir=?, updated_at=? WHERE id=?", (staging_dir, _now(), mission_id))

def set_promotion_status(mission_id: int, promotion_status: str | None) -> None:
    with _db() as conn, conn:
        conn.execute("UPDATE missions SET promotion_status=?, updated_at=? WHERE id=?", (promotion_status, _now(), mission_id))

def find_mission_by_staging_dir(staging_dir: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM missions WHERE staging_dir=? ORDER BY id DESC LIMIT 1", (staging_dir,)).fetchone()
        return dict(row) if row else None
~~~

Defaults: `create_mission` default `harness_version=2` means every new mission (CLI, GUI, self-build) is harness-aware; existing rows keep NULL.

---

### 3.13 `nl_coding_agent/cli.py` (C6c/C7)

1. `mission --resume <id>`: after `get_mission`, if `mission.get("harness_version") != 2` -> `raise SystemExit("Mission #<id> predates the staged-candidate harness; create a new mission instead (legacy missions cannot be resumed safely).")`.
2. `mission --list`: show `harness_version`/stage presence compactly (optional, low risk) so the operator can see legacy rows.
3. New sub-option (recommended, small): `mission --abandon-stage <id>`: allowed only when mission status is `blocked`/`interrupted` and no live process holds `data/mission.lock`; calls `promotion.discard_stage` (refusing if a journal exists), sets `staging_dir=NULL`, `promotion_status='abandoned'`, mission `blocked` with summary. This is the explicit human recovery path for a corrupt/missing stage (no automatic deletion of a journal).
4. `selfbuild --autonomous`: keep `check_selfbuild_readiness`; the new preflight runs inside `run_autonomous` and its message is printed by the existing `Stopped:` line. No CLI flag disables the gates.
5. Do **not** add any flag that disables staging/verification (SPEC-28 invariant 8: protections are not switchable by a single agent; a human env flag was deliberately omitted).

---

### 3.14 Tests

See section 7 for the full plan. Files touched/added: `tests/test_staging_broker_adversarial.py` (replace), `tests/test_rollback_stub.py` (replace + newline fix), `tests/test_operational_tools.py` (4 tools), `tests/test_selfbuild_runner.py` (harness filter, preflight, post-hoc removal), `tests/conftest.py` (new fixtures), `tests/test_promotion_stage.py` (new), `tests/test_candidate_verification.py` (new), `tests/test_harness_schema.py` (new), `tests/test_orchestrator_staging.py` (new), `tests/test_harness_sh.py` (new, SH-01..SH-07).

---

### 3.15 Documentation and manifest (C1b/C8)

- `SHA256_MANIFEST.json`: re-certified after C1b (test file hash changes); add a manifest entry for the new modules only if the team extends the manifest convention to runtime code (current manifest covers the 5 audited files; keep scope minimal and document the decision in the C1b commit).
- `docs/07_SAFETY.md`: add "Staged candidate and promotion" section: staging location, 4 model tools, no shell, independent candidate+oracle verification, recovery point, CAS/journal rollback, explicit limitations (candidate code executes; no OS sandbox; Windows newline normalization).
- `docs/CURRENT_STATE.md`: replace pipeline description with the staged flow, DB columns, evidence; update test counts to the final full-suite number; list SH-01..SH-07 evidence after they run on the real repo.
- `docs/02_SELF_BUILD_ROADMAP.md` and `docs/product-blueprint/specifiche/28_SELF_HEALING_AGENT_HARNESS.md`: change the status line from "non implementata" to "implemented in the staged-candidate harness; verified by tests/...; known limitations ...". Update only after C6/C7 are green on the real repo (SPEC-28 section 7).
- `build/phase2/PATCH_WINDOWS_REAUDIT.md`: design record of the C1b adaptation (auditable) - this is the only place where the design deliberately deviates from the PATCH bytes, and only in a test fixture.

---
## 4. The hard problem: where and how the regression suite runs on the candidate

### 4.1 Answer (short form)

Run the real repo suite against a **disposable copy of the staged workspace**, using the **real embedded interpreter** (never copied), with a **throw-away data directory** and a **scrubbed environment**:

- copy A ("candidate"): staged source + staged tests; run pytest; must be green;
- copy B ("oracle"): staged source + **baseline tests from the stage manifest**; run pytest; must be green;
- both runs: `cwd=<copy>`, `NL_DATA_DIR=<temp>/data`, `QT_QPA_PLATFORM=offscreen`, `PYTHONDONTWRITEBYTECODE=1`, `-q -p no:cacheprovider --junitxml=... tests`, timeout 600 s;
- pass = both exit 0, both junit reports non-empty with zero failures/errors, neither timed out; a runner preflight proves the imported `nl_coding_agent` package is inside the copy (exit 86 otherwise);
- cost measured: **1.32 MB per copy, ~14 s per suite**, no `python/`, `crewAI/`, `dist/`, `data/` copy at all. Verification copies are deleted after the evidence is persisted.

Why not run in the stage workspace itself: pytest may write into cwd (`.pytest_cache`, `__pycache__`, test scratch files) and the oracle copy requires replacing `tests/`; running in a separate copy keeps the validated hashes of `stage/workspace` untouched, which `mark_verified` re-checks.

Why not run in the live repo: the candidate is not applied yet; a red suite would leave the live tree partially modified today, and the live tree may contain human edits.

### 4.2 Where each piece lives during verification

~~~text
<project_root>/data/staging/mission-<id>-xxxx/
  manifest.json                  <- baseline (text snapshot) + changed hashes, broker-owned
  workspace/                     <- candidate files (never executed in place)
  verification/                  <- created and deleted by candidate_verification
    candidate/                   <- copy A: candidate source + candidate tests (+ runner)
    oracle/                      <- copy B: candidate source + pinned baseline tests
    data/candidate/              <- NL_DATA_DIR for copy A (SQLite etc.)
    data/oracle/                 <- NL_DATA_DIR for copy B
    evidence/                    <- junit-candidate.xml, junit-oracle.xml, report.json
<db_path().parent>/
  verification/mission-<id>.json <- retained evidence summary (small)
  recovery/<mission_id>.json     <- pre-images, retained per SPEC-02A policy
~~~

### 4.3 Test-suite dependency audit (what the suite needs, measured)

The suite in a staging-shaped copy needs **no data/** (after the PATCH test replacement) and **no vendor tree**. Dependency table:

| Test file | Repo-path dependencies (other than `nl_coding_agent`) | Works in staging copy? |
|---|---|---|
| `test_foundation.py` | scans repo root (copy) for files; Ollama calls tolerate offline; registry test patches `_DB_PATH` | yes (measured pass) |
| `test_operational_tools.py` | temp dirs; asserts 7 tools today -> must be migrated to 4 | yes after C2 |
| `test_system_status.py`, `test_version.py`, `test_cli_config.py` | none | yes |
| `test_gui_panels.py`, `test_gui_smoke.py`, `test_model_hub.py` | cwd-relative `nl_coding_agent/gui/widgets`; `config/models.yaml` path string; offscreen Qt | yes (source tree present) |
| `test_missions_graph.py` | patches `database._DB_PATH` | yes |
| `test_distribution_audit.py` | `scripts/audit_distribution.py` (must be in copy) | yes (stage baseline includes `scripts/`) |
| `test_stage_portable.py` | `scripts/stage_portable.py` | yes |
| `test_verify_relocation.py` | `scripts/verify_relocation.py` | yes |
| `test_project_root_migration.py` | `scripts/migrate_project_root.py`, `nl_coding_agent.core.relocation` | yes |
| `test_selfbuild_mode.py` | `nl_agent.py`, `NL Coding Agent.bat`, `Self-Build Mode.bat`; spawns `nl_agent.py selfbuild --help` in cwd | yes (all are staged text files) |
| `test_selfbuild_runner.py` | patches runner internals; one test indirectly exercised the old post-hoc gate | yes; updated in C7 |
| `test_roadmap.py` | `docs/NEXT_SELF_BUILD_MISSION.md` (staged) | yes; oracle pins the baseline copy |
| `test_scope_permission.py`, `test_crewai_runtime.py` | none / site-packages check | yes |
| `test_rollback_stub.py` (old root version) | `data/mission_baselines/42.json` + live planner | **NO** - FileNotFoundError measured; replaced by PATCH version in C1a |
| `test_staging_broker_adversarial.py` (old root version) | writes into `./data/staging` and real planner | unsafe; replaced by PATCH version in C1a (PATCH test writes only temp dirs) |

### 4.4 Tests that fail in a *naive* staging copy and why (explicit list)

Measured on a source-only copy (the shape `stage_candidate` produces):

1. `tests/test_rollback_stub.py::TestRollbackStub::test_restore_planner_from_baseline_42` -> `FileNotFoundError: data/mission_baselines/42.json`. **Cause:** the old test reads the live mission baseline and the live planner file. **Fix:** replaced by the PATCH isolated recovery test (C1a).
2. Root `tests/test_staging_broker_adversarial.py` -> passes only because cwd happens to be the copy; it writes `data/staging` into cwd and rewrites real source paths if run at repo root. **Fix:** replaced by the PATCH temp-dir test (C1a); never run the root version again.
3. `PATCH/tests/test_rollback_stub.py::TestRecoveryStore::test_restore_only_known_agent_postimage` -> fails on Windows only (`result['blocked'] == ['planner.py']`). **Cause:** fixture uses `Path.write_text` (CRLF) and hashes `sha256_text` (LF). **Fix:** C1b writes fixture text with `newline=""` (measured pass).

No other test fails in the copy: measured **93 passed / 1 failed (old rollback stub) / 94 collected** before PATCH; **102 passed / 1 failed (PATCH newline) / 103 collected** with PATCH applied. After C1a+C1b the copy suite is fully green; the oracle run (baseline tests over candidate source) is green as well when the candidate is behaviour-preserving.

### 4.5 Minimal hermetic environment recipe (exact)

**Copy rules** (source of truth: the stage workspace itself; ~181 files):

- copy A = `shutil.copytree(stage.workspace, verify/candidate)` (this already excludes `data/`, `logs/`, `state/`, `dist/`, `build/`, `python/`, `crewAI/`, `.git`, caches - `snapshot_workspace` did the filtering when the stage was created);
- copy B = copytree of the same, then `overlay_oracle` (section 4.6);
- do **not** copy `python/`, `crewAI/`, `crewAI-tools/`, `dist/`, `build/`, `data/`, `logs/`, `state/`, `.git/`, model/checkpoint files. Estimate: 0 bytes of the 1.64 GB + 467 MB + 1.44 GB vendor payloads; total added disk per verification ~**2.7 MB** plus pytest tmp (system temp) ~ a few MB.

**Interpreter:** the orchestrator passes `sys.executable` (the embedded `python\python.exe`, absolute). It is *executed* from the copy but never copied. The `._pth` isolated-runtime quirk is handled by a generated `_pytest_runner.py` that inserts the copy root at `sys.path[0]` and asserts the imported package path is inside the copy (exit 86 otherwise).

**Environment (exact keys):**

~~~text
cwd                = <copy>
NL_DATA_DIR        = <verify>/data/<suite>      (redirects SQLite + selfbuild state; verified)
QT_QPA_PLATFORM    = offscreen                 (GUI tests; they also setdefault it)
PYTHONDONTWRITEBYTECODE = 1                    (no __pycache__ in the copy)
PYTHONUTF8         = 1
PYTHONIOENCODING   = utf-8
PYTHONHASHSEED     = 0
NO_COLOR           = 1
GIT_PAGER / PAGER  = cat
drop PYTHONPATH, PYTHONHOME, PYTHONSTARTUP, PYTHONUSERBASE
~~~

**Command (per suite, argv list, no shell):**

~~~text
<python.exe> <copy>/_pytest_runner.py -q -p no:cacheprovider --no-header
             --junitxml=<verify>/evidence/junit-<suite>.xml tests
timeout: subprocess.run(..., timeout=NL_VERIFY_TIMEOUT_S)  # default 600 s
decode: nl_coding_agent.tools.shell.decode_output (Windows OEM fallback)
~~~

**Data dependencies:** none. The suite creates its own temp dirs; all DB writes follow `NL_DATA_DIR` (verified: a run leaves the copy root untouched except temp-only churn; with the unsafe test replaced, nothing at all is written into the copy root). If a future test needs fixture data, it must create it under `tmp_path` or `NL_DATA_DIR`; copying `data/` (16 MB) is explicitly rejected (not needed, and it contains mission history/baselines with user provenance).

**Evidence:** junit XML parsed into `failures: list[str]` (classname::name), stdout/stderr tails (last 8 000 chars each) kept in `report.json` and in `verification_runs` rows (40 000-char truncation, existing helper); exit code 86 or missing junit => infrastructure failure => not a pass.

### 4.6 Oracle overlay (the SH-04 gate)

Baseline source of truth: `stage/manifest.json["baseline"]` (the text snapshot taken at stage creation; ~1.47 MB, already in memory).

`overlay_oracle(copy_root, baseline)`:

1. delete `copy_root/tests` entirely;
2. restore every baseline `tests/**` file (LF bytes);
3. restore pinned root config: `pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`, `conftest.py` (write baseline version, or delete candidate-added one if it was not in baseline);
4. restore pinned inputs: `docs/NEXT_SELF_BUILD_MISSION.md` (the suite reads it; it is mission input, never a candidate output);
5. delete any other candidate-added `conftest.py` outside `tests/` (prevents a candidate conftest from monkeypatching the oracle);
6. return an operations log embedded in the evidence report.

Rationale: a candidate that weakens, deletes, or replaces tests cannot hide a regression from the baseline suite. If a mission legitimately changes tested behaviour, the oracle goes red and the mission is blocked pending a human decision - that is intended fail-closed behaviour (SPEC-28 invariants 3 and 9, "candidate tests are not the sole oracle"). Recommended human procedure: update the baseline tests in a **separate, human-reviewed commit before** starting the mission (no retroactive agent baseline changes).

Empirical proof of the mechanism: fixture with a buggy source change plus a matching weakened test -> candidate suite **0 failures**, oracle suite **1 failure**; the integration would block.

### 4.7 Windows newline/byte-hash correctness (mandatory adaptation; empirically found)

Facts from the probe:

1. `scoped_write_file` uses `Path.write_text` -> on Windows the staged file bytes contain CRLF.
2. `staging_broker` and `workspace.snapshot_workspace` hash **text** after universal-newline translation -> all manifest hashes are LF-normalized.
3. `promote_staged` writes `candidate.read_bytes()` -> live file becomes CRLF (whole-file rewrite; git diff noise for a repository whose files are LF).
4. Recovery rollback with `expected_post_hashes = delta[rel]["after"]` (LF hash) could not recognise the just-written CRLF bytes: measured `{'restored': [], 'blocked': ['nl_coding_agent/core/workspace.py'], 'reason': ['... not the recorded agent post-image']}`. **Rollback was impossible for the normal model write path.**
5. The same class of bug is why the audited PATCH test fails on Windows (section 4.4 item 3).

Integration fixes (all implemented outside the audited modules):

- `filesystem.scoped_write_file/scoped_patch_file` write with `newline=""` (C2);
- `promotion.normalize_staged_newlines(stage)` after every model stage and before every validate (C3/C6);
- `promotion.assert_byte_hash_invariant(stage)` before mark/promote: asserts `sha256_bytes(staged_bytes) == sha256_text(staged_text) == delta["after"]` for every changed file; failure => `GateFailure("byte-invariant")` => blocked, no live write;
- recovery `expected_post_hashes` are computed from the same staged bytes that `promote_staged` will write (`sha256_bytes`), i.e. after normalization they equal the broker hashes.

Known residual limitation (OPEN): external projects checked out with CRLF will have a changed file normalized to LF on promotion (whole-file line-ending change). Recommended default for phase 2: accept + document; optional future PATCH v3 could preserve per-file newline style in the manifest.

### 4.8 Size/runtime/cleanup

| Item | Value (measured/derived) |
|---|---|
| stage workspace | 181 files, ~1.32 MB |
| stage manifest | ~1.47 MB (one per mission, under `data/staging`) |
| verification copies | 2 x ~1.32 MB + junit (~50 KB) + runner scripts |
| verification data dirs | fresh SQLite ~100 KB each |
| one suite runtime | ~13.5-14 s on this machine (full repo suite) |
| two suites + copies | ~28-30 s per verification attempt; worst case with 2 repairs ~90 s |
| recovery point | 2 files ~18 KB; roughly 2x the changed-file bytes when many files change (hex encoding) |
| transient per mission before cleanup | ~6 MB; after cleanup: recovery point + evidence JSON + DB rows |
| cleanup | verification dir removed right after the report; stage dir removed on terminal status (except conflict statuses); `sweep_stale_stages` removes orphan/terminal stages older than 7 days and never removes a journal |

### 4.9 Residual limitations of the verification answer (state them in docs)

1. Candidate tests execute candidate code with user privileges; no OS sandbox. Mitigations only (no shell tool, disposable copy, env scrub, timeout); do not market the harness as a sandbox.
2. Network is not isolated (tests may connect; current suite tolerates an offline Ollama).
3. Hardware behaviour cannot be verified here (AGENTS.md invariant); hardware checks stay "pending" in mission evidence if relevant.
4. Oracle pinning blocks legitimate behaviour/test changes until a human updates the baseline tests out-of-band.
5. External CRLF checkouts get a line-ending normalization on promoted files (section 4.7).
6. Flaky tests become mission blockers by design; the recommended handling is fixing/isolating the flaky test in the repo, not a runtime retry (a retry would weaken the gate). Optional config for a documented exclusion list is OPEN and must be human-owned (never model-writable).

---

## 5. DB/evidence sequencing, journal and crash-recovery semantics

### 5.1 DB schema additions (C5)

~~~sql
ALTER TABLE missions ADD COLUMN harness_version  INTEGER;   -- NULL = legacy, 2 = staged harness
ALTER TABLE missions ADD COLUMN staging_dir      TEXT;      -- absolute stage dir or NULL
ALTER TABLE missions ADD COLUMN promotion_status TEXT;      -- see vocabulary below
~~~

Vocabulary (`missions.promotion_status`): `staged`, `validated`, `verified`, `reviewed`, `promoting`, `promoted`, `candidate_rejected`, `verification_failed`, `review_rejected`, `cas_conflict`, `rollback_conflict`, `rollback_complete`, `stage_missing`, `abandoned`, `error`.

`missions.status` keeps the existing values (`pending/running/completed/failed/blocked/interrupted`); only `_finalize_completed` writes `completed`.

### 5.2 Durable write ordering (fail-closed)

| Step | DB write | File write | Crash consequence |
|---|---|---|---|
| mission start | `status=running`, `started_at` | none | resume: create stage |
| stage created | `staging_dir=<path>`, `promotion_status=staged` | stage dir + manifest | resume: reuse stage |
| developer staged | task completed; handoff | stage workspace only | resume: re-validate stage |
| validated | `promotion_status=validated` | manifest `validated=true` | resume: re-validate |
| verification passed | 2 x `verification_runs` rows; `promotion_status=verified` | manifest `verified=true`+evidence | resume: hashes re-checked; re-verify if changed |
| review APPROVE | task completed; handoff; `promotion_status=reviewed` | none | resume: promote |
| pre-promotion | **`promotion_status=promoting`** | recovery point written **before** any live write | resume: reconcile journal / live check |
| promotion done | `promotion_status=promoted`; handoff | live files written; journal deleted by broker | resume: finalize only |
| completed | `status=completed`, result fields, `finished_at` | evidence JSON; stage cleanup | resume: cached completed result |
| blocked | `status=blocked`, `result_summary=reason`, `review_verdict`, `changed_paths=[]`, `diff_stat=""` | stage retained (except post-promotion) | new mission / operator action |
| failed | `status=failed` | stage retained; may need reconcile | resume/reconcile |

Rules:

- `promotion_status='promoting'` is written **before** `promote_staged`. A crash therefore leaves a durable "promotion may have started" marker *plus* either no writes, some writes, or all writes.
- The recovery point is written after the live-CAS preflight and before `promote_staged`; `save_snapshot` refuses overwrite, so `ensure_recovery_point` reuses an identical existing point for retries.
- No code path writes `status=completed` outside `_finalize_completed` (verify with a grep in C6c acceptance).

### 5.3 Promotion journal algorithm (broker behavior used as-is)

1. preflight: all destination hashes still equal manifest `before`; staged candidate hashes still equal `after`; else no journal, no write.
2. write `promotion-journal.json` (`project_root, changed{before,after}, status=in-progress`).
3. per file: re-check CAS, `_atomic_write(dest, staged_bytes)`.
4. delete journal; `manifest.promoted=true`.
5. on exception: keep journal; caller must reconcile (never guess, never delete a journal without proof).

### 5.4 Recovery decision tree at resume (and at self-build preflight)

~~~text
load stage
  |
  +-- stage dir missing / manifest unreadable / project_root mismatch
  |      -> GateFailure(stage-missing | stage-mismatch) -> mission blocked, no writes.
  |
  +-- journal exists
  |      +-- all changed files current == after
  |      |      -> promotion had completed: delete journal, finalize COMPLETED (no model calls, no rewrite).
  |      +-- all current == before
  |      |      -> promotion never wrote: delete journal, continue (re-promote after gates).
  |      +-- mixed
  |             -> recovery point must exist; restore only files whose current == after
  |                (rollback_from_snapshot with expected_post_hashes = staged bytes hashes).
  |             +-- all after-files restored -> delete journal -> rollback_complete -> re-promote.
  |             +-- any blocked (human edit) -> keep journal -> mission BLOCKED rollback_conflict;
  |                                          operator merges; no automatic write.
  |
  +-- no journal
         +-- live already equals after (all changed files) -> treat as promoted -> COMPLETED.
         +-- else if manifest verified -> continue from the last durable phase
             (re-validate + re-hash; if staged workspace changed since verification -> verified invalidated,
              re-run validation + verification, bounded by the attempt ceiling).
~~~

Journal vs DB consistency: if the journal exists but the mission row is terminal or missing, the preflight blocks self-build startup with an explicit message (no automatic deletion). The operator path is `mission --resume <id>` (reconcile) or `mission --abandon-stage <id>` when there is no journal.

### 5.5 Evidence ledger

- `verification_runs`: one row per suite per attempt with `command = "verify:candidate <argv>" / "verify:oracle <argv>" / "harness:validate"`, exit code, tails, passed.
- `handoffs`: stage created, developer staged diff, tester evidence (oracle+candidate), reviewer verdict, promoted files+hashes, block reason+code.
- `events`: human-readable harness events (`promotion state: ...`).
- `<db_path().parent>/verification/mission-<id>.json`: suite results, failures, durations, overlay ops, timeout flags; retained after stage cleanup.
- recovery point `<db_path().parent>/recovery/<mission_id>.json`: pre-images, retained for selective rollback (SPEC-02A).
- Never write verification evidence or recovery points into the target project (only the stage itself, which is cleaned).

### 5.6 Retention/cleanup

- After `completed`: persist evidence, delete verification dir and stage dir (recovery point + evidence retained).
- After `blocked` before promotion: keep stage + evidence for diagnosis; `sweep_stale_stages` deletes it after `retention_days` (7) if the mission is terminal and no journal.
- After `rollback_conflict`: keep everything (journal + stage + recovery) until human resolution.
- Startup sweep: `sweep_stale_stages` + preflight in `run_autonomous`; a sweep never deletes journals or non-terminal missions.
- Existing `data/staging/999` leftover from the old unsafe test: delete it during C1a verification only after confirming it is the old artifact (contains old planner/test copies, no journal); record the action in the C1a commit message. (Recommended; if the Lead prefers zero deletions, leave it and add it to the retention audit.)

---

## 6. Failure-mode matrix

Legend: **DB** = `missions.status` / `missions.promotion_status`; **FS** = live filesystem state; stage = candidate workspace retained unless stated.

| # | Failure mode | Detection gate | DB state | Live FS state | Recovery path / next action |
|---|---|---|---|---|---|
| 1 | Stub/placeholder code (API removed, body `pass`/`...`/NotImplementedError, >70% shrink, invalid Python) | `code_integrity_gate.detect_stub` via `validate_candidate` (C3/C6) | `blocked` / `candidate_rejected`; developer task failed/attempt recorded | **untouched** (candidate only in stage) | no rollback needed; stage kept; operator fixes roadmap/model or starts a new mission; self-build stops with reason |
| 2 | Weak test (test function removed, or every test body is only `assert True`) | `detect_weak_test` via validate | `blocked` / `candidate_rejected` | untouched | as row 1; if detected during a debugger repair the tester loop consumes one repair attempt |
| 3 | Out-of-scope write / protected path / path traversal / symlink | `out_of_scope_paths`, broker `_safe_path`, `check_delta_policy`, `filesystem` protected dirs | `blocked` / `candidate_rejected` | untouched | as row 1; a debugger repair may revert the staged extra file (overwrite back to baseline) before the next validation |
| 4 | Candidate suite red (candidate tests fail) | TestGate candidate copy | `blocked` / `verification_failed` after repairs exhausted; `verification_runs` rows show failures | untouched | bounded repair loop (debugger edits stage, re-validate, re-verify); then blocked. Resume re-runs the tester with the persistent attempt ceiling; human fixes or new mission |
| 5 | Oracle suite red while candidate suite green (SH-04: tests weakened to match a bug) | TestGate oracle copy | `blocked` / `verification_failed`; oracle failure ids in evidence | untouched | bounded repair loop; if the mission legitimately changes behaviour, a human updates the baseline tests out-of-band **before** a new mission; resume-only retries stay inside the attempt ceiling |
| 6 | Reviewer REJECT | LLM verdict parse (conservative: ambiguity = REJECT) | `blocked` / `review_rejected`; `review_verdict=REJECT` | untouched | stage kept; no promotion. New mission after addressing the review; resume uses the persisted REJECT (no silent re-review) |
| 7 | CAS conflict at promotion preflight (external/human edit to a changed file since the stage baseline) | `check_live_drift` before the recovery point; broker preflight as second line | `blocked` / `cas_conflict` | external content **preserved**; nothing written | no journal exists; operator merges/decides; a later resume retries promotion only if live bytes match the stage baseline again |
| 8 | Human/concurrent edit during promotion, between files | broker per-file CAS; journal kept | `blocked` / `cas_conflict` or `rollback_conflict` | written part = candidate; edited part = human; no blind overwrite | `reconcile`: restore only after-files (CAS); if the human-edited file is not at before/after -> `rollback_conflict`, journal kept, manual three-way merge, recovery point available |
| 9 | Crash between files during promotion | journal + `promotion_status='promoting'` + dead lock pid | resume: `running`; reconcile outcome drives next | mixed: some after, some before | all-after -> finalize completed; all-before -> retry; mixed -> automatic CAS rollback then retry; conflict -> blocked (`rollback_conflict`) |
| 10 | Crash after full promotion, before DB finalize | `is_live_promoted` at resume (journal may be absent because the broker deletes it before returning) | resume: `running` -> finalize | complete candidate applied | finalize completed without model calls or rewrites; cleanup runs |
| 11 | Promotion journal present at restart / self-build preflight | `promotion.preflight` / `reconcile` | mission `running/interrupted`; self-build returns `blocked` with a resume instruction | unchanged | run `mission --resume <id>` -> reconcile (row 9); if the mission row is terminal/missing -> preflight blocks with explicit message; `--abandon-stage` only when no journal |
| 12 | Resumed mission | stage lookup via `missions.staging_dir`; manifest re-read; hashes re-checked | `running` (existing resume bookkeeping) | unchanged | continue from the persisted phase; no re-baseline, no duplicate staging, no duplicate tasks; if the staged workspace changed since `verified`, verification is invalidated and re-run (attempt ceiling persists) |
| 13 | Stage missing/corrupt or project-root mismatch on resume | `load_stage`/hash checks | `blocked` / `stage_missing` or `stage_mismatch` | untouched | operator discards the stage pointer (`--abandon-stage`) and creates a new mission; no automatic re-staging (could silently change scope) |
| 14 | Verification infrastructure failure (timeout, runner imported outside copy, python missing, junit absent/empty) | pass rule requires exit 0 + non-empty junit + no timeout + resolution guard | `blocked` / `verification_failed`; evidence includes error | untouched | repair loop not useful for infra failures (keep it: a second attempt is cheap); then blocked; operator fixes environment |
| 15 | Legacy mission (pre-harness) targeted explicitly or selected | `_assert_harness_mission` / selection filter | `blocked` / `abandoned`? no: `blocked` with legacy reason; `promotion_status` untouched (NULL) | untouched | create a new mission; optional one-time operator script to mark legacy resumables blocked (OPEN: requires user approval; not part of automatic flow) |
| 16 | Unexpected exception inside a stage | catch-all in `_run_locked` | `failed` / `error`; stage retained | possibly nothing written (all model writes staged) | resume: reconcile; inspect handoff; fix bug |
| 17 | Out-of-scope external edits (unrelated files) | not a gate for promotion (only delta paths are CAS-checked) | not blocking | unchanged by mission | recorded in reviewer context as "live tree has unrelated changes"; mission may complete; no rollback touches them |
---

## 7. Test plan for SH-01..SH-07 (pytest, fake model output, no Ollama)

### 7.1 Test seams and fixtures (new `tests/conftest.py`)

All harness tests must run without Ollama and without touching the real repo. Required fixtures:

~~~python
# tests/conftest.py
import json, os, sys
from pathlib import Path
import pytest

@pytest.fixture()
def mission_env(tmp_path, monkeypatch):
    """Isolated app data dir: SQLite, recovery, verification, mission lock."""
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setenv("NL_DATA_DIR", str(data))
    monkeypatch.setenv("NL_VERIFY_TIMEOUT_S", "120")
    monkeypatch.setenv("NL_MAX_REPAIRS", "1")
    from nl_coding_agent.persistence.database import init_db, db_path
    init_db(db_path())                       # create schema in the isolated DB
    return data

@pytest.fixture()
def demo_project(tmp_path):
    """Minimal text project: package + pytest config + one meaningful test."""
    root = tmp_path / "demo"
    (root / "demo_pkg").mkdir(parents=True)
    (root / "demo_pkg/__init__.py").write_text("", encoding="utf-8")
    (root / "demo_pkg/mathx.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/__init__.py").write_text("", encoding="utf-8")
    (root / "tests/test_mathx.py").write_text(
        "from demo_pkg.mathx import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding="utf-8")
    return root

class FakeModel:
    """Scripted outputs, one per _call_model invocation; also records prompts."""
    def __init__(self, outputs): self.outputs = list(outputs); self.prompts = []
    def __call__(self, orch, role, model_name, prompt, **kwargs):
        self.prompts.append((role, prompt))
        if not self.outputs:
            raise AssertionError("FakeModel ran out of outputs; a stage called the model more often than expected")
        return self.outputs.pop(0)

@pytest.fixture()
def fake_model(monkeypatch):
    def install(outputs):
        fake = FakeModel(outputs)
        monkeypatch.setattr(
            "nl_coding_agent.agents.orchestrator.MultiAgentOrchestrator._call_model",
            lambda self, role, model_name, prompt, **kw: fake(self, role, model_name, prompt, **kw),
        )
        return fake
    return install

@pytest.fixture(autouse=True)
def no_ollama(monkeypatch):
    """A test that reaches CrewAI/Ollama fails loudly instead of hanging."""
    import nl_coding_agent.agents.orchestrator as orch
    monkeypatch.setattr(orch, "_make_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Ollama must not be called in tests")))
~~~

Notes:

- `_call_model` is the single seam (section 3.9.2); guarding `_make_llm` proves no hidden LLM path exists.
- `mission_env` sets `NL_DATA_DIR`, so `db_path()`, `mission_lock`, baselines, recovery and verification evidence are all isolated (verified: `db_path()` reads the env dynamically at call time).
- `demo_project` keeps verification fast (~1 s per suite); the embedded interpreter is the real one.
- Tests must not spawn `selfbuild --autonomous`; the SH tests call `MultiAgentOrchestrator.run_mission` with `FakeModel` only.

### 7.2 SH cases (files, inputs, assertions)

**`tests/test_harness_sh.py`** - orchestrator level, uses `FakeModel`.

| Test | Scenario / fake output | Assertions (DB / FS / evidence) |
|---|---|---|
| `test_sh01_stub_planner_blocked` | developer output writes `demo_pkg/mathx.py` with `def add(a,b): pass` and a new weak test; reviewer not reached | mission `blocked`, `promotion_status='candidate_rejected'`; live `mathx.py` unchanged; no `promotion-journal.json`; a `harness:validate` verification row exists; handoff payload contains the stub path |
| `test_sh04_weak_test_rejected_structurally` | developer keeps the source correct but rewrites `tests/test_mathx.py` to a single `assert True` | blocked; `detect_weak_test` error recorded; live test file unchanged |
| `test_sh04_oracle_red_candidate_green` | developer changes `add` to return `a - b` AND updates the candidate test to `assert add(2,3) == -1` (structurally valid) | candidate suite green, oracle suite red; mission `blocked`, `promotion_status='verification_failed'`; live files unchanged; `verification_runs` has both `verify:candidate` and `verify:oracle` rows with oracle passed=0 |
| `test_sh05_out_of_scope_rejected` | fake output writes `README.md` (outside scope) plus a valid mathx change | blocked (`candidate_rejected`); live README absent/unchanged |
| `test_sh05_no_shell_tools` | unit: `get_project_tools(root)` | exactly 4 tools; `run_command`/`run_tests`/`git_diff` absent; writes land in the passed root |
| `test_happy_path_completed` (baseline for SH-07) | valid source+test output, reviewer `"APPROVE\nok"` | mission `completed`, `promotion_status='promoted'`; live files contain the new function; stage dir removed; recovery JSON exists |
| `test_review_reject_leaves_live_untouched` | valid candidate, reviewer `"REJECT: missing docs"` | mission `blocked`, `review_rejected`; live bytes identical to before |
| `test_stop_after_developer_resume` | run 1 `stop_after="developer"`; run 2 resume with reviewer APPROVE | run 1 `interrupted`, live unchanged, stage retained; run 2 `completed`, exactly one promotion; tasks not duplicated |
| `test_human_edit_during_mission_cas` | valid developer output; the `FakeModel` reviewer call performs an external write to the live file (simulating a human) before promotion | mission `blocked`, `cas_conflict`; live contains the human content; no journal; stage retained |
| `test_legacy_mission_refused` | create a mission row with `harness_version=NULL`; call `run_mission` | `blocked` with the legacy message; no stage dir; live untouched; no model call |

**`tests/test_promotion_stage.py`** - coordinator unit tests, temp roots, no model:

- `begin_stage` manifest/scope; `derive_scope` fallback from top-level entries; empty scope raises;
- `validate` rejects stub, weak test, out-of-scope, protected path, denied mission-input path (`docs/NEXT_SELF_BUILD_MISSION.md`);
- `normalize_staged_newlines` + `assert_byte_hash_invariant`: write a staged file with the Windows-default `Path.write_text` (CRLF), assert the invariant fails before normalization and passes after;
- `promote` idempotency: second call returns `already=True` without writing; `is_live_promoted` true;
- recovery point reuse on retried promotion; mismatching existing point -> conflict;
- `reconcile` matrix: all-after -> `promotion-complete` (journal removed, live unchanged); all-before -> `never-promoted`; mixed with a staged after-file -> `rolled-back` and restore; mixed with a human-edited file -> `conflict` with journal kept;
- `rollback` preserves a newer human edit (`blocked`) - complements the PATCH test at coordinator level;
- `cleanup_after_terminal` writes the evidence JSON and removes the stage only for completed/non-conflict; `sweep_stale_stages` never deletes a journal.

**`tests/test_candidate_verification.py`** - verification environment:

- clean demo project: both suites pass; junit parsed; copies removed by cleanup; no writes inside the copy root except temp paths;
- candidate-only failure: a broken candidate test -> candidate red, oracle green -> `passed=False`;
- oracle-only failure: buggy source + matching weakened test -> candidate green, oracle red -> `passed=False` (SH-04 mechanism at module level);
- timeout: a test that sleeps longer than `timeout_s=1` -> `timed_out=True`, `passed=False`, process killed;
- resolution guard: assert the generated `_pytest_runner.py` refuses an out-of-copy import (unit-test the exit-86 branch or its content) -> infrastructure error is not a pass;
- empty/missing junit -> not a pass; `NL_DATA_DIR` isolation: a test that opens the DB writes only under the per-suite data dir (assert `<copy>/data` does not exist);
- overlay: a candidate-added `conftest.py` and a modified `pyproject.toml` are not effective in the oracle copy.

**`tests/test_harness_schema.py`** - persistence:

- create a legacy-schema DB (tables without the 3 columns), run `init_db`, assert the columns exist, rows preserved, `harness_version` NULL for old rows;
- `create_mission` defaults `harness_version=2`; `set_mission_staging`/`set_promotion_status`/`find_mission_by_staging_dir` round-trip.

**`tests/test_selfbuild_runner.py` additions:**

- `select_resumable_mission` skips legacy (harness_version NULL) and picks harness-v2; `pending_roadmap_mission` likewise;
- `run_autonomous` with a legacy resumable present: skips it, logs, proceeds (or returns idle) - no exception;
- `run_autonomous` with an unresolved promotion journal: returns `blocked` with a resume instruction, does not call the orchestrator;
- post-hoc gate removal: create a live file that the old detector would have restored; a fake orchestrator returns `completed`; assert the runner does not rewrite the file and does not read `mission_baselines`;
- explicit legacy `resume_mission_id` -> blocked result, orchestrator not called.

**SH-06 (recovery economy)** - in `test_promotion_stage.py`: the recovery point contains only delta files with correct `before_sha256/before_hex`, size bounded (<100 KB for a 2-file text change); `save_snapshot` refuses >1 MB files; no `python/`, model or binary content enters the recovery point.

**SH-07 (two consecutive missions without manual intervention)** - `test_harness_sh.py::test_sh07_two_consecutive_missions`:

- mission A: valid feature + test, reviewer APPROVE -> completed, live updated, stage cleaned;
- mission B (new mission row, same demo project): second feature, reviewer APPROVE -> completed; mission A's changes are part of mission B's baseline;
- assertions: both mission rows `completed`; live tree contains both features; mission B's stage delta is only its own files; a fresh `MultiAgentOrchestrator` instance reports both as completed (restart-like); no manual DB/state manipulation.

### 7.3 Existing tests migrated

| File | Change |
|---|---|
| `tests/test_staging_broker_adversarial.py` | replaced by the PATCH isolated test (C1a); the unsafe root version must not exist afterwards |
| `tests/test_rollback_stub.py` | replaced by the PATCH isolated recovery test + `newline=""` fixture fix (C1a/C1b) |
| `tests/test_operational_tools.py` | `get_project_tools` assertion 7 -> 4; negative assertions for `run_command`/`run_tests`/`git_diff`; add a CRLF check for `scoped_write_file`; existing filesystem/shell tests unchanged |
| `tests/test_selfbuild_runner.py` | resumable fixtures gain `harness_version=2`; new legacy/preflight/post-hoc tests |
| `tests/conftest.py` | new (fixtures above) |
| all other test files | unchanged |

### 7.4 New test files and rough counts

| File | Tests (approx) | Runtime |
|---|---|---|
| `tests/test_promotion_stage.py` | 14-16 | ~3-5 s |
| `tests/test_candidate_verification.py` | 8-10 | ~15-20 s (real pytest subprocesses on the demo project) |
| `tests/test_harness_schema.py` | 3-4 | <1 s |
| `tests/test_harness_sh.py` | 10-12 | ~30-45 s (each happy-path mission runs two real pytest suites) |
| `tests/test_selfbuild_runner.py` | +6 | ~2 s |
| full suite after C8 | 103 (after C1b) + ~45 = ~148, green | ~60-75 s |

---

## 8. Risks and open questions

| # | Risk / question | Impact | Recommended default (decision) |
|---|---|---|---|
| R1 (**OPEN**) | Staging dirs live under `<project_root>/data/staging` (the PATCH hard-codes it) -> artifacts inside external projects (SPEC-02A concern) | MED for external projects; none for NL Coding Agent | Accept for phase 2; document and always clean; future PATCH v3 should add a `staging_base` parameter (requires re-audit) |
| R2 | Candidate tests execute candidate code with user privileges (no OS sandbox) | MED (inherent to a pytest gate) | Keep no shell/test tool in the model toolset; disposable copy; env scrub; timeout; document the limitation; real OS sandbox is separate future work (SPEC-28 SH-05) |
| R3 | Oracle pinning blocks legitimate behaviour/test changes | MED (self-build throughput) | Intended fail-closed behaviour; a human updates baseline tests in a separate reviewed commit before the mission; document the procedure |
| R4 | **Windows newline/byte mismatch in the audited PATCH** (one test fails; recovery CAS cannot roll back CRLF promotion) | **HIGH if ignored** | Mandatory C1b fixture fix + normalization + byte-invariant guard (section 4.7). Single most important correctness fix |
| R5 | Legacy missions (29 pending, #5 interrupted) are not resumable under the new harness | MED (self-build would stall/misbehave) | Selection filters `harness_version=2`; explicit legacy resume refused; optional operator-run one-time marking script (needs user approval; not automatic) |
| R6 | Verification flakiness (GUI/offscreen, network-tolerant tests) | LOW-MED (false blocks) | Deterministic env; no runtime retries (they would weaken the gate); fix flaky tests in the repo; optional human-owned exclusion list OPEN, never model-writable |
| R7 | External CRLF checkouts get line-ending normalization on promoted files | LOW | Document; future manifest could preserve per-file newline style |
| R8 | Reviewer LLM (local 9B) quality | MED | Reviewer is an additional gate, never the sole oracle; deterministic verification precedes it; REJECT leaves live untouched |
| R9 | Stage/baseline storage growth (manifest ~1.5 MB + mission baseline ~1.3 MB per mission) | LOW-MED | Stage cleanup on terminal status; sweep 7 days; mission_baselines retention is P1 (documented, not solved here) |
| R10 | DB migration on first run of C5 | LOW (additive) | Back up SQLite before deploying C5; migrations idempotent and tested against the legacy schema |
| R11 (**OPEN**) | `--abandon-stage` ergonomics / who may abandon | LOW | Operator-only CLI; refuses if a journal exists or a live lock is held; GUI stays out of phase 2 |
| R12 (**OPEN**) | Recovery-history GUI / retention policy (SPEC-02A P1) | LOW (future) | Phase 2 only writes/retains recovery points |
| R13 | Attempt budget across resumes | LOW | Persistent attempt ceiling `MAX_TOTAL_STAGE_ATTEMPTS`; resume re-checks it |
| R14 | Stage edited after verification | LOW (caught) | `mark_verified` re-hash + `assert_byte_hash_invariant` + broker CAS; the model cannot reach the stage after verification |
| R15 | Docs test-count claims stale (65/72) | LOW | Update in C8 with the final measured number |

---

## 9. Recommended implementation order (small, independently testable commits)

Each commit must compile, keep the full safe suite green, and be revert-safe. Do not run autonomous self-build at any point during implementation; use the fake-model tests.

### C1a - apply the audited PATCH files verbatim

- copy the 5 PATCH files over their root paths; verify SHA-256 against `SHA256_MANIFEST.json` first;
- commit message: "safety: apply audited staging broker / recovery store / integrity gate v2 (PATCH hashes verified)".

Acceptance:

~~~powershell
python\python.exe -m pytest tests/test_staging_broker_adversarial.py -q -p no:cacheprovider   # 7 passed
python\python.exe -m pytest tests/test_rollback_stub.py -q -p no:cacheprovider               # 2 passed, 1 known Windows newline failure (C1b)
$env:NL_DATA_DIR="$env:TEMP\nl-test-data"
python\python.exe -m pytest tests -q -p no:cacheprovider                                      # 102 passed, 1 failed (documented)
~~~

### C1b - Windows newline re-audit of the PATCH test only

- fix `tests/test_rollback_stub.py` fixture writes (`newline=""`), update `SHA256_MANIFEST.json`, add `build/phase2/PATCH_WINDOWS_REAUDIT.md`;
- acceptance: `pytest tests/test_rollback_stub.py -q` -> 3 passed; full suite -> 103 passed.

### C2 - test seam + model-tool reduction (no staging wiring yet)

- `orchestrator._call_model` extraction (pure refactor), `crew_tools` 4 tools, `filesystem` `newline=""`;
- `tests/test_operational_tools.py` updated; add a unit test that `_call_model` can be monkeypatched (no CrewAI call);
- acceptance: full suite green; tool-list assertions pass; no `run_command` remains in `crew_tools.py`.

### C3 - `core/promotion.py` + unit tests

- no runtime wiring; temp demo roots only;
- acceptance: `pytest tests/test_promotion_stage.py -q` green; full suite green.

### C4 - `core/candidate_verification.py` + tests

- acceptance: `pytest tests/test_candidate_verification.py -q` green; runtime measured; full suite green.

### C5 - DB migrations + missions helpers + runner selection/preflight scaffolding

- additive migrations; `create_mission(harness_version=2)`; selection filters; `run_autonomous` preflight (orchestrator not yet staged);
- acceptance: `test_harness_schema.py` + `test_selfbuild_runner.py` green; full suite green; SQLite backup taken before first run (process note).

### C6a - staged developer/debugger writes (no promote yet)

- tools and text fallback bound to `stage.workspace`; validation gate; `stop_after=developer` keeps the stage;
- acceptance: new orchestrator stage tests + full suite green; tests assert the live tree bytes are unchanged.

### C6b - tester independent verification + mark_verified + review-before-promote

- candidate+oracle suites; repair loop; reviewer candidate diff; no promotion yet;
- acceptance: SH red-path tests (SH-01, SH-04, SH-05) + full suite green.

### C6c - promotion, recovery, journal reconciliation, DB finalize sequence

- `_promote_candidate`, `_finalize_completed/_blocked/_interrupted`, reconcile on resume, crash tests (SH-02/SH-03), happy path, SH-07;
- acceptance: `test_harness_sh.py` green; full suite green; static grep: `completed` written only in `_finalize_completed`.

### C7 - remove the post-hoc gate from `selfbuild_runner.py` + legacy/preflight behavior

- delete the block and imports; runner tests updated;
- acceptance: `pytest tests/test_selfbuild_runner.py -q` green; full suite green; static greps (no `p.write_text(baseline_content`, no `detect_stub(` in the runner).

### C8 - docs + final acceptance

- update `docs/07_SAFETY.md`, `docs/CURRENT_STATE.md`, `docs/02_SELF_BUILD_ROADMAP.md`, SPEC-28 status; record evidence from C1-C7; update counts;
- final acceptance:

~~~powershell
$env:NL_DATA_DIR="$env:TEMP\nl-final-data"
python\python.exe -m pytest tests -q -p no:cacheprovider        # all green (expected ~148)
python\python.exe scripts\verify_relocation.py --json            # read-only relocation gate
python\python.exe nl_agent.py selfbuild --help                   # CLI smoke (argparse only)
python\python.exe -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; import nl_coding_agent.gui.main"
git status --porcelain                                          # only intended files
~~~

The SH fake-model suite is the acceptance harness; a real autonomous self-build run is a separate, Lead-approved activity after phase 2 (SPEC-28 section 7).

---

## 10. Definition of done (phase 2)

- [ ] PATCH files applied, hashes verified; Windows newline re-audit recorded; full suite green.
- [ ] No model-facing write can reach the live tree: tools bound to `stage.workspace`; text fallback staged; `run_command`/`run_tests` absent from model tools.
- [ ] `stage_candidate` at mission start; `validate_candidate` after model output; candidate and oracle suites run in disposable copies; both green before `mark_verified`.
- [ ] `save_snapshot` before the first live write; `promote_staged` with journal+CAS; `rollback_from_snapshot(expected_post_hashes=...)` on failure/reconcile; recovery point never in the target project's source paths.
- [ ] `missions.status='completed'` only after promotion; every gate failure `blocked`; post-hoc baseline rewrite in `selfbuild_runner` deleted.
- [ ] Crash-resume matrix (journal present, crash between files, crash before finalize, stage missing) covered by tests and passing.
- [ ] SH-01..SH-07 pass with fake model output and no Ollama; existing suite migrated and green.
- [ ] Docs updated only after the wiring is real; evidence recorded in `docs/CURRENT_STATE.md`; no claim of OS sandbox.
- [ ] Relocation gate (`scripts/verify_relocation.py`) still green; no unrelated files in the final diff.

---

## Appendix A - prototype evidence log (for the implementer)

All commands ran in the user temp directory; the live repo was untouched (`git status` checked).

1. Source-only copy: 182 files / 1.32 MB; full pytest with `python\python.exe`, `NL_DATA_DIR=<temp>`, `QT_QPA_PLATFORM=offscreen`: **13.5 s, 93 passed, 1 failed** (old `test_rollback_stub` -> `FileNotFoundError: data/mission_baselines/42.json`).
2. PATCH applied over that copy: **13.8 s, 103 collected, 102 passed, 1 failed** (`test_rollback_stub::test_restore_only_known_agent_postimage`, `blocked == ['planner.py']`). Root cause proven: fixture `write_text` writes CRLF, expected hash is `sha256_text` of LF; with `newline=""` the scenario restores successfully (measured).
3. `stage_candidate` on the real-size tree: **0.59 s**, manifest **1.47 MB**, 181 baseline files; validate + mark_verified + save_snapshot (2 files, **18 KB**) + promote: 2 files promoted, journal created then deleted; both rollback paths restored byte-identically.
4. Oracle-overlay prototype: buggy source + matching weakened test -> candidate suite **0 failures**, oracle suite **1 failure**.
5. CRLF promotion probe: model-tool-style write (default `write_text`) -> staged CRLF; `promote_staged` wrote CRLF to live; recovery `expected_post_hashes=delta["after"]` -> `blocked` (rollback impossible). With staged LF bytes (`newline=""`), promotion wrote LF and recovery rolled back exactly. Hence section 4.7.
6. Read-only DB inventory: 45 missions (13 completed, 2 blocked, 1 interrupted, 29 pending); 1 project; `data/staging/999` leftover from the old unsafe test.

## Appendix B - audited API cheat-sheet used by the integration

~~~text
staging_broker.stage_candidate(project_root, mission_id, scope_paths) -> Path
staging_broker.validate_candidate(stage_dir, baseline_path=None, scope_paths=None) -> dict
staging_broker.mark_verified(stage_dir, *, passed, evidence) -> None
staging_broker.promote_staged(stage_dir, project_root) -> {promoted, blocked, reason}
staging_broker.rollback_from_staged(stage_dir, project_root, baseline_path=None) -> {restored, blocked, reason}
staging_broker.StagingRejected  (RuntimeError)

recovery_store.save_snapshot(mission_id, scope_paths, root=".", *, recovery_dir=None) -> Path
recovery_store.rollback_from_snapshot(rollback_path, files_to_check, *,
                                      expected_post_hashes=None, project_root=None) -> {restored, blocked, reason}
recovery_store.sha256_text(text) -> str ; sha256_bytes(bytes) -> str ; _atomic_write(path, bytes)

code_integrity_gate.detect_stub(content, baseline=None) -> bool
code_integrity_gate.detect_weak_test(baseline, current) -> bool
~~~

## Appendix C - status vocabulary

- `missions.status`: `pending | running | completed | failed | blocked | interrupted` (existing).
- `missions.promotion_status`: `staged | validated | verified | reviewed | promoting | promoted | candidate_rejected | verification_failed | review_rejected | cas_conflict | rollback_conflict | rollback_complete | stage_missing | abandoned | error`.
- `verification_runs.command`: `verify:candidate ...`, `verify:oracle ...`, `harness:validate`.
- Handoff payload keys added: `stage_dir`, `scope`, `staged_paths`, `promoted`, `hashes`, `oracle`, `candidate`, `report`, `code`, `details`.

## Appendix D - anchor index at HEAD `6cfacfa` (re-verify at `338def0`)

| File | Line / region | Purpose |
|---|---|---|
| `nl_coding_agent/agents/orchestrator.py` | 49-52 imports; 146-215 text actions; 218 class; 350-359 scope; 361-418 finalize; 422-480 run_mission; 482-609 run_locked; 613-719 developer; 721-788 tester; 790-861 debugger; 863-962 reviewer | replace/wire per section 3.9 |
| `nl_coding_agent/tools/crew_tools.py` | 17-81 | 4 tools |
| `nl_coding_agent/core/selfbuild_runner.py` | 12-13 imports; 293-326 post-hoc gate; 151-363 runner | delete block; filter selection; preflight |
| `nl_coding_agent/persistence/database.py` | 142-155 migrations | add 3 columns |
| `nl_coding_agent/persistence/missions.py` | 35-46 create_mission | harness_version + helpers |
| `nl_coding_agent/cli.py` | 413-425 resume; 446-501 autonomous | legacy refusal + messages |
| `tests/test_operational_tools.py` | 67-76 | 4-tool assertion |

## Appendix E - current-status postscript

The Lead reports relocation P0 fully verified (gate 30/30 PASS, clean HEAD `338def0`, independent verifier `overall_ok=true`, F1-F6 resolved), so phase 2/task-6 is unblocked. The anchors above were taken at `6cfacfa`; re-check them against `338def0` before editing (if a line moved, use the function names, not the line numbers). Anchor check at `6cfacfa`: `orchestrator.py` is 962 lines; `_run_developer_stage` starts at line 613, `_run_tester_stage` at 721, `_run_debugger` at 790, `_run_reviewer_stage` at 863 - matching the task brief.




# SH-07 Tier B - Real Local-Model Acceptance Evidence

Date: 2026-10-28. Stage 3 exit gate (two consecutive supervised missions with local
models, no cloud/network). Tier A (deterministic fake-model) is verified; Tier B was
attempted twice against isolated git worktrees with local Ollama models.

Raw artifacts (copied from the git-ignored build evidence dirs):
- `attempt1/` - first live attempt at HEAD `e81a916` (2 docs-only missions, 0 implementation)
- `attempt2/` - second live attempt at HEAD `2a44460` (quality-gated; invalid candidate blocked)
Each attempt contains `evidence.json`, `summary.md`, `console.log`, and (attempt2) `git.diff`.

## Attempt 1 (quality-gate hole found)

- Command: `python scripts/run_supervisor_sh07.py --mode live --confirm-live --worktree <isolated worktree>`
  at HEAD `e81a916`, temp `NL_DATA_DIR`, local models only.
- Runner verdict at the time: PASS (2 completed missions), but manual review showed both
  "completed" missions only added Markdown spec files (`specifiche/...`) - no code or tests.
- Root cause: backlog source-reference paths were included in the composed mission goal, so
  the orchestrator derived a documentation-only write scope; reviewer accepted docs-only
  candidates for implementation requirements.
- Fixes (`2a44460`): source-reference paths removed from the mission goal plus an explicit
  implementation contract; orchestrator rejects documentation-only candidates for
  requirement-linked missions before independent verification; Tier B pass criteria require
  code/test changes; regression tests added.
- Raw artifacts: `attempt1/` (evidence.json + console.log).

## Attempt 2 (quality gates active)

- Command: same, at HEAD `2a44460`, fresh isolated worktree, temp `NL_DATA_DIR`.
- Result: **BLOCKED (honest failure)**, 0 completed / 2 failed, 0 promotions, worktree
  clean (status empty, empty diff), run status BLOCKED with fail-fast reason.
- Mission NL-BP-051 sequence: developer candidate modified/weakened
  `tests/test_selfbuild_mode.py`; validation rejected it ("Destructive code change or
  invalid syntax", "Weakened test"), the retry was rejected again, and the supervisor
  recorded HARD_BLOCK + dead-letter. No live write occurred; the staged candidate stayed
  on the stage.
- Verdict: Tier B **NOT PASSED**. The local 7B developer model could not produce a valid
  implementation of NL-BP-051, while the safety gates correctly prevented any corruption.
- Consequences: NL-BP-063 (two consecutive real local-model missions without manual repair)
  remains **BLOCKED**; the supervisor default mode remains **off**, automatic mode stays
  opt-in and gated by explicit human enablement; no cloud/network was used.

## Stage-3 exit decision (evidence-based)

The plan allows stage-3 exit with Tier A verified and Tier B explicitly recorded as blocked
with automatic mode disabled. That is the recorded outcome: the supervisor, preflight,
queue/lease, control, evidence and quality gates are implemented and verified; real
local-model endurance remains an open, evidence-backed blocker rather than a weakened gate.

## Re-run

To re-run when a stronger local developer model is configured:

`powershell
python\python.exe scripts\run_supervisor_sh07.py --mode live --confirm-live --worktree <clean isolated git worktree outside the repo>
`

A pass requires: run status completed, 2 completed missions, each with at least one code/test
change, clean quality-gate evidence, and no cloud/network grants.

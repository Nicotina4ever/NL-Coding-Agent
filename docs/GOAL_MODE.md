# Goal Mode (Stage 8) - Goals, Milestones and Decomposition

**Status:** G1/G2/G3/G5/G6/G8 foundation implemented. Durable goals and milestones, lifecycle,
dependency validation, structured decomposition, independent completion verification and a
non-executing `goal` CLI are available. Completion is **verification-gated**: source-backed
evidence is verified first and a goal can never complete from a checklist, plan, progress or
agent claim. This is still **not** autonomous goal execution: no mission is created/started
and no agent/model runs.

**Implementation:** `nl_coding_agent/persistence/goal_store.py` (SQL persistence),
`nl_coding_agent/core/goals.py` (GoalService), `nl_coding_agent/core/goal_verification.py`
(independent verifier), `nl_coding_agent/app/services.py` (lazy goal facade + completion
gate + replan/links/activity/queue/approval/inspection), `nl_coding_agent/cli.py` (`goal` command group).
**Tests:** `tests/test_goals_core.py`, `tests/test_goal_verification.py`,
`tests/test_app_services_goals.py`, `tests/test_goals_cli.py`,
`tests/test_goal_completion_gate.py`, `tests/test_goal_replanning.py`,
`tests/test_goal_approval.py` (targeted tests; temp `NL_DATA_DIR`).

---

## 1. Data model (additive SQLite)

New additive tables, created through the normal app `init_db` schema path:

- `goals`: id, project_id, title, objective, acceptance_criteria JSON, priority
  (P0-P3), status (planned/active/paused/blocked/completed/cancelled), dependencies JSON
  (goal ids), template_id/version, source, origin (user/import/template), attachments JSON,
  reference_metadata JSON, created_at/updated_at.
- `milestones`: id, goal_id FK, title, description, priority, status, ordering
  (unique per goal), dependencies JSON (milestone ids), acceptance_criteria JSON,
  evidence_refs JSON, created_at/updated_at.
- `goal_missions`: links goals/milestones to **existing** mission ids
  (`missions`/`tasks` are reused, never forked); role and unique mapping.

No destructive migration, no goal deletion command and no reset command. Existing databases
and legacy tables are preserved; schema creation is idempotent.

## 2. Lifecycle

```text
planned --activate--> active --pause--> paused --resume--> active
   |                     |                |
   |                     +--block--> blocked --unblock--> active
   |                     |                |
   +---------------------+----------------+--> cancelled
active --complete (explicit; verified evidence; all milestones completed; >=1 milestone)--> completed
planned/completed/cancelled terminal rules apply
```

Rules:

- invalid transitions return a structured `lifecycle` error and never change status;
- terminal goals (`completed`/`cancelled`) are immutable through goal/milestone updates;
- `completed` is only reachable through explicit completion after the independent verifier
  returns `verified` (see section 4b); GoalService still requires active status, at least one
  milestone and all milestones completed. A checklist/plan/progress/claim alone never completes;
- completion refusals and dry-runs leave goal status unchanged;
- progress/next-work queries never mutate status; no automatic completion exists.

## 3. CLI usage (no execution)

```powershell
# Isolated app database for a rehearsal/session.
$env:NL_DATA_DIR = "$env:TEMP\nl-goal-demo"

# Create a goal (objective positional; all other fields optional).
python\nl_agent.py goal create "Ship the private beta" --title "Beta" --priority P0 --acceptance "installer works" --json

python\nl_agent.py goal list --status planned --priority P0 --json
python\nl_agent.py goal show 1 --json
python\nl_agent.py goal activate 1
python\nl_agent.py goal pause 1
python\nl_agent.py goal resume 1
python\nl_agent.py goal block 1 --reason "waiting for input"
python\nl_agent.py goal unblock 1
python\nl_agent.py goal cancel 1

# Structured decomposition plan (list, or { "milestones": [...] }), from file or stdin.
python\nl_agent.py goal decompose 1 --plan plan.json --json
Get-Content plan.json | python\nl_agent.py goal decompose 1 --plan - --json

python\nl_agent.py goal next --goal-id 1 --json
python\nl_agent.py goal progress 1 --json
python\nl_agent.py goal progress --json
```

Flags for `goal create`: `--title`, `--project PATH|ID`, `--priority P0..P3`,
`--acceptance` (repeatable), `--dependency ID` (repeatable), `--attachment` (repeatable),
`--reference KEY=VALUE` (repeatable), `--reference-file JSON`, `--from-file JSON`,
`--json`. Attachments/references are metadata only; no file is read/uploaded.

Exit codes: `0` success; `1` validation/not-found/lifecycle/dependency/decomposition
error; `2` usage/argparse or malformed plan input. JSON errors are emitted on stdout
when `--json` is used (and always summarized on stderr); no stack traces.

**No execution flags exist.** Unknown flags (such as `--run`) are rejected by argparse;
the help epilog documents the no-autonomous-run contract and DB isolation.

## 4. Decomposition plan schema

`decompose` accepts a non-empty JSON list of milestone objects (or an object with a
`milestones` list). Each item:

```json
[
  {
    "key": "design",
    "title": "Design the solution",
    "description": "Short bounded description",
    "priority": "P0",
    "dependencies": [],
    "acceptance_criteria": ["design reviewed"],
    "evidence_refs": ["docs/design.md"]
  },
  {
    "key": "build",
    "title": "Implement it",
    "priority": "P1",
    "dependencies": ["design"]
  },
  {
    "title": "Verify",
    "dependencies": ["build"]
  }
]
```

Rules: `key` is optional (auto `m1`, `m2`, ...; unique when supplied);
titles are required, bounded and must not duplicate plan or existing milestone titles;
`dependencies` reference either an existing milestone id in the same goal or a plan key
(no self/missing/duplicate/cycles); unknown fields, empty plans, non-object items, invalid
priorities/criteria and terminal goals are rejected. Milestones are created in plan order with
deterministic ordering; existing milestones are preserved. This is a deterministic structured
plan only - no LLM/network is involved.

## 4b. Verification-gated completion (G3/G5)

Completion is no longer just a lifecycle call: `AppServices.goal_complete` and the CLI run the
independent verifier (`core/goal_verification.py`) first. Verified completion requires every
acceptance criterion to be satisfied by fresh, trusted, source-backed evidence
(test/command/artifact/reviewer/user/file_check); untrusted/model/self claims, stale evidence,
contradictions and missing criteria are refused.

```powershell
# read-only report; exit 0 only when verified
python\nl_agent.py goal verify 1 --evidence evidence.json --criteria criteria.json --json

# explicit completion: evidence required unless --dry-run
python\nl_agent.py goal complete 1 --evidence evidence.json --criteria criteria.json --json
python\nl_agent.py goal complete 1 --evidence-json '[{"type":"test","source":"pytest:tests","exit_code":0,"trust":"trusted"}]' --dry-run --json
```

Evidence JSON may be a list, a single object, or `{"evidence": [...], "criteria": [...]}`.
Minimal item: `{"type": "test", "source": "pytest:tests", "result": "pass", "trust": "trusted", "exit_code": 0}`.
Criterion schema: `{"id": "C1", "text": "tests pass", "required_evidence_types": ["test"], "stale_after_s": 3600}`
(see `docs/GOAL_VERIFICATION.md` for the full evidence contract).

Gate behavior:

- refusal (unverified/partial/contradicted/stale/untrusted or no effective criteria) returns
  verdict, criterion results, blockers and outstanding criteria with status unchanged;
- a verified report is persisted, then GoalService.complete_goal() is called explicitly; if
  lifecycle/milestone rules reject completion, the goal still stays unchanged;
- `--dry-run` verifies/report but never changes status;
- `goal verify` is read-only and `goal_verifications` exposes append-only records;
  `goal_false_completions` reports completed goals without a verified latest record.

Exit codes: `goal verify` 0 verified, 1 unverified/partial/contradicted/missing criteria,
2 usage/malformed JSON; `goal complete` 0 verified+completed (or dry-run verified), 1 refusal/
completion rejected, 2 usage/missing evidence.

## 4c. Versioned replanning, links, activity and queue (G6)

Replanning replaces the **current milestone set** without rewriting the original goal
objective/title. Each replan appends a `goal_plan_versions` snapshot (objective snapshot,
full milestone snapshot with dependency ids, rationale, trigger, evidence refs, diff) and
marks only the newest version current; prior versions are preserved. First replan is
version 1; later replans increment.

Triggers: `manual` (default), `evidence`, `failure`, `constraint`. A
non-empty `rationale` is always required; `evidence` requires non-empty
`evidence_refs`. Plan schema is the decomposition schema plus optional
`risk`, `validation_strategy` and `mission_intent` per milestone. Validation is
strict (empty plan, unknown fields, duplicate keys/titles, missing existing ids,
self/cyclic dependencies are refused). Items matching an existing milestone title are
updated in place (milestone id and existing mission link preserved); other current
milestones are removed and new ones created in plan order. `goal_plan_versions`,
`goal_current_plan`, `goal_plan_diff` expose snapshots/diffs without model/network.

Mission links are **existing missions only** (`goal_links` returns mission id/title/status/
role; no mission is created/started). `goal_activity` returns goal-scoped
`source='goals'` audit events (create/lifecycle/decompose/replan/verification/completion/
milestone/link). `goal_queue` is read-only: `not_connected` when no mission is linked,
`linked_not_queued` when links have no supervisor queue row, or `available` with the
linked `mission_queue` entries. No execution flags exist.

```powershell
python\nl_agent.py goal replan 1 --plan plan.json --rationale "evidence changed" --trigger evidence --evidence evidence.json --json
python\nl_agent.py goal versions 1 --diff --json
python\nl_agent.py goal links 1 --json
python\nl_agent.py goal activity 1 --json
python\nl_agent.py goal queue 1 --json
```

CLI exit codes follow the other goal commands: 0 success, 1 validation/not-found/lifecycle/
dependency/decomposition, 2 usage/argparse/malformed JSON. Goal commands dispatch before
model config and use `NL_DATA_DIR` isolation.

## 4d. Plan approval and read-only work inspection (G8)

Plan approval is explicit metadata, separate from execution and from completion:

- `GoalService.approve_plan(goal_id, version=None, rationale=None, approver="user")`
  approves the current plan version by default or an explicit existing version, records
  approved_at/approved_by/approval_note, emits `source=goals` `plan_approved` audit, and is
  idempotent (a second call returns already_approved without a duplicate audit).
- No current plan version means approval is refused; missing/invalid versions are
  structured errors. `approver` must be non-empty and rationale/note is bounded.
- Approval never executes/instantiates missions or workers and does not approve future
  plans: `replan_goal` always creates a new unapproved version, while an older approved
  version remains historically approved. `goal_current_plan` / `goal_plan_versions`
  expose `approved`, `approval_status`, `approved_at`, `approved_by` and
  `approval_note`.

Read-only inspection APIs (no mission creation, execution or worker control):

- `goal_mission_tasks(goal_id)`: only linked missions with tasks
  (id/title/status/agent_role/depends_on); explicit `not_connected` when no mission is linked.
- `goal_queue_entries(goal_id)`: only `mission_queue` rows for linked missions
  (state/priority/attempts/lease_owner/claimed_at/scheduled_at/finished_at); explicit
  `not_connected` when no mission is linked.
- `goal_active_work(goal_id)`: assigned tasks (non-empty agent_role) plus
  `supervisor_runs` scoped by goal/mission project where available
  (id/mode/status/owner_id/owner_pid/heartbeat_at); states `not_connected` / `idle` /
  `active`. It never starts/claims/stops workers.

```powershell
python\nl_agent.py goal approve 1 --version 2 --rationale "approved for execution planning" --json
python\nl_agent.py goal tasks 1 --json
python\nl_agent.py goal workers 1 --json
```

Exit codes follow other goal commands (0 success, 1 validation/not-found, 2 usage); there
are no execution flags and no worker/mission execution is performed.

## 5. AppServices facade

`services.goal_*` is a thin lazy wrapper over GoalService (no duplicated logic):

| Method | Purpose |
|---|---|
| `goal_create` | create goal from objective + optional fields |
| `goal_list` | list/filter by project/status/priority (bounded) |
| `goal_get` / `goal_update` | read/update non-terminal goals |
| `goal_activate/pause/resume/block/unblock/cancel` | validated lifecycle |
| `goal_decompose` | structured plan -> milestones |
| `goal_milestones` | list milestones |
| `goal_next_work` | eligible pending milestones respecting dependencies/priority |
| `goal_progress` / `goal_progress_summary` | read-only progress |
| `goal_verify` | read-only independent verification report |
| `goal_verifications` / `goal_verification_outstanding` | append-only records/outstanding |
| `goal_false_completions` | read-only false-completion detection |
| `goal_complete` | verification-gated explicit completion (dry-run supported) |
| `goal_replan` / `goal_plan_versions` / `goal_current_plan` / `goal_plan_diff` | versioned replan snapshots and diffs |
| `goal_links` | linked existing missions (id/title/status/role) |
| `goal_activity` | goal-scoped source=goals audit timeline |
| `goal_queue` | read-only linked mission queue/status or explicit not-connected state |
| `goal_approve_plan` | explicit idempotent plan-version approval (metadata only) |
| `goal_mission_tasks` | read-only linked missions + tasks |
| `goal_queue_entries` | read-only mission_queue rows for linked missions |
| `goal_active_work` | read-only assigned tasks + supervisor runs (not-connected/idle/active) |

All methods return `{"ok": bool, ...}` envelopes; failures return
`{"ok": false, "error": {"code": "validation|not_found|lifecycle|dependency|decomposition|verification|error", "type": ..., "message": ...}}`.
`goal_complete` refusal carries `verdict`, `criteria`, `blockers`, `outstanding`, `status_mutated: false`.
GoalService is constructed lazily on first use; constructing AppServices does not scan or
mutate goal tables. No mission creation, execution, model or network call is performed.

## 6. DB isolation and reproducibility

Goal data is stored in the app SQLite database under `NL_DATA_DIR` (default
`data/nl_coding_agent.sqlite3`). There is deliberately no reset/delete command:
use a fresh `NL_DATA_DIR` to isolate a run. The CLI goal commands do not require a models
config file and never touch the live mission execution path; tests use a temp
`NL_DATA_DIR` and dedicated temp project directories.

## 7. Limits and remaining work (not claimed)

- No mission creation/execution, no agent/model/LLM decomposition and no GUI Goal Mode page.
- No dependency-aware scheduling, execution FSM or autonomous goal runner. Verification
  judges only supplied/recorded evidence; it does not execute tests/commands, create
  artifacts or prove absolute product correctness (human/external evidence is still required).
- Replanning/model intent does not execute missions: goals/links/queue/tasks/workers are
  read-only planning surfaces; approval is metadata only and a future runner must still
  enqueue/start missions explicitly. No worker control/queue mutation exists.
- No goal templates/import UI, no reset/delete command, no multi-user concurrency controls
  beyond SQLite, no cross-project scheduler.
- Completion is available through CLI/facade only with verified evidence; the verifier does
  not execute anything and GUI completion remains unwired.
- No GUI editing in this increment; the GUI Goal Mode remains a future increment.
- Real autonomous goal execution, GUI Goal Mode replan/queue editing, scheduling and
  external-evidence collection remain **MANUAL-PENDING** and outside G1/G2/G3/G5/G6/G8.

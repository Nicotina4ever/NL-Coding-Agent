# Goal Mode (Stage 8) - Goals, Milestones and Decomposition

**Status:** G1/G2 foundation implemented. Durable goals and milestones, lifecycle,
dependency validation, structured decomposition, AppServices facade and a non-executing
`goal` CLI are available. This is **not** autonomous goal execution: no mission is
created/started, no agent/model runs, and no verification/completion engine is claimed yet.

**Implementation:** `nl_coding_agent/persistence/goal_store.py` (SQL persistence),
`nl_coding_agent/core/goals.py` (GoalService), `nl_coding_agent/app/services.py`
(lazy goal facade) and `nl_coding_agent/cli.py` (`goal` command group).
**Tests:** `tests/test_goals_core.py`, `tests/test_app_services_goals.py`,
`tests/test_goals_cli.py` (targeted tests; temp `NL_DATA_DIR`).

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
active --complete (explicit, all milestones completed, >=1 milestone)--> completed
planned/completed/cancelled terminal rules apply
```

Rules:

- invalid transitions return a structured `lifecycle` error and never change status;
- terminal goals (`completed`/`cancelled`) are immutable through goal/milestone updates;
- `completed` is only reachable through explicit `complete_goal()` (CLI does not expose
  execution; the facade does expose it) and requires all milestones completed;
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

All methods return `{"ok": bool, ...}` envelopes; failures return
`{"ok": false, "error": {"code": "validation|not_found|lifecycle|dependency|decomposition|error", "type": ..., "message": ...}}`.
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
- No goal verification/completion engine, dependency-aware scheduling or execution FSM
  (a later increment may add independent verification; the `blocked`/`completed`
  states exist but only explicit service calls change them).
- No goal templates/import UI, no reset/delete command, no multi-user concurrency controls
  beyond SQLite, no cross-project scheduler.
- No CLI completion command; completion is available through the service/facade only.
- No GUI editing in this increment; the GUI Goal Mode remains a future increment.
- Real autonomous goal execution and verification remain **MANUAL-PENDING** and outside G1/G2.

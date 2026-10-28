# Stage 3 - Persistent Autonomous Supervisor: Design and Implementation Plan

**Status:** design-only deliverable (no runtime code changed by this document).
**Task:** shared `task-20` (design). Owner: harness-wirer.
**Repository baseline:** HEAD `221d310` (stage 2 harness C6/C7/C8 merged; full suite 149 passed).
**Target program stage:** 3 - "Persistent autonomous supervisor and verified handoff" (`docs/product-blueprint/INDEX.json` program_order, `docs/PRODUCT_BACKLOG.md` program execution order).
**Backlog requirements covered:** NL-BP-012, 050, 051, 052, 053, 061, 062, 063, 064, 065, 066, 067, 075, 077 (stage 3). Primary: NL-BP-061/062/063/064 (P0). Stage-2 dependencies: NL-BP-072 (permissions), NL-BP-073 (tool registry), NL-BP-076 (cloud enforcement).
**Inputs read:** `specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md`, `specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md`, `specifiche/02_SELF_BUILD_E_RECOVERY.md`, `specifiche/28_SELF_HEALING_AGENT_HARNESS.md` (SH-07), `specifiche/15_SICUREZZA_E_PRIVACY.md`, `specifiche/13A_GPU_CONTENTION_CLOUD_FALLBACK.md`, `docs/07_SAFETY.md`, `docs/HARNESS_ACCEPTANCE.md`, `docs/CURRENT_STATE.md`, `docs/PRODUCT_BACKLOG.md`, `docs/product-blueprint/INDEX.json`, current `core/selfbuild_runner.py`, `core/promotion.py`, `core/mission_lock.py`, `persistence/database.py`, `persistence/missions.py`, `agents/orchestrator.py`, `cli.py`, `app/services.py`, `models/providers.py`, `resources/scheduler.py`, `config/models.yaml`.

---

## 0. Executive summary

The current self-build capability is a **bounded functional loop** (`run_autonomous`, max 5 missions) that selects durable missions, falls back to the fixed roadmap file `docs/NEXT_SELF_BUILD_MISSION.md`, runs one synchronous orchestrator mission at a time, and keeps lightweight state in `data/selfbuild_state.json` under a file lock. It has no durable queue, no lease/heartbeat, no backlog-driven planner, no persisted budget/retry policy, no approval state, no evidence ledger beyond handoffs/verification runs, and no service lifecycle independent of the calling chat/CLI.

Stage 3 replaces that loop with a **persistent, non-LLM supervisor service** composed of the already-working mission engine:

1. a **durable queue** (`mission_queue`) with a spec state machine, idempotency keys and claim tokens;
2. a **single-owner lease + heartbeat** (`supervisor_leases`) plus a per-mission file lock for the working tree;
3. a **deterministic planner** that consumes the indexed backlog (`docs/product-blueprint/INDEX.json` mirrored into SQLite `backlog_items`) and produces the next mission, with no dependency on `NEXT_SELF_BUILD_MISSION.md`;
4. **fail-closed preflight** (promotion journals, stale stages, legacy missions, migration readiness, permissions, model availability, autonomy mode);
5. **start/stop/pause/resume** commands persisted in SQLite and honored at safe mission boundaries, independent of any chat session;
6. **budgets/retry/dead-letter** semantics and a **per-mission evidence ledger**;
7. an **SH-07 acceptance plan** with deterministic fake-model CI evidence and a separately gated real-local-model evidence run on an isolated worktree.

The design is additive: it reuses `promotion` (staged candidate lifecycle), `MultiAgentOrchestrator.run_mission` (developer -> tester -> reviewer, promotion last), `mission_lock`, `persistence` and the event bus. It does not rewrite the harness and does not introduce a second mission engine.

---

## 1. Design decisions (top 5)

1. **SQLite is the supervisor's operational source of truth; `INDEX.json`/`PRODUCT_BACKLOG.md` stay human-authored.** The supervisor mirrors the backlog into `backlog_items` (with content hashes and a sync fingerprint), schedules from SQLite only, and writes mission outcomes to SQLite (`supervisor_status`). It never rewrites the Markdown or the index from a model-driven run. Promoting a requirement to `verified` in the authored backlog remains a human/backend, evidence-reviewed step (C3e produces the exact diff to apply). This prevents self-certification and keeps the backlog rules in `docs/PRODUCT_BACKLOG.md` ("never overwrite this file from an agent session").
2. **Reconciliation over distributed transactions.** SQLite helpers today open one connection per call, so the supervisor cannot make "mission row + queue row + backlog row" one ACID transaction across modules. Instead every transition is idempotent and **derived from durable facts** (missions row, stage manifest, promotion journal, verification runs). Startup `reconcile()` repairs queue/backlog rows from those facts. This matches the existing crash-recovery philosophy (promotion journal, CAS, resume).
3. **One supervisor per project via lease CAS; one mission at a time in C3.** A lease row with owner id/pid/host, version and TTL is acquired with a single compare-and-swap statement; a daemon heartbeat thread renews it. A stale lease is reclaimed only after TTL expiry **and** proof the owner pid is not alive on this host. Missions remain serialized (SPEC-26 allows parallel only for truly independent workstreams; that is deferred). A lightweight `machine_leases(resource='inference')` serializes local inference across projects that share the app-data DB.
4. **The fixed roadmap is deprecated, not silently kept.** Planner selection reads `INDEX.json` program_order + requirements. `NEXT_SELF_BUILD_MISSION.md` survives only for the manual `selfbuild --goal/--from-roadmap` path (legacy compatibility) and is not consulted by the supervisor. A missing/corrupt index is **blocked**, never silently replaced by the roadmap.
5. **Autonomy is opt-in and fail-closed.** Modes Off/Assisted/Automatic are persisted per project in `app_settings`; default is Off. Automatic still requires: base permission grants (read/write/execute), no delete/network/cloud without explicit grant, local models by default, positive budgets, and a clean preflight. Every model invocation passes `assert_model_permitted` before LLM construction (stage-2 NL-BP-072/076), so cloud/network escalation is impossible from the supervisor without grants, even if a model suggests it.

---

## 2. Current state and gap analysis

| Requirement | Current state (HEAD 221d310) | Gap for stage 3 |
|---|---|---|
| NL-BP-051 durable mission persistence/resume | missions/tasks/attempts/handoffs/verification_runs tables; baseline JSON; interrupted reset; staging_dir/promotion_status; orchestrator resume | no queue/idempotency key/lease; resume command is manual |
| NL-BP-052 single-writer lock | `core/mission_lock.py` O_EXCL + pid liveness + stale reclaim; `data/selfbuild.lock` around run_autonomous | no per-supervisor lease/heartbeat; no contention test |
| NL-BP-061 supervisor daemon | bounded `run_autonomous` loop in-process; state JSON; promotion preflight; legacy filter | no always-on service, durable queue, lease/heartbeat, start/stop/pause independent of chat |
| NL-BP-062 backlog selection | `next_mission` reads fixed Markdown; `core/autonomous_roadmap_planner.py` exists but nothing imports it | no INDEX.json/SQLite backlog mirror, no READY resolver, no idempotency/dedupe |
| NL-BP-063 two consecutive verified missions | never executed on the new harness (SH-07 PENDING) | needs supervisor + acceptance evidence |
| NL-BP-064 autonomy modes/budgets/approvals | CLI flags only; cloud label read-only | no persisted modes, budgets, approval queue |
| NL-BP-065 bounded repair | orchestrator tester/debugger loop bounded by NL_MAX_REPAIRS, attempts persisted | no failure-signature classification, strategy change or dead-letter at supervisor level |
| NL-BP-072/073/076 permissions/tool registry/cloud | task-18/task-19 in flight (stage 2) | supervisor must consume grants; no duplicate permission logic |
| NL-BP-075 diagnostics | events table (no correlation columns), log files | no correlation ids, supervisor diagnostics/status surface |
| NL-BP-050/066/067 goals/teams | not implemented (stage 3/4) | queue links to requirement ids; Goals hierarchy deferred (see section 18) |

Existing pieces to reuse unchanged or nearly unchanged: `core/promotion.py` (stage/validate/verify/promote/reconcile/preflight/sweep/cleanup), `core/staging_broker.py`, `core/recovery_store.py`, `core/candidate_verification.py`, `core/workspace.py`, `agents/orchestrator.py` pipeline (with one additive control hook), `core/mission_lock.py`, `persistence/missions.py`, `app/services.py` event bus/scheduler patterns, `models/providers.py`, `resources/scheduler.py`.

---

## 3. Non-negotiable invariants

Inherited from SPEC-02/02A/15/21/26/28 and existing harness:

1. No live write before the staged candidate passes validation, independent candidate+oracle verification and reviewer APPROVE; promotion is the last gate.
2. Supervisor state is durable before success is reported; no "completed" without passing gates and persisted evidence.
3. A mission runs under the working-tree lock; a supervisor only runs a mission whose queue row it owns (claim token + lease).
4. Stop/pause are honored at safe boundaries; stop never aborts a promotion mid-write and never kills processes the supervisor does not own.
5. No cloud/network escalation without explicit persisted grant; no silent cloud fallback; local-only is the default.
6. No destructive action (delete/migrate/publish/install) autonomously; DELETE is denied by default and the model tool surface has no delete/shell tool.
7. A newer human edit is never overwritten: CAS/recovery semantics stay authoritative; conflicts block and ask for reconciliation.
8. The supervisor is non-LLM policy code; no model tool can grant permissions, change modes/budgets, pause itself out of policy, or select its own next task.
9. Autonomy Off is always honored, and Off is the default.
10. The backlog index is read-only for the supervisor; authored status/evidence updates are human/backend-reviewed.

---

## 4. Component map and data flow

~~~text
                        +---------------------------------------------------------------+
                 CLI    |  nl_agent.py supervisor run|start|stop|pause|resume|status    |
                 GUI    |  app/services.py supervisor_* (event bus, thread)            |
                        +------------------------------+--------------------------------+
                                                       |
                        +------------------------------v--------------------------------+
                        | core/supervisor.py  (non-LLM service, C3c)                    |
                        |  preflight -> reconcile -> loop -> select -> execute -> record|
                        |  lease/heartbeat, budgets, stop/pause, failure classification |
                        +----+----------------------+----------------------+------------+
                             |                      |                      |
             +---------------v------+  +------------v---------+  +---------v----------------+
             | core/backlog.py      |  | persistence/         |  | core/run_control.py      |
             |  INDEX.json loader   |  | supervisor_store.py  |  |  stop/pause checkpoints  |
             |  sync, READY select  |  |  queue, lease, runs, |  |  (threading.Events)      |
             |  idempotency keys    |  |  backlog, evidence   |  +---------+----------------+
             +----------+-----------+  +----------+-----------+            |
                        |                         |                        |
             +----------v-----------+   +---------v-------------+   +------v-----------------+
             | docs/product-        |   | SQLite (app data dir) |   | MultiAgentOrchestrator |
             | blueprint/           |   |  supervisor_leases    |   |  run_mission(          |
             | INDEX.json (authored)|   |  supervisor_runs      |   |    control=...)        |
             | docs/PRODUCT_BACKLOG |   |  mission_queue        |   |  staged harness,       |
             |  (human view)        |   |  backlog_items        |   |  candidate+oracle      |
             +----------------------+   |  mission_evidence     |   |  verification,         |
                                        |  approvals            |   |  promotion last        |
                                        |  machine_leases       |   +------+-----------------+
                                        |  events (+corr ids)   |          |
                                        +-----------------------+          |
                                                        +------------------v----------------+
                                                        | core/promotion.py                 |
                                                        | stage/journal/CAS/recovery/       |
                                                        | reconcile/preflight/sweep         |
                                                        +-----------------------------------+
~~~

### 4.1 One supervisor run (happy path)

1. `Supervisor.preflight()`: relocation readiness, lease, promotion journal/stage state, legacy/failed queue repair, autonomy mode, permissions, backlog sync, model/resource availability, git state (read only), stale stage sweep.
2. `Supervisor.acquire()`: CAS lease row; start heartbeat thread; start `supervisor_runs` row.
3. `Supervisor.reconcile()`: repair queue/backlog rows from mission/stage/journal facts (idempotent).
4. Loop up to `max_missions_per_run`:
   - consume stop/pause commands; check wall clock/mission budget;
   - take the first resumable queue item (CLAIMED/RUNNING/INTERRUPTED) or select a new READY requirement from `backlog_items`;
   - claim queue item (CAS token), ensure/reuse mission row (`missions.requirement_id`), build the goal;
   - acquire `machine_leases('inference')` and `mission_lock` (the orchestrator also takes the mission lock);
   - call `orchestrator.run_mission(mission_id, control=RunControl)`;
   - record outcome: mission evidence rows, queue state, backlog progress, events, budget counters;
   - on blocked/needs-fix: retry per policy or stop; never start unrelated work while a requirement is hard-blocked (fail-fast default).
5. `Supervisor.release()`: release inference lease, finish run row, release lease; heartbeat stops. Stage cleanup is orchestrator/promotion responsibility (already implemented).

### 4.2 Why the orchestrator stays the mission engine

The orchestrator already implements the full evidence pipeline and crash semantics (C6). The supervisor must not duplicate or bypass it: it creates/selects a mission row and calls `run_mission`. This keeps one writer of `missions.status` (`_finalize_completed`) and one promotion path.

---

## 5. State machines

### 5.1 Supervisor run states (`supervisor_runs.status`)

~~~text
STARTING -> RUNNING
RUNNING  <-> PAUSED                 (pause requested; honored at mission boundary)
RUNNING  -> WAITING_FOR_RESOURCES   (models/GPU/quota unavailable; backoff, checkpoint kept)
RUNNING  -> WAITING_FOR_APPROVAL    (risky action / cloud consent pending)
RUNNING  -> STOPPING -> STOPPED     (stop requested; current mission reaches a safe state)
RUNNING  -> BLOCKED                 (preflight blocker, journal conflict, hard failure, budget exhausted)
RUNNING  -> COMPLETED               (bounded mission limit reached, or backlog has no READY work)
crash    -> RECOVERING -> RUNNING|BLOCKED   (next start; stale lease reclaimed after proof)
~~~

Allowed transitions are validated in code; every transition writes `supervisor_runs.status` + an event row before returning. `STOPPED`/`COMPLETED` release the lease.

### 5.2 Queue item states (`mission_queue.state`)

~~~text
PROPOSED -> READY -> CLAIMED -> RUNNING -> VERIFYING -> REVIEWING -> VERIFIED
                              |                |             |
                              |                |             +-> NEEDS_FIX -> READY (bounded retry)
                              |                +----------------> BLOCKED
                              +---------------------------------> INTERRUPTED (stop/stop_after/crash)
INTERRUPTED -> CLAIMED (resume same mission; never duplicates)
BLOCKED/CANCELLED/VERIFIED are terminal for that queue row.
~~~

Mapping from orchestrator results:

| Orchestrator result | Queue transition | Retry? |
|---|---|---|
| `completed` | VERIFIED | no |
| `interrupted` (stop/pause or `--stop-after`) | INTERRUPTED (same mission retained) | resume on next run, not counted as failure |
| `blocked` with `candidate_rejected`/`verification_failed`, attempts < max | NEEDS_FIX -> READY | yes, with failure signature |
| `blocked` with `cas_conflict`, `rollback_conflict`, `legacy_mission`, review rejection policy, promotion journal conflict | BLOCKED (terminal) | no; requires human/operator |
| `failed` (unexpected exception) | NEEDS_FIX if retryable else BLOCKED, stage retained | bounded |
| model unavailable / HTTP 429 / lease lost | item unchanged; supervisor WAITING_FOR_RESOURCES or RECOVERING | yes after backoff |
| PermissionDenied (cloud/network/delete) | NEEDS_FIX + approval row; supervisor WAITING_FOR_APPROVAL (assisted) or BLOCKED (automatic without consent) | after grant |

### 5.3 Durable write ordering (fail-closed)

| Step | DB write | File write | Crash consequence |
|---|---|---|---|
| run start | `supervisor_runs` STARTING/RUNNING, lease row | none | next start reclaims stale lease after proof |
| select | queue READY/PROPOSED row (idempotency key) | none | reconcile re-uses row |
| claim | queue CLAIMED + claim token | none | reconcile sees CLAIMED w/o mission -> READY or adopts existing mission |
| mission create | `missions` row (requirement_id, harness_version=2), queue RUNNING | none | reconcile adopts mission by requirement |
| developer..reviewer | orchestrator's own durable writes (tasks/handoffs/stage) | staged workspace only | orchestrator `_run_locked` reconcile on resume (C6) |
| promotion | `promotion_status`/journal | live files + journal + recovery | promotion.reconcile on resume (C6) |
| mission terminal | orchestrator finalize writes missions + handoffs | evidence JSON | queue reconcile maps mission status |
| record outcome | queue VERIFIED/..., backlog_items progress, mission_evidence rows, events | evidence JSON/hashes | idempotent repair on next reconcile |
| run end | run status, lease released | log | lease expiry otherwise |

---

## 6. Durable schema (additive migrations)

All changes are additive and idempotent, consistent with `persistence/database.py` `_MIGRATIONS` + `_SCHEMA` + `_INDEXES`. Existing rows untouched; no backfill of historical missions (legacy rows keep NULL `requirement_id`).

### 6.1 Column migrations (append to `_MIGRATIONS`)

~~~python
("missions", "requirement_id", "TEXT"),          # NL-BP-062 traceability
("missions", "supervisor_run_id", "INTEGER"),    # optional link to supervisor_runs.id
("events", "project_id", "INTEGER"),             # NL-BP-075 correlation
("events", "mission_id", "INTEGER"),
("events", "correlation_id", "TEXT"),
("events", "event_kind", "TEXT"),
~~~

### 6.2 New tables (append to `_SCHEMA`; executed idempotently by `init_db`)

~~~sql
CREATE TABLE IF NOT EXISTS supervisor_leases (
    project_id  INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    owner_id    TEXT NOT NULL,
    owner_pid   INTEGER NOT NULL,
    owner_host  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supervisor_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    mode                TEXT NOT NULL,              -- off|assisted|automatic
    status              TEXT NOT NULL,              -- STARTING|RUNNING|PAUSED|WAITING_FOR_RESOURCES|WAITING_FOR_APPROVAL|STOPPING|STOPPED|BLOCKED|COMPLETED|RECOVERING
    owner_id            TEXT,
    owner_pid           INTEGER,
    config_json         TEXT NOT NULL DEFAULT '{}',
    stop_requested      INTEGER NOT NULL DEFAULT 0,
    pause_requested     INTEGER NOT NULL DEFAULT 0,
    missions_completed  INTEGER NOT NULL DEFAULT 0,
    missions_failed     INTEGER NOT NULL DEFAULT 0,
    started_at          TEXT NOT NULL,
    heartbeat_at        TEXT,
    finished_at         TEXT,
    stopped_reason      TEXT
);

CREATE TABLE IF NOT EXISTS mission_queue (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    requirement_id    TEXT,
    mission_id        INTEGER REFERENCES missions(id) ON DELETE SET NULL,
    state             TEXT NOT NULL,               -- PROPOSED|READY|CLAIMED|RUNNING|VERIFYING|REVIEWING|VERIFIED|NEEDS_FIX|BLOCKED|INTERRUPTED|CANCELLED
    priority          TEXT NOT NULL DEFAULT 'P1',
    idempotency_key   TEXT NOT NULL,
    claim_token       TEXT,
    lease_owner       TEXT,
    attempts          INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 2,
    budget_json       TEXT NOT NULL DEFAULT '{}',
    goal              TEXT NOT NULL,
    payload_json      TEXT NOT NULL DEFAULT '{}',
    failure_class     TEXT,
    failure_signature TEXT,
    scheduled_at      TEXT,
    claimed_at        TEXT,
    heartbeat_at      TEXT,
    finished_at       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(project_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS backlog_items (
    requirement_id       TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    area                 TEXT,
    priority             TEXT,
    program_stage        INTEGER,
    program_stage_name   TEXT,
    status               TEXT NOT NULL,             -- authored source status: verified|partial|planned|blocked
    dependencies_json    TEXT NOT NULL DEFAULT '[]',
    acceptance_json      TEXT NOT NULL DEFAULT '[]',
    source_refs_json     TEXT NOT NULL DEFAULT '[]',
    content_hash         TEXT NOT NULL,
    source_fingerprint   TEXT,
    last_synced_at       TEXT NOT NULL,
    supervisor_status    TEXT,                      -- READY|IN_FLIGHT|VERIFIED|NEEDS_FIX|BLOCKED|SKIPPED
    last_mission_id      INTEGER,
    attempts             INTEGER NOT NULL DEFAULT 0,
    note                 TEXT
);

CREATE TABLE IF NOT EXISTS mission_evidence (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id   INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    queue_id     INTEGER,
    kind         TEXT NOT NULL,                     -- diff|verification|review|promotion|recovery|budget|failure|preflight
    record_key   TEXT NOT NULL,
    sha256       TEXT,
    path         TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    UNIQUE(mission_id, kind, record_key)
);

CREATE TABLE IF NOT EXISTS approvals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    mission_id   INTEGER,
    action       TEXT NOT NULL,                     -- delete|network|cloud|install|publish|migrate|external_tool
    scope_json   TEXT NOT NULL DEFAULT '{}',
    reason       TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending|approved|denied|expired
    requested_at TEXT NOT NULL,
    decided_at   TEXT,
    decided_by   TEXT,
    expires_at   TEXT
);

CREATE TABLE IF NOT EXISTS supervisor_commands (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id       INTEGER,
    command      TEXT NOT NULL,                     -- start|stop|pause|resume|kick
    requested_by TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    consumed_at  TEXT
);

CREATE TABLE IF NOT EXISTS machine_leases (
    resource    TEXT PRIMARY KEY,                   -- 'inference' (stage 4 replaces with full scheduler)
    owner_id    TEXT NOT NULL,
    owner_pid   INTEGER NOT NULL,
    owner_host  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
~~~

### 6.3 Indexes (append to `_INDEXES`)

~~~sql
CREATE INDEX IF NOT EXISTS idx_missions_requirement ON missions(requirement_id);
CREATE INDEX IF NOT EXISTS idx_queue_project_state ON mission_queue(project_id, state, id);
CREATE INDEX IF NOT EXISTS idx_queue_requirement ON mission_queue(project_id, requirement_id);
CREATE INDEX IF NOT EXISTS idx_backlog_stage ON backlog_items(program_stage, priority);
CREATE INDEX IF NOT EXISTS idx_evidence_mission ON mission_evidence(mission_id, id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(project_id, status, id);
CREATE INDEX IF NOT EXISTS idx_runs_project ON supervisor_runs(project_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);
~~~

### 6.4 Settings helpers (new, `persistence/database.py`)

The `app_settings` table exists but has no accessors. Add generic helpers (also reusable by NL-BP-072):

~~~python
def get_setting(key: str, default: str | None = None) -> str | None
def set_setting(key: str, value: str) -> None
def get_json_setting(key: str, default: dict | None = None) -> dict
def set_json_setting(key: str, value: dict) -> None
def log_event(conn, message: str, source: str = "system", level: str = "info",
              payload: str = "{}", *, project_id: int | None = None,
              mission_id: int | None = None, correlation_id: str | None = None,
              event_kind: str | None = None) -> None   # additive kwargs only
~~~

Key namespaces:
- `supervisor.global` = JSON defaults (backend-managed).
- `supervisor.project.<project_id>` = per-project overrides (mode, budgets, allowed cloud models, stage override, backlog path).
- `permissions.policy.global` / `permissions.policy.project.<id>` = owned by stage-2 `core/permissions.py` (NL-BP-072; do not duplicate).

### 6.5 Legacy migration

`data/selfbuild_state.json` remains a read-only legacy input: on the first supervisor run, `reconcile()` imports `last_completed_mission_id`/`last_completed_fingerprint`/`relocated_from` into `supervisor_runs/config`-independent `app_settings` keys (`supervisor.legacy.<project_id>`) and records an event. The file is never modified or deleted. `docs/NEXT_SELF_BUILD_MISSION.md` is no longer read by the supervisor path.

---

## 7. Lease, heartbeat, single-owner protocol

### 7.1 Supervisor lease

- `owner_id` = random UUID per supervisor process; `owner_pid`/`owner_host` recorded for liveness proof.
- Acquire (single CAS, inside one write transaction):

~~~sql
INSERT INTO supervisor_leases (project_id, owner_id, owner_pid, owner_host, version,
                               acquired_at, heartbeat_at, expires_at)
VALUES (?, ?, ?, ?, 1, ?, ?, ?)
ON CONFLICT(project_id) DO UPDATE SET
    owner_id=excluded.owner_id, owner_pid=excluded.owner_pid,
    owner_host=excluded.owner_host, acquired_at=excluded.acquired_at,
    heartbeat_at=excluded.heartbeat_at, expires_at=excluded.expires_at,
    version=supervisor_leases.version+1
WHERE supervisor_leases.expires_at < :now
   OR supervisor_leases.owner_id = :owner_id
RETURNING version;
~~~

- No row returned means a live owner: inspect it. If `owner_host` is this host and the pid is alive -> raise `LeaseConflict` ("another supervisor is active; use stop/status"). If TTL expired and pid dead -> CAS steal (the statement above already permits it; the higher-level check is for the diagnostic message). Never kill the other process.
- Renew every `heartbeat_interval_s` (default 5 s, TTL default 30 s):

~~~sql
UPDATE supervisor_leases
   SET heartbeat_at=?, expires_at=?, version=version+1
 WHERE project_id=? AND owner_id=? AND version=?;
~~~

Rowcount 0 -> lease lost: set a local `lease_lost` flag; the run stops after the current safe point and does **not** write queue/backlog transitions that require ownership. Unknown/clock-skew tolerance: TTL is evaluated from UTC ISO timestamps; if clocks are suspect the supervisor refuses to steal (`LeaseConflict`) rather than risk dual writers.
- Release: `DELETE FROM supervisor_leases WHERE project_id=? AND owner_id=?` (only own row).
- Heartbeat runs in a daemon `threading.Thread` with its own short-lived SQLite connections (repo pattern); exceptions are logged and counted; 3 consecutive failures -> local stop (fail-closed).
- `mission_lock` (working tree) remains the ultimate writer guard; the supervisor checks `lock_status()` in preflight and before each launch, and the orchestrator acquires it per mission. A foreign live lock -> `WAITING_FOR_RESOURCES` with reason, no force-kill.
- `machine_leases('inference')`: same CAS shape with resource key; acquired around the orchestrator call, renewed by the same heartbeat, released after. Prevents two projects sharing app data from loading models concurrently. Same-host separate app-data dirs are not coordinated in C3 (documented limitation).

### 7.2 Run ownership and queue claims

- Claim a queue item:

~~~sql
UPDATE mission_queue
   SET state='CLAIMED', claim_token=?, lease_owner=?, claimed_at=?, updated_at=?
 WHERE id=? AND state IN ('READY','INTERRUPTED','NEEDS_FIX')
   AND (claim_token IS NULL OR claim_token=?)
   AND idempotency_key=?;
~~~

Rowcount 1 = claim; otherwise reload and re-dispatch. The claim token is required for every transition and is stored in the row; a supervisor that lost the lease cannot mutate the row.
- Mission row creation: create the mission, then set `mission_queue.mission_id`. A crash between them is repaired by reconciliation: find `missions` rows with the same `requirement_id` in (`pending/running/interrupted`) and adopt the newest as resumable; else return the item to READY.
- The supervisor never deletes queue/evidence rows; terminal states keep the audit trail. `CANCELLED` requires an explicit operator command.

---

## 8. Preflight (fail-closed start gate)

`Supervisor.preflight() -> PreflightReport` runs before any mission/model and returns `ok` only if no blockers. Ordered checks:

| # | Check | Blocking action on failure |
|---|---|---|
| 1 | Relocation readiness (`core.relocation.check_selfbuild_readiness`) | BLOCKED (database/state identity unverified) |
| 2 | Autonomy mode read from `app_settings`; `off` -> no run | return idle/off, no writes |
| 3 | Supervisor lease acquire (section 7) | `LeaseConflict` -> exit with status "already-running"; no queue changes |
| 4 | `promotion.preflight(root, mission_lookup=find_mission_by_staging_dir)` | BLOCKED + promotion journal resume command (no model call, no writes) |
| 5 | Stale/orphan stages: `promotion.sweep_stale_stages` (7 days, terminal missions, never journals) | warnings; removed list in report |
| 6 | Working-tree lock: `mission_lock.lock_status()`; live foreign owner | WAITING_FOR_RESOURCES (recheck later); no force |
| 7 | Legacy missions (`harness_version != 2`) in resumable statuses | warning, excluded; never resumed |
| 8 | Queue reconciliation (section 10.5) | repairs or BLOCKED on inconsistent state |
| 9 | Backlog: load `INDEX.json`, schema_version check, sync to SQLite, compare fingerprint | BLOCKED on missing/corrupt index; never use roadmap fallback |
| 10 | Permissions: `is_granted('read'/'write'/'execute', project_id)`; delete/network/cloud grants reported | BLOCKED if base scopes missing; approvals reported |
| 11 | Model availability: Ollama/local provider reachable and role models present (config `config/models.yaml` + env overrides); `assert_model_permitted` on each configured model | WAITING_FOR_RESOURCES with retry command if unavailable; BLOCKED if a cloud model is configured without CLOUD grant |
| 12 | Budget sanity: `max_missions_per_run` in 1..5, `max_attempts_per_requirement` in 1..5, wall clock > 0, backoff finite | config error -> BLOCKED |
| 13 | Git state read-only: HEAD sha, dirty/untracked counts recorded as evidence (never discarded) | warning only |
| 14 | Legacy `data/selfbuild.lock`: if live pid -> BLOCKED (another runner); stale -> reclaim with recorded event | event |
| 15 | Machine inference lease availability | WAITING_FOR_RESOURCES if another project holds it |

`PreflightReport` dataclass:

~~~python
@dataclass
class PreflightReport:
    ok: bool
    project_id: int
    root: str
    mode: str
    program_stage: int | None
    blockers: list[str]
    warnings: list[str]
    recovery: list[str]
    lease: dict | None
    backlog: dict
    permissions: dict
    models: dict
    git: dict
    resume_command: str
~~~

Every preflight writes one `events` row (`event_kind='preflight'`, `correlation_id=run owner`) with blockers/warnings, but performs no live writes. Blocked results always include the exact resume command.

---

## 9. Start / stop / pause / resume independent of chat

The supervisor has no dependency on a chat session, conversation history, TODO lists or the GUI. Everything needed is in SQLite plus the app-data filesystem. Three entry surfaces use the same service API:

### 9.1 CLI (`nl_agent.py`)

~~~text
supervisor run     [--project .] [--mode off|assisted|automatic] [--max-missions N]
                   [--once] [--detach] [--json] [--dev-model M] [--reviewer-model M] [--debug-model M]
supervisor start   (alias: run --detach; persists mode and starts the loop)
supervisor stop    [--project .] [--reason TEXT]
supervisor pause   [--project .]
supervisor resume  [--project .]
supervisor status  [--project .] [--json] [--watch]
supervisor index   [--project .] [--check|--sync|--show-next] [--json]
supervisor recover [--project .] [--dry-run] [--json]
supervisor advance-stage --stage N --evidence PATH --confirm   (human/backend only)
~~~

- `run` foreground is the default and is the honest C3 form: a bounded (default 1 mission) or long-running (automatic, capped by budget/wall clock) loop.
- `--detach` spawns `python nl_agent.py supervisor run ...` as a new process with stdout/stderr redirected to `logs/supervisor.log` and records the pid in `supervisor_runs`. This is a process, not an OS service: it does not survive a reboot and must not be advertised as one (a Windows Task Scheduler recipe is stage 6, not claimed).
- `stop`/`pause`/`resume` write `supervisor_commands` rows and set flags on the active run; they work from another terminal while the supervisor runs and require no chat.
- Signals: `Ctrl+C`/SIGINT in the foreground sets stop_requested, lets the current mission reach a safe boundary, releases lease, exits 0/1 consistently.
- `selfbuild --autonomous` becomes a deprecated compatibility alias for `supervisor run --max-missions N --mode automatic` (prints a deprecation warning). `selfbuild --goal`/`--from-roadmap` remain the manual one-mission path (not supervisor).
- Exit codes: 0 completed/idle/off; 1 blocked/failed; 2 preflight/invalid config; 3 stopped by request; 4 waiting for resources/approval (nothing failed, resume available).

### 9.2 Service layer (`app/services.py`)

~~~python
class AppServices:
    def supervisor_start(self, project_id: int, *, mode: str | None = None,
                         max_missions: int | None = None) -> str          # returns a scheduler/thread id
    def supervisor_stop(self, project_id: int, *, reason: str = "") -> dict
    def supervisor_pause(self, project_id: int) -> dict
    def supervisor_resume(self, project_id: int) -> dict
    def supervisor_status(self, project_id: int) -> dict
    def supervisor_preflight(self, project_id: int) -> dict
    def supervisor_queue(self, project_id: int, *, limit: int = 50) -> list[dict]
~~~

The service runs the loop in a dedicated daemon thread (not the shared `SequentialScheduler` worker, so a long supervisor run cannot starve the scheduler's other tasks and stop/pause remain responsive). It emits `Event(source='supervisor', level, message, payload)` on the existing bus for the GUI log/status bar. Only one supervisor thread per project is allowed (lease enforces this across processes too).

### 9.3 GUI (minimal in C3, full UX stage 4)

- New `gui/widgets/autonomy_panel.py`: mode selector (Off/Assisted/Automatic), budget fields (missions, attempts, wall clock), Start/Pause/Resume/Stop buttons, status + preflight report, queue table (requirement, state, attempts, mission id).
- `settings_panel.py`: read-only permissions/cloud summary with a link to the permissions editor (task-18/GUI stage 4); never a toggle that silently disables safety.
- `main_window.py`: status-bar supervisor state + an always-reachable emergency Stop button (NL-BP-024) calling `supervisor_stop`; event-bus subscription for logs.
- `task_board.py`: show queue/requirement columns and the resume command.
- GUI must call services only; no supervisor logic in widgets.

### 9.4 Control semantics

- **Stop**: persist command + flag; checked (a) between missions, (b) inside the orchestrator at safe stage boundaries via `RunControl.checkpoint()` (before developer, after developer, after tester, before reviewer). If the reviewer has already approved and promotion started, promotion completes (never abort mid-promotion); then the supervisor stops. The current mission is finalized `interrupted` (staged candidate retained) or `completed` if it reached promotion; queue row becomes INTERRUPTED/VERIFIED accordingly. `status` -> STOPPING -> STOPPED.
- **Pause** in C3: honored at mission boundaries only ("pausing after current mission"), so no half-written mission. Status PAUSED; lease is renewed while paused only for a bounded grace window (default 2x TTL) to avoid holding the project indefinitely; if the pause outlives the grace, the supervisor releases the lease and can be restarted later (`supervisor resume`).
- **Resume**: clears flags; preflight + reconcile; a queue item in INTERRUPTED resumes the same mission id (orchestrator re-validates/re-verifies/promotes exactly once); a VERIFIED requirement is not re-run.
- **Emergency stop**: same stop command, plus the GUI button; never kills unrelated processes, never deletes evidence, never bypasses CAS.

---

## 10. Backlog-driven mission selection (replaces the fixed roadmap)

### 10.1 Sources of truth

- `docs/product-blueprint/INDEX.json` (authored, schema_version 1): `program_order.stages` (stage/status/depends_on_stages/requirement_ids) and `requirements` (id, title, area, priority, status, dependencies, acceptance, evidence, source_refs, program_stage).
- `docs/PRODUCT_BACKLOG.md` (human view of the same data; never written by the supervisor).
- SQLite `backlog_items`: operational mirror, synced by content hash; `supervisor_status`/`attempts`/`last_mission_id` are supervisor-owned.
- `docs/NEXT_SELF_BUILD_MISSION.md`: legacy manual path only; the supervisor path asserts (static test + runtime warning) that it never reads it.

### 10.2 Sync (`core/backlog.py` -> `supervisor_store.sync_backlog`)

- Load `INDEX.json`; validate `schema_version` and required fields; compute `content_hash` = sha256 over canonical JSON of (title, priority, status, dependencies, acceptance, program_stage, source_refs).
- Upsert by `requirement_id`; if the hash changed, update fields and preserve supervisor progress only when no active mission references the requirement (otherwise keep IN_FLIGHT and warn). Requirements present in DB but missing from the index are marked `SKIPPED` (never deleted).
- Record `source_fingerprint` = sha256 of the whole file; store it in `app_settings` (`supervisor.backlog.<project_id>`) for change detection. Warnings (schema drift, unknown status, dependency referencing an unknown ID) are reported in preflight; a schema_version mismatch is BLOCKED.

### 10.3 Program-stage gate

1. `current_program_stage(index)` = the lowest-numbered stage whose `status != 'completed'` and whose `depends_on_stages` are all `completed` (or explicitly overridden by a recorded, evidence-backed `advance-stage` command approved by a human/backend).
2. Only requirements with `program_stage == current_stage` are selectable. This is how stage 3 work starts only after stage 2 gates pass. The override is explicit, stored in `supervisor_runs.config_json` + events, and never automatic.
3. If no selectable requirement remains, the supervisor reports `COMPLETED` for the run and suggests `advance-stage` with the evidence needed - it never advances on its own.

### 10.4 Selection algorithm (deterministic, non-LLM)

~~~python
def select_next_requirement(project_id, *, project_root, index, config,
                            in_flight_requirement_ids) -> dict | None:
    # 1. effective status = verified if (authored status == verified) or backlog_item.supervisor_status == VERIFIED
    # 2. candidate = items in current program stage with effective status in (partial, planned),
    #    dependencies effective-verified, supervisor_status not in (VERIFIED, BLOCKED, SKIPPED),
    #    not in_flight, attempts < max_attempts
    # 3. order by priority (P0, P1, P2, P3), then requirement id (stable), then authored order
    # 4. skip a requirement whose write scope would collide with an active queue item
    # 5. return the first candidate + computed idempotency key; else None
~~~

- Dedupe by stable ID + content hash: `idempotency_key = sha256(requirement_id | content_hash | program_stage | scope_fingerprint | git_head)`. A queue row with the same key that is not terminal (or was interrupted) is resumed, not duplicated. A VERIFIED key is skipped.
- `in_flight_requirement_ids` comes from non-terminal queue rows and from `missions.requirement_id` with status in (`pending/running/interrupted`).
- Risk gating is fail-closed at execution time, not guessed from titles: base scopes (`read/write/execute`) are required in preflight; a requirement that actually needs cloud/network/delete blocks at the model call or approval point and is classified accordingly. The authored index may later gain an explicit `required_scopes` field (stage 4); C3 does not parse prose heuristically.

### 10.5 Mission goal composition

`compose_mission_goal(requirement, stage) -> str` produces a compact, deterministic goal:

~~~text
[{requirement_id}] {title}

Program stage {n}: {stage name}
Area: {area}; Priority: {priority}; Authored status: {status}

Acceptance gates (must pass independently; reviewer APPROVE alone is not sufficient):
- ...
- ...

Source references (read on demand, do not paste the whole blueprint):
- specifiche/...

Scope: implement the smallest verifiable change that satisfies the gates.
Do not perform destructive actions, installs, network access or cloud calls.
The candidate is staged; nothing is live until promotion.
~~~

The requirement id is stored in `missions.requirement_id` and in the goal text prefix, enabling reconciliation and audit. The goal intentionally does not embed the entire spec corpus (SPEC-21 "Blueprint on demand").

### 10.6 Retiring the roadmap path

- `core/selfbuild_runner.py` becomes a compatibility shim in C3d: `run_autonomous(...)` maps to `run_supervisor(..., max_missions=...)` and preserves the legacy result keys (`status/missions/stopped_reason/resume_command`) plus the C5/C7 preflight/legacy guards (moved into supervisor preflight).
- `core/autonomous_roadmap_planner.py` is dead code at HEAD; C3b leaves the file untouched (deletion needs explicit approval) but adds a static test that the supervisor/backlog modules do not import it, and a deprecation note in `docs/CURRENT_STATE.md`.
- `next_mission`/`docs/NEXT_SELF_BUILD_MISSION.md` remain for `selfbuild --goal/--from-roadmap` only; `--from-roadmap` prints a "legacy manual path" notice.

---

## 11. Mission execution, outcomes, budgets, retries

### 11.1 Execution path

~~~python
mission = ensure_mission(queue_item)          # create or adopt; harness_version=2
orch = orchestrator_factory(root)             # MultiAgentOrchestrator(root, project_id=...)
result = orch.run_mission(
    mission_id=mission["id"], goal=queue_item["goal"],
    developer_model=config.developer_model, reviewer_model=config.reviewer_model,
    debug_model=config.debug_model, control=self.control,
)
~~~

The orchestrator stays responsible for stages, candidate+oracle verification, promotion and finalize. The supervisor records the outcome and never edits mission/task rows directly except the additive `requirement_id`/`supervisor_run_id` links.

### 11.2 Budgets (persisted, configurable, defaults conservative)

| Budget | Default | Enforcement |
|---|---|---|
| missions per run | 1 (CLI/assisted); automatic configurable 1-5 | loop counter; `LIMIT` |
| attempts per requirement | 2 (queue total) | queue.attempts vs max_attempts; dead-letter on exhaustion |
| orchestrator repair attempts | existing `NL_MAX_REPAIRS` (2) + `MAX_TOTAL_STAGE_ATTEMPTS` (5) | unchanged, orchestrator; supervisor sees result |
| wall clock per run | 3600 s | checked between missions and at checkpoints; graceful stop with resume command |
| mission wall clock | 1800 s (soft) | supervisor records start/finish; if exceeded after return, classify as budget failure (no kill mid-call; model/timeout config bounds it) |
| consecutive failures | 2 | supervisor BLOCKED, stops; no infinite loop |
| retry backoff | 30/120/600/1800 s (capped) | WAITING_FOR_RESOURCES / NEEDS_FIX scheduling |
| idle wait | 30 s | WAITING_FOR_RESOURCES poll with heartbeat |

Config precedence: code defaults < `supervisor.global` JSON < `supervisor.project.<id>` JSON < CLI flags. All persisted in `supervisor_runs.config_json` for reproducibility.

### 11.3 Failure classification

`classify_outcome(result) -> FailureClass` maps the orchestrator result/promotion_status/error codes to one of:

- `VERIFIED`: run complete -> queue VERIFIED, backlog progress, evidence.
- `REPAIRABLE`: candidate_rejected / verification_failed with attempts left and a **new** failure signature.
- `HARD_BLOCK`: cas_conflict, rollback_conflict, legacy mission, promotion journal conflict, review-rejected policy repeated, integrity/byte-invariant, harness refusal.
- `WAIT_RESOURCE`: model unavailable/timeout/429/quota/GPU busy.
- `WAIT_APPROVAL`: PermissionDenied for cloud/network/delete/install/publish.
- `BUDGET_EXHAUSTED`: attempts/wall clock/consecutive failures.
- `INTERRUPTED`: stop/pause/`--stop-after`.

Failure signature = sha256(failure class + orchestrator error code + sorted failing verification names + stage). Same signature as the previous attempt -> do not retry identically: change strategy (allowed alternate local model from config; never cloud without grants) or block with diagnosis (NL-BP-065). Repair actions happen inside the orchestrator's staged debugger loop; the supervisor only decides retry/stop.

### 11.4 Halting policy (SPEC-21 "no infinite loop")

- A hard-blocked requirement stops the run (fail-fast) unless the config explicitly enables independent workstreams, which C3 does **not** implement.
- `max_missions_per_run`, wall clock, consecutive failures and attempts are all enforced; reaching a limit returns a status and an exact resume command.
- Every halt writes a `supervisor_runs.stopped_reason`, an event and a `mission_evidence` row (`kind='failure'` or `kind='budget'`).

---

## 12. Resources, cloud and permissions

### 12.1 Local availability gate (`core/resource_gate.py`, minimal in C3)

~~~python
@dataclass
class ResourceDecision:
    action: str            # "run" | "wait" | "blocked"
    reason: str
    retry_after_s: int | None
    observed: dict

def probe_local_models(config: SupervisorConfig) -> dict       # reachable, models, loaded, missing role models
def acquire_inference_slot(owner_id: str, *, ttl_s: float) -> bool
def release_inference_slot(owner_id: str) -> None
def decide(config, *, project_id: int) -> ResourceDecision      # availability + permissions + contention
~~~

- Uses `models.providers.build_providers(ModelHub)`/`models.ollama_registry`; unknown telemetry stays unknown (no invented VRAM numbers).
- Missing required role models -> WAITING_FOR_RESOURCES with retry; never auto-download necessarily (install flows are separate requirements).
- GPU contention: C3 distinguishes local inference (queued/serialized by `machine_leases`) and **does not claim** GPU-test execution relocation; moving inference to cloud does not move hardware tests (SPEC-13A). Full adaptive policy is NL-BP-070/071 (stage 4).
- HTTP 429/quota: parse `Retry-After` when available, else backoff schedule; checkpoint; never silent cloud.

### 12.2 Cloud/network enforcement

- Stage-2 `core/permissions.py` is the single policy point (API present at HEAD working tree: `READ/WRITE/EXECUTE/DELETE/NETWORK/CLOUD`, `SCOPES`, `DEFAULT_GRANTS`, `PermissionDenied`, `grant/revoke/is_granted/get_policy/require`, `is_cloud_model/is_remote_endpoint/assert_model_permitted`, policy keys `permissions.policy.global` and `permissions.policy.project.<id>`). `assert_model_permitted(model_name, base_url=None, project_id=None)` raises `PermissionDenied` before any LLM/HTTP object is constructed; it is already wired in `orchestrator._make_llm` and `cli.make_llm`. The supervisor never bypasses it; there is no env/CLI flag to disable it. C3c threads the supervisor's `project_id` into those call sites (additive parameter) so per-project policy applies; None keeps today's global-policy behavior.
- `is_cloud_model` heuristic (`-cloud`/`cloud` token, documented in permissions module) marks `ollama/gpt-oss:120b-cloud` as cloud; `is_remote_endpoint` treats loopback (`127.0.0.1`, `localhost`, `::1`) as local, other hosts require NETWORK.
- Supervisor additional gates (defense in depth, never weaker): configured `allowed_cloud_models` whitelist; a persisted per-project cloud-consent flag (today `AppServices.is_cloud_escalation_enabled()` reads `config/models.yaml roles.fallback_cloud.enabled` as a global default only; the design persists the per-project consent in `supervisor.project.<id>` and keeps the CLOUD grant authoritative); in `assisted` mode an `approvals` row is required; in `automatic` mode cloud is used only with CLOUD grant + whitelist + consent + budget > 0. Every decision writes an `events` row (`event_kind='cloud-decision'`) with model, endpoint class, consent id and reason **before** the attempt. Fallback is never silent.
- No source/media leaves the machine before consent; logs redact API keys (existing shell/log hygiene).
- `orchestrator.MultiAgentOrchestrator.__init__` gains optional `project_id` so `_make_llm` can evaluate project policy; default None -> global grants only (legacy CLI behavior unchanged for non-supervisor paths until stage-2 wiring lands).

### 12.3 Permission scopes required by the supervisor

| Action | Scope | Default |
|---|---|---|
| read backlog/index/repo, list, status | READ | allowed |
| run missions (staged writes + verification) | WRITE + EXECUTE | allowed locally |
| delete/migrate/clean/publish/install | DELETE / (risky execute) | **denied**; approval required; model cannot trigger |
| non-loopback provider endpoints | NETWORK | **denied**; grant + approval |
| cloud-backed models | CLOUD + consent | **denied**; grant + consent + whitelist |
| external tool registry (stage 2 NL-BP-073) | EXECUTE per tool | denied by default |

The permissions API is human/backend-only: no CrewAI tool exposes grant/revoke; tests assert the model tool surface remains the four file tools.

---

## 13. Evidence ledger and observability

### 13.1 DB records

- `mission_evidence` rows (idempotent `UNIQUE(mission_id, kind, record_key)`): `diff` (changed paths + diff sha), `verification` (candidate/oracle run ids, passed), `review` (verdict + notes ref), `promotion` (promoted paths + hashes + recovery path), `recovery` (journal/CAS outcome), `budget`, `failure`, `preflight` (blockers/warnings).
- Existing tables remain authoritative for detail: `handoffs`, `verification_runs`, `task_attempts`, `events` (now with correlation ids).
- `backlog_items.supervisor_status/last_mission_id/attempts` give the requirement-level view.

### 13.2 Files (app data dir, never the target project)

~~~text
<db_path().parent>/
  verification/mission-<id>.json        (existing promotion evidence)
  recovery/<mission_id>.json            (existing intake recovery point)
  supervisor/runs/<run_id>/run.json     (run summary, config, budget, decisions)
  supervisor/runs/<run_id>/events.jsonl (append-only supervisor events, correlation ids)
  supervisor/queue/<queue_id>.json      (terminal queue snapshot; small)
  supervisor/approvals/<id>.json        (optional copy of approval decisions)
  logs/supervisor.log                   (console/detached log, simple rotation)
~~~

Evidence is written after the durable DB transition; a failure to write a JSON file is logged but does not suppress DB evidence. Retention: run/queue/evidence rows kept (small); `supervisor/runs/<id>` may be archived after 90 days only by explicit cleanup command (NL-BP-094), never automatically.

### 13.3 Status/diagnostics surface

`supervisor status --json` returns: mode, run id/status, lease owner/expiry, current queue item/mission/stage (taken from mission/tasks/progress + promotion_status), budget consumed, last verification summary, pending approvals, blockers/warnings, resume command, log path. `supervisor recover --dry-run --json` returns the reconciliation plan without writing. Correlation id = run owner UUID flows into events; logs include mission id/queue id.

---

## 14. SH-07 acceptance plan (two consecutive verified missions, no manual repair)

SH-07 has two evidence tiers. **Neither alone is sufficient**: fake-model CI proves the supervisor/queue/planner logic deterministically; real local-model evidence proves the end-to-end loop with Ollama. NL-BP-063 becomes `verified` only when both are recorded; otherwise it stays `blocked` with the failure evidence (never upgraded on a reviewer claim).

### 14.1 Tier A - deterministic fake-model CI (mandatory merge gate)

File: `tests/test_supervisor_sh07.py` (new, ~8 tests, target runtime < 20 s). Fixtures:

- temp app data: `NL_DATA_DIR=<tmp>/appdata`, `init_db()`;
- temp project: `nl_coding_agent/__init__.py` (empty, required by the candidate/oracle runner import guard), `demo_pkg/`, `tests/` with a passing baseline suite, and a fixture `docs/product-blueprint/INDEX.json` (schema_version 1; program_order where stage 1/2 are completed and stage 3 is in_progress; requirements R1/R2 P0 planned with no dependencies, R3 with an unmet dependency, R4 authored verified);
- fake model: the real `MultiAgentOrchestrator` is used with `_call_model` monkeypatched to scripted outputs per requirement (developer writes a unique source file via the ````write:<path>` fallback, reviewer returns APPROVE); candidate+oracle verification runs for real on the tiny project (~1 s per mission). `orchestrator_factory` injects it. No Ollama, no CrewAI kickoff.

Scenarios/assertions:

1. `test_two_consecutive_missions_complete_and_advance_backlog`: `run_supervisor(root, max_missions=1)` -> mission A for R1: queue VERIFIED, `missions.requirement_id='R1'`, status completed, live file changed only after promotion, stage cleaned, evidence rows (`verification`, `promotion`), backlog R1 `supervisor_status='VERIFIED'`. Then a **fresh `Supervisor` instance** (simulated restart) runs R2 (not R1): completed, two missions total, no duplicate queue rows/missions, lease released/expired cleanly, run 1 status COMPLETED (limit) and run 2 COMPLETED (backlog exhausted for stage 3 or limit), R3 never selected (unmet dependency), R4 never selected (already verified). Exact promotion handoffs = 2.
2. `test_restart_mid_queue_resumes_same_mission_without_duplication`: run 1 with `max_missions=1`; run 2 resumes the same interrupted mission via INTERRUPTED queue item (simulated by stopping after developer through `RunControl` hook); assert one mission row per requirement, same mission id, one promotion.
3. `test_stop_and_pause_commands_are_honored`: request stop from a hook during reviewer; mission reaches completed (promotion is last gate) or interrupted at the boundary; supervisor STOPPED, lease released, queue consistent; request pause -> status PAUSED at boundary; resume -> continues.
4. `test_budget_retry_then_dead_letter`: attempts=1 config; scripted failing candidate -> queue NEEDS_FIX then BLOCKED on exhaustion; no infinite loop; next requirement not started (fail-fast); failure signature persisted.
5. `test_preflight_blocks_unreconciled_promotion_journal`: fake journal in a stage dir -> blocked result with resume command, zero model calls.
6. `test_mode_off_does_nothing`: no queue/model writes.
7. `test_planner_uses_sqlite_not_roadmap`: delete/rename `docs/NEXT_SELF_BUILD_MISSION.md` in the fixture project; planner still selects R1 (static + runtime assertion that `core.roadmap.next_mission` was not called, e.g. monkeypatch it to raise).
8. `test_legacy_missions_are_not_resumed`: `harness_version` NULL row in resumable status is ignored/warned, never executed.

Commands (CI/acceptance, offscreen):

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
pythonpython.exe -m pytest -q tests/test_supervisor_sh07.py tests/test_supervisor_store.py tests/test_backlog_planner.py -p no:cacheprovider
pythonpython.exe -m pytest -q tests -p no:cacheprovider
~~~

### 14.2 Tier B - real local-model evidence (manual, isolated worktree; gate for automatic mode)

Purpose: prove two consecutive real missions complete with local Ollama models, real diffs, candidate+oracle verification, promotion, backlog advancement, and a supervisor restart - **without manual repair**. Environment constraints:

- isolated git worktree of this repository: `git worktree add --detach <temp>/nl-supervisor-sh07 HEAD` (tracked files only; no python/crewAI/dist/data). Never the live working tree; never the master checkout.
- throw-away app data: `NL_DATA_DIR=<temp>/appdata`; copy/point the worktree's `docs/product-blueprint/INDEX.json` as the real backlog; models from `config/models.yaml` local roles (developer `ollama/qwen2.5-coder:7b-instruct-q4_K_M`, reviewer `ollama/qwen3.5:9b` by default, overridable); Ollama on loopback only.
- no cloud/network grants: preflight must show `network`/`cloud` denied; no source leaves the machine.
- mode `automatic`, `max_missions=2`, default budgets; the two selected requirements are the smallest READY stage-3 requirements present in the real INDEX at execution time (docs/tests-only changes preferred). If the pair or model availability is unsuitable, the run **must not** be forced by editing gates or statuses; record the blocker.
- acceptance runner: `scripts/run_supervisor_sh07.py --mode live --confirm-live --worktree <temp>` (new; refuses to run without `--confirm-live`, refuses non-isolated/live roots, refuses cloud/network endpoints, prints the plan first). It runs the supervisor twice (two separate invocations; second invocation proves restart persistence) or once with `max_missions=1` twice, then verifies and writes evidence.
- required evidence artifacts under `build/phase3/evidence/sh07-<UTC timestamp>/`:
  - `summary.json`: run ids, modes, models (name + quantization from `ollama list`), durations, exit codes, budget; `commands.txt`;
  - two mission records: mission ids, requirement ids, status `completed`, verdict `APPROVE`, changed paths, diff sha256; `verification_runs` rows (candidate+oracle passed, junit/report paths); `promotion` evidence (promoted paths/hashes, recovery path); stage cleaned;
  - backlog progression: `backlog_items` supervisor_status VERIFIED for both requirements (SQLite snapshot exported as JSON; the authored INDEX/PRODUCT_BACKLOG update diff is produced for human review);
  - restart proof: second supervisor run selected the next requirement without any new prompt; no duplicate mission/queue rows; lease released; preflight report clean;
  - `git diff` per mission from the worktree + `git status`; `logs/supervisor.log`; `run.json` files; machine info (CPU/RAM/GPU if available; unknown marked unknown);
  - pass/fail checklist with explicit "NOT PROVEN" items.
- pass criteria: both missions completed with passing candidate+oracle verification and promotion; no manual code repair between them; restart persisted; backlog advanced automatically in SQLite; no live-tree writes outside the worktree; no cloud/network calls; no unresolved journal/lock; evidence artifacts complete.
- failure handling: model unavailable -> WAITING_FOR_RESOURCES evidence (not a pass); model produces stubs/weak tests -> blocked by gates, evidence kept, automatic mode stays disabled, NL-BP-063 remains blocked with the recorded reason; never weaken gates, never manually edit the candidate to pass.
- the runner exits 0 only if every pass criterion holds; otherwise exit 2 (environment/not-run) or 1 (gate failure) and writes the failure evidence. It never commits to the worktree and removes it (`git worktree remove --force`) unless `--keep-worktree` is passed.
- evidence recording: `docs/HARNESS_ACCEPTANCE.md` gets an SH-07 section with the evidence path, commit sha, date, models, and result; `docs/PRODUCT_BACKLOG.md`/`INDEX.json` update NL-BP-063 (and stage 3 status) only after a human review of the evidence (the supervisor itself does not touch these files).

### 14.3 Fake CI vs live evidence - what each proves

| Claim | Tier A fake | Tier B live |
|---|---|---|
| queue/lease/heartbeat/preflight/restart logic | yes | yes (real timings) |
| backlog-driven selection and dedupe | yes | yes (real index) |
| candidate+oracle verification, promotion-last, evidence | yes (real verifier processes) | yes |
| local Ollama can implement and verify two missions without manual repair | no (scripted model) | yes / blocked evidence |
| no cloud/network without grants | yes (assertions) | yes (preflight + audit) |
| unattended operation after reboot / long-running daemon | no | no (process, not service; stage 6) |

---

## 15. File-by-file change list (with signatures)

### 15.1 New modules

#### `nl_coding_agent/persistence/supervisor_store.py` (C3a)

~~~python
@dataclass(frozen=True)
class Lease:
    project_id: int; owner_id: str; version: int; expires_at: str

class LeaseConflict(RuntimeError): ...

# leases
def acquire_lease(project_id: int, *, owner_id: str, owner_pid: int, owner_host: str,
                  ttl_s: float) -> Lease
def renew_lease(project_id: int, *, owner_id: str, version: int, ttl_s: float) -> Lease | None
def release_lease(project_id: int, *, owner_id: str) -> None
def get_lease(project_id: int) -> dict | None

# runs / commands
def start_run(project_id: int, *, mode: str, config: dict, owner_id: str,
              owner_pid: int) -> int
def update_run(run_id: int, *, status: str | None = None, **fields) -> None
def finish_run(run_id: int, *, status: str, reason: str = "") -> None
def get_active_run(project_id: int) -> dict | None
def set_run_flags(run_id: int, *, pause: bool | None = None, stop: bool | None = None) -> None
def request_command(project_id: int, command: str, *, requested_by: str,
                    run_id: int | None = None) -> int
def take_pending_commands(project_id: int, run_id: int) -> list[dict]

# queue
def enqueue_mission(project_id: int, *, requirement_id: str | None, goal: str,
                    priority: str, idempotency_key: str, max_attempts: int,
                    budget: dict, payload: dict | None = None,
                    state: str = "READY") -> int
def get_queue_item(queue_id: int) -> dict | None
def find_queue_item(project_id: int, idempotency_key: str) -> dict | None
def list_queue(project_id: int, *, states: tuple[str, ...] | None = None,
               limit: int = 100) -> list[dict]
def claim_queue_item(queue_id: int, *, claim_token: str, owner_id: str) -> bool
def update_queue_item(queue_id: int, *, claim_token: str | None = None, state: str | None = None,
                      mission_id: int | None = None, failure_class: str | None = None,
                      failure_signature: str | None = None, increment_attempts: bool = False,
                      **fields) -> bool

# backlog mirror
def sync_backlog(requirements: list[dict], *, source_fingerprint: str) -> dict
def get_backlog_item(requirement_id: str) -> dict | None
def list_backlog(*, program_stage: int | None = None) -> list[dict]
def set_backlog_progress(requirement_id: str, *, supervisor_status: str,
                         mission_id: int | None = None, note: str = "") -> None

# evidence / approvals
def record_evidence(mission_id: int, *, kind: str, record_key: str, payload: dict,
                    queue_id: int | None = None, sha256: str | None = None,
                    path: str | None = None) -> int
def list_evidence(mission_id: int) -> list[dict]
def create_approval(project_id: int, *, action: str, scope: dict, reason: str,
                    mission_id: int | None = None, requested_by: str = "system",
                    expires_at: str | None = None) -> int
def decide_approval(approval_id: int, *, approved: bool, decided_by: str,
                    reason: str = "") -> None
def pending_approvals(project_id: int) -> list[dict]

# machine inference slot
def acquire_machine_lease(resource: str, *, owner_id: str, owner_pid: int,
                          owner_host: str, ttl_s: float) -> Lease | None
def renew_machine_lease(resource: str, *, owner_id: str, version: int,
                        ttl_s: float) -> bool
def release_machine_lease(resource: str, *, owner_id: str) -> None
~~~

#### `nl_coding_agent/core/backlog.py` (C3b)

~~~python
INDEX_PATH = "docs/product-blueprint/INDEX.json"
SUPPORTED_SCHEMA_VERSIONS = (1,)

class BacklogError(RuntimeError): ...

@dataclass(frozen=True)
class BacklogRequirement:
    id: str; title: str; area: str; priority: str; status: str
    dependencies: tuple[str, ...]; acceptance: tuple[str, ...]
    source_refs: tuple[str, ...]; program_stage: int | None
    content_hash: str

@dataclass(frozen=True)
class ProgramStage:
    stage: int; name: str; status: str; depends_on_stages: tuple[int, ...]
    requirement_ids: tuple[str, ...]

def load_index(path: str | Path = INDEX_PATH) -> dict
def iter_requirements(index: dict) -> list[BacklogRequirement]
def program_stages(index: dict) -> list[ProgramStage]
def current_program_stage(index: dict, *, override: int | None = None) -> ProgramStage | None
def requirement_content_hash(raw: dict) -> str
def sync_backlog(project_root: Path, *, index_path: str | Path | None = None) -> dict
def effective_status(requirement: BacklogRequirement, row: dict | None) -> str
def select_next_requirement(project_id: int, *, project_root: Path, index: dict,
                            config: "SupervisorConfig",
                            in_flight_requirement_ids: set[str]) -> dict | None
def build_mission_payload(requirement: BacklogRequirement, stage: ProgramStage,
                          *, project_id: int, max_attempts: int) -> dict
def idempotency_key(requirement: BacklogRequirement, stage: ProgramStage,
                    *, git_head: str) -> str
def compose_mission_goal(requirement: BacklogRequirement, stage: ProgramStage) -> str
def advance_program_stage(*, project_id: int, index_path: Path, from_stage: int,
                          evidence: list[str], approved_by: str) -> dict
~~~

#### `nl_coding_agent/core/run_control.py` (C3c)

~~~python
class RunStopped(RuntimeError): ...

class RunControl:
    def __init__(self, *, stop_event: "threading.Event | None" = None,
                 pause_event: "threading.Event | None" = None,
                 on_checkpoint: Callable[[str], None] | None = None) -> None
    def request_stop(self, reason: str = "") -> None
    def request_pause(self) -> None
    def clear_pause(self) -> None
    @property
    def stop_requested(self) -> bool
    @property
    def pause_requested(self) -> bool
    def checkpoint(self, stage: str) -> None      # raises RunStopped when stop requested
~~~

#### `nl_coding_agent/core/resource_gate.py` (C3c, minimal)

~~~python
@dataclass
class ResourceDecision:
    action: str          # "run" | "wait" | "blocked"
    reason: str
    retry_after_s: int | None
    observed: dict

def probe_local_models(config) -> dict
def missing_role_models(config) -> list[str]
def acquire_inference_slot(owner_id: str, owner_pid: int, owner_host: str, *, ttl_s: float) -> bool
def release_inference_slot(owner_id: str) -> None
def decide(config, *, project_id: int) -> ResourceDecision
~~~

#### `nl_coding_agent/core/supervisor.py` (C3c)

~~~python
@dataclass(frozen=True)
class SupervisorConfig:
    mode: str = "off"
    max_missions_per_run: int = 1
    max_attempts_per_requirement: int = 2
    max_wall_time_s: int = 3600
    mission_wall_time_s: int = 1800
    heartbeat_interval_s: float = 5.0
    lease_ttl_s: float = 30.0
    idle_wait_s: float = 30.0
    backoff_schedule_s: tuple[int, ...] = (30, 120, 600, 1800)
    max_consecutive_failures: int = 2
    allowed_cloud_models: tuple[str, ...] = ()
    backlog_path: str = "docs/product-blueprint/INDEX.json"
    program_stage_override: int | None = None
    fail_fast_on_block: bool = True
    developer_model: str | None = None
    reviewer_model: str | None = None
    debug_model: str | None = None

    @classmethod
    def load(cls, project_id: int | None, *, overrides: dict | None = None) -> "SupervisorConfig"
    def to_dict(self) -> dict

@dataclass
class PreflightReport:
    ok: bool; project_id: int; root: str; mode: str
    program_stage: int | None
    blockers: list[str]; warnings: list[str]; recovery: list[str]
    lease: dict | None; backlog: dict; permissions: dict; models: dict; git: dict
    resume_command: str

@dataclass
class Outcome:
    queue_state: str
    failure_class: str | None
    failure_signature: str | None
    retry_after_s: int | None
    mission_result: dict

class SupervisorError(RuntimeError): ...
class SupervisorBlocked(SupervisorError): ...
class LeaseConflict(SupervisorError): ...

class Supervisor:
    def __init__(self, project_root: str | Path, *, project_id: int | None = None,
                 config: SupervisorConfig | None = None,
                 orchestrator_factory: Callable | None = None,
                 event_sink: Callable | None = None,
                 control: RunControl | None = None) -> None
    def preflight(self) -> PreflightReport
    def reconcile(self) -> list[str]
    def acquire(self) -> Lease
    def heartbeat(self) -> Lease | None
    def release(self) -> None
    def sync_backlog(self) -> dict
    def select_next(self) -> dict | None
    def enqueue_next(self) -> int | None
    def execute_queue_item(self, queue_item: dict) -> Outcome
    def execute_mission(self, mission_id: int) -> dict
    def classify(self, mission_result: dict) -> Outcome
    def record_outcome(self, queue_item: dict, outcome: Outcome) -> None
    def request_pause(self, *, requested_by: str = "human") -> dict
    def request_stop(self, *, requested_by: str = "human", reason: str = "") -> dict
    def tick(self) -> dict
    def run(self, *, max_missions: int | None = None) -> dict
    def run_once(self) -> dict
    def status(self) -> dict

def run_supervisor(project_root: str | Path, *, project_id: int | None = None,
                   mode: str | None = None, max_missions: int | None = None,
                   once: bool = False, developer_model: str | None = None,
                   reviewer_model: str | None = None, debug_model: str | None = None,
                   config_overrides: dict | None = None,
                   orchestrator_factory: Callable | None = None,
                   event_sink: Callable | None = None) -> dict
def supervisor_status(project_root: str | Path, *, project_id: int | None = None) -> dict
def supervisor_command(project_root: str | Path, command: str, *,
                       requested_by: str = "cli", reason: str = "") -> dict
~~~

#### `nl_coding_agent/app/supervisor_service.py` (C3d, thin)

~~~python
class SupervisorThread:
    def __init__(self, project_root: Path, project_id: int, *,
                 services: "AppServices", config_overrides: dict | None = None) -> None
    def start(self, *, max_missions: int | None = None) -> None
    def stop(self, *, reason: str = "") -> None
    def is_running(self) -> bool
    def status(self) -> dict
~~~

### 15.2 Modified modules

| File | Change |
|---|---|
| `nl_coding_agent/persistence/database.py` | add 6 column migrations (section 6.1), 7 new tables + indexes (6.2/6.3), `get_setting/set_setting/get_json_setting/set_json_setting`, additive `log_event` kwargs (section 6.4) |
| `nl_coding_agent/persistence/missions.py` | `create_mission(..., requirement_id: str|None = None, supervisor_run_id: int|None = None)`; `list_missions_by_requirement(requirement_id: str) -> list[dict]`; `get_active_mission_for_requirement(requirement_id: str) -> dict|None`; keep all existing signatures backward compatible |
| `nl_coding_agent/agents/orchestrator.py` | additive `project_id: int|None = None` in `MultiAgentOrchestrator.__init__`; `run_mission(..., control: RunControl|None = None)`; `_run_locked(..., control=None)`; `control.checkpoint('before-developer'/'after-developer'/'after-tester'/'before-reviewer')` before/after stages; `RunStopped` -> `_finalize_interrupted` with reason (never between reviewer APPROVE and promotion, never mid-promotion); `_make_llm` passes project_id into the existing `assert_model_permitted(model_name, base_url)` call (stage-2 wiring already present; C3c only adds the project scope parameter). No other pipeline change. |
| `nl_coding_agent/core/selfbuild_runner.py` | replace the loop with a compatibility shim: `run_autonomous(...)` -> `run_supervisor(..., max_missions=..., mode='automatic')` mapping result keys; keep `select_resumable_mission`/`roadmap_fingerprint` helpers only if tests need them (mark deprecated); remove `next_mission` use from the default path; keep C5/C7 preflight/legacy behavior now owned by supervisor preflight |
| `nl_coding_agent/cli.py` | add `supervisor` command group (section 9.1); `selfbuild --autonomous` -> deprecation warning + supervisor shim; extend `mission --list` with requirement id/queue state; keep C7 legacy-resume refusal |
| `nl_coding_agent/app/services.py` | supervisor service methods (9.2), dedicated thread lifecycle, event bus emission, queue/status reads; no business logic beyond orchestration |
| `nl_coding_agent/gui/widgets/autonomy_panel.py` (new) | minimal mode/budget/start/pause/resume/stop/status/queue UI |
| `nl_coding_agent/gui/widgets/settings_panel.py` | read-only permissions/cloud summary + autonomy link |
| `nl_coding_agent/gui/main_window.py` | status-bar supervisor state + emergency Stop action |
| `nl_coding_agent/gui/widgets/task_board.py` | requirement/queue columns + resume command |
| `scripts/run_supervisor_sh07.py` (new) | SH-07 acceptance runner (fake/live modes; isolated worktree; evidence artifacts; refuses live/cloud) |
| `scripts/verify_supervisor.py` (new) | read-only preflight/diagnostic gate: schema present, no active lease, no unresolved journal, queue/backlog consistency, no running supervisor process, `--json` exit code |
| `tests/test_supervisor_store.py` (new) | lease CAS/TTL/stale-pid, queue claim/idempotency, backlog sync, evidence/approvals round-trip |
| `tests/test_backlog_planner.py` (new) | index parse/hash/dedupe, stage gate, dependency/priority ordering, idempotency stability, no roadmap import, goal composition |
| `tests/test_supervisor_core.py` (new) | preflight matrix, reconcile matrix, retry/backoff/dead-letter, fail-fast, stop/pause, off mode |
| `tests/test_supervisor_sh07.py` (new) | Tier A end-to-end (section 14.1) |
| `tests/test_supervisor_cli.py` (new) | argument parsing, status JSON, stop/pause command persistence, no live execution |
| `tests/test_selfbuild_runner.py` | adapt run_autonomous tests to the shim/supervisor result mapping; keep C5/C7 assertions |
| `docs/07_SAFETY.md` | supervisor/permissions/cloud section; honest limitations (no OS sandbox, no daemon, no silent cloud) |
| `docs/CURRENT_STATE.md` | replace self-build section: supervisor, queue/lease/backlog, modes, commands, evidence |
| `docs/HARNESS_ACCEPTANCE.md` | SH-07 section with Tier A/Tier B results and artifact paths |
| `docs/PRODUCT_BACKLOG.md`/`docs/product-blueprint/INDEX.json` | status/evidence-only updates for NL-BP-061/062/063/064/065/075 and stage-3 program status, applied by human/backend after evidence review |
| `docs/02_SELF_BUILD_ROADMAP.md` | stage-3 section/phase note |

No modifications are proposed to `core/promotion.py`, `core/staging_broker.py`, `core/recovery_store.py`, `core/candidate_verification.py`, `core/mission_lock.py`, `tools/**`: they already implement the required primitives. Permissions/tool-registry modules are stage-2 deliverables (task-18/task-19) consumed here.

---

## 16. Failure modes and recovery matrix

| # | Failure | Detection | Behavior / recovery |
|---|---|---|---|
| 1 | Supervisor crash before claim | lease TTL expiry; run row stale | next start reclaims lease after pid proof; READY queue unchanged |
| 2 | Crash after claim, mission not created | queue CLAIMED, mission_id NULL | reconcile -> READY; no duplicate mission |
| 3 | Crash during mission (model call) | mission running/interrupted, stage exists | restart selects resumable queue item first; orchestrator reconciles stage/journal; never duplicates patch |
| 4 | Crash after promotion, before finalize | live hashes == manifest after; journal may exist | `promotion.reconcile` -> promotion-complete -> finalize completed once (existing C6 path) |
| 5 | Crash after mission completed before queue/backlog update | mission status completed, queue RUNNING | reconcile derives VERIFIED and updates backlog; evidence repaired idempotently |
| 6 | Promotion journal conflict | `promotion.preflight` / reconcile conflict | preflight BLOCKED, no model call/writes, exact resume command |
| 7 | Another process holds the working-tree lock | `mission_lock.lock_status()` live pid | WAITING_FOR_RESOURCES; recheck later; never kill |
| 8 | Two supervisors same project | lease CAS conflict / live pid | second exits `already-running`; status shows owner |
| 9 | Two supervisors different projects, same GPU | machine inference lease | second WAITING_FOR_RESOURCES; backoff |
| 10 | Local model missing / Ollama down | resource gate/probe | WAITING_FOR_RESOURCES + checkpoint + retry command; no implicit cloud |
| 11 | 429/quota/rate limit | error classification + `Retry-After` | backoff schedule; same queue item; no repeated paid calls; no policy change |
| 12 | Cloud/network/delete without grant | `PermissionDenied` before LLM/tool | approval row + WAITING_FOR_APPROVAL (assisted) / BLOCKED (automatic); audited; no data sent |
| 13 | Stub/weak test/out-of-scope candidate | validation gate | blocked `candidate_rejected`; live untouched; retry bounded or dead-letter |
| 14 | Oracle red / candidate green | candidate verification | blocked `verification_failed`; retry bounded; evidence kept |
| 15 | Reviewer REJECT / repeated failures | result classification | BLOCKED/NEEDS_FIX per policy; failure signature prevents identical retry; strategy change or dead-letter |
| 16 | Attempts/wall clock/consecutive failures exhausted | counters | BLOCKED; fail-fast; resume command; no infinite loop |
| 17 | Legacy mission (harness_version != 2) in queue/resume | preflight/reconcile | excluded + warning; never executed; operator creates new mission |
| 18 | Backlog index missing/corrupt/schema drift | loader validation | BLOCKED; no roadmap fallback; operator fixes index |
| 19 | Program stage not satisfied | stage gate | no selection; COMPLETED with `advance-stage` guidance; never auto-advance |
| 20 | Lease lost mid-run (renew fail) | heartbeat rowcount 0 | local flag; current mission returns; no queue/backlog writes; exit `lease-lost`; new owner reconciles |
| 21 | Evidence JSON write fails | file error logged | DB evidence already committed; run continues; warning in status |
| 22 | DB busy/locked | sqlite OperationalError | retry with busy_timeout; 3 consecutive failures -> BLOCKED (fail-closed), no partial state claimed |
| 23 | Stop requested during promotion | control checkpoint placement | promotion completes; then STOPPED; never abort mid-journal |
| 24 | Mission changes supervisor/orchestrator code | changed_paths inspection after mission | run completes; `restart_required` flag/event written (SPEC-02 autoupdate: no hot reload); operator restarts to load new code |
| 25 | User manually edits files during a mission | promotion CAS drift | blocked `cas_conflict`; human edit preserved; evidence records drift |
| 26 | System reboot mid-run | stale run/lease/queue rows | next start RECOVERING: reconcile queue from missions/stages; report resume; nothing silently rerun |

---

## 17. Commit order C3a-C3e

Each commit is independently testable and green; no autonomous run is executed in CI or during development. Target: full suite stays green after each commit.

### C3a - additive schema + supervisor store + settings helpers
Scope: `persistence/database.py` (migrations/tables/indexes/settings/log_event kwargs), new `persistence/supervisor_store.py`, new `tests/test_supervisor_store.py`, new `tests/test_harness_schema.py` additions for migrations. No behavior change; no code reads the new tables yet.
Acceptance commands:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
pythonpython.exe -m pytest -q tests/test_supervisor_store.py tests/test_harness_schema.py -p no:cacheprovider
pythonpython.exe -m pytest -q tests -p no:cacheprovider
~~~

### C3b - backlog index sync + deterministic planner
Scope: new `core/backlog.py`, `tests/test_backlog_planner.py`; deprecation note for `autonomous_roadmap_planner.py`; no supervisor loop yet.
Acceptance:

~~~powershell
pythonpython.exe -m pytest -q tests/test_backlog_planner.py -p no:cacheprovider
pythonpython.exe -m pytest -q tests -p no:cacheprovider
pythonpython.exe -c "import sys; sys.path.insert(0,'.'); from nl_coding_agent.core import backlog; from nl_coding_agent.core.backlog import load_index, current_program_stage; i=load_index('docs/product-blueprint/INDEX.json'); print(current_program_stage(i))"
~~~

### C3c - supervisor core: lease/heartbeat, preflight, reconcile, loop, control, resource gate
Scope: new `core/supervisor.py`, `core/run_control.py`, `core/resource_gate.py`; additive hooks in `agents/orchestrator.py` (control + project_id); new `tests/test_supervisor_core.py`; `tests/test_selfbuild_runner.py` untouched (shim comes in C3d).
Acceptance:

~~~powershell
pythonpython.exe -m pytest -q tests/test_supervisor_core.py tests/test_orchestrator_staging.py tests/test_promotion_stage.py -p no:cacheprovider
pythonpython.exe -m pytest -q tests -p no:cacheprovider
~~~

### C3d - CLI/service/GUI surfaces + selfbuild_runner compatibility shim
Scope: `cli.py` supervisor group + deprecation alias, `app/services.py` + `app/supervisor_service.py`, minimal GUI panels, `core/selfbuild_runner.py` shim, `tests/test_supervisor_cli.py`, adapt `tests/test_selfbuild_runner.py`, update `tests/test_selfbuild_mode.py` if CLI strings changed.
Acceptance:

~~~powershell
pythonpython.exe -m pytest -q tests/test_supervisor_cli.py tests/test_selfbuild_runner.py tests/test_selfbuild_mode.py tests/test_cli_config.py -p no:cacheprovider
pythonpython.exe nl_agent.py supervisor status --project . --json
pythonpython.exe nl_agent.py supervisor index --project . --check
pythonpython.exe -m pytest -q tests -p no:cacheprovider
~~~

### C3e - SH-07 acceptance: deterministic end-to-end test, acceptance runner, docs/backlog evidence
Scope: `tests/test_supervisor_sh07.py`, `scripts/run_supervisor_sh07.py`, `scripts/verify_supervisor.py`, `docs/HARNESS_ACCEPTANCE.md`, `docs/07_SAFETY.md`, `docs/CURRENT_STATE.md`, `docs/02_SELF_BUILD_ROADMAP.md`, evidence-reviewed `PRODUCT_BACKLOG.md`/`INDEX.json` status updates.
Acceptance:

~~~powershell
pythonpython.exe -m pytest -q tests/test_supervisor_sh07.py -p no:cacheprovider
pythonpython.exe -m pytest -q tests -p no:cacheprovider
pythonpython.exe scripts/run_supervisor_sh07.py --mode fake --json
pythonpython.exe scripts/verify_supervisor.py --json
# manual, isolated worktree, local models, after Lead/user confirmation:
pythonpython.exe scripts/run_supervisor_sh07.py --mode live --confirm-live --worktree <temp>
l-supervisor-sh07
~~~

Pass criteria for stage 3 exit: full suite green; Tier A test green; Tier B evidence recorded (or NL-BP-063 explicitly left blocked with evidence + automatic mode disabled); `verify_supervisor.py` 0 failed; no live-tree writes outside the worktree; no cloud/network use; no commit to the worktree; backlog/index statuses updated only from evidence.

---

## 18. Risks and open questions

### Risks (ranked)

1. **Local 7B/9B model reliability** (highest): two consecutive real missions may fail even with the harness; failure is evidence, not a reason to weaken gates. Mitigation: tiny/independent requirements, staged repair loop, model overrides, accept `BLOCKED` and keep automatic mode opt-in.
2. **Backlog schema drift**: INDEX.json is 214 KB human-authored; parser must fail closed on schema_version/unknown dependencies. Mitigation: schema validation, content hashes, sync warnings, tests with fixture copies.
3. **Self-certification of backlog status**: supervisor updating authored Markdown would be unsafe. Mitigation: SQLite-only supervisor statuses; authored updates human/backend-only with evidence pointers; tests assert no write to `docs/`.
4. **Daemon expectations**: C3 `--detach` is a process, not a Windows service; reboot/relaunch needs a launcher (stage 6). Document honestly; do not claim unattended 24/7 operation.
5. **Lease/clock edge cases**: stale-lease steal could allow dual writers on clock skew/pid reuse. Mitigation: TTL + pid/host proof + `mission_lock` as ultimate guard + fail-closed LeaseConflict; tests simulate stale/dead/live owners.
6. **SQLite concurrency**: heartbeat + GUI + mission writes share one DB; WAL/busy_timeout help; short transactions only, no transaction held across model calls. Mitigation: tests for heartbeat under concurrent writes; retries.
7. **Evidence growth / retained artifacts**: DB rows small but runs/queue JSON can accumulate. Mitigation: 90-day manual cleanup command; no automatic deletion of recovery/evidence.
8. **Permissions/tool-registry dependency ordering**: stage-3 code depends on stage-2 modules landing (task-18/19). Mitigation: C3a/C3b do not import them; C3c imports `permissions` defensively with fail-closed behavior (missing module -> automatic mode BLOCKED with clear message).
9. **Stop latency**: canonical stop is boundary-based; a long model call can delay it. Mitigation: model/request timeouts, status shown as STOPPING, optional future mid-call cancellation; never advertise instant stop.
10. **Self-modification during a run**: a mission may change supervisor/orchestrator code; process continues old code. Mitigation: `restart_required` evidence + event; no hot reload; next run loads new code after the candidate passes and is promoted.
11. **Machine inference lease only within one app-data DB**: separate portable installs are not coordinated; GPU contention across them is not solved in C3 (NL-BP-070/071, stage 4). Document.
12. **Backlog program-stage gating vs real repository state**: stage 2 may still be in_progress while stage-3 implementation is manually underway; the planner must not start stage-4 work. Mitigation: explicit stage gate + recorded `advance-stage` only.

### Open questions for the Lead/user (need a decision before C3c/C3e)

1. **Authored backlog writes**: confirm human-only in C3 (recommended) vs. a narrowly scoped backend writer that updates only Status/Evidence/Note fields after verified missions.
2. **Process model**: accept foreground/thread + optional `--detach` process for C3 (recommended), with a real service/Task Scheduler integration in stage 6? Or require a true daemon now (adds Windows service work and installer dependency).
3. **SH-07 live run authorisation**: confirm permission to run two real local-model missions in an isolated `git worktree` (no commit, no live DB, `NL_DATA_DIR` temp) and to record the evidence under `build/phase3/evidence/`; who approves the two selected requirements at execution time.
4. **NL-BP-063 definition of done**: is Tier A + Tier B (isolated worktree, real local models) sufficient, or must the two missions be real self-build improvements promoted into the main repository? (Recommended: Tier A+B for stage 3 exit; a later real self-build pair is a release criterion NL-BP-146/147.)
5. **Parallel workstreams**: keep C3 strictly single-mission (recommended) or implement independent-workstream parallelism now (needs write-scope disjointness supervisor, more risk).
6. **Mission wall-clock enforcement**: soft post-return classification (recommended, no mid-call kill) vs. hard cancellation (needs cooperative model/provider timeouts and risks partial staged candidates).
7. **Canonical runtime location of supervisor evidence**: app data dir (recommended, portable via NL_DATA_DIR) vs. repository build/ (acceptance artifacts only).

---

## 19. Test plan summary

| File | Tests (approx) | Runtime | Type |
|---|---|---|---|
| `tests/test_supervisor_store.py` | 13-15 | < 2 s | unit (SQLite temp, NL_DATA_DIR) |
| `tests/test_backlog_planner.py` | 10-12 | < 2 s | unit (fixture INDEX) |
| `tests/test_supervisor_core.py` | 15-18 | ~5-8 s | integration with fake orchestrator (no LLM) |
| `tests/test_supervisor_cli.py` | 5-6 | < 1 s | CLI parsing/status |
| `tests/test_supervisor_sh07.py` | 8 | ~15-20 s (real candidate+oracle verifier on tiny project) | end-to-end, fake model |
| `tests/test_selfbuild_runner.py` (modified) | 19 (kept/adapted) | ~2 s | shim compatibility |
| `scripts/run_supervisor_sh07.py` | n/a | manual, 5-30 min | Tier B acceptance evidence |
| `scripts/verify_supervisor.py` | n/a | < 2 s | read-only gate |

Rules: every test sets `NL_DATA_DIR` to a temp dir; no test touches the live SQLite DB; no Ollama/CrewAI kickoff; no `run_autonomous` against the real repo; no commit; no self-build run; verification subprocesses only inside disposable copies (existing pattern). Full suite after stage 3: baseline 149 + ~50 = ~199 expected (measure and record; do not hardcode claims before running).

---

## Appendix A - Configuration examples

~~~json
// app_settings["supervisor.global"]
{
  "mode": "off",
  "max_missions_per_run": 1,
  "max_attempts_per_requirement": 2,
  "max_wall_time_s": 3600,
  "heartbeat_interval_s": 5,
  "lease_ttl_s": 30,
  "backoff_schedule_s": [30, 120, 600, 1800],
  "allowed_cloud_models": []
}

// app_settings["supervisor.project.1"]
{
  "mode": "assisted",
  "max_missions_per_run": 2,
  "program_stage_override": null,
  "developer_model": "ollama/qwen2.5-coder:7b-instruct-q4_K_M",
  "reviewer_model": "ollama/qwen3.5:9b"
}
~~~

## Appendix B - Queue/evidence record examples

~~~json
// mission_queue row (compact)
{
  "id": 12, "project_id": 1, "requirement_id": "NL-BP-061",
  "state": "NEEDS_FIX", "priority": "P0",
  "idempotency_key": "f0c1...", "attempts": 1, "max_attempts": 2,
  "failure_class": "REPAIRABLE",
  "failure_signature": "9ac3...", "mission_id": 46
}

// mission_evidence row
{
  "mission_id": 46, "queue_id": 12, "kind": "verification",
  "record_key": "candidate+oracle", "sha256": "…",
  "payload": {"candidate": {"passed": true, "exit_code": 0},
              "oracle": {"passed": true, "exit_code": 0}}
}
~~~

## Appendix C - Planned CLI help (supervisor group)

~~~text
usage: nl_agent.py supervisor <command> [options]

commands:
  run      run the persistent supervisor loop (foreground; --detach for a process)
  start    persist mode and start the supervisor (detached process)
  stop     request a graceful stop of the active supervisor
  pause    pause after the current mission
  resume   clear pause/stop flags and continue
  status   print supervisor/lease/queue/budget status (--json)
  index    check/sync the indexed backlog and show the next requirement
  recover  reconcile queue/stage/journal state (--dry-run)
  advance-stage  explicitly advance the program stage (human/backend, evidence required)
~~~

## Appendix D - Traceability

| Backlog ID | Where this design covers it |
|---|---|
| NL-BP-012 | handoffs reused; `missions.requirement_id`/queue/evidence links; section 6/13 |
| NL-BP-050/051 | durable queue/runs/evidence + reconcile (sections 5/6/10/16) |
| NL-BP-052 | lease/heartbeat + mission_lock composition (section 7) |
| NL-BP-053 | queue single-mission, write-scope collision skip in selection; dependencies DAG (existing task_graph reused by orchestrator) |
| NL-BP-061 | whole document; primarily sections 4/7/8/9 |
| NL-BP-062 | section 10 (INDEX.json -> SQLite -> selection; no roadmap) |
| NL-BP-063 | section 14 (SH-07 Tier A/B, evidence requirements) |
| NL-BP-064 | sections 9/11/12 (modes, budgets, approvals, pause/stop) |
| NL-BP-065 | section 11.3 (failure class/signature/dead-letter) |
| NL-BP-066/067 | deferred to stage 4 (fixed roles in C3; queue/evidence hooks ready) |
| NL-BP-070/071 | minimal resource gate in C3; full scheduler/GPU policy stage 4 |
| NL-BP-072/073/076 | consumed from stage 2 (permissions/tool registry/cloud) - sections 3/12 |
| NL-BP-075 | status/diagnostics/correlation ids (section 13) |
| NL-BP-077 | project registry/open_project reused by supervisor preflight |
| SH-07 | section 14 |
| SPEC-02/02A/15/21/26/28, 13A | section 3 invariants + failure matrix + acceptance |

---

## Appendix E - Explicit non-goals for C3 (do not claim these)

- No OS sandbox, container or privilege isolation; candidate tests still execute candidate code with user privileges (existing declared limitation).
- No always-on Windows service / reboot survival; `--detach` is a background process only.
- No parallel missions/workstreams or multi-agent team optimization (NL-BP-066/067 stage 4).
- No automatic cloud fallback; no cloud/network without grants and consent.
- No self-modifying policy: supervisor cannot change mode/budget/permissions/backlog from model output.
- No automatic rewriting of `docs/PRODUCT_BACKLOG.md` / `INDEX.json`; those updates are human/backend, evidence-reviewed.
- No automatic program-stage advancement; explicit `advance-stage --confirm` with evidence only.
- No deletions, migrations, installs, publishing or cleanup during a normal mission.
- No unbounded loop: every run is capped by missions/time/attempts/consecutive failures.

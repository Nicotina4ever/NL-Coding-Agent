# Tool, Safety and Self-Modification Policy

## Tool permissions

Classify operations:
- READ: file/list/search/status.
- WRITE_REVERSIBLE: patch/create tracked source files.
- EXECUTE_SAFE: tests/build/lint/status.
- EXECUTE_RISKY: installers, network changes, migration scripts, destructive commands.
- DESTRUCTIVE: delete/reset/clean operations.

Normal autonomous mode may perform READ, WRITE_REVERSIBLE and known-safe verification inside the
active project.

Risky/destructive operations require policy approval.

## Workspace boundaries

The active project root is the default boundary.

Symlinks/junctions and resolved paths must not silently escape the project boundary.

Protected/vendor paths in the Coding Agent workspace:
- python/
- crewAI/
- crewAI-tools/
- user backup archives
- model/cache locations outside the project

## Git

Git is the preferred lightweight rollback mechanism.

Before a coding mission:
- inspect clean/dirty state;
- never silently discard user changes;
- record pre-existing changes;
- keep agent changes distinguishable.

Do not run destructive `git reset --hard` or `git clean -fdx` autonomously.

## Self-modification

Self-build changes must be treated as candidate updates.

A running GUI should not attempt to hot-reload arbitrary rewritten core modules.
Preferred flow:
- produce candidate source;
- execute tests in child process;
- review diff;
- mark update ready;
- restart application to load the new version.

## Cloud escalation

Cloud fallback is off by default.
The UI must show when a model is cloud-backed.
Project policy controls whether source content can leave the machine.


## Staged candidate and promotion harness (implemented 2026-10-28)

The autonomous mission pipeline now runs through a staged-candidate harness
(SPEC-28, phase-2 commits C1-C7). This section describes the enforced behavior;
it is not a claim of a complete OS sandbox.

### Write path

- Model-facing tools are limited to four file operations: `read_file`,
  `write_file`, `patch_file`, `list_dir`. There is no shell, test-runner or git tool
  exposed to the model (removed in C2; SPEC-28 SH-05 note).
- Developer and debugger stages bind those tools to a **staged workspace** under
  `<project>/data/staging/mission-<id>-<suffix>/workspace`. The Markdown/JSON
  text-action fallback writes to the same staged workspace. Nothing is written to
  the live project tree before promotion.
- A stage is created from a text snapshot of the project (vendor trees,
  `python/`, `crewAI/`, caches, `data/`, logs, dist/build and binary assets are
  excluded) and its scope comes from the declared task write paths (or a derived
  top-level scope).

### Gates before promotion

1. **Integrity validation** (`nl_coding_agent/core/staging_broker.py`,
   `code_integrity_gate.py`): AST-based stub detection, weakened-test detection,
   out-of-scope files, protected/absolute paths and mission-input files (for
   example `docs/NEXT_SELF_BUILD_MISSION.md`) are rejected before any live write.
2. **Independent regression verification** (`core/candidate_verification.py`): the
   staged source is copied to a disposable directory and the project suite runs
   twice with the real embedded interpreter - once with the candidate tests
   (must pass) and once with **baseline pinned tests** over the candidate source
   (oracle, must pass). A green candidate with weakened tests fails the oracle.
   The suite runs with a throw-away `NL_DATA_DIR`, offscreen Qt and no cache.
3. **Review**: the reviewer sees the candidate diff, validation result and
   verification runs, and is told the candidate is not applied; a REJECT leaves
   the live tree byte-identical.

### Promotion and recovery

- Promotion is the last gate and only runs after reviewer APPROVE. It asserts a
  byte/text hash invariant (Windows CRLF normalization), checks live drift with
  compare-and-swap semantics, writes an explicit recovery point
  (`data/recovery/<mission>.json`) and promotes through the broker journal
  (`promotion-journal.json`). A crash between files is reconciled at resume:
  all-after = complete, all-before = retry, mixed = CAS rollback of the recorded
  post-images, any conflicting human edit = blocked (never overwritten).
- Mission status semantics: `completed` is written only after a verified
  promotion; every gate failure writes `blocked`; blocked/interrupted results
  never claim staged paths as applied changes (they are recorded as staged
  candidate paths in handoffs). Legacy missions (no `harness_version`) cannot be
  resumed by the staged-candidate pipeline.

### Declared limitations (do not overclaim)

- Candidate tests execute candidate code with the current user's OS privileges;
  there is no OS sandbox. Mitigations are the four-tool surface, disposable
  verification copies, scrubbed environment, timeouts and the promotion gates.
- Network access is not isolated.
- A legitimate behaviour change that requires changing the pinned baseline tests
  is blocked by the oracle gate pending a human-reviewed baseline update.
- Promoted files are normalized to LF; an external CRLF checkout would see a
  line-ending change on promoted files.


## Permissions, external tools and retention (implemented 2026-10-28)

- **Capability permissions** are human/backend-owned and fail closed: read/write/execute
  are local defaults; delete/network/cloud require an explicit grant stored in
  `app_settings` with audit events. Model-facing tools do not import the permission
  API, so an agent cannot grant itself a capability; there is no bypass flag.
- **Cloud escalation** is denied by default: a cloud model requires an explicit CLOUD
  grant, and a non-loopback provider endpoint requires NETWORK, enforced before any LLM
  instance is created.
- **External tools** are discovered read-only through a registry of fixed descriptors
  (git, embedded Python, pytest, Ollama, ffmpeg). Probes run only fixed argv lists with
  shell=False and a hard timeout, or a localhost health GET; there is no API for
  arbitrary command strings.
- **Recovery retention** is auditable and explicit: read-only inventory, verified zip
  archives, and cleanup only after confirmation against a validated archive manifest.
  Nothing is deleted automatically.

## Persistent autonomous supervisor (stage 3, implemented C3a-C3d, 2026-10-28)

- The supervisor is **non-LLM policy code** in `nl_coding_agent/core/supervisor.py`; it
  owns a durable queue, lease/heartbeat, preflight and evidence ledger, and drives the
  existing staged-candidate orchestrator. The model cannot select its own next task,
  grant permissions, change modes/budgets or disable stop/pause.
- **Autonomy is opt-in and off by default.** Modes Off/Assisted/Automatic are persisted per
  project; every mode still needs read/write/execute grants, and cloud/network/delete stay
  denied unless explicitly granted. There is no flag or environment variable that bypasses
  the permission gate.
- **Start/stop/pause/resume are independent of any chat**: durable commands are consumed by
  the loop, and the GUI/CLI send the same commands. Stop is **cooperative at safe
  checkpoints** (never between the reviewer APPROVE and the promotion write); it can take as
  long as the current model/verification call. Pause is honoured at mission boundaries.
- **Honest limitations:** the supervisor is a process/thread loop, not an OS service — a
  reboot or crash requires restarting it, and the stale lease is reclaimed only after TTL +
  process-liveness proof. Candidate and test code still execute with the user's OS
  privileges (no OS sandbox, no network isolation). The machine inference slot serializes
  local inference only within one app-data database; cross-install GPU contention remains
  future work (NL-BP-070/071).
- **Evidence and fail-closed behavior:** queue/backlog/evidence/run transitions are durable
  before success is reported; unresolved promotion journals, live leases/locks, invalid
  backlog indexes, missing grants or missing local models block or wait with an exact resume
  command. The read-only gate is `scripts/verify_supervisor.py`.
- **Tier B (real local-model two-mission) evidence is not yet recorded**; automatic mode
  remains opt-in and SH-07 Tier A (fake model) is the only supervisor acceptance evidence so
  far (NL-BP-063 stays blocked).

## SH-07 real-model acceptance evidence (2026-10-28)

Tier B was executed twice on isolated worktrees with local models. Attempt 1 exposed a
documentation-only candidate hole (fixed in 2a44460); attempt 2 was BLOCKED by the candidate
validation gate when the local developer weakened a test file - no promotion, no live write,
clean worktree. This is recorded as honest evidence, not hidden: NL-BP-063 stays blocked and
the supervisor default mode stays off. See docs/SH07_TIERB_EVIDENCE.md.


## CrewAI Flow pipeline, HITL and model routing (stage 4, C4a-C4e)

- **Flow is opt-in only.** Sequential remains default; Flow mission execution is selected
  explicitly (```pipeline="flow"```) and reuses the same staged-candidate validator,
  candidate+oracle verification, reviewer gate and promotion-last CAS/journal machinery.
  No gate is weakened or duplicated.
- **No real-model Flow acceptance.** All Flow/parity/crash evidence is fake-model in temp
  projects/data dirs; real local-model Flow reliability is unverified, which is why Flow is not
  the default.
- **HITL approvals are deterministic.** Reviewed action table maps pauses to durable approval
  rows (no LLM collapse); approve resumes, deny blocks with the live tree unchanged, expiry is
  handled by the store, decisions are audited as human/backend events.
- **Memory is off by default.** Local-only policy (explicit storage path, no cloud/remote
  embedder) is validated, but CrewAI memory wiring is deferred; the app SQLite evidence ledger
  remains the memory of record and no CrewAI default storage is written.
- **Telemetry is off by default** via ```crew_runtime_env()```; Flow state lives only in the app
  SQLite DB.
- **No OS sandbox / network isolation.** Candidate/test code runs with user privileges;
  permission grants and promotion gates are the mitigations. Capability probes require explicit
  human action and are not run in tests.
- **No silent cloud fallback.** Unknown/declared capabilities never satisfy a role requirement,
  cloud/remote models require explicit grants, and ```permissions.assert_model_permitted```
  remains the only gate before LLM construction.

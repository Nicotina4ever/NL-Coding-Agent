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

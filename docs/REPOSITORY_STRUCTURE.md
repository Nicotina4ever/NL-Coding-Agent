# Repository Structure and Ownership

**Status:** authoritative for the repository layout after the 2026-10-28 hygiene follow-up
(shared `task-34`), the root reorganization Phase A (shared `task-44`), Phase B
(shared `task-45`; generated roots consolidated under `.workspace/`) and Phase C
(shared `task-46`; crewAI checkout staged under `da_eliminare/`). Measured before/after
inventory and validation are in `docs/REPOSITORY_HYGIENE_FOLLOWUP.md`,
`.workspace/build/root_reorg/REPORT.md` and `docs/CREWAI_CHECKOUT_REMOVAL_PROPOSAL.md`.
**Rule:** all paths are repository-relative. Do not introduce absolute workspace paths into
documentation, launchers or runtime code — the repository must stay relocatable.

## Top-level ownership matrix

| Path | Class | Git | Owner / writer | Purpose | Cleanup / retention | Ship in portable payload? |
|---|---|---|---|---|---|---|
| `AGENTS.md` | governance | tracked | Lead | Binding workspace rules, containment, verification invariant, vendor policy | Keep; update with behavior changes | No (developer doc) |
| `README.md` | user doc | tracked | Lead | Single authoritative overview, quick start, docs map | Keep | Recommended (stage-6 follow-up) |
| `pyproject.toml` | config | tracked | developers | Package metadata, dependencies, pytest config | Keep | Yes (allowlisted) |
| `.gitignore` | config | tracked | developers | Ignore rules for generated/user/vendor content | Keep | No |
| `SHA256_MANIFEST.json` | integrity metadata | tracked | safety owner | SHA-256 certification of the 5 audited safety-foundation files (verified 5/5) | Keep at root while those files exist; removal requires migrating the evidence | No |
| `nl_agent.py` + `NL Coding Agent.bat` | entry points | tracked | developers | CLI entry point and the single user-facing launcher at the repository root (desktop GUI); both resolve the repository/payload root | Keep at root | `nl_agent.py` + `NL Coding Agent.bat` |
| `scripts/launchers/**` | launchers | tracked | developers | Diagnostics/status/self-build launchers plus VoiceBridge audit/work launchers; every launcher resolves the repository/payload root itself | Keep; portable launchers are re-staged to the payload root by `scripts/stage_portable.py` | `doctor.bat`, `status.bat`, `Self-Build Mode.bat` at payload root (VoiceBridge launchers are development-only) |
| `python/` | embedded runtime | **ignored** | release owner | Python 3.12 + installed packages (CrewAI, PySide6, psutil, PyYAML, pytest) | Never edited by hand except `python\\python.exe -m pip`; never committed; never cleaned by hygiene | Yes (independent runtime) |
| `nl_coding_agent/` | application source | tracked | developers | CLI, GUI, orchestration, supervisor, flows, projects, persistence, tools | Normal source review flow | Yes (allowlisted) |
| `tests/` | tests | tracked | developers | Pytest suite and fixtures | Keep; never shipped | No |
| `scripts/` | developer tooling | tracked | developers | Read-only audits/gates, portable staging, SBOM check, migration tools and consolidated launchers (`scripts/launchers/`) | Keep; scripts must be read-only unless explicitly an apply tool | No (the portable launchers are re-staged to the payload root) |
| `installer/` | distribution tooling | tracked (stage 6, in progress) | stage-6 owner | Lightweight bootstrapper/installer bootstrap and platform manifest | Keep with stage-6 work | No (it *builds* the payload) |
| `config/` | runtime config | tracked | developers | `models.yaml` (roles/models), `voicebridge.yaml` (external project, machine-local) | Keep; `config/voicebridge.yaml` is never shipped | `models.yaml` only |
| `assets/` | assets | tracked | product/GUI owner | Real SVG logo + theme tokens | Keep | Yes (allowlisted) |
| `.agents/` | agent instructions | tracked | Lead | Agent definitions, rules, skills for agentic sessions | Keep | No |
| `docs/` | documentation | tracked | Lead/docs owners | Product, program, evidence and history docs | Keep; evidence retained through release acceptance | No |
| `docs/history/legacy/` | archived evidence | tracked | Lead | Dated legacy docs + patch evidence moved from the root | **Never deleted**; verbatim | No |
| `docs/evidence/` | acceptance evidence | tracked | stage owners | SH-07 evidence, CrewAI SBOM | Retain for audit traceability | No |
| `da_eliminare/` | review-only staging | **ignored** (README tracked) | user/Lead | Staging for material that appears no longer needed; nothing is deleted or archived without explicit user authorization | Review-only; never shipped; portable payload and release builder exclude it | Never |
| `data/` | user data | **ignored** | runtime | SQLite DB, self-build state, backups, mission baselines, staging, recovery. Deliberately stays at the repository root (relocation-acceptance dependency; not moved by Phase B). | **Never deleted/shipped**; back up before migrations; restore only from verified backup | Never |
| `.workspace/` | generated workspace | **ignored** | runtime/task owners | Single generated-data root (ROOT REORG Phase B): `build/` phase evidence, audits and scratch; `dist/` release candidates; `logs/`; `temp/`; `cache/`; `state/`. Default `<repo>/.workspace`; override `NL_WORKSPACE_DIR`; policy in `nl_coding_agent/core/workspace.py`. | Safe to regenerate/clear with the app and tests stopped (evidence retention by owner decision); never committed or shipped | Never |
| `docs/history/legacy/temp-scripts/` | archived one-off repair scripts | tracked | — | Historical DB/source repair scripts (superseded; their functionality is integrated in the committed tree) | **Never deleted or executed**; verbatim historical evidence | Never |
| `da_eliminare/crewAI/` | review-only staging (vendor checkout) | **ignored** (inside `da_eliminare/`) | user/Lead | Reference-only upstream CrewAI checkout (own `.git`, docs), moved intact by ROOT REORG Phase C (task-46). **Not imported**: the app uses installed `crewai==1.15.32`. The SBOM/legal gate reads its `LICENSE` | Review-only; nothing deleted, archived or removed from Git without explicit user authorization; restore by moving back to `crewAI/` | Never |
| | `crewAI-tools/` | vendor checkout | **ignored** | — | Legacy vendor checkout; absent at this audit | Same policy if restored | Never |
| `.git/` | git metadata | ignored | git | Repository history and worktree registrations | Never shipped; never cleaned | Never |

## Generated, cache and scratch policy

| Category | Location | Rule |
|---|---|---|
| Python bytecode / tool caches | `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/` | Regenerated on demand; git-ignored; never shipped; safe to delete with the app and tests stopped. Never touch caches inside `python/` or the staged vendor checkout (protected). |
| Coverage output | `.coverage*`, `htmlcov/` | Regenerated; git-ignored; never shipped. |
| OS/app scratch | `.workspace/temp/`, `tmp/`, `*.tmp`, `*.bak`, `nul` | Ephemeral; git-ignored; may be emptied when no process holds files. |
| Accidental variable-expansion tree | `%SystemDrive%/` | Must never exist (a literal unexpanded variable created one in the past; it was removed). Defensively git-ignored. |
| Build evidence | `.workspace/build/` | Git-ignored; evidence for open acceptance decisions; removed only after the decision is closed and with owner agreement. |
| Release payloads | `.workspace/dist/` | Git-ignored; at most one verified candidate; the stale `.workspace/dist/portable-release` needs explicit authorization before replacement/removal (stage-6 decision). |
| Runtime caches | `python/`, `crewAI/` | Protected — hygiene passes never clean inside vendor/runtime trees. |

**Backup rule:** `data/` is authoritative user/mission data. Before any migration or cleanup that
touches `data/`, copy `data/nl_coding_agent.sqlite3` (plus `-wal`/`-shm`) and
`data/selfbuild_state.json` to a dated folder under `data/backups/` and verify the copy.

## Development-only files (never shipped in the portable payload)

The portable build is **allowlist-based** (`scripts/stage_portable.py`): only `nl_agent.py`,
`nl_coding_agent/`, `python/`, `assets/`, `config/`, `pyproject.toml`, the root
`NL Coding Agent.bat`, and the three CLI launchers re-staged from `scripts/launchers/` to the
payload root (`doctor.bat`, `status.bat`, `Self-Build Mode.bat`) are included. Everything below
is development-only and must stay outside the payload:

- **Repository metadata:** `.git/`, `.gitignore`, `.agents/`.
- **Development sources and tests:** `tests/`, `scripts/` (except the launchers explicitly
  re-staged to the payload root), `installer/`.
- **Review-only staging:** `da_eliminare/` (git-ignored except for its README; never shipped).
- **Documentation and evidence:** `docs/` (including `docs/history/legacy/`, `docs/evidence/`,
  this document, audit/plan/backlog docs). The root `AGENTS.md` is developer-only; a user-facing
  `README.md` **should** be added to the payload by the stage-6 build owner.
- **Generated/transient:** `.workspace/` (build evidence, release candidates, logs,
  temp/cache/state), caches, `*.pyc`/`*.pyo`, `.pytest_cache/`,
  `.ruff_cache/`, `.mypy_cache/`, `.venv/`, `venv/`.
- **User data and diagnostics:** `data/`, `*.sqlite3`, `*.db`; generated logs/state are
  inside `.workspace/`.
- **Machine-local configuration:** `config/voicebridge.yaml`, `config/voicebridge.local.yaml`
  (external project paths and user data; explicitly excluded by the staging tool).
- **Vendor reference trees:** `da_eliminare/crewAI/` (reference-only upstream checkout with its
  own `.git`, staged by Phase C task-46; not imported at runtime — the installed CrewAI package is
  bundled via `python/`) and `crewAI-tools/` if ever restored. Nothing in `da_eliminare/` is
  shipped; permanent deletion requires owner authorization plus preserved license/SBOM evidence.
- **Historical/legal evidence:** `SHA256_MANIFEST.json`, the archived one-off repair scripts in
  `docs/history/legacy/temp-scripts/`, and the archived patch evidence in
  `docs/history/legacy/patch-evidence/`.

Packaging must never recurse into `.workspace/`, and must not copy the embedded runtime from
inside an existing payload. Portable independence smoke tests run only in a managed temporary
directory and record their cleanup path (see `AGENTS.md`).

## Workspace layout (ROOT REORG Phase B)

Generated data uses one configurable root, default `<repository>/.workspace` and overridable
with `NL_WORKSPACE_DIR`; the single policy module is
`nl_coding_agent/core/workspace.py` (`workspace_root()`, `workspace_path()`,
`build_root()`, `dist_root()`, `logs_root()`, `temp_root()`, `cache_root()`,
`state_root()`).

| Child | Purpose |
|---|---|
| `.workspace/build/` | Transient build/audit evidence and generated reports |
| `.workspace/dist/` | Release candidates and portable payloads (at most one verified) |
| `.workspace/logs/` | Run logs and diagnostics |
| `.workspace/temp/` | Disposable scratch files |
| `.workspace/cache/` | Application caches |
| `.workspace/state/` | Legacy bootstrap CLI state |

`python/` (the embedded runtime shipped in the payload) and `data/` (live SQLite user data,
backups, recovery, mission baselines) deliberately stay at their historical repository-relative
paths: they are a relocation-acceptance dependency and are checked by
`scripts/verify_relocation.py`. `.workspace/` is git-ignored, excluded from the portable payload
and the source-release builder, and `tests/test_workspace_paths.py` fails if a legacy root
output directory (build/dist/logs/temp/cache) reappears.

## Relocation safety

- Documentation and commands must use repository-relative paths or `%~dp0`-style launcher
  resolution; no absolute workspace paths.
- `scripts/verify_relocation.py` is the read-only gate that verifies the canonical root, project
  identity, state keys and operational documentation after any move/rename.
- File moves in this repository use `git mv` so history is preserved and rollback stays simple.
- Launchers resolve the repository/payload root themselves (a `%~dp0` fallback chain); keep
  exactly one user-facing launcher at the repository root. `scripts/stage_portable.py` re-maps
  the consolidated CLI launchers to the payload root.

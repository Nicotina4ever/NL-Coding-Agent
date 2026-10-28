# Repository Structure and Ownership

**Status:** authoritative for the repository layout after the 2026-10-28 hygiene follow-up
(shared `task-34`). Measured before/after inventory and validation are in
`docs/REPOSITORY_HYGIENE_FOLLOWUP.md`.
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
| `nl_agent.py` + `*.bat` launchers | entry points | tracked | developers | CLI/GUI/self-build/status/doctor/VoiceBridge entry points; all resolve their own folder | Keep at root (user-facing) | `nl_agent.py` + 2 main launchers only (per staging allowlist) |
| `python/` | embedded runtime | **ignored** | release owner | Python 3.12 + installed packages (CrewAI, PySide6, psutil, PyYAML, pytest) | Never edited by hand except `python\\python.exe -m pip`; never committed; never cleaned by hygiene | Yes (independent runtime) |
| `nl_coding_agent/` | application source | tracked | developers | CLI, GUI, orchestration, supervisor, flows, projects, persistence, tools | Normal source review flow | Yes (allowlisted) |
| `tests/` | tests | tracked | developers | Pytest suite and fixtures | Keep; never shipped | No |
| `scripts/` | developer tooling | tracked | developers | Read-only audits/gates, portable staging, SBOM check, migration tools | Keep; scripts must be read-only unless explicitly an apply tool | No |
| `installer/` | distribution tooling | tracked (stage 6, in progress) | stage-6 owner | Lightweight bootstrapper/installer bootstrap and platform manifest | Keep with stage-6 work | No (it *builds* the payload) |
| `config/` | runtime config | tracked | developers | `models.yaml` (roles/models), `voicebridge.yaml` (external project, machine-local) | Keep; `config/voicebridge.yaml` is never shipped | `models.yaml` only |
| `assets/` | assets | tracked | product/GUI owner | Real SVG logo + theme tokens | Keep | Yes (allowlisted) |
| `.agents/` | agent instructions | tracked | Lead | Agent definitions, rules, skills for agentic sessions | Keep | No |
| `docs/` | documentation | tracked | Lead/docs owners | Product, program, evidence and history docs | Keep; evidence retained through release acceptance | No |
| `docs/history/legacy/` | archived evidence | tracked | Lead | Dated legacy docs + patch evidence moved from the root | **Never deleted**; verbatim | No |
| `docs/evidence/` | acceptance evidence | tracked | stage owners | SH-07 evidence, CrewAI SBOM | Retain for audit traceability | No |
| `data/` | user data | **ignored** | runtime | SQLite DB, self-build state, backups, mission baselines, staging, recovery | **Never deleted/shipped**; back up before migrations; restore only from verified backup | Never |
| `logs/` | diagnostics | **ignored** | runtime | Run logs and historical mission output | Retention by user decision; never shipped | Never |
| `build/` | transient evidence | **ignored** | task owners | Phase evidence, audit reports, scratch scripts, relocation evidence | Safe to regenerate; keep through the relevant acceptance decision; not shipped | Never |
| `dist/` | release artifacts | **ignored** | release owner | At most one verified portable candidate | Existing `dist/portable-release` is stale (missing current packages): rebuild only at stage 6 with explicit authorization | Never packaged into itself |
| `temp_*.py` (root) | one-off repair scripts | tracked | — | Historical DB/source repair scripts (superseded) | **Proposal only** — see `docs/REPOSITORY_HYGIENE_FOLLOWUP.md`; do not execute | Never |
| `crewAI/` | vendor checkout | **ignored** | vendor owner | Reference-only CrewAI source checkout (own `.git`, docs). **Not imported**: the app uses installed `crewai==1.15.32` | Protected; no cleanup; replacement/archival needs explicit user authorization | Never |
| `crewAI-tools/` | vendor checkout | **ignored** | — | Legacy vendor checkout; absent at this audit | Same policy if restored | Never |
| `.git/` | git metadata | ignored | git | Repository history and worktree registrations | Never shipped; never cleaned | Never |
| `state/`, `cache/`, `temp/` | runtime/scratch | **ignored** | runtime | Reserved application-state/cache/temp roots when used (currently the app keeps state under `data/`); `temp/`/`cache/` are ephemeral and may be emptied | Safe to clear when the app is stopped; never back up merged content | Never |

## Generated, cache and scratch policy

| Category | Location | Rule |
|---|---|---|
| Python bytecode / tool caches | `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/` | Regenerated on demand; git-ignored; never shipped; safe to delete with the app and tests stopped. Never touch caches inside `python/` or `crewAI/` (protected). |
| Coverage output | `.coverage*`, `htmlcov/` | Regenerated; git-ignored; never shipped. |
| OS/app scratch | `temp/`, `tmp/`, `*.tmp`, `*.bak`, `nul` | Ephemeral; git-ignored; may be emptied when no process holds files. |
| Accidental variable-expansion tree | `%SystemDrive%/` | Must never exist (a literal unexpanded variable created one in the past; it was removed). Defensively git-ignored. |
| Build evidence | `build/` | Git-ignored; evidence for open acceptance decisions; removed only after the decision is closed and with owner agreement. |
| Release payloads | `dist/` | Git-ignored; at most one verified candidate; stale payloads need explicit authorization before replacement/removal (stage-6 decision). |
| Runtime caches | `python/`, `crewAI/` | Protected — hygiene passes never clean inside vendor/runtime trees. |

**Backup rule:** `data/` is authoritative user/mission data. Before any migration or cleanup that
touches `data/`, copy `data/nl_coding_agent.sqlite3` (plus `-wal`/`-shm`) and
`data/selfbuild_state.json` to a dated folder under `data/backups/` and verify the copy.

## Development-only files (never shipped in the portable payload)

The portable build is **allowlist-based** (`scripts/stage_portable.py`): only `nl_agent.py`,
`nl_coding_agent/`, `python/`, `assets/`, `config/`, `pyproject.toml` and the main launchers are
included. Everything below is development-only and must stay outside the payload:

- **Repository metadata:** `.git/`, `.gitignore`, `.agents/`.
- **Development sources and tests:** `tests/`, `scripts/`, `installer/`.
- **Documentation and evidence:** `docs/` (including `docs/history/legacy/`, `docs/evidence/`,
  this document, audit/plan/backlog docs). The root `AGENTS.md` is developer-only; a user-facing
  `README.md` **should** be added to the payload by the stage-6 build owner.
- **Generated/transient:** `build/`, `dist/`, caches, `*.pyc`/`*.pyo`, `.pytest_cache/`,
  `.ruff_cache/`, `.mypy_cache/`, `.venv/`, `venv/`.
- **User data and diagnostics:** `data/`, `logs/`, `state/`, `temp/`, `*.sqlite3`, `*.db`.
- **Machine-local configuration:** `config/voicebridge.yaml`, `config/voicebridge.local.yaml`
  (external project paths and user data; explicitly excluded by the staging tool).
- **Vendor reference trees:** `crewAI/`, `crewAI-tools/` (not imported at runtime; the installed
  CrewAI package is bundled via `python/`).
- **Historical/legal evidence:** `SHA256_MANIFEST.json`, `temp_*.py`, and the archived patch
  evidence in `docs/history/legacy/patch-evidence/`.

Packaging must never recurse into `dist/` or `build/`, and must not copy the embedded runtime from
inside an existing payload. Portable independence smoke tests run only in a managed temporary
directory and record their cleanup path (see `AGENTS.md`).

## Relocation safety

- Documentation and commands must use repository-relative paths or `%~dp0`-style launcher
  resolution; no absolute workspace paths.
- `scripts/verify_relocation.py` is the read-only gate that verifies the canonical root, project
  identity, state keys and operational documentation after any move/rename.
- File moves in this repository use `git mv` so history is preserved and rollback stays simple.

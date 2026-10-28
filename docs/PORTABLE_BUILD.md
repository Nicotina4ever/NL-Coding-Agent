# Portable Payload Staging

## Status

Portable payload staging is implemented. It assembles an inspectable one-folder payload from the
workspace without deleting or rewriting source files. It is **not** an installer and it does not
claim that the staged folder has passed clean-directory acceptance tests.

## Command

```powershell
python\python.exe scripts\stage_portable.py --source "." --output "K:\AI\nl-coding-agent-portable" --dry-run
```

Run the command from the repository root (`K:\AI\NL Coding Agent`); `--source` defaults to the
current directory. The output directory must be outside the source tree and must be absent or empty. Use the same
command without `--dry-run` to copy the payload and write `payload_manifest.json`.

## Measured Staging Plan

Dry-run measured on 2026-10-28:

| Metric | Value |
|---|---:|
| Files | 23,711 |
| Total size | 1,547,268,760 bytes (1.44 GiB) |
| Runtime `python/` | 1,546,437,333 bytes (23,656 files) |
| Application `nl_coding_agent/` | 238,141 bytes (48 files) |
| Assets | 590,775 bytes |
| Config | 437 bytes |
| Top-level launchers and entry point | 1,568 bytes |

The plan excludes the 467 MiB `crewAI/` vendor checkout, `crewAI-tools/` if present, user `data/`,
`.workspace/`, tests, docs, scripts, `.git`, and generated caches. The staged payload is
smaller than the full workspace because the vendor checkout is not part of the runtime.

## Included Roots

- `nl_agent.py`
- `nl_coding_agent/`
- `python/` (embedded runtime and installed packages)
- `assets/`
- `config/`
- `pyproject.toml`
- `NL Coding Agent.bat` (root launcher)
- `doctor.bat`, `status.bat`, `Self-Build Mode.bat` when present — these sources live under
  `scripts/launchers/` and are re-staged by `scripts/stage_portable.py` to the payload root
  under their user-facing names

## Excluded Roots and Patterns

- Vendor/reference: `crewAI/`, `crewAI-tools/`
- User data and runtime state: `data/`; generated logs/state/caches: `.workspace/` (ROOT REORG
  Phase B: `build/`, `dist/`, `logs/`, `temp/`, `cache/`, `state/` live there; override with
  `NL_WORKSPACE_DIR`)
- Development-only: `tests/`, `docs/`, `scripts/`, `.agents/`
- Version control: `.git/`
- Caches: `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `node_modules`, `.venv`,
  `venv`
- Bytecode: `*.pyc`, `*.pyo`
- Machine-local project config: `config/voicebridge.yaml`, `config/voicebridge.local.yaml`

Symlinks are skipped. The source tree is never modified.

## Manifest

`payload_manifest.json` records:

- `source` and `output`;
- `created_at` and `dry_run`;
- `file_count` and `total_size`;
- `included_roots`, `excluded_roots`, `excluded_directory_names`, `excluded_suffixes`, and
  `excluded_files`;
- `top_level` entries with `{path, size, files}`.

## Safety Boundaries

- The script refuses an output directory inside the source tree.
- The script refuses a non-empty output directory.
- A dry run writes nothing.
- This document does not authorize deleting `crewAI/`, `python/`, user data, or logs.

## Clean Payload Validation

A real payload was staged at `K:\AI\nl-coding-agent-portable-final` from the workspace and
checked without importing the development tree:

- `python\python.exe nl_agent.py doctor` exited 0, reported `CrewAI: OK (1.15.32)`, found
  Ollama, and reported `Project: not configured (Project root not configured)` instead of
  crashing on the excluded machine-local config.
- Offscreen `MainWindow` constructed six pages, showed `No project open`, and closed cleanly.
- A smoke project at `K:\AI\portable-smoke-project` was opened through the payload, persisted in
  `K:\AI\nl-coding-agent-portable-final\data\nl_coding_agent.sqlite3`, and was still present
  after a second process started.

The current payload keeps SQLite under its own `data/` directory. That is acceptable for an
inspectable portable folder, but an installed build must move user data outside the installation
directory before the installer gate.

## User-Data Override

Set `NL_DATA_DIR` to keep the SQLite database, self-build state, and self-build log outside the
installation folder:

```powershell
$env:NL_DATA_DIR = "K:\AI\nl-coding-agent-user-data"
python\python.exe nl_agent.py doctor
```

The database is `<NL_DATA_DIR>\nl_coding_agent.sqlite3`; `selfbuild_state.json` is written beside
it, and `selfbuild.log` is written under `<NL_DATA_DIR>\..\logs`. When `NL_DATA_DIR` is unset,
the development default remains `<application root>\data`. The current launchers do not set the
variable yet, and existing data is not migrated automatically.

## Next Steps

1. Add a portable launcher or installer option that sets `NL_DATA_DIR` by default and define the
   migration policy for existing development data.
2. Run the full acceptance flow from the staged payload: agent execution, source editing, test
   execution, persistence, and restart recovery.
3. Evaluate a clean runtime rather than copying the entire development `python/` tree.
4. Add an installer only after the staged payload passes the acceptance flow.
5. Complete the third-party license and notice audit before distribution.

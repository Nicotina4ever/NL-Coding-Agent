# Distribution Audit and Size-Reduction Plan

Audit date: 2026-10-28

Command:

```powershell
python\python.exe scripts\audit_distribution.py --json
```

The audit is read-only. It skipped symlinks, excluded `.git` metadata from the measured
working tree, and limited duplicate hashing to files at or below 5 MiB. It reported zero walk
errors and zero large files skipped by the duplicate pass. No files were deleted, moved, or
modified during the audit.

## Measured totals

| Metric | Bytes | Human-readable |
|---|---:|---:|
| Total working tree, excluding `.git` | 2,215,430,573 | 2.06 GiB |
| Protected runtime/vendor trees | 2,209,811,571 | 2.06 GiB |
| Generated artifacts and caches outside protected trees | 475,314 | 464.17 KiB |
| Duplicate bytes reclaimable | 270 | 270 B |
| Custom payload after subtracting protected, generated, `data`, and `logs` | 957,814 | 935.37 KiB |

The protected trees account for 99.75% of the measured working tree. The application code,
assets, tests, scripts, and documentation together are under 1 MiB.

## Largest top-level directories

| Directory | Bytes | Share |
|---|---:|---:|
| `python` | 1,720,029,750 | 77.64% |
| `crewAI` | 489,781,821 | 22.11% |
| `data` | 4,071,008 | 0.18% |
| `assets` | 590,775 | 0.03% |
| `nl_coding_agent` | 584,511 | 0.03% |
| `tests` | 148,484 | 0.01% |
| `logs` | 114,866 | 0.01% |
| `docs` | 56,525 | 0.00% |
| `scripts` | 21,428 | 0.00% |
| `.agents` | 7,005 | 0.00% |

## Protected trees

| Tree | Bytes | Human-readable | Classification |
|---|---:|---:|---|
| `python` | 1,720,029,750 | 1.60 GiB | Never touch; disposable runtime |
| `crewAI` | 489,781,821 | 467.09 MiB | Vendor/reference checkout; never rewrite |

`crewAI-tools` is not present in this workspace at audit time.

Runtime import evidence:

```text
python\python.exe -c "import crewai; print(crewai.__file__)"
K:\AI\Coding Agent\python\Lib\site-packages\crewai\__init__.py
```

The runtime imports `crewai` 1.15.32 from the embedded runtime, not from the `crewAI` checkout.
That makes the 467.09 MiB vendor checkout a candidate for exclusion from a portable payload, but
not for deletion or in-place modification.

## Generated artifacts and caches

Generated artifacts outside protected trees total 475,314 bytes (464.17 KiB). Largest entries:

| Path | Bytes |
|---|---:|
| `tests/__pycache__` | 123,588 |
| `nl_coding_agent/gui/widgets/__pycache__` | 78,662 |
| `nl_coding_agent/__pycache__` | 52,629 |
| `nl_coding_agent/agents/__pycache__` | 42,967 |
| `nl_coding_agent/core/__pycache__` | 42,728 |

The remaining generated entries total 134,740 bytes. These files are regenerated automatically
and should be excluded from packaging rather than treated as source.

## Duplicate files

One duplicate group was found:

| SHA-256 prefix | File size | Copies | Reclaimable |
|---|---:|---:|---:|
| `51c132bacc07b186` | 30 B | 10 | 270 B |

The group is ten empty package `__init__.py` files. Deduplicating them would save 270 bytes and
would make package layout less conventional. Recommendation: keep them.

## Declared dependencies

| Dependency | Evidence of use |
|---|---|
| `PySide6` | GUI entry points and widgets under `nl_coding_agent/gui/`. |
| `psutil` | `nl_coding_agent/core/status.py` and mission-lock liveness checks. |
| `crewai` | `nl_coding_agent/main.py`, `nl_coding_agent/cli.py`, and `nl_coding_agent/agents/orchestrator.py`. |
| `PyYAML` | Configuration loading in `nl_coding_agent/main.py`, `cli.py`, and `app/services.py`. |

No declared dependency was found to be unused with high confidence. `kubernetes`, `numpy`, and
other large runtime packages are transitive dependencies inside `python/Lib/site-packages`; they
are not declared directly by this project.

## Size drivers inside the protected runtime

`python/Lib/site-packages` is approximately 1.54 GiB of the 1.60 GiB runtime. Large components
observed inside it include:

| Component | Approximate size |
|---|---:|
| `PySide6` | 647.0 MiB |
| `kubernetes` | 75.4 MiB |
| `numpy` | 31.1 MiB |
| `crewai` | 12.5 MiB |

These measurements are evidence for a future clean-runtime build. They are not authorization to
delete or prune the current runtime in place.

## Cleanup classification

### Safe to ignore or exclude from packaging

- `__pycache__`, `.pytest_cache`, and other generated cache directories.
- `tests/__pycache__` and package-level `__pycache__` directories.
- `.git` metadata and `.git` directories inside checkouts.
- Audit output written outside the application payload, such as `.workspace/logs/distribution_audit.json`.

### Requires user approval

- `data/` contains the SQLite database, mission baselines, and runtime state. It is user data and
  must not be deleted or shipped as a template.
- `.workspace/logs/` contains diagnostics and audit output. Retention and packaging decisions require user
  approval.
- `crewAI/` is a vendor/reference checkout. Excluding it from a portable build is recommended, but
  deleting or rewriting it requires explicit approval.
- `python/` is the disposable embedded runtime. Do not prune it in place. A separate clean runtime
  can be evaluated for a future portable build.

### Never touch

- `python/`, `crewAI/`, and `crewAI-tools/` if present.
- `.git` and user backup archives.
- User models, external projects, and saved data.

## Size-reduction plan

1. Create a staging payload containing only `nl_coding_agent/`, `assets/`, `config/`, launchers,
   `README`/license files, and `pyproject.toml`. Exclude `tests/`, `docs/` source notes, `.git`,
   caches, `data/`, `.workspace/`, and the `crewAI` vendor checkout unless a reference copy is required.
2. Use the installed `crewai` package from the embedded runtime. Pin and record its version, and
   add the required third-party license notices.
3. Keep the embedded `python/` runtime for a one-folder Windows build. Measure a clean runtime
   separately rather than pruning the working runtime.
4. Exclude generated caches and user state from the payload, and create `data/` and `.workspace/` on
   first launch.
5. Validate the staged payload from a clean directory on Windows. Confirm GUI launch, project
   open, Ollama model discovery, and the full test suite in the source workspace.

Excluding the 467.09 MiB `crewAI` checkout would reduce the measured working tree from 2.06 GiB to
approximately 1.61 GiB before any clean-runtime work. That estimate is arithmetic, not a verified
build result.

## Next steps for native CrewAI integration

- Keep the runtime import path check as a regression test: `crewai` must resolve from
  `python/Lib/site-packages`, not the `crewAI` checkout.
- Record the installed `crewai` version and pin it in project metadata.
- Add license notices for `crewai` and its transitive dependencies.
- Remove `crewAI/` only from build staging first; do not delete the vendor checkout without
  explicit approval.
- Re-run the audit and the full suite after any dependency change.

## Next steps for a portable Windows build

- Choose a one-folder layout with the embedded runtime, application package, assets, config, and
  launchers.
- Exclude `.git`, caches, `data/`, `.workspace/`, and the `crewAI` vendor checkout from the payload.
- Add a clean-directory smoke test that launches the GUI, opens a project, and discovers Ollama
  models.
- Verify the build on a clean Windows VM. Hardware-only checks such as ASIO, audio latency, and
  device routing remain pending until explicitly tested.

## Notes

- No files were deleted or moved during the audit.
- The audit measures the working tree; it is not approval to execute the cleanup plan.
- The largest safe packaging reduction is excluding the vendor `crewAI` checkout, subject to user
  approval and a successful clean-runtime test.

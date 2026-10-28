# Stage 6b Portable Release Acceptance - Measured Evidence

**Status:** portable candidate staged and smoke-tested from a managed temp installation path; **release acceptance is PARTIAL** because several acceptance criteria can only be verified manually on hardware/clean machines. Revision 1's release-blocking status portability defect is **fixed and re-verified** (see Revision 2 below).
**Date:** 2026-10-28. Revision 1 measured at HEAD 7dbd40b; Revision 2 measured after the CLI status portability fix (full suite 513 passed; see Revision 2).
**Task:** shared `task-38` (stage 6b release acceptance). Owner: runner-integrator.
**Candidate:** dist/stage6b-portable-candidate-r2 (supersedes the revision-1 dist/stage6b-portable-candidate, retained pending authorization) - built with the repository embedded Python runtime and current sources by scripts/stage_portable.py (stage-6b allowlist).
**Existing stale release:** `dist/portable-release` was **not modified or deleted** (23,639 files / 1,507,677,689 B, payload_manifest.json sha256 `fcec8cc9...8d44`). Replacement/deletion requires the explicit authorization requested in section 8.

**Constraints respected:** no network downloads, no model inference, no autonomous/self-build mission, no Ollama model runs (the `doctor` smoke performs the application own read-only `ollama list` check requested by the acceptance step), no git commit, no destructive changes, live `data/` untouched.

---

## 1. Candidate identity

| Property | Measured value |
|---|---|
| Candidate directory | `dist/stage6b-portable-candidate` |
| Manifest file count / source bytes | **23,682 files / 1,508,402,351 B (1.40 GiB)** |
| On-disk files / bytes (incl. payload_manifest.json) | **23,683 / 1,508,405,002 B** |
| Payload tree sha256 (sorted rel-path + file sha256) | `80e4664618a165d49e7375fc1441a27e1b8416be1eb7206cda8bbe347ffa7b03` |
| payload_manifest.json sha256 | `8b89a2f6a0067f9e5d855a2a298deb77eb92919f1914a837390e1a3f66a8d7b3` |
| Manifest created_at (UTC) | `2026-10-28T17:49:34Z` |
| Embedded runtime copies | 1 (`python/python.exe`) |
| CrewAI package copies | 1 (`python/Lib/site-packages/crewai`) |
| Native extension modules (.pyd) | 222 included; `_ssl`, `_socket`, `_sqlite3`, `shiboken6.Shiboken` verified importable |
| Flows package | `nl_coding_agent/flows` present |
| README | `README.md` present (7,001 B) |

Build command and timing:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python\python.exe scripts\stage_portable.py --output dist\stage6b-portable-candidate --json
# exit 0, 35-59 s on this host, source tree read-only, no network
```

### Stage-6b allowlist (implemented in scripts/stage_portable.py)

| Included | Excluded (fails closed if present at payload top level) |
|---|---|
| `README.md`, `nl_agent.py`, `NL Coding Agent.bat`, `Self-Build Mode.bat`, `doctor.bat`, `status.bat` | `.git`, `.agents`, `AGENTS.md`, `PATCH`, `build`, `crewAI`, `crewAI-tools`, `data`, `dist` (self-nesting), `docs`, `installer`, `logs`, `scripts`, `state`, `temp`, `tests` |
| `nl_coding_agent/` (full current package incl. `flows/`), `python/` (single embedded runtime; no `Scripts`, caches or bytecode), `assets/`, `config/models.yaml`, `pyproject.toml` | `config/voicebridge.yaml` (machine-local external project path), other `config/*`, caches/`__pycache__`/`*.pyc`/`*.pyo` |

The staging script fails closed when: more than one embedded `python.exe` is present; any shipped text file outside the runtime contains the absolute workspace root or the old `K:/AI/Coding Agent` path; an excluded top-level entry would be included. The manifest records these checks: `single_runtime_copy: true`, `absolute_path_hits: []`, `excluded_top_level_present: []`.

A regression found during this task (native `.pyd` extension modules excluded by mistake, breaking `_ssl`/`_socket`/`_sqlite3`/PySide6) was fixed before staging; the test fixture now covers native extension inclusion.

---

## 2. Reproducibility

Two independent staging runs from the same source tree were compared: the dist candidate and a second payload staged directly into the managed temp acceptance directory.

| Field | dist candidate | temp staging | Equal |
|---|---|---|---|
| file_count | 23,682 | 23,682 | yes |
| total_size | 1,508,402,351 | 1,508,402,351 | yes |
| tree_sha256 | `80e4664...7b03` | same | yes |
| included/excluded roots, top_level, payload_checks | identical | identical | yes |

The candidate 99 non-runtime payload files (application source, README, launchers, assets, config, pyproject) are byte-identical to the current working tree/HEAD (0 mismatches, 0 missing). Stage-6a source-release reproducibility (byte-identical zip + manifests) is recorded in `docs/BOOTSTRAPPER.md`.

Reproducibility scope: same host, same embedded runtime bytes, same source tree; the runtime is copied byte-for-byte from `python/`. A clean-checkout/clean-machine rebuild remains manual-pending (section 6).

---

## 3. Acceptance smoke from a non-default installation path

The second payload (identical tree hash) was staged into a managed temp directory outside the repository and executed with the candidate own embedded Python, cwd set to the temp payload, no `PYTHONPATH`, and `NL_DATA_DIR` pointing to a temp data directory:

```text
temp root: %TEMP%/nl-stage6b-acceptance-20261028T185010  (managed, removed after the run)
payload:   <temp>/payload
python:    <temp>/payload/python/python.exe
data:      <temp>/data
```

| Check | Command | Result |
|---|---|---|
| CLI help | `python.exe nl_agent.py --help` | **PASS** exit 0 (command list printed) |
| Doctor | `python.exe nl_agent.py doctor` | **PASS** exit 0; imports CrewAI 1.15.32, read-only `ollama list` OK, configured role models reported OK ("Doctor complete.") |
| Status (default payload invocation) | `python.exe nl_agent.py status` | **FAIL** exit 1: `KeyError: 'project'` in `cli.status()` - the machine-local `config/voicebridge.yaml` is (correctly) not shipped and `status` does not handle its absence (release-blocking finding, section 7) |
| Status with explicit external config | `python.exe nl_agent.py --project-config <temp>/status_config.yaml status` | **PASS** exit 0 (prints "No state created yet"; command works when a config is supplied) |
| Imports incl. flows | `import nl_coding_agent; nl_coding_agent.flows; core.supervisor; agents.orchestrator; gui.main` (cwd payload, sys.path=[payload]) | **PASS** exit 0; all module files resolve **inside the temp payload** |
| GUI offscreen smoke | `QT_QPA_PLATFORM=offscreen` plus `QApplication` and `MainWindow(get_services())` + show + processEvents | **PASS** exit 0; window title "NL Coding Agent" (only a non-fatal Qt font-directory warning) |
| Mission persistence from payload | candidate Python creates project + mission via registry/persistence with `NL_DATA_DIR=temp/data`, then a second process reads it back | **PASS** project_id 1, mission_id 1, title "Stage6b acceptance", status "pending", DB under `<temp>/data` |
| No dev-only files in payload | relocation check + listing | **PASS**: none of tests/ scripts/ installer/ docs/ build/ data/ logs/ AGENTS.md PATCH/ crewAI/ crewAI-tools/ .git .agents present; `config/voicebridge.yaml` absent; `payload_manifest.json` present |
| Single runtime copy | manifest check + on-disk count | **PASS** 1 `python.exe`, 1 `crewai` site-packages copy, 222 `.pyd` included |
| Relocation-safe payload (no absolute workspace paths) | scan all non-runtime text files in the temp payload for current repo root and old `K:/AI/Coding Agent` root | **PASS** 0 hits; staging-time check also 0 hits |
| Payload not mutated by smoke | recursive before/after listing of temp payload | **PASS** same file count/size; 0 `__pycache__`; no `state/` dir created |
| Live repository data untouched | `data/` mtimes before/after; all commands used temp `NL_DATA_DIR` | **PASS** `data/nl_coding_agent.sqlite3` mtime unchanged (2026-10-28 18:36:06) |

### Cleanup record

- Managed temp directory removed after the smoke: **23,689 files / 1,508,650,018 B** removed; `Test-Path` false afterwards; no `nl-stage6b-acceptance-*` leftovers.
- No repo files, `data/`, `logs/`, model files or vendor/runtime trees were modified by the smoke.
- The dist candidate and its payload manifest were kept for Lead review (git-ignored `dist/`).

---

## 4. Targeted tests (this task)

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
python\python.exe -m pytest -q tests\test_stage_portable.py -p no:cacheprovider
# 8 passed (allowlist, exclusions, dry-run, non-empty refusal, default dist output,
#  absolute-path refusal, duplicate-runtime refusal, native .pyd extension inclusion)
```

The full suite is **not run by this task** (constraint); the Lead runs it before committing. The current Lead-reported baseline at the stage-4 close was 397 passing tests; the only test file changed here is `tests/test_stage_portable.py` (targeted 8 passed).

---

## 5. What this evidence supports and does not support

**Supported:** the stage-6b allowlist produces an inspectable one-folder portable payload with one embedded runtime, current sources (incl. flows), README/launchers/assets/models config; the payload is independently reproducible (identical tree sha256 across two stagings); it runs from a non-default installation path in a managed temp directory without importing the repository, persists missions in an external temp SQLite database, constructs the offscreen GUI, and excludes development-only files and absolute workspace paths.

**Not supported / FAIL:** out-of-the-box `status` (and `status.bat`) from a portable payload. **Release acceptance is therefore PARTIAL, not accepted.**

---

## 6. Manual-pending items (cannot be executed in this environment)

1. **Clean Windows machine/VM without a global Python/uv/conda/pip**: install + startup + project + mission exclusively from the candidate. This environment has the development workspace and the embedded runtime; no clean machine is available.
2. **Clipboard screenshot + drag-and-drop attachments end-to-end** (hardware/OS clipboard interaction; real model attachment delivery).
3. **Microphone / local ASR / TTS audio hardware** acceptance (device, permissions, latency).
4. **Real multimodal latency** and real-model interactive GUI acceptance.
5. **Signed installer / published download channel**: the candidate is a staged payload; manifest signing, hosting, network download and update/repair from the network are not exercised here.
6. **Production runtime archive provenance**: the runtime is copied from the repository embedded Python; a clean, reproducible runtime build/signing pipeline is stage-6 follow-up.
7. **Uninstall/user-data preservation and OS integration** (no installer/OS integration in this candidate).
8. **GUI full interaction/mission execution from the installed payload** (only offscreen construction was smoke-tested).
9. Linux/macOS candidate behaviour (schema-level only).
10. Full pytest baseline (Lead-run) and final sign-off.

---

## 7. Release-blocking finding discovered during acceptance

**Portable `status` / `status.bat` fails without machine-local config** (`KeyError: 'project'`). `nl_coding_agent/cli.py::status()` assumes `config/voicebridge.yaml` (which contains an external user path and is intentionally excluded from the payload). README/launchers advertise `status.bat`, so this is an out-of-box portability defect, not a hardware item.

Options for the Lead (a code change is outside this task write scopes):

1. Make `status` config-optional in `cli.py` (print "no project configured" with exit 0 and pointer to `--project-config`) and add a regression test.
2. Remove `status.bat`/status from the shipped payload and README until fixed (less useful).
3. Ship a portable-safe config template (conflicts with the current machine-local-config exclusion policy; not recommended).

**Recommendation: option 1**, as a small follow-up change, then re-run this acceptance step.

---

## 8. Authorization request: stale dist replacement / candidate retention

Current `dist/` inventory (all git-ignored; **no deletion or replacement was performed**):

| Path | Files | Bytes | Identity / status |
|---|---:|---:|---|
| `dist/portable-release` | 23,639 | 1,507,677,689 | **STALE** pre-relocation payload; payload_manifest sha256 `fcec8cc...8d44`; missing current `flows` package; source recorded as `K:/AI/Coding Agent` |
| `dist/stage6a-source-candidate` | 3 | 1,102,563 | stage-6a source-only candidate/evidence (README/manifests/zip), not a runtime payload |
| `dist/stage6b-portable-candidate` | 23,683 | 1,508,405,002 | **this stage-6b candidate**, tree sha256 `80e4664...7b03`; one verified portable candidate (partial acceptance due to status defect) |

Requests to the Lead/user:

1. **Authorize replacement/removal of the stale `dist/portable-release`** after this stage-6b candidate (or its successor after the status fix) passes final acceptance; archive its `payload_manifest.json` and a file inventory as historical evidence before deletion.
2. **Authorize removal of `dist/stage6a-source-candidate`** once its evidence is superseded (recommended), so `dist/` converges to one candidate.
3. **Authorize the small `cli.py` status-portability fix** (outside this task write scopes) or accept the documented limitation; until then the release cannot be called accepted.
4. Keep exactly **one** new stage-6b candidate; this task created only `dist/stage6b-portable-candidate` and did not delete anything.

---

## 9. Honest limitations of this evidence

- Candidate provenance: built from the working tree at `2026-10-28T17:49:34Z`; app payload files match HEAD `7dbd40b` byte-for-byte (99/99 non-runtime files). If the Lead commits the stage-6b script/test changes, re-stage from that commit before publishing.
- Reproducibility is demonstrated on this host/filesystem with the same embedded runtime bytes; it does not prove reproducible runtime builds on a clean machine.
- Staging is a deterministic copy, not an installer; no signing/hosting/notarization.
- The candidate still contains the existing embedded runtime full dependency set (~1.40 GiB); size optimization and license notices are follow-ups.
- The `doctor` smoke ran the application normal read-only `ollama list` check; no inference/model load was performed and cloud/network was not contacted.
- `status` default failure blocks claiming "accepted install"; all other measured smoke gates passed.

---

## Revision 2 - status portability fix and re-verification (2026-10-28)

Revision 1 found one release-blocking portability defect: the default status command raised
KeyError: 'project' because a portable payload intentionally does not ship the machine-local
config/voicebridge.yaml. The defect is fixed in nl_coding_agent/cli.py::status(): without a
configured project it now prints "Project: not configured" plus a pointer to --project-config,
returns exit code 0, and still prints legacy state when a project config is supplied. Two
regression tests were added to tests/test_cli_config.py; the full suite is 513 passed.

The fixed candidate was rebuilt from the same source tree, re-staged into a fresh managed temp
directory, and re-smoked from that non-default path:

| Property | Measured value (revision 2) |
|---|---|
| Candidate directory | dist/stage6b-portable-candidate-r2 |
| Manifest file count / source bytes | **23,682 files / 1,508,403,109 B (1.40 GiB)** |
| Payload tree sha256 | 606462d3f8c0fa5ed69e3bb880d5a48f131652f38c79fb935bc4481f79906dcd |
| payload_manifest.json sha256 | e2620b6f7470f20a84f0e820265bf648764b512f5b81515e8957c9bd1b6dfba0 |
| Reproducibility vs temp staging | file_count, total_size and tree sha256 identical (TREE_EQUAL True) |
| Embedded runtime copies / CrewAI copies | 1 / 1; 222 .pyd modules included |
| Absolute-path hits / excluded top-level present | [] / [] |

Re-smoke from the managed temp payload (NL_DATA_DIR temp, candidate embedded Python, cwd payload, no
PYTHONPATH):

| Check | Result |
|---|---|
| python.exe nl_agent.py status (default, no project config) | **PASS** exit 0: "Project: not configured", config path pointer, "No state created yet..."; no traceback |
| python.exe nl_agent.py --help | **PASS** exit 0 |
| python.exe nl_agent.py doctor | **PASS** exit 0 (CrewAI import, read-only ollama list, role models OK, "Doctor complete.") |
| Imports incl. flows/supervisor/orchestrator/GUI | **PASS** exit 0, all modules resolve inside the payload |
| Offscreen GUI MainWindow(get_services()) from the candidate payload | **PASS** exit 0, window title "NL Coding Agent" (only non-fatal Qt font warning) |
| Payload tree hash equality candidate vs temp staging | **PASS** |
| Temp payload cleanup | removed; no leftovers; no __pycache__ in payload |

Revision-1 (dist/stage6b-portable-candidate, tree 80e4664...) remains on disk only as historical
evidence; retiring it, dist/stage6a-source-candidate and the stale dist/portable-release still
requires the explicit authorization requested in section 8.

---

## Cross-platform private beta extension (NL-BP-152..165, stage-6 extension)

The repository owner extended the release acceptance criteria to a private cross-platform beta for
two trusted testers (Linux and macOS), covering Windows x64/ARM64, Linux x86_64/ARM64 and macOS
Intel/Apple Silicon. The full program plan is docs/CROSS_PLATFORM_PRIVATE_BETA_PROGRAM.md.

| Requirement | Acceptance state |
|---|---|
| NL-BP-152/153/160 | PARTIAL + MANUAL-PENDING: compatibility matrix/platform layer implemented (31 tests); non-Windows wheel/runtime availability and real hardware unverified |
| NL-BP-154/155/158 | PARTIAL + MANUAL-PENDING: six-target manifests/provisioner and measured-only release builder implemented (57 tests); no real native runtime archives or non-Windows candidates exist yet; macOS Universal 2 deliberately not claimed (separate per-arch runtimes) |
| NL-BP-156/165 | PARTIAL + MANUAL-PENDING: CI matrix/headless GUI/bootstrapper checks implemented (7 tests, not executed on GitHub); real CI runs, ARM64 runners, per-platform artifacts and real-hardware evidence absent |
| NL-BP-157 | PARTIAL + MANUAL-PENDING: optional-backend probes/declarations and graceful degradation implemented; no GPU/ASR/TTS backend installed or tested |
| NL-BP-159/161 | NL-BP-161 VERIFIED (31 tests, redacted opt-in diagnostics, issue templates, runbooks); NL-BP-159 beta packages/checksums/instructions still to build |
| NL-BP-162/163 | NL-BP-162 VERIFIED tooling (12 tests, measured snapshot CLEAR-WITH-REVIEW; must re-run before upload); NL-BP-163 owner authorization gates documented but external distribution still requires explicit owner authorization |
| NL-BP-164 | PARTIAL: cross-platform acceptance matrix documented; real-hardware/clean-machine acceptance records still MANUAL-PENDING |

No cross-platform support is claimed until the corresponding CI builds and real-hardware beta tests
pass. Existing Windows acceptance evidence in this document remains valid and unchanged.

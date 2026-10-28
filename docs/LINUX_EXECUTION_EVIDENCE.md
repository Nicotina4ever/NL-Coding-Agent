# Linux execution evidence - stage 6k (WSL2 Ubuntu, fixed code, source-level)

**Status:** REAL re-run of the Linux evidence after the task-58 fixes: the POSIX launcher bad substitution is fixed and generated release/beta manifests are now byte-identical between Windows and Linux. Evidence remains **source-level Linux x86_64 only**. It is **not** GitHub Actions evidence, not native-runtime/installer acceptance, not real-hardware or clean-machine acceptance, and **no platform support is claimed**.
**Captured:** 2026-10-28T19:57:17Z UTC on the existing WSL2 Ubuntu distro (same machine as the Windows side).
**Repository state at capture:** live HEAD bf678ce27e8bef897f808eb4ef586ae65e962764 (short bf678ce). The task-58 fixes were still **uncommitted**, so the deterministic build evidence ran against a clean HEAD clone with the fix files overlaid; the live worktree was dirty from concurrent team work and was used only read-only. The clone and all temporary workspaces were removed after the run.
**What changed since the previous stage-6j evidence:** the Self-Build POSIX launcher bug is fixed; release manifests are written with explicit LF; beta package inventory ordering is made OS-independent; stage payload manifests are written with explicit LF. The previous stage-6j report (EOL-only CRLF/LF manifest difference) is superseded by this document.

**Generated artifacts:** 18 small JSON/Markdown/text reports under `docs/evidence/linux/` (about 51 KB), including the fresh Windows/Linux reports, cross-OS comparisons and the fix manifest.

---

## 1. Fixes covered by this evidence

| Fix | File(s) | Verification |
|---|---|---|
| Bad parameter expansion in the POSIX Self-Build launcher (line 69) | `scripts/launchers/Self-Build Mode.sh` | The malformed expansion became the intended `${NL_SELFBUILD_REVIEWER_MODEL:-}`; all POSIX launchers are scanned for the doubled-brace form, and a new regression test executes every launcher in a synthetic layout. |
| Explicit LF writes for generated release manifests | `scripts/build_release.py` | New `_write_lf()` uses `write_bytes(text.encode("utf-8"))` for release/platform/runtime manifests; Windows and Linux manifests are now byte-identical. |
| Explicit LF write for the portable payload manifest | `scripts/stage_portable.py` | `payload_manifest.json` is written with explicit UTF-8/LF bytes. |
| OS-independent beta package inventory/checksum order | `scripts/build_beta_packages.py` | Checksum/inventory entries are sorted by POSIX relative path, so `beta-manifest.json` and `SHA256SUMS` are byte-identical across Windows and Linux. |
| Regression tests | `tests/test_stage_portable.py`, `tests/test_build_release.py`, `tests/test_build_beta_packages.py` | Launchers executed through Git Bash/POSIX shell; generated files asserted CRLF-free; beta inventory asserted POSIX-sorted. Test helper skips cleanly if no usable shell exists. |

The launcher default was checked against `scripts/launchers/Self-Build Mode.bat` and the other POSIX launchers: `ollama/qwen3.5:9b`, same selfbuild argv, same environment defaults.

---

## 2. Environment (evidence: `environment.json`)

| Item | Measured value |
|---|---|
| Distro | Ubuntu 24.04.4 LTS (Noble Numbat), WSL default local user |
| Kernel | `6.18.54.1-microsoft-standard-WSL2` (WSL2) |
| Architecture | `x86_64` |
| Python | system `python3 3.12.3` at `/usr/bin/python3`; no pip/apt installs, no venv |
| Git | `git version 2.43.0` |
| Live mount | `/mnt/k/AI/NL Coding Agent` |
| Evidence clone | clean HEAD `bf678ce27e8bef897f808eb4ef586ae65e962764` plus the uncommitted task-58 fix overlay (4 source files + 3 test files; hashes in `task_58_fix_manifest.json`) |
| Other tooling | `bash`/`dash`, stdlib only; no GUI stack |

The distro was started only for the commands; Docker was not started, and no WSL configuration or packages were changed.

---

## 3. Cross-OS results (Windows vs Linux, same clean clone + fix overlay)

Both operating systems built the same source release twice with the fixed `scripts.build_release` and both reproducibility runs returned **PASS 40/40**. Comparing the first candidate of each OS:

| Artifact | Windows | Linux | Verdict |
|---|---|---|---|
| source archive sha256 | `93c2bb16a008fcb7d90f0d28f1621a2d2dca616c3b6a09f7e2a68ffd7ed813bd` | same | **byte-identical** |
| source archive size | 1,438,099 bytes | same | **equal** |
| source file list | 340 files | 340 files | **equal** |
| `release-manifest.json` sha256 | `012e8e64688a91ee5c2bce2c3859c032b56f9b4f2d63975cd0fd099c24a35268` | same | **byte-identical, 0 CRLF** |
| `platform-manifest.json` sha256 | `3a8d2077c1ba3267ded942b2d90408a5ea966ad3a0f6b64c5780d6ff7c89c28d` | same | **byte-identical, 0 CRLF** |
| `runtime-manifest.json` sha256 | `747b8f005fc46bbed3cfc7f87c0562576476a56c492079dbab16dd9f90f657ee` | same | **byte-identical, 0 CRLF** |
| beta package (14 files: beta-manifest, SHA256SUMS, installer manifests, INSTALL docs, source zip, ...) | all sha256 | same | **byte-identical** |
| stage payload (107 files) | 106/107 sha256 | same | identical except `payload_manifest.json` |

**Stage payload note:** `payload_manifest.json` intentionally records a `created_at` capture timestamp, so its bytes cannot be identical across two runs; with that field normalized the manifests are identical, and both are LF-only (no CRLF). This is an evidence report, not a release manifest; the release and beta manifests are fully byte-identical.

Raw reports: `reproducibility_windows.json`, `reproducibility_linux.json`, `cross_os_reproducibility.json`, `cross_os_manifest_eol_analysis.txt`, `cross_os_beta_package.json`, `cross_os_stage_payload.json`.

---

## 4. Other Linux runs (all from the fixed clone, all exit 0)

| Command | Exit | Result |
|---|---|---|
| `bash -n` / `sh -n` on all `scripts/launchers/*.sh` and `*.command` (live mount + clone) | 0 | 10 checks, 0 failures (`shell_syntax_linux.json`) |
| synthetic POSIX launcher execution (fake `nl_agent.py` + fake provisioned `python/bin/python3`) | mixed | GUI/doctor/status/**Self-Build** all exit 0 with correct argv; packaged payload without runtime exits 2 fail-closed; payload without `nl_agent.py` exits 2 fail-closed (`launcher_checks_linux.txt`) |
| `python3 scripts/ci/reproducibility_check.py --json --report-dir ...` | 0 | PASS 40/40; two builds byte-identical |
| `python3 scripts/ci/package_smoke.py --json --report-dir ...` | 0 | PASS 6/6; source 340 files/1,438,099 B; beta package 14 files/1,482,756 B; six-target MANUAL-PENDING matrix; native-runtime plan no network/no writes (`package_smoke_linux.json`) |
| `python3 scripts/rehearse_release.py --json --report-dir ...` | 0 | PASS 8/8 synthetic stages, NOT-A-RELEASE notice (`release_rehearsal_linux.json`) |
| `python3 scripts/release_acceptance.py ... matrix ...` | 0 | targets 6, verified 0, partial 0, MANUAL-PENDING 6, invalid 0, `no_ci_hardware_claim=true` (`release_acceptance_matrix_linux.json` / `.md`) |
| `python3 scripts/release_acceptance.py ... verify ...` | 0 | `ok=true`, 0 records, 0 invalid |
| `python3 scripts/fetch_native_runtimes.py --json` | 0 | plan only: `mode=plan, dry_run=true, no_network=true, no_writes=true`; 6 targets; host `linux-x86_64` |
| `python3 scripts/build_beta_packages.py --plan --candidate ... --name linux-wsl-<epoch> --json` | 0 | `status=plan`, 14 planned files, nothing written (`beta_package_plan_linux.json`) |
| Linux beta build from the same candidate | 0 | 14 files; byte-identical to the Windows beta package |

The earlier stage-6j note that a naive `release_acceptance.py matrix --repo-root ...` order and a candidate-less `--plan` fail remains true; the commands above are the corrected invocations.

---

## 5. Repository cleanliness and managed temp cleanup (evidence: `workspace_cleanliness_linux.json`)

- Evidence clone: HEAD `bf678ce` plus the 4-file fix overlay; `git status` showed exactly those 4 modified files before and after the run (no extra tracked changes); `.workspace` files 0 -> 0; `__pycache__` 4 -> 4 (pre-existing from the Windows reproducibility build inside the clone); `build/`, `dist/`, `logs/`, `state/` absent.
- Live mounted worktree: status snapshot byte-identical before and after (88 status lines of concurrent team work, unchanged by this run); no legacy root directories created; live `build/dist/logs/state` all absent.
- Managed cleanup: the temporary evidence directory (clone, candidates, packages) and WSL `/tmp` workspaces were removed; `managed_temp_cleaned=true`, `wsl_temp_cleaned=true`. No commit was made.

---

## 6. Tests run (affected local suites)

```
python -m pytest -q tests/test_build_release.py tests/test_build_beta_packages.py \
  tests/test_stage_portable.py tests/test_platform_support.py tests/test_ci_workflows.py
# 92 passed
```

New coverage includes: POSIX launcher execution (GUI/doctor/status/self-build argv + fail-closed payload, skipped only when no usable shell exists); CRLF-free assertion for release candidates and beta package text files; POSIX-sorted beta inventory/SHA256SUMS; stage payload manifest LF. `shell_syntax_linux.json` records the live shell syntax checks.

---

## 7. Findings and residual limitations

Resolved by task-58:
1. **Self-Build POSIX launcher bad substitution** - fixed; execution now exits 0 with the intended default reviewer model.
2. **CRLF vs LF release manifests** - fixed; release/platform/runtime manifests and all 14 beta package files are byte-identical Windows vs Linux.
3. **OS-dependent beta inventory ordering** - fixed; beta-manifest inventory and SHA256SUMS use POSIX-sorted order on both OSes.

Residual limitations (explicit):
- WSL2 Ubuntu on Windows 11 is **not** GitHub Actions and does not exercise hosted-runner behaviour.
- Source-level evidence only: system `python3` has no `PySide6`/GUI and no `crewai`/agents; no models/network/Ollama; no GPU/CUDA/ROCm, ASR/TTS, clipboard or DPI checks.
- No native runtime archives were downloaded, measured or installed; no installer/clean-machine/real-hardware acceptance.
- The stage payload `payload_manifest.json` keeps an intentional `created_at` timestamp; it is LF-only and identical modulo that timestamp, but is not claimed byte-identical.
- The evidence clone carries the uncommitted task-58 fix overlay (hashes recorded); base HEAD remains `bf678ce`.
- No platform support or beta acceptance is claimed; no commit.

---

## 8. Evidence file index (`docs/evidence/linux/`, 18 files, ~51 KB)

| File | Content |
|---|---|
| `environment.json` | distro/kernel/arch/python/git/mount/HEAD/fix overlay |
| `task_58_fix_manifest.json` | sha256/size of the uncommitted fixed files |
| `reproducibility_windows.json` / `reproducibility_linux.json` | full 40-check reports for each OS |
| `cross_os_reproducibility.json` | archive/manifest/beta equality summary |
| `cross_os_manifest_eol_analysis.txt` | exact byte/CRLF analysis of the release manifests |
| `cross_os_beta_package.json` | 14-file beta package hash comparison |
| `cross_os_stage_payload.json` | 107-file stage payload comparison and timestamp note |
| `package_smoke_linux.json` | package-smoke PASS report and facts |
| `release_rehearsal_linux.json` | synthetic 8-stage rehearsal PASS summary |
| `release_acceptance_matrix_linux.json` / `.md` | six-target acceptance matrix (all MANUAL-PENDING) |
| `fetch_native_runtimes_plan_linux.json` | dry-run acquisition plan (no network/writes) |
| `beta_package_plan_linux.json` | beta package plan (unique name, file list) |
| `shell_syntax_linux.json` | per-launcher `bash -n`/`sh -n` results (10 checks, 0 failures) |
| `launcher_checks_linux.txt` | synthetic root-resolution/fail-closed execution checks |
| `live_worktree_status_at_capture.txt` | live worktree snapshot (concurrent edits) |
| `workspace_cleanliness_linux.json` | clone/live cleanliness and temp cleanup |

## 9. Regeneration notes

The Linux suite is reproducible from a clean clone of the pinned HEAD with the fix overlay applied and the system `python3`:

```bash
# clean clone of HEAD bf678ce + task-58 fix overlay
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 NO_COLOR=1
export NL_WORKSPACE_DIR=$(mktemp -d)
python3 scripts/ci/reproducibility_check.py --json --report-dir reports
python3 scripts/ci/package_smoke.py --json --report-dir reports
python3 scripts/rehearse_release.py --json --report-dir reports
python3 scripts/release_acceptance.py --repo-root "$PWD" matrix \
  --records-dir "$(mktemp -d)" --json-out reports/matrix.json --markdown-out reports/matrix.md --json
python3 scripts/fetch_native_runtimes.py --json
python3 scripts/build_beta_packages.py --plan --candidate <built-candidate> \
  --source "$PWD" --output-parent "$(mktemp -d)" --name "linux-wsl-<unique>" --json
```

The Windows side of the comparison is the same fixed `scripts/ci/reproducibility_check.py` and `build_release.py` run on Windows against the same clean clone and fix overlay.

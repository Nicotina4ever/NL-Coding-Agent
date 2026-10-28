# Release-Pipeline Rehearsal (Stage 6h)

**Status:** implemented and tested. This is an explicitly **synthetic rehearsal**, not a
release, not an acceptance claim and not platform-support evidence.

**Task:** shared `task-54`. Script: `scripts/rehearse_release.py`.
Tests: `tests/test_release_rehearsal.py`.

## 1. What it is

A fully local, managed-temp end-to-end run of the stage-6 pipeline wiring using
**synthetic marker-only runtime archives** and one **synthetic acceptance record fixture**.
It exists so integration bugs between the fetch/measure, release-builder, beta-package,
provisioner and acceptance-matrix steps are found now, before real native runtimes exist.

It never downloads, never runs a model, never uploads/publishes and never writes to tracked
evidence directories.

## 2. Stages

| # | Stage | What is exercised |
|---|---|---|
| 1 | `synthetic_runtime_fixtures` | Creates six temp runtime fixtures named like the declarative sources: zip for Windows targets, tar.gz for Linux/macOS targets; each has distinct marker content and a valid launcher member (python.exe / bin/python3). No real runtime content. |
| 2 | `fetch_native_runtimes_offline_measure` | Runs `scripts.fetch_native_runtimes` with `--offline-dir` + `--write` into temp outputs; six offline measurements, schema-valid measured draft, evidence report. |
| 3 | `measured_draft_validation` | Validates the six-target draft with `installer.runtime_manifest`: release_ready only at 6/6 and hashes/sizes equal the measurements. |
| 4 | `native_candidate_build` | Builds a source release candidate with `scripts.build_release`, passing every synthetic archive as `--runtime-archive TARGET=PATH` into temp output. |
| 5 | `native_candidate_manifest_validation` | Validates generated runtime/platform manifests: six targets, release_ready true, measured (non-optional) runtime components, archive hashes/sizes match the bundled synthetic archives. |
| 6 | `beta_package_build` | Builds the deterministic beta package from that candidate via `scripts.build_beta_packages`; checks six-target beta manifest entries are still explicitly unmeasured. |
| 7 | `offline_provision_install_verify` | For each target uses `installer.provision` against the candidate as an offline bundle: install + verify into temp targets with a shared content-addressed cache; checks the synthetic launcher exists and cache holds six artifacts. |
| 8 | `release_acceptance_matrix_synthetic_record` | Writes one clearly synthetic record fixture into a **temporary** records directory (never committed), runs the `scripts.release_acceptance` matrix and checks six targets, zero verified, no CI hardware claim, one valid record for windows-x86_64 in MANUAL-PENDING. |

## 3. Usage

```powershell
# Full rehearsal, JSON printed and JSON+Markdown reports written to a temp/CI dir.
python\python.exe scripts\rehearse_release.py --json --report-dir .workspace\build\rehearsal-reports

# Human-readable summary (no report files).
python\python.exe scripts\rehearse_release.py
```

Exit codes: `0` PASS, `1` FAIL (failing stage and evidence are included).
The temp workspace is always removed, including on failure; the report directory is the only
persisted output.

## 4. Report

`release_rehearsal.json` contains:

- `synthetic_rehearsal: true` and the explicit `NOT A RELEASE` / no-platform-support notice;
- overall `status` (PASS/FAIL) and per-stage `status` + redacted detail;
- measured facts: six synthetic targets, fixture names/hashes, six measured draft hashes,
  native-candidate counts and manifest flags, beta-package counts, provisioning/verification
  results per target, acceptance matrix summary, canonical-manifest-unchanged flag and
  workspace-cleaned flag;
- `failures` with stage evidence on failure.

`release_rehearsal.md` is a readable table/report of the same information.
Temporary absolute paths are redacted; the report contains no real-run timestamps.

## 5. What this proves

- The fetch tool can measure local six-target archives in offline mode and emit a measured
  runtime-manifest draft which the schema accepts as release_ready at 6/6.
- `build_release.py` can consume per-target runtime archives and emit a
  native-candidate-shaped release with valid runtime/platform manifests and matching hashes.
- The beta package builder consumes that candidate and still keeps runtime components
  unmeasured/not bundled in the beta package.
- `installer.provision` can offline-install and verify the measured runtime for all six
  targets with cache isolation and no repository runtime reuse.
- The release-acceptance matrix accepts one synthetic temp record without making any CI or
  hardware-support claim.
- The pipeline can run with no network/model/upload and without touching canonical manifests.

## 6. What this does NOT prove

- It does not use real Python standalone runtimes; the archives are marker-only fixtures, so
  measured hashes are synthetic and **must never be published or reused as real hashes**.
- It does not prove that real six-target runtime artifacts exist, download, measure, run or
  match upstream providers.
- It is not a clean-machine, Windows ARM64, Linux ARM64, macOS Intel/Apple Silicon, GPU,
  ASR/TTS, GUI or hardware acceptance test.
- It does not replace the real tester records or `docs/RELEASE_ACCEPTANCE.md`; the
  acceptance record generated here is synthetic, temporary and explicitly not a tester result.
- It is not a release, signing, notarization, publishing or platform-support claim.

## 7. Safety and cleanup guarantees

- Managed temp workspace (system temp), always cleaned; canonical manifests
  (`installer/runtime_manifest.json`, `installer/platform_manifest.json`,
  `installer/runtime_sources.json`) are hashed before/after and a change is a FAIL.
- No writes outside the temp workspace except `--report-dir`.
- No network, model, Ollama, upload/publish or package-manager action; static guards in the tests
  enforce this.
- Synthetic acceptance record lives only in the temp records dir and is never committed.
- A corrupt synthetic archive produces a FAIL report with the failing stage and nonzero exit.

## 8. Relationship to the real pipeline

Run this rehearsal after changes to the packaging/acceptance chain, then follow the real
pipeline: acquire/measure real archives (`scripts/fetch_native_runtimes.py`), build a real
native candidate, produce beta packages, provision on real hosts, and collect real tester
records. Only then can release acceptance be discussed.

## 9. MANUAL-PENDING (unchanged by this task)

- Real six-target runtime archives and their measured hashes.
- Clean-machine and real-hardware acceptance, including GPU/ASR/TTS/audio/dpi.
- Signed/published distribution channel.
- Full pytest baseline and Lead/reviewer sign-off.

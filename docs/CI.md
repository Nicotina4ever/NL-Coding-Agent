# GitHub Actions CI (cross-platform beta)

The CI workflow is `.github/workflows/ci.yml`. It verifies a **private beta regression
matrix**, not a full platform-support claim. GitHub-hosted ARM64 runners are public
preview; those jobs are marked non-blocking (continue-on-error) and documented below.

## Matrix

| Name | Runner | Arch | Blocking | Notes |
|---|---|---|---|---|
| windows-x64 | windows-latest | x64 | yes | primary Windows job |
| windows-arm64 | windows-11-arm | arm64 | no (public preview) | if the hosted label is unavailable the documented alternative is a self-hosted Windows ARM64 runner or Windows 11 ARM64 VM; still MANUAL-PENDING |
| ubuntu-x64 | ubuntu-latest | x86_64 | yes | primary Linux job |
| ubuntu-arm64 | ubuntu-24.04-arm | aarch64 | no (public preview) | alternative: self-hosted ARM64 Linux runner or QEMU emulation (slower, not implemented here) |
| macos-arm64 | macos-14 | arm64 | yes | Apple Silicon hosted runner |
| macos-intel-x64 | macos-13 | x86_64 | yes | Intel hosted runner while available |

Each job uses Python 3.12 and runs:

1. **Unit tests** (pytest, GUI smoke/panels excluded, JUnit report).
2. **Integration tests** (bootstrapper, staged-candidate orchestrator, supervisor Flow,
   Flow persistence/resume, JUnit report).
3. **Headless GUI smoke** with QT_QPA_PLATFORM=offscreen
   (scripts/ci/headless_gui_smoke.py): constructs the real MainWindow offscreen, checks
   the page/tab structure and read-only IDE surfaces, and never calls a model.
4. **Bootstrapper checks** (scripts/ci/bootstrap_check.py): read-only template plan plus a
   fully local offline bundle with a fake app archive. It exercises the existing installer
   CLI contract (plan/install/verify) with no downloads and no publishing.
5. **Report checksums** (scripts/ci/checksums.py) and upload of reports only.

CI dependency installation (pip install pytest -e .) uses the package index to prepare the
runner. The application/bootstrapper checks themselves perform no network downloads.

## What CI verifies

- YAML/matrix structure and the static CI guards in tests/test_ci_workflows.py.
- Unit and integration tests on the matrix that is actually available.
- Headless GUI construction and core Studio IDE structure on each runner.
- The installer CLI contract with local fake artifacts (read-only plan, install, verify).
- Report provenance: JUnit reports, smoke JSON, bootstrap JSON and SHA256SUMS.
- Safety guards: permissions contents read, no secrets, no push/publish/release/
  visibility/collaborator actions, artifacts limited to reports/.
- The packaging/acceptance smoke: source candidate -> beta package -> acceptance matrix
  -> native-runtime dry-run plan, with checksum/manifest and six-target honesty invariants.
- The reproducible source-release check on ubuntu-latest, windows-latest and macos-14:
  two builds of the committed tree compared byte-for-byte (archive sha256/size/file list
  and release/platform/runtime manifests), internal consistency, schema validity, forbidden
  content (no workspace/git/data/runtime/vendor/dev artifacts) and a PASS/FAIL report.


## Package smoke job (ubuntu-latest)

A separate blocking `package-smoke` job runs `scripts/ci/package_smoke.py` on
`ubuntu-latest` with Python 3.12. It uses a managed temporary workspace (removed at
the end), performs **no network request, no model call and no upload/publish action**,
and verifies the packaging/acceptance chain end to end:

1. builds a source release candidate with the `scripts.build_release` functions
   (temporary output; committed tree only);
2. builds a deterministic private-beta package with `scripts.build_beta_packages`
   from that candidate (temporary output; overwrite refusal preserved);
3. runs the `scripts.release_acceptance` matrix against a temporary empty records
   directory and enforces six targets, all `MANUAL-PENDING`, zero verified targets,
   zero invalid records and `no_ci_hardware_claim`;
4. runs `scripts.fetch_native_runtimes --dry-run` and enforces plan-only mode,
   six targets, `no_network=true` and `no_writes=true`;
5. validates the beta `SHA256SUMS`, beta manifest inventory, six-target unmeasured
   runtime declarations, installer/runtime manifest templates, and the absence of
   runtime/vendor/user data in the package.

The job emits a JSON PASS/FAIL report (`package_smoke.json`), uploads reports only
(3-day retention) and is blocking on the Linux runner. It is regression/evidence
tooling for this private beta, not a platform-support or release-acceptance claim.

## Reproducibility job (ubuntu-latest, windows-latest, macos-14)

A separate blocking `reproducibility` job runs `scripts/ci/reproducibility_check.py` on
ubuntu-latest (x86_64), windows-latest (x64) and macos-14 (Apple Silicon) with Python 3.12.
It builds the reproducible source release **twice** from the committed tree with the existing
`scripts.build_release` contract in a **managed temporary workspace** (removed at the end;
no writes to the repository) and compares:

1. source archive sha256, size, member count/list;
2. `release-manifest.json`, `platform-manifest.json` and `runtime-manifest.json`
   byte-for-byte;
3. internal consistency: manifest archive/component digests match the real zip, zip members
   match the release file list, and the runtime manifest validates with six targets and
   explicit unmeasured placeholders;
4. forbidden content: no `.workspace/`, `.git/`, `data/`, `python/`, vendor checkouts,
   `da_eliminare/`, caches, databases, bytecode, dev scripts/patches or other development
   artifacts in the candidate or in the source archive.

The job emits `reports/reproducibility_check.json` + `.md` (reports only), uploads them with
**3-day retention**, and is blocking on all three runners. It performs no network request,
no model call and no publishing/upload action, and it exits 1 on any mismatch.

**What this proves vs MANUAL-PENDING:** once the workflow runs externally, a PASS is evidence
that deterministic source-only builds hold on that runner and are byte-identical across the
three operating systems for the same committed tree. It does **not** prove platform support,
native runtime availability/measurement, installer/clean-machine acceptance, GUI interaction
or hardware behaviour: those stay MANUAL-PENDING (see the compatibility matrix and beta
testing guide). Until the job has actually run on GitHub, even its cross-OS evidence is
external/manual; the local run proves determinism on the current host only.

## MANUAL-PENDING (not verified by CI)

- **Real release artifacts / downloads / installers**: CI uses fake local artifacts only;
  real offline bundles, code signing, notarization, download mirrors and hashes are
  release-pipeline/human steps.
- **Windows ARM64 and Ubuntu ARM64 hosted runners**: public-preview availability and
  behaviour are non-blocking; a green/amber run does not prove native ARM64 support.
- **Real models, Ollama, cloud APIs**: never contacted by CI; model quality, cloud grants,
  latency and memory behaviour are manual.
- **Hardware**: audio/microphone, ASR/TTS, GPU/VRAM pressure and high-DPI behaviour are
  manual on the reference machine.
- **Interactive GUI/accessibility**: CI constructs offscreen and checks structure; real
  keyboard navigation, screen readers, DPI scaling and visual identity are manual.
- **Publishing/visibility/collaborators**: no workflow performs these actions.
- **Package smoke is not a real artifact acceptance**: it builds source/beta packages from the
  committed tree with local tooling only; no native six-target runtimes are downloaded or
  measured, and a PASS is CI regression evidence, not clean-machine/hardware acceptance.
- **Full platform support**: a green matrix is regression evidence for this private beta,
  not an acceptance claim for every OS/architecture combination.
- **Cross-OS reproducibility evidence**: the `reproducibility` job's cross-platform evidence
  exists only after it runs on GitHub; a local PASS proves determinism on the current host.
  Byte-identical source builds do not prove that native runtimes/installers work anywhere.

## Artifacts, provenance and retention

Only reports/ is uploaded. The matrix jobs keep reports for 7 days (pytest-unit.xml,
pytest-integration.xml, headless_gui_smoke.json, bootstrap_check.json, SHA256SUMS); the
package-smoke job uploads package_smoke.json and SHA256SUMS, and each reproducibility runner
uploads reproducibility_check.json/.md and SHA256SUMS, all with 3-day retention. No databases, user data,
embedded runtimes, model files or checkpoints are uploaded. SHA256SUMS is generated over
the report files only and is the provenance index for the run. CI does not publish, tag,
release, change repository visibility or manage collaborators.

## Failure handling

A blocking job failure is a regression signal. An experimental ARM64 job failure is recorded
in its run but does not block the matrix; it must be treated as MANUAL-PENDING evidence, not
as a pass. The Lead reviews the matrix result before any beta acceptance claim.

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
- **Full platform support**: a green matrix is regression evidence for this private beta,
  not an acceptance claim for every OS/architecture combination.

## Artifacts, provenance and retention

Only reports/ is uploaded (7-day retention): pytest-unit.xml, pytest-integration.xml,
headless_gui_smoke.json, bootstrap_check.json and SHA256SUMS. No databases, user data,
embedded runtimes, model files or checkpoints are uploaded. SHA256SUMS is generated over
the report files only and is the provenance index for the run. CI does not publish, tag,
release, change repository visibility or manage collaborators.

## Failure handling

A blocking job failure is a regression signal. An experimental ARM64 job failure is recorded
in its run but does not block the matrix; it must be treated as MANUAL-PENDING evidence, not
as a pass. The Lead reviews the matrix result before any beta acceptance claim.

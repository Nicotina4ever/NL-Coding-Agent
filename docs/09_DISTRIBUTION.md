# Distribution & Optimization Goal

## Status

**Phase 3 staged; clean-directory validation active.** The priority gate is met: mission #30
completed an autonomous cycle, mission #24 and #16 provide recovery evidence, and
`scripts/verify_handoff_and_resume.py` verifies the launcher, SQLite records, state, locks, and
full suite. Mission #36 completed the read-only repository audit and size-reduction plan
(`docs/DISTRIBUTION_AUDIT.md`); mission #37 completed native CrewAI runtime integration
(`docs/CREWAI_RUNTIME.md`); mission #38 completed portable payload staging
(`docs/PORTABLE_BUILD.md`) with reviewer approval; mission #39 added the `NL_DATA_DIR` override
for the SQLite database and self-build state. A new canonical release candidate is staged at
`.workspace\dist\portable-release`; launcher default data-directory wiring, data migration, installer work,
and the full acceptance flow remain open.

The canonical staging plan is measured at 23,638 source files and 1,507,676,008 bytes (1.40 GiB)
after excluding `python\Scripts`, the machine-local `config/voicebridge.yaml`, `.workspace\`,
and runtime caches. The release candidate was copied to a managed temporary directory and
verified outside the source tree with `NL_DATA_DIR` outside the payload: `doctor` exited 0,
CrewAI and Ollama were detected, the offscreen GUI constructed six pages, a project opened, and
the project persisted across a second process. The staged payload itself contains no caches,
SQLite data, `python\Scripts`, or private voicebridge config. The older sibling payloads are
superseded and remain audit-only until the user approves deletion. The installer, licensing, and
full agent-execution acceptance tests remain deferred. Implement this goal through NL Coding
Agent's Self-Build Mode where practical, not by ad-hoc manual changes.

## Stage 6a - Bootstrapper and reproducible release foundation (implemented 2026-10-28)

A first, tested distribution foundation now exists (see `docs/BOOTSTRAPPER.md`):

- `installer/`: per-user, manifest-driven bootstrapper CLI (`plan` is the default dry-run mode; `install`/`update`/`repair`/`verify`; cache list/verify/prune/clear; offline-bundle mode). Downloads use urllib with streaming sha256+size verification and atomic publish; installs are isolated copies into a user-selected target while sharing a content-addressed cache. It never installs system-wide and never needs a global Python/pip/uv/conda.
- `scripts/build_release.py`: reproducible source-only release candidate from git-tracked files (deterministic zip with fixed metadata, `release-manifest.json` and installer-compatible `platform-manifest.json`). Two builds from identical inputs are byte-identical (measured: zip sha256 `55ea8674...eaa06`, 1,053,218 B). It writes only a NEW candidate directory and never copies `python/` or `crewAI/` by default.
- 40 targeted tests (fake/local artifacts, no network) and measured local offline install/verify evidence are documented in `docs/BOOTSTRAPPER.md`.

Still manual-pending: clean Windows machine acceptance, a published/signed download channel, a bundled clean runtime archive, code signing/uninstaller, user-data migration/`NL_DATA_DIR` launcher wiring, and license notices in the payload. The existing stale `.workspace\dist\portable-release` was left untouched; the measured source-only smoke candidate `.workspace/dist/stage6a-source-candidate` (zip 1,053,218 B + manifests, no runtime) is retained for Lead review only and is not a verified full release candidate.

## Priority gate

Start only when all of the following are true:

- [x] NL Coding Agent can select the next roadmap mission without manual OpenCode/Antigravity help.
- [x] A complete mission can modify source, run tests, pass review, and persist its result.
- [x] An interrupted mission can be resumed from SQLite without losing its task/diff state.
- [x] The dedicated Self-Build Mode launcher and exact resume command are documented and verified.

## 1. Repository audit and optimization

Inspect the entire project and report:

- redundant or obsolete source files;
- unnecessary copies of libraries and runtimes;
- unused packages and development-only dependencies;
- temporary files, logs, caches, and generated artifacts;
- duplicate or unused vendor source repositories;
- opportunities to simplify imports, modules, and startup.

Produce a size report and a cleanup plan. Do not delete, relocate, or overwrite files
automatically without verifying ownership, references, and runtime dependencies. Never delete
user data, model checkpoints, external projects, or backup archives.

## 2. Native CrewAI integration

Make CrewAI an application dependency integrated with NL Coding Agent's engine instead of
requiring users to clone CrewAI or configure a development environment.

- Reuse the existing development installation while developing.
- Include the actual required runtime dependencies, including CrewAI.
- Exclude unnecessary upstream development repositories.
- Preserve required third-party licenses and notices.

## 3. Portable Windows distribution

Create a distributable Windows build with:

- an application launcher;
- a self-contained application runtime where practical;
- CrewAI and required Python dependencies;
- PySide6 and all required assets;
- functional Ollama integration;
- SQLite persistence and user-data paths independent of the installation folder;
- clear handling of missing Ollama installations or models;
- diagnostic logs and graceful startup errors.

Prefer an inspectable one-folder portable build initially. Evaluate PyInstaller, Nuitka, or an
equivalent according to actual compatibility, size, and performance. Do not claim packaging
success merely because an EXE was generated.

Staging is implemented in `scripts/stage_portable.py` and documented in
`docs/PORTABLE_BUILD.md`. The default output is `.workspace\dist\portable-release`; a non-empty output is
still refused. A dry run produces 23,638 files and 1,507,676,008 bytes (1.40 GiB) after excluding
`python\Scripts`, `.workspace\`, caches, and the machine-local `config/voicebridge.yaml`.
The staged candidate was copied to a managed temporary directory and passed `doctor`, offscreen
GUI startup, project opening, and restart persistence with `NL_DATA_DIR` outside the payload.
Mission #39 added `NL_DATA_DIR`, so user data can be moved outside the installation; the
launchers do not set it automatically yet and no migration exists. Both launchers now set
`PYTHONDONTWRITEBYTECODE=1` to stop payload runs from regenerating caches. No signed installer or
packaging claim exists yet; the full acceptance flow remains open. Stage 6a (2026-10-28) added the
per-user bootstrapper foundation and the reproducible source release builder (`installer/`,
`scripts/build_release.py`, `docs/BOOTSTRAPPER.md`); clean-machine acceptance and runtime
packaging remain manual-pending.

Build outputs are now governed by the workspace-containment policy: permanent build artifacts
belong under `.workspace\dist\`, temporary build files under `.workspace\build\`, and no new sibling directories under
`K:\AI` are created without explicit approval. Portable independence tests use a managed
temporary directory and record its cleanup. Existing sibling payloads are audit-only until the
user approves deletion.

## 4. Installer and modular dependencies

After validating the portable build, prepare a Windows installer with:

- configurable installation paths;
- clean updates;
- uninstall behavior that preserves user projects and personal data;
- no unnecessary bundled models, duplicate Python installations, or duplicate AI environments;
- optional reuse of an existing Ollama installation and model directory.

Keep the architecture portable enough for future Linux/macOS support, but do not make
cross-platform packaging a prerequisite for the Windows release.

Stage 6a (2026-10-28) implemented the first half of this goal: a per-user bootstrapper foundation
with manifest-driven online/offline install, update, repair, verify and cache management, plus a
reproducible source-only release builder and platform manifests. It is documented in
`docs/BOOTSTRAPPER.md` and covered by 40 targeted tests. The remaining installer work (signed
artifacts, clean runtime bundle, uninstaller/OS integration, clean-Windows acceptance) is still
open.

## 5. Distribution and licensing

Audit licenses for CrewAI, Python dependencies, Qt/PySide6, bundled tools, and optional AI
components. Include applicable third-party notices and licenses. Treat model weights and their
individual licenses separately from the application.

Do not distribute credentials, personal SQLite records, development logs, private projects, or
model checkpoints.

## 6. Acceptance tests

Test the portable build from a clean directory without relying on the original development
workspace or its Python environment. Verify:

- GUI startup;
- project opening;
- model detection;
- agent execution;
- source editing;
- test execution;
- persistence;
- restart recovery.

Record build size, startup behavior, missing dependencies, and reproducible build instructions.

## Final outcome

NL Coding Agent should eventually be downloadable as an ordinary Windows application that runs
its CrewAI-based coding engine with locally installed Ollama models and can safely update and
develop itself.

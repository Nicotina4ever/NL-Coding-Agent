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
`dist\portable-release`; launcher default data-directory wiring, data migration, installer work,
and the full acceptance flow remain open.

The canonical staging plan is measured at 23,638 source files and 1,507,676,008 bytes (1.40 GiB)
after excluding `python\Scripts`, the machine-local `config/voicebridge.yaml`, `dist\`, `build\`,
and runtime caches. The release candidate was copied to a managed temporary directory and
verified outside the source tree with `NL_DATA_DIR` outside the payload: `doctor` exited 0,
CrewAI and Ollama were detected, the offscreen GUI constructed six pages, a project opened, and
the project persisted across a second process. The staged payload itself contains no caches,
SQLite data, `python\Scripts`, or private voicebridge config. The older sibling payloads are
superseded and remain audit-only until the user approves deletion. The installer, licensing, and
full agent-execution acceptance tests remain deferred. Implement this goal through NL Coding
Agent's Self-Build Mode where practical, not by ad-hoc manual changes.

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
`docs/PORTABLE_BUILD.md`. The default output is `dist\portable-release`; a non-empty output is
still refused. A dry run produces 23,638 files and 1,507,676,008 bytes (1.40 GiB) after excluding
`python\Scripts`, `dist\`, `build\`, caches, and the machine-local `config/voicebridge.yaml`.
The staged candidate was copied to a managed temporary directory and passed `doctor`, offscreen
GUI startup, project opening, and restart persistence with `NL_DATA_DIR` outside the payload.
Mission #39 added `NL_DATA_DIR`, so user data can be moved outside the installation; the
launchers do not set it automatically yet and no migration exists. Both launchers now set
`PYTHONDONTWRITEBYTECODE=1` to stop payload runs from regenerating caches. No installer or
packaging claim exists yet; the full acceptance flow remains open.

Build outputs are now governed by the workspace-containment policy: permanent build artifacts
belong under `dist\`, temporary build files under `build\`, and no new sibling directories under
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

# Workspace Migration Readiness

## Decision

- Current canonical root: `K:\AI\Coding Agent`.
- Desired future root: `K:\AI\NL Coding Agent`.
- The workspace is **not** renamed, moved, copied or migrated now.
- Do not create `K:\AI\NL Coding Agent` until the user explicitly authorizes the rename.
- Do not relocate or modify OpenCode sessions or databases.

The actual rename requires OpenCode and every related process to be stopped first. This document
is a checklist and an audit, not authorization to move anything.

## Preconditions for a future authorized rename

- [ ] User explicitly authorizes the rename and the target path.
- [ ] OpenCode, NL Coding Agent, Self-Build Mode, Ollama clients, terminals and build processes are stopped.
- [ ] No mission is running; no `mission.lock` or `selfbuild.lock` remains.
- [ ] A verified SQLite backup exists outside the workspace.
- [ ] The Git worktree is understood: commit or preserve all uncommitted/untracked work.
- [ ] The portable release candidate and `dist/` policy are reviewed; build outputs are not moved by accident.
- [ ] The target directory does not already exist or is empty and approved.
- [ ] The user confirms whether OpenCode configuration/session data must remain untouched.

## Hardcoded absolute paths found

Application runtime code contains no hardcoded `K:\AI` or `C:\Users\Nicola` paths. The absolute
paths are in documentation, launchers/config examples, and persisted state:

| Location | Kind | Migration action |
|---|---|---|
| `AGENTS.md` | Canonical-root documentation | Update after the authorized rename. |
| `README.txt`, `README_FIRST.txt` | Workspace instructions | Update after the authorized rename. |
| `PASTE_THIS_IN_ANTIGRAVITY.txt` | Antigravity workspace instructions | Update or retire after the rename. |
| `START_HERE_ANTIGRAVITY.md` | Bootstrap instructions | Update after the rename. |
| `.agents/rules/python-runtime.md` | Target Python path | Update after the rename. |
| `docs/02_SELF_BUILD_ROADMAP.md` | Self-build project path and examples | Update examples after the rename. |
| `docs/08_ACCEPTANCE_GATES.md` | Launcher path example | Update after the rename. |
| `docs/09_DISTRIBUTION.md` | Portable path examples | Update after the rename. |
| `docs/COMPLETED_MISSIONS.md` | Historical evidence paths | Keep historical paths; add a note if needed. |
| `docs/CURRENT_STATE.md` | Runtime/payload paths | Update current paths after the rename. |
| `docs/PORTABLE_BUILD.md` | Build and smoke-test examples | Update current examples after the rename. |
| `docs/NEXT_SELF_BUILD_MISSION.md` | Mission examples | Replace when the next mission changes. |
| `config/voicebridge.yaml` | Machine-local private project path | Do not package; update locally if the external project moves. |
| `data/nl_coding_agent.sqlite3` | Persisted project roots | Inspect and migrate project `root` values deliberately; do not rewrite blindly. |
| `data/selfbuild_state.json` | Project-root key `K:\AI\Coding Agent` | Rename the state key only with a verified migration. |
| `.bat` launchers | Use `%~dp0`, no absolute root | No change required; verify after the rename. |

## OS-specific code to review before cross-platform work

These are not migration blockers, but they are part of the cross-platform roadmap:

- `nl_coding_agent/tools/shell.py`: Windows command/encoding branch.
- `nl_coding_agent/core/status.py`: Windows-specific status branch.
- `nl_coding_agent/gui/main_window.py`: direct `nvidia-smi` call.
- Root `.bat` launchers: Windows-only entry points; Linux/macOS need equivalent launchers.
- Packaging and installer logic: currently Windows-oriented.

## Post-rename verification (only after explicit authorization)

- [ ] `python\python.exe nl_agent.py doctor` exits 0 from the new root.
- [ ] Recent Projects resolves the new root and no stale absolute path remains.
- [ ] `selfbuild_state.json` matches the new root key.
- [ ] Full test suite passes.
- [ ] Offscreen GUI smoke test passes.
- [ ] Portable staging still excludes `dist/`, `build/`, caches and user data.
- [ ] Ollama and CrewAI imports work.
- [ ] No OpenCode session/database was moved or modified.

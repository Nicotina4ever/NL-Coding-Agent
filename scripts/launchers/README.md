# Launchers

User-facing and development entry points. All launchers resolve the repository root
themselves (a small `%~dp0`-based fallback chain), so they work when double-clicked or
started from any working directory.

## Layout

| Launcher | Purpose | Shipped in portable payload? |
|---|---|---|
| `../../NL Coding Agent.bat` (repository root) | Desktop GUI (PySide6). The **single obvious root launcher** for the application. | Yes, at payload root |
| `doctor.bat` | Environment diagnostics (runtime, CrewAI, Ollama, project state). | Yes, at payload root |
| `status.bat` | Persisted projects/missions/state summary. | Yes, at payload root |
| `Self-Build Mode.bat` | One guarded, bounded self-build mission with persisted state/resume hint. | Yes, at payload root |
| `voicebridge/audit_voicebridge.bat` | Read-only audit of the external NL VoiceBridge Studio project. | No (development-only) |
| `voicebridge/work_voicebridge.bat` | Prepare a task for the external VoiceBridge project. | No (development-only) |

## Portable payload staging

`scripts/stage_portable.py` copies the three CLI launchers above from this directory to the
payload root under their original names (`doctor.bat`, `status.bat`, `Self-Build Mode.bat`),
so the portable user experience keeps the same launch files at the payload root even though the
development sources live here. The same root-resolution logic makes the staged copies find
`python\python.exe` at the payload root.

## Behaviour notes

- Every launcher sets `PYTHONPATH` to the resolved root, UTF-8 I/O, no bytecode writes,
  `NO_COLOR=1`; VoiceBridge launchers additionally set `PYTHONNOUSERSITE=1` and disable pip
  configuration.
- All CLI launchers forward extra arguments (`%*`) after their default command, so
  `doctor.bat --help` / `Self-Build Mode.bat --help` print the CLI help without starting work.
- `voicebridge/work_voicebridge.bat` prompts for a goal and aborts on empty input; it starts a
  real `work` mission when a goal is provided.
- Exit codes from the embedded Python invocation are preserved.

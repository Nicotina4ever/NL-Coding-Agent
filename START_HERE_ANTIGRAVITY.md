# START HERE — Antigravity Bootstrap Mission

You are being used as the **initial external booster** that turns the existing NL Coding Agent
bootstrap into a usable desktop product capable of continuing its own development with local
Ollama agents.

## What already works

On the target machine:
- CrewAI is installed in `K:\AI\Coding Agent\python`.
- `pip check` reports no broken requirements.
- importing `Agent`, `Crew`, `Task`, `Flow`, and `LLM` succeeds.
- Ollama is already installed and contains multiple local models.
- an early `nl_coding_agent` bootstrap may already contain `doctor`, `audit`, `work`, and `status`
  behavior. Inspect it before changing anything.

## Your objective

Implement the roadmap in `docs/02_SELF_BUILD_ROADMAP.md`, beginning with Phase 0 and proceeding
through the first usable GUI milestone without waiting for the user after every small decision.

Use the workspace rules and the custom agents under `.agents/agents/`.

### Mandatory outcome of the boost

The user should be able to launch a Windows desktop application from the workspace root and:

1. See NL-branded UI using the supplied real SVG.
2. Click **Open Project** and choose any folder.
3. Have the app automatically identify language/framework/build metadata and relevant docs.
4. Persist the project in SQLite and show it under Recent Projects.
5. See available Ollama models detected dynamically.
6. Run an Audit on the chosen project.
7. Create a task/mission without creating YAML.
8. See orchestration state, handoffs and logs.
9. Preserve the old CLI entry points or provide backward-compatible replacements.
10. Open `K:\AI\Coding Agent` itself as a project for future self-development.

## Strong implementation preferences

- Python 3.12 embedded at `python\python.exe`.
- PySide6/Qt6 for the desktop shell.
- SQLite from Python stdlib for persistent app/project/task state.
- CrewAI/Flows as orchestration framework where it adds value.
- Ollama HTTP/API/CLI adapter isolated behind an interface.
- No Docker.
- No new Python environment.
- Avoid unnecessary dependencies.
- Do not duplicate model files or large runtimes.

If PySide6 is missing, install it directly into the dedicated embedded Python using:
`python\python.exe -m pip install --no-cache-dir PySide6 psutil`

Do not use the NVIDIA extra PyPI index. The project may set `PIP_CONFIG_FILE=nul` for installs.

## Implementation strategy

Do not attempt the full autonomous coding engine in one giant rewrite.

Build these vertical slices in order:
1. foundation + tests;
2. SQLite project registry + project scanner;
3. Ollama model registry + resource monitor;
4. desktop shell + theme/logo;
5. Open Project / Recent Projects;
6. project overview and audit;
7. task graph UI and persisted mission;
8. operational file/shell/git tools;
9. build/test/debug loop;
10. self-build mode.

At every phase:
- inspect existing code;
- implement;
- run tests;
- review diff;
- update docs/state;
- continue unless blocked by a genuinely external/manual requirement.

## Definition of "autonomous"

Autonomy means the system can progress through ordinary implementation, test, debug and review
cycles without asking the user to approve each trivial step.

It does NOT mean:
- destructive file operations without gates;
- pretending manual/hardware verification happened;
- sending code to cloud models silently;
- allowing two writers to edit the same working tree concurrently.

## End-of-boost handoff

Before finishing this Antigravity boost, create:
- a stable launcher `NL Coding Agent.bat`;
- a working test command;
- `docs/CURRENT_STATE.md` describing what actually works;
- `docs/NEXT_SELF_BUILD_MISSION.md` containing the next mission that the local orchestrator can
  execute on itself.

The local product should then be able to take over incremental development.

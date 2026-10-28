# Self-Build Roadmap

The stages are dependency-driven, not fixed-time sprints.

## Phase 0 — Stabilize the existing bootstrap

Required:
- inspect current `nl_coding_agent`;
- preserve working CLI behavior;
- create/repair a test harness;
- add `.gitignore` that excludes `python/`, vendor repos, logs, runtime state and caches;
- if the workspace root is not a Git repository, initialize Git only after the ignore rules are
  correct;
- record a clean baseline commit.

Do not add large backup copies.

## Phase 1 — Project Registry: eliminate per-project YAML

Implement `Open Project`.

Given a folder:
- normalize/validate path;
- identify Git root if present;
- identify common languages/frameworks;
- detect build metadata;
- locate documentation;
- locate existing agent instruction files;
- identify likely generated/vendor directories;
- create a ProjectProfile;
- persist it to SQLite;
- show it in Recent Projects.

No generated YAML is required from the user.

Detection examples:
- Python: pyproject.toml, requirements*.txt, setup.py
- Rust: Cargo.toml
- JS/TS: package.json, pnpm/yarn/npm locks
- C/C++: CMakeLists.txt, *.sln, *.vcxproj
- .NET: *.sln, *.csproj
- Go: go.mod
- Java: pom.xml, gradle files

The profile is revisable; detection is evidence, not truth.

## Phase 2 — Model Registry and Resource Scheduler

Query Ollama dynamically.

For each model store:
- name;
- local/cloud classification where detectable/configured;
- loaded/unloaded status;
- approximate disk/model size from Ollama output;
- user tags/capabilities;
- preferred roles.

Resource monitor:
- system RAM;
- `ollama ps`;
- NVIDIA VRAM via `nvidia-smi` if available.

Default scheduling:
- one local generation stage at a time;
- unload large local model after stage when advantageous;
- cloud model does not consume local VRAM but remains permission-gated;
- concurrent read-only non-LLM tasks are allowed.

Do not promise exact memory requirements from model file size alone.

## Phase 3 — First GUI

Use PySide6.

Window:
- left rail/sidebar: Projects, Files/Overview, Tasks, Agents, Models, Settings;
- center: project dashboard / task board / diff or editor surface;
- right inspector: Mission / agent activity / selected task details;
- bottom: logs/terminal/event stream;
- status bar: active model, Ollama, VRAM/RAM, project state.

Initial features:
- Open Project;
- Recent Projects;
- Scan/Audit;
- create mission;
- task list;
- agent/model inventory;
- log view;
- settings.

Do not build Monaco integration yet unless the core milestone is already stable.

## Phase 4 — Operational Coding Tools

Add scoped tools:
- read file;
- grep/search;
- create/replace/patch file;
- list tree;
- shell execution;
- Git status/diff;
- optional branch/worktree management.

All tool calls must be scoped to the active project unless explicitly authorized otherwise.

Each write produces an auditable diff.

## Phase 5 — Verification and Debug Loop

Auto-detect candidate verification commands.
Require explicit confirmation once for commands with side effects or unknown risk.

Flow:
`Developer -> Verify -> Debug -> Verify -> Reviewer`

Bound retries by policy and detect repeated failure signatures.
Escalate to Architect when repeated local fixes fail.

"Build passed" and "feature verified" are distinct states.

## Phase 6 — Task Graph and Collision Prevention

Tasks include:
- affected paths;
- dependencies;
- read/write claims;
- agent role;
- model;
- verification gates;
- state.

Writer scheduling rules:
- never allow two tasks with overlapping write scopes in the same working tree;
- tasks with dependencies cannot start early;
- parallelism is opt-in after conflict analysis;
- isolated Git worktrees may later enable safe concurrent writers.

## Phase 7 — Self-Build

Open `K:\AI\Coding Agent` like any other project.

Self-build task requirements:
- baseline tests pass before modification;
- vendor/runtime paths excluded;
- modifications are applied to source, not the running process memory;
- candidate build/tests run in a subprocess;
- GUI offers "Restart to apply" when needed;
- failed candidate remains inspectable and does not erase the last known working revision.

The self-builder updates `docs/CURRENT_STATE.md` and `docs/NEXT_SELF_BUILD_MISSION.md`.

## Phase 8 — Advanced GUI

After orchestration is reliable:
- integrated code viewer/editor;
- structured diff approval;
- dependency graph visualization;
- drag/drop task board;
- agent conversation/handoff viewer;
- project-specific role/model override UI;
- optional Monaco editor via Qt WebEngine;
- theme customization.

## Phase 9 — Smarter routing

Later:
- empirical model scoring per task type;
- benchmark history;
- confidence/escalation policy;
- task-specific context budgeting;
- repo-map/RAG only where it provides measurable value.

Avoid adding RAG merely because it is fashionable.

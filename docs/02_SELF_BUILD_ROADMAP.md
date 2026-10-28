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

Open the repository root (`K:\AI\NL Coding Agent`) like any other project.

Self-build task requirements:
- baseline tests pass before modification;
- vendor/runtime paths excluded;
- modifications are applied to source, not the running process memory;
- candidate build/tests run in a subprocess;
- GUI offers "Restart to apply" when needed;
- failed candidate remains inspectable and does not erase the last known working revision.

- model writes are staged: developer/debugger tools write only a staged workspace;
- the tester runs independent candidate + oracle regression suites in disposable copies;
- promotion is the last gate (recovery point + compare-and-swap + journal) and
  happens only after reviewer APPROVE; blocked/interrupted missions never claim
  staged changes as applied.

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

## Phase 10 - Optimization and Windows distribution

The priority gate is **met**: mission #30 completed an autonomous cycle, mission #24 and #16
provide recovery evidence, and `scripts/verify_handoff_and_resume.py` verifies the launcher,
SQLite records, state, locks, and full suite. Mission #36 completed the **repository audit**
(`docs/DISTRIBUTION_AUDIT.md`); mission #37 completed **native CrewAI runtime integration**
(`docs/CREWAI_RUNTIME.md`); mission #38 completed **portable payload staging**
(`docs/PORTABLE_BUILD.md`); mission #39 added the `NL_DATA_DIR` **user-data override**. A real
payload at `K:\AI\nl-coding-agent-portable-final` passed `doctor`, offscreen GUI startup, project
opening, and restart persistence. Launcher wiring, data migration, clean-directory acceptance,
and the release-candidate audit are the active gates; packaging and distribution implementation
remain deferred.

Deliver, in order:
- [x] repository size/redundancy audit and a safe cleanup plan;
- [x] native CrewAI runtime integration without a required developer checkout;
- [x] portable payload staging script and measured dry-run plan;
- [x] real one-folder payload copy at `K:\AI\nl-coding-agent-portable-final`;
- [x] configurable user-data directory (`NL_DATA_DIR`) with default compatibility;
- [ ] launcher wiring, migration policy, and full clean-directory acceptance flow;
- a Windows installer with clean update/uninstall behavior that preserves user data;
- a third-party license/notice audit and a clean distribution payload;
- acceptance tests from a clean directory, including GUI, project opening, model detection,
  agent execution, source editing, test execution, persistence, and restart recovery.

See `docs/09_DISTRIBUTION.md` for the full requirements and guardrails. Prefer delegating this
work to NL Coding Agent's Self-Build Mode after the priority gate is met.

## Phase 11 - Universal Model Hub and provider adapters

Replace the Ollama-only model view with a provider-agnostic Model Hub. Preserve the existing
Ollama integration as one adapter.

- Discover Ollama, LM Studio, llama.cpp and custom OpenAI-compatible endpoints.
- Run discovery asynchronously with progress, timeouts, refresh and actionable errors.
- Separate model views for LLM/multimodal inference, speech engines, hardware, and storage.
- Never assume provider parameter or tool-calling compatibility.
- Keep provider configuration editable without per-project YAML.

Acceptance: no indefinite loading state; offline and empty states are explicit; provider errors
are visible; the GUI thread remains responsive; tests cover parsing and error paths.

## Phase 12 - Adaptive Inference Controller and Explainable Model Advisor

Select and tune compatible parameters per agent and task, with Automatic, Assisted and Manual
modes. Discover capabilities from providers, but distinguish measured facts from estimates.

- Recommend temperature, sampling, output length, reasoning controls, context budget and
  concurrency where supported.
- Use actual verified mission outcomes, latency, tool-call reliability and resource measurements.
- Persist benchmark and mission performance history in SQLite.
- Explain why a model/configuration was selected, why alternatives were rejected, and the
  tradeoffs and uncertainty.
- Offer a lightweight benchmark when history is insufficient; label recommendations provisional.
- Never change parameters during an active mission without preserving reproducibility and
  recording the transition.
- Respect explicit provider preferences, resource limits and cloud-use restrictions.

## Phase 13 - Optimize My Team

Add a real optimization workflow, not a decorative button.

- Analyze project architecture, technologies, backlog, dependencies and complexity.
- Discover models, hardware, capabilities and verified performance history.
- Recommend an adaptive number of agents justified by independent work and quality risks.
- Propose specialized and temporary roles, model assignments and per-agent parameters.
- Estimate bottlenecks and safe parallel opportunities; explain measured data vs estimates.
- Show current team vs recommended team, changes, benefits and tradeoffs before applying.
- Provide Apply, Customize and Keep Current actions.
- Support optional adaptive reassessment only at safe mission boundaries; never interrupt an
  active task or discard agent context silently.
- Persist team configurations, optimization history and verified metrics in SQLite.

Profiles: Maximum Verified Quality (preferred), Balanced, Maximum Speed, Resource Saving and
Custom. Maximum Verified Quality prioritizes correctness, maintainability, coverage and
requirements satisfaction; it does not mean unlimited agents, reviews or computation.

## Phase 14 - Persistent Goals, Milestones, Tasks and Missions

Add a hierarchical, evidence-driven work management system on top of the existing mission and
task tables.

- Goals: strategic objective, constraints, priorities, acceptance criteria and measurable outcomes.
- Milestones: deliverables with dependencies and verification gates.
- Tasks/TODOs: concrete actions, assignments, dependencies, statuses and expected artifacts.
- Missions: execution attempts, handoffs, diffs, tests, reviews and recovery state.
- Distinguish user-defined goals from agent proposals; preserve user overrides.
- Allow agents to propose and decompose work, select ready tasks and replan from verified results.
- Prevent duplicate tasks, uncontrolled goal expansion, conflicting assignments and infinite
  recursive delegation.
- Verified evidence outweighs agent consensus: tests, builds, diffs, runtime behavior and
  reproducible logs are required before success claims.
- A goal is complete only when its acceptance criteria are verified.

Create the persistent top-level goal: "Complete NL Coding Agent as a professional autonomous,
multimodal, cross-platform AI development environment." Link roadmap items to it without
duplicating entries. The self-build engine must select feasible next tasks, execute them, verify
results and update the hierarchy. Persist everything in SQLite with restart recovery.

## Phase 15 - Speech and Multimodal Input Manager

Add optional, independently installable ASR engines: Qwen3-ASR 0.6B/1.7B, Faster-Whisper,
WhisperX (optional alignment/diarization) and Vosk. Provide a catalog with languages, source,
size, storage, hardware, features and license; resumable downloads, integrity checks,
diagnostics and test transcription. Reuse shared checkpoints and isolate conflicting runtimes.

Separate enable/disable, load/unload, install/switch/uninstall and selective cleanup. Disabling
an engine must not delete its models. Never delete shared or externally managed checkpoints.
Provide a read-only space audit before any confirmed cleanup. Integrate voice into Mission Chat
with review/edit of transcription, language selection and local processing by default. NL Coding
Agent must remain usable with no ASR backend installed.

## Phase 16 - Professional Development Environment

Evolve the PySide6 GUI toward practical IDE capabilities while reusing maintained components and
protocols: code editor with tabs/highlighting/autocomplete, LSP, DAP, integrated terminal, Git and
visual diff with selective approval, project explorer, global search, symbols, test explorer,
problems, execution logs, agent chat, task board, context-aware multi-file editing, indexing and
semantic retrieval, MCP/tools, attachments, persistent history and adaptive teams.

Evaluate Monaco, CodeMirror 6 and other maintained components by integration complexity,
performance, licensing and packaging. Do not promise proprietary Cursor/Codex internals or the
entire VS Code extension ecosystem. Improve hierarchy, typography, responsive/resizable panels,
status visibility, model details, team visualization, task progress, resource/download status,
control consistency and empty/loading/offline/error states. Never block the GUI thread.

## Phase 17 - Cross-platform architecture

Support one codebase on Windows x64, Linux x64 and macOS Apple Silicon (Intel where practical).
Move OS-specific behavior behind adapters: process launching, shells, filesystem paths and
permissions, terminal integration, hardware/resource detection, install/update and inference
backends. Remove hardcoded PowerShell, Windows paths, CUDA and Windows-only executable names from
shared logic. Support CUDA, CPU, llama.cpp/GGUF, Ollama, LM Studio, Apple Metal/MLX and extensible
providers. Detect unified memory and recommend models from measured capabilities. Do not declare
platform support complete until native builds and smoke tests pass on that platform.

## Phase 18 - Zero-friction installation and distribution

Create reproducible platform-specific builds: Windows portable/installer, Linux portable/package
options, macOS signed/notarized bundle when feasible. Bundle the application runtime, CrewAI,
required Python dependencies and GUI components. First-run setup detects inference engines,
reuses model locations, offers approved optional installs, selects cache paths, explains hardware
requirements, runs an end-to-end diagnostic and supports CPU-only operation where practical.
Never silently download large models, use paid services or modify global environments. Maintain
reproducible manifests/lockfiles and build native artifacts on their target OS/architecture.

## Workspace migration — completed 2026-10-28

The workspace was renamed to the canonical root `K:\AI\NL Coding Agent` and the relocation was
verified (see `docs/WORKSPACE_MIGRATION.md` for the completed record, verification evidence and
rollback procedure).

**Historical rationale — SUPERSEDED by the completed relocation above, kept for traceability:**
the original instruction was not to rename, move, copy or migrate the pre-relocation workspace root
while OpenCode and related processes were live, and not to create the new root before explicit user
authorization after all related processes and sessions had stopped; the concern was split project
identity in SQLite, persisted state keys and hardcoded paths. That authorization was given and the
rename was executed with a verified backup, so the prohibition no longer applies.

Do not relocate the repository again, and do not create sibling workspace copies, without a new
explicit user authorization. Do not relocate OpenCode sessions or databases without authorization.

## Expansion priority

1. Preserve and verify the current self-build handoff.
2. Finish the Universal Model Hub and remove the indefinite loading/empty failure mode.
3. Add the Adaptive Inference Controller and Explainable Model Advisor.
4. Add Optimize My Team and persistent Goals/Milestones/Tasks/Missions.
5. Add the optional Speech/ASR Manager and Mission Chat voice input.
6. Add professional editor/LSP/DAP/terminal/Git capabilities and GUI refinements.
7. Add cross-platform adapters and reproducible installation/distribution.

Implement vertical, testable increments through NL Coding Agent's own verified autonomous workflow
where practical. Do not generate large quantities of unused scaffolding or documentation.

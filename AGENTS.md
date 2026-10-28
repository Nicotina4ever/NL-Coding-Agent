# NL Coding Agent — Workspace Rules

## Mission

Build **NL Coding Agent** as a local-first, multi-agent software-development orchestrator.
It must open an arbitrary existing project with one click, understand its documentation and
codebase, build an internal project profile automatically, assign specialized AI agents,
execute build/test/debug loops, preserve state, and allow the product to improve itself.

The product is not a generic chat wrapper and not a clone of Cursor. Its defining capability
is **orchestration**: task decomposition, precise handoffs, resource-aware scheduling,
verification, conflict prevention, persistent state, and controlled self-development.

Read `START_HERE_ANTIGRAVITY.md` before implementing major work.

## Existing environment — preserve it

Workspace root on the user's machine:

`K:\AI\Coding Agent`

Existing paths:
- `python\` — dedicated disposable Python 3.12 embedded runtime. Use this Python. Do not create
  venv/conda/uv environments unless explicitly requested.
- `crewAI\` — vendor/source checkout. Treat as reference/vendor; do not rewrite.
- `crewAI-tools\` — legacy/vendor checkout. Treat as reference/vendor; do not rewrite.
- `nl_coding_agent\` — existing bootstrap application. Refactor incrementally; do not throw away
  working CLI behavior without replacement tests.
- `config\`, `state\`, `logs\` may already exist.

Python validation already succeeded:
- `python\python.exe -m pip check` -> no broken requirements.
- importing `Agent, Crew, Task, Flow, LLM` from `crewai` -> succeeds.

## No configuration ceremony

The normal user must NOT have to create YAML files for every project.
Opening a project folder must trigger automatic discovery and persist the result in SQLite.

YAML/JSON may exist internally for defaults or developer overrides, but the GUI must expose
settings and the application must create/manage them automatically.

## Local-model-first policy

Primary inference provider is the existing Ollama server.

Known available models at project inception include:
- `qwen3.5:9b`
- `muse-glimmer:30b-q4_K_M`
- `qwen2.5-coder:7b-instruct-q4_K_M`
- other local models returned dynamically by `ollama list`
- optional cloud fallback through Ollama, including `gpt-oss:120b-cloud`

Never hard-code the full model list as the source of truth. Query Ollama dynamically.

Cloud models are opt-in escalation only. Do not transmit source code to cloud models unless the
user has enabled cloud escalation for that project/task.

## Resource policy

Target machine:
- Windows 11
- NVIDIA RTX 4060 Ti, 8 GB VRAM
- 32 GB RAM

Start conservatively:
- local LLM stages execute sequentially by default;
- do not keep multiple large Ollama models loaded without a reason;
- after a completed local-model stage, the scheduler may call `ollama stop <model>`;
- inspect `ollama ps`, system RAM, and NVIDIA memory where available;
- read-only analysis tasks may later run concurrently only when they do not create model-memory
  pressure or file conflicts.

The application should choose reliability over raw concurrency.

## Code ownership and safety

Do not edit:
- `python\` runtime internals except installing packages through its `python.exe -m pip`;
- `crewAI\`;
- `crewAI-tools\`;
- user backup archives;
unless the user explicitly asks.

Do not delete repositories, user files, backup archives, model checkpoints, or external caches.

For self-development, use Git diffs/commits as the normal rollback mechanism rather than creating
large duplicate snapshots.

## Product architecture invariant

Keep these concerns separated:
1. GUI / presentation.
2. Project discovery and registry.
3. Orchestration/task graph.
4. Model/provider registry.
5. Resource scheduler.
6. Tool execution and file access.
7. Build/test/debug verification.
8. Persistent state.
9. Self-update/self-build coordination.

The GUI must call stable backend services. Business logic must not live inside widgets.

## Verification invariant

"Code generated" is not "task complete".

A task can be marked complete only when its applicable gates pass:
- requested files exist and parse;
- relevant automated tests/build checks pass;
- reviewer accepts the diff;
- manual/hardware-only checks are explicitly marked as pending when they cannot be automated.

Never claim ASIO, audio latency, browser media synchronization, device routing, or similar
hardware behavior is verified merely because code compiles.

## GUI identity

Use `assets\LogoMio.svg` as the real product logo.
Use `assets\theme.tokens.json` as the initial design-token source.

Brand anchors extracted from the real SVG include:
- electric violet `#7531FE`
- magenta `#E4469B`
- deep purple `#521B8D`
- rose `#BA266C`
- lavender `#AB83C6`
- cyan `#46A3C0`

Dark, modern, professional desktop UI. Cursor-like density is welcome, but do not visually copy it.
No glow on code, transcript text, logs, labels, or body text. Subtle glow is allowed only on the
logo and restrained decorative accents.

## Development behavior

Prefer end-to-end vertical increments over producing large amounts of unused scaffolding.
Inspect existing code before replacing it.
Run tests after meaningful changes.
Keep documentation synchronized with actual behavior.
If architecture docs conflict with working code, investigate and record the decision rather than
silently choosing one.

## First milestone

The first usable desktop milestone must provide:
- launchable GUI;
- Open Project;
- Recent Projects;
- automatic project detection;
- dynamic Ollama model discovery;
- project audit;
- task creation;
- visible agent/task state;
- logs;
- no mandatory per-project YAML;
- preservation of existing CLI capabilities.

Then proceed toward operational coding tools and self-build.

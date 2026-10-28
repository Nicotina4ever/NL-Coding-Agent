# Target Architecture

## Layers

```text
┌──────────────────────────────────────────────────────────────┐
│                      Desktop GUI (PySide6)                  │
│ Project sidebar | Mission | Task graph | Diff | Logs | GPU  │
└──────────────────────────┬───────────────────────────────────┘
                           │ stable application services
┌──────────────────────────▼───────────────────────────────────┐
│                    Application / Use Cases                  │
│ OpenProject | Audit | CreateMission | RunTask | Resume      │
└───────────────┬───────────────┬──────────────┬───────────────┘
                │               │              │
┌───────────────▼──────┐ ┌──────▼──────┐ ┌────▼──────────────┐
│ Project Registry     │ │ Orchestrator │ │ Resource Manager  │
│ scanner + SQLite     │ │ task graph   │ │ Ollama/GPU/RAM    │
└───────────────┬──────┘ └──────┬──────┘ └────┬──────────────┘
                │               │              │
┌───────────────▼───────────────▼──────────────▼──────────────┐
│                         Adapters                             │
│ Ollama | CrewAI | Git | Filesystem | Shell | Build/Test    │
└──────────────────────────────────────────────────────────────┘
```

## Recommended Python package layout

Keep/refactor the existing package toward:

```text
nl_coding_agent/
  __init__.py
  cli.py
  bootstrap.py

  app/
    services.py
    commands.py

  core/
    models.py
    enums.py
    task_graph.py
    policies.py
    events.py

  projects/
    scanner.py
    detectors.py
    registry.py
    documentation.py

  agents/
    profiles.py
    router.py
    handoff.py
    crew_adapter.py

  models/
    ollama_registry.py
    provider_policy.py
    capability_profiles.py

  resources/
    scheduler.py
    memory_monitor.py
    gpu_monitor.py

  tools/
    filesystem.py
    shell.py
    git.py
    verification.py
    tool_policy.py

  persistence/
    database.py
    migrations.py
    repositories.py

  selfbuild/
    coordinator.py
    update_plan.py

  gui/
    main.py
    main_window.py
    controllers/
    widgets/
    dialogs/
    theme.py

  assets/
```

Names can adapt to the existing bootstrap. Preserve good existing code instead of forcing this
tree mechanically.

## Persistent storage

Use SQLite, for example:

`data\nl_coding_agent.sqlite3`

Core tables/entities:
- projects
- project_sessions
- project_facts
- model_inventory
- agent_profiles
- missions
- tasks
- task_dependencies
- task_attempts
- handoffs
- verification_runs
- decisions
- artifacts
- app_settings

Do not store huge source files in SQLite. Store paths, hashes, summaries, decisions and state.

## Event model

Backend should emit structured events:
- PROJECT_OPENED
- PROJECT_SCANNED
- MODEL_DISCOVERED
- MISSION_CREATED
- TASK_QUEUED
- TASK_STARTED
- AGENT_ASSIGNED
- MODEL_LOADING
- MODEL_UNLOADED
- HANDOFF_CREATED
- TOOL_STARTED
- TOOL_FINISHED
- VERIFICATION_PASSED
- VERIFICATION_FAILED
- TASK_BLOCKED
- TASK_COMPLETED

The GUI listens to events rather than inspecting implementation internals.

## Separation from CrewAI

CrewAI is an orchestration engine dependency, not the product architecture.

Wrap it behind an adapter so:
- task/project state remains ours;
- model/resource policies remain ours;
- future replacement or mixed orchestration is possible;
- the GUI never imports CrewAI directly.

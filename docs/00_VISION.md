# Product Vision

NL Coding Agent is a desktop control plane for **local-first agentic software development**.

The user supplies a folder and an objective. The product supplies:
- codebase understanding;
- task decomposition;
- specialized agents;
- precise handoffs;
- resource-aware model scheduling;
- controlled file/command tools;
- compilation and tests;
- debug cycles;
- review gates;
- persistent memory/state;
- resumable development.

## User experience target

The normal path is:

`Launch -> Open Project -> Describe Goal -> Review/Run -> Watch Progress`

Opening a project must not require generating configuration files manually.

The user can later customize everything—roles, models, verification commands, cloud fallback,
permissions—but useful defaults are generated automatically.

## Local-first, not local-only

Local Ollama models are the default workers.
Cloud-backed Ollama models are optional escalation resources and must be clearly identifiable in
the UI.

A task may have a policy such as:
- Local only.
- Ask before cloud escalation.
- Cloud escalation allowed for architecture only.
- Cloud allowed.

## What makes the product different

A single coding agent can edit files. NL Coding Agent must coordinate a **team**:
- understand dependencies;
- prevent task collisions;
- sequence model usage to fit consumer hardware;
- require verification;
- keep durable state across sessions;
- know when work is automated and when human/hardware verification remains.

## Self-build

NL Coding Agent is a valid project target.
It can plan and implement improvements to itself, but:
- current stable behavior must remain testable;
- changes are reviewed through Git;
- application upgrades are applied/reloaded at safe boundaries;
- the self-builder must not rewrite the running process blindly.

# Multi-agent runtime audit and Chat-to-mission path (2026-10-29)

This audit is against the real engine in `K:\AI\NL Coding Agent`, not the design documents. It separates
what is **implemented and used**, what **exists but is not wired**, and what is **missing**, then
describes the single operational path completed end-to-end from the NL Coder Chat controller.

## Active path

```
NL Coder Chat (Mission mode / Chat controller startMission)
  → MCP start_mission (execution approval + bound project)
  → AppServices.run_mission
  → Supervisor.execute_mission (resource lease + checkpoints)
  → SupervisorConfig.pipeline = "sequential" (default)
  → MultiAgentOrchestrator.run_mission
      → _plan_tasks (proportional team policy)
      → _run_planned_analysis (architect/auditor, read-only) → developer
      → _run_tester_stage (deterministic candidate + oracle pytest)
      → _run_reviewer_stage (LLM APPROVE/REJECT)
      → staged promotion
  → persisted tasks/attempts/handoffs/verification/model bindings
  → mission_detail + candidate_diff → NL Coder Chat dashboard
```

Every LLM role goes through the existing `CrewRuntime` seam: `orchestrator._call_model` →
`CrewAIBackend.run_agent` → one `CrewAI Agent + Task + Crew(process=sequential)` per stage. The tester
is deterministic Python verification; promotion and gates are deterministic. No second Crew, Flow,
Supervisor or model runtime was added.

## Implemented and used

| Capability | Reality |
|---|---|
| CrewAI runtime | One-agent Crew per LLM stage (`developer`, `architect`/`auditor`, debugger repairs, `reviewer`). Real `CrewAIBackend`, not the fake runtime. |
| Role catalog | Reviewed `AgentSpec` policy in `agents/specs.py`; developer/debugger/reviewer/tester/architect/auditor resolve through it. |
| Supervisor | Real `Supervisor` with resource lease, heartbeat, cooperative checkpoints and terminal finalizers. MCP/Chat dispatch to it. |
| Mission persistence | `tasks`, `task_attempts`, `handoffs`, `verification_runs`, baseline JSON, `resume_count`; resume skips completed work and reuses persisted architect notes. |
| Handoffs | `architect|auditor → developer`, `developer → tester`, `debugger → tester`, `tester → reviewer`, `reviewer → orchestrator` carry real work payloads. |
| Independent verification | Deterministic candidate and oracle pytest suites in disposable copies; both must pass before review/promotion. |
| Model assignment | `ModelRouter` bindings are resolved for architect/developer/reviewer/debugger; snapshots persist in `mission_model_snapshots`. Exact caller routes still execute (no silent substitution). |
| Per-attempt evidence | `task_attempts.metadata_json` records model, provider, duration, bound tools and CrewAI token usage when reported. Reviewer/developer/architect attempts included. |
| Proportional team | Single-file mission: developer/tester/reviewer. Multi-file or design objective: read-only architect + developer/tester/reviewer. Security/audit objective: read-only auditor (and architect when also multi-file) + developer/tester/reviewer. |
| Chat visibility | Mission detail shows tasks/agents, ModelRouter assignments, handoffs, attempts with model/duration/tokens, candidate+oracle verification and the retained diff. |

## Exists but is not wired in the Chat/extension path

| Item | Status / reason |
|---|---|
| CrewAI Flows (`MissionFlow`, `SupervisorRunFlow`) | Implemented and tested, but `SupervisorConfig.pipeline` defaults to `sequential`; no GUI, MCP or Chat writer sets `flow`. Flow mode calls the same orchestrator stage methods and now the same analysis helper. It is a single-node Flow (`@start` + Python loop), not a `@listen`/`@router` graph. |
| Multi-agent Crew (`run_crew`, `build_crew`, `CrewSpec`) | Implemented and tested; production uses one-agent crews. Memory/hierarchical/delegation policy is validated but never enabled in production. |
| `planner` role | Catalogued only; no mission task/stage/handoff. |
| Flow events/approval providers | Test-only. |
| Flow repair/waiting-approval branches | Not reachable in the current executor wiring. |
| `architect_model`/`auditor` route selection in clients | Engine supports architect route; MCP exposes `architect_model`, but the NL Coder UI sends only developer/reviewer and auditor uses the developer route. |

## Missing

- More than one task per role and a fully configurable team graph (the planner currently always keeps the
  required developer/tester/reviewer core and conditionally adds architect/auditor).
- A persisted pipeline selector in the GUI/MCP and a real Flow graph for parallel/conditional branches.
- Results-based **selection** of models. The evidence needed for it is now persisted (model, usage,
  duration, status, tests, review), but no ranking/consumer exists yet.
- Billed cost accounting. Local Ollama has no provider-reported cost; token usage and duration are recorded
  and the cost field is not invented.
- Planner role execution/handoff.

## End-to-end evidence

The isolated two-file mission completed with **four** actually executed roles:

- planner selected `architect → developer → tester → reviewer` because the goal spans two source files;
- architect (read-only tools) delivered notes and token-usage metadata consumed by the developer;
- developer delivered `src/calc.py` + `src/stats.py` and a two-file diff;
- deterministic tester ran independent candidate and oracle suites: **2 passed / 2 passed**, exit 0;
- reviewer delivered `APPROVE` with model/token evidence;
- live files contain `sub` and `mean`; retained diff `2 file(s), +4/-2`;
- dashboard received tasks, handoffs, role→model bindings, attempt metadata, verification and diff.

Machine-readable record: `docs/evidence/frontend/team-mission-evidence.json`; log:
`docs/evidence/frontend/TEAM_MISSION_ACCEPTANCE_INSTALLED.log`. The complete Python suite passes
1,283 tests; the installed VSIX runs the same four-role mission.

## Design decision

The smallest safe seam was `_plan_tasks`: both the sequential and Flow executors call it, so proportional
composition reaches Chat/MCP/extension/Flow without a second orchestration component. The read-only
analysis execution was extracted into one shared `_run_planned_analysis` / `_run_analysis_stage` helper
used by both pipelines, avoiding duplicate architect/auditor implementations.

*Last updated: 2026-10-29.*

# NL Code 1.0 — engine checkpoint (2026-10-30, time-boxed session)

This is a **WIP checkpoint**, not the 1.0 acceptance. Work was stopped at the user's
01:30–01:45 limit. The tree compiles and the focused engine tests below pass, but the
realistic multi-module recovery acceptance has **not** been completed yet.

## Completed in this checkpoint

- **Dynamic multi-task planner** in `MultiAgentOrchestrator._plan_tasks`:
  - one implementation task per declared source path when there are 2–4 source paths;
  - a separate test-update subtask when the objective names test paths;
  - chained dependencies (analysis → implementation subtasks → tester → reviewer);
  - broad path lists remain one integration task instead of exploding into dozens;
  - existing single-path goals remain one developer task.
- **Multiple tasks per role execution**:
  - `_run_developer_tasks` executes all planned developer subtasks on the same staged candidate;
  - completed subtasks are skipped on resume and their structured handoff is replayed;
  - candidate scope is the union of all implementation subtasks;
  - sequential and Flow executors share the same helper.
- **Real CrewAI Flow graph**:
  - `MissionFlow` now uses `@start`, `@router(...)`, `@listen(...)` and a real
    `run_finish` node instead of a single `@start` Python loop;
  - routes: develop, verify, repair, review, promote, finish;
  - verification failure routes into a real repair node and back to verification;
  - durable phase/facts still decide resume; persistence snapshots keep working.
- **Flow repair branch**
  - the executor's `run_verification` can defer repairs and return `needs_repair`;
  - `run_repair` now invokes the real debugger and Flow re-verifies;
  - sequential path still keeps its bounded internal repair loop.
- **Structured developer handoffs** (`task_id`, artifact/diff, decisions, open issues,
  next steps, model metadata); intermediate developer→developer handoffs for subtasks.
- **Real tool surface** in `crew_tools`:
  - `run_tests` (real pytest via existing verifier);
  - `run_command` bounded argv allowlist (`shell=False`; pytest/python compile/git/read-only inspection);
  - `git_status`, `git_diff`;
  - `research_fetch_url` through the permission-gated Research service;
  - `mcp_list_tools` through the existing local MCP client (invocation remains approval-gated);
  - architect/auditor keep read-only file tools.
- **ModelRouter auto selection**:
  - `historical_performance()` aggregates real `task_attempts.metadata_json` outcomes
    (attempts, success rate, duration, tokens, approved missions, optional cost);
  - `auto_select()` ranks explicit candidates by measured capabilities + historical
    results, records `source=auto_ranked` and a selection rationale;
  - `auto`/`automatic` mission routes are resolved before execution, fail closed on error,
    and the selection is persisted in the mission snapshot;
  - mission `start_mission` now defaults to the real Flow pipeline (`pipeline="flow"`),
    while the legacy sequential path remains available.

## Verification done

- `py_compile` of all touched engine files: pass.
- Focused tests: 30 passed
  (`test_mission_flow.py`, `test_flow_resume.py`, `test_mission_team_plan.py`,
  `test_model_router.py`, `test_mcp_sdk.py`).
- Supervisor regressions: 41 passed (`test_supervisor_sh07.py`, `test_supervisor_core.py`).
- Existing one-file mission through the **Flow pipeline** passed end-to-end:
  completed, APPROVE, promoted, candidate+oracle PASS, dashboard received detail + diff.
  The run created two developer subtasks because the objective contained a separated
  test-path clause; this is valid multi-task behavior but the acceptance fixture should
  be simplified to one clean subtask demonstration.

## Not done / next session

1. **Realistic multi-module acceptance** with multiple subtasks, a real correction
   branch, independent tests and review. Not yet built/run.
2. **Measured capability probing**: `auto_select` consumes measured capabilities if
   present, but no Ollama probe was run in this checkpoint; the acceptance must record
   measured `tool_calling`/`structured_output` evidence.
3. **Automatic route end-to-end** with a real `auto` mission; only unit-level implementation
   exists so far.
4. **Flow repair branch proof with a real failure** (not only the FakeExecutor tests).
5. **Structured handoff schema** should be promoted to a typed model and consumed by
   planner/reviewer rather than remaining JSON payloads.
6. **MCP invocation** remains human-approval-gated; only discovery is exposed to the model.
7. **Cost control**: local cost is 0/unknown; no cloud price table or budget policy is wired.
8. **Docs/GUI**: no new GUI work (per instruction); mission detail already shows Flow runs
   via existing status, but no 1.0 acceptance evidence was produced.
9. Existing team-mission acceptance test still assumes one developer task; it needs
   updating for multiple implementation subtasks.

## How to resume

```powershell
python\python.exe -m pytest -q tests/test_mission_flow.py tests/test_flow_resume.py tests/test_mission_team_plan.py
cd frontend; node test/runMissionTests.cjs   # real Flow pipeline
```

Then build the realistic project fixture and run through NL Coder mission mode with
`pipeline="flow"`, inspect `flow_states` transitions and `task_attempts.metadata_json`.

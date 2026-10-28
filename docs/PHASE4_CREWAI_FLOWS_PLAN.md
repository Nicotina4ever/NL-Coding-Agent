# Stage 4 - CrewAI + CrewAI Flows First-Class Integration: Design and Implementation Plan

**Status:** design-only deliverable (no runtime code changed, no tracked-file edits, no autonomous runs).
**Task:** shared `task-25` (design). Owner: runner-integrator.
**Repository baseline:** HEAD `e81a916` (stage 3 supervisor C3e merged; stage 3 still in progress pending SH-07 Tier B).
**Target program stage:** 4 - "Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities" (`docs/product-blueprint/INDEX.json` program_order).
**Backlog requirements covered by this design:** NL-BP-001, 002, 006, 007, 008, 009, 010, 011, 013 (stage-4 CrewAI/model items; the remaining stage-4 GUI/multimodal/voice requirements are out of scope here).
**Write scope:** `build/phase4/` only.
**Inputs read:** `docs/product-blueprint/specifiche/01_ARCHITETTURA_E_RUNTIME.md`, `05_MODEL_HUB_PROVIDERS.md`, `06_MODEL_ADVISOR_E_PARAMETRI.md`, `21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md`, `26_AUTONOMOUS_BACKLOG_EXECUTION.md`, `docs/07_SAFETY.md`, `docs/HARNESS_ACCEPTANCE.md`, `docs/CREWAI_RUNTIME.md`, `docs/PRODUCT_BACKLOG.md`, `docs/product-blueprint/INDEX.json`, `pyproject.toml`, current `agents/orchestrator.py`, `core/supervisor.py`, `core/run_control.py`, `core/resource_gate.py`, `core/backlog.py`, `core/permissions.py`, `core/promotion.py`, `persistence/supervisor_store.py`, `persistence/missions.py`, `models/providers.py`, `tools/registry.py`, `app/services.py`, `cli.py`, and the installed CrewAI 1.15.32 sources under `python/Lib/site-packages/crewai` (read-only).

---

## 0. Executive summary

The installed CrewAI runtime is already the only CrewAI code path in the product: `crewai==1.15.32` (plus the separate `crewai-core==1.15.32` distribution) resolves from `python/Lib/site-packages`, while the 467 MiB `crewAI/` checkout remains reference-only and is excluded from the payload (NL-BP-001/002 verified). However, the integration is still a thin per-call wrapper: `MultiAgentOrchestrator._call_model()` constructs one Agent + Task + Crew per LLM step and throws the Crew away. There are no first-class agent/team definitions, no shared model routing, no CrewAI Flows pipeline, no memory/delegation policy, no capability-aware routing, and no CrewAI event/evidence bridge. The supervisor (stage 3) drives missions through the sequential orchestrator only.

This plan makes the installed CrewAI the **maintainable orchestration backend** and adds a complete, durable **CrewAI Flows** pipeline for the product mission lifecycle, without a second vendor checkout, without a second Python environment, and without weakening the staged-candidate safety harness.

The design has five pillars:

1. **Crew backend layer (`agents/crew_backend.py`):** one place that builds agents, tasks, crews and flows from immutable `AgentSpec` / `TaskSpec` / `CrewSpec` descriptors; model resolution and permission checks happen here, once; tests inject a `FakeCrewRuntime` through a protocol seam instead of monkeypatching private methods.
2. **Flows pipeline (`flows/` package):** a `MissionFlow(Flow[MissionState])` whose methods map 1:1 onto the existing stage engine (developer -> verify/repair -> review -> promote), with durable state persisted in the **app's SQLite database** (explicit path, not `%LOCALAPPDATA%\CrewAI`), resume-by-durable-state so completed steps never re-call a model, and a supervisor-level flow that drives the queue lifecycle.
3. **Supervisor integration:** a `MissionExecutor` protocol with `SequentialMissionExecutor` (today's behavior, default) and `FlowMissionExecutor`; the supervisor keeps ownership of queue states, leases, approvals, evidence and classification, so the Flow is an executor, not a second source of truth.
4. **Model routing + capability registry:** `ModelRouter` resolves role -> provider/model/parameters from the Model Hub, enforces `permissions.assert_model_permitted` and `required_capabilities` (measured > declared > unknown), snapshots the binding into the mission config for NL-BP-011, and refuses unsupported routes instead of pretending.
5. **Containment/licensing/upgrade discipline:** telemetry and CrewAI default storage paths are explicitly disabled/redirected; memory defaults (cloud LLM + OpenAI embedder) are never enabled implicitly; a pinned version, API-surface compatibility test, SBOM generation and an upgrade playbook keep the dependency maintainable.

Rollout is behind human-owned pipeline flags (`pipeline=sequential|flow`, default `sequential`) and lands as C4a-C4e. Every commit is independently testable with fake models and no network. Stage 4 must not start before the stage-3 program gate passes (program_order rule); C4a (backend extraction) is low-risk and can be prepared in parallel only with an explicit Lead exception.

---

## 1. Design decisions (top 10)

1. **The installed package is the backend; the vendor checkout is never an import source.** All new code imports `crewai` from the embedded runtime site-packages. No second checkout, no second venv/conda, no edits to site-packages. `crewAI/` stays protected vendor reference and stays excluded from payloads (NL-BP-001/002 remain the guard tests).
2. **Keep one CrewAI execution seam that tests can replace.** The current `_call_model` monkeypatch seam is good; it becomes a typed `CrewRuntime` protocol. Flow methods and future multi-agent crews use the same protocol, so fake-model tests (no Ollama, no network) cover every path.
3. **Flow state lives in the app DB, with an explicit path.** The installed default `SQLiteFlowPersistence()` writes to `C:\Users\<user>\AppData\Local\CrewAI\<cwd-name>\flow_states.db` (measured; see section 12). That path is outside the app data dir and is created as a side effect. The design implements `AppFlowPersistence(FlowPersistence)` backed by `NL_DATA_DIR` SQLite (same WAL/backup story as missions), and keeps CrewAI bundled SQLite backend only as the verified reference/spike fallback. No default CrewAI storage path is ever used.
4. **Resume is explicit and durable, not magic.** CrewAI 1.15.32 offers (a) `@persist` state snapshots and (b) checkpointing (`CheckpointConfig`, `Flow.from_checkpoint`). A smoke test proved that `kickoff(restore_from_state_id=...)` restores state but **re-runs start methods with a fresh id** (counter 2 -> 4), i.e. it is "fork from state", not "skip completed steps". The design therefore makes resume deterministic at the **step level**: every Flow method first checks durable mission facts (tasks/verification/promotion status) and returns the recorded outcome without a model call, and the flow is re-entered with a pinned `inputs['id']` so its persistence key is stable. Checkpointing remains an optional spike in C4a; it is not required for the acceptance gates.
5. **Supervisor remains the source of truth for queue/lease/evidence; Flow is an executor.** `mission_queue` states, `supervisor_runs`, evidence rows and approvals are written exactly as today (single writer `record_outcome`). Flow state is a checkpoint of the executor; on restart the supervisor reconciles queue rows from Flow snapshots + mission facts and never duplicates a mission or a model call.
6. **Human-in-the-loop uses the app approval workflow, not a console prompt.** CrewAI `@human_feedback` + `HumanFeedbackProvider` is mapped onto the existing `approvals` table and queue `INTERRUPTED/WAIT_APPROVAL` semantics. A GUI/CLI provider raises `HumanFeedbackPending` after persisting the request; approval resolution resumes via `Flow.from_pending(...).resume(feedback)`. Risk decisions stay in non-LLM policy code (no model-collapsed approval for delete/network/cloud).
7. **Memory, delegation and telemetry are off by default and local-only when enabled.** Measured defaults are unsafe for a local-first desktop app: CrewAI `Memory` defaults to `llm='gpt-5.4-mini'`, an OpenAI embedder when none is given, and LanceDB under `%LOCALAPPDATA%\CrewAI\...\memory`. Telemetry is enabled unless `OTEL_SDK_DISABLED` / `CREWAI_DISABLE_TELEMETRY` / `CREWAI_DISABLE_TRACKING` is set. The app runtime env and router enforce the safe defaults; the app SQLite evidence ledger remains the durable memory of record.
8. **Model routing is auditable and fail-closed.** Role -> model resolution moves from scattered `DEFAULT_*_MODEL` constants into `ModelRouter`: Model Hub inventory + capability registry + permission policy + local-first order -> `ModelBinding` snapshot. Unsupported capability combinations are refused with an explanation (NL-BP-009), and cloud/network escalation still requires explicit persisted grants (NL-BP-072/076).
9. **The staged-candidate harness is untouched.** Flow steps call the same stage engine methods; promotion is still the last gate; four model tools remain (`read_file/write_file/patch_file/list_dir`) and the shell/test/git tools remain absent (SH-05). Nothing in this design adds a model-facing command executor.
10. **Pin, prove compatibility, ship an SBOM.** `crewai==1.15.32` stays pinned; a new compat test pins the exact API surface we use (Flow decorators, persistence base, HITL, event types, Agent/Crew/Task fields); an SBOM is generated from installed distributions and validated before release; the upgrade procedure is documented and requires fake-model + full-suite evidence.

---

## 2. Measured current state (evidence, HEAD e81a916)

All facts below were measured read-only in this session (commands in section 12). They ground every design claim; unverified things are labelled.

### 2.1 Installed runtime

| Item | Measurement |
|---|---|
| `crewai` version / path | `1.15.32` / `K:\AI\NL Coding Agent\python\Lib\site-packages\crewai\__init__.py` (never under `crewAI/`) |
| `crewai-core` | `1.15.32` (separate distribution; `crewai_core.paths`, `crewai_core.telemetry`, `crewai_core.lock_store` are imported by the Flow engine) |
| `crewai-cli` | `1.15.32` |
| notable transitive deps | `litellm 1.100.4`, `chromadb 1.5.9`, `lancedb 0.40.0`, `pydantic 2.12.5`, `pytest 9.2.0` |
| Python runtime | embedded `python\python.exe` (3.12.10), no global/venv requirement |
| `crewai` license metadata | `License: None`, no license file inside `crewai-1.15.32.dist-info`; evidence exists in `crewAI/LICENSE` (MIT-style, Copyright (c) 2025 crewAI, Inc.); SBOM/licensing work must close this gap (section 7) |
| vendor checkout | `crewAI/` exists (reference only, workspace pyproject, MIT `LICENSE`); `crewAI-tools/` absent; `tests/test_crewai_runtime.py` enforces pin + import path |

### 2.2 Current application seams (read from HEAD)

- `agents/orchestrator.py`: 1426 lines. `MultiAgentOrchestrator.__init__(project_root, base_url, project_id=None)`; `run_mission(mission_id, goal=None, developer_model=None, reviewer_model=None, debug_model=None, stop_after=None, control=None)`; single `_call_model(role, model_name, prompt, *, goal, backstory, expected_output, tools=None)` builds `Agent -> Task -> Crew(process=Process.sequential)`; `_make_llm` enforces `permissions.assert_model_permitted(model, base_url, project_id)`; stage methods `_run_developer_stage / _run_tester_stage / _run_debugger / _run_reviewer_stage`; promotion helpers; `_checkpoint(control, stage)` only at safe boundaries (never around the promotion write).
- `core/supervisor.py`: 1845 lines. Durable loop `preflight -> acquire lease -> reconcile -> select/enqueue/claim -> execute -> classify -> record_outcome`; `SupervisorConfig` (mode, budgets, models, backoff, `max_consecutive_failures`, `allowed_cloud_models`); `orchestrator_factory` injection; `_invoke_orchestrator(mission_id, goal)` calls `run_mission(..., control=self.control)`; `classify()` maps results into `VERIFIED / INTERRUPTED / WAIT_RESOURCE / WAIT_APPROVAL / REPAIRABLE / HARD_BLOCK`; `record_outcome()` is the single writer of queue/backlog/evidence transitions; approvals are created for `WAIT_APPROVAL`.
- `persistence/supervisor_store.py`: queue states `PROPOSED, READY, CLAIMED, RUNNING, VERIFYING, REVIEWING, VERIFIED, NEEDS_FIX, BLOCKED, INTERRUPTED, CANCELLED` with an explicit transition table; claim tokens/idempotency keys; leases/heartbeats; `supervisor_runs`; evidence ledger; approvals.
- `core/run_control.py`: cooperative stop checkpoints (`control.checkpoint(stage)` raises `RunStopped`); pause is honoured only at mission boundaries.
- `models/providers.py`: `ModelHub(providers).discover(timeout)` returning `ProviderSnapshot` / `ModelInfo` (provider, name, size, loaded, family, `capabilities: tuple` currently unpopulated); Ollama + generic OpenAI-compatible adapters; `unload(provider_id, name)`.
- `core/permissions.py`: project-scoped grants (read/write/execute base scopes, delete/network/cloud explicit), `assert_model_permitted`, `PermissionDenied`; supervisor preflight blocks without base scopes.
- `tools/registry.py`: read-only `ToolRegistry` / `ExternalTool` / `ToolCapability` with bounded probes for git/python/pytest/ollama/ffmpeg (stage-2 task-19); discovery only, no execution grants.
- `app/services.py`: `supervisor_*` service methods; `cli.py`: `supervisor run|start|stop|pause|resume|status|index|recover|advance-stage`; stage-3 GUI panels minimal.

### 2.3 Installed Flow API surface (measured, 1.15.32)

`from crewai.flow.flow import Flow, start, listen, router, or_, and_` and `from crewai.flow import ...` export:

- `Flow[T]` with pydantic fields: `initial_state, name, tracing, stream, memory, input_provider, suppress_flow_events, human_feedback_history, last_human_feedback, persistence, max_method_calls, execution_context, checkpoint, checkpoint_completed_methods, checkpoint_method_outputs, checkpoint_method_counts, checkpoint_state`.
- `FlowState` base model with `id` (uuid default factory); persistent state must have an `id` (decorator raises otherwise).
- `kickoff(inputs=None, input_files=None, from_checkpoint=None, restore_from_state_id=None)`, `kickoff_async`, `resume(feedback)`, `resume_async`, `from_pending(flow_id, persistence)`, `pending_feedback`, `from_checkpoint(config)`, `fork(config)`, `plot`, `ask`, `recall/remember`.
- `crewai.flow.persistence`: `FlowPersistence` (abstract: `init_db/save_state/load_state`; optional `save_pending_feedback/load_pending_feedback/clear_pending_feedback`), `SQLiteFlowPersistence(db_path=None)`, `persist(persistence=None, verbose=False)` decorator (class- or method-level metadata stamper; the engine saves state after each persisted method).
- `crewai.flow.human_feedback.human_feedback(message, emit, llm, default_outcome, metadata, provider, learn, learn_source, learn_strict)`; `HumanFeedbackResult(output, feedback, outcome, timestamp, method_name, metadata)`; `HumanFeedbackPending`; `HumanFeedbackProvider`.
- `crewai.state.checkpoint_config.CheckpointConfig` fields: `location, on_events, provider, max_checkpoints, restore_from`; `Flow.from_checkpoint` exists but was **not** smoke-verified in this design (see risks).
- Flow event types (`crewai.events.types.flow_events`): `FlowCreatedEvent, FlowStartedEvent, FlowFinishedEvent, FlowFailedEvent, FlowPausedEvent, FlowPlotEvent, FlowInputRequestedEvent, FlowInputReceivedEvent, MethodExecutionStartedEvent, MethodExecutionFinishedEvent, MethodExecutionFailedEvent, MethodExecutionPausedEvent, HumanFeedbackRequestedEvent, HumanFeedbackReceivedEvent`; bus `crewai.events.crewai_event_bus` exposes `on/off/emit/aemit/register_handler/flush/shutdown`.
- `Agent` relevant fields include `role, goal, backstory, llm, tools, allow_delegation, max_iter, max_rpm, memory, verbose, tools_handler, callbacks, step_callback, guardrail, max_retry_limit, execution_context`; `Crew` includes `agents, tasks, process(sequential|hierarchical), memory, embedder, manager_agent/manager_llm, step_callback, task_callback, output_log_file, planning, max_rpm`; `Task` includes `description, expected_output, agent, context, human_input, output_json/output_pydantic/response_model, guardrail(s), max_retries, async_execution`.

### 2.4 Behavioural smoke results (temp dir, read-only for the repo)

A minimal `@persist(SQLiteFlowPersistence(temp))` flow with `@start` -> `@listen`:

- ran offline (no LLM/Crew); persisted rows: `begin: counter=1`, `finish: counter=2` under one `flow_uuid`;
- `CounterFlow(persistence=...).kickoff(restore_from_state_id=<id>)` restored state but assigned a **new** flow id and re-ran both methods (counter 2 -> 4): "fork from state", not "resume skipping completed steps";
- a CrewAI event-bus console listener emitted `'charmap' codec can't encode character '\U0001f30a'` handler errors on the Windows console (NL-BP-013 surface reappears through Flow/Crew events; the app must force UTF-8 child env and not rely on console printing);
- the temp SQLite file stayed locked for the interpreter lifetime (Windows `PermissionError` on immediate temp-dir cleanup): tests must tolerate this (pytest `tmp_path` cleanup is lazy) or close persistence handles explicitly.

### 2.5 Unsafe defaults that must be overridden

| Default | Measured behavior | Required app behavior |
|---|---|---|
| Flow persistence | `SQLiteFlowPersistence()` defaults to `%LOCALAPPDATA%\CrewAI\<project-dir>\flow_states.db`; `db_storage_path()` creates the directory as a side effect | always pass an explicit app path; never call the default constructor in product code |
| Telemetry | OTLP exporter to `https://telemetry.crewai.com:4319`; opt-out env flags `OTEL_SDK_DISABLED` / `CREWAI_DISABLE_TELEMETRY` / `CREWAI_DISABLE_TRACKING` (source `crewai_core.telemetry.Telemetry._is_telemetry_disabled`) | set all three in the app/worker env by default; expose explicit opt-in only |
| Memory | `Memory` defaults: `llm='gpt-5.4-mini'`, `embedder=None` -> OpenAI embedder (`text-embedding-3-large`), storage LanceDB under `%LOCALAPPDATA%\CrewAI\...\memory` | never enable implicitly; if enabled: local LLM binding, local embedder config, explicit `storage=` under `NL_DATA_DIR`, project scope, no secrets |
| Storage root | `crewai_core.paths.db_storage_path()` = appdirs user data dir for author `CrewAI`, project dir from `CREWAI_STORAGE_DIR` or `Path.cwd().name` | all product flows pass explicit paths; containment test asserts no new files under the user CrewAI dir during fake-model tests |

---

## 3. Target architecture: installed CrewAI as the maintainable backend

### 3.1 Layer map (additive; reuses stage-2/3 code)

```text
GUI (PySide6) / CLI
        |
app/services.py  (stable facade; supervisor_* + new flow_* read/write APIs)
        |
core/supervisor.py (non-LLM durable policy: queue, lease, approvals, evidence, classification)
        |  MissionExecutor protocol
        +--> SequentialMissionExecutor  -> MultiAgentOrchestrator.run_mission()   [default today]
        +--> FlowMissionExecutor        -> flows.supervisor_flow.SupervisorMissionFlow
                                                   |
                                      flows.mission_flow.MissionFlow(Flow[MissionState])
                                                   |  calls MissionStageEngine methods
                                      agents/mission_stage_engine.py  (extracted from _run_locked)
                                                   |
                                      agents/crew_backend.py   (CrewRuntime protocol)
                                        + CrewAIBackend (production)
                                        + FakeCrewRuntime (tests)
                                                   |
                                      models/model_router.py -> ModelHub + capability registry + permissions
                                                   |
                                      existing stage-2 harness: staging, validation, candidate+oracle verification,
                                      reviewer gate, promotion (last), recovery/journal/CAS, evidence
```

Everything above the `CrewRuntime` line is deterministic policy code. The LLM only executes the prompts inside a stage/flow method. No model can grant permissions, change mode/budget, select the next task, or bypass promotion.

### 3.2 Component responsibilities

**A. `agents/crew_backend.py` (new) - CrewAI runtime adapter**

- `CrewRuntime` protocol (typing.Protocol, runtime-checkable):
  - `run_agent(spec: AgentSpec, prompt: str, *, tools: list, expected_output: str) -> AgentResult`
  - `run_crew(spec: CrewSpec, inputs: dict) -> CrewResult` (future read-only multi-agent pipelines; not used by write stages)
  - `run_flow(flow: Flow, *, inputs: dict, resume_feedback: str | None = None) -> FlowResult` (serialization/runtimes/locking in one place)
  - `close() -> None`
  - `AgentResult(text, model, provider, usage, duration_s, tools_used, raw_events)`; `CrewResult(output, task_outputs, usage, ...)`; `FlowResult(output, flow_id, state, pending_feedback)`.
- `CrewAIBackend` (production): builds `Agent(role, goal, backstory, llm=router.build_llm(binding, project_id), tools=..., allow_delegation=policy.allow, max_iter=..., verbose=False)`, `Task(...)`, `Crew(agents=..., tasks=..., process=Process.sequential, verbose=False, memory=policy.memory_enabled)`; `kickoff()`; maps exceptions (`PermissionDenied`, LLM errors) into typed `CrewRuntimeError` subclasses that the stage engine/supervisor classify.
- `FakeCrewRuntime` (tests): scripted responses per role/flow step, call log, hooks (same pattern as `tests/test_orchestrator_staging.py::ScriptedModel`), zero network.
- `crew_runtime_env()`: the single env builder for in-process/child CrewAI work: `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `NO_COLOR=1`, `OTEL_SDK_DISABLED=1`, `CREWAI_DISABLE_TELEMETRY=1`, `CREWAI_DISABLE_TRACKING=1`; `CREWAI_STORAGE_DIR` not used (explicit paths instead). Unit-tested so no caller forgets.
- No `run_command`, no shell, no test-runner tool is added here; `tools=` comes from `get_project_tools(stage.workspace)` for write stages (4 tools) or from an explicit read-only allowlist for non-write crews.

**B. `agents/specs.py` (new) - declarative agents/tasks/crews**

- `AgentSpec(role_id, display_role, goal_template, backstory, model_role, tools_policy, allow_delegation=False, max_iter, temperature, capability_requirements)`.
- `TaskSpec(task_id, description_template, expected_output, agent_role_id, context=(), output_json=None)`.
- `CrewSpec(crew_id, process="sequential", agents=(), tasks=(), memory_policy="off", max_rpm=...)`.
- Built-in immutable catalog for the product roles: `developer`, `debugger`, `reviewer`, `tester` (deterministic verification, no LLM), `architect` (read-only), `auditor` (read-only), `planner` (read-only, future). Roles are code-reviewed constants, not model-generated. Team optimization/creation (NL-BP-066/067) is a later stage; this design provides the seam (`CrewSpec`) without enabling autonomous team invention.
- Prompts/backstories move out of orchestrator string literals into the catalog templates (developer/debugger/reviewer prompt texts preserved; prompt regressions checked by tests asserting required evidence lines, as in `test_orchestrator_staging.py`).

**C. `agents/model_router.py` (new) - model routing (section 6) and `models/capabilities.py` (new) - capability registry.**

**D. `agents/mission_stage_engine.py` (new, C4a extraction)**

- Pure refactor of `MultiAgentOrchestrator._run_locked` stage sequence into explicit methods with stable contracts:
  - `run_developer(mission_id, task, goal, model_binding, stage, baseline, control) -> StageOutcome`
  - `run_tester(mission_id, task, model_bindings, stage, baseline, control) -> StageOutcome` (includes bounded repair loop; every debugger call persists attempts exactly as today)
  - `run_reviewer(mission_id, task, model_binding, stage, baseline) -> StageOutcome`
  - `promote(mission_id, stage) -> PromotionOutcome`
  - `finalize_completed/blocked/interrupted(...)` unchanged in the orchestrator (single writer of `missions.status`).
- `MultiAgentOrchestrator.run_mission()` becomes a thin composer that calls the engine in the same order, with the same checkpoints, exceptions and persistence writes. Acceptance for C4a: `tests/test_orchestrator_staging.py`, `tests/test_orchestrator_seam.py`, `tests/test_harness_repair.py` and the full suite stay green with zero behavioral change.
- `StageOutcome(status, verdict, error, code, payload, verification)` mirrors today's result fields so the supervisor `classify()` keeps working unchanged.

**E. `flows/` package (new, C4b/C4c/C4d)** - section 4.

**F. Supervisor adapter (modified in C4c)** - section 5.

### 3.3 Agents, tasks, crews, memory, delegation, tools: the product policy

| Capability | Product policy | Enforcement point |
|---|---|---|
| Agents | deterministic catalog (`AgentSpec`), one role per stage; code-reviewed prompts | `agents/specs.py` + crew backend refuses unknown role ids |
| Tasks | `TaskSpec` mapped 1:1 to mission tasks in SQLite; context/expected_output explicit | stage engine; task rows remain the durable audit trail |
| Crews | production write path uses single-agent Crew per step (today's behavior) so no multi-writer risk; multi-agent Crew allowed only for read-only analysis/audit | `CrewSpec.process=sequential` default; `hierarchical` only for read-only crews behind a flag in C4d |
| Memory | app SQLite evidence ledger is memory of record; CrewAI Memory optional, **off by default**, local-only (local LLM for analysis, local embedder, explicit path, project scope, no secrets) | `MemoryPolicy` in backend; `tests/test_flow_memory_policy.py` asserts no cloud client/storage path is touched |
| Delegation | `allow_delegation=False` for every write-capable agent; read-only delegation max depth 1 with allowlist + budget, behind `DelegationPolicy` flag | `CrewAIBackend` (model cannot enable it) |
| Tools | write stages: only 4 stage-bound filesystem tools; no shell/test/git (SH-05). Read-only crews: explicit allowlist of read-only tools. External tools (registry) are discovery/health only; execute requires persisted grant + approval | `get_project_tools` + `DelegationPolicy` + `permissions` |
| Flows | mission + supervisor pipelines (section 4) | `flows/` package |

### 3.4 Containment and runtime invariants

1. **No new environment:** use `python\python.exe` and its installed site-packages only. No `pip install`, no second venv/conda, no vendored copy (`AGENTS.md`, SPEC-01).
2. **No vendor imports:** `import crewai` must never resolve under `crewAI/` (`tests/test_crewai_runtime.py` keeps this).
3. **No writes to CrewAI default storage:** product code never calls `SQLiteFlowPersistence()`, `Memory()`, `Crew(memory=True)` without explicit local paths/config. A test asserts the user appdata CrewAI dir is not modified by fake-model suites (compare directory state before/after where it exists).
4. **Telemetry off by default:** `crew_runtime_env()` sets the three opt-out flags; a test asserts the builder + subprocess env; opt-in only via an explicit human setting (not implemented in this stage).
5. **No cloud/network without grants:** every LLM construction path goes through `ModelRouter.build_llm()` -> `permissions.assert_model_permitted`; tests use local/fake bindings and assert a cloud binding raises `PermissionDenied`.
6. **UTF-8 boundary:** `PYTHONUTF8/PYTHONIOENCODING` in runtime env; app event bridge formats events itself (no raw console emoji from CrewAI listeners); `decode_output` remains for child output (NL-BP-013).
7. **Single writer per concern:** Flow persistence writes only flow tables; supervisor `record_outcome` writes queue/backlog/evidence; orchestrator finalize writes mission status; promotion writes live tree. No dual writes.
8. **Stop safety:** Flow methods call `control.checkpoint(stage)` only at the same safe boundaries as today; promotion remains uninterrupted. Pause is honoured at mission boundaries.

## 4. Complete CrewAI Flows integration (product pipelines)

### 4.1 What "complete" means for NL-BP-006/007

Acceptance requires a **production** pipeline implemented with `crewai.flow.flow.Flow`, with persisted + resumable state, deterministic transitions, fake-LLM tests, no vendor-checkout dependency and no unused placeholder. This design provides:

1. `SupervisorRunFlow` - the supervisor loop iteration graph (outer pipeline, C4c);
2. `MissionFlow` - the per-mission staged-candidate pipeline (inner pipeline, C4c);
3. optional read-only `AuditFlow` - project analysis/audit pipeline for the GUI (C4e, non-mutating);
4. HITL approval pauses inside `MissionFlow` (C4d).

Exactly **one executor per mission** (sequential or flow, never both) is selected by the supervisor; the Flow is not a second scheduler. The deterministic gate logic (validation, candidate/oracle verification, review verdict, promotion) stays in the stage engine; the Flow only sequences the steps and persists its state.

### 4.2 Pipeline inventory

| Flow | Scope | Mutates live tree? | Model calls | Owner/commit |
|---|---|---|---|---|
| `SupervisorRunFlow` | one supervised run: preflight -> acquire -> reconcile -> loop(select -> execute -> classify -> record) -> stop/pause/budget exit | only through `MissionFlow` / sequential executor | none directly | supervisor adapter, C4c |
| `MissionFlow` | one mission: developer -> verify/repair loop -> reviewer -> promotion -> finalize | only at promotion (same rules as today) | developer/debugger/reviewer | stage engine, C4c |
| `AuditFlow` (optional C4e) | read-only repository audit/report composing read-only agents | no | architect/auditor | GUI/CLI later |
| `ApprovalFlow` (sub-graph inside MissionFlow) | `@human_feedback` gate for risky action / assisted review | no | none for deterministic outcomes | C4d |

No Flow method may modify the live tree directly. The only live write path remains `promotion.promote()` inside the stage engine.

### 4.3 Flow state model: `MissionState(FlowState)`

Minimal, reference-based state (authoritative mission facts stay in SQLite tables):

| Field | Type | Source of truth / meaning |
|---|---|---|
| `id` | uuid str | Flow persistence key (required by `@persist`); pinned on resume |
| `schema_version` | int | state-schema evolution; unknown > supported -> blocked, never guessed |
| `project_id`, `mission_id`, `queue_id`, `supervisor_run_id` | ints | durable business keys |
| `requirement_id`, `goal`, `write_scope` | str/list | mission input snapshot (immutable during a flow) |
| `phase` | enum-like str | planned / developing / verifying / repairing / reviewing / promoting / waiting_approval / completed / blocked / interrupted |
| `attempt`, `repair_round`, `max_repairs` | ints | bounded loop counters (authoritative copy in tasks/queue too) |
| `stage_dir`, `baseline_sha256` | str | staged-candidate identity (validated against stage manifest on resume) |
| `changed_paths`, `diff_stat`, `promotion_status` | list/str | projections of stage evidence, re-derived on resume |
| `verification_ref`, `review_verdict`, `review_ref` | str | evidence paths/keys; verdict is authoritative in handoffs |
| `last_error`, `error_code` | str | classification input for supervisor `classify()` |
| `approval_id`, `approval_action` | int/str | HITL link (C4d) |
| `model_bindings` | list[dict] | per-role `ModelBinding` snapshot (NL-BP-011) |
| `config_sha256` | str | hash of routing/role/provider config used |
| `idempotency_key` | str | backlog/queue idempotency key (same as supervisor store) |
| `created_at`, `updated_at` | str | ISO timestamps |

Rules: state holds references + hashes, never raw prompts/diffs/secrets; size guard (<=256 KiB; oversized state is a fail-closed error, not truncation); every step re-validates `stage_dir`/manifest hashes against the live staged candidate before trusting replay data; state schema is additive and versioned.

### 4.4 Persistence: `AppFlowPersistence(FlowPersistence)` in the app DB

Why not the bundled `SQLiteFlowPersistence` by default: measured default writes to `%LOCALAPPDATA%\CrewAI\<cwd-name>\flow_states.db` (outside app data, side-effect directory creation), keeps a separate DB/backup story from missions, and has no link to the app approvals. The bundled backend stays available behind a **spike-only** flag for C4a comparison, never as product default.

New additive tables (migrations follow the existing `database.py` pattern; no backfill, no legacy rewrite):

```sql
CREATE TABLE IF NOT EXISTS flow_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_uuid TEXT NOT NULL,
    method_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    state_sha256 TEXT NOT NULL,
    state_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flow_states_uuid ON flow_states(flow_uuid);

CREATE TABLE IF NOT EXISTS flow_pending_feedback (
    flow_uuid TEXT PRIMARY KEY,
    approval_id INTEGER,
    method_name TEXT NOT NULL,
    context_json TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flow_runs (
    flow_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    mission_id INTEGER,
    queue_id INTEGER,
    supervisor_run_id INTEGER,
    pipeline TEXT NOT NULL,             -- 'mission' | 'supervisor' | 'audit'
    status TEXT NOT NULL,               -- RUNNING | PAUSED_WAITING_APPROVAL | INTERRUPTED | COMPLETED | BLOCKED | FAILED
    last_method TEXT,
    state_sha256 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_flow_runs_mission ON flow_runs(mission_id);
CREATE INDEX IF NOT EXISTS idx_flow_runs_status ON flow_runs(status);

ALTER TABLE missions ADD COLUMN flow_id TEXT;   -- additive; NULL for sequential missions
```

Adapter contract (implements the full `FlowPersistence` interface from the installed package):

| Method | Behavior |
|---|---|
| `init_db()` | idempotent migration of the 3 tables + mission column (via existing migration helper) |
| `save_state(flow_uuid, method_name, state_data)` | one transaction: insert snapshot row + upsert `flow_runs.last_method/state_sha256/updated_at`; reject oversized/non-serializable state |
| `load_state(flow_uuid)` | latest state_json or None |
| `save_pending_feedback(flow_uuid, context, state_data)` | persist pending context + approval link (single row per flow); also snapshot state |
| `load_pending_feedback(flow_uuid)` | return (state, context) or None |
| `clear_pending_feedback(flow_uuid)` | delete marker after successful resume |

Operational rules: use `database.get_connection()` (WAL, busy_timeout, foreign_keys); one short transaction per save; per-mission `mission_lock` already serializes promotions/writes; snapshots are small (<256 KiB) and pruned per policy (keep latest + last 50 per flow, prune on terminal reconciliation; `flow_runs` retained for audit); pending feedback cleared only after resume evidence is recorded; connections are closed after each call (Windows lock issue measured only with the bundled backend kept open).

State schema check on load: if `schema_version` is newer than supported -> mark flow `BLOCKED` with a clear error (never guess/rewrite).

### 4.5 `MissionFlow` graph, checkpoints and resume semantics

```text
start(resume?)
  phase = derive_phase(state, durable mission facts)          # deterministic, no model call
  router: planned -> develop | verified -> review | promoted -> finish
develop (@persist)
  result = engine.run_developer(...)                          # staged candidate only
  control.checkpoint("developer")                             # safe boundary (stop honoured)
verify (@persist)
  result = engine.run_tester(...)                             # candidate+oracle + bounded repairs
  control.checkpoint("tester")
  router: passed -> review | failed+repair budget -> repair -> verify | exhausted -> blocked
review (@persist)
  result = engine.run_reviewer(...)                           # candidate diff only
  # optional HITL pause points (C4d) via @human_feedback
  router: APPROVE -> promote | REJECT -> blocked
promote (@persist)
  result = engine.promote(...)                                # promotion last; journal/CAS/recovery
finish
  return result_payload(status, verdict, diff_stat, changed_paths, promotion_status, error)
```

**Resume-by-durable-state** (primary strategy, no reliance on unverified checkpointing): every method starts with a guard that queries the authoritative durable facts and returns the recorded outcome without calling a model:

| Step | Guard before model call |
|---|---|
| `develop` | developer task completed + persisted developer handoff/attempt -> return recorded candidate (re-validate stage; if invalid -> blocked) |
| `verify` | tester task completed + persisted `verify:candidate`/`verify:oracle` rows -> reuse report; persisted verified candidate -> mark_verified rebind path (existing `_rebind_persisted_verification`) |
| `repair` | repair round counters from tasks/attempts; never exceed `MAX_REPAIR_ATTEMPTS`/`MAX_TOTAL_STAGE_ATTEMPTS` |
| `review` | reviewer handoff with verdict exists -> reuse; REJECT stays blocked |
| `promote` | promotion `reconcile(stage)`/`is_live_promoted` -> recover completed promotion (existing branch) |
| `finish` | mission status terminal -> return recorded payload |

The Flow is re-entered with **pinned state id** `kickoff(inputs={"id": flow_id, ...})` so `@persist` keeps writing under the same `flow_uuid`; a resume never starts a second history. The startup `start` method re-derives `phase` from SQLite facts even if the persisted state is stale (facts win over state; conflict -> blocked with reconciliation evidence).

**Crash-window matrix** (each has a fake-model test):

| Crash point | Expected on restart | Mechanism |
|---|---|---|
| before developer writes | resume re-runs developer | no facts recorded |
| after developer write, before persist | stage manifest exists; re-validate and continue (no duplicate write; `_ensure_stage` reuses stage) | stage manifest + `_ensure_stage` |
| after verification persisted, before review | verify reused from verification_runs/report; no re-run | verify guard |
| after review APPROVE, before promotion | promotion journal/reconcile path; one promotion | `promotion.reconcile` + CAS |
| during promotion | journal reconcile (all-after = complete, mixed = CAS rollback, human edit = blocked) | existing stage-2 machinery, unchanged |
| after promotion, before finalize | `_finalize_completed` from live diff; one completion | live diff + mission status |
| while waiting approval | queue INTERRUPTED/WAIT_APPROVAL; resume only after approval | approval provider + pending feedback |

**Stop/pause:** Flow methods call `control.checkpoint(stage)` at the same boundaries as today's `_checkpoint` (never between reviewer APPROVE and promotion write). `RunStopped` is caught by the executor and returned as `{"status": "interrupted", ...}`; the supervisor maps it to queue INTERRUPTED and the existing resume command. Pause is honoured at mission boundaries (unchanged).

**Checkpointing (optional C4a spike, not required):** `CheckpointConfig(location, on_events, provider, max_checkpoints, restore_from)` + `Flow.from_checkpoint` exist in 1.15.32 but were not smoke-verified here. C4a must evaluate with a fake flow in a temp dir whether it: resumes completed methods without repeating, supports a local/app-owned provider, and adds no default storage path. Only if all three pass may `flow.resume_strategy=checkpoint` be offered; otherwise it stays unimplemented and documented.

### 4.6 Supervisor integration: persistence-backed mission executor

```text
core/supervisor.py
  SupervisorConfig.pipeline = "sequential" | "flow"      (default sequential; validated)
  Supervisor._build_executor() -> MissionExecutor
     SequentialMissionExecutor  -> MultiAgentOrchestrator.run_mission(...)          # today
     FlowMissionExecutor        -> flows.supervisor_flow.execute_mission_flow(...)  # new
  Supervisor._invoke_mission(mission_id, goal) -> dict   # same contract as today
  execute_queue_item(...) -> claim -> self._invoke_mission(...) -> classify() -> record_outcome()
```

`MissionExecutor` protocol: `execute(mission_id: int, goal: str | None, *, control: RunControl, models: dict[str, str | None]) -> dict`. The returned dict keeps today's keys (status, mission_id, promotion_status, changed_paths, diff_stat, verdict, review, error, verification_runs, handoffs) so `classify()` and `record_outcome()` are unchanged.

Lifecycle mapping (single writer per concern):

| Event / step | Flow persistence | Supervisor store/DB | Evidence/events |
|---|---|---|---|
| executor starts mission | flow_id created (uuid), `flow_runs` RUNNING | queue RUNNING (already), mission.staging_dir set by engine | mission_evidence kind `flow` record `start`; event `flow.started` |
| each method finished | state snapshot (+sha) | `flow_runs.last_method/state_sha256` | mission_evidence kind `flow_method` with method, duration, state sha; event `flow.method` |
| HITL pause | pending feedback row | queue INTERRUPTED (failure_class WAIT_APPROVAL), run WAITING_FOR_APPROVAL, approval row (action, scope, flow_id, method) | evidence `flow_paused`; event `flow.paused` |
| approval decided | pending feedback cleared on resume | approval status updated via `decide_approval` | evidence `approval`; event `flow.resumed` |
| flow returns | `flow_runs` terminal (COMPLETED/BLOCKED/FAILED/INTERRUPTED) | `classify` -> queue transition, backlog, evidence (unchanged writer) | handoff/result evidence as today |
| restart/reconcile | load `flow_runs` active rows | compare with queue/mission/promotion facts; repair queue row idempotently | evidence `flow_reconcile` |

Reconcile rules (additive to today's `reconcile()`):

1. Always run the existing promotion journal/stage reconciliation **before** touching flow rows (never undo a promotion).
2. For each `flow_runs.status IN (RUNNING, PAUSED_WAITING_APPROVAL, INTERRUPTED)` whose queue row is terminal or missing: resume the queue row forward only if durable mission facts prove the step; otherwise mark flow `BLOCKED` with evidence and leave the queue row untouched.
3. Never delete flow snapshots during recovery; prune only terminal flows.
4. No model call during reconcile.

Supervisor surfaces (C4c): `supervisor status --json` adds `flows: [{flow_id, mission_id, queue_id, status, last_method, waiting_approval}]`; `mission --show` includes the latest flow summary; CLI `supervisor approvals list|approve|deny` (see 4.7). GUI reads the same service methods (read-only status first).

### 4.7 Human-in-the-loop (HITL)

Approval points (non-LLM policy decides; the Flow only pauses):

1. risky action classification from `classify()` (WAIT_APPROVAL tokens/actions: delete/network/cloud/install/publish/migrate/external_tool);
2. assisted-mode review gates (optional per project policy);
3. oracle pinning conflicts requiring a human-reviewed baseline-test update;
4. explicit external-tool execute grants (SPEC-25) - never model-invoked.

Mechanism:

- `flows/approval_provider.py`: `GuiApprovalProvider(HumanFeedbackProvider)` with `request_feedback(context, flow)`:
  1. derive action + scope from `context.method_name` / `state.phase` / `last_error` (deterministic mapping table, no LLM);
  2. `store.create_approval(project_id, action=..., scope={"flow_id":..., "mission_id":..., "method":..., "paths":...}, reason=..., ...)` (existing store);
  3. emit `HumanFeedbackRequestedEvent` + app event + evidence `approval_requested`;
  4. raise `HumanFeedbackPending(context=context)` - the flow pauses; the supervisor records queue INTERRUPTED/WAIT_APPROVAL.
- `@human_feedback(message=..., emit=["approved","rejected","changes_requested"], default_outcome="rejected", provider=GuiApprovalProvider(...))` decorates only the gated method(s). Outcomes are matched deterministically by app code against explicit feedback values (exact/label match), **not** by an LLM collapse. If a model-based collapse is ever configured, it must be a local `ModelBinding` with permissions and is itself recorded as a model call (never for risk decisions).
- Approval resolution: `supervisor approvals approve --id N --feedback "approved: ..."` (CLI) or GUI action -> `store.decide_approval(...)` -> supervisor resume path -> `MissionFlow.from_pending(flow_id, persistence)` -> `resume(feedback)` -> load state/pending context -> resume evidence. Rejection -> mission `blocked`, live tree unchanged, approval recorded.
- Guarantees: no risky action is approved by the model or the Flow; approval expiry is handled by the store; audit records who/when/scope; feedback text size-bounded and secret-scrubbed; interactive console input is never used inside worker threads (CLI waits by exiting with a resume command and exit code WAIT_APPROVAL; GUI uses the event bus).
- `FlowInputRequestedEvent` / `Flow.ask` (conversational/manual input) are **not** used for autonomous missions; if a future GUI needs them, they map to the same approval/input-request table, not to console prompts.

### 4.8 CrewAI event -> app event/evidence mapping

`flows/events.py`: one bridge subscribing to `crewai_event_bus.on(EventType, handler)` for flow/method/HITL events (and read-only CrewAI task/tool/LLM events for metrics). It never writes mission/queue status (single writer remains supervisor/engine). Mapping:

| CrewAI event | App event (EventBus) | Durable evidence / DB | Idempotency |
|---|---|---|---|
| `FlowCreatedEvent` | `flow.created` | `flow_runs` row (if not exists) | flow_id |
| `FlowStartedEvent` | `flow.started` | mission_evidence(kind="flow", record_key="start") | flow_id |
| `MethodExecutionStartedEvent` | `flow.method.started` | no row (bounded memory only) | flow_id+method+attempt |
| `MethodExecutionFinishedEvent` | `flow.method.finished` | mission_evidence(kind="flow_method", record_key=method:attempt): duration, state_sha256, truncated output sample; `flow_runs` last_method | record_key |
| `MethodExecutionFailedEvent` | `flow.method.failed` | evidence with error class/message (bounded, no secrets); classification input | record_key |
| `FlowPausedEvent` / `HumanFeedbackRequestedEvent` | `flow.paused` | approval row + pending feedback + queue WAIT_APPROVAL | approval_id |
| `HumanFeedbackReceivedEvent` | `flow.resumed` | approval decision evidence; pending marker cleared | approval_id |
| `FlowFinishedEvent` | `flow.finished` | `flow_runs` terminal; result dict -> `classify`/`record_outcome` | flow_id |
| `FlowFailedEvent` | `flow.failed` | evidence + classify (REPAIRABLE/HARD_BLOCK/...) | flow_id |
| CrewAI `TaskStartedEvent` / `TaskCompletedEvent` inside a step | `agent.task.*` | enriched metrics only (tokens/duration/model); task_attempts remain written by the stage engine | role+task id |
| `ToolUsageStarted/Finished/Error` | `tool.usage` | evidence `tool_usage` summary (name, status, duration; no raw args by default) | attempt id |
| `LLMCallCompletedEvent` | `model.call` | usage metrics into evidence/task attempt; never prompt text | role+attempt |

Rules: correlation ids `correlation_id=supervisor owner_id` and `mission_id` on every app event; evidence payloads are bounded/truncated and hashed; no prompt bodies/diffs/secrets at default log level; duplicate event deliveries are de-duplicated by deterministic record keys (insert-once/update-if-same-hash); no raw CrewAI console listener output reaches the GUI (the bridge is the only formatting path; UTF-8 safe).

### 4.9 Storage, retention and cleanup

- Flow tables are additive and inert unless `pipeline=flow` runs. `flow_runs` is retained for audit (like mission_evidence); `flow_states` pruned to latest + last 50 per flow at terminal cleanup; `flow_pending_feedback` cleared on successful resume.
- Flow snapshots contain references/hashes only; large artifacts stay in `data/staging/<mission>/`, `data/recovery/`, `data/verification/` owned by existing retention (`core/retention.py`, stage-2 task-19) - unchanged.
- No new default CrewAI paths: a test asserts no files are created under `%LOCALAPPDATA%\CrewAI` during fake-model pipeline tests (when the dir exists, compare recursive state; skip cleanly when it does not).
- Backup/restore: one app SQLite DB already backs up missions + queue + (new) flow tables together; optional audit archives (stage-2 retention) cover recovery points, not flow snapshots.

---

## 5. Integration seams: exact signatures and file changes

### 5.1 New files

| File | Public surface (initial C4x shape) |
|---|---|
| `agents/crew_backend.py` | `class CrewRuntime(Protocol)`; `class CrewAIBackend`; `class FakeCrewRuntime`; `class AgentResult/CrewResult/FlowResult`; `crew_runtime_env() -> dict[str, str]`; `build_agent(spec, binding, tools) -> Agent`; `build_task(spec, agent) -> Task`; `build_crew(spec, agents, tasks) -> Crew` |
| `agents/specs.py` | `@dataclass(frozen=True) AgentSpec/TaskSpec/CrewSpec/MemoryPolicy/DelegationPolicy`; `ROLE_CATALOG: Mapping[str, AgentSpec]`; `get_role(role_id)` |
| `agents/mission_stage_engine.py` | `class MissionStageEngine(orchestrator)`; `run_developer(...) -> StageOutcome`; `run_tester(...) -> StageOutcome`; `run_reviewer(...) -> StageOutcome`; `promote(...) -> PromotionOutcome` |
| `models/capabilities.py` | `class CapabilityRecord`; `class CapabilityRegistry` (`get/put/list/expire`); `probe_tool_calling/probe_structured_output/probe_context_window(...)` (explicit, budgeted, local-only by default) |
| `models/model_router.py` | `class ModelBinding`; `class RouteRefused(RuntimeError)`; `class ModelRouter` (`resolve(role, *, project_id, required=frozenset(), allow_cloud=False, overrides=None) -> ModelBinding`; `build_llm(binding, project_id) -> LLM`; `snapshot(mission_id, bindings) -> dict`) |
| `flows/state.py` | `class MissionState(FlowState)`; `FlowPhase` string constants; `derive_phase(state, facts) -> str` |
| `flows/persistence.py` | `class AppFlowPersistence(FlowPersistence)` |
| `flows/mission_flow.py` | `class MissionFlow(Flow[MissionState])`; `build_mission_flow(...) -> MissionFlow`; `run_mission_flow(project_root, project_id, mission_id, *, control, models, persistence=None) -> dict` |
| `flows/supervisor_flow.py` | `class SupervisorRunFlow(Flow[SupervisorState])`; `class FlowMissionExecutor(MissionExecutor)` |
| `flows/approval_provider.py` | `class GuiApprovalProvider(HumanFeedbackProvider)`; `outcome_for_feedback(feedback, options) -> str` (deterministic) |
| `flows/events.py` | `class CrewEventBridge` (`start(mission_id, flow_id, correlation_id)/stop()`; handlers) |
| `agents/supervisor_executor.py` | `class MissionExecutor(Protocol)`; `class SequentialMissionExecutor`; (`FlowMissionExecutor` in flows/supervisor_flow.py) |

### 5.2 Modified files (additive; default behavior unchanged)

| File | Change | Risk |
|---|---|---|
| `agents/orchestrator.py` | `__init__(..., crew_runtime: CrewRuntime | None = None)`; `_call_model` delegates to `self.crew_runtime.run_agent(...)` (same seam name for tests); stage bodies moved to `MissionStageEngine` (C4a pure refactor), `run_mission` composes it identically; add `flow_id` to result payload when present | medium (refactor only; behavior tests unchanged) |
| `core/supervisor.py` | `SupervisorConfig.pipeline: str = "sequential"` + validation; `_build_executor()`; `_invoke_mission()` (replaces `_invoke_orchestrator` internally, old private alias kept); `execute_queue_item` calls executor; reconcile flow rows; status includes flows | medium |
| `persistence/supervisor_store.py` | `start_flow_run/update_flow_run/get_flow_run/list_active_flow_runs/finish_flow_run`; queue payload `flow_id` helper; approval JSON payload carries flow_id/method | low |
| `persistence/database.py` | additive migrations: 3 flow tables + indexes + `missions.flow_id` + `model_capabilities` + `mission_model_snapshots` (one idempotent entry each) | low |
| `persistence/missions.py` | `set_mission_flow(mission_id, flow_id)`; `get_mission_flow(mission_id)`; `record_model_snapshot(mission_id, role, binding)` / `get_model_snapshots(mission_id)` | low |
| `app/services.py` | `flow_status(mission_id) -> dict | None`; `project_flow_runs(project_id, limit) -> list[dict]`; `approve_flow_feedback(approval_id, decision, feedback) -> dict` (delegates to store + resume command); GUI untouched otherwise | low |
| `cli.py` | `supervisor run --pipeline {sequential,flow}`; `supervisor approvals list/approve/deny`; `supervisor status --json` includes flows; `mission --show` adds flow summary | low |
| `config/models.yaml` | optional per-role params/capability requirements (no mandatory per-project YAML; defaults in code/db) | low |
| `tests/*` | new suites (section 9) + extend `test_crewai_runtime.py` | low |

### 5.3 Human-owned flags/config keys

| Key | Default | Allowed | Owner |
|---|---|---|---|
| `supervisor.pipeline` / `--pipeline` | `sequential` | `sequential`, `flow` | human CLI/GUI/app_settings |
| `flow.persistence_backend` | `app_sqlite` | `app_sqlite` (product), `crewai_sqlite` (spike only) | human/dev |
| `flow.resume_strategy` | `durable_state` | `durable_state`, `checkpoint` only if C4a spike passes | human/dev |
| `crew.memory` | `off` | `off`, `local` (requires local embedder + explicit path) | human |
| `crew.delegation` | `off` | `off`, `readonly_allowlist` | human |
| `crew.telemetry` | `off` (env flags set) | `off`; opt-in not exposed in this stage | human only; model cannot change |
| `flow.events` | `bridge` | `bridge` (app formatting) | code |

No flag can disable staging/validation/verification/promotion gates (SPEC-28 invariant). Flags are read at mission/run boundaries, never mid-mission; a model tool cannot write them.

---

## 6. Model routing: Model Hub + permissions + capability registry

### 6.1 Current state and gap (evidence-based)

| Item | Current (HEAD) | Gap for stage 4 |
|---|---|---|
| NL-BP-008 Model Hub | `OllamaProvider` + `OpenAICompatibleProvider`, dynamic discovery, loaded state, unload; GUI off-thread | needs role routing/decision use, not only display |
| NL-BP-009 capabilities | `ModelInfo.capabilities` tuple never populated; no probes | measured vs declared vs unknown records; capability-aware refusal |
| NL-BP-010 role mapping | CLI flags + global `config/models.yaml`; GUI read-only | persisted project/global role mapping + per-mission override wins |
| NL-BP-011 snapshot | handoffs store model name only; no params/provider version snapshot | mission-level `ModelBinding` snapshot row referenced by evidence |
| permissions/cloud | `_make_llm` enforces `assert_model_permitted` (project-scoped) | flow/model router must be the single constructor so no path bypasses it |
| tool registry | read-only discovery (task-19) | use for health/advisor, never to authorize model execution |

### 6.2 Components and contracts

**Capability record** (additive table `model_capabilities`): `(provider_id, model_name, backend_version, capability, state, evidence_kind, probe_id, measured_at, hardware_fingerprint, context_limit, latency_ms, source)` where `state IN ('measured','declared','unknown','unavailable')`. Measured always wins over declared; unknown never becomes a pass. Recorded probes:

- tool calling (a scripted one-shot tool schema call; local model only unless cloud granted);
- structured output/JSON (response_model probe);
- vision/audio support (tiny fixture, explicit consent; skipped = unknown);
- context window (bounded binary search behind an explicit budget);
- latency/throughput microbench (for the advisor later).

Probes run only on explicit human action from Settings/CLI, have time/token budgets, never during a mission, never cloud without grants.

**ModelBinding** (runtime + persisted snapshot): `(role, provider_id, model_name, base_url, params{temperature, top_p, top_k, seed, max_tokens, num_ctx}, capabilities, capability_sources, source="role_config|project_override|global_override|fallback|advisor", measured_at, config_sha256)`. No secrets in the binding.

**ModelRouter** resolution order: explicit mission override -> project role mapping (app_settings/SQLite) -> global role mapping (config/models.yaml / DB) -> fallback chain (ordered, local-first); filters by `required_capabilities` and resource gate; then `assert_model_permitted(model, base_url, project_id)`; returns immutable binding or raises `RouteRefused(reason, missing_capabilities)`. `build_llm()` is the only function that constructs `crewai.LLM`; `_make_llm` is kept only as a compatibility wrapper during C4a-C4e and removed in C4e. Temperature/params are applied only when the backend/model declares support; unsupported params are dropped with a warning recorded in the snapshot (never silently faked).

**Snapshot for reproducibility (NL-BP-011):** `mission_model_snapshots(mission_id, role, binding_json, config_sha256, created_at)` written before the first model call of a mission; handoffs/evidence reference `config_sha256`; GUI/CLI show it; tests assert a mission with the fake runtime still writes the snapshot (synthetic binding) so the contract is independent of real models.

**Refusal semantics:**

- missing/unknown capability for a role that requires it -> `RouteRefused` surfaced by supervisor preflight as BLOCKED with explanation (or WAIT_APPROVAL if a human can grant/allow a different model);
- cloud/network not permitted -> `PermissionDenied` (existing), mapped to WAIT_APPROVAL by `classify`;
- model/server not reachable -> `WAIT_RESOURCE`/backoff (existing tokens);
- no silent cloud fallback, no invented success, no capability claim without a probe record.

**Advisor seam (NL-BP-068, later):** router accepts an optional `policy` object (profile Maximum Verified Quality/Balanced/Speed/Resource Saving/Custom) that is only an ordering hint over already-permitted bindings; unmeasured suggestions are labelled PROVISIONAL; user overrides always win; advisor never changes a mission mid-flight.

**Tool registry integration:** `ToolRegistry` results feed Settings -> Permissions & External Tools and (later) the advisor as environment facts; execute grants for external tools come from the approval/permission layer, not from model routing, and are never inferred from the execute capability alone. No arbitrary command execution is added anywhere in this stage.

## 7. Licensing and upgrade strategy

### 7.1 Measured facts and gaps

| Fact | Evidence | Consequence |
|---|---|---|
| `crewai==1.15.32` pinned in `pyproject.toml`; installed version is 1.15.32 | `tests/test_crewai_runtime.py` (pin + import path) | pin is enforced, but only for `crewai` itself |
| `crewai-core==1.15.32`, `crewai-cli==1.15.32` installed as separate distributions | `importlib.metadata.version` (section 12) | transitive split-distribution: pinning `crewai` does not pin `crewai-core` explicitly today; C4a should pin it too |
| installed `crewai` metadata has `License: None` and no license file in `crewai-1.15.32.dist-info` | metadata probe; dist-info listing | release-build license audit must source the upstream LICENSE (vendor checkout has the MIT text) and not rely on dist metadata |
| vendor `crewAI/LICENSE` = MIT-style, `Copyright (c) 2025 crewAI, Inc.` | file read | include notice in payload/THIRD_PARTY_NOTICES |
| notable transitive runtime: `litellm 1.100.4`, `chromadb 1.5.9`, `lancedb 0.40.0`, `pydantic 2.12.5`; `PySide6` (LGPL/GPL) | installed metadata + pyproject | SBOM + license review + payload size; model weights are separate and never bundled |
| `crewAI/` checkout is reference-only and excluded from payload; `crewAI-tools/` absent | NL-BP-001/002 evidence + `tests/test_stage_portable.py` | no duplicated vendor; no second environment |
| privacy/telemetry default is ON unless env-disabled | `crewai/telemetry/telemetry.py` + `crewai_core/telemetry` source | product must set the opt-out flags by default (section 3.4/7.6) |

### 7.2 SBOM generation and validation (C4a)

Design: `scripts/generate_sbom.py` (new, read-only, no network) builds a deterministic JSON SBOM from the **installed** distributions:

- per distribution: `name, version, license (License-Expression or License or "UNKNOWN - manual review"), home_page, requires_dist, requires_python, installer, files_hash (sha256 over sorted RECORD entries), import_root`;
- top-level: `schema_version, generated_at, python, platform, app_pin (pyproject crewai pin), import_path_evidence, unknown_licenses`;
- output: `build/phase4/sbom.json` for review and `dist/portable-release/SBOM.json` for release payloads (stage 6 packaging consumes it); build/ and dist/ are not committed as runtime code.
- validation: `scripts/check_crewai_upgrade.py --verify-sbom <path>` recomputes hashes/versions and fails on drift; the release gate compares the pin in pyproject with the SBOM entry.
- acceptance: SBOM includes `crewai` and `crewai-core` with identical versions; every `UNKNOWN@@ license is explicitly listed for human review; command exits 0 on the pinned runtime and nonzero when a version/hash is altered in a temp copy (test).

### 7.3 License obligations checklist (must be human/legal-reviewed before distribution)

1. Include MIT license texts + copyright notices for `crewai` / `crewai-core` (upstream release files, not only vendor checkout) and for other MIT/BSD deps.
2. Audit transitive licenses from the SBOM: `litellm`, `chromadb`, `lancedb`, `pydantic`, `PySide6`/Qt (LGPLv3/GPLv3 obligations: dynamic linking, notices, relinking/object-file offer as applicable), `opentelemetry`, others.
3. Model weights (Ollama models, Hugging Face checkpoints) are licensed separately and are **not** bundled; no cloud upload of sources/models without consent (SPEC-05/15).
4. Payload `THIRD_PARTY_NOTICES` generated from SBOM + curated license texts; keep in `dist/portable-release` (stage 6).
5. Do not ship `crewAI/` checkout, caches, logs, user data, DBs, or model weights (existing packaging rules).
6. Document the decision + evidence in `docs/DISTRIBUTION.md` / `docs/CREWAI_RUNTIME.md` (C4e) - this plan does not claim legal clearance.

### 7.4 Pin policy and compatibility gate

- Keep `crewai==1.15.32` pinned. Add explicit `crewai-core==1.15.32` (and, if justified, a constraints file for `litellm`) in C4a so the split distribution cannot drift independently. No range specifiers until the upgrade gate exists.
- New `tests/test_crewai_compat.py` pins the API surface the product uses (fails loudly on a version bump):
  - versions: `crewai == 1.15.32`, `crewai-core == 1.15.32`;
  - import path under site-packages, never under vendor `crewAI/`;
  - symbols: `Flow, FlowState, start, listen, router, or_, and_, persist, FlowPersistence, SQLiteFlowPersistence, human_feedback, HumanFeedbackPending, HumanFeedbackProvider, CheckpointConfig, Agent, Crew, Task, Process, LLM`;
  - events: `FlowStartedEvent, FlowFinishedEvent, FlowFailedEvent, FlowPausedEvent, MethodExecutionStartedEvent, MethodExecutionFinishedEvent, MethodExecutionFailedEvent, HumanFeedbackRequestedEvent, HumanFeedbackReceivedEvent`;
  - signatures/methods: `Flow.kickoff/resume/resume_async/from_pending/from_checkpoint`; `FlowPersistence.init_db/save_state/load_state/save_pending_feedback/load_pending_feedback/clear_pending_feedback`; `HumanFeedbackProvider.request_feedback`;
  - required pydantic fields present on `Agent/Crew/Task` (the exact names we set);
  - hermetic behaviour: a tiny fake flow with the app persistence saves/loads state; the decorator requires `state.id`; `crew_runtime_env()` contains all three telemetry opt-out flags;
  - static guards (grep): no product code calls `SQLiteFlowPersistence()` without `db_path`, no `Memory()` without explicit local config, no `memory=True` outside `crew_backend.py`, no import from `crewAI/`, no `shell=True` added by the integration.
- New `build/phase4/crewai_api_baseline.json` (generated once by the compat script, then stored as a test fixture under `tests/fixtures/crewai_api_baseline.json` so tests do not depend on build/) lists symbols/signatures; a diff is printed on upgrade.
- New `scripts/check_crewai_upgrade.py` (new, C4a; read-only, no network, no install): runs the compat subset, compares the current API surface against the baseline manifest, verifies the SBOM, prints a JSON report (status, added/removed symbols, version drift, unknown licenses), exit code 0 = compatible, 2 = drift, 3 = license gap. Used in CI/pre-release and by a human during upgrades.

### 7.5 Upgrade playbook (human-run; never autonomous)

1. Approval: user/Lead approves the upgrade and the target version.
2. Install into the embedded runtime only: `python\python.exe -m pip install crewai==<X> crewai-core==<X>` (no new venv/conda, no vendor edits). Keep the previous wheels in `build/` for rollback.
3. Run the compatibility gate + SBOM diff; review added/removed symbols and changed behaviour, especially Flow persistence/HITL/checkpoint signatures.
4. Run fake-model suites (CrewAI/Flow/supervisor) and the full offscreen suite; record counts.
5. Regenerate SBOM; review licenses/payload size (chromadb/lancedb are large).
6. Update `docs/CREWAI_RUNTIME.md` pin/evidence and `build/phase4/crewai_api_baseline.json`; commit the pin + baseline together.
7. Rollback: `python\python.exe -m pip install crewai==1.15.32 crewai-core==1.15.32` and restore the baseline/SBOM refs; re-run the gate.
8. Runtime self-update is explicitly out of scope (SPEC-27): no mission may install/replace the CrewAI runtime; the updater/bootstrap owns that path.

### 7.6 Telemetry and privacy defaults

- `crew_runtime_env()` sets `OTEL_SDK_DISABLED=1`, `CREWAI_DISABLE_TELEMETRY=1`, `CREWAI_DISABLE_TRACKING=1` in every CrewAI-executing process (in-process app and any child worker). Test asserts all three; no crew/flow is started without this env.
- No prompt/task/source content is exported by the app event bridge; evidence keeps hashes/truncated summaries only (existing privacy stance).
- Opt-in telemetry (if ever wanted) is a human setting in Settings -> Privacy, off by default, and never enabled by a model or a mission.
- Cloud model usage remains governed by `permissions.assert_model_permitted` + explicit grants; telemetry being off does not replace the cloud gate.

### 7.7 Version-risk watchlist (why the gate matters)

The APIs this design relies on are recent and evolving in 1.15.x: conversational Flow fields, async human-feedback providers/pending context, checkpoint configuration, event-type names, `crewai-core` split. A minor upgrade may rename or re-shape them. Mitigations: adapter layer (`CrewRuntime`, `AppFlowPersistence`, `GuiApprovalProvider`), compat test + baseline manifest, pinned versions, SBOM, and staged rollout flags.

---

## 8. Migration and feature-flag plan

### 8.1 Prerequisites / stage gating

- Program rule (INDEX.json program_order): stage 4 may start only when stage 3 gates pass or the Lead records an evidence-backed exception. Stage 3 is **in progress** at HEAD e81a916 (SH-07 Tier B real-local-model evidence not executed). This design is planning-only; C4a implementation should wait for the stage-3 gate, or be treated as a low-risk independent exception with the Lead explicit decision.
- Before first deployment of the additive migrations: back up the app SQLite (same operational note as C5). Migrations are additive and idempotent; tests run on copies/temp dirs, never the live DB.
- No autonomous runs during any C4 commit; fake-model tests only.

### 8.2 Rollout phases

| Phase | Flag state | What runs | Evidence gate |
|---|---|---|---|
| C4a | all new flags absent/off; sequential executor unchanged | crew backend + router + stage-engine extraction; Flow not wired | existing suites green; compat/SBOM tests green |
| C4b | `supervisor.pipeline=sequential` (default); Flow module exists but is unreachable from the supervisor | MissionFlow unit/integration tests with fake runtime; app persistence tests | Flow state/persistence/resume tests green |
| C4c | `supervisor.pipeline=sequential` default; `flow` opt-in via CLI/app_settings (human) | both executors available; flow tested with fake models + parity vs sequential | fake-model flow mission + crash/resume + supervisor tests green |
| C4d | HITL flags off by default; memory/delegation off; capability-aware routing on for refusal semantics | approvals/HITL tests; capability refusal; memory policy tests | HITL/approval/memory tests green |
| C4e | default decision recorded; defaults may become `pipeline=flow` only if all gates pass; otherwise sequential stays default and flow remains opt-in | documentation, SBOM, final acceptance | fake-model full suite + status smoke + human-reviewed decision |

Rollout rule: a flag is read at mission/run boundaries only. No mission may run half sequential and half flow.

### 8.3 Data migration

- Additive only: `flow_states`, `flow_pending_feedback`, `flow_runs`, `missions.flow_id`, `model_capabilities`, `mission_model_snapshots`. No backfill, no rewrite of existing rows/DB files.
- Existing missions/queue rows have `flow_id NULL` and remain sequential; they are never resumed by the flow executor (the executor selection is per queue row/new mission).
- Queue payloads gain optional `flow_id`; older rows without it are handled by the sequential path.
- State-schema: `MissionState.schema_version` is checked; a newer version blocks instead of guessing.
- Rollback: set the flag off; new missions use sequential; in-flight flow missions are finished by the flow executor (flag read at start) or marked interrupted with evidence and resumed later; flow tables remain inert (no drop) and can be pruned by the standard retention job.

### 8.4 Contract parity between executors

`SequentialMissionExecutor` and `FlowMissionExecutor` must return the same result dict contract (status, mission_id, promotion_status, changed_paths, diff_stat, verdict, review, error, verification_runs, handoffs). Tests assert parity on: happy path, stub candidate, reviewer REJECT, stop_after developer/tester, legacy mission refusal, promotion CAS conflict, repair success and repair-budget exhaustion (reuse the stage-2 fake-model scenarios). Classification (`Supervisor.classify`) and `record_outcome` are unchanged and covered by both.

### 8.5 No dual-run invariant

Never run the flow executor and the sequential orchestrator for the same mission. The executor is selected once per mission by `Supervisor._build_executor()` and the choice is recorded in mission evidence/queue payload. A test asserts exactly one executor instance and no duplicate developer/reviewer calls for a mission.

---

## 9. Test strategy with fake models (no network)

### 9.1 Principles

1. **No Ollama, no cloud, no CrewAI network path**: every model call goes through `FakeCrewRuntime` (production path) or `_call_model` monkeypatch (existing tests). An autouse fixture replaces `_make_llm` with a loud failure, as `tests/test_orchestrator_staging.py` already does.
2. **Telemetry/storage containment asserted**, not assumed: env builder test, no-network guard (e.g. monkeypatch `urllib.request.urlopen`/socket connect to raise in new suites where applicable), and a test that no new files appear under `%LOCALAPPDATA%\CrewAI`.
3. **Isolated app data**: `NL_DATA_DIR` temp dir per test (existing fixture pattern); temp demo project whose staged copy can run real candidate/oracle suites (same tiny project as `test_orchestrator_staging.py`); tests never touch the live DB or live tree.
4. **Real gates stay real where cheap**: mission-flow tests use the real promotion/verification machinery on the tiny project (no LLM), like the existing 8 staging tests (~1-2 s each). Fake only the LLM and (where needed) the subprocess verification for pure state-machine tests.
5. **Deterministic**: fixed ids/uuids injected where needed, no sleeps/wall-clock assertions beyond generous bounds, no retries that hide flakiness.
6. **Test the adversarial path**: crash windows, human edit during review, approval denial, capability refusal, memory disabled, telemetry off, stop/pause at every boundary.
7. **No autonomous/self-build runs** and no full real-model evidence in automated tests; Tier B stays a separately gated human-run acceptance (stage 3 carry-over).

### 9.2 Test matrix

| File | Layer | Fake seam | Key assertions |
|---|---|---|---|
| `tests/test_crew_backend.py` | crew backend | FakeCrewRuntime; monkeypatched Agent/Crew constructors | Agent/Task/Crew built from specs with 4 tools max; no shell/test tool; delegation off; env flags; memory off; exception mapping |
| `tests/test_crewai_compat.py` | dependency | none (real installed package) | pins/symbols/signatures/fields/behaviour/env; no vendor import; static guards |
| `tests/test_crewai_runtime.py` (extend) | dependency | none | existing pin/path test stays; add `crewai-core` pin |
| `tests/test_model_router.py` | routing | fake ModelHub/inventory; fake permissions | local-first order; override precedence; required capability refusal; cloud/network -> PermissionDenied; snapshot persisted (NL-BP-011); no LLM constructed in dry resolve |
| `tests/test_model_capabilities.py` | capabilities | fake probe transports | measured/declared/unknown states; unknown never passes; probe budget/timeout; registry persistence |
| `tests/test_flow_state.py` | state | none | schema fields; derive_phase matrix; schema_version guard; size guard; no secrets fields |
| `tests/test_flow_persistence.py` | persistence | temp NL_DATA_DIR | init idempotent; save/load latest; sha256; pending feedback roundtrip; prune; flow_runs upsert; no default CrewAI path writes |
| `tests/test_mission_flow.py` | Flow pipeline | FakeCrewRuntime + real gates on demo project | happy path one promotion; stub/reject/stop-after scenarios; verification rows; result contract parity |
| `tests/test_flow_resume.py` | resume | FakeCrewRuntime with crash hooks | each crash-window row of section 4.5; no repeated model call; one promotion; pinned flow id; stale state -> facts win/blocked |
| `tests/test_supervisor_flow.py` | supervisor integration | fake runtime + fake executor hooks | queue RUNNING -> flow; classify parity; crash/reconcile; no duplicate executor; evidence/flow_runs mapping; WAIT_APPROVAL pause/resume |
| `tests/test_flow_human_feedback.py` | HITL | fake GuiApprovalProvider / fake bus | pending -> approval row + queue WAIT_APPROVAL; resume feedback; reject -> blocked live unchanged; expiry; deterministic outcomes (no LLM collapse) |
| `tests/test_flow_memory_policy.py` | memory/delegation | fake Memory; env checks | memory off by default; local-only config required; no cloud LLM/OpenAI embedder; explicit path under NL_DATA_DIR; delegation denied for write roles |
| `tests/test_flow_events_evidence.py` | events/evidence | fake event bus emissions | mapping table rows; correlation ids; dedupe; bounded payloads; no prompt text; UTF-8 no crash |
| `tests/test_supervisor_sh07.py` (extend) | acceptance | fake runtime, `pipeline=flow` param | two consecutive missions through Flow; live tree correct; resume across restart |
| `tests/test_supervisor_cli.py` / `test_services` (extend) | surfaces | patched store/supervisor | `--pipeline` flag; approvals list/approve/deny; status includes flows; read-only service methods |

### 9.3 Fixtures

- `app_data`: temp `NL_DATA_DIR`, `database.init_db().close()` (existing pattern).
- `demo_project`: tiny `src/calc.py` + `tests/test_calc.py` + `nl_coding_agent/__init__.py` (same as staging tests) so real candidate/oracle verification runs offline.
- `fake_runtime`: scripted per role/flow method + call log + hooks (raise at chosen boundary for crash tests).
- `fake_flow_persistence`: in-memory `FlowPersistence` for pure state tests when DB is not the subject.
- `fake_approval_provider`: persists an approval then raises `HumanFeedbackPending`.
- `no_llm` autouse: `_make_llm` -> AssertionError; `crewai.LLM` constructor guard; optional no-network guard.
- `telemetry_env` assertions helper shared across suites.

### 9.4 Crash/resume test method

In a test: install a fake runtime hook that raises (or stops the control) immediately after a chosen `@persist` method completes; assert persisted state/flow row; discard the flow instance; construct a new `MissionFlow(persistence=AppFlowPersistence())` and kickoff with the pinned flow id; assert (a) the completed step did not call the model again (call log), (b) durable rows unchanged (no duplicate attempts/verification/promotion), (c) final status equals the uninterrupted baseline. Repeat for every row of the crash-window table. Promotion-crash cases reuse the stage-2 journal/CAS tests rather than re-implementing them.

### 9.5 Evidence and limitations

- Automated evidence is fake-model only. A real local-model assisted run (stage 3 SH-07 Tier B carry-over + one flow mission) is a **separate human-gated acceptance**; this plan does not claim it.
- No full-suite count is promised for architecture that does not exist yet; each commit records its actual counts, and the final acceptance target remains "full offscreen suite green" (the current baseline is 215+; exact final number recorded at C4e).
- Performance budget (indicative): new Flow fake-model suites < 60 s combined on the reference machine; per-mission flow test reuses the tiny project and stays in the same range as `test_orchestrator_staging.py` (~1-2 s/mission).

---

## 10. Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation / verification | Commit |
|---|---|---|---|---|---|
| R1 | Stage-3 gate not passed; starting stage 4 early violates program order | high (current state) | medium | design only now; C4a waits or Lead records exception; no autonomous runs | C4a |
| R2 | Flow resume semantics misunderstood (restore != skip) | medium | high | resume-by-durable-state primary; smoke proven fork semantics documented; crash tests per window; checkpointing optional spike only | C4b |
| R3 | Checkpoint API differs/unstable | medium | medium | not depended on; spike must pass 3 criteria before any use; documented as unsupported otherwise | C4a/C4b |
| R4 | HITL provider/async feedback semantics differ from docs | medium | high | C4d spike; deterministic outcomes; pending-feedback table; no LLM collapse for risk; tests fake provider | C4d |
| R5 | Flow state and supervisor/queue state diverge (double source of truth) | medium | high | supervisor is source of truth; flow state references+hashes; reconcile from durable facts; parity tests; no dual-run invariant | C4b/C4c |
| R6 | CrewAI default storage/telemetry writes leak outside app data / send network | medium | high | explicit persistence path; env opt-out flags; containment tests; static guards; SBOM/upgrade gate | C4a |
| R7 | Memory defaults use cloud LLM/OpenAI embedder | high if enabled | high | memory off by default; explicit local-only policy; tests; docs limitation | C4d |
| R8 | Windows charmap/console emoji errors from CrewAI listeners (observed) | high | low/medium | app-only event bridge; force UTF-8 env; no raw CrewAI console formatting; test with emoji event text | C4a/C4c |
| R9 | Windows SQLite lock leaks / cleanup errors | medium | low | app persistence closes connections per call; tests use lazy tmp cleanup; document bundled-backend caveat | C4b |
| R10 | Refactor of orchestrator introduces behavior drift | medium | high | C4a pure extraction; staging/seam/repair tests + full suite unchanged; no gate logic changes | C4a |
| R11 | Capability registry/route refusals block legitimate local models | medium | medium | declared fallback with explicit human override; PROVISIONAL labels; refusal has actionable reason; tests | C4d |
| R12 | License metadata gap (dist License None) / payload size (chromadb, lancedb) | high | medium/high | SBOM + human license review; size measured for stage 6 packaging; exclude models/vendor; document | C4a/C4e |
| R13 | Event bus global singletons/handler leaks across tests/missions | medium | medium | bridge start/stop per mission; unsubscribe; tests assert no cross-mission events; no telemetry listener output in app | C4a/C4c |
| R14 | Flow state schema evolution breaks resume | medium | high | schema_version guard (block, never guess); additive migrations; state minimal; upgrade gate | C4b |
| R15 | Approval bypass via Flow input or model-suggested action | low | critical | approval creation only in policy code; hashed/allowlisted actions; no model tool writes approvals/flags; SH-05 surface unchanged; adversarial tests | C4d |
| R16 | Stage-2 safety harness weakened by integration | low | critical | stage engine unchanged; promotion last; staging tests/verification oracle untouched; no new model tools; static greps | all |
| R17 | Real-model evidence not automated; false confidence | high | medium | explicitly separate Tier B human-gated acceptance; docs state limitation; no overclaiming in acceptance | C4e |
| R18 | Scope creep into GUI/multimodal/voice stage-4 requirements | high | medium | this plan covers CrewAI/model items only; UI consumes read-only service APIs in later tasks | all |

---

## 11. Commit order C4a-C4e and acceptance commands

Common environment for every acceptance command (repository root, offscreen, no bytecode, no pytest cache):

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:OTEL_SDK_DISABLED='1'; $env:CREWAI_DISABLE_TELEMETRY='1'; $env:CREWAI_DISABLE_TRACKING='1'
```

Common rules: no commit until targeted + full offscreen suite green; no autonomous/self-build run; no live-DB writes (tests use `NL_DATA_DIR` temp dirs); DB backup before first run of additive migrations on the real DB; each commit is revert-safe and leaves default behavior = current sequential pipeline.

### C4a - CrewAI backend foundation, stage-engine extraction, routing/capability skeleton, SBOM/compat gate

Files: `agents/crew_backend.py`, `agents/specs.py`, `agents/mission_stage_engine.py`, `agents/supervisor_executor.py` (protocol + sequential), `models/model_router.py`, `models/capabilities.py` (skeleton), `persistence/database.py` (additive `mission_model_snapshots`/`model_capabilities` only), `persistence/missions.py`, `pyproject.toml` (crewai-core pin), `tests/test_crew_backend.py`, `tests/test_crewai_compat.py`, `tests/fixtures/crewai_api_baseline.json`, `scripts/check_crewai_upgrade.py`, `scripts/generate_sbom.py`, extend `tests/test_crewai_runtime.py`.

Steps: (1) extract stage engine as a pure refactor, orchestrator composes it unchanged; (2) add `CrewRuntime` protocol + `CrewAIBackend` + `FakeCrewRuntime` and switch `_call_model` to it (default backend = CrewAI, same output); (3) `crew_runtime_env()` telemetry/UTF-8 env; (4) role catalog moving prompt text verbatim; (5) router resolving from ModelHub/config with permission gate + binding snapshot (no behavior change for default models); (6) compat test/baseline + SBOM script; (7) optional checkpoint spike note (temp-only, no production path).

Acceptance commands (run from the repository root; full suite + compat/SBOM gate are mandatory before committing):

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
$env:OTEL_SDK_DISABLED='1'; $env:CREWAI_DISABLE_TELEMETRY='1'; $env:CREWAI_DISABLE_TRACKING='1'
python\python.exe -m pytest -q tests/test_crew_backend.py tests/test_crewai_compat.py tests/test_crewai_runtime.py -p no:cacheprovider
python\python.exe scripts\check_crewai_upgrade.py --compat --sbom build\phase4\sbom.json
python\python.exe -m pytest -q tests -p no:cacheprovider
```

### C4b - Flow state, app persistence, MissionFlow skeleton/resume

Files: `flows/__init__.py`, `flows/state.py`, `flows/persistence.py`, `flows/mission_flow.py`, `flows/events.py`, `persistence/database.py` (3 flow tables + missions.flow_id + migration), `persistence/missions.py` (`set_mission_flow/get_mission_flow`), `persistence/supervisor_store.py` (flow_runs helpers), tests `test_flow_state.py`, `test_flow_persistence.py`, `test_mission_flow.py`, `test_flow_resume.py`, `test_flow_events_evidence.py`.

Steps: additive migrations; `AppFlowPersistence` full interface; `MissionState` + derive_phase; MissionFlow methods with durable-fact guards; pinned-id resume; event bridge (no status writes); flags absent (module unreachable from supervisor). 

### C4c - Supervisor Flow executor, CLI/service surfaces, parity and crash/reconcile tests

Files: `core/supervisor.py` (`pipeline` config, `_build_executor/ _invoke_mission`, reconcile/status), `flows/supervisor_flow.py`, `agents/supervisor_executor.py` (complete), `cli.py` (`--pipeline`, status), `app/services.py` (flow status), tests `test_supervisor_flow.py`, extend `test_supervisor_sh07.py`/`test_supervisor_cli.py`, parity scenarios reused from stage-2 tests.

Acceptance: flow executor fake-model happy/stub/reject/stop-after/repair/budget parity; crash across supervisor restart; reconcile idempotent; single executor invariant; default remains sequential.

### C4d - HITL approvals, memory/delegation policy, capability-aware routing/evidence

Files: `flows/approval_provider.py`, `core/supervisor.py` (resume path/approval mapping), `app/services.py` + `cli.py` (`supervisor approvals list|approve|deny`), `models/capabilities.py` + `models/model_router.py` refinements (capability filters/refusals), `agents/crew_backend.py` (memory/delegation policy), `persistence/supervisor_store.py` (approval flow link), tests `test_flow_human_feedback.py`, `test_flow_memory_policy.py`, `test_model_capabilities.py`, `test_model_router.py`.

Acceptance: pending feedback -> approval row + WAIT_APPROVAL; approve resumes and continues; deny -> blocked/live unchanged; approval expiry; deterministic outcome matching; memory never enabled by default/cloud; capability refusal before mission start; no telemetry network.

### C4e - Acceptance, docs, SBOM artifact and rollout decision

Files: `docs/CREWAI_RUNTIME.md` (pin/upgrade/telemetry/storage evidence), `docs/CURRENT_STATE.md`, `docs/07_SAFETY.md` (Flow pipeline + HITL + limitations), `docs/HARNESS_ACCEPTANCE.md` (stage-4 evidence), `docs/PRODUCT_BACKLOG.md` + `docs/product-blueprint/INDEX.json` status updates for NL-BP-006/007/009/010/011 (human-reviewed), `build/phase4/sbom.json` (artifact), acceptance evidence log.

Acceptance: full fake-model suite green; SBOM verified; status smoke read-only; default flag decision recorded (flow default only if all gates green; otherwise sequential stays default); no real-model/autonomous run claim.

### Consolidated acceptance commands (run at each gate; adjust file lists to the commit)

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
$env:OTEL_SDK_DISABLED='1'; $env:CREWAI_DISABLE_TELEMETRY='1'; $env:CREWAI_DISABLE_TRACKING='1'

# C4a
python\python.exe -m pytest -q tests/test_crew_backend.py tests/test_crewai_compat.py tests/test_crewai_runtime.py -p no:cacheprovider
python\python.exe scripts\check_crewai_upgrade.py --compat --sbom build\phase4\sbom.json
python\python.exe -m pytest -q tests -p no:cacheprovider

# C4b
python\python.exe -m pytest -q tests/test_flow_state.py tests/test_flow_persistence.py tests/test_mission_flow.py tests/test_flow_resume.py tests/test_flow_events_evidence.py -p no:cacheprovider
python\python.exe -m pytest -q tests -p no:cacheprovider

# C4c
python\python.exe -m pytest -q tests/test_supervisor_flow.py tests/test_supervisor_sh07.py tests/test_supervisor_cli.py tests/test_orchestrator_staging.py tests/test_promotion_stage.py -p no:cacheprovider
python\python.exe -m pytest -q tests -p no:cacheprovider

# C4d
python\python.exe -m pytest -q tests/test_flow_human_feedback.py tests/test_flow_memory_policy.py tests/test_model_capabilities.py tests/test_model_router.py tests/test_supervisor_approvals.py -p no:cacheprovider
python\python.exe -m pytest -q tests -p no:cacheprovider

# C4e (final, read-only smoke)
python\python.exe -m pytest -q tests -p no:cacheprovider
python\python.exe scripts\check_crewai_upgrade.py --verify-sbom build\phase4\sbom.json
python\python.exe scripts\verify_supervisor.py
python\python.exe scripts\verify_relocation.py --json
python\python.exe nl_agent.py supervisor status --project . --json
python\python.exe nl_agent.py supervisor run --help
```
Note: `tests/test_supervisor_approvals.py` is listed for C4d; if the approvals tests are folded into existing supervisor suites at implementation time, update the command list in the same commit. All pytest commands are fake-model/offscreen; none starts an autonomous mission or touches the live DB.

---

## 12. Evidence appendix (read-only measurements)

### 12.1 Commands executed and observed facts

1. Version/paths:
   `python\python.exe -c "import crewai; print(crewai.__version__); print(crewai.__file__)"` -> `1.15.32`, `K:\AI\NL Coding Agent\python\Lib\site-packages\crewai\__init__.py`.
2. Distribution versions (`importlib.metadata`): `crewai 1.15.32`, `crewai-core 1.15.32`, `crewai-cli 1.15.32`, `litellm 1.100.4`, `chromadb 1.5.9`, `lancedb 0.40.0`, `pydantic 2.12.5`, `pytest 9.2.0`; `crewai` metadata `License: None`; no license file in `crewai-1.15.32.dist-info`.
3. Flow API introspection: fields/methods listed in section 2.3; `FlowState` fields = `['id']`; flow exports include `Flow, start, listen, router, or_, and_, persist, persistence, human_feedback, HumanFeedbackPending, HumanFeedbackProvider, CheckpointConfig`.
4. Persistence API introspection: `persist(persistence=None, verbose=False)`; `FlowPersistence` methods; `SQLiteFlowPersistence(db_path=None)`; default `db_path` measured as `C:\Users\<user>\AppData\Local\CrewAI\<project>\flow_states.db` via `default_flow_persistence()`.
5. Checkpoint API introspection: `CheckpointConfig` fields `[location, on_events, provider, max_checkpoints, restore_from]`; module `crewai.state.checkpoint_config`.
6. HITL introspection: `human_feedback(message, emit, llm, default_outcome, metadata, provider, learn, learn_source, learn_strict)`; `HumanFeedbackProvider`/`HumanFeedbackPending` import from `crewai.flow.async_feedback`/`crewai.flow`.
7. Event types introspection: `crewai.events.types.flow_events` list in section 2.3; bus methods `on/off/emit/aemit`.
8. Telemetry source read: `Telemetry.__init__` returns early when `_is_telemetry_disabled()`; that method checks `OTEL_SDK_DISABLED`, `CREWAI_DISABLE_TELEMETRY`, `CREWAI_DISABLE_TRACKING`; exporter endpoint `https://telemetry.crewai.com:4319`.
9. Memory source read: `Memory` defaults `llm='gpt-5.4-mini'`, `embedder=None` -> default OpenAI embedder, storage LanceDB under `db_storage_path()/memory` when no path/env.
10. Storage path source read: `crewai_core.paths.db_storage_path()` uses appdirs user data dir (author `CrewAI`), directory created on call; project dir from `CREWAI_STORAGE_DIR` or `Path.cwd().name`.
11. Flow smoke (temp dir, no LLM): `@persist` saved `begin:counter=1` and `finish:counter=2`; `kickoff(restore_from_state_id=<id>)` restored state with a new id and re-ran both methods (counter 4) -> fork-from-state semantics documented; CrewAI event listener emitted Windows charmap errors for emoji; temp DB locked at interpreter exit by the bundled persistence.
12. Vendor/runtime: `crewAI/LICENSE` MIT Copyright (c) 2025 crewAI, Inc.; `tests/test_crewai_runtime.py` asserts version/path; `crewAI-tools/` absent.
13. Current seams verified by reading `agents/orchestrator.py` (1426 lines) and `core/supervisor.py` (1845 lines): signatures listed in section 2.2.
14. Repo hygiene: this design task wrote only `build/phase4/CREWAI_FLOWS_PLAN.md` (git-ignored build output) and made no tracked-file edits, no code changes and no autonomous/self-build runs; the repository working tree may contain unrelated concurrent work from other tasks, which this design does not touch; the live app SQLite main file was not modified by this task (only read-only metadata probes of the embedded runtime were needed).

### 12.2 Open questions to verify in C4a/C4b spikes (not assumed above)

1. Does `Flow.from_checkpoint`/`CheckpointConfig` resume completed methods without repeating, with an app-owned local provider and no default storage writes? (If yes, it may be offered as `flow.resume_strategy=checkpoint` in a later commit; if no, durable-state resume stands alone.)
2. Exact payload shapes of flow/method/human-feedback events across the installed 1.15.32 (bridge must be tolerant and tested against fake emissions at minimum; a temp real-flow smoke in C4b can confirm).
3. `HumanFeedbackProvider` async contract (what the engine expects from `request_feedback` timing/return) and whether `Flow.from_pending` restores everything needed for `resume(feedback)` in-process.
4. Local embedder options/config for `Memory` (none tested here; until verified, memory stays off).
5. Whether `crewai-core` should be a direct dependency pin (design recommends yes) and its license text source.
6. Windows cleanup behaviour for app-owned flow persistence (connection lifecycle) and whether pytest tmp cleanup needs a retry hook.
7. `Flow.ask` / conversational Flow features are not needed for autonomous missions; confirm they stay disabled/absent from product flows.

### 12.3 Requirement -> design -> acceptance mapping

| Requirement | Design section | Acceptance evidence target (fake-model) |
|---|---|---|
| NL-BP-001 pinned native runtime | 2.1, 7.4 | `test_crewai_runtime.py` + `test_crewai_compat.py` pins/paths |
| NL-BP-002 vendor excluded, no vendor import | 3.4, 7.4 | existing staging/runtime tests + compat static guard |
| NL-BP-006 first-class Flows in a production pipeline | 4.1-4.6, 11 (C4b/C4c) | `test_mission_flow.py` + `test_supervisor_flow.py` (real Flow, real gates, fake model) |
| NL-BP-007 durable Flow mission pipeline + crash resume | 4.4-4.6, 8 | `test_flow_persistence.py`, `test_flow_resume.py` crash-window matrix, supervisor reconcile test |
| NL-BP-008 Model Hub as routing source | 6.2 | `test_model_router.py` (local-first, overrides, unload-agnostic) |
| NL-BP-009 capability registry (measured/declared/unknown) | 6.2 | `test_model_capabilities.py` refusal semantics |
| NL-BP-010 role->model mapping without YAML ceremony | 6.2, 5.3 | router override precedence tests + app_settings persistence test |
| NL-BP-011 mission config snapshot | 6.2 | `mission_model_snapshots` roundtrip test, referenced by handoff/evidence |
| NL-BP-013 unicode hardening incl CrewAI events | 3.4, 9.2 | env builder test + emoji event bridge test (observed charmap source) |

### 12.4 Non-goals (explicitly out of this plan)

- No GUI redesign, multimodal chat, voice/ASR, editor/terminal/LSP work (other stage-4 tasks).
- No Model Advisor full implementation (NL-BP-068 later); only the routing/advisory seam.
- No parallel missions/team optimization (NL-BP-066/067 later).
- No cloud activation, telemetry opt-in UI, or model/plugin installation.
- No vendor checkout modification, no second environment, no autonomous self-build run, no real-model evidence claims.
- No change to staged-candidate gates, promotion ordering, or the four-tool model surface.

---

**Deliverable:** this file only (`build/phase4/CREWAI_FLOWS_PLAN.md`). No tracked-file edits; no code; no autonomous runs.



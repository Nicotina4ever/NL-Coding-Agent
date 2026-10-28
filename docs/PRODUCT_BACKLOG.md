# Product Backlog - NL Coding Agent (canonical, deduplicated, indexed)

**Version 1.0 - 2026-10-28.** This is the single persistent product backlog and long-term specification for NL Coding Agent. It consolidates the Master Blueprint (docs/product-blueprint/**), the previous state/history documents and the final-product requirements into atomic, evidence-based requirements grouped by product area.

> **Supersedes:** the previous docs/PRODUCT_BACKLOG.md (22-line mission #42 attempt), 03_MASTER_CHECKLIST.md as a de-facto backlog, and every duplicate requirement list in the Blueprint. It does **not** supersede the Blueprint specifications (design authority), AGENTS.md (workspace rules) or SQLite/docs history (evidence).

**Machine-readable:** [docs/product-blueprint/INDEX.json](product-blueprint/INDEX.json) - **One-line index:** [docs/BLUEPRINT_INDEX.md](BLUEPRINT_INDEX.md) - **Audit:** [build/backlog/AUDIT.md](../build/backlog/AUDIT.md).

**Snapshot:** 2026-10-28 16:12 Europe/Rome - git HEAD 7e778da (clean at snapshot; only the backlog deliverables untracked/modified) - Python 3.12.10 (python/python.exe) - measured pytest --collect-only = **134 tests collected** (full suite not run by this consolidation; see [NL-BP-150](#nl-bp-150)). Phase 2 (task-6) was being implemented concurrently: C1a/C1b/C2/C3/C4/C5 landed during consolidation; C6 (orchestrator staging wiring) and C7 remain pending at this snapshot.

## How to use this backlog

1. **Pick from the top, not from chat.** Execute only requirements that are READY (all dependencies done). P0 first, then P1; a single active requirement/milestone at a time unless write scopes are disjoint.
2. **Status changes require evidence.** planned -> partial needs implemented code + evidence pointer; partial -> verified needs a named test or a measured command (file + test name, or command + result + date). Agent reports, checklists and claims are never evidence.
3. **Never overwrite this file from an agent session.** Update only the Status, Evidence and Note fields of the affected entry; keep IDs, acceptance gates and dependencies stable. If scope changes, add a new PROPOSED requirement with the next free ID in its area and record the rationale.
4. **Use the Blueprint on demand, not wholesale.** The supervisor/agent reads this entry (plus its source spec) and verifies against the actual code; it must not load the whole corpus into the model context.
5. **A mission is complete only when its acceptance gates pass**, independently verified; reviewer=APPROVE or a green suite alone are not sufficient (see NL-BP-054/058/060).
6. **No destructive action** (delete/move/migrate/cleanup/publish/install) without explicit user authorization, and never as part of a normal coding mission.

### Status vocabulary

- verified - implemented AND proven in this repository by a named test, a measured command, or both recorded in Evidence.
- partial - implemented or usable but unverified, limited, or missing acceptance evidence (e.g. components exist but are not wired).
- planned - specified but absent, or only a static placeholder exists.
- blocked - the acceptance depends on an incomplete earlier phase/integration; no amount of local work on it alone can make it pass.

### Priority semantics

- P0 - release-blocking: required by the final release acceptance criteria (area 6) or a hard safety/prerequisite gate. Do not ship without it.
- P1 - required for a coherent, useful final product; can run in parallel once P0 foundations land.
- P2 - advanced evolution planned by the Master Blueprint; after the core release.
- P3 - polish / optional distribution extras and long-term maintenance.

## Program execution order (authoritative)

This order is authoritative for sequencing the whole program. It does not create new
requirement IDs: every NL-BP requirement below is mapped to exactly one stage
(machine-readable in docs/product-blueprint/INDEX.json as program_order and
program_stage), and dependencies between requirements are refined from repository
evidence only.

| Stage | Name | Status | Requirements | IDs | Depends on |
|---|---|---|---|---|---|
| 1 | Repository relocation and path reconciliation | COMPLETE | 1 | NL-BP-143 | - |
| 2 | Transactional staging, safety and self-healing | COMPLETE | 15 | NL-BP-3-5, 54-60, 65, 72-74, 76 | 1 |
| 3 | Persistent autonomous supervisor and verified handoff | COMPLETE (Tier B blocked evidence) | 13 | NL-BP-12, 50-53, 61-64, 66, 67, 75, 77 | 2 |
| 4 | Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities | COMPLETE | 40 | NL-BP-1, 2, 6-11, 13, 20-46, 68-71 | 3 |
| 5 | Repository cleanup and optimization | COMPLETE | 8 | NL-BP-90-97 | 4 |
| 6 | Lightweight portable/bootstrapper and final release testing | IN PROGRESS |  40 | NL-BP-110-124, 140-142, 144-151 | 5 |

Execution rule: a later stage starts only when the previous stage's gates pass, unless the
Lead records an explicit evidence-backed exception for independent low-risk work. Stage 1 is
complete (verified relocation: see docs/WORKSPACE_MIGRATION.md); Stage 2 is complete (verified
harness C1-C9b, permissions/tool registry, SH-06); Stage 3 is in progress: the persistent
supervisor core/CLI/service/GUI (C3a-C3d) and SH-07 Tier A (fake model) are implemented, while
SH-07 Tier B (real local models) remains pending explicit authorization and blocks NL-BP-063.

## Summary

| Status | P0 | P1 | P2 | P3 | Total |
|---|---|---|---|---|---|
| verified | 19 | 10 | 0 | 0 | 29 |
| partial | 17 | 24 | 9 | 0 | 50 |
| planned | 17 | 9 | 7 | 2 | 35 |
| blocked | 3 | 0 | 0 | 0 | 3 |
| **Total** | 56 | 43 | 16 | 2 | 117 |

| Area | Requirements | verified | partial | planned | blocked |
|---|---|---|---|---|---|
| Area 1 - CrewAI + CrewAI Flows first-class integration | 13 | 6 | 7 | 0 | 0 |
| Area 2 - Studio GUI + multimodal chat | 27 | 1 | 7 | 19 | 0 |
| Area 3 - Universal autonomous development | 28 | 16 | 6 | 5 | 1 |
| Area 4 - Repository hygiene | 8 | 2 | 4 | 2 | 0 |
| Area 5 - Lightweight installation + portable distribution | 15 | 2 | 5 | 8 | 0 |
| Area 6 - Release acceptance criteria | 12 | 0 | 5 | 4 | 3 |

### Area ownership

| Area | Shared task | Description |
|---|---|---|
| Area 1 - CrewAI + CrewAI Flows first-class integration | `task-9` | CrewAI as a first-class engine dependency (not a cloned vendor checkout), agent/task/crew execution with verified gates, and complete CrewAI Flows integration for product workflows. |
| Area 2 - Studio GUI + multimodal chat | `task-10` | Professional NL-branded Studio shell; multimodal mission chat (drag-and-drop, Ctrl+V screenshots, attachments), media/ASR/TTS backends, IDE tools (editor/terminal/Git/tests/debug/LSP/MCP), accessibility and non-blocking UX. |
| Area 3 - Universal autonomous development | `task-11` | Persistent goals/milestones/tasks/missions, dynamic teams, model competence evidence, resource scheduling, permissions/tool registry, supervised execution on arbitrary projects, independent gates, staged changes, safe rollback; the indexed blueprint is the durable specification. |
| Area 4 - Repository hygiene | `task-12` | Read-only audits, removal of duplicate/generated/obsolete artifacts, consolidated build outputs, one verified candidate, no destructive action without explicit authorization. |
| Area 5 - Lightweight installation + portable distribution | `task-13` | Online native bootstrapper, private runtimes into a user-selected location, no global Python/pip/uv/conda, optional components and offline packages, repair/update/cache management, shared downloads without isolation loss, Windows/Linux/macOS verified builds. |
| Area 6 - Release acceptance criteria | `task-14` | Evidence gates for the final product: non-default install path; clean Windows without global Python; relocation survival; clipboard screenshot + drag-and-drop attachments; mic + local transcription; CrewAI workflows and autonomous missions execute; invalid agent edits cannot corrupt verified sources; local model discovery + evidence-based selection; reproducible organized builds. |

## Changelog

**v3.0 (2026-10-28)** - Cross-platform private beta program added to the persistent backlog: NL-BP-152..165 (14 requirements) cover the Windows x64/ARM64, Linux x86_64/ARM64 and macOS Intel/Apple Silicon compatibility audit/matrix, platform abstraction and unsupported-config handling, native verified runtime manifests (never reusing Windows runtime on Linux/macOS), native bootstrapper candidates, GitHub Actions CI matrix (unit/integration/headless GUI/bootstrapper), optional CPU/GPU/ASR/TTS policy with graceful degradation, macOS Universal 2 decision, private beta packages/checksums/versioned manifests/non-developer instructions, beta feedback workflow with redacted diagnostics, pre-upload secrets/history audit, owner-only authorization gates (no push/publish/visibility change), and MANUAL-PENDING real-hardware cross-platform acceptance. Stage 6 is reopened as in_progress (extension); total requirements 117. No universal platform support is claimed until builds/tests pass and real-hardware beta acceptance is recorded.

**v2.1 (2026-10-28)** - Stage 6 engineering complete: stage-6b portable candidate r2 (23,682 files / 1.40 GiB, single embedded runtime, flows + README, no dev-only files, relocation-safe) was smoke-tested from a managed non-default path: status/--help/doctor/imports/offscreen GUI PASS, reproducible tree hash. Revision-1's release-blocking status portability defect was fixed with regression tests (full suite 513 passed). Release acceptance remains PARTIAL: clean Windows without global Python, real clipboard/microphone/audio hardware, signed installer/update and full desktop mission execution are explicitly manual-pending; retiring the stale dist payloads (dist/portable-release, revision-1 candidate, stage6a source candidate) requires explicit user authorization.

**v2.0 (2026-10-28)** - Stage 4 engineering complete: CrewAI/Flows/model intelligence (C4a-C4e) plus Studio GUI, multimodal mission chat (F1), voice dictation/TTS foundation (F2) and IDE surfaces (F3a/F3b). Requirement statuses updated from measured evidence (NL-BP-029/031 verified; 025-028/030/033-035/037-042/044 partial). Hardware/desktop acceptance (microphone/ASR/TTS, Windows clipboard screenshots, real DPI/focus, live LSP/MCP/debugger sessions, PTY/OS-sandbox) is explicitly manual-pending. Stage 6 release acceptance evidence remains in progress.

**v1.9 (2026-10-28)** - Structural hygiene pass: one authoritative root README.md; legacy handoff/readme/patch evidence moved (git mv, nothing deleted) to docs/history/legacy/ with an index; docs/REPOSITORY_STRUCTURE.md ownership/retention/packaging policy; crewAI checkout audited read-only (not imported; kept protected); measured before/after root inventory; P-01..P-08 authorization-gated proposals recorded. Stage-6a bootstrapper/reproducible release builder evidence added; stage-4 F1 (multimodal chat) and F2 (voice) evidence added; stage 4 remains in progress (F3 IDE surfaces).

**v1.8 (2026-10-28)** - Program-status correction: stage 4 remains IN PROGRESS because C4a-C4e delivered only the CrewAI/Flows/model-intelligence portion; Studio GUI, multimodal chat/attachments, voice/ASR/TTS and IDE surfaces are still outstanding. Stage 5 (hygiene) completed; stage 6 (distribution) started early with final release acceptance gated on stage-4 completion and explicit distribution authorization. No requirement IDs changed.

**v1.7 (2026-10-28)** - Stage 5 complete: read-only repository hygiene audit plus Lead-authorized safe cleanups (3,100,666 bytes freed; 15 to 12 duplicate groups; 2 to 1 worktrees); validation 16 PASS/5 WARN/0 FAIL, full suite 417 passed. Remaining cleanup items need explicit authorization; user data, runtimes and stale dist release preserved. Stage 6 distribution/acceptance started.

**v1.6 (2026-10-28)** - Stage 4 complete (C4a-C4e): CrewRuntime seam/specs, app-owned Flow foundation, opt-in supervisor Flow executor, HITL/memory-policy/capability routing, SBOM/compat gate. Sequential pipeline remains default; Flow opt-in only because no real-model Flow acceptance evidence exists. NL-BP-006/007/009 partial (fake-model verified), 010/011 partial refreshed; counts 27 verified / 34 partial / 38 planned / 4 blocked. Stage 5 repository hygiene started (audit first, no destructive actions without authorization).

**v1.5 (2026-10-28)** - Stage-4 engineering record (C4a-C4e): CrewRuntime seam/typed specs, app-owned Flow state+persistence, opt-in supervisor Flow executor and HITL approvals, capability records + model router, memory/delegation policy, SBOM/compat gate (docs/evidence/crewai_sbom.json). NL-BP-006/007/009 planned->partial (Flow opt-in + fake-model verified for 006/007; capability registry framework only for 009); NL-BP-010/011 evidence refreshed, both stay partial. Rollout decision: sequential remains default, Flow opt-in only, because no real-model Flow acceptance exists; no gate weakened. Stage 4 remains in progress (GUI/multimodal/voice/other area-4 requirements still open). Counts: 27 verified / 34 partial / 38 planned / 4 blocked.

**v1.4 (2026-10-28)** - Stage 3 engineering complete (supervisor, preflight, queue/lease, backend selection, SH-07 Tier A verified); SH-07 Tier B recorded as BLOCKED with honest evidence (docs/SH07_TIERB_EVIDENCE.md); NL-BP-063 stays blocked, supervisor default mode off. Stage 4 started from docs/PHASE4_CREWAI_FLOWS_PLAN.md. No new requirement IDs.

**v1.3 (2026-10-28)** - Stage 3 supervisor implemented through C3d + SH-07 Tier A. C3a d81a168 additive supervisor schema/store, C3b c91e0c9 indexed-backlog loader/planner, C3c b9ec909 supervisor core (lease/heartbeat, preflight, reconcile, queue loop, run control, resource gate), C3d dbe3c3b CLI/service/GUI + selfbuild shim, C3e (this change) SH-07 Tier A end-to-end acceptance + runner/verifier scripts + docs. NL-BP-061/062 moved to verified (fake-model/end-to-end evidence + read-only gate); NL-BP-064 moved to partial (modes/budgets/stop/pause implemented, approvals flow partial); NL-BP-075 evidence refreshed but stays partial (no dashboard/429 matrix); NL-BP-063 stays blocked pending Tier B real local-model evidence. Stage 3 stays in progress; automatic mode remains off by default. Counts: 27 verified / 31 partial / 41 planned / 4 blocked.

**v1.2 (2026-10-28)** - Stage 2 closed (C1-C9b). Permission model + cloud/network gate (C9a 641c333), tool registry + recovery retention + repair evidence (C9b 283a94e): NL-BP-065/072/073/076 verified. Counts: 25 verified / 29 partial / 45 planned / 4 blocked. Stage 3 started from docs/PHASE3_SUPERVISOR_PLAN.md; NL-BP-003 real-model end-to-end and SH-07 remain the stage-3 gate.

**v1.1 (2026-10-28)** - C6/C7 wired the staged-candidate harness end-to-end: NL-BP-004/054/055/056/057/058/059/060/074 moved to verified (fake-model end-to-end tests, full suite 149 passed). No new requirement IDs; stage 2 remains in progress for permissions/tool registry (NL-BP-072/073); SH-07/supervisor work belongs to stage 3.

**v1.0 (2026-10-28)** - first consolidated backlog; supersedes the prior docs/PRODUCT_BACKLOG.md and all duplicate planning lists. Sources: Master Blueprint v6 files (30 specifications + checklist + handoffs + templates), final-product requirements (6 areas, 9 release acceptance criteria), docs/CURRENT_STATE.md, docs/COMPLETED_MISSIONS.md, docs/NEXT_SELF_BUILD_MISSION.md, docs/PHASE2_HARNESS_INTEGRATION_PLAN.md, docs/WORKSPACE_MIGRATION.md, AGENTS.md, repository code, tests and a read-only SQLite/FS audit. 98 source ID groups merged into 103 atomic requirements; 11 conflicts recorded.

## Area 1 - CrewAI + CrewAI Flows first-class integration

_CrewAI as a first-class engine dependency (not a cloned vendor checkout), agent/task/crew execution with verified gates, and complete CrewAI Flows integration for product workflows._

<a id="nl-bp-001"></a>
### NL-BP-001 - CrewAI pinned as a native runtime dependency

- **Area:** CORE - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-05; docs/CREWAI_RUNTIME.md)
- **Dependencies:** none
- **Acceptance gates:**
  - python/python.exe -c "import crewai; print(crewai.__version__)" reports the pinned 1.15.32
  - crewai.__file__ resolves under python/Lib/site-packages, never under the repository crewAI/ checkout
  - a pytest test enforces the pin and the import path
- **Evidence:**
  - pyproject.toml declares dependencies [PySide6, psutil, crewai==1.15.32, PyYAML]
  - tests/test_crewai_runtime.py::test_crewai_imports_from_embedded_runtime - PASS (targeted safe batch: 68 passed, 2026-10-28)
  - python/python.exe --version = Python 3.12.10 (measured at consolidation snapshot)
  - docs/CREWAI_RUNTIME.md
- **Sources:** specifiche/01_ARCHITETTURA_E_RUNTIME.md; specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; 03_MASTER_CHECKLIST.md#P0-05; docs/CREWAI_RUNTIME.md
- **Note:** Vendor checkout is not the import source; the embedded runtime site-packages is.

<a id="nl-bp-002"></a>
### NL-BP-002 - Vendor CrewAI checkout excluded from app runtime and payload

- **Area:** CORE - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-05; SPEC-23)
- **Dependencies:** NL-BP-001
- **Acceptance gates:**
  - no application module imports from the repository crewAI/ directory
  - the portable staging script refuses to include crewAI/ and writes the exclusion in the payload manifest
  - tests cover the exclusion
- **Evidence:**
  - tests/test_crewai_runtime.py (import path proof) - PASS in 68-test targeted batch
  - tests/test_stage_portable.py::test_staging_excludes_vendor_user_data_and_caches - PASS (16 passed safe batch)
  - dist/portable-release/payload_manifest.json lists crewAI and crewAI-tools under excluded_roots
  - docs/CREWAI_RUNTIME.md (vendor checkout policy)
- **Sources:** specifiche/01_ARCHITETTURA_E_RUNTIME.md; specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md; AGENTS.md#existing-environment-preserve-it; 03_MASTER_CHECKLIST.md#P1-05
- **Note:** The 467 MiB crewAI/ checkout is reference-only and excluded from staging.

<a id="nl-bp-003"></a>
### NL-BP-003 - Developer -> Tester -> Debugger -> Reviewer mission pipeline with real changes

- **Area:** CORE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-05, P0-09)
- **Dependencies:** NL-BP-001, NL-BP-012
- **Acceptance gates:**
  - one mission with a local model changes source, persists changed paths and a real diff, records verification exit codes/logs and a reviewer verdict in SQLite
  - a developer stage that produces no file change fails instead of reporting completion
  - the evidence survives a process restart
- **Evidence:**
  - nl_coding_agent/agents/orchestrator.py implements the stages, baseline snapshots, scope checks and handoffs
  - SQLite measured: 58 verification_runs, 151 handoffs, 13 completed missions with 11 APPROVE verdicts (read-only probe, 2026-10-28)
  - historical live missions #16, #24, #36, #37, #38, #39, #40, #41 completed/APPROVE (docs/CURRENT_STATE.md, docs/COMPLETED_MISSIONS.md, DB rows)
  - docs/08_ACCEPTANCE_GATES.md#Gate-F
- **Sources:** specifiche/02_SELF_BUILD_E_RECOVERY.md; specifiche/19_TEST_MATRIX_E_GATE.md; docs/08_ACCEPTANCE_GATES.md#Gate-F; 03_MASTER_CHECKLIST.md#P0-05; 03_MASTER_CHECKLIST.md#P0-09
- **Note:** Pipeline code exists and historical missions were executed with local models, but the current run was not re-verified end-to-end and Phase 2 is rewiring its internals.

<a id="nl-bp-004"></a>
### NL-BP-004 - Fail-closed test/verification gate blocks completion

- **Area:** CORE - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-06)
- **Dependencies:** NL-BP-003
- **Acceptance gates:**
  - a mission with failing tests can never end as completed, even if the reviewer returns APPROVE
  - an ambiguous reviewer verdict is treated as REJECT
  - adversarial test SH-04 (green candidate tests, weakened baseline oracle) blocks promotion
- **Evidence:**
  - C6 bce3b71: fail-closed gate inside the orchestrator; staging tests prove invalid/stub candidates and reviewer REJECT produce blocked/unchanged live tree
  - tests/test_orchestrator_staging.py 8 tests; full suite 149 passed (2026-10-28)
  - orchestrator._run_tester_stage raises VerificationError after max_retries=2 (nl_coding_agent/agents/orchestrator.py)
  - parse_reviewer_verdict ambiguity -> REJECT covered by tests/test_roadmap.py::test_verdicts - PASS in 68-test batch
  - SQLite: mission #45 status=blocked, review_verdict=REJECT (measured probe)
  - gap: no automated test yet for test-fail + reviewer-approve (planned as NL-BP-058 oracle gate)
- **Sources:** specifiche/07_QUALITY_GATES_E_BENCHMARK.md; specifiche/19_TEST_MATRIX_E_GATE.md; 03_MASTER_CHECKLIST.md#P0-06
- **Note:** Wired end-to-end into the orchestrator in C6; completion requires verified promotion.

<a id="nl-bp-006"></a>
### NL-BP-006 - CrewAI Flows first-class integration in a product pipeline

- **Area:** CORE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (final product requirement area 1)
- **Dependencies:** NL-BP-001
- **Acceptance gates:**
  - at least one production pipeline (mission orchestration or autonomous supervisor) is implemented with crewai.flow.flow.Flow
  - Flow state is persisted and resumable; transitions are deterministic and unit-tested with fake LLM output
  - no vendor checkout dependency and no placeholder Flow left unused
- **Evidence:**
  - tests/test_foundation.py::test_crewai_flow_import proves only the installed package import - PASS in 68-test batch
  - grep over nl_coding_agent/**/*.py finds no Flow usage and no flows module
  - C4a-C4c: nl_coding_agent/flows/{state,persistence,mission_flow,supervisor_flow}.py + agents/supervisor_executor.py implement a production Flow mission pipeline; AppFlowPersistence (app SQLite, pinned ids, durable-state resume) and tests/test_flow_state.py/test_flow_persistence.py/test_mission_flow.py/test_flow_resume.py 38 tests PASS (fake model)
  - supervisor opt-in flow pipeline parity: tests/test_supervisor_flow.py 8 PASS + SH-07 flow parity test; rollback/deny/stop gates unchanged; no real-model Flow run
- **Sources:** FINAL-REQ/area-1; specifiche/01_ARCHITETTURA_E_RUNTIME.md; gs-tasks/task-9
- **Note:** Flow integration is implemented but opt-in only. The default pipeline stays sequential because no real local-model Flow acceptance exists; fake-model fake-runtime tests are green.

<a id="nl-bp-007"></a>
### NL-BP-007 - Flow-based durable autonomous mission pipeline

- **Area:** CORE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (final product requirement area 1)
- **Dependencies:** NL-BP-006, NL-BP-051
- **Acceptance gates:**
  - an autonomous mission sequence runs as a CrewAI Flow with persisted state (SQLite or app data)
  - crash/restart resumes the flow without repeating completed steps
  - integration tests use fake models and isolate the live tree
- **Evidence:**
  - C4b/C4c: MissionFlow + SupervisorRunFlow run a durable mission sequence with persisted flow state in the app SQLite DB (flow_states/flow_runs), pinned flow ids and durable-fact resume; tests/test_flow_resume.py 5 passed, tests/test_supervisor_flow.py 8 passed (crash across supervisor restart, idempotent reconcile, fake model only)
  - The default orchestrator/supervisor path still uses the sequential executor; Flow execution is behind pipeline="flow" (CLI --pipeline flow) and was not run against real models
- **Sources:** FINAL-REQ/area-1; specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md; specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md
- **Note:** Flow-based supervisor pipeline implemented and fake-model verified (opt-in). Crash/resume parity and single-executor invariants are tested; a real-model Flow acceptance is still absent, so this stays partial.

<a id="nl-bp-008"></a>
### NL-BP-008 - Multi-provider Model Hub core: dynamic discovery, health, loaded state, unload

- **Area:** CORE - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-04, P1-05)
- **Dependencies:** NL-BP-001
- **Acceptance gates:**
  - Ollama and OpenAI-compatible providers discover models dynamically with timeouts and actionable offline/auth errors
  - loaded-model state is reported and unload is available through the native API
  - GUI discovery runs off the UI thread and recovers from errors
- **Evidence:**
  - nl_coding_agent/models/providers.py (OllamaProvider, OpenAICompatibleProvider, build_providers)
  - nl_coding_agent/models/ollama_registry.py (HTTP + CLI fallback, loaded state, stop)
  - tests/test_model_hub.py - 7 tests PASS in 68-test targeted batch (incl. panel error recovery)
  - build/relocation/verify_relocation_final_lead.json: ollama.reachable PASS, 21 models listed (2026-10-28T15:48)
- **Sources:** specifiche/05_MODEL_HUB_PROVIDERS.md; 03_MASTER_CHECKLIST.md#P1-04; 03_MASTER_CHECKLIST.md#P1-05; FINAL-REQ/area-6
- **Note:** Ollama and OpenAI-compatible adapters are implemented and unit-tested; LM Studio/llama.cpp are reachable through the generic OpenAI-compatible adapter but have no presets.

<a id="nl-bp-009"></a>
### NL-BP-009 - Provider capability registry from real probes (tools, JSON, vision, audio, context)

- **Area:** CORE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-05 'capability test reale')
- **Dependencies:** NL-BP-008
- **Acceptance gates:**
  - per backend+model capability records distinguish measured, declared and unknown capabilities
  - real probes test tool calling, JSON/structured output, vision and max usable context
  - capability-aware routing refuses unsupported combinations and explains why
- **Evidence:**
  - C4d: nl_coding_agent/models/capabilities.py records measured/declared/unknown/unavailable capabilities (vision/audio/tool_calling/structured_output/context) in the additive model_capabilities table; measured wins, declared/unknown never pass; probes are caller-supplied (no implicit network)
  - C4d: capability-aware ModelRouter refuses unsupported combinations (RouteRefused with missing capabilities); tests/test_model_capabilities.py + test_model_router.py PASS
  - Real capability probes (actual tool/JSON/vision/audio/context probes against local models) were NOT executed in this stage; no network/model loads in tests
- **Sources:** specifiche/05_MODEL_HUB_PROVIDERS.md; specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; 03_MASTER_CHECKLIST.md#P1-05; FINAL-REQ/area-2
- **Note:** Capability registry/routing framework implemented and unit-tested; real measured probes and UI remain missing, so this stays partial.

<a id="nl-bp-005"></a>
### NL-BP-005 - Reviewer independence and persisted verdict

- **Area:** CORE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-06; SPEC-07)
- **Dependencies:** NL-BP-003, NL-BP-004
- **Acceptance gates:**
  - reviewer receives task contract, candidate/live diff and verification evidence
  - verdict is persisted and a REJECT blocks completion
  - reviewer approval can never override a failing deterministic gate
- **Evidence:**
  - orchestrator reviewer stage persists verdict + handoff; mission #45 REJECT/blocked in DB
  - tests/test_roadmap.py verdict parsing PASS
  - docs/COMPLETED_MISSIONS.md records a reviewer false-negative incident (mission #24) requiring a stronger reviewer model
- **Sources:** specifiche/07_QUALITY_GATES_E_BENCHMARK.md; docs/05_ORCHESTRATION.md#Reviewer-independence; 03_MASTER_CHECKLIST.md#P0-06
- **Note:** The reviewer is an additional LLM gate with persisted verdict; the deterministic independent oracle that outranks it is not wired.

<a id="nl-bp-010"></a>
### NL-BP-010 - Configurable role -> model mapping without mandatory per-project YAML

- **Area:** CORE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-05; SPEC-05)
- **Dependencies:** NL-BP-008
- **Acceptance gates:**
  - role->model mapping is editable from GUI/CLI and persisted per project or globally
  - opening a project requires no YAML authoring
  - per-mission overrides win over stored defaults and are recorded
- **Evidence:**
  - nl_coding_agent/cli.py flags --dev-model, --reviewer-model, --debug-model
  - config/models.yaml global defaults; nl_coding_agent/agents/orchestrator.py DEFAULT_*_MODEL constants
  - GUI Agents panel is read-only (nl_coding_agent/gui/widgets/agents_panel.py; docs/CURRENT_STATE.md)
  - project registry persists facts in SQLite without per-project YAML (tests/test_foundation.py::test_open_project_round_trip - PASS)
  - C4d: ModelRouter role->ModelBinding resolution (explicit override -> project -> role config -> fallback) with capability/permission filters; tests/test_model_router.py PASS
- **Sources:** specifiche/05_MODEL_HUB_PROVIDERS.md; docs/05_ORCHESTRATION.md; 03_MASTER_CHECKLIST.md#P1-05; AGENTS.md#no-configuration-ceremony
- **Note:** CLI per-mission overrides and a global config file exist; GUI mapping is read-only and project-level mapping is not persisted.

<a id="nl-bp-011"></a>
### NL-BP-011 - Mission configuration snapshot for reproducibility

- **Area:** CORE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (SPEC-05; SPEC-18; SPEC-21)
- **Dependencies:** NL-BP-010
- **Acceptance gates:**
  - each mission persists provider, model, parameters and version snapshot usable to reproduce the run
  - handoffs/review evidence reference that snapshot
  - missions table or related tables expose the snapshot without external config files
- **Evidence:**
  - handoff payloads include "model": <model_name> per stage (orchestrator.py lines ~718, 864, 958)
  - SQLite PRAGMA table_info(missions) measured: no model/provider/params columns (read-only probe)
  - temperature is set in _make_llm (0.1) but not persisted
  - C4d: models/model_router.py ModelBinding + mission_model_snapshots table persist immutable role/provider/model/params/capability snapshots (fake-model test); not yet wired into every mission path
- **Sources:** specifiche/05_MODEL_HUB_PROVIDERS.md; specifiche/18_SQLITE_SCHEMA_E_STATI.md; specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md
- **Note:** Stage handoffs record the model name; sampling parameters, provider version and a mission-level config snapshot are not persisted as first-class rows.

<a id="nl-bp-012"></a>
### NL-BP-012 - Structured handoff contract persisted in SQLite

- **Area:** CORE - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-02/P1-03)
- **Dependencies:** NL-BP-003
- **Acceptance gates:**
  - handoffs table stores mission_id, from_role, to_role, summary, payload and timestamp
  - every stage transition records a handoff
  - handoffs are readable after restart
- **Evidence:**
  - SQLite PRAGMA table_info(handoffs) measured: [id, mission_id, from_role, to_role, summary, payload, created_at]
  - 151 handoff rows present (read-only probe, 2026-10-28)
  - nl_coding_agent/agents/orchestrator.py record_handoff calls; docs/05_ORCHESTRATION.md handoff contract
- **Sources:** specifiche/03_GOALS_MILESTONES_TASKS.md; specifiche/18_SQLITE_SCHEMA_E_STATI.md; docs/05_ORCHESTRATION.md; 03_MASTER_CHECKLIST.md#P1-02
- **Note:** Handoff rows are the durable communication contract between stages.

<a id="nl-bp-013"></a>
### NL-BP-013 - Windows console/Unicode encoding hardening at the application boundary

- **Area:** CORE - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-10)
- **Dependencies:** none
- **Acceptance gates:**
  - child-process output decodes as UTF-8 with Windows OEM and locale fallbacks
  - emoji/unicode event text never crashes a mission with charmap/UnicodeDecodeError
  - a test exercises shell decoding
- **Evidence:**
  - nl_coding_agent/tools/shell.py decode_output + UTF-8 child env (_UTF8_CHILD_ENV)
  - tests/test_operational_tools.py::test_scoped_shell_execution - PASS in 68-test batch
  - docs/CURRENT_STATE.md section 4 records the charmap fix
- **Sources:** specifiche/01_ARCHITETTURA_E_RUNTIME.md; 03_MASTER_CHECKLIST.md#P0-10
- **Note:** Vendor code is not patched; decoding is handled at the tool/log boundary.

## Area 2 - Studio GUI + multimodal chat

_Professional NL-branded Studio shell; multimodal mission chat (drag-and-drop, Ctrl+V screenshots, attachments), media/ASR/TTS backends, IDE tools (editor/terminal/Git/tests/debug/LSP/MCP), accessibility and non-blocking UX._

<a id="nl-bp-024"></a>
### NL-BP-024 - Emergency Pause/Stop always reachable during an active mission

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-15; SPEC-21 governance)
- **Dependencies:** NL-BP-064
- **Acceptance gates:**
  - Pause/Stop is visible whenever a mission is running, outside settings
  - stop cancels owned work gracefully, persists state and never kills external processes
  - verified with a live mission and a restart
- **Evidence:**
  - no stop/pause widget exists (grep over GUI); only external process kill used during recovery tests
  - specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md; specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md
- **Sources:** specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md; specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md; 03_MASTER_CHECKLIST.md#P0-15; FINAL-REQ/area-2
- **Note:** Safety requirement before unattended autonomy: the user must be able to interrupt a run without killing external processes.

<a id="nl-bp-026"></a>
### NL-BP-026 - Multimodal Mission Chat input: text, multi-file picker, drag-and-drop

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-06)
- **Dependencies:** NL-BP-021
- **Acceptance gates:**
  - mission chat surface is attached to project/mission and accepts text plus multiple files/folders
  - drag-and-drop and file picker produce attachment items with type detection
  - sending is explicit and testable offscreen with fixture files
- **Evidence:**
  - grep: no chat widget, no drag/drop handlers, no attachment model (GUI has dialogs, file viewer, task board only)
  - specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md expected experiences
- **Sources:** specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; 03_MASTER_CHECKLIST.md#P2-06; FINAL-REQ/area-2; FINAL-REQ/area-6 (criterion 4)
- **Note:** There is no chat surface at all today: only a single-line goal dialog.

<a id="nl-bp-027"></a>
### NL-BP-027 - Ctrl+V screenshot/image paste including Windows screenshots

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-06)
- **Dependencies:** NL-BP-026
- **Acceptance gates:**
  - pasting an image from the Windows clipboard (Win+Shift+S screenshot) creates an attachment with preview
  - unsupported clipboard formats fail with an explicit message, never silently
  - manual Windows test recorded as evidence
- **Evidence:**
  - no clipboard handling code (grep clipboard/QClipboard absent)
  - FINAL-REQ/area-6 criterion 4; specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md
- **Sources:** specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; FINAL-REQ/area-2; FINAL-REQ/area-6
- **Note:** Release acceptance criterion 4 explicitly requires Windows screenshot paste.

<a id="nl-bp-028"></a>
### NL-BP-028 - Attachment UX: previews, removal, type handling, explicit submit

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-06)
- **Dependencies:** NL-BP-026
- **Acceptance gates:**
  - attachments show thumbnail/name/size/type and can be removed before submit
  - media type is detected and unsupported types are explained
  - transcript/attachments are editable before explicit send
- **Evidence:**
  - no attachment UI (grep)
  - specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md
- **Sources:** specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; FINAL-REQ/area-2
- **Note:** Atomic UX requirement from final area 2; nothing implemented.

<a id="nl-bp-029"></a>
### NL-BP-029 - Attachment provenance persistence across restart

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-06; SPEC-09/18)
- **Dependencies:** NL-BP-026, NL-BP-028
- **Acceptance gates:**
  - attachment rows persist canonical path, content hash, media type, size, owner, project/mission refs and policy
  - attachments are revisitable after restart and removable without deleting user source files
  - deduplication and originals/derived separation are tested
- **Evidence:**
  - SQLite tables measured: no media_attachments, assets or attachments tables
  - specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; specifiche/18_SQLITE_SCHEMA_E_STATI.md
- **Sources:** specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; specifiche/18_SQLITE_SCHEMA_E_STATI.md; 03_MASTER_CHECKLIST.md#P2-06
- **Note:** Requires a media_attachments table and content-addressed storage in app data, not project source.

<a id="nl-bp-033"></a>
### NL-BP-033 - Microphone push-to-talk/dictation with editable local transcript

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-08) elevated by release criterion 5
- **Dependencies:** NL-BP-035
- **Acceptance gates:**
  - push-to-talk captures the microphone, transcribes locally, and inserts editable text before submit
  - language auto/manual selection and abort control exist
  - works with no cloud and no network; evidence recorded on Windows
- **Evidence:**
  - no microphone/audio capture code (grep)
  - specifiche/10_SPEECH_ASR_MODELS.md speech-to-mission section
- **Sources:** specifiche/10_SPEECH_ASR_MODELS.md; FINAL-REQ/area-2; FINAL-REQ/area-6 (criterion 5)
- **Note:** Release acceptance criterion 5: mic + local transcription must work.

<a id="nl-bp-035"></a>
### NL-BP-035 - Speech/ASR manager: Qwen3-ASR, Vosk, Faster-Whisper, WhisperX catalog and lifecycle

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-08) elevated by release criterion 5
- **Dependencies:** none
- **Acceptance gates:**
  - optional engines with catalog showing languages, source, size, hardware, latency, license
  - on-demand resumable install; enable/load/unload/uninstall/cleanup separated
  - disabling keeps weights; uninstall only app-owned non-shared assets; app works with none installed
- **Evidence:**
  - nl_coding_agent/gui/widgets/models_panel.py Speech tab is a placeholder label ('No speech engine is installed')
  - no ASR/audio modules or dependencies (grep whisper/vosk/asr absent)
  - specifiche/10_SPEECH_ASR_MODELS.md acceptance list
- **Sources:** specifiche/10_SPEECH_ASR_MODELS.md; 03_MASTER_CHECKLIST.md#P2-08; 03_MASTER_CHECKLIST.md#P3-05; FINAL-REQ/area-2
- **Note:** Only a static placeholder tab exists; at minimum one local engine must back mic transcription for release.

<a id="nl-bp-020"></a>
### NL-BP-020 - Studio shell with NL branding: logo, design tokens, dark theme

- **Area:** STUDIO - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-07)
- **Dependencies:** none
- **Acceptance gates:**
  - the GUI launches offscreen and constructs/closes the main window without errors
  - assets/LogoMio.svg and assets/theme.tokens.json drive the visual identity
  - brand palette is used and body/code/log text has no glow
- **Evidence:**
  - assets/LogoMio.svg and assets/theme.tokens.json exist
  - nl_coding_agent/gui/theme.py + main_window.py
  - tests/test_gui_smoke.py::test_main_window_constructs_and_closes_cleanly - PASS (16 passed safe batch)
  - docs/03_GUI_SPEC.md visual rules
- **Sources:** specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; docs/03_GUI_SPEC.md; AGENTS.md#gui-identity; 03_MASTER_CHECKLIST.md#P1-07
- **Note:** Brand assets are the real ones (LogoMio.svg + theme.tokens.json); no glow on text is implemented in stylesheet but final visual review remains human.

<a id="nl-bp-021"></a>
### NL-BP-021 - Navigation shell: sidebar, stacked panels, resizable splitters, inspector, log, status bar

- **Area:** STUDIO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-07)
- **Dependencies:** NL-BP-020
- **Acceptance gates:**
  - sidebar switches between Projects/Files/Tasks/Agents/Models/Settings
  - panes are resizable; inspector, log panel and status bar are present
  - layout is persisted per project and restored on restart
- **Evidence:**
  - nl_coding_agent/gui/main_window.py: stack indices 0-5 (6 pages), QSplitter layout, inspector + log + status bar
  - tests/test_gui_smoke.py offscreen construction PASS
  - no layout persistence code (grep for settings/storage of splitter state absent)
- **Sources:** specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; docs/03_GUI_SPEC.md#Suggested-desktop-composition; 03_MASTER_CHECKLIST.md#P1-07
- **Note:** Six pages and resizable splitters exist; per-project layout persistence is missing.

<a id="nl-bp-022"></a>
### NL-BP-022 - Settings panel surfacing project/runtime/provider configuration

- **Area:** STUDIO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-07/P1-08)
- **Dependencies:** NL-BP-020
- **Acceptance gates:**
  - settings show project root, SQLite path, provider URL, model config, cloud state
  - settings are editable from the GUI where the product allows configuration
  - changes persist and affect backend services
- **Evidence:**
  - nl_coding_agent/gui/widgets/settings_panel.py rows: Project root, SQLite database, Ollama base URL, Model config, Cloud escalation
  - tests/test_gui_panels.py::test_settings_panel_is_read_only_and_tracks_project - PASS (16-test batch)
  - no write path exists in the panel
- **Sources:** specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; 03_MASTER_CHECKLIST.md#P1-07; 03_MASTER_CHECKLIST.md#P1-08
- **Note:** Read-only display only; user-editable settings and self-build controls are absent.

<a id="nl-bp-023"></a>
### NL-BP-023 - Self-Build controls under Settings > Advanced (modes, plan, limits, history, stop)

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-08, P1-16)
- **Dependencies:** NL-BP-064
- **Acceptance gates:**
  - self-build/autonomy controls exist only under Settings > Advanced with opt-in toggle, plan, limits and history
  - self-build never starts automatically on app open
  - running mission status is visible naturally in Tasks/Missions with pause/stop controls
- **Evidence:**
  - settings_panel.py contains no self-build/autonomy controls; GUI panes are read-only status displays
  - specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md explicit UX decision
  - no mode persistence in SQLite (tables measured)
- **Sources:** specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md; 03_MASTER_CHECKLIST.md#P1-08; 03_MASTER_CHECKLIST.md#P1-16
- **Note:** Explicit UX decision: no prominent self-build CTA on the home screen; controls belong in Advanced settings.

<a id="nl-bp-025"></a>
### NL-BP-025 - Mission creation, run and resume from the GUI

- **Area:** STUDIO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-03)
- **Dependencies:** NL-BP-021
- **Acceptance gates:**
  - a mission can be created with a goal from the GUI and appears in the task board
  - run/resume is wired to the backend and status refreshes
  - no GUI thread blocking; evidence test or smoke run recorded
- **Evidence:**
  - nl_coding_agent/gui/widgets/projects_panel.py New Mission QInputDialog + create_mission
  - nl_coding_agent/gui/widgets/task_board.py mission list, Run/Resume action, roadmap mission creation
  - no GUI automation for mission execution; only read-only panel tests (16-test batch)
- **Sources:** specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; specifiche/03_GOALS_MILESTONES_TASKS.md; 03_MASTER_CHECKLIST.md#P1-03
- **Note:** Project panel can create a mission from a single-line goal dialog and the task board can run/resume; no GUI test covers a mission run.

<a id="nl-bp-030"></a>
### NL-BP-030 - Media backends: PDF/Office/text/log/code/JSON/CSV extraction and safe archives

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-07)
- **Dependencies:** NL-BP-026
- **Acceptance gates:**
  - supported document types extract text with source provenance and size limits
  - archives are extracted safely (no traversal, no bomb) or refused
  - no media leaves the machine without explicit cloud consent
- **Evidence:**
  - no document/media parser modules (only an extension allowlist in file_viewer.py)
  - specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md
- **Sources:** specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; 03_MASTER_CHECKLIST.md#P2-07
- **Note:** Separate adapters per media family; archive extraction must be traversal/zip-bomb safe.

<a id="nl-bp-031"></a>
### NL-BP-031 - Capability-aware routing of images and attachments to supporting models

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-07)
- **Dependencies:** NL-BP-009, NL-BP-026, NL-BP-030
- **Acceptance gates:**
  - images are sent only to models whose vision capability is verified; otherwise the user gets an explicit alternative
  - audio understanding is never confused with ASR
  - routing respects local-only/cloud policy and is shown in the UI
- **Evidence:**
  - no capability-aware routing (grep vision/attachment absent)
  - specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; specifiche/05_MODEL_HUB_PROVIDERS.md
- **Sources:** specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; specifiche/05_MODEL_HUB_PROVIDERS.md; 03_MASTER_CHECKLIST.md#P2-07
- **Note:** Vision support must come from the capability registry, never from 'OpenAI-compatible' assumptions.

<a id="nl-bp-032"></a>
### NL-BP-032 - Audio/video media backends: transcription and frame sampling/audio extraction

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-07)
- **Dependencies:** NL-BP-035
- **Acceptance gates:**
  - audio attachments produce local ASR transcripts with timestamps where supported
  - video is sampled into frames and audio extracted for ASR with provenance
  - processing is async, cancellable and bounded
- **Evidence:**
  - no audio/video/ffmpeg integration in nl_coding_agent/ (grep)
  - specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md
- **Sources:** specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md; specifiche/10_SPEECH_ASR_MODELS.md; 03_MASTER_CHECKLIST.md#P2-07
- **Note:** FFmpeg/audio tooling is not integrated; no media modules exist.

<a id="nl-bp-036"></a>
### NL-BP-036 - Model lifecycle UI: install/load/unload/uninstall and storage audit

- **Area:** STUDIO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-09)
- **Dependencies:** NL-BP-008
- **Acceptance gates:**
  - Model Hub exposes install/load/unload/uninstall and owned-model cleanup with confirmations
  - storage audit shows ownership, size and references before deletion
  - shared Ollama/Hugging Face checkpoints are never deleted
- **Evidence:**
  - providers.py supports unload (Ollama stop); models_panel has no action buttons
  - models_panel Storage/Hardware tabs are read-only labels
  - specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md
- **Sources:** specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md; 03_MASTER_CHECKLIST.md#P2-09; 03_MASTER_CHECKLIST.md#P2-14
- **Note:** Backend unload exists; the GUI model surfaces are read-only status tables with no lifecycle actions.

<a id="nl-bp-043"></a>
### NL-BP-043 - Project explorer, search, indexing and targeted context retrieval

- **Area:** STUDIO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-11)
- **Dependencies:** NL-BP-077
- **Acceptance gates:**
  - project explorer + text search operate on the open project
  - selective indexing/retrieval feeds missions without dumping the whole repository
  - no surprise downloads/embeddings; context budget measured
- **Evidence:**
  - nl_coding_agent/gui/widgets/file_viewer.py read-only browser with text filter
  - no search/index/embedding module (grep)
  - specifiche/12_PROJECT_DISCOVERY.md context retrieval section
- **Sources:** specifiche/12_PROJECT_DISCOVERY.md; 03_MASTER_CHECKLIST.md#P2-11
- **Note:** A filtered read-only file browser exists; search/index/semantic retrieval do not.

<a id="nl-bp-044"></a>
### NL-BP-044 - Accessibility and usability: keyboard focus, DPI scaling, contrast, shortcuts, command palette

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** P1 (SPEC-08; final area 2 'accessible')
- **Dependencies:** NL-BP-020
- **Acceptance gates:**
  - keyboard navigation/focus order, tooltips, contrast and DPI scaling verified
  - shortcuts and command palette implemented
  - UI review evidence recorded (manual accessibility checklist)
- **Evidence:**
  - gui/theme.py defines focus styles; no accessibility tests or command palette code
  - specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; final area 2 wording
- **Sources:** specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; FINAL-REQ/area-2
- **Note:** Theme defines focus states, but no accessibility verification or command palette exists.

<a id="nl-bp-045"></a>
### NL-BP-045 - Non-blocking responsive UI with explicit empty/loading/error/offline states

- **Area:** STUDIO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-07; SPEC-08)
- **Dependencies:** NL-BP-021
- **Acceptance gates:**
  - inference/download/scan/build work never blocks the Qt event loop
  - each async surface defines empty/loading/error/offline states and never fabricates metrics
  - a measurable latency or responsiveness test exists
- **Evidence:**
  - ModelHubFetchThread in gui/widgets/models_panel.py; SequentialScheduler thread
  - tests/test_model_hub.py::test_model_hub_panel_renders_and_recovers_from_error - PASS in 68-test batch
  - no latency/responsiveness test; other panels have no async states
- **Sources:** specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; specifiche/05_MODEL_HUB_PROVIDERS.md; 03_MASTER_CHECKLIST.md#P1-07
- **Note:** Model discovery runs in a worker and has error/empty labels; there is no systematic state design or latency test.

<a id="nl-bp-046"></a>
### NL-BP-046 - Project dashboard and agent/task visualization

- **Area:** STUDIO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-03, P1-07)
- **Dependencies:** NL-BP-021, NL-BP-051
- **Acceptance gates:**
  - dashboard shows project facts, detected stack, docs, Git state, last audit, missions and unresolved manual checks
  - task cards show state, role, model, dependencies, write scope, verification and retry count
  - agent panel shows role/model availability and resource policy
- **Evidence:**
  - gui/widgets/projects_panel.py, task_board.py, agents_panel.py, inspector_panel.py, log_panel.py
  - tests/test_gui_panels.py 3 tests PASS (16-test batch)
  - no dashboard Git-state/unresolved-checks surface
- **Sources:** docs/03_GUI_SPEC.md#Project-dashboard; specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md; 03_MASTER_CHECKLIST.md#P1-03
- **Note:** Projects, task board, agents and inspector panels exist; project dashboard with Git state and unresolved manual checks is missing.

<a id="nl-bp-034"></a>
### NL-BP-034 - Optional text-to-speech with local model discovery/install/switch/unload

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** new (final product requirement area 2)
- **Dependencies:** NL-BP-035
- **Acceptance gates:**
  - TTS is disabled by default and installable on demand from local models
  - switch/unload works and frees resources
  - app remains fully usable without TTS
- **Evidence:**
  - no TTS code (grep tts/speech absent outside a placeholder label)
  - FINAL-REQ/area-2
- **Sources:** FINAL-REQ/area-2; specifiche/10_SPEECH_ASR_MODELS.md
- **Note:** Optional capability; must never block text/mic operation when absent.

<a id="nl-bp-037"></a>
### NL-BP-037 - Integrated code editor (maintained component) with tabs and highlighting

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-10)
- **Dependencies:** NL-BP-021
- **Acceptance gates:**
  - editable editor with tabs, syntax highlighting, undo/save and large-file performance
  - component licensing and packaging impact documented
  - offscreen smoke test opens/edits/saves a fixture
- **Evidence:**
  - nl_coding_agent/gui/widgets/file_viewer.py is read-only QFileSystemModel + QPlainTextEdit
  - specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md
- **Sources:** specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md; 03_MASTER_CHECKLIST.md#P2-10; docs/02_SELF_BUILD_ROADMAP.md#Phase-8
- **Note:** Current Files panel is a read-only viewer; editor component choice (Monaco/WebEngine vs CodeMirror 6) must be evaluated on size, performance, licensing.

<a id="nl-bp-038"></a>
### NL-BP-038 - Integrated terminal/PTY with command policy

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-10)
- **Dependencies:** NL-BP-072
- **Acceptance gates:**
  - terminal runs commands in the project cwd with timeout/output bounds and visible policy
  - no widget-held business logic; cancellation works
  - tests cover policy and cancellation
- **Evidence:**
  - no terminal widget (grep); backend scoped_run_command uses shell=True with cwd only
  - specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md
- **Sources:** specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md; 03_MASTER_CHECKLIST.md#P2-10
- **Note:** Backend shell helper exists but is not a sandbox; terminal UI must be policy-gated.

<a id="nl-bp-039"></a>
### NL-BP-039 - Git UI: status, branches, diff, selective staging

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-10)
- **Dependencies:** NL-BP-053
- **Acceptance gates:**
  - visual diff with file-level staging selection and branch/status display
  - destructive git operations require explicit confirmation
  - tests use a temporary repository
- **Evidence:**
  - nl_coding_agent/tools/git_tools.py provides get_git_status/get_git_diff; no GUI module references it
  - specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md
- **Sources:** specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md; 03_MASTER_CHECKLIST.md#P2-10
- **Note:** git_tools backend exists for status/diff; no GUI.

<a id="nl-bp-040"></a>
### NL-BP-040 - Test explorer, problems panel and debugger integration (DAP)

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-10)
- **Dependencies:** NL-BP-011, NL-BP-039
- **Acceptance gates:**
  - tests can be run/filtered from the UI and failures listed as problems
  - debugger via DAP or an explicit documented non-support statement
  - no fake buttons; every action performs a real backend call
- **Evidence:**
  - task_board.py shows verification runs/handoffs only; no problems/test/debug panels
  - specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md
- **Sources:** specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md; 03_MASTER_CHECKLIST.md#P2-10
- **Note:** No test explorer/problems/debugger surface exists; mission evidence is visible in the task board.

<a id="nl-bp-041"></a>
### NL-BP-041 - LSP integration for diagnostics, completion and symbols

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-10)
- **Dependencies:** NL-BP-037
- **Acceptance gates:**
  - at least one language server session provides diagnostics/completion/symbol navigation
  - server lifecycle is managed and resource-bounded
  - integration test with a mock or local server
- **Evidence:**
  - grep LSP: only false positives inside Qt class names; no protocol client
  - specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md
- **Sources:** specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md; 03_MASTER_CHECKLIST.md#P2-10
- **Note:** No LSP client or language-server management exists.

<a id="nl-bp-042"></a>
### NL-BP-042 - MCP tool integration

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** new (final product requirement area 2; SPEC-11)
- **Dependencies:** NL-BP-073
- **Acceptance gates:**
  - MCP servers can be registered with consent, their tools discovered and invoked under the permission model
  - tests against a local mock MCP server
  - no implicit network or credential exposure
- **Evidence:**
  - no MCP code (grep only finds a ctypes cp call)
  - FINAL-REQ/area-2; specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md
- **Sources:** specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md; FINAL-REQ/area-2
- **Note:** MCP appears in the final area 2 list; no client/registry exists.

## Area 3 - Universal autonomous development

_Persistent goals/milestones/tasks/missions, dynamic teams, model competence evidence, resource scheduling, permissions/tool registry, supervised execution on arbitrary projects, independent gates, staged changes, safe rollback; the indexed blueprint is the durable specification._

<a id="nl-bp-051"></a>
### NL-BP-051 - Durable mission/task persistence, resume and idempotent recovery

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-07, P0-08)
- **Dependencies:** NL-BP-012
- **Acceptance gates:**
  - every significant transition is committed before reporting success
  - interrupted missions resume without duplicating applied patches; state distinguishes INTERRUPTED/RETRYABLE/BLOCKED
  - mission/task state survives restart; resume command is exact and tested
- **Evidence:**
  - persistence/database.py schema + migrations; orchestrator baseline save/load; mission/interrupted reset logic
  - additive harness schema (missions.harness_version/staging_dir/promotion_status) + tests/test_harness_schema.py 3 tests PASS (C5, HEAD 7e778da)
  - tests/test_selfbuild_runner.py 9 tests PASS (68-test batch, selection/reconcile/resume-command)
  - SQLite measured: mission #41 resume_count and completed/APPROVE; mission #40 completion record
  - docs/CURRENT_STATE.md live stop-after/resume evidence; no crash-idempotency test yet
- **Sources:** specifiche/02_SELF_BUILD_E_RECOVERY.md; specifiche/18_SQLITE_SCHEMA_E_STATI.md; specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md; 03_MASTER_CHECKLIST.md#P0-07; 03_MASTER_CHECKLIST.md#P0-08
- **Note:** Resume, baseline persistence and reconciliation are implemented and exercised live (#40/#41), but double-write prevention is not proven by an automated crash test.

<a id="nl-bp-054"></a>
### NL-BP-054 - Evidence-based completion: no mission completes without passing gates

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-06; SPEC-07)
- **Dependencies:** NL-BP-003, NL-BP-005
- **Acceptance gates:**
  - completed requires passing verification runs, reviewer APPROVE and persisted evidence
  - failed tests or empty diff make completion impossible
  - baseline/diff cannot be retroactively rewritten to hide agent changes
- **Evidence:**
  - C6 bce3b71: _finalize_completed only after verified promotion; _finalize_blocked/_finalize_interrupted never report applied changes
  - tests/test_orchestrator_staging.py: happy path vs stub/reject/stop-after assertions
  - orchestrator _finalize only called on APPROVE path; tester raises VerificationError on failure
  - SQLite measured: 13 completed (11 with APPROVE), missions #44/#45 blocked REJECT
  - specifiche/07_QUALITY_GATES_E_BENCHMARK.md; gap: SH-04 oracle test planned
- **Sources:** specifiche/07_QUALITY_GATES_E_BENCHMARK.md; specifiche/19_TEST_MATRIX_E_GATE.md; 03_MASTER_CHECKLIST.md#P0-06
- **Note:** Evidence-based completion is enforced by the staged-candidate orchestrator flow.

<a id="nl-bp-055"></a>
### NL-BP-055 - Staged candidate writes: every model mutation stays off the live tree

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-17; SPEC-28 invariants)
- **Dependencies:** NL-BP-051, NL-BP-053
- **Acceptance gates:**
  - developer/debugger tools and the Markdown/text fallback write only inside a staged workspace
  - before promotion no live file changes; an automated test asserts live-tree bytes are unchanged after a developer stage
  - staging excluded from vendor/data/cache copies and cleaned on terminal status
- **Evidence:**
  - C6 bce3b71: developer/debugger tools, JSON tool calls and text fallback write only stage.workspace; promotion is the only live-write path
  - tests/test_orchestrator_staging.py: live tree unchanged until promotion (8 tests)
  - nl_coding_agent/core/staging_broker.py exists (v2, C1a commit cb5184e); tests/test_staging_broker_adversarial.py 7 tests PASS (68-test batch, incl SH-01/SH-02/SH-03/SH-04)
  - promotion lifecycle (C3 commit 7372128, 14 tests), candidate/oracle verification (C4 commit 10aa437, 7 tests) and harness schema (C5 commit 7e778da) landed during consolidation; 24 harness tests PASS (HEAD 7e778da)
  - grep: no staging/promotion import or call in nl_coding_agent/agents/orchestrator.py
  - docs/PHASE2_HARNESS_INTEGRATION_PLAN.md section 1.3 (runtime imports not wired); mission #45 result summary: agent overwrote planner/test live before rollback (SQLite probe)
- **Sources:** specifiche/28_SELF_HEALING_AGENT_HARNESS.md#2; specifiche/27_SELF_CHANGE_GATES_AND_DEPLOY.md; 03_MASTER_CHECKLIST.md#P0-17; FINAL-REQ/area-6 (criterion 7)
- **Note:** Staged-candidate writes wired end-to-end; model-facing surface is 4 file tools (no shell/test/git).

<a id="nl-bp-056"></a>
### NL-BP-056 - Pre-edit recovery points, compare-and-swap rollback and baseline provenance

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-13)
- **Dependencies:** NL-BP-055
- **Acceptance gates:**
  - preimage of every in-scope dirty/untracked file is stored before modification (size-bounded, content-addressed)
  - rollback restores only files whose current hash equals the recorded postimage; human edits are never overwritten
  - SH-02/SH-03 crash and concurrency tests pass; external changes are tracked distinctly from mission changes
- **Evidence:**
  - C6 bce3b71: promotion.ensure_recovery_point before live writes; CAS drift check; rollback_from_snapshot(expected_post_hashes)
  - tests/test_promotion_stage.py (14 tests) + staging human-edit CAS-conflict test
  - nl_coding_agent/core/recovery_store.py v2 applied (C1a); tests/test_rollback_stub.py 3 tests PASS (68-test batch)
  - promotion.ensure_recovery_point/promote/rollback implement recovery point + CAS + journal (C3, 14 tests PASS); selfbuild_runner preflight calls promotion.preflight (C5); orchestrator not wired yet
  - tests/test_staging_broker_adversarial.py::test_sh02_cas_rollback_preserves_newer_human_edit and ::test_sh03_recovery_from_promoted_candidate - PASS (broker level)
  - selfbuild_runner.py imports save_snapshot/rollback_from_snapshot at line 12, used only in the post-hoc block at ~line 308
  - data/mission_baselines: 16 baseline files measured; mission #45 rollback evidence (agent-reported in result summary)
- **Sources:** specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md; specifiche/15_SICUREZZA_E_PRIVACY.md; 03_MASTER_CHECKLIST.md#P0-13
- **Note:** Recovery point + compare-and-swap rollback implemented and wired before promotion.

<a id="nl-bp-057"></a>
### NL-BP-057 - Stub/weak-test integrity gate enforced before promotion

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-17; SPEC-27; SPEC-28 SH-01/SH-04)
- **Dependencies:** NL-BP-055, NL-BP-056
- **Acceptance gates:**
  - stub/placeholder/truncation and weakened-test detection runs as a mandatory promotion gate
  - SH-01 (planner replaced by pass + self-approving test) and SH-04 (green weakened tests) are blocked before any live write
  - no false positive for legitimate pass/abstract bodies; evidence persisted
- **Evidence:**
  - C6 bce3b71: promotion.validate (AST stub/weak-test, scope, protected/input paths) before candidate verification; post-hoc runner gate removed in C7 3790aaf
  - stub candidate end-to-end test -> blocked, live unchanged, no recovery point
  - nl_coding_agent/core/code_integrity_gate.py (detect_stub, detect_weak_test) present
  - promotion.validate wires the integrity gate into candidate validation (C3/C4; 24 harness tests PASS at HEAD 7e778da); still not called by the orchestrator
  - tests/test_staging_broker_adversarial.py::test_sh01_stub_never_touches_live_source and ::test_sh04_weak_test_rejected - PASS (68-test batch, broker level)
  - selfbuild_runner.py lines 308-310 still run the post-hoc detect_stub + direct baseline rewrite; docs/history/legacy/AUDIT_REALE_E_LIMITI.md item 6 records the fail-open except
  - mission #45 blocked after live stub overwrite restored from baseline 42 (SQLite result summary)
- **Sources:** specifiche/27_SELF_CHANGE_GATES_AND_DEPLOY.md; specifiche/28_SELF_HEALING_AGENT_HARNESS.md#4; 03_MASTER_CHECKLIST.md#P0-17
- **Note:** Integrity gate is enforced before promotion and is fail-closed.

<a id="nl-bp-058"></a>
### NL-BP-058 - Independent candidate + oracle verification before promotion

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (SPEC-28 section 5; SPEC-19; SH-04)
- **Dependencies:** NL-BP-055
- **Acceptance gates:**
  - candidate tests run in a disposable copy with scrubbed env, offscreen Qt and throw-away NL_DATA_DIR
  - baseline-pinned oracle tests run over candidate source; both suites green before promotion
  - SH-04 prototype (green weakened tests + red oracle) is reproduced as an automated test
- **Evidence:**
  - C6 bce3b71: tester gate runs candidate_verification.verify_candidate (candidate + baseline-test oracle) in disposable copies; verification_runs rows recorded
  - tests/test_candidate_verification.py (7) + tests/test_orchestrator_staging.py (candidate/oracle rows asserted)
  - docs/PHASE2_HARNESS_INTEGRATION_PLAN.md sections 4.1-4.9 (measured prototypes: source-only copy 182 files/1.32 MB, suite ~13.5 s; oracle-overlay proof)
  - nl_coding_agent/core/candidate_verification.py exists (C4 commit 10aa437) with tests/test_candidate_verification.py 7 tests PASS (24-test harness batch, HEAD 7e778da)
  - grep: no candidate_verification import/call in nl_coding_agent/agents/orchestrator.py (integration pending, Phase 2 C6b)
  - oracle gate required by SPEC-28 section 5 and final area 6 criterion 7
- **Sources:** specifiche/28_SELF_HEALING_AGENT_HARNESS.md#5; specifiche/19_TEST_MATRIX_E_GATE.md; docs/PHASE2_HARNESS_INTEGRATION_PLAN.md
- **Note:** Candidate + oracle verification is the tester gate for missions.

<a id="nl-bp-059"></a>
### NL-BP-059 - Promotion journal, CAS and crash reconciliation

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-13; SPEC-28 SH-03)
- **Dependencies:** NL-BP-055, NL-BP-056
- **Acceptance gates:**
  - promotion writes a durable journal with before/after hashes; per-file CAS before atomic writes
  - resume reconciles all-after/all-before/mixed states, automatic CAS rollback on mixed, blocked on conflict
  - journal is never deleted without proof; tests cover crash points
- **Evidence:**
  - C6 bce3b71: promotion.promote/journal/reconcile wired in _run_locked (promotion-complete resume, conflict -> blocked)
  - tests/test_promotion_stage.py journal/reconcile tests + staging resume test
  - tests/test_staging_broker_adversarial.py promotion/rollback tests PASS (68-test batch)
  - nl_coding_agent/core/promotion.py (C3) + tests/test_promotion_stage.py 14 tests PASS (24-test harness batch, HEAD 7e778da); DB promotion_status/staging_dir columns present (C5); selfbuild preflight uses promotion.preflight
  - docs/PHASE2_HARNESS_INTEGRATION_PLAN.md sections 5.3-5.5 (algorithm); no orchestrator call sites (grep)
  - SQLite missions table has no promotion_status/staging_dir columns yet (PRAGMA measured)
- **Sources:** specifiche/28_SELF_HEALING_AGENT_HARNESS.md#4; specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md#3; 03_MASTER_CHECKLIST.md#P0-13
- **Note:** Promotion journal, CAS and crash reconciliation are wired.

<a id="nl-bp-060"></a>
### NL-BP-060 - Fail-closed mission status semantics (no false APPROVE/completed)

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (SPEC-28 invariant 9; SPEC-19)
- **Dependencies:** NL-BP-054, NL-BP-059
- **Acceptance gates:**
  - every gate failure maps to blocked/failed, never completed
  - no APPROVE persisted when tests failed; no baseline rewrite after the fact
  - static check proves only the finalize function writes completed
- **Evidence:**
  - C6 bce3b71: completed only after promotion; blocked on every gate failure; staged paths not reported as applied changes
  - tests/test_orchestrator_staging.py: status assertions for happy/stub/reject/stop-after/legacy
  - SQLite: missions #44/#45 blocked with REJECT; 13 completed; no completed mission visible with failing verification
  - selfbuild_runner preflight/legacy gates added in C5 return blocked for unresolved promotion state and non-harness missions (HEAD 7e778da)
  - docs/history/legacy/AUDIT_REALE_E_LIMITI.md item 6 records the runner fail-open exception (swallowed error)
  - orchestrator finalize path only on APPROVE; Phase 2 C6c plans explicit finalize split
- **Sources:** specifiche/28_SELF_HEALING_AGENT_HARNESS.md#2; specifiche/19_TEST_MATRIX_E_GATE.md; specifiche/07_QUALITY_GATES_E_BENCHMARK.md
- **Note:** Fail-closed mission status semantics implemented and tested.

<a id="nl-bp-061"></a>
### NL-BP-061 - Supervisor daemon independent of the chat/LLM with durable queue, lease and preflight

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-14, P0-15, P0-18)
- **Dependencies:** NL-BP-051
- **Acceptance gates:**
  - non-LLM supervisor process/loop survives restart with durable queue, lease/heartbeat and single-claim guarantee
  - startup preflight blocks when an unresolved promotion journal/stage exists
  - Stop/Pause/Resume honored; no duplicate or conflicting claims; tests
- **Evidence:**
  - C3a d81a168: additive supervisor schema + tests/test_supervisor_store.py 17 tests (lease CAS/TTL with pid/host proof, heartbeat renew, queue claim/state machine/idempotency, backlog mirror, evidence, approvals)
  - C3c b9ec909: nl_coding_agent/core/supervisor.py Supervisor (lease acquisition/heartbeat thread, 15-check fail-closed preflight, reconcile-on-start, queue loop, run control, resource gate) + core/run_control.py + core/resource_gate.py
  - tests/test_supervisor_core.py 33 tests PASS (off-mode default, preflight matrix, reconciliation matrix, stop/pause, retry/dead-letter, lease conflict/lost, real-orchestrator RunStopped hook)
  - tests/test_supervisor_sh07.py 7 tests PASS: two consecutive missions from a fixture INDEX.json, plus restart/pause/stop/resume idempotency
  - C3d dbe3c3b: CLI supervisor group + background SupervisorService + tests/test_supervisor_cli.py 20 tests PASS
  - scripts/verify_supervisor.py read-only gate PASS (schema, no active lease, no live run, no journal, queue/backlog consistency, default mode off, valid index)
- **Sources:** specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md; specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md; 03_MASTER_CHECKLIST.md#P0-14; 03_MASTER_CHECKLIST.md#P0-15; 03_MASTER_CHECKLIST.md#P0-18
- **Note:** Implemented as a process/thread supervisor with durable SQLite queue/lease/state and CLI/GUI controls; it is not an OS service (no reboot survival), stale leases are reclaimed only after TTL + liveness proof.

<a id="nl-bp-062"></a>
### NL-BP-062 - Automatic next-mission selection from the indexed backlog

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-14, P0-18)
- **Dependencies:** NL-BP-061
- **Acceptance gates:**
  - after a verified mission, the next READY task is selected from the indexed backlog without a new prompt
  - dedupe by stable requirement ID/fingerprint; roadmap/state updated automatically
  - two consecutive selection runs verified live
- **Evidence:**
  - C3b c91e0c9: nl_coding_agent/core/backlog.py fail-closed INDEX.json loader (schema/program_order/requirements), program-stage gate, dependency/priority ordering, content hash, idempotency keys, goal composition; tests/test_backlog_planner.py 20 tests PASS
  - SQLite backlog_items mirror (sync/read/progress) + supervisor selection from it; no dependency on docs/NEXT_SELF_BUILD_MISSION.md (static test asserts it)
  - tests/test_supervisor_sh07.py 7 tests PASS: two consecutive requirements selected and completed from a fixture indexed backlog without a new prompt; same idempotency key never duplicates a queue row/mission; a third run selects nothing
  - scripts/run_supervisor_sh07.py --mode fake PASS, evidence in build/phase3/evidence/sh07-fake-<UTC>/evidence.json
- **Sources:** specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md; specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md; 03_MASTER_CHECKLIST.md#P0-14; 03_MASTER_CHECKLIST.md#P0-18
- **Note:** Selection is fully implemented and proven with fake-model end-to-end evidence; the "two consecutive selection runs verified live" arm is covered by the Tier B SH-07 gate (NL-BP-063), which stays blocked until real local-model evidence exists.

<a id="nl-bp-063"></a>
### NL-BP-063 - Two consecutive missions with local models and no manual repair

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** blocked
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-18; SPEC-28 SH-07)
- **Dependencies:** NL-BP-055, NL-BP-056, NL-BP-057, NL-BP-058, NL-BP-059, NL-BP-061, NL-BP-062
- **Acceptance gates:**
  - two consecutive real missions complete with tests/review/evidence and automatic backlog progress
  - no manual code repair between them; survives a supervisor restart
  - evidence recorded in SQLite/logs and reproducible from a clean start
- **Evidence:**
  - Tier A (2026-10-28): tests/test_supervisor_sh07.py - two consecutive fake-model missions complete without manual repair
  - Tier B attempt 1 (e81a916): 2 docs-only missions -> quality-gate hole fixed in 2a44460 (docs/SH07_TIERB_EVIDENCE.md)
  - Tier B attempt 2 (2a44460): real local models -> validation rejected weakened tests, supervisor BLOCKED with 0 promotions and clean worktree; docs/evidence/sh07/attempt2/
  - SQLite: mission #44 blocked REJECT (supervisor continuous execution); mission #45 blocked after stub overwrite (result summary)
  - data/selfbuild_state.json audit_note_42/43: stub restore and manual repair recorded
  - docs/history/legacy/HANDOFF_DEEPSEEK_HARNESS.md: previous cycle #43/#45 produced stubs; protections not integrated
  - docs/CURRENT_STATE.md known boundaries: no unattended proof
  - Tier A (fake model) now PASS: tests/test_supervisor_sh07.py 7 tests - two consecutive staged-candidate missions with candidate+oracle verification, one promotion per mission, restart/pause/stop idempotency and fail-closed negatives; evidence via scripts/run_supervisor_sh07.py --mode fake
  - Tier B (real local models) NOT executed: scripts/run_supervisor_sh07.py --mode live --confirm-live --worktree <isolated worktree> requires explicit authorization and records evidence under build/phase3/evidence/
- **Sources:** specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md; specifiche/28_SELF_HEALING_AGENT_HARNESS.md#7; 03_MASTER_CHECKLIST.md#P0-18
- **Note:** BLOCKED on real local-model endurance: Tier A passes deterministically, but Tier B attempt 2 was blocked by the validation gate (local developer weakened a test). Automatic mode stays opt-in and default off; the gate must not be weakened to claim SH-07. See docs/SH07_TIERB_EVIDENCE.md.

<a id="nl-bp-064"></a>
### NL-BP-064 - Autonomy modes Off/Assisted/Automatic with budgets, approvals and stop/pause

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-15; SPEC-26)
- **Dependencies:** NL-BP-061
- **Acceptance gates:**
  - Off/Assisted/Automatic mode persisted per project with advanced parameters (budget, attempts, risk, resources)
  - risky operations (delete, migrate, publish, cloud, install) require explicit approval policies
  - no cloud activation by default; budget/attempt limits enforced; stop/pause honored
- **Evidence:**
  - C3c b9ec909: SupervisorConfig persisted via app_settings (supervisor.global / supervisor.project.<id>) with validated budgets (missions, attempts, wall clock, backoff, consecutive failures); mode off is the default
  - durable stop/pause/resume via supervisor_commands + supervisor_runs flags, honoured at safe mission boundaries (never mid-promotion); tests/test_supervisor_core.py 33 tests PASS
  - C3d dbe3c3b: CLI supervisor group with --mode/--confirm-assisted, background SupervisorService, Autonomy GUI page and emergency STOP; tests/test_supervisor_cli.py 20 tests PASS + tests/test_gui_smoke.py/test_gui_panels.py PASS
  - approvals table + pending_approvals/decide_approval helpers exist; cloud/network/delete stay denied by default via the permission gate (tests/test_permissions.py)
- **Sources:** specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md; specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md; 03_MASTER_CHECKLIST.md#P0-15
- **Note:** Modes, budgets and stop/pause are implemented and persisted; the approval request/decision flow is only partially integrated (no complete assisted-approval UI/mission resume workflow yet), so status stays partial.

<a id="nl-bp-065"></a>
### NL-BP-065 - Bounded repair loop driven by structured diagnostics

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (SPEC-28 section 4; SPEC-07 retries)
- **Dependencies:** NL-BP-054
- **Acceptance gates:**
  - repair attempts are bounded and logged; the same error signature does not loop forever
  - after repeated comparable failures the mission blocks with diagnosis instead of retrying
  - repair acts on staged candidates only (NL-BP-055)
- **Evidence:**
  - C9b 283a94e + tests/test_harness_repair.py: scripted failing candidate -> one debugger repair -> candidate+oracle pass -> reviewer APPROVE -> one promotion -> completed (verification rows fail,fail,pass,pass)
  - repair-budget exhaustion path -> blocked, live unchanged, no recovery point; max-attempt constants enforced
  - orchestrator _run_tester_stage max_retries=2 loop calls _run_debugger; attempts recorded in task_attempts (59 rows measured)
  - no signature classification/dead-letter; historical missions #37/#40 needed manual fixes (docs/COMPLETED_MISSIONS.md)
- **Sources:** specifiche/28_SELF_HEALING_AGENT_HARNESS.md#4; specifiche/07_QUALITY_GATES_E_BENCHMARK.md; specifiche/24_OPERATIONS_SUPERVISION_HEALTH_AND_DIAGNOSTICS.md
- **Note:** Bounded repair loop implemented and evidenced on the staged-candidate flow.

<a id="nl-bp-068"></a>
### NL-BP-068 - Explainable Model Advisor with profiles and per-agent parameters

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-03, P2-04, P2-12) elevated by final criterion 8
- **Dependencies:** NL-BP-008, NL-BP-009
- **Acceptance gates:**
  - recommends provider/model/sampling/context/parallelism per task/role with reasons and confidence
  - profiles Maximum Verified Quality/Balanced/Speed/Resource Saving/Custom; overrides persist and win
  - unmeasured recommendations labelled PROVISIONAL; no invented scores
- **Evidence:**
  - no advisor module; DEFAULT_DEVELOPER_MODEL/REVIEWER/DEBUG constants in orchestrator; no parameter persistence
  - specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md
- **Sources:** specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md; 03_MASTER_CHECKLIST.md#P2-03; 03_MASTER_CHECKLIST.md#P2-04; 03_MASTER_CHECKLIST.md#P2-12; FINAL-REQ/area-6 (criterion 8)
- **Note:** Final release criterion 8 (evidence-based selection) depends on this component.

<a id="nl-bp-069"></a>
### NL-BP-069 - Model/Agent Competence Index fed by targeted, reproducible micro-benchmarks

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-16, P2-17) elevated by final criterion 8
- **Dependencies:** NL-BP-068
- **Acceptance gates:**
  - evaluation runs persist exact model+quantization+role+tools+params+hardware+task and pass/fail evidence
  - targeted micro-benchmarks with hidden oracle; no massive benchmark runs; sample/confidence recorded
  - results invalidated on model/toolchain/hardware change; selection consumes the index
- **Evidence:**
  - SQLite tables measured: no benchmark/evaluation_runs/measurements tables; no benchmark code
  - specifiche/22_MODEL_AGENT_COMPETENCE_INDEX.md
- **Sources:** specifiche/22_MODEL_AGENT_COMPETENCE_INDEX.md; 03_MASTER_CHECKLIST.md#P2-16; 03_MASTER_CHECKLIST.md#P2-17; FINAL-REQ/area-6 (criterion 8)
- **Note:** Needed for evidence-based model selection; no benchmark tables or runs exist.

<a id="nl-bp-072"></a>
### NL-BP-072 - Universal permission model: read/write/execute/delete/network/cloud scopes and grants

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-16; P1-09; P1-15)
- **Dependencies:** none
- **Acceptance gates:**
  - per project/mission/agent grants (once/mission/project/global) for read/write/execute/delete/network/cloud, with revocation and audit
  - symlink/junction realpath and TOCTOU-safe scope enforcement; out-of-scope writes denied and logged
  - SH-05 adversarial test proves broker enforcement and honest OS-sandbox limitations
- **Evidence:**
  - C9a 641c333 + nl_coding_agent/core/permissions.py: scopes read/write/execute/delete/network/cloud with fail-closed defaults, persisted grants in app_settings, transactional audit events, no env/flag bypass
  - tests/test_permissions.py 38 tests: defaults, grant/revoke persistence, project overrides, unknown scope, audit rows, model-tool static check
  - nl_coding_agent/tools/filesystem.py PROTECTED_DIRS + resolve_scoped_path; tests/test_scope_permission.py 2 tests PASS, tests/test_operational_tools.py security test PASS (68-test batch)
  - nl_coding_agent/tools/shell.py shell=True with cwd only (no confinement); no grants/broker/tables in SQLite
  - specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md; docs/history/legacy/AUDIT_REALE_E_LIMITI.md item 5
- **Sources:** specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md; specifiche/15_SICUREZZA_E_PRIVACY.md; 03_MASTER_CHECKLIST.md#P0-16; 03_MASTER_CHECKLIST.md#P1-09; 03_MASTER_CHECKLIST.md#P1-15
- **Note:** Universal permission model implemented backend-side; GUI Settings matrix is a stage-4/5 follow-up.

<a id="nl-bp-074"></a>
### NL-BP-074 - Model-facing tool surface limited to file operations; no false sandbox claims

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-16; SPEC-28 SH-05)
- **Dependencies:** NL-BP-072
- **Acceptance gates:**
  - get_project_tools exposes only read_file/write_file/patch_file/list_dir; no shell/test/git tools for the model
  - verification commands run only through the deterministic tester stage
  - docs state explicitly that candidate code executes with user privileges and no OS sandbox is claimed
- **Evidence:**
  - C2 8871145: model tools reduced to read_file/write_file/patch_file/list_dir; run_command/run_tests/git_diff removed
  - tests/test_operational_tools.py asserts the 4-tool surface; seam test guards single CrewAI invocation point
  - nl_coding_agent/tools/crew_tools.py 4 tools (commit 8871145 C2)
  - tests/test_operational_tools.py::test_crew_tools_binding_limited_to_file_operations - PASS (68-test batch; asserts run_command/run_tests/git_diff absent)
  - docs/07_SAFETY.md currently lacks the staged-harness limitation section (planned C8 in Phase 2 plan)
- **Sources:** specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md; specifiche/28_SELF_HEALING_AGENT_HARNESS.md#2; 03_MASTER_CHECKLIST.md#P0-16
- **Note:** Model-facing tool surface is limited to file operations; no shell/test execution.

<a id="nl-bp-050"></a>
### NL-BP-050 - Persistent Goals > Milestones > Tasks > Missions hierarchy with CRUD

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-02, P1-03)
- **Dependencies:** NL-BP-012
- **Acceptance gates:**
  - goals and milestones tables with relations, dependencies, acceptance criteria and evidence links
  - CRUD + semantic dedup + project association; user-defined goals distinguishable from agent proposals
  - task board/Goals views render the hierarchy; checklist import never auto-ticks completion
- **Evidence:**
  - SQLite tables measured (read-only): missions, tasks, task_attempts, handoffs, verification_runs, events; no goals or milestones tables
  - core/task_graph.py + tests/test_missions_graph.py 4 tests PASS (68-test batch)
  - specifiche/03_GOALS_MILESTONES_TASKS.md; docs/02_SELF_BUILD_ROADMAP.md#Phase-14
- **Sources:** specifiche/03_GOALS_MILESTONES_TASKS.md; 03_MASTER_CHECKLIST.md#P1-02; 03_MASTER_CHECKLIST.md#P1-03; docs/02_SELF_BUILD_ROADMAP.md#Phase-14
- **Note:** Missions/tasks/task_attempts already exist and are persistent; the Goals and Milestones layers and their CRUD/UI do not exist.

<a id="nl-bp-052"></a>
### NL-BP-052 - Single-writer mission lock across processes

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (SPEC-02; docs/CURRENT_STATE.md)
- **Dependencies:** NL-BP-051
- **Acceptance gates:**
  - two processes cannot write the same working tree concurrently
  - stale locks from dead processes are reclaimed safely
  - a test exercises contention and stale-lock recovery
- **Evidence:**
  - nl_coding_agent/core/mission_lock.py (O_EXCL lock, pid liveness, stale reclaim)
  - docs/CURRENT_STATE.md claims single-writer lock; one test patches mission_lock for isolation only (tests/test_selfbuild_mode.py:75)
- **Sources:** specifiche/02_SELF_BUILD_E_RECOVERY.md; specifiche/15_SICUREZZA_E_PRIVACY.md
- **Note:** Implementation exists and stale-pid recovery is coded; no contention test proves it.

<a id="nl-bp-053"></a>
### NL-BP-053 - Task dependency DAG and write-scope collision prevention

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-02; docs/02 Phase 6)
- **Dependencies:** NL-BP-050
- **Acceptance gates:**
  - tasks with unmet dependencies cannot start
  - dependency cycles are detected and rejected
  - tasks with overlapping write scopes are not run concurrently
- **Evidence:**
  - nl_coding_agent/core/task_graph.py
  - tests/test_missions_graph.py::test_task_graph_dependencies, ::test_task_graph_cycle_detection, ::test_task_collision_prevention, ::test_mission_persistence_roundtrip - all PASS (68-test batch)
  - docs/02_SELF_BUILD_ROADMAP.md#Phase-6
- **Sources:** specifiche/03_GOALS_MILESTONES_TASKS.md; specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md; docs/02_SELF_BUILD_ROADMAP.md#Phase-6
- **Note:** Unit-verified at the graph layer; not yet enforced by the live orchestrator for parallel workstreams.

<a id="nl-bp-070"></a>
### NL-BP-070 - Resource-aware scheduler: RAM/VRAM pressure, serialization, unload idle models

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-05)
- **Dependencies:** NL-BP-008
- **Acceptance gates:**
  - scheduler sequences local inference and accounts for measured RAM/VRAM and loaded models
  - idle owned models can be unloaded; checkpoints are not deleted; GUI remains responsive
  - serialize/parallelize decisions are explainable and configurable
- **Evidence:**
  - nl_coding_agent/resources/scheduler.py SequentialScheduler thread
  - nl_coding_agent/models/ollama_registry.py exposes loaded-model query and stop; resources status via nvidia-smi/psutil in core/status.py
  - no VRAM-based scheduling/unload automation (grep decision logic)
- **Sources:** specifiche/13_RESOURCE_SCHEDULER.md; 03_MASTER_CHECKLIST.md#P2-05
- **Note:** A sequential worker scheduler and Ollama list/ps/stop helpers exist; scheduling decisions do not consume measured VRAM pressure or unload idle owned models automatically.

<a id="nl-bp-073"></a>
### NL-BP-073 - Tool Registry for external tools with probe, capabilities and grants

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-15)
- **Dependencies:** NL-BP-072
- **Acceptance gates:**
  - register executable/endpoint with platform, version, checksum, capabilities, health probe and grants
  - Execute grant does not imply Write to the tool directory; tools can be reused without copying
  - GUI Settings > Permissions & External Tools with revocation and history
- **Evidence:**
  - C9b 283a94e + nl_coding_agent/tools/registry.py: read-only ExternalTool descriptors (git, embedded python, pytest, ollama, ffmpeg) and ToolRegistry with fixed-argv shell=False bounded probes; no arbitrary-command API
  - tests/test_tool_registry.py 15 tests + AppServices.list_external_tools read-only API
  - no tool-registry code/tables (grep tool_registry absent)
  - specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md
- **Sources:** specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md; 03_MASTER_CHECKLIST.md#P1-15
- **Note:** Read-only discovery/capability registry implemented; grants are enforced by the permission layer, not by the registry.

<a id="nl-bp-075"></a>
### NL-BP-075 - Operations reliability and diagnostics dashboard

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-14)
- **Dependencies:** NL-BP-051
- **Acceptance gates:**
  - structured logs with correlation IDs; 429/timeout backoff honoring Retry-After; dead-letter/blocked queue
  - Health & Diagnostics view exposes versions, providers, models, last test pass/fail, blocked tasks, space audit and owned processes
  - diagnostic export is redacted; tests for 429/timeout paths
- **Evidence:**
  - C3a d81a168: additive events columns project_id/mission_id/correlation_id/event_kind; supervisor logs correlation ids per run; schema/index tests PASS
  - C3c b9ec909: retry backoff schedule, failure signatures, dead-letter/blocked queue states and WAITING_FOR_RESOURCES/APPROVAL outcomes; scripts/verify_supervisor.py --json read-only diagnostic gate (schema, lease, journals, queue/backlog consistency, no live supervisor, mode default, index validity)
  - C3d dbe3c3b: supervisor status --json, CLI exit codes, background service/queue status, GUI supervisor status label; tests/test_supervisor_core.py + tests/test_supervisor_cli.py PASS
  - no full Health & Diagnostics dashboard, no measured 429/timeout matrix yet; specifiche/24_OPERATIONS_SUPERVISION_HEALTH_AND_DIAGNOSTICS.md
- **Sources:** specifiche/24_OPERATIONS_SUPERVISION_HEALTH_AND_DIAGNOSTICS.md; 03_MASTER_CHECKLIST.md#P1-14
- **Note:** Correlation ids, retry/backoff/dead-letter queue and a read-only diagnostic gate exist; the full diagnostics dashboard and 429/timeout test matrix remain missing, so status stays partial.

<a id="nl-bp-076"></a>
### NL-BP-076 - Cloud escalation enforcement: local-only default, explicit consent

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-06; SPEC-15)
- **Dependencies:** NL-BP-072
- **Acceptance gates:**
  - cloud disabled by default; explicit per-project/mission consent required; UI marks cloud-backed models
  - no source/media leaves the machine before consent; fallback is never silent
  - tests with missing credentials and zero budget; audit trail of cloud decisions
- **Evidence:**
  - C9a 641c333: cloud model and remote endpoint denied by default; explicit CLOUD/NETWORK grant required; enforced in orchestrator._make_llm and cli.make_llm before LLM construction; no bypass flag; local loopback always allowed
  - tests/test_permissions.py covers denial/allow paths and orchestrator._make_llm cloud refusal
  - settings_panel.py Cloud escalation read-only label; no cloud routing code (grep cloud)
  - models/providers.py lists whatever the provider exposes; no local/cloud classification beyond provider kind
  - specifiche/15_SICUREZZA_E_PRIVACY.md; specifiche/05_MODEL_HUB_PROVIDERS.md
- **Sources:** specifiche/15_SICUREZZA_E_PRIVACY.md; specifiche/05_MODEL_HUB_PROVIDERS.md; 03_MASTER_CHECKLIST.md#P1-06
- **Note:** Cloud escalation is local-only by default with explicit consent enforcement.

<a id="nl-bp-077"></a>
### NL-BP-077 - Open arbitrary project with automatic discovery, SQLite profile and Recent Projects

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-01)
- **Dependencies:** none
- **Acceptance gates:**
  - Open Project accepts an arbitrary folder and returns a project profile without any user-authored YAML
  - profile (languages, frameworks, build files, docs) is persisted in SQLite and survives restart
  - Recent Projects lists it and removal from the registry never deletes the folder
- **Evidence:**
  - nl_coding_agent/projects/scanner.py + registry.py
  - tests/test_foundation.py::test_scan_valid_directory, ::test_scan_rejects_nonexistent, ::test_open_project_round_trip - PASS (68-test batch)
  - SQLite measured: 1 project row (id=1, NL Coding Agent, canonical root), 6 project_facts rows
  - docs/CURRENT_STATE.md project registry section; historical smoke project persistence evidence
- **Sources:** specifiche/12_PROJECT_DISCOVERY.md; 03_MASTER_CHECKLIST.md#P1-01; AGENTS.md#no-configuration-ceremony; docs/04_PROJECT_MANAGER.md
- **Note:** One-click project opening exists with zero per-project YAML; scanner covers common stacks and project facts are persisted.

<a id="nl-bp-066"></a>
### NL-BP-066 - Dynamic agent teams / Agent Factory with Automatic/Assisted/Manual modes

- **Area:** AUTONOMY - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-01, P2-02)
- **Dependencies:** NL-BP-050
- **Acceptance gates:**
  - project analysis proposes team composition (roles, count, models) with rationale
  - temporary/vertical specialists can be added/removed/reused; user overrides preserved
  - modes Automatic/Assisted/Manual implemented; no recursive spawning storms
- **Evidence:**
  - orchestrator fixed stages/roles; no agent-factory module (grep)
  - specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md
- **Sources:** specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md; 03_MASTER_CHECKLIST.md#P2-01; 03_MASTER_CHECKLIST.md#P2-02
- **Note:** Orchestrator currently has fixed Developer/Tester/Debugger/Reviewer roles; no team composition analysis.

<a id="nl-bp-067"></a>
### NL-BP-067 - Optimize My Team workflow with before/after preview and apply/customize/keep

- **Area:** AUTONOMY - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-02; SPEC-06)
- **Dependencies:** NL-BP-066, NL-BP-068, NL-BP-069
- **Acceptance gates:**
  - preview compares current vs recommended roles/models/params/parallelism with reasons, estimates vs measurements
  - Apply/Customize/Keep actions persist configuration and history
  - never interrupts an active mission; changes only at mission boundaries
- **Evidence:**
  - no team optimizer code/GUI (grep)
  - specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md; specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md
- **Sources:** specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md; specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md; 03_MASTER_CHECKLIST.md#P2-02
- **Note:** Tied to the Model Advisor and Competence Index; no decorative button shipped.

<a id="nl-bp-071"></a>
### NL-BP-071 - GPU contention detection and authorized cloud fallback policies

- **Area:** AUTONOMY - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-13; SPEC-13A)
- **Dependencies:** NL-BP-070, NL-BP-076
- **Acceptance gates:**
  - external GPU load is detected and AI inference vs GPU test execution is distinguished
  - local-only/ask/preauthorized cloud policies enforced; queue/defer with visible reason
  - adaptive timeouts/heartbeat; no silent cloud; degrades without NVIDIA telemetry
- **Evidence:**
  - no contention/fallback logic (grep)
  - specifiche/13A_GPU_CONTENTION_CLOUD_FALLBACK.md
- **Sources:** specifiche/13A_GPU_CONTENTION_CLOUD_FALLBACK.md; specifiche/13_RESOURCE_SCHEDULER.md; 03_MASTER_CHECKLIST.md#P2-13
- **Note:** No contention detection, adaptive timeouts or cloud policy engine exists.

## Area 4 - Repository hygiene

_Read-only audits, removal of duplicate/generated/obsolete artifacts, consolidated build outputs, one verified candidate, no destructive action without explicit authorization._

<a id="nl-bp-090"></a>
### NL-BP-090 - Read-only distribution/dependency audit tooling with measured report

- **Area:** HYGIENE - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-12, P1-13)
- **Dependencies:** none
- **Acceptance gates:**
  - one command audits workspace size, protected trees, duplicates, caches and declared dependencies without writing to the tree
  - JSON output is machine-readable and a test covers it
  - a committed report records measured totals and cleanup classifications
- **Evidence:**
  - scripts/audit_distribution.py; tests/test_distribution_audit.py::test_json_audit_on_temp_workspace - PASS (16-test safe batch)
  - docs/DISTRIBUTION_AUDIT.md measured totals: 2,215,430,573 B working tree, 99.75% protected, 270 B reclaimable duplicates, zero walk errors
- **Sources:** specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md; 03_MASTER_CHECKLIST.md#P1-12; 03_MASTER_CHECKLIST.md#P1-13; docs/DISTRIBUTION_AUDIT.md
- **Note:** Audit is read-only; it produces evidence but is not authorization to clean anything.

<a id="nl-bp-091"></a>
### NL-BP-091 - Build/dist containment: no sibling directories, packaging excludes vendor/user data/caches

- **Area:** HYGIENE - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-10, P1-13)
- **Dependencies:** none
- **Acceptance gates:**
  - staging refuses output inside the source tree or a non-empty directory and defaults under dist/
  - payload excludes vendor checkouts, user data, logs, tests, docs, scripts, .git and caches
  - no new sibling directory is created under K:/AI by the build paths
- **Evidence:**
  - scripts/stage_portable.py + tests/test_stage_portable.py 6 tests PASS (16-test batch)
  - .gitignore covers python/, crewAI/, crewAI-tools/, data/, logs/, state/, dist/, build/, caches
  - read-only K:/AI listing at 2026-10-28: no nl-coding-agent-portable* or portable-smoke-project directories present
  - AGENTS.md workspace containment rules
- **Sources:** specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md; 13A_GPU_CONTENTION_CLOUD_FALLBACK.md; 03_MASTER_CHECKLIST.md#P1-10; 03_MASTER_CHECKLIST.md#P1-13; AGENTS.md#workspace-containment-and-build-outputs
- **Note:** Current K:/AI inspection shows no nl-coding-agent-portable* siblings; only the internal dist/portable-release candidate exists.

<a id="nl-bp-092"></a>
### NL-BP-092 - One verified release candidate; stale payloads labeled, never auto-deleted

- **Area:** HYGIENE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-12)
- **Dependencies:** NL-BP-091
- **Acceptance gates:**
  - at most one verified release candidate exists with a validation manifest (HEAD, hashes, smoke evidence)
  - older payloads are labeled superseded and kept audit-only until the user authorizes cleanup
  - candidate can be rebuilt from the current HEAD and re-validated
- **Evidence:**
  - dist/portable-release/payload_manifest.json: 23,638 files, 1,507,676,008 B, source K:/AI/Coding Agent, created 2026-10-28T07:41:13 (pre-relocation)
  - no verified-candidate manifest with HEAD/hashes; docs/09_DISTRIBUTION.md describes the historical candidate
  - K:/AI read-only listing: no external portable dirs remain at snapshot
- **Sources:** specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md; docs/09_DISTRIBUTION.md; 03_MASTER_CHECKLIST.md#P1-12
- **Note:** The existing dist payload is stale: its manifest records the pre-relocation source root and was built before C1/C2; it has not been re-validated against current HEAD.

<a id="nl-bp-093"></a>
### NL-BP-093 - External/legacy build artifacts audited with explicit user authorization

- **Area:** HYGIENE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-12; SPEC-23)
- **Dependencies:** NL-BP-090
- **Acceptance gates:**
  - read-only inventory with unique-file detection, verification and size accounting exists for any legacy build directory
  - cleanup proposal lists exact paths, unique contents, risk and rollback; deletion only after explicit authorization
  - current state documented honestly (what exists now, what was removed and when/why)
- **Evidence:**
  - Historical claims: specifiche/23 inventory table and 02_STATO_REALE_DA_VERIFICARE.md (three 1.46 GB portables, smoke fixture)
  - Read-only check 2026-10-28: none of those four paths exist under K:/AI; only dist/portable-release
  - docs/AUDIT_E_MIGRAZIONE_SENZA_RISCHI.md runbook + docs/product-blueprint/tools/audit_external_builds.ps1 (read-only script exists)
- **Sources:** specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md; 02_STATO_REALE_DA_VERIFICARE.md; AUDIT_E_MIGRAZIONE_SENZA_RISCHI.md; 03_MASTER_CHECKLIST.md#P1-12
- **Note:** Blueprint claimed three sibling portables (~1.46 GB each) plus a smoke fixture; measured current state has none. Removal provenance is not recorded in the repository, so the audit/authorization record is incomplete.

<a id="nl-bp-095"></a>
### NL-BP-095 - Repository artifact hygiene: tracked temp scripts, caches, stale files

- **Area:** HYGIENE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P1-13)
- **Dependencies:** NL-BP-090
- **Acceptance gates:**
  - no stale tracked temp/debug scripts in the repository root
  - caches/logs/user data ignored; build working notes confined to build/
  - artifact audit and cleanup decisions recorded before removal (authorization for tracked-file deletion)
- **Evidence:**
  - git ls-files measured: temp_fix_planner.py, temp_fix_title.py, temp_restore.py, temp_restore_planner.py are tracked
  - .pytest_cache/ and package __pycache__/ present on disk (ignored by .gitignore/global config); git status clean at HEAD 8871145
  - docs/DISTRIBUTION_AUDIT.md counts generated caches outside protected trees
- **Sources:** specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md; 03_MASTER_CHECKLIST.md#P1-13; AGENTS.md#workspace-containment-and-build-outputs
- **Note:** Four stale temp scripts remain tracked at the repository root; caches are ignored and the working tree was clean at snapshot.

<a id="nl-bp-094"></a>
### NL-BP-094 - Cleanup preview, trash/quarantine and retention policy implemented

- **Area:** HYGIENE - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-14, P2-15)
- **Dependencies:** NL-BP-056, NL-BP-090
- **Acceptance gates:**
  - cleanup preview shows exact paths, sizes, ownership, references and recoverable space
  - trash/quarantine restore or selective archive restore verified end-to-end
  - auto-clean only app-owned finished-job temporaries; shared caches/models/user data never touched
- **Evidence:**
  - no storage-manager/trash/zip implementation (grep); data/recovery contains only recovery points
  - specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md section 8; specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md
- **Sources:** specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md; specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md; 03_MASTER_CHECKLIST.md#P2-14; 03_MASTER_CHECKLIST.md#P2-15
- **Note:** Policy is specified; no storage manager, trash/quarantine or archive/restore implementation exists.

<a id="nl-bp-096"></a>
### NL-BP-096 - No duplicate runtimes/dependencies beyond one runtime plus one candidate payload

- **Area:** HYGIENE - **Priority:** P2 - **Status:** partial
- **Blueprint priority:** P2 (03_MASTER_CHECKLIST P2-14; SPEC-23)
- **Dependencies:** NL-BP-092
- **Acceptance gates:**
  - exactly one embedded development runtime; release candidate contains at most one independent runtime
  - vendor checkouts excluded from distributions; crewAI-tools absent unless needed
  - measured duplication report and planned consolidation without destructive action
- **Evidence:**
  - docs/DISTRIBUTION_AUDIT.md: python/ 1,720,029,750 B, crewAI/ 489,781,821 B; crewAI-tools absent
  - dist/portable-release/payload_manifest.json: python payload 1,506,844,135 B
  - specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md
- **Sources:** specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md; specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md; 03_MASTER_CHECKLIST.md#P2-14
- **Note:** Measured duplication: 1.72 GB development runtime + 1.51 GB runtime inside the stale dist payload + 490 MB vendor crewAI checkout.

<a id="nl-bp-097"></a>
### NL-BP-097 - Retention and naming policy for dist/build/logs/recovery visible in product

- **Area:** HYGIENE - **Priority:** P3 - **Status:** planned
- **Blueprint priority:** P3 (SPEC-23 acceptance)
- **Dependencies:** NL-BP-094
- **Acceptance gates:**
  - versioned naming and retention policy for builds/logs/recovery/configurable and visible in GUI/CLI
  - no duplicate final/really-final naming; at most one verified candidate
  - policy tests and documentation
- **Evidence:**
  - AGENTS.md policy text only; no retention implementation
  - specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md acceptance list
- **Sources:** specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md
- **Note:** Only workspace rules exist; no product-side retention/naming policy is implemented or exposed.

## Area 5 - Lightweight installation + portable distribution

_Online native bootstrapper, private runtimes into a user-selected location, no global Python/pip/uv/conda, optional components and offline packages, repair/update/cache management, shared downloads without isolation loss, Windows/Linux/macOS verified builds._

<a id="nl-bp-110"></a>
### NL-BP-110 - Portable payload staging script with manifest and safety refusals

- **Area:** DISTRO - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-02, P3-03)
- **Dependencies:** NL-BP-002, NL-BP-091
- **Acceptance gates:**
  - dry-run and real staging produce file counts, sizes and payload_manifest.json
  - script refuses source-internal or non-empty output and skips symlinks
  - tests cover exclusions and refusals
- **Evidence:**
  - scripts/stage_portable.py; docs/PORTABLE_BUILD.md
  - tests/test_stage_portable.py 6 tests PASS (16-test batch)
  - dist/portable-release/payload_manifest.json exists (23,638 files / 1,507,676,008 B)
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; 03_MASTER_CHECKLIST.md#P3-02; 03_MASTER_CHECKLIST.md#P3-03; docs/PORTABLE_BUILD.md
- **Note:** This is staging, not an installer; it copies the development runtime rather than building a clean one.

<a id="nl-bp-111"></a>
### NL-BP-111 - Release payload validated independently from the source tree

- **Area:** DISTRO - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-08)
- **Dependencies:** NL-BP-110
- **Acceptance gates:**
  - payload built from current HEAD is copied to a managed temp directory and run with data outside the payload
  - doctor exits 0, GUI constructs, project opens and persists across restart; no source-tree dependency
  - evidence recorded with HEAD, manifest hashes and cleanup path
- **Evidence:**
  - docs/09_DISTRIBUTION.md and docs/PORTABLE_BUILD.md record historical validation of K:/AI/nl-coding-agent-portable-final (no longer present)
  - current dist/portable-release manifest source is K:/AI/Coding Agent (pre-relocation) and predates C1/C2
  - tests do not cover a real payload run
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; specifiche/19_TEST_MATRIX_E_GATE.md; 03_MASTER_CHECKLIST.md#P3-08; docs/09_DISTRIBUTION.md
- **Note:** Historical validation exists (doctor + offscreen GUI + project persistence from a temp copy), but it predates the relocation and current HEAD; the in-tree dist payload is stale.

<a id="nl-bp-112"></a>
### NL-BP-112 - App-data override NL_DATA_DIR for portable/installed builds

- **Area:** DISTRO - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-03; SPEC-14)
- **Dependencies:** none
- **Acceptance gates:**
  - SQLite and self-build state follow NL_DATA_DIR when set; default behavior unchanged
  - directory is created if needed; tests cover default/override/state placement
  - documented for portable use
- **Evidence:**
  - nl_coding_agent/persistence/database.py (NL_DATA_DIR); tests/test_user_data_path.py 3 tests PASS (68-test batch)
  - docs/PORTABLE_BUILD.md user-data override section; mission #39 completed/APPROVE
- **Sources:** specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md; specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md#5; 03_MASTER_CHECKLIST.md#P3-03
- **Note:** Database and self-build state follow NL_DATA_DIR; launchers do not set it yet.

<a id="nl-bp-113"></a>
### NL-BP-113 - Launchers/installer set app-data location by default, with data migration policy

- **Area:** DISTRO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-03; docs/PORTABLE_BUILD next steps)
- **Dependencies:** NL-BP-112, NL-BP-114
- **Acceptance gates:**
  - portable/installer launcher sets NL_DATA_DIR outside the installation by default
  - existing development data migration is defined and dry-run tested
  - uninstall preserves user data unless a separate confirmed action is chosen
- **Evidence:**
  - launchers are .bat files without NL_DATA_DIR (documents/PORTABLE_BUILD.md states they do not set it yet)
  - no migration code for installed data
- **Sources:** specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md; docs/PORTABLE_BUILD.md; specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md
- **Note:** Requires the installer/bootstrapper; launchers currently inherit the in-tree data directory.

<a id="nl-bp-114"></a>
### NL-BP-114 - Lightweight native bootstrapper per OS/arch with manifest, checksum and rollback

- **Area:** DISTRO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-03, P3-04)
- **Dependencies:** NL-BP-110, NL-BP-112
- **Acceptance gates:**
  - small native launcher downloads verified platform bundles into a user-selected directory with progress/repair/uninstall
  - manifest/checksum verification, resumable download, atomic install and rollback to the previous bundle
  - offline package option; no global Python/pip/uv required
- **Evidence:**
  - no installer/bootstrap code (grep installer absent); docs/09_DISTRIBUTION.md and SPEC-16 are design only
  - dist/portable-release is a one-folder payload, not an installer
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md; 03_MASTER_CHECKLIST.md#P3-03; 03_MASTER_CHECKLIST.md#P3-04; FINAL-REQ/area-5
- **Note:** Nonexistent: no installer, bootstrapper or update channel code in the repository.

<a id="nl-bp-115"></a>
### NL-BP-115 - No global Python/pip/uv/conda requirement; private runtime in a user-selected location

- **Area:** DISTRO - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-03)
- **Dependencies:** NL-BP-114
- **Acceptance gates:**
  - end user never installs Python/pip/uv/conda; the app uses its private runtime
  - install directory is user-selectable and may be non-default
  - verified on a clean Windows machine without global toolchains
- **Evidence:**
  - pyproject.toml has no uv/pipx dependency; payload includes python/ runtime (1.51 GB)
  - no installer/path selection (absent); clean-machine verification not performed
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; specifiche/17_WINDOWS_LINUX_MACOS.md; FINAL-REQ/area-5
- **Note:** Design property is already true for the payload (bundled runtime, no uv dependency), but installation path selection and a clean-machine proof do not exist.

<a id="nl-bp-116"></a>
### NL-BP-116 - Optional components/models installed on demand with no forced downloads

- **Area:** DISTRO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-05)
- **Dependencies:** NL-BP-114
- **Acceptance gates:**
  - components and models are selectable; unselected items are never downloaded
  - downloads are resumable, checksummed and show real size before consent
  - existing local Ollama/model directories can be reused with consent
- **Evidence:**
  - no installer/component-selection code (grep)
  - specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; specifiche/10_SPEECH_ASR_MODELS.md
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; specifiche/10_SPEECH_ASR_MODELS.md; 03_MASTER_CHECKLIST.md#P3-05
- **Note:** Requires installer + speech/model lifecycle; nothing implemented.

<a id="nl-bp-117"></a>
### NL-BP-117 - Repair, update and verify-installation flows with cache management

- **Area:** DISTRO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-04; SPEC-20)
- **Dependencies:** NL-BP-114
- **Acceptance gates:**
  - repair works even when the main runtime is broken, without manual pip
  - verify installation reports component state; update applies atomically with rollback to previous working bundle
  - no update while a mission is active; cache management is app-owned only
- **Evidence:**
  - nl_agent.py doctor exists (read-only diagnostics); no repair/update code
  - specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md
- **Sources:** specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md; 03_MASTER_CHECKLIST.md#P3-04
- **Note:** Only the read-only doctor CLI exists; no repair/update/verify-installation flow.

<a id="nl-bp-118"></a>
### NL-BP-118 - Clean-runtime build instead of duplicating the 1.44 GB development runtime

- **Area:** DISTRO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** P2/P3 (SPEC-16; docs/PORTABLE_BUILD next steps)
- **Dependencies:** NL-BP-110
- **Acceptance gates:**
  - runtime packaging approach evaluated (PyInstaller/Nuitka/clean venv) with measured size and compatibility
  - clean-runtime artifact starts the app and passes smoke tests from a clean directory
  - size reduction vs current payload documented
- **Evidence:**
  - dist/portable-release manifest: python payload 1,506,844,135 B of 1,507,676,008 B total
  - docs/PORTABLE_BUILD.md next steps item 3; docs/DISTRIBUTION_AUDIT.md size plan
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; docs/PORTABLE_BUILD.md; docs/DISTRIBUTION_AUDIT.md
- **Note:** The staged payload is 1.51 GB, almost entirely the copied development python/ tree.

<a id="nl-bp-121"></a>
### NL-BP-121 - License/NOTICE/SBOM audit and secret-free payload

- **Area:** DISTRO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-01)
- **Dependencies:** NL-BP-110
- **Acceptance gates:**
  - licenses audited for CrewAI, PySide6/Qt, Python, bundled tools and model weights
  - NOTICE and dependency manifest/SBOM generated and shipped
  - no credentials, personal SQLite records, logs, private projects or checkpoints in the payload
- **Evidence:**
  - docs/CREWAI_RUNTIME.md license follow-up section
  - dist payload excludes data/, logs/, config/voicebridge.yaml; no NOTICE/SBOM files in payload
  - specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md section Legal/supply chain
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; 03_MASTER_CHECKLIST.md#P3-01; docs/CREWAI_RUNTIME.md
- **Note:** CrewAI license follow-up is documented and the payload excludes user data/config; no NOTICE/SBOM generation or complete audit exists.

<a id="nl-bp-122"></a>
### NL-BP-122 - Reproducible builds: pins, lockfile and immutable build manifest

- **Area:** DISTRO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-08; SPEC-20)
- **Dependencies:** NL-BP-110
- **Acceptance gates:**
  - dependency lockfile and build toolchain versions recorded
  - build produces an immutable manifest with hashes and reproducible steps
  - a clean rebuild reproduces the verified candidate (or differences are explained)
- **Evidence:**
  - pyproject.toml pins crewai==1.15.32 only; no lockfile
  - dist/portable-release/payload_manifest.json lists paths/sizes but no content hashes; build steps are manual docs
  - specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md
- **Sources:** specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md; specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; 03_MASTER_CHECKLIST.md#P3-08
- **Note:** crewai is pinned and a payload manifest exists, but there is no lockfile, hash manifest or scripted reproducible build.

<a id="nl-bp-119"></a>
### NL-BP-119 - Windows/Linux/macOS native builds with native smoke tests

- **Area:** DISTRO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-02, P3-07)
- **Dependencies:** NL-BP-114, NL-BP-118
- **Acceptance gates:**
  - platform-specific private runtimes built on real target OSes; no Windows Python on Linux/Mac
  - native smoke tests: startup, project open, provider discovery, tool call, SQLite, shutdown/recovery, installer
  - support declared only after native test evidence
- **Evidence:**
  - no CI/config for cross-platform builds; no artifacts (repository inspection)
  - specifiche/17_WINDOWS_LINUX_MACOS.md; docs/09_DISTRIBUTION.md
- **Sources:** specifiche/17_WINDOWS_LINUX_MACOS.md; 03_MASTER_CHECKLIST.md#P3-02; 03_MASTER_CHECKLIST.md#P3-07
- **Note:** Only the Windows development runtime exists; no Linux/macOS artifacts or CI. Qt multiplatform alone is not evidence.

<a id="nl-bp-120"></a>
### NL-BP-120 - OS adapter layer: no Windows-only assumptions in shared logic

- **Area:** DISTRO - **Priority:** P2 - **Status:** partial
- **Blueprint priority:** P2 (SPEC-17)
- **Dependencies:** NL-BP-119
- **Acceptance gates:**
  - process/shell/paths/IPC/GPU/update behavior behind OS adapters
  - no hardcoded PowerShell/CUDA/Windows paths in shared business logic
  - per-adapter tests and a cross-platform smoke path
- **Evidence:**
  - tools/shell.py handles Windows OEM decoding only; .bat launchers are Windows-only; main.py has Windows-oriented config paths
  - no adapters module (grep); specifiche/17_WINDOWS_LINUX_MACOS.md
- **Sources:** specifiche/17_WINDOWS_LINUX_MACOS.md; specifiche/01_ARCHITETTURA_E_RUNTIME.md
- **Note:** Some OS-aware handling exists in tools (encoding, protected paths), but there is no adapter boundary and Windows assumptions remain.

<a id="nl-bp-124"></a>
### NL-BP-124 - Shared model downloads/cache reuse without isolation loss

- **Area:** DISTRO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-05; SPEC-10/16)
- **Dependencies:** NL-BP-116
- **Acceptance gates:**
  - existing model directories are detected and reused with consent; no automatic copy
  - optional isolated runtime only for incompatible optional modules, with reason
  - cleanup never deletes shared checkpoints; ownership audit shown
- **Evidence:**
  - no installer/model-management code; specifiche/10_SPEECH_ASR_MODELS.md and specifiche/16
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; specifiche/10_SPEECH_ASR_MODELS.md; 03_MASTER_CHECKLIST.md#P3-05
- **Note:** Requires installer + speech/model management; shared Hugging Face/Ollama caches must never be deleted or duplicated blindly.

<a id="nl-bp-123"></a>
### NL-BP-123 - Optional full offline package

- **Area:** DISTRO - **Priority:** P3 - **Status:** planned
- **Blueprint priority:** P3 (03_MASTER_CHECKLIST P3-06)
- **Dependencies:** NL-BP-114, NL-BP-118
- **Acceptance gates:**
  - offline installer/portable contains private runtime and dependencies (models optional)
  - works without network on a clean machine
  - documented and tested
- **Evidence:**
  - absent (no installer); specifiche/16 and 03_MASTER_CHECKLIST P3-06
- **Sources:** specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md; 03_MASTER_CHECKLIST.md#P3-06
- **Note:** Optional channel; online lightweight bootstrapper is the primary distribution.

## Area 6 - Release acceptance criteria

_Evidence gates for the final product: non-default install path; clean Windows without global Python; relocation survival; clipboard screenshot + drag-and-drop attachments; mic + local transcription; CrewAI workflows and autonomous missions execute; invalid agent edits cannot corrupt verified sources; local model discovery + evidence-based selection; reproducible organized builds._

<a id="nl-bp-141"></a>
### NL-BP-141 - Accepted install on a non-default path

- **Area:** RELEASE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (final release acceptance criterion 1)
- **Dependencies:** NL-BP-114, NL-BP-115
- **Acceptance gates:**
  - installer installs to a user-chosen non-default directory on Windows
  - application starts, opens a project and persists state from that path
  - uninstall preserves user projects/data; evidence recorded
- **Evidence:**
  - Stage-6b portable candidate executed from a managed non-default temp installation path: --help/doctor/imports/incl-flows/GUI-offscreen/persistence PASS; default status FAIL; installer install/uninstall and user-data preservation not measured (manual-pending).
  - no installer/path selection (absent)
  - FINAL-REQ/area-6 criterion 1
- **Sources:** FINAL-REQ/area-6; specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md
- **Note:** Portable payload path acceptance is measured; installer install/uninstall/user-data preservation remain manual-pending.

<a id="nl-bp-142"></a>
### NL-BP-142 - Accepted run on clean Windows without global Python

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (final release acceptance criterion 2)
- **Dependencies:** NL-BP-114, NL-BP-115
- **Acceptance gates:**
  - clean Windows machine/VM without system Python, uv, conda or pip runs install+startup+project+mission
  - all required runtime components come from the bundle
  - evidence recorded with machine description and commands
- **Evidence:**
  - Stage-6b portable candidate smoke on the development machine (not a clean machine): payload runs from a managed temp path; clean Windows without global Python remains manual-pending.
  - docs/PORTABLE_BUILD.md historical payload check (doctor/GUI/project persistence) - not clean-machine and not current HEAD
  - FINAL-REQ/area-6 criterion 2
- **Sources:** FINAL-REQ/area-6; specifiche/19_TEST_MATRIX_E_GATE.md; docs/09_DISTRIBUTION.md#6
- **Note:** Stage-6b candidate smoke is measured on the dev machine only; clean-machine acceptance remains manual-pending.

<a id="nl-bp-143"></a>
### NL-BP-143 - Relocation survival for repository and application data

- **Area:** RELEASE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (final release acceptance criterion 3; SPEC-14)
- **Dependencies:** NL-BP-112
- **Acceptance gates:**
  - repository relocation gate passes read-only with zero failed checks and no stale root in operational paths
  - installed/portable app survives moving its directory or data directory with SQLite identity preserved
  - regression tests cover migration and rollback
- **Evidence:**
  - Stage-6b portable payload staged and run from a managed temp path with NL_DATA_DIR temp; project+mission persisted in temp SQLite; repository relocation gate remains 30/30 PASS; installed-app data migration still absent.
  - build/relocation/verify_relocation_final_lead.json ok=true, 30 checks PASS, canonical root K:/AI/NL Coding Agent (2026-10-28T15:48)
  - docs/WORKSPACE_MIGRATION.md completed record; tests/test_verify_relocation.py and tests/test_project_root_migration.py exist
  - installed-app relocation absent (no installer/data migration)
- **Sources:** FINAL-REQ/area-6; docs/WORKSPACE_MIGRATION.md; specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md
- **Note:** Portable payload relocation to a temp path is measured; installed-app data migration/rollback remains absent.

<a id="nl-bp-144"></a>
### NL-BP-144 - Accepted clipboard screenshot + drag-and-drop attachments end-to-end

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (final release acceptance criterion 4)
- **Dependencies:** NL-BP-027, NL-BP-028, NL-BP-031
- **Acceptance gates:**
  - Windows screenshot copied to clipboard and pasted with Ctrl+V appears as a preview attachment
  - drag-and-drop of multiple files works; attachments are sent to a capability-verified model
  - persisted across restart; evidence captured
- **Evidence:**
  - absent (no chat/attachment/clipboard code)
  - FINAL-REQ/area-6 criterion 4
- **Sources:** FINAL-REQ/area-6; specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md
- **Note:** Depends on Studio multimodal chat; nothing implemented.

<a id="nl-bp-145"></a>
### NL-BP-145 - Accepted microphone + local transcription end-to-end

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (final release acceptance criterion 5)
- **Dependencies:** NL-BP-033, NL-BP-035
- **Acceptance gates:**
  - microphone recording transcribes locally (Qwen3-ASR or Vosk class) and the text is usable in a mission
  - no cloud/network required; disabled ASR does not break the app
  - hardware test recorded with microphone model and OS
- **Evidence:**
  - absent (no ASR/audio code)
  - FINAL-REQ/area-6 criterion 5
- **Sources:** FINAL-REQ/area-6; specifiche/10_SPEECH_ASR_MODELS.md
- **Note:** Depends on the optional speech manager; at least one local engine is required for acceptance.

<a id="nl-bp-146"></a>
### NL-BP-146 - Accepted CrewAI workflows and autonomous missions execute end-to-end

- **Area:** RELEASE - **Priority:** P0 - **Status:** blocked
- **Blueprint priority:** new (final release acceptance criterion 6)
- **Dependencies:** NL-BP-003, NL-BP-007, NL-BP-055, NL-BP-056, NL-BP-057, NL-BP-058, NL-BP-059, NL-BP-061, NL-BP-062
- **Acceptance gates:**
  - a CrewAI workflow modifies a real project, runs tests, passes review and persists evidence
  - an autonomous mission sequence executes from the indexed backlog without new prompts
  - evidence captured for both; failures remain blocked, not completed
- **Evidence:**
  - docs/CURRENT_STATE.md historical missions #16/#24/#36-#41 completed/APPROVE
  - SQLite: missions #44/#45 blocked REJECT (measured); no current end-to-end run
  - docs/PHASE2_HARNESS_INTEGRATION_PLAN.md: staging not wired; final criterion 6 not met
- **Sources:** FINAL-REQ/area-6; specifiche/19_TEST_MATRIX_E_GATE.md; specifiche/28_SELF_HEALING_AGENT_HARNESS.md
- **Note:** BLOCKED: historical cycles ran, but the safety foundation is not wired into the runtime and the latest supervisor missions #44/#45 are blocked.

<a id="nl-bp-147"></a>
### NL-BP-147 - Accepted guarantee: invalid agent edits cannot corrupt verified sources

- **Area:** RELEASE - **Priority:** P0 - **Status:** blocked
- **Blueprint priority:** new (final release acceptance criterion 7; SPEC-28)
- **Dependencies:** NL-BP-055, NL-BP-056, NL-BP-057, NL-BP-058, NL-BP-059
- **Acceptance gates:**
  - adversarial SH-01..SH-07 evidence on a real/isolated workspace: stub+weakened-test patch blocked before any live write
  - dirty/untracked user edits preserved; crash/resume adds no duplicate write
  - repair/rollback succeeds without manual external correction; evidence in SQLite/logs
- **Evidence:**
  - tests/test_staging_broker_adversarial.py SH-01/SH-04 PASS at broker level (68-test batch)
  - SQLite mission #45 blocked after agent overwrote planner/test; post-hoc rollback from baseline (result summary)
  - data/selfbuild_state.json audit_note_42/43 manual restore; docs/history/legacy/AUDIT_REALE_E_LIMITI.md items 1-4
- **Sources:** FINAL-REQ/area-6; specifiche/28_SELF_HEALING_AGENT_HARNESS.md#5; specifiche/27_SELF_CHANGE_GATES_AND_DEPLOY.md
- **Note:** BLOCKED: broker-level SH-01/SH-04 tests pass, but the live pipeline still writes directly to the working tree before the post-hoc gate; mission #45 is a real live overwrite incident.

<a id="nl-bp-148"></a>
### NL-BP-148 - Accepted local model discovery + evidence-based model selection

- **Area:** RELEASE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (final release acceptance criterion 8)
- **Dependencies:** NL-BP-008, NL-BP-009, NL-BP-068, NL-BP-069
- **Acceptance gates:**
  - models are discovered dynamically from local providers with capability probes
  - selection of model/role/params is backed by persisted evidence and confidence, never by name/reputation
  - a comparison of two models on a real task is recorded and reproducible
- **Evidence:**
  - nl_coding_agent/models/providers.py + Ollama registry; 21 models discovered via Ollama API in relocation gate (2026-10-28T15:48); tests/test_model_hub.py 7 PASS
  - no capability/evidence selection: orchestrator uses DEFAULT_*_MODEL constants; no benchmarks DB
- **Sources:** FINAL-REQ/area-6; specifiche/05_MODEL_HUB_PROVIDERS.md; specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md; specifiche/22_MODEL_AGENT_COMPETENCE_INDEX.md
- **Note:** Discovery is verified; capability probes, advisor and competence evidence are missing, so selection is still static defaults.

<a id="nl-bp-149"></a>
### NL-BP-149 - Accepted reproducible, organized builds from a clean environment

- **Area:** RELEASE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (final release acceptance criterion 9)
- **Dependencies:** NL-BP-110, NL-BP-114, NL-BP-122, NL-BP-111
- **Acceptance gates:**
  - a documented clean-checkout build reproduces the verified candidate (manifest/hashes match or differences explained)
  - exactly one organized candidate remains; build directories contain no stray duplicates
  - acceptance evidence recorded with HEAD and toolchain versions
- **Evidence:**
  - Stage-6b reproducible staging: two independent stagings identical tree sha256 80e4664... (23,682 files/1,508,402,351 B); stage-6a source release byte-identical; dist still contains stale portable-release plus stage-6a source candidate pending authorization (not yet one organized candidate).
  - dist/portable-release/payload_manifest.json source K:/AI/Coding Agent (pre-relocation), no hashes
  - no lockfile/CI/build script beyond stage_portable.py
  - docs/DISTRIBUTION_AUDIT.md size plan is arithmetic, not a verified build
- **Sources:** FINAL-REQ/area-6; specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md; specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md
- **Note:** Reproducibility is measured; clean-environment build and the one-organized-candidate state require authorization for stale/extra dist cleanup.

<a id="nl-bp-140"></a>
### NL-BP-140 - Release acceptance matrix runner with recorded evidence and manual-pending labels

- **Area:** RELEASE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P1 (03_MASTER_CHECKLIST P3-08; SPEC-19)
- **Dependencies:** NL-BP-090
- **Acceptance gates:**
  - one documented command/checklist records gate ID, requirement ID, exact command, OS/hardware, env, exit/result, artifacts, timestamp and reviewer
  - hardware/native items are labelled NEEDS_NATIVE_TEST, never PASS
  - release audit template filled for each candidate
- **Evidence:**
  - docs/RELEASE_ACCEPTANCE.md measured 2026-10-28 at HEAD 7dbd40b: candidate 23,682 files/1,508,402,351 B, tree sha256 80e4664..., acceptance matrix with manual-pending labels; default status smoke FAIL (config portability defect).
  - scripts/verify_relocation.py (read-only gate, 30 checks PASS in build/relocation/verify_relocation_final_lead.json); scripts/verify_handoff_and_resume.py exists
  - docs/product-blueprint/templates/RELEASE_AUDIT_TEMPLATE.md exists (template, not executed)
  - no unified acceptance runner; specifiche/19_TEST_MATRIX_E_GATE.md
- **Sources:** specifiche/19_TEST_MATRIX_E_GATE.md; 03_MASTER_CHECKLIST.md#P3-08; templates/RELEASE_AUDIT_TEMPLATE.md
- **Note:** A measured stage-6b acceptance matrix with manual-pending labels now exists; the default status command portability defect still blocks a full pass.

<a id="nl-bp-150"></a>
### NL-BP-150 - Full pytest baseline green with documented measured count

- **Area:** RELEASE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-02; SPEC-19 Gate A)
- **Dependencies:** NL-BP-001
- **Acceptance gates:**
  - python/python.exe -m pytest runs the full suite green (with documented offscreen/no-cache flags if required)
  - count, command, environment and date recorded in CURRENT_STATE and release evidence
  - no test skipped silently to obtain green
- **Evidence:**
  - tests/test_stage_portable.py targeted 8 passed at HEAD 7dbd40b (2026-10-28); full suite deliberately not run by stage-6b acceptance (Lead-run).
  - measured 2026-10-28 at HEAD 7e778da (16:12 Europe/Rome): pytest tests --collect-only = 134 collected; harness component batch 24 passed; key regression batch 37 passed; earlier safe batches 68 + 16 passed at HEAD 8871145
  - docs/CURRENT_STATE.md still reports 65/69 tests (stale); docs/PHASE2_HARNESS_INTEGRATION_PLAN.md expected 103 after C1b (superseded by C3-C5 additions)
  - full-suite run deliberately not performed by this consolidation (mission restrictions)
- **Sources:** specifiche/19_TEST_MATRIX_E_GATE.md; 03_MASTER_CHECKLIST.md#P0-02; docs/CURRENT_STATE.md
- **Note:** Full-suite baseline remains Lead-run; only targeted stage-6b staging tests were executed by this task.

<a id="nl-bp-151"></a>
### NL-BP-151 - Honest, evidence-based current-state documentation with consistent history

- **Area:** RELEASE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** P0 (03_MASTER_CHECKLIST P0-11)
- **Dependencies:** NL-BP-150
- **Acceptance gates:**
  - CURRENT_STATE.md states measured evidence, exact commands and unresolved manual checks; no agent-report-only claims
  - NEXT_SELF_BUILD_MISSION.md matches durable state and the indexed backlog; no contradictory title/goal
  - test counts and mission history consistent across docs, SQLite and selfbuild_state.json
- **Evidence:**
  - docs/RELEASE_ACCEPTANCE.md added with measured stage-6b evidence, explicit manual-pending items and stale-dist authorization request; HARNESS_ACCEPTANCE and CURRENT_STATE updated.
  - docs/CURRENT_STATE.md test counts 65/69 vs measured 106 collected; missing missions #42-#45
  - docs/NEXT_SELF_BUILD_MISSION.md title says Supervisor Persistente while its goal describes P1-01 project discovery
  - data/selfbuild_state.json last_completed_mission_id=43 with audit notes; SQLite has completed #42/#43 and blocked #44/#45
  - this consolidation: docs/PRODUCT_BACKLOG.md, docs/BLUEPRINT_INDEX.md, docs/product-blueprint/INDEX.json
- **Sources:** specifiche/02_SELF_BUILD_E_RECOVERY.md; specifiche/19_TEST_MATRIX_E_GATE.md; 02_STATO_REALE_DA_VERIFICARE.md; 03_MASTER_CHECKLIST.md#P0-11
- **Note:** Stage-6b measured evidence is documented; manual-pending items and the status-portability defect are labelled explicitly.

## Deduplication and merge decisions

All previous IDs are mapped below. A single requirement can absorb several legacy IDs; no legacy entry was silently dropped.

| Legacy source / ID | Merged into | Reason |
|---|---|---|
| `03_MASTER_CHECKLIST.md#P0-01` | [NL-BP-150](#nl-bp-150), [NL-BP-151](#nl-bp-151) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-02` | [NL-BP-150](#nl-bp-150), [NL-BP-013](#nl-bp-013) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-03` | [NL-BP-074](#nl-bp-074), [NL-BP-072](#nl-bp-072) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-04` | [NL-BP-004](#nl-bp-004), [NL-BP-003](#nl-bp-003), [NL-BP-075](#nl-bp-075) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-05` | [NL-BP-003](#nl-bp-003), [NL-BP-001](#nl-bp-001) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-06` | [NL-BP-004](#nl-bp-004), [NL-BP-005](#nl-bp-005), [NL-BP-054](#nl-bp-054) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-07` | [NL-BP-051](#nl-bp-051), [NL-BP-012](#nl-bp-012) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-08` | [NL-BP-051](#nl-bp-051), [NL-BP-056](#nl-bp-056) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-09` | [NL-BP-003](#nl-bp-003) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-10` | [NL-BP-013](#nl-bp-013) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-11` | [NL-BP-151](#nl-bp-151) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-12` | [NL-BP-061](#nl-bp-061), [NL-BP-003](#nl-bp-003) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-13` | [NL-BP-056](#nl-bp-056) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-14` | [NL-BP-061](#nl-bp-061), [NL-BP-062](#nl-bp-062) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-15` | [NL-BP-064](#nl-bp-064), [NL-BP-024](#nl-bp-024) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-16` | [NL-BP-072](#nl-bp-072), [NL-BP-074](#nl-bp-074) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-17` | [NL-BP-055](#nl-bp-055), [NL-BP-057](#nl-bp-057) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P0-18` | [NL-BP-061](#nl-bp-061), [NL-BP-062](#nl-bp-062), [NL-BP-063](#nl-bp-063) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-01` | [NL-BP-077](#nl-bp-077), [NL-BP-043](#nl-bp-043) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-02` | [NL-BP-050](#nl-bp-050), [NL-BP-053](#nl-bp-053), [NL-BP-046](#nl-bp-046) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-03` | [NL-BP-050](#nl-bp-050), [NL-BP-046](#nl-bp-046), [NL-BP-025](#nl-bp-025) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-04` | [NL-BP-008](#nl-bp-008) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-05` | [NL-BP-008](#nl-bp-008), [NL-BP-009](#nl-bp-009), [NL-BP-010](#nl-bp-010) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-06` | [NL-BP-076](#nl-bp-076) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-07` | [NL-BP-020](#nl-bp-020), [NL-BP-021](#nl-bp-021), [NL-BP-022](#nl-bp-022), [NL-BP-045](#nl-bp-045) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-08` | [NL-BP-022](#nl-bp-022), [NL-BP-023](#nl-bp-023), [NL-BP-024](#nl-bp-024) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-09` | [NL-BP-072](#nl-bp-072) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-10` | [NL-BP-091](#nl-bp-091) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-11` | [NL-BP-056](#nl-bp-056), [NL-BP-117](#nl-bp-117) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-12` | [NL-BP-090](#nl-bp-090), [NL-BP-092](#nl-bp-092), [NL-BP-093](#nl-bp-093), [NL-BP-096](#nl-bp-096), [NL-BP-097](#nl-bp-097) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-13` | [NL-BP-090](#nl-bp-090), [NL-BP-091](#nl-bp-091), [NL-BP-095](#nl-bp-095) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-14` | [NL-BP-075](#nl-bp-075) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-15` | [NL-BP-073](#nl-bp-073), [NL-BP-072](#nl-bp-072) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P1-16` | [NL-BP-023](#nl-bp-023), [NL-BP-024](#nl-bp-024), [NL-BP-046](#nl-bp-046) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-01` | [NL-BP-066](#nl-bp-066) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-02` | [NL-BP-066](#nl-bp-066), [NL-BP-067](#nl-bp-067) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-03` | [NL-BP-068](#nl-bp-068) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-04` | [NL-BP-068](#nl-bp-068) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-05` | [NL-BP-070](#nl-bp-070) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-06` | [NL-BP-026](#nl-bp-026), [NL-BP-027](#nl-bp-027), [NL-BP-028](#nl-bp-028), [NL-BP-029](#nl-bp-029) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-07` | [NL-BP-030](#nl-bp-030), [NL-BP-031](#nl-bp-031), [NL-BP-032](#nl-bp-032) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-08` | [NL-BP-035](#nl-bp-035), [NL-BP-033](#nl-bp-033) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-09` | [NL-BP-036](#nl-bp-036) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-10` | [NL-BP-037](#nl-bp-037), [NL-BP-038](#nl-bp-038), [NL-BP-039](#nl-bp-039), [NL-BP-040](#nl-bp-040), [NL-BP-041](#nl-bp-041) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-11` | [NL-BP-043](#nl-bp-043) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-12` | [NL-BP-068](#nl-bp-068) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-13` | [NL-BP-071](#nl-bp-071) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-14` | [NL-BP-094](#nl-bp-094), [NL-BP-036](#nl-bp-036), [NL-BP-097](#nl-bp-097) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-15` | [NL-BP-094](#nl-bp-094) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-16` | [NL-BP-069](#nl-bp-069) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P2-17` | [NL-BP-069](#nl-bp-069) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-01` | [NL-BP-121](#nl-bp-121) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-02` | [NL-BP-110](#nl-bp-110), [NL-BP-119](#nl-bp-119) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-03` | [NL-BP-110](#nl-bp-110), [NL-BP-112](#nl-bp-112), [NL-BP-113](#nl-bp-113), [NL-BP-114](#nl-bp-114), [NL-BP-115](#nl-bp-115) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-04` | [NL-BP-114](#nl-bp-114), [NL-BP-117](#nl-bp-117) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-05` | [NL-BP-116](#nl-bp-116), [NL-BP-035](#nl-bp-035), [NL-BP-124](#nl-bp-124) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-06` | [NL-BP-123](#nl-bp-123) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-07` | [NL-BP-119](#nl-bp-119) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-08` | [NL-BP-140](#nl-bp-140), [NL-BP-142](#nl-bp-142), [NL-BP-111](#nl-bp-111), [NL-BP-149](#nl-bp-149) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `03_MASTER_CHECKLIST.md#P3-09` | [NL-BP-143](#nl-bp-143) | Checklist item was a task, not an atomic requirement; split/merged into the requirements that own its acceptance gates. |
| `V6_INDEX_CHECKLIST_PATCH.md#P0-19..P0-22 (declared only)` | [NL-BP-055](#nl-bp-055), [NL-BP-056](#nl-bp-056), [NL-BP-057](#nl-bp-057), [NL-BP-058](#nl-bp-058), [NL-BP-059](#nl-bp-059), [NL-BP-063](#nl-bp-063) | Declared in the v6 changelog but missing from the actual checklist/index (conflict C1); mapped to the SPEC-28 requirements it describes. |
| `V6_INDEX_CHECKLIST_PATCH.md#P1-17 (declared only)` | [NL-BP-066](#nl-bp-066), [NL-BP-067](#nl-bp-067) | Declared in the v6 changelog but missing from the actual checklist/index (conflict C1); mapped to the SPEC-28 requirements it describes. |
| `docs/PRODUCT_BACKLOG.md (previous consolidation attempt, mission #42)` | [NL-BP-001](#nl-bp-001), [NL-BP-003](#nl-bp-003), [NL-BP-004](#nl-bp-004), [NL-BP-008](#nl-bp-008), [NL-BP-020](#nl-bp-020), [NL-BP-021](#nl-bp-021), [NL-BP-051](#nl-bp-051), [NL-BP-054](#nl-bp-054), [NL-BP-056](#nl-bp-056), [NL-BP-066](#nl-bp-066), [NL-BP-067](#nl-bp-067), [NL-BP-070](#nl-bp-070), [NL-BP-077](#nl-bp-077), [NL-BP-090](#nl-bp-090), [NL-BP-094](#nl-bp-094) | Previous consolidation attempt; every covered item merged into the same stable IDs. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-0` | [NL-BP-090](#nl-bp-090), [NL-BP-150](#nl-bp-150) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-1` | [NL-BP-077](#nl-bp-077) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-2` | [NL-BP-008](#nl-bp-008), [NL-BP-070](#nl-bp-070) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-3` | [NL-BP-020](#nl-bp-020), [NL-BP-021](#nl-bp-021), [NL-BP-046](#nl-bp-046) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-4` | [NL-BP-074](#nl-bp-074), [NL-BP-072](#nl-bp-072) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-5` | [NL-BP-004](#nl-bp-004), [NL-BP-065](#nl-bp-065) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-6` | [NL-BP-053](#nl-bp-053) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-7` | [NL-BP-055](#nl-bp-055), [NL-BP-056](#nl-bp-056), [NL-BP-057](#nl-bp-057), [NL-BP-059](#nl-bp-059), [NL-BP-063](#nl-bp-063) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-8` | [NL-BP-037](#nl-bp-037), [NL-BP-038](#nl-bp-038), [NL-BP-039](#nl-bp-039) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-9` | [NL-BP-068](#nl-bp-068), [NL-BP-069](#nl-bp-069) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-10` | [NL-BP-110](#nl-bp-110), [NL-BP-111](#nl-bp-111), [NL-BP-114](#nl-bp-114), [NL-BP-117](#nl-bp-117) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-11` | [NL-BP-008](#nl-bp-008), [NL-BP-009](#nl-bp-009), [NL-BP-036](#nl-bp-036) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-12` | [NL-BP-068](#nl-bp-068) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-13` | [NL-BP-066](#nl-bp-066), [NL-BP-067](#nl-bp-067) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-14` | [NL-BP-050](#nl-bp-050), [NL-BP-051](#nl-bp-051), [NL-BP-053](#nl-bp-053) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-15` | [NL-BP-033](#nl-bp-033), [NL-BP-034](#nl-bp-034), [NL-BP-035](#nl-bp-035) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-16` | [NL-BP-037](#nl-bp-037), [NL-BP-038](#nl-bp-038), [NL-BP-039](#nl-bp-039), [NL-BP-040](#nl-bp-040), [NL-BP-041](#nl-bp-041), [NL-BP-042](#nl-bp-042), [NL-BP-043](#nl-bp-043), [NL-BP-044](#nl-bp-044) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-17` | [NL-BP-119](#nl-bp-119), [NL-BP-120](#nl-bp-120) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/02_SELF_BUILD_ROADMAP.md#Phase-18` | [NL-BP-114](#nl-bp-114), [NL-BP-116](#nl-bp-116), [NL-BP-117](#nl-bp-117), [NL-BP-123](#nl-bp-123) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/08_ACCEPTANCE_GATES.md#Gate-A` | [NL-BP-001](#nl-bp-001), [NL-BP-150](#nl-bp-150) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/08_ACCEPTANCE_GATES.md#Gate-B` | [NL-BP-077](#nl-bp-077), [NL-BP-046](#nl-bp-046) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/08_ACCEPTANCE_GATES.md#Gate-C` | [NL-BP-008](#nl-bp-008), [NL-BP-070](#nl-bp-070) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/08_ACCEPTANCE_GATES.md#Gate-D` | [NL-BP-020](#nl-bp-020), [NL-BP-021](#nl-bp-021), [NL-BP-044](#nl-bp-044) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/08_ACCEPTANCE_GATES.md#Gate-E` | [NL-BP-090](#nl-bp-090), [NL-BP-140](#nl-bp-140) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/08_ACCEPTANCE_GATES.md#Gate-F` | [NL-BP-003](#nl-bp-003), [NL-BP-004](#nl-bp-004), [NL-BP-012](#nl-bp-012), [NL-BP-072](#nl-bp-072), [NL-BP-074](#nl-bp-074) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/08_ACCEPTANCE_GATES.md#Gate-G` | [NL-BP-055](#nl-bp-055), [NL-BP-056](#nl-bp-056), [NL-BP-057](#nl-bp-057), [NL-BP-059](#nl-bp-059), [NL-BP-063](#nl-bp-063) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/09_DISTRIBUTION.md` | [NL-BP-110](#nl-bp-110), [NL-BP-111](#nl-bp-111), [NL-BP-114](#nl-bp-114), [NL-BP-115](#nl-bp-115), [NL-BP-117](#nl-bp-117), [NL-BP-121](#nl-bp-121), [NL-BP-122](#nl-bp-122), [NL-BP-140](#nl-bp-140), [NL-BP-142](#nl-bp-142) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/03_GUI_SPEC.md` | [NL-BP-020](#nl-bp-020), [NL-BP-021](#nl-bp-021), [NL-BP-024](#nl-bp-024), [NL-BP-044](#nl-bp-044), [NL-BP-045](#nl-bp-045), [NL-BP-046](#nl-bp-046) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/04_PROJECT_MANAGER.md` | [NL-BP-077](#nl-bp-077), [NL-BP-043](#nl-bp-043) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/05_ORCHESTRATION.md` | [NL-BP-003](#nl-bp-003), [NL-BP-005](#nl-bp-005), [NL-BP-012](#nl-bp-012), [NL-BP-066](#nl-bp-066) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/06_RESOURCE_SCHEDULER.md` | [NL-BP-070](#nl-bp-070), [NL-BP-071](#nl-bp-071) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/07_SAFETY.md` | [NL-BP-072](#nl-bp-072), [NL-BP-074](#nl-bp-074), [NL-BP-076](#nl-bp-076) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `docs/01_ARCHITECTURE.md` | [NL-BP-001](#nl-bp-001), [NL-BP-013](#nl-bp-013), [NL-BP-020](#nl-bp-020), [NL-BP-072](#nl-bp-072) | Legacy phase/gate docs are historical roadmaps; their intent is preserved by the listed requirements. |
| `specifiche/* (all 30 spec files)` | [NL-BP-001](#nl-bp-001), [NL-BP-003](#nl-bp-003), [NL-BP-004](#nl-bp-004), [NL-BP-008](#nl-bp-008), [NL-BP-026](#nl-bp-026), [NL-BP-050](#nl-bp-050), [NL-BP-055](#nl-bp-055), [NL-BP-072](#nl-bp-072), [NL-BP-090](#nl-bp-090), [NL-BP-110](#nl-bp-110), [NL-BP-140](#nl-bp-140) | Blueprint specification families are represented by the atomic requirements enumerated from them. |
| `FINAL-PRODUCT-REQUIREMENTS (areas 1-6 from the task brief)` | [NL-BP-006](#nl-bp-006), [NL-BP-007](#nl-bp-007), [NL-BP-026](#nl-bp-026), [NL-BP-027](#nl-bp-027), [NL-BP-028](#nl-bp-028), [NL-BP-033](#nl-bp-033), [NL-BP-034](#nl-bp-034), [NL-BP-042](#nl-bp-042), [NL-BP-044](#nl-bp-044), [NL-BP-050](#nl-bp-050), [NL-BP-055](#nl-bp-055), [NL-BP-061](#nl-bp-061), [NL-BP-062](#nl-bp-062), [NL-BP-068](#nl-bp-068), [NL-BP-069](#nl-bp-069), [NL-BP-114](#nl-bp-114), [NL-BP-115](#nl-bp-115), [NL-BP-141](#nl-bp-141), [NL-BP-142](#nl-bp-142), [NL-BP-143](#nl-bp-143), [NL-BP-144](#nl-bp-144), [NL-BP-145](#nl-bp-145), [NL-BP-146](#nl-bp-146), [NL-BP-147](#nl-bp-147), [NL-BP-148](#nl-bp-148), [NL-BP-149](#nl-bp-149) | Final-product brief areas are represented by the listed release requirements. |

## Conflicts resolved

| ID | Topic | Observation and resolution |
|---|---|---|
| C1 | v6 checklist/index patch not applied | The v6 changelog claims new checklist IDs P0-19..P0-22 and P1-17 plus a SPEC-28 index row, but the actual checklist/index in the repository do not contain them. **Resolution:** SPEC-28 self-healing requirements were enumerated directly from specifiche/28_SELF_HEALING_AGENT_HARNESS.md (SH-01..SH-07 gates) and mapped to NL-BP-055..059, 063, 065, 074, 146, 147. No P0-19..P0-22 IDs were minted as authority. Blueprint maintainers should apply the v6 patch or retire the changelog claim. |
| C2 | MANIFEST.json is incomplete (v5 only) | Measured: 53 files exist under docs/product-blueprint but MANIFEST.json lists 47; missing entries are 07_HANDOFF_SELF_HEALING.md, Prompt.txt, specifiche/28_SELF_HEALING_AGENT_HARNESS.md, V6_CHANGELOG.md, V6_INDEX_CHECKLIST_PATCH.md (MANIFEST.json itself is not self-listed). **Resolution:** docs/product-blueprint/INDEX.json now records the complete source inventory and supersedes MANIFEST.json as the backlog source index. MANIFEST.json was not modified (out of this task's write scope). |
| C3 | External portable directories claimed but absent | Blueprint/history claims three sibling portables (~1.46 GB each) plus K:\AI\portable-smoke-project. Read-only inspection of K:\AI on 2026-10-28 shows none of those four paths; only the internal dist/portable-release payload exists. **Resolution:** Current measurement wins for status. The external-artifact requirement (NL-BP-093) is partial: the audit/authorization record for the removal is not in the repository, so the history cannot be reconstructed from repo evidence. No deletion action was taken by this task. |
| C4 | Self-build state and history disagree across docs/DB/state | CURRENT_STATE ends at mission #41 (65/69 test claims) and says next = new mission; selfbuild_state.json records last_completed=#43 with audit notes; SQLite has completed #42/#43, blocked #44/#45; NEXT_SELF_BUILD_MISSION.md title says 'Supervisor Persistente' while its goal is P1-01 project discovery. **Resolution:** Durable DB + state JSON are treated as the historical record; docs are stale views (NL-BP-151). Mission #44 (continuous supervisor execution) and #45 (project discovery) are blocked/REJECT and are evidence that unattended autonomy is not achieved (NL-BP-063). This backlog is the new durable specification. |
| C5 | Test-count claims disagree | Test counts in docs are 65/69/72/97/103; measured at final snapshot HEAD 7e778da (2026-10-28 16:12) the collection is 134 tests, with 24 harness component tests and 37 key regression tests passing (plus two earlier safe batches of 68+16 at HEAD 8871145). The full suite was intentionally not run by this consolidation. **Resolution:** Reported as measured, not claimed as full-green: NL-BP-150 is partial until a documented full-suite run. Stale counts in state docs must be updated after Phase 2 (NL-BP-151). |
| C6 | Safety harness applied but not wired | The safety modules are applied and tested standalone: staging_broker/recovery_store/code_integrity_gate v2 (C1a), promotion lifecycle (C3), candidate+oracle verification (C4) and harness schema/preflight (C5) landed during consolidation; 24 harness tests pass. However grep still shows no staging/promotion/candidate-verification calls from agents/orchestrator.py, so model writes still reach the live tree before any gate. Mission #45 shows a live stub overwrite followed by rollback. Some docs/audit notes read as if the protections were verified end-to-end. **Resolution:** Status is blocked for the integration requirements NL-BP-055/056/057/147 and partial for NL-BP-058/059 (modules + tests landed, orchestrator wiring pending) and NL-BP-060. Module-level tests are evidence of components only, never of end-to-end protection. This matches audit docs/history/legacy/AUDIT_REALE_E_LIMITI.md and the Phase 2 plan (C6/C7 pending at snapshot). |
| C7 | Blueprint priorities vs final-product release criteria | The blueprint puts multimodal attachments/ASR in P2 and distribution in P3 while the final release acceptance criteria make them mandatory. Conversely the blueprint's P0 self-build items are prerequisites for the release criterion 'invalid agent edits cannot corrupt verified sources'. **Resolution:** Priority semantics are explicitly redefined in this backlog: P0 = release acceptance criterion or hard safety/prerequisite; P1 = coherent product; P2 = advanced blueprint evolution; P3 = polish/extras. Both BP priority and backlog priority are recorded per requirement. |
| C8 | Prior PRODUCT_BACKLOG.md consolidation was incomplete | The previous file lists 13 checklist IDs without acceptance gates, evidence, dependencies, status classification or machine-readable index, and claims 'No duplicates' while covering only part of the checklist. **Resolution:** It is replaced by this consolidated backlog (103 atomic requirements with evidence). Its entries are mapped in the dedup map; mission #42's completion does not prove backlog quality. |
| C9 | Docs say autonomous priority gate is met/verified | Those claims predate the Phase 2 safety audit and the blocked missions #44/#45; they are historical, not current. **Resolution:** Final requirements and current measured evidence override them. NL-BP-146/147 blocked; NL-BP-063 blocked; completion claims are not treated as evidence. |
| C10 | Old Antigravity Gate A-E claim | The legacy handoff criterion (Gates A-E) was explicitly declared insufficient by the blueprint; SPEC-19 requires operational self-build gates (D-J) plus native tests. **Resolution:** Legacy gates are mapped to requirements but are not acceptance evidence. Release acceptance uses NL-BP-140..151 and SPEC-19. |
| C11 | GUI feature expectations vs placeholders | The Model Hub Speech tab and read-only status panels could be mistaken for implemented functionality; they are placeholders/summary surfaces. **Resolution:** Anything with no callable backend is status partial/planned; e.g. speech tab placeholder -> NL-BP-035 planned; read-only model panels -> NL-BP-036 partial. |

## Verification snapshot (2026-10-28)

Measured at git HEAD 8871145 (clean tree, Python 3.12.10):

- `git rev-parse --short HEAD ; git status --porcelain` -> 8871145; clean working tree
- `python/python.exe -m pytest tests --collect-only -q -p no:cacheprovider` -> 134 tests collected in 2.66s at HEAD 7e778da (C5)
- `python/python.exe -m pytest tests/test_promotion_stage.py tests/test_candidate_verification.py tests/test_harness_schema.py -q -p no:cacheprovider` -> 24 passed in 4.44s at HEAD 7e778da (C3 promotion 14 + C4 candidate 7 + C5 harness schema 3)
- `python/python.exe -m pytest tests/test_selfbuild_runner.py tests/test_staging_broker_adversarial.py tests/test_rollback_stub.py tests/test_operational_tools.py tests/test_model_hub.py -q -p no:cacheprovider` -> 37 passed in 2.90s at HEAD 7e778da
- `python/python.exe -m pytest tests/test_crewai_runtime.py tests/test_operational_tools.py tests/test_orchestrator_seam.py tests/test_scope_permission.py tests/test_rollback_stub.py tests/test_staging_broker_adversarial.py tests/test_model_hub.py tests/test_cli_config.py tests/test_user_data_path.py tests/test_version.py tests/test_missions_graph.py tests/test_roadmap.py tests/test_selfbuild_runner.py tests/test_foundation.py -q -p no:cacheprovider` -> 68 passed in 9.39s at HEAD 8871145
- `python/python.exe -m pytest tests/test_gui_smoke.py tests/test_gui_panels.py tests/test_system_status.py tests/test_distribution_audit.py tests/test_stage_portable.py tests/test_selfbuild_mode.py -q -p no:cacheprovider` -> 16 passed in 20.14s at HEAD 8871145
- `read-only SQLite probe (sqlite3 URI mode=ro) against data/nl_coding_agent.sqlite3` -> 1 project; 45 missions total (13 completed, 29 pending, 2 blocked, 1 interrupted; 15 owned by project 1, 30 legacy unowned); tables: projects, project_facts, model_inventory, missions, tasks, task_attempts, app_settings, events, handoffs, verification_runs; no goals/milestones/attachments/benchmarks tables; 151 handoffs, 58 verification_runs, 107 tasks, 77 events, 59 task_attempts
- `read-only manifest completeness probe over docs/product-blueprint` -> 53 files on disk vs 47 listed in MANIFEST.json; 6 not listed (MANIFEST.json, 07_HANDOFF_SELF_HEALING.md, Prompt.txt, SPEC-28, V6_CHANGELOG.md, V6_INDEX_CHECKLIST_PATCH.md)
- `read-only filesystem inventory: dist/, data/, build/, config/, logs/, K:\AI siblings` -> dist/portable-release manifest: 23,638 files / 1,507,676,008 B / source K:\AI\Coding Agent / created 2026-10-28T07:41:13; data/staging/999 leftover; data/recovery/99.json; 16 mission baselines; no nl-coding-agent-portable* or portable-smoke-project directories under K:\AI
- `targeted source inspections (grep / read-only)` -> no Flow usage in app; no staging/promotion calls in orchestrator; selfbuild_runner post-hoc gate at lines 308-310; no multimodal/ASR/LSP/DAP/MCP/goals/benchmarks/tool-registry/installer code; model-facing tools = 4 (C2 commit); tracked temp_*.py scripts at repo root
- `read-only docs: build/relocation/verify_relocation_final_lead.json` -> ok=true, 30 checks PASS, canonical root verified, 21 Ollama models listed (2026-10-28T15:48)

**Caveats:**
- The full pytest suite was intentionally not run by this consolidation (mission restriction: safe/targeted tests only). NL-BP-150 stays partial.
- Historical mission results are recorded in SQLite/docs; they were not replayed. They are accepted only as historical evidence, never as current verification.
- GUI/multimodal/audio absence was established from source inspection and dependency inventory, not from an exhaustive runtime trace.
- Local-model quality and hardware behaviour (audio, GPU, ASR accuracy) cannot be verified in this consolidation.
- The removal of external portable directories (C3) happened outside the repository; authorization/provenance is not recorded in the repo.
- Phase 2 (task-6) was in progress concurrently: statuses are a snapshot at HEAD 7e778da; commits after C5 (C6/C7) may advance NL-BP-055..059/061. Re-verify against the current HEAD before relying on those statuses.
- CrewAI import requires a Windows user profile environment (USERPROFILE/APPDATA): a deliberately stripped environment fails at import inside crewai_core token manager. The documented test commands therefore set the standard Windows env; clean-install acceptance must cover this.

## Source reference legend

- specifiche/NN_*.md#section - Master Blueprint specification (authoritative design source).
- 03_MASTER_CHECKLIST.md#P0-xx - original Blueprint checklist ID (mapped in the dedup table).
- FINAL-REQ/area-N - final-product requirement area N from the task brief (areas 1-6; area 6 holds the release acceptance criteria).
- docs/... - repository documentation; nl_coding_agent/... - runtime code; tests/... - verification evidence.


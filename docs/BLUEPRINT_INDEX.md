# Blueprint Index - stable requirement index

Single index of every consolidated product requirement. Each row has a stable ID (**NL-BP-###**), the product area, the primary source, the original Blueprint priority (where one exists), the evidence-based status and a link to the canonical backlog entry.

> Generated from build/backlog/*.mjs by build/backlog/generate.mjs. Machine-readable form: [INDEX.json](product-blueprint/INDEX.json). Canonical backlog: [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md). Do not renumber IDs; append new ones and mark them PROPOSED until accepted.

**Snapshot:** 2026-10-28 16:12 Europe/Rome - git HEAD 7e778da (clean at snapshot; only the backlog deliverables untracked/modified) - Python 3.12.10 (python/python.exe) - pytest --collect-only = **134 tests collected** (full suite not run by this consolidation; Phase 2 in progress).

**Stage-3 update (2026-10-28, C3a-C3e Tier A):** supervisor schema/store, indexed-backlog planner, supervisor core/CLI/service/GUI and SH-07 Tier A (fake-model two consecutive missions) implemented; NL-BP-061/062 verified, NL-BP-064 partial, NL-BP-063 stays blocked pending Tier B real local-model evidence. Counts: 27 verified / 31 partial / 41 planned / 4 blocked.

## Program execution order (authoritative)

- **Stage 1 - Repository relocation and path reconciliation**: completed (1 requirements; IDs in INDEX.json program_order)
- **Stage 2 - Transactional staging, safety and self-healing**: in_progress (15 requirements; IDs in INDEX.json program_order)
- **Stage 3 - Persistent autonomous supervisor and verified handoff**: completed (engineering; Tier B blocked evidence - docs/SH07_TIERB_EVIDENCE.md) (13 requirements; IDs in INDEX.json program_order; C3a-C3d implemented, SH-07 Tier A verified, Tier B pending)
- **Stage 4 - Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities**: in_progress (40 requirements; IDs in INDEX.json program_order)
- **Stage 5 - Repository cleanup and optimization**: pending (8 requirements; IDs in INDEX.json program_order)
- **Stage 6 - Lightweight portable/bootstrapper and final release testing**: pending (26 requirements; IDs in INDEX.json program_order)

Every row below carries the same requirement ID and evidence; the stage mapping is
authoritative in docs/product-blueprint/INDEX.json (program_stage).
## Status legend

- verified - implemented AND proven in this repository by a named test, a measured command, or both recorded in Evidence.
- partial - implemented or usable but unverified, limited, or missing acceptance evidence (e.g. components exist but are not wired).
- planned - specified but absent, or only a static placeholder exists.
- blocked - the acceptance depends on an incomplete earlier phase/integration; no amount of local work on it alone can make it pass.

## Requirement index

### Area 1 - CrewAI + CrewAI Flows first-class integration (CORE, 13 requirements)

| ID | Requirement | Source | BP priority | Status | Evidence (primary) | Backlog |
|---|---|---|---|---|---|---|
| NL-BP-001 | CrewAI pinned as a native runtime dependency | SPEC-01; CREWAI_RUNTIME.md | P1 (03_MASTER_CHECKLIST P1-05; docs/CREWAI_RUNTIME.md) | verified | pyproject.toml declares dependencies [PySide6, psutil, crewai==1.15.32, PyYAML] | [NL-BP-001](PRODUCT_BACKLOG.md#nl-bp-001) |
| NL-BP-002 | Vendor CrewAI checkout excluded from app runtime and payload | SPEC-23 | P1 (03_MASTER_CHECKLIST P1-05; SPEC-23) | verified | tests/test_crewai_runtime.py (import path proof) - PASS in 68-test targeted batch | [NL-BP-002](PRODUCT_BACKLOG.md#nl-bp-002) |
| NL-BP-003 | Developer -> Tester -> Debugger -> Reviewer mission pipeline with real changes | SPEC-02 | P0 (03_MASTER_CHECKLIST P0-05, P0-09) | partial | nl_coding_agent/agents/orchestrator.py implements the stages, baseline snapshots, scope checks and handoffs | [NL-BP-003](PRODUCT_BACKLOG.md#nl-bp-003) |
| NL-BP-004 | Fail-closed test/verification gate blocks completion | SPEC-07 | P0 (03_MASTER_CHECKLIST P0-06) | verified | C6 bce3b71: fail-closed gate inside the orchestrator; staging tests prove invalid/stub candidates and reviewer REJECT produce blocked/unchanged live tree | [NL-BP-004](PRODUCT_BACKLOG.md#nl-bp-004) |
| NL-BP-005 | Reviewer independence and persisted verdict | 05_ORCHESTRATION.md | P0 (03_MASTER_CHECKLIST P0-06; SPEC-07) | partial | orchestrator reviewer stage persists verdict + handoff | [NL-BP-005](PRODUCT_BACKLOG.md#nl-bp-005) |
| NL-BP-006 | CrewAI Flows first-class integration in a product pipeline | final-area-1 (direct final-product requirement) | new (final product requirement area 1) | planned | tests/test_foundation.py::test_crewai_flow_import proves only the installed package import - PASS in 68-test batch | [NL-BP-006](PRODUCT_BACKLOG.md#nl-bp-006) |
| NL-BP-007 | Flow-based durable autonomous mission pipeline | final-area-1 (direct final-product requirement) | new (final product requirement area 1) | planned | no Flow-based pipeline exists (grep) | [NL-BP-007](PRODUCT_BACKLOG.md#nl-bp-007) |
| NL-BP-008 | Multi-provider Model Hub core: dynamic discovery, health, loaded state, unload | SPEC-05 | P1 (03_MASTER_CHECKLIST P1-04, P1-05) | verified | nl_coding_agent/models/providers.py (OllamaProvider, OpenAICompatibleProvider, build_providers) | [NL-BP-008](PRODUCT_BACKLOG.md#nl-bp-008) |
| NL-BP-009 | Provider capability registry from real probes (tools, JSON, vision, audio, context) | SPEC-05 | P1 (03_MASTER_CHECKLIST P1-05 'capability test reale') | planned | ModelInfo in nl_coding_agent/models/providers.py exposes only provider/name/size/loaded/family/modified/capabilities ... | [NL-BP-009](PRODUCT_BACKLOG.md#nl-bp-009) |
| NL-BP-010 | Configurable role -> model mapping without mandatory per-project YAML | SPEC-05 | P1 (03_MASTER_CHECKLIST P1-05; SPEC-05) | partial | nl_coding_agent/cli.py flags --dev-model, --reviewer-model, --debug-model | [NL-BP-010](PRODUCT_BACKLOG.md#nl-bp-010) |
| NL-BP-011 | Mission configuration snapshot for reproducibility | SPEC-18 | P1 (SPEC-05; SPEC-18; SPEC-21) | partial | handoff payloads include "model": <model_name> per stage (orchestrator.py lines ~718, 864, 958) | [NL-BP-011](PRODUCT_BACKLOG.md#nl-bp-011) |
| NL-BP-012 | Structured handoff contract persisted in SQLite | 05_ORCHESTRATION.md | P1 (03_MASTER_CHECKLIST P1-02/P1-03) | verified | SQLite PRAGMA table_info(handoffs) measured: [id, mission_id, from_role, to_role, summary, payload, created_at] | [NL-BP-012](PRODUCT_BACKLOG.md#nl-bp-012) |
| NL-BP-013 | Windows console/Unicode encoding hardening at the application boundary | SPEC-01 | P0 (03_MASTER_CHECKLIST P0-10) | verified | nl_coding_agent/tools/shell.py decode_output + UTF-8 child env (_UTF8_CHILD_ENV) | [NL-BP-013](PRODUCT_BACKLOG.md#nl-bp-013) |

### Area 2 - Studio GUI + multimodal chat (STUDIO, 27 requirements)

| ID | Requirement | Source | BP priority | Status | Evidence (primary) | Backlog |
|---|---|---|---|---|---|---|
| NL-BP-020 | Studio shell with NL branding: logo, design tokens, dark theme | SPEC-08 | P1 (03_MASTER_CHECKLIST P1-07) | verified | assets/LogoMio.svg and assets/theme.tokens.json exist | [NL-BP-020](PRODUCT_BACKLOG.md#nl-bp-020) |
| NL-BP-021 | Navigation shell: sidebar, stacked panels, resizable splitters, inspector, log, status bar | SPEC-08 | P1 (03_MASTER_CHECKLIST P1-07) | partial | nl_coding_agent/gui/main_window.py: stack indices 0-6 (7 pages incl. Autonomy), QSplitter layout, inspector + log + supervisor status bar | [NL-BP-021](PRODUCT_BACKLOG.md#nl-bp-021) |
| NL-BP-022 | Settings panel surfacing project/runtime/provider configuration | SPEC-08 | P1 (03_MASTER_CHECKLIST P1-07/P1-08) | partial | nl_coding_agent/gui/widgets/settings_panel.py rows: Project root, SQLite database, Ollama base URL, Model config, Clo... | [NL-BP-022](PRODUCT_BACKLOG.md#nl-bp-022) |
| NL-BP-023 | Self-Build controls under Settings > Advanced (modes, plan, limits, history, stop) | SPEC-08 | P1 (03_MASTER_CHECKLIST P1-08, P1-16) | planned | settings_panel.py contains no self-build/autonomy controls | [NL-BP-023](PRODUCT_BACKLOG.md#nl-bp-023) |
| NL-BP-024 | Emergency Pause/Stop always reachable during an active mission | SPEC-21 | P0 (03_MASTER_CHECKLIST P0-15; SPEC-21 governance) | planned | no stop/pause widget exists (grep over GUI) | [NL-BP-024](PRODUCT_BACKLOG.md#nl-bp-024) |
| NL-BP-025 | Mission creation, run and resume from the GUI | SPEC-08 | P1 (03_MASTER_CHECKLIST P1-03) | partial | nl_coding_agent/gui/widgets/projects_panel.py New Mission QInputDialog + create_mission | [NL-BP-025](PRODUCT_BACKLOG.md#nl-bp-025) |
| NL-BP-026 | Multimodal Mission Chat input: text, multi-file picker, drag-and-drop | SPEC-09 | P2 (03_MASTER_CHECKLIST P2-06) | planned | grep: no chat widget, no drag/drop handlers, no attachment model (GUI has dialogs, file viewer, task board only) | [NL-BP-026](PRODUCT_BACKLOG.md#nl-bp-026) |
| NL-BP-027 | Ctrl+V screenshot/image paste including Windows screenshots | SPEC-09 | P2 (03_MASTER_CHECKLIST P2-06) | planned | no clipboard handling code (grep clipboard/QClipboard absent) | [NL-BP-027](PRODUCT_BACKLOG.md#nl-bp-027) |
| NL-BP-028 | Attachment UX: previews, removal, type handling, explicit submit | SPEC-09 | P2 (03_MASTER_CHECKLIST P2-06) | planned | no attachment UI (grep) | [NL-BP-028](PRODUCT_BACKLOG.md#nl-bp-028) |
| NL-BP-029 | Attachment provenance persistence across restart | SPEC-09 | P2 (03_MASTER_CHECKLIST P2-06; SPEC-09/18) | planned | SQLite tables measured: no media_attachments, assets or attachments tables | [NL-BP-029](PRODUCT_BACKLOG.md#nl-bp-029) |
| NL-BP-030 | Media backends: PDF/Office/text/log/code/JSON/CSV extraction and safe archives | SPEC-09 | P2 (03_MASTER_CHECKLIST P2-07) | planned | no document/media parser modules (only an extension allowlist in file_viewer.py) | [NL-BP-030](PRODUCT_BACKLOG.md#nl-bp-030) |
| NL-BP-031 | Capability-aware routing of images and attachments to supporting models | SPEC-09 | P2 (03_MASTER_CHECKLIST P2-07) | planned | no capability-aware routing (grep vision/attachment absent) | [NL-BP-031](PRODUCT_BACKLOG.md#nl-bp-031) |
| NL-BP-032 | Audio/video media backends: transcription and frame sampling/audio extraction | SPEC-09 | P2 (03_MASTER_CHECKLIST P2-07) | planned | no audio/video/ffmpeg integration in nl_coding_agent/ (grep) | [NL-BP-032](PRODUCT_BACKLOG.md#nl-bp-032) |
| NL-BP-033 | Microphone push-to-talk/dictation with editable local transcript | SPEC-10 | P2 (03_MASTER_CHECKLIST P2-08) elevated by release criterion 5 | planned | no microphone/audio capture code (grep) | [NL-BP-033](PRODUCT_BACKLOG.md#nl-bp-033) |
| NL-BP-034 | Optional text-to-speech with local model discovery/install/switch/unload | final-area-2 (direct final-product requirement) | new (final product requirement area 2) | planned | no TTS code (grep tts/speech absent outside a placeholder label) | [NL-BP-034](PRODUCT_BACKLOG.md#nl-bp-034) |
| NL-BP-035 | Speech/ASR manager: Qwen3-ASR, Vosk, Faster-Whisper, WhisperX catalog and lifecycle | SPEC-10 | P2 (03_MASTER_CHECKLIST P2-08) elevated by release criterion 5 | planned | nl_coding_agent/gui/widgets/models_panel.py Speech tab is a placeholder label ('No speech engine is installed') | [NL-BP-035](PRODUCT_BACKLOG.md#nl-bp-035) |
| NL-BP-036 | Model lifecycle UI: install/load/unload/uninstall and storage audit | SPEC-14 | P2 (03_MASTER_CHECKLIST P2-09) | partial | providers.py supports unload (Ollama stop) | [NL-BP-036](PRODUCT_BACKLOG.md#nl-bp-036) |
| NL-BP-037 | Integrated code editor (maintained component) with tabs and highlighting | SPEC-11 | P2 (03_MASTER_CHECKLIST P2-10) | planned | nl_coding_agent/gui/widgets/file_viewer.py is read-only QFileSystemModel + QPlainTextEdit | [NL-BP-037](PRODUCT_BACKLOG.md#nl-bp-037) |
| NL-BP-038 | Integrated terminal/PTY with command policy | SPEC-11 | P2 (03_MASTER_CHECKLIST P2-10) | planned | no terminal widget (grep) | [NL-BP-038](PRODUCT_BACKLOG.md#nl-bp-038) |
| NL-BP-039 | Git UI: status, branches, diff, selective staging | SPEC-11 | P2 (03_MASTER_CHECKLIST P2-10) | planned | nl_coding_agent/tools/git_tools.py provides get_git_status/get_git_diff | [NL-BP-039](PRODUCT_BACKLOG.md#nl-bp-039) |
| NL-BP-040 | Test explorer, problems panel and debugger integration (DAP) | SPEC-11 | P2 (03_MASTER_CHECKLIST P2-10) | planned | task_board.py shows verification runs/handoffs only | [NL-BP-040](PRODUCT_BACKLOG.md#nl-bp-040) |
| NL-BP-041 | LSP integration for diagnostics, completion and symbols | SPEC-11 | P2 (03_MASTER_CHECKLIST P2-10) | planned | grep LSP: only false positives inside Qt class names | [NL-BP-041](PRODUCT_BACKLOG.md#nl-bp-041) |
| NL-BP-042 | MCP tool integration | final-area-2 (direct final-product requirement) | new (final product requirement area 2; SPEC-11) | planned | no MCP code (grep only finds a ctypes cp call) | [NL-BP-042](PRODUCT_BACKLOG.md#nl-bp-042) |
| NL-BP-043 | Project explorer, search, indexing and targeted context retrieval | SPEC-12 | P2 (03_MASTER_CHECKLIST P2-11) | partial | nl_coding_agent/gui/widgets/file_viewer.py read-only browser with text filter | [NL-BP-043](PRODUCT_BACKLOG.md#nl-bp-043) |
| NL-BP-044 | Accessibility and usability: keyboard focus, DPI scaling, contrast, shortcuts, command palette | SPEC-08 | P1 (SPEC-08; final area 2 'accessible') | planned | gui/theme.py defines focus styles | [NL-BP-044](PRODUCT_BACKLOG.md#nl-bp-044) |
| NL-BP-045 | Non-blocking responsive UI with explicit empty/loading/error/offline states | SPEC-08 | P1 (03_MASTER_CHECKLIST P1-07; SPEC-08) | partial | ModelHubFetchThread in gui/widgets/models_panel.py | [NL-BP-045](PRODUCT_BACKLOG.md#nl-bp-045) |
| NL-BP-046 | Project dashboard and agent/task visualization | 03_GUI_SPEC.md | P1 (03_MASTER_CHECKLIST P1-03, P1-07) | partial | gui/widgets/projects_panel.py, task_board.py, agents_panel.py, inspector_panel.py, log_panel.py | [NL-BP-046](PRODUCT_BACKLOG.md#nl-bp-046) |

### Area 3 - Universal autonomous development (AUTONOMY, 28 requirements)

| ID | Requirement | Source | BP priority | Status | Evidence (primary) | Backlog |
|---|---|---|---|---|---|---|
| NL-BP-050 | Persistent Goals > Milestones > Tasks > Missions hierarchy with CRUD | SPEC-03 | P1 (03_MASTER_CHECKLIST P1-02, P1-03) | partial | SQLite tables measured (read-only): missions, tasks, task_attempts, handoffs, verification_runs, events | [NL-BP-050](PRODUCT_BACKLOG.md#nl-bp-050) |
| NL-BP-051 | Durable mission/task persistence, resume and idempotent recovery | SPEC-02 | P0 (03_MASTER_CHECKLIST P0-07, P0-08) | partial | persistence/database.py schema + migrations | [NL-BP-051](PRODUCT_BACKLOG.md#nl-bp-051) |
| NL-BP-052 | Single-writer mission lock across processes | nl_coding_agent/core/mission_lock.py (implementation) | P1 (SPEC-02; docs/CURRENT_STATE.md) | partial | nl_coding_agent/core/mission_lock.py (O_EXCL lock, pid liveness, stale reclaim) | [NL-BP-052](PRODUCT_BACKLOG.md#nl-bp-052) |
| NL-BP-053 | Task dependency DAG and write-scope collision prevention | SPEC-03 | P1 (03_MASTER_CHECKLIST P1-02; docs/02 Phase 6) | verified | nl_coding_agent/core/task_graph.py | [NL-BP-053](PRODUCT_BACKLOG.md#nl-bp-053) |
| NL-BP-054 | Evidence-based completion: no mission completes without passing gates | SPEC-07 | P0 (03_MASTER_CHECKLIST P0-06; SPEC-07) | verified | C6 bce3b71: _finalize_completed only after verified promotion; _finalize_blocked/_finalize_interrupted never report applied changes | [NL-BP-054](PRODUCT_BACKLOG.md#nl-bp-054) |
| NL-BP-055 | Staged candidate writes: every model mutation stays off the live tree | SPEC-28 | P0 (03_MASTER_CHECKLIST P0-17; SPEC-28 invariants) | verified | C6 bce3b71: developer/debugger tools, JSON tool calls and text fallback write only stage.workspace; promotion is the only live-write path | [NL-BP-055](PRODUCT_BACKLOG.md#nl-bp-055) |
| NL-BP-056 | Pre-edit recovery points, compare-and-swap rollback and baseline provenance | SPEC-02A | P0 (03_MASTER_CHECKLIST P0-13) | verified | C6 bce3b71: promotion.ensure_recovery_point before live writes; CAS drift check; rollback_from_snapshot(expected_post_hashes) | [NL-BP-056](PRODUCT_BACKLOG.md#nl-bp-056) |
| NL-BP-057 | Stub/weak-test integrity gate enforced before promotion | SPEC-27 | P0 (03_MASTER_CHECKLIST P0-17; SPEC-27; SPEC-28 SH-01/SH-04) | verified | C6 bce3b71: promotion.validate (AST stub/weak-test, scope, protected/input paths) before candidate verification; post-hoc runner gate removed in C7 3790aaf | [NL-BP-057](PRODUCT_BACKLOG.md#nl-bp-057) |
| NL-BP-058 | Independent candidate + oracle verification before promotion | SPEC-28 | P0 (SPEC-28 section 5; SPEC-19; SH-04) | verified | C6 bce3b71: tester gate runs candidate_verification.verify_candidate (candidate + baseline-test oracle) in disposable copies; verification_runs rows recorded | [NL-BP-058](PRODUCT_BACKLOG.md#nl-bp-058) |
| NL-BP-059 | Promotion journal, CAS and crash reconciliation | SPEC-28 | P0 (03_MASTER_CHECKLIST P0-13; SPEC-28 SH-03) | verified | C6 bce3b71: promotion.promote/journal/reconcile wired in _run_locked (promotion-complete resume, conflict -> blocked) | [NL-BP-059](PRODUCT_BACKLOG.md#nl-bp-059) |
| NL-BP-060 | Fail-closed mission status semantics (no false APPROVE/completed) | SPEC-28 | P0 (SPEC-28 invariant 9; SPEC-19) | verified | C6 bce3b71: completed only after promotion; blocked on every gate failure; staged paths not reported as applied changes | [NL-BP-060](PRODUCT_BACKLOG.md#nl-bp-060) |
| NL-BP-061 | Supervisor daemon independent of the chat/LLM with durable queue, lease and preflight | SPEC-21 | P0 (03_MASTER_CHECKLIST P0-14, P0-15, P0-18) | verified | C3a d81a168 + C3c b9ec909 + C3d dbe3c3b: core/supervisor.py lease/heartbeat + preflight + queue loop, persistence/supervisor_store.py durable state, CLI/service/GUI surfaces; tests/test_supervisor_store.py 17, test_supervisor_core.py 33, test_supervisor_cli.py 20 PASS | [NL-BP-061](PRODUCT_BACKLOG.md#nl-bp-061) |
| NL-BP-062 | Automatic next-mission selection from the indexed backlog | SPEC-26 | P0 (03_MASTER_CHECKLIST P0-14, P0-18) | verified | C3b c91e0c9 core/backlog.py fail-closed INDEX.json loader + program-stage gate + dedupe/idempotency; tests/test_backlog_planner.py 20 PASS; tests/test_supervisor_sh07.py 7 PASS (two consecutive requirements from a fixture indexed backlog, no roadmap dependency) | [NL-BP-062](PRODUCT_BACKLOG.md#nl-bp-062) |
| NL-BP-063 | Two consecutive missions with local models and no manual repair | SPEC-28 | P0 (03_MASTER_CHECKLIST P0-18; SPEC-28 SH-07) | blocked | Tier A fake-model PASS (tests/test_supervisor_sh07.py 7 tests + scripts/run_supervisor_sh07.py --mode fake evidence); Tier B real local-model evidence NOT executed and requires explicit authorization | [NL-BP-063](PRODUCT_BACKLOG.md#nl-bp-063) |
| NL-BP-064 | Autonomy modes Off/Assisted/Automatic with budgets, approvals and stop/pause | SPEC-26 | P0 (03_MASTER_CHECKLIST P0-15; SPEC-26) | partial | C3c b9ec909 + C3d dbe3c3b: SupervisorConfig persisted modes/budgets, durable stop/pause/resume, CLI --confirm-assisted, Autonomy GUI page; approvals flow only partial | [NL-BP-064](PRODUCT_BACKLOG.md#nl-bp-064) |
| NL-BP-065 | Bounded repair loop driven by structured diagnostics | SPEC-28 | P0 (SPEC-28 section 4; SPEC-07 retries) | verified | C9b 283a94e + tests/test_harness_repair.py: scripted failing candidate -> one debugger repair -> candidate+oracle pass -> reviewer APPROVE -> one promotion -> completed (verification rows fail,fail,pass,pass) | [NL-BP-065](PRODUCT_BACKLOG.md#nl-bp-065) |
| NL-BP-066 | Dynamic agent teams / Agent Factory with Automatic/Assisted/Manual modes | SPEC-04 | P2 (03_MASTER_CHECKLIST P2-01, P2-02) | planned | orchestrator fixed stages/roles | [NL-BP-066](PRODUCT_BACKLOG.md#nl-bp-066) |
| NL-BP-067 | Optimize My Team workflow with before/after preview and apply/customize/keep | SPEC-06 | P2 (03_MASTER_CHECKLIST P2-02; SPEC-06) | planned | no team optimizer code/GUI (grep) | [NL-BP-067](PRODUCT_BACKLOG.md#nl-bp-067) |
| NL-BP-068 | Explainable Model Advisor with profiles and per-agent parameters | SPEC-06 | P2 (03_MASTER_CHECKLIST P2-03, P2-04, P2-12) elevated by final criterion 8 | planned | no advisor module | [NL-BP-068](PRODUCT_BACKLOG.md#nl-bp-068) |
| NL-BP-069 | Model/Agent Competence Index fed by targeted, reproducible micro-benchmarks | SPEC-22 | P2 (03_MASTER_CHECKLIST P2-16, P2-17) elevated by final criterion 8 | planned | SQLite tables measured: no benchmark/evaluation_runs/measurements tables | [NL-BP-069](PRODUCT_BACKLOG.md#nl-bp-069) |
| NL-BP-070 | Resource-aware scheduler: RAM/VRAM pressure, serialization, unload idle models | SPEC-13 | P2 (03_MASTER_CHECKLIST P2-05) | partial | nl_coding_agent/resources/scheduler.py SequentialScheduler thread | [NL-BP-070](PRODUCT_BACKLOG.md#nl-bp-070) |
| NL-BP-071 | GPU contention detection and authorized cloud fallback policies | SPEC-13A | P2 (03_MASTER_CHECKLIST P2-13; SPEC-13A) | planned | no contention/fallback logic (grep) | [NL-BP-071](PRODUCT_BACKLOG.md#nl-bp-071) |
| NL-BP-072 | Universal permission model: read/write/execute/delete/network/cloud scopes and grants | SPEC-25 | P0 (03_MASTER_CHECKLIST P0-16; P1-09; P1-15) | verified | C9a 641c333 + nl_coding_agent/core/permissions.py: scopes read/write/execute/delete/network/cloud with fail-closed defaults, persisted grants in app_settings, transactional audit events, no env/flag bypass | [NL-BP-072](PRODUCT_BACKLOG.md#nl-bp-072) |
| NL-BP-073 | Tool Registry for external tools with probe, capabilities and grants | SPEC-25 | P1 (03_MASTER_CHECKLIST P1-15) | verified | C9b 283a94e + nl_coding_agent/tools/registry.py: read-only ExternalTool descriptors (git, embedded python, pytest, ollama, ffmpeg) and ToolRegistry with fixed-argv shell=False bounded probes; no arbitrary-command API | [NL-BP-073](PRODUCT_BACKLOG.md#nl-bp-073) |
| NL-BP-074 | Model-facing tool surface limited to file operations; no false sandbox claims | SPEC-28 | P0 (03_MASTER_CHECKLIST P0-16; SPEC-28 SH-05) | verified | C2 8871145: model tools reduced to read_file/write_file/patch_file/list_dir; run_command/run_tests/git_diff removed | [NL-BP-074](PRODUCT_BACKLOG.md#nl-bp-074) |
| NL-BP-075 | Operations reliability and diagnostics dashboard | SPEC-24 | P1 (03_MASTER_CHECKLIST P1-14) | partial | C3a correlation columns + C3c retry/backoff/dead-letter + scripts/verify_supervisor.py read-only gate + supervisor status --json; full Health & Diagnostics dashboard and 429/timeout matrix still missing | [NL-BP-075](PRODUCT_BACKLOG.md#nl-bp-075) |
| NL-BP-076 | Cloud escalation enforcement: local-only default, explicit consent | SPEC-15 | P1 (03_MASTER_CHECKLIST P1-06; SPEC-15) | verified | C9a 641c333: cloud model and remote endpoint denied by default; explicit CLOUD/NETWORK grant required; enforced in orchestrator._make_llm and cli.make_llm before LLM construction; no bypass flag; local loopback always allowed | [NL-BP-076](PRODUCT_BACKLOG.md#nl-bp-076) |
| NL-BP-077 | Open arbitrary project with automatic discovery, SQLite profile and Recent Projects | SPEC-12 | P1 (03_MASTER_CHECKLIST P1-01) | verified | nl_coding_agent/projects/scanner.py + registry.py | [NL-BP-077](PRODUCT_BACKLOG.md#nl-bp-077) |

### Area 4 - Repository hygiene (HYGIENE, 8 requirements)

| ID | Requirement | Source | BP priority | Status | Evidence (primary) | Backlog |
|---|---|---|---|---|---|---|
| NL-BP-090 | Read-only distribution/dependency audit tooling with measured report | SPEC-23 | P1 (03_MASTER_CHECKLIST P1-12, P1-13) | verified | scripts/audit_distribution.py | [NL-BP-090](PRODUCT_BACKLOG.md#nl-bp-090) |
| NL-BP-091 | Build/dist containment: no sibling directories, packaging excludes vendor/user data/caches | AGENTS.md | P1 (03_MASTER_CHECKLIST P1-10, P1-13) | verified | scripts/stage_portable.py + tests/test_stage_portable.py 6 tests PASS (16-test batch) | [NL-BP-091](PRODUCT_BACKLOG.md#nl-bp-091) |
| NL-BP-092 | One verified release candidate; stale payloads labeled, never auto-deleted | SPEC-23 | P1 (03_MASTER_CHECKLIST P1-12) | partial | dist/portable-release/payload_manifest.json: 23,638 files, 1,507,676,008 B, source K:/AI/Coding Agent, created 2026-1... | [NL-BP-092](PRODUCT_BACKLOG.md#nl-bp-092) |
| NL-BP-093 | External/legacy build artifacts audited with explicit user authorization | SPEC-23 | P1 (03_MASTER_CHECKLIST P1-12; SPEC-23) | partial | Historical claims: specifiche/23 inventory table and 02_STATO_REALE_DA_VERIFICARE.md (three 1.46 GB portables, smoke ... | [NL-BP-093](PRODUCT_BACKLOG.md#nl-bp-093) |
| NL-BP-094 | Cleanup preview, trash/quarantine and retention policy implemented | SPEC-02A | P2 (03_MASTER_CHECKLIST P2-14, P2-15) | planned | no storage-manager/trash/zip implementation (grep) | [NL-BP-094](PRODUCT_BACKLOG.md#nl-bp-094) |
| NL-BP-095 | Repository artifact hygiene: tracked temp scripts, caches, stale files | SPEC-23 | P1 (03_MASTER_CHECKLIST P1-13) | partial | git ls-files measured: temp_fix_planner.py, temp_fix_title.py, temp_restore.py, temp_restore_planner.py are tracked | [NL-BP-095](PRODUCT_BACKLOG.md#nl-bp-095) |
| NL-BP-096 | No duplicate runtimes/dependencies beyond one runtime plus one candidate payload | SPEC-23 | P2 (03_MASTER_CHECKLIST P2-14; SPEC-23) | partial | docs/DISTRIBUTION_AUDIT.md: python/ 1,720,029,750 B, crewAI/ 489,781,821 B | [NL-BP-096](PRODUCT_BACKLOG.md#nl-bp-096) |
| NL-BP-097 | Retention and naming policy for dist/build/logs/recovery visible in product | SPEC-23 | P3 (SPEC-23 acceptance) | planned | AGENTS.md policy text only | [NL-BP-097](PRODUCT_BACKLOG.md#nl-bp-097) |

### Area 5 - Lightweight installation + portable distribution (DISTRO, 15 requirements)

| ID | Requirement | Source | BP priority | Status | Evidence (primary) | Backlog |
|---|---|---|---|---|---|---|
| NL-BP-110 | Portable payload staging script with manifest and safety refusals | SPEC-16 | P3 (03_MASTER_CHECKLIST P3-02, P3-03) | verified | scripts/stage_portable.py | [NL-BP-110](PRODUCT_BACKLOG.md#nl-bp-110) |
| NL-BP-111 | Release payload validated independently from the source tree | 09_DISTRIBUTION.md | P3 (03_MASTER_CHECKLIST P3-08) | partial | docs/09_DISTRIBUTION.md and docs/PORTABLE_BUILD.md record historical validation of K:/AI/nl-coding-agent-portable-fin... | [NL-BP-111](PRODUCT_BACKLOG.md#nl-bp-111) |
| NL-BP-112 | App-data override NL_DATA_DIR for portable/installed builds | SPEC-14 | P3 (03_MASTER_CHECKLIST P3-03; SPEC-14) | verified | nl_coding_agent/persistence/database.py (NL_DATA_DIR) | [NL-BP-112](PRODUCT_BACKLOG.md#nl-bp-112) |
| NL-BP-113 | Launchers/installer set app-data location by default, with data migration policy | PORTABLE_BUILD.md | P3 (03_MASTER_CHECKLIST P3-03; docs/PORTABLE_BUILD next steps) | planned | launchers are .bat files without NL_DATA_DIR (documents/PORTABLE_BUILD.md states they do not set it yet) | [NL-BP-113](PRODUCT_BACKLOG.md#nl-bp-113) |
| NL-BP-114 | Lightweight native bootstrapper per OS/arch with manifest, checksum and rollback | SPEC-16 | P3 (03_MASTER_CHECKLIST P3-03, P3-04) | planned | no installer/bootstrap code (grep installer absent) | [NL-BP-114](PRODUCT_BACKLOG.md#nl-bp-114) |
| NL-BP-115 | No global Python/pip/uv/conda requirement; private runtime in a user-selected location | SPEC-16 | P3 (03_MASTER_CHECKLIST P3-03) | partial | pyproject.toml has no uv/pipx dependency | [NL-BP-115](PRODUCT_BACKLOG.md#nl-bp-115) |
| NL-BP-116 | Optional components/models installed on demand with no forced downloads | SPEC-16 | P3 (03_MASTER_CHECKLIST P3-05) | planned | no installer/component-selection code (grep) | [NL-BP-116](PRODUCT_BACKLOG.md#nl-bp-116) |
| NL-BP-117 | Repair, update and verify-installation flows with cache management | SPEC-20 | P3 (03_MASTER_CHECKLIST P3-04; SPEC-20) | planned | nl_agent.py doctor exists (read-only diagnostics) | [NL-BP-117](PRODUCT_BACKLOG.md#nl-bp-117) |
| NL-BP-118 | Clean-runtime build instead of duplicating the 1.44 GB development runtime | DISTRIBUTION_AUDIT.md | P2/P3 (SPEC-16; docs/PORTABLE_BUILD next steps) | planned | dist/portable-release manifest: python payload 1,506,844,135 B of 1,507,676,008 B total | [NL-BP-118](PRODUCT_BACKLOG.md#nl-bp-118) |
| NL-BP-119 | Windows/Linux/macOS native builds with native smoke tests | SPEC-17 | P3 (03_MASTER_CHECKLIST P3-02, P3-07) | planned | no CI/config for cross-platform builds | [NL-BP-119](PRODUCT_BACKLOG.md#nl-bp-119) |
| NL-BP-120 | OS adapter layer: no Windows-only assumptions in shared logic | SPEC-17 | P2 (SPEC-17) | partial | tools/shell.py handles Windows OEM decoding only | [NL-BP-120](PRODUCT_BACKLOG.md#nl-bp-120) |
| NL-BP-121 | License/NOTICE/SBOM audit and secret-free payload | SPEC-16 | P3 (03_MASTER_CHECKLIST P3-01) | partial | docs/CREWAI_RUNTIME.md license follow-up section | [NL-BP-121](PRODUCT_BACKLOG.md#nl-bp-121) |
| NL-BP-122 | Reproducible builds: pins, lockfile and immutable build manifest | SPEC-20 | P3 (03_MASTER_CHECKLIST P3-08; SPEC-20) | partial | pyproject.toml pins crewai==1.15.32 only | [NL-BP-122](PRODUCT_BACKLOG.md#nl-bp-122) |
| NL-BP-123 | Optional full offline package | SPEC-16 | P3 (03_MASTER_CHECKLIST P3-06) | planned | absent (no installer) | [NL-BP-123](PRODUCT_BACKLOG.md#nl-bp-123) |
| NL-BP-124 | Shared model downloads/cache reuse without isolation loss | SPEC-10 | P3 (03_MASTER_CHECKLIST P3-05; SPEC-10/16) | planned | no installer/model-management code | [NL-BP-124](PRODUCT_BACKLOG.md#nl-bp-124) |

### Area 6 - Release acceptance criteria (RELEASE, 12 requirements)

| ID | Requirement | Source | BP priority | Status | Evidence (primary) | Backlog |
|---|---|---|---|---|---|---|
| NL-BP-140 | Release acceptance matrix runner with recorded evidence and manual-pending labels | SPEC-19 | P1 (03_MASTER_CHECKLIST P3-08; SPEC-19) | partial | scripts/verify_relocation.py (read-only gate, 30 checks PASS in build/relocation/verify_relocation_final_lead.json) | [NL-BP-140](PRODUCT_BACKLOG.md#nl-bp-140) |
| NL-BP-141 | Accepted install on a non-default path | final-area-6 (release acceptance criterion 1) | new (final release acceptance criterion 1) | planned | no installer/path selection (absent) | [NL-BP-141](PRODUCT_BACKLOG.md#nl-bp-141) |
| NL-BP-142 | Accepted run on clean Windows without global Python | final-area-6 (release acceptance criterion 2) | new (final release acceptance criterion 2) | planned | docs/PORTABLE_BUILD.md historical payload check (doctor/GUI/project persistence) - not clean-machine and not current ... | [NL-BP-142](PRODUCT_BACKLOG.md#nl-bp-142) |
| NL-BP-143 | Relocation survival for repository and application data | WORKSPACE_MIGRATION.md | new (final release acceptance criterion 3; SPEC-14) | partial | build/relocation/verify_relocation_final_lead.json ok=true, 30 checks PASS, canonical root K:/AI/NL Coding Agent (202... | [NL-BP-143](PRODUCT_BACKLOG.md#nl-bp-143) |
| NL-BP-144 | Accepted clipboard screenshot + drag-and-drop attachments end-to-end | final-area-6 (release acceptance criterion 4) | new (final release acceptance criterion 4) | planned | absent (no chat/attachment/clipboard code) | [NL-BP-144](PRODUCT_BACKLOG.md#nl-bp-144) |
| NL-BP-145 | Accepted microphone + local transcription end-to-end | final-area-6 (release acceptance criterion 5) | new (final release acceptance criterion 5) | planned | absent (no ASR/audio code) | [NL-BP-145](PRODUCT_BACKLOG.md#nl-bp-145) |
| NL-BP-146 | Accepted CrewAI workflows and autonomous missions execute end-to-end | final-area-6 (release acceptance criterion 6) | new (final release acceptance criterion 6) | blocked | docs/CURRENT_STATE.md historical missions #16/#24/#36-#41 completed/APPROVE | [NL-BP-146](PRODUCT_BACKLOG.md#nl-bp-146) |
| NL-BP-147 | Accepted guarantee: invalid agent edits cannot corrupt verified sources | final-area-6 (release acceptance criterion 7) | new (final release acceptance criterion 7; SPEC-28) | blocked | tests/test_staging_broker_adversarial.py SH-01/SH-04 PASS at broker level (68-test batch) | [NL-BP-147](PRODUCT_BACKLOG.md#nl-bp-147) |
| NL-BP-148 | Accepted local model discovery + evidence-based model selection | final-area-6 (release acceptance criterion 8) | new (final release acceptance criterion 8) | partial | nl_coding_agent/models/providers.py + Ollama registry | [NL-BP-148](PRODUCT_BACKLOG.md#nl-bp-148) |
| NL-BP-149 | Accepted reproducible, organized builds from a clean environment | final-area-6 (release acceptance criterion 9) | new (final release acceptance criterion 9) | blocked | dist/portable-release/payload_manifest.json source K:/AI/Coding Agent (pre-relocation), no hashes | [NL-BP-149](PRODUCT_BACKLOG.md#nl-bp-149) |
| NL-BP-150 | Full pytest baseline green with documented measured count | SPEC-19 | P0 (03_MASTER_CHECKLIST P0-02; SPEC-19 Gate A) | partial | measured 2026-10-28 at HEAD 7e778da (16:12 Europe/Rome): pytest tests --collect-only = 134 collected | [NL-BP-150](PRODUCT_BACKLOG.md#nl-bp-150) |
| NL-BP-151 | Honest, evidence-based current-state documentation with consistent history | 02_STATO_REALE_DA_VERIFICARE.md | P0 (03_MASTER_CHECKLIST P0-11) | partial | docs/CURRENT_STATE.md test counts 65/69 vs measured 106 collected | [NL-BP-151](PRODUCT_BACKLOG.md#nl-bp-151) |

## Source inventory

| Source | Role | Used for | Present on disk |
|---|---|---|---|
| `docs/product-blueprint/00_MASTER_INDEX.md` | primary | source map, SPEC list | yes |
| `docs/product-blueprint/01_DECISIONI_E_PRIORITA.md` | primary | constraints, priority philosophy | yes |
| `docs/product-blueprint/02_STATO_REALE_DA_VERIFICARE.md` | primary | evidence discipline, historical state | yes |
| `docs/product-blueprint/03_MASTER_CHECKLIST.md` | primary | P0-P3 requirement IDs, dedup map | yes |
| `docs/product-blueprint/04_HANDOFF_MINIMO.md` | primary | handoff policy, active priority | yes |
| `docs/product-blueprint/05_TRACCIABILITA.md` | primary | traceability model, valid-evidence list | yes |
| `docs/product-blueprint/06_UNICO_HANDOFF_AUTONOMIA.md` | primary | autonomy contract, safeguards | yes |
| `docs/product-blueprint/07_HANDOFF_SELF_HEALING.md` | primary | self-healing scope | yes |
| `docs/product-blueprint/MANIFEST.json` | primary | file inventory (incomplete; see C2) | yes |
| `docs/product-blueprint/README_IMPORTANTE.md` | primary | precedence rules, versioning | yes |
| `docs/product-blueprint/NOTE_SULLE_SPECIFICHE_PRECEDENTI.md` | primary | legacy context policy | yes |
| `docs/product-blueprint/AUDIT_E_MIGRAZIONE_SENZA_RISCHI.md` | primary | read-only audit runbook | yes |
| `docs/product-blueprint/V2_CHANGELOG.md` | primary | source history | yes |
| `docs/product-blueprint/V3_CHANGELOG.md` | primary | source history | yes |
| `docs/product-blueprint/V4_CHANGELOG.md` | primary | source history | yes |
| `docs/product-blueprint/V5_CHANGELOG.md` | primary | source history | yes |
| `docs/product-blueprint/V6_CHANGELOG.md` | primary | self-healing addition (conflict C1) | yes |
| `docs/product-blueprint/V6_INDEX_CHECKLIST_PATCH.md` | primary | self-healing addition (conflict C1) | yes |
| `docs/product-blueprint/Prompt.txt` | primary | handoff intent | yes |
| `docs/product-blueprint/specifiche/01_ARCHITETTURA_E_RUNTIME.md` | spec | SPEC-01 requirements | yes |
| `docs/product-blueprint/specifiche/02_SELF_BUILD_E_RECOVERY.md` | spec | SPEC-02 requirements | yes |
| `docs/product-blueprint/specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md` | spec | SPEC-02A requirements | yes |
| `docs/product-blueprint/specifiche/03_GOALS_MILESTONES_TASKS.md` | spec | SPEC-03 requirements | yes |
| `docs/product-blueprint/specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md` | spec | SPEC-04 requirements | yes |
| `docs/product-blueprint/specifiche/05_MODEL_HUB_PROVIDERS.md` | spec | SPEC-05 requirements | yes |
| `docs/product-blueprint/specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md` | spec | SPEC-06 requirements | yes |
| `docs/product-blueprint/specifiche/07_QUALITY_GATES_E_BENCHMARK.md` | spec | SPEC-07 requirements | yes |
| `docs/product-blueprint/specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md` | spec | SPEC-08 requirements | yes |
| `docs/product-blueprint/specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md` | spec | SPEC-09 requirements | yes |
| `docs/product-blueprint/specifiche/10_SPEECH_ASR_MODELS.md` | spec | SPEC-10 requirements | yes |
| `docs/product-blueprint/specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md` | spec | SPEC-11 requirements | yes |
| `docs/product-blueprint/specifiche/12_PROJECT_DISCOVERY.md` | spec | SPEC-12 requirements | yes |
| `docs/product-blueprint/specifiche/13_RESOURCE_SCHEDULER.md` | spec | SPEC-13 requirements | yes |
| `docs/product-blueprint/specifiche/13A_GPU_CONTENTION_CLOUD_FALLBACK.md` | spec | SPEC-13A requirements | yes |
| `docs/product-blueprint/specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md` | spec | SPEC-14 requirements | yes |
| `docs/product-blueprint/specifiche/15_SICUREZZA_E_PRIVACY.md` | spec | SPEC-15 requirements | yes |
| `docs/product-blueprint/specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md` | spec | SPEC-16 requirements | yes |
| `docs/product-blueprint/specifiche/17_WINDOWS_LINUX_MACOS.md` | spec | SPEC-17 requirements | yes |
| `docs/product-blueprint/specifiche/18_SQLITE_SCHEMA_E_STATI.md` | spec | SPEC-18 requirements | yes |
| `docs/product-blueprint/specifiche/19_TEST_MATRIX_E_GATE.md` | spec | SPEC-19 requirements | yes |
| `docs/product-blueprint/specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md` | spec | SPEC-20 requirements | yes |
| `docs/product-blueprint/specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md` | spec | SPEC-21 requirements | yes |
| `docs/product-blueprint/specifiche/22_MODEL_AGENT_COMPETENCE_INDEX.md` | spec | SPEC-22 requirements | yes |
| `docs/product-blueprint/specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md` | spec | SPEC-23 requirements | yes |
| `docs/product-blueprint/specifiche/24_OPERATIONS_SUPERVISION_HEALTH_AND_DIAGNOSTICS.md` | spec | SPEC-24 requirements | yes |
| `docs/product-blueprint/specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md` | spec | SPEC-25 requirements | yes |
| `docs/product-blueprint/specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md` | spec | SPEC-26 requirements | yes |
| `docs/product-blueprint/specifiche/27_SELF_CHANGE_GATES_AND_DEPLOY.md` | spec | SPEC-27 requirements | yes |
| `docs/product-blueprint/specifiche/28_SELF_HEALING_AGENT_HARNESS.md` | spec | SPEC-28 requirements (SH-01..SH-07) | yes |
| `docs/product-blueprint/templates/GOAL_TEMPLATE.md` | template | goal record shape (advisory) | yes |
| `docs/product-blueprint/templates/TASK_MISSION_TEMPLATE.md` | template | mission record shape (advisory) | yes |
| `docs/product-blueprint/templates/RELEASE_AUDIT_TEMPLATE.md` | template | release audit shape (advisory) | yes |
| `docs/product-blueprint/tools/audit_external_builds.ps1` | tool | read-only external build audit (inventory) | yes |
| `docs/PRODUCT_BACKLOG.md` | deliverable | previous mission #42 content replaced by this consolidation; old entries mapped in dedup_map (C8) | yes |
| `docs/CURRENT_STATE.md` | state | historical verified capabilities, stale counts (C4/C5) | yes |
| `docs/COMPLETED_MISSIONS.md` | state | mission history evidence #16-#41 | yes |
| `docs/NEXT_SELF_BUILD_MISSION.md` | state | stale roadmap view (C4) | yes |
| `docs/PHASE2_HARNESS_INTEGRATION_PLAN.md` | design | Phase 2 design, measured prototypes, harness gap evidence | yes |
| `docs/WORKSPACE_MIGRATION.md` | state | relocation evidence, gate results, rollback procedure | yes |
| `docs/09_DISTRIBUTION.md` | history | distribution history and claims (C9) | yes |
| `docs/08_ACCEPTANCE_GATES.md` | history | legacy gate mapping (C10) | yes |
| `docs/07_SAFETY.md` | history | safety policy mapping | yes |
| `docs/02_SELF_BUILD_ROADMAP.md` | history | phase mapping, future phases 11-18 | yes |
| `docs/03_GUI_SPEC.md` | history | GUI/design mapping | yes |
| `docs/04_PROJECT_MANAGER.md` | history | project discovery mapping | yes |
| `docs/05_ORCHESTRATION.md` | history | orchestration/handoff/reviewer mapping | yes |
| `docs/06_RESOURCE_SCHEDULER.md` | history | resource scheduler mapping | yes |
| `docs/00_VISION.md` | history | product intent context | yes |
| `docs/01_ARCHITECTURE.md` | history | architecture context | yes |
| `docs/09_ANTIGRAVITY_EXECUTION_MISSION.md` | history | historical bootstrap context (not authoritative) | yes |
| `docs/README_AGGIUNTA.md` | history | SPEC-13A import note | yes |
| `docs/DISTRIBUTION_AUDIT.md` | evidence | measured sizes, duplicate/dependency audit | yes |
| `docs/PORTABLE_BUILD.md` | evidence | staging and NL_DATA_DIR evidence | yes |
| `docs/CREWAI_RUNTIME.md` | evidence | CrewAI pin/import/license evidence | yes |
| `AUDIT_REALE_E_LIMITI.md` | evidence | safety foundation audit and gaps | yes |
| `HANDOFF_DEEPSEEK_HARNESS.md` | evidence | stub incidents #43/#45, harness objective | yes |
| `AGENTS.md` | governance | workspace rules, containment, verification invariant | yes |
| `FINAL-PRODUCT-REQUIREMENTS (task brief areas 1-6)` | external-brief | 6 product areas and 9 release acceptance criteria | external |
| `Team task board (task-8..task-14)` | external-brief | area ownership mapping | external |

## Conflicts recorded during consolidation

- **C1 - v6 checklist/index patch not applied**: SPEC-28 self-healing requirements were enumerated directly from specifiche/28_SELF_HEALING_AGENT_HARNESS.md (SH-01..SH-07 gates) and mapped to NL-BP-055..059, 063, 065, 074, 146, 147. No P0-19..P0-22 IDs were minted as authority. Blueprint maintainers should apply the v6 patch or retire the changelog claim.
- **C2 - MANIFEST.json is incomplete (v5 only)**: docs/product-blueprint/INDEX.json now records the complete source inventory and supersedes MANIFEST.json as the backlog source index. MANIFEST.json was not modified (out of this task's write scope).
- **C3 - External portable directories claimed but absent**: Current measurement wins for status. The external-artifact requirement (NL-BP-093) is partial: the audit/authorization record for the removal is not in the repository, so the history cannot be reconstructed from repo evidence. No deletion action was taken by this task.
- **C4 - Self-build state and history disagree across docs/DB/state**: Durable DB + state JSON are treated as the historical record; docs are stale views (NL-BP-151). Mission #44 (continuous supervisor execution) and #45 (project discovery) are blocked/REJECT and are evidence that unattended autonomy is not achieved (NL-BP-063). This backlog is the new durable specification.
- **C5 - Test-count claims disagree**: Reported as measured, not claimed as full-green: NL-BP-150 is partial until a documented full-suite run. Stale counts in state docs must be updated after Phase 2 (NL-BP-151).
- **C6 - Safety harness applied but not wired**: Status is blocked for the integration requirements NL-BP-055/056/057/147 and partial for NL-BP-058/059 (modules + tests landed, orchestrator wiring pending) and NL-BP-060. Module-level tests are evidence of components only, never of end-to-end protection. This matches audit AUDIT_REALE_E_LIMITI.md and the Phase 2 plan (C6/C7 pending at snapshot).
- **C7 - Blueprint priorities vs final-product release criteria**: Priority semantics are explicitly redefined in this backlog: P0 = release acceptance criterion or hard safety/prerequisite; P1 = coherent product; P2 = advanced blueprint evolution; P3 = polish/extras. Both BP priority and backlog priority are recorded per requirement.
- **C8 - Prior PRODUCT_BACKLOG.md consolidation was incomplete**: It is replaced by this consolidated backlog (103 atomic requirements with evidence). Its entries are mapped in the dedup map; mission #42's completion does not prove backlog quality.
- **C9 - Docs say autonomous priority gate is met/verified**: Final requirements and current measured evidence override them. NL-BP-146/147 blocked; NL-BP-063 blocked; completion claims are not treated as evidence.
- **C10 - Old Antigravity Gate A-E claim**: Legacy gates are mapped to requirements but are not acceptance evidence. Release acceptance uses NL-BP-140..151 and SPEC-19.
- **C11 - GUI feature expectations vs placeholders**: Anything with no callable backend is status partial/planned; e.g. speech tab placeholder -> NL-BP-035 planned; read-only model panels -> NL-BP-036 partial.

## Related documents

- [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md) - canonical backlog with acceptance gates, dependencies and dedup decisions.
- [product-blueprint/INDEX.json](product-blueprint/INDEX.json) - machine-readable requirements, source inventory, dedup map and conflicts.
- [build/backlog/AUDIT.md](../build/backlog/AUDIT.md) - consolidation audit: sources read, decisions, discrepancies, verification commands.
- [product-blueprint/03_MASTER_CHECKLIST.md](product-blueprint/03_MASTER_CHECKLIST.md) - original Blueprint checklist (source, not the backlog).


# Universal Goal Mode & Document-Driven Goal Bootstrap - Capability Audit (read-only)

**Task:** shared task-68. **Date:** 2026-10-28 (Europe/Rome). **Repository:** `K:\AI\NL Coding Agent` at git HEAD `393e6ce` (clean working tree before this task).
**Type:** read-only capability audit + queue-only backlog input. **No feature was implemented, no application code was modified, and no model, mission or network run was started.**
**Directives under audit:** (1) Universal Goal Mode; (2) Document-Driven Goal Bootstrap & Planning (2026-10-28, queue only).

---

## 1. Executive summary

The application already has a **strong execution substrate** but **no first-class Goal product layer**:

- **What exists:** SQLite missions/tasks/task_attempts/handoffs/verification_runs/mission_evidence, a durable **mission_queue** with claim/lease/heartbeat/retry/failure-signature, supervisor runs/leases/commands/approvals, deterministic cron-like watchdog/flow tables, a human-in-the-loop approval store; a supervisor loop with backlog sync, next-requirement selection, preflight, reconcile, pause/stop; CrewAI Flows with durable flow state; GUI pages for Projects, Files, Tasks, Chat, IDE, Research, Agents, Model Hub, Settings plus an Autonomy panel; CLI `supervisor run/start/stop/...`, `index`, `recover`, `advance`; local attachment ingestion (files/clipboard, text/PDF/Office when optional libraries exist) with provenance; a project scanner that only lists doc filenames; and the web-research engine (stage 7, partially implemented).
- **What is missing:** any `goals` or `milestones` entity/table (measured live DB: none), a **Goals GUI**, goal CLI/API parity, goal-mode creation from NL + attachments/repos/references/acceptance criteria, adaptive goal decomposition and versioned replanning, a goal-continuation scheduler across goals, independent goal-completion verification against the original objective, reusable goal templates, document-corpus discovery/ingestion, documentation reconciliation, requirement/objective/constraint/acceptance extraction with provenance, editable/approved document-driven plans, and incremental document-change reconciliation.
- **Existing requirement NL-BP-050** ("Persistent Goals > Milestones > Tasks > Missions hierarchy with CRUD", status partial) already captures the hierarchy goal conceptually; it remains partial and **is not rewritten here**. The new requirements add the executable goal-mode depth and the document-driven bootstrap layer that 050 does not cover.
- **Project Genome (NL-BP-178) and the research engine (NL-BP-169..176/205..211)** are planned/partial; neither turns project documentation into a goal/plan. The Goal Template at `docs/product-blueprint/templates/GOAL_TEMPLATE.md` is advisory only (no code, CLI or GUI loader).

Twelve genuine gaps were registered as pending **NL-BP-212..223** in the new **program stage 8** after the dedupe mapping in section 5.

## 2. Method and evidence rules

- Static read-only inspection of `nl_coding_agent/**`, `docs/product-blueprint/INDEX.json` and a **read-only** SQLite open (`mode=ro`) for the live schema table list; commands in section 8.
- Line references are to the current files at the audit HEAD.
- "Implemented" does **not** mean exercised end-to-end; no mission, network request, model inference or install was performed by this audit.
- The user directives' premises were verified with two precision notes: (a) migration-backed schema and supervisor/queue/lease/Flow infrastructure do exist and are material foundations to reuse; (b) document ingestion exists only as **local attachment text extraction** plus scanner metadata - there is no corpus-to-requirements pipeline.

## 3. Existing capability evidence

### 3.1 SQLite schema - execution objects, no goals/milestones

Live database read-only table list: `app_settings, approvals, backlog_items, events, flow_pending_feedback, flow_runs, flow_states, handoffs, machine_leases, mission_attachments, mission_evidence, mission_queue, missions, model_inventory, project_facts, projects, supervisor_commands, supervisor_leases, supervisor_runs, task_attempts, tasks, verification_runs` - **no table named goal/milestone**.

| Evidence | Finding |
|---|---|
| `nl_coding_agent/persistence/database.py:72-92` | `missions(id, project_id, title, goal TEXT, status, ...)` and `tasks(id, mission_id, title, description, status, agent_role, depends_on, ...)`. `goal` is a free-text column on the execution mission, not a goal entity |
| `nl_coding_agent/persistence/database.py:94-139` | task attempts, handoffs and verification runs are mission-scoped execution records |
| `nl_coding_agent/persistence/database.py:141-168` | `supervisor_leases` and `supervisor_runs` (run mode/status/counters/stop/pause) |
| `nl_coding_agent/persistence/database.py:170-194` | `mission_queue` (requirement_id, mission_id, state, priority, idempotency_key, claim token, lease owner, attempts/retries, budget, **goal TEXT**, payload, failure class/signature) - a single-mission queue, not a multi-goal scheduler |
| `nl_coding_agent/persistence/database.py:196-214` | `backlog_items` mirrors indexed requirements (requirement_id, area, priority, program_stage, status, dependencies/acceptance/source refs, content hash, supervisor status, last_mission_id) - the indexed Blueprint, not user goals |
| `nl_coding_agent/persistence/database.py:216-350` | mission evidence, approvals, supervisor commands, machine leases, flow states/runs, attachments, capability grants/approvals |
| `nl_coding_agent/persistence/missions.py:43-62` | `create_mission(project_id, title, goal, ...)` writes a flat mission row with free-text goal |

### 3.2 Supervisor, queue, lease, Flows and persistence - reusable foundations

| Evidence | Finding |
|---|---|
| `nl_coding_agent/core/supervisor.py:96-176` | `SupervisorConfig` (mode/max_mission/limits); `Supervisor` lifecycle class at 277 |
| `nl_coding_agent/core/supervisor.py:381-410, 471` | project lease acquire/adopt/heartbeat/release |
| `nl_coding_agent/core/supervisor.py:490-568` | `sync_backlog()` (index -> backlog_items), `select_next()` (next indexed requirement), `enqueue_next()` (mission queue) |
| `nl_coding_agent/core/supervisor.py:592-806` | preflight, transitions, approvals, control commands (pause/stop), recover |
| `nl_coding_agent/core/supervisor.py:875-1028` | reconcile, status snapshots, approval list/decide |
| `nl_coding_agent/core/supervisor.py:1350-1360` | `execute_queue_item()` claims a queue item, resource-decides, then executes one mission |
| `nl_coding_agent/persistence/supervisor_store.py:237-455` | durable project `acquire_lease/renew_lease/release_lease/get_lease` + machine leases (single-owner claims) |
| `nl_coding_agent/persistence/supervisor_store.py:482-555` | supervisor run start/update/finish/get |
| `nl_coding_agent/persistence/supervisor_store.py:574-666` | Flow run start/update/get/list |
| `nl_coding_agent/persistence/supervisor_store.py:688-739` | durable supervisor commands (stop/pause/requests) |
| `nl_coding_agent/persistence/supervisor_store.py:752-895` | `enqueue_mission/find_queue_item/list_queue/claim_queue_item/update_queue_item` (state machine, claim token, lease owner, retry/failure signature) |
| `nl_coding_agent/persistence/supervisor_store.py:920-1046` | `sync_backlog/list_backlog/set_backlog_progress` (indexed-requirement mirror) |
| `nl_coding_agent/persistence/supervisor_store.py:1049-1094` | mission `record_evidence/list_evidence` (sha256/path/payload) |
| `nl_coding_agent/app/services.py:744-870` | GUI/API facade: supervisor start/stop/pause/resume/status/preflight/queue/approvals/flow runs |
| `nl_coding_agent/app/supervisor_service.py:21-183` | in-process supervisor service (start/status/pause/stop/wait/shutdown) |
| `nl_coding_agent/flows/` (`state.py, persistence.py, mission_flow.py, supervisor_flow.py, events.py, approval_provider.py`) | durable Flow state, mission flow and supervisor flow execution with approvals |

**Conclusion:** a durable supervisor/queue/lease/Flow substrate exists and should be reused by Goal Mode; it is **mission/requirement-oriented**, not goal-oriented.

### 3.3 GUI - execution/autonomy surfaces, no Goals/Milestones page

| Evidence | Finding |
|---|---|
| `nl_coding_agent/gui/widgets/sidebar.py:8-18` | navigation pages: Projects, Files, Tasks, Chat, IDE, Research, Agents, Model Hub, Settings - **no Goals** |
| `nl_coding_agent/gui/main_window.py:375-379, 447-461` | stack pages: 0 projects, 1 files, 2 tasks, 3 agents, 4 settings, 5 models, 6 autonomy, 7 chat, 8 IDE, 9 research - **no goals/milestones page** |
| `nl_coding_agent/gui/widgets/autonomy_panel.py:1-6, 46-56` | read-only supervisor status + mission queue view; buttons only enqueue/command; no goal hierarchy |
| `nl_coding_agent/gui/widgets/task_board.py` (mission/task list + details) | shows missions/tasks/handoffs/verification; not a goal/milestone tree |
| `nl_coding_agent/gui/widgets/projects_panel.py:132-140`; `chat_panel.py:107` | a mission is created from a single-line "goal" prompt; no goal object, acceptance criteria or attachment-driven goal |
| `nl_coding_agent/gui/widgets/research_panel.py:127` | Studio Research workspace exists (web research, stage 7 partial); it is not a goal/document-planning workspace |

### 3.4 CLI/API parity - no goal commands

| Evidence | Finding |
|---|---|
| `nl_coding_agent/cli.py:752-860` | subcommands: doctor, audit, work, status, roadmap, mission, selfbuild, `supervisor run/start/stop/pause/resume/status/approvals/index/recover/advance`, gui - **no goal command** |
| `cmd /c findstr /n "add_parser(\"goal" nl_coding_agent/cli.py` | no match |
| `nl_coding_agent/app/services.py:280` | API creates a mission from title+goal only; no goal CRUD; supervisor API is mission/queue oriented |

### 3.5 Document ingestion - local attachments + scanner metadata only

| Evidence | Finding |
|---|---|
| `nl_coding_agent/app/attachments.py:77-87` | extraction availability: text on; pdf via pdfplumber, xlsx via openpyxl, docx via python-docx (optional); audio/video false |
| `nl_coding_agent/app/attachments.py:233-267` | local byte extraction for text/PDF/Office; images metadata; audio/video deferred; unsupported rejected |
| `nl_coding_agent/app/attachments.py:415-450` | `prepare_path/prepare_paths` accept existing **local** files/folders only (no URL), batch limit, local store + SQLite provenance |
| `nl_coding_agent/projects/scanner.py:62-124` | project scan returns languages/frameworks/build files and a **filename list** `doc_files[:200]` + file sample; content is never read into requirements |
| `nl_coding_agent/research/reader.py:554-566` | web reader supports HTML/text/JSON; **PDF/Office/other binary media are explicitly UnsupportedDocument**; no local corpus ingestion |
| `nl_coding_agent/research/service.py:138-637` | search/fetch_read/GitHub/HF lookups + findings store (stage 7 partial): web evidence, not project-doc bootstrap |
| `nl_coding_agent/core/backlog.py:130-160, 510-591` | loads the machine-readable `INDEX.json` and selects indexed requirements; no document parsing or extraction |
| `nl_coding_agent/core/autonomous_roadmap_planner.py:15, 39-78` | parses the fixed `03_MASTER_CHECKLIST.md`/writes `NEXT_SELF_BUILD_MISSION.md`; no document corpus, reconciliation or goal decomposition |
| `nl_coding_agent/core/roadmap.py:12, 139` | reads the single fixed `docs/NEXT_SELF_BUILD_MISSION.md` |
| `docs/product-blueprint/templates/GOAL_TEMPLATE.md` | advisory record shape only (goal ID, value, scope, acceptance criteria, milestones...); `git grep GOAL_TEMPLATE` shows only docs/INDEX/MANIFEST references - **no code loader, CLI or GUI use** |

### 3.6 Goal-adjacent requirements already registered (not rewritten)

| ID | Status | Relevance |
|---|---|---|
| NL-BP-050 | partial | Persistent Goals > Milestones > Tasks > Missions hierarchy with CRUD; its own note says goals/milestones layers and CRUD/UI do not exist - **conceptual coverage retained**; new 212 adds executable goal-mode depth |
| NL-BP-051 | partial | durable mission/task persistence, resume and idempotent recovery |
| NL-BP-052 | partial | single-writer mission lock |
| NL-BP-061/062 | verified | supervisor daemon + next-mission selection from indexed backlog |
| NL-BP-063 | blocked | two consecutive missions without manual repair (SH-07 Tier B) |
| NL-BP-064 | partial | autonomy modes/budgets/approvals; 166-168 partial (Trusted/Full profiles, permission taxonomy) |
| NL-BP-066/067/068/069 | planned | team factory, optimization, model advisor, competence index |
| NL-BP-169..176, 205..211 | partial/planned | research engine (web search/reader/GitHub/HF/knowledge store/policy) and research safety/provider/acceptance requirements |
| NL-BP-177..181 | planned | multi-root workspace, Project Genome, Integration Forge |
| NL-BP-203 | planned | research real-network acceptance |
| NL-BP-054/058/060 | verified | evidence-based completion, independent candidate/oracle verification, fail-closed statuses - foundations for independent goal verification |
| NL-BP-012 | verified | durable structured handoffs |
| NL-BP-043, 046, 026-030 | partial | project context retrieval, dashboard, attachments/media backends |

## 4. Directive capabilities vs existing infrastructure

| Directive capability | Exists today? | Comment |
|---|---|---|
| NL goal creation (text + attachments/repos/reference material + acceptance criteria) | **Partial/no** | Mission creation takes title+goal text (services.py:280; projects_panel.py:132-140); attachments are local only (026-030); no persistent goal object |
| Persistent multi-goal hierarchy, priorities, dependencies, pause/resume/cancel | **No** (concept only in 050) | No goals/milestones tables (live DB); supervisor handles one active queue; pause/stop are run-level |
| Adaptive decomposition/versioned replanning | **Partial/no** | Only indexed-requirement selection (backlog.py:510-591) + fixed checklist parser; no versioned plan |
| Goal-continuation scheduler across goals | **Partial foundation** | mission_queue + supervisor + leases exist (supervisor_store.py:752-1046) but single mission sequence, requirement-based |
| Independent goal completion verification | **Foundation only** | 054/058/060 verify missions; no goal-level objective/acceptance verifier or false-completion detector |
| Goals GUI/CLI/API parity | **No** | No goals page/command; Task Board + Autonomy panel are mission/queue views |
| Reusable goal templates | **Advisory only** | GOAL_TEMPLATE.md not consumed by code |
| Document corpus discovery/ingestion | **Local attachments + scanner metadata only** | attachments.py local extraction; scanner.py lists doc filenames; research reader rejects PDF/Office and is web-oriented |
| Documentation reconciliation / extraction with provenance | **No** | No doc corpus model, contradiction/version reconciliation, requirement extraction |
| Editable plan preview/approve/persisted versions | **No** | No plan document model or plan version history |
| Incremental doc-change reconciliation | **No** | No incremental corpus refresh/diff |
| Docs-only project acceptance | **No** | No document-driven bootstrap path |

## 5. Dedupe mapping (directive sub-capability -> existing ID / new ID)

| Sub-capability | Existing coverage | New requirement | Decision |
|---|---|---|---|
| Persistent goal/milestone hierarchy with CRUD | NL-BP-050 (partial; concept/acceptance already registered) | NL-BP-212 | 050 retained; 212 supplies executable goal-mode depth (tables/API/lifecycle) that 050 lacks; no change to 050 |
| Mission/task persistence, lock, resume | NL-BP-051/052/061 | - | covered foundations, reused not duplicated |
| Goal creation from NL + attachments/repos/references/acceptance criteria | NL-BP-026..030 (attachments), 077 (project open), 050 (acceptance criteria concept) | NL-BP-212 | new goal entity + intake/acceptance mapping |
| Multi-goal priorities/dependencies/pause/resume/cancel | NL-BP-061/062/064 (supervisor/modes) | NL-BP-212 | new goal lifecycle; supervisor policy reused |
| Adaptive decomposition + versioned replanning | NL-BP-062 (indexed next mission), 050 (hierarchy), 178 (genome planned) | NL-BP-213 | new decomposition/replan engine |
| Goal-continuation scheduler across goals | NL-BP-061/062/064, mission_queue, 070 scheduler | NL-BP-214 | new cross-goal scheduler reusing queue/lease/policy |
| Independent goal completion verification | NL-BP-054/058/060 verified, 203 planned | NL-BP-215 | new goal-level verifier/false-completion detection |
| Goals GUI + CLI/API parity | NL-BP-046 partial dashboard, 025 mission GUI, 023/024 controls | NL-BP-216 | new GUI/CLI/API surface |
| Reusable goal templates across projects/Mega Suite | GOAL_TEMPLATE.md advisory; 195 Mega Suite installer | NL-BP-217 | new reusable-template system |
| Document corpus discovery/ingestion | NL-BP-077 discovery, 043 retrieval partial, 030/026..030 local extraction, 170/171 research web/GitHub (partial) | NL-BP-218 | new corpus ingestion with provenance; reuses local extraction and project scan |
| Documentation reconciliation | NL-BP-178 planned genome, 174 research store partial | NL-BP-219 | new reconciliation engine |
| Requirement/objective/constraint/dependency/acceptance extraction | NL-BP-178/213 concepts | NL-BP-220 | new extraction with source provenance |
| Editable plan preview/approve + optional auto-execution, persisted versions | NL-BP-213/064/166-168/024 | NL-BP-221 | new document-driven plan surface |
| Incremental doc-change/new-evidence reconciliation | NL-BP-219/174 | NL-BP-222 | new incremental reconciliation |
| Docs-only acceptance scenario | NL-BP-203/199-204 acceptance patterns | NL-BP-223 | new end-to-end acceptance |
| Research engine (search/reader/GitHub/HF/knowledge store) | NL-BP-169..176/205..211 partial/planned | - | covered; doc links can use research readers where appropriate, but project-doc corpus is 218 |
| Permissions/autonomy policy for auto-execution | NL-BP-064/166/167/168 | - | covered policy; 221 consumes it |
| Stage-2/3 gates and SH-07 Tier B | NL-BP-054..060/063 | - | unchanged; stage 8 depends on stages 3+7 |

## 6. New requirements registered (status planned, program stage 8)

| ID | Priority | Area | Dependencies | Summary |
|---|---|---|---|---|
| NL-BP-212 | P0 | autonomy | 050, 051, 061, 064, 166 | Universal Goal Mode core: NL goal creation with attachments/repos/references/acceptance criteria; persistent multi-goal hierarchy, priorities/dependencies, pause/resume/cancel; reuses supervisor/SQLite/Flow; survives restart/agent changes; CLI/API/GUI parity |
| NL-BP-213 | P0 | autonomy | 212, 062 | Adaptive goal decomposition and versioned replanning: milestones/tasks/missions with priorities/dependencies/risks/validation; replan on evidence/failure/change without silently discarding the objective |
| NL-BP-214 | P0 | autonomy | 212, 061, 062, 064 | Goal continuation scheduler: eligible-task selection/execution across multiple goals without prompts, resource/conflict safe, policy-driven, reusing queue/lease |
| NL-BP-215 | P0 | autonomy | 212, 054, 058, 060 | Independent goal completion verification: never from own checklist; verify against original objective/acceptance with evidence/tests/blockers; detect false completion |
| NL-BP-216 | P0 | studio | 212, 213, 214 | Goals GUI + CLI/API parity: milestones/tasks/active agents/logs/decisions/verified progress/blockers + lifecycle actions |
| NL-BP-217 | P1 | autonomy | 212, 195 | Reusable goal templates across unrelated projects and the Mega Suite |
| NL-BP-218 | P0 | autonomy | 077, 043, 030 | Document corpus discovery/ingestion: folder/nested docs, README/AGENTS/specs/architecture/checklists/roadmaps, Markdown/text/PDF/Office/archives, Git docs, doc URLs, provenance, untrusted input, no execution |
| NL-BP-219 | P0 | autonomy | 218, 178, 174 | Documentation reconciliation: authoritative docs, version conflicts, obsolete instructions, missing/contradictory requirements vs source/deps/tests/Git history |
| NL-BP-220 | P0 | autonomy | 218, 219, 050 | Requirement/objective/constraint/dependency/acceptance extraction with source provenance for plan generation |
| NL-BP-221 | P0 | autonomy | 213, 220, 064, 166 | Document-driven plan preview/edit/approve + optional auto-execution under autonomy policy, persisted plan versions |
| NL-BP-222 | P0 | autonomy | 218, 219, 214, 215 | Incremental document-change/new-evidence reconciliation preserving verified progress and original objective |
| NL-BP-223 | P0 | release | 212..222 | Acceptance scenario: unfamiliar doc-rich project import, traceable plan, deliberate false-completion detection, eligible-task execution, restart persistence, docs-only projects |

## 7. Blockers, risks and human/external decisions

- **Stage 8 is pending**: depends on stages 3 and 7. Stage 7 is itself pending (partially implemented) and stage 6 is in progress; no stage status was changed by this import.
- **Existing 050 stays partial and is not rewritten**; its acceptance remains the conceptual hierarchy record. Any future reconciliation of 050 with 212 requires an authorized evidence update, not an ID rewrite.
- **Document-driven auto-execution requires an autonomy policy** (NL-BP-064/166..168) and the existing approval gates; large/untrusted corpora must be treated as untrusted input (NL-BP-175 policy) and may require owner authorization for execution.
- **Independent goal verification cannot be claimed from model consensus**: it must reuse the verified 054/058/060 gates and record real evidence; SH-07 Tier B (NL-BP-063) stays blocked.
- **Corpus size/scope**: unbounded folder ingestion is not authorized; discovery must be consent-based (077) with limits, and no document content may be executed.
- **Docs-only project**: acceptance requires projects without runnable code; test/verification evidence must be honest (document review/consistency evidence, not fabricated tests).
- **Goal templates/Mega Suite**: 217 depends on the Mega Suite distribution path (195), which is planned/pending.
- **No implementation started** by this task; no deletion/publication/cloud authorization is granted.

## 8. Verification commands used (read-only; no network/model/mission runs)

- Read-only SQLite `SELECT name FROM sqlite_master WHERE type='table'` on `data/nl_coding_agent.sqlite3` (mode=ro): 23 tables, no goal/milestone table.
- `nl_coding_agent/persistence/database.py:72-92, 141-232`; `persistence/missions.py:43-62`; `persistence/supervisor_store.py:237-1046`.
- `nl_coding_agent/core/supervisor.py:96-176, 381-568, 592-1028, 1350-1360`; `app/supervisor_service.py:21-183`; `app/services.py:280, 676-870`.
- `nl_coding_agent/gui/widgets/sidebar.py:8-18`; `gui/main_window.py:375-379, 447-461`; `gui/widgets/autonomy_panel.py:1-6, 46-56`; `gui/widgets/projects_panel.py:132-140`; `gui/widgets/research_panel.py:127`.
- `nl_coding_agent/cli.py:752-860` (no goal subcommand).
- `nl_coding_agent/app/attachments.py:77-87, 233-267, 415-450`; `projects/scanner.py:62-124`; `research/reader.py:554-566`; `research/service.py:138-637`.
- `nl_coding_agent/core/backlog.py:130-160, 510-591`; `core/autonomous_roadmap_planner.py:15, 39-78`; `core/roadmap.py:12, 139`.
- `git grep -n "GOAL_TEMPLATE"`: only `docs/BLUEPRINT_INDEX.md`, `docs/product-blueprint/INDEX.json`, `docs/product-blueprint/MANIFEST.json` - no code reference.
- `docs/product-blueprint/INDEX.json` requirement statuses for 050/051/052/061/062/063/064/066-070/166-168/169-176/177-181/203/205-211 and 054/058/060.

## 9. Change record

New documentation file and the queue-only backlog update it justifies. The addendum bundle and all preserved addenda under `docs/product-blueprint/addenda/` remain unchanged. No application code, tests, configuration, models, missions or network state were changed, and no commit was created by this task.

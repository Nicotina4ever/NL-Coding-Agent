# Product Backlog - NL Coding Agent (canonical, deduplicated, indexed)

**Version 1.0 - 2026-10-28.** This is the single persistent product backlog and long-term specification for NL Coding Agent. It consolidates the Master Blueprint (docs/product-blueprint/**), the previous state/history documents and the final-product requirements into atomic, evidence-based requirements grouped by product area.

> **Supersedes:** the previous docs/PRODUCT_BACKLOG.md (22-line mission #42 attempt), 03_MASTER_CHECKLIST.md as a de-facto backlog, and every duplicate requirement list in the Blueprint. It does **not** supersede the Blueprint specifications (design authority), AGENTS.md (workspace rules) or SQLite/docs history (evidence).

**Machine-readable:** [docs/product-blueprint/INDEX.json](product-blueprint/INDEX.json) - **One-line index:** [docs/BLUEPRINT_INDEX.md](BLUEPRINT_INDEX.md) - **Audit:** [build/backlog/AUDIT.md](../build/backlog/AUDIT.md).

**Snapshot:** 2026-10-28 16:12 Europe/Rome - git HEAD 7e778da (clean at snapshot; only the backlog deliverables untracked/modified) - Python 3.12.10 (python/python.exe) - measured pytest --collect-only = **134 tests collected** (full suite not run by this consolidation; see [NL-BP-150](#nl-bp-150)). Phase 2 (task-6) was being implemented concurrently: C1a/C1b/C2/C3/C4/C5 landed during consolidation; C6 (orchestrator staging wiring) and C7 remain pending at this snapshot.

**Addendum import v3.7 (2026-10-28, queue-only):** 39 new planned requirements NL-BP-166..204 from the preserved user addendum docs/product-blueprint/addenda/ were added under a new pending program stage 7 after a read-only dedupe cross-check; no existing ID/acceptance/status or stage 1-6 status was changed and no implementation started. Totals: 156 requirements (33 verified / 64 partial / 56 planned / 3 blocked).

**Web-research directive v3.8 (2026-10-28, queue-only):** the Universal Web Research & Intelligence Engine directive was audited read-only (see docs/WEB_RESEARCH_CAPABILITY_AUDIT.md); existing research requirements NL-BP-169..176/203 were preserved and seven genuine gaps became planned NL-BP-205..211 in stage 7. No existing ID/acceptance/status or stage 1-6 status was changed and no implementation started. Totals: 163 requirements (33 verified / 64 partial / 63 planned / 3 blocked).

**Goal-mode directive v4.2 (2026-10-28, queue-only):** the Universal Goal Mode + Document-Driven Goal Bootstrap & Planning directives were audited read-only (docs/GOAL_MODE_CAPABILITY_AUDIT.md): no goals/milestones tables or Goals GUI, supervisor/queue/lease/Flow substrate reusable, document ingestion local-only, GOAL_TEMPLATE advisory. Twelve gaps became planned NL-BP-212..223 in new pending stage 8; existing NL-BP-050 stays partial/unchanged. No code/model/network/mission run. Totals: 175 requirements (33 verified / 77 partial / 62 planned / 3 blocked).

**Open-model directive v4.3 (2026-10-28, queue-only):** the Open Model & Provider Ecosystem directive was audited read-only (docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md): config-driven Ollama/OpenAI-compatible discovery with closed provider kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI and an unwired tested router; capability states exist but measured-only gating; presets are hand-edited YAML. Ten extension gaps became planned NL-BP-224..233 in new pending stage 9; existing NL-BP-008/009/010/036/068/069/183/208 unchanged. No code/model/network/mission run. Totals: 185 requirements (33 verified / 77 partial / 72 planned / 3 blocked).

**Release-publication directive v4.4 (2026-10-28, queue-only):** the Final Release Hygiene & GitHub Publication Gate directive was audited read-only (docs/RELEASE_PUBLICATION_GATE_AUDIT.md): read-only hygiene/distribution audits, root policy, packaging/beta/rehearsal/acceptance tooling and the verified secrets/history scanner NL-BP-162 exist, but there is no CI/hook enforcement, no integrated final readiness milestone and no publication-readiness verdict; real external acceptance stays MANUAL-PENDING. Three gaps became planned NL-BP-234..236 in new pending stage 10; existing requirements unchanged. No code/model/network/push/publish run. Totals: 188 requirements (33 verified / 77 partial / 75 planned / 3 blocked).

**Studio final-UX directive v5.2 (2026-10-29, queue-only):** the final Studio GUI UX directive was audited read-only (docs/STUDIO_FINAL_UX_AUDIT.md): verified NL branding/theme and partial navigation/settings/self-build/emergency/accessibility/state requirements exist, but there is no UI i18n, 82 inline styles/110 hardcoded colours, a prominent Projects Self-Build button, a raw QTextEdit Inspector, ambiguous project/activity state and offscreen-only GUI evidence. Five gaps became planned NL-BP-237..241 appended to the EXISTING stage 4 (no new stage); stage 4 status/note corrected honestly to in_progress ('engineering complete; final UX acceptance reopened'). Existing IDs/acceptance and other stages unchanged. No code/GUI/model/network run. Totals: 193 requirements (34 verified / 82 partial / 74 planned / 3 blocked).

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
| 1 | Repository relocation and path reconciliation | COMPLETE | 1 | NL-BP 143 | - |
| 2 | Transactional staging, safety and self-healing | COMPLETE | 15 | NL-BP 3-5, 54-60, 65, 72-74, 76 | 1 |
| 3 | Persistent autonomous supervisor and verified handoff | COMPLETE | 13 | NL-BP 12, 50-53, 61-64, 66-67, 75, 77 | 2 |
| 4 | Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities | IN PROGRESS | 45 | NL-BP 1-2, 6-11, 13, 20-46, 68-71, 237-241 | 3 |
| 5 | Repository cleanup and optimization | COMPLETE | 8 | NL-BP 90-97 | 4 |
| 6 | Lightweight portable/bootstrapper and final release testing | IN PROGRESS | 40 | NL-BP 110-124, 140-142, 144-165 | 5 |
| 7 | Universal autonomy, research intelligence and Mega Suite | PENDING | 46 | NL-BP 166-211 | 6 |
| 8 | Universal Goal Mode and document-driven planning | PENDING | 12 | NL-BP 212-223 | 3, 7 |
| 9 | Open model and provider ecosystem | PENDING | 10 | NL-BP 224-233 | 4, 7 |
| 10 | Final release hygiene and GitHub publication gate | PENDING | 3 | NL-BP 234-236 | 6, 7, 8, 9 |

Execution rule: a later stage starts only when the previous stage's gates pass, unless the
Lead records an explicit evidence-backed exception for independent low-risk work. Stages 1-3
and 5 are complete; stage 4 is in progress (engineering complete; final UX acceptance reopened
by the 2026-10-29 directive); stage 6 is in progress; stages 7-10 are pending. SH-07 Tier B
(real local models) remains BLOCKED in NL-BP-063 and blocks any final readiness verdict.
Publication/push remains forbidden without explicit owner authorization.

## Summary

| Status | P0 | P1 | P2 | P3 | Total |
|---|---|---|---|---|---|
| verified | 23 | 13 | 0 | 0 | 36 |
| partial | 45 | 28 | 11 | 1 | 85 |
| planned | 40 | 19 | 9 | 1 | 69 |
| blocked | 3 | 0 | 0 | 0 | 3 |
| **Total** | 111 | 60 | 20 | 2 | 193 |

| Area | Requirements | verified | partial | planned | blocked |
|---|---|---|---|---|---|
| Area 1 - CrewAI + CrewAI Flows first-class integration | 24 | 6 | 7 | 11 | 0 |
| Area 2 - Studio GUI + multimodal chat | 40 | 3 | 25 | 12 | 0 |
| Area 3 - Universal autonomous development | 60 | 17 | 21 | 21 | 1 |
| Area 4 - Repository hygiene | 9 | 3 | 5 | 1 | 0 |
| Area 5 - Lightweight installation + portable distribution | 27 | 2 | 12 | 13 | 0 |
| Area 6 - Release acceptance criteria | 33 | 3 | 12 | 16 | 2 |

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

**v5.4 (2026-10-29)** - Static UI localization completed and NL-BP-237 verified (Italian default/English catalogs 409 keys each, identical key/placeholder sets, live switching across principal and secondary panels, persisted preference, separation from agent/code/documentation language). Pre-push guard historical blocker cleared with a precise tests-only synthetic-fixture allowlist (exact digest/path/rule/scope/commits/reason, visible in reports, narrowness tests); measured scan-staged/head/all PASS with 0 blocking and 5 allowlisted under unchanged detection rules, NL-BP-235 verified. Full integration suite 1110 passed in 142.8 s. Counts 36 verified / 85 partial / 69 planned / 3 blocked. NL-BP-238/239/240/241 remain partial; final release-HEAD rerun, real self-build/live content, human visual/screen-reader acceptance, external acceptance and owner publication authorization remain pending.

**v5.3 (2026-10-29)** - Studio final-UX implementation: Italian-default/English i18n framework with persisted live switching across principal and secondary panels (319 catalog keys each), NL-token visual system and reusable components, responsive Inspector/Projects/header fixes based on real screenshots, self-build moved from Projects to Settings > Advanced with progress/emergency-stop preserved, structured Inspector diagnostics and explicit opened/selected + IDLE/RUNNING activity state, and real Windows Qt screenshot evidence at three sizes/DPI with functional interaction capture. Five new requirements 237-241 now partial; full suite 1102 passed in 139.7 s; counts 34 verified / 87 partial / 69 planned / 3 blocked. Human aesthetic/Italian QA sign-off, complete legacy-style migration, real self-build/live-mission content and screen-reader acceptance remain MANUAL-PENDING.

**v5.2 (2026-10-29)** - Queue-only final Studio GUI UX acceptance directive. Read-only audit (docs/STUDIO_FINAL_UX_AUDIT.md) confirmed: verified NL branding/theme shell (020) and partial navigation/settings/self-build/emergency/accessibility/state requirements (021/022/023/024/044/045/046); NO UI internationalization/language setting/persistence; 82 setStyleSheet calls and 110 hardcoded colour literals across the GUI; a prominent Projects-page 'Self-Build (This Agent)' button (projects_panel.py:34-37, 121-125) alongside existing Settings > Advanced controls; a raw read-only QTextEdit Inspector; ambiguous project/open/activity state; and offscreen-only GUI evidence with real-desktop/clipboard/DPI items MANUAL-PENDING. Five acceptance gaps appended to the EXISTING program stage 4 as planned NL-BP-237..241 (i18n, visual/IA polish, self-build placement/runtime UX, Inspector/state clarity, real-GUI evidence). Stage 4 status/note corrected honestly from completed to in_progress ('engineering complete; final UX acceptance reopened'); no new stage/framework; stages 1-3/5-10 untouched; existing requirement IDs/acceptance retained; addenda preserved; no code/GUI/model/network run started. Totals: 193 requirements; 34 verified / 82 partial / 74 planned / 3 blocked.

**v5.1 (2026-10-29)** - Goal Mode G8/G9: plan approval metadata and audit (current/explicit version, idempotent, replan creates unapproved version), read-only linked task/queue/active-work inspection with connected/idle/not-connected states, AppServices/CLI goal approve/tasks/workers, an eighth Goals GUI section (Tasks & Active Workers) and Plan Version approval controls, with GUI adapters aligned to the real facade. Goal suite 98 passed; targeted GUI 23 passed; full integration suite 1081 passed in 147.8 s. Counts unchanged at 34 verified / 82 partial / 69 planned / 3 blocked. NL-BP-216 remains partial for permission-policy gating/non-blocking refresh and real lifecycle acceptance; NL-BP-213 remains partial for objective/evidence-driven task/mission derivation.

**v5.0 (2026-10-28)** - Stage-7 R7/R8: prompt-injection resistance completed and verified (bounded passive scanner with redacted evidence, untrusted markers, research_injection audit, independent permission gate, no execution/following; 12 injection + 3 service tests, research suite 154) and saved findings can be attached to missions with permission-gated revocable links plus non-destructive stale/expired retention and GUI attach/detach/retention controls (60 targeted tests). Full integration suite 1053 passed in 136.5 s; counts 34 verified / 82 partial / 69 planned / 3 blocked. NL-BP-210 remains partial only for live-network preview/provider and live-approval acceptance (MANUAL-PENDING).

**v4.9 (2026-10-28)** - Goal Mode G6/G7 vertical slice: versioned replanning (goal_plan_versions snapshots/diffs, rationale/trigger/evidence validation, immutable objective, in-place milestones preserving mission links, plan-version/current APIs, replan audit and CLI/API replan/versions/links/activity/queue) and seven-section Goals GUI (missions/queue, activity/decisions, plan versions, evidence/verification, replan dialog, verify-before-complete evidence dialog) with 19 targeted GUI/service tests. Pre-push R2/R3: hook interpreter/quoting fix, real temp-remote push-blocking integration tests, fail-closed Git errors, bounded-history robustness, CI assertions and runtime-assembled synthetic fixtures; canonical scan-all remains blocked by historical synthetic-fixture commits, so no clean-pre-push verified claim is made. Full suite 1031 passed; counts unchanged at 33 verified / 83 partial / 69 planned / 3 blocked.

**v4.8 (2026-10-28)** - Stage-8 G4/G5: Goals GUI workspace (11th page: project-scoped goals/filters/create/lifecycle/milestones/next-work/progress/blockers, verification-gated completion delegation, no widget business logic; 8 offscreen tests, headless 11-page smoke) and verification-gated completion through AppServices/CLI (GoalVerifier before status mutation, persisted reports, refusals covering missing/untrusted/self/contradicted/stale evidence with no status change, dry-run/read-only verify/records/false-completion, CLI verify/complete; 12 tests; goal suite 62). Full suite 1007 passed. Autonomous scheduling/continuation, autonomy-policy resource/conflict handling, versioned replanning, templates, full task/agent/log views, verifier reuse of staged-candidate gates and end-to-end acceptance remain pending.

**v4.7 (2026-10-28)** - Stage-8 G2/G3: non-executing Goal CLI group and lazy AppServices goal facade (create/list/show/lifecycle/decompose/next/progress, JSON/text, stable errors, no model config/execution, 30 targeted tests) and independent GoalVerifier (test/command/artifact/reviewer/user/file evidence, required-type enforcement, append-only goal_verifications, explicit false-completion detection, no status mutation; 20 tests). Full suite 987 passed; counts 33 verified / 83 partial / 69 planned / 3 blocked. Goals GUI page, scheduler/continuation, adaptive replanning, document reconciliation/extraction/plan approval, verifier integration and end-to-end acceptance remain pending.

**v4.6 (2026-10-28)** - Stage-8 first implementation increments: G1 Universal Goal Mode foundation (durable goals/milestones tables linked to existing missions, GoalService lifecycle/dependencies/structured decomposition/next-work/progress/audit, 17 tests) and D1 document corpus discovery/ingestion (bounded read-only project/archive/Git/injected-URL document discovery with provenance, authority flags and immutable untrusted marking, 8 tests). Counts 33 verified / 81 partial / 71 planned / 3 blocked; full suite 954 passed. GUI/CLI/API goal surfaces, multi-goal execution/continuation, replanning, reconciliation/extraction/planning, independent verification and acceptance remain pending.

**v4.5 (2026-10-28)** - Stage-7 R6: real AppServices research facade wired into the Studio Research workspace (lazy, injection-only network; offline by default; configured fake services persist provenance/citations and expose permission-needed/denied; 18 tests). Stage-10 R1: mandatory blocking pre-push secrets/content guard (scan-staged/head/history/all, hook mode, install-hook with backup, redacted evidence, blocking CI secrets-scan job, 9 temp-repo tests; no canonical hook installed, no push attempted, bounded history). Full suite 929 passed; live provider/network acceptance and real external publication acceptance remain MANUAL-PENDING.

**v4.4 (2026-10-28)** - Queue-only Final Release Hygiene & GitHub Publication Gate directive and mandatory pre-push secrets/content scan. Read-only audit (docs/RELEASE_PUBLICATION_GATE_AUDIT.md) confirmed: read-only distribution/repository-hygiene audits (090/091/095 verified; others partial), root-reorg/retention policy, packaging/beta/rehearsal/acceptance tooling (110-124/140/149/195-197), VERIFIED secrets/history scanner NL-BP-162 with redacted evidence and exit-code gate but NO CI wiring or Git hooks (core.hooksPath unset), owner gates/no-remote/private repo (163), and MANUAL-PENDING real-hardware/CI/beta acceptance. No integrated readiness milestone, blocking pre-push gate or publication verdict existed. Added planned NL-BP-234 (P0 final repository/distribution readiness milestone/refactor), NL-BP-235 (P0 mandatory blocking pre-push gate) and NL-BP-236 (P1 publication verdict + external-acceptance/sign-off gate) in new pending stage 10 (depends_on_stages [6,7,8,9]). Existing requirement IDs/acceptance and stages 1-9 untouched; addenda preserved; no code/model/network/push/publish run started. Totals: 188 requirements; 33 verified / 77 partial / 75 planned / 3 blocked.

**v4.3 (2026-10-28)** - Queue-only Open Model & Provider Ecosystem directive. Read-only audit (docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md) confirmed: config-driven Ollama + generic OpenAI-compatible discovery, api_key_env Bearer headers, health/loaded/unload; dynamic Ollama tags/namespaces; a tested ModelRouter (override/project/role/fallback, capability/permission/resource gates, snapshots) not instantiated in product code; capability states measured/declared/unknown/unavailable with measured-only gating; read-only Model Hub GUI/Settings; presets exist only as hand-edited config/models.yaml; provider kind branch is closed; only temperature is passed. Requirements 008/009/010/036/068/069/183/208 retained unchanged; ten gaps added as planned NL-BP-224..233 in new pending stage 9 (depends_on_stages [4,7]). No existing ID/acceptance/status or stage 1-8 status rewritten; addenda preserved; no code/model/network/mission run started. Totals: 185 requirements; 33 verified / 77 partial / 72 planned / 3 blocked.

**v4.2 (2026-10-28)** - Queue-only Universal Goal Mode + Document-Driven Goal Bootstrap & Planning directives. Read-only audit (docs/GOAL_MODE_CAPABILITY_AUDIT.md) confirmed: SQLite has missions/tasks/task_attempts/handoffs/verification_runs/mission_queue/supervisor_runs/leases/approvals/Flow tables but no goals/milestones; supervisor/queue/lease/Flow infrastructure and CLI supervisor commands exist; GUI has Task Board/Autonomy/Research but no Goals page; document ingestion is local attachment extraction plus scanner filenames; GOAL_TEMPLATE.md is advisory only. Deduped against NL-BP-050/051/052/061/062/063/064/066-070/166-168/169-176/177-181/203/205-211; twelve gaps added as planned NL-BP-212..223 in new pending program stage 8 (depends on stages 3 and 7). NL-BP-050 remains partial and unchanged. No code/model/network/mission run started; addenda preserved. Totals: 175 requirements; 33 verified / 77 partial / 62 planned / 3 blocked.

**v4.1 (2026-10-28)** - Stage-7 R4/R5: ResearchService permission + auto-review boundary before any network-capable work, explicit permission-gated stdlib transport (no implicit network), provenance/citation persistence in the research store and typed read-only research tools; Studio Research workspace as the 10th page (provider/permission/offline status, previews, history, saved findings, URL/GitHub/HF/attachment intake); CI headless smoke updated for 10 pages. 34 new tests; full suite 910 passed. Live network/providers, real AppServices research facade, tool-execution/model wiring and real-network acceptance remain MANUAL-PENDING; no research-reliability or platform-support claim.

**v4.0 (2026-10-28)** - Stage-7 second implementation increments: independent auto-review policy engine + autonomy profiles foundation (166/167 partial) and research provider registry/router, local SQLite research store and read-only GitHub/Hugging Face investigators over injected transports (169/171/172/174/205/207 partial). 63 new tests this batch; full suite 877 passed. All of it is fixture/foundation-only: no live provider/network calls, GUI/tool-registry/execution wiring, embeddings/retrieval, live API authentication or real-network acceptance; these remain MANUAL-PENDING.

**v3.9 (2026-10-28)** - Stage-7 first implementation increments: NL-BP-168 capability taxonomy and durable scoped approvals (20 capabilities/12 scopes/6 decisions, fail-closed defaults, additive SQLite, audit, 23 tests; part of Trusted Auto Review/Full Autonomy track) and NL-BP-170/175/206 research foundation (stdlib retrieval policy with domain/SSRF/rate/size enforcement, injectable-transport fetcher with redirects/provenance/untrusted tagging, HTML reader; 69 tests). Both are partial/foundation-only: no GUI/tool wiring, search providers, browser, real transport, research store or real-network acceptance; full suite 814 passed. Real-network research and TRUSTED AUTO REVIEW/FULL AUTONOMY remain pending/MANUAL-PENDING.

**v3.8 (2026-10-28)** - Queue-only Universal Web Research & Intelligence Engine directive. Read-only capability audit (docs/WEB_RESEARCH_CAPABILITY_AUDIT.md) found no external web-research capability: stdlib urllib is used only for loopback Ollama/model-provider probes and a local tool health endpoint; MCP is local stdio-only with human-gated invocation and no bundled GitHub/HF/web servers; NETWORK/CLOUD permission scopes are fail-closed but unused by research tools; attachments are local files/clipboard only. Deduped every directive sub-capability against NL-BP-169..176/203 and added seven genuine gaps as planned requirements **NL-BP-205..211** (provider registry, retrieval safety, connector registration, HF acquisition, version-aware docs, Studio research workspace, acceptance matrix) under stage 7. No existing ID/acceptance/status or stage 1-6 status was rewritten; no code/model/network run started; addendum bundle preserved. Totals: 163 requirements; 33 verified / 64 partial / 63 planned / 3 blocked.

**v3.7 (2026-10-28)** - Queue-only import of the user-supplied Universal Autonomy/Research/Mega Suite addendum (preserved unchanged at docs/product-blueprint/addenda/, MANIFEST verified; docs/product-blueprint/addenda/README_IMPORT.md rules respected: merge, do not replace). Read-only cross-check against the 117 live requirements produced a 20-group dedupe mapping; 39 genuinely new capabilities became planned requirements **NL-BP-166..204** under a new pending program stage 7. Covered capabilities stayed on existing IDs (dynamic teams 066/067, competence index 068/069, staged gates 054-060/063, multi-platform beta 152-165, Studio 020-046, distribution 110-124). No existing ID, acceptance criterion or stage 1-6 status was rewritten; no code, mission or network run started. SH-07 Tier B remains BLOCKED; owner authorization is still required for publication, deletion, cloud use and external distribution. Totals: 156 requirements; 33 verified / 64 partial / 56 planned / 3 blocked. This update also synchronises the program/summary tables and requirement appendix in this file with INDEX.json (previously they still showed the 103-entry view).

**v3.6 (2026-10-28)** - Stage-4 G1 GUI safety controls: Settings > Advanced self-build controls (no autostart/no GUI start), read-only plan/history and an always-reachable emergency Pause/Stop using the cooperative supervisor path (NL-BP-023/024 partial, 064 evidence; 20 new offscreen tests). Stage-6j/6k: genuine WSL2 Ubuntu execution evidence (shell syntax, launcher execution, reproducibility/package/rehearsal/acceptance/fetch/beta plans), POSIX Self-Build launcher bad-substitution fix, and byte-identical cross-platform release manifests/beta package. Full suite 722 passed. The user-supplied universal-autonomy/research addendum is preserved as queue-only input; no features from it are implemented. External/manual acceptance items unchanged.

**v3.5 (2026-10-28)** - Stage-6h/6i: synthetic end-to-end release-pipeline rehearsal (synthetic runtime fixtures -> measured draft -> native candidate with runtime archives -> beta package -> offline provision/verify -> acceptance matrix; explicit NOT-A-RELEASE, canonical manifests unchanged, temp-only evidence) and a cross-platform reproducible source-release check (two builds, archive/manifest equality, forbidden-content scan) wired into a ubuntu/windows/macOS CI job. Full suite 693 passed; relocation 34/0; supervisor/SBOM green; local rehearsal PASS 8/8, reproducibility PASS 40/40, package smoke PASS. Real archives, actual CI runs, clean-machine/hardware acceptance, signing and distribution authorization remain MANUAL-PENDING.

**v3.4 (2026-10-28)** - Stage-6f/6g: POSIX launchers (NL Coding Agent.sh, doctor.sh, status.sh, Self-Build Mode.sh, macOS .command) shipped and mapped into the payload root with executable bits, source-vs-payload root resolution, provisioned-runtime use and fail-closed fallback; CI package-smoke job added (source candidate + beta package + acceptance matrix + native-runtime dry-run, reports-only artifacts) and locally validated. Full suite 682 passed. Real native runtime archives/CI runs/clean-machine/hardware acceptance, signing and distribution authorization remain MANUAL-PENDING.

**v3.3 (2026-10-28)** - Stage-6c/6d/6e tooling: deterministic private-beta package builder (source package with SHA256SUMS, versioned manifests, six-target install docs, byte-identical rebuild), release-acceptance matrix runner and beta acceptance record tool with MANUAL-PENDING enforcement and generated tracked matrix evidence (six targets MANUAL-PENDING, no CI hardware claim), and native runtime acquisition/measurement tooling for all six targets (plan/offline/download, measured manifest draft, no fabricated hashes). NL-BP-140 verified; 159/164/165 partial. Full suite 677 passed, gates green; real native archives, actual CI execution, clean-machine/hardware acceptance and distribution authorization remain MANUAL-PENDING/owner-gated.

**v3.2 (2026-10-28)** - Root reorganization implemented (not audit-only): 32 -> 21 top-level root items; one root launcher plus scripts/launchers/; repair scripts archived to docs/history/legacy/temp-scripts/; unused crewAI checkout moved to da_eliminare/crewAI; build/dist/logs/state consolidated under .workspace with configurable policy; python/ and data/ preserved. Full suite 628 passed, relocation 33/0/1, supervisor/SBOM/GUI/portable/release-builder/doctor/CLI green, secrets audit CLEAR-WITH-REVIEW blocking 0. NL-BP-095 verified, 094/097 partial; no deletion, stale candidates and da_eliminare require owner authorization.

**v3.1 (2026-10-28)** - Cross-platform private beta C1-C5 implemented: compatibility audit/matrix + platform abstraction (31 tests), six-target native runtime manifests/provisioner + measured-only release builder (57 tests), GitHub Actions CI matrix + headless GUI/bootstrapper checks (7 tests), beta feedback workflow + opt-in redacted diagnostic generator (31 tests), pre-upload secrets/history audit (12 tests), and root reorganization Phase A (one root launcher; CLI launchers under scripts/launchers/; repair scripts archived; da_eliminare staging). NL-BP-161/162 verified; 152-158/160/163-165 partial. All non-Windows runtime/CI/clean-machine/hardware acceptance remains MANUAL-PENDING; secrets audit must be re-run before any upload and owner authorization is required for external distribution.

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

<a id="nl-bp-183"></a>
### NL-BP-183 - Model Competence Lab: multi-backend inspection, capability verification and role benchmarks

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-008, NL-BP-009, NL-BP-069, NL-BP-070
- **Acceptance gates:**
  - Inspects models across Ollama, LM Studio, llama.cpp, MLX/macOS, OpenAI-compatible services and optional cloud, verifying actual tool/JSON/vision/audio capabilities.
  - Runs role-specific benchmarks (coding, test authoring, editing, review, repair, research) recording model ID, quantization, backend, prompts, options, time, memory and hardware.
  - Uses an independent judge/evaluator: the evaluated model is never the sole judge.
  - Results feed the existing Model/Agent Competence Index (NL-BP-069) and Model Advisor (NL-BP-068); no invented rankings.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #4
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #4
- **Note:** Extends existing competence index/advisor; genuinely new is the lab-level multi-backend inspection/benchmark harness with independent judging.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-187"></a>
### NL-BP-187 - Plugin/SDK extension ecosystem with documented interfaces

- **Area:** CORE - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-008, NL-BP-009, NL-BP-073
- **Acceptance gates:**
  - Documents interfaces for adding agent roles, parsers, model backends, tools, research connectors, UI panels and project adapters.
  - Third-party skills carry provenance and explicit sandbox limitations; retrieved README instructions are never executed by default.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Note:** Expansion of Tool Registry (NL-BP-073) into a documented plugin/SDK surface.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-208"></a>
### NL-BP-208 - Hugging Face acquisition workflow with compatibility evidence and explicit license/gated approval

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: universal web research & intelligence engine)
- **Dependencies:** NL-BP-172, NL-BP-183, NL-BP-124, NL-BP-008
- **Acceptance gates:**
  - Compatibility evidence (architecture, quantization, backend, RAM/VRAM/disk estimates with uncertainty) is written into the Model Registry/Competence Index/Scheduler before any acquisition decision.
  - License and gated-model access require explicit approval; no auto-accept and no automatic download of huge checkpoints.
  - Optional verified resumable downloads go only to approved locations with checksums; shared cache reuse avoids duplication.
  - Acquisition events are audited; failed/partial downloads are cleaned up safely.
- **Evidence:**
  - not started - queued only by task-60 from the user directive; read-only capability audit in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability-gap evidence: docs/WEB_RESEARCH_CAPABILITY_AUDIT.md sections 3 and 5 (only local urllib Ollama/model probes, gated local-stdio MCP, unused web-research permissions, local-only attachments)
- **Sources:** user directive 2026-10-28: Universal Web Research & Intelligence Engine (task-60; audited in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md); docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; NL-BP-172; NL-BP-183; NL-BP-124; NL-BP-008
- **Note:** Acquisition half of the HF research requirement (NL-BP-172); reuses model registry, competence index, scheduler and shared-cache requirements.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-224"></a>
### NL-BP-224 - Built-in provider presets with editable defaults

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-008, NL-BP-010, NL-BP-036
- **Acceptance gates:**
  - Built-in presets exist for Ollama, llama.cpp, LM Studio and generic OpenAI-compatible providers, plus an extension point for further presets; they are conveniences, never restrictions.
  - Every preset field (base URL, model, auth/secret reference, protocol, defaults) is user-editable and removable; providers outside all presets remain supported.
  - No hardcoded approved provider/family/architecture/quantization list is introduced by presets.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-008; NL-BP-010; NL-BP-036
- **Note:** Presets today exist only as hand-edited config/models.yaml entries (config/models.yaml:6-25); NL-BP-008/010/036 stay unchanged.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-225"></a>
### NL-BP-225 - Custom provider profiles: arbitrary endpoint, auth, headers and protocol

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-008, NL-BP-224
- **Acceptance gates:**
  - A custom provider profile can define an arbitrary base URL, model id, authentication (including secret references), custom headers and protocol semantics.
  - Profiles are editable, importable, exportable and reusable across projects; secrets are referenced, never stored in plain profile files, and are redacted in UI/export/logs.
  - Saved profiles are validated and versioned; a broken profile fails with actionable errors without blocking other providers.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-008; NL-BP-224
- **Note:** New profile model/store; extends the fixed YAML schema without rewriting NL-BP-008.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-226"></a>
### NL-BP-226 - Automatic discovery plus always-available manual entry

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-008, NL-BP-224, NL-BP-225
- **Acceptance gates:**
  - Automatic discovery runs where supported (Ollama /api/tags + /api/ps incl. community namespaces/tags; OpenAI-compatible /models; llama.cpp/LM Studio through their OpenAI-compatible endpoints).
  - Manual provider/model entry is always available, even when discovery is unsupported, empty or offline, and feeds the same profile/routing pipeline.
  - Discovery failures are actionable and never remove manually entered entries.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-008; NL-BP-224; NL-BP-225
- **Note:** Complements verified NL-BP-008 discovery; manual fallback is genuinely new.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-227"></a>
### NL-BP-227 - Extensible provider protocol adapters (no closed provider list)

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-008, NL-BP-225
- **Acceptance gates:**
  - Provider protocols are implemented as registered adapters (Ollama, OpenAI-compatible and additional/non-OpenAI protocols) declared by the adapter itself.
  - Adding a protocol does not require editing a closed kind list or core routing branch; adapters declare their discovery/auth/model-list behaviour and capabilities.
  - Adapter identity/version/health and provenance are exposed; a malformed adapter cannot corrupt other providers.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-008; NL-BP-225
- **Note:** Replaces the closed kind branch in providers.py:268-293; no provider list becomes authoritative.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-228"></a>
### NL-BP-228 - Automatic parameter suggestions plus unrestricted expert configuration

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-010, NL-BP-225, NL-BP-068
- **Acceptance gates:**
  - The system suggests sane parameters per model/backend (context window, temperature, reasoning/thinking mode, tool-calling, structured output) with rationale and uncertainty.
  - Experts can override or add backend-specific extra parameters without artificial restrictions; unsupported parameters are warned about, not silently dropped.
  - Suggested vs user-specified values remain distinguishable and are persisted with the profile.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-010; NL-BP-225; NL-BP-068
- **Note:** Today the router passes only temperature (model_router.py:222-234); suggestions/additional parameters are new.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-229"></a>
### NL-BP-229 - Per-model and per-role profiles with project bindings and override preservation

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-010, NL-BP-011, NL-BP-068, NL-BP-225
- **Acceptance gates:**
  - Each model can carry a profile (context, reasoning, sampling, tool-calling, prompt templates, extra params) and each role can bind a model+profile; bindings can be project-specific.
  - Switching model or profile preserves explicit user overrides and records the effective configuration snapshot.
  - Profiles are versioned, editable/importable/exportable and never silently reset.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-010; NL-BP-011; NL-BP-068; NL-BP-225
- **Note:** Per-role model/temperature exists in YAML (config/models.yaml:27-43); persistent profiles/project bindings are new.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-230"></a>
### NL-BP-230 - Explicit capability states declared/detected/tested/unknown with warnings, not arbitrary rejection

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-009, NL-BP-069, NL-BP-183, NL-BP-070
- **Acceptance gates:**
  - The UI/API distinguishes declared, detected, tested and unknown capability states (mapped onto the existing measured/declared/unknown/unavailable evidence model) and shows their source.
  - Unknown/declared capabilities produce visible warnings for ordinary experimental use instead of hard refusal; hard gates remain only where a task/policy explicitly requires a measured capability.
  - Optional competence benchmarks and hardware profiling can enrich the states and never become an arbitrary allow-list for experimental use.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-009; NL-BP-069; NL-BP-183; NL-BP-070
- **Note:** Existing registry has measured/declared/unknown/unavailable (capabilities.py:17-18) and measured-only gating; presentation/policy layer is new. NL-BP-009/069/183 retained.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-231"></a>
### NL-BP-231 - Flexible local/external/embedding/multimodal routing with explanations, override and policy enforcement

- **Area:** CORE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-008, NL-BP-009, NL-BP-010, NL-BP-070, NL-BP-168, NL-BP-225, NL-BP-230
- **Acceptance gates:**
  - Routing covers local, external, embedding and multimodal backends with a deterministic resolution order and capability-aware selection.
  - Each decision is explainable (why this model/backend, refused candidates, missing capabilities) and the user can override without losing the recorded reason.
  - Existing permission/cloud-spending policy is enforced on every route; no hidden cloud or cost path is introduced.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-008; NL-BP-009; NL-BP-010; NL-BP-070; NL-BP-168; NL-BP-225; NL-BP-230
- **Note:** Router module exists and is tested but not instantiated in product code; live wiring, explanations, override and embedding/multimodal routes are new. NL-BP-010/070/168 retained.
- **Program stage:** 9 - Open model and provider ecosystem

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

<a id="nl-bp-190"></a>
### NL-BP-190 - Visual quality lab: screenshot baselines, accessibility, DPI and multi-monitor checks

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-020, NL-BP-046, NL-BP-044
- **Acceptance gates:**
  - Performs screenshot-baseline and human-reviewed UI comparison plus DPI/font-scaling, accessibility, keyboard-only, resize, multi-monitor and theme checks.
  - Measures GPU/CPU performance and debugs visual regressions without treating screenshots as proof of code correctness.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Note:** New quality capability; existing accessibility (NL-BP-044) covers rules/requirements but not a visual regression lab.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-191"></a>
### NL-BP-191 - GUI interaction automation / local computer use

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-168, NL-BP-190
- **Acceptance gates:**
  - Optional local accessibility-tree automation, screenshots, clicking/typing in controlled workspaces.
  - Uses live user approval for cross-project/high-impact UI actions; interactive GUI tests are separated from headless CI tests.
  - Actions are bounded, auditable and cancellable.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Note:** New capability; distinct from headless offscreen GUI tests. Requires the permission engine (NL-BP-168).
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-192"></a>
### NL-BP-192 - Multi-window / multi-session workspace

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-021, NL-BP-043
- **Acceptance gates:**
  - Supports concurrent projects without conflicting edits, with tabs/sessions/handoff, project-specific knowledge and per-workspace model selection.
  - Restart restores sessions and never merges unrelated project state.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Note:** New UX capability; current GUI is single-window/single-project.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-193"></a>
### NL-BP-193 - Advanced IDE parity: profiling, merge conflicts, code actions and quick-open

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-037, NL-BP-038, NL-BP-039, NL-BP-040, NL-BP-041
- **Acceptance gates:**
  - Adds profiling, merge-conflict resolution, code actions and quick-open on top of the existing editor/LSP/terminal/Git/test surfaces.
  - Every action is backed by a real implementation with a test; no mocked panels are described as features.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Note:** Fills explicit IDE gaps left by NL-BP-037..042.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-194"></a>
### NL-BP-194 - OCR-on-demand extraction for images, screenshots and documents

- **Area:** STUDIO - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-028, NL-BP-030
- **Acceptance gates:**
  - Invokes OCR only when needed for images/screenshots/scans, with language selection and page/region citation plus confidence.
  - Runs locally/offline by default and never silently uploads attachments to cloud.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #5
- **Note:** New extraction capability; existing media backends (NL-BP-030) do not include OCR.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-210"></a>
### NL-BP-210 - Studio Research workspace: search history, source previews, permission status and saved findings

- **Area:** STUDIO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: universal web research & intelligence engine)
- **Dependencies:** NL-BP-169, NL-BP-170, NL-BP-171, NL-BP-172, NL-BP-173, NL-BP-174, NL-BP-175, NL-BP-176
- **Acceptance gates:**
  - A research workspace shows search/query history, provider/permission status, citations and saved findings per project.
  - It previews web pages, GitHub repositories and Hugging Face models without executing retrieved content, and accepts pasted URLs/repo/model links plus existing local attachments as intake.
  - Findings can be attached to missions; retention/deletion policy preserves provenance and honours permissions.
- **Evidence:**
  - not started - queued only by task-60 from the user directive; read-only capability audit in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability-gap evidence: docs/WEB_RESEARCH_CAPABILITY_AUDIT.md sections 3 and 5 (only local urllib Ollama/model probes, gated local-stdio MCP, unused web-research permissions, local-only attachments)
- **Sources:** user directive 2026-10-28: Universal Web Research & Intelligence Engine (task-60; audited in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md); docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; NL-BP-169; NL-BP-170; NL-BP-171; NL-BP-172; NL-BP-173; NL-BP-174; NL-BP-175; NL-BP-176
- **Note:** New GUI surface; local attachments (NL-BP-026..030) become one intake path rather than the research capability itself.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-216"></a>
### NL-BP-216 - Goals GUI with CLI/API parity: milestones, progress, evidence, blockers and lifecycle actions

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-212, NL-BP-213, NL-BP-214
- **Acceptance gates:**
  - A Goals/Milestones page shows hierarchy, milestones, task queues, active agents, logs, decisions, verified progress, outstanding requirements and blockers.
  - Lifecycle actions (pause/resume/cancel/replan/approve) are available and mirrored in CLI and API with equivalent behavior and permission checks.
  - The GUI is a non-blocking view over stable services; no business logic lives in widgets.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-212; NL-BP-213; NL-BP-214
- **Note:** New GUI/CLI/API surface; extends the Task Board/Autonomy panel rather than replacing them.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-232"></a>
### NL-BP-232 - Model Hub GUI/CLI/API provider and profile management

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-036, NL-BP-224, NL-BP-225, NL-BP-229, NL-BP-231
- **Acceptance gates:**
  - Model Hub supports provider/profile switch, edit, import, export and reuse across projects from GUI, CLI and API with equivalent behavior.
  - Preset and custom-provider management is available in the UI; credential values are redacted and secret references are the only stored form.
  - No hardcoded approved provider/family/architecture/quantization list gates the UI; the existing read-only model discovery table remains.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-036; NL-BP-224; NL-BP-225; NL-BP-229; NL-BP-231
- **Note:** Extends the partial read-only Model Hub UI (NL-BP-036) without rewriting it.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-237"></a>
### NL-BP-237 - Studio UI internationalization and localization infrastructure

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-29: final Studio GUI UX acceptance)
- **Dependencies:** NL-BP-020, NL-BP-022, NL-BP-044
- **Acceptance gates:**
  - UI language defaults to Italian on the user's initial installation, with English plus extensible language catalogs and manual selection and optional OS-language detection.
  - The choice persists across restart and applies consistently to menus, dialogs, tooltips, errors and notifications.
  - UI language is independent of agent-response language and of generated code/documentation language; missing translations fall back visibly without breaking the UI.
  - Catalog loading is testable and no user-visible string remains hardcoded outside the catalog.
- **Evidence:**
  - not started - queued only by task-87 from the user directive; read-only GUI/UX capability audit in docs/STUDIO_FINAL_UX_AUDIT.md; no code, GUI, model or network run started
  - capability evidence: audit sections 3-4 (no UI i18n; 82 setStyleSheet/110 hardcoded colours; prominent Projects Self-Build button; raw QTextEdit Inspector; offscreen-only GUI tests)
- **Sources:** user directive 2026-10-29: final Studio GUI UX acceptance (localization, design polish, self-build placement, Inspector/state clarity, real-GUI evidence) (task-87; audited in docs/STUDIO_FINAL_UX_AUDIT.md); docs/STUDIO_FINAL_UX_AUDIT.md; NL-BP-020; NL-BP-022; NL-BP-044
- **Note:** Genuinely new; no UI translation infrastructure or language setting exists today.
- **Program stage:** 4 - Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities

<a id="nl-bp-238"></a>
### NL-BP-238 - Studio visual design and information architecture polish

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-29: final Studio GUI UX acceptance)
- **Dependencies:** NL-BP-020, NL-BP-021, NL-BP-044, NL-BP-045
- **Acceptance gates:**
  - A coherent typography, spacing, density, hierarchy and navigation system is applied across pages/panels with reusable components instead of per-widget inline styling.
  - Layouts remain usable and readable at supported window sizes/DPI settings, with status reporting that is legible (not raw debug text).
  - The real NL logo/palette/tokens define the identity; no unrelated palette and no distracting glow on text/code/logs.
  - Any retained inline style is justified; visual QA evidence is provided per the acceptance scenario in NL-BP-241.
- **Evidence:**
  - not started - queued only by task-87 from the user directive; read-only GUI/UX capability audit in docs/STUDIO_FINAL_UX_AUDIT.md; no code, GUI, model or network run started
  - capability evidence: audit sections 3-4 (no UI i18n; 82 setStyleSheet/110 hardcoded colours; prominent Projects Self-Build button; raw QTextEdit Inspector; offscreen-only GUI tests)
- **Sources:** user directive 2026-10-29: final Studio GUI UX acceptance (localization, design polish, self-build placement, Inspector/state clarity, real-GUI evidence) (task-87; audited in docs/STUDIO_FINAL_UX_AUDIT.md); docs/STUDIO_FINAL_UX_AUDIT.md; NL-BP-020; NL-BP-021; NL-BP-044; NL-BP-045
- **Note:** Extends verified shell/tokens (020) and partial navigation/accessibility (021/044/045); the 82 inline styles/110 hardcoded colours are the measured debt.
- **Program stage:** 4 - Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities

<a id="nl-bp-239"></a>
### NL-BP-239 - Self-build placement and runtime UX acceptance

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-29: final Studio GUI UX acceptance)
- **Dependencies:** NL-BP-023, NL-BP-024, NL-BP-046, NL-BP-216
- **Acceptance gates:**
  - The prominent Projects-page Self-Build action is removed; activation and configuration live under Settings > Advanced > Autonomous Development (reusing NL-BP-023/024 controls, not duplicating them).
  - Self-build progress is visible in Goals/Tasks with clear linked mission/task state, and the emergency pause/stop remains accessible during execution.
  - The self-build repository can still be opened as a normal project through a documented non-prominent path; no hidden auto-start occurs.
- **Evidence:**
  - not started - queued only by task-87 from the user directive; read-only GUI/UX capability audit in docs/STUDIO_FINAL_UX_AUDIT.md; no code, GUI, model or network run started
  - capability evidence: audit sections 3-4 (no UI i18n; 82 setStyleSheet/110 hardcoded colours; prominent Projects Self-Build button; raw QTextEdit Inspector; offscreen-only GUI tests)
- **Sources:** user directive 2026-10-29: final Studio GUI UX acceptance (localization, design polish, self-build placement, Inspector/state clarity, real-GUI evidence) (task-87; audited in docs/STUDIO_FINAL_UX_AUDIT.md); docs/STUDIO_FINAL_UX_AUDIT.md; NL-BP-023; NL-BP-024; NL-BP-046; NL-BP-216
- **Note:** Reuses partial NL-BP-023/024 and Goals/Tasks surfaces; acceptance is new.
- **Program stage:** 4 - Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities

<a id="nl-bp-240"></a>
### NL-BP-240 - Inspector structured summaries, expandable diagnostics and unambiguous project/activity state

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-29: final Studio GUI UX acceptance)
- **Dependencies:** NL-BP-021, NL-BP-022, NL-BP-045, NL-BP-046
- **Acceptance gates:**
  - Inspector presents structured summaries (project/mission/agent/verification) with expandable raw diagnostics instead of a single raw technical wall.
  - Project selection, opened-project state and current application activity (idle/indexing/auditing/supervisor running/mission running) are unambiguous across header, status and Projects page.
  - Errors and evidence remain reachable in expanded diagnostics; no information is hidden by the redesign.
- **Evidence:**
  - not started - queued only by task-87 from the user directive; read-only GUI/UX capability audit in docs/STUDIO_FINAL_UX_AUDIT.md; no code, GUI, model or network run started
  - capability evidence: audit sections 3-4 (no UI i18n; 82 setStyleSheet/110 hardcoded colours; prominent Projects Self-Build button; raw QTextEdit Inspector; offscreen-only GUI tests)
- **Sources:** user directive 2026-10-29: final Studio GUI UX acceptance (localization, design polish, self-build placement, Inspector/state clarity, real-GUI evidence) (task-87; audited in docs/STUDIO_FINAL_UX_AUDIT.md); docs/STUDIO_FINAL_UX_AUDIT.md; NL-BP-021; NL-BP-022; NL-BP-045; NL-BP-046
- **Note:** Extends partial NL-BP-021/022/045/046; structured Inspector and activity model are new.
- **Program stage:** 4 - Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities

<a id="nl-bp-241"></a>
### NL-BP-241 - Real-GUI visual and interaction acceptance evidence

- **Area:** STUDIO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-29: final Studio GUI UX acceptance)
- **Dependencies:** NL-BP-020, NL-BP-021, NL-BP-044, NL-BP-190
- **Acceptance gates:**
  - Real screenshots are captured for the main pages/dialogs at multiple window sizes and DPI settings, with evidence stored in the repository.
  - Functional interaction tests exercise real-window behaviour (open/select project, page navigation, self-build activation/stop, inspector expansion, language switch) beyond offscreen widget construction.
  - Real-GUI evidence is labelled real/manual and is never inferred from offscreen tests; extends NL-BP-190/044 visual/accessibility acceptance.
- **Evidence:**
  - not started - queued only by task-87 from the user directive; read-only GUI/UX capability audit in docs/STUDIO_FINAL_UX_AUDIT.md; no code, GUI, model or network run started
  - capability evidence: audit sections 3-4 (no UI i18n; 82 setStyleSheet/110 hardcoded colours; prominent Projects Self-Build button; raw QTextEdit Inspector; offscreen-only GUI tests)
- **Sources:** user directive 2026-10-29: final Studio GUI UX acceptance (localization, design polish, self-build placement, Inspector/state clarity, real-GUI evidence) (task-87; audited in docs/STUDIO_FINAL_UX_AUDIT.md); docs/STUDIO_FINAL_UX_AUDIT.md; NL-BP-020; NL-BP-021; NL-BP-044; NL-BP-190
- **Note:** Extends planned NL-BP-190 and partial NL-BP-044; offscreen-only tests are the current evidence gap.
- **Program stage:** 4 - Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities

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

<a id="nl-bp-166"></a>
### NL-BP-166 - Trusted Auto Review autonomy profile for routine scoped work

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-064, NL-BP-072, NL-BP-073
- **Acceptance gates:**
  - Trusted Auto Review auto-approves routine authorized read/write/patch, staged edits, shell tests, local private package installs, debugging, approved network research and next-mission progress under a durable project policy, with no per-action prompt spam.
  - Independent code review and every existing staged-candidate/regression gate remain mandatory even when tool actions are auto-approved.
  - Separate controls exist for tool auto-authorization, automated review, background mission continuation, external network, cloud LLM use, user-file access and release/deployment; enabling one never silently enables another.
  - The effective policy is inspectable, revocable, auditable and persisted across restart.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.1
- **Note:** Extends the existing Off/Assisted/Automatic modes (NL-BP-064) with the user-requested Trusted profile; does not weaken NL-BP-054/055-060/063 gates.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-167"></a>
### NL-BP-167 - Full Autonomy / Unrestricted profile with truthful OS-rights disclosure

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-166, NL-BP-168, NL-BP-072
- **Acceptance gates:**
  - Explicit user-opt-in profile grants broad execution and optional external registered path permissions with per-scope configuration.
  - The UI discloses the effective operating-system rights and warns that application-level filters cannot reliably sandbox arbitrary shell processes; it recommends isolated/disposable workspaces and never claims total reversibility.
  - Deletion, publication, secrets, remote writes and other high-impact permissions remain separately controlled or are explicitly owner-overridden with risk, scope and audit trail.
  - Emergency stop remains reachable and irreversible actions outside the approved policy stay refused.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.1
- **Note:** No forced arbitrary max-mission cap is imposed by the addendum; existing bounded repair/gates and human stop controls stay authoritative.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-168"></a>
### NL-BP-168 - Expanded permission capability taxonomy with durable scoped approvals

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-072, NL-BP-073
- **Acceptance gates:**
  - Capabilities cover read, write, execute, install-private, install-system, web-search, web-fetch, browser-interact, download, open-external-project, model-inference-local, model-inference-cloud, secret-use, git-commit, git-push, publish-release, delete, network-write, mcp-call and microphone.
  - Scopes cover tool, process, path, project, external registered resource, host/domain, repository, task, mission, workspace, session and saved policy, with allow-once, allow-mission, allow-project, always-allow-matching-scope, deny and revoke.
  - A pending WAIT_APPROVAL decision survives crash/restart; approvals are durable, auditable and fail closed at the execution boundary when denied.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.2
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.2
- **Note:** Extends NL-BP-072/073 without rewriting their acceptance; the existing application filter is explicitly not an OS sandbox.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-169"></a>
### NL-BP-169 - Research: multi-provider web search router

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-168, NL-BP-073
- **Acceptance gates:**
  - Multiple configurable search providers are probed for availability at runtime (e.g. Brave/Tavily/Exa/other) with no mandatory paid API.
  - Supports general/technical/domain/date searches, query reformulation, source-reliability ranking, latency/cost/rate-limit policy and manual provider override.
  - When no provider is configured, offline/known-URL modes and honest limitations are shown.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Note:** No tracked search capability exists today; adjacent infrastructure is NL-BP-042 (MCP) and NL-BP-043 (project context retrieval).
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-170"></a>
### NL-BP-170 - Research: web page/document reader and JS browser automation

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-168, NL-BP-169
- **Acceptance gates:**
  - Fetches HTTP(S) resources with redirects/canonical URLs, HTML-to-readable text, code blocks, tables, PDFs, metadata and links under size/time limits and caching.
  - JavaScript-heavy documentation can be read through browser automation (e.g. Playwright), including optional accessibility tree, screenshots and forms, under a distinct permission.
  - SSRF protection covers localhost/private IP ranges unless explicitly authorized; retrieval provenance is retained.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Note:** Browser interaction is a separate capability/grant, not an implicit side effect of web search.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-171"></a>
### NL-BP-171 - Research: GitHub/repository investigator pinned to commit SHAs

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-168, NL-BP-073
- **Acceptance gates:**
  - Uses official GitHub REST/GraphQL and/or GitHub MCP for branches, tags, commits, API docs, code search, issues, PRs, reviews, changelog/release chronology, workflows, license and security disclosures.
  - Private-repository operations use only authorized tokens/scopes; discoveries are pinned to an actual commit SHA.
  - Never silently clones or executes untrusted projects.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Note:** New capability; no git-hosting investigator exists in the live backlog.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-172"></a>
### NL-BP-172 - Research: Hugging Face model investigator without checkpoint download

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-168, NL-BP-008
- **Acceptance gates:**
  - Reads Hub API metadata, model cards, file manifests, licensing/gates and revisions.
  - Reports architecture, quantization and RAM/VRAM/disk estimates with explicit uncertainty, plus compatibility with Ollama/llama.cpp/MLX/Transformers where applicable.
  - Discovery never downloads checkpoints, accepts licenses or runs model code.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Note:** Adjacent existing requirement: NL-BP-124 (shared model cache reuse) and NL-BP-008 (provider discovery); neither investigates Hub metadata.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-173"></a>
### NL-BP-173 - Research: ecosystem and package documentation discovery

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-169, NL-BP-170
- **Acceptance gates:**
  - Covers PyPI, crates.io, npm, NuGet, Qt, CMake, official SDK docs/release notes, compatibility data, vulnerability databases, migration guides, licenses and attribution.
  - Prefers primary sources and cross-checks contested claims.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Note:** Planned extension of the research engine; no package-ecosystem investigator exists today.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-174"></a>
### NL-BP-174 - Local-first research knowledge store with citations and provenance

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-169, NL-BP-170, NL-BP-171, NL-BP-172, NL-BP-043
- **Acceptance gates:**
  - Stores referenced excerpts with citation URL, retrieval timestamp, code/version/SHA, confidence and contradictions.
  - Uses local embeddings via existing services, deduplication, cache expiry/refresh and project/team knowledge sharing.
  - Untrusted retrieved code is never retained as executable instructions.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.1
- **Note:** Extends project context retrieval (NL-BP-043) to external research evidence; no web knowledge store exists today.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-175"></a>
### NL-BP-175 - Untrusted-source and prompt-injection resistance for research content

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-168, NL-BP-170
- **Acceptance gates:**
  - Web pages, repository text and model cards are treated as untrusted data, never as instructions; prompt-injection fixtures are ignored.
  - Network request permission is separated from trusting retrieved page content.
  - Retrieved instructions are never executed by default; research decisions and rejections are auditable.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.2
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.2
- **Note:** Security requirement for the research engine; dovetails with the full-autonomy disclosure (NL-BP-167).
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-176"></a>
### NL-BP-176 - Research-aware agent planning and upgrade/update checks

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-169, NL-BP-170, NL-BP-174, NL-BP-062
- **Acceptance gates:**
  - Permissioned research tools and citation-backed findings are woven into coding plans, update checks and library/model compatibility assessments.
  - Findings retain evidence links in mission decisions; no unsourced claims are presented as verified.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #4
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #4
- **Note:** Integration requirement for research-aware agents; the supervisor/next-mission machinery itself is NL-BP-061/062/063.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-177"></a>
### NL-BP-177 - Multi-root project workspace with read-only discovery first

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-077, NL-BP-043
- **Acceptance gates:**
  - Indexes several user-selected directories across drives, Git repositories and language ecosystems, read-only by default.
  - Never recursively scans all of K:\AI without explicit consent.
  - Supports Python/C++/Rust/JS/Go plus DAW/audio integration adapters; each root carries ownership and permission profiles.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3
- **Note:** Extends single-project discovery (NL-BP-077) to a multi-root workspace; no bulk sibling scan is authorized by this requirement.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-178"></a>
### NL-BP-178 - Project Genome: versioned measurable codebase intelligence map

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-177
- **Acceptance gates:**
  - Per project discovers launch/build entry points, dependency graph and lockfiles, Python ABI versions, CUDA/native library requirements, Git state, databases, models/caches, services, module/API boundaries, tests/coverage, shared assets/branding, licenses, target OS, runtime constraints, disk usage and known fragile assumptions.
  - Measured facts are separated from guesses; the map is versioned, searchable and refreshed incrementally.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.1
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.1
- **Note:** New capability; project facts exist in SQLite (project_facts) but there is no genome model/graph.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-179"></a>
### NL-BP-179 - Integration Forge: merge/keep-separate/share-service matrix and non-monolith architecture

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-178
- **Acceptance gates:**
  - Shows a merge/keep-separate/share-service matrix across the user's NL audio/video/voice/teleprompter projects, respecting actual code and ownership.
  - Proposes a common launcher/shell, modules/plugins, shared model hub and shared runtime where compatible, with isolated environments where ABI/backend conflicts require it.
  - Detects duplicate Python distributions, model checkpoints, FFmpeg, CUDA/ONNX/PyTorch, databases and packages; never forces a single Python runtime.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.2
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.2
- **Note:** Product-level Mega Suite foundation; no integration analysis exists today.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-180"></a>
### NL-BP-180 - Integration contracts: generated adapters, contract tests, migration shims and rollback

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-179, NL-BP-055
- **Acceptance gates:**
  - Generates typed module APIs, CLI/IPC adapters, migration shims, contract tests, service boundaries, config migration and rollback plans.
  - Uses staged gradual (strangler) migration instead of mass rewrite; integration edits stay in staging until independent gates pass.
  - Preserves functioning tools, user data, project identity and settings; compares functional outcomes on authorized golden fixtures where available.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.2
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.2
- **Note:** Implementation half of the Integration Forge; reuses the staged-candidate harness (NL-BP-055..060).
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-181"></a>
### NL-BP-181 - Integration Dashboard: readiness, conflicts, disk savings and reversible rollout

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-179, NL-BP-180
- **Acceptance gates:**
  - Dashboard shows projects, modules, integration readiness, incompatible dependencies, shared services, proposed moves, expected actual disk savings, test status, upgrade steps and reversible rollout.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.2
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.2
- **Note:** UI/reporting surface for the Integration Forge.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-182"></a>
### NL-BP-182 - Project-specific permission profiles for external projects

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-168, NL-BP-177
- **Acceptance gates:**
  - Per-external-project profiles define read-only discovery, approved modification, protected directories/tool paths and remote collaboration/access.
  - Profiles are separate from the owning user's project policy and can be revoked.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.2
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.2
- **Note:** Extends the permission engine (NL-BP-168) to other users' projects; no permission is granted by this planning requirement.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-188"></a>
### NL-BP-188 - Task-specific automation with controlled notifications

- **Area:** AUTONOMY - **Priority:** P2 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-075, NL-BP-067
- **Acceptance gates:**
  - Automates library updates, flaky-test tracking, benchmark/ASR model updates, release-readiness notifications and controlled periodic research.
  - No unapproved outward notifications or API costs; schedules and costs are auditable.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Note:** Scheduling/notification automation; existing diagnostics dashboard (NL-BP-075) is read-only.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-205"></a>
### NL-BP-205 - Search Provider Registry: capability matrix, no-key/public modes and explicit routing policy

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: universal web research & intelligence engine)
- **Dependencies:** NL-BP-169, NL-BP-168
- **Acceptance gates:**
  - An explicit provider capability matrix records search type, coverage/languages/recency, authentication requirements, cost class, rate limits and known limitations for every configured search provider.
  - Availability and no-key/public-provider modes are supported: providers that need no paid account work, and unavailable providers fail with an actionable status instead of a silent fallback.
  - Users can select a provider explicitly and deterministic routing (reliability/cost/privacy/latency) explains each choice; no silent paid-service use and no hidden cost.
  - Cost, privacy and rate-limit policy is persisted per project/mission and honoured by the router.
- **Evidence:**
  - not started - queued only by task-60 from the user directive; read-only capability audit in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability-gap evidence: docs/WEB_RESEARCH_CAPABILITY_AUDIT.md sections 3 and 5 (only local urllib Ollama/model probes, gated local-stdio MCP, unused web-research permissions, local-only attachments)
- **Sources:** user directive 2026-10-28: Universal Web Research & Intelligence Engine (task-60; audited in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md); docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; NL-BP-169; NL-BP-168
- **Note:** Registry gap after the router requirement NL-BP-169; complements permission scopes NL-BP-168/072 without rewriting them.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-206"></a>
### NL-BP-206 - Web retrieval safety policy: domain allow/deny, SSRF/private-IP, redirect and download limits, caching provenance

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: universal web research & intelligence engine)
- **Dependencies:** NL-BP-170, NL-BP-175
- **Acceptance gates:**
  - Domain allow/deny lists are enforced before every request including redirects; loopback/private/link-local targets are blocked unless an explicit grant authorizes them.
  - Per-mission rate limits, download size/time caps, maximum redirects and content-type limits are enforced and auditable.
  - Cached responses carry URL, redirect chain, retrieval timestamp and content hash as provenance; cache expiry/refresh is explicit.
  - Retrieved content is treated as untrusted; policy denials fail closed and are logged.
- **Evidence:**
  - not started - queued only by task-60 from the user directive; read-only capability audit in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability-gap evidence: docs/WEB_RESEARCH_CAPABILITY_AUDIT.md sections 3 and 5 (only local urllib Ollama/model probes, gated local-stdio MCP, unused web-research permissions, local-only attachments)
- **Sources:** user directive 2026-10-28: Universal Web Research & Intelligence Engine (task-60; audited in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md); docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; NL-BP-170; NL-BP-175
- **Note:** Safety gap distinct from NL-BP-175 (model/agent trust boundary); must exist before any real fetch is enabled.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-207"></a>
### NL-BP-207 - Research connectors registered through the existing tool registry/MCP with typed read-only permissions

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: universal web research & intelligence engine)
- **Dependencies:** NL-BP-171, NL-BP-172, NL-BP-073
- **Acceptance gates:**
  - Web, GitHub and Hugging Face connectors are registered through the existing tool registry/MCP surface with typed capabilities, versions, health checks and provenance.
  - Research tools are read-only and separated from write/install/publish/delete operations; grants are per connector/scope and revocable.
  - Connector results carry source URL/SHA/timestamp and are auditable; a connector cannot escalate its permissions.
- **Evidence:**
  - not started - queued only by task-60 from the user directive; read-only capability audit in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability-gap evidence: docs/WEB_RESEARCH_CAPABILITY_AUDIT.md sections 3 and 5 (only local urllib Ollama/model probes, gated local-stdio MCP, unused web-research permissions, local-only attachments)
- **Sources:** user directive 2026-10-28: Universal Web Research & Intelligence Engine (task-60; audited in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md); docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; NL-BP-171; NL-BP-172; NL-BP-073
- **Note:** Uses the existing registry/MCP infrastructure (NL-BP-073/042) rather than a second tool system.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-209"></a>
### NL-BP-209 - Version-aware official documentation research: SDK/API versions, changelogs and migration guides

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: universal web research & intelligence engine)
- **Dependencies:** NL-BP-170, NL-BP-173, NL-BP-174
- **Acceptance gates:**
  - Resolves the current authoritative version of a library/SDK/API and cites official docs, changelog and migration guide with primary-source preference.
  - Flags version mismatches and conflicting sources with uncertainty indicators; records retrieval time, version and SHA/revision.
  - Feeds task context and upgrade planning; never invents versions or breaking changes.
- **Evidence:**
  - not started - queued only by task-60 from the user directive; read-only capability audit in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability-gap evidence: docs/WEB_RESEARCH_CAPABILITY_AUDIT.md sections 3 and 5 (only local urllib Ollama/model probes, gated local-stdio MCP, unused web-research permissions, local-only attachments)
- **Sources:** user directive 2026-10-28: Universal Web Research & Intelligence Engine (task-60; audited in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md); docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; NL-BP-170; NL-BP-173; NL-BP-174
- **Note:** Extends ecosystem discovery (NL-BP-173) with version awareness and conflict/uncertainty handling.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-212"></a>
### NL-BP-212 - Universal Goal Mode core: goal creation, persistent multi-goal hierarchy and lifecycle

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-050, NL-BP-051, NL-BP-061, NL-BP-064, NL-BP-166
- **Acceptance gates:**
  - Users can create a goal from natural language with attachments/repository/reference material and observable acceptance criteria; goals are distinguishable from agent proposals and persist with provenance.
  - Persistent multi-goal hierarchy (goals > milestones > tasks/missions) with priorities, dependencies, ownership and pause/resume/cancel lifecycle; no goal is lost across restart or agent/model changes.
  - Reuses the existing supervisor, SQLite and Flow substrate instead of a parallel orchestrator; Goal Mode is available with CLI/API/GUI parity and explicit autonomy-policy integration.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-050; NL-BP-051; NL-BP-061; NL-BP-064; NL-BP-166
- **Note:** Executable depth for the hierarchy concept in NL-BP-050 (kept unchanged); reuses 051/061/064 and the Trusted profile 166.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-213"></a>
### NL-BP-213 - Adaptive goal decomposition and versioned replanning

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-212, NL-BP-062
- **Acceptance gates:**
  - A goal is decomposed into milestones/tasks/missions with priorities, dependencies, risks and validation criteria derived from the objective and evidence.
  - Replanning is versioned and triggered by new evidence, failures or changed constraints without silently discarding or rewriting the original objective; differences and rationale are persisted.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-212; NL-BP-062
- **Note:** Replaces the fixed checklist/next-mission heuristic for goal mode; the indexed-backlog selector (062) remains a valid fallback.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-214"></a>
### NL-BP-214 - Goal continuation scheduler: cross-goal eligible-task execution

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-212, NL-BP-061, NL-BP-062, NL-BP-064
- **Acceptance gates:**
  - Eligible tasks across multiple active goals are selected and executed without a new prompt, respecting policies, budgets and pause/stop.
  - Resource scheduling and conflict handling prevent concurrent unsafe writes and duplicate execution; reuses the existing mission queue/lease/claim substrate.
  - Continuation decisions are persisted and explainable (which goal/task, why selected, why deferred).
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-212; NL-BP-061; NL-BP-062; NL-BP-064
- **Note:** Cross-goal extension of the verified single-sequence supervisor (061/062); does not relax staged/independent gates.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-215"></a>
### NL-BP-215 - Independent goal completion verification against the original objective

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-212, NL-BP-054, NL-BP-058, NL-BP-060
- **Acceptance gates:**
  - A goal is never marked complete from its own checklist or agent claim; completion is verified against the original objective and acceptance criteria with independent evidence/tests.
  - Outstanding requirements, blockers, regressions and unverified manual items are reported explicitly; deliberate false-completion claims are rejected and persisted.
  - Verification reuses the staged-candidate/oracle and fail-closed gates instead of duplicating them.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-212; NL-BP-054; NL-BP-058; NL-BP-060
- **Note:** Goal-level layer over verified gate foundations 054/058/060; SH-07 Tier B (063) remains blocked.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-217"></a>
### NL-BP-217 - Reusable goal templates across projects and the NL Mega Suite

- **Area:** AUTONOMY - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-212, NL-BP-195
- **Acceptance gates:**
  - Goal templates (objective, acceptance criteria, milestones, constraints, risks) can be created, versioned, previewed and instantiated in unrelated projects.
  - Templates are reusable by the future NL Mega Suite integration path and never imply execution/approval by themselves.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-212; NL-BP-195
- **Note:** Extends the advisory GOAL_TEMPLATE.md into a real reusable system; depends on the planned Mega Suite installer 195.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-218"></a>
### NL-BP-218 - Document corpus discovery and ingestion with provenance

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-077, NL-BP-043, NL-BP-030
- **Acceptance gates:**
  - Discovers and ingests project documentation from folders/nested trees (README/AGENTS/specs/architecture/checklists/roadmaps), Markdown/text/PDF/Office/archives, Git repository documentation and authorized documentation URLs.
  - Every ingested item carries provenance (path/URL, hash, revision/timestamp, type) and is treated as untrusted input: content is never executed and unsafe archives are refused.
  - Ingestion is consent-based and bounded (no unbounded filesystem scanning, no silent network, no user secrets).
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-077; NL-BP-043; NL-BP-030
- **Note:** New corpus pipeline; reuses project discovery (077), context retrieval (043), local extraction (030) and research readers where URLs are authorized.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-219"></a>
### NL-BP-219 - Documentation reconciliation: authoritative sources, conflicts and obsolete requirements

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-218, NL-BP-178, NL-BP-174
- **Acceptance gates:**
  - Reconciles documentation against source/dependencies/tests/Git history: authoritative vs stale docs, version conflicts, obsolete instructions, missing or contradictory requirements.
  - Findings carry source provenance and severity; contradictions are surfaced rather than silently resolved.
  - Reconciliation results feed plan generation and remain versioned/re-runnable.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-218; NL-BP-178; NL-BP-174
- **Note:** New reconciliation engine; complementary to the planned Project Genome (178) and research store (174).
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-220"></a>
### NL-BP-220 - Requirement/objective/constraint/dependency/acceptance extraction with provenance

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-218, NL-BP-219, NL-BP-050
- **Acceptance gates:**
  - Extracts objectives, requirements, constraints (technical/legal/owner), dependencies and acceptance criteria from the documentation corpus.
  - Every extracted item cites its source document/excerpt and confidence; inferred items are labelled and never presented as explicit user requirements.
  - Extraction output is machine-readable and feeds plan generation without executing document content.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-218; NL-BP-219; NL-BP-050
- **Note:** New extraction layer; the goal/acceptance concept in 050 remains the record shape.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-221"></a>
### NL-BP-221 - Editable document-driven plan preview/approval with optional supervised execution

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-213, NL-BP-220, NL-BP-064, NL-BP-166
- **Acceptance gates:**
  - A document-driven plan can be previewed, edited, approved or rejected before execution, with rationale and provenance for each item.
  - Plan versions are persisted and immutable once executed; optional auto-execution runs only under the configured autonomy policy/approvals and can be paused/stopped.
  - Approval decisions and plan changes are audited.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-213; NL-BP-220; NL-BP-064; NL-BP-166
- **Note:** Consumes decomposition (213) and extraction (220) and autonomy policy (064/166); no silent auto-execution.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-222"></a>
### NL-BP-222 - Incremental documentation-change and new-evidence reconciliation

- **Area:** AUTONOMY - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-218, NL-BP-219, NL-BP-214, NL-BP-215
- **Acceptance gates:**
  - Document changes or new evidence are detected incrementally and reconciled with the active plan/goal without silently discarding verified progress or the original objective.
  - Changed assumptions/requirements trigger explainable replanning; unaffected verified work is preserved and re-verified where necessary.
  - Incremental results are versioned and auditable.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-218; NL-BP-219; NL-BP-214; NL-BP-215
- **Note:** Builds on reconciliation (219) and the continuation/verification requirements; avoids full re-planning from scratch.
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

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

<a id="nl-bp-234"></a>
### NL-BP-234 - Final repository/distribution readiness milestone with audit and justified refactor

- **Area:** HYGIENE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: final release hygiene and GitHub publication gate)
- **Dependencies:** NL-BP-090, NL-BP-095, NL-BP-096, NL-BP-110, NL-BP-140, NL-BP-149, NL-BP-162, NL-BP-197, NL-BP-198
- **Acceptance gates:**
  - A final audit produces the evidence deliverable: BEFORE/AFTER repository tree, exact moves/deletes/consolidations, disk and Git-history size analysis, security/licensing audit, and full regression/packaging results.
  - Where justified and authorized, the milestone refactors structure/root clutter/obsolete code/temp files/redundant components, dependency/runtime organization/compatibility/licensing, shared-vs-duplicated models/environments/assets, build/cache/logs/dev-data/ignored dirs, and distribution allowlist/package contents/launchers/installer.
  - Documentation is finalized for README, contributor setup, per-platform install, troubleshooting, limitations and release notes; cross-platform build reproduciblity and real-machine acceptance are reported honestly.
  - Source repository, local workspace and distributable app remain separated; protected assets/user data/models/runtimes/evidence/stale candidates are never deleted without owner authorization; code is removed only after dependency analysis and regression verification.
  - The public-source/beta-release readiness verdict lists explicit blockers (it cannot be a bare 'ready' claim).
- **Evidence:**
  - not started - queued only by task-70 from the user directive; read-only capability audit in docs/RELEASE_PUBLICATION_GATE_AUDIT.md; no code, model, network, push or publish run started
  - capability evidence: audit sections 3-4 (read-only hygiene/audits and acceptance tooling exist; secrets scanner NL-BP-162 verified but not wired to CI/hooks; owner gates/manual-pending external acceptance; no publication verdict artifact)
- **Sources:** user directive 2026-10-28: Final Release Hygiene & GitHub Publication Gate + mandatory pre-push secrets/content scan (task-70; audited in docs/RELEASE_PUBLICATION_GATE_AUDIT.md); docs/RELEASE_PUBLICATION_GATE_AUDIT.md; NL-BP-090; NL-BP-095; NL-BP-096; NL-BP-110; NL-BP-140; NL-BP-149; NL-BP-162; NL-BP-197; NL-BP-198
- **Note:** Program-level integration of per-domain hygiene/distribution/acceptance requirements; no existing requirement rewritten.
- **Program stage:** 10 - Final release hygiene and GitHub publication gate

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

<a id="nl-bp-152"></a>
### NL-BP-152 - Cross-platform compatibility audit and support matrix for Windows x64/ARM64, Linux x86_64/ARM64 and macOS Intel/Apple Silicon

- **Area:** DISTRO - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-149
- **Acceptance gates:**
  - every tracked module/native dependency is classified verified, partial or unsupported per OS/CPU
  - Windows-only code paths and assumptions are identified with file/line evidence
  - matrix distinguishes CI-verified from real-hardware MANUAL-PENDING support
  - audit is evidence-based (imports, platform APIs, wheels, subprocess flags), not a claim list
- **Evidence:**
  - not started; program directive 2026-10-28
  - Committed docs/PLATFORM_COMPATIBILITY_MATRIX.md (six-target, 13 feature rows incl. CI-vs-MANUAL-PENDING split, 17 Windows-first assumptions with file:line, 30-row native dependency matrix) and nl_coding_agent/core/platform_support.py + 31 tests. Audit/implementation evidence exists; non-Windows runtime/wheel availability remains unverified (no network) and only Windows x64 is locally exercised.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** Committed docs/PLATFORM_COMPATIBILITY_MATRIX.md (six-target, 13 feature rows incl. CI-vs-MANUAL-PENDING split, 17 Windows-first assumptions with file:line, 30-row native dependency matrix) and nl_coding_agent/core/platform_support.py + 31 tests. Audit/implementation evidence exists; non-Windows runtime/wheel availability remains unverified (no network) and only Windows x64 is locally exercised.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-153"></a>
### NL-BP-153 - Platform abstraction layer: OS/CPU detection, native adapters and clear unsupported-configuration handling

- **Area:** DISTRO - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-152
- **Acceptance gates:**
  - one shared application codebase with explicit platform adapters (paths, process creation flags, clipboard, audio, GPU probes)
  - unsupported combinations fail closed with actionable messages and never silently degrade
  - unit tests cover each declared platform branch without executing platform-specific hardware
  - no forked application codebase per OS
- **Evidence:**
  - not started
  - platform_support.py provides canonical six-target OS/CPU detection, fail-closed unsupported handling, feature declarations and read-only optional-backend probes (31 tests). Adapters are not yet wired through every GUI/CLI path; POSIX gaps identified in the matrix (detached flags, shell=True verification path, python.exe-only discovery, Windows resume strings, NVIDIA-only GPU probe).
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** platform_support.py provides canonical six-target OS/CPU detection, fail-closed unsupported handling, feature declarations and read-only optional-backend probes (31 tests). Adapters are not yet wired through every GUI/CLI path; POSIX gaps identified in the matrix (detached flags, shell=True verification path, python.exe-only discovery, Windows resume strings, NVIDIA-only GPU probe).
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-154"></a>
### NL-BP-154 - Native per-platform runtime provisioning manifests (Windows x64/ARM64, Linux x86_64/ARM64, macOS Intel/Apple Silicon), verified downloads and offline bundles

- **Area:** DISTRO - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-153, NL-BP-114
- **Acceptance gates:**
  - one runtime/dependency manifest per OS/CPU with pinned versions, sizes and sha256
  - provisioner never reuses Windows embedded Python or Windows binaries on Linux/macOS
  - downloads are hash+size verified with atomic staging; offline bundle path works
  - no global Python/pip/uv/conda required; manifests are validated by tests with fake artifacts
- **Evidence:**
  - not started; stage-6a installer supports a single template manifest only
  - installer/platform_targets.py, runtime_manifest.py/json and provision.py implement six native targets, host detection, strict native-identity guard (no Windows runtime on Linux/macOS), measured-only sha256/size policy, six-target release_ready gate, offline/cache/atomic/repair/update reuse and macOS separate-arch decision; 57 targeted tests. Real native runtime/dependency archives and clean-host execution remain MANUAL-PENDING.
  - Native runtime measurement path is verified end-to-end with synthetic archives: scripts/rehearse_release.py exercises fetch_native_runtimes offline measurement -> six-target measured draft (release_ready 6/6) -> build_release native candidate with per-target runtime archives -> manifest/hash validation, while canonical installer manifests stay byte-identical. Real runtime archives and hashes remain MANUAL-PENDING.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** Native runtime measurement path is verified end-to-end with synthetic archives: scripts/rehearse_release.py exercises fetch_native_runtimes offline measurement -> six-target measured draft (release_ready 6/6) -> build_release native candidate with per-target runtime archives -> manifest/hash validation, while canonical installer manifests stay byte-identical. Real runtime archives and hashes remain MANUAL-PENDING.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-155"></a>
### NL-BP-155 - Cross-platform bootstrapper CLI and native application candidates for private beta (Windows/Linux/macOS, x64+ARM64 where feasible)

- **Area:** DISTRO - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-154
- **Acceptance gates:**
  - install --target works per supported OS with no admin/global install
  - platform candidates contain the correct native runtime and launch the app
  - unsupported configurations are refused with clear guidance
  - CI builds are distinguished from real-hardware acceptance (MANUAL-PENDING)
- **Evidence:**
  - not started; stage-6b candidate is Windows-only
  - Cross-platform provisioner/planning exists for all six targets (installer/provision.py, bootstrap.py provision CLI, release-builder six-platform manifests); no real native application candidates/packages have been built or tested on Linux/macOS/ARM64 yet.
  - POSIX launchers now ship for Linux/macOS: scripts/launchers/NL Coding Agent.sh, doctor.sh, status.sh, Self-Build Mode.sh and a macOS .command wrapper, mapped by stage_portable to the payload root and staged executable; launchers resolve source vs payload layout, use provisioned python/bin/python3 when present, warn only for developer system-python fallback, fail closed when a packaged payload lacks a runtime, forward args and preserve exit codes. Native runtime archives and native candidates are still unmeasured/MANUAL-PENDING; launchers were statically/shell-syntax validated, not executed on a real non-Windows runtime.
  - POSIX launchers ship for Linux/macOS and the synthetic rehearsal proves the candidate/provisioning chain for all six targets (offline install+verify with the generated runtime/platform manifests); no real native candidate exists yet because native runtime archives are unmeasured/MANUAL-PENDING.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** POSIX launchers ship for Linux/macOS and the synthetic rehearsal proves the candidate/provisioning chain for all six targets (offline install+verify with the generated runtime/platform manifests); no real native candidate exists yet because native runtime archives are unmeasured/MANUAL-PENDING.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-156"></a>
### NL-BP-156 - GitHub Actions CI matrix: Windows, Ubuntu Linux and macOS (Apple Silicon and Intel where feasible)

- **Area:** DISTRO - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-152, NL-BP-155
- **Acceptance gates:**
  - workflows run unit, integration, headless GUI smoke and platform-specific bootstrapper checks
  - matrix includes Windows x64 (and ARM64 where feasible), Linux x86_64/ARM64, macOS arm64/x86_64
  - artifacts/checksums are produced per platform without publishing releases
  - CI success is not treated as full platform support (manual-pending remains)
- **Evidence:**
  - not started
  - .github/workflows/ci.yml implements the six-entry CI matrix (Windows x64 + experimental ARM64, Ubuntu x86_64 + experimental ARM64, macOS arm64 + Intel) with unit/integration/headless GUI/bootstrapper checks and report-only artifacts; 7 static/local-dry-run tests. Actual GitHub Actions execution and ARM64 runner availability remain MANUAL-PENDING; CI success is not platform support.
  - GitHub Actions CI now has the six-platform regression matrix plus a blocking package-smoke job on ubuntu-latest that builds a source candidate and beta package, runs the acceptance matrix (six targets, no CI hardware claim) and the native-runtime dry-run plan, uploading reports only; workflow is statically validated and locally dry-run (9 CI tests) but actual GitHub execution remains MANUAL-PENDING.
  - CI now includes the six-platform regression matrix, a blocking package-smoke job and a cross-platform reproducibility job (ubuntu-latest/windows-latest/macos-14); static tests validate jobs/guards and local runs PASS (package smoke 6/6; reproducibility 40/40), but actual GitHub Actions execution and cross-OS evidence remain MANUAL-PENDING.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** CI now includes the six-platform regression matrix, a blocking package-smoke job and a cross-platform reproducibility job (ubuntu-latest/windows-latest/macos-14); static tests validate jobs/guards and local runs PASS (package smoke 6/6; reproducibility 40/40), but actual GitHub Actions execution and cross-OS evidence remain MANUAL-PENDING.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-157"></a>
### NL-BP-157 - Optional CPU/GPU/ASR/TTS component policy and graceful degradation (no mandatory CUDA/ROCm/Metal/MLX)

- **Area:** DISTRO - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-153
- **Acceptance gates:**
  - capability probes report available/absent backends per platform
  - absent GPU/ASR/TTS backends degrade gracefully with explicit status, never a hard failure
  - optional components are the user's choice; no silent downloads
  - tests cover absent-backend paths
- **Evidence:**
  - not started
  - platform_support.py probes and declares optional GPU/ASR/TTS backends without executing hardware and never requires CUDA/ROCm/Metal/MLX; installer runtime manifests declare optional components with degradation notes. No real GPU/ASR/TTS backends installed/tested (MANUAL-PENDING).
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** platform_support.py probes and declares optional GPU/ASR/TTS backends without executing hardware and never requires CUDA/ROCm/Metal/MLX; installer runtime manifests declare optional components with degradation notes. No real GPU/ASR/TTS backends installed/tested (MANUAL-PENDING).
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-158"></a>
### NL-BP-158 - macOS Universal 2 feasibility decision and architecture-specific builds where Universal 2 is not feasible

- **Area:** DISTRO - **Priority:** P2 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-154, NL-BP-156
- **Acceptance gates:**
  - native dependency support for universal2 is measured and documented
  - if universal2 is infeasible (e.g. standalone runtime lacks universal2), separate arm64/x86_64 builds are produced
  - decision and evidence recorded, no unverified universal claim
- **Evidence:**
  - not started
  - macOS Universal 2 decision recorded: separate macos-x86_64/macos-arm64 runtimes are provisioned; universal artifact is only schema-legal when measured and shared by both targets. No macOS build has been produced/tested (MANUAL-PENDING).
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** macOS Universal 2 decision recorded: separate macos-x86_64/macos-arm64 runtimes are provisioned; universal artifact is only schema-legal when measured and shared by both targets. No macOS build has been produced/tested (MANUAL-PENDING).
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-184"></a>
### NL-BP-184 - Build/Test Laboratory for multi-platform engineering

- **Area:** DISTRO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-140, NL-BP-122, NL-BP-119
- **Acceptance gates:**
  - Covers Windows and macOS/Linux targets with unit, integration, property, fuzz and security test lanes plus UI/hardware manual checkpoints.
  - Includes audio/video golden-fixture tests where relevant, reproducibility checks and runner provenance.
  - Provides precise failure isolation and never declares platform support from synthetic fixtures alone.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Note:** Extends the existing acceptance/reproducibility work (NL-BP-140/122/119) into a laboratory surface; real hardware remains manual-pending.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-185"></a>
### NL-BP-185 - Dependency and Supply Chain Lab

- **Area:** DISTRO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-121, NL-BP-122, NL-BP-184
- **Acceptance gates:**
  - Maintains dependency graph, SBOM, vulnerability advisories, license obligations and version pinning.
  - Verifies signatures/hashes and performs policy-controlled download/install into a private install root/cache; tests dependencies before upgrades.
  - Audits public Git history and tracked files before any first public push.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Note:** Extends NL-BP-121 (license/SBOM/secret-free payload) and NL-BP-162 (pre-upload audit); new lab-level tooling/automation is missing.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-186"></a>
### NL-BP-186 - Source control and collaboration integration (GitHub/GitLab)

- **Area:** DISTRO - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-168, NL-BP-073
- **Acceptance gates:**
  - Integrates GitHub/GitLab/remote providers for PR/issue management, branch/worktree isolation, code-owner protections, conflict detection, review provenance and optional scheduled CI monitoring.
  - Requires human approval for public release or credentialed writes; no push/publish/visibility change without explicit owner authorization.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #6
- **Note:** Git tooling exists only locally (NL-BP-039); remote collaboration/PR management is new.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-195"></a>
### NL-BP-195 - Mega Suite modular installer with shared model cache and storage plan

- **Area:** DISTRO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-116, NL-BP-124
- **Acceptance gates:**
  - Installer selects individual products/modules and inference backends; shared model cache never duplicates weights.
  - Optional per-module isolated environment where dependencies conflict; a visible storage plan precedes installation.
  - Per-module update/uninstall preserves other modules and user data.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #7
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #7
- **Note:** Extends NL-BP-116/124; new is Mega-Suite-level modular selection plus storage plan.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-196"></a>
### NL-BP-196 - Self-update with atomic deployment, verified manifests and previous-app fallback

- **Area:** DISTRO - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-117, NL-BP-122
- **Acceptance gates:**
  - Atomic deployment with verified manifests and fallback to the previous working application.
  - Data-schema migrations are reversible where possible and never corrupt in-progress tasks.
  - Supports integrity repair/uninstall and clear storage reclaim.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #7
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #7
- **Note:** Extends NL-BP-117 repair/update baseline with explicit atomic deploy/fallback and migration safety.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

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

<a id="nl-bp-159"></a>
### NL-BP-159 - Private beta release packages: checksums, versioned manifests and non-developer installation instructions

- **Area:** RELEASE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-155
- **Acceptance gates:**
  - per-platform beta packages with sha256 checksums and versioned manifests
  - installation instructions are written for non-developers and are platform-specific
  - packages contain no development data, databases, checkpoints or vendor copies
  - packages are prepared locally/artifacts only; no release upload without owner authorization
- **Evidence:**
  - not started
  - scripts/build_beta_packages.py + tests (11) produce a deterministic private-beta package from a measured source candidate: SHA256SUMS, versioned beta-manifest with six-target unmeasured runtime entries, installer manifests without fabricated hashes, INSTALL.md plus six per-platform install docs, BETA_README/VERSION and source zip. Real source-only package .workspace/dist/beta-0.2.0 (14 files / 1,097,875 B, 13 checksum entries verified, byte-identical rebuild) exists; native platform runtime packages/clean-host acceptance and signing remain MANUAL-PENDING.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** scripts/build_beta_packages.py + tests (11) produce a deterministic private-beta package from a measured source candidate: SHA256SUMS, versioned beta-manifest with six-target unmeasured runtime entries, installer manifests without fabricated hashes, INSTALL.md plus six per-platform install docs, BETA_README/VERSION and source zip. Real source-only package .workspace/dist/beta-0.2.0 (14 files / 1,097,875 B, 13 checksum entries verified, byte-identical rebuild) exists; native platform runtime packages/clean-host acceptance and signing remain MANUAL-PENDING.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-160"></a>
### NL-BP-160 - Cross-platform compatibility matrix documentation: GUI, editor, clipboard, attachments, microphone, ASR/TTS, Ollama, CrewAI, terminal, Git, LSP, MCP, GPU

- **Area:** RELEASE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-152
- **Acceptance gates:**
  - matrix rows cover every feature area x platform/architecture with verified/experimental/unsupported and MANUAL-PENDING labels
  - platform-specific limitations are documented (no OS sandbox, hardware requirements, absence of optional backends)
  - matrix is kept in sync with CI evidence
- **Evidence:**
  - not started
  - docs/PLATFORM_COMPATIBILITY_MATRIX.md covers the 13 feature areas x six targets with verified/partial/unsupported + MANUAL-PENDING and native-dependency evidence; it is being re-synced to the current HEAD (task-47) and real CI/hardware evidence is still absent.
  - Compatibility matrix/launcher sections updated for shipped POSIX .sh/.command launchers and their payload mapping, with runtime unmeasured/MANUAL-PENDING and no support-level upgrade; CI package-smoke coverage documented.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** Compatibility matrix/launcher sections updated for shipped POSIX .sh/.command launchers and their payload mapping, with runtime unmeasured/MANUAL-PENDING and no support-level upgrade; CI package-smoke coverage documented.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-161"></a>
### NL-BP-161 - Private beta feedback workflow: GitHub Issue templates and opt-in diagnostic report generator with redaction

- **Area:** RELEASE - **Priority:** P1 - **Status:** verified
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-159
- **Acceptance gates:**
  - bug/feature issue templates collect platform, version and reproduction steps
  - diagnostic report generator is opt-in and redacts secrets, API keys, personal paths, project content and database rows
  - redaction is tested with fixture secrets/paths and never uploads automatically
  - report can be attached to a GitHub issue manually
- **Evidence:**
  - not started
  - tests/test_diagnostic_report.py (31 tests) proves opt-in local-only reports and redaction of API keys/tokens, private keys, credential URLs, cloud ids, usernames/home and personal absolute paths, plus not-collected project content/DB rows/env; .github/ISSUE_TEMPLATE beta forms validate; docs/BETA_TESTING.md and PRIVATE_BETA_RUNBOOK.md cover triage/authorization. Reports never upload automatically.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** tests/test_diagnostic_report.py (31 tests) proves opt-in local-only reports and redaction of API keys/tokens, private keys, credential URLs, cloud ids, usernames/home and personal absolute paths, plus not-collected project content/DB rows/env; .github/ISSUE_TEMPLATE beta forms validate; docs/BETA_TESTING.md and PRIVATE_BETA_RUNBOOK.md cover triage/authorization. Reports never upload automatically.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-162"></a>
### NL-BP-162 - Pre-upload audit of tracked files and Git history: secrets, private databases, embedded runtimes, vendor copies and heavyweight build outputs

- **Area:** RELEASE - **Priority:** P0 - **Status:** verified
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** none
- **Acceptance gates:**
  - read-only audit scans tracked files and Git history for secret patterns, DB/runtime/vendor/heavy files
  - findings are classified and reported with redacted evidence
  - no publishing action is performed by the audit
  - the existing private repository is preserved
- **Evidence:**
  - not started
  - scripts/audit_release_secrets.py + 12 temp-Git-fixture tests + docs/SECRETS_AUDIT.md: read-only tracked-files and bounded Git-history scan with redacted evidence, classifications and exit-code upload gate; measured HEAD b139065 snapshot 321 tracked files/50 commits, 0 blocking (CLEAR-WITH-REVIEW). Re-run required before any actual upload because the tree changed; no publishing action performed.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** scripts/audit_release_secrets.py + 12 temp-Git-fixture tests + docs/SECRETS_AUDIT.md: read-only tracked-files and bounded Git-history scan with redacted evidence, classifications and exit-code upload gate; measured HEAD b139065 snapshot 321 tracked files/50 commits, 0 blocking (CLEAR-WITH-REVIEW). Re-run required before any actual upload because the tree changed; no publishing action performed.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-163"></a>
### NL-BP-163 - Private repository and release authorization gates: no push, visibility change, collaborator invite or release upload without explicit owner authorization

- **Area:** RELEASE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-162
- **Acceptance gates:**
  - runbook documents owner-only upload/publish steps and authorization requirements
  - CI/release scripts have no push/publish/visibility actions
  - developer data, runtimes and model checkpoints are excluded from artifacts
  - the existing private repository is not modified
- **Evidence:**
  - not started
  - docs/PRIVATE_BETA_RUNBOOK.md defines owner gates G-1..G-10 (no push/remote change, visibility change, collaborator invites, release upload, public posting, telemetry, history rewrite or evidence deletion without explicit owner authorization), pre-upload checklist, package content rules and per-release authorization template; CI/release static guards reject publish/push actions. Owner authorization for any external beta distribution is still required and pending.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** docs/PRIVATE_BETA_RUNBOOK.md defines owner gates G-1..G-10 (no push/remote change, visibility change, collaborator invites, release upload, public posting, telemetry, history rewrite or evidence deletion without explicit owner authorization), pre-upload checklist, package content rules and per-release authorization template; CI/release static guards reject publish/push actions. Owner authorization for any external beta distribution is still required and pending.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-164"></a>
### NL-BP-164 - Cross-platform release acceptance criteria extension with MANUAL-PENDING clean-machine and real-hardware matrix

- **Area:** RELEASE - **Priority:** P0 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-141, NL-BP-142, NL-BP-156, NL-BP-160
- **Acceptance gates:**
  - acceptance criteria are extended to Windows x64/ARM64, Linux x86_64/ARM64 and macOS Intel/Apple Silicon
  - clean-machine installation, GUI interaction, clipboard, microphone/ASR/TTS and GPU items are marked MANUAL-PENDING until tested on real systems
  - CI builds alone never mark raw platform support complete
  - beta acceptance records tester, OS/CPU, package checksum and result
- **Evidence:**
  - not started
  - docs/RELEASE_ACCEPTANCE.md now carries the cross-platform acceptance matrix for Windows x64/ARM64, Linux x86_64/ARM64 and macOS Intel/Apple Silicon with explicit MANUAL-PENDING real-hardware/clean-machine items; no real cross-platform acceptance has been recorded.
  - Acceptance-matrix tooling and docs exist (docs/BETA_ACCEPTANCE.md, docs/RELEASE_ACCEPTANCE.md cross-platform criteria) and the generated matrix records all six targets as MANUAL-PENDING; no real-hardware/clean-machine acceptance records exist yet.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** Acceptance-matrix tooling and docs exist (docs/BETA_ACCEPTANCE.md, docs/RELEASE_ACCEPTANCE.md cross-platform criteria) and the generated matrix records all six targets as MANUAL-PENDING; no real-hardware/clean-machine acceptance records exist yet.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-165"></a>
### NL-BP-165 - Cross-platform CI artifact provenance and real-hardware beta acceptance evidence

- **Area:** RELEASE - **Priority:** P1 - **Status:** partial
- **Blueprint priority:** new (cross-platform private beta directive 2026-10-28)
- **Dependencies:** NL-BP-156, NL-BP-159
- **Acceptance gates:**
  - per-platform artifacts carry version manifest, checksums and CI job provenance
  - real-hardware beta results are recorded separately from CI results
  - unverified configurations remain experimental/unsupported until tested
  - one authoritative beta acceptance report is maintained
- **Evidence:**
  - not started
  - scripts/ci/checksums.py and CI report artifacts/checksums are implemented and tested; per-platform native packages and real-hardware beta acceptance records do not exist yet (MANUAL-PENDING).
  - Beta package builder produces checksummed/versioned candidate manifests; acceptance-matrix tool validates CI-vs-real-hardware evidence and rejects false CI support claims. Real per-platform runtime artifacts, CI execution and real-hardware acceptance records remain MANUAL-PENDING.
  - Package-smoke job produces deterministic package_smoke.json + SHA256SUMS report artifacts (reports-only upload, short retention) and validates source/beta package checksums, manifests and the acceptance matrix; real native artifacts, actual CI-triggered runs and real-hardware acceptance records remain MANUAL-PENDING.
  - Reproducible source-release check proves deterministic archives/manifests and forbidden-content exclusions locally (40/40 checks) and is wired into a cross-platform CI job; synthetic rehearsal proves the full fetch->draft->candidate->beta->provision->acceptance wiring with explicit NOT-A-RELEASE reporting. Real native artifacts, actual CI-triggered evidence and real-hardware records remain MANUAL-PENDING.
- **Sources:** user cross-platform beta program directive 2026-10-28
- **Note:** Reproducible source-release check proves deterministic archives/manifests and forbidden-content exclusions locally (40/40 checks) and is wired into a cross-platform CI job; synthetic rehearsal proves the full fetch->draft->candidate->beta->provision->acceptance wiring with explicit NOT-A-RELEASE reporting. Real native artifacts, actual CI-triggered evidence and real-hardware records remain MANUAL-PENDING.
- **Program stage:** 6 - Lightweight portable/bootstrapper and final release testing (extended cross-platform private beta)

<a id="nl-bp-189"></a>
### NL-BP-189 - Operating metrics and user-visible health dashboard

- **Area:** RELEASE - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-075, NL-BP-140
- **Acceptance gates:**
  - Dashboard exposes successful missions, failed gates, regressions prevented, recovery actions, API/network usage, disk/caches by owner, RAM/VRAM, inference speed and model capabilities/confidence.
  - Logs are privacy-aware with rotation; measured and estimated values remain distinct.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Note:** Extends NL-BP-075 hospital/health diagnostics (autonomy area) with user-visible program metrics; kept in release area as evidence/readiness surface.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-197"></a>
### NL-BP-197 - Source-vs-binary release separation and public-repository readiness

- **Area:** RELEASE - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-162, NL-BP-163, NL-BP-140
- **Acceptance gates:**
  - Public source releases contain clean sources and eligible build artifacts only, excluding private state, user files, caches, runtimes, secret history, heavy models and vendor clones.
  - Binary releases are managed separately; nothing is uploaded without owner authorization.
  - Docs state that changing a repository from public to private cannot revoke already-downloaded copies.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #7
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #7
- **Note:** Extends NL-BP-162/163 with explicit source-vs-binary separation and public visibility rules.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-198"></a>
### NL-BP-198 - Readiness taxonomy enforced across evidence and reports

- **Area:** RELEASE - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-140, NL-BP-151, NL-BP-164
- **Acceptance gates:**
  - Enforces the labels implemented, fixture-verified, real-model-verified, real-hardware-verified, manually-pending, blocked and planned in evidence reports/tooling.
  - Labels are never conflated; acceptance records carry the exact label and evidence.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Note:** Extends the status vocabulary into machine-enforced readiness labels; no existing acceptance is rewritten.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-199"></a>
### NL-BP-199 - Cross-app acceptance scenario on real projects

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-152, NL-BP-164, NL-BP-144, NL-BP-145, NL-BP-147, NL-BP-148, NL-BP-149, NL-BP-177, NL-BP-169
- **Acceptance gates:**
  - Import two unrelated projects, analyze real code, permit a known external SDK tool, research verified docs/GitHub/HF, patch only in isolated staging, run trusted baseline tests and promote a safe change.
  - Use GUI screenshot paste and ASR, hand a mission over across a restart, build a portable candidate on another target and verify a user-selectable installer path.
  - Real hardware and external/manual checks stay separate from simulated tests.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Note:** End-to-end program acceptance scenario; depends on stages 1-6 plus the new capabilities.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-200"></a>
### NL-BP-200 - Full Autonomy acceptance scenario

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-166, NL-BP-167, NL-BP-168, NL-BP-063, NL-BP-061
- **Acceptance gates:**
  - Issue a broad goal, configure Trusted or Full scopes and observe several distinct missions without routine prompts.
  - Demonstrate independent reviewer rejection with actual bounded repair, no accidental cloud calls and no silent irreversible actions outside the approved policy.
  - Show the user how to inspect and revoke saved approvals.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Note:** Acceptance scenario for the new profiles; SH-07 Tier B (NL-BP-063) must be genuinely verified first, never relaxed.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-201"></a>
### NL-BP-201 - Mega Suite integration acceptance scenario

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-177, NL-BP-179, NL-BP-180, NL-BP-195
- **Acceptance gates:**
  - Detect a duplicate checkpoint/runtime, propose safe consolidation and execute one approved modular integration that preserves both original products.
  - Build installer modules and validate on real target-OS hardware.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #8
- **Note:** Acceptance scenario for the Integration Forge and Mega Suite installer.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-202"></a>
### NL-BP-202 - Trusted Auto Review acceptance scenario

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-166, NL-BP-168, NL-BP-072
- **Acceptance gates:**
  - Demonstrate dozens of allowed routine actions with no prompts, blocked writes outside declared scope and approved external FFmpeg execution.
  - Prove persistence/revocation after restart, pending-approval expiry/deny and that an untrusted page's prompt injection is ignored.
  - Prove the Code Reviewer can reject even in Full Autonomy, emergency stop leaves no orphaned workers and lock/lease recovery is correct.
  - Document realistic Full Autonomy limits rather than advertising unbreakable security.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.3
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #1.3
- **Note:** Acceptance scenario for the autonomy profiles; complements NL-BP-200.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-203"></a>
### NL-BP-203 - Research engine acceptance: real network vs fixtures

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-169, NL-BP-170, NL-BP-171, NL-BP-172, NL-BP-173, NL-BP-174, NL-BP-175
- **Acceptance gates:**
  - Real-network tests locate a current API, verify a GitHub issue and related commit, inspect an HF model without checkpoint download, read JS-rendered docs and cite current versions correctly.
  - Denied-network and prompt-injection tests pass; retrieved evidence is preserved in the project research library and usable as task context.
  - Fixtures alone never count as real-network verification.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.2
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #2.2
- **Note:** Acceptance scenario for the research engine.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-204"></a>
### NL-BP-204 - Multi-project Genome/Integration Forge acceptance on real projects

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user addendum 2026-10-28: universal autonomy, research and Mega Suite)
- **Dependencies:** NL-BP-177, NL-BP-178, NL-BP-179, NL-BP-180, NL-BP-181
- **Acceptance gates:**
  - On at least two distinct real projects, produce a fact-backed dependency/integration report and identify one shareable component and one genuine incompatibility.
  - Implement a small cross-project integration in staging, run contract tests, prove both original tools remain functional and roll back without touching the other project's unsaved work.
  - Record useful disk savings without blind deletion.
- **Evidence:**
  - not started - queued only by task-59 from the user addendum; no code, mission or network run was started
  - source: docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.3
- **Sources:** docs/product-blueprint/addenda/2026-10-28_UNIVERSAL_AUTONOMY_RESEARCH_MEGASUITE.md #3.3
- **Note:** Acceptance scenario for the Project Genome and Integration Forge.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-211"></a>
### NL-BP-211 - Research acceptance extension: fixture-vs-real-network matrix and cross-project evidence reuse

- **Area:** RELEASE - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: universal web research & intelligence engine)
- **Dependencies:** NL-BP-203, NL-BP-205, NL-BP-206, NL-BP-207, NL-BP-208, NL-BP-209, NL-BP-210
- **Acceptance gates:**
  - A fixture-vs-real-network matrix covers provider failures/timeouts/rate limits, offline/denied network, domain restrictions, SSRF attempts, prompt injection, license-gated HF flows and reuse of stored evidence in arbitrary-project missions.
  - Each case is labelled fixture-verified vs real-network-verified vs manual-pending; fixtures never count as real-network verification.
  - Stored research evidence is reusable across projects with provenance and permission checks.
- **Evidence:**
  - not started - queued only by task-60 from the user directive; read-only capability audit in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability-gap evidence: docs/WEB_RESEARCH_CAPABILITY_AUDIT.md sections 3 and 5 (only local urllib Ollama/model probes, gated local-stdio MCP, unused web-research permissions, local-only attachments)
- **Sources:** user directive 2026-10-28: Universal Web Research & Intelligence Engine (task-60; audited in docs/WEB_RESEARCH_CAPABILITY_AUDIT.md); docs/WEB_RESEARCH_CAPABILITY_AUDIT.md; NL-BP-203; NL-BP-205; NL-BP-206; NL-BP-207; NL-BP-208; NL-BP-209; NL-BP-210
- **Note:** Extends the addendum's real-network acceptance requirement (NL-BP-203) with the full failure/exception matrix.
- **Program stage:** 7 - Universal autonomy, research intelligence and Mega Suite

<a id="nl-bp-223"></a>
### NL-BP-223 - Document-driven goal acceptance scenario on an unfamiliar project

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directives 2026-10-28: Universal Goal Mode + document-driven planning)
- **Dependencies:** NL-BP-212, NL-BP-213, NL-BP-214, NL-BP-215, NL-BP-216, NL-BP-218, NL-BP-219, NL-BP-220, NL-BP-221, NL-BP-222
- **Acceptance gates:**
  - Import an unfamiliar documentation-rich project; produce a traceable plan deriving requirements/constraints/acceptance from its docs.
  - Insert a deliberately false completion claim and prove independent verification rejects it; execute an eligible task under policy and preserve progress across restart.
  - Cover docs-only projects without runnable tests via honest document-consistency evidence; label synthetic vs real evidence distinctly.
- **Evidence:**
  - not started - queued only by task-68 from the user directives; read-only capability audit in docs/GOAL_MODE_CAPABILITY_AUDIT.md; no code, mission or network run started
  - capability evidence: audit sections 3-4 (SQLite has no goals/milestones tables; supervisor/queue/lease/Flow substrate exists; no Goals GUI/CLI; local-only document ingestion; GOAL_TEMPLATE is advisory only)
- **Sources:** user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning (task-68; audited in docs/GOAL_MODE_CAPABILITY_AUDIT.md); docs/GOAL_MODE_CAPABILITY_AUDIT.md; NL-BP-212; NL-BP-213; NL-BP-214; NL-BP-215; NL-BP-216; NL-BP-218; NL-BP-219; NL-BP-220; NL-BP-221; NL-BP-222
- **Note:** End-to-end acceptance for stage 8; separate from research acceptance (203/211) and cross-app scenario (199).
- **Program stage:** 8 - Universal Goal Mode and document-driven planning

<a id="nl-bp-233"></a>
### NL-BP-233 - Open-provider acceptance scenario on real endpoints

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: open model and provider ecosystem)
- **Dependencies:** NL-BP-224, NL-BP-225, NL-BP-226, NL-BP-227, NL-BP-228, NL-BP-229, NL-BP-230, NL-BP-231, NL-BP-232
- **Acceptance gates:**
  - Connect a custom OpenAI-compatible endpoint, llama.cpp and LM Studio, plus an Ollama community-namespace model or custom fine-tune; use both discovery and manual entry.
  - Apply per-role profiles and verify unknown capabilities are displayed with warnings, routing explanations/overrides and unsupported-combination warnings without arbitrary rejection.
  - Verify permission/cloud-spending controls and profile import/export/reuse across projects; evidence distinguishes fixture-verified vs real-endpoint-verified vs manual-pending.
- **Evidence:**
  - not started - queued only by task-69 from the user directive; read-only capability audit in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; no code, model or network run started
  - capability evidence: audit sections 3-4 (fixed YAML provider schema, closed kind branch, Bearer-only auth, temperature-only params, read-only Model Hub GUI, unwired router, measured-only capability gating)
- **Sources:** user directive 2026-10-28: Open Model & Provider Ecosystem (task-69; audited in docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md); docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md; NL-BP-224; NL-BP-225; NL-BP-226; NL-BP-227; NL-BP-228; NL-BP-229; NL-BP-230; NL-BP-231; NL-BP-232
- **Note:** End-to-end acceptance for stage 9; real endpoints are permissioned/manual and cannot be claimed from fixtures alone.
- **Program stage:** 9 - Open model and provider ecosystem

<a id="nl-bp-235"></a>
### NL-BP-235 - Mandatory blocking pre-push secrets/content scan gate

- **Area:** RELEASE - **Priority:** P0 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: final release hygiene and GitHub publication gate)
- **Dependencies:** NL-BP-162, NL-BP-163
- **Acceptance gates:**
  - A separately runnable CLI gate plus Git hook and CI integration block a push/publication when the scan fails (fail closed, non-zero exit, no silent bypass).
  - The gate scans staged changes, tracked files and Git history for credentials/tokens/secrets, private data, personal paths/sensitive configuration, embedded runtimes/vendor copies/large blobs and development data.
  - Findings are redacted in output/reports; the gate itself never pushes, publishes or modifies the repository.
  - The gate is runnable before ANY earlier public GitHub upload and must not be deferred to the final milestone; repeatably run at the actual release HEAD.
- **Evidence:**
  - not started - queued only by task-70 from the user directive; read-only capability audit in docs/RELEASE_PUBLICATION_GATE_AUDIT.md; no code, model, network, push or publish run started
  - capability evidence: audit sections 3-4 (read-only hygiene/audits and acceptance tooling exist; secrets scanner NL-BP-162 verified but not wired to CI/hooks; owner gates/manual-pending external acceptance; no publication verdict artifact)
- **Sources:** user directive 2026-10-28: Final Release Hygiene & GitHub Publication Gate + mandatory pre-push secrets/content scan (task-70; audited in docs/RELEASE_PUBLICATION_GATE_AUDIT.md); docs/RELEASE_PUBLICATION_GATE_AUDIT.md; NL-BP-162; NL-BP-163
- **Note:** NL-BP-162 provides the verified scanner and exit-code upload gate but is manual (no hooks/CI wiring); 235 adds mandatory blocking enforcement without rewriting 162.
- **Program stage:** 10 - Final release hygiene and GitHub publication gate

<a id="nl-bp-236"></a>
### NL-BP-236 - Publication readiness verdict and external-acceptance gate

- **Area:** RELEASE - **Priority:** P1 - **Status:** planned
- **Blueprint priority:** new (user directive 2026-10-28: final release hygiene and GitHub publication gate)
- **Dependencies:** NL-BP-140, NL-BP-162, NL-BP-163, NL-BP-164, NL-BP-165, NL-BP-197, NL-BP-198
- **Acceptance gates:**
  - An evidence-backed public-source/beta-release readiness verdict is recorded with explicit blockers, linked acceptance evidence and the exact scanned HEAD.
  - No 'publication ready' verdict may be recorded while real external acceptance (hardware/clean-machine/real-network/actual CI/beta records) remains unresolved or unverified; those items stay MANUAL-PENDING and block the verdict.
  - Owner authorization and residual-risk sign-off are recorded for the specific artifact/scope, consistent with the owner gates; a queued requirement grants no standing authorization.
- **Evidence:**
  - not started - queued only by task-70 from the user directive; read-only capability audit in docs/RELEASE_PUBLICATION_GATE_AUDIT.md; no code, model, network, push or publish run started
  - capability evidence: audit sections 3-4 (read-only hygiene/audits and acceptance tooling exist; secrets scanner NL-BP-162 verified but not wired to CI/hooks; owner gates/manual-pending external acceptance; no publication verdict artifact)
- **Sources:** user directive 2026-10-28: Final Release Hygiene & GitHub Publication Gate + mandatory pre-push secrets/content scan (task-70; audited in docs/RELEASE_PUBLICATION_GATE_AUDIT.md); docs/RELEASE_PUBLICATION_GATE_AUDIT.md; NL-BP-140; NL-BP-162; NL-BP-163; NL-BP-164; NL-BP-165; NL-BP-197; NL-BP-198
- **Note:** Consumes the verified acceptance matrix/secrets audit and owner gates; explicit verdict artifact is new.
- **Program stage:** 10 - Final release hygiene and GitHub publication gate

## Addendum import v3.7 - Universal Autonomy/Research/Mega Suite dedupe mapping

User-supplied addendum (2026-10-28) preserved unchanged at docs/product-blueprint/addenda/ (MANIFEST verified). Queue-only import by shared task-59: the spec was cross-checked against the 117 existing requirements; only genuinely missing capabilities were added. Existing IDs, acceptance criteria and statuses were not rewritten; stages 1-6 statuses were not changed.

| Group | Capability | Addendum section | Existing coverage | New requirements | Decision |
|---|---|---|---|---|---|
| G1 | Autonomy profiles and separate control knobs (Trusted Auto Review, Full Autonomy) | #1.1 | NL-BP-064, NL-BP-072, NL-BP-073, NL-BP-076, NL-BP-024 | NL-BP-166, NL-BP-167, NL-BP-168 | Extends existing modes/permission model with new profiles; existing acceptance unchanged. |
| G2 | Trusted Auto Review / Full Autonomy acceptance scenario | #1.3 | NL-BP-004, NL-BP-005, NL-BP-054, NL-BP-058, NL-BP-060, NL-BP-065 | NL-BP-202 | Independent review/gates already covered; acceptance scenario is new. |
| G3 | Web search router and web page/document reader with JS browser | #2.1 | NL-BP-042, NL-BP-043, NL-BP-009 | NL-BP-169, NL-BP-170 | MCP/project-context infrastructure exists; external web research is new. |
| G4 | GitHub / Hugging Face / ecosystem investigators | #2.1 | NL-BP-042 | NL-BP-171, NL-BP-172, NL-BP-173 | No repository-model-ecosystem investigator exists today. |
| G5 | Local-first research knowledge store and injection resistance | #2.1-2.2 | NL-BP-074, NL-BP-043 | NL-BP-174, NL-BP-175 | Model-facing trust boundary and project context exist; research evidence store/injection rules are new. |
| G6 | Research-aware planning and update checks | #4 | NL-BP-061, NL-BP-062, NL-BP-063 | NL-BP-176 | Supervisor/backlog machinery exists; research-aware planning is new. |
| G7 | Multi-root workspace and Project Genome | #3-3.1 | NL-BP-077, NL-BP-043 | NL-BP-177, NL-BP-178 | Single-project discovery exists; multi-root/genome is new. |
| G8 | Integration Forge: matrix, contracts, dashboard, external-project profiles | #3.2 | NL-BP-055, NL-BP-072, NL-BP-121, NL-BP-122 | NL-BP-179, NL-BP-180, NL-BP-181, NL-BP-182 | Staged candidates/gates and hygiene tooling exist; cross-project integration forge is new. |
| G9 | Model Competence Lab (multi-backend inspection, benchmark harness, independent judge) | #4 | NL-BP-008, NL-BP-009, NL-BP-068, NL-BP-069, NL-BP-070 | NL-BP-183 | Competence index/advisor/capability registry exist; lab-level multi-backend benchmark harness with independent judge is new. |
| G10 | Dynamic Agent Factory and team optimization | #4 | NL-BP-066, NL-BP-067, NL-BP-070, NL-BP-053 | none (covered) | Already covered by planned NL-BP-066/067 plus scheduler/collision requirements; no new ID. |
| G11 | Studio IDE, attachments/chat, voice and Model Hub completion + visual/computer-use/multi-window | #5 | NL-BP-020, NL-BP-021, NL-BP-022, NL-BP-023, NL-BP-024, NL-BP-025, NL-BP-026, NL-BP-027, NL-BP-028, NL-BP-029, NL-BP-030, NL-BP-031, NL-BP-032, NL-BP-033, NL-BP-034, NL-BP-035, NL-BP-036, NL-BP-037, NL-BP-038, NL-BP-039, NL-BP-040, NL-BP-041, NL-BP-042, NL-BP-043, NL-BP-044, NL-BP-045, NL-BP-046 | NL-BP-190, NL-BP-191, NL-BP-192, NL-BP-193, NL-BP-194 | Existing Studio requirements remain the completion baseline; visual QA, computer use, multi-window, advanced IDE gaps and OCR are new. |
| G12 | Independent review, differential testing and quality gates | #4 | NL-BP-054, NL-BP-055, NL-BP-056, NL-BP-057, NL-BP-058, NL-BP-059, NL-BP-060, NL-BP-065, NL-BP-146, NL-BP-147 | none (covered) | Fully covered by existing staged-candidate/oracle/repair requirements; no new ID and no gate relaxation. |
| G13 | Build/Test Laboratory and Dependency/Supply Chain Lab | #6 | NL-BP-140, NL-BP-122, NL-BP-119, NL-BP-121, NL-BP-162 | NL-BP-184, NL-BP-185 | Acceptance/reproducibility/SBOM pieces exist; laboratory-level build and supply-chain automation is new. |
| G14 | Source control/collaboration, plugin SDK, task automation | #6 | NL-BP-039, NL-BP-073, NL-BP-075 | NL-BP-186, NL-BP-187, NL-BP-188 | Local Git tools/tool registry/diagnostics exist; remote collaboration, plugin SDK and task automation are new. |
| G15 | Mega Suite modular installer with shared cache and storage plan | #7 | NL-BP-116, NL-BP-124, NL-BP-110, NL-BP-152, NL-BP-153, NL-BP-154, NL-BP-155, NL-BP-156, NL-BP-157, NL-BP-158 | NL-BP-195 | Portable/beta distribution work exists; Mega-Suite modular selection and storage plan are new. |
| G16 | Self-update with atomic deploy, manifests and previous-app fallback | #7 | NL-BP-117, NL-BP-122 | NL-BP-196 | Repair/update baseline exists; atomic deployment/fallback/migration safety is new. |
| G17 | Source-vs-binary release separation and public-repository readiness | #7 | NL-BP-162, NL-BP-163, NL-BP-140 | NL-BP-197 | Pre-upload audit/owner gates exist; explicit source/binary separation is new. |
| G18 | Multi-platform bootstrapper, GitHub CI and real-hardware beta | #7-8 | NL-BP-110, NL-BP-111, NL-BP-112, NL-BP-113, NL-BP-114, NL-BP-115, NL-BP-116, NL-BP-117, NL-BP-118, NL-BP-119, NL-BP-120, NL-BP-121, NL-BP-122, NL-BP-123, NL-BP-124, NL-BP-140, NL-BP-141, NL-BP-142, NL-BP-144, NL-BP-145, NL-BP-146, NL-BP-147, NL-BP-148, NL-BP-149, NL-BP-150, NL-BP-151, NL-BP-152, NL-BP-153, NL-BP-154, NL-BP-155, NL-BP-156, NL-BP-157, NL-BP-158, NL-BP-159, NL-BP-160, NL-BP-161, NL-BP-162, NL-BP-163, NL-BP-164, NL-BP-165 | none (covered) | Already covered by stage-6 distribution/release and cross-platform beta requirements; no new ID. |
| G19 | Operating metrics and readiness taxonomy | #8 | NL-BP-075, NL-BP-140, NL-BP-151, NL-BP-164 | NL-BP-189, NL-BP-198 | Diagnostics dashboard/status vocabulary exist; user-visible metrics and enforced readiness labels are new. |
| G20 | End-to-end cross-app / Full Autonomy / Mega Suite / research / genome acceptance scenarios | #8 | NL-BP-140, NL-BP-164, NL-BP-165, NL-BP-063 | NL-BP-199, NL-BP-200, NL-BP-201, NL-BP-203, NL-BP-204 | Individual acceptance tooling exists; the addendum's program-level scenarios are new. |

Program mapping: all 39 new requirements are **program stage 7** (Universal autonomy, research intelligence and Mega Suite), status planned, pending after stage 6. The addendum grants no deletion/publication/cloud authorization; SH-07 Tier B remains blocked.

## Web-research directive v3.8 - capability audit and dedupe mapping

Read-only audit: docs/WEB_RESEARCH_CAPABILITY_AUDIT.md (file:line evidence). Source: user directive 2026-10-28: Universal Web Research & Intelligence Engine. Queue-only: no implementation, no code/model/network run.

| Sub-capability | Existing coverage | New requirements | Decision |
|---|---|---|---|
| multi-provider search router | NL-BP-169 | NL-BP-205 | 169 owns the router; 205 adds provider registry/capability matrix/no-key modes/routing policy |
| provider capability matrix, availability/no-key/public modes | - | NL-BP-205 | new |
| explicit provider selection + intelligent routing | NL-BP-169 | NL-BP-205 | 169 owns query routing; 205 owns explicit policy/selection |
| cost/privacy/rate policy and no silent paid use | NL-BP-168, NL-BP-072 | NL-BP-205 | 205 implements provider policy; permission scopes stay in 168/072 |
| web page/document reader and JS browser | NL-BP-170 | none (covered) | covered |
| domain allow/deny, redirect/SSRF/private-IP, rate/download caps, caching provenance | NL-BP-175 | NL-BP-206 | 175 trust boundary; 206 retrieval enforcement |
| GitHub repository investigator | NL-BP-171 | none (covered) | covered |
| Hugging Face model investigator | NL-BP-172 | none (covered) | covered |
| Hugging Face acquisition/license/download/cache workflow | NL-BP-008, NL-BP-124, NL-BP-183 | NL-BP-208 | new acquisition workflow; reuses model/competence/cache requirements |
| ecosystem/package documentation discovery | NL-BP-173 | none (covered) | covered |
| version-aware official docs/changelogs/migration guides | NL-BP-173 | NL-BP-209 | new version-awareness/conflict handling |
| research knowledge store/citations/embeddings | NL-BP-174 | none (covered) | covered |
| prompt-injection/untrusted-source handling | NL-BP-175 | NL-BP-206 | 206 adds retrieval-side enforcement |
| research-aware agent planning/update checks | NL-BP-176 | none (covered) | covered |
| research connectors in tool registry/MCP with typed read-only permissions | NL-BP-042, NL-BP-073 | NL-BP-207 | new connector registration/permission separation |
| Studio research workspace/search history/previews/saved findings | - | NL-BP-210 | new GUI; local attachment intake stays in NL-BP-026..030 |
| pasted URLs/repo/model links/attachments research intake | NL-BP-026, NL-BP-027, NL-BP-028, NL-BP-029, NL-BP-030 | NL-BP-210 | new intake extension for research references |
| research acceptance fixture-vs-real-network matrix | NL-BP-203 | NL-BP-211 | 203 scenario; 211 full failure/exception matrix |
| real-network research verification | NL-BP-203 | NL-BP-211 | covered/enforced by 211 |

New requirements are program stage 7, status planned. Blocked/external items preserved:
- no search-provider credentials/API keys configured; no-key/public/offline modes must work before paid providers
- network access is denied by default (core/permissions.py) and must be explicitly granted
- SSRF/domain/rate/download safety (NL-BP-206) must exist before any real web fetch is enabled
- Hugging Face gated/licensed models need explicit owner approval before acquisition
- real-network research acceptance is permissioned/manual (NL-BP-203/211) and cannot be claimed from fixtures
- MCP is local stdio-only and no GitHub/HF/web MCP server is bundled; remote MCP transports are unsupported
- stage 7 is pending; SH-07 Tier B (NL-BP-063) remains blocked

## Goal-mode directive v4.2 - capability audit and dedupe mapping

Read-only audit: docs/GOAL_MODE_CAPABILITY_AUDIT.md (file:line evidence). Source: user directives 2026-10-28: Universal Goal Mode + Document-Driven Goal Bootstrap & Planning. Queue-only: no implementation, no code/model/network/mission run.

| Sub-capability | Existing coverage | New requirements | Decision |
|---|---|---|---|
| Persistent goal/milestone hierarchy + CRUD | NL-BP-050 | NL-BP-212 | 050 remains the conceptual record; 212 supplies executable goal tables/API/lifecycle |
| Goal creation from NL + attachments/repos/references/acceptance criteria | NL-BP-026, NL-BP-027, NL-BP-028, NL-BP-029, NL-BP-030, NL-BP-077 | NL-BP-212 | goal entity + intake mapping is new; local attachments reused |
| Multi-goal priorities/dependencies/pause/resume/cancel | NL-BP-051, NL-BP-061, NL-BP-064 | NL-BP-212 | new goal lifecycle; mission persistence/lock/policy reused |
| Adaptive goal decomposition + versioned replanning | NL-BP-062, NL-BP-050, NL-BP-178 | NL-BP-213 | new decomposition/replan engine; genome planned |
| Goal continuation scheduler across goals | NL-BP-061, NL-BP-062, NL-BP-064, NL-BP-070 | NL-BP-214 | cross-goal scheduling is new; queue/lease reused |
| Independent goal completion verification / false-completion detection | NL-BP-054, NL-BP-058, NL-BP-060, NL-BP-203 | NL-BP-215 | goal-level verifier new; verified gate foundations reused |
| Goals GUI + CLI/API parity | NL-BP-046, NL-BP-025, NL-BP-023, NL-BP-024 | NL-BP-216 | new Goals surface; existing dashboard/task board extended |
| Reusable goal templates across projects/Mega Suite | - | NL-BP-217 | GOAL_TEMPLATE advisory only; new system |
| Document corpus discovery/ingestion with provenance | NL-BP-077, NL-BP-043, NL-BP-030, NL-BP-170, NL-BP-171 | NL-BP-218 | new corpus pipeline; local extraction/project scan/research readers reused |
| Documentation reconciliation | NL-BP-178, NL-BP-174 | NL-BP-219 | new reconciliation engine; genome/research store adjacent |
| Requirement/objective/constraint/dependency/acceptance extraction | NL-BP-050, NL-BP-178 | NL-BP-220 | new extraction with provenance |
| Editable plan preview/approve + supervised auto-execution + versions | NL-BP-213, NL-BP-064, NL-BP-166, NL-BP-024 | NL-BP-221 | new plan surface; autonomy policy reused |
| Incremental doc-change/new-evidence reconciliation | NL-BP-219, NL-BP-174, NL-BP-214, NL-BP-215 | NL-BP-222 | new incremental reconciliation |
| Document-driven goal acceptance scenario | NL-BP-203, NL-BP-199, NL-BP-200, NL-BP-201 | NL-BP-223 | new end-to-end stage-8 acceptance |

New requirements are program stage 8, status planned. Blocked/external items preserved:
- stage 8 is pending; depends_on_stages [3, 7] and stage 7 is itself pending/partially implemented
- existing NL-BP-050 stays partial and is not rewritten; reconciliation needs an authorized evidence update
- document-driven auto-execution requires autonomy policy/approval (NL-BP-064/166..168); corpus content is untrusted and never executed
- independent goal verification cannot rely on model consensus; SH-07 Tier B (NL-BP-063) remains blocked
- unbounded folder ingestion is not authorized; corpus discovery is consent-based and bounded
- docs-only projects require honest document-consistency evidence, never fabricated test results
- goal templates depend on the planned Mega Suite path (NL-BP-195)

## Open-model directive v4.3 - capability audit and dedupe mapping

Read-only audit: docs/OPEN_MODEL_ECOSYSTEM_AUDIT.md (file:line evidence). Source: user directive 2026-10-28: Open Model & Provider Ecosystem (presets as conveniences not restrictions). Queue-only: no implementation, no code/model/network/mission run.

| Sub-capability | Existing coverage | New requirements | Decision |
|---|---|---|---|
| Multi-provider discovery/health/loaded/unload | NL-BP-008 | none (covered) | verified foundation NL-BP-008 retained |
| Built-in presets with editable defaults | - | NL-BP-224 | hand-edited YAML presets only today; first-class editable presets are new |
| Custom provider profiles (URL/model/auth/headers/protocol/secret refs/import-export) | NL-BP-008, NL-BP-010 | NL-BP-225 | fixed YAML schema; new profile store |
| Auto discovery + always-available manual entry | NL-BP-008 | NL-BP-226 | auto discovery exists; manual entry/fallback is new |
| Extensible protocol adapters, no closed provider list | NL-BP-008 | NL-BP-227 | closed kind branch; adapter registry is new |
| Automatic parameter suggestions + expert/backend-specific params | NL-BP-010, NL-BP-068 | NL-BP-228 | temperature-only today; suggestions/additional params new |
| Per-model/per-role profiles + project bindings + switch-preserving overrides | NL-BP-010, NL-BP-011, NL-BP-068 | NL-BP-229 | YAML roles only; persistent profiles/bindings new |
| Capability states declared/detected/tested/unknown + optional benchmarks, warnings not rejection | NL-BP-009, NL-BP-069, NL-BP-183 | NL-BP-230 | evidence registry exists; presentation/policy layer new; lab retained |
| Flexible local/external/embedding/multimodal routing with explanations/override/policy | NL-BP-010, NL-BP-070, NL-BP-168 | NL-BP-231 | router module unwired; live routing surface new |
| Model Hub GUI/CLI/API provider+profile management | NL-BP-036 | NL-BP-232 | read-only UI today; management surface new |
| Model lifecycle load/unload/storage UI | NL-BP-036 | none (covered) | retained; 232 adds management, no duplicate |
| Competence benchmarks/hardware profiling | NL-BP-069, NL-BP-183 | none (covered) | retained; 230 may consume |
| Permission/cloud-spending enforcement | NL-BP-168, NL-BP-072 | none (covered) | retained; 231 enforces existing policy |
| Open-provider acceptance scenario | - | NL-BP-233 | new end-to-end acceptance |

New requirements are program stage 9, status planned. Blocked/external items preserved:
- stage 9 is pending; depends_on_stages [4, 7] and stage 7 is itself pending/partially implemented
- ModelRouter is tested but not instantiated in product code; live wiring (231) must not weaken permission/cloud gates
- provided presets must not become an approved-provider/architecture/quantization allow-list
- manual provider entry must remain available but cannot bypass permission or cloud-spending policy
- unknown/declared capability combinations warn for experimental use; hard refusals only where task/policy requires measured capability
- real-endpoint acceptance (233) is permissioned/manual and distinct from fixture evidence
- HF acquisition (208) and competence benchmarks (069/183) remain separate planned requirements; no downloads in this directive

## Release-publication directive v4.4 - capability audit and dedupe mapping

Read-only audit: docs/RELEASE_PUBLICATION_GATE_AUDIT.md (file:line evidence). Source: user directive 2026-10-28: Final Release Hygiene & GitHub Publication Gate + mandatory pre-push secrets/content scan. Queue-only: no implementation, no code/model/network/push/publish run.

| Sub-capability | Existing coverage | New requirements | Decision |
|---|---|---|---|
| Repository hygiene/distribution read-only audits | NL-BP-090, NL-BP-091, NL-BP-092, NL-BP-093, NL-BP-094, NL-BP-095, NL-BP-096, NL-BP-097 | none (covered) | verified/partial per-domain audits retained; 234 integrates them |
| Final integrated readiness milestone + BEFORE/AFTER + exact move/delete/consolidation report + disk/Git-history analysis + security/licensing + regression/packaging + verdict | - | NL-BP-234 | genuinely new program-level deliverable |
| Duplicate runtimes/models/assets/dependencies and build/cache/logs/dev data consolidation | NL-BP-096, NL-BP-094, NL-BP-097, NL-BP-121, NL-BP-122, NL-BP-124 | NL-BP-234 | subtasks covered; integrated analysis/refactor is new |
| Distribution allowlist/package/launchers/installer and clean builds | NL-BP-110, NL-BP-111, NL-BP-112, NL-BP-113, NL-BP-114, NL-BP-115, NL-BP-116, NL-BP-117, NL-BP-118, NL-BP-119, NL-BP-120, NL-BP-121, NL-BP-122, NL-BP-123, NL-BP-124, NL-BP-149, NL-BP-195, NL-BP-196, NL-BP-197 | NL-BP-234 | requirements retained; final readiness integration new |
| Protected assets / no deletion without authorization | NL-BP-092, NL-BP-093, NL-BP-094, NL-BP-163 | none (covered) | policy retained; 234 must respect it |
| Pre-push secrets/content scanner (tracked+history, redacted, exit-code) | NL-BP-162 | none (covered) | verified scanner retained |
| Mandatory blocking pre-push gate with Git hook/CI/staged scan/fail-closed/no-push | - | NL-BP-235 | genuinely new enforcement layer |
| Owner authorization gates (push/visibility/upload/history/collaborators) | NL-BP-163 | none (covered) | retained; 236 records sign-off |
| Release acceptance matrix and readiness labels | NL-BP-140, NL-BP-198 | NL-BP-236 | matrix retained; explicit verdict artifact new |
| Real hardware/clean-machine/real-network/CI/beta external acceptance | NL-BP-152, NL-BP-153, NL-BP-154, NL-BP-155, NL-BP-156, NL-BP-157, NL-BP-158, NL-BP-159, NL-BP-160, NL-BP-161, NL-BP-164, NL-BP-165 | NL-BP-236 | stays MANUAL-PENDING and blocks ready verdict; no duplicate |
| Source-vs-binary release separation and public repository readiness | NL-BP-197, NL-BP-198 | NL-BP-234, NL-BP-236 | consumed by final milestone/verdict; retained |
| Readiness taxonomy enforcement | NL-BP-198 | NL-BP-236 | 198 retained; 236 verdict references it |
| Owner residual-risk sign-off | - | NL-BP-236 | new recorded artifact |

New requirements are program stage 10, status planned. Blocked/external items preserved:
- stage 10 is pending; depends_on_stages [6,7,8,9] and several of those stages are in progress/pending
- publication/push/visibility/collaborator upload remain FORBIDDEN without explicit owner authorization (NL-BP-163; PRIVATE_BETA_RUNBOOK G-1..G-10); repository has no configured remote
- real external acceptance (real hardware, clean machines, actual GitHub CI runs, non-Windows builds, beta tester records) remains MANUAL-PENDING and blocks any publication-ready verdict (NL-BP-236)
- committed docs/SECRETS_AUDIT.md snapshot was measured at an earlier HEAD and must be re-run at the release HEAD; the bounded heuristic scanner cannot prove absence of custom/obfuscated secrets, LFS/submodules or deep history
- no deletion of user data, live SQLite, python/ runtime, data/, da_eliminare/crewAI, models, evidence, backups or stale release candidates without owner authorization
- SH-07 Tier B (NL-BP-063) stays BLOCKED and blocks a final readiness verdict
- code removal only after dependency analysis and regression, inside a separately authorized scope
- no git-history rewrite without verified backup and explicit owner authorization; leaked secrets in history are presumed compromised and require rotation
- local static CI checks are not actual GitHub CI execution evidence; real CI runs remain pending (NL-BP-165)

## Studio final-UX directive v5.2 - capability audit and dedupe mapping

Read-only audit: docs/STUDIO_FINAL_UX_AUDIT.md (file:line evidence). Source: user directive 2026-10-29: final Studio GUI UX acceptance (i18n, visual polish, self-build placement, Inspector/state clarity, real-GUI evidence). Queue-only: no implementation, no code/GUI/model/network run.

| Sub-capability | Existing coverage | New requirements | Decision |
|---|---|---|---|
| Branding, logo, tokens, dark theme shell | NL-BP-020 | none (covered) | verified NL-BP-020 retained |
| Navigation/panels/inspector/log/status bar | NL-BP-021 | NL-BP-238, NL-BP-240 | 021 retained; final IA/Inspector extend it |
| Settings surfaces | NL-BP-022 | NL-BP-237, NL-BP-239 | 022 retained; language setting and advanced activation extend it |
| Self-build controls under Settings > Advanced | NL-BP-023 | NL-BP-239 | 023 retained; placement/runtime acceptance extends it |
| Emergency pause/stop always reachable | NL-BP-024 | none (covered) | 024 retained and reused by 239 |
| Accessibility/focus/DPI/shortcuts | NL-BP-044 | NL-BP-238, NL-BP-241 | 044 retained; visual/real-GUI evidence extend it |
| Non-blocking responsive UI and explicit states | NL-BP-045 | NL-BP-238, NL-BP-240 | 045 retained |
| Project dashboard/agent-task visualization | NL-BP-046 | NL-BP-240 | 046 retained; state clarity extends it |
| Visual quality lab / screenshot baselines | NL-BP-190 | NL-BP-241 | 190 retained; real-GUI evidence extends it |
| Goals/Tasks progress surfaces | NL-BP-216, NL-BP-046 | none (covered) | retained and reused by 239 |
| UI internationalization/localization | - | NL-BP-237 | genuinely new |
| Visual design/IA polish with reusable components | - | NL-BP-238 | genuinely new acceptance layer |
| Self-build placement/runtime UX acceptance | - | NL-BP-239 | genuinely new acceptance over 023/024 |
| Inspector structured summaries + project/activity state clarity | - | NL-BP-240 | genuinely new |
| Real-GUI screenshot/interaction evidence | - | NL-BP-241 | genuinely new acceptance over 044/190 |
| Notification centre/toasts | - | none (covered) | folded into 238/240 status reporting; no separate requirement |

New requirements are appended to existing program stage 4, status planned. Blocked/external items preserved:
- no new stage/framework: final Studio UX remains stage-4 work and is queued only
- Italian-default localization needs a real translation catalog and QA pass; machine translation alone is not acceptance
- real-GUI screenshots/interaction evidence at multiple sizes/DPI is manual/hardware-dependent and cannot be inferred from offscreen tests
- removing the Projects Self-Build button requires the Settings > Advanced activation path and non-prominent self-repo open path to be accepted first (NL-BP-023/024)
- Inspector redesign must keep evidence/errors reachable via expandable diagnostics
- theme/design cleanup must preserve the verified NL identity/tokens and no-glow rule
- existing requirement statuses (020 verified; 021/022/023/024/044/045/046 partial; 190 planned) are unchanged; stage-4 reopen is a program-level honesty correction

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


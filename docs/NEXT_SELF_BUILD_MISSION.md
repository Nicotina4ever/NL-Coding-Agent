# Development continuation — Goal execution integration

Latest verified increment (2026-10-29): the shared engine MCP bridge and official-SDK
client are implemented; see CURRENT_STATE.md and README commands. Real REA introspection
and real Ollama MCP mission #49 were exercised. #49 was review-rejected despite passing
candidate/oracle tests: preserve that evidence, do not mark it complete. Code - OSS was
actually inspected at a pinned revision; EXTERNAL_SOURCE_REFERENCES.md records the
comparison and dependencies. No editor replacement, clone or external configuration
installation is necessary. Remaining natural-language capability routing, automatic
MCP use and broader external-client acceptance are limitations, not a new roadmap.
This checkpoint ends the current increment; no further large development run is started.
Follow-up: #49 exposed missing original-objective context in the reviewer prompt;
after repairing it, real MCP mission #50 passed review, verification and promotion.
The independent reviewer also reran its promoted-project tests. Retained evidence now
keeps candidate diffs for future terminal stages; older records missing a full diff
report that limitation explicitly. Details and exact test evidence are in CURRENT_STATE.

Studio checkpoint: the 2026-10-29 dock workspace and native VoiceBridge acceptance
are recorded at the top of CURRENT_STATE.md. The GUI arithmetic mission was rejected
by its reviewer despite passing tests; preserve that evidence and do not mark it
successful. The owner's subsequent platform request prioritizes the conversational
engine path, existing MCP client interoperability, and an engine bridge for external
clients. Reuse AppServices/Supervisor and the existing mission state; do not rebuild
the already-integrated workspace or start another roadmap.

Latest checkpoint (2026-10-29 independent review): the approved-plan bootstrap below
has been integrated and its approval/project binding/atomicity repaired and tested.
Do not repeat it or infer completion from the older checklist. CURRENT_STATE.md's
independent-review section records current evidence and limitations, including the
native GUI and real local-model delegation acceptance. The review run ends here;
no subsequent development mission was started automatically. Runtime custom-agent
configuration, cohesive workspace and contextual Chat remain incomplete product work.
The historical continuation text below is retained for context, not current status.

2026-10-29: Continue the existing indexed program. NL-BP-214 remains partial.

Implemented: approved active Goal milestones execute through the existing Supervisor
(`supervisor run --project <folder> --work-source goals`), with proof-backed dependency
continuation, atomic links, priorities, policy rechecks and crash recovery. Execution
is opt-in; approving plans/previews never starts a model. Goals do not auto-complete.

Validation: targeted Goal/Supervisor/CrewAI regressions and one real local-model mission;
see CURRENT_STATE.md and `.workspace/temp/goal-execution-live-20261029-retry/result.json`.
The arithmetic project is synthetic; inference, candidate/oracle tests and promotion
are real. It is not unfamiliar-project acceptance.

Next dependency-ready integration: approved document-plan provenance into an explicit
Goal bootstrap through existing services, then execution preview/start in the established
Studio controls. Preserve version approval and original-objective verification. Imported
text must not authorize source edits. Broad cross-project continuation, adaptive replanning
and final NL-BP-214/223 acceptance remain unproven; no stage/product completion claim.

Parallel work: the owner confirmed another agent is changing the document-plan GUI,
related docs/locales and smoke tests. Preserve those changes; this commit stages only
its own code and documentation hunks. Reconcile parallel GUI work before claiming a
clean GUI regression. Restart the application before exercising changed services.

Integration validation (2026-10-29): 179 targeted regression tests passed; the final
Goal/Supervisor core/CLI group passed 70 tests after interface/restart corrections.
Full suite: 1,166 passed / 10 failed. Seven failures result from the parallel removal
of the tracked DocumentPlanDialog (one Chat test and six packaging/rehearsal tests);
three reproduce pre-existing Problems-panel expectations and Windows POSIX-shell
WinError 1920. No fully green regression or release-readiness claim. Evidence:
`.workspace/temp/goal-execution-full-regression.txt`,
`.workspace/temp/goal-execution-interface-final-2.txt`.
Gatekeeper review approved the diff and inspected real-model evidence directly.

Final storage isolation hardening: candidate/oracle subprocesses receive separate
NL_WORKSPACE_DIR and CREWAI_STORAGE_DIR beneath their suite data directory. Parent
state remains unchanged. Targeted verification/backend/Goal batch: 42 passed;
final candidate verification batch (including real state-isolation subprocesses):
11 passed. Gatekeeper approved this additional isolation diff.
## Objective

Bring approved document-plan provenance into an explicit Goal bootstrap through existing services, then execution preview/start in the established Studio controls.

## Scope of Work

- `nl_coding_agent/core/doc_planning.py`
- `nl_coding_agent/core/goals.py`
- `nl_coding_agent/core/autonomous_roadmap_planner.py`
- `tests/test_rollback_stub.py`
- `tests/test_scope_permission.py`
- `nl_coding_agent/core/autonomous_roadmap_planner.py`

## Acceptance Gates

- [ ] Approved-plan provenance is available for explicit Goal bootstrap
- [ ] Goal execution preview and start reuse existing Studio controls
- [ ] Existing version approval and original-objective verification are preserved
- [ ] Imported text cannot authorize source edits

## Execution via NL Coding Agent CLI

`nl-coding-agent doctor` and targeted tests.

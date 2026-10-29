> 2026-10-29: The mission #47 incident correction is closed with targeted tests
> and gatekeeper review (details in CURRENT_STATE.md). Restart the GUI before
> exercising the corrected Chat routing. No subsequent self-build mission was
> started or authorized by this correction; the historical mission below is not
> an instruction to continue automatically.

# Next Self-Build Mission: Supervisor Persistente

**Goal:** Document that the autonomous supervisor can open arbitrary folders, discover language/framework/README, and persist Recent Projects without per-project YAML — verifying P1-01 from the Blueprint using existing code and evidence.

**Source:** docs/product-blueprint/03_MASTER_CHECKLIST.md (P1-01), SPEC-12

## Scope of Work
- docs/CURRENT_STATE.md
- docs/COMPLETED_MISSIONS.md
- nl_coding_agent/core/autonomous_roadmap_planner.py (read-only import verification)
- tests/test_rollback_stub.py
- tests/test_scope_permission.py

## Acceptance gates
- [ ] Project scanner (`nl_coding_agent/projects/registry.py`) runs without error on workspace.
- [ ] `docs/CURRENT_STATE.md` updated with verified discovery evidence.
- [ ] No manual feature code by OpenCode; no source/test modifications outside scope.
- [ ] Full suite 72 passes; rollback/permission tests unchanged.
- [ ] Verified by autonomous Developer -> Tester -> Reviewer using local model.

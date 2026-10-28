---
name: nl-self-build-cycle
description: Gestisce il ciclo di auto-sviluppo di NL Coding Agent, dalla modifica del codice fino ai test, alla revisione e alla ripresa delle missioni.
---

# NL Self-Build Cycle

Use this procedure when NL Coding Agent is modifying itself.

1. Establish current acceptance-test baseline.
2. Inspect Git status; preserve unrelated user changes.
3. Define one coherent vertical improvement with file/write scope.
4. Implement through normal application architecture boundaries.
5. Run focused tests.
6. Run broader regression tests.
7. Ask the review/gatekeeper agent to inspect diff + results.
8. If rejected, return specific blockers to the implementing agent.
9. If approved, update `docs/CURRENT_STATE.md`.
10. Write/update `docs/NEXT_SELF_BUILD_MISSION.md`.
11. If the running application must reload changed modules, mark restart required rather than
    performing unsafe hot replacement.

Never call work "complete" when only code generation occurred.

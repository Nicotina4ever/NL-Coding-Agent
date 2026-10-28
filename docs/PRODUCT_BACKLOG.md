# Product Backlog
Consolidated from `docs/product-blueprint/03_MASTER_CHECKLIST.md`. No duplicates.
## P0 - High Priority
- P0-01 Audit repo / Git state (SPEC-02, SPEC-15)
- P0-07 SQLite persistence (SPEC-18)
- P0-09 Real self-build (SPEC-19)
- P0-11 Docs state / resume (SPEC-02)
- P0-13 Recovery points (SPEC-02A)
## P1 - Medium Priority
- P1-01 Open arbitrary folder / scanner (SPEC-12)
- P1-02 Goal > milestone > task > mission (SPEC-03)
- P1-04 Model Hub (SPEC-05)
- P1-07 Stable Qt GUI (SPEC-08)
## P2 - Low Priority
- P2-01 Agent factory (SPEC-04)
- P2-02 Adaptive inference + Optimize My Team (SPEC-06)
- P2-05 Resource scheduler (SPEC-13)
- P2-14 Recovery storage manager (SPEC-02A, SPEC-14)
## Constraints
- Local-model-first; Ollama primary; cloud opt-in.
- No automatic migration/cleanup/sibling dirs/packaging until verified.
- Preserve `python/`, `crewAI/`, `crewAI-tools/`, `.git`; use embedded `python\python.exe`.
# Prompt breve di importazione e ripresa (da passare a OpenCode o NL Coding Agent)

> **Non inviare tutte le specifiche in chat come nuovi prompt.** Importare la cartella documentale una sola volta; poi dare soltanto la consegna sintetica seguente.

```text
Read docs/product-blueprint/README_IMPORTANTE.md, 00_MASTER_INDEX.md,
01_DECISIONI_E_PRIORITA.md and 02_STATO_REALE_DA_VERIFICARE.md.

This documentation is the consolidated PRODUCT BACKLOG, not an instruction
for immediate parallel implementation. Preserve repository code, existing
TODOs, Git changes, SQLite and prior working features.

ONE ACTIVE GOAL: independently verify and stabilize the local Ollama-driven
self-build handoff (real source edits, diff, automated tests, reviewer decision,
SQLite evidence, interruption/restart recovery). Inspect actual code and tests;
never mark reported progress as verified without evidence.

Reconcile existing TODOs against 03_MASTER_CHECKLIST.md. Store deduplicated
future goals in the existing persistent backlog; do not execute them now.
Keep exactly the next actionable task active and update durable state at
meaningful checkpoints. Observed test results outweigh agent opinions.

CRITICAL: the repository root is now K:\AI\NL Coding Agent (relocation
completed and verified 2026-10-28). Do NOT move, copy or migrate it again
without a new explicit user authorization after all processes stop. Do NOT
create external sibling build directories.

Self-development controls belong under Settings > Advanced, NOT as a
prominent home-screen call to action. Keep mission status and emergency stop
visible when relevant.

Packaging decision: lightweight native platform-specific bootstrapper and
app-local verified runtime bundles; no uv or global package-manager
requirements; models/ASR are optional. Packaging implementation is future
backlog, NOT the current task.

Implement, execute and verify only the current priority. Stop on genuine
blockers or permissions; record exact resume commands and evidence.
```

## Dopo la verifica P0

Proporre una **sola prossima milestone** dal backlog, valutando dipendenze/valore, poi permettere al Self-Build Mode di eseguirla con gli stessi gate. Evitare espansione incontrollata del Goal.

## Nota V4 (solo quando il self-build corrente è concluso e verificato)

Successivamente attivare come unica missione il **Supervisor persistente** (SPEC-21): dimostrare che NL Coding Agent seleziona da sé la *missione successiva* senza ChatGPT/OpenCode e che si riprende a processo riavviato. Il Competence Index e la pulizia fisica delle build esterne restano backlog, a meno di nuova scelta esplicita. Per un eventuale audit del disco usare il runbook, senza side effect.

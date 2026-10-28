# SPEC-03 — Goals, milestones, tasks/TODOs, missions

**Goal** = obiettivo strategico durevole con motivazione, contesto, vincoli, priorità, owner e criteri d'accettazione. **Milestone** = risultato intermedio dimostrabile; **Task/TODO** = lavoro operativo verificabile, con dipendenze; **Mission** = tentativo esecutivo con ruoli, modelli, tool call, diff, test, review, log, tempi e stato. Una mission può fallire e il task restare aperto.

Stati esempio: Goal `PROPOSED/ACTIVE/ON_HOLD/BLOCKED/VERIFIED/ABANDONED`; Task `BACKLOG/READY/RUNNING/VERIFYING/REVIEW/BLOCKED/DONE/FAILED/CANCELLED`; Mission `CREATED/ACTIVE/INTERRUPTED/RECOVERING/COMPLETED/FAILED`. L'implementazione può adattarli, con migrazioni, senza valori rigidi.

Requisiti: CRUD reale, persistenza SQLite, deduplica semantica guidata, project association, tag, subgoal, dependency DAG, ownership, criteri osservabili, URL/path delle evidenze; importare checklist Markdown senza spuntare automaticamente. Gli agenti possono proporre Goal/task nuovi ma non espandere scope in maniera ricorsiva senza rationale/limiti. Obiettivi utente distinguibili da proposte.

UI: sezione **Goals** dedicata (strategia/roadmap), **Tasks** con board e filtri, **Missions** con cronologia/telemetria. Mostrare `verified %` solo come rapporto derivato da gate, non da TODO spuntati arbitrariamente. Eseguire un task attivo per team in modalità sicura iniziale, con autonomia per lavoro parallelo indipendente.

Goal iniziale persistente: “Portare NL Coding Agent a uno Studio autonomo, multimodale, multiprovider e distribuibile” ma **soltanto la milestone Self-Build HandOff è immediatamente attiva**. Restanti milestone nel backlog. L'utente può cambiare priorità/obiettivi.

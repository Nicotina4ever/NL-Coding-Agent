# Architettura operativa, CrewAI + Flows

## Unico motore e confini

```text
NL Code standalone (Code - OSS workbench)     NL Coder VSIX
           \                                    /
            \------- frontend / MCP ----------/
                            |
                  AppServices / Supervisor
                   /       |          \
                Flow   Planner/Tasks    ModelRouter/ResourceManager
                  |       |                  |
                 CrewAI (ruoli, modelli, tool, handoff)
                            |
        policy → staged candidate → candidate+oracle → reviewer
                            |
                       CAS promotion
                            |
            SQLite / handoff / checkpoint / diff / recovery
```

L'illustrazione descrive la direzione e i componenti già presenti, non attesta che ogni arco abbia superato i gate end-to-end.

**Regola:** nessun secondo Supervisor, orchestratore, router, parser missione o DB per la UI. Le modalità sequenziale e Flow condividono gli stessi helper operativi e le stesse autorizzazioni.

## Stato implementato al checkpoint `1655cbb` (report, da confermare)

- `start_mission → AppServices.run_mission → Supervisor.execute_mission → MultiAgentOrchestrator`; ticket, lease, heartbeat, checkpoint, lock writer, stop/resume.
- `CrewAIBackend` esegue `Agent + Task + Crew(process=sequential)` per **singolo ruolo LLM**; tester e promozione sono deterministici. Un Crew per ruolo NON equivale a team multi-agente CrewAI che collabora internamente. È lecito orchestrare Crew specializzati dal Supervisor.
- `MissionFlow` con `@start`, `@router` e `@listen`: `develop → verify` con `repair → verify` se check fallisce, `review → promote → finish`; Chat/MCP impostati sul Flow di default; sequential disponibile come fallback.
- `_plan_tasks` crea più task developer a catena quando dichiara 2–4 file sorgente; test update separato; `_run_developer_tasks` usa lo stesso candidate e conserva handoff su resume. Questa è una base multi-task, **non** un task graph dinamico generalizzato.
- Architect/auditor in sola lettura quando scelti dalla policy; planner role catalogato ma non ancora vero piano adattivo aperto.
- `task_attempts`, `handoffs`, `verification_runs`, `mission_model_snapshots` contengono evidenze/stati; source of truth SQLite.

## Contratto per specialisti verticali

Ogni ruolo ha obiettivo, competenze, policy/strumenti, modello e parametri, input rilevante, criteri di verifica, limiti e output tipizzato. Non fissare un numero di ruoli. Il Supervisor seleziona specialisti in base a scansione del progetto e dipendenze, non soltanto regex/numero file. Più task per ruolo e deleghe condizionate sono requisiti 1.0.

**Handoff minimo**: `mission_id`, `task_id`, `from_role`, `to_role`, `scope`, `objective`, `facts`, `decisions`, `artifacts/diff`, `paths`, `test_results`, `open_issues`, `next_steps`, `model/provider/usage`, `timestamp/version`. Persistire e **consumare** sul task successivo; non limitarsi a scrivere log decorativi. Il reviewer riceve contratto, diff, test ed evidenze e deve poter rifiutare.

## Lifecycle missione / qualità

1. Analisi/read-only del repository e baseline Git, pianificazione e policy verificata.
2. Staged candidate per una o più attività, tool file autorizzati, handoff.
3. Test candidate su candidato + oracle con test baseline fissati, output persistito.
4. Su fallimento: Flow attiva debugger, classificazione errore, tentativi con budget, re-verify. Loop ripetitivi identici devono fermarsi, non bruciare notte e token.
5. Review indipendente APPROVE/REJECT, CAS promotion/recovery journal e verifica file live.
6. Stato completato soltanto dopo criteri e promozione; stop/resume e checkpoint idempotenti.

## Test ancora necessari

- Eseguire ramo repair **con test reale che fallisce** e dimostrare la riparazione, non solo FakeExecutor.
- Un progetto con moduli dipendenti, più developer tasks e handoff consumati, con ripresa intermedia.
- Dimostrare discrepanze tra modelli, agenzia/competenze dinamiche, limite tentativi, revoca permessi e crash durante promozione.
- Distinguere tool `available` da tool `actually_invoked`, consumi dichiarati da consumi misurati, success rate per ruolo da semplici aggregazioni di output LLM.

Riferimenti di implementazione: [checkpoint WIP](NL_CODE_1_0_WIP.md), [safety harness](07_SAFETY.md), [piano operativo](NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md).

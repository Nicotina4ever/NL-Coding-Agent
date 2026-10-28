# 07 — Handoff breve: stabilizzazione del self-build, NON nuova espansione

Da leggere soltanto **dopo** che il processo di modifica attuale ha finito o è stato fermato in sicurezza. Questa istruzione è deliberatamente corta; i dettagli stanno in SPEC-28.

> Missione unica: stabilizzare il motore già presente prima di altre missioni autonome. Leggi `specifiche/28_SELF_HEALING_AGENT_HARNESS.md`, `specifiche/27_SELF_CHANGE_GATES_AND_DEPLOY.md` e lo stato reale del repository. **Non avviare nuove missioni self-build non presidiate.** Controlla prima che `autonomous_roadmap_planner.py` e i test siano completi, non stub. Implementa per primi staging di patch, recovery text-only selettivo e gate indipendenti; verifica con SH-01 (planner/test sabotati) e SH-04 (test verdi ma falsi). Permetti solo tentativi di riparazione limitati, altrimenti rollback o block senza perdere dirty/untracked. Esegui test e documenta prove; **non dichiare auto-healing affidabile senza test avversi riusciti e due missioni consecutive senza riparazione esterna**. Non spostare o cancellare directory e non modificare vendor/runtime/modelli.

Nessun comando per la sessione OpenCode è necessario finché non si conclude il lavoro in corso; questo file entra nella roadmap persistente.

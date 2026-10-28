# NL Coding Agent — audit sui sorgenti forniti (28 ottobre 2026)

## Ambito e verifiche

Materiale esaminato: `NL_Coding_Agent_Review.zip` fornito dall'utente, 135 file, 561.467 byte non compressi. Nessun accesso al repository reale `K:\AI\Coding Agent`, al suo database SQLite, ai processi o alla versione di Python embedded; le conclusioni descrivono **il contenuto dello ZIP**, non eventuali modifiche successive in Windows.

Le modifiche proposte sono state sviluppate in una cartella isolata. Verificati `python -m compileall` e **12 test mirati superati** (`test_staging_broker_adversarial.py`, `test_rollback_stub.py`, `test_scope_permission.py`). Suite completa, GUI, CrewAI/Ollama e loop reale **non verificati** qui: nel runtime di analisi il pacchetto CrewAI non è installato. Non dedurre che tutti i 72 test riportati altrove passino con queste modifiche.

## Problemi critici dimostrati dal codice originale

1. **Staging inesistente nel flusso effettivo.** `agents/orchestrator.py` usa `get_project_tools(self.root)`, poi `_apply_text_actions(self.root, output)`. Entrambi scrivono nel repository vero. `core/staging_broker.py` non è invocato da quel flusso. La semplice presenza del file non costituisce protezione.
2. **Ripristino impossibile da recovery_store.** `save_snapshot()` originale salva soltanto hash/lunghezze; `rollback_from_snapshot()` marca `restored` quando il file non è cambiato, ma non reintegra il precedente contenuto.
3. **Promozione insicura.** `promote_staged()` originale copia i file senza controllare l'hash preesistente del target, senza prova della verifica e senza journal di ripristino.
4. **Test avversi che modificano sorgenti reali.** `tests/test_staging_broker_adversarial.py` sovrascrive `nl_coding_agent/core/autonomous_roadmap_planner.py` e solo successivamente tenta un ripristino. Un'interruzione può lasciare codice danneggiato.
5. **Shell non confinata.** `tools/shell.py` esegue testo libero con `shell=True` e semplicemente `cwd=project_root`. Questo **non limita** il processo alla cartella, né impedisce modifiche esterne. `get_project_tools()` espone `run_command` a Developer e Debugger.
6. **Check gate tardivo e fail-open.** `core/selfbuild_runner.py` esegue controlli dopo `orch.run_mission()` e dopo che il Reviewer può aver scritto `completed` nel DB; l'`except` del gate registra e ignora errori. Il rollback del runner scrive direttamente la baseline senza un post-hash registrato, quindi può perdere modifiche concorrenti.
7. **Supervisor non autonomo nel passaggio tra obiettivi.** `run_autonomous()` legge `docs/NEXT_SELF_BUILD_MISSION.md` con `next_mission()`; non chiama `select_next_task()/write_roadmap_mission()` alla fine della missione. Con un documento invariato si ferma sul fingerprint già completato. `--max-missions 1` esegue una missione per avvio, non è un servizio persistente.
8. **I permessi testati sono parziali.** `tests/test_scope_permission.py` verifica funzioni di matching, ma non prova che il comando shell arbitrario o gli agent tools siano isolati.
9. **Roadmap artificiale.** Il planner nel file ricevuto seleziona la checklist e produce titoli `Backlog Consolidation: P...`, con scope pressoché fisso; non costruisce automaticamente un piano di implementazione pertinente a ogni voce della checklist.

## Modifiche fornite nel pacchetto

- `core/recovery_store.py`: registra preimage testuali (limite 1 MB per file), controllo del root e rollback **solo** quando l'hash corrente coincide con l'hash della postimage realmente registrata.
- `core/staging_broker.py`: crea staging source-only sotto `data/staging`, confronto con baseline, rilevamento stub/test indeboliti, scope, validazione e attestazione di verifica vincolata agli hash, preflight CAS, journal promozione e rollback CAS conservativo.
- `core/code_integrity_gate.py`: confronto strutturale AST di definizioni Python e test, non semplici conteggi di parole.
- `tests/test_staging_broker_adversarial.py` e `tests/test_rollback_stub.py`: fixture in cartelle temporanee, senza modificare file sorgenti o usare baseline DB #42.

**IMPORTANTE:** questa è una prima patch delle fondamenta, **non un harness completo già cablato al modello**. `mark_verified()` espone un'attestazione che deve essere chiamata solo dal verificatore attendibile, non dagli agenti. Il journal consente il recupero ma non fornisce una transazione atomica multi-file. I test su codice candidato continuano a richiedere processi isolati o un sandbox OS appropriato: eseguire Python generato dal modello con i privilegi utente può ancora toccare file esterni.

## Cosa manca prima di Self-Build non presidiato

1. Instradare **ogni** scrittura del Developer/Debugger, inclusi tool nativi, JSON-tool-call e fallback Markdown, al broker di staging; negare shell generica ai modelli senza sandbox OS.
2. Eseguire le regression suite **prima della promozione** in un workspace di prova e con un ambiente controllato, preservando una copia attendibile dei test precedenti. Solo il verificatore indipendente può attestare il risultato.
3. Collegare l'esito di promozione e il journal allo stato SQLite in una sequenza idempotente. Se il gate fallisce, DB=`blocked` e nessun `APPROVE` residuo. Gestire crash fra promozioni, rollback di file nuovi e modifiche concorrenti.
4. Implementare tentativi di repair limitati e osservabili, senza aggirare i gate.
5. Ripristinare il planner che sceglie task **di sviluppo reali**, deduplica, aggiorna la roadmap dopo la missione e continua attraverso più missioni in un supervisore separato dalla sessione di chat.
6. Collaudare con due missioni successive senza intervento esterno; richiedere approvazioni appropriate per fuori-scope/cloud/cancellazioni.

## Istruzioni di uso

Non copiare automaticamente sul repository mentre una missione è attiva. I file `PATCH/` sono proposte da integrare **dopo revisione dei diff**, non un installer auto-eseguibile. Aggiungere test e collegamento del broker in una missione manuale separata, con Self-Build automatico disabilitato, e non segnare SPEC-28 completata finché i gate non sono dimostrati end-to-end.

# SPEC-26 — Esecuzione autonoma dell'intero Blueprint, con un solo avvio

**Scopo:** un'istruzione iniziale per creare una **capacità permanente** riutilizzabile su qualunque progetto. Non una conversazione infinita e non centinaia di prompt manuali. **Stato:** requisito, non funzionalità già verificata.

## Cosa significa «senza comandi su comandi»

L'utente apre un progetto, assegna un Goal persistente e sceglie `Assistito` o `Automatico` una volta. Un **supervisor non-LLM**, persistente e riavviabile, legge il backlog, individua il prossimo task, attiva agenti con permessi, verifica il risultato e continua solo in condizioni sicure. Se si spegne il computer o non ci sono modelli disponibili, registra checkpoint e riprende alla successiva esecuzione; nessun processo prosegue magicamente a PC spento. Per un lavoro non presidiato servirà un launcher/scheduler/servizio realmente implementato che resti attivo, non solo un flag CLI o TODO di OpenCode.

## Pipeline universale

1. **Discover:** seleziona workspace + analizza obiettivi e codice; nel self-build il progetto è NL Coding Agent, negli altri progetti è la cartella aperta.
2. **Reconcile:** consulta `00_MASTER_INDEX.md`, `03_MASTER_CHECKLIST.md` e stato SQLite senza caricare tutto il corpus; deduplica Goal / Milestone / Task per IDs stabili, versioni e fingerprint.
3. **Prioritize:** confronta requisiti, prove, dipendenze, impatto, costo, rischi e override; esclude task bloccati e sceglie il prossimo READY.
4. **Protect:** controlla permessi, modifiche Git esistenti, file dirty/untracked, snapshot preimage leggero di soli file in write-scope; propone uno stop per conflitti o rischio non approvato.
5. **Execute:** Developer modifica file autorizzati con strumenti reali; Tester esegue test; Reviewer controlla il diff effettivo; Debugger interviene se i gate falliscono entro un limite di tentativi.
6. **Verify:** confronta test specifici, suite di regressione, accettazione, diff e artefatti; Reviewer `APPROVE` non prevale su test falliti. Non fare approvare al Reviewer il risultato dopo aver nascosto cambiamenti pertinenti dalla baseline.
7. **Commit state:** persiste evidenze, hash, config di modello/agente, esito, permessi, tempo/costi, milestone, progresso; aggiorna `CURRENT_STATE.md` e `NEXT_SELF_BUILD_MISSION.md` come viste dello stato reale.
8. **Continue:** avvia la successiva missione READY secondo la policy, oppure `WAITING_FOR_APPROVAL`, `WAITING_FOR_RESOURCES`, `BLOCKED`, `PAUSED`, `DONE`; nessuna cascata incontrollata.

## Modalità utente

- `Off`: non esegue missioni.
- `Assistito`: propone goal/team/scope, chiede consenso ai passaggi definiti dall'utente.
- `Automatico controllato`: prosegue tra task sicuri e già autorizzati, con budget di risorse/tempo/tentativi, pause e stop. Non approva autonomamente cancellazioni, migrazioni, pubblicazioni o nuove sorgenti cloud.

La scelta deve essere persistita per progetto; il self-build richiede inoltre una modalità più restrittiva. Il pulsante di configurazione sta in **Settings → Advanced → Autonomous Development**; avanzamento in Goals/Tasks/Missions; **Pausa e Stop** visibili durante esecuzione.

## Fonti di verità e scheduler

- SQLite per stati/transazioni/lock, cronologia di tentativi, idempotency key, lease/heartbeat e policy.
- Git e filesystem per codice realmente presente; diff veritiero, non dedotto dal testo del LLM.
- Master Blueprint per requisiti; Markdown non sovrascrive prove del codice né permessi dell'utente.
- Il planner può usare LLM, ma il loop di continuazione/approvazione non deve dipendere da memoria chat o autoreferenzialità del modello.
- Compiti eseguibili in parallelismo solo se ownership e risorse lo permettono; tool locali e GPU in uso da altri processi sono risorse contese.

## Prima milestone: self-build realmente autonomo e protetto

Dall'ultimo resoconto di OpenCode del 28 ottobre 2026 risultavano missione #42 `completed/APPROVE`, 69 test verdi e test di recovery verdi, **ma anche una sovrascrittura erronea di file sorgenti/test da parte del modello locale, riparata manualmente da OpenCode**. Quindi la capacità di autocostruzione *senza supervisione umana* NON è ancora provata. Verificare da repository/SQLite: non promuovere questo resoconto a prova definitiva.

Ordine di sicurezza **basato sulle dipendenze**, non numero fisso di agenti:

1. Snapshot pre-modifica e rollback selettivo, con preservazione del dirty state; controllo patch/stub inattesi.
2. Enforcement del write-scope e tool broker, grant per tool/percorso; impedire conflitti di writer.
3. Planner persistente e supervisor per una nuova missione READY, con loop idempotente e stop/pausa.
4. E2E intenzionalmente avverso: agente propone di troncare un modulo con stub; il quality gate lo rileva e recupera automaticamente senza perdita di lavoro dell'utente.
5. Un *secondo* task realizzato e verificato in sequenza con **solo i modelli locali**, senza riparazioni manuali di OpenCode.
6. Solo allora promuovere l'autonomia non presidiata a modalità normalmente utilizzabile, mantenendo restrizioni per i task rischiosi.

## Test di sistema obbligatori

- [ ] Nuova sessione/riavvio: seleziona prossima missione dal backlog e procede senza nuovo messaggio.
- [ ] Dopo un task approvato seleziona il successivo, senza rimanere su `NEXT_SELF_BUILD_MISSION.md` già completato.
- [ ] Fallimento test, output LLM non valido, stub distruttivo, tool error, quota 429, GPU occupata: comportamento controllato e recuperabile.
- [ ] Task ripetuto / crash tra commit e state-update: nessun duplicato, nessun file sovrascritto senza riconciliazione.
- [ ] Il supervisor non modifica fuori scope, non installa, non cancella, non pubblica né usa cloud senza permesso pertinente.
- [ ] Verifica dei due livelli: `mission --resume` della missione e scelta automatica del prossimo task dal backlog.
- [ ] Permessi e stato mantenuti per progetto indipendentemente dai TODO/compaction dell'IDE di sviluppo.

**Dipendenze:** SPEC-02, SPEC-02A, SPEC-03, SPEC-07, SPEC-15, SPEC-18, SPEC-19, SPEC-21, SPEC-23, SPEC-24, SPEC-25.

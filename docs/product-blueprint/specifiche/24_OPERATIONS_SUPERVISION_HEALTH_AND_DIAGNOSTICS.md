# SPEC-24 — Operazioni, diagnostica, continuità e controllo del lavoro lungo

**Priorità:** P1 dopo il ciclo self-build minimo. La parte necessaria al riavvio corretto appartiene a P0/SPEC-21.

## Problemi reali osservati nella fase bootstrap

- Quota provider esaurita (`429`), passaggio fra modelli e sessioni OpenCode; un TODO aperto non obbliga la conversazione a proseguire.
- CrewAI logging su console Windows con errori `charmap` per emoji, senza necessariamente causare fallimento del task.
- Review contaminata da modifiche esterne (Blueprint) nella baseline di missione #41; necessaria distinzione fra changed files, file autorizzati e snapshot, senza manipolare evidenze.
- `selfbuild --autonomous` dispone di loop **limitato**; finché non è verificata generazione della missione successiva dal backlog, non promettere autocompletamento.
- OpenCode crea cartelle di packaging sibling quando l'output path non è fissato; impedire per policy/test.

## Dashboard Health & Diagnostics

Un'area `Diagnostics` interrogabile da GUI/CLI deve esporre: versione app/runtime, provider e modelli disponibili, capacità tool, servizi GUI, ultimo pass/fail dei test, task bloccati, ultime exception, mission recovery points, space audit, processi di proprietà dell'app, salute Ollama e riconnessione. Non rendere disponibile per default una raccolta di segreti, token, codice proprietario o allegati. Export ZIP di **report redatto** soltanto su richiesta.

## Eventi e log

- Event ID stabile e correlazione `goal_id → milestone_id → task_id → mission_id → attempt_id → agent_id → provider_call_id`.
- Log strutturati con timestamp, esito, processo, comando redatto, durate, error category, log file path; dimensioni e retention configurabili.
- Distinguere errore di console/logging, errore LLM, tool failure, fallimento test, review rejection, quota, timeout, conflitto Git, risorsa GPU occupata.
- Retention di log vs recovery point: un failure log utile non è temp; i dati utente e le prove di QA non vanno cancellati dalla pulizia ordinaria.

## Poliche di esecuzione robusta

- Backoff per 429 e timeout transitori, con `Retry-After` se restituito, jitter e limiti configurati. Nessun retry rapido infinito né cambio silenzioso a provider pagato.
- Timeouts separati per inferenza, compilazione, test e download; heartbeat/progress indicator quando disponibile. CPU/GPU resource contention non equivale a crash.
- Se una missione sta usando la GPU e un carico esterno è rilevato, consentire queue/attesa/riprogrammazione e fallback soltanto secondo consent/policy. Non terminare processi esterni.
- Dead-letter / blocked queue per task che falliscono ripetutamente con medesimo errore. Raggruppare errori per causa e proporre remediation concreta.
- Watchdog interno recupera solo processi posseduti dall'app; non riavvia infinitamente l'app se una nuova release causa crash. Self-update applica controllo di avvio, versione precedente avviabile e recovery di soli file modificati.

## Autonomia e UX

- Gli agenti possono proporre miglioramenti del prodotto o BUG, ma restano `PROPOSED` finché goal/priorità non li rendono candidati.
- Mostrare missione attuale, ultimo risultato verificato, motivo di attesa, prossimo comando, costi stimati/consumati, utilizzo risorse.
- UI non bloccante; l'utente deve poter interrompere o cambiare impostazioni per la *prossima* missione senza corrompere lo stato della corrente.

## Acceptance gates

- [ ] Un 429 produce un log esplicito, stato `WAITING_PROVIDER/BLOCKED`, senza perdita di missione e senza costo cloud non consentito.
- [ ] Test GPU lungo non viene scambiato per crash se registra progress/heartbeat; test impallato termina con diagnosi controllata.
- [ ] L'export diagnostico rimuove token, path sensibili e allegati non autorizzati.
- [ ] Le baseline distinguono file esterni da scope consentito senza nascondere modifiche dell'agente.
- [ ] Crash del supervisor → riavvio sicuro, unico worker, task resume senza doppia patch.
- [ ] Integrità database verificata, migrazioni reversibili quando fattibile, spazio/caches distinguibili da source e recovery.
- [ ] CLI e GUI presentano lo stesso stato durevole.

**Dipendenze:** SPEC-02/02A/03/07/13/13A/14/18/21/23.

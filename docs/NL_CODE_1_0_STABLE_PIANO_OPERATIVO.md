# NL Code 1.0 STABLE — Piano operativo integrato per DeepSeek Harness

**Data di riferimento:** 30 ottobre 2026  
**Prodotto:** NL Code (standalone Code - OSS personalizzata), NL Coder (estensione VS Code Insiders), NL Coding Engine (motore condiviso Python/CrewAI/Flows).  
**Repository operativo:** `K:\AI\NL Coding Agent`  
**Traguardo:** un coding agent locale-first realmente autonomo, multi-modello, multi-agente, affidabile, riprendibile e utilizzabile, con interfaccia autonoma riconoscibile come prodotto NL.  
**Stato di questo documento:** piano di realizzazione e accettazione, **NON** dichiarazione di 1.0 già pronta.

## 0. Mandato e criteri generali

- Un solo motore Python, un solo Supervisor, un solo Model Router, una sola fonte di verità per database, permessi, modelli, agenti e missioni. NL Coder per VS Code e NL Code standalone sono due client dello stesso motore.
- Non ricreare il progetto; valorizzare la base verificata. Non presentare ogni commit/VSIX come traguardo di prodotto. Commits e checkpoint tecnici vanno bene; **1.0 STABLE** soltanto dopo la matrice di accettazione.
- Progettazione locale-first, Ollama/llama.cpp/LM Studio e altri provider compatibili, cloud opzionale con opt-in e costi controllati. Preferire modelli locali per test e attività ripetitive.
- Supportare sviluppo di un repository esistente **e** creazione di un'applicazione da zero, includendo progettazione, codice, test, debugging, consolidamento e documentazione.
- Team dinamici, specialisti verticali personalizzabili, dipendenze e più task per ruolo, ragionamento/pianificazione basati sul progetto ispezionato (non solo regex su nomi di file). Non fissare un numero immutabile di agenti.
- Autonomia sostenuta per ore, pause sicure, ripresa deterministica e interventi dell'utente (queue, steering, stop). Non promettere sicurezza assoluta; dimostrare le barriere con prove negative.
- Evitare download massivi e duplicazioni di Python embedded, modelli e checkpoint; permettere percorsi esterni. Niente virtualenv obbligatori, niente installer globali necessari.
- Conservare il brand NL dal logo originale, palette esistente e credits dell'ideatore Nicola Lanci. Nessun glow sul testo tecnico; privilegiare leggibilità e densità informativa ragionevole.
- Nessuna modifica distruttiva al database originale, ai dati delle missioni, alle credenziali e ai progetti reali durante l'accettazione. Usare profili e repository di prova isolati. Mai usare SendKeys globali senza verificare inequivocabilmente il focus dell'applicazione.

## 1. Stato noto e verificabile da cui ripartire

### Evidenze consegnate da DeepSeek (richiedono riesame nel repository al momento del lavoro)

- Checkpoint `03a6a25`: team proporzionale, handoff, model bindings, prove VSIX e missione semplice.
- Checkpoint `1655cbb`: multi-subtask developer, primo vero `MissionFlow` con `@start/@router/@listen`, ciclo `repair → verify`, tools locali, aggregazione delle prestazioni del Model Router, percorso Chat/MCP predefinito Flow; **WIP, non release**.
- Test dichiarati nell'ultimo checkpoint: 30 mirati PASS, 41 Supervisor PASS, missione Flow semplice PASS. **Una prova multi-modulo complessa e repair reale NON sono state completate.** Il test della vecchia missione team si aspetta ancora un solo task developer: regressione aperta.
- VSIX 0.3.0 (ispezionata): `nlcodingagent.nl-coding-agent`, nome visibile NL Coder, entry `out/extension.js`, SDK MCP ufficiale; nessun README top-level nel pacchetto; impostazioni `engineRoot`, `pythonPath`, `allowExecution`, `requestTimeoutSeconds`, `researchProfile`; Chat/controller separati da missioni; logica `busyChat` impedisce seconda richiesta; `nlc_converse` passa `history: []` (il backend può ricostruirla, ma va verificato).
- `chatHistory()` legge la cronologia persistita **per progetto**, non gestisce esplicitamente sessioni multiple; `handleUserMessage` invia gli allegati espliciti, azzera la lista dopo successo. `currentEditor()` tiene l'ultimo editor attivo, ma non allega automaticamente il suo testo in ogni turno: esaminare condizioni di errore, cambi di editor, attachment stale e UX.
- Standalone Windows `K:\AI\NL Coding Agent\.workspace\dist\NL Code\NL Code.exe` già costruita e avviata in prove precedenti; prima distribuzione ~1,43 GB e includeva un'estensione precedente, quindi **non è provata l'integrazione delle ultimissime funzionalità**.
- GUI attuale standalone sostanzialmente Code - OSS con branding superficiale, UI Copilot nativa visibile e NL Coder secondario: non conforme all'identità desiderata.
- Screenshot della pagina extension: logo presente, **No README available**, descrizione tecnica grezza, mancano una presentazione curata e un onboarding.
- Avvisi `star-activation` appartengono a manifest **upstream** Git/Git-base/test in `.workspace/build/nl-code-oss/src` e `.build/`, non necessariamente a NL Coder. Non fare patch ai manifest generati solo per nascondere warning.
- `settings.json` dell'utente presentava nel testo copiato `engineRoot` con caratteri/escape non validi; possibile ulteriore trasformazione degli URL in markup Markdown durante il copia-incolla. Validare **il vero file** JSONC prima di correggerlo, senza sovrascrivere altri settings.

### Verdetti da non gonfiare

- `CrewAIBackend` esegue un Crew con un solo agente per stage LLM; la collaborazione tra ruoli è orchestrata dal Supervisor. L'esistenza di CrewAI non dimostra delega gerarchica nativa CrewAI.
- Flow con router/listener è implementato nel checkpoint WIP; **repair con errore reale e resume multi-task non sono ancora dimostrati**.
- `auto_select()` e `historical_performance()` esistono secondo il report; **selezione auto reale e capability probe non ancora validate**.
- Qwen che dice «non posso leggere file» non prova un system prompt restrittivo: il modello può allucinare le proprie limitazioni. Verificare le effettive tool invocation e gli artefatti, non le dichiarazioni del modello.
- Test unitari verdi non equivalgono a una buona esperienza d'uso né a un'app di distribuzione stabile.

## 2. Ordine esecutivo per la ripresa — stop ai lavori paralleli disorganizzati

### FASE A — Baseline, regressioni e connessione (bloccante)

1. Leggere `docs/NL_CODE_1_0_WIP.md`, `docs/MULTI_AGENT_RUNTIME.md`, blueprint/checklist, commit `1655cbb`, test e tracce esistenti. Fare `git status`, distinguere modifiche non committate di altri agenti, identificare DB/config attivi e build realmente utilizzata.
2. Inventariare punti di entrata: `nlc_converse`, `start_mission`, `mission_detail`, `chat_history`, settings, Studio GUI, standalone launcher, `NL_DATA_DIR`, Flow, task planner e autorizzazioni.
3. Eseguire la suite Python complessiva, test frontend/webview/extension-host e accettazione installed VSIX con **profilo isolato**. Correggere prima il test team divenuto incompatibile con più task developer; verificare se esiste regressione reale del motore.
4. Riprodurre con log il bug `engineRoot` mancante in installazione VSIX, il caso JSONC settings invalido e la mancata discovery del runtime, senza toccare configurazioni di terzi.
5. Registrare un report conciso `BASELINE_1_0.md`: revisioni, suite PASS/FAIL, difetti riprodotti, percorsi, risorse, dati non toccati. NON riprogettare componenti già verificati.

**Gate A:** suite esistente senza regressioni non spiegate; progetto di test isolato; storia/DB live intatti; primo avvio diagnosticabile anche quando il runtime non è configurato.

### FASE B — Chat **davvero agentica** e Session/Conversation Manager (bloccante)

1. Ispezionare esattamente come `nlc_converse` costruisce system prompt, tool schema, chiamate a provider, storage e memoria. Registrare **nomi e risultati reali** dei tool: non dedurre dal testo generato dal modello.
2. Unificare semanticamente Chat e Mission Controller sul Supervisor e i tool del motore, senza sostituire il modello con una shell privilegiata. Per richieste di sola lettura: consultazione file/ricerca workspace, editor/selection context, diff/Git status, elenco tool permessi, informazioni progetto. Per modifiche: piano/missione autorizzata, diff, test, approvazione e promozione, mai patch diretto fuori dal perimetro.
3. Il modello deve conoscere le capacità *effettive* per quella sessione: per `read-only` deve poter usare tool READ autorizzati; per azioni non autorizzate deve motivare il limite reale. Se un modello non supporta tool calling nativo, usare percorso alternativo verificato del motore, o dichiarare la limitazione e offrire un modello compatibile; non simulare invocazioni.
4. Aggiungere strumenti Chat interrogabili dal modello con telemetria verificabile: `list_dir`, `read_file` (bounded), `search_files/search_text`, `git_status/diff`, `read_diagnostics`, `get_project_context`, `get_mission_state` e, dove sicuro, `run_tests`, `run_command`, URL Research e MCP tramite policy. Evitare che l'estensione inventi nuove autorizzazioni.
5. Conversazioni multiple per progetto, titolo, elenco, ricerca, apertura, rinomina, archivio, eliminazione controllata, esportazione opzionale; ripresa dello storico corretto anche dopo riavvio e cambio progetto. Migrare se necessario senza perdere chat precedenti, niente secondo database per la stessa informazione.
6. Contesto: distinguere `workspace/project` (riferimento), `file/editor/selection` (riferimento leggero o snapshot esplicito) e `attachment` (scelta esplicita per il singolo invio). Mostrare pill e consentire rimuovi; conservare snapshot/hash/versione senza reinserire testo invariato in tutte le chiamate. Se l'invio fallisce, mantenere in modo controllabile gli allegati non ancora consumati e non duplicarli.
7. Coda persistente di messaggi, `enqueue/edit/reorder/remove`, steering al prossimo checkpoint, Stop generazione Chat, Stop missione distinto, Resume, segnalazione degli effetti collaterali e limite di esecuzione. Il nuovo input non deve perdersi durante `busyChat`; lo stato deve sopravvivere a reload/process restart.
8. Modellare Goals → Milestones → Tasks → Missions distintamente. Chat può creare e discutere goal/TODO, assegnare task al Supervisor e consultarli; un messaggio ordinario non deve avviare una missione distruttiva senza policy/autorizzazione.
9. Per sessioni lunghe: strategia riassunto del contesto, recupero selettivo, riferimenti a diff/artefatti; non copiare ogni volta README enormi. Log strumenti, tokens/durate/errori e limiti di contesto con dati veri.

**Gate B — da provare in VSIX installata:** «Leggi `nl_agent.py` e riporta le prime 5 righe» restituisce testo reale + **trace tool read_file**; «cerca l'uso di Supervisor nel repository» restituisce percorsi verificati; `READ-only` blocca una scrittura reale; inviare più messaggi durante una risposta li mette in queue; steering interviene sul job; stop e resume funzionano senza lavoro fantasma; cronologia e allegati rimangono coerenti dopo restart e fra progetti.

### FASE C — Motore CrewAI/Flows: completare i TODO rimasti (bloccante)

1. Completare **handoff tipizzati**: input/output per ruolo, task_id, dipendenze, artefatti, paths, hash, decisioni, open_issues, next_steps, modello, usage, verifica, confidence/unknowns. Validazione schema, schema version, migrazioni leggere, fallback legacy, tracciabilità di chi consuma davvero la consegna.
2. Planner che ispeziona progetto, simboli, test e dipendenze prima di definire DAG/task: più task per ruolo, specialisti temporanei, raggruppamenti intelligenti, possibilità di parallelizzare task indipendenti con risorse/lock condivisi, integrazione finale, rivalutazione del piano dopo errore. Numero agenti dinamico.
3. Flows `@start/@router/@listen` **realmente in uso** dalla Chat e dalle missioni: sviluppa/verifica/ripara/riesamina/promuovi; branch read-only/audit/approval; checkpoint/heartbeat/stop/resume idempotente; no doppie promozioni né lost work, niente loop infinito. Testare l'errore di test reale e la correzione reale, non solo FakeExecutor.
4. `ModelRouter`: capability probe reale (tool calling, JSON strutturato, context window, vision se pertinente) e score storico per categoria task, esito verificato, latenza, risorse RAM/VRAM, token e costo quando disponibile. Gestire cold start, poche osservazioni, modelli nuovi e fallback esplicito. Mai scambiare il successo del reviewer con garanzia di qualità. Overrides manuali persistenti; mai sostituzione silenziosa di route.
5. Resource Scheduler adatto a host con più modelli e GPU limitata: stima GPU/CPU/RAM, scarico modelli inattivi quando opportuno, inferenza seriale dove serve, parallelismo CPU/test indipendente, nessuna assunzione che ogni ruolo debba occupare VRAM contemporaneamente.
6. Strumenti veri attraverso interfaccia unica con permessi e log: file/search/patch, run_command (`shell=False` o equivalente sicuro), tests/build, Git, URL Research, MCP discovery **e invoke** autorizzato e tracciato, REA. Aggiungere i connettori per provider supportati senza duplicare gate.
7. Cloud e costi: BYOK solo se autorizzato, limite missione/giorno, conferma per escalation, conteggio reale del provider se disponibile, stime marcate come stime; default locale senza spesa. Compiti di routine sul locale, non su DeepSeek cloud per inerzia.
8. Verifiche indipendenti candidate/oracle, static checks, integration tests pertinenti, reviewer diverso quando utile, evidenze e diff sempre consultabili. Prevenire il caso di test che passano perché l'agente ha alterato i test di riferimento.

**Gate C:** missione realistica multi-modulo con più task e dipendenze, almeno un test inizialmente rosso e repair guidato da Flow, interruzione deliberata e ripresa in un nuovo processo, code promotion soltanto dopo verifiche, handoff tutti leggibili e usati, model binding e tool trace reali, nessun intervento manuale fuori dalle autorizzazioni iniziali.

### FASE D — Settings, Model Hub, agent editor e gestione dati (bloccante)

1. Primo avvio: discovery del runtime accanto all'app **o** selezione del percorso con Browse; scelta di path di motore, modelli/cache e dati; validazione di `nl_agent.py`, runtime Python, protocol version, permessi. VSIX può usare engine esterno, standalone lo trova o guida alla configurazione. Nessun path fisso `K:\` nel prodotto consegnato.
2. Impostazioni realmente modificabili tramite backend (save, validate, dry-run, revert); separare `execution mode` estensione da `READ/WRITE/EXECUTE` progetto. Spiegare permessi effettivi, perché un'azione è negata e chi può concederla. Non avere una seconda fonte di verità nel webview.
3. Model Hub: provider enable/test, disponibilità reale e stato caricato, modelli rilevati, role bindings, profili `Maximum Verified Quality / Balanced / Fast / Resource-saving / Custom`, parametri per agente, capability probe e motivazione del router; possibilità di configurare specialisti e strumenti, con validazione dei cambiamenti.
4. Sessions, Goals, Missions e Results con viste distinte e filtri. **Le missioni persistenti sono un registro di lavori/recovery**, non una lista infinita di cose da eseguire: stati pending/running/blocked/completed/archived, filtri, ricerca e archiviazione; pending e terminali si possono eliminare manualmente con conferma, mentre running richiede stop cooperativo.
5. Database/Storage Manager: scansione read-only e **misura dello spazio reale** per conversazioni, allegati, missioni, task attempts, event logs, diff, workspaces candidati, checkpoint, cache e modelli; attribuzione a progetto, retention policy configurabile, preview di cosa verrà eliminato e conferma mirata. Archiviare ≠ cancellare. Togliere un progetto dall'IDE ≠ cancellarne sorgenti.
6. SQLite: transazioni/FK e ordine di cancellazione corretti, vacuum/compattazione sicura a DB non occupato, backup/export opzionale **prima** della purga, misurazione dello spazio effettivamente recuperato, recovery su crash e test anti-corruzione. Mai toccare modelli condivisi, progetti sorgente, credential stores o dati di altre app.
7. Diagnostica: "Engine Doctor" accessibile, controlli runtime/provider/SQLite/Flow/permissions, esportazione log ripulita da segreti, gestione errori comprensibile. Correggere `settings.json` solo dopo parsing JSONC effettivo, lavorando sulla chiave necessaria, mai azzerare le preferenze globali dell'utente.

**Gate D:** utente configura senza editare YAML/JSON, cambia un reviewer e vede applicata realmente la nuova route; crea/apre/archivia chat e missioni; ripulisce una fixture conclusa, misura spazio liberato, riapre i progetti attivi senza perdita; errore runtime assente porta a wizard, non a messaggio tecnico bloccante.

### FASE E — Identità NL Code e UX standalone (bloccante per standalone 1.0)

1. Mantenere Code - OSS per editor/Git/terminal/debugger, ma costruire un **workbench mission-first**: home NL (nuovo progetto, apri repository, ultimi progetti, missioni, stato engine e modelli), Chat NL principale e spaziosa, Mission Control, Agent Factory, Model Hub, Tasks/Goals, timeline eventi e risultati; editor sempre disponibile e dockabile.
2. Primo avvio **non** deve presentare default onboarding/Copilot come protagonista. Disabilitare/nascondere le entry/viste predefinite non pertinenti nel profilo NL, in modo reversibile; non modificare indiscriminatamente estensioni Git o upstream Code - OSS. Valutare gli interventi source-workbench realmente necessari e mantenerli tramite patch/scripts riproducibili.
3. Applicare logo SVG reale e palette NL (`#7531FE`, `#E4469B`, `#46A3C0` come riferimenti esistenti, da affinare osservando assets/theme tokens) a titlebar, splash, activity bar, editor theme, schede, pannelli, icone, toolbar e dialogs. Design coerente e leggibile, nessun glow sui testi. Layout per vari DPI e schermi; accessibilità, scaling, focus/keyboard e contrasto.
4. `Help → About NL Code`: ideazione, progettazione e direzione **Nicola Lanci**, repository GitHub `Nicotina4ever/NL-Coding-Agent`, acknowledgments tecnici senza confondere credits. `NL Coder` rimane l'estensione installabile in VS Code con medesimo backend.
5. Migliorare VSIX: README incluso, icona, changelog, screenshots, comandi, onboarding, category, errore diagnosi, impostazioni corrette. Non cambiare ID interno senza una migrazione. Gli upstream `star-activation` **non sono difetti dell'estensione NL**.
6. Evitare rebuild completo di Code - OSS per ogni modifica engine/webview: canale di aggiornamento extension/runtime e profilo portable; ricompilare il workbench soltanto quando cambia il suo sorgente. Testare che la distribuzione contenga davvero l'ultima estensione.

**Gate E:** a primo avvio schermata, marchio e flusso principale sono riconoscibilmente NL; utente può iniziare una missione senza trovare prima l'estensione nel sidebar; nessun Copilot protagonista; editor/Git/terminal funzionano; About e guida presenti; layout salvato e ripristinato; stessa missione end-to-end via standalone e via VSIX.

### FASE F — Accettazione 1.0, rilascio pulito e distribuzione

**Fixture reale**: repository isolato multi-modulo di dimensione significativa, con progetto, tests, difetto iniziale non banale e requisiti di integrazione; idealmente copia di un sottoinsieme di NL Audio Matrix o altro componente verificabile **senza necessità di hardware**. Il progetto reale non è campo di esperimenti automatici distruttivi.

**Scenari minimi obbligatori:**

1. Nuovo progetto da zero: crea struttura, codice, test, documentazione, esegue, corregge e propone risultato finale in progetto autorizzato.
2. Progetto esistente: scansione, pianificazione multi-ruolo, più file e subtasks, dependency graph, handoff, build/test, revisione e promozione.
3. Failure reale: test fallisce, Flow entra `repair`, debugger propone patch verificabile, verifica riparte, reviewer controlla, risultato coerente.
4. Pause/Resume: Stop durante generazione, durante più task e durante verifica; riavvio di UI/engine; nessuna modifica doppia, stato e queue consistenti. Verificare emergency stop e bounded runaway loops.
5. Chat agentica: file read senza upload, ricerca testo, contesto editor solo quando desiderato, URL autorizzato, tool calls tracciate, conservazione storico; queue/steering e redirect del Supervisor.
6. Permessi: read-only vieta write/execute; policy di progetto prevale sui toggles GUI; fuori-scope/DELETE/NETWORK/CLOUD negati, Escalation solo esplicita; no command injection tramite prompt/file/tool output.
7. Model routing: scegliere tra modelli disponibili con test misurati, spiegare scelta, rispettare override, gestire timeout/offline e pressione VRAM; prove locale-only senza spesa.
8. Storage: archivio e purga di progetto *chiuso*, con simulazione di impatto e spazio, preservando progetti aperti, checkpoint condivisi e sorgenti.
9. Standalone: fresh extraction in nuova directory, primo avvio guidato, niente repo di sviluppo necessario, funzionamento NL Chat e missione vera; ripresa dopo update, dati preservati, nessun modello duplicato per default.
10. VSIX: installata in profilo VS Code Insiders pulito, onboarding engineRoot, stessi servizi del motore, Chat/Missions/Model Hub/History; non contaminare configurazione personale dell'utente.
11. Stress/affidabilità: test lunga durata con budget di operazioni/tokens, stop su limite, checkpoint, crash simulato, restart; monitor memory/CPU/GPU, SQLite concurrency, no progress falsi.
12. UI/branding: screenshot e ispezione umana a più risoluzioni/DPI, componenti originali NL, credits About, assenza UI predefinita invasiva.

**Requisiti di prova:** per ogni caso comando, input/fixture, modello e versione, log, trace dei tool realmente invocati, handoff, diff, test/verdetto, risultato, risorse/spesa misurata (se disponibile), commit e stato PASS/FAIL. Test falsi, log inventati o screen mock non sono prove.

**Rilascio Windows 1.0:** si può dichiarare soltanto quando tutti i gate per Windows sono superati, il pacchetto si avvia su profilo pulito e l'utente approva l'esperienza. Mac/Linux vanno preparati nello stesso codice ma **non etichettati supportati** finché build/runtime e prove native non sono state realmente eseguite. Condivisione privata GitHub e releases per OS dopo le rispettive prove; escludere credenziali, checkpoint e dati personali.

## 3. Cosa fare dei TODO del checkpoint 1655cbb

| TODO | Decisione per la ripresa |
|---|---|
| Audit Flows/executor/planner/tools/router/persistence | **Completato**: leggere il rapporto e fare breve diff/checkpoint audit, senza rifarlo da zero |
| Dynamic multi-task planner | **Parzialmente implementato**: correggere regressione e rendere pianificazione dipendente dal repository |
| Real branching/resumable MissionFlow | **Implementato WIP**: completare prova real error/repair e resume multi-task |
| Structured handoffs + adaptive specialists | **PRIORITÀ**, backend + consumo reale da ogni ruolo |
| Measured/historical router + cost controls | **PRIORITÀ**, capability reali, routing end-to-end, limiti spesa, override |
| Real file/shell/Git/test/Research/MCP tools | **Parziale**: provare tool use da Chat e da Flow; implementare invocation MCP consentita |
| Realistic multi-module acceptance with forced recovery | **GATE CRITICO**, non un altro calc.py |
| End-to-end via NL Coder with evidence | **GATE CRITICO**, includere stop/queue/steering/history/UI e standalone |

I quattro TODO iniziali segnati «fatti» non equivalgono a «tutto provato in release». I punti finali della lista sono i **gate di accettazione**, non attività decorative.

## 4. Modalità di lavoro per non bruciare budget

- Una missione integrata con un unico backlog checklist; sottofasi interne e commit checkpoint, non una sequenza di nuovi prompt per ogni file.
- Prima implementazione/test focalizzati sul motore locale; DeepSeek esterno usato per analisi/integration/debugging difficili e decisioni, non come sostituto di test meccanici o prove Ollama.
- Esibire dati reali su consumi cloud. Default **zero cloud** dentro NL Code salvo opt-in; fermare per budget configurato. Evitare MAX persistente se non giustificato.
- Ferma la fase se emerge una regressione critica: correggerla prima della fase successiva. Non proseguire sovrapponendo nuovi strati a fondamenta rotte.
- Evitare modifiche inutili in `.workspace/build/nl-code-oss/src` e generated directories. Usare overlay/patch riproducibili e profilare test di sviluppo separati dai repository build enormi.
- Conservare working tree utente, Git e database originali. Niente pulizia automatica senza scan/preview/permesso.
- Ogni checkpoint restituisce: funzionalità effettivamente ottenuta, test veri, FAIL noti, commit, via di ripresa; non cambiare versione utente finché non passa il gate release.

## 5. Prima sessione di DeepSeek — ordine immediato

1. Leggere questo file e i checkpoint esistenti; verificare git diff, test e difetti osservati su VSIX 0.3.0.
2. **Riparare regressione planner e diagnosi Chat/Tool/History**; ottenere una lettura file reale via Chat con trace, non un testo generato sulla capacità di leggere.
3. Implementare sessioni, queue/steering/stop in modo persistente e testarle sul client installato.
4. Completare handoff tipizzati, router capability probes, tool invocation e real Flow repair; mantenere un solo motore.
5. Eseguire la missione multi-modulo con errore reale e ripresa. Se fallisce, debuggare il motore prima di dedicare tempo a splash/theme.
6. Soltanto dopo: Settings/Model Hub/Storage Manager utilizzabili; workbench mission-first e branding completo; sync VSIX/standalone.
7. Accettazione fresh install e release 1.0 Windows **solo se** i gate passano. Altrimenti lasciare un checkpoint utilizzabile che descriva precisamente cosa impedisce la release.

## 6. Definizione di DONE

**Non è DONE**: «compila», «140/1283 test verdi», «esiste una classe Flow», «CrewAI viene importato», «modello dice che può leggere i file», «uno screenshot mostra due funzioni aggiunte», «l'eseguibile ha il nuovo nome», «README dichiara completezza».

**È DONE**: aprire NL Code da installazione pulita, selezionare motore/progetto e modelli, affidare un'app o una funzionalità complessa, vedere gli agenti operare e consegnarsi artefatti reali, intervenire durante l'esecuzione, chiudere e riaprire, ottenere diff e test affidabili, archiviarne il lavoro e ripulirne i dati, con un'identità NL coerente. Il tutto senza moltiplicare runtime e senza modifiche fuori policy.

---

**Nota di comunicazione**: non chiedere all'utente di approvare micro-piani intermedi o installare copie ridondanti. Se rimangono problemi non bloccanti, dichiararli esplicitamente; non utilizzare la sigla STABLE per una build non accettata.

## Objective

Costruire il Context Engine e la memoria di progetto di NL Code: budget di contesto misurato con
degrado graduale, summarization persistita, project profile e recupero selettivo, così che Chat e
missioni recuperino il contesto reale del progetto invece di rileggere il repository o fallire per
budget.

## Scope of Work

- Nuovo modulo `nl_coding_agent/context/` per budget, stima token, finestra scorrevole e summary.
- Integrare budget e summary in `nl_coding_agent/app/chat_tools.py` e nei prompt missione di
  `nl_coding_agent/agents/orchestrator.py`.
- Persistenza di profile/memoria in `nl_coding_agent/persistence/database.py` e servizio in
  `nl_coding_agent/app/services.py`.
- Test di accettazione in `tests/test_context_engine.py`.
- Mantenere `docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md` come unica fonte del piano.

## Acceptance Gates

- [ ] Chat oltre budget degrada con summary persistita, senza "start a narrower turn".
- [ ] Riavvio di client/motore conserva summary e project profile.
- [ ] Una missione multi-modulo usa il retrieval e cita i file pertinenti.
- [ ] La memoria di progetto recupera errori/decisioni di missioni precedenti.
- [ ] Nessuna regressione della suite completa.

## Programma corrente — evoluzione harness (checkpoint 2 novembre 2026)

Questo blocco sostituisce le "prossime missioni" precedenti ed è la priorità operativa reale,
derivata da quattro audit sul codice (motore, percorso team, frontend, storage/docs) e dalla
baseline di test. Non è una roadmap teorica: ogni voce indica il codice interessato e la prova.

**Stato verificato**: baseline 1366 PASS; percorso Team Architect→specialisti corretto (route
auditor, tool di scrittura garantiti, task pianificati per architect/auditor assegnati,
`dropped_roles`/`remapped_roles` esposti); `mission_wall_time_s` imposto ai checkpoint; tool di
developer/debugger coerenti con i prompt; Delete missione pulisce lo staging usa-e-getta e conserva
gli stage con journal; preview Research ripristinata. Restano aperte le lacune elencate in
`CURRENT_STATE.md`.

### P0 — Chiusura affidabilità (in corso)

1. Suite completa verde su albero fermo e commit di checkpoint; nessuna modifica concorrente durante
   la suite.
2. NL Coder: stato connessione reale quando l'engine muore, Stop Chat che annulla la chiamata in
   volo, drain della coda all'avvio, blocco del doppio invio, monitor che non sovrascrive la
   missione selezionata, conferma esplicita per CLOUD, `/help`. File: `frontend/src/chatProvider.ts`,
   `frontend/src/backend.ts`, `frontend/media/main.js`.
3. Rigenerare VSIX e payload portabile dallo stesso HEAD e correggere `BUILD_INFO.json`; nessuna
   distribuzione dichiarata valida se la VSIX inclusa non corrisponde al sorgente.

### P1 — Context Engine e project profile (prossima missione)

Obiettivo: contesto misurato e degradabile invece del muro a 60k caratteri; memoria di progetto
persistita e recupero selettivo; continuità fra sessioni lunghe. Codice: nuovo
`nl_coding_agent/context/` (budget, tokenizer stimato, finestra scorrevole, summarization locale
opzionale persistita), `app/chat_tools.py`, `agents/orchestrator.py`, `persistence/database.py`
(project profile e memorie), `app/services.py` (`get_project_context`). Prove: turno Chat che supera
il budget senza errore; summary persistita e riusata dopo restart; prompt missione costruito da
profile+retrieval invece che da snapshot alfabetico; nessuna perdita di allegati/history.

### P2 — Code Intelligence e hook

Obiettivo: il modello vede il codice come un IDE. Esporre `lsp_diagnostics` e ricerca simboli come
tool read-only sia in Chat sia in missione; check post-write (sintassi/import/diagnostica) con
recovery bounded; usare il ledger `tool_invocations` per le verifiche. Codice: `app/lsp.py`,
`app/chat_tools.py`, `tools/crew_tools.py`, `agents/orchestrator.py`,
`core/code_integrity_gate.py`. Prove: errore introdotto in una patch rilevato prima del tester;
diagnostica mostrata con file/riga; nessun falso PASS.

### P3 — Team Architect dinamico, skills e subagenti

Obiettivo: specialisti realmente dinamici (oltre i 5 ruoli base) con assegnazione operativa
persistita e visibile; skills caricate progressivamente (`.agents/skills`, `.nlcode/skills`);
subagenti read-only con contesto isolato e handoff strutturato, parallelizzabili quando non
confliggono. Codice: `agents/specs.py`, `agents/orchestrator.py`, `app/services.py`,
`persistence/missions.py`, nuovo `nl_coding_agent/skills/` e `nl_coding_agent/agents/subagents.py`.
Prove: una squadra con ruoli non-base riceve task propri; una skill viene caricata solo quando
richiesta e il suo uso è tracciato; un subagente produce un handoff consumato dal Supervisor.

### P4 — Model intelligence e risorse

Obiettivo: Chat e missioni usano la stessa evidenza (capability misurate, storico per ruolo,
latenza/VRAM, gate risorse); nessuna sostituzione silenziosa di route; override espliciti
persistenti. Codice: `models/model_router.py`, `app/services.py` (`_chat_candidates`),
`core/resource_gate.py`, `models/operational_probes.py`. Prove: Chat con route `auto` motiva la
scelta persisted; route esplicita vince; modello offline/timeout produce fallback dichiarato.

### P5 — Interfaccia, storage e documentazione

Obiettivo: una sola esperienza coerente, non un pannello per funzione; pulizia storage con
preview/misura e conferma esplicita; documentazione consolidata (README, `docs/README`,
`CURRENT_STATE`, questo piano, gate, operations, safety) senza nuovi file di fase. La pulizia
proposta (audit storage) è: Livello A 2.761 MB, Livello B 4.224 MB, Livello C 9.821 MB; nessuna
cancellazione senza autorizzazione dell'utente e senza processi/test fermi.

## Acceptance Gates correnti

- [x] Percorso Team Architect→specialisti: route, istruzioni, tool e task verificati con test.
- [x] `mission_wall_time_s` imposto e ripresa possibile dopo interruzione.
- [x] Delete missione non perde file del progetto e non lascia staging usa-e-getta.
- [ ] Suite completa verde su albero fermo (unico residuo noto: flakiness CI smoke sotto editing
      concorrente, da riprovare a tree fermo).
- [ ] VSIX/payload rigenerati dallo stesso HEAD e verificati.
- [ ] Context engine con budget/summary e project memory (P1).
- [ ] Code intelligence e diagnostica post-write (P2).
- [ ] Specialisti dinamici, skills e subagenti (P3).
- [ ] Routing unificato Chat/missioni con evidence (P4).
- [ ] Una missione end-to-end su progetto esistente con errore reale, repair, review e resume,
      eseguita dall'interfaccia installata e registrata con evidenze.


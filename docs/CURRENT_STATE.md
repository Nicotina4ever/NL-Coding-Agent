**Checkpoint 2 novembre 2026 (sessione harness, P1–P5).** P1 Context Engine, P2 Code Intelligence/hook, P3 skills+subagenti+specialisti advisory, P4 routing unificato e P5 distribuzione sono implementati e verificati. Suite Python completa **1405 passed** a working tree fermo. Evidenze reali distinte dai test simulati: missione multi-agente con advisor e skill (`docs/evidence/nlcode/real-e2e-20261102-182320.json`), riparazione Flow di un errore introdotto dall'agente (test dedicato), LSP reale con errori file/riga, Chat con routing ModelRouter e continuità `CHAT-99` (`docs/evidence/nlcode/real-chat-20261102-183029.json`), VSIX installata e missione accettata, standalone Code-OSS ricompilato con **NLCODE-STANDALONE-ACCEPTANCE-PASS**. Restano limiti dichiarati (sotto): riparazione del ramo `repair` non ancora provata con modello reale su errore introdotto, e payload standalone che referenzia l'engine del repo (design attuale) invece di incorporarne una copia indipendente. La 1.0 non è dichiarata.
# Stato corrente — NL Coding Agent / NL Code

**Verifica aggiornata: 2 novembre 2026.** La versione **1.0 STABLE non è stata raggiunta**. Due audit indipendenti (motore e percorso team) più una verifica frontend hanno classificato lo stato reale; le affermazioni di questo file sono allineate al codice/test al momento del checkpoint, non ai documenti storici.

### Context Engine e memoria (P1, implementato)

- **Finestra dinamica per modello**: `context/window.py` ricava il budget da `num_ctx` configurato, capability ledger, config provider, cache misurata e probe Ollama `/api/show`; solo se il provider non riporta nulla usa un fallback generoso dichiarato. Non esiste più il muro fisso a 60.000 caratteri e il budget non è un limite economico o di iterazioni.
- **Thinking e output riservati**: il budget riserva esplicitamente token di output e di ragionamento; i campi `thinking`/`reasoning` già presenti nella conversazione sono conteggiati. La stima si calibra sui `prompt_eval_count`/`usage.prompt_tokens` reali del provider (EWMA per modello).
- **Compattazione senza perdita**: le turnate con scritture, risultati di test/verifica, errori, decisioni/steering e la richiesta corrente sono preservate testualmente; solo il resto viene riassunto in un digest strutturato (obiettivi, decisioni, risultati, problemi). Il digest è incrementale: non viene ricalcolato né duplicato, e copre anche le decisioni ancora presenti nel prompt così una nuova sessione può continuare.
- **Continuità**: Chat carica la cronologia in funzione della finestra, inietta il digest persistito quando omette messaggi o quando inizia una nuova sessione, e mantiene il digest nel DB (`context_summaries` con `covered_count`/`digest_json`).
- **Contesto condiviso tra agenti**: `MissionContextPack` è costruito una volta per missione (profile + file rilevanti + memoria) e ogni ruolo riceve solo la propria vista (architect/auditor: profilo+file selezionabili; developer/debugger: estratti; reviewer: decisioni+aree cambiate), evitando di duplicare l'intero contesto.
- **Memoria di progetto**: decisioni/errori/esiti delle missioni sono persistiti e richiamati per parole chiave, filtrando le memorie che riguardano file diversi dal target esplicito.

Verifica: `tests/test_context_engine.py` (finestra dinamica, calibrazione, thinking, digest critico, pack per ruolo, memoria e missione reale FakeCrewRuntime), `tests/test_chat_tools.py` (turno lungo compattato, continuità nuova sessione). Evidenza reale: missione multi-agente completata e risposta di una nuova sessione Chat con la decisione `CH-42` recuperata dal digest (stesso file di evidence).

### Code Intelligence e hook post-write (P2, implementato)

- `tools/code_intel.py`: ricerca simboli read-only (AST Python, dichiarazioni TS/JS) e diagnostica statica su file espliciti (sintassi Python, parse JSON/TOML, pyflakes se già presente). Non esegue codice del progetto.
- **LSP reale**: `lsp_diagnostics` usa `pylsp` installato nel runtime embedded (rilevato anche in `python\Scripts`), apre i documenti (`didOpen`), attende `publishDiagnostics` e restituisce file/riga/colonna. Corretto il bug di trasporto `stdout.read()` che bloccava le risposte brevi. Verificato: `undefined name` e import inutilizzato rilevati su fixture.
- Tool esposti al modello: `search_symbols`, `lsp_diagnostics`, `list_skills`, `load_skill` (Chat e missioni, anche read-only); nessuna installazione automatica: se un server manca il tool riporta `available:false`.
- Hook post-write: `_validate_stage` esegue la diagnostica statica sui file cambiati prima del tester; se fallisce, il candidato è invalidato (`promotion.invalidate_validation`), il gate resta chiuso e il feedback con file/riga entra nel retry del developer. Il ledger registra l'invocazione.
- **Riparazione autonoma verificata**: `tests/test_flow_repair.py` esegue il vero executor con il MissionFlow: il developer introduce una regressione semantica valida (somma invece di differenza), il tester determina `needs_repair`, il debugger ripara, la verifica passa, il reviewer approva e il candidato viene promosso; un secondo caso prova che un JSON/sintassi introdotto viene bloccato prima del tester. Un terzo caso prova che un errore di sintassi introdotto non raggiunge mai il progetto live.
- Verifica reale separata: missione con test **rosso preesistente** riparata da Ollama locale (candidato+oracle PASS, APPROVE, promozione, test live 2 passed) in `docs/evidence/nlcode/real-p2-repair-20261102-171636.json`.
- Limite residuo: il ramo `repair` non è ancora stato esercitato con un modello reale che introduce l'errore (solo seam scriptato + riparazione reale di un test rosso preesistente).

### Skills, subagenti e specialisti dinamici (P3, implementato)

- **Skills progressive**: `skills/discovery.py` scopre `.agents/skills`, `.nlcode/skills` e `skills/` (SKILL.md con frontmatter o JSON), espone solo nome/descrizione nel catalogo iniettato nei prompt e carica il corpo su richiesta con `load_skill`. Contenuto trattato come guida non autorizzante, bounded (60 skill, 16k caratteri).
- **Subagenti isolati**: `agents/subagents.py` esegue un agente con prompt e contesto propri (mai il transcript padre), strumenti read-only di default, e restituisce un handoff JSON strutturato (`summary/facts/decisions/risks/next_steps`).
- **Advisor dinamici**: nuovo ruolo read-only `advisor`, multiplo e distinto per nome, persistito dal Team Architect/assignment, eseguito come subagente isolato prima dello sviluppo; gli handoff sono registrati come `record_handoff` e il testo entra nelle note passate al developer. Frontend e catalogo tool aggiornati. Test: `tests/test_skills.py`, `tests/test_subagents.py`, `tests/test_advisors.py` (missione completa con 2 advisor e handoff consumati).

### Model intelligence e routing unificato (P4, implementato)

- Chat e missioni usano lo stesso `ModelRouter.auto_select` con capability misurate e risultati storici; Chat registra la decisione (`strategy`, `selected`, `selection`, `capabilities`) nella risposta e nell'evidenza.
- Una richiesta esplicita dell'utente resta prioritaria (`preserve_requested_order`); l'auto-selezione si applica solo in modalità automatica. Cloud continua a richiedere autorizzazione esplicita.
- Verificato con modello reale: `model_router.auto_select`, modello richiesto preservato, continuità di sessione (`CHAT-99`) recuperata; test dedicati in `tests/test_model_routing.py`.

### Distribuzione (P5, verificato)

- **VSIX**: ricompilata da HEAD (`.workspace/dist/NL-Coding-Agent-0.7.2.vsix`, 4,7 MB), contiene il codice advisor aggiornato; `test:webview` PASS, `test:integration` 16 PASS con 82 tool, `test:vsix` (installata su VS Code) **VSIX-INSTALLED-MISSION-PASS** con missione reale e diff.
- **Standalone Code - OSS**: ricompilato per Windows x64 (Electron 43.8.3, Code-OSS 1.145.0) in `.workspace/dist/NL Code`; script di accettazione GUI end-to-end **NLCODE-STANDALONE-ACCEPTANCE-PASS** (home, watermark, terminale, agenti, Chat reale con engine Python figlio, shutdown pulito, impostazioni preservate). ZIP portabile rigenerato (625.741.998 byte). Nota: il payload usa l'engine del repository (`engineRoot`) secondo il design attuale; non è un runtime autonomo separato.



### Checkpoint harness (2 novembre 2026)

- **Baseline**: suite completa ~8 minuti, 1366 PASS. Tre test erano rimasti indietro rispetto al codice e sono stati riallineati al comportamento voluto: contratto `core.instructions` in `test_crew_backend`, guardia statica del servizio research (la risoluzione DNS SSRF ora usa `socket.getaddrinfo`, senza I/O di rete nel servizio), preview Research (facade `research_preview` mancante).
- **Team Architect → specialisti (difetti riprodotti e corretti)**: l'auditor nel percorso sequenziale usava il modello del developer invece della route assegnata; un profilo con tool ridotti poteva azzerare la capacità di scrittura; il planner deterministico ignorava la squadra attiva (architect/auditor/debugger senza task); `team_plan` scartava/rimappava ruoli senza dirlo. Ora: route auditor risolta dal profilo, tool essenziali di scrittura ripristinati e riportati (`tool_adjustments`), architect/auditor assegnati ricevono un task pianificato, `dropped_roles`/`remapped_roles` esposti, `mission_detail`/risultato missione includono gli specialisti con `task_ids` e stato `standby` (debugger).
- **Affidabilità**: `mission_wall_time_s` (prima solo descrittivo) è imposto ai checkpoint tramite `RunControl`; developer e debugger ricevono i tool che i loro prompt promettono (`run_tests`, `run_command`, lettura per il debugger); Delete missione rimuove la copia di staging usa-e-getta ma conserva gli stage con journal di promozione non riconciliato (evidenza di recovery) e non tocca mai i file del progetto.
- **Catalogo tool**: `_TEAM_ROLE_TOOLS` include ora `git_status`/`git_diff`/`run_command`/`run_tests` coerenti con i picker dell'estensione e con `tools/crew_tools.py`; test che verifica l'assenza di opzioni morte.

### Lacune harness ancora aperte (ordinate)

1. **Code intelligence fuori dal loop**: LSP esiste in GUI/services ma non è ancora un tool del modello; la ricerca è `rglob`+substring; manca la diagnostica post-write nel ciclo di sviluppo.
2. **Skills e subagenti assenti**: nessun caricamento progressivo di skill; ruoli fissi in `agents/specs.py`, pipeline sequenziale, nessuna delega con contesto isolato (il Context Engine condiviso è il primo passo, non il runtime subagenti).
3. **Hook pre/post tool assenti**: i gate sono a fine stage; nessun lint/typecheck/diagnostica per singola scrittura.
4. **Chat resilience**: Stop Chat ora annulla la chiamata in volo, ma un turno con tool in volo interrotto da crash non è ancora journalato/recuperabile.
5. **NL Coder / distribuzione**: corretti stato connessione, Stop, drain coda, doppio invio, selezione monitor, CLOUD con conferma, `/help`/`/restore`, messaggio team. Restano: **payload standalone estratto e ZIP portabile stale** (da ricostruire), doppia `initialize` alla riconnessione, `errorMessage` sticky, identità client MCP `0.1.0`.
6. **Documentazione**: restano da consolidare `README`/`docs/README`/`NL_CODE_STANDALONE`/`FRONTEND_ARCHITECTURE` e il piano 1.0; `NEXT_SELF_BUILD_MISSION.md` ora indica P2.


### URL fetch e ricerca web

NL Coder riconosce URL nei messaggi e nei transcript, recupera le pagine dalla Chat e passa il contenuto
come dato non attendibile con URL e titolo persistiti nell'attachment. Per le domande senza URL,
`web_search` esegue ricerca web generica via Bing HTML e `fetch_url` consulta le pagine
pertinenti; i risultati includono link citabili. Il motore fornisce trasporti HTTP bounded per fetch
generico, ricerca e GitHub REST read-only (repository, README, tree); i contenuti allegati vengono
riproposti nei follow-up Chat entro un budget e restano non attendibili. Il fetch generico usa
controllo DNS su indirizzi privati/reservati e rivalutazione dei redirect; il permesso NETWORK di
Project Access governa nello stesso scope ricerca e fetch. Il profilo Research resta una scelta
distinta che governa l'auto-approvazione; la query di ricerca è inviata a Bing e i relativi
risultati restano non fidati. La GitHub REST lookup condivide il grant NETWORK e Research approval.
Il pinning dell'indirizzo di connessione dopo la risoluzione DNS resta una limitazione esplicita.

### Confine delle interfacce e classificazione delle modifiche

Il prodotto mantiene **un solo motore Python condiviso e due interfacce supportate**: NL Coder VSIX
per VS Code Insiders e NL Code standalone basato su Code - OSS. La GUI Python/PySide6 è legacy:
il codice e i test preesistenti restano conservati, ma non fanno parte del normale sviluppo,
verifica o acceptance, salvo richiesta esplicita.

| Area | Modifiche recenti | Trattamento |
|---|---|---|
| Motore condiviso | `nl_coding_agent/agents/`, `app/`, `models/operational_probes.py`, `persistence/missions.py`, `research/transport.py`, `config/models.yaml`, test backend selezionati | Conservare e verificare una volta; entrambe le UI lo consumano. |
| NL Coder VSIX | `frontend/src/`, `frontend/media/`, `frontend/test/`, packaging e test installati | Compilare, testare e reinstallare la VSIX per acceptance. |
| GUI Qt legacy | `nl_coding_agent/gui/`, `tests/test_chat_panel.py`, `tests/test_gui_panels.py`, `tests/test_recent_ui_regressions.py` | Conservare senza ulteriore sviluppo o test ordinario; i relativi PASS storici non accettano NL Code Code - OSS. |
| Documentazione/configurazione | README e documenti architetturali/modelli/chat, `config/models.yaml` | Allineare al confine sopra; la configurazione modelli resta condivisa. |

`ParcoTest/` è materiale preesistente non classificato né modificato in questo ciclo.

### Difetti 0.7.2 verificati e corretti

- FastMCP `1.30.0` chiamava direttamente nell'event loop i tool sincroni. La scansione/inferenza di `team_plan` bloccava così la sessione MCP e faceva scadere contemporaneamente anche richieste rapide. Gli handler sincroni del server ora vengono eseguiti in worker thread.
- `team_plan` usava inoltre un retry locale di 180 s + 270 s, oltre il timeout client di 240 s. Ora fa un solo tentativo bounded a 90 s e restituisce/salva la squadra deterministica con la causa del fallback invece di lasciare scadere il tool.
- Team Architect materializzava e ordinava l'intero albero del progetto prima di applicare i limiti del prompt. La raccolta ora pota runtime, output, cache, dati utente, vendor staged e repository annidati, con limiti espliciti alla traversata.
- Gli aggiornamenti della Queue erano read-modify-write non sincronizzati. Le operazioni sono ora protette da lock per progetto e il frontend impedisce drain duplicati; `/team` espone lo stato occupato e rilascia correttamente la coda.
- Verifiche: `26 passed` nei test mirati Python; `npm run compile` e packaging VSIX passati; acceptance della VSIX installata passata con Team Architect e tre richieste MCP concorrenti.
- Vision: probe locale reale `qwen3.5:9b` riconosce la fixture PNG (`RED`); il test MCP registra screenshot PNG come attachment; l'acceptance VSIX verifica Ctrl+V→store e handoff non fidato. Il composer supporta anche `@file` con ricerca workspace e attachment via MCP.
- ASR: `J:\ZLinkdaC\Qwen3ASR` è rilevato in-place con `qwen3-asr-cli.exe`; il catalogo esclude il GGUF forced-aligner. Faster-Whisper 1.2.1 e Vosk sono disponibili nel runtime; whisper.cpp è utilizzabile registrando il CLI esterno. Il pannello offre download esplicito di Vosk small IT/EN e Faster-Whisper tiny/base/small con NETWORK; non rimuove/sovrascrive modelli esterni.
- Acceptance VSIX Chat: Team Architect concorrente, salvataggi/immissione Queue, selezione modello, allegati, fetch/history e shutdown PASS. La missione multi-file installata completa con APPROVE, candidate/oracle PASS e promozione.

### Team Supervisor e gestione missioni (2 novembre 2026)

- `Generate team` salva una squadra attiva per progetto senza duplicare i ruoli supportati dal Supervisor. Le route `provider/model`, le istruzioni e i tools personalizzabili vengono applicati agli stage; Project Access resta l'unica policy dei permessi.
- La Chat consente selezione filtrata singola/multipla, Stop cooperativo, Archive e Delete distinti. Il backend applica le azioni in transazione; Delete riallinea Goal/milestone e riferimenti DB senza cancellare i file del progetto.
- Delete di missioni pending/terminali richiede solo conferma e il permesso globale `DELETE` del Project Access, non l'abilitazione dell'esecuzione agentica; per una running resta obbligatorio lo stop cooperativo.
- Verifica della correzione mission-delete: 4 test Python mirati PASS, compilazione TypeScript e test webview PASS; acceptance della VSIX installata in profilo isolato PASS per eliminazione singola e batch di missioni pending con execution disabilitato. La prova copre il server MCP read-only con `DELETE` concesso/revocato e il controller installato dopo conferma.
- Verifiche: 87 test Python mirati PASS; `npm --prefix frontend run compile` e `test:webview` PASS; test extension-host VS Code PASS; la VSIX 0.7.2 corrente è stata reinstallata nel profilo Insiders. È necessario ricaricare la finestra per usare i moduli appena installati.
- Limite di acceptance: la missione host con Ollama reale è rimasta `running` sul primo developer task senza tentativo completato prima della chiusura dell'host; non la considero una prova riuscita. Il ciclo team→persistenza→invocazione developer/tester/reviewer, modelli, istruzioni e tools è invece coperto da una missione isolata con `FakeCrewRuntime` e da test route/provider permission-gated.

### GUI PySide6 legacy: team e missioni (lavoro storico del 2 novembre 2026)

Le note e i test qui sotto documentano modifiche mantenute nel repository, ma riguardano
esclusivamente l'interfaccia Qt legacy. Non sono una prova di NL Code Code - OSS né un target
per i prossimi interventi.

- `AgentsPanel` riceve il progetto corrente, scopre le route `provider/model` in worker thread, genera una proposta Team Architect, la mostra per conferma e la assegna attraverso `assign_project_team`. La squadra attiva, i modelli e i profili vengono indicati nel pannello e nel dialogo degli specialisti; la rigenerazione aggiorna i ruoli esistenti. Il form specialisti non espone più permessi duplicati: Project Access resta l'unica policy, mentre Tools restano configurabili.
- `TaskBoardWidget` è ora project-scoped e offre ricerca, filtro stato/archivio, selezione multipla e selezione delle missioni filtrate del progetto corrente. Stop è cooperativo; Archive e Delete sono azioni distinte, confermate e batch. Pending si elimina senza archiviazione preliminare; per gli ID running selezionati Archive/Delete attendono il safe stop senza bloccare il thread GUI.
- Il Delete aggiorna la Chat con l'evento, ricarica Task Board e Goals e azzera nell'Inspector la missione rimossa; il backend riallinea Goal/milestone e record DB senza cancellare i file del progetto.
- Verifiche GUI standalone: `22 passed` tra `test_gui_panels.py`, `test_recent_ui_regressions.py` e `test_i18n_coverage.py`; backend missioni/team: `34 passed`. La prova Stop GUI registra la richiesta cooperativa e simula il passaggio al terminale `interrupted`: non è una missione live con un modello fermata dal Supervisor. Generate team GUI usa un risultato Team Architect stub per verificare thread, anteprima, assegnazione reale, profili attivi e deduplicazione; non dimostra l'inferenza Team Architect live da questa finestra.

Le note successive descrivono il checkpoint storico del 30 ottobre 2026 (`1655cbb`) e i problemi osservati allora; non sono lo stato corrente dei percorsi Queue/Team Architect.

## Architettura reale riportata e già verificata in modo parziale

- **Motore condiviso** in `K:\AI\NL Coding Agent`, Python embedded; CrewAI runtime, Supervisor, missioni persistite SQLite, file staging, candidate/oracle verification, reviewer e promozione.
- **NL Coder**: estensione VS Code Insiders `nlcodingagent.nl-coding-agent` 0.7.2, Chat+Mission+Engine e backend MCP. La VSIX corrente è installata nel profilo utente; ricaricare la finestra VS Code per sostituire i moduli già caricati in memoria.
- **NL Code standalone** Windows: workbench basato su Code - OSS e seconda interfaccia supportata; deve usare una build portatile con la stessa VSIX NL Coder accettata in VS Code Insiders.
- `03a6a25`: team proporzionale, quattro ruoli su test isolato, handoff e snapshot modelli; missione test con due file e promozione.
- `1655cbb` (WIP): multi-subtask developer nello stesso candidato; Flow `@start/@router/@listen`, ramo repair→verify; strumenti controllati file/shell/Git/test/Research, discovery MCP; aggregazione storico e `auto_select`; default Chat/MCP `pipeline="flow"`. Test riportati: 30 focalizzati, 41 Supervisor, una missione Flow semplice PASS. **Il Flow repair con errore reale, il resume multi-modulo e il tool routing auto live NON sono stati validati**.

## Problemi osservati direttamente durante l'uso di NL Coder

1. **Chat non dimostra uso autonomo del filesystem**: Qwen dice di non poter aprire file; può riassumere `README.md` quando esplicitamente allegato. Non scambiare l'autodescrizione del modello per il vero system prompt: verificare `nlc_converse`, tool schemas, trace e risultati.
2. **Un messaggio per volta**: frontend blocca invio mentre `busyChat`; mancano queue persistente, steering durante lavoro, cancellazione reale delle generazioni e stati di resume chiari.
3. **Sessioni storiche**: UI non offre gestione multiconversazione né una vista di archivio/purga; alcune conversazioni pregresse risultano non trovate.
4. **Missioni accumulate**: NL Coder Chat offre filtri e azioni missione; i controlli Task Board della GUI Qt sono legacy e non costituiscono acceptance per NL Code.
5. **Engine Settings poco operative**: elenco 21 modelli Ollama e ruoli, ma la configurazione esposta appare read-only o confusa; il backend può concedere WRITE/EXECUTE mentre la sessione GUI è read-only (livelli distinti, da spiegare).
6. **Onboarding motore**: VSIX installata in un profilo Insiders non trova l'engineRoot finché l'utente non lo inserisce manualmente. È emerso un errore di salvataggio `settings.json`: diagnosi sul file JSONC reale, senza modifiche indiscriminate.
7. **Contesto editor / attachment**: il file allegato viene letto, ma il comportamento percepito dell'utente è ripetitivo; occorre distinguere file attivo, snapshot, allegato esplicito per turno e storage di contenuti già letti.
8. **Scheda estensione**: icona logo presente, ma `No README available`. Titoli/esperienza ancora troppo tecnici.
9. **Standalone**: la GUI PySide6 ora copre team e missioni, ma la build `NL Code.exe` indicata sopra resta quella precedente; identità, palette e workbench NL originali non sono ancora completati.
10. **Warnings `star-activation`**: provenienti da `git-base`, `git` e test packages upstream Code - OSS; non sono in sé bug di NL Coder. Non toccare alberi `.build`/`out` per nasconderli.

## Bloccanti del prossimo ciclo

- Riprodurre e correggere regressioni del planner multi-task, soprattutto il test precedente che assume un unico task developer.
- Dimostrare da una chat installata **lettura reale di file senza upload**, tool call con telemetry e risposta verificabile; eventuali errori del system prompt misurati e non indovinati.
- Colmare Flows real repair/recovery, handoff consumati da ruoli distinti, modello auto con capability probe reali.
- Aggiungere gestore conversazioni, queue/steer/stop, impostazioni editabili, pulizia dati selettiva.
- Accettare NL Code Code - OSS con la VSIX corrente e lo stesso engine; validare missione multi-modulo con errore forzato e resume, quindi completare i gate 1.0.

## Cosa NON risulta completato

- Nessuna prova di notte autonoma sicura su lavoro complesso; nessuna accettazione full multi-modulo da zero.
- Nessuna dimostrazione di team liberamente arbitrari o parallelismo sicuro; il planner usa principalmente path dichiarati.
- Nessun supporto Linux/macOS dichiarabile stabile senza runtime nativi e test reali. I launcher
  POSIX e i pacchetti source-beta non sono build standalone distribuibili; non pubblicarli come
  release native. La prossima missione è descritta in [NEXT_SELF_BUILD_MISSION.md](NEXT_SELF_BUILD_MISSION.md).
- Nessuna convalida della 1.0 da profilo standalone pulito e dall'utente.

Riferimenti: [WIP](NL_CODE_1_0_WIP.md), [piano unico 1.0](NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md), [gates](08_ACCEPTANCE_GATES.md), [evidenza team](evidence/frontend/team-mission-evidence.json).

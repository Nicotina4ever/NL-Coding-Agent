# NL Chat: agente operativo, contesto, queue, conversazioni

## Problema osservato

Il modello Qwen localmente può dichiarare «non posso leggere i file», ma riassume un README quando viene allegato. Questo **non prova** un system prompt restrittivo: il modello può inventare la propria descrizione. La Chat invoca `nlc_converse`; una missione passa da `start_mission` al Supervisor. La connessione a MCP/Ollama da sola non dimostra tool calling agentico nella Chat.

**Gate prioritario**: in read-only, richiedere `read_file` sul workspace *senza allegato*, vedere traccia tool vera e confrontare il testo con il file sul disco; poi testare una missione con WRITE esplicito e controlli indipendenti.

## Strumenti Chat

- Concedere strumenti READ: lista file, lettura limitata, ricerca testo/codice, stato Git, diff, diagnostica editor, progetto, missioni, conversazioni.
- Consentire EXECUTE/WRITE soltanto via broker, scope e autorizzazione; nessuna libertà di shell per puro prompt. Eseguire via servizi esistenti, non un secondo agente di esecuzione nascosto nella webview.
- Registrare la **chiamata reale**, nome tool, scope, esito, durata e artifact; non includere dati segreti nei log. Modelli senza tool calling nativo devono usare una strategia validata o dare indicazione di incompatibilità, non fingersi tool-enabled.
- Read-only significa impossibilità di scrittura/esecuzione, non di lettura. L'utente vede READ/WRITE/EXECUTE/NETWORK/CLOUD e la differenza fra grant backend e toggle sessione.

## Contesto per turno

- Workspace e progetto = riferimento costante, non copia integrale a ogni messaggio.
- Editor aperto / selezione = riferimento leggero, snapshot soltanto su richiesta o quando serve e confermato nel composer.
- Attachment esplicito = il composer lo disassocia dopo l'invio, ma il riferimento resta nel messaggio persistito. I follow-up possono riusare i contenuti testuali degli attachment recenti entro un budget limitato, sempre come dati non fidati e solo per lo stesso progetto.
- Ctrl+V nel composer Chat acquisisce immagini/screenshot come attachment PNG nel medesimo store; il composer non apre una seconda interfaccia. Il Model Hub può misurare `vision` con una fixture locale. Solo un modello con capability `vision=measured`, selezionato dal ModelRouter, riceve i byte; la sua analisi passa agli altri agenti come handoff testuale non fidato. `unknown`, `declared` e `unavailable` non autorizzano l'invio. Cloud richiede l'escalation e i permessi esistenti.
- `@` nel composer apre la ricerca dei file del workspace; selezionare un risultato inserisce `@percorso/relativo` e allega lo snapshot tramite l'ingestione MCP già esistente. `.git`, runtime, data, build e vendor staging sono esclusi. Il riferimento resta testo nel prompt e il contenuto viene letto dal tool di attachment, non da una seconda cache UI.
- Se non esiste una route Vision misurata o l'analisi fallisce, Chat dichiara che l'immagine non è stata interpretata e non attribuisce contenuti visivi al modello testuale.
- Niente reinserimento automatico di un README da 17 KB ad ogni domanda; lettura incrementale on-demand quando il modello ne ha bisogno.
- File condivisi via Tool/Research sono dati *non fidati*, non istruzioni al Supervisor.
- La ricerca web generica è disponibile nella Chat tramite `web_search` (provider Bing HTML) e `fetch_url`: per una domanda di ricerca cerca risultati, consulta le pagine pertinenti e cita gli URL effettivamente letti. Gli URL HTTP(S) inseriti nel messaggio vengono anche recuperati prima della risposta quando consentito; l'attachment include URL canonico e titolo, così i follow-up possono recuperare la provenienza. Ricerca e fetch passano dal Project Access `NETWORK` e dal profilo Research; query, risultati e contenuti sono dati non fidati.
- I link GitHub pubblici restano leggibili tramite l'investigator REST GET dedicato: repository, README e contenuti. Per l'ispezione del codice GitHub la Chat usa `github_lookup`; non sostituisce la ricerca/fetch web generica. La conversazione ricarica gli attachment di ricerca persistiti nei follow-up e non confonde HTML GitHub con contenuti repository.

## Sessioni e storico

Vere **conversazioni multiple per progetto** con session_id, titolo, modello, ultima attività, ricerca, archivio, rinomina, ripresa dopo riavvio, copia/export; riuso del database engine se già contiene messaggi. Migrazioni additive senza perdere chat storiche. Non confondere una history piatta per progetto con sessioni. Distinguere le conversazioni dai task/missioni persistenti (servono al resume; non devono ingombrare la Chat).

## Queue, steering, stop e resume

- L'utente può scrivere mentre l'LLM lavora: enqueue più messaggi con modifica/riordino/rimozione prima dell'esecuzione; il `busyChat` attuale non deve rifiutare l'input.
- **Steering**: un nuovo vincolo/istruzione raggiunge Supervisor al prossimo checkpoint sicuro, persistito e riscontrato nella timeline; non basta un messaggio in una conversazione parallela.
- **Stop generation**: interrompe realmente provider/inferenza dove supportato; **Stop mission**: arresto cooperativo con persistenza, safe checkpoint, output parziali, revival esplicito. Distinguere i due stati e le loro limitazioni.
- Persistenza coda, avvio del progetto in un'altra finestra, riavvio extension host, shutdown e recupero; nessun invio perso e nessun doppio write.

## Proof-of-use nella GUI

Mostrare tool calls eseguite, agent role/model, file letti/creati, candidate diff, test candidate/oracle, handoff, review, motivazione di routing e costi se presenti. La Chat deve creare/gestire goal e Todo attraverso gli stessi servizi, senza limitarsi a scrivere testo. Se mancano permessi, proporre la richiesta corretta senza concederseli.

## Fallback locale/cloud (1 novembre 2026)

`_resolve_chat_provider` prova prima la route richiesta. Se è locale e fallisce, può usare `fallback_cloud` solo quando la politica è abilitata e CLOUD è concesso. Se è cloud e il permesso manca, usa la route locale chat/developer. La selezione esplicita di un modello cloud nella GUI attiva il grant CLOUD di progetto; nessun modello può concederselo da solo. Il fallback cloud automatico resta disattivato finché l'owner non abilita la politica.

## Fallback operativo (1 novembre 2026, dettaglio)

- Un timeout locale viene ritentato una volta con deadline maggiore; non è di per sé un errore e non autorizza il cloud.
- Dopo un errore locale reale, la catena prova gli altri ruoli/modelli locali prima del cloud.
- Un cloud con quota esaurita, 429/401/403 o endpoint indisponibile non viene ritentato; si passa a un'alternativa locale autorizzata.
- La classificazione cloud usa provider/endpoint (`openai_compatible` remoto) oltre al token nel nome del modello.
- Cambiando modello la storia messaggi/tool resta la stessa; viene aggiunta solo una nota di sistema sul fallback, senza perdere contesto o ripetere tool completati.

## Profili di accesso e team (1 novembre 2026)

- Le permission dei singoli specialisti non sono più il punto di controllo: è stato introdotto un profilo di progetto (`read-only`, `workspace-write`, `full-access`, `auto-review`) applicato a tutti gli agenti.
- `auto-review` registra anche il profilo trusted e mantiene separati cloud/delete.
- `Generate team` propone specialisti usando il catalogo provider/modelli dinamico; i ruoli eseguibili dal Supervisor sono architect, developer, debugger, reviewer e auditor.
- La squadra viene assegnata al progetto corrente: una nuova generazione aggiorna gli stessi ruoli invece di duplicarli, e la UI distingue gli specialisti attivi. Route `provider/model`, istruzioni e tools vengono applicati all'invocazione; i tools restano personalizzabili e limitati a quelli disponibili per lo stage. Project Access resta l'unica policy operativa: non esistono permessi duplicati per specialista.
- `Add llama.cpp` registra il provider OpenAI-compatible e usa `/v1/models` per il discovery quando il server è attivo.

## Gestione missioni dalla Chat

- La lista missioni e il dettaglio restano nel dashboard esistente. Filtri di stato/archivio e "select filtered" permettono selezione singola o multipla per il solo progetto corrente.
- Stop, Archive e Delete sono azioni distinte. Stop è cooperativo; Archive e Delete chiedono conferma e attendono l'arresto delle missioni running prima di procedere. Le pending e le missioni terminali sono eliminabili senza avviarle né archiviarle.
- Eliminare missioni non richiede di abilitare l'esecuzione agentica: dopo la conferma, il Project Access globale deve concedere `DELETE`. Per una missione running resta necessario lo stop cooperativo.
- Archive conserva la missione; Delete rimuove record e collegamenti DB senza eliminare file del progetto. Goal e milestone vengono riallineati; lo staging resta gestito dallo Storage Manager.
- Le operazioni batch sono transazionali e rifiutano una missione ancora running, anche in caso di race dopo la richiesta di stop.

## GUI PySide6 legacy — Agents e Task Board (lavoro storico del 2 novembre 2026)

Questa sezione documenta soltanto l'interfaccia Qt legacy. Il codice e i test restano conservati,
ma non sono target ordinari di sviluppo/acceptance e non descrivono NL Code, che è il workbench Code - OSS.

- L'Agents panel riceve il progetto corrente e scopre dinamicamente le route `provider/model` in un worker. Generate team esegue Team Architect senza bloccare la GUI, mostra proposta, modelli e Tools per conferma e persiste la squadra con `assign_project_team`. La schermata mostra i profili attivi del progetto; le rigenerazioni aggiornano gli specialisti per ruolo invece di crearne copie.
- I profili personalizzati mantengono Tools modificabili nelle opzioni avanzate, ma non hanno più un campo Permissions: i permessi effettivi vengono dal solo Project Access globale.
- Il Task Board è limitato al progetto aperto e consente filtro testo/stato/archivio, selezione multipla e selezione delle missioni filtrate. Una missione pending può essere archiviata o eliminata direttamente dopo conferma. Stop è un'azione separata e cooperativa; Archive/Delete su missioni running attendono il safe checkpoint senza bloccare la GUI.
- La cancellazione batch usa il servizio transazionale esistente, non elimina sorgenti o staging, aggiorna Task Board e Goals e mostra un evento nella Chat; l'Inspector torna al riepilogo progetto se stava mostrando una missione cancellata.
- La copertura GUI usa `Fake`/stato isolato per verificare persistenza, deduplicazione, selezione e attesa del checkpoint. Non è una prova di Team Architect live o di arresto di un Supervisor reale dalla GUI.

## NL Code 0.7 (1 novembre 2026)

- Accesso progetto sotto la Chat, default Auto review; cloud autorizzato non bloccato; le cancellazioni passano da `da_eliminare` con manifest.
- Team Architect sceglie un modello analista esplicito, legge documentazione/progetto e crea un numero dinamico di specialisti.
- `/plan` produce un piano JSON e nessuna missione; `/apply` crea il Goal con milestone e non esegue.
- `/checkpoint`, `/checkpoints`, `/restore` separano il ripristino file dal rewind conversazione; i progetti Git usano ref nascosti.
- Script `scripts/nlcode/autopilot.py` e `scripts/nlcode/mcp_smoke.py`.

## NL Coder 0.7.2: Vision e concorrenza (2 novembre 2026)

- La capability Vision viene misurata dal Probe del Model Hub e registrata nel capability ledger esistente.
- Incolla PNG/screenshot con Ctrl+V nel composer Chat; il chip attachment riporta il tipo Vision e resta rimovibile.
- Il modello Vision è uno specialista per-turno: riceve l'immagine solo con capability misurata e lascia un handoff testuale al modello Chat/agentico selezionato. Nessun requisito Vision è imposto agli altri ruoli.
- Acceptance installata: PNG clipboard → attachment MCP; Team Architect completa mentre mission detail, Queue e role settings sono concorrenti; Chat e history vengono persistiti.
- Team Architect usa un solo tentativo locale bounded a 90 s; se l'analisi scade, salva il team deterministico e mostra la causa, senza superare il timeout MCP con un secondo retry lungo.
- Il messaggio iniziale Chat riassume `@file`, Ctrl+V, `/team`, `/mission` e Dictation per rendere scopribili i flussi esistenti.

## ASR locale e modelli

- Engine supportati dal catalogo: Faster-Whisper, Vosk, Qwen3-ASR e whisper.cpp; la disponibilità runtime è indicata per engine. I menu separano engine e relativi modelli, includendo i download disponibili nello stesso menu dei modelli.
- Una cartella esterna con modelli ASR supportati può essere aggiunta da Engine/Speech e viene registrata in-place; i file non vengono copiati, sovrascritti o eliminati. I forced aligner non compaiono come modelli ASR.
- I download Vosk/Faster-Whisper richiedono grant `NETWORK` e conferma; vengono salvati sotto `data/speech/models`, verificano l'archivio e non sovrascrivono/eliminano modelli.

## Verifica 0.7.0

- `scripts/nlcode/mcp_smoke.py` passes against the project-bound server (72 tools, project_context and engine_settings callable).
- `scripts/nlcode/autopilot.py --dry-run` produced a plan for ParcoTest without changing project files.
- Git checkpoint capture/restore verified on an isolated repository; file restore and conversation rewind remain separate operations.
- Installed VSIX acceptance: mission developer→tester→reviewer→promotion PASS.

## Note operative 0.7.0

- Avvio MCP smoke: `python\python.exe scripts\nlcode\mcp_smoke.py --project <cartella>`.
- Autopilota: `python\python.exe scripts\nlcode\autopilot.py --project <cartella> --objective "<obiettivo>" --model <provider/modello> --dry-run` (piano), poi senza `--dry-run` per creare il Goal e avviare il Supervisor.
- Checkpoint: `/checkpoint`, `/checkpoints`, `/restore <id>` oppure History → File checkpoints.

## Auto review 0.7.1

- Auto review grants the project cloud-inference capability and the trusted review profile; cloud actions are not blocked by the profile.
- Direct delete remains denied; project deletions are moved to `da_eliminare` with a manifest.
- Autopilot recovery is bounded by `autopilot_supervise.py`; create `STOP` in the job directory to stop before the next retry.

### ParcoTest autopilot smoke (2026-11-01)

- Job: `.workspace/jobs/autopilot-20261101-155503`.
- Piano applicato, Goal #1 attivato, Supervisor avviato due volte dal wrapper di recovery.
- Blocco esterno: `data/selfbuild_state.json` non contiene un entry per ParcoTest; il Supervisor richiede `scripts/migrate_project_root.py --apply` prima del self-build. Nessuna modifica applicativa a ParcoTest.

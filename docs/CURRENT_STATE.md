**Checkpoint 2 novembre 2026 — estensione 0.7.2.** Chat e missioni condividono il motore Python; la Chat supporta Queue persistente, Missioni, Team Architect, attachment multimodali con Ctrl+V e handoff Vision capability-aware. Cloud resta opt-in; modelli senza capability Vision misurata non ricevono byte immagine. Stato dettagliato sotto.
# Stato corrente — NL Coding Agent / NL Code

**Verifica aggiornata: 2 novembre 2026, estensione NL Coder 0.7.2.** La versione **1.0 STABLE non è stata raggiunta**. Il test VSIX installato in profilo isolato ha completato Team Architect mentre `mission_detail`, rimozione Queue e salvataggio ruolo erano concorrenti; Chat, attachments, fetch autorizzato, history e shutdown hanno superato la stessa acceptance.

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

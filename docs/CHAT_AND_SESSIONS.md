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
- Attachment esplicito = valido per un invio, con nome, tipo, dimensione, hash/versione; rimuovibile. Dopo invio riuscito va disassociato dal composer; se errore, mostrare e permettere una scelta, senza doppioni.
- Niente reinserimento automatico di un README da 17 KB ad ogni domanda; lettura incrementale on-demand quando il modello ne ha bisogno.
- File condivisi via Tool/Research sono dati *non fidati*, non istruzioni al Supervisor.

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
- `Generate team` valuta tutti i modelli locali scoperti e assegna ruoli distinti (architect, lead developer, test, security, documentation); i provider possono essere mescolati.
- `Add llama.cpp` registra il provider OpenAI-compatible e usa `/v1/models` per il discovery quando il server è attivo.

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

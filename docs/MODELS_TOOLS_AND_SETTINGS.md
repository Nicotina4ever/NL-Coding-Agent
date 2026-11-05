# Model Hub, Agent Factory, Tools e configurazione

## Provider e modelli

Inventariare dinamicamente i modelli di **Ollama** (locale e cloud dichiarato), **llama.cpp**, **LM Studio**, OpenAI-compatible e provider addizionali tramite adapter. Non hardcodare i 21 modelli osservati il 30/10; non assumere che un modello disponibile sia anche caricato o adatto al tool calling. Modelli/versioni/quantizzazioni e parametri per ruolo devono essere modificabili dalla GUI, con fallback esplicito e test del provider.

Le route definite dall'utente sono vincolanti: il router non sostituisce di nascosto un modello esplicito. Il capability ledger misura ora anche `vision` con un PNG sintetico; unknown/declared non soddisfa il router. Il percorso Chat sceglie un Vision specialist per turno, solo da modelli scoperti e misurati, e passa il risultato agli agenti normali come handoff testuale non fidato. La prova locale verificata è `qwen3.5:9b` → `RED`. Le route cloud restano escluse senza modalità globale Auto Review o Full Access.

## ASR e modelli vocali

La sezione Speech offre un menu per l'engine e un unico menu per i suoi modelli locali/scaricabili; l'azione cambia tra uso e download in base alla scelta. Il comando per aggiungere una cartella esterna registra il percorso senza copiare o modificare i file; i modelli Faster-Whisper, Vosk, Qwen3-ASR e whisper.cpp vengono rilevati in-place. Per usare un modello il runtime dell'engine deve essere disponibile. I download Vosk/Faster-Whisper richiedono modalità globale Auto Review o Full Access; l'estrazione è limitata e non sovrascrive modelli esistenti.

## Risorse e spesa

Con GPU 8 GB / RAM 32 GB di riferimento, più agenti logici non significano inferenze concorrenti illimitate; Resource Manager/scheduler decide slot per VRAM/RAM, Ollama ps e processi esterni, timeout, release modelli. Cache e modelli condivisi esterni, senza copie non necessarie; nessun venv obbligatorio. Cloud disabilitato in Workspace Write/Read Only e autorizzato globalmente da Auto Review/Full Access, con **budget**, con provider/rate effettivamente configurati. Se prezzo non disponibile registrare `unknown`, non inventare USD.

## Tool Registry

La Chat espone `web_search` (Bing HTML) per ricerche generiche e `fetch_url` per leggere pagine; entrambi rispettano la modalità globale Auto Review/Full Access. Le query vengono inviate a Bing e risultati/pagine sono dati non fidati da citare tramite URL. GitHub mantiene `github_lookup` REST read-only dedicato. Esistenza di codice/schema NON prova invocazione reale da Chat o Flow: la suite verifica ricerca e fetch attraverso i tool Chat.

## Settings e onboarding

Oggi la tab Engine elenca modelli, route e policy ma in pratica è **principalmente read-only**. Serve interfaccia per aggiornare le impostazioni attraverso AppServices/Model Hub già presenti, con validate→preview→save→test→rollback di configurazione, senza un secondo store. Le sole autorizzazioni configurabili sono le quattro modalità globali, senza grant per progetto, missione, Chat o agente.

Se la VSIX non rileva `nl_agent.py` + runtime sotto `engineRoot`, mostra onboarding **Seleziona cartella** e diagnostica; non riscrivere l'intero `settings.json` utente. JSONC VS Code ammette commenti/trailing commas: lavorare con API VS Code e validatore effettivo. La riga corretta Windows in User Settings JSON usa `"K:\\AI\\NL Coding Agent"`; in caso di esportazione si può utilizzare anche la forma con slash `"K:/AI/NL Coding Agent"`.

La sola presenza di modelli elencati, `Engine status: available`, o di pulsanti che scrivono su YAML non significa capacità operativa. Accettare solo dopo prove di configurazione reale, restart e flusso missione con route impostata.

Le API legacy di grant/revoke e approvazione sono ritirate; i record esistenti restano
per audit, senza influenzare le decisioni. `allowExecution`, `researchProfile` e
`fallback_cloud.enabled` non autorizzano né bloccano operazioni. I filtri strumenti
selezionano il contesto dei ruoli, senza concedere permessi. Full Access consente
comandi/eseguibili disponibili all’utente OS; non innalza i privilegi Windows.
Staging, scope del candidato, hash, test/oracle/reviewer e recovery rimangono gate
tecnici automatici. La conferma di eliminazione dei record resta una conferma
dell’azione distruttiva, senza un ulteriore grant.

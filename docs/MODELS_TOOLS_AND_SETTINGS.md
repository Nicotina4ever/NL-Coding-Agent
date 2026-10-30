# Model Hub, Agent Factory, Tools e configurazione

## Provider e modelli

Inventariare dinamicamente i modelli di **Ollama** (locale e cloud dichiarato), **llama.cpp**, **LM Studio**, OpenAI-compatible e provider addizionali tramite adapter. Non hardcodare i 21 modelli osservati il 30/10; non assumere che un modello disponibile sia anche caricato o adatto al tool calling. Modelli/versioni/quantizzazioni e parametri per ruolo devono essere modificabili dalla GUI, con fallback esplicito e test del provider.

Le route definite dall'utente sono vincolanti: il router non sostituisce di nascosto un modello esplicito. `auto_select()` al checkpoint `1655cbb` usa risultati storici da `task_attempts.metadata_json`, ma **non è ancora validato** con capability probe live. Classificare per task/competenze e hardware: esiti verified, latenze, token, review, errori, contesto effettivo, supporto tool/structured output. Evitare benchmark inventati e premi per test triviale. Se pochi campioni, preferire scelta controllata/benchmark mirati.

## Risorse e spesa

Con GPU 8 GB / RAM 32 GB di riferimento, più agenti logici non significano inferenze concorrenti illimitate; Resource Manager/scheduler decide slot per VRAM/RAM, Ollama ps e processi esterni, timeout, release modelli. Cache e modelli condivisi esterni, senza copie non necessarie; nessun venv obbligatorio. Cloud disabilitato di default, attivabile per progetto/ruolo e **budget**, con provider/rate effettivamente configurati. Se prezzo non disponibile registrare `unknown`, non inventare USD.

## Tool Registry

I tool dichiarati da DeepSeek al checkpoint: `read_file`, `list_dir`, `write_file`, `patch_file`, `run_tests`, `run_command` (argv allowlist e `shell=False`), `git_status`, `git_diff`, `research_fetch_url` gated, `mcp_list_tools` con client esistente. Esistenza di codice/schema NON prova invocazione reale da Chat o Flow. `mcp invoke` richiede grant/approvazione: mantenere broker unico. Separare permessi READ, WRITE, EXECUTE, DELETE, NETWORK, CLOUD e tool esterni con trust e scope specifici.

## Settings e onboarding

Oggi la tab Engine elenca modelli, route e policy ma in pratica è **principalmente read-only**. Serve interfaccia per aggiornare le impostazioni attraverso AppServices/Model Hub già presenti, con validate→preview→save→test→rollback di configurazione, senza un secondo store. La UI deve distinguere modalità `read-only` dell'estensione e permessi backend grant di un progetto.

Se la VSIX non rileva `nl_agent.py` + runtime sotto `engineRoot`, mostra onboarding **Seleziona cartella** e diagnostica; non riscrivere l'intero `settings.json` utente. JSONC VS Code ammette commenti/trailing commas: lavorare con API VS Code e validatore effettivo. La riga corretta Windows in User Settings JSON usa `"K:\\AI\\NL Coding Agent"`; in caso di esportazione si può utilizzare anche la forma con slash `"K:/AI/NL Coding Agent"`.

La sola presenza di modelli elencati, `Engine status: available`, o di pulsanti che scrivono su YAML non significa capacità operativa. Accettare solo dopo prove di configurazione reale, restart e flusso missione con route impostata.

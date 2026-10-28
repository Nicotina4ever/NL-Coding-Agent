# Master checklist — unica sorgente di backlog

> **Importante:** caselle inizialmente non selezionate = **non verificate da questo pacchetto**, NON necessariamente assenti nel codice. L'agente deve confrontarle con repository, SQLite e test prima di spuntarle. Ogni checkbox richiede prova salvata con percorso/comando/esito/data/commit o diff. Non spuntare sulla base di un rapporto testuale.

## P0 — Self-build autonomo (blocco di consegna)

- [ ] **P0-01** Audit repo e stato Git iniziale, senza perdere modifiche. → [SPEC-02](specifiche/02_SELF_BUILD_E_RECOVERY.md), [SPEC-15](specifiche/15_SICUREZZA_E_PRIVACY.md)
- [ ] **P0-02** Test runtime embedded, CrewAI, CLI, GUI e pytest; documentare errori reali. → [SPEC-19](specifiche/19_TEST_MATRIX_E_GATE.md)
- [ ] **P0-03** File tools read/search/create/patch scoped e Git diff reale. → [SPEC-02](specifiche/02_SELF_BUILD_E_RECOVERY.md), [SPEC-11](specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md)
- [ ] **P0-04** Shell controllata e tester che esegue test/build con output persistito. → [SPEC-07](specifiche/07_QUALITY_GATES_E_BENCHMARK.md)
- [ ] **P0-05** CrewAI → provider locale → Developer/Tester/Reviewer; nessuna falsa simulazione. → [SPEC-02](specifiche/02_SELF_BUILD_E_RECOVERY.md)
- [ ] **P0-06** Verificare rifiuto Reviewer e regressione con test fallito: impossibile completare Goal/Task. → [SPEC-07](specifiche/07_QUALITY_GATES_E_BENCHMARK.md)
- [ ] **P0-07** SQLite persiste missioni, handoff, prove, errori, decisioni. → [SPEC-18](specifiche/18_SQLITE_SCHEMA_E_STATI.md)
- [ ] **P0-08** Resume dopo crash/riavvio; no doppie patch o stato incoerente. → [SPEC-02](specifiche/02_SELF_BUILD_E_RECOVERY.md)
- [ ] **P0-09** Self-build reale su micro-modifica non simulata; diff/test/review verificabili. → [SPEC-19](specifiche/19_TEST_MATRIX_E_GATE.md)
- [ ] **P0-10** Correggere problemi CrewAI Windows Unicode/charmap senza toccare vendor. → [SPEC-01](specifiche/01_ARCHITETTURA_E_RUNTIME.md)
- [ ] **P0-11** Docs stato/ripresa aggiornate solo con esiti realmente osservati; comando per continuare documentato. → [SPEC-02](specifiche/02_SELF_BUILD_E_RECOVERY.md)
- [ ] **P0-12** Nessuna dipendenza operativa obbligatoria da Antigravity o OpenCode per continuare una missione locale. → [SPEC-02](specifiche/02_SELF_BUILD_E_RECOVERY.md)

- [ ] **P0-13** Recovery point scoped prima delle modifiche agentiche, preimage per file dirty/untracked, hash, rollback non distruttivo e resume idempotente; verificare prima lo stato implementativo. → [SPEC-02A](specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md)

- [ ] **P0-14** Supervisore durevole seleziona una *nuova* missione dal backlog dopo una verificata, senza chat OpenCode attiva; transazioni, lease e resume idempotente. → [SPEC-21](specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md)
- [ ] **P0-15** Rispetto modalità Off/Assistita/Automatica, stop emergenza, retry bounded; provider 429 blocca o cambia soltanto entro policy autorizzata. → [SPEC-21](specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md), [SPEC-24](specifiche/24_OPERATIONS_SUPERVISION_HEALTH_AND_DIAGNOSTICS.md)

## P1 — Fondamenta prodotto e governance

- [ ] **P1-01** Open Project arbitrary folder, scanner linguaggi/framework/README; Recent Projects persistente; nessun YAML manuale. → [SPEC-12](specifiche/12_PROJECT_DISCOVERY.md)
- [ ] **P1-02** Goal > milestone > task > mission reali con CRUD e relazioni SQLite; evidence-based completion. → [SPEC-03](specifiche/03_GOALS_MILESTONES_TASKS.md)
- [ ] **P1-03** Task board e log incrementali che rimangono coerenti dopo restart. → [SPEC-03](specifiche/03_GOALS_MILESTONES_TASKS.md), [SPEC-08](specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md)
- [ ] **P1-04** Model Hub generale, provider health, model discovery/refresh e stati/offline, non pannello fisso Ollama. → [SPEC-05](specifiche/05_MODEL_HUB_PROVIDERS.md)
- [ ] **P1-05** Adattatori Ollama, LM Studio, llama.cpp, endpoint OpenAI-compatible configurabili; capability test reale. → [SPEC-05](specifiche/05_MODEL_HUB_PROVIDERS.md)
- [ ] **P1-06** Policy cloud locale-first, cost/consent, privacy per progetto e missione. → [SPEC-15](specifiche/15_SICUREZZA_E_PRIVACY.md)
- [ ] **P1-07** GUI Qt stabile, responsive, branding originale, layout persistente e log leggibili. → [SPEC-08](specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md)
- [ ] **P1-08** Self-Build controlli in Settings → Advanced; stato visibile nelle missioni; stop emergenza raggiungibile. → [SPEC-08](specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md)
- [ ] **P1-09** Controllo write scope, conflitti, worktree opzionali, rollback Git non distruttivo. → [SPEC-15](specifiche/15_SICUREZZA_E_PRIVACY.md)
- [ ] **P1-10** No sibling build directories; script build usa percorsi dichiarati, audit 3 portable senza cancellazione. → [SPEC-14](specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md)

- [ ] **P1-11** Cronologia versioni/missioni, anteprima rollback e fallback alla versione precedente avviabile per self-update; preservare SQLite/dati utente. → [SPEC-02A](specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md)

- [ ] **P1-12** Audit **read-only** di build/artefatti esterni (3 portable da ~1,46 GB + smoke fixture), rilevazione file unici, verifica release indipendente; nessuna eliminazione non autorizzata. → [SPEC-23](specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md)
- [ ] **P1-13** Repo hygiene: percorsi build/dist interni e manifest, fixture temporanee gestite, evitare duplicazioni runtime, non rifattorizzare massivamente durante P0. → [SPEC-23](specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md)
- [ ] **P1-14** Health/Diagnostics e stati di errore, retry limitati, 429/timeout/Unicode e report diagnostico redatto. → [SPEC-24](specifiche/24_OPERATIONS_SUPERVISION_HEALTH_AND_DIAGNOSTICS.md)

## P2 — Intelligenza adattiva e strumenti professionali

- [ ] **P2-01** Agent Factory: ruoli variabili/verticali, agenti temporanei, reuso e team dinamico. → [SPEC-04](specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md)
- [ ] **P2-02** Automatico/Assistito/Manuale + pulsante **Ottimizza il mio team**, confronto prima/dopo e override. → [SPEC-04](specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md)
- [ ] **P2-03** Profilo preferito Maximum Verified Quality, altri profili, scelte motivate e risultati misurati. → [SPEC-06](specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md), [SPEC-07](specifiche/07_QUALITY_GATES_E_BENCHMARK.md)
- [ ] **P2-04** Parametri per agente (temperatura, contesto, sampling, reasoning) supportati e autodetect, override persistenti. → [SPEC-06](specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md)
- [ ] **P2-05** Resource Scheduler reale con VRAM/RAM/load/throughput, serialità intelligente, modello unload. → [SPEC-13](specifiche/13_RESOURCE_SCHEDULER.md)
- [ ] **P2-06** Mission Chat: file picker, drag-drop, Ctrl+V screenshot, anteprime, file multipli, persistenza. → [SPEC-09](specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md)
- [ ] **P2-07** Vision/document/audio/video router con capability checking e fallback locale. → [SPEC-09](specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md)
- [ ] **P2-08** Speech Manager opzionale Qwen3-ASR, Vosk, Faster-Whisper, WhisperX; UI install/switch/test. → [SPEC-10](specifiche/10_SPEECH_ASR_MODELS.md)
- [ ] **P2-09** Model manager: install, disable, unload, uninstall, cache audit/cleanup rispettando ownership. → [SPEC-14](specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md)
- [ ] **P2-10** Editor avanzato integrato, LSP, DAP, terminale, Git diff, Test Explorer, MCP. → [SPEC-11](specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md)
- [ ] **P2-11** Indicizzazione di progetto e recupero del contesto mirato, senza infilare tutto nei prompt. → [SPEC-12](specifiche/12_PROJECT_DISCOVERY.md)
- [ ] **P2-12** Benchmark comparabili e storico dei risultati, spiegazioni del Model Advisor, no metriche inventate. → [SPEC-06](specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md)

- [ ] **P2-13** GPU contention con programmi esterni, distinzione inferenza/test, queue, cloud solo autorizzato, timeout adattivi. → [SPEC-13A](specifiche/13A_GPU_CONTENTION_CLOUD_FALLBACK.md)
- [ ] **P2-14** Recovery storage manager: dedup dei punti di ripristino, retention configurabile, scansione read-only, archiviazione ZIP selettiva recuperabile, cestino/quarantena per i vecchi checkpoint e pulizia sicura degli app-owned temp. → [SPEC-02A](specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md), [SPEC-14](specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md)

- [ ] **P2-15** Test end-to-end di recupero da archivio compresso e ripristino da cestino/quarantena, senza toccare runtime, modelli, repository o DB non pertinenti. → [SPEC-02A](specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md)

- [ ] **P2-16** Model & Agent Competence Index registra prove reali e *configurazioni esatte* (modello+quantizzazione+ruolo+parametri+strumenti+ambiente) senza classifiche inventate. → [SPEC-22](specifiche/22_MODEL_AGENT_COMPETENCE_INDEX.md)
- [ ] **P2-17** Qualificazione mirata di nuovi modelli e benchmark riproducibili, risparmio risorse, confidenza statistica e aggiornamento dell’indice dai risultati verificati. → [SPEC-22](specifiche/22_MODEL_AGENT_COMPETENCE_INDEX.md)

## P3 — Distribuzione e qualità di prodotto

- [ ] **P3-01** Audit licenze e manifest dipendenze CrewAI/Qt/runtime/modelli; niente segreti nei pacchetti. → [SPEC-16](specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md)
- [ ] **P3-02** Pacchetti applicativi compressi per OS/architettura; nessun Windows Python su Linux/Mac. → [SPEC-17](specifiche/17_WINDOWS_LINUX_MACOS.md)
- [ ] **P3-03** Bootstrapper leggero, install locale, nessun package manager globale obbligatorio. → [SPEC-16](specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md)
- [ ] **P3-04** Download riprendibili e verificati, repair, diagnostica, primo avvio guidato. → [SPEC-20](specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md)
- [ ] **P3-05** Modelli/ASR opzionali selezionabili, cache esterne riusate, nessun download coatto. → [SPEC-10](specifiche/10_SPEECH_ASR_MODELS.md)
- [ ] **P3-06** Portable completa offline opzionale; release snella e non duplicata. → [SPEC-16](specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md)
- [ ] **P3-07** Prove native Windows e Linux; macOS Apple Silicon/Metal/MLX quando implementato, firma/notarizzazione per release pubblica. → [SPEC-17](specifiche/17_WINDOWS_LINUX_MACOS.md)
- [ ] **P3-08** Test in installazione pulita senza repository di sviluppo; release e update sicuro. → [SPEC-19](specifiche/19_TEST_MATRIX_E_GATE.md)
- [ ] **P3-09** Migrazione path `K:\AI\NL Coding Agent` preparata, NON ESEGUITA prima di autorizzazione utente. → [SPEC-14](specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md)

## Come spuntare correttamente

Salvare per ogni ID: `status`, commit/diff di riferimento, test command, esito, log, piattaforma, timestamp, persona/agente che ha verificato, limiti/assunzioni. Una checklist non basta senza evidenze. Per funzioni soggettive (design UX), distinguere approvazione umana da verifiche automatizzate.

## Addendum v5 — Controlli indispensabili per esecuzione continuativa

- [ ] **P0-16** Tool broker con restrizioni di accesso, grant espliciti ai percorsi esterni, e nessuna falsa dichiarazione di sandboxing. → [SPEC-25](specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md)
- [ ] **P0-17** Protezione contro file di produzione/test sostituiti da stub; rollback selettivo verificato in un test avverso, senza riparazione manuale OpenCode. → [SPEC-27](specifiche/27_SELF_CHANGE_GATES_AND_DEPLOY.md)
- [ ] **P0-18** Supervisor persistente consuma backlog e completa due task locali consecutivi con prove e avanzamento automatico, senza prompt aggiuntivi; Stop/Pausa/Resume. → [SPEC-26](specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md)
- [ ] **P1-15** Tool Registry universale con accessi Read/Execute separati da Write, scope e revoca; GUI Permissions & External Tools. → [SPEC-25](specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md)
- [ ] **P1-16** Frontend Goals/Missions riflette supervisor e permessi, con stato e richieste; Self-Build in Advanced Settings. → [SPEC-26](specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md)

Questi ID si aggiungono alle caselle precedenti; non costituiscono un secondo backlog concorrente. Nessuna checkbox viene spuntata automaticamente sulla base dei rapporti OpenCode.

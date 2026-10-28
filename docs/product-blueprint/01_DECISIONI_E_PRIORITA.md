# Decisioni consolidate, vincoli e ordine di esecuzione

## Decisioni approvate

- Nome prodotto: **NL Coding Agent**. Radice canonica **`K:\AI\NL Coding Agent`** (rinomina completata e verificata il 2026-10-28); un'ulteriore migrazione richiede autorizzazione distinta.
- Prodotto **desktop locale-first, non locale-only**: cloud opzionale con opt-in esplicito, trasparenza sulla privacy e nessun costo nascosto.
- Motore esistente **CrewAI**, integrato senza dipendere da repository vendor clonati nella distribuzione.
- Provider non fissato a Ollama: architettura a plugin/adattatori, discovery e strumenti per Ollama, llama.cpp, LM Studio e endpoint compatibili.
- **Team dinamici**, numero e ruoli suggeriti dal progetto e modificabili, non organico rigidamente fisso.
- Obiettivo di ottimizzazione preferito **Maximum Verified Quality**; disponibili anche bilanciato, velocità, risparmio risorse, custom. Conservare override manuali.
- **Qualità provata > consenso degli agenti.** Le review non ribaltano test obiettivamente falliti.
- **Goals** persistenti separati da **TODO/task** operativi; missioni e verifiche tracciabili.
- GUI **PySide6** per desktop; editor professionale tramite componente mantenuto (es. Monaco/WebEngine o CodeMirror), da valutare con test reali.
- Self-Build **non è una CTA gigante**: configurazione in `Impostazioni → Avanzate → Sviluppo autonomo`; stato e controlli d'emergenza rimangono visibili durante l'esecuzione.
- **Multimodalità**: file, clipboard, screenshot, PDF, audio, video, sorgenti, archivi; routing basato sulle vere capability dei modelli.
- ASR opzionale: Qwen3-ASR 0.6B/1.7B, Vosk, Faster-Whisper, WhisperX; modelli scaricabili e disinstallabili senza cancellare asset condivisi.
- Modellazione hardware consapevole: su 8 GB VRAM / 32 GB RAM, molti agenti logici ≠ molti modelli residenti simultaneamente.
- UI brand dal logo SVG e `assets/theme.tokens.json`; viola `#7531FE`, magenta `#E4469B`, cyan `#46A3C0`; niente glow su testo/codice/log/trascrizioni.
- Distribuzione primaria: **bootstrapper nativo leggero** per OS/architettura che installa bundle compatibili in una directory scelta dall'utente; opzionale offline completa.
- **Nessun uv**, nessun Python/pip/Conda/Homebrew obbligatorio a livello globale; nessun download massivo implicito; niente duplicati inutili.
- Linux e macOS sono obiettivi di rilascio **con build e prove native**, non claim basati sul fatto che Qt sia multipiattaforma.
- Gestione spazio: audit solo lettura con dimensioni reali, proprietà e riferimenti; cancellazione solo dopo conferma esplicita. Mai cancellare checkpoint condivisi o archivi utente.
- Sviluppo pragmatico: riuso moduli funzionanti, piccoli vertical slice verificati, libertà tecnica agli agenti, niente cerimonie YAML obbligatorie.

## Priorità, senza scadenze o numeri artificiali

**P0 — SUBITO E SOLO QUESTO:** audit e hardening del self-build operativo; test Ollama locale modifica file reale → diff → test → review → persistenza SQLite → restart/resume. Se fallisce, risolvere prima di dichiarare autonomo il sistema.

**P1 — Utilità quotidiana:** Goals/Tasks/Missions solidi, Open Project, Model Hub, GUI senza blocchi, log, controlli operativi, strumenti base IDE, provider adattatori. Pianificare per valore e dipendenze, non implementare tutto insieme.

**P2 — Evoluzione:** team adattivi, Model Advisor/ottimizzazione, multimodalità e ASR opzionale, UI Studio professionale, QA avanzato.

**P3 — Distribuzione professionale:** packaging snello, bootstrapper/repair, test cross-platform, aggiornamenti, licenze. L'architettura deve prepararla già da P1, ma non bloccare P0.

## Regola per ogni nuova idea

Registrarla come `PROPOSED` nel backlog con riferimento a una specifica. Non modificare attivamente il codice finché il Goal corrente non ha verifiche soddisfacenti o una ragione esplicita di sospensione.

## Nuova decisione V4 — Continuazione controllata e pulizia

- P0 include la **selezione verificata della prossima missione da un backlog persistente**, non soltanto la conclusione di una missione esistente. Il Supervisor deve esistere al di fuori del contesto dell'LLM e rispettare modalità Off/Assistita/Automatica.
- Le capacità dei modelli non sono considerate note a priori: creare un Model/Agent Competence Index, alimentato da prove mirate, con confidenza e contesto hardware. Non eseguire benchmark massivi nel P0.
- Attività di **repo hygiene** programmata: le 3 portable esterne + la smoke fixture vanno **inventariate e validate**; l'utente deciderà se cestinare/archiviare/eliminare. Nessuna migrazione o cancellazione automatica.
- Nuovi requisiti vanno nel Blueprint e non nella chat OpenCode, salvo il prossimo task eseguibile. Mai aggiornare la roadmap in modo da annullare gli override dell'utente.

## Decisione v5 — Universale, autonomo ma verificato

- Un solo handoff iniziale, poi supervisor **non-LLM** e backlog persistente per ogni progetto, anche a chat chiusa. Non equiparare `--max-missions 1-5` a un processo always-on.
- Prima di esecuzione non presidiata: tool broker/percorso, recovery point pre-edit, rilevamento stub e diff anomalo, test avversi, due task successivi locali senza riparazione manuale.
- Tool esterni autorizzabili via Tool Registry con capability Read/Execute distinte da Write/Delete; fuori dalla radice *default ask/deny*, non vietato per sempre.
- Sviluppo autonomo nelle impostazioni avanzate; Task/Goal/Mission monitorabili; Stop/Pausa sempre disponibili.
- Le portable esterne restano intatte: audit read-only e scelta dell'utente per archiviazione/cestino. Nessuna migrazione della cartella di lavoro senza approvazione.


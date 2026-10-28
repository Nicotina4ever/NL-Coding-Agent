# SPEC-13A — Contesa GPU, inferenza AI, test hardware e fallback autorizzato

**Stato:** requisito di prodotto / backlog futuro, **non dichiarato implementato**.  
**Priorità:** successiva alla verifica del Self-Build Ollama end-to-end.  
**Collegamenti:** SPEC-13 Resource-Aware Scheduler, SPEC-05 Provider/Model Hub, SPEC-06 Model Advisor, SPEC-07 Quality Gates, SPEC-15 Sicurezza/Privacy, SPEC-18 Persistenza, SPEC-19 Test Matrix.

## Obiettivo

NL Coding Agent deve poter continuare a pianificare, scrivere e revisionare codice anche quando la GPU locale è occupata da applicazioni esterne (per esempio NL Video Suite, Codex, rendering, training o test CUDA), **senza interferire con i carichi già avviati**. Deve distinguere nettamente:

1. **Inferenza del modello AI** (Ollama, LM Studio, llama.cpp, altro): può essere locale CPU/GPU o remota, secondo policy.
2. **Esecuzione del software sviluppato** (test CUDA, rendering, benchmark video, test ML): richiede l'hardware e l'ambiente adatti; spostare il ragionamento su cloud **non** trasferisce automaticamente anche i test GPU.
3. **Servizi esterni e altre applicazioni**: possono essere monitorati nei limiti delle API di sistema, ma non sono sotto il controllo dello scheduler NL.

## Politiche selezionabili dall'utente

- **Solo locale (default prudente):** nessuna richiesta remota; accodare i task incompatibili, provare CPU solo se accettabile e disponibile, svolgere intanto lavoro indipendente.
- **Chiedi prima:** proporre un provider cloud motivando vantaggi, informazioni inviate e costi; attendere consenso esplicito.
- **Cloud preautorizzato:** utilizzare soltanto provider, progetti, classificazioni dati e budget già autorizzati. Mai aggiungere servizi a pagamento o trasferire sorgenti riservati senza permesso.
- **Riserva GPU per test:** dare precedenza a processi/test hardware del progetto rispetto alle inferenze LLM locali, eventualmente scaricando **solo i propri modelli inattivi** tramite API supportate.
- Parametri e priorità personalizzabili per progetto e per sessione; profili compatibili con Maximum Verified Quality.

## Resource monitor & decision engine

Rilevare quando possibile: RAM disponibile, CPU, GPU memory in uso/libera, utilizzo GPU, processo proprietario, modello caricato, memoria stimata per nuovo contesto, richieste concorrenti, latenza e progresso. Su NVIDIA usare NVML o `nvidia-smi` se disponibili; su Linux/macOS adattatori appropriati (Metal/MPS/altro) senza fingere metriche non disponibili. I valori *osservati*, *stimati* e *sconosciuti* devono restare distinti.

Schema decisionale:

1. Classificare il task come inferenza, test CPU, test GPU, lavoro I/O o altra categoria.
2. Rilevare dipendenze fra task, ownership dei file, lock e contesa delle risorse.
3. Se GPU occupata: preferire lavoro indipendente non GPU, CPU locale ragionevole, coda di esecuzione o fallback cloud **solo se autorizzato e compatibile con la riservatezza**.
4. Non assumere che utilizzare cloud per l'agente risolva la necessità di GPU locale per i test. Un runner GPU remoto è un prodotto/servizio distinto, da configurare esplicitamente.
5. Rivalutare l'allocazione ai confini delle fasi, senza interrompere processi esterni o cambiare modello in modo non tracciato nel mezzo di una modifica.
6. Lasciare sempre disponibile un comando **Pausa/Stop** per le operazioni controllate da NL Coding Agent.

## Timeout e recovery

- Timeout **specifici per operazione**: startup/caricamento modello, attesa della GPU, inferenza, download, build, test CUDA, checkpoint, revisione.
- Distinguere *assenza di output* da *assenza di progresso*; alcuni test lunghi possono lavorare correttamente senza stampare log continuamente.
- Controllare heartbeat/progresso quando esposto; prevedere timeout di inattività e limiti massimi configurabili, senza un singolo valore universale.
- Arresto graduale e cleanup solo dei processi posseduti; salvare log, exit code, stato missione, risorse e `resume` in SQLite.
- Retry limitati con cambio di strategia motivato; niente loop infiniti, niente spawn ricorsivi incontrollati.
- Se un provider cloud o locale va in quota/rate-limit, accodare o usare alternativa consentita, senza invii ripetuti a pagamento o cambio automatico di policy.

## Coordinamento con app esterne e suite NL

- **Livello 1 (subito realizzabile):** monitorare carico e VRAM e riconoscere la contesa anche con software non integrato; non uccidere né sospendere processi esterni.
- **Livello 2 (futuro):** Resource Coordinator condiviso con NL Video Suite, NL Audio Tools, VoiceCoach e altre utility che *aderiscono volontariamente*, tramite lock/lease e API locali; identificare proprietario, priorità, scadenza e consumo previsto. L'assenza di coordinamento non impedisce il funzionamento conservativo del livello 1.
- Non richiedere un unico processo centrale sempre attivo o un percorso fisso: NL_Core, se disponibile, è un servizio/opzione, non un prerequisito del coding agent.

## GUI / UX

Nel Resource Manager mostrare: RAM/VRAM disponibile, processi osservabili, modelli caricati e loro proprietà, test in coda, attività esterne, policy cloud, costo stimato/autorizzato, motivazione del rinvio e azioni **Esegui ora / Accoda / Passa a CPU / Usa cloud autorizzato** secondo disponibilità. I controlli disabilitati devono spiegare perché. Informazioni hardware ignote non vanno inventate.

## Evidenze richieste / acceptance gates

- [ ] Un processo esterno occupa VRAM: NL Coding Agent evita di lanciare un'inferenza o un test GPU concorrente non sostenibile e registra la scelta.
- [ ] L'inferenza AI può cambiare backend secondo policy; il test GPU rimane in coda quando non dispone di hardware, con stato visibile.
- [ ] Nessuna chiamata cloud senza consenso/policy esplicita; test automatico con credenziali mancanti e budget a zero.
- [ ] Un test lungo con heartbeat non viene terminato da un timeout generico; un processo realmente bloccato viene gestito e la missione rimane recuperabile.
- [ ] Un processo esterno non è terminato o modificato dal gestore risorse.
- [ ] Gestione corretta di carico misto: software esterno GPU + agente Ollama + task non-GPU indipendenti.
- [ ] Misure, decisioni, retry e risultati sono persistiti e consultabili; le prove sono riproducibili.
- [ ] Test su macchina senza GPU NVIDIA o senza driver/telemetria: degradazione corretta, nessun crash.

## Collegamento alla Master Checklist (proposta)

**P2-13 — Resource Contention & Adaptive Fallback.** Monitorare carichi GPU esterni, distinguere inferenza LLM da esecuzione test GPU, accodare task incompatibili, fallback CPU/cloud soltanto secondo policy, timeout adattivi, heartbeat, ripresa persistente, e opzione futura di coordinamento con suite NL. → [SPEC-13A](specifiche/13A_GPU_CONTENTION_CLOUD_FALLBACK.md).

> Non modificare il repository attivo né interrompere la missione #41 per implementare questa specifica. Quando il self-build è verificato, integrare P2-13 nel backlog e selezionarlo soltanto quando dipendenze e priorità lo giustificano.

# SPEC-14 — Disciplina storage, build e cache

## Radice e migrazione

**ATTUALE/CANONICA:** `K:\AI\NL Coding Agent` (rinomina completata e verificata il 2026-10-28; in precedenza `Coding Agent`). **NON SPOSTARE O COPIARE** ulteriormente: un'eventuale nuova migrazione richiede autorizzazione esplicita dopo arresto OpenCode, NL Coding Agent, subprocess/packaging; esportare stato e controllare hardcoded path/SQLite/session associations; evitare copia da 2 GB.

Le tre cartelle sibling `K:\AI\nl-coding-agent-portable`, `-clean`, `-final` risultavano ognuna ~1,46 GB nel resoconto utente. Fare audit read-only: funzionamento reale, unique files, hashes, secrets/user data, contenuto. **Non assumere quale “final” sia buona; non eliminare o spostare senza conferma.** Nuove build sotto `build/` e `dist/` interne al progetto, escluderle dagli input per impedire recursive packaging.

## Proprietà file

Categorie: source user, app-owned runtime, app-owned models, externally shared models, caches app-owned, caches shared (Hugging Face), temp di job, logs, download incompleti, diagnostic artifacts, build intermedi, distro release. Registrare owner, path canonico, size reale, references, last used, running-process locks; symlink e junction rispettati.

Azioni separate: Analyze (read-only), Enable/Disable feature, Load/Unload RAM/VRAM, Change model, Uninstall owned model, Clean owned temporary, Prune log, Clean app-specific cache. Prima della pulizia mostrare cosa e quanto viene cancellato, chi usa il modello, conferma esplicita. Autoclean facoltativo **solo temporanei di task conclusi**, niente glob arbitrari o shared caches. Cambio cache path senza copie massive implicite: scegli lascia, collega, trasferisci selettivamente.

Non introdurre snapshot/backup massivi automatici. Git/diff per recupero di codice, SQLite state persistente e verificabile. Pacchetti di release non devono contenere segreti, dati cliente, allegati e log di sviluppo. Primo avvio installabile nella directory scelta e scrivibile; la modalità portable deve mantenere eventuali user data localmente o usare locazioni configurabili.


## Rollback e recovery: distinzione dalle cache

I recovery points della missione e la versione precedente avviabile **non** sono cache temporanee. Non devono essere eliminati dalla pulizia ordinaria. Dettagli e test obbligatori in [SPEC-02A](02A_RECOVERY_POINTS_ROLLBACK_CACHE.md). Le regole di contesa GPU e fallback si trovano in [SPEC-13A](13A_GPU_CONTENTION_CLOUD_FALLBACK.md).

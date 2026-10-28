# NL Coding Agent — Master Blueprint (28 ottobre 2026)

**Questa è una raccolta di specifiche, decisioni, verifiche e checklist. NON è una patch eseguibile.**

Obiettivo: conservare il quadro completo concordato per NL Coding Agent, senza bombardare OpenCode di istruzioni e senza sovrascrivere il codice o la documentazione già presente.

## Prima di tutto

- **La radice canonica del repository è `K:\AI\NL Coding Agent`** (rinomina completata e verificata il 2026-10-28; record in `docs/WORKSPACE_MIGRATION.md`). Non spostarlo, copiarlo o avviare nuove migrazioni durante una sessione attiva: un'ulteriore migrazione richiede approvazione esplicita e arresto dei processi.
- **Un'unica priorità attiva iniziale:** verificare fino in fondo il self-build tramite modelli locali, fino alla ripresa dopo interruzione. Non iniziare contemporaneamente il resto.
- **Non trattare i rapporti di Antigravity/OpenCode come prove:** controllare sorgenti, test, diff, SQLite, log e riavvio.
- Questo archivio va **estratto in una cartella documentale**, idealmente `K:\AI\NL Coding Agent\docs\product-blueprint\`, e non nella radice dove potrebbe sovrascrivere file omonimi.
- **Non applicare automaticamente** tutta la checklist: è un backlog di prodotto, non un comando a implementare 100 funzioni contemporaneamente.

## Leggi nell'ordine

1. [`00_MASTER_INDEX.md`](00_MASTER_INDEX.md): indice e percorsi ai dettagli.
2. [`01_DECISIONI_E_PRIORITA.md`](01_DECISIONI_E_PRIORITA.md): unica priorità attiva, principi e divieti.
3. [`02_STATO_REALE_DA_VERIFICARE.md`](02_STATO_REALE_DA_VERIFICARE.md): che cosa sappiamo e che cosa è da verificare.
4. [`03_MASTER_CHECKLIST.md`](03_MASTER_CHECKLIST.md): roadmap tracciabile con criteri d'accettazione.
5. [`04_HANDOFF_MINIMO.md`](04_HANDOFF_MINIMO.md): consegna sintetica all'agente.
6. `specifiche/`: documentazione di implementazione per funzione.
7. `templates/`: schede Goal, Task, Verification e Handoff da adattare alla persistenza effettiva.

## Regola di precedenza

**Realtà verificata del codice > vincoli espliciti dell'utente > decisioni consolidate in questo documento > vecchie bozze/idee > ipotesi dei modelli.**

Questo pacchetto non contiene `AGENTS.md`, codice, runtime Python, modelli né file da sostituire direttamente. Le specifiche precedenti (`docs/00_VISION.md`, `docs/01_ARCHITECTURE.md`, ecc.) restano fonti storiche; dove differiscono, registrare la decisione e non procedere a una riscrittura indiscriminata.


## Aggiornamento v2 — 28 ottobre 2026

Consolidate due specifiche aggiuntive: [SPEC-02A](specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md) (rollback e cache protetta) e [SPEC-13A](specifiche/13A_GPU_CONTENTION_CLOUD_FALLBACK.md) (GPU/cloud). Aggiornati [indice](00_MASTER_INDEX.md) e [checklist](03_MASTER_CHECKLIST.md). Non implica funzionalità già implementate. Non sovrascrivere file `product-blueprint` già modificati dall’agente senza confrontarne i diff; **non usare il pacchetto per sostituire codice o stato runtime**.


## Aggiornamento v3 — 28 ottobre 2026

[SPEC-02A](specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md) ora esplicita la gestione dei recovery point con **compressione/esportazione selettiva**, **cestino o quarantena ripristinabile** e protezione dei blob condivisi. Aggiornate checklist e indice. È una specifica progettuale, **non** un motore di rollback già installato. Importare dopo la missione corrente, confrontando i file se già modificati dagli agenti.

## Importazione V4, senza sovrascritture inattese

Questa versione si basa su v3 e aggiunge SPEC-21/22/23/24. Se la cartella `docs/product-blueprint` esiste già nel repository e contiene modifiche locali, **confrontare i file prima di sostituirli**, specialmente checklist, index e log aggiunti dagli agenti. È documentazione/proposta, non prova d'implementazione. Non creare nuove directory sotto `K:\AI` con l'estrazione dello ZIP: il percorso voluto è `docs/product-blueprint/` dentro la radice attuale.

**Per adesso**: nessuna autorizzazione a OpenCode di generare build esterne o ripulire cartelle. Una eventuale richiesta di cleanup deve essere distinta da una richiesta di audit.

## Importazione V5

Questa versione include i requisiti di supervisione *universale* e Permission/Tool Registry, e il resoconto della missione #42 come motivazione di test avversi. **Non si tratta di nuovo software già funzionante.** Se nel repository esiste già la V4 modificata da OpenCode, importa soltanto i nuovi file `06_UNICO_HANDOFF_AUTONOMIA.md`, `V5_CHANGELOG.md` e `specifiche/25_*.md`, `26_*.md`, `27_*.md`, confrontando prima indice/checklist/decisioni invece di sovrascriverli.


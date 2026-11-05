# Persistenza, spazio disco, purga e sicurezza operativa

Questo documento integra la policy tecnica originale **[07_SAFETY.md](07_SAFETY.md)** (staging, oracle, CAS/rollback, confini e permessi). Non la sostituisce.

## Tipi di dati distinti

1. **Progetto sorgente**: file e Git del repository aperto — MAI cancellati dal gestore di cronologia.
2. **Missioni operative**: task, attempt, stage, handoff, checkpoint, leases, diff, log, verification, recovery points, resume state in DB/storage NL.
3. **Chat e allegati**: conversazioni, indici, metadata e contenuti/staging allegati con riferimento a progetto/sessione.
4. **Temporanei**: candidate copies conclusi, log diagnostici, cache interne del solo NL Coder.
5. **Modelli/runtime condivisi**: checkpoint Ollama/llama.cpp, Python embedded, config di altri progetti — **esclusi** dalla purga delle conversazioni.

## Manager storage richiesto nella 1.0

- Scansione **read-only** preventiva con spazio per categoria, oggetto, progetto, durata e dipendenze; tabella di impatto e byte recuperabili realmente attribuibili a file NL.
- Azioni distinte: nascondi/archivia, esporta, elimina dati scelti, compatta SQLite, pulisci temporanei di job terminati. La cancellazione definitiva deve chiedere conferma esplicita e mostrare quanto non sarà più riprendibile.
- Proteggere **missioni attive, pending/resumable** e dati richiesti da verifiche o altri progetti. «Progetto chiuso» non deve significare che i suoi sorgenti vadano eliminati.
- SQLite: effettuare transazioni e foreign-key check; W​AL/checkpoint e VACUUM in manutenzione controllata **solo quando le connessioni sono chiuse / exclusive lock**, con spazio temporaneo adeguato. Non cancellare semplicemente il `.sqlite3` o file `-wal/-shm` mentre il programma è aperto.
- Dedupe per contenuti e allegati con riferimento/hash, senza trasformare uno snapshot di file aperto in un allegato permanente a ogni invio.
- Impostazioni path runtime, cache, modelli e DB configurabili; non spostare pesi enormi o creare copie senza opt-in. Garantire compatibilità con `NL_DATA_DIR` e priorità del profilo standalone senza confondere database di sviluppo e dati utente.

## Barriere operazioni agentiche

Candidato isolato, scope project, symlink/junction check, staging, hashes preimage, candidate e oracle, reviewer indipendente, CAS promotion, recovery journal e crash reconciliation. Le istruzioni di tool/file/URL sono dati non fidati, non autorizzazioni. Cloud, network, delete e processi potenzialmente rischiosi richiedono policy. Il fetch di URL usa il trasporto HTTPS bounded del motore, verifica gli indirizzi risolti e i redirect, e richiede la modalità globale Auto Review o Full Access; `web-fetch` segue la medesima policy, senza una seconda approvazione Research. La ricerca web richiede inoltre un provider esplicitamente configurato. Per notte non presidiata usare budget di runtime, tentativi, tool, spesa e timeout, e richiedere approvazione quando esce dal perimetro.

Il sistema non offre una sandbox OS completa soltanto perché usa `shell=False` e allowlist. Testare esplicitamente escalation, path traversal, symlink, file dirty, collisioni di scrittura, tool output malevolo, crash nel mezzo della promozione.

## Pulizia docs

Questo ZIP docs è stato prodotto in ambiente separato, senza modificare direttamente la cartella `K:\AI\NL Coding Agent\docs` né il database. I file rimossi sono nel pacchetto archivio separato; per un'integrazione reale fare prima audit dei riferimenti da codice/test/script e validazione locale.

# Prossima missione — distribuzione nativa Linux e macOS

## Stato

La build NL Code Code - OSS verificata è Windows x64. Linux e macOS hanno launcher POSIX,
target dichiarati e un bootstrapper fail-closed, ma nessun runtime nativo misurato né una build
standalone accettata. I pacchetti source-beta esistenti non sono installazioni eseguibili e non
vanno pubblicati come release native.

Il repository GitHub `Nicotina4ever/NL-Coding-Agent` contiene un solo commit iniziale, mentre il
repository di lavoro ha una storia Git distinta e non configurava un remote. Prima di pubblicare,
integrare le due storie senza force-push e far passare il pre-push guard sull'esatto contenuto
staged.

## Obiettivo

Produrre e accettare distribuzioni NL Code standalone native per Linux e macOS usando il motore
Python condiviso e la VSIX NL Coder corrente. Non sviluppare né testare la GUI PySide6 legacy.

## Scope e gate

1. Implementare build riproducibili su runner nativi per Linux x86_64 e macOS x86_64/arm64;
   decidere separatamente se Linux ARM64 è supportabile.
2. Costruire e misurare runtime e dipendenze per ogni target; non riusare il runtime Windows.
   Universal 2 resta escluso finché tutti i componenti nativi non sono verificati.
3. Riutilizzare il workflow di Code - OSS e i confini di packaging esistenti senza modificare il
   checkout vendor; includere soltanto l'estensione NL Coder e i file necessari.
4. Verificare su host pulito installazione, primo avvio, project discovery, Chat con Ollama,
   missione e arresto dell'engine. Registrare separatamente dipendenze hardware-only, signing e
   notarizzazione.
5. Eseguire secret/content guard, inventario e checksum sugli artefatti finali. Non includere
   database, progetti, modelli, log, credenziali, checkpoint o staging.
6. Pubblicare gli asset per OS/architettura in una GitHub Release solo dopo il superamento dei
   gate nativi e la verifica dei checksum. Una release source-only può essere etichettata solo
   esplicitamente come tale e non sostituisce queste prove.

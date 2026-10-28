# SPEC-09 — Mission Chat realmente multimodale

Input: testo, drag&drop file/cartelle, file picker multiplo, incolla `Ctrl+V` di screenshot e immagini, immagini con preview/zoom, PDF/Office/testo/log/codice/JSON/CSV, archivi ZIP, audio, registrazione microfono, video. Associarli a una chat, missione, project ID e riferimento di provenienza persistenti.

Pipeline media adapter separati: document text extraction, images/vision via modello che lo supporta, ASR via modulo speech (optional), video frame sampling + audio extraction/ASR, parsers per log/structured data, code repository import controllato. Capacità model-specific: vision ≠ solo perché OpenAI API compatibile; audio understanding ≠ ASR. Dare alternative quando modello non compatibile e non esfiltrare media al cloud senza consenso.

Asset: path canonical, content hash, media type reale, dimensioni, owner, references, access policy; originals, derived artifacts e temporanei separati; evita duplicazioni massicce. Archivi non estratti con path traversal/zip-bomb; limite/prova per file enormi; privacy e rimozione selettiva, senza cancellare file sorgente esterni. Un file condiviso tra più missioni non va cancellato a causa di una sola.

Esperienze richieste: “Correggi questa GUI seguendo screenshot”, “Implementa mockup allegato”, “Confronta screenshot before/after”, “Leggi specifiche PDF”, “Analizza log + immagine”, “Trascrivi dettatura e converti in Goal/Task”. Mostrare quali parti sono state osservate direttamente, trascritte, o inferite; non inventare screenshot esaminati.

Persistenza: trascrizione editabile prima dell'invio, allegati rivisitabili dopo riavvio, elaborazione asincrona e abort controllato.

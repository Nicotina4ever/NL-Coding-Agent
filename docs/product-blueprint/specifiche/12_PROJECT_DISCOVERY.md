# SPEC-12 — Apertura progetti e contesto automatico

Flusso zero-cerimonie: `Apri progetto` → scegli cartella → rileva linguaggi, struttura, framework, documentazione, comandi build/test → crea profilo persistente SQLite → propone Goal/missione. Nessun file YAML manuale richiesto all'utente; override in GUI, impostazioni per progetto salvate internamente.

Scanner: filtri Git ignore + directory enormi/binary/vendor/cache, README/AGENTS.md e documentazione, `pyproject`, `package.json`, CMake, Cargo, solution, pom, etc., rilevando ciò che esiste senza assumere stack. Guardare sorgenti e documenti prima di pianificare, rilevare repository multi-modulo, symlink, workspace e nested repositories senza escape involontari.

Project registry: path canonico, id persistente, name, techs, last opened, branch, docs summary, build commands discovered/confirmed, checksum/mtime per incremental rescan; Recent Projects; rimozione dal registro non cancella directory. Audit in sola lettura dove possibile; file di terzi non modificati per memorizzare metadata.

Context retrieval: segmenta code search strutturata e indicizzazione selettiva; optional embeddings, no download a sorpresa. Prioritizzare file reali e requisiti, non buttare l'intero repo nel contesto. Sostenere progetti diversi (Python, C++/Qt, TypeScript, audio tooling, Flutter, Cloudflare Workers ecc.) con detector estensibili.

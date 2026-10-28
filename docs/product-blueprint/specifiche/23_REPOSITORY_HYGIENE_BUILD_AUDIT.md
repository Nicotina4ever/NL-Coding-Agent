# SPEC-23 — Repo Hygiene, deduplicazione build e riordino controllato

**Priorità:** P1 per l'audit e la disciplina futura; consolidamento operativo SOLO a ciclo self-build stabile e con autorizzazione. **Stato:** REQUISITO. Non modificare il workspace durante l'audit.

## Inventario noto al 28 ottobre 2026 (fornito dall'utente)

| Percorso | Dimensione riportata | File | Ruolo da verificare |
|---|---:|---:|---|
| `K:\AI\NL Coding Agent` | 2,07 GB | 75.706 | Canonical source repository attuale (rinominato il 2026-10-28) |
| `K:\AI\nl-coding-agent-portable` | 1,46 GB | 25.753 | Prima portable |
| `K:\AI\nl-coding-agent-portable-clean` | 1,46 GB | 25.752 | Tentativo pulito |
| `K:\AI\nl-coding-agent-portable-final` | 1,46 GB | 25.750 | Candidata finale NON ancora provata |
| `K:\AI\portable-smoke-project` | ~0 GB | 2 | Fixture di smoke test |

Tre portable: **circa 4,38 GB** complessivi, potenzialmente recuperabili **solo in parte** dopo la selezione e conservazione della versione valida. Due copie delle tre occupano circa **2,92 GB**, ma non è ancora dimostrato che siano ridondanti o prive di file unici. Non usare il nome `final` come prova.

## Invarianti non negoziabili

- **NON** creare, spostare, rinominare, copiare o cancellare directory sibling sotto `K:\AI` durante P0.
- Non eliminare i quattro percorsi esterni sopra elencati prima di inventario, verifica univocità, diagnostica release e conferma esplicita dell'utente.
- La rinomina `Coding Agent` → `NL Coding Agent` è stata autorizzata, eseguita e verificata il 2026-10-28 (vedi `docs/WORKSPACE_MIGRATION.md`); non eseguire ulteriori rinominazioni o spostamenti senza nuova autorizzazione separata e senza la chiusura di tutte le sessioni/processi legati alla radice.
- Conservare `.git` e modifiche non committate, `data/*.sqlite*`, state, configurazioni, credenziali (senza copiarle in pacchetti), log importanti, recovery point, checkpoint condivisi e installazioni dipendenti.
- Non eseguire `git clean -fd`, `git reset --hard`, cancellazioni ricorsive o pulizia implicita di altri progetti.
- Analisi symlink/junction/reparse points in modalità *no follow* per evitare attraversamenti accidentali e recuperi di spazio falsati.

## Workflow di audit **read-only**

1. Inventario delle quattro cartelle esterne e sorgenti: dimensioni reali, conteggi, top-level tree, manifest, launcher, versioni, timestamp, riferimenti nei build script; identificare link a cartelle esterne senza attraversarli.
2. Correlare contenuto del `dist` con `pyproject.toml`, lock/dependency graph, runtime embed, CrewAI importati realmente, librerie PySide6, plugin, licenze e artefatti dei test. Distinguerne uso attivo da mera presenza su disco; non rimuovere librerie solo perché non compaiono in un grep statico.
3. Confronto di elenchi file, dimensioni, firme/Hash **mirati** a manifest, binari principali e file discordanti; hashing completo solo quando serve e dopo stima dei tempi/costi I/O.
4. Validare ciascuna candidata in un processo isolato/temporaneo con GUI start, `doctor`, CrewAI import, connessione Ollama, project open, test mock/smoke e percorso dati. Una build può funzionare solo perché trova il runtime nel repository: verificare che sia indipendente.
5. Confrontare le 3 portable e produrre `KEEP`, `ARCHIVE`, `DELETE_CANDIDATE`, `UNKNOWN` con evidenze e dimensioni stimabili. Nessuna azione distruttiva nella fase di audit.
6. Preparare anteprima delle azioni con path esatti, proprietario, dimensione, possibili file unici, eventuali lock/processi, downgrade e rollback disponibili. L'utente autorizza individualmente.
7. Dopo autorizzazione: preferire cestino/quarantena dove supportati e quando ragionevole; eliminazione permanente solo se scelta esplicitamente. Ricontrollare i path e i fingerprint immediatamente prima dell'operazione.

## Layout del repository (policy)

- `K:\AI\NL Coding Agent\build\` per intermedi e risultati di build effimeri.
- `K:\AI\NL Coding Agent\dist\` per poche release verificate, registrate con manifest.
- `K:\AI\NL Coding Agent\cache\`, `temp\`, `logs\`, `data\recovery\` per **solo dati di proprietà di NL Coding Agent**, con policy separata dalla persistente SQLite.
- Artifact staging: input di packaging esclusi da `build/`, `dist/`, cache, tests, `.git`, modelli/cache Hugging Face esterni e directory già distribuite.
- Build script con `out_dir` esplicito, non `../` o path relativo ambiguo che crei sibling. Smoke test in temp directory gestita e documentata, senza contaminare repo o creare cartelle permanenti nel parent.
- Non duplicare runtimes o checkpoint per ogni progetto. Una distribuzione indipendente può avere una sola copia del runtime necessario: questo NON è un duplicato inutile.

## Riordino codice e documentazione

- Identificare moduli obsoleti, CLI doppie, entrypoint incoerenti, funzioni ridondanti, import ciclici, test fixture orphan, code path Windows-only e hardcoded `K:\AI`.
- Rispettare compatibilità di script `.bat` esistenti e dei percorsi SQLite; migrazioni con test, non mass rename.
- Tenere **una specifica autorevole** (`product-blueprint`), stato tecnico reale in SQLite/Git, handoff snello in `CURRENT_STATE.md`, documenti originali come storia non in conflitto; evitare creare `final-v2-really-final` e documenti duplicati.
- Applicare piccoli refactor verificabili solo dopo handoff, con recovery point scoped (SPEC-02A) e smoke test; niente refactor massivi di cartelle durante la prima autonomia.

## Acceptance gates

- [ ] Audit deterministico e read-only con dimensioni reali e file unici delle tre build, senza toccarle.
- [ ] Una sola release candidate verificata e manifest che la distingue; altre copie etichettate, non eliminate automaticamente.
- [ ] `stage_portable` non include precedenti distribuzioni/cache/test o fonte vendor non necessaria.
- [ ] Rebuild non crea un nuovo sibling in `K:\AI`; destinazioni sempre note.
- [ ] Cleanup preview con conferma esplicita, esclusioni per SQLite/modelli shared/symlink/hardlink/recovery e spazio reale recuperabile.
- [ ] Repo/CLI/test/GUI funzionano prima e dopo la pulizia approvata; git dirty state preservato.
- [ ] Policy di retention e naming versionato per dist/build/log/recovery implementata, verificata e visualizzabile.

**Dipendenze:** SPEC-02A, SPEC-14, SPEC-16/20; SPEC-19 per validazione di release.

# Tracciabilità — dai desiderata alle prove

## Modello di record minimo per ogni requisito

`req_id | goal_id | milestone_id | task_ids | specification | implemented_at | commit/diff | tests | reviewer_verdict | platform | status | evidence | known_gaps`

Ogni requisito del `03_MASTER_CHECKLIST.md` punta a una o più specifiche. Il registro vero deve vivere nel database SQLite dell'app, o essere collegato ad esso tramite mapping: **il documento Markdown non sostituisce la persistenza dell'app**.

## Dipendenze principali

```text
P0: Tools + CrewAI/Ollama + Tests + SQLite + Recovery
 ├─> P1: Project registry + Goals/Tasks + Model Hub + Core GUI
 │    ├─> P2: Agent Factory / Model Advisor (richiedono metriche e provider affidabili)
 │    ├─> P2: Multimodal chat / ASR (richiedono UI + model capabilities + storage)
 │    └─> P2: IDE integrations (richiedono project manager + tool security)
 └─> P3: Packaging / Cross-platform (richiede runtime inventariato e test di release)
```

Sono dipendenze indicative: un agente può riordinare i task in base al codice realmente presente, purché spieghi la scelta e non salti verifiche.

## Esempi di prove valide

- Commit o diff con file effettivamente modificati dal motore locale; tool call attribuibile al Developer LLM.
- Test runner e risultati exit-code/stdout/stderr/timestamp conservati, non solo dichiarati.
- Reviewer che riceve diff e risultati, verdict persistito; fallimento test blocca `COMPLETE`.
- SQLite che conserva mission ID, stato prima/dopo riavvio e checkpoint.
- GUI modello provider offline → stato e messaggio chiari, senza bloccare event loop.
- Packaging avviato da ambiente pulito e su OS nativo con smoke test.

## Criticità da tenere separate

- `Test passato` non prova qualità della specifica se il test è triviale/autoreferenziale.
- `API compatibile OpenAI` non prova vision/tool-calling/JSON corretto: fare capability probe.
- `Qt cross-platform` non prova installer Linux/macOS.
- `Modello su disco` non significa modello utilizzabile o libero in VRAM.
- `Reviewer ha approvato` non significa test superati.
- `Cartella chiamata final` non significa release verificata.

## Estensione V4

- **SPEC-21** P0-14/15: Scheduler persistente; richiede prove di *due missioni consecutive*, ripresa, stop, lock, assenza di task duplicati.
- **SPEC-22** P2-16/17: Registro competenze; richiede test con oracolo, misure confrontabili e livelli di confidenza.
- **SPEC-23** P1-12/13: Gestione repository e build; richiede inventario read-only, manifest e convalida indipendente prima di qualunque proposta di cleanup.
- **SPEC-24** P1-14: affidabilità operativa; richiede 429, test di timeout, log strutturati e report privacy-safe.

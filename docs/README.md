# NL Code — documentazione operativa unica

**Aggiornamento documentale: 2 novembre 2026 (checkpoint harness).** Questa directory sostituisce il vecchio accumulo di audit, roadmap e log. È un corpus **di lavoro**, NON una dichiarazione di versione 1.0 stabile. Le affermazioni verificate al checkpoint sono in `CURRENT_STATE.md`; il programma operativo corrente è nel piano 1.0 (sezione "Programma corrente"). I rapporti storici restano come riferimento, non come stato.

## Prima di lavorare: soltanto 4 documenti

1. **[CURRENT_STATE.md](CURRENT_STATE.md)** — checkpoint reale, difetti verificati, lacune harness aperte.
2. **[NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md](NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md)** — **unico piano esecutivo**, con il "Programma corrente P0–P5" aggiornato alle lacune reali.
3. **[08_ACCEPTANCE_GATES.md](08_ACCEPTANCE_GATES.md)** — prove richieste prima di dichiarare stable.
4. **[OPERATIONS_AND_RESTART.md](OPERATIONS_AND_RESTART.md)** — ripresa, comandi e cosa non toccare.

`NEXT_SELF_BUILD_MISSION.md` descrive la prossima missione (Context Engine e memoria di progetto);
non è un piano parallelo.

## Dove trovare gli altri dettagli, soltanto quando servono

| Documento | Autorità / funzione |
|---|---|
| [PRODUCT_AND_UX.md](PRODUCT_AND_UX.md) | Visione definitiva, identità NL, comportamento UX |
| [ARCHITECTURE_AND_ENGINE.md](ARCHITECTURE_AND_ENGINE.md) | Confini architetturali, CrewAI, Flows, missioni, handoff |
| [CHAT_AND_SESSIONS.md](CHAT_AND_SESSIONS.md) | Chat agentica, contesto file, storia, queue, steering, stop |
| [MODELS_TOOLS_AND_SETTINGS.md](MODELS_TOOLS_AND_SETTINGS.md) | Model Hub, routing, tool calling, permessi, settings |
| [07_SAFETY.md](07_SAFETY.md) | Policy di sicurezza tecnica e staged candidate originale: non semplificata |
| [SAFETY_AND_STORAGE.md](SAFETY_AND_STORAGE.md) | Archivio/purga, storage, esclusioni di cancellazione, privacy |
| [RELEASE_AND_STANDALONE.md](RELEASE_AND_STANDALONE.md) | Workbench NL, Windows/Linux/macOS, pacchetti per amici |
| [FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md) | Contratti MCP/front-end già documentati (riferimento tecnico) |
| [NL_CODE_STANDALONE.md](NL_CODE_STANDALONE.md) | Build Code - OSS esistente, script e limiti (riferimento tecnico) |
| [CREWAI_RUNTIME.md](CREWAI_RUNTIME.md) | Import e versione CrewAI del runtime embedded (riferimento tecnico) |
| [EXTERNAL_SOURCE_REFERENCES.md](EXTERNAL_SOURCE_REFERENCES.md) | Revisioni upstream verificate (riferimento tecnico) |
| [PRE_PUSH_GUARD.md](PRE_PUSH_GUARD.md) | Procedure tecniche di verifica prima di upload GitHub |

## Documenti tecnici da NON riscrivere a cuor leggero

- **[PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md)**: backlog storico completo, **193 ID `NL-BP-*`**. Conservato *byte-per-byte*: potrebbe essere letto dal planner e altri strumenti. I suoi stati riflettono snapshot storici e NON sostituiscono `CURRENT_STATE.md`.
- **[product-blueprint/INDEX.json](product-blueprint/INDEX.json)**: indice macchina degli stessi requisiti, conservato senza rimappare gli ID.
- **[product-blueprint/specifiche/](product-blueprint/specifiche/)**: specifiche originali di dettaglio (SPECS), in sottocartella, consultabili quando un requisito lo esige. Le vecchie checklist e i changelog duplicati sono stati rimossi dal corpus operativo.
- **[NL_CODE_1_0_WIP.md](NL_CODE_1_0_WIP.md)**: verbale del checkpoint `1655cbb` con limiti documentati, mantenuto integralmente.

## Gerarchia unica delle fonti

**Repository e test attuali > prove riproducibili > CURRENT_STATE > piano 1.0 + gate > backlog/blueprint storici > vecchi rapporti archiviati**. Se un vecchio file afferma che un modulo è assente ma il codice nuovo lo implementa, prevale il test del codice; se un rapporto dichiara PASS senza log riproducibile, resta «da verificare».

## Materiale tolto e recupero

Il pacchetto separato `NL_CODE_DOCS_ARCHIVIO_ESCLUSI.zip` contiene **ogni file escluso** con il percorso originale. Il backup integrale di partenza rimane `docs(1).zip`. Non serve tenere duecento file nella cartella attiva. Prima di sostituirla, verificare nel repository riferimenti ai percorsi esclusi e aggiornare solo quelli effettivamente usati da codice/test/script. Questo archivio non contiene il resto del progetto e non esegue alcuna modifica sul tuo PC.

**Nota:** `product-blueprint/INDEX.json` e il backlog sono snapshot che possono citare documenti adesso archiviati. Conservati per la stabilità degli ID; eventuali link storici vanno risolti nell'archivio, senza ricreare copie nella cartella operativa.

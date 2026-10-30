# Runbook unico di ripresa per DeepSeek / agenti locali

## Prima di qualsiasi modifica

1. Aprire `CURRENT_STATE.md`, `NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md`, `NL_CODE_1_0_WIP.md`, `08_ACCEPTANCE_GATES.md`; leggere `PRODUCT_BACKLOG.md` soltanto per gli ID e le dipendenze del requisito in esame.
2. Sul checkout reale `K:\AI\NL Coding Agent` eseguire `git status --short`, annotare HEAD, working tree e gli eventuali agenti paralleli. Non sovrascrivere modifiche altrui.
3. Identificare Python embedded, `NL_DATA_DIR` e DB reale, eventuali fixture di prova, stato delle missioni; non eseguire query di cancellazione su DB live.
4. Verificare che le fonti richiamate da script/test siano ancora presenti dopo la pulizia di docs: la pulizia qui è stata eseguita **su una copia ZIP**, non sul codice completo, quindi questa convalida non può essere pre-certificata.

## Baseline in locale (comandi indicativi, da confrontare con repo)

```powershell
cd 'K:\AI\NL Coding Agent'
git status --short
python\python.exe -m pytest -q
python\python.exe -m pytest -q tests/test_mission_flow.py tests/test_flow_resume.py tests/test_mission_team_plan.py
# Dal frontend, seguire i test riportati in FRONTEND_ARCHITECTURE.md e package.json corrente
```

Se fallisce un test preesistente dopo multi-subtask, distinguere aspettativa obsoleta e regressione reale; aggiornare in modo verificabile. Non utilizzare il codice dei test per mascherare un comportamento rotto.

## Ordine di lavoro unico

- **A:** baseline e regressioni, engineRoot/JSONC, DB/profilo isolato.
- **B:** Chat read tools reali, sessioni, queue/steer/stop, attachment semantics.
- **C:** Flow real repair, handoff tipizzati, planner dinamico, auto model via misure, tool invocation reale.
- **D:** Model Hub/Engine Settings e Storage Manager che lavorano via servizi backend.
- **E:** NL standalone con identità visiva mission-first, About e VSIX attuale, senza rebuild continui.
- **F:** fixture multi-modulo con recovery forzato e completa matrice `08_ACCEPTANCE_GATES.md` su build installata.

I TODO segnati **fatti** nel checkpoint `1655cbb` non vanno rifatti senza una prova di regressione. `MAX` del provider a pagamento non dev'essere impostazione permanente; preferire tool/test/modelli locali per lavori ripetitivi.

## Cosa produrre a ogni checkpoint

Commit, elenco file effettivamente cambiati, test con comandi/esiti, tool invocati, prove (log/diff/hash), stato gate, dati reali intatti, comando di ripresa e problemi specifici. Un WIP non si chiama `1.0 STABLE`. Niente nuovi documenti-fase duplicati; aggiornare questo runbook, CURRENT_STATE e i gate, non aprire nuovi micro-roadmap.

## Quando serve il codice sorgente originario di una decisione

I vecchi audit e piani esclusi sono nel pacchetto `NL_CODE_DOCS_ARCHIVIO_ESCLUSI.zip`, all'esterno della cartella `docs` operativa. I requisiti con ID `NL-BP-*` restano nel backlog e nell'indice macchina; le spec di dettaglio restano in `product-blueprint/specifiche/`.

## CI e riproducibilità

Il workflow `.github/workflows/ci.yml` usa una **matrix** Windows, Linux, macOS su **x64** e **ARM64**; i target sperimentali restano dichiarati tali. Ogni job ha `permissions: contents: read`, non esegue **no publishing**/push/release/API di pubblicazione e carica soltanto report e **checksum**.

Il job `package-smoke` produce `reports/package_smoke.json`; il job `reproducibility` produce `reports/reproducibility_check.json` e verifica che due build siano **byte-identical**. Gli artifact hanno **3-day retention** e non includono runtime, DB, modelli, log o dati personali.

Stato manuale: l'accettazione su hardware/installazione reale resta **MANUAL-PENDING** finché non esiste una prova registrata sul sistema operativo dichiarato. I comandi locali sono:

```powershell
python\python.exe -m pytest -q tests/test_ci_workflows.py
python\python.exe -m pytest -q tests/test_release_acceptance.py tests/test_release_rehearsal.py
```


# Runbook — Audit delle build esterne e riordino senza perdere lavoro

## Prima di qualunque azione

1. Terminare o mettere in pausa in modo consistente OpenCode, NL Coding Agent, Ollama mission writers, build/packaging e test che stanno modificando il progetto. **Per un audit read-only** si può lavorare anche prima, ma i risultati potrebbero cambiare se ci sono processi attivi.
2. Non sovrascrivere il repository con questo Blueprint e non fare modifiche non richieste alla sessione OpenCode o al database SQLite.
3. Eseguire l'inventario read-only `tools/audit_external_builds.ps1` (vedi sotto), verificare manifest/entrypoint/smoke e confrontare file unici.
4. Annotare ultima release **effettivamente funzionante**, runtime necessario, dipendenze, e controllare se le varie build stanno accidentalmente puntando a `K:\AI\NL Coding Agent`.
5. Prima di eliminare una candidata, mostrare all'utente **percorso esatto**, dimensione, contenuto esclusivo, rischio, stima spazio recuperato, destinazione cestino/quarantena o eliminazione permanente; chiedere conferma esplicita.
6. Non cancellare la smoke fixture fino a quando lo smoke test valido non è riproducibile altrove.
7. Se si vuole un archivio di sicurezza, comprimere **solo i sorgenti/config/metadati unici da preservare**, non creare una quarta portable integrale da 1,46 GB.
8. Verificare nuovamente test/launcher dopo qualunque pulizia approvata; se qualcosa non va, ripristinare da archivio/quarantena.

## Script read-only

Con PowerShell dalla root del progetto (quando vorrai usarlo):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "docs\product-blueprint\tools\audit_external_builds.ps1"
```

Lo script mostra dimensione apparente, numero di file e conteggio di nomi relativi condivisi/fuori posto. NON elimina, modifica, muove, zippa o calcola hash di tutti i GB. Può impiegare tempo su decine di migliaia di file. Il percorso `K:\AI` è inserito solo perché è stato indicato esplicitamente dall'utente.

## Rinomina del progetto — completata il 2026-10-28

**La rinomina è stata autorizzata, eseguita e verificata** (radice canonica `K:\AI\NL Coding Agent`; record in `docs/WORKSPACE_MIGRATION.md`). Il preflight sotto resta come riferimento storico (superseded): processi, hardcoded path nei `.bat` e package/config, `SQLite` e associazioni OpenCode, symlink/working directories, mapping IDE, script release. Regola ancora valida: **non copiare** il repository verso una nuova radice — raddoppierebbe inutilmente il peso; una rinomina in place è l'unica modalità ammessa.

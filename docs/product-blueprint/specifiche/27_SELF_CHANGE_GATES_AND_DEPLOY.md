# SPEC-27 — Self-modification safety, diff gates e rollback minimale

**Problema reale:** nella missione #42 il Developer locale ha sovrascritto un planner e un test con stub e OpenCode li ha ripristinati manualmente. La presenza di una suite verde non prova che la modifica richiesta sia corretta o completa. Si progetta contro questo caso, non contro un problema teorico.

## Prima del task

- Una baseline Git stabile (commit locale del codice sorgente verificato, *solo se* `.gitignore` esclude runtime, cache, dati, segreti e modelli). Il workspace ha attualmente numerosi file modificati/untracked: non forzare `git add .` o `git reset --hard`.
- Per ciascuna missione, scrivere manifest `write_scope`, hash originali per file dirty/untracked, preimage selettive e riferimenti a contenuti precedenti; salvare nel percorso app-owned gestito. Evitare copie dell'intero progetto.
- Se il modello desidera scrivere fuori scope, deve ripianificare/chiedere il grant; non usare modelli che generano interi file dove patch delimitate sono più sicure senza verificarne l'esito.

## Durante la modifica

- Validazione pre/post del patch: file esistente, encoding, diff, dimensioni, marker di stub/placeholder/troncamento, rimozioni grandi inattese, test mancanti, API pubbliche eliminate.
- Eseguire prima test mirati, poi regressione, import/smoke del processo fresco dove appropriato. Un test potrebbe aver subito la stessa sovrascrittura del codice: confrontare i test con i requisiti originali e la baseline.
- Reviewer indipendente quando possibile, ma l'approvazione non prevale su gate oggettivi; nessuna manipolazione della baseline a valle per ottenere un diff apparentemente pulito.

## Fallimento e ripristino

- In caso di gate fallito, conservare prove e proporre riparazione entro limiti; rollback **solo dei file effettivamente posseduti dalla missione**, verificando che il contenuto non sia stato modificato da un altro attore nel frattempo.
- In presenza di conflitto, fermarsi e proporre merge; non annullare modifiche umane o di altri agenti.
- Snapshot e cache: proprietà e quota di retention, ZIP/export selettivo, cestino/quarantena solo su approvazione; mai includere embedded Python, checkpoint, installazioni o modelli in snapshot text-scoped.
- Per aggiornamenti dell'app in esecuzione: validare in processo separato, applicare a restart, rollback alla release precedente funzionante; non sostituire file caricati live.

## Prove

- [ ] Recupero da patch che sostituisce modulo e test con stub, senza ricorrere a OpenCode.
- [ ] Dirty/untracked files preservati dopo errore e resume.
- [ ] Nessun `git clean -fd` o `git reset --hard` lanciato per «risolvere» un conflitto.
- [ ] Interruzione tra stage e restart non perde le preimage necessarie al rollback.
- [ ] Git diff/manifest corrispondono esattamente ai file modificati; non comprendono documentazione copiata nel frattempo, né nascondono modifiche realmente introdotte.

**Dipendenze:** SPEC-02A, SPEC-07, SPEC-15, SPEC-18, SPEC-19, SPEC-25, SPEC-26.

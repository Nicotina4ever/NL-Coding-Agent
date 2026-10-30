# Accettazione NL Code 1.0 STABLE — gate veri

**Questo file sostituisce il vecchio `08_ACCEPTANCE_GATES.md` orientato al bootstrap.** Non sono test da spuntare a parole: ogni caso ha comando/input/fixture, modello e route, tool invocati, diff, verifiche, esito, log e commit. Le checkboxes restano aperte finché testate sul repository reale e sull'app installata.

## G0 — Baseline, compatibilità, dati

- [ ] Repository e checkout target verificati (`git status`, commit, storage/db attivi); eventuali modifiche di altri agenti preservate.
- [ ] Suite Python globale, test frontend, extension-host e installed VSIX passano; regressione multi-developer-task risolta senza nascondere test.
- [ ] Nuova installazione VSIX identifica motore da onboarding e valida JSONC senza sovrascrivere User Settings o altri plugin.
- [ ] Due progetti separati non condividono in modo errato chat, write scope, missioni, grants o dati.

## G1 — Chat e controllo operativo

- [ ] Da Chat in READ, leggere e citare un file *non allegato*; una traccia dimostra tool invocato, path e risultato, senza allucinazioni.
- [ ] Coda persistente mentre il modello è occupato; modificare/riordinare/rimuovere un messaggio prima del turno; niente duplicati dopo restart.
- [ ] Steering cambia realmente la missione in corso al checkpoint; Stop generation e Stop mission operano sul backend, Resume riutilizza i fatti persistiti.
- [ ] Sessioni Chat per progetto con nuova/apri/ricerca/rinomina/archivia/cancella e recupero storico preesistente; nessun DB parallelo.
- [ ] Contesto file attivo e selezione non vengono reinviati come allegati automatici; allegato esplicito usato una sola volta, anche dopo errore/retry.
- [ ] Engine/Model Hub permette di cambiare e validare configurazione reale, mostra chiaramente grants vs modalità sessione.

## G2 — Motore multi-agente locale e Flows

- [ ] Team e sottotask generati dall'analisi dei moduli e dipendenze, non solo da elenco di path; più task per ruolo e handoff tipizzati **consumati**.
- [ ] Tool file/shell/Git/test/Research/MCP invocati realmente quando autorizzati, con tracciamento affidabile; tool non consentiti negati.
- [ ] Flow reale segue ramo `repair → verify` dopo una **regressione autentica** e completa APPROVE/promozione, test candidate e oracle.
- [ ] Stop/ripresa dopo più subtask con checkpoint, handoff, diff stabili, nessuna doppia patch e nessuna promozione in conflitto.
- [ ] Modello `auto` scelto in una missione reale da capability probe misurati + esiti storici, motivazione persistita, route manuale rispettata, zero cloud senza opt-in.
- [ ] Modelli locali incompatibili/timeout/offline e contesa GPU gestiti; loop e costi bounded.

## G3 — Progetto di accettazione credibile

- [ ] Progetto **nuovo da zero**: repo strutturato, dipendenze, implementazione multi-modulo, documentazione, test e risultato eseguibile.
- [ ] Progetto **esistente**: modifica significativa con più moduli, interfacce e test, errori da correggere, task dipendenti e revisione indipendente.
- [ ] Una lunga missione non presidiata prosegue entro budget e non corrompe dati dopo interruzione/riavvio; prova reale o stress controllato, non promessa.

## G4 — Storage, sicurezza, distribuzione

- [ ] Preview dello spazio per chat/missione/progetto; archiviazione e purga selettive su profilo di prova; protezione di DB live, sorgenti e modelli condivisi.
- [ ] Test negativi: read-only, scope, symlink, shell allowlist, NETWORK/CLOUD, reviewer reject, candidate/test tampering, crash in promotion.
- [ ] Standalone Windows da directory nuova si avvia senza checkout sviluppo, usa motore e VSIX **aggiornati**, mostra UI NL mission-first e About Nicola Lanci; editor/Git/terminal OK.
- [ ] Screenshots reali a DPI multipli e validazione umana di leggibilità, stile, flow e installazione.
- [ ] Secrets guard, docs/README estensione, versioni pinned, eventuale privata distribution testata con dati isolati; nessuna pubblicazione/push senza approvazione.
- [ ] Linux/macOS: **non marcate STABLE** prima di build/runtime/test nativi indipendenti.

## Regola del rilascio

**NL Code 1.0 STABLE** solamente quando tutti i gate obbligatori per Windows sono verificati su build installata **e l'utente approva l'UX**. Altrimenti: checkpoint WIP con elenco preciso di gate non superati. Il numero di unit test verdi da solo non è criterio di rilascio.

## Record di accettazione beta e privacy

Lo strumento di record è `scripts/release_acceptance.py`; ogni esecuzione produce un **record** verificabile e una **matrix** con **target** platform/arch, versione, **sha256** del pacchetto e matrice degli step. La matrice copre `install`, `startup`, `cli`, `gui`, `clipboard`, `mic`, `tester` alias e le verifiche manuali.

La **privacy** è un requisito: i record non contengono dati personali, credenziali, sorgenti utente o percorsi assoluti; i pacchetti escludono runtime, DB, modelli e log privati. Gli step non automatizzabili restano esplicitamente **MANUAL-PENDING**: nessun risultato “no support” viene presentato come supporto o come release. Il comando di verifica è:

```powershell
python\python.exe scripts\release_acceptance.py verify --input <record.json> --json
```

Il verifier non usa rete, non pubblica e non modifica il repository; un record invalido deve fallire in modo esplicito.


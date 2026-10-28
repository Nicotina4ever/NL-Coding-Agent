# SPEC-21 — Mission Supervisor persistente e prosecuzione autonoma

**Priorità:** P0 per completare realmente il passaggio di consegne, ma non riscrivere la parte già funzionante. **Stato:** REQUISITO, non implementazione verificata.

## Problema da risolvere

Un agente LLM o una sessione OpenCode può terminare dopo un solo incarico, esaurire quota/contesto, bloccarsi su un errore, o lasciare TODO non aggiornati. La continuità di NL Coding Agent non può dipendere dal fatto che una conversazione resti aperta. I TODO di sessione NON costituiscono una coda persistente di progetto.

## Composizione

1. **Goal Registry**: identità e priorità di Goals, milestone, requisiti, dipendenze, proprietario e criteri di accettazione; distingue obiettivi dell'utente da proposte generate dagli agenti.
2. **Mission Scheduler**: seleziona solo task fattibili e non duplicati; legge stato, diff, test, ticket, dipendenze, disponibilità dei modelli e politiche di rischio; propone/scopre il prossimo incarico dal backlog indicizzato.
3. **Supervisor**: processo applicativo **distinto dall'LLM**, decide se avviare, sospendere, ritentare, passare a un altro modello autorizzato, o attendere; mantiene stato in SQLite.
4. **Recovery Controller**: riprende task interrotti senza rifare patch già applicate; riconcilia processi, lock, Git, hash pre/post e prove persistite.
5. **Human Governance**: autonomia configurabile, Stop/Pausa sempre raggiungibili, limiti di budget/risorse, approvazione per azioni rischiose.

## Macchina a stati e idempotenza

`PROPOSED → READY → CLAIMED → RUNNING → VERIFYING → REVIEWING → VERIFIED / NEEDS_FIX / BLOCKED / INTERRUPTED / CANCELLED`.

- Transizioni transazionali in SQLite; identificativo univoco di missione/tentativo e `idempotency_key` (goal + scope + versione requisiti + fingerprint commit/base).
- Heartbeat e lease con scadenza: alla riapertura verificare se il processo esiste prima di riavviare; non interpretare automaticamente una sessione silenziosa come morta.
- Event log append-only per assegnazioni, comandi, risultati, decisioni e approvazioni; snapshot versionati delle configurazioni agent/model/provider.
- Task in esecuzione non devono essere acquisiti da due worker contemporanei. I lock di file/progetto non vanno eliminati alla cieca.
- Un task non viene segnato `VERIFIED` soltanto perché il developer/reviewer lo dichiara, oppure perché i test preesistenti passano: deve soddisfare i gate specifici del task e non introdurre regressioni.
- Alla ripresa: ricontrollare baseline/diff e modifiche esterne; se il codice è cambiato da un altro attore, chiedere riconciliazione anziché sovrascrivere.

## Pianificazione autonoma a lungo termine

- La lettura del Master Blueprint è **on demand**: indice → un solo requisito → riscontro col codice → task piccolo verificabile; non alimentare al modello decine di MD contemporaneamente.
- La sequenza delle missioni è **budgeted**, configurabile, con punto di arresto, limiti di tentativi e rilevamento dei cicli ripetuti; nessun loop infinito garantito.
- Non iniziare task non correlati quando quello precedente è `BLOCKED`: si possono eseguire solo workstream realmente indipendenti e sicuri.
- Dopo un successo verificato: aggiornare goal/milestone, esiti SQLite, `CURRENT_STATE.md`/`NEXT_SELF_BUILD_MISSION.md` con riferimenti ai test; scegliere un nuovo task solo se la modalità autonoma è attiva.
- Se la modalità autonoma è disattivata, terminare la missione senza rischedulare. Mantenere visibili log e comando di ripresa.

## Modalità GUI

- `Impostazioni → Avanzate → Sviluppo autonomo`: Off, Assistito, Automatico con parametri avanzati; politiche rischio, costo/tempo, modelli cloud esplicitamente autorizzati, soglie risorse e quota.
- `Goals / Tasks / Missions`: roadmap, prossimo task, cronologia, prove, impedimenti, proposte di variazione e pulsanti Pausa/Riprendi.
- **Stop di emergenza** accessibile durante le esecuzioni anche fuori dalle impostazioni; spegne la coda e annulla in modo controllato processi posseduti, senza kill di processi altrui.
- Stato visibile `RUNNING`, `WAITING_FOR_RESOURCES`, `WAITING_FOR_APPROVAL`, `BLOCKED`, `VERIFYING`, `REVIEWING`, `RECOVERING`.

## Rispetto della realtà operativa

- Nessun modello cloud viene attivato se non consentito; se un provider `:free` esaurisce quota, salvare checkpoint e mettere in attesa, provando un alternativo già autorizzato e compatibile solo secondo policy.
- Il fallback cloud può spostare l'**inferenza** ma non l'esecuzione fisica dei **test GPU** locali. Test hardware restano in coda o richiedono runner remoto separato, autenticato e autorizzato.
- Se il modello non supporta tool calling, JSON o contesto richiesto, segnalarlo anziché fingere una riuscita.

## Acceptance gates

- [ ] Al riavvio, i task pendenti sono ricostruiti soltanto da stato durevole, anche con contesto chat azzerato.
- [ ] Dopo una missione approvata viene selezionata la successiva a partire da un Goal incompleto, senza nuovo prompt umano.
- [ ] Nessuna modifica doppia/duplicazione task dopo crash e resume ripetuti.
- [ ] Simulare modello non disponibile / quota esaurita: fallback consentito o pausa con resume esatto, senza cloud implicito.
- [ ] Test deliberatamente fallito → `NEEDS_FIX/BLOCKED`, mai `VERIFIED`, indipendentemente dal parere del Reviewer.
- [ ] Il sistema rispetta Stop/Pausa, limiti di tentativi e autonomia Off, conserva i dati e non lascia processi orfani posseduti.
- [ ] Contesa con altro progetto: nessuna scrittura simultanea sui medesimi file.

**Dipendenze:** SPEC-02, SPEC-02A, SPEC-03, SPEC-07, SPEC-13/13A, SPEC-18 e SPEC-19. Non duplicare il motore esistente; comporre i servizi attuali.

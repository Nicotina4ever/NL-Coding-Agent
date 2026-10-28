# SPEC-02 — Self-Build reale, sicurezza e continuità

## Esperienza obiettivo

NL Coding Agent apre il proprio repository come qualunque altro progetto, riceve un goal, seleziona task pronti dal suo backlog, pianifica, modifica realmente file in scope, esegue test e review, registra stato/diff, e sceglie il prossimo task dopo una conclusione **verificata**. La modalità è opzionale e controllabile nelle impostazioni avanzate.

## Pipeline minima inderogabile

1. Preflight: path risolti, Git diff iniziale, stato dirty, modelli/servizi e risorse, task contract e acceptance tests.
2. Project-scoped Developer, su provider locale selezionato, usa file/patch tools reali; risultato attribuibile alla tool call del modello, non allo script di test.
3. Persist source change, diff, file hashes e handoff.
4. Tester esegue test/lint/build in processo figli sicuro, con exit code e log; verifiche contestualizzate.
5. Debugger interviene sui fallimenti, con retry motivati e limite/stop in caso di errori ripetitivi.
6. Reviewer indipendente riceve contratto, diff ed evidenze e approva/rifiuta con motivazioni. **Test oggettivamente falliti = non completato**, anche se Reviewer approva.
7. Commit opzionale soltanto entro le policy; checkpoint DB + audit; prossimo task solo su stato consistente.

## Ripresa

Eventi durabili: ogni transizione significativa deve essere committata nel DB prima di comunicare il successo. Al riavvio distinguere `RUNNING_INTERRUPTED`, `PENDING_VERIFICATION`, `RETRYABLE`, `BLOCKED`; rilevare se file sono già stati modificati (hash/diff), non riprodurre patch alla cieca. Prevenire missioni doppie con lock/lease e idempotency keys.

Autoupdate: non fare hot-reload di moduli core modificati dal processo attuale; testare candidato in processo isolato e riavviare solo in un confine sicuro. Non distruggere modifiche manuali. Git baseline + diff selettivi, senza clonazioni/snapshot giganti.

Autonomia: un task dopo l'altro inizialmente. Permettere task paralleli soltanto per workstream indipendenti e isolamento dei file; mai cicli di spawning ricorsivi incontrollati. Se l'utente interrompe, salvare stato prima dell'arresto. Se si esaurisce un provider, lasciare comando di ripresa.

## Prova di handoff, non negoziabile

Eseguire un task nuovo, concreto e circoscritto **con il motore Ollama locale come programmatore**, tracciare diff reale, test pertinenti, review e persistenza. Interrompere intenzionalmente una missione separata in un checkpoint sicuro, riavviare, dimostrare resume non duplicato. Niente dichiarazione di bootstrap completato prima di entrambe le prove. Conservare `scripts/run_tracked_selfbuild_test.py` e `scripts/verify_handoff_and_resume.py` se esistono, ma ispezionarli prima: uno script può simulare l'effetto senza delega reale.

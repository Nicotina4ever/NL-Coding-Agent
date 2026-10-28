# SPEC-15 — Safety, user consent e code execution

Permissions classificate: READ, reversible project WRITE, safe EXECUTE, risky EXECUTE (installers/network/system changes), DESTRUCTIVE. Consentire autonomia per file tracking/patch e verifiche nel repository attivo, ma policy specifiche per rete, installazioni, cancellazioni, Git push, segreti, modifiche esterne, con possibilità di preferenze esplicite e override temporanei.

Risolvere symlink/junction/realpath prima del controllo scope; bloccare path traversal e alterazioni di file non appartenenti al progetto. Inventory di modifiche utente precedenti; non `git reset --hard`, `git clean -fdx`, `git checkout` su modifiche umane senza approvazione. Shell allow/policy, timeout, logs ridotti; nessun loop incontrollato con `--auto` interpretato come permesso illimitato.

Cloud disabled di default per contenuto sorgente; suggerire escalation se necessario ma consenso per provider e tipologia dati; mostrare chiaramente quando un modello “cloud” appare nel registry locale. Segreti API, tokens e allegati sensibili protetti, esclusi da log/telemetria/LLM prompts quando non necessari. Nessuna trasmissione implicitamente autorizzata.

Self-build: candidate branch/diff, test figli, non alterare core live in maniera non sicura; restart controllato dopo verifica; stop d'emergenza raggiungibile. Dependency install/download con origin+checksum e conferma; componenti opzionali disinstallabili, nessun mutamento di Python globale. Registrare audit degli strumenti e azioni rischiose.

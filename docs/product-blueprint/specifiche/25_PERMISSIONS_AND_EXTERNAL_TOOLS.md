# SPEC-25 — Permessi universali, accesso ai tool esterni e isolamento

**Ambito:** qualsiasi repository gestito, non soltanto il self-build. **Stato:** requisito da confrontare con il codice. **Precedenza:** sicurezza delle azioni prima dell'autonomia non presidiata.

## Regola fondante

Un agente non ha libero accesso al sistema operativo perché un LLM ha ricevuto una frase come «rimani nella cartella del progetto». Le decisioni di autorizzazione sono applicate dal **tool broker** e, per l'esecuzione non attendibile, quando necessario da una sandbox **di sistema**. Un processo lanciato con i privilegi dell'utente può eludere controlli applicativi su pathname: non dichiarare sandboxing vero finché non verificato su Windows/Linux/macOS.

## Capability e scope

Permessi per progetto, missione, agente, azione e percorso/risorsa:

| Operazione | Default suggerito | Note |
|---|---|---|
| Read progetto aperto | Autorizzabile in apertura | Eseguire con esclusioni per segreti |
| Write sui file in scope missione | Secondo policy dell'utente e con recovery point | Vietare scritture concorrenti sugli stessi file |
| Read path esterno | Richiedere o ereditare concessione esplicita | Es. SDK, modelli, tool condivisi |
| Execute tool esterno | Concessione distinta da Read | Eseguibili consentiti e argomenti, cwd, ambiente |
| Write path esterno | Richiedere approvazione con ambito preciso | Mai implicito dalla sola apertura del progetto |
| Delete / move massivo / cleanup | Conferma esplicita, preview e dry-run | Non aggirabile dal planner |
| Network / cloud / installazioni | Policy per destinazione, dati e costo | Cloud non implicito, download grandi con conferma |
| Self-modification | Modalità separata più restrittiva | Nessun rimpiazzo del runtime attivo |

Le scelte dell'utente: `deny`, `allow_once`, `allow_mission`, `allow_project`, `allow_global` ove appropriato, con scadenza, revoca e motivazione. Gestire **read, write, execute, delete, network, install, secrets, cloud** separatamente. Conservare audit della decisione, senza loggare token o contenuti sensibili.

## Tool Registry universale

- Discovery non distruttivo di eseguibili, SDK, API e runtime; registrazione manuale con percorso scelto dall'utente; versioni, `probe`/health, architettura e OS.
- Per ogni tool: `tool_id`, `executable_or_endpoint`, `owner`, `platform`, `capabilities`, `access_grants`, `allowed_projects`, `env_policy`, `working_directory`, `version`, `checksum` se opportuno.
- Esempio: `FFmpeg` in `K:\AI\NL_Core\tools\ffmpeg\bin\ffmpeg.exe`, autorizzato **Read/Execute** per NL Video Suite senza copiarlo.
- La disponibilità di un tool non conferisce automaticamente scrittura nella sua directory.
- I percorsi condivisi con modelli, Core e cache non sono proprietà del progetto aperto; la pulizia non può toccarli senza una procedura separata.

## Path security e processo

- Normalizzare percorsi assoluti, symlink/junction e case su Windows; applicare controlli sugli effettivi target di scrittura. Proteggere da traversal, race TOCTOU e confusione cwd/shell.
- La shell non deve essere una backdoor per eludere il broker; se l'agente può eseguire comandi arbitrari con pieni privilegi, la policy non costituisce isolamento robusto. Usare sandbox OS o ridurre la superficie consentita, distinguendo chiaramente modalità con garanzie differenti.
- Per processi figli: timeout con heartbeat, output massimo, environment controllato, gruppi di processi, ownership e cleanup dei soli processi avviati dall'app.
- Separare i privilegi tra Reader, Developer, Tester, Reviewer e manutenzione storage: il Reviewer di default non modifica il codice sotto esame.

## GUI

`Settings → Permissions & External Tools` con matrice per progetto, storia delle richieste, grant temporanei, revoca, dry-run prima di azioni distruttive e controllo `Pause/Stop` sempre visibile durante la missione.

## Acceptance gates

- [ ] Un tool fuori dalla radice può essere registrato ed eseguito con permesso `Execute`, senza copiarne i file e senza autorizzare `Write`.
- [ ] Tentativo di scrittura extra-scope rifiutato dal tool broker e loggato.
- [ ] Symlink/junction che punta fuori root non aggira una policy di filesystem.
- [ ] Test che dimostra le limitazioni dell'isolamento OS e non etichetta come sandbox ciò che è solo filtro applicativo.
- [ ] Grant una-volta/missione/progetto revocabili e persistiti correttamente.
- [ ] Delete/move/clean up richiedono approvazione esplicita dopo preview; `--auto` non è una concessione universale.
- [ ] Cloud/servizi remoti non ricevono codice confidenziale senza autorizzazione.

**Dipendenze:** SPEC-02A, SPEC-03, SPEC-11, SPEC-12, SPEC-15, SPEC-18, SPEC-21, SPEC-23.

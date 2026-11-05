# Standalone NL e distribuzione

## Rilascio 0.7.3 beta.1 — Windows x64

Il rilascio comprende Setup per utente, portable e VSIX con checksum SHA-256.
`build_release.ps1` confronta versione del payload e della VSIX, richiede output
vuoto e produce lo stato `built-awaiting-acceptance`. Solo dopo il lifecycle e
la prova dell'archivio estratto il manifest viene marcato verificato.

Il portable include l'estensione NL corrente e un profilo iniziale pulito,
mai il profilo dello sviluppatore. Configurazioni personali, database, log e
`engine/data` sono esclusi. L'installer conserva configurazione ed estensioni:
la vecchia configurazione modelli viene migrata dai file applicazione alla
cartella dati quando quella nuova non esiste. La cancellazione opzionale dei
dati richiede un marker di proprietà e percorsi senza junction; cartelle già
popolate prima dell'installazione vengono conservate.

`test_windows_installer.ps1` usa solo una nuova fixture sotto `.workspace/temp`,
rifiuta registrazioni NL Code esistenti, non modifica scorciatoie utente e può
verificare l'upgrade con `-PreviousSetup`. I risultati non vengono eliminati.
Il test ha superato 32 controlli. Inno 6 conserva il limite dei percorsi Windows
molto lunghi; installazione condivisa all-users, macOS e Linux non rientrano
nei gate del rilascio. Evidenze in `docs/evidence/nlcode/release-0.7.3-beta.1-20261105/`.

## Tre elementi, un motore

- **NL Coding Engine** Python/CrewAI/Flows e database controllato da AppServices.
- **NL Coder** VSIX per VS Code/Insiders, installabile dove il motore è configurato; onboarding engineRoot e integrazione Chat/missioni/Goals.
- **NL Code** standalone Windows basata su Code - OSS con workbench mission-first, Chat NL principale e identità visiva originale. La build precedente `NL Code.exe` esiste ma somiglia ancora troppo a VS Code; non attribuirle automaticamente stato stable.

## Personalizzazione vera (non skin)

Home NL, progetto nuovo/esistente, Workspace/IDE, terminale/Git/debugger, Mission Control, Agent Factory, Model Hub, Storage Manager, notifiche, settings, About autore Nicola Lanci. Conservarne usabilità e funzionalità professionali, ma evitare che il Copilot nativo monopolizzi il primo avvio; disattivare per il **profilo NL**, senza patch distruttive a Git/extensions upstream. Branding basato sul SVG reale e theme tokens, coerente su splash/titlebar/sidebar/pannelli, no glow su testo tecnico.

## Rebuild economico

Il pacchetto Windows originale è in `.workspace/dist/NL Code`; script source/build in `scripts/nlcode/`. Quando cambia soltanto motore o VSIX **non** ripacchettare automaticamente l'intero Code - OSS: aggiornare l'estensione del profilo portabile e testare. Quando cambiano file core workbench, mantenere patch riproducibili e rigenerare una release candidata con verifica da directory vuota. Verificare che la build distribuita contenga la versione corrente NL Coder, non la 0.1.0.

## Cross-platform e beta amici

Code - OSS è una base per Windows, Linux e macOS; i runtime embedded e dipendenze native vanno costruiti e testati **per ogni sistema/architettura**. I soli launcher POSIX non costituiscono compatibilità native; Windows stable solo dopo gate Windows, Linux/macOS solo dopo prove native. Il motore deve poter essere installato a percorso scelto dall'utente, e i pacchetti non devono contenere pesi/modelli condivisi, DB personali, credenziali, .env, log privati o checkpoint dell'autore.

GitHub `Nicotina4ever/NL-Coding-Agent` per codice, script e release; caricamento/pubblicazione **soltanto su richiesta esplicita del proprietario**. Documentare crediti reali, acknowledgements tecnici, changelog e README estensione per eliminare “No README available”.

I riferimenti ai passaggi di packaging già verificati sono in [NL_CODE_STANDALONE.md](NL_CODE_STANDALONE.md), i pin upstream in [EXTERNAL_SOURCE_REFERENCES.md](EXTERNAL_SOURCE_REFERENCES.md), il guard in [PRE_PUSH_GUARD.md](PRE_PUSH_GUARD.md).

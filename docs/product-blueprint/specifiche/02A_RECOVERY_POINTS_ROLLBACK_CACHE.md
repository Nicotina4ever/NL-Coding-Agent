# SPEC-02A — Rollback verificabile, recovery points e igiene della cache

> **Stato:** requisito progettuale da verificare e implementare nel repository reale. La presenza di Git, SQLite e del comando `--resume` **non prova** che il ripristino sicuro sia già funzionante. Non interrompere ora le missioni di self-build in corso per aggiungere questo componente.
>
> **Relazioni:** [SPEC-02 — Self-Build](02_SELF_BUILD_E_RECOVERY.md), [SPEC-14 — Storage](14_STORAGE_E_MODEL_LIFECYCLE.md), [SPEC-15 — Sicurezza](15_SICUREZZA_E_PRIVACY.md), [SPEC-18 — SQLite](18_SQLITE_SCHEMA_E_STATI.md), [SPEC-19 — Gate](19_TEST_MATRIX_E_GATE.md), [SPEC-20 — Release](20_RELEASE_UPDATE_DIAGNOSTICA.md).

## Obiettivo

Consentire all'utente e agli agenti di **annullare selettivamente una missione fallita**, ripristinare uno stato avviabile precedente dopo un aggiornamento difettoso e liberare cache/temp senza perdere codice o dati importanti. Tutto questo senza clonare automaticamente un intero repository o duplicare GB di runtime/modelli a ogni modifica.

### Principio non negoziabile

**Il rollback non deve essere più distruttivo della modifica che cerca di annullare.** Mai `git reset --hard`, `git clean -fd`, cancellazioni globali, restore dell'intero repository o sostituzioni indiscriminate di SQLite per annullare una missione circoscritta. Non rimuovere cambiamenti manuali, dati di altri progetti, file di terzi o modifiche di missioni successive.

## 1. Recovery Point Manager — prima di ogni modifica

- Inventaria lo stato Git iniziale (`HEAD`, branch, staged/unstaged/untracked), directory autorizzate, hash e metadati dei file candidati alla modifica; non richiedere un repository pulito per impostazione predefinita.
- Associa `recovery_point_id`, `project_id`, `mission_id`, timestamp, perimetro file, configurazione provider/modello, versioni runtime e criteri d'accettazione; persisti il riferimento in SQLite.
- Prima di scrivere un file, crea una **preimage** recuperabile dei suoi byte originali (anche se era untracked o modificato manualmente) in archivio app-owned content-addressed e deduplicato; registra anche permessi/mode rilevanti e stato "il file non esisteva".
- Crea checkpoint incrementali per soli file effettivamente modificati; salva patch/diff, hash prima/dopo, file creati/cancellati/rinominati e risultati dei gate.
- Un diff testuale Git non è sufficiente da solo per file binari, file untracked, modifiche manuali preesistenti, aggiornamenti del runtime o DB.
- Per missioni potenzialmente distruttive, migrazioni DB e autoupdate del core, usa un grado di isolamento superiore: candidata in staging/worktree, versione avviabile precedente e backup coerente **selettivo** dei dati necessari.
- Lo storage del recovery ha esclusioni obbligatorie per modelli, cache condivise, artefatti distribuzione e altri file enormi non pertinenti; avvisa prima di operazioni che richiederebbero una copia di grandi dimensioni.

## 2. Esecuzione, verifica e commit/attivazione

- I tool di modifica scrivono atomicamente quando praticabile; l'orchestratore registra gli eventi di modifica in modo recuperabile. Non considerare completata una missione se lo stato dei file non corrisponde agli hash registrati.
- Test, build, lint e smoke test producono exit code ed evidenza. Un Reviewer favorevole non prevale su test falliti.
- Distinguere `implementation_verified`, `candidate_activated` e `runtime_healthy`: per un self-update del core, usare processo figlio e controllo di salute prima del passaggio alla nuova versione.
- Se la nuova app non supera il controllo di avvio, rientrare nella versione precedente avviabile, mantenendo diagnostica e dati non interessati; non ricaricare in-process il codice core appena modificato.
- Commit Git selettivi possono aiutare, ma non vanno creati inavvertitamente su lavoro dell'utente senza policy; non forzare push remoti.

## 3. Rollback selettivo e gestione dei conflitti

- GUI: **Missioni → Cronologia → Modifiche → Ripristina questa missione**, con diff/previsione dei file coinvolti. In **Impostazioni → Avanzate → Sviluppo autonomo** configurare politica di rollback; arresto di emergenza sempre accessibile quando una missione gira.
- Modalità **Auto protetta**: applica automaticamente il rollback solo se falliscono verifiche e tutti i file interessati coincidono con lo stato `postimage` della missione, non vi sono edit successivi o dati non pertinenti e il recovery point è completo.
- Se uno o più file sono cambiati successivamente, **non sovrascriverli**: mostra confronto tre-vie/patch selettiva, lascia missione `BLOCKED_ROLLBACK_CONFLICT` e richiedi intervento o una procedura sicura specifica.
- Supporta ripristino completo della missione o di singoli file/hunk, con tracciatura delle azioni; mai accorpare indiscriminatamente modifiche di missioni indipendenti.
- Il rollback ripristina l'effettivo contenuto precedente, inclusi nuovi file creati dall'agente (solo se ancora identici alla postimage attesa); preserva file nuovi non riconducibili all'agente.
- Dopo rollback, esegui test/health check essenziali e registra se il sistema è tornato a uno stato funzionante. Se il rollback fallisce, conserva il punto di recupero e documenta come intervenire.

## 4. Stato e SQLite

- Missioni, task, eventi, recovery points e audit log devono essere consistenti e durevoli; usare transazioni e journaling adeguato. Se occorre salvare il DB, usare **SQLite Backup API** o metodo consistente; non limitarsi a copiare il file principale a database attivo in modalità WAL.
- Le migrazioni schema richiedono verifica della compatibilità e piano di ripristino prima di applicarle; il recupero dello stato del codice **non deve** ripristinare alla cieca l'intero DB e cancellare task più recenti.
- Gestire stati espliciti: `PREPARED`, `ACTIVE`, `VERIFIED`, `FAILED`, `ROLLBACK_READY`, `ROLLED_BACK`, `BLOCKED_ROLLBACK_CONFLICT`, `RELEASE_FALLBACK_ACTIVE`.
- La ripresa dopo crash deve verificare la corrispondenza hash/preimage/postimage e distinguere checkpoint di scrittura e restore parziali, senza riapplicare patch una seconda volta.

## 5. Policy di cartelle e cache

**Nel repository di sviluppo attuale** `K:\AI\NL Coding Agent` (radice canonica dal 2026-10-28; non spostare):

```text
data/
  missions/       # Stato missioni/metadata, dove già presente
  recovery/       # Preimage deduplicate e manifest dei restore point
  history/        # Indice consultabile delle versioni/operazioni
cache/
  indexing/       # Indici ricostruibili
  inference/      # File effimeri di inferenza app-owned
  downloads/      # Download interrotti, manifest e cache dedicate
temp/            # Solo artefatti temporanei, per job identificato
logs/            # Diagnostica con retention configurabile
build/           # Build di sviluppo
dist/            # Release e output verificati
```

Le cartelle sono indicative, **non autorizzano la riorganizzazione immediata** del repository né la duplicazione del DB già esistente. Sorgenti e user data persistenti non sono cache. Inserire queste cartelle generate nel `.gitignore` appropriato e non includerle nei pacchetti di release.

**Nelle distribuzioni Windows/Linux/macOS:** usare una directory dati applicativa scrivibile e configurabile, non presumere che `app/` installata sia scrivibile. Per una portable esplicitamente configurata si può usare `<directory-app>/data`, `<directory-app>/cache`, `<directory-app>/temp` con path relativi alla radice; rispettare modalità readonly/permessi OS.

**Per progetti esterni aperti da NL Coding Agent:** per default archiviare metadata, indici, recovery e cache nella **directory dati di NL Coding Agent**, in sottocartelle per `project_id`; non creare `.nlcoding`, `cache`, `.venv` o altri artefatti nel repo dell'utente senza consenso. Opzione di cache per-progetto solo esplicita.

**Modelli Ollama, Hugging Face e checkpoint condivisi** non sono temporanei gestiti dall'app e non devono essere cancellati per pulire cache o disattivare una funzione.

## 6. Retention e pulizia

- Separare: **cache ricostruibile**, **temporanei di job completati**, **log/diagnostica**, **recovery points ancora utili**, **pacco release**, **model checkpoints** e **dati utente**.
- La pulizia automatica predefinita può riguardare soltanto **temporanei app-owned di job conclusi** con nessun lock/processo attivo; opt-in per cache ricostruibili e riduzione log. Non cancellare automaticamente recovery points ancora necessari, i più recenti punti validi o una versione funzionante per aggiornamenti; politiche di spazio/età configurabili, non soglie rigide universali.
- Prima di ogni pulizia manuale o di categorie sensibili: scansione in sola lettura, spazio effettivo recuperabile, file candidati, proprietario/uso e conferma.
- Rispettare lock, symlink, junction, riferimenti, artifact retention e dipendenze di missioni non concluse. Non seguire junction/symlink oltre lo scope autorizzato.
- Se lo storage si riempie, sospendere nuove missioni rischiose e chiedere una policy di retention; non eliminare silenziosamente il punto di ripristino più sicuro.

## 7. Test obbligatori

- Missione locale modifica file già modificato manualmente → rollback selettivo conserva esattamente il contenuto manuale iniziale.
- Missione crea file nuovo → rollback elimina **solo** quel file quando invariato, senza toccare un nuovo file omonimo modificato successivamente.
- Altro processo modifica file dopo missione → rollback segnala conflitto, non sovrascrive.
- Crash dopo patch ma prima del checkpoint di completamento → resume/restore idempotente, hash validati.
- Fallimento test o reviewer → missione non approvata, ripristino automatico solo entro politica verificata.
- Modifica self-update al core genera errore all'avvio → torna alla build precedente **avviabile**, conserva diagnostica e dati compatibili.
- SQLite in WAL con aggiornamenti → backup coerente e dati più recenti non persi in rollback selettivo.
- Storage audit distingue temp, cache e punti di recupero; preserva checkpoint condivisi Ollama/Hugging Face.
- Non si crea alcuna copia completa del repo o dell'embedded Python per normali missioni di coding; testare anche su Linux/macOS nei rispettivi ambienti.


## 8. Archiviazione compressa, cestino e recupero dopo pulizia

**Tre azioni distinte e reversibili dove possibile:** `Conserva`, `Archivia compresso`, `Sposta nel cestino`. La selezione è configurabile dall'utente per la manutenzione; nessuna conversione o eliminazione deve partire silenziosamente a conclusione di una missione.

- **Conserva:** mantieni recovery point e file preimage referenziati finché richiesti da missioni, blocchi di rollback, policy o release ancora in uso. I punti più recenti e l'ultima versione avviabile vanno protetti dalla pulizia ordinaria.
- **Archivia compresso:** l'utente può selezionare punti recuperabili di missioni concluse e creare un archivio `.zip` (o formato equivalente portabile) contenente **solo manifest, metadata necessari, preimage dei file effettivamente modificati, patch/diff e hash**. Escludi modelli, runtime, interi repository, DB di produzione e file temporanei non indispensabili. Se le preimage sono condivise tramite deduplicazione, materializzare nell'archivio soltanto i contenuti necessari ai punti selezionati, senza alterare le altre referenze. L'archivio deve avere indice e verifica integrità; dimostrare il restore da archivio prima di proporre lo smaltimento della sorgente.
- **Sposta nel cestino:** ove supportato, usa il **cestino del sistema operativo** e non la cancellazione definitiva, dopo anteprima e consenso. Su filesystem/ambienti senza cestino affidabile, offrire una **quarantena locale dell'app** con data di scadenza e funzione Ripristina, oppure spiegare che l'operazione sarà permanente e chiedere conferma distinta. Mai simulare una reversibilità inesistente.
- **Elimina definitivamente:** azione separata, esplicita e con preview dello spazio realmente recuperabile, solo su file app-owned non più referenziati e non protetti; non cancellare dati di progetti, modelli esterni o cache condivise.
- **Compressione non obbligatoria:** il recupero frequente è più efficiente con preimage incrementali/deduplicate; generare archivi soltanto per conservazione a lungo termine o esportazione richiesta. Riutilizzare hash dei blob; non ricomprimere più volte file già compressi o contenuti identici.
- **Soglie non rigide:** offrire retention su età, numero missioni e budget disco **configurabili**, più notifiche e anteprima prima di riduzioni significative. Un progetto non deve perdere la possibilità di rollback mentre una missione è ancora in corso o recuperabile.
- **Archivi fuori dal runtime:** nella modalità sviluppo usare `data/recovery/archives/` (configurabile); nelle release usare percorso dati app privato/scrivibile e configurabile. Non inserire archivi di recovery nel Git repository né nei pacchetti distribuibili; se l'utente desidera esportarli altrove, chiedere il percorso esplicitamente.
- **Sicurezza e privacy:** gli archivi possono includere sorgenti confidenziali, configurazioni e segreti accidentalmente presenti nei file. Mostrare elenco dei file inclusi; escludere credenziali o chiedere avviso/consenso appropriato. Non caricarli nel cloud in automatico.
- **Test:** un archivio compresso deve essere riapribile, verificabile con hash e ripristinabile in un workspace isolato. Dimostrare che il cestino/quarantena consente il recupero nel periodo dichiarato, che la deduplicazione non rompe i punti rimasti e che una richiesta di pulizia non tocca `.git`, modelli, runtime o configurazioni di altri progetti.

### Interfaccia suggerita

`Settings → Advanced → Autonomous Development → Recovery & Retention` per la policy; `Missions → History → Recovery points` per ripristino e archiviazione puntuale; `Storage Manager` per la scansione read-only, la compressione selettiva e la gestione cestino/quarantena. Avvio automatico del Self-Build ancora sotto Settings → Advanced, con stop emergenza visibile durante l'esecuzione.

Il Recovery Point Manager non è un backup completo del sistema, ma un **sistema di versionamento recuperabile delle modifiche attribuibili agli agenti**. Non pretendere di ripristinare installazioni, stati hardware o modelli mai salvati.

## Priorità e stato

**P0 (prima di lasciare libero un Self-Build non presidiato):** checkpoint dei file in-scope, rollback non distruttivo in caso di errore, recupero dopo crash, test minimi di sicurezza. Verificare prima quello che il codice già implementa. **P1:** GUI cronologia + anteprima rollback, automatic fallback della release self-update, policy retention. **P2:** storage manager avanzato, esportazione compressa di recovery point selezionati, cestino/quarantena con ripristino, deduplicazione e benchmark di occupazione.

Questa specifica documenta un requisito **non comprovato nel repository attuale**: richiede audit + implementazione + test. Non passare a OpenCode come missione concorrente alla #41. Non rinominare il workspace.

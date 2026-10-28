# Unico handoff operativo — senza una sequenza infinita di prompt

**Scopo:** dare una sola consegna a OpenCode o, preferibilmente, al Coding Agent quando sa già leggere il Blueprint. Questo documento è il contratto operativo da implementare. **Non** attiva magicamente un processo autonomo con la sola lettura: serve il software della SPEC-26 e la sua verifica.

## Stato noto al 28 ottobre 2026 (da verificare di nuovo)

- CLI esistente: `python\python.exe nl_agent.py` espone `mission`, `roadmap`, `selfbuild`.
- `selfbuild --autonomous` attualmente impone `--max-missions` da 1 a 5: loop **limitato**, non supervisor sempre attivo.
- OpenCode ha dichiarato missione #42 completata e 69 test verdi, ma ha **riparato manualmente** file danneggiati dal modello locale. Perciò l'autonomia continuativa senza supervisione non è ancora dimostrata.
- Git è già inizializzato, ma ci sono molte modifiche/untracked; i TODO di OpenCode non sono il backlog di prodotto e non devono essere considerati verità.
- La radice attuale **resta `K:\AI\Coding Agent`**. Non spostarla, copiarla o rinominarla.

## Unica consegna da impartire (una volta soltanto)

> Leggi `docs/product-blueprint/00_MASTER_INDEX.md`, `01_DECISIONI_E_PRIORITA.md`, `03_MASTER_CHECKLIST.md`, `06_UNICO_HANDOFF_AUTONOMIA.md` e solo le specifiche necessarie al prossimo task. Confronta codice, Git, SQLite e test; non fidarti dei soli rapporti degli agenti. Implementa, utilizzando e verificando i componenti esistenti senza riscriverli, un **supervisor persistente e universale** capace di selezionare automaticamente una missione sicura e incompleta dal Blueprint o dal backlog del progetto aperto, proteggerne le modifiche con checkpoint limitati ai file, assegnarla a modelli locali, verificarla, salvare lo stato, riprenderla dopo interruzione e proseguire con la successiva senza nuovi prompt. **Prima** dimostra rollback di uno stub distruttivo e enforcement dei percorsi/tool autorizzati. Mantieni la modalità non presidiata disabilitata finché questi test e due missioni locali consecutive non superano i gate senza riparazioni manuali esterne. Usa Goals/Tasks/Missions persistenti, non i TODO di OpenCode. Tutte le altre funzionalità restano un backlog deduplicato da affrontare una per volta, secondo dipendenze e priorità. Non creare cartelle sorelle sotto `K:\AI`, non eseguire pulizie, non spostare il repository, non usare cloud né modificare risorse esterne senza consenso. Al termine produci comando di avvio e procedure Stop/Pausa/Riprendi verificati, indicando ciò che funziona e ciò che rimane bloccato. `VERIFIED EVIDENCE > AGENT CONSENSUS`.

## Cosa non confondere

- Una **chat** OpenCode con TODO aperti non è un job in background.
- `--auto` di OpenCode approva alcune richieste di permesso, non implica ripresa eterna o confinamento OS.
- `selfbuild --autonomous --max-missions 3` è una **prova manuale bounded** finché il supervisor long-running non esiste; non implementa da solo tutto il Blueprint.
- Un progetto nuovo non deve contenere copie dei modelli o dei tool: Tool Registry + grants.
- File `CURRENT_STATE.md` o `NEXT_SELF_BUILD_MISSION.md` sono **viste** dello stato, non bastano da soli per una coda di lavoro durevole.

## Dopo che il supervisor è verificato

Aprire NL Coding Agent → Settings → Advanced → Autonomous Development, scegliere `Assistito` (default) o `Automatico controllato`, selezionare il Goal e avviare **una volta**. Lo stato deve essere persistito per progetto; alla riapertura il sistema recupera le missioni senza che l'utente copi la lista dei requisiti in chat. Pausa/Stop attivi durante l'esecuzione. Il comando CLI esatto deve essere riportato dal programma e testato: non inventare flag o comportamenti non implementati.

## Salvaguardie per progetto

La pianificazione, l'indice dei modelli, i permessi esterni, le cache e il controllo qualità sono **capacità del Core valide per ogni progetto**, non un'eccezione locale dell'autosviluppo.

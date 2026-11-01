**Checkpoint 1 novembre 2026 — estensione 0.5.1.** Chat e missioni condividono lo stesso motore e la stessa sessione persistita; la Chat ora supporta /plan, /agent, /mission, /fetch, menu slash nel mezzo della composizione, rewind/modifica dei messaggi, storico con archivio, Keep/Reject delle modifiche missione e dettatura locale (richiede un modello ASR locale). Cloud resta opt-in; nessun fallback cloud automatico. Stato dettagliato sotto.
# Stato corrente — NL Coding Agent / NL Code

**Punto di riferimento: 30 ottobre 2026; checkpoint più recente riportato `1655cbb`.** La versione **1.0 STABLE non è stata raggiunta**. Questo file separa esecuzione dichiarata, difetti osservati dall'utente e lavoro ancora da dimostrare; non sostituisce prove sul repository vivo.

## Architettura reale riportata e già verificata in modo parziale

- **Motore condiviso** in `K:\AI\NL Coding Agent`, Python embedded; CrewAI runtime, Supervisor, missioni persistite SQLite, file staging, candidate/oracle verification, reviewer e promozione.
- **NL Coder**: estensione VS Code Insiders `nlcodingagent.nl-coding-agent`, VSIX 0.3.0, Chat+Mission+Engine, backend MCP. Il file VSIX è stato ispezionato, ma installazione e prove Windows sono riportate dall'agente; l'uso personale dell'utente conferma connessione e dialoghi Ollama.
- **NL Code standalone** Windows: `K:\AI\NL Coding Agent\.workspace\dist\NL Code\NL Code.exe` avviabile secondo precedente accettazione. La build originale includeva NL Coder più vecchio e layout quasi identico a Code - OSS: **non** è la GUI NL finale.
- `03a6a25`: team proporzionale, quattro ruoli su test isolato, handoff e snapshot modelli; missione test con due file e promozione.
- `1655cbb` (WIP): multi-subtask developer nello stesso candidato; Flow `@start/@router/@listen`, ramo repair→verify; strumenti controllati file/shell/Git/test/Research, discovery MCP; aggregazione storico e `auto_select`; default Chat/MCP `pipeline="flow"`. Test riportati: 30 focalizzati, 41 Supervisor, una missione Flow semplice PASS. **Il Flow repair con errore reale, il resume multi-modulo e il tool routing auto live NON sono stati validati**.

## Problemi osservati direttamente durante l'uso di NL Coder

1. **Chat non dimostra uso autonomo del filesystem**: Qwen dice di non poter aprire file; può riassumere `README.md` quando esplicitamente allegato. Non scambiare l'autodescrizione del modello per il vero system prompt: verificare `nlc_converse`, tool schemas, trace e risultati.
2. **Un messaggio per volta**: frontend blocca invio mentre `busyChat`; mancano queue persistente, steering durante lavoro, cancellazione reale delle generazioni e stati di resume chiari.
3. **Sessioni storiche**: UI non offre gestione multiconversazione né una vista di archivio/purga; alcune conversazioni pregresse risultano non trovate.
4. **Missioni accumulate**: UI mostra molte missioni storiche (#3, #7, #16, #36..#46), comprese vecchie `pending`/`blocked`, senza archivio e recupero spazio.
5. **Engine Settings poco operative**: elenco 21 modelli Ollama e ruoli, ma la configurazione esposta appare read-only o confusa; il backend può concedere WRITE/EXECUTE mentre la sessione GUI è read-only (livelli distinti, da spiegare).
6. **Onboarding motore**: VSIX installata in un profilo Insiders non trova l'engineRoot finché l'utente non lo inserisce manualmente. È emerso un errore di salvataggio `settings.json`: diagnosi sul file JSONC reale, senza modifiche indiscriminate.
7. **Contesto editor / attachment**: il file allegato viene letto, ma il comportamento percepito dell'utente è ripetitivo; occorre distinguere file attivo, snapshot, allegato esplicito per turno e storage di contenuti già letti.
8. **Scheda estensione**: icona logo presente, ma `No README available`. Titoli/esperienza ancora troppo tecnici.
9. **Standalone**: Copilot/UI upstream prevalenti, palette e workbench NL non ancora realizzati.
10. **Warnings `star-activation`**: provenienti da `git-base`, `git` e test packages upstream Code - OSS; non sono in sé bug di NL Coder. Non toccare alberi `.build`/`out` per nasconderli.

## Bloccanti del prossimo ciclo

- Riprodurre e correggere regressioni del planner multi-task, soprattutto il test precedente che assume un unico task developer.
- Dimostrare da una chat installata **lettura reale di file senza upload**, tool call con telemetry e risposta verificabile; eventuali errori del system prompt misurati e non indovinati.
- Colmare Flows real repair/recovery, handoff consumati da ruoli distinti, modello auto con capability probe reali.
- Aggiungere gestore conversazioni, queue/steer/stop, impostazioni editabili, pulizia dati selettiva.
- Verificare una missione multi-modulo con errori forzati e resume; poi completare identità standalone originale e acceptance 1.0.

## Cosa NON risulta completato

- Nessuna prova di notte autonoma sicura su lavoro complesso; nessuna accettazione full multi-modulo da zero.
- Nessuna dimostrazione di team liberamente arbitrari o parallelismo sicuro; il planner usa principalmente path dichiarati.
- Nessun supporto Linux/macOS dichiarabile stabile senza runtime nativi e test reali.
- Nessuna convalida della 1.0 da profilo standalone pulito e dall'utente.

Riferimenti: [WIP](NL_CODE_1_0_WIP.md), [piano unico 1.0](NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md), [gates](08_ACCEPTANCE_GATES.md), [evidenza team](evidence/frontend/team-mission-evidence.json).

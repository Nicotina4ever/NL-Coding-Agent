# Prossima missione — Context Engine e memoria di progetto

## Stato

Baseline 2 novembre 2026: suite Python verde sul codice verificato, percorso Team Architect →
specialisti corretto, deadline missione imposta, staging di missione ripulito. Le lacune reali
rimaste sono elencate in `CURRENT_STATE.md`; il programma completo è nel piano operativo
`NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md` (P0–P5). La distribuzione nativa Linux/macOS resta
rinviata: non è la priorità corrente e non va dichiarata supportata.

## Obiettivo

Costruire il **Context Engine** del motore condiviso e una **memoria di progetto persistente**, così
che Chat e missioni recuperino il contesto necessario invece di rileggere il repository o fallire per
budget. Moduli previsti: nuovo `nl_coding_agent/context/`, `app/chat_tools.py`,
`agents/orchestrator.py`, `persistence/database.py`, `app/services.py`. Nessuna nuova interfaccia:
il lavoro deve risultare nella Chat NL Coder e nelle missioni esistenti.

## Scope e gate

1. Budget di contesto centralizzato e misurato (stima token, finestra scorrevole, limiti per
   sezione: istruzioni, history, allegati, risultati tool) con degrado graduale invece del muro a
   60.000 caratteri JSON.
2. Summarization locale opzionale della conversazione, persistita come messaggio/metadato e riusata
   dopo restart; nessuna perdita di tool call pendenti o allegati.
3. Project profile persistito per progetto: linguaggi, entry point, test command, moduli principali,
   documenti autorevoli, rischi noti; aggiornabile e interrogabile.
4. Recupero selettivo per missione: i prompt di developer/architect/reviewer ricevono i file e i
   simboli pertinenti (scope, import, test, decisioni precedenti) invece di uno snapshot alfabetico.
5. Memoria di progetto: decisioni, errori ricorrenti, verifiche e lezioni delle missioni precedenti
   recuperabili con un comando/tool e mostrate nel contesto quando pertinenti.
6. Prove: un turno Chat oltre budget non fallisce; riavvio del client conserva summary e profilo;
   missione su progetto multi-modulo usa il retrieval e cita i file; un errore già visto in una
   missione precedente viene recuperato dalla memoria.

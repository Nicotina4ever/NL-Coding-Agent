# Prossima missione — Code Intelligence e runtime hooks

## Stato

P1 Context Engine e memoria di progetto sono implementati e verificati (suite dedicata, missione
multi-agente reale e continuità Chat dopo nuova sessione). Il programma completo resta in
`NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md` (P0–P5); la distribuzione nativa Linux/macOS è rinviata.

## Obiettivo

Portare il codice dentro il ciclo dell'agente: il modello deve vedere simboli, riferimenti e
diagnostica come tool reali, e ogni scrittura deve poter essere verificata prima della fase tester.

## Scope e gate

1. Esporre `lsp_diagnostics` e ricerca simboli come tool read-only bounded sia in Chat sia nelle
   missioni, riusando `app/lsp.py` e i servizi esistenti (nessuna seconda implementazione LSP).
2. Hook post-write: dopo una scrittura nel candidato eseguire sintassi/import/diagnostica e
   restituire al developer un feedback strutturato; i check falliti non devono diventare PASS.
3. Usare il ledger `tool_invocations` e le evidenze di verifica per decidere retry/repair, con
   budget bounded e senza loop ripetitivi.
4. Test: errore introdotto in una patch rilevato prima del tester; diagnostica con file/riga;
   nessun falso PASS; Chat in read-only limitata come oggi.
5. Verifica reale distinta dai test simulati: una missione con errore reale (test rosso) riparata
   dal ciclo Flow/repair con modelli Ollama locali, con evidenza in `docs/evidence/nlcode/`.

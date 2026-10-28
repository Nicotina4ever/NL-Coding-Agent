# SPEC-19 — Test matrix, prove e criteri d'accettazione

## Gate P0 (necessario prima del self-build autonomo)

A. Runtime Python/CrewAI CLI GUI imports/pytest. B. Project opening/canonical scope. C. Local Ollama/tool calling verificato. D. Source code modifica reale con diff e prova attribuzione. E. Test pertinente, exit code/log/test failure gate. F. Reviewer indipendente, può rifiutare. G. SQLite mission/traces/commit evidence. H. Crash/interruption resume no duplicate changes. I. Self-build riuscito su app stessa con processo di verifica separato. J. Nessuna dipendenza da OpenCode/Antigravity per l'esecuzione successiva.

**Non basta** che il vecchio boost Antigravity abbia passato Gate A–E relativi alla GUI. I Gate operativi/del self-build devono essere testati per il passaggio di consegne.

## Test comportamentali obbligatori successivi

- Goal test fallito ma Reviewer approva → NON COMPLETE.
- Model Hub: endpoint offline/invalid response/tool-capability missing → UI responsive + errore comprensibile.
- Team optimizer: preserva manual overrides; nessuna spawn storm; resource pressure → serialize.
- Speech: ASR disabled e nessun modello installato → app funziona; disattivazione conserva pesi; cleanup non elimina shared files.
- Multimodal: incolla immagine, allega audio e PDF, persiste refs; un modello solo text non riceve immagini non supportate come se sapesse capirle.
- GUI: switching project mentre process lavora, worker cancellation, focus, resizable pane, theme contrast.
- Package: avvio senza dev repo, runtime local-only, smoke su OS nativo, download interrotto/repair, update rollback, licenze.

## Evidenza per ogni gate

`test ID | requirement ID | exact command | target OS/hardware | environment | exit/result | artifacts | timestamp | responsible reviewer | limitations`.

Hardware audio/GUI e macOS/Linux: se non testati, marcarli `NEEDS_NATIVE_TEST`, non PASS. Non simulare risultati in documentazione; registrare output completo in artifact store e un summary breve consultabile in GUI.

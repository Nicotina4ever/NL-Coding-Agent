# Prossima missione — chiusura dei residui verificati

## Stato

Checkpoint del 5 novembre: corrette le regressioni osservate nella missione #60,
la squadra automatica, il recupero limitato, i modelli cloud/locali e gli allegati
trascinati. La verifica sul progetto reale distingue accesso al progetto originale
e modifiche alla sua copia controllata; la missione utente non viene ripresa dallo
sviluppo. Consultare `CURRENT_STATE.md` per test e limiti effettivi.

P1–P5 sono implementati; il nucleo è verificato con test e con evidenze reali (missione advisor,
repair Flow, LSP reale, Chat con routing e continuità, VSIX installata, standalone accettato).
Restano solo i residui elencati nel piano operativo.

Il checkpoint globale del 5 novembre unifica le autorizzazioni nelle quattro
modalità GUI e corregge DELETE in Workspace Write. Non reintrodurre grant separati
per progetto, missione, Chat o agente. Le prove usano i due host con profili isolati;
gli installer 0.7.4 con questa policy hanno superato 32 controlli, incluso upgrade dalla 0.7.3.

## Obiettivo

Chiudere i residui senza riaprire il programma:

1. Eseguire con modelli reali il ramo `repair` quando è il candidato a introdurre l'errore
   (seam già coperto deterministicamente) e registrare l'evidenza.
2. Verificare manualmente scaling Windows e uso quotidiano su progetti reali. Il percorso team
   completo dalla Chat installata è ora verificato nei due host; Stop/Riprendi, riconnessione,
   coda e risultato durevole sono coperti dal runtime e dall'harness GUI del 4 novembre.
3. Il rilascio 0.7.3 beta.1 comprende ZIP/Setup/VSIX rigenerati, prova del portable estratto
   e 32 controlli installer con upgrade dalla 0.7.2. Ripetere questi gate al prossimo rilascio.
   Restano dedicati i gate per percorsi molto lunghi, installazione condivisa multiutente,
   macOS e Linux; non dichiararli verificati dalla compilazione Windows.


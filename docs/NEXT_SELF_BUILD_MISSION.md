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

## Obiettivo

Chiudere i residui senza riaprire il programma:

1. Eseguire con modelli reali il ramo `repair` quando è il candidato a introdurre l'errore
   (seam già coperto deterministicamente) e registrare l'evidenza.
2. Verificare manualmente scaling Windows e uso quotidiano su progetti reali. Il percorso team
   completo dalla Chat installata è ora verificato nei due host; Stop/Riprendi, riconnessione,
   coda e risultato durevole sono coperti dal runtime e dall'harness GUI del 4 novembre.
3. Al prossimo rilascio richiesto, rigenerare ZIP/Setup dal payload aggiornato e ripetere i gate
   di distribuzione. Il payload locale incorpora già una copia indipendente di engine e runtime;
   gli archivi pubblicati non sono stati sostituiti da questo intervento.


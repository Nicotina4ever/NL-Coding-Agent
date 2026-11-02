# Prossima missione — chiusura dei residui verificati

## Stato

P1–P5 sono implementati; il nucleo è verificato con test e con evidenze reali (missione advisor,
repair Flow, LSP reale, Chat con routing e continuità, VSIX installata, standalone accettato).
Restano solo i residui elencati nel piano operativo.

## Obiettivo

Chiudere i residui senza riaprire il programma:

1. Eseguire con modelli reali il ramo `repair` quando è il candidato a introdurre l'errore
   (seam già coperto deterministicamente) e registrare l'evidenza.
2. Verificare dall'interfaccia installata una missione del percorso team completo (non solo chat).
3. Decidere esplicitamente se il payload standalone debba incorporare una copia indipendente
   dell'engine e del runtime invece di referenziare il repository.
4. Eseguire la suite completa a albero fermo e aggiornare i gate.


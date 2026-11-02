# Prossima missione — P2 residuo e skills/subagenti

## Stato

P1 (Context Engine, memoria di progetto, contesto condiviso) e il nucleo P2 (code intelligence
read-only, diagnostica post-write, missione reale con test rosso riparato) sono implementati e
verificati. Il programma completo è in `NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md`.

## Obiettivo

Chiudere i due residui P2 e aprire P3 senza regredire quanto verificato.

## Scope e gate

1. P2: verificare con modelli locali il ramo `repair` quando il **candidato introduce** un errore
   (non solo un test rosso preesistente), incluso il feedback dei diagnostici post-write.
2. P2: usare `lsp_diagnostics` reale quando `pylsp`/`pyright`/`basedpyright` è già installato;
   altrimenti resta un'esposizione onesta `available:false` (nessuna installazione).
3. P3: skills a caricamento progressivo (`.agents/skills`, `.nlcode/skills`) consumate dal runtime
   e tracciate; subagenti read-only con contesto isolato e handoff strutturato consumato dal
   Supervisor; specialisti dinamici oltre i ruoli base senza duplicare il contesto.
4. Gate: una missione reale con errore introdotto e riparazione, un subagente reale il cui handoff
   entra nel risultato finale, e suite completa verde.

# SPEC-20 — Release, aggiornamenti, diagnosi e riparazione

Sorgente unica e build manifest/version immutabili; dependency pins, checksums/firmware/license metadata, changelog, release channel. CI per piattaforme supportate quando disponibile. Confezionare runtime privato e applicazione; escludere repo vendor, segreti, log, cache di sviluppo, dataset e personal SQLite.

Bootstrapper **indipendente dalla Python app** per riparare runtime rotto. Manifest firmato/verificato, download riprendibile con file partial, atomic install, rollback su bundle precedente, cleaning soltanto app-owned/safe staged files. Nessun upgrade in mezzo a una missione di self-build; attendere confine sicuro e persist state.

Diagnostica utente leggibile: backend trovato? modelli installati? tool calls eseguibili? RAM/VRAM? dipendenze PySide6/CrewAI? arch compatibile? permission? dettagli errore e report export redatto dei segreti. Comando `Repair` e `Verify Installation` funzionanti senza IDE e senza manutenzione manuale pip. Nessun auto install silenzioso di download pesanti.

Installer/remover rispetta user projects, checkpoints esterni, state DB, cache condivise: la rimozione completa dei dati personali deve essere un'azione separata, chiara e confermata. Stable release richiede test Linux e macOS nativi per affermare supporto. Fallback offline completo opzionale.

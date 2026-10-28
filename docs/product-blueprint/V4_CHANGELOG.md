# V4 — Product Blueprint esteso e governabile

Aggiornamento **28 ottobre 2026**, consolidato su v3 e *senza alcuna modifica* al repository locale dell'utente.

## Novità

- SPEC-21: supervisore persistente distinto dal singolo LLM, selezione missioni dal backlog, stato/versionamento/riavvio, stop/approval/limiti.
- SPEC-22: indice delle competenze e benchmark mirati per combinazioni modello+ruolo+strumenti+parametri, con evidenza e confidenza.
- SPEC-23: riordino del repository, audit delle tre portable esterne da ~1,46 GB e della smoke fixture; regole esplicite per non creare altre directory sibling.
- SPEC-24: diagnostica lunga durata, 429, logging, error classification, policy retry, baseline/review, Health Dashboard.
- `AUDIT_E_MIGRAZIONE_SENZA_RISCHI.md`: checklist operativa di audit prima di qualunque autorizzazione a pulizia o migrazione.
- `tools/audit_external_builds.ps1`: inventario sola-lettura, senza delete/move, per cartelle specifiche indicate dall'utente.
- Checklist e indice aggiornati con riferimenti e gate verificabili; stato di P0 aggiornato come **dichiarato e da validare**, non dichiarato concluso.

## Non cambia

- Priorità corrente: verificare handoff locale; **non avviare adesso tutti i goals**.
- Radice attuale: `K:\AI\Coding Agent`; radice futura `K:\AI\NL Coding Agent` **non autorizzata**.
- No cancellazioni, copie massive, backup dell'intero Python/vendor/modelli, nuovi sibling `K:\AI`.
- Installer futuro app-local senza package manager globale/uv obbligatorio; release multi-OS solo dopo test nativi.
- Script PowerShell incluso è opzionale e di sola lettura; nessun tool viene eseguito automaticamente.

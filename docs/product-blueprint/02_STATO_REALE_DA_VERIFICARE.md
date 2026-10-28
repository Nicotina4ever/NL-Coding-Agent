# Fotografia storica del 28 ottobre 2026 — evidenze e incertezze

**Questo archivio non contiene un checkout aggiornato del codice sulla macchina dell'utente.** Non è quindi un audit di implementazione e non prova che i feature elencati funzionino.

## Elementi riferiti dall'utente o dai log (DA VERIFICARE)

- `K:\AI\Coding Agent`: cartella sorgente, misurata a ~2,07 GB e ~75.706 file nel resoconto dell'utente.
- Tre cartelle sibling `nl-coding-agent-portable`, `-clean`, `-final`: ciascuna ~1,46 GB e ~25.750 file. `portable-smoke-project` ~2 file. **I nomi non provano quale build funzioni.** Non cancellare automaticamente.
- Runtime `python\python.exe`, Python 3.12.10; in precedenza import CrewAI e pip check funzionavano. Ripetere check sull'installazione corrente.
- GUI PySide6 vista in screenshot, con navigation `Models` e intestazione **Ollama Models**. Tabella mostrava **Fetching models...**: non prova né successo né bug persistente.
- Antigravity ha dichiarato il ciclo Developer → Tester → Reviewer con modello locale `qwen2.5-coder:7b-instruct-q4_K_M`, modifiche a `nl_coding_agent/core/status.py` e `tests/test_system_status.py`.
- Nel diario Antigravity: missioni #4/#6/#7, `scripts/run_tracked_selfbuild_test.py`, `scripts/verify_handoff_and_resume.py`, `docs/CURRENT_STATE.md`, `docs/NEXT_SELF_BUILD_MISSION.md`; alcuni test dichiarati passati. La Reviewer e il resume non risultano confermati in modo indipendente. L'agente si è fermato per quota 429.
- Log CrewAI includevano errori console Windows `charmap` con emoji 🚀. Non cambiare codice vendor: correggere encoding/logging al confine applicativo e confermare che i log tornino.
- OpenCode installato e lanciabile nella sessione citata (`opencode --version` → 1.19.4; supporto `--auto` nell'help). La sua sessione e TODO sono esterni a questa documentazione e possono essere più aggiornati.

## Da determinare per primo (non inventare stati)

- [ ] Git status, branch e diff iniziale, file untracked, backup senza duplicazioni.
- [ ] Quali test esistono e passano davvero con runtime incorporato.
- [ ] Schema SQLite e migrazioni; missioni e prove per #4/#6/#7.
- [ ] Il Developer LLM ha davvero emesso la modifica e usato un tool, anziché uno script che simula l'azione?
- [ ] Il Reviewer ha restituito verdict verificabile e registrato? Cosa accade a un rifiuto?
- [ ] Un'interruzione forzata seguita da riavvio riprende lo stato senza rieseguire distruttivamente i task?
- [ ] L'interfaccia e i comandi CLI funzionano, compreso il rilevamento modelli senza freeze?
- [ ] Esiste un Self-Build entry point persistente e limitato che non dipende da OpenCode?
- [ ] I build portable sono isolati dall'albero sorgente e non contengono cache/modelli/segreti?
- [ ] Nessun task attivo ha creato conflitti con le modifiche di OpenCode/Antigravity?

## Livelli di confidenza da mostrare nell'app

`REQUESTED` → `IMPLEMENTED_UNVERIFIED` → `VERIFIED_AUTOMATED` → `VERIFIED_INTEGRATION` → `VERIFIED_NATIVE_HARDWARE`.

Separare inoltre `BLOCKED`, `PARTIAL`, `REJECTED` e `NOT_APPLICABLE`; non inferire che una dichiarazione di agente sia una prova.

## Rapporto recente ricevuto dall'utente (non riesaminato sul suo disco)

- Utente: `python\python.exe -m pytest -q` → **69 passed in 12.62s**.
- `nl_agent.py --help` mostra comandi `doctor`, `audit`, `work`, `status`, `roadmap`, `mission`, `selfbuild`, `gui`.
- `selfbuild --help` include `--from-roadmap`, `--autonomous`, `--resume`, `--max-missions` e stop-after; l'esistenza di flag NON prova l'autoplanning dal backlog.
- `mission --list` aveva #41 interrotta dopo Developer #93; poi OpenCode ha **riferito** #41 `completed`, Reviewer `APPROVE`, Tester concluso e 69 test superati, con `data/selfbuild_state.json` aggiornato.
- Il rapporto #41 contiene ambiguità tra `diff_stat` a 6 file, `changed_paths` che riportava Blueprint e scope dichiarato di 4 file: occorre controllare provenance, baseline e audit trail; non correggere la baseline per nascondere modifiche della missione.
- **Non verificato indipendentemente:** selezione della prossima missione senza nuovo prompt, resilienza a riavvio reale, isolamento di processi concorrenti, rollback dei file preimage e controllo di integrità delle build.
- Da inventario utente: progetto 2,07 GB; portable `portable`, `portable-clean`, `portable-final` da 1,46 GB ciascuna; smoke fixture di 2 file. Non è stato eseguito alcun audit comparativo approfondito in questa sessione.

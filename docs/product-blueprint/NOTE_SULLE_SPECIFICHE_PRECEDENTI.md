# Compatibilità con il precedente Antigravity SelfBuild Pack

Il pacchetto originario (precedentemente consegnato nella conversazione) conteneva `AGENTS.md`, `START_HERE_ANTIGRAVITY.md`, `docs/00_VISION.md` ... `docs/09_ANTIGRAVITY_EXECUTION_MISSION.md`, il logo e `assets/theme.tokens.json`, agent definitions e rules.

**Questo nuovo Blueprint non sostituisce quei file nel repository e non aggiunge agent definition auto-eseguibili.** È deliberatamente solo documentazione e checklist.

Evoluzioni importanti rispetto al pacchetto iniziale:

1. L'handoff si chiude **solo** dopo self-build reale con Ollama + recovery verificato; non bastano GUI e Gate A–E.
2. `Ollama Models` diventa Model Hub multi-provider, con policy cloud e capability detection.
3. Team e modelli diventano adattivi e misurati; predefinito Maximum Verified Quality.
4. Goals persistenti separati da Tasks e Missions.
5. GUI diventa Studio con allegati/screenshot/audio/video, Qwen3-ASR opzionale e strumenti IDE.
6. Self-Build attivazione spostata **nelle Impostazioni Avanzate**, non come grande tasto promozionale.
7. Distribuzione bootstrapper leggero per piattaforma, nessuna installazione globale obbligatoria, nessun uv.
8. Rinomina della cartella completata il 2026-10-28 (radice canonica `K:\AI\NL Coding Agent`); nessun ulteriore spostamento o migrazione senza autorizzazione dell'utente.
9. Niente pulizie/cancellazioni automatiche di build, cache o modelli condivisi.
10. Nuove richieste sono backlog, **non missioni da eseguire contemporaneamente**.

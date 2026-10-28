# SPEC-01 — Architettura, modularità e runtime

**Goal:** desktop application locale-first con servizi stabili, indipendenti da GUI e provider specifici.

Livelli separati: GUI PySide6; API/application service facade; Project Registry; Goals/Missions/Task Graph; Agent Factory/CrewAI bridge; inference provider adapters; capabilities and resource scheduler; strumenti scope-limited; verification and quality gates; SQLite + event log; self-build coordinator; updater/bootstrapper separato. Non integrare logica business nei widget.

Interfacce da standardizzare in modo incrementale: `ProjectService`, `MissionService`, `GoalService`, `ModelRegistry`, `InferenceProvider`, `AgentScheduler`, `ToolExecutor`, `ArtifactStore`, `VerificationService`, `SelfBuildService`, `UpdateService`. Nomi indicativi: adattarli al codice, senza riscrivere moduli funzionanti.

**Runtime dev:** l'installazione attuale usa `K:\AI\Coding Agent\python\python.exe` (Python 3.12.10 al bootstrap), con CrewAI; non imporre nuovo ambiente e non modificare i checkout `crewAI/`, `crewAI-tools/` come sorgenti dell'app.

**Runtime distro:** Python privato e dipendenze confezionate in bundle OS-specifico; non distribuire il runtime Windows su Linux/macOS. CrewAI può essere bundled come libreria e non come repository clonato intero; audit licenze/transitive deps.

Processi impegnativi (inferenza, download, scansione, build, ASR) devono stare in worker/processi separati, mai bloccare l'event loop Qt. Event bus tipizzato e log strutturati per propagare progresso/errore e supportare UI e CLI. I processi figli su Windows devono forzare/gestire UTF-8 in modo appropriato, evitando `charmap` quando gli eventi CrewAI contengono emoji; niente patch a vendor.

**Verifica:** launch GUI/CLI, imports, graceful shutdown, error states, unit test dei servizi indipendenti dalla GUI, persist on restart.

# Indice generale e mappa della documentazione

## Orientamento

| Documento | Scopo | Quando leggerlo |
|---|---|---|
| [README](README_IMPORTANTE.md) | Uso sicuro dell'archivio | All'importazione |
| [Decisioni e priorità](01_DECISIONI_E_PRIORITA.md) | Vincoli e scelte definitive | Prima di pianificare |
| [Stato da verificare](02_STATO_REALE_DA_VERIFICARE.md) | Distinzione tra dichiarato e provato | Prima di ogni ripresa |
| [Master checklist](03_MASTER_CHECKLIST.md) | Backlog e prove di completamento | Durante pianificazione/QA |
| [Handoff minimo](04_HANDOFF_MINIMO.md) | Prompt cortissimo per un agente | Solo quando serve la ripresa |
| [Handoff unico per sviluppo continuo](06_UNICO_HANDOFF_AUTONOMIA.md) | Contratto di implementazione del supervisor universale e di ripresa senza prompt successivi | Prima di abilitare autonomia non presidiata |
| [Tracciabilità](05_TRACCIABILITA.md) | Dipendenze, prove e riferimenti | Audit |
| [Runbook audit build](AUDIT_E_MIGRAZIONE_SENZA_RISCHI.md) | Inventario read-only e pulizia soltanto autorizzata | Prima del riordino |

## Specifiche di dettaglio

| ID | File | Dominio |
|---|---|---|
| SPEC-01 | [Architettura](specifiche/01_ARCHITETTURA_E_RUNTIME.md) | Confini moduli, GUI, applicazione |
| SPEC-02 | [Self-build](specifiche/02_SELF_BUILD_E_RECOVERY.md) | Modifica reale, verify, resume |
| SPEC-02A | [Rollback e recovery points](specifiche/02A_RECOVERY_POINTS_ROLLBACK_CACHE.md) | Protezione modifica, rollback selettivo, cache, archivi ZIP e cestino |
| SPEC-03 | [Goals e missioni](specifiche/03_GOALS_MILESTONES_TASKS.md) | Goals > milestones > tasks > missions |
| SPEC-04 | [Agenti adattivi](specifiche/04_AGENT_FACTORY_E_TEAM_DINAMICI.md) | Ruoli variabili, verticali, task graph |
| SPEC-05 | [Provider e modelli](specifiche/05_MODEL_HUB_PROVIDERS.md) | Ollama, LM Studio, llama.cpp ecc. |
| SPEC-06 | [Model Advisor](specifiche/06_MODEL_ADVISOR_E_PARAMETRI.md) | Tuning motivato, misure reali |
| SPEC-07 | [Qualità verificata](specifiche/07_QUALITY_GATES_E_BENCHMARK.md) | Prove > consenso di agenti |
| SPEC-08 | [GUI/UX](specifiche/08_GUI_STUDIO_E_ADVANCED_SETTINGS.md) | Studio, palette, Self-Build nascosto |
| SPEC-09 | [Multimodalità](specifiche/09_MULTIMODAL_CHAT_E_ALLEGATI.md) | Screenshot, documenti, audio, video |
| SPEC-10 | [Speech/ASR](specifiche/10_SPEECH_ASR_MODELS.md) | Qwen3-ASR, Vosk, WhisperX, Faster-Whisper |
| SPEC-11 | [Tool IDE](specifiche/11_IDE_TOOLS_LSP_DAP_MCP.md) | Editor, terminale, Git, LSP, DAP |
| SPEC-12 | [Project Manager](specifiche/12_PROJECT_DISCOVERY.md) | One-click open, no YAML obbligatorio |
| SPEC-13 | [Risorse](specifiche/13_RESOURCE_SCHEDULER.md) | VRAM, RAM, concorrenza |
| SPEC-13A | [GPU / Cloud fallback](specifiche/13A_GPU_CONTENTION_CLOUD_FALLBACK.md) | Contesa GPU, timeout adattivi, cloud autorizzato |
| SPEC-14 | [Storage](specifiche/14_STORAGE_E_MODEL_LIFECYCLE.md) | Cache, modelli, pulizia selettiva |
| SPEC-15 | [Sicurezza](specifiche/15_SICUREZZA_E_PRIVACY.md) | Scope, Git, autorizzazioni, cloud |
| SPEC-16 | [Distribuzione](specifiche/16_BOOTSTRAP_INSTALLER_DISTRIBUZIONE.md) | Lightweight installer, no uv/global |
| SPEC-17 | [Cross-platform](specifiche/17_WINDOWS_LINUX_MACOS.md) | OS adapters, Metal/MLX, test nativi |
| SPEC-18 | [Persistenza](specifiche/18_SQLITE_SCHEMA_E_STATI.md) | Dati durevoli, versionamenti, eventi |
| SPEC-19 | [Test e accettazione](specifiche/19_TEST_MATRIX_E_GATE.md) | Gate tecnici + evidenze |
| SPEC-20 | [Release e manutenzione](specifiche/20_RELEASE_UPDATE_DIAGNOSTICA.md) | Build riproducibili, riparazione |
| SPEC-21 | [Supervisor persistente](specifiche/21_SUPERVISORE_PERSISTENTE_AUTONOMIA.md) | Coda goal duratura, ripresa, pianificazione autonoma |
| SPEC-22 | [Competenze agenti/modelli](specifiche/22_MODEL_AGENT_COMPETENCE_INDEX.md) | Benchmark mirati, classifica contestuale, affidabilità |
| SPEC-23 | [Repo hygiene e build audit](specifiche/23_REPOSITORY_HYGIENE_BUILD_AUDIT.md) | Tre portable esterne, pulizia sicura, percorsi |
| SPEC-24 | [Operazioni e diagnostica](specifiche/24_OPERATIONS_SUPERVISION_HEALTH_AND_DIAGNOSTICS.md) | 429, timeout, log, health, error recovery |
| SPEC-25 | [Permessi e tool esterni](specifiche/25_PERMISSIONS_AND_EXTERNAL_TOOLS.md) | Permessi universali, Tool Registry, limiti veri di sandbox |
| SPEC-26 | [Continuazione autonoma](specifiche/26_AUTONOMOUS_BACKLOG_EXECUTION.md) | Supervisor che procede dal backlog senza prompt nuovi |
| SPEC-27 | [Self-change quality gates](specifiche/27_SELF_CHANGE_GATES_AND_DEPLOY.md) | Preimage, diff, stub detection, rollback, Git e smoke |

## Fonti progettuali preesistenti (NON sovrascrivere)

Nel repository di sviluppo sono stati predisposti i documenti originali `AGENTS.md`, `START_HERE_ANTIGRAVITY.md`, `docs/00_VISION.md` ... `docs/09_ANTIGRAVITY_EXECUTION_MISSION.md` e i token in `assets/theme.tokens.json` (se tuttora presenti). Vanno consultati come contesto, ma **non attribuire loro un'implementazione non verificata**. Il vecchio criterio di handoff A–E non è sufficiente: occorre il ciclo Ollama end-to-end con resume verificato.

## Gerarchia della roadmap

```text
Obiettivo strategico (Goal)
  → milestone misurabili
    → task concreti e dipendenti
      → missioni / tentativi esecutivi
        → modifiche, log, test, review, evidenze
```

Non trasformare l'indice in 20 incarichi simultanei. Selezionare il prossimo task realmente pronto, implementarlo e verificarlo.

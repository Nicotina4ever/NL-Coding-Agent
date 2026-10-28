# Nuova conversazione DeepSeek Harness — handoff completo

> **RELOCATION UPDATE (2026-10-28):** il repository è ora `K:\AI\NL Coding Agent`. Le indicazioni
> di percorso contenute in questo documento sono contesto storico precedente alla rinomina e sono
> conservate così come sono state scritte; la radice canonica corrente è `K:\AI\NL Coding Agent`.

## Contesto

Progetto Windows: `K:\AI\Coding Agent`. Obiettivo: NL Coding Agent, sistema locale multi-agent di coding con CLI `nl_agent.py`, CrewAI, Ollama, SQLite e GUI Qt. Il repository è già avviato; **non va rifatto né spostato**. Hardware: NVIDIA RTX 4060 Ti 8GB, 32GB RAM. LLM principali disponibili localmente: `qwen3.5:9b`, `ornith-1.5:9b`, `granite4.2:3b`, `qwen2.5-coder:7b-instruct-q4_K_M`. Uso DeepSeek-V4.1-Flash via API consentito se autorizzato dall'utente in Harness; modello API ufficiale `deepseek-flash`. Cloud **non** automaticamente abilitato dall'app NL Coding Agent.

Il repository contiene il Master Blueprint in `docs/product-blueprint/` con la SPEC-28. Un ciclo auto-build precedente (#43/#45) ha prodotto stub al posto del planner/test; i rapporti OpenCode descrivono 72 test verdi ma l'audit reale degli ultimi sorgenti evidenzia protezioni non integrate.

## Allegati da fornire nella sessione

1. `NL_Coding_Agent_Review.zip` (sorgenti e blueprint, 135 file).
2. `NL_Coding_Agent_Safety_Foundation_Patch.zip` (solo cinque file modificati, patch unificata, test e audit).

## Obiettivo operativo per l'agente

1. Leggi `AUDIT_REALE_E_LIMITI.md`, controlla i diff della patch proposta, verifica che i file del repository reale non siano cambiati da quando è stato creato lo ZIP. Non sovrascrivere versioni successive o modifiche manuali: merge guidato dal diff.
2. Prima di ogni modifica ferma e verifica i processi Self-Build/missione realmente in esecuzione, senza uccidere processi estranei. Mantieni Git, data/, runtime, vendor, checkpoint e directory sorelle intatti.
3. Integra lo staging in **tutte** le scritture modello di `MultiAgentOrchestrator`, incluse tool native e `_apply_text_actions`, non soltanto in `selfbuild_runner`. Rimuovi `run_command` generico dagli strumenti del modello finché non esiste sandbox OS/command broker. Il root di stage deve contenere solo sorgenti/test piccoli e non essere un duplicato multi-GB.
4. Verifica i candidati con l'intera suite attendibile sullo staging (moduli esistenti e test pre-missione); promuovi solo dopo test e gate AST/scope; non accettare `APPROVE` come prova indipendente. Fai fail-closed su ogni eccezione. Gestisci journal multi-file, crash/restart e CAS postimage; proteggi dirty/untracked.
5. Implementa bounded repair su staging e riduci il rischio di stub con feedback diagnostico; vietato riparare direttamente il repo. Usa prove dell'effettiva funzionalità, non assert fittizi.
6. Correggi la persistente selezione missioni: `run_autonomous` attualmente usa un Markdown fisso e non chiama il planner di nuovi task. Non creare un altro orchestratore, riusa SQLite. Il supervisore deve vivere indipendentemente dalla chat, con start/stop/resume verificati e monitoraggio reali.
7. Solo DOPO test reali SH-01..SH-07 e due missioni distinte senza intervento manuale: attiva la prosecuzione sul Blueprint, avvia Model/Agent Competence Index locale (benchmark non invasivi, niente modelli cloud senza grant nell'app), poi le altre specifiche.

## Comportamento e formato di consegna

NON chiedere un nuovo prompt a ogni sottotask. Procedi per passi reali entro le autorizzazioni; se un gate fallisce, diagnostica e correggi entro limiti ragionevoli, oppure blocca in sicurezza. Mostra evidenza originale dei test e degli hash; distinguere IMPLEMENTATO, TESTATO SUL MOCK, VERIFICATO END-TO-END, BLOCCATO. Non scrivere un report di "handoff completo" se non hai dimostrato due missioni autonome successive. Non modificare directory estranee o installare runtime globali; niente nuove copie portable da 1,46 GB.

## Prima prova da fare

Riprodurre in un workspace temporaneo la sostituzione del planner con `def select_next_task(): pass` e del test con `assert True`, verificando che l'agente non possa cambiare neanche un byte del repository vero. Controllare che la protezione passi attraverso i tool di CrewAI, non soltanto importando `staging_broker.py` dai test. Solo dopo eseguire un normale self-build controllato.

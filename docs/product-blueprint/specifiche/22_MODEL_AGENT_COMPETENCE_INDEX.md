# SPEC-22 — Model & Agent Competence Index, benchmark mirati

**Priorità:** P2. **Stato:** requisito futuro; NON lanciare benchmark massivi mentre si chiude P0.

## Distinguere modello, agente, ruolo e configurazione

- **Modello**: ID/versione/tag/hash del checkpoint, quantizzazione, provider, runtime, capacità dichiarate e verificate, hardware di test.
- **Agent Profile**: ruolo/skill, strumenti concessi, istruzioni, progetto/dominio, policy, modello assegnato.
- **Evaluation Run**: combinazione esatta di model+profile+config+task+ambiente. Un buon risultato in un ruolo non implica abilità universale.
- Mai assegnare punteggi predefiniti perché il modello ha un nome noto, più parametri o recensioni positive.

## Indice costruito nel tempo

Per dominio (Python, Qt, C++, ASIO, audio DSP, WebRTC, test, security, docs, design UI ecc.) registrare campioni comparabili, versione del toolchain, difficoltà, verifiche passate/fallite, tool call riuscite, regressioni, tempo, costi, picchi RAM/VRAM, errori e incertezza. Identificare risultati **osservati** vs **stime** vs **capability dichiarate**. Conservare distribuzioni/campioni e non solo un totale puntuale; il numero di prove conta.

## Benchmark contestuali economici

1. Definire skill richieste dalla missione e leggere benchmark storici vicini.
2. Solo se l'evidenza è insufficiente o un modello è nuovo, far svolgere una **prova breve, isolata e verificabile**, con fixture e oracle nascosto; nessun cambiamento al repository principale.
3. Riutilizzare il risultato finché modello/config/ambiente sono compatibili; invalidarlo dopo cambi significativi del checkpoint, tool chain o ambiente.
4. Evitare che i modelli leggano le risposte del benchmark; separare valutatore deterministico e agente candidato.
5. Se un nuovo candidato non è stato testato, assegnargli un livello `UNKNOWN/PROVISIONAL`, non un punteggio inventato.
6. Comparare soprattutto **dentro la stessa classe di task e condizioni**, usando intervalli o incertezza per campioni scarsi; nessuna falsa precisione.
7. Separare contributi del modello da difficoltà del task e qualità degli strumenti. Usare task normalizzati e controllare regressioni.

## Agent selection

- `Project Analyzer` rileva tecnologie, domini, rischi e task graph.
- `Competence Index` produce candidati con evidenze e confidenza.
- `Adaptive Team Planner` consiglia ruoli, numero logico di agenti, provider e parametri in base a capacità, qualità, risorse e vincoli.
- `Scheduler` impone serialità/parallellismo reale e contesa di file/RAM/VRAM. Più agenti non implicano più modelli residenti.
- Suggerire revisione con un secondo modello quando aggiunge diversità utile; la revisione non prevale sui gate deterministici.
- Profilo preferito `Maximum Verified Quality`; `Balanced`, `Speed`, `Resource Saving`, `Custom` disponibili. Preservare override manuali e consentire scelta assistita.
- Mostrare **perché**, con riferimenti ai test, ed esporre alternative. Non modificare in corsa parametri non riproducibili: aggiornare al boundary della missione.

## Persistenza indicativa

Tabelle/entità logiche: `models`, `providers`, `agent_profiles`, `model_capabilities`, `benchmarks`, `evaluation_runs`, `role_skill_scores`, `recommendations`, `team_assignments`, `hardware_profiles`, `override_policies`. Schema effettivo da verificare/normalizzare prima di migrare SQLite, senza duplicati.

## Acceptance gates

- [ ] A nuovo modello nessuna classifica inventata; prova `PROVISIONAL` esplicitamente dichiarata.
- [ ] Due task comparabili hanno score e prove riproducibili; task non comparabili non diventano classifica assoluta.
- [ ] Cambio di versione/quantizzazione invalidato o segnalato.
- [ ] Model Advisor sceglie e spiega configurazione diversa per coding, review e vision quando evidenza lo giustifica.
- [ ] Modello scarso in tool calling non riceve missioni che richiedono tool senza fallback verificato.
- [ ] Benchmark non tocca sorgenti utente e non causa conflitti con test GPU di progetti esterni.
- [ ] Override, policy locale-only e confini di spesa sempre rispettati.

**Dipendenze:** SPEC-04/05/06/07, SPEC-13/13A, SPEC-18/19.

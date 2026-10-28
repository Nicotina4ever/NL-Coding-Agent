# SPEC-06 — Explainable AI Model Advisor e parametri adattivi

## Obiettivo

Suggerire per ogni task/ruolo: provider, modello, parametri di campionamento e contesto, reasoning dove esposto, output budget, compatibilità tool, parallelismo, pianificazione RAM/VRAM. Mostrare **perché** e **quanto è affidabile** la scelta.

## Parametri

Temperatura, top_p, top_k, repeat_penalty, seed, num_ctx/context window, max output tokens, eventuali reasoning flags/effort/stop sequences **solo se supportati dal modello/backend**. Profilo iniziale ragionato per ruolo: coding/test generalmente deterministici; brainstorming/UI può essere più esplorativo. Non applicare temperature universalmente “migliori”; rispettare raccomandazioni del modello e prove locali.

Contesto: selezionare file rilevanti con retrieval/search/riassunto e riserva per output/tools; non portare il massimo disponibile senza misurare qualità, VRAM, tempo. Compattazione ragionata al riempimento, mai perdere vincoli/accettazione.

## Scoring e profili

Obiettivo preferito **Maximum Verified Quality**; altri Balanced, Maximum Speed, Resource Saving, Custom. Misure: test pass rate per classi di task non banali, regressioni, reviewer reject rate, tool calls valide, time-to-verified, token/latency, consumo RAM/VRAM, context stability. Separare training/test dei benchmark da missioni reali; attenzione a campioni piccoli e overfitting ai test.

Non inventare punteggi. Se non si hanno misure, etichettare raccomandazione `PROVISIONAL` e proporre un microbenchmark. Risultati deduplicati in SQLite con versione, backend, hardware, task type, timestamp e confidence. Override utente per modello/parametro/team sempre prevalente; advisor non cambia missione a metà in modo silenzioso.

## Interazione

Pulsante **Ottimizza il mio team**: anteprima prima/dopo, differenze in modelli/ruoli/parametri/concorrenza, benefici attesi con evidenze e trade-off (tempo, qualità, privacy, memoria, costi). Modalità `Automatic/Assisted/Manual` distinta dal profilo qualità; cambi automatici consentiti entro policy e al confine delle missioni.

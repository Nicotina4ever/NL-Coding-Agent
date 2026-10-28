# SPEC-04 — Agent Factory, gruppi dinamici e specializzazione verticale

Il numero di agenti **non è fisso**. Un analizzatore esamina repo, stack, dipendenze, rischio, task indipendenti, carico e memoria e propone composizione: team compatto se sufficiente, specialisti verticali se utile, team lead/integration QA per progetti vasti. L'utente può aumentare/diminuire/sostituire agenti.

Agente = ruolo logico con skill/tool policy, contesto/handoff, modello/provider e budget selezionabili; **non implica un nuovo modello in memoria**. Ruoli esemplificativi: Planner, Backend, Frontend, Desktop/Qt, Audio/DSP, AI/ML, Database, Security, Infra/Cloud, Build/Packaging, Documentation, Tester, Debugger, Reviewer, Integration Lead. Possono nascere specialisti temporanei, riusati o sospesi al completamento.

Agent Factory costruisce task contract e capability profiles riusabili; manager dei team valuta i task graph e assegna workstream indipendenti in sicurezza. File ownership, worktree/patch isolation se necessari, serializzazione quando più agenti toccano gli stessi componenti. Non fissare limiti arbitrari al numero di agenti; limitare risorse/concorrenza secondo dati reali e prevenire runaway spawning.

Modalità: `Automatic` seleziona team entro policy; `Assisted` suggerisce e richiede approvazione; `Manual` applica override e non li sovrascrive. Pulsante **Ottimizza il mio team** in Agent Manager/Model Hub: confronto prima/dopo ruoli, modelli, parametri, parallelismo e ragioni; `Applica`, `Personalizza`, `Mantieni`; suggerimenti spiegabili, stime vs misure separate. Adaptive Team opzionale ricalcola a confini di missione sicuri e registra la configurazione usata.

Non confondere più agenti con più qualità: usare benchmark e integrazione verificata. Debounce suggerimenti, niente riorganizzazioni continue durante patch attive.

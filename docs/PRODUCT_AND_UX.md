# Prodotto e UX — requisiti non negoziabili

## Identità del prodotto

**NL Coding Engine** è il motore di programmazione agentica, locale-first. **NL Coder** è l'estensione compatibile VS Code/Insiders; **NL Code** è la standalone basata su Code - OSS, con una propria identità, non una semplice skin. Tutti usano le medesime APIs, configurazioni autorizzate, database e runtime; nessuna copia parallela di CrewAI, Supervisor, model router, missioni.

**Autore / ideazione / progettazione / direzione del progetto: Nicola Lanci.** `Help → About NL Code` e pagina estensione devono usare logo reale `assets/LogoMio.svg`, identificativi GitHub e crediti trasparenti sulle tecnologie. Uso personale e beta per amici; nessuna trasformazione in azienda implicita.

## Esperienza primaria

L'utente apre l'app, sceglie una cartella o crea un progetto da zero, descrive un obiettivo e incarica il sistema di investigare, pianificare, delegare, modificare, testare, verificare, correggere, recuperare e completare. Il lavoro può durare molte ore, con limiti di spesa/tempo/risorse, stop e checkpoint; le decisioni che richiedono realmente la persona emergono come richieste chiare. Il completamento si misura dal prodotto e dai test, non dal numero di messaggi o commit.

- **Home NL** con progetti recenti, nuovo progetto, riprendi, missioni, connessioni modelli, stato motore.
- **NL Chat come superficie principale** (non un accessorio laterale). Editor, terminale, Git, debugger rimangono strumenti professionali.
- **Mission Control** con task graph, responsabilità degli agenti, handoff, code/steering, verifiche, diff, promozioni, motivazioni del router, cronologia.
- **Model Hub / Agent Factory** configurabili, ruoli specializzati non fissati, provider locali/cloud, benchmark e capacità reali.
- **Storage Manager** per progetti chiusi, cronologia, log e temporanei con anteprima e conferma.
- **Settings** con livelli di permesso distinguibili e controllo autonomo in `Settings → Advanced → Autonomous Development`; arresto emergenza accessibile sempre durante esecuzione.

## Visual design e brand

- L'asset sorgente di verità è il logo SVG personale e, se disponibile, `assets/theme.tokens.json`; mantenere la palette effettivamente estratta dagli asset. Riferimenti storici: violetto `#7531FE`, magenta `#E4469B`, accenti ciano, superfici scure leggibili.
- **Niente glow/neon sul testo, codice, log o timeline**; possibile luce sottile soltanto su logo/hero. Contrasto, dimensioni responsive, scorciatoie e focus keyboard, DPI/scaling verificati.
- Disattivare o de-enfatizzare nel profilo NL onboarding Copilot e pannelli upstream superflui; non compromettere funzioni Git/editor né distruggere i plugin dell'utente.
- Non presentare una singola extension installata come "prodotto standalone completo". La personalizzazione del workbench dovrà essere riproducibile in build/patch conservate.

## Qualità d'uso

Chat, missioni e goal non devono essere flussi isolati: una richiesta conversazionale può leggere il workspace, creare/aggiornare un goal e trasformarsi in una missione autorizzata, mantenendo il contesto; queue, steering, stop, resume e cronologia devono convivere in una UX coerente. In read-only il modello **può leggere** se READ è concesso, non può scrivere/eseguire.

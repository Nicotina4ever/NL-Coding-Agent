# SPEC-08 — Interfaccia professionale, identità NL e Self-Build in Avanzate

## Navigazione principale (orientativa, adattare al layout reale)

Home/Dashboard, Projects, Studio/Editor, Chat/Missions, Goals, Tasks, Agents, Model Hub, Files/Diff, Tests, Settings. Evitare sidebar enorme: viste aggregabili e ricerca comandi. Main area per lavoro quotidiano, non per controllo interno dello sviluppo del programma.

**Decisione UX esplicita dell'utente:** il tasto grande e vistoso per **autocostruzione, incremento funzionalità e sistemazione dell'app** non è professionale. **Rimuoverlo dalla schermata principale** o ridurlo a informazione discreta; collocare azioni per attivare/configurare Self-Build in `Impostazioni → Avanzate → Sviluppo autonomo` (o percorso equivalente). Distinguere:
- toggle opt-in per consentire self-build;
- piano e obiettivi selezionabili;
- schedule/modalità e limiti, policy repository, conferme;
- stato, risultati, storico e prove;
- pausa/ripresa/disabilita;
- azioni di test/diagnostica.

Quando un self-build è attivo, la missione compare naturalmente nel **Task Board/Missions/Activity** con progressi; pulsante **Stop/Pausa di emergenza** sempre accessibile durante lavori attivi, non nascosto in Avanzate. Il self-build non deve avviarsi da solo per mera apertura del software.

## Look

Utilizzare `assets/LogoMio.svg` e `assets/theme.tokens.json`: `#7531FE` violetto, `#E4469B` magenta, `#521B8D` deep purple, `#AB83C6` lavender, `#46A3C0` cyan. Superfici neutre scure, testo leggibile, tipografia e spaziature coerenti, indicatori semantici. **Niente glow** su codice, log, testi, parole trascritte, input e label; glow lieve solo decorazione/logo. Non inventare un nuovo branding.

Resizable panes, docking quando utile, layout salvato per progetto, toolbar compatta, command palette, status bar con modello/provider/CPU/RAM/VRAM/active mission, stati empty/loading/error/offline progettati. Accessibilità: focus keyboard, tooltip, contrasto, scaling/DPI; non bloccare thread UI.

Editor: usare componente mantenuto (Monaco via Qt WebEngine, CodeMirror 6 o altro) verificando size, performance, licensing e bridge sicuro; no “finto VS Code” monolitico. Mockup ≠ funzionalità; ogni pulsante deve compiere davvero l'azione dichiarata.

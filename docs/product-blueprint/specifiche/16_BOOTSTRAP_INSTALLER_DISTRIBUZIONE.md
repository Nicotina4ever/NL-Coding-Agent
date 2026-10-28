# SPEC-16 — Distribuzione: bootstrapper leggero, nessuna installazione globale

**Decisione utente:** non spedire necessariamente ~1,46 GB di portable Windows, soprattutto a chi usa Linux; preferire un piccolo bootstrapper **nativo per OS/arch** che scarica componenti precompilati verificati necessari e selezionati dall'utente, dentro una directory app dedicata. **Non introdurre uv come dipendenza di installazione.** Niente obbligo di installare globalmente Python, pip, Conda, Homebrew, Node o simili.

### Canali

- **Online lightweight bootstrapper:** programma nativo minimo con progress/repair/uninstall, scarica manifest e runtime+application bundle per piattaforma. Download HTTP(S) solo da origini consentite, checksum/verifica firma, atomically unpack/install, resume e rollback su bundle precedente. Backend inference e ASR soltanto opzionali.
- **Offline full package:** cartella portable o installer completo, un runtime privato e dipendenze dentro il bundle, modelli facoltativi generalmente esclusi.
- **Developer mode:** dipendenze bloccate e build riproducibili; non imporre al consumatore l'ambiente di sviluppo.

Il launcher non deve richiedere di aprire manualmente `pip install`; se manca componente essenziale avvia **Repair/Complete Installation** nella sua GUI o utility indipendente che funziona anche con runtime principale rotto. Il runtime può essere confezionato come bundle per piattaforma da CI, non un Python embedded Windows privo di pip spostato su altri OS. L'installer non ha bisogno di installare nel sistema Go/Rust/altro eventuale linguaggio usato per compilarlo.

### Primi passi e footprint

First Run: rileva sistema, architettura, CPU/GPU e permessi; stima dimensione download e storage; propone percorso scrivibile; controlla runtime e DLL/lib compatibili; verifica repo app; scopre server Ollama/LM Studio/llama.cpp esistenti e riusa modelli esterni con consenso. Installa plugin ASR selezionato (Qwen3-ASR ecc.) solo a richiesta. Unselect = non scaricare.

Directory logica: `launcher/`, `app/`, `runtime/`, `dependencies/`, `modules/`, `models/` *solo modelli owned*, `state/`, `logs/`, `repair/` (può essere layout OS-specific). Evitare duplicare runtimes senza ragione; in caso dipendenze ASR incompatibili, env/processo isolato solo per modulo opzionale, con motivazione.

### Legal, supply chain, validation

Audit licenze CrewAI e transitive deps, PySide6/Qt e modalità LGPL/commerciale, Python, binari di modello e FFmpeg eventuale; generare NOTICE e SBOM/manifest. App non include modelli senza verifica dei diritti; separare licenze pesi. Test indipendenza dai path dev, test install/update/repair, e no global writes non autorizzati. Il bundle online totale scaricato può comunque essere grande: **minore download iniziale non significa zero spazio finale**.

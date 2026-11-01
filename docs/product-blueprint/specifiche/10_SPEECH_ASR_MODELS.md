# SPEC-10 — Speech/ASR Manager opzionale e modulare

## Catalogo iniziale di motori (non scaricarli tutti)

- **Qwen3-ASR**: modelli ufficiali 0.6B e 1.7B; scelta modello/lingua, eventuale forced aligner opzionale; distribuzione/accesso/licenze da verificare nel manifest install.
- **Vosk**: modelli lingua-specifici small/full, molto leggeri per comandi e dettatura offline (es. italiano); selezione per lingua e dimensione.
- **Faster-Whisper**: tiny/base/small/medium/large o versioni compatibili (large-v3/turbo dove supportato), quantizzazione INT8 quando disponibile; hardware-aware.
- **WhisperX**: pipeline Whisper-compatible con opzioni allineamento, word timestamps e diarizzazione; dipendenze/asset addizionali e gating dei modelli quando necessario.

Ogni adapter dichiara lingue, formati, dimensione download, dimensione disco/runtime, disponibilità CPU/CUDA/Metal (secondo librerie effettive), latenza, qualità misurata sul PC, provenienza, licenza. Non dare per scontata la compatibilità cross-platform di qualsiasi versione di Torch o altri backend.

## UX e ciclo di vita

Speech/ASR disattivo di default senza rompere l'app. `Abilita` ≠ `Carica in RAM` ≠ `Installa` ≠ `Disinstalla` ≠ `Pulisci cache`. Consentire scelta e cambio motore/modello, più provider attivati ma uno o più selezionati per missione. In caso di disattivazione i checkpoint **rimangono** per default. Alla disinstallazione chiedere conferma dopo audit; eliminare solo asset posseduti dall'app e non condivisi/in uso, mai l'intera Hugging Face cache comune alla cieca.

Installazione on-demand: elenco di modelli predefiniti verificati e custom HF/repository path, source URL/revision/sha, dimensione reale/prevista e spazio disponibile, download riprendibile, checksum, progress/pause/retry; condivisione modelli già presenti via path esterno e senza copia automatica. Optional runtime isolated private in caso di dipendenze incompatibili con CrewAI, ma niente duplicati gratuiti per ogni ASR.

Speech-to-mission: registra da microfono o allega audio, trascrizione locale, lingua auto/manuale, editing prima invio, timestamp/diarizzazione solo quando supportati. Download/offline failure non deve impedire chat testuale e coding.

**Accettazione:** senza ASR installato app funziona; install 0.6B Qwen o Vosk testabile; toggle off preserva file; unload libera risorse; cache cleanup mostra ownership e chiede conferma; forced aligner non scaricato se non richiesto.

## Stato operativo (1 novembre 2026)

- **Vosk**: adaptatore locale attivo; modello italiano small in `data/speech/models/vosk-model-small-it-0.22` (circa 87 MB). È la dettatura leggera predefinita quando presente.
- **Qwen3-ASR**: riuso in place dell'installazione esistente `J:\ZLinkdaC\Qwen3ASR`, senza copiare il modello GGUF. La cartella può essere registrata da Settings o con `NL_QWEN3_ASR_HOME`; modelli esterni non vengono cancellati.
- **Faster-Whisper**: adapter mantenuto opzionale; richiede installazione locale esplicita.
- Il pulsante Dictate nella Chat registra localmente, trascrive e inserisce il testo nel composer; il testo resta modificabile e non viene inviato automaticamente.
- I modelli scaricati da NL Code restano sotto `data/speech/models`; quelli esterni sono referenziati per percorso.

NL CODING AGENT - BOOTSTRAP

DESTINAZIONE
------------
Copia il contenuto di questo pacchetto dentro:

K:\AI\NL Coding Agent\

La cartella python\ NON è inclusa: deve essere quella che hai già.
Le cartelle crewAI\ e crewAI-tools\ possono restare dove sono.

STRUTTURA FINALE MINIMA
------------------------
K:\AI\NL Coding Agent\
  python\
  crewAI\
  crewAI-tools\
  nl_coding_agent\
  config\
  state\
  logs\
  doctor.bat
  audit_voicebridge.bat
  work_voicebridge.bat
  status.bat

PRIMO AVVIO
-----------
1. Finisci l'installazione:
   python\python.exe -m pip install --no-cache-dir "crewai[litellm]"

2. Esegui:
   doctor.bat

3. Se tutto è OK:
   audit_voicebridge.bat

L'audit NON modifica NL VoiceBridge Studio.

4. Leggi:
   state\NL_VoiceBridge_Studio\audit.md

5. Per preparare un compito:
   work_voicebridge.bat

Questa versione bootstrap esegue:
Architect -> handoff -> Developer -> handoff -> Reviewer

e scarica il modello Ollama dopo ciascuno stadio con:
ollama stop <model>

MODELLI
-------
Architect:
  muse-glimmer:30b-q4_K_M

Developer:
  qwen3.5:9b

Reviewer:
  qwen2.5-coder:7b-instruct-q4_K_M

Cloud escalation:
  gpt-oss:120b-cloud
  DISABILITATO per default.

BACKUP VOICEBRIDGE
------------------
I due file:
  NL VoiceBridge Studio.rar
  NL VoiceBridge Studio.zip
sono configurati come protected_paths e non vengono usati dall'audit.

IMPORTANTE
----------
Questa è la fase bootstrap: serve a verificare orchestrazione, passaggi di consegne,
modelli e stato persistente SENZA ancora dare agli agenti il potere di modificare
o eseguire codice.

Dopo il primo audit riuscito, il passo successivo è aggiungere:
- file tools scoped al repository
- shell tool
- Git diff/status
- build/test auto-detection
- loop Developer -> Test -> Debug -> Review
- lock/scheduling per task
- escalation cloud opzionale

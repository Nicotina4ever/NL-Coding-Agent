# SPEC-05 — Model Hub multi-provider e capability registry

L'etichetta pubblica va da **"Ollama Models" → "Model Hub"**. Ollama rimane un adapter predefinito, non l'identità della funzionalità. Schede: AI Models, Providers, Speech/ASR, Resources/Storage, Download/Health.

Provider desiderati: Ollama, LM Studio, llama.cpp/server, endpoint OpenAI-compatible custom (ad es. Jan, LocalAI, vLLM dove compatibili); provider cloud opzionali dietro policy/consenso. Endpoint/porte configurabili, network discovery rispettoso della privacy; non presupporre che un server sia installato. Model inventory dinamico; refresh manuale e automatico senza bloccare GUI; offline, timeout, auth error, empty state e capability mismatch chiari.

Model registry per backend/model: id stabile, endpoint, provenienza, licenza se nota, cloud/local classification, tipi di input/output, tool calling testato, JSON schema/structured output, vision/audio se supportati, max context noto vs sperimentato, sampling params, quantizzazione/backend, resource data (measured vs estimated), version e timestamp. Possibilità di override manuale delle capabilities quando discovery incompleta.

`OpenAI-compatible` non garantisce tool calling multimodale né identica semantica dei parametri. Prevedere probe reali dei formati tool, code edits e output strutturato. Niente invio sorgenti a cloud prima di consenso esplicito e granularizzato. Fallback locale preferito, fallback cloud mai silenzioso.

Permettere modelli diversi per ruolo/agente, senza richiedere duplicati del modello; appuntare provider/versione/parametri per riproducibilità della missione.

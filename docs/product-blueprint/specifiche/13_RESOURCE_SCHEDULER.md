# SPEC-13 — Resource-Aware Scheduler e model lifecycle

Distingue **agenti logici**, **inference sessions**, **processi/worker** e **modelli in memoria**. Con RTX 4060 Ti da 8 GB + 32 GB RAM può essere preferibile una sola inferenza locale per volta e scaricare i modelli tra fasi; è un profilo iniziale, non un vincolo universale.

Misure: Ollama API/list/ps, NVML/nvidia-smi quando disponibili, psutil RAM/CPU, GPU su Linux/Windows/Metal quando strumenti supportati, API provider, tempo caricamento, token throughput, peak VRAM/RAM. Distinguere osservazione, stima e dato sconosciuto.

Scheduler considera: task graph e file ownership, priorità, scadenza se indicata, caratteristiche modelli, runtime caricamento, context budget, throughput, memory pressure, GPU/CPU load, modello condiviso da più ruoli. Prefetch solo se utile e entro budget. Load/unload su API native; non supporre che disabilitare agent cancelli modello o liberazione immediata VRAM. Possibilità `Unload model` e `Unload all owned idle models` senza cancellare checkpoint.

Concorrenza: parallelizzare scansioni/read-only e test indipendenti quando utile; inferenze parallele soltanto se misurato sostenibile; missioni che modificano stessi file richiedono lock/worktree/integrazione. QoS GUI: non bloccarla. Dare ragioni comprensibili per serialize/parallelize, con override dell'utente su limiti hardware.

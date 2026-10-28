# Resource Scheduler

## Hardware target

- RTX 4060 Ti 8 GB VRAM
- 32 GB system RAM
- Windows 11
- Ollama

## Core invariant

The agent graph may contain many logical agents without running many LLM generations
simultaneously.

Logical concurrency != model concurrency.

## Initial scheduling mode

`LOCAL_LLM_CONCURRENCY = 1`

Queue local inference stages.

Cloud-backed Ollama requests may be separately scheduled because they do not load the local model,
but privacy/quota policy still applies.

## Measurements

Prefer measured state:
- `ollama list`
- `ollama ps`
- Ollama API where useful
- `nvidia-smi` for GPU memory if available
- `psutil` for system memory

Do not infer free VRAM solely from model file size.

## Model lifecycle

Before stage:
- confirm Ollama;
- ensure task policy permits model;
- inspect memory;
- enqueue.

After stage:
- persist output/handoff;
- if another large local model is next or memory is pressured, call `ollama stop <model>`;
- confirm state when practical.

## Parallelism later

Allow concurrent work only if all conditions are satisfied:
- no overlapping write scope, or isolated worktree;
- resource scheduler permits;
- tasks are dependency-independent;
- parallelism provides value.

Read-only filesystem scans, compilation subprocesses, and UI work may overlap without implying
parallel LLM inference.

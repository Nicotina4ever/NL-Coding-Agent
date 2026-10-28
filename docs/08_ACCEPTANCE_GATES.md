# Acceptance Gates

## Gate A — Foundation

- existing CrewAI imports still work;
- tests run using `python\python.exe`;
- no additional Python environment created;
- vendor/runtime folders are not rewritten.

## Gate B — Project opening

- Open Project accepts an arbitrary folder;
- project appears in Recent Projects after restart;
- no project YAML is required;
- scan results are inspectable;
- project can be removed from the registry without deleting the actual folder.

## Gate C — Ollama

- app detects whether Ollama is reachable;
- model list comes from Ollama dynamically;
- loaded model state is shown when available;
- local/cloud policy can be configured from UI;
- unavailable resource metrics degrade gracefully.

## Gate D — GUI

- launcher works from `K:\AI\Coding Agent`;
- logo renders from the supplied SVG;
- design tokens are centralized;
- no text/code/log glow;
- main panels are resizable;
- UI remains responsive while audit/model work is running.

## Gate E — Audit

- audit works on at least the Coding Agent repo and one external project;
- audit does not modify the target project;
- findings are persisted;
- unknown/manual items are labeled rather than invented.

## Gate F — Operational coding

- one mission can produce a real source diff;
- tool scope is restricted to active project;
- verification command runs and its output is stored;
- failure routes through debug before completion;
- reviewer can reject;
- completion requires gates.

## Gate G — Self-build

- NL Coding Agent opens itself as a project;
- a self-build mission modifies its source through the normal tool path;
- candidate tests run separately;
- failed self-build does not erase last working source;
- next mission/state docs are updated.

## First Antigravity boost is complete when

Gates A through E pass and enough of F exists for the local product to continue implementing F/G
with substantially less external assistance.

# Multi-Agent Orchestration

## Roles are logical, models are interchangeable

Do not equate one role with one permanent model.

Initial logical roles:
- Architect / Planner
- Developer
- Debugger
- Reviewer
- Test/Verification Gatekeeper
- Researcher (optional)
- UI Specialist (optional)

A model router selects among available models based on:
- local/cloud policy;
- task type;
- task complexity;
- context need;
- historical success;
- current memory pressure.

## Initial practical model policy

Use as a starting profile only; inventory is dynamic.

- Architect: `muse-glimmer:30b-q4_K_M` when local deep planning is worth the slower stage.
- General Developer: `qwen3.5:9b`.
- Focused code review/small fixes: `qwen2.5-coder:7b-instruct-q4_K_M`.
- Cloud escalation: `gpt-oss:120b-cloud` only if user policy allows.

The UI must allow changing these mappings without editing YAML.

## Handoff contract

Every handoff is structured. Store:
- mission id;
- task id;
- sender role;
- receiver role;
- objective;
- current facts;
- files relevant;
- files modified;
- constraints;
- verification performed;
- unresolved issues;
- expected next output.

Do not hand a worker a giant conversation transcript when a concise structured handoff suffices.

## Task states

Suggested:
- DISCOVERED
- PLANNED
- READY
- RUNNING
- VERIFYING
- REVIEW
- BLOCKED
- MANUAL_CHECK
- COMPLETED
- FAILED
- CANCELLED

## Debug loop

On verification failure:
1. classify failure;
2. extract minimal relevant logs;
3. send failing command + error + diff + task contract to Debugger;
4. patch;
5. rerun only relevant checks;
6. broaden checks before final approval.

If the same failure signature repeats, escalate instead of looping forever.

## Reviewer independence

Reviewer should receive:
- task contract;
- diff;
- test results;
- key architecture constraints.

Reviewer should not merely repeat the Developer's narrative.
It can reject the task and return specific blockers.

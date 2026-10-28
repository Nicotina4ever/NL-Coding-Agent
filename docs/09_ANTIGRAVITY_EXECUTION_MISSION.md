# Antigravity Execution Mission

## Primary instruction

Read, in order:
1. `AGENTS.md`
2. `START_HERE_ANTIGRAVITY.md`
3. `docs/01_ARCHITECTURE.md`
4. `docs/02_SELF_BUILD_ROADMAP.md`
5. `docs/03_GUI_SPEC.md`
6. `docs/08_ACCEPTANCE_GATES.md`

Then inspect the existing source and execute the first boost.

## Delegation

Use the supplied custom agents:
- `nl-core-engineer`
- `nl-gui-builder`
- `nl-test-gatekeeper`

The `nl-self-build-lead` should coordinate and keep a task list.

Do not let multiple agents edit the same files concurrently.

## Stop conditions

Do not stop because a minor implementation detail is unspecified. Make a reasonable decision and
record it.

Stop/request user input only for:
- irreversible/destructive operation;
- missing external credential or service;
- ambiguity that changes the product goal materially;
- physical/hardware test that cannot be automated;
- permission to transmit private source to a cloud fallback when not already allowed.

## Required final report

Produce:
- features completed;
- tests/builds run and exact results;
- incomplete/manual checks;
- architecture deviations and why;
- `docs/CURRENT_STATE.md`;
- `docs/NEXT_SELF_BUILD_MISSION.md`.

The next mission must be executable by NL Coding Agent's own local orchestration path.

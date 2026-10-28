# NL Coding Agent — Antigravity Self-Build Pack

This pack is an **overlay** for the existing `K:\AI\NL Coding Agent` workspace.
It does not contain or replace the embedded Python, CrewAI checkout, CrewAI Tools checkout, or
current source.

## Install

Extract/copy the contents of this pack into:

`K:\AI\NL Coding Agent`

Allow merging folders.

Important files:
- `AGENTS.md`
- `START_HERE_ANTIGRAVITY.md`
- `.agents\...`
- `docs\...`
- `assets\LogoMio.svg`
- `assets\theme.tokens.json`
- `PASTE_THIS_IN_ANTIGRAVITY.txt`

## Start in Antigravity

1. Create/open an Antigravity Project pointing at `K:\AI\NL Coding Agent`.
2. Prefer a normal/local project for this first bootstrap if you want the agent to modify the real
   workspace directly; use an isolated worktree if your root is already a clean Git repo and you
   deliberately want that isolation.
3. Antigravity should automatically discover the root `AGENTS.md`.
4. Open the agent manager and select `nl-self-build-lead` if it appears.
5. Paste the content of `PASTE_THIS_IN_ANTIGRAVITY.txt`.
6. Let it implement and test.

The custom agents live under `.agents\agents\`.
The reusable self-build/UI procedures live under `.agents\skills\`.

## Suggested Antigravity permissions

Use a mode that allows normal edits and safe build/test commands while still gating destructive
operations. Do not use unrestricted destructive permissions merely to avoid prompts.

## Why there are still some Markdown files

These are not per-project setup files for end users.

They are the **constitution and engineering brief** used once to teach the initial builder how
NL Coding Agent should work. The product itself is explicitly required to replace per-project YAML
with one-click folder discovery and SQLite persistence.

## After the boost

Open NL Coding Agent itself from its new GUI and feed it the generated
`docs\NEXT_SELF_BUILD_MISSION.md`.

That is the intended handoff point from Antigravity to local self-build.

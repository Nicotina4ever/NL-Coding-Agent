# Legacy documentation and patch evidence

**Moved:** 2026-10-28 (repository hygiene follow-up, shared `task-34`).
**Rule:** these files are **preserved verbatim** as dated historical evidence. They are not
authoritative operational instructions. Do not edit them to reflect newer state; add a new
document under `docs/` instead. Do not execute any script or apply any patch kept here.

They were moved from the repository root with `git mv`, so file history is preserved
(`git log --follow`). No content was rewritten during the move.

## Mapping (old path -> new path)

| Old path (repository root) | New path | Type / purpose | Status |
|---|---|---|---|
| `README.txt` | `docs/history/legacy/README.txt` | Bootstrap-pack install readme (Italian); describes the first bootstrap layout and VoiceBridge audit/work entry points | Superseded by the root `README.md`; historical |
| `README_FIRST.txt` | `docs/history/legacy/README_FIRST.txt` | Antigravity self-build overlay install guide | Historical |
| `START_HERE_ANTIGRAVITY.md` | `docs/history/legacy/START_HERE_ANTIGRAVITY.md` | Bootstrap mission brief for the external Antigravity booster | Historical; superseded by `README.md` + `AGENTS.md` |
| `PASTE_THIS_IN_ANTIGRAVITY.txt` | `docs/history/legacy/PASTE_THIS_IN_ANTIGRAVITY.txt` | Ready-to-paste bootstrap prompt for Antigravity | Historical; do not paste as current instructions |
| `AUDIT_REALE_E_LIMITI.md` | `docs/history/legacy/AUDIT_REALE_E_LIMITI.md` | Safety-foundation audit and gap list that motivated the staged patch integration | Historical evidence (citations updated in `docs/BLUEPRINT_INDEX.md`, `docs/PRODUCT_BACKLOG.md`, `docs/product-blueprint/INDEX.json`) |
| `HANDOFF_DEEPSEEK_HARNESS.md` | `docs/history/legacy/HANDOFF_DEEPSEEK_HARNESS.md` | DeepSeek Harness handoff describing stub incidents #43/#45 and the original objective | Historical evidence |
| `FOUNDATION_CHANGES.patch` | `docs/history/legacy/patch-evidence/FOUNDATION_CHANGES.patch` | Unified diff of the audited Safety Foundation Patch | Historical evidence; the live sources already contain the applied result |
| `PATCH/**` | `docs/history/legacy/patch-evidence/PATCH/**` | Audited patch copies (byte-identical to the live sources at move time) plus `PATCH/WINDOWS_REAUDIT.md` | Historical evidence; `SHA256_MANIFEST.json` at the root still certifies the live files |

## Why they are not at the repository root

The root now carries exactly one authoritative entry point (`README.md`) plus the binding agent
rules (`AGENTS.md`). The files above were written for a completed bootstrap/mission phase and
contain dated commands and pre-rename context; keeping them at the root made the current state
ambiguous.

## References updated for the move

- `AGENTS.md` — points to the root `README.md` for overview/quick start.
- `.agents/agents/nl-self-build-lead/agent.md` — points to `README.md`.
- `docs/BLUEPRINT_INDEX.md` — evidence rows for the two historical audits updated to the new paths.
- `docs/PRODUCT_BACKLOG.md` — audit citations updated to the new paths.
- `docs/product-blueprint/INDEX.json` — `source_inventory` paths updated for the two historical audits.

## References intentionally left as historical records

These dated documents still contain the original root-relative names because they are records of
what was true when they were written; rewriting them would falsify history:

- `docs/WORKSPACE_MIGRATION.md` (completed relocation record)
- `docs/REPOSITORY_HYGIENE.md` (stage-5 read-only audit report)
- `docs/PHASE2_HARNESS_INTEGRATION_PLAN.md` (stage-2 design record; `PATCH/` references describe the
  historical integration step)
- `docs/09_ANTIGRAVITY_EXECUTION_MISSION.md` (historical bootstrap mission)
- `docs/product-blueprint/00_MASTER_INDEX.md`, `docs/product-blueprint/NOTE_SULLE_SPECIFICHE_PRECEDENTI.md`
  (blueprint provenance notes listing the originally delivered documents)
- `docs/evidence/sh07/attempt2/console.log` (raw acceptance log)

## Related documents

- `README.md` — current authoritative overview and quick start.
- `docs/REPOSITORY_STRUCTURE.md` — directory ownership and packaging limits.
- `docs/REPOSITORY_HYGIENE_FOLLOWUP.md` — measured before/after state, changes and remaining
  authorization proposals.
- `docs/REPOSITORY_HYGIENE.md` — the earlier read-only audit that identified these candidates.

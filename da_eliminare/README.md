# da_eliminare — review-only staging (nothing is deleted here)

This directory is the user-requested staging area for repository material that appears
**no longer needed**. It is deliberately excluded from the portable payload and from the
release builder.

## Rules

1. **Nothing in this directory may be deleted, archived elsewhere or removed from Git
   without explicit user authorization.** The Lead/owner must approve each item.
2. Items placed here are moved with `git mv` (history preserved) or left untracked; content
   is never rewritten or truncated during staging.
3. This directory is **not** an execution path and **not** a shipping location. Do not import,
   launch, package or deploy anything from it.
4. To restore an item, `git mv` it back to its original location and update references.
5. Anything still used by the application, tests, launchers, tooling, installer or
   documentation must not be moved here.

## Packaging exclusion

- Portable payload: `scripts/stage_portable.py` excludes the whole directory.
- Source release builder: `scripts/build_release.py` excludes the whole directory.
- Git: contents other than this README are git-ignored (see `.gitignore`).

## Current contents

- `README.md` — this policy note (the only tracked file).
- `crewAI/` — reference-only upstream CrewAI checkout (38,926 files / 807,816,022 B, including
  its nested `.git`), staged on 2026-10-28 by ROOT REORG Phase C (shared task-46). It is not
  imported by the application (the installed `crewai==1.15.32` package is the runtime), was moved
  here intact (never deleted, copied or rewritten), and its contents remain git-ignored and
  excluded from the portable payload and source release builder. Evidence, reversible restore and
  the open authorization item: [`../docs/CREWAI_CHECKOUT_REMOVAL_PROPOSAL.md`](../docs/CREWAI_CHECKOUT_REMOVAL_PROPOSAL.md).
  The SBOM/legal gate reads `crewAI/LICENSE` from this staged location; permanent deletion needs
  the owner to preserve that license evidence and authorize removal. Restore by moving the folder
  back to `crewAI/`.
- No other repository material is staged here: Phase A moved the one-off repair scripts to
  `docs/history/legacy/temp-scripts/` and the extra launchers to `scripts/launchers/`.

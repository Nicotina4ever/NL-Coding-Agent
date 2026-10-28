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
- No repository material has been staged here yet: Phase A left no proven-unnecessary
  tracked root leftovers after moving the one-off repair scripts to
  `docs/history/legacy/temp-scripts/` and the extra launchers to `scripts/launchers/`.

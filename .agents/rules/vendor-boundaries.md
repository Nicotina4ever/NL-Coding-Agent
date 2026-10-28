---
trigger: always_on
description: "Protect embedded runtime, vendor repositories, caches and backup files."
---

# Vendor Boundaries

Do not modify source inside:
- `python/`
- `da_eliminare/crewAI/` (staged vendor reference; deletion requires explicit owner authorization)
- `crewAI-tools/` (when present)

Package installation into the embedded Python is allowed via pip, but do not hand-edit runtime
library files.

The crewAI reference checkout is staged under `da_eliminare/` after the root-reorganization Phase C;
that staging area is review-only and nothing inside it may be deleted, archived elsewhere or removed
from Git without explicit owner authorization. Do not recursively scan vendor directories as if they
were NL Coding Agent product source unless a task explicitly concerns them.

Do not create backup archives or duplicate model/runtime directories.

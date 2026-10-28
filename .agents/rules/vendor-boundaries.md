---
trigger: always_on
description: "Protect embedded runtime, vendor repositories, caches and backup files."
---

# Vendor Boundaries

Do not modify source inside:
- `python/`
- `crewAI/`
- `crewAI-tools/`

Package installation into the embedded Python is allowed via pip, but do not hand-edit runtime
library files.

Do not recursively scan vendor directories as if they were NL Coding Agent product source unless
a task explicitly concerns them.

Do not create backup archives or duplicate model/runtime directories.

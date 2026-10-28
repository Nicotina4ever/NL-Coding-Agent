---
trigger: glob
globs: "**/*.py, requirements*.txt, pyproject.toml"
description: "Python runtime and dependency rules for NL Coding Agent."
---

# Python Runtime Rules

- Target `K:\AI\NL Coding Agent\python\python.exe` Python 3.12.
- Do not create a virtualenv, Conda env, Poetry env, or uv-managed duplicate runtime.
- Install necessary packages directly using `python\python.exe -m pip`.
- Prefer stdlib and existing dependencies; justify new dependencies.
- Keep GUI and backend importable without changing current working directory.
- Use pathlib for Windows paths.

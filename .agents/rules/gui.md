---
trigger: glob
globs: "nl_coding_agent/gui/**/*.py, **/*.qss, **/*theme*.json"
description: "NL Coding Agent GUI design and architecture rules."
---

# GUI Rules

- Use `assets/LogoMio.svg`.
- Design tokens come from `assets/theme.tokens.json`.
- No glow on body text, code, filenames, task text, or logs.
- Keep business logic out of widgets.
- Long tasks run off the UI thread and report structured events.
- Use resizable splitters/panels.
- Ensure high contrast and keyboard usability.
- Do not imitate Cursor branding/assets; only borrow the productive multi-pane interaction pattern.

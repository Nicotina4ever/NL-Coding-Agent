# GUI / Design Specification

## Product personality

Professional creative-technical workstation.
Dense enough for development work, calmer than a gaming dashboard.
The brand can feel luminous; the information must remain crisp.

## Source of truth

Use:
- `assets/LogoMio.svg`
- `assets/theme.tokens.json`

The core brand colors are extracted from the actual supplied SVG, not guessed.

## Visual rules

- Dark background.
- Thin borders and layered surfaces rather than giant shadows.
- Electric violet as the primary action/focus accent.
- Magenta for selected creative/agent identity accents.
- Cyan for information, resource/connection states and secondary technical accents.
- Rose for optional contrasting emphasis.
- Do not render paragraphs, code, log text or filenames with glow.
- Do not use neon outlines around every component.
- Logo/hero accents may use a subtle bloom.
- High-contrast code/log typography.

## Suggested desktop composition

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ logo  NL CODING AGENT          project                         Ollama ● │
├──────────────┬────────────────────────────────┬─────────────────────────┤
│ Projects     │                                │ Mission / Inspector     │
│              │      MAIN WORKSPACE            │                         │
│ Files        │                                │ Active Agent            │
│ Tasks        │  Project Overview / Task Board │ Handoff                 │
│ Agents       │  Diff / Code later             │ Verification            │
│ Models       │                                │                         │
│              │                                │                         │
├──────────────┴────────────────────────────────┴─────────────────────────┤
│ Logs / Terminal / Event stream                              VRAM  RAM   │
└─────────────────────────────────────────────────────────────────────────┘
```

Resizable splitters are required.

## Launch/Home screen

Primary action:
**Open Project**

Secondary:
- recent projects;
- "Open NL Coding Agent (Self Build)";
- Ollama connection status.

No setup wizard asking the user to author config files.

## Project dashboard

Show:
- project name/path;
- detected stack;
- documentation found;
- Git state;
- last audit;
- missions/tasks;
- unresolved manual verification;
- current workers/model.

Prominent actions:
- Audit
- New Mission
- Resume
- Project Settings

## Agent/Task visualization

Each task card shows:
- state;
- role;
- model;
- dependencies;
- files/write scope;
- last verification;
- retry count.

Agent state should distinguish:
- idle;
- waiting dependency;
- reasoning;
- editing;
- running tools;
- verifying;
- blocked;
- completed.

## Resource bar

Display live:
- Ollama connected;
- current model;
- loaded model(s);
- GPU VRAM where available;
- RAM;
- task queue.

Do not fabricate metrics if collection fails; show unavailable.

## First GUI technology

PySide6 widgets are preferred for the first stable version:
- QMainWindow
- QSplitter
- QTreeView/QListView
- QStackedWidget
- QDockWidget where useful
- custom item delegates sparingly
- QSvgWidget or QSvgRenderer for logo
- centralized QSS/theme tokens

Keep UI logic in controllers/services, not widget event handlers full of business logic.

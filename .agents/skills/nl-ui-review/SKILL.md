---
name: nl-ui-review
description: Verifica la GUI di NL Coding Agent, la coerenza con il logo e la palette, la leggibilità e il comportamento dei pannelli.
---

# NL UI Review

Review the current desktop UI against:
- `docs/03_GUI_SPEC.md`
- `assets/theme.tokens.json`
- `assets/LogoMio.svg`

Check:
1. Brand consistency.
2. Readability at normal Windows scaling.
3. No glow on text/code/logs.
4. Resizable multi-pane layout.
5. Clear active project/model/task state.
6. No blocking model/build work on the GUI thread.
7. Empty/error/loading states.
8. Consistent spacing and typography.
9. Keyboard navigation for primary actions.
10. Visual evidence: capture screenshots when the environment supports it and compare behavior
    across the Home, Project, Tasks and Models views.

Report issues by severity and include concrete remediation.

# Studio GUI screenshot evidence (U2)

Status: measured real-window evidence, not a human aesthetic approval.

## Command

    python scripts/capture_gui_screenshots.py

The script launches the actual Studio on the current Windows Qt platform (the
child process removes QT_QPA_PLATFORM/QT_OPENGL), stubs the local Ollama probe,
runs a bounded interaction sequence (Projects/Files/Tasks/Goals/Settings page
navigation, Open Project dialog shown/closed, Settings Advanced visibility,
Inspector project/mission summaries and expanded diagnostics, self-build placement
check) and grabs the real window. No model, network or mission is started.

## Measured artifacts

| File | Requested logical size | Requested DPI | Measured pixels | Platform | Result |
|---|---|---|---|---|---|
| STUDIO_1280x800_DPI100.png | 1280x800 | 1.0 | 1280x800 | windows | saved |
| STUDIO_1600x1000_DPI125.png | 1600x1000 | 1.25 | 2000x1250 | windows | saved |
| STUDIO_1920x1080_DPI150.png | 1920x1080 | 1.5 | 2880x1421 | windows | saved |

All three captures reported self_build_absent=true, the Open Project dialog title,
Settings Advanced visible=true and saved=true. The DPI 1.25/1.5 PNGs are larger
because Qt scale factors multiply logical pixels; the 1.5 capture was physically
clamped at 1421 px height by the available desktop, so it is not a strict
2880x1620 capture.

## Inspected screenshot

docs/evidence/gui/STUDIO_1280x800_DPI100.png was visually inspected: the Studio
shell shows the token-based header/activity badge, Project identity line, compact
Projects page with only the subtle Advanced self-build link, structured Inspector
cards (Project/Mission/Agent/Verification/Activity), diagnostics tree and status
bar. The screenshot confirms visual hierarchy and readable status; this is
functional/visual evidence, not human aesthetic sign-off.

## Limitations / MANUAL-PENDING

- Host desktop, font availability (Qt emitted a QFontDatabase "no fonts" warning on
  this embedded runtime) and OS DPI scaling vary; exact layout on other hardware is
  untested.
- The interaction sequence is scripted and bounded; real project content, real
  missions, live services and accessibility with a screen reader remain
  MANUAL-PENDING.
- No human design review, no model/network/mission run, and no publication.

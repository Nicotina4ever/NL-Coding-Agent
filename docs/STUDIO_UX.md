# Studio UX U2/U4 - visual polish, layout fixes and evidence (NL-BP-238/239/240/241)

## Design system

The verified NL token file assets/theme.tokens.json remains the single source of
truth. gui/theme.py derives typography (display/title/section/body/small/micro),
spacing (4/8/12/16/24), density (row 26, card min-height 64, header 44) and radius
scales, plus component QSS for section headers, summary cards, status badges and
empty/loading states. Palette use is restricted to the NL identity: electric violet
#7531FE, magenta #E4469B, deep purple #521B8D, rose #BA266C, lavender #AB83C6 and
cyan #46A3C0, with the existing neutral/semantic tokens. There is no unrelated
palette, and no text/code/log glow: token rules and component QSS contain no
text-shadow/box-shadow rules. Decorative glow remains logo/accent-only by policy.

gui/components.py provides reusable section headers, summary cards, status badges,
empty states and card rows used by the Inspector and page chrome. Existing panels
keep their functionality and translations; primary surfaces now use token-derived
styles where practical.

## Information architecture

- Projects: the prominent "Self-Build (This Agent)" header action is removed. A
  subtle "Advanced self-build…" link remains at the right edge with a tooltip
  pointing to Settings > Advanced > Autonomous Development. Opened vs Selected
  project identity is shown explicitly and a differing selection is marked.
- Settings > Advanced: the existing activation/configuration controls remain the
  only place where autonomy mode/limits are changed; a visible "Self-Build (This
  Agent) — Advanced controls" heading makes the placement explicit. Saving never
  starts autonomy by itself.
- Header/status: the opened project is labelled "Opened: …"; a status badge shows
  IDLE / RUNNING / PAUSED / BLOCKED with the current mission title when known.
  Emergency Pause/Stop remain in the always-reachable status-bar widget.
- Progress remains visible through Goals, Tasks, activity and the existing status
  widgets; no new execution behavior was added.
- Inspector: the raw QTextEdit wall is replaced by five structured summary cards
  (Project, Mission, Agent, Verification, Activity), an activity badge, and an
  expandable diagnostics tree retaining raw facts/evidence/errors and file text.
  Copy/export was not present before and was not removed.
- U4 layout fixes: inspector labels/cards wrap and expand, the inspector scrolls
  vertically only (horizontal scrollbar disabled at 1280), cards sit in a vertically
  scrollable upper pane and diagnostics in a visible lower split pane with a
  stretch-last detail column; the splitter gives the inspector a 268 px minimum /
  ~300 px default width while preserving user resizing. Projects uses a compact
  empty-state card (Open Project + recent-project guidance) instead of a blank box.
  Header opened/activity/autonomy labels have bounded widths at 1280/1600.

## Verification and evidence

- tests/test_inspector_panel.py covers cards/diagnostics/raw retention.
- tests/test_gui_status_state.py covers self-build placement, opened/selected
  identity and design-token/no-unrelated-palette/no-glow guards.
- GUI smoke/headless smoke and the 11-page shell remain green.
- scripts/capture_gui_screenshots.py launches the real Studio (Windows platform),
  runs a bounded page/dialog/Settings/Inspector sequence, verifies self-build
  absence and captures PNGs at 1280x800 DPI 1.0, 1600x1000 DPI 1.25 and
  1920x1080 DPI 1.5. Measured artifacts and limitations are in
  docs/evidence/gui/SCREENSHOTS.md.

## Manual-pending / limits

- No human aesthetic sign-off was performed; evidence is measured screenshots plus
  automated structural/accessibility checks.
- DPI behaviour depends on the host desktop; the third capture measured
  2880x1421 physical pixels because the OS clamped the logical window height.
  Other desktop/DPI hardware may differ.
- Real project content, real missions/runs and full interaction tests with live
  services remain MANUAL-PENDING. No model/network/mission was run.

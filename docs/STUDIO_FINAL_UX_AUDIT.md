# Studio Final UX - Capability Audit (read-only)

**Task:** shared task-87. **Date:** 2026-10-29 (Europe/Rome). **Repository:** K:\AI\NL Coding Agent at git HEAD b57020b (clean working tree before this task).
**Type:** read-only GUI/UX capability audit + queue-only backlog extension. **No implementation, no application code change, no model/network/mission/GUI run was performed.**
**Directive under audit:** final Studio GUI UX acceptance (localization, visual/information-architecture polish, self-build placement/runtime UX, Inspector/state clarity, real-GUI evidence) - user directive 2026-10-29, queue only.

---

## 1. Executive summary

The Studio shell is functionally rich (Projects, Files, Tasks, Chat, IDE, Research, Goals, Agents, Model Hub, Settings; NL logo/tokens/dark theme; Goals/Task/Inspector/log/status surfaces; Settings > Advanced autonomy controls; emergency pause/stop) and its requirements NL-BP-020/021/022/023/024/044/045/046 are verified/partial, with NL-BP-190 (visual quality lab) planned. However the **final UX acceptance layer is genuinely missing**:

- **No UI internationalization/localization:** no QTranslator/translation catalogs, no UI-language setting, no locale persistence; all panels/dialogs/menus/tooltips/errors are hardcoded English. (Locale utilities exist only for unrelated CLI/agent/encoding paths, not UI translations.)
- **Visual design/information architecture is not final:** verified brand shell + theme tokens, but the GUI carries **82 setStyleSheet calls and 110 hardcoded hex colour literals** across widgets (inline styling bypassing tokens), with ad-hoc typography/spacing/density, no consolidated reusable components, and limited responsive behaviour beyond splitters/minimum sizes.
- **Self-build placement is not the accepted UX:** a prominent **"Self-Build (This Agent)" button remains in the Projects page** (projects_panel.py:34-37, 121-125), while the intended UX puts activation/configuration under **Settings > Advanced** (settings_panel.py:101-102), with progress in Goals/Tasks and emergency stop accessible during execution. NL-BP-023/024 remain partial and must be reused, not duplicated.
- **Inspector is a raw technical wall:** inspector_panel.py is a single read-only QTextEdit fed HTML/plain dumps; no structured summaries, collapsible diagnostics or severity grouping.
- **Project/open/activity state is ambiguous:** the header shows only the project name and the status bar VRAM/RAM/tasks; project-list selection is not the opened project; activity (indexing/auditing/supervisor/mission) is split across transient log lines/status labels with no unambiguous global state.
- **GUI evidence is offscreen-only:** tests force QT_QPA_PLATFORM=offscreen (tests/test_gui_smoke.py:1-3); docs/HARNESS_ACCEPTANCE.md:152-163 lists real-desktop focus/DPI/dialogs and real clipboard/drag-drop as MANUAL-PENDING; there are **no real-GUI screenshots** in docs/evidence/ (only vendor images under da_eliminare/crewAI, excluded). No functional interaction test suite exists for real window behaviour.

Five genuinely missing acceptance requirements were appended to the existing **program stage 4** (no new stage/framework): **NL-BP-237..241**, all P0, status planned.

## 2. Method and evidence rules

- Static read-only inspection of nl_coding_agent/gui/**, assets/theme.tokens.json, tests/test_gui_smoke.py, docs/HARNESS_ACCEPTANCE.md and docs/product-blueprint/INDEX.json; commands in section 8.
- No GUI was launched (not even offscreen) by this audit; existing tests/docs were read, not executed.
- "Implemented" here means code exists; it is not final UX acceptance.

## 3. Existing GUI evidence

### 3.1 Shell, navigation and pages

| Evidence | Finding |
|---|---|
| gui/main_window.py (MainWindow composition; panels wired via services; Inspector/log/status bar) | functional shell with header, sidebar, stacked pages, Inspector, log and status bar; project-open fan-out at _on_project_opened (lines 572-590) |
| gui/widgets/sidebar.py:8-19 | pages: Projects, Files, Tasks, Chat, IDE, Research, Goals, Agents, Model Hub, Settings - navigation exists (NL-BP-021 partial) |
| gui/widgets/task_board.py; gui/widgets/goals_panel.py:303-1632 | Tasks + Goals surfaces exist (Goals has goal/missions/activity/tasks/versions/evidence/milestones/progress tabs) |
| gui/main_window.py:120-161 | emergency pause/stop control block (NL-BP-024 partial): visible per supervisor status, pause/stop buttons |
| gui/widgets/settings_panel.py:101-200 | "Advanced - self-build and autonomy" group: autonomy mode, missions/run, attempts, wall-clock, read-only plan preview, history table, Save/Pause controls (NL-BP-023 partial) |
| gui/main_window.py status/log surfaces | status labels + log panel; no notification centre/toast system |

### 3.2 Branding, theme and tokens

| Evidence | Finding |
|---|---|
| assets/theme.tokens.json; gui/theme.py | real NL palette tokens and stylesheet (sidebar, buttons, inspector, status colours); NL-BP-020 verified |
| gui/main_window.py (logo/icon) | real LogoMio.svg used for window icon/header |
| grep measurement | **82 setStyleSheet calls** and **110 hardcoded hex colour literals** across gui/**, including inline #46A3C0/#7E8798 styles in panels (e.g. projects_panel.py:31,35,47); token coverage is partial and component styling ad hoc |
| gui/theme.py | one global stylesheet with fixed font sizes (13px etc.); no responsive typography/density system; no component library |

### 3.3 Localization/i18n

| Evidence | Finding |
|---|---|
| grep QTranslator/tr(/gettext/i18n/language in gui/** | **no UI translation infrastructure**; user-visible strings are hardcoded English (e.g. "Projects", "Self-Build (This Agent)", "Open Project...", "Autonomy mode", dialog titles/messages) |
| persistence/**, app/services.py, cli.py grep language/locale | no UI-language setting/persistence; locale occurrences are encoding/LSP-related only |
| settings_panel.py | no language selector; Settings page surfaces project/database/Ollama/model/cloud/advanced autonomy only |
| tests/ | no localization/translation tests |

### 3.4 Self-build placement and runtime UX

| Evidence | Finding |
|---|---|
| gui/widgets/projects_panel.py:34-37 | prominent **"Self-Build (This Agent)"** button in the Projects header, styled with a distinct colour |
| gui/widgets/projects_panel.py:121-125 | handler just opens the repo root as a project and emits project_opened - no explicit activation/confirmation flow |
| gui/widgets/settings_panel.py:101-102 | intended "Advanced - self-build and autonomy" controls exist in Settings |
| gui/main_window.py:120-161 | emergency pause/stop block accessible; Goals/Tasks pages show progress |
| Requirements | NL-BP-023 (Settings > Advanced controls) partial; NL-BP-024 (emergency stop) partial - both retained and reused, not duplicated |

### 3.5 Inspector and project/activity state clarity

| Evidence | Finding |
|---|---|
| gui/widgets/inspector_panel.py (single read-only QTextEdit, show_project/show_mission render HTML/plain dumps) | raw technical text wall; no structured summary cards, collapsible sections, severity grouping or diagnostics export |
| gui/main_window.py:572-590 | on open: project name into header label, inspector gets facts, panels receive project; no explicit "opened vs selected" indicator outside the Projects list selection |
| gui/main_window.py header/status | header project label + Ollama/VRAM/RAM status and transient log messages; no single unambiguous activity model (idle/indexing/auditing/supervisor running/mission running) and no persistent current-activity indicator |
| gui/widgets/projects_panel.py:75-125 | list selection only enables buttons; open is a separate double-click/emit action - selection state and open state can diverge without clear UI feedback |

### 3.6 Real-GUI evidence

| Evidence | Finding |
|---|---|
| tests/test_gui_smoke.py:1-3; tests/test_gui_panels.py and other GUI tests | force QT_QPA_PLATFORM=offscreen; widget construction/read-only rendering only |
| docs/HARNESS_ACCEPTANCE.md:152-163 | F1/F3 rows explicitly list real desktop drag-and-drop, Windows clipboard screenshot, real PDF/Office extraction, real desktop focus/DPI/dialogs and live LSP/MCP/debugger sessions as **MANUAL-PENDING** |
| docs/evidence/ | no real-GUI screenshots; GUI evidence is offscreen test output/logs |
| Requirement NL-BP-190 | planned visual quality lab (screenshot baselines/DPI/accessibility); NL-BP-044/045 partial (accessibility/responsive states) - extended, not duplicated |

### 3.7 Existing requirements retained unchanged

| ID | Status | Relevance |
|---|---|---|
| NL-BP-020 | verified | shell/branding/theme/tokens - retained |
| NL-BP-021 | partial | navigation/panels/inspector/log/status - retained; 238/240 extend |
| NL-BP-022 | partial | Settings surfaces - retained; 237 adds language setting, 239 advanced activation |
| NL-BP-023 | partial | self-build controls under Settings > Advanced - retained; 239 adds placement/runtime acceptance |
| NL-BP-024 | partial | emergency pause/stop always reachable - retained; 239 references |
| NL-BP-044 | partial | accessibility/usability incl. DPI/focus/shortcuts - retained; 241/238 extend |
| NL-BP-045 | partial | non-blocking explicit states - retained; 238/240 extend |
| NL-BP-046 | partial | project dashboard/agent-task visualization - retained; 240 extends state clarity |
| NL-BP-190 | planned | visual quality lab - retained; 241 extends to real-GUI evidence |

## 4. Directive capabilities vs current state

| Directive capability | Exists today? | Comment |
|---|---|---|
| UI i18n/localization (Italian default, English + extensible catalogs, manual/OS detection, persisted, all UI strings, separate from agent/code/docs language) | **No** | none of the i18n infrastructure/settings exists |
| Visual design/IA polish (typography/spacing/density/navigation/panels/responsive/hierarchy/reusable components/status reporting; real palette, no glow) | **Partial** | brand shell/tokens verified but 82 inline styles/110 hardcoded colours, ad-hoc density/typography, no component system |
| Self-build placement/runtime UX (remove Projects action; activate under Settings > Advanced; progress in Goals/Tasks; emergency stop) | **Partial** | Settings controls and stop exist; prominent Projects button remains and activation flow not accepted |
| Inspector structured summaries/expandable diagnostics + unambiguous project/activity state | **No** | raw QTextEdit; state split across transient labels/log |
| Real-GUI visual/interaction acceptance evidence (screenshots at sizes/DPI + functional interaction tests, not only offscreen) | **No** | offscreen tests only; manual-pending list; no screenshots |

## 5. Dedupe mapping (directive sub-capability -> existing ID / new ID)

| Sub-capability | Existing coverage | New requirement | Decision |
|---|---|---|---|
| Branding, logo, tokens, dark theme shell | NL-BP-020 (verified) | - | retained; no duplication |
| Navigation/panels/inspector/log/status bar | NL-BP-021 partial | NL-BP-238/240 | 021 retained; final IA polish and structured Inspector extend it |
| Settings surfaces | NL-BP-022 partial | NL-BP-237/239 | 022 retained; language setting and advanced activation extend it |
| Self-build controls under Settings > Advanced | NL-BP-023 partial | NL-BP-239 | 023 retained; placement/runtime acceptance extends it |
| Emergency pause/stop always reachable | NL-BP-024 partial | - (used by 239) | retained; no duplicate |
| Accessibility/focus/DPI/shortcuts | NL-BP-044 partial | NL-BP-241/238 | 044 retained; real-GUI evidence/visual polish extend it |
| Non-blocking responsive UI and explicit states | NL-BP-045 partial | NL-BP-238/240 | 045 retained |
| Project dashboard/agent-task visualization | NL-BP-046 partial | NL-BP-240 | 046 retained; state clarity extends it |
| Visual quality lab / screenshot baselines | NL-BP-190 planned | NL-BP-241 | 190 retained; real-GUI evidence extends it |
| Goals/Tasks progress surfaces | NL-BP-216 (Goals GUI), task board 046 | - (used by 239) | retained |
| UI internationalization/localization | - | NL-BP-237 | genuinely new |
| Visual design/IA polish with reusable components | - | NL-BP-238 | genuinely new acceptance layer |
| Self-build placement/runtime UX acceptance | - | NL-BP-239 | genuinely new acceptance over 023/024 |
| Inspector structured summaries + project/activity state clarity | - | NL-BP-240 | genuinely new |
| Real-GUI screenshot/interaction evidence | - | NL-BP-241 | genuinely new acceptance over 044/190 |
| Notification centre/toasts | - (log/status + QMessageBox only) | folded into 238/240 status reporting | no separate requirement |

## 6. New requirements appended to existing program stage 4 (status planned)

| ID | Priority | Area | Dependencies | Summary |
|---|---|---|---|---|
| NL-BP-237 | P0 | studio | 020, 022, 044 | Internationalization/localization: UI default Italian for initial installation, English + extensible catalogs, manual selection + optional OS-language detection, persisted across restart, consistent menus/dialogs/tooltips/errors/notifications; UI language separate from agent-response/code/documentation language |
| NL-BP-238 | P0 | studio | 020, 021, 044, 045 | Studio visual design and information architecture polish: typography/spacing/density/navigation/panels/responsive layouts/hierarchy/reusable components/readable status reporting; real NL palette/identity, no unrelated palette or distracting glow |
| NL-BP-239 | P0 | studio | 023, 024, 046, 216 | Self-build placement and runtime UX: remove prominent Projects-page Self-Build action, activation/configuration under Settings > Advanced > Autonomous Development, progress in Goals/Tasks, emergency stop accessible during execution; reuse NL-BP-023/024 rather than duplicating them |
| NL-BP-240 | P0 | studio | 021, 022, 045, 046 | Inspector structured summaries + expandable diagnostics; unambiguous project selection/open state and current application activity |
| NL-BP-241 | P0 | studio | 020, 021, 044, 190 | Real-GUI visual/interaction acceptance evidence: real screenshots at multiple window sizes/DPI and functional interaction tests, not only offscreen widget tests; extends NL-BP-190/044 |

## 7. Program effect (existing stage 4 reopened, no new stage)

- Program stage 4 ("Complete CrewAI integration, model intelligence, GUI, multimodal and voice capabilities") was marked **completed**; the final UX acceptance reopened by this directive means its status/note are corrected honestly to **in_progress - engineering complete; final UX acceptance reopened by the 2026-10-29 directive**.
- Stage 4 requirement membership is extended with NL-BP-237..241 (45 requirements). Stages 1-3/5-10 statuses, requirement IDs and acceptance are untouched. No new stage/framework was created.
- Stage 4 status change is a **program-level honesty correction**, not a downgrade of existing requirement evidence: 020 remains verified; 021/022/023/024/044/045/046/190 keep their statuses.

## 8. Blockers, risks and human/external decisions

- **No new stage**: final Studio UX remains stage-4 work; no implementation started by this audit.
- **Italian-default localization** requires a real translation catalog/QA pass (machine translation alone is not acceptance); other languages remain optional/extensible.
- **Real-GUI evidence is manual/pending by nature**: screenshots at multiple sizes/DPI, Windows clipboard/drag-drop and real dialogs cannot be produced by offscreen tests; hardware/OS evidence must be labelled real-manual, not fabricated.
- **Self-build button removal**: must preserve current project-open ability for the self-build repo via a non-prominent, documented path; removing it without Settings activation proof would break the accepted flow (NL-BP-023/024).
- **Inspector redesign** must not hide evidence/errors; structured summaries need expandable raw diagnostics for traceability.
- **Theme cleanup** must preserve the verified NL identity/tokens and the no-glow rule; no unrelated palette.
- **Offscreen tests are not interaction evidence**: existing CI/offscreen guarantees remain valid but cannot satisfy NL-BP-241.
- **No commit/code/GUI run** was performed by this task; the repository owner decides acceptance and commits.

## 9. Verification commands used (read-only; no GUI/model/network runs)

- File reads: nl_coding_agent/gui/main_window.py (composition/header/status/emergency/project-open fan-out), gui/widgets/sidebar.py:8-19, gui/widgets/projects_panel.py:1-200, gui/widgets/settings_panel.py:101-560, gui/widgets/inspector_panel.py (full), gui/widgets/goals_panel.py (class/tab inventory), gui/theme.py, assets/theme.tokens.json.
- greps: setStyleSheet (82 occurrences) and hex colour literals (110 occurrences) across gui/**; QTranslator|tr(|gettext|i18n|language|locale; statusBar|QMessageBox|notification|toast|showMessage.
- Evidence docs: docs/HARNESS_ACCEPTANCE.md:152-163 (MANUAL-PENDING real-desktop/GUI items), tests/test_gui_smoke.py:1-3 (offscreen), docs/evidence/ image inventory (no real GUI screenshots; vendor images only under excluded da_eliminare/crewAI).
- Requirement statuses read from docs/product-blueprint/INDEX.json: 020 verified; 021/022/023/024/044/045/046 partial; 190 planned; stage 4 completed before this import.
- No GUI launch, model, mission or network operation was executed.

## 10. Change record

New documentation file and the queue-only backlog update it justifies. The preserved addendum bundle under docs/product-blueprint/addenda/ is unchanged. No application code, tests, configuration, GUI, models, missions or network state were changed, and no commit was created by this task.

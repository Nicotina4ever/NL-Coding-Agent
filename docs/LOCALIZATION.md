# Studio UI localization (U1, NL-BP-237)

**Status:** implemented for the existing desktop Studio. Italian is the installation
default, English is the second catalog, and the Settings language selector switches the
UI live and persists the preference in the existing SQLite application settings.
Remaining untranslated strings are tracked honestly under Coverage/limits below.

**Implementation:** @@BT@@nl_coding_agent/gui/i18n.py@@BT@@, catalogs in
@@BT@@nl_coding_agent/gui/locales/it.json@@BT@@ and @@BT@@.../en.json@@BT@@; presentation
wiring in the sidebar, main window, Settings, Projects, Inspector and Open Project
dialog; persistence in @@BT@@AppServices.ui_language_preference/set_ui_language@@BT@@.

## Behavior

- Fresh installation defaults to **Italian** by policy. The value is not inferred from
  the OS unless the user explicitly selects @@BT@@System (auto)@@BT@@.
- Explicit selections are @@BT@@it@@BT@@, @@BT@@en@@BT@@ and @@BT@@system@@BT@@. @@BT@@system@@BT@@ (also accepted as
  @@BT@@auto@@BT@@ at the persistence boundary) maps the OS locale to the closest supported
  catalog (currently @@BT@@it@@BT@@ / @@BT@@en@@BT@@) and falls back to Italian when unsupported or
  unknown.
- Resolution order: **explicit persisted preference > OS detection only for
  system/auto > Italian default**. Invalid persisted values fall back to Italian.
- The preference is stored in the existing application SQLite database under
  @@BT@@app_settings.ui.language@@BT@@. There is no destructive migration and no separate
  settings store. Restarting the app or reconstructing @@BT@@AppServices@@BT@@ preserves the
  selection.
- Changing the selector updates the running UI immediately (QTranslator plus explicit
  widget retranslation hooks) and then persists. No restart is required.
- UI language is presentation-only. It is **separate from agent response language,
  generated code language and documentation language**; no prompt, model setting,
  provider setting or code-generation language is changed by this feature.

## Catalog format

@@FENCE@@json
{
  "locale": "it",
  "name": "Italiano",
  "version": 1,
  "strings": {
    "sidebar.projects": "Progetti",
    "projects.open": "Apri progetto…",
    "status.tasks_count": "Attività: {running} in esecuzione, {pending} in attesa",
    "inspector.last_used": "Ultimo utilizzo: {value}"
  }
}
@@FENCE@@

Rules:

- one JSON object per supported locale file under @@BT@@nl_coding_agent/gui/locales/@@BT@@;
- @@BT@@locale@@BT@@ identifies the catalog code; @@BT@@name@@BT@@ is the selector label;
  @@BT@@strings@@BT@@ maps stable keys to translated text;
- named placeholders use Python/Qt-style @@BT@@{name}@@BT@@ and are formatted with a safe
  formatter (unknown placeholders remain visible; formatting never raises);
- missing keys fall back deterministically to English, then to the caller-provided
  English/source default, then to the key itself;
- malformed/unreadable catalogs are skipped safely rather than breaking the app;
- loader discovery is file-based, so adding a catalog does not require a new
  framework or network access.

## Adding a language

1. Copy @@BT@@en.json@@BT@@ to @@BT@@<locale>.json@@BT@@ under @@BT@@nl_coding_agent/gui/locales/@@BT@@.
2. Set @@BT@@locale@@BT@@, @@BT@@name@@BT@@ and translate the @@BT@@strings@@BT@@ values (keep the keys).
3. Add the locale to the Settings selector options and to AppServices validation if it
   should be user-selectable. The service discovers catalogs automatically for
   resolution/fallback; the current built-in selector intentionally offers Italian,
   English and System only.
4. Run @@BT@@tests/test_i18n.py@@BT@@ and the GUI smoke tests. Do not place prompts,
  model instructions or generated-code language in catalogs.

## Coverage (principal surfaces)

Translated through the injected translation service:

- main window title/header, no-project label, autonomy button/tooltip, Ollama tooltip,
  empty status labels, IDE tab titles;
- sidebar page names and tooltips;
- Projects page title, primary buttons, recent list heading, project tooltips and
  remove/new-mission dialog strings;
- Settings page title/subtitle, primary form labels, cloud/permissions state and
  language selector, refresh button, advanced group title;
- Inspector page title and principal project/file/mission labels;
- Open Project dialog title/prompt/buttons/validation messages.

## Secondary-panel coverage (U3, NL-BP-237 remaining strings)

The following secondary surfaces now use the shared catalog/tr helper and registered
retranslate hooks (selected principal strings, tooltips, empty/loading/error states,
buttons, table headers and status labels):

| Surface | Covered examples | Remaining |
|---|---|---|
| Task board | title, roadmap/refresh/run buttons, task-tree headers, empty queue/status | dynamic mission/task payload text, backend errors |
| Chat composer | title, hint, input placeholder, dictate/stop/attach/remove/send buttons and tooltips, voice/status empty states | voice backend diagnostic codes and dynamic attachment errors |
| Goals workspace | title, safety hint, tabs, list/detail headings, lifecycle/verify/replan/complete/approve buttons, tasks/queue/versions/evidence headers, empty states | dialogs' secondary body text, dynamic goal/audit/mission payloads |
| Research workspace | title, safety hint, query/search/provider/status empty states, source/library/preview tabs and buttons, intake/retention labels | provider/backend diagnostics, dynamic result/preview payloads |
| Autonomy page | title/subtitle, primary buttons, supervisor idle state, queue headers | dynamic supervisor notices/history |
| Agents | title/subtitle, availability statuses, headers, policy, refresh | model names/notes and backend error details |
| Model Hub | title/subtitle, tabs, provider filter, table headers, empty/loading states | provider/model/family payload values and diagnostic details |
| Logs | title and clear action | log/event payload messages (backend owned) |
| IDE editor | title, no-file/save labels/tooltips, open-file empty state | dynamic save/read-only/error detail strings |
| Terminal | title, no-project/placeholder/run/clear/status labels | command/policy output and dynamic execution diagnostics |
| Git | title, no-repository/refresh/status labels, diff/log tabs | branch/commit/diff/log payloads |
| Problems | title, refresh, no-problems status, table headers | dynamic severity/source/message payloads |
| Command palette | title/window title, filter placeholder, safety hint | command labels/categories supplied by MainWindow (principal surface owned by U1) |

Tests `tests/test_i18n_coverage.py` verify catalog-key completeness, representative
Italian and English strings and live retranslation for these panels, plus English/source
fallback when no application translator is active.

## Coverage limits and remaining work

- Not every secondary string is translated. Remaining: dynamic agent/model/mission/
  research/audit payloads and backend diagnostics; secondary dialogs/body copy; advanced
  Settings labels/notices; command labels built by the main window; some dynamic status
  notices and error descriptions. Untranslated text falls back to English/source.
- No pluralization rules, locale-specific date/number formatting, right-to-left layout,
  rich-text markup in catalogs, translator tooling or machine translation at runtime.
- Language changes do not alter running mission logs, already-generated responses,
  source code or documentation; those are intentionally separate.
- OS detection uses the Qt system locale mapping; headless/embedded environments may
  report no useful locale, in which case System falls back to Italian.
- Secondary panels without an active application translator intentionally stay
  English/source for direct-construction compatibility; the shipped Studio creates the
  translator before constructing its panels.
- No network, model, GUI automation or translation service is used by the framework or
  its tests; the desktop GUI itself is exercised offscreen only.

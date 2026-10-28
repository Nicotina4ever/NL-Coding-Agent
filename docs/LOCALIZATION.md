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

## Coverage limits and remaining work

- Many secondary strings remain untranslated: large autonomy/self-build, research,
  Goals, chat, editor, terminal, Git, problems, agents, models and command-palette
  surfaces; dynamic agent/model output; log/error payloads from the backend; and some
  advanced Settings labels/notices. Untranslated text falls back to English/source.
- No pluralization rules, locale-specific date/number formatting, right-to-left layout,
  rich-text markup in catalogs, translator tooling or machine translation at runtime.
- Language changes do not alter running mission logs, already-generated responses,
  source code or documentation; those are intentionally separate.
- OS detection uses the Qt system locale mapping; headless/embedded environments may
  report no useful locale, in which case System falls back to Italian.
- No network, model, GUI automation or translation service is used by the framework or
  its tests; the desktop GUI itself is exercised offscreen only.

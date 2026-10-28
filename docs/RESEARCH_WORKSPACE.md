# Studio Research workspace (stage 7 R5, NL-BP-210)

The Research page is the 10th main-window page. It is a **read-only research UI**:
web/GitHub/Hugging Face content is untrusted data, never instructions. Research
actions are explicit; opening the app or constructing the page never performs a
search, preview, intake, model call or network request.

## UI map

- **Query** (Research query, Ctrl+Shift+R focuses it) and **provider/route selector**
  with per-provider availability, permission, auth-required and offline status.
  Provider credentials are never displayed; status text is redacted.
- **Results table**: title, provider, URL, snippet, age and a literal UNTRUSTED marker.
  Selection loads a read-only preview through the injected service.
- **Source preview**: read-only Text and Chunks tabs plus Details (metadata,
  citation/provenance, requested URL, redirects, STALE/CONFLICT indicators).
- **Actions**: Copy URL, Request open URL (emits open_url_requested to the host;
  this panel never opens a browser or downloads a page itself), Save finding.
- **Library**: History, Saved findings and Mission findings lists scoped to the
  open project and, when set, mission; explicit Refresh button. A saved finding can
  be attached to the current mission (permission-checked via AppServices), detached
  revocably, and listed under Mission findings. Controls are disabled with an
  explicit reason when there is no project/mission or no attachment facade.
- **Retention**: explicit Apply retention action with a confirmation dialog and
  status label. It marks old sources/findings stale/expired and never deletes
  findings, citations, provenance, URLs or mission links.
- **Intake**: Auto-detect, Web URL, GitHub repo, Hugging Face model or local
  attachment. Pasted links are validated before reaching the service; GitHub and
  Hugging Face links route to their dedicated intake kinds.
- **States**: idle, loading, empty, error, permission-needed, denied, offline.
  Search/preview/intake run through a QThreadPool; the UI thread is never blocked.

Styling uses the product identity: electric violet #7531FE for the title/accent
and cyan #46A3C0 for provenance/status accents, with lavender hints on a dark UI.
No glow is applied to content text.

## Data flow and permissions

The panel has no backend imports. ResearchPanel(services) reaches an injected
research service via services.research / services.research_service (duck-typed
methods: provider_statuses, search, preview, history, saved_findings,
save_finding, intake). If no service is configured, the page states that
research is offline; it does not fall back to direct HTTP, SQLite, a model, or
CrewAI.

All operations report a result dict with ok and optional permission_needed,
denied/reason, offline, error, results, text, chunks, metadata, provenance,
redirects, stale/stale_reason, conflict/conflict_reason. The UI surfaces these
states and redacts credential-looking strings before display. The service owns
policy/network/storage; GUI tests inject deterministic fakes.

- **No automatic research**: construction loads provider status only; search,
  preview, intake and library refresh are explicit or project-scope driven.
- **No browser integration**: copy and a host request signal only; no
  QDesktopServices, no embedded browser, no auto-open.
- **No credentials displayed**: token/api-key/secret/password assignments are
  redacted; provider dicts are never rendered raw.
- **Scope**: history/saved findings are queried with the current project id and
  mission id; saved findings are written only through the service.

## Offline / permission states

- Permission needed: shown in the main status and intake status; the operation is
  not retried implicitly.
- Denied by policy: shown with the policy reason (redacted).
- Offline: shown in the service/status labels; no network attempt is made by the
  panel.
- Auth-required providers show auth required (never shown) in provider status;
  the panel never asks for or displays a token.

## Manual-pending / limitations

- Real network, provider authentication, live GitHub/Hugging Face research,
  permission-enforcement behavior and persistence of saved findings are
  **MANUAL-PENDING**: the tests use injected fakes only and do not count as
  live-network acceptance.
- The panel is integrated as the 10th page; the real research backend is expected
  to be supplied through AppServices. Until that service is wired, the page shows
  the offline state rather than creating its own transport.
- Screenshots/drag-drop visual regression and accessibility with a real screen
  reader remain manual.
- No checkpoint download, browser automation, publishing or model execution is
  performed by this page.

## Tests

tests/test_research_panel.py (offscreen Qt, fake AppServices) covers construction
without auto-search, provider status/permission display, search success/empty/error/
permission-needed/offline, result selection + read-only preview/provenance/redirect/
stale/conflict, history/saved findings scoping and save delegation, URL/GitHub/HF
intake validation, attachment delegation, copy/open-URL request only, accessibility
labels/shortcut, and static guards against direct network/SQLite/CrewAI imports.


## Finding-to-mission attachment and retention (R8)

Saved findings can be attached to an existing mission through the injected
AppServices facade (research_attach_finding / research_detach_finding /
research_mission_findings). The database keeps an append-only attachment row with
finding_id, mission_id, source, attached_at/created_at and revoked_at. An active
(finding, mission) pair is unique: a repeated attach is idempotent, detach revokes
the link without deleting the finding, and a later re-attach creates a new link.
Finding/mission validation and project isolation are enforced by the store and
AppServices; attach/detach require a capability decision and return structured
denied/needs_approval refusals without creating a link. Audit events contain ids
and scope only (source=research, finding_attached/finding_detached/
retention_applied), never finding text, URLs or credentials.

Retention is non-destructive: apply_retention(now, ttl_days, max_items) marks old
sources/findings stale and expired (stale_reason/expired_at) while preserving all
rows, content hashes, URLs, citations, provenance and mission links. The GUI shows
the summary and uses honest stale/expired-not-deleted wording; there is no hard
delete API in the store or GUI.

GUI tests use injected fake services only; real project/SQLite permission behavior,
live network and real mission attachment acceptance remain MANUAL-PENDING.
tests/test_gui_smoke.py and tests/test_gui_panels.py assert the 10-page layout,
page map and no direct network/SQLite/CrewAI imports.

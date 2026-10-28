# Private Beta Testing Guide

**Status:** private beta tester onboarding and feedback guide (NL-BP-159/161/164 support).
**Audience:** non-developer beta testers and the maintainers who triage their reports.
**Related documents:** `docs/PRIVATE_BETA_RUNBOOK.md` (owner gates, triage rules),
`docs/BOOTSTRAPPER.md` (installer/offline bundle commands), `docs/RELEASE_ACCEPTANCE.md`
(measured acceptance evidence and manual-pending items), `docs/PLATFORM_COMPATIBILITY_MATRIX.md`
(per-platform/per-feature status, maintained by the compatibility task),
`.github/ISSUE_TEMPLATE/beta_bug.yml` and `beta_feature.yml` (the forms you will use).

---

## 1. What this private beta is

NL Coding Agent is a local-first, multi-agent software-development orchestrator. This beta is a
small, **private** test of early installable packages on real machines. It is not a public release.

What the beta is for:

- validating that the package installs and launches on a real, clean-ish machine;
- validating the core workflow (project discovery, audit, a first mission, resume after restart);
- collecting reproducible bug reports with enough evidence to fix them;
- recording honest per-platform/per-feature acceptance evidence.

What it is **not**:

- not a supported product release; there is **no support SLA**;
- **not a claim of cross-platform support** for a platform merely because CI builds or another
  tester succeeded — real-hardware results stay **MANUAL-PENDING** until the maintainers record and
  accept them;
- not a cloud service: there is no account, no upload and no automatic data collection.

## 2. Privacy: there is no telemetry

- The application sends **no telemetry** and performs **no automatic upload**; this beta has no
  account system and no analytics endpoint.
- The opt-in diagnostic report (`section 8`) is generated **locally** and only leaves your machine
  if **you** attach it to an issue.
- Cloud model providers are disabled by default and require explicit opt-in in the app; do not
  enable them for beta testing unless the maintainer asks you to.
- Never paste API keys, tokens, passwords, private keys, cloud account identifiers or private
  project content into an issue. If you think a secret leaked into a log, say so without quoting it.

## 3. Current platform status (read this before installing)

The program is building native candidates per platform. **Only a platform for which the owner has
given you a package + checksum is testable.** Everything else is not packaged yet.

| Platform / architecture | Candidate packaged now? | Evidence status |
|---|---|---|
| Windows 11 x64 | Portable + bootstrapper foundations exist (see `docs/RELEASE_ACCEPTANCE.md`) | Automated/CI checks pass; clean-machine and full GUI interaction remain **MANUAL-PENDING** |
| Windows ARM64 | Not packaged yet | **MANUAL-PENDING / not testable** |
| Linux x86_64 | Not packaged yet (schema-level support only) | **MANUAL-PENDING / not testable** |
| Linux ARM64 / aarch64 | Not packaged yet | **MANUAL-PENDING / not testable** |
| macOS Apple Silicon | Not packaged yet | **MANUAL-PENDING / not testable** |
| macOS Intel | Not packaged yet | **MANUAL-PENDING / not testable** |

Additional declared limitations you should expect in this beta (from the measured acceptance
evidence, not a guess list):

- The earlier portable `status` portability defect is fixed and re-verified in revision 2 of
  `docs/RELEASE_ACCEPTANCE.md` (default status prints `Project: not configured` and exits 0). Use
  `doctor`, `status` and the GUI as the primary checks and report any deviation.
- Full GUI interaction, clipboard attachments, microphone/ASR/TTS, GPU behaviour, signed installer
  and network update/repair have **not** been verified on real hardware yet.
- A schema/decision for a platform is not evidence that a candidate exists for it.

If you were not given a package for your platform by the maintainer, do not build one from source
to "test support": report the missing-platform gap instead.

## 4. Before you start

- A machine you can install to without administrator rights (portable folder or user-writable
  install directory).
- Enough free disk space for the payload (Windows portable payload is roughly 1.4 GiB unpacked).
- Ollama installed and running locally if you will test model-dependent features (optional for
  install/GUI-only testing). The app discovers models dynamically; it does not download models.
- The **package checksum** provided by the maintainer (or the `release-manifest.json` `archive.sha256`
  that ships with a candidate directory).

## 5. Get the package and verify its checksum

Always verify the checksum before installing. A mismatch means: do not install, delete the file, and
report it privately to the maintainer (treat it as a security issue, do not post the link publicly).

**Windows (PowerShell):**

```powershell
Get-FileHash -Algorithm SHA256 .\nl-coding-agent-0.2.0-windows-x64.zip
```

**Linux:**

```bash
sha256sum nl-coding-agent-0.2.0-linux-x86_64.tar.gz
```

**macOS:**

```bash
shasum -a 256 nl-coding-agent-0.2.0-macos-arm64.zip
```

Compare the 64-character value with the one the maintainer gave you (or with
`release-manifest.json` -> `archive.sha256`). Include that checksum in every issue you file.

## 6. Install

### 6.1 Portable package (recommended for testers)

1. Unzip the package into a user-writable folder **outside** any synced/cloud folder, for example
   `%USERPROFILE%\Apps\NL-Coding-Agent` (Windows) or `~/Apps/NL-Coding-Agent` (Linux/macOS
   candidates when published). Do not use Program Files / system directories.
2. Do **not** copy your own `data/`, databases, logs or model files into the package folder. The
   package is program-only; user data lives in the application data directory (or `NL_DATA_DIR`).
3. Launch with the packaged launcher:
   - Windows: `NL Coding Agent.bat` (GUI), `doctor.bat`, `Self-Build Mode.bat`, `status.bat`. In a
     **packaged payload** these CLI launchers are staged at the package root; in a **source
     checkout** they live under `scripts\launchers\` (the GUI launcher stays at the repository
     root).
   - Linux/macOS: the packaged `.sh`/`.command` launcher, when a candidate for that platform is
     published. If the launcher is not executable: `chmod +x` it first; never run the app with a
     system Python — the payload ships its own runtime.

Do not run the launcher from inside the .zip: extract first.

### 6.2 Bootstrapper install (when the maintainer provides a manifest)

The bootstrapper is a plain command-line tool that installs into a **new or empty** user-selected
directory (never global, never admin). Follow `docs/BOOTSTRAPPER.md` `4`; the safe patterns are:

```powershell
# Plan only - writes nothing and downloads nothing
python installer\bootstrap.py plan --manifest <platform-manifest.json>

# Install into a new/empty user directory
python installer\bootstrap.py install --target %USERPROFILE%\Apps\NL-Coding-Agent --manifest <platform-manifest.json> --cache %USERPROFILE%\AppData\Local\NL-Coding-Agent\cache

# No-network install from an offline bundle directory
python installer\bootstrap.py install --target %USERPROFILE%\Apps\NL-Coding-Agent --offline-bundle <bundle-dir> --cache %TEMP%\nl-cache

# Verify an existing managed installation
python installer\bootstrap.py verify --target %USERPROFILE%\Apps\NL-Coding-Agent --json
```

If you test the bootstrapper, also record the `verify` JSON (redact your paths if needed) in the
issue.

### 6.3 From a source checkout (developers only)

Source checkouts are for development, not beta acceptance. On Windows use the embedded runtime in
the checkout (`python\python.exe`); its CLI launchers are under `scripts\launchers\` and the GUI
launcher is the root `NL Coding Agent.bat`. On Linux/macOS a source checkout is not a beta
candidate; do not treat it as one.

## 7. First-run validation checklist

Run these in order and note the exact output for anything unexpected. Use `doctor` as the primary
health check.

| Step | Command / action | Expected |
|---|---|---|
| 1 | the doctor launcher (`doctor.bat` at the payload root, or `scripts\launchers\doctor.bat` in a source checkout) or `python\python.exe nl_agent.py doctor` | exits 0; runtime, CrewAI, Ollama and project checks reported OK (Ollama may be reported unavailable if you are not testing models) |
| 2 | Launch the GUI (`NL Coding Agent.bat`) | window opens with the NL logo/theme; no crash |
| 3 | Open Project -> select a small read-only test folder | project is discovered and appears in Recent Projects |
| 4 | Run the project audit from the GUI | audit completes read-only; findings are visible |
| 5 | (Optional) run a small mission/self-build on a **test folder**, not your real work | state, mission, diff and verification evidence are persisted; resume works after restart |
| 6 | Check the data/log directory | SQLite DB and state exist in the app data dir; logs are local only |
| 7 | Restart the app | project and mission state are still there |

Also try these if relevant to your test assignment:

- an installation path **with spaces** and a non-ASCII user name;
- an offline run (disconnect network; local Ollama models still work);
- a second launch while the first one is open (expect a clear message, never silent data damage).

## 8. What to report and where

All feedback goes through **GitHub Issues in the private beta repository** (see
`docs/PRIVATE_BETA_RUNBOOK.md` `8` for communication rules). Choose the right form:

- `Beta bug report` (`beta_bug.yml`) for defects, crashes, wrong behaviour, packaging problems.
- `Beta feature request` (`beta_feature.yml`) for missing or confusing capabilities.

A good report contains:

1. **Platform and architecture** (e.g. Windows 11 x64, Ubuntu 24.04 x86_64, macOS 14 arm64).
2. **Package version** (e.g. `0.2.0`) and the **package SHA-256 checksum** you verified.
3. **Install method** (portable unzip, bootstrapper `--target` install, offline bundle).
4. **Reproduction steps** from a clean start, numbered.
5. **Expected vs actual** behaviour, with the exact error text.
6. **Evidence provenance**: real hardware (**MANUAL-PENDING** until accepted) versus a CI artifact
   run. Never present a CI run as real-hardware acceptance.
7. **Relevant log lines** only, redacted; or a small attachment.
8. The **diagnostic report** (section 9 below) when the issue involves install, environment,
   models, packages or an unexplained failure.

Maintainers triage with labels (see `docs/PRIVATE_BETA_RUNBOOK.md` `7`):
`type/bug` vs `type/feature`, `platform/*`, `arch/*`, `severity/*`, `evidence/MANUAL-PENDING` vs
`evidence/CI`, and `status/*`. Reports without a reproducible environment/checksum may be labelled
`status/needs-info`.

## 9. Diagnostic report (opt-in, local-only, redacted)

The repository ships a small generator that collects a **redacted** environment report. It is
opt-in: you run it yourself, nothing runs automatically, and it never uploads anything.

From the installation folder (or the repository checkout):

```powershell
# Preview only - writes nothing
python\python.exe scripts\diagnostic_report.py --dry-run

# Write a Markdown report you can review and attach manually
python\python.exe scripts\diagnostic_report.py --output beta-diagnostic.md

# Optional machine-readable JSON variant
python\python.exe scripts\diagnostic_report.py --format json --output beta-diagnostic.json
```

The report contains: OS/architecture/Python versions, application version and install method,
package checksums and release-manifest summary, installed package versions (allow-list), a
redacted configuration summary, capability **presence** probes (modules/executables on PATH),
database presence/size only, and an allow-list of non-secret environment variables.

It **redacts** API keys/tokens/passwords, private keys, URL credentials, cloud account identifiers,
the user home directory, usernames and personal absolute paths.

It **does not collect**: project source/content or file listings, database rows, chat/model output,
model files, user files outside the installation, hostname/username, or non-allow-listed
environment variables. It performs no network request, no model inference and no mission run.

**Review the file before attaching it**; the redaction is defensive, but only you can decide what
is shareable. Attach it manually to the issue (or paste its content) — do not expect the app to
send it.

## 10. MANUAL-PENDING acceptance matrix

This is the honest status board for the beta. A cell becomes `VERIFIED` only after a real tester
records the required evidence and a maintainer accepts it. `CI` means automated evidence exists but
real-hardware acceptance is still pending. `N/P` means no package is available for that platform
yet, so it is not testable.

| Acceptance item | Win 11 x64 | Win ARM64 | Linux x86_64 | Linux ARM64 | macOS arm64 | macOS Intel |
|---|---|---|---|---|---|---|
| Package checksum verified | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Clean install (portable) | MANUAL-PENDING (CI partial) | N/P | N/P | N/P | N/P | N/P |
| Bootstrapper install/verify | MANUAL-PENDING (CI partial) | N/P | N/P | N/P | N/P | N/P |
| First launch + GUI renders | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Open project / Recent Projects | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Project audit | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Mission run + persisted diff | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Resume after restart | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Clipboard screenshot / drag-drop attachments | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Microphone / ASR / TTS | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| GPU capability / graceful CPU fallback | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Terminal / Git / file tools | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Offline install from bundle | MANUAL-PENDING (CI partial) | N/P | N/P | N/P | N/P | N/P |
| Uninstall / user-data preservation | MANUAL-PENDING | N/P | N/P | N/P | N/P | N/P |
| Network update/repair (signed channel) | NOT IMPLEMENTED | N/P | N/P | N/P | N/P | N/P |

**Recording rule:** a beta acceptance record must include: tester (private handle), date, platform
and architecture, package version + SHA-256, install method, each item tested, result
(pass/fail/blocked), issue link if any, and evidence provenance. One row per tester/package in the
release acceptance log. A CI run alone never fills a `VERIFIED` cell.

## 11. Tester rules

- Keep builds and links **private**; do not upload packages, mirrors or screenshots of private work
  to public services.
- Use a **test folder**, not your real projects or personal documents.
- One issue per problem; search existing issues first.
- Never attach secrets, credentials, private keys or personal data. If a secret is exposed by the
  app or in a log, report the fact privately without quoting the secret.
- State uncertainty honestly: "not tested" is a valid and useful answer.
- Do not modify the application files to "make it work" without telling us — that changes the
  evidence. Note any local workaround you used.

## 12. What happens next

- A maintainer acknowledges and triages reports on a **best-effort** basis (no SLA in the private
  beta); see the triage labels in `docs/PRIVATE_BETA_RUNBOOK.md`.
- Confirmed, reproducible defects are fixed in a candidate; you may be asked to re-test the same
  steps on a new checksum.
- Platform/feature claims are updated only in the acceptance matrix and release acceptance record
  after verified evidence.
- If the beta ends or a package is withdrawn, the maintainer tells testers privately.

## 13. Troubleshooting quick checks

| Symptom | First checks |
|---|---|
| Launcher exits immediately | run the doctor launcher (or `python\python.exe nl_agent.py doctor`) from a terminal in the install folder and copy the output; check the path contains no forbidden write-protected location |
| Model-dependent action fails | is Ollama running? `ollama list` shows models? are cloud providers disabled? |
| GUI does not open | confirm the package is extracted (not running from inside the zip), then include the console/log output |
| Checksum mismatch | stop; delete the file; report privately to the maintainer |
| Old state after restart | check the app data directory (`NL_DATA_DIR` if set) and include the diagnostic report |

## 14. Related documents

- `docs/PRIVATE_BETA_RUNBOOK.md` - owner authorization gates, pre-upload audit, triage and
  communication rules.
- `docs/BOOTSTRAPPER.md` - install/verify/offline commands.
- `docs/RELEASE_ACCEPTANCE.md` - measured acceptance evidence and current manual-pending items.
- `docs/PLATFORM_COMPATIBILITY_MATRIX.md` - per-platform and per-feature compatibility status.
- `docs/PRODUCT_BACKLOG.md` - requirements NL-BP-159/161/163/164 background.
- `.github/ISSUE_TEMPLATE/beta_bug.yml` and `beta_feature.yml` - the issue forms.

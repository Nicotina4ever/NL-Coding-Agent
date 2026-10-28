# Private Beta Runbook - Owner Gates, Triage and Communication

**Status:** operational runbook for the private cross-platform beta (NL-BP-159/161/162/163/164
support). **Owner-only where stated.**
**Audience:** the repository owner (authorizer) and the maintainers who triage beta feedback.
**Related documents:** `docs/BETA_TESTING.md` (tester onboarding, diagnostic report, MANUAL-PENDING
matrix), `docs/RELEASE_ACCEPTANCE.md` (measured acceptance evidence), `docs/BOOTSTRAPPER.md`
(bootstrapper commands), `docs/REPOSITORY_STRUCTURE.md` (repository ownership), `AGENTS.md`
(binding workspace rules).

---

## 1. Status and scope

- The repository is a **private beta repository**. It has **no configured remote** and nothing in
  this runbook authorizes publication, pushing or distribution.
- The current repository state is preserved as-is: keep the private repository, its history and its
  existing release/local candidates intact.
- All external actions (push, visibility change, collaborator invite, release upload, package
  distribution, public announcement) require **explicit owner authorization for that specific
  action**. There is no standing or implied authorization, including from the existence of this
  runbook or of a packaged candidate.

## 2. Non-negotiable owner gates

The following must **not** happen unless the owner has explicitly authorized that exact action in
writing, for that exact artifact/scope:

| # | Gated action | Default state |
|---|---|---|
| G-1 | Adding/changing a git remote, or `git push` to any remote (including force-push) | **FORBIDDEN** |
| G-2 | Changing repository visibility (making it public), creating a public mirror/fork | **FORBIDDEN** |
| G-3 | Inviting collaborators, creating teams, transferring ownership | **FORBIDDEN** |
| G-4 | Uploading beta packages/artifacts to GitHub Releases, a website, a package registry, cloud storage or any download service | **FORBIDDEN** |
| G-5 | Publishing download links, checksums intended for distribution, or beta invitations publicly | **FORBIDDEN** |
| G-6 | Enabling telemetry/upload/analytics in the application or diagnostic tooling | **FORBIDDEN** |
| G-7 | Rewriting repository history (`git reset` on published refs, rebase of shared history, tag deletion/moves) | **FORBIDDEN** |
| G-8 | Deleting or replacing `data/`, `logs/`, databases, backups, model checkpoints, vendor checkouts or acceptance evidence | **FORBIDDEN** |
| G-9 | Publishing a candidate built from a workspace containing personal data or development databases | **FORBIDDEN** |
| G-10 | Running model inference, network installs or mission runs as part of "verification" without owner approval | **FORBIDDEN by default** |

Allowed without new authorization (local only, non-destructive):

- local commits on the private repository (the Lead owns commit decisions);
- local candidate builds under `build/` / `dist/` (git-ignored), with the existing safe tooling;
- read-only audits and tests that do not download or publish anything;
- triage of issues within the private repository;
- private, one-to-one communication with testers who already have the package.

## 3. Pre-upload / pre-share audit checklist

Run this **before any candidate is shared with a tester**, and before any owner-authorized upload.
Every step is read-only/local; record the output path or hash as evidence.

1. **Repository hygiene audit** (secrets/stale/cache candidates, read-only):

   ```powershell
   python\python.exe scripts\audit_repository_hygiene.py --json-out build\beta\hygiene.json --quiet
   ```

   If the dedicated pre-upload secrets/history audit tool (NL-BP-162) is present in this checkout,
   run it as well (read-only, bounded, never publishes):

   ```powershell
   python\python.exe scripts\audit_release_secrets.py --markdown-out build\beta\secrets_audit.md --quiet
   ```

2. **CrewAI SBOM compatibility check** (no network):

   ```powershell
   python\python.exe scripts\check_crewai_upgrade.py --verify-sbom
   ```

3. **Tracked-file secret patterns** (bounded, read-only). Review any hit manually; do not paste
   secrets into issues:

   ```powershell
   git grep -n -I -E "(sk-[A-Za-z0-9]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY)"
   ```

4. **Git history spot-check** for the same patterns in added lines of the beta-relevant range;
   classify any finding before proceeding:

   ```powershell
   git log --all --oneline --decorate -20
   git log -p --all -- . | Select-String -Pattern "sk-|ghp_|AKIA|PRIVATE KEY" -CaseSensitive
   ```

5. **Package content audit** - list the archive contents and confirm no forbidden paths appear:

   ```powershell
   python -m zipfile -l <candidate.zip>
   # Linux/macOS tar candidates:
   tar -tzf <candidate.tar.gz>
   ```

6. **Checksums and manifests** - verify the artifact hashes match the manifests and record them:

   ```powershell
   Get-FileHash -Algorithm SHA256 <candidate-file>
   python -c "import json; d=json.load(open('release-manifest.json')); print(d['archive'])"
   ```

7. **Payload absolute-path check** - confirm the payload manifest reports no absolute-path hits:

   ```powershell
   python -c "import json; d=json.load(open('payload_manifest.json')); print(d['payload_checks'])"
   ```

8. **Independent review** - a maintainer other than the person who built the candidate reviews the
   audit output. The reviewer records: candidate name, version, SHA-256, size, audit commands,
   results, known limitations and MANUAL-PENDING items.

If any step fails, stop: do not share the candidate. Fix, rebuild, repeat.

## 4. Package content rules

**Must be present** (program-only payload): launchers, `nl_agent.py`, `nl_coding_agent/`, the
appropriate native runtime for the target platform, `assets/`, `config/models.yaml`, package
`README.md` and a release/platform manifest with checksums.

**Must never be present** in a shared package:

- `data/` (SQLite database, self-build state, backups, mission baselines), `logs/`, `state/`;
- `config/voicebridge.yaml` / `config/voicebridge.local.yaml` (machine-local external paths);
- model files or checkpoints, Ollama caches, Hugging Face caches;
- vendor checkouts (`crewAI/`, `crewAI-tools/`) unless an authorized license review explicitly
  requires reference material;
- `build/`, `dist/`, test suites, development docs/evidence, patch/legacy evidence, temporary
  repair scripts, `.git/` metadata, `__pycache__`/tool caches, `.env` or secrets;
- a Windows runtime inside a Linux/macOS candidate (never reuse runtimes across platforms).

See `docs/REPOSITORY_STRUCTURE.md` "Development-only files (never shipped in the portable
payload)" for the maintained exclusion list.

## 5. Versioning, checksums and provenance

- The application version has **one source of truth**: `nl_coding_agent/core/version.py`
  (`APP_VERSION`). A package version must match it and the generated manifests.
- Never reuse a version for different bytes. Change the version before rebuilding a candidate that
  differs in content.
- Every shared artifact needs: file name, platform key, size, SHA-256 and the manifest version.
  Record them in the beta acceptance log before sharing.
- Provenance is recorded separately for **CI** artifacts and **real-hardware MANUAL-PENDING**
  results; never present CI evidence as platform acceptance.

## 6. Authorization and distribution procedure (owner-only steps)

1. Maintainer builds the candidate locally under `build/` or `dist/` (git-ignored).
2. Maintainer runs the audit checklist (`3) and writes a short evidence note with the results.
3. Owner reviews the evidence and the package content (`4), then records an explicit authorization
   in the beta log, for example:
   - date/time, authorizer (owner), candidate name + version + SHA-256,
   - scope authorized (which testers / which private channel / which actions),
   - explicit statement that distribution is private and time-limited.
4. Only after that record exists may the owner (not a maintainer acting alone) upload the artifact
   to the authorized private destination and send private links to the named testers.
5. First tester confirms checksum and reports a first-run result before broader testing.
6. Any change to artifact, version, audience or destination requires **new** authorization.

Nothing in this section authorizes a public release, a remote push or a visibility change.

## 7. Issue triage rules

### Label taxonomy

| Group | Labels | Meaning |
|---|---|---|
| Source | `beta` | all private-beta feedback |
| Type | `type/bug`, `type/feature` | defect vs request (from the issue forms) |
| Platform | `platform/windows-x64`, `platform/windows-arm64`, `platform/linux-x86_64`, `platform/linux-arm64`, `platform/macos-arm64`, `platform/macos-x64`, `platform/unknown` | platform reported by the tester |
| Architecture | `arch/x86_64`, `arch/arm64`, `arch/unknown` | CPU architecture |
| Evidence | `evidence/MANUAL-PENDING`, `evidence/CI` | real-hardware result pending acceptance vs CI-only evidence |
| Severity | `severity/blocker`, `severity/major`, `severity/minor`, `severity/cosmetic` | triaged severity |
| Status | `status/needs-triage`, `status/confirmed`, `status/needs-info`, `status/duplicate`, `status/fixed-candidate`, `status/accepted`, `status/wontfix` | workflow state |
| Privacy | `privacy/hold` | potential secret/personal data exposure; private handling only |

### Triage workflow

1. **Safety scan** the issue first: if it contains a secret/token/personal data, add `privacy/hold`,
   ask the reporter to edit/redact (never quote the secret), and follow the incident procedure
   (`8.3). Do not copy the content elsewhere.
2. Verify the report has platform/arch, version, checksum, install method, reproduction,
   expected/actual and evidence provenance. If not: `status/needs-info` with a short checklist.
3. Reproduce when possible from the stated package/checksum. Never download anything from an
   untrusted source to reproduce.
4. Classify: `type/*`, `platform/*`, `arch/*`, `severity/*`; set `status/confirmed`.
5. Record real-hardware results as `evidence/MANUAL-PENDING` in the acceptance matrix
   (`docs/BETA_TESTING.md` `10`) until a maintainer accepts them; fill the row with tester, date,
   package SHA-256, tested items and result.
6. Link the issue from the acceptance record and vice versa.
7. When a fix ships in a candidate, mark `status/fixed-candidate` and ask the reporter to re-test
   with the new checksum; close after confirmation or after a documented decision.
8. Closed without fix: `status/wontfix` (with rationale) or `status/duplicate` (link the canonical
   issue). Never silently close reproducible bug reports.

### What to ask testers for

Ask for: the redacted opt-in diagnostic report (`docs/BETA_TESTING.md` `9`), relevant redacted log
lines, exact package checksum, steps, and whether the run was real hardware or CI. Never ask for
API keys, tokens, passwords, private project files, full databases or full home-directory listings.

## 8. Communication rules

### 8.1 Channels

- Issues in the private beta repository are the public-within-beta record.
- Direct messages to named testers are private; do not forward their content outside the beta
  group.
- Do not publish status updates, screenshots, download links, checksums or test results on public
  services while the beta is private.

### 8.2 Tone and expectations

- State platform/feature status honestly ("MANUAL-PENDING", "not packaged", "works with
  workaround"). Never claim verified support without recorded real-hardware evidence.
- No support SLA is implied. Acknowledge best-effort; give testers a clear next step.
- Do not speculate about root causes as facts; label hypotheses as hypotheses.

### 8.3 Security / secret-exposure incident

1. Do not quote or further copy the exposed secret.
2. Add `privacy/hold` and restrict discussion.
3. Ask the reporter to edit/delete the content from the issue; if the secret is in an attachment,
   ask them to remove it.
4. Owner rotates/revokes the affected credential (the owner decides; never do this silently in a
   shared environment).
5. Record an incident note with date, artifact, scope, action and follow-up. If the secret came from
   the product itself, treat it as a release blocker for the beta.
6. Communicate only what is necessary to affected testers.

## 9. Repository and artifact preservation

- Never delete or rewrite `data/`, `logs/`, databases, backups, acceptance evidence, vendor
  checkouts, model caches or existing release candidates as part of triage or packaging.
- Keep at most one verified release candidate per platform; record the others as candidates until
  an authorized cleanup decision.
- Use Git commits/diffs as rollback for repository work; do not create duplicate large snapshots.
- Back up the SQLite database and self-build state before any migration; never ship them.

## 10. Withdrawal and rollback

If a package is defective or leaks data:

1. Stop distributing it; tell testers privately to stop using it and delete the package.
2. Mark the candidate **withdrawn** in the beta log with the reason and SHA-256.
3. If it was uploaded (only in an owner-authorized release), the owner decides whether to delete
   the uploaded artifact after recording the evidence; do not silently remove evidence.
4. Provide a fixed candidate only after the full audit checklist (`3) passes again.

## 11. Roles

| Role | Responsibility |
|---|---|
| Owner (user) | Sole authorizer for external actions (push/visibility/collaborators/releases/distribution); reviews audit evidence; decides withdrawal. |
| Lead / maintainer | Builds candidates, runs audits, triages issues, fixes, records evidence; never performs gated external actions alone. |
| Reviewer (maintainer != builder) | Independently checks the audit evidence and package contents before distribution. |
| Tester | Installs from an authorized private link, verifies checksum, validates the checklist, reports with redacted evidence. |

## 12. Related documents

- `docs/BETA_TESTING.md` - tester onboarding, diagnostic report, MANUAL-PENDING matrix.
- `docs/RELEASE_ACCEPTANCE.md` - measured acceptance evidence and manual-pending items.
- `docs/PLATFORM_COMPATIBILITY_MATRIX.md` - per-platform/per-feature compatibility status.
- `docs/REPOSITORY_STRUCTURE.md` - ownership, retention and packaging exclusion policy.
- `.github/ISSUE_TEMPLATE/beta_bug.yml`, `beta_feature.yml`, `config.yml` - feedback forms.
- `docs/PRODUCT_BACKLOG.md` - requirements NL-BP-159/161/162/163/164.

# Mandatory blocking pre-push secrets/content guard (stage 10 R1/R2/R3, NL-BP-235)

scripts/prepush_guard.py is a blocking, read-only release guard. It must be run
before ANY upload, push, share or publication (including every earlier public
GitHub upload). It never pushes, commits, tags, fetches, publishes, changes
visibility/collaborators or rewrites history.

This document records the stage-10 R2 acceptance review, an end-to-end hook proof
against temporary bare remotes, the R3 synthetic-fixture remediation and dated
working-tree measurements. The Lead decides verified status; nothing here claims
external acceptance, publication authorization or complete history coverage.

## Modes

- scan-staged: scans the Git index (staged content) before a commit/push.
- scan-head: scans tracked files at HEAD plus the working tree.
- scan-history: scans a bounded window of Git history (up to 30 commits, changed
  paths, bounded bytes) for secrets/artifacts that were committed and later removed.
- scan-all: runs staged + head + bounded history (used by CI).
- hook: Git pre-push mode; reads the refs Git sends on stdin, scans the staged
  index and the bounded history, and exits non-zero before any push when blocked.
- install-hook: prints the hook that would be installed (dry-print by default).
  --force writes it; if a hook already exists, --force alone is refused and
  --force --backup is required, preserving the old hook as pre-push.bak.<stamp>.

Global flags: --repo PATH, --allowlist FILE, --json, --json-out FILE,
--markdown-out FILE. Global flags work before or after the subcommand.

## Fail-closed failure semantics

| Situation | Exit | Behavior |
|---|---|---|
| Clean scan (no blocking findings, no truncated bounds) | 0 | allowed to continue |
| Blocking findings, or any scan bound reached (files/bytes/findings/commits) | 1 | BLOCKED; no upload/push should proceed |
| Usage error, invalid allowlist, not a Git repository | 2 | refused |
| Operational failure (Git missing/timeout/non-zero read-only Git command, hook cannot resolve repo) | 3 | fails closed; hook aborts the push |

There is no silent bypass flag inside the tool: there is no --skip, --ignore,
--force-pass or continue-on-error mode. Missing Git or a failed read-only Git
command raises a guard error instead of scanning an empty tree. Missing historical
paths (files deleted by later commits) are the only skipped Git object; that skip
is scoped to an expected deleted path in bounded history, not to I/O/Git failures.
Git's own --no-verify flag bypasses client hooks; that is outside this gate's
control and is documented honestly below.

Git hook: a non-zero hook exit aborts git push. The installed hook embeds the
interpreter that ran install-hook (not a bare python3, which may be absent on
Windows/Git-for-Windows) and absolute forward-slash paths, so it works under Git
Bash and POSIX shells. If the guard is deleted/moved or the interpreter is missing,
the hook exits 3 and the push is blocked.

## Install and use

Run manually before every push/upload (Windows embedded runtime):

  python\python.exe scripts/prepush_guard.py scan-all --json-out reports/prepush_guard.json --markdown-out reports/prepush_guard.md

CI/POSIX equivalent:

  python scripts/prepush_guard.py scan-all --json-out reports/prepush_guard.json --markdown-out reports/prepush_guard.md

Install the hook in an authorized checkout (default prints only; never installed in
the canonical repository by the task/tests):

  python\python.exe scripts/prepush_guard.py install-hook
  python\python.exe scripts/prepush_guard.py install-hook --force
  python\python.exe scripts/prepush_guard.py install-hook --force --backup

Refusal semantics for an existing hook: without --force the install prints a
dry-print and exits 2 without writing; with --force but without --backup it exits 2
without writing and asks for --backup; with --force --backup the old hook is moved
to .git/hooks/pre-push.bak.<timestamp>, then the blocking hook is written and made
executable. The hook is a local convenience and is not a substitute for the CI job
or for running scan-all before upload.

## Detection, reuse and synthetic-fixture remediation

Secret patterns, redaction, classification and artifact rules are imported from
scripts/audit_release_secrets.py; the guard does not duplicate regexes. It checks:

- credentials/tokens/secrets (high-confidence provider patterns, generic
  assignments, high-entropy values);
- personal absolute paths, private/loopback URLs and sensitive configuration;
- embedded runtimes, vendor copies, databases, user data, logs and build outputs;
- large blobs above 5 MiB and upload-exclusion artifact paths.

Findings are redacted (SHA-256[0:12], at most 4-char prefix, length; context
matches replaced with [REDACTED:<hash>]). Full values never appear in stdout,
JSON, Markdown or reports. Scans are bounded (file/total bytes, commit count,
findings), and reaching a bound fails closed. Markdown/docs files are still scanned
for explicit credential patterns; review-only personal-path/entropy heuristics are
skipped there to avoid documentation examples blocking releases (documented review
policy, not a silent skip).

R3 fixture remediation: tests/test_prepush_guard.py previously held a hardcoded
AWS-shaped synthetic constant, which the guard correctly flagged in the worktree and
bounded history. It is now built at runtime by joining parts (the full literal is
never present in source; a regression test asserts the assembled value is absent
from the file text). The OpenAI-shaped synthetic allowlist fixture was remediated
the same way. Detection/redaction tests still write the assembled value into
temporary files and the scanner still flags it with the same AWS rule; scanner
rules, allowlist logic and finding suppression were not weakened.

## Allowlist

The only allowlist is for documented synthetic fixtures under tests/. JSON file:

  {"fixtures": [{"sha256": "<64 hex>", "path_prefix": "tests/", "reason": "synthetic fixture"}]}

Entries with other prefixes are rejected. An allowlisted match is still reported
(allowlisted=true) but does not block; values remain redacted. Never allowlist real
credentials. The audit's documented synthetic-fixture digest allowlist is reused.
No blanket tests/ allowlist and no finding suppression is used by this task.

## Verified end-to-end hook behavior (integration tests, temporary repos only)

These use local temporary repositories and a local temporary bare remote; no
canonical hook is installed and no external push/network occurs:

1. A commit containing an AWS-shaped secret: installing the hook in the temp repo
   and running a real git push to a temp bare remote is BLOCKED (git exits non-zero,
   the hook reports the redacted finding, the secret never appears in push output,
   and the bare remote has no branch ref).
2. A clean commit pushes successfully with the hook installed; the temp bare remote
   receives the branch. A later secret commit in the same repo is then blocked,
   proving the installed hook (not only the CLI) runs on a real push.
3. git push --no-verify succeeds even with the hook installed: Git deliberately
   skips client hooks, so this bypass is outside the gate's control. Coverage relies
   on running scan-all before upload and on the independent blocking CI job.
4. Existing-hook protection: no --force refuses; --force without --backup refuses
   and preserves the existing hook; --force --backup preserves the old hook and
   installs the blocking guard.
5. Operational fail-closed: with Git unavailable, scan-all exits 3 and hook mode
   exits 3 (push would be aborted), rather than passing on an empty scan.

## Bypass is outside this gate's control (honest limits)

- git push --no-verify, core.hooksPath changes, removing/uninstalling the hook,
  uploading from a different clone/tool, GitHub web upload, copying files to an
  external channel or disabling CI are all outside the local hook's control. The
  guard cannot prevent them; it only blocks when it runs. The CI secrets-scan job
  is an independent blocking environment, and humans must still run scan-all before
  any similar upload. Never treat a clean local scan as authorization.

## CI gate

.github/workflows/ci.yml has a blocking secrets-scan job on ubuntu-latest with
contents: read, no publish/push/visibility/collaborator actions, checkout with
persist-credentials: false and full bounded history (fetch-depth: 0), running
guard scan-all with JSON+Markdown reports, report checksums, and reports-only
artifacts. The guard command has no continue-on-error and no bypass flag; a non-zero
guard exit fails the job. CI covers the repository, not local uncommitted working
copies; local hook plus CI are complementary. At the R3 measurement the current
head content is clean but the canonical bounded history still contains the removed
fixture literal, so the CI scan-all would correctly fail until the history window /
release-HEAD rerun or an owner-approved precise fixture decision resolves it.

## Pre-upload use and repeatability at the actual release HEAD

Run scan-all before ANY earlier public GitHub upload, not only at the final
milestone. Repeat it at the actual release HEAD (after every commit/changed file
that can affect the repository) and after any allowlist decision. Record the exact
scan HEAD and report digest. The bounded history window and the documented scan
bounds must be disclosed: a clean bounded scan is not proof of unbounded/complete
history coverage or of external acceptance.

## Measured evidence: R3 working-tree scans (2026-10-28, Europe/Rome)

- Measured at: 2026-10-28, working tree on git HEAD
  144bd3a5190cc1a4450253841c93bd981eb34032 (task-82 changes uncommitted; reports
  reflect the current working tree).
- Commands:
  - python scripts/prepush_guard.py scan-staged --json-out
    .workspace/build/prepush_guard_r3/scan-staged.json --markdown-out ...scan-staged.md
  - python scripts/prepush_guard.py scan-head --json-out
    .workspace/build/prepush_guard_r3/scan-head.json --markdown-out ...scan-head.md
  - python scripts/prepush_guard.py scan-all --json-out
    .workspace/build/prepush_guard_r3/scan-all.json --markdown-out ...scan-all.md
- scan-staged: PASS exit 0, 0 files / 0 findings (nothing staged at measurement time).
- scan-head: PASS exit 0, 434 files, 7,029,159 bytes, 166 findings, 0 blocking,
  3 allowlisted, truncated=false; REVIEW classes only (private/loopback URLs,
  personal absolute paths, high-entropy heuristics).
- scan-all: BLOCKED exit 1, 584 files, 19,823,099 bytes, 229 findings, 2 blocking,
  3 allowlisted, truncated=false. The 2 blocking findings are rule
  aws_access_key_id in bounded HISTORY scope, path tests/test_prepush_guard.py, on
  commits d9341cd3 and 3cae00c5 (old commits that still contain the now-removed
  hardcoded literal). There is no blocking finding in the current head/working-tree
  content.
- Clean-history rehearsal (additional evidence, not a substitute): a temporary
  repository containing only the current tracked working-tree content (436 tracked
  files, one clean commit) passes scan-all exit 0 with the same rules: 434 files,
  7,026,597 bytes, 166 findings, 0 blocking, 3 allowlisted, truncated=false. This
  proves the current content is clean under all scan scopes; it deliberately does
  not include the canonical bounded history.
- Reports (gitignored generated evidence):
  .workspace/build/prepush_guard_r3/scan-staged.json/.md,
  .workspace/build/prepush_guard_r3/scan-head.json/.md,
  .workspace/build/prepush_guard_r3/scan-all.json/.md.
- Prior R2 evidence (HEAD b5cea20, blocked in head+history by the hardcoded
  fixture) is superseded by this remediation and remains only as historical
  evidence; it is not the current result.

### Honest residual blocker for the canonical scan-all

The actual bounded-history scan-all at this HEAD cannot exit 0 without one of the
following, none of which this task is authorized to perform:

1. waiting until the old commits leave the bounded 30-commit window / a final
   release HEAD whose bounded history no longer contains them;
2. an owner-authorized precise tests-only allowlist entry for the exact synthetic
   digest present only in those old commits (documented allowlist mechanism; not
   blanket tests/ allowlisting and not suppression of other findings);
3. an owner-authorized history rewrite/squash before publication (not performed;
   this task makes no commit/push/history modification).

The scanner rules, allowlist policy and finding suppression were not weakened.
Therefore the canonical bounded-history scan-all remains BLOCKED, a clean status is
not claimed, and a final release-HEAD rerun is mandatory.

## Acceptance review (Lead decides verified)

- Bullet 1 (separately runnable CLI + Git hook + CI integration block fail closed,
  non-zero, no silent bypass): MET in temporary-repo integration tests and the CI
  job configuration. Honest limits: the canonical repository hook is not installed
  by this task; git's --no-verify bypass is outside hook control; CI is the
  independent blocking environment.
- Bullet 2 (staged, tracked, history; secrets/private data/personal paths/config/
  runtimes/vendor/large blobs/dev data): MET by scan-staged/scan-head/scan-history/
  scan-all and the import-reused detection rules; hook covers staged + bounded
  history. Bounded window and documented review-only heuristics are disclosed.
- Bullet 3 (redacted output/reports; never pushes, publishes or modifies the repo):
  MET by redaction tests, static source audit (no push/fetch/tag/network/history
  rewrite/destructive calls) and read-only report evidence; the tool writes only
  requested JSON/Markdown report paths.
- Bullet 4 (runnable before ANY earlier public upload; repeatably at actual release
  HEAD): the CLI and CI are runnable before upload and repeatable by design. R3
  measurements show scan-staged/scan-head PASS and the clean-history rehearsal PASS,
  but the canonical bounded-history scan-all remains BLOCKED by old commits that
  contain the removed synthetic fixture. A clean verification is not claimed; a
  final release-HEAD rerun and an owner decision on the bounded-history residual are
  required.

## Limits: not a substitute for external acceptance

This guard is necessary but not sufficient. It cannot detect every credential
format, encrypted/binary content, external services, legal/license compliance or
real hardware/network behavior. A clean scan is not external acceptance and never
authorizes publishing; it is not a substitute for external acceptance or owner
authorization. Real clean-machine/platform testing, external secret scanning,
signing and owner authorization for the specific artifact/scope remain
MANUAL-PENDING. Never print or upload a detected secret; rotate real credentials.

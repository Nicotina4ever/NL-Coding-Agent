# Mandatory blocking pre-push secrets/content guard (stage 10 R1/R2/R3/R4, NL-BP-235)

scripts/prepush_guard.py is a blocking, read-only release guard. It must be run
before ANY upload, push, share or publication (including every earlier public
GitHub upload). It never pushes, commits, tags, fetches, publishes, changes
visibility/collaborators or rewrites history.

This document records the R2 acceptance review, the R3 synthetic-fixture
remediation, the R4 precise tests-only synthetic allowlist and the dated clean
working-tree measurements. The Lead decides verified status; nothing here claims
external acceptance or owner publication authorization, and bounded history is not
complete history coverage.

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
temporary files and the scanner still flags it with the same AWS rule.

## Precise tests-only known-synthetic allowlist (R4)

The remaining historical blocker was two bounded-history commits
(d9341cd3ee869cbce5f0cb58b8946cfaa191f2d1 and
3cae00c508e200c7ef88474b69cd1dc1dfec5304) that still contain the removed
hardcoded synthetic AWS-shaped fixture literal. The guard now carries one
documented, narrow known-synthetic allowlist entry with ALL of:

- exact value digest: 457643f44d19aed85fd756aa50cc0cd6b57376d4e8f5a72f9f85972a522002a3;
- exact path: tests/test_prepush_guard.py;
- exact rule: aws_access_key_id;
- exact scope: history;
- exact historical commits: d9341cd3ee869cbce5f0cb58b8946cfaa191f2d1 and
  3cae00c508e200c7ef88474b69cd1dc1dfec5304;
- mandatory explicit reason (runtime-assembled non-secret test fixture proving
  detection; hardcoded form removed in R3; no real credential involved).

This is not scanner weakening, not a blanket tests-tree/rule allowlist and not
finding suppression: a different digest, a different path, a different rule, a
staged/head scope or a different commit still blocks normally. The allowlist entry
is visible in JSON reports under report.allowlist.known_synthetic_fixtures and on
the allowlisted finding under finding.allowlist (digest/path/rule/scope/commits/
reason); values remain redacted and allowlisted findings are counted as
allowlisted, not blocking. The pre-existing generic --allowlist file plumbing
(tests/-only documented synthetic fixtures with sha256/path_prefix/reason) is
unchanged; no blanket allowlist file is added. This is ordinary Lead/local
development authorization for a synthetic non-secret fixture only; it suppresses
no real credential and does not grant owner publication authorization.

## Allowlist

The only external allowlist is for documented synthetic fixtures under tests/. JSON:

  {"fixtures": [{"sha256": "<64 hex>", "path_prefix": "tests/", "reason": "synthetic fixture"}]}

Entries with other prefixes are rejected. An allowlisted match is still reported
(allowlisted=true) but does not block; values remain redacted. Never allowlist real
credentials. The audit's documented synthetic-fixture digest allowlist is reused.
No blanket tests/ allowlist and no finding suppression is used.

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
6. Allowlist narrowness: the known synthetic value in a temp repo (different
   commit), the same value at another path, the same value in staged/head scope and
   a different AWS-shaped secret still block; only the exact historical tuple is
   allowlisted, and reports remain redacted.

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
guard exit fails the job. The R4 precise known-synthetic allowlist is built into the
guard, so the CI scan-all sees it without extra flags. CI covers the repository, not
local uncommitted working copies; local hook plus CI are complementary.

## Pre-upload use and repeatability at the actual release HEAD

Run scan-all before ANY earlier public GitHub upload, not only at the final
milestone. Repeat it at the actual release HEAD (after every commit/changed file
that can affect the repository) and after any allowlist decision. Record the exact
scan HEAD and report digest. The bounded history window and the documented scan
bounds must be disclosed: a clean bounded scan is not proof of unbounded/complete
history coverage or of external acceptance.

## Measured evidence: R4 clean scans (2026-10-29, Europe/Rome)

- Measured at: 2026-10-29, working tree on git HEAD
  e801a4cffcfbd24a1c7390facc2ff3bb1bef3a1a (task-93 changes uncommitted; reports
  reflect the current working tree).
- Commands (same detection rules, precise allowlist active by default):
  - python scripts/prepush_guard.py scan-staged --json-out
    .workspace/build/prepush_guard_r4/scan-staged.json --markdown-out ...scan-staged.md
  - python scripts/prepush_guard.py scan-head --json-out
    .workspace/build/prepush_guard_r4/scan-head.json --markdown-out ...scan-head.md
  - python scripts/prepush_guard.py scan-all --json-out
    .workspace/build/prepush_guard_r4/scan-all.json --markdown-out ...scan-all.md
- scan-staged: PASS exit 0, 0 files / 0 findings / 0 blocking (nothing staged at
  measurement time).
- scan-head: PASS exit 0, 450 files, 7,483,236 bytes, 169 findings, 0 blocking,
  3 allowlisted (pre-existing audit synthetic fixtures in
  tests/test_diagnostic_report.py, not real credentials), truncated=false; REVIEW
  classes only (private/loopback URLs, personal paths, high-entropy heuristics).
- scan-all: PASS exit 0, 630 files, 20,734,442 bytes, 202 findings, 0 blocking,
  5 allowlisted, truncated=false. The 5 allowlisted = 3 pre-existing
  tests/test_diagnostic_report.py synthetic fixtures + the 2 exact historical
  aws_access_key_id findings in tests/test_prepush_guard.py that now carry
  finding.allowlist.kind=known_synthetic_fixture with the documented reason and
  commits. No blocking finding and no non-allowlisted AWS-shaped finding in the
  current worktree/head.
- Allowlist visibility: report.allowlist.known_synthetic_fixtures has exactly one
  entry (digest/path/rule/scope/commits/reason); counts.allowlisted=5 for scan-all.
  The value is never printed: findings remain redacted (sha256_12/prefix/length).
- Reports (gitignored generated evidence):
  .workspace/build/prepush_guard_r4/scan-staged.json/.md,
  .workspace/build/prepush_guard_r4/scan-head.json/.md,
  .workspace/build/prepush_guard_r4/scan-all.json/.md.
- Prior R3 evidence (HEAD 144bd3a) was blocked only by the old bounded-history
  fixture commits and remains historical; R4 resolves that exact blocker with the
  precise allowlist.

### Bounded-history and authorization caveats

The scan is bounded (30 commits, changed paths, file/byte/finding caps), so a clean
scan is not unbounded/complete history coverage. The known-synthetic allowlist is
exact-digest/exact-path/exact-rule/exact-history-scope/exact-commits only; if those
commits leave the bounded window the allowlisted count naturally drops, and the
entry remains harmless. A final release-HEAD rerun is mandatory after the last
change that can affect the repository. This allowlist is ordinary Lead/local
development authorization for a synthetic non-secret fixture; it is not owner
publication authorization, not external acceptance, and does not authorize any
push/publication. Owner publication authorization and external acceptance remain
required.

## Acceptance review (Lead decides verified)

- Bullet 1 (separately runnable CLI + Git hook + CI integration block fail closed,
  non-zero, no silent bypass): MET in temporary-repo integration tests and the CI
  job configuration. Honest limits: the canonical repository hook is not installed
  by this task; git's --no-verify bypass is outside hook control; CI is the
  independent blocking environment.
- Bullet 2 (staged, tracked, history; secrets/private data/personal paths/config/
  runtimes/vendor/large blobs/dev data): MET by scan-staged/scan-head/scan-history/
  scan-all and the import-reused detection rules; the hook covers staged + bounded
  history. Bounded window and documented review-only heuristics are disclosed.
- Bullet 3 (redacted output/reports; never pushes, publishes or modifies the repo):
  MET by redaction tests, static source audit (no push/fetch/tag/network/history
  rewrite/destructive calls) and read-only report evidence; the tool writes only
  requested JSON/Markdown report paths.
- Bullet 4 (runnable before ANY earlier public upload; repeatably at actual release
  HEAD): MET at the measured R4 HEAD: scan-staged/scan-head/scan-all PASS with
  exit 0, 0 blocking findings, same rules, allowlist visible, reports redacted. A
  final release-HEAD rerun remains mandatory and bounded-history/external
  acceptance/owner authorization caveats apply.

## Limits: not a substitute for external acceptance

This guard is necessary but not sufficient. It cannot detect every credential
format, encrypted/binary content, external services, legal/license compliance or
real hardware/network behavior. A clean scan is not external acceptance and never
authorizes publishing; it is not a substitute for external acceptance or owner
authorization. Real clean-machine/platform testing, external secret scanning,
signing and owner authorization for the specific artifact/scope remain
MANUAL-PENDING. Never print or upload a detected secret; rotate real credentials.

# Mandatory pre-push secrets/content guard (stage 10 R1, NL-BP-235)

scripts/prepush_guard.py is a blocking, read-only release guard. It must be run
before ANY upload, push, share or publication. It never pushes, commits, tags,
fetches, publishes, changes visibility/collaborators or rewrites history.

## Modes

- scan-staged: scans the Git index (staged content) before a commit/push.
- scan-head: scans tracked files at HEAD plus the working tree.
- scan-history: scans a bounded window of Git history (commits, changed paths,
  bounded bytes) for secrets/artifacts that were committed and later removed.
- scan-all: runs staged + head + bounded history (used by CI).
- hook: Git pre-push mode; reads the refs Git sends on stdin, scans staged content
  and bounded history, and exits non-zero on findings before any push.
- install-hook: prints the hook that would be installed (dry-print by default).
  --force writes it; if a hook already exists, --backup is required and the old
  hook is backed up first. This repository's canonical .git/hooks is not modified
  by the task/tests; install explicitly in a checkout when authorized.

Global flags: --repo PATH, --allowlist FILE, --json, --json-out FILE,
--markdown-out FILE. Exit codes: 0 clean, 1 findings/blocked or bounds fail-closed,
2 usage/invalid allowlist/not a Git repository, 3 operational failure (hook fails
closed).

## Detection and reuse

Secret patterns, redaction, classification and artifact rules are imported from
scripts/audit_release_secrets.py. The guard does not duplicate regexes. It adds
scope handling for staged/head/history and checks for:

- credentials/tokens/secrets (high-confidence provider patterns, generic
  assignments, high-entropy values);
- personal absolute paths, private/loopback URLs and sensitive config;
- embedded runtimes, vendor copies, databases, user data, logs, build outputs;
- large blobs above the 5 MiB threshold and upload-exclusion artifact paths.

Findings are redacted (SHA-256[0:12], prefix at most 4 chars, length; context
matches replaced with [REDACTED:<hash>]). Full values never appear in stdout,
JSON, Markdown or reports. Scans are bounded (file/total bytes, commit count,
findings), and reaching a bound fails closed.

Documentation/markdown files are still scanned for explicit credential patterns,
but review-only personal-path/entropy heuristics are skipped there to avoid
documentation examples blocking releases. This is a documented review policy, not
a silent skip; executable/config/source artifacts are scanned fully.

## Allowlist

The only allowlist is for documented synthetic fixtures under tests/. A JSON file:

{
  "fixtures": [
    {"sha256": "<64 hex>", "path_prefix": "tests/", "reason": "synthetic fixture"}
  ]
}

Entries with other prefixes are rejected. An allowlisted match is still reported
(allowlisted=true) but does not block; values remain redacted. The audit's
documented test-fixture digest allowlist is reused as well. Never allowlist real
credentials.

## Install and use

Run manually before every push/upload:

  python\python.exe scripts/prepush_guard.py scan-all --json-out reports/prepush_guard.json --markdown-out reports/prepush_guard.md

Install the hook in an authorized checkout (default prints only):

  python\python.exe scripts/prepush_guard.py install-hook
  python\python.exe scripts/prepush_guard.py install-hook --force --backup

The hook invokes the guard in blocking mode on pre-push; no push proceeds if the
guard exits non-zero. The installed hook is a convenience, not a replacement for
running the guard in CI.

## CI gate

.github/workflows/ci.yml has a blocking secrets-scan job on ubuntu-latest with
contents: read, no publish/push/visibility/collaborator actions, running scan-all
on the checkout and uploading reports only. A non-zero guard exit fails the job.

## Limits: not a substitute for acceptance

This guard is necessary but not sufficient. It cannot detect every credential
format, encrypted/binary content, external services, legal/license compliance or
real hardware/network behavior. A clean scan is not external acceptance and never
authorizes publishing. Real clean-machine/platform testing, external secret
scanning, signing and owner authorization remain MANUAL-PENDING. Never print or
upload a detected secret; rotate real credentials.

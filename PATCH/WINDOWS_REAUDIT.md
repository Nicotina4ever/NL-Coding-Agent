# Windows Newline Re-Audit of the Audited Safety Foundation Patch (C1b)

**Date:** 2026-10-28
**Repository:** `K:\AI\NL Coding Agent`
**Scope:** the five files of the audited Safety Foundation Patch (`PATCH/**`), applied as-is in C1a
except for the single test-fixture fix documented here.

## What was re-audited

`SHA256_MANIFEST.json` certifies the audited patch files. Before application, all five PATCH hashes
matched the manifest (5/5 PASS). After applying the five files to their root paths (commit C1a),
the audited tests were run:

```powershell
python\python.exe -m pytest tests/test_staging_broker_adversarial.py tests/test_rollback_stub.py -q
# 9 passed, 1 failed
```

Failure: `tests/test_rollback_stub.py::TestRecoveryStore::test_restore_only_known_agent_postimage`
-> `AssertionError: ['planner.py'] is not false` (the rollback was correctly *blocked*).

## Root cause (Windows text-mode newline translation)

- The test fixture writes text with `Path.write_text(..., encoding='utf-8')`; on Windows this
  translates `\n` to `\r\n` bytes.
- `recovery_store.save_snapshot`/with`rollback_from_snapshot` compare **byte** hashes
  (`sha256_bytes`), while the test's `expected_post_hashes` uses `sha256_text` over the original
  string (LF). The current file bytes (CRLF) therefore did not match the recorded post-image and the
  rollback was conservatively blocked. The production behaviour is fail-closed and correct; the
  fixture was Windows-incompatible.

## Fix (test fixture only, no production semantics changed)

`Path.write_text(..., newline='')` is used for every fixture write in
`tests/test_rollback_stub.py` (root copy and `PATCH/tests/test_rollback_stub.py`), disabling
newline translation so fixture bytes match the recorded LF hashes.

- `tests/test_staging_broker_adversarial.py` (audited): unchanged, **7 passed**.
- `tests/test_rollback_stub.py`: newline fix only, **3 passed**.
- Re-audited file SHA-256:
  - previous audited hash: `84dc98111ee9d459822e6f65feb9903e17ad716c267b9c435ae4f14eccd4c2ae`
  - new hash:              `04543865eaca4a9e980b1fcc64f8de66def3a631e04d386f54f4716025117d23`
  - `SHA256_MANIFEST.json` updated accordingly; the PATCH copy and the root copy are identical.

## Mandatory integration constraint (carried into C2+ and the phase-2 plan)

This failure is the same class of defect measured for the *normal model write path*:
`filesystem.scoped_write_file/scoped_patch_file` use `Path.write_text`, which produces CRLF on
Windows, while the broker hashes normalized text. Without adaptation, recovery CAS cannot recognise
the bytes the promotion just wrote.

Required in phase 2 (see `docs/PHASE2_HARNESS_INTEGRATION_PLAN.md` section 4.7):

1. model-facing writers use `newline=''` (C2);
2. `normalize_staged_newlines(stage)` after every model stage and before every validation (C3/C6);
3. `assert_byte_hash_invariant(stage)` before mark/promote: assert
   `sha256_bytes(bytes) == sha256_text(text) == manifest delta after`; any mismatch blocks the
   mission without touching the live tree;
4. recovery `expected_post_hashes` are derived from the same staged bytes that promotion writes.

## Verdict

Audited production modules applied byte-verbatim (3/3 hashes matched before application). The one
audited test fixture required a Windows-only newline correction; semantics and security properties of
the gate are unchanged. Full safe suite result is recorded in the C1b commit message.

# Beta acceptance records (cross-platform private beta)

This document defines how the owner/testers record **real-hardware beta acceptance**
for the six native targets and how the release-acceptance matrix is generated. It is
separate from CI: CI is headless regression evidence and is **never** hardware support.

## Tool

`scripts/release_acceptance.py` has three commands (stdlib only, no network, no
model, no upload/push):

```powershell
python\python.exe scripts/release_acceptance.py matrix --records-dir docs\evidence\beta_acceptance --json-out docs\evidence\beta_acceptance\acceptance_matrix.json --markdown-out docs\evidence\beta_acceptance\acceptance_matrix.md
python\python.exe scripts/release_acceptance.py record --input C:\temp\my-record.json
python\python.exe scripts/release_acceptance.py verify --records-dir docs\evidence\beta_acceptance --json
```

- **matrix** reads committed evidence (installer/platform_targets.py, docs/HARNESS_ACCEPTANCE.md,
  docs/RELEASE_ACCEPTANCE.md, docs/SECRETS_AUDIT.md, .github/workflows/ci.yml) plus validated
  tester records. It prints/writes a deterministic JSON+Markdown matrix with states
  verified, partial, MANUAL-PENDING. CI is shown as partial (headless only) and can never make a
  target row verified. Non-Windows/non-WSL targets stay MANUAL-PENDING until a real tester
  record exists.
- **record** validates one tester JSON and stores it under docs/evidence/beta_acceptance/ with a
  canonical filename. Missing/invalid fields, checksum/target mismatches and unsupported hardware
  claims are rejected with exit code 2. Personal absolute paths are redacted to
  <redacted-path> before storage. Existing records are never overwritten.
- **verify** re-validates every stored record and prints a summary; exit 1 if any record is invalid.

## Tester record format

```json
{
  "schema_version": "1.0",
  "tester_alias": "tester-1",
  "timestamp": "2026-10-28T12:00:00+00:00",
  "target_id": "windows-x86_64",
  "os": "windows",
  "arch": "x86_64",
  "package": {"version": "0.1.0-beta", "sha256": "<64 lowercase hex>"},
  "install_path_type": "clean-custom",
  "evidence_notes": "clean machine, no global Python; screenshots retained by the owner",
  "steps": {
    "install": {"result": "pass", "evidence_note": "installed to a clean non-default path"},
    "startup": {"result": "pass", "evidence_note": "GUI opened"},
    "cli": {"result": "pass", "evidence_note": "doctor/status worked"},
    "gui": {"result": "pass", "evidence_note": "window/menus usable"},
    "clipboard": {"result": "pass", "evidence_note": "screenshot + file paste verified"},
    "mic": {"result": "pass", "evidence_note": "recording/transcript verified"},
    "asr_tts": {"result": "pass", "evidence_note": "local ASR/TTS verified"},
    "gpu": {"result": "pass", "evidence_note": "GPU usage observed in task manager"},
    "offline": {"result": "pass", "evidence_note": "offline install/run verified"},
    "restart": {"result": "pass", "evidence_note": "restart preserved state"}
  }
}
```

Required steps: install, startup, cli, gui, clipboard, mic, asr_tts, gpu, offline, restart.
Each step result is pass, fail, not-tested or manual-pending. Hardware steps (clipboard, mic,
asr_tts, gpu) require an explicit evidence_note when claiming pass. A support_claimed or
hardware_verified=true field is rejected unless every hardware step has an explicit pass result.
Install path type: clean-custom, clean-default, upgrade, or portable.

## Privacy and ownership

- Use a **tester alias only** (2-40 letters/digits/._-); names and emails are rejected.
- Do not include credentials, tokens, license keys, screenshots with personal data, usernames in
  absolute paths or machine serials. Absolute personal paths (C:\Users\..., /home/...,
  /Users/..., UNC paths) are redacted automatically, but avoid them anyway.
- evidence_notes may reference owner-held screenshots/logs; do not store binary evidence in this
  repository.
- Records are tracked JSON under docs/evidence/beta_acceptance/; the owner reviews them before
  commit. This tool never uploads them anywhere.

## States and MANUAL-PENDING policy

- verified target: all required steps, including all four hardware steps, have explicit pass
  results in a real tester record. CI alone never produces verified.
- partial: at least one standard step passed but hardware/other steps are pending/failed.
- MANUAL-PENDING: no valid real record, or no real step result yet.
- A green CI workflow (when it runs) is only regression evidence; it does not prove GUI,
  clipboard, microphone, ASR/TTS, GPU, clean-machine installation, signing or native behavior.
- Unsupported/unrecorded configurations remain experimental and must not be described as
  supported. No cross-platform support claim is allowed before the matrix rows for those targets
  are verified by real records and the owner authorizes distribution.

This matrix and any single record are not a support claim.\n\n## No publishing

The tool performs no network access, model calls, package uploads, git pushes, releases,
visibility changes or collaborator changes. It only reads committed evidence and writes
validated local record/matrix files.

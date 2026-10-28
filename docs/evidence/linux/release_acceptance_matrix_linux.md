# Release acceptance matrix

Generated from committed evidence and validated tester records. States: verified / partial / MANUAL-PENDING. CI is never hardware support.

## Targets

| Target | OS/arch | Acceptance | Hardware verified | CI (headless only) | Records | Pending steps |
|---|---|---|---|---|---|---|
| windows-x86_64 | windows/x86_64 | MANUAL-PENDING | no | partial | 0 | install, startup, cli, gui, clipboard, mic, asr_tts, gpu, offline, restart |
| windows-arm64 | windows/arm64 | MANUAL-PENDING | no | partial | 0 | install, startup, cli, gui, clipboard, mic, asr_tts, gpu, offline, restart |
| linux-x86_64 | linux/x86_64 | MANUAL-PENDING | no | partial | 0 | install, startup, cli, gui, clipboard, mic, asr_tts, gpu, offline, restart |
| linux-aarch64 | linux/aarch64 | MANUAL-PENDING | no | partial | 0 | install, startup, cli, gui, clipboard, mic, asr_tts, gpu, offline, restart |
| macos-x86_64 | macos/x86_64 | MANUAL-PENDING | no | partial | 0 | install, startup, cli, gui, clipboard, mic, asr_tts, gpu, offline, restart |
| macos-arm64 | macos/arm64 | MANUAL-PENDING | no | partial | 0 | install, startup, cli, gui, clipboard, mic, asr_tts, gpu, offline, restart |

## Requirements

| Requirement | State | Evidence |
|---|---|---|
| NL-BP-140 | partial | docs/PRODUCT_BACKLOG.md: NL-BP-140 |
| NL-BP-164 | partial | docs/RELEASE_ACCEPTANCE.md: NL-BP-164 | PARTIAL: cross-platform acceptance matrix documented and generated in docs/evidence/beta_acceptance/ACCEPTANCE_MATRIX.md (six targets MANUAL-PENDING, 0 invalid records); real-hardware/clean-machine acceptance records still MANUAL-PENDING | |
| NL-BP-165 | MANUAL-PENDING | no committed real-hardware acceptance record; MANUAL-PENDING |

## Gates

| Gate | State | Note |
|---|---|---|
| CI | partial | CI workflow committed; results are headless/regression evidence and never real-hardware support |
| CLEAR-WITH-REVIEW | partial | owner review/authorization remains required; audit must be re-run at HEAD |
| real-hardware beta acceptance | MANUAL-PENDING | requires tester records with explicit per-step results; CI can never mark this verified |

## Summary

- verified targets: 0
- partial targets: 0
- MANUAL-PENDING targets: 6
- invalid records: 0
- CI hardware support claimed: no

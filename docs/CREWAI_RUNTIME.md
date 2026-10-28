# CrewAI Runtime Integration

## Status

Native runtime integration is the second step in the distribution goal. The application uses the
`crewai` package installed in the embedded Python runtime; the vendor/reference checkout is
reference-only and, since ROOT REORG Phase C (task-46, 2026-10-28), is staged at
`da_eliminare/crewAI/` after read-only evidence proved the application never imports it. It was
moved (never deleted, copied or rewritten); the move is reversible and the checkout keeps its
nested `.git`, docs and license. See `docs/CREWAI_CHECKOUT_REMOVAL_PROPOSAL.md`.

## Pinned Version

`pyproject.toml` declares:

```toml
dependencies = [
    "PySide6",
    "psutil",
    "crewai==1.15.32",
    "PyYAML",
]
```

The installed runtime version is `1.15.32`.

## Runtime Import Evidence

Command:

```powershell
python\python.exe -c "import crewai, sysconfig; from pathlib import Path; print(Path(crewai.__file__).resolve()); print(Path(sysconfig.get_paths()['purelib']).resolve()); print(crewai.__version__)"
```

Observed output:

```text
K:\AI\Coding Agent\python\Lib\site-packages\crewai\__init__.py
K:\AI\Coding Agent\python\Lib\site-packages
1.15.32
```

The two paths above are the observed pre-relocation output of 2026-10-28 and are preserved as
historical evidence. The runtime currently lives under the canonical repository root:
`K:\AI\NL Coding Agent\python\Lib\site-packages`.

`tests/test_crewai_runtime.py` asserts that the imported package lives under the runtime's
`site-packages` directory, is not inside the vendor checkout (now staged at
`da_eliminare/crewAI/`), and reports the pinned version.

## Vendor Checkout Policy

- `da_eliminare/crewAI/` is the reference-only upstream CrewAI checkout (own `.git`). It was
  moved there intact by ROOT REORG Phase C (task-46) and is not imported by the application.
- Excluding it from portable payloads and source releases remains in place; deleting the staged
  checkout requires explicit repository-owner authorization (see the proposal document).
- `crewAI-tools/` is absent from this workspace at audit time. If it is restored later, the same
  protected-vendor/staging policy applies.

## License Follow-Up

Before distribution, include the upstream CrewAI license and copyright notice in the payload.
The staged vendor `da_eliminare/crewAI/LICENSE` contains the CrewAI copyright notice and an MIT-style permission
grant. This is not a complete third-party license audit: transitive Python dependencies,
PySide6/Qt, and any bundled tools must be audited separately, and model weights are licensed
separately from the application.

## Verification

```powershell
python\python.exe -m pytest tests\test_crewai_runtime.py
python\python.exe -m pytest
```

Both commands must pass before the mission is considered complete. This document does not claim
that a portable build or installer has been produced.


## C4e: SBOM, compatibility and rollout decision (2026-10-28)

Read-only gate: ```python\python.exe scripts\check_crewai_upgrade.py --verify-sbom docs\evidence\crewai_sbom.json```
and ```--compat``` (no install/network/model call). Tracked deterministic artifact:
```docs/evidence/crewai_sbom.json``` (schema 1.0, no timestamps): pinned chain
```crewai==crewai-core==crewai-cli==1.15.32```, dependency inventory, per-distribution
files sha256, import-path evidence, API compatibility baseline and license evidence.

Measured license gap: installed ```crewai```, ```crewai-core``` and ```crewai-cli``` metadata report
```License=None``` (no License-Expression). Upstream/reference MIT text and copyright line are
recorded from ```da_eliminare/crewAI/LICENSE``` (sha256 in the SBOM; path updated by the Phase C staging); manual/legal review of transitive
dependencies remains required before distribution.

Telemetry/storage: ```crew_runtime_env()``` sets PYTHONUTF8, PYTHONIOENCODING=utf-8, NO_COLOR,
OTEL_SDK_DISABLED, CREWAI_DISABLE_TELEMETRY, CREWAI_DISABLE_TRACKING; Flow state is persisted
only in the application SQLite DB (```AppFlowPersistence```), never in CrewAI default
@BT3%%LOCALAPPDATA%%/CrewAI``` storage. CrewAI memory remains off by default.

API compatibility baseline: crewai Agent/Task/Crew/LLM/Process, flow Flow/FlowState/start/
listen/router, persistence FlowPersistence/persist, async feedback HumanFeedbackPending/
HumanFeedbackProvider/PendingFeedbackContext, flow events; ```--compat``` PASS.

## Rollout decision (human-reviewed, 2026-10-28)

Sequential remains the default pipeline; the CrewAI Flow pipeline is opt-in only
(```pipeline="flow"``` / ```supervisor run --pipeline flow```). Reason: stage-4 Flow
evidence is fake-model only; real-model Flow acceptance is absent, so enabling Flow by default
would overstate verification. No gate was weakened, promotion remains last, sequential path is
unchanged. Revisit only after a real local-model Flow acceptance is recorded.

## Limitations

- No real-model Flow mission/acceptance run in stage 4; all Flow/parity evidence is fake-model
  in temp projects/DBs.
- No OS sandbox/network isolation: candidate/test code runs with user privileges.
- Memory is off; HITL approvals are opt-in (Flow path), not the sequential default.
- SBOM is a measured-environment snapshot; drift must be regenerated and re-reviewed.

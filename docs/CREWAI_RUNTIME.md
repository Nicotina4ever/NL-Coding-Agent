# CrewAI Runtime Integration

## Status

Native runtime integration is the second step in the distribution goal. The application uses the
`crewai` package installed in the embedded Python runtime; the repository's `crewAI/` directory
remains vendor/reference source only. No vendor files are deleted, moved, or rewritten.

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
`site-packages` directory, is not inside the repository's `crewAI/` checkout, and reports the
pinned version.

## Vendor Checkout Policy

- `crewAI/` is protected vendor/reference source. It is not imported by the application.
- Excluding `crewAI/` from a portable payload is the intended size reduction; deleting or
  rewriting the checkout requires explicit user approval.
- `crewAI-tools/` is absent from this workspace at audit time. If it is restored later, the same
  protected-vendor policy applies.

## License Follow-Up

Before distribution, include the upstream CrewAI license and copyright notice in the payload.
The vendored `crewAI/LICENSE` contains the CrewAI copyright notice and an MIT-style permission
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

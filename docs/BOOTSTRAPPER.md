# Bootstrapper and Reproducible Release Foundation (Stage 6a)

**Status:** implemented foundation; measured locally; **clean-machine acceptance remains manual-pending** (a clean Windows machine without the development workspace or a global Python cannot be exercised in this environment).
**Task:** shared `task-32`. Owner: runner-integrator.
**Scope:** lightweight per-user bootstrapper (`installer/`), reproducible source-only release builder (`scripts/build_release.py`), platform manifest schema, offline bundles, tests and this documentation.
**Not claimed:** a signed installer, a published download endpoint, uninstall/OS integration, a bundled production runtime, clean-machine acceptance, Linux/macOS acceptance.

---

## 1. What exists now

| Component | File | Purpose |
|---|---|---|
| Bootstrapper CLI | `installer/bootstrap.py` | plan (default, dry run), install, update, repair, verify, cache list/verify/prune/clear, offline bundle mode |
| Manifest schema | `installer/platform_manifest.py` | loads and validates platform manifests; component/platform resolution; sha256/size checks |
| Fetcher | `installer/fetcher.py` | urllib streaming download with atomic staging + hash/size verification; offline bundle fetcher (no network) |
| Operations | `installer/operations.py` | plan/install/update/repair/verify, shared cache, install state, safe target rules |
| Manifest template | `installer/platform_manifest.json` | schema + platform matrix example (status template, `release_ready: false`; not installable) |
| Release builder | `scripts/build_release.py` | deterministic tracked-source zip + `release-manifest.json` + installer-compatible `platform-manifest.json` |
| Target catalogue | `installer/platform_targets.py` | canonical six OS/arch targets, host detection, strict native guard (Windows runtime is never reused on Linux/macOS) |
| Native runtime manifest | `installer/runtime_manifest.py` + `installer/runtime_manifest.json` | six-target runtime/dependency pins, per-target selectors, measured-only sha256/size, optional CPU/GPU/ASR/TTS declarations, release_ready gating, macOS universal2 decision |
| Cross-platform provisioner | `installer/provision.py` | selects the native runtime per OS/arch, verifies hashes, reuses cache/atomic staging/offline bundle/repair/update, fails closed with guidance |
| Archive support | `installer/operations.py` | safe `zip`, `tar.gz` and `tar` extraction with traversal/symlink rejection |
| Tests | `tests/test_bootstrap_installer.py`, `tests/test_build_release.py` | 40 targeted tests, fake/local artifacts only, no network |

Everything is standard library only (Python >= 3.10): no global Python/pip/uv/conda, no second environment, no third-party package, no admin/elevation.

---

## 2. Measured local evidence (2026-10-28)

The measurements below were taken before ROOT REORG Phase B (shared `task-45`); the measured
artifacts were moved unchanged into `.workspace/`, so the paths shown are the current equivalent
locations under the single workspace policy (default `<repo>/.workspace`).

| Step | Command | Result |
|---|---|---|
| Build candidate | `python scripts/build_release.py --name stage6a-source-candidate --json` | `.workspace/dist/stage6a-source-candidate`: 255 tracked files, 3,625,705 B input; zip 1,053,218 B sha256 `55ea86742a8af56267cbc51366f2187292cc43771762348ade535695893eaa06` |
| Reproducibility | two builds into `.workspace/build/phase6a/repro-a` and `.workspace/build/phase6a/repro-b` | identical candidate name, identical file set, **byte-identical** `release-manifest.json`, `platform-manifest.json` and source zip (same sha256) |
| Offline plan | `python installer/bootstrap.py plan --offline-bundle .workspace/dist/stage6a-source-candidate --target .workspace/build/phase6a/install-test --cache .workspace/build/phase6a/cache --json` | `installable: true`, 1,053,218 B to fetch, cache misses 0 -> 1, no writes |
| Offline install | same with `install` | `status: installed`, 255 files / 3,625,705 B, 1 artifact into shared cache |
| Verify | `python installer/bootstrap.py verify --target .workspace/build/phase6a/install-test --json` | `status: verified`, `ok: true`, 255/255 files, 3,625,705 B checked, 0 missing/modified |
| Cache | `python installer/bootstrap.py cache list --cache .workspace/build/phase6a/cache --json` | 1 content-addressed entry, 1,053,218 B |

The existing stale `.workspace/dist/portable-release` was not touched: the new source-only candidate (`.workspace/dist/stage6a-source-candidate`, zip 1,053,218 B + manifests) is a separate, newly created directory (the builder refuses to overwrite any existing candidate), and `python/` and `crewAI/` were not copied. That candidate and the `.workspace/build/phase6a/` smoke workspace are retained as measured stage-6a evidence for Lead review only; they are not a verified full release (no runtime bundle), and removing/replacing or promoting them is a Lead decision under the repository structure policy (at most one verified release candidate under `.workspace/dist/`).

---

## 3. Architecture

```text
release pipeline (future publishing)          user machine
-------------------------------              --------------------------------
scripts/build_release.py                     installer/bootstrap.py
  tracked files -> deterministic zip          plan (default, dry-run)
  release-manifest.json                       install --target <user dir>
  platform-manifest.json  ------------------>  update / repair / verify
  (relative component URLs)                    cache list|verify|prune|clear
        |                                      |
        |  online: base_urls + urllib           |  offline: --offline-bundle <dir>
        v                                      v
   TLS stream -> sha256/size verify -> atomic publish -> shared content-addressed cache
                                                          -> isolated target install
```

### Manifest schema (platform manifest)

A release manifest is JSON with `schema_version: 1` and:

| Field | Meaning |
|---|---|
| `product` | `id`, `name`, `version`, `channel` |
| `release_ready` | false for documentation templates; install/update/repair refuse templates |
| `base_urls` | `primary` URL plus optional `mirrors`; component `url` values may be relative to the primary base |
| `platforms` | per-platform entry: `display_name`, `launcher`, `runtime_component`, ordered `components` list |
| `components` | ordered list: `id`, `kind` (`app`/`runtime`/`assets`/`config`/`launcher`/`offline`), `version`, `archive` (`zip`/`file`), `destination` (relative to target), `sha256`, `size`, `url`, `platforms`, `optional` |

Optional components (for example a platform runtime that is not bundled in a source-only release) may omit sha256/size in the trailing metadata only when `optional: true`; non-optional components in a `release_ready` manifest require a positive size and a valid 64-hex sha256. The runtime_component on each platform documents the runtime entry; it is installed only when it appears in that platform components list.

The shipped `installer/platform_manifest.json` is a **template**: `release_ready: false`, placeholder hashes/sizes and example invalid base URLs. Real manifests are emitted by `scripts/build_release.py` or authored by the release pipeline.

### Install state and layout

Each install writes `install.json` into the target root: product/version/platform/launcher, per-component archive hashes, every extracted file with its sha256/size, cache hits/downloads and warnings. `verify` recomputes those hashes; `update`/`repair` keep the previous target as a sibling backup directory (`.<name>.backup-<utc>`) instead of deleting it. Launchers and user data stay outside installer ownership: `NL_DATA_DIR` remains the application data mechanism.

---

## 4. Commands

```powershell
# Default mode is a dry-run plan; it never writes or downloads.
python installer/bootstrap.py plan --manifest C:/releases/0.2.0/platform-manifest.json

# Install into a new/empty user-selected directory (never global, never admin).
python installer/bootstrap.py install --target C:/Users/me/Apps/NL-Coding-Agent --manifest C:/releases/0.2.0/platform-manifest.json --cache C:/Users/me/AppData/Local/NL-Coding-Agent/cache

# No-network install from an offline bundle directory (manifest.json + artifacts).
python installer/bootstrap.py install --target C:/Users/me/Apps/NL-Coding-Agent --offline-bundle .workspace/dist/stage6a-source-candidate --cache C:/temp/nl-cache

# Update/repair/verify an existing managed installation.
python installer/bootstrap.py update --target C:/Users/me/Apps/NL-Coding-Agent --manifest C:/releases/0.3.0/platform-manifest.json
python installer/bootstrap.py repair --target C:/Users/me/Apps/NL-Coding-Agent --offline-bundle .workspace/dist/stage6a-source-candidate
python installer/bootstrap.py verify --target C:/Users/me/Apps/NL-Coding-Agent --json

# Shared cache management (clear/prune require --yes).
python installer/bootstrap.py cache list   --cache C:/Users/me/AppData/Local/NL-Coding-Agent/cache
python installer/bootstrap.py cache verify --cache C:/Users/me/AppData/Local/NL-Coding-Agent/cache
python installer/bootstrap.py cache prune  --cache C:/Users/me/AppData/Local/NL-Coding-Agent/cache --keep-days 30 --yes
python installer/bootstrap.py cache clear  --cache C:/Users/me/AppData/Local/NL-Coding-Agent/cache --yes
```

Exit codes: 0 ok/plan/verified; 2 usage, manifest, target or install-state error; 3 verification failed; 4 artifact download/verification error; 5 reserved for unsafe/refused operations.

### Online vs offline

- **Online** uses `urllib.request` (TLS, timeout, streaming) against `base_urls.primary` + component URL; bytes are hashed while streaming, the declared size is enforced, and only a fully verified temporary file is atomically renamed into the cache.
- **Offline bundle** is a directory containing `manifest.json` or `platform-manifest.json` plus local artifacts; component URLs resolve inside the bundle only (absolute paths and `..` escapes are rejected). No network call is made. A `scripts/build_release.py` candidate directory is directly usable as an offline bundle.
- Tests never use the network: they use fake/local artifacts and an injected opener only for unit-testing the urllib path.

### Shared cache and isolation

Cache layout: `<cache>/artifacts/<sha256>/<artifact-name>`. Entries are content-addressed and immutable; multiple isolated target installs share the same cache, and a corrupt cache entry is detected, discarded and re-fetched. `plan` reports cache hits/download bytes; `cache verify` re-hashes entries; `prune` removes entries older than `--keep-days`; `clear` requires `--yes`. No target file is linked to another target, so installs are independent copies.

---

## 5. Security and safety properties (implemented)

- sha256 + exact size verification for every artifact, both in the fetcher and again before installation.
- Atomic artifact publish (`.nlcoding-part` temp -> verify -> `os.replace`); no partial cache/install files on failure.
- Install/update/repair stage into a sibling temporary directory and only then move into place; failures leave the previous target intact.
- Zip extraction rejects absolute paths, `..` entries, drive paths and symlink entries (zip-slip protection).
- Target rules: user-selected directory only; refuses filesystem root and system/global locations (Windows/Program Files/ProgramData, posix system dirs); install requires a new or empty directory; update/repair require an existing `install.json`.
- Update/repair preserve the previous installation as a backup directory; user files in the target are never expected (target is program payload only), and user data stays in `NL_DATA_DIR`.
- No downloaded code is executed by the bootstrapper; no global install, no registry/service changes, no elevation request, no shell invocation.
- No network in offline mode; online mode is HTTPS-only (non-HTTP component URLs are refused by the fetcher).

Trust limitation: integrity is anchored in the manifest (sha256). A compromised manifest can describe a different payload; production distribution should sign manifests/releases and serve them over an authenticated channel (out of scope for this foundation).

---

## 6. Reproducible source release builder

```powershell
# Plan only (no writes): files/size/version/head/candidate name.
python scripts/build_release.py --plan --json

# Build a new candidate under .workspace/dist/ (refuses to overwrite an existing directory).
python scripts/build_release.py --json

# Two builds from the same inputs are byte-identical (same zip and manifests).
python scripts/build_release.py --output-parent .workspace/build/phase6a/repro-a --json
python scripts/build_release.py --output-parent .workspace/build/phase6a/repro-b --json

# Optional prebuilt runtime archive (python/ and crewAI/ are never copied from the workspace).
python scripts/build_release.py --with-runtime-archive C:/build/python-3.12.10-win64.zip --runtime-platform windows-x86_64 --runtime-version 3.12.10
```

Candidate contents:

| File | Content |
|---|---|
| `nl-coding-agent-<version>-source.zip` | tracked source files, sorted, fixed zip metadata (1980-01-01, create_system=3, mode 100644), deterministic compression |
| `release-manifest.json` | product/version, git head + short, tracked hash, per-file sha256/size, archive sha256/size, platform matrix, runtime info, explicit exclusions, generator version |
| `platform-manifest.json` | installer-compatible release manifest with relative component URL for the zip (candidate directory works as an offline bundle); optional runtime component only when an archive was supplied |

Optional `runtime/<archive>` is added only for `--with-runtime-archive`.

Determinism rules: no timestamps in manifests, no absolute paths, sorted file/component order, `json.dumps(sort_keys=True)`, fixed zip entry metadata, no environment data, version parsed from `nl_coding_agent/core/version.py`, HEAD from read-only git. Only git-tracked files are packaged; untracked files are never included.

Default exclusions: `.git`, `.workspace/`, `data/`, `python/`, `crewAI/`, `crewAI-tools/`, `PATCH/`, `.agents/`, caches (`__pycache__` etc.), bytecode, SQLite/log files, `config/voicebridge.yaml`, `.env`, `SHA256_MANIFEST.json`, `temp_*.py` and `*.patch` artifacts. The builder writes only a NEW candidate directory (default parent `<source>/.workspace/dist`), refuses existing paths and never deletes, moves or rewrites anything - including the existing stale `.workspace/dist/portable-release` (removal/replacement requires explicit authorization).

---

## 7. Cross-platform native runtime provisioner (private beta)

The private beta targets six OS/architecture pairs. Target ids are shared by the
manifests, the release builder and the provisioner:

| Target | OS / arch | Runtime id | Runtime archive | Status |
|---|---|---|---|---|
| `windows-x86_64` | Windows 11 x64 | `python-runtime-windows-x86_64` | zip | manifest template; artifact not measured yet |
| `windows-arm64` | Windows 11 ARM64 | `python-runtime-windows-arm64` | zip | manifest template; artifact not measured yet |
| `linux-x86_64` | Linux x86_64 | `python-runtime-linux-x86_64` | tar.gz | manifest template; artifact not measured yet |
| `linux-aarch64` | Linux ARM64 | `python-runtime-linux-aarch64` | tar.gz | manifest template; artifact not measured yet |
| `macos-x86_64` | macOS Intel | `python-runtime-macos-x86_64` | tar.gz | manifest template; artifact not measured yet |
| `macos-arm64` | macOS Apple Silicon | `python-runtime-macos-arm64` | tar.gz | manifest template; artifact not measured yet |

### Native runtime selection and no Windows reuse

- `installer/platform_targets.py` is the single source of truth for the six targets, host detection,
  aliases and the strict native guard. On an unsupported OS/arch (for example Linux riscv64)
  the provisioner fails closed with the list of supported targets and guidance.
- `installer/provision.py` selects only the runtime declared for the detected (or explicitly
  requested) target. The repository `python/` Windows x64 runtime is never referenced, copied or
  reused by the provisioner; it consumes manifest-declared artifacts only. A Windows artifact is
  rejected on Linux/macOS even if a manifest wrongly declares it for that target, and vice versa.
- Install/update/repair require the selected target to match the native host; a cross-target plan is
  allowed for release review, but cross-target installation fails closed.
- Downloads are hash+size verified, staged atomically, stored in the shared content-addressed cache
  and reused offline; the provisioner delegates this to the same `installer/operations.py` machinery
  already used by the bootstrapper (cache isolation and repair/update included).

### Manifest policy: measured hashes only, release_ready gating

- `installer/runtime_manifest.json` is a template with `release_ready: false`. Every unmeasured runtime
  has `sha256: ""` and `size: 0`; the validator rejects an unmeasured artifact that declares a
  sha256/size (never fabricate hashes) and rejects a measured artifact without a real hash and
  positive size.
- A runtime manifest becomes `release_ready: true` only when all six native runtimes are measured.
  The provisioner refuses install/update/repair from a template or partially measured manifest.
- `scripts/build_release.py` emits `runtime-manifest.json` for the candidate. Measured archives are passed
  as `--runtime-archive TARGET=PATH` (repeatable); unmeasured targets keep explicit empty
  placeholders. The generated manifest is validated by the same schema.

### Optional CPU/GPU/ASR/TTS components (graceful degradation)

Each target declares optional components with `optional: true`, `required: false` and an explicit
degradation message: CPU (always available), CUDA/ROCm/Metal/MLX GPU backends, ASR (whisper.cpp)
and TTS (piper). None is mandatory: a missing GPU backend falls back to CPU, and missing ASR/TTS
leaves text input and the rest of the application fully usable. The template marks all accelerator
backends unavailable (not measured/not bundled); only the declarations and degradation paths are
implemented, not GPU/ASR/TTS acceptance.

### macOS Universal 2 decision

Decision: `universal2.supported = false`, `decision = separate-per-arch`. Standalone Python runtimes
(python-build-standalone and similar) are normally distributed per architecture; a Universal 2
payload would need measured universal binaries for the interpreter, extension modules and every
native dependency. No such measured artifacts exist for this beta, so no universal claim is made;
separate `macos-x86_64` and `macos-arm64` runtimes are declared and provisioned. A future universal
artifact is only allowed by the schema if it is measured and shared by both macOS targets.

### Release-runner: acquire and measure the six native runtimes (stage 6e)

The six-target runtime manifest starts as a template with **no measured artifacts**. The acquisition
tool closes that gap without inventing hashes:

- `installer/runtime_sources.json` is the declarative source schema: exactly six targets
  (`windows-x86_64`, `windows-arm64`, `linux-x86_64`, `linux-aarch64`, `macos-x86_64`,
  `macos-arm64`), each with `provider`, `provider_url`, `version`, `archive_kind`,
  `url` (or `url_template` with `{version}`/`{target}`), `filename`, and
  `expected_sha256`/`expected_size` that **must stay empty until a real archive has been
  measured**. The shipped file is a template: URLs are documented placeholders and all expected
  hashes are empty.
- `scripts/fetch_native_runtimes.py` is the measurement tool. The default is a **plan**
  (`--dry-run` semantics): it validates the sources and prints the plan without any network
  request, file write or directory creation.
  - `--offline-dir DIR` measures archives already downloaded by a release runner/human (no network);
  - `--download` streams from the source URLs with a hard byte bound and timeout via an injectable
    opener (tests use fakes and a loopback HTTP server only);
  - every archive is format-checked against the target's pinned archive kind, its members are
    content-checked, and a **Windows runtime artifact is rejected for non-Windows targets**
    (and vice versa) - the Windows embedded runtime is never reused off Windows;
  - optional expected sha256/size values are verified when present; a mismatch is a hard refusal;
  - `--write` emits a **NEW** measured runtime-manifest draft plus an evidence report under
    `.workspace/build/native-runtimes/`. `installer/runtime_manifest.json` is never overwritten
    unless `--force` is passed explicitly; existing outputs are also refused without `--force`;
  - the draft is `release_ready: true` **only when all six targets are measured**; a partial
    measurement stays `release_ready: false` with explicit empty `sha256`/`size` placeholders
    and `measured: false` for the missing targets (the schema validator is run before writing);
  - the tool never uploads/pushes/publishes, never runs models, never executes the downloaded
    archives and never deletes user files.

~~~powershell
# 1. Plan from the declarative sources (default: no network, no writes).
python scripts/fetch_native_runtimes.py
python scripts/fetch_native_runtimes.py --json

# 2. Release runner: download + measure all six (bounded, explicit network step).
python scripts/fetch_native_runtimes.py --download --json

# 2b. Alternative: measure archives already downloaded/verified by a human.
python scripts/fetch_native_runtimes.py --offline-dir C:/build/native-runtimes --write

# 3. The new draft is a normal runtime manifest: validate it with the provisioner (plan only).
python installer/bootstrap.py provision plan --runtime-manifest ".workspace/build/native-runtimes/runtime-manifest.measured.json"

# 4. Feed measured archives to the release builder (repeatable per target).
python scripts/build_release.py --runtime-archive windows-x86_64=C:/build/python-3.12.10-windows-x86_64.zip
~~~

**CI vs MANUAL-PENDING:** acquisition/measurement is a release-runner or human step. CI never
downloads real runtimes and a green CI matrix is not platform support. Measured hashes are
reproducibility evidence only; clean-machine installation, GUI interaction, real hardware
(microphone/ASR/TTS, GPU, clipboard) and every non-Windows target stay **MANUAL-PENDING** until a
tester records them (see `docs/PLATFORM_COMPATIBILITY_MATRIX.md`, `docs/BETA_TESTING.md`).

### Commands

```powershell
# Plan the native runtime for this host (default dry-run).
python installer/bootstrap.py provision plan --runtime-manifest installer/runtime_manifest.json

# Inspect another target explicitly (no install unless run on that native host).
python installer/bootstrap.py provision plan --runtime-manifest installer/runtime_manifest.json --platform linux-aarch64

# Install/verify/update/repair from measured artifacts (offline bundle = local artifacts only).
python installer/bootstrap.py provision install --runtime-manifest release/runtime-manifest.json --target C:/Apps/NL/runtime --offline-bundle .workspace/build/release-candidate
python installer/bootstrap.py provision verify --target C:/Apps/NL/runtime
python installer/bootstrap.py provision repair --runtime-manifest release/runtime-manifest.json --target C:/Apps/NL/runtime

# Build a release candidate; measured native runtimes are pinned per target.
python scripts/build_release.py --plan --json
python scripts/build_release.py --runtime-archive windows-x86_64=C:/build/python-win64.zip --runtime-archive linux-x86_64=C:/build/python-linux.tar.gz
```

## 8. Tests (targeted; no network)

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_bootstrap_installer.py tests/test_build_release.py tests/test_fetch_native_runtimes.py -p no:cacheprovider
```

Result: **90 passed** in this environment (32 acquisition/measurement tooling tests from
`tests/test_fetch_native_runtimes.py`; the bootstrapper/provisioner and release-builder files
contribute the remaining 58). The acquisition tests use fake local archives, an injected opener and
one loopback HTTP server only: no external network, no model runs. Coverage:

- manifest validation (template, schema errors, unsafe destinations, missing hashes, unknown platforms);
- plan writes nothing; install into empty target; shared cache + isolated second install; template/non-empty/root target refusals; hash and size mismatch leave no partial install; corrupt cache re-fetch;
- verify detects modified/missing files with exit code 3; repair restores and keeps a backup; update to new version keeps previous backup; same-version up-to-date; downgrade refused;
- urllib fetcher success/atomic hash-mismatch cleanup/non-HTTP refusal; offline bundle path traversal refusal;
- cache list/verify/prune/clear and confirmation requirements;
- CLI flow (install/plan/verify) and exit codes; no writes outside cache/target; static checks for stdlib-only/no global tooling;
- release reproducibility (byte-identical two builds), manifest completeness/hashes/exclusions, platform-manifest validation + offline install integration, source-only zip excludes `python/`/`crewAI/`, version parsing, optional runtime archive bundling, CLI plan/build/refusal, no destructive operations.
- cross-platform: six-target runtime manifest validation, selection per OS/arch, unsupported-host/target refusals with guidance, Windows-artifact rejection on Linux/macOS, measured-only hashes/release_ready gating, offline installs for all six targets with fake archives, cache isolation, hash-mismatch atomic failure, repair/update, macOS separate per-arch runtimes, optional component degradation.
- acquisition/measurement (stage 6e): sources-schema validation (six targets, archive-kind/URL/format and measured-only expected-hash rules, credential refusal), default dry-run opens no network and writes nothing, offline archive hashing (zip/tar.gz), expected-hash/size refusal, archive-format and OS-content refusals (Windows runtime never accepted off Windows), measured draft generation with ` + '`release_ready`' + ` gating for partial measurements, template-overwrite refusal, existing-output/` + '`--force`' + ` handling, download bounds/timeouts via injected opener, evidence report URL redaction, target aliases/refusals, and static no-publish/no-network-default guards.

---

## 9. Known limitations / manual-pending

1. **Clean Windows acceptance is manual-pending**: this environment has the development workspace and embedded runtime; a fresh Windows install without Python, with real downloads and GUI/agent execution, must be validated by a human on a clean VM/machine.
2. **No real published artifacts**: the template base URLs are examples; a release pipeline must produce, sign and host the component archives from a trusted channel.
3. **No code signing / SmartScreen reputation**; no MSI/uninstaller, no Start-menu/OS integration, no automatic update check - this is a foundation, not the final installer.
4. **No production runtime bundle**: `python/` and `crewAI/` are deliberately never copied by the builder; runtime archives must come from the separate clean-runtime build pipeline (stage 6b) and be supplied with `--runtime-archive TARGET=PATH` (repeatable; legacy `--with-runtime-archive` still accepted).
5. **User data migration**: the bootstrapper installs program files only; it does not move existing `data/`, does not set `NL_DATA_DIR` in launchers and does not migrate a development database (tracked from PORTABLE_BUILD next steps).
6. **Licensing/notices**: third-party notices and license texts are not yet generated into the payload (stage 6b).
7. **Trust root**: manifests are not signed; sha256 verification protects against corrupt/mismatched downloads, not a malicious manifest.
8. **GUI/agent acceptance from the installed payload** (GUI startup, project open, model detection, mission execution) was not executed in this task; the local smoke covers plan/install/verify integrity only.
9. Linux/macOS behaviour is schema-level only; no cross-platform acceptance.
10. Update/repair keep backup directories by design (no automatic cleanup); cache has no automatic size cap.
11. **Cross-platform beta runtimes are not measured yet**: `installer/runtime_manifest.json` and `installer/runtime_sources.json` are templates with empty sha256/size placeholders for all six targets, and no real standalone Python archive has been downloaded/measured on this machine. The stage-6e tooling (`scripts/fetch_native_runtimes.py`) now provides the release-runner path: it validates sources, performs bounded download or offline measurement, rejects format/OS mismatches and writes a new draft manifest with `release_ready` true only at 6/6 measured. Running it for real remains a release-runner/human step with external URLs; the provisioner/CI tests use local fake zip/tar.gz artifacts only.
12. **No clean/hardware acceptance for the six targets**: Windows ARM64, Linux x86_64/ARM64 and macOS Intel/Apple Silicon hosts, GPU backends (CUDA/ROCm/Metal/MLX), ASR/TTS hardware and real latency remain manual-pending; only CPU fallback/degradation declarations are implemented.
13. **macOS Universal 2 is deliberately not claimed** (separate per-arch runtimes); no code signing/notarization, Linux distro/glibc matrix, Windows ARM64 toolchain or CI cross-build was validated.
14. Runtime dependency pins (crewai==1.15.32, PySide6==6.12.0, psutil==7.2.2, Python 3.12.10) are the development-runtime pins; per-target native build/verification of those pins is a beta-pipeline task, not measured here.

---

## 10. Next steps (stage 6b/6c)

1. Build a clean, reproducible Windows runtime archive (separate from the development `python/`) and publish it as a signed component.
2. Publish/sign release manifests and archives; add manifest signature verification.
3. Add launcher wiring for `NL_DATA_DIR` and a documented user-data migration policy.
4. Implement uninstall/repair UX, backup retention/cleanup, and cache size caps.
5. Add license/third-party notices to the payload.
6. Run clean-Windows acceptance: install from the network, GUI startup, project open, Ollama discovery, agent execution, persistence, restart recovery, update/repair/rollback.
7. Linux/macOS runtime and acceptance.
8. Produce and measure all six native runtime archives on a release runner: populate the real URLs in `installer/runtime_sources.json`, run `python scripts/fetch_native_runtimes.py --download --write`, review the new `.workspace/build/native-runtimes/` draft + evidence report, then feed the measured archives to `scripts/build_release.py` (or copy the measured manifest into a release candidate). Then run clean-host acceptance and GPU/ASR/TTS degradation checks; measurement alone is not platform support.

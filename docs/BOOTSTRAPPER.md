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
| Tests | `tests/test_bootstrap_installer.py`, `tests/test_build_release.py` | 40 targeted tests, fake/local artifacts only, no network |

Everything is standard library only (Python >= 3.10): no global Python/pip/uv/conda, no second environment, no third-party package, no admin/elevation.

---

## 2. Measured local evidence (2026-10-28)

| Step | Command | Result |
|---|---|---|
| Build candidate | `python scripts/build_release.py --name stage6a-source-candidate --json` | `dist/stage6a-source-candidate`: 255 tracked files, 3,625,705 B input; zip 1,053,218 B sha256 `55ea86742a8af56267cbc51366f2187292cc43771762348ade535695893eaa06` |
| Reproducibility | two builds into `build/phase6a/repro-a` and `build/phase6a/repro-b` | identical candidate name, identical file set, **byte-identical** `release-manifest.json`, `platform-manifest.json` and source zip (same sha256) |
| Offline plan | `python installer/bootstrap.py plan --offline-bundle dist/stage6a-source-candidate --target build/phase6a/install-test --cache build/phase6a/cache --json` | `installable: true`, 1,053,218 B to fetch, cache misses 0 -> 1, no writes |
| Offline install | same with `install` | `status: installed`, 255 files / 3,625,705 B, 1 artifact into shared cache |
| Verify | `python installer/bootstrap.py verify --target build/phase6a/install-test --json` | `status: verified`, `ok: true`, 255/255 files, 3,625,705 B checked, 0 missing/modified |
| Cache | `python installer/bootstrap.py cache list --cache build/phase6a/cache --json` | 1 content-addressed entry, 1,053,218 B |

The existing stale `dist/portable-release` was not touched: the new source-only candidate (`dist/stage6a-source-candidate`, zip 1,053,218 B + manifests) is a separate, newly created directory (the builder refuses to overwrite any existing candidate), and `python/` and `crewAI/` were not copied. That candidate and the `build/phase6a/` smoke workspace are retained as measured stage-6a evidence for Lead review only; they are not a verified full release (no runtime bundle), and removing/replacing or promoting them is a Lead decision under the repository structure policy (at most one verified release candidate under `dist/`).

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
python installer/bootstrap.py install --target C:/Users/me/Apps/NL-Coding-Agent --offline-bundle dist/stage6a-source-candidate --cache C:/temp/nl-cache

# Update/repair/verify an existing managed installation.
python installer/bootstrap.py update --target C:/Users/me/Apps/NL-Coding-Agent --manifest C:/releases/0.3.0/platform-manifest.json
python installer/bootstrap.py repair --target C:/Users/me/Apps/NL-Coding-Agent --offline-bundle dist/stage6a-source-candidate
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

# Build a new candidate under dist/ (refuses to overwrite an existing directory).
python scripts/build_release.py --json

# Two builds from the same inputs are byte-identical (same zip and manifests).
python scripts/build_release.py --output-parent build/phase6a/repro-a --json
python scripts/build_release.py --output-parent build/phase6a/repro-b --json

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

Default exclusions: `.git`, `data/`, `logs/`, `dist/`, `build/`, `python/`, `crewAI/`, `crewAI-tools/`, `PATCH/`, `.agents/`, caches (`__pycache__` etc.), bytecode, SQLite/log files, `config/voicebridge.yaml`, `.env`, `SHA256_MANIFEST.json`, `temp_*.py` and `*.patch` artifacts. The builder writes only a NEW candidate directory (default parent `<source>/dist`), refuses existing paths and never deletes, moves or rewrites anything - including the existing stale `dist/portable-release` (removal/replacement requires explicit authorization).

---

## 7. Platform matrix

| Platform | Manifest support | Runtime bundle | Status |
|---|---|---|---|
| windows-x86_64 | schema + template + build_release output | optional external prebuilt zip (`--with-runtime-archive`) | source-only install tested locally; production runtime/manual acceptance pending |
| linux-x86_64 | template + build_release platform entry | optional external prebuilt zip | schema only; no acceptance yet |
| macos-x86_64 / macos-arm64 | platform keys accepted by schema | none | schema only |
| windows-arm64 / linux-aarch64 | platform keys accepted by schema | none | schema only |

---

## 8. Tests (targeted; no network)

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_bootstrap_installer.py tests/test_build_release.py -p no:cacheprovider
```

Result: **40 passed**. Coverage:

- manifest validation (template, schema errors, unsafe destinations, missing hashes, unknown platforms);
- plan writes nothing; install into empty target; shared cache + isolated second install; template/non-empty/root target refusals; hash and size mismatch leave no partial install; corrupt cache re-fetch;
- verify detects modified/missing files with exit code 3; repair restores and keeps a backup; update to new version keeps previous backup; same-version up-to-date; downgrade refused;
- urllib fetcher success/atomic hash-mismatch cleanup/non-HTTP refusal; offline bundle path traversal refusal;
- cache list/verify/prune/clear and confirmation requirements;
- CLI flow (install/plan/verify) and exit codes; no writes outside cache/target; static checks for stdlib-only/no global tooling;
- release reproducibility (byte-identical two builds), manifest completeness/hashes/exclusions, platform-manifest validation + offline install integration, source-only zip excludes `python/`/`crewAI/`, version parsing, optional runtime archive bundling, CLI plan/build/refusal, no destructive operations.

---

## 9. Known limitations / manual-pending

1. **Clean Windows acceptance is manual-pending**: this environment has the development workspace and embedded runtime; a fresh Windows install without Python, with real downloads and GUI/agent execution, must be validated by a human on a clean VM/machine.
2. **No real published artifacts**: the template base URLs are examples; a release pipeline must produce, sign and host the component archives from a trusted channel.
3. **No code signing / SmartScreen reputation**; no MSI/uninstaller, no Start-menu/OS integration, no automatic update check - this is a foundation, not the final installer.
4. **No production runtime bundle**: `python/` and `crewAI/` are deliberately never copied by the builder; runtime archives must come from the separate clean-runtime build pipeline (stage 6b) and be supplied with `--with-runtime-archive`.
5. **User data migration**: the bootstrapper installs program files only; it does not move existing `data/`, does not set `NL_DATA_DIR` in launchers and does not migrate a development database (tracked from PORTABLE_BUILD next steps).
6. **Licensing/notices**: third-party notices and license texts are not yet generated into the payload (stage 6b).
7. **Trust root**: manifests are not signed; sha256 verification protects against corrupt/mismatched downloads, not a malicious manifest.
8. **GUI/agent acceptance from the installed payload** (GUI startup, project open, model detection, mission execution) was not executed in this task; the local smoke covers plan/install/verify integrity only.
9. Linux/macOS behaviour is schema-level only; no cross-platform acceptance.
10. Update/repair keep backup directories by design (no automatic cleanup); cache has no automatic size cap.

---

## 10. Next steps (stage 6b/6c)

1. Build a clean, reproducible Windows runtime archive (separate from the development `python/`) and publish it as a signed component.
2. Publish/sign release manifests and archives; add manifest signature verification.
3. Add launcher wiring for `NL_DATA_DIR` and a documented user-data migration policy.
4. Implement uninstall/repair UX, backup retention/cleanup, and cache size caps.
5. Add license/third-party notices to the payload.
6. Run clean-Windows acceptance: install from the network, GUI startup, project open, Ollama discovery, agent execution, persistence, restart recovery, update/repair/rollback.
7. Linux/macOS runtime and acceptance.

# Private Beta Packages (Stage 6c)

**Task:** shared `task-49` (NL-BP-159 and the artifact part of NL-BP-165).
**Status:** builder implemented and tested; one deterministic beta package built from the
existing stage-6a source candidate as local evidence. Native six-target runtimes remain
**MANUAL-PENDING / unmeasured** - the beta package does not contain or fabricate them.

## 1. Purpose

`scripts/build_beta_packages.py` turns a measured **source release candidate** produced by
`scripts/build_release.py` into a deterministic, self-describing **private-beta package**
that a non-developer evaluator can verify and report on. It is packaging and evidence, not a
signer, not an installer, not a runtime downloader and not a publisher.

It deliberately reuses existing contracts:

- candidate contract: `release-manifest.json` + source zip from `scripts/build_release.py`;
- installer schemas: `installer/platform_manifest.py` and `installer/runtime_manifest.py`;
- platform matrix and pinned identifiers: `installer/platform_targets.py` (via the release builder);
- no duplicate build logic: the builder imports `scripts.build_release` for version reading,
  six-target maps, platform-manifest and runtime-manifest generation.

## 2. Input: source release candidate

A candidate directory must contain:

| File | Requirement |
|---|---|
| `release-manifest.json` | build_release schema; product.version must equal `nl_coding_agent/core/version.py` APP_VERSION in `--source`; source.git_head must be a valid hex head; archive block with name/format/sha256/size/file_count |
| `<archive>.zip` | must match declared sha256/size; readable zip; no absolute/traversal members; no `python/`, `crewAI/`, `data/`, `logs/`, `.workspace/`, `dist/`, `build/`, `.git/`, `da_eliminare/` or user/cache file members |

Use `--candidate PATH` explicitly, or omit it to discover the newest candidate under
`.workspace/dist` (then legacy `dist`). If no candidate exists, run
`scripts/build_release.py` first.

## 3. Output layout

A NEW directory `.workspace/dist/beta-<version>/` (override with `--output-parent` /
`--name`; an existing path is always refused and left untouched):

```text
beta-<version>/
  SHA256SUMS                       sha256 for every payload file except SHA256SUMS
  beta-manifest.json               versioned package manifest and inventory
  VERSION                          APP_VERSION
  BETA_README.md                   short beta readme (version, git head, pending items)
  INSTALL.md                       universal non-developer instructions and checksum commands
  install/INSTALL-<target>.md      per-platform instructions (six files)
  installer/platform-manifest.json installer template: real source-zip hash, empty runtime hashes
  installer/runtime-manifest.json  six-target runtime template: all runtimes unmeasured
  source/<candidate-archive>.zip   copied measured source release zip
```

No runtime, vendor checkout, user data, logs, workspace content, build output or timestamp is
included. Only the candidate source zip plus generated text/JSON files are packaged.

## 4. Usage

```powershell
# Build from the newest source candidate under .workspace/dist (or use --candidate).
python\python.exe scripts\build_beta_packages.py --plan --json
python\python.exe scripts\build_beta_packages.py --candidate .workspace\dist\release-candidate-... --json

# Explicit output parent/name (must not exist yet).
python\python.exe scripts\build_beta_packages.py --candidate .workspace\dist\release-candidate-... --output-parent .workspace\dist --name beta-0.2.0 --json
```

Exit codes: `0` success/plan; `2` usage, candidate, integrity, version or overwrite error.

## 5. `beta-manifest.json`

The manifest is versioned and deterministic (sorted keys, no timestamps or absolute paths):

- `package_format`: `nl-coding-agent-beta-package`; `schema_version`: 1; channel beta;
- `product`: id/name/version (version from `nl_coding_agent/core/version.py`);
- `source`: git head, short head, tracked hash, candidate manifest reference, copied archive
  identity (relative name, sha256, size, file_count, zip format);
- `payload`: package inventory with path/sha256/size, total size, explicit exclusion list
  (`beta-manifest.json` and `SHA256SUMS` cannot hash themselves);
- `checksums`: SHA256SUMS algorithm/file/coverage statement;
- `platforms`: six OS/arch entries with display name, launcher, runtime component id,
  archive kind, runtime object explicitly `measured: false, sha256: "", size: 0,
  status: "unmeasured", release_ready: false`, per-target CI flags and MANUAL-PENDING items;
- `universal2`: `supported: false, decision: separate-per-arch` (no unverified universal claim);
- `validation`: CI flags, global MANUAL-PENDING list, `release_ready: false`,
  `runtime_components_measured: false`;
- `installers`: platform/runtime manifest paths and the install-doc list;
- `notes`: determinism, no-bundled-runtime and no-fabricated-hash statements.

## 6. Checksums and installer templates

`SHA256SUMS` lists `<sha256>  <relative-path>` for every payload file except itself, sorted by
path, so standard tools verify it directly:

```powershell
Get-FileHash -Algorithm SHA256 -Path .\SHA256SUMS   # Windows
sha256sum -c SHA256SUMS                             # Linux
shasum -a 256 -c SHA256SUMS                         # macOS
```

`installer/platform-manifest.json` is a valid installer-schema **template**:
`release_ready: false`, six platform entries, an `app-source` component with the real measured
source-zip sha256/size and relative `source/<archive>` URL, and six optional runtime
components with `sha256: ""` / `size: 0` placeholders. `installer/runtime-manifest.json` is the
six-target runtime/dependency template generated by `scripts/build_release.py` with every
runtime unmeasured and the Universal 2 decision recorded. Both files validate against the
installer schemas; neither fabricates a hash.

## 7. Generated install documentation

`INSTALL.md` (universal) and `install/INSTALL-<target>.md` (six platform files) are generated
for non-developers and contain:

- package contents and the MANUAL-PENDING nature of the source beta;
- checksum commands: PowerShell `Get-FileHash`, Linux `sha256sum -c`, macOS
  `shasum -a 256 -c` (per-platform docs use the matching command);
- extraction commands (`Expand-Archive` on Windows; `python3 -m zipfile -e` on Linux/macOS);
- first-run validation steps (version, checksum, extraction, recording OS/arch/output);
- what to report and where (private beta owner/channel; no public uploads of source, data,
  credentials or model files);
- explicit MANUAL-PENDING warnings: unmeasured runtimes, clean-host acceptance, GPU/ASR/TTS
  hardware, signing/download channel, Universal 2 not claimed.

## 8. Determinism and safety guarantees

- Identical candidate + source version => byte-identical package (fixed file names, sorted
  SHA256SUMS/inventory order, `json.dumps(sort_keys=True)`, no timestamps, no absolute paths,
  no environment data, no random identifiers in output content).
- Writes only the NEW package directory; a concurrent existing path is refused after staging;
  the temporary staging directory is removed on failure.
- No network, model, upload or publish code path exists; the builder never invokes the
  application, the installer, Ollama or any download.
- Never bundles runtimes, vendor checkouts, user data, logs or workspace/build content; the
  source zip is validated for forbidden members and archive integrity before copying.
- The source zip is verified against the candidate manifest (size, sha256, file count) and
  against zip-slip/absolute-path rules.

## 9. Measured evidence (local)

- Real build from `.workspace/dist/stage6a-source-candidate` (APP_VERSION 0.2.0, git head
  4787c30): package `.workspace/dist/beta-0.2.0`, 14 files / 1,097,875 bytes,
  `SHA256SUMS` with 13 entries, all checksums verified, six platform entries with runtime
  components unmeasured and `release_ready: false`, both installer templates validate,
  0 absolute-path hits in generated text files.
- A second build into a managed parent was byte-identical (14/14 files, same hashes).
- Targeted tests: `tests/test_build_beta_packages.py` - 11 passed, fake local candidates
  only, no network. Coverage: deterministic rebuild, SHA256SUMS and inventory correctness,
  six-target/unmeasured honesty, install-doc content, overwrite refusal, version/hash mismatch
  and runtime/user-data rejection, no absolute paths/timestamps, static no-network/no-publish
  guards, plan/CLI and candidate discovery.

## 10. Manual-pending items (not claimed by this task)

1. Native standalone runtimes for the six OS/arch targets are not built/measured; the beta
   package intentionally contains no runtimes and no fabricated hashes.
2. Clean-host acceptance on Windows ARM64, Linux x86_64/ARM64 and macOS Intel/Apple Silicon.
3. GPU backends (CUDA/ROCm/Metal/MLX), ASR/TTS hardware and real multimodal latency.
4. Code signing/notarization, a signed/published download channel and release approval.
5. Full pytest baseline and reviewer sign-off (Lead-run); this task ran targeted tests only.

## 11. Related documents

- `docs/BOOTSTRAPPER.md` - bootstrapper, six-target provisioner, runtime manifests.
- `docs/RELEASE_ACCEPTANCE.md` - stage-6b portable candidate acceptance evidence.
- `scripts/build_release.py` - source release candidate contract consumed here.

# Cross-Platform Compatibility Matrix - NL Coding Agent private beta (C1)

**Status:** evidence-based audit, platform support abstraction and the C2-C5 cross-platform foundations are implemented, committed and re-synced (C1b). No cross-platform support is claimed: every non-Windows target remains **MANUAL-PENDING** until a measured native runtime is published, a real build/run exists and real-machine acceptance is recorded.
**Requirement IDs:** NL-BP-152 (audit + matrix), NL-BP-153 (platform abstraction), NL-BP-160 (matrix documentation); cross-referenced follow-ups NL-BP-154/155/156/157/158/161/162/163/164/165; program `docs/CROSS_PLATFORM_PRIVATE_BETA_PROGRAM.md`.
**Audit snapshot (this re-sync):** 2026-10-28 19:26 Europe/Rome, git HEAD `4089616`, working tree clean, **333 tracked files**. Previous snapshot was `29a0ca1`; since then C2 (six-target runtime manifests + provisioner), C3 (CI matrix), C4 (beta workflow/diagnostics), C5 (pre-upload secrets audit) and ROOT REORG Phase A landed. All file:line references below were re-verified at `4089616`. While this re-sync was being written the HEAD advanced to `68fe22a` (a docs-only commit that records the C1-C5 evidence in `docs/CURRENT_STATE.md`, `docs/PRODUCT_BACKLOG.md`, `docs/RELEASE_ACCEPTANCE.md` and `docs/product-blueprint/INDEX.json`); no code/installer/CI file changed in that commit, so this document's evidence remains valid at HEAD `68fe22a`.
**Method:** read-only static audit of the tracked repository + read-only probes of the local Windows runtime (`python\python.exe`) + review of the committed CI/beta/secrets evidence. No network calls, no model runs, no self-build, no installer execution, no hardware runs. Hardware/desktop behaviour is never claimed.

---

## 1. Verdict summary

| Question | Answer (evidence-based) |
|---|---|
| Is the application code forked per OS? | **No.** One `nl_coding_agent` package (90 tracked Python modules incl. the platform support layer); platform differences are declarations/probes plus the Windows-first assumptions listed in section 5. |
| Is any non-Windows target verified? | **No.** There is no Linux/macOS runtime artifact, shipped launcher, package or run evidence. All five non-Windows targets are MANUAL-PENDING (section 10.2 explains why a committed CI workflow definition does not change this). |
| Is Windows x86_64 a beta candidate? | **PARTIAL.** A Windows portable candidate exists (stage-6b) and local tests pass; clean-machine and real-desktop/hardware acceptance remain MANUAL-PENDING (see `docs/BOOTSTRAPPER.md`, `docs/CURRENT_STATE.md`, `docs/RELEASE_ACCEPTANCE.md`). |
| Are the six native runtime manifests/provisioner implemented? | **PARTIAL.** `installer/platform_targets.py` + `installer/runtime_manifest.*` + `installer/provision.py` implement all six targets with measured-only hashes, strict no-Windows-runtime-reuse guards, macOS separate-per-arch decision and optional CPU/GPU/ASR/TTS declarations. The shipped manifest is a `release_ready=false` template: no measured runtime archive exists (section 10.1). |
| Is a CI matrix implemented? | **Workflow definition committed, not executed here.** `.github/workflows/ci.yml` defines six runner jobs (ARM64 jobs experimental/non-blocking) documented in `docs/CI.md`. No GitHub run evidence exists in this repository state, so no matrix cell is upgraded (section 10.2). |
| Are CUDA/ROCm/Metal/MLX required? | **No.** GPU probing is optional and NVIDIA-only; unknown/unavailable is reported, never fatal. `platform_support.probe_gpu` enforces `cuda_required=False`, `rocm_required=False`, `metal_required=False`, `mlx_required=False` and `forced=False`; the runtime manifest declares all accelerator components optional with CPU fallback. |
| Are native wheels/runtime archives for all six targets present? | **No.** Only the Windows x86_64 development runtime exists locally (`win_amd64` wheels, section 6). The six-target runtime manifest declares pinned ids/versions/URLs but every runtime is unmeasured (`sha256=""`, `size=0`, `release_ready=false`). |
| Is the beta workflow and pre-upload audit documented? | **Yes, as tooling/process, not acceptance.** `docs/BETA_TESTING.md`, `docs/PRIVATE_BETA_RUNBOOK.md`, `.github/ISSUE_TEMPLATE/` and the redacted diagnostic report exist. The C5 secrets snapshot is **CLEAR-WITH-REVIEW** (0 blocking, 52 review items) and must be re-run at the current HEAD before any upload; owner authorization remains mandatory (section 10.4). |

---

## 2. Audit method and evidence basis

### 2.1 Repository facts (snapshot)

- `git rev-parse HEAD` = `4089616`; tracked files = **333**; `nl_coding_agent` Python modules = **90** (incl. `core/platform_support.py`); `installer` Python modules = 8 (incl. `platform_targets, runtime_manifest, provision`); `scripts` Python modules = 17 (incl. `scripts/ci/`); `tests` Python files = 68; launchers = **1 root GUI launcher** (`NL Coding Agent.bat`) + **5 under `scripts/launchers/`** (3 CLI launchers that are remapped to the portable payload root, 2 development-only VoiceBridge launchers); the four dated repair scripts are archived under `docs/history/legacy/temp-scripts/`; `da_eliminare/` is the review-only staging area (only its README is tracked; contents are git-ignored, never shipped).
- Workstreams since the previous snapshot: C2 (`installer/platform_targets.py`, `installer/runtime_manifest.py + installer/runtime_manifest.json`, `installer/provision.py`, release builder), C3 (`.github/workflows/ci.yml`, `scripts/ci/*`, `docs/CI.md`), C4 (`docs/BETA_TESTING.md`, `docs/PRIVATE_BETA_RUNBOOK.md`, `.github/ISSUE_TEMPLATE/*`, diagnostic report), C5 (`scripts/audit_release_secrets.py`, `docs/SECRETS_AUDIT.md`). This document is the only file edited by C1b; no code/CI/installer file was modified.

### 2.2 This machine (Windows x86_64 only)

| Probe | Measured value | Relevance |
|---|---|---|
| OS/CPU | Windows 11 `10.0.26300`, `AMD64` | only locally available target |
| Python | CPython 3.12.10, MSC v.1943 64-bit (AMD64), `python\python.exe`, `python312._pth` isolated layout | Windows embedded runtime; cannot be reused on Linux/macOS (program constraint #2) |
| SQLite | `sqlite3` 3.49.1 (DLL-backed `python/sqlite3.dll`) | portable at code level; native library is Windows |
| PySide6 / Qt | PySide6 6.12.0, Qt 6.12.0 | GUI toolkit is cross-platform, but the installed wheel/plugins are Windows-only |
| Qt plugins present | `plugins/platforms`: qdirect2d, qminimal, qoffscreen, qwindows; `plugins/multimedia`: ffmpegmediaplugin, windowsmediaplugin; `plugins/imageformats`: qgif/qjpeg/qsvg/... | Windows platform/multimedia plugins only: no Linux/macOS display or audio plugins shipped |
| PATH tools | git, ollama, ffmpeg/ffprobe, node, uv, curl **present**; piper, pylsp, pyright-langserver, basedpyright-langserver, clangd, typescript-language-server, gopls, debugpy **missing** | corroborates the feature matrix rows (terminal/git/LSP/MCP/GPU/ASR/TTS) |
| Optional Python libs | onnxruntime, tokenizers, pydantic_core, tiktoken, aiohttp, chromadb, lancedb, PIL, pdfplumber, openpyxl **present**; sounddevice, faster-whisper, vosk, piper, debugpy, python-docx, python-pptx **missing** | attachments/ASR/TTS/debug rows; optional backends fail closed |
| CUDA/ROCm | `nvidia-smi` path is probed only by the GUI status bar; no ROCm/Metal/MLX probing exists | GPU row; no accelerator requirement anywhere |

### 2.3 Evidence commands used (read-only)

~~~powershell
# Run from the repository root (paths below are repository-relative on purpose)
git ls-files                                            # 333 tracked files at this re-sync
git status --porcelain                                  # clean at snapshot
python\python.exe -c "import platform, sys, sqlite3; print(platform.platform(), sys.version)"
python\python.exe -m pytest tests/test_platform_support.py -q -p no:cacheprovider   # 31 passed
python\python.exe -m pytest tests/test_bootstrap_installer.py tests/test_build_release.py -q -p no:cacheprovider
python\python.exe -m pytest tests/test_ci_workflows.py tests/test_release_secrets_audit.py -q -p no:cacheprovider
python\python.exe scripts\audit_release_secrets.py --json-out build/phase6/secrets_audit.json --markdown-out docs\SECRETS_AUDIT.md
# read-only review: docs/CI.md, .github/workflows/ci.yml, installer/runtime_manifest.{json,py},
# installer/platform_targets.py, installer/provision.py, docs/BETA_TESTING.md,
# docs/PRIVATE_BETA_RUNBOOK.md, docs/BOOTSTRAPPER.md section 7, docs/RELEASE_ACCEPTANCE.md
# platform-assumption greps: sys.platform / os.name / ctypes / windll / DETACHED_PROCESS /
# CREATE_NEW_PROCESS_GROUP / .bat / .exe / shell=True / APPDATA / SystemDrive / which / nvidia
~~~

Automated evidence re-run by this re-sync: `tests/test_platform_support.py` (31 tests, injected fakes; no hardware/network) -> **31 passed**. Cross-workstream evidence reviewed (not re-executed here, no GitHub/CI/network): `docs/CI.md`, `.github/workflows/ci.yml`, `installer/runtime_manifest.json` + provisioner sources, `docs/BETA_TESTING.md`, `docs/PRIVATE_BETA_RUNBOOK.md`, `docs/SECRETS_AUDIT.md`, `docs/BOOTSTRAPPER.md` section 7, `docs/RELEASE_ACCEPTANCE.md` cross-platform rows. Matrix-reference validation is recorded in section 10.6.

---

## 3. Target matrix - six OS/arch targets

Legend for sections 4/5: **V** = verified by automated evidence recorded in this repository environment (today only Windows x86_64); **P** = partial (code path exists, only partly verifiable/optional component missing); **MP** = MANUAL-PENDING (shared code exists, but no build/run/real-machine evidence: support is not claimed); **U** = unsupported/known blocker.

| Target id | OS / CPU | Local runtime present | Launcher layout at this HEAD | Native runtime manifest (`installer/runtime_manifest.json`) | Code status | Beta status |
|---|---|---|---|---|---|---|
| `windows-x86_64` | Windows 11 x64 | **yes** - developer embedded runtime in `python/` (dev only, never shipped as source) | root GUI `NL Coding Agent.bat`; CLI launchers in `scripts/launchers/` remapped to payload root | template: runtime id/version/URL declared, `measured=false` (`sha256=""`, `size=0`) | shared code; Windows-first assumptions audited in section 5 | **PARTIAL**: local tests + portable candidate r2; clean-machine and real-desktop acceptance MANUAL-PENDING |
| `windows-arm64` | Windows 11 ARM64 | no | same Windows `.bat` layout (cmd.exe exists on Windows ARM64) | template: declared, unmeasured | shared code; no ARM64 runtime/wheels evidenced (chromadb/lancedb/onnxruntime win_arm64 absent here) | **MANUAL-PENDING**; native wheel/runtime availability is the likely blocker |
| `linux-x86_64` | Linux x86_64 | no | per-target launcher name declared `NL Coding Agent.sh` (`installer/platform_targets.py:60`); not shipped | template: declared, unmeasured (`tar.gz`) | shared code; POSIX assumptions unverified | **MANUAL-PENDING** |
| `linux-aarch64` | Linux ARM64 | no | declared `NL Coding Agent.sh` (`:71`); not shipped | template: declared, unmeasured | shared code; ARM64 wheel availability unverified | **MANUAL-PENDING** |
| `macos-x86_64` | macOS Intel | no | declared `NL Coding Agent.sh` (`:82`); not shipped | template: declared, unmeasured; Universal 2 **not claimed** (separate-per-arch decision) | shared code; macOS audio/clipboard/packaging/notarization unverified | **MANUAL-PENDING** |
| `macos-arm64` | macOS Apple Silicon | no | declared `NL Coding Agent.sh` (`:93`); not shipped | template: declared, unmeasured; separate-per-arch | shared code; signing/notarization and real-hardware checks unverified | **MANUAL-PENDING** |

Platform declarations are also machine-readable in `platform_support.platform_declarations()` (`PlatformDeclaration.status` = `local-verified-partial` for windows-x86_64, `manifest-schema-only` for the other five). **Declaration drift (documented, not edited here):** the module's `runtime_manifest`/`launcher` text still reflects the pre-C2 state ("none/manifest schema only", `.command`, "Universal 2 decision open"); the six-target runtime manifest and `installer/platform_targets.py` are authoritative in this document. A follow-up module declaration update is recommended (docs-only scope for C1b).

---

## 4. Feature matrix - GUI, editor, clipboard, attachments, microphone, ASR/TTS, Ollama, CrewAI, terminal, Git, LSP, MCP, GPU

Cell format: level + verification class. **CI** = automatable in a CI runner for that target (unit/offscreen/static); **HW** = requires real hardware/desktop/clean machine (MANUAL-PENDING regardless of CI). A CI **workflow definition** is now committed (`.github/workflows/ci.yml`) but it has **not been executed on GitHub** for this repository state; therefore no cell is upgraded and every non-Windows cell stays MP (`10.2).

| Feature | windows-x86_64 | windows-arm64 | linux-x86_64 | linux-aarch64 | macos-x86_64 | macos-arm64 | Verification class |
|---|---|---|---|---|---|---|---|
| GUI (Qt desktop shell) | **V (CI+HW)** | MP (HW) | MP (CI+HW) | MP (CI+HW) | MP (CI+HW) | MP (CI+HW) | offscreen Qt smoke is CI; real desktop/focus/DPI is MANUAL-PENDING |
| Editor (read-only view + guarded save) | **V (CI)** | MP (CI) | MP (CI) | MP (CI) | MP (CI) | MP (CI) | CI: widget tests; MANUAL-PENDING: real file dialogs |
| Clipboard (paste screenshot/files) | **P (HW)** | MP (HW) | MP (HW) | MP (HW) | MP (HW) | MP (HW) | real OS clipboard is MANUAL-PENDING; attachment-byte path is CI |
| Attachments (drag/drop, text/PDF/XLSX extraction) | **V (CI)** | MP (CI) | MP (CI) | MP (CI) | MP (CI) | MP (CI) | CI: extraction/tests; optional docx/pptx libs absent (fail closed) |
| Microphone (capture devices/recording) | **P (HW)** | MP (HW) | MP (HW) | MP (HW) | MP (HW) | MP (HW) | MANUAL-PENDING: real microphone + OS audio backend |
| ASR / TTS (local engines) | **P (CI+HW)** | MP (HW) | MP (CI+HW) | MP (CI+HW) | MP (CI+HW) | MP (CI+HW) | lifecycle CI with fakes; real engines/models/devices MANUAL-PENDING |
| Ollama (local models) | **V (CI+HW)** | MP (HW) | MP (CI+HW) | MP (CI+HW) | MP (CI+HW) | MP (CI+HW) | CI: discovery/API code; real model execution/GPU offload out of scope |
| CrewAI (agents/flows runtime) | **V (CI)** | MP (CI) | MP (CI) | MP (CI) | MP (CI) | MP (CI) | CI: import/compat tests; **native wheel availability per target is the blocker** |
| Terminal (human-only argv policy) | **V (CI)** | MP (CI) | MP (CI) | MP (CI) | MP (CI) | MP (CI) | CI: policy tests; POSIX shell semantics/argv availability MANUAL-PENDING |
| Git (read-only repo operations) | **V (CI)** | MP (CI) | MP (CI) | MP (CI) | MP (CI) | MP (CI) | CI when git installed; external binary per target |
| LSP (detection + stdio JSON-RPC) | **P (CI)** | MP (CI) | MP (CI) | MP (CI) | MP (CI) | MP (CI) | CI with fake transports; real language servers MANUAL-PENDING |
| MCP (local stdio servers) | **P (CI)** | MP (CI) | MP (CI) | MP (CI) | MP (CI) | MP (CI) | CI: stdio client/config tests; real servers external, human-configured |
| GPU (optional telemetry/acceleration) | **P (HW)** | MP (HW) | MP (HW) | MP (HW) | MP (HW) | MP (HW) | MANUAL-PENDING: NVIDIA-only telemetry; AMD/Metal/MLX never required, not queried |

Cross-cutting notes:

- **No cell above is a support claim for a non-Windows target.** "MP" always means "shared code exists; build/run/acceptance not recorded".
- **Windows ARM64** is the most likely native blocker: CrewAI 1.15.32 hard-requires `chromadb~=1.5.9` and `lancedb>=0.33`, both Rust-built (`maturin`) native wheels. Only `win_amd64` artifacts are evidenced here; C2 now declares all six native runtimes and dependency pins but every runtime is unmeasured, so ARM64 wheel/runtime availability still must be verified on a real release runner (section 10.1).
- **macOS** additionally needs notarization/signing and audio/display manual checks that cannot be inferred from code.
- CI can only raise confidence for the CI-class items; it can never clear a MANUAL-PENDING hardware/clean-machine row.

### 4.1 CI-verifiable vs MANUAL-PENDING (what each gate can prove)

| Area | Automatable in CI (per target) | MANUAL-PENDING (real hardware / real machine) |
|---|---|---|
| GUI | Qt offscreen construction, page counts, smoke flows | real display server/WM, focus, DPI, menus, drag/drop |
| Editor | widget construction, guarded save, stale-content CAS | native file dialogs, IME, clipboard shortcuts |
| Clipboard | attachment bytes path with synthetic images | OS clipboard screenshot paste, cross-app drag/drop |
| Attachments | extraction/limits/provenance tests | OS drag/drop origin metadata, huge-file UX |
| Microphone | nothing real (fake recorder only) | device enumeration, permission prompts, capture quality |
| ASR/TTS | lifecycle with fakes, capability detection | engine install, model load, latency, audio output |
| Ollama | HTTP API discovery against a local server | model availability/quality/VRAM offload, GPU backend |
| CrewAI | import/compat/unit tests | real long agent runs, native wheel availability per target |
| Terminal | policy refusals, argv runner with fakes | real shell commands/quoting per OS, QProcess behaviour |
| Git | read-only subprocess calls with injected runner | real repo states, line-ending/permission behaviour |
| LSP | detection with fake `which`, JSON-RPC framing with fake transport | real servers, diagnostics/hover completeness |
| MCP | config validation, stdio client with fake transport | real local MCP servers, approval UX |
| GPU | probe logic with injected runner (no hardware) | NVIDIA/AMD/Apple telemetry, driver states, memory pressure |
| Packaging/provisioning | runtime-manifest schema validation, six-target selection/refusal tests, offline provisioner plan/install with fake archives (C2 tests; see `docs/BOOTSTRAPPER.md` section 8) | real measured runtime archives, real downloads/mirrors, signing/notarization, clean install per OS |
| Beta workflow/diagnostics | CI-workflow static guards, secrets-audit unit tests, diagnostic-report redaction tests (committed; not executed on GitHub here) | real tester installs, issue triage, owner authorization, real-hardware acceptance records |

---
## 5. Tracked-module inventory (every tracked module classified)

Portability classes: **A** = portable pure-Python (stdlib only, no OS calls); **B** = portable code but depends on an external native/runtime component (Qt, SQLite engine, CrewAI native stack, an external executable); **C** = Windows-first assumption that needs a platform adapter (explicit list + evidence below); **D** = packaging/artifact gap owned by C2/C3 (not an application-code portability defect); **T** = tests/docs (portable pytest, but several tests encode Windows assumptions).

### 5.1 Application package `nl_coding_agent/` (90 modules)

| Package | Modules (complete) | Class | Per-target consequence |
|---|---|---|---|
| `nl_coding_agent` (3) | `__init__, cli, main` | C (cli: detached-process flags), A (main) | CLI works via Python on any OS; `cli.py:381-402` Windows-only flags are guarded but the POSIX detached-supervisor fallback is unverified |
| `agents` (5) | `__init__, crew_backend, orchestrator, specs, supervisor_executor` | B | Depends on CrewAI native stack; shared code |
| `app` (8) | `__init__, attachments, debug, lsp, mcp, services, speech, supervisor_service` | B (all); C within `services.py` (command-name policy) | External engines/servers; extraction libs probed at runtime; see feature matrix |
| `core` (22) | `__init__, autonomous_roadmap_planner, backlog, candidate_verification, code_integrity_gate, mission_lock, permissions, platform_support, promotion, recovery_store, relocation, resource_gate, retention, roadmap, run_control, selfbuild_runner, staging_broker, status, supervisor, task_graph, version, workspace` | A except: C for `status.py` (SystemDrive fallback, guarded), `selfbuild_runner.py` + `supervisor.py` (Windows resume-command strings), B for `candidate_verification.py` (spawns `sys.executable`); `platform_support.py` is A (stdlib-only declarations/probes, committed by C1) | Core orchestration/state is portable Python + SQLite; resume messages are Windows-only text |
| `flows` (7) | `__init__, approval_provider, events, mission_flow, persistence, state, supervisor_flow` | B | Depends on CrewAI Flows/native stack |
| `gui` (5) | `__init__, __main__, main, main_window, theme` | B; C for `theme.py:47` font preference and `main_window.py:503-518` NVIDIA-only GPU probe | Qt GUI is shared; Windows-first cosmetics/telemetry |
| `gui/dialogs` (2) | `__init__, open_project` | B | Qt file dialog; native dialog behaviour MANUAL-PENDING |
| `gui/widgets` (17) | `__init__, agents_panel, autonomy_panel, chat_panel, command_palette, editor_panel, file_viewer, git_panel, inspector_panel, log_panel, models_panel, problems_panel, projects_panel, settings_panel, sidebar, task_board, terminal_panel` | B | Qt widgets; clipboard/drag-drop/terminal paths need real-desktop checks |
| `models` (5) | `__init__, capabilities, model_router, ollama_registry, providers` | B | Ollama CLI/HTTP and OpenAI-compatible HTTP; external services |
| `persistence` (4) | `__init__, database, missions, supervisor_store` | B | SQLite engine is native per platform; schema/code portable |
| `projects` (3) | `__init__, registry, scanner` | A | Portable path scanning |
| `resources` (2) | `__init__, scheduler` | A | Threads only |
| `tools` (7) | `__init__, crew_tools, filesystem, git_tools, registry, shell, verification` | B; C for `shell.py` (OEM codepage via ctypes + `shell=True`), `verification.py` (`python\python.exe` probe), `git_tools.py` (external git) | Tool layer is the main Windows-first surface; see 5.2 |

Installers and CI/release scripts (owned by C2/C3/C4/C5, not application modules): `installer/` 8 modules (`__init__, bootstrap, fetcher, operations, platform_manifest, platform_targets, provision, runtime_manifest`), `scripts/` 17 modules (`__init__-free scripts incl. `audit_release_secrets`, `diagnostic_report`, `scripts/ci/{bootstrap_check,checksums,headless_gui_smoke}`), `tests/` 68 files.

### 5.2 Class C - Windows-first assumptions (file:line evidence)

| # | File:line | Assumption | Impact on non-Windows | Recommended adapter |
|---|---|---|---|---|
| C1 | `cli.py:381-402` | `_launch_detached` uses `DETACHED_PROCESS` / `CREATE_NEW_PROCESS_GROUP` (guarded by `hasattr`) | POSIX fallback passes no flags and no session detach; child may die with the terminal; unverified | Platform adapter returns POSIX process flags (`start_new_session=True`); C4 to test |
| C2 | `tools/shell.py:19-27` | `ctypes.windll.kernel32.GetOEMCP` for console decoding (guarded `os.name == "nt"`) | POSIX returns `None`, decode falls back to locale/UTF-8: fine | None required; keep guarded |
| C3 | `tools/shell.py:85` | `shell=True` for the verification command string | Windows -> cmd.exe; POSIX -> /bin/sh; quoting/availability of the generated command differs and is unverified | Prefer argv-based runner; keep legacy string path for project-agnostic test commands |
| C4 | `tools/verification.py:14` | Detects only `<project>/python/python.exe` | POSIX embedded layout/executable differ | Platform adapter for runtime executable discovery (C2 provides per-target runtime layout) |
| C5 | `core/status.py:19-22` | `SystemDrive` fallback for the disk root (guarded `os.name == "nt"`) | POSIX uses `/`: fine | None required |
| C6 | `core/selfbuild_runner.py:158-165` | Resume command text `python\python.exe nl_agent.py ...` | Wrong/backslash command printed on POSIX | Build from `sys.executable` + platform launcher name |
| C7 | `core/supervisor.py:236` and `:1743` | Same Windows resume-command strings | Same | Same adapter |
| C8 | `gui/main_window.py:503-518` | GPU telemetry only via `nvidia-smi`; unknown shows an em dash | No AMD/Metal probing; correct fail-closed behaviour, no CUDA requirement | Optional: inject platform probe from `platform_support.probe_gpu` |
| C9 | `gui/theme.py:47` | Font stack starts with `Segoe UI` (Windows font) | Qt falls back to Inter/sans-serif; cosmetic only | Add per-OS preferred font in tokens (C4 UI polish) |
| C10 | `app/lsp.py:217, 267` | Document URIs are built from the local path by replacing backslashes with forward slashes and stripping the leading slash | Windows drive-letter spelling and POSIX root spelling are both plausible; real editor/server URI handling is untested on non-Windows targets | Covered by LSP client tests with fakes; real server check is MANUAL-PENDING |
| C11 | `app/services.py:458-576` | Terminal deny/allow lists mix POSIX and Windows command names (`del`, `taskkill`, `powershell`, `rm`, `chmod`, ...) | Policy is argv+name based and shell-refusing on both; some OS-native commands are not listed | Keep list per-OS-extensible; CI can test names |
| C12 | Launcher layout: 1 root GUI `NL Coding Agent.bat` + 5 files under `scripts/launchers/` (3 payload-shipped CLI: `doctor.bat`, `status.bat`, `Self-Build Mode.bat`; 2 dev-only VoiceBridge) | `cmd.exe` syntax (`%~dp0`, `setlocal`, `pause`, `%ERRORLEVEL%`) and `python\python.exe` | No Linux/macOS launcher is shipped; only the launcher *names* are declared per target (`installer/platform_targets.py:60,71,82,93`) | C2 ships the declared `NL Coding Agent.sh` per target; payload remap in `scripts/stage_portable.py` |
| C13 | `scripts/stage_portable.py:35-51` (INCLUDED_ROOTS + `LAUNCHER_SOURCE_TO_PAYLOAD`) | Windows embedded `python/` and `.bat` launchers are staged; the 3 CLI launchers are remapped from `scripts/launchers/` to payload root | Portable payload is still Windows-only by construction; non-Windows payload needs a measured runtime + `.sh` launcher | C2 owns the per-target payload extension |
| C14 | `scripts/build_release.py:76-79` | `DEFAULT_PLATFORMS`/`DEFAULT_LAUNCHERS` now derive from `installer/platform_targets.py`: all six targets, per-target launcher names; runtime-manifest emission supports measured archives (`--runtime-archive TARGET=PATH`) | Implemented in C2; still no measured archives, so generated runtime manifests remain `release_ready=false` | C2/release pipeline supplies measured archives per target |
| C15 | `installer/platform_manifest.py:24` (PLATFORM_KEYS), `:219` (`detect_platform`) | All six ids accepted; `installer/platform_manifest.json` now declares all six platform entries; native provisioning uses the separate six-target `installer/runtime_manifest.json` + `installer/provision.py` | Schema valid for six targets; artifacts unmeasured | C2 keeps manifests in sync; release pipeline produces measured manifests |
| C16 | `installer/operations.py` | Platform-aware cache dirs (:74), forbidden install roots (:123), atomic verified downloads and symlink-safe extraction; `installer/provision.py` delegates to this machinery for native runtimes | Code is portable; no macOS/Linux clean-machine acceptance evidence | C2/C3 exercise it on real runners; CI uses fake local artifacts only |
| C17 | `scripts/verify_relocation.py` | Scans `*.bat`/`*.ps1` launchers and a hard-coded Windows drive pattern | Gate is Windows-specific (relocation tooling, not product runtime) | Keep Windows-only for this repo; CI C3 owns per-OS checks |

| C18 | `nl_coding_agent/core/platform_support.py:250-287` | Platform declarations still describe the **pre-C2** runtime-manifest state ("none (manifest schema accepts the key only)", `.command` launcher, "Universal 2 decision open") and use `.command` for macOS while C2 declares `NL Coding Agent.sh` | Documentation drift only (no runtime behaviour): this matrix and `installer/runtime_manifest.json` are authoritative | Follow-up: update the module declarations (tests assert only honesty invariants, so the change is safe); not edited in this docs-only re-sync | the only `ctypes`/`windll` use is C2 (OEM codepage). Other Windows-only API families found: none beyond the table above.

### 5.3 Tests and launchers

| Group | Files | Class | Notes |
|---|---|---|---|
| Tests | 68 tracked `tests/test_*.py` | T (portable pytest) | GUI tests use `QT_QPA_PLATFORM=offscreen`; some still encode Windows expectations: `test_selfbuild_mode.py` asserts `.bat` launchers, `test_verify_relocation.py` scans `*.bat`/`*.ps1`, `test_bootstrap_installer.py` uses Windows manifest fixtures, `test_crewai_runtime.py` checks site-packages vs vendor. C3 adds `test_ci_workflows.py` static guards; C5 adds `test_release_secrets_audit.py`. These need per-OS fixtures, not product changes. |
| Launchers | 1 root `NL Coding Agent.bat` + 5 under `scripts/launchers/` | D | Windows-only; layout documented in `scripts/launchers/README.md`. Payload remap in `scripts/stage_portable.py`; C2 declares per-target launcher names. |
| Packaging scripts | `scripts/stage_portable.py`, `scripts/build_release.py`, `installer/*` | D | C2 implemented six-target runtime manifests, provisioner and release-builder integration; no measured archives yet. |
| CI/beta/audit tooling | `.github/workflows/ci.yml`, `scripts/ci/*`, `docs/CI.md`, `docs/BETA_TESTING.md`, `docs/PRIVATE_BETA_RUNBOOK.md`, `scripts/audit_release_secrets.py`, `scripts/diagnostic_report.py`, `.github/ISSUE_TEMPLATE/*` | D | C3-C5 evidence committed; not executed on GitHub here; CI success is never treated as support. |

---

## 6. Native / runtime dependency matrix

Since C2 the six-target `installer/runtime_manifest.json` (template, `release_ready=false`) also pins, per target, the runtime id/archive/URL plus the dependency ids `crewai 1.15.32`, `PySide6 6.12.0` and `psutil 7.2.2`, and declares optional CPU/GPU/ASR/TTS components (all accelerator/ASR/TTS entries marked unavailable with degradation text). Wheel evidence below is still from the local Windows runtime (`importlib.metadata` `WHEEL` Tag): PySide6 `cp310-abi3-win_amd64`; psutil `cp37-abi3-win_amd64`; PyYAML `cp312-cp312-win_amd64`; litellm `cp310-abi3-win_amd64` (maturin, `Root-Is-Purelib: false`); chromadb `cp39-abi3-win_amd64` (maturin); lancedb `cp310-abi3-win_amd64` (maturin); onnxruntime `cp312-cp312-win_amd64`; numpy `cp312-cp312-win_amd64`; crewai `py3-none-any`; pytest/httpx/openai/pydantic `py3-none-any`. Tags: **verified-local** = wheel present and imported here; **MP** = not evidenced (MANUAL-PENDING); **RISK** = likely blocker to confirm; **optional** = absent locally, fail-closed.

| Dependency | Role | windows-x86_64 | windows-arm64 | linux-x86_64 | linux-aarch64 | macos-x86_64 | macos-arm64 | Action / note |
|---|---|---|---|---|---|---|---|---|
| CPython runtime | application runtime | verified-local dev runtime (3.12.10 MSC x64) | MP/RISK | MP | MP/RISK | MP | MP | Six-target `runtime_manifest` declares one runtime per target but all unmeasured; `provision.py` refuses cross-target/native reuse; never reuse Windows runtime |
| PySide6 / Qt 6.12.0 | GUI | verified-local (win_amd64 + Windows Qt plugins) | MP/RISK | MP | MP/RISK | MP | MP | Pinned per target in the runtime manifest (package id/version); per-target wheels and Qt plugins still unverified |
| Qt Multimedia (QAudioSource) | mic/recording | P (plugin present, real mic untested) | MP | MP (needs PulseAudio/PipeWire/ALSA + Qt plugin) | MP | MP (CoreAudio) | MP | MANUAL-PENDING per target |
| SQLite (`sqlite3`) | persistence | verified-local 3.49.1 | MP | MP (ships with CPython) | MP | MP | MP | Bundled with CPython; no app-side native build |
| psutil 7.2.2 | status/leases | verified-local | MP | MP | MP | MP | MP | Has per-OS wheels; C2 pins |
| PyYAML 6.0.3 | config | verified-local | MP | MP | MP | MP | MP | native (C ext); per-OS wheels |
| pydantic / pydantic_core | CrewAI/Flows | verified-local | MP | MP | MP | MP | MP | pydantic-core is Rust-native; ARM64/macOS wheels verified by C2 |
| tokenizers | CrewAI/litellm | verified-local (Rust) | MP/RISK | MP | MP/RISK | MP | MP | native Rust; per-target wheels required |
| crewai 1.15.32 | orchestration | verified-local (import + tests) | MP/RISK | MP | MP | MP | MP | pure wheel, but requires chromadb+lancedb+tokenizers; pinned per target in the runtime manifest, wheel availability unverified |
| litellm 1.100.4 | model provider layer | verified-local | MP/RISK | MP | MP | MP | MP | installed wheel is maturin-built for win_amd64; per-target wheel needed |
| chromadb 1.5.9 | CrewAI memory/vector | verified-local (Rust win_amd64) | MP/RISK | MP | MP/RISK | MP | MP | crewai hard-requires `chromadb~=1.5.9`; native wheel matrix must be verified |
| lancedb 0.40.0 | CrewAI knowledge/vector | verified-local (Rust win_amd64) | MP/RISK | MP | MP/RISK | MP | MP | crewai requires `lancedb>=0.33,<1`; native wheel matrix must be verified |
| onnxruntime 1.31.1 | chromadb embedding helper | verified-local | MP/RISK | MP | MP/RISK | MP | MP | native; per-target wheel needed |
| numpy 2.5.4 | transitive | verified-local | MP | MP | MP | MP | MP | native; per-target wheels |
| tiktoken / aiohttp | litellm transitive | verified-local | MP | MP | MP | MP | MP | native/Rust components per target |
| pytest 9.2.0 | verification runner | verified-local | MP | MP | MP | MP | MP | pure wheel; CI runners install it |
| Ollama (binary/HTTP) | local models | verified-local (binary on PATH) | MP | MP | MP | MP | MP | external install; not bundled |
| ffmpeg | optional media | present on PATH (optional) | MP | MP | MP | MP | MP | discovery only (`tools/registry.py:115-178`); not required |
| ASR: faster-whisper / vosk / qwen3-asr | mic transcription | optional/absent (fail-closed) | optional | optional (CTranslate2 native per OS) | optional | optional | optional | local human install; hints in `app/speech.py:31-35` |
| TTS: Piper / NL_TTS_COMMAND | speech output | optional/absent | optional | optional | optional | optional | optional | local human install |
| sounddevice / PortAudio | audio capture alt | optional/absent | optional | optional | optional | optional | optional | native PortAudio per OS |
| debugpy | DAP debugging | optional/absent | optional | optional | optional | optional | optional | pure Python; not installed here |
| LSP servers (pylsp/pyright/clangd/...) | editor diagnostics | absent (detection tested) | optional | optional | optional | optional | optional | external binaries; `app/lsp.py:22-29` |
| MCP servers | tools | absent (stdio client tested) | optional | optional | optional | optional | optional | external local processes; stdio only |
| Git | read-only repo ops | verified-local (git on PATH) | optional | optional | optional | optional | optional | external install |
| NVIDIA driver / nvidia-smi | optional telemetry | partial (probe only) | MP | MP | MP | MP | MP | optional; never required |
| AMD ROCm / rocm-smi | optional telemetry | not queried | not queried | candidate command only, never executed by default | not queried | n/a | n/a | never required |
| Apple Metal / MLX | optional acceleration | n/a | n/a | n/a | n/a | not queried / never required | not queried / never required | no forced backend |
| Native runtime archives (six targets) | provisioning | dev `python/` only (never shipped) | MP (unmeasured) | MP (unmeasured) | MP (unmeasured) | MP (unmeasured) | MP (unmeasured) | `runtime_manifest.json` is a template: `sha256=""`/`size=0` for all six, `release_ready=false`; install/update/repair refuse it |
| Per-target dependency pins | provisioning | declared | declared | declared | declared | declared | declared | `runtime_manifest.json` pins `crewai/PySide6/psutil` per target; validated by C2 tests (measured-only policy; no fabricated hashes) |
| Optional CPU/GPU/ASR/TTS components | provisioning/backends | CPU available; CUDA/whisper/piper unavailable (declarations) | same declarations | declared CPU/ROCm | declared CPU | declared CPU/Metal | declared CPU/Metal/MLX | All `optional:true`, `required:false` with degradation text; CUDA/ROCm/Metal/MLX never mandatory (section 10.1) |
| PDF/Office extraction libs | attachments | pdfplumber/openpyxl/PIL present; docx/pptx absent | same | per target install | same | same | same | optional, fail-closed |

---

## 7. Per-target blockers and MANUAL-PENDING acceptance checklists

### 7.1 Blockers before any non-Windows claim (status after C2-C5)

1. **Measured native runtime archives** per target with real sha256/size - the schema/provisioner are implemented (C2), but `installer/runtime_manifest.json` is a `release_ready=false` template with zero measured runtimes. No non-Windows artifact exists yet.
2. **Native dependency wheel matrix on real runners** (CrewAI stack: chromadb/lancedb/onnxruntime/tokenizers/pydantic-core; PySide6/Qt plugins; numpy; tiktoken/aiohttp) - manifest pins exist, availability/installation is unverified.
3. **Shipped per-target launchers** - only launcher *names* are declared (`NL Coding Agent.sh` for Linux/macOS); the tracked tree still ships Windows `.bat` launchers only. Payload extension per target is C2 work.
4. **Clean-install acceptance per target** - the provisioner/installer support plan/install/verify/update/repair with hash verification and offline bundles (C2), but no clean machine has run it.
5. **CI execution evidence** - the workflow definition exists (`.github/workflows/ci.yml`, `docs/CI.md`) but has not run on GitHub in this repository state; ARM64 jobs are explicitly experimental/non-blocking. CI success will never be treated as support.
6. **macOS packaging** - code signing/notarization decision still open for distribution; the Universal 2 decision is recorded as **not claimed** (separate `macos-x86_64`/`macos-arm64` runtimes; `runtime_manifest.json` `universal2.decision="separate-per-arch"`).
7. **POSIX semantics** - `shell=True` verification path, detached supervisor, terminal command availability, executable bits/symlinks in packaged launchers remain unverified.
8. **Real-hardware beta acceptance** (NL-BP-164) - documented in `docs/BETA_TESTING.md` (MANUAL-PENDING matrix) and `docs/PRIVATE_BETA_RUNBOOK.md`, not yet recorded per tester (OS/arch, package checksum, install path, results).
9. **Pre-upload audit refresh** - the C5 secrets snapshot is CLEAR-WITH-REVIEW at `b139065` (pre-reorg); it must be re-run at the current HEAD before any share/upload, followed by owner authorization (`docs/PRIVATE_BETA_RUNBOOK.md`).

### 7.2 MANUAL-PENDING checklist (run on every target before claiming support)

- [ ] Package: checksum/version manifest verified; install to a non-default path without a global Python/pip/uv/conda.
- [ ] First run: GUI opens on a real desktop; DPI/focus/window-manager behaviour acceptable; no console crash.
- [ ] Clipboard: paste a screenshot and a file from another application; drag/drop a file onto chat.
- [ ] Editor: open/save a file, stale-content conflict refused.
- [ ] Attachments: text + PDF/XLSX extraction; docx/pptx fail closed with a clear message.
- [ ] Microphone: device enumeration, permission prompt, record + transcribe with a local engine; TTS output.
- [ ] Ollama: local server reachable, required models discovered/loaded; one real Developer->Tester->Reviewer mission.
- [ ] CrewAI: agent/flows import and one real local-model run per target.
- [ ] Terminal: explicit human command runs (no shell); destructive/network refusals hold.
- [ ] Git: status/diff/log on a real repository (read-only).
- [ ] LSP: at least one installed language server returns diagnostics.
- [ ] MCP: at least one local stdio server discovered; tool call requires approval.
- [ ] GPU (optional): telemetry reported or cleanly "unavailable"; no CUDA/ROCm/Metal/MLX requirement enforced; CPU-only run works.
- [ ] Restart/resume: mission state survives restart; no duplicate tasks; lock hygiene.
- [ ] Update/repair/rollback via bootstrapper (where implemented) with managed files intact.
- [ ] Native runtime provisioning: release runtime manifest has measured sha256/size for the target, `provision plan/install/verify` succeeds offline, and no Windows runtime artifact was reused off Windows.
- [ ] CI provenance: artifact report bundle + `SHA256SUMS` reviewed; a green CI run recorded as CI evidence only (never as platform support).

---

## 8. Known limitations of this audit

1. **No network access** was used: PyPI wheel availability for non-Windows targets could not be queried. The audit reports "not evidenced/MANUAL-PENDING" and "wheel-tag risk" instead of inventing availability; C2 must verify on the release runner.
2. **No non-Windows machine or VM** was available: every non-Windows cell is MANUAL-PENDING by construction.
3. **No real hardware checks**: microphone, audio output, GPU, clipboard, DPI/focus are explicitly unverified.
4. **Snapshot scope**: this is a docs-only re-sync at committed HEAD `4089616` (clean tree); C2-C5 are committed but no GitHub CI run, no measured native archives and no non-Windows machine were available, so those cells remain MANUAL-PENDING.
5. **No runtime execution of installers/provisioner** and no self-build/mission run (task constraints); C2's provisioner/installer evidence is reviewed from code + committed tests, not executed here.
6. Static classification cannot prove absence of platform bugs; it lists assumptions and the evidence that exists.
7. `scripts/verify_relocation.py` and this repository's operational scripts are Windows-oriented; they are development tooling, not product runtime, and are out of scope for beta packaging.
8. Optional backend availability is machine-specific; the module reports it at runtime and always fails closed rather than silently degrading.
9. **Declaration drift**: `nl_coding_agent/core/platform_support.py` still carries pre-C2 runtime-manifest/launcher wording (C18). This document and `installer/runtime_manifest.json` are authoritative; a follow-up module update is recommended and out of scope for a docs-only re-sync.
10. **Secrets audit is a snapshot**: `docs/SECRETS_AUDIT.md` was generated at `b139065` (321 tracked files) before the ROOT REORG Phase A; it must be re-run at the current HEAD before any upload decision. This re-sync also removes the absolute document-URI example that the audit listed as F0018, so a fresh run should no longer report that matrix line.

---

## 9. Maintenance and CI synchronisation

- The matrix must be updated in the same change that adds CI evidence or beta-test results; a green CI job is not a support claim (program constraint #7).
- Snapshot discipline: record the git HEAD, date and tracked-file count at the top; re-verify file:line references when code moves; prefer function names when a reference is unstable.
- Machine-readable declarations live in `nl_coding_agent/core/platform_support.py`; tests enforce honesty rules (`tests/test_platform_support.py`: only windows-x86_64 may be "verified"; non-Windows features must stay "manual-pending"; GPU never required).
- Cross-reference the evidence sources instead of duplicating them: `installer/runtime_manifest.json` + `installer/platform_targets.py` + `installer/provision.py` (C2), `docs/CI.md` + `.github/workflows/ci.yml` (C3), `docs/BETA_TESTING.md` + `docs/PRIVATE_BETA_RUNBOOK.md` + `.github/ISSUE_TEMPLATE/*` (C4), `docs/SECRETS_AUDIT.md` (C5), `docs/BOOTSTRAPPER.md` section 7, `docs/RELEASE_ACCEPTANCE.md` cross-platform rows.
- Re-validate the matrix after each such commit: platform ids must match `installer/platform_targets.py (TARGET_ORDER)` and `platform_support.PLATFORM_IDS`; every referenced repository path must exist; the feature table must keep exactly 13 areas; no non-Windows value may be "verified".
- If a target moves from MP to verified, the matrix cell, the module declaration, and the evidence (CI run URL or beta-test record) must change together.

---


---

## 10. Cross-workstream evidence incorporated by this re-sync (C2-C5 + ROOT REORG Phase A)

This section is the index from this matrix to the evidence produced by the other workstreams. It records what is implemented, what is only a definition/template, and what stays MANUAL-PENDING. Nothing here is a platform-support claim.

### 10.1 Six-target native runtime manifests and provisioner (C2)

Evidence: `installer/platform_targets.py` (single source of truth for the six targets, host detection, aliases, strict native guard), `installer/runtime_manifest.py` + `installer/runtime_manifest.json` (schema + template), `installer/provision.py` (provisioner), `docs/BOOTSTRAPPER.md` section 7, and the C2 tests cited there (**56 passed** for bootstrapper + provisioner + release builder, per `docs/BOOTSTRAPPER.md` section 8; not re-executed by this docs-only re-sync).

| Target | Runtime id (manifest) | Archive | Manifest state | Launcher name declared |
|---|---|---|---|---|
| `windows-x86_64` | `python-runtime-windows-x86_64` | zip | template, `measured=false` | `NL Coding Agent.bat` (shipped) |
| `windows-arm64` | `python-runtime-windows-arm64` | zip | template, unmeasured | `NL Coding Agent.bat` (shipped; runtime missing) |
| `linux-x86_64` | `python-runtime-linux-x86_64` | tar.gz | template, unmeasured | `NL Coding Agent.sh` (declared, not shipped) |
| `linux-aarch64` | `python-runtime-linux-aarch64` | tar.gz | template, unmeasured | `NL Coding Agent.sh` (declared, not shipped) |
| `macos-x86_64` | `python-runtime-macos-x86_64` | tar.gz | template, unmeasured | `NL Coding Agent.sh` (declared, not shipped) |
| `macos-arm64` | `python-runtime-macos-arm64` | tar.gz | template, unmeasured | `NL Coding Agent.sh` (declared, not shipped) |

Implemented guarantees (code-level, verified by reading the sources and the C2 tests as recorded):

1. **Exactly six targets.** `runtime_manifest.validate_runtime_manifest` requires the target key set to equal `TARGET_ORDER` exactly (`installer/runtime_manifest.py:205-212`); unknown hosts/targets fail closed with guidance (`installer/platform_targets.py:133-191`).
2. **Measured hashes only, never fabricated.** An unmeasured artifact MUST have empty `sha256` and `size=0`; a measured artifact requires a real 64-hex sha256 and positive size; `release_ready=true` requires all six runtimes measured (`runtime_manifest.py:89-107, :169-212`; `installer/runtime_manifest.json` `release_ready=false`).
3. **No Windows runtime reuse.** The embedded `python/` Windows x64 development runtime is never referenced by the provisioner; a Windows artifact is rejected for Linux/macOS and vice versa, and install/update/repair require the selected target to match the native host (`installer/platform_targets.py:210-248`; `installer/provision.py:7-16, :110-121`).
4. **Template is not installable.** `provision.py` refuses install/update/repair unless `release_ready` is true and the target runtime is measured (`provision.py:181-186`); a plan for a template manifest warns and writes nothing.
5. **macOS Universal 2 is NOT claimed.** Decision is `universal2.supported=false`, `decision="separate-per-arch"` with rationale/evidence fields (`installer/runtime_manifest.json:15-21`; `installer/runtime_manifest.py:19-23, :186-203`; `docs/BOOTSTRAPPER.md` "macOS Universal 2 decision"). Separate `macos-x86_64` and `macos-arm64` runtimes are declared.
6. **Optional CPU/GPU/ASR/TTS are declarative only.** Each target lists optional components with `optional:true`, `required:false` and a degradation message; CPU is always available, CUDA/ROCm/Metal/MLX/ASR/TTS are optional and unavailable in the template. None is mandatory and a missing backend degrades gracefully (`runtime_manifest.py:9-11, :146-166`; `installer/runtime_manifest.json` per-target `optional_components`).
7. **Dependency pins per target** exist for `crewai 1.15.32`, `PySide6 6.12.0`, `psutil 7.2.2` (`installer/runtime_manifest.json` dependency arrays; `scripts/build_release.py:82-86` `PINNED_DEPENDENCIES`). Native wheel availability per target is still unverified (section 6).

**Still MANUAL-PENDING:** no measured runtime archive, no real download/mirror, no clean install on any target, no code signing/notarization, no non-Windows launcher shipped.

### 10.2 GitHub Actions CI matrix (C3)

Evidence: `.github/workflows/ci.yml`, `scripts/ci/{headless_gui_smoke,bootstrap_check,checksums}.py`, `docs/CI.md`, `tests/test_ci_workflows.py` (static guards; 7 tests per `docs/RELEASE_ACCEPTANCE.md`, not executed here).

| Matrix job | Runner | Arch | Blocking? | Notes |
|---|---|---|---|---|
| `windows-x64` | `windows-latest` | x64 | yes | primary Windows job |
| `windows-arm64` | `windows-11-arm` | arm64 | **no** (public preview, `experimental: true`) | a green/amber run is not native ARM64 support |
| `ubuntu-x64` | `ubuntu-latest` | x86_64 | yes | primary Linux job |
| `ubuntu-arm64` | `ubuntu-24.04-arm` | aarch64 | **no** (public preview) | alternative: self-hosted ARM64 or QEMU (not implemented) |
| `macos-arm64` | `macos-14` | arm64 | yes | Apple Silicon hosted runner |
| `macos-intel-x64` | `macos-13` | x86_64 | yes | Intel hosted runner while available |

Jobs run: unit tests (GUI smoke/panels/bootstrap excluded), integration tests (bootstrapper, staged-candidate orchestrator, supervisor Flow, flow persistence/resume), headless offscreen GUI smoke, offline bootstrapper checks with fake local artifacts, and report checksums; only `reports/` is uploaded (7-day retention). Safety guards: `permissions: contents: read`, no push/publish/release/visibility/collaborator actions.

**Status here:** the workflow is a committed definition; there is **no GitHub run evidence** in this repository state, so no matrix cell is upgraded and `docs/CI.md`'s MANUAL-PENDING list remains authoritative. CI success, when it exists, is regression evidence only (program constraint #7).

### 10.3 Beta testing, diagnostics and feedback workflow (C4)

Evidence: `docs/BETA_TESTING.md` (tester onboarding, privacy/no-telemetry statement, platform status table, first-run checklist, MANUAL-PENDING acceptance matrix), `docs/PRIVATE_BETA_RUNBOOK.md` (owner gates, pre-upload checklist, package rules, versioning/checksums, authorization procedure, triage rules, withdrawal/rollback, roles), `.github/ISSUE_TEMPLATE/{beta_bug,beta_feature,config}.yml` (platform/arch/severity/evidence labels, including `evidence/MANUAL-PENDING` vs `evidence/CI`), and the opt-in redacted diagnostic report (`scripts/diagnostic_report.py`, tests `tests/test_diagnostic_report.py`).

Matrix implications: real-hardware evidence is recorded per tester with OS/arch, package checksum, install path and result; until then the acceptance matrix in `docs/BETA_TESTING.md` section 10 keeps every real-hardware row MANUAL-PENDING. This matrix stays consistent with that table and does not duplicate it.

### 10.4 Pre-upload secrets and repository audit (C5)

Evidence: `scripts/audit_release_secrets.py`, `docs/SECRETS_AUDIT.md`, `tests/test_release_secrets_audit.py` (12 tests per `docs/RELEASE_ACCEPTANCE.md`).

Snapshot at `b139065` (before ROOT REORG Phase A): tracked files 321, git history 50 commits / 374 object paths, 4.38 MiB scanned, **59 findings: 0 blocking** (ROTATE 0; EXCLUDE-FROM-UPLOAD 7, all present-but-untracked local-only trees; REVIEW 52), upload gate **CLEAR-WITH-REVIEW**. No ROTATE credential and no tracked/history upload-exclusion artifact was found in the bounded scan; the 52 review items still need owner/developer decisions and local-only trees must stay out of any package.

Matrix implications: (a) this is a pre-reorg snapshot and **must be re-run at the current HEAD before any upload/share**; (b) owner authorization remains mandatory (`docs/PRIVATE_BETA_RUNBOOK.md`); (c) this re-sync rewords the document-URI example previously flagged as F0018 (absolute file-URL string), so a fresh scan should no longer report that matrix line; (d) no secret values are reproduced here.

### 10.5 Launcher layout and ROOT REORG Phase A

| Item | Current location | Shipped? | Notes |
|---|---|---|---|
| GUI launcher | root `NL Coding Agent.bat` | yes, payload root | **single obvious root launcher** |
| CLI launchers | `scripts/launchers/{doctor,status,Self-Build Mode}.bat` | yes, remapped to payload root by `scripts/stage_portable.py:35-51` | names preserved for users |
| VoiceBridge dev launchers | `scripts/launchers/voicebridge/{audit_voicebridge,work_voicebridge}.bat` | no (development-only) | not part of the beta payload |
| Dated repair scripts | `docs/history/legacy/temp-scripts/{temp_fix_planner,temp_fix_title,temp_restore,temp_restore_planner}.py` | no | historical evidence; **never execute** (they mutate source/DB) |
| Review-only staging | `da_eliminare/` (only `README.md` tracked; contents git-ignored) | no | nothing may be deleted/moved/untracked from Git without explicit user authorization; excluded from payload (`scripts/stage_portable.py` `EXCLUDED_ROOTS`) and release builder (`scripts/build_release.py:48-61`) |

This is a layout/organization change, not an OS-portability change: the launchers are still Windows `.bat` files; the Linux/macOS launcher *names* are only declared in `installer/platform_targets.py`. `scripts/launchers/README.md` is the layout reference.

### 10.6 Matrix-reference and validation checks performed for this re-sync

| Check | Command | Result |
|---|---|---|
| Platform support tests | `python\python.exe -m pytest tests/test_platform_support.py -q -p no:cacheprovider` | **31 passed** (no hardware/network) |
| Platform id alignment | compare `installer.platform_targets.TARGET_ORDER`, `installer.runtime_manifest.json` target keys, `platform_support.PLATFORM_IDS`, and the section 3 table | 6/6 identical ids: `windows-x86_64, windows-arm64, linux-x86_64, linux-aarch64, macos-x86_64, macos-arm64` |
| Feature areas | count rows in section 4 vs `platform_support.FEATURE_AREAS` | 13/13 match |
| Referenced repository paths | extract every `...`-quoted repo path from this document and check existence at HEAD | all references resolve (document paths, installers, tests, scripts, workflows, launcher files) |
| Non-Windows honesty | scan section 3/4/10 for "verified" applied outside `windows-x86_64` | none: all six non-Windows cells stay V-free/MP |
| Secrets-sensitive strings | scan for absolute file-URL examples / credential-like values introduced by this edit | none; F0018-style document-URI string removed |
| Git state | `git status --porcelain` after the edit | only this document modified (no commit) |

**Remaining MANUAL-PENDING (not resolved by this re-sync):** every non-Windows target (runtime artifact, launch, install, GUI, mission, terminal/Git/LSP/MCP, microphone/ASR/TTS, GPU, restart/resume, clean-machine acceptance), Windows ARM64 native availability, macOS signing/notarization, real CI runs on GitHub, measured runtime archives/hashes, secrets-audit re-run at HEAD, and all real-hardware acceptance records.

## Appendix A - platform_support module (NL-BP-153 summary)

File: `nl_coding_agent/core/platform_support.py` (new; stdlib only; no network, no model, no process execution by default).

| API | Purpose |
|---|---|
| `PLATFORM_IDS`, `FEATURE_AREAS` | six canonical target ids (aligned with installer keys) and the 13 feature areas above |
| `detect_platform(...)` | injectable OS/CPU detection -> `PlatformInfo` (supported flag + reason) |
| `require_supported_platform(...)` | raises `UnsupportedPlatformError(code="unsupported-platform")` with actionable hint and matrix path |
| `platform_declarations()/get_platform_declaration()` | per-target status, runtime-manifest state, launcher, notes |
| `feature_declaration()/feature_level()` | per-feature per-target level + CI-verifiable flag + manual-pending note + evidence refs |
| `support_snapshot()` | JSON-safe declaration snapshot for diagnostics/CLI |
| `probe_optional_backends(which=, find_spec=, environ=)` | read-only probes for git, ollama, ffmpeg, piper, ASR engines, Qt audio, sounddevice, debugpy, LSP servers, TTS command, built-in stdio MCP; deterministic codes/hints |
| `require_optional_backend(name, probes=...)` | fails closed with `UnsupportedConfigurationError(code="backend-unavailable")` and the install hint |
| `probe_gpu(platform=, which=, runner=)` | optional NVIDIA/AMD telemetry; **no execution without an injected runner**; macOS reported manual-pending; always `forced=False`, CUDA/ROCm/Metal/MLX not required |
| `environment_report(...)` | one JSON-safe report: platform + declaration + feature levels + probes + GPU; `real_hardware_verified: False` |

Tests: `tests/test_platform_support.py`, **31 passed** at HEAD `4089616` (`python\python.exe -m pytest tests/test_platform_support.py -q -p no:cacheprovider`): all six detect branches, unsupported-host fail-closed, declaration honesty (no verified claims outside Windows x64), injected probes with no process/network execution, GPU no-runner/no-hardware behaviour, macOS no-Metal requirement, JSON-safe reports. The module is committed; its platform declarations still contain the pre-C2 runtime-manifest/launcher wording listed as C18 (section 5.2) - a follow-up code update is recommended and was out of scope for this docs-only re-sync.

## Appendix B - what this re-sync changed (C1b, docs-only)

- Updated the snapshot to HEAD `4089616` (2026-10-28 19:26 Europe/Rome; HEAD advanced to docs-only `68fe22a` while writing), 333 tracked files; corrected repository counts (90 app modules / 8 installer modules / 17 scripts / 68 tests) and the launcher layout (1 root GUI launcher + 5 under `scripts/launchers/`, temp scripts archived, `da_eliminare` staging).
- Re-verified every file:line reference in the module inventory and class-C table at this HEAD; fixed the broken C1 rendering (DETACHED_PROCESS/CREATE_NEW_PROCESS_GROUP) and refreshed C3/C4/C10/C11/C12/C13/C14/C15/C16/C18.
- Added section 10 with the C2-C5 + ROOT REORG evidence: six-target runtime manifests/provisioner (measured-only hashes, no Windows runtime reuse, macOS separate-per-arch decision, optional CPU/GPU/ASR/TTS), CI matrix (definition only, no GitHub run), beta testing/runbook/issue templates + redacted diagnostics, pre-upload secrets audit snapshot (CLEAR-WITH-REVIEW, must be re-run at HEAD), launcher/root-reorg layout, and the matrix-reference validation results.
- Kept the CI-vs-MANUAL-PENDING distinction explicit: no non-Windows support is claimed and no matrix cell was upgraded; C18 records the known declaration drift in `platform_support.py`.
- Removed the absolute document-URI example previously flagged by the secrets audit (F0018-style string).
- No installer/, .github/, scripts/build_release.py or other tasks' documents were edited (the only changed file is this matrix); no commit, no network/model/hardware/installer runs.


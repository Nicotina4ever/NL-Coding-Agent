# Cross-Platform Compatibility Matrix - NL Coding Agent private beta (C1)

**Status:** evidence-based audit + platform support abstraction implemented (`nl_coding_agent/core/platform_support.py`, `tests/test_platform_support.py`). No cross-platform support is claimed: every non-Windows target is **MANUAL-PENDING** until a real build and a real-machine acceptance run are recorded.
**Requirement IDs:** NL-BP-152 (audit + matrix), NL-BP-153 (platform abstraction), NL-BP-160 (matrix documentation); program `docs/CROSS_PLATFORM_PRIVATE_BETA_PROGRAM.md`.
**Audit snapshot:** 2026-10-28 19:12 Europe/Rome, git HEAD `29a0ca1` (tracked tree clean at snapshot; HEAD advanced to `871b266` during this task because C2/C3 committed concurrently). Workstreams C2 (installer/runtime manifests), C3 (CI) and C4 (beta workflow) were modifying installer/, launchers and .github/ concurrently; those areas are owned by their tasks and are classified here from the committed baseline, with an explicit note. This document must be re-synced after those commits (section 9).
**Method:** read-only static audit of the tracked repository + read-only probes of the local Windows runtime (`python\python.exe`). No network calls, no model runs, no self-build, no installer execution. Hardware/desktop behaviour is never claimed.

---

## 1. Verdict summary

| Question | Answer (evidence-based) |
|---|---|
| Is the application code forked per OS? | **No.** One `nl_coding_agent` package (89 tracked Python modules); platform differences are declarations/probes plus a small set of Windows-first assumptions listed in section 5. |
| Is any non-Windows target verified? | **No.** There is no Linux/macOS runtime, launcher, package or run evidence in the repository. All five non-Windows targets are MANUAL-PENDING. |
| Is Windows x86_64 a beta candidate? | **PARTIAL.** A Windows portable candidate exists (stage-6b) and local tests pass; clean-machine and real-desktop/hardware acceptance remain MANUAL-PENDING (already recorded in `docs/BOOTSTRAPPER.md`, `docs/CURRENT_STATE.md`, `docs/RELEASE_ACCEPTANCE.md`). |
| Does CI success mean support? | **No.** CI can verify unit/offscreen/bootstrap behaviour only; it cannot prove real desktop, microphone, GPU, clipboard or clean-machine install. This matrix separates the two. |
| Are CUDA/ROCm/Metal/MLX required? | **No.** GPU probing is optional and NVIDIA-only; unknown/unavailable is reported, never fatal. The new module enforces `cuda_required=False`, `rocm_required=False`, `metal_required=False`, `mlx_required=False` and `forced=False`. |
| Are native wheels for all six targets present? | **No.** Only the Windows x86_64 runtime exists locally; its native dependencies are `win_amd64` wheels (section 6). Manifest entries for other targets are schema-level only. |

---

## 2. Audit method and evidence basis

### 2.1 Repository facts (snapshot)

- `git rev-parse HEAD` = `29a0ca1`; tracked files = **314**; `nl_coding_agent` Python modules = **89**; `installer` Python modules = 5; `scripts` Python modules = 15 (including `scripts/ci/`, being added by C3); `tests` Python files = 65; root launchers = 6 `*.bat` at HEAD (relocation into `scripts/launchers/` was in progress, uncommitted, at snapshot).
- Packaging/adapters owned by other tasks: `installer/*` (C2), `scripts/build_release.py` (C2), `.github/` + `scripts/ci/*` (C3), beta workflow scripts (C4). This audit does not edit them.

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
git -C "K:\AI\NL Coding Agent" ls-files              # 314 tracked files at snapshot
git -C "K:\AI\NL Coding Agent" status --porcelain    # concurrent C2/C3 work noted, not audited as committed
python\python.exe -c "import platform, sys, sqlite3; print(platform.platform(), sys.version)"
python\python.exe -m pip list                             # or importlib.metadata per distribution
python\python.exe -c "from importlib import metadata; print(metadata.distribution('PySide6').read_text('WHEEL'))"
Get-ChildItem -Recurse python\Lib\site-packages\PySide6\plugins
# platform-assumption greps: sys.platform / os.name / ctypes / windll / DETACHED_PROCESS /
# CREATE_NEW_PROCESS_GROUP / .bat / .exe / shell=True / APPDATA / SystemDrive / which / nvidia
~~~

Automated evidence added by this task: `tests/test_platform_support.py` (31 tests, injected fakes; no hardware/network): `python\python.exe -m pytest tests/test_platform_support.py -q -p no:cacheprovider` -> **31 passed**.

---

## 3. Target matrix - six OS/arch targets

Legend for sections 4/5: **V** = verified by automated evidence recorded in this repository environment (today only Windows x86_64); **P** = partial (code path exists, only partly verifiable/optional component missing); **MP** = MANUAL-PENDING (shared code exists, but no build/run/real-machine evidence: support is not claimed); **U** = unsupported/known blocker.

| Target id | OS / CPU | Local runtime present | Launcher at HEAD | Bootstrapper manifest | Code status | Beta status |
|---|---|---|---|---|---|---|
| `windows-x86_64` | Windows 11 x64 | **yes** - developer embedded runtime in `python/` | `.bat` launchers (cmd.exe) | template entry + build_release default; runtime component optional/placeholder | shared code; Windows-first assumptions audited in section 5 | **PARTIAL**: local tests + one portable candidate r2; clean-machine and real-desktop acceptance MANUAL-PENDING |
| `windows-arm64` | Windows 11 ARM64 | no | `.bat` would run on Windows, but no ARM64 runtime/wheels | schema accepts key only (`installer/platform_manifest.py:23`); manifest declares no runtime | shared code; native dependency wheels not evidenced (chromadb/lancedb/onnxruntime win_arm64 absent here) | **MANUAL-PENDING**, likely native blocker to confirm in C2 |
| `linux-x86_64` | Linux x86_64 | no | `.sh` planned (not shipped) | template entry + build_release platform entry only (placeholder sha256/size) | shared code; POSIX assumptions unverified | **MANUAL-PENDING** |
| `linux-aarch64` | Linux ARM64 | no | `.sh` planned (not shipped) | schema accepts key only | shared code; ARM64 wheel availability unverified | **MANUAL-PENDING** |
| `macos-x86_64` | macOS Intel | no | `.command` planned (not shipped) | schema accepts key only | shared code; macOS specifics (audio, clipboard, packaging, notarization) unverified | **MANUAL-PENDING** |
| `macos-arm64` | macOS Apple Silicon | no | `.command` planned (not shipped) | schema accepts key only | shared code; Universal 2 decision open (C2) | **MANUAL-PENDING** |

Platform declarations are also machine-readable in `platform_support.platform_declarations()` (`PlatformDeclaration.status` = `local-verified-partial` for windows-x86_64, `manifest-schema-only` for the other five).

---

## 4. Feature matrix - GUI, editor, clipboard, attachments, microphone, ASR/TTS, Ollama, CrewAI, terminal, Git, LSP, MCP, GPU

Cell format: level + verification class. **CI** = automatable in a CI runner for that target (unit/offscreen/static); **HW** = requires real hardware/desktop/clean machine (MANUAL-PENDING regardless of CI).

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
- **Windows ARM64** is the most likely native blocker: CrewAI 1.15.32 hard-requires `chromadb~=1.5.9` and `lancedb>=0.33`, both Rust-built (`maturin`) native wheels. Only `win_amd64` artifacts are evidenced here; ARM64 availability must be confirmed by C2 on the release runner.
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

---
## 5. Tracked-module inventory (every tracked module classified)

Portability classes: **A** = portable pure-Python (stdlib only, no OS calls); **B** = portable code but depends on an external native/runtime component (Qt, SQLite engine, CrewAI native stack, an external executable); **C** = Windows-first assumption that needs a platform adapter (explicit list + evidence below); **D** = packaging/artifact gap owned by C2/C3 (not an application-code portability defect); **T** = tests/docs (portable pytest, but several tests encode Windows assumptions).

### 5.1 Application package `nl_coding_agent/` (89 modules)

| Package | Modules (complete) | Class | Per-target consequence |
|---|---|---|---|
| `nl_coding_agent` (3) | `__init__, cli, main` | C (cli: detached-process flags), A (main) | CLI works via Python on any OS; `cli.py:381-402` Windows-only flags are guarded but the POSIX detached-supervisor fallback is unverified |
| `agents` (5) | `__init__, crew_backend, orchestrator, specs, supervisor_executor` | B | Depends on CrewAI native stack; shared code |
| `app` (8) | `__init__, attachments, debug, lsp, mcp, services, speech, supervisor_service` | B (all); C within `services.py` (command-name policy) | External engines/servers; extraction libs probed at runtime; see feature matrix |
| `core` (21) | `__init__, autonomous_roadmap_planner, backlog, candidate_verification, code_integrity_gate, mission_lock, permissions, promotion, recovery_store, relocation, resource_gate, retention, roadmap, run_control, selfbuild_runner, staging_broker, status, supervisor, task_graph, version, workspace` | A except: C for `status.py` (SystemDrive fallback, guarded), `selfbuild_runner.py` + `supervisor.py` (Windows resume-command strings), B for `candidate_verification.py` (spawns `sys.executable`) | Core orchestration/state is portable Python + SQLite; resume messages are Windows-only text |
| `flows` (7) | `__init__, approval_provider, events, mission_flow, persistence, state, supervisor_flow` | B | Depends on CrewAI Flows/native stack |
| `gui` (5) | `__init__, __main__, main, main_window, theme` | B; C for `theme.py:47` font preference and `main_window.py:503-518` NVIDIA-only GPU probe | Qt GUI is shared; Windows-first cosmetics/telemetry |
| `gui/dialogs` (2) | `__init__, open_project` | B | Qt file dialog; native dialog behaviour MANUAL-PENDING |
| `gui/widgets` (17) | `__init__, agents_panel, autonomy_panel, chat_panel, command_palette, editor_panel, file_viewer, git_panel, inspector_panel, log_panel, models_panel, problems_panel, projects_panel, settings_panel, sidebar, task_board, terminal_panel` | B | Qt widgets; clipboard/drag-drop/terminal paths need real-desktop checks |
| `models` (5) | `__init__, capabilities, model_router, ollama_registry, providers` | B | Ollama CLI/HTTP and OpenAI-compatible HTTP; external services |
| `persistence` (4) | `__init__, database, missions, supervisor_store` | B | SQLite engine is native per platform; schema/code portable |
| `projects` (3) | `__init__, registry, scanner` | A | Portable path scanning |
| `resources` (2) | `__init__, scheduler` | A | Threads only |
| `tools` (7) | `__init__, crew_tools, filesystem, git_tools, registry, shell, verification` | B; C for `shell.py` (OEM codepage via ctypes + `shell=True`), `verification.py` (`python\python.exe` probe), `git_tools.py` (external git) | Tool layer is the main Windows-first surface; see 5.2 |

Installers and CI scripts (owned by C2/C3, not application modules): `installer/` 5 modules (`__init__, bootstrap, fetcher, operations, platform_manifest`), `scripts/` 15 modules, `scripts/ci/` 3 modules in progress.

### 5.2 Class C - Windows-first assumptions (file:line evidence)

| # | File:line | Assumption | Impact on non-Windows | Recommended adapter |
|---|---|---|---|---|
| C1 | `cli.py:381-402` | `_launch_detached` uses `DETACHED_PROCESSCREATE_NEW_PROCESS_GROUP` (guarded by `hasattr`) | POSIX fallback passes no flags and no session detach; child may die with the terminal; unverified | Platform adapter returns POSIX process flags (`start_new_session=True`); C2/C4 to test |
| C2 | `tools/shell.py:19-27` | `ctypes.windll.kernel32.GetOEMCP` for console decoding (guarded `os.name == "nt"`) | POSIX returns `None`, decode falls back to locale/UTF-8: fine | None required; keep guarded |
| C3 | `tools/shell.py:82-91` | `shell=True` for the verification command string | Windows -> cmd.exe; POSIX -> /bin/sh; quoting/availability of the generated command differs and is unverified | Prefer argv-based runner; keep legacy string path for project-agnostic test commands |
| C4 | `tools/verification.py:13-16` | Detects only `<project>/python/python.exe` | POSIX embedded layout/executable differ | Platform adapter for runtime executable discovery (C2 provides per-target runtime layout) |
| C5 | `core/status.py:19-22` | `SystemDrive` fallback for the disk root (guarded `os.name == "nt"`) | POSIX uses `/`: fine | None required |
| C6 | `core/selfbuild_runner.py:158-165` | Resume command text `python\python.exe nl_agent.py ...` | Wrong/backslash command printed on POSIX | Build from `sys.executable` + platform launcher name |
| C7 | `core/supervisor.py:236` and `:1743` | Same Windows resume-command strings | Same | Same adapter |
| C8 | `gui/main_window.py:503-518` | GPU telemetry only via `nvidia-smi`; unknown shows an em dash | No AMD/Metal probing; correct fail-closed behaviour, no CUDA requirement | Optional: inject platform probe from `platform_support.probe_gpu` |
| C9 | `gui/theme.py:47` | Font stack starts with `Segoe UI` (Windows font) | Qt falls back to Inter/sans-serif; cosmetic only | Add per-OS preferred font in tokens (C4 UI polish) |
| C10 | `app/lsp.py:216-220, 267` | File URIs built by replacing \ with `/` and stripping the leading slash | Windows `C:/x` -> `file:///C:/x`; POSIX `/x` -> `file:///x`: both reasonable; untested on POSIX editors | Covered by LSP tests |
| C11 | `app/services.py:443-508` | Terminal deny/allow lists mix POSIX and Windows command names (`del`, `taskkill`, `powershell`, `rm`, `chmod`, ...) | Policy is argv+name based and shell-refusing on both; some OS-native commands are not listed | Keep list per-OS-extensible; CI can test names |
| C12 | root `*.bat` launchers (6 at HEAD; workspace rules now define one root GUI launcher + CLI launchers under `scripts/launchers/`) | `cmd.exe` syntax (`%~dp0`, `setlocal`, `pause`, `%ERRORLEVEL%`) and `python\python.exe` | No Linux/macOS launcher exists in the tracked snapshot | C2 ships `\*.sh`/`*.command` launchers per manifest |
| C13 | `scripts/stage_portable.py` INCLUDED_ROOTS | Only `.bat` launchers + Windows embedded `python/` are staged (HEAD snapshot) | Portable payload is Windows-only by construction | C2 must extend allowlist per target (owned by C2) |
| C14 | `scripts/build_release.py:72-78` | `DEFAULT_PLATFORMS` = windows-x86_64 + linux-x86_64 only; launchers .bat/.sh | 4 of 6 targets have no default release entry | C2 owns extension |
| C15 | `installer/platform_manifest.py:23` | `PLATFORM_KEYS` already accepts all six ids; `detect_platform()` at :218-231 maps win/linux/darwin + x86_64/arm64 | Schema supports six targets; shipped template `installer/platform_manifest.json` declares only 2 | C2 adds runtime/component manifests per target |
| C16 | `installer/operations.py` | Platform-aware cache dirs (:73-83) and forbidden install roots (:122-133); zip extraction rejects symlinks (:220-270) | Code is portable; no macOS/Linux acceptance evidence | C2/C3 test bootstrapper per runner |
| C17 | `scripts/verify_relocation.py` | Scans `*.bat`/`*.ps1` launchers and a hard-coded Windows drive pattern | Gate is Windows-specific (relocation tooling, not product runtime) | Keep Windows-only for this repo; CI C3 owns per-OS checks |

Registry usage: a repo-wide grep for `winreg`/`HKEY_`/`Registry` found **no registry access** in the application; the only `ctypes`/`windll` use is C2 (OEM codepage). Other Windows-only API families found: none beyond the table above.

### 5.3 Tests and launchers

| Group | Files | Class | Notes |
|---|---|---|---|
| Tests | 65 tracked `tests/test_*.py` | T (portable pytest) | GUI tests use `QT_QPA_PLATFORM=offscreen`; a few encode Windows expectations: `test_selfbuild_mode.py` asserts `.bat` launchers, `test_verify_relocation.py` scans `*.bat`/`*.ps1`, `test_bootstrap_installer.py` uses a Windows manifest fixture, `test_crewai_runtime.py` checks site-packages vs vendor. These need per-OS fixtures in C3, not product changes |
| Launchers | 6 root `*.bat` at HEAD | D | Windows-only; C2 provides per-target launchers; workspace rules now define the moved layout |
| Packaging scripts | `scripts/stage_portable.py`, `scripts/build_release.py`, `installer/*` | D | Owned by C2; schema/platform keys partly ready |
| CI scaffolding | `scripts/ci/*` (C3, in progress at snapshot) | D | Not part of this audit; CI success will not be treated as support |

---

## 6. Native / runtime dependency matrix

Wheel evidence is from the local Windows runtime (`importlib.metadata` `WHEEL` Tag): PySide6 `cp310-abi3-win_amd64`; psutil `cp37-abi3-win_amd64`; PyYAML `cp312-cp312-win_amd64`; litellm `cp310-abi3-win_amd64` (maturin, `Root-Is-Purelib: false`); chromadb `cp39-abi3-win_amd64` (maturin); lancedb `cp310-abi3-win_amd64` (maturin); onnxruntime `cp312-cp312-win_amd64`; numpy `cp312-cp312-win_amd64`; crewai `py3-none-any`; pytest/httpx/openai/pydantic `py3-none-any`. Tags: **verified-local** = wheel present and imported here; **MP** = not evidenced (MANUAL-PENDING); **RISK** = likely blocker to confirm; **optional** = absent locally, fail-closed.

| Dependency | Role | windows-x86_64 | windows-arm64 | linux-x86_64 | linux-aarch64 | macos-x86_64 | macos-arm64 | Action / note |
|---|---|---|---|---|---|---|---|---|
| CPython runtime | application runtime | verified-local (3.12.10 MSC x64) | MP/RISK | MP | MP/RISK | MP | MP | C2 provisions a native runtime per target; never reuse Windows runtime |
| PySide6 / Qt 6.12.0 | GUI | verified-local (win_amd64 + Windows Qt plugins) | MP/RISK | MP | MP/RISK | MP | MP | C2 pins per-target PySide6 wheels; Qt plugins differ per OS |
| Qt Multimedia (QAudioSource) | mic/recording | P (plugin present, real mic untested) | MP | MP (needs PulseAudio/PipeWire/ALSA + Qt plugin) | MP | MP (CoreAudio) | MP | MANUAL-PENDING per target |
| SQLite (`sqlite3`) | persistence | verified-local 3.49.1 | MP | MP (ships with CPython) | MP | MP | MP | Bundled with CPython; no app-side native build |
| psutil 7.2.2 | status/leases | verified-local | MP | MP | MP | MP | MP | Has per-OS wheels; C2 pins |
| PyYAML 6.0.3 | config | verified-local | MP | MP | MP | MP | MP | native (C ext); per-OS wheels |
| pydantic / pydantic_core | CrewAI/Flows | verified-local | MP | MP | MP | MP | MP | pydantic-core is Rust-native; ARM64/macOS wheels verified by C2 |
| tokenizers | CrewAI/litellm | verified-local (Rust) | MP/RISK | MP | MP/RISK | MP | MP | native Rust; per-target wheels required |
| crewai 1.15.32 | orchestration | verified-local (import + tests) | MP/RISK | MP | MP | MP | MP | pure wheel, but requires chromadb+lancedb+tokenizers |
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
| PDF/Office extraction libs | attachments | pdfplumber/openpyxl/PIL present; docx/pptx absent | same | per target install | same | same | same | optional, fail-closed |

---

## 7. Per-target blockers and MANUAL-PENDING acceptance checklists

### 7.1 Blockers before any non-Windows claim (owned by C2/C3/C4)

1. **Native runtime provisioning** per target with pinned sha256/size (C2, NL-BP-154/157) - currently only Windows x86_64 has a local runtime.
2. **Native dependency wheel matrix** (CrewAI stack: chromadb/lancedb/onnxruntime/tokenizers/pydantic-core; PySide6/Qt plugins; numpy; tiktoken/aiohttp) - must be resolved and tested on release runners.
3. **Per-target launchers** (`.sh` / `.command` and a Windows ARM64 path) - the tracked snapshot still has Windows `.bat` launchers.
4. **Bootstrapper manifests** for all six targets (template now declares 2) + clean-install test per target.
5. **CI matrix** (C3) for unit/offscreen GUI/bootstrapper only; must never be presented as support.
6. **macOS**: code signing/notarization decision and Universal 2 decision (C2/NL-BP-158).
7. **POSIX semantics**: `shell=True` verification path, detached supervisor, terminal command availability, file permissions/executable bits in packaged launchers.
8. **Real-hardware beta acceptance** (NL-BP-164) recorded per tester: OS/arch, package checksum/version manifest, install path, results.

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

---

## 8. Known limitations of this audit

1. **No network access** was used: PyPI wheel availability for non-Windows targets could not be queried. The audit reports "not evidenced/MANUAL-PENDING" and "wheel-tag risk" instead of inventing availability; C2 must verify on the release runner.
2. **No non-Windows machine or VM** was available: every non-Windows cell is MANUAL-PENDING by construction.
3. **No real hardware checks**: microphone, audio output, GPU, clipboard, DPI/focus are explicitly unverified.
4. **Concurrent workstreams**: installer/, launchers/, .github/ and scripts/ci/ were being modified by C2/C3/C4 during the audit; this document is anchored to committed HEAD `29a0ca1` and must be re-synced after their commits.
5. **No runtime execution of installers** and no self-build/mission run (task constraints).
6. Static classification cannot prove absence of platform bugs; it lists assumptions and the evidence that exists.
7. `scripts/verify_relocation.py` and this repository's operational scripts are Windows-oriented; they are development tooling, not product runtime, and are out of scope for beta packaging.
8. Optional backend availability is machine-specific; the module reports it at runtime and always fails closed rather than silently degrading.

---

## 9. Maintenance and CI synchronisation

- The matrix must be updated in the same change that adds CI evidence or beta-test results; a green CI job is not a support claim (program constraint #7).
- Machine-readable declarations live in `nl_coding_agent/core/platform_support.py`; tests enforce honesty rules (`tests/test_platform_support.py`: only windows-x86_64 may be "verified"; non-Windows features must stay "manual-pending"; GPU never required).
- Future C2 increments update `installer/*` and `scripts/build_release.py`; C3 adds `.github/workflows/*`; C4 adds beta packages/diagnostics. None of those may edit this matrix without recording the evidence date/commit.
- If a target moves from MP to verified, the matrix cell, the module declaration, and the evidence (CI run URL or beta-test record) must change together.

---

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

Tests: `tests/test_platform_support.py`, 31 passed (`python\python.exe -m pytest tests/test_platform_support.py -q -p no:cacheprovider`): all six detect branches, unsupported-host fail-closed, declaration honesty (no verified claims outside Windows x64), injected probes with no process/network execution, GPU no-runner/no-hardware behaviour, macOS no-Metal requirement, JSON-safe reports.

## Appendix B - what this audit did NOT change

- No tracked installer/, .github/, scripts/build_release.py or other tasks' documents were edited (task constraint).
- No commit was created; the Lead reviews and commits `nl_coding_agent/core/platform_support.py`, `tests/test_platform_support.py` and this document.
- No hardware, network, model or autonomous-mission execution was performed by this task.


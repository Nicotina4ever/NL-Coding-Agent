# NL Coding Agent — Universal Autonomy, Research & Mega Suite Factory

> ADDENDUM (2026-10-28). Specification and backlog input, **not** evidence of implemented features. Canonical existing workspace: `K:\AI\NL Coding Agent`. This document complements the current authoritative indexed Blueprint; it does not replace `INDEX.json`, live status, existing acceptance evidence, or existing permission policies. Assign new backlog IDs **only after deduplicating against the current index**.

## 0. Product mission and definition of done

NL Coding Agent is the **universal AI engineering studio** for: (a) creating new software; (b) understanding and safely modifying existing software; (c) consolidating the user's collection of audio/video, AI, dubbing, teleprompter, voice, utilities and coding tools into a modular, installable *NL Mega Suite*; (d) researching current libraries, source code and models; (e) executing and validating multi-agent work; (f) shipping reliable cross-platform releases. All core capabilities are reusable on **arbitrary projects**, not hard-coded to the self-build project or the NL family.

Distinguish **implemented, tested in fixtures, tested with real local models, verified on real hardware, blocked, and planned**. Avoid percentage-complete claims inferred solely from test counts. The user's existing Stage 1–6 initiative continues; this addendum enters the persistent backlog and is scheduled by dependencies, not allowed to interrupt active tasks. No automatic cloud-model usage unless expressly authorized.

**Non-negotiable quality:** evidence outranks agent or reviewer claims; never weaken or replace existing tests to make a gate pass; unchanged production files until candidate verification, durable and reversible source promotions, independent validation, no blanket deletion of user data. SH-07 Tier B stays BLOCKED until actual real-model acceptance gates pass.

## 1. Autonomy, Auto Review and permissions (highest new priority)

### 1.1 Four UX profiles

- **Manual:** each potentially mutating tool operation can require explicit approval; research and read scopes configurable.
- **Assisted:** autonomous planning/read/research/tests, ask for write/install/publish or unusual changes.
- **Trusted Auto Review (recommended for an owned project):** auto-approve routine **authorized** read/write/patch, edit staging, shell tests, local package installation, debugging, approved network research and progress to next mission; code review and independent gates still mandatory. Permissions inherit from a project-scoped durable policy and can be time- or mission-scoped.
- **Full Autonomy / Unrestricted:** explicit user-opt-in mode with broad execution and optional external path permissions. It must accurately display the effective **operating-system rights** and warning that application-level filters cannot reliably sandbox arbitrary shell processes. Encourage use in isolated/disposable workspaces, not claim total reversibility. The user decides any scope and exception; no forced arbitrary max-mission limits.

**Separate controls:** (i) auto-authorization of tools; (ii) automated code review; (iii) background mission continuation; (iv) external network access; (v) cloud LLM usage; (vi) user-file access; (vii) release/deployment. Enabling one must not silently enable the others. Explicit global/persistent approvals may exist but must be inspectable, revocable and auditable.

### 1.2 Permission engine

- Capabilities by operation: `read`, `write`, `execute`, `install-private`, `install-system`, `web-search`, `web-fetch`, `browser-interact`, `download`, `open-external-project`, `model-inference-local`, `model-inference-cloud`, `secret-use`, `git-commit`, `git-push`, `publish-release`, `delete`, `network-write`, `mcp-call`, `microphone`.
- Scopes: tool, process, path, project, external registered resource, host/domain, repository, task, mission, workspace, session, saved policy. `Allow once`, `Allow mission`, `Allow project`, `Always allow matching scope`, `Deny`, `Revoke`.
- **Trusted project**: user may choose full routine access in the chosen workspace without repeated prompts. External SDKs/programs/models can be granted read/execute, read/write or broader rights separately. No assumption that tools outside the project are forbidden forever.
- **Risk-sensitive controls:** publishing public code, exposing secrets, deleting unowned folders, managing credentials, system-wide changes and irreversible remote actions require a separately explicit rule, even if routine edits are auto-approved. If user grants these too, clearly report risk, scope and audit trail.
- **Actual enforcement:** brokered tools, guarded process execution, platform-specific isolation where available, allowed external directories, subprocess inheritance checks, virtual filesystem / worktree-based tests; explicit acknowledgement that prompts and path filters are *not* an OS sandbox. Denial must be fail-closed at the execution boundary.
- Approvals are durable; WAIT_APPROVAL can survive crash/restart. Auto Review results include actor, policy, reasoning, files, tests, diff, security decision and expiry. Human emergency stop accessible from Missions even though autonomous configuration lives in Settings → Advanced → Autonomous Development.
- For network tools, separate **request permission** from **trusting the retrieved page as instructions**. Treat web content, repository text and model cards as untrusted sources, resistant to prompt injection.

### 1.3 Acceptance

Demonstrate: no prompt for dozens of allowed routine actions in Trusted; blocked write outside declared scope; approved external `FFmpeg` execution; persistence and revocation after restart; pending approval expiry/deny; untrusted page prompt injection ignored; Code Reviewer can **reject** even in Full Autonomy; emergency stop, no orphaned workers, correct lock/lease recovery. In Full Autonomy, document realistic limits rather than advertise unbreakable security.

## 2. Research & Web Intelligence Engine

This is an essential programming-agent skill, not a decorative search bar. Audit current MCP/HTTP capabilities before creating new code.

### 2.1 Connectors and readers

- **Web search router:** multiple configurable providers (e.g. Brave/Tavily/Exa/other, provider availability verified at runtime), general/technical/domain/date searches, query reformulation, rank by source reliability, latency/cost/rate-limit policies, manual provider override; no mandatory paid API. When no service is configured, provide offline/known-URL modes and honest limitations.
- **Web page/document reader:** fetch HTTP(S) resources with redirects/canonical URLs, HTML→readable text, code blocks, tables, PDFs, metadata, links, scripts when relevant. Browser automation/Playwright for JavaScript-heavy docs, optionally accessibility tree, screenshots and forms under distinct permissions. Sensible size/time limits, caching and redirect controls; network isolation/SSRF protection including localhost/private IP if not explicitly authorized.
- **GitHub/repository investigator:** official GitHub REST/GraphQL and/or GitHub MCP, branches/tags/commits, API docs, code search, issues/PRs/reviews, changelog/release chronology, workflow configs, license/security disclosures; authenticated private repo operations only through authorized tokens and scopes. Pin discoveries to an actual commit SHA, do not secretly clone or execute untrusted projects.
- **Hugging Face investigator:** official Hub API and metadata/model cards/file manifests/licensing/gates/revisions, model architecture, quantization, RAM/VRAM/disk requirements estimated with uncertainty, alternatives, compatibility with Ollama/llama.cpp/MLX/Transformers where available. Discovery alone never downloads/accepts license/runs code.
- **Ecosystem discovery:** PyPI, crates.io, npm, NuGet, Qt, CMake, official SDK docs and release notes, package compatibility, vulnerability databases, migration guides, license and attribution. Provide primary-source preference and cross-check contested claims.
- **Local-first knowledge store:** referenced excerpts, citation URLs, retrieval timestamp, code/version, SHA/revision, confidence and contradictions; local embeddings via existing services, dedup, cache expiry and refresh, project/team knowledge sharing. Do not retain untrusted code as executable instructions.

### 2.2 Acceptance

Actual network tests distinguish from fixtures: locate current API; verify GitHub issue and related commit; inspect HF model **without checkpoint download**; read JS-rendered docs; cite current versions correctly; test denied network and injection. Preserve retrieved evidence in project research library and make it usable as task context.

## 3. Project Discovery / Genome / Mega Suite Integration Forge

**Multi-root Project Workspace:** index several user-selected directories across drives, Git repos and language ecosystems in **read-only discovery first**; do not recursively scan all of `K:\AI` without consent. Support Python/C++/Rust/JS/Go and specialized DAWs/audio integration as adapters.

### 3.1 Project Genome (actual codebase intelligence)

For each project discover: launch/build entry points, real dependency graph and lockfiles, Python ABI/versions, CUDA/native library requirements, Git state, databases, models and caches, application services, module/API boundaries, tests/coverage, shared UI assets/branding, licenses, target OS, runtime constraints, amount of disk space and known fragile assumptions. Distinguish measured facts from guesses. Store a versioned, searchable map that refreshes incrementally.

### 3.2 Integration Forge (the key Mega Suite differentiator)

- Show a **merge/keep-separate/share-service** matrix comparing NL Audio Tools, AudioLab, Video Suite, VoiceCoach, TakeFlow, VoiceBridge, Audio Matrix, teleprompter and future projects, respecting actual code and ownership.
- Propose an integration architecture **without mandating a monolith**: common launcher/shell, modules/plugins, shared AI model hub, shared runtime where compatible, separate environment when ABI/backend conflicts; communication via documented interfaces and explicit contracts.
- Detect duplicate Python distributions, model checkpoints, FFmpeg, CUDA/ONNX/PyTorch, databases and packages; **do not force a single Python** when incompatible native dependencies require isolation.
- Generate typed module APIs, CLI/IPC adapters, migration shims, contract tests, service boundaries, config migration and rollback plans; gradual strangler migration instead of mass rewrite.
- Preserve functioning tools, user data, project identity, and existing settings; compare functional outcomes on golden fixtures (audio/video reference files, timeline edits etc.) when available and authorized.
- Implement an **Integration Dashboard**: projects, modules, integration readiness, incompatible dependencies, shared services, proposed moves, expected disk savings (actual bytes), test status, upgrade steps and reversible rollout.
- Asset/UI standardization: same design tokens sourced from user's logo/palette and existing NL conventions; no neon/glow on transcription/timeline text. Keep visual style independent of technology choices.
- **Project-specific permission profiles** for working on other user's projects: read-only discovery, approved modification, protected directories and tool paths, remote collaboration/access.

### 3.3 Acceptance

On at least two distinct real projects: produce a fact-backed dependency/integration report, identify one shareable component and one genuine incompatibility, implement a small cross-project integration in staging, run contract tests, prove original tools remain functional, rollback without touching the other project's unsaved work, record useful disk savings without blind deletions.

## 4. Agent Factory, model intelligence, context and quality

- **Dynamic role composition** — Planner/Architect/Developer/Tester/Reviewer/Debugger/Integrator/Release Engineer/Documentation Researcher/Audio or video specialist selected per task; no arbitrary always-on agent count. Select local vs remote only under policy. Support serial role scheduling on 8 GB VRAM and parallel I/O/file-independent tasks when safe.
- **Model competence lab** — Ollama, LM Studio, llama.cpp, MLX/macOS, OpenAI-compatible services and cloud optional; inspect models and verify actual tool/JSON/vision/audio capabilities; benchmark role-specific coding/test/edit/review/repair/research tasks; evidence by model ID, quantization, backend, prompts, options, time, memory and hardware. Never let the evaluated model judge itself exclusively.
- **Maximum Verified Quality profile** — user preference; adjustable speed/quality/resource strategy. 'Ottimizza il mio team' with measured rationale, confidence and manual override; detect GPU contention, choose CPU/wait/other permitted engine; never silently offload GPU tests to the cloud.
- **Context engineering** — repo-aware semantic code search with symbol graph, call graph, dependency-aware retrieval, ranked relevant snippets, context budget/token observability, code citation, timeline of mission decisions, avoid ever-growing chat-only memory.
- **Differential testing/independent verification** — implementation plan → isolated candidate → trusted pre-existing tests → behavioral regression + security scan → independent reviewer (alternative model when useful) → approved promotion. Detect stub/test weakening, flaky tests, truncated output, out-of-scope paths, fake benchmarks, hallucinated evidence. Bounded repair and model escalation, no unverifiable 'APPROVE'. Keep SH-07 Tier B blocked until actually passed.
- **Mission Supervisor** — robust queue, lease, heartbeat, crash-recovery, priorities/dependencies, stop/pause/resume, task delegation, handoff, durable audit; no infinite loop required and no unwarranted fixed mission cap. Periodic check-ins/results available in GUI, not 'come back in 20 minutes' external promises.
- **Research-aware agents** — permissioned web tools + citation-backed findings woven into coding plans, update checks and library model compatibility assessments.

## 5. Complete AI Studio UX and native computer work

- **IDE:** multi-project explorer, code editor + syntax highlighting (CodeMirror/Monaco/Qt choice justified), LSP, DAP, terminal with scoped permissions, Git diff/branches, merge conflict handling, test explorer, debugger, profiling, code actions, quick-open/command palette, MCP/Tool explorer, logs and tasks. No static mocked panels described as implemented features.
- **Unified multimodal conversations:** drag/drop files/folders; Ctrl+V text and screenshot/image data from clipboard (`Win+Shift+S`), attach audio/video/PDF/Office/docs/code, tab-aware context, image/video preview, OCR only when needed, summarize/follow-up, safe file parsing and retention. Verify real model vision/audio capabilities; fallback adapters under permission. Do not silently upload attachments to cloud.
- **Voice assistant:** microphone PTT and optional VAD, Qwen-ASR/Faster-Whisper/Vosk adapters by actual local support, timestamps and editable transcript, optional local TTS, hands-free coding guidance, transcription of logs/media when relevant, cancellation and resource scheduling. Never assume a standard LLM understands raw audio.
- **GUI interaction automation:** optional local computer use (UI accessibility automation, screenshots, tests, click/type) in controlled workspaces; live user approval for cross-project/high-impact UI actions. Separate interactive GUI tests from headless CI tests.
- **Visual quality lab:** screenshot-baseline and human-reviewed UI comparison, DPI/font scaling, accessibility, keyboard-only paths, resize/multimonitor themes, GPU/CPU perf; debug visual regressions without treating images as code correctness proof.
- **Workspace multi-window/session:** work on projects concurrently without conflicting edits; tab/session/handoff; project-specific knowledge and per-workspace model selection.

## 6. Tool Registry and engineering lab

- Discover compilers/SDKs/toolchains/FFmpeg/CMake/Ninja/Git/REAPER integration/DAW SDKs/MCP servers at **approved external paths**. Register capabilities and versions, command schemas, platform availability and health checks; avoid copying installed SDKs into projects.
- **Build/Test Laboratory:** Windows and macOS/Linux targets, per-platform native runtimes, unit/integration/property/fuzz/security tests, UI/hardware manual checkpoints, audio sample golden tests where relevant; reproducibility, runner provenance and precise failure isolation.
- **Dependency and Supply Chain Lab:** dependency graph, SBOM, vulnerability advisories, license obligations, version pinning, signature/hash verification, policy-controlled download/install, test before dependency upgrades, private install root and caching. Audit public Git history and tracked files before first public push.
- **Source control & collaboration:** GitHub/GitLab/remote providers, PR/issue management, branch/worktree isolation, code owner protections, human approvals for public release or credentialed write, conflict detection, code review provenance, optional scheduled CI monitoring.
- **Task-specific automation:** library updates, flaky test tracking, benchmark and ASR model updates, release readiness notifications, controlled periodic research; no unapproved outward notifications or API costs.
- **Plugin/SDK ecosystem:** documented interfaces for adding agent roles, parsers, model backends, tools, research connectors, UI panels, project adapters; third-party skills with provenance and sandbox limitations. Never execute README instructions from retrieved sources by default.

## 7. Storage, portable releases and cross-platform reality

- **Private bootstrapper / online portable** is default: runtime and pinned wheels downloaded with verified hash/size/signatures where available into a user-selected local path, no mandatory global Python/pip/uv/Conda. Offline portable optional and inevitably larger.
- **Per-target builds** for Windows x64/ARM64, Linux x86_64/ARM64, macOS Intel/Apple Silicon; native GUI binaries/wheels/ML backends vary. For macOS use Universal 2 only if all dependencies support it. Tests on actual platform and CPU, not synthetic fixture alone.
- **Source release vs binary release** separate: public GitHub contains clean sources and eligible build artifacts, excludes private state, user files, caches, runtimes, secret histories, heavy models/vendor clones. No upload without owner authorization; changing repo from public to private cannot revoke copies already downloaded.
- **Self-update and fallback**: atomic deployment, verified manifests, previous-app fallback, data schema migrations reversible where possible, no corrupting in-progress tasks. Support integrity repair/uninstall and clear storage reclaim.
- **Mega Suite distribution**: modular installer selecting individual products/modules and inference backends; shared model cache without duplicating weights; optional per-module isolated environment where dependencies conflict. Visible storage plan before installation.

## 8. Operating metrics, readiness and acceptance

- User-visible health dashboard: successful missions, failed gates, regressions prevented, recovery actions, API/network usage, disk/caches by owner, RAM/VRAM and inference speed, model capabilities/confidence. Keep logs privacy-aware with rotation.
- **Cross-app acceptance scenario:** import two unrelated projects, analyze real code, permit known external SDK tool, research verified docs/GitHub/HF, patch only in isolated staging, run trusted baseline tests, promote safe change, use GUI screenshot paste and ASR, handoff mission across restart, build a portable candidate on another target, verify a user-selectable installer path. Keep real hardware acceptance separate from simulated tests.
- **Full Autonomy scenario:** issue a broad goal, configure Trusted or Full scopes, observe several distinct missions without routine prompts; demonstrate independent reviewer rejection and actual bounded repair, no accidental cloud calls, no silent irreversible actions outside the approved policy. Show user how to inspect and revoke saved approvals.
- **Mega Suite integration scenario:** detect duplicate checkpoint and runtime, propose safe consolidation, execute one approved modular integration preserving both original products, build installer modules and validate on real target OS hardware.
- **Ready labels:** `implemented`, `fixture-verified`, `real-model-verified`, `real-hardware-verified`, `manually-pending`, `blocked`, `planned`; never conflate these.

## 9. Suggested dependency order, without blocking active work

1. Finish currently active Stage 6 and mandatory safety gates; do not interrupt unrelated active teammates or force a new status. Snapshot current verified state, and import this **as future backlog input** with traceability.
2. Policy engine / Full Autonomy UX + external tool permissions + independent review guarantees. Reuse existing HITL approvals and permissions. Test on a controlled multi-project workspace.
3. Research engine (URL fetch + docs reader first, then search router, GitHub/HF connectors, browser when necessary) integrated with Tool Registry and agents.
4. Project Genome + multi-root analysis and Integration Forge foundation; product-level contribution to NL Mega Suite.
5. Finish and verify current Studio F1/F2/F3 features, speech, model competence lab and dynamic agent teams; avoid duplicating existing implementations.
6. Cross-project integration, shared dependency planning, UX QA and distribution based on actual measured compatibility.
7. Release acceptance and real hardware/manual checks, CI tests and permitted publication.

Planning must be dependency-driven. Lead may adjust stages and run independent work in parallel when worktrees and shared manifest ownership are truly isolated. Do not invent fixed durations, mission counts, model rankings or percent complete. Never declare the full Mega Suite achieved just because its project manager is operational.

## 10. Backlog import contract

1. Read current authoritative `docs/product-blueprint/INDEX.json`, `docs/PRODUCT_BACKLOG.md`, current state and acceptance evidence before adding anything. Respect existing IDs and review what is already implemented.
2. For each section, map **existing requirement ID** or create unique new ID; give owner, dependency, implementation location, acceptance evidence, permissions and real vs fixture test requirements.
3. Separate **product features, platform engineering tasks, release prerequisites, manual owner decisions**. Mark user-approved policies separately from actual owner permissions; this document grants no deletion/publication/cloud authorization by itself.
4. Update authoritative index/checklists only after a conflict-aware merge; use Git commits and explicit evidence. Preserve older spec history but do not duplicate goals.
5. Continue current Goal without pausing just to acknowledge this document. Queue a concise acceptance checkpoint and continue autonomous authorized work.

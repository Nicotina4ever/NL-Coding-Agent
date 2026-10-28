# Cross-Platform Private Beta Program (NL Coding Agent)

**Status:** in progress (stage-6 extension). Added 2026-10-28 at the repository owner's request.
**Backlog:** NL-BP-152..165 in docs/product-blueprint/INDEX.json and docs/PRODUCT_BACKLOG.md.
**Scope owner:** the repository owner (private beta), executed by the Lead and the agent team.

## Objective

Prepare a reproducible, evidence-based private beta of NL Coding Agent for two trusted external
testers (one Linux, one macOS), extending the existing Windows single-platform distribution work.
The product must remain one shared application codebase with native platform adapters and verified
platform-specific runtime/dependency packages. No cross-platform support is claimed until the
corresponding CI builds and real-hardware beta tests pass.

## Target matrix

| OS | Architecture | Target state |
|---|---|---|
| Windows | x64 | beta candidate + verified bootstrap (existing stage-6b work) |
| Windows | ARM64 | beta candidate where feasible; documented limitations otherwise |
| Linux | x86_64 | beta candidate + verified bootstrap |
| Linux | ARM64 | beta candidate where feasible; documented limitations otherwise |
| macOS | Intel (x86_64) | architecture-specific candidate (or Universal 2 if feasible) |
| macOS | Apple Silicon (arm64) | architecture-specific candidate (or Universal 2 if feasible) |

macOS Universal 2 is preferred only if every native dependency supports both slices; otherwise
separate architecture-specific builds are produced and the decision evidence is recorded.

## Hard constraints

1. One shared application codebase; platform differences live in explicit adapters.
2. Never reuse the Windows embedded Python or Windows binaries on Linux/macOS.
3. No global Python/pip/uv/conda requirement for testers; verified native runtimes download into a
   user-selected location, with offline installation options where supported.
4. Never require CUDA, ROCm, Metal or MLX; optional CPU/GPU/ASR/TTS backends degrade gracefully and
   absent backends are reported clearly.
5. No push to GitHub, no visibility change, no collaborator invites and no release upload unless the
   repository owner explicitly authorizes it. The existing private repository is preserved.
6. No development data, databases, model checkpoints or vendor copies in beta packages.
7. CI success is not platform support: real-hardware and clean-machine items stay **MANUAL-PENDING**
   until tested on actual systems.
8. No destructive actions and no secrets in reports or artifacts.

## Workstreams

| ID | Backlog | Deliverable | Primary files |
|---|---|---|---|
| C1 | NL-BP-152/153/160 | compatibility audit, platform support table, optional-backend probes, compatibility matrix | nl_coding_agent/core/platform_support.py, docs/PLATFORM_COMPATIBILITY_MATRIX.md |
| C2 | NL-BP-154/157/158 | native runtime/dependency manifests for six targets, cross-platform provisioner, Universal 2 decision, optional component declarations | installer/, scripts/build_release.py, docs/BOOTSTRAPPER.md |
| C3 | NL-BP-156/165 | GitHub Actions CI matrix (Windows/Linux/macOS, x64+ARM64 where feasible), headless GUI smoke, bootstrapper checks, artifact provenance | .github/workflows/, scripts/ci/, docs/CI.md |
| C4 | NL-BP-159/161/163 | beta packages/checksums/versioned manifests/install instructions; GitHub Issues feedback workflow; redacted opt-in diagnostic report; owner authorization runbook | .github/ISSUE_TEMPLATE/, scripts/diagnostic_report.py, docs/BETA_TESTING.md, docs/PRIVATE_BETA_RUNBOOK.md |
| C5 | NL-BP-162 | tracked-files and Git-history audit for secrets/private DBs/runtimes/vendor copies/heavy outputs; redacted report | scripts/audit_release_secrets.py, docs/SECRETS_AUDIT.md |

## Phases and gates

1. **C1 audit + platform abstraction** - evidence-based matrix and fail-closed unsupported handling.
2. **C2 native runtimes and provisioner** - per-target manifests; fake-artifact tests; no fabricated
   hashes; real manifests/hashes are produced on a release runner.
3. **C3 CI matrix** - unit/integration/headless GUI/bootstrapper checks per runner; static guards that
   no workflow can push, publish, change visibility or invite collaborators.
4. **C4 beta workflow and packages** - non-developer instructions, checksums, issue templates,
   redacted diagnostics, owner-only upload runbook.
5. **C5 pre-upload audit** - secrets/history/repository audit must be green before any upload decision.
6. **Owner authorization gate** - repository owner reviews audit + packages and explicitly authorizes
   any upload/publish; otherwise everything remains local/artifacts only.
7. **Real-hardware beta acceptance** - testers run install + GUI + platform-specific checks; results
   are recorded separately from CI. Until then, all corresponding matrix rows are MANUAL-PENDING.

## Beta acceptance evidence (to be recorded, never assumed)

- package identity, platform/arch, checksum and version manifest per tester;
- installation result (non-default path) and first-run experience without global Python;
- headless GUI/CLI checks vs real desktop interaction (focus, DPI, clipboard screenshot, drag/drop);
- optional backends: Ollama models, CUDA/ROCm/Metal/MLX availability, ASR/TTS engines and devices;
- editor/terminal/Git/LSP/MCP feature status on each platform;
- failures/bugs reported through the beta issue template; diagnostic reports reviewed for redaction.

## Current state (2026-10-28)

- Windows: stage-6b portable candidate r2 exists and passed a non-default-path smoke; release
  acceptance remains PARTIAL with manual-pending hardware items.
- Linux/macOS: not yet built or tested; no support is claimed.
- Backlog, program plan and acceptance criteria extension are committed; implementation tasks C1-C5
  are in progress.

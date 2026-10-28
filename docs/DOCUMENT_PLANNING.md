# Document Planning (D4) - generation, versions, approval

**Status:** backend/service/CLI implementation for NL-BP-221. Document-derived plans are
draft planning artifacts only: they never execute commands, create or start missions, call
models, install anything or edit documents. Approval is metadata and does not approve
future edits.

## Generation

Documents are ingested read-only from a project root (or explicit paths) and processed by:

1. requirement extraction - objectives, requirements, constraints (technical/legal/owner),
   dependencies and acceptance criteria with document/item provenance, explicit vs
   inferred labels and confidence;
2. reconciliation - stale/duplicate/version conflicts, obsolete paths/commands, missing
   documentation, contradictory requirements and doc-vs-source/dependency/test/Git
   evidence;
3. plan generation - a deterministic draft with:
   - title and objective (from documented objective or explicit argument; empty when no
     documented objective exists - never fabricated);
   - acceptance criteria with provenance;
   - one milestone per requirement/constraint/dependency item, each with stable key,
     priority (P0-P3), dependencies (document order), risk summary (matching findings),
     validation strategy, provenance refs (document IDs/paths/URLs/excerpt hashes/line/
     offset) and explicit/inferred label;
   - all reconciliation findings as explicit risks; high-severity contradictions/version
     conflicts as blockers;
   - limitations/unknowns (empty corpus, missing evidence, bounded corpus, no acceptance);
   - a deterministic plan hash over the plan content.

An empty/unknown corpus produces an honest draft with an empty objective, no fabricated
requirements and explicit limitations/unknowns.

## Persistence and lifecycle

Additive SQLite tables (idempotent schema, no destructive migration):

- document_plans: project id/root, title, objective, status
  (draft/approved/rejected), current_version, plan_hash, timestamps.
- document_plan_versions: one immutable snapshot per version with milestones,
  acceptance, provenance, risks, blockers, limitations/unknowns, rationale, diff,
  plan hash, approval/rejection metadata, timestamp.

Lifecycle: generate -> draft v1 -> edit (required reason) -> new immutable version, diff,
status draft -> approve current version with reason -> approved metadata + approved
snapshot; reject current version with reason -> rejected metadata. An edit after
approval/rejection creates a NEW draft version; old approval/rejection metadata stays on
its immutable snapshot.

Validation on edit: non-empty milestone list, unique keys, non-empty titles, P0-P3
priorities, existing dependencies, no self/cyclic dependencies, bounded item counts.
Every edit requires a non-empty rationale and records added/removed/changed milestones.
Approval requires the current version and a reason; approval/rejection write
source=document_planning audit events. There is no execution/mission start.

## AppServices

- docs_plan_generate(...) - bounded corpus discovery + generation (project root, explicit
  paths, or an already-ingested corpus/documents; no network).
- docs_plan_list/get/versions - plan and immutable version inspection.
- docs_plan_edit(plan_id, milestones, rationale, ...) - new draft version.
- docs_plan_approve(plan_id, version=None, reason=..., approver=user)
- docs_plan_reject(plan_id, version=None, reason=..., rejected_by=user)
All return structured ok/error envelopes; no stack traces.

## CLI (pre-model, NL_DATA_DIR-isolated)

    python\nl_agent.py docs plan . --json
    python\nl_agent.py docs plans --json
    python\nl_agent.py docs plans 1 --json
    python\nl_agent.py docs plan-edit 1 --file plan.json --reason "new evidence" --json
    python\nl_agent.py docs plan-approve 1 --reason "reviewed" --json
    python\nl_agent.py docs plan-reject 1 --reason "not acceptable" --json

Use --file - to read edit plan JSON from stdin. Exit codes: 0 success, 1
validation/not-found/lifecycle, 2 usage/argparse/malformed JSON. There are no execution
flags. Plan generation and inspection work without a model config; document content is
UNTRUSTED and is never executed. Approval does not execute or start anything.

## Table/API reference

Core module: nl_coding_agent/core/doc_planning.py
(generate_plan, edit_plan, approve_plan, reject_plan, list_plans, get_plan,
list_plan_versions, get_plan_version).

Tests: tests/test_doc_planning.py, tests/test_app_services_document_planning.py,
tests/test_docs_planning_cli.py (temp fixtures, no network/model/mission).

## Limits

- Planning is heuristic and document-driven; plans are drafts, not implementation truth.
- No execution, mission creation, worker control, code edits, verification of claims,
  model summarization or automatic conflict resolution.
- Dynamic document content is untrusted data; generated titles/text mirror source excerpts
  and are not instructions. Human review remains required before any use.
- Current CLI/text output is intentionally concise; JSON is the machine-readable surface.
- GUI integration is out of scope for this increment.

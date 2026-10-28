# Goal Completion Verification (stage-8 G3, NL-BP-215)

Independent verification layer that decides whether a goal's original objective and
acceptance criteria are satisfied by source-backed evidence. It is deliberately not
model-judged, not consensus-based and never marks a goal complete.

Module: nl_coding_agent/core/goal_verification.py
Table: goal_verifications (additive, idempotent; created by database.init_db)

## Why

A goal must never be marked complete from its own checklist, plan, agent summary or
reviewer claim. Completion is verified against the original objective/acceptance
criteria with evidence that can be traced to a test run, command result, artifact
hash, reviewer approval, user confirmation or file check. Outstanding requirements,
blockers, regressions, stale evidence and unverified manual items are reported
explicitly; deliberate false-completion claims are rejected and persisted.

## Evidence types

Every evidence item has type, source, result, timestamp and trust. Supported types:

| Type | Meaning | Typical source |
|---|---|---|
| test | Automated test/verification run | pytest/junit/verification_runs |
| command | Command with exit code | shell/build command |
| artifact | Artifact/hash/file produced or checked | release zip, generated file |
| reviewer_approval | Independent reviewer decision | reviewer handoff/approval record |
| user_confirmation | Explicit user/owner confirmation | user decision event |
| file_check | Filesystem/content assertion | read-only file check |

Trusted levels: trusted, verified, system, human, user, owner, external.
All other values (model, ai, llm, agent, self, claim, untrusted, unknown, missing)
are untrusted: they are recorded in the report but never satisfy a criterion.
Evidence without a source is rejected (source-backed evidence only). Command/test
exit codes are authoritative: a non-zero exit code fails the evidence even if a
result field claims success.

Evidence sources:
1. Caller-supplied items (dicts or EvidenceItem objects). Items may target a
   criterion with criterion_ids; otherwise they match by evidence type.
2. Recorded application evidence linked to the goal through goal_missions:
   - verification_runs: command, exit code and passed -> test/command evidence;
   - mission_evidence: kind/payload/path/sha256 -> reviewer/user/test/command/artifact;
   - task_attempts: status -> command evidence of what was executed;
   - the mission reviewer verdict (APPROVE/REJECT) -> reviewer_approval evidence.
3. Milestone evidence_refs: declared refs are accepted only if they carry type,
   source and a trusted trust level (default trust is untrusted, so declarations
   alone never satisfy a criterion).

## Acceptance criteria and required evidence

Criteria can be supplied explicitly (preferred) or fall back to the goal's stored
acceptance_criteria strings. A criterion supports:

- id (unique) and text (required);
- required_evidence_types: one or more of the evidence types above. All required
  types must have passing trusted evidence; missing types block verification. An
  empty list means any one trusted source-backed evidence item is enough.
- stale_after_s (optional): maximum age of evidence; older evidence is stale.
- required_result: currently pass (the only meaningful completion result).

The verifier never uses a criterion whose evidence is only the goal's own text.

## Per-criterion statuses

- verified: every required evidence type has fresh trusted passing evidence and no
  contradicting evidence.
- partial: some required types passed, others are missing.
- missing: no relevant evidence (or no evidence of the required types).
- unknown: evidence exists but is untrusted/model-only, has an unknown result, or
  freshness cannot be established.
- stale: only stale evidence matches the criterion.
- contradicted: at least one fresh trusted evidence item failed.

## Goal verdicts

- verified: every criterion verified.
- partial: no contradiction, at least one criterion verified/partial, not all verified.
- contradicted: at least one criterion contradicted (wins over partial/verified).
- unverified: no criteria (objective not decomposed into verifiable criteria), or
  all criteria missing/unknown/stale without any verified/partial criterion.

A goal with no acceptance criteria is unverified by design: completion cannot be
verified against an empty checklist.

## Self-declaration and false completion

- self_declared is true when the caller claims completion or the goal already has
  status completed.
- self_declared_mismatch (and false_completion in the report) is true when a
  self-declared completion is not independently verified.
- detect_false_completion() scans completed goals and reports:
  - completed_without_verification when no goal_verifications record exists;
  - contradicted_criteria / unverified_criteria / partial_criteria when the latest
    record is not verified.
- summarize_outstanding() returns the latest outstanding criteria and blockers.
- Detection and verification never change goal status; goals.py/GoalService remain
  the only lifecycle owner. No auto-completion exists in this module.

## Persistence

goal_verifications (append-only) stores: goal_id, verifier_version, verdict,
criteria results JSON, evidence refs JSON, blockers JSON, self_declared,
self_declared_mismatch, goal_status at verification, created_at. Schema creation is
additive/idempotent; existing goals and mission history are untouched. Stored
evidence refs contain type/source/result/timestamp/trust/hash/path/exit code/actor
and matched criterion ids; raw commands and arbitrary context/details are not
persisted (a command SHA-256 is stored instead when a command was supplied).

API: ensure_schema, verify_goal, record_goal_verification, get_goal_verification,
list_goal_verifications, latest_goal_verification, summarize_outstanding,
detect_false_completion, find_false_completions.

verify_goal(goal_id, evidence=None, criteria=None, stale_after_s=None,
self_declared_complete=None, include_stored_evidence=True, persist=True) returns the
structured report (criteria, evidence refs, blockers, verdict, record_id) and
persists it by default.

## Limits and remaining integration

- Human/real external evidence is still required. The verifier only judges records;
  it does not execute tests, run commands or create artifacts. A verified verdict
  says the supplied/recorded evidence satisfies the criteria, not that the product
  is correct in the absolute.
- It is not wired into GoalService, app services, CLI or GUI yet (no goal-status
  mutation and no auto-completion). Integration must call verify_goal before any
  completion transition and surface blockers; false-completion detection must be
  exposed read-only.
- Existing staged-candidate/oracle/reviewer/promotion gates remain authoritative for
  mission-level evidence; the goal verifier reuses their recorded outputs and does
  not duplicate or weaken them.
- Evidence quality depends on provenance: DB records are trusted system evidence,
  but a compromised or buggy recorder could still record false evidence. Manual
  items remain MANUAL-PENDING until real evidence exists.
- No model judgment, no LLM consensus, no network access and no model run is used by
  the verifier or its tests.

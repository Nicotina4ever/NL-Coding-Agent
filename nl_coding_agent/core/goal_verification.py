"""Independent goal completion verification and false-completion detection (NL-BP-215).

This module verifies a goal against its original objective/acceptance criteria using
source-backed evidence. It is deliberately not model-judged and never marks a goal
complete: goals.py/GoalService remain the only lifecycle owner, and this module
never mutates goal status.

Evidence sources
----------------
* caller-supplied evidence items (tests, commands with exit codes, artifact hashes,
  reviewer approvals, user confirmations, file checks) with type/source/result/
  timestamp/trust;
* already-recorded application evidence for linked missions:
  verification_runs (command + exit code + passed), mission_evidence (kind,
  hash/path/payload), task_attempts (status) and the mission reviewer verdict;
* milestone evidence_refs declared on the goal/milestones (trust must be stated;
  declared refs default to untrusted and therefore never satisfy a criterion).

Every criterion must have at least one trusted, source-backed piece of evidence.
Required evidence types per criterion are enforced explicitly; model/agent claims,
untrusted sources, stale evidence and contradictory results never count as positive
evidence. Results are deterministic for identical inputs and stored rows.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Iterable, Mapping

from nl_coding_agent.persistence import database
from nl_coding_agent.persistence import goal_store
from nl_coding_agent.persistence import missions as missions_store
from nl_coding_agent.persistence import supervisor_store

VERIFIER_VERSION = "goal-verifier/1.0"

VERIFIED = "verified"
UNVERIFIED = "unverified"
PARTIAL = "partial"
CONTRADICTED = "contradicted"
VERDICTS: tuple[str, ...] = (VERIFIED, UNVERIFIED, PARTIAL, CONTRADICTED)

CRITERION_VERIFIED = "verified"
CRITERION_PARTIAL = "partial"
CRITERION_MISSING = "missing"
CRITERION_UNKNOWN = "unknown"
CRITERION_STALE = "stale"
CRITERION_CONTRADICTED = "contradicted"
CRITERION_STATUSES: tuple[str, ...] = (
    CRITERION_VERIFIED, CRITERION_PARTIAL, CRITERION_MISSING,
    CRITERION_UNKNOWN, CRITERION_STALE, CRITERION_CONTRADICTED,
)

EVIDENCE_TEST = "test"
EVIDENCE_COMMAND = "command"
EVIDENCE_ARTIFACT = "artifact"
EVIDENCE_REVIEWER = "reviewer_approval"
EVIDENCE_USER = "user_confirmation"
EVIDENCE_FILE_CHECK = "file_check"
EVIDENCE_TYPES: tuple[str, ...] = (
    EVIDENCE_TEST, EVIDENCE_COMMAND, EVIDENCE_ARTIFACT,
    EVIDENCE_REVIEWER, EVIDENCE_USER, EVIDENCE_FILE_CHECK,
)

EVIDENCE_TYPE_ALIASES = {
    "tests": EVIDENCE_TEST,
    "test_run": EVIDENCE_TEST,
    "pytest": EVIDENCE_TEST,
    "cmd": EVIDENCE_COMMAND,
    "command_run": EVIDENCE_COMMAND,
    "shell": EVIDENCE_COMMAND,
    "hash": EVIDENCE_ARTIFACT,
    "artifact_hash": EVIDENCE_ARTIFACT,
    "file": EVIDENCE_ARTIFACT,
    "reviewer": EVIDENCE_REVIEWER,
    "review": EVIDENCE_REVIEWER,
    "approval": EVIDENCE_REVIEWER,
    "reviewer_approval": EVIDENCE_REVIEWER,
    "user": EVIDENCE_USER,
    "user_confirm": EVIDENCE_USER,
    "user_confirmation": EVIDENCE_USER,
    "file_check": EVIDENCE_FILE_CHECK,
    "filesystem_check": EVIDENCE_FILE_CHECK,
}

TRUSTED_LEVELS: frozenset[str] = frozenset({
    "trusted", "verified", "system", "human", "user", "owner", "external",
})
UNTRUSTED_LEVELS: frozenset[str] = frozenset({
    "untrusted", "model", "ai", "llm", "agent", "self", "claim", "claimed",
    "unknown", "missing", "none",
})

RESULT_PASS = "pass"
RESULT_FAIL = "fail"
RESULT_STALE = "stale"
RESULT_UNKNOWN = "unknown"
RESULT_VALUES: tuple[str, ...] = (
    RESULT_PASS, RESULT_FAIL, RESULT_STALE, RESULT_UNKNOWN,
)
PASS_RESULTS = frozenset({"pass", "passed", "ok", "success", "succeeded",
                          "verified", "true", "1", "approve", "approved"})
FAIL_RESULTS = frozenset({"fail", "failed", "error", "contradicted", "rejected",
                          "reject", "false", "0"})
STALE_RESULTS = frozenset({"stale", "expired", "outdated", "old"})

MAX_EVIDENCE_ITEMS = 500
MAX_CRITERIA = 100


class GoalVerificationError(RuntimeError):
    """Base error for goal verification."""


class GoalNotFoundError(GoalVerificationError):
    """Raised when the goal to verify does not exist."""


# --------------------------------------------------------------------------- #
# Evidence and criteria models
# --------------------------------------------------------------------------- #

def normalize_evidence_type(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Evidence type is required")
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in EVIDENCE_TYPES:
        return normalized
    if normalized in EVIDENCE_TYPE_ALIASES:
        return EVIDENCE_TYPE_ALIASES[normalized]
    raise ValueError(
        "Unknown evidence type: " + repr(value) + "; expected one of "
        + ", ".join(EVIDENCE_TYPES)
    )


def normalize_evidence_result(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in PASS_RESULTS:
        return RESULT_PASS
    if text in FAIL_RESULTS:
        return RESULT_FAIL
    if text in STALE_RESULTS:
        return RESULT_STALE
    return RESULT_UNKNOWN


def normalize_trust(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in TRUSTED_LEVELS:
        return text
    if text in UNTRUSTED_LEVELS:
        return text
    return "untrusted"


def _is_trusted(item: "EvidenceItem") -> bool:
    return item.trust in TRUSTED_LEVELS


def _sha_of(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8", "replace")).hexdigest()


@dataclass(frozen=True)
class EvidenceItem:
    """One source-backed piece of evidence considered by the verifier."""

    type: str
    source: str
    result: str = RESULT_UNKNOWN
    timestamp: str = ""
    trust: str = "untrusted"
    sha256: str = ""
    path: str = ""
    exit_code: int | None = None
    command: str = ""
    actor: str = ""
    criterion_ids: tuple[str, ...] = ()
    details: dict = field(default_factory=dict)

    def to_ref(self, *, accepted: bool,
               rejection_reason: str = "",
               matched_criteria: Iterable[str] = ()) -> dict:
        """Persistable, secret-free evidence reference (no raw command/details)."""
        ref = {
            "type": self.type,
            "source": self.source,
            "result": self.result,
            "timestamp": self.timestamp,
            "trust": self.trust,
            "accepted": bool(accepted),
            "sha256": self.sha256,
            "path": self.path,
            "exit_code": self.exit_code,
            "actor": self.actor,
            "criterion_ids": list(self.criterion_ids),
            "matched_criteria": sorted(set(matched_criteria)),
        }
        if self.command:
            ref["command_sha256"] = _sha_of(self.command)
        if rejection_reason:
            ref["rejection_reason"] = str(rejection_reason)
        return ref


_EVIDENCE_FIELD_ALIASES = {
    "type": "type",
    "kind": "type",
    "evidence_type": "type",
    "source": "source",
    "source_id": "source",
    "result": "result",
    "status": "result",
    "timestamp": "timestamp",
    "time": "timestamp",
    "created_at": "timestamp",
    "trust": "trust",
    "trust_level": "trust",
    "sha256": "sha256",
    "hash": "sha256",
    "artifact_hash": "sha256",
    "path": "path",
    "file": "path",
    "exit_code": "exit_code",
    "exit": "exit_code",
    "command": "command",
    "actor": "actor",
    "criterion_id": "criterion_ids",
    "criterion": "criterion_ids",
    "criterion_ids": "criterion_ids",
    "criteria": "criterion_ids",
    "ok": "result",
    "passed": "result",
    "success": "result",
    "origin": "source",
    "evidence_source": "source",
}


def normalize_evidence(item: object) -> EvidenceItem:
    """Normalize caller evidence (EvidenceItem or mapping) with fail-closed trust."""
    if isinstance(item, EvidenceItem):
        data = {
            "type": item.type, "source": item.source, "result": item.result,
            "timestamp": item.timestamp, "trust": item.trust,
            "sha256": item.sha256, "path": item.path,
            "exit_code": item.exit_code, "command": item.command,
            "actor": item.actor, "criterion_ids": item.criterion_ids,
            "details": dict(item.details),
        }
    elif isinstance(item, Mapping):
        data = {}
        details = {}
        for key, value in item.items():
            name = _EVIDENCE_FIELD_ALIASES.get(str(key).strip().lower(), None)
            if name is None:
                details[str(key)] = value
            else:
                data[name] = value
        data["details"] = details
    else:
        raise ValueError("Evidence item must be a mapping or EvidenceItem: " + repr(item))

    evidence_type = normalize_evidence_type(data.get("type"))
    source = str(data.get("source") or "").strip()
    if not source:
        raise ValueError("Evidence source is required (source-backed evidence only)")
    result = normalize_evidence_result(data.get("result"))
    trust = normalize_trust(data.get("trust"))
    criterion_ids = data.get("criterion_ids") or ()
    if isinstance(criterion_ids, str):
        criterion_ids = (criterion_ids,)
    exit_code = data.get("exit_code")
    if exit_code is not None:
        try:
            exit_code = int(exit_code)
        except (TypeError, ValueError):
            raise ValueError("exit_code must be an integer") from None
        # Recorded exit codes are authoritative for command/test evidence.
        if exit_code != 0:
            result = RESULT_FAIL
        elif result == RESULT_UNKNOWN:
            result = RESULT_PASS
    return EvidenceItem(
        type=evidence_type,
        source=source[:500],
        result=result,
        timestamp=str(data.get("timestamp") or "")[:100],
        trust=trust,
        sha256=str(data.get("sha256") or "")[:128],
        path=str(data.get("path") or "")[:1000],
        exit_code=exit_code,
        command=str(data.get("command") or "")[:4000],
        actor=str(data.get("actor") or "")[:200],
        criterion_ids=tuple(str(value)[:100] for value in criterion_ids)[:50],
        details=dict(data.get("details") or {}),
    )


@dataclass(frozen=True)
class AcceptanceCriterion:
    """One acceptance criterion with explicit required evidence types."""

    id: str
    text: str
    required_evidence_types: tuple[str, ...] = ()
    required_result: str = RESULT_PASS
    stale_after_s: int | None = None


_CRITERION_FIELD_ALIASES = {
    "id": "id",
    "criterion_id": "id",
    "text": "text",
    "description": "text",
    "title": "text",
    "required_evidence_types": "required_evidence_types",
    "required_types": "required_evidence_types",
    "required_evidence": "required_evidence_types",
    "evidence_types": "required_evidence_types",
    "types": "required_evidence_types",
    "required_result": "required_result",
    "expected_result": "required_result",
    "stale_after_s": "stale_after_s",
    "stale_after_seconds": "stale_after_s",
    "max_age_s": "stale_after_s",
    "stale_after": "stale_after_s",
}


def normalize_criterion(item: object, *, index: int = 0) -> AcceptanceCriterion:
    if isinstance(item, AcceptanceCriterion):
        criterion_id = item.id
        text = item.text
        required = item.required_evidence_types
        required_result = item.required_result
        stale_after = item.stale_after_s
    elif isinstance(item, str):
        criterion_id = "AC-" + str(index + 1)
        text = item.strip()
        required = ()
        required_result = RESULT_PASS
        stale_after = None
    elif isinstance(item, Mapping):
        data = {}
        for key, value in item.items():
            name = _CRITERION_FIELD_ALIASES.get(str(key).strip().lower(), None)
            if name is None:
                raise ValueError("Unknown criterion field: " + repr(key))
            data[name] = value
        if not data.get("text"):
            raise ValueError("Criterion text is required")
        criterion_id = str(data.get("id") or ("AC-" + str(index + 1))).strip()
        text = str(data["text"]).strip()
        required = data.get("required_evidence_types") or ()
        if isinstance(required, str):
            required = (required,)
        required_result = normalize_evidence_result(
            data.get("required_result") or RESULT_PASS)
        stale_after = data.get("stale_after_s")
    else:
        raise ValueError("Criterion must be a string, mapping or AcceptanceCriterion")
    if not criterion_id:
        raise ValueError("Criterion id is required")
    if not text:
        raise ValueError("Criterion text is required")
    if len(text) > 4000 or len(criterion_id) > 100:
        raise ValueError("Criterion text/id is too long")
    normalized_types: list[str] = []
    for evidence_type in required:
        normalized = normalize_evidence_type(evidence_type)
        if normalized not in normalized_types:
            normalized_types.append(normalized)
    if stale_after is not None:
        try:
            stale_after = int(stale_after)
        except (TypeError, ValueError):
            raise ValueError("stale_after_s must be an integer number of seconds") from None
        if stale_after <= 0:
            raise ValueError("stale_after_s must be positive")
    return AcceptanceCriterion(
        id=criterion_id,
        text=text,
        required_evidence_types=tuple(normalized_types),
        required_result=required_result,
        stale_after_s=stale_after,
    )


def normalize_criteria(criteria: Iterable | None, *,
                       allow_empty: bool = True) -> list[AcceptanceCriterion]:
    if criteria is None:
        return []
    if isinstance(criteria, (str, Mapping, AcceptanceCriterion)):
        criteria = [criteria]
    normalized: list[AcceptanceCriterion] = []
    seen: set[str] = set()
    for index, item in enumerate(list(criteria)):
        criterion = normalize_criterion(item, index=index)
        if criterion.id in seen:
            raise ValueError("Duplicate criterion id: " + criterion.id)
        seen.add(criterion.id)
        normalized.append(criterion)
        if len(normalized) > MAX_CRITERIA:
            raise ValueError("Too many acceptance criteria (max " + str(MAX_CRITERIA) + ")")
    if not normalized and not allow_empty:
        raise ValueError("At least one acceptance criterion is required")
    return normalized


# --------------------------------------------------------------------------- #
# Evidence loading from recorded application state
# --------------------------------------------------------------------------- #

def _mission_evidence_type(kind: str, sha256: str, path: str) -> str:
    lowered = str(kind or "").strip().lower()
    if "review" in lowered or "approval" in lowered:
        return EVIDENCE_REVIEWER
    if "user" in lowered or "confirm" in lowered:
        return EVIDENCE_USER
    if "test" in lowered or "pytest" in lowered or "verify" in lowered:
        return EVIDENCE_TEST
    if "command" in lowered or "shell" in lowered or "run" in lowered:
        return EVIDENCE_COMMAND
    if "file" in lowered or "artifact" in lowered or "hash" in lowered:
        return EVIDENCE_ARTIFACT
    if sha256 or path:
        return EVIDENCE_ARTIFACT
    return EVIDENCE_COMMAND


def _result_from_payload(payload: Mapping | None) -> str:
    payload = dict(payload or {})
    for key in ("result", "status", "passed", "ok", "success", "exit_code"):
        if key in payload and payload[key] is not None:
            value = payload[key]
            if key in ("passed", "ok", "success") and isinstance(value, bool):
                return RESULT_PASS if value else RESULT_FAIL
            if key == "exit_code":
                try:
                    return RESULT_PASS if int(value) == 0 else RESULT_FAIL
                except (TypeError, ValueError):
                    return RESULT_UNKNOWN
            return normalize_evidence_result(value)
    return RESULT_UNKNOWN


def load_stored_evidence(goal_id: int) -> list[EvidenceItem]:
    """Load recorded mission/task/verification evidence linked to the goal (read-only)."""
    items: list[EvidenceItem] = []
    goal = goal_store.get_goal(int(goal_id))
    if goal is None:
        raise GoalNotFoundError("goal not found: " + str(goal_id))
    for milestone in goal_store.list_milestones(int(goal_id)):
        for ref in milestone.get("evidence_refs") or []:
            if not isinstance(ref, Mapping):
                continue
            if not ref.get("type") and not ref.get("kind"):
                continue
            if not ref.get("source"):
                continue
            try:
                items.append(normalize_evidence(dict(ref)))
            except ValueError:
                continue

    for link in goal_store.list_goal_missions(int(goal_id)):
        mission_id = link.get("mission_id")
        if mission_id is None:
            continue
        mission = missions_store.get_mission(int(mission_id)) or {}
        verdict = str(mission.get("review_verdict") or "").strip().upper()
        if verdict:
            passed = verdict in ("APPROVE", "APPROVED", "PASS", "PASSED")
            items.append(EvidenceItem(
                type=EVIDENCE_REVIEWER,
                source="db:missions:" + str(mission_id) + ":review_verdict",
                result=RESULT_PASS if passed else RESULT_FAIL,
                timestamp=str(mission.get("finished_at")
                              or mission.get("updated_at") or ""),
                trust="system",
                actor=str(mission.get("reviewer_role") or ""),
            ))

        for run in missions_store.get_verification_runs(int(mission_id)):
            command = str(run.get("command") or "")
            verification_type = (
                EVIDENCE_TEST
                if ("test" in command.lower() or "pytest" in command.lower())
                else EVIDENCE_COMMAND
            )
            passed = bool(run.get("passed"))
            items.append(EvidenceItem(
                type=verification_type,
                source="db:verification_runs:" + str(run.get("id")),
                result=RESULT_PASS if passed else RESULT_FAIL,
                timestamp=str(run.get("created_at") or ""),
                trust="system",
                exit_code=(int(run.get("exit_code"))
                           if run.get("exit_code") is not None else None),
                command=command,
            ))

        for evidence in supervisor_store.list_evidence(int(mission_id)):
            payload = evidence.get("payload") or {}
            sha256 = str(evidence.get("sha256") or payload.get("sha256") or "")
            path = str(evidence.get("path") or payload.get("path") or "")
            items.append(EvidenceItem(
                type=_mission_evidence_type(
                    evidence.get("kind"), sha256, path),
                source="db:mission_evidence:" + str(evidence.get("id")),
                result=_result_from_payload(payload),
                timestamp=str(evidence.get("created_at") or ""),
                trust="system",
                sha256=sha256,
                path=path,
            ))

        for attempt in missions_store.get_task_attempts(int(mission_id)):
            status = str(attempt.get("status") or "").strip().lower()
            if status in ("success", "succeeded", "completed", "passed", "ok"):
                result = RESULT_PASS
            elif status in ("failed", "error", "blocked", "cancelled"):
                result = RESULT_FAIL
            else:
                result = RESULT_UNKNOWN
            items.append(EvidenceItem(
                type=EVIDENCE_COMMAND,
                source="db:task_attempts:" + str(attempt.get("id")),
                result=result,
                timestamp=str(attempt.get("finished_at")
                              or attempt.get("started_at") or ""),
                trust="system",
                actor=str(attempt.get("agent_role") or ""),
            ))
    return _dedupe_evidence(items)


def _dedupe_evidence(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[tuple] = set()
    unique: list[EvidenceItem] = []
    for item in items:
        key = (item.type, item.source, item.sha256, item.timestamp, item.result)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #

def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _freshness(item: EvidenceItem, stale_after_s: int | None) -> str:
    """Return fresh/stale/unknown for one trusted evidence item."""
    if item.result == RESULT_STALE:
        return RESULT_STALE
    if not stale_after_s:
        return "fresh"
    parsed = _parse_timestamp(item.timestamp)
    if parsed is None:
        return RESULT_UNKNOWN
    age = (datetime.now() - parsed).total_seconds()
    return RESULT_STALE if age > stale_after_s else "fresh"


def _matches_criterion(item: EvidenceItem, criterion: AcceptanceCriterion) -> bool:
    if item.criterion_ids:
        return criterion.id in item.criterion_ids
    if criterion.required_evidence_types:
        return item.type in criterion.required_evidence_types
    return item.type in EVIDENCE_TYPES


def _evaluate_criterion(
    criterion: AcceptanceCriterion,
    evidence: list[EvidenceItem],
    *,
    default_stale_after_s: int | None,
) -> dict:
    relevant = [item for item in evidence if _matches_criterion(item, criterion)]
    trusted = [item for item in relevant if _is_trusted(item)]
    untrusted = [item for item in relevant if not _is_trusted(item)]
    threshold = (criterion.stale_after_s
                 if criterion.stale_after_s is not None else default_stale_after_s)
    fresh: list[EvidenceItem] = []
    stale: list[EvidenceItem] = []
    timing_unknown: list[EvidenceItem] = []
    blockers: list[dict] = []
    for item in trusted:
        freshness = _freshness(item, threshold)
        if freshness == "fresh":
            fresh.append(item)
        elif freshness == RESULT_STALE:
            stale.append(item)
        else:
            timing_unknown.append(item)

    refs = [
        item.to_ref(
            accepted=_is_trusted(item) and item in fresh,
            rejection_reason=(
                "" if _is_trusted(item)
                else "untrusted/model evidence ignored"
            ),
            matched_criteria=(criterion.id,),
        )
        for item in relevant
    ]

    status = CRITERION_MISSING
    if not trusted:
        if untrusted:
            status = CRITERION_UNKNOWN
            blockers.append({
                "code": "no_trusted_evidence",
                "detail": "Only untrusted/model evidence was supplied; it cannot "
                          "verify a goal.",
            })
        else:
            blockers.append({
                "code": "missing_evidence",
                "detail": "No source-backed evidence matches this criterion.",
            })
    else:
        contradictions = [item for item in fresh if item.result == RESULT_FAIL]
        if contradictions:
            status = CRITERION_CONTRADICTED
            blockers.append({
                "code": "contradicted",
                "detail": "Contradicting evidence: " + ", ".join(
                    item.source for item in contradictions[:10]),
            })
        elif not fresh:
            if stale and not timing_unknown:
                status = CRITERION_STALE
                blockers.append({
                    "code": "stale_evidence",
                    "detail": "Only stale evidence matches this criterion: "
                              + ", ".join(item.source for item in stale[:10]),
                })
            else:
                status = CRITERION_UNKNOWN
                blockers.append({
                    "code": "unverifiable_freshness",
                    "detail": "Evidence freshness could not be established "
                              "(missing/invalid timestamp or unknown result).",
                })
        else:
            required = list(criterion.required_evidence_types)
            passed = [item for item in fresh if item.result == RESULT_PASS]
            passed_types = {item.type for item in passed}
            present_types = {item.type for item in fresh}
            if required:
                missing_types = [name for name in required if name not in passed_types]
                if not missing_types:
                    status = CRITERION_VERIFIED
                elif passed:
                    status = CRITERION_PARTIAL
                    blockers.append({
                        "code": "missing_required_evidence_types",
                        "detail": "Missing passing evidence type(s): "
                                  + ", ".join(missing_types),
                    })
                elif present_types.intersection(required):
                    status = CRITERION_UNKNOWN
                    blockers.append({
                        "code": "required_evidence_not_passing",
                        "detail": "Present required evidence did not pass: "
                                  + ", ".join(sorted(present_types.intersection(required))),
                    })
                else:
                    status = CRITERION_MISSING
                    blockers.append({
                        "code": "missing_required_evidence_types",
                        "detail": "No evidence of required type(s): "
                                  + ", ".join(missing_types),
                    })
            else:
                if passed:
                    status = CRITERION_VERIFIED
                else:
                    status = CRITERION_UNKNOWN
                    blockers.append({
                        "code": "no_passing_evidence",
                        "detail": "Evidence exists but none has a passing result.",
                    })
    for item in stale:
        blockers.append({
            "code": "stale_evidence_source",
            "detail": "Stale evidence ignored: " + item.source,
        })
    for item in timing_unknown:
        blockers.append({
            "code": "unknown_evidence_timestamp",
            "detail": "Unknown timestamp or freshness for: " + item.source,
        })
    return {
        "criterion_id": criterion.id,
        "text": criterion.text,
        "status": status,
        "verified": status == CRITERION_VERIFIED,
        "required_evidence_types": list(criterion.required_evidence_types),
        "stale_after_s": criterion.stale_after_s,
        "evidence": refs,
        "blockers": blockers,
    }


def _goal_verdict(criteria_results: list[dict]) -> str:
    if not criteria_results:
        return UNVERIFIED
    statuses = [result["status"] for result in criteria_results]
    if any(status == CRITERION_CONTRADICTED for status in statuses):
        return CONTRADICTED
    if all(status == CRITERION_VERIFIED for status in statuses):
        return VERIFIED
    if any(status in (CRITERION_VERIFIED, CRITERION_PARTIAL) for status in statuses):
        return PARTIAL
    return UNVERIFIED


def _goal_criteria(goal: dict) -> list[AcceptanceCriterion]:
    return normalize_criteria(list(goal.get("acceptance_criteria") or []))


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #

def ensure_schema() -> tuple[str, ...]:
    """Create/migrate the additive goal_verifications table; returns its columns."""
    conn = database.init_db()
    try:
        rows = conn.execute("PRAGMA table_info(goal_verifications)").fetchall()
        return tuple(str(row["name"]) for row in rows)
    finally:
        conn.close()


def _record_report(report: dict) -> int:
    ensure_schema()
    conn = database.get_connection()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO goal_verifications
                    (goal_id, verifier_version, verdict, criteria_json,
                     evidence_refs_json, blockers_json, self_declared,
                     self_declared_mismatch, goal_status, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(report["goal_id"]),
                    str(report["verifier_version"]),
                    str(report["verdict"]),
                    json.dumps(report.get("criteria") or [], ensure_ascii=False,
                               sort_keys=True),
                    json.dumps(report.get("evidence_refs") or [], ensure_ascii=False,
                               sort_keys=True),
                    json.dumps(report.get("blockers") or [], ensure_ascii=False,
                               sort_keys=True),
                    1 if report.get("self_declared") else 0,
                    1 if report.get("self_declared_mismatch") else 0,
                    str(report.get("goal_status") or ""),
                    str(report["created_at"]),
                ),
            )
            return int(cursor.lastrowid)
    finally:
        conn.close()


def _report_row(row) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    for column, key in (
        ("criteria_json", "criteria"),
        ("evidence_refs_json", "evidence_refs"),
        ("blockers_json", "blockers"),
    ):
        raw = data.pop(column, "[]")
        try:
            data[key] = json.loads(raw or "[]")
        except (TypeError, ValueError):
            data[key] = []
    data["self_declared"] = bool(data.get("self_declared"))
    data["self_declared_mismatch"] = bool(data.get("self_declared_mismatch"))
    data["verified"] = data.get("verdict") == VERIFIED
    return data


def record_goal_verification(report: Mapping) -> int:
    """Persist one verification report (append-only; never changes goal status)."""
    required = ("goal_id", "verifier_version", "verdict", "criteria",
                "evidence_refs", "blockers", "created_at")
    missing = [name for name in required if name not in report]
    if missing:
        raise GoalVerificationError(
            "report is missing fields: " + ", ".join(missing))
    return _record_report(dict(report))


def get_goal_verification(verification_id: int) -> dict | None:
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM goal_verifications WHERE id=?",
            (int(verification_id),),
        ).fetchone()
        return _report_row(row)
    finally:
        conn.close()


def list_goal_verifications(goal_id: int, *, limit: int = 20) -> list[dict]:
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM goal_verifications WHERE goal_id=? ORDER BY id DESC LIMIT ?",
            (int(goal_id), max(1, min(int(limit), 500))),
        ).fetchall()
        return [_report_row(row) for row in rows]
    finally:
        conn.close()


def latest_goal_verification(goal_id: int) -> dict | None:
    records = list_goal_verifications(goal_id, limit=1)
    return records[0] if records else None


# --------------------------------------------------------------------------- #
# Public verification API
# --------------------------------------------------------------------------- #

def verify_goal(
    goal_id: int,
    evidence: Iterable | None = None,
    criteria: Iterable | None = None,
    *,
    stale_after_s: int | None = None,
    self_declared_complete: bool | None = None,
    include_stored_evidence: bool = True,
    persist: bool = True,
    verifier_version: str = VERIFIER_VERSION,
) -> dict:
    """Independently verify goal completion from source-backed evidence.

    Never marks the goal complete and never changes goal status: it returns and
    (optionally) persists a structured verification report.
    """
    goal = goal_store.get_goal(int(goal_id))
    if goal is None:
        raise GoalNotFoundError("goal not found: " + str(goal_id))
    normalized_criteria = (normalize_criteria(criteria)
                           if criteria is not None else _goal_criteria(goal))
    caller_evidence = [normalize_evidence(item) for item in (evidence or [])]
    if len(caller_evidence) > MAX_EVIDENCE_ITEMS:
        raise ValueError("Too many evidence items (max " + str(MAX_EVIDENCE_ITEMS) + ")")
    stored_evidence = load_stored_evidence(int(goal_id)) if include_stored_evidence else []
    all_evidence = _dedupe_evidence(list(caller_evidence) + list(stored_evidence))
    if len(all_evidence) > MAX_EVIDENCE_ITEMS:
        all_evidence = all_evidence[:MAX_EVIDENCE_ITEMS]

    if self_declared_complete is None:
        self_declared = str(goal.get("status")) == "completed"
    else:
        self_declared = bool(self_declared_complete)

    criteria_results: list[dict] = []
    blockers: list[dict] = []
    if not normalized_criteria:
        blockers.append({
            "code": "no_acceptance_criteria",
            "detail": "The goal has no acceptance criteria; completion cannot be "
                      "verified against its original objective without explicit "
                      "criteria.",
        })
    for criterion in normalized_criteria:
        result = _evaluate_criterion(
            criterion, all_evidence, default_stale_after_s=stale_after_s)
        criteria_results.append(result)
        for blocker in result.get("blockers") or []:
            blockers.append({
                "criterion_id": result["criterion_id"],
                "code": blocker.get("code"),
                "detail": blocker.get("detail"),
            })

    verdict = _goal_verdict(criteria_results)
    self_declared_mismatch = bool(self_declared and verdict != VERIFIED)
    if self_declared_mismatch:
        blockers.append({
            "code": "self_declared_completion_mismatch",
            "detail": "Completion was self-declared but independent verification "
                      "did not return verified.",
        })

    accepted_sources = {
        item.source for item in all_evidence if _is_trusted(item)
    }
    matched_criteria: dict[str, list[str]] = {}
    for item in all_evidence:
        for criterion in normalized_criteria:
            if _matches_criterion(item, criterion):
                matched_criteria.setdefault(item.source, []).append(criterion.id)
    evidence_refs = [
        item.to_ref(
            accepted=(_is_trusted(item) and item.source in accepted_sources),
            rejection_reason=(
                "" if _is_trusted(item)
                else "untrusted/model evidence ignored"
            ),
            matched_criteria=matched_criteria.get(item.source, ()),
        )
        for item in all_evidence
    ]

    report = {
        "goal_id": int(goal_id),
        "goal_title": str(goal.get("title") or ""),
        "goal_objective": str(goal.get("objective") or ""),
        "goal_status": str(goal.get("status") or ""),
        "verifier_version": str(verifier_version),
        "verdict": verdict,
        "criteria": criteria_results,
        "evidence_refs": evidence_refs,
        "blockers": blockers,
        "self_declared": bool(self_declared),
        "self_declared_mismatch": bool(self_declared_mismatch),
        "false_completion": bool(self_declared_mismatch),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "record_id": None,
        "goal_status_mutated": False,
    }
    if persist:
        report["record_id"] = record_goal_verification(report)
    return report


def summarize_outstanding(goal_id: int) -> dict:
    """Return outstanding criteria/blockers from the latest verification record."""
    goal = goal_store.get_goal(int(goal_id))
    if goal is None:
        raise GoalNotFoundError("goal not found: " + str(goal_id))
    latest = latest_goal_verification(int(goal_id))
    if latest is None:
        criteria = _goal_criteria(goal)
        return {
            "goal_id": int(goal_id),
            "verdict": None,
            "record_id": None,
            "verified": False,
            "false_completion": False,
            "outstanding_criteria": [
                {"criterion_id": criterion.id, "text": criterion.text,
                 "status": CRITERION_MISSING}
                for criterion in criteria
            ],
            "blockers": [{
                "code": "no_verification_record",
                "detail": "No goal verification record exists yet.",
            }],
            "created_at": None,
        }
    outstanding = [
        {
            "criterion_id": criterion.get("criterion_id"),
            "text": criterion.get("text"),
            "status": criterion.get("status"),
        }
        for criterion in latest.get("criteria") or []
        if criterion.get("status") != CRITERION_VERIFIED
    ]
    return {
        "goal_id": int(goal_id),
        "verdict": latest.get("verdict"),
        "record_id": latest.get("id"),
        "verified": latest.get("verdict") == VERIFIED,
        "false_completion": latest.get("verdict") != VERIFIED,
        "outstanding_criteria": outstanding,
        "blockers": list(latest.get("blockers") or []),
        "created_at": latest.get("created_at"),
    }


def detect_false_completion(
    goal_id: int | None = None,
    *,
    project_id: int | None = None,
    limit: int = 500,
) -> dict:
    """Detect completed goals lacking a verified independent record.

    A goal marked completed without a verification record, or whose latest record
    is unverified/partial/contradicted, is reported as a false completion. This
    function never changes goal status.
    """
    if goal_id is not None:
        goal = goal_store.get_goal(int(goal_id))
        if goal is None:
            raise GoalNotFoundError("goal not found: " + str(goal_id))
        goals = [goal] if str(goal.get("status")) == "completed" else []
    else:
        goals = goal_store.list_goals(
            project_id=project_id, status="completed",
            limit=max(1, min(int(limit), 500)))
    findings: list[dict] = []
    for goal in goals:
        record = latest_goal_verification(int(goal["id"]))
        if record is None:
            findings.append({
                "goal_id": int(goal["id"]),
                "goal_title": str(goal.get("title") or ""),
                "goal_status": str(goal.get("status")),
                "reason_code": "completed_without_verification",
                "verdict": None,
                "record_id": None,
                "blockers": [{
                    "code": "no_verification_record",
                    "detail": "Goal is marked completed but no independent goal "
                              "verification record exists.",
                }],
                "self_declared_mismatch": True,
            })
            continue
        if record.get("verdict") != VERIFIED:
            findings.append({
                "goal_id": int(goal["id"]),
                "goal_title": str(goal.get("title") or ""),
                "goal_status": str(goal.get("status")),
                "reason_code": str(record.get("verdict")) + "_criteria",
                "verdict": record.get("verdict"),
                "record_id": record.get("id"),
                "blockers": list(record.get("blockers") or []),
                "self_declared_mismatch": bool(
                    record.get("self_declared_mismatch")),
            })
    return {
        "checked_goals": len(goals),
        "false_completions": findings,
        "count": len(findings),
        "ok": not findings,
    }


def find_false_completions(
    goal_id: int | None = None,
    *,
    project_id: int | None = None,
    limit: int = 500,
) -> list[dict]:
    """Convenience list view of detect_false_completion() findings."""
    return detect_false_completion(
        goal_id, project_id=project_id, limit=limit)["false_completions"]


# Compatibility aliases (explicit names above remain the primary API).
record_verification = record_goal_verification
list_verifications = list_goal_verifications
get_latest_verification = latest_goal_verification
detect_false_completions = detect_false_completion
summarize_outstanding_criteria = summarize_outstanding

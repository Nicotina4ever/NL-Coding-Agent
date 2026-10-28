"""Deterministic document-driven plan generation and version lifecycle (D4, NL-BP-221).

Plan content is derived from untrusted documents; generation never executes,
starts missions, installs or calls models. Approval is metadata only and never
approves future edits: every edit creates a new draft version.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from nl_coding_agent.core.doc_reconciliation import reconcile as _reconcile
from nl_coding_agent.core.requirement_extraction import extract_requirements

PLAN_STATUSES = ("draft", "approved", "rejected")
PRIORITIES = ("P0", "P1", "P2", "P3")
DEFAULT_DB = None
MAX_MILESTONES = 100
MAX_RISKS = 100
MAX_EXCERPT = 400


class DocPlanningError(ValueError):
    code = "doc-planning-error"


class DocPlanValidationError(DocPlanningError):
    code = "validation"


class DocPlanNotFoundError(DocPlanningError):
    code = "not_found"


class DocPlanLifecycleError(DocPlanningError):
    code = "lifecycle"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", "replace")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _text(value, limit=4000, *, allow_empty=False) -> str:
    text = str(value or "").strip()
    if not text and not allow_empty:
        raise DocPlanValidationError("required text is empty")
    return text[:limit]


def _connect(db_path=None):
    from nl_coding_agent.persistence.database import init_db
    return init_db(Path(db_path) if db_path else None)


def _audit(event_kind: str, message: str, payload: dict) -> None:
    try:
        from nl_coding_agent.persistence.database import init_db, log_event
        conn = init_db()
        try:
            log_event(conn, message, source="document_planning",
                      payload=_canonical(payload),
                      event_kind=event_kind)
        finally:
            conn.close()
    except Exception:
        pass


def _report_documents(corpus) -> list[dict]:
    if corpus is None:
        return []
    if hasattr(corpus, "documents"):
        docs = corpus.documents
    elif isinstance(corpus, Mapping):
        docs = corpus.get("documents") or []
    else:
        docs = corpus
    result = []
    for raw in docs or ():
        if hasattr(raw, "to_dict"):
            raw = raw.to_dict()
        if isinstance(raw, Mapping):
            item = dict(raw)
            digest = str(item.get("sha256") or "")
            item["document_id"] = ("doc-" + (digest[:16] if re.fullmatch(
                r"[0-9a-f]{64}", digest) else _sha(str(
                    item.get("path") or item.get("title") or ""))[:16]))
            result.append(item)
    return result


def _item_provenance(item) -> dict:
    data = item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
    return {"item_id": data.get("id"), "kind": data.get("kind"),
            "document_id": data.get("document_id"),
            "source_path": data.get("source_path"),
            "source_url": data.get("source_url"),
            "document_title": data.get("document_title"),
            "document_sha256": data.get("document_sha256"),
            "excerpt": data.get("excerpt", "")[:MAX_EXCERPT],
            "excerpt_sha256": data.get("excerpt_sha256"),
            "line": data.get("line"), "offset": data.get("offset"),
            "label": data.get("label"), "confidence": data.get("confidence")}


def _finding_ref(finding) -> dict:
    data = finding.to_dict() if hasattr(finding, "to_dict") else dict(finding or {})
    return {"finding_id": data.get("id"), "category": data.get("category"),
            "severity": data.get("severity"), "title": data.get("title"),
            "detail": data.get("detail", "")[:500],
            "documents": [{"document_id": item.get("document_id"),
                           "path": item.get("path"), "url": item.get("url")}
                          for item in data.get("documents") or []],
            "counterparts": [{"document_id": item.get("document_id"),
                              "path": item.get("path")}
                             for item in data.get("counterparts") or []],
            "excerpt": data.get("excerpt", "")[:MAX_EXCERPT],
            "excerpt_sha256": data.get("excerpt_sha256")}


def _priority_for(item: Mapping, finding_refs: list) -> str:
    kind = item.get("kind")
    explicit = bool(item.get("explicit"))
    if kind == "constraint" and item.get("constraint_kind") in ("legal", "owner"):
        return "P0"
    if kind == "constraint" and explicit:
        return "P0"
    if kind == "requirement" and explicit:
        return "P1"
    if kind == "dependency" and explicit:
        return "P2"
    return "P2" if explicit else "P3"


def _validate_milestones(milestones) -> list[dict]:
    if not isinstance(milestones, (list, tuple)):
        raise DocPlanValidationError("milestones must be a list")
    if not milestones:
        raise DocPlanValidationError("milestones must not be empty")
    if len(milestones) > MAX_MILESTONES:
        raise DocPlanValidationError("too many milestones")
    result = []
    keys = []
    for index, raw in enumerate(milestones):
        if not isinstance(raw, Mapping):
            raise DocPlanValidationError("milestone #" + str(index + 1)
                                         + " must be an object")
        key = str(raw.get("key") or "").strip()
        if not key:
            raise DocPlanValidationError("milestone key is required")
        if key in keys:
            raise DocPlanValidationError("duplicate milestone key: " + key)
        keys.append(key)
        title = _text(raw.get("title"), 300)
        priority = str(raw.get("priority") or "P1").upper()
        if priority not in PRIORITIES:
            raise DocPlanValidationError("invalid milestone priority: " + priority)
        dependencies = raw.get("dependencies") or []
        if not isinstance(dependencies, (list, tuple)):
            raise DocPlanValidationError("milestone dependencies must be a list")
        deps = [str(item) for item in dependencies]
        if key in deps:
            raise DocPlanValidationError("milestone cannot depend on itself: " + key)
        result.append({"key": key, "title": title,
                       "description": str(raw.get("description") or "")[:4000],
                       "priority": priority, "dependencies": deps,
                       "risk": str(raw.get("risk") or "")[:2000],
                       "validation_strategy": str(
                           raw.get("validation_strategy") or "")[:2000],
                       "provenance": list(raw.get("provenance") or [])[:100],
                       "inferred": bool(raw.get("inferred", False)),
                       "label": str(raw.get("label") or
                                    ("inferred" if raw.get("inferred") else "explicit"))})
    known = set(keys)
    for milestone in result:
        for dep in milestone["dependencies"]:
            if dep not in known:
                raise DocPlanValidationError("missing milestone dependency: " + dep)
    graph = {item["key"]: set(item["dependencies"]) for item in result}
    visiting, visited = set(), set()

    def visit(node):
        if node in visiting:
            raise DocPlanValidationError("milestone dependency cycle")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, ()):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return result


def _milestone_diff(old: list[dict], new: list[dict]) -> dict:
    old_by_key = {item["key"]: item for item in old or ()}
    new_by_key = {item["key"]: item for item in new or ()}
    added = [key for key in new_by_key if key not in old_by_key]
    removed = [key for key in old_by_key if key not in new_by_key]
    changed = []
    for key in sorted(set(old_by_key) & set(new_by_key)):
        fields = {}
        for field in ("title", "description", "priority", "dependencies",
                      "risk", "validation_strategy", "label"):
            if old_by_key[key].get(field) != new_by_key[key].get(field):
                fields[field] = {"from": old_by_key[key].get(field),
                                 "to": new_by_key[key].get(field)}
        if fields:
            changed.append({"key": key, "fields": fields})
    return {"added": added, "removed": removed, "changed": changed,
            "counts": {"added": len(added), "removed": len(removed),
                       "changed": len(changed),
                       "unchanged": len(set(old_by_key) & set(new_by_key)) - len(changed)}}


def _plan_payload(objective, title, milestones, acceptance_criteria,
                  provenance, risks, blockers, limitations, unknowns,
                  project_root, project_id=None, corpus_hash="",
                  extraction_hash="", reconciliation_hash="") -> dict:
    payload = {
        "schema_version": 1, "tool": "document_plan",
        "title": title, "objective": objective,
        "milestones": milestones,
        "acceptance_criteria": acceptance_criteria,
        "provenance": provenance, "risks": risks, "blockers": blockers,
        "limitations": limitations, "unknowns": unknowns,
        "project_root": str(project_root or ""),
        "project_id": project_id,
        "corpus_hash": corpus_hash,
        "extraction_hash": extraction_hash,
        "reconciliation_hash": reconciliation_hash,
        "untrusted_marker": "UNTRUSTED: plan derived from document data; never executed",
        "executed": False,
    }
    payload["plan_hash"] = _sha(_canonical(payload))
    return payload


def generate_plan(corpus, project_root=None, *, reconciliation=None,
                  extraction=None, title=None, objective=None,
                  project_id=None, persist: bool = True, db_path=None,
                  generator: str = "document_corpus") -> dict:
    docs = _report_documents(corpus)
    extraction = extraction or extract_requirements(corpus)
    reconciliation = reconciliation or _reconcile(corpus, project_root)
    limitations = list(extraction.limitations) + list(reconciliation.limitations)
    unknowns = list(extraction.unknowns) + list(reconciliation.unknowns)
    objective_text = str(objective or "").strip()
    if not objective_text:
        objective_items = [item for item in extraction.items
                           if item.kind == "objective"]
        if objective_items:
            explicit = [item for item in objective_items if item.explicit]
            objective_text = (explicit[0] if explicit else objective_items[0]).text
        else:
            limitations.append("no documented objective found; objective left empty")
    title_text = str(title or "").strip()
    if not title_text:
        titles = [str(doc.get("title") or "") for doc in docs if doc.get("title")]
        title_text = titles[0] if titles else "Document-derived plan"
    acceptance_items = [item for item in extraction.items
                        if item.kind == "acceptance"]
    acceptance_criteria = [{"text": item.text, "label": item.label,
                            "explicit": item.explicit,
                            "confidence": item.confidence,
                            "provenance": [_item_provenance(item)]}
                           for item in acceptance_items[:50]]
    if not acceptance_criteria:
        limitations.append("no explicit acceptance criteria found")
    risk_refs = [_finding_ref(item) for item in reconciliation.findings]
    blockers = [ref for ref in risk_refs
                if ref.get("severity") == "high" or ref.get("category") in (
                    "contradictory_requirement", "version_conflict")]
    items = [item for item in extraction.items
             if item.kind in ("requirement", "constraint", "dependency")]
    milestones = []
    last_key_by_doc = {}
    for item in items[:MAX_MILESTONES]:
        key = "m-" + _sha(str(item.id) + "|" + item.document_id)[:16]
        provenance = _item_provenance(item)
        matching_risks = []
        for finding in reconciliation.findings:
            finding_docs = [str(entry.get("document_id") or "")
                            for entry in (finding.documents if hasattr(finding, "documents")
                                          else ())] if hasattr(finding, "documents") else []
            if item.document_id in finding_docs:
                matching_risks.append(_finding_ref(finding))
        dependencies = []
        previous = last_key_by_doc.get(item.document_id)
        if previous:
            dependencies.append(previous)
        last_key_by_doc[item.document_id] = key
        validation = ("Verify against the cited document evidence; no command, "
                      "mission or model execution is performed.")
        milestones.append({
            "key": key, "title": item.text[:300],
            "description": (item.section or "")[:1000],
            "priority": _priority_for(item.to_dict(), risk_refs),
            "dependencies": dependencies,
            "risk": "; ".join(str(entry.get("title") or "") for entry in matching_risks[:5]),
            "validation_strategy": validation,
            "provenance": [provenance],
            "inferred": (not item.explicit),
            "label": item.label,
        })
    if not items:
        limitations.append("no requirement/constraint/dependency items were generated")
    provenance = []
    for item in extraction.items[:300]:
        provenance.append(_item_provenance(item))
    payload = _plan_payload(
        objective_text, title_text, milestones, acceptance_criteria,
        provenance, risk_refs[:MAX_RISKS], blockers[:MAX_RISKS],
        list(dict.fromkeys(limitations)), list(dict.fromkeys(unknowns)),
        project_root, project_id, extraction.corpus_hash,
        extraction.report_hash, reconciliation.report_hash)
    if persist:
        stored = _persist_plan(payload, project_root=project_root,
                               project_id=project_id, db_path=db_path)
        payload.update({"plan_id": stored["plan_id"],
                        "version": stored["version"],
                        "status": stored["status"],
                        "run_id": stored.get("run_id")})
    payload["ok"] = True
    payload["executed"] = False
    return payload


def _persist_plan(plan: dict, *, project_root=None, project_id=None,
                  db_path=None) -> dict:
    now = _now()
    conn = _connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO document_plans (project_id, project_root, title, "
                "objective, status, current_version, plan_hash, created_at, "
                "updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (int(project_id) if project_id is not None else None,
                 str(project_root or ""), plan["title"], plan["objective"],
                 "draft", 1, plan["plan_hash"], now, now))
            plan_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO document_plan_versions (plan_id, version, "
                "milestones_json, acceptance_criteria_json, provenance_json, "
                "risks_json, blockers_json, limitations_json, unknowns_json, "
                "rationale, diff_json, plan_hash, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (plan_id, 1, _canonical(plan["milestones"]),
                 _canonical(plan["acceptance_criteria"]),
                 _canonical(plan["provenance"]), _canonical(plan["risks"]),
                 _canonical(plan["blockers"]), _canonical(plan["limitations"]),
                 _canonical(plan["unknowns"]), "generated from corpus",
                 _canonical({"added": [item["key"] for item in plan["milestones"]],
                             "removed": [], "changed": [],
                             "counts": {"added": len(plan["milestones"]),
                                        "removed": 0, "changed": 0,
                                        "unchanged": 0}}), plan["plan_hash"], now))
    finally:
        conn.close()
    _audit("document_plan_generated", "Document plan generated",
           {"plan_id": plan_id, "plan_hash": plan["plan_hash"]})
    return {"plan_id": plan_id, "version": 1, "status": "draft"}


def _version_from_row(row) -> dict:
    data = dict(row)
    for source, target in (("milestones_json", "milestones"),
                           ("acceptance_criteria_json", "acceptance_criteria"),
                           ("provenance_json", "provenance"),
                           ("risks_json", "risks"), ("blockers_json", "blockers"),
                           ("limitations_json", "limitations"),
                           ("unknowns_json", "unknowns"),
                           ("diff_json", "diff")):
        raw = data.pop(source, "[]")
        try:
            data[target] = json.loads(raw)
        except (TypeError, ValueError):
            data[target] = []
    return data


def _plan_from_row(row, *, include_versions=False, db_path=None) -> dict:
    data = dict(row)
    versions = list_plan_versions(data["id"], db_path=db_path)
    data["versions_count"] = len(versions)
    current = next((item for item in versions
                    if int(item["version"]) == int(data.get("current_version"))),
                   None)
    data["current"] = current
    if include_versions:
        data["versions"] = versions
    return data


def list_plans(*, project_id=None, project_root=None, status=None,
               limit=100, db_path=None) -> list[dict]:
    query = "SELECT * FROM document_plans WHERE 1=1"
    params = []
    if project_id is not None:
        query += " AND project_id=?"
        params.append(int(project_id))
    if project_root:
        query += " AND project_root=?"
        params.append(str(project_root))
    if status:
        query += " AND status=?"
        params.append(str(status))
    query += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))
    conn = _connect(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
        return [_plan_from_row(row, db_path=db_path) for row in rows]
    finally:
        conn.close()


def get_plan(plan_id: int, *, include_versions=True, db_path=None) -> dict:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM document_plans WHERE id=?",
                           (int(plan_id),)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise DocPlanNotFoundError("document plan not found: " + str(plan_id))
    return _plan_from_row(row, include_versions=include_versions,
                          db_path=db_path)


def list_plan_versions(plan_id: int, *, db_path=None) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM document_plan_versions WHERE plan_id=? "
            "ORDER BY version ASC", (int(plan_id),)).fetchall()
    finally:
        conn.close()
    return [_version_from_row(row) for row in rows]


def get_plan_version(plan_id: int, version: int, *, db_path=None) -> dict:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM document_plan_versions WHERE plan_id=? AND version=?",
            (int(plan_id), int(version))).fetchone()
    finally:
        conn.close()
    if row is None:
        raise DocPlanNotFoundError("document plan version not found")
    return _version_from_row(row)


def edit_plan(plan_id: int, milestones, rationale: str, *,
              title=None, objective=None, db_path=None) -> dict:
    reason = _text(rationale, 4000)
    plan = get_plan(plan_id, db_path=db_path)
    validated = _validate_milestones(milestones)
    current = get_plan_version(plan_id, plan["current_version"], db_path=db_path)
    diff = _milestone_diff(current.get("milestones") or [], validated)
    new_version = int(plan["current_version"]) + 1
    provenance = []
    for item in validated:
        provenance.extend(item.get("provenance") or [])
    now = _now()
    new_title = str(title or plan["title"])
    new_objective = str(objective or plan["objective"])
    payload = _plan_payload(new_objective, new_title, validated,
                            current.get("acceptance_criteria") or [],
                            provenance, current.get("risks") or [],
                            current.get("blockers") or [],
                            current.get("limitations") or [],
                            current.get("unknowns") or [],
                            plan.get("project_root"))
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO document_plan_versions (plan_id, version, "
                "milestones_json, acceptance_criteria_json, provenance_json, "
                "risks_json, blockers_json, limitations_json, unknowns_json, "
                "rationale, diff_json, plan_hash, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (int(plan_id), new_version, _canonical(validated),
                 _canonical(current.get("acceptance_criteria") or []),
                 _canonical(provenance), _canonical(current.get("risks") or []),
                 _canonical(current.get("blockers") or []),
                 _canonical(current.get("limitations") or []),
                 _canonical(current.get("unknowns") or []), reason,
                 _canonical(diff), payload["plan_hash"], now))
            conn.execute(
                "UPDATE document_plans SET current_version=?, title=?, objective=?, "
                "status='draft', plan_hash=?, updated_at=? WHERE id=?",
                (new_version, new_title, new_objective, payload["plan_hash"],
                 now, int(plan_id)))
    finally:
        conn.close()
    _audit("document_plan_edited", "Document plan edited",
           {"plan_id": int(plan_id), "version": new_version, "rationale": reason,
            "diff": diff["counts"]})
    return {"ok": True, "plan_id": int(plan_id), "version": new_version,
            "status": "draft", "diff": diff, "rationale": reason,
            "plan_hash": payload["plan_hash"]}


def approve_plan(plan_id: int, version: int | None = None, *,
                 rationale: str, approver: str = "user",
                 db_path=None) -> dict:
    reason = _text(rationale, 4000)
    approver_text = _text(approver, 200)
    plan = get_plan(plan_id, db_path=db_path)
    if plan["status"] == "rejected":
        raise DocPlanLifecycleError("rejected plan must be edited before approval")
    target = int(version if version is not None else plan["current_version"])
    if target != int(plan["current_version"]):
        raise DocPlanLifecycleError("only the current plan version can be approved")
    if plan["status"] == "approved":
        current = get_plan_version(plan_id, target, db_path=db_path)
        return {"ok": True, "already_approved": True, "plan_id": int(plan_id),
                "version": target, "status": "approved",
                "approved_by": current.get("approved_by"),
                "approved_at": current.get("approved_at")}
    now = _now()
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE document_plan_versions SET approved_by=?, approved_at=?, "
                "rationale=? WHERE plan_id=? AND version=?",
                (approver_text, now, reason, int(plan_id), target))
            conn.execute(
                "UPDATE document_plans SET status='approved', updated_at=? "
                "WHERE id=?", (now, int(plan_id)))
    finally:
        conn.close()
    _audit("document_plan_approved", "Document plan approved",
           {"plan_id": int(plan_id), "version": target,
            "approved_by": approver_text})
    return {"ok": True, "already_approved": False, "plan_id": int(plan_id),
            "version": target, "status": "approved",
            "approved_by": approver_text, "approved_at": now}


def reject_plan(plan_id: int, version: int | None = None, *,
                rationale: str, rejected_by: str = "user",
                db_path=None) -> dict:
    reason = _text(rationale, 4000)
    rejected_text = _text(rejected_by, 200)
    plan = get_plan(plan_id, db_path=db_path)
    target = int(version if version is not None else plan["current_version"])
    if target != int(plan["current_version"]):
        raise DocPlanLifecycleError("only the current plan version can be rejected")
    if plan["status"] == "rejected":
        return {"ok": True, "already_rejected": True, "plan_id": int(plan_id),
                "version": target, "status": "rejected"}
    now = _now()
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE document_plan_versions SET rejected_by=?, rejected_at=?, "
                "rationale=? WHERE plan_id=? AND version=?",
                (rejected_text, now, reason, int(plan_id), target))
            conn.execute(
                "UPDATE document_plans SET status='rejected', updated_at=? "
                "WHERE id=?", (now, int(plan_id)))
    finally:
        conn.close()
    _audit("document_plan_rejected", "Document plan rejected",
           {"plan_id": int(plan_id), "version": target,
            "rejected_by": rejected_text})
    return {"ok": True, "already_rejected": False, "plan_id": int(plan_id),
            "version": target, "status": "rejected",
            "rejected_by": rejected_text, "rejected_at": now}


class DocumentPlanner:
    """Thin class facade over deterministic generation and lifecycle functions."""

    generate_plan = staticmethod(generate_plan)
    edit_plan = staticmethod(edit_plan)
    approve_plan = staticmethod(approve_plan)
    reject_plan = staticmethod(reject_plan)
    list_plans = staticmethod(list_plans)
    get_plan = staticmethod(get_plan)
    list_plan_versions = staticmethod(list_plan_versions)

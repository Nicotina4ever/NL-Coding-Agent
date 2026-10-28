"""Tests for deterministic document plan generation and version lifecycle (D4)."""
from __future__ import annotations
import os, sys
from pathlib import Path
import pytest

REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from nl_coding_agent.core import doc_planning as dp  # noqa: E402
from nl_coding_agent.core.document_corpus import DocumentCorpus  # noqa: E402
from nl_coding_agent.persistence.database import init_db  # noqa: E402

def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text,encoding="utf-8")

def _project(tmp_path):
    root=tmp_path/"project"
    _write(root/"README.md","""# Product

## Requirements

- The system must work offline.

## Constraints

- Must not use network access.

## Acceptance Criteria

- Done when tests pass.
""")
    _write(root/"docs"/"guide.md","# Guide\n\nUse SQLite.\n")
    _write(root/"docs"/"guide-v2.md","# Guide v2\n\nUse Postgres.\n")
    _write(root/"src"/"app.py","print('ok')\n")
    return root

def _corpus(root):
    return DocumentCorpus().discover_project(root, consent=True)

def _milestones():
    return [{"key":"m1","title":"Implement offline mode","priority":"P1",
             "dependencies":[],"description":"from documents",
             "validation_strategy":"tests"}]

def test_generation_is_deterministic_with_provenance_risks_and_acceptance(tmp_path):
    root=_project(tmp_path)
    first=dp.generate_plan(_corpus(root), root, persist=False)
    second=dp.generate_plan(_corpus(root), root, persist=False)
    assert first["ok"]
    assert first["objective"]
    assert first["milestones"]
    assert first["acceptance_criteria"]
    assert first["provenance"]
    assert first["risks"]
    assert first["blockers"]
    assert first["plan_hash"]==second["plan_hash"]
    assert first["milestones"]==second["milestones"]
    milestone=first["milestones"][0]
    assert milestone["key"].startswith("m-")
    assert milestone["priority"] in dp.PRIORITIES
    assert milestone["provenance"][0]["document_id"]
    assert milestone["provenance"][0]["excerpt_sha256"]
    assert first["executed"] is False
    assert "UNTRUSTED" in first["untrusted_marker"]

def test_empty_and_unknown_documents_are_honest(tmp_path):
    empty=dp.generate_plan({"documents":[]}, tmp_path, persist=False)
    assert empty["ok"]
    assert empty["objective"]==""
    assert empty["milestones"]==[]
    assert empty["acceptance_criteria"]==[]
    assert empty["limitations"]
    assert empty["unknowns"]
    assert empty["executed"] is False

def test_edit_versions_diff_validation_and_approved_immutability(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR",str(tmp_path/"data"))
    root=_project(tmp_path)
    plan=dp.generate_plan(_corpus(root), root)
    plan_id=plan["plan_id"]
    assert plan["status"]=="draft"
    edited=dp.edit_plan(plan_id,_milestones(),"requirements changed")
    assert edited["version"]==2 and edited["status"]=="draft"
    assert edited["diff"]["counts"]["added"]==1
    loaded=dp.get_plan(plan_id)
    assert loaded["current_version"]==2
    assert loaded["status"]=="draft"
    approved=dp.approve_plan(plan_id,rationale="looks correct")
    assert approved["status"]=="approved" and approved["version"]==2
    approved_version=dp.get_plan_version(plan_id,2)
    assert approved_version["approved_by"]=="user"
    after=dp.edit_plan(plan_id,[{"key":"m1","title":"New title","priority":"P2","dependencies":[],"description":"x"}],"new evidence")
    assert after["version"]==3
    assert dp.get_plan(plan_id)["status"]=="draft"
    old=dp.get_plan_version(plan_id,2)
    assert old["approved_at"]==approved_version["approved_at"]
    assert old["milestones"][0]["title"]=="Implement offline mode"
    before_edit=dp.get_plan_version(plan_id,3)
    assert before_edit["approved_at"] is None
    with pytest.raises(dp.DocPlanValidationError):
        dp.edit_plan(plan_id,[],"missing reason")
    with pytest.raises(dp.DocPlanValidationError):
        dp.edit_plan(plan_id,_milestones(),"")
    for invalid in (
        [{"key":"m1","title":"A","priority":"P1","dependencies":["m1"]}],
        [{"key":"m1","title":"A","priority":"P1","dependencies":["missing"]}],
        [{"key":"a","title":"A","priority":"P1","dependencies":["b"]},
         {"key":"b","title":"B","priority":"P1","dependencies":["a"]}],
        [{"key":"a","title":"A","priority":"P9","dependencies":[]}],
    ):
        with pytest.raises(dp.DocPlanValidationError):
            dp.edit_plan(plan_id,invalid,"bad plan")

def test_reject_audit_persistence_and_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR",str(tmp_path/"data"))
    root=_project(tmp_path)
    plan=dp.generate_plan(_corpus(root), root)
    plan_id=plan["plan_id"]
    rejected=dp.reject_plan(plan_id,rationale="not acceptable")
    assert rejected["status"]=="rejected"
    versions=dp.list_plan_versions(plan_id)
    assert versions[0]["rejected_by"]=="user"
    assert len(dp.list_plans())==1
    loaded=dp.get_plan(plan_id)
    assert loaded["status"]=="rejected"
    conn=init_db()
    try:
        rows=conn.execute("SELECT event_kind FROM events WHERE source='document_planning' ORDER BY id").fetchall()
    finally:
        conn.close()
    kinds={row[0] for row in rows}
    assert "document_plan_generated" in kinds
    assert "document_plan_rejected" in kinds
    with pytest.raises(dp.DocPlanLifecycleError):
        dp.approve_plan(plan_id,rationale="retry")

def test_static_no_execution_or_network_guards():
    source=(REPO_ROOT/"nl_coding_agent"/"core"/"doc_planning.py").read_text(encoding="utf-8").lower()
    for forbidden in ("import requests","urllib.request","import urllib","import socket",
                      "http.client","subprocess","os.system(","eval(","exec(",
                      "orchestrator","start_mission"):
        assert forbidden not in source, forbidden

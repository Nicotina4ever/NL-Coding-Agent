"""Tests for AppServices document planning surfaces."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import pytest
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from nl_coding_agent.persistence.database import init_db  # noqa: E402

def _write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding="utf-8")

@pytest.fixture()
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR",str(tmp_path/"data"))
    from nl_coding_agent.app.services import AppServices
    value=AppServices(); yield value
    try: value._db.close()
    except Exception: pass

def _root(tmp_path):
    root=tmp_path/"project"
    _write(root/"README.md","""# Product

## Requirements

- The system must work offline.

## Constraints

- Must not use network access.

## Acceptance Criteria

- Done when tests pass.
""")
    _write(root/"src"/"app.py","print('ok')\n")
    return root

def test_generate_list_get_versions_edit_approve_reject_and_restart(services,tmp_path):
    root=_root(tmp_path)
    result=services.docs_plan_generate(project_root=str(root))
    assert result["ok"], result
    plan=result["plan"]; plan_id=plan["plan_id"]
    assert plan["objective"] and plan["milestones"]
    assert plan["risks"]==[] or plan["risks"]
    assert services.docs_plan_list()["total"]==1
    assert services.docs_plan_get(plan_id)["plan"]["status"]=="draft"
    assert services.docs_plan_versions(plan_id)["total"]==1
    edited=services.docs_plan_edit(plan_id,[{"key":"m1","title":"Do it","priority":"P1","dependencies":[]}],"reason")
    assert edited["ok"] and edited["version"]==2
    assert services.docs_plan_approve(plan_id,reason="approved")["ok"]
    assert services.docs_plan_reject(plan_id,reason="rejected")["ok"]
    assert services.docs_plan_get(plan_id)["plan"]["status"]=="rejected"
    errors=[
        services.docs_plan_get(9999),
        services.docs_plan_edit(plan_id,[],"missing"),
        services.docs_plan_approve(9999,reason="x"),
    ]
    assert all(not item["ok"] for item in errors)
    root_id=services.docs_plan_generate(project_root=str(root))["plan_id"]
    services._db.close()
    from nl_coding_agent.app.services import AppServices
    rebuilt=AppServices()
    try:
        assert rebuilt.docs_plan_get(root_id)["ok"]
        assert rebuilt.docs_plan_list()["total"]==2
    finally:
        rebuilt._db.close()

def test_no_missions_created_or_executed(services,tmp_path):
    conn=init_db()
    try: before=conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
    finally: conn.close()
    result=services.docs_plan_generate(project_root=str(_root(tmp_path)))
    plan_id=result["plan_id"]
    services.docs_plan_edit(plan_id,[{"key":"m1","title":"X","priority":"P1","dependencies":[]}],"r")
    services.docs_plan_approve(plan_id,reason="ok")
    services.docs_plan_reject(plan_id,reason="no")
    conn=init_db()
    try:
        after=conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        row=conn.execute("SELECT status FROM document_plans WHERE id=?",(plan_id,)).fetchone()
    finally: conn.close()
    assert after==before
    assert row["status"]=="rejected"

def test_structured_errors_and_validation(services,tmp_path):
    result=services.docs_plan_generate(project_root=str(_root(tmp_path)))
    plan_id=result["plan_id"]
    bad=services.docs_plan_edit(plan_id,[{"key":"a","title":"A","priority":"P1","dependencies":["b"]},
                                        {"key":"b","title":"B","priority":"P1","dependencies":["a"]}],"cycle")
    assert not bad["ok"] and bad["error"]["code"]=="validation"
    assert not services.docs_plan_approve(plan_id,reason="")["ok"]
    assert not services.docs_plan_reject(plan_id,reason="")["ok"]
    assert not services.docs_plan_generate()["ok"]


@pytest.mark.parametrize("text", [
    "Analizza la documentazione e prepara un piano",
    "Analyze the documentation and prepare a plan",
    "Leggi i documenti e pianifica il lavoro",
])
def test_chat_routes_to_existing_plan_service_without_missions(services, tmp_path, text):
    from nl_coding_agent.projects.registry import open_project
    root = _root(tmp_path)
    project = open_project(root)
    assert services.chat_workflow(text) == "document_plan"
    result = services.chat_document_plan(project, text)
    assert result["ok"], result
    assert result["status"] == "draft" and result["executed"] is False
    assert result["plan"]["objective"] == text
    assert services.list_missions(project["id"]) == []
    assert (root / "src/app.py").read_text() == "print('ok')\n"


@pytest.mark.parametrize("text", [
    "Implement the feature in src/app.py",
    "Implement the plan described in docs",
    "Implementa il piano descritto nella documentazione",
    "Fix docs/plan.md",
])
def test_coding_chat_route_preserved(services, text):
    assert services.chat_workflow(text) == "coding"


def test_chat_plan_includes_text_attachment_without_mission(services, tmp_path):
    from nl_coding_agent.projects.registry import open_project
    project = open_project(_root(tmp_path))
    item = services.prepare_attachment_text(
        project["id"], "# Requirements\n- The system must preserve attached context.\n")
    result = services.chat_document_plan(
        project, "Analizza la documentazione e prepara un piano", [item["id"]])
    assert result["ok"], result
    assert "attached context" in json.dumps(result["plan"])
    assert services.list_missions(project["id"]) == []

"""Tests for document planning CLI (pre-model, no execution)."""
from __future__ import annotations
import contextlib, io, json, os, sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
import nl_coding_agent.cli as cli  # noqa: E402

def _write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding="utf-8")

def _run(args,stdin=""):
    out,err=io.StringIO(),io.StringIO(); old=sys.stdin; sys.stdin=io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            try: code=cli.main(args)
            except SystemExit as exc: code=int(exc.code or 0)
    finally: sys.stdin=old
    return code,out.getvalue(),err.getvalue()

def test_cli_plan_lifecycle_json_text_and_exits(tmp_path,monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR",str(tmp_path/"data"))
    root=tmp_path/"project"
    _write(root/"README.md","# Product\n\n## Requirements\n\n- The system must work offline.\n\n## Acceptance Criteria\n\n- Done when tests pass.\n")
    models=tmp_path/"missing-models.yaml"
    code,out,err=_run(["--models",str(models),"docs","plan",str(root),"--json"])
    assert code==0,err
    payload=json.loads(out); plan=payload["plan"]; plan_id=plan["plan_id"]
    assert plan["milestones"] and plan["objective"]
    code,out,err=_run(["docs","plans","--json"])
    assert code==0 and json.loads(out)["plans"][0]["id"]==plan_id
    code,out,err=_run(["docs","plans",str(plan_id)])
    assert code==0 and "Document plan" in out
    edit=tmp_path/"edit.json"
    edit.write_text(json.dumps({"milestones":[{"key":"m1","title":"Do","priority":"P1","dependencies":[]}]}),encoding="utf-8")
    code,out,err=_run(["docs","plan-edit",str(plan_id),"--file",str(edit),"--reason","change","--json"])
    assert code==0,err and json.loads(out)["version"]==2
    code,out,err=_run(["docs","plan-approve",str(plan_id),"--reason","ok","--json"])
    assert code==0,err and json.loads(out)["status"]=="approved"
    code,out,err=_run(["docs","plan-edit",str(plan_id),"--file",str(edit),"--reason","again"])
    assert code==0
    code,out,err=_run(["docs","plan-reject",str(plan_id),"--reason","no","--json"])
    assert code==0 and json.loads(out)["status"]=="rejected"
    code,out,err=_run(["docs","plans","9999","--json"])
    assert code==1 and json.loads(out)["error"]["code"]=="not_found"
    code,out,err=_run(["docs","plan-approve",str(plan_id)])
    assert code==2
    code,out,err=_run(["docs","plan-reject",str(plan_id),"--reason",""])
    assert code==1
    code,out,err=_run(["docs","plan-edit",str(plan_id),"--file",str(tmp_path/"missing.json"),"--reason","x"])
    assert code==2
    code,out,err=_run(["docs","plan",str(root),"--run"])
    assert code==2

def test_cli_db_isolation(tmp_path,monkeypatch):
    root=tmp_path/"project"; _write(root/"README.md","# P\n\n## Requirements\n\n- The system must work.\n")
    monkeypatch.setenv("NL_DATA_DIR",str(tmp_path/"one"))
    assert _run(["docs","plan",str(root),"--json"])[0]==0
    monkeypatch.setenv("NL_DATA_DIR",str(tmp_path/"two"))
    code,out,err=_run(["docs","plans","--json"])
    assert code==0 and json.loads(out)["total"]==0

from pathlib import Path
from nl_coding_agent.core.supervisor import Supervisor
from nl_coding_agent.persistence import database, missions, supervisor_store as store
from nl_coding_agent.projects.registry import open_project


def test_supervisor_approvals_list_decide_audit_and_deny_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "project"; root.mkdir()
    (root / "nl_coding_agent").mkdir(); (root / "nl_coding_agent" / "__init__.py").write_text("")
    database.init_db().close()
    pid = int(open_project(root)["id"])
    mid = missions.create_mission(pid, "approval mission", "goal")
    aid = store.create_flow_approval(pid, flow_id="flow-appr", method_name="review",
                                     action="network", reason="needs network", mission_id=mid,
                                     requested_by="flow", ttl_s=3600)
    sup = Supervisor(root, project_id=pid)
    assert len(sup.list_approvals()) == 1
    assert any(row["id"] == aid for row in sup.status()["approvals"])
    result = sup.decide_approval(aid, approved=False, decided_by="human", reason="no")
    assert result["ok"] is True and result["decision"] == "denied"
    assert missions.get_mission(mid)["status"] == "blocked"
    assert sup.list_approvals(status="denied")[0]["decided_by"] == "human"
    assert store.flow_approval_outcome("flow-appr") == "denied"

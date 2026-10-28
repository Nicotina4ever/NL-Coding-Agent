import pytest
from types import SimpleNamespace
from crewai.flow.async_feedback.types import HumanFeedbackPending, PendingFeedbackContext
from nl_coding_agent.flows import approval_provider as ap
from nl_coding_agent.persistence import database, supervisor_store as store


def test_deterministic_classification_outcomes_and_durable_request(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    database.init_db().close()
    assert ap.classify_approval("review", "reviewing") == "review"
    assert ap.classify_approval("promote", "promoting", "cloud denied") == "cloud"
    assert ap.normalize_feedback("approved: looks good") == "approved"
    assert ap.normalize_feedback("whatever") == "rejected"
    project = store._db
    from nl_coding_agent.persistence import database as db
    conn = db.init_db()
    try:
        with conn:
            conn.execute("INSERT INTO projects (name, root) VALUES ('p','X:/p')")
            pid = int(conn.execute("SELECT id FROM projects").fetchone()["id"])
    finally:
        conn.close()
    provider = ap.GuiApprovalProvider(pid, mission_id=None)
    ctx = PendingFeedbackContext(flow_id="flow-hf", flow_class="tests.F", method_name="review", method_output={}, message="approve?")
    with pytest.raises(HumanFeedbackPending) as caught:
        provider.request_feedback(ctx, SimpleNamespace(state=SimpleNamespace(phase="reviewing", last_error="")))
    aid = caught.value.context.flow_id
    approval = store.list_approvals_for_flow("flow-hf")[0]
    assert approval["status"] == "pending" and approval["action"] in store.APPROVAL_ACTIONS
    assert provider.resume_outcome("flow-hf") == "pending"
    assert provider.decide(approval["id"], approved=True, decided_by="human", reason="ok")["outcome"] == "approved"
    assert provider.resume_outcome("flow-hf") == "approved"

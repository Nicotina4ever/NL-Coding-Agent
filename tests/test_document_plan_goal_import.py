"""Document approval imports into durable goals without granting execution approval."""
import pytest

from nl_coding_agent.persistence.database import init_db


@pytest.fixture
def setup_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices
    services = AppServices()
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text(
        "# Example\n## Requirements\n- The system must preserve files.\n"
        "## Acceptance Criteria\n- Done when tests pass.\n", encoding="utf-8")
    project = services.open_project(root)
    result = services.docs_plan_generate(project_root=str(root), project_id=project["id"])
    assert result["ok"], result
    plan_id = result["plan_id"]
    edited = services.docs_plan_edit(plan_id, [
        {"key": "first", "title": "Read source", "priority": "P1", "dependencies": []},
        {"key": "second", "title": "Verify source", "priority": "P2", "dependencies": ["first"],
         "validation_strategy": "Run the project tests"},
    ], "Prepare ordered work")
    assert edited["ok"], edited
    yield services, project, plan_id
    services._db.close()


def test_import_uses_approved_version_and_maps_dependencies_without_execution(setup_plan):
    services, project, plan_id = setup_plan
    assert services.docs_plan_approve(plan_id, reason="Owner reviewed")["ok"]
    result = services.goal_create_from_document_plan(plan_id, project_id=project["id"])
    assert result["ok"], result
    goal = result["goal"]
    assert goal["status"] == "planned"
    assert goal["acceptance_criteria"] == ["Done when tests pass."]
    assert goal["reference_metadata"]["plan_version"] == "2"
    from nl_coding_agent.persistence import goal_store
    milestones = goal_store.list_milestones(goal["id"])
    assert [item["title"] for item in milestones] == ["Read source", "Verify source"]
    assert milestones[1]["dependencies"] == [milestones[0]["id"]]
    assert milestones[1]["validation_strategy"] == "Run the project tests"
    assert goal_store.list_plan_versions(goal["id"]) == []
    assert result["executed"] is False
    conn = init_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize("status", ["draft", "rejected", "edited_after_approval"])
def test_nonapproved_current_plan_does_not_create_goal(setup_plan, status):
    services, project, plan_id = setup_plan
    if status == "rejected":
        services.docs_plan_reject(plan_id, reason="Not accepted")
    if status == "edited_after_approval":
        services.docs_plan_approve(plan_id, reason="Old version accepted")
        services.docs_plan_edit(plan_id, [
            {"key": "new", "title": "Changed", "priority": "P1", "dependencies": []}
        ], "New unapproved version")
    assert not services.goal_create_from_document_plan(plan_id, project_id=project["id"])["ok"]
    assert services.goal_list()["total"] == 0


def test_project_mismatch_and_activation_fail_before_writes(setup_plan, tmp_path):
    services, project, plan_id = setup_plan
    services.docs_plan_approve(plan_id, reason="Reviewed")
    other = tmp_path / "other"
    other.mkdir()
    other_project = services.open_project(other)
    for fields in ({"project_id": other_project["id"]},
                   {"project_id": project["id"], "project_root": str(other)},
                   {"project_id": project["id"], "activate": True}):
        assert not services.goal_create_from_document_plan(plan_id, **fields)["ok"]
    assert services.goal_list()["total"] == 0


def test_database_failure_rolls_back_entire_import(setup_plan):
    services, project, plan_id = setup_plan
    services.docs_plan_approve(plan_id, reason="Reviewed")
    conn = init_db()
    try:
        conn.execute("CREATE TRIGGER reject_second BEFORE INSERT ON milestones "
                     "WHEN NEW.title = 'Verify source' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        conn.commit()
        result = services.goal_create_from_document_plan(plan_id, project_id=project["id"])
        assert not result["ok"], result
        assert services.goal_list()["total"] == 0
        assert conn.execute("SELECT COUNT(*) FROM milestones").fetchone()[0] == 0
    finally:
        conn.close()

"""Tests for task graph dependencies, collision prevention, and SQLite mission persistence."""
import tempfile
import pytest
from pathlib import Path
from nl_coding_agent.core.task_graph import TaskGraph, CyclicDependencyError
from nl_coding_agent.persistence.database import init_db
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_mission,
    update_mission_status,
    add_task,
    get_tasks,
    update_task_status,
    record_handoff,
    get_handoffs,
    record_verification_run,
    get_verification_runs,
)


def test_task_graph_dependencies():
    graph = TaskGraph()
    # Task 1: No deps
    graph.add_task(1, "Create model", "Implement model", "developer")
    # Task 2: Depends on 1
    graph.add_task(2, "Test model", "Run tests", "tester", depends_on=[1])

    # Initially, only task 1 is ready
    ready = graph.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].task_id == 1

    # Complete task 1
    graph.nodes[1].status = "completed"

    # Now task 2 is ready
    ready = graph.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].task_id == 2


def test_task_graph_cycle_detection():
    graph = TaskGraph()
    graph.add_task(1, "Task 1", "", "developer", depends_on=[2])
    with pytest.raises(CyclicDependencyError):
        graph.add_task(2, "Task 2", "", "developer", depends_on=[1])


def test_task_collision_prevention():
    graph = TaskGraph()
    t1 = graph.add_task(1, "Edit UI", "", "developer", write_paths=["src/gui.py"])
    t2 = graph.add_task(2, "Refactor UI", "", "developer", write_paths=["src/gui.py"])
    t3 = graph.add_task(3, "Update Docs", "", "developer", write_paths=["docs/readme.md"])

    # t1 and t2 collide
    assert graph.check_collision(t1, t2) is True
    # t1 and t3 do not collide
    assert graph.check_collision(t1, t3) is False
    assert graph.can_run_concurrently([t1], t3) is True
    assert graph.can_run_concurrently([t1], t2) is False


def test_mission_persistence_roundtrip():
    m_id = create_mission(project_id=None, title="Self Build Test", goal="Add feature X")
    assert m_id > 0

    m = get_mission(m_id)
    assert m["title"] == "Self Build Test"
    assert m["status"] == "pending"

    # Add tasks
    t1_id = add_task(m_id, "Code feature", "Write code", "developer")
    t2_id = add_task(m_id, "Verify feature", "Run tests", "tester", depends_on=[t1_id])

    tasks = get_tasks(m_id)
    assert len(tasks) == 2
    assert tasks[1]["depends_on"] == [t1_id]

    # Record handoff
    record_handoff(m_id, "developer", "tester", "Code implemented", {"files": ["feature.py"]})
    handoffs = get_handoffs(m_id)
    assert len(handoffs) == 1
    assert handoffs[0]["from_role"] == "developer"
    assert handoffs[0]["to_role"] == "tester"

    # Record verification run
    record_verification_run(m_id, t2_id, "pytest", 0, "1 passed", "", True)
    runs = get_verification_runs(m_id)
    assert len(runs) == 1
    assert runs[0]["passed"] == 1

"""Tests for durable goal/milestone schema, GoalService and decomposition (G1)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core import goals as goals_module  # noqa: E402
from nl_coding_agent.core.goals import (  # noqa: E402
    GOAL_STATUSES,
    MILESTONE_STATUSES,
    PRIORITIES,
    GoalDependencyError,
    GoalDecompositionError,
    GoalLifecycleError,
    GoalNotFoundError,
    GoalService,
    GoalValidationError,
)
from nl_coding_agent.persistence import goal_store, missions  # noqa: E402
from nl_coding_agent.persistence.database import init_db  # noqa: E402


class GoalTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name) / "data"
        self.data_dir.mkdir()
        self._old_env = os.environ.get("NL_DATA_DIR")
        os.environ["NL_DATA_DIR"] = str(self.data_dir)
        self.service = GoalService()

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("NL_DATA_DIR", None)
        else:
            os.environ["NL_DATA_DIR"] = self._old_env

    def make_goal(self, **overrides):
        values = dict(objective="Ship durable goal mode", title="Goal",
                      acceptance_criteria=["works"], priority="P1")
        values.update(overrides)
        return self.service.create_goal(**values)

    def make_active_goal(self, **overrides):
        goal = self.make_goal(**overrides)
        return self.service.activate_goal(goal["id"])


class SchemaAndPersistenceTests(GoalTestCase):
    def test_additive_schema_is_idempotent_and_preserves_legacy_tables(self):
        tables = goal_store.ensure_schema()
        self.assertEqual(tables, ("goal_missions", "goals", "milestones"))
        conn = init_db()
        try:
            names = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        for expected in ("missions", "tasks", "projects", "events", "goals",
                         "milestones", "goal_missions"):
            self.assertIn(expected, names)
        # existing legacy rows survive repeated goal schema initialisation
        mission_id = missions.create_mission(None, "Legacy mission", "legacy goal")
        GoalService()
        conn = init_db()
        try:
            row = conn.execute("SELECT title, status FROM missions WHERE id=?",
                               (mission_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["title"], "Legacy mission")
        self.assertEqual(row["status"], "pending")
        self.assertEqual(self.service.list_goals(), [])

    def test_restart_persists_goals_and_milestones(self):
        goal = self.make_active_goal(project_id=None)
        self.service.decompose_goal(goal["id"], [{"title": "M1"}])
        restarted = GoalService()
        loaded = restarted.get_goal(goal["id"])
        self.assertEqual(loaded["title"], "Goal")
        milestones = restarted.list_milestones(goal["id"])
        self.assertEqual(len(milestones), 1)
        self.assertEqual(milestones[0]["title"], "M1")


class GoalCrudTests(GoalTestCase):
    def test_create_get_list_update_deterministic_priority(self):
        low = self.make_goal(title="Low", priority="P3")
        high = self.make_goal(title="High", priority="P0", project_id=7,
                              attachments=["file:notes"], reference_metadata={"k": "v"})
        listed = self.service.list_goals()
        self.assertEqual([item["id"] for item in listed], [high["id"], low["id"]])
        loaded = self.service.get_goal(high["id"])
        self.assertEqual(loaded["priority"], "P0")
        self.assertEqual(loaded["status"], "planned")
        self.assertEqual(loaded["acceptance_criteria"], ["works"])
        self.assertEqual(loaded["attachments"], ["file:notes"])
        self.assertEqual(loaded["reference_metadata"], {"k": "v"})
        self.assertEqual(self.service.list_goals(project_id=7)[0]["id"], high["id"])
        updated = self.service.update_goal(low["id"], title="Low v2",
                                           priority="P0", acceptance_criteria=["a", "b"])
        self.assertEqual(updated["title"], "Low v2")
        self.assertEqual(updated["priority"], "P0")
        self.assertEqual(updated["acceptance_criteria"], ["a", "b"])
        self.assertEqual(self.service.list_goals()[0]["title"] in ("High", "Low v2"), True)
        with self.assertRaises(GoalNotFoundError):
            self.service.get_goal(9999)
        with self.assertRaises(GoalValidationError):
            self.make_goal(priority="P9")
        with self.assertRaises(GoalValidationError):
            self.make_goal(origin="robot")
        with self.assertRaises(GoalValidationError):
            self.service.update_goal(low["id"], status="active")

    def test_goal_dependencies_missing_self_and_cycle(self):
        first = self.make_goal(title="First")
        second = self.make_goal(title="Second", dependencies=[first["id"]])
        self.assertEqual(second["dependencies"], [first["id"]])
        with self.assertRaises(GoalDependencyError):
            self.make_goal(title="Missing", dependencies=[9999])
        with self.assertRaises(GoalDependencyError):
            self.service.update_goal(first["id"], dependencies=[first["id"]])
        # second -> first already exists; adding first -> second would close a cycle
        with self.assertRaises(GoalDependencyError):
            self.service.update_goal(first["id"], dependencies=[second["id"]])
        self.assertIn(first["id"], self.service.get_goal(second["id"])["dependencies"])


class LifecycleTests(GoalTestCase):
    def test_valid_transitions_and_explicit_completion(self):
        goal = self.make_goal()
        self.assertEqual(goal["status"], "planned")
        activated = self.service.activate_goal(goal["id"])
        self.assertEqual(activated["status"], "active")
        paused = self.service.pause_goal(goal["id"])
        self.assertEqual(paused["status"], "paused")
        resumed = self.service.resume_goal(goal["id"])
        self.assertEqual(resumed["status"], "active")
        blocked = self.service.block_goal(goal["id"], "waiting")
        self.assertEqual(blocked["status"], "blocked")
        unblocked = self.service.unblock_goal(goal["id"])
        self.assertEqual(unblocked["status"], "active")
        with self.assertRaises(GoalLifecycleError):
            self.service.complete_goal(goal["id"])
        milestone = self.service.create_milestone(goal["id"], "M1")
        with self.assertRaises(GoalLifecycleError):
            self.service.complete_goal(goal["id"])
        self.service.update_milestone(milestone["id"], status="completed")
        # All milestones completed still does NOT silently complete the goal.
        self.assertEqual(self.service.get_goal(goal["id"])["status"], "active")
        completed = self.service.complete_goal(goal["id"], evidence={"check": "green"})
        self.assertEqual(completed["status"], "completed")
        with self.assertRaises(GoalLifecycleError):
            self.service.activate_goal(goal["id"])
        with self.assertRaises(GoalLifecycleError):
            self.service.cancel_goal(goal["id"])
        with self.assertRaises(GoalLifecycleError):
            self.service.update_goal(goal["id"], title="closed")

    def test_invalid_transitions_leave_status_unchanged(self):
        goal = self.make_goal()
        for method, expected in ((self.service.pause_goal, "planned"),
                                 (self.service.resume_goal, "planned")):
            with self.assertRaises(GoalLifecycleError):
                method(goal["id"])
            self.assertEqual(self.service.get_goal(goal["id"])["status"], expected)
        self.service.activate_goal(goal["id"])
        with self.assertRaises(GoalLifecycleError):
            self.service.activate_goal(goal["id"])
        self.service.cancel_goal(goal["id"])
        self.assertEqual(self.service.get_goal(goal["id"])["status"], "cancelled")
        with self.assertRaises(GoalLifecycleError):
            self.service.pause_goal(goal["id"])


class MilestoneTests(GoalTestCase):
    def test_milestone_crud_dependencies_and_ordering(self):
        goal = self.make_active_goal()
        first = self.service.create_milestone(goal["id"], "First", priority="P1")
        second = self.service.create_milestone(goal["id"], "Second", priority="P0",
                                               dependencies=[first["id"]])
        self.assertEqual(first["ordering"], 0)
        self.assertEqual(second["ordering"], 1)
        self.assertEqual(second["dependencies"], [first["id"]])
        listed = self.service.list_milestones(goal["id"])
        self.assertEqual([item["title"] for item in listed], ["First", "Second"])
        updated = self.service.update_milestone(first["id"], description="desc",
                                                acceptance_criteria=["ok"],
                                                evidence_refs=["tests"])
        self.assertEqual(updated["description"], "desc")
        self.assertEqual(updated["acceptance_criteria"], ["ok"])
        self.assertEqual(updated["evidence_refs"], ["tests"])
        with self.assertRaises(GoalDependencyError):
            self.service.update_milestone(first["id"], dependencies=[first["id"]])
        with self.assertRaises(GoalDependencyError):
            self.service.update_milestone(first["id"], dependencies=[second["id"]])
        with self.assertRaises(GoalDependencyError):
            self.service.delete_milestone(first["id"])
        self.assertTrue(self.service.delete_milestone(second["id"]))
        with self.assertRaises(GoalNotFoundError):
            self.service.get_milestone(second["id"])
        with self.assertRaises(GoalValidationError):
            self.service.create_milestone(goal["id"], "Bad", priority="P9")

    def test_milestone_dependencies_missing_and_cycle(self):
        goal = self.make_active_goal()
        first = self.service.create_milestone(goal["id"], "First")
        with self.assertRaises(GoalDependencyError):
            self.service.create_milestone(goal["id"], "Bad", dependencies=[9999])
        second = self.service.create_milestone(goal["id"], "Second",
                                               dependencies=[first["id"]])
        with self.assertRaises(GoalDependencyError):
            self.service.update_milestone(first["id"], dependencies=[second["id"]])


class DecompositionTests(GoalTestCase):
    def test_decomposition_creates_ordered_dependency_graph(self):
        goal = self.make_active_goal()
        created = self.service.decompose_goal(goal["id"], [
            {"key": "design", "title": "Design", "priority": "P0"},
            {"key": "build", "title": "Build", "dependencies": ["design"]},
            {"key": "verify", "title": "Verify", "dependencies": ["build"]},
        ])
        self.assertEqual([item["title"] for item in created],
                         ["Design", "Build", "Verify"])
        by_title = {item["title"]: item for item in created}
        self.assertEqual(by_title["Build"]["dependencies"], [by_title["Design"]["id"]])
        self.assertEqual(by_title["Verify"]["dependencies"], [by_title["Build"]["id"]])
        self.assertEqual([item["ordering"] for item in created], [0, 1, 2])
        # new plan can depend on already-created milestones by integer id
        extra = self.service.decompose_goal(goal["id"], [
            {"title": "Ship", "dependencies": [by_title["Verify"]["id"]]}])
        self.assertEqual(extra[-1]["dependencies"], [by_title["Verify"]["id"]])

    def test_decomposition_validation(self):
        goal = self.make_active_goal()
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [])
        with self.assertRaises((GoalDecompositionError, GoalValidationError)):
            self.service.decompose_goal(goal["id"], [{}])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [
                {"key": "a", "title": "A"}, {"key": "a", "title": "B"}])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [
                {"title": "Same"}, {"title": "Same"}])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [
                {"title": "A", "bogus": True}])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [
                {"title": "A", "dependencies": ["missing"]}])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [
                {"title": "A", "dependencies": [9999]}])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [
                {"key": "a", "title": "A", "dependencies": ["a"]}])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [
                {"key": "a", "title": "A", "dependencies": ["b"]},
                {"key": "b", "title": "B", "dependencies": ["a"]}])
        self.service.decompose_goal(goal["id"], [{"title": "Existing"}])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(goal["id"], [{"title": "existing"}])
        cancelled = self.make_goal(title="Terminal")
        self.service.cancel_goal(cancelled["id"])
        with self.assertRaises(GoalDecompositionError):
            self.service.decompose_goal(cancelled["id"], [{"title": "Late"}])

    def test_decomposition_keeps_existing_milestones(self):
        goal = self.make_active_goal()
        first = self.service.create_milestone(goal["id"], "Existing")
        created = self.service.decompose_goal(goal["id"],
                                              [{"title": "New"}])
        self.assertEqual(len(created), 2)
        self.assertEqual([item["title"] for item in created], ["Existing", "New"])
        self.assertEqual(created[1]["ordering"], first["ordering"] + 1)


class EligibleProgressTests(GoalTestCase):
    def test_dependencies_status_and_priority_for_next_work(self):
        dependency = self.make_active_goal(title="Dependency", priority="P0")
        dep_milestone = self.service.create_milestone(dependency["id"], "Dep M")
        dependent = self.make_active_goal(title="Dependent", priority="P0",
                                          dependencies=[dependency["id"]])
        dependent_milestone = self.service.create_milestone(dependent["id"], "Dependent M")
        other = self.make_active_goal(title="Other", priority="P1")
        other_milestone = self.service.create_milestone(other["id"], "Other M")
        work = self.service.next_work()
        self.assertEqual(work[0]["milestone_id"], dep_milestone["id"])
        self.assertNotIn(dependent_milestone["id"],
                         [item["milestone_id"] for item in work])
        self.assertNotIn(other_milestone["id"],
                         [item["milestone_id"] for item in work if item["goal_id"] == dependent["id"]])
        self.service.update_milestone(dep_milestone["id"], status="completed")
        # completing the dependency milestone does not complete the dependency goal
        self.assertNotIn(dependent_milestone["id"],
                         [item["milestone_id"] for item in self.service.next_work()])
        self.service.update_milestone(
            self.service.create_milestone(dependency["id"], "Dep final")["id"],
            status="completed")
        self.assertEqual(self.service.complete_goal(dependency["id"])["status"],
                         "completed")
        work = self.service.next_work()
        ids = [item["milestone_id"] for item in work]
        self.assertIn(dependent_milestone["id"], ids)
        self.assertLess(ids.index(dependent_milestone["id"]),
                        ids.index(other_milestone["id"]))
        self.assertEqual(self.service.next_work(goal_id=other["id"])[0]["milestone_id"],
                         other_milestone["id"])
        self.assertEqual(self.service.next_work(project_id=999), [])
        self.assertEqual(self.service.next_work(limit=1)[0]["milestone_id"],
                         dependent_milestone["id"])

    def test_planned_paused_cancelled_goals_have_no_eligible_work(self):
        planned = self.make_goal()
        self.service.create_milestone(planned["id"], "Planned M")
        self.assertEqual(self.service.eligible_milestones(planned["id"]), [])
        self.assertEqual(self.service.next_work(), [])
        active = self.make_active_goal(title="Active")
        milestone = self.service.create_milestone(active["id"], "Active M")
        self.assertEqual([item["id"] for item in
                          self.service.eligible_milestones(active["id"])],
                         [milestone["id"]])
        self.service.pause_goal(active["id"])
        self.assertEqual(self.service.next_work(), [])

    def test_progress_summary_and_percent(self):
        goal = self.make_active_goal()
        first = self.service.create_milestone(goal["id"], "A")
        self.service.create_milestone(goal["id"], "B")
        progress = self.service.progress(goal["id"])
        self.assertEqual(progress["milestones_total"], 2)
        self.assertEqual(progress["milestones_completed"], 0)
        self.assertEqual(progress["progress_percent"], 0.0)
        self.assertEqual(sorted(progress["eligible_next_work"]),
                         sorted([first["id"], self.service.list_milestones(goal["id"])[1]["id"]]))
        self.service.update_milestone(first["id"], status="completed")
        progress = self.service.progress(goal["id"])
        self.assertEqual(progress["progress_percent"], 50.0)
        self.assertEqual(progress["status"], "active")
        summary = self.service.progress_summary()
        self.assertEqual(summary["goals_total"], 1)
        self.assertEqual(summary["milestones_total"], 2)
        self.assertEqual(summary["milestones_completed"], 1)


class AuditAndNoExecutionTests(GoalTestCase):
    def test_audit_events_source_goals(self):
        goal = self.make_active_goal()
        self.service.create_milestone(goal["id"], "M")
        conn = init_db()
        try:
            rows = conn.execute(
                "SELECT event_kind, payload FROM events WHERE source='goals' "
                "ORDER BY id").fetchall()
        finally:
            conn.close()
        kinds = [row["event_kind"] for row in rows]
        self.assertIn("goal_created", kinds)
        self.assertIn("goal_lifecycle", kinds)
        self.assertIn("milestone_created", kinds)
        self.assertTrue(any(str(goal["id"]) in str(row["payload"]) for row in rows))

    def test_link_mission_never_creates_or_executes_missions(self):
        goal = self.make_active_goal()
        conn = init_db()
        try:
            before = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        finally:
            conn.close()
        mission_id = missions.create_mission(None, "Linked mission", "goal")
        linked = self.service.link_goal_mission(goal["id"], mission_id)
        self.assertEqual(linked["mission_id"], mission_id)
        self.assertEqual(len(self.service.list_goal_missions(goal["id"])), 1)
        conn = init_db()
        try:
            after = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
            mission = conn.execute("SELECT status, title FROM missions WHERE id=?",
                                   (mission_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(after, before + 1)
        self.assertEqual(mission["status"], "pending")
        self.assertEqual(mission["title"], "Linked mission")
        with self.assertRaises(GoalNotFoundError):
            self.service.link_goal_mission(goal["id"], 9999)

    def test_static_no_model_network_or_gui_imports(self):
        for relative in ("nl_coding_agent/core/goals.py",
                         "nl_coding_agent/persistence/goal_store.py"):
            source = (REPO_ROOT / relative).read_text(encoding="utf-8")
            for forbidden in ("import requests", "import urllib", "import socket",
                              "http.client", "import crewai", "import ollama",
                              "PySide6", "tkinter", "subprocess"):
                self.assertNotIn(forbidden, source, relative + ": " + forbidden)
        self.assertEqual(tuple(GOAL_STATUSES),
                         ("planned", "active", "paused", "blocked", "completed",
                          "cancelled"))
        self.assertEqual(tuple(MILESTONE_STATUSES),
                         ("pending", "active", "paused", "blocked", "completed",
                          "cancelled"))
        self.assertEqual(tuple(PRIORITIES), ("P0", "P1", "P2", "P3"))


if __name__ == "__main__":
    unittest.main()

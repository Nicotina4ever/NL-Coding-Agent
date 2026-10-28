"""Tests for versioned goal replanning, mission links/activity/queue and CLI (G6)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import nl_coding_agent.cli as cli  # noqa: E402
from nl_coding_agent.app.services import AppServices  # noqa: E402
from nl_coding_agent.core.goals import (  # noqa: E402
    GoalDependencyError, GoalDecompositionError, GoalLifecycleError,
    GoalService, GoalValidationError,
)
from nl_coding_agent.persistence import goal_store, missions  # noqa: E402
from nl_coding_agent.persistence.database import init_db  # noqa: E402

CRITERIA = [{"id": "C1", "text": "tests pass",
             "required_evidence_types": ["test"]}]
EVIDENCE = [{"type": "test", "source": "pytest:tests", "result": "pass",
             "trust": "trusted", "exit_code": 0}]


class GoalReplanningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.data_dir = self.root / "data"
        self.project_dir = self.root / "project"
        self.project_dir.mkdir()
        self._old_env = os.environ.get("NL_DATA_DIR")
        os.environ["NL_DATA_DIR"] = str(self.data_dir)
        self.services = AppServices()
        self.seed = self.services.goal_create(
            "Deliver the G6 vertical slice", title="G6",
            acceptance_criteria=["tests pass"])["goal"]
        self.goal_id = self.seed["id"]
        self.services.goal_activate(self.goal_id)
        self.initial = self.services.goal_decompose(self.goal_id, [
            {"key": "a", "title": "Alpha"},
            {"key": "b", "title": "Beta", "dependencies": ["a"]},
        ])
        self.alpha = next(item for item in self.initial["milestones"]
                          if item["title"] == "Alpha")
        self.beta = next(item for item in self.initial["milestones"]
                         if item["title"] == "Beta")

    def tearDown(self):
        try:
            self.services._db.close()
        except Exception:
            pass
        if self._old_env is None:
            os.environ.pop("NL_DATA_DIR", None)
        else:
            os.environ["NL_DATA_DIR"] = self._old_env

    def replan(self, plan, rationale="New evidence changes the plan",
               trigger="manual", evidence=None):
        return self.services.goal_replan(self.goal_id, plan, rationale,
                                         trigger=trigger,
                                         evidence_refs=evidence)

    def test_schema_idempotent_and_milestone_fields(self):
        conn = init_db()
        try:
            tables = {row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            columns = {row["name"] for row in conn.execute(
                "PRAGMA table_info(milestones)")}
        finally:
            conn.close()
        self.assertIn("goal_plan_versions", tables)
        for name in ("risk", "validation_strategy", "mission_intent"):
            self.assertIn(name, columns)
        # Idempotent restarts keep data and add no destructive changes.
        first = GoalService()
        second = GoalService()
        versions = second.list_plan_versions(self.goal_id)
        self.assertEqual(versions, [])
        self.assertEqual(first.current_plan(self.goal_id)["objective_snapshot"],
                         "Deliver the G6 vertical slice")

    def test_replan_versions_current_diff_objective_and_prior_snapshot(self):
        mission_id = missions.create_mission(None, "Existing mission", "work")
        linked = self.services._goal_service().link_goal_mission(
            self.goal_id, mission_id, milestone_id=self.alpha["id"])
        self.assertTrue(linked["id"])
        result = self.replan([
            {"key": "a", "title": "Alpha", "priority": "P0", "risk": "low",
             "validation_strategy": "unit tests", "mission_intent": "build"},
            {"key": "b", "title": "Beta", "dependencies": ["a"]},
            {"key": "c", "title": "Gamma", "dependencies": ["b"],
             "risk": "high", "validation_strategy": "e2e",
             "mission_intent": "verify"},
        ], trigger="evidence", evidence=["test:pytest::1"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["version"]["version"], 1)
        self.assertTrue(result["version"]["is_current"])
        self.assertEqual(result["diff"]["counts"], {"added": 1, "removed": 0,
                                                     "changed": 1, "unchanged": 1})
        self.assertEqual(result["version"]["trigger"], "evidence")
        self.assertEqual(result["version"]["evidence_refs"], ["test:pytest::1"])
        self.assertEqual(result["goal"]["objective"],
                         "Deliver the G6 vertical slice")
        milestones = {item["title"]: item for item in result["milestones"]}
        self.assertEqual(milestones["Alpha"]["id"], self.alpha["id"])
        self.assertEqual(milestones["Alpha"]["priority"], "P0")
        self.assertEqual(milestones["Alpha"]["risk"], "low")
        self.assertEqual(milestones["Alpha"]["validation_strategy"], "unit tests")
        self.assertEqual(milestones["Alpha"]["mission_intent"], "build")
        self.assertEqual(milestones["Gamma"]["risk"], "high")
        self.assertEqual(milestones["Gamma"]["validation_strategy"], "e2e")
        self.assertEqual(milestones["Gamma"]["mission_intent"], "verify")
        self.assertEqual(len(self.services.goal_plan_versions(self.goal_id)["versions"]),
                         1)
        current = self.services.goal_current_plan(self.goal_id)["plan"]
        self.assertEqual(current["version"], 1)
        self.assertEqual(self.services.goal_plan_diff(self.goal_id)["diff"]["counts"],
                         result["diff"]["counts"])
        links = self.services.goal_links(self.goal_id)["links"]
        self.assertEqual(links[0]["mission_id"], mission_id)
        self.assertEqual(links[0]["milestone_id"], self.alpha["id"])
        self.assertEqual(links[0]["mission_status"], "pending")
        # Second replan preserves version 1 and makes version 2 current.
        second = self.replan([
            {"key": "a", "title": "Alpha", "priority": "P2"},
            {"key": "d", "title": "Delta", "dependencies": ["a"]},
        ], rationale="constraint changed", trigger="constraint")
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["version"]["version"], 2)
        versions = self.services.goal_plan_versions(self.goal_id)["versions"]
        self.assertEqual([item["version"] for item in versions], [2, 1])
        self.assertTrue(versions[0]["is_current"])
        self.assertFalse(versions[1]["is_current"])
        self.assertEqual([item["title"] for item in versions[1]["milestones"]],
                         ["Alpha", "Beta", "Gamma"])
        self.assertEqual(second["diff"]["removed"], ["Beta", "Gamma"])
        self.assertEqual(second["diff"]["added"], ["Delta"])
        self.assertEqual(second["goal"]["objective"],
                         "Deliver the G6 vertical slice")

    def test_rationale_trigger_and_evidence_validation(self):
        plan = [{"title": "Alpha"}]
        service = self.services._goal_service()
        with self.assertRaises(GoalValidationError):
            service.replan_goal(self.goal_id, plan, "")
        with self.assertRaises(GoalValidationError):
            service.replan_goal(self.goal_id, plan, "x", trigger="bogus")
        with self.assertRaises(GoalValidationError):
            service.replan_goal(self.goal_id, plan, "x", trigger="evidence",
                                evidence_refs=[])
        self.assertEqual(self.services.goal_plan_versions(self.goal_id)["total"], 0)
        self.assertEqual(self.services.goal_plan_versions(self.goal_id)["versions"], [])
        # facade surfaces the same validation as structured errors
        bad = self.replan(plan, rationale="")
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["error"]["code"], "validation")
        # failure/constraint triggers work without model/network calls.
        self.assertTrue(self.replan(plan, trigger="failure",
                                    evidence=["build:failed"])["ok"])
        self.assertTrue(self.replan(plan, trigger="constraint")["ok"])

    def test_plan_validation_failures_do_not_mutate_current_plan(self):
        before = self.services.goal_milestones(self.goal_id)["milestones"]
        failures = [
            [],
            [{"title": "Alpha"}, {"title": "Alpha"}],
            [{"key": "a", "title": "A"}, {"key": "a", "title": "B"}],
            [{"title": "A", "bogus": True}],
            [{"title": "A", "objective": "rewritten"}],
            [{"key": "a", "title": "A", "dependencies": ["a"]}],
            [{"key": "a", "title": "A", "dependencies": ["b"]},
             {"key": "b", "title": "B", "dependencies": ["a"]}],
            [{"title": "A", "dependencies": [9999]}],
            [{"title": "A", "dependencies": ["missing"]}],
        ]
        service = self.services._goal_service()
        for plan in failures:
            with self.assertRaises(GoalDecompositionError):
                service.replan_goal(self.goal_id, plan, "validation probe")
            facade = self.replan(plan)
            self.assertFalse(facade["ok"])
            self.assertEqual(facade["error"]["code"], "decomposition")
            self.assertEqual(self.services.goal_milestones(self.goal_id)["milestones"],
                             before)
            self.assertEqual(self.services.goal_plan_versions(self.goal_id)["total"], 0)
        with self.assertRaises(GoalLifecycleError):
            self.services._goal_service().cancel_goal(self.goal_id)
            self.services._goal_service().replan_goal(
                self.goal_id, [{"title": "Alpha"}], "terminal probe")
        self.assertEqual(self.services.goal_plan_versions(self.goal_id)["total"], 0)

    def test_objective_immutable_and_existing_mission_links_only(self):
        conn = init_db()
        try:
            before = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        finally:
            conn.close()
        mission_id = missions.create_mission(None, "Existing mission", "work")
        self.services._goal_service().link_goal_mission(self.goal_id, mission_id)
        result = self.replan([{"title": "Alpha"}, {"title": "Beta",
                                                   "dependencies": [self.alpha["id"]]}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["goal"]["objective"],
                         "Deliver the G6 vertical slice")
        links = self.services.goal_links(self.goal_id)["links"]
        self.assertEqual(links[0]["mission_id"], mission_id)
        self.assertEqual(links[0]["mission_title"], "Existing mission")
        conn = init_db()
        try:
            after = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(after, before + 1)

    def test_activity_and_queue_states(self):
        no_links = self.services.goal_queue(self.goal_id)
        self.assertTrue(no_links["ok"])
        self.assertFalse(no_links["linked"])
        self.assertEqual(no_links["state"], "not_connected")
        mission_id = missions.create_mission(None, "Existing mission", "work")
        self.services._goal_service().link_goal_mission(self.goal_id, mission_id)
        linked = self.services.goal_queue(self.goal_id)
        self.assertTrue(linked["linked"])
        self.assertEqual(linked["state"], "linked_not_queued")
        # Existing supervisor queue row -> available, still no execution.
        conn = init_db()
        try:
            with conn:
                conn.execute("INSERT INTO projects (name, root) VALUES (?,?)",
                             ("test", str(self.project_dir)))
                project_id = conn.execute(
                    "SELECT last_insert_rowid()").fetchone()[0]
                now = datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    "INSERT INTO mission_queue (project_id, mission_id, state, "
                    "priority, idempotency_key, goal, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (project_id, mission_id, "queued", "P1",
                     "g6-test-" + str(mission_id), "work", now, now))
            queue_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        finally:
            conn.close()
        available = self.services.goal_queue(self.goal_id)
        self.assertEqual(available["state"], "available")
        self.assertTrue(available["queue"][0]["queue_id"])
        # Replanning records an activity entry too.
        replanned = self.replan([{"title": "Alpha"}, {"title": "Beta",
                                                     "dependencies": [self.alpha["id"]]}])
        self.assertTrue(replanned["ok"], replanned)
        # Complete the goal with verified evidence to record completion/verification activity.
        for milestone in self.services.goal_milestones(self.goal_id)["milestones"]:
            self.services.goal_milestone_update(milestone["id"], status="completed")
        complete = self.services.goal_complete(self.goal_id, EVIDENCE, CRITERIA)
        self.assertTrue(complete["ok"], complete)
        activity = self.services.goal_activity(self.goal_id)["activity"]
        kinds = [item["event_kind"] for item in activity]
        self.assertIn("goal_replanned", kinds)
        self.assertIn("goal_verified", kinds)
        self.assertIn("goal_completed", kinds)
        self.assertEqual(self.services.goal_get(self.goal_id)["goal"]["status"],
                         "completed")

    def test_restart_persists_versions(self):
        result = self.replan([{"title": "Alpha", "risk": "medium"}])
        self.assertTrue(result["ok"])
        self.services._db.close()
        restarted = GoalService()
        versions = restarted.list_plan_versions(self.goal_id)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["milestones"][0]["risk"], "medium")
        self.assertEqual(restarted.get_goal(self.goal_id)["objective"],
                         "Deliver the G6 vertical slice")

    # ---------------------------------------------------------------- CLI
    def run_cli(self, args, stdin_text=""):
        out, err = io.StringIO(), io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = cli.main(args)
                except SystemExit as exc:
                    code = int(exc.code or 0)
        finally:
            sys.stdin = old_stdin
        return code, out.getvalue(), err.getvalue()

    def test_cli_replan_versions_links_activity_queue(self):
        mission_id = missions.create_mission(None, "Existing mission", "work")
        self.services._goal_service().link_goal_mission(self.goal_id, mission_id)
        self.services._db.close()
        plan = [{"key": "a", "title": "Alpha", "risk": "low"},
                {"key": "c", "title": "Gamma", "dependencies": ["a"],
                 "validation_strategy": "e2e", "mission_intent": "verify"}]
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        code, out, err = self.run_cli(["goal", "replan", str(self.goal_id),
                                       "--plan", str(plan_path),
                                       "--rationale", "evidence changed",
                                       "--trigger", "evidence",
                                       "--evidence-json", json.dumps(["test:pytest::1"]),
                                       "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["version"]["version"], 1)
        self.assertEqual(payload["diff"]["counts"]["added"], 1)
        code, out, err = self.run_cli(["goal", "versions", str(self.goal_id),
                                       "--diff", "--json"])
        self.assertEqual(code, 0, err)
        versions = json.loads(out)
        self.assertEqual(len(versions["versions"]), 1)
        self.assertEqual(versions["diff"]["added"], ["Gamma"])
        code, out, err = self.run_cli(["goal", "versions", str(self.goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("v1", out)
        code, out, err = self.run_cli(["goal", "links", str(self.goal_id), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["links"][0]["mission_id"], mission_id)
        code, out, err = self.run_cli(["goal", "links", str(self.goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("Existing mission", out)
        code, out, err = self.run_cli(["goal", "activity", str(self.goal_id),
                                       "--json"])
        self.assertEqual(code, 0)
        self.assertTrue(any(item["event_kind"] == "goal_replanned"
                            for item in json.loads(out)["activity"]))
        code, out, err = self.run_cli(["goal", "activity", str(self.goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("Goal replanned", out)
        code, out, err = self.run_cli(["goal", "queue", str(self.goal_id), "--json"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["linked"])
        code, out, err = self.run_cli(["goal", "queue", str(self.goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("linked_not_queued", out)

    def test_cli_exit_codes_and_validation(self):
        self.services._db.close()
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps([{"title": "Alpha"}]), encoding="utf-8")
        code, out, err = self.run_cli(["goal", "replan", str(self.goal_id),
                                       "--plan", str(plan_path)])
        self.assertEqual(code, 2)  # --rationale is required by argparse
        code, out, err = self.run_cli(["goal", "replan", str(self.goal_id),
                                       "--plan", str(plan_path),
                                       "--rationale", "x", "--trigger", "bogus"])
        self.assertEqual(code, 2)
        code, out, err = self.run_cli(["goal", "replan", "9999",
                                       "--plan", str(plan_path),
                                       "--rationale", "x", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")
        bad_plan = self.root / "bad.json"
        bad_plan.write_text(json.dumps([{"title": "Alpha"},
                                        {"title": "Alpha"}]), encoding="utf-8")
        code, out, err = self.run_cli(["goal", "replan", str(self.goal_id),
                                       "--plan", str(bad_plan),
                                       "--rationale", "x", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "decomposition")
        malformed = self.root / "malformed.json"
        malformed.write_text("{oops", encoding="utf-8")
        code, out, err = self.run_cli(["goal", "replan", str(self.goal_id),
                                       "--plan", str(malformed),
                                       "--rationale", "x"])
        self.assertEqual(code, 2)
        # stdin plan support
        code, out, err = self.run_cli(["goal", "replan", str(self.goal_id),
                                       "--plan", "-", "--rationale", "stdin plan",
                                       "--json"],
                                      stdin_text=json.dumps([{"title": "Alpha"}]))
        self.assertEqual(code, 0, err)

    def test_cli_db_isolation_and_no_execution_imports(self):
        self.services._db.close()
        old = os.environ["NL_DATA_DIR"]
        os.environ["NL_DATA_DIR"] = str(self.root / "other-data")
        try:
            code, out, err = self.run_cli(["goal", "links", str(self.goal_id),
                                           "--json"])
            self.assertEqual(code, 1)
            code, out, err = self.run_cli(["goal", "queue", str(self.goal_id),
                                           "--json"])
            self.assertEqual(code, 1)
        finally:
            os.environ["NL_DATA_DIR"] = old
        source = (REPO_ROOT / "nl_coding_agent" / "cli.py").read_text(encoding="utf-8")
        start = source.index('if command == "replan":')
        end = source.index('if command == "verify":', start)
        block = source[start:end]
        for forbidden in ("MultiAgentOrchestrator", "import requests",
                          "import urllib", "import socket", "PySide6", "ollama"):
            self.assertNotIn(forbidden, block)

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    unittest.main()

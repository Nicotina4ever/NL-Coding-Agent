"""Tests for the goal CLI command group (persist only, no execution)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import nl_coding_agent.cli as cli  # noqa: E402
from nl_coding_agent.persistence.database import init_db  # noqa: E402


class GoalCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.data_dir = self.root / "data"
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "README.md").write_text("# demo" + chr(10), encoding="utf-8")
        self._old_env = os.environ.get("NL_DATA_DIR")
        os.environ["NL_DATA_DIR"] = str(self.data_dir)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("NL_DATA_DIR", None)
        else:
            os.environ["NL_DATA_DIR"] = self._old_env

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

    def create_goal(self, *extra):
        code, out, err = self.run_cli(["goal", "create", "Ship G2 CLI",
                                       "--title", "G2 CLI", "--json", *extra])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["ok"], True)
        return json.loads(out)["goal"]["id"]

    def test_help_documents_no_autonomous_execution_and_rejects_flags(self):
        with self.assertRaises(SystemExit) as context:
            cli.main(["goal", "--help"])
        self.assertEqual(int(context.exception.code or 0), 0)
        code, out, err = self.run_cli(["goal", "create", "x", "--run"])
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", err)
        code, out, err = self.run_cli(["goal", "create"])
        self.assertEqual(code, 2)
        self.assertIn("objective", err.lower())

    def test_create_list_show_text_and_json(self):
        goal_id = self.create_goal("--priority", "P0", "--acceptance", "works",
                                   "--reference", "owner=team",
                                   "--project", str(self.project))
        code, out, err = self.run_cli(["goal", "list", "--json"])
        self.assertEqual(code, 0, err)
        listed = json.loads(out)
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["total"], 1)
        goal = listed["goals"][0]
        self.assertEqual(goal["title"], "G2 CLI")
        self.assertEqual(goal["priority"], "P0")
        self.assertEqual(goal["acceptance_criteria"], ["works"])
        self.assertEqual(goal["reference_metadata"], {"owner": "team"})
        self.assertIsNotNone(goal["project_id"])
        code, out, err = self.run_cli(["goal", "list"])
        self.assertEqual(code, 0)
        self.assertIn("G2 CLI", out)
        code, out, err = self.run_cli(["goal", "show", str(goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("Objective: Ship G2 CLI", out)
        code, out, err = self.run_cli(["goal", "show", str(goal_id), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["goal"]["id"], goal_id)
        code, out, err = self.run_cli(["goal", "list", "--priority", "P0", "--json"])
        self.assertEqual(json.loads(out)["total"], 1)
        code, out, err = self.run_cli(["goal", "list", "--priority", "P3", "--json"])
        self.assertEqual(json.loads(out)["total"], 0)

    def test_lifecycle_text_json_and_invalid_transition(self):
        goal_id = self.create_goal()
        for command, expected in (("activate", "active"), ("pause", "paused"),
                                  ("resume", "active")):
            code, out, err = self.run_cli(["goal", command, str(goal_id), "--json"])
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["goal"]["status"], expected)
        code, out, err = self.run_cli(["goal", "block", str(goal_id),
                                       "--reason", "wait", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["goal"]["status"], "blocked")
        code, out, err = self.run_cli(["goal", "unblock", str(goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("active", out)
        code, out, err = self.run_cli(["goal", "cancel", str(goal_id), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["goal"]["status"], "cancelled")
        code, out, err = self.run_cli(["goal", "activate", str(goal_id), "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "lifecycle")

    def test_decompose_next_progress_validation(self):
        goal_id = self.create_goal()
        self.assertEqual(self.run_cli(["goal", "activate", str(goal_id)])[0], 0)
        plan = [{"key": "a", "title": "A"},
                {"key": "b", "title": "B", "dependencies": ["a"]}]
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        code, out, err = self.run_cli(["goal", "decompose", str(goal_id),
                                       "--plan", str(plan_path), "--json"])
        self.assertEqual(code, 0, err)
        decomposed = json.loads(out)
        self.assertEqual(len(decomposed["milestones"]), 2)
        code, out, err = self.run_cli(["goal", "next", "--goal-id", str(goal_id),
                                       "--json"])
        self.assertEqual(code, 0, err)
        next_payload = json.loads(out)
        self.assertEqual(len(next_payload["work"]), 1)
        self.assertEqual(next_payload["work"][0]["title"], "A")
        code, out, err = self.run_cli(["goal", "progress", str(goal_id), "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["progress"]["milestones_total"], 2)
        code, out, err = self.run_cli(["goal", "progress", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["summary"]["goals_total"], 1)
        code, out, err = self.run_cli(["goal", "decompose", str(goal_id),
                                       "--plan", "-", "--json"],
                                      stdin_text=json.dumps([{"title": "C"}]))
        self.assertEqual(code, 0, err)
        bad_path = self.root / "bad.json"
        bad_path.write_text(json.dumps([{"title": "A"}]), encoding="utf-8")
        code, out, err = self.run_cli(["goal", "decompose", str(goal_id),
                                       "--plan", str(bad_path), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "decomposition")
        malformed = self.root / "malformed.json"
        malformed.write_text("{not json", encoding="utf-8")
        code, out, err = self.run_cli(["goal", "decompose", str(goal_id),
                                       "--plan", str(malformed)])
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)
        code, out, err = self.run_cli(["goal", "decompose", str(goal_id),
                                       "--plan", str(self.root / "missing.json")])
        self.assertEqual(code, 2)

    def test_validation_errors_missing_goal_and_no_mission_creation(self):
        code, out, err = self.run_cli(["goal", "create", "x", "--priority", "P9"])
        self.assertEqual(code, 2)
        code, out, err = self.run_cli(["goal", "create", "x", "--dependency", "999", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "dependency")
        for args in (["goal", "show", "999"], ["goal", "activate", "999"],
                     ["goal", "progress", "999"]):
            code, out, err = self.run_cli(args + ["--json"])
            self.assertEqual(code, 1, args)
            self.assertEqual(json.loads(out)["error"]["code"], "not_found")
        conn = init_db()
        try:
            missions_before = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        finally:
            conn.close()
        goal_id = self.create_goal()
        self.run_cli(["goal", "activate", str(goal_id)])
        self.run_cli(["goal", "next", "--json"])
        self.run_cli(["goal", "progress", str(goal_id), "--json"])
        conn = init_db()
        try:
            missions_after = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(missions_after, missions_before)

    def test_goal_commands_need_no_models_config_and_isolate_databases(self):
        code, out, err = self.run_cli(["--models", str(self.root / "missing.yaml"),
                                       "goal", "list", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["total"], 0)
        goal_id = self.create_goal()
        other_dir = self.root / "other-data"
        old = os.environ["NL_DATA_DIR"]
        os.environ["NL_DATA_DIR"] = str(other_dir)
        try:
            code, out, err = self.run_cli(["goal", "list", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["total"], 0)
            code, out, err = self.run_cli(["goal", "show", str(goal_id), "--json"])
            self.assertEqual(code, 1)
        finally:
            os.environ["NL_DATA_DIR"] = old

    def test_goal_replan_versions_links_activity_queue_cli(self):
        from nl_coding_agent.app.services import AppServices
        from nl_coding_agent.persistence import missions
        services = AppServices()
        try:
            goal = services.goal_create("CLI G6", title="CLI G6",
                                        acceptance_criteria=["works"])["goal"]
            goal_id = goal["id"]
            services.goal_activate(goal_id)
            services.goal_decompose(goal_id, [
                {"key": "a", "title": "Alpha"},
                {"key": "b", "title": "Beta", "dependencies": ["a"]},
            ])
            mission_id = missions.create_mission(None, "Existing mission", "work")
            services._goal_service().link_goal_mission(goal_id, mission_id)
        finally:
            services._db.close()
        plan_path = self.root / "g6-plan.json"
        plan_path.write_text(json.dumps([{"title": "Alpha", "risk": "low"},
                                         {"title": "Gamma"}]), encoding="utf-8")
        code, out, err = self.run_cli(["goal", "replan", str(goal_id),
                                       "--plan", str(plan_path),
                                       "--rationale", "evidence changed",
                                       "--trigger", "evidence",
                                       "--evidence-json", json.dumps(["test:x::1"]),
                                       "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["version"]["version"], 1)
        code, out, err = self.run_cli(["goal", "versions", str(goal_id),
                                       "--diff", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["diff"]["added"], ["Gamma"])
        code, out, err = self.run_cli(["goal", "links", str(goal_id), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["links"][0]["mission_id"], mission_id)
        code, out, err = self.run_cli(["goal", "activity", str(goal_id), "--json"])
        self.assertEqual(code, 0)
        self.assertIn("goal_replanned",
                      [item["event_kind"] for item in json.loads(out)["activity"]])
        code, out, err = self.run_cli(["goal", "queue", str(goal_id), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["state"], "linked_not_queued")
        code, out, err = self.run_cli(["goal", "replan", str(goal_id),
                                       "--plan", str(plan_path)])
        self.assertEqual(code, 2)  # rationale required


    def test_goal_approve_tasks_workers_cli(self):
        from nl_coding_agent.app.services import AppServices
        services = AppServices()
        try:
            goal = services.goal_create("CLI G8", title="CLI G8",
                                        acceptance_criteria=["works"])["goal"]
            goal_id = goal["id"]
            services.goal_activate(goal_id)
            services.goal_replan(goal_id, [{"title": "A"}], "initial",
                                 trigger="manual")
        finally:
            services._db.close()
        code, out, err = self.run_cli(["goal", "approve", str(goal_id),
                                       "--rationale", "cli", "--json"])
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["approved"])
        code, out, err = self.run_cli(["goal", "approve", str(goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("already approved", out.lower())
        code, out, err = self.run_cli(["goal", "tasks", str(goal_id), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["state"], "not_connected")
        code, out, err = self.run_cli(["goal", "workers", str(goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("no linked", out.lower())
        code, out, err = self.run_cli(["goal", "approve", "9999", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")


    def test_static_no_execution_or_network_imports_in_goal_cli(self):
        source = (REPO_ROOT / "nl_coding_agent" / "cli.py").read_text(encoding="utf-8")
        start = source.index("def _dispatch_goal(")
        end = source.index("\ndef main(", start)
        block = source[start:end]
        for forbidden in ("MultiAgentOrchestrator", "orchestrator", "import requests",
                          "import urllib", "import socket", "PySide6", "crewai",
                          "ollama", "subprocess"):
            self.assertNotIn(forbidden, block, forbidden)
        help_start = source.index('"goal", help=')
        help_block = source[help_start:help_start + 1600]
        self.assertIn("no autonomous execution", help_block.lower())
        self.assertIn("GOAL_GROUP_EPILOG", help_block)
        self.assertIn("NL_DATA_DIR", source)
        self.assertIn("reset", source.lower())


if __name__ == "__main__":
    unittest.main()

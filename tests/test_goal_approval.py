"""Tests for G8 plan approval, linked task/queue/worker inspection and CLI parity."""
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
    GoalNotFoundError, GoalService, GoalValidationError,
)
from nl_coding_agent.persistence import missions  # noqa: E402
from nl_coding_agent.persistence.database import init_db  # noqa: E402


class GoalApprovalTests(unittest.TestCase):
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
        self.goal = self.services.goal_create(
            "Approve and inspect plans", title="G8",
            acceptance_criteria=["works"])["goal"]
        self.goal_id = self.goal["id"]
        self.services.goal_activate(self.goal_id)
        self.replanned = self.services.goal_replan(
            self.goal_id, [{"title": "A"}, {"title": "B"}],
            "initial plan", trigger="manual")

    def tearDown(self):
        try:
            self.services._db.close()
        except Exception:
            pass
        if self._old_env is None:
            os.environ.pop("NL_DATA_DIR", None)
        else:
            os.environ["NL_DATA_DIR"] = self._old_env

    def audit_rows(self):
        conn = init_db()
        try:
            return conn.execute(
                "SELECT event_kind, payload FROM events WHERE source='goals' "
                "ORDER BY id").fetchall()
        finally:
            conn.close()

    def test_schema_has_additive_approval_columns(self):
        conn = init_db()
        try:
            first = [row[1] for row in conn.execute(
                "PRAGMA table_info(goal_plan_versions)")]
        finally:
            conn.close()
        for name in ("approved", "approved_at", "approved_by", "approval_note"):
            self.assertIn(name, first)
        # Idempotent schema restart preserves the plan version and pending status.
        second = AppServices()
        try:
            plan = second.goal_current_plan(self.goal_id)["plan"]
            self.assertFalse(plan["approved"])
            self.assertEqual(plan["approval_status"], "pending")
        finally:
            second._db.close()

    def test_approve_current_default_and_explicit_version(self):
        result = self.services.goal_approve_plan(
            self.goal_id, rationale="looks good", approver="owner")
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["already_approved"])
        self.assertTrue(result["approved"])
        self.assertEqual(result["approval_status"], "approved")
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["approved_by"], "owner")
        self.assertEqual(result["approval_note"], "looks good")
        self.assertTrue(result["plan"]["approved"])
        current = self.services.goal_current_plan(self.goal_id)["plan"]
        self.assertTrue(current["approved"])
        self.assertTrue(current["approved_at"])
        status = self.services.goal_approve_plan(
            self.goal_id, version=1, rationale="again")
        self.assertTrue(status["already_approved"])
        self.assertEqual(status["version"], 1)
        self.assertEqual(self.audit_rows()[-1]["event_kind"], "plan_approved")
        self.assertIn(str(self.goal_id), str(self.audit_rows()[-1]["payload"]))

    def test_approve_missing_plan_version_and_validation(self):
        no_plan = self.services.goal_create("No plan", title="No plan")["goal"]
        missing = self.services.goal_approve_plan(no_plan["id"])
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "not_found")
        invalid = self.services.goal_approve_plan(self.goal_id, version=99)
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["error"]["code"], "not_found")
        with self.assertRaises(GoalValidationError):
            self.services._goal_service().approve_plan(
                self.goal_id, approver="")
        with self.assertRaises(GoalNotFoundError):
            self.services._goal_service().approve_plan(
                self.goal_id, version=999)
        # No approval happened for the invalid inputs.
        current = self.services.goal_current_plan(self.goal_id)["plan"]
        self.assertFalse(current["approved"])
        self.assertEqual([row["event_kind"] for row in self.audit_rows()
                          if row["event_kind"] == "plan_approved"], [])

    def test_approval_is_idempotent_and_replan_creates_unapproved_version(self):
        first = self.services.goal_approve_plan(self.goal_id)
        self.assertTrue(first["ok"])
        audit_before = len([row for row in self.audit_rows()
                            if row["event_kind"] == "plan_approved"])
        second = self.services.goal_approve_plan(self.goal_id)
        self.assertTrue(second["already_approved"])
        audit_after = len([row for row in self.audit_rows()
                           if row["event_kind"] == "plan_approved"])
        self.assertEqual(audit_after, audit_before)
        replanned = self.services.goal_replan(
            self.goal_id, [{"title": "A"}, {"title": "C"}],
            "new evidence", trigger="evidence", evidence_refs=["test:x"])
        self.assertTrue(replanned["ok"])
        self.assertEqual(replanned["version"]["version"], 2)
        self.assertFalse(replanned["version"]["approved"])
        self.assertEqual(replanned["version"]["approval_status"], "pending")
        versions = self.services.goal_plan_versions(self.goal_id)["versions"]
        self.assertTrue(versions[1]["approved"])
        self.assertFalse(versions[0]["approved"])
        current = self.services.goal_current_plan(self.goal_id)["plan"]
        self.assertFalse(current["approved"])
        approved = self.services.goal_approve_plan(self.goal_id, version=2)
        self.assertTrue(approved["ok"])
        self.assertEqual(approved["version"], 2)
        self.assertTrue(approved["approved"])

    def test_approval_and_inspections_persist_across_restart(self):
        self.assertTrue(self.services.goal_approve_plan(self.goal_id)["ok"])
        self.services._db.close()
        restarted = AppServices()
        try:
            plan = restarted.goal_current_plan(self.goal_id)["plan"]
            self.assertTrue(plan["approved"])
            self.assertEqual(plan["approval_status"], "approved")
            self.assertTrue(any(row["event_kind"] == "plan_approved"
                                for row in self.audit_rows()))
        finally:
            restarted._db.close()


class LinkedInspectionTests(GoalApprovalTests):
    def _seed_work(self):
        conn = init_db()
        try:
            with conn:
                conn.execute("INSERT INTO projects (name, root) VALUES (?,?)",
                             ("test", str(self.project_dir)))
                project_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            linked_mission = missions.create_mission(
                project_id, "Linked mission", "do work")
            unlinked_mission = missions.create_mission(
                project_id, "Unlinked mission", "other work")
            linked_task = missions.add_task(
                linked_mission, "Build", "implement", "developer")
            missions.add_task(linked_mission, "Review", "review", "reviewer")
            unassigned = missions.add_task(
                linked_mission, "Unassigned", "later", None)
            unlinked_task = missions.add_task(
                unlinked_mission, "Hidden", "not linked", "developer")
            now = datetime.now().isoformat(timespec="seconds")
            with conn:
                conn.execute(
                    "INSERT INTO mission_queue (project_id, mission_id, state, "
                    "priority, idempotency_key, goal, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (project_id, linked_mission, "queued", "P1", "g8-linked",
                     "goal", now, now))
                conn.execute(
                    "INSERT INTO mission_queue (project_id, mission_id, state, "
                    "priority, idempotency_key, goal, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (project_id, unlinked_mission, "queued", "P1", "g8-unlinked",
                     "goal", now, now))
                conn.execute(
                    "INSERT INTO supervisor_runs (project_id, mode, status, "
                    "owner_id, owner_pid, config_json, started_at, heartbeat_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (project_id, "sequential", "running", "owner", 123, "{}",
                     now, now))
        finally:
            conn.close()
        self.services._goal_service().link_goal_mission(
            self.goal_id, linked_mission)
        return {"project_id": project_id, "linked_mission": linked_mission,
                "unlinked_mission": unlinked_mission,
                "linked_task": linked_task, "unlinked_task": unlinked_task,
                "unassigned": unassigned}

    def test_mission_tasks_only_linked_and_read_only(self):
        seed = self._seed_work()
        conn = init_db()
        try:
            before = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
            statuses = [row[0] for row in conn.execute(
                "SELECT status FROM missions ORDER BY id")]
        finally:
            conn.close()
        result = self.services.goal_mission_tasks(self.goal_id)
        self.assertTrue(result["ok"])
        self.assertTrue(result["linked"])
        self.assertEqual([mission["mission_id"]
                          for mission in result["missions"]],
                         [seed["linked_mission"]])
        task_ids = [task["id"] for task in result["tasks"]]
        self.assertIn(seed["linked_task"], task_ids)
        self.assertIn(seed["unassigned"], task_ids)
        self.assertNotIn(seed["unlinked_task"], task_ids)
        for task in result["tasks"]:
            self.assertIn("depends_on", task)
            self.assertIn("agent_role", task)
        conn = init_db()
        try:
            after = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
            statuses_after = [row[0] for row in conn.execute(
                "SELECT status FROM missions ORDER BY id")]
        finally:
            conn.close()
        self.assertEqual(after, before)
        self.assertEqual(statuses_after, statuses)

    def test_queue_entries_only_linked_and_read_only(self):
        seed = self._seed_work()
        result = self.services.goal_queue_entries(self.goal_id)
        self.assertTrue(result["ok"])
        self.assertTrue(result["linked"])
        self.assertEqual(len(result["entries"]), 1)
        entry = result["entries"][0]
        self.assertEqual(entry["mission_id"], seed["linked_mission"])
        for name in ("state", "priority", "attempts", "lease_owner",
                     "claimed_at", "scheduled_at", "finished_at"):
            self.assertIn(name, entry)
        self.assertEqual(entry["state"], "queued")
        conn = init_db()
        try:
            count = conn.execute("SELECT COUNT(1) FROM mission_queue").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 2)

    def test_active_work_only_linked_and_explicit_empty_states(self):
        seed = self._seed_work()
        result = self.services.goal_active_work(self.goal_id)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "active")
        roles = {task["agent_role"] for task in result["assigned_tasks"]}
        self.assertEqual(roles, {"developer", "reviewer"})
        self.assertNotIn(seed["unlinked_task"],
                         [task["id"] for task in result["assigned_tasks"]])
        self.assertTrue(result["supervisor_runs"])
        run = result["supervisor_runs"][0]
        for name in ("id", "mode", "status", "owner_id", "heartbeat_at", "owner_pid"):
            self.assertIn(name, run)
        empty = self.services.goal_create("Empty", title="Empty")["goal"]
        tasks = self.services.goal_mission_tasks(empty["id"])
        queue = self.services.goal_queue_entries(empty["id"])
        work = self.services.goal_active_work(empty["id"])
        self.assertEqual(tasks["state"], "not_connected")
        self.assertEqual(queue["state"], "not_connected")
        self.assertEqual(work["state"], "not_connected")
        self.assertEqual(work["assigned_tasks"], [])
        self.assertEqual(work["supervisor_runs"], [])
        # A linked mission with no assigned tasks is idle, not active.
        idle_goal = self.services.goal_create("Idle", title="Idle")["goal"]
        mission_id = missions.create_mission(None, "Idle mission", "idle")
        self.services._goal_service().link_goal_mission(
            idle_goal["id"], mission_id)
        idle = self.services.goal_active_work(idle_goal["id"])
        self.assertEqual(idle["state"], "idle")

    def test_inspection_never_executes_or_creates_workers(self):
        self._seed_work()
        conn = init_db()
        try:
            missions_before = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
            tasks_before = conn.execute("SELECT COUNT(1) FROM tasks").fetchone()[0]
        finally:
            conn.close()
        for _ in range(3):
            self.services.goal_mission_tasks(self.goal_id)
            self.services.goal_queue_entries(self.goal_id)
            self.services.goal_active_work(self.goal_id)
        conn = init_db()
        try:
            missions_after = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
            tasks_after = conn.execute("SELECT COUNT(1) FROM tasks").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(missions_after, missions_before)
        self.assertEqual(tasks_after, tasks_before)


class GoalApprovalCliTests(GoalApprovalTests):
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

    def test_cli_approve_tasks_workers_json_text_and_exit_codes(self):
        LinkedInspectionTests._seed_work(self)
        self.services._db.close()
        code, out, err = self.run_cli(["goal", "approve", str(self.goal_id),
                                       "--rationale", "cli approval", "--json"])
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["approved"])
        code, out, err = self.run_cli(["goal", "approve", str(self.goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("approved", out)
        self.assertIn("already", out.lower())
        code, out, err = self.run_cli(["goal", "tasks", str(self.goal_id), "--json"])
        self.assertEqual(code, 0, err)
        tasks_payload = json.loads(out)
        self.assertTrue(tasks_payload["linked"])
        self.assertEqual(len(tasks_payload["missions"]), 1)
        code, out, err = self.run_cli(["goal", "tasks", str(self.goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("Linked mission", out)
        code, out, err = self.run_cli(["goal", "workers", str(self.goal_id), "--json"])
        self.assertEqual(code, 0, err)
        workers_payload = json.loads(out)
        self.assertEqual(workers_payload["state"], "active")
        self.assertTrue(workers_payload["queue_entries"])
        code, out, err = self.run_cli(["goal", "workers", str(self.goal_id)])
        self.assertEqual(code, 0)
        self.assertIn("active work", out)
        code, out, err = self.run_cli(["goal", "approve", "9999", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")
        code, out, err = self.run_cli(["goal", "approve", str(self.goal_id),
                                       "--version", "99", "--json"])
        self.assertEqual(code, 1)
        code, out, err = self.run_cli(["goal", "approve"])
        self.assertEqual(code, 2)
        code, out, err = self.run_cli(["goal", "workers", "9999"])
        self.assertEqual(code, 1)

    def test_cli_empty_states_and_db_isolation(self):
        empty = self.services.goal_create("Empty", title="Empty")["goal"]
        self.services._db.close()
        code, out, err = self.run_cli(["goal", "tasks", str(empty["id"])])
        self.assertEqual(code, 0)
        self.assertIn("no linked", out.lower())
        code, out, err = self.run_cli(["goal", "workers", str(empty["id"]), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["state"], "not_connected")
        old = os.environ["NL_DATA_DIR"]
        os.environ["NL_DATA_DIR"] = str(self.root / "other-data")
        try:
            code, out, err = self.run_cli(["goal", "tasks", str(empty["id"])])
            self.assertEqual(code, 1)
            code, out, err = self.run_cli(["goal", "approve", str(empty["id"])])
            self.assertEqual(code, 1)
        finally:
            os.environ["NL_DATA_DIR"] = old

    def test_cli_rejects_execution_flags_and_no_network_imports(self):
        self.services._db.close()
        code, out, err = self.run_cli(["goal", "approve", str(self.goal_id), "--run"])
        self.assertEqual(code, 2)
        source = (REPO_ROOT / "nl_coding_agent" / "cli.py").read_text(encoding="utf-8")
        start = source.index('if command == "approve":')
        end = source.index('if command == "verify":', start)
        block = source[start:end]
        for forbidden in ("MultiAgentOrchestrator", "import requests",
                          "import urllib", "import socket", "PySide6", "ollama",
                          "subprocess"):
            self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()

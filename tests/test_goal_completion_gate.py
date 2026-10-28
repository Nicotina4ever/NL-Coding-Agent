"""Verification-gated goal completion through AppServices and CLI (stage-8 G5)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import nl_coding_agent.cli as cli  # noqa: E402
from nl_coding_agent.app.services import AppServices  # noqa: E402
from nl_coding_agent.persistence import goal_store  # noqa: E402
from nl_coding_agent.persistence.database import init_db  # noqa: E402

CRITERIA = [{"id": "C1", "text": "tests pass",
             "required_evidence_types": ["test"]}]
EVIDENCE = [{"type": "test", "source": "pytest:tests", "result": "pass",
             "trust": "trusted", "exit_code": 0}]


def _now(offset_seconds: int = 0) -> str:
    return (datetime.now() + timedelta(seconds=offset_seconds)).isoformat(
        timespec="seconds")


class GoalCompletionGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.data_dir = self.root / "data"
        self._old_env = os.environ.get("NL_DATA_DIR")
        os.environ["NL_DATA_DIR"] = str(self.data_dir)
        self.services = AppServices()

    def tearDown(self):
        try:
            self.services._db.close()
        except Exception:
            pass
        if self._old_env is None:
            os.environ.pop("NL_DATA_DIR", None)
        else:
            os.environ["NL_DATA_DIR"] = self._old_env

    def seed_goal(self, *, criteria=("tests pass",), milestone_status="completed"):
        result = self.services.goal_create(
            "Ship verified completion", title="Verified goal",
            acceptance_criteria=list(criteria))
        self.assertTrue(result["ok"], result)
        goal_id = result["goal"]["id"]
        self.assertTrue(self.services.goal_activate(goal_id)["ok"])
        milestone_id = None
        if milestone_status is not None:
            created = self.services.goal_milestone_create(goal_id, "Run tests")
            milestone_id = created["milestone"]["id"]
            self.assertTrue(self.services.goal_milestone_update(
                milestone_id, status=milestone_status)["ok"])
        return goal_id, milestone_id

    def status(self, goal_id):
        return self.services.goal_get(goal_id)["goal"]["status"]

    # ------------------------------------------------------------- facade
    def test_verified_only_completion_records_and_completes(self):
        goal_id, _milestone = self.seed_goal()
        read_only = self.services.goal_verify(goal_id, EVIDENCE, CRITERIA)
        self.assertTrue(read_only["ok"])
        self.assertEqual(read_only["verdict"], "verified")
        self.assertEqual(self.services.goal_verifications(goal_id)["total"], 0)
        self.assertEqual(self.status(goal_id), "active")
        result = self.services.goal_complete(goal_id, EVIDENCE, CRITERIA)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["verdict"], "verified")
        self.assertEqual(result["goal_status"], "completed")
        self.assertTrue(result["status_mutated"])
        self.assertIsNotNone(result["record_id"])
        records = self.services.goal_verifications(goal_id)["verifications"]
        self.assertEqual(records[0]["id"], result["record_id"])
        self.assertEqual(records[0]["verdict"], "verified")
        self.assertEqual(self.status(goal_id), "completed")
        false = self.services.goal_false_completions()
        self.assertTrue(false["ok"])
        self.assertEqual(false["count"], 0)

    def test_refusals_never_mutate_status(self):
        cases = [
            ("missing", [], CRITERIA),
            ("untrusted", [{"type": "test", "source": "model:self",
                            "result": "pass", "trust": "self"}], CRITERIA),
            ("contradicted", [{"type": "test", "source": "pytest:fail",
                               "exit_code": 1, "trust": "trusted"}], CRITERIA),
            ("stale", [{"type": "test", "source": "pytest:old",
                        "result": "pass", "trust": "trusted",
                        "timestamp": _now(-86400)}],
             [{"id": "C1", "text": "tests pass",
               "required_evidence_types": ["test"], "stale_after_s": 60}]),
            ("partial", [{"type": "test", "source": "pytest:partial",
                          "result": "pass", "trust": "trusted"}],
             [{"id": "C1", "text": "test+artifact",
               "required_evidence_types": ["test", "artifact"]}]),
        ]
        for name, evidence, criteria in cases:
            goal_id, _ = self.seed_goal(criteria=["tests pass"])
            before = self.status(goal_id)
            result = self.services.goal_complete(goal_id, evidence, criteria)
            self.assertFalse(result["ok"], name)
            self.assertEqual(result["outcome"], "refused", name)
            self.assertEqual(result["status_mutated"], False, name)
            self.assertEqual(result["goal_status"], before, name)
            self.assertEqual(self.status(goal_id), before, name)
            self.assertNotEqual(result["verdict"], "verified", name)
            self.assertIn("criteria", result)
            self.assertIn("blockers", result)
            self.assertIn("outstanding", result)
            self.assertIsNotNone(result["record_id"], name)
            records = self.services.goal_verifications(goal_id)["verifications"]
            self.assertEqual(records[0]["id"], result["record_id"], name)

    def test_goal_without_acceptance_criteria_refuses_with_missing_criteria(self):
        goal_id, _ = self.seed_goal(criteria=[])
        result = self.services.goal_complete(goal_id, EVIDENCE)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "missing_criteria")
        self.assertEqual(result["verdict"], "unverified")
        self.assertFalse(result["status_mutated"])
        self.assertEqual(self.status(goal_id), "active")
        self.assertTrue(any(blocker.get("code") == "no_acceptance_criteria"
                            for blocker in result["blockers"]))

    def test_completion_rejected_when_milestones_incomplete(self):
        goal_id, _ = self.seed_goal(milestone_status="pending")
        result = self.services.goal_complete(goal_id, EVIDENCE, CRITERIA)
        self.assertFalse(result["ok"])
        self.assertEqual(result["outcome"], "completion_rejected")
        self.assertEqual(result["verdict"], "verified")
        self.assertFalse(result["status_mutated"])
        self.assertEqual(self.status(goal_id), "active")
        self.assertEqual(result["error"]["code"], "lifecycle")
        self.assertIsNotNone(result["record_id"])

    def test_dry_run_does_not_change_status(self):
        goal_id, _ = self.seed_goal()
        result = self.services.goal_complete(goal_id, EVIDENCE, CRITERIA,
                                             dry_run=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["outcome"], "dry_run_verified")
        self.assertEqual(result["verdict"], "verified")
        self.assertFalse(result["status_mutated"])
        self.assertEqual(self.status(goal_id), "active")

    def test_goal_verify_is_read_only_and_false_completions_helper(self):
        goal_id, _ = self.seed_goal()
        before = self.status(goal_id)
        report = self.services.goal_verify(goal_id, EVIDENCE, CRITERIA)
        self.assertTrue(report["ok"])
        self.assertEqual(report["verdict"], "verified")
        self.assertEqual(self.status(goal_id), before)
        self.assertEqual(self.services.goal_verifications(goal_id)["total"], 0)
        # Simulate a legacy false completion directly in SQL, then detect read-only.
        goal_store.set_goal_status(goal_id, "completed")
        detected = self.services.goal_false_completions()
        self.assertTrue(detected["ok"])
        self.assertFalse(detected["clean"])
        self.assertEqual(detected["count"], 1)
        self.assertEqual(detected["false_completions"][0]["goal_id"], goal_id)
        self.assertEqual(self.status(goal_id), "completed")
        one = self.services.goal_false_completions(goal_id)
        self.assertEqual(one["count"], 1)

    def test_structured_errors_for_missing_goal_and_bad_evidence(self):
        missing = self.services.goal_complete(9999, EVIDENCE, CRITERIA)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "not_found")
        goal_id, _ = self.seed_goal()
        bad = self.services.goal_complete(goal_id, [{"type": "test"}], CRITERIA)
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["error"]["code"], "error")
        verify_bad = self.services.goal_verify(goal_id, [{"type": "test"}],
                                               CRITERIA)
        self.assertFalse(verify_bad["ok"])

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

    def close_services(self):
        self.services._db.close()

    def test_cli_verify_and_complete_text_json_and_exit_codes(self):
        goal_id, _ = self.seed_goal()
        self.close_services()
        evidence_path = self.root / "evidence.json"
        evidence_path.write_text(json.dumps(EVIDENCE), encoding="utf-8")
        criteria_path = self.root / "criteria.json"
        criteria_path.write_text(json.dumps(CRITERIA), encoding="utf-8")
        code, out, err = self.run_cli(["goal", "verify", str(goal_id),
                                       "--evidence", str(evidence_path),
                                       "--criteria", str(criteria_path), "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["verdict"], "verified")
        code, out, err = self.run_cli(["goal", "verify", str(goal_id),
                                       "--evidence-json", json.dumps(EVIDENCE),
                                       "--criteria-json", json.dumps(CRITERIA)])
        self.assertEqual(code, 0, err)
        self.assertIn("verified", out.lower())
        code, out, err = self.run_cli(["goal", "complete", str(goal_id),
                                       "--evidence-json", json.dumps(EVIDENCE),
                                       "--criteria-json", json.dumps(CRITERIA),
                                       "--dry-run", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["outcome"], "dry_run_verified")
        code, out, err = self.run_cli(["goal", "complete", str(goal_id),
                                       "--evidence-json", json.dumps(EVIDENCE),
                                       "--criteria-json", json.dumps(CRITERIA),
                                       "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["outcome"], "completed")
        self.assertEqual(json.loads(out)["goal_status"], "completed")
        code, out, err = self.run_cli(["goal", "complete", str(goal_id),
                                       "--json"])
        self.assertEqual(code, 2)
        self.assertIn("requires --evidence", err)

    def test_cli_refusal_and_validation_exit_codes(self):
        goal_id, _ = self.seed_goal()
        self.close_services()
        bad_evidence = json.dumps([{"type": "test", "source": "pytest:fail",
                                    "exit_code": 1, "trust": "trusted"}])
        code, out, err = self.run_cli(["goal", "verify", str(goal_id),
                                       "--evidence-json", bad_evidence,
                                       "--criteria-json", json.dumps(CRITERIA),
                                       "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["verdict"], "contradicted")
        code, out, err = self.run_cli(["goal", "complete", str(goal_id),
                                       "--evidence-json", bad_evidence,
                                       "--criteria-json", json.dumps(CRITERIA),
                                       "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["outcome"], "refused")
        code, out, err = self.run_cli(["goal", "complete", "9999",
                                       "--evidence-json", json.dumps(EVIDENCE),
                                       "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")
        malformed = self.root / "malformed.json"
        malformed.write_text("{oops", encoding="utf-8")
        code, out, err = self.run_cli(["goal", "verify", str(goal_id),
                                       "--evidence", str(malformed)])
        self.assertEqual(code, 2)
        self.assertIn("JSON", err)
        code, out, err = self.run_cli(["goal", "verify", str(goal_id),
                                       "--evidence-json", "[]",
                                       "--criteria-json", json.dumps(CRITERIA)])
        self.assertEqual(code, 1)

    def test_cli_stdin_and_db_isolation(self):
        goal_id, _ = self.seed_goal()
        self.close_services()
        code, out, err = self.run_cli(
            ["goal", "verify", str(goal_id), "--evidence", "-",
             "--criteria-json", json.dumps(CRITERIA), "--json"],
            stdin_text=json.dumps(EVIDENCE))
        self.assertEqual(code, 0, err)
        old = os.environ["NL_DATA_DIR"]
        os.environ["NL_DATA_DIR"] = str(self.root / "other-data")
        try:
            code, out, err = self.run_cli(["goal", "verify", str(goal_id),
                                           "--evidence-json", json.dumps(EVIDENCE),
                                           "--criteria-json", json.dumps(CRITERIA),
                                           "--json"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out)["error"]["code"], "not_found")
        finally:
            os.environ["NL_DATA_DIR"] = old

    def test_no_mission_creation_or_auto_completion_paths(self):
        conn = init_db()
        try:
            before = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        finally:
            conn.close()
        goal_id, _ = self.seed_goal()
        self.close_services()
        self.run_cli(["goal", "verify", str(goal_id), "--evidence-json",
                      json.dumps(EVIDENCE), "--criteria-json",
                      json.dumps(CRITERIA)])
        self.run_cli(["goal", "complete", str(goal_id), "--evidence-json",
                      json.dumps(EVIDENCE), "--criteria-json",
                      json.dumps(CRITERIA), "--dry-run"])
        conn = init_db()
        try:
            after = conn.execute("SELECT COUNT(1) FROM missions").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(after, before)
        # Only an explicit complete call changes status; verify/detection do not.
        services = AppServices()
        try:
            status = services.goal_get(goal_id)["goal"]["status"]
            self.assertEqual(status, "active")
            result = services.goal_complete(goal_id, EVIDENCE, CRITERIA)
            self.assertEqual(result["outcome"], "completed")
        finally:
            services._db.close()

    def test_static_no_model_network_or_gui_imports_and_no_auto_completion(self):
        services_source = (REPO_ROOT / "nl_coding_agent" / "app" /
                           "services.py").read_text(encoding="utf-8")
        cli_source = (REPO_ROOT / "nl_coding_agent" / "cli.py").read_text(
            encoding="utf-8")
        start = services_source.index("def goal_verify(")
        end = services_source.index("def goal_complete(", start)
        facade = services_source[start:end] + services_source[
            end:services_source.index("def goal_completions", end)
            if "def goal_completions" in services_source
            else services_source.index("    # --- Events ---", end)]
        for forbidden in ("import requests", "import urllib", "import socket",
                          "PySide6", "subprocess", "MultiAgentOrchestrator"):
            self.assertNotIn(forbidden, facade)
        self.assertIn("verify_goal", services_source)
        cli_start = cli_source.index('if command == "verify":')
        cli_end = cli_source.index('if command == "progress":', cli_start)
        cli_block = cli_source[cli_start:cli_end]
        for forbidden in ("MultiAgentOrchestrator", "import requests",
                          "import urllib", "import socket", "PySide6", "ollama"):
            self.assertNotIn(forbidden, cli_block)
        self.assertIn("goal_complete", cli_block)
        self.assertIn("source-backed evidence", cli_source.lower())
        self.assertIn("checklist", cli_source.lower())


if __name__ == "__main__":
    unittest.main()

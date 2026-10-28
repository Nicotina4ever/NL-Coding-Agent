"""C3d: supervisor CLI surfaces, JSON output, exit codes and command wiring."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nl_coding_agent import cli
from nl_coding_agent.app.supervisor_service import SupervisorService
from nl_coding_agent.persistence import database


def run_main(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with patch.object(sys, "argv", ["nl_agent.py", *argv]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main()
    return code, out.getvalue(), err.getvalue()


class ExitCodeTests(unittest.TestCase):
    def test_documented_exit_code_mapping(self):
        self.assertEqual(cli.supervisor_exit_code("completed"), 0)
        self.assertEqual(cli.supervisor_exit_code("off"), 0)
        self.assertEqual(cli.supervisor_exit_code("idle"), 0)
        self.assertEqual(cli.supervisor_exit_code("blocked"), 1)
        self.assertEqual(cli.supervisor_exit_code("failed"), 1)
        self.assertEqual(cli.supervisor_exit_code("already-running"), 1)
        self.assertEqual(cli.supervisor_exit_code("stopped"), 3)
        self.assertEqual(cli.supervisor_exit_code("paused"), 3)
        self.assertEqual(cli.supervisor_exit_code("waiting_for_resources"), 4)
        self.assertEqual(cli.supervisor_exit_code("waiting_for_approval"), 4)
        self.assertEqual(cli.supervisor_exit_code("something-else"), 2)


class ParserTests(unittest.TestCase):
    def test_supervisor_help_lists_every_command(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["nl_agent.py", "supervisor", "--help"]), \
                contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit):
                cli.main()
        text = output.getvalue()
        for command in ("run", "start", "stop", "pause", "resume",
                        "status", "index", "recover", "advance-stage"):
            self.assertIn(command, text)

    def test_assisted_mode_requires_confirm_flag(self):
        before = {"called": False}

        def forbidden(**kwargs):
            before["called"] = True
            raise AssertionError("assisted run must not start without --confirm-assisted")

        with patch("nl_coding_agent.core.supervisor.run_supervisor", forbidden):
            code, _out, err = run_main([
                "supervisor", "run", "--mode", "assisted", "--project", ".",
            ])
        self.assertEqual(code, 2)
        self.assertIn("confirm-assisted", err)
        self.assertFalse(before["called"])

    def test_assisted_mode_with_confirm_runs(self):
        calls = {}

        def fake_run(root, **kwargs):
            calls.update(kwargs)
            return {"status": "completed", "missions": [], "resume_command": "x"}

        with patch("nl_coding_agent.core.supervisor.run_supervisor", fake_run):
            code, out, _err = run_main([
                "supervisor", "run", "--mode", "assisted",
                "--confirm-assisted", "--project", ".",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(calls["mode"], "assisted")
        self.assertIn("completed", out)


class RunCommandTests(unittest.TestCase):
    def test_run_forwards_mode_and_budget_and_prints_json(self):
        calls = {}

        def fake_run(root, **kwargs):
            calls.update(kwargs)
            return {
                "status": "completed", "missions": [{"id": 7, "status": "completed"}],
                "stopped_reason": "limit", "resume_command": "resume-cmd",
            }

        with patch("nl_coding_agent.core.supervisor.run_supervisor", fake_run):
            code, out, _err = run_main([
                "supervisor", "run", "--project", ".",
                "--mode", "automatic", "--max-missions", "2", "--json",
                "--dev-model", "ollama/dev", "--reviewer-model", "ollama/rev",
            ])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(calls["mode"], "automatic")
        self.assertEqual(calls["max_missions"], 2)
        self.assertEqual(calls["developer_model"], "ollama/dev")
        self.assertEqual(calls["reviewer_model"], "ollama/rev")

    def test_run_exit_codes_for_blocked_waiting_and_stopped(self):
        cases = [
            ("blocked", 1),
            ("waiting_for_resources", 4),
            ("waiting_for_approval", 4),
            ("stopped", 3),
            ("paused", 3),
            ("off", 0),
        ]
        for status, expected in cases:
            with patch(
                "nl_coding_agent.core.supervisor.run_supervisor",
                return_value={"status": status, "missions": [], "resume_command": "x"},
            ):
                code, _out, _err = run_main([
                    "supervisor", "run", "--project", ".", "--mode", "off"
                    if status == "off" else "automatic",
                ])
            self.assertEqual(code, expected, msg=status)

    def test_run_failure_is_exit_2(self):
        with patch("nl_coding_agent.core.supervisor.run_supervisor",
                   side_effect=RuntimeError("boom")):
            code, _out, err = run_main(["supervisor", "run", "--project", "."])
        self.assertEqual(code, 2)
        self.assertIn("boom", err)

    def test_off_mode_reports_off_and_does_not_claim_execution(self):
        with patch(
            "nl_coding_agent.core.supervisor.run_supervisor",
            return_value={"status": "off", "missions": [], "resume_command": "x"},
        ) as runner:
            code, out, _err = run_main([
                "supervisor", "run", "--project", ".", "--mode", "off",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(runner.call_count, 1)
        self.assertIn("off", out)
        self.assertEqual(runner.call_args.kwargs["mode"], "off")


class ControlCommandTests(unittest.TestCase):
    def test_stop_pause_resume_call_supervisor_command_and_persist(self):
        recorded = []

        def fake_command(root, command, *, requested_by="cli", reason=""):
            recorded.append((command, requested_by, reason))
            return {"ok": True, "command": command}

        with patch("nl_coding_agent.core.supervisor.supervisor_command", fake_command):
            stop_code, stop_out, _ = run_main([
                "supervisor", "stop", "--project", ".", "--reason", "test", "--json",
            ])
            pause_code, _pause_out, _ = run_main([
                "supervisor", "pause", "--project", ".",
            ])
            resume_code, _resume_out, _ = run_main([
                "supervisor", "resume", "--project", ".",
            ])
        self.assertEqual((stop_code, pause_code, resume_code), (0, 0, 0))
        self.assertEqual(
            [item[0] for item in recorded], ["stop", "pause", "resume"]
        )
        self.assertEqual(recorded[0][1], "cli")
        self.assertEqual(recorded[0][2], "test")
        self.assertEqual(json.loads(stop_out)["command"], "stop")

    def test_status_json_outputs_snapshot(self):
        snapshot = {
            "status": "idle", "mode": "off", "root": "R",
            "run": {"status": "COMPLETED"}, "lease": None,
            "queue_counts": {"READY": 1}, "program_stage": 2,
            "resume_command": "python nl_agent.py supervisor run",
        }
        with patch("nl_coding_agent.core.supervisor.supervisor_status",
                   return_value=snapshot):
            code, out, _err = run_main([
                "supervisor", "status", "--project", ".", "--json",
            ])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "idle")
        self.assertEqual(payload["queue_counts"], {"READY": 1})

    def test_command_error_is_exit_2(self):
        with patch("nl_coding_agent.core.supervisor.supervisor_command",
                   side_effect=RuntimeError("nope")):
            code, _out, err = run_main(["supervisor", "stop", "--project", "."])
        self.assertEqual(code, 2)
        self.assertIn("nope", err)


def _fixture_index() -> dict:
    return {
        "schema_version": "1.0",
        "program_order": {"stages": [
            {"stage": 1, "name": "One", "status": "completed",
             "depends_on_stages": [], "requirement_ids": ["R-1"]},
            {"stage": 2, "name": "Two", "status": "in_progress",
             "depends_on_stages": [1], "requirement_ids": ["R-2"]},
        ]},
        "requirements": [
            {"id": "R-1", "title": "Base", "priority": "P0", "status": "verified",
             "dependencies": [], "acceptance": [], "source_refs": [],
             "program_stage": 1},
            {"id": "R-2", "title": "Next", "priority": "P0", "status": "planned",
             "dependencies": ["R-1"], "acceptance": ["ok"], "source_refs": [],
             "program_stage": 2},
        ],
    }


class IndexCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "project"
        (self.root / "docs" / "product-blueprint").mkdir(parents=True)
        self.data = Path(self._tmp.name) / "data"
        self._env = patch.dict(os.environ, {"NL_DATA_DIR": str(self.data)})
        self._env.start()
        self.addCleanup(self._env.stop)
        database.init_db().close()
        (self.root / "docs" / "product-blueprint" / "INDEX.json").write_text(
            json.dumps(_fixture_index()), encoding="utf-8", newline="",
        )

    def test_index_check_json(self):
        code, out, _err = run_main([
            "supervisor", "index", "--project", str(self.root), "--check", "--json",
        ])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["requirements"], 2)
        self.assertEqual(payload["current_stage"]["stage"], 2)

    def test_index_show_next_syncs_mirror(self):
        code, out, _err = run_main([
            "supervisor", "index", "--project", str(self.root),
            "--show-next", "--sync", "--json",
        ])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["next"]["requirement_id"], "R-2")
        self.assertIn("sync", payload)

    def test_missing_index_is_exit_2(self):
        (self.root / "docs" / "product-blueprint" / "INDEX.json").unlink()
        code, _out, err = run_main([
            "supervisor", "index", "--project", str(self.root), "--check",
        ])
        self.assertEqual(code, 2)
        self.assertIn("Backlog index", err)


class RecoverAndAdvanceTests(unittest.TestCase):
    def test_recover_dry_run_uses_preflight_only(self):
        report = SimpleNamespace(
            to_dict=lambda: {"ok": True, "blockers": [], "warnings": ["w"]}
        )
        fake = SimpleNamespace(preflight=lambda: report)
        with patch("nl_coding_agent.core.supervisor.Supervisor", return_value=fake):
            code, out, _err = run_main([
                "supervisor", "recover", "--project", ".", "--dry-run", "--json",
            ])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["preflight"]["ok"])

    def test_advance_stage_requires_confirm_and_evidence(self):
        code, _out, err = run_main([
            "supervisor", "advance-stage", "--project", ".", "--stage", "3",
        ])
        self.assertEqual(code, 2)
        self.assertIn("confirm", err)
        code, _out, err = run_main([
            "supervisor", "advance-stage", "--project", ".", "--stage", "3",
            "--confirm",
        ])
        self.assertEqual(code, 2)
        self.assertIn("evidence", err)

    def test_advance_stage_records_override(self):
        index = SimpleNamespace(
            stages=[SimpleNamespace(stage=2), SimpleNamespace(stage=3)],
        )
        with patch("nl_coding_agent.cli._supervisor_open_project",
                   return_value={"id": 1}), \
                patch("nl_coding_agent.core.backlog.load_project_index",
                      return_value=index), \
                patch("nl_coding_agent.persistence.database.get_json_setting",
                      return_value={"mode": "automatic"}), \
                patch("nl_coding_agent.persistence.database.set_json_setting") as set_cfg, \
                patch("nl_coding_agent.persistence.database.init_db"), \
                patch("nl_coding_agent.persistence.database.log_event"):
            code, out, _err = run_main([
                "supervisor", "advance-stage", "--project", ".", "--stage", "3",
                "--confirm", "--evidence", "docs/HARNESS_ACCEPTANCE.md", "--json",
            ])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["program_stage_override"], 3)
        saved = set_cfg.call_args.args[1]
        self.assertEqual(saved["program_stage_override"], 3)
        self.assertEqual(saved["mode"], "automatic")


class SelfBuildShimCliTests(unittest.TestCase):
    def test_selfbuild_autonomous_prints_deprecation_and_delegates(self):
        calls = {}

        def fake_run(root, **kwargs):
            calls.update(kwargs)
            return {"status": "completed", "missions": [], "stopped_reason": "",
                    "resume_command": "resume"}

        class FakeLock:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("nl_coding_agent.core.relocation.check_selfbuild_readiness",
                   return_value={"ok": True, "errors": [], "warnings": []}), \
                patch("nl_coding_agent.core.mission_lock.mission_lock",
                      return_value=FakeLock()), \
                patch("nl_coding_agent.core.selfbuild_runner.run_autonomous",
                      side_effect=fake_run), \
                patch("nl_coding_agent.persistence.database.db_path",
                      return_value=Path(tempfile.gettempdir()) / "x.sqlite3"):
            code, _out, err = run_main([
                "selfbuild", "--autonomous", "--project", ".",
                "--stop-after", "developer",
            ])
        self.assertEqual(code, 0)
        self.assertIn("deprecated", err.lower())
        self.assertEqual(calls["stop_after"], "developer")


class SupervisorServiceTests(unittest.TestCase):
    def test_background_thread_start_wait_and_events(self):
        events = []

        class FakeBus:
            def emit(self, event):
                events.append(event)

        def fake_runner(root, **kwargs):
            return {"status": "completed", "missions": [], "stopped_reason": "done",
                    "resume_command": "x"}

        service = SupervisorService(
            Path("."), project_id=1, supervisor_runner=fake_runner,
            event_bus=FakeBus(),
        )
        started = service.start(mode="automatic", max_missions=1)
        self.assertTrue(started["ok"])
        result = service.wait(timeout=15)
        self.assertFalse(service.is_running())
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("started" in event.message.lower() for event in events))
        self.assertTrue(any("finished" in event.message.lower() for event in events))

    def test_second_start_is_rejected_while_thread_is_running(self):
        import threading

        gate = threading.Event()

        def fake_runner(root, **kwargs):
            gate.wait(timeout=10)
            return {"status": "completed"}

        service = SupervisorService(
            Path("."), project_id=1, supervisor_runner=fake_runner,
        )
        self.assertTrue(service.start()["ok"])
        second = service.start()
        gate.set()
        service.wait(timeout=15)
        self.assertFalse(second["ok"])


if __name__ == "__main__":
    unittest.main()

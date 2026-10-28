"""C3d: selfbuild_runner is a thin deprecated compatibility shim over the supervisor.

Keeps the C5 (promotion-preflight) and C7 (legacy-harness refusal) assertions and
the legacy helper API, while run_autonomous() delegates to the stage-3 supervisor.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.core import selfbuild_runner as runner
from nl_coding_agent.core.code_integrity_gate import detect_stub
from nl_coding_agent.core.selfbuild_runner import (
    MAX_AUTONOMOUS_MISSIONS,
    _resume_command,
    _resume_command_for_results,
    _stage_dirs,
    completed_roadmap_mission,
    pending_roadmap_mission,
    reconcile_completed_mission,
    roadmap_fingerprint,
    run_autonomous,
    select_resumable_mission,
)

RUNNER_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "nl_coding_agent"
    / "core"
    / "selfbuild_runner.py"
)


class SelfBuildHelpersTest(unittest.TestCase):
    def test_resumable_priority(self):
        missions = [
            {"id": 3, "status": "pending", "harness_version": 2},
            {"id": 2, "status": "interrupted", "harness_version": 2},
            {"id": 1, "status": "running", "harness_version": 2},
            {"id": 4, "status": "completed", "harness_version": 2},
        ]
        self.assertEqual(select_resumable_mission(missions)["id"], 1)

    def test_no_resumable_work(self):
        missions = [
            {"id": 1, "status": "completed", "harness_version": 2},
            {"id": 2, "status": "blocked", "harness_version": 2},
            {"id": 3, "status": "failed", "harness_version": 2},
        ]
        self.assertIsNone(select_resumable_mission(missions))

    def test_roadmap_matching_requires_title_goal_and_status(self):
        roadmap = {"title": "A mission", "goal": "Do the work"}
        missions = [
            {"id": 1, "title": "A mission", "goal": "Do the work", "status": "completed"},
            {"id": 2, "title": "A mission", "goal": "Do other work", "status": "completed"},
            {"id": 3, "title": "A mission", "goal": "Do the work", "status": "pending",
             "harness_version": 2},
        ]
        self.assertEqual(completed_roadmap_mission(missions, roadmap)["id"], 1)
        self.assertEqual(pending_roadmap_mission(missions, roadmap)["id"], 3)

    def test_fingerprint_tracks_roadmap_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roadmap.md"
            path.write_text("first", encoding="utf-8")
            first = roadmap_fingerprint({"source": str(path)})
            path.write_text("second", encoding="utf-8")
            second = roadmap_fingerprint({"source": str(path)})
            self.assertNotEqual(first, second)

    def test_autonomous_limit_is_bounded(self):
        self.assertGreaterEqual(MAX_AUTONOMOUS_MISSIONS, 1)
        self.assertLessEqual(MAX_AUTONOMOUS_MISSIONS, 10)

    def test_resume_command_includes_blocked_mission_id(self):
        command = _resume_command_for_results(
            Path("project"), "blocked", [{"id": 40, "status": "failed"}],
        )
        self.assertIn("--resume 40", command)

    def test_resume_command_omits_id_when_completed_or_idle(self):
        completed = _resume_command_for_results(
            Path("project"), "completed", [{"id": 40, "status": "completed"}],
        )
        idle = _resume_command_for_results(Path("project"), "idle", [])
        self.assertNotIn("--resume", completed)
        self.assertNotIn("--resume", idle)

    def test_resume_command_helper_builds_explicit_resume(self):
        self.assertIn("--resume 40", _resume_command(Path("project"), 40))


class ShimDelegationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "project"
        self.root.mkdir(parents=True)
        self.logs: list[str] = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(runner, "_log",
                                             side_effect=self._log))
        self.stack.enter_context(patch.object(runner, "open_project",
                                              return_value={"id": 1}))
        self.stack.enter_context(patch.object(runner, "list_missions",
                                              return_value=[]))
        self.stack.enter_context(patch.object(
            runner.promotion, "preflight", return_value=[]))

    def _log(self, message, on_event=None):
        self.logs.append(str(message))

    def _fake_supervisor(self, result: dict):
        calls: list[dict] = []

        def fake(root, **kwargs):
            calls.append({"root": root, **kwargs})
            return result

        self.stack.enter_context(patch.object(runner, "run_supervisor", fake))
        return calls

    def test_result_is_mapped_to_legacy_shape(self):
        calls = self._fake_supervisor({
            "status": "completed",
            "missions": [{"id": 41, "status": "completed", "verdict": "APPROVE",
                          "diff_stat": "1 file", "error": None}],
            "stopped_reason": "done",
            "resume_command": "supervisor-resume",
        })
        result = run_autonomous(
            self.root, max_missions=2, developer_model="ollama/dev",
            reviewer_model="ollama/rev", debug_model="ollama/dbg",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["missions"][0]["id"], 41)
        self.assertEqual(result["missions"][0]["verdict"], "APPROVE")
        self.assertEqual(result["stopped_reason"], "done")
        self.assertEqual(result["resume_command"], "supervisor-resume")
        self.assertEqual(calls[0]["mode"], "automatic")
        self.assertEqual(calls[0]["max_missions"], 2)
        self.assertEqual(calls[0]["developer_model"], "ollama/dev")
        self.assertEqual(calls[0]["reviewer_model"], "ollama/rev")
        self.assertIn("deprecated", self.logs[0].lower())

    def test_blocked_and_waiting_statuses_map_to_legacy_blocked(self):
        for supervisor_status in ("blocked", "waiting_for_resources", "stopped"):
            calls = self._fake_supervisor({
                "status": supervisor_status, "missions": [],
                "stopped_reason": "reason", "resume_command": "resume",
            })
            result = run_autonomous(self.root, max_missions=1)
            self.assertEqual(result["status"], "blocked", msg=supervisor_status)
            self.assertEqual(result["supervisor"]["status"], supervisor_status)
            self.assertTrue(calls)

    def test_stop_after_is_legacy_and_not_forwarded(self):
        calls = self._fake_supervisor({
            "status": "completed", "missions": [], "stopped_reason": "",
            "resume_command": "x",
        })
        run_autonomous(self.root, max_missions=1, stop_after="developer")
        self.assertNotIn("stop_after", calls[0])
        self.assertTrue(any("--stop-after is a legacy" in message for message in self.logs))

    def test_event_sink_adapts_on_event_callback(self):
        events: list[str] = []

        def fake(root, **kwargs):
            sink = kwargs.get("event_sink")
            if sink is not None:
                sink({"level": "info", "message": "supervisor event",
                      "payload": {"x": 1}})
            return {"status": "completed", "missions": [], "stopped_reason": "",
                    "resume_command": "x"}

        self.stack.enter_context(patch.object(runner, "run_supervisor", fake))
        run_autonomous(self.root, max_missions=1, on_event=events.append)
        self.assertIn("supervisor event", events)


class FailClosedShimTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "project"
        self.root.mkdir(parents=True)
        self.logs: list[str] = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(
            runner, "_log", side_effect=lambda message, on_event=None: self.logs.append(message)))
        self.stack.enter_context(patch.object(runner, "open_project",
                                              return_value={"id": 1}))
        self.stack.enter_context(patch.object(runner, "list_missions",
                                              return_value=[]))

    def test_explicit_legacy_resume_is_blocked_without_supervisor(self):
        mission = {"id": 44, "status": "blocked", "title": "Legacy",
                   "goal": "Old work", "project_id": 1, "harness_version": None}
        with patch.object(runner, "get_mission", return_value=mission), \
                patch.object(runner, "run_supervisor",
                             side_effect=AssertionError("must not run")):
            result = run_autonomous(self.root, max_missions=1, resume_mission_id=44)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("predates the staged-candidate harness", result["stopped_reason"])
        self.assertEqual(_stage_dirs(self.root), [])

    def test_explicit_completed_mission_returns_completed_without_running(self):
        mission = {"id": 41, "status": "completed", "title": "Done",
                   "goal": "x", "project_id": 1, "harness_version": 2,
                   "review_verdict": "APPROVE", "diff_stat": "1 file"}
        with patch.object(runner, "get_mission", return_value=mission), \
                patch.object(runner, "run_supervisor",
                             side_effect=AssertionError("must not run")):
            result = run_autonomous(self.root, max_missions=1, resume_mission_id=41)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["missions"][0]["id"], 41)
        self.assertIn("already completed", result["stopped_reason"])

    def test_explicit_harness_resume_delegates(self):
        mission = {"id": 41, "status": "pending", "title": "Resume",
                   "goal": "x", "project_id": 1, "harness_version": 2}
        calls = []

        def fake(root, **kwargs):
            calls.append(kwargs)
            return {"status": "completed", "missions": [],
                    "stopped_reason": "", "resume_command": "x"}

        with patch.object(runner, "get_mission", return_value=mission), \
                patch.object(runner, "run_supervisor", fake):
            result = run_autonomous(self.root, max_missions=1, resume_mission_id=41)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("Selected explicit mission #41" in message for message in self.logs))
        self.assertTrue(calls)

    def test_unreconciled_promotion_journal_blocks_new_work(self):
        with patch.object(
            runner.promotion, "preflight",
            return_value=["Mission #77 has an unreconciled promotion journal"],
        ), patch.object(runner, "run_supervisor",
                       side_effect=AssertionError("must not run")):
            result = run_autonomous(self.root, max_missions=1)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Unresolved candidate promotion state", result["stopped_reason"])

    def test_legacy_resumable_is_skipped_and_logged(self):
        legacy = {"id": 44, "status": "pending", "title": "Old",
                  "goal": "old", "project_id": 1, "harness_version": None}
        calls = []

        def fake(root, **kwargs):
            calls.append(kwargs)
            return {"status": "completed", "missions": [],
                    "stopped_reason": "", "resume_command": "x"}

        with patch.object(runner, "list_missions", return_value=[legacy]), \
                patch.object(runner, "run_supervisor", fake):
            result = run_autonomous(self.root, max_missions=1)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("Ignoring legacy mission(s)" in message for message in self.logs))
        self.assertTrue(calls)


class PostHocGateRemovalTests(unittest.TestCase):
    def test_runner_source_contains_no_post_hoc_gate(self):
        source = RUNNER_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("p.write_text(baseline_content", source)
        self.assertNotIn("detect_stub(", source)
        self.assertNotIn("rollback_from_snapshot(", source)
        self.assertNotIn("save_snapshot", source)
        self.assertNotIn("mission_baselines", source)
        self.assertNotIn("Harness gate error", source)

    def test_runner_keeps_harness_preflight_legacy_refusal_and_supervisor_delegation(self):
        source = RUNNER_SOURCE.read_text(encoding="utf-8")
        self.assertIn("promotion.HARNESS_VERSION", source)
        self.assertIn("promotion.preflight(", source)
        self.assertIn("predates the staged-candidate harness", source)
        self.assertIn("run_supervisor(", source)
        self.assertIn("deprecated", source.lower())

    def test_completed_mission_does_not_rewrite_stub_from_mission_baselines(self):
        good = "def add(a, b):\n    return a + b\n"
        stub = "def add(a, b):\n    pass\n"
        self.assertTrue(detect_stub(stub, good))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            live_file = root / "planner.py"
            live_file.write_text(stub, encoding="utf-8")
            baselines = root / "data" / "mission_baselines"
            baselines.mkdir(parents=True)
            (baselines / "41.json").write_text(
                json.dumps({"planner.py": good}), encoding="utf-8",
            )
            tree_before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            with patch.object(runner, "_log"), \
                    patch.object(runner, "open_project", return_value={"id": 1}), \
                    patch.object(runner, "list_missions", return_value=[]), \
                    patch.object(runner.promotion, "preflight", return_value=[]), \
                    patch.object(runner, "run_supervisor", return_value={
                        "status": "completed", "missions": [],
                        "stopped_reason": "", "resume_command": "x",
                    }):
                result = run_autonomous(root, max_missions=1)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(live_file.read_text(encoding="utf-8"), stub)
            tree_after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(tree_after, tree_before)


if __name__ == "__main__":
    unittest.main()

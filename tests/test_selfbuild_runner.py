import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.core.selfbuild_runner import (
    MAX_AUTONOMOUS_MISSIONS,
    _resume_command,
    _resume_command_for_results,
    completed_roadmap_mission,
    pending_roadmap_mission,
    reconcile_completed_mission,
    roadmap_fingerprint,
    run_autonomous,
    select_resumable_mission,
)


class TestSelfBuildSelection(unittest.TestCase):
    def test_resumable_priority(self):
        missions = [
            {"id": 3, "status": "pending", "harness_version": 2},
            {"id": 2, "status": "interrupted", "harness_version": 2},
            {"id": 1, "status": "running", "harness_version": 2},
            {"id": 4, "status": "completed", "harness_version": 2},
        ]
        selected = select_resumable_mission(missions)
        self.assertEqual(selected["id"], 1)

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
            Path("project"),
            "blocked",
            [{"id": 40, "status": "failed"}],
        )
        self.assertIn("--resume 40", command)

    def test_resume_command_omits_id_when_completed_or_idle(self):
        completed = _resume_command_for_results(
            Path("project"),
            "completed",
            [{"id": 40, "status": "completed"}],
        )
        idle = _resume_command_for_results(Path("project"), "idle", [])
        self.assertNotIn("--resume", completed)
        self.assertNotIn("--resume", idle)

    def test_resume_command_helper_builds_explicit_resume(self):
        command = _resume_command(Path("project"), 40)
        self.assertIn("--resume 40", command)

    def test_run_autonomous_forwards_stop_after(self):
        calls = {}

        class FakeOrchestrator:
            def run_mission(self, **kwargs):
                calls.update(kwargs)
                return {
                    "status": "completed",
                    "verdict": "APPROVE",
                    "diff_stat": "1 file changed",
                }

        roadmap = {"title": "Recovery", "goal": "Fix controls", "source": ""}
        mission = {
            "id": 41,
            "status": "pending",
            "title": "Recovery",
            "goal": "Fix controls",
            "project_id": 1,
            "harness_version": 2,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch("nl_coding_agent.core.selfbuild_runner._log"), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner._load_state",
                        return_value={"projects": {}},
                    ), \
                    patch("nl_coding_agent.core.selfbuild_runner._save_state"), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.open_project",
                        return_value={"id": 1},
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.list_missions",
                        return_value=[],
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.next_mission",
                        return_value=roadmap,
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.create_mission",
                        return_value=41,
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.get_mission",
                        return_value=mission,
                    ):
                result = run_autonomous(
                    root,
                    max_missions=1,
                    stop_after="developer",
                    orchestrator_factory=lambda _: FakeOrchestrator(),
                )
        self.assertEqual(calls["stop_after"], "developer")
        self.assertEqual(result["status"], "completed")

    def test_resumed_completed_mission_updates_state_immediately(self):
        saved = []

        class FakeOrchestrator:
            def run_mission(self, **kwargs):
                return {
                    "status": "completed",
                    "verdict": "APPROVE",
                    "diff_stat": "1 file changed",
                }

        roadmap = {"title": "Recovery", "goal": "Fix controls", "source": ""}
        mission = {
            "id": 41,
            "status": "pending",
            "title": "Recovery",
            "goal": "Fix controls",
            "project_id": 1,
            "harness_version": 2,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch("nl_coding_agent.core.selfbuild_runner._log"), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner._load_state",
                        return_value={"projects": {}},
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner._save_state",
                        side_effect=saved.append,
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.open_project",
                        return_value={"id": 1},
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.list_missions",
                        return_value=[],
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.next_mission",
                        return_value=roadmap,
                    ), \
                    patch(
                        "nl_coding_agent.core.selfbuild_runner.get_mission",
                        return_value=mission,
                    ):
                result = run_autonomous(
                    root,
                    max_missions=1,
                    resume_mission_id=41,
                    orchestrator_factory=lambda _: FakeOrchestrator(),
                )
        self.assertEqual(result["status"], "completed")
        self.assertTrue(saved)
        project_state = saved[-1]["projects"][str(root)]
        self.assertEqual(project_state["last_completed_mission_id"], 41)
        self.assertEqual(
            project_state["last_completed_fingerprint"],
            roadmap_fingerprint(roadmap),
        )

    def test_reconcile_completed_mission_requires_current_roadmap(self):
        project_state = {}
        with patch(
            "nl_coding_agent.core.selfbuild_runner.next_mission",
            return_value={"title": "Other", "goal": "Other", "source": ""},
        ):
            changed = reconcile_completed_mission(
                project_state,
                Path("project"),
                {"id": 41, "title": "Recovery", "goal": "Fix controls"},
            )
        self.assertFalse(changed)
        self.assertEqual(project_state, {})


class HarnessSelectionTests(unittest.TestCase):
    def test_legacy_missions_are_never_selected_as_resumable(self):
        missions = [
            {"id": 44, "status": "blocked", "harness_version": None},
            {"id": 45, "status": "pending", "harness_version": None},
            {"id": 46, "status": "interrupted", "harness_version": 2},
        ]
        selected = select_resumable_mission(missions)
        self.assertEqual(selected["id"], 46)

    def test_legacy_pending_roadmap_mission_is_not_reused(self):
        roadmap = {"title": "A mission", "goal": "Do the work"}
        missions = [{"id": 44, "title": "A mission", "goal": "Do the work",
                     "status": "pending", "harness_version": None}]
        self.assertIsNone(pending_roadmap_mission(missions, roadmap))

    def test_explicit_legacy_resume_is_blocked_without_running_a_mission(self):
        ran = []
        mission = {
            "id": 44, "status": "blocked", "title": "Legacy",
            "goal": "Old work", "project_id": 1, "harness_version": None,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch("nl_coding_agent.core.selfbuild_runner._log"), \
                    patch("nl_coding_agent.core.selfbuild_runner._load_state",
                          return_value={"projects": {}}), \
                    patch("nl_coding_agent.core.selfbuild_runner._save_state"), \
                    patch("nl_coding_agent.core.selfbuild_runner.open_project",
                          return_value={"id": 1}), \
                    patch("nl_coding_agent.core.selfbuild_runner.list_missions",
                          return_value=[]), \
                    patch("nl_coding_agent.core.selfbuild_runner.get_mission",
                          return_value=mission):
                result = run_autonomous(
                    root, max_missions=1, resume_mission_id=44,
                    orchestrator_factory=lambda _: ran.append(True),
                )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("predates the staged-candidate harness", result["stopped_reason"])
        self.assertEqual(ran, [])

    def test_unreconciled_promotion_journal_blocks_new_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch("nl_coding_agent.core.selfbuild_runner._log"), \
                    patch("nl_coding_agent.core.selfbuild_runner._load_state",
                          return_value={"projects": {}}), \
                    patch("nl_coding_agent.core.selfbuild_runner._save_state"), \
                    patch("nl_coding_agent.core.selfbuild_runner.open_project",
                          return_value={"id": 1}), \
                    patch("nl_coding_agent.core.selfbuild_runner.list_missions",
                          return_value=[]), \
                    patch("nl_coding_agent.core.selfbuild_runner.promotion.preflight",
                          return_value=["Mission #77 has an unreconciled promotion journal"]):
                result = run_autonomous(root, max_missions=1)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Unresolved candidate promotion state", result["stopped_reason"])


if __name__ == "__main__":
    unittest.main()

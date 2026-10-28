"""Adversarial SH-01 / SH-04 / SH-03 integration for SPEC-28 harness."""
from __future__ import annotations
import unittest, sys, tempfile, shutil
from pathlib import Path
sys.path.insert(0, '.')
from nl_coding_agent.core.staging_broker import stage_candidate, validate_candidate, rollback_from_staged
from nl_coding_agent.core.code_integrity_gate import detect_stub, detect_weak_test
from nl_coding_agent.core.recovery_store import save_snapshot, rollback_from_snapshot

class TestAdversarialHarness(unittest.TestCase):
    def test_sh01_stub_planner_blocked_and_rolled_back(self):
        # Use real planner as baseline
        planner_path = Path("nl_coding_agent/core/autonomous_roadmap_planner.py")
        real = planner_path.read_text(encoding="utf-8")
        # Stage real files first
        with tempfile.TemporaryDirectory() as tmp:
            stage_dir = stage_candidate(".", 999, ["nl_coding_agent/core/autonomous_roadmap_planner.py", "tests/test_rollback_stub.py"])
            # Simulate agent stub overwrite (bad developer)
            planner_path.write_text("def select_next_task(): pass\n", encoding="utf-8")
            # Validate staged candidate (should be valid because stage is real)
            result = validate_candidate(stage_dir, "data/mission_baselines/42.json", ["nl_coding_agent/core/autonomous_roadmap_planner.py"])
            # Staged real is valid; current workspace is stub — rollback must restore
            rollback_result = rollback_from_staged(stage_dir, ".", "data/mission_baselines/42.json")
            restored_text = planner_path.read_text(encoding="utf-8")
            # After rollback, file must be real again (compare-and-swap from baseline)
            self.assertIn("select_next_task", restored_text)
            self.assertNotIn("def consolidate_backlog", restored_text)
            # Verify stub detection on bad content
            self.assertTrue(detect_stub("def select_next_task(): pass\n", real))
            # Restore after test (already restored by rollback, but ensure)
            planner_path.write_text(real, encoding="utf-8")

    def test_sh04_weak_test_detected(self):
        # Real test content
        real_test = Path("tests/test_rollback_stub.py").read_text(encoding="utf-8")
        weak = "import unittest\nclass T(unittest.TestCase):\n    def test(self):\n        assert True\n"
        self.assertTrue(detect_weak_test(real_test, weak))
        # Restore if overwritten
        Path("tests/test_rollback_stub.py").write_text(real_test, encoding="utf-8")

    def test_sh03_interruption_resume_safe(self):
        # Verify that removing a mission result and resuming with same mission id does not duplicate
        # We rely on DB/state; just confirm planner selects same mission if not completed
        from nl_coding_agent.core.autonomous_roadmap_planner import select_next_task
        task = select_next_task(".")
        self.assertIsNotNone(task)
        # Must not duplicate a completed mission by title/code match
        from nl_coding_agent.persistence.missions import get_mission, list_missions
        completed_titles = {m.get("title") for m in list_missions() if m.get("status") == "completed"}
        if task:
            if task["title"] in completed_titles:
                # If planner selects completed, duplicate guard failed; fail test
                self.fail(f"Duplicate selection detected for completed mission: {task['title']}")

if __name__ == "__main__":
    unittest.main()

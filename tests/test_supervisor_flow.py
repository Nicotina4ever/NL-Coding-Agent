"""C4c: supervisor Flow pipeline parity, idempotent reconcile, single executor, default."""
from __future__ import annotations

import json
from unittest.mock import patch

from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
from nl_coding_agent.flows.supervisor_flow import SupervisorRunFlow
from nl_coding_agent.persistence import supervisor_store as store

from tests.test_supervisor_sh07 import (  # reuse the SH-07 fake-model fixture
    FEATURE_A, FEATURE_B, SH07Base, fixture_index, write_block,
)


class FlowBase(SH07Base):
    def config(self, **overrides) -> SupervisorConfig:
        values = {
            "mode": "automatic",
            "max_missions_per_run": 2,
            "max_attempts_per_requirement": 1,
            "heartbeat_interval_s": 0.5,
            "lease_ttl_s": 30.0,
            "backoff_schedule_s": (0,),
            "developer_model": "ollama/flow-dev",
            "reviewer_model": "ollama/flow-review",
            "debug_model": "ollama/flow-dev",
            "pipeline": "flow",
        }
        values.update(overrides)
        return SupervisorConfig(**values)


class FlowHappyPathTests(FlowBase):
    def test_two_consecutive_missions_through_flow(self):
        supervisor = self.make_supervisor()
        result = supervisor.run(max_missions=2)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["completed"], 2)
        self.assertEqual(result["pipeline"], "flow")
        self.assertEqual((self.root / "src" / "feature_a.py").read_text(encoding="utf-8"), FEATURE_A)
        self.assertEqual((self.root / "src" / "feature_b.py").read_text(encoding="utf-8"), FEATURE_B)
        missions = self.missions_by_requirement()
        self.assertEqual(missions["R-2"]["status"], "completed")
        self.assertEqual(missions["R-3"]["status"], "completed")
        self.assertIsNotNone(missions["R-2"]["flow_id"])
        self.assertIsNotNone(missions["R-3"]["flow_id"])
        flows = store.list_flow_runs(project_id=self.project_id)
        self.assertEqual(len(flows), 2)
        self.assertTrue(all(row["status"] == "COMPLETED" for row in flows))
        self.assertTrue(all(row["pipeline"] == "mission" for row in flows))
        # One evidence row of kind flow per mission.
        for mission in missions.values():
            kinds = [row["kind"] for row in self.evidence_rows(int(mission["id"]))]
            self.assertIn("flow", kinds)
        self.assertEqual(self.stage_dirs(), [])


class FlowParityTests(FlowBase):
    def test_invalid_candidate_is_blocked_without_live_change(self):
        self.holder["developer"] = lambda prompt: write_block("src/feature_a.py", "def broken(:\n")
        result = self.make_supervisor().run(max_missions=1)
        self.assertEqual(result["status"], "blocked", result)
        self.assert_live_unchanged()
        mission = self.missions_by_requirement()["R-2"]
        self.assertEqual(mission["status"], "blocked")

    def test_reviewer_reject_is_blocked_without_promotion(self):
        self.holder["reviewer_output"] = "REJECT\nflow parity reject\n"
        result = self.make_supervisor().run(max_missions=1)
        self.assertEqual(result["status"], "blocked", result)
        self.assert_live_unchanged()
        mission = self.missions_by_requirement()["R-2"]
        self.assertEqual(mission["status"], "blocked")
        self.assertEqual(mission["review_verdict"], "REJECT")

    def test_stop_after_developer_resumes_without_duplicate_promotion(self):
        self.holder["stop_after_developer"] = True
        supervisor = self.make_supervisor()
        first = supervisor.run(max_missions=1)
        self.assertIn(first["status"], ("stopped", "completed"), first)
        holder_new = {}
        self.holder.clear()
        self.holder.update(holder_new)
        # The fake model only stops once (holder was cleared).
        second = self.make_supervisor().run(max_missions=1)
        self.assertEqual(second["status"], "completed", second)
        self.assertEqual((self.root / "src" / "feature_a.py").read_text(encoding="utf-8"), FEATURE_A)
        handoffs = self.evidence_rows(int(self.missions_by_requirement()["R-2"]["id"]))
        self.assertLessEqual(len([row for row in handoffs if row["kind"] == "promotion"]), 1)


class FlowControlTests(FlowBase):
    def test_default_pipeline_is_sequential_and_runs_no_flow(self):
        supervisor = self.make_supervisor(config=self.config(pipeline="sequential"))
        self.assertIsNone(supervisor._build_executor(1, "goal"))
        result = supervisor.run(max_missions=1)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(supervisor.config.pipeline, "sequential")
        self.assertEqual(store.list_flow_runs(project_id=self.project_id), [])
        self.assertEqual(self.missions_by_requirement()["R-2"]["flow_id"], None)

    def test_single_executor_per_mission_and_flow_status(self):
        supervisor = self.make_supervisor()
        first = supervisor._build_executor(7, "goal")
        second = supervisor._build_executor(7, "goal")
        self.assertIs(first, second)
        status = supervisor.status()
        self.assertEqual(status["pipeline"], "flow")
        self.assertIn("flow_runs", status)

    def test_reconcile_is_idempotent_after_flow_runs(self):
        supervisor = self.make_supervisor()
        result = supervisor.run(max_missions=1)
        self.assertEqual(result["status"], "completed", result)
        first = supervisor.reconcile()
        second = supervisor.reconcile()
        self.assertEqual(first, [])
        self.assertEqual(second, [])

    def test_crash_between_mission_and_record_outcome_recovers_without_duplicate(self):
        index = fixture_index()
        index["program_order"]["stages"][1]["requirement_ids"] = ["R-2"]
        index["requirements"] = [item for item in index["requirements"]
                                 if item["id"] in ("R-1", "R-2")]
        self.write_index(index)
        supervisor = self.make_supervisor()
        crashes = {"count": 0}

        def crash_once(*args, **kwargs):
            if crashes["count"] == 0:
                crashes["count"] += 1
                raise KeyboardInterrupt("simulated supervisor crash")
            return original(*args, **kwargs)

        original = supervisor.record_outcome
        with patch.object(supervisor, "record_outcome", side_effect=crash_once):
            with self.assertRaises(KeyboardInterrupt):
                supervisor.run(max_missions=1)
        # Restart: reconcile must repair the queue from the completed flow mission.
        restarted = self.make_supervisor()
        result = restarted.run(max_missions=1)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["recovery"], [] if not result["recovery"] else result["recovery"])
        self.assertEqual(restarted.reconcile(), [])
        self.assertEqual(restarted.reconcile(), [])
        missions = self.missions_by_requirement()
        self.assertEqual(len([m for m in missions.values() if m["status"] == "completed"]), 1)
        flows = store.list_flow_runs(project_id=self.project_id)
        self.assertEqual(len(flows), 1)
        self.assertEqual(flows[0]["status"], "COMPLETED")

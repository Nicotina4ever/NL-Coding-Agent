"""C3e / SH-07 Tier A: deterministic two-consecutive-mission supervisor acceptance.

Real MultiAgentOrchestrator pipeline (staged candidate, candidate+oracle verification,
reviewer, promotion) with only the model seam faked; a tiny temp project and a fixture
INDEX.json backlog. No Ollama/CrewAI call is made and no live repository/DB is touched.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.agents import orchestrator as orchestrator_module
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.core import resource_gate
from nl_coding_agent.core.supervisor import Supervisor, SupervisorConfig
from nl_coding_agent.persistence import database
from nl_coding_agent.persistence import supervisor_store as store
from nl_coding_agent.persistence.missions import (
    get_handoffs,
    get_mission,
    get_verification_runs,
    list_missions,
)
from nl_coding_agent.projects.registry import open_project

CALC_SOURCE = "def add(a, b):\n    return a + b\n"
TEST_SOURCE = "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
FEATURE_A = 'FEATURE_A = "a"\n'
FEATURE_B = 'FEATURE_B = "b"\n'


def write_block(rel_path: str, content: str) -> str:
    return "```write:" + rel_path + "\n" + content.rstrip("\n") + "\n```"


def fixture_index() -> dict:
    return {
        "schema_version": "1.0",
        "program_order": {
            "stages": [
                {"stage": 1, "name": "Foundation", "status": "completed",
                 "depends_on_stages": [], "requirement_ids": ["R-1"]},
                {"stage": 2, "name": "Supervisor", "status": "in_progress",
                 "depends_on_stages": [1], "requirement_ids": ["R-2", "R-3"]},
            ]
        },
        "requirements": [
            {"id": "R-1", "title": "Base", "area": "core", "priority": "P0",
             "status": "verified", "dependencies": [], "acceptance": ["base"],
             "source_refs": ["spec-1"], "program_stage": 1},
            {"id": "R-2", "title": "Add feature A in src/feature_a.py",
             "area": "autonomy", "priority": "P0", "status": "planned",
             "dependencies": ["R-1"], "acceptance": ["feature A module exists"],
             "source_refs": ["src/feature_a.py"], "program_stage": 2},
            {"id": "R-3", "title": "Add feature B in src/feature_b.py",
             "area": "autonomy", "priority": "P0", "status": "planned",
             "dependencies": ["R-1"], "acceptance": ["feature B module exists"],
             "source_refs": ["src/feature_b.py"], "program_stage": 2},
        ],
    }


class FakeModel:
    """Scripted model seam: developer writes requirements, reviewer APPROVEs."""

    def __init__(self, holder: dict) -> None:
        self.holder = holder
        self.calls: list[dict] = []

    def __call__(self, role, model_name, prompt, *, goal="", backstory="",
                 expected_output="", tools=None):
        self.calls.append({"role": role, "prompt": prompt})
        holder = self.holder
        if role == "Implementation Developer":
            custom = holder.get("developer")
            if custom is not None:
                output = custom(prompt)
            elif "feature_a" in prompt:
                output = write_block("src/feature_a.py", FEATURE_A)
            elif "feature_b" in prompt:
                output = write_block("src/feature_b.py", FEATURE_B)
            else:
                raise AssertionError("unexpected developer prompt: " + prompt[:200])
            if holder.get("stop_after_developer"):
                holder["supervisor"].control.request_stop("SH-07 test stop")
            return output
        if role == "Code Reviewer & Quality Gatekeeper":
            hook = holder.get("reviewer_hook")
            if hook is not None:
                hook(holder)
            return holder.get("reviewer_output", "APPROVE\nSH-07 fake review.\n")
        raise AssertionError("unexpected model role: " + str(role))


class SH07Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "appdata"
        self.root = Path(self._tmp.name) / "project"
        self._env = patch.dict(os.environ, {"NL_DATA_DIR": str(self.data)})
        self._env.start()
        self.addCleanup(self._env.stop)
        self._write_project()
        self.write_index(fixture_index())
        database.init_db().close()
        self.project = open_project(self.root)
        self.project_id = int(self.project["id"])
        self._git = patch.object(
            Supervisor, "_git_state",
            return_value={"head": "", "dirty": 0, "untracked": 0, "error": ""},
        )
        self._git.start()
        self.addCleanup(self._git.stop)
        self.holder: dict = {}
        self.fake = FakeModel(self.holder)

    # ---------------------------------------------------------------- setup

    def _write_project(self) -> None:
        (self.root / "nl_coding_agent").mkdir(parents=True)
        (self.root / "nl_coding_agent" / "__init__.py").write_text(
            "", encoding="utf-8", newline="")
        (self.root / "src").mkdir()
        (self.root / "src" / "__init__.py").write_text(
            "", encoding="utf-8", newline="")
        (self.root / "src" / "calc.py").write_text(
            CALC_SOURCE, encoding="utf-8", newline="")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_calc.py").write_text(
            TEST_SOURCE, encoding="utf-8", newline="")
        (self.root / "docs" / "product-blueprint").mkdir(parents=True)

    def write_index(self, data: dict | None = None) -> Path:
        path = self.root / "docs" / "product-blueprint" / "INDEX.json"
        path.write_text(
            json.dumps(data if data is not None else fixture_index(), ensure_ascii=False),
            encoding="utf-8", newline="",
        )
        return path

    def config(self, **overrides) -> SupervisorConfig:
        values = {
            "mode": "automatic",
            "max_missions_per_run": 2,
            "max_attempts_per_requirement": 1,
            "heartbeat_interval_s": 0.5,
            "lease_ttl_s": 30.0,
            "backoff_schedule_s": (0,),
            "developer_model": "ollama/sh07-dev",
            "reviewer_model": "ollama/sh07-review",
            "debug_model": "ollama/sh07-dev",
        }
        values.update(overrides)
        return SupervisorConfig(**values)

    def make_supervisor(self, *, config: SupervisorConfig | None = None) -> Supervisor:
        def factory(root):
            orchestrator = MultiAgentOrchestrator(root, project_id=self.project_id)
            orchestrator._call_model = self.fake
            return orchestrator

        def decider(cfg, *, project_id):
            return resource_gate.ResourceDecision(
                "run", "", None, {"sh07_fake_probe": True})

        supervisor = Supervisor(
            self.root, project_id=self.project_id, config=config or self.config(),
            orchestrator_factory=factory, resource_decider=decider,
        )
        self.holder["supervisor"] = supervisor
        return supervisor

    # ---------------------------------------------------------------- helpers

    def _base_files(self) -> set[str]:
        return {
            "docs/product-blueprint/INDEX.json",
            "nl_coding_agent/__init__.py",
            "src/__init__.py",
            "src/calc.py",
            "tests/test_calc.py",
        }

    def live_files(self) -> set[str]:
        files = set()
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root)
            if rel.parts and rel.parts[0] == "data":
                continue
            files.add(rel.as_posix())
        return files

    def assert_live_unchanged(self, extra: set[str] | None = None) -> None:
        self.assertEqual(
            self.live_files(), self._base_files() | set(extra or set())
        )
        self.assertEqual(
            (self.root / "src" / "calc.py").read_text(encoding="utf-8"), CALC_SOURCE
        )
        self.assertEqual(
            (self.root / "tests" / "test_calc.py").read_text(encoding="utf-8"),
            TEST_SOURCE,
        )

    def missions_by_requirement(self) -> dict[str, dict]:
        return {
            str(mission.get("requirement_id")): mission
            for mission in list_missions(self.project_id)
            if mission.get("requirement_id")
        }

    def stage_dirs(self) -> list[Path]:
        basedir = self.root / "data" / "staging"
        if not basedir.is_dir():
            return []
        return sorted(path for path in basedir.glob("mission-*") if path.is_dir())

    def evidence_rows(self, mission_id: int) -> list[dict]:
        return store.list_evidence(mission_id)


class SH07HappyPathTests(SH07Base):
    def test_two_consecutive_missions_without_manual_repair(self):
        supervisor = self.make_supervisor()
        result = supervisor.run(max_missions=2)

        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["completed"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["missions"]), 2)

        missions = self.missions_by_requirement()
        self.assertEqual(sorted(missions), ["R-2", "R-3"])
        for requirement_id, mission in missions.items():
            self.assertEqual(mission["status"], "completed")
            self.assertEqual(mission["harness_version"], 2)
            evidence = self.evidence_rows(int(mission["id"]))
            kinds = [row["kind"] for row in evidence]
            for expected in ("diff", "verification", "review", "promotion"):
                self.assertIn(expected, kinds)
            promotions = [row for row in evidence if row["kind"] == "promotion"]
            self.assertEqual(len(promotions), 1)
            promoted_handoffs = [
                handoff for handoff in get_handoffs(int(mission["id"]))
                if "Promoted" in str(handoff.get("summary") or "")
            ]
            self.assertEqual(len(promoted_handoffs), 1)
            recovery = self.data / "recovery" / (str(mission["id"]) + ".json")
            self.assertTrue(recovery.is_file())

        self.assertIn("src/feature_a.py", missions["R-2"]["changed_paths"])
        self.assertIn("src/feature_b.py", missions["R-3"]["changed_paths"])
        self.assertEqual(
            (self.root / "src" / "feature_a.py").read_text(encoding="utf-8"), FEATURE_A
        )
        self.assertEqual(
            (self.root / "src" / "feature_b.py").read_text(encoding="utf-8"), FEATURE_B
        )
        self.assert_live_unchanged({"src/feature_a.py", "src/feature_b.py"})
        self.assertEqual(self.stage_dirs(), [])

        queue = store.list_queue(self.project_id)
        self.assertEqual(len(queue), 2)
        self.assertEqual({item["requirement_id"] for item in queue}, {"R-2", "R-3"})
        self.assertTrue(all(item["state"] == "VERIFIED" for item in queue))
        self.assertTrue(all(item["attempts"] == 1 for item in queue))
        for requirement_id in ("R-2", "R-3"):
            row = store.get_backlog_item(requirement_id)
            self.assertEqual(row["supervisor_status"], "VERIFIED")
            self.assertEqual(row["last_mission_id"], missions[requirement_id]["id"])

        run = store.get_run(int(result["run_id"]))
        self.assertEqual(run["status"], "COMPLETED")
        self.assertEqual(run["missions_completed"], 2)
        self.assertIsNone(store.get_lease(self.project_id))

        roles = [call["role"] for call in self.fake.calls]
        self.assertEqual(roles.count("Implementation Developer"), 2)
        self.assertEqual(roles.count("Code Reviewer & Quality Gatekeeper"), 2)
        self.assertNotIn("Software Debugger", roles)

    def test_restart_between_missions_is_idempotent(self):
        first = self.make_supervisor()
        result_one = first.run(max_missions=1)
        self.assertEqual(result_one["status"], "completed")
        self.assertEqual(result_one["completed"], 1)
        first_missions = self.missions_by_requirement()
        self.assertEqual(sorted(first_missions), ["R-2"])
        first_mission_id = first_missions["R-2"]["id"]
        calls_after_first = len(self.fake.calls)

        second = self.make_supervisor()  # simulated supervisor restart
        result_two = second.run(max_missions=1)
        self.assertEqual(result_two["status"], "completed")
        self.assertEqual(result_two["completed"], 1)
        missions = self.missions_by_requirement()
        self.assertEqual(sorted(missions), ["R-2", "R-3"])
        self.assertNotEqual(missions["R-3"]["id"], first_mission_id)
        self.assertEqual(len(list_missions(self.project_id)), 2)
        queue = store.list_queue(self.project_id)
        self.assertEqual(len(queue), 2)
        self.assertEqual(
            [item["requirement_id"] for item in queue].count("R-2"), 1
        )
        self.assertEqual(len(self.fake.calls), calls_after_first + 2)

        third = self.make_supervisor()  # nothing left to run
        calls_before = len(self.fake.calls)
        result_three = third.run(max_missions=1)
        self.assertEqual(result_three["status"], "completed")
        self.assertEqual(result_three["completed"], 0)
        self.assertEqual(result_three["missions"], [])
        self.assertEqual(len(self.fake.calls), calls_before)
        self.assertEqual(len(list_missions(self.project_id)), 2)
        self.assertEqual(len(store.list_queue(self.project_id)), 2)

    def test_pause_at_mission_boundary_then_resume(self):
        self.holder["reviewer_hook"] = (
            lambda holder: holder["supervisor"].request_pause(requested_by="sh07")
        )
        supervisor = self.make_supervisor()
        result = supervisor.run(max_missions=2)
        self.assertEqual(result["status"], "paused", result)
        self.assertEqual(result["completed"], 1)
        self.assertTrue((self.root / "src" / "feature_a.py").is_file())
        self.assertFalse((self.root / "src" / "feature_b.py").exists())
        self.assertEqual(len(store.list_queue(self.project_id)), 1)
        self.assertEqual(
            store.get_run(int(result["run_id"]))["status"], "STOPPED"
        )

        self.holder["reviewer_hook"] = None
        resumed = self.make_supervisor()
        result_two = resumed.run(max_missions=2)
        self.assertEqual(result_two["status"], "completed")
        self.assertEqual(result_two["completed"], 1)
        self.assert_live_unchanged({"src/feature_a.py", "src/feature_b.py"})
        queue = store.list_queue(self.project_id)
        self.assertEqual(len(queue), 2)
        self.assertTrue(all(item["state"] == "VERIFIED" for item in queue))

    def test_stop_at_boundary_resumes_without_duplicate_promotion(self):
        self.holder["stop_after_developer"] = True
        supervisor = self.make_supervisor()
        result = supervisor.run(max_missions=1)
        self.assertEqual(result["status"], "stopped", result)
        self.assertEqual(result["completed"], 0)
        self.assertFalse((self.root / "src" / "feature_a.py").exists())
        queue = store.list_queue(self.project_id)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["state"], "INTERRUPTED")
        interrupted_mission_id = queue[0]["mission_id"]
        interrupted_mission = get_mission(int(interrupted_mission_id))
        self.assertEqual(interrupted_mission["status"], "interrupted")
        # promotion_status=validated proves the stop happened after the developer
        # stage (the staged candidate was validated) and before any promotion.
        self.assertEqual(interrupted_mission["promotion_status"], "validated")

        self.holder["stop_after_developer"] = False
        resumed = self.make_supervisor()
        result_two = resumed.run(max_missions=1)
        self.assertEqual(result_two["status"], "completed")
        self.assertEqual(result_two["completed"], 1)
        missions = self.missions_by_requirement()
        self.assertEqual(len(missions), 1)  # no duplicate mission
        self.assertEqual(missions["R-2"]["id"], interrupted_mission_id)
        self.assertEqual(missions["R-2"]["status"], "completed")
        self.assertEqual(
            (self.root / "src" / "feature_a.py").read_text(encoding="utf-8"), FEATURE_A
        )
        self.assert_live_unchanged({"src/feature_a.py"})
        queue = store.list_queue(self.project_id)
        self.assertEqual(queue[0]["state"], "VERIFIED")
        promotions = [
            handoff for handoff in get_handoffs(int(interrupted_mission_id))
            if "Promoted" in str(handoff.get("summary") or "")
        ]
        self.assertEqual(len(promotions), 1)


class SH07FailClosedTests(SH07Base):
    def test_invalid_candidate_is_blocked_without_live_write(self):
        self.holder["developer"] = lambda prompt: write_block(
            "src/feature_a.py", "def broken(:\n    pass\n"
        )
        result = self.make_supervisor().run(max_missions=1)
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["completed"], 0)
        self.assertFalse((self.root / "src" / "feature_a.py").exists())
        self.assert_live_unchanged()
        mission = self.missions_by_requirement()["R-2"]
        self.assertEqual(mission["status"], "blocked")
        evidence = self.evidence_rows(int(mission["id"]))
        kinds = [row["kind"] for row in evidence]
        self.assertIn("failure", kinds)
        self.assertNotIn("promotion", kinds)
        queue = store.list_queue(self.project_id)
        self.assertEqual(queue[0]["state"], "BLOCKED")
        self.assertEqual(queue[0]["failure_class"], "BUDGET_EXHAUSTED")
        self.assertEqual(
            store.get_backlog_item("R-2")["supervisor_status"], "BLOCKED"
        )
        self.assertFalse(
            (self.data / "recovery" / (str(mission["id"]) + ".json")).exists()
        )
        self.assertTrue(self.stage_dirs())
        self.assertEqual(
            [call["role"] for call in self.fake.calls], ["Implementation Developer"]
        )

    def test_oracle_red_candidate_is_blocked(self):
        index = fixture_index()
        index["requirements"][1]["title"] = "Change src/calc.py and tests/test_calc.py"
        index["requirements"][1]["source_refs"] = ["src/calc.py", "tests/test_calc.py"]
        self.write_index(index)
        self.holder["developer"] = lambda prompt: (
            write_block("src/calc.py", "def add(a, b):\n    return a - b\n")
            + "\n"
            + write_block(
                "tests/test_calc.py",
                "from src.calc import add\n\n\ndef test_add():\n"
                "    assert add(1, 2) == -1\n",
            )
        )
        with patch.object(orchestrator_module, "MAX_REPAIR_ATTEMPTS", 0):
            result = self.make_supervisor().run(max_missions=1)
        self.assertEqual(result["status"], "blocked", result)
        self.assertEqual(result["completed"], 0)
        self.assert_live_unchanged()
        mission = self.missions_by_requirement()["R-2"]
        self.assertEqual(mission["status"], "blocked")
        runs = get_verification_runs(int(mission["id"]))
        self.assertTrue(runs)
        self.assertTrue(any(
            str(row["command"]).startswith("verify:candidate")
            and int(row["passed"]) == 1 for row in runs
        ))
        self.assertTrue(any(
            str(row["command"]).startswith("verify:oracle")
            and int(row["passed"]) == 0 for row in runs
        ))
        kinds = [row["kind"] for row in self.evidence_rows(int(mission["id"]))]
        self.assertNotIn("promotion", kinds)
        self.assertIn("failure", kinds)
        self.assertEqual(store.list_queue(self.project_id)[0]["state"], "BLOCKED")
        self.assertFalse(
            (self.data / "recovery" / (str(mission["id"]) + ".json")).exists()
        )

    def test_automatic_mode_off_by_default_runs_nothing(self):
        self.assertEqual(SupervisorConfig.load(None).mode, "off")
        supervisor = self.make_supervisor(config=SupervisorConfig())
        result = supervisor.run(max_missions=2)
        self.assertEqual(result["status"], "off")
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(list_missions(self.project_id), [])
        self.assertEqual(store.list_queue(self.project_id), [])
        self.assertIsNone(store.get_lease(self.project_id))
        self.assert_live_unchanged()


if __name__ == "__main__":
    unittest.main()

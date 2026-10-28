"""C3b: indexed-backlog loader, program-stage gate and deterministic mission planner."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.core import backlog as B
from nl_coding_agent.persistence import database
from nl_coding_agent.persistence import supervisor_store as store

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_INDEX = REPO_ROOT / "docs" / "product-blueprint" / "INDEX.json"


def valid_index() -> dict:
    return {
        "schema_version": 1,
        "program_order": {
            "stages": [
                {"stage": 1, "name": "Foundation", "status": "completed",
                 "depends_on_stages": [], "requirement_ids": ["R-1"]},
                {"stage": 2, "name": "Supervisor", "status": "in_progress",
                 "depends_on_stages": [1], "requirement_ids": ["R-2", "R-3"]},
                {"stage": 3, "name": "After", "status": "pending",
                 "depends_on_stages": [2], "requirement_ids": ["R-4"]},
            ]
        },
        "requirements": [
            {"id": "R-1", "title": "Base", "area": "core", "priority": "P0",
             "status": "verified", "dependencies": [], "acceptance": ["base works"],
             "source_refs": ["spec-1"], "program_stage": 1,
             "program_stage_name": "Foundation"},
            {"id": "R-2", "title": "Second", "area": "autonomy", "priority": "P1",
             "status": "planned", "dependencies": ["R-1"],
             "acceptance": ["second works"], "source_refs": ["spec-2"],
             "program_stage": 2},
            {"id": "R-3", "title": "Third", "area": "autonomy", "priority": "P0",
             "status": "planned", "dependencies": ["R-1"],
             "acceptance": [], "source_refs": [],
             "program_stage": 2},
            {"id": "R-4", "title": "Later", "area": "later", "priority": "P0",
             "status": "planned", "dependencies": [], "acceptance": [],
             "source_refs": [], "program_stage": 3},
        ],
    }


class PlannerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "project"
        self.data = Path(self._tmp.name) / "data"
        self.index_dir = self.root / "docs" / "product-blueprint"
        self.index_dir.mkdir(parents=True)
        self.index_path = self.index_dir / "INDEX.json"
        self._env = patch.dict(os.environ, {"NL_DATA_DIR": str(self.data)})
        self._env.start()
        self.addCleanup(self._env.stop)
        database.init_db().close()

    # ---------------------------------------------------------------- helpers

    def write_index(self, data: dict | str, *, path: Path | None = None) -> Path:
        target = path or self.index_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            target.write_text(data, encoding="utf-8", newline="")
        else:
            target.write_text(
                json.dumps(data, ensure_ascii=False, indent=1),
                encoding="utf-8", newline="",
            )
        return target

    def load_valid(self, data: dict | None = None) -> B.BacklogIndex:
        self.write_index(data if data is not None else valid_index())
        return B.load_index(self.index_path)

    def select(self, index: B.BacklogIndex, *, config=None, in_flight=None):
        return B.select_next_requirement(
            1, project_root=self.root, index=index, config=config,
            in_flight_requirement_ids=in_flight,
        )

    def create_project(self) -> int:
        conn = database.get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO projects (name, root) VALUES ('project', 'X:/project')"
                )
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def assert_invalid(self, data, message: str) -> None:
        with self.assertRaises(B.BacklogValidationError, msg=message) as ctx:
            self.write_index(data)
            B.load_index(self.index_path)
        self.assertIsInstance(ctx.exception, B.BacklogValidationError)


class LoaderTests(PlannerTestCase):
    def test_valid_index_loads_with_program_order(self):
        index = self.load_valid()
        self.assertEqual(index.schema_version, 1)
        self.assertEqual(len(index.requirements), 4)
        self.assertEqual([stage.stage for stage in index.stages], [1, 2, 3])
        self.assertEqual(index.by_id()["R-2"].priority, "P1")
        current = B.current_program_stage(index)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.stage, 2)
        self.assertEqual(current.name, "Supervisor")
        self.assertEqual(index.warnings, ())
        expected_hash = hashlib.sha256(self.index_path.read_bytes()).hexdigest()
        self.assertEqual(index.source_fingerprint, expected_hash)

    def test_authored_string_schema_version_is_accepted(self):
        data = valid_index()
        data["schema_version"] = "1.0"
        index = self.load_valid(data)
        self.assertEqual(index.schema_version, 1)

    def test_missing_corrupt_and_wrong_schema_fail_closed(self):
        with self.assertRaises(B.BacklogError):
            B.load_index(self.index_path)  # missing file
        self.write_index("{this is not json")
        with self.assertRaises(B.BacklogValidationError):
            B.load_index(self.index_path)
        for bad in (2, "2.0", None, 1.5, True):
            data = valid_index()
            data["schema_version"] = bad
            self.assert_invalid(data, "schema_version=" + repr(bad))

    def test_structural_errors_are_rejected(self):
        cases = []
        data = valid_index()
        del data["program_order"]
        cases.append(("missing program_order", data))
        data = valid_index()
        data["program_order"]["stages"] = []
        cases.append(("empty stages", data))
        data = valid_index()
        data["requirements"] = []
        cases.append(("empty requirements", data))
        data = valid_index()
        data["requirements"].append(copy.deepcopy(data["requirements"][0]))
        cases.append(("duplicate requirement id", data))
        data = valid_index()
        data["requirements"][1]["status"] = "later"
        cases.append(("invalid requirement status", data))
        data = valid_index()
        data["requirements"][1]["priority"] = "P9"
        cases.append(("invalid priority", data))
        data = valid_index()
        data["program_order"]["stages"][0]["status"] = "done"
        cases.append(("invalid stage status", data))
        data = valid_index()
        data["program_order"]["stages"][2]["stage"] = 2
        cases.append(("duplicate stage", data))
        data = valid_index()
        del data["requirements"][1]["title"]
        cases.append(("missing title", data))
        data = valid_index()
        data["requirements"][1]["dependencies"] = "R-1"
        cases.append(("dependencies not a list", data))
        for label, data in cases:
            self.assert_invalid(data, label)

    def test_project_index_resolution_stays_inside_project(self):
        self.write_index(valid_index())
        resolved = B.resolve_index_path(self.root)
        self.assertEqual(resolved, self.index_path.resolve())
        outside = Path(self._tmp.name) / "outside.json"
        self.write_index(valid_index(), path=outside)
        with self.assertRaises(B.BacklogValidationError):
            B.resolve_index_path(self.root, outside)
        loaded = B.load_project_index(self.root)
        self.assertEqual(len(loaded.requirements), 4)


class SelectionTests(PlannerTestCase):
    def test_dependency_gate_and_priority_ordering(self):
        index = self.load_valid()
        selected = self.select(index)
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["requirement_id"], "R-3")  # P0 before P1
        self.assertEqual(selected["program_stage"], 2)
        self.assertEqual(selected["max_attempts"], 2)

        data = valid_index()
        data["requirements"][2]["dependencies"] = ["R-4"]  # R-4 is not verified
        index = self.load_valid(data)
        self.assertEqual(self.select(index)["requirement_id"], "R-2")

        data["requirements"][3]["status"] = "verified"
        index = self.load_valid(data)
        self.assertEqual(self.select(index)["requirement_id"], "R-3")

    def test_unknown_dependency_warns_and_is_not_selectable(self):
        data = valid_index()
        data["requirements"][2]["dependencies"] = ["R-404"]
        index = self.load_valid(data)
        self.assertTrue(any("R-404" in warning for warning in index.warnings))
        selected = self.select(index)
        self.assertEqual(selected["requirement_id"], "R-2")

    def test_no_current_stage_and_no_candidate(self):
        data = valid_index()
        for stage in data["program_order"]["stages"]:
            stage["status"] = "completed"
        index = self.load_valid(data)
        self.assertIsNone(B.current_program_stage(index))
        self.assertIsNone(self.select(index))

        data = valid_index()
        for requirement in data["requirements"][1:3]:
            requirement["status"] = "verified"
        index = self.load_valid(data)
        self.assertIsNone(self.select(index))

    def test_program_stage_override(self):
        index = self.load_valid()
        selected = self.select(index, config={"program_stage_override": 3})
        self.assertEqual(selected["requirement_id"], "R-4")
        with self.assertRaises(B.BacklogValidationError):
            self.select(index, config={"program_stage_override": 9})

    def test_verified_authored_item_is_not_selected(self):
        data = valid_index()
        data["requirements"][2]["status"] = "verified"
        index = self.load_valid(data)
        self.assertEqual(self.select(index)["requirement_id"], "R-2")

    def test_in_flight_and_attempt_exclusions(self):
        index = self.load_valid()
        selected = self.select(index, in_flight={"R-3"})
        self.assertEqual(selected["requirement_id"], "R-2")
        self.assertIsNone(self.select(index, in_flight={"R-2", "R-3"}))

        conn = database.get_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO backlog_items (requirement_id, title, status, content_hash, "
                    "last_synced_at, attempts) VALUES ('R-3', 'Third', 'planned', 'h', 'now', 2)"
                )
        finally:
            conn.close()
        selected = self.select(index)
        self.assertEqual(selected["requirement_id"], "R-2")

    def test_requirement_without_program_stage_is_derived_from_stage_list(self):
        data = valid_index()
        del data["requirements"][1]["program_stage"]
        index = self.load_valid(data)
        self.assertEqual(index.by_id()["R-2"].program_stage, 2)
        self.assertEqual(index.by_id()["R-2"].program_stage_name, "Supervisor")


class HashAndKeyTests(PlannerTestCase):
    def test_content_hash_is_stable_and_tracks_contract_fields(self):
        base = valid_index()["requirements"][2]
        first = B.requirement_content_hash(base)
        self.assertEqual(first, B.requirement_content_hash(copy.deepcopy(base)))
        noisy = copy.deepcopy(base)
        noisy["evidence"] = ["some evidence"]
        noisy["note"] = "human note"
        noisy["backlog_anchor"] = "nl-bp-999"
        self.assertEqual(first, B.requirement_content_hash(noisy))
        changed = copy.deepcopy(base)
        changed["acceptance"] = ["different gate"]
        self.assertNotEqual(first, B.requirement_content_hash(changed))

    def test_idempotency_key_is_stable_and_dedupes_queue_rows(self):
        index = self.load_valid()
        stage = B.current_program_stage(index)
        assert stage is not None
        requirement = index.by_id()["R-3"]
        first = B.idempotency_key(requirement, stage, git_head="abc")
        self.assertEqual(first, B.idempotency_key(requirement, stage, git_head="abc"))
        self.assertNotEqual(first, B.idempotency_key(requirement, stage, git_head="def"))
        changed = copy.deepcopy(requirement.raw)
        changed["acceptance"] = ["new gate"]
        self.assertNotEqual(
            B.requirement_content_hash(changed), requirement.content_hash
        )

        selected = self.select(index)
        project_id = self.create_project()
        queue_id = store.enqueue_mission(
            project_id, requirement_id=selected["requirement_id"],
            goal=selected["goal"], priority=selected["priority"],
            idempotency_key=selected["idempotency_key"], max_attempts=2,
            budget={}, payload={"requirement": selected["requirement_id"]},
        )
        again = store.enqueue_mission(
            project_id, requirement_id=selected["requirement_id"],
            goal=selected["goal"], priority=selected["priority"],
            idempotency_key=selected["idempotency_key"], max_attempts=2,
            budget={},
        )
        self.assertEqual(queue_id, again)
        self.assertEqual(len(store.list_queue(project_id)), 1)

        explicit = B.select_next_requirement(
            1, project_root=self.root, index=index,
            config=B.PlannerConfig(git_head="fixed-head"),
        )
        self.assertEqual(
            explicit["idempotency_key"],
            B.idempotency_key(index.by_id()["R-3"], stage, git_head="fixed-head"),
        )


class GoalTests(PlannerTestCase):
    def test_goal_composition_contains_the_mission_contract(self):
        index = self.load_valid()
        stage = B.current_program_stage(index)
        assert stage is not None
        requirement = index.by_id()["R-2"]
        goal = B.compose_mission_goal(requirement, stage)
        self.assertIn("[R-2] Second", goal)
        self.assertIn("Program stage 2: Supervisor", goal)
        self.assertIn("Area: autonomy; Priority: P1", goal)
        self.assertIn("- second works", goal)
        self.assertIn("Implementation requirement", goal)
        self.assertIn("documentation-only or comment-only change does not satisfy", goal)
        self.assertNotIn("Source references", goal)
        self.assertNotIn("spec-2", goal)
        self.assertIn("nothing is live until promotion", goal)
        self.assertEqual(goal, B.compose_mission_goal(requirement, stage))

    def test_mission_payload_is_deterministic(self):
        index = self.load_valid()
        stage = B.current_program_stage(index)
        assert stage is not None
        requirement = index.by_id()["R-3"]
        first = B.build_mission_payload(requirement, stage, project_id=7,
                                        max_attempts=3, git_head="head")
        second = B.build_mission_payload(requirement, stage, project_id=7,
                                         max_attempts=3, git_head="head")
        self.assertEqual(first, second)
        self.assertEqual(first["title"], "[R-3] Third")
        self.assertEqual(first["idempotency_key"],
                         B.idempotency_key(requirement, stage, git_head="head"))
        self.assertEqual(first["program_stage"], 2)


class MirrorTests(PlannerTestCase):
    def test_mirror_sync_and_verified_upgrade(self):
        index = self.load_valid()
        report = B.sync_backlog_mirror(1, index)
        self.assertEqual(report["inserted"], ["R-1", "R-2", "R-3", "R-4"])
        self.assertEqual(B.mirror_source_fingerprint(1), index.source_fingerprint)
        self.assertEqual(store.get_backlog_item("R-2")["supervisor_status"], None)

        self.assertTrue(store.set_backlog_progress("R-3", supervisor_status="VERIFIED"))
        selected = self.select(index)
        self.assertEqual(selected["requirement_id"], "R-2")

        self.assertTrue(store.set_backlog_progress("R-2", supervisor_status="IN_FLIGHT"))
        self.assertIsNone(self.select(index))

    def test_mirror_rejects_unvalidated_index(self):
        with self.assertRaises(B.BacklogError):
            B.sync_backlog_mirror(1, {"requirements": []})


class RealIndexTests(PlannerTestCase):
    def test_real_index_loads_read_only(self):
        self.assertTrue(REAL_INDEX.is_file())
        index = B.load_index(REAL_INDEX)
        self.assertEqual(index.schema_version, 1)
        self.assertGreaterEqual(len(index.requirements), 100)
        # Stage 7 (universal autonomy/research/Mega Suite) and stage 8 (universal
        # goal mode/document-driven planning) are queue-only extensions; stages 1-6 remain
        # the authoritative shipped-program track.
        self.assertEqual(sorted(stage.stage for stage in index.stages), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        fingerprint = hashlib.sha256(REAL_INDEX.read_bytes()).hexdigest()
        self.assertEqual(index.source_fingerprint, fingerprint)
        current = B.current_program_stage(index)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertNotEqual(current.status, "completed")
        completed = {stage.stage for stage in index.stages if stage.status == "completed"}
        self.assertTrue(set(current.depends_on_stages) <= completed)

        selected = B.select_next_requirement(
            1, project_root=REPO_ROOT, index=index,
            config=B.PlannerConfig(git_head="read-only"),
        )
        if selected is not None:
            self.assertEqual(selected["program_stage"], current.stage)
            effective = {
                requirement.requirement_id: B.effective_status(requirement, None)
                for requirement in index.requirements
            }
            for dependency in selected["dependencies"]:
                self.assertEqual(effective.get(dependency), "verified")


class StaticDependencyTests(unittest.TestCase):
    def test_backlog_module_has_no_roadmap_dependency(self):
        source_path = Path(B.__file__)
        source = source_path.read_text(encoding="utf-8")
        self.assertNotIn("NEXT_SELF_BUILD_MISSION", source)
        self.assertNotIn("next_mission", source)
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(
            any("roadmap" in name.lower() for name in imported),
            msg="backlog must not import any roadmap module: " + repr(imported),
        )
        self.assertFalse(
            any("autonomous_roadmap_planner" in name for name in imported),
            msg=repr(imported),
        )


if __name__ == "__main__":
    unittest.main()

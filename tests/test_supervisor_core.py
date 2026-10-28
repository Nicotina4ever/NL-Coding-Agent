"""C3c: supervisor core - control, resource gate, preflight, reconcile and loop.

Fake orchestrator and fake resource probes only: no LLM/CrewAI call is made and every
test uses a temporary NL_DATA_DIR/project unless it explicitly builds the real
orchestrator with a monkeypatched _call_model seam.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.agents import orchestrator as orchestrator_module
from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
from nl_coding_agent.core import backlog as backlog_module
from nl_coding_agent.core import promotion
from nl_coding_agent.core import resource_gate
from nl_coding_agent.core import supervisor as supervisor_module
from nl_coding_agent.core.run_control import RunControl, RunStopped
from nl_coding_agent.core.supervisor import (
    Supervisor,
    SupervisorConfig,
    SupervisorError,
    resume_command,
    run_supervisor,
    supervisor_command,
    supervisor_status,
)
from nl_coding_agent.persistence import database, supervisor_store as store
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_mission,
    set_mission_staging,
    update_mission_result,
    update_mission_status,
)
from nl_coding_agent.projects.registry import open_project


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
            {"id": "R-2", "title": "Second", "area": "autonomy", "priority": "P0",
             "status": "planned", "dependencies": ["R-1"],
             "acceptance": ["works"], "source_refs": ["spec-2"], "program_stage": 2},
            {"id": "R-3", "title": "Third", "area": "autonomy", "priority": "P1",
             "status": "planned", "dependencies": ["R-1"],
             "acceptance": ["also works"], "source_refs": [], "program_stage": 2},
        ],
    }


def fake_decision(action: str = "run", reason: str = "", retry_after_s=None):
    return resource_gate.ResourceDecision(
        action, reason, retry_after_s, {"fake_probe": True}
    )


class FakeOrchestrator:
    def __init__(self, root, scripts, calls):
        self.root = root
        self.scripts = scripts
        self.calls = calls

    def run_mission(self, **kwargs):
        self.calls.append(kwargs)
        script = self.scripts.pop(0)
        return script(kwargs)


class SupervisorTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "project"
        self.data = Path(self._tmp.name) / "data"
        (self.root / "docs" / "product-blueprint").mkdir(parents=True)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8", newline="")
        self.write_index()
        self._env = patch.dict(os.environ, {"NL_DATA_DIR": str(self.data)})
        self._env.start()
        self.addCleanup(self._env.stop)
        database.init_db().close()
        self.project = open_project(self.root)
        self.project_id = int(self.project["id"])
        self._git = patch.object(
            Supervisor, "_git_state",
            return_value={"head": "", "dirty": 0, "untracked": 0, "error": ""},
        )
        self._git.start()
        self.addCleanup(self._git.stop)
        self.calls: list[dict] = []
        index = backlog_module.load_project_index(self.root)
        backlog_module.sync_backlog_mirror(self.project_id, index)

    # ---------------------------------------------------------------- helpers

    def write_index(self, data: dict | None = None) -> Path:
        path = self.root / "docs" / "product-blueprint" / "INDEX.json"
        path.write_text(
            json.dumps(data if data is not None else fixture_index(), ensure_ascii=False),
            encoding="utf-8", newline="",
        )
        return path

    def config(self, **overrides) -> SupervisorConfig:
        kwargs = {
            "mode": "automatic",
            "max_missions_per_run": 1,
            "max_attempts_per_requirement": 1,
            "heartbeat_interval_s": 0.2,
            "lease_ttl_s": 30.0,
            "backoff_schedule_s": (0,),
            "developer_model": "ollama/local-dev",
            "reviewer_model": "ollama/local-review",
            "debug_model": "ollama/local-dev",
        }
        kwargs.update(overrides)
        return SupervisorConfig(**kwargs)

    def decider(self, decision=None):
        value = decision or fake_decision("run")

        def decide(config, *, project_id):
            return value

        return decide

    def supervisor(self, *, config=None, scripts=None, decider=None,
                   project_id=None, control=None) -> Supervisor:
        scripts = list(scripts or [self.completed_script()])

        def factory(root):
            return FakeOrchestrator(root, scripts, self.calls)

        return Supervisor(
            self.root,
            project_id=project_id if project_id is not None else self.project_id,
            config=config or self.config(),
            orchestrator_factory=factory,
            resource_decider=decider or self.decider(),
            control=control,
        )

    def completed_script(self):
        def script(kwargs):
            mission_id = kwargs["mission_id"]
            update_mission_result(
                mission_id, "completed",
                result_summary="fake mission completed", review_verdict="APPROVE",
                diff_stat="1 file(s), +1/-0", changed_paths=["src/app.py"],
            )
            return {
                "status": "completed", "mission_id": mission_id,
                "verdict": "APPROVE", "diff_stat": "1 file(s), +1/-0",
                "changed_paths": ["src/app.py"], "review": "APPROVE fake",
                "promotion_status": "promoted",
                "verification_runs": [
                    {"command": "verify:candidate python", "passed": 1, "exit_code": 0},
                ],
            }

        return script

    def blocked_script(self, message: str = "Candidate rejected by the validation gate"):
        def script(kwargs):
            mission_id = kwargs["mission_id"]
            update_mission_result(
                mission_id, "blocked", result_summary=message,
                review_verdict="REJECT", diff_stat="", changed_paths=[],
            )
            return {
                "status": "blocked", "mission_id": mission_id,
                "error": message, "promotion_status": "candidate_rejected",
            }

        return script

    def queue_item(self, requirement_id: str = "R-2", *, state: str = "READY",
                   attempts: int = 0, max_attempts: int = 1) -> int:
        queue_id = store.enqueue_mission(
            self.project_id, requirement_id=requirement_id, goal="do work",
            priority="P0",
            idempotency_key="key-" + requirement_id + "-" + state + "-" + str(id(self)),
            max_attempts=max_attempts, budget={},
        )
        if state == "READY":
            return queue_id
        token = "token-" + str(queue_id)
        self.assertTrue(store.claim_queue_item(queue_id, claim_token=token,
                                               owner_id="tester"))
        path = supervisor_module._transition_path("CLAIMED", state)
        self.assertIsNotNone(path, msg="unreachable state " + state)
        for step in path or []:
            self.assertTrue(store.update_queue_item(
                queue_id, claim_token=token, state=step,
                increment_attempts=(step == "RUNNING" and attempts > 0),
            ))
        current = store.get_queue_item(queue_id)["attempts"]
        while attempts > current:
            self.assertTrue(store.update_queue_item(
                queue_id, claim_token=token, increment_attempts=True))
            current += 1
        return queue_id

    def attach_mission(self, queue_id: int, *, requirement_id: str = "R-2") -> int:
        mission_id = create_mission(
            self.project_id, "[R] mission", "do work",
            requirement_id=requirement_id, supervisor_run_id=1,
        )
        item = store.get_queue_item(queue_id)
        store.update_queue_item(queue_id, claim_token=item.get("claim_token"),
                                mission_id=mission_id)
        return mission_id


# --------------------------------------------------------------------------- #
# RunControl
# --------------------------------------------------------------------------- #

class RunControlTests(unittest.TestCase):
    def test_flags_and_checkpoint_raise(self):
        control = RunControl()
        seen: list[str] = []
        control._checkpoint_hook = seen.append
        self.assertFalse(control.stop_requested or control.pause_requested)
        control.checkpoint("before-developer")
        control.request_pause()
        self.assertTrue(control.pause_requested)
        control.clear_pause()
        self.assertFalse(control.pause_requested)
        control.request_stop("operator stop")
        with self.assertRaises(RunStopped) as ctx:
            control.checkpoint("after-tester")
        self.assertEqual(ctx.exception.stage, "after-tester")
        self.assertIn("operator stop", str(ctx.exception))
        self.assertEqual(seen, ["before-developer", "after-tester"])
        control.clear_stop()
        control.checkpoint("before-reviewer")

    def test_shared_events_and_reason_preserved(self):
        stop_event = threading.Event()
        control = RunControl(stop_event=stop_event)
        control.request_stop()
        self.assertTrue(stop_event.is_set())
        control.request_stop("because")
        self.assertEqual(control.stop_reason, "because")
        control.clear_stop()
        self.assertFalse(stop_event.is_set())


# --------------------------------------------------------------------------- #
# Resource gate
# --------------------------------------------------------------------------- #

class ResourceGateTests(SupervisorTestCase):
    class Model:
        def __init__(self, name):
            self.name = name

    def test_unreachable_ollama_is_a_wait(self):
        with patch.object(resource_gate.ollama_registry, "check_ollama_reachable",
                          return_value=False):
            decision = resource_gate.decide(self.config(), project_id=self.project_id)
        self.assertEqual(decision.action, "wait")
        self.assertIn("not reachable", decision.reason)
        self.assertEqual(decision.retry_after_s, 0)

    def test_missing_role_model_is_a_wait(self):
        with patch.object(resource_gate.ollama_registry, "check_ollama_reachable",
                          return_value=True), \
                patch.object(resource_gate.ollama_registry, "list_models",
                             return_value=[self.Model("some-other-model")]), \
                patch.object(resource_gate.ollama_registry, "list_loaded_models",
                             return_value=[]):
            decision = resource_gate.decide(self.config(), project_id=self.project_id)
        self.assertEqual(decision.action, "wait")
        self.assertIn("local-dev", decision.reason)

    def test_available_local_models_are_ready(self):
        with patch.object(resource_gate.ollama_registry, "check_ollama_reachable",
                          return_value=True), \
                patch.object(resource_gate.ollama_registry, "list_models",
                             return_value=[self.Model("local-dev"),
                                           self.Model("local-review")]), \
                patch.object(resource_gate.ollama_registry, "list_loaded_models",
                             return_value=[]):
            decision = resource_gate.decide(self.config(), project_id=self.project_id)
            self.assertEqual(decision.action, "run")
            self.assertEqual(resource_gate.missing_role_models(self.config()), [])

    def test_cloud_model_without_grant_is_blocked_before_probing(self):
        config = self.config(developer_model="ollama/gpt-oss:120b-cloud")
        with patch.object(resource_gate.ollama_registry, "check_ollama_reachable",
                          side_effect=AssertionError("probe must not run")):
            decision = resource_gate.decide(config, project_id=self.project_id)
        self.assertEqual(decision.action, "blocked")
        self.assertIn("CLOUD", decision.reason)

    def test_busy_machine_slot_is_a_wait(self):
        lease = store.acquire_machine_lease(
            resource_gate.INFERENCE_RESOURCE, owner_id="other-project",
            owner_pid=os.getpid(), owner_host="host", ttl_s=60,
        )
        self.assertIsNotNone(lease)
        try:
            with patch.object(resource_gate.ollama_registry, "check_ollama_reachable",
                              return_value=True), \
                    patch.object(resource_gate.ollama_registry, "list_models",
                                 return_value=[self.Model("local-dev"),
                                               self.Model("local-review")]), \
                    patch.object(resource_gate.ollama_registry, "list_loaded_models",
                                 return_value=[]):
                decision = resource_gate.decide(self.config(), project_id=self.project_id)
            self.assertEqual(decision.action, "wait")
            self.assertIn("machine inference slot", decision.reason)
        finally:
            store.release_machine_lease(resource_gate.INFERENCE_RESOURCE,
                                        owner_id="other-project")

    def test_inference_slot_acquire_release(self):
        self.assertTrue(resource_gate.acquire_inference_slot(
            "owner-a", os.getpid(), "host", ttl_s=60))
        self.assertFalse(resource_gate.acquire_inference_slot(
            "owner-b", os.getpid(), "host", ttl_s=60))
        resource_gate.release_inference_slot("owner-a")
        self.assertTrue(resource_gate.acquire_inference_slot(
            "owner-b", os.getpid(), "host", ttl_s=60))
        resource_gate.release_inference_slot("owner-b")


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #

class PreflightTests(SupervisorTestCase):
    def test_off_mode_is_the_default_and_does_not_run(self):
        self.assertEqual(SupervisorConfig.load(None).mode, "off")
        supervisor = self.supervisor(config=self.config(mode="off"))
        result = supervisor.run()
        self.assertEqual(result["status"], "off")
        self.assertEqual(self.calls, [])
        self.assertEqual(store.list_queue(self.project_id), [])

    def test_missing_backlog_index_blocks_fail_closed(self):
        (self.root / "docs" / "product-blueprint" / "INDEX.json").unlink()
        supervisor = self.supervisor()
        report = supervisor.preflight()
        self.assertFalse(report.ok)
        self.assertTrue(any("Backlog" in blocker for blocker in report.blockers))
        result = supervisor.run()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.calls, [])
        self.assertIsNone(store.get_lease(self.project_id))

    def test_corrupt_backlog_index_blocks_fail_closed(self):
        (self.root / "docs" / "product-blueprint" / "INDEX.json").write_text(
            "{not-json", encoding="utf-8", newline="",
        )
        supervisor = self.supervisor()
        report = supervisor.preflight()
        self.assertFalse(report.ok)
        self.assertTrue(any("not usable" in blocker for blocker in report.blockers))
        self.assertEqual(supervisor.run()["status"], "blocked")
        self.assertEqual(self.calls, [])

    def test_unreconciled_promotion_journal_blocks_without_model_call(self):
        mission_id = create_mission(self.project_id, "[R-2] staged", "do work",
                                    requirement_id="R-2")
        stage = promotion.begin_stage(self.root, mission_id, ["src/app.py"])
        set_mission_staging(mission_id, str(stage.stage_dir))
        (stage.stage_dir / promotion.PROMOTION_JOURNAL).write_text(
            json.dumps({"changed": {}}), encoding="utf-8", newline="",
        )
        supervisor = self.supervisor()
        report = supervisor.preflight()
        self.assertFalse(report.ok)
        self.assertTrue(any("promotion" in blocker.lower() for blocker in report.blockers))
        result = supervisor.run()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.calls, [])
        self.assertIsNone(store.get_lease(self.project_id))

    def test_legacy_missions_are_excluded_with_warning(self):
        legacy_id = create_mission(self.project_id, "legacy", "old work",
                                   harness_version=1)
        update_mission_status(legacy_id, "interrupted")
        supervisor = self.supervisor()
        report = supervisor.preflight()
        self.assertTrue(report.ok)
        self.assertTrue(any(str(legacy_id) in warning for warning in report.warnings))

    def test_missing_base_permission_blocks(self):
        from nl_coding_agent.core import permissions

        permissions.revoke(permissions.WRITE)
        supervisor = self.supervisor()
        report = supervisor.preflight()
        self.assertFalse(report.ok)
        self.assertTrue(any("WRITE" in blocker for blocker in report.blockers))
        self.assertEqual(supervisor.run()["status"], "blocked")
        self.assertEqual(self.calls, [])

    def test_invalid_config_blocks(self):
        supervisor = self.supervisor(config=self.config(max_attempts_per_requirement=0))
        report = supervisor.preflight()
        self.assertFalse(report.ok)
        self.assertTrue(any("configuration" in blocker for blocker in report.blockers))

    def test_resource_wait_preflight_and_run(self):
        decider = self.decider(fake_decision("wait", "Ollama is not reachable", 30))
        supervisor = self.supervisor(decider=decider)
        report = supervisor.preflight()
        self.assertTrue(report.ok)
        self.assertTrue(any("not reachable" in warning for warning in report.warnings))
        result = supervisor.run()
        self.assertEqual(result["status"], "waiting_for_resources")
        self.assertEqual(result["retry_after_s"], 30)
        self.assertEqual(self.calls, [])
        self.assertIsNone(store.get_lease(self.project_id))
        self.assertEqual(store.get_run(result["run_id"])["status"], "STOPPED")


# --------------------------------------------------------------------------- #
# Run loop
# --------------------------------------------------------------------------- #

class RunLoopTests(SupervisorTestCase):
    def test_happy_path_single_mission_updates_everything(self):
        supervisor = self.supervisor()
        result = supervisor.run(max_missions=1)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completed"], 1)
        self.assertEqual(len(self.calls), 1)
        call = self.calls[0]
        self.assertIsInstance(call["control"], RunControl)
        mission = get_mission(call["mission_id"])
        self.assertEqual(mission["status"], "completed")
        self.assertEqual(mission["requirement_id"], "R-2")
        self.assertEqual(mission["supervisor_run_id"], result["run_id"])
        queue = store.list_queue(self.project_id)
        self.assertEqual([(item["requirement_id"], item["state"]) for item in queue],
                         [("R-2", "VERIFIED")])
        self.assertEqual(queue[0]["attempts"], 1)
        self.assertEqual(store.get_backlog_item("R-2")["supervisor_status"], "VERIFIED")
        self.assertEqual(store.get_backlog_item("R-2")["last_mission_id"],
                         call["mission_id"])
        kinds = {row["kind"] for row in store.list_evidence(call["mission_id"])}
        self.assertTrue({"diff", "verification", "review", "promotion"} <= kinds)
        run = store.get_run(result["run_id"])
        self.assertEqual(run["status"], "COMPLETED")
        self.assertEqual(run["missions_completed"], 1)
        self.assertIsNone(store.get_lease(self.project_id))
        self.assertIn("supervisor run", result["resume_command"])

    def test_max_missions_limit_stops_after_two_verified_missions(self):
        supervisor = self.supervisor(
            config=self.config(max_missions_per_run=2),
            scripts=[self.completed_script(), self.completed_script()],
        )
        result = supervisor.run(max_missions=2)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completed"], 2)
        self.assertEqual(len(self.calls), 2)
        states = sorted((item["requirement_id"], item["state"])
                        for item in store.list_queue(self.project_id))
        self.assertEqual(states, [("R-2", "VERIFIED"), ("R-3", "VERIFIED")])

    def test_stop_command_before_first_mission_stops_without_running(self):
        supervisor = self.supervisor()
        supervisor.request_stop(requested_by="tester", reason="emergency")
        result = supervisor.run()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(self.calls, [])
        self.assertIsNone(store.get_lease(self.project_id))
        run = store.get_run(result["run_id"])
        self.assertEqual(run["status"], "STOPPED")
        self.assertIn("emergency", run["stopped_reason"])

    def test_stop_mid_mission_via_control_checkpoint_interrupts_safely(self):
        def interrupted_script(kwargs):
            mission_id = kwargs["mission_id"]
            update_mission_status(mission_id, "interrupted")
            raise RunStopped("after-developer", "operator stop")

        supervisor = self.supervisor(scripts=[interrupted_script])
        result = supervisor.run()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)
        queue = store.list_queue(self.project_id)
        self.assertEqual(queue[0]["state"], "INTERRUPTED")
        self.assertEqual(store.get_backlog_item("R-2")["supervisor_status"], "IN_FLIGHT")
        self.assertIsNone(store.get_lease(self.project_id))

    def test_pause_at_mission_boundary_keeps_completed_mission(self):
        holder: dict = {}

        def pausing_script(kwargs):
            holder["supervisor"].request_pause(requested_by="tester")
            return self.completed_script()(kwargs)

        supervisor = self.supervisor(scripts=[pausing_script])
        holder["supervisor"] = supervisor
        result = supervisor.run()
        self.assertEqual(result["status"], "paused")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(store.list_queue(self.project_id)[0]["state"], "VERIFIED")
        run = store.get_run(result["run_id"])
        self.assertEqual(run["status"], "STOPPED")
        self.assertIn("Pause", run["stopped_reason"])
        self.assertIsNone(store.get_lease(self.project_id))

    def test_repairable_failure_retries_same_mission_then_verifies(self):
        supervisor = self.supervisor(
            config=self.config(max_attempts_per_requirement=2,
                               max_consecutive_failures=2),
            scripts=[self.blocked_script(), self.completed_script()],
        )
        result = supervisor.run()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completed"], 1)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0]["mission_id"], self.calls[1]["mission_id"])
        queue = store.list_queue(self.project_id)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["state"], "VERIFIED")
        self.assertEqual(queue[0]["attempts"], 2)
        kinds = {row["kind"] for row in store.list_evidence(self.calls[1]["mission_id"])}
        self.assertIn("failure", kinds)

    def test_attempt_budget_exhaustion_dead_letters_and_stops(self):
        supervisor = self.supervisor(scripts=[self.blocked_script()])
        result = supervisor.run()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(self.calls), 1)
        queue = store.list_queue(self.project_id)
        self.assertEqual(queue[0]["state"], "BLOCKED")
        self.assertEqual(queue[0]["failure_class"], "BUDGET_EXHAUSTED")
        self.assertEqual(store.get_backlog_item("R-2")["supervisor_status"], "BLOCKED")
        self.assertEqual(store.get_run(result["run_id"])["status"], "BLOCKED")
        self.assertIsNone(store.get_lease(self.project_id))

    def test_second_supervisor_on_live_lease_is_refused(self):
        held = store.acquire_lease(
            self.project_id, owner_id="other-supervisor", owner_pid=os.getpid(),
            owner_host="host", ttl_s=60,
        )
        self.assertIsNotNone(held)
        try:
            result = self.supervisor().run()
            self.assertEqual(result["status"], "already-running")
            self.assertIn("other-supervisor", result["error"])
            self.assertEqual(self.calls, [])
            self.assertEqual(store.get_lease(self.project_id)["owner_id"],
                             "other-supervisor")
        finally:
            store.release_lease(self.project_id, owner_id="other-supervisor")

    def test_heartbeat_renews_and_detects_lost_lease(self):
        supervisor = self.supervisor()
        lease = supervisor.acquire()
        renewed = supervisor.heartbeat()
        self.assertIsNotNone(renewed)
        assert renewed is not None
        self.assertGreater(renewed.version, lease.version)
        store.release_lease(self.project_id, owner_id=supervisor.owner_id)
        stolen = store.acquire_lease(
            self.project_id, owner_id="other", owner_pid=os.getpid(),
            owner_host="host", ttl_s=60,
        )
        self.assertIsNotNone(stolen)
        try:
            self.assertIsNone(supervisor.heartbeat())
            self.assertTrue(supervisor._lease_lost)
            self.assertTrue(supervisor.control.stop_requested)
        finally:
            store.release_lease(self.project_id, owner_id="other")
            supervisor.lease = None


# --------------------------------------------------------------------------- #
# Reconcile
# --------------------------------------------------------------------------- #

class ReconcileTests(SupervisorTestCase):
    def reconcile_supervisor(self) -> Supervisor:
        supervisor = self.supervisor()
        supervisor.run_id = 77
        return supervisor

    def test_claimed_without_mission_returns_to_ready(self):
        queue_id = self.queue_item("R-2", state="READY")
        store.claim_queue_item(queue_id, claim_token="t", owner_id="crashed")
        supervisor = self.reconcile_supervisor()
        actions = supervisor.reconcile()
        self.assertEqual(store.get_queue_item(queue_id)["state"], "READY")
        self.assertTrue(any("READY" in action for action in actions))

    def test_running_mission_completed_becomes_verified(self):
        queue_id = self.queue_item("R-2", state="RUNNING")
        mission_id = self.attach_mission(queue_id)
        update_mission_result(mission_id, "completed", result_summary="done",
                              review_verdict="APPROVE", diff_stat="1", changed_paths=[])
        self.reconcile_supervisor().reconcile()
        self.assertEqual(store.get_queue_item(queue_id)["state"], "VERIFIED")
        self.assertEqual(store.get_backlog_item("R-2")["supervisor_status"], "VERIFIED")

    def test_running_interrupted_mission_becomes_interrupted(self):
        queue_id = self.queue_item("R-2", state="RUNNING")
        mission_id = self.attach_mission(queue_id)
        update_mission_status(mission_id, "interrupted")
        self.reconcile_supervisor().reconcile()
        self.assertEqual(store.get_queue_item(queue_id)["state"], "INTERRUPTED")

    def test_running_blocked_mission_retries_or_dead_letters_by_attempts(self):
        queue_id = self.queue_item("R-2", state="RUNNING", attempts=1, max_attempts=2)
        mission_id = self.attach_mission(queue_id)
        update_mission_result(mission_id, "blocked",
                              result_summary="Verification failed after retries",
                              review_verdict="REJECT", diff_stat="", changed_paths=[])
        supervisor = self.reconcile_supervisor()
        supervisor.reconcile()
        self.assertEqual(store.get_queue_item(queue_id)["state"], "NEEDS_FIX")
        self.assertEqual(store.get_backlog_item("R-2")["supervisor_status"], "NEEDS_FIX")

        queue_id2 = self.queue_item("R-3", state="RUNNING", attempts=1, max_attempts=1)
        mission_id2 = self.attach_mission(queue_id2, requirement_id="R-3")
        update_mission_result(mission_id2, "blocked",
                              result_summary="Verification failed after retries",
                              review_verdict="REJECT", diff_stat="", changed_paths=[])
        supervisor.reconcile()
        self.assertEqual(store.get_queue_item(queue_id2)["state"], "BLOCKED")

    def test_crashed_active_run_is_marked_stopped(self):
        crashed = store.start_run(self.project_id, mode="automatic", config={},
                                  owner_id="old-owner", owner_pid=1)
        actions = self.reconcile_supervisor().reconcile()
        self.assertEqual(store.get_run(crashed)["status"], "STOPPED")
        self.assertTrue(any("crashed run" in action for action in actions))


# --------------------------------------------------------------------------- #
# Orchestrator control hook (real orchestrator, fake model seam)
# --------------------------------------------------------------------------- #

class OrchestratorControlTests(SupervisorTestCase):
    def test_run_stopped_at_checkpoint_finalizes_interrupted_without_live_write(self):
        (self.root / "nl_coding_agent").mkdir()
        (self.root / "nl_coding_agent" / "__init__.py").write_text(
            "", encoding="utf-8", newline="")
        calc = self.root / "src" / "calc.py"
        calc.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8", newline="")
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_calc.py").write_text(
            "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            encoding="utf-8", newline="",
        )
        mission_id = create_mission(
            self.project_id, "[R-2] control test",
            "Add a subtract function to src/calc.py", requirement_id="R-2",
        )
        orch = MultiAgentOrchestrator(self.root, project_id=self.project_id)
        orch._call_model = lambda role, model, prompt, **kw: (
            "```write:src/calc.py\n"
            "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n```"
        )
        seen: list[str] = []
        control = RunControl()

        def hook(stage: str) -> None:
            seen.append(stage)
            if stage == "after-developer":
                control.request_stop("test stop")

        control._checkpoint_hook = hook
        result = orch.run_mission(mission_id=mission_id, goal=None, control=control)
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(calc.read_text(encoding="utf-8"),
                         "def add(a, b):\n    return a + b\n")
        self.assertEqual(get_mission(mission_id)["status"], "interrupted")
        self.assertIn("after-developer", seen)
        self.assertFalse(any("promotion" in stage for stage in seen))
        self.assertEqual(get_mission(mission_id)["promotion_status"], "validated")


# --------------------------------------------------------------------------- #
# Status / commands
# --------------------------------------------------------------------------- #

class StatusAndCommandTests(SupervisorTestCase):
    def test_status_and_resume_command(self):
        status = supervisor_status(self.root, project_id=self.project_id)
        self.assertEqual(status["status"], "idle")
        self.assertIn("supervisor run", status["resume_command"])
        self.assertIn("program_stage", status)

    def test_stop_pause_resume_commands_persist(self):
        stopped = supervisor_command(self.root, "stop", requested_by="tester")
        self.assertTrue(stopped["ok"])
        pending = store.take_pending_commands(self.project_id)
        self.assertEqual([item["command"] for item in pending], ["stop"])
        self.assertTrue(supervisor_command(self.root, "pause", requested_by="tester")["ok"])
        self.assertTrue(supervisor_command(self.root, "resume", requested_by="tester")["ok"])
        with self.assertRaises(SupervisorError):
            supervisor_command(self.root, "explode")
        command = resume_command(self.root, mode="automatic", max_missions=2)
        self.assertEqual(command.count("--max-missions"), 1)
        self.assertIn("--mode automatic", command)


if __name__ == "__main__":
    unittest.main()

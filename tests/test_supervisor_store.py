"""C3a: durable supervisor store - leases, queue, runs, backlog mirror, evidence, approvals."""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent.persistence import database
from nl_coding_agent.persistence import supervisor_store as store
from nl_coding_agent.persistence.missions import create_mission


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self._env = patch.dict(os.environ, {"NL_DATA_DIR": str(self.data)})
        self._env.start()
        self.addCleanup(self._env.stop)
        database.init_db().close()
        conn = database.get_connection()
        try:
            with conn:
                conn.execute("INSERT INTO projects (name, root) VALUES ('project', 'X:/project')")
            self.project_id = int(conn.execute("SELECT id FROM projects").fetchone()["id"])
        finally:
            conn.close()
        self.host = store._hostname()

    # ---------------------------------------------------------------- helpers

    def mission(self) -> int:
        return create_mission(None, "mission", "goal")

    def acquire(self, owner: str = "owner-a", *, pid: int | None = None,
                host: str | None = None, ttl_s: float = 60):
        return store.acquire_lease(
            self.project_id,
            owner_id=owner,
            owner_pid=os.getpid() if pid is None else pid,
            owner_host=self.host if host is None else host,
            ttl_s=ttl_s,
        )

    def backlog_items(self, **overrides) -> list[dict]:
        first = {
            "requirement_id": "R-1", "title": "One", "area": "autonomy",
            "priority": "P0", "program_stage": 2, "program_stage_name": "Two",
            "status": "planned", "dependencies": [], "acceptance": ["works"],
            "source_refs": ["spec-1"], "content_hash": "hash-1",
        }
        second = {
            "requirement_id": "R-2", "title": "Two", "area": "autonomy",
            "priority": "P1", "program_stage": 2, "program_stage_name": "Two",
            "status": "partial", "dependencies": ["R-1"], "acceptance": [],
            "source_refs": [], "content_hash": "hash-2",
        }
        first.update(overrides.get("first", {}))
        second.update(overrides.get("second", {}))
        return [first, second]


class LeaseTests(StoreTestCase):
    def test_acquire_renew_conflict_and_release(self):
        lease = self.acquire()
        self.assertEqual(lease.owner_id, "owner-a")
        self.assertEqual(lease.version, 1)
        held = store.get_lease(self.project_id)
        self.assertEqual(held["owner_id"], "owner-a")
        self.assertEqual(held["expires_at"], lease.expires_at)

        with self.assertRaises(store.LeaseConflict) as ctx:
            self.acquire("owner-b")
        self.assertEqual(ctx.exception.owner_id, "owner-a")
        self.assertIn("held by", str(ctx.exception))

        self.assertIsNone(
            store.renew_lease(self.project_id, owner_id="owner-a", version=99, ttl_s=60)
        )
        renewed = store.renew_lease(
            self.project_id, owner_id="owner-a", version=lease.version, ttl_s=60
        )
        self.assertIsNotNone(renewed)
        assert renewed is not None
        self.assertEqual(renewed.version, lease.version + 1)

        store.release_lease(self.project_id, owner_id="owner-a")
        self.assertIsNone(store.get_lease(self.project_id))
        other = self.acquire("owner-b")
        self.assertEqual(other.version, 1)

    def test_renew_self_keeps_the_lease(self):
        lease = self.acquire()
        again = self.acquire()
        self.assertEqual(again.owner_id, "owner-a")
        self.assertEqual(again.version, lease.version + 1)

    def test_expired_dead_local_owner_can_be_stolen(self):
        self.acquire(pid=999_999, ttl_s=-5)
        with patch.object(store, "_pid_alive", return_value=False):
            stolen = self.acquire("owner-b")
        self.assertEqual(stolen.owner_id, "owner-b")
        self.assertEqual(stolen.version, 2)

    def test_expired_live_local_owner_is_not_stolen(self):
        self.acquire(pid=os.getpid(), ttl_s=-5)
        with self.assertRaises(store.LeaseConflict) as ctx:
            self.acquire("owner-b")
        self.assertIn("still alive", str(ctx.exception))
        self.assertEqual(store.get_lease(self.project_id)["owner_id"], "owner-a")

    def test_expired_lease_from_another_host_is_reclaimed(self):
        self.acquire(host="some-other-host", ttl_s=-5)
        reclaimed = self.acquire("owner-b", host=self.host)
        self.assertEqual(reclaimed.owner_id, "owner-b")
        self.assertEqual(reclaimed.version, 2)

    def test_concurrent_acquisition_has_a_single_winner(self):
        results: list[tuple[str, str]] = []
        lock = threading.Lock()

        def worker(owner: str) -> None:
            try:
                store.acquire_lease(
                    self.project_id, owner_id=owner, owner_pid=os.getpid(),
                    owner_host=self.host, ttl_s=60,
                )
            except store.LeaseConflict:
                outcome = "lost"
            except Exception as exc:  # pragma: no cover - surfaced by assertion
                outcome = "error:" + str(exc)
            else:
                outcome = "won"
            with lock:
                results.append((outcome, owner))

        threads = [threading.Thread(target=worker, args=("owner-" + str(index),))
                   for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        outcomes = sorted(item[0] for item in results)
        self.assertEqual(outcomes, ["lost", "won"])


class MachineLeaseTests(StoreTestCase):
    def test_machine_lease_single_owner_round_trip(self):
        first = store.acquire_machine_lease(
            "inference", owner_id="m1", owner_pid=os.getpid(),
            owner_host=self.host, ttl_s=60,
        )
        self.assertIsNotNone(first)
        assert first is not None
        self.assertIsNone(store.acquire_machine_lease(
            "inference", owner_id="m2", owner_pid=os.getpid(),
            owner_host=self.host, ttl_s=60,
        ))
        self.assertFalse(store.renew_machine_lease(
            "inference", owner_id="m1", version=999, ttl_s=60
        ))
        self.assertTrue(store.renew_machine_lease(
            "inference", owner_id="m1", version=first.version, ttl_s=60
        ))
        store.release_machine_lease("inference", owner_id="m1")
        self.assertIsNone(store.get_machine_lease("inference"))
        second = store.acquire_machine_lease(
            "inference", owner_id="m2", owner_pid=os.getpid(),
            owner_host=self.host, ttl_s=60,
        )
        self.assertIsNotNone(second)


class RunAndCommandTests(StoreTestCase):
    def test_run_lifecycle_flags_and_active_lookup(self):
        run_id = store.start_run(
            self.project_id, mode="automatic", config={"max_missions": 2},
            owner_id="owner-a", owner_pid=os.getpid(),
        )
        run = store.get_run(run_id)
        self.assertEqual(run["status"], "STARTING")
        self.assertEqual(run["config"], {"max_missions": 2})
        self.assertEqual(store.get_active_run(self.project_id)["id"], run_id)

        self.assertTrue(store.set_run_flags(run_id, pause=True, stop=False))
        run = store.get_run(run_id)
        self.assertEqual(run["pause_requested"], 1)
        self.assertEqual(run["stop_requested"], 0)

        self.assertTrue(store.update_run(run_id, status="RUNNING", missions_completed=2))
        run = store.get_run(run_id)
        self.assertEqual(run["status"], "RUNNING")
        self.assertEqual(run["missions_completed"], 2)

        store.finish_run(run_id, status="COMPLETED", reason="done")
        run = store.get_run(run_id)
        self.assertEqual(run["status"], "COMPLETED")
        self.assertEqual(run["stopped_reason"], "done")
        self.assertIsNotNone(run["finished_at"])
        self.assertIsNone(store.get_active_run(self.project_id))

    def test_run_validation(self):
        with self.assertRaises(store.StoreError):
            store.start_run(self.project_id, mode="yolo", config={},
                            owner_id="o", owner_pid=1)
        run_id = store.start_run(self.project_id, mode="off", config={},
                                 owner_id="o", owner_pid=1)
        with self.assertRaises(store.StoreError):
            store.update_run(run_id, status="NOT_A_STATE")
        with self.assertRaises(store.StoreError):
            store.update_run(run_id, unknown_column=1)
        with self.assertRaises(store.StoreError):
            store.finish_run(run_id, status="RUNNING")
        self.assertFalse(store.update_run(999, status="RUNNING"))

    def test_commands_are_consumed_once(self):
        first = store.request_command(self.project_id, "stop", requested_by="human")
        second = store.request_command(self.project_id, "pause", requested_by="human")
        pending = store.take_pending_commands(self.project_id)
        self.assertEqual([item["command"] for item in pending], ["stop", "pause"])
        self.assertEqual(store.take_pending_commands(self.project_id), [])
        self.assertIn(first, [item["id"] for item in pending])
        self.assertIn(second, [item["id"] for item in pending])

        run_id = store.start_run(self.project_id, mode="automatic", config={},
                                 owner_id="o", owner_pid=1)
        targeted = store.request_command(self.project_id, "kick", requested_by="human",
                                         run_id=run_id)
        other = store.request_command(self.project_id, "resume", requested_by="human",
                                      run_id=run_id + 1)
        taken = store.take_pending_commands(self.project_id, run_id)
        ids = [item["id"] for item in taken]
        self.assertIn(targeted, ids)
        self.assertNotIn(other, ids)
        with self.assertRaises(store.StoreError):
            store.request_command(self.project_id, "explode", requested_by="human")


class QueueTests(StoreTestCase):
    def enqueue(self, key: str = "key-1", **overrides) -> int:
        options = {
            "requirement_id": "R-1", "goal": "Do the work", "priority": "P0",
            "idempotency_key": key, "max_attempts": 2,
            "budget": {"wall_time_s": 60}, "payload": {"source": "test"},
        }
        options.update(overrides)
        return store.enqueue_mission(self.project_id, **options)

    def test_idempotency_claim_and_full_transition(self):
        queue_id = self.enqueue()
        self.assertEqual(self.enqueue(), queue_id)
        item = store.get_queue_item(queue_id)
        self.assertEqual(item["state"], "READY")
        self.assertEqual(item["budget"], {"wall_time_s": 60})
        self.assertEqual(item["payload"], {"source": "test"})
        self.assertEqual(store.find_queue_item(self.project_id, "key-1")["id"], queue_id)

        self.assertTrue(store.claim_queue_item(
            queue_id, claim_token="token-1", owner_id="owner-a"
        ))
        self.assertFalse(store.claim_queue_item(
            queue_id, claim_token="token-2", owner_id="owner-a"
        ))
        self.assertTrue(store.update_queue_item(
            queue_id, claim_token="token-1", state="RUNNING", increment_attempts=True
        ))
        item = store.get_queue_item(queue_id)
        self.assertEqual(item["state"], "RUNNING")
        self.assertEqual(item["attempts"], 1)
        for state in ("VERIFYING", "REVIEWING", "VERIFIED"):
            self.assertTrue(store.update_queue_item(
                queue_id, claim_token="token-1", state=state
            ))
        item = store.get_queue_item(queue_id)
        self.assertEqual(item["state"], "VERIFIED")
        self.assertIsNotNone(item["finished_at"])
        self.assertEqual(self.enqueue(), queue_id)
        self.assertEqual(store.get_queue_item(queue_id)["state"], "VERIFIED")

    def test_invalid_transitions_and_token_mismatch(self):
        queue_id = self.enqueue()
        store.claim_queue_item(queue_id, claim_token="token-1", owner_id="owner-a")
        store.update_queue_item(queue_id, claim_token="token-1", state="RUNNING")
        with self.assertRaises(store.StoreError):
            store.update_queue_item(queue_id, claim_token="token-1", state="READY")
        self.assertFalse(store.update_queue_item(
            queue_id, claim_token="wrong-token", state="INTERRUPTED"
        ))
        with self.assertRaises(store.StoreError):
            store.update_queue_item(queue_id, claim_token="token-1", state="NOT_A_STATE")
        self.assertFalse(store.update_queue_item(9999, state="READY"))

    def test_queue_validation_and_listing(self):
        first = self.enqueue("key-1")
        second = self.enqueue("key-2", requirement_id="R-2", priority="P1")
        with self.assertRaises(store.StoreError):
            self.enqueue("key-3", priority="P9")
        with self.assertRaises(store.StoreError):
            self.enqueue("key-4", state="WHATEVER")
        ready = store.list_queue(self.project_id, states=("READY",))
        self.assertEqual([item["id"] for item in ready], [first, second])
        store.claim_queue_item(first, claim_token="t", owner_id="o")
        claimed = store.list_queue(self.project_id, states=("CLAIMED",))
        self.assertEqual([item["id"] for item in claimed], [first])
        self.assertEqual(store.list_queue(self.project_id, limit=0), [])


class BacklogMirrorTests(StoreTestCase):
    def test_sync_preserves_progress_and_marks_missing_skipped(self):
        report = store.sync_backlog(self.backlog_items(), source_fingerprint="fp-1")
        self.assertEqual(report["inserted"], ["R-1", "R-2"])
        self.assertTrue(store.set_backlog_progress(
            "R-1", supervisor_status="VERIFIED", mission_id=5, note="ok"
        ))
        changed = self.backlog_items(first={"title": "One v2", "content_hash": "hash-1b"})
        report = store.sync_backlog(changed, source_fingerprint="fp-2")
        self.assertEqual(report["updated"], ["R-1"])
        self.assertEqual(report["unchanged"], ["R-2"])
        item = store.get_backlog_item("R-1")
        self.assertEqual(item["title"], "One v2")
        self.assertEqual(item["supervisor_status"], "VERIFIED")
        self.assertEqual(item["last_mission_id"], 5)
        self.assertEqual(item["note"], "ok")

        report = store.sync_backlog([changed[0]], source_fingerprint="fp-3")
        self.assertIn("R-2", report["skipped"])
        self.assertEqual(store.get_backlog_item("R-2")["supervisor_status"], "SKIPPED")
        staged = store.list_backlog(program_stage=2)
        self.assertEqual([row["requirement_id"] for row in staged], ["R-1", "R-2"])

    def test_progress_validation_and_missing_item(self):
        store.sync_backlog(self.backlog_items(), source_fingerprint="fp")
        self.assertFalse(store.set_backlog_progress("R-404", supervisor_status="READY"))
        with self.assertRaises(store.StoreError):
            store.set_backlog_progress("R-1", supervisor_status="DONE")
        with self.assertRaises(store.StoreError):
            store.sync_backlog([{"requirement_id": "R-9"}], source_fingerprint="fp")


class EvidenceAndApprovalTests(StoreTestCase):
    def test_evidence_is_idempotent_per_record_key(self):
        mission_id = self.mission()
        first = store.record_evidence(
            mission_id, kind="verification", record_key="candidate+oracle",
            payload={"passed": True}, queue_id=3,
        )
        second = store.record_evidence(
            mission_id, kind="verification", record_key="candidate+oracle",
            payload={"passed": False},
        )
        self.assertEqual(first, second)
        rows = store.list_evidence(mission_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payload"], {"passed": True})
        self.assertEqual(rows[0]["queue_id"], 3)
        other = store.record_evidence(
            mission_id, kind="promotion", record_key="promoted", payload={},
        )
        self.assertNotEqual(other, first)
        self.assertEqual(len(store.list_evidence(mission_id)), 2)
        with self.assertRaises(store.StoreError):
            store.record_evidence(mission_id, kind="", record_key="x", payload={})

    def test_approvals_round_trip_expiry_and_validation(self):
        approval_id = store.create_approval(
            self.project_id, action="cloud",
            scope={"model": "ollama/gpt-oss:120b-cloud"}, reason="need quota",
            requested_by="human",
        )
        pending = store.pending_approvals(self.project_id)
        self.assertEqual([row["id"] for row in pending], [approval_id])
        self.assertEqual(pending[0]["requested_by"], "human")
        self.assertFalse(store.decide_approval(9999, approved=True, decided_by="human"))
        self.assertTrue(store.decide_approval(
            approval_id, approved=True, decided_by="human", reason="approved"
        ))
        self.assertFalse(store.decide_approval(
            approval_id, approved=False, decided_by="human"
        ))
        row = store.get_approval(approval_id)
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["decided_by"], "human")
        self.assertEqual(row["decision_reason"], "approved")
        self.assertEqual(store.pending_approvals(self.project_id), [])
        self.assertEqual(len(store.list_approvals(self.project_id, status="approved")), 1)

        expired_at = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
        expired_id = store.create_approval(
            self.project_id, action="delete", scope={"path": "x"}, reason="cleanup",
            expires_at=expired_at,
        )
        self.assertEqual(store.pending_approvals(self.project_id), [])
        self.assertEqual(store.get_approval(expired_id)["status"], "expired")
        with self.assertRaises(store.StoreError):
            store.create_approval(self.project_id, action="shutdown", scope={}, reason="")
        with self.assertRaises(store.StoreError):
            store.list_approvals(self.project_id, status="whatever")


if __name__ == "__main__":
    unittest.main()

"""C3: promotion.py - stage lifecycle, policy, recovery point, CAS promotion, journal reconcile."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nl_coding_agent.core import promotion as P
from nl_coding_agent.core.promotion import GateFailure


class PromotionTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "project"
        (self.root / "src").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / "src" / "app.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8", newline=""
        )
        (self.root / "tests" / "test_app.py").write_text(
            "from src.app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            encoding="utf-8",
            newline="",
        )

    def stage(self, mission_id: int = 42, scope: list[str] | None = None) -> P.Stage:
        return P.begin_stage(self.root, mission_id, scope or ["src/app.py"])

    def write_staged(self, stage: P.Stage, rel: str, text: str) -> None:
        target = stage.workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")

    def mark_ok(self, stage: P.Stage) -> dict:
        verdict = P.validate(stage)
        self.assertTrue(verdict["valid"], verdict)
        P.mark_verified(stage, passed=True, evidence='{"candidate": "pass", "oracle": "pass"}')
        return verdict


class LifecycleTests(PromotionTestBase):
    def test_begin_stage_requires_scope(self):
        with self.assertRaises(GateFailure) as ctx:
            P.begin_stage(self.root, 7, [])
        self.assertEqual(ctx.exception.code, "scope")

    def test_derive_scope_falls_back_to_top_level_entries(self):
        scope = P.derive_scope(self.root, [])
        self.assertIn("src", scope)
        self.assertIn("tests", scope)

    def test_happy_path_promotes_and_is_idempotent(self):
        stage = self.stage()
        self.write_staged(stage, "src/app.py", "def add(a, b):\n    return a + b + 1\n")
        with self.assertRaises(GateFailure) as ctx:
            P.promote(stage)
        self.assertEqual(ctx.exception.code, "not-verified")
        verdict = self.mark_ok(stage)
        self.assertTrue(verdict["valid"])
        self.assertNotEqual(
            (self.root / "src" / "app.py").read_text(encoding="utf-8"),
            "def add(a, b):\n    return a + b + 1\n",
        )
        result = P.promote(stage)
        self.assertEqual(result["promoted"], ["src/app.py"])
        self.assertFalse(result["blocked"])
        self.assertTrue((self.root / "src" / "app.py").read_text(encoding="utf-8").endswith("+ 1\n"))
        self.assertTrue(P.is_live_promoted(stage))
        self.assertTrue((self.root / "data" / "recovery" / "42.json").is_file())
        again = P.promote(stage)
        self.assertTrue(again["already"])

    def test_stub_candidate_is_rejected(self):
        stage = self.stage()
        self.write_staged(stage, "src/app.py", "def add(a, b):\n    pass\n")
        verdict = P.validate(stage)
        self.assertFalse(verdict["valid"])
        self.assertTrue(verdict["errors"])
        with self.assertRaises(GateFailure) as ctx:
            P.promote(stage)
        self.assertEqual(ctx.exception.code, "not-verified")
        self.assertIn("return a + b", (self.root / "src" / "app.py").read_text(encoding="utf-8"))

    def test_out_of_scope_change_is_rejected(self):
        stage = self.stage(scope=["src/app.py"])
        self.write_staged(stage, "src/app.py", "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n")
        self.write_staged(stage, "docs/readme.md", "# changed\n")
        verdict = P.validate(stage)
        self.assertFalse(verdict["valid"])
        self.assertTrue(any("Out-of-scope" in e for e in verdict["errors"]))
        self.assertFalse((self.root / "docs" / "readme.md").exists())

    def test_protected_path_change_is_rejected(self):
        stage = self.stage(scope=["src/app.py"])
        manifest = P.read_manifest(stage)
        manifest["changed"] = {"python/evil.py": {"before": None, "after": "x"}}
        P._save_manifest(stage, manifest)
        errors = P.check_delta_policy(stage)
        self.assertTrue(any("Protected path" in e for e in errors))


class NewlineTests(PromotionTestBase):
    def test_crlf_is_normalized_and_promoted_as_lf(self):
        stage = self.stage()
        staged = stage.workspace / "src" / "app.py"
        staged.write_bytes(b"def add(a, b):\r\n    return a + b + 2\r\n")
        normalized = P.normalize_staged_newlines(stage)
        self.assertIn("src/app.py", normalized)
        self.assertNotIn(b"\r\n", staged.read_bytes())
        verdict = P.validate(stage)
        self.assertTrue(verdict["valid"], verdict)
        P.assert_byte_hash_invariant(stage)
        P.mark_verified(stage, passed=True, evidence="candidate pass; oracle pass")
        P.promote(stage)
        live_bytes = (self.root / "src" / "app.py").read_bytes()
        self.assertNotIn(b"\r\n", live_bytes)
        self.assertTrue(live_bytes.endswith(b"+ 2\n"))

    def test_byte_hash_invariant_is_enforced_before_promotion(self):
        stage = self.stage()
        self.write_staged(stage, "src/app.py", "def add(a, b):\n    return a + b + 3\n")
        self.mark_ok(stage)
        # Corrupt the staged bytes without updating the manifest hashes.
        (stage.workspace / "src" / "app.py").write_bytes(b"def add(a, b):\r\n    return a + b + 3\r\n")
        with self.assertRaises(GateFailure) as ctx:
            P.assert_byte_hash_invariant(stage)
        self.assertEqual(ctx.exception.code, "byte-invariant")
        with self.assertRaises(GateFailure):
            P.promote(stage)


class CasTests(PromotionTestBase):
    def test_external_live_edit_blocks_promotion(self):
        stage = self.stage()
        self.write_staged(stage, "src/app.py", "def add(a, b):\n    return a + b + 4\n")
        self.mark_ok(stage)
        (self.root / "src" / "app.py").write_text(
            "def add(a, b):\n    return 'human'\n", encoding="utf-8", newline=""
        )
        with self.assertRaises(GateFailure) as ctx:
            P.promote(stage)
        self.assertEqual(ctx.exception.code, "cas-conflict")
        self.assertIn("human", (self.root / "src" / "app.py").read_text(encoding="utf-8"))

    def test_journal_all_after_is_recognized_as_complete(self):
        stage = self.stage()
        self.write_staged(stage, "src/app.py", "def add(a, b):\n    return a + b + 5\n")
        self.mark_ok(stage)
        P.promote(stage)
        manifest = P.read_manifest(stage)
        (stage.stage_dir / P.PROMOTION_JOURNAL).write_text(
            json.dumps({"project_root": str(self.root), "changed": manifest["changed"]}),
            encoding="utf-8",
        )
        outcome = P.reconcile(stage)
        self.assertEqual(outcome["state"], "promotion-complete")
        self.assertFalse((stage.stage_dir / P.PROMOTION_JOURNAL).exists())

    def test_mixed_journal_is_rolled_back_with_cas(self):
        stage = self.stage(scope=["src/app.py", "tests/test_app.py"])
        self.write_staged(stage, "src/app.py", "def add(a, b):\n    return a + b + 6\n")
        self.write_staged(
            stage,
            "tests/test_app.py",
            "from src.app import add\n\n\ndef test_add():\n    assert add(1, 2) == 9\n",
        )
        self.mark_ok(stage)
        P.ensure_recovery_point(stage)
        manifest = P.read_manifest(stage)
        journal = stage.stage_dir / P.PROMOTION_JOURNAL
        journal.write_text(
            json.dumps({"project_root": str(self.root), "changed": manifest["changed"]}),
            encoding="utf-8",
        )
        # Simulate a crash after one of two files was promoted.
        (self.root / "src" / "app.py").write_bytes(
            (stage.workspace / "src" / "app.py").read_bytes()
        )
        outcome = P.reconcile(stage)
        self.assertEqual(outcome["state"], "rolled-back", outcome)
        self.assertIn("return a + b\n", (self.root / "src" / "app.py").read_text(encoding="utf-8"))
        self.assertFalse(journal.exists())

    def test_preflight_reports_unreconciled_journal(self):
        stage = self.stage()
        journal = stage.stage_dir / P.PROMOTION_JOURNAL
        journal.write_text(json.dumps({"changed": {}}), encoding="utf-8")
        messages = P.preflight(self.root, mission_lookup=lambda staged: {"status": "blocked"})
        self.assertTrue(messages)
        self.assertIn("terminal", messages[0])


class EvidenceTests(PromotionTestBase):
    def test_cleanup_retains_evidence_and_discards_stage(self):
        stage = self.stage()
        self.write_staged(stage, "src/app.py", "def add(a, b):\n    return a + b + 7\n")
        self.mark_ok(stage)
        P.promote(stage)
        evidence_dir = Path(self._tmp.name) / "evidence"
        P.cleanup_after_terminal(stage, mission_status="completed", evidence_dir=evidence_dir)
        self.assertTrue((evidence_dir / "mission-42.json").is_file())
        self.assertFalse(stage.stage_dir.exists())
        payload = json.loads((evidence_dir / "mission-42.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["harness_version"], 2)

    def test_discard_refuses_when_journal_present(self):
        stage = self.stage()
        (stage.stage_dir / P.PROMOTION_JOURNAL).write_text("{}", encoding="utf-8")
        with self.assertRaises(GateFailure):
            P.discard_stage(stage)


if __name__ == "__main__":
    unittest.main()

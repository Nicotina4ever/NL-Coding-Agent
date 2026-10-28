"""Independent destructive-edit simulations; NEVER modify actual repository files."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nl_coding_agent.core.staging_broker import (
    StagingRejected, stage_candidate, validate_candidate, mark_verified,
    promote_staged, rollback_from_staged,
)


class TestStagingBroker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.planner = self.root / 'nl_coding_agent/core/planner.py'
        self.planner.parent.mkdir(parents=True)
        self.original = 'def select_next_task():\n    return [1, 2, 3]\n'
        self.planner.write_text(self.original, encoding='utf-8')
        self.test = self.root / 'tests/test_planner.py'
        self.test.parent.mkdir()
        self.test.write_text('def test_planner():\n    assert [1, 2, 3] == [1, 2, 3]\n', encoding='utf-8')
        self.scope = ['nl_coding_agent/core/planner.py', 'tests/test_planner.py']
        self.stage = stage_candidate(self.root, 42, self.scope)
        self.staged_planner = self.stage / 'workspace/nl_coding_agent/core/planner.py'

    def test_sh01_stub_never_touches_live_source(self):
        self.staged_planner.write_text('def select_next_task():\n    pass\n', encoding='utf-8')
        verdict = validate_candidate(self.stage)
        self.assertFalse(verdict['valid'])
        self.assertTrue(verdict['stub_files'])
        with self.assertRaises(StagingRejected):
            promote_staged(self.stage, self.root)
        self.assertEqual(self.planner.read_text(encoding='utf-8'), self.original)

    def test_sh04_weak_test_rejected(self):
        (self.stage / 'workspace/tests/test_planner.py').write_text(
            'def test_planner():\n    assert True\n', encoding='utf-8')
        verdict = validate_candidate(self.stage)
        self.assertFalse(verdict['valid'])
        self.assertTrue(verdict['weak_tests'])
        self.assertEqual(self.test.read_text(encoding='utf-8').count('assert'), 1)

    def test_unverified_candidate_cannot_promote(self):
        self.staged_planner.write_text('def select_next_task():\n    return [1, 2, 3, 4]\n', encoding='utf-8')
        self.assertTrue(validate_candidate(self.stage)['valid'])
        with self.assertRaises(StagingRejected):
            promote_staged(self.stage, self.root)
        mark_verified(self.stage, passed=True, evidence='independent pytest fixture: pass')
        self.assertEqual(promote_staged(self.stage, self.root)['blocked'], [])
        self.assertIn('4', self.planner.read_text(encoding='utf-8'))

    def test_sh02_human_edit_blocks_promotion(self):
        self.staged_planner.write_text('def select_next_task():\n    return [1, 2, 3, 4]\n', encoding='utf-8')
        self.assertTrue(validate_candidate(self.stage)['valid'])
        mark_verified(self.stage, passed=True, evidence='independent test result')
        self.planner.write_text('def select_next_task():\n    return "human"\n', encoding='utf-8')
        with self.assertRaises(StagingRejected):
            promote_staged(self.stage, self.root)
        self.assertIn('human', self.planner.read_text(encoding='utf-8'))

    def test_sh02_cas_rollback_preserves_newer_human_edit(self):
        self.staged_planner.write_text('def select_next_task():\n    return [1, 2, 3, 4]\n', encoding='utf-8')
        self.assertTrue(validate_candidate(self.stage)['valid'])
        mark_verified(self.stage, passed=True, evidence='independent test result')
        promote_staged(self.stage, self.root)
        self.planner.write_text('def select_next_task():\n    return "human"\n', encoding='utf-8')
        result = rollback_from_staged(self.stage, self.root)
        self.assertIn('nl_coding_agent/core/planner.py', result['blocked'])
        self.assertIn('human', self.planner.read_text(encoding='utf-8'))

    def test_sh03_recovery_from_promoted_candidate(self):
        self.staged_planner.write_text('def select_next_task():\n    return [1, 2, 3, 4]\n', encoding='utf-8')
        self.assertTrue(validate_candidate(self.stage)['valid'])
        mark_verified(self.stage, passed=True, evidence='independent test result')
        promote_staged(self.stage, self.root)
        self.assertIn('nl_coding_agent/core/planner.py', rollback_from_staged(self.stage, self.root)['restored'])
        self.assertEqual(self.planner.read_text(encoding='utf-8'), self.original)

    def test_changed_staged_file_after_validation_rejected(self):
        self.staged_planner.write_text('def select_next_task():\n    return [1, 2, 3, 4]\n', encoding='utf-8')
        self.assertTrue(validate_candidate(self.stage)['valid'])
        self.staged_planner.write_text('def select_next_task():\n    pass\n', encoding='utf-8')
        with self.assertRaises(StagingRejected):
            mark_verified(self.stage, passed=True, evidence='stale test')
        self.assertEqual(self.planner.read_text(encoding='utf-8'), self.original)


if __name__ == '__main__':
    unittest.main()

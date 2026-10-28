"""Recovery must preserve human changes and genuinely restore exact preimages."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nl_coding_agent.core.recovery_store import save_snapshot, rollback_from_snapshot, sha256_text


class TestRecoveryStore(unittest.TestCase):
    def test_restore_only_known_agent_postimage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'planner.py'
            p.write_text('def planner():\n    return 123\n', encoding='utf-8', newline='')
            recovery = save_snapshot(42, ['planner.py'], root=root)
            bad = 'def planner():\n    pass\n'
            p.write_text(bad, encoding='utf-8', newline='')
            result = rollback_from_snapshot(recovery, ['planner.py'], expected_post_hashes={'planner.py': sha256_text(bad)})
            self.assertFalse(result['blocked'])
            self.assertIn('return 123', p.read_text(encoding='utf-8'))

    def test_dirty_human_edit_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'planner.py'
            p.write_text('original', encoding='utf-8', newline='')
            recovery = save_snapshot(42, ['planner.py'], root=root)
            p.write_text('human edit', encoding='utf-8', newline='')
            result = rollback_from_snapshot(recovery, ['planner.py'], expected_post_hashes={'planner.py': sha256_text('agent stub')})
            self.assertIn('planner.py', result['blocked'])
            self.assertEqual(p.read_text(encoding='utf-8'), 'human edit')

    def test_without_postimage_no_speculative_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'planner.py'
            p.write_text('old', encoding='utf-8', newline='')
            recovery = save_snapshot(42, ['planner.py'], root=root)
            p.write_text('new', encoding='utf-8', newline='')
            self.assertIn('planner.py', rollback_from_snapshot(recovery, ['planner.py'])['blocked'])
            self.assertEqual(p.read_text(encoding='utf-8'), 'new')


if __name__ == '__main__':
    unittest.main()

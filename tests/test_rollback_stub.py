import unittest
from pathlib import Path
import sys
sys.path.insert(0, '.')
class TestRollbackStub(unittest.TestCase):
    def test_restore_planner_from_baseline_42(self):
        import json
        from nl_coding_agent.core.autonomous_roadmap_planner import select_next_task
        self.assertTrue(hasattr(select_next_task, '__call__'))
        baseline = json.loads(Path('data/mission_baselines/42.json').read_text(encoding='utf-8'))
        planner_content = baseline.get('nl_coding_agent/core/autonomous_roadmap_planner.py', '')
        self.assertIn('select_next_task', planner_content)
        self.assertNotIn('def consolidate_backlog', planner_content)
        current = Path('nl_coding_agent/core/autonomous_roadmap_planner.py').read_text(encoding='utf-8')
        self.assertIn('select_next_task', current)
        self.assertNotIn('def consolidate_backlog', current)
if __name__ == '__main__':
    unittest.main()

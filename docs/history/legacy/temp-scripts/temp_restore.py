import sys, json
sys.path.insert(0, '.')
from pathlib import Path
b = json.load(open('data/mission_baselines/42.json'))
# Planner from baseline (real)
Path('nl_coding_agent/core/autonomous_roadmap_planner.py').write_text(
    b['nl_coding_agent/core/autonomous_roadmap_planner.py'], encoding='utf-8')
# Restore docs from baseline
for k in ['docs/CURRENT_STATE.md', 'docs/COMPLETED_MISSIONS.md']:
    if k in b and b[k]:
        Path(k).write_text(b[k], encoding='utf-8')
# Restore backlog to real concise version
backlog_text = "\n".join([
    "# Product Backlog",
    "Consolidated from `docs/product-blueprint/03_MASTER_CHECKLIST.md`. No duplicates.",
    "## P0 - High Priority",
    "- P0-01 Audit repo / Git state (SPEC-02, SPEC-15)",
    "- P0-07 SQLite persistence (SPEC-18)",
    "- P0-09 Real self-build (SPEC-19)",
    "- P0-11 Docs state / resume (SPEC-02)",
    "- P0-13 Recovery points (SPEC-02A)",
    "## P1 - Medium Priority",
    "- P1-01 Open arbitrary folder / scanner (SPEC-12)",
    "- P1-02 Goal > milestone > task > mission (SPEC-03)",
    "- P1-04 Model Hub (SPEC-05)",
    "- P1-07 Stable Qt GUI (SPEC-08)",
    "## P2 - Low Priority",
    "- P2-01 Agent factory (SPEC-04)",
    "- P2-02 Adaptive inference + Optimize My Team (SPEC-06)",
    "- P2-05 Resource scheduler (SPEC-13)",
    "- P2-14 Recovery storage manager (SPEC-02A, SPEC-14)",
    "## Constraints",
    "- Local-model-first; Ollama primary; cloud opt-in.",
    "- No automatic migration/cleanup/sibling dirs/packaging until verified.",
    "- Preserve `python/`, `crewAI/`, `crewAI-tools/`, `.git`; use embedded `python\\python.exe`.",
])
Path('docs/PRODUCT_BACKLOG.md').write_text(backlog_text, encoding='utf-8')
# Rollback test (correct version)
rb_text = """import unittest
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
"""
Path('tests/test_rollback_stub.py').write_text(rb_text, encoding='utf-8')
print('restored planner, docs, rollback test; planner stub removed')

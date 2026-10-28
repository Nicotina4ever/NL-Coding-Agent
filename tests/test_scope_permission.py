import unittest
from pathlib import Path
import sys
sys.path.insert(0, '.')
from nl_coding_agent.core.workspace import out_of_scope_paths, path_in_scope

class TestScopePermission(unittest.TestCase):
    def test_protected_paths_denied(self):
        forbidden = ["python/python.exe", "crewAI/crewai.py", ".git/config"]
        for p in forbidden:
            self.assertTrue(p in out_of_scope_paths([p], ["nl_coding_agent/"]),
                            f"{p} should be denied")

    def test_authorized_paths_accepted(self):
        allowed = ["nl_coding_agent/core/roadmap.py", "tests/test_roadmap.py", "docs/NEXT_SELF_BUILD_MISSION.md"]
        for p in allowed:
            self.assertTrue(path_in_scope(p, ["nl_coding_agent/", "tests/", "docs/"]),
                            f"{p} should be allowed")

if __name__ == '__main__':
    unittest.main()

import unittest
from nl_coding_agent.core.status import get_system_status_summary

class TestSystemStatus(unittest.TestCase):
    def test_get_system_status_summary(self):
        status = get_system_status_summary()
        self.assertEqual(status['status'], 'operational')
        self.assertEqual(status['engine'], 'NL Coding Agent')
        self.assertEqual(status['version'], '0.2.0')

if __name__ == '__main__':
    unittest.main()

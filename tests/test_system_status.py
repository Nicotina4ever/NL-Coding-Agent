import unittest

from nl_coding_agent.core.status import (
    get_cpu_usage,
    get_disk_usage,
    get_memory_usage,
    get_network_status,
    get_system_status_summary,
    get_uptime_seconds,
)


class TestSystemStatus(unittest.TestCase):
    def test_system_status_summary(self):
        status = get_system_status_summary()
        self.assertIsInstance(status["uptime_check"], bool)
        self.assertTrue(status["uptime_check"])
        self.assertGreaterEqual(status["cpu_usage"], 0.0)
        self.assertLessEqual(status["cpu_usage"], 100.0)
        self.assertGreaterEqual(status["memory_usage"], 0.0)
        self.assertLessEqual(status["memory_usage"], 100.0)
        self.assertGreaterEqual(status["disk_usage"], 0.0)
        self.assertLessEqual(status["disk_usage"], 100.0)
        self.assertIn(status["network_status"], {"Connected", "Offline", "Unknown"})
        self.assertGreater(status["uptime_seconds"], 0)
        self.assertIn("timestamp", status)

    def test_individual_helpers_return_measured_values(self):
        self.assertGreaterEqual(get_cpu_usage(interval=0.01), 0.0)
        self.assertGreaterEqual(get_memory_usage(), 0.0)
        self.assertGreaterEqual(get_disk_usage(), 0.0)
        self.assertIn(get_network_status(), {"Connected", "Offline", "Unknown"})
        self.assertGreater(get_uptime_seconds(), 0)


if __name__ == "__main__":
    unittest.main()

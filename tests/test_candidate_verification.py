"""C4: candidate_verification - candidate + oracle disposable-copy regression gate."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from nl_coding_agent.core.candidate_verification import (
    cleanup_verification,
    parse_junit,
    prepare_copies,
    report_to_dict,
    scrubbed_env,
    verify_candidate,
)
from nl_coding_agent.core.workspace import snapshot_workspace

CALC_SOURCE = "def add(a, b):\n    return a + b\n"
CALC_BROKEN = "def add(a, b):\n    return 0\n"
TEST_SOURCE = "from demo.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
TEST_WEAK = "from demo.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 0\n"


class CandidateVerificationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.project = self.tmp / "project"
        (self.project / "nl_coding_agent").mkdir(parents=True)
        (self.project / "nl_coding_agent" / "__init__.py").write_text("", encoding="utf-8", newline="")
        (self.project / "demo").mkdir()
        (self.project / "demo" / "__init__.py").write_text("", encoding="utf-8", newline="")
        (self.project / "demo" / "calc.py").write_text(CALC_SOURCE, encoding="utf-8", newline="")
        (self.project / "tests").mkdir()
        (self.project / "tests" / "test_calc.py").write_text(TEST_SOURCE, encoding="utf-8", newline="")
        self.baseline = snapshot_workspace(self.project)
        self.stage = self.tmp / "stage"
        self.stage.mkdir()
        self.workspace = self.stage / "workspace"
        shutil.copytree(self.project, self.workspace)

    def verify(self) -> object:
        return verify_candidate(self.workspace, self.stage, self.baseline, timeout_s=180)

    def test_candidate_and_oracle_pass_on_unchanged_workspace(self):
        report = self.verify()
        self.assertTrue(report.passed, report.error)
        self.assertTrue(report.candidate.passed)
        self.assertTrue(report.oracle.passed)
        self.assertGreater(report.candidate.duration_s, 0)
        payload_file = report.verify_dir / "evidence" / "report.json"
        self.assertTrue(payload_file.is_file())
        payload = json.loads(payload_file.read_text(encoding="utf-8"))
        self.assertTrue(payload["passed"])
        self.assertEqual(report_to_dict(report)["passed"], True)

    def test_oracle_catches_green_but_weakened_candidate(self):
        # Candidate: buggy source + matching weakened test (green on its own).
        (self.workspace / "demo" / "calc.py").write_text(CALC_BROKEN, encoding="utf-8", newline="")
        (self.workspace / "tests" / "test_calc.py").write_text(TEST_WEAK, encoding="utf-8", newline="")
        report = self.verify()
        self.assertTrue(report.candidate.passed, "candidate suite should be green")
        self.assertFalse(report.oracle.passed, "oracle suite must catch the regression")
        self.assertFalse(report.passed)
        self.assertIn("oracle suite failed", str(report.error))
        self.assertTrue(report.oracle.failures)

    def test_external_python_project_needs_no_agent_package(self):
        shutil.rmtree(self.workspace / "nl_coding_agent")
        baseline = {k: v for k, v in self.baseline.items()
                    if not k.startswith("nl_coding_agent/")}
        report = verify_candidate(self.workspace, self.stage, baseline, timeout_s=60)
        self.assertTrue(report.passed, report.error)
        (self.workspace / "demo" / "calc.py").write_text(CALC_BROKEN)
        report = verify_candidate(self.workspace, self.stage, baseline, timeout_s=60)
        self.assertFalse(report.passed)
        self.assertTrue(report.oracle.failures)

    def test_project_collection_error_can_still_be_repaired(self):
        (self.workspace / "tests/test_calc.py").write_text("def broken syntax\n")
        report = self.verify()
        self.assertFalse(report.passed)
        self.assertTrue(report.candidate.failures)
        self.assertFalse(report.candidate.infrastructure_failure)

    def test_runner_error_retains_cause_and_is_infrastructure_failure(self):
        (self.workspace / "nl_coding_agent" / "__init__.py").write_text(
            "raise RuntimeError('runner startup failed')")
        report = self.verify()
        self.assertFalse(report.passed)
        self.assertTrue(report.candidate.infrastructure_failure)
        self.assertIn("runner startup failed", report.candidate.error)

    def test_candidate_without_tests_fails(self):
        shutil.rmtree(self.workspace / "tests")
        report = self.verify()
        self.assertFalse(report.passed)
        self.assertFalse(report.candidate.passed)
        self.assertIsNotNone(report.candidate.error)

    def test_cleanup_removes_verification_dir(self):
        report = self.verify()
        self.assertTrue(report.verify_dir.exists())
        cleanup_verification(report.verify_dir)
        self.assertFalse(report.verify_dir.exists())

    def test_scrubbed_env_drops_python_paths_and_sets_isolation(self):
        env = scrubbed_env(self.tmp / "data")
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertTrue(str(env["NL_DATA_DIR"]).endswith("data"))
        self.assertEqual(env["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_overlay_restores_pinned_baseline_tests(self):
        (self.workspace / "tests" / "test_calc.py").write_text(TEST_WEAK, encoding="utf-8", newline="")
        candidate, oracle, ops = prepare_copies(self.workspace, self.stage, self.baseline)
        self.assertIn("assert add(1, 2) == 0", (candidate / "tests" / "test_calc.py").read_text(encoding="utf-8"))
        self.assertEqual((oracle / "tests" / "test_calc.py").read_text(encoding="utf-8"), TEST_SOURCE)
        self.assertTrue(any("baseline test file" in op for op in ops))

    def test_parse_junit_missing_and_present(self):
        missing = self.tmp / "missing.xml"
        self.assertEqual(parse_junit(missing), (0, 0, []))
        ok = self.tmp / "ok.xml"
        ok.write_text(
            '<?xml version="1.0"?><testsuite><testcase classname="tests.t" name="test_ok"/></testsuite>',
            encoding="utf-8",
        )
        self.assertEqual(parse_junit(ok), (1, 0, []))
        bad = self.tmp / "bad.xml"
        bad.write_text(
            '<?xml version="1.0"?><testsuite><testcase classname="tests.t" name="test_bad">'
            '<failure message="boom"/></testcase></testsuite>',
            encoding="utf-8",
        )
        self.assertEqual(parse_junit(bad), (1, 1, ["tests.t::test_bad"]))


if __name__ == "__main__":
    unittest.main()

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nl_coding_agent import cli
from nl_coding_agent.cli import ensure_project, load_yaml


class TestLegacyMissionResume(unittest.TestCase):
    def test_legacy_mission_resume_raises_clear_error_without_starting(self):
        argv = ["nl_agent.py", "mission", "--project", ".", "--resume", "44"]
        mission = {
            "id": 44,
            "status": "blocked",
            "harness_version": None,
            "project_id": 1,
        }

        class ForbiddenOrchestrator:
            def __init__(self, *args, **kwargs):
                raise AssertionError("orchestrator must not start for a legacy resume")

        with patch.object(sys, "argv", argv), \
                patch(
                    "nl_coding_agent.projects.registry.open_project",
                    return_value={"id": 1},
                ), \
                patch(
                    "nl_coding_agent.persistence.missions.get_mission",
                    return_value=mission,
                ), \
                patch(
                    "nl_coding_agent.agents.orchestrator.MultiAgentOrchestrator",
                    ForbiddenOrchestrator,
                ):
            with self.assertRaises(SystemExit) as caught:
                cli.main()
        self.assertEqual(
            str(caught.exception),
            "Mission #44 predates the staged-candidate harness; "
            "create a new mission instead "
            "(legacy missions cannot be resumed safely).",
        )


class TestCliConfig(unittest.TestCase):
    def test_missing_yaml_returns_empty_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.yaml"
            self.assertEqual(load_yaml(missing), {})

    def test_missing_project_root_is_a_clear_startup_error(self):
        with self.assertRaises(SystemExit) as caught:
            ensure_project({})
        self.assertIn("Project root not configured", str(caught.exception))

    def test_configured_project_root_is_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(ensure_project({"project": {"root": str(root)}}), root.resolve())

    def test_status_without_project_config_degrades_gracefully(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = cli.status({}, Path("missing-voicebridge.yaml"))
        self.assertEqual(exit_code, 0)
        text = buffer.getvalue()
        self.assertIn("Project: not configured", text)
        self.assertIn("No state created yet", text)

    def test_status_from_portable_install_without_project_config_cli(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "voicebridge.yaml")
            argv = ["nl_agent.py", "--project-config", missing, "status"]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(buffer):
                exit_code = cli.main()
        self.assertEqual(exit_code, 0)
        self.assertIn("Project: not configured", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from nl_coding_agent import cli

ROOT = Path(__file__).resolve().parents[1]


def test_gui_launcher_disables_bytecode_cache():
    launcher = ROOT / "NL Coding Agent.bat"
    assert launcher.exists(), "NL Coding Agent.bat does not exist"
    content = launcher.read_text(encoding="utf-8")
    assert "nl_agent.py" in content
    assert "PYTHONDONTWRITEBYTECODE=1" in content


def test_selfbuild_mode_launcher():
    launcher = ROOT / "Self-Build Mode.bat"
    assert launcher.exists(), "Self-Build Mode.bat does not exist"

    content = launcher.read_text(encoding="utf-8")
    assert "nl_agent.py" in content
    assert "selfbuild" in content
    assert "--autonomous" in content
    assert "--project" in content
    assert "PYTHONDONTWRITEBYTECODE=1" in content

    result = subprocess.run(
        [sys.executable, "nl_agent.py", "selfbuild", "--help"],
        cwd=ROOT,
        timeout=60,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "--autonomous" in output
    assert "--max-missions" in output


def test_autonomous_selfbuild_forwards_stop_after():
    captured = {}

    @contextmanager
    def fake_lock(*args, **kwargs):
        yield

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "completed",
            "missions": [],
            "stopped_reason": "",
            "resume_command": "resume",
        }

    argv = [
        "nl_agent.py",
        "selfbuild",
        "--autonomous",
        "--project",
        str(ROOT),
        "--stop-after",
        "developer",
    ]
    with patch("nl_coding_agent.core.mission_lock.mission_lock", fake_lock), \
            patch(
                "nl_coding_agent.core.selfbuild_runner.run_autonomous",
                side_effect=fake_run,
            ), \
            patch.object(sys, "argv", argv):
        assert cli.main() == 0

    assert captured["stop_after"] == "developer"


if __name__ == "__main__":
    pytest.main([str(Path(__file__))])

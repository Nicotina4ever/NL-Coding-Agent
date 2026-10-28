"""CI workflow validation: matrix coverage, safe steps and static guards."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
CI_SCRIPTS = ("headless_gui_smoke.py", "bootstrap_check.py", "checksums.py")


def _workflow() -> dict:
    assert WORKFLOW.is_file(), "CI workflow is missing"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _matrix_entries() -> list[dict]:
    entries = []
    for job in _workflow().get("jobs", {}).values():
        include = (job.get("strategy", {}).get("matrix", {}) or {}).get("include", [])
        entries.extend(include)
    return entries


def _all_run_commands() -> str:
    commands = []
    for job in _workflow().get("jobs", {}).values():
        for step in job.get("steps", []):
            if "run" in step:
                commands.append(str(step["run"]))
    return "\n".join(commands)


def test_workflow_parses_and_matrix_covers_platforms():
    data = _workflow()
    assert data.get("on") is not None or data.get(True) is not None
    assert data.get("permissions", {}).get("contents") == "read"
    entries = _matrix_entries()
    by_name = {entry.get("name"): entry for entry in entries}
    assert set(by_name) >= {"windows-x64", "windows-arm64", "ubuntu-x64",
                            "ubuntu-arm64", "macos-arm64", "macos-intel-x64"}
    assert by_name["windows-x64"]["os"] == "windows-latest"
    assert by_name["ubuntu-x64"]["os"] == "ubuntu-latest"
    assert by_name["macos-arm64"]["os"] == "macos-14"
    assert by_name["macos-intel-x64"]["os"] == "macos-13"
    assert by_name["windows-arm64"]["experimental"] is True
    assert by_name["ubuntu-arm64"]["experimental"] is True
    for entry in entries:
        assert entry.get("os") and entry.get("arch") and entry.get("python_arch")
        assert entry.get("experimental") in (True, False)


def test_workflow_runs_required_checks_and_headless_gui():
    commands = _all_run_commands()
    assert "pytest" in commands
    assert "--junitxml=reports/pytest-unit.xml" in commands
    assert "--junitxml=reports/pytest-integration.xml" in commands
    assert "tests/test_bootstrap_installer.py" in commands
    assert "scripts/ci/headless_gui_smoke.py" in commands
    assert "scripts/ci/bootstrap_check.py" in commands
    assert "scripts/ci/checksums.py" in commands
    assert _workflow().get("env", {}).get("QT_QPA_PLATFORM") == "offscreen"
    steps = [step for job in _workflow()["jobs"].values()
             for step in job.get("steps", [])]
    assert any(str(step.get("uses", "")).startswith("actions/setup-python@")
               for step in steps)


def test_workflow_has_no_publishing_or_privileged_actions():
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    for forbidden in ("git push", "gh release", "gh api", "publish", "visibility",
                      "collaborator", "contents: write", "secrets.", "pull_request_target",
                      "actions/create-release", "actions/delete", "docker push"):
        assert forbidden not in text, forbidden


def test_artifacts_are_limited_to_reports_and_checksums():
    uploads = []
    for job in _workflow().get("jobs", {}).values():
        for step in job.get("steps", []):
            if "upload-artifact" in str(step.get("uses", "")):
                uploads.append(str(step.get("with", {}).get("path", "")))
    assert uploads
    for path in uploads:
        assert path.strip().startswith("reports"), path
        for forbidden in ("dist/", "data/", "python/", ".sqlite", "model", "checkpoint"):
            assert forbidden not in path.lower()
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    assert "dist/" not in text
    assert "model checkpoint" not in text


def test_ci_scripts_use_no_network_or_downloads():
    for name in CI_SCRIPTS:
        source = (REPO / "scripts" / "ci" / name).read_text(encoding="utf-8")
        lowered = source.lower()
        for forbidden in ("urllib.request", "requests", "http.client", "socket.socket",
                          "pip install", "curl ", "wget ", "git clone", "download("):
            assert forbidden not in lowered, (name, forbidden)
        assert "https://" not in lowered, name
    bootstrap = (REPO / "scripts" / "ci" / "bootstrap_check.py").read_text(encoding="utf-8")
    assert "--offline-bundle" in bootstrap
    assert "offline://ci/" in bootstrap


def test_ci_scripts_run_locally_and_write_only_report_files(tmp_path):
    reports = tmp_path / "reports"
    run_env = dict(os.environ)
    run_env.update({"PYTHONDONTWRITEBYTECODE": "1",
                    "QT_QPA_PLATFORM": "offscreen",
                    "NL_DATA_DIR": str(tmp_path / "data")})
    for script in ("headless_gui_smoke.py", "bootstrap_check.py"):
        completed = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "ci" / script),
             "--json", "--report-dir", str(reports)],
            cwd=str(REPO), env=run_env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180)
        assert completed.returncode == 0, completed.stderr[-2000:]
        payload = json.loads(completed.stdout)
        assert payload["status"] == "PASS"
    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "ci" / "checksums.py"), str(reports)],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert completed.returncode == 0
    names = {path.name for path in reports.iterdir()}
    assert names == {"headless_gui_smoke.json", "bootstrap_check.json", "SHA256SUMS"}
    assert "  " in (reports / "SHA256SUMS").read_text(encoding="utf-8")


def test_ci_docs_exist_and_mark_manual_pending():
    docs = (REPO / "docs" / "CI.md").read_text(encoding="utf-8")
    assert "matrix" in docs.lower()
    assert "MANUAL-PENDING" in docs
    for platform in ("Windows", "Linux", "macOS", "ARM64", "x64"):
        assert platform.lower() in docs.lower()
    assert "checksum" in docs.lower()
    assert "no publish" in docs.lower() or "no publishing" in docs.lower()

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
CI_SCRIPTS = ("headless_gui_smoke.py", "bootstrap_check.py", "checksums.py",
              "package_smoke.py")


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
    assert "scripts/ci/package_smoke.py" in commands
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
    for script in ("headless_gui_smoke.py", "bootstrap_check.py", "package_smoke.py"):
        completed = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "ci" / script),
             "--json", "--report-dir", str(reports)],
            cwd=str(REPO), env=run_env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300)
        assert completed.returncode == 0, completed.stderr[-2000:]
        payload = json.loads(completed.stdout)
        assert payload["status"] == "PASS"
    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "ci" / "checksums.py"), str(reports)],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert completed.returncode == 0
    names = {path.name for path in reports.iterdir()}
    assert names == {"headless_gui_smoke.json", "bootstrap_check.json",
                     "package_smoke.json", "SHA256SUMS"}
    assert "  " in (reports / "SHA256SUMS").read_text(encoding="utf-8")




def test_package_smoke_job_is_ubuntu_isolated_and_reports_only():
    data = _workflow()
    job = data["jobs"]["package-smoke"]
    assert job["runs-on"] == "ubuntu-latest"
    assert int(job["timeout-minutes"]) <= 30
    assert job.get("permissions", {}).get("contents") == "read"
    steps = job["steps"]
    commands = [str(step.get("run", "")) for step in steps]
    assert any("scripts/ci/package_smoke.py --json --report-dir reports" in command
               for command in commands)
    assert any("scripts/ci/checksums.py reports" in command for command in commands)
    setup = [step for step in steps
             if str(step.get("uses", "")).startswith("actions/setup-python@")]
    assert setup, "package-smoke must set up Python"
    assert str(setup[0]["with"]["python-version"]).startswith("3.12")
    uploads = [step for step in steps
               if "actions/upload-artifact" in str(step.get("uses", ""))]
    assert uploads
    upload = uploads[0]
    assert str(upload["with"]["path"]).strip().startswith("reports")
    assert int(upload["with"]["retention-days"]) <= 7
    text = json.dumps(job).lower()
    for forbidden in ("contents: write", "secrets.", "git push", "gh release",
                      "publish", "visibility", "collaborator", "docker push"):
        assert forbidden not in text, forbidden


def test_package_smoke_local_pass_writes_only_report(tmp_path):
    import os
    import subprocess

    reports = tmp_path / "reports"
    env = dict(os.environ)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen",
                "NL_DATA_DIR": str(tmp_path / "data")})
    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "ci" / "package_smoke.py"),
         "--json", "--report-dir", str(reports)],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    payload = json.loads(completed.stdout)
    assert payload["status"] == "PASS"
    assert payload["workspace"] == {"managed": True, "cleaned": True}
    assert payload["checks"] and all(item["status"] == "PASS"
                                     for item in payload["checks"])
    ids = [item["id"] for item in payload["checks"]]
    assert "beta_package_checksums_and_manifests" in ids
    assert "release_acceptance_matrix_all_manual_pending" in ids
    assert "native_runtime_plan_dry_run" in ids
    assert {path.name for path in reports.iterdir()} == {"package_smoke.json"}
    report = json.loads((reports / "package_smoke.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["facts"]["acceptance_matrix"]["manual_pending"] == 6
    assert report["facts"]["beta_package"]["targets"] == 6
    assert report["facts"]["native_runtime_plan"]["no_network"] is True


def test_ci_docs_exist_and_mark_manual_pending():
    docs = (REPO / "docs" / "CI.md").read_text(encoding="utf-8")
    assert "matrix" in docs.lower()
    assert "MANUAL-PENDING" in docs
    for platform in ("Windows", "Linux", "macOS", "ARM64", "x64"):
        assert platform.lower() in docs.lower()
    assert "checksum" in docs.lower()
    assert "no publish" in docs.lower() or "no publishing" in docs.lower()
    assert "package-smoke" in docs.lower() or "package smoke" in docs.lower()
    assert "package_smoke.json" in docs
    assert "retention" in docs.lower()
    assert "MANUAL-PENDING" in docs

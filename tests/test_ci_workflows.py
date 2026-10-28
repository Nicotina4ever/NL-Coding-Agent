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
              "package_smoke.py", "reproducibility_check.py")


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

def test_workflow_has_reproducibility_job_reports_only():
    job = _workflow()["jobs"]["reproducibility"]
    assert job["permissions"]["contents"] == "read"
    assert int(job["timeout-minutes"]) <= 20
    entries = job["strategy"]["matrix"]["include"]
    assert {"ubuntu-latest", "windows-latest", "macos-14"} <= {entry["os"] for entry in entries}
    for entry in entries:
        assert entry["experimental"] is False
        assert entry["arch"] and entry["python_arch"]
    commands = [str(step.get("run", "")) for step in job["steps"]]
    assert any("scripts/ci/reproducibility_check.py --json --report-dir reports" in command
               for command in commands)
    assert any("scripts/ci/checksums.py reports" in command for command in commands)
    setup = [step for step in job["steps"]
             if str(step.get("uses", "")).startswith("actions/setup-python@")]
    assert setup, "reproducibility must set up Python"
    assert str(setup[0]["with"]["python-version"]).startswith("3.12")
    uploads = [step for step in job["steps"]
               if "actions/upload-artifact" in str(step.get("uses", ""))]
    assert uploads
    assert str(uploads[0]["with"]["path"]).strip().startswith("reports")
    assert int(uploads[0]["with"]["retention-days"]) <= 7
    text = json.dumps(job).lower()
    for forbidden in ("contents: write", "secrets.", "git push", "gh release",
                      "publish", "visibility", "collaborator", "docker push",
                      "pull_request_target"):
        assert forbidden not in text, forbidden


def _dist_entries() -> list[str]:
    dist = REPO / ".workspace" / "dist"
    if not dist.is_dir():
        return []
    return sorted(path.name for path in dist.iterdir())


def test_reproducibility_local_pass_writes_only_report(tmp_path):
    reports = tmp_path / "reports"
    env = dict(os.environ)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen",
                "NL_DATA_DIR": str(tmp_path / "data")})
    before = _dist_entries()
    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "ci" / "reproducibility_check.py"),
         "--json", "--report-dir", str(reports)],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300)
    assert completed.returncode == 0, completed.stderr[-3000:]
    payload = json.loads(completed.stdout)
    assert payload["status"] == "PASS"
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["checks"] >= 30
    assert payload["forbidden"]["ok"] is True
    assert payload["workspace"] == {"managed": True, "cleaned": True}
    assert len(payload["runs"]) == 2
    assert all(value is True for value in payload["comparisons"].values())
    names = {path.name for path in reports.iterdir()}
    assert names == {"reproducibility_check.json", "reproducibility_check.md"}
    report = json.loads((reports / "reproducibility_check.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert "MANUAL-PENDING" in report["ci_vs_manual_pending"]
    assert "byte-identical" in report["ci_vs_manual_pending"]
    assert _dist_entries() == before, "reproducibility check must not write release candidates"


def test_reproducibility_detects_tamper_and_forbidden(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "nl_reproducibility_check",
        REPO / "scripts" / "ci" / "reproducibility_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def make_candidate(root: Path, label: str, manifest_text: str,
                       archive: bytes) -> dict:
        root.mkdir(parents=True)
        (root / "x-source.zip").write_bytes(archive)
        for name in module.MANIFEST_NAMES:
            (root / name).write_text(manifest_text, encoding="utf-8")
        return module.collect_candidate(root, label)

    run1 = make_candidate(tmp_path / "c1", "run1", '{"a": 1}', b"zip-one")
    run2 = make_candidate(tmp_path / "c2", "run2", '{"a": 2}', b"zip-two")
    checks, comparisons = module.compare_runs(run1, run2)
    failed = {check["id"] for check in checks if check["status"] == "FAIL"}
    assert "archive_sha256_equal" in failed
    assert "release_manifest_byte_identical" in failed
    assert comparisons["archive_sha256_equal"] is False

    found = module.scan_forbidden_paths([
        "python/python.exe", "data/app.sqlite3", ".workspace/x", "temp_fix.py",
        "crewAI/vendor.py", "docs/readme.md", "nl_coding_agent/cli.py",
    ])
    paths = {item["path"] for item in found}
    assert {"python/python.exe", "data/app.sqlite3", ".workspace/x", "temp_fix.py",
            "crewAI/vendor.py"} <= paths
    assert "docs/readme.md" not in paths
    assert "nl_coding_agent/cli.py" not in paths


def test_ci_docs_document_reproducibility_job():
    docs = (REPO / "docs" / "CI.md").read_text(encoding="utf-8")
    lowered = docs.lower()
    assert "reproducib" in lowered
    assert "reproducibility_check.json" in docs
    assert "byte" in lowered and "identical" in lowered
    assert "3-day retention" in docs
    assert "MANUAL-PENDING" in docs
    assert "no publishing" in lowered or "no publish" in lowered

def test_reproducibility_missing_source_exits_one(tmp_path):
    reports = tmp_path / "reports"
    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "ci" / "reproducibility_check.py"),
         "--json", "--report-dir", str(reports),
         "--source", str(tmp_path / "does-not-exist")],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120)
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert payload["summary"]["failed"] >= 1
    assert (reports / "reproducibility_check.json").is_file()
    assert (reports / "reproducibility_check.md").is_file()


def test_workflow_has_blocking_secrets_scan_job_reports_only():
    data = _workflow()
    assert "secrets-scan" in data["jobs"], "blocking secrets-scan job is missing"
    job = data["jobs"]["secrets-scan"]
    assert job["runs-on"] == "ubuntu-latest"
    assert int(job["timeout-minutes"]) <= 30
    assert job["permissions"]["contents"] == "read"
    steps = job.get("steps", [])
    checkout = [step for step in steps
                if str(step.get("uses", "")).startswith("actions/checkout@")]
    assert checkout
    assert checkout[0]["with"].get("persist-credentials") is False
    assert checkout[0]["with"].get("fetch-depth") == 0
    commands = " ".join(str(step.get("run", "")) for step in steps)
    assert "scripts/prepush_guard.py scan-all" in commands
    assert "--json-out reports/prepush_guard.json" in commands
    assert "--markdown-out reports/prepush_guard.md" in commands
    assert "scripts/ci/checksums.py reports" in commands
    # No bypass flags or non-blocking behavior in the blocking job.
    assert "--no-verify" not in commands.lower()
    assert "|| true" not in commands
    assert "continue-on-error" not in json.dumps(job).lower()
    uploads = [step for step in steps
               if "actions/upload-artifact" in str(step.get("uses", ""))]
    assert uploads
    assert str(uploads[0]["with"]["path"]).strip().startswith("reports")
    text = json.dumps(job).lower()
    for forbidden in ("contents: write", "secrets.", "git push", "gh release",
                      "publish", "visibility", "collaborator", "docker push",
                      "pull_request_target"):
        assert forbidden not in text, forbidden


def test_pre_push_guard_docs_cover_install_bypass_and_release_head_rerun():
    docs = (REPO / "docs" / "PRE_PUSH_GUARD.md").read_text(encoding="utf-8")
    lowered = docs.lower()
    assert "install-hook" in docs
    assert "--force" in docs and "--backup" in docs
    assert "scan-all" in docs
    assert "exit" in lowered and "fail closed" in lowered
    assert "--no-verify" in lowered
    assert "outside" in lowered and "control" in lowered
    assert "earlier public" in lowered or "before any" in lowered
    assert "final release-head" in lowered
    assert "bounded" in lowered
    assert "not a substitute" in lowered
    assert "owner authorization" in lowered
    assert "scan-all at current head" in lowered or "measured evidence" in lowered


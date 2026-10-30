from __future__ import annotations

import sys
import time

import pytest


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    data = tmp_path / "data"
    workspace = tmp_path / "workspace"
    crewai = tmp_path / "crewai"
    for path in (data, workspace, crewai, tmp_path / "tmp", tmp_path / "appdata",
                 tmp_path / "localappdata"):
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NL_DATA_DIR", str(data))
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CREWAI_STORAGE_DIR", str(crewai))
    monkeypatch.setenv("TMP", str(tmp_path / "tmp"))
    monkeypatch.setenv("TEMP", str(tmp_path / "tmp"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    return tmp_path



def _wait(job_id, project_id, timeout=15):
    from nl_coding_agent.core import job_manager
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = job_manager.get_job(project_id, job_id)
        if job.get("status") not in ("starting", "running"):
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_background_job_runs_in_project_and_persists_output(isolated):
    from nl_coding_agent.core import job_manager
    from nl_coding_agent.app.services import AppServices
    services = AppServices()
    project_dir = isolated / "project"
    project_dir.mkdir()
    (project_dir / "job.py").write_text(
        "from pathlib import Path\nPath('job-output.txt').write_text('JOB-OK')\n"
        "print('JOB-OUTPUT')\n", encoding="utf-8")
    project = services.open_project(project_dir)
    job = job_manager.start_job(
        project["id"], project_dir, [sys.executable, "job.py"], label="probe")
    finished = _wait(job["id"], project["id"])
    assert finished["status"] == "completed"
    assert (project_dir / "job-output.txt").read_text(encoding="utf-8") == "JOB-OK"
    result = job_manager.output(project["id"], job["id"])
    assert "JOB-OUTPUT" in result["output"]
    assert any(item["id"] == job["id"] for item in job_manager.list_jobs(project["id"]))
    services._db.close()


def test_background_job_rejects_inline_code_and_external_scripts(isolated):
    from nl_coding_agent.core import job_manager
    from nl_coding_agent.app.services import AppServices
    services = AppServices()
    project_dir = isolated / "project"
    project_dir.mkdir()
    project = services.open_project(project_dir)
    try:
        job_manager.start_job(project["id"], project_dir, [sys.executable, "-c", "print(1)"])
    except job_manager.JobError as exc:
        assert "inline" in str(exc)
    else:
        raise AssertionError("inline python must be rejected")
    outside = isolated / "outside.py"
    outside.write_text("print('outside')", encoding="utf-8")
    try:
        job_manager.start_job(project["id"], project_dir, [sys.executable, str(outside)])
    except job_manager.JobError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("external script must be rejected")
    services._db.close()

from __future__ import annotations

import json

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


def test_node_candidate_verification_runs_the_project_test_command(isolated):
    from nl_coding_agent.core import candidate_verification
    stage = isolated / "stage"
    workspace = stage / "workspace"
    tests = workspace / "tests"
    tests.mkdir(parents=True)
    (workspace / "package.json").write_text(json.dumps({
        "name": "fixture", "private": True,
        "scripts": {"test": 'node --test "tests/**/*.test.js"'},
    }), encoding="utf-8")
    (tests / "ok.test.js").write_text(
        "const test = require('node:test');\n"
        "const assert = require('node:assert');\n"
        "test('ok', () => { assert.equal(1 + 1, 2); });\n",
        encoding="utf-8")
    stage.mkdir(exist_ok=True)
    report = candidate_verification.verify_candidate(
        workspace, stage, {}, project_root=None, timeout_s=60)
    assert report.candidate.passed, report.candidate.error
    assert report.candidate.command == ["npm test"]
    assert report.passed, report.error

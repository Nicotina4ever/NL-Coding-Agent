"""Tests for independent goal completion verification and false-completion detection.

NL-BP-215. All tests use a throw-away NL_DATA_DIR, create goals/missions through the
existing persistence modules and never run a model, network request or GUI.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nl_coding_agent.core import goal_verification as gv
from nl_coding_agent.persistence import database
from nl_coding_agent.persistence import goal_store
from nl_coding_agent.persistence import missions as missions_store
from nl_coding_agent.persistence import supervisor_store

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path))
    goal_store.ensure_schema()
    return tmp_path


@pytest.fixture()
def goal_factory(data_dir):
    def make(*, criteria=("Feature works",), objective="Deliver the feature",
             status="active", title="Goal"):
        goal_id = goal_store.create_goal(
            None, title, objective, acceptance_criteria=list(criteria))
        if status != "planned":
            goal_store.set_goal_status(goal_id, status)
        return goal_id
    return make


@pytest.fixture()
def mission_factory(goal_factory):
    def make(goal_id):
        mission_id = missions_store.create_mission(None, "Mission", "Do the work")
        goal_store.link_mission(goal_id, mission_id)
        return mission_id
    return make


def _evidence(type, source, result="pass", trust="trusted", **kwargs):
    item = {"type": type, "source": source, "result": result, "trust": trust}
    item.update(kwargs)
    return item


def _criterion(criterion_id, text, types=()):
    return {
        "id": criterion_id,
        "text": text,
        "required_evidence_types": list(types),
    }


def _now(offset_seconds=0):
    return (datetime.now() + timedelta(seconds=offset_seconds)).isoformat(
        timespec="seconds")


def _set_review_verdict(mission_id, verdict):
    conn = database.get_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE missions SET review_verdict=?, finished_at=? WHERE id=?",
                (verdict, _now(), int(mission_id)),
            )
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Verified criteria with source-backed evidence
# --------------------------------------------------------------------------- #

def test_criteria_verified_with_test_command_artifact_reviewer_user_evidence(
        goal_factory):
    goal_id = goal_factory(criteria=[])
    criteria = [
        _criterion("C1", "tests pass", ["test"]),
        _criterion("C2", "command succeeds", ["command"]),
        _criterion("C3", "artifact hash present", ["artifact"]),
        _criterion("C4", "reviewer approved", ["reviewer_approval"]),
        _criterion("C5", "user confirmed", ["user_confirmation"]),
    ]
    evidence = [
        _evidence("test", "pytest:tests", exit_code=0),
        _evidence("command", "cmd:build", exit_code=0),
        _evidence("artifact", "artifact:zip", sha256="a" * 64, path="dist/app.zip"),
        _evidence("reviewer_approval", "reviewer:proof", actor="reviewer"),
        _evidence("user_confirmation", "user:ok", actor="owner"),
    ]
    report = gv.verify_goal(goal_id, evidence, criteria)
    assert report["verdict"] == "verified"
    assert report["false_completion"] is False
    assert report["record_id"] is not None
    assert [item["status"] for item in report["criteria"]] == ["verified"] * 5
    assert report["goal_status"] == "active"
    assert report["goal_status_mutated"] is False
    # Verification never auto-completes the goal.
    assert goal_store.get_goal(goal_id)["status"] == "active"


def test_required_evidence_types_are_enforced(goal_factory):
    goal_id = goal_factory(criteria=[])
    report = gv.verify_goal(
        goal_id,
        [_evidence("artifact", "artifact:only", sha256="b" * 64)],
        [_criterion("C1", "tests required", ["test"])],
    )
    assert report["criteria"][0]["status"] == "missing"
    assert report["verdict"] == "unverified"
    assert any(
        blocker["code"] == "missing_evidence"
        for blocker in report["criteria"][0]["blockers"]
    )

    partial = gv.verify_goal(
        goal_id,
        [_evidence("test", "pytest:partial", exit_code=0)],
        [_criterion("C2", "test and artifact", ["test", "artifact"])],
    )
    assert partial["criteria"][0]["status"] == "partial"
    assert partial["verdict"] == "partial"
    assert any(
        "artifact" in str(blocker.get("detail"))
        for blocker in partial["criteria"][0]["blockers"]
    )


def test_missing_unknown_stale_and_contradicted_statuses(goal_factory):
    goal_id = goal_factory(criteria=[])
    criteria = [_criterion("C1", "tests pass", ["test"])]

    missing = gv.verify_goal(goal_id, [], criteria)
    assert missing["criteria"][0]["status"] == "missing"
    assert missing["verdict"] == "unverified"

    model_claim = gv.verify_goal(
        goal_id,
        [_evidence("test", "model:claim", trust="model")],
        criteria,
    )
    assert model_claim["criteria"][0]["status"] == "unknown"
    assert model_claim["verdict"] == "unverified"
    ref = model_claim["evidence_refs"][0]
    assert ref["accepted"] is False
    assert "untrusted" in ref["rejection_reason"]

    stale = gv.verify_goal(
        goal_id,
        [_evidence("test", "pytest:old", timestamp=_now(-86400), exit_code=0)],
        [{"id": "C1", "text": "tests pass", "required_evidence_types": ["test"],
          "stale_after_s": 60}],
    )
    assert stale["criteria"][0]["status"] == "stale"
    assert stale["verdict"] == "unverified"

    contradicted = gv.verify_goal(
        goal_id,
        [
            _evidence("test", "pytest:pass", exit_code=0),
            _evidence("test", "pytest:fail", exit_code=1),
        ],
        criteria,
    )
    assert contradicted["criteria"][0]["status"] == "contradicted"
    assert contradicted["verdict"] == "contradicted"
    assert any(
        blocker["code"] == "contradicted"
        for blocker in contradicted["criteria"][0]["blockers"]
    )


def test_exit_codes_are_authoritative_for_command_evidence(goal_factory):
    goal_id = goal_factory(criteria=[])
    criteria = [_criterion("C1", "command ok", ["command"])]
    ok = gv.verify_goal(goal_id, [_evidence("command", "cmd:zero", exit_code=0)],
                        criteria)
    assert ok["verdict"] == "verified"
    failed = gv.verify_goal(goal_id, [{"type": "command", "source": "cmd:one",
                                       "exit_code": 1, "trust": "system"}],
                            criteria)
    assert failed["verdict"] == "contradicted"


# --------------------------------------------------------------------------- #
# Existing recorded evidence (verification_runs / mission_evidence / task_attempts)
# --------------------------------------------------------------------------- #

def test_recorded_mission_evidence_satisfies_criteria(goal_factory, mission_factory):
    goal_id = goal_factory(criteria=[])
    mission_id = mission_factory(goal_id)
    missions_store.record_verification_run(
        mission_id, None, "pytest -q tests", 0, "ok", "", True)
    supervisor_store.record_evidence(
        mission_id, kind="artifact", record_key="zip",
        payload={"result": "pass", "path": "dist/app.zip"},
        sha256="c" * 64, path="dist/app.zip")
    supervisor_store.record_evidence(
        mission_id, kind="review", record_key="reviewer",
        payload={"result": "pass", "reviewer": "reviewer"})
    task_id = missions_store.add_task(mission_id, "Verify", "run tests", "tester")
    missions_store.record_task_attempt(task_id, "success", output="ok")

    criteria = [
        _criterion("C1", "test run", ["test"]),
        _criterion("C2", "artifact", ["artifact"]),
        _criterion("C3", "reviewer", ["reviewer_approval"]),
        _criterion("C4", "task command", ["command"]),
    ]
    report = gv.verify_goal(goal_id, [], criteria)
    assert report["verdict"] == "verified"
    sources = {ref["source"] for ref in report["evidence_refs"]}
    assert any(source.startswith("db:verification_runs:") for source in sources)
    assert any(source.startswith("db:mission_evidence:") for source in sources)
    assert any(source.startswith("db:task_attempts:") for source in sources)
    artifact_refs = [ref for ref in report["evidence_refs"]
                     if ref["type"] == "artifact"]
    assert artifact_refs and artifact_refs[0]["sha256"] == "c" * 64
    assert artifact_refs[0]["path"] == "dist/app.zip"


def test_mission_review_verdict_is_source_backed_evidence(goal_factory, mission_factory):
    goal_id = goal_factory(criteria=[])
    mission_id = mission_factory(goal_id)
    _set_review_verdict(mission_id, "APPROVE")
    report = gv.verify_goal(
        goal_id, [],
        [_criterion("C1", "reviewer approved", ["reviewer_approval"])],
    )
    assert report["verdict"] == "verified"
    assert any(
        ref["source"].endswith(":review_verdict")
        for ref in report["evidence_refs"]
    )


# --------------------------------------------------------------------------- #
# Persistence: hash/source, ordering, schema idempotency, restart survival
# --------------------------------------------------------------------------- #

def test_evidence_hash_and_source_are_persisted(goal_factory):
    goal_id = goal_factory(criteria=[])
    artifact_hash = "d" * 64
    report = gv.verify_goal(
        goal_id,
        [_evidence("artifact", "artifact:persist", sha256=artifact_hash,
                   path="out/app.bin")],
        [_criterion("C1", "artifact", ["artifact"])],
    )
    assert report["verdict"] == "verified"
    records = gv.list_goal_verifications(goal_id)
    assert len(records) == 1
    stored = records[0]
    assert stored["id"] == report["record_id"]
    refs = stored["evidence_refs"]
    assert refs[0]["source"] == "artifact:persist"
    assert refs[0]["sha256"] == artifact_hash
    fetched = gv.get_goal_verification(report["record_id"])
    assert fetched["verdict"] == "verified"
    assert fetched["criteria"][0]["status"] == "verified"


def test_multiple_records_and_ordering(goal_factory):
    goal_id = goal_factory(criteria=[])
    criteria = [_criterion("C1", "tests", ["test"])]
    first = gv.verify_goal(goal_id, [_evidence("test", "pytest:one", exit_code=0)],
                           criteria)
    second = gv.verify_goal(goal_id, [], criteria)
    assert second["record_id"] > first["record_id"]
    records = gv.list_goal_verifications(goal_id)
    assert [record["id"] for record in records] == [second["record_id"],
                                                    first["record_id"]]
    assert records[0]["verdict"] == "unverified"
    latest = gv.latest_goal_verification(goal_id)
    assert latest["id"] == second["record_id"]


def test_schema_is_idempotent_and_survives_restart(goal_factory, data_dir):
    columns = gv.ensure_schema()
    again = gv.ensure_schema()
    assert columns == again
    for expected in ("goal_id", "verifier_version", "verdict", "criteria_json",
                     "evidence_refs_json", "blockers_json", "self_declared",
                     "self_declared_mismatch", "created_at"):
        assert expected in columns
    goal_id = goal_factory(criteria=[])
    gv.verify_goal(goal_id, [_evidence("test", "pytest:restart", exit_code=0)],
                   [_criterion("C1", "tests", ["test"])])

    env = dict(os.environ)
    env["NL_DATA_DIR"] = str(data_dir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import sys; sys.path.insert(0, " + repr(str(REPO_ROOT)) + "); "
        "from nl_coding_agent.core import goal_verification as g; "
        "records = g.list_goal_verifications(" + str(goal_id) + "); "
        "print(records[0]['verdict']); print(len(records))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env,
        capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == ["verified", "1"]
    conn = sqlite3.connect(str(data_dir / "nl_coding_agent.sqlite3"))
    try:
        count = conn.execute("SELECT COUNT(*) FROM goal_verifications").fetchone()[0]
    finally:
        conn.close()
    assert count == 1


# --------------------------------------------------------------------------- #
# False-completion detection and outstanding summary
# --------------------------------------------------------------------------- #

def test_false_completion_when_completed_without_verification(goal_factory):
    goal_id = goal_factory(status="completed",
                           criteria=("Feature works",))
    result = gv.detect_false_completion(goal_id)
    assert result["ok"] is False
    assert result["count"] == 1
    finding = result["false_completions"][0]
    assert finding["goal_id"] == goal_id
    assert finding["reason_code"] == "completed_without_verification"
    assert finding["record_id"] is None
    summary = gv.summarize_outstanding(goal_id)
    assert summary["verified"] is False
    assert summary["blockers"][0]["code"] == "no_verification_record"
    assert summary["outstanding_criteria"][0]["status"] == "missing"


def test_false_completion_when_latest_record_is_contradicted(goal_factory):
    goal_id = goal_factory(status="completed",
                           criteria=("Feature works",))
    report = gv.verify_goal(
        goal_id, [_evidence("test", "pytest:fail", exit_code=1)],
        [_criterion("C1", "tests pass", ["test"])],
    )
    assert report["verdict"] == "contradicted"
    assert report["self_declared"] is True
    assert report["self_declared_mismatch"] is True
    assert report["false_completion"] is True
    result = gv.detect_false_completion(goal_id)
    assert result["count"] == 1
    assert result["false_completions"][0]["reason_code"] == "contradicted_criteria"
    assert result["false_completions"][0]["record_id"] == report["record_id"]
    # Detection/verification never changes the goal lifecycle.
    assert goal_store.get_goal(goal_id)["status"] == "completed"


def test_verified_completed_goal_is_not_a_false_completion(goal_factory):
    goal_id = goal_factory(status="completed",
                           criteria=("Feature works",))
    report = gv.verify_goal(
        goal_id, [_evidence("test", "pytest:pass", exit_code=0)],
        [_criterion("C1", "tests pass", ["test"])],
    )
    assert report["verdict"] == "verified"
    assert report["self_declared"] is True
    assert report["self_declared_mismatch"] is False
    result = gv.detect_false_completion()
    assert result["ok"] is True
    assert result["count"] == 0


def test_detect_scans_all_completed_goals(goal_factory):
    verified_goal = goal_factory(status="completed", title="Verified")
    gv.verify_goal(verified_goal, [_evidence("test", "pytest:ok", exit_code=0)],
                   [_criterion("C1", "tests", ["test"])])
    missing_goal = goal_factory(status="completed", title="No verification")
    result = gv.detect_false_completion()
    assert result["checked_goals"] == 2
    assert result["count"] == 1
    assert result["false_completions"][0]["goal_id"] == missing_goal
    assert [item["goal_id"] for item in gv.find_false_completions()] == [missing_goal]


def test_self_declared_completion_on_active_goal_is_a_mismatch(goal_factory):
    goal_id = goal_factory(status="active", criteria=("Feature works",))
    report = gv.verify_goal(
        goal_id, [], [_criterion("C1", "tests", ["test"])],
        self_declared_complete=True,
    )
    assert report["verdict"] == "unverified"
    assert report["self_declared"] is True
    assert report["self_declared_mismatch"] is True
    record = gv.get_goal_verification(report["record_id"])
    assert record["self_declared"] is True
    assert record["self_declared_mismatch"] is True
    assert goal_store.get_goal(goal_id)["status"] == "active"


def test_goal_without_acceptance_criteria_cannot_be_verified(goal_factory):
    goal_id = goal_factory(status="completed", criteria=())
    report = gv.verify_goal(goal_id, [])
    assert report["verdict"] == "unverified"
    assert any(blocker["code"] == "no_acceptance_criteria"
               for blocker in report["blockers"])
    assert gv.detect_false_completion(goal_id)["count"] == 1


def test_explicit_criteria_override_goal_acceptance_list(goal_factory):
    goal_id = goal_factory(criteria=("Legacy criterion",))
    report = gv.verify_goal(
        goal_id,
        [_evidence("file_check", "fs:file", result="pass")],
        [_criterion("NEW-1", "file exists", ["file_check"])],
    )
    assert report["verdict"] == "verified"
    assert report["criteria"][0]["criterion_id"] == "NEW-1"


def test_summarize_outstanding_after_partial_verification(goal_factory):
    goal_id = goal_factory(criteria=())
    gv.verify_goal(
        goal_id,
        [_evidence("test", "pytest:partial", exit_code=0)],
        [
            _criterion("C1", "tests", ["test"]),
            _criterion("C2", "artifact", ["artifact"]),
        ],
    )
    summary = gv.summarize_outstanding(goal_id)
    assert summary["verified"] is False
    assert summary["false_completion"] is True
    outstanding_ids = [item["criterion_id"]
                       for item in summary["outstanding_criteria"]]
    assert outstanding_ids == ["C2"]
    assert summary["blockers"]


# --------------------------------------------------------------------------- #
# Validation, trust and import hygiene
# --------------------------------------------------------------------------- #

def test_untrusted_or_unknown_results_never_verify(goal_factory):
    goal_id = goal_factory(criteria=[])
    criteria = [_criterion("C1", "any evidence", [])]
    untrusted = gv.verify_goal(
        goal_id, [_evidence("artifact", "model:claim", trust="model")], criteria)
    assert untrusted["verdict"] == "unverified"
    assert untrusted["criteria"][0]["status"] == "unknown"

    unknown_result = gv.verify_goal(
        goal_id,
        [_evidence("artifact", "fs:check", result="unknown", trust="system")],
        criteria,
    )
    assert unknown_result["criteria"][0]["status"] == "unknown"

    trusted = gv.verify_goal(
        goal_id,
        [_evidence("artifact", "fs:check", result="pass", trust="system")],
        criteria,
    )
    assert trusted["verdict"] == "verified"


def test_evidence_and_criterion_validation(goal_factory):
    goal_id = goal_factory(criteria=[])
    with pytest.raises(ValueError):
        gv.verify_goal(goal_id, [{"type": "telepathy", "source": "x"}],
                       [_criterion("C1", "x", [])])
    with pytest.raises(ValueError):
        gv.normalize_evidence({"type": "test", "result": "pass"})
    with pytest.raises(ValueError):
        gv.normalize_criterion({"id": "C1", "text": "x", "bogus": True})
    with pytest.raises(ValueError):
        gv.verify_goal(goal_id, [], [{"id": "C1", "text": "a"},
                                    {"id": "C1", "text": "b"}])
    with pytest.raises(gv.GoalNotFoundError):
        gv.verify_goal(999999, [])


def test_verifier_module_has_no_model_network_or_gui_imports():
    source = (REPO_ROOT / "nl_coding_agent" / "core" / "goal_verification.py")
    text = source.read_text(encoding="utf-8").lower()
    for forbidden in ("import crewai", "from crewai", "import requests",
                      "import urllib", "import httpx", "import socket",
                      "pyside6", "pyqt", "openai", "sqlite3"):
        assert forbidden not in text, forbidden

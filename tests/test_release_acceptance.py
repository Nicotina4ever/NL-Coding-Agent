"""Release acceptance matrix/record tool: validation, redaction, no false CI claims."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "release_acceptance.py"
SHA = "a" * 64


def _fixture_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "evidence" / "beta_acceptance").mkdir(parents=True)
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    (root / "docs" / "HARNESS_ACCEPTANCE.md").write_text(
        "## Stage-6b portable release acceptance (2026-10-28) - PARTIAL\n"
        "CI is headless regression evidence; hardware is MANUAL-PENDING.\n", encoding="utf-8")
    (root / "docs" / "RELEASE_ACCEPTANCE.md").write_text(
        "| Requirement | Acceptance state |\n|---|---|\n"
        "| NL-BP-156/165 | PARTIAL + MANUAL-PENDING: CI checks not executed, hardware absent |\n"
        "| NL-BP-164 | PARTIAL: matrix documented; real-hardware records MANUAL-PENDING |\n",
        encoding="utf-8")
    (root / "docs" / "PRODUCT_BACKLOG.md").write_text(
        "### NL-BP-140 - Release acceptance matrix runner\n\n"
        "- **Status:** partial\n", encoding="utf-8")
    (root / "docs" / "SECRETS_AUDIT.md").write_text(
        "| Findings | 66 (blocking: 0) |\n| Upload gate | **CLEAR-WITH-REVIEW** |\n",
        encoding="utf-8")
    return root


def _record(target="windows-x86_64", *, hardware_pass=True, alias="tester-1", **overrides):
    steps = {}
    for step in ("install", "startup", "cli", "gui", "offline", "restart"):
        steps[step] = {"result": "pass", "evidence_note": "observed on target"}
    for step in ("clipboard", "mic", "asr_tts", "gpu"):
        steps[step] = ({"result": "pass", "evidence_note": "explicit manual hardware result"}
                       if hardware_pass else
                       {"result": "manual-pending", "evidence_note": "not tested yet"})
    record = {
        "schema_version": "1.0", "tester_alias": alias,
        "timestamp": "2026-10-28T12:00:00+00:00", "target_id": target,
        "os": "windows" if target.startswith("windows") else
              "linux" if target.startswith("linux") else "macos",
        "arch": "arm64" if target.endswith("arm64") else "x86_64",
        "package": {"version": "0.1.0-beta", "sha256": SHA},
        "install_path_type": "clean-custom",
        "evidence_notes": "clean machine installation; screenshots retained by owner",
        "steps": steps,
    }
    record.update(overrides)
    return record


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def test_matrix_labels_ci_vs_manual_and_never_claims_ci_hardware(tmp_path):
    root = _fixture_repo(tmp_path)
    reports = tmp_path / "reports"
    first = _run(root, "matrix", "--records-dir", str(root / "docs" / "evidence" / "beta_acceptance"),
                 "--json-out", str(reports / "matrix.json"),
                 "--markdown-out", str(reports / "matrix.md"), "--json")
    assert first.returncode == 0, first.stderr
    matrix = json.loads(first.stdout)
    assert matrix["ci_support_claimed"] is False
    assert matrix["summary"]["no_ci_hardware_claim"] is True
    assert len(matrix["targets"]) == 6
    for row in matrix["targets"]:
        assert row["acceptance"]["state"] == "MANUAL-PENDING"
        assert row["acceptance"]["hardware_verified"] is False
        assert row["ci"]["state"] == "partial"
    assert all(row["acceptance"]["state"] == "MANUAL-PENDING"
               for row in matrix["targets"] if not row["target_id"].startswith("windows-x86"))
    markdown = (reports / "matrix.md").read_text(encoding="utf-8")
    assert "MANUAL-PENDING" in markdown and "CI is never hardware support" in markdown
    # deterministic output
    second = _run(root, "matrix", "--records-dir", str(root / "docs" / "evidence" / "beta_acceptance"),
                  "--json-out", str(reports / "matrix2.json"), "--json")
    assert second.returncode == 0
    assert (reports / "matrix.json").read_bytes() == (reports / "matrix2.json").read_bytes()


def test_full_record_can_verify_only_that_target_not_others(tmp_path):
    root = _fixture_repo(tmp_path)
    records = root / "docs" / "evidence" / "beta_acceptance"
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(_record()), encoding="utf-8")
    stored = _run(root, "record", "--input", str(record_path), "--records-dir", str(records), "--json")
    assert stored.returncode == 0, stored.stderr
    assert json.loads(stored.stdout)["state"] == "verified"
    matrix = json.loads(_run(root, "matrix", "--records-dir", str(records), "--json").stdout)
    windows = next(row for row in matrix["targets"] if row["target_id"] == "windows-x86_64")
    assert windows["acceptance"]["state"] == "verified"
    assert windows["acceptance"]["hardware_verified"] is True
    assert all(row["acceptance"]["state"] == "MANUAL-PENDING"
               for row in matrix["targets"] if row["target_id"] != "windows-x86_64")
    assert matrix["summary"]["verified"] == 1
    assert matrix["summary"]["manual_pending"] == 5


def test_record_validation_rejects_missing_checksum_target_and_hardware_claims(tmp_path):
    root = _fixture_repo(tmp_path)
    records = root / "docs" / "evidence" / "beta_acceptance"
    cases = []
    bad_sha = _record()
    bad_sha["package"]["sha256"] = ""
    cases.append(bad_sha)
    bad_target = _record(target="windows-x86_64")
    bad_target["target_id"] = "android-arm64"
    cases.append(bad_target)
    mismatch = _record(target="windows-x86_64")
    mismatch["arch"] = "arm64"
    cases.append(mismatch)
    missing_step = _record()
    del missing_step["steps"]["mic"]
    cases.append(missing_step)
    hardware_claim = _record(hardware_pass=False, support_claimed=True)
    cases.append(hardware_claim)
    for index, payload in enumerate(cases):
        path = tmp_path / ("bad-" + str(index) + ".json")
        path.write_text(json.dumps(payload), encoding="utf-8")
        completed = _run(root, "record", "--input", str(path), "--records-dir", str(records))
        assert completed.returncode == 2, (index, completed.stdout, completed.stderr)
    assert not list(records.glob("*.json"))
    verify = _run(root, "verify", "--records-dir", str(records), "--json")
    assert verify.returncode == 0
    assert json.loads(verify.stdout)["records"] == 0


def test_record_redacts_personal_paths_and_rejects_identity_alias(tmp_path):
    root = _fixture_repo(tmp_path)
    records = root / "docs" / "evidence" / "beta_acceptance"
    payload = _record()
    payload["evidence_notes"] = (r"Installed from C:\Users\Alice\Downloads\bundle "
                                 r"and /home/alice/artifacts; log at K:\\AI\\private")
    path = tmp_path / "privacy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    completed = _run(root, "record", "--input", str(path), "--records-dir", str(records), "--json")
    assert completed.returncode == 0, completed.stderr
    stored = json.loads(next(records.glob("*.json")).read_text(encoding="utf-8"))
    serialized = json.dumps(stored)
    assert "Alice" not in serialized and "alice" not in serialized
    assert "K:\\\\AI\\\\private" not in serialized
    assert "<redacted-path>" in serialized

    identity = _record(alias="alice@example.com")
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(json.dumps(identity), encoding="utf-8")
    rejected = _run(root, "record", "--input", str(identity_path), "--records-dir", str(records))
    assert rejected.returncode == 2
    assert "alias" in rejected.stderr.lower()


def test_verify_reports_invalid_records_and_script_has_no_network_or_publish():
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("urllib", "requests", "http.client", "socket", "git push",
                      "gh release", "gh api", "http://", "https://"):
        assert forbidden not in source.lower(), forbidden
    docs = (REPO / "docs" / "08_ACCEPTANCE_GATES.md").read_text(encoding="utf-8")
    assert "MANUAL-PENDING" in docs
    assert "no support" in docs.lower() or "not a support claim" in docs.lower()
    assert "tester alias" in docs.lower() or "alias" in docs.lower()


def test_beta_acceptance_docs_cover_commands_privacy_and_records():
    docs = (REPO / "docs" / "08_ACCEPTANCE_GATES.md").read_text(encoding="utf-8")
    for expected in ("scripts/release_acceptance.py", "matrix", "record", "verify",
                     "target", "sha256", "privacy", "MANUAL-PENDING"):
        assert expected.lower() in docs.lower(), expected

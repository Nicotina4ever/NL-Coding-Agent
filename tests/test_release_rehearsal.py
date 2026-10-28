"""Tests for the synthetic end-to-end release-pipeline rehearsal (no network)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.rehearse_release as rehearsal  # noqa: E402

SCRIPT = REPO_ROOT / "scripts" / "rehearse_release.py"
CANONICAL = (
    "installer/runtime_manifest.json",
    "installer/platform_manifest.json",
    "installer/runtime_sources.json",
)


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_rehearsal(report_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen"})
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--report-dir", str(report_dir)],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )


class ReleaseRehearsalTests(unittest.TestCase):
    def test_full_rehearsal_passes_with_synthetic_flag_and_six_targets(self):
        canonical_before = {name: _sha(REPO_ROOT / name) for name in CANONICAL}
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "reports"
            completed = _run_rehearsal(report_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            report = json.loads(completed.stdout)
            self.assertTrue(report["synthetic_rehearsal"])
            self.assertEqual(report["status"], "PASS")
            self.assertIn("NOT A RELEASE", report["synthetic_notice"])
            self.assertEqual([item["name"] for item in report["stages"]],
                             list(rehearsal.STAGE_NAMES))
            self.assertTrue(all(item["status"] == "PASS" for item in report["stages"]))
            facts = report["facts"]
            self.assertEqual(sorted(facts["synthetic_targets"]), sorted(rehearsal.TARGETS))
            self.assertTrue(facts["draft"]["release_ready"])
            self.assertTrue(facts["candidate_manifests"]["runtime_release_ready"])
            self.assertTrue(facts["candidate_manifests"]["platform_release_ready"])
            self.assertEqual(facts["beta_package"]["targets"], 6)
            self.assertEqual(facts["provisioning"]["targets"], 6)
            self.assertTrue(all(item["verified"] for item in
                                facts["provisioning"]["installed"].values()))
            self.assertEqual(facts["provisioning"]["cache_artifacts"], 6)
            self.assertEqual(facts["acceptance"]["targets"], 6)
            self.assertEqual(facts["acceptance"]["valid_records"], 1)
            self.assertEqual(facts["acceptance"]["windows_record_count"], 1)
            self.assertEqual(facts["acceptance"]["windows_state"], "MANUAL-PENDING")
            self.assertEqual(facts["acceptance"]["summary"]["verified"], 0)
            self.assertTrue(facts["acceptance"]["no_ci_hardware_claim"])
            self.assertFalse(facts["acceptance"]["record_committed"])
            self.assertTrue(facts["canonical_manifests_unchanged"])
            self.assertTrue(facts["workspace_cleaned"])
            self.assertEqual(report["workspace"], {"managed": True, "cleaned": True})
            self.assertEqual({path.name for path in report_dir.iterdir()},
                             {"release_rehearsal.json", "release_rehearsal.md"})
            markdown = (report_dir / "release_rehearsal.md").read_text(encoding="utf-8")
            self.assertIn("NOT A RELEASE", markdown)
            self.assertIn("Synthetic release-pipeline rehearsal", markdown)
            self.assertIn("| Stage | Status | Detail |", markdown)
            self.assertIn(facts["acceptance"]["windows_state"], markdown)
            self.assertEqual(canonical_before,
                             {name: _sha(REPO_ROOT / name) for name in CANONICAL})

    def test_report_has_no_temp_paths_or_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "reports"
            completed = _run_rehearsal(report_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            report = json.loads(completed.stdout)
            text = json.dumps(report, sort_keys=True)
            markdown = (report_dir / "release_rehearsal.md").read_text(encoding="utf-8")
            for needle in (str(REPO_ROOT), str(report_dir), "AppData", "nl-release-rehearsal-"):
                self.assertNotIn(needle, text)
                self.assertNotIn(needle, markdown)
            timestamp = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T")
            self.assertIsNone(timestamp.search(text))
            self.assertIsNone(timestamp.search(markdown))

    def test_happy_path_writes_only_report_files_outside_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "reports"
            before = sorted(path.as_posix() for path in REPO_ROOT.iterdir())
            completed = _run_rehearsal(report_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            after = sorted(path.as_posix() for path in REPO_ROOT.iterdir())
            self.assertEqual(before, after, "rehearsal created files in the repository")
            self.assertEqual({path.name for path in report_dir.iterdir()},
                             {"release_rehearsal.json", "release_rehearsal.md"})
            report = json.loads((report_dir / "release_rehearsal.json").read_text(
                encoding="utf-8"))
            self.assertTrue(report["workspace"]["cleaned"])
            leftovers = list(Path(tempfile.gettempdir()).glob("nl-release-rehearsal-*"))
            self.assertEqual(leftovers, [])

    def test_corrupt_synthetic_archive_reports_failure_and_cleans_workspace(self):
        canonical_before = {name: _sha(REPO_ROOT / name) for name in CANONICAL}
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            result = rehearsal.run_rehearsal(
                workspace, corrupt_targets=("windows-x86_64",))
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(result["synthetic_rehearsal"])
            stages = {item["name"]: item for item in result["stages"]}
            self.assertEqual(stages["synthetic_runtime_fixtures"]["status"], "PASS")
            self.assertEqual(stages["fetch_native_runtimes_offline_measure"]["status"],
                             "FAIL")
            self.assertEqual(stages["measured_draft_validation"]["status"], "SKIPPED")
            self.assertTrue(result["failures"])
            self.assertIn("fetch_native_runtimes_offline_measure", result["failures"][0])
            self.assertFalse(workspace.exists(), "workspace must be cleaned after failure")
            self.assertEqual(canonical_before,
                             {name: _sha(REPO_ROOT / name) for name in CANONICAL})

    def test_six_target_fixture_coverage_and_archive_kinds(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixtures = rehearsal._create_synthetic_archives(Path(tmp))
            self.assertEqual(sorted(fixtures["targets"]), sorted(rehearsal.TARGETS))
            for target_id, facts in fixtures["targets"].items():
                descriptor = rehearsal.release_builder.SUPPORTED_TARGETS[target_id]
                self.assertEqual(facts["archive_kind"], descriptor["archive"])
                self.assertTrue(facts["bytes"] > 0)
                self.assertEqual(len(facts["sha256"]), 64)
                path = fixtures["archives"][target_id]
                self.assertTrue(path.is_file())
                if descriptor["os"] == "windows":
                    self.assertTrue(path.name.endswith(".zip"))
                else:
                    self.assertTrue(path.name.endswith(".tar.gz"))

    def test_static_guards_no_network_model_or_upload(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("import urllib", "import requests", "import socket",
                          "http.client", "subprocess", "os.system(",
                          "pip install", "curl ", "wget ", "git clone",
                          "ollama", "model.run", "upload(", "publish(",
                          "http://", "https://"):
            self.assertNotIn(forbidden, source, "forbidden token in rehearsal: " + forbidden)
        self.assertIn("synthetic_rehearsal", source)
        self.assertIn("NOT A RELEASE", source)
        self.assertIn("runtime_fetch.main", source)
        self.assertIn("build_release", source)
        self.assertIn("build_beta_package", source)
        self.assertIn("provision.provision_install", source)
        self.assertIn("acceptance.build_matrix", source)


if __name__ == "__main__":
    unittest.main()

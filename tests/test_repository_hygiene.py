"""Tests for the read-only repository hygiene audit (stage 5)."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_repository_hygiene.py"
spec = importlib.util.spec_from_file_location("audit_repository_hygiene", SCRIPT)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit)

BS = chr(92)


def snapshot_tree(root: Path) -> dict:
    entries: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            entries[rel] = ("dir",)
        else:
            data = path.read_bytes()
            entries[rel] = ("file", len(data), hashlib.sha256(data).hexdigest())
    return entries


class AuditFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.build_repository()

    def write(self, rel: str, text: str = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        return path

    def write_bytes(self, rel: str, data: bytes) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def sha(self, rel: str) -> str:
        return hashlib.sha256((self.root / rel).read_bytes()).hexdigest()

    def old_root(self) -> str:
        return "K:" + BS + "AI" + BS + "Coding Agent"

    def build_repository(self) -> None:
        self.write("nl_coding_agent/__init__.py", "package" + chr(10))
        cli_source = (
            "import argparse" + chr(10)
            + "parser = argparse.ArgumentParser()" + chr(10)
            + "sub = parser.add_subparsers()" + chr(10)
            + "sub.add_parser(\"gui\")" + chr(10)
            + "sub.add_parser(\"doctor\")" + chr(10)
        )
        self.write("nl_coding_agent/cli.py", cli_source)
        self.write("nl_coding_agent/core/a.py", "VALUE = 1" + chr(10))
        self.write("tests/__init__.py", "")
        self.write("tests/test_x.py", "def test_x():" + chr(10) + "    assert True" + chr(10))
        self.write("tests/test_relocation.py", "OLD = '" + self.old_root() + "'" + chr(10))
        self.write("docs/guide.md", "guide" + chr(10))
        self.write("docs/COMPLETED_MISSIONS.md", "old root " + self.old_root() + chr(10))
        self.write("docs/PHASE4_CREWAI_FLOWS_PLAN.md", "stage4 plan" + chr(10))
        self.write("docs/dup_a.md", "same duplicate content" + chr(10))
        self.write("docs/dup_b.md", "same duplicate content" + chr(10))
        self.write("config/models.yaml", "roles:" + chr(10) + "  developer:" + chr(10) + "    model: demo" + chr(10))
        self.write("config/voicebridge.yaml", "project:" + chr(10) + "  name: demo" + chr(10))
        self.write("assets/logo.svg", "<svg></svg>" + chr(10))
        self.write_bytes("python/python.exe", b"MZfakeexe")
        self.write_bytes("python/python312.zip", b"zipdata")
        self.write_bytes("python/python312.dll", b"dll")
        self.write("python/Lib/site-packages/crewai/__init__.py", "crewai" + chr(10))
        self.write("python/Lib/site-packages/crewai/__pycache__/x.pyc", "pyc")
        self.write("data/history.json", "{}" + chr(10))
        self.write(".workspace/logs/app.log", "log" + chr(10))
        self.write("crewAI/README.md", "vendor" + chr(10))
        self.write("crewAI/.git/config", "gitdir" + chr(10))
        self.write("crewAI-tools/placeholder.txt", "vendor tools" + chr(10))
        self.write(".workspace/dist/portable-release/nl_agent.py", "launcher" + chr(10))
        self.write(".workspace/dist/portable-release/nl_coding_agent/__init__.py", "packaged" + chr(10))
        self.write_bytes(".workspace/dist/portable-release/python/python.exe", b"MZfakeexe")
        self.write_bytes(".workspace/dist/portable-release/python/python312.zip", b"zipdata")
        self.write_bytes(".workspace/dist/portable-release/python/python312.dll", b"dll")
        self.write(".workspace/dist/portable-release/python/Lib/site-packages/crewai/__init__.py", "crewai" + chr(10))
        self.write(".workspace/dist/portable-release/payload_manifest.json",
                   json.dumps({"source": self.old_root(), "output": "x"}))
        self.write(".workspace/build/phase4/CREWAI_FLOWS_PLAN.md", "stage4 plan" + chr(10))
        self.write(".workspace/build/portable_plan.json", json.dumps({"source": self.old_root()}))
        self.write(".workspace/build/audit_payload_db.py", "print('scratch')" + chr(10))
        self.write(".workspace/build/relocation/audit.md", "evidence" + chr(10))
        self.write("PATCH/nl_coding_agent/core/a.py", "VALUE = 1" + chr(10))
        self.write("PATCH/README.md", "patch readme" + chr(10))
        self.write("__pycache__/x.pyc", "pyc")
        self.write(".pytest_cache/README.md", "cache")
        self.write("%SystemDrive%/ProgramData/cache.db", "junk")
        self.write("nl_agent.py", "print('launcher')" + chr(10))
        self.write(".gitignore", "python/" + chr(10) + "crewAI/" + chr(10) + ".workspace/" + chr(10)
                   + "dist/" + chr(10) + "build/" + chr(10) + "data/" + chr(10)
                   + "logs/" + chr(10) + "__pycache__/" + chr(10))
        self.write("pyproject.toml",
                   "[project]" + chr(10) + "name = \"demo\"" + chr(10)
                   + "requires-python = \">=3.12\"" + chr(10)
                   + "dependencies = [\"demo-dep==1.2.3\"]" + chr(10))
        launcher = ("@echo off" + chr(10) + "cd /d \"%~dp0\"" + chr(10)
                    + "python" + BS + "python.exe \"%~dp0nl_agent.py\" gui" + chr(10))
        self.write("NL Coding Agent.bat", launcher)
        self.write("temp_fix.py", "print('temp')" + chr(10))
        self.write("FOUNDATION_CHANGES.patch", "--- a" + chr(10) + "+++ b" + chr(10))
        self.write("scripts/check.py", "OLD = '" + self.old_root() + "'" + chr(10))
        self.write("README.txt", "readme" + chr(10))
        manifest = {"nl_coding_agent/core/a.py": self.sha("nl_coding_agent/core/a.py")}
        self.write("SHA256_MANIFEST.json", json.dumps(manifest))

    def run_audit(self, **kwargs) -> dict:
        options = {"dependency_versions": {"demo-dep": "1.2.3"}, "worktree_text": ""}
        options.update(kwargs)
        return audit.audit_repository(self.root, **options)

    def area(self, report: dict, name: str) -> dict:
        for item in report["areas"]:
            if item["name"] == name:
                return item
        self.fail("area not found: " + name)


class ReadOnlyAndDeterminismTests(AuditFixture):
    def test_audit_is_read_only(self):
        before = snapshot_tree(self.root)
        report = self.run_audit()
        after = snapshot_tree(self.root)
        self.assertEqual(after, before)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["actions_taken"], [])

    def test_audit_is_deterministic_except_timestamp(self):
        first = self.run_audit()
        second = self.run_audit()
        first.pop("generated_at")
        second.pop("generated_at")
        first["totals"].pop("elapsed_seconds")
        second["totals"].pop("elapsed_seconds")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_cli_writes_json_and_markdown_outside_repository(self):
        before = snapshot_tree(self.root)
        json_path = self.base / "out" / "audit.json"
        markdown_path = self.base / "out" / "audit.md"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = audit.main([
                "--root", str(self.root),
                "--json-out", str(json_path),
                "--markdown-out", str(markdown_path),
                "--quiet",
            ])
        self.assertEqual(code, 0)
        self.assertTrue(json_path.is_file())
        self.assertTrue(markdown_path.is_file())
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], audit.SCHEMA_VERSION)
        markdown = markdown_path.read_text(encoding="utf-8")
        for heading in ("# Repository hygiene audit", "## Summary", "## Areas",
                        "## Recommendations", "## Validation plan for approved changes"):
            self.assertIn(heading, markdown)
        self.assertIn("SAFE", markdown)
        self.assertIn("NEEDS-AUTHORIZATION", markdown)
        self.assertIn("DO-NOT-TOUCH", markdown)
        self.assertEqual(snapshot_tree(self.root), before)


class AreaAndCacheTests(AuditFixture):
    def test_areas_counts_and_protection_classes(self):
        report = self.run_audit()
        self.assertGreater(report["totals"]["files"], 20)
        self.assertGreater(report["totals"]["bytes"], 0)
        self.assertFalse(report["totals"]["truncated"])
        source = self.area(report, "nl_coding_agent")
        self.assertEqual((source["kind"], source["classification"]), ("source", "source"))
        self.assertEqual(self.area(report, "data")["classification"], "protected")
        self.assertEqual(self.area(report, ".workspace/logs")["classification"], "protected")
        self.assertEqual(self.area(report, "python")["classification"], "protected")
        self.assertEqual(self.area(report, "crewAI")["classification"], "protected")
        self.assertEqual(self.area(report, ".workspace/dist")["classification"], "protected")
        self.assertEqual(self.area(report, "%SystemDrive%")["classification"], "safe")
        self.assertEqual(self.area(report, ".workspace/build")["classification"], "evidence")

    def test_caches_separate_repository_candidates_from_runtime_caches(self):
        report = self.run_audit()
        caches = report["caches"]
        paths = {item["path"] for item in caches["repo_cleanup_candidates"]}
        self.assertIn("__pycache__", paths)
        self.assertIn(".pytest_cache", paths)
        runtime_entries = [item for item in caches["entries"]
                           if item["path"].startswith("python/")]
        self.assertTrue(runtime_entries)
        self.assertTrue(all(item["protected"] for item in runtime_entries))
        self.assertGreater(caches["repo_cleanup_bytes"], 0)

    def test_max_files_bound_marks_truncation(self):
        report = self.run_audit(bounds={"max_files": 2})
        self.assertTrue(report["totals"]["truncated"])


class DuplicateTests(AuditFixture):
    def test_duplicates_detect_patch_build_and_generic_groups(self):
        report = self.run_audit()
        groups = report["duplicates"]["groups"]
        by_paths = {tuple(group["paths"]): group for group in groups}
        patch_group = by_paths.get(("PATCH/nl_coding_agent/core/a.py", "nl_coding_agent/core/a.py"))
        self.assertIsNotNone(patch_group)
        self.assertEqual(patch_group["classification"], "NEEDS-AUTHORIZATION")
        build_evidence = [item for item in report["obsolete"]
                          if item["kind"] == "duplicate-build-evidence"]
        self.assertEqual(len(build_evidence), 1)
        self.assertEqual(build_evidence[0]["path"],
                         ".workspace/build/phase4/CREWAI_FLOWS_PLAN.md")
        self.assertEqual(build_evidence[0]["classification"], "SAFE")
        generic = by_paths.get(("docs/dup_a.md", "docs/dup_b.md"))
        self.assertIsNotNone(generic)
        self.assertEqual(generic["classification"], "NEEDS-AUTHORIZATION")
        self.assertGreater(report["duplicates"]["hashed_files"], 5)
        self.assertFalse(report["duplicates"]["truncated"])

    def test_hash_bounds_skip_large_files(self):
        report = self.run_audit(bounds={"max_hash_bytes": 10})
        self.assertGreaterEqual(report["duplicates"]["skipped_large_files"], 1)
        paths = [path for group in report["duplicates"]["groups"] for path in group["paths"]]
        self.assertNotIn("docs/dup_a.md", paths)


class ObsoleteAndStaleTests(AuditFixture):
    def test_obsolete_candidates_and_recommendation_classes(self):
        report = self.run_audit()
        kinds = {(item["kind"], item["classification"]) for item in report["obsolete"]}
        self.assertIn(("temp-repair-script", "NEEDS-AUTHORIZATION"), kinds)
        self.assertIn(("applied-patch-artifact", "NEEDS-AUTHORIZATION"), kinds)
        self.assertIn(("applied-patch-copy-dir", "NEEDS-AUTHORIZATION"), kinds)
        self.assertIn(("accidental-path-tree", "SAFE"), kinds)
        self.assertIn(("repository-cache", "SAFE"), kinds)
        self.assertIn(("duplicate-build-evidence", "SAFE"), kinds)
        self.assertIn(("stale-generated-metadata", "NEEDS-AUTHORIZATION"), kinds)
        self.assertIn(("stray-build-script", "NEEDS-AUTHORIZATION"), kinds)
        self.assertIn(("stale-portable-release", "DO-NOT-TOUCH"), kinds)
        self.assertIn(("vendor-checkout-metadata", "DO-NOT-TOUCH"), kinds)
        recs = report["recommendations"]
        classes = {item["classification"] for item in recs}
        self.assertEqual(classes, {"SAFE", "NEEDS-AUTHORIZATION", "DO-NOT-TOUCH"})
        ids = {item["id"] for item in recs}
        self.assertIn("H-01", ids)
        self.assertIn("H-09", ids)
        self.assertIn("H-11", ids)

    def test_stale_path_classification_and_counts(self):
        report = self.run_audit()
        stale = report["stale_paths"]
        paths = {match["path"]: match for match in stale["matches"]}
        self.assertEqual(paths["scripts/check.py"]["classification"], "NEEDS-AUTHORIZATION")
        self.assertEqual(paths["docs/COMPLETED_MISSIONS.md"]["classification"], "DO-NOT-TOUCH")
        self.assertEqual(paths["tests/test_relocation.py"]["classification"], "DO-NOT-TOUCH")
        self.assertGreaterEqual(stale["counts_by_pattern"].get("old_root", 0), 3)
        operational = stale["counts_by_classification"].get("NEEDS-AUTHORIZATION", 0)
        self.assertGreaterEqual(operational, 1)

    def test_stale_worktree_detection_uses_injected_registration(self):
        stale_dir = self.base / "stale-worktree"
        stale_dir.mkdir()
        (stale_dir / "file.txt").write_text("x", encoding="utf-8")
        missing_dir = self.base / "missing-worktree"
        registration = (
            "worktree " + str(self.root) + chr(10)
            + "HEAD abc123" + chr(10)
            + "branch refs/heads/master" + chr(10) + chr(10)
            + "worktree " + str(stale_dir) + chr(10)
            + "HEAD def456" + chr(10)
            + "detached" + chr(10) + chr(10)
            + "worktree " + str(missing_dir) + chr(10)
            + "HEAD 0000" + chr(10)
            + "detached" + chr(10)
        )
        report = self.run_audit(worktree_text=registration)
        self.assertEqual(report["worktrees"]["registered_count"], 3)
        self.assertEqual(report["worktrees"]["stale_count"], 2)
        kinds = [item["kind"] for item in report["obsolete"]]
        self.assertIn("stale-git-worktree", kinds)
        stale_entries = [item for item in report["obsolete"] if item["kind"] == "stale-git-worktree"]
        self.assertTrue(all(item["classification"] == "NEEDS-AUTHORIZATION" for item in stale_entries))

    def test_parse_worktrees_handles_blocks(self):
        text = (
            "worktree C:/repo" + chr(10) + "HEAD abc" + chr(10) + "branch refs/heads/master" + chr(10)
            + chr(10) + "worktree C:/tmp/wt" + chr(10) + "HEAD def" + chr(10) + "detached" + chr(10)
        )
        parsed = audit.parse_worktrees(text)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["branch"], "refs/heads/master")
        self.assertTrue(parsed[1]["detached"])
        self.assertEqual(parsed[1]["path"], "C:/tmp/wt")


class ValidationTests(AuditFixture):
    def test_launcher_references_and_cli_commands_pass(self):
        report = self.run_audit()
        checks = {item["check"]: item for item in report["validations"]["checks"]}
        launcher = checks["launcher.NL Coding Agent.bat"]
        self.assertEqual(launcher["status"], "PASS", launcher["detail"])

    def test_launcher_missing_reference_fails(self):
        self.write("NL Coding Agent.bat",
                   "@echo off" + chr(10) + "python" + BS + "missing.exe nl_agent.py gui" + chr(10))
        report = self.run_audit()
        checks = {item["check"]: item for item in report["validations"]["checks"]}
        self.assertEqual(checks["launcher.NL Coding Agent.bat"]["status"], "FAIL")

    def test_launcher_unknown_command_fails(self):
        self.write("NL Coding Agent.bat",
                   "@echo off" + chr(10) + "python" + BS + "python.exe nl_agent.py nosuchcommand" + chr(10))
        report = self.run_audit()
        checks = {item["check"]: item for item in report["validations"]["checks"]}
        self.assertEqual(checks["launcher.NL Coding Agent.bat"]["status"], "FAIL")

    def test_dependency_pin_validation(self):
        report = self.run_audit()
        checks = {item["check"]: item for item in report["validations"]["checks"]}
        self.assertEqual(checks["dependency.demo-dep"]["status"], "PASS")
        mismatch = self.run_audit(dependency_versions={"demo-dep": "9.9.9"})
        checks = {item["check"]: item for item in mismatch["validations"]["checks"]}
        self.assertEqual(checks["dependency.demo-dep"]["status"], "FAIL")
        missing = self.run_audit(dependency_versions={})
        checks = {item["check"]: item for item in missing["validations"]["checks"]}
        self.assertEqual(checks["dependency.demo-dep"]["status"], "FAIL")

    def test_sha256_manifest_validation(self):
        report = self.run_audit()
        checks = {item["check"]: item for item in report["validations"]["checks"]}
        self.assertEqual(checks["manifest.sha256"]["status"], "PASS")
        self.write("nl_coding_agent/core/a.py", "VALUE = 2" + chr(10))
        tampered = self.run_audit()
        checks = {item["check"]: item for item in tampered["validations"]["checks"]}
        self.assertEqual(checks["manifest.sha256"]["status"], "FAIL")

    def test_dist_payload_manifest_stale_source_warns(self):
        report = self.run_audit()
        checks = {item["check"]: item for item in report["validations"]["checks"]}
        self.assertEqual(checks["manifest.dist_payload"]["status"], "WARN")
        self.assertIn("stale", checks["manifest.dist_payload"]["detail"])


class SafetyStaticTests(unittest.TestCase):
    def test_script_has_no_network_or_destructive_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "urllib", "requests.", "http://", "https://", "socket.",
            "os.remove", "os.unlink", "os.rename", "os.replace",
            "shutil.rmtree", ".unlink(",
        ):
            self.assertNotIn(forbidden, source, "forbidden token in audit script: " + forbidden)

    def test_default_reports_live_under_workspace_build(self):
        self.assertEqual(str(audit.DEFAULT_JSON).replace(chr(92), "/"),
                         ".workspace/build/phase5/repository_hygiene.json")
        self.assertEqual(str(audit.DEFAULT_MD).replace(chr(92), "/"),
                         ".workspace/build/phase5/repository_hygiene.md")


if __name__ == "__main__":
    unittest.main()

"""Tests for the reproducible source-only release builder (no network, temp fixtures)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer import operations  # noqa: E402
from installer.platform_manifest import load_manifest, validate_manifest  # noqa: E402
import scripts.build_release as release  # noqa: E402

NL = chr(10)
HEAD = "0123456789abcdef0123456789abcdef01234567"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_file(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def make_source(root: Path, version: str = "0.3.1") -> list[str]:
    files = {
        "nl_agent.py": b"print('app')" + NL.encode(),
        "nl_coding_agent/__init__.py": b"package" + NL.encode(),
        "nl_coding_agent/core/version.py": ("APP_VERSION = '" + version + "'" + NL).encode(),
        "nl_coding_agent/core/app.py": b"VALUE = 1" + NL.encode(),
        "docs/README.md": b"documentation" + NL.encode(),
        "tests/test_app.py": b"def test_app():" + NL.encode() + b"    assert True" + NL.encode(),
        "scripts/tool.py": b"print('tool')" + NL.encode(),
        "assets/logo.svg": b"<svg></svg>" + NL.encode(),
        "config/models.yaml": b"roles: {}" + NL.encode(),
        ".gitignore": b"data/" + NL.encode(),
        "NL Coding Agent.bat": b"@echo off" + NL.encode(),
        "data/user.sqlite3": b"user data",
        "logs/app.log": b"log line",
        "dist/portable-release/old.txt": b"old payload",
        "build/cache.txt": b"build cache",
        "python/python.exe": b"MZ fake exe",
        "crewAI/vendor.md": b"vendor",
        "PATCH/applied.py": b"patch",
        "temp_restore.py": b"print('temp')" + NL.encode(),
        "FOUNDATION_CHANGES.patch": b"diff",
        "config/voicebridge.yaml": b"project: {}" + NL.encode(),
        "nl_coding_agent/__pycache__/x.pyc": b"pyc",
        "SHA256_MANIFEST.json": b"{}",
    }
    for rel, data in files.items():
        write_file(root, rel, data)
    write_file(root, "untracked_secret.txt", b"must never be packaged")
    return sorted(files)


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    return buffer.getvalue()


class ReleaseFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "src"
        self.source.mkdir()
        self.tracked = make_source(self.source)

    def build(self, output_parent: Path | None = None, **kwargs) -> dict:
        parent = output_parent or (self.root / "out-a")
        options = {"tracked": self.tracked, "head": HEAD}
        options.update(kwargs)
        return release.build_release(self.source, parent, **options)

    def candidate_files(self, candidate: str | Path) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        for path in sorted(Path(candidate).rglob("*")):
            if path.is_file():
                result[path.relative_to(candidate).as_posix()] = path.read_bytes()
        return result


class ReproducibilityTests(ReleaseFixture):
    def test_two_builds_are_byte_identical(self):
        first = self.build(self.root / "out-a")
        second = self.build(self.root / "out-b")
        self.assertEqual(first["status"], "built")
        self.assertEqual(Path(first["candidate"]).name, Path(second["candidate"]).name)
        files_a = self.candidate_files(first["candidate"])
        files_b = self.candidate_files(second["candidate"])
        self.assertEqual(sorted(files_a), sorted(files_b))
        for name in files_a:
            self.assertEqual(files_a[name], files_b[name], "non-deterministic file: " + name)

    def test_plan_writes_nothing(self):
        before = sorted(path.as_posix() for path in self.source.rglob("*"))
        out = self.root / "plan-out"
        plan = release.build_release(self.source, out, tracked=self.tracked, head=HEAD,
                                     plan=True)
        after = sorted(path.as_posix() for path in self.source.rglob("*"))
        self.assertEqual(before, after)
        self.assertFalse(out.exists())
        self.assertEqual(plan["status"], "plan")
        self.assertEqual(plan["git_head"], HEAD)
        self.assertGreater(plan["tracked_files"], 5)
        self.assertEqual(plan["writes"], [])

    def test_existing_candidate_is_refused_and_untouched(self):
        first = self.build(self.root / "out-a")
        marker = Path(first["candidate"]) / "keep-me.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(release.ReleaseError):
            self.build(self.root / "out-a")
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


class ManifestTests(ReleaseFixture):
    def test_release_manifest_is_complete_and_excludes_unsafe_paths(self):
        result = self.build()
        candidate = Path(result["candidate"])
        manifest = json.loads((candidate / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["product"]["version"], "0.3.1")
        self.assertEqual(manifest["source"]["git_head"], HEAD)
        self.assertEqual(manifest["archive"]["file_count"], len(manifest["files"]))
        self.assertEqual(manifest["archive"]["sha256"],
                         sha256_bytes((candidate / manifest["archive"]["name"]).read_bytes()))
        paths = {entry["path"] for entry in manifest["files"]}
        for included in ("nl_agent.py", "nl_coding_agent/core/app.py",
                         "docs/README.md", "tests/test_app.py"):
            self.assertIn(included, paths)
        for excluded in ("data/user.sqlite3", "logs/app.log", "dist/portable-release/old.txt",
                         "build/cache.txt", "python/python.exe", "crewAI/vendor.md",
                         "PATCH/applied.py", "temp_restore.py", "FOUNDATION_CHANGES.patch",
                         "config/voicebridge.yaml", "nl_coding_agent/__pycache__/x.pyc",
                         "SHA256_MANIFEST.json", "untracked_secret.txt"):
            self.assertNotIn(excluded, paths)
        for entry in manifest["files"]:
            source_bytes = (self.source / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], sha256_bytes(source_bytes))
            self.assertEqual(entry["size"], len(source_bytes))
        with zipfile.ZipFile(candidate / manifest["archive"]["name"]) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, paths)
            for info in archive.infolist():
                self.assertEqual(info.date_time, release.FIXED_ZIP_DATE)
                self.assertEqual(info.create_system, 3)
        self.assertIn("windows-x86_64", manifest["platforms"])
        self.assertIn("linux-x86_64", manifest["platforms"])

    def test_platform_manifest_is_installer_compatible_and_offline_installable(self):
        result = self.build()
        candidate = Path(result["candidate"])
        platform_manifest = load_manifest(candidate / "platform-manifest.json")
        self.assertTrue(platform_manifest["release_ready"])
        components = {item["id"]: item for item in platform_manifest["components"]}
        self.assertIn("app-source", components)
        app_component = components["app-source"]
        self.assertEqual(app_component["sha256"],
                         sha256_bytes((candidate / app_component["url"]).read_bytes()))
        runtime_component = platform_manifest["platforms"]["windows-x86_64"]["runtime_component"]
        self.assertEqual(components[runtime_component]["kind"], "runtime")
        self.assertTrue(components[runtime_component]["optional"])
        target = self.root / "installed"
        cache = self.root / "cache"
        install_result = operations.install(
            platform_manifest, target, cache_dir=cache, offline_bundle=candidate,
            platform_id="windows-x86_64",
        )
        self.assertEqual(install_result["status"], "installed")
        self.assertEqual((target / "nl_agent.py").read_bytes(),
                         (self.source / "nl_agent.py").read_bytes())
        self.assertTrue(operations.verify_install(target)["ok"])

    def test_source_only_build_never_copies_python_or_vendor(self):
        result = self.build()
        candidate = Path(result["candidate"])
        manifest = json.loads((candidate / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertIsNone(manifest["runtime"])
        self.assertFalse((candidate / "python").exists())
        self.assertFalse((candidate / "crewAI").exists())
        with zipfile.ZipFile(candidate / manifest["archive"]["name"]) as archive:
            for name in archive.namelist():
                self.assertFalse(name.startswith("python/"), name)
                self.assertFalse(name.startswith("crewAI/"), name)

    def test_version_comes_from_version_file(self):
        write_file(self.source, "nl_coding_agent/core/version.py",
                   b"APP_VERSION = '9.9.9'" + NL.encode())
        result = self.build()
        manifest = json.loads((Path(result["candidate"]) / "release-manifest.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(manifest["product"]["version"], "9.9.9")
        self.assertEqual(release.read_version(self.source), "9.9.9")


class RuntimeTests(ReleaseFixture):
    def test_with_runtime_archive_bundles_referenced_zip(self):
        runtime_bytes = zip_bytes({"python.exe": b"MZ runtime", "Lib/x.py": b"x = 1"})
        runtime_path = self.root / "python-runtime.zip"
        runtime_path.write_bytes(runtime_bytes)
        result = self.build(self.root / "out-runtime", runtime_archive=runtime_path,
                            runtime_platform="windows-x86_64",
                            runtime_version="3.12.10")
        candidate = Path(result["candidate"])
        manifest = json.loads((candidate / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(result["runtime_bundled"])
        self.assertIsNotNone(manifest["runtime"])
        platform_manifest = load_manifest(candidate / "platform-manifest.json")
        components = {item["id"]: item for item in platform_manifest["components"]}
        runtime_component = components["python-runtime-windows-x86_64"]
        self.assertEqual(runtime_component["sha256"], sha256_bytes(runtime_bytes))
        self.assertEqual(runtime_component["size"], len(runtime_bytes))
        self.assertFalse(runtime_component["optional"])
        self.assertEqual(platform_manifest["platforms"]["windows-x86_64"]["components"][0],
                         "python-runtime-windows-x86_64")
        self.assertEqual(platform_manifest["platforms"]["linux-x86_64"]["components"],
                         ["app-source"])
        self.assertTrue((candidate / "runtime" / runtime_path.name).is_file())
        target = self.root / "runtime-installed"
        install_result = operations.install(
            platform_manifest, target, cache_dir=self.root / "runtime-cache",
            offline_bundle=candidate, platform_id="windows-x86_64",
        )
        self.assertEqual(install_result["status"], "installed")
        self.assertEqual((target / "python" / "python.exe").read_bytes(), b"MZ runtime")


class CliTests(ReleaseFixture):
    def setUp(self):
        super().setUp()
        import subprocess

        def git(*args: str) -> None:
            subprocess.run(
                ["git", "-C", str(self.source), *args],
                capture_output=True, check=True, timeout=60,
            )

        git("init", "-q")
        git("add", "-A", "--", ".")
        git("-c", "user.email=test@example.invalid", "-c", "user.name=Test",
            "commit", "-q", "-m", "fixture")

    def test_cli_plan_and_build(self):
        out = self.root / "cli-out"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = release.main([
                "--source", str(self.source), "--output-parent", str(out),
                "--name", "candidate", "--head", HEAD, "--plan", "--json",
            ])
        self.assertEqual(code, 0)
        self.assertFalse(out.exists())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "plan")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = release.main([
                "--source", str(self.source), "--output-parent", str(out),
                "--name", "candidate", "--head", HEAD, "--json",
            ])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "built")
        self.assertTrue((out / "candidate" / "release-manifest.json").is_file())
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = release.main([
                "--source", str(self.source), "--output-parent", str(out),
                "--name", "candidate", "--head", HEAD, "--json",
            ])
        self.assertEqual(code, 2)
        self.assertIn("refusing to overwrite", stderr.getvalue())


class SafetyTests(unittest.TestCase):
    def test_builder_has_no_destructive_operations(self):
        source = (REPO_ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        for forbidden in ("shutil", "os.remove", "os.unlink", "os.rename", "rmtree",
                          "os.rmdir", "send2trash"):
            self.assertNotIn(forbidden, source,
                             "forbidden destructive token in build_release.py: " + forbidden)

    def test_candidate_is_new_directory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            source.mkdir()
            tracked = make_source(source)
            parent = root / "dist"
            result = release.build_release(source, parent, tracked=tracked, head=HEAD,
                                           name="candidate")
            self.assertTrue((parent / "candidate").is_dir())
            self.assertEqual(sorted(path.name for path in parent.iterdir()), ["candidate"])
            self.assertEqual(
                sorted(path.name for path in Path(result["candidate"]).iterdir()),
                ["nl-coding-agent-0.3.1-source.zip", "platform-manifest.json",
                 "release-manifest.json"],
            )


if __name__ == "__main__":
    unittest.main()

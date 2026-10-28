"""Tests for the lightweight bootstrapper (no network; fake/local artifacts only)."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer import bootstrap, operations  # noqa: E402
from installer.fetcher import (  # noqa: E402
    ArtifactError,
    DownloadError,
    OfflineBundleFetcher,
    UrllibFetcher,
    VerificationError,
    verify_artifact,
)
from installer.platform_manifest import (  # noqa: E402
    ManifestError,
    components_for_platform,
    load_manifest,
    validate_manifest,
)

NL = chr(10)
PLATFORM = "windows-x86_64"
LAUNCHER = "NL Coding Agent.bat"
APP_FILES = {
    "nl_agent.py": b"print('launcher')" + NL.encode("utf-8"),
    "nl_coding_agent/__init__.py": b"package" + NL.encode("utf-8"),
    LAUNCHER: b"@echo off" + NL.encode("utf-8"),
}
APP_FILES_V2 = {
    "nl_agent.py": b"print('launcher v2')" + NL.encode("utf-8"),
    "nl_coding_agent/__init__.py": b"package v2" + NL.encode("utf-8"),
    LAUNCHER: b"@echo off" + NL.encode("utf-8"),
}


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    return buffer.getvalue()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_manifest(version: str = "0.2.0", *, app_bytes: bytes | None = None,
                  app_url: str = "artifacts/app.zip", release_ready: bool = True,
                  runtime_optional: bool = True) -> dict:
    data = app_bytes if app_bytes is not None else zip_bytes(APP_FILES)
    components = [{
        "id": "app-source",
        "kind": "app",
        "version": version,
        "archive": "zip",
        "destination": ".",
        "sha256": sha256_bytes(data),
        "size": len(data),
        "url": app_url,
        "platforms": [PLATFORM],
        "placeholder": False,
    }]
    if runtime_optional:
        components.append({
            "id": "python-runtime-" + PLATFORM,
            "kind": "runtime",
            "version": "3.12.10",
            "archive": "zip",
            "destination": "python",
            "sha256": "",
            "size": 0,
            "url": "components/python-runtime-" + PLATFORM + ".zip",
            "platforms": [PLATFORM],
            "optional": True,
            "placeholder": True,
        })
    return {
        "schema_version": 1,
        "status": "release" if release_ready else "template",
        "release_ready": release_ready,
        "generated_by": "tests",
        "product": {
            "id": "nl-coding-agent",
            "name": "NL Coding Agent",
            "version": version,
            "channel": "stable",
        },
        "base_urls": {"primary": "https://example.invalid/releases/" + version,
                      "mirrors": []},
        "platforms": {
            PLATFORM: {
                "display_name": "Windows 11 x64",
                "launcher": LAUNCHER,
                "runtime_component": "python-runtime-" + PLATFORM,
                "components": ["app-source"],
            }
        },
        "components": components,
    }


def write_bundle(bundle_dir: Path, manifest: dict, artifacts: dict[str, bytes]) -> Path:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + NL, encoding="utf-8"
    )
    for rel_path, data in artifacts.items():
        target = bundle_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return bundle_dir


class CountingFetcher:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.calls = 0

    def fetch(self, component, destination):
        self.calls += 1
        return self.delegate.fetch(component, destination)


class InstallerFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.cache = self.root / "cache"
        self.target = self.root / "app"
        self.bundle = self.root / "bundle"
        self.app_bytes = zip_bytes(APP_FILES)
        self.manifest = make_manifest(app_bytes=self.app_bytes)
        write_bundle(self.bundle, self.manifest, {"artifacts/app.zip": self.app_bytes})

    def install(self, target: Path | None = None, *, manifest: dict | None = None,
                bundle: Path | None = None, fetcher=None) -> dict:
        return operations.install(
            manifest or self.manifest,
            target or self.target,
            cache_dir=self.cache,
            fetcher=fetcher,
            offline_bundle=bundle or self.bundle,
        )


class ManifestTests(InstallerFixture):
    def test_shipped_template_manifest_validates_and_is_not_release_ready(self):
        template_path = REPO_ROOT / "installer" / "platform_manifest.json"
        manifest = load_manifest(template_path)
        self.assertFalse(manifest["release_ready"])
        self.assertEqual(manifest["product"]["version"], "0.2.0")
        self.assertIn("windows-x86_64", manifest["platforms"])
        self.assertIn("linux-x86_64", manifest["platforms"])
        runtime = manifest["platforms"]["windows-x86_64"]["runtime_component"]
        components = {item["id"]: item for item in manifest["components"]}
        self.assertEqual(components[runtime]["kind"], "runtime")
        self.assertTrue(components[runtime]["optional"])

    def test_template_plan_is_not_installable_and_writes_nothing(self):
        manifest = load_manifest(REPO_ROOT / "installer" / "platform_manifest.json")
        plan = operations.plan_install(manifest, target=self.target, cache_dir=self.cache,
                                       platform_id=PLATFORM)
        self.assertFalse(plan["installable"])
        self.assertFalse(plan["release_ready"])
        self.assertTrue(any("template" in warning for warning in plan["warnings"]))
        self.assertFalse(self.target.exists())
        self.assertFalse(self.cache.exists())

    def test_manifest_validation_rejects_unsafe_or_incomplete_manifests(self):
        broken = make_manifest()
        broken["product"].pop("version")
        with self.assertRaises(ManifestError):
            validate_manifest(broken)
        broken = make_manifest()
        broken["components"][0]["destination"] = "../escape"
        with self.assertRaises(ManifestError):
            validate_manifest(broken)
        broken = make_manifest()
        broken["components"][0]["sha256"] = "not-a-hash"
        with self.assertRaises(ManifestError):
            validate_manifest(broken)
        broken = make_manifest()
        broken["platforms"][PLATFORM]["components"] = ["unknown-component"]
        with self.assertRaises(ManifestError):
            validate_manifest(broken)
        broken = make_manifest(release_ready=True)
        broken["components"][0]["sha256"] = ""
        with self.assertRaises(ManifestError):
            validate_manifest(broken)
        broken = make_manifest()
        broken["schema_version"] = 99
        with self.assertRaises(ManifestError):
            validate_manifest(broken)

    def test_components_for_platform_excludes_optional_runtime(self):
        components = components_for_platform(self.manifest, PLATFORM)
        self.assertEqual([item["id"] for item in components], ["app-source"])


class PlanTests(InstallerFixture):
    def test_plan_reports_downloads_and_cache_state_without_writing(self):
        before = sorted(path.as_posix() for path in self.root.rglob("*"))
        plan = operations.plan_install(self.manifest, target=self.target,
                                       cache_dir=self.cache, platform_id=PLATFORM,
                                       offline_bundle=self.bundle)
        after = sorted(path.as_posix() for path in self.root.rglob("*"))
        self.assertEqual(before, after)
        self.assertTrue(plan["installable"])
        self.assertEqual(plan["target_state"], "absent")
        self.assertEqual(plan["download_bytes"], len(self.app_bytes))
        self.assertEqual(plan["cache_hits"], 0)
        self.assertEqual(plan["platform"], PLATFORM)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.cache.exists())


class InstallTests(InstallerFixture):
    def test_install_creates_isolated_target_and_shared_cache(self):
        result = self.install()
        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["version"], "0.2.0")
        self.assertEqual(result["downloaded"], ["app-source"])
        for rel_path, data in APP_FILES.items():
            self.assertEqual((self.target / rel_path).read_bytes(), data)
        state = operations.read_install_state(self.target)
        self.assertEqual(state["version"], "0.2.0")
        self.assertEqual(state["platform"], PLATFORM)
        self.assertEqual(state["file_count"], len(APP_FILES))
        report = operations.verify_install(self.target)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["checked_files"], len(APP_FILES))
        self.assertEqual(operations.cache_verify(self.cache)["ok"], True)
        listing = operations.cache_list(self.cache)
        self.assertEqual(listing["count"], 1)
        staging = [path for path in self.root.iterdir()
                   if path.name.startswith(".") and "staging" in path.name]
        self.assertEqual(staging, [])

    def test_second_install_reuses_cache_and_keeps_targets_isolated(self):
        delegate = OfflineBundleFetcher(self.bundle)
        counter = CountingFetcher(delegate)
        self.install(fetcher=counter)
        second_target = self.root / "app-two"
        result = operations.install(self.manifest, second_target, cache_dir=self.cache,
                                    fetcher=counter)
        self.assertEqual(counter.calls, 1)
        self.assertEqual(result["cache_hits"], 1)
        self.assertEqual(result["downloaded"], [])
        self.assertEqual((second_target / "nl_agent.py").read_bytes(), APP_FILES["nl_agent.py"])
        self.assertEqual((self.target / "nl_agent.py").read_bytes(), APP_FILES["nl_agent.py"])

    def test_install_refuses_template_manifest(self):
        manifest = make_manifest(release_ready=False)
        with self.assertRaises(operations.InstallError):
            operations.install(manifest, self.target, cache_dir=self.cache,
                               offline_bundle=self.bundle)
        self.assertFalse(self.target.exists())

    def test_install_refuses_non_empty_target(self):
        self.target.mkdir()
        (self.target / "user-file.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(operations.TargetError):
            self.install()
        self.assertEqual((self.target / "user-file.txt").read_text(encoding="utf-8"), "keep")

    def test_install_refuses_filesystem_root(self):
        root = Path(Path.cwd().anchor)
        with self.assertRaises(operations.TargetError):
            operations.validate_target(root)

    def test_hash_mismatch_fails_without_partial_install(self):
        wrong = zip_bytes(APP_FILES_V2)
        manifest = make_manifest(app_bytes=wrong)
        manifest["components"][0]["sha256"] = "0" * 64
        bundle = self.root / "bad-bundle"
        write_bundle(bundle, manifest, {"artifacts/app.zip": wrong})
        with self.assertRaises(VerificationError):
            operations.install(manifest, self.target, cache_dir=self.cache,
                               offline_bundle=bundle)
        self.assertFalse(self.target.exists())
        self.assertEqual([path for path in self.root.rglob("*.nlcoding-part")], [])
        staging = [path for path in self.root.iterdir()
                   if path.name.startswith(".") and "staging" in path.name]
        self.assertEqual(staging, [])

    def test_size_mismatch_fails(self):
        manifest = make_manifest(app_bytes=self.app_bytes)
        manifest["components"][0]["size"] = len(self.app_bytes) + 99
        bundle = self.root / "bad-size-bundle"
        write_bundle(bundle, manifest, {"artifacts/app.zip": self.app_bytes})
        with self.assertRaises(VerificationError):
            operations.install(manifest, self.target, cache_dir=self.cache,
                               offline_bundle=bundle)
        self.assertFalse(self.target.exists())

    def test_corrupt_cache_is_discarded_and_refetched(self):
        self.install()
        cache_artifact = next((self.cache / "artifacts").rglob("app.zip"))
        cache_artifact.write_bytes(b"corrupted")
        second_target = self.root / "app-repair"
        result = operations.install(self.manifest, second_target, cache_dir=self.cache,
                                    offline_bundle=self.bundle)
        self.assertEqual(result["downloaded"], ["app-source"])
        self.assertTrue(operations.verify_install(second_target)["ok"])
        self.assertTrue(operations.cache_verify(self.cache)["ok"])


class VerifyRepairUpdateTests(InstallerFixture):
    def test_verify_detects_missing_and_modified_files(self):
        self.install()
        manifest_path = self.target / "nl_agent.py"
        manifest_path.write_text("tampered", encoding="utf-8")
        (self.target / "nl_coding_agent" / "__init__.py").unlink()
        report = operations.verify_install(self.target)
        self.assertFalse(report["ok"])
        self.assertIn("nl_agent.py", report["modified"])
        self.assertIn("nl_coding_agent/__init__.py", report["missing"])
        self.assertEqual(bootstrap.main(["verify", "--target", str(self.target), "--json"]),
                         bootstrap.EXIT_VERIFICATION)

    def test_repair_restores_damaged_files_and_keeps_backup(self):
        self.install()
        (self.target / "nl_agent.py").write_text("tampered", encoding="utf-8")
        result = operations.repair(self.manifest, self.target, cache_dir=self.cache,
                                   offline_bundle=self.bundle, platform_id=PLATFORM)
        self.assertEqual(result["status"], "repaired")
        self.assertTrue(Path(result["backup"]).is_dir())
        self.assertEqual((self.target / "nl_agent.py").read_bytes(), APP_FILES["nl_agent.py"])
        self.assertTrue(operations.verify_install(self.target)["ok"])

    def test_healthy_repair_is_a_no_op(self):
        self.install()
        result = operations.repair(self.manifest, self.target, cache_dir=self.cache,
                                   offline_bundle=self.bundle, platform_id=PLATFORM)
        self.assertEqual(result["status"], "healthy")
        self.assertFalse(result["changed"])

    def test_update_installs_new_version_and_keeps_previous_backup(self):
        self.install()
        v2_bytes = zip_bytes(APP_FILES_V2)
        manifest_v2 = make_manifest(version="0.2.1", app_bytes=v2_bytes,
                                    app_url="artifacts/app-v2.zip")
        bundle_v2 = self.root / "bundle-v2"
        write_bundle(bundle_v2, manifest_v2, {"artifacts/app-v2.zip": v2_bytes})
        result = operations.update(manifest_v2, self.target, cache_dir=self.cache,
                                   offline_bundle=bundle_v2, platform_id=PLATFORM)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["previous_version"], "0.2.0")
        self.assertEqual(result["version"], "0.2.1")
        backup = Path(result["backup"])
        self.assertTrue(backup.is_dir())
        self.assertEqual((backup / "nl_agent.py").read_bytes(), APP_FILES["nl_agent.py"])
        self.assertEqual((self.target / "nl_agent.py").read_bytes(), APP_FILES_V2["nl_agent.py"])
        self.assertEqual(operations.read_install_state(self.target)["version"], "0.2.1")
        self.assertTrue(operations.verify_install(self.target)["ok"])

    def test_same_version_update_is_up_to_date(self):
        self.install()
        result = operations.update(self.manifest, self.target, cache_dir=self.cache,
                                   offline_bundle=self.bundle, platform_id=PLATFORM)
        self.assertEqual(result["status"], "up-to-date")
        self.assertIsNone(result["backup"])

    def test_update_refuses_downgrade_by_default(self):
        self.install()
        older = make_manifest(version="0.1.0", app_bytes=self.app_bytes)
        bundle_older = self.root / "bundle-older"
        write_bundle(bundle_older, older, {"artifacts/app.zip": self.app_bytes})
        with self.assertRaises(operations.InstallError):
            operations.update(older, self.target, cache_dir=self.cache,
                              offline_bundle=bundle_older, platform_id=PLATFORM)


class FetcherTests(InstallerFixture):
    def test_urllib_fetcher_success_writes_verified_artifact(self):
        manifest = make_manifest(app_bytes=self.app_bytes)

        class FakeResponse:
            status = 200

            def __init__(self, data: bytes) -> None:
                self._buffer = io.BytesIO(data)

            def read(self, size: int = -1) -> bytes:
                return self._buffer.read(size)

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

        def opener(url, timeout=None):
            return FakeResponse(self.app_bytes)

        fetcher = UrllibFetcher(manifest, opener=opener, timeout=1)
        destination = self.cache / "app.zip"
        path = fetcher.fetch(manifest["components"][0], destination)
        self.assertEqual(path.read_bytes(), self.app_bytes)
        self.assertEqual(verify_artifact(path, manifest["components"][0]["sha256"],
                                         len(self.app_bytes)), path)

    def test_urllib_fetcher_hash_mismatch_is_atomic(self):
        manifest = make_manifest(app_bytes=self.app_bytes)
        manifest["components"][0]["sha256"] = "1" * 64

        class FakeResponse:
            status = 200

            def __init__(self, data: bytes) -> None:
                self._buffer = io.BytesIO(data)

            def read(self, size: int = -1) -> bytes:
                return self._buffer.read(size)

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

        fetcher = UrllibFetcher(manifest, opener=lambda url, timeout=None: FakeResponse(self.app_bytes))
        destination = self.cache / "bad.zip"
        with self.assertRaises(VerificationError):
            fetcher.fetch(manifest["components"][0], destination)
        self.assertFalse(destination.exists())
        self.assertEqual([path for path in self.cache.rglob("*.nlcoding-part")], [])

    def test_urllib_fetcher_rejects_non_http_urls(self):
        manifest = make_manifest(app_bytes=self.app_bytes)
        manifest["components"][0]["url"] = "file:///tmp/app.zip"
        fetcher = UrllibFetcher(manifest, opener=lambda *args, **kwargs: None)
        with self.assertRaises(DownloadError):
            fetcher.fetch(manifest["components"][0], self.cache / "x.zip")

    def test_offline_bundle_rejects_escaping_paths(self):
        manifest = make_manifest(app_bytes=self.app_bytes)
        manifest["components"][0]["url"] = "../escape.zip"
        bundle = self.root / "escape-bundle"
        write_bundle(bundle, manifest, {"artifacts/app.zip": self.app_bytes})
        with self.assertRaises(ArtifactError):
            OfflineBundleFetcher(bundle).fetch(manifest["components"][0],
                                               self.cache / "app.zip")


class CacheTests(InstallerFixture):
    def test_cache_list_verify_prune_and_clear(self):
        self.install()
        listing = operations.cache_list(self.cache)
        self.assertEqual(listing["count"], 1)
        self.assertTrue(operations.cache_verify(self.cache)["ok"])
        artifact = Path(listing["entries"][0]["path"])
        artifact.write_bytes(b"corrupt")
        self.assertFalse(operations.cache_verify(self.cache)["ok"])
        refused = operations.cache_prune(self.cache, keep_days=0)
        self.assertEqual(refused["status"], "refused")
        artifact.write_bytes(self.app_bytes)
        old = time.time() - 3 * 86400
        os.utime(artifact, (old, old))
        pruned = operations.cache_prune(self.cache, keep_days=0.5, yes=True)
        self.assertEqual(pruned["status"], "pruned")
        self.assertEqual(len(pruned["removed"]), 1)
        self.install(target=self.root / "app-again")
        refused_clear = operations.cache_clear(self.cache)
        self.assertEqual(refused_clear["status"], "refused")
        cleared = operations.cache_clear(self.cache, yes=True)
        self.assertEqual(cleared["status"], "cleared")
        self.assertEqual(operations.cache_list(self.cache)["count"], 0)


class CliTests(InstallerFixture):
    def test_cli_install_plan_verify_flow(self):
        code = bootstrap.main([
            "install", "--target", str(self.target), "--offline-bundle", str(self.bundle),
            "--cache", str(self.cache), "--json",
        ])
        self.assertEqual(code, bootstrap.EXIT_OK)
        self.assertTrue((self.target / "nl_agent.py").is_file())
        code = bootstrap.main(["verify", "--target", str(self.target), "--json"])
        self.assertEqual(code, bootstrap.EXIT_OK)
        code = bootstrap.main([
            "plan", "--manifest", str(self.bundle / "manifest.json"),
            "--target", str(self.root / "future"), "--cache", str(self.cache), "--json",
        ])
        self.assertEqual(code, bootstrap.EXIT_OK)

    def test_cli_template_install_exit_code(self):
        template = REPO_ROOT / "installer" / "platform_manifest.json"
        code = bootstrap.main([
            "install", "--target", str(self.target), "--manifest", str(template),
            "--cache", str(self.cache), "--json",
        ])
        self.assertEqual(code, bootstrap.EXIT_USAGE)
        self.assertFalse(self.target.exists())

    def test_cli_verification_failure_exit_code(self):
        self.install()
        (self.target / "nl_agent.py").write_text("bad", encoding="utf-8")
        code = bootstrap.main(["verify", "--target", str(self.target)])
        self.assertEqual(code, bootstrap.EXIT_VERIFICATION)


class SafetyTests(unittest.TestCase):
    def test_installer_uses_only_stdlib_and_no_global_tooling(self):
        sources = [path.read_text(encoding="utf-8") for path in
                   (REPO_ROOT / "installer").glob("*.py")]
        combined = chr(10).join(sources)
        for forbidden in ("subprocess", "os.system(", "import requests",
                          "pip install", "uv pip install"):
            self.assertNotIn(forbidden, combined,
                             "forbidden global-tooling token in installer: " + forbidden)

    def test_install_does_not_write_outside_cache_or_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            target = root / "app"
            bundle = root / "bundle"
            app_bytes = zip_bytes(APP_FILES)
            manifest = make_manifest(app_bytes=app_bytes)
            write_bundle(bundle, manifest, {"artifacts/app.zip": app_bytes})
            before = {path.as_posix() for path in root.rglob("*")}
            operations.install(manifest, target, cache_dir=cache, offline_bundle=bundle)
            after = {path.as_posix() for path in root.rglob("*")}
            new_paths = after - before
            allowed_roots = {cache.resolve(), target.resolve()}
            for path_text in new_paths:
                path = Path(path_text).resolve()
                self.assertTrue(any(path == item or item in path.parents for item in allowed_roots),
                                "unexpected write outside cache/target: " + path_text)


if __name__ == "__main__":
    unittest.main()

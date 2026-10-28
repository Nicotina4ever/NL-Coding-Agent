"""Tests for the deterministic private-beta package builder (no network)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer.platform_manifest import load_manifest  # noqa: E402
from installer.runtime_manifest import load_runtime_manifest  # noqa: E402
import scripts.build_beta_packages as beta  # noqa: E402

HEAD = "0123456789abcdef0123456789abcdef01234567"
VERSION = "0.4.2"
SOURCE_FILES = {
    "README.md": b"# fixture source" + bytes([10]),
    "nl_agent.py": b"print('fixture')" + bytes([10]),
    "nl_coding_agent/core/version.py": ("APP_VERSION = '" + VERSION + "'" + chr(10)).encode("utf-8"),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[name])
    return buffer.getvalue()


def make_fixture(root: Path, *, version: str = VERSION,
                 source_files: dict[str, bytes] | None = None,
                 archive_name: str | None = None,
                 candidate_version: str | None = None) -> tuple[Path, Path, bytes]:
    source = root / "source"
    (source / "nl_coding_agent" / "core").mkdir(parents=True)
    (source / "nl_coding_agent" / "core" / "version.py").write_text(
        "APP_VERSION = '" + version + "'" + chr(10), encoding="utf-8")
    files = source_files if source_files is not None else dict(SOURCE_FILES)
    payload = make_zip(files)
    candidate = root / "candidate"
    candidate.mkdir()
    name = archive_name or ("nl-coding-agent-" + version + "-source.zip")
    (candidate / name).write_bytes(payload)
    manifest = {
        "schema_version": 1,
        "generator": {"name": "fixture", "version": "1"},
        "product": {"id": "nl-coding-agent", "name": "NL Coding Agent",
                    "version": candidate_version or version, "channel": "source"},
        "source": {"git_head": HEAD, "git_head_short": HEAD[:12],
                   "tracked_files": len(files), "tracked_hash": sha256_bytes(payload)},
        "archive": {"name": name, "format": "zip", "sha256": sha256_bytes(payload),
                    "size": len(payload), "file_count": len(files),
                    "total_bytes": sum(len(item) for item in files.values())},
        "files": [{"path": item, "sha256": sha256_bytes(files[item]),
                   "size": len(files[item])} for item in sorted(files)],
        "platforms": {},
    }
    (candidate / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    return source, candidate, payload


def package_files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


class BetaPackageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source, self.candidate, self.zip_payload = make_fixture(self.root)

    def build(self, parent: Path | None = None, **kwargs) -> tuple[dict, Path]:
        parent = parent or (self.root / "out")
        result = beta.build_beta_package(self.candidate, source=self.source,
                                         output_parent=parent, **kwargs)
        return result, Path(result["output"])

    def test_layout_checksums_and_inventory(self):
        result, output = self.build()
        self.assertEqual(result["status"], "packaged")
        files = package_files(output)
        expected = {
            "SHA256SUMS", "beta-manifest.json",
            "installer/platform-manifest.json", "installer/runtime-manifest.json",
            "INSTALL.md", "BETA_README.md", "VERSION",
            "source/nl-coding-agent-" + VERSION + "-source.zip",
            *["install/INSTALL-" + target + ".md" for target in beta.release_builder.TARGET_ORDER],
        }
        self.assertEqual(set(files), expected)
        self.assertEqual(files["VERSION"], (VERSION + chr(10)).encode())
        self.assertEqual(files["source/nl-coding-agent-" + VERSION + "-source.zip"],
                         self.zip_payload)
        sums = files["SHA256SUMS"].decode("utf-8").splitlines()
        parsed = {}
        for line in sums:
            digest, rel = line.split("  ", 1)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            parsed[rel] = digest
        self.assertEqual(set(parsed), expected - {"SHA256SUMS"})
        for rel, digest in parsed.items():
            self.assertEqual(digest, sha256_bytes(files[rel]), rel)
        manifest = json.loads(files["beta-manifest.json"])
        inventory = {item["path"]: item for item in manifest["payload"]["inventory"]}
        self.assertEqual(set(inventory), expected - {"SHA256SUMS", "beta-manifest.json"})
        for rel, item in inventory.items():
            self.assertEqual(item["sha256"], sha256_bytes(files[rel]), rel)
            self.assertEqual(item["size"], len(files[rel]), rel)
        self.assertEqual(manifest["source"]["archive"]["sha256"], sha256_bytes(self.zip_payload))
        self.assertEqual(manifest["source"]["git_head"], HEAD)
        for forbidden in ("python/", "crewAI/", "data/", "logs/", ".workspace/",
                          "da_eliminare/", "build/", "dist/"):
            self.assertFalse(any(path.startswith(forbidden) for path in files), forbidden)

    def test_six_target_metadata_is_explicitly_unmeasured_and_honest(self):
        result, output = self.build()
        files = package_files(output)
        manifest = json.loads(files["beta-manifest.json"])
        targets = list(beta.release_builder.TARGET_ORDER)
        self.assertEqual(sorted(manifest["platforms"]), sorted(targets))
        for target in targets:
            entry = manifest["platforms"][target]
            self.assertEqual(entry["runtime"]["measured"], False)
            self.assertEqual(entry["runtime"]["sha256"], "")
            self.assertEqual(entry["runtime"]["size"], 0)
            self.assertEqual(entry["runtime"]["release_ready"], False)
            self.assertEqual(entry["runtime"]["status"], "unmeasured")
            self.assertTrue(entry["manual_pending"])
            self.assertTrue(entry["ci_flags"])
        self.assertFalse(manifest["validation"]["release_ready"])
        self.assertFalse(manifest["validation"]["runtime_components_measured"])
        self.assertTrue(manifest["validation"]["ci_flags"])
        self.assertTrue(manifest["validation"]["manual_pending"])
        self.assertFalse(manifest["universal2"]["supported"])
        self.assertEqual(manifest["universal2"]["decision"], "separate-per-arch")
        platform_manifest = load_manifest(output / "installer" / "platform-manifest.json")
        self.assertFalse(platform_manifest["release_ready"])
        self.assertEqual(sorted(platform_manifest["platforms"]), sorted(targets))
        components = {item["id"]: item for item in platform_manifest["components"]}
        app = components["app-source"]
        self.assertEqual(app["sha256"], sha256_bytes(self.zip_payload))
        self.assertEqual(app["size"], len(self.zip_payload))
        for target in targets:
            runtime = components[platform_manifest["platforms"][target]["runtime_component"]]
            self.assertEqual(runtime["kind"], "runtime")
            self.assertEqual(runtime["sha256"], "")
            self.assertEqual(runtime["size"], 0)
            self.assertTrue(runtime["optional"])
        runtime_manifest = load_runtime_manifest(output / "installer" / "runtime-manifest.json")
        self.assertFalse(runtime_manifest["release_ready"])
        self.assertEqual(sorted(runtime_manifest["targets"]), sorted(targets))
        for entry in runtime_manifest["targets"].values():
            self.assertFalse(entry["runtime"]["measured"])
            self.assertEqual(entry["runtime"]["sha256"], "")
            self.assertEqual(entry["runtime"]["size"], 0)

    def test_install_docs_are_non_developer_friendly(self):
        _, output = self.build()
        files = package_files(output)
        main = files["INSTALL.md"].decode("utf-8")
        for token in ("Get-FileHash", "sha256sum -c", "shasum -a 256 -c",
                      "MANUAL-PENDING", "First-run", "feedback", "SHA256SUMS"):
            self.assertIn(token, main)
        self.assertIn(VERSION, files["BETA_README.md"].decode("utf-8"))
        self.assertIn(HEAD[:12], files["BETA_README.md"].decode("utf-8"))
        for target in beta.release_builder.TARGET_ORDER:
            text = files["install/INSTALL-" + target + ".md"].decode("utf-8")
            descriptor = beta.release_builder.SUPPORTED_TARGETS[target]
            self.assertIn(descriptor["display_name"], text)
            self.assertIn(target, text)
            self.assertIn("MANUAL-PENDING", text)
            self.assertIn("feedback", text.lower())
            self.assertIn("unmeasured", text)
            if descriptor["os"] == "windows":
                self.assertIn("Get-FileHash", text)
            elif descriptor["os"] == "linux":
                self.assertIn("sha256sum -c", text)
            else:
                self.assertIn("shasum -a 256 -c", text)

    def test_rebuild_is_byte_deterministic(self):
        first = self.build(self.root / "out-a")[1]
        second = self.build(self.root / "out-b")[1]
        files_a = package_files(first)
        files_b = package_files(second)
        self.assertEqual(sorted(files_a), sorted(files_b))
        for rel in files_a:
            self.assertEqual(files_a[rel], files_b[rel], "non-deterministic file: " + rel)

    def test_refuses_to_overwrite_existing_package(self):
        output = self.root / "out" / ("beta-" + VERSION)
        output.mkdir(parents=True)
        marker = output / "keep.txt"
        marker.write_text("do not touch", encoding="utf-8")
        with self.assertRaises(beta.BetaPackageError):
            beta.build_beta_package(self.candidate, source=self.source,
                                    output_parent=self.root / "out")
        self.assertEqual(marker.read_text(encoding="utf-8"), "do not touch")
        self.assertEqual(sorted(path.name for path in output.iterdir()), ["keep.txt"])

    def test_no_absolute_paths_or_timestamps_in_text_files(self):
        _, output = self.build()
        needles = (str(self.root), str(self.source), str(self.candidate),
                   str(output), "K:", "C:", "\\\\")
        timestamp = re.compile(r"[12][0-9]{3}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:")
        for rel, data in package_files(output).items():
            if rel.endswith(".zip"):
                continue
            text = data.decode("utf-8")
            for needle in needles:
                self.assertNotIn(needle, text, rel + " contains " + needle)
            self.assertIsNone(timestamp.search(text), rel + " contains a timestamp")

    def test_rejects_candidate_with_runtime_or_user_data(self):
        for bad_name in ("python/python.exe", "data/user.sqlite3", "crewAI/vendor.py",
                         ".workspace/state.json"):
            root = self.root / ("bad-" + bad_name.replace("/", "-"))
            source, candidate, _ = make_fixture(
                root, source_files={"nl_agent.py": b"x", bad_name: b"bad"})
            with self.assertRaises(beta.BetaPackageError):
                beta.build_beta_package(candidate, source=source,
                                        output_parent=root / "out")

    def test_rejects_version_mismatch_and_hash_mismatch(self):
        mismatch_root = self.root / "mismatch"
        source, candidate, _ = make_fixture(mismatch_root, candidate_version="9.9.9")
        with self.assertRaises(beta.BetaPackageError):
            beta.build_beta_package(candidate, source=source,
                                    output_parent=mismatch_root / "out")
        manifest = json.loads((self.candidate / "release-manifest.json").read_text(encoding="utf-8"))
        manifest["archive"]["sha256"] = "0" * 64
        (self.candidate / "release-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(beta.BetaPackageError):
            beta.build_beta_package(self.candidate, source=self.source,
                                    output_parent=self.root / "out-hash")
        self.assertFalse((self.root / "out-hash" / ("beta-" + VERSION)).exists())

    def test_plan_writes_nothing_and_main_builds(self):
        out = self.root / "plan-out"
        result = beta.build_beta_package(self.candidate, source=self.source,
                                         output_parent=out, plan=True)
        self.assertEqual(result["status"], "plan")
        self.assertFalse(out.exists())
        self.assertIn("beta-manifest.json", result["files"])
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = beta.main(["--candidate", str(self.candidate), "--source", str(self.source),
                              "--output-parent", str(self.root / "cli-out"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "packaged")
        self.assertTrue(Path(payload["output"]).is_dir())
        self.assertTrue((Path(payload["output"]) / "SHA256SUMS").is_file())
        self.assertEqual(beta.main(["--candidate", str(self.candidate),
                                    "--source", str(self.source),
                                    "--output-parent", str(self.root / "cli-out")]), 2)

    def test_auto_discovers_candidate_under_workspace_dist(self):
        root = self.root / "auto"
        source = root / "source"
        (source / "nl_coding_agent" / "core").mkdir(parents=True)
        (source / "nl_coding_agent" / "core" / "version.py").write_text(
            "APP_VERSION = '" + VERSION + "'" + chr(10), encoding="utf-8")
        candidate = source / ".workspace" / "dist" / ("release-candidate-" + VERSION + "-abcdef")
        candidate.mkdir(parents=True)
        payload = make_zip(SOURCE_FILES)
        (candidate / ("nl-coding-agent-" + VERSION + "-source.zip")).write_bytes(payload)
        manifest = {
            "schema_version": 1,
            "product": {"id": "nl-coding-agent", "name": "NL Coding Agent",
                        "version": VERSION, "channel": "source"},
            "source": {"git_head": HEAD, "git_head_short": HEAD[:12],
                       "tracked_files": len(SOURCE_FILES),
                       "tracked_hash": sha256_bytes(payload)},
            "archive": {"name": "nl-coding-agent-" + VERSION + "-source.zip",
                        "format": "zip", "sha256": sha256_bytes(payload),
                        "size": len(payload), "file_count": len(SOURCE_FILES)},
            "files": [],
            "platforms": {},
        }
        (candidate / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        result = beta.build_beta_package(source=source)
        self.assertEqual(result["status"], "packaged")
        self.assertTrue((source / ".workspace" / "dist" / ("beta-" + VERSION)
                         / "beta-manifest.json").is_file())

    def test_static_no_network_no_publish_no_timestamps(self):
        source = (REPO_ROOT / "scripts" / "build_beta_packages.py").read_text(encoding="utf-8")
        for forbidden in ("import urllib", "import requests", "import socket",
                          "http.client", "subprocess", "os.system(",
                          "pip install", "model.run", "ollama", "publish(",
                          "upload(", "datetime", "time.time"):
            self.assertNotIn(forbidden, source, "forbidden token in beta builder: " + forbidden)
        self.assertIn("from scripts import build_release", source)


if __name__ == "__main__":
    unittest.main()

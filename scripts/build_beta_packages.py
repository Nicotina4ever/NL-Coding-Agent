"""Build a deterministic private-beta package from a source release candidate.

Input: a source release candidate produced by scripts/build_release.py (its
release-manifest.json + source zip), or an explicit --candidate directory.

Output: a NEW directory .workspace/dist/beta-<version>/ (refuses to overwrite)
containing checksums, a versioned beta manifest, installer/runtime manifest
templates, non-developer installation instructions and the measured source zip.

Guarantees: deterministic bytes for identical inputs; no runtime, vendor
checkout, user data, logs or workspace content is bundled; no network, model,
upload or publish path; existing package directories are refused untouched;
manifests reuse the installer schemas and scripts/build_release.py contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer.platform_manifest import validate_manifest  # noqa: E402
from installer.runtime_manifest import validate_runtime_manifest  # noqa: E402
from scripts import build_release as release_builder  # noqa: E402

PACKAGE_FORMAT = "nl-coding-agent-beta-package"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_PARENT = Path(".workspace") / "dist"
SHA256SUMS_NAME = "SHA256SUMS"
MANIFEST_NAME = "beta-manifest.json"
PLATFORM_MANIFEST_NAME = "installer/platform-manifest.json"
RUNTIME_MANIFEST_NAME = "installer/runtime-manifest.json"
INSTALL_NAME = "INSTALL.md"
README_NAME = "BETA_README.md"
VERSION_NAME = "VERSION"
SOURCE_DIR = "source"
FENCE = chr(96) * 3
HEX = set("0123456789abcdef")
FORBIDDEN_PAYLOAD_PREFIXES = (
    "python/", "crewAI/", "crewAI-tools/", "data/", "logs/", ".workspace/",
    "dist/", "build/", "state/", ".git/", "da_eliminare/", "node_modules/",
)
FORBIDDEN_PAYLOAD_SUFFIXES = (".sqlite3", ".pyc", ".pyo", ".log")
MANUAL_PENDING_ITEMS = (
    "native standalone runtimes for the six OS/arch targets are not built or measured yet",
    "clean-host install/start/project/mission acceptance on Windows ARM64, Linux x86_64/ARM64, macOS Intel/Apple Silicon",
    "GPU backends (CUDA/ROCm/Metal/MLX), ASR/TTS hardware and real multimodal latency",
    "code signing/notarization and a published/signed download channel",
    "the full pytest baseline and reviewer sign-off (Lead-run)",
)
CI_FLAGS = (
    "deterministic_package_bytes",
    "sha256sums_cover_payload",
    "payload_inventory_hashes",
    "six_target_platform_matrix_declared",
    "runtime_components_marked_unmeasured",
    "manifests_validate_against_installer_schema",
    "no_runtime_vendor_or_user_data_bundled",
)
UNIVERSAL2_EVIDENCE = (
    "macOS Universal 2 is not claimed: separate per-arch runtimes are declared; "
    "a universal artifact is only schema-legal when measured and shared by both "
    "macOS targets (see installer/runtime-manifest.json)."
)


class BetaPackageError(RuntimeError):
    """Raised when a beta package cannot be produced safely or honestly."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(data) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
            + chr(10)).encode("utf-8")


def _text_bytes(text: str) -> bytes:
    return (text.rstrip(chr(10)) + chr(10)).encode("utf-8")


def _safe_relative(value: str, field: str) -> str:
    text = str(value or "").replace(chr(92), "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise BetaPackageError("unsafe relative path in " + field + ": " + repr(value))
    parts = [part for part in text.split("/") if part]
    if not parts or any(part == ".." for part in parts):
        raise BetaPackageError("unsafe relative path in " + field + ": " + repr(value))
    return "/".join(parts)


def _read_version(source: Path) -> str:
    try:
        return release_builder.read_version(source)
    except Exception as exc:
        raise BetaPackageError("cannot read APP_VERSION from source: " + str(exc)) from exc


def _discover_candidate(source: Path) -> Path:
    candidates: list[Path] = []
    for root in (source / ".workspace" / "dist", source / "dist"):
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir(), key=lambda item: item.name, reverse=True):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if child.name.startswith("beta-"):
                continue
            if (child / "release-manifest.json").is_file():
                candidates.append(child)
    if not candidates:
        raise BetaPackageError(
            "no source release candidate found under .workspace/dist or dist; run "
            "scripts/build_release.py first or pass --candidate PATH"
        )
    return candidates[0]


def _load_candidate(candidate: str | Path) -> dict:
    path = Path(candidate).expanduser().resolve()
    if path.is_file() and path.name == "release-manifest.json":
        path = path.parent
    if not path.is_dir():
        raise BetaPackageError("candidate directory not found: " + str(path))
    manifest_path = path / "release-manifest.json"
    if not manifest_path.is_file():
        raise BetaPackageError(
            "candidate has no release-manifest.json (expected build_release.py output): "
            + str(path)
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BetaPackageError("cannot read candidate release-manifest.json: " + str(exc))
    product = manifest.get("product") or {}
    source = manifest.get("source") or {}
    archive = manifest.get("archive") or {}
    version = str(product.get("version") or "").strip()
    git_head = str(source.get("git_head") or "").strip().lower()
    if not version:
        raise BetaPackageError("candidate release manifest has no product.version")
    if not re.fullmatch(r"[0-9a-f]{7,64}", git_head):
        raise BetaPackageError("candidate release manifest has no valid git head")
    if not isinstance(archive, dict):
        raise BetaPackageError("candidate release manifest has no archive block")
    archive_name = _safe_relative(str(archive.get("name") or ""), "candidate archive.name")
    if "/" in archive_name:
        raise BetaPackageError("candidate archive name must be a file name: " + archive_name)
    digest = str(archive.get("sha256") or "").strip().lower()
    if len(digest) != 64 or any(char not in HEX for char in digest):
        raise BetaPackageError("candidate archive has no valid sha256")
    try:
        size = int(archive.get("size"))
    except (TypeError, ValueError) as exc:
        raise BetaPackageError("candidate archive has no valid size") from exc
    if size <= 0:
        raise BetaPackageError("candidate archive size must be positive")
    archive_path = path / archive_name
    if not archive_path.is_file():
        raise BetaPackageError("candidate archive not found: " + str(archive_path))
    if archive_path.stat().st_size != size:
        raise BetaPackageError("candidate archive size does not match its manifest")
    if sha256_file(archive_path) != digest:
        raise BetaPackageError("candidate archive sha256 does not match its manifest")
    if str(archive.get("format") or "zip").lower() != "zip":
        raise BetaPackageError("candidate archive must be a zip for beta packages")
    _validate_source_archive(archive_path, int(archive.get("file_count") or 0))
    return {
        "path": path,
        "manifest": manifest,
        "version": version,
        "git_head": git_head,
        "git_head_short": str(source.get("git_head_short") or git_head[:12]),
        "tracked_hash": str(source.get("tracked_hash") or ""),
        "archive_name": archive_name,
        "archive_sha256": digest,
        "archive_size": size,
        "archive_file_count": int(archive.get("file_count") or 0),
    }


def _validate_source_archive(archive_path: Path, expected_file_count: int) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = [item.filename.replace(chr(92), "/") for item in archive.infolist()
                     if not item.is_dir()]
    except (OSError, zipfile.BadZipFile) as exc:
        raise BetaPackageError("candidate archive is not a readable zip: " + str(exc))
    if expected_file_count and len(names) != expected_file_count:
        raise BetaPackageError(
            "candidate archive file count does not match release manifest: expected "
            + str(expected_file_count) + ", got " + str(len(names))
        )
    for name in names:
        if not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            raise BetaPackageError("candidate archive contains an absolute path: " + name)
        parts = [part for part in name.split("/") if part]
        if any(part == ".." for part in parts):
            raise BetaPackageError("candidate archive contains a traversal path: " + name)
        normalised = "/".join(parts)
        for prefix in FORBIDDEN_PAYLOAD_PREFIXES:
            if normalised == prefix.rstrip("/") or normalised.startswith(prefix):
                raise BetaPackageError(
                    "candidate archive contains development/runtime data that must never "
                    "be bundled in a beta package: " + normalised
                )
        if normalised.lower().endswith(FORBIDDEN_PAYLOAD_SUFFIXES):
            raise BetaPackageError("candidate archive contains user/data/cache files: "
                                   + normalised)


def _build_platform_manifest(candidate: dict, version: str) -> dict:
    manifest = release_builder.build_platform_manifest(
        version=version,
        zip_name=SOURCE_DIR + "/" + candidate["archive_name"],
        zip_sha256=candidate["archive_sha256"],
        zip_size=candidate["archive_size"],
        platforms=dict(release_builder.DEFAULT_PLATFORMS),
        launchers=dict(release_builder.DEFAULT_LAUNCHERS),
        base_url="https://downloads.example.invalid/nl-coding-agent/beta-" + version,
    )
    manifest["status"] = "template"
    manifest["release_ready"] = False
    manifest["product"]["channel"] = "beta"
    normalized = validate_manifest(manifest)
    if normalized["release_ready"]:
        raise BetaPackageError("beta platform manifest must not be release_ready")
    return manifest


def _build_runtime_manifest(version: str) -> dict:
    manifest = release_builder.build_runtime_manifest(
        version, {},
        base_url="https://downloads.example.invalid/nl-coding-agent/beta-" + version,
    )
    manifest["status"] = "template"
    manifest["release_ready"] = False
    normalized = validate_runtime_manifest(manifest)
    for target_id, entry in normalized["targets"].items():
        runtime = entry["runtime"]
        if runtime["measured"] or runtime["sha256"] or runtime["size"]:
            raise BetaPackageError(
                "beta runtime manifest must keep " + target_id
                + " unmeasured with empty sha256/size"
            )
    return manifest


def _checksum_lines(root: Path) -> list[tuple[str, str, int]]:
    entries: list[tuple[str, str, int]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == SHA256SUMS_NAME:
            continue
        entries.append((rel, sha256_file(path), path.stat().st_size))
    # Sort by POSIX relative path so Windows (case-insensitive) and POSIX produce
    # the same deterministic order in beta-manifest.json and SHA256SUMS.
    entries.sort(key=lambda item: item[0])
    return entries


def _write_sums(root: Path) -> None:
    lines = [digest + "  " + rel for rel, digest, _size in _checksum_lines(root)]
    (root / SHA256SUMS_NAME).write_bytes(_text_bytes(chr(10).join(lines)))


def _install_common_lines(version: str) -> list[str]:
    return [
        "# NL Coding Agent private beta - " + version,
        "",
        "This is a source beta package, not a ready-to-run installer. The native",
        "standalone runtimes for the six beta targets are NOT bundled (status:",
        "MANUAL-PENDING / unmeasured). The package contains the measured source release",
        "archive, integrity manifests and instructions for beta evaluators.",
        "",
        "## Package contents",
        "",
        "- source/<source-archive>.zip - measured source release archive",
        "- " + SHA256SUMS_NAME + " - sha256 checksums for every payload file",
        "- " + MANIFEST_NAME + " - versioned beta manifest (inventory, platform matrix, flags)",
        "- " + PLATFORM_MANIFEST_NAME + " and " + RUNTIME_MANIFEST_NAME + " - installer/runtime templates",
        "- " + INSTALL_NAME + ", install/INSTALL-<target>.md - these instructions",
        "- " + README_NAME + ", " + VERSION_NAME,
        "",
        "## 1. Verify integrity before doing anything else",
        "",
        "All checksum commands are run from the extracted beta package directory.",
        "",
        "### Windows PowerShell",
        "",
        FENCE + "powershell",
        "Get-FileHash -Algorithm SHA256 -Path .\\" + SHA256SUMS_NAME,
        "# Then compare each line of SHA256SUMS with:",
        "Get-FileHash -Algorithm SHA256 -Path .\\source\\<source-archive>.zip",
        FENCE,
        "",
        "### Linux",
        "",
        FENCE + "bash",
        "sha256sum -c " + SHA256SUMS_NAME,
        FENCE,
        "",
        "### macOS",
        "",
        FENCE + "bash",
        "shasum -a 256 -c " + SHA256SUMS_NAME,
        FENCE,
        "",
        "A SHA256SUMS line looks like <sha256>  <relative-path>. Do not continue if any",
        "line fails: report the failing file and the full command output.",
        "",
        "## 2. First-run validation (source beta)",
        "",
        "1. Confirm " + VERSION_NAME + " and " + MANIFEST_NAME + " contain version " + version + ".",
        "2. Confirm all checksums pass (step 1).",
        "3. Read " + README_NAME + " and the per-platform file in install/ for your OS/arch.",
        "4. Extract the source archive:",
        "   - Windows: Expand-Archive -Path .\\source\\<archive>.zip -DestinationPath .\\app",
        "   - Linux/macOS: python3 -m zipfile -e source/<archive>.zip app",
        "5. Record your OS, architecture, shell version, checksum result and any error.",
        "",
        "There is no runnable native runtime in this package yet. A clean-host first run",
        "requires a measured native runtime artifact (MANUAL-PENDING); do not claim an",
        "install/startup success from this source package alone.",
        "",
        "## 3. Report issues / feedback",
        "",
        "Send the following to the private beta owner/channel:",
        "",
        "- package version and git head (from " + MANIFEST_NAME + ")",
        "- OS and architecture (for example Windows 11 x64, Linux x86_64, macOS arm64)",
        "- exact commands run and their full output (copy/paste, no screenshots only)",
        "- checksum failures with file names and hashes",
        "- steps to reproduce and the observed/expected result",
        "",
        "Do not upload source code, user projects, SQLite data, credentials or model files",
        "to public trackers; use the private beta feedback channel agreed with the owner.",
        "",
        "## MANUAL-PENDING warnings",
        "",
    ] + ["- MANUAL-PENDING: " + item for item in MANUAL_PENDING_ITEMS] + [
        "- MANUAL-PENDING: " + UNIVERSAL2_EVIDENCE,
        "",
    ]


def _install_platform_lines(version: str, target_id: str, descriptor: dict) -> list[str]:
    is_windows = descriptor["os"] == "windows"
    checksum = ("Get-FileHash -Algorithm SHA256 -Path .\\source\\<source-archive>.zip"
                if is_windows else
                ("sha256sum -c " + SHA256SUMS_NAME if descriptor["os"] == "linux"
                 else "shasum -a 256 -c " + SHA256SUMS_NAME))
    extract = ("Expand-Archive -Path .\\source\\<archive>.zip -DestinationPath .\\app"
               if is_windows else
               "python3 -m zipfile -e source/<archive>.zip app")
    return [
        "# NL Coding Agent private beta - " + descriptor["display_name"] + " - " + version,
        "",
        "- Target: " + target_id,
        "- OS/arch: " + descriptor["os"] + "/" + descriptor["arch"],
        "- Runtime archive kind: " + descriptor["archive"],
        "- Runtime component: " + descriptor["runtime_id"]
        + " (status: unmeasured / release_ready=false)",
        "- Launcher after a future install: " + descriptor["launcher"],
        "",
        "## 1. Verify checksums",
        "",
        FENCE + ("powershell" if is_windows else "bash"),
        checksum,
        FENCE,
        "",
        "Compare against the matching line in " + SHA256SUMS_NAME + ". If any hash differs,",
        "stop and report the failure; do not run extracted content.",
        "",
        "## 2. Extract the source archive",
        "",
        FENCE + ("powershell" if is_windows else "bash"),
        extract,
        FENCE,
        "",
        "## 3. First-run validation",
        "",
        "1. Check " + VERSION_NAME + " / " + MANIFEST_NAME + " report version " + version + ".",
        "2. Confirm the checksum in step 1 passes.",
        "3. Note that the native " + descriptor["os"] + " " + descriptor["arch"]
        + " runtime is MANUAL-PENDING/unmeasured in this package; a clean-host run is",
        "   not expected to start the application until a measured runtime is published.",
        "4. Record OS/arch, commands, outputs and the beta manifest git head for feedback.",
        "",
        "## 4. Feedback / issues",
        "",
        "Report version, git head, OS/arch, checksum result, commands and full errors to the",
        "private beta owner/channel. Never upload user projects, databases, credentials or",
        "model files to public trackers.",
        "",
        "## MANUAL-PENDING warnings",
        "",
        "- MANUAL-PENDING: native runtime artifact for " + target_id + " is not measured/bundled.",
        "- MANUAL-PENDING: clean-host acceptance and GPU/ASR/TTS hardware checks.",
        "- MANUAL-PENDING: code signing and published download channel.",
        "- MANUAL-PENDING: " + UNIVERSAL2_EVIDENCE,
        "",
    ]


def _beta_readme_lines(version: str, git_head_short: str) -> list[str]:
    return [
        "# NL Coding Agent - private beta source package " + version,
        "",
        "This package is a deterministic source-beta artifact built from git head "
        + git_head_short + ".",
        "",
        "- Read " + INSTALL_NAME + " and install/INSTALL-<target>.md first.",
        "- Verify " + SHA256SUMS_NAME + " before extracting or using anything.",
        "- " + MANIFEST_NAME + " lists the inventory, six-target platform matrix and",
        "  CI-vs-MANUAL-PENDING flags.",
        "- Native six-target runtimes are not bundled and are MANUAL-PENDING; see the",
        "  installer/runtime-manifest.json placeholders (no fabricated hashes).",
        "- This source beta is not a signed installer and makes no startup/acceptance claim.",
        "",
    ]


def build_beta_package(candidate: str | Path | None = None, *, source: str | Path | None = None,
                       output_parent: str | Path | None = None,
                       name: str | None = None, plan: bool = False) -> dict:
    source_path = Path(source).expanduser().resolve() if source else REPO_ROOT
    if not source_path.is_dir():
        raise BetaPackageError("source directory not found: " + str(source_path))
    version = _read_version(source_path)
    candidate_path = (Path(candidate).expanduser().resolve() if candidate
                      else _discover_candidate(source_path))
    loaded = _load_candidate(candidate_path)
    if loaded["version"] != version:
        raise BetaPackageError(
            "candidate version " + loaded["version"] + " does not match APP_VERSION "
            + version + " in " + str(source_path / "nl_coding_agent" / "core" / "version.py")
        )
    parent = (Path(output_parent).expanduser().resolve() if output_parent
              else source_path / DEFAULT_OUTPUT_PARENT)
    package_name = name or ("beta-" + version)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", package_name) or package_name in (".", ".."):
        raise BetaPackageError("invalid beta package directory name: " + repr(package_name))
    output = parent / package_name
    if output.exists():
        raise BetaPackageError(
            "beta package output already exists; refusing to overwrite: " + str(output)
        )
    platform_manifest = _build_platform_manifest(loaded, version)
    runtime_manifest = _build_runtime_manifest(version)
    platform_matrix = {}
    for target_id in release_builder.TARGET_ORDER:
        descriptor = release_builder.SUPPORTED_TARGETS[target_id]
        platform_matrix[target_id] = {
            "display_name": descriptor["display_name"],
            "os": descriptor["os"],
            "arch": descriptor["arch"],
            "launcher": descriptor["launcher"],
            "runtime_component": descriptor["runtime_id"],
            "runtime_archive_kind": descriptor["archive"],
            "runtime": {
                "measured": False,
                "sha256": "",
                "size": 0,
                "status": "unmeasured",
                "release_ready": False,
            },
            "ci_flags": [
                "matrix_entry_declared",
                "runtime_marked_unmeasured",
                "install_doc_generated",
            ],
            "manual_pending": [
                "native runtime artifact is not built/measured",
                "clean-host acceptance for this target",
                "GPU/ASR/TTS hardware and latency checks",
            ],
        }
    install_docs = [INSTALL_NAME] + ["install/INSTALL-" + target_id + ".md"
                                      for target_id in release_builder.TARGET_ORDER]
    planned_files = [
        SHA256SUMS_NAME, MANIFEST_NAME, PLATFORM_MANIFEST_NAME, RUNTIME_MANIFEST_NAME,
        INSTALL_NAME, README_NAME, VERSION_NAME,
        SOURCE_DIR + "/" + loaded["archive_name"], *install_docs[1:],
    ]
    plan_result = {
        "status": "plan" if plan else "packaged",
        "candidate": str(loaded["path"]),
        "output_parent": str(parent),
        "output": str(output),
        "product": {"id": "nl-coding-agent", "version": version},
        "git_head": loaded["git_head"],
        "source_archive": {
            "name": loaded["archive_name"],
            "sha256": loaded["archive_sha256"],
            "size": loaded["archive_size"],
            "file_count": loaded["archive_file_count"],
        },
        "files": planned_files,
        "writes": [],
    }
    if plan:
        return plan_result
    if parent.exists() and not parent.is_dir():
        raise BetaPackageError("output parent exists and is not a directory: " + str(parent))
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="." + package_name + ".building-",
                                    dir=str(parent)))
    try:
        (staging / SOURCE_DIR).mkdir()
        shutil.copyfile(loaded["path"] / loaded["archive_name"],
                        staging / SOURCE_DIR / loaded["archive_name"])
        (staging / "install").mkdir()
        (staging / PLATFORM_MANIFEST_NAME).parent.mkdir(parents=True, exist_ok=True)
        (staging / PLATFORM_MANIFEST_NAME).write_bytes(_json_bytes(platform_manifest))
        (staging / RUNTIME_MANIFEST_NAME).write_bytes(_json_bytes(runtime_manifest))
        (staging / INSTALL_NAME).write_bytes(
            _text_bytes(chr(10).join(_install_common_lines(version))))
        for target_id in release_builder.TARGET_ORDER:
            descriptor = release_builder.SUPPORTED_TARGETS[target_id]
            (staging / "install" / ("INSTALL-" + target_id + ".md")).write_bytes(
                _text_bytes(chr(10).join(_install_platform_lines(version, target_id, descriptor))))
        (staging / README_NAME).write_bytes(
            _text_bytes(chr(10).join(_beta_readme_lines(version, loaded["git_head_short"]))))
        (staging / VERSION_NAME).write_bytes(_text_bytes(version))
        inventory = [
            {"path": rel, "sha256": digest, "size": size}
            for rel, digest, size in _checksum_lines(staging)
            if rel not in (MANIFEST_NAME, SHA256SUMS_NAME)
        ]
        payload_size = sum(item["size"] for item in inventory)
        beta_manifest = {
            "schema_version": SCHEMA_VERSION,
            "package_format": PACKAGE_FORMAT,
            "channel": "beta",
            "product": {"id": "nl-coding-agent", "name": "NL Coding Agent",
                        "version": version},
            "source": {
                "git_head": loaded["git_head"],
                "git_head_short": loaded["git_head_short"],
                "tracked_hash": loaded["tracked_hash"],
                "candidate_manifest": "release-manifest.json",
                "archive": {
                    "name": SOURCE_DIR + "/" + loaded["archive_name"],
                    "sha256": loaded["archive_sha256"],
                    "size": loaded["archive_size"],
                    "file_count": loaded["archive_file_count"],
                    "format": "zip",
                },
            },
            "payload": {
                "root": ".",
                "payload_file_count": len(inventory) + 2,
                "inventory_file_count": len(inventory),
                "inventory_total_size": payload_size,
                "inventory_excludes": [MANIFEST_NAME, SHA256SUMS_NAME],
                "inventory": inventory,
            },
            "checksums": {
                "algorithm": "sha256",
                "file": SHA256SUMS_NAME,
                "covers": "all payload files except SHA256SUMS itself",
            },
            "platforms": platform_matrix,
            "universal2": {
                "supported": False,
                "decision": "separate-per-arch",
                "evidence": UNIVERSAL2_EVIDENCE,
            },
            "validation": {
                "ci_flags": list(CI_FLAGS),
                "manual_pending": list(MANUAL_PENDING_ITEMS),
                "release_ready": False,
                "runtime_components_measured": False,
            },
            "installers": {
                "platform_manifest": PLATFORM_MANIFEST_NAME,
                "runtime_manifest": RUNTIME_MANIFEST_NAME,
                "install_docs": install_docs,
            },
            "notes": [
                "deterministic beta package: no timestamps, absolute paths or environment data",
                "no runtime, vendor checkout, user data or workspace content is bundled",
                "native six-target runtimes are MANUAL-PENDING and no hashes are fabricated",
            ],
        }
        (staging / MANIFEST_NAME).write_bytes(_json_bytes(beta_manifest))
        _write_sums(staging)
        if output.exists():
            raise BetaPackageError(
                "beta package output appeared during the build; refusing to overwrite: "
                + str(output)
            )
        os.replace(staging, output)
    except Exception:
        _cleanup(staging)
        raise
    result = dict(plan_result)
    result.update({
        "status": "packaged",
        "writes": ["beta package directory created: " + str(output)],
        "files": len(_checksum_lines(output)) + 1,
        "inventory_file_count": len(beta_manifest["payload"]["inventory"]),
        "sha256sums": str(output / SHA256SUMS_NAME),
        "manifest": str(output / MANIFEST_NAME),
    })
    return result


def _cleanup(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic private-beta package from a source release candidate."
    )
    parser.add_argument("--candidate", default=None,
                        help="source release candidate directory (default: newest under .workspace/dist)")
    parser.add_argument("--source", default=str(REPO_ROOT),
                        help="repository root containing nl_coding_agent/core/version.py")
    parser.add_argument("--output-parent", default=None,
                        help="parent for the NEW beta-<version> directory (default: <source>/.workspace/dist)")
    parser.add_argument("--name", default=None,
                        help="package directory name override (default beta-<version>)")
    parser.add_argument("--plan", action="store_true", help="print the plan; write nothing")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_beta_package(
            args.candidate, source=args.source, output_parent=args.output_parent,
            name=args.name, plan=args.plan,
        )
    except BetaPackageError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Beta package " + result["status"] + ": " + result["output"])
        if result.get("product"):
            print("Version: " + str(result["product"].get("version")))
        if result.get("git_head"):
            print("Git head: " + str(result["git_head"]))
        if result.get("source_archive"):
            print("Source archive: " + str(result["source_archive"]["name"])
                  + " (" + str(result["source_archive"]["size"]) + " bytes)")
        if args.plan:
            print("No files were written (plan mode).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

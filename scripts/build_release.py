"""Reproducible source-only release package builder (stage 6a foundation).

Builds a deterministic source zip from git-tracked files, plus two generated
manifests:

  * release-manifest.json - reproducibility evidence: version (from
    nl_coding_agent/core/version.py), git head, tracked-file inventory with
    per-file sha256/size, archive sha256/size, aggregate counts, platform
    matrix and explicit exclusions.
  * platform-manifest.json - the manifest consumed by installer/bootstrap.py
    (schema in installer/platform_manifest.py), with a relative component URL so
    the candidate directory itself works as an offline bundle.

Guarantees:
  * only git-tracked files are packaged (untracked files are never included);
  * user data, logs, dist, build, embedded runtime, vendor checkouts, caches,
    machine-local config and patch/temp artifacts are excluded;
  * no timestamps, absolute paths or environment data enter the manifests, and
    zip entries use fixed metadata, so identical inputs produce identical
    manifest bytes and identical archive bytes;
  * writes only a NEW candidate directory (refuses to overwrite an existing one)
    and never deletes, moves or rewrites anything;
  * python/ and crewAI/ are never copied by default; an optional
    --with-runtime-archive references a caller-supplied prebuilt runtime zip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_NAME = "build_release.py"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = 1
NL = chr(10)
FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
ZIP_COMPRESS_LEVEL = 9

EXCLUDED_ROOTS = (
    ".git",
    ".agents",
    "build",
    "crewAI",
    "crewAI-tools",
    "data",
    "dist",
    "logs",
    "PATCH",
    "python",
    "state",
)
EXCLUDED_DIR_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cache", ".tox", ".nox", "htmlcov", ".venv", "venv", "node_modules",
    "Scripts",
})
EXCLUDED_FILES = frozenset({
    ".env",
    "config/voicebridge.yaml",
    "config/voicebridge.local.yaml",
    "SHA256_MANIFEST.json",
})
EXCLUDED_SUFFIXES = frozenset({
    ".pyc", ".pyo", ".pyd", ".sqlite3", ".db", ".log", ".egg-info",
})
DEFAULT_PLATFORMS = {
    "windows-x86_64": "Windows 11 x64",
    "linux-x86_64": "Linux x86_64",
}
DEFAULT_LAUNCHERS = {
    "windows-x86_64": "NL Coding Agent.bat",
    "linux-x86_64": "NL Coding Agent.sh",
}
DEFAULT_BASE_URL = "https://downloads.example.invalid/nl-coding-agent"
DEFAULT_RUNTIME_VERSION = "3.12.10"


class ReleaseError(RuntimeError):
    """Raised when a release build cannot be produced safely or reproducibly."""


def read_version(source: Path) -> str:
    version_file = source / "nl_coding_agent" / "core" / "version.py"
    if not version_file.is_file():
        raise ReleaseError("version file not found: " + str(version_file))
    try:
        text = version_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseError("cannot read version file: " + str(exc)) from exc
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("APP_VERSION") and "=" in stripped:
            value = stripped.split("=", 1)[1].strip()
            if value[:1] in ("'", '"'):
                quote = value[0]
                end = value.find(quote, 1)
                if end > 0:
                    return value[1:end]
            if value:
                return value
    raise ReleaseError("APP_VERSION not found in " + str(version_file))


def git_head(source: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseError("cannot read git HEAD: " + str(exc)) from exc
    head = (result.stdout or "").strip()
    if result.returncode != 0 or not head:
        raise ReleaseError("cannot read git HEAD (not a git repository?): "
                           + (result.stderr or "").strip())
    return head


def tracked_files(source: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(source), "ls-files", "-z"],
            capture_output=True, timeout=60, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseError("cannot list tracked files: " + str(exc)) from exc
    if result.returncode != 0:
        raise ReleaseError("cannot list tracked files: "
                           + result.stderr.decode("utf-8", "replace").strip())
    names = result.stdout.decode("utf-8", "replace").split(chr(0))
    return sorted(name for name in names if name)


def is_excluded(rel: str) -> bool:
    parts = [part for part in rel.split("/") if part]
    if not parts:
        return True
    if parts[0] in EXCLUDED_ROOTS:
        return True
    if any(part in EXCLUDED_DIR_NAMES for part in parts):
        return True
    if rel in EXCLUDED_FILES:
        return True
    suffix = Path(rel).suffix.lower()
    if suffix in EXCLUDED_SUFFIXES:
        return True
    name = parts[-1]
    if name.startswith("temp_") and name.endswith(".py"):
        return True
    if name.endswith(".patch"):
        return True
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def collect_files(source: Path, *, tracked: list[str] | None = None) -> list[dict]:
    candidates = tracked if tracked is not None else tracked_files(source)
    files: list[dict] = []
    seen: set[str] = set()
    for rel in sorted(candidates):
        rel_text = rel.replace(chr(92), "/")
        if rel_text in seen:
            continue
        seen.add(rel_text)
        if is_excluded(rel_text):
            continue
        path = source / rel_text
        if not path.is_file():
            raise ReleaseError("tracked file is missing from the working tree: " + rel_text)
        size = path.stat().st_size
        files.append({"path": rel_text, "size": size, "sha256": sha256_file(path)})
    if not files:
        raise ReleaseError("no tracked files to package after exclusions")
    return files


def tracked_hash(files: list[dict]) -> str:
    material = "".join(item["path"] + chr(0) + item["sha256"] + chr(0) for item in files)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_zip(source: Path, files: list[dict], zip_path: Path) -> tuple[str, int]:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=ZIP_COMPRESS_LEVEL) as archive:
        for entry in files:
            info = zipfile.ZipInfo(entry["path"], date_time=FIXED_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits = 0
            archive.writestr(info, (source / entry["path"]).read_bytes())
    return sha256_file(zip_path), zip_path.stat().st_size


def build_platform_manifest(
    *,
    version: str,
    zip_name: str,
    zip_sha256: str,
    zip_size: int,
    platforms: dict[str, str],
    launchers: dict[str, str],
    base_url: str,
    runtime_archive: dict | None = None,
) -> dict:
    platform_entries: dict[str, dict] = {}
    components: list[dict] = []
    runtime_components: dict[str, dict] = {}
    for platform_id in sorted(platforms):
        runtime_id = "python-runtime-" + platform_id
        runtime_components[platform_id] = {
            "id": runtime_id,
            "kind": "runtime",
            "version": (runtime_archive or {}).get("version", DEFAULT_RUNTIME_VERSION),
            "archive": "zip",
            "destination": "python",
            "sha256": "",
            "size": 0,
            "url": "components/" + runtime_id + ".zip",
            "platforms": [platform_id],
            "optional": True,
            "placeholder": True,
        }
    ordered_components: list[dict] = []
    ordered_components.append({
        "id": "app-source",
        "kind": "app",
        "version": version,
        "archive": "zip",
        "destination": ".",
        "sha256": zip_sha256,
        "size": zip_size,
        "url": zip_name,
        "platforms": sorted(platforms),
        "placeholder": False,
    })
    if runtime_archive:
        runtime_platform = runtime_archive["platform"]
        if runtime_platform not in platforms:
            raise ReleaseError("runtime archive platform is not in the manifest platforms: "
                               + str(runtime_platform))
        runtime_id = "python-runtime-" + runtime_platform
        ordered_components.append({
            "id": runtime_id,
            "kind": "runtime",
            "version": str(runtime_archive["version"]),
            "archive": "zip",
            "destination": "python",
            "sha256": str(runtime_archive["sha256"]),
            "size": int(runtime_archive["size"]),
            "url": "runtime/" + str(runtime_archive["name"]),
            "platforms": [runtime_platform],
            "placeholder": False,
        })
        runtime_components[runtime_platform] = ordered_components[-1]
    existing_ids = {component["id"] for component in ordered_components}
    for key in sorted(runtime_components):
        if runtime_components[key]["id"] not in existing_ids:
            ordered_components.append(runtime_components[key])
    for platform_id in sorted(platforms):
        included = ["app-source"]
        runtime_component = runtime_components[platform_id]
        if runtime_archive and runtime_archive["platform"] == platform_id:
            included = [runtime_component["id"], "app-source"]
        platform_entries[platform_id] = {
            "display_name": platforms[platform_id],
            "launcher": launchers.get(platform_id, DEFAULT_LAUNCHERS.get(platform_id, "nl_agent.py")),
            "runtime_component": runtime_component["id"],
            "components": included,
        }
    return {
        "schema_version": 1,
        "status": "release",
        "release_ready": True,
        "generated_by": TOOL_NAME + " " + TOOL_VERSION,
        "product": {
            "id": "nl-coding-agent",
            "name": "NL Coding Agent",
            "version": version,
            "channel": "source",
        },
        "base_urls": {"primary": base_url.rstrip("/"), "mirrors": []},
        "platforms": platform_entries,
        "components": ordered_components,
    }


def build_release(
    source: str | Path,
    output_parent: str | Path | None = None,
    *,
    name: str | None = None,
    plan: bool = False,
    tracked: list[str] | None = None,
    head: str | None = None,
    version: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    platforms: dict[str, str] | None = None,
    launchers: dict[str, str] | None = None,
    runtime_archive: str | Path | None = None,
    runtime_platform: str = "windows-x86_64",
    runtime_version: str = DEFAULT_RUNTIME_VERSION,
) -> dict:
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise ReleaseError("source directory not found: " + str(source_path))
    parent = Path(output_parent).resolve() if output_parent else source_path / "dist"
    release_version = version or read_version(source_path)
    release_head = head or git_head(source_path)
    platform_map = dict(platforms or DEFAULT_PLATFORMS)
    launcher_map = dict(launchers or DEFAULT_LAUNCHERS)
    for platform_id in platform_map:
        if platform_id not in launcher_map:
            raise ReleaseError("no launcher configured for platform: " + platform_id)
    files = collect_files(source_path, tracked=tracked)
    source_hash = tracked_hash(files)
    candidate_name = name or ("release-candidate-" + release_version + "-"
                              + release_head[:12])
    candidate = parent / candidate_name
    if candidate.exists():
        raise ReleaseError("candidate output already exists; refusing to overwrite: "
                           + str(candidate))
    runtime_info: dict | None = None
    if runtime_archive:
        runtime_path = Path(runtime_archive).resolve()
        if not runtime_path.is_file():
            raise ReleaseError("runtime archive not found: " + str(runtime_path))
        if runtime_path.suffix.lower() != ".zip":
            raise ReleaseError("runtime archive must be a .zip file: " + str(runtime_path))
        runtime_info = {
            "name": runtime_path.name,
            "sha256": sha256_file(runtime_path),
            "size": runtime_path.stat().st_size,
            "platform": runtime_platform,
            "version": runtime_version,
            "source_name": runtime_path.name,
        }
    plan_result = {
        "status": "plan",
        "product": {"id": "nl-coding-agent", "version": release_version},
        "git_head": release_head,
        "source_tracked_hash": source_hash,
        "tracked_files": len(files),
        "total_bytes": sum(entry["size"] for entry in files),
        "candidate": str(candidate),
        "zip_name": "nl-coding-agent-" + release_version + "-source.zip",
        "platforms": sorted(platform_map),
        "runtime_archive": runtime_info,
        "writes": [],
    }
    if plan:
        return plan_result
    if parent.exists() and not parent.is_dir():
        raise ReleaseError("output parent exists and is not a directory: " + str(parent))
    parent.mkdir(parents=True, exist_ok=True)
    candidate.mkdir(parents=True, exist_ok=False)
    zip_name = "nl-coding-agent-" + release_version + "-source.zip"
    zip_path = candidate / zip_name
    zip_sha256, zip_size = build_zip(source_path, files, zip_path)

    release_manifest = {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "product": {
            "id": "nl-coding-agent",
            "name": "NL Coding Agent",
            "version": release_version,
            "channel": "source",
        },
        "source": {
            "git_head": release_head,
            "git_head_short": release_head[:12],
            "tracked_files": len(files),
            "tracked_hash": source_hash,
        },
        "archive": {
            "name": zip_name,
            "format": "zip",
            "sha256": zip_sha256,
            "size": zip_size,
            "file_count": len(files),
            "total_bytes": sum(entry["size"] for entry in files),
        },
        "files": files,
        "platforms": {
            platform_id: {
                "display_name": platform_map[platform_id],
                "launcher": launcher_map[platform_id],
                "runtime_component": "python-runtime-" + platform_id,
                "runtime_bundled": bool(runtime_info
                                        and runtime_info["platform"] == platform_id),
            }
            for platform_id in sorted(platform_map)
        },
        "runtime": runtime_info,
        "excluded_roots": sorted(EXCLUDED_ROOTS),
        "excluded_dir_names": sorted(EXCLUDED_DIR_NAMES),
        "excluded_files": sorted(EXCLUDED_FILES),
        "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
        "excluded_patterns": ["temp_*.py", "*.patch"],
        "notes": [
            "source-only release: embedded python/ and crewAI/ are never copied by default",
            "identical tracked inputs produce identical manifests and archive bytes",
            "offline install: pass this candidate directory to installer/bootstrap.py --offline-bundle",
        ],
    }
    release_manifest_path = candidate / "release-manifest.json"
    release_manifest_path.write_text(
        json.dumps(release_manifest, indent=2, ensure_ascii=False, sort_keys=True) + NL,
        encoding="utf-8",
    )
    platform_manifest = build_platform_manifest(
        version=release_version,
        zip_name=zip_name,
        zip_sha256=zip_sha256,
        zip_size=zip_size,
        platforms=platform_map,
        launchers=launcher_map,
        base_url=base_url,
        runtime_archive=runtime_info,
    )
    platform_manifest_path = candidate / "platform-manifest.json"
    platform_manifest_path.write_text(
        json.dumps(platform_manifest, indent=2, ensure_ascii=False, sort_keys=True) + NL,
        encoding="utf-8",
    )
    if runtime_info:
        runtime_target = candidate / "runtime" / runtime_info["name"]
        runtime_target.parent.mkdir(parents=True, exist_ok=True)
        runtime_target.write_bytes(Path(runtime_archive).resolve().read_bytes())
    return {
        "status": "built",
        "candidate": str(candidate),
        "product": release_manifest["product"],
        "git_head": release_head,
        "source_tracked_hash": source_hash,
        "files": len(files),
        "total_bytes": release_manifest["archive"]["total_bytes"],
        "archive": {"path": str(zip_path), "sha256": zip_sha256, "size": zip_size},
        "release_manifest": str(release_manifest_path),
        "platform_manifest": str(platform_manifest_path),
        "runtime_bundled": bool(runtime_info),
        "writes": ["candidate directory created: " + str(candidate)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a reproducible source-only release candidate (never overwrites).",
    )
    parser.add_argument("--source", default=str(REPO_ROOT))
    parser.add_argument("--output-parent", default=None,
                        help="parent directory for the new candidate (default: <source>/dist)")
    parser.add_argument("--name", default=None, help="candidate directory name override")
    parser.add_argument("--head", default=None,
                        help="git HEAD override for exported sources without .git (advanced)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--plan", action="store_true", help="print the plan; write nothing")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--with-runtime-archive", default=None,
                        help="optional prebuilt runtime .zip to bundle (python/ is never copied)")
    parser.add_argument("--runtime-platform", default="windows-x86_64")
    parser.add_argument("--runtime-version", default=DEFAULT_RUNTIME_VERSION)
    args = parser.parse_args(argv)
    try:
        result = build_release(
            args.source,
            args.output_parent,
            name=args.name,
            head=args.head,
            plan=args.plan,
            base_url=args.base_url,
            runtime_archive=args.with_runtime_archive,
            runtime_platform=args.runtime_platform,
            runtime_version=args.runtime_version,
        )
    except ReleaseError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Release " + result["status"] + ": " + str(result.get("candidate")))
        if result.get("product"):
            print("Product: " + str(result["product"].get("name")) + " "
                  + str(result["product"].get("version")))
        print("Git head: " + str(result.get("git_head")))
        print("Files: " + str(result.get("files")) + " ("
              + str(result.get("total_bytes")) + " bytes)")
        if result.get("archive"):
            print("Archive: " + str(result["archive"]["path"]))
            print("Archive sha256: " + str(result["archive"]["sha256"]))
        if args.plan:
            print("No files were written (plan mode).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CI reproducibility check for the stage-6 source release.

Builds the reproducible source release TWICE from the committed tree with the
existing scripts.build_release contract (no changes to that builder), in a
managed temporary workspace, then compares the candidates:

* source archive sha256 + size + member list;
* the release, platform and runtime manifests byte-for-byte;
* internal consistency (manifest archive/component digests match the real zip,
  zip members match the release file list, runtime manifest validates and keeps
  six targets with unmeasured placeholders);
* forbidden content: no .workspace/.git/data/runtime/vendor/dev files in the
  candidate or in the source archive.

The tool writes a JSON PASS/FAIL report (plus a short Markdown summary) only when
--report-dir is given; otherwise it writes nothing outside the temporary
workspace. Exit 0 = PASS, 1 = mismatch/forbidden content/build failure, 2 = usage.

Safety: no network request, no model call, no publishing/uploading/tagging, no
execution of generated code, no writes to the repository; the temporary workspace
is always removed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.build_release as release_builder  # noqa: E402
from installer.platform_manifest import (  # noqa: E402
    ManifestError,
    validate_manifest as validate_platform_manifest,
)
from installer.platform_targets import TARGET_ORDER  # noqa: E402
from installer.runtime_manifest import (  # noqa: E402
    RuntimeManifestError,
    validate_runtime_manifest,
)

TOOL_NAME = "reproducibility_check.py"
TOOL_VERSION = "0.1.0"
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
MANIFEST_NAMES = ("release-manifest.json", "platform-manifest.json", "runtime-manifest.json")
REPORT_JSON = "reproducibility_check.json"
REPORT_MARKDOWN = "reproducibility_check.md"

FORBIDDEN_DIR_PREFIXES = (
    ".git/", ".workspace/", ".agents/", "data/", "python/", "crewai/",
    "crewai-tools/", "da_eliminare/", "patch/", "dist/", "build/", "logs/",
    "state/", "cache/", "temp/", ".venv/", "venv/", "node_modules/",
)
FORBIDDEN_DIR_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git",
    ".workspace", "node_modules", ".venv",
})
FORBIDDEN_FILES = frozenset({
    ".env", "sha256_manifest.json", "config/voicebridge.yaml",
    "config/voicebridge.local.yaml",
})
FORBIDDEN_SUFFIXES = (
    ".pyc", ".pyo", ".pyd", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm",
    ".db", ".log",
)
DEV_FILE_PREFIX = "temp_"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _display_path(path: Path | str | None) -> str:
    if path is None:
        return ""
    value = Path(path)
    try:
        return value.resolve().relative_to(REPO_ROOT).as_posix()
    except (OSError, ValueError):
        return value.name


def _git_head() -> str | None:
    git_dir = REPO_ROOT / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = git_dir / head[len("ref: "):].strip()
            return ref.read_text(encoding="utf-8").strip() or None
        return head or None
    except OSError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def forbidden_reason(path: str) -> str | None:
    """Return a short reason when a payload path must never be shipped; else None."""
    text = str(path).replace(chr(92), "/").strip()
    lowered = text.lower()
    parts = [part for part in lowered.split("/") if part]
    if not parts:
        return "empty path"
    for prefix in FORBIDDEN_DIR_PREFIXES:
        if lowered.startswith(prefix):
            return "directory:" + prefix
    for part in parts:
        if part in FORBIDDEN_DIR_NAMES:
            return "directory-name:" + part
    if lowered in FORBIDDEN_FILES:
        return "file:" + lowered
    suffixes = tuple(FORBIDDEN_SUFFIXES)
    if lowered.endswith(suffixes):
        return "suffix:" + lowered.rsplit(".", 1)[-1]
    basename = parts[-1]
    if basename.startswith(DEV_FILE_PREFIX) and basename.endswith(".py"):
        return "dev-script:" + basename
    if basename.endswith(".patch"):
        return "dev-patch:" + basename
    return None


def scan_forbidden_paths(paths: list[str]) -> list[dict]:
    found = []
    for path in paths:
        reason = forbidden_reason(path)
        if reason:
            found.append({"path": path, "reason": reason})
    return found


def _check(checks: list[dict], check_id: str, ok: bool, detail: str = "") -> None:
    checks.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                   "detail": str(detail)})


def collect_candidate(candidate: Path, label: str) -> dict:
    """Collect stable, machine-comparable facts about one built candidate."""
    candidate = Path(candidate)
    files = sorted(path.relative_to(candidate).as_posix()
                   for path in candidate.rglob("*") if path.is_file())
    zips = [name for name in files if "/" not in name and name.endswith("-source.zip")]
    archive = None
    if len(zips) == 1:
        archive_path = candidate / zips[0]
        archive = {
            "name": zips[0],
            "sha256": sha256_file(archive_path),
            "size": archive_path.stat().st_size,
        }
    manifests = {}
    for name in MANIFEST_NAMES:
        path = candidate / name
        manifests[name] = {
            "present": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else None,
            "size": path.stat().st_size if path.is_file() else None,
        }
    return {
        "label": label,
        "candidate": _display_path(candidate),
        "files": files,
        "file_count": len(files),
        "files_sha256": sha256_bytes(chr(10).join(files).encode("utf-8")),
        "archive": archive,
        "manifests": manifests,
    }


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_checks(candidate: Path, run: dict, checks: list[dict]) -> None:
    label = run["label"]
    expected = set(MANIFEST_NAMES)
    if run["archive"] is not None:
        expected.add(run["archive"]["name"])
    actual = set(run["files"])
    _check(checks, "candidate_expected_files_" + label, expected == actual,
           "expected=" + repr(sorted(expected)) + " actual=" + repr(sorted(actual)))
    _check(checks, "single_source_archive_" + label, run["archive"] is not None,
           "found=" + repr([name for name in run["files"] if name.endswith("-source.zip")]))
    for name in MANIFEST_NAMES:
        entry = run["manifests"][name]
        _check(checks, "manifest_present_" + label + "_" + name, bool(entry["present"]),
               "size=" + str(entry["size"]))
    archive = run["archive"]
    if archive is None:
        return
    archive_path = candidate / archive["name"]
    if not archive_path.is_file():
        _check(checks, "archive_readable_" + label, False, "missing archive")
        return
    release = _load_json(candidate / "release-manifest.json")
    release_archive = release.get("archive") or {}
    _check(checks, "release_manifest_archive_identity_" + label,
           release_archive.get("sha256") == archive["sha256"]
           and int(release_archive.get("size") or -1) == archive["size"]
           and str(release_archive.get("name") or "") == archive["name"],
           "manifest=" + str(release_archive.get("sha256"))[:16] + "/"
           + str(release_archive.get("size")))
    manifest_files = sorted(str(item.get("path") or "") for item in release.get("files") or [])
    with zipfile.ZipFile(archive_path) as archive_zip:
        members = sorted(archive_zip.namelist())
    _check(checks, "release_manifest_file_list_matches_zip_" + label,
           manifest_files == members,
           "manifest=" + str(len(manifest_files)) + " zip=" + str(len(members)))
    _check(checks, "release_manifest_file_count_" + label,
           int(release_archive.get("file_count") or -1) == len(manifest_files),
           "count=" + str(release_archive.get("file_count")))
    found = scan_forbidden_paths(manifest_files)
    _check(checks, "no_forbidden_files_in_archive_" + label, not found,
           "found=" + repr(found[:10]))
    extra = scan_forbidden_paths(sorted(actual - expected))
    _check(checks, "no_forbidden_extra_candidate_files_" + label, not extra,
           "found=" + repr(extra[:10]))
    platform_manifest = _load_json(candidate / "platform-manifest.json")
    try:
        validate_platform_manifest(platform_manifest)
        platform_ok = True
        platform_detail = "schema validated"
    except (ManifestError, ValueError) as exc:
        platform_ok = False
        platform_detail = str(exc)
    _check(checks, "platform_manifest_valid_" + label, platform_ok, platform_detail)
    app_components = [component for component in platform_manifest.get("components") or []
                      if str(component.get("kind")) == "app"]
    app_ok = any(str(component.get("sha256")) == archive["sha256"]
                 and int(component.get("size") or -1) == archive["size"]
                 for component in app_components)
    _check(checks, "platform_manifest_app_component_matches_archive_" + label, app_ok,
           "app_components=" + str(len(app_components)))
    runtime_manifest = _load_json(candidate / "runtime-manifest.json")
    try:
        validate_runtime_manifest(runtime_manifest)
        runtime_ok = True
        runtime_detail = "schema validated"
    except (RuntimeManifestError, ValueError) as exc:
        runtime_ok = False
        runtime_detail = str(exc)
    _check(checks, "runtime_manifest_valid_" + label, runtime_ok, runtime_detail)
    targets = (runtime_manifest.get("targets") or {})
    _check(checks, "runtime_manifest_six_targets_" + label,
           set(targets) == set(TARGET_ORDER), "targets=" + str(sorted(targets)))
    unmeasured_honest = True
    for target_id, entry in targets.items():
        runtime = (entry or {}).get("runtime") or {}
        if not bool(runtime.get("measured")):
            if str(runtime.get("sha256") or "") != "" or int(runtime.get("size") or 0) != 0:
                unmeasured_honest = False
    _check(checks, "runtime_manifest_unmeasured_placeholders_" + label,
           unmeasured_honest and runtime_manifest.get("release_ready") is False,
           "release_ready=" + str(runtime_manifest.get("release_ready")))


def compare_runs(run1: dict, run2: dict) -> tuple[list[dict], dict]:
    checks: list[dict] = []
    comparisons: dict = {}

    def same(key: str, left, right, check_id: str) -> None:
        ok = left == right
        comparisons[key] = bool(ok)
        _check(checks, check_id, ok, "run1=" + repr(left) + " run2=" + repr(right))

    same("archive_sha256_equal", (run1["archive"] or {}).get("sha256"),
         (run2["archive"] or {}).get("sha256"), "archive_sha256_equal")
    same("archive_size_equal", (run1["archive"] or {}).get("size"),
         (run2["archive"] or {}).get("size"), "archive_size_equal")
    same("file_list_equal", run1["files"], run2["files"], "file_list_equal")
    same("file_count_equal", run1["file_count"], run2["file_count"], "file_count_equal")
    same("files_sha256_equal", run1["files_sha256"], run2["files_sha256"],
         "files_sha256_equal")
    for name in MANIFEST_NAMES:
        key = name.replace("-", "_").replace(".json", "") + "_byte_identical"
        comparisons[key] = (run1["manifests"][name]["sha256"]
                            == run2["manifests"][name]["sha256"])
        _check(checks, key, comparisons[key],
               "run1=" + str(run1["manifests"][name]["sha256"])[:16]
               + " run2=" + str(run2["manifests"][name]["sha256"])[:16])
    return checks, comparisons


def _summary(checks: list[dict]) -> dict:
    passed = sum(1 for item in checks if item["status"] == "PASS")
    failed = len(checks) - passed
    return {"checks": len(checks), "passed": passed, "failed": failed}


def run_reproducibility(source: str | Path = REPO_ROOT, *,
                        workspace_root: str | Path | None = None) -> dict:
    """Build twice and compare; return the PASS/FAIL report (never writes reports)."""
    started = time.monotonic()
    source_path = Path(source).resolve()
    report: dict = {
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "generated_at": _utc_now(),
        "mode": "reproducible-source-release",
        "status": "FAIL",
        "source": {"path": _display_path(source_path), "git_head": _git_head()},
        "workspace": {"managed": True, "cleaned": False},
        "runs": [],
        "checks": [],
        "comparisons": {},
        "forbidden": {"ok": False, "found": []},
        "support_claim": False,
        "ci_vs_manual_pending": (
            "This check proves byte-identical source-release builds on the current host "
            "(and, when the CI job runs externally, on each matrix runner). It is not "
            "platform support: real runtimes, installers, clean machines and hardware "
            "stay MANUAL-PENDING, and a green CI run is not an acceptance claim."
        ),
    }
    checks = report["checks"]
    if not source_path.is_dir():
        _check(checks, "source_directory_present", False, str(source_path))
        report["summary"] = _summary(checks)
        report["status"] = "FAIL"
        report["duration_s"] = round(time.monotonic() - started, 3)
        return report
    managed = workspace_root is None
    temporary = tempfile.TemporaryDirectory(prefix="nl-ci-repro-") if managed else None
    try:
        root = Path(temporary.name) if temporary is not None else Path(workspace_root).resolve()
        if not managed:
            root.mkdir(parents=True, exist_ok=True)
        runs: list[dict | None] = []
        for label, directory in (("run1", root / "run1"), ("run2", root / "run2")):
            try:
                result = release_builder.build_release(source_path, directory, name="candidate")
                candidate = Path(result["candidate"]).resolve()
                try:
                    candidate.relative_to(root)
                    inside_workspace = True
                except ValueError:
                    inside_workspace = False
                _check(checks, "build_" + label, inside_workspace,
                       "candidate=" + _display_path(candidate))
                runs.append(collect_candidate(candidate, label))
            except Exception as exc:  # noqa: BLE001 - reported as a deterministic failure
                _check(checks, "build_" + label, False, type(exc).__name__ + ": " + str(exc))
                runs.append(None)
        report["runs"] = [run for run in runs if run is not None]
        if all(run is not None for run in runs):
            for run in runs:
                directory = root / str(run["label"]) / "candidate"
                _candidate_checks(directory, run, checks)
            comparison_checks, comparisons = compare_runs(runs[0], runs[1])
            checks.extend(comparison_checks)
            report["comparisons"] = comparisons
            forbidden_found = []
            for run in runs:
                release_path = root / str(run["label"]) / "candidate" / "release-manifest.json"
                try:
                    release = _load_json(release_path)
                    paths = [str(item.get("path") or "") for item in release.get("files") or []]
                    forbidden_found.extend({"run": run["label"], **item}
                                           for item in scan_forbidden_paths(paths))
                except (OSError, ValueError):
                    forbidden_found.append({"run": run["label"], "path": "*",
                                            "reason": "release manifest unreadable"})
            report["forbidden"] = {"ok": not forbidden_found, "found": forbidden_found}
    finally:
        if temporary is not None:
            temporary.cleanup()
            report["workspace"] = {"managed": True, "cleaned": True}
        else:
            report["workspace"] = {"managed": False, "cleaned": False}
    report["duration_s"] = round(time.monotonic() - started, 3)
    failed = [check for check in checks if check["status"] != "PASS"]
    report["status"] = "PASS" if not failed and report["forbidden"]["ok"] else "FAIL"
    report["summary"] = _summary(checks)
    return report


def _markdown(report: dict) -> str:
    ticks = chr(96)
    lines = [
        "# Reproducible source-release check",
        "",
        "Status: **" + report["status"] + "**",
        "",
        "Source: " + ticks + str(report["source"]["path"]) + ticks + " at " + ticks
        + str(report["source"]["git_head"]) + ticks,
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for check in report["checks"]:
        lines.append("| " + str(check["id"]) + " | " + str(check["status"]) + " | "
                     + str(check["detail"]).replace("|", "/") + " |")
    lines.extend([
        "",
        "Temporary workspace: managed=" + str(report["workspace"]["managed"])
        + ", cleaned=" + str(report["workspace"]["cleaned"]),
        "",
        "A PASS is reproducibility evidence only; real runtimes, clean-machine install "
        "and hardware acceptance remain MANUAL-PENDING. No artifact was published.",
        "",
    ])
    return chr(10).join(lines)


def write_reports(report: dict, report_dir: str | Path) -> dict:
    """Write only the two report artifacts under report_dir."""
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / REPORT_JSON
    markdown_path = directory / REPORT_MARKDOWN
    report["artifacts"] = {"report_json": _display_path(json_path),
                           "report_markdown": _display_path(markdown_path)}
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + chr(10),
                         encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return report["artifacts"]


def _print_summary(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(TOOL_NAME + " " + TOOL_VERSION + " - " + report["status"])
    print("Source: " + str(report["source"]["path"]) + " @ "
          + str(report["source"]["git_head"]))
    for check in report["checks"]:
        if check["status"] != "PASS":
            print("  FAIL  " + check["id"] + " - " + check["detail"])
    print("PASS " + str(report["summary"]["passed"]) + "/"
          + str(report["summary"]["checks"]) + " checks; temp workspace "
          + ("removed" if report["workspace"]["cleaned"] else "not removed") + ".")
    if report.get("artifacts"):
        print("Reports: " + str(report["artifacts"]["report_json"]) + ", "
              + str(report["artifacts"]["report_markdown"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Build the source release twice and verify byte-level "
                    "reproducibility (no network, no publishing).",
    )
    parser.add_argument("--source", default=str(REPO_ROOT),
                        help="committed source tree to build from (default: repository root)")
    parser.add_argument("--report-dir", default=None,
                        help="write report artifacts only into this directory")
    parser.add_argument("--workspace", default=None,
                        help="managed workspace root override (advanced; not removed by the tool)")
    parser.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_reproducibility(args.source, workspace_root=args.workspace)
    if args.report_dir:
        write_reports(report, args.report_dir)
    _print_summary(report, as_json=bool(args.json))
    return EXIT_PASS if report["status"] == "PASS" else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())

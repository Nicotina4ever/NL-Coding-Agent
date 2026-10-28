"""CI packaging/acceptance smoke for the private beta (managed temp workspace).

Runs entirely locally in a temporary workspace with no network, no model and no
upload/publish action:

  1. build a source release candidate from the committed tree via the
     scripts.build_release functions (temporary output);
  2. build a beta package from that candidate via scripts.build_beta_packages;
  3. run the release-acceptance matrix (scripts.release_acceptance) against a
     temporary empty records directory and enforce the six-target /
     all-MANUAL-PENDING / no-CI-hardware-claim invariants;
  4. run the native-runtime acquisition plan in dry-run mode
     (scripts.fetch_native_runtimes --dry-run) and enforce no network/writes;
  5. validate beta SHA256SUMS, beta manifest, installer manifest templates, the
     six unmeasured targets and the absence of runtime/user data.

The JSON report is PASS/FAIL, printed to stdout and optionally written as
package_smoke.json into --report-dir. The temporary workspace is always removed.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer.platform_manifest import load_manifest  # noqa: E402
from installer.runtime_manifest import load_runtime_manifest  # noqa: E402
import scripts.build_beta_packages as beta_builder  # noqa: E402
import scripts.build_release as release_builder  # noqa: E402
import scripts.fetch_native_runtimes as runtime_fetch  # noqa: E402
import scripts.release_acceptance as acceptance  # noqa: E402

TOOL_NAME = "package_smoke.py"
TOOL_VERSION = "1.0"
SCHEMA_VERSION = 1
TARGETS = tuple(release_builder.TARGET_ORDER)
FORBIDDEN_PACKAGE_PREFIXES = (
    "python/", "crewAI/", "crewAI-tools/", "data/", "logs/", ".workspace/",
    "dist/", "build/", "state/", ".git/", "da_eliminare/", "node_modules/",
)
REQUIRED_BETA_FILES = (
    "SHA256SUMS", "beta-manifest.json", "VERSION", "BETA_README.md",
    "INSTALL.md", "installer/platform-manifest.json",
    "installer/runtime-manifest.json",
)


class SmokeFailure(RuntimeError):
    """Raised when a package-smoke invariant fails."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _check(checks: list[dict], check_id: str, ok: bool, detail: str) -> None:
    checks.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                   "detail": detail})
    if not ok:
        raise SmokeFailure(check_id + ": " + detail)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_source_candidate(workspace: Path) -> dict:
    tracked = release_builder.tracked_files(REPO_ROOT)
    head = release_builder.git_head(REPO_ROOT)
    parent = workspace / "source-release"
    result = release_builder.build_release(
        REPO_ROOT, parent, name="smoke-source", tracked=tracked, head=head,
    )
    if result.get("status") != "built":
        raise SmokeFailure("source release build did not report built")
    candidate = Path(result["candidate"])
    manifest = _load_json(candidate / "release-manifest.json")
    archive = manifest.get("archive") or {}
    archive_path = candidate / str(archive.get("name") or "")
    if not archive_path.is_file():
        raise SmokeFailure("source release archive missing")
    if _sha256(archive_path) != str(archive.get("sha256") or ""):
        raise SmokeFailure("source release archive hash mismatch")
    return {
        "candidate": candidate,
        "version": str((manifest.get("product") or {}).get("version") or ""),
        "git_head": str((manifest.get("source") or {}).get("git_head") or ""),
        "archive_name": str(archive.get("name") or ""),
        "archive_sha256": str(archive.get("sha256") or ""),
        "archive_size": int(archive.get("size") or 0),
        "tracked_files": int((manifest.get("source") or {}).get("tracked_files") or 0),
    }


def _build_beta_package(workspace: Path, candidate: dict) -> Path:
    result = beta_builder.build_beta_package(
        candidate["candidate"], source=REPO_ROOT,
        output_parent=workspace / "beta-packages",
    )
    if result.get("status") != "packaged":
        raise SmokeFailure("beta package build did not report packaged")
    package = Path(result["output"])
    if not package.is_dir():
        raise SmokeFailure("beta package directory missing")
    return package


def _validate_beta_package(package: Path, version: str) -> dict:
    files = sorted(path for path in package.rglob("*") if path.is_file())
    relative = {path.relative_to(package).as_posix() for path in files}
    for required in REQUIRED_BETA_FILES:
        if required not in relative:
            raise SmokeFailure("beta package missing required file: " + required)
    if not any(name.startswith("source/") and name.endswith(".zip") for name in relative):
        raise SmokeFailure("beta package has no source archive")
    if not any(name.startswith("install/INSTALL-") for name in relative):
        raise SmokeFailure("beta package has no per-platform install docs")
    for name in relative:
        for prefix in FORBIDDEN_PACKAGE_PREFIXES:
            if name.startswith(prefix):
                raise SmokeFailure("beta package contains forbidden path: " + name)
        if name.lower().endswith((".sqlite3", ".pyc", ".pyo", ".log")):
            raise SmokeFailure("beta package contains user/cache data: " + name)
    sums_path = package / "SHA256SUMS"
    sums = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise SmokeFailure("malformed SHA256SUMS line")
        digest, rel = parts
        sums[rel] = digest
    if set(sums) != relative - {"SHA256SUMS"}:
        raise SmokeFailure("SHA256SUMS does not cover exactly the payload files")
    for rel, digest in sums.items():
        if _sha256(package / rel) != digest:
            raise SmokeFailure("SHA256SUMS mismatch: " + rel)
    manifest = _load_json(package / "beta-manifest.json")
    product = manifest.get("product") or {}
    if str(product.get("version") or "") != version:
        raise SmokeFailure("beta manifest version does not match APP_VERSION")
    platforms = manifest.get("platforms") or {}
    if sorted(platforms) != sorted(TARGETS):
        raise SmokeFailure("beta manifest does not declare exactly six targets")
    for target, entry in platforms.items():
        runtime = entry.get("runtime") or {}
        if runtime.get("measured") is not False:
            raise SmokeFailure("beta target runtime must be unmeasured: " + target)
        if runtime.get("sha256") or runtime.get("size"):
            raise SmokeFailure("beta target runtime has fabricated hash/size: " + target)
        if runtime.get("release_ready") is not False:
            raise SmokeFailure("beta target runtime must not be release_ready: " + target)
    validation = manifest.get("validation") or {}
    if validation.get("release_ready") is not False:
        raise SmokeFailure("beta manifest must not claim release_ready")
    if validation.get("runtime_components_measured") is not False:
        raise SmokeFailure("beta manifest must not claim measured runtime components")
    if not validation.get("manual_pending") or not validation.get("ci_flags"):
        raise SmokeFailure("beta manifest must carry CI and MANUAL-PENDING flags")
    inventory = {item["path"]: item for item in
                 (manifest.get("payload") or {}).get("inventory") or []}
    expected_inventory = relative - {"SHA256SUMS", "beta-manifest.json"}
    if set(inventory) != expected_inventory:
        raise SmokeFailure("beta manifest inventory does not match payload")
    for rel, item in inventory.items():
        if item.get("sha256") != _sha256(package / rel):
            raise SmokeFailure("beta manifest inventory hash mismatch: " + rel)
    platform_manifest = load_manifest(package / "installer" / "platform-manifest.json")
    if platform_manifest.get("release_ready") is not False:
        raise SmokeFailure("installer platform manifest must be a template")
    if sorted(platform_manifest["platforms"]) != sorted(TARGETS):
        raise SmokeFailure("installer platform manifest must declare six targets")
    components = {item["id"]: item for item in platform_manifest["components"]}
    for target in TARGETS:
        runtime_id = platform_manifest["platforms"][target]["runtime_component"]
        runtime = components.get(runtime_id) or {}
        if runtime.get("kind") != "runtime":
            raise SmokeFailure("installer runtime component missing: " + target)
        if runtime.get("sha256") or runtime.get("size"):
            raise SmokeFailure("installer runtime template has fabricated hash/size: "
                               + target)
    runtime_manifest = load_runtime_manifest(package / "installer" / "runtime-manifest.json")
    if runtime_manifest.get("release_ready") is not False:
        raise SmokeFailure("runtime manifest template must not be release_ready")
    if sorted(runtime_manifest["targets"]) != sorted(TARGETS):
        raise SmokeFailure("runtime manifest template must declare six targets")
    for target, entry in runtime_manifest["targets"].items():
        if entry["runtime"].get("measured") or entry["runtime"].get("sha256") \
                or entry["runtime"].get("size"):
            raise SmokeFailure("runtime template target not unmeasured: " + target)
    return {
        "files": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "targets": len(platforms),
        "sha256sums_entries": len(sums),
        "version": version,
    }


def _acceptance_matrix(workspace: Path) -> dict:
    records = workspace / "acceptance-records"
    records.mkdir(parents=True, exist_ok=True)
    matrix = acceptance.build_matrix(REPO_ROOT, records)
    targets = matrix.get("targets") or []
    if sorted(row.get("target_id") for row in targets) != sorted(TARGETS):
        raise SmokeFailure("acceptance matrix does not declare exactly six targets")
    for row in targets:
        state = (row.get("acceptance") or {}).get("state")
        if state != "MANUAL-PENDING":
            raise SmokeFailure("acceptance target must be MANUAL-PENDING with no "
                               "tester records: " + str(row.get("target_id")) + "=" + str(state))
        if (row.get("acceptance") or {}).get("hardware_verified"):
            raise SmokeFailure("acceptance matrix made a CI hardware claim: "
                               + str(row.get("target_id")))
    summary = matrix.get("summary") or {}
    if matrix.get("ci_support_claimed") is not False:
        raise SmokeFailure("acceptance matrix must not claim CI hardware support")
    if summary.get("no_ci_hardware_claim") is not True:
        raise SmokeFailure("acceptance matrix missing no_ci_hardware_claim flag")
    if int(summary.get("verified") or 0) != 0 or int(summary.get("manual_pending") or 0) != 6:
        raise SmokeFailure("acceptance matrix summary is not all-MANUAL-PENDING")
    if int(summary.get("invalid_records") or 0) != 0:
        raise SmokeFailure("acceptance matrix has invalid records")
    gates = matrix.get("gates") or []
    hardware_gates = [gate for gate in gates
                      if "real-hardware" in str(gate.get("gate") or "")]
    if not hardware_gates or hardware_gates[0].get("state") != "MANUAL-PENDING":
        raise SmokeFailure("acceptance matrix has no MANUAL-PENDING real-hardware gate")
    return {
        "targets": len(targets),
        "verified": int(summary.get("verified") or 0),
        "manual_pending": int(summary.get("manual_pending") or 0),
        "invalid_records": int(summary.get("invalid_records") or 0),
        "no_ci_hardware_claim": True,
    }


def _fetch_plan() -> dict:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        code = runtime_fetch.main(["--dry-run", "--json"])
    if code != 0:
        raise SmokeFailure("native-runtime dry-run plan failed with exit code "
                           + str(code))
    try:
        plan = json.loads(buffer.getvalue())
    except json.JSONDecodeError as exc:
        raise SmokeFailure("native-runtime dry-run plan did not emit JSON: " + str(exc))
    if plan.get("dry_run") is not True or plan.get("no_network") is not True \
            or plan.get("no_writes") is not True:
        raise SmokeFailure("native-runtime plan must be dry-run/no-network/no-writes")
    targets = plan.get("targets") or []
    if sorted(str(item.get("target") or "") for item in targets) != sorted(TARGETS):
        raise SmokeFailure("native-runtime plan does not declare exactly six targets")
    for item in targets:
        if item.get("action") != "plan-only":
            raise SmokeFailure("native-runtime plan has a non-plan action: "
                               + str(item.get("target")))
    counts = plan.get("counts") or {}
    if int(counts.get("selected") or 0) != 6 or int(counts.get("total") or 0) != 6:
        raise SmokeFailure("native-runtime plan counts are not six/six")
    return {"targets": len(targets), "dry_run": True, "no_network": True,
            "no_writes": True, "mode": str(plan.get("mode") or "plan")}


def run_smoke(workspace: Path) -> dict:
    checks: list[dict] = []
    facts: dict = {}
    try:
        candidate = _build_source_candidate(workspace)
        _check(checks, "source_release_candidate", True,
               "tracked files=" + str(candidate["tracked_files"])
               + " version=" + candidate["version"])
        facts["source_release"] = {
            "version": candidate["version"], "git_head": candidate["git_head"],
            "tracked_files": candidate["tracked_files"],
            "archive_bytes": candidate["archive_size"],
        }
        version = release_builder.read_version(REPO_ROOT)
        _check(checks, "version_matches_app_version", candidate["version"] == version,
               "candidate=" + candidate["version"] + " APP_VERSION=" + version)

        package = _build_beta_package(workspace, candidate)
        beta_facts = _validate_beta_package(package, version)
        _check(checks, "beta_package_checksums_and_manifests", True,
               "files=" + str(beta_facts["files"])
               + " sha256sums=" + str(beta_facts["sha256sums_entries"]))
        facts["beta_package"] = beta_facts
        _check(checks, "beta_six_target_unmeasured_honesty", True,
               "six targets; runtime sha256/size empty; release_ready=false; "
               "MANUAL-PENDING flags present")

        matrix_facts = _acceptance_matrix(workspace)
        _check(checks, "release_acceptance_matrix_all_manual_pending", True,
               "targets=" + str(matrix_facts["targets"])
               + " verified=" + str(matrix_facts["verified"])
               + " manual_pending=" + str(matrix_facts["manual_pending"]))
        facts["acceptance_matrix"] = matrix_facts

        plan_facts = _fetch_plan()
        _check(checks, "native_runtime_plan_dry_run", True,
               "targets=" + str(plan_facts["targets"])
               + " mode=" + plan_facts["mode"]
               + " no_network/no_writes")
        facts["native_runtime_plan"] = plan_facts
        return {"checks": checks, "facts": facts, "failures": []}
    except Exception as exc:  # produce a FAIL report instead of a traceback artifact
        checks.append({"id": "package_smoke", "status": "FAIL",
                       "detail": type(exc).__name__ + ": " + str(exc)})
        return {"checks": checks, "facts": facts,
                "failures": [type(exc).__name__ + ": " + str(exc)]}


def _report(checks: list[dict], facts: dict, failures: list[str],
            workspace_cleaned: bool) -> dict:
    passed = sum(1 for item in checks if item["status"] == "PASS")
    failed = sum(1 for item in checks if item["status"] == "FAIL")
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "status": "PASS" if failed == 0 and not failures else "FAIL",
        "checks": checks,
        "facts": facts,
        "failures": failures,
        "workspace": {"managed": True, "cleaned": bool(workspace_cleaned)},
        "ci_vs_manual_pending": (
            "This smoke builds deterministic source/beta packages and runs the acceptance "
            "matrix in a managed temp workspace. It is CI evidence only: the six native "
            "runtimes are unmeasured, real-hardware/clean-machine acceptance remains "
            "MANUAL-PENDING, and no CI run implies platform or release support."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=None,
                        help="write package_smoke.json into this directory (optional)")
    parser.add_argument("--json", action="store_true", help="print the JSON report")
    args = parser.parse_args(argv)
    workspace = Path(tempfile.mkdtemp(prefix="nl-package-smoke-"))
    result: dict = {"checks": [], "facts": {}, "failures": []}
    cleaned = False
    try:
        result = run_smoke(workspace)
    finally:
        try:
            shutil.rmtree(workspace, ignore_errors=True)
            cleaned = not workspace.exists()
        except OSError:
            cleaned = False
    report = _report(result["checks"], result["facts"], result["failures"], cleaned)
    if report["status"] != "PASS":
        report["failures"].append("workspace cleanup failed" if not cleaned else "")
        report["failures"] = [item for item in report["failures"] if item]
        report["status"] = "FAIL" if report["failures"] else report["status"]
    if args.report_dir:
        report_dir = Path(args.report_dir).expanduser()
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "package_smoke.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(TOOL_NAME + " " + TOOL_VERSION + ": " + report["status"])
        for check in report["checks"]:
            print("  " + check["status"] + "  " + check["id"] + "  " + check["detail"])
        for failure in report["failures"]:
            print("  FAIL  " + failure)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

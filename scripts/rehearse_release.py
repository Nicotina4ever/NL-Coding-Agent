"""Synthetic end-to-end rehearsal of the stage-6 release pipeline.

In a managed temporary workspace (always removed), with no network, no model and
no upload/publish:

  1. create synthetic runtime archive fixtures for the six targets
     (zip for Windows, tar.gz for POSIX; distinct marker files, NO real runtimes);
  2. run scripts.fetch_native_runtimes with --offline-dir and --write to produce a
     temporary measured runtime-manifest draft (release_ready only at 6/6);
  3. build a native-candidate-shaped source release with scripts.build_release,
     passing every synthetic archive as --runtime-archive TARGET=PATH;
  4. validate generated runtime/platform manifests and archive hashes;
  5. build a beta package from that candidate with scripts.build_beta_packages;
  6. provision + verify the synthetic runtime offline for all six targets with
     installer.provision (temporary target/cache);
  7. run scripts.release_acceptance matrix against temporary records containing
     one clearly synthetic rehearsal record fixture (never committed).

The report is explicitly synthetic: synthetic_rehearsal=true, per-stage PASS/FAIL,
measured facts and a NOT-A-RELEASE / no-platform-support statement. A failing
stage is reported with evidence and exits 1. Canonical manifests are checked to be
unchanged; the temporary workspace is always cleaned.

This is pipeline wiring/evidence rehearsal only. It does not claim real runtimes,
clean-machine acceptance, CI hardware support or a release.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer.platform_manifest import load_manifest
from installer.runtime_manifest import load_runtime_manifest
from installer import provision
import scripts.build_beta_packages as beta_builder
import scripts.build_release as release_builder
import scripts.fetch_native_runtimes as runtime_fetch
import scripts.release_acceptance as acceptance

TOOL_NAME = "rehearse_release.py"
TOOL_VERSION = "1.0"
SCHEMA_VERSION = 1
TARGETS = tuple(release_builder.TARGET_ORDER)
SYNTHETIC_NOTICE = (
    "NOT A RELEASE: this rehearsal uses synthetic marker-only runtime archives and a "
    "synthetic acceptance record fixture. It proves pipeline wiring/invariants, not "
    "real runtimes, platform support, clean-machine acceptance, hardware behaviour or "
    "any release/CI support claim."
)
CANONICAL_MANIFESTS = (
    "installer/runtime_manifest.json",
    "installer/platform_manifest.json",
    "installer/runtime_sources.json",
)
STAGE_NAMES = (
    "synthetic_runtime_fixtures",
    "fetch_native_runtimes_offline_measure",
    "measured_draft_validation",
    "native_candidate_build",
    "native_candidate_manifest_validation",
    "beta_package_build",
    "offline_provision_install_verify",
    "release_acceptance_matrix_synthetic_record",
)


class RehearsalFailure(RuntimeError):
    """Raised by a rehearsal stage; the report keeps the failing stage and evidence."""

    def __init__(self, stage: str, message: str):
        super().__init__(stage + ": " + message)
        self.stage = stage
        self.message = message


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _redact(text: str, workspace: Path) -> str:
    return str(text).replace(str(workspace), "<temp-workspace>")


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[name])
    return buffer.getvalue()


def _tar_gz_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in sorted(files):
            payload = files[name]
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _synthetic_members(target_id: str, archive_kind: str) -> dict[str, bytes]:
    marker = ("SYNTHETIC-REHEARSAL-TARGET " + target_id + chr(10)).encode("utf-8")
    if archive_kind == "zip":
        return {
            "python.exe": ("synthetic python launcher marker for " + target_id
                           + chr(10)).encode("utf-8"),
            "python312.dll": b"synthetic runtime marker (not a real DLL)" + bytes([10]),
            "SYNTHETIC_" + target_id + ".txt": marker,
        }
    return {
        "bin/python3": ("synthetic posix launcher marker for " + target_id
                        + chr(10)).encode("utf-8"),
        "lib/python3.12/site.py": b"# synthetic runtime marker (not real)" + bytes([10]),
        "SYNTHETIC_" + target_id + ".txt": marker,
    }


def _create_synthetic_archives(workspace: Path,
                               corrupt_targets: tuple[str, ...] = ()) -> dict:
    sources = runtime_fetch.load_sources()
    offline_dir = workspace / "synthetic-runtime-archives"
    offline_dir.mkdir(parents=True)
    archives: dict[str, Path] = {}
    facts: dict[str, dict] = {}
    for target_id in TARGETS:
        source = sources["targets"][target_id]
        path = offline_dir / source.filename
        if target_id in corrupt_targets:
            path.write_bytes(b"NOT-A-RUNTIME-ARCHIVE: synthetic corrupt fixture" + bytes([10]))
            facts[target_id] = {"filename": source.filename,
                                "archive_kind": source.archive_kind,
                                "corrupt": True}
            archives[target_id] = path
            continue
        members = _synthetic_members(target_id, source.archive_kind)
        payload = (_zip_bytes(members) if source.archive_kind == "zip"
                   else _tar_gz_bytes(members))
        path.write_bytes(payload)
        facts[target_id] = {"filename": source.filename,
                            "archive_kind": source.archive_kind,
                            "bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest()}
        archives[target_id] = path
    return {"offline_dir": offline_dir, "archives": archives, "targets": facts}


def _fetch_measured_draft(workspace: Path, fixtures: dict) -> dict:
    draft = workspace / "fetch" / "runtime-manifest.measured.json"
    evidence = workspace / "fetch" / "runtime-evidence.json"
    draft.parent.mkdir(parents=True)
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = runtime_fetch.main([
            "--offline-dir", str(fixtures["offline_dir"]),
            "--write", "--out", str(draft), "--evidence", str(evidence), "--json",
        ])
    if code != 0:
        raise RehearsalFailure(
            "fetch_native_runtimes_offline_measure",
            "fetch_native_runtimes offline-dir/--write failed (exit " + str(code) + "): "
            + stderr.getvalue()[-1600:].strip(),
        )
    try:
        payload = json.loads(stdout.getvalue())
    except json.JSONDecodeError as exc:
        raise RehearsalFailure("fetch_native_runtimes_offline_measure",
                               "fetch_native_runtimes produced no JSON: " + str(exc))
    measurements = payload.get("measurements") or []
    if len(measurements) != len(TARGETS):
        raise RehearsalFailure("fetch_native_runtimes_offline_measure",
                               "expected six measurements, got " + str(len(measurements)))
    written = payload.get("written") or {}
    if not Path(str(written.get("runtime_manifest") or "")).is_file():
        raise RehearsalFailure("fetch_native_runtimes_offline_measure",
                               "measured runtime-manifest draft was not written")
    return {"draft": Path(written["runtime_manifest"]),
            "evidence": Path(written.get("evidence") or evidence),
            "measurements": measurements}


def _validate_draft(draft_path: Path, measurements: list[dict]) -> dict:
    manifest = load_runtime_manifest(draft_path)
    if manifest["release_ready"] is not True:
        raise RehearsalFailure("measured_draft_validation",
                               "six synthetic runtimes must produce release_ready=true")
    if sorted(manifest["targets"]) != sorted(TARGETS):
        raise RehearsalFailure("measured_draft_validation",
                               "draft does not declare exactly six targets")
    by_target = {str(item.get("target")): item for item in measurements}
    for target_id in TARGETS:
        runtime = manifest["targets"][target_id]["runtime"]
        if not runtime["measured"] or not runtime["sha256"] or runtime["size"] <= 0:
            raise RehearsalFailure("measured_draft_validation",
                                   "draft runtime is not measured: " + target_id)
        measured = by_target.get(target_id) or {}
        if runtime["sha256"] != measured.get("sha256") \
                or int(runtime["size"]) != int(measured.get("size") or 0):
            raise RehearsalFailure("measured_draft_validation",
                                   "draft hash/size does not match measurement: " + target_id)
    return {"release_ready": True, "targets": len(manifest["targets"]),
            "sha256s": {target: manifest["targets"][target]["runtime"]["sha256"]
                        for target in TARGETS}}


def _build_native_candidate(workspace: Path, fixtures: dict) -> dict:
    tracked = release_builder.tracked_files(REPO_ROOT)
    head = release_builder.git_head(REPO_ROOT)
    parent = workspace / "native-candidate"
    runtime_archives = {target: str(fixtures["archives"][target]) for target in TARGETS}
    result = release_builder.build_release(
        REPO_ROOT, parent, name="rehearsal-native-candidate",
        tracked=tracked, head=head, runtime_archives=runtime_archives,
    )
    candidate = Path(result["candidate"])
    if not (candidate / "runtime-manifest.json").is_file():
        raise RehearsalFailure("native_candidate_build",
                               "native candidate has no runtime-manifest.json")
    if not (candidate / "platform-manifest.json").is_file():
        raise RehearsalFailure("native_candidate_build",
                               "native candidate has no platform-manifest.json")
    return {"candidate": candidate, "tracked_files": len(tracked),
            "version": str((result.get("product") or {}).get("version") or ""),
            "archive_bytes": int((result.get("archive") or {}).get("size") or 0)}


def _validate_native_candidate(candidate: Path) -> dict:
    runtime_manifest = load_runtime_manifest(candidate / "runtime-manifest.json")
    platform_manifest = load_manifest(candidate / "platform-manifest.json")
    if runtime_manifest["release_ready"] is not True:
        raise RehearsalFailure("native_candidate_manifest_validation",
                               "candidate runtime manifest is not release_ready")
    if sorted(runtime_manifest["targets"]) != sorted(TARGETS):
        raise RehearsalFailure("native_candidate_manifest_validation",
                               "candidate runtime manifest does not declare six targets")
    if platform_manifest["release_ready"] is not True:
        raise RehearsalFailure("native_candidate_manifest_validation",
                               "candidate platform manifest is not release_ready")
    if sorted(platform_manifest["platforms"]) != sorted(TARGETS):
        raise RehearsalFailure("native_candidate_manifest_validation",
                               "candidate platform manifest does not declare six targets")
    components = {item["id"]: item for item in platform_manifest["components"]}
    measured = {}
    for target_id in TARGETS:
        runtime_id = platform_manifest["platforms"][target_id]["runtime_component"]
        component = components.get(runtime_id) or {}
        if component.get("kind") != "runtime" or component.get("optional"):
            raise RehearsalFailure("native_candidate_manifest_validation",
                                   "candidate runtime component is not measured: " + target_id)
        archive_path = candidate / str(component.get("url") or "")
        if not archive_path.is_file():
            raise RehearsalFailure("native_candidate_manifest_validation",
                                   "candidate runtime archive missing: " + target_id)
        if _sha256(archive_path) != str(component.get("sha256") or ""):
            raise RehearsalFailure("native_candidate_manifest_validation",
                                   "candidate runtime archive hash mismatch: " + target_id)
        if archive_path.stat().st_size != int(component.get("size") or 0):
            raise RehearsalFailure("native_candidate_manifest_validation",
                                   "candidate runtime archive size mismatch: " + target_id)
        measured[target_id] = str(component["sha256"])
    return {"runtime_release_ready": True, "platform_release_ready": True,
            "targets": len(TARGETS), "runtime_sha256s": measured}


def _build_beta_package(workspace: Path, candidate: Path) -> dict:
    result = beta_builder.build_beta_package(
        candidate, source=REPO_ROOT, output_parent=workspace / "beta-packages",
    )
    package = Path(result["output"])
    if not package.is_dir():
        raise RehearsalFailure("beta_package_build", "beta package directory missing")
    manifest = json.loads((package / "beta-manifest.json").read_text(encoding="utf-8"))
    targets = manifest.get("platforms") or {}
    if sorted(targets) != sorted(TARGETS):
        raise RehearsalFailure("beta_package_build",
                               "beta manifest does not declare six targets")
    for target_id, entry in targets.items():
        if (entry.get("runtime") or {}).get("measured") is not False:
            raise RehearsalFailure("beta_package_build",
                                   "beta package claims measured runtime: " + target_id)
    files = [path for path in package.rglob("*") if path.is_file()]
    if not (package / "SHA256SUMS").is_file():
        raise RehearsalFailure("beta_package_build", "beta package has no SHA256SUMS")
    return {"files": len(files),
            "total_bytes": sum(path.stat().st_size for path in files),
            "targets": len(targets), "version": str(manifest["product"]["version"])}


def _provision_offline(workspace: Path, candidate: Path) -> dict:
    runtime_manifest = load_runtime_manifest(candidate / "runtime-manifest.json")
    cache = workspace / "provision-cache"
    installed = {}
    for target_id in TARGETS:
        target = workspace / "provisioned" / target_id
        result = provision.provision_install(
            runtime_manifest, target, platform_id=target_id, host_target=target_id,
            offline_bundle=candidate, cache_dir=cache,
        )
        if result.get("status") != "installed":
            raise RehearsalFailure("offline_provision_install_verify",
                                   "provision install failed: " + target_id)
        report = provision.provision_verify(target)
        if not report.get("ok"):
            raise RehearsalFailure("offline_provision_install_verify",
                                   "provision verify failed: " + target_id)
        descriptor = release_builder.SUPPORTED_TARGETS[target_id]
        launcher = (target / "runtime" / "python.exe"
                    if descriptor["os"] == "windows"
                    else target / "runtime" / "bin" / "python3")
        if not launcher.is_file():
            raise RehearsalFailure("offline_provision_install_verify",
                                   "synthetic launcher missing after install: " + target_id)
        installed[target_id] = {"verified": True,
                                "launcher": launcher.relative_to(target).as_posix()}
    cache_entries = [path for path in (cache / "artifacts").iterdir() if path.is_dir()]
    return {"targets": len(installed), "installed": installed,
            "cache_artifacts": len(cache_entries)}


def _synthetic_record(version: str) -> dict:
    steps = {step: {"result": "manual-pending",
                    "evidence_note": "synthetic rehearsal fixture; not a real tester result"}
             for step in acceptance.REQUIRED_STEPS}
    return {
        "schema_version": acceptance.SCHEMA_VERSION,
        "tester_alias": "synthetic-rehearsal",
        "timestamp": "2000-01-01T00:00:00+00:00",
        "target_id": "windows-x86_64",
        "os": "windows",
        "arch": "x86_64",
        "package": {"version": version, "sha256": "a" * 64},
        "install_path_type": "clean-custom",
        "evidence_notes": ("SYNTHETIC rehearsal fixture generated in a temp workspace; "
                           "not a real tester record and never committed."),
        "steps": steps,
    }


def _acceptance_matrix(workspace: Path, version: str) -> dict:
    records = workspace / "acceptance-records"
    records.mkdir(parents=True)
    record = _synthetic_record(version)
    validated, errors = acceptance.validate_record(record)
    if errors:
        raise RehearsalFailure("release_acceptance_matrix_synthetic_record",
                               "synthetic record fixture is invalid: " + "; ".join(errors))
    (records / "synthetic-rehearsal-record.json").write_text(
        json.dumps(validated, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    matrix = acceptance.build_matrix(REPO_ROOT, records)
    targets = matrix.get("targets") or []
    if sorted(row.get("target_id") for row in targets) != sorted(TARGETS):
        raise RehearsalFailure("release_acceptance_matrix_synthetic_record",
                               "matrix does not declare exactly six targets")
    if matrix.get("invalid_records"):
        raise RehearsalFailure("release_acceptance_matrix_synthetic_record",
                               "matrix rejected the synthetic record fixture")
    windows = [row for row in targets
               if row.get("target_id") == "windows-x86_64"]
    if not windows or (windows[0].get("acceptance") or {}).get("record_count") != 1:
        raise RehearsalFailure("release_acceptance_matrix_synthetic_record",
                               "synthetic record was not applied to windows-x86_64")
    for row in targets:
        acceptance_state = row.get("acceptance") or {}
        if acceptance_state.get("hardware_verified"):
            raise RehearsalFailure("release_acceptance_matrix_synthetic_record",
                                   "synthetic record made a hardware claim")
        if acceptance_state.get("state") == "verified":
            raise RehearsalFailure("release_acceptance_matrix_synthetic_record",
                                   "synthetic record must not verify a target")
    summary = matrix.get("summary") or {}
    if matrix.get("ci_support_claimed") is not False \
            or summary.get("no_ci_hardware_claim") is not True:
        raise RehearsalFailure("release_acceptance_matrix_synthetic_record",
                               "matrix made a CI hardware-support claim")
    if int(summary.get("verified") or 0) != 0:
        raise RehearsalFailure("release_acceptance_matrix_synthetic_record",
                               "matrix summary reports verified targets")
    return {
        "targets": len(targets), "valid_records": 1, "invalid_records": 0,
        "windows_record_count": 1,
        "windows_state": str((windows[0].get("acceptance") or {}).get("state")),
        "summary": {"verified": int(summary.get("verified") or 0),
                    "partial": int(summary.get("partial") or 0),
                    "manual_pending": int(summary.get("manual_pending") or 0)},
        "record_committed": False, "no_ci_hardware_claim": True,
    }



def _safe_value(value, workspace: Path):
    if isinstance(value, Path):
        try:
            return "<temp-workspace>/" + value.relative_to(workspace).as_posix()
        except ValueError:
            return "<path>"
    if isinstance(value, dict):
        return {str(key): _safe_value(item, workspace) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, workspace) for item in value]
    return value


def _detail(value, workspace: Path) -> str:
    try:
        text = json.dumps(_safe_value(value, workspace), sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = repr(_safe_value(value, workspace))
    return _redact(text, workspace)[:900]

def run_rehearsal(workspace: Path, *, corrupt_targets: tuple[str, ...] = ()) -> dict:
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    before = {name: _sha256(REPO_ROOT / name) for name in CANONICAL_MANIFESTS}
    stages: list[dict] = []
    facts: dict = {}
    failures: list[str] = []

    def stage(name: str, func):
        try:
            result = func()
        except RehearsalFailure as exc:
            stages.append({"name": name, "status": "FAIL",
                           "detail": _redact(exc.message, workspace)})
            failures.append(_redact(str(exc), workspace))
            raise
        except Exception as exc:
            stages.append({"name": name, "status": "FAIL",
                           "detail": _redact(type(exc).__name__ + ": " + str(exc), workspace)})
            failures.append(_redact(type(exc).__name__ + ": " + str(exc), workspace))
            raise RehearsalFailure(name, type(exc).__name__ + ": " + str(exc))
        stages.append({"name": name, "status": "PASS",
                       "detail": _detail(result, workspace)})
        return result

    try:
        try:
            fixtures = stage("synthetic_runtime_fixtures",
                             lambda: _create_synthetic_archives(
                                 workspace, corrupt_targets=corrupt_targets))
            fetch = stage("fetch_native_runtimes_offline_measure",
                          lambda: _fetch_measured_draft(workspace, fixtures))
            draft = stage("measured_draft_validation",
                          lambda: _validate_draft(fetch["draft"], fetch["measurements"]))
            candidate = stage("native_candidate_build",
                              lambda: _build_native_candidate(workspace, fixtures))
            validated = stage("native_candidate_manifest_validation",
                              lambda: _validate_native_candidate(candidate["candidate"]))
            beta = stage("beta_package_build",
                         lambda: _build_beta_package(workspace, candidate["candidate"]))
            provisioned = stage("offline_provision_install_verify",
                                lambda: _provision_offline(workspace, candidate["candidate"]))
            matrix = stage("release_acceptance_matrix_synthetic_record",
                           lambda: _acceptance_matrix(workspace, candidate["version"]))
            facts = {
                "synthetic_targets": list(TARGETS),
                "fixtures": fixtures["targets"],
                "draft": draft,
                "candidate": {"version": candidate["version"],
                              "tracked_files": candidate["tracked_files"],
                              "archive_bytes": candidate["archive_bytes"]},
                "candidate_manifests": validated,
                "beta_package": beta,
                "provisioning": provisioned,
                "acceptance": matrix,
            }
        except RehearsalFailure as exc:
            for name in STAGE_NAMES:
                if not any(item["name"] == name for item in stages):
                    stages.append({"name": name, "status": "SKIPPED",
                                   "detail": "not run after failure at " + exc.stage})
        after = {name: _sha256(REPO_ROOT / name) for name in CANONICAL_MANIFESTS}
        if before != after:
            changed = [name for name in CANONICAL_MANIFESTS if before[name] != after[name]]
            failures.append("canonical manifests changed during rehearsal: "
                            + ", ".join(changed))
            for name in STAGE_NAMES:
                if not any(item["name"] == name for item in stages):
                    stages.append({"name": name, "status": "SKIPPED",
                                   "detail": "canonical manifest mutation detected"})
        facts["canonical_manifests_unchanged"] = before == after
    finally:
        cleaned = False
        try:
            shutil.rmtree(workspace, ignore_errors=True)
            cleaned = not workspace.exists()
        except OSError:
            cleaned = False
        facts["workspace_cleaned"] = cleaned
    failed = any(item["status"] == "FAIL" for item in stages) or bool(failures)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "synthetic_rehearsal": True,
        "synthetic_notice": SYNTHETIC_NOTICE,
        "status": "FAIL" if failed else "PASS",
        "stages": stages,
        "facts": facts,
        "failures": failures,
        "workspace": {"managed": True, "cleaned": bool(facts.get("workspace_cleaned"))},
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Synthetic release-pipeline rehearsal",
        "",
        "**" + SYNTHETIC_NOTICE + "**",
        "",
        "- Status: **" + str(report["status"]) + "**",
        "- Synthetic rehearsal: yes",
        "- Managed temp workspace cleaned: "
        + ("yes" if (report.get("workspace") or {}).get("cleaned") else "no"),
        "- Canonical manifests unchanged: "
        + ("yes" if (report.get("facts") or {}).get("canonical_manifests_unchanged")
           else "no"),
        "",
        "## Stages",
        "",
        "| Stage | Status | Detail |",
        "|---|---|---|",
    ]
    for item in report.get("stages") or []:
        detail = str(item.get("detail") or "").replace("|", "/")[:400]
        lines.append("| " + str(item["name"]) + " | " + str(item["status"])
                     + " | " + detail + " |")
    facts = report.get("facts") or {}
    lines += ["", "## Measured facts", ""]
    for key in ("synthetic_targets", "draft", "candidate", "candidate_manifests",
                "beta_package", "provisioning", "acceptance",
                "canonical_manifests_unchanged", "workspace_cleaned"):
        if key not in facts:
            continue
        value = facts[key]
        if isinstance(value, dict) and key == "fixtures":
            continue
        lines.append("- " + key + ": " + json.dumps(value, sort_keys=True)[:1200])
    if report.get("failures"):
        lines += ["", "## Failures", ""] + ["- " + item for item in report["failures"]]
    lines.append("")
    return chr(10).join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=None,
                        help="write release_rehearsal.json and .md here (optional)")
    parser.add_argument("--json", action="store_true", help="print the JSON report")
    args = parser.parse_args(argv)
    workspace = Path(tempfile.mkdtemp(prefix="nl-release-rehearsal-"))
    try:
        report = run_rehearsal(workspace)
    except Exception as exc:
        report = {
            "schema_version": SCHEMA_VERSION,
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "synthetic_rehearsal": True,
            "synthetic_notice": SYNTHETIC_NOTICE,
            "status": "FAIL",
            "stages": [{"name": "internal", "status": "FAIL",
                        "detail": _redact(str(exc), workspace)}],
            "facts": {},
            "failures": [_redact(type(exc).__name__ + ": " + str(exc), workspace)],
            "workspace": {"managed": True, "cleaned": not workspace.exists()},
        }
    if args.report_dir:
        report_dir = Path(args.report_dir).expanduser()
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "release_rehearsal.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
        (report_dir / "release_rehearsal.md").write_text(
            render_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(TOOL_NAME + " " + TOOL_VERSION + ": " + str(report["status"]))
        for item in report.get("stages") or []:
            print("  " + item["status"] + "  " + item["name"])
        print(SYNTHETIC_NOTICE)
        for failure in report.get("failures") or []:
            print("  FAIL  " + failure)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

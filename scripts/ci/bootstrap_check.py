"""CI bootstrapper check: template plan + fake local offline bundle, no network.

Uses only the existing installer CLI contract (plan/install/verify --json). No package
is downloaded: the bundle contains a locally generated fake app archive. Exit 1 on any
contract failure; writes bootstrap_check.json into the report directory when requested.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _platform_id() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if system == "windows":
        return "windows-arm64" if arm else "windows-x86_64"
    if system == "darwin":
        return "macos-arm64" if arm else "macos-x86_64"
    return "linux-aarch64" if arm else "linux-x86_64"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fake_app_zip() -> bytes:
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("nl_agent.py", "print('ci fake launcher')\n")
        archive.writestr("nl_coding_agent/__init__.py", "# ci fake package\n")
    return buffer.getvalue()


def _fake_manifest(platform_id: str, app_bytes: bytes) -> dict:
    return {
        "schema_version": 1,
        "status": "release",
        "release_ready": True,
        "generated_by": "scripts/ci/bootstrap_check.py (fake local artifacts)",
        "product": {"id": "nl-coding-agent-ci", "name": "NL Coding Agent (CI fake)",
                    "version": "0.0-ci", "channel": "test"},
        "base_urls": {"primary": "offline://ci/", "mirrors": []},
        "platforms": {
            platform_id: {
                "display_name": "CI " + platform_id,
                "launcher": "nl_agent.py",
                "runtime_component": "ci-runtime",
                "components": ["ci-app"],
            }
        },
        "components": [
            {"id": "ci-app", "kind": "app", "version": "0.0-ci", "archive": "zip",
             "destination": ".", "sha256": _sha256(app_bytes), "size": len(app_bytes),
             "url": "artifacts/app.zip", "platforms": [platform_id], "placeholder": False},
            {"id": "ci-runtime", "kind": "runtime", "version": "0.0-ci",
             "archive": "zip", "destination": "python", "sha256": "", "size": 0,
             "url": "components/ci-runtime.zip", "platforms": [platform_id],
             "optional": True, "placeholder": True},
        ],
    }


def _run_cli(bootstrap: Path, args: list[str], cwd: Path) -> dict:
    command = [sys.executable, str(bootstrap), *args, "--json"]
    completed = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=180,
                               shell=False)
    payload = {}
    try:
        payload = json.loads(completed.stdout or "{}")
    except ValueError:
        payload = {}
    return {"exit_code": completed.returncode, "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-4000:], "json": payload,
            "command": [Path(sys.executable).name, "installer/bootstrap.py", *args]}


def run(report_dir: Path | None = None) -> dict:
    repo = _repo_root()
    root = Path(tempfile.mkdtemp(prefix="nl-ci-bootstrap-"))
    checks = []
    report = {"status": "FAIL", "platform_id": _platform_id(), "checks": checks}
    try:
        bootstrap = repo / "installer" / "bootstrap.py"
        template = repo / "installer" / "platform_manifest.json"
        plan_template = _run_cli(bootstrap, ["plan", "--manifest", str(template),
                                             "--cache", str(root / "cache")], repo)
        checks.append({"name": "template-plan-read-only",
                       "ok": plan_template["exit_code"] == 0
                       and plan_template["json"].get("status") == "plan",
                       "exit_code": plan_template["exit_code"]})
        checks.append({"name": "template-not-release-ready",
                       "ok": plan_template["json"].get("release_ready") is False})

        app_bytes = _fake_app_zip()
        platform_id = report["platform_id"]
        bundle = root / "bundle"
        (bundle / "artifacts").mkdir(parents=True)
        (bundle / "artifacts" / "app.zip").write_bytes(app_bytes)
        manifest = _fake_manifest(platform_id, app_bytes)
        (bundle / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        target = root / "target"
        cache = root / "cache"
        plan = _run_cli(bootstrap, ["plan", "--offline-bundle", str(bundle),
                                    "--target", str(target), "--cache", str(cache),
                                    "--platform", platform_id], repo)
        checks.append({"name": "offline-plan",
                       "ok": plan["exit_code"] == 0
                       and plan["json"].get("status") == "plan"
                       and bool(plan["json"].get("installable")),
                       "exit_code": plan["exit_code"]})
        install = _run_cli(bootstrap, ["install", "--offline-bundle", str(bundle),
                                       "--target", str(target), "--cache", str(cache),
                                       "--platform", platform_id], repo)
        installed = (target / "nl_agent.py").is_file()
        checks.append({"name": "offline-install-fake-artifact",
                       "ok": install["exit_code"] == 0 and installed,
                       "exit_code": install["exit_code"]})
        verify = _run_cli(bootstrap, ["verify", "--target", str(target)], repo)
        checks.append({"name": "install-verify",
                       "ok": verify["exit_code"] == 0
                       and verify["json"].get("ok") is True,
                       "exit_code": verify["exit_code"]})
        checks.append({"name": "no-network-download-path",
                       "ok": "offline://" in json.dumps(manifest) and "artifacts/app.zip" in json.dumps(manifest)})
        report["status"] = "PASS" if all(item["ok"] for item in checks) else "FAIL"
        report["checks"] = checks
        report["no_network"] = True
        report["fake_local_artifacts"] = True
    except Exception as exc:  # noqa: BLE001 - report and fail closed
        report["error"] = str(exc)
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "bootstrap_check.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI bootstrapper checks (offline fake artifacts)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args(argv)
    report = run(Path(args.report_dir).resolve() if args.report_dir else None)
    if args.json or args.report_dir:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Bootstrapper check: " + report["status"])
        for check in report.get("checks", []):
            print(("  OK   " if check["ok"] else "  FAIL ") + check["name"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

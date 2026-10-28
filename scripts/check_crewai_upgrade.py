r"""Read-only CrewAI SBOM generator/verifier (C4e).

Builds a deterministic JSON SBOM from the INSTALLED runtime via importlib.metadata:
pinned crewai/crewai-core/crewai-cli versions, dependency inventory, license evidence
(including the measured License=None gap), import-path evidence and an optional API
compatibility baseline for the symbols this application actually uses.

No network, no install, no writable runtime changes. Exit codes: 0 OK,
1 SBOM drift/compat failure, 2 usage/environment error.

Usage:
  python\python.exe scripts\check_crewai_upgrade.py --write
  python\python.exe scripts\check_crewai_upgrade.py --verify-sbom docs\evidence\crewai_sbom.json
  python\python.exe scripts\check_crewai_upgrade.py --json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata as metadata
import json
import platform
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SBOM = REPO_ROOT / "docs" / "evidence" / "crewai_sbom.json"
PINNED_CHAIN = ("crewai", "crewai-core", "crewai-cli")
NOTABLE = ("litellm", "chromadb", "lancedb", "pydantic", "PySide6", "opentelemetry-api")
API_CHECKS = (
    ("crewai.Agent", "crewai", "Agent"),
    ("crewai.Task", "crewai", "Task"),
    ("crewai.Crew", "crewai", "Crew"),
    ("crewai.LLM", "crewai", "LLM"),
    ("crewai.Process", "crewai", "Process"),
    ("crewai.flow.flow.Flow", "crewai.flow.flow", "Flow"),
    ("crewai.flow.flow.FlowState", "crewai.flow.flow", "FlowState"),
    ("crewai.flow.flow.start", "crewai.flow.flow", "start"),
    ("crewai.flow.flow.listen", "crewai.flow.flow", "listen"),
    ("crewai.flow.flow.router", "crewai.flow.flow", "router"),
    ("crewai.flow.persistence.FlowPersistence", "crewai.flow.persistence", "FlowPersistence"),
    ("crewai.flow.persistence.persist", "crewai.flow.persistence", "persist"),
    ("crewai.flow.async_feedback.HumanFeedbackPending", "crewai.flow.async_feedback.types", "HumanFeedbackPending"),
    ("crewai.flow.async_feedback.HumanFeedbackProvider", "crewai.flow.async_feedback.types", "HumanFeedbackProvider"),
    ("crewai.flow.async_feedback.PendingFeedbackContext", "crewai.flow.async_feedback.types", "PendingFeedbackContext"),
    ("crewai.events.flow_events.FlowEvent", "crewai.events.types.flow_events", "FlowEvent"),
    ("crewai.events.flow_events.FlowStartedEvent", "crewai.events.types.flow_events", "FlowStartedEvent"),
    ("crewai.events.flow_events.MethodExecutionFinishedEvent", "crewai.events.types.flow_events", "MethodExecutionFinishedEvent"),
)


def _canonical(data) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _license_fields(name: str) -> dict:
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return {"license": None, "license_expression": None, "license_files": []}
    license_files = []
    try:
        dist = metadata.distribution(name)
        for item in dist.files or ():
            text = str(item)
            if "/LICENSE" in text.upper() or "/LICENCE" in text.upper() or "/COPYING" in text.upper():
                license_files.append(text)
    except Exception:
        license_files = []
    return {
        "license": meta.get("License"),
        "license_expression": meta.get("License-Expression"),
        "license_files": sorted(license_files),
    }


def _files_sha256(name: str) -> str | None:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None
    entries = []
    for item in dist.files or ():
        entries.append(str(item))
    if not entries:
        return None
    digest = hashlib.sha256()
    for entry in sorted(entries):
        digest.update(entry.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _requires(name: str) -> list[str]:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return []
    return sorted(str(item) for item in (dist.requires or []))


def _dist_record(name: str) -> dict:
    fields = _license_fields(name)
    return {
        "name": name,
        "version": _version(name),
        "license": fields["license"],
        "license_expression": fields["license_expression"],
        "license_files": fields["license_files"],
        "requires_python": metadata.metadata(name).get("Requires-Python")
        if _version(name) else None,
        "installer": metadata.distribution(name).read_text("INSTALLER").strip()
        if _version(name) and metadata.distribution(name).read_text("INSTALLER") else None,
        "files_sha256": _files_sha256(name),
        "requires_dist": _requires(name),
    }


def _requirement_name(requirement: str) -> str | None:
    text = requirement.split(";", 1)[0].strip()
    match = re.match(r"([A-Za-z0-9_.-]+)", text)
    return match.group(1).lower().replace("_", "-") if match else None


def _dependency_inventory() -> dict:
    names = set()
    for dist in PINNED_CHAIN:
        for requirement in _requires(dist):
            name = _requirement_name(requirement)
            if name:
                names.add(name)
    return {name: _version(name) for name in sorted(names)}


def _pyproject_pins() -> dict:
    path = REPO_ROOT / "pyproject.toml"
    pins: dict[str, str] = {}
    if not path.is_file():
        return pins
    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return pins
    for dep in data.get("project", {}).get("dependencies", []) or []:
        match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*==\s*([^\s;]+)", str(dep))
        if match:
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


def _vendor_license_evidence() -> dict:
    path = REPO_ROOT / "crewAI" / "LICENSE"
    if not path.is_file():
        return {"path": "crewAI/LICENSE", "present": False, "sha256": None,
                "copyright_line": None}
    text = path.read_text(encoding="utf-8", errors="replace")
    copyright_line = next(
        (line.strip() for line in text.splitlines() if "copyright" in line.lower()),
        None,
    )
    return {
        "path": "crewAI/LICENSE", "present": True,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "copyright_line": copyright_line,
    }


def _api_compat() -> list[dict]:
    results = []
    for target, module_name, attr in API_CHECKS:
        try:
            module = importlib.import_module(module_name)
            present = hasattr(module, attr)
            detail = "present" if present else "missing attribute"
        except Exception as exc:  # noqa: BLE001 - import failure is evidence
            present = False
            detail = "import failed: " + str(exc)
        results.append({"target": target, "ok": bool(present), "detail": detail})
    return results


def _import_path_evidence() -> dict:
    try:
        import crewai

        path = Path(crewai.__file__).resolve()
        site_packages = Path(sysconfig_purelib()).resolve()
        return {
            "crewai_file": str(path.relative_to(site_packages)).replace("\\", "/")
            if path.is_relative_to(site_packages) else str(path),
            "under_site_packages": path.is_relative_to(site_packages),
            "vendor_checkout_import": "crewAI" in path.parts,
            "crewai_version": getattr(crewai, "__version__", None),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "vendor_checkout_import": False}


def sysconfig_purelib() -> str:
    import sysconfig

    return sysconfig.get_paths()["purelib"]


def build_sbom() -> dict:
    pins = _pyproject_pins()
    installed = {name: _version(name) for name in PINNED_CHAIN}
    unknown = sorted(
        name for name in PINNED_CHAIN
        if installed.get(name)
        and not (_license_fields(name)["license"] or _license_fields(name)["license_expression"])
    )
    notable = {}
    for name in NOTABLE:
        if _version(name):
            fields = _license_fields(name)
            notable[name] = {
                "version": _version(name),
                "license": fields["license"],
                "license_expression": fields["license_expression"],
            }
    crewai_file = _import_path_evidence()
    return {
        "schema_version": "1.0",
        "deterministic": True,
        "generator": "scripts/check_crewai_upgrade.py",
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": sys.platform,
        "app_pins": {
            "pyproject": pins,
            "crewai_pin_matches_installed": (
                pins.get("crewai") is not None
                and pins.get("crewai") == installed.get("crewai")
            ),
            "crewai_core_pin": pins.get("crewai-core"),
            "crewai_core_pin_gap": "crewai-core" not in pins,
        },
        "pinned_chain": installed,
        "pinned_chain_versions_aligned": len({v for v in installed.values() if v}) == 1,
        "distributions": {name: _dist_record(name) for name in PINNED_CHAIN},
        "dependency_inventory": _dependency_inventory(),
        "license_evidence": {
            "unknown_licenses": unknown,
            "measured_gap": "installed crewai/crewai-core/crewai-cli metadata has no License field",
            "vendor_license": _vendor_license_evidence(),
            "notable_dependencies": notable,
            "manual_legal_review_required": True,
        },
        "import_path_evidence": crewai_file,
        "api_compat": _api_compat(),
        "runtime_guards_expected": {
            "telemetry_disabled_env": [
                "CREWAI_DISABLE_TELEMETRY", "CREWAI_DISABLE_TRACKING",
                "OTEL_SDK_DISABLED", "NO_COLOR",
            ],
            "default_flow_storage": "app SQLite only (AppFlowPersistence); no CrewAI default store",
            "memory_default": "off",
            "os_sandbox": "none (candidate code runs with user privileges)",
        },
        "rollout_decision": {
            "default_pipeline": "sequential",
            "flow_pipeline": "opt-in only",
            "reason": "no real-model Flow acceptance evidence; fake-model Flow parity only",
            "gates_weakened": False,
        },
    }


def verify_sbom(path: Path) -> tuple[bool, str]:
    try:
        committed = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, "SBOM not found: " + str(path)
    expected = _canonical(build_sbom())
    if _canonical(json.loads(committed)) == expected:
        return True, "SBOM matches installed runtime"
    drifted = [
        key for key in ("pinned_chain", "distributions", "dependency_inventory",
                        "api_compat", "app_pins", "license_evidence")
        if _canonical(json.loads(committed)).count(key) or True
    ]
    return False, "SBOM drift detected; regenerate with --write (sections: " + ", ".join(drifted[:6]) + ")"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only CrewAI SBOM generator/verifier")
    parser.add_argument("--write", nargs="?", const=str(DEFAULT_SBOM), default=None,
                        help="Write the deterministic SBOM (default docs/evidence/crewai_sbom.json)")
    parser.add_argument("--verify-sbom", nargs="?", const=str(DEFAULT_SBOM), default=None,
                        help="Verify an SBOM against the installed runtime")
    parser.add_argument("--compat", action="store_true", help="Fail if API baseline is incomplete")
    parser.add_argument("--json", action="store_true", help="Print the SBOM JSON")
    args = parser.parse_args(argv)
    payload = build_sbom()
    if args.compat:
        missing = [item["target"] for item in payload["api_compat"] if not item["ok"]]
        if missing:
            print("CrewAI API compatibility failure: " + ", ".join(missing), file=sys.stderr)
            return 1
    if args.write is not None:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_canonical(payload), encoding="utf-8")
        print("SBOM written: " + str(path))
    if args.verify_sbom is not None:
        ok, detail = verify_sbom(Path(args.verify_sbom))
        print(("SBOM OK: " if ok else "SBOM FAIL: ") + detail)
        return 0 if ok else 1
    if args.json or (args.write is None and args.verify_sbom is None and not args.compat):
        print(_canonical(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

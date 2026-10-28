"""Native runtime provisioner for the cross-platform private beta.

The provisioner consumes an installer.runtime_manifest (six OS/arch targets),
selects the native runtime for exactly one target, and delegates the verified
download/cache/atomic-staging/repair/update machinery to installer.operations.

Hard guarantees:

  * the Windows embedded python/ runtime (and any Windows artifact) is never
    reused on Linux/macOS; native selection is strict and fails closed;
  * unsupported OS/architecture fails closed with explicit guidance;
  * hashes/sizes come from the manifest and are verified by the shared fetcher
    and cache; unmeasured template manifests are never installable;
  * optional CPU/GPU/ASR/TTS components are declarative only: they are never
    required and their absence produces degradation notes, not failures.
"""
from __future__ import annotations

from pathlib import Path

from installer import operations
from installer.platform_targets import (
    SUPPORTED_TARGETS,
    UnsupportedTargetError,
    detect_host_target,
    ensure_native_target,
    resolve_target,
)
from installer.runtime_manifest import (
    RuntimeManifestError,
    optional_components_for_target,
    runtime_for_target,
    target_entry,
)


class ProvisionError(RuntimeError):
    """Raised when the native runtime cannot be provisioned safely."""


_RUNTIME_DESTINATION = "runtime"
_LAUNCHER_RELATIVE = {
    "windows": "python.exe",
    "linux": "bin/python3",
    "macos": "bin/python3",
}


def _launcher_for_target(target_id: str) -> str:
    descriptor = SUPPORTED_TARGETS[target_id]
    return _RUNTIME_DESTINATION + "/" + _LAUNCHER_RELATIVE[descriptor["os"]]


def build_platform_manifest(runtime_manifest: dict, target_id: str) -> dict:
    """Translate one runtime target into a platform manifest usable by operations."""
    selected, entry = target_entry(runtime_manifest, target_id)
    runtime = dict(entry["runtime"])
    measured = bool(runtime.get("measured"))
    component = {
        "id": runtime["id"],
        "kind": "runtime",
        "version": runtime["version"],
        "archive": runtime["archive"],
        "destination": _RUNTIME_DESTINATION,
        "sha256": runtime["sha256"] if measured else "",
        "size": int(runtime["size"]) if measured else 0,
        "url": runtime["url"],
        "platforms": [selected],
        "optional": False,
        "placeholder": not measured,
    }
    ensure_native_target(component, selected)
    return {
        "schema_version": 1,
        "status": str(runtime_manifest.get("status") or "template"),
        "release_ready": bool(runtime_manifest.get("release_ready")),
        "generated_by": "installer/provision.py",
        "product": dict(runtime_manifest["product"]),
        "base_urls": {
            "primary": str(runtime_manifest["base_urls"]["primary"]),
            "mirrors": [],
        },
        "platforms": {
            selected: {
                "display_name": str(entry["display_name"]),
                "launcher": _launcher_for_target(selected),
                "runtime_component": component["id"],
                "components": [component["id"]],
            }
        },
        "components": [component],
    }


def _serialise_optional(manifest: dict, target_id: str) -> list[dict]:
    result = []
    for item in optional_components_for_target(manifest, target_id):
        result.append({
            "id": item["id"],
            "kind": item["kind"],
            "backend": item["backend"],
            "optional": True,
            "available": bool(item["available"]),
            "required": False,
            "degradation": item["degradation"],
        })
    return result


def _require_native_host(target_id: str, host_target: str | None) -> str:
    detected = host_target or detect_host_target()
    if detected != target_id:
        raise UnsupportedTargetError(
            "target " + target_id + " does not match the native host " + detected
            + "; a runtime for one OS/architecture is never installed on another, and "
            "the Windows embedded python/ runtime is never reused on Linux/macOS. "
            "Run the provisioner on the matching host, or use an explicitly supported "
            "beta target. Supported targets: " + ", ".join(SUPPORTED_TARGETS) + ".",
            host=detected,
        )
    return detected


def _check_platform_components(platform_manifest: dict, target_id: str) -> None:
    for component in platform_manifest["components"]:
        if str(component.get("kind")) == "runtime":
            ensure_native_target(component, target_id)


def provision_plan(runtime_manifest: dict, *, target: str | Path | None = None,
                   platform_id: str | None = None, cache_dir: str | Path | None = None,
                   offline_bundle: str | Path | None = None,
                   host_target: str | None = None) -> dict:
    """Plan the native runtime provisioning for the selected target (writes nothing)."""
    selected = resolve_target(platform_id)
    host = host_target or detect_host_target()
    platform_manifest = build_platform_manifest(runtime_manifest, selected)
    _check_platform_components(platform_manifest, selected)
    plan = operations.plan_install(
        platform_manifest,
        target=target,
        cache_dir=cache_dir,
        platform_id=selected,
        offline_bundle=offline_bundle,
    )
    native = runtime_for_target(runtime_manifest, selected)
    optional = _serialise_optional(runtime_manifest, selected)
    degradation = [item["degradation"] for item in optional if not item["available"]]
    plan.update({
        "schema_version": 1,
        "target": selected,
        "host_target": host,
        "native_runtime": native,
        "dependencies": [dict(item) for item in
                         target_entry(runtime_manifest, selected)[1]["dependencies"]],
        "optional_components": optional,
        "degradation": degradation,
        "universal2": dict(runtime_manifest.get("universal2") or {}),
        "runtime_measured": bool(native.get("measured")),
    })
    if not native.get("measured"):
        plan.setdefault("warnings", []).append(
            "native runtime is unmeasured (template manifest); provision an installable "
            "release manifest with measured sha256/size before installing"
        )
    if plan.get("installable"):
        plan.setdefault("warnings", []).append(
            "optional CPU/GPU/ASR/TTS components are declarative; unavailable backends "
            "degrade gracefully and are never required"
        )
    return plan


def _provision_install_like(action: str, runtime_manifest: dict, target: str | Path,
                            *, platform_id: str | None = None,
                            cache_dir: str | Path | None = None,
                            offline_bundle: str | Path | None = None,
                            host_target: str | None = None,
                            allow_downgrade: bool = False) -> dict:
    selected = resolve_target(platform_id)
    host = _require_native_host(selected, host_target)
    if not runtime_manifest.get("release_ready"):
        raise ProvisionError(
            "runtime manifest is a template (release_ready=false); refusing to "
            + action + ". Use a generated release manifest with measured artifacts."
        )
    platform_manifest = build_platform_manifest(runtime_manifest, selected)
    _check_platform_components(platform_manifest, selected)
    if action == "install":
        result = operations.install(
            platform_manifest, target, cache_dir=cache_dir,
            platform_id=selected, offline_bundle=offline_bundle,
        )
    elif action == "update":
        result = operations.update(
            platform_manifest, target, cache_dir=cache_dir,
            platform_id=selected, offline_bundle=offline_bundle,
            allow_downgrade=allow_downgrade,
        )
    elif action == "repair":
        result = operations.repair(
            platform_manifest, target, cache_dir=cache_dir,
            platform_id=selected, offline_bundle=offline_bundle,
        )
    else:
        raise ProvisionError("unknown provisioner action: " + action)
    native = runtime_for_target(runtime_manifest, selected)
    optional = _serialise_optional(runtime_manifest, selected)
    result.update({
        "schema_version": 1,
        "target": selected,
        "host_target": host,
        "native_runtime": native,
        "dependencies": [dict(item) for item in
                         target_entry(runtime_manifest, selected)[1]["dependencies"]],
        "optional_components": optional,
        "degradation": [item["degradation"] for item in optional if not item["available"]],
        "universal2": dict(runtime_manifest.get("universal2") or {}),
    })
    return result


def provision_install(runtime_manifest: dict, target: str | Path, **kwargs) -> dict:
    return _provision_install_like("install", runtime_manifest, target, **kwargs)


def provision_update(runtime_manifest: dict, target: str | Path, **kwargs) -> dict:
    return _provision_install_like("update", runtime_manifest, target, **kwargs)


def provision_repair(runtime_manifest: dict, target: str | Path, **kwargs) -> dict:
    return _provision_install_like("repair", runtime_manifest, target, **kwargs)


def provision_verify(target: str | Path) -> dict:
    return operations.verify_install(target)

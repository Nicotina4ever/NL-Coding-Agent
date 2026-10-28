"""Runtime/dependency manifest for the cross-platform private beta.

One schema describes exactly six native targets. Each target pins:

  * a standalone Python runtime identifier, version, archive kind/url and
    measured sha256/size (or explicit unmeasured placeholders);
  * pinned Python-level dependency identifiers bundled inside that runtime
    (crewai, PySide6, psutil, ...);
  * optional CPU/GPU/ASR/TTS components with availability + graceful
    degradation notes. No GPU backend (CUDA/ROCm/Metal/MLX) and no ASR/TTS
    backend is ever mandatory.

Hashes and sizes are only ever recorded when measured. An unmeasured artifact
MUST leave sha256 empty and size 0; a release_ready manifest requires every one
of the six runtimes to be measured. The template shipped as
installer/runtime_manifest.json is release_ready=false and contains no made-up
hashes.

macOS Universal 2: standalone Python runtimes (python-build-standalone and
similar) are normally built per architecture. This manifest therefore defines
separate macos-x86_64 and macos-arm64 runtimes. A universal2 claim is only
allowed with a measured universal artifact shared by both macOS targets; the
template records the decision "separate-per-arch" and makes no universal claim.
"""
from __future__ import annotations

import json
from pathlib import Path

from installer.platform_targets import (
    SUPPORTED_TARGETS,
    TARGET_ORDER,
    arch_family,
    resolve_target,
)

SCHEMA_VERSION = 1
ARCHIVE_FORMATS = ("zip", "tar.gz", "tar", "file")
DEPENDENCY_KINDS = ("python-package", "native-library", "tool")
OPTIONAL_KINDS = ("cpu", "gpu", "asr", "tts")
UNIVERSAL2_DECISIONS = ("separate-per-arch", "universal2")
HEX = set("0123456789abcdef")


class RuntimeManifestError(ValueError):
    """Raised when a runtime manifest is missing, malformed or unsafe."""


def load_runtime_manifest(path: str | Path) -> dict:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise RuntimeManifestError("runtime manifest not found: " + str(manifest_path))
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeManifestError("cannot read runtime manifest: " + str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeManifestError("runtime manifest is not valid JSON: " + str(exc)) from exc
    return validate_runtime_manifest(data)


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeManifestError("field must be a non-empty string: " + field)
    return value.strip()


def _sha256(value, field: str) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip().lower()
    if len(text) != 64 or any(char not in HEX for char in text):
        raise RuntimeManifestError("invalid sha256: " + field)
    return text


def _size(value, field: str) -> int:
    if value in (None, ""):
        return 0
    try:
        size = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeManifestError("invalid size: " + field) from exc
    if size < 0:
        raise RuntimeManifestError("negative size: " + field)
    return size


def _artifact(item: dict, field: str, *, required_measured: bool) -> dict:
    measured = bool(item.get("measured", False))
    sha256 = _sha256(item.get("sha256"), field + ".sha256")
    size = _size(item.get("size"), field + ".size")
    if not measured:
        if sha256 or size:
            raise RuntimeManifestError(
                "unmeasured artifact must not declare sha256/size (never fabricate hashes): "
                + field
            )
    else:
        if not sha256 or size <= 0:
            raise RuntimeManifestError(
                "measured artifact requires a real sha256 and positive size: " + field
            )
    if required_measured and not measured:
        raise RuntimeManifestError("release-ready manifest requires a measured artifact: "
                                   + field)
    return {"measured": measured, "sha256": sha256, "size": size}


def _validate_dependency(item, field: str, *, release_ready: bool) -> dict:
    if not isinstance(item, dict):
        raise RuntimeManifestError("dependency must be an object: " + field)
    dependency_id = _text(item.get("id"), field + ".id")
    kind = str(item.get("kind") or "python-package")
    if kind not in DEPENDENCY_KINDS:
        raise RuntimeManifestError("unsupported dependency kind for " + dependency_id + ": "
                                   + kind)
    version = _text(item.get("version"), field + ".version")
    pinned = str(item.get("pinned") or (dependency_id + "==" + version)).strip()
    if "==" not in pinned:
        raise RuntimeManifestError("dependency pin must use ==: " + pinned)
    artifact = None
    if item.get("archive"):
        archive = str(item["archive"])
        if archive not in ARCHIVE_FORMATS:
            raise RuntimeManifestError("unsupported dependency archive: " + archive)
        artifact = {
            "archive": archive,
            "url": _text(item.get("url"), field + ".url"),
            **_artifact(item, field, required_measured=release_ready and not bool(
                item.get("optional", False))),
        }
    elif item.get("sha256") or item.get("size"):
        raise RuntimeManifestError("dependency sha256/size requires an archive descriptor: "
                                   + dependency_id)
    return {
        "id": dependency_id,
        "kind": kind,
        "version": version,
        "pinned": pinned,
        "optional": bool(item.get("optional", False)),
        "artifact": artifact,
    }


def _validate_optional(item, field: str) -> dict:
    if not isinstance(item, dict):
        raise RuntimeManifestError("optional component must be an object: " + field)
    component_id = _text(item.get("id"), field + ".id")
    kind = str(item.get("kind") or "")
    if kind not in OPTIONAL_KINDS:
        raise RuntimeManifestError("unsupported optional component kind for " + component_id
                                   + ": " + kind)
    if not bool(item.get("optional", True)):
        raise RuntimeManifestError("CPU/GPU/ASR/TTS component must be optional: " + component_id)
    available = bool(item.get("available", False))
    backend = _text(item.get("backend", "none"), field + ".backend")
    degradation = _text(item.get("degradation"), field + ".degradation")
    return {
        "id": component_id,
        "kind": kind,
        "optional": True,
        "available": available,
        "backend": backend,
        "degradation": degradation,
    }


def validate_runtime_manifest(data) -> dict:
    if not isinstance(data, dict):
        raise RuntimeManifestError("runtime manifest must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeManifestError("unsupported runtime manifest schema_version: "
                                   + str(data.get("schema_version")))
    product = data.get("product")
    if not isinstance(product, dict):
        raise RuntimeManifestError("runtime_manifest.product is required")
    product_id = _text(product.get("id"), "product.id")
    version = _text(product.get("version"), "product.version")
    release_ready = bool(data.get("release_ready", False))
    base_urls = data.get("base_urls")
    if not isinstance(base_urls, dict):
        raise RuntimeManifestError("runtime_manifest.base_urls is required")
    primary = _text(base_urls.get("primary"), "base_urls.primary")

    universal2 = data.get("universal2")
    if not isinstance(universal2, dict):
        raise RuntimeManifestError("runtime_manifest.universal2 decision is required")
    decision = str(universal2.get("decision") or "")
    if decision not in UNIVERSAL2_DECISIONS:
        raise RuntimeManifestError("invalid macOS universal2 decision: " + decision)
    supported = bool(universal2.get("supported", False))
    if supported and decision != "universal2":
        raise RuntimeManifestError("universal2.supported=true requires decision=universal2")
    if not supported and decision != "separate-per-arch":
        raise RuntimeManifestError(
            "universal2.supported=false requires decision=separate-per-arch (no unverified "
            "universal claim allowed)"
        )
    universal_artifact = None
    if supported:
        universal_artifact = _artifact(
            universal2.get("artifact") or {}, "universal2.artifact", required_measured=True)

    raw_targets = data.get("targets")
    if not isinstance(raw_targets, dict):
        raise RuntimeManifestError("runtime_manifest.targets must be an object")
    if set(raw_targets) != set(TARGET_ORDER):
        raise RuntimeManifestError(
            "runtime manifest must declare exactly the six supported targets: "
            + ", ".join(TARGET_ORDER)
        )
    targets: dict[str, dict] = {}
    for target_id in TARGET_ORDER:
        entry = raw_targets[target_id]
        if not isinstance(entry, dict):
            raise RuntimeManifestError("target entry must be an object: " + target_id)
        descriptor = SUPPORTED_TARGETS[target_id]
        selector = entry.get("selector")
        if not isinstance(selector, dict):
            raise RuntimeManifestError("target selector is required: " + target_id)
        selector_os = str(selector.get("os") or "").lower()
        selector_arch = arch_family(str(selector.get("arch") or ""))
        if selector_os != descriptor["os"] or selector_arch != arch_family(descriptor["arch"]):
            raise RuntimeManifestError(
                "target selector does not match target " + target_id + ": "
                + selector_os + "/" + str(selector.get("arch"))
            )
        runtime = entry.get("runtime")
        if not isinstance(runtime, dict):
            raise RuntimeManifestError("target runtime is required: " + target_id)
        runtime_id = _text(runtime.get("id"), target_id + ".runtime.id")
        if runtime_id != descriptor["runtime_id"]:
            raise RuntimeManifestError(
                "pinned runtime id mismatch for " + target_id + ": expected "
                + descriptor["runtime_id"] + ", got " + runtime_id
            )
        archive = str(runtime.get("archive") or descriptor["archive"])
        if archive not in ARCHIVE_FORMATS:
            raise RuntimeManifestError("unsupported runtime archive for " + target_id + ": "
                                       + archive)
        measured = _artifact(runtime, target_id + ".runtime", required_measured=release_ready)
        targets[target_id] = {
            "selector": {"os": descriptor["os"], "arch": descriptor["arch"]},
            "display_name": _text(entry.get("display_name", descriptor["display_name"]),
                                  target_id + ".display_name"),
            "runtime": {
                "id": runtime_id,
                "version": _text(runtime.get("version"),
                                 target_id + ".runtime.version"),
                "archive": archive,
                "url": _text(runtime.get("url"), target_id + ".runtime.url"),
                **measured,
            },
            "dependencies": [
                _validate_dependency(item, target_id + ".dependencies[" + str(index) + "]",
                                     release_ready=release_ready)
                for index, item in enumerate(entry.get("dependencies") or [])
            ],
            "optional_components": [
                _validate_optional(item,
                                   target_id + ".optional_components[" + str(index) + "]")
                for index, item in enumerate(entry.get("optional_components") or [])
            ],
            "notes": [str(note) for note in (entry.get("notes") or [])],
        }
        dependency_ids = [item["id"] for item in targets[target_id]["dependencies"]]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise RuntimeManifestError("duplicate dependency id for " + target_id)
        optional_ids = [item["id"] for item in targets[target_id]["optional_components"]]
        if len(optional_ids) != len(set(optional_ids)):
            raise RuntimeManifestError("duplicate optional component id for " + target_id)
    if supported:
        for target_id in ("macos-x86_64", "macos-arm64"):
            if not universal_artifact or not universal_artifact["measured"]:
                raise RuntimeManifestError("universal2 requires a measured universal artifact")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": str(data.get("status") or ("release" if release_ready else "template")),
        "release_ready": release_ready,
        "generated_by": str(data.get("generated_by") or ""),
        "product": {
            "id": product_id,
            "name": str(product.get("name") or product_id),
            "version": version,
            "channel": str(product.get("channel") or "beta"),
        },
        "base_urls": {"primary": primary},
        "universal2": {
            "supported": supported,
            "decision": decision,
            "rationale": str(universal2.get("rationale") or ""),
            "evidence": str(universal2.get("evidence") or ""),
            "artifact": universal_artifact,
        },
        "targets": targets,
    }


def target_entry(manifest: dict, target_id: str | None = None) -> tuple[str, dict]:
    selected = resolve_target(target_id)
    entry = manifest["targets"].get(selected)
    if entry is None:
        raise RuntimeManifestError("runtime manifest has no entry for target: " + selected)
    return selected, entry


def runtime_for_target(manifest: dict, target_id: str | None = None) -> dict:
    selected, entry = target_entry(manifest, target_id)
    return {"target": selected, **dict(entry["runtime"])}


def dependencies_for_target(manifest: dict, target_id: str | None = None) -> list[dict]:
    _, entry = target_entry(manifest, target_id)
    return [dict(item) for item in entry["dependencies"]]


def optional_components_for_target(manifest: dict, target_id: str | None = None) -> list[dict]:
    _, entry = target_entry(manifest, target_id)
    return [dict(item) for item in entry["optional_components"]]


def manifest_summary(manifest: dict) -> dict:
    return {
        "schema_version": manifest["schema_version"],
        "status": manifest["status"],
        "release_ready": manifest["release_ready"],
        "product": dict(manifest["product"]),
        "universal2": {
            "supported": manifest["universal2"]["supported"],
            "decision": manifest["universal2"]["decision"],
        },
        "targets": {
            target_id: {
                "runtime": dict(entry["runtime"]),
                "dependencies": len(entry["dependencies"]),
                "optional_components": [
                    {"id": item["id"], "kind": item["kind"],
                     "available": item["available"]}
                    for item in entry["optional_components"]
                ],
            }
            for target_id, entry in manifest["targets"].items()
        },
    }

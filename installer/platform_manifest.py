"""Platform manifest loading and validation for the bootstrapper.

A platform manifest is a JSON document that describes one product release:
base URLs, one entry per platform (launcher, ordered component list, runtime
component) and the components themselves (id, kind, version, archive format,
destination, sha256, size, relative URL, supported platforms).

The template shipped as installer/platform_manifest.json is intentionally not
release-ready: it documents the schema and the platform matrix, while real
manifests are emitted by scripts/build_release.py or authored by the release
pipeline with real hashes and sizes.
"""
from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

SCHEMA_VERSION = 1
ARCHIVE_FORMATS = ("zip", "file")
COMPONENT_KINDS = ("app", "runtime", "assets", "config", "launcher", "offline")
PLATFORM_KEYS = ("windows-x86_64", "windows-arm64", "linux-x86_64", "linux-aarch64",
                 "macos-x86_64", "macos-arm64")
HEX = set("0123456789abcdef")


class ManifestError(ValueError):
    """Raised when a platform manifest is missing, malformed or unsafe."""


def load_manifest(path: str | Path) -> dict:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ManifestError("manifest not found: " + str(manifest_path))
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError("cannot read manifest: " + str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise ManifestError("manifest is not valid JSON: " + str(exc)) from exc
    return validate_manifest(data)


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError("manifest field must be a non-empty string: " + field)
    return value.strip()


def _sha256_value(value, field: str, *, release_ready: bool) -> str:
    if value is None or value == "":
        if release_ready:
            raise ManifestError("release-ready manifest requires sha256: " + field)
        return ""
    text = str(value).strip().lower()
    if len(text) != 64 or any(char not in HEX for char in text):
        raise ManifestError("invalid sha256: " + field)
    return text


def _destination(value) -> str:
    text = str(value or ".").strip().replace(chr(92), "/")
    if text in ("", "."):
        return "."
    if text.startswith("/") or ":" in text.split("/", 1)[0]:
        raise ManifestError("component destination must be relative: " + text)
    parts = [part for part in text.split("/") if part]
    if any(part == ".." for part in parts):
        raise ManifestError("component destination must not escape the target: " + text)
    return "/".join(parts)


def validate_manifest(data) -> dict:
    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("unsupported manifest schema_version: "
                            + str(data.get("schema_version")))
    product = data.get("product")
    if not isinstance(product, dict):
        raise ManifestError("manifest.product is required")
    product_id = _text(product.get("id"), "product.id")
    product_version = _text(product.get("version"), "product.version")
    _text(product.get("name", product_id), "product.name")
    channel = str(product.get("channel") or "stable")
    release_ready = bool(data.get("release_ready", True))

    base_urls = data.get("base_urls")
    if not isinstance(base_urls, dict):
        raise ManifestError("manifest.base_urls is required")
    primary = _text(base_urls.get("primary"), "base_urls.primary")
    mirrors = base_urls.get("mirrors") or []
    if not isinstance(mirrors, list) or not all(isinstance(item, str) and item.strip()
                                                for item in mirrors):
        raise ManifestError("base_urls.mirrors must be a list of URLs")

    platforms = data.get("platforms")
    if not isinstance(platforms, dict) or not platforms:
        raise ManifestError("manifest.platforms must be a non-empty object")
    raw_components = data.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ManifestError("manifest.components must be a non-empty list")
    components: list[dict] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_components):
        if not isinstance(item, dict):
            raise ManifestError("component #" + str(index) + " must be an object")
        component_id = _text(item.get("id"), "components[" + str(index) + "].id")
        if component_id in seen_ids:
            raise ManifestError("duplicate component id: " + component_id)
        seen_ids.add(component_id)
        kind = str(item.get("kind") or "app")
        if kind not in COMPONENT_KINDS:
            raise ManifestError("unsupported component kind for " + component_id + ": " + kind)
        archive = str(item.get("archive") or "zip")
        if archive not in ARCHIVE_FORMATS:
            raise ManifestError("unsupported archive format for " + component_id + ": " + archive)
        url = _text(item.get("url"), "components." + component_id + ".url")
        if archive == "file" and url.endswith("/"):
            raise ManifestError("file component URL must name a file: " + component_id)
        version = _text(item.get("version"), "components." + component_id + ".version")
        optional = bool(item.get("optional", False))
        required = bool(release_ready and not optional)
        sha256 = _sha256_value(item.get("sha256"), "components." + component_id + ".sha256",
                               release_ready=required)
        raw_size = item.get("size")
        if raw_size is None or raw_size == "":
            size = 0
        else:
            try:
                size = int(raw_size)
            except (TypeError, ValueError) as exc:
                raise ManifestError("invalid size for component " + component_id) from exc
            if size < 0:
                raise ManifestError("negative size for component " + component_id)
        if required and size <= 0:
            raise ManifestError("release-ready manifest requires a positive size: " + component_id)
        platforms_field = item.get("platforms") or []
        if not isinstance(platforms_field, list) or not all(
                isinstance(entry, str) for entry in platforms_field):
            raise ManifestError("component platforms must be a list of strings: " + component_id)
        for entry in platforms_field:
            if entry not in PLATFORM_KEYS:
                raise ManifestError("unknown platform for component " + component_id + ": " + entry)
        components.append({
            "id": component_id,
            "kind": kind,
            "version": version,
            "archive": archive,
            "destination": _destination(item.get("destination")),
            "sha256": sha256,
            "size": size,
            "url": url,
            "platforms": list(platforms_field),
            "optional": optional,
            "placeholder": bool(item.get("placeholder", not required)),
        })

    by_id = {component["id"]: component for component in components}
    normalized_platforms: dict[str, dict] = {}
    for platform_id, entry in platforms.items():
        platform_text = str(platform_id)
        if platform_text not in PLATFORM_KEYS:
            raise ManifestError("unknown platform: " + platform_text)
        if not isinstance(entry, dict):
            raise ManifestError("platform entry must be an object: " + platform_text)
        display_name = _text(entry.get("display_name", platform_text),
                             "platforms." + platform_text + ".display_name")
        launcher = _text(entry.get("launcher"), "platforms." + platform_text + ".launcher")
        runtime_component = _text(entry.get("runtime_component"),
                                  "platforms." + platform_text + ".runtime_component")
        if runtime_component not in by_id:
            raise ManifestError("platform runtime component is not defined: " + runtime_component)
        if by_id[runtime_component]["kind"] != "runtime":
            raise ManifestError("platform runtime_component must be a runtime component: "
                                + runtime_component)
        ordered = entry.get("components")
        if not isinstance(ordered, list) or not ordered:
            raise ManifestError("platform components must be a non-empty list: " + platform_text)
        ordered_ids: list[str] = []
        for component_id in ordered:
            component_text = str(component_id)
            if component_text not in by_id:
                raise ManifestError("platform references unknown component: " + component_text)
            ordered_ids.append(component_text)
        for component_id in ordered_ids:
            component = by_id[component_id]
            if component["platforms"] and platform_text not in component["platforms"]:
                raise ManifestError("component " + component_id
                                    + " is not declared for platform " + platform_text)
        normalized_platforms[platform_text] = {
            "display_name": display_name,
            "launcher": launcher,
            "runtime_component": runtime_component,
            "components": ordered_ids,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": str(data.get("status") or ("release" if release_ready else "template")),
        "release_ready": release_ready,
        "generated_by": str(data.get("generated_by") or ""),
        "generated_at": str(data.get("generated_at") or ""),
        "product": {
            "id": product_id,
            "name": str(product.get("name") or product_id),
            "version": product_version,
            "channel": channel,
        },
        "base_urls": {"primary": primary,
                      "mirrors": [item.strip() for item in mirrors]},
        "platforms": normalized_platforms,
        "components": components,
    }


def detect_platform() -> str:
    machine = platform.machine().lower()
    system = sys.platform
    if system.startswith("win"):
        if machine in ("arm64", "aarch64"):
            return "windows-arm64"
        return "windows-x86_64"
    if system.startswith("linux"):
        if machine in ("aarch64", "arm64"):
            return "linux-aarch64"
        return "linux-x86_64"
    if system == "darwin":
        return "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x86_64"
    raise ManifestError("unsupported host platform: " + system + "/" + machine)


def resolve_platform(manifest: dict, platform_id: str | None = None) -> str:
    chosen = platform_id or detect_platform()
    if chosen not in manifest["platforms"]:
        raise ManifestError("platform not supported by this manifest: " + chosen
                            + " (supported: " + ", ".join(sorted(manifest["platforms"])) + ")")
    return chosen


def components_for_platform(manifest: dict, platform_id: str) -> list[dict]:
    platform_entry = manifest["platforms"][platform_id]
    by_id = {component["id"]: component for component in manifest["components"]}
    return [dict(by_id[component_id]) for component_id in platform_entry["components"]]


def component_url(manifest: dict, component: dict) -> str:
    url = str(component["url"])
    if url.startswith(("http://", "https://", "file://")):
        return url
    base = str(manifest["base_urls"]["primary"]).rstrip("/")
    return base + "/" + url.lstrip("/")


def manifest_summary(manifest: dict) -> dict:
    return {
        "schema_version": manifest["schema_version"],
        "status": manifest["status"],
        "release_ready": manifest["release_ready"],
        "product": dict(manifest["product"]),
        "base_urls": dict(manifest["base_urls"]),
        "platforms": sorted(manifest["platforms"]),
        "components": [{
            "id": component["id"],
            "kind": component["kind"],
            "version": component["version"],
            "size": component["size"],
            "archive": component["archive"],
            "sha256": component["sha256"],
        } for component in manifest["components"]],
    }

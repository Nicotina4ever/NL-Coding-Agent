"""Canonical native targets for the cross-platform private beta.

This module is the single source of truth for the six supported OS/architecture
targets. It is used by the runtime manifest, the provisioner, the release
builder and the tests.

Target ids are stable and match installer.platform_manifest.PLATFORM_KEYS:

    windows-x86_64, windows-arm64,
    linux-x86_64,   linux-aarch64,
    macos-x86_64,   macos-arm64

A native runtime is selected only for exactly one of these targets. The local
repository python/ runtime is a Windows x64 development runtime and MUST NOT be
reused for any other target: the provisioner works from manifest-declared
artifacts only.
"""
from __future__ import annotations

import platform
import sys

TARGET_ORDER = (
    "windows-x86_64",
    "windows-arm64",
    "linux-x86_64",
    "linux-aarch64",
    "macos-x86_64",
    "macos-arm64",
)

SUPPORTED_TARGETS = {
    "windows-x86_64": {
        "os": "windows",
        "arch": "x86_64",
        "machine_aliases": ("amd64", "x86_64", "x64"),
        "display_name": "Windows 11 x64",
        "launcher": "NL Coding Agent.bat",
        "runtime_id": "python-runtime-windows-x86_64",
        "archive": "zip",
        "platform": "windows",
        "universal2": False,
    },
    "windows-arm64": {
        "os": "windows",
        "arch": "arm64",
        "machine_aliases": ("arm64", "aarch64"),
        "display_name": "Windows 11 ARM64",
        "launcher": "NL Coding Agent.bat",
        "runtime_id": "python-runtime-windows-arm64",
        "archive": "zip",
        "platform": "windows",
        "universal2": False,
    },
    "linux-x86_64": {
        "os": "linux",
        "arch": "x86_64",
        "machine_aliases": ("x86_64", "amd64"),
        "display_name": "Linux x86_64",
        "launcher": "NL Coding Agent.sh",
        "runtime_id": "python-runtime-linux-x86_64",
        "archive": "tar.gz",
        "platform": "linux",
        "universal2": False,
    },
    "linux-aarch64": {
        "os": "linux",
        "arch": "aarch64",
        "machine_aliases": ("aarch64", "arm64"),
        "display_name": "Linux ARM64",
        "launcher": "NL Coding Agent.sh",
        "runtime_id": "python-runtime-linux-aarch64",
        "archive": "tar.gz",
        "platform": "linux",
        "universal2": False,
    },
    "macos-x86_64": {
        "os": "macos",
        "arch": "x86_64",
        "machine_aliases": ("x86_64", "amd64"),
        "display_name": "macOS Intel (x86_64)",
        "launcher": "NL Coding Agent.sh",
        "runtime_id": "python-runtime-macos-x86_64",
        "archive": "tar.gz",
        "platform": "macos",
        "universal2": False,
    },
    "macos-arm64": {
        "os": "macos",
        "arch": "arm64",
        "machine_aliases": ("arm64", "aarch64"),
        "display_name": "macOS Apple Silicon (arm64)",
        "launcher": "NL Coding Agent.sh",
        "runtime_id": "python-runtime-macos-arm64",
        "archive": "tar.gz",
        "platform": "macos",
        "universal2": False,
    },
}

_UNSUPPORTED_GUIDANCE = (
    "Supported targets: " + ", ".join(TARGET_ORDER) + ". "
    "A native runtime must be provided for the detected OS/architecture; the "
    "Windows embedded python/ runtime is not portable and is never reused on "
    "Linux or macOS. For an unsupported host use an explicitly supported "
    "target with a prebuilt runtime artifact, or request a beta build for that "
    "platform. See docs/BOOTSTRAPPER.md (cross-platform beta)."
)


class UnsupportedTargetError(ValueError):
    """Raised when the host/target OS or architecture is not supported."""

    def __init__(self, message: str, *, host: str | None = None):
        super().__init__(message)
        self.host = host


def arch_family(machine: str) -> str:
    """Canonical architecture family used for selector matching."""
    value = str(machine or "").strip().lower()
    if value in ("amd64", "x86_64", "x64", "x86-64"):
        return "x86_64"
    if value in ("arm64", "aarch64", "arm64e"):
        return "arm64"
    return value


def normalise_machine(machine: str) -> str:
    return arch_family(machine)


def detect_host_target(system: str | None = None, machine: str | None = None) -> str:
    """Return the canonical target for this host, or fail closed with guidance."""
    system_value = (system if system is not None else sys.platform).lower()
    raw_machine = str(machine if machine is not None else platform.machine()).strip().lower()
    machine_family = arch_family(raw_machine)
    if system_value.startswith("win"):
        os_name = "windows"
    elif system_value.startswith("linux"):
        os_name = "linux"
    elif system_value == "darwin" or system_value.startswith("mac"):
        os_name = "macos"
    else:
        raise UnsupportedTargetError(
            "unsupported host operating system: " + system_value + ". " + _UNSUPPORTED_GUIDANCE,
            host=system_value + "/" + raw_machine,
        )
    for target_id in TARGET_ORDER:
        descriptor = SUPPORTED_TARGETS[target_id]
        if descriptor["os"] == os_name and arch_family(descriptor["arch"]) == machine_family:
            return target_id
    raise UnsupportedTargetError(
        "unsupported host architecture: " + os_name + "/" + raw_machine + ". "
        + _UNSUPPORTED_GUIDANCE,
        host=os_name + "/" + raw_machine,
    )


def resolve_target(target_id: str | None = None, *, system: str | None = None,
                   machine: str | None = None) -> str:
    """Resolve an explicit target id (or detect the host target)."""
    if target_id is None or str(target_id).strip() == "":
        return detect_host_target(system=system, machine=machine)
    value = str(target_id).strip().lower()
    aliases = {
        "windows-x64": "windows-x86_64",
        "win-x86_64": "windows-x86_64",
        "win-x64": "windows-x86_64",
        "windows-amd64": "windows-x86_64",
        "windows-aarch64": "windows-arm64",
        "win-arm64": "windows-arm64",
        "linux-x64": "linux-x86_64",
        "linux-amd64": "linux-x86_64",
        "linux-arm64": "linux-aarch64",
        "linux-arm": "linux-aarch64",
        "macos-x64": "macos-x86_64",
        "macos-amd64": "macos-x86_64",
        "macos-intel": "macos-x86_64",
        "macos-aarch64": "macos-arm64",
        "macos-apple-silicon": "macos-arm64",
        "darwin-arm64": "macos-arm64",
        "darwin-x86_64": "macos-x86_64",
    }
    value = aliases.get(value, value)
    if value not in SUPPORTED_TARGETS:
        raise UnsupportedTargetError(
            "unsupported target: " + str(target_id) + ". " + _UNSUPPORTED_GUIDANCE,
            host=str(target_id),
        )
    return value


def target_descriptor(target_id: str) -> dict:
    return dict(SUPPORTED_TARGETS[resolve_target(target_id)])


def target_ids() -> tuple[str, ...]:
    return TARGET_ORDER


def launcher_for_target(target_id: str) -> str:
    return str(SUPPORTED_TARGETS[resolve_target(target_id)]["launcher"])


def runtime_component_id(target_id: str) -> str:
    return str(SUPPORTED_TARGETS[resolve_target(target_id)]["runtime_id"])


def is_windows_runtime_id(value: str) -> bool:
    text = str(value or "").lower()
    return "windows" in text or text.endswith(".exe") or "win32" in text or "amd64" in text


def ensure_native_target(component: dict, target_id: str) -> None:
    """Guard: a runtime artifact for one OS/arch must never be used for another.

    Windows artifacts are rejected on Linux/macOS even if a manifest wrongly
    declares them for that platform. Conversely, non-Windows artifacts are
    rejected for Windows targets. The check is applied by the provisioner before
    any artifact is fetched or executed.
    """
    descriptor = SUPPORTED_TARGETS[resolve_target(target_id)]
    component_id = str(component.get("id") or "")
    url = str(component.get("url") or "")
    declared = [str(item) for item in (component.get("platforms") or [])]
    if declared and target_id not in declared:
        raise UnsupportedTargetError(
            "runtime component " + component_id + " is not declared for target "
            + target_id + "; refusing cross-platform reuse. " + _UNSUPPORTED_GUIDANCE
        )
    text = (component_id + " " + url).lower()
    target_os = descriptor["os"]
    for foreign in ("windows", "linux", "macos"):
        if foreign == target_os:
            continue
        if foreign in text:
            raise UnsupportedTargetError(
                "refusing to use " + foreign + " runtime artifact " + component_id
                + " on target " + target_id + ": native runtime selection is strict and "
                "the Windows embedded runtime is never reused on Linux/macOS. "
                + _UNSUPPORTED_GUIDANCE
            )
    if target_os != "windows" and is_windows_runtime_id(component_id):
        raise UnsupportedTargetError(
            "refusing to use Windows runtime " + component_id + " on target "
            + target_id + ". " + _UNSUPPORTED_GUIDANCE
        )

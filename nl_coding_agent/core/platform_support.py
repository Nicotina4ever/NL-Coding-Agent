"""Cross-platform support declarations and optional-backend capability probes (NL-BP-153).

This module is the single place where the application states, in machine-readable
form, what it *supports* and what it merely *expects to work* on each of the six
private-beta targets:

    windows-x86_64, windows-arm64, linux-x86_64, linux-aarch64,
    macos-x86_64, macos-arm64

Honesty rules (see docs/PLATFORM_COMPATIBILITY_MATRIX.md):

* "verified" only ever means *automated/static evidence recorded in this
  repository environment* (today: Windows x86_64 only). It never means real
  hardware, clean-machine or cross-platform acceptance.
* Every other target is "manual-pending": the shared code exists but no build or
  run has been recorded there. CI success must not be promoted to support.
* Optional backends (GPU telemetry, ASR/TTS, audio capture, language servers,
  debuggers) are probed read-only and fail closed with deterministic codes.
  CUDA, ROCm, Metal and MLX are never required; no accelerator is forced.
* The module performs **no network I/O, no model calls and no process
  execution by default**. The one bounded-telemetry probe accepts an injected
  runner callable so tests stay hardware-free. Callers that are allowed to run
  a fixed read-only command (e.g. the GUI status bar for nvidia-smi) inject it.

No OS forks: the same package is imported everywhere; platform differences are
expressed as declarations/probes, not as separate code bases.
"""
from __future__ import annotations

import importlib.util
import os
import platform as _platform
import shutil
import sys
from dataclasses import dataclass
from typing import Callable, Mapping

__all__ = [
    "PLATFORM_IDS", "FEATURE_AREAS", "LEVEL_VERIFIED", "LEVEL_PARTIAL",
    "LEVEL_MANUAL_PENDING", "LEVEL_UNSUPPORTED",
    "PLATFORM_STATUS_LOCAL_PARTIAL", "PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY",
    "PlatformSupportError", "UnsupportedPlatformError",
    "UnsupportedConfigurationError", "PlatformInfo", "PlatformDeclaration",
    "FeatureDeclaration", "detect_platform", "require_supported_platform",
    "platform_declarations", "get_platform_declaration",
    "feature_declaration", "feature_level", "support_snapshot",
    "probe_optional_backends", "require_optional_backend", "probe_gpu",
    "environment_report",
]

# ---------------------------------------------------------------------------
# Canonical target identifiers (aligned with installer/platform_manifest.py
# PLATFORM_KEYS; duplicated here so this module has no ownership coupling).
# ---------------------------------------------------------------------------
PLATFORM_IDS: tuple[str, ...] = (
    "windows-x86_64",
    "windows-arm64",
    "linux-x86_64",
    "linux-aarch64",
    "macos-x86_64",
    "macos-arm64",
)
_SUPPORTED = frozenset(PLATFORM_IDS)

# Support levels used by the feature table. "verified" is only valid for a
# target where automated evidence exists in this repository environment.
LEVEL_VERIFIED = "verified"
LEVEL_PARTIAL = "partial"
LEVEL_MANUAL_PENDING = "manual-pending"
LEVEL_UNSUPPORTED = "unsupported"
_LEVELS = frozenset({LEVEL_VERIFIED, LEVEL_PARTIAL, LEVEL_MANUAL_PENDING, LEVEL_UNSUPPORTED})

PLATFORM_STATUS_LOCAL_PARTIAL = "local-verified-partial"
PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY = "manifest-schema-only"

MATRIX_DOC = "docs/PLATFORM_COMPATIBILITY_MATRIX.md"

FEATURE_AREAS: tuple[str, ...] = (
    "gui", "editor", "clipboard", "attachments", "microphone", "asr_tts",
    "ollama", "crewai", "terminal", "git", "lsp", "mcp", "gpu",
)

#: Optional local backends the application can use when a human installed them.
#: Names are stable codes; tests and diagnostics rely on them.
_BACKEND_SPECS: tuple[tuple[str, str, str | None, str | None, str], ...] = (
    # (name, kind, executable, python_module, install_hint)
    ("git", "executable", "git", None,
     "Install Git for your OS, then reopen the app."),
    ("ollama", "executable", "ollama", None,
     "Install Ollama locally and make sure `ollama` is on PATH; the app never downloads models."),
    ("ffmpeg", "executable", "ffmpeg", None,
     "Optional: install FFmpeg for your OS and put `ffmpeg` on PATH; attachments do not require it."),
    ("piper", "executable", "piper", None,
     "Optional TTS: install Piper for your OS and put `piper` on PATH."),
    ("tts:piper-python", "python", None, "piper",
     "Optional TTS: install the local Piper Python package (human action)."),
    ("asr:faster-whisper", "python", None, "faster_whisper",
     "Optional ASR: install faster-whisper and a local CTranslate2 model directory."),
    ("asr:vosk", "python", None, "vosk",
     "Optional ASR: install vosk and a local Vosk model directory."),
    ("asr:qwen3-asr", "python", None, "qwen3_asr",
     "Optional ASR: configure a local qwen3-asr package/model directory."),
    ("audio:qtaudio", "python", None, "PySide6.QtMultimedia",
     "Qt Multimedia is required for in-app audio capture; install the PySide6 wheels for your OS."),
    ("audio:sounddevice", "python", None, "sounddevice",
     "Optional audio: install sounddevice; it requires a PortAudio build for your OS."),
    ("debugpy", "python", None, "debugpy",
     "Optional debugger: install debugpy for a DAP session; pdb remains console-only."),
)
_LSP_SERVERS: tuple[tuple[str, str, str], ...] = (
    # (server_id, executable, languages)
    ("pylsp", "pylsp", "python"),
    ("pyright", "pyright-langserver", "python,typescript"),
    ("basedpyright", "basedpyright-langserver", "python"),
    ("clangd", "clangd", "c,cpp"),
    ("typescript", "typescript-language-server", "typescript,javascript"),
    ("gopls", "gopls", "go"),
)


class PlatformSupportError(RuntimeError):
    """Base class for deterministic platform/configuration support failures."""

    code = "platform-support-error"

    def __init__(self, message: str, *, code: str | None = None,
                 hint: str = "", detail: str = "") -> None:
        super().__init__(message)
        self.code = str(code or self.code)
        self.hint = str(hint or "")
        self.detail = str(detail or "")

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "hint": self.hint,
                "detail": self.detail}


class UnsupportedPlatformError(PlatformSupportError):
    """The host OS/CPU combination is not one of the declared beta targets."""

    code = "unsupported-platform"


class UnsupportedConfigurationError(PlatformSupportError):
    """A requested optional backend/capability is not available on this host."""

    code = "backend-unavailable"


@dataclass(frozen=True)
class PlatformInfo:
    """Detected host platform, with the canonical target id when declared."""

    os_name: str
    arch: str
    platform_id: str | None
    supported: bool
    reason: str = ""
    python_version: str = ""
    python_implementation: str = ""
    executable: str = ""

    def to_dict(self) -> dict:
        return {
            "os_name": self.os_name,
            "arch": self.arch,
            "platform_id": self.platform_id,
            "supported": self.supported,
            "reason": self.reason,
            "python_version": self.python_version,
            "python_implementation": self.python_implementation,
            "executable": self.executable,
        }


@dataclass(frozen=True)
class PlatformDeclaration:
    """What the repository declares for one target (never real-hardware proof)."""

    platform_id: str
    display_name: str
    os_name: str
    arch: str
    status: str
    ci_verifiable: bool
    runtime_manifest: str
    default_launcher: str
    notes: str

    def to_dict(self) -> dict:
        return {
            "platform_id": self.platform_id,
            "display_name": self.display_name,
            "os_name": self.os_name,
            "arch": self.arch,
            "status": self.status,
            "ci_verifiable": self.ci_verifiable,
            "runtime_manifest": self.runtime_manifest,
            "default_launcher": self.default_launcher,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class FeatureDeclaration:
    """Per-target support level for one product feature area."""

    feature: str
    levels: Mapping[str, str]
    ci_verifiable: bool
    manual_pending: str
    evidence: str

    def level(self, platform_id: str) -> str:
        try:
            return str(self.levels[platform_id])
        except KeyError as exc:  # pragma: no cover - table is validated below
            raise ValueError("Unknown platform for feature " + self.feature + ": "
                             + str(platform_id)) from exc

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "levels": dict(self.levels),
            "ci_verifiable": self.ci_verifiable,
            "manual_pending": self.manual_pending,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Platform declarations
# ---------------------------------------------------------------------------
_WINDOWS = "windows"
_LINUX = "linux"
_MACOS = "macos"
_X64 = "x86_64"
_ARM64 = "arm64"

_PLATFORM_DECLARATIONS: tuple[PlatformDeclaration, ...] = (
    PlatformDeclaration(
        "windows-x86_64", "Windows 11 x64", _WINDOWS, _X64,
        PLATFORM_STATUS_LOCAL_PARTIAL, True,
        "developer embedded runtime present locally (python/python.exe); "
        "release runtime is an external prebuilt archive",
        "NL Coding Agent.bat",
        "Only target with local runtime evidence. Real clean-machine/desktop "
        "acceptance remains MANUAL-PENDING.",
    ),
    PlatformDeclaration(
        "windows-arm64", "Windows 11 ARM64", _WINDOWS, _ARM64,
        PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY, True,
        "none (manifest schema accepts the key only)",
        "NL Coding Agent.bat (Windows launcher; runtime missing)",
        "No native runtime/wheels evidenced; CrewAI native dependencies "
        "(chromadb/lancedb/onnxruntime) have no Windows ARM64 artifacts in this repo.",
    ),
    PlatformDeclaration(
        "linux-x86_64", "Linux x86_64", _LINUX, _X64,
        PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY, True,
        "template entry + build_release platform entry only (placeholder sha256/size)",
        "NL Coding Agent.sh (planned; not shipped)",
        "Bootstrapper schema supports it; no Linux runtime archive, launcher or "
        "real run evidenced.",
    ),
    PlatformDeclaration(
        "linux-aarch64", "Linux ARM64", _LINUX, _ARM64,
        PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY, True,
        "none (manifest schema accepts the key only)",
        "NL Coding Agent.sh (planned; not shipped)",
        "No native runtime/wheels evidenced; ARM64 wheel availability for the "
        "CrewAI native stack must be verified by the release runner (C2).",
    ),
    PlatformDeclaration(
        "macos-x86_64", "macOS Intel", _MACOS, _X64,
        PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY, True,
        "none (manifest schema accepts the key only)",
        "NL Coding Agent.command (planned; not shipped)",
        "No macOS runtime, launcher or notarization evidence; Universal 2 decision open.",
    ),
    PlatformDeclaration(
        "macos-arm64", "macOS Apple Silicon", _MACOS, _ARM64,
        PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY, True,
        "none (manifest schema accepts the key only)",
        "NL Coding Agent.command (planned; not shipped)",
        "No macOS runtime, launcher or notarization evidence; Universal 2 decision open.",
    ),
)

# ---------------------------------------------------------------------------
# Feature declarations. Levels are evidence-bound; see the matrix document for
# file:line evidence and for the CI-verifiable vs MANUAL-PENDING split.
# ---------------------------------------------------------------------------
_WIN_ONLY_VERIFIED: dict[str, str] = {
    "windows-x86_64": LEVEL_VERIFIED,
    "windows-arm64": LEVEL_MANUAL_PENDING,
    "linux-x86_64": LEVEL_MANUAL_PENDING,
    "linux-aarch64": LEVEL_MANUAL_PENDING,
    "macos-x86_64": LEVEL_MANUAL_PENDING,
    "macos-arm64": LEVEL_MANUAL_PENDING,
}
_WIN_PARTIAL: dict[str, str] = {**_WIN_ONLY_VERIFIED, "windows-x86_64": LEVEL_PARTIAL}


_FEATURE_DECLARATIONS: tuple[FeatureDeclaration, ...] = (
    FeatureDeclaration(
        "gui", dict(_WIN_ONLY_VERIFIED), True,
        "Real desktop session per target: display server/window manager, focus, "
        "DPI scaling, tray/desktop integration. Offscreen Qt tests are CI-verifiable only.",
        "PySide6 6.12.0 (win_amd64) in python/; gui/main.py, gui/main_window.py; "
        "tests/test_gui_smoke.py, test_gui_panels.py, test_model_hub.py",
    ),
    FeatureDeclaration(
        "editor", dict(_WIN_ONLY_VERIFIED), True,
        "Real editor interaction and file-dialog behaviour on each desktop target.",
        "gui/widgets/editor_panel.py; app/services.py save path; "
        "tests/test_editor_panel.py (Windows x64 only evidence)",
    ),
    FeatureDeclaration(
        "clipboard", dict(_WIN_PARTIAL), False,
        "Real screenshot/clipboard and drag-and-drop on each desktop session "
        "(Qt offscreen cannot exercise OS clipboard integration).",
        "gui/widgets/chat_panel.py:239-308 (QClipboard/QMimeData/QImage); "
        "app/attachments.py prepare_clipboard_image; tests/test_chat_panel.py",
    ),
    FeatureDeclaration(
        "attachments", dict(_WIN_ONLY_VERIFIED), True,
        "Optional PDF/Office extraction libraries are not installed; their "
        "availability is probed per host (fail-closed).",
        "app/attachments.py extraction_availability(); tests/test_attachments.py",
    ),
    FeatureDeclaration(
        "microphone", dict(_WIN_PARTIAL), False,
        "Real microphone capture and OS audio backend per target; QtMultimedia or "
        "sounddevice with native PortAudio must be installed and tested by a human.",
        "app/speech.py:284-337 list_input_devices/start_recording; :464-532 "
        "QAudioSource recorder (not exercised by unit tests)",
    ),
    FeatureDeclaration(
        "asr_tts", dict(_WIN_PARTIAL), True,
        "Real ASR engines/models (faster-whisper, vosk, qwen3-asr) and TTS backends "
        "(Piper/local command) are optional local installs, absent here; lifecycle is tested with fakes.",
        "app/speech.py:122-144 detect_capabilities; :397-413 local ASR; :415-457 TTS; "
        "tests/test_speech.py, test_chat_voice.py",
    ),
    FeatureDeclaration(
        "ollama", dict(_WIN_ONLY_VERIFIED), True,
        "Ollama models must be installed and run on each target; model execution, "
        "GPU offload and model quality are out of audit scope.",
        "models/ollama_registry.py (HTTP + CLI fallback, no bundling); "
        "tools/registry.py ollama probe; local `ollama` found on PATH in this environment",
    ),
    FeatureDeclaration(
        "crewai", dict(_WIN_ONLY_VERIFIED), True,
        "CrewAI 1.15.32 import/unit evidence exists on Windows x64 only; its native "
        "dependency wheels (chromadb, lancedb, onnxruntime, tokenizers, pydantic-core) "
        "are unverified for ARM64/macOS targets and must be resolved by C2.",
        "crewai 1.15.32 + litellm 1.100.4 installed in python/ (win_amd64 native "
        "wheels); agents/crew_backend.py, flows/*; tests/test_crewai_compat.py, "
        "test_crewai_runtime.py",
    ),
    FeatureDeclaration(
        "terminal", dict(_WIN_ONLY_VERIFIED), True,
        "Per-target shell semantics: the policy is argv-based and refuses shells, but "
        "command allow/deny lists mention both POSIX and Windows names; POSIX "
        "behaviour is unverified.",
        "app/services.py:443-576 terminal policy + shell=False runner; "
        "gui/widgets/terminal_panel.py QProcess; tests/test_terminal_policy.py",
    ),
    FeatureDeclaration(
        "git", dict(_WIN_ONLY_VERIFIED), True,
        "Git must be installed on each target; no bundling. Real repository "
        "operations are read-only by policy.",
        "tools/git_tools.py, app/services.py:578-600 read-only git; "
        "gui/widgets/git_panel.py; tests/test_git_panel.py",
    ),
    FeatureDeclaration(
        "lsp", dict(_WIN_PARTIAL), True,
        "Real language servers (pylsp/pyright/clangd/...) are not installed; the client "
        "and detection are tested with injected transports only. Server installation is a human action.",
        "app/lsp.py (detection via shutil.which, JSON-RPC stdio, no auto-install); "
        "tests/test_lsp_client.py",
    ),
    FeatureDeclaration(
        "mcp", dict(_WIN_PARTIAL), True,
        "Real MCP servers are external local processes; only the stdio client, config "
        "validation and gated invocation are tested. No network transport is supported.",
        "app/mcp.py (stdio only, shell=False, approval-gated invocation); "
        "tests/test_mcp_integration.py",
    ),
    FeatureDeclaration(
        "gpu", dict(_WIN_PARTIAL), False,
        "GPU telemetry is NVIDIA-only and optional; AMD ROCm and Apple Metal/MLX are "
        "not queried and are never required. Real hardware measurements are MANUAL-PENDING.",
        "gui/main_window.py:503-518 `nvidia-smi` status bar probe (optional, "
        "unknown reported as em dash); resource_gate.py is model/lease based, no CUDA import",
    ),
)
if len(_FEATURE_DECLARATIONS) != len(FEATURE_AREAS):  # pragma: no cover
    raise RuntimeError("feature declaration table is incomplete")
_FEATURE_BY_NAME = {item.feature: item for item in _FEATURE_DECLARATIONS}
_PLATFORM_BY_ID = {item.platform_id: item for item in _PLATFORM_DECLARATIONS}


def _normalise_system(value: str) -> str:
    text = str(value or "").strip().lower()
    if text.startswith(("win", "cygwin", "msys")):
        return _WINDOWS
    if text.startswith("linux"):
        return _LINUX
    if text in ("darwin", "macos", "mac", "osx"):
        return _MACOS
    return text


def _normalise_machine(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in ("amd64", "x86_64", "x64", "x86-64"):
        return _X64
    if text in ("arm64", "aarch64", "armv8", "armv8l"):
        return _ARM64
    return text


_PLATFORM_ID_BY_OS_ARCH: dict[tuple[str, str], str] = {
    (_WINDOWS, _X64): "windows-x86_64",
    (_WINDOWS, _ARM64): "windows-arm64",
    (_LINUX, _X64): "linux-x86_64",
    (_LINUX, _ARM64): "linux-aarch64",  # canonical id for Linux ARM64
    (_MACOS, _X64): "macos-x86_64",
    (_MACOS, _ARM64): "macos-arm64",
}


def platform_id_for(system: str, machine: str) -> str | None:
    """Map a system/machine pair to a canonical target id, or None."""
    os_name = _normalise_system(system)
    arch = _normalise_machine(machine)
    return _PLATFORM_ID_BY_OS_ARCH.get((os_name, arch))


def detect_platform(
    *,
    system: str | None = None,
    machine: str | None = None,
    python_version: str | None = None,
    python_implementation: str | None = None,
    executable: str | None = None,
) -> PlatformInfo:
    """Detect the host platform without importing or executing anything.

    Every input can be injected so tests can cover each declared branch (including
    unsupported hosts) without touching real hardware. Defaults read the running Python.
    """
    system_value = sys.platform if system is None else system
    machine_value = (
        _platform.machine() if machine is None else machine
    )
    os_name = _normalise_system(system_value)
    arch = _normalise_machine(machine_value)
    platform_id = platform_id_for(system_value, machine_value)
    reason = ""
    if platform_id is None:
        reason = (
            "host " + str(system_value) + "/" + str(machine_value)
            + " is not one of the declared beta targets: " + ", ".join(PLATFORM_IDS)
        )
    return PlatformInfo(
        os_name=os_name,
        arch=arch,
        platform_id=platform_id,
        supported=platform_id is not None,
        reason=reason,
        python_version=str(python_version if python_version is not None
                           else _platform.python_version()),
        python_implementation=str(python_implementation
                                  if python_implementation is not None
                                  else _platform.python_implementation()),
        executable=str(executable if executable is not None else sys.executable),
    )


def require_supported_platform(
    *,
    system: str | None = None,
    machine: str | None = None,
    info: PlatformInfo | None = None,
) -> PlatformInfo:
    """Return the detected PlatformInfo or raise UnsupportedPlatformError."""
    resolved = info or detect_platform(system=system, machine=machine)
    if not resolved.supported:
        raise UnsupportedPlatformError(
            "Unsupported host platform: " + resolved.os_name + "/" + resolved.arch
            + ". NL Coding Agent declares these beta targets: "
            + ", ".join(PLATFORM_IDS) + ".",
            code="unsupported-platform",
            hint="See " + MATRIX_DOC + " for the evidence and the MANUAL-PENDING list. "
                 "No unsupported configuration is forced; the application can still start "
                 "for diagnostics on unknown platforms when callers opt out of this check.",
            detail=resolved.reason,
        )
    return resolved


def platform_declarations() -> tuple[PlatformDeclaration, ...]:
    """Return the six platform declarations."""
    return _PLATFORM_DECLARATIONS


def get_platform_declaration(platform_id: str) -> PlatformDeclaration:
    key = str(platform_id or "").strip()
    try:
        return _PLATFORM_BY_ID[key]
    except KeyError as exc:
        raise ValueError(
            "Unknown platform id " + repr(platform_id) + "; expected one of "
            + ", ".join(PLATFORM_IDS)
        ) from exc


def feature_declaration(feature: str) -> FeatureDeclaration:
    key = str(feature or "").strip()
    try:
        return _FEATURE_BY_NAME[key]
    except KeyError as exc:
        raise ValueError(
            "Unknown feature area " + repr(feature) + "; expected one of "
            + ", ".join(FEATURE_AREAS)
        ) from exc


def feature_level(feature: str, platform_id: str) -> str:
    """Return the declared level for one feature/platform pair."""
    return feature_declaration(feature).level(str(platform_id))


def support_snapshot() -> dict:
    """JSON-safe declaration snapshot (used by diagnostics and the matrix)."""
    return {
        "matrix_document": MATRIX_DOC,
        "platforms": [item.to_dict() for item in _PLATFORM_DECLARATIONS],
        "features": [item.to_dict() for item in _FEATURE_DECLARATIONS],
        "levels": sorted(_LEVELS),
        "notes": "Declarations describe code/artifact status only; real-hardware "
                 "and clean-machine acceptance is MANUAL-PENDING on every target.",
    }


# ---------------------------------------------------------------------------
# Optional-backend probes (read-only, no network, no process execution)
# ---------------------------------------------------------------------------
def _probe_entry(name: str, kind: str, available: bool, detail: str,
                 hint: str, code: str) -> dict:
    return {
        "name": name,
        "kind": kind,
        "required": False,
        "available": bool(available),
        "detail": detail,
        "install_hint": hint,
        "code": code,
    }


def _default_which(name: str) -> str | None:
    return shutil.which(name)


def _default_find_spec(name: str):
    try:
        return importlib.util.find_spec(name)
    except (ImportError, ValueError, ModuleNotFoundError):
        return None


def probe_optional_backends(
    *,
    which: Callable[[str], str | None] | None = None,
    find_spec: Callable[[str], object | None] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, dict]:
    """Probe optional local backends without executing any process or using network.

    Executables are resolved through PATH (or the injected `which`); Python
    integrations through importlib metadata (or the injected `find_spec`).
    Every result is fail-closed data: callers decide whether the backend is required
    for the requested action.
    """
    which_fn = which or _default_which
    spec_fn = find_spec or _default_find_spec
    env = environ if environ is not None else os.environ
    probes: dict[str, dict] = {}
    for name, kind, executable, module, hint in _BACKEND_SPECS:
        if kind == "executable":
            path = which_fn(str(executable))
            available = bool(path)
            probes[name] = _probe_entry(
                name, kind, available,
                "found at " + str(path) if available else "not found on PATH",
                hint, "ok" if available else "not-found",
            )
        else:
            present = spec_fn(str(module)) is not None
            probes[name] = _probe_entry(
                name, kind, present,
                "importable module " + str(module) if present
                else "module " + str(module) + " is not installed",
                hint, "ok" if present else "not-installed",
            )
    for server_id, executable, languages in _LSP_SERVERS:
        path = which_fn(executable)
        available = bool(path)
        probes["lsp:" + server_id] = _probe_entry(
            "lsp:" + server_id, "executable", available,
            ("found at " + str(path) if available
             else executable + " is not installed (no download is attempted)"),
            "Install " + executable + " for your OS to use it as a language server "
            "(" + languages + ").",
            "ok" if available else "not-found",
        )
    tts_command = str(env.get("NL_TTS_COMMAND", "") or "").strip()
    probes["tts:local-command"] = _probe_entry(
        "tts:local-command", "configuration", bool(tts_command),
        ("NL_TTS_COMMAND is configured" if tts_command
         else "NL_TTS_COMMAND is not set"),
        "Set NL_TTS_COMMAND to a local TTS command for your OS.",
        "configured" if tts_command else "not-configured",
    )
    probes["mcp:stdio"] = _probe_entry(
        "mcp:stdio", "internal", True,
        "built-in stdio MCP client (local servers only; no network transport)",
        "Configure local stdio MCP servers in mcp_servers.json.",
        "builtin",
    )
    return probes


def require_optional_backend(
    name: str,
    *,
    probes: Mapping[str, Mapping] | None = None,
    which: Callable[[str], str | None] | None = None,
    find_spec: Callable[[str], object | None] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict:
    """Return the probe entry for an optional backend or raise an actionable error.

    The error is deterministic (`backend-unavailable`) and contains the install
    hint; callers must not silently degrade past this point when the backend is
    required for the requested feature.
    """
    current = dict(probes) if probes is not None else probe_optional_backends(
        which=which, find_spec=find_spec, environ=environ)
    try:
        entry = dict(current[str(name)])
    except KeyError as exc:
        raise UnsupportedConfigurationError(
            "Unknown optional backend: " + repr(name),
            code="unknown-backend",
            hint="Known backends: " + ", ".join(sorted(current)),
        ) from exc
    if entry.get("required") is True and not entry.get("available"):
        raise UnsupportedConfigurationError(
            "Required backend is unavailable: " + str(name), code="backend-unavailable",
            hint=str(entry.get("install_hint") or ""),
            detail=str(entry.get("detail") or ""),
        )
    if not entry.get("available"):
        raise UnsupportedConfigurationError(
            "Optional backend is not available on this host: " + str(name)
            + " (the feature that needs it fails closed).",
            code="backend-unavailable",
            hint=str(entry.get("install_hint") or ""),
            detail=str(entry.get("detail") or ""),
        )
    return entry


# ---------------------------------------------------------------------------
# Optional GPU telemetry (never required, never forced; no hardware in tests)
# ---------------------------------------------------------------------------
_GPU_COMMANDS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("nvidia", "nvidia-smi",
     ("nvidia-smi", "--query-gpu=memory.used,memory.total",
      "--format=csv,noheader,nounits"), "nvidia-cuda"),
    ("amd", "rocm-smi", ("rocm-smi", "--showmeminfo", "vram"), "amd-rocm"),
)


def probe_gpu(
    *,
    platform: PlatformInfo | None = None,
    which: Callable[[str], str | None] | None = None,
    runner: Callable[[list[str]], Mapping] | None = None,
) -> dict:
    """Probe optional GPU telemetry, read-only.

    Defaults to **no process execution**: without an injected `runner` the probe
    only reports whether a telemetry command exists (via `which`). The GUI may
    inject a bounded runner for the status bar; tests never execute hardware.

    macOS is reported as manual-pending: Metal is an accelerator available to the
    OS, but this module does not query it and never requires it (nor MLX).
    """
    info = platform or detect_platform()
    which_fn = which or _default_which
    base = {
        "required": False,
        "forced": False,
        "cuda_required": False,
        "rocm_required": False,
        "metal_required": False,
        "mlx_required": False,
        "platform_id": info.platform_id,
    }
    if info.os_name == _MACOS:
        return {
            **base,
            "status": "manual-pending",
            "backend": None,
            "available": None,
            "accelerators": ["apple-metal"],
            "memory_used_mb": None,
            "memory_total_mb": None,
            "detail": "macOS GPU telemetry (Metal) is not queried in-process; Metal is "
                      "available to the OS but never required, and MLX is never required.",
        }
    for backend, executable, argv, accelerator in _GPU_COMMANDS:
        if backend == "amd" and info.os_name != _LINUX:
            continue
        resolved = which_fn(executable)
        if not resolved:
            continue
        common = {
            **base,
            "backend": backend,
            "accelerators": [accelerator, "cpu"],
            "memory_used_mb": None,
            "memory_total_mb": None,
        }
        if runner is None:
            return {
                **common,
                "status": "detected-not-queried",
                "available": None,
                "detail": executable + " found at " + str(resolved)
                          + "; telemetry is not queried without an injected runner "
                            "(read-only, bounded).",
            }
        command = list(argv)
        command[0] = str(resolved)
        try:
            result = runner(command)
            returncode = int(result.get("returncode", -1))
            stdout = str(result.get("stdout") or "")
            stderr = str(result.get("stderr") or "")
        except Exception as exc:  # noqa: BLE001 - optional telemetry must not crash
            return {**common, "status": "probe-failed", "available": None,
                    "detail": "GPU telemetry probe failed: " + str(exc)}
        if returncode != 0:
            return {**common, "status": "probe-failed", "available": None,
                    "detail": executable + " exited " + str(returncode)
                              + (": " + stderr.strip()[:200] if stderr.strip() else "")}
        used_mb = None
        total_mb = None
        try:
            first_line = stdout.strip().splitlines()[0]
            parts = [piece.strip() for piece in first_line.split(",")]
            if len(parts) >= 2:
                used_mb = float(parts[0])
                total_mb = float(parts[1])
        except (IndexError, TypeError, ValueError):
            used_mb = None
        if used_mb is None or total_mb is None:
            return {**common, "status": "probe-failed", "available": None,
                    "detail": "GPU telemetry output could not be parsed."}
        return {**common, "status": "available", "available": True,
                "memory_used_mb": used_mb, "memory_total_mb": total_mb,
                "detail": executable + " reported GPU memory telemetry (optional, "
                          "informational; no CUDA/ROCm requirement)."}
    return {
        **base,
        "status": "unavailable",
        "backend": None,
        "available": False,
        "accelerators": ["cpu"],
        "memory_used_mb": None,
        "memory_total_mb": None,
        "detail": "No NVIDIA/AMD GPU telemetry command found; the application runs "
                  "CPU-only. GPU acceleration is optional and never required.",
    }


# ---------------------------------------------------------------------------
# Aggregate diagnostic report (JSON-safe; used by beta diagnostics/C4 later)
# ---------------------------------------------------------------------------
def environment_report(
    *,
    system: str | None = None,
    machine: str | None = None,
    which: Callable[[str], str | None] | None = None,
    find_spec: Callable[[str], object | None] | None = None,
    environ: Mapping[str, str] | None = None,
    runner: Callable[[list[str]], Mapping] | None = None,
) -> dict:
    """Return one JSON-safe report: detection, declarations, probes and feature levels.

    No network, no model and no process execution happen here unless the caller
    injects a GPU `runner`.
    """
    info = detect_platform(system=system, machine=machine)
    probes = probe_optional_backends(which=which, find_spec=find_spec, environ=environ)
    gpu = probe_gpu(platform=info, which=which, runner=runner)
    declaration = None
    features: dict[str, dict] = {}
    if info.platform_id is not None:
        declaration = get_platform_declaration(info.platform_id).to_dict()
        features = {
            feature: {
                "level": feature_level(feature, info.platform_id),
                "ci_verifiable": feature_declaration(feature).ci_verifiable,
                "manual_pending": feature_declaration(feature).manual_pending,
            }
            for feature in FEATURE_AREAS
        }
    return {
        "platform": info.to_dict(),
        "declaration": declaration,
        "features": features,
        "optional_backends": probes,
        "gpu": gpu,
        "matrix_document": MATRIX_DOC,
        "real_hardware_verified": False,
    }
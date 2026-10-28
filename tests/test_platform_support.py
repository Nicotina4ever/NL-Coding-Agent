"""Platform abstraction tests: fake probes only, no hardware, no network, no models.

These tests cover every declared platform branch and the fail-closed optional
backend handling (NL-BP-153). They never execute a process, open a socket or load
a model; the real GPU runner is injected only with fakes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nl_coding_agent.core import platform_support as ps

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Declarations and detection
# ---------------------------------------------------------------------------
def test_platform_ids_are_exactly_the_six_beta_targets():
    assert ps.PLATFORM_IDS == (
        "windows-x86_64", "windows-arm64", "linux-x86_64", "linux-aarch64",
        "macos-x86_64", "macos-arm64",
    )
    assert len(set(ps.PLATFORM_IDS)) == 6
    declarations = ps.platform_declarations()
    assert [item.platform_id for item in declarations] == list(ps.PLATFORM_IDS)


def test_platform_declarations_do_not_overclaim_support():
    """C1c: declarations describe the post-C2/C3 reality without upgrading support."""
    for item in ps.platform_declarations():
        assert item.ci_verifiable is True
        assert item.notes
        assert item.status in {
            ps.PLATFORM_STATUS_LOCAL_PARTIAL,
            ps.PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY,
        }
        assert "pre-C2" not in item.runtime_manifest
        if item.platform_id == "windows-x86_64":
            assert item.status == ps.PLATFORM_STATUS_LOCAL_PARTIAL
            assert "developer embedded runtime" in item.runtime_manifest
            assert "NL Coding Agent.bat" in item.default_launcher
            assert "runtime manifest declares" in item.runtime_manifest
        else:
            assert item.status == ps.PLATFORM_STATUS_MANIFEST_SCHEMA_ONLY
            # Every non-Windows target now has a declared-but-unmeasured runtime.
            assert "six-target runtime manifest declares" in item.runtime_manifest
            assert "unmeasured" in item.runtime_manifest
            assert "developer embedded runtime" not in item.runtime_manifest
            if item.os_name == "windows":
                assert ".bat" in item.default_launcher
                assert "runtime missing" in item.default_launcher
            else:
                assert item.default_launcher.startswith("NL Coding Agent.sh")
                assert "payload root" in item.default_launcher
                assert "python/bin/python3" in item.default_launcher
                assert "unmeasured" in item.default_launcher
                assert "MANUAL-PENDING" in item.default_launcher
                assert "not shipped" not in item.default_launcher
    windows = ps.get_platform_declaration("windows-x86_64")
    assert "NL Coding Agent.bat" in windows.default_launcher
    assert "scripts/launchers/" in windows.default_launcher
    for macos_id in ("macos-x86_64", "macos-arm64"):
        declaration = ps.get_platform_declaration(macos_id)
        assert "Universal 2 not claimed" in declaration.runtime_manifest
        assert "separate-per-arch" in declaration.runtime_manifest


def test_posix_launchers_are_shipped_and_fail_closed():
    launchers = ROOT / "scripts" / "launchers"
    expected = ("NL Coding Agent.sh", "doctor.sh", "status.sh",
                "Self-Build Mode.sh", "NL Coding Agent.command")
    for name in expected:
        path = launchers / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env sh\n"), name
        assert '"$@"' in text, name
        if name != "NL Coding Agent.command":
            assert "nl_agent.py" in text, name
            assert "python/bin/python3" in text, name
            assert "python3" in text, name
            assert "BOOTSTRAPPER" in text or "bootstrap" in text, name
            assert "selfbuild" not in text or "Self-Build" in path.name, name
    doctor = (launchers / "doctor.sh").read_text(encoding="utf-8")
    assert "doctor" in doctor and "gui" not in doctor
    gui = (launchers / "NL Coding Agent.sh").read_text(encoding="utf-8")
    assert "gui" in gui and "selfbuild" not in gui
    command = (launchers / "NL Coding Agent.command").read_text(encoding="utf-8")
    assert "NL Coding Agent.sh" in command and "exec" in command
    if os.name != "nt":
        for name in expected:
            assert os.access(launchers / name, os.X_OK), name


def test_posix_launcher_shell_syntax_when_shell_available():
    import shutil
    import subprocess

    shell = shutil.which("bash") or shutil.which("sh")
    if not shell:
        pytest.skip("no POSIX shell available for syntax validation")
    launchers = ROOT / "scripts" / "launchers"
    for name in ("NL Coding Agent.sh", "doctor.sh", "status.sh",
                 "Self-Build Mode.sh", "NL Coding Agent.command"):
        source = (launchers / name).read_bytes()
        completed = subprocess.run([shell, "-n"], input=source,
                                   capture_output=True, timeout=30)
        stderr = (completed.stderr or b"").decode("utf-8", "replace").lower()
        if completed.returncode != 0 and "windows subsystem for linux" in stderr:
            pytest.skip("bash shim requires an installed WSL distribution")
        assert completed.returncode == 0, (
            name, (completed.stderr or b"")[-1000:])


def test_every_platform_declaration_is_json_safe():
    for item in ps.platform_declarations():
        payload = item.to_dict()
        assert json.loads(json.dumps(payload)) == payload
        assert payload["platform_id"] in ps.PLATFORM_IDS


@pytest.mark.parametrize(
    "system, machine, expected",
    [
        ("win32", "AMD64", "windows-x86_64"),
        ("win32", "x86_64", "windows-x86_64"),
        ("win32", "ARM64", "windows-arm64"),
        ("linux", "x86_64", "linux-x86_64"),
        ("linux2", "aarch64", "linux-aarch64"),
        ("linux", "arm64", "linux-aarch64"),
        ("darwin", "x86_64", "macos-x86_64"),
        ("darwin", "arm64", "macos-arm64"),
    ],
)
def test_detect_platform_covers_every_declared_branch(system, machine, expected):
    info = ps.detect_platform(system=system, machine=machine,
                              python_version="3.12.10",
                              python_implementation="CPython",
                              executable="/fake/python")
    assert info.platform_id == expected
    assert info.supported is True
    assert info.python_version == "3.12.10"
    assert info.executable == "/fake/python"
    assert info.os_name in {"windows", "linux", "macos"}
    assert info.arch in {"x86_64", "arm64"}
    assert json.loads(json.dumps(info.to_dict())) == info.to_dict()


def test_unknown_host_is_detected_but_not_supported():
    info = ps.detect_platform(system="freebsd13", machine="riscv64")
    assert info.platform_id is None
    assert info.supported is False
    assert "windows-x86_64" in info.reason
    with pytest.raises(ps.UnsupportedPlatformError) as caught:
        ps.require_supported_platform(info=info)
    error = caught.value
    assert error.code == "unsupported-platform"
    assert "freebsd13/riscv64" in str(error)
    assert ps.MATRIX_DOC in error.hint
    assert "linux-aarch64" in str(error)
    payload = error.to_dict()
    assert payload["code"] == "unsupported-platform"
    assert payload["hint"]


def test_require_supported_platform_returns_info_for_declared_targets():
    info = ps.require_supported_platform(system="linux", machine="aarch64")
    assert info.platform_id == "linux-aarch64"
    assert info.supported is True
    assert ps.require_supported_platform(info=info) is info


# ---------------------------------------------------------------------------
# Feature table
# ---------------------------------------------------------------------------
def test_feature_table_is_complete_and_evidence_bound():
    assert tuple(item.feature for item in (
        ps.feature_declaration(feature) for feature in ps.FEATURE_AREAS
    )) == ps.FEATURE_AREAS
    assert len(ps.FEATURE_AREAS) == 13
    allowed_levels = {
        ps.LEVEL_VERIFIED, ps.LEVEL_PARTIAL, ps.LEVEL_MANUAL_PENDING,
        ps.LEVEL_UNSUPPORTED,
    }
    for feature in ps.FEATURE_AREAS:
        declaration = ps.feature_declaration(feature)
        assert set(declaration.levels) == set(ps.PLATFORM_IDS)
        assert set(declaration.levels.values()) <= allowed_levels
        assert declaration.manual_pending
        assert declaration.evidence
        assert isinstance(declaration.ci_verifiable, bool)
        for platform_id in ps.PLATFORM_IDS:
            level = declaration.levels[platform_id]
            if platform_id != "windows-x86_64":
                assert level != ps.LEVEL_VERIFIED, (
                    feature + " must not claim verified support on " + platform_id)
        assert declaration.levels["windows-x86_64"] in {
            ps.LEVEL_VERIFIED, ps.LEVEL_PARTIAL}
    verified_on_windows = {
        feature for feature in ps.FEATURE_AREAS
        if ps.feature_level(feature, "windows-x86_64") == ps.LEVEL_VERIFIED
    }
    assert {"gui", "editor", "attachments", "ollama", "crewai",
            "terminal", "git"} <= verified_on_windows
    partial_on_windows = {
        feature for feature in ps.FEATURE_AREAS
        if ps.feature_level(feature, "windows-x86_64") == ps.LEVEL_PARTIAL
    }
    assert {"clipboard", "microphone", "asr_tts", "lsp", "mcp", "gpu"} <= partial_on_windows
    # C1c: feature-level evidence/statements reflect the committed C2-C5 artifacts.
    assert "installer/runtime_manifest.json" in ps.feature_declaration("crewai").evidence
    assert "unverified" in ps.feature_declaration("crewai").manual_pending
    assert "installer/runtime_manifest.json" in ps.feature_declaration("gpu").evidence
    assert "optional" in ps.feature_declaration("gpu").evidence
    assert ":458-576" in ps.feature_declaration("terminal").evidence


def test_feature_helpers_validate_names():
    assert ps.feature_level("gui", "windows-x86_64") == ps.LEVEL_VERIFIED
    assert ps.feature_level("gui", "macos-arm64") == ps.LEVEL_MANUAL_PENDING
    assert ps.feature_declaration("gpu").ci_verifiable is False
    assert ps.feature_declaration("terminal").ci_verifiable is True
    with pytest.raises(ValueError):
        ps.feature_declaration("not-a-feature")
    with pytest.raises(ValueError):
        ps.get_platform_declaration("beos-x86_64")
    with pytest.raises(ValueError):
        ps.feature_level("gui", "beos-x86_64")


def test_support_snapshot_is_json_safe_and_honest():
    snapshot = ps.support_snapshot()
    payload = json.loads(json.dumps(snapshot))
    assert payload == snapshot
    assert len(payload["platforms"]) == 6
    assert len(payload["features"]) == 13
    assert "MANUAL-PENDING" in payload["notes"]
    assert payload["matrix_document"] == ps.MATRIX_DOC


# ---------------------------------------------------------------------------
# Optional backend probes (injected tools; no execution, no network)
# ---------------------------------------------------------------------------
EXPECTED_BACKEND_KEYS = {
    "git", "ollama", "ffmpeg", "piper", "tts:piper-python",
    "asr:faster-whisper", "asr:vosk", "asr:qwen3-asr",
    "audio:qtaudio", "audio:sounddevice", "debugpy",
    "lsp:pylsp", "lsp:pyright", "lsp:basedpyright", "lsp:clangd",
    "lsp:typescript", "lsp:gopls", "tts:local-command", "mcp:stdio",
}


def _fake_probes():
    executables = {
        "git": "/usr/bin/git",
        "ffmpeg": None,
        "ollama": None,
        "piper": None,
        "pylsp": "/opt/pylsp",
        "clangd": None,
        "gopls": None,
        "pyright-langserver": None,
        "basedpyright-langserver": None,
        "typescript-language-server": None,
    }
    modules = {
        "faster_whisper": object(),
        "PySide6.QtMultimedia": object(),
        "vosk": None,
        "qwen3_asr": None,
        "sounddevice": None,
        "piper": None,
        "debugpy": None,
    }
    return (
        lambda name: executables.get(str(name)),
        lambda name: modules.get(str(name)),
    )


def test_optional_backend_probes_are_injected_friendly_and_actionable():
    which, find_spec = _fake_probes()
    probes = ps.probe_optional_backends(which=which, find_spec=find_spec, environ={})
    assert set(probes) == EXPECTED_BACKEND_KEYS
    assert probes["git"]["available"] is True and probes["git"]["code"] == "ok"
    assert probes["ffmpeg"]["available"] is False
    assert probes["ffmpeg"]["code"] == "not-found"
    assert probes["ollama"]["install_hint"]
    assert probes["lsp:pylsp"]["available"] is True
    assert probes["lsp:gopls"]["available"] is False
    assert probes["asr:faster-whisper"]["available"] is True
    assert probes["asr:vosk"]["available"] is False
    assert probes["audio:qtaudio"]["available"] is True
    assert probes["audio:sounddevice"]["available"] is False
    assert probes["tts:local-command"]["available"] is False
    assert probes["tts:local-command"]["code"] == "not-configured"
    assert probes["mcp:stdio"]["available"] is True
    assert probes["mcp:stdio"]["kind"] == "internal"
    for entry in probes.values():
        assert entry["required"] is False
        assert entry["install_hint"]
        assert entry["detail"]


def test_optional_backend_probes_honour_environment_configuration():
    which, find_spec = _fake_probes()
    probes = ps.probe_optional_backends(
        which=which, find_spec=find_spec, environ={"NL_TTS_COMMAND": "/opt/say"})
    assert probes["tts:local-command"]["available"] is True
    assert probes["tts:local-command"]["code"] == "configured"


def test_probe_defaults_do_not_execute_processes_or_network(monkeypatch):
    import subprocess
    import socket

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("optional probe must not execute processes")))
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("optional probe must not open sockets")))
    probes = ps.probe_optional_backends(which=lambda name: None,
                                        find_spec=lambda name: None,
                                        environ={})
    assert probes["git"]["available"] is False
    assert probes["mcp:stdio"]["available"] is True


def test_module_has_no_process_or_network_imports():
    assert getattr(ps, "subprocess", None) is None
    assert getattr(ps, "urllib", None) is None
    assert getattr(ps, "requests", None) is None


def test_require_optional_backend_fails_closed_with_hint():
    unavailable = {
        "ollama": {"name": "ollama", "kind": "executable", "required": False,
                   "available": False, "detail": "not found on PATH",
                   "install_hint": "Install Ollama locally.", "code": "not-found"},
    }
    with pytest.raises(ps.UnsupportedConfigurationError) as caught:
        ps.require_optional_backend("ollama", probes=unavailable)
    error = caught.value
    assert error.code == "backend-unavailable"
    assert "ollama" in str(error)
    assert "Install Ollama locally." in error.hint
    assert error.to_dict()["detail"] == "not found on PATH"

    available = {**unavailable, "ollama": {**unavailable["ollama"],
                                           "available": True, "code": "ok"}}
    assert ps.require_optional_backend("ollama", probes=available)["available"] is True


def test_require_optional_backend_rejects_unknown_names():
    with pytest.raises(ps.UnsupportedConfigurationError) as caught:
        ps.require_optional_backend("not-a-backend", probes={})
    assert caught.value.code == "unknown-backend"
    assert not caught.value.hint == ""


def test_require_optional_backend_accepts_probe_pipeline():
    which, find_spec = _fake_probes()
    probes = ps.probe_optional_backends(which=which, find_spec=find_spec, environ={})
    assert ps.require_optional_backend("git", probes=probes)["available"] is True
    with pytest.raises(ps.UnsupportedConfigurationError):
        ps.require_optional_backend("ffmpeg", probes=probes)


# ---------------------------------------------------------------------------
# Optional GPU telemetry
# ---------------------------------------------------------------------------
def _platform(system="linux", machine="x86_64"):
    return ps.detect_platform(system=system, machine=machine)


def test_gpu_unavailable_is_not_an_error_and_never_required():
    result = ps.probe_gpu(platform=_platform(), which=lambda name: None)
    assert result["status"] == "unavailable"
    assert result["available"] is False
    assert result["required"] is False
    assert result["forced"] is False
    assert result["cuda_required"] is False
    assert result["rocm_required"] is False
    assert result["metal_required"] is False
    assert result["mlx_required"] is False
    assert result["accelerators"] == ["cpu"]
    assert result["memory_used_mb"] is None


def test_gpu_without_runner_reports_detected_not_queried():
    result = ps.probe_gpu(
        platform=_platform("win32", "AMD64"),
        which=lambda name: "/fake/nvidia-smi" if name == "nvidia-smi" else None,
        runner=None,
    )
    assert result["status"] == "detected-not-queried"
    assert result["backend"] == "nvidia"
    assert result["available"] is None


def test_gpu_parses_injected_telemetry():
    captured = []

    def runner(argv):
        captured.append(list(argv))
        return {"returncode": 0, "stdout": "2048, 8192" + chr(10), "stderr": ""}

    result = ps.probe_gpu(
        platform=_platform("win32", "AMD64"),
        which=lambda name: "/fake/nvidia-smi",
        runner=runner,
    )
    assert result["status"] == "available"
    assert result["available"] is True
    assert result["backend"] == "nvidia"
    assert result["memory_used_mb"] == 2048.0
    assert result["memory_total_mb"] == 8192.0
    assert captured and captured[0][0] == "/fake/nvidia-smi"
    assert result["cuda_required"] is False


def test_gpu_probe_failure_is_data_not_a_crash():
    def failing(argv):
        raise OSError("driver missing")

    result = ps.probe_gpu(
        platform=_platform(), which=lambda name: "/fake/nvidia-smi", runner=failing)
    assert result["status"] == "probe-failed"
    assert result["available"] is None
    assert "driver missing" in result["detail"]

    bad_output = ps.probe_gpu(
        platform=_platform(), which=lambda name: "/fake/nvidia-smi",
        runner=lambda argv: {"returncode": 0, "stdout": "garbage", "stderr": ""})
    assert bad_output["status"] == "probe-failed"

    unavailable = ps.probe_gpu(
        platform=_platform(), which=lambda name: "/fake/nvidia-smi",
        runner=lambda argv: {"returncode": 2, "stdout": "", "stderr": "no devices"})
    assert unavailable["status"] == "probe-failed"
    assert "exited 2" in unavailable["detail"]


def test_gpu_amd_candidate_is_probed_only_on_linux():
    seen = []

    def which(name):
        seen.append(name)
        return None

    ps.probe_gpu(platform=_platform("win32", "AMD64"), which=which)
    assert seen == ["nvidia-smi"]
    seen.clear()
    ps.probe_gpu(platform=_platform("linux", "x86_64"), which=which)
    assert seen == ["nvidia-smi", "rocm-smi"]


def test_macos_gpu_is_manual_pending_and_metal_mlx_are_not_required():
    result = ps.probe_gpu(
        platform=_platform("darwin", "arm64"),
        which=lambda name: (_ for _ in ()).throw(
            AssertionError("macOS GPU probe must not execute telemetry")),
    )
    assert result["status"] == "manual-pending"
    assert result["backend"] is None
    assert result["available"] is None
    assert result["accelerators"] == ["apple-metal"]
    assert result["metal_required"] is False
    assert result["mlx_required"] is False
    assert result["forced"] is False


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------
def test_environment_report_is_json_safe_and_marks_hardware_unverified(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("environment report must not open sockets")))
    which, find_spec = _fake_probes()
    report = ps.environment_report(
        system="win32", machine="AMD64", which=which, find_spec=find_spec,
        environ={})
    payload = json.loads(json.dumps(report))
    assert payload == report
    assert report["platform"]["platform_id"] == "windows-x86_64"
    assert report["platform"]["supported"] is True
    assert report["declaration"]["status"] == ps.PLATFORM_STATUS_LOCAL_PARTIAL
    assert set(report["features"]) == set(ps.FEATURE_AREAS)
    assert report["features"]["gui"]["level"] == ps.LEVEL_VERIFIED
    assert report["features"]["gpu"]["level"] == ps.LEVEL_PARTIAL
    assert report["optional_backends"]["git"]["available"] is True
    assert report["gpu"]["status"] == "unavailable"
    assert report["real_hardware_verified"] is False


def test_environment_report_for_unsupported_host_does_not_raise():
    report = ps.environment_report(system="plan9", machine="mips",
                                   which=lambda name: None,
                                   find_spec=lambda name: None, environ={})
    payload = json.loads(json.dumps(report))
    assert payload == report
    assert report["platform"]["supported"] is False
    assert report["declaration"] is None
    assert report["features"] == {}
    assert report["real_hardware_verified"] is False
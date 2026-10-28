"""Stage-2: read-only external tool registry (SPEC-25 / NL-BP-073)."""
from __future__ import annotations

import subprocess
import sys

import pytest

from nl_coding_agent.tools import registry as registry_module
from nl_coding_agent.tools.registry import (
    DEFAULT_OLLAMA_URL,
    PROBE_TIMEOUT_S,
    ExternalTool,
    ToolCapability,
    ToolRegistry,
)

EXPECTED_TOOL_IDS = {"git", "python", "pytest", "ollama", "ffmpeg"}


class FakeCompleted:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return self._payload if size is None or size < 0 else self._payload[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def test_builtin_tools_are_described_with_capabilities_and_platform():
    registry = ToolRegistry()
    assert {tool.tool_id for tool in registry.tools()} == EXPECTED_TOOL_IDS

    git = registry.describe("git")
    assert git["executable"] == "git"
    assert git["platform"] == sys.platform
    assert git["owner"] == "nl_coding_agent"
    assert ToolCapability.READ in git["capabilities"]

    pytest_tool = registry.describe("pytest")
    # Execute capability is distinct from write: probe/discovery never grants write.
    assert pytest_tool["capabilities"] == [ToolCapability.EXECUTE]

    ollama = registry.describe("ollama")
    assert ollama["endpoint"] == DEFAULT_OLLAMA_URL + "/api/tags"
    assert ToolCapability.NETWORK in ollama["capabilities"]

    ffmpeg = registry.describe("ffmpeg")
    assert ffmpeg["probe_argv"] == ["ffmpeg", "-version"]


def test_find_filters_by_query_and_capability():
    registry = ToolRegistry()
    assert [tool.tool_id for tool in registry.find("git")] == ["git"]
    assert [tool.tool_id for tool in registry.find("PYTHON")] == ["python"]
    network = {
        tool.tool_id for tool in registry.find(capability=ToolCapability.NETWORK)
    }
    assert network == {"ollama"}
    assert registry.find("no-such-tool") == []


def test_probe_uses_argv_list_without_shell_and_with_bounded_timeout(monkeypatch):
    calls = []

    monkeypatch.setattr(
        registry_module.shutil,
        "which",
        lambda name: "C:/tools/" + name + ".exe",
    )

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return FakeCompleted(0, b"git version 2.43.0.windows.1\n", b"")

    monkeypatch.setattr(registry_module.subprocess, "run", fake_run)

    registry = ToolRegistry(probe_timeout_s=60)
    assert registry.probe_timeout_s == PROBE_TIMEOUT_S
    result = registry.probe("git")

    assert result["available"] is True
    assert result["version"] == "git version 2.43.0.windows.1"
    assert result["path"] == "C:/tools/git.exe"
    assert calls, "probe must execute the registered version command"
    argv, kwargs = calls[0]
    assert argv == ["C:/tools/git.exe", "--version"]
    assert kwargs["shell"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["timeout"] <= PROBE_TIMEOUT_S
    assert result["duration_s"] >= 0


def test_probe_marks_tool_unavailable_when_executable_is_missing(monkeypatch):
    monkeypatch.setattr(registry_module.shutil, "which", lambda name: None)

    def forbidden(*args, **kwargs):
        raise AssertionError("no process may run when the executable is absent")

    monkeypatch.setattr(registry_module.subprocess, "run", forbidden)

    result = ToolRegistry().probe("ffmpeg")

    assert result["available"] is False
    assert result["path"] is None
    assert "not found" in result["error"]


def test_probe_reports_failed_version_command(monkeypatch):
    monkeypatch.setattr(registry_module.shutil, "which", lambda name: "C:/tools/git.exe")
    monkeypatch.setattr(
        registry_module.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompleted(2, b"", b"fatal: bad option\n"),
    )

    result = ToolRegistry().probe("git")

    assert result["available"] is False
    assert "probe exit 2" in result["error"]


def test_probe_decodes_non_utf8_output_without_crashing(monkeypatch):
    monkeypatch.setattr(registry_module.shutil, "which", lambda name: "C:/tools/git.exe")
    monkeypatch.setattr(
        registry_module.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompleted(0, b"git version 2.43 \xff\n", b""),
    )

    result = ToolRegistry().probe("git")

    assert result["available"] is True
    assert result["version"].startswith("git version 2.43")


def test_ollama_falls_back_to_read_only_http_tags_probe(monkeypatch):
    seen = {}
    monkeypatch.setattr(registry_module.shutil, "which", lambda name: None)

    def fake_urlopen(url, timeout=None):
        seen["url"] = url
        seen["timeout"] = timeout
        return FakeResponse(b'{"models": []}')

    monkeypatch.setattr(registry_module.urllib.request, "urlopen", fake_urlopen)

    result = ToolRegistry(probe_timeout_s=1).probe("ollama")

    assert seen["url"] == DEFAULT_OLLAMA_URL + "/api/tags"
    assert 0 < seen["timeout"] <= PROBE_TIMEOUT_S
    assert result["available"] is True
    assert result["endpoint_reachable"] is True
    assert result["version"] == "http-api"


def test_ollama_http_failure_keeps_tool_unavailable(monkeypatch):
    monkeypatch.setattr(registry_module.shutil, "which", lambda name: None)

    def failing_urlopen(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(registry_module.urllib.request, "urlopen", failing_urlopen)

    result = ToolRegistry().probe("ollama")

    assert result["available"] is False
    assert result["endpoint_reachable"] is False
    assert "connection refused" in result["error"]


def test_custom_tool_probe_only_runs_its_registered_argv(monkeypatch):
    executable = sys.executable
    tool = ExternalTool(
        tool_id="fake-tool",
        display_name="Fake Tool",
        executable=executable,
        probe_argv=(executable, "--version"),
        capabilities=(ToolCapability.EXECUTE,),
    )
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return FakeCompleted(0, b"fake 1.0\n")

    monkeypatch.setattr(registry_module.subprocess, "run", fake_run)
    registry = ToolRegistry([tool], probe_timeout_s=0.5)

    result = registry.probe("fake-tool")

    assert calls == [[executable, "--version"]]
    assert result["available"] is True
    assert registry.probe_timeout_s == 0.5


def test_probe_rejects_unknown_tool_ids_and_exposes_no_command_api():
    registry = ToolRegistry()
    assert not hasattr(registry, "run_command")
    assert not hasattr(registry, "execute")
    with pytest.raises(KeyError):
        registry.probe("sh")
    with pytest.raises(KeyError):
        registry.describe("powershell")


def test_describe_all_can_skip_probes_and_probe_all_covers_every_tool(monkeypatch):
    monkeypatch.setattr(
        ToolRegistry,
        "probe",
        lambda self, tool_id: {"tool_id": tool_id, "available": True},
    )
    registry = ToolRegistry()

    described = registry.describe_all(probe=False)
    assert {item["tool_id"] for item in described} == EXPECTED_TOOL_IDS
    assert all("probe" not in item for item in described)

    probed = registry.describe_all(probe=True)
    assert all(item["probe"]["available"] for item in probed)
    assert {result["tool_id"] for result in registry.probe_all()} == EXPECTED_TOOL_IDS


def test_unknown_capability_and_invalid_descriptor_are_rejected():
    with pytest.raises(ValueError):
        ExternalTool(
            tool_id="bad",
            display_name="Bad",
            executable="bad.exe",
            capabilities=("root",),
        )
    with pytest.raises(ValueError):
        ExternalTool(tool_id="", display_name="Empty", executable="empty.exe")
    with pytest.raises(ValueError):
        ExternalTool(tool_id="x", display_name="X", kind="script", executable="x.exe")


def test_duplicate_tool_ids_are_rejected():
    tool = ExternalTool(tool_id="dup", display_name="Dup", executable="dup.exe")
    with pytest.raises(ValueError):
        ToolRegistry([tool, tool])


def test_app_services_lists_external_tools_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "appdata"))
    from nl_coding_agent.app.services import AppServices

    services = AppServices()
    descriptors = services.list_external_tools(probe=False)

    assert {item["tool_id"] for item in descriptors} == EXPECTED_TOOL_IDS
    assert all("probe" not in item for item in descriptors)
    assert not (tmp_path / "project").exists()


def test_app_services_probe_result_is_attached_without_side_effects(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "appdata"))
    from nl_coding_agent.app.services import AppServices

    monkeypatch.setattr(
        registry_module.ToolRegistry,
        "probe",
        lambda self, tool_id: {"tool_id": tool_id, "available": True},
    )
    services = AppServices()
    descriptors = services.list_external_tools(probe=True)

    assert all(item["probe"]["available"] for item in descriptors)

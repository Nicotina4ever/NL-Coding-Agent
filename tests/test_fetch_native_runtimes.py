"""Stage 6e: native runtime acquisition/measurement tooling (NL-BP-154/156/165).

Fake local archives/opener and one loopback HTTP server only; no external network,
no model runs, no writes outside pytest temp directories.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.fetch_native_runtimes as fetch  # noqa: E402
from installer.platform_targets import SUPPORTED_TARGETS, TARGET_ORDER  # noqa: E402
from installer.runtime_manifest import load_runtime_manifest  # noqa: E402

NL = chr(10)
SHIPPED_SOURCES = REPO_ROOT / "installer" / "runtime_sources.json"
TEMPLATE = REPO_ROOT / "installer" / "runtime_manifest.json"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------
def shipped_sources() -> dict:
    return json.loads(SHIPPED_SOURCES.read_text(encoding="utf-8"))


def write_sources(tmp_path: Path, data: dict | None = None) -> Path:
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(data if data is not None else shipped_sources(), indent=2),
                    encoding="utf-8")
    return path


def zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])
    return buffer.getvalue()


def targz_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in sorted(members):
            data = members[name]
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def archives_for(target_id: str) -> bytes:
    kind = SUPPORTED_TARGETS[target_id]["archive"]
    if kind == "zip":
        return zip_bytes({"python/python.exe": b"MZ fake runtime" + NL.encode(),
                          "python/python312.dll": b"fake dll"})
    return targz_bytes({"python/bin/python3": b"#!/bin/sh" + NL.encode(),
                        "python/lib/python3.12/os.py": b"print('runtime')" + NL.encode()})


def write_offline(tmp_path: Path, sources_path: Path, targets: list[str] | None = None,
                  payloads: dict[str, bytes] | None = None) -> Path:
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    offline = tmp_path / "offline"
    offline.mkdir(exist_ok=True)
    for target_id in (targets or list(TARGET_ORDER)):
        entry = sources["targets"][target_id]
        data = (payloads or {}).get(target_id, archives_for(target_id))
        (offline / entry["filename"]).write_bytes(data)
    return offline


def json_stdout(capsys) -> dict:
    out = capsys.readouterr().out
    return json.loads(out)


@pytest.fixture()
def workspace_env(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    monkeypatch.setenv("NL_WORKSPACE_DIR", str(workspace))
    return workspace


@pytest.fixture()
def no_network(monkeypatch):
    monkeypatch.setattr(fetch.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("dry-run must not open network connections")))
    return None


# ---------------------------------------------------------------------------
# Sources schema
# ---------------------------------------------------------------------------
def test_shipped_sources_template_is_valid_with_six_targets():
    sources = fetch.load_sources(SHIPPED_SOURCES)
    assert list(sources["targets"]) == list(TARGET_ORDER)
    assert sources["schema_version"] == 1
    for target_id in TARGET_ORDER:
        source = sources["targets"][target_id]
        assert source.archive_kind == SUPPORTED_TARGETS[target_id]["archive"]
        assert source.expected_sha256 == ""
        assert source.expected_size == 0
        assert source.filename.endswith(
            ("zip",) if source.archive_kind == "zip" else (".tar.gz", ".tgz"))
        assert source.url.startswith("https://")
    assert sources["status"] == "template"


def test_sources_reject_missing_target():
    data = shipped_sources()
    del data["targets"]["macos-arm64"]
    with pytest.raises(fetch.SourceError):
        fetch.validate_sources(data)


def test_sources_reject_unknown_target():
    data = shipped_sources()
    data["targets"]["plan9-mips"] = dict(data["targets"]["windows-x86_64"])
    with pytest.raises(fetch.SourceError):
        fetch.validate_sources(data)


def test_sources_reject_archive_kind_mismatch():
    data = shipped_sources()
    data["targets"]["windows-x86_64"]["archive_kind"] = "tar.gz"
    with pytest.raises(fetch.SourceError) as caught:
        fetch.validate_sources(data)
    assert caught.value.code == "archive-kind-mismatch"


def test_sources_reject_measured_hash_without_size():
    data = shipped_sources()
    data["targets"]["linux-x86_64"]["expected_sha256"] = "a" * 64
    with pytest.raises(fetch.SourceError) as caught:
        fetch.validate_sources(data)
    assert caught.value.code == "measured-source-requires-size"


def test_sources_reject_size_without_hash():
    data = shipped_sources()
    data["targets"]["linux-x86_64"]["expected_size"] = 123
    with pytest.raises(fetch.SourceError) as caught:
        fetch.validate_sources(data)
    assert caught.value.code == "unmeasured-source-must-not-declare-size"


def test_sources_reject_non_http_url():
    data = shipped_sources()
    data["targets"]["linux-x86_64"]["url"] = "file:///tmp/python.tar.gz"
    with pytest.raises(fetch.SourceError):
        fetch.validate_sources(data)


def test_sources_reject_credentials_in_url():
    data = shipped_sources()
    data["targets"]["linux-x86_64"]["url"] = "https://user:secret@example.invalid/x.tar.gz"
    with pytest.raises(fetch.SourceError) as caught:
        fetch.validate_sources(data)
    assert caught.value.code == "url-credentials"


def test_sources_reject_url_extension_mismatch():
    data = shipped_sources()
    data["targets"]["windows-x86_64"]["filename"] = "runtime.tar.gz"
    with pytest.raises(fetch.SourceError) as caught:
        fetch.validate_sources(data)
    assert caught.value.code == "url-format-mismatch"


# ---------------------------------------------------------------------------
# Dry-run / plan
# ---------------------------------------------------------------------------
def test_dry_run_is_default_and_writes_nothing(tmp_path, workspace_env, no_network):
    code = fetch.main(["--json"])
    assert code == 0
    assert not workspace_env.exists()
    assert list(tmp_path.glob("*.json")) == []
    plan = json.loads(_last_stdout())
    assert plan["dry_run"] is True
    assert plan["counts"] == {"selected": 6, "total": 6}
    assert plan["no_network"] is True and plan["no_writes"] is True


def test_dry_run_plan_lists_all_six_and_never_opens_network(workspace_env, no_network):
    assert fetch.main([]) == 0
    assert fetch.main(["--json"]) == 0
    plan = json.loads(_last_stdout())
    assert [entry["target"] for entry in plan["targets"]] == list(TARGET_ORDER)
    assert all(entry["action"] == "plan-only" for entry in plan["targets"])
    assert not workspace_env.exists()


_CAPTURED: list[str] = []


def _last_stdout() -> str:
    return _CAPTURED[-1]


@pytest.fixture(autouse=True)
def _capture_stdout(monkeypatch, capsys):
    """Capture stdout across subprocess-free main() calls (pytest capsys is per-test)."""
    _CAPTURED.clear()
    import builtins
    real_print = builtins.print

    def capture(*args, sep=" ", end=NL, file=None, **kwargs):
        _CAPTURED.append(sep.join(str(arg) for arg in args) + end)
        real_print(*args, sep=sep, end=end, file=file, **kwargs)

    monkeypatch.setattr(builtins, "print", capture)
    yield
    _CAPTURED.clear()


# ---------------------------------------------------------------------------
# Offline measurement
# ---------------------------------------------------------------------------
def test_offline_measurement_hashes_all_archives(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    offline = write_offline(tmp_path, sources_path)
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--json"])
    assert code == 0
    payload = json.loads(_last_stdout())
    assert [item["target"] for item in payload["measurements"]] == list(TARGET_ORDER)
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    for item in payload["measurements"]:
        path = offline / sources["targets"][item["target"]]["filename"]
        assert item["size"] == path.stat().st_size
        assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert item["measured"] is True
        assert item["expected_match"] is None
    assert payload["written"] is None
    assert not (workspace_env / "build").exists()


def test_offline_expected_hash_is_verified(tmp_path, workspace_env):
    data = shipped_sources()
    sources_path = write_sources(tmp_path, data)
    offline = write_offline(tmp_path, sources_path)
    payload = (offline / data["targets"]["windows-x86_64"]["filename"]).read_bytes()
    data["targets"]["windows-x86_64"]["expected_sha256"] = hashlib.sha256(payload).hexdigest()
    data["targets"]["windows-x86_64"]["expected_size"] = len(payload)
    sources_path = write_sources(tmp_path, data)
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--target", "windows-x86_64", "--json"])
    assert code == 0
    item = json.loads(_last_stdout())["measurements"][0]
    assert item["expected_match"] is True


def test_offline_expected_hash_mismatch_is_refused(tmp_path, workspace_env):
    data = shipped_sources()
    data["targets"]["windows-x86_64"]["expected_sha256"] = "f" * 64
    data["targets"]["windows-x86_64"]["expected_size"] = 1
    sources_path = write_sources(tmp_path, data)
    offline = write_offline(tmp_path, sources_path)
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--target", "windows-x86_64"])
    assert code == fetch.EXIT_FAILURE
    assert "size-mismatch" in _CAPTURED[-1] or "hash-mismatch" in _CAPTURED[-1]


def test_offline_missing_archive_is_refused(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    offline = tmp_path / "offline"
    offline.mkdir()
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--target", "windows-x86_64"])
    assert code == fetch.EXIT_FAILURE
    assert "offline-archive-missing" in _CAPTURED[-1]


def test_archive_format_mismatch_is_refused(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    data = json.loads(sources_path.read_text(encoding="utf-8"))
    offline = tmp_path / "offline"
    offline.mkdir()
    (offline / data["targets"]["windows-x86_64"]["filename"]).write_bytes(
        targz_bytes({"python/bin/python3": b"x"}))
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--target", "windows-x86_64"])
    assert code == fetch.EXIT_FAILURE
    assert "archive-format" in _CAPTURED[-1]


def test_windows_runtime_artifact_rejected_for_linux_target(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    data = json.loads(sources_path.read_text(encoding="utf-8"))
    offline = tmp_path / "offline"
    offline.mkdir()
    (offline / data["targets"]["linux-x86_64"]["filename"]).write_bytes(
        targz_bytes({"python/python.exe": b"MZ windows runtime",
                     "python/python312.dll": b"dll"}))
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--target", "linux-x86_64"])
    assert code == fetch.EXIT_FAILURE
    assert "windows-runtime-on-non-windows" in _CAPTURED[-1]


def test_non_windows_artifact_rejected_for_windows_target(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    data = json.loads(sources_path.read_text(encoding="utf-8"))
    offline = tmp_path / "offline"
    offline.mkdir()
    (offline / data["targets"]["windows-x86_64"]["filename"]).write_bytes(
        zip_bytes({"python/bin/python3": b"#!/bin/sh"}))
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--target", "windows-x86_64"])
    assert code == fetch.EXIT_FAILURE
    assert "non-windows-runtime-on-windows" in _CAPTURED[-1]


def test_host_mismatch_is_recorded_not_fatal(tmp_path, workspace_env, monkeypatch):
    monkeypatch.setattr(fetch, "detect_host_target_safe",
                        lambda: ("linux-x86_64", ""))
    code = fetch.main(["--json"])
    assert code == 0
    plan = json.loads(_last_stdout())
    windows = [entry for entry in plan["targets"] if entry["target"] == "windows-x86_64"][0]
    assert windows["native_host_match"] is False


# ---------------------------------------------------------------------------
# Measured manifest draft + evidence
# ---------------------------------------------------------------------------
def test_measured_draft_generation_all_six(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    offline = write_offline(tmp_path, sources_path)
    template_before = TEMPLATE.read_bytes()
    draft_path = tmp_path / "draft.json"
    evidence_path = tmp_path / "evidence.json"
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--write", "--out", str(draft_path),
                       "--evidence", str(evidence_path)])
    assert code == 0
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    loaded = load_runtime_manifest(draft_path)
    assert loaded["release_ready"] is True
    assert draft["status"] == "release"
    assert draft["generated_by"].startswith("fetch_native_runtimes.py")
    assert TEMPLATE.read_bytes() == template_before
    assert "C:" + chr(92) not in draft_path.read_text(encoding="utf-8")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["summary"] == {"selected": 6, "measured": 6, "unmeasured": 0,
                                   "all_six_measured": True, "release_ready": True}
    assert evidence["support_claim"] is False
    assert "MANUAL-PENDING" in evidence["ci_vs_manual_pending"]
    assert evidence["template_manifest"]["overwritten"] is False
    assert all("C:" + chr(92) not in json.dumps(entry) for entry in evidence["targets"])


def test_partial_measurement_keeps_release_ready_false(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    subset = ["windows-x86_64", "linux-x86_64", "macos-arm64"]
    offline = write_offline(tmp_path, sources_path, targets=subset)
    draft_path = tmp_path / "draft.json"
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--target", "windows-x86_64", "--target", "linux-x86_64",
                       "--target", "macos-arm64", "--write",
                       "--out", str(draft_path)])
    assert code == 0
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["release_ready"] is False
    assert draft["status"] == "draft"
    assert draft["targets"]["windows-x86_64"]["runtime"]["measured"] is True
    for target_id in ("windows-arm64", "linux-aarch64", "macos-x86_64"):
        runtime = draft["targets"][target_id]["runtime"]
        assert runtime["measured"] is False
        assert runtime["sha256"] == ""
        assert runtime["size"] == 0


def test_write_refuses_to_overwrite_tracked_template(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    offline = write_offline(tmp_path, sources_path)
    before = TEMPLATE.read_bytes()
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--write", "--out", str(TEMPLATE)])
    assert code == fetch.EXIT_FAILURE
    assert "refuse-template-overwrite" in _CAPTURED[-1]
    assert TEMPLATE.read_bytes() == before


def test_write_refuses_existing_output_without_force(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    offline = write_offline(tmp_path, sources_path)
    out = tmp_path / "draft.json"
    out.write_text("keep", encoding="utf-8")
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--write", "--out", str(out)])
    assert code == fetch.EXIT_FAILURE
    assert "output-exists" in _CAPTURED[-1]
    assert out.read_text(encoding="utf-8") == "keep"
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--write", "--out", str(out), "--force"])
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["release_ready"] is True


def test_default_write_uses_workspace_build_paths(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    offline = write_offline(tmp_path, sources_path)
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--write"])
    assert code == 0
    expected_draft = workspace_env / "build" / "native-runtimes" / "runtime-manifest.measured.json"
    expected_evidence = workspace_env / "build" / "native-runtimes" / "evidence.json"
    assert expected_draft.is_file()
    assert expected_evidence.is_file()
    assert json.loads(expected_draft.read_text(encoding="utf-8"))["release_ready"] is True


def test_measurement_without_write_writes_nothing(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    offline = write_offline(tmp_path, sources_path)
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline)])
    assert code == 0
    assert not workspace_env.exists()


def test_evidence_redacts_url_query_and_credentials(tmp_path, workspace_env):
    data = shipped_sources()
    data["targets"]["windows-x86_64"]["url"] = (
        "https://downloads.example.invalid/runtime.zip?token=supersecret")
    sources_path = write_sources(tmp_path, data)
    offline = write_offline(tmp_path, sources_path, targets=["windows-x86_64"])
    evidence_path = tmp_path / "evidence.json"
    code = fetch.main(["--sources", str(sources_path), "--offline-dir", str(offline),
                       "--target", "windows-x86_64", "--write",
                       "--out", str(tmp_path / "draft.json"),
                       "--evidence", str(evidence_path)])
    assert code == 0
    text = evidence_path.read_text(encoding="utf-8")
    assert "supersecret" not in text
    evidence = json.loads(text)
    entry = [item for item in evidence["targets"] if item["target"] == "windows-x86_64"][0]
    assert entry["source_url"].endswith("/runtime.zip")
    assert "?" not in entry["source_url"]


# ---------------------------------------------------------------------------
# Download path (injected opener + loopback HTTP server)
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._buffer = io.BytesIO(payload)
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def close(self) -> None:
        return None


def test_download_uses_injected_opener_and_bounds(tmp_path):
    payload = archives_for("linux-x86_64")
    dest = tmp_path / "linux.tar.gz"
    result = fetch.download_archive("https://example.invalid/linux.tar.gz", dest,
                                    opener=lambda url, timeout: _FakeResponse(payload),
                                    timeout=5.0, max_bytes=10_000_000,
                                    target="linux-x86_64")
    assert dest.read_bytes() == payload
    assert result["size"] == len(payload)
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    with pytest.raises(fetch.DownloadError) as caught:
        fetch.download_archive("https://example.invalid/linux.tar.gz",
                               tmp_path / "too-big.tar.gz",
                               opener=lambda url, timeout: _FakeResponse(payload),
                               timeout=5.0, max_bytes=10, target="linux-x86_64")
    assert caught.value.code == "download-too-large"
    with pytest.raises(fetch.DownloadError) as caught:
        fetch.download_archive("https://example.invalid/x.zip", tmp_path / "x.zip",
                               opener=lambda url, timeout: (_ for _ in ()).throw(
                                   OSError("connection refused")),
                               timeout=1.0, target="windows-x86_64")
    assert caught.value.code == "download-open-failed"


def test_download_read_failure_is_a_deterministic_error(tmp_path):
    class _Broken:
        status = 200

        def read(self, size=-1):
            raise TimeoutError("socket timeout")

        def close(self):
            return None

    with pytest.raises(fetch.DownloadError) as caught:
        fetch.download_archive("https://example.invalid/x.zip", tmp_path / "x.zip",
                               opener=lambda url, timeout: _Broken(), timeout=1.0,
                               target="windows-x86_64")
    assert caught.value.code == "download-read-failed"


@pytest.fixture()
def loopback_server(tmp_path):
    payload = archives_for("windows-x86_64")
    (tmp_path / "python-3.12.10-windows-x86_64.zip").write_bytes(payload)

    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_download_mode_with_loopback_http_server(tmp_path, workspace_env, loopback_server):
    base_url, payload = loopback_server
    data = shipped_sources()
    data["targets"]["windows-x86_64"]["url"] = (
        base_url + "/python-3.12.10-windows-x86_64.zip")
    sources_path = write_sources(tmp_path, data)
    code = fetch.main(["--sources", str(sources_path), "--download",
                       "--target", "windows-x86_64", "--json"])
    assert code == 0
    result = json.loads(_last_stdout())["measurements"][0]
    assert result["target"] == "windows-x86_64"
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["mode"] == "download"
    assert (workspace_env / "cache" / "native-runtimes"
            / "python-3.12.10-windows-x86_64.zip").is_file()


# ---------------------------------------------------------------------------
# Validation, selection and static safety guards
# ---------------------------------------------------------------------------
def test_target_aliases_and_unknown_target(tmp_path, workspace_env):
    assert fetch.resolve_selected_targets(["win-x64", "linux-arm64"]) == [
        "windows-x86_64", "linux-aarch64"]
    code = fetch.main(["--target", "not-a-target"])
    assert code == fetch.EXIT_USAGE
    assert "unsupported-target" in _CAPTURED[-1]


def test_mode_conflicts_are_refused(tmp_path, workspace_env):
    sources_path = write_sources(tmp_path)
    offline = write_offline(tmp_path, sources_path)
    for argv in (["--dry-run", "--offline-dir", str(offline)],
                 ["--offline-dir", str(offline), "--download"],
                 ["--write"]):
        code = fetch.main(["--sources", str(sources_path)] + argv)
        assert code == fetch.EXIT_USAGE, argv


def test_static_guards_no_publish_no_network_defaults():
    source = (REPO_ROOT / "scripts" / "fetch_native_runtimes.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "shutil.rmtree", "requests.", "webbrowser",
                      "smtplib", "socket", "git push", "git tag", "upload(",
                      "publish(", "os.system", "os.remove"):
        assert forbidden not in source, "forbidden capability in tool: " + forbidden
    parser = fetch.build_parser()
    args = parser.parse_args([])
    assert args.dry_run is None
    assert args.write is False and args.download is False and args.offline_dir is None
    assert fetch.TEMPLATE_MANIFEST.name == "runtime_manifest.json"
    assert fetch.TARGET_ORDER and len(fetch.TARGET_ORDER) == 6

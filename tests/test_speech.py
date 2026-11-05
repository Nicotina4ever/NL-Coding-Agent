"""F2 speech manager: detection, install refusal, model lifecycle, recording, ASR/TTS."""
from __future__ import annotations

import json
import io
import socket
import wave
import zipfile
from pathlib import Path

import pytest

from nl_coding_agent.app import speech as sp
from nl_coding_agent.persistence import database


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    database.init_db().close()
    return tmp_path


def _caps(**probes):
    return sp.detect_capabilities(
        probes=probes, tts_probes={"piper": False, "local-command": False},
        device_probe_error=None)


class FakeRecorder:
    def __init__(self, path: Path, *, fail_start=False, fail_stop=False):
        self.path = path
        self.fail_start, self.fail_stop = fail_start, fail_stop
        self.seconds = None
        self.stopped = False

    def start(self, max_seconds):
        if self.fail_start:
            raise RuntimeError("device busy")
        self.seconds = max_seconds
        with wave.open(str(self.path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 16000)

    def stop(self):
        if self.fail_stop:
            raise RuntimeError("stop failed")
        self.stopped = True
        return {"wav_path": str(self.path), "duration_s": 1.0}

    def is_recording(self):
        return not self.stopped

    def cancel(self):
        pass


def test_capability_detection_catalog_and_install_refusal():
    caps = _caps(**{"faster-whisper": True, "vosk": False, "qwen3-asr": False})
    manager = sp.SpeechManager(capabilities=caps)
    assert manager.asr_engines()["faster-whisper"] is True
    catalog = manager.catalog()
    assert {row["engine"] for row in catalog["engines"]} == set(sp.DEFAULT_ENGINES)
    assert catalog["cloud_asr"] is False and catalog["telemetry"] is False
    plan = manager.install_plan("vosk")
    assert plan["installable"] is False
    assert plan["requires_human_action"] is True
    assert plan["downloads"] is False
    assert "human action" in plan["refusal"]
    with pytest.raises(sp.SpeechError) as caught:
        manager.install_plan("nope")
    assert caught.value.code == "unknown-engine"


def test_local_model_discovery_switch_persist_and_unload(tmp_path):
    model_dir = tmp_path / "whisper-small"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"x" * 2048)
    manager = sp.SpeechManager(
        capabilities=_caps(**{"faster-whisper": True}),
        model_dirs=[str(tmp_path)])
    models = manager.discover_models()
    assert [m.model_id for m in models] == ["whisper-small"]
    assert models[0].engine == "faster-whisper"
    assert manager.active_model() is None
    selected = manager.switch_model("whisper-small")
    assert selected["model_id"] == "whisper-small"
    reopened = sp.SpeechManager(
        capabilities=_caps(**{"faster-whisper": True}), model_dirs=[str(tmp_path)])
    assert reopened.active_model()["model_id"] == "whisper-small"
    assert reopened.unload_model()["unloaded"] is True
    assert reopened.active_model() is None
    with pytest.raises(sp.SpeechError) as caught:
        manager.switch_model("missing-model")
    assert caught.value.code == "model-not-local"


def test_model_selection_uses_engine_when_model_ids_collide(tmp_path):
    faster_root = tmp_path / "faster-whisper"
    vosk_root = tmp_path / "vosk"
    faster_model = faster_root / "shared"
    vosk_model = vosk_root / "shared"
    faster_model.mkdir(parents=True)
    (faster_model / "model.bin").write_bytes(b"faster")
    (vosk_model / "am").mkdir(parents=True)
    (vosk_model / "am" / "final.mdl").write_bytes(b"vosk")
    manager = sp.SpeechManager(
        capabilities=_caps(**{"faster-whisper": True, "vosk": True}),
        model_dirs=[str(faster_root), str(vosk_root)])

    selected = manager.switch_model("shared", engine="vosk")
    assert selected["engine"] == "vosk"
    assert selected["path"] == str(vosk_model)
    with pytest.raises(sp.SpeechError) as caught:
        manager.switch_model("shared", engine="whisper.cpp")
    assert caught.value.code == "model-not-local"


def test_curated_model_download_is_explicit_scoped_and_safe(tmp_path, monkeypatch):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("vosk-model-small-it-0.22/am/final.mdl", b"model")
        archive.writestr("vosk-model-small-it-0.22/conf/model.conf", "sample-rate=16000")
    archive_bytes = payload.getvalue()

    class Response:
        def __init__(self):
            self.stream = io.BytesIO(archive_bytes)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def read(self, size):
            return self.stream.read(size)

    monkeypatch.setattr(sp.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    manager = sp.SpeechManager(capabilities=_caps(vosk=True))
    selected = manager.download_model("vosk-model-small-it-0.22")

    assert selected["engine"] == "vosk"
    assert Path(selected["path"]).is_relative_to(Path(isolated_root := database.data_root()) / "speech" / "models")
    assert (Path(selected["path"]) / "am" / "final.mdl").read_bytes() == b"model"
    assert any(item.model_id == "vosk-model-small-it-0.22" for item in manager.discover_models())
    with pytest.raises(sp.SpeechError) as caught:
        manager.download_model("not-in-curated-catalog")
    assert caught.value.code == "unknown-model-download"


def test_faster_whisper_download_uses_curated_snapshot_in_managed_root(monkeypatch):
    calls = []

    def fake_snapshot_download(*, repo_id, local_dir, **kwargs):
        calls.append((repo_id, kwargs.get("allow_patterns")))
        target = Path(local_dir)
        target.mkdir(parents=True)
        (target / "config.json").write_text("{}", encoding="utf-8")
        (target / "model.bin").write_bytes(b"model")
        (target / "tokenizer.json").write_text("{}", encoding="utf-8")
        return str(target)

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download)
    manager = sp.SpeechManager(
        capabilities=_caps(**{"faster-whisper": True, "vosk": False}))
    model = manager.download_model("faster-whisper-tiny")

    assert calls[0][0] == "Systran/faster-whisper-tiny"
    assert "model.bin" in calls[0][1]
    assert Path(model["path"]).is_relative_to(Path(isolated_root := database.data_root()) / "speech" / "models")
    assert model["engine"] == "faster-whisper"


def test_asr_download_rejects_archive_path_traversal(tmp_path, monkeypatch):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escape.txt", "outside")
    archive_bytes = payload.getvalue()

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            nonlocal archive_bytes
            data, archive_bytes = archive_bytes[:size], archive_bytes[size:]
            return data

    monkeypatch.setattr(sp.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    manager = sp.SpeechManager(capabilities=_caps(vosk=True))
    with pytest.raises(sp.SpeechError) as caught:
        manager.download_model("vosk-model-small-it-0.22")
    assert caught.value.code == "archive-path-invalid"


def test_speech_download_requires_project_network_permission(tmp_path):
    from nl_coding_agent.app.services import AppServices
    from nl_coding_agent.core import permissions

    root = tmp_path / "project"
    root.mkdir()
    services = AppServices()
    project = services.open_project(root)
    services.speech_manager = lambda: type("Manager", (), {
        "download_model": staticmethod(lambda model_id: {"model_id": model_id})
    })()
    try:
        with pytest.raises(permissions.PermissionDenied):
            services.speech_download_model(project["id"], "vosk-model-small-it-0.22")
        permissions.set_access_mode("auto-review")
        assert services.speech_download_model(
            project["id"], "vosk-model-small-it-0.22")["model_id"] == "vosk-model-small-it-0.22"
    finally:
        services._db.close()


def test_qwen_forced_aligner_is_not_offered_as_asr(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "qwen3-asr-1.7b-q8_0.gguf").write_bytes(b"asr")
    (models / "qwen3-forced-aligner-0.6b-q4_k_m.gguf").write_bytes(b"aligner")
    manager = sp.SpeechManager(capabilities=_caps(**{"qwen3-asr": True}),
                               model_dirs=[str(models)])
    assert [item.model_id for item in manager.discover_models()] == ["qwen3-asr-1.7b-q8_0.gguf"]


def test_external_whisper_cpp_folder_is_discovered_and_transcribes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import subprocess

    external = tmp_path / "whisper.cpp"
    (external / "bin").mkdir(parents=True)
    cli = external / "bin" / "whisper-cli.exe"
    cli.write_bytes(b"external cli")
    model_dir = external / "models"
    model_dir.mkdir()
    model = model_dir / "ggml-tiny.bin"
    model.write_bytes(b"model")
    manager = sp.SpeechManager(capabilities=_caps(**{"whisper.cpp": True}))

    registered = manager.set_external_home(str(external))
    assert registered["whisper_cpp_cli"] == str(cli.resolve())
    selected = manager.switch_model("ggml-tiny")
    assert selected["engine"] == "whisper.cpp"

    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF")
    def fake_run(command, **kwargs):
        output_prefix = Path(command[command.index("-of") + 1])
        output_prefix.with_suffix(".txt").write_text("hello from whisper", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    transcript = manager.transcribe(wav)
    assert transcript["text"] == "hello from whisper"
    assert transcript["engine"] == "whisper.cpp"


def test_external_vosk_model_folder_is_added_in_place_and_persisted(tmp_path):
    external = tmp_path / "external-vosk"
    (external / "am").mkdir(parents=True)
    (external / "am" / "final.mdl").write_bytes(b"model")
    manager = sp.SpeechManager(capabilities=_caps(vosk=True))

    registered = manager.set_external_home(str(external))
    assert registered["external_home"] == str(external.resolve())
    assert [item["model_id"] for item in registered["models"]] == ["external-vosk"]
    selected = manager.switch_model("external-vosk")
    assert selected["engine"] == "vosk"
    assert selected["path"] == str(external.resolve())

    reopened = sp.SpeechManager(capabilities=_caps(vosk=True))
    assert any(item.model_id == "external-vosk" for item in reopened.discover_models())
    assert reopened.active_model()["model_id"] == "external-vosk"


def test_external_model_folder_without_supported_asr_model_is_rejected(tmp_path):
    external = tmp_path / "empty"
    external.mkdir()
    manager = sp.SpeechManager(capabilities=_caps(vosk=True))
    with pytest.raises(sp.SpeechError) as caught:
        manager.set_external_home(str(external))
    assert caught.value.code == "external-folder-invalid"


def test_cloud_asr_requires_explicit_permission(monkeypatch, tmp_path):
    manager = sp.SpeechManager(capabilities=_caps(), transcriber=lambda path, meta: {"text": "x"})
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(manager, "active_model", lambda: {
        "model_id": "gpt-oss:120b-cloud", "engine": "cloud", "path": ""})
    from nl_coding_agent.core import permissions
    with pytest.raises(permissions.PermissionDenied):
        manager.transcribe(wav)


def test_audio_devices_graceful_and_no_hardware_required():
    caps = sp.detect_capabilities(probes={"qtaudio": False, "sounddevice": False},
                                  tts_probes={"piper": False, "local-command": False})
    manager = sp.SpeechManager(capabilities=caps)
    result = manager.list_input_devices()
    assert result["devices"] == []
    assert result["error_code"] == "audio-unavailable"
    assert "No local audio capture backend" in result["message"]
    probe_error = sp.SpeechManager(capabilities=sp.SpeechCapabilities(
        audio_backends={}, device_probe_error="permission denied"))
    assert probe_error.list_input_devices()["error_code"] == "audio-unavailable"
    assert probe_error.start_recording is not None
    with pytest.raises(sp.SpeechError) as caught:
        probe_error.start_recording()
    assert caught.value.code == "audio-unavailable"


def test_recording_bounded_fail_closed_and_wav_staging(tmp_path):
    wav = tmp_path / "rec.wav"
    recorder = FakeRecorder(wav)
    manager = sp.SpeechManager(capabilities=_caps(qtaudio=True, sounddevice=False),
                               recorder_factory=lambda: recorder)
    session = manager.start_recording(max_seconds=9999)
    assert session["max_seconds"] == sp.DEFAULT_MAX_RECORDING_SECONDS
    stopped = manager.stop_recording(session["session_id"])
    assert Path(stopped["wav_path"]).is_file()
    with pytest.raises(sp.SpeechError) as caught:
        manager.stop_recording(session["session_id"])
    assert caught.value.code == "recording-not-found"

    failing = sp.SpeechManager(capabilities=_caps(qtaudio=True),
                               recorder_factory=lambda: FakeRecorder(wav, fail_start=True))
    with pytest.raises(sp.SpeechError) as start_error:
        failing.start_recording()
    assert start_error.value.code == "audio-device-unavailable"

    broken = sp.SpeechManager(capabilities=_caps(qtaudio=True),
                              recorder_factory=lambda: FakeRecorder(wav, fail_stop=True))
    broken_session = broken.start_recording()
    with pytest.raises(sp.SpeechError) as stop_error:
        broken.stop_recording(broken_session["session_id"])
    assert stop_error.value.code == "recording-failed"


def test_transcription_injected_or_fail_closed(tmp_path):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF")
    manager = sp.SpeechManager(
        capabilities=_caps(),
        transcriber=lambda path, meta: {"text": "hello mission", "segments": [{"text": "hello mission"}]})
    transcript = manager.transcribe(wav)
    assert transcript["text"] == "hello mission"
    assert transcript["editable"] is True
    unavailable = sp.SpeechManager(capabilities=_caps())
    with pytest.raises(sp.SpeechError) as caught:
        unavailable.transcribe(wav)
    assert caught.value.code == "asr-unavailable"
    with pytest.raises(sp.SpeechError) as missing:
        manager.transcribe(tmp_path / "missing.wav")
    assert missing.value.code == "audio-not-found"


def test_tts_availability_install_plan_and_injected_speak(tmp_path):
    disabled = sp.SpeechManager(capabilities=sp.detect_capabilities(
        probes={"qtaudio": False}, tts_probes={"piper": False, "local-command": False}))
    assert disabled.tts_status()["available"] is False
    plan = disabled.tts_install_plan()
    assert plan["installable"] is False and plan["downloads"] is False
    with pytest.raises(sp.SpeechError) as caught:
        disabled.speak("hello")
    assert caught.value.code == "tts-unavailable"

    target = tmp_path / "tts.wav"
    calls = []
    speaking = sp.SpeechManager(
        capabilities=sp.detect_capabilities(tts_probes={"local-command": True}),
        tts_runner=lambda text, path: calls.append((text, path)) or {"wav_path": str(path)})
    result = speaking.speak("hello", output_path=target)
    assert result["spoken"] is True and calls[0][0] == "hello"
    assert speaking.unload_tts()["unloaded"] is True


def test_speech_operations_do_not_use_network(monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("speech management must not use the network")
    monkeypatch.setattr(socket, "socket", _no_network)
    manager = sp.SpeechManager(capabilities=_caps(),
                               transcriber=lambda path, meta: {"text": "ok"})
    caps = sp.detect_capabilities(probes={}, tts_probes={})
    assert caps.engines

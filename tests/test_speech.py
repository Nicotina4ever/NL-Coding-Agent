"""F2 speech manager: detection, install refusal, model lifecycle, recording, ASR/TTS."""
from __future__ import annotations

import json
import socket
import wave
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

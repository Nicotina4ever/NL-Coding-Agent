"""F2: local-first speech manager (ASR/TTS/audio devices/recording).

Read-only capability detection and explicit-human-action lifecycle. No network
downloads, no cloud ASR/TTS without the permission gate, no telemetry. Missing local
engines/models/hardware fail closed with deterministic error codes and clear messages.
Tests inject fake probes/recorders/transcribers; real microphone/ASR/TTS hardware
verification remains manual.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from nl_coding_agent.persistence import database

__all__ = [
    "SpeechError", "SpeechCapabilities", "SpeechModel", "RecordingSession",
    "SpeechManager", "AudioRecorder", "detect_capabilities",
    "DEFAULT_ENGINES", "DEFAULT_MAX_RECORDING_SECONDS",
]

DEFAULT_ENGINES = ("faster-whisper", "vosk", "qwen3-asr")
DEFAULT_MAX_RECORDING_SECONDS = 120
ASR_INSTALL_HINTS = {
    "faster-whisper": "pip install faster-whisper (human action) + a local CTranslate2 model dir",
    "vosk": "pip install vosk (human action) + a local Vosk model dir",
    "qwen3-asr": "configure a local qwen3-asr package/model directory (human action)",
}


class SpeechError(RuntimeError):
    """Deterministic speech failure; code is stable for UI/CLI handling."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class SpeechModel:
    model_id: str
    engine: str
    path: str
    size_mb: float = 0.0
    status: str = "available"

    def to_dict(self) -> dict:
        return {"model_id": self.model_id, "engine": self.engine,
                "path": self.path, "size_mb": round(self.size_mb, 2),
                "status": self.status}


@dataclass
class SpeechCapabilities:
    engines: dict = field(default_factory=dict)
    local_model_dirs: list = field(default_factory=list)
    audio_backends: dict = field(default_factory=dict)
    tts_backends: dict = field(default_factory=dict)
    device_probe_error: str | None = None

    def to_dict(self) -> dict:
        return {"engines": dict(self.engines),
                "local_model_dirs": list(self.local_model_dirs),
                "audio_backends": dict(self.audio_backends),
                "tts_backends": dict(self.tts_backends),
                "device_probe_error": self.device_probe_error}


@dataclass
class RecordingSession:
    session_id: str
    max_seconds: int
    backend: str
    started_at: str
    recorder: Any = None


@runtime_checkable
class AudioRecorder(Protocol):
    def start(self, max_seconds: int) -> None: ...
    def stop(self) -> dict: ...
    def is_recording(self) -> bool: ...
    def cancel(self) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _env_model_dirs() -> list[Path]:
    raw = os.environ.get("NL_SPEECH_MODEL_DIRS", "")
    dirs = []
    for item in raw.replace(";", os.pathsep).split(os.pathsep):
        text = item.strip()
        if text:
            dirs.append(Path(text).expanduser())
    return dirs


def _default_model_root() -> Path:
    return database.data_root() / "speech" / "models"


def _recordings_root() -> Path:
    return database.data_root() / "speech" / "recordings"


def detect_capabilities(*, probes: dict | None = None,
                        tts_probes: dict | None = None,
                        device_probe_error: str | None = None) -> SpeechCapabilities:
    probes = dict(probes or {})
    engines = {
        engine: bool(probes.get(engine, _importable(engine.replace("-", "_"))))
        for engine in DEFAULT_ENGINES
    }
    local_dirs = [str(_default_model_root()), *[str(path) for path in _env_model_dirs()]]
    audio = {
        "qtaudio": bool(probes.get("qtaudio", _importable("PySide6.QtMultimedia"))),
        "sounddevice": bool(probes.get("sounddevice", _importable("sounddevice"))),
    }
    tts_probes = dict(tts_probes or {})
    command = os.environ.get("NL_TTS_COMMAND", "").strip()
    tts = {
        "piper": bool(tts_probes.get("piper", shutil.which("piper") is not None)),
        "local-command": bool(tts_probes.get("local-command", bool(command))),
        "piper-python": bool(tts_probes.get("piper-python", _importable("piper"))),
    }
    return SpeechCapabilities(engines=engines, local_model_dirs=local_dirs,
                              audio_backends=audio, tts_backends=tts,
                              device_probe_error=device_probe_error)


def _is_model_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    markers = ("model.bin", "config.json", "*.gguf", "*.onnx", "am")
    for marker in markers:
        if marker.startswith("*"):
            if list(path.glob(marker)):
                return True
        elif (path / marker).exists():
            return True
    return any(child.is_dir() for child in path.iterdir()) if path.is_dir() else False


class SpeechManager:
    """ASR/TTS lifecycle + recording for the mission chat (local-only by default)."""

    SETTING_MODEL = "speech.asr_model"
    SETTING_TTS = "speech.tts_backend"

    def __init__(self, *, capabilities: SpeechCapabilities | None = None,
                 recorder_factory: Callable[[], AudioRecorder] | None = None,
                 transcriber: Callable[[str, dict], dict] | None = None,
                 tts_runner: Callable[[str, Path], dict] | None = None,
                 model_dirs: list[str] | None = None,
                 project_id: int | None = None) -> None:
        self.capabilities = capabilities or detect_capabilities()
        self._recorder_factory = recorder_factory
        self._transcriber = transcriber
        self._tts_runner = tts_runner
        self._model_dirs = [Path(item).expanduser() for item in (model_dirs or self.capabilities.local_model_dirs)]
        self.project_id = int(project_id) if project_id is not None else None
        self._sessions: dict[str, RecordingSession] = {}

    # ------------------------------------------------------------------ status
    def asr_engines(self) -> dict:
        return dict(self.capabilities.engines)

    def audio_backend(self) -> str | None:
        if self.capabilities.audio_backends.get("qtaudio"):
            return "qtaudio"
        if self.capabilities.audio_backends.get("sounddevice"):
            return "sounddevice"
        return None

    def discover_models(self) -> list[SpeechModel]:
        models: list[SpeechModel] = []
        seen = set()
        for root in self._model_dirs:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if not child.is_dir() or str(child) in seen:
                    continue
                if not _is_model_dir(child):
                    continue
                seen.add(str(child))
                engine = (
                    "faster-whisper" if (child / "model.bin").exists()
                    else "vosk" if (child / "am").exists()
                    else "qwen3-asr"
                )
                size_mb = 0.0
                try:
                    size_mb = sum(item.stat().st_size for item in child.rglob("*")
                                  if item.is_file()) / (1024 * 1024)
                except OSError:
                    pass
                models.append(SpeechModel(child.name, engine, str(child), size_mb))
        return models

    def catalog(self) -> dict:
        engine_rows = []
        for engine in DEFAULT_ENGINES:
            engine_rows.append({
                "engine": engine,
                "installed": bool(self.capabilities.engines.get(engine)),
                "installable": False,
                "requires_human_action": True,
                "hint": ASR_INSTALL_HINTS.get(engine, ""),
            })
        return {"engines": engine_rows, "models": [m.to_dict() for m in self.discover_models()],
                "active_model": self.active_model(),
                "audio_backend": self.audio_backend(),
                "audio_available": self.audio_backend() is not None,
                "cloud_asr": False, "telemetry": False}

    def install_plan(self, engine: str) -> dict:
        engine = str(engine or "").strip()
        if engine not in DEFAULT_ENGINES:
            raise SpeechError("unknown-engine", "Unknown speech engine: " + repr(engine))
        return {
            "engine": engine, "installable": False, "requires_human_action": True,
            "downloads": False,
            "steps": [
                "Review the upstream license and local model disk/VRAM requirements.",
                "Install the Python package or provide a local model dir yourself (human action).",
                "Point NL_SPEECH_MODEL_DIRS at the local model and restart.",
                "Select the model in Settings / mission chat voice controls.",
            ],
            "hint": ASR_INSTALL_HINTS.get(engine, ""),
            "refusal": "Automatic installation/download is never performed by the app: "
                       "installation requires explicit human action.",
        }

    # -------------------------------------------------------------- model state
    def active_model(self) -> dict | None:
        raw = database.get_json_setting(self.SETTING_MODEL, {})
        if not raw:
            return None
        model_id = str(raw.get("model_id") or "")
        for model in self.discover_models():
            if model.model_id == model_id and model.path == str(raw.get("path")):
                return model.to_dict()
        return None

    def switch_model(self, model_id: str) -> dict:
        wanted = str(model_id or "").strip()
        match = next((m for m in self.discover_models() if m.model_id == wanted), None)
        if match is None:
            raise SpeechError("model-not-local",
                              "Speech model " + repr(wanted) + " is not a discovered local model.")
        engine_available = bool(self.capabilities.engines.get(match.engine))
        if not engine_available and self._transcriber is None:
            raise SpeechError("asr-unavailable",
                              "ASR engine " + match.engine + " is not installed; local model exists but "
                              "cannot be loaded (human installation required).")
        database.set_json_setting(self.SETTING_MODEL, {
            "model_id": match.model_id, "engine": match.engine, "path": match.path,
            "selected_at": _now(),
        })
        return match.to_dict()

    def unload_model(self) -> dict:
        database.set_json_setting(self.SETTING_MODEL, {})
        return {"unloaded": True, "active_model": None}

    # ------------------------------------------------------------------ devices
    def list_input_devices(self) -> dict:
        if self.capabilities.device_probe_error:
            return {"devices": [], "backend": None,
                    "error_code": "audio-unavailable",
                    "message": self.capabilities.device_probe_error}
        backend = self.audio_backend()
        if backend is None:
            return {"devices": [], "backend": None,
                    "error_code": "audio-unavailable",
                    "message": "No local audio capture backend (QtMultimedia or sounddevice) is available."}
        devices: list[dict] = []
        try:
            if backend == "qtaudio":
                from PySide6.QtMultimedia import QMediaDevices
                for device in QMediaDevices.audioInputs():
                    devices.append({"name": device.description(),
                                    "backend": "qtaudio", "default": False})
            else:
                import sounddevice as sd
                for index, item in enumerate(sd.query_devices()):
                    if int(item.get("max_input_channels") or 0) > 0:
                        devices.append({"name": str(item.get("name") or index),
                                        "backend": "sounddevice", "default": False})
        except Exception as exc:  # noqa: BLE001 - graceful read-only failure
            return {"devices": [], "backend": backend,
                    "error_code": "audio-unavailable",
                    "message": "Audio device probe failed: " + str(exc)}
        if devices:
            devices[0]["default"] = True
        return {"devices": devices, "backend": backend, "error_code": None,
                "message": "" if devices else "No microphone/input device detected."}

    # ---------------------------------------------------------------- recording
    def start_recording(self, *, max_seconds: int = 60) -> dict:
        backend = self.audio_backend()
        if self._recorder_factory is None and backend is None:
            raise SpeechError("audio-unavailable",
                              "No local audio capture backend; microphone recording is unavailable.")
        bounded = max(1, min(int(max_seconds), DEFAULT_MAX_RECORDING_SECONDS))
        recorder = (self._recorder_factory()
                    if self._recorder_factory is not None else _QtAudioRecorder())
        try:
            recorder.start(bounded)
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed with a clear code
            raise SpeechError("audio-device-unavailable",
                              "Could not start microphone recording: " + str(exc)) from exc
        import uuid
        session = RecordingSession(uuid.uuid4().hex, bounded, backend or "injected",
                                   _now(), recorder)
        self._sessions[session.session_id] = session
        return {"session_id": session.session_id, "max_seconds": bounded,
                "backend": session.backend, "started_at": session.started_at}

    def stop_recording(self, session_id: str) -> dict:
        session = self._sessions.pop(str(session_id), None)
        if session is None:
            raise SpeechError("recording-not-found", "Recording session not found.")
        try:
            result = session.recorder.stop() or {}
        except Exception as exc:  # noqa: BLE001
            raise SpeechError("recording-failed", "Recording failed: " + str(exc)) from exc
        wav_path = str(result.get("wav_path") or "")
        if not wav_path or not Path(wav_path).is_file():
            raise SpeechError("recording-failed", "No WAV recording was produced.")
        return {"wav_path": wav_path,
                "duration_s": float(result.get("duration_s") or 0.0),
                "max_seconds": session.max_seconds,
                "backend": session.backend}

    def cancel_recording(self, session_id: str) -> dict:
        session = self._sessions.pop(str(session_id), None)
        if session is not None:
            try:
                session.recorder.cancel()
            except Exception:
                pass
        return {"cancelled": session is not None}

    # ------------------------------------------------------------ transcription
    def transcribe(self, wav_path: str | Path, *, language: str | None = None,
                   max_chars: int = 50_000) -> dict:
        path = Path(wav_path).expanduser()
        if not path.is_file():
            raise SpeechError("audio-not-found", "Recording file not found: " + str(path))
        active = self.active_model()
        if active is None and self._transcriber is None:
            raise SpeechError("asr-unavailable",
                              "No local ASR model is selected and no ASR engine is available.")
        model_name = str((active or {}).get("model_id") or "injected-transcriber")
        # Local-first policy: a cloud model name must pass the explicit cloud grant.
        try:
            from nl_coding_agent.core.permissions import is_cloud_model
            if is_cloud_model(model_name):
                from nl_coding_agent.core import permissions
                permissions.assert_model_permitted(model_name, "", self.project_id)
        except Exception:
            raise
        if self._transcriber is not None:
            result = self._transcriber(str(path), {"language": language, "model": model_name})
        else:
            result = self._run_local_asr(str(path), active or {}, language=language)
        text = str(result.get("text") or "")
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [transcript truncated]"
        return {"text": text, "editable": True,
                "engine": str((active or {}).get("engine") or "injected"),
                "model": model_name,
                "segments": list(result.get("segments") or []),
                "duration_s": result.get("duration_s"),
                "language": result.get("language")}

    def _run_local_asr(self, path: str, active: dict, *, language=None) -> dict:
        engine = str(active.get("engine") or "")
        model_path = str(active.get("path") or "")
        if engine == "faster-whisper":
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SpeechError("asr-unavailable",
                                  "faster-whisper is not installed (local install required).") from exc
            model = WhisperModel(model_path, device="cpu", compute_type="int8")
            segments, _info = model.transcribe(path, language=language)
            rows = [{"start": seg.start, "end": seg.end, "text": seg.text} for seg in segments]
            return {"text": " ".join(row["text"].strip() for row in rows),
                    "segments": rows}
        raise SpeechError("asr-unavailable",
                          "No local ASR adapter for engine " + repr(engine)
                          + "; install/configure it explicitly.")

    # -------------------------------------------------------------------- TTS
    def tts_status(self) -> dict:
        available = any(self.capabilities.tts_backends.values())
        return {"available": available, "backends": dict(self.capabilities.tts_backends),
                "cloud": False, "telemetry": False,
                "message": "" if available else
                "No local TTS backend detected (Piper/local command). TTS is unavailable; "
                "nothing was downloaded."}

    def tts_install_plan(self) -> dict:
        return {"installable": False, "requires_human_action": True, "downloads": False,
                "steps": ["Install a local TTS engine such as Piper yourself (human action).",
                          "Set NL_TTS_COMMAND to the local command, or install the piper package.",
                          "Restart the app and select the TTS toggle in mission chat."],
                "refusal": "Automatic installation/download is never performed by the app."}

    def speak(self, text: str, *, output_path: str | Path | None = None) -> dict:
        content = str(text or "").strip()
        if not content:
            raise SpeechError("tts-empty", "Nothing to speak.")
        status = self.tts_status()
        if not status["available"] and self._tts_runner is None:
            raise SpeechError("tts-unavailable",
                              "No local TTS backend is available; TTS was not started.")
        target = Path(output_path) if output_path else _recordings_root() / (
            "tts-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + ".wav")
        target.parent.mkdir(parents=True, exist_ok=True)
        if self._tts_runner is not None:
            result = self._tts_runner(content, target) or {}
        else:
            command = os.environ.get("NL_TTS_COMMAND", "").strip()
            if not command:
                raise SpeechError("tts-unavailable",
                                  "No NL_TTS_COMMAND configured for local TTS.")
            import subprocess
            try:
                subprocess.run([command, str(target)], input=content, text=True,
                               capture_output=True, timeout=60, check=True)
            except Exception as exc:  # noqa: BLE001
                raise SpeechError("tts-failed", "Local TTS command failed: " + str(exc)) from exc
            result = {"wav_path": str(target)}
        return {"spoken": True, "wav_path": str(result.get("wav_path") or target),
                "backend": "local-command" if self._tts_runner is None else "injected"}

    def unload_tts(self) -> dict:
        database.set_json_setting(self.SETTING_TTS, {})
        return {"unloaded": True}


class _QtAudioRecorder:
    """QAudioSource WAV recorder (optional runtime path; not exercised by unit tests)."""

    def __init__(self) -> None:
        self._source = None
        self._buffer = None
        self._wav = None
        self._path = None
        self._timer = None
        self._started = None

    def start(self, max_seconds: int) -> None:
        from PySide6.QtCore import QTimer  # noqa: F401 - availability check
        from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

        device = QMediaDevices.defaultAudioInput()
        if device is None or device.isNull():
            raise SpeechError("audio-device-unavailable", "No default microphone input device.")
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._path = _recordings_root() / (
            "rec-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".wav")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._wav = wave.open(str(self._path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(16000)
        self._source = QAudioSource(device, fmt)
        self._buffer = self._source.start()
        self._started = _now()
        self._frames = 0
        if self._buffer is not None:
            self._buffer.readyRead.connect(self._drain)

    def _drain(self) -> None:
        if self._buffer is None or self._wav is None:
            return
        data = self._buffer.readAll().data()
        if data:
            self._wav.writeframes(data)

    def is_recording(self) -> bool:
        return self._source is not None

    def stop(self) -> dict:
        if self._source is not None:
            self._source.stop()
            self._source = None
        if self._wav is not None:
            self._wav.close()
            self._wav = None
        duration = 0.0
        if self._path is not None and self._path.is_file():
            try:
                with wave.open(str(self._path), "rb") as handle:
                    duration = handle.getnframes() / max(1, handle.getframerate())
            except Exception:
                pass
        return {"wav_path": str(self._path or ""), "duration_s": duration}

    def cancel(self) -> None:
        self.stop()
        if self._path is not None:
            try:
                Path(self._path).unlink()
            except OSError:
                pass

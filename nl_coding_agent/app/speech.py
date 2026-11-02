"""F2: local-first speech manager (ASR/TTS/audio devices/recording).

Read-only capability detection and explicit-human-action lifecycle. No network
downloads, no cloud ASR/TTS without the permission gate, no telemetry. Missing local
engines/models/hardware fail closed with deterministic error codes and clear messages.
Tests inject fake probes/recorders/transcribers; real microphone/ASR/TTS hardware
verification remains manual.
"""
from __future__ import annotations

import importlib.util
import audioop
import json
import os
import time
import shutil
import stat
import tempfile
import urllib.request
import wave
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Protocol, runtime_checkable

from nl_coding_agent.persistence import database

__all__ = [
    "SpeechError", "SpeechCapabilities", "SpeechModel", "RecordingSession",
    "SpeechManager", "AudioRecorder", "detect_capabilities",
    "DEFAULT_ENGINES", "DEFAULT_MAX_RECORDING_SECONDS",
]

DEFAULT_ENGINES = ("faster-whisper", "vosk", "qwen3-asr", "whisper.cpp")
DEFAULT_MAX_RECORDING_SECONDS = 120
ASR_INSTALL_HINTS = {
    "faster-whisper": "optional Python package and a local CTranslate2 Whisper model.",
    "vosk": "lightweight offline Vosk model; used by NL Code when present.",
    "qwen3-asr": "external qwen3-asr-cli plus a local GGUF model (reused in place).",
    "whisper.cpp": "optional whisper-cli/whisper.cpp binary plus a local GGUF/bin model.",
}
DOWNLOADABLE_ASR_MODELS = (
    {"model_id": "faster-whisper-tiny", "engine": "faster-whisper",
     "language": "Multilingual", "size_mb": 75, "max_download_mb": 180,
     "license": "MIT", "repo_id": "Systran/faster-whisper-tiny"},
    {"model_id": "faster-whisper-base", "engine": "faster-whisper",
     "language": "Multilingual", "size_mb": 142, "max_download_mb": 320,
     "license": "MIT", "repo_id": "Systran/faster-whisper-base"},
    {"model_id": "faster-whisper-small", "engine": "faster-whisper",
     "language": "Multilingual", "size_mb": 466, "max_download_mb": 900,
     "license": "MIT", "repo_id": "Systran/faster-whisper-small"},
    {"model_id": "vosk-model-small-it-0.22", "engine": "vosk",
     "language": "Italian", "size_mb": 48,
     "license": "Apache-2.0",
     "url": "https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip"},
    {"model_id": "vosk-model-small-en-us-0.15", "engine": "vosk",
     "language": "English (US)", "size_mb": 40,
     "license": "Apache-2.0",
     "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"},
)
MAX_ASR_DOWNLOAD_BYTES = 160 * 1024 * 1024
MAX_ASR_EXTRACTED_BYTES = 240 * 1024 * 1024


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


def _qwen3_external_homes() -> list[Path]:
    """Discover an existing Qwen3-ASR CLI/model install without copying it."""
    homes: list[Path] = []
    raw = os.environ.get("NL_QWEN3_ASR_HOME", "").strip()
    if raw:
        homes.append(Path(raw).expanduser())
    try:
        configured = database.get_json_setting("speech.qwen3_home") if hasattr(
            database, "get_json_setting") else None
        if isinstance(configured, dict) and configured.get("path"):
            homes.append(Path(str(configured["path"])).expanduser())
    except Exception:
        pass
    candidates = [Path(r"J:\ZLinkdaC\Qwen3ASR")] if os.name == "nt" else []
    for candidate in candidates:
        if candidate.is_dir():
            homes.append(candidate)
    return [path.resolve() for path in homes if path.is_dir()]


def _qwen3_cli(home: Path | None = None) -> Path | None:
    homes = [home] if home else _qwen3_external_homes()
    for root in homes:
        if root is None:
            continue
        for name in ("qwen3-asr-cli.exe", "qwen3-asr-cli", "qwen3_asr_cli"):
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def _whisper_cpp_cli_from_root(root: Path) -> Path | None:
    names = ("whisper-cli.exe", "whisper-cli", "main.exe", "main")
    candidates = [root / name for name in names]
    candidates.extend(root / "bin" / name for name in names)
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def _whisper_cpp_cli() -> Path | None:
    configured = os.environ.get("NL_WHISPER_CPP_HOME", "").strip()
    roots = [Path(configured).expanduser()] if configured else []
    try:
        stored = database.get_json_setting("speech.whisper_cpp_home", {})
        if isinstance(stored, dict) and stored.get("path"):
            roots.append(Path(str(stored["path"])).expanduser())
    except Exception:
        pass
    names = ("whisper-cli.exe", "whisper-cli", "main.exe", "main")
    for root in roots:
        candidate = _whisper_cpp_cli_from_root(root)
        if candidate is not None:
            return candidate
    for name in names[:2]:
        found = shutil.which(name)
        if found:
            return Path(found).resolve()
    return None


def _recordings_root() -> Path:
    return database.data_root() / "speech" / "recordings"


def detect_capabilities(*, probes: dict | None = None,
                        tts_probes: dict | None = None,
                        device_probe_error: str | None = None) -> SpeechCapabilities:
    probes = dict(probes or {})
    qwen3_cli = _qwen3_cli()
    engines = {
        engine: bool(probes.get(engine, _importable(engine.replace("-", "_"))))
        for engine in DEFAULT_ENGINES
    }
    if "qwen3-asr" in engines:
        engines["qwen3-asr"] = bool(probes.get("qwen3-asr", qwen3_cli is not None))
    if "whisper.cpp" in engines:
        engines["whisper.cpp"] = bool(probes.get("whisper.cpp", _whisper_cpp_cli() is not None))
    local_dirs = [str(_default_model_root()), *[str(path) for path in _env_model_dirs()]]
    try:
        external_config = database.get_json_setting("speech.external_model_dirs", {})
        external_dirs = external_config.get("paths", []) if isinstance(external_config, dict) else []
        if isinstance(external_dirs, list):
            for value in external_dirs:
                if not str(value).strip():
                    continue
                external_root = Path(str(value)).expanduser()
                local_dirs.append(str(external_root))
                nested_models = external_root / "models"
                if nested_models.is_dir():
                    local_dirs.append(str(nested_models))
    except Exception:
        pass
    for home in _qwen3_external_homes():
        candidate = home / "models"
        if candidate.is_dir() and str(candidate) not in local_dirs:
            local_dirs.append(str(candidate))
    whisper_home = os.environ.get("NL_WHISPER_CPP_HOME", "").strip()
    try:
        stored_whisper = database.get_json_setting("speech.whisper_cpp_home", {})
        if not whisper_home and isinstance(stored_whisper, dict):
            whisper_home = str(stored_whisper.get("path") or "")
    except Exception:
        pass
    if whisper_home:
        candidate = Path(whisper_home).expanduser() / "models"
        if candidate.is_dir() and str(candidate) not in local_dirs:
            local_dirs.append(str(candidate))
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
    markers = ("model.bin", "config.json", "*.gguf", "ggml-*.bin", "*.onnx", "am")
    for marker in markers:
        if marker.startswith("*"):
            if list(path.glob(marker)):
                return True
        elif (path / marker).exists():
            return True
    return False


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
            children = []
            if ((root / "model.bin").is_file() or (root / "config.json").is_file()
                    or (root / "am").is_dir()):
                children.append(root)
            children.extend(sorted(root.iterdir()))
            for child in children:
                if str(child) in seen:
                    continue
                if child.is_file() and child.suffix.lower() == ".gguf":
                    lower_name = child.name.lower()
                    if "forced-aligner" in lower_name or "aligner" in lower_name:
                        continue
                    if "qwen3-asr" not in lower_name and "qwen-asr" not in lower_name:
                        continue
                    seen.add(str(child))
                    models.append(SpeechModel(child.name, "qwen3-asr", str(child),
                                             child.stat().st_size / (1024 * 1024)))
                    continue
                if child.is_file() and child.name.lower().startswith("ggml-") \
                        and child.suffix.lower() == ".bin":
                    seen.add(str(child))
                    models.append(SpeechModel(child.stem, "whisper.cpp", str(child),
                                             child.stat().st_size / (1024 * 1024)))
                    continue
                if not child.is_dir():
                    continue
                if child.name.lower() == "models" and (
                        any(child.glob("qwen*asr*.gguf")) or any(child.glob("ggml-*.bin"))):
                    continue
                if not _is_model_dir(child):
                    continue
                seen.add(str(child))
                if (child / "model.bin").exists() or (child / "config.json").exists():
                    engine = "faster-whisper"
                elif (child / "am").is_dir():
                    engine = "vosk"
                elif any(child.glob("qwen*asr*.gguf")):
                    engine = "qwen3-asr"
                elif any(child.glob("ggml-*.bin")):
                    engine = "whisper.cpp"
                else:
                    continue
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
            "downloadable_models": [dict(item) for item in DOWNLOADABLE_ASR_MODELS],
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

    def download_model(self, model_id: str) -> dict:
        """Download one curated Vosk or Faster-Whisper model after explicit consent."""
        choice = next((item for item in DOWNLOADABLE_ASR_MODELS
                       if item["model_id"] == str(model_id)), None)
        if choice is None:
            raise SpeechError("unknown-model-download", "No curated download exists for " + repr(model_id))
        if (choice["engine"] == "vosk"
                and not self.capabilities.engines.get("vosk")):
            raise SpeechError("asr-unavailable",
                              "Install the Vosk engine before downloading a Vosk model: "
                              + ASR_INSTALL_HINTS["vosk"])

        model_root = _default_model_root()
        target = model_root / str(choice["model_id"])
        if target.exists():
            if _is_model_dir(target):
                return next(model.to_dict() for model in self.discover_models()
                            if model.path == str(target))
            raise SpeechError("model-path-exists",
                              "Model target exists but is not a valid model; nothing was overwritten: "
                              + str(target))
        model_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="nl-asr-download-", dir=str(model_root.parent)) as temp:
            if choice["engine"] == "faster-whisper":
                if not self.capabilities.engines.get("faster-whisper"):
                    raise SpeechError("asr-unavailable",
                                      "Install faster-whisper in the embedded Python runtime first.")
                staging = Path(temp) / str(choice["model_id"])
                try:
                    from huggingface_hub import snapshot_download
                    snapshot_download(
                        repo_id=str(choice["repo_id"]), local_dir=str(staging), max_workers=4,
                        allow_patterns=["config.json", "model.bin", "tokenizer.json",
                                        "preprocessor_config.json", "vocabulary.*", "*.json"],
                    )
                except Exception as exc:
                    raise SpeechError("download-failed", "Could not download Faster-Whisper model: "
                                      + str(exc)[:800]) from exc
                downloaded_bytes = sum(item.stat().st_size for item in staging.rglob("*")
                                       if item.is_file())
                if downloaded_bytes > int(choice["max_download_mb"]) * 1024 * 1024:
                    raise SpeechError("download-too-large", "Faster-Whisper snapshot exceeds its catalog size limit.")
                if not (staging / "config.json").is_file() or not (staging / "model.bin").is_file():
                    raise SpeechError("model-invalid", "Faster-Whisper snapshot lacks config.json or model.bin.")
                shutil.move(str(staging), str(target))
                return next(model.to_dict() for model in self.discover_models()
                            if model.path == str(target))

            archive_path = Path(temp) / "model.zip"
            total = 0
            try:
                with urllib.request.urlopen(str(choice["url"]), timeout=30) as response:
                    with archive_path.open("wb") as archive_file:
                        while True:
                            block = response.read(1024 * 1024)
                            if not block:
                                break
                            total += len(block)
                            if total > MAX_ASR_DOWNLOAD_BYTES:
                                raise SpeechError("download-too-large",
                                                  "ASR model archive exceeds the 160 MiB download limit.")
                            archive_file.write(block)
            except SpeechError:
                raise
            except Exception as exc:
                raise SpeechError("download-failed", "Could not download ASR model: " + str(exc)) from exc

            extraction_root = Path(temp) / "unpacked"
            extraction_root.mkdir()
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    total_unpacked = 0
                    for member in archive.infolist():
                        member_path = PurePosixPath(member.filename)
                        if member_path.is_absolute() or ".." in member_path.parts:
                            raise SpeechError("archive-path-invalid", "ASR archive contains an unsafe path.")
                        mode = member.external_attr >> 16
                        if stat.S_ISLNK(mode):
                            raise SpeechError("archive-path-invalid", "ASR archive contains a symlink.")
                        total_unpacked += int(member.file_size)
                        if total_unpacked > MAX_ASR_EXTRACTED_BYTES:
                            raise SpeechError("archive-too-large",
                                              "ASR archive expands beyond the 240 MiB safety limit.")
                    archive.extractall(extraction_root)
            except SpeechError:
                raise
            except Exception as exc:
                raise SpeechError("archive-invalid", "Could not unpack ASR model: " + str(exc)) from exc

            extracted = extraction_root / str(choice["model_id"])
            if not _is_model_dir(extracted) or not (extracted / "am").is_dir():
                raise SpeechError("model-invalid", "Downloaded archive did not contain a valid Vosk model.")
            shutil.move(str(extracted), str(target))

        return next(model.to_dict() for model in self.discover_models()
                    if model.path == str(target))

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

    def switch_model(self, model_id: str, engine: str = "") -> dict:
        wanted = str(model_id or "").strip()
        requested_engine = str(engine or "").strip()
        match = next((m for m in self.discover_models()
                      if m.model_id == wanted
                      and (not requested_engine or m.engine == requested_engine)), None)
        if match is None:
            raise SpeechError("model-not-local",
                              "Speech model " + repr(wanted)
                              + (f" for engine {requested_engine!r}" if requested_engine else "")
                              + " is not a discovered local model.")
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

    def set_external_home(self, path: str) -> dict:
        """Register an existing local ASR model folder without copying it."""
        root = Path(str(path or "")).expanduser().resolve()
        if not root.is_dir():
            raise SpeechError("external-folder-missing", "External folder does not exist: " + str(root))
        cli = _qwen3_cli(root)
        whisper_cli = _whisper_cpp_cli_from_root(root)
        qwen_models = list(root.glob("*.gguf")) + list((root / "models").glob("*.gguf"))
        previous_dirs = self._model_dirs
        candidates = [root]
        models_dir = root / "models"
        if models_dir.is_dir():
            candidates.append(models_dir)
        self._model_dirs = [*previous_dirs, *candidates]
        discovered = [
            model for model in self.discover_models()
            if Path(model.path).resolve().is_relative_to(root)
        ]
        if not discovered:
            self._model_dirs = previous_dirs
            raise SpeechError(
                "external-folder-invalid",
                "No supported local ASR model was found in the selected folder or its models subfolder.")
        external_config = database.get_json_setting("speech.external_model_dirs", {})
        stored_dirs = external_config.get("paths", []) if isinstance(external_config, dict) else []
        if not isinstance(stored_dirs, list):
            stored_dirs = []
        registered_dirs = list(dict.fromkeys(
            [str(item) for item in stored_dirs if str(item).strip()] + [str(root)]))
        database.set_json_setting("speech.external_model_dirs", {"paths": registered_dirs})
        if cli is not None or qwen_models:
            qwen_home = root.parent if root.name.lower() == "models" else root
            database.set_json_setting("speech.qwen3_home", {"path": str(qwen_home), "set_at": _now()})
        if whisper_cli is not None:
            database.set_json_setting("speech.whisper_cpp_home", {"path": str(root), "set_at": _now()})
        self.capabilities = detect_capabilities()
        self._model_dirs = [Path(item).expanduser() for item in self.capabilities.local_model_dirs]
        return {"external_home": str(root), "models": [item.to_dict() for item in discovered],
                "qwen3_cli": str(cli) if cli else None,
                "whisper_cpp_cli": str(whisper_cli) if whisper_cli else None,
                "catalog": self.catalog()}

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

    def _run_qwen3_asr(self, wav_path: str, model_path: str, *, language=None) -> dict:
        """Run an existing Qwen3-ASR GGUF CLI in place; never copy the model."""
        model = Path(model_path).expanduser()
        if not model.is_file():
            raise SpeechError("model-not-local", "Qwen3-ASR model file is missing: " + str(model))
        home = model.parent.parent if model.parent.name.lower() == "models" else model.parent
        cli = _qwen3_cli(home) or _qwen3_cli()
        if cli is None:
            raise SpeechError("asr-unavailable",
                              "qwen3-asr-cli was not found; point NL_QWEN3_ASR_HOME at the install.")
        import subprocess
        source = Path(wav_path)
        temp_wav: Path | None = None
        try:
            with wave.open(str(source), "rb") as reader:
                channels = reader.getnchannels()
                width = reader.getsampwidth()
                rate = reader.getframerate()
                frames = reader.readframes(reader.getnframes())
            if rate != 16000 or channels != 1:
                if width != 2:
                    raise SpeechError("unsupported-audio", "Qwen3-ASR requires 16-bit WAV audio.")
                if channels != 1:
                    frames = audioop.tomono(frames, width, 0.5, 0.5)
                if rate != 16000:
                    frames, _ = audioop.ratecv(frames, width, 1, rate, 16000, None)
                temp_fd, temp_name = tempfile.mkstemp(prefix="nl-asr-", suffix=".wav")
                os.close(temp_fd)
                temp_wav = Path(temp_name)
                with wave.open(str(temp_wav), "wb") as writer:
                    writer.setnchannels(1)
                    writer.setsampwidth(width)
                    writer.setframerate(16000)
                    writer.writeframes(frames)
                source = temp_wav
            command = [str(cli), "-m", str(model), "-f", str(source),
                       "--no-timing", "--threads", "4"]
            if language:
                command.extend(["-l", str(language)])
            try:
                completed = subprocess.run(command, capture_output=True, text=True,
                                           timeout=300, encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired as exc:
                raise SpeechError("asr-timeout", "Qwen3-ASR timed out.") from exc
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()[-800:]
                raise SpeechError("asr-failed", "Qwen3-ASR failed: " + detail)
            lines = [line.strip() for line in (completed.stdout or "").splitlines()]
            skip = ("qwen3-asr-cli", "model:", "audio:", "threads:", "language:")
            text = " ".join(line for line in lines
                            if line and not line.lower().startswith(skip))
            return {"text": text, "engine": "qwen3-asr", "model": model.name,
                    "segments": [], "language": language}
        finally:
            if temp_wav is not None:
                try:
                    temp_wav.unlink(missing_ok=True)
                except OSError:
                    pass

    def _run_local_asr(self, path: str, active: dict, *, language=None) -> dict:
        engine = str(active.get("engine") or "")
        model_path = str(active.get("path") or "")
        if engine == "qwen3-asr":
            return self._run_qwen3_asr(path, model_path, language=language)
        if engine == "whisper.cpp":
            return self._run_whisper_cpp_asr(path, model_path, language=language)
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
        if engine == "vosk":
            return self._run_vosk_asr(path, model_path)
        raise SpeechError("asr-unavailable",
                          "No local ASR adapter for engine " + repr(engine)
                          + "; install/configure it explicitly.")

    def _run_whisper_cpp_asr(self, wav_path: str, model_path: str, *, language=None) -> dict:
        cli = _whisper_cpp_cli()
        model = Path(model_path).expanduser()
        if cli is None:
            raise SpeechError("asr-unavailable",
                              "whisper-cli was not found; register its folder in Engine → Dictation.")
        if not model.is_file():
            raise SpeechError("model-not-local", "whisper.cpp model file is missing: " + str(model))
        import subprocess
        with tempfile.TemporaryDirectory(prefix="nl-whisper-output-",
                                         dir=str(database.data_root())) as temp:
            output_prefix = Path(temp) / "transcript"
            command = [str(cli), "-m", str(model), "-f", str(Path(wav_path).resolve()),
                       "-nt", "-otxt", "-of", str(output_prefix)]
            if language:
                command.extend(["-l", str(language)])
            try:
                completed = subprocess.run(command, capture_output=True, text=True,
                                           timeout=300, encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired as exc:
                raise SpeechError("asr-timeout", "whisper.cpp transcription timed out.") from exc
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()[-800:]
                raise SpeechError("asr-failed", "whisper.cpp failed: " + detail)
            text_path = output_prefix.with_suffix(".txt")
            text = text_path.read_text(encoding="utf-8", errors="replace").strip() \
                if text_path.is_file() else str(completed.stdout or "").strip()
            return {"text": text, "engine": "whisper.cpp", "model": model.name,
                    "segments": [], "language": language}

    def _run_vosk_asr(self, wav_path: str, model_path: str) -> dict:
        """Lightweight offline Vosk adapter for a local model directory."""
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
        except ImportError as exc:
            raise SpeechError("asr-unavailable", "vosk is not installed.") from exc
        root = Path(model_path)
        if not root.is_dir():
            raise SpeechError("model-not-local", "Vosk model directory is missing: " + str(root))
        SetLogLevel(-1)
        with wave.open(wav_path, "rb") as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            rate = reader.getframerate()
            frames = reader.readframes(reader.getnframes())
        if width != 2:
            raise SpeechError("unsupported-audio", "Vosk requires 16-bit PCM WAV audio.")
        if channels != 1:
            frames = audioop.tomono(frames, width, 0.5, 0.5)
        if rate != 16000:
            frames = audioop.ratecv(frames, width, 1, rate, 16000, None)[0]
        model = Model(str(root))
        recognizer = KaldiRecognizer(model, 16000)
        recognizer.AcceptWaveform(frames)
        payload = json.loads(recognizer.FinalResult() or "{}")
        return {"text": str(payload.get("text") or "").strip(),
                "engine": "vosk", "model": root.name, "segments": []}

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
        self._app = None

    def start(self, max_seconds: int) -> None:
        from PySide6.QtCore import QCoreApplication  # noqa: F401 - availability check
        from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

        # The MCP engine is headless: QtMultimedia still needs an application
        # instance and explicit event processing for QAudioSource callbacks.
        self._app = QCoreApplication.instance() or QCoreApplication([])
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
            # Let readyRead callbacks deliver buffered audio before closing.
            for _ in range(20):
                if self._app is not None:
                    self._app.processEvents()
                self._drain()
                time.sleep(0.01)
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

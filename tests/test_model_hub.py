import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

from PySide6.QtWidgets import QApplication

from nl_coding_agent.gui.widgets.models_panel import ModelsPanel
from nl_coding_agent.gui.widgets.sidebar import PAGES
from nl_coding_agent.models.ollama_registry import OllamaModel
from nl_coding_agent.models.providers import (
    ModelHub,
    ModelHubSnapshot,
    ModelInfo,
    OpenAICompatibleProvider,
    OllamaProvider,
    ProviderSnapshot,
    build_providers,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_build_providers_uses_enabled_entries_only():
    providers = build_providers(
        {
            "providers": {
                "ollama": {
                    "enabled": True,
                    "kind": "ollama",
                    "label": "Ollama",
                    "base_url": "http://127.0.0.1:11434",
                },
                "lm_studio": {
                    "enabled": True,
                    "kind": "openai_compatible",
                    "label": "LM Studio",
                    "base_url": "http://127.0.0.1:1234/v1",
                },
                "disabled": {
                    "enabled": False,
                    "kind": "openai_compatible",
                    "base_url": "http://127.0.0.1:9999/v1",
                },
            }
        }
    )
    assert [provider.provider_id for provider in providers] == ["ollama", "lm_studio"]
    assert isinstance(providers[0], OllamaProvider)
    assert isinstance(providers[1], OpenAICompatibleProvider)


def test_openai_compatible_probe_parses_models(monkeypatch):
    monkeypatch.setattr(
        "nl_coding_agent.models.providers._http_json",
        lambda url, timeout, headers=None: {
            "data": [
                {"id": "local-coder", "owned_by": "lmstudio", "size": 4_000_000_000},
                {"id": "embed", "owned_by": "lmstudio"},
            ]
        },
    )
    provider = OpenAICompatibleProvider(
        "lm_studio", "LM Studio", "http://127.0.0.1:1234/v1"
    )
    snapshot = provider.probe(timeout=0.1)
    assert snapshot.reachable is True
    assert [model.name for model in snapshot.models] == ["local-coder", "embed"]
    assert snapshot.models[0].size_gb == 4.0
    assert snapshot.models[0].provider_id == "lm_studio"


def test_openai_compatible_probe_reports_actionable_error(monkeypatch):
    def fail(url, timeout, headers=None):
        raise OSError("connection refused")

    monkeypatch.setattr("nl_coding_agent.models.providers._http_json", fail)
    snapshot = OpenAICompatibleProvider(
        "lm_studio", "LM Studio", "http://127.0.0.1:1234/v1"
    ).probe(timeout=0.1)
    assert snapshot.reachable is False
    assert "not reachable" in snapshot.error
    assert "127.0.0.1:1234" in snapshot.error


def test_ollama_provider_marks_loaded_models(monkeypatch):
    monkeypatch.setattr(
        "nl_coding_agent.models.providers.check_ollama_reachable",
        lambda base_url, timeout: True,
    )
    monkeypatch.setattr(
        "nl_coding_agent.models.providers.ollama_models",
        lambda base_url, timeout: [
            OllamaModel(name="qwen3.5:9b", size_gb=6.6, loaded=False, family="qwen3"),
            OllamaModel(name="coder:7b", size_gb=4.7, loaded=True, family="qwen2"),
        ],
    )
    monkeypatch.setattr(
        "nl_coding_agent.models.providers.ollama_loaded_models",
        lambda base_url, timeout: [
            OllamaModel(name="coder:7b", size_gb=4.7, loaded=True)
        ],
    )
    snapshot = OllamaProvider().probe(timeout=0.1)
    assert snapshot.reachable is True
    assert [model.name for model in snapshot.models] == ["qwen3.5:9b", "coder:7b"]
    assert snapshot.models[1].loaded is True
    assert [model.name for model in snapshot.loaded] == ["coder:7b"]


def test_model_hub_aggregates_and_reports_errors(monkeypatch):
    hub = ModelHub(
        [
            OllamaProvider(),
            OpenAICompatibleProvider("lm_studio", "LM Studio", "http://127.0.0.1:1234/v1"),
        ]
    )
    monkeypatch.setattr(
        "nl_coding_agent.models.providers.check_ollama_reachable",
        lambda base_url, timeout: True,
    )
    monkeypatch.setattr(
        "nl_coding_agent.models.providers.ollama_models",
        lambda base_url, timeout: [OllamaModel(name="a", size_gb=1.0, loaded=False)],
    )
    monkeypatch.setattr(
        "nl_coding_agent.models.providers.ollama_loaded_models",
        lambda base_url, timeout: [],
    )

    def fail(url, timeout, headers=None):
        raise OSError("offline")

    monkeypatch.setattr("nl_coding_agent.models.providers._http_json", fail)
    snapshot = hub.discover(timeout=0.1)
    assert [model.name for model in snapshot.models] == ["a"]
    assert snapshot.reachable is True
    assert len(snapshot.errors) == 1
    assert "LM Studio" in snapshot.errors[0]


def test_model_hub_panel_renders_and_recovers_from_error():
    _app()
    snapshot = ModelHubSnapshot(
        [
            ProviderSnapshot(
                provider_id="ollama",
                label="Ollama",
                kind="ollama",
                base_url="http://127.0.0.1:11434",
                reachable=True,
                models=[
                    ModelInfo(
                        provider_id="ollama",
                        provider_label="Ollama",
                        name="qwen3.5:9b",
                        size_gb=6.6,
                        loaded=True,
                        family="qwen3",
                    )
                ],
                loaded=[
                    ModelInfo(
                        provider_id="ollama",
                        provider_label="Ollama",
                        name="qwen3.5:9b",
                        size_gb=6.6,
                        loaded=True,
                    )
                ],
            )
        ]
    )

    class FakeServices:
        def __init__(self):
            self.saved = None

        def discover_models(self, timeout=5.0):
            return snapshot

        def save_generation_params(self, params, **kwargs):
            self.saved = (params, kwargs)
            return dict(params)

        def generation_params(self, **kwargs):
            return {"effective": {}, "configured": []}

    services = FakeServices()
    panel = ModelsPanel(services)
    assert panel._tabs.count() == 5
    panel._on_snapshot(snapshot)
    assert panel._table.rowCount() == 1
    assert panel._table.item(0, 1).text() == "qwen3.5:9b"
    assert "1 model" in panel._status_label.text()
    panel._gp_scope.setCurrentText("model")
    panel._gp_model.setText("ollama/qwen3.5:9b")
    panel._gp_fields["temperature"].setText("0.2")
    panel._gp_fields["top_k"].setText("40")
    panel._save_parameters()
    assert services.saved is not None
    params, kwargs = services.saved
    assert params == {"temperature": 0.2, "top_k": 40}
    assert kwargs["scope"] == "model"
    assert kwargs["model_name"] == "ollama/qwen3.5:9b"
    assert "Saved" in panel._gp_status.text()
    panel._on_error("offline")
    assert "offline" in panel._status_label.text()
    assert panel._refresh_btn.isEnabled()
    panel.shutdown()


def test_speech_tab_selects_engine_model_and_registers_external_model():
    app = _app()

    class FakeServices:
        def __init__(self):
            self.catalog = {
                "engines": [
                    {"engine": "vosk", "installed": True, "hint": "Vosk runtime"},
                    {"engine": "whisper.cpp", "installed": True, "hint": "Whisper runtime"},
                ],
                "models": [
                    {"model_id": "vosk-it", "engine": "vosk", "path": "D:/asr/vosk-it"},
                    {"model_id": "ggml-tiny", "engine": "whisper.cpp", "path": "D:/asr/ggml-tiny.bin"},
                ],
                "active_model": {"model_id": "vosk-it", "engine": "vosk", "path": "D:/asr/vosk-it"},
            }
            self.selected = None
            self.external_path = None
            self.called_off_gui_thread = False

        def speech_catalog(self):
            from PySide6.QtCore import QThread
            self.called_off_gui_thread = QThread.currentThread() != app.thread()
            return self.catalog

        def speech_switch_model(self, model_id, engine):
            from PySide6.QtCore import QThread
            self.called_off_gui_thread = QThread.currentThread() != app.thread()
            self.selected = (model_id, engine)
            model = next(item for item in self.catalog["models"]
                         if item["model_id"] == model_id and item["engine"] == engine)
            self.catalog["active_model"] = model
            return model

        def speech_set_external_home(self, path):
            from PySide6.QtCore import QThread
            self.called_off_gui_thread = QThread.currentThread() != app.thread()
            self.external_path = path
            model = {"model_id": "external-it", "engine": "vosk", "path": path}
            self.catalog["models"].append(model)
            self.catalog["active_model"] = model
            return {"models": [model], "catalog": self.catalog}

    services = FakeServices()
    panel = ModelsPanel(services)
    panel._render_speech_catalog(services.catalog)
    assert panel._speech_engine.currentData() == "vosk"
    assert panel._speech_model.currentData() == "vosk-it"

    panel._speech_engine.setCurrentIndex(panel._speech_engine.findData("whisper.cpp"))
    assert panel._speech_model.count() == 1
    assert panel._speech_model.currentData() == "ggml-tiny"
    panel._speech_engine.setCurrentIndex(panel._speech_engine.findData("vosk"))
    panel._speech_model.setCurrentIndex(panel._speech_model.findData("vosk-it"))
    panel._speech_use.click()
    deadline = time.monotonic() + 3
    while services.selected is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert services.selected == ("vosk-it", "vosk")
    assert services.called_off_gui_thread is True
    deadline = time.monotonic() + 3
    while panel._speech_thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert panel._speech_thread is None

    panel._speech_external_path.setText("D:/external/vosk-it")
    panel._speech_add_external.click()
    deadline = time.monotonic() + 3
    while services.external_path is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert services.external_path == "D:/external/vosk-it"
    deadline = time.monotonic() + 3
    while panel._speech_model.findData("external-it") < 0 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert panel._speech_model.findData("external-it") >= 0
    assert "not copied" in panel._speech_status.text()
    panel.shutdown()


def test_model_hub_is_visible_in_sidebar():
    assert ("Model Hub", "models") in PAGES

"""F2 chat voice: dictation insertion, TTS toggle, failure status, no auto-submit."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


class FakeSpeech:
    def __init__(self, *, transcript="dictated mission text", fail_start=False,
                 fail_transcribe=False):
        self.transcript = transcript
        self.fail_start = fail_start
        self.fail_transcribe = fail_transcribe
        self.calls = []
        self.tts_calls = []

    def start_recording(self, *, max_seconds=60):
        self.calls.append(("start", max_seconds))
        if self.fail_start:
            raise _speech_error("audio-unavailable", "no microphone backend")
        return {"session_id": "s1", "max_seconds": max_seconds, "backend": "fake"}

    def stop_recording(self, session_id):
        self.calls.append(("stop", session_id))
        return {"wav_path": "fake.wav", "duration_s": 1.0}

    def transcribe(self, wav_path):
        self.calls.append(("transcribe", wav_path))
        if self.fail_transcribe:
            raise _speech_error("asr-unavailable", "no local ASR model")
        return {"text": self.transcript, "editable": True, "engine": "fake"}

    def speak(self, text):
        self.tts_calls.append(text)
        return {"spoken": True}


def _speech_error(code, message):
    from nl_coding_agent.app.speech import SpeechError
    return SpeechError(code, message)


@pytest.fixture()
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    from nl_coding_agent.app.services import AppServices
    instance = AppServices()
    yield instance
    try:
        instance._db.close()
    except Exception:
        pass


@pytest.fixture()
def panel(services, tmp_path):
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
    _app()
    widget = ChatPanel(services, speech=FakeSpeech())
    widget.set_project({"id": 1, "root": str(tmp_path)})
    yield widget
    widget.deleteLater()
    _app().processEvents()


def test_voice_controls_accessible_and_shortcut(panel):
    assert panel._mic_btn.accessibleName() == "Start or stop dictation"
    assert panel._voice_stop_btn.accessibleName() == "Stop voice recording"
    assert panel._voice_status.accessibleName() == "Voice status"
    assert panel._tts_toggle.accessibleName() == "Read transcript aloud"
    assert panel._voice_stop_btn.isEnabled() is False
    shortcuts = {s.key().toString() for s in panel.findChildren(QShortcut)}
    assert any("Ctrl+Shift+M" in item for item in shortcuts)


def test_dictation_inserts_editable_transcript_and_never_submits(panel):
    submitted = []
    panel.submitted.connect(submitted.append)
    panel._mic_btn.click()
    assert panel._voice_session is not None
    assert panel._voice_stop_btn.isEnabled() is True
    assert "recording" in panel._voice_status.text().lower()
    panel._stop_voice()
    assert panel.wait_for_idle()
    assert "dictated mission text" in panel._input.toPlainText()
    assert submitted == []  # transcript insertion is editable, never auto-submit
    assert panel._voice_session is None
    panel._input.setPlainText("edited transcript")
    assert panel._input.toPlainText() == "edited transcript"


def test_tts_toggle_speaks_transcript_only_when_enabled(panel):
    panel._tts_toggle.setChecked(True)
    panel._mic_btn.click()
    panel._stop_voice()
    assert panel.wait_for_idle()
    assert panel._speech.tts_calls == ["dictated mission text"]


def test_voice_start_failure_is_clear_and_does_not_crash(services, tmp_path):
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
    _app()
    widget = ChatPanel(services, speech=FakeSpeech(fail_start=True))
    widget.set_project({"id": 1, "root": str(tmp_path)})
    widget._mic_btn.click()
    assert "audio-unavailable" in widget._voice_status.text()
    assert widget._voice_session is None
    widget.deleteLater()
    _app().processEvents()


def test_transcription_failure_is_shown_with_code(services, tmp_path):
    from nl_coding_agent.gui.widgets.chat_panel import ChatPanel
    _app()
    widget = ChatPanel(services, speech=FakeSpeech(fail_transcribe=True))
    widget.set_project({"id": 1, "root": str(tmp_path)})
    widget._mic_btn.click()
    widget._stop_voice()
    assert widget.wait_for_idle()
    assert "asr-unavailable" in widget._voice_status.text()
    assert widget._input.toPlainText() == ""
    widget.deleteLater()
    _app().processEvents()


def test_ctrl_shift_m_shortcut_toggles_voice(panel):
    shortcut = next(s for s in panel.findChildren(QShortcut)
                    if "Ctrl+Shift+M" in s.key().toString())
    shortcut.activated.emit()
    assert panel._voice_session is not None
    shortcut.activated.emit()
    assert panel.wait_for_idle()
    assert panel._voice_session is None

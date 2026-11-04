"""Loopback HTTP tests for incremental provider streaming.

All responses are synthetic and served from 127.0.0.1; no live model runtime,
vendor checkout or user data is touched. NL_DATA_DIR is redirected per test so
the permission checks use a throw-away SQLite database.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from nl_coding_agent.core import permissions
from nl_coding_agent.models import generation_params
from nl_coding_agent.models.providers import OllamaProvider, OpenAICompatibleProvider


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "state"))


@contextmanager
def _loopback_server(responder):
    calls: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw)
            calls.append({"path": self.path, "body": body, "headers": dict(self.headers)})
            responder(self, body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port), calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def _start_stream(handler, content_type: str) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()


def _write(handler, payload: str) -> None:
    handler.wfile.write(payload.encode("utf-8"))
    handler.wfile.flush()


def _sse(event) -> str:
    return "data: " + json.dumps(event) + "\n\n"


def test_ollama_streams_text_before_the_response_ends():
    first_seen = threading.Event()
    release = threading.Event()

    def responder(handler, body):
        _start_stream(handler, "application/x-ndjson")
        _write(handler, json.dumps({
            "message": {"role": "assistant", "content": "Hel"}, "done": False,
        }) + "\n")
        release.wait(5)
        _write(handler, json.dumps({
            "message": {"role": "assistant", "content": "lo"}, "done": False,
        }) + "\n")
        _write(handler, json.dumps({
            "message": {"role": "assistant", "content": ""}, "done": True,
            "prompt_eval_count": 5, "eval_count": 2,
        }) + "\n")

    with _loopback_server(responder) as (base, calls):
        generation_params.save_params(
            {"temperature": 0.25}, scope="role", role="chat")
        provider = OllamaProvider(base_url=base)
        deltas: list[str] = []
        outcome: dict = {}

        def on_delta(text):
            deltas.append(text)
            first_seen.set()

        def run():
            try:
                outcome["message"] = provider.chat_turn_stream(
                    "demo",
                    [{"role": "user", "content": "hi"}],
                    [{"type": "function", "function": {"name": "ping"}}],
                    timeout=10,
                    on_delta=on_delta,
                )
            except Exception as exc:  # pragma: no cover - surfaced by assertion
                outcome["error"] = exc

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        assert first_seen.wait(5), "no text fragment arrived while the server was still open"
        assert not release.is_set()
        assert deltas == ["Hel"]
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert "error" not in outcome, outcome.get("error")
        message = outcome["message"]
        assert message["content"] == "Hello"
        assert message["_usage"] == {"prompt_tokens": 5, "output_tokens": 2}
        assert calls[0]["path"] == "/api/chat"
        assert calls[0]["body"]["stream"] is True
        assert calls[0]["body"]["tools"][0]["function"]["name"] == "ping"
        assert calls[0]["body"]["options"] == {"temperature": 0.25}


def test_openai_compatible_accumulates_fragmented_tool_call_arguments():
    def responder(handler, body):
        _start_stream(handler, "text/event-stream")
        _write(handler, _sse({"choices": [{"index": 0, "delta": {
            "role": "assistant", "content": "I"}}]}))
        _write(handler, _sse({"choices": [{"index": 0, "delta": {
            "content": "'ll check."}}]}))
        _write(handler, _sse({"choices": [{"index": 0, "delta": {
            "tool_calls": [{"index": 0, "id": "call_abc", "type": "function",
                            "function": {"name": "get_weather",
                                         "arguments": "{\"ci"}}]}}]}))
        _write(handler, _sse({"choices": [{"index": 0, "delta": {
            "tool_calls": [{"index": 0, "function": {
                "arguments": "ty\":\"Paris\"}"}}]}}]}))
        _write(handler, _sse({"choices": [{"index": 0, "delta": {},
                                           "finish_reason": "tool_calls"}],
                              "usage": {"prompt_tokens": 11,
                                        "completion_tokens": 7}}))
        _write(handler, "data: [DONE]\n\n")

    with _loopback_server(responder) as (base, calls):
        provider = OpenAICompatibleProvider("local", "Local", base + "/v1")
        deltas: list[str] = []
        message = provider.chat_turn_stream(
            "demo",
            [{"role": "user", "content": "weather?"}],
            [{"type": "function", "function": {"name": "get_weather"}}],
            timeout=10,
            on_delta=deltas.append,
        )

    assert calls[0]["path"] == "/v1/chat/completions"
    assert calls[0]["body"]["stream"] is True
    assert calls[0]["body"]["tools"][0]["function"]["name"] == "get_weather"
    assert calls[0]["body"]["stream_options"] == {"include_usage": True}
    assert deltas == ["I", "'ll check."]
    assert message["content"] == "I'll check."
    assert message["_usage"] == {"prompt_tokens": 11, "output_tokens": 7}
    assert message["tool_calls"] == [{
        "function": {"name": "get_weather", "arguments": {"city": "Paris"}},
        "id": "call_abc",
        "type": "function",
    }]


def test_ollama_midstream_disconnect_raises_after_visible_partial_text():
    def responder(handler, body):
        _start_stream(handler, "application/x-ndjson")
        _write(handler, json.dumps({
            "message": {"role": "assistant", "content": "partial"}, "done": False,
        }) + "\n")

    with _loopback_server(responder) as (base, _calls):
        provider = OllamaProvider(base_url=base)
        deltas: list[str] = []
        with pytest.raises(ConnectionError):
            provider.chat_turn_stream(
                "demo", [{"role": "user", "content": "hi"}], [],
                timeout=10, on_delta=deltas.append)

    assert deltas == ["partial"]


def test_openai_compatible_midstream_disconnect_raises():
    def responder(handler, body):
        _start_stream(handler, "text/event-stream")
        _write(handler, _sse({"choices": [{"index": 0, "delta": {
            "content": "partial"}}]}))

    with _loopback_server(responder) as (base, _calls):
        provider = OpenAICompatibleProvider("local", "Local", base + "/v1")
        with pytest.raises(ConnectionError):
            provider.chat_turn_stream(
                "demo", [{"role": "user", "content": "hi"}], [], timeout=10)


def test_cancellation_raises_interrupted_error_between_reads():
    cancelled = threading.Event()

    def responder(handler, body):
        _start_stream(handler, "text/event-stream")
        for index in range(100):
            try:
                _write(handler, _sse({"choices": [{"index": 0, "delta": {
                    "content": "tick" + str(index)}}]}))
            except OSError:
                return
            time.sleep(0.01)

    def on_delta(_text):
        cancelled.set()

    with _loopback_server(responder) as (base, _calls):
        provider = OpenAICompatibleProvider("local", "Local", base + "/v1")
        with pytest.raises(InterruptedError):
            provider.chat_turn_stream(
                "demo", [{"role": "user", "content": "hi"}], [], timeout=10,
                on_delta=on_delta, cancelled=cancelled.is_set)


@pytest.mark.parametrize("kind", ["ollama", "openai_compatible"])
def test_permission_is_checked_before_any_network_io(kind):
    def responder(handler, body):
        _start_stream(handler, "application/x-ndjson")
        _write(handler, json.dumps({"message": {"content": "should not run"},
                                    "done": True}) + "\n")

    with _loopback_server(responder) as (base, calls):
        if kind == "ollama":
            provider = OllamaProvider(base_url=base)
        else:
            provider = OpenAICompatibleProvider("api", "API", base + "/v1")
        with pytest.raises(permissions.PermissionDenied):
            provider.chat_turn_stream(
                "gpt-oss:120b-cloud",
                [{"role": "user", "content": "private source"}],
                [],
                timeout=5,
            )
        assert calls == []

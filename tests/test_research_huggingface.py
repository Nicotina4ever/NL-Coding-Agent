"""Hugging Face investigator tests: local fixtures/fake transport, no network/download."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from nl_coding_agent.research import github as gh
from nl_coding_agent.research import huggingface as hf

REPO = Path(__file__).resolve().parents[1]
SHA = "b1b2c3d4e5f60718293a4b5c6d7e8f9012345678"


def response(status=200, payload=None, text=None, headers=None):
    body = text.encode("utf-8") if text is not None else json.dumps(payload).encode("utf-8")
    return gh.HttpResponse(status_code=status, headers=tuple((headers or {}).items()), body=body)


class FakeTransport:
    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def request(self, request):
        self.requests.append(request)
        return self.handler(request)


def model_payload(**overrides):
    data = {
        "id": "acme/tiny-model", "author": "acme", "sha": SHA,
        "lastModified": "2026-01-01T00:00:00Z", "downloads": 10, "likes": 2,
        "pipeline_tag": "text-generation", "library_name": "transformers",
        "tags": ["license:mit", "text-generation", "safetensors"],
        "cardData": {"license": "mit"},
        "gated": False, "private": False,
        "siblings": [{"rfilename": "model.safetensors"},
                     {"rfilename": "tokenizer.json"}],
    }
    data.update(overrides)
    return data


def handler_for(payload=None, files=None, card="## Model Card\n\nExample."):
    payload = payload or model_payload()
    files = files if files is not None else [
        {"path": "model.safetensors", "size": 2 * 1024 ** 3, "type": "file", "oid": "a" * 40},
        {"path": "model-q4_k_m.gguf", "size": 1 * 1024 ** 3, "type": "file", "oid": "b" * 40},
        {"path": "tokenizer.json", "size": 1024, "type": "file", "oid": "c" * 40},
        {"path": "README.md", "size": 20, "type": "file", "oid": "d" * 40},
    ]

    def handler(request):
        url = request.url
        if "/raw/" in url:
            return response(status=200, text=card, headers={"content-type": "text/plain"})
        if "/tree/" in url:
            return response(payload=files)
        if "/api/models?" in url or "/api/datasets?" in url or "/api/spaces?" in url:
            return response(payload=[{"id": "acme/tiny-model", "downloads": 10}])
        if "/api/models" in url and "/revision/" in url:
            return response(payload=payload)
        if url.endswith("/models") or url.endswith("/datasets") or url.endswith("/spaces"):
            return response(payload=[{"id": "acme/tiny-model", "downloads": 10}])
        if "/api/models/acme/tiny-model" in url or "/api/datasets/" in url or "/api/spaces/" in url:
            return response(payload=payload)
        return response(status=404, payload={"error": "not found"})

    return handler


def make_client(handler=None, **kwargs):
    transport = FakeTransport(handler or handler_for())
    return hf.HuggingFaceResearchClient(transport, **kwargs), transport


def test_model_info_metadata_license_gated_and_provenance():
    client, transport = make_client(token="hf-secret")
    result = client.model_info("acme/tiny-model")
    assert result.kind == "models"
    data = result.data
    assert data["sha"] == SHA
    assert data["pipeline_tag"] == "text-generation"
    assert data["tags"] and "license:mit" in data["tags"]
    assert data["cardData"]["license"] == "mit"
    assert data["gated"] is False and data["private"] is False
    assert result.provenance.canonical_url == "https://huggingface.co/models/acme/tiny-model"
    assert result.provenance.sha == SHA
    assert result.provenance.untrusted is True
    assert all(request.method == "GET" for request in transport.requests)
    assert transport.requests[0].header_dict["Authorization"] == "Bearer hf-secret"
    assert "hf-secret" not in repr(client)


def test_model_card_and_files_sizes_formats_estimates():
    client, transport = make_client()
    card = client.model_card("acme/tiny-model", revision=SHA)
    assert card.kind == "model_card" and "Model Card" in card.data["text"]
    files = client.files("acme/tiny-model", revision=SHA)
    payload = files.data
    names = {item["path"] for item in payload["files"]}
    assert "model.safetensors" in names and "model-q4_k_m.gguf" in names
    by_name = {item["path"]: item for item in payload["files"]}
    assert by_name["model.safetensors"]["size"] == 2 * 1024 ** 3
    assert by_name["model.safetensors"]["format"] == ".safetensors"
    assert by_name["model-q4_k_m.gguf"]["quantization"] == "q4_k_m"
    estimate = payload["estimates"]
    assert estimate["estimate"] is True and estimate["measured"] is False
    assert estimate["disk_bytes"] >= estimate["weights_bytes"] > 0
    assert estimate["ram_gb_estimate"] > 0 and estimate["vram_gb_estimate"] > 0
    assert "uncertainty" in estimate and "estimate" in estimate["disclaimer"].lower()
    assert all("/resolve/" not in request.url for request in transport.requests)
    assert not any(request.url.endswith((".safetensors", ".gguf")) for request in transport.requests)


def test_license_info_gated_private_without_acceptance_or_download():
    client, transport = make_client(handler_for(
        payload=model_payload(gated=True, private=True,
                              cardData={"license": "apache-2.0"})))
    info = client.license_info("acme/tiny-model")
    assert info["licenses"] == ["apache-2.0"]
    assert info["gated"] is True and info["private"] is True
    assert info["license_acceptance_performed"] is False
    assert all("accept" not in request.url.lower() for request in transport.requests)
    assert all("/resolve/" not in request.url for request in transport.requests)


def test_search_models_datasets_spaces_and_optional_token():
    client, transport = make_client(token="")
    for method in (client.search_models, client.search_datasets, client.search_spaces):
        result = method("llama", limit=2)
        assert result.kind.startswith("search_")
        assert result.provenance.repo_id.startswith("search/")
    assert "Authorization" not in transport.requests[0].header_dict


def test_typed_errors_and_bounded_responses():
    for status, error in ((401, hf.HuggingFaceAuthError),
                          (403, hf.HuggingFaceGatedError),
                          (429, hf.HuggingFaceRateLimitError),
                          (404, hf.HuggingFaceNotFoundError),
                          (500, hf.HuggingFaceResponseError)):
        client, _ = make_client(lambda request, s=status: response(
            status=s, payload={"error": "x"}), token="hf-secret")
        with pytest.raises(error) as caught:
            client.model_info("acme/tiny-model")
        assert "hf-secret" not in str(caught.value)
    client, _ = make_client(lambda request: response(status=200, text="x" * 5000),
                            max_response_bytes=100)
    with pytest.raises(hf.HuggingFaceResponseError):
        client.model_info("acme/tiny-model")
    client, _ = make_client(lambda request: response(status=200, text="not-json"))
    with pytest.raises(hf.HuggingFaceResponseError):
        client.model_info("acme/tiny-model")


def test_estimates_are_marked_coarse_and_never_measured():
    payload = hf.estimate_resources([
        {"path": "weights.safetensors", "size": 4 * 1024 ** 3},
        {"path": "model-q8_0.gguf", "size": 2 * 1024 ** 3},
    ])
    assert payload["estimate"] is True and payload["measured"] is False
    assert payload["weights_bytes"] == 6 * 1024 ** 3
    assert payload["ram_gb_estimate"] > 0 and payload["vram_gb_estimate"] > 0
    assert payload["quantizations_guess"] == ["q8_0"]
    assert "no checkpoint was retrieved" in payload["disclaimer"]


def test_static_guards_no_network_download_acceptance_or_execution():
    source = (REPO / "nl_coding_agent" / "research" / "huggingface.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("urllib.request", "http.client", "import requests",
                      "from requests", "import socket", "import subprocess",
                      "huggingface_hub", "trust_remote_code", "/resolve/",
                      "/accept", "method=\"post\"", ".post(", ".put(", ".patch(",
                      ".delete("):
        assert forbidden not in lowered, forbidden
    assert "admin" not in lowered
    assert "method=\"GET\"" in source
    assert "estimate" in lowered and "measured" in lowered

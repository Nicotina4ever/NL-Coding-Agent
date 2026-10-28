"""Read-only Hugging Face Hub research investigator (NL-BP-172/207).

Uses the public Hub API contract through an injected transport only. No checkpoint
retrieval, no license acceptance, no code execution, no network library import. All
requests are GETs. Tokens are optional, injected, sent as Bearer headers and never
logged.

Results carry canonical Hub URL + repo id + revision/sha provenance. File sizes and
RAM/VRAM/disk numbers are coarse heuristics derived from file metadata and are
explicitly marked as estimates, never measured provider claims.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.parse import quote, urlencode

from .github import HttpRequest, HttpResponse, HttpTransport

__all__ = [
    "HuggingFaceError", "HuggingFaceTransportError", "HuggingFaceAuthError",
    "HuggingFaceRateLimitError", "HuggingFaceNotFoundError", "HuggingFaceGatedError",
    "HuggingFaceResponseError", "HFProvenance", "HFResult",
    "HuggingFaceResearchClient", "estimate_resources",
]

HUB_BASE = "https://huggingface.co"
API_BASE = HUB_BASE + "/api"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_WEIGHT_SUFFIXES = (".safetensors", ".bin", ".gguf", ".onnx", ".pt", ".pth", ".ckpt")


@dataclass(frozen=True, slots=True)
class HFProvenance:
    hub: str
    repo_id: str
    canonical_url: str
    revision: str | None
    sha: str | None
    fetched_at: str
    untrusted: bool = True

    def __post_init__(self) -> None:
        if self.untrusted is not True:
            raise ValueError("Hugging Face content is always untrusted")
        if self.sha is not None and not _SHA_RE.match(str(self.sha).lower()):
            raise ValueError("Hugging Face sha must be a 40-char commit SHA")
        object.__setattr__(self, "sha", str(self.sha).lower() if self.sha else None)

    def to_dict(self) -> dict:
        return {"provider": "huggingface", "hub": self.hub,
                "repo_id": self.repo_id, "canonical_url": self.canonical_url,
                "revision": self.revision, "sha": self.sha,
                "fetched_at": self.fetched_at, "untrusted": True}


@dataclass(frozen=True, slots=True)
class HFResult:
    kind: str
    data: Any
    provenance: HFProvenance

    def to_dict(self) -> dict:
        return {"kind": self.kind, "data": self.data,
                "provenance": self.provenance.to_dict()}


class HuggingFaceError(Exception):
    code = "huggingface_error"

    def __init__(self, message: str, *, status_code: int | None = None,
                 url: str = "", detail: str = "") -> None:
        super().__init__(str(message))
        self.message = str(message)
        self.status_code = status_code
        self.url = str(url)
        self.detail = str(detail)

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message,
                "status_code": self.status_code, "url": self.url}


class HuggingFaceTransportError(HuggingFaceError):
    code = "huggingface_transport_error"


class HuggingFaceAuthError(HuggingFaceError):
    code = "huggingface_auth_error"


class HuggingFaceRateLimitError(HuggingFaceError):
    code = "huggingface_rate_limit"


class HuggingFaceNotFoundError(HuggingFaceError):
    code = "huggingface_not_found"


class HuggingFaceGatedError(HuggingFaceError):
    code = "huggingface_gated"


class HuggingFaceResponseError(HuggingFaceError):
    code = "huggingface_response_error"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _guess_quantization(path: str) -> str | None:
    lower = str(path or "").lower()
    match = re.search(r"(q\d(?:_[a-z0-9]+)*|f16|bf16|fp16|int8|int4)", lower)
    return match.group(1) if match else None


def _file_format(path: str) -> str:
    suffix = "." + str(path).rsplit(".", 1)[-1].lower() if "." in str(path) else ""
    return suffix


def estimate_resources(files: list[Mapping[str, Any]],
                       *, parameters_billions: float | None = None) -> dict:
    """Coarse heuristic estimates from file metadata only. Never a measured claim."""
    sizes = [int(item.get("size") or 0) for item in files
             if isinstance(item, Mapping) and str(item.get("path") or "")
             .lower().endswith(_WEIGHT_SUFFIXES)]
    weights_bytes = sum(max(0, size) for size in sizes)
    disk_bytes = sum(max(0, int(item.get("size") or 0)) for item in files
                     if isinstance(item, Mapping))
    if weights_bytes:
        ram_gb = weights_bytes / (1024 ** 3) * 1.2
        vram_gb = weights_bytes / (1024 ** 3) * 1.1
    elif parameters_billions:
        ram_gb = float(parameters_billions) * 2.0
        vram_gb = float(parameters_billions) * 2.0
    else:
        ram_gb = vram_gb = 0.0
    quantizations = sorted({
        guess for guess in (_guess_quantization(str(item.get("path") or ""))
                            for item in files if isinstance(item, Mapping))
        if guess
    })
    return {
        "estimate": True,
        "measured": False,
        "method": "coarse file-size heuristic; not provider-measured",
        "uncertainty": "coarse, at least +/-50%; actual RAM/VRAM depends on runtime, "
                       "quantization, context and hardware",
        "disk_bytes": disk_bytes,
        "weights_bytes": weights_bytes,
        "ram_gb_estimate": round(ram_gb, 2),
        "vram_gb_estimate": round(vram_gb, 2),
        "quantizations_guess": quantizations,
        "disclaimer": "estimates only; no checkpoint was retrieved or executed",
    }


class HuggingFaceResearchClient:
    def __init__(self, transport: HttpTransport, *, token: str | None = None,
                 env: Mapping[str, str] | None = None, api_base: str = API_BASE,
                 hub_base: str = HUB_BASE, max_items: int = 100,
                 max_response_bytes: int = 2_000_000, timeout_s: float = 15.0) -> None:
        if transport is None:
            raise ValueError("HuggingFaceResearchClient requires an injected transport")
        environment = env if env is not None else os.environ
        self._token = str(token if token is not None
                          else environment.get("HF_TOKEN")
                          or environment.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
        self._transport = transport
        self.api_base = str(api_base).rstrip("/")
        self.hub_base = str(hub_base).rstrip("/")
        self.max_items = max(1, int(max_items))
        self.max_response_bytes = max(1, int(max_response_bytes))
        self.timeout_s = float(timeout_s)

    def __repr__(self) -> str:
        return "HuggingFaceResearchClient(api_base=" + repr(self.api_base) + ", token=REDACTED)"

    def _headers(self, accept: str = "application/json") -> tuple[tuple[str, str], ...]:
        headers = {"Accept": accept, "User-Agent": "NL-Coding-Agent-Research/0.1"}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        return tuple(sorted(headers.items()))

    def _request(self, path: str, params: Mapping[str, Any] | None = None,
                 accept: str = "application/json") -> HttpResponse:
        url = self.api_base + "/" + str(path).lstrip("/")
        if params:
            query = urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url += "?" + query
        request = HttpRequest(method="GET", url=url, headers=self._headers(accept),
                              timeout_s=self.timeout_s, max_bytes=self.max_response_bytes)
        try:
            response = self._transport.request(request)
        except HuggingFaceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HuggingFaceTransportError("Hugging Face transport failed: " + str(exc),
                                            url=url) from exc
        if not isinstance(response, HttpResponse):
            raise HuggingFaceResponseError("transport returned an invalid response", url=url)
        status = int(response.status_code)
        if status == 401:
            raise HuggingFaceAuthError("Hugging Face authentication failed", status_code=status, url=url)
        if status == 429:
            raise HuggingFaceRateLimitError("Hugging Face rate limit exceeded",
                                             status_code=status, url=url)
        if status == 404:
            raise HuggingFaceNotFoundError("Hugging Face resource not found",
                                            status_code=status, url=url)
        if status in (401, 403):
            raise HuggingFaceGatedError(
                "Hugging Face resource is gated/private or access is forbidden",
                status_code=status, url=url)
        if status >= 400:
            raise HuggingFaceResponseError("Hugging Face API returned HTTP " + str(status),
                                            status_code=status, url=url)
        if len(response.body or b"") > self.max_response_bytes:
            raise HuggingFaceResponseError("Hugging Face response exceeds the size budget",
                                            status_code=status, url=url)
        return response

    def _json(self, path: str, params: Mapping[str, Any] | None = None):
        response = self._request(path, params)
        try:
            return json.loads((response.body or b"{}").decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise HuggingFaceResponseError("invalid JSON in Hugging Face response",
                                            status_code=response.status_code,
                                            url=self.api_base + "/" + path) from exc

    def _provenance(self, kind: str, repo_id: str, data: Mapping,
                    revision: str | None = None) -> HFProvenance:
        sha = str(data.get("sha") or "") if isinstance(data, Mapping) else ""
        if not _SHA_RE.match(sha.lower()):
            sha = None
        return HFProvenance(hub="huggingface", repo_id=repo_id,
                            canonical_url=self.hub_base + "/" + kind + "/" + repo_id,
                            revision=revision or sha,
                            sha=sha.lower() if sha else None,
                            fetched_at=_iso_now())

    def _repo_result(self, kind: str, repo_id: str, data: Mapping,
                     revision: str | None = None) -> HFResult:
        return HFResult(kind, dict(data or {}),
                        self._provenance(kind, repo_id, data, revision))

    # --------------------------------------------------------------- searches
    def search_models(self, query: str, *, limit: int = 20) -> HFResult:
        return self._search("models", query, limit)

    def search_datasets(self, query: str, *, limit: int = 20) -> HFResult:
        return self._search("datasets", query, limit)

    def search_spaces(self, query: str, *, limit: int = 20) -> HFResult:
        return self._search("spaces", query, limit)

    def _search(self, kind: str, query: str, limit: int) -> HFResult:
        data = self._json(kind, {"search": str(query), "limit": min(limit, self.max_items)})
        items = list(data if isinstance(data, list) else (data or {}).get("items") or [])
        items = items[: min(limit, self.max_items)]
        provenance = HFProvenance("huggingface", "search/" + kind,
                                  self.hub_base + "/" + kind + "?search=" + quote(str(query)),
                                  None, None, _iso_now())
        return HFResult("search_" + kind, items, provenance)

    # ------------------------------------------------------------- repo info
    def model_info(self, repo_id: str, *, revision: str | None = None) -> HFResult:
        return self._repo_info("models", repo_id, revision)

    def dataset_info(self, repo_id: str, *, revision: str | None = None) -> HFResult:
        return self._repo_info("datasets", repo_id, revision)

    def space_info(self, repo_id: str, *, revision: str | None = None) -> HFResult:
        return self._repo_info("spaces", repo_id, revision)

    def _repo_info(self, kind: str, repo_id: str, revision: str | None) -> HFResult:
        path = kind + "/" + repo_id
        if revision:
            path += "/revision/" + quote(str(revision), safe="")
        data = self._json(path)
        if not isinstance(data, dict):
            raise HuggingFaceResponseError("expected a JSON object from Hugging Face")
        return self._repo_result(kind, repo_id, data, revision)

    def model_card(self, repo_id: str, *, revision: str | None = None) -> HFResult:
        path = "models/" + repo_id + "/raw/" + quote(str(revision or "main"), safe="") + "/README.md"
        response = self._request(path, accept="text/plain")
        text = (response.body or b"").decode("utf-8", errors="replace")
        data = {"repo_id": repo_id, "revision": revision or "main",
                "text": text, "charset": response.header("content-type")}
        return HFResult("model_card", data,
                        HFProvenance("huggingface", repo_id,
                                     self.hub_base + "/models/" + repo_id,
                                     revision or "main", None, _iso_now()))

    def files(self, repo_id: str, *, revision: str | None = None) -> HFResult:
        path = "models/" + repo_id + "/tree/" + quote(str(revision or "main"), safe="")
        data = self._json(path, {"recursive": "true"})
        items = list(data if isinstance(data, list) else (data or {}).get("siblings") or [])
        normalized = [{"path": str(item.get("path") or item.get("rfilename") or ""),
                       "size": int(item.get("size") or 0),
                       "type": str(item.get("type") or "file"),
                       "oid": str(item.get("oid") or item.get("lfs", {}).get("oid") or ""),
                       "format": _file_format(str(item.get("path") or item.get("rfilename") or "")),
                       "quantization": _guess_quantization(str(item.get("path") or item.get("rfilename") or ""))}
                      for item in items if isinstance(item, Mapping)]
        provenance = HFProvenance("huggingface", repo_id,
                                  self.hub_base + "/models/" + repo_id,
                                  revision or "main", None, _iso_now())
        payload = {"repo_id": repo_id, "revision": revision or "main", "files": normalized,
                   "estimates": estimate_resources(normalized)}
        return HFResult("files", payload, provenance)

    def license_info(self, repo_id: str) -> dict:
        info = self.model_info(repo_id)
        data = info.data or {}
        card = data.get("cardData") or {}
        tags = data.get("tags") or []
        licenses = card.get("license") or [tag[8:] for tag in tags
                                           if str(tag).startswith("license:")]
        if isinstance(licenses, str):
            licenses = [licenses]
        return {"repo_id": repo_id, "licenses": list(licenses or []),
                "gated": bool(data.get("gated")), "private": bool(data.get("private")),
                "license_acceptance_performed": False,
                "provenance": info.provenance.to_dict()}

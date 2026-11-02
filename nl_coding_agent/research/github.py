"""Read-only GitHub research investigator (NL-BP-171/172/207).

Official REST contract through an injected transport only. No network library is
imported, no repository copy is made, no code is executed and no write/mutation
endpoint is exposed: every request is a GET. Optional tokens come from injected
configuration/environment, are sent only as an Authorization header, and are never
logged or included in errors/provenance.

Every result carries a provenance record: canonical API URL, repository full name,
requested ref and the resolved commit SHA (when resolvable), fetch timestamp and the
literal untrusted marker. Pagination and response sizes are bounded; auth,
rate-limit, not-found and response failures use typed exceptions.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.parse import quote, urlencode

__all__ = [
    "HttpRequest", "HttpResponse", "HttpTransport", "GitHubError",
    "GitHubTransportError", "GitHubAuthError", "GitHubRateLimitError",
    "GitHubNotFoundError", "GitHubResponseError", "GitHubProvenance",
    "GitHubResult", "GitHubResearchClient",
]

DEFAULT_API_BASE = "https://api.github.com"
DEFAULT_USER_AGENT = "NL-Coding-Agent-Research/0.1 (read-only; injected transport)"
API_VERSION = "2022-11-28"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    timeout_s: float = 15.0
    max_bytes: int = 2_000_000

    @property
    def header_dict(self) -> dict[str, str]:
        return {name: value for name, value in self.headers}


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes = b""

    def header(self, name: str, default: str | None = None) -> str | None:
        wanted = str(name).strip().lower()
        for key, value in self.headers:
            if key.strip().lower() == wanted:
                return value
        return default


class HttpTransport(Protocol):
    """Injected HTTP transport (tests provide a scripted fake)."""

    def request(self, request: HttpRequest) -> HttpResponse:
        ...


class GitHubError(Exception):
    """Base typed GitHub investigator error; never contains a token."""

    code = "github_error"

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


class GitHubTransportError(GitHubError):
    code = "github_transport_error"


class GitHubAuthError(GitHubError):
    code = "github_auth_error"


class GitHubRateLimitError(GitHubError):
    code = "github_rate_limit"

    def __init__(self, message: str, *, retry_after_s: float | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after_s = retry_after_s

    def to_dict(self) -> dict:
        return {**super().to_dict(), "retry_after_s": self.retry_after_s}


class GitHubNotFoundError(GitHubError):
    code = "github_not_found"


class GitHubResponseError(GitHubError):
    code = "github_response_error"


@dataclass(frozen=True, slots=True)
class GitHubProvenance:
    repo: str
    canonical_url: str
    kind: str
    requested_ref: str | None
    resolved_commit_sha: str | None
    fetched_at: str
    untrusted: bool = True

    def __post_init__(self) -> None:
        if not self.repo or "/" not in self.repo:
            raise ValueError("GitHub provenance requires owner/repo")
        if self.untrusted is not True:
            raise ValueError("GitHub content is always untrusted")
        if self.resolved_commit_sha is not None and not _SHA_RE.match(
                str(self.resolved_commit_sha).lower()):
            raise ValueError("resolved_commit_sha must be a 40-char commit SHA")
        object.__setattr__(self, "resolved_commit_sha",
                           str(self.resolved_commit_sha).lower()
                           if self.resolved_commit_sha else None)

    def to_dict(self) -> dict:
        return {"provider": "github", "repo": self.repo,
                "canonical_url": self.canonical_url, "kind": self.kind,
                "requested_ref": self.requested_ref,
                "resolved_commit_sha": self.resolved_commit_sha,
                "fetched_at": self.fetched_at, "untrusted": True}


@dataclass(frozen=True, slots=True)
class GitHubResult:
    kind: str
    data: Any
    provenance: GitHubProvenance

    def to_dict(self) -> dict:
        return {"kind": self.kind, "data": self.data,
                "provenance": self.provenance.to_dict()}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_repo(full_name: str) -> str:
    text = str(full_name or "").strip().strip("/")
    parts = text.split("/")
    if (len(parts) != 2 or
            any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)):
        raise ValueError("repository must be owner/name")
    return parts[0] + "/" + parts[1]


def _encoded_path(path: str, *, allow_empty: bool) -> str:
    parts = str(path or "").replace("\\", "/").strip("/").split("/")
    if parts == [""]:
        parts = []
    if (not allow_empty and not parts) or any(
            not part or part in (".", "..") or "\x00" in part for part in parts):
        raise ValueError("repository path is invalid")
    return "/".join(quote(part, safe="") for part in parts)


def _header(headers: tuple[tuple[str, str], ...], name: str) -> str | None:
    wanted = name.strip().lower()
    for key, value in headers:
        if key.strip().lower() == wanted:
            return value
    return None


class GitHubResearchClient:
    """Read-only GitHub REST investigator using an injected transport."""

    def __init__(self, transport: HttpTransport, *, token: str | None = None,
                 api_base: str = DEFAULT_API_BASE,
                 env: Mapping[str, str] | None = None, user_agent: str = DEFAULT_USER_AGENT,
                 max_pages: int = 3, max_items: int = 100,
                 max_response_bytes: int = 2_000_000, timeout_s: float = 15.0) -> None:
        if transport is None:
            raise ValueError("GitHubResearchClient requires an injected transport")
        self._transport = transport
        environment = env if env is not None else os.environ
        self._token = str(token if token is not None
                          else environment.get("GITHUB_TOKEN") or "").strip()
        self.api_base = str(api_base).rstrip("/")
        self.user_agent = str(user_agent)
        self.max_pages = max(1, int(max_pages))
        self.max_items = max(1, int(max_items))
        self.max_response_bytes = max(1, int(max_response_bytes))
        self.timeout_s = float(timeout_s)
        self._commit_cache: dict[tuple[str, str | None], str | None] = {}

    def __repr__(self) -> str:
        return "GitHubResearchClient(api_base=" + repr(self.api_base) + ", token=REDACTED)"

    def _url(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        url = self.api_base + "/" + str(path).lstrip("/")
        if params:
            query = urlencode({key: value for key, value in params.items()
                               if value is not None})
            if query:
                url += "?" + query
        return url

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": self.user_agent,
        }
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        return headers

    def _request(self, path: str, params: Mapping[str, Any] | None = None) -> HttpResponse:
        url = self._url(path, params)
        request = HttpRequest(method="GET", url=url,
                              headers=tuple(sorted(self._headers().items())),
                              timeout_s=self.timeout_s,
                              max_bytes=self.max_response_bytes)
        try:
            response = self._transport.request(request)
        except GitHubError:
            raise
        except Exception as exc:  # noqa: BLE001 - typed transport failure
            raise GitHubTransportError("GitHub transport failed: " + str(exc),
                                       url=url) from exc
        if not isinstance(response, HttpResponse):
            raise GitHubResponseError("transport returned an invalid response", url=url)
        status = int(response.status_code)
        if status == 401:
            raise GitHubAuthError("GitHub authentication failed (token missing/invalid)",
                                  status_code=status, url=url)
        if status in (429,) or (status == 403 and (
                response.header("x-ratelimit-remaining") == "0"
                or response.header("retry-after") is not None)):
            retry = response.header("retry-after")
            try:
                retry_after = float(retry) if retry is not None else None
            except ValueError:
                retry_after = None
            raise GitHubRateLimitError("GitHub API rate limit exceeded",
                                       retry_after_s=retry_after,
                                       status_code=status, url=url)
        if status == 404:
            raise GitHubNotFoundError("GitHub resource not found", status_code=status, url=url)
        if status >= 400:
            raise GitHubResponseError("GitHub API returned HTTP " + str(status),
                                      status_code=status, url=url)
        if len(response.body or b"") > self.max_response_bytes:
            raise GitHubResponseError("GitHub response exceeds the size budget",
                                      status_code=status, url=url)
        return response

    def _json(self, path: str, params: Mapping[str, Any] | None = None):
        response = self._request(path, params)
        try:
            return json.loads((response.body or b"{}").decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise GitHubResponseError("invalid JSON in GitHub response",
                                      status_code=response.status_code,
                                      url=self._url(path, params)) from exc

    def _resolve_commit(self, repo: str, ref: str | None) -> str | None:
        key = (repo, ref)
        if key in self._commit_cache:
            return self._commit_cache[key]
        resolved = str(ref).lower() if ref and _SHA_RE.match(str(ref).lower()) else None
        if resolved is None:
            try:
                if ref:
                    data = self._json("repos/" + repo + "/commits/"
                                      + quote(str(ref), safe=""), {"per_page": 1})
                else:
                    data = self._json("repos/" + repo + "/commits", {"per_page": 1})
                if isinstance(data, dict):
                    sha = str(data.get("sha") or "")
                elif isinstance(data, list) and data and isinstance(data[0], dict):
                    sha = str(data[0].get("sha") or "")
                else:
                    sha = ""
                if _SHA_RE.match(sha.lower()):
                    resolved = sha.lower()
            except Exception:  # noqa: BLE001 - resolution is best-effort provenance
                resolved = None
        self._commit_cache[key] = resolved
        return resolved

    def _provenance(self, repo: str, kind: str, ref: str | None = None,
                    resolved: str | None = None) -> GitHubProvenance:
        sha = self._resolve_commit(repo, ref) if resolved is None else resolved
        return GitHubProvenance(repo=repo, canonical_url=self.api_base + "/repos/" + repo,
                                kind=kind, requested_ref=ref,
                                resolved_commit_sha=sha, fetched_at=_iso_now())

    def _result(self, repo: str, kind: str, data: Any, ref: str | None = None,
                resolved: str | None = None) -> GitHubResult:
        return GitHubResult(kind, data, self._provenance(repo, kind, ref, resolved))

    # ------------------------------------------------------------- repository
    def repository(self, full_name: str) -> GitHubResult:
        repo = _parse_repo(full_name)
        data = self._json("repos/" + repo)
        return self._result(repo, "repository", data, None)

    def readme(self, full_name: str, *, ref: str | None = None) -> GitHubResult:
        repo = _parse_repo(full_name)
        data = self._json("repos/" + repo + "/readme", {"ref": ref} if ref else None)
        text = self._decode_content(data)
        payload = {"name": data.get("name"), "path": data.get("path"),
                   "sha": data.get("sha"), "text": text}
        return self._result(repo, "readme", payload, ref)

    def license_info(self, full_name: str, *, ref: str | None = None) -> GitHubResult:
        repo = _parse_repo(full_name)
        data = self._json("repos/" + repo + "/license", {"ref": ref} if ref else None)
        payload = {"name": data.get("name"), "path": data.get("path"),
                   "sha": data.get("sha"), "text": self._decode_content(data)}
        return self._result(repo, "license", payload, ref)

    def branches(self, full_name: str, *, limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        items = self._paginate("repos/" + repo + "/branches", limit=limit)
        return self._result(repo, "branches", items)

    def tags(self, full_name: str, *, limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        items = self._paginate("repos/" + repo + "/tags", limit=limit)
        return self._result(repo, "tags", items)

    def commits(self, full_name: str, *, ref: str | None = None,
                limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        params = {"sha": ref} if ref else {}
        items = self._paginate("repos/" + repo + "/commits", params, limit=limit)
        first_sha = items[0].get("sha") if items and isinstance(items[0], dict) else None
        return self._result(repo, "commits", items, ref, resolved=first_sha)

    def issues(self, full_name: str, *, state: str = "open",
               limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        items = self._paginate("repos/" + repo + "/issues",
                               {"state": state}, limit=limit)
        return self._result(repo, "issues", items)

    def issue_comments(self, full_name: str, number: int,
                       *, limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        items = self._paginate("repos/" + repo + "/issues/" + str(int(number)) + "/comments",
                               limit=limit)
        return self._result(repo, "issue_comments", items)

    def pull_requests(self, full_name: str, *, state: str = "open",
                      limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        items = self._paginate("repos/" + repo + "/pulls", {"state": state}, limit=limit)
        return self._result(repo, "pull_requests", items)

    def pull_reviews(self, full_name: str, number: int,
                     *, limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        items = self._paginate("repos/" + repo + "/pulls/" + str(int(number)) + "/reviews",
                               limit=limit)
        return self._result(repo, "pull_reviews", items)

    def releases(self, full_name: str, *, limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        items = self._paginate("repos/" + repo + "/releases", limit=limit)
        return self._result(repo, "releases", items)

    def workflows(self, full_name: str, *, limit: int = 20) -> GitHubResult:
        repo = _parse_repo(full_name)
        data = self._json("repos/" + repo + "/actions/workflows")
        items = list((data or {}).get("workflows") or [])[: min(limit, self.max_items)]
        return self._result(repo, "workflows", items)

    def contents(self, full_name: str, *, path: str = "", ref: str | None = None,
                 limit: int = 40) -> GitHubResult:
        repo = _parse_repo(full_name)
        safe_path = _encoded_path(path, allow_empty=True)
        endpoint = "repos/" + repo + "/contents"
        if safe_path:
            endpoint += "/" + safe_path
        data = self._json(endpoint, {"ref": ref} if ref else None)
        if isinstance(data, list):
            items = [{
                key: item.get(key) for key in
                ("name", "path", "type", "size", "sha", "download_url")
                if item.get(key) is not None
            } for item in data[: min(max(1, int(limit)), self.max_items)]
                if isinstance(item, dict)]
            payload = {"items": items, "truncated": len(data) > len(items)}
        elif isinstance(data, dict):
            payload = {key: data.get(key) for key in
                       ("name", "path", "type", "size", "sha", "download_url")
                       if data.get(key) is not None}
        else:
            raise GitHubResponseError("unexpected GitHub contents response",
                                      url=self._url(endpoint))
        return self._result(repo, "contents", payload, ref)

    def file_contents(self, full_name: str, path: str, *,
                      ref: str | None = None) -> GitHubResult:
        repo = _parse_repo(full_name)
        safe_path = _encoded_path(path, allow_empty=False)
        data = self._json("repos/" + repo + "/contents/" + safe_path,
                          {"ref": ref} if ref else None)
        payload = {"path": data.get("path"), "sha": data.get("sha"),
                   "size": data.get("size"), "text": self._decode_content(data)}
        return self._result(repo, "file_contents", payload, ref)

    def search_repositories(self, query: str, *, limit: int = 20) -> GitHubResult:
        data = self._json("search/repositories", {"q": str(query), "per_page": min(limit, 100)})
        items = list((data or {}).get("items") or [])[: min(limit, self.max_items)]
        provenance = GitHubProvenance(repo="search/repositories",
                                      canonical_url=self.api_base + "/search/repositories",
                                      kind="search_repositories", requested_ref=None,
                                      resolved_commit_sha=None, fetched_at=_iso_now())
        return GitHubResult("search_repositories", items, provenance)

    # --------------------------------------------------------------- helpers
    def _paginate(self, path: str, params: Mapping[str, Any] | None = None,
                  *, limit: int = 20) -> list:
        items: list = []
        page_params = dict(params or {})
        per_page = min(max(1, int(limit)), 100)
        page_params.setdefault("per_page", per_page)
        for _ in range(self.max_pages):
            data = self._json(path, page_params)
            if not isinstance(data, list):
                raise GitHubResponseError("expected a JSON list from GitHub",
                                          url=self._url(path, page_params))
            items.extend(data)
            if len(items) >= limit or len(data) < per_page:
                break
            page = int(page_params.get("page") or 1) + 1
            page_params["page"] = page
        return items[: min(limit, self.max_items)]

    @staticmethod
    def _decode_content(data: Mapping[str, Any]) -> str:
        if not isinstance(data, Mapping):
            return ""
        content = data.get("content")
        if not content:
            return str(data.get("text") or "")
        try:
            raw = base64.b64decode(str(content).replace("\n", ""), validate=False)
        except Exception:  # noqa: BLE001 - malformed content is a response error
            return ""
        return raw.decode("utf-8", errors="replace")

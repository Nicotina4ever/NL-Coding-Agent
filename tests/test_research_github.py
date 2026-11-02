"""GitHub investigator tests: injected fake transport only, no network."""
from __future__ import annotations
import base64
import json
from pathlib import Path

import pytest

from nl_coding_agent.research import github as gh

REPO = Path(__file__).resolve().parents[1]
SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"


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


class RepoHandler:
    def __init__(self):
        self.calls = []

    def __call__(self, request):
        url = request.url
        self.calls.append(url)
        if "/readme" in url:
            content = base64.b64encode(b"# Demo README").decode()
            return response(payload={"name": "README.md", "path": "README.md",
                                     "sha": "readme-blob", "content": content})
        if "/license" in url:
            return response(payload={"name": "MIT", "path": "LICENSE",
                                     "sha": "license-blob",
                                     "content": base64.b64encode(b"MIT text").decode()})
        if "/contents/" in url:
            return response(payload={"path": "src/app.py", "sha": "blob-sha", "size": 9,
                                     "content": base64.b64encode(b"x = 1\n").decode()})
        if url.split("?", 1)[0].endswith("/contents"):
            return response(payload=[
                {"name": "README.md", "path": "README.md", "type": "file", "size": 20},
                {"name": "src", "path": "src", "type": "dir"},
            ])
        if "/branches" in url:
            return response(payload=[{"name": "main", "commit": {"sha": SHA}}])
        if "/tags" in url:
            return response(payload=[{"name": "v1", "commit": {"sha": SHA}}])
        if "/issues/" in url and "/comments" in url:
            return response(payload=[{"id": 9, "body": "a comment"}])
        if "/issues" in url:
            return response(payload=[{"number": 1, "title": "issue"}])
        if "/pulls/" in url and "/reviews" in url:
            return response(payload=[{"id": 7, "state": "APPROVED"}])
        if "/pulls" in url:
            return response(payload=[{"number": 2, "title": "pr"}])
        if "/releases" in url:
            return response(payload=[{"tag_name": "v1", "body": "notes"}])
        if "/actions/workflows" in url:
            return response(payload={"workflows": [{"id": 3, "name": "ci"}]})
        if "/search/repositories" in url:
            return response(payload={"total_count": 1,
                                     "items": [{"full_name": "acme/demo"}]})
        if "/commits" in url:
            return response(payload=[{"sha": SHA, "commit": {"message": "initial"}}])
        if url.rstrip("/").endswith("/repos/acme/demo"):
            return response(payload={"full_name": "acme/demo", "default_branch": "main",
                                     "license": {"spdx_id": "MIT"}, "stars": 5})
        return response(status=404, payload={"message": "not found"})


def make_client(handler=None, **kwargs):
    transport = FakeTransport(handler or RepoHandler())
    return gh.GitHubResearchClient(transport, **kwargs), transport


def test_repository_metadata_provenance_and_auth_header():
    client, transport = make_client(token="secret-token")
    result = client.repository("acme/demo")
    assert result.kind == "repository" and result.data["default_branch"] == "main"
    provenance = result.provenance
    assert provenance.repo == "acme/demo"
    assert provenance.canonical_url == "https://api.github.com/repos/acme/demo"
    assert provenance.resolved_commit_sha == SHA
    assert provenance.untrusted is True
    assert all(item.method == "GET" for item in transport.requests)
    assert transport.requests[0].header_dict["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in repr(client)
    assert "secret-token" not in json.dumps(result.to_dict())


def test_readme_license_contents_and_ref_pinning():
    client, transport = make_client()
    readme = client.readme("acme/demo", ref="v1.0.0")
    assert readme.data["text"] == "# Demo README"
    assert readme.provenance.requested_ref == "v1.0.0"
    assert readme.provenance.resolved_commit_sha == SHA
    license_info = client.license_info("acme/demo", ref="v1.0.0")
    assert license_info.data["text"] == "MIT text"
    contents = client.file_contents("acme/demo", "src/app.py", ref="v1.0.0")
    assert contents.data["text"] == "x = 1\n"
    assert contents.data["sha"] == "blob-sha"
    assert contents.provenance.requested_ref == "v1.0.0"
    assert any("ref=v1.0.0" in request.url for request in transport.requests)


def test_repository_contents_are_bounded_and_paths_reject_traversal():
    client, transport = make_client(max_items=1)
    result = client.contents("acme/demo", limit=10)
    assert result.kind == "contents"
    assert result.data["items"] == [{
        "name": "README.md", "path": "README.md", "type": "file", "size": 20
    }]
    assert result.data["truncated"] is True
    assert transport.requests[0].method == "GET"
    with pytest.raises(ValueError, match="repository path is invalid"):
        client.contents("acme/demo", path="../other")
    with pytest.raises(ValueError, match="repository must be owner/name"):
        client.repository("acme/demo?format=evil")


def test_pagination_is_bounded_and_read_only():
    pages = {}

    def handler(request):
        if "/commits" in request.url:
            return response(payload=[{"sha": SHA}])
        if "/branches" in request.url:
            page = "1" if "page=1" not in request.url and "page=" not in request.url else request.url.split("page=")[1].split("&")[0]
            pages[page] = pages.get(page, 0) + 1
            return response(payload=[{"name": "b%d" % i} for i in range(3)])
        return response(status=404)

    client, transport = make_client(handler, max_pages=2, max_items=4)
    result = client.branches("acme/demo", limit=4)
    assert result.kind == "branches"
    assert len(result.data) <= 4
    branch_requests = [r for r in transport.requests if "/branches" in r.url]
    assert 1 <= len(branch_requests) <= 2
    assert all(r.method == "GET" for r in transport.requests)


def test_typed_auth_rate_limit_and_not_found_errors_never_leak_token():
    cases = [
        (401, {}, gh.GitHubAuthError),
        (403, {"x-ratelimit-remaining": "0"}, gh.GitHubRateLimitError),
        (429, {}, gh.GitHubRateLimitError),
        (404, {}, gh.GitHubNotFoundError),
        (500, {}, gh.GitHubResponseError),
    ]
    for status, headers, error_type in cases:
        client, _transport = make_client(lambda request, s=status, h=headers: response(
            status=s, payload={"message": "error"}, headers=h), token="super-secret")
        with pytest.raises(error_type) as caught:
            client.repository("acme/demo")
        assert str(caught.value).find("super-secret") == -1
        assert "super-secret" not in json.dumps(caught.value.to_dict())


def test_bounded_response_size_and_invalid_json_are_typed():
    client, _ = make_client(lambda request: response(status=200, text="x" * 5000),
                            max_response_bytes=100)
    with pytest.raises(gh.GitHubResponseError):
        client.repository("acme/demo")
    client, _ = make_client(lambda request: response(status=200, text="not-json"))
    with pytest.raises(gh.GitHubResponseError):
        client.repository("acme/demo")


def test_issue_pr_release_workflow_search_surfaces():
    client, _ = make_client()
    assert client.issues("acme/demo").data[0]["number"] == 1
    assert client.issue_comments("acme/demo", 1).data[0]["body"] == "a comment"
    assert client.pull_requests("acme/demo").data[0]["number"] == 2
    assert client.pull_reviews("acme/demo", 2).data[0]["state"] == "APPROVED"
    assert client.releases("acme/demo").data[0]["tag_name"] == "v1"
    assert client.workflows("acme/demo").data[0]["name"] == "ci"
    search = client.search_repositories("language:python", limit=3)
    assert search.kind == "search_repositories" and search.data[0]["full_name"] == "acme/demo"


def test_optional_token_absent_and_transport_failure_typed():
    client, transport = make_client(token="")
    client.repository("acme/demo")
    assert "Authorization" not in transport.requests[0].header_dict
    client, _ = make_client(lambda request: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(gh.GitHubTransportError):
        client.repository("acme/demo")


def test_static_guards_no_network_write_or_execution():
    source = (REPO / "nl_coding_agent" / "research" / "github.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("urllib.request", "http.client", "import requests",
                      "from requests", "import socket", "import subprocess",
                      "import git", "method=\"post\"", "method='post'",
                      ".post(", ".put(", ".patch(", ".delete(", "git clone",
                      "git push"):
        assert forbidden not in lowered, forbidden
    assert "method=\"GET\"" in source
    assert "Authorization" in source and "REDACTED" in source

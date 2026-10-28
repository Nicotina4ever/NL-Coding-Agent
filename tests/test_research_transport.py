"""Tests for the explicit stdlib research HTTP transport (fake opener only)."""
from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.research.github import HttpRequest  # noqa: E402
from nl_coding_agent.research.transport import (  # noqa: E402
    StdlibHttpTransport,
    TransportLimitError,
    TransportPermissionError,
    TransportRequestError,
)


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b"", final_url="https://example.com/"):
        self.status = status
        self.code = status
        self.headers = dict(headers or {"Content-Type": "text/html"})
        self._body = body
        self.final_url = final_url
        self.closed = False

    def read(self, amount=-1):
        data = self._body if amount is None or amount < 0 else self._body[:amount]
        self._body = self._body[amount:] if amount and amount > 0 else b""
        return data

    def close(self):
        self.closed = True

    def geturl(self):
        return self.final_url


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append({"request": request, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return self.response


def transport(gate=None, opener=None, **kwargs):
    gate = gate or (lambda url: True)
    return StdlibHttpTransport(gate, opener=opener or FakeOpener(FakeResponse()), **kwargs)


class TransportTests(unittest.TestCase):
    def test_requires_explicit_permission_gate_and_valid_config(self):
        with self.assertRaises(ValueError):
            StdlibHttpTransport(None)
        with self.assertRaises(ValueError):
            StdlibHttpTransport(lambda url: True, allowed_schemes=("ftp",))
        with self.assertRaises(ValueError):
            StdlibHttpTransport(lambda url: True, timeout_s=0)
        with self.assertRaises(ValueError):
            StdlibHttpTransport(lambda url: True, max_bytes=0)
        instance = transport()
        self.assertIn("StdlibHttpTransport", repr(instance))
        self.assertNotIn("secret", repr(instance))

    def test_success_passes_request_and_returns_bounded_response(self):
        calls = []
        opener = FakeOpener(FakeResponse(status=200, headers={
            "Content-Type": "text/html", "ETag": "abc", "Set-Cookie": "must-not-leak"},
            body=b"hello transport"))
        instance = StdlibHttpTransport(lambda url: calls.append(url) or True,
                                       opener=opener, max_bytes=100)
        response = instance.request(HttpRequest(method="GET",
                                               url="https://example.com/page?q=1#frag",
                                               headers=(("Accept", "text/html"),),
                                               timeout_s=3.0, max_bytes=50))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"hello transport")
        self.assertEqual(response.header("etag"), "abc")
        self.assertIsNone(response.header("set-cookie"))
        self.assertEqual(calls, ["https://example.com/page?q=1"])
        self.assertEqual(len(opener.calls), 1)
        request_obj = opener.calls[0]["request"]
        self.assertEqual(request_obj.full_url, "https://example.com/page?q=1")
        self.assertEqual(opener.calls[0]["timeout"], 3.0)
        self.assertEqual(request_obj.get_method(), "GET")

    def test_permission_gate_denies_before_any_io(self):
        opener = FakeOpener()
        denied = StdlibHttpTransport(lambda url: False, opener=opener)
        with self.assertRaises(TransportPermissionError):
            denied.request(HttpRequest(method="GET", url="https://example.com/"))
        self.assertEqual(opener.calls, [])

        def boom(url):
            raise RuntimeError("gate exploded")

        op = FakeOpener()
        with self.assertRaises(TransportPermissionError):
            StdlibHttpTransport(boom, opener=op).request(HttpRequest(method="GET", url="https://example.com/"))
        self.assertEqual(op.calls, [])

    def test_url_and_method_validation_happens_before_io(self):
        opener = FakeOpener()
        instance = transport(opener=opener)
        for url in ("https://user:secret@example.com/", "http://example.com/",
                    "ftp://example.com/", "file:///tmp/x", "not-a-url"):
            with self.assertRaises(TransportRequestError):
                instance.request(HttpRequest(method="GET", url=url))
        self.assertEqual(opener.calls, [])
        for method in ("POST", "PUT", "DELETE"):
            with self.assertRaises(TransportRequestError):
                instance.request(HttpRequest(method=method, url="https://example.com/"))
        with self.assertRaises(TransportRequestError):
            instance.request(HttpRequest(method="GET", url="https://example.com/", body=b"x"))
        with self.assertRaises(TransportRequestError):
            instance.request(HttpRequest(method="GET", url="https://example.com/",
                                         headers=(("X-Bad\n", "v"),)))
        self.assertEqual(opener.calls, [])

    def test_http_scheme_only_when_explicitly_allowed(self):
        opener = FakeOpener(FakeResponse(body=b"ok"))
        instance = StdlibHttpTransport(lambda url: True, opener=opener,
                                       allowed_schemes=("https", "http"))
        response = instance.request(HttpRequest(method="GET", url="http://example.com/x"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(opener.calls[0]["request"].full_url, "http://example.com/x")

    def test_response_limit_is_enforced(self):
        opener = FakeOpener(FakeResponse(body=b"x" * 20))
        instance = StdlibHttpTransport(lambda url: True, opener=opener, max_bytes=10)
        with self.assertRaises(TransportLimitError):
            instance.request(HttpRequest(method="GET", url="https://example.com/", max_bytes=10))

    def test_redirect_is_returned_not_followed(self):
        headers = {"Location": "https://example.com/next", "Content-Type": "text/html"}
        error = urllib.error.HTTPError("https://example.com/start", 302, "Found",
                                       headers, None)
        opener = FakeOpener(error=error)
        instance = StdlibHttpTransport(lambda url: True, opener=opener)
        response = instance.request(HttpRequest(method="GET", url="https://example.com/start"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.header("location"), "https://example.com/next")
        self.assertEqual(len(opener.calls), 1)

    def test_static_no_implicit_network_object(self):
        source = (REPO_ROOT / "nl_coding_agent" / "research" / "transport.py").read_text(
            encoding="utf-8")
        self.assertIn("permission gate", source)
        self.assertNotIn("urlopen(", source)
        self.assertNotIn("build_opener()", source)
        self.assertIn("_NoRedirectHandler", source)


if __name__ == "__main__":
    unittest.main()

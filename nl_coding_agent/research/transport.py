"""Stdlib HTTP transport for research (R4) - explicit construction only.

Implements the existing injected HttpTransport contract from
nl_coding_agent.research.github (request(HttpRequest) -> HttpResponse).
It is never created implicitly: construction requires an explicit permission gate
(the service wires the capability/auto-review boundary), and all tests inject a
fake opener. No module-level opener/network object exists.

Safety rules:
  * only GET/HEAD, only explicitly allowed http(s) schemes;
  * URL credentials are rejected before any request; headers cannot contain CR/LF;
  * the permission gate is called before opening the connection and must return
    exactly True; False/exception fails closed;
  * timeouts and response sizes are bounded (request and transport limits);
  * redirects are NOT followed here: a 3xx response is returned with its
    Location header so the policy-enforcing fetcher can re-evaluate each hop;
  * errors never contain credentials or token/header values.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable

from .github import HttpRequest, HttpResponse, HttpTransport

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_BYTES = 2_000_000
READ_ONLY_METHODS = ("GET", "HEAD")
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class TransportError(RuntimeError):
    """Base explicit-transport failure (never includes credentials)."""


class TransportPermissionError(TransportError):
    """The explicit permission gate refused this URL/interaction."""


class TransportRequestError(TransportError):
    """Invalid request/URL/headers or I/O failure."""


class TransportLimitError(TransportError):
    """Response exceeded the configured byte cap."""


def _validate_url(url: str, allowed_schemes: Iterable[str]) -> str:
    if not isinstance(url, str) or not url.strip():
        raise TransportRequestError("URL must be a non-empty string")
    text = url.strip()
    if any(ord(char) < 32 for char in text):
        raise TransportRequestError("URL must not contain control characters")
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError as exc:
        raise TransportRequestError("URL is not parseable") from exc
    scheme = parts.scheme.lower()
    if scheme not in tuple(allowed_schemes):
        raise TransportRequestError("scheme is not allowed: " + (scheme or "<none>"))
    if not parts.hostname:
        raise TransportRequestError("URL must include a host")
    if parts.username is not None or parts.password is not None:
        raise TransportRequestError("URL must not contain credentials")
    if not parts.path and not parts.netloc:
        raise TransportRequestError("URL is not absolute")
    return urllib.parse.urlunsplit((scheme, parts.netloc, parts.path or "/",
                                    parts.query, ""))


def _validate_headers(headers: tuple[tuple[str, str], ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in headers or ():
        raw_name, raw_value = str(name), str(value)
        if any(char in raw_name + raw_value for char in ("\r", "\n")):
            raise TransportRequestError("headers must not contain CR/LF")
        header_name = raw_name.strip()
        header_value = raw_value.strip()
        if not header_name or not header_value:
            raise TransportRequestError("headers require a name and value")
        if header_name.lower() in ("host", "content-length", "transfer-encoding"):
            raise TransportRequestError("header is managed by the transport: " + header_name)
        result[header_name] = header_value
    return result


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Let redirect statuses surface as HTTPError/3xx responses instead of following."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


@dataclass
class _OpenedResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


class StdlibHttpTransport:
    """Explicit, permission-gated urllib transport implementing HttpTransport."""

    def __init__(self, permission_gate: Callable[[str], bool], *,
                 opener=None, allowed_schemes: Iterable[str] = ("https",),
                 timeout_s: float = DEFAULT_TIMEOUT_S,
                 max_bytes: int = DEFAULT_MAX_BYTES,
                 user_agent: str = "NL-Coding-Agent-Research/0.4 (explicit transport)"):
        if not callable(permission_gate):
            raise ValueError(
                "StdlibHttpTransport requires an explicit permission gate; "
                "no network transport is created by default")
        schemes = tuple(str(item).strip().lower() for item in allowed_schemes or ())
        if not schemes or any(item not in ("https", "http") for item in schemes):
            raise ValueError("allowed_schemes must be https and optionally http")
        if float(timeout_s) <= 0:
            raise ValueError("timeout_s must be positive")
        if int(max_bytes) <= 0:
            raise ValueError("max_bytes must be positive")
        self._permission_gate = permission_gate
        self._allowed_schemes = schemes
        self.timeout_s = float(timeout_s)
        self.max_bytes = int(max_bytes)
        self.user_agent = str(user_agent)
        if opener is None:
            opener = urllib.request.build_opener(_NoRedirectHandler())
        self._opener = opener

    def __repr__(self) -> str:
        return ("StdlibHttpTransport(schemes=" + repr(self._allowed_schemes)
                + ", timeout_s=" + str(self.timeout_s)
                + ", max_bytes=" + str(self.max_bytes) + ")")

    def _check_permission(self, url: str) -> None:
        try:
            decision = self._permission_gate(url)
        except Exception as exc:  # fail closed, never leak values
            raise TransportPermissionError(
                "permission gate refused the request ("
                + type(exc).__name__ + ")") from None
        if decision is not True:
            raise TransportPermissionError("permission gate denied the request")

    @staticmethod
    def _headers_from(instance) -> tuple[tuple[str, str], ...]:
        try:
            raw = instance.headers.items() if hasattr(instance.headers, "items") else ()
        except Exception:
            raw = ()
        items = []
        for name, value in raw:
            if str(name).lower() in ("location", "content-type", "etag",
                                     "last-modified", "content-language", "date",
                                     "content-length", "retry-after", "link"):
                items.append((str(name), str(value)))
        return tuple(sorted(items))

    def request(self, request: HttpRequest) -> HttpResponse:
        if not isinstance(request, HttpRequest):
            raise TransportRequestError("request must be an HttpRequest")
        method = str(request.method or "GET").upper()
        if method not in READ_ONLY_METHODS:
            raise TransportRequestError("transport is read-only: " + method)
        if request.body:
            raise TransportRequestError("read-only transport does not accept a body")
        url = _validate_url(request.url, self._allowed_schemes)
        headers = _validate_headers(request.headers)
        headers.setdefault("User-Agent", self.user_agent)
        headers.setdefault("Accept-Encoding", "identity")
        self._check_permission(url)
        timeout = min(float(request.timeout_s or self.timeout_s), self.timeout_s)
        limit = min(int(request.max_bytes or self.max_bytes), self.max_bytes)
        urllib_request = urllib.request.Request(url, headers=headers, method=method)
        try:
            response = self._opener.open(urllib_request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            # 3xx/4xx/5xx are returned as responses; redirects are not followed.
            try:
                body = exc.read(limit + 1) or b""
            except Exception:
                body = b""
            finally:
                try:
                    exc.close()
                except Exception:
                    pass
            if len(body) > limit:
                raise TransportLimitError("response exceeds max_bytes") from None
            return HttpResponse(status_code=int(exc.code),
                                headers=self._headers_from(exc), body=bytes(body))
        except Exception as exc:
            raise TransportRequestError(
                "transport I/O failure: " + type(exc).__name__) from None
        response_headers = self._headers_from(response)
        try:
            status = int(getattr(response, "status", None)
                         or getattr(response, "code", 0))
            if status <= 0:
                raise TransportRequestError("transport returned no HTTP status")
            body = response.read(limit + 1) or b""
        except TransportRequestError:
            raise
        except Exception as exc:
            raise TransportRequestError(
                "transport response read failed: " + type(exc).__name__) from None
        finally:
            try:
                response.close()
            except Exception:
                pass
        if len(body) > limit:
            raise TransportLimitError("response exceeds max_bytes")
        return HttpResponse(status_code=status, headers=response_headers,
                            body=bytes(body))

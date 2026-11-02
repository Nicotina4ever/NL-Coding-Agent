"""F3b: read-only LSP server detection + minimal JSON-RPC stdio client.

No installs, no network, no automatic server launches: a client starts only when the
caller explicitly starts it for the open project. Missing servers fail closed with
deterministic codes. Diagnostics are plain data for the Problems panel; hover,
completion and symbols are explicit user actions.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

__all__ = ["LspError", "LspServerSpec", "detect_language_servers", "LspClient",
           "LspManager", "encode_message", "decode_messages", "StdioLspTransport"]

_SERVERS = (
   ("pylsp", ["pylsp"], ("python",)),
    ("pyright", ["pyright-langserver", "--stdio"], ("python", "typescript")),
    ("basedpyright", ["basedpyright-langserver", "--stdio"], ("python",)),
    ("clangd", ["clangd"], ("c", "cpp")),
    ("typescript", ["typescript-language-server", "--stdio"], ("typescript", "javascript")),
    ("gopls", ["gopls"], ("go",)),
)
LANGUAGE_EXTENSIONS = {
    ".py": "python", ".pyi": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".go": "go",
}


class LspError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class LspServerSpec:
    server_id: str
    command: str
    args: tuple[str, ...]
    languages: tuple[str, ...]
    available: bool
    source: str = "which"

    def to_dict(self) -> dict:
        return {"server_id": self.server_id, "command": self.command,
                "args": list(self.args), "languages": list(self.languages),
                "available": self.available, "source": self.source}


def detect_language_servers(*, which=None) -> list[LspServerSpec]:
    import shutil
    import sys

    def _runtime_scripts(command: str) -> str | None:
        """Find console scripts installed in the embedded runtime's Scripts dir."""
        scripts = Path(sys.executable).resolve().parent / "Scripts"
        for candidate in (command, command + ".exe", command + ".cmd", command + ".bat"):
            path = scripts / candidate
            if path.is_file():
                return str(path)
        return None

    explicit = which is not None
    finder = which or shutil.which
    results = []
    for server_id, argv, languages in _SERVERS:
        command = argv[0]
        found = finder(command)
        source = "which" if found else "missing"
        if not found and not explicit:
            found = _runtime_scripts(command)
            source = "runtime-scripts" if found else "missing"
        results.append(LspServerSpec(server_id, str(found or command), tuple(argv[1:]),
                                     tuple(languages), bool(found), source=source))
    return results


def encode_message(payload: dict) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


def decode_messages(buffer: bytes) -> tuple[list[dict], bytes]:
    """Parse zero or more Content-Length framed JSON messages from a byte buffer."""
    messages = []
    while True:
        marker = buffer.find(b"\r\n\r\n")
        if marker < 0:
            break
        header = buffer[:marker].decode("ascii", "replace")
        length = None
        for line in header.splitlines():
            if line.lower().startswith("content-length:"):
                try:
                    length = int(line.split(":", 1)[1].strip())
                except ValueError:
                    raise LspError("protocol-error", "Invalid Content-Length header")
        if length is None:
            raise LspError("protocol-error", "Missing Content-Length header")
        start = marker + 4
        if len(buffer) < start + length:
            break
        body = buffer[start:start + length]
        try:
            messages.append(json.loads(body.decode("utf-8")))
        except ValueError as exc:
            raise LspError("protocol-error", "Invalid JSON body") from exc
        buffer = buffer[start + length:]
    return messages, buffer


class _Transport(Protocol):
    def send(self, payload: dict) -> None: ...
    def receive(self, timeout: float) -> dict: ...
    def close(self) -> None: ...


class StdioLspTransport:
    """Minimal stdio transport (explicitly created; no shell)."""

    def __init__(self, command: list[str], cwd: Path) -> None:
        self._process = subprocess.Popen(
            command, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False,
        )
        self._queue: queue.Queue = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        buffer = b""
        try:
            while True:
                # read() on a pipe blocks until the full size or EOF: a short LSP
                # response would then never be delivered. read1 returns as soon as
                # data is available.
                if not self._process.stdout:
                    return
                chunk = self._process.stdout.read1(4096)
                if not chunk:
                    return
                buffer += chunk
                messages, buffer = decode_messages(buffer)
                for message in messages:
                    self._queue.put(message)
        except Exception:
            return

    def send(self, payload: dict) -> None:
        if not self._process.stdin:
            raise LspError("transport-closed", "Language server stdin is closed")
        self._process.stdin.write(encode_message(payload))
        self._process.stdin.flush()

    def receive(self, timeout: float) -> dict:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise LspError("timeout", "Language server did not answer in time") from exc

    def close(self) -> None:
        try:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.terminate()
            self._process.wait(timeout=3)
        except Exception:
            pass


class LspClient:
    """Minimal explicit LSP client scoped to one project root."""

    def __init__(self, server: LspServerSpec, project_root: Path, *,
                 transport=None, timeout: float = 5.0) -> None:
        self.server = server
        self.root = Path(project_root).resolve()
        self.timeout = float(timeout)
        self._transport = transport
        self._next_id = 1
        self._diagnostics: dict[str, list[dict]] = {}
        self._initialized = False
        self.last_error = ""

    def _ensure_transport(self):
        if self._transport is None:
            if not self.server.available:
                raise LspError("server-unavailable",
                               "Language server " + self.server.server_id
                               + " is not installed (no install/download is attempted).")
            try:
                self._transport = StdioLspTransport(
                    [self.server.command, *self.server.args], self.root)
            except (FileNotFoundError, OSError) as exc:
                raise LspError(
                    "server-unavailable",
                    "Language server command could not be started: " + str(exc)) from exc
        return self._transport

    def _next(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def notify(self, method: str, params: dict) -> None:
        self._ensure_transport().send({"jsonrpc": "2.0", "method": method,
                                       "params": params})

    def request(self, method: str, params: dict, *, timeout: float | None = None) -> dict:
        transport = self._ensure_transport()
        request_id = self._next()
        transport.send({"jsonrpc": "2.0", "id": request_id, "method": method,
                        "params": params})
        deadline = self.timeout if timeout is None else float(timeout)
        while True:
            message = transport.receive(deadline)
            if message.get("id") == request_id:
                if "error" in message:
                    raise LspError("rpc-error", str(message["error"]))
                return dict(message.get("result") or {})
            self._absorb(message)

    def _absorb(self, message: dict) -> None:
        if message.get("method") == "textDocument/publishDiagnostics":
            params = message.get("params") or {}
            self._diagnostics[str(params.get("uri") or "")] = list(params.get("diagnostics") or [])

    def initialize(self) -> dict:
        root_uri = "file:///" + quote(str(self.root).replace("\\", "/").lstrip("/"))
        result = self.request("initialize", {
            "processId": None, "rootUri": root_uri, "capabilities": {},
            "workspaceFolders": [{"uri": root_uri, "name": self.root.name}],
        })
        self.notify("initialized", {})
        self._initialized = True
        return result

    def diagnostics(self, *, timeout: float | None = None,
                    expected_uris: list[str] | None = None) -> dict:
        if not self._initialized:
            raise LspError("not-initialized", "Start the language client explicitly first.")
        deadline = self.timeout if timeout is None else float(timeout)
        import time as _time

        end = _time.monotonic() + deadline
        while True:
            if expected_uris and all(uri in self._diagnostics for uri in expected_uris):
                break
            remaining = end - _time.monotonic()
            if remaining <= 0:
                break
            try:
                message = self._ensure_transport().receive(min(0.25, remaining))
            except LspError as exc:
                if exc.code != "timeout":
                    raise
                continue
            self._absorb(message)
        result = {}
        for uri, rows in self._diagnostics.items():
            result[uri] = [{"severity": int(row.get("severity") or 1),
                            "message": str(row.get("message") or ""),
                            "line": int((row.get("range") or {}).get("start", {}).get("line", 0)) + 1,
                            "column": int((row.get("range") or {}).get("start", {}).get("character", 0)) + 1,
                            "source": str(row.get("source") or "lsp")}
                           for row in rows]
        return result

    def open_document(self, path: str, *, language_id: str = "python") -> str:
        """Open one project file in the language server (diagnostics require didOpen)."""
        target = (self.root / str(path).replace("\\", "/").lstrip("./")).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise LspError("scope", "Document is outside the project root") from exc
        if not target.is_file():
            raise LspError("missing", "Document is missing: " + str(path))
        uri = self._uri(str(path))
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise LspError("read", "Cannot read document: " + str(exc)) from exc
        self.notify("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": language_id,
                             "version": 1, "text": text[:500_000]},
        })
        return uri

    def hover(self, path: str, line: int, character: int) -> dict:
        return self.request("textDocument/hover", {
            "textDocument": {"uri": self._uri(path)},
            "position": {"line": max(0, int(line) - 1), "character": max(0, int(character))}})

    def completion(self, path: str, line: int, character: int) -> dict:
        return self.request("textDocument/completion", {
            "textDocument": {"uri": self._uri(path)},
            "position": {"line": max(0, int(line) - 1), "character": max(0, int(character))}})

    def symbols(self, path: str) -> dict:
        return self.request("textDocument/documentSymbol",
                            {"textDocument": {"uri": self._uri(path)}})

    def _uri(self, path: str) -> str:
        target = (self.root / str(path)).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise LspError("path-escape", "LSP path escapes the open project") from exc
        return "file:///" + quote(str(target).replace("\\", "/").lstrip("/"))

    def close(self) -> None:
        try:
            if self._initialized:
                self.notify("exit", {})
        except Exception:
            pass
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._initialized = False


class LspManager:
    def __init__(self, project_root: Path, *, detector=None, transport_factory=None,
                 timeout: float = 5.0):
        self.root = Path(project_root).resolve()
        self._detector = detector or detect_language_servers
        self._factory = transport_factory
        self._timeout = max(1.0, float(timeout))
        self._clients: dict[str, LspClient] = {}

    def catalog(self) -> list[dict]:
        return [server.to_dict() for server in self._detector()]

    def server_for(self, language: str) -> LspServerSpec | None:
        language = str(language or "").lower()
        for server in self._detector():
            if server.available and language in server.languages:
                return server
        return None

    def start(self, language: str) -> dict:
        language = str(language or "").lower()
        if language in self._clients:
            return {"started": True, "language": language, "reused": True}
        server = self.server_for(language)
        if server is None:
            raise LspError("server-unavailable",
                           "No local language server for " + repr(language)
                           + " is installed; nothing was installed or downloaded.")
        transport = self._factory(server) if self._factory else None
        client = LspClient(server, self.root, transport=transport,
                           timeout=self._timeout)
        client.initialize()
        self._clients[language] = client
        return {"started": True, "language": language, "server": server.to_dict()}

    def diagnostics(self, language: str, *, timeout: float | None = None,
                    expected_uris: list[str] | None = None) -> dict:
        client = self._clients.get(str(language or "").lower())
        if client is None:
            raise LspError("not-initialized", "Language server is not started for this language.")
        return client.diagnostics(timeout=timeout, expected_uris=expected_uris)

    def open_documents(self, language: str, paths) -> list[str]:
        """Open explicit project-relative files so the server publishes diagnostics."""
        client = self._clients.get(str(language or "").lower())
        if client is None:
            raise LspError("not-initialized", "Language server is not started for this language.")
        language_id = "python" if str(language).lower() == "python" else str(language)
        uris: list[str] = []
        for path in list(paths or []):
            uris.append(client.open_document(str(path), language_id=language_id))
        return uris

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

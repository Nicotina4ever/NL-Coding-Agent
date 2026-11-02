"""Read-only code intelligence for models and post-write hooks (P2).

Two bounded capabilities that do not execute project code:
* symbol search over Python ASTs (plus a conservative regex fallback for other
  languages) so agents can navigate by symbol instead of reading whole trees;
* static diagnostics (syntax / structured-file parse, optional pyflakes) over an
  explicit file list, used as a post-write hook before the tester.
A language server is used only when one is already detectable; the tool reports
availability instead of installing anything.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILES = 600
MAX_BYTES = 400_000
IGNORED_DIRS = {
    ".git", ".hg", ".svn", "data", ".workspace", "__pycache__", "node_modules",
    "python", "vscode", "dist", "build", ".build", "out", "out-vscode-min",
    "da_eliminare", "ParcoTest", ".pytest_cache", ".mypy_cache", ".venv", "venv",
}
_PY_SUFFIXES = {".py"}
_OTHER_SYMBOL_RE = None


def _iter_files(root: Path, *, max_files: int = MAX_FILES):
    pending = [root]
    seen = 0
    while pending and seen < max_files:
        directory = pending.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if seen >= max_files:
                return
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if entry.name not in IGNORED_DIRS and not entry.name.startswith("."):
                        pending.append(entry)
                    continue
                if not entry.is_file() or entry.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            seen += 1
            yield entry


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


@dataclass
class Symbol:
    name: str
    kind: str
    path: str
    line: int
    column: int = 0
    parent: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "path": self.path,
                "line": self.line, "column": self.column, "parent": self.parent}


def _python_symbols(text: str, relative: str) -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    symbols: list[Symbol] = []

    def walk(node: ast.AST, parent: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(Symbol(child.name, "function", relative,
                                      int(getattr(child, "lineno", 0) or 0),
                                      int(getattr(child, "col_offset", 0) or 0), parent))
                walk(child, child.name)
            elif isinstance(child, ast.ClassDef):
                symbols.append(Symbol(child.name, "class", relative,
                                      int(getattr(child, "lineno", 0) or 0),
                                      int(getattr(child, "col_offset", 0) or 0), parent))
                walk(child, child.name)
            else:
                walk(child, parent)

    walk(tree)
    return symbols


def search_symbols(root: str | Path, query: str = "", *, limit: int = 50,
                   path_prefix: str = "") -> list[dict]:
    """Find Python (AST) and common-declaration symbols matching ``query``."""
    root = Path(root).resolve()
    needle = str(query or "").strip().lower()
    prefix = str(path_prefix or "").strip().replace("\\", "/").lstrip("./")
    results: list[dict] = []
    for path in _iter_files(root):
        relative = _relative(path, root)
        if prefix and not relative.startswith(prefix):
            continue
        suffix = path.suffix.lower()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found: list[Symbol] = []
        if suffix in _PY_SUFFIXES:
            found = _python_symbols(text, relative)
        elif suffix in (".ts", ".tsx", ".js", ".jsx"):
            import re as _re

            pattern = _re.compile(
                r"^\s*(?:export\s+)?(?:default\s+)?(class|function|interface|type|enum|const)\s+([A-Za-z_$][\w$]*)",
                _re.MULTILINE)
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                found.append(Symbol(match.group(2), match.group(1), relative, line))
        for symbol in found:
            if needle and needle not in symbol.name.lower() and needle not in symbol.path.lower():
                continue
            results.append(symbol.to_dict())
            if len(results) >= max(1, min(int(limit), 500)):
                return results
    return results


@dataclass
class Diagnostic:
    path: str
    line: int
    column: int
    severity: str
    message: str
    source: str

    def to_dict(self) -> dict:
        return {"path": self.path, "line": self.line, "column": self.column,
                "severity": self.severity, "message": self.message,
                "source": self.source}


def _python_diagnostics(root: Path, path: Path) -> list[Diagnostic]:
    relative = _relative(path, root)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Diagnostic(relative, 0, 0, "error", "cannot read file: " + str(exc), "filesystem")]
    try:
        compile(source, relative, "exec")
    except SyntaxError as exc:
        return [Diagnostic(relative, int(exc.lineno or 0), int(exc.offset or 0),
                           "error", str(exc.msg or "syntax error"), "syntax")]
    except ValueError as exc:
        return [Diagnostic(relative, 0, 0, "error", str(exc), "syntax")]
    # Optional static analysis when the development runtime already ships pyflakes.
    if "pyflakes" in sys.modules or _module_available("pyflakes"):
        try:
            from pyflakes import api as pyflakes_api
            from pyflakes import reporter as pyflakes_reporter

            class _Collector(pyflakes_reporter.Reporter):
                def __init__(self):
                    super().__init__(sys.stderr)
                    self.items: list[Diagnostic] = []

                def unexpectedError(self, filename, msg):  # noqa: N802
                    self.items.append(Diagnostic(_relative(Path(filename), root), 0, 0,
                                                 "error", str(msg), "pyflakes"))

                def syntaxError(self, filename, msg, lineno, offset, text):  # noqa: N802
                    self.items.append(Diagnostic(_relative(Path(filename), root),
                                                 int(lineno or 0), int(offset or 0),
                                                 "error", str(msg), "pyflakes"))

                def flake(self, message):
                    self.items.append(Diagnostic(
                        _relative(Path(message.filename), root),
                        int(getattr(message, "lineno", 0) or 0),
                        int(getattr(message, "col", 0) or 0),
                        "error" if message.__class__.__name__ == "UndefinedName" else "warning",
                        str(message.message % message.message_args)
                        if getattr(message, "message_args", None) else str(message),
                        "pyflakes"))

            collector = _Collector()
            pyflakes_api.check(source, relative, collector)
            return collector.items[:40]
        except Exception:
            return []
    return []


def _module_available(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _structured_diagnostics(root: Path, path: Path) -> list[Diagnostic]:
    relative = _relative(path, root)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [Diagnostic(relative, 0, 0, "error", "cannot read file: " + str(exc), "filesystem")]
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            json.loads(raw.decode("utf-8", errors="replace"))
        elif suffix == ".toml":
            tomllib.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, json.JSONDecodeError) as exc:
        line = int(getattr(exc, "lineno", 0) or 0)
        column = int(getattr(exc, "colno", 0) or 0)
        return [Diagnostic(relative, line, column, "error", str(exc), suffix.lstrip("."))]
    return []


def diagnose_files(root: str | Path, paths, *, limit: int = 40) -> list[dict]:
    """Static diagnostics for explicit files inside ``root`` (never executes code)."""
    root = Path(root).resolve()
    diagnostics: list[Diagnostic] = []
    for item in list(paths or [])[:limit]:
        relative = str(item).replace("\\", "/").lstrip("./")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            diagnostics.append(Diagnostic(relative, 0, 0, "error",
                                          "path is outside the project", "scope"))
            continue
        if not path.is_file():
            diagnostics.append(Diagnostic(relative, 0, 0, "error",
                                          "file is missing", "scope"))
            continue
        suffix = path.suffix.lower()
        if suffix in _PY_SUFFIXES:
            diagnostics.extend(_python_diagnostics(root, path))
        elif suffix in (".json", ".toml"):
            diagnostics.extend(_structured_diagnostics(root, path))
    return [item.to_dict() for item in diagnostics[:limit * 4]]


def format_diagnostics(items: list[dict], *, limit: int = 20) -> str:
    if not items:
        return "Static diagnostics: no errors."
    lines = ["Static diagnostics (" + str(len(items)) + "):"]
    for item in items[:limit]:
        lines.append("- " + str(item.get("severity") or "error").upper() + " "
                     + str(item.get("path") or "?") + ":"
                     + str(item.get("line") or 0) + ":" + str(item.get("column") or 0)
                     + " " + str(item.get("message") or "") + " [" + str(item.get("source") or "") + "]")
    return "\n".join(lines)


def lsp_diagnostics(project_root: str | Path, *, language: str = "python",
                    timeout_s: float = 20.0, paths=None) -> dict:
    """Bounded diagnostics through an already-available LSP server (no installs)."""
    root = Path(project_root).resolve()
    try:
        from nl_coding_agent.app.lsp import LspManager
    except Exception as exc:  # pragma: no cover - import guard
        return {"available": False, "reason": "LSP module unavailable: " + type(exc).__name__,
                "diagnostics": []}
    if not paths:
        suffix = ".py" if str(language).lower() == "python" else None
        discovered = []
        for path in _iter_files(root, max_files=MAX_FILES):
            if suffix and path.suffix.lower() != suffix:
                continue
            discovered.append(_relative(path, root))
            if len(discovered) >= 30:
                break
        paths = discovered
    try:
        manager = LspManager(root, timeout=max(5.0, float(timeout_s)))
        catalog = manager.catalog()
        available = [item for item in catalog if item.get("available")]
        if not available:
            return {"available": False,
                    "reason": "no language server detected (pylsp/pyright/basedpyright not installed)",
                    "diagnostics": [], "catalog": catalog}
        try:
            manager.start(language)
            uris = manager.open_documents(language, list(paths)[:50])
            payload = manager.diagnostics(language, timeout=max(5.0, float(timeout_s)),
                                          expected_uris=uris)
        finally:
            try:
                manager.close()
            except Exception:
                pass
        from urllib.parse import unquote

        items: list[dict] = []
        if isinstance(payload, dict):
            for uri, rows in payload.items():
                relative = unquote(str(uri)).replace("file:///", "").replace("file://", "")
                relative = relative.replace("\\", "/").lstrip("/")
                try:
                    relative = Path(relative).resolve().relative_to(root).as_posix()
                except ValueError:
                    pass
                for row in rows or []:
                    items.append({
                        "path": relative,
                        "line": int(row.get("line") or 0),
                        "column": int(row.get("column") or 0),
                        "severity": "error" if int(row.get("severity") or 1) == 1 else "warning",
                        "message": str(row.get("message") or ""),
                        "source": "lsp:" + str(row.get("source") or language),
                    })
        return {"available": True, "language": language,
                "diagnostics": items[:200], "catalog": catalog,
                "files_analyzed": len(paths)}
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__ + ": " + str(exc),
                "diagnostics": []}

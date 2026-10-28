"""Stage 6e: acquire and measure native runtime archives for the six beta targets.

This tool closes the gap between the declarative six-target runtime manifest
(installer/runtime_manifest.json, a template with no measured artifacts) and a
measured manifest that can feed the provisioner/release builder (NL-BP-154/156/165).

Safety properties (all tested):

* default mode is a PLAN (--dry-run semantics): no network request, no filesystem
  write, no directory creation;
* --offline-dir measures archives already downloaded by a release runner/human;
* --download streams from declarative sources using a bounded-size, bounded-time
  reader with an injectable opener (tests use fakes/local loopback servers);
* every archive is format-checked against the target's pinned archive kind and
  content-checked so a Windows runtime artifact is never accepted for a
  non-Windows target (or the reverse);
* optional expected sha256/size values are verified when present; a mismatch is
  a hard refusal;
* --write emits a NEW measured runtime-manifest draft plus an evidence report;
  installer/runtime_manifest.json is never overwritten unless --force is given
  explicitly;
* no upload/push/publish, no model runs, no execution of the downloaded archives,
  no deletion of user files.

Hashes are only ever computed from real bytes; the tool never fabricates a hash
or a size. A partial measurement keeps release_ready=false and leaves explicit
unmeasured placeholders for the missing targets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer.platform_targets import (  # noqa: E402
    SUPPORTED_TARGETS,
    TARGET_ORDER,
    UnsupportedTargetError,
    detect_host_target,
    resolve_target,
)
from installer.runtime_manifest import validate_runtime_manifest  # noqa: E402
from nl_coding_agent.core.workspace import workspace_root  # noqa: E402

TOOL_NAME = "fetch_native_runtimes.py"
TOOL_VERSION = "0.1.0"
SOURCES_SCHEMA_VERSION = 1
DEFAULT_SOURCES = REPO_ROOT / "installer" / "runtime_sources.json"
TEMPLATE_MANIFEST = REPO_ROOT / "installer" / "runtime_manifest.json"
DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 1024 * 1024
MAX_MEMBERS_SCANNED = 200
_EXTENSION_BY_KIND = {"zip": (".zip",), "tar.gz": (".tar.gz", ".tgz"), "tar": (".tar",)}
_ARCHIVE_KINDS = tuple(_EXTENSION_BY_KIND)
_HEX = set("0123456789abcdef")
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_FAILURE = 3


class FetchRuntimeError(RuntimeError):
    """Deterministic refusal; code is stable for CLI/tests."""

    def __init__(self, message: str, *, code: str = "fetch-runtime-error",
                 target: str | None = None) -> None:
        super().__init__(message)
        self.code = str(code)
        self.target = target


class SourceError(FetchRuntimeError):
    def __init__(self, message: str, *, code: str = "source-invalid",
                 target: str | None = None) -> None:
        super().__init__(message, code=code, target=target)


class MeasureError(FetchRuntimeError):
    def __init__(self, message: str, *, code: str = "measure-failed",
                 target: str | None = None) -> None:
        super().__init__(message, code=code, target=target)


class DownloadError(FetchRuntimeError):
    def __init__(self, message: str, *, code: str = "download-failed",
                 target: str | None = None) -> None:
        super().__init__(message, code=code, target=target)


@dataclass(frozen=True)
class ArchiveSource:
    target_id: str
    provider: str
    provider_url: str
    version: str
    archive_kind: str
    url: str
    filename: str
    expected_sha256: str
    expected_size: int
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "provider": self.provider,
            "provider_url": self.provider_url,
            "version": self.version,
            "archive_kind": self.archive_kind,
            "url": redact_url(self.url),
            "filename": self.filename,
            "expected_sha256": self.expected_sha256,
            "expected_size": int(self.expected_size),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_url(url: str) -> str:
    """Return scheme://host/path, dropping credentials, query and fragment."""
    try:
        parts = urllib.parse.urlsplit(str(url))
    except ValueError:
        return ""
    host = parts.hostname or ""
    if parts.port:
        host = host + ":" + str(parts.port)
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path, "", ""))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _display_path(path: Path | str | None) -> str:
    if path is None:
        return ""
    value = Path(path)
    try:
        return value.resolve().relative_to(REPO_ROOT).as_posix()
    except (OSError, ValueError):
        return value.name


def _git_head() -> str | None:
    git_dir = REPO_ROOT / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = git_dir / head[len("ref: "):].strip()
            return ref.read_text(encoding="utf-8").strip() or None
        return head or None
    except OSError:
        return None


def default_workspace_path(*parts: str) -> Path:
    return workspace_root().joinpath(*parts)


def default_draft_path() -> Path:
    return default_workspace_path("build", "native-runtimes", "runtime-manifest.measured.json")


def default_evidence_path() -> Path:
    return default_workspace_path("build", "native-runtimes", "evidence.json")


def default_cache_dir() -> Path:
    return default_workspace_path("cache", "native-runtimes")


def detect_host_target_safe() -> tuple[str | None, str]:
    try:
        return detect_host_target(), ""
    except UnsupportedTargetError as exc:
        return None, str(exc)


# ---------------------------------------------------------------------------
# Source manifest
# ---------------------------------------------------------------------------
def _text(value, field: str, *, code: str = "source-invalid") -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceError("required non-empty string: " + field, code=code)
    return value.strip()


def _positive_number(value, field: str, default: float):
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SourceError("must be a positive number: " + field) from exc
    if number <= 0:
        raise SourceError("must be a positive number: " + field)
    return number


def _sha256_field(value, field: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if len(text) != 64 or any(char not in _HEX for char in text):
        raise SourceError("invalid sha256: " + field)
    return text


def _size_field(value, field: str) -> int:
    if value in (None, ""):
        return 0
    try:
        size = int(value)
    except (TypeError, ValueError) as exc:
        raise SourceError("invalid expected_size: " + field) from exc
    if size < 0:
        raise SourceError("expected_size must not be negative: " + field)
    return size


def _http_url(value, field: str) -> str:
    text = _text(value, field)
    parts = urllib.parse.urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise SourceError("URL must use http(s): " + field)
    if not parts.hostname:
        raise SourceError("URL must have a host: " + field)
    if parts.username or parts.password:
        raise SourceError("URL must not embed credentials: " + field, code="url-credentials")
    return text


def _filename_from_url(url: str) -> str:
    name = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
    return name


def _check_archive_extension(filename: str, archive_kind: str, field: str) -> None:
    lowered = filename.lower()
    allowed = _EXTENSION_BY_KIND[archive_kind]
    if not any(lowered.endswith(ext) for ext in allowed):
        raise SourceError(
            "archive filename/URL does not match archive_kind " + archive_kind
            + " (expected " + "/".join(allowed) + "): " + field,
            code="url-format-mismatch",
        )


def validate_sources(data: Mapping) -> dict:
    """Validate and normalize installer/runtime_sources.json (no network, no writes)."""
    if not isinstance(data, Mapping):
        raise SourceError("runtime sources must be a JSON object")
    if data.get("schema_version") != SOURCES_SCHEMA_VERSION:
        raise SourceError("unsupported schema_version: " + repr(data.get("schema_version")))
    product = data.get("product")
    if not isinstance(product, Mapping):
        raise SourceError("product is required")
    product_id = _text(product.get("id"), "product.id")
    product_name = _text(product.get("name", product_id), "product.name")
    product_version = _text(product.get("version"), "product.version")
    channel = str(product.get("channel") or "beta")
    base_url = _http_url(data.get("base_url", "https://downloads.example.invalid/nl-coding-agent"),
                        "base_url").rstrip("/")
    timeout_s = _positive_number(data.get("timeout_s"), "timeout_s", DEFAULT_TIMEOUT_S)
    max_bytes = int(_positive_number(data.get("max_archive_bytes"), "max_archive_bytes",
                                     DEFAULT_MAX_ARCHIVE_BYTES))
    targets_raw = data.get("targets")
    if not isinstance(targets_raw, Mapping):
        raise SourceError("targets must be an object")
    missing = [target for target in TARGET_ORDER if target not in targets_raw]
    unknown = sorted(str(key) for key in targets_raw if str(key) not in SUPPORTED_TARGETS)
    if missing:
        raise SourceError("runtime sources must declare all six targets; missing: "
                          + ", ".join(missing))
    if unknown:
        raise SourceError("runtime sources declare unsupported targets: " + ", ".join(unknown))
    targets: dict[str, ArchiveSource] = {}
    for target_id in TARGET_ORDER:
        entry = targets_raw[target_id]
        if not isinstance(entry, Mapping):
            raise SourceError("target entry must be an object: " + target_id)
        descriptor = SUPPORTED_TARGETS[target_id]
        provider = _text(entry.get("provider"), target_id + ".provider")
        provider_url = ""
        if entry.get("provider_url"):
            provider_url = _http_url(entry.get("provider_url"), target_id + ".provider_url")
        version = str(entry.get("version") or "").strip()
        if not version:
            raise SourceError("missing version: " + target_id)
        archive_kind = str(entry.get("archive_kind") or descriptor["archive"]).strip().lower()
        if archive_kind not in _ARCHIVE_KINDS:
            raise SourceError("unsupported archive_kind for " + target_id + ": " + archive_kind)
        if archive_kind != descriptor["archive"]:
            raise SourceError(
                "archive_kind " + archive_kind + " does not match the pinned archive kind "
                + descriptor["archive"] + " for " + target_id,
                code="archive-kind-mismatch", target=target_id,
            )
        raw_url = entry.get("url") or entry.get("url_template")
        if not raw_url:
            raise SourceError("missing url/url_template: " + target_id)
        try:
            url = str(raw_url).format(version=version, target=target_id)
        except (KeyError, IndexError, ValueError) as exc:
            raise SourceError("invalid URL template: " + target_id) from exc
        url = _http_url(url, target_id + ".url")
        filename = str(entry.get("filename") or "").strip() or _filename_from_url(url)
        if Path(filename).name != filename or not filename or filename in (".", ".."):
            raise SourceError("filename must be a plain file name: " + target_id)
        _check_archive_extension(filename, archive_kind, target_id)
        expected_sha256 = _sha256_field(entry.get("expected_sha256"), target_id + ".expected_sha256")
        expected_size = _size_field(entry.get("expected_size"), target_id + ".expected_size")
        if expected_sha256 and expected_size <= 0:
            raise SourceError(
                "measured source requires a positive expected_size: " + target_id,
                code="measured-source-requires-size", target=target_id,
            )
        if not expected_sha256 and expected_size not in (0, None):
            raise SourceError(
                "unmeasured source must not declare expected_size: " + target_id,
                code="unmeasured-source-must-not-declare-size", target=target_id,
            )
        targets[target_id] = ArchiveSource(
            target_id=target_id,
            provider=provider,
            provider_url=provider_url,
            version=version,
            archive_kind=archive_kind,
            url=url,
            filename=filename,
            expected_sha256=expected_sha256,
            expected_size=int(expected_size),
            notes=tuple(str(item) for item in (entry.get("notes") or [])),
        )
    return {
        "schema_version": SOURCES_SCHEMA_VERSION,
        "status": str(data.get("status") or "template"),
        "generated_by": str(data.get("generated_by") or ""),
        "note": str(data.get("note") or ""),
        "product": {"id": product_id, "name": product_name, "version": product_version,
                    "channel": channel},
        "base_url": base_url,
        "timeout_s": float(timeout_s),
        "max_archive_bytes": max_bytes,
        "targets": targets,
    }


def load_sources(path: str | Path = DEFAULT_SOURCES) -> dict:
    sources_path = Path(path)
    if not sources_path.is_file():
        raise SourceError("runtime sources not found: " + str(sources_path), code="sources-not-found")
    try:
        data = json.loads(sources_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError("runtime sources are not valid JSON: " + str(exc),
                          code="sources-invalid-json") from exc
    return validate_sources(data)


def resolve_selected_targets(selected: list[str] | None) -> list[str]:
    if not selected:
        return list(TARGET_ORDER)
    resolved: list[str] = []
    for item in selected:
        try:
            target = resolve_target(str(item))
        except UnsupportedTargetError as exc:
            raise SourceError(str(exc), code="unsupported-target") from exc
        if target not in resolved:
            resolved.append(target)
    return resolved


# ---------------------------------------------------------------------------
# Planning (dry-run; no network, no writes)
# ---------------------------------------------------------------------------
def build_plan(sources: dict, *, selected: list[str], host_target: str | None,
               offline_dir: Path | None = None, mode: str = "plan") -> dict:
    entries = []
    for target_id in selected:
        source = sources["targets"][target_id]
        descriptor = SUPPORTED_TARGETS[target_id]
        entries.append({
            "target": target_id,
            "display_name": descriptor["display_name"],
            "provider": source.provider,
            "provider_url": source.provider_url,
            "version": source.version,
            "archive_kind": source.archive_kind,
            "filename": source.filename,
            "url": redact_url(source.url),
            "expected_sha256": source.expected_sha256,
            "expected_size": source.expected_size,
            "expected_state": "measured-expected" if source.expected_sha256 else "unmeasured",
            "native_host_match": (host_target == target_id) if host_target else None,
            "action": ("measure-offline" if mode == "offline" and offline_dir is not None
                       else "download-and-measure" if mode == "download"
                       else "plan-only"),
            "offline_path": (str(offline_dir / source.filename) if offline_dir else None),
        })
    return {
        "mode": mode,
        "dry_run": mode == "plan",
        "host_target": host_target,
        "sources": {"schema_version": sources["schema_version"],
                    "status": sources["status"], "product": dict(sources["product"]),
                    "base_url": sources["base_url"]},
        "targets": entries,
        "counts": {"selected": len(entries), "total": len(TARGET_ORDER)},
        "no_network": mode == "plan",
        "no_writes": mode == "plan",
    }


# ---------------------------------------------------------------------------
# Archive inspection and measurement
# ---------------------------------------------------------------------------
def _detect_archive_format(path: Path) -> str | None:
    try:
        head = Path(path).open("rb").read(8)
    except OSError as exc:
        raise MeasureError("cannot read archive: " + str(exc), code="archive-unreadable") from exc
    if head.startswith(b"PK" + bytes([3, 4])):
        return "zip"
    if head.startswith(bytes([0x1F, 0x8B])):
        return "tar.gz"
    return None


def _member_names(path: Path, archive_kind: str) -> tuple[list[str], bool]:
    names: list[str] = []
    truncated = False
    try:
        if archive_kind == "zip":
            with zipfile.ZipFile(path) as archive:
                all_names = archive.namelist()
                names = all_names[:MAX_MEMBERS_SCANNED]
                truncated = len(all_names) > len(names)
        else:
            with tarfile.open(path, "r:*") as archive:
                for index, member in enumerate(archive):
                    if index >= MAX_MEMBERS_SCANNED:
                        truncated = True
                        break
                    names.append(member.name)
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError) as exc:
        raise MeasureError("archive is not a readable " + archive_kind + ": " + str(exc),
                           code="archive-invalid") from exc
    return names, truncated


def _os_evidence(names: list[str]) -> tuple[str, dict]:
    windows_markers = 0
    posix_markers = 0
    for name in names:
        lowered = str(name).replace(chr(92), "/").lower()
        parts = [part for part in lowered.split("/") if part]
        basename = parts[-1] if parts else ""
        if basename.endswith((".exe", ".dll", ".pyd")):
            windows_markers += 1
        elif any(part in ("windows", "win-amd64", "win_amd64", "win-arm64")
                 for part in parts):
            windows_markers += 1
        if basename in ("python3", "python3.12", "python") or basename.endswith(
                (".so", ".dylib")):
            posix_markers += 1
    if windows_markers and posix_markers:
        evidence = "mixed"
    elif windows_markers:
        evidence = "windows"
    elif posix_markers:
        evidence = "posix"
    else:
        evidence = "unknown"
    return evidence, {"windows_markers": windows_markers, "posix_markers": posix_markers}


def inspect_archive(source: ArchiveSource, path: Path) -> dict:
    expected_kind = source.archive_kind
    detected = _detect_archive_format(path)
    if detected is None:
        raise MeasureError("archive format is not zip/tar.gz: " + source.filename,
                           code="archive-format", target=source.target_id)
    if detected != expected_kind:
        raise MeasureError(
            "archive format " + detected + " does not match the pinned archive kind "
            + expected_kind + " for " + source.target_id,
            code="archive-format", target=source.target_id,
        )
    names, truncated = _member_names(path, expected_kind)
    evidence, counts = _os_evidence(names)
    target_os = SUPPORTED_TARGETS[source.target_id]["os"]
    if evidence == "windows" and target_os != "windows":
        raise FetchRuntimeError(
            "refusing a Windows runtime artifact for non-Windows target "
            + source.target_id + ": the Windows embedded runtime is never reused off "
              "Windows (native runtime selection is strict).",
            code="windows-runtime-on-non-windows", target=source.target_id,
        )
    if evidence == "posix" and target_os == "windows":
        raise FetchRuntimeError(
            "refusing a non-Windows runtime artifact for Windows target "
            + source.target_id + ".",
            code="non-windows-runtime-on-windows", target=source.target_id,
        )
    return {
        "format_detected": detected,
        "members_scanned": len(names),
        "member_scan_truncated": bool(truncated),
        "os_evidence": evidence,
        "windows_markers": counts["windows_markers"],
        "posix_markers": counts["posix_markers"],
        "mixed_os_evidence": evidence == "mixed",
    }


def measure_archive(source: ArchiveSource, path: str | Path, *, mode: str,
                    known_sha256: str | None = None) -> dict:
    started = time.monotonic()
    archive_path = Path(path)
    if not archive_path.is_file():
        raise MeasureError("archive not found: " + str(archive_path),
                           code="archive-missing", target=source.target_id)
    size = int(archive_path.stat().st_size)
    if size <= 0:
        raise MeasureError("archive is empty: " + str(archive_path),
                           code="archive-empty", target=source.target_id)
    digest = known_sha256 or sha256_file(archive_path)
    if source.expected_size and size != source.expected_size:
        raise MeasureError(
            "archive size mismatch for " + source.target_id + ": expected "
            + str(source.expected_size) + ", got " + str(size),
            code="size-mismatch", target=source.target_id,
        )
    if source.expected_sha256 and digest.lower() != source.expected_sha256:
        raise MeasureError(
            "archive sha256 mismatch for " + source.target_id + " (expected "
            + source.expected_sha256 + ", got " + digest + ")",
            code="hash-mismatch", target=source.target_id,
        )
    inspection = inspect_archive(source, archive_path)
    expected_match = None
    if source.expected_sha256:
        expected_match = True
    return {
        "target": source.target_id,
        "provider": source.provider,
        "version": source.version,
        "filename": source.filename,
        "archive_kind": source.archive_kind,
        "mode": mode,
        "measured": True,
        "size": size,
        "sha256": digest,
        "expected_sha256": source.expected_sha256,
        "expected_size": source.expected_size,
        "expected_match": expected_match,
        "source_url": redact_url(source.url),
        "duration_s": round(time.monotonic() - started, 3),
        **inspection,
    }


def offline_archive_path(source: ArchiveSource, offline_dir: str | Path) -> Path:
    base = Path(offline_dir).resolve()
    if not base.is_dir():
        raise MeasureError("offline directory not found: " + str(offline_dir),
                           code="offline-dir-missing", target=source.target_id)
    candidate = (base / source.filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise MeasureError("offline archive path escapes the offline directory: "
                           + source.filename, code="offline-path-escape",
                           target=source.target_id) from exc
    if not candidate.is_file():
        raise MeasureError("offline archive not found: " + str(candidate),
                           code="offline-archive-missing", target=source.target_id)
    return candidate


# ---------------------------------------------------------------------------
# Download (bounded size/time; injectable opener for tests)
# ---------------------------------------------------------------------------
def download_archive(url: str, destination: str | Path, *, opener: Callable | None = None,
                     timeout: float = DEFAULT_TIMEOUT_S,
                     max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
                     chunk_size: int = DEFAULT_CHUNK_SIZE,
                     target: str | None = None) -> dict:
    """Stream one archive to destination with a hard byte bound and wall-time guard."""
    if max_bytes <= 0:
        raise DownloadError("max_bytes must be positive")
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest.with_name(dest.name + ".part")
    try:
        temp_path.unlink(missing_ok=True)
    except OSError:
        pass
    opener_fn = opener or urllib.request.urlopen
    digest = hashlib.sha256()
    written = 0
    started = time.monotonic()
    response = None
    try:
        try:
            response = opener_fn(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - network errors are data
            raise DownloadError("could not open source URL for " + str(target or "")
                                + ": " + str(exc), code="download-open-failed",
                                target=target) from exc
        status = int(getattr(response, "status", 200) or 200)
        if status < 200 or status >= 300:
            raise DownloadError("HTTP " + str(status) + " for source "
                                + redact_url(url), code="download-http-error", target=target)
        with temp_path.open("wb") as handle:
            while True:
                if time.monotonic() - started > timeout:
                    raise DownloadError("download timed out after " + str(timeout) + "s",
                                        code="download-timeout", target=target)
                try:
                    block = response.read(chunk_size)
                except Exception as exc:  # noqa: BLE001
                    raise DownloadError("download read failed: " + str(exc),
                                        code="download-read-failed", target=target) from exc
                if not block:
                    break
                written += len(block)
                if written > max_bytes:
                    raise DownloadError(
                        "download exceeds the configured byte limit (" + str(max_bytes) + ")",
                        code="download-too-large", target=target)
                digest.update(block)
                handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())
        if written <= 0:
            raise DownloadError("downloaded archive is empty",
                                code="download-empty", target=target)
        os.replace(temp_path, dest)
        return {"path": dest, "size": written, "sha256": digest.hexdigest(),
                "download_seconds": round(time.monotonic() - started, 3),
                "source_url": redact_url(url)}
    finally:
        if response is not None:
            closer = getattr(response, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:  # noqa: BLE001
                    pass
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Acquisition orchestration
# ---------------------------------------------------------------------------
def measure_offline(sources: dict, offline_dir: str | Path,
                    selected: list[str]) -> list[dict]:
    results = []
    for target_id in selected:
        source = sources["targets"][target_id]
        path = offline_archive_path(source, offline_dir)
        results.append(measure_archive(source, path, mode="offline"))
    return results


def acquire_download(sources: dict, cache_dir: str | Path, selected: list[str], *,
                     opener: Callable | None = None,
                     timeout: float | None = None,
                     max_bytes: int | None = None) -> list[dict]:
    limit = int(max_bytes if max_bytes is not None else sources["max_archive_bytes"])
    effective_timeout = float(timeout if timeout is not None else sources["timeout_s"])
    cache = Path(cache_dir)
    results = []
    for target_id in selected:
        source = sources["targets"][target_id]
        destination = cache / source.filename
        downloaded = download_archive(source.url, destination, opener=opener,
                                      timeout=effective_timeout, max_bytes=limit,
                                      target=target_id)
        measured = measure_archive(source, downloaded["path"], mode="download",
                                   known_sha256=downloaded["sha256"])
        measured["download"] = {
            "seconds": downloaded["download_seconds"],
            "declared_source_url": downloaded["source_url"],
        }
        results.append(measured)
    return results


# ---------------------------------------------------------------------------
# Measured manifest draft + evidence
# ---------------------------------------------------------------------------
def build_measured_draft(sources: dict, measurements: list[dict]) -> dict:
    """Build a schema-valid runtime-manifest draft; release_ready only for 6/6."""
    measured_map: dict[str, dict] = {}
    for item in measurements:
        target_id = item["target"]
        source = sources["targets"][target_id]
        measured_map[target_id] = {
            "version": source.version,
            "archive": item["archive_kind"],
            "name": item["filename"],
            "sha256": item["sha256"],
            "size": int(item["size"]),
        }
    import scripts.build_release as release_builder  # local import: heavy module, test-visible

    draft = release_builder.build_runtime_manifest(
        sources["product"]["version"], measured_map, base_url=sources["base_url"])
    draft["generated_by"] = TOOL_NAME + " " + TOOL_VERSION
    draft["product"] = dict(sources["product"])
    draft["base_urls"] = {"primary": sources["base_url"]}
    try:
        validate_runtime_manifest(draft)
    except ValueError as exc:
        raise FetchRuntimeError("internal error: generated draft failed schema validation: "
                                + str(exc), code="draft-invalid") from exc
    expected_ready = len({item["target"] for item in measurements}) == len(TARGET_ORDER)
    if bool(draft.get("release_ready")) != expected_ready:
        raise FetchRuntimeError("internal error: draft release_ready does not match six-target "
                                "measurement", code="draft-invalid")
    draft["status"] = "release" if expected_ready else "draft"
    return draft


def build_evidence(sources: dict, measurements: list[dict], *, selected: list[str],
                   mode: str, host_target: str | None, host_note: str,
                   sources_path: Path, draft_path: Path | None,
                   evidence_path: Path | None) -> dict:
    by_target = {item["target"]: item for item in measurements}
    targets = []
    for target_id in TARGET_ORDER:
        source = sources["targets"][target_id]
        measurement = by_target.get(target_id)
        entry = source.to_dict()
        entry.update({
            "target": target_id,
            "selected": target_id in selected,
            "measured": measurement is not None,
            "native_host_match": (host_target == target_id) if host_target else None,
        })
        if measurement is not None:
            entry.update({key: measurement[key] for key in (
                "size", "sha256", "expected_match", "format_detected", "members_scanned",
                "member_scan_truncated", "os_evidence", "windows_markers", "posix_markers",
                "mixed_os_evidence", "duration_s", "mode", "source_url")})
            if "download" in measurement:
                entry["download"] = dict(measurement["download"])
        targets.append(entry)
    measured_count = len(measurements)
    return {
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "generated_at": _utc_now(),
        "mode": mode,
        "dry_run": False,
        "host_target": host_target,
        "host_detection": "detected" if host_target else "unsupported",
        "host_note": host_note,
        "git_head": _git_head(),
        "sources": {
            "path": _display_path(sources_path),
            "sha256": sha256_file(sources_path) if Path(sources_path).is_file() else "",
            "schema_version": sources["schema_version"],
            "status": sources["status"],
            "product": dict(sources["product"]),
        },
        "outputs": {
            "runtime_manifest_draft": _display_path(draft_path) if draft_path else None,
            "evidence_report": _display_path(evidence_path) if evidence_path else None,
        },
        "template_manifest": {
            "path": _display_path(TEMPLATE_MANIFEST),
            "sha256": sha256_file(TEMPLATE_MANIFEST) if TEMPLATE_MANIFEST.is_file() else "",
            "overwritten": False,
        },
        "targets": targets,
        "summary": {
            "selected": len(selected),
            "measured": measured_count,
            "unmeasured": len(TARGET_ORDER) - measured_count,
            "all_six_measured": measured_count == len(TARGET_ORDER),
            "release_ready": measured_count == len(TARGET_ORDER),
        },
        "support_claim": False,
        "ci_vs_manual_pending": (
            "Measurement is a release-runner/human step. Measured hashes are "
            "reproducibility evidence, not platform support: real-hardware and "
            "clean-machine acceptance stay MANUAL-PENDING, and no CI run is implied."
        ),
    }


# ---------------------------------------------------------------------------
# Writing (never overwrite the template by default)
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, payload: Mapping) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + chr(10),
                             encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
    return path


def write_outputs(draft: Mapping, evidence: dict, *, draft_path: str | Path,
                  evidence_path: str | Path, force: bool = False) -> dict:
    draft_target = Path(draft_path).expanduser()
    evidence_target = Path(evidence_path).expanduser()
    template = TEMPLATE_MANIFEST.resolve()
    if draft_target.resolve() == template and not force:
        raise FetchRuntimeError(
            "refusing to overwrite the tracked template manifest installer/runtime_manifest.json; "
            "write a new draft path (default: .workspace/build/native-runtimes/"
            "runtime-manifest.measured.json) or pass --force explicitly.",
            code="refuse-template-overwrite",
        )
    if not force:
        for target, label in ((draft_target, "runtime-manifest draft"),
                              (evidence_target, "evidence report")):
            if target.exists():
                raise FetchRuntimeError(
                    "refusing to overwrite an existing " + label + ": " + str(target)
                    + " (pass --force to replace it)", code="output-exists")
    written_manifest = _atomic_write_json(draft_target, draft)
    evidence["outputs"]["runtime_manifest_draft"] = _display_path(written_manifest)
    evidence["outputs"]["evidence_report"] = _display_path(evidence_target)
    written_evidence = _atomic_write_json(evidence_target, evidence)
    return {"runtime_manifest": str(written_manifest), "evidence": str(written_evidence)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_plan(plan: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return
    print(TOOL_NAME + " " + TOOL_VERSION + " - PLAN (dry-run: no network, no writes)")
    print("Sources: " + str(plan["sources"].get("status") or "") +
          " | product " + str(plan["sources"]["product"].get("version") or ""))
    print("Host target: " + str(plan["host_target"] or "(unsupported host)"))
    print("Targets: " + str(plan["counts"]["selected"]) + "/" + str(plan["counts"]["total"]))
    for entry in plan["targets"]:
        print("  " + entry["target"] + "  provider=" + entry["provider"]
              + "  version=" + entry["version"]
              + "  archive=" + entry["archive_kind"]
              + "  expected=" + entry["expected_state"]
              + "  action=" + entry["action"])
    print("No files were written and no network request was made.")


def _print_measurements(measurements: list[dict], *, as_json: bool, draft: dict | None,
                        written: dict | None) -> None:
    if as_json:
        print(json.dumps({"measurements": measurements,
                          "draft_release_ready": bool(draft and draft.get("release_ready")),
                          "written": written}, indent=2, ensure_ascii=False))
        return
    print(TOOL_NAME + " " + TOOL_VERSION + " - MEASUREMENT SUMMARY")
    for item in measurements:
        print("  " + item["target"] + "  bytes=" + str(item["size"])
              + "  sha256=" + item["sha256"]
              + "  format=" + item["format_detected"]
              + "  os-evidence=" + item["os_evidence"]
              + "  expected=" + ("verified" if item["expected_match"] else "unmeasured"))
    if draft is not None:
        print("Draft: release_ready=" + str(bool(draft.get("release_ready")))
              + " status=" + str(draft.get("status")))
    if written:
        print("Wrote runtime-manifest draft: " + written["runtime_manifest"])
        print("Wrote evidence report: " + written["evidence"])
    else:
        print("Nothing was written (use --write to emit the draft and evidence report).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Plan/acquire/measure the six native beta runtime archives. "
                    "The default is a dry-run plan (no network, no writes).",
    )
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES),
                        help="runtime sources JSON (default: installer/runtime_sources.json)")
    parser.add_argument("--target", action="append", default=[],
                        help="target id/alias to measure (repeatable; default: all six)")
    parser.add_argument("--offline-dir", default=None,
                        help="measure pre-downloaded archives from this directory (no network)")
    parser.add_argument("--download", action="store_true",
                        help="download archives from the sources (network; release runner only)")
    parser.add_argument("--cache-dir", default=None,
                        help="download cache (default: .workspace/cache/native-runtimes)")
    parser.add_argument("--dry-run", action="store_true", default=None,
                        help="plan only; conflicts with --offline-dir/--download/--write")
    parser.add_argument("--write", action="store_true",
                        help="write a NEW measured runtime-manifest draft + evidence report")
    parser.add_argument("--out", default=None,
                        help="draft output path (default: .workspace/build/native-runtimes/"
                             "runtime-manifest.measured.json)")
    parser.add_argument("--evidence", default=None,
                        help="evidence report path (default: .workspace/build/native-runtimes/"
                             "evidence.json)")
    parser.add_argument("--force", action="store_true",
                        help="allow replacing an existing output (never the tracked template "
                             "unless explicitly forced)")
    parser.add_argument("--timeout", type=float, default=None,
                        help="per-archive network timeout in seconds")
    parser.add_argument("--max-bytes", type=int, default=None,
                        help="hard per-archive byte limit for downloads")
    parser.add_argument("--host-target", choices=TARGET_ORDER, default=None,
                        help="override the detected host target (tests/diagnostics)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def run(args: argparse.Namespace, *, opener: Callable | None = None) -> int:
    if args.offline_dir and args.download:
        raise SourceError("use either --offline-dir or --download, not both",
                          code="mode-conflict")
    if args.dry_run and (args.offline_dir or args.download or args.write):
        raise SourceError("--dry-run cannot be combined with --offline-dir/--download/--write",
                          code="mode-conflict")
    if args.write and not (args.offline_dir or args.download):
        raise SourceError("--write requires --offline-dir or --download",
                          code="write-requires-measurement")
    selected = resolve_selected_targets(args.target)
    sources = load_sources(args.sources)
    host_target = args.host_target
    host_note = ""
    if host_target is None:
        host_target, host_note = detect_host_target_safe()
    mode = "plan"
    if args.download:
        mode = "download"
    elif args.offline_dir:
        mode = "offline"
    draft_path = Path(args.out).expanduser() if args.out else default_draft_path()
    evidence_path = Path(args.evidence).expanduser() if args.evidence else default_evidence_path()
    if mode == "plan":
        plan = build_plan(sources, selected=selected, host_target=host_target, mode="plan")
        _print_plan(plan, as_json=bool(args.json))
        return EXIT_OK
    offline_dir = Path(args.offline_dir).expanduser() if args.offline_dir else None
    if mode == "offline":
        if offline_dir is None:
            raise SourceError("--offline-dir is required", code="mode-conflict")
        measurements = measure_offline(sources, offline_dir, selected)
    else:
        cache_dir = Path(args.cache_dir).expanduser() if args.cache_dir else default_cache_dir()
        measurements = acquire_download(
            sources, cache_dir, selected, opener=opener,
            timeout=args.timeout, max_bytes=args.max_bytes)
    draft = None
    written = None
    if args.write:
        draft = build_measured_draft(sources, measurements)
        evidence = build_evidence(sources, measurements, selected=selected, mode=mode,
                                  host_target=host_target, host_note=host_note,
                                  sources_path=Path(args.sources),
                                  draft_path=draft_path, evidence_path=evidence_path)
        written = write_outputs(draft, evidence, draft_path=draft_path,
                                evidence_path=evidence_path, force=bool(args.force))
    _print_measurements(measurements, as_json=bool(args.json), draft=draft, written=written)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except SourceError as exc:
        print("error [" + exc.code + "]: " + str(exc), file=sys.stderr)
        return EXIT_USAGE
    except FetchRuntimeError as exc:
        target = (" target=" + exc.target) if exc.target else ""
        print("error [" + exc.code + "]" + target + ": " + str(exc), file=sys.stderr)
        return EXIT_FAILURE
    except OSError as exc:
        print("error [os-error]: " + str(exc), file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())

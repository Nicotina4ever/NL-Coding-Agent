"""Artifact fetching with sha256 + size verification and atomic staging.

Two fetchers are provided:

  * UrllibFetcher - the online path. It streams a component from the release
    base URL through urllib.request, enforces the declared size and sha256, and
    only atomically renames the verified temporary file into place.
  * OfflineBundleFetcher - the no-network path. It resolves each component
    inside a local offline bundle directory (same manifest schema), copies it,
    verifies it and atomically publishes it.

A fetcher only writes the destination cache file (plus a temporary sibling that
is removed on failure); it never installs anything and never executes code.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Protocol

CHUNK_SIZE = 1024 * 1024
DEFAULT_TIMEOUT = 60.0


class ArtifactError(RuntimeError):
    """Base class for artifact acquisition failures."""


class DownloadError(ArtifactError):
    """The artifact could not be downloaded or read."""


class VerificationError(ArtifactError):
    """The artifact bytes do not match the manifest sha256/size."""

    def __init__(self, message: str, *, expected_sha256: str = "",
                 expected_size: int = 0, actual_sha256: str = "",
                 actual_size: int = 0) -> None:
        super().__init__(message)
        self.expected_sha256 = expected_sha256
        self.expected_size = expected_size
        self.actual_sha256 = actual_sha256
        self.actual_size = actual_size


def verify_artifact(path: str | Path, sha256: str, size: int) -> Path:
    """Verify an existing file against the manifest sha256 and size."""
    artifact = Path(path)
    if not artifact.is_file():
        raise VerificationError("artifact is missing: " + str(artifact))
    actual_size = artifact.stat().st_size
    if int(size) >= 0 and actual_size != int(size):
        raise VerificationError("artifact size mismatch: expected " + str(size)
                                + " bytes, got " + str(actual_size),
                                expected_sha256=sha256, expected_size=int(size),
                                actual_size=actual_size)
    digest = hashlib.sha256()
    with artifact.open("rb") as handle:
        while True:
            block = handle.read(CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    actual_sha256 = digest.hexdigest()
    if str(sha256).lower() and actual_sha256 != str(sha256).lower():
        raise VerificationError("artifact sha256 mismatch for " + artifact.name,
                                expected_sha256=sha256, expected_size=int(size),
                                actual_sha256=actual_sha256, actual_size=actual_size)
    return artifact


def _safe_destination(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _publish(temp_path: Path, destination: Path) -> Path:
    os.replace(temp_path, destination)
    return destination


def _cleanup_temp(temp_path: Path) -> None:
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError:
        pass


class Fetcher(Protocol):
    def fetch(self, component: dict, destination: Path) -> Path:
        """Acquire one component into destination (verified) and return it."""


class OfflineBundleFetcher:
    """Resolve components from a local offline-bundle directory (no network)."""

    def __init__(self, bundle_dir: str | Path) -> None:
        self.bundle_dir = Path(bundle_dir).resolve()
        if not self.bundle_dir.is_dir():
            raise ArtifactError("offline bundle is not a directory: " + str(self.bundle_dir))

    def _resolve(self, url: str) -> Path:
        text = str(url)
        relative = text
        if text.startswith("file://"):
            relative = text[len("file://"):]
        relative = relative.replace(chr(92), "/")
        candidate_path = Path(relative)
        if candidate_path.is_absolute() or candidate_path.drive:
            raise ArtifactError("offline bundle component URL must be relative: " + text)
        if any(part == ".." for part in candidate_path.parts):
            raise ArtifactError("offline bundle component URL must not escape the bundle: " + text)
        resolved = (self.bundle_dir / candidate_path).resolve()
        try:
            resolved.relative_to(self.bundle_dir)
        except ValueError as exc:
            raise ArtifactError("offline bundle component escapes the bundle: " + text) from exc
        if not resolved.is_file():
            raise ArtifactError("offline bundle artifact not found: "
                                + resolved.relative_to(self.bundle_dir).as_posix())
        return resolved

    def fetch(self, component: dict, destination: Path) -> Path:
        source = self._resolve(str(component["url"]))
        destination = _safe_destination(Path(destination))
        if destination.exists():
            try:
                verify_artifact(destination, str(component["sha256"]),
                                int(component["size"]))
                return destination
            except VerificationError:
                _cleanup_temp(destination)
        temp_path = destination.with_name(destination.name + ".nlcoding-part")
        _cleanup_temp(temp_path)
        try:
            shutil.copyfile(source, temp_path)
            verify_artifact(temp_path, str(component["sha256"]), int(component["size"]))
            return _publish(temp_path, destination)
        except Exception:
            _cleanup_temp(temp_path)
            raise


class UrllibFetcher:
    """Download a component with urllib, verify it and publish it atomically."""

    def __init__(
        self,
        manifest: dict,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        opener: Callable | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self.manifest = manifest
        self.timeout = float(timeout)
        self._opener = opener or urllib.request.urlopen
        self.max_bytes = max_bytes

    def _url(self, component: dict) -> str:
        from installer.platform_manifest import component_url

        return component_url(self.manifest, component)

    def fetch(self, component: dict, destination: Path) -> Path:
        url = self._url(component)
        if not url.startswith(("http://", "https://")):
            raise DownloadError("refusing non-HTTP artifact URL: " + url)
        expected_size = int(component["size"])
        expected_sha256 = str(component["sha256"])
        if expected_size <= 0 or not expected_sha256:
            raise DownloadError("manifest has no sha256/size for component: "
                               + str(component.get("id")))
        destination = _safe_destination(Path(destination))
        if destination.exists():
            try:
                verify_artifact(destination, expected_sha256, expected_size)
                return destination
            except VerificationError:
                _cleanup_temp(destination)
        temp_path = destination.with_name(destination.name + ".nlcoding-part")
        _cleanup_temp(temp_path)
        digest = hashlib.sha256()
        written = 0
        try:
            with self._opener(url, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200))
                if status < 200 or status >= 300:
                    raise DownloadError("HTTP " + str(status) + " for " + url)
                with temp_path.open("wb") as handle:
                    while True:
                        block = response.read(CHUNK_SIZE)
                        if not block:
                            break
                        written += len(block)
                        if self.max_bytes is not None and written > self.max_bytes:
                            raise DownloadError("download exceeded the configured byte limit")
                        if written > expected_size:
                            raise VerificationError(
                                "download exceeds declared size for " + str(component["id"]),
                                expected_sha256=expected_sha256,
                                expected_size=expected_size,
                                actual_size=written,
                            )
                        digest.update(block)
                        handle.write(block)
                    handle.flush()
                    os.fsync(handle.fileno())
            actual_sha256 = digest.hexdigest()
            if written != expected_size:
                raise VerificationError(
                    "artifact size mismatch for " + str(component["id"]),
                    expected_sha256=expected_sha256, expected_size=expected_size,
                    actual_sha256=actual_sha256, actual_size=written)
            if actual_sha256 != expected_sha256.lower():
                raise VerificationError(
                    "artifact sha256 mismatch for " + str(component["id"]),
                    expected_sha256=expected_sha256, expected_size=expected_size,
                    actual_sha256=actual_sha256, actual_size=written)
            return _publish(temp_path, destination)
        except urllib.error.HTTPError as exc:
            _cleanup_temp(temp_path)
            raise DownloadError("HTTP " + str(exc.code) + " while downloading " + url) from exc
        except urllib.error.URLError as exc:
            _cleanup_temp(temp_path)
            raise DownloadError("network error while downloading " + url + ": "
                                + str(exc.reason)) from exc
        except (OSError, ValueError) as exc:
            _cleanup_temp(temp_path)
            if isinstance(exc, ArtifactError):
                raise
            raise DownloadError("download failed for " + url + ": " + str(exc)) from exc
        except Exception:
            _cleanup_temp(temp_path)
            raise


def make_fetcher(
    manifest: dict,
    *,
    offline_bundle: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable | None = None,
) -> Fetcher:
    """Create the fetcher for this run: local bundle (no network) or urllib."""
    if offline_bundle is not None:
        return OfflineBundleFetcher(offline_bundle)
    return UrllibFetcher(manifest, timeout=timeout, opener=opener)

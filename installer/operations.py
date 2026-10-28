"""Install/update/repair/verify/cache operations for the bootstrapper.

All functions are explicit about what they may write:
  * install/update/repair write only the verified shared cache, one managed
    staging directory next to the target, and the target directory itself;
  * update/repair keep the previous installation as a sibling backup directory
    (never delete it automatically);
  * verify/plan/cache-list/cache-verify are strictly read-only;
  * no function installs system-wide, writes outside the selected target/cache,
    executes downloaded code, or requires a global Python/pip/uv/conda.

Install state is a small JSON document in the target root (install.json) that
records product/version/platform and every installed file with its sha256.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat as stat_module
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Callable

from installer import TOOL_NAME, TOOL_VERSION
from installer.fetcher import (
    ArtifactError,
    Fetcher,
    VerificationError,
    make_fetcher,
    verify_artifact,
)
from installer.platform_manifest import components_for_platform, resolve_platform

INSTALL_STATE_NAME = "install.json"
INSTALL_STATE_SCHEMA = 1
CACHE_ARTIFACTS_DIR = "artifacts"
CHUNK_SIZE = 1024 * 1024
VERSION_UNKNOWN = "(unknown)"


class InstallerError(RuntimeError):
    """Base class for bootstrapper operation failures."""


class TargetError(InstallerError):
    """The requested install target is not acceptable."""


class NotInstalledError(InstallerError):
    """The target does not contain a bootstrapper-managed installation."""


class InstallError(InstallerError):
    """Installation/update/repair could not be completed safely."""


def human_bytes(size: int | float) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            if unit == "B":
                return str(int(value)) + " B"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return str(int(size)) + " B"


def default_cache_dir() -> Path:
    override = os.environ.get("NL_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "~"
        return (Path(base).expanduser() / "NL Coding Agent" / "cache").resolve()
    if sys.platform == "darwin":
        return (Path("~/Library/Caches/nl-coding-agent").expanduser()).resolve()
    base = os.environ.get("XDG_CACHE_HOME") or "~/.cache"
    return (Path(base).expanduser() / "nl-coding-agent").resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _safe_name(text: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    cleaned = "".join(char if char in allowed else "_" for char in str(text))
    return cleaned.strip("._") or "artifact"


def cache_artifact_path(cache_dir: str | Path, component: dict) -> Path:
    sha256 = str(component.get("sha256") or "")
    if not sha256:
        raise ArtifactError("component has no sha256 in the manifest: "
                            + str(component.get("id")))
    url_name = str(component.get("url") or "").rstrip("/").split("/")[-1]
    name = _safe_name(url_name) if url_name else _safe_name(component["id"] + "-"
                                                            + component["version"])
    return Path(cache_dir).resolve() / CACHE_ARTIFACTS_DIR / sha256 / name


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _forbidden_target_roots() -> list[Path]:
    roots: list[Path] = []
    if sys.platform.startswith("win"):
        for name in ("WINDIR", "ProgramFiles", "ProgramFiles(x86)", "ProgramData",
                     "SystemRoot"):
            value = os.environ.get(name)
            if value:
                roots.append(Path(value))
    else:
        for value in ("/usr", "/etc", "/opt", "/bin", "/sbin", "/lib", "/lib64"):
            roots.append(Path(value))
    return roots


def validate_target(target: str | Path, *, existing_install_ok: bool = False) -> Path:
    """Validate a user-selected install target and return its resolved path."""
    resolved = Path(target).expanduser().resolve()
    if not str(target).strip():
        raise TargetError("install target must not be empty")
    if str(resolved) == str(Path(resolved.anchor).resolve()):
        raise TargetError("refusing the filesystem root as an install target: " + str(resolved))
    for forbidden in _forbidden_target_roots():
        try:
            if resolved == forbidden.resolve() or _within(resolved, forbidden):
                raise TargetError("refusing a system/global install location: "
                                  + str(resolved) + "; choose a per-user directory")
        except OSError:
            continue
    if resolved.exists() and not resolved.is_dir():
        raise TargetError("install target exists and is not a directory: " + str(resolved))
    state = install_state_path(resolved)
    if resolved.exists() and any(resolved.iterdir()) and not (existing_install_ok and state.is_file()):
        raise TargetError("install target is not empty: " + str(resolved)
                          + " (choose a new directory, or use update/repair for an existing install)")
    if resolved.is_dir():
        try:
            probe = resolved / (".nlcoding-write-probe-" + uuid.uuid4().hex)
            probe.write_text("probe", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise TargetError("install target is not writable: " + str(resolved)
                              + " (" + str(exc) + ")") from exc
    return resolved


def install_state_path(target: str | Path) -> Path:
    return Path(target) / INSTALL_STATE_NAME


def read_install_state(target: str | Path) -> dict:
    target_path = Path(target)
    state_path = install_state_path(target_path)
    if not state_path.is_file():
        raise NotInstalledError("no bootstrapper installation found in " + str(target_path)
                                + " (missing " + INSTALL_STATE_NAME + ")")
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NotInstalledError("cannot read installation state: " + str(exc)) from exc
    if not isinstance(data, dict) or data.get("schema_version") != INSTALL_STATE_SCHEMA:
        raise NotInstalledError("unsupported installation state schema in " + str(state_path))
    return data


def _write_install_state(staging: Path, state: dict) -> None:
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    (staging / INSTALL_STATE_NAME).write_text(text + chr(10), encoding="utf-8")


def _version_key(value: str) -> tuple:
    parts: list = []
    for token in str(value).replace("-", ".").replace("_", ".").split("."):
        try:
            parts.append((0, int(token)))
        except ValueError:
            parts.append((1, token))
    return tuple(parts)


def _staging_dir(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / ("." + target.name + ".nlcoding-staging-" + uuid.uuid4().hex)
    if staging.exists():
        raise InstallError("staging directory already exists (unexpected): " + str(staging))
    staging.mkdir(parents=True)
    return staging


def _cleanup_staging(staging: Path | None) -> None:
    if staging is None:
        return
    try:
        if Path(staging).exists():
            shutil.rmtree(staging, ignore_errors=True)
    except OSError:
        pass


def _safe_zip_member(member: zipfile.ZipInfo) -> str:
    name = str(member.filename).replace(chr(92), "/")
    if name.endswith("/"):
        return ""
    if not name or name.startswith("/") or name.startswith("./"):
        raise InstallError("unsafe archive entry: " + name)
    parts = [part for part in name.split("/") if part]
    if not parts or any(part == ".." for part in parts):
        raise InstallError("unsafe archive entry: " + name)
    mode = (member.external_attr >> 16) & 0o170000
    if mode and stat_module.S_ISLNK(mode):
        raise InstallError("refusing symlink archive entry: " + name)
    if member.is_dir():
        return ""
    return "/".join(parts)


def _extract_component(archive_path: Path, component: dict, staging: Path,
                       files_out: dict[str, dict]) -> int:
    destination_rel = component.get("destination") or "."
    destination_root = staging if destination_rel == "." else staging / destination_rel
    if component["archive"] == "file":
        target_rel = destination_rel
        if destination_rel == ".":
            target_rel = str(component["url"]).rstrip("/").split("/")[-1]
        target = staging / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = archive_path.read_bytes()
        target.write_bytes(data)
        rel = target.relative_to(staging).as_posix()
        files_out[rel] = {"sha256": hashlib.sha256(data).hexdigest(),
                          "size": len(data), "component": component["id"]}
        return 1
    extracted = 0
    with zipfile.ZipFile(archive_path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            rel_name = _safe_zip_member(member)
            if not rel_name:
                continue
            target_rel = rel_name if destination_rel == "." else destination_rel + "/" + rel_name
            target = staging / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            data = archive.read(member)
            target.write_bytes(data)
            files_out[target_rel] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "component": component["id"],
            }
            extracted += 1
    return extracted


def _obtain_component(component: dict, cache_dir: Path, fetcher: Fetcher,
                      warnings: list[str]) -> tuple[Path, bool]:
    destination = cache_artifact_path(cache_dir, component)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        try:
            verify_artifact(destination, str(component["sha256"]), int(component["size"]))
            return destination, True
        except VerificationError:
            warnings.append("cache artifact failed verification and was discarded: "
                            + str(component["id"]))
            try:
                destination.unlink()
            except OSError:
                pass
    fetched = fetcher.fetch(component, destination)
    verify_artifact(fetched, str(component["sha256"]), int(component["size"]))
    return fetched, False


def _stage_payload(manifest: dict, platform_id: str, target: Path, cache_dir: Path,
                   fetcher: Fetcher) -> tuple[Path, dict]:
    components = components_for_platform(manifest, platform_id)
    staging = _staging_dir(target)
    files: dict[str, dict] = {}
    warnings: list[str] = []
    cache_hits = 0
    downloaded: list[str] = []
    try:
        for component in components:
            archive_path, cached = _obtain_component(component, cache_dir, fetcher, warnings)
            if cached:
                cache_hits += 1
            else:
                downloaded.append(component["id"])
            _extract_component(archive_path, component, staging, files)
            if len(files) == 0:
                continue
        launcher = manifest["platforms"][platform_id]["launcher"]
        if not (staging / launcher).exists():
            warnings.append("launcher not found in the staged payload: " + launcher)
        total_bytes = sum(entry["size"] for entry in files.values())
        state = {
            "schema_version": INSTALL_STATE_SCHEMA,
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "product": dict(manifest["product"]),
            "version": manifest["product"]["version"],
            "platform": platform_id,
            "launcher": launcher,
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "components": [{
                "id": component["id"],
                "kind": component["kind"],
                "version": component["version"],
                "sha256": component["sha256"],
                "size": component["size"],
            } for component in components],
            "files": files,
            "file_count": len(files),
            "total_size": total_bytes,
            "cache_hits": cache_hits,
            "downloaded": downloaded,
            "warnings": warnings,
        }
        _write_install_state(staging, state)
        return staging, state
    except Exception:
        _cleanup_staging(staging)
        raise


def _commit_fresh(staging: Path, target: Path) -> None:
    if target.exists():
        if any(target.iterdir()):
            _cleanup_staging(staging)
            raise TargetError("install target became non-empty during install: " + str(target))
        target.rmdir()
    os.replace(staging, target)


def _commit_update(staging: Path, target: Path) -> Path:
    backup = target.parent / ("." + target.name + ".backup-"
                              + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    counter = 1
    while backup.exists():
        backup = target.parent / ("." + target.name + ".backup-"
                                  + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                                  + "-" + str(counter))
        counter += 1
    try:
        os.replace(target, backup)
    except OSError as exc:
        _cleanup_staging(staging)
        raise InstallError("cannot move the existing installation aside: " + str(exc)) from exc
    try:
        os.replace(staging, target)
    except OSError as exc:
        try:
            os.replace(backup, target)
        except OSError:
            raise InstallError("update failed and the backup could not be restored from "
                               + str(backup) + ": " + str(exc)) from exc
        _cleanup_staging(staging)
        raise InstallError("update failed; the previous installation was restored: "
                           + str(exc)) from exc
    return backup


def _cache_hit(cache_dir: Path, component: dict) -> bool:
    if not str(component.get("sha256") or "") or int(component.get("size") or 0) <= 0:
        return False
    destination = cache_artifact_path(cache_dir, component)
    return destination.is_file() and destination.stat().st_size == int(component["size"])


def plan_install(manifest: dict, *, target: str | Path | None = None,
                 cache_dir: str | Path | None = None, platform_id: str | None = None,
                 offline_bundle: str | Path | None = None) -> dict:
    resolved_platform = resolve_platform(manifest, platform_id)
    components = components_for_platform(manifest, resolved_platform)
    cache = Path(cache_dir).resolve() if cache_dir else default_cache_dir()
    warnings: list[str] = []
    target_state = "unspecified"
    target_path = None
    installable = bool(manifest.get("release_ready"))
    if not manifest.get("release_ready"):
        warnings.append("manifest is a template (release_ready=false); "
                        "use a manifest emitted by scripts/build_release.py")
    if target is not None:
        target_path = Path(target).expanduser().resolve()
        state_path = install_state_path(target_path)
        if not target_path.exists():
            target_state = "absent"
        elif not target_path.is_dir():
            target_state = "not-a-directory"
            installable = False
        elif state_path.is_file():
            try:
                state = read_install_state(target_path)
                target_state = "existing-install:" + str(state.get("version"))
            except NotInstalledError:
                target_state = "non-empty"
                installable = False
        elif any(target_path.iterdir()):
            target_state = "non-empty"
            installable = False
        else:
            target_state = "empty"
    component_plans = []
    download_bytes = 0
    for component in components:
        cached = _cache_hit(cache, component)
        if not cached:
            download_bytes += int(component["size"])
        component_plans.append({
            "id": component["id"],
            "kind": component["kind"],
            "version": component["version"],
            "archive": component["archive"],
            "destination": component["destination"],
            "size": int(component["size"]),
            "sha256": str(component["sha256"]),
            "url": str(component["url"]),
            "cached": cached,
            "optional": bool(component.get("optional", False)),
        })
    return {
        "status": "plan",
        "installable": installable,
        "product": dict(manifest["product"]),
        "platform": resolved_platform,
        "platform_display_name": manifest["platforms"][resolved_platform]["display_name"],
        "launcher": manifest["platforms"][resolved_platform]["launcher"],
        "manifest_status": manifest.get("status"),
        "release_ready": bool(manifest.get("release_ready")),
        "target": str(target_path) if target_path is not None else None,
        "target_state": target_state,
        "cache_dir": str(cache),
        "offline": offline_bundle is not None,
        "components": component_plans,
        "download_bytes": download_bytes,
        "cache_hits": sum(1 for item in component_plans if item["cached"]),
        "warnings": warnings,
        "writes": [],
    }


def install(manifest: dict, target: str | Path, *, cache_dir: str | Path | None = None,
            platform_id: str | None = None, fetcher: Fetcher | None = None,
            offline_bundle: str | Path | None = None) -> dict:
    if not manifest.get("release_ready"):
        raise InstallError("manifest is a template (release_ready=false); refusing to install")
    resolved_platform = resolve_platform(manifest, platform_id)
    target_path = validate_target(target)
    cache = Path(cache_dir).resolve() if cache_dir else default_cache_dir()
    chosen_fetcher = fetcher or make_fetcher(manifest, offline_bundle=offline_bundle)
    staging, state = _stage_payload(manifest, resolved_platform, target_path, cache,
                                    chosen_fetcher)
    try:
        _commit_fresh(staging, target_path)
    except Exception:
        _cleanup_staging(staging)
        raise
    return {
        "status": "installed",
        "product": dict(manifest["product"]),
        "version": manifest["product"]["version"],
        "platform": resolved_platform,
        "target": str(target_path),
        "files": state["file_count"],
        "total_size": state["total_size"],
        "cache_dir": str(cache),
        "cache_hits": state["cache_hits"],
        "downloaded": state["downloaded"],
        "warnings": state["warnings"],
        "offline": offline_bundle is not None,
    }


def update(manifest: dict, target: str | Path, *, cache_dir: str | Path | None = None,
           platform_id: str | None = None, fetcher: Fetcher | None = None,
           offline_bundle: str | Path | None = None,
           allow_downgrade: bool = False) -> dict:
    if not manifest.get("release_ready"):
        raise InstallError("manifest is a template (release_ready=false); refusing to update")
    resolved_platform = resolve_platform(manifest, platform_id)
    target_path = validate_target(target, existing_install_ok=True)
    state = read_install_state(target_path)
    installed_version = str(state.get("version") or "")
    new_version = str(manifest["product"]["version"])
    if installed_version == new_version:
        return {"status": "up-to-date", "version": installed_version,
                "target": str(target_path), "backup": None}
    if (not allow_downgrade
            and _version_key(new_version) < _version_key(installed_version)):
        raise InstallError("refusing to downgrade from " + installed_version
                           + " to " + new_version + " without --allow-downgrade")
    cache = Path(cache_dir).resolve() if cache_dir else default_cache_dir()
    chosen_fetcher = fetcher or make_fetcher(manifest, offline_bundle=offline_bundle)
    staging, new_state = _stage_payload(manifest, resolved_platform, target_path, cache,
                                        chosen_fetcher)
    try:
        backup = _commit_update(staging, target_path)
    except Exception:
        _cleanup_staging(staging)
        raise
    return {
        "status": "updated",
        "previous_version": installed_version,
        "version": new_version,
        "platform": resolved_platform,
        "target": str(target_path),
        "backup": str(backup),
        "files": new_state["file_count"],
        "cache_hits": new_state["cache_hits"],
        "downloaded": new_state["downloaded"],
        "offline": offline_bundle is not None,
    }


def verify_install(target: str | Path) -> dict:
    target_path = Path(target).expanduser().resolve()
    state = read_install_state(target_path)
    files = state.get("files")
    if not isinstance(files, dict) or not files:
        raise NotInstalledError("installation state has no file inventory: " + str(target_path))
    missing: list[str] = []
    modified: list[str] = []
    checked = 0
    checked_bytes = 0
    for rel, entry in sorted(files.items()):
        installed = target_path / str(rel)
        if not installed.is_file():
            missing.append(str(rel))
            continue
        checked += 1
        try:
            actual = _sha256_file(installed)
        except OSError:
            missing.append(str(rel))
            continue
        if actual != str((entry or {}).get("sha256")):
            modified.append(str(rel))
        checked_bytes += installed.stat().st_size
    launcher = str(state.get("launcher") or "")
    launcher_present = bool(launcher) and (target_path / launcher).is_file()
    ok = not missing and not modified and launcher_present
    return {
        "status": "verified" if ok else "verification-failed",
        "ok": ok,
        "target": str(target_path),
        "product": state.get("product"),
        "version": state.get("version"),
        "platform": state.get("platform"),
        "launcher": launcher,
        "launcher_present": launcher_present,
        "checked_files": checked,
        "checked_bytes": checked_bytes,
        "missing": missing,
        "modified": modified,
    }


def repair(manifest: dict, target: str | Path, *, cache_dir: str | Path | None = None,
           platform_id: str | None = None, fetcher: Fetcher | None = None,
           offline_bundle: str | Path | None = None) -> dict:
    if not manifest.get("release_ready"):
        raise InstallError("manifest is a template (release_ready=false); refusing to repair")
    target_path = validate_target(target, existing_install_ok=True)
    report = verify_install(target_path)
    if report["ok"]:
        return {"status": "healthy", "target": str(target_path),
                "version": report.get("version"), "changed": False}
    state = read_install_state(target_path)
    installed_version = str(state.get("version") or "")
    manifest_version = str(manifest["product"]["version"])
    if installed_version != manifest_version:
        raise InstallError("repair requires the manifest for the installed version ("
                           + installed_version + "), got " + manifest_version
                           + "; use update instead")
    resolved_platform = resolve_platform(manifest, platform_id)
    cache = Path(cache_dir).resolve() if cache_dir else default_cache_dir()
    chosen_fetcher = fetcher or make_fetcher(manifest, offline_bundle=offline_bundle)
    staging, new_state = _stage_payload(manifest, resolved_platform, target_path, cache,
                                        chosen_fetcher)
    try:
        backup = _commit_update(staging, target_path)
    except Exception:
        _cleanup_staging(staging)
        raise
    return {
        "status": "repaired",
        "target": str(target_path),
        "version": manifest_version,
        "backup": str(backup),
        "missing": report.get("missing", []),
        "modified": report.get("modified", []),
        "files": new_state["file_count"],
        "cache_hits": new_state["cache_hits"],
        "offline": offline_bundle is not None,
    }


def cache_list(cache_dir: str | Path) -> dict:
    cache = Path(cache_dir).resolve()
    entries: list[dict] = []
    total_bytes = 0
    artifacts = cache / CACHE_ARTIFACTS_DIR
    if artifacts.is_dir():
        for sha_dir in sorted(artifacts.iterdir(), key=lambda item: item.name):
            if not sha_dir.is_dir():
                continue
            for artifact in sorted(sha_dir.iterdir(), key=lambda item: item.name):
                if not artifact.is_file():
                    continue
                size = artifact.stat().st_size
                total_bytes += size
                entries.append({"sha256": sha_dir.name, "name": artifact.name,
                                "path": str(artifact), "size": size})
    return {"cache_dir": str(cache), "entries": entries, "count": len(entries),
            "total_bytes": total_bytes, "human": human_bytes(total_bytes)}


def cache_verify(cache_dir: str | Path) -> dict:
    listing = cache_list(cache_dir)
    failures: list[dict] = []
    checked = 0
    for entry in listing["entries"]:
        checked += 1
        try:
            actual = _sha256_file(Path(entry["path"]))
        except OSError as exc:
            failures.append({"path": entry["path"], "error": str(exc)})
            continue
        if actual != entry["sha256"].lower():
            failures.append({"path": entry["path"], "error": "sha256 mismatch",
                             "expected": entry["sha256"], "actual": actual})
    return {"cache_dir": listing["cache_dir"], "ok": not failures,
            "checked": checked, "failures": failures,
            "total_bytes": listing["total_bytes"]}


def cache_prune(cache_dir: str | Path, *, keep_days: float = 30.0,
                yes: bool = False) -> dict:
    if not yes:
        return {"status": "refused", "cache_dir": str(Path(cache_dir).resolve()),
                "removed": [], "reason": "cache prune requires yes=True (explicit confirmation)"}
    cache = Path(cache_dir).resolve()
    artifacts = cache / CACHE_ARTIFACTS_DIR
    cutoff = time.time() - max(0.0, float(keep_days)) * 86400.0
    removed: list[str] = []
    freed = 0
    if artifacts.is_dir():
        for sha_dir in sorted(artifacts.iterdir(), key=lambda item: item.name):
            if not sha_dir.is_dir():
                continue
            for artifact in sorted(sha_dir.iterdir(), key=lambda item: item.name):
                if not artifact.is_file():
                    continue
                try:
                    if artifact.stat().st_mtime > cutoff:
                        continue
                    size = artifact.stat().st_size
                    artifact.unlink()
                    removed.append(str(artifact))
                    freed += size
                except OSError:
                    continue
            try:
                if not any(sha_dir.iterdir()):
                    sha_dir.rmdir()
            except OSError:
                pass
    return {"status": "pruned", "cache_dir": str(cache), "removed": removed,
            "freed_bytes": freed, "keep_days": float(keep_days)}


def cache_clear(cache_dir: str | Path, *, yes: bool = False) -> dict:
    if not yes:
        return {"status": "refused", "cache_dir": str(Path(cache_dir).resolve()),
                "removed": 0, "reason": "cache clear requires yes=True (explicit confirmation)"}
    cache = Path(cache_dir).resolve()
    artifacts = cache / CACHE_ARTIFACTS_DIR
    removed = 0
    freed = 0
    if artifacts.is_dir():
        for sha_dir in sorted(artifacts.iterdir(), key=lambda item: item.name):
            if not sha_dir.is_dir() or len(sha_dir.name) != 64:
                continue
            try:
                for artifact in sha_dir.iterdir():
                    if artifact.is_file():
                        freed += artifact.stat().st_size
                        artifact.unlink()
                        removed += 1
                sha_dir.rmdir()
            except OSError:
                continue
    return {"status": "cleared", "cache_dir": str(cache), "removed": removed,
            "freed_bytes": freed}

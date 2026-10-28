"""Stage an inspectable one-folder portable payload (stage 6b allowlist).

The source tree is read-only. Files are written only inside the requested output
directory (a NEW or EMPTY directory; existing payloads are never replaced).
This is staging, not an installer and not a clean-directory acceptance test.

Stage-6b allowlist (intentionally narrow):
  * README.md - user-facing overview/quick start;
  * nl_agent.py and the supported launchers (main GUI at the root; the
    doctor/status/self-build launchers live in scripts/launchers/ in the source
    tree and are re-mapped to the payload root under their user-facing names);
  * nl_coding_agent/ - full current application source, including flows/;
  * python/ - exactly one embedded runtime copy (no Scripts/, caches, bytecode);
  * assets/, config/models.yaml, pyproject.toml.

Everything development-only is excluded: tests/, scripts/, installer/, docs/,
.workspace/ (build evidence, release payloads, logs, temp/cache/state scratch),
AGENTS.md, PATCH/ historical evidence, data/, caches, vendor checkouts (crewAI*,
.git) and machine-local config.
The payload is validated for a single runtime copy and for the absence of
absolute workspace paths before the manifest is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core.workspace import WORKSPACE_DIRNAME  # noqa: E402

PAYLOAD_MANIFEST_VERSION = 1
INCLUDED_ROOTS = (
    "README.md",
    "nl_agent.py",
    "nl_coding_agent",
    "python",
    "assets",
    "config/models.yaml",
    "pyproject.toml",
    "NL Coding Agent.bat",
)
# Launcher sources that must appear at the PAYLOAD ROOT under their user-facing
# names even though their development sources live under scripts/launchers/.
LAUNCHER_SOURCE_TO_PAYLOAD = {
    "scripts/launchers/doctor.bat": "doctor.bat",
    "scripts/launchers/status.bat": "status.bat",
    "scripts/launchers/Self-Build Mode.bat": "Self-Build Mode.bat",
    # POSIX beta launch surface (same user-facing names at the payload root).
    "scripts/launchers/NL Coding Agent.sh": "NL Coding Agent.sh",
    "scripts/launchers/NL Coding Agent.command": "NL Coding Agent.command",
    "scripts/launchers/doctor.sh": "doctor.sh",
    "scripts/launchers/status.sh": "status.sh",
    "scripts/launchers/Self-Build Mode.sh": "Self-Build Mode.sh",
}
EXCLUDED_ROOTS = (
    WORKSPACE_DIRNAME,
    ".agents",
    ".git",
    "AGENTS.md",
    "PATCH",
    # Legacy root locations retained defensively so a pre-reorg checkout can
    # never leak build outputs, releases, logs or scratch state into a payload.
    "build",
    "crewAI",
    "crewAI-tools",
    "da_eliminare",
    "data",
    "dist",
    "docs",
    "installer",
    "logs",
    "scripts",
    "state",
    "temp",
    "tests",
)
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "Scripts",
    "venv",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_FILES = {
    "AGENTS.md",
    "config/voicebridge.yaml",
    "config/voicebridge.local.yaml",
    "SHA256_MANIFEST.json",
}
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".bat", ".ps1",
    ".ini", ".cfg", ".sh", ".command",
}
OLD_ROOT_PATTERN = re.compile(r"K:/+AI/+Coding[ ]+Agent", re.IGNORECASE)
MAX_ABSOLUTE_PATH_SCAN_BYTES = 2 * 1024 * 1024


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            if unit == "B":
                return str(int(value)) + " B"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _normalise(text: str) -> str:
    return text.replace(chr(92), "/")


def _payload_relative(source: Path, path: Path) -> str:
    """Return the path a source file gets in the payload (launchers are re-mapped)."""
    relative = path.relative_to(source).as_posix()
    return LAUNCHER_SOURCE_TO_PAYLOAD.get(relative, relative)


def _is_excluded_file(source: Path, path: Path) -> bool:
    return path.relative_to(source).as_posix() in EXCLUDED_FILES


def _iter_source_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in INCLUDED_ROOTS:
        root = source / root_name
        if not root.exists():
            continue
        if root.is_file():
            if (
                root.suffix.lower() not in EXCLUDED_SUFFIXES
                and not _is_excluded_file(source, root)
            ):
                files.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(
                name for name in dirnames if name not in EXCLUDED_DIR_NAMES
            )
            for filename in sorted(filenames):
                path = Path(dirpath) / filename
                if path.is_symlink():
                    continue
                if path.suffix.lower() in EXCLUDED_SUFFIXES:
                    continue
                if _is_excluded_file(source, path):
                    continue
                files.append(path)
    for source_rel in LAUNCHER_SOURCE_TO_PAYLOAD:
        path = source / source_rel
        if path.is_file() and path not in files:
            files.append(path)
    return files


def _top_level_entries(source: Path, files: list[Path]) -> list[dict]:
    entries: dict[str, dict] = {}
    for path in files:
        key = _payload_relative(source, path).split("/")[0]
        entry = entries.setdefault(key, {"path": key, "size": 0, "files": 0})
        entry["size"] += path.stat().st_size
        entry["files"] += 1
    return [entries[key] for key in sorted(entries)]


def _tree_sha256(source: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: _payload_relative(source, item)):
        relative = _normalise(_payload_relative(source, path))
        digest.update(relative.encode("utf-8"))
        digest.update(chr(0).encode("utf-8"))
        digest.update(_sha256_file(path).encode("utf-8"))
        digest.update(chr(0).encode("utf-8"))
    return digest.hexdigest()


def _runtime_checks(source: Path, files: list[Path]) -> dict:
    python_copies = sorted(
        _normalise(path.relative_to(source).as_posix())
        for path in files
        if path.name.lower() == "python.exe"
    )
    crewai_packages = sorted({
        _normalise(path.relative_to(source).as_posix()).split("/site-packages/crewai/")[0]
        + "/site-packages/crewai"
        for path in files
        if "/site-packages/crewai/" in _normalise(path.relative_to(source).as_posix())
    })
    return {
        "python_runtime_copies": len(python_copies),
        "python_runtime_paths": python_copies,
        "crewai_package_copies": len(crewai_packages),
        "crewai_package_paths": crewai_packages,
        "single_runtime_copy": len(python_copies) == 1,
    }


def _absolute_path_hits(source: Path, files: list[Path]) -> list[dict]:
    source_text = _normalise(str(source)).casefold()
    hits: list[dict] = []
    for path in files:
        relative = _normalise(path.relative_to(source).as_posix())
        if relative.startswith("python/"):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_ABSOLUTE_PATH_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        normalised = _normalise(text)
        if source_text in normalised.casefold() or OLD_ROOT_PATTERN.search(normalised):
            hits.append({"path": relative})
    return hits


def _validate_payload(source: Path, files: list[Path]) -> dict:
    runtime = _runtime_checks(source, files)
    if not runtime["single_runtime_copy"]:
        raise ValueError(
            "payload must contain exactly one embedded Python runtime copy; found "
            + str(runtime["python_runtime_copies"]) + ": "
            + ", ".join(runtime["python_runtime_paths"][:5])
        )
    absolute_hits = _absolute_path_hits(source, files)
    if absolute_hits:
        raise ValueError(
            "payload contains absolute workspace paths: "
            + ", ".join(hit["path"] for hit in absolute_hits[:5])
        )
    top_level = {_payload_relative(source, path).split("/")[0] for path in files}
    excluded_present = sorted(top_level.intersection(EXCLUDED_ROOTS))
    if excluded_present:
        raise ValueError("payload contains excluded top-level paths: "
                         + ", ".join(excluded_present))
    return {
        "runtime": runtime,
        "absolute_path_hits": absolute_hits,
        "excluded_top_level_present": excluded_present,
        "checked": True,
    }


def _manifest(
    source: Path,
    output: Path,
    files: list[Path],
    dry_run: bool,
    tree_sha256: str,
    checks: dict,
) -> dict:
    total_size = sum(path.stat().st_size for path in files)
    payload_dist_root = source / WORKSPACE_DIRNAME / "dist"
    output_location = "dist" if output.parent == payload_dist_root else "external"
    return {
        "payload_manifest_version": PAYLOAD_MANIFEST_VERSION,
        "source_name": source.name,
        "output_name": output.name,
        "output_location": output_location,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "file_count": len(files),
        "total_size": total_size,
        "tree_sha256": tree_sha256,
        "included_roots": list(INCLUDED_ROOTS),
        "launcher_source_to_payload": dict(LAUNCHER_SOURCE_TO_PAYLOAD),
        "excluded_roots": list(EXCLUDED_ROOTS),
        "excluded_directory_names": sorted(EXCLUDED_DIR_NAMES),
        "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
        "excluded_files": sorted(EXCLUDED_FILES),
        "top_level": _top_level_entries(source, files),
        "payload_checks": checks,
    }


def _validate_output(source: Path, output: Path, dry_run: bool = False) -> None:
    if output == source:
        raise ValueError("output directory must not be the source tree")
    payload_dist_root = source / WORKSPACE_DIRNAME / "dist"
    if output.is_relative_to(source) and not output.is_relative_to(payload_dist_root):
        raise ValueError(
            "output directory must be outside the source tree or under .workspace/dist/"
        )
    if output.exists():
        if not output.is_dir():
            raise ValueError("output path exists and is not a directory")
        if any(output.iterdir()) and not dry_run:
            raise ValueError("output directory is not empty")


def _stage(source: Path, output: Path, files: list[Path]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for path in files:
        relative = Path(_payload_relative(source, path))
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        if destination.suffix.lower() in {".sh", ".command"}:
            try:
                os.chmod(destination, 0o755)
            except OSError:
                pass


def _print_summary(manifest: dict) -> None:
    print("Portable payload staging plan")
    print(f"Source name: {manifest['source_name']}")
    print(f"Output name: {manifest['output_name']} ({manifest['output_location']})")
    print(f"Files: {manifest['file_count']}")
    print(f"Size: {_human_size(manifest['total_size'])}")
    print(f"Tree sha256: {manifest['tree_sha256']}")
    print(f"Single runtime copy: {manifest['payload_checks']['runtime']['single_runtime_copy']}")
    print(f"Dry run: {'yes' if manifest['dry_run'] else 'no'}")
    print("Top-level entries:")
    for entry in manifest["top_level"]:
        print(
            f"  {entry['path']}: {entry['files']} file(s), "
            f"{_human_size(entry['size'])}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=".", help="Source workspace root")
    parser.add_argument(
        "--output",
        default=None,
        help="Destination payload directory (default: <source>/.workspace/dist/portable-release)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan without copying")
    parser.add_argument("--json", action="store_true", help="Print the manifest as JSON")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    output = (
        Path(args.output).resolve()
        if args.output
        else source / WORKSPACE_DIRNAME / "dist" / "portable-release"
    )
    if not source.is_dir():
        print(f"error: source directory not found: {source}", file=sys.stderr)
        return 2

    try:
        _validate_output(source, output, dry_run=args.dry_run)
        files = _iter_source_files(source)
        checks = _validate_payload(source, files)
        tree_sha256 = "" if args.dry_run else _tree_sha256(source, files)
        manifest = _manifest(source, output, files, args.dry_run, tree_sha256, checks)
        if not args.dry_run:
            _stage(source, output, files)
            (output / "payload_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        _print_summary(manifest)
        if args.dry_run:
            print("No files were written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

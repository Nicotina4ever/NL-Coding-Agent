"""Stage an inspectable one-folder portable payload.

The source tree is read-only. Files are written only inside the requested output
directory. This is staging, not an installer and not a clean-directory acceptance
test.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

INCLUDED_ROOTS = (
    "nl_agent.py",
    "nl_coding_agent",
    "python",
    "assets",
    "config",
    "pyproject.toml",
    "Self-Build Mode.bat",
    "NL Coding Agent.bat",
)
EXCLUDED_ROOTS = (
    ".git",
    ".agents",
    "build",
    "crewAI",
    "crewAI-tools",
    "data",
    "dist",
    "docs",
    "logs",
    "scripts",
    "state",
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
    "config/voicebridge.yaml",
    "config/voicebridge.local.yaml",
}


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


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
    return files


def _top_level_entries(source: Path, files: list[Path]) -> list[dict]:
    entries: dict[str, dict] = {}
    for path in files:
        relative = path.relative_to(source)
        key = relative.parts[0]
        entry = entries.setdefault(key, {"path": key, "size": 0, "files": 0})
        entry["size"] += path.stat().st_size
        entry["files"] += 1
    return [entries[key] for key in sorted(entries)]


def _manifest(
    source: Path,
    output: Path,
    files: list[Path],
    dry_run: bool,
) -> dict:
    total_size = sum(path.stat().st_size for path in files)
    return {
        "source": str(source),
        "output": str(output),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "file_count": len(files),
        "total_size": total_size,
        "included_roots": list(INCLUDED_ROOTS),
        "excluded_roots": list(EXCLUDED_ROOTS),
        "excluded_directory_names": sorted(EXCLUDED_DIR_NAMES),
        "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
        "excluded_files": sorted(EXCLUDED_FILES),
        "top_level": _top_level_entries(source, files),
    }


def _validate_output(source: Path, output: Path) -> None:
    if output == source:
        raise ValueError("output directory must not be the source tree")
    if output.is_relative_to(source) and not output.is_relative_to(source / "dist"):
        raise ValueError("output directory must be outside the source tree or under dist/")
    if output.exists():
        if not output.is_dir():
            raise ValueError("output path exists and is not a directory")
        if any(output.iterdir()):
            raise ValueError("output directory is not empty")


def _stage(source: Path, output: Path, files: list[Path]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for path in files:
        relative = path.relative_to(source)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def _print_summary(manifest: dict) -> None:
    print("Portable payload staging plan")
    print(f"Source: {manifest['source']}")
    print(f"Output: {manifest['output']}")
    print(f"Files: {manifest['file_count']}")
    print(f"Size: {_human_size(manifest['total_size'])}")
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
        help="Destination payload directory (default: <source>/dist/portable-release)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan without copying")
    parser.add_argument("--json", action="store_true", help="Print the manifest as JSON")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    output = Path(args.output).resolve() if args.output else source / "dist" / "portable-release"
    if not source.is_dir():
        print(f"error: source directory not found: {source}", file=sys.stderr)
        return 2

    try:
        _validate_output(source, output)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        files = _iter_source_files(source)
        manifest = _manifest(source, output, files, args.dry_run)
        if not args.dry_run:
            _stage(source, output, files)
            (output / "payload_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except OSError as exc:
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

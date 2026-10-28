#!/usr/bin/env python3
"""Read-only distribution audit for the NL Coding Agent workspace.

The audit measures the working tree, separates protected vendor/runtime trees,
finds generated artifacts and duplicate files, and reports declared Python
dependencies. It never deletes, moves, or modifies anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tomllib
from pathlib import Path

PROTECTED_NAMES = ("python", "crewAI", "crewAI-tools")
CACHE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"}
BUILD_NAMES = {"build", "dist", "htmlcov", ".tox", ".nox"}
DUPLICATE_EXCLUDED_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "data",
    "logs",
    *PROTECTED_NAMES,
}
MAX_DUPLICATE_FILE_SIZE = 5 * 1024 * 1024
MAX_DUPLICATE_GROUPS = 50
MAX_DUPLICATE_PATHS = 20
MAX_GENERATED_ENTRIES = 20
DEFAULT_TOP = 10


def _is_generated_name(name: str) -> bool:
    return name in CACHE_NAMES or name in BUILD_NAMES or name.endswith(".egg-info")


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return ()


def _generated_root(parts: tuple[str, ...]) -> str | None:
    for index, part in enumerate(parts):
        if _is_generated_name(part):
            return "/".join(parts[: index + 1])
    return None


def _skip_duplicate(parts: tuple[str, ...]) -> bool:
    return any(part in DUPLICATE_EXCLUDED_NAMES or _is_generated_name(part) for part in parts)


def _read_dependencies(root: Path) -> list[str]:
    dependencies: list[str] = []

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project = data.get("project", {})
            if isinstance(project, dict):
                for item in project.get("dependencies", []) or []:
                    if isinstance(item, str):
                        dependencies.append(item)
                optional = project.get("optional-dependencies", {})
                if isinstance(optional, dict):
                    for group in optional.values():
                        for item in group or []:
                            if isinstance(item, str):
                                dependencies.append(item)
        except (OSError, tomllib.TOMLDecodeError):
            pass

    requirements = root / "requirements.txt"
    if requirements.is_file():
        try:
            for raw in requirements.read_text(encoding="utf-8").splitlines():
                line = raw.split("#", 1)[0].strip()
                if not line or line.startswith("-"):
                    continue
                dependencies.append(line)
        except OSError:
            pass

    seen: set[str] = set()
    unique: list[str] = []
    for dependency in dependencies:
        key = dependency.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(dependency.strip())
    return unique


def _scan(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")

    top_sizes: dict[str, int] = {}
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        top_sizes[entry.name] = 0
                except OSError:
                    continue
    except OSError as exc:
        raise OSError(f"cannot read {root}: {exc}") from exc

    protected_sizes = {name: 0 for name in PROTECTED_NAMES if (root / name).is_dir()}
    generated_sizes: dict[str, int] = {}
    duplicate_candidates: list[tuple[Path, int, str]] = []
    skipped_large_files = 0
    walk_errors = 0
    total_size = 0

    def on_error(_: OSError) -> None:
        nonlocal walk_errors
        walk_errors += 1

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=on_error):
        current = Path(dirpath)
        parts = _relative_parts(current, root)

        if ".git" in parts:
            dirnames[:] = []
            continue

        top_name = parts[0] if parts else None
        generated = _generated_root(parts)

        for filename in filenames:
            path = current / filename
            try:
                if path.is_symlink():
                    continue
                size = path.stat().st_size
            except OSError:
                walk_errors += 1
                continue

            total_size += size
            if top_name is not None:
                top_sizes[top_name] = top_sizes.get(top_name, 0) + size
                if top_name in protected_sizes:
                    protected_sizes[top_name] += size
            if generated is not None and top_name not in protected_sizes:
                generated_sizes[generated] = generated_sizes.get(generated, 0) + size

            if size <= 0 or _skip_duplicate(parts + (filename,)):
                continue
            if size > MAX_DUPLICATE_FILE_SIZE:
                skipped_large_files += 1
                continue
            duplicate_candidates.append((path, size, "/".join(parts + (filename,))))

    hashes: dict[str, dict] = {}
    for path, size, relative in duplicate_candidates:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            walk_errors += 1
            continue
        key = digest.hexdigest()
        bucket = hashes.setdefault(key, {"size": size, "paths": []})
        bucket["paths"].append(relative)

    duplicate_groups = []
    for digest, bucket in hashes.items():
        paths = sorted(bucket["paths"])
        if len(paths) < 2:
            continue
        duplicate_groups.append(
            {
                "sha256": digest,
                "size": bucket["size"],
                "paths": paths[:MAX_DUPLICATE_PATHS],
                "path_count": len(paths),
                "wasted_bytes": bucket["size"] * (len(paths) - 1),
            }
        )
    duplicate_groups.sort(key=lambda item: item["wasted_bytes"], reverse=True)

    top_directories = [
        {"path": name, "size": size}
        for name, size in sorted(top_sizes.items(), key=lambda item: item[1], reverse=True)
        if size > 0
    ][:DEFAULT_TOP]

    protected = [
        {"path": name, "size": size}
        for name, size in sorted(protected_sizes.items(), key=lambda item: item[1], reverse=True)
    ]

    generated = [
        {"path": name, "size": size}
        for name, size in sorted(generated_sizes.items(), key=lambda item: item[1], reverse=True)
    ][:MAX_GENERATED_ENTRIES]

    return {
        "root": str(root),
        "total_size": total_size,
        "top_directories": top_directories,
        "protected": protected,
        "generated": generated,
        "duplicate_groups": duplicate_groups[:MAX_DUPLICATE_GROUPS],
        "dependencies": _read_dependencies(root),
        "skipped_large_files": skipped_large_files,
        "walk_errors": walk_errors,
    }


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024.0 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} TiB"


def _format_entries(entries: list[dict], limit: int | None = None) -> list[str]:
    lines = []
    for entry in entries[:limit] if limit else entries:
        lines.append(f"- `{entry['path']}`: {format_size(entry['size'])} ({entry['size']:,} bytes)")
    return lines or ["- none"]


def human_report(result: dict) -> str:
    lines = [
        "Distribution audit",
        "==================",
        f"Root: {result['root']}",
        f"Total working-tree size (excluding .git): {format_size(result['total_size'])} "
        f"({result['total_size']:,} bytes)",
        "",
        "Top-level directories:",
        *_format_entries(result["top_directories"]),
        "",
        "Protected trees (never touch):",
        *_format_entries(result["protected"]),
        "",
        "Generated artifacts and caches:",
        *_format_entries(result["generated"]),
        "",
        "Duplicate groups:",
    ]
    if result["duplicate_groups"]:
        for group in result["duplicate_groups"][:10]:
            lines.append(
                f"- {group['sha256'][:16]}...: {format_size(group['size'])} x "
                f"{group['path_count']} files, {format_size(group['wasted_bytes'])} reclaimable"
            )
            for path in group["paths"][:5]:
                lines.append(f"  - {path}")
            if group["path_count"] > 5:
                lines.append(f"  - ... {group['path_count'] - 5} more")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "Declared Python dependencies:",
            *([f"- {item}" for item in result["dependencies"]] or ["- none"]),
            "",
            f"Large files skipped by duplicate hashing (>5 MiB): {result['skipped_large_files']}",
            f"Walk errors: {result['walk_errors']}",
            "",
            "No files were deleted, moved, or modified by this audit.",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Workspace root to audit (default: current directory)")
    parser.add_argument("--json", action="store_true", help="Emit the audit as JSON")
    args = parser.parse_args(argv)

    try:
        result = _scan(Path(args.root))
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(human_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

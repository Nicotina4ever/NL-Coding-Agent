"""Project scanner — language/framework detection for an arbitrary folder."""
from __future__ import annotations

import json
from pathlib import Path


# Maps file names or extensions to (language, framework)
_INDICATOR_FILES: list[tuple[str, str, str]] = [
    # (filename_or_glob, language, framework)
    ("pyproject.toml",      "Python",       "pyproject"),
    ("requirements.txt",    "Python",       "pip"),
    ("setup.py",            "Python",       "setuptools"),
    ("setup.cfg",           "Python",       "setuptools"),
    ("Pipfile",             "Python",       "pipenv"),
    ("poetry.lock",         "Python",       "poetry"),
    ("package.json",        "JavaScript",   "node"),
    ("pnpm-lock.yaml",      "JavaScript",   "pnpm"),
    ("yarn.lock",           "JavaScript",   "yarn"),
    ("package-lock.json",   "JavaScript",   "npm"),
    ("Cargo.toml",          "Rust",         "cargo"),
    ("go.mod",              "Go",           "go modules"),
    ("pom.xml",             "Java",         "maven"),
    ("build.gradle",        "Java/Kotlin",  "gradle"),
    ("CMakeLists.txt",      "C/C++",        "cmake"),
    ("Makefile",            "C/C++",        "make"),
    ("*.csproj",            "C#",           "dotnet"),
    ("*.sln",               "C#",           "dotnet"),
    ("Gemfile",             "Ruby",         "bundler"),
    ("composer.json",       "PHP",          "composer"),
    ("docker-compose.yml",  "Docker",       "compose"),
    ("docker-compose.yaml", "Docker",       "compose"),
    ("Dockerfile",          "Docker",       "dockerfile"),
    (".github",             "DevOps",       "github-actions"),
]

_EXT_LANGS: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "JavaScript", ".tsx": "TypeScript",
    ".rs": "Rust", ".go": "Go", ".java": "Java", ".kt": "Kotlin",
    ".cs": "C#", ".cpp": "C++", ".c": "C", ".h": "C/C++",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".dart": "Dart",
    ".lua": "Lua", ".r": "R", ".m": "MATLAB/Octave",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sh": "Shell", ".ps1": "PowerShell", ".bat": "Batch",
    ".md": "Markdown", ".yaml": "YAML", ".yml": "YAML", ".json": "JSON",
    ".toml": "TOML",
}

_IGNORE_DIRS = {
    "__pycache__", ".git", ".svn", ".hg", "node_modules",
    ".venv", "venv", "env", ".env", "dist", "build",
    "target", "bin", "obj", ".idea", ".vscode",
    "python", "crewAI", "crewAI-tools",  # vendor dirs in this workspace
}

_DOC_EXTENSIONS = {".md", ".txt", ".rst", ".adoc"}
_TOP_DOCS = {"agents.md", "readme.md", "readme.txt", "architecture.md",
             "contributing.md", "changelog.md", "license"}


def scan_project(root: Path, max_files: int = 3000) -> dict:
    """
    Scan a project folder and return a dict of facts.
    Does NOT modify any files.
    """
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    detected_languages: dict[str, int] = {}
    detected_frameworks: list[str] = []
    extensions: dict[str, int] = {}
    doc_files: list[str] = []
    all_files: list[str] = []
    top_build_files: list[str] = []

    # Check top-level indicator files
    for indicator, lang, framework in _INDICATOR_FILES:
        if "*" in indicator:
            # glob pattern
            matches = list(root.glob(indicator))
            if matches:
                detected_languages[lang] = detected_languages.get(lang, 0) + 1
                if framework not in detected_frameworks:
                    detected_frameworks.append(framework)
                for m in matches[:3]:
                    top_build_files.append(m.name)
        else:
            p = root / indicator
            if p.exists():
                detected_languages[lang] = detected_languages.get(lang, 0) + 1
                if framework not in detected_frameworks:
                    detected_frameworks.append(framework)
                top_build_files.append(indicator)

    # Walk the tree
    try:
        for item in _walk_limited(root, max_files):
            rel = str(item.relative_to(root))
            all_files.append(rel)
            ext = item.suffix.lower()
            extensions[ext] = extensions.get(ext, 0) + 1
            lang = _EXT_LANGS.get(ext)
            if lang:
                detected_languages[lang] = detected_languages.get(lang, 0) + 1
            if ext in _DOC_EXTENSIONS:
                doc_files.append(rel)
    except Exception:
        pass

    primary_language = max(detected_languages, key=detected_languages.get) if detected_languages else "Unknown"

    return {
        "root": str(root),
        "primary_language": primary_language,
        "languages": dict(sorted(detected_languages.items(), key=lambda kv: -kv[1])),
        "frameworks": detected_frameworks,
        "top_build_files": list(dict.fromkeys(top_build_files)),  # dedup preserving order
        "extension_counts": dict(sorted(extensions.items(), key=lambda kv: -kv[1])[:30]),
        "doc_files": doc_files[:200],
        "file_count": len(all_files),
        "files_sample": all_files[:500],
    }


def _walk_limited(root: Path, max_files: int):
    """Yield file Paths, skipping ignored dirs, up to max_files."""
    count = 0
    stack = [root]
    while stack and count < max_files:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except PermissionError:
            continue
        for entry in entries:
            if count >= max_files:
                break
            if entry.is_dir():
                if entry.name not in _IGNORE_DIRS and not entry.name.startswith("."):
                    stack.append(entry)
            elif entry.is_file():
                yield entry
                count += 1

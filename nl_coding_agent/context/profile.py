"""Persisted project intelligence and selective context retrieval (P1).

The old mission prompt read every ``.py``/``.toml`` file from a sorted walk until an
18k character budget was exhausted, so a mission about one module could receive
unrelated files and miss the relevant one. This module builds a bounded, persisted
profile of the project (languages, test command, entry points, modules, docs) and
selects the files/line ranges that actually match a mission goal, with a reason
for every selected file.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from nl_coding_agent.persistence.database import init_db

MAX_SOURCE_FILES = 1500
MAX_READ_BYTES = 400_000
PROFILE_MAX_AGE_S = 24 * 60 * 60
IGNORED_DIRS = {
    ".git", ".hg", ".svn", "data", ".workspace", "__pycache__", "node_modules",
    "python", "vscode", "dist", "build", ".build", "out", "out-vscode-min",
    "da_eliminare", "ParcoTest", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "venv", ".venv",
}
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
                   ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"}
DOC_SUFFIXES = {".md", ".txt", ".rst"}
KEY_DOC_NAMES = ("AGENTS.md", "README.md", "docs/README.md",
                 "docs/CURRENT_STATE.md", "CLAUDE.md")
_PATH_RE = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+[/\\])+[\w.-]+\.(?:py|ts|tsx|js|jsx|json|toml|ya?ml|md|txt|rst|cfg|ini))"
)
_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9_]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db():
    return init_db()


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5, stdin=subprocess.DEVNULL, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def goal_tokens(text: str) -> list[str]:
    """Identifier-aware tokens used for path/symbol matching."""
    tokens: list[str] = []
    for raw in _TOKEN_SPLIT_RE.split(str(text or "")):
        if not raw:
            continue
        for part in _CAMEL_RE.split(raw):
            for piece in part.split("_"):
                lowered = piece.strip().lower()
                if len(lowered) >= 3 and lowered not in tokens:
                    tokens.append(lowered)
    return tokens


def mentioned_paths(text: str) -> list[str]:
    """Project-relative paths explicitly written in the objective."""
    result: list[str] = []
    for match in _PATH_RE.findall(str(text or "")):
        normalized = match.replace("\\", "/").lstrip("./")
        if normalized and normalized not in result:
            result.append(normalized)
    return result


@dataclass
class ProjectProfile:
    root: str = ""
    name: str = ""
    primary_language: str = "Unknown"
    languages: dict = field(default_factory=dict)
    frameworks: list = field(default_factory=list)
    test_command: str = ""
    entry_points: list = field(default_factory=list)
    key_docs: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    source_files: list = field(default_factory=list)
    file_count: int = 0
    git_head: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "name": self.name,
            "primary_language": self.primary_language,
            "languages": dict(self.languages),
            "frameworks": list(self.frameworks),
            "test_command": self.test_command,
            "entry_points": list(self.entry_points),
            "key_docs": list(self.key_docs),
            "modules": list(self.modules),
            "source_files": list(self.source_files),
            "file_count": int(self.file_count),
            "git_head": self.git_head,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, value) -> "ProjectProfile":
        data = value if isinstance(value, dict) else {}
        profile = cls()
        for field_name in cls.__dataclass_fields__:  # type: ignore[attr-defined]
            if field_name in data:
                setattr(profile, field_name, data[field_name])
        return profile


def _iter_project_files(root: Path, *, max_files: int = MAX_SOURCE_FILES):
    """Bounded walk that never descends into generated, vendor or user-data trees."""
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
                if not entry.is_file():
                    continue
                if entry.stat().st_size > MAX_READ_BYTES:
                    continue
            except OSError:
                continue
            seen += 1
            yield entry


def build_profile(root: Path | str, *, project_id: int | None = None) -> ProjectProfile:
    root = Path(root).resolve()
    profile = ProjectProfile(root=str(root), name=root.name, generated_at=_now())
    try:
        from nl_coding_agent.projects.scanner import scan_project

        facts = scan_project(root)
        profile.primary_language = str(facts.get("primary_language") or "Unknown")
        profile.languages = dict(facts.get("languages") or {})
        profile.frameworks = list(facts.get("frameworks") or [])
        profile.file_count = int(facts.get("file_count") or 0)
    except Exception:
        pass
    try:
        from nl_coding_agent.tools.verification import detect_test_command

        profile.test_command = detect_test_command(root)
    except Exception:
        profile.test_command = ""
    profile.git_head = _git_head(root)

    sources: list[dict] = []
    docs: list[str] = []
    entry_points: list[str] = []
    modules: dict[str, int] = {}
    for path in _iter_project_files(root):
        relative = _safe_relative(path, root)
        suffix = path.suffix.lower()
        if relative.count("/") == 0 and suffix in (SOURCE_SUFFIXES | DOC_SUFFIXES):
            entry_points.append(relative)
        top = relative.split("/", 1)[0]
        if "/" in relative and top not in IGNORED_DIRS:
            modules[top] = modules.get(top, 0) + 1
        if relative in KEY_DOC_NAMES or (suffix in DOC_SUFFIXES and relative.count("/") <= 1):
            docs.append(relative)
        if suffix in SOURCE_SUFFIXES:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            sources.append({"path": relative, "size": size, "ext": suffix})
    # Prefer real source files over generated config noise when the cap is hit.
    sources.sort(key=lambda item: (item["ext"] not in {".py", ".ts", ".tsx", ".js"},
                                  item["path"]))
    profile.source_files = sources[:MAX_SOURCE_FILES]
    profile.key_docs = docs[:12]
    profile.entry_points = entry_points[:12]
    profile.modules = [
        {"name": name, "files": count}
        for name, count in sorted(modules.items(), key=lambda kv: -kv[1])[:20]
    ]
    return profile


def save_profile(project_id: int, profile: ProjectProfile) -> None:
    conn = _db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO project_profiles(project_id, root, profile_json, updated_at) "
                "VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET "
                "root=excluded.root, profile_json=excluded.profile_json, updated_at=excluded.updated_at",
                (int(project_id), profile.root,
                 json.dumps(profile.to_dict(), ensure_ascii=False), _now()),
            )
    finally:
        conn.close()


def load_profile(project_id: int) -> ProjectProfile | None:
    conn = _db()
    try:
        row = conn.execute(
            "SELECT profile_json FROM project_profiles WHERE project_id=?",
            (int(project_id),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return ProjectProfile.from_dict(json.loads(row["profile_json"] or "{}"))
    except (TypeError, ValueError):
        return None


def ensure_profile(project_id: int, root: Path | str, *,
                   max_age_s: float = PROFILE_MAX_AGE_S) -> ProjectProfile:
    """Return a cached profile, rebuilding it only when missing, stale or re-rooted."""
    resolved = str(Path(root).resolve())
    cached = load_profile(int(project_id))
    if cached is not None and cached.root == resolved and cached.generated_at:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(cached.generated_at)).total_seconds()
        except ValueError:
            age = max_age_s + 1
        if age <= max_age_s:
            return cached
    profile = build_profile(root, project_id=project_id)
    save_profile(int(project_id), profile)
    return profile


def profile_summary_text(profile: ProjectProfile, *, max_chars: int = 2500) -> str:
    languages = ", ".join(
        name + " (" + str(count) + ")" for name, count in list(profile.languages.items())[:6]
    ) or profile.primary_language
    modules = ", ".join(item.get("name", "") for item in profile.modules[:12])
    docs = ", ".join(profile.key_docs[:8])
    entries = ", ".join(profile.entry_points[:8])
    lines = [
        "PROJECT PROFILE (persisted scan; verify before editing):",
        "- Root: " + profile.root,
        "- Primary language: " + profile.primary_language + (" [" + languages + "]" if languages else ""),
        "- Frameworks: " + (", ".join(profile.frameworks) or "(none detected)"),
        "- Test command: " + (profile.test_command or "(not detected)"),
        "- Entry points: " + (entries or "(none detected)"),
        "- Key docs: " + (docs or "(none detected)"),
        "- Modules: " + (modules or "(flat project)"),
        "- Git head: " + (profile.git_head or "(no git)") + " · files scanned: " + str(profile.file_count),
    ]
    text = "\n".join(lines)
    return text[:max_chars]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _excerpt_for_tokens(text: str, tokens: Iterable[str], *, max_chars: int = 2600,
                        max_lines: int = 60) -> str:
    wanted = [token for token in tokens if token]
    lines = text.splitlines()
    if not lines:
        return ""
    selected: list[int] = []
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(token in lowered for token in wanted):
            selected.extend(range(max(0, index - 2), min(len(lines), index + 3)))
    if selected:
        unique = sorted(set(selected))[:max_lines]
        body = "\n".join(str(number + 1) + ": " + lines[number] for number in unique)
        header = "[matching lines from " + str(len(lines)) + " total]"
    else:
        body = "\n".join(str(number + 1) + ": " + line
                         for number, line in enumerate(lines[:max_lines]))
        header = "[first " + str(min(max_lines, len(lines))) + " of " + str(len(lines)) + " lines]"
    return (header + "\n" + body)[:max_chars]


def select_relevant_files(root: Path | str, goal: str, profile: ProjectProfile | None,
                          *, budget_chars: int = 14_000,
                          max_files: int = 8) -> list[dict]:
    """Rank project files against a mission objective and return bounded excerpts.

    Every selection carries a human-readable reason; path mentions in the objective
    always win, then symbol/path token matches, then tests/docs when the goal asks
    for them. Files are read only after ranking, and the total size is bounded.
    """
    root = Path(root).resolve()
    tokens = goal_tokens(goal)
    spelled = mentioned_paths(goal)
    spelled_lower = {item.lower() for item in spelled}
    spelled_tokens: set[str] = set()
    for item in spelled:
        spelled_tokens.update(goal_tokens(item))
    distinctive = [token for token in tokens if token not in spelled_tokens]
    lowered_goal = str(goal or "").lower()
    wants_tests = any(word in lowered_goal for word in ("test", "pytest", "spec", "verification"))
    wants_docs = any(word in lowered_goal for word in ("doc", "readme", "documentazione", "documentation"))
    wants_config = any(word in lowered_goal for word in (
        "dependency", "dependencies", "pyproject", "package.json", "requirements",
        "config", "configuration", "setup", "toml", "yaml"))
    candidates = list((profile.source_files if profile else []) or [])
    if not candidates:
        for path in _iter_project_files(root):
            candidates.append({"path": _safe_relative(path, root),
                               "ext": path.suffix.lower()})
    ranked: list[tuple[float, str, dict]] = []
    for item in candidates:
        relative = str(item.get("path") or "")
        if not relative:
            continue
        lowered = relative.lower()
        if any(part in IGNORED_DIRS for part in lowered.split("/")):
            continue
        score = 0.0
        reasons: list[str] = []
        explicit = lowered in spelled_lower
        suffix_match = any(lowered.endswith(value) for value in spelled_lower)
        if explicit:
            score += 100
            reasons.append("explicitly named in the objective")
        elif suffix_match:
            score += 60
            reasons.append("path suffix matches the objective")
        stem = Path(lowered).stem
        parts = set(re.split(r"[^a-z0-9_]+", lowered))
        token_hits = [token for token in tokens if token in parts or token in stem]
        if token_hits:
            score += min(30, 6 * len(token_hits))
            reasons.append("path/symbol matches: " + ", ".join(token_hits[:4]))
        if wants_tests and (lowered.startswith("tests/") or "/test" in lowered or "test_" in lowered):
            score += 12
            reasons.append("test file requested by the objective")
        if wants_docs and lowered.endswith((".md", ".txt", ".rst")):
            score += 8
            reasons.append("documentation requested by the objective")
        # When the objective names its target files, unrelated files that only share a
        # generic path token (e.g. another "feature_*.py") are noise, not context.
        if spelled and not (explicit or suffix_match):
            relevant_extra = [token for token in distinctive
                              if token in parts or token in stem]
            requested_kind = (
                (wants_tests and (lowered.startswith("tests/") or "test_" in lowered))
                or (wants_docs and lowered.endswith((".md", ".txt", ".rst")))
                or (wants_config and lowered.endswith((".json", ".toml", ".yaml", ".yml", ".ini", ".cfg")))
            )
            if not relevant_extra and not requested_kind:
                continue
        # Reference/data documents are not implementation context unless the objective
        # asks for them: a requirement boilerplate "consult the blueprint" must not
        # pull the whole backlog index into a code prompt.
        suffix = Path(lowered).suffix
        is_source = suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
        if not is_source and not explicit and not suffix_match:
            if suffix in (".json", ".toml", ".yaml", ".yml", ".ini", ".cfg") and not wants_config:
                continue
            if suffix in (".md", ".txt", ".rst") and not wants_docs:
                continue
        if lowered in {name.lower() for name in KEY_DOC_NAMES}:
            score += 4
            reasons.append("authoritative project document")
        ext = str(item.get("ext") or Path(lowered).suffix)
        if ext in (".py", ".ts", ".tsx", ".js", ".jsx"):
            score += 2
        if lowered.endswith((".lock", ".log", ".map", ".min.js")):
            score -= 20
        if score <= 0:
            continue
        ranked.append((score, relative, {"path": relative, "reason": "; ".join(reasons),
                                         "score": round(score, 1)}))
    ranked.sort(key=lambda entry: (-entry[0], entry[1]))
    selected: list[dict] = []
    used = 0
    for score, relative, metadata in ranked[:max_files * 3]:
        if len(selected) >= max_files or used >= budget_chars:
            break
        excerpt = _excerpt_for_tokens(_read_text(root / relative), tokens)
        if not excerpt:
            continue
        remaining = budget_chars - used
        if remaining < 400:
            break
        excerpt = excerpt[:remaining]
        used += len(excerpt)
        selected.append({**metadata, "excerpt": excerpt})
    return selected


def mission_context_text(root: Path | str, goal: str, profile: ProjectProfile | None,
                         *, budget_chars: int = 16_000) -> tuple[str, list[dict]]:
    """Compose the profile + retrieved files block consumed by mission prompts."""
    chunks: list[str] = []
    if profile is not None:
        chunks.append(profile_summary_text(profile))
    reserved = max(2_000, budget_chars // 3)
    files = select_relevant_files(root, goal, profile,
                                  budget_chars=max(2_000, budget_chars - reserved))
    for item in files:
        chunks.append("--- " + item["path"] + " (match: " + item["reason"] + ") ---\n"
                      + item["excerpt"])
    text = "\n\n".join(chunks)
    if len(text) > budget_chars:
        text = text[:budget_chars] + "\n... [project context truncated]"
    return text, files

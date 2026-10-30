"""Roadmap parsing and next-mission selection.

The self-builder reads the consolidated ``docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md``
as its task source; requirement identifiers remain in the historical backlog.
"""
from __future__ import annotations

import re
from pathlib import Path

DEFAULT_ROADMAP = Path("docs") / "NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md"
PROTECTED_PREFIXES = (
    "python/", "crewai/", "crewai-tools/", ".git/", "data/", ".workspace/",
    "logs/", "state/",
)

_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_PATH_SUFFIXES = (
    "py", "md", "txt", "toml", "json", "yaml", "yml", "qss", "js", "ts", "tsx",
    "jsx", "rs", "go", "c", "cpp", "h", "hpp", "cs", "java", "kt", "bat", "ps1",
)
_ROOT_FILE_RE = re.compile(rf"^[\w.-]+\.(?:{'|'.join(_PATH_SUFFIXES)})$")
_BARE_PATH_RE = re.compile(rf"(?<![\w/.-])((?:[\w.-]+[/\\])+[\w.-]+\.(?:{'|'.join(_PATH_SUFFIXES)}))")
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.+)$")


def _section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _looks_like_path(token: str) -> bool:
    token = token.strip()
    if not token or " " in token or "://" in token:
        return False
    if token.startswith(("-", "--")):
        return False
    lowered = token.lower().replace("\\", "/")
    if lowered.startswith(PROTECTED_PREFIXES):
        return False
    if lowered.startswith(("http", "mailto:")):
        return False
    if "/" in token or "\\" in token:
        return True
    return bool(_ROOT_FILE_RE.match(token))


def normalize_path(token: str) -> str:
    return token.strip().replace("\\", "/").lstrip("./")


def extract_paths(text: str) -> list[str]:
    """Extract likely project-relative paths from roadmap prose."""
    candidates: list[str] = []
    for token in _BACKTICK_RE.findall(text):
        if _looks_like_path(token):
            candidates.append(normalize_path(token))
    text_without_urls = re.sub(r"https?://\S+", "", text)
    for token in _BARE_PATH_RE.findall(text_without_urls):
        if _looks_like_path(token):
            candidates.append(normalize_path(token))

    seen: set[str] = set()
    result: list[str] = []
    for path in candidates:
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def parse_roadmap_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    first_heading = next((line for line in text.splitlines() if line.startswith("# ")), "")
    title = first_heading.lstrip("# ").strip()
    for prefix in ("Next Self-Build Mission — ", "Next Self-Build Mission - ", "Next Self-Build Mission: "):
        if title.startswith(prefix):
            title = title[len(prefix):].strip()
            break

    objective = _section(text, "Objective")
    scope = _section(text, "Scope of Work")
    gates_text = _section(text, "Acceptance Gates")
    commands_text = _section(text, "Execution via NL Coding Agent CLI")

    gates: list[dict] = []
    current: dict | None = None
    for line in gates_text.splitlines():
        match = _CHECKBOX_RE.match(line)
        if match:
            if current:
                gates.append(current)
            current = {
                "text": match.group(2).strip(),
                "done": match.group(1).lower() == "x",
            }
        elif current and line.strip():
            current["text"] = f"{current['text']} {line.strip()}"
    if current:
        gates.append(current)
    write_paths = extract_paths(objective + "\n" + scope)
    goal = (
        f"{title}\n\n"
        f"Objective:\n{objective}\n\n"
        f"Scope of work:\n{scope}\n\n"
        f"Acceptance gates:\n{gates_text}\n\n"
        "Implement the change directly in the project files. "
        "Do not only describe a plan."
    ).strip()

    return {
        "source": str(path),
        "title": title or path.stem,
        "objective": objective,
        "scope": scope,
        "goal": goal,
        "write_paths": write_paths,
        "acceptance_gates": gates,
        "commands": commands_text,
        "all_gates_done": bool(gates) and all(g["done"] for g in gates),
    }


def next_mission(project_root: Path | str, roadmap_path: Path | None = None) -> dict:
    """Read the current next-mission document for a project."""
    root = Path(project_root).resolve()
    path = roadmap_path or (root / DEFAULT_ROADMAP)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        raise FileNotFoundError(
            f"No roadmap found at {path}. Create docs/NL_CODE_1_0_STABLE_PIANO_OPERATIVO.md "
            "with an Objective, Scope of Work and Acceptance Gates."
        )
    mission = parse_roadmap_file(path)
    mission["project_root"] = str(root)
    return mission


def format_mission(mission: dict) -> str:
    gates = mission.get("acceptance_gates", [])
    lines = [
        f"Title: {mission['title']}",
        f"Source: {mission.get('source', '?')}",
        f"Write scope: {', '.join(mission.get('write_paths', [])) or '(unrestricted)'}",
        "Acceptance gates:",
    ]
    if gates:
        for gate in gates:
            mark = "x" if gate["done"] else " "
            lines.append(f"  [{mark}] {gate['text']}")
    else:
        lines.append("  (none declared)")
    lines.append("")
    lines.append("Goal:")
    lines.append(mission.get("goal", ""))
    return "\n".join(lines)

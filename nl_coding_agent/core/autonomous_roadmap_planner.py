"""Smallest reliable autonomous roadmap planner (DEPRECATED - stage 3 C3b).

Deprecated: the persistent supervisor selects missions through
nl_coding_agent.core.backlog and docs/product-blueprint/INDEX.json. This module is
kept as a reference only; nothing in the supervisor path imports it.

Reads Blueprint checklist, selects first incomplete feasible task,
reconciles against SQLite mission evidence to avoid duplicates.
"""
from __future__ import annotations
import re
from pathlib import Path
from nl_coding_agent.persistence.missions import list_missions

CHECKLIST = Path("docs/product-blueprint/03_MASTER_CHECKLIST.md")


def _parse_checklist_items(text: str) -> list[dict]:
    items = []
    for m in re.finditer(
        r"- \[ \]\s*\*\*(P\d+-\d+)\*\*\s*(.+?)(?:\n|\Z)",
        text,
    ):
        code = m.group(1)
        desc = m.group(2).strip()
        priority = int(re.search(r"\d+", code).group())
        items.append({"code": code, "priority": priority, "desc": desc})
    return items


def _completed_titles(project_id: int | None = None) -> set[str]:
    return {
        (m.get("title") or "")
        for m in list_missions(project_id)
        if m.get("status") == "completed"
    }


def select_next_task(root: str | Path = ".") -> dict | None:
    root = Path(root).resolve()
    checklist_path = root / CHECKLIST
    if not checklist_path.exists():
        return None
    text = checklist_path.read_text(encoding="utf-8", errors="replace")
    items = _parse_checklist_items(text)
    completed = _completed_titles()
    for it in sorted(items, key=lambda i: (i["priority"], i["code"])):
        desc_short = it["desc"][:60]
        if any(desc_short in c for c in completed):
            continue
        if any(it["code"] in (m.get("goal") or "") or it["code"] in (m.get("title") or "") for m in list_missions() if m.get("status") == "completed"):
            continue
        goal = f"Consolidate product backlog item {it['code']}: {it['desc'][:120]}"
        return {
            "title": f"Backlog Consolidation: {it['code']}",
            "goal": goal,
            "source": str(checklist_path.relative_to(root)),
            "all_gates_done": False,
            "priority": it["priority"],
            "checklist_code": it["code"],
        }
    return None


def write_roadmap_mission(root: str | Path, task: dict) -> Path:
    root = Path(root).resolve()
    path = root / "docs/NEXT_SELF_BUILD_MISSION.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    scope_lines = "docs/PRODUCT_BACKLOG.md\n- nl_coding_agent/core/autonomous_roadmap_planner.py\n- tests/test_roadmap.py"
    content = (
        f"# Next Self-Build Mission: {task['title']}\n\n"
        f"**Goal:** {task['goal']}\n\n"
        f"**Source:** {task['source']} (checklist item {task.get('checklist_code','')})\n\n"
        f"## Scope of Work\n{scope_lines}\n\n"
        f"## Acceptance gates\n"
        f"- [ ] Consolidated backlog file exists and references checklist/spec.\n"
        f"- [ ] No duplicate entries; priorities/dependencies respected.\n"
        f"- [ ] Full test suite passes (69+).\n"
        f"- [ ] No external code changes outside doc/backlog scope.\n"
        f"- [ ] Verified by autonomous Developer -> Tester -> Reviewer.\n"
    )
    path.write_text(content, encoding="utf-8")
    return path

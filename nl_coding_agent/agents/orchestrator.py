"""Autonomous Multi-Agent Orchestrator: Developer -> Tester -> Debugger -> Reviewer.

The orchestrator is intentionally evidence-driven:
- an LLM stage is only successful when the workspace actually changed;
- the tester runs real automated verification;
- the reviewer receives a mission-scoped diff, not the whole dirty working tree;
- every gate and outcome is persisted in SQLite;
- interrupted missions can be resumed in a new process.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from crewai import Agent, Crew, LLM, Process, Task

from nl_coding_agent.app.services import Event, get_event_bus
from nl_coding_agent.core.mission_lock import MissionLockError, mission_lock
from nl_coding_agent.core.roadmap import extract_paths
from nl_coding_agent.core.task_graph import TaskCollisionError, TaskGraph
from nl_coding_agent.core.workspace import (
    diff_snapshots,
    diff_stats,
    out_of_scope_paths,
    snapshot_workspace,
)
from nl_coding_agent.persistence.database import db_path
from nl_coding_agent.persistence.missions import (
    add_task,
    get_handoffs,
    get_latest_attempt,
    get_mission,
    get_task_attempts,
    get_tasks,
    get_verification_runs,
    increment_resume_count,
    mark_mission_started,
    mission_progress,
    record_handoff,
    record_task_attempt,
    record_verification_run,
    reset_interrupted_tasks,
    update_mission_result,
    update_mission_status,
    update_task_status,
)
from nl_coding_agent.tools.crew_tools import get_project_tools
from nl_coding_agent.tools.filesystem import scoped_patch_file, scoped_write_file
from nl_coding_agent.tools.git_tools import get_git_diff, get_git_status
from nl_coding_agent.tools.verification import run_verification

DEFAULT_DEVELOPER_MODEL = os.environ.get(
    "NL_DEVELOPER_MODEL", "ollama/qwen2.5-coder:7b-instruct-q4_K_M"
)
DEFAULT_REVIEWER_MODEL = os.environ.get(
    "NL_REVIEWER_MODEL", "ollama/qwen3.5:9b"
)
DEFAULT_DEBUG_MODEL = os.environ.get("NL_DEBUG_MODEL", DEFAULT_DEVELOPER_MODEL)


class DeveloperNoChangeError(RuntimeError):
    """Raised when the developer stage produced no workspace change."""


class ScopeViolationError(RuntimeError):
    """Raised when a stage modified files outside its declared write scope."""


class VerificationError(RuntimeError):
    """Raised when automated verification cannot be made to pass."""


def _truncate(text: str, limit: int = 20_000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _make_llm(model_name: str, base_url: str = "http://127.0.0.1:11434", temperature: float = 0.1) -> LLM:
    """Create a CrewAI LLM instance for Ollama."""
    return LLM(model=model_name, base_url=base_url, temperature=temperature)


def parse_reviewer_verdict(text: str) -> str:
    """Parse a reviewer verdict conservatively. Ambiguity is a REJECT."""
    for raw_line in (text or "").splitlines():
        line = raw_line.strip().strip("*#`> ")
        if not line:
            continue
        match = re.match(r"(APPROVE|REJECT)(?:D|ED)?\b", line, re.IGNORECASE)
        if match:
            return "APPROVE" if match.group(1).upper() == "APPROVE" else "REJECT"
        match = re.match(r"(?:VERDICT|DECISION)\s*[:\-]\s*(APPROVE|REJECT)(?:D|ED)?\b", line, re.IGNORECASE)
        if match:
            return "APPROVE" if match.group(1).upper() == "APPROVE" else "REJECT"
    return "REJECT"


def _strip_code_fences(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1])
    return content


def _extract_added_lines_from_diff(content: str) -> str:
    """Salvage code from a model that emitted a unified diff inside a write block."""
    if "diff --git" not in content and "@@" not in content:
        return content
    if "@@" not in content:
        return content
    output: list[str] = []
    in_hunk = False
    for line in content.splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith(("diff --git", "index ", "--- ", "+++ ")):
            continue
        if line.startswith("+"):
            output.append(line[1:])
        elif line.startswith(" "):
            output.append(line[1:])
        elif line.startswith("\\"):
            continue
    return "\n".join(output) if output else content


def clean_file_content(content: str, rel_path: str) -> str:
    cleaned = _strip_code_fences(content)
    cleaned = _extract_added_lines_from_diff(cleaned)
    cleaned = cleaned.replace("\r\n", "\n")
    if rel_path.lower().endswith((".py", ".pyi", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".qss")):
        if cleaned and not cleaned.endswith("\n"):
            cleaned += "\n"
    return cleaned


def _apply_text_actions(project_root: Path, text: str) -> list[str]:
    """Execute write/patch actions emitted as text by a local model.

    This is a fallback for models that describe a tool call instead of using the
    native tool API.  Every action is scoped through the filesystem safety layer.
    """
    actions: list[str] = []
    root = Path(project_root).resolve()

    # JSON tool calls: ```json {"name": "write_file", "arguments": {...}} ```
    for block in re.findall(r"```json\r?\n(.*?)```", text, re.DOTALL):
        try:
            data = json.loads(block.strip())
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("action") or item.get("tool")
                args = item.get("arguments") or item.get("args") or item
                if not isinstance(args, dict):
                    continue
                if name == "write_file" and "path" in args and "content" in args:
                    content = clean_file_content(str(args["content"]), str(args["path"]))
                    scoped_write_file(root, str(args["path"]), content)
                    actions.append(f"Wrote {args['path']} via JSON tool call")
                elif name == "patch_file" and {"path", "target", "replacement"} <= set(args):
                    scoped_patch_file(root, str(args["path"]), str(args["target"]), str(args["replacement"]))
                    actions.append(f"Patched {args['path']} via JSON tool call")
        except Exception as exc:
            actions.append(f"JSON action rejected: {exc}")

    # ```write:<path> ... ``` and ```file:<path> ... ```
    write_pattern = re.compile(r"```(?:write|file):([^\r\n`]+)\r?\n(.*?)```", re.DOTALL)
    for match in write_pattern.finditer(text):
        rel_path = match.group(1).strip()
        content = clean_file_content(match.group(2), rel_path)
        try:
            scoped_write_file(root, rel_path, content)
            actions.append(f"Wrote {rel_path} via code block")
        except Exception as exc:
            actions.append(f"Failed to write {rel_path}: {exc}")

    # **File:** `path` followed by a fenced code block
    labelled_pattern = re.compile(
        r"(?:\*\*)?(?:File|Path)(?:\*\*)?\s*:\s*`?([^\s`\r\n]+)`?\s*\r?\n+```[A-Za-z0-9_+.-]*\r?\n(.*?)```",
        re.DOTALL,
    )
    for match in labelled_pattern.finditer(text):
        rel_path = match.group(1).strip()
        content = clean_file_content(match.group(2), rel_path)
        try:
            scoped_write_file(root, rel_path, content)
            actions.append(f"Wrote {rel_path} via labelled code block")
        except Exception as exc:
            actions.append(f"Failed to write {rel_path}: {exc}")

    # ```patch:<path> <<<<<<< TARGET ... ======= ... >>>>>>> ```
    patch_pattern = re.compile(
        r"```patch:([^\r\n`]+)\r?\n<<<<<<< TARGET\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n>>>>>>>\r?\n?```",
        re.DOTALL,
    )
    for match in patch_pattern.finditer(text):
        rel_path = match.group(1).strip()
        try:
            scoped_patch_file(root, rel_path, match.group(2), match.group(3))
            actions.append(f"Patched {rel_path} via patch block")
        except Exception as exc:
            actions.append(f"Failed to patch {rel_path}: {exc}")

    return actions


class MultiAgentOrchestrator:
    """Coordinates Developer, Tester, Debugger, and Reviewer on a real project."""

    def __init__(self, project_root: Path | str, base_url: str = "http://127.0.0.1:11434"):
        self.root = Path(project_root).resolve()
        self.base_url = base_url
        self.bus = get_event_bus()

    # ------------------------------------------------------------------ helpers

    def _emit(self, source: str, level: str, message: str, **payload) -> None:
        self.bus.emit(Event(source=source, level=level, message=message, payload=payload or None))

    def _call_model(self, agent, task) -> str:
        """Single seam for model invocation.

        Tests monkeypatch this method to inject deterministic fake model output
        without loading any LLM; real runs use CrewAI exactly as before.
        """
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )
        return str(crew.kickoff())

    def _snapshot(self) -> dict[str, str]:
        return snapshot_workspace(self.root)

    def _mission_diff(self, baseline: dict[str, str]) -> tuple[str, list[str], str]:
        current = self._snapshot()
        diff, changed = diff_snapshots(baseline, current)
        return diff, changed, diff_stats(diff)

    def _latest_output(self, task_id: int) -> str:
        attempt = get_latest_attempt(task_id)
        return (attempt or {}).get("output") or ""

    def _baseline_path(self, mission_id: int) -> Path:
        return db_path().parent / "mission_baselines" / f"{mission_id}.json"

    def _save_baseline(self, mission_id: int, snapshot: dict[str, str]) -> None:
        path = self._baseline_path(mission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot), encoding="utf-8")

    def _load_baseline(self, mission_id: int) -> dict[str, str] | None:
        path = self._baseline_path(mission_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _collect_changed_paths(self, mission_id: int, current: list[str]) -> list[str]:
        """Union of current changes and changes recorded before a crash/resume."""
        mission = get_mission(mission_id) or {}
        paths: set[str] = set()
        try:
            paths.update(json.loads(mission.get("changed_paths") or "[]"))
        except Exception:
            pass
        for handoff in get_handoffs(mission_id):
            payload = handoff.get("payload") or {}
            for path in payload.get("changed_paths") or []:
                paths.add(path)
            for path in self._paths_from_diff(payload.get("diff_sample") or ""):
                paths.add(path)
        paths.update(current)
        return sorted(paths)

    @staticmethod
    def _paths_from_diff(diff_text: str) -> list[str]:
        paths: set[str] = set()
        for line in (diff_text or "").splitlines():
            if line.startswith("+++ b/"):
                paths.add(line[len("+++ b/"):].strip())
            elif line.startswith("--- a/"):
                paths.add(line[len("--- a/"):].strip())
        return sorted(paths)

    def _plan_tasks(self, mission_id: int, goal: str) -> list[dict]:
        write_paths = extract_paths(goal)
        t1 = add_task(
            mission_id,
            "Code Implementation",
            goal,
            "developer",
            write_paths=write_paths,
        )
        t2 = add_task(
            mission_id,
            "Test & Verification",
            "Run automated tests against the modified source and repair failures",
            "tester",
            depends_on=[t1],
        )
        t3 = add_task(
            mission_id,
            "Code Review",
            "Review the mission-scoped diff and record APPROVE/REJECT",
            "reviewer",
            depends_on=[t2],
        )
        return get_tasks(mission_id)

    def _validate_plan(self, tasks: list[dict]) -> None:
        graph = TaskGraph()
        for task in tasks:
            graph.add_task(
                task["id"],
                task["title"],
                task.get("description") or "",
                task.get("agent_role") or "",
                depends_on=task.get("depends_on") or [],
                write_paths=task.get("write_paths") or [],
                status=task.get("status") or "pending",
            )
        graph.validate()

        def depends_on(task_id: int, target_id: int, seen: set[int] | None = None) -> bool:
            seen = seen or set()
            if task_id in seen:
                return False
            seen.add(task_id)
            node = graph.nodes.get(task_id)
            if not node:
                return False
            if target_id in node.depends_on:
                return True
            return any(depends_on(dep, target_id, seen) for dep in node.depends_on)

        writers = [t for t in tasks if t.get("agent_role") == "developer" and t.get("write_paths")]
        for i, left in enumerate(writers):
            for right in writers[i + 1:]:
                if graph.check_collision(graph.nodes[left["id"]], graph.nodes[right["id"]]):
                    if depends_on(left["id"], right["id"]) or depends_on(right["id"], left["id"]):
                        continue
                    raise TaskCollisionError(
                        f"Write-scope collision between task #{left['id']} and task #{right['id']}: "
                        f"{left.get('write_paths')} vs {right.get('write_paths')}"
                    )

    def _check_scope(self, changed_paths: list[str], write_paths: list[str]) -> None:
        if not write_paths:
            return
        violations = out_of_scope_paths(changed_paths, write_paths)
        if violations:
            raise ScopeViolationError(
                "Developer modified files outside the declared write scope: "
                + ", ".join(violations)
                + f" (allowed: {', '.join(write_paths)})"
            )

    def _finalize(
        self,
        mission_id: int,
        status: str,
        baseline: dict[str, str],
        review_text: str = "",
        verdict: str = "",
        summary: str = "",
    ) -> dict:
        diff, changed, stat = self._mission_diff(baseline)
        changed = self._collect_changed_paths(mission_id, changed)
        if not diff.strip() and changed:
            recovered_diff = get_git_diff(self.root)
            if recovered_diff.strip():
                diff = recovered_diff
                stat = diff_stats(diff)
        update_mission_result(
            mission_id,
            status,
            result_summary=summary or None,
            review_verdict=verdict or None,
            diff_stat=stat,
            changed_paths=changed,
        )
        record_handoff(
            mission_id,
            "orchestrator",
            "user",
            summary or f"Mission finished with status {status}",
            {
                "status": status,
                "verdict": verdict,
                "changed_paths": changed,
                "diff_stat": stat,
            },
        )
        self._emit(
            "orchestrator",
            "info" if status == "completed" else "warning",
            f"Mission #{mission_id} finished: {status}",
            mission_id=mission_id,
            changed_paths=changed,
        )
        return {
            "status": status,
            "mission_id": mission_id,
            "git_diff": get_git_diff(self.root),
            "mission_diff": diff,
            "diff_stat": stat,
            "changed_paths": changed,
            "review": review_text,
            "verdict": verdict,
            "handoffs": get_handoffs(mission_id),
            "verification_runs": get_verification_runs(mission_id),
            "tasks": get_tasks(mission_id),
            "attempts": get_task_attempts(mission_id),
            "progress": mission_progress(mission_id),
        }

    # ---------------------------------------------------------------- public API

    def run_mission(
        self,
        mission_id: int,
        goal: str | None = None,
        developer_model: str | None = None,
        reviewer_model: str | None = None,
        debug_model: str | None = None,
        stop_after: str | None = None,
    ) -> dict:
        """Execute or resume a complete mission through all gates."""
        mission = get_mission(mission_id)
        if not mission:
            raise ValueError(f"Mission #{mission_id} not found")
        goal = (goal or mission.get("goal") or "").strip()
        if not goal:
            raise ValueError(f"Mission #{mission_id} has no goal")

        developer_model = developer_model or DEFAULT_DEVELOPER_MODEL
        reviewer_model = reviewer_model or DEFAULT_REVIEWER_MODEL
        debug_model = debug_model or DEFAULT_DEBUG_MODEL

        if mission["status"] == "completed":
            diff, changed, stat = self._mission_diff(self._snapshot())
            return {
                "status": "completed",
                "mission_id": mission_id,
                "git_diff": get_git_diff(self.root),
                "mission_diff": "",
                "diff_stat": mission.get("diff_stat") or "",
                "changed_paths": json.loads(mission.get("changed_paths") or "[]"),
                "review": mission.get("result_summary") or "",
                "verdict": mission.get("review_verdict") or "",
                "handoffs": get_handoffs(mission_id),
                "verification_runs": get_verification_runs(mission_id),
                "tasks": get_tasks(mission_id),
                "attempts": get_task_attempts(mission_id),
                "progress": mission_progress(mission_id),
            }

        try:
            with mission_lock(mission_id):
                return self._run_locked(
                    mission_id,
                    goal,
                    developer_model,
                    reviewer_model,
                    debug_model,
                    stop_after,
                )
        except MissionLockError as exc:
            self._emit("orchestrator", "error", str(exc), mission_id=mission_id)
            update_mission_status(mission_id, "blocked")
            return {
                "status": "blocked",
                "mission_id": mission_id,
                "error": str(exc),
                "handoffs": get_handoffs(mission_id),
                "verification_runs": get_verification_runs(mission_id),
            }

    def _run_locked(
        self,
        mission_id: int,
        goal: str,
        developer_model: str,
        reviewer_model: str,
        debug_model: str,
        stop_after: str | None,
    ) -> dict:
        mission = get_mission(mission_id) or {}
        existing_tasks = get_tasks(mission_id)
        if existing_tasks:
            reset_ids = reset_interrupted_tasks(mission_id)
            if reset_ids or mission.get("status") in ("running", "interrupted", "failed", "blocked"):
                increment_resume_count(mission_id)
                message = (
                    f"Resuming mission #{mission_id}; reset interrupted tasks {reset_ids}"
                    if reset_ids
                    else f"Resuming mission #{mission_id} from persisted state"
                )
                record_handoff(mission_id, "system", "orchestrator", message, {"reset_tasks": reset_ids})
                self._emit("orchestrator", "info", message, mission_id=mission_id)

        mark_mission_started(mission_id)
        self._emit(
            "orchestrator",
            "info",
            f"Starting mission #{mission_id}: {goal[:160]}",
            mission_id=mission_id,
            project=str(self.root),
        )

        tasks = get_tasks(mission_id) if existing_tasks else self._plan_tasks(mission_id, goal)
        self._validate_plan(tasks)
        if existing_tasks:
            baseline = self._load_baseline(mission_id)
            if baseline is None:
                baseline = self._snapshot()
                self._emit(
                    "orchestrator", "warning",
                    "No persisted mission baseline found; using the current working tree as baseline.",
                    mission_id=mission_id,
                )
        else:
            baseline = self._snapshot()
            self._save_baseline(mission_id, baseline)

        task_map = {t["agent_role"]: t for t in tasks}
        dev_task = task_map.get("developer")
        test_task = task_map.get("tester")
        rev_task = task_map.get("reviewer")

        try:
            # 1. Developer
            if dev_task and dev_task["status"] != "completed":
                self._run_developer_stage(mission_id, dev_task, goal, developer_model, baseline)
            elif dev_task:
                output = self._latest_output(dev_task["id"])
                self._emit("developer", "info", "Developer stage already completed; reusing persisted result.")
                record_handoff(
                    mission_id, "developer", "tester",
                    "Developer stage recovered from persistence.",
                    {"output_sample": _truncate(output, 1000)},
                )

            if stop_after == "developer":
                return self._finalize(
                    mission_id, "interrupted", baseline,
                    summary="Mission interrupted after developer stage (requested). Resume to continue.",
                )

            # 2. Tester / Debugger
            if test_task and test_task["status"] != "completed":
                self._run_tester_stage(mission_id, test_task, debug_model, baseline)
            elif test_task:
                self._emit("tester", "info", "Tester stage already completed; reusing persisted verification.")
                record_handoff(
                    mission_id, "tester", "reviewer",
                    "Verification recovered from persistence.",
                    {"verification_runs": len(get_verification_runs(mission_id))},
                )

            if stop_after == "tester":
                return self._finalize(
                    mission_id, "interrupted", baseline,
                    summary="Mission interrupted after tester stage (requested). Resume to continue.",
                )

            # 3. Reviewer
            review_text = ""
            verdict = "REJECT"
            if rev_task and rev_task["status"] != "completed":
                review_text, verdict = self._run_reviewer_stage(mission_id, rev_task, reviewer_model, baseline)
            elif rev_task:
                review_text = self._latest_output(rev_task["id"])
                verdict = parse_reviewer_verdict(review_text)
                self._emit(
                    "reviewer", "info",
                    f"Reviewer stage recovered from persistence; verdict {verdict}.",
                )

            if verdict == "APPROVE":
                return self._finalize(
                    mission_id, "completed", baseline,
                    review_text=review_text, verdict=verdict,
                    summary="Reviewer APPROVED the mission diff.",
                )
            return self._finalize(
                mission_id, "blocked", baseline,
                review_text=review_text, verdict="REJECT",
                summary="Reviewer REJECTED the mission diff. Inspect the recorded review and diff.",
            )
        except Exception as exc:
            message = f"Mission #{mission_id} failed: {exc}"
            self._emit("orchestrator", "error", message, mission_id=mission_id)
            record_handoff(mission_id, "orchestrator", "user", message, {"error": str(exc)})
            update_mission_status(mission_id, "failed")
            return {
                "status": "failed",
                "mission_id": mission_id,
                "error": str(exc),
                "git_diff": get_git_diff(self.root),
                "handoffs": get_handoffs(mission_id),
                "verification_runs": get_verification_runs(mission_id),
                "tasks": get_tasks(mission_id),
                "attempts": get_task_attempts(mission_id),
                "progress": mission_progress(mission_id),
            }

    # ------------------------------------------------------------------ stages

    def _run_developer_stage(
        self,
        mission_id: int,
        task_rec: dict,
        goal: str,
        model_name: str,
        baseline: dict[str, str],
    ) -> str:
        task_id = task_rec["id"]
        write_paths = task_rec.get("write_paths") or extract_paths(goal)
        update_task_status(task_id, "running")
        self._emit(
            "developer", "info",
            f"Developer agent starting work on task #{task_id} with {model_name}",
            model=model_name,
            write_paths=write_paths,
        )

        tools = get_project_tools(self.root)
        dev_agent = Agent(
            role="Implementation Developer",
            goal=f"Implement the requested code change directly in the project files: {goal}",
            backstory=(
                "You are an expert autonomous software engineer. You inspect existing code using read_file "
                "or list_dir, and you write the necessary files or patches using write_file or patch_file. "
                "You can also use ```write:<file_path>\\n<content>``` blocks. "
                "You must produce real file changes, not only a plan."
            ),
            llm=_make_llm(model_name, self.base_url),
            tools=tools,
            verbose=True,
            allow_delegation=False,
        )

        scope_text = (
            "Declared write scope (do not modify other files):\n- " + "\n- ".join(write_paths)
            if write_paths
            else "No explicit write scope was declared. Stay focused on the goal."
        )
        prompt = f"""
PROJECT ROOT: {self.root}
MISSION GOAL: {goal}

{scope_text}

INSTRUCTIONS:
1. Read the relevant existing files first.
2. Implement the requested change directly in the project files.
3. Prefer patch_file for small edits. For complete files use write_file or this exact block format:
```write:<relative_path>
<valid source code>
```
4. Do NOT output 'diff --git' or unified-diff headers inside a source file.
5. Do NOT claim success without actually writing the files.
6. Finish with a short summary of the files you changed.
"""
        crew_task = Task(
            description=prompt,
            expected_output="Summary of files actually modified and the changes made.",
            agent=dev_agent,
        )
        before = self._snapshot()
        try:
            output = self._call_model(dev_agent, crew_task)
            actions = _apply_text_actions(self.root, output)
            after = self._snapshot()
            diff, changed = diff_snapshots(before, after)
            self._check_scope(changed, write_paths)

            if not changed:
                raise DeveloperNoChangeError(
                    "Developer produced no workspace change. "
                    f"Actions parsed: {actions or 'none'}. The model output did not modify files."
                )

            record_task_attempt(
                task_id,
                "completed",
                output=_truncate(output),
            )
            update_task_status(task_id, "completed")
            summary = (
                f"Developer modified {len(changed)} file(s): {', '.join(changed)}. "
                f"Actions: {len(actions)}."
            )
            record_handoff(
                mission_id=mission_id,
                from_role="developer",
                to_role="tester",
                summary=summary,
                payload={
                    "model": model_name,
                    "changed_paths": changed,
                    "actions": actions,
                    "diff_sample": _truncate(diff, 4000),
                    "output_sample": _truncate(output, 1500),
                },
            )
            self._emit("developer", "info", summary, mission_id=mission_id, changed_paths=changed)
            return output
        except Exception as exc:
            record_task_attempt(task_id, "failed", error=str(exc))
            update_task_status(task_id, "failed", error=str(exc))
            self._emit("developer", "error", f"Developer failed: {exc}", mission_id=mission_id)
            raise

    def _run_tester_stage(
        self,
        mission_id: int,
        task_rec: dict,
        debug_model: str,
        baseline: dict[str, str],
        max_retries: int = 2,
    ) -> dict:
        task_id = task_rec["id"]
        update_task_status(task_id, "running")
        self._emit(
            "tester", "info",
            f"Tester running automated verification on project {self.root.name}",
            mission_id=mission_id,
        )

        last_res = None
        for attempt in range(max_retries + 1):
            res = run_verification(self.root, timeout=300)
            last_res = res
            record_verification_run(
                mission_id=mission_id,
                task_id=task_id,
                command=res["command"],
                exit_code=res["exit_code"],
                stdout=_truncate(res["stdout"], 40_000),
                stderr=_truncate(res["stderr"], 40_000),
                passed=res["passed"],
            )

            if res["passed"]:
                summary = f"Verification PASSED with '{res['command']}' in {res['duration_s']}s"
                record_handoff(
                    mission_id=mission_id,
                    from_role="tester",
                    to_role="reviewer",
                    summary=summary,
                    payload={"exit_code": 0, "command": res["command"]},
                )
                record_task_attempt(task_id, "completed", output=summary)
                update_task_status(task_id, "completed")
                self._emit("tester", "info", summary, mission_id=mission_id)
                return res

            if attempt >= max_retries:
                break

            error_msg = f"Test failure (exit code {res['exit_code']}):\n{res['stdout']}\n{res['stderr']}"
            self._emit(
                "tester", "warning",
                f"Verification failed on attempt {attempt + 1}. Calling debugger.",
                mission_id=mission_id,
            )
            record_handoff(
                mission_id=mission_id,
                from_role="tester",
                to_role="debugger",
                summary=f"Tests failed (attempt {attempt + 1})",
                payload={"error": _truncate(error_msg, 4000)},
            )
            self._run_debugger(mission_id, debug_model, error_msg, task_rec.get("write_paths") or [], baseline)

        update_task_status(task_id, "failed", error="Tests failed after retries")
        record_task_attempt(task_id, "failed", error=f"Tests failed after {max_retries} retries")
        raise VerificationError(
            f"Verification failed after {max_retries} retries. Last output:\n"
            f"{(last_res or {}).get('stderr', '')[-3000:]}"
        )

    def _run_debugger(
        self,
        mission_id: int,
        model_name: str,
        error_msg: str,
        write_paths: list[str],
        baseline: dict[str, str],
    ) -> None:
        """Debugger agent repairs code based on test failures."""
        tools = get_project_tools(self.root)
        debugger = Agent(
            role="Software Debugger",
            goal="Analyze the test failure error and fix the code to make tests pass.",
            backstory=(
                "You are an expert troubleshooter. You read error logs, locate broken code, "
                "and apply precise fixes using write_file or patch_file."
            ),
            llm=_make_llm(model_name, self.base_url),
            tools=tools,
            verbose=True,
            allow_delegation=False,
        )

        scope_text = (
            "Stay inside the declared write scope:\n- " + "\n- ".join(write_paths)
            if write_paths
            else "Stay focused on the failing code."
        )
        prompt = f"""
PROJECT ROOT: {self.root}
TEST FAILURE LOGS:
{_truncate(error_msg, 12_000)}

{scope_text}

INSTRUCTIONS:
1. Examine the failing tests and the current code.
2. Fix the error directly in the source files using patch_file or:
```write:<relative_path>
<valid source code>
```
3. Do NOT include 'diff --git' or unified-diff headers inside a source file.
4. Keep changes minimal and focused on resolving the error.
"""
        task = Task(description=prompt, expected_output="Summary of the fix actually applied.", agent=debugger)
        before = self._snapshot()
        output = self._call_model(debugger, task)
        actions = _apply_text_actions(self.root, output)
        after = self._snapshot()
        diff, changed = diff_snapshots(before, after)
        self._check_scope(changed, write_paths)
        summary = (
            f"Debugger modified {len(changed)} file(s): {', '.join(changed)}."
            if changed
            else "Debugger produced no file change."
        )
        record_handoff(
            mission_id,
            "debugger",
            "tester",
            summary,
            {
                "model": model_name,
                "changed_paths": changed,
                "actions": actions,
                "diff_sample": _truncate(diff, 4000),
                "output_sample": _truncate(output, 1500),
            },
        )
        self._emit("debugger", "info", summary, mission_id=mission_id, changed_paths=changed)

    def _run_reviewer_stage(
        self,
        mission_id: int,
        task_rec: dict,
        model_name: str,
        baseline: dict[str, str],
    ) -> tuple[str, str]:
        task_id = task_rec["id"]
        update_task_status(task_id, "running")
        diff, changed, stat = self._mission_diff(baseline)
        changed = self._collect_changed_paths(mission_id, changed)
        recovered = False
        if not diff.strip() and changed:
            recovered_diff = get_git_diff(self.root)
            if recovered_diff.strip():
                diff = recovered_diff
                stat = diff_stats(diff)
                recovered = True
        self._emit(
            "reviewer", "info",
            f"Reviewer inspecting mission diff ({stat}) on task #{task_id}",
            mission_id=mission_id,
        )

        reviewer = Agent(
            role="Code Reviewer & Quality Gatekeeper",
            goal="Verify code quality, adherence to scope, and absence of regressions in the mission diff.",
            backstory=(
                "You are a strict, diligent senior engineer. You review only the mission diff. "
                "You give an APPROVE or REJECT verdict on the first line."
            ),
            llm=_make_llm(model_name, self.base_url),
            verbose=True,
            allow_delegation=False,
        )

        recovery_note = (
            "\nNOTE: this mission was resumed and its original baseline was not persisted. "
            "The diff below is the current working-tree diff recovered from handoffs; "
            "review it as the mission's change set.\n"
            if recovered
            else ""
        )
        verification_text = "\n".join(
            f"- {run.get('command')}: exit {run.get('exit_code')} "
            f"({'PASS' if run.get('passed') else 'FAIL'})"
            for run in get_verification_runs(mission_id)
        ) or "- No verification run recorded."
        prompt = f"""
PROJECT ROOT: {self.root}
MISSION CHANGED FILES: {', '.join(changed) or '(none)'}
{recovery_note}
GIT STATUS:
{get_git_status(self.root)}

VERIFICATION RUNS:
{verification_text}

MISSION-SCOPED DIFF TO REVIEW:
{_truncate(diff, 60_000)}

INSTRUCTIONS:
1. Review only the mission-scoped diff above; unrelated pre-existing working-tree changes are not part of this mission.
2. Check correctness, safety, scope adherence, and missing tests.
3. Base every claim on the diff, changed-file list, and verification runs above. Do not invent imports, files, or failures that are not present in that evidence.
4. Start your response with exactly 'APPROVE' or 'REJECT' on the first line.
5. Follow the verdict with concise review notes and blocking issues.
"""
        task = Task(
            description=prompt,
            expected_output="APPROVE or REJECT verdict on the first line, followed by review notes.",
            agent=reviewer,
        )
        try:
            review_text = self._call_model(reviewer, task)
            verdict = parse_reviewer_verdict(review_text)
            record_task_attempt(task_id, "completed", output=_truncate(review_text))
            update_task_status(task_id, "completed")
            summary = f"Review completed with verdict: {verdict}"
            record_handoff(
                mission_id=mission_id,
                from_role="reviewer",
                to_role="orchestrator",
                summary=summary,
                payload={
                    "model": model_name,
                    "verdict": verdict,
                    "review_notes": _truncate(review_text, 2000),
                    "changed_paths": changed,
                },
            )
            self._emit("reviewer", "info", summary, mission_id=mission_id, verdict=verdict)
            return review_text, verdict
        except Exception as exc:
            record_task_attempt(task_id, "failed", error=str(exc))
            update_task_status(task_id, "failed", error=str(exc))
            self._emit("reviewer", "error", f"Review failed: {exc}", mission_id=mission_id)
            raise

"""Autonomous Multi-Agent Orchestrator: Developer -> Tester -> Debugger -> Reviewer."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable

from crewai import Agent, Crew, LLM, Process, Task

from nl_coding_agent.app.services import Event, get_event_bus
from nl_coding_agent.persistence.database import init_db, log_event
from nl_coding_agent.persistence.missions import (
    create_mission,
    get_mission,
    update_mission_status,
    add_task,
    get_tasks,
    update_task_status,
    record_task_attempt,
    record_handoff,
    get_handoffs,
    record_verification_run,
    get_verification_runs,
)
from nl_coding_agent.tools.crew_tools import get_project_tools
from nl_coding_agent.tools.filesystem import scoped_read_file, scoped_write_file, scoped_patch_file
from nl_coding_agent.tools.git_tools import get_git_diff, get_git_status
from nl_coding_agent.tools.verification import run_verification


def _make_llm(model_name: str, base_url: str = "http://127.0.0.1:11434", temperature: float = 0.1) -> LLM:
    """Create a CrewAI LLM instance for Ollama."""
    return LLM(model=model_name, base_url=base_url, temperature=temperature)


def _apply_text_actions(project_root: Path, text: str) -> list[str]:
    """
    Fallback parser for local models: if model emits structured blocks like:
    ```write:path/to/file.py
    file contents
    ```
    or
    ```patch:path/to/file.py
    <<<<<<< TARGET
    old code
    =======
    new code
    >>>>>>>
    ```
    Executes them safely to ensure code modifications always apply on disk.
    """
    actions_taken = []
    root = Path(project_root).resolve()

    # Pattern for write: ```write:<rel_path>\n<content>```
    write_pattern = re.compile(r"```write:([^\r\n]+)\r?\n(.*?)```", re.DOTALL)
    for match in write_pattern.finditer(text):
        rel_path = match.group(1).strip()
        content = match.group(2)
        try:
            scoped_write_file(root, rel_path, content)
            actions_taken.append(f"Wrote file {rel_path} via block")
        except Exception as e:
            actions_taken.append(f"Failed to write {rel_path}: {e}")

    # Pattern for patch: ```patch:<rel_path>\n<<<<<<< TARGET\n<target>\n=======\n<replacement>\n>>>>>>>```
    patch_pattern = re.compile(
        r"```patch:([^\r\n]+)\r?\n<<<<<<< TARGET\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n>>>>>>>\r?\n?```",
        re.DOTALL,
    )
    for match in patch_pattern.finditer(text):
        rel_path = match.group(1).strip()
        target = match.group(2)
        replacement = match.group(3)
        try:
            scoped_patch_file(root, rel_path, target, replacement)
            actions_taken.append(f"Patched file {rel_path} via block")
        except Exception as e:
            actions_taken.append(f"Failed to patch {rel_path}: {e}")

    return actions_taken


class MultiAgentOrchestrator:
    """Coordinates Developer, Tester, Debugger, and Reviewer on a real project."""

    def __init__(self, project_root: Path | str, base_url: str = "http://127.0.0.1:11434"):
        self.root = Path(project_root).resolve()
        self.base_url = base_url
        self.bus = get_event_bus()
        self.db = init_db()

    def run_mission(
        self,
        mission_id: int,
        goal: str,
        developer_model: str = "ollama/qwen2.5-coder:7b-instruct-q4_K_M",
        reviewer_model: str = "ollama/qwen2.5-coder:7b-instruct-q4_K_M",
    ) -> dict:
        """Execute or resume a complete mission through all gates."""
        update_mission_status(mission_id, "running")
        self.bus.emit(Event(
            source="orchestrator", level="info",
            message=f"Starting mission #{mission_id}: {goal}",
            payload={"mission_id": mission_id, "project": str(self.root)},
        ))

        # Retrieve or initialize task nodes
        existing_tasks = get_tasks(mission_id)
        if not existing_tasks:
            t1 = add_task(mission_id, "Code Implementation", goal, "developer")
            t2 = add_task(mission_id, "Test & Verification", "Verify automated tests pass", "tester", depends_on=[t1])
            t3 = add_task(mission_id, "Code Review", "Review diff and integration", "reviewer", depends_on=[t2])
            tasks = get_tasks(mission_id)
        else:
            tasks = existing_tasks

        task_map = {t["agent_role"]: t for t in tasks}

        # ── 1. Developer Stage ──────────────────────────────────────────────
        dev_task = task_map.get("developer")
        if dev_task and dev_task["status"] != "completed":
            self._run_developer_stage(mission_id, dev_task, goal, developer_model)

        # ── 2. Tester / Verifier & Debugger Stage ───────────────────────────
        test_task = task_map.get("tester")
        if test_task and test_task["status"] != "completed":
            self._run_tester_stage(mission_id, test_task, developer_model)

        # ── 3. Reviewer Stage ───────────────────────────────────────────────
        rev_task = task_map.get("reviewer")
        review_result = "PENDING"
        if rev_task and rev_task["status"] != "completed":
            review_result = self._run_reviewer_stage(mission_id, rev_task, reviewer_model)

        # Finalize Mission
        diff = get_git_diff(self.root)
        update_mission_status(mission_id, "completed")
        self.bus.emit(Event(
            source="orchestrator", level="info",
            message=f"Mission #{mission_id} COMPLETED successfully.",
            payload={"mission_id": mission_id, "review": review_result},
        ))

        return {
            "status": "completed",
            "mission_id": mission_id,
            "git_diff": diff,
            "review": review_result,
            "handoffs": get_handoffs(mission_id),
            "verification_runs": get_verification_runs(mission_id),
        }

    def _run_developer_stage(self, mission_id: int, task_rec: dict, goal: str, model_name: str) -> str:
        task_id = task_rec["id"]
        update_task_status(task_id, "running")
        self.bus.emit(Event(
            source="developer", level="info",
            message=f"Developer agent starting work on task #{task_id}",
        ))

        tools = get_project_tools(self.root)
        dev_llm = _make_llm(model_name, self.base_url)

        dev_agent = Agent(
            role="Implementation Developer",
            goal=f"Implement the requested code change directly in the project files: {goal}",
            backstory=(
                "You are an expert autonomous software engineer. You inspect existing code using read_file "
                "or list_dir, and you write the necessary files or patches using write_file or patch_file. "
                "You can also use ```write:<file_path>\\n<content>``` blocks."
            ),
            llm=dev_llm,
            tools=tools,
            verbose=True,
            allow_delegation=False,
        )

        prompt = f"""
PROJECT ROOT: {self.root}
MISSION GOAL: {goal}

INSTRUCTIONS:
1. Check the existing project structure and relevant files.
2. Implement the minimal, clean, high-quality solution to achieve the goal.
3. Modify or create files using the available tools (write_file, patch_file) or output formatted ```write:<relative_path> code blocks.
4. When finished, summarize the exact changes made.
"""
        crew_task = Task(description=prompt, expected_output="Summary of files modified and changes made.", agent=dev_agent)
        crew = Crew(agents=[dev_agent], tasks=[crew_task], process=Process.sequential, verbose=True)

        try:
            output = str(crew.kickoff())
            # Parse any block actions as fallback
            actions = _apply_text_actions(self.root, output)
            record_task_attempt(task_id, "completed", output=output)
            update_task_status(task_id, "completed")

            diff = get_git_diff(self.root)
            summary = f"Developer finished implementation. Actions: {len(actions)}. Uncommitted diff length: {len(diff)} chars."
            record_handoff(
                mission_id=mission_id,
                from_role="developer",
                to_role="tester",
                summary=summary,
                payload={"diff_sample": diff[:2000], "output_sample": output[:1000]},
            )
            self.bus.emit(Event(source="developer", level="info", message=summary))
            return output
        except Exception as e:
            record_task_attempt(task_id, "failed", error=str(e))
            update_task_status(task_id, "failed")
            self.bus.emit(Event(source="developer", level="error", message=f"Developer failed: {e}"))
            raise

    def _run_tester_stage(self, mission_id: int, task_rec: dict, debug_model: str, max_retries: int = 2) -> dict:
        task_id = task_rec["id"]
        update_task_status(task_id, "running")
        self.bus.emit(Event(
            source="tester", level="info",
            message=f"Tester running automated verification on project {self.root.name}",
        ))

        retries = 0
        last_res = None
        while retries <= max_retries:
            res = run_verification(self.root)
            last_res = res
            record_verification_run(
                mission_id=mission_id,
                task_id=task_id,
                command=res["command"],
                exit_code=res["exit_code"],
                stdout=res["stdout"],
                stderr=res["stderr"],
                passed=res["passed"],
            )

            if res["passed"]:
                summary = f"Verification PASSED with command '{res['command']}' in {res['duration_s']}s"
                record_handoff(
                    mission_id=mission_id,
                    from_role="tester",
                    to_role="reviewer",
                    summary=summary,
                    payload={"exit_code": 0},
                )
                record_task_attempt(task_id, "completed", output=summary)
                update_task_status(task_id, "completed")
                self.bus.emit(Event(source="tester", level="info", message=summary))
                return res

            # Tests failed -> Debugger cycle
            retries += 1
            error_msg = f"Test failure (exit code {res['exit_code']}):\n{res['stdout']}\n{res['stderr']}"
            self.bus.emit(Event(
                source="tester", level="warning",
                message=f"Verification failed on attempt {retries}. Calling debugger...",
            ))
            record_handoff(
                mission_id=mission_id,
                from_role="tester",
                to_role="debugger",
                summary=f"Tests failed (attempt {retries})",
                payload={"error": error_msg[:2000]},
            )

            if retries <= max_retries:
                self._run_debugger(debug_model, error_msg)

        # Exceeded retries
        update_task_status(task_id, "failed")
        record_task_attempt(task_id, "failed", error=f"Tests failed after {max_retries} attempts")
        raise RuntimeError(f"Verification failed after {max_retries} retries: {last_res['stderr']}")

    def _run_debugger(self, model_name: str, error_msg: str) -> None:
        """Debugger agent repairs code based on test failures."""
        tools = get_project_tools(self.root)
        dbg_llm = _make_llm(model_name, self.base_url)

        debugger = Agent(
            role="Software Debugger",
            goal="Analyze the test failure error and fix the code to make tests pass.",
            backstory="You are an expert troubleshooter. You read error logs, locate broken code, and apply precise fixes.",
            llm=dbg_llm,
            tools=tools,
            verbose=True,
            allow_delegation=False,
        )

        prompt = f"""
PROJECT ROOT: {self.root}
TEST FAILURE LOGS:
{error_msg}

INSTRUCTIONS:
1. Examine the failing tests and code.
2. Fix the error by editing the code with write_file, patch_file, or ```write: blocks.
3. Keep changes minimal and focused on resolving the error.
"""
        task = Task(description=prompt, expected_output="Summary of fix applied.", agent=debugger)
        crew = Crew(agents=[debugger], tasks=[task], process=Process.sequential, verbose=True)
        out = str(crew.kickoff())
        _apply_text_actions(self.root, out)

    def _run_reviewer_stage(self, mission_id: int, task_rec: dict, model_name: str) -> str:
        task_id = task_rec["id"]
        update_task_status(task_id, "running")
        self.bus.emit(Event(
            source="reviewer", level="info",
            message=f"Reviewer inspecting diff on task #{task_id}",
        ))

        diff = get_git_diff(self.root)
        rev_llm = _make_llm(model_name, self.base_url)

        reviewer = Agent(
            role="Code Reviewer & Quality Gatekeeper",
            goal="Verify code quality, adherence to scope, and absence of regressions in git diff.",
            backstory="You are a strict, diligent senior engineer. You review git diffs and give an APPROVE or REJECT verdict.",
            llm=rev_llm,
            verbose=True,
            allow_delegation=False,
        )

        prompt = f"""
PROJECT ROOT: {self.root}
GIT DIFF TO REVIEW:
{diff}

INSTRUCTIONS:
1. Check if the modifications are correct and safe.
2. Verify no extraneous files or secrets are included.
3. Start your response with 'APPROVE' or 'REJECT' on the first line, followed by a concise review summary.
"""
        task = Task(description=prompt, expected_output="APPROVE or REJECT verdict with review notes.", agent=reviewer)
        crew = Crew(agents=[reviewer], tasks=[task], process=Process.sequential, verbose=True)

        try:
            review_text = str(crew.kickoff())
            record_task_attempt(task_id, "completed", output=review_text)
            update_task_status(task_id, "completed")

            verdict = "APPROVE" if "APPROVE" in review_text.upper() else "REJECT"
            summary = f"Review completed with verdict: {verdict}"
            record_handoff(
                mission_id=mission_id,
                from_role="reviewer",
                to_role="orchestrator",
                summary=summary,
                payload={"verdict": verdict, "review_notes": review_text[:1000]},
            )
            self.bus.emit(Event(source="reviewer", level="info", message=summary))
            return review_text
        except Exception as e:
            record_task_attempt(task_id, "failed", error=str(e))
            update_task_status(task_id, "failed")
            self.bus.emit(Event(source="reviewer", level="error", message=f"Review failed: {e}"))
            raise

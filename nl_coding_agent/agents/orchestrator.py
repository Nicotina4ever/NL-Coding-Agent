"""Autonomous Multi-Agent Orchestrator: Developer -> Tester -> Debugger -> Reviewer.

The orchestrator is intentionally evidence-driven:
- an LLM stage is only successful when the workspace actually changed;
- the tester runs real automated verification;
- the reviewer receives a mission-scoped diff, not the whole dirty working tree;
- every gate and outcome is persisted in SQLite;
- interrupted missions can be resumed in a new process.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from crewai import LLM

from nl_coding_agent.agents.crew_backend import CrewAIBackend, CrewRuntime
from nl_coding_agent.agents.specs import resolve_role
from nl_coding_agent.app.services import Event, get_event_bus
from nl_coding_agent.core import candidate_verification, promotion
from nl_coding_agent.core.mission_lock import MissionLockError, mission_lock
from nl_coding_agent.core.promotion import GateFailure
from nl_coding_agent.core.roadmap import extract_paths
from nl_coding_agent.core.run_control import RunControl, RunStopped
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
    get_task,
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
    set_mission_staging,
    set_promotion_status,
    update_mission_result,
    update_mission_status,
    update_task_status,
)
from nl_coding_agent.tools.crew_tools import get_project_tools
from nl_coding_agent.tools.filesystem import scoped_patch_file, scoped_write_file
from nl_coding_agent.tools.git_tools import get_git_diff

DEFAULT_DEVELOPER_MODEL = os.environ.get(
    "NL_DEVELOPER_MODEL", "ollama/qwen2.5-coder:7b-instruct-q4_K_M"
)
DEFAULT_REVIEWER_MODEL = os.environ.get(
    "NL_REVIEWER_MODEL", "ollama/qwen3.5:9b"
)
DEFAULT_DEBUG_MODEL = os.environ.get("NL_DEBUG_MODEL", DEFAULT_DEVELOPER_MODEL)

VERIFY_TIMEOUT_S = int(os.environ.get("NL_VERIFY_TIMEOUT_S", "600"))
MAX_REPAIR_ATTEMPTS = int(os.environ.get("NL_MAX_REPAIRS", "2"))
MAX_TOTAL_STAGE_ATTEMPTS = MAX_REPAIR_ATTEMPTS + 3   # hard ceiling across resumes
HARNESS_VERSION = promotion.HARNESS_VERSION


class DeveloperNoChangeError(RuntimeError):
    """Raised when the developer stage produced no workspace change."""


class ScopeViolationError(RuntimeError):
    """Raised when a stage modified files outside its declared write scope."""


class VerificationError(RuntimeError):
    """Raised when automated verification cannot be made to pass."""


#: Candidate files that count as implementation evidence for a functional
#: requirement. Documentation-only candidates are rejected before promotion.
_IMPLEMENTATION_SUFFIXES = (
    ".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg",
    ".bat", ".ps1", ".sh", ".js", ".mjs", ".ts", ".tsx", ".css", ".qss",
)
_IMPLEMENTATION_PREFIXES = ("tests/", "scripts/", "nl_coding_agent/", "installer/")
_DOCUMENTATION_REQUIREMENT_TOKENS = ("documentation", "docs-only", "readme", "policy document")


def is_implementation_path(rel_path: str) -> bool:
    """True when a changed path is code/test/config evidence, not a Markdown doc."""
    rel = str(rel_path or "").replace("\\", "/").lstrip("./").lower()
    if not rel:
        return False
    if rel.endswith(".md") or rel.endswith(".rst") or rel.endswith(".txt"):
        return False
    if rel.endswith(_IMPLEMENTATION_SUFFIXES):
        return True
    return rel.startswith(_IMPLEMENTATION_PREFIXES)


def _truncate(text: str, limit: int = 20_000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _make_llm(model_name: str, base_url: str = "http://127.0.0.1:11434",
              temperature: float = 0.1, *, project_id: int | None = None) -> LLM:
    """Create a permission-checked CrewAI LLM instance for Ollama.

    Fail-closed escalation gate: a cloud model needs an explicit CLOUD grant and
    a non-loopback endpoint needs an explicit NETWORK grant. There is no flag or
    environment variable that disables this check. project_id applies the
    project-scoped permission policy when the caller (stage-3 supervisor) has one.
    """
    from nl_coding_agent.core.permissions import assert_model_permitted

    assert_model_permitted(model_name, base_url, project_id=project_id)
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

    def __init__(self, project_root: Path | str, base_url: str = "http://127.0.0.1:11434",
                 project_id: int | None = None,
                 crew_runtime: CrewRuntime | None = None):
        self.root = Path(project_root).resolve()
        self.base_url = base_url
        self.project_id = int(project_id) if project_id is not None else None
        self.crew_runtime: CrewRuntime = (
            crew_runtime if crew_runtime is not None
            else CrewAIBackend(base_url=self.base_url, project_id=self.project_id)
        )
        self.bus = get_event_bus()
        self._last_verification = None

    # ------------------------------------------------------------------ helpers

    def _emit(self, source: str, level: str, message: str, **payload) -> None:
        self.bus.emit(Event(source=source, level=level, message=message, payload=payload or None))

    @staticmethod
    def _checkpoint(control: RunControl | None, stage: str) -> None:
        """Call a supervisor checkpoint at a safe stage boundary only.

        The final checkpoint runs before entering promotion. No checkpoint may
        interrupt the journaled CAS/promotion operation itself.
        """
        if control is not None:
            control.checkpoint(stage)

    def _call_model(
        self,
        role: str,
        model_name: str,
        prompt: str,
        *,
        goal: str,
        backstory: str,
        expected_output: str,
        tools: list | None = None,
    ) -> str:
        """Single model-invocation seam; tests monkeypatch this method.

        No stage method may construct Agent/Task/Crew or touch a model directly: every
        model call goes through the CrewRuntime seam (CrewAIBackend by default,
        FakeCrewRuntime in tests) so the staged-candidate harness can be tested without
        Ollama and the default behavior stays exactly one single-agent sequential Crew.
        """
        self._assert_execution_permissions()
        spec = resolve_role(role)
        result = self.crew_runtime.run_agent(
            spec,
            prompt,
            goal=goal,
            backstory=backstory,
            model_name=model_name,
            expected_output=expected_output,
            tools=tools,
            project_id=self.project_id,
        )
        return result.text

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

    # ----------------------------------------------------------- harness helpers

    def _mission_input_paths(self) -> list[str]:
        """Files that are mission input and must never be modified by the model."""
        return [p for p in promotion.MISSION_INPUT_DENY if (self.root / p).is_file()]

    def _recovery_dir(self) -> Path:
        return db_path().parent / "recovery"

    def _evidence_dir(self) -> Path:
        return db_path().parent / "verification"

    def _save_promotion_status(self, mission_id: int, status: str | None) -> None:
        set_promotion_status(mission_id, status)
        self._emit("harness", "info", f"Promotion state: {status}", mission_id=mission_id)

    def _assert_harness_mission(self, mission: dict) -> None:
        self._assert_project_binding(mission)
        self._assert_execution_permissions()
        if mission.get("harness_version") != HARNESS_VERSION:
            raise GateFailure(
                f"Mission #{mission['id']} predates the staged-candidate harness "
                f"(harness_version={mission.get('harness_version')!r}); create a new mission "
                "instead of resuming it.",
                code="legacy-mission",
            )

    def _assert_project_binding(self, mission: dict) -> None:
        """Bind execution and provider policy to the mission's registered project."""
        from nl_coding_agent.projects.registry import get_project

        project_id = mission.get("project_id")
        project = get_project(project_id) if project_id is not None else None
        if (not project or Path(project["root"]).resolve() != self.root
                or (self.project_id is not None and self.project_id != project_id)):
            raise GateFailure(
                "Mission does not belong to the requested project; execution denied",
                code="project-mismatch",
            )
        self.project_id = int(project_id)

    def _assert_execution_permissions(self) -> None:
        from nl_coding_agent.core import permissions

        try:
            for scope in (permissions.READ, permissions.WRITE, permissions.EXECUTE):
                permissions.require(scope, project_id=self.project_id)
        except permissions.PermissionDenied as exc:
            raise GateFailure(str(exc), code="permission-denied") from exc

    def _ensure_stage(self, mission_id: int, dev_task: dict | None, goal: str) -> promotion.Stage:
        mission = get_mission(mission_id) or {}
        stored = mission.get("staging_dir")
        if stored:
            stage = promotion.load_stage(stored)
            if stage.project_root != self.root:
                raise GateFailure("Staged candidate belongs to a different project root", code="stage-mismatch")
            return stage
        write_paths = list((dev_task or {}).get("write_paths") or [])
        scope = promotion.derive_scope(self.root, write_paths or extract_paths(goal))
        stage = promotion.begin_stage(self.root, mission_id, scope)
        set_mission_staging(mission_id, str(stage.stage_dir))
        self._save_promotion_status(mission_id, "staged")
        record_handoff(
            mission_id,
            "orchestrator",
            "developer",
            f"Candidate stage created: {stage.stage_dir.name}",
            {"stage_dir": str(stage.stage_dir), "scope": list(stage.scope)},
        )
        return stage

    def _validate_stage(self, stage: promotion.Stage) -> dict:
        verdict = promotion.validate(stage, deny_paths=self._mission_input_paths())
        if verdict["valid"]:
            self._save_promotion_status(stage.mission_id, "validated")
        return verdict

    def _assert_implementation_candidate(self, mission_id: int, stage: promotion.Stage) -> None:
        """Reject documentation-only candidates for functional backlog requirements."""
        mission = get_mission(mission_id) or {}
        requirement_id = mission.get("requirement_id")
        if not requirement_id:
            return
        title = str(mission.get("title") or "").lower()
        if any(token in title for token in _DOCUMENTATION_REQUIREMENT_TOKENS):
            return
        manifest = promotion.read_manifest(stage)
        changed = sorted((manifest.get("changed") or {}).keys())
        if not any(is_implementation_path(path) for path in changed):
            raise GateFailure(
                "Documentation-only candidate rejected for implementation requirement "
                + str(requirement_id)
                + ": changed paths "
                + repr(changed)
                + " contain no code/test evidence.",
                code="documentation-only-candidate",
            )

    def _run_verification(self, stage: promotion.Stage, task_id: int) -> candidate_verification.VerificationReport:
        self._assert_execution_permissions()
        baseline = promotion.read_manifest(stage)["baseline"]
        report = candidate_verification.verify_candidate(
            stage.workspace,
            stage.stage_dir,
            baseline,
            timeout_s=VERIFY_TIMEOUT_S,
            report_path=stage.stage_dir / "verification" / "report.json",
        )
        for suite in (report.candidate, report.oracle):
            record_verification_run(
                mission_id=stage.mission_id,
                task_id=task_id,
                command=f"verify:{suite.suite} " + " ".join(suite.command),
                exit_code=suite.exit_code if suite.exit_code is not None else -1,
                stdout=_truncate(suite.stdout_tail, 40_000),
                stderr=_truncate(suite.stderr_tail, 40_000),
                passed=suite.passed,
            )
        self._last_verification = report
        if report.passed:
            promotion.mark_verified(
                stage,
                passed=True,
                evidence=json.dumps({
                    "candidate": report.candidate.failures or "pass",
                    "oracle": report.oracle.failures or "pass",
                    "duration_s": round(report.candidate.duration_s + report.oracle.duration_s, 2),
                    "snapshot_sha256": self._candidate_fingerprint(stage),
                })[:2000],
            )
            self._save_promotion_status(stage.mission_id, "verified")
        return report

    def _last_verification_dict(self) -> dict | None:
        report = self._last_verification
        if report is None:
            return None
        try:
            return candidate_verification.report_to_dict(report)
        except Exception:
            return None

    @staticmethod
    def _candidate_fingerprint(stage: promotion.Stage) -> str:
        content = json.dumps(promotion.candidate_snapshot(stage), sort_keys=True).encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def _rebind_persisted_verification(self, mission_id: int, stage: promotion.Stage) -> None:
        """Keep a persisted verified candidate verifiable across a resume.

        Re-validating a persisted candidate resets the broker's verified marker, so a
        resumed mission that had already passed verification must re-bind the recorded
        evidence to the exact staged hashes before promotion is allowed.
        """
        manifest = promotion.read_manifest(stage)
        try:
            evidence = json.loads(manifest.get("evidence") or "{}")
        except (TypeError, ValueError):
            evidence = {}
        if (not isinstance(evidence, dict)
                or evidence.get("snapshot_sha256") != self._candidate_fingerprint(stage)):
            raise GateFailure(
                "Persisted verification does not match the staged candidate; re-verification required",
                code="verification-stale",
            )
        if manifest.get("verified"):
            self._save_promotion_status(mission_id, "verified")
            return
        if not manifest.get("validated"):
            raise GateFailure(
                "Persisted staged candidate is not validated; cannot reuse verification evidence",
                code="stage-not-validated",
            )
        try:
            promotion.mark_verified(
                stage,
                passed=True,
                evidence=str(manifest.get("evidence") or "restored from persisted tester completion"),
            )
        except Exception as exc:  # broker refuses if staged bytes moved since validation
            raise GateFailure(
                "Staged candidate changed after verification; re-verification required: " + str(exc),
                code="stage-invalid",
                details={"error": str(exc)},
            ) from exc
        self._save_promotion_status(mission_id, "verified")

    def _promote_candidate(self, stage: promotion.Stage) -> dict:
        self._assert_execution_permissions()
        self._save_promotion_status(stage.mission_id, "promoting")
        try:
            result = promotion.promote(stage, recovery_dir=self._recovery_dir())
        except GateFailure as exc:
            self._save_promotion_status(
                stage.mission_id,
                "cas-conflict" if exc.code == "cas-conflict" else "promotion-failed",
            )
            raise
        self._save_promotion_status(stage.mission_id, "promoted")
        record_handoff(
            stage.mission_id,
            "orchestrator",
            "user",
            f"Promoted {len(result['promoted'])} file(s) to the live tree",
            {"promoted": result["promoted"], "hashes": result.get("hashes", {})},
        )
        return result

    def _persisted_review(self, mission_id: int) -> tuple[str, str]:
        for handoff in reversed(get_handoffs(mission_id)):
            if handoff.get("from_role") != "reviewer" or handoff.get("to_role") != "orchestrator":
                continue
            payload = handoff.get("payload") or {}
            verdict = payload.get("verdict")
            if verdict in ("APPROVE", "REJECT"):
                return payload.get("review_notes") or handoff.get("summary") or "", verdict
        for task in get_tasks(mission_id):
            if task.get("agent_role") != "reviewer":
                continue
            output = self._latest_output(task["id"])
            if output.strip():
                return output, parse_reviewer_verdict(output)
        return "", "REJECT"

    # -------------------------------------------------------------- finalization

    def _result_payload(
        self,
        mission_id: int,
        *,
        status: str,
        mission_diff: str = "",
        diff_stat: str = "",
        changed_paths: list[str] | None = None,
        review: str = "",
        verdict: str = "",
        error: str | None = None,
        promotion_status: str | None = None,
    ) -> dict:
        if promotion_status is None:
            mission = get_mission(mission_id) or {}
            promotion_status = mission.get("promotion_status")
        payload = {
            "status": status,
            "mission_id": mission_id,
            "git_diff": get_git_diff(self.root),
            "mission_diff": mission_diff,
            "diff_stat": diff_stat,
            "changed_paths": list(changed_paths or []),
            "review": review,
            "verdict": verdict,
            "promotion_status": promotion_status,
            "handoffs": get_handoffs(mission_id),
            "verification_runs": get_verification_runs(mission_id),
            "tasks": get_tasks(mission_id),
            "attempts": get_task_attempts(mission_id),
            "progress": mission_progress(mission_id),
        }
        if error is not None:
            payload["error"] = error
        return payload

    def _finalize_completed(
        self,
        mission_id: int,
        goal: str,
        baseline: dict[str, str],
        *,
        review_text: str,
        verdict: str,
        summary: str,
    ) -> dict:
        """Single writer of missions.status='completed' (live diff is authoritative)."""
        diff, changed, stat = self._mission_diff(baseline)
        changed = self._collect_changed_paths(mission_id, changed)
        if not diff.strip() and changed:
            recovered_diff = get_git_diff(self.root)
            if recovered_diff.strip():
                diff = recovered_diff
                stat = diff_stats(diff)
        mission = get_mission(mission_id) or {}
        promotion_status = mission.get("promotion_status") or "promoted"
        update_mission_result(
            mission_id,
            "completed",
            result_summary=summary or None,
            review_verdict=verdict or None,
            diff_stat=stat,
            changed_paths=changed,
        )
        record_handoff(
            mission_id,
            "orchestrator",
            "user",
            summary or "Mission finished with status completed",
            {
                "status": "completed",
                "verdict": verdict,
                "changed_paths": changed,
                "diff_stat": stat,
                "promotion_status": promotion_status,
            },
        )
        self._emit(
            "orchestrator",
            "info",
            f"Mission #{mission_id} finished: completed",
            mission_id=mission_id,
            changed_paths=changed,
        )
        return self._result_payload(
            mission_id,
            status="completed",
            mission_diff=diff,
            diff_stat=stat,
            changed_paths=changed,
            review=review_text,
            verdict=verdict,
            promotion_status=promotion_status,
        )

    def _finalize_blocked(
        self,
        mission_id: int,
        reason: str,
        verdict: str,
        *,
        review_text: str = "",
        stage: promotion.Stage | None = None,
        code: str | None = None,
        details: dict | None = None,
    ) -> dict:
        """Blocked before/without promotion: nothing from the candidate is applied."""
        staged_paths: list[str] = []
        stage_dir: str | None = None
        if stage is not None:
            stage_dir = str(stage.stage_dir)
            try:
                staged_paths = sorted((promotion.read_manifest(stage).get("changed") or {}).keys())
            except Exception:
                staged_paths = []
        update_mission_result(
            mission_id,
            "blocked",
            result_summary=reason,
            review_verdict=verdict or None,
            diff_stat="",
            changed_paths=[],
        )
        record_handoff(
            mission_id,
            "orchestrator",
            "user",
            reason,
            {
                "status": "blocked",
                "code": code,
                "details": details,
                "staged_paths": staged_paths,
                "stage_dir": stage_dir,
            },
        )
        self._emit(
            "orchestrator",
            "warning",
            f"Mission #{mission_id} blocked: {reason}",
            mission_id=mission_id,
            code=code,
        )
        return self._result_payload(
            mission_id,
            status="blocked",
            diff_stat="",
            changed_paths=[],
            review=review_text,
            verdict=verdict,
            error=reason,
        )

    def _finalize_interrupted(
        self,
        mission_id: int,
        stage: promotion.Stage | None,
        *,
        summary: str,
    ) -> dict:
        """Interrupted after a stage: the staged candidate is retained, live unchanged."""
        staged_paths: list[str] = []
        stage_dir: str | None = None
        if stage is not None:
            stage_dir = str(stage.stage_dir)
            try:
                staged_paths = sorted((promotion.read_manifest(stage).get("changed") or {}).keys())
            except Exception:
                staged_paths = []
        update_mission_status(mission_id, "interrupted")
        record_handoff(
            mission_id,
            "orchestrator",
            "user",
            summary,
            {
                "status": "interrupted",
                "staged_paths": staged_paths,
                "stage_dir": stage_dir,
                "live_changes": "none",
            },
        )
        self._emit("orchestrator", "warning", summary, mission_id=mission_id)
        return self._result_payload(
            mission_id,
            status="interrupted",
            diff_stat="",
            changed_paths=[],
        )

    def _failed_result(self, mission_id: int, exc: Exception) -> dict:
        message = f"Mission #{mission_id} failed: {exc}"
        self._emit("orchestrator", "error", message, mission_id=mission_id)
        record_handoff(mission_id, "orchestrator", "user", message, {"error": str(exc)})
        update_mission_status(mission_id, "failed")
        return self._result_payload(mission_id, status="failed", error=str(exc))

    # ---------------------------------------------------------------- public API

    def run_mission(
        self,
        mission_id: int,
        goal: str | None = None,
        developer_model: str | None = None,
        reviewer_model: str | None = None,
        debug_model: str | None = None,
        stop_after: str | None = None,
        control: RunControl | None = None,
    ) -> dict:
        """Execute or resume a complete mission through all gates.

        control is the optional cooperative supervisor handle; its checkpoints are
        only called at safe stage boundaries (never around the promotion write).
        """
        mission = get_mission(mission_id)
        if not mission:
            raise ValueError(f"Mission #{mission_id} not found")
        try:
            self._assert_project_binding(mission)
        except GateFailure as exc:
            # A wrong-project request must not mutate the owning mission's state.
            return self._result_payload(mission_id, status="blocked", error=str(exc))
        goal = (goal or mission.get("goal") or "").strip()
        if not goal:
            raise ValueError(f"Mission #{mission_id} has no goal")

        developer_model = developer_model or DEFAULT_DEVELOPER_MODEL
        reviewer_model = reviewer_model or DEFAULT_REVIEWER_MODEL
        debug_model = debug_model or DEFAULT_DEBUG_MODEL

        if mission["status"] == "completed":
            return self._result_payload(
                mission_id,
                status="completed",
                mission_diff="",
                diff_stat=mission.get("diff_stat") or "",
                changed_paths=json.loads(mission.get("changed_paths") or "[]"),
                review=mission.get("result_summary") or "",
                verdict=mission.get("review_verdict") or "",
                promotion_status=mission.get("promotion_status"),
            )

        try:
            with mission_lock(mission_id):
                return self._run_locked(
                    mission_id,
                    goal,
                    developer_model,
                    reviewer_model,
                    debug_model,
                    stop_after,
                    control,
                )
        except MissionLockError as exc:
            self._emit("orchestrator", "error", str(exc), mission_id=mission_id)
            update_mission_status(mission_id, "blocked")
            return self._result_payload(mission_id, status="blocked", error=str(exc))

    def _run_locked(
        self,
        mission_id: int,
        goal: str,
        developer_model: str,
        reviewer_model: str,
        debug_model: str,
        stop_after: str | None,
        control: RunControl | None = None,
    ) -> dict:
        mission = get_mission(mission_id) or {}
        existing_tasks = get_tasks(mission_id)
        stage: promotion.Stage | None = None
        baseline: dict[str, str] = {}
        try:
            from nl_coding_agent.core.doc_planning import is_document_plan_request
            if is_document_plan_request(goal):
                raise GateFailure(
                    "Document analysis/plan requests require the document planning service; "
                    "submit through Chat or open Document plan. No coding agents were started.",
                    code="document-planning-required")
            self._assert_harness_mission(mission)

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
                loaded = self._load_baseline(mission_id)
                if loaded is None:
                    baseline = self._snapshot()
                    self._emit(
                        "orchestrator", "warning",
                        "No persisted mission baseline found; using the current working tree as baseline.",
                        mission_id=mission_id,
                    )
                else:
                    baseline = loaded
            else:
                baseline = self._snapshot()
                self._save_baseline(mission_id, baseline)

            task_map = {t["agent_role"]: t for t in tasks}
            dev_task = task_map.get("developer")
            test_task = task_map.get("tester")
            rev_task = task_map.get("reviewer")

            # Candidate stage: every model write lands inside stage.workspace, never live.
            stage = self._ensure_stage(mission_id, dev_task, goal)
            outcome = promotion.reconcile(stage, recovery_dir=self._recovery_dir())
            if outcome.get("state") == "conflict":
                self._save_promotion_status(mission_id, "rollback_conflict")
                return self._finalize_blocked(
                    mission_id,
                    "Promotion journal conflict: " + json.dumps(outcome, default=str),
                    "REJECT",
                    stage=stage,
                    code="rollback-conflict",
                    details=outcome,
                )
            if outcome.get("state") == "promotion-complete" or promotion.is_live_promoted(stage):
                self._save_promotion_status(mission_id, "promoted")
                result = self._finalize_completed(
                    mission_id,
                    goal,
                    baseline,
                    review_text="",
                    verdict="APPROVE",
                    summary="Promotion recovered after crash.",
                )
                promotion.cleanup_after_terminal(
                    stage,
                    mission_status="completed",
                    evidence_dir=self._evidence_dir(),
                    verification=self._last_verification_dict(),
                )
                return result

            self._checkpoint(control, "before-developer")

            # 1. Developer: staged candidate only.
            if dev_task and dev_task["status"] != "completed":
                self._run_developer_stage(mission_id, dev_task, goal, developer_model, baseline, stage)
            elif dev_task:
                self._emit(
                    "developer", "info",
                    "Developer stage already completed; re-validating the persisted staged candidate.",
                )
                verdict = self._validate_stage(stage)
                if not verdict["valid"]:
                    raise GateFailure(
                        "Persisted staged candidate no longer validates: "
                        + "; ".join(verdict["errors"]),
                        code="candidate-rejected",
                        details={"errors": verdict["errors"]},
                    )

            self._checkpoint(control, "after-developer")

            if stop_after == "developer":
                return self._finalize_interrupted(
                    mission_id,
                    stage,
                    summary="Interrupted after developer stage (staged candidate retained).",
                )

            self._checkpoint(control, "before-tester")

            # 2. Tester: independent candidate + oracle verification, bounded repairs.
            if test_task and test_task["status"] != "completed":
                self._run_tester_stage(mission_id, test_task, debug_model, baseline, stage)
            elif test_task:
                self._emit("tester", "info", "Tester stage already completed; reusing persisted verification evidence.")
                self._rebind_persisted_verification(mission_id, stage)

            self._checkpoint(control, "after-tester")

            if stop_after == "tester":
                return self._finalize_interrupted(
                    mission_id,
                    stage,
                    summary="Interrupted after tester stage (verified candidate retained).",
                )

            self._checkpoint(control, "before-reviewer")

            # 3. Reviewer: reviews the candidate, never an applied diff.
            if rev_task and rev_task["status"] != "completed":
                review_text, verdict = self._run_reviewer_stage(mission_id, rev_task, reviewer_model, baseline, stage)
            else:
                review_text, verdict = self._persisted_review(mission_id)
                self._emit(
                    "reviewer", "info",
                    f"Reviewer stage recovered from persistence; verdict {verdict}.",
                )

            if verdict != "APPROVE":
                self._save_promotion_status(mission_id, "review_rejected")
                return self._finalize_blocked(
                    mission_id,
                    "Reviewer REJECTED the candidate diff.",
                    "REJECT",
                    review_text=review_text,
                    stage=stage,
                    code="review-rejected",
                )

            # 4. Recheck cancellation/goal policy after review, before any live write.
            self._checkpoint(control, "before-promotion")
            promotion_result = self._promote_candidate(stage)
            result = self._finalize_completed(
                mission_id,
                goal,
                baseline,
                review_text=review_text,
                verdict="APPROVE",
                summary=f"Reviewer APPROVED; promoted {len(promotion_result['promoted'])} file(s).",
            )
            promotion.cleanup_after_terminal(
                stage,
                mission_status="completed",
                evidence_dir=self._evidence_dir(),
                verification=self._last_verification_dict(),
            )
            return result
        except RunStopped as exc:
            return self._finalize_interrupted(
                mission_id,
                stage,
                summary=(
                    f"Mission interrupted at safe checkpoint '{exc.stage}': "
                    f"{exc.reason or 'stop requested'}."
                ),
            )
        except GateFailure as exc:
            self._save_promotion_status(mission_id, exc.code.replace("-", "_"))
            return self._finalize_blocked(
                mission_id,
                str(exc),
                "REJECT",
                stage=stage,
                code=exc.code,
                details=exc.details,
            )
        except (VerificationError, DeveloperNoChangeError, ScopeViolationError) as exc:
            return self._finalize_blocked(
                mission_id,
                str(exc),
                "REJECT",
                stage=stage,
                code=type(exc).__name__,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a failed mission with stage retained
            return {**self._failed_result(mission_id, exc), "promotion_status": "error"}

    # ------------------------------------------------------------------ stages

    def _run_developer_stage(
        self,
        mission_id: int,
        task_rec: dict,
        goal: str,
        model_name: str,
        baseline: dict[str, str],
        stage: promotion.Stage,
    ) -> str:
        task_id = task_rec["id"]
        write_paths = task_rec.get("write_paths") or list(stage.scope)
        update_task_status(task_id, "running")
        self._emit(
            "developer", "info",
            f"Developer agent starting work on task #{task_id} with {model_name}",
            model=model_name,
            write_paths=write_paths,
            stage_dir=str(stage.stage_dir),
        )

        tools = get_project_tools(stage.workspace)
        scope_text = (
            "Declared write scope (do not modify other files):\n- " + "\n- ".join(write_paths)
            if write_paths
            else "No explicit write scope was declared. Stay focused on the goal."
        )
        prompt = f"""
PROJECT ROOT: {self.root}
WORKSPACE (staged copy; write relative paths here): {stage.workspace}
MISSION GOAL: {goal}

{scope_text}

INSTRUCTIONS:
1. Read the relevant existing files first.
2. Implement the requested change directly in the staged workspace files.
3. Prefer patch_file for small edits. For complete files use write_file or this exact block format:
```write:<relative_path>
<valid source code>
```
4. Do NOT edit files outside the declared write scope: the candidate is rejected if you do.
5. Do NOT output 'diff --git' or unified-diff headers inside a source file.
6. Nothing is live until review and promotion; only the staged copy may change.
7. There is no shell or test runner tool: the independent tester verifies later.
8. Do NOT claim success without actually writing the files.
9. Finish with a short summary of the files you changed.
"""
        output = self._call_model(
            "Implementation Developer",
            model_name,
            prompt,
            goal=f"Implement the requested code change in the staged candidate: {goal}",
            backstory=(
                "You are an expert autonomous software engineer. You inspect existing code using read_file "
                "or list_dir, and you write the necessary files or patches using write_file or patch_file. "
                "You can also use ```write:<file_path>\n<content>``` blocks. "
                "You must produce real file changes in the staged workspace, not only a plan."
            ),
            expected_output="Summary of files actually modified in the staged workspace and the changes made.",
            tools=tools,
        )
        actions = _apply_text_actions(stage.workspace, output)
        promotion.normalize_staged_newlines(stage)
        verdict = self._validate_stage(stage)
        diff, changed, _stat = promotion.candidate_diff(stage)
        # The no-change check runs before the invalid-verdict branch: validate() reports an
        # empty candidate as invalid, which would otherwise mask DeveloperNoChangeError.
        if not changed:
            error_msg = (
                "Developer produced no workspace change. "
                f"Actions parsed: {actions or 'none'}. The model output did not modify files."
            )
            record_task_attempt(task_id, "failed", output=_truncate(output), error=_truncate(error_msg, 2000))
            update_task_status(task_id, "failed", error=_truncate(error_msg, 2000))
            raise DeveloperNoChangeError(error_msg)
        if not verdict["valid"]:
            error_msg = "; ".join(verdict["errors"])
            record_task_attempt(task_id, "failed", output=_truncate(output), error=_truncate(error_msg, 2000))
            update_task_status(task_id, "failed", error=_truncate(error_msg, 2000))
            raise GateFailure(
                "Staged candidate rejected by the validation gate: " + error_msg,
                code="candidate-rejected",
                details={"errors": verdict["errors"]},
            )
        record_task_attempt(task_id, "completed", output=_truncate(output))
        update_task_status(task_id, "completed")
        summary = (
            f"Developer staged {len(changed)} file(s): {', '.join(changed)}. "
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

    def _run_tester_stage(
        self,
        mission_id: int,
        task_rec: dict,
        debug_model: str,
        baseline: dict[str, str],
        stage: promotion.Stage,
        max_attempts: int | None = None,
    ) -> dict:
        task_id = task_rec["id"]
        fresh = get_task(task_id) or task_rec
        attempts_used = int(fresh.get("attempts") or 0)
        max_attempts = MAX_REPAIR_ATTEMPTS if max_attempts is None else max_attempts
        if attempts_used > MAX_TOTAL_STAGE_ATTEMPTS:
            raise VerificationError("Verification repair budget exhausted across resumes.")
        write_paths = task_rec.get("write_paths") or list(stage.scope)
        update_task_status(task_id, "running")
        self._emit(
            "tester", "info",
            f"Tester independently verifying the staged candidate for mission #{mission_id}",
            mission_id=mission_id,
            max_attempts=max_attempts,
        )

        last_error = "candidate validation never passed"
        report = None
        for attempt in range(max_attempts + 1):
            verdict = self._validate_stage(stage)
            if not verdict["valid"]:
                errors = "; ".join(verdict["errors"])
                last_error = errors
                record_verification_run(
                    mission_id=mission_id,
                    task_id=task_id,
                    command="harness:validate",
                    exit_code=1,
                    stdout="",
                    stderr=_truncate(errors, 40_000),
                    passed=False,
                )
                if attempt >= max_attempts:
                    break
                record_handoff(
                    mission_id=mission_id,
                    from_role="tester",
                    to_role="debugger",
                    summary=f"Candidate validation failed (attempt {attempt + 1}); calling debugger.",
                    payload={"error": _truncate(errors, 4000), "attempt": attempt + 1},
                )
                self._run_debugger(mission_id, debug_model, errors, write_paths, baseline, stage)
                continue

            self._assert_implementation_candidate(mission_id, stage)

            report = self._run_verification(stage, task_id)
            if report.passed:
                summary = (
                    "Candidate and oracle suites PASSED "
                    f"(candidate {report.candidate.duration_s}s, oracle {report.oracle.duration_s}s)"
                )
                record_handoff(
                    mission_id=mission_id,
                    from_role="tester",
                    to_role="reviewer",
                    summary=summary,
                    payload={
                        "candidate": report.candidate.passed,
                        "oracle": report.oracle.passed,
                        "report": str(report.verify_dir / "evidence" / "report.json"),
                    },
                )
                record_task_attempt(task_id, "completed", output=summary)
                update_task_status(task_id, "completed")
                self._emit("tester", "info", summary, mission_id=mission_id)
                return {"report": report}

            last_error = report.error or "candidate/oracle suite failed"
            if any(suite.infrastructure_failure for suite in (report.candidate, report.oracle)):
                # A broken/unsupported harness cannot be repaired by editing project source.
                break
            if attempt >= max_attempts:
                break
            error_msg = (
                f"Verification failed (attempt {attempt + 1}): {report.error}\n"
                f"CANDIDATE:\n{report.candidate.stdout_tail[-4000:]}\n{report.candidate.stderr_tail[-4000:]}\n"
                f"ORACLE:\n{report.oracle.stdout_tail[-4000:]}\n{report.oracle.stderr_tail[-4000:]}"
            )
            record_handoff(
                mission_id=mission_id,
                from_role="tester",
                to_role="debugger",
                summary=f"Verification failed on attempt {attempt + 1}. Calling debugger.",
                payload={"error": _truncate(error_msg, 4000), "attempt": attempt + 1},
            )
            self._emit(
                "tester", "warning",
                f"Verification failed on attempt {attempt + 1}. Calling debugger.",
                mission_id=mission_id,
            )
            self._run_debugger(mission_id, debug_model, error_msg, write_paths, baseline, stage)

        error_summary = _truncate(last_error, 4000)
        record_task_attempt(task_id, "failed", error=error_summary)
        update_task_status(task_id, "failed", error=error_summary)
        self._save_promotion_status(mission_id, "verification_failed")
        failures = []
        if report is not None:
            if not report.candidate.passed:
                failures.append("candidate: " + str(report.candidate.failures or report.candidate.error))
            if not report.oracle.passed:
                failures.append("oracle: " + str(report.oracle.failures or report.oracle.error))
        raise VerificationError(
            f"Verification failed after {attempt + 1} attempt(s): "
            + ("; ".join(failures) if failures else error_summary)
        )

    def _run_debugger(
        self,
        mission_id: int,
        model_name: str,
        error_msg: str,
        write_paths: list[str],
        baseline: dict[str, str],
        stage: promotion.Stage,
    ) -> None:
        """Debugger agent repairs only the staged candidate based on verification failures."""
        tools = get_project_tools(stage.workspace)
        scope_text = (
            "Stay inside the staged declared write scope:\n- " + "\n- ".join(write_paths)
            if write_paths
            else "Stay focused on the failing code."
        )
        prompt = f"""
PROJECT ROOT: {self.root}
WORKSPACE (staged copy; write relative paths here): {stage.workspace}
TEST FAILURE LOGS:
{_truncate(error_msg, 12_000)}

{scope_text}

INSTRUCTIONS:
1. Examine the failing tests and the current staged code.
2. Fix the error directly in the staged source files using patch_file or:
```write:<relative_path>
<valid source code>
```
3. Do NOT edit files outside the declared write scope; out-of-scope changes are rejected.
4. Nothing is live until review and promotion; only the staged copy may change.
5. There is no shell or test runner tool available.
6. Do NOT include 'diff --git' or unified-diff headers inside a source file.
7. Keep changes minimal and focused on resolving the error.
"""
        output = self._call_model(
            "Software Debugger",
            model_name,
            prompt,
            goal="Analyze the verification failure and fix the staged candidate.",
            backstory=(
                "You are an expert troubleshooter. You read error logs, locate broken code, "
                "and apply precise fixes using write_file or patch_file in the staged workspace."
            ),
            expected_output="Summary of the staged fix actually applied.",
            tools=tools,
        )
        actions = _apply_text_actions(stage.workspace, output)
        promotion.normalize_staged_newlines(stage)
        diff, changed, _stat = promotion.candidate_diff(stage)
        summary = (
            f"Debugger staged {len(changed)} file(s): {', '.join(changed)}."
            if changed
            else "Debugger produced no staged file change."
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
        stage: promotion.Stage,
    ) -> tuple[str, str]:
        task_id = task_rec["id"]
        update_task_status(task_id, "running")
        diff, changed, stat = promotion.candidate_diff(stage)
        manifest = promotion.read_manifest(stage)
        validation_text = (
            f"validated={bool(manifest.get('validated'))} validated_by_broker=True "
            f"verified={bool(manifest.get('verified'))} "
            f"evidence={(str(manifest.get('evidence') or '(none)'))[:500]}"
        )
        verification_text = "\n".join(
            f"- {run.get('command')}: exit {run.get('exit_code')} "
            f"({'PASS' if run.get('passed') else 'FAIL'})"
            for run in get_verification_runs(mission_id)
        ) or "- No verification run recorded."
        self._emit(
            "reviewer", "info",
            f"Reviewer inspecting the staged candidate ({stat}) on task #{task_id}",
            mission_id=mission_id,
        )
        prompt = f"""
PROJECT ROOT: {self.root}
CANDIDATE STAGE: {stage.stage_dir}
CANDIDATE CHANGED FILES: {', '.join(changed) or '(none)'}

VALIDATION RESULT:
{validation_text}

VERIFICATION RUNS:
{verification_text}

CANDIDATE DIFF TO REVIEW:
{_truncate(diff, 60_000)}

INSTRUCTIONS:
1. This candidate is NOT yet applied to the live project. Review only the candidate diff above.
2. An APPROVE verdict leads to promotion; a REJECT verdict keeps the candidate unapplied.
3. Check correctness, safety, scope adherence, and missing tests.
4. Base every claim on the candidate diff, changed-file list, validation result and verification runs above. Do not invent imports, files, or failures that are not present in that evidence.
5. Start your response with exactly 'APPROVE' or 'REJECT' on the first line.
6. Follow the verdict with concise review notes and blocking issues.
"""
        try:
            review_text = self._call_model(
                "Code Reviewer & Quality Gatekeeper",
                model_name,
                prompt,
                goal="Verify code quality, adherence to scope, and absence of regressions in the candidate diff.",
                backstory=(
                    "You are a strict, diligent senior engineer. You review only the candidate diff. "
                    "You give an APPROVE or REJECT verdict on the first line."
                ),
                expected_output="APPROVE or REJECT verdict on the first line, followed by review notes.",
            )
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
                    "candidate": True,
                },
            )
            self._save_promotion_status(mission_id, "reviewed" if verdict == "APPROVE" else "review_rejected")
            self._emit("reviewer", "info", summary, mission_id=mission_id, verdict=verdict)
            return review_text, verdict
        except Exception as exc:
            record_task_attempt(task_id, "failed", error=str(exc))
            update_task_status(task_id, "failed", error=str(exc))
            self._emit("reviewer", "error", f"Review failed: {exc}", mission_id=mission_id)
            raise

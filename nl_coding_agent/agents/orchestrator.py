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
import dataclasses
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
from nl_coding_agent.persistence.database import db_path, get_setting, set_setting
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

VERIFY_TIMEOUT_S = int(os.environ.get("NL_VERIFY_TIMEOUT_S", "3600"))
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
              temperature: float = 0.1, *, project_id: int | None = None,
              role: str | None = None) -> LLM:
    """Create a permission-checked CrewAI LLM instance for Ollama.

    Context length is deliberately not set here: Ollama's own model/server
    settings own it. Only explicitly persisted generation parameters are sent;
    unconfigured values remain provider defaults.
    """
    from nl_coding_agent.core.permissions import assert_model_permitted

    assert_model_permitted(model_name, base_url, project_id=project_id)
    kwargs: dict = {"model": model_name, "base_url": base_url, "temperature": temperature}
    # Persistent per-model/per-role generation parameters. Missing values are
    # intentionally omitted so the provider keeps its own defaults.
    try:
        from nl_coding_agent.models.generation_params import effective_params
        params = effective_params(model_name=model_name, role=role)
        kwargs.update(_llm_generation_kwargs(params))
    except Exception:
        pass
    return LLM(**kwargs)


#: CrewAI/OpenAI-compatible kwargs accepted directly.
_DIRECT_LLM_PARAMS = {
    "temperature", "top_p", "seed", "max_tokens", "frequency_penalty",
    "presence_penalty", "stop",
}
#: Ollama-native options that must travel via extra_body.options.
_OLLAMA_OPTION_PARAMS = {
    "top_k", "min_p", "repeat_penalty", "repeat_last_n", "mirostat",
    "mirostat_tau", "mirostat_eta", "num_predict", "tfs_z", "typical_p",
}


def _llm_generation_kwargs(params: dict | None) -> dict:
    """Translate persisted generation params without imposing context length."""
    selected = dict(params or {})
    kwargs: dict = {}
    options: dict = {}
    for key, value in selected.items():
        if key == "num_ctx":
            # Context length belongs to the Ollama application, never to NL Code.
            continue
        if key in _DIRECT_LLM_PARAMS:
            kwargs[key] = value
        elif key in _OLLAMA_OPTION_PARAMS:
            options[key] = value
    if options:
        kwargs["extra_body"] = {"options": options}
    return kwargs


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


def _apply_unified_diff(project_root: Path, rel_path: str, diff_text: str) -> None:
    """Apply a model-emitted unified diff through the existing scoped writer.

    This is deliberately a small parser for the exact patch shape local models
    emit (git-style headers plus @@ hunks); it never executes model code.
    """
    current = (Path(project_root).resolve() / rel_path).read_text(encoding="utf-8")
    source = current.splitlines(keepends=True)
    hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    output: list[str] = []
    cursor = 0
    matched = False

    def find_context(expected: str, start: int) -> int:
        """Tolerate off-by-a-few hunk headers from small local models."""
        wanted = expected.rstrip("\r\n")
        for distance in range(0, 41):
            for candidate in (start + distance, start - distance):
                if 0 <= candidate < len(source):
                    if source[candidate].rstrip("\r\n") == wanted:
                        return candidate
        return -1

    for raw in str(diff_text or "").splitlines(keepends=True):
        if raw.startswith(("--- ", "+++ ", "diff ", "index ")):
            continue
        match = hunk_re.match(raw)
        if match:
            matched = True
            old_start = max(0, int(match.group(1)) - 1)
            output.extend(source[cursor:old_start])
            cursor = old_start
            continue
        if not matched:
            continue
        if raw.startswith("\\ No newline"):
            continue
        if raw.startswith(" "):
            expected = raw[1:]
            located = find_context(expected, cursor)
            if located < 0:
                raise ValueError("unified diff context mismatch in " + rel_path)
            output.extend(source[cursor:located])
            output.append(source[located])
            cursor = located + 1
        elif raw.startswith("-"):
            expected = raw[1:]
            located = find_context(expected, cursor)
            if located < 0:
                raise ValueError("unified diff deletion mismatch in " + rel_path)
            output.extend(source[cursor:located])
            cursor = located + 1
        elif raw.startswith("+"):
            output.append(raw[1:] + ("\n" if not raw[1:].endswith(("\n", "\r")) else ""))
    if not matched:
        raise ValueError("no unified-diff hunk found for " + rel_path)
    output.extend(source[cursor:])
    scoped_write_file(project_root, rel_path, "".join(output))


def _apply_python_tool_calls(project_root: Path, text: str) -> list[str]:
    """Recover model-emitted Python calls such as patch_file('p', '''diff''')."""
    import ast

    actions: list[str] = []
    root = Path(project_root).resolve()
    blocks = re.findall(r"```(?:python|py)\r?\n(.*?)```", text, re.DOTALL)
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            # A malformed trailing statement must not hide a literal tool call.
            # Extract only the fixed literal form below; never eval/exec.
            calls = []
        else:
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        if not calls:
            pattern = re.compile(
                r"(write_file|patch_file)\(\s*(['\"])(.*?)\2\s*,\s*"
                r"(\"\"\"|''')(.*?)\4\s*\)",
                re.DOTALL,
            )
            for match in pattern.finditer(block):
                name = match.group(1)
                rel_path = match.group(3)
                content = match.group(5)
                try:
                    if name == "write_file":
                        scoped_write_file(root, rel_path, clean_file_content(content, rel_path))
                        actions.append(f"Wrote {rel_path} via malformed Python tool call")
                    else:
                        _apply_unified_diff(root, rel_path, content)
                        actions.append(f"Patched {rel_path} via malformed Python unified diff")
                except Exception as exc:
                    actions.append(f"Malformed Python tool call rejected for {rel_path}: {exc}")
            continue
        for call in calls:
            func = call.func
            name = func.id if isinstance(func, ast.Name) else None
            if name not in ("patch_file", "write_file"):
                continue
            positional: list[str] = []
            keywords: dict[str, str] = {}
            for arg in call.args[:3]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    positional.append(arg.value)
            for keyword in call.keywords:
                if (keyword.arg in ("path", "content", "diff", "patch", "target", "replacement")
                        and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)):
                    keywords[str(keyword.arg)] = keyword.value.value
            rel_path = keywords.get("path") or (positional[0] if positional else "")
            if not rel_path:
                continue
            try:
                if name == "write_file":
                    content = keywords.get("content") or (
                        positional[1] if len(positional) > 1 else "")
                    if not content:
                        continue
                    scoped_write_file(root, rel_path, clean_file_content(content, rel_path))
                    actions.append(f"Wrote {rel_path} via Python tool call")
                elif "target" in keywords and "replacement" in keywords:
                    _apply_snippet_patch(root, rel_path, keywords["target"],
                                         keywords["replacement"])
                    actions.append(f"Patched {rel_path} via Python snippet call")
                elif len(positional) >= 3:
                    _apply_snippet_patch(root, rel_path, positional[1], positional[2])
                    actions.append(f"Patched {rel_path} via Python snippet call")
                else:
                    diff = (keywords.get("diff") or keywords.get("patch")
                            or (positional[-1] if len(positional) >= 2 else ""))
                    if not diff:
                        continue
                    _apply_unified_diff(root, rel_path, diff)
                    actions.append(f"Patched {rel_path} via Python unified diff")
            except Exception as exc:
                actions.append(f"Python tool call rejected for {rel_path}: {exc}")
    return actions


def _apply_snippet_patch(project_root: Path, rel_path: str, target: str,
                         replacement: str) -> None:
    """Apply a literal snippet patch through the scoped filesystem writer.

    Local-model output is never executed. A model that emits a duplicate method
    signature is rejected by the validation gate rather than rewritten by a
    fragile heuristic; the retry feedback asks for an exact snippet.
    """
    if not str(target):
        raise ValueError("Refusing an empty patch target")
    scoped_patch_file(Path(project_root).resolve(), rel_path, target, replacement)


def _apply_text_actions(project_root: Path, text: str, *, project_id: int | None = None,
                        mission_id: int | None = None, role: str | None = None,
                        model: str | None = None) -> list[str]:
    """Execute write/patch actions emitted as text by a local model.

    This is a fallback for models that describe a tool call instead of using the
    native tool API.  Every action is scoped through the filesystem safety layer.
    """
    actions: list[str] = []
    root = Path(project_root).resolve()

    # Some local models emit one JSON tool object per line inside a Python fence
    # instead of a JSON array or a ```json fence. Parse the literal objects only.
    for block in re.findall(r"```(?:python|py)\r?\n(.*?)```", text, re.DOTALL):
        for line in block.splitlines():
            candidate = line.strip().rstrip(",")
            if not candidate.startswith("{"):
                continue
            try:
                item = json.loads(candidate)
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("tool") or item.get("action")
            args = item.get("arguments") or item.get("args")
            if not isinstance(args, dict):
                continue
            try:
                if name == "write_file" and "path" in args and "content" in args:
                    content = clean_file_content(str(args["content"]), str(args["path"]))
                    scoped_write_file(root, str(args["path"]), content)
                    actions.append(f"Wrote {args['path']} via fenced JSON line")
                elif name == "patch_file" and {"path", "target", "replacement"} <= set(args):
                    target = str(args["target"])
                    if not target:
                        raise ValueError("empty patch target")
                    _apply_snippet_patch(root, str(args["path"]), target,
                                         str(args["replacement"]))
                    actions.append(f"Patched {args['path']} via fenced JSON line")
            except Exception as exc:
                actions.append(f"Fenced JSON action rejected: {exc}")

    # Full-file fenced form used by many local models:
    # ```python
    # --- catalog/repository.py ---
    # <complete file>
    # ```
    section_pattern = re.compile(
        r"```(?:python|py)\r?\n---\s*([^\r\n]+?)\s*---\r?\n(.*?)```",
        re.DOTALL,
    )
    for match in section_pattern.finditer(text):
        rel_path = match.group(1).strip().strip("`")
        if not rel_path or " " in rel_path:
            continue
        try:
            scoped_write_file(root, rel_path,
                              clean_file_content(match.group(2), rel_path))
            actions.append(f"Wrote {rel_path} via section code block")
        except Exception as exc:
            actions.append(f"Failed to write {rel_path}: {exc}")
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
                    _apply_snippet_patch(root, str(args["path"]),
                                         str(args["target"]), str(args["replacement"]))
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
            _apply_snippet_patch(root, rel_path, match.group(2), match.group(3))
            actions.append(f"Patched {rel_path} via patch block")
        except Exception as exc:
            actions.append(f"Failed to patch {rel_path}: {exc}")

    actions.extend(_apply_python_tool_calls(root, text))
    try:
        from nl_coding_agent.core.tool_invocations import record_invocation
        for action in actions:
            lowered = action.lower()
            if action.startswith("Wrote "):
                tool_name = "write_file"
            elif action.startswith("Patched "):
                tool_name = "patch_file"
            else:
                tool_name = "text_action"
            status = "failed" if ("rejected" in lowered or lowered.startswith("failed")) else "completed"
            record_invocation(
                tool_name, result=action, status=status, source="fallback",
                project_id=project_id, mission_id=mission_id,
                role=role, model=model,
            )
    except Exception:
        pass
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
        self._last_agent_result = None
        self._route_selections: dict[str, dict] = {}
        self._ledger_mission_id: int | None = None

    # ------------------------------------------------------------------ helpers

    def _agent_metadata(self, model_name: str, role: str = "developer") -> dict:
        """Actual CrewAI result evidence for the last call, bounded and JSON-safe."""
        result = self._last_agent_result
        metadata = {"model": str(model_name or ""), "provider": "ollama"}
        if result is not None:
            metadata.update({
                "model": str(getattr(result, "model", None) or model_name or ""),
                "provider": str(getattr(result, "provider", None) or "ollama"),
                "duration_s": getattr(result, "duration_s", None),
                "tools_used": list(getattr(result, "tools_used", ()) or ()),
                "available_tools": list(getattr(result, "available_tools", ()) or ()),
                "tool_invocations": [dict(item) for item in
                                     (getattr(result, "tool_invocations", ()) or ())],
            })
            usage = getattr(result, "usage", None)
            if usage:
                try:
                    metadata["usage"] = dict(usage)
                except Exception:
                    pass
        try:
            from nl_coding_agent.models.generation_params import effective_params
            params = effective_params(model_name=model_name, role=role)
            metadata["generation_params"] = {
                key: value for key, value in params.items() if key != "num_ctx"
            }
        except Exception:
            metadata["generation_params"] = {}
        try:
            from nl_coding_agent.models.ollama_registry import loaded_model_context
            metadata["effective_context"] = loaded_model_context(
                str(model_name).split("/", 1)[-1])
        except Exception:
            metadata["effective_context"] = None
        return metadata

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

    def _resolve_route(self, role: str, requested: str | None, *,
                       required_capabilities=(), max_cost_usd: float | None = None) -> str:
        """Resolve an explicit route, or an explicitly requested ``auto`` route."""
        route = str(requested or "").strip()
        if route.lower() not in ("auto", "automatic"):
            return route
        try:
            from nl_coding_agent.models.model_router import ModelRouter, RouteRefused
            from nl_coding_agent.models.ollama_registry import list_models
            from nl_coding_agent.models.capabilities import capability_set_for
            models = list_models()
            candidates = [{"provider_id": "ollama", "model_name": item.name}
                          for item in models if getattr(item, "name", "")]
            if not candidates:
                raise RouteRefused("Automatic routing requires at least one available local model")
            # Measure a bounded set only when the capability ledger has no
            # measured evidence yet. The probe persists results, so later
            # missions reuse them instead of calling the model again.
            role_required = tuple(required_capabilities or (
                ("tool_calling", "structured_output")
                if role in ("developer", "debugger") else
                ("structured_output",) if role == "reviewer" else ()
            ))
            measured = any(
                capability_set_for("ollama", item["model_name"]).supports("tool_calling")
                for item in candidates
            )
            if not measured:
                try:
                    from nl_coding_agent.models.operational_probes import (
                        probe_available_models,
                    )
                    probe_available_models(limit=3)
                    self._emit(
                        "model_router", "info",
                        "Measured operational capabilities for automatic routing "
                        "(bounded Ollama probe).",
                        mission_id=None,
                    )
                except Exception as probe_exc:
                    self._emit(
                        "model_router", "warning",
                        "Capability probe unavailable; automatic routing will use "
                        "existing evidence only: " + type(probe_exc).__name__,
                        mission_id=None,
                    )
            prefer = ("tool_calling", "structured_output", "patch_quality") if role in (
                "developer", "debugger") else ("structured_output", "tool_calling")
            router = ModelRouter(project_id=self.project_id)
            binding = router.auto_select(
                role, candidates, required_capabilities=role_required,
                prefer_capabilities=prefer,
                project_id=self.project_id, max_cost_usd=max_cost_usd,
            )
            resolved = f"{binding.provider_id}/{binding.model_name}"
            self._route_selections[role] = dict(binding.selection)
            self._emit(
                "model_router", "info",
                f"Automatic model for {role}: {resolved} (score {binding.selection.get('score')})",
                mission_id=None,
                selection=dict(binding.selection),
            )
            return resolved
        except Exception as exc:  # fail closed: never silently choose a different model
            raise GateFailure(
                f"Automatic model selection failed for {role}: {type(exc).__name__}: {exc}",
                code="model-selection-failed",
            ) from exc

    def _take_steering(self, mission_id: int) -> str:
        """Consume a queued user steering instruction at the next stage prompt."""
        try:
            key = "mission.steer." + str(int(mission_id))
            text = get_setting(key, "") or ""
            if text:
                set_setting(key, "")
            return str(text)[:8000]
        except Exception:
            return ""

    @staticmethod
    def _textual_tool_request(output: str) -> dict | None:
        """Recover a tool request emitted as JSON text by a non-native model."""
        text = str(output or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        if isinstance(parsed.get("tool_calls"), list) and parsed["tool_calls"]:
            first = parsed["tool_calls"][0]
            return first if isinstance(first, dict) else None
        if isinstance(parsed.get("name"), str) and isinstance(parsed.get("arguments", {}), dict):
            return {"name": parsed["name"], "arguments": parsed.get("arguments") or {}}
        return None

    def _execute_textual_tool(self, workspace: Path, request: dict) -> str:
        """Execute only read-only/textual tools requested as text; write tools are not auto-run."""
        name = str(request.get("name") or "")
        args = request.get("arguments") if isinstance(request.get("arguments"), dict) else {}
        from nl_coding_agent.tools.filesystem import scoped_list_dir, scoped_read_file
        result = ""
        status = "completed"
        try:
            if name in ("read_file", "read_source"):
                result = scoped_read_file(workspace, str(args.get("path") or ""))[:12000]
            elif name in ("list_dir", "list_source"):
                entries = scoped_list_dir(workspace, str(args.get("path") or "."))
                result = "\n".join(entries)[:8000]
            elif name == "run_tests":
                from nl_coding_agent.tools.verification import detect_test_command
                from nl_coding_agent.tools.shell import scoped_run_command
                run = scoped_run_command(workspace, detect_test_command(workspace), timeout=120)
                result = (f"exit={run.get('returncode')}\n{run.get('stdout') or ''}\n"
                          f"{run.get('stderr') or ''}")[:12000]
            elif name == "git_status":
                from nl_coding_agent.tools.git_tools import get_git_status
                result = get_git_status(workspace)[:8000]
            elif name == "git_diff":
                from nl_coding_agent.tools.git_tools import get_git_diff
                result = get_git_diff(workspace)[:12000]
            else:
                result = "tool is not available for textual replay: " + name
                status = "denied"
        except Exception as exc:
            result = "tool error: " + type(exc).__name__ + ": " + str(exc)
            status = "failed"
        try:
            from nl_coding_agent.core.tool_invocations import record_invocation
            record_invocation(
                name, arguments=args, result=result, status=status,
                source="fallback", project_id=self.project_id,
                mission_id=getattr(self, "_ledger_mission_id", None),
                call_id=str(request.get("id") or "") or None,
            )
        except Exception:
            pass
        return result

    def _call_model_with_textual_tools(self, role: str, model_name: str, prompt: str, *,
                                       workspace: Path, goal: str, backstory: str,
                                       expected_output: str, tools: list | None,
                                       max_rounds: int = 2) -> str:
        """Run a bounded read-tool loop for models that emit JSON tool text instead of native calls."""
        current_prompt = prompt
        output = ""
        for round_index in range(max_rounds + 1):
            output = self._call_model(
                role, model_name, current_prompt, goal=goal, backstory=backstory,
                expected_output=expected_output,
                tools=tools if round_index == 0 else None,
            )
            request = self._textual_tool_request(output)
            if not request or round_index >= max_rounds:
                break
            result = self._execute_textual_tool(workspace, request)
            current_prompt = (
                prompt
                + "\n\nTOOL RESULT FOR " + str(request.get("name")) + ":\n"
                + _truncate(result, 12000)
                + "\n\nDo not request more read-only tools. Now produce the actual code changes "
                  "using patch_file or a ```write:path``` block. Do not return a tool request or a plan."
            )
        return output

    def _record_model_assignments(self, mission_id: int, routes: dict[str, str]) -> None:
        """Resolve role routes through the existing ModelRouter and persist the snapshot.

        The exact routes chosen by the caller remain the execution routes (no silent
        substitution); the router validates permissions and stores immutable bindings
        for later results-based model selection.
        """
        try:
            from nl_coding_agent.models.model_router import ModelRouter

            overrides: dict[str, dict] = {}
            for role, route in routes.items():
                text = str(route or "").strip()
                if not text:
                    continue
                provider, _, model_name = text.partition("/")
                if not model_name:
                    provider, model_name = "ollama", text
                overrides[role] = {
                    "provider_id": provider or "ollama",
                    "model_name": model_name,
                }
            if not overrides:
                return
            router = ModelRouter(role_bindings=overrides, project_id=self.project_id)
            resolved = {role: router.resolve(role) for role in overrides}
            for role, selection in self._route_selections.items():
                if role in resolved and selection:
                    resolved[role] = dataclasses.replace(
                        resolved[role], source="auto_ranked", selection=selection,
                    )
            router.record_mission_snapshot(mission_id, resolved)
            self._emit(
                "orchestrator", "info",
                "Model assignments recorded: " + ", ".join(
                    f"{role}={binding.model_name}" for role, binding in sorted(resolved.items())
                ),
                mission_id=mission_id,
                model_bindings={role: binding.to_dict() for role, binding in resolved.items()},
            )
        except Exception as exc:  # noqa: BLE001 - assignment evidence must not fake a route
            self._emit(
                "orchestrator", "warning",
                "Model assignment snapshot unavailable: " + type(exc).__name__ + ": " + str(exc),
                mission_id=mission_id,
            )

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
        self._last_agent_result = result
        try:
            from nl_coding_agent.core.tool_invocations import record_many
            record_many(
                [dict(item) for item in (getattr(result, "tool_invocations", ()) or ())],
                project_id=self.project_id,
                mission_id=getattr(self, "_ledger_mission_id", None),
                role=role,
                model=model_name,
                source="native",
            )
        except Exception:
            pass
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

    @staticmethod
    def _needs_architecture_review(goal: str, write_paths: list[str]) -> bool:
        """Proportional team policy: read-only architecture only for broad/multi-file work."""
        source_paths = [str(path) for path in (write_paths or [])
                        if not str(path).replace("\\", "/").lower().startswith("tests/")
                        and not str(path).lower().endswith((".md", ".rst", ".txt"))]
        if len(set(source_paths)) >= 2:
            return True
        lowered = str(goal or "").lower()
        markers = ("refactor", "architecture", "architettura", "design", "progett",
                   "migrate", "migrazione", "multi-file", "multiple modules",
                   "several modules", "system-wide", "across the")
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _needs_audit(goal: str) -> bool:
        lowered = str(goal or "").lower()
        markers = ("audit", "security", "sicurezza", "vulnerab", "dependency",
                   "dipenden", "performance", "prestazion", "risk", "rischio")
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _subtask_clauses(goal: str) -> list[str]:
        """Split an objective into independently reviewable implementation clauses."""
        text = str(goal or "")
        for separator in ("\r\n", "\n", ";"):
            text = text.replace(separator, "\n")
        raw = [line.strip(" \t-*") for line in text.split("\n") if line.strip(" \t-*")]
        clauses: list[str] = []
        for line in raw:
            # Do not split ordinary prose on "and": it creates redundant subtasks.
            clauses.append(line)
        result: list[str] = []
        for clause in clauses:
            if clause and clause not in result:
                result.append(clause)
        return result

    @staticmethod
    def _module_path_for(name: str, known: set[str]) -> str | None:
        candidate = name.replace(".", "/") + ".py"
        if candidate in known:
            return candidate
        return None

    def _order_source_paths_by_imports(self, paths: list[str]) -> list[str]:
        """Topologically order target modules using their real imports (deps first)."""
        import ast

        ordered_input = [str(path).replace("\\", "/") for path in paths]
        known = set(ordered_input)
        dependencies: dict[str, set[str]] = {path: set() for path in ordered_input}
        for path in ordered_input:
            full = self.root / path
            try:
                tree = ast.parse(full.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for module in modules:
                    target = self._module_path_for(module, known)
                    if target and target != path:
                        dependencies[path].add(target)
        ordered: list[str] = []
        remaining = list(ordered_input)
        while remaining:
            ready = [path for path in remaining if not (dependencies[path] - set(ordered))]
            if not ready:
                # Import cycle or unparseable graph: keep the declared deterministic order.
                ready = [remaining[0]]
            ready.sort(key=lambda item: remaining.index(item))
            for path in ready:
                ordered.append(path)
                remaining.remove(path)
        return ordered

    def _existing_project_context(self, workspace: Path, limit: int = 18_000) -> str:
        """Bounded read-only snapshot of the small project for the developer prompt."""
        chunks: list[str] = []
        used = 0
        for candidate in sorted(workspace.rglob("*")):
            if used >= limit:
                break
            if any(part in {".git", "data", ".workspace", "__pycache__", "node_modules"}
                   for part in candidate.parts):
                continue
            if not candidate.is_file() or candidate.suffix not in (".py", ".toml", ".ini", ".cfg"):
                continue
            try:
                body = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            relative = candidate.relative_to(workspace).as_posix()
            snippet = body[: max(1000, min(6000, limit - used))]
            chunks.append(f"--- {relative} ---\n{snippet}")
            used += len(snippet)
        return "\n\n".join(chunks)

    def _plan_tasks(self, mission_id: int, goal: str) -> list[dict]:
        """Proportionally plan analysis, one or more implementation subtasks, test and review.

        The planner is deterministic and auditable: it derives implementation subtasks
        from the declared source paths (one writer per path, chained in dependency
        order), or from explicit clauses when the objective has no path list. This is
        what allows more than one task per role without a second orchestrator.
        """
        write_paths = list(dict.fromkeys(extract_paths(goal)))
        source_paths = [path for path in write_paths
                        if not path.replace("\\", "/").lower().startswith("tests/")
                        and not path.lower().endswith((".md", ".rst", ".txt"))]
        source_paths = self._order_source_paths_by_imports(source_paths)
        test_paths = [path for path in write_paths
                      if path.replace("\\", "/").lower().startswith("tests/")]
        analysis_tasks: list[dict] = []
        if self._needs_architecture_review(goal, write_paths):
            analysis_tasks.append(add_task(
                mission_id,
                "Architecture Analysis",
                "Read-only architectural analysis of the current project for the mission objective; "
                "produce constraints and an implementation outline for the developer.",
                "architect",
                write_paths=[],
            ))
        if self._needs_audit(goal):
            analysis_tasks.append(add_task(
                mission_id,
                "Risk & Test Audit",
                "Read-only audit of security, dependency, compatibility and test risks relevant to the "
                "mission objective; hand constraints to the developer.",
                "auditor",
                depends_on=[analysis_tasks[-1]] if analysis_tasks else [],
                write_paths=[],
            ))

        clauses = self._subtask_clauses(goal)
        units: list[tuple[str, list[str], str]] = []
        if 2 <= len(source_paths) <= 4:
            for index, path in enumerate(source_paths):
                clause = clauses[index % len(clauses)] if clauses else goal
                units.append((
                    f"Implement change in {path}",
                    [path],
                    f"{goal}\n\nSUBTASK {index + 1}/{len(source_paths)} — implement the part of the "
                    f"objective that belongs to `{path}`. Start by reading `{path}` and the modules it "
                    f"depends on. Do not modify any other file.",
                ))
        elif source_paths:
            # A broad path list is one integration-sized change, not dozens of microtasks.
            # One source file may still be split by explicit clauses, capped for safety.
            if len(source_paths) == 1 and 1 < len(clauses) <= 3:
                for index, clause in enumerate(clauses):
                    units.append((
                        f"Implementation part {index + 1}",
                        source_paths,
                        f"{goal}\n\nSUBTASK {index + 1}/{len(clauses)} — focus only on this clause:\n"
                        f"{clause}\nDo not modify any other file.",
                    ))
            else:
                units.append(("Code Implementation", source_paths, goal))
        else:
            units.append(("Code Implementation", write_paths, goal))

        if test_paths:
            units.append((
                "Test updates",
                test_paths,
                f"{goal}\n\nSUBTASK — update only the tests needed for this objective. "
                "Do not modify source files in this subtask.",
            ))

        implementation_tasks: list[int] = []
        previous_id: int | None = analysis_tasks[-1] if analysis_tasks else None
        for title, paths, description in units:
            depends = [previous_id] if previous_id else []
            task_id = add_task(
                mission_id,
                title,
                description,
                "developer",
                depends_on=depends,
                write_paths=paths,
            )
            implementation_tasks.append(task_id)
            previous_id = task_id
        if not implementation_tasks:
            implementation_tasks.append(add_task(
                mission_id, "Code Implementation", goal, "developer",
                depends_on=[analysis_tasks[-1]] if analysis_tasks else [],
                write_paths=write_paths,
            ))

        tester = add_task(
            mission_id,
            "Test & Verification",
            "Run independent candidate/oracle tests against the complete staged change and repair failures",
            "tester",
            depends_on=[implementation_tasks[-1]],
        )
        reviewer = add_task(
            mission_id,
            "Code Review",
            "Review the mission-scoped diff and record APPROVE/REJECT",
            "reviewer",
            depends_on=[tester],
        )
        return get_tasks(mission_id)

    @staticmethod
    def _tasks_for_role(tasks: list[dict], role: str) -> list[dict]:
        return [task for task in tasks if task.get("agent_role") == role]

    @staticmethod
    def _task_order_key(task: dict) -> tuple:
        return (int(task.get("id") or 0),)


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

    def _ensure_stage(self, mission_id: int, dev_task: dict | None, goal: str,
                      *, scope_paths: list[str] | None = None) -> promotion.Stage:
        mission = get_mission(mission_id) or {}
        stored = mission.get("staging_dir")
        if stored:
            stage = promotion.load_stage(stored)
            if stage.project_root != self.root:
                raise GateFailure("Staged candidate belongs to a different project root", code="stage-mismatch")
            return stage
        write_paths = list(scope_paths or (dev_task or {}).get("write_paths") or [])
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
            project_root=self.root,
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
        try:
            from nl_coding_agent.core.failure_evidence import (
                capture_exception,
                record_exception,
                record_running_task_failures,
            )

            payload = capture_exception(
                exc, source="orchestrator", method="_run_locked",
                mission_id=int(mission_id),
            )
            record_exception(
                int(mission_id), exc, source="orchestrator", method="_run_locked",
            )
            record_running_task_failures(
                int(mission_id), exc, source="orchestrator",
                traceback_text=payload.get("traceback") or "",
            )
        except Exception:
            pass
        self._emit("orchestrator", "error", message, mission_id=mission_id)
        record_handoff(mission_id, "orchestrator", "user", message, {"error": str(exc)})
        update_mission_status(mission_id, "failed")
        return self._result_payload(mission_id, status="failed", error=str(exc))

    def _finalize_execution_failed(self, mission_id: int, *, error: str,
                                   code: str = "executor_exception",
                                   stage: promotion.Stage | None = None,
                                   failure_stage: str | None = None,
                                   traceback_text: str = "",
                                   exception_type: str = "") -> dict:
        """Single writer for an unexpected executor/Flow crash.

        The staged candidate and every handoff/attempt remain on disk for resume
        and post-mortem; the live tree is untouched.  This is deliberately a
        terminal `failed` state, not a normal `blocked` policy decision.
        """
        stage_dir = str(stage.stage_dir) if stage is not None else None
        staged_paths: list[str] = []
        if stage is not None:
            try:
                staged_paths = sorted(
                    (promotion.read_manifest(stage).get("changed") or {}).keys()
                )
            except Exception:
                staged_paths = []
        summary = "Mission failed during execution: " + str(error)[:8000]
        update_mission_result(
            mission_id, "failed", result_summary=summary, review_verdict=None,
            diff_stat="", changed_paths=[],
        )
        payload = {
            "status": "failed",
            "code": code,
            "failure_stage": failure_stage,
            "exception_type": exception_type,
            "traceback_sample": (traceback_text or "")[-8000:],
            "staged_paths": staged_paths,
            "stage_dir": stage_dir,
            "live_changes": "none",
        }
        record_handoff(mission_id, "orchestrator", "user", summary, payload)
        try:
            self._emit("orchestrator", "error", summary, mission_id=mission_id)
        except Exception:
            pass
        result = self._result_payload(
            mission_id, status="failed", error=summary,
            promotion_status=None,
        )
        result["code"] = code
        result["failure_stage"] = failure_stage
        result["stage_dir"] = stage_dir
        return result

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
        architect_model: str | None = None,
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
        from nl_coding_agent.core.doc_planning import is_document_plan_request
        if mission.get("status") == "blocked" and is_document_plan_request(mission.get("goal") or ""):
            return self._result_payload(mission_id, status="blocked",
                error=mission.get("result_summary") or "Document planning service required")
        goal = (goal or mission.get("goal") or "").strip()
        if not goal:
            raise ValueError(f"Mission #{mission_id} has no goal")

        developer_model = developer_model or DEFAULT_DEVELOPER_MODEL
        reviewer_model = reviewer_model or DEFAULT_REVIEWER_MODEL
        debug_model = debug_model or DEFAULT_DEBUG_MODEL
        architect_model = architect_model or developer_model

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

        control = control or RunControl()
        try:
            with control.observe_mission_stop(mission_id), mission_lock(mission_id):
                return self._run_locked(
                    mission_id,
                    goal,
                    developer_model,
                    reviewer_model,
                    debug_model,
                    stop_after,
                    control,
                    architect_model,
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
        architect_model: str | None = None,
    ) -> dict:
        mission = get_mission(mission_id) or {}
        self._ledger_mission_id = int(mission_id)
        existing_tasks = get_tasks(mission_id)
        stage: promotion.Stage | None = None
        baseline: dict[str, str] = {}
        architect_model = str(architect_model or developer_model or "")
        try:
            developer_model = self._resolve_route("developer", developer_model)
            reviewer_model = self._resolve_route("reviewer", reviewer_model)
            debug_model = self._resolve_route("debugger", debug_model)
            architect_model = self._resolve_route("architect", architect_model)
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
            planned_roles = {str(task.get("agent_role") or "") for task in tasks}
            assignment_routes = {
                "architect": architect_model,
                "developer": developer_model,
                "reviewer": reviewer_model,
                "debugger": debug_model,
            }
            if "auditor" in planned_roles:
                assignment_routes["auditor"] = developer_model
            self._record_model_assignments(mission_id, assignment_routes)
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
            dev_tasks = self._tasks_for_role(tasks, "developer")
            test_tasks = self._tasks_for_role(tasks, "tester")
            review_tasks = self._tasks_for_role(tasks, "reviewer")
            dev_task = dev_tasks[0] if dev_tasks else None
            test_task = test_tasks[-1] if test_tasks else None
            rev_task = review_tasks[-1] if review_tasks else None

            # Candidate stage: every model write lands inside stage.workspace, never live.
            # The scope is the union of all implementation subtasks, not just the first.
            stage_scope = [path for task in dev_tasks for path in (task.get("write_paths") or [])]
            stage = self._ensure_stage(mission_id, dev_task, goal, scope_paths=stage_scope)
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

            self._checkpoint(control, "before-architect")
            architecture_notes = self._run_planned_analysis(
                mission_id, tasks, goal,
                {"architect": architect_model, "auditor": developer_model},
            )
            self._checkpoint(control, "after-architect")

            self._checkpoint(control, "before-developer")

            # 1. Developer: all planned implementation subtasks, staged candidate only.
            if dev_tasks:
                self._run_developer_tasks(
                    mission_id, tasks, goal, developer_model, baseline, stage,
                    architecture_notes=architecture_notes, control=control,
                )
                if all(task.get("status") == "completed" for task in dev_tasks):
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

    def _analysis_notes(self, mission_id: int, role: str) -> str:
        """Read a persisted analysis handoff so resumed missions reuse completed work."""
        for handoff in reversed(get_handoffs(mission_id)):
            if handoff.get("from_role") == role and handoff.get("to_role") == "developer":
                payload = handoff.get("payload") or {}
                return str(payload.get("notes") or "")
        return ""

    def _architect_notes(self, mission_id: int) -> str:
        return self._analysis_notes(mission_id, "architect")

    def _run_analysis_stage(
        self,
        mission_id: int,
        task_rec: dict,
        goal: str,
        model_name: str,
        *,
        role: str,
        display_role: str,
        purpose: str,
    ) -> str:
        """Shared read-only analysis stage for architect/auditor; hands notes to the developer."""
        task_id = task_rec["id"]
        update_task_status(task_id, "running")
        self._emit(
            role, "info",
            f"{display_role} analysing the project before implementation with {model_name}",
            mission_id=mission_id,
        )
        tools = get_project_tools(self.root, read_only=True)
        prompt = f"""
PROJECT ROOT: {self.root}
MISSION GOAL: {goal}

You are the read-only {display_role} in a multi-agent coding mission.
Inspect only the files needed to understand the existing design, constraints and tests.
Do not modify any file; you have no write tools.

{purpose}

Do not claim that changes were made. The Developer will perform them in a staged candidate.
"""
        try:
            notes = self._call_model(
                display_role,
                model_name,
                prompt,
                goal=f"{display_role} analysis for this mission: {goal}",
                backstory=(
                    f"You are a read-only {display_role}. You inspect the existing project and "
                    "hand precise constraints to the implementation developer. You never edit files."
                ),
                expected_output="Concise analysis notes: files, interfaces, constraints, risks, verification targets.",
                tools=tools,
            )
            metadata = self._agent_metadata(model_name)
            summary = f"{display_role} analysis delivered ({len(notes)} chars)."
            record_task_attempt(task_id, "completed", output=_truncate(notes, 12_000),
                                metadata=metadata)
            update_task_status(task_id, "completed")
            record_handoff(
                mission_id,
                role,
                "developer",
                summary,
                {
                    "role": role,
                    "model": metadata.get("model") or model_name,
                    "notes": _truncate(notes, 8_000),
                    "read_only": True,
                    "agent": metadata,
                },
            )
            self._emit(role, "info", summary, mission_id=mission_id)
            return str(notes or "")
        except Exception as exc:
            record_task_attempt(task_id, "failed", error=_truncate(str(exc), 2000),
                                metadata=self._agent_metadata(model_name))
            update_task_status(task_id, "failed", error=_truncate(str(exc), 2000))
            self._emit(role, "error", f"{display_role} analysis failed: {exc}",
                       mission_id=mission_id)
            raise GateFailure(f"{display_role} analysis failed: " + str(exc),
                              code=role + "-failed") from exc

    def _run_architect_stage(self, mission_id: int, task_rec: dict, goal: str,
                             model_name: str) -> str:
        return self._run_analysis_stage(
            mission_id, task_rec, goal, model_name,
            role="architect", display_role="Software Architect",
            purpose=("Produce concise implementation notes for the Developer: files that must change "
                     "and why; interfaces/tests to preserve; minimal outline and risks; what "
                     "independent verification should prove."),
        )

    def _run_auditor_stage(self, mission_id: int, task_rec: dict, goal: str,
                           model_name: str) -> str:
        return self._run_analysis_stage(
            mission_id, task_rec, goal, model_name,
            role="auditor", display_role="Repository Auditor",
            purpose=("Produce concise risk notes for the Developer: security/dependency/compatibility "
                     "risks, existing tests and interfaces to preserve, and what the independent "
                     "tester/reviewer must verify."),
        )

    def _run_planned_analysis(self, mission_id: int, tasks: list[dict], goal: str,
                              models: dict[str, str]) -> str:
        """Execute every planned read-only analysis task in order and combine its notes."""
        notes: list[str] = []
        for task in tasks:
            role = str(task.get("agent_role") or "")
            if role not in ("architect", "auditor"):
                continue
            if task.get("status") == "completed":
                analysis = self._analysis_notes(mission_id, role)
                self._emit(role, "info", "Analysis recovered from persisted handoff.",
                           mission_id=mission_id)
            elif role == "architect":
                analysis = self._run_architect_stage(
                    mission_id, task, goal, models.get("architect") or models.get("developer") or "")
            elif role == "auditor":
                analysis = self._run_auditor_stage(
                    mission_id, task, goal, models.get("auditor") or models.get("developer") or "")
            else:
                continue
            if str(analysis or "").strip():
                label = "Architecture" if role == "architect" else "Audit"
                notes.append(f"[{label}]\n{analysis.strip()}")
        return "\n\n".join(notes)

    def _developer_task_note(self, mission_id: int, task_id: int) -> str:
        """Read the structured handoff of a completed implementation subtask."""
        for handoff in reversed(get_handoffs(mission_id)):
            payload = handoff.get("payload") or {}
            if handoff.get("from_role") == "developer" and int(payload.get("task_id") or -1) == int(task_id):
                parts = [
                    f"Task #{task_id}: {payload.get('task_title') or ''}".strip(),
                    str(payload.get("decisions") or payload.get("output_sample") or "")[:2500],
                    "Artifacts: " + ", ".join(payload.get("changed_paths") or []),
                ]
                return "\n".join(part for part in parts if part)
        return ""

    def _run_developer_tasks(
        self,
        mission_id: int,
        tasks: list[dict],
        goal: str,
        model_name: str,
        baseline: dict[str, str],
        stage: promotion.Stage,
        *,
        architecture_notes: str = "",
        control: RunControl | None = None,
    ) -> str:
        """Execute every planned implementation subtask in dependency order on one candidate.

        Completed subtasks are skipped on resume; their structured handoff is replayed
        into the next developer prompt. There is intentionally only one implementation
        runtime: each subtask is a scoped call to the same developer stage.
        """
        dev_tasks = sorted(self._tasks_for_role(tasks, "developer"), key=self._task_order_key)
        notes = str(architecture_notes or "")
        for index, task in enumerate(dev_tasks):
            next_target = "tester" if index == len(dev_tasks) - 1 else "developer"
            if task.get("status") == "completed":
                prior = self._developer_task_note(mission_id, int(task["id"]))
                if prior:
                    notes = (notes + "\n\nCOMPLETED SUBTASK\n" + prior).strip()
                continue
            self._checkpoint(control, f"before-developer-{task['id']}")
            task_goal = str(task.get("description") or goal)
            output = self._run_developer_stage(
                mission_id, task, task_goal, model_name, baseline, stage,
                architecture_notes=notes,
                handoff_to=next_target,
                task_index=index,
                task_count=len(dev_tasks),
            )
            note = (
                f"Task #{task['id']} ({task.get('title') or 'implementation'}) completed.\n"
                + _truncate(str(output or ""), 2500)
            )
            notes = (notes + "\n\nCOMPLETED SUBTASK\n" + note).strip()
        return notes

    def _run_developer_stage(
        self,
        mission_id: int,
        task_rec: dict,
        goal: str,
        model_name: str,
        baseline: dict[str, str],
        stage: promotion.Stage,
        *,
        architecture_notes: str = "",
        handoff_to: str = "tester",
        task_index: int = 0,
        task_count: int = 1,
    ) -> str:
        task_id = task_rec["id"]
        write_paths = task_rec.get("write_paths") or list(stage.scope)
        before_files = snapshot_workspace(stage.workspace)
        update_task_status(task_id, "running")
        self._emit(
            "developer", "info",
            f"Developer agent starting subtask {task_index + 1}/{task_count} (#{task_id}) with {model_name}",
            model=model_name,
            write_paths=write_paths,
            stage_dir=str(stage.stage_dir),
        )

        tools = [item for item in get_project_tools(stage.workspace, project_id=self.project_id)
                 if getattr(item, "name", "") not in ("run_command", "run_tests")]
        scope_text = (
            "Declared write scope for THIS subtask (do not modify other files):\n- "
            + "\n- ".join(write_paths)
            if write_paths
            else "No explicit write scope was declared. Stay focused on the goal."
        )
        architecture_text = (
            "PRIOR ARCHITECTURE/AUDIT NOTES AND COMPLETED SUBTASKS (use as guidance; verify against the code):\n"
            + _truncate(architecture_notes, 10_000)
            if str(architecture_notes or "").strip()
            else "PRIOR NOTES: (none yet)"
        )
        steering = self._take_steering(mission_id)
        steering_text = (
            "USER STEERING (highest priority, while preserving verification and scope):\n"
            + steering if steering else ""
        )
        existing_context = self._existing_project_context(stage.workspace)
        tests_context = ""
        try:
            test_files = sorted((stage.workspace / "tests").glob("test_*.py"))
            tests_context = "\n\n".join(
                f"--- {item.relative_to(stage.workspace).as_posix()} ---\n"
                + item.read_text(encoding="utf-8", errors="replace")[:8000]
                for item in test_files[:8]
            )
        except Exception:
            tests_context = ""
        prompt = f"""
PROJECT ROOT: {self.root}
WORKSPACE (staged copy; write relative paths here): {stage.workspace}
MISSION GOAL: {goal}

SUBTASK {task_index + 1}/{task_count}: {task_rec.get('title') or 'implementation'}
{scope_text}

{architecture_text}

{steering_text}

EXISTING PROJECT FILES (read-only snapshot; preserve these interfaces and do not invent a different project):
{existing_context}

ACCEPTANCE TESTS ARE AUTHORITATIVE — do not edit tests; implement exactly the calls and signatures they make:
{tests_context or '(no test files found)'}

INSTRUCTIONS:
1. Read the relevant existing files first, including their imports and dependent modules.
2. Implement the requested change directly in the staged workspace files.
3. The target files already exist. You MUST modify them with patch_file (possibly several patch_file calls) and preserve every existing class/function. Do NOT replace an existing file with write_file and do NOT delete/rename existing public definitions: the validation gate rejects that as a destructive change. write_file is only for genuinely new files, or as the exact ```write:path``` fallback when no patch can express the change.
4. Do NOT edit files outside this subtask's declared write scope: the candidate is rejected if you do.
5. Preserve every existing public function and test unless the objective explicitly asks to remove or rename it. Do not move functions between files.
6. Do NOT output 'diff --git' or unified-diff headers inside a source file.
7. Nothing is live until review and promotion; only the staged copy may change.
8. Real tools are available in the staged workspace: read/list/write/patch, git status/diff, run tests, and a bounded shell allowlist. Use them to inspect and self-check, but never claim a test passed without its output.
9. Do NOT claim success without actually writing the files.
10. Finish with a concise summary of the files changed, decisions made and any open problem.
"""
        base_prompt = prompt
        output = ""
        actions = {}
        verdict: dict = {}
        changed: list[str] = []
        after_files: dict[str, str] = {}
        first_verdict: dict | None = None
        first_changed: list[str] = []
        first_output = ""
        for attempt_index in range(2):
            model_prompt = base_prompt
            if attempt_index:
                model_prompt += (
                    "\n\nPREVIOUS ATTEMPT WAS REJECTED BY THE VALIDATION GATE:\n"
                    + _truncate(validation_feedback, 4000)
                    + "\nThe staged files have been restored to their pre-attempt state. "
                      "Use patch_file to preserve every existing class/function; do not rewrite "
                      "an existing file and do not remove or rename existing definitions."
                )
                retry_files: list[str] = []
                for rel_path in write_paths:
                    target = stage.workspace / str(rel_path)
                    if target.is_file():
                        try:
                            retry_files.append(
                                "--- " + str(rel_path) + " (current exact content) ---\n"
                                + _truncate(target.read_text(encoding="utf-8", errors="replace"), 5000))
                        except OSError:
                            continue
                if retry_files:
                    model_prompt += ("\n\nUse these exact snippets as patch targets; do not invent "
                                     "line positions or duplicate a class that already exists:\n\n"
                                     + "\n\n".join(retry_files))
            try:
                output = self._call_model_with_textual_tools(
                    "Implementation Developer", model_name, model_prompt,
                    workspace=stage.workspace,
                    goal=f"Implement the requested code change in the staged candidate: {goal}",
                    backstory=(
                        "You are an expert autonomous software engineer. You inspect existing code "
                        "using read_file or list_dir, and you write precise patches using patch_file. "
                        "You must produce real file changes in the staged workspace, not only a plan, "
                        "and you must preserve every existing public function and class."
                    ),
                    expected_output="Summary of files actually modified in the staged workspace and the changes made.",
                    tools=tools,
                )
            except Exception:
                # A fake/constrained model may not provide a second response. The
                # first validation verdict is still authoritative and blocked.
                if first_verdict is not None:
                    verdict = first_verdict
                    changed = list(first_changed)
                    # Preserve the rejected candidate for diagnosis instead of
                    # leaving only the restored baseline.
                    if first_output:
                        _apply_text_actions(
                            stage.workspace, first_output,
                            project_id=self.project_id, mission_id=mission_id,
                            role="developer", model=model_name,
                        )
                        promotion.normalize_staged_newlines(stage)
                    output = first_output
                    break
                raise
            actions = _apply_text_actions(
                stage.workspace, output,
                project_id=self.project_id, mission_id=mission_id,
                role="developer", model=model_name,
            )
            promotion.normalize_staged_newlines(stage)
            after_files = snapshot_workspace(stage.workspace)
            allowed = {str(path).replace("\\", "/") for path in write_paths}
            unauthorized = [
                path for path in set(before_files) | set(after_files)
                if before_files.get(path) != after_files.get(path)
                and allowed and path.replace("\\", "/") not in allowed
            ]
            if unauthorized:
                # Revert this subtask's out-of-scope edits instead of corrupting the work
                # of a previous developer stage. The task only owns its declared paths.
                for path in unauthorized:
                    target = stage.workspace / path
                    if path in before_files:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(before_files[path], encoding="utf-8")
                    else:
                        target.unlink(missing_ok=True)
                self._emit(
                    "developer", "warning",
                    "Reverted out-of-scope subtask edits: " + ", ".join(sorted(unauthorized)),
                    mission_id=mission_id, task_id=task_id,
                )
                promotion.normalize_staged_newlines(stage)
            verdict = self._validate_stage(stage)
            diff, changed, _stat = promotion.candidate_diff(stage)
            if changed and verdict["valid"]:
                break
            validation_feedback = (
                "; ".join(verdict.get("errors") or [])
                or "No file change was produced."
            )
            if attempt_index == 0:
                first_verdict = dict(verdict)
                first_changed = list(changed)
                first_output = str(output or "")                # A destructive rewrite is not retried against the corrupted file:
                # restore the exact pre-attempt snapshot and give the model one
                # bounded corrective attempt with the actual gate feedback.
                for path in set(before_files) | set(after_files):
                    target = stage.workspace / path
                    if path in before_files:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(before_files[path], encoding="utf-8")
                    else:
                        target.unlink(missing_ok=True)
                promotion.normalize_staged_newlines(stage)
                self._emit(
                    "developer", "warning",
                    "Developer attempt rejected; retrying once with validation feedback: "
                    + validation_feedback[:1000],
                    mission_id=mission_id, task_id=task_id,
                )
        diff, changed, _stat = promotion.candidate_diff(stage)
        if not changed and first_changed:
            changed = list(first_changed)
        metadata = self._agent_metadata(model_name)
        metadata.update({
            "task_id": task_id,
            "subtask": task_rec.get("title"),
            "subtask_index": task_index,
            "subtask_count": task_count,
            "handoff_to": handoff_to,
        })
        # The no-change check runs before the invalid-verdict branch: validate() reports an
        # empty candidate as invalid, which would otherwise mask DeveloperNoChangeError.
        if not changed:
            error_msg = (
                "Developer produced no workspace change. "
                f"Actions parsed: {actions or 'none'}. The model output did not modify files."
            )
            record_task_attempt(task_id, "failed", output=_truncate(output), error=_truncate(error_msg, 2000),
                                metadata=metadata)
            update_task_status(task_id, "failed", error=_truncate(error_msg, 2000))
            raise DeveloperNoChangeError(error_msg)
        if not verdict["valid"]:
            error_msg = "; ".join(verdict["errors"])
            record_task_attempt(task_id, "failed", output=_truncate(output), error=_truncate(error_msg, 2000),
                                metadata=metadata)
            update_task_status(task_id, "failed", error=_truncate(error_msg, 2000))
            raise GateFailure(
                "Staged candidate rejected by the validation gate: " + error_msg,
                code="candidate-rejected",
                details={"errors": verdict["errors"]},
            )
        record_task_attempt(task_id, "completed", output=_truncate(output), metadata=metadata)
        update_task_status(task_id, "completed")
        summary = (
            f"Developer subtask #{task_id} staged {len(changed)} file(s): {', '.join(changed)}. "
            f"Actions: {len(actions)}."
        )
        open_issues = []
        lower_output = str(output or "").lower()
        for marker in ("could not", "unable to", "todo", "remaining", "non riesco", "da fare"):
            if marker in lower_output:
                open_issues.append(marker)
        record_handoff(
            mission_id=mission_id,
            from_role="developer",
            to_role=handoff_to,
            summary=summary,
            payload={
                "model": model_name,
                "task_id": task_id,
                "task_title": task_rec.get("title"),
                "subtask_goal": _truncate(goal, 3000),
                "changed_paths": changed,
                "actions": actions,
                "artifact": {
                    "changed_paths": changed,
                    "diff_sample": _truncate(diff, 4000),
                },
                "decisions": _truncate(output, 1500),
                "open_issues": open_issues,
                "next_steps": (
                    "Continue with the next implementation subtask."
                    if handoff_to == "developer"
                    else "Independent candidate/oracle verification, then review."
                ),
                "diff_sample": _truncate(diff, 4000),
                "output_sample": _truncate(output, 1500),
                "agent": metadata,
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
        *,
        defer_repairs: bool = False,
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
                if defer_repairs:
                    record_handoff(
                        mission_id=mission_id,
                        from_role="tester",
                        to_role="debugger",
                        summary="Candidate validation failed; Flow routes to repair.",
                        payload={"error": _truncate(errors, 4000),
                                 "write_paths": write_paths,
                                 "deferred_repair": True},
                    )
                    record_task_attempt(task_id, "failed", error=_truncate(errors, 4000),
                                        metadata={"deferred_repair": True})
                    return {"needs_repair": True, "error": errors,
                            "write_paths": write_paths}
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
            error_msg = (
                f"Verification failed (attempt {attempt + 1}): {report.error}\n"
                f"CANDIDATE:\n{report.candidate.stdout_tail[-4000:]}\n{report.candidate.stderr_tail[-4000:]}\n"
                f"ORACLE:\n{report.oracle.stdout_tail[-4000:]}\n{report.oracle.stderr_tail[-4000:]}"
            )
            if defer_repairs:
                record_handoff(
                    mission_id=mission_id,
                    from_role="tester",
                    to_role="debugger",
                    summary="Verification failed; Flow routes to repair.",
                    payload={"error": _truncate(error_msg, 4000),
                             "write_paths": write_paths,
                             "deferred_repair": True},
                )
                record_task_attempt(task_id, "failed", error=_truncate(error_msg, 4000),
                                    metadata={"deferred_repair": True})
                return {"needs_repair": True, "error": error_msg,
                        "write_paths": write_paths}
            if attempt >= max_attempts:
                break
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
        from nl_coding_agent.core.code_integrity_gate import detect_stub

        before_debug = snapshot_workspace(stage.workspace)
        tools = [item for item in get_project_tools(stage.workspace, project_id=self.project_id)
                 if getattr(item, "name", "") not in ("read_file", "list_dir")]
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
5. Real tools are available: file read/write/patch, git status/diff, run tests and a bounded shell allowlist. Use them to diagnose the real failure.
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
        actions = _apply_text_actions(
            stage.workspace, output,
            project_id=self.project_id, mission_id=mission_id,
            role="debugger", model=model_name,
        )
        promotion.normalize_staged_newlines(stage)
        after_debug = snapshot_workspace(stage.workspace)
        reverted: list[str] = []
        for path in set(before_debug) | set(after_debug):
            before_text = before_debug.get(path)
            after_text = after_debug.get(path)
            if before_text == after_text:
                continue
            # A repair must not delete existing definitions or replace a real module
            # with an empty/stub file. For new-feature files the stage baseline is
            # empty, so the pre-repair candidate is the correct comparison point.
            if after_text is None or detect_stub(after_text, before_text):
                target = stage.workspace / path
                if before_text is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(before_text, encoding="utf-8")
                else:
                    target.unlink(missing_ok=True)
                reverted.append(path)
        if reverted:
            promotion.normalize_staged_newlines(stage)
            self._emit("debugger", "warning",
                       "Reverted destructive debugger edits: " + ", ".join(sorted(reverted)),
                       mission_id=mission_id)
        diff, changed, _stat = promotion.candidate_diff(stage)
        metadata = self._agent_metadata(model_name, "debugger")
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
                "agent": metadata,
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
        mission = get_mission(mission_id) or {}
        objective = str(mission.get("goal") or "(missing persisted objective)")
        steering = self._take_steering(mission_id)
        steering_text = (
            "\nUSER STEERING TO CONSIDER DURING REVIEW:\n" + steering
            if steering else ""
        )
        self._emit(
            "reviewer", "info",
            f"Reviewer inspecting the staged candidate ({stat}) on task #{task_id}",
            mission_id=mission_id,
        )
        prompt = f"""
PROJECT ROOT: {self.root}
CANDIDATE STAGE: {stage.stage_dir}
CANDIDATE CHANGED FILES: {', '.join(changed) or '(none)'}

PERSISTED MISSION OBJECTIVE:
{objective}

{steering_text}

AUTHORIZED CANDIDATE WRITE SCOPE:
{json.dumps(list(stage.scope), ensure_ascii=False)}

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
4. Assess the diff against the persisted mission objective and authorized write scope above. Base every claim on that objective, scope, diff, changed-file list, validation result and verification runs. Do not invent imports, files, or failures that are not present in that evidence.
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
            metadata = self._agent_metadata(model_name, "reviewer")
            record_task_attempt(task_id, "completed", output=_truncate(review_text),
                                metadata=metadata)
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
                    "agent": metadata,
                },
            )
            self._save_promotion_status(mission_id, "reviewed" if verdict == "APPROVE" else "review_rejected")
            self._emit("reviewer", "info", summary, mission_id=mission_id, verdict=verdict)
            return review_text, verdict
        except Exception as exc:
            record_task_attempt(task_id, "failed", error=str(exc),
                                metadata=self._agent_metadata(model_name, "reviewer"))
            update_task_status(task_id, "failed", error=str(exc))
            self._emit("reviewer", "error", f"Review failed: {exc}", mission_id=mission_id)
            raise

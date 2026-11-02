"""Isolated sub-agents with structured handoffs (P3).

A sub-agent runs with its own prompt and its own context: it never sees the parent
transcript, never receives write tools by default and never shares the parent's
message list. It returns a structured handoff that the caller (Supervisor,
orchestrator or Chat) can persist and consume. This is the runtime primitive used by
dynamic project advisors and by explicit delegation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from nl_coding_agent.agents.specs import AgentSpec, get_role
from nl_coding_agent.tools.crew_tools import get_project_tools

HANDOFF_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
MAX_CONTEXT_CHARS = 24_000
MAX_OUTPUT_CHARS = 12_000


@dataclass
class SubagentResult:
    name: str
    role_id: str
    model: str
    output: str
    handoff: dict = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    duration_s: float | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "role_id": self.role_id, "model": self.model,
                "output": self.output[:MAX_OUTPUT_CHARS], "handoff": self.handoff,
                "tools": list(self.tools), "duration_s": self.duration_s}


def _parse_handoff(text: str, *, name: str) -> dict:
    """Accept a structured JSON handoff or degrade to a bounded text handoff."""
    for block in HANDOFF_JSON_RE.findall(str(text or "")):
        try:
            parsed = json.loads(block)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return {
                "summary": str(parsed.get("summary") or "")[:2000],
                "facts": [str(item)[:600] for item in (parsed.get("facts") or [])][:20],
                "decisions": [str(item)[:600] for item in (parsed.get("decisions") or [])][:20],
                "risks": [str(item)[:600] for item in (parsed.get("risks") or [])][:20],
                "next_steps": [str(item)[:600] for item in (parsed.get("next_steps") or [])][:20],
            }
    return {"summary": str(text or "")[:2000], "facts": [], "decisions": [],
            "risks": [], "next_steps": []}


class SubagentRunner:
    """Runs one isolated read-only sub-agent through the existing CrewRuntime seam."""

    def __init__(self, project_root: str | Path, project_id: int | None,
                 crew_runtime, *, read_only: bool = True):
        self.root = Path(project_root).resolve()
        self.project_id = int(project_id) if project_id is not None else None
        self.runtime = crew_runtime
        self.read_only = bool(read_only)

    def _tools(self, allowed=None, read_only: bool = True) -> list:
        tools = get_project_tools(self.root, read_only=read_only or self.read_only,
                                  project_id=self.project_id)
        if allowed:
            allowed_set = {str(item) for item in allowed}
            tools = [tool for tool in tools
                     if str(getattr(tool, "name", "")) in allowed_set]
        return tools

    def run(self, *, name: str, objective: str, context: str = "",
            model: str = "", role_id: str = "advisor", instructions: str = "",
            allowed_tools=None, read_only: bool = True) -> SubagentResult:
        try:
            spec: AgentSpec = get_role(role_id)
        except Exception:
            spec = get_role("advisor")
        tools = self._tools(allowed_tools, read_only=read_only)
        prompt = (
            "INDEPENDENT SUB-AGENT CONTEXT (your own; the parent transcript is not "
            "available and must not be assumed):\n" + str(context or "")[:MAX_CONTEXT_CHARS]
            + "\n\nOBJECTIVE:\n" + str(objective or "")[:4_000]
            + "\n\nReturn a concise analysis and finish with one fenced JSON handoff: "
              '{"summary": "...", "facts": [...], "decisions": [...], "risks": [...], '
              '"next_steps": [...]}. Never modify files; you have read-only tools only.'
        )
        backstory = (
            "You are an isolated read-only sub-agent. You cannot see the parent "
            "conversation, cannot write files and cannot change permissions. Your only "
            "output is an evidence-based analysis plus a structured handoff."
        )
        if instructions:
            backstory += "\n\nSpecialist instructions:\n" + str(instructions)[:4000]
        result = self.runtime.run_agent(
            spec, prompt, goal=str(objective or "")[:2_000],
            backstory=backstory, model_name=model or "", expected_output="Structured handoff.",
            tools=tools, project_id=self.project_id,
        )
        text = str(getattr(result, "text", "") or "")
        handoff = _parse_handoff(text, name=str(name or spec.display_role))
        return SubagentResult(
            name=str(name or spec.display_role),
            role_id=spec.role_id,
            model=str(getattr(result, "model", None) or model or ""),
            output=text[:MAX_OUTPUT_CHARS],
            handoff=handoff,
            tools=[str(getattr(tool, "name", "")) for tool in tools],
            duration_s=getattr(result, "duration_s", None),
        )


def delegated_task(name: str, objective: str, context: str = "", *,
                   role_id: str = "advisor", model: str = "",
                   instructions: str = "", allowed_tools=None) -> dict:
    """Describe a delegation without running it (used by Supervisor/team planning)."""
    return {"name": name, "objective": objective, "context": context,
            "role_id": role_id, "model": model, "instructions": instructions,
            "allowed_tools": list(allowed_tools or [])}


__all__ = ["SubagentResult", "SubagentRunner", "delegated_task", "_parse_handoff"]

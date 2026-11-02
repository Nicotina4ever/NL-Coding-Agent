"""Context Engine facade shared by Chat and mission agents (P1).

One place decides what each model call receives and what is recovered from the
project: the model's real window (see ``context.window``), the persisted project
profile, goal-based file retrieval and durable cross-mission memory. The budget is
dynamic and never a cost or iteration limit; Chat turns degrade with an incremental
digest instead of failing, and a ``MissionContextPack`` lets several agents share
the same recovered information without duplicating the whole context.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from nl_coding_agent.context import memory as project_memory
from nl_coding_agent.context.budget import (
    DEFAULT_CHARS_PER_TOKEN,
    DEFAULT_PROMPT_TOKENS,
    ChatBudget,
    compact_chat,
    estimate_tokens,
)
from nl_coding_agent.context.profile import (
    ProjectProfile,
    build_profile,
    ensure_profile,
    load_profile,
    mentioned_paths,
    mission_context_text,
    profile_summary_text,
    save_profile,
    select_relevant_files,
)
from nl_coding_agent.context.window import (
    ContextLimits,
    calibrate,
    calibration_ratio,
    limits_for,
    model_window,
)
from nl_coding_agent.persistence.database import init_db

__all__ = [
    "ChatBudget", "ContextEngine", "ContextLimits", "MissionContext",
    "MissionContextPack", "ProjectProfile", "budget", "estimate_tokens",
    "memory", "profile", "window",
]


def _path_related(candidate: str, spelled: list[str]) -> bool:
    """True when a memory path and an objective path denote the same file."""
    candidate = candidate.replace("\\", "/").lstrip("./").lower()
    for path in spelled:
        path = path.replace("\\", "/").lstrip("./").lower()
        if candidate == path or candidate.endswith("/" + path) or path.endswith("/" + candidate):
            return True
    return False


@dataclass
class MissionContextPack:
    """Recovered mission context shared by every agent stage of one mission.

    Built once per mission; each role receives only the slice it needs, so agents
    share facts without each of them re-reading the repository or duplicating the
    whole prompt.
    """

    goal: str = ""
    profile_text: str = ""
    files: list[dict] = field(default_factory=list)
    memory_entries: list[dict] = field(default_factory=list)
    memory_text: str = ""

    def file_paths(self) -> list[str]:
        return [str(item.get("path") or "") for item in self.files if item.get("path")]

    def for_role(self, role: str, *, budget_chars: int = 8_000) -> str:
        """Role-specific view of the same pack (no duplicated whole context)."""
        role = str(role or "developer").lower().replace("-", "_")
        parts: list[str] = []
        if role in ("architect", "auditor"):
            if self.profile_text:
                parts.append(self.profile_text)
            paths = self.file_paths()
            if paths:
                parts.append("FILES selectable for this mission: " + ", ".join(paths[:12]))
            if self.memory_text:
                parts.append(self.memory_text)
        elif role == "reviewer":
            if self.memory_text:
                parts.append(self.memory_text)
            if self.files:
                parts.append("CHANGED-AREA FILES under review: " + ", ".join(self.file_paths()[:12]))
        else:  # developer / debugger
            if self.profile_text:
                parts.append(self.profile_text)
            for item in self.files:
                parts.append("--- " + str(item.get("path")) + " (match: "
                             + str(item.get("reason") or "") + ") ---\n"
                             + str(item.get("excerpt") or ""))
            if self.memory_text:
                parts.append(self.memory_text)
        text = "\n\n".join(part for part in parts if part)
        if len(text) > budget_chars:
            text = text[:budget_chars] + "\n... [role context truncated]"
        return text

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "files": [
                {key: item.get(key) for key in ("path", "reason", "score")}
                for item in self.files
            ],
            "memory_entries": len(self.memory_entries),
            "profile": bool(self.profile_text),
            "estimated_tokens": estimate_tokens(
                self.profile_text + self.memory_text
                + "".join(str(item.get("excerpt") or "") for item in self.files)),
        }


@dataclass
class MissionContext:
    """Recovered context for one mission prompt, with its provenance."""

    text: str = ""
    files: list[dict] = field(default_factory=list)
    profile: ProjectProfile | None = None
    memory_text: str = ""
    memory_entries: int = 0
    estimated_tokens: int = 0
    pack: MissionContextPack | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "files": [
                {key: item.get(key) for key in ("path", "reason", "score")}
                for item in self.files
            ],
            "profile": bool(self.profile),
            "memory_entries": self.memory_entries,
            "estimated_tokens": self.estimated_tokens,
        }


class ContextEngine:
    """Project-scoped context builder; all methods are read-only except summaries."""

    def __init__(self, project_id: int | None = None, root: str | Path | None = None):
        self.project_id = int(project_id) if project_id is not None else None
        self.root = Path(root).resolve() if root is not None else None

    # -------------------------------------------------------------- profile

    def profile(self, *, refresh: bool = False) -> ProjectProfile | None:
        if self.root is None:
            return None
        if self.project_id is None:
            return build_profile(self.root)
        if refresh:
            profile = build_profile(self.root, project_id=self.project_id)
            save_profile(self.project_id, profile)
            return profile
        return ensure_profile(self.project_id, self.root)

    def profile_text(self, *, max_chars: int = 2_500) -> str:
        profile = self.profile()
        return profile_summary_text(profile, max_chars=max_chars) if profile else ""

    # -------------------------------------------------------------- memory

    def memory_text(self, query: str = "", *, limit: int = 6) -> str:
        return project_memory.recall_text(self.project_id, query, limit=limit)

    def remember(self, kind: str, text: str, *, mission_id: int | None = None,
                 tags=(), confidence: float = 0.5) -> dict | None:
        return project_memory.record(self.project_id, kind, text, mission_id=mission_id,
                                     tags=tags, confidence=confidence)

    def remember_mission(self, mission_id: int) -> list[dict]:
        return project_memory.attach_mission_outcome(mission_id)

    @staticmethod
    def _relevant_memories(entries: list[dict], goal: str) -> list[dict]:
        """Drop lessons about unrelated files when the objective names its target."""
        spelled = [path.lower() for path in mentioned_paths(goal)]
        if not spelled:
            return entries
        kept: list[dict] = []
        for entry in entries:
            entry_paths = [path.lower() for path in mentioned_paths(entry.get("text", ""))]
            if not entry_paths or any(_path_related(candidate, spelled)
                                      for candidate in entry_paths):
                kept.append(entry)
        return kept

    # -------------------------------------------------------------- mission

    def build_mission_pack(self, goal: str, *, budget_chars: int = 16_000,
                           root_override: str | Path | None = None,
                           memory_limit: int = 6) -> MissionContextPack:
        """Recover shared mission context once, for every agent stage."""
        profile = self.profile()
        read_root = (Path(root_override).resolve() if root_override is not None
                     else self.root)
        profile_text = profile_summary_text(profile) if profile else ""
        files: list[dict] = []
        if read_root is not None:
            _, files = mission_context_text(
                read_root, goal, profile,
                budget_chars=max(2_000, budget_chars - min(6_000, len(profile_text))))
        memories = project_memory.recall(self.project_id, goal,
                                         limit=max(12, memory_limit * 2))
        memories = self._relevant_memories(memories, goal)[:memory_limit]
        return MissionContextPack(
            goal=str(goal or ""),
            profile_text=profile_text,
            files=files,
            memory_entries=memories,
            memory_text=self._format_memories(memories),
        )

    @staticmethod
    def _format_memories(entries: list[dict]) -> str:
        if not entries:
            return ""
        lines = ["PROJECT MEMORY (persisted from earlier missions; verify before relying on it):"]
        for entry in entries:
            lines.append("- [" + str(entry.get("kind") or "note") + "] "
                         + str(entry.get("text") or "")
                         + ((" (mission #" + str(entry.get("mission_id")) + ")")
                            if entry.get("mission_id") else ""))
        return "\n".join(lines)

    def mission_context(self, goal: str, *, budget_chars: int = 16_000,
                        memory_limit: int = 6,
                        root_override: str | Path | None = None) -> MissionContext:
        pack = self.build_mission_pack(goal, budget_chars=budget_chars,
                                       root_override=root_override,
                                       memory_limit=memory_limit)
        text = pack.for_role("developer", budget_chars=budget_chars)
        return MissionContext(text=text, files=pack.files, profile=self.profile(),
                              memory_text=pack.memory_text,
                              memory_entries=len(pack.memory_entries),
                              estimated_tokens=estimate_tokens(text), pack=pack)

    # ---------------------------------------------------------------- chat

    def resolve_limits(self, provider_id: str = "ollama", model_name: str = "",
                       *, base_url: str = "") -> ContextLimits:
        return limits_for(provider_id, model_name, base_url=base_url)

    def chat_turn(self, messages, tools=None, *, session_id: str = "",
                  project_id: int | None = None,
                  limits: ContextLimits | None = None,
                  provider_id: str | None = None, model_name: str | None = None,
                  max_tokens: int | None = None,
                  max_chars: int | None = None,
                  tool_token_budget: int | None = None) -> ChatBudget:
        if limits is not None:
            max_tokens = max_tokens or limits.prompt_tokens
            ratio = limits.chars_per_token
        else:
            ratio = calibration_ratio(provider_id or "ollama", model_name or "") \
                if (provider_id or model_name) else None
            ratio = ratio or DEFAULT_CHARS_PER_TOKEN
            if max_tokens is None and max_chars is None:
                if provider_id or model_name:
                    dynamic = self.resolve_limits(provider_id or "ollama",
                                                  model_name or "")
                    max_tokens = dynamic.prompt_tokens
                    ratio = dynamic.chars_per_token
                else:
                    max_tokens = DEFAULT_PROMPT_TOKENS
        target = project_id if project_id is not None else self.project_id
        previous = self.latest_summary(session_id) if target is not None else None
        previous_summary = str((previous or {}).get("summary") or "")
        previous_covered = int((previous or {}).get("covered_count") or 0)
        result = compact_chat(
            messages, tools, max_tokens=max_tokens, max_chars=max_chars,
            chars_per_token=ratio, tool_token_budget=tool_token_budget,
            previous_summary=previous_summary, previous_covered=previous_covered)
        if result.degraded and target is not None:
            if previous_summary and result.summarized_messages <= 0:
                # Nothing new was folded: keep the existing digest (no duplicate rows).
                return result
            record = result.summary or (
                "Context compacted without dropping turns: "
                + (", ".join(result.trimmed) or "size-only trim")
                + " (" + str(result.chars) + " chars, ~"
                + str(result.estimated_tokens) + " tokens)")
            try:
                self.persist_summary(target, session_id, record,
                                     result.summarized_messages,
                                     digest=result.digest,
                                     covered_count=result.covered_messages)
            except Exception:
                pass
        return result

    def persist_summary(self, project_id: int | None, session_id: str,
                        summary: str, message_count: int = 0,
                        scope: str = "chat", digest: dict | None = None,
                        covered_count: int | None = None) -> bool:
        if not summary:
            return False
        digest_json = json.dumps(digest or {}, ensure_ascii=False, sort_keys=True)
        covered = int(covered_count if covered_count is not None else message_count)
        conn = init_db()
        try:
            digest_hash = hashlib.sha256(
                (summary + "\n" + digest_json).encode("utf-8")).hexdigest()
            row = conn.execute(
                "SELECT summary, digest_json FROM context_summaries WHERE project_id IS ? "
                "AND session_id=? AND scope=? ORDER BY id DESC LIMIT 1",
                (project_id, session_id, scope),
            ).fetchone()
            if row:
                if str(row["summary"]) == summary:
                    # Same digest text: no new information, do not append a duplicate row.
                    return False
            with conn:
                conn.execute(
                    "INSERT INTO context_summaries"
                    "(project_id, session_id, scope, message_count, summary, covered_count, "
                    "digest_json, created_at) VALUES(?,?,?,?,?,?,?, datetime('now'))",
                    (project_id, session_id, scope, int(message_count), summary,
                     covered, digest_json),
                )
            return True
        finally:
            conn.close()

    def latest_summary(self, session_id: str | None = "",
                       scope: str = "chat") -> dict | None:
        conn = init_db()
        try:
            if session_id is None:
                row = conn.execute(
                    "SELECT * FROM context_summaries WHERE project_id IS ? "
                    "AND scope=? ORDER BY id DESC LIMIT 1",
                    (self.project_id, scope),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM context_summaries WHERE project_id IS ? "
                    "AND session_id=? AND scope=? ORDER BY id DESC LIMIT 1",
                    (self.project_id, session_id, scope),
                ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        try:
            digest = json.loads(row["digest_json"] or "{}")
        except (TypeError, ValueError):
            digest = {}
        return {"summary": str(row["summary"] or ""),
                "digest": digest if isinstance(digest, dict) else {},
                "message_count": int(row["message_count"] or 0),
                "covered_count": int(row["covered_count"] or 0),
                "created_at": str(row["created_at"] or "")}

    # ---------------------------------------------------------------- model

    def calibrate(self, provider_id: str, model_name: str, *,
                  prompt_tokens: int | None, chars_sent: int) -> float | None:
        return calibrate(provider_id, model_name, prompt_tokens=prompt_tokens,
                         chars_sent=chars_sent)

    # -------------------------------------------------------------- health

    def status(self) -> dict:
        profile = self.profile()
        memory_entries = project_memory.recall(self.project_id, "", limit=1)
        summary = self.latest_summary(None) if self.project_id is not None else None
        return {
            "project_id": self.project_id,
            "root": str(self.root) if self.root else None,
            "profile": {
                "available": profile is not None,
                "generated_at": getattr(profile, "generated_at", ""),
                "source_files": len(getattr(profile, "source_files", []) or []),
                "test_command": getattr(profile, "test_command", ""),
            },
            "memory": {"recallable": bool(memory_entries)},
            "summary": summary,
            "limits": {"note": "derived per model at call time from context.window",
                       "default_chars_per_token": DEFAULT_CHARS_PER_TOKEN,
                       "default_prompt_tokens": DEFAULT_PROMPT_TOKENS},
        }

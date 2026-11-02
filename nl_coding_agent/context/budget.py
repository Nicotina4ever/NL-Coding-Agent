"""Measured, loss-minimising context compaction for Chat prompts (P1).

Design goals (hardening after the first version):
* the limit is derived from the selected model's real window (``context.window``),
  never from a fixed byte wall, and it is not a cost or iteration budget;
* generated output and the model's thinking tokens are reserved explicitly, and
  reasoning text already present in the transcript is counted in the estimate;
* compaction preserves decisions and results: turns that contain writes, test or
  verification outcomes, errors, user steering/decisions and final answers are kept
  verbatim (bounded) while only routine chatter is folded into a structured digest;
* the digest is incremental: a previously persisted digest is extended instead of
  being recomputed, so long conversations survive a new session;
* it never raises on budget. If the model window is unknown the caller supplies a
  generous fallback and the pass degrades gradually.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Iterable

DEFAULT_CHARS_PER_TOKEN = 3.4
DEFAULT_PROMPT_TOKENS = 18_000
MIN_RECENT_UNITS = 6
SUMMARY_CHAR_LIMIT = 7_000
SUMMARY_LINE_CHARS = 220
TRIM_TOOL_RESULT_CHARS = 1_600
TRIM_MESSAGE_CHARS = 2_400
TRIM_CRITICAL_CHARS = 2_400
TRIM_TOOL_DESCRIPTION_CHARS = 400
SUMMARY_MESSAGE_OVERHEAD = 24

_WHITESPACE_RE = re.compile(r"\s+")
_CRITICAL_RE = re.compile(
    r"(?i)\b(approve|reject|pass|fail|failed|error|exception|traceback|exit[_ ]code|"
    r"verification|pytest|test[ _]result|decided|decision|instead|do not|don't|"
    r"non usare|invece|errore|verifica|commit)\b")
_WRITE_TOOLS = {"write_file", "patch_file", "start_coding", "start_mission"}


def _text_of(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key in ("content", "thinking", "reasoning", "reasoning_content",
                    "_thinking", "name", "summary", "error"):
            item = value.get(key)
            if isinstance(item, str) and item:
                parts.append(item)
        tool_calls = value.get("tool_calls")
        if tool_calls:
            try:
                parts.append(json.dumps(tool_calls, ensure_ascii=False, default=str))
            except (TypeError, ValueError):
                parts.append(str(tool_calls))
        if not parts:
            try:
                parts.append(json.dumps(value, ensure_ascii=False, default=str))
            except (TypeError, ValueError):
                parts.append(str(value))
        return "\n".join(parts)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def estimate_tokens(value, *, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    """Model-calibrated token estimate for text, messages or tool schemas.

    The ratio is calibrated from real provider prompt-token counts when available
    (``context.window.calibrate``); otherwise a conservative code/prose ratio is
    used. Reasoning/thinking fields are included because they occupy the window.
    """
    text = _text_of(value)
    if not text:
        return 0
    ratio = float(chars_per_token or DEFAULT_CHARS_PER_TOKEN)
    ratio = max(1.0, min(9.0, ratio))
    return max(1, int(math.ceil(len(text) / ratio)))


def json_chars(value) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return len(str(value))


@dataclass
class ChatBudget:
    messages: list[dict]
    tools: list[dict]
    chars: int
    estimated_tokens: int
    max_tokens: int = DEFAULT_PROMPT_TOKENS
    max_chars: int | None = None
    summarized: bool = False
    summary: str = ""
    digest: dict = field(default_factory=dict)
    summarized_messages: int = 0
    covered_messages: int = 0
    preserved_messages: int = 0
    trimmed: list[str] = field(default_factory=list)
    degraded: bool = False

    def to_dict(self) -> dict:
        return {
            "degraded": self.degraded,
            "summarized": self.summarized,
            "summarized_messages": self.summarized_messages,
            "covered_messages": self.covered_messages,
            "preserved_messages": self.preserved_messages,
            "summary": self.summary,
            "digest": dict(self.digest),
            "trimmed": list(self.trimmed),
            "chars": self.chars,
            "estimated_tokens": self.estimated_tokens,
            "max_tokens": self.max_tokens,
            "max_chars": self.max_chars,
        }


def split_units(messages: Iterable[dict]) -> tuple[list[dict], list[list[dict]]]:
    """Split a transcript into a system head and whole turn units.

    A ``tool`` message always belongs to the assistant turn that requested it, so
    compaction never leaves an orphan tool result without its call.
    """
    items = list(messages or [])
    head: list[dict] = []
    while items and str(items[0].get("role") or "") == "system":
        head.append(items.pop(0))
    units: list[list[dict]] = []
    for item in items:
        role = str(item.get("role") or "")
        if role == "tool" and units:
            units[-1].append(item)
        elif role == "assistant" and units and units[-1][-1].get("role") == "assistant":
            units[-1].append(item)
        else:
            units.append([item])
    return head, units


def _flatten(head: list[dict], units: list[list[dict]], extra: list[dict] | None = None) -> list[dict]:
    result = list(head) + list(extra or [])
    for unit in units:
        result.extend(unit)
    return result


def _first_line(text: str, limit: int = SUMMARY_LINE_CHARS) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "")).strip()[:limit]


def _unit_is_critical(unit: list[dict]) -> bool:
    for message in unit:
        role = str(message.get("role") or "")
        text = _text_of(message)
        if role == "tool" and _CRITICAL_RE.search(text):
            return True
        if role == "assistant":
            for call in message.get("tool_calls") or []:
                name = str((call.get("function") or {}).get("name") or "")
                if name in _WRITE_TOOLS:
                    return True
            if _CRITICAL_RE.search(text):
                return True
        if role == "user" and _CRITICAL_RE.search(text):
            return True
    return False


def _tool_call_paths(unit: list[dict]) -> list[str]:
    paths: list[str] = []
    for message in unit:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except (TypeError, ValueError):
                    arguments = {}
            if not isinstance(arguments, dict):
                continue
            path = str(arguments.get("path") or arguments.get("file") or "")
            if path:
                paths.append(path)
    return paths


def _tool_result_outcome(message: dict) -> str:
    name = str(message.get("name") or "tool")
    raw = str(message.get("content") or "")
    detail = ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            result = parsed.get("result")
            if isinstance(result, dict):
                if result.get("error"):
                    detail = "ERROR " + str(result["error"])[:160]
                elif result.get("isError") or result.get("ok") is False:
                    detail = "FAILED " + str(result.get("message") or "")[:160]
                elif result.get("returncode") is not None:
                    detail = "exit " + str(result.get("returncode"))
                elif result.get("unchanged") is not None:
                    detail = "ok"
                else:
                    detail = "ok"
            elif parsed.get("error"):
                detail = "ERROR " + str(parsed["error"])[:160]
    except (TypeError, ValueError):
        pass
    if not detail:
        match = re.search(r"(?i)(pass|fail|error|exit[_ ]code[:= ]?-?\d+)", raw)
        detail = match.group(1) if match else _first_line(raw, 120)
    return name + ": " + detail


def _collect_sections(units: list[list[dict]]) -> dict[str, list[str]]:
    """Collect objectives, decisions, results and issues from turn units."""
    sections: dict[str, list[str]] = {"requests": [], "decisions": [], "results": [],
                                      "issues": []}

    def add(section: str, line: str) -> None:
        line = _first_line(line)
        if line and line not in sections[section] and len(sections[section]) < 40:
            sections[section].append(line)

    for unit in units:
        paths = _tool_call_paths(unit)
        for message in unit:
            role = str(message.get("role") or "")
            if role == "user":
                text = _first_line(message.get("content"), SUMMARY_LINE_CHARS)
                if _CRITICAL_RE.search(text):
                    add("decisions", text)
                else:
                    add("requests", text)
            elif role == "assistant":
                text = _first_line(message.get("content"))
                if text:
                    if _CRITICAL_RE.search(text):
                        add("issues" if re.search(r"(?i)error|fail|reject", text) else "decisions", text)
                    else:
                        add("requests", "(answer) " + text)
                for path in paths:
                    add("results", "wrote/patched " + path)
            elif role == "tool":
                outcome = _tool_result_outcome(message)
                if re.search(r"(?i)error|fail|exit [1-9]", outcome):
                    add("issues", outcome)
                else:
                    add("results", outcome)
    return {key: list(value) for key, value in sections.items() if value}


def _render_summary(sections: dict[str, list[str]], *, previous: str = "",
                    covered_before: int = 0) -> tuple[str, dict]:
    lines: list[str] = list(previous.strip().splitlines()) if previous else []
    labels = (("requests", "OBJECTIVES"), ("decisions", "DECISIONS/STEERING"),
              ("results", "RESULTS"), ("issues", "OPEN ISSUES/ERRORS"))
    for key, label in labels:
        values = sections.get(key) or []
        if not values:
            continue
        header = label + ":"
        if header not in lines:
            lines.append(header)
        for value in values:
            item = "- " + value
            if item not in lines:
                lines.append(item)
    # Deduplicate and bound; the covered-message counter lives in the digest JSON,
    # not in the text, so the same transcript always yields the same summary.
    seen: set[str] = set()
    unique: list[str] = []
    for line in lines:
        key = line.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(line)
    text = "\n".join(unique).strip()
    if len(text) > SUMMARY_CHAR_LIMIT:
        text = text[:SUMMARY_CHAR_LIMIT].rstrip()
    digest = {key: list(value) for key, value in sections.items()}
    digest["covered_before"] = int(covered_before)
    return text, digest


def structured_summary(units: list[list[dict]], *, previous: str = "",
                       covered_before: int = 0) -> tuple[str, dict]:
    """Backwards-compatible wrapper returning a rendered incremental digest."""
    return _render_summary(_collect_sections(units), previous=previous,
                           covered_before=covered_before)


def _trim_message(message: dict, limit: int) -> bool:
    text = _text_of(message)
    if len(text) <= limit:
        return False
    message["content"] = text[:limit] + "\n... [context trimmed]"
    message.pop("thinking", None)
    message.pop("reasoning", None)
    return True


def _trim_tools(tools: list[dict], max_tokens: int,
                chars_per_token: float) -> tuple[list[dict], bool, int]:
    if not tools:
        return tools, False, 0
    if estimate_tokens(tools, chars_per_token=chars_per_token) <= max_tokens:
        return tools, False, 0
    copy = json.loads(json.dumps(tools, ensure_ascii=False, default=str))
    trimmed = 0
    for tool in copy:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict):
            continue
        description = str(function.get("description") or "")
        if len(description) > TRIM_TOOL_DESCRIPTION_CHARS:
            function["description"] = description[:TRIM_TOOL_DESCRIPTION_CHARS] + "..."
            trimmed += 1
        if estimate_tokens(copy, chars_per_token=chars_per_token) <= max_tokens:
            break
    return copy, trimmed > 0, trimmed


def _merge_sections(target: dict[str, list[str]],
                    source: dict[str, list[str]]) -> None:
    for key, values in (source or {}).items():
        bucket = target.setdefault(key, [])
        for value in values:
            if value not in bucket and len(bucket) < 40:
                bucket.append(value)


def _measure(messages: list[dict], tools: list[dict], chars_per_token: float) -> tuple[int, int]:
    return (estimate_tokens(messages, chars_per_token=chars_per_token),
            estimate_tokens(tools, chars_per_token=chars_per_token))


def compact_chat(
    messages: Iterable[dict],
    tools: Iterable[dict] | None = None,
    *,
    max_tokens: int | None = None,
    max_chars: int | None = None,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    tool_token_budget: int | None = None,
    tool_char_budget: int | None = None,
    min_recent_units: int = MIN_RECENT_UNITS,
    previous_summary: str = "",
    previous_covered: int = 0,
    summary_limit: int = SUMMARY_CHAR_LIMIT,
) -> ChatBudget:
    """Fit one Chat model turn into a dynamic window without losing decisions.

    Degradation order: trim old oversized payloads, shorten tool descriptions,
    fold routine turns into an incremental structured digest, drop only routine
    turns, trim preserved payloads, and finally hard-bound the result. Never raises.
    """
    if tool_token_budget is None and tool_char_budget:
        tool_token_budget = max(512, int(tool_char_budget / chars_per_token))
    if max_tokens is None:
        max_tokens = (int(max_chars / chars_per_token) if max_chars
                      else DEFAULT_PROMPT_TOKENS)
    max_tokens = max(512, int(max_tokens))
    tool_budget = int(tool_token_budget or max(512, max_tokens // 3))
    head, units = split_units(messages)
    tool_list = list(tools or [])
    trimmed: list[str] = []
    preserved = 0
    summarized_messages = 0
    summary = str(previous_summary or "").strip()
    digest: dict = {"reused_previous": True} if summary else {}
    digest_sections: dict[str, list[str]] = {}
    covered = int(previous_covered or 0)

    def message_list() -> list[dict]:
        return _flatten(head, units)

    def over() -> bool:
        tokens, tool_tokens = _measure(message_list(), tool_list, chars_per_token)
        return tokens + tool_tokens > max_tokens or (
            tool_tokens > tool_budget and tool_tokens > 0)

    if not over() and not _exceeds_chars(message_list(), tool_list, max_chars):
        return ChatBudget(messages=message_list(), tools=tool_list,
                          chars=json_chars(message_list()) + json_chars(tool_list),
                          estimated_tokens=sum(_measure(message_list(), tool_list,
                                                        chars_per_token)),
                          max_tokens=max_tokens, max_chars=max_chars)

    # 1. Trim oversized payloads in older units (never the most recent ones).
    old_units = units[:-min_recent_units] if len(units) > min_recent_units else []
    for unit in old_units:
        for message in unit:
            if _trim_message(message, TRIM_TOOL_RESULT_CHARS
                             if str(message.get("role")) == "tool"
                             else TRIM_MESSAGE_CHARS):
                trimmed.append("trimmed-" + str(message.get("role") or "message"))

    # 2. Shorten tool descriptions (parameter schemas are preserved).
    tool_list, tools_trimmed, tool_count = _trim_tools(tool_list, tool_budget, chars_per_token)
    if tools_trimmed:
        trimmed.append("trimmed-tool-descriptions:" + str(tool_count))

    # 3. Preserve critical and recent units; fold routine turns into an incremental
    #    digest. Already-covered messages are never folded twice.
    critical_indexes = {index for index, unit in enumerate(units)
                        if _unit_is_critical(unit)}
    # The latest turn is the active request: it is never folded or dropped.
    protected_indexes = set(critical_indexes)
    if units:
        protected_indexes.add(len(units) - 1)
    counts = [len(unit) for unit in units]
    total_messages = sum(counts)
    recent_count = sum(counts[-min_recent_units:]) if len(units) > min_recent_units else total_messages
    recent_start = max(0, len(units) - min_recent_units)
    fold_indexes: list[int] = []
    if previous_summary and previous_covered > 0:
        new_messages = total_messages - int(previous_covered)
        if new_messages > recent_count + 1:
            covered_boundary = int(previous_covered)
            accumulated = 0
            for index, count in enumerate(counts):
                if index >= recent_start:
                    break
                already = accumulated + count <= covered_boundary
                accumulated += count
                if already:
                    continue
                if index not in protected_indexes:
                    fold_indexes.append(index)
    else:
        fold_indexes = [index for index in range(len(units))
                        if index not in protected_indexes and index < recent_start]
    if fold_indexes and (over() or max_chars):
        folded = [units[index] for index in fold_indexes]
        _merge_sections(digest_sections, _collect_sections(folded))
        summarized_messages = sum(len(unit) for unit in folded)
        covered = max(int(previous_covered or 0),
                      total_messages - recent_count + summarized_messages)
        units = [unit for index, unit in enumerate(units) if index not in set(fold_indexes)]
        preserved = len(units)
    elif previous_summary:
        # Reuse the persisted digest without recomputing or duplicating it.
        summarized_messages = 0
        covered = int(previous_covered or 0)

    # 4. Still over: drop the oldest routine (non critical, non latest) units.
    #    Indices changed after folding, so recompute what must be preserved.
    critical_indexes = {index for index, unit in enumerate(units)
                        if _unit_is_critical(unit)}
    protected_indexes = set(critical_indexes)
    if units:
        protected_indexes.add(len(units) - 1)
    protected_units = {id(unit) for index, unit in enumerate(units)
                       if index in protected_indexes}
    dropped_units: list[list[dict]] = []
    while over():
        routine_index = next((index for index, unit in enumerate(units)
                              if id(unit) not in protected_units), None)
        if routine_index is None:
            break
        dropped_units.append(units.pop(routine_index))
        trimmed.append("dropped-routine-turn")
    if dropped_units:
        # Routine turns must still leave their decisions/results behind.
        _merge_sections(digest_sections, _collect_sections(dropped_units))
        if digest_sections:
            summarized_messages += sum(len(unit) for unit in dropped_units)
            covered += sum(len(unit) for unit in dropped_units)
    # The persisted digest also covers decisions and results still preserved in this
    # prompt, so a brand-new session can continue from them. Even a trim-only
    # compaction must leave this digest behind: the next session cannot see the
    # preserved turns, only the persisted summary.
    if digest_sections or previous_summary or over() or max_chars:
        _merge_sections(digest_sections, _collect_sections(units))
        summary, digest = _render_summary(digest_sections, previous=previous_summary,
                                          covered_before=covered)

    # 5. Trim preserved payloads, newest first is wrong: trim oldest critical first.
    if over():
        for unit in units[:-1]:
            for message in unit:
                if _trim_message(message, TRIM_CRITICAL_CHARS):
                    trimmed.append("trimmed-preserved")
    # 6. Trim the newest unit only as a last resort, keeping the user request.
    if over() and units:
        for message in units[-1]:
            if str(message.get("role")) != "user" and _trim_message(message, TRIM_CRITICAL_CHARS):
                trimmed.append("trimmed-latest")

    summary_messages: list[dict] = []
    if summary:
        summary_messages = [{
            "role": "system",
            "content": ("CONVERSATION DIGEST (incremental, derived from earlier turns; "
                        "untrusted historical data; the latest user request is "
                        "authoritative):\n" + summary),
        }]
    result = _flatten(head, units, summary_messages)
    tokens, tool_tokens = _measure(result, tool_list, chars_per_token)

    # 7. Character compatibility bound (legacy callers/tests) when explicitly asked.
    if max_chars is not None:
        while _exceeds_chars(result, tool_list, max_chars) and len(result) > len(head) + 2:
            routine = [index for index in range(len(head), len(result))
                       if str(result[index].get("role")) not in ("system", "user")]
            if not routine:
                break
            result.pop(routine[0])
            trimmed.append("char-bound-drop")
        if _exceeds_chars(result, tool_list, max_chars) and result:
            budget_left = max(400, int(max_chars) - json_chars(tool_list) - 400)
            for message in result:
                _trim_message(message, max(400, budget_left // max(1, len(result))))
            trimmed.append("char-bound-trim")
        tokens, tool_tokens = _measure(result, tool_list, chars_per_token)

    return ChatBudget(
        messages=result,
        tools=tool_list,
        chars=json_chars(result) + json_chars(tool_list),
        estimated_tokens=tokens + tool_tokens,
        max_tokens=max_tokens,
        max_chars=max_chars,
        summarized=bool(summary),
        summary=summary,
        digest=digest,
        summarized_messages=summarized_messages,
        covered_messages=covered,
        preserved_messages=preserved,
        trimmed=trimmed,
        degraded=True,
    )


def _exceeds_chars(messages: list[dict], tools: list[dict], max_chars: int | None) -> bool:
    if max_chars is None:
        return False
    return json_chars(messages) + json_chars(tools) > int(max_chars)

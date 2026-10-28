"""Bounded prompt-injection scanner for untrusted research content (NL-BP-175).

The scanner is deliberately passive: it never executes, evaluates, follows or
fetches anything found in content. It scans bounded text/markdown/HTML/JSON for
instruction-like language (prompt/system overrides, role changes, tool/command
execution, secret exfiltration, URL-assisted instructions and hidden/zero-width
text), returns immutable redacted records, and is unsuitable as a sandbox.

Public API:
  scan_text(text, source=...) -> InjectionScan
  scan_payload(mapping/list, source=...) -> InjectionScan
  InjectionSignal / InjectionScan (frozen dataclasses)
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

MAX_SCAN_CHARS = 200_000
MAX_SIGNALS = 100
MAX_WARNINGS = 10
MAX_EXCERPT_CHARS = 240
MAX_CONTEXT_CHARS = 70

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITIES = (SEVERITY_LOW, SEVERITY_MEDIUM, SEVERITY_HIGH)

KIND_INSTRUCTION_OVERRIDE = "instruction_override"
KIND_ROLE_OVERRIDE = "role_override"
KIND_TOOL_EXECUTION = "tool_execution"
KIND_SECRET_EXFILTRATION = "secret_exfiltration"
KIND_URL_INJECTION = "url_injection"
KIND_HIDDEN_TEXT = "hidden_text"
KINDS = (KIND_INSTRUCTION_OVERRIDE, KIND_ROLE_OVERRIDE, KIND_TOOL_EXECUTION,
         KIND_SECRET_EXFILTRATION, KIND_URL_INJECTION, KIND_HIDDEN_TEXT)

_ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
_HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.IGNORECASE | re.DOTALL)
_HIDDEN_STYLE_RE = re.compile(
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|"
    r"opacity\s*:\s*0(?:\.0+)?|color\s*:\s*(?:white|#fff(?:fff)?|transparent))",
    re.IGNORECASE)
_HIDDEN_ATTR_RE = re.compile(
    r"<[^>]*\b(?:hidden|aria-hidden\s*=\s*['\"]?true)\b[^>]*>", re.IGNORECASE)

_PATTERNS: tuple[tuple[str, str, re.Pattern], ...] = (
    (KIND_INSTRUCTION_OVERRIDE, SEVERITY_HIGH, re.compile(
        r"\b(?:ignore|disregard|forget|bypass|override|skip)\s+(?:all\s+)?"
        r"(?:the\s+)?(?:previous|prior|above|earlier|system|developer|security|"
        r"safety|hidden)\s+(?:instructions?|prompts?|rules?|messages?|"
        r"directives?|directions?)", re.IGNORECASE)),
    (KIND_INSTRUCTION_OVERRIDE, SEVERITY_HIGH, re.compile(
        r"\b(?:system|developer|admin(?:istrator)?)\s+(?:prompt|message|"
        r"instruction|override)s?\b", re.IGNORECASE)),
    (KIND_INSTRUCTION_OVERRIDE, SEVERITY_MEDIUM, re.compile(
        r"\b(?:new|updated|real)\s+instructions?\s*:", re.IGNORECASE)),
    (KIND_INSTRUCTION_OVERRIDE, SEVERITY_MEDIUM, re.compile(
        r"\bdo\s+not\s+(?:follow|obey|trust)\b[^\n.]{0,80}"
        r"\b(?:instructions?|rules?|system|safety)\b", re.IGNORECASE)),
    (KIND_ROLE_OVERRIDE, SEVERITY_HIGH, re.compile(
        r"\b(?:pretend|act\s+as|you\s+are\s+now|from\s+now\s+on\s+you\s+are|"
        r"role\s*[:=]\s*)\s*(?:a\s+|an\s+|the\s+)?(?:system|developer|admin|"
        r"assistant|root|superuser|unrestricted|jailbroken)\b", re.IGNORECASE)),
    (KIND_ROLE_OVERRIDE, SEVERITY_MEDIUM, re.compile(
        r"\b(?:you\s+are|you're)\s+(?:now\s+)?(?:a\s+|an\s+|the\s+)?"
        r"(?:different|unrestricted|jailbroken|developer|admin)\b", re.IGNORECASE)),
    (KIND_TOOL_EXECUTION, SEVERITY_HIGH, re.compile(
        r"\b(?:run|execute|invoke|call|use)\s+(?:the\s+)?(?:tool|command|shell|"
        r"terminal|sub" r"process|script|program|powershell|cmd(?:\.exe)?|bash|sh|"
        r"curl|wget|python|node|browser|filesystem)\b", re.IGNORECASE)),
    (KIND_TOOL_EXECUTION, SEVERITY_HIGH, re.compile(
        r"\b(?:sub" r"process|os\.system|eval|exec)\s*\(", re.IGNORECASE)),
    (KIND_TOOL_EXECUTION, SEVERITY_MEDIUM, re.compile(
        r"\b(?:rm\s+-rf|del\s+/s|format\s+c:|shutdown\s+/s|mkfs\b)", re.IGNORECASE)),
    (KIND_TOOL_EXECUTION, SEVERITY_MEDIUM, re.compile(
        r"\b(?:curl|wget|invoke-webrequest|start-process)\b", re.IGNORECASE)),
    (KIND_SECRET_EXFILTRATION, SEVERITY_HIGH, re.compile(
        r"\b(?:exfiltrate|steal|harvest|leak|dump|reveal|print|send|upload|"
        r"post|transmit|forward|share)\b[^\n.]{0,100}\b(?:secret|secrets|"
        r"token|tokens|api[\s_-]*key|password|passwords|credential|credentials|"
        r"environment\s+variables?|env\s+vars?|private\s+key|\.env|ssh\s+key|"
        r"cookies?)\b", re.IGNORECASE)),
    (KIND_SECRET_EXFILTRATION, SEVERITY_HIGH, re.compile(
        r"\b(?:read|cat|print|show|copy|collect)\s+(?:the\s+)?(?:env|\.env|"
        r"credentials|~?/\.ssh|environment)\b", re.IGNORECASE)),
    (KIND_SECRET_EXFILTRATION, SEVERITY_MEDIUM, re.compile(
        r"\b(?:secret|token|password|credential|api[\s_-]*key)s?\b[^\n.]{0,60}"
        r"\b(?:send|upload|post|forward|exfiltrate|share)\b", re.IGNORECASE)),
    (KIND_URL_INJECTION, SEVERITY_HIGH, re.compile(
        r"\b(?:visit|open|navigate\s+to|go\s+to|fetch|download|request|read\s+from)\b"
        r"[^\n.]{0,80}https?://", re.IGNORECASE)),
    (KIND_URL_INJECTION, SEVERITY_HIGH, re.compile(
        r"\b(?:javascript|data|file|ftp|smb):[^\s\"'<>)]+", re.IGNORECASE)),
    (KIND_URL_INJECTION, SEVERITY_MEDIUM, re.compile(
        r"\[[^\]]{0,120}\]\((?:javascript|data|file|ftp|smb):[^)]+\)",
        re.IGNORECASE)),
)


class InjectionScanError(ValueError):
    """Raised for invalid scanner input (never for content signals)."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _safe_excerpt(text: str, start: int, end: int, *, kind: str) -> str:
    """Bounded redacted excerpt: the matched span itself is never emitted."""
    if kind == KIND_HIDDEN_TEXT:
        return "[hidden/zero-width content redacted]"
    before = text[max(0, start - MAX_CONTEXT_CHARS):start]
    after = text[end:end + MAX_CONTEXT_CHARS]
    url_re = re.compile(r"https?://[^\s\"'<>)]+", re.IGNORECASE)

    def clean(value: str) -> str:
        # Scrub instruction-like patterns and URLs from surrounding context too:
        # an excerpt must never become a second copy of the malicious payload.
        for _kind, _severity, pattern in _PATTERNS:
            value = pattern.sub(" [REDACTED] ", value)
        value = url_re.sub(" [URL] ", value)
        value = _ZERO_WIDTH_RE.sub("", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value[:MAX_EXCERPT_CHARS]
    excerpt = (clean(before) + " [REDACTED] " + clean(after)).strip()
    if len(excerpt) > MAX_EXCERPT_CHARS:
        excerpt = excerpt[:MAX_EXCERPT_CHARS - 15].rstrip() + " [truncated]"
    return excerpt


@dataclass(frozen=True, slots=True)
class InjectionSignal:
    """One immutable, redacted injection-like content signal."""

    kind: str
    severity: str
    excerpt: str
    sha256: str
    offset: int
    source: str = ""

    @property
    def hash(self) -> str:
        """Alias used by audit/evidence consumers for the matched-span hash."""
        return self.sha256

    def to_dict(self) -> dict:
        return {"kind": self.kind, "severity": self.severity,
                "excerpt": self.excerpt, "sha256": self.sha256,
                "hash": self.sha256,
                "offset": int(self.offset), "source": self.source,
                "untrusted": True}


@dataclass(frozen=True, slots=True)
class InjectionScan:
    """Immutable summary of one bounded scan."""

    signals: tuple[InjectionSignal, ...] = ()
    scanned_chars: int = 0
    truncated: bool = False
    content_sha256: str = ""
    sources: tuple[str, ...] = ()
    untrusted: bool = True

    @property
    def count(self) -> int:
        return len(self.signals)

    @property
    def has_signals(self) -> bool:
        return bool(self.signals)

    @property
    def highest_severity(self) -> str:
        best = SEVERITY_LOW
        for signal in self.signals:
            if SEVERITIES.index(signal.severity) > SEVERITIES.index(best):
                best = signal.severity
        return best if self.signals else "none"

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({signal.kind for signal in self.signals}))

    def warnings(self, limit: int = MAX_WARNINGS) -> list[dict]:
        """Bounded warning dictionaries safe to place in a research result."""
        limit = max(0, min(int(limit), MAX_WARNINGS))
        return [signal.to_dict() for signal in self.signals[:limit]]

    def to_dict(self) -> dict:
        return {"count": self.count, "kinds": list(self.kinds),
                "highest_severity": self.highest_severity,
                "signals": [signal.to_dict() for signal in self.signals],
                "scanned_chars": self.scanned_chars,
                "truncated": bool(self.truncated),
                "content_sha256": self.content_sha256,
                "sources": list(self.sources), "untrusted": True}


def _normalize_zero_width(text: str) -> tuple[str, list[int], int]:
    chars: list[str] = []
    offsets: list[int] = []
    hidden = 0
    for index, char in enumerate(text):
        if _ZERO_WIDTH_RE.match(char):
            hidden += 1
            continue
        chars.append(char)
        offsets.append(index)
    return "".join(chars), offsets, hidden


def _signal(kind: str, severity: str, excerpt: str, matched: str,
            offset: int, source: str) -> InjectionSignal:
    return InjectionSignal(kind=kind, severity=severity, excerpt=excerpt,
                           sha256=_sha256(matched), offset=int(offset),
                           source=str(source or "")[:500])


def scan_text(text: Any, *, source: str = "", max_chars: int = MAX_SCAN_CHARS,
              max_signals: int = MAX_SIGNALS) -> InjectionScan:
    """Scan bounded text deterministically; never executes or follows content."""
    if text is None:
        text = ""
    raw = str(text)
    max_chars = max(1, min(int(max_chars), MAX_SCAN_CHARS))
    max_signals = max(1, min(int(max_signals), MAX_SIGNALS))
    truncated = len(raw) > max_chars
    content = raw[:max_chars]
    normalized, offsets, hidden_count = _normalize_zero_width(content)
    # Unicode/entity tricks are matched on a decoded copy as well; offsets are
    # approximate for decoded matches but remain bounded and deterministic.
    decoded = html.unescape(normalized)
    signals: list[InjectionSignal] = []

    def add(kind: str, severity: str, matched: str, offset: int,
            excerpt: str | None = None) -> None:
        if len(signals) >= max_signals:
            return
        signals.append(_signal(kind, severity,
                               excerpt if excerpt is not None else
                               _safe_excerpt(content, offset,
                                             offset + max(1, len(matched)),
                                             kind=kind),
                               matched, offset, source))

    seen: set[tuple[str, int]] = set()

    def run(text_value: str, mapping: list[int] | None, *,
            source_text: str) -> None:
        for kind, severity, pattern in _PATTERNS:
            for match in pattern.finditer(text_value):
                if len(signals) >= max_signals:
                    return
                matched = match.group(0)
                if mapping is not None:
                    start = mapping[min(match.start(), len(mapping) - 1)] \
                        if mapping else 0
                else:
                    start = match.start()
                key = (kind, int(start))
                if key in seen:
                    continue
                seen.add(key)
                add(kind, severity, matched, start)

    run(normalized, offsets, source_text=content)
    if decoded != normalized:
        run(decoded, None, source_text=normalized)

    # Hidden HTML/markdown tricks are content signals even without a phrase.
    hidden_excerpt = "[hidden/zero-width content redacted]"
    if hidden_count:
        add(KIND_HIDDEN_TEXT, SEVERITY_MEDIUM,
            "zero-width characters: " + str(hidden_count),
            offsets[0] if offsets else 0, excerpt=hidden_excerpt)
    for match in _HTML_COMMENT_RE.finditer(content):
        add(KIND_HIDDEN_TEXT, SEVERITY_MEDIUM, match.group(0),
            match.start(), excerpt=hidden_excerpt)
    for match in _HIDDEN_STYLE_RE.finditer(content):
        add(KIND_HIDDEN_TEXT, SEVERITY_MEDIUM, match.group(0),
            match.start(), excerpt=hidden_excerpt)
    for match in _HIDDEN_ATTR_RE.finditer(content):
        add(KIND_HIDDEN_TEXT, SEVERITY_LOW, match.group(0),
            match.start(), excerpt=hidden_excerpt)
    # Deterministic order: severity desc then offset asc then kind.
    signals.sort(key=lambda item: (-SEVERITIES.index(item.severity),
                                    item.offset, item.kind))
    signals = signals[:max_signals]
    combined_sources = (str(source)[:500],) if source else ()
    return InjectionScan(
        signals=tuple(signals), scanned_chars=len(content),
        truncated=bool(truncated),
        content_sha256=_sha256(content), sources=combined_sources,
        untrusted=True)


def scan_payload(value: Any, *, source: str = "",
                 max_chars: int = MAX_SCAN_CHARS,
                 max_signals: int = MAX_SIGNALS) -> InjectionScan:
    """Recursively scan string leaves of a bounded JSON-like payload."""
    chunks: list[tuple[str, str]] = []
    budget = [max(1, min(int(max_chars), MAX_SCAN_CHARS))]

    def walk(item: Any, path: str, depth: int) -> None:
        if budget[0] <= 0 or depth > 12:
            return
        if isinstance(item, str):
            text = item[:budget[0]]
            budget[0] -= len(text)
            chunks.append((path, text))
        elif isinstance(item, Mapping):
            for key, child in list(item.items())[:200]:
                walk(child, path + "." + str(key)[:80], depth + 1)
                if budget[0] <= 0:
                    return
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(list(item)[:200]):
                walk(child, path + "[" + str(index) + "]", depth + 1)
                if budget[0] <= 0:
                    return

    walk(value, source or "payload", 0)
    scans = [scan_text(text, source=path, max_chars=len(text) + 1,
                       max_signals=max_signals)
             for path, text in chunks]
    return combine_scans(scans, max_signals=max_signals)


def combine_scans(scans: Iterable[InjectionScan], *,
                  max_signals: int = MAX_SIGNALS) -> InjectionScan:
    signals: list[InjectionSignal] = []
    scanned = 0
    truncated = False
    sources: list[str] = []
    digests: list[str] = []
    for scan in scans:
        if not isinstance(scan, InjectionScan):
            raise InjectionScanError("combine_scans expects InjectionScan records")
        scanned += scan.scanned_chars
        truncated = truncated or scan.truncated
        sources.extend(scan.sources)
        if scan.content_sha256:
            digests.append(scan.content_sha256)
        signals.extend(scan.signals)
    # Deduplicate identical signals, preserving deterministic order.
    unique: list[InjectionSignal] = []
    seen: set[tuple] = set()
    for signal in signals:
        key = (signal.kind, signal.sha256, signal.offset, signal.source)
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)
    unique.sort(key=lambda item: (item.source, -SEVERITIES.index(item.severity),
                                  item.offset, item.kind))
    unique = unique[:max(1, min(int(max_signals), MAX_SIGNALS))]
    digest = _sha256("".join(digests)) if digests else ""
    return InjectionScan(signals=tuple(unique), scanned_chars=scanned,
                         truncated=truncated, content_sha256=digest,
                         sources=tuple(dict.fromkeys(sources)), untrusted=True)


def scan_html(text: Any, *, source: str = "") -> InjectionScan:
    """Convenience alias for scanning HTML/markdown source."""
    return scan_text(text, source=source)


def warnings_for(value: Any, *, source: str = "",
                 limit: int = MAX_WARNINGS) -> list[dict]:
    return scan_payload(value, source=source).warnings(limit=limit)

# Convenience/back-compat aliases used by integrations and tests.
scan = scan_text
scan_untrusted = scan_payload
detect_injections = scan_text

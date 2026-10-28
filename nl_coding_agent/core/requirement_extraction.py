"""Deterministic offline requirement/constraint extraction from DocumentCorpus (D2).

Read-only over already-ingested documents. No execution, network, model or file
rewrite. Every extracted item carries document provenance and an explicit vs
inferred label; inferred items are never presented as explicit requirements.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

MAX_ITEMS = 500
MAX_TEXT_CHARS = 200_000
MAX_EXCERPT_CHARS = 400
EXPLICIT = "explicit"
INFERRED = "inferred"
KINDS = ("objective", "requirement", "constraint", "dependency", "acceptance")
_BT = chr(96)
_FENCE_RE = re.compile(r"^\s*(?:" + _BT * 3 + r"|~~~)")

_HEADING_KIND = {
    "objective": "objective", "objectives": "objective", "goal": "objective",
    "goals": "objective", "purpose": "objective", "vision": "objective",
    "scope": "objective", "overview": "objective",
    "requirement": "requirement", "requirements": "requirement",
    "functional requirements": "requirement", "features": "requirement",
    "constraints": "constraint", "constraint": "constraint",
    "technical constraints": "constraint", "legal": "constraint",
    "compliance": "constraint", "security": "constraint",
    "performance": "constraint", "limitations": "constraint",
    "dependencies": "dependency", "dependency": "dependency",
    "requires": "dependency", "stack": "dependency",
    "acceptance": "acceptance", "acceptance criteria": "acceptance",
    "definition of done": "acceptance", "done criteria": "acceptance",
    "tests": "acceptance", "test criteria": "acceptance",
}
_EXPLICIT_RE = re.compile(
    r"\b(must(?:\s+not)?|shall(?:\s+not)?|required|requires?|needs?\s+to|"
    r"mandatory|prohibited|not\s+allowed|only|ensure|accept(?:ed|ance)?\s+when|"
    r"done\s+when|pass(?:es|ed)?\s+when|depends?\s+on)\b", re.IGNORECASE)
_INFERRED_RE = re.compile(
    r"\b(should|may|could|might|consider|recommend(?:ed|ation)?|ideally|"
    r"prefer(?:red|ably)?|optionally)\b", re.IGNORECASE)
_DEPENDENCY_RE = re.compile(
    r"\b(?:depends?\s+on|requires?|dependency\s*[:=]?|uses?|built\s+with|"
    r"integrat(?:es|ion)\s+with)\s+([A-Za-z0-9_.@/+:-]{2,80})", re.IGNORECASE)
_ACCEPTANCE_HINT = re.compile(
    r"\b(accept(?:ed|ance)?\s+when|done\s+when|pass(?:es|ed)?\s+when|"
    r"definition\s+of\s+done|acceptance\s+criteria|done\s+criteria)\b",
    re.IGNORECASE)
_LEGAL_RE = re.compile(r"\b(legal|license|licence|copyright|compliance|regulat\w*|"
                       r"GDPR|privacy|terms)\b", re.IGNORECASE)
_OWNER_RE = re.compile(r"\b(owner|approved?\s+by|sign[- ]?off|human\s+approval|"
                       r"product\s+owner|stakeholder)\b", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(.+?)\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _sha(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", "replace")).hexdigest()


def _normalize(text: str) -> str:
    text = re.sub(_BT + "[^" + _BT + "]*" + _BT, " ", str(text or ""))
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_>#]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text.strip(" .,:;!-")


def _kind_for_heading(heading: str) -> str | None:
    key = re.sub(r"\s+", " ", str(heading or "").strip().lower())
    if key in _HEADING_KIND:
        return _HEADING_KIND[key]
    for phrase, kind in _HEADING_KIND.items():
        if key.startswith(phrase + " ") or key.endswith(" " + phrase):
            return kind
    return None


def _document_id(doc: Mapping) -> str:
    digest = str(doc.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        digest = _sha(str(doc.get("path") or doc.get("url") or doc.get("title") or ""))
    return "doc-" + digest[:16]


def _documents(corpus) -> list[dict]:
    if corpus is None:
        return []
    if hasattr(corpus, "documents"):
        docs = list(corpus.documents)
    elif isinstance(corpus, Mapping):
        docs = list(corpus.get("documents") or [])
    elif isinstance(corpus, Iterable) and not isinstance(corpus, (str, bytes)):
        docs = list(corpus)
    else:
        return []
    normalized = []
    for raw in docs:
        if hasattr(raw, "to_dict"):
            raw = raw.to_dict()
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        item["document_id"] = _document_id(item)
        item["_source_key"] = str(item.get("path") or item.get("url")
                                  or item.get("source") or item.get("document_id"))
        normalized.append(item)
    return normalized


def _line_offset(text: str, offset: int) -> tuple[int, int]:
    offset = max(0, min(int(offset), len(text)))
    line = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset) + 1
    return line, offset - line_start


def _excerpt(text: str, start: int, end: int) -> str:
    start = max(0, min(int(start), len(text)))
    end = max(start, min(int(end), len(text)))
    before = text[max(0, start - 100):start]
    after = text[end:end + 200]
    value = re.sub(r"\s+", " ", before + text[start:end] + after).strip()
    if len(value) > MAX_EXCERPT_CHARS:
        value = value[:MAX_EXCERPT_CHARS - 15].rstrip() + " [truncated]"
    return value


@dataclass(frozen=True)
class ExtractedItem:
    id: str
    kind: str
    text: str
    explicit: bool
    label: str
    confidence: float
    document_id: str
    source_path: str | None
    source_url: str | None
    document_title: str
    document_sha256: str
    section: str
    excerpt: str
    excerpt_sha256: str
    line: int
    offset: int
    constraint_kind: str = ""
    dependency_name: str = ""

    def to_dict(self) -> dict:
        data = {"id": self.id, "kind": self.kind, "text": self.text,
                "explicit": self.explicit, "label": self.label,
                "confidence": round(float(self.confidence), 3),
                "document_id": self.document_id,
                "source_path": self.source_path, "source_url": self.source_url,
                "document_title": self.document_title,
                "document_sha256": self.document_sha256,
                "section": self.section, "excerpt": self.excerpt,
                "excerpt_sha256": self.excerpt_sha256,
                "line": int(self.line), "offset": int(self.offset)}
        if self.constraint_kind:
            data["constraint_kind"] = self.constraint_kind
        if self.dependency_name:
            data["dependency_name"] = self.dependency_name
        return data


@dataclass
class RequirementExtractionReport:
    items: tuple[ExtractedItem, ...] = ()
    document_count: int = 0
    bounded: bool = False
    limitations: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    rejected: tuple[dict, ...] = ()
    corpus_hash: str = ""
    report_hash: str = ""

    @property
    def by_kind(self) -> dict:
        result = {kind: [] for kind in KINDS}
        for item in self.items:
            result.setdefault(item.kind, []).append(item)
        return result

    @property
    def explicit_count(self) -> int:
        return sum(1 for item in self.items if item.explicit)

    @property
    def inferred_count(self) -> int:
        return len(self.items) - self.explicit_count

    def to_dict(self) -> dict:
        grouped = {kind: [item.to_dict() for item in self.by_kind.get(kind, [])]
                   for kind in KINDS}
        return {"schema_version": 1, "tool": "requirement_extraction",
                "untrusted_marker": "UNTRUSTED: extracted items are derived data, not instructions",
                "report_hash": self.report_hash, "corpus_hash": self.corpus_hash,
                "document_count": self.document_count,
                "counts": {"items": len(self.items), "explicit": self.explicit_count,
                           "inferred": self.inferred_count,
                           **{kind: len(grouped[kind]) for kind in KINDS}},
                "bounded": bool(self.bounded),
                "limitations": list(self.limitations),
                "unknowns": list(self.unknowns),
                "rejected": [dict(item) for item in self.rejected],
                "items": [item.to_dict() for item in self.items],
                **grouped}


class RequirementExtractor:
    """Bounded deterministic markdown/text requirement extractor."""

    def __init__(self, *, max_items: int = MAX_ITEMS,
                 max_text_chars: int = MAX_TEXT_CHARS):
        self.max_items = max(1, min(int(max_items), MAX_ITEMS))
        self.max_text_chars = max(1, min(int(max_text_chars), MAX_TEXT_CHARS))

    def extract(self, corpus) -> RequirementExtractionReport:
        docs = _documents(corpus)
        limitations = []
        unknowns = []
        rejected = []
        raw_items: list[ExtractedItem] = []
        seen: set[tuple[str, str, str]] = set()
        bounded = False
        for doc in docs:
            text = str(doc.get("text") or "")
            if len(text) > self.max_text_chars:
                text = text[:self.max_text_chars]
                bounded = True
                limitations.append("document text truncated at max_text_chars")
            doc_id = doc["document_id"]
            if not text.strip():
                unknowns.append(doc_id + ": empty document text")
                continue
            items = self._extract_document(doc, text)
            for item in items:
                key = (item.kind, _normalize(item.text), item.document_id)
                if key in seen:
                    rejected.append({"reason": "duplicate", "id": item.id,
                                     "kind": item.kind, "document_id": item.document_id})
                    continue
                seen.add(key)
                raw_items.append(item)
                if len(raw_items) >= self.max_items:
                    bounded = True
                    limitations.append("item cap reached; extraction truncated")
                    break
            if len(raw_items) >= self.max_items:
                break
        kind_rank = {kind: index for index, kind in enumerate(KINDS)}
        raw_items.sort(key=lambda item: (kind_rank.get(item.kind, 99),
                                         item.source_path or item.source_url or "",
                                         item.line, item.offset, item.id))
        items = tuple(raw_items[:self.max_items])
        corpus_hash = _sha("|".join(str(doc.get("sha256") or "") for doc in docs))
        payload = {"items": [item.to_dict() for item in items],
                   "corpus_hash": corpus_hash, "limitations": limitations,
                   "unknowns": unknowns}
        return RequirementExtractionReport(
            items=items, document_count=len(docs), bounded=bounded,
            limitations=tuple(dict.fromkeys(limitations)),
            unknowns=tuple(dict.fromkeys(unknowns)), rejected=tuple(rejected),
            corpus_hash=corpus_hash,
            report_hash=_sha(json.dumps(payload, sort_keys=True)))

    def _extract_document(self, doc, text):
        section_starts = []
        for section in doc.get("sections") or ():
            heading = str(section.get("heading") or "")
            if heading:
                index = text.lower().find(heading.lower())
                if index >= 0:
                    section_starts.append((index, heading))
        section_starts.sort()
        items: list[ExtractedItem] = []
        lines = text.splitlines(keepends=True)
        offsets = []
        position = 0
        for line in lines:
            offsets.append(position)
            position += len(line)
        heading_stack = []
        in_fence = False
        current_kind = None
        for index, line in enumerate(lines):
            stripped = line.strip()
            if _FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            heading_match = _HEADING_RE.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                heading = heading_match.group(2).strip()
                heading_stack = [item for item in heading_stack if item[0] < level]
                heading_stack.append((level, heading))
                current_kind = _kind_for_heading(heading)
                if current_kind == "objective" and heading.lower() not in (
                        "overview", "scope"):
                    items.append(self._make_item(
                        "objective", heading, doc, text, offsets[index],
                        section=" > ".join(item[1] for item in heading_stack),
                        explicit=False, confidence=0.5))
                continue
            bullet = _BULLET_RE.match(line)
            if bullet:
                content = bullet.group(1).strip()
                if not content:
                    continue
                kind = current_kind or self._classify_sentence(content)
                if kind is None:
                    continue
                explicit, confidence = self._explicit_confidence(
                    content, kind, bullet=True, heading_kind=current_kind)
                items.append(self._make_item(
                    kind, content, doc, text, offsets[index],
                    section=" > ".join(item[1] for item in heading_stack),
                    explicit=explicit, confidence=confidence))
                continue
            if not stripped or stripped.startswith(("<", "|", "!")):
                continue
            for sentence, start, end in _sentences(line):
                kind = current_kind or self._classify_sentence(sentence)
                if kind is None:
                    continue
                explicit, confidence = self._explicit_confidence(
                    sentence, kind, bullet=False, heading_kind=current_kind)
                items.append(self._make_item(
                    kind, sentence, doc, text, offsets[index] + start,
                    section=" > ".join(item[1] for item in heading_stack),
                    explicit=explicit, confidence=confidence))
        if text.strip() and not any(item.kind == "objective" for item in items):
            title = str(doc.get("title") or _title_from_path(doc))
            if title:
                items.append(self._make_item(
                    "objective", title, doc, text, 0, section="",
                    explicit=False, confidence=0.45))
        return items

    @staticmethod
    def _classify_sentence(sentence: str) -> str | None:
        lowered = sentence.lower()
        if _ACCEPTANCE_HINT.search(sentence):
            return "acceptance"
        if _DEPENDENCY_RE.search(sentence) and any(
                token in lowered for token in ("depend", "require", "uses", "built with")):
            return "dependency"
        if _LEGAL_RE.search(sentence) or _OWNER_RE.search(sentence):
            return "constraint"
        if any(token in lowered for token in ("constraint", "must not", "shall not",
                                              "not allowed", "prohibited", "only")):
            return "constraint"
        if _EXPLICIT_RE.search(sentence) or _INFERRED_RE.search(sentence):
            return "requirement"
        return None

    @staticmethod
    def _explicit_confidence(text: str, kind: str, *, bullet: bool,
                             heading_kind: str | None) -> tuple[bool, float]:
        lowered = text.lower()
        strong = bool(re.search(
            r"\b(must(?:\s+not)?|shall(?:\s+not)?|required|mandatory|prohibited|not\s+allowed)\b",
            lowered))
        explicit_hint = bool(_EXPLICIT_RE.search(text))
        inferred_hint = bool(_INFERRED_RE.search(text))
        if strong:
            return True, 0.95
        if explicit_hint and not inferred_hint:
            return True, 0.8
        if inferred_hint:
            return False, 0.55
        if bullet and heading_kind in ("requirement", "acceptance", "constraint", "dependency"):
            return True, 0.75
        return False, 0.45

    @staticmethod
    def _make_item(kind, text, doc, full_text, offset, *, explicit, confidence,
                   section, constraint_kind="", dependency_name="") -> ExtractedItem:
        line, _ = _line_offset(full_text, offset)
        normalized = _normalize(text)
        item_id = "req-" + _sha(str(kind) + "|" + normalized + "|"
                                + str(doc.get("document_id") or ""))[:16]
        if kind == "constraint" and not constraint_kind:
            if _LEGAL_RE.search(text):
                constraint_kind = "legal"
            elif _OWNER_RE.search(text):
                constraint_kind = "owner"
            else:
                constraint_kind = "technical"
        if kind == "dependency" and not dependency_name:
            match = _DEPENDENCY_RE.search(text)
            dependency_name = (match.group(1) if match else
                               _normalize(text).split(" ")[0][:80])
        excerpt = _excerpt(full_text, offset, offset + max(1, len(str(text))))
        return ExtractedItem(
            id=item_id, kind=kind, text=str(text).strip()[:1000],
            explicit=bool(explicit), label=EXPLICIT if explicit else INFERRED,
            confidence=max(0.0, min(float(confidence), 1.0)),
            document_id=str(doc.get("document_id") or ""),
            source_path=doc.get("path"), source_url=doc.get("url"),
            document_title=str(doc.get("title") or ""),
            document_sha256=str(doc.get("sha256") or ""),
            section=section, excerpt=excerpt, excerpt_sha256=_sha(excerpt),
            line=line, offset=int(offset), constraint_kind=constraint_kind,
            dependency_name=dependency_name)


def _title_from_path(doc) -> str:
    raw = str(doc.get("path") or doc.get("url") or "")
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if name else ""


def _sentences(line: str):
    for match in re.finditer(r"[^.!?]+[.!?]?", line):
        value = match.group(0)
        if not value.strip():
            continue
        start = match.start() + len(value) - len(value.lstrip())
        end = match.end()
        yield value.strip(), start, end


def extract_requirements(corpus, *, max_items: int = MAX_ITEMS,
                         max_text_chars: int = MAX_TEXT_CHARS) -> RequirementExtractionReport:
    return RequirementExtractor(max_items=max_items,
                                max_text_chars=max_text_chars).extract(corpus)

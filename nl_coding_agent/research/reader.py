"""Readable-page extraction for the research foundation (NL-BP-170).

HTML is parsed with the standard library HTMLParser only; scripts are never
executed, and script/style/embed-like element content is dropped and recorded.
The extractor produces deterministic plain text and markdown, a title, metadata,
headings, paragraphs, lists, code/pre blocks, links (resolved against the final
URL) and basic tables.  Plain text, markdown and JSON pass through unchanged;
PDF/Office/other binary media types return an explicit UnsupportedDocument
instead of pretending to read them.

Retrieved documents are untrusted input: this module only structures text and
keeps the source citation/provenance.  It does not follow links, run scripts or
interpret instructions found in the content.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from .models import (
    KIND_BINARY,
    KIND_HTML,
    KIND_JSON,
    KIND_MARKDOWN,
    KIND_TEXT,
    Citation,
    RetrievedDocument,
    Source,
    freeze_metadata,
)

MAX_TEXT_CHARS = 500_000
MAX_LINKS = 500
SKIPPED_TAGS = frozenset({
    "script", "style", "template", "noscript", "iframe", "object", "embed",
    "svg", "canvas", "video", "audio", "source", "track",
})
BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "div", "dl", "dt", "dd",
    "fieldset", "figcaption", "figure", "footer", "form", "header", "hr",
    "main", "nav", "section", "summary", "details",
})
HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_PDF_TYPES = frozenset({"application/pdf"})
_OFFICE_TYPES = frozenset({
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "application/epub+zip",
})


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True, slots=True)
class Link:
    text: str
    url: str


@dataclass(frozen=True, slots=True)
class CodeBlock:
    text: str
    language: str = ""


@dataclass(frozen=True, slots=True)
class ListBlock:
    ordered: bool
    items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Table:
    rows: tuple[tuple[str, ...], ...]
    has_header: bool = False


@dataclass(frozen=True, slots=True)
class ReadablePage:
    """Structured, deterministic reading of one retrieved document."""

    source: Source
    title: str
    metadata: tuple[tuple[str, str], ...]
    text: str
    markdown: str
    headings: tuple[Heading, ...] = ()
    paragraphs: tuple[str, ...] = ()
    lists: tuple[ListBlock, ...] = ()
    code_blocks: tuple[CodeBlock, ...] = ()
    links: tuple[Link, ...] = ()
    tables: tuple[Table, ...] = ()
    removed: tuple[str, ...] = ()
    untrusted: bool = True
    truncated: bool = False
    kind: str = KIND_HTML

    def __post_init__(self) -> None:
        if self.untrusted is not True:
            raise ValueError("readable pages must remain marked untrusted")
        if not isinstance(self.source, Source):
            raise TypeError("ReadablePage requires a Source record")

    @property
    def canonical_url(self) -> str:
        return self.source.canonical_url

    @property
    def citation(self) -> Citation:
        return self.source.citation()

    def metadata_dict(self) -> dict[str, str]:
        return {name: value for name, value in self.metadata}

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "untrusted": True,
            "title": self.title,
            "canonical_url": self.canonical_url,
            "metadata": [list(pair) for pair in self.metadata],
            "headings": [{"level": item.level, "text": item.text}
                         for item in self.headings],
            "paragraphs": list(self.paragraphs),
            "lists": [{"ordered": item.ordered, "items": list(item.items)}
                      for item in self.lists],
            "code_blocks": [{"language": item.language, "text": item.text}
                            for item in self.code_blocks],
            "links": [{"text": item.text, "url": item.url} for item in self.links],
            "tables": [{"has_header": item.has_header,
                        "rows": [list(row) for row in item.rows]}
                       for item in self.tables],
            "removed": list(self.removed),
            "text": self.text,
            "markdown": self.markdown,
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class UnsupportedDocument:
    """Explicit fail-closed result for formats this foundation cannot read."""

    source: Source
    media_type: str
    reason: str
    detail: str
    untrusted: bool = True

    def __post_init__(self) -> None:
        if self.untrusted is not True:
            raise ValueError("unsupported documents must remain marked untrusted")

    @property
    def supported(self) -> bool:
        return False

    @property
    def canonical_url(self) -> str:
        return self.source.canonical_url

    @property
    def citation(self) -> Citation:
        return self.source.citation()

    @property
    def message(self) -> str:
        return self.detail

    def to_dict(self) -> dict[str, Any]:
        return {"kind": KIND_BINARY, "supported": False, "untrusted": True,
                "media_type": self.media_type, "reason": self.reason,
                "detail": self.detail,
                "canonical_url": self.canonical_url}


def _normalize_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in value.replace("\x00", " ").splitlines()]
    return "\n".join(line for line in lines if line).strip()


class _HTMLExtractor(HTMLParser):
    """Collect structured blocks from an HTML document without executing it."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.metadata: dict[str, str] = {}
        self.headings: list[Heading] = []
        self.paragraphs: list[str] = []
        self.lists: list[ListBlock] = []
        self.code_blocks: list[CodeBlock] = []
        self.links: list[Link] = []
        self.tables: list[Table] = []
        self.removed: list[str] = []
        self._skip_depth = 0
        self._mode: str | None = None
        self._buffer: list[str] = []
        self._heading_level = 0
        self._title_mode = False
        self._code_buffer: list[str] = []
        self._code_language = ""
        self._inside_code = False
        self._list_stack: list[dict[str, Any]] = []
        self._table_rows: list[tuple[str, ...]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._cell_header = False
        self._table_has_header = False
        self._link_href: str | None = None
        self._link_parts: list[str] = []

    # -- helpers ---------------------------------------------------------
    def _flush(self) -> None:
        if self._mode == "heading":
            text = _normalize_text("".join(self._buffer))
            if text:
                self.headings.append(Heading(self._heading_level, text))
        elif self._mode == "paragraph":
            text = _normalize_text("".join(self._buffer))
            if text:
                self.paragraphs.append(text)
        elif self._mode == "list_item":
            text = _normalize_text("".join(self._buffer))
            if text:
                self._append_list_item(text)
        elif self._mode == "cell":
            text = _normalize_text("".join(self._buffer))
            if self._cell is not None:
                self._cell.append(text)
        elif self._mode == "code":
            text = "".join(self._code_buffer).strip("\n")
            if text.strip():
                self.code_blocks.append(CodeBlock(text.rstrip(),
                                                  self._code_language.strip().lower()))
        self._mode = None
        self._buffer = []
        self._heading_level = 0
        self._code_buffer = []
        self._code_language = ""
        self._inside_code = False

    def _append_list_item(self, text: str) -> None:
        if not self._list_stack:
            self._list_stack.append({"ordered": False, "items": []})
        self._list_stack[-1]["items"].append(text)

    def _close_list(self) -> None:
        if not self._list_stack:
            return
        context = self._list_stack.pop()
        if context["items"]:
            self.lists.append(ListBlock(bool(context["ordered"]),
                                        tuple(context["items"])))

    def _append_text(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._title_mode:
            self.title_parts.append(data)
            return
        if self._mode == "code":
            self._code_buffer.append(data)
            return
        if self._link_href is not None:
            self._link_parts.append(data)
        if self._mode in ("heading", "paragraph", "list_item", "cell"):
            self._buffer.append(data)
            return
        if data.strip():
            self._mode = "paragraph"
            self._buffer.append(data)

    # -- HTMLParser callbacks -------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {name.lower(): value for name, value in attrs if name}
        if tag in SKIPPED_TAGS:
            if self._skip_depth == 0 and tag not in self.removed:
                self.removed.append(tag)
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if tag == "title":
            self._title_mode = True
            self.title_parts = []
            return
        if tag == "meta":
            name = (attributes.get("name") or attributes.get("property") or "").strip().lower()
            content = (attributes.get("content") or "").strip()
            if name and content:
                self.metadata[name] = content[:2000]
            return
        if tag in HEADING_TAGS:
            self._flush()
            self._mode = "heading"
            self._heading_level = HEADING_TAGS[tag]
            return
        if tag == "p":
            self._flush()
            self._mode = "paragraph"
            return
        if tag == "br":
            if self._mode in ("heading", "paragraph", "list_item"):
                self._buffer.append("\n")
            elif self._mode == "code":
                self._code_buffer.append("\n")
            return
        if tag in ("ul", "ol"):
            self._flush()
            self._list_stack.append({"ordered": tag == "ol", "items": []})
            return
        if tag == "li":
            self._flush()
            self._mode = "list_item"
            return
        if tag == "pre":
            self._flush()
            self._mode = "code"
            self._inside_code = True
            return
        if tag == "code":
            css_class = attributes.get("class") or ""
            language = ""
            for token in css_class.split():
                if token.startswith("language-"):
                    language = token[len("language-"):]
                elif token.startswith("lang-"):
                    language = token[len("lang-"):]
            if self._mode == "code":
                if language and not self._code_language:
                    self._code_language = language
            else:
                self._inside_code = True
            return
        if tag == "table":
            self._flush()
            self._table_rows = []
            self._table_has_header = False
            return
        if tag == "tr":
            if self._cell is not None:
                self._finish_cell()
            if self._table_rows is None:
                self._table_rows = []
            self._row = []
            return
        if tag in ("td", "th"):
            if self._cell is not None:
                self._finish_cell()
            if self._row is None:
                self._row = []
            self._cell = []
            self._cell_header = tag == "th"
            self._mode = "cell"
            return
        if tag == "a":
            href = (attributes.get("href") or "").strip()
            self._link_href = href or None
            self._link_parts = []
            return
        if tag in ("img",):
            alt = (attributes.get("alt") or "").strip()
            if alt:
                self._append_text(alt)
            return
        if tag in BLOCK_TAGS:
            self._flush()
            return

    def handle_startendtag(self, tag: str,
                           attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIPPED_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if tag == "title":
            self._title_mode = False
            return
        if tag == "a":
            self._finish_link()
            return
        if tag in HEADING_TAGS:
            self._flush()
            return
        if tag == "p":
            self._flush()
            return
        if tag in ("ul", "ol"):
            self._flush()
            self._close_list()
            return
        if tag == "li":
            self._flush()
            return
        if tag == "pre":
            self._flush()
            return
        if tag == "code":
            self._inside_code = False
            return
        if tag in ("td", "th"):
            self._finish_cell()
            return
        if tag == "tr":
            if self._cell is not None:
                self._finish_cell()
            if self._row is not None and self._table_rows is not None:
                if self._row:
                    self._table_rows.append(tuple(self._row))
            self._row = None
            return
        if tag == "table":
            if self._table_rows is not None:
                if self._table_rows:
                    self.tables.append(Table(tuple(self._table_rows),
                                             self._table_has_header))
            self._table_rows = None
            self._row = None
            self._cell = None
            return
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        self._append_text(data)

    def _finish_cell(self) -> None:
        self._flush()
        if self._cell is not None and self._row is not None:
            text = " ".join(self._cell).strip()
            self._row.append(text)
            if self._cell_header and text:
                self._table_has_header = True
        self._cell = None
        self._cell_header = False

    def _finish_link(self) -> None:
        if self._link_href is None:
            return
        text = _normalize_text("".join(self._link_parts)) or self._link_href
        href = self._link_href.strip()
        self._link_href = None
        self._link_parts = []
        if not href or href.startswith("#"):
            return
        if href.lower().startswith(("javascript:", "data:", "vbscript:")):
            if "unsafe-link" not in self.removed:
                self.removed.append("unsafe-link")
            return
        url = urljoin(self.base_url, href)
        try:
            scheme = urlsplit(url).scheme.lower()
        except ValueError:
            return
        if scheme not in ("http", "https"):
            return
        if len(self.links) >= MAX_LINKS:
            return
        self.links.append(Link(text=text[:500], url=url))


def _markdown_escape_table_cell(value: str) -> str:
    return value.replace("|", chr(92) + "|").replace("\n", " ")


def _build_text(title: str, headings: list[Heading], paragraphs: list[str],
                lists: list[ListBlock], code_blocks: list[CodeBlock],
                tables: list[Table]) -> str:
    parts: list[str] = []
    if title:
        parts.append(title)
    current_heading_anchor = 0
    for heading in headings:
        parts.append(heading.text)
        current_heading_anchor += 1
    parts.extend(paragraphs)
    for block in lists:
        for item in block.items:
            parts.append(("- " if not block.ordered else "- ") + item)
    for code in code_blocks:
        fence = chr(96) * 3
        parts.append(fence + code.language + chr(10) + code.text + chr(10) + fence)
    for table in tables:
        for row in table.rows:
            parts.append(" | ".join(row))
    return "\n\n".join(part for part in parts if part).strip()


def _build_markdown(title: str, headings: list[Heading], paragraphs: list[str],
                    lists: list[ListBlock], code_blocks: list[CodeBlock],
                    links: list[Link], tables: list[Table]) -> str:
    parts: list[str] = []
    if title:
        parts.append("# " + title)
    for heading in headings:
        parts.append("#" * max(1, min(6, heading.level)) + " " + heading.text)
    parts.extend(paragraphs)
    for block in lists:
        marker = "1. " if block.ordered else "- "
        lines = [marker + item for item in block.items]
        parts.append("\n".join(lines))
    for code in code_blocks:
        fence = chr(96) * 3
        parts.append(fence + code.language + chr(10) + code.text + chr(10) + fence)
    for table in tables:
        rows = [[_markdown_escape_table_cell(cell) for cell in row]
                for row in table.rows]
        if not rows:
            continue
        width = max(len(row) for row in rows)
        padded = [row + [""] * (width - len(row)) for row in rows]
        header = padded[0]
        lines = ["| " + " | ".join(header) + " |",
                 "| " + " | ".join(["---"] * width) + " |"]
        for row in padded[1:]:
            lines.append("| " + " | ".join(row) + " |")
        parts.append("\n".join(lines))
    if links:
        parts.append("## Links")
        parts.append("\n".join("- [" + item.text.replace("]", chr(92) + "]")
                               + "](" + item.url + ")" for item in links))
    return "\n\n".join(part for part in parts if part).strip()


def _truncate(value: str) -> tuple[str, bool]:
    if len(value) <= MAX_TEXT_CHARS:
        return value, False
    return value[:MAX_TEXT_CHARS].rstrip() + "\n\n[truncated]", True


def read_document(document: RetrievedDocument) -> ReadablePage | UnsupportedDocument:
    """Read one retrieved document with stdlib-only extraction."""
    if not isinstance(document, RetrievedDocument):
        raise TypeError("read_document requires a RetrievedDocument")
    media_type = document.media_type
    if media_type in _PDF_TYPES or media_type in _OFFICE_TYPES:
        return UnsupportedDocument(
            source=document.source, media_type=media_type,
            reason="unsupported_document_format",
            detail=("PDF/Office extraction is not supported by the research "
                    "foundation; this increment does not download conversion "
                    "libraries, execute macros or run any external converter."))
    if media_type in ("text/html", "application/xhtml+xml") or document.kind == KIND_HTML:
        base_url = document.source.final_url or document.source.canonical_url
        parser = _HTMLExtractor(base_url)
        try:
            parser.feed(document.content)
            parser.close()
        except Exception as exc:
            return UnsupportedDocument(
                source=document.source, media_type=media_type or "text/html",
                reason="html_parse_error",
                detail="HTML parser failed closed: " + type(exc).__name__)
        title = _normalize_text("".join(parser.title_parts))
        if not title:
            title = _normalize_text(parser.metadata.get("og:title", ""))
        if not title:
            title = _normalize_text(parser.metadata.get("twitter:title", ""))
        if not title and parser.headings:
            title = parser.headings[0].text
        metadata = freeze_metadata(parser.metadata)
        source = document.source.with_site_metadata(metadata, title=title)
        text = _build_text(title, parser.headings, parser.paragraphs,
                           parser.lists, parser.code_blocks, parser.tables)
        markdown = _build_markdown(title, parser.headings, parser.paragraphs,
                                   parser.lists, parser.code_blocks, parser.links,
                                   parser.tables)
        text, text_truncated = _truncate(text)
        markdown, markdown_truncated = _truncate(markdown)
        return ReadablePage(
            source=source, title=title, metadata=metadata, text=text,
            markdown=markdown, headings=tuple(parser.headings),
            paragraphs=tuple(parser.paragraphs), lists=tuple(parser.lists),
            code_blocks=tuple(parser.code_blocks), links=tuple(parser.links),
            tables=tuple(parser.tables), removed=tuple(parser.removed),
            untrusted=True, truncated=bool(text_truncated or markdown_truncated),
            kind=KIND_HTML)
    if media_type in ("text/plain", "text/markdown", "text/x-markdown",
                      "application/json") or media_type.endswith("+json"):
        if media_type == "application/json" or media_type.endswith("+json"):
            try:
                json.loads(document.content)
            except (ValueError, TypeError):
                return UnsupportedDocument(
                    source=document.source, media_type=media_type,
                    reason="invalid_json",
                    detail="JSON content is not valid JSON; refusing to treat it as readable data.")
            kind = KIND_JSON
        else:
            kind = KIND_MARKDOWN if "markdown" in media_type else KIND_TEXT
        text, truncated = _truncate(document.content)
        markdown = text if kind == KIND_MARKDOWN else text
        return ReadablePage(
            source=document.source, title=document.title,
            metadata=document.source.metadata, text=text, markdown=markdown,
            untrusted=True, truncated=truncated, kind=kind)
    return UnsupportedDocument(
        source=document.source, media_type=media_type,
        reason="unsupported_media_type",
        detail=("media type " + (media_type or "<missing>")
                + " is not supported by the research foundation reader"))

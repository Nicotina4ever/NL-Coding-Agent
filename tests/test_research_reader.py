"""Reader tests: stdlib HTML parsing with local fixtures, no network/model/GUI.

The reader is fed RetrievedDocument objects built locally; nothing is fetched,
no script is executed and no third-party parser is imported.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from nl_coding_agent.research import reader as r
from nl_coding_agent.research.models import (
    KIND_HTML,
    KIND_JSON,
    KIND_MARKDOWN,
    KIND_TEXT,
    Provenance,
    RetrievedDocument,
    Source,
    sha256_hex,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
READER_SOURCE = REPO_ROOT / "nl_coding_agent" / "research" / "reader.py"
URL = "https://example.com/docs/page"
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
FENCE = chr(96) * 3

HTML = """<!doctype html>
<html><head><title>Example &amp; Docs</title>
<meta name="description" content="A test page">
<meta property="og:site_name" content="Example">
<script>window.secret = "IGNORE_SCRIPT";</script>
<style>.x{display:none}</style>
</head><body>
<h1>Main heading</h1>
<h2>Install</h2>
<p>Hello <strong>world</strong> and <code>inline</code>.</p>
<ul><li>One</li><li>Two</li></ul>
<ol><li>First</li></ol>
<pre><code class="language-python">print("hi")</code></pre>
<p><a href="/relative?q=1">relative link</a> and <a href="https://other.example/x">external</a></p>
<a href="javascript:alert(1)">bad</a>
<table><tr><th>Name</th><th>Value</th></tr><tr><td>a</td><td>b</td></tr></table>
<iframe src="https://evil.example/">IGNORE_IFRAME</iframe>
</body></html>"""


def make_document(content: str, content_type: str = "text/html; charset=utf-8",
                  url: str = URL) -> RetrievedDocument:
    body = content.encode("utf-8")
    provenance = Provenance(
        requested_url=url, canonical_url=url, final_url=url,
        redirect_chain=(url,), fetched_at=NOW,
        content_type=content_type.split(";", 1)[0].strip(),
        charset="utf-8", sha256=sha256_hex(body), size=len(body), status_code=200)
    return RetrievedDocument(source=Source(provenance=provenance), content=content,
                             kind=KIND_HTML if "html" in content_type else KIND_TEXT)


def test_html_fixture_title_metadata_and_structure():
    page = r.read_document(make_document(HTML))
    assert isinstance(page, r.ReadablePage)
    assert page.title == "Example & Docs"
    assert page.source.title == "Example & Docs"
    assert page.metadata_dict()["description"] == "A test page"
    assert page.metadata_dict()["og:site_name"] == "Example"
    assert [item.text for item in page.headings] == ["Main heading", "Install"]
    assert [item.level for item in page.headings] == [1, 2]
    assert page.paragraphs[0] == "Hello world and inline."
    assert page.lists[0].ordered is False
    assert page.lists[0].items == ("One", "Two")
    assert page.lists[1].ordered is True
    assert page.lists[1].items == ("First",)
    assert page.code_blocks == (r.CodeBlock('print("hi")', "python"),)
    assert page.tables == (r.Table((("Name", "Value"), ("a", "b")), True),)
    assert page.untrusted is True
    assert page.citation.url == URL
    assert page.citation.sha256 == page.source.sha256


def test_html_links_are_resolved_and_unsafe_links_are_not_preserved():
    page = r.read_document(make_document(HTML))
    urls = [item.url for item in page.links]
    assert "https://example.com/relative?q=1" in urls
    assert "https://other.example/x" in urls
    assert all(not url.lower().startswith("javascript:") for url in urls)
    assert "unsafe-link" in page.removed


def test_script_style_and_iframe_content_is_dropped_and_never_executed():
    page = r.read_document(make_document(HTML))
    for forbidden in ("IGNORE_SCRIPT", "IGNORE_IFRAME", "window.secret", ".x{display"):
        assert forbidden not in page.text
        assert forbidden not in page.markdown
    for tag in ("script", "style", "iframe"):
        assert tag in page.removed
    assert "bad" in page.text
    assert "javascript:" not in page.markdown


def test_markdown_contains_headings_code_links_and_tables():
    page = r.read_document(make_document(HTML))
    markdown = page.markdown
    assert "# Example & Docs" in markdown
    assert "# Main heading" in markdown
    assert "## Install" in markdown
    assert FENCE + "python" in markdown
    assert 'print("hi")' in markdown
    assert "[relative link](https://example.com/relative?q=1)" in markdown
    assert "| Name | Value |" in markdown
    assert "| a | b |" in markdown


def test_plain_text_markdown_and_json_are_passthrough():
    plain = "line one\nline two\n"
    page = r.read_document(make_document(plain, "text/plain; charset=utf-8"))
    assert isinstance(page, r.ReadablePage)
    assert page.kind == KIND_TEXT
    assert page.text == plain
    assert page.markdown == plain

    markdown = "# Title\n\n- one\n- two\n"
    md_page = r.read_document(make_document(markdown, "text/markdown; charset=utf-8"))
    assert md_page.kind == KIND_MARKDOWN
    assert md_page.text == markdown
    assert md_page.markdown == markdown

    json_text = '{"a": 1, "b": [2, 3]}'
    json_page = r.read_document(make_document(json_text, "application/json"))
    assert json_page.kind == KIND_JSON
    assert json_page.text == json_text
    assert json_page.markdown == json_text


def test_invalid_json_fails_closed_with_unsupported_result():
    result = r.read_document(make_document("{not json", "application/json"))
    assert isinstance(result, r.UnsupportedDocument)
    assert result.reason == "invalid_json"
    assert result.supported is False
    assert result.citation.url == URL


@pytest.mark.parametrize("media_type", [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
])
def test_pdf_and_office_formats_fail_closed_with_clear_result(media_type):
    document = make_document("%PDF-1.7 fake", media_type)
    result = r.read_document(document)
    assert isinstance(result, r.UnsupportedDocument)
    assert result.supported is False
    assert result.reason == "unsupported_document_format"
    assert "PDF/Office extraction is not supported" in result.message
    assert result.citation.url == URL
    assert result.untrusted is True


def test_unknown_media_type_fails_closed():
    result = r.read_document(make_document("binary", "image/png"))
    assert isinstance(result, r.UnsupportedDocument)
    assert result.reason == "unsupported_media_type"
    assert "image/png" in result.message


def test_title_falls_back_to_og_title_then_first_heading():
    og = make_document('<html><head><meta property="og:title" content="OG title">'
                       '</head><body><p>x</p></body></html>')
    assert r.read_document(og).title == "OG title"
    heading = make_document("<html><body><h2>Only heading</h2><p>x</p></body></html>")
    assert r.read_document(heading).title == "Only heading"


def test_reader_is_deterministic_and_bounded():
    page_a = r.read_document(make_document(HTML))
    page_b = r.read_document(make_document(HTML))
    assert page_a == page_b
    huge = "<html><body><p>" + ("x" * (r.MAX_TEXT_CHARS + 1000)) + "</p></body></html>"
    page = r.read_document(make_document(huge))
    assert page.truncated is True
    assert "[truncated]" in page.text
    assert len(page.text) < r.MAX_TEXT_CHARS + 100


def test_reader_module_uses_stdlib_only_and_never_executes_content():
    source = READER_SOURCE.read_text(encoding="utf-8")
    for forbidden in ("import requests", "import bs4", "from bs4",
                      "import lxml", "import playwright", "exec(", "eval(",
                      "subprocess", "import socket"):
        assert forbidden not in source, forbidden

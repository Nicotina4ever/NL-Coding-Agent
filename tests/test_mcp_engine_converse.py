"""Focused unit tests for the MCP chat bridge argument handling.

The tool itself is exercised over real stdio in ``test_mcp_sdk.py``; these tests
pin the prompt-shaping rules that must run before any model request is made.
"""
from __future__ import annotations

from nl_coding_agent.app.mcp_engine import _attachment_context


def test_empty_or_invalid_attachments_produce_no_context():
    assert _attachment_context([]) == ""
    assert _attachment_context(None) == ""
    assert _attachment_context("not-a-list") == ""
    assert _attachment_context([None, "junk", {"name": "x"}, {"extracted_text": 5}]) == ""
    assert _attachment_context([{"extracted_text": "   \n"}]) == ""


def test_attachment_context_is_framed_as_untrusted():
    context = _attachment_context([{"name": "editor.py", "extracted_text": "print(1)"}])
    assert context.startswith("\n\nUNTRUSTED attachment editor.py:\n")
    assert "print(1)" in context


def test_attachment_context_shares_one_budget_across_items():
    capped = _attachment_context(
        [{"name": "a", "extracted_text": "z" * 80}, {"name": "b", "extracted_text": "q" * 80}],
        budget=100,
    )
    assert capped.count("z") == 80
    assert capped.count("q") == 20
    assert len(capped) < 200


def test_attachment_name_is_bounded():
    context = _attachment_context([{"name": "n" * 500, "extracted_text": "payload"}])
    assert "payload" in context
    assert "n" * 201 not in context

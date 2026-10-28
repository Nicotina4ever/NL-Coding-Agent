"""Tests for deterministic offline requirement/constraint extraction (D2, NL-BP-220)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core import requirement_extraction as re  # noqa: E402
from nl_coding_agent.core.document_corpus import DocumentCorpus  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    _write(root / "README.md", """# Product

## Goals

- Ship an offline tool.

## Requirements

- The system must work offline.
- Users should be able to export reports.

## Constraints

- The product must comply with GDPR.
- Only the owner can approve releases.

## Dependencies

- depends on sqlite3

## Acceptance Criteria

- Done when the test suite passes.
""")
    _write(root / "docs" / "spec.md", """# Specification

## Requirements

- The system must not call the network.
""")
    return root


def _extract(root: Path, **kwargs):
    report = DocumentCorpus().discover_project(root, consent=True)
    return re.extract_requirements(report, **kwargs)


def test_extracts_all_kinds_with_provenance_and_labels(tmp_path):
    report = _extract(_project(tmp_path))
    assert report.items
    kinds = set(report.by_kind)
    for expected in ("objective", "requirement", "constraint", "dependency",
                     "acceptance"):
        assert report.by_kind.get(expected), expected
    requirement = next(item for item in report.by_kind["requirement"]
                       if "must work offline" in item.text)
    assert requirement.explicit is True
    assert requirement.label == "explicit"
    assert 0.7 <= requirement.confidence <= 1.0
    assert requirement.document_id.startswith("doc-")
    assert requirement.source_path == "README.md"
    assert requirement.document_sha256
    assert requirement.excerpt
    assert len(requirement.excerpt_sha256) == 64
    assert requirement.line > 0
    assert requirement.offset >= 0
    assert "Requirements" in requirement.section
    acceptance = report.by_kind["acceptance"][0]
    assert acceptance.explicit is True
    constraint_kinds = {item.constraint_kind for item in report.by_kind["constraint"]}
    assert "legal" in constraint_kinds
    assert any(item.constraint_kind == "owner"
               for item in report.by_kind["constraint"])
    dependency = report.by_kind["dependency"][0]
    assert dependency.dependency_name == "sqlite3"
    inferred = [item for item in report.items if item.label == "inferred"]
    assert inferred
    assert all(item.explicit is False for item in inferred)
    assert all("explicit" in item.to_dict() and "confidence" in item.to_dict()
               for item in report.items)
    assert report.to_dict()["counts"]["items"] == len(report.items)


def test_dedupe_bounds_and_empty_documents(tmp_path):
    root = tmp_path / "dedupe"
    _write(root / "README.md", """# Dupe

## Requirements

- The system must be safe.
- The system must be safe.
""")
    report = _extract(root)
    matching = [item for item in report.items
                if item.text == "The system must be safe."]
    assert len(matching) == 1
    assert report.rejected
    bounded = _extract(root, max_items=1)
    assert len(bounded.items) == 1
    assert bounded.bounded is True
    assert bounded.limitations
    empty = re.extract_requirements({"documents": []})
    assert empty.items == ()
    assert empty.document_count == 0


def test_stable_ids_and_report_hash(tmp_path):
    root = _project(tmp_path)
    report = DocumentCorpus().discover_project(root, consent=True)
    first = re.extract_requirements(report)
    second = re.extract_requirements(report)
    assert first.report_hash == second.report_hash
    assert [item.id for item in first.items] == [item.id for item in second.items]
    assert all(item.id.startswith("req-") for item in first.items)


def test_static_no_network_or_execution_guards():
    source = (REPO_ROOT / "nl_coding_agent" / "core"
              / "requirement_extraction.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("import requests", "from requests", "urllib.request",
                      "import urllib", "import socket", "http.client", "httpx",
                      "subprocess", "os.system(", "eval(", "exec(",
                      "shell=true"):
        assert forbidden not in lowered, forbidden
    assert "never present inferred" in lowered or "inferred" in lowered

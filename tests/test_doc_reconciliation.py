"""Tests for deterministic documentation reconciliation (D2, NL-BP-219)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core import doc_reconciliation as dr  # noqa: E402
from nl_coding_agent.core.document_corpus import DocumentCorpus  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    _write(root / "README.md", """# Product

## Requirements

- The system must use SQLite.
- See `missing/path.py` before deploying.
- Run `definitely-missing-command --now`.

## Dependencies

- requires requests

## Acceptance Criteria

- Done when `tests/missing_test.py` passes.
""")
    _write(root / "AGENTS.md", "# Agents\n\nRules here.\n")
    _write(root / "docs" / "guide.md", "# Guide\n\nUse SQLite.\n")
    _write(root / "docs" / "guide-v2.md", "# Guide v2\n\nUse Postgres.\n")
    _write(root / "docs" / "legacy.md", "# Legacy\n\nDeprecated old guide. See gone/file.md.\n")
    _write(root / "docs" / "spec.md", "# Spec\n\n## Requirements\n\n- The system must not use SQLite.\n")
    _write(root / "src" / "app.py", "print('ok')\n")
    _write(root / "tests" / "test_app.py", "def test_ok(): pass\n")
    _write(root / "requirements.txt", "flask\n")
    return root


def _report(root: Path):
    return DocumentCorpus().discover_project(root, consent=True)


def test_findings_conflicts_stale_obsolete_and_evidence(tmp_path):
    root = _project(tmp_path)
    report = dr.reconcile(_report(root), root)
    categories = set(report.counts)
    assert "stale_document" in categories
    assert "version_conflict" in categories
    assert "obsolete_instruction" in categories
    assert "doc_dependency_mismatch" in categories
    assert "doc_test_mismatch" in categories
    assert "contradictory_requirement" in categories
    assert report.findings
    assert report.coverage["documents"] >= 4
    assert report.coverage["dependencies_available"] >= 1
    assert report.coverage["tests_available"] >= 1
    assert report.report_id.startswith("drr-")
    assert len(report.report_hash) == 64
    conflict = next(item for item in report.findings
                    if item.category == "version_conflict")
    assert conflict.severity == "high"
    assert conflict.counterparts
    assert conflict.documents[0]["path"]
    assert conflict.id.startswith("dr-")
    contradiction = next(item for item in report.findings
                         if item.category == "contradictory_requirement")
    assert contradiction.counterparts
    for finding in report.findings:
        data = finding.to_dict()
        assert data["auto_resolved"] is False and data["executed"] is False
        assert data["documents"] or data["category"] == "missing_documentation"
    assert any("git" in item.lower() for item in report.unknowns)


def test_consistent_docs_do_not_produce_conflict_or_stale_findings(tmp_path):
    root = tmp_path / "consistent"
    _write(root / "README.md", "# Product\n\n## Requirements\n\n- The system must use SQLite.\n")
    _write(root / "docs" / "spec.md", "# Spec\n\n## Requirements\n\n- The system must preserve data.\n")
    _write(root / "src" / "app.py", "print('ok')\n")
    report = dr.reconcile(_report(root), root)
    categories = set(report.counts)
    assert "contradictory_requirement" not in categories
    assert "version_conflict" not in categories
    assert "stale_document" not in categories


def test_missing_documentation_and_unknown_evidence(tmp_path):
    root = tmp_path / "missing"
    _write(root / "docs" / "only.md", "# Only\n\nSee `absent.py`.\n")
    report = dr.reconcile(_report(root), root)
    assert "missing_documentation" in set(report.counts)
    no_root = dr.reconcile(_report(root), None)
    assert no_root.unknowns
    assert no_root.coverage["project_root_supplied"] is False
    assert "path_references_checked" in no_root.coverage


def test_duplicates_are_reported_from_corpus_report(tmp_path):
    root = tmp_path / "dupes"
    _write(root / "README.md", "# Product\n\nDocs.\n")
    _write(root / "docs" / "dup.md", "# Product\n\nDocs.\n")
    corpus = _report(root)
    data = corpus.to_dict()
    data["duplicates"] = [{"sha256": "a" * 64, "path": "docs/dup.md",
                           "duplicate_of": "README.md"}]
    report = dr.reconcile(data, root)
    assert "duplicate_document" in set(report.counts)


def test_git_evidence_stale_and_version_currency(tmp_path):
    root = tmp_path / "gitdoc"
    _write(root / "docs" / "guide.md", "# Guide\n\nOld instructions.\n")
    corpus = _report(root)
    data = corpus.to_dict()
    doc = data["documents"][0]
    doc["git_commit"] = "a" * 40
    report = dr.reconcile(
        {"documents": [doc]}, root,
        git_evidence={"docs/guide.md": ["b" * 40]})
    assert "doc_git_mismatch" in set(report.counts)


def test_report_hash_is_deterministic_and_persistent_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("NL_DATA_DIR", str(tmp_path / "data"))
    root = _project(tmp_path)
    first = dr.reconcile(_report(root), root, persist=True)
    second = dr.reconcile(_report(root), root)
    assert first.report_hash == second.report_hash
    assert first.report_id == second.report_id
    assert first.run_id is not None
    runs = dr.list_reconciliation_runs()
    assert len(runs) == 1
    assert runs[0]["report_hash"] == first.report_hash
    loaded = dr.get_reconciliation_run(first.run_id)
    assert loaded is not None
    assert loaded["report"]["report_id"] == first.report_id
    assert dr.get_reconciliation_run(9999) is None


def test_static_no_network_or_execution_guards():
    source = (REPO_ROOT / "nl_coding_agent" / "core"
              / "doc_reconciliation.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("import requests", "from requests", "urllib.request",
                      "import urllib", "import socket", "http.client", "httpx",
                      "subprocess", "os.system(", "eval(", "exec(",
                      "shell=true"):
        assert forbidden not in lowered, forbidden
    assert "never edits" in lowered

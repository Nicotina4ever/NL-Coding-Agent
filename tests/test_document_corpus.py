"""Document corpus tests: temp fixtures, fake readers/extractors, no network."""
from __future__ import annotations
import io
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from nl_coding_agent.core import document_corpus as dc


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    _write(root / "README.md", "# Project\n\nOverview text.\n\n## Setup\n\nRun it.\n")
    _write(root / "AGENTS.md", "# Agent Rules\n\nRules here.\n")
    _write(root / "docs" / "architecture.md", "# Architecture\n\nComponents.\n")
    _write(root / "docs" / "roadmap.md", "# Roadmap\n\nMilestones.\n")
    _write(root / "docs" / "checklists" / "release.md", "# Release Checklist\n\n- item\n")
    _write(root / "specs" / "spec.md", "# Spec\n\nRequirements.\n")
    _write(root / "config" / "settings.yaml", "key: value\n")
    _write(root / "data" / "secret.md", "# private data\n")
    _write(root / "python" / "lib" / "readme.md", "# runtime\n")
    _write(root / "build" / "out.md", "# build output\n")
    _write(root / ".git" / "config.md", "# git internals\n")
    _write(root / "assets" / "logo.svg", "<svg/>")
    _write(root / "binary.bin", "not-a-doc")
    return root


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   text=True, timeout=30)


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    _write(repo / "docs" / "guide.md", "# Guide\n\nCommitted content.\n")
    _write(repo / "README.md", "# Repo\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs")
    return repo


def test_project_discovery_nested_docs_authority_ignored_dirs_and_untrusted(tmp_path):
    root = _project(tmp_path)
    report = dc.DocumentCorpus().discover(consent=True, project_roots=[root])
    paths = {doc.path for doc in report.documents}
    assert "README.md" in paths
    assert "AGENTS.md" in paths
    assert "docs/architecture.md" in paths
    assert "docs/roadmap.md" in paths
    assert "docs/checklists/release.md" in paths
    assert "specs/spec.md" in paths
    assert "config/settings.yaml" in paths
    assert "data/secret.md" not in paths
    assert "python/lib/readme.md" not in paths
    assert "build/out.md" not in paths
    assert ".git/config.md" not in paths
    assert "assets/logo.svg" not in paths
    assert all(doc.untrusted is True for doc in report.documents)
    assert all(doc.sha256 and doc.size >= 0 and doc.retrieved_at for doc in report.documents)
    readme = next(doc for doc in report.documents if doc.path == "README.md")
    assert readme.title == "Project"
    assert "Setup" in readme.headings
    assert readme.sections
    assert "readme" in readme.authority_candidates
    assert "roadmap" in next(doc for doc in report.documents
                             if doc.path == "docs/roadmap.md").authority_candidates
    assert "checklist" in next(doc for doc in report.documents
                               if doc.path == "docs/checklists/release.md").authority_candidates
    assert "spec" in next(doc for doc in report.documents
                          if doc.path == "specs/spec.md").authority_candidates
    assert report.ok and report.complete
    assert report.to_dict()["untrusted_marker"] == dc.UNTRUSTED_MARKER


def test_consent_is_required_and_explicit_files_dedupe(tmp_path):
    root = _project(tmp_path)
    with pytest.raises(dc.ConsentRequiredError):
        dc.DocumentCorpus().discover(project_roots=[root])
    with pytest.raises(dc.ConsentRequiredError):
        dc.DocumentCorpus().discover_project(root)
    same = tmp_path / "same.txt"
    same.write_text("identical content\n", encoding="utf-8")
    report = dc.DocumentCorpus().discover(consent=True, explicit_files=[root / "README.md", same])
    assert len(report.documents) == 2
    duplicate = dc.DocumentCorpus().discover(
        consent=True, explicit_files=[same, tmp_path / "copy.txt"])
    # copy does not exist -> skipped, not duplicated
    assert any(item["reason"] == "unreadable" for item in duplicate.skipped)
    copy = tmp_path / "copy.txt"
    copy.write_text("identical content\n", encoding="utf-8")
    duplicate = dc.DocumentCorpus().discover(consent=True, explicit_files=[same, copy])
    assert len(duplicate.documents) == 1
    assert len(duplicate.duplicates) == 1
    assert duplicate.duplicates[0]["sha256"] == duplicate.documents[0].sha256


def test_archive_safe_zip_traversal_tar_symlink_and_limits(tmp_path):
    safe = tmp_path / "docs.zip"
    with zipfile.ZipFile(safe, "w") as zf:
        zf.writestr("guide.md", "# Guide\n\nArchive content.\n")
        zf.writestr("notes.txt", "notes\n")
        zf.writestr("image.png", b"\x89PNG")
    report = dc.DocumentCorpus().discover_archive(safe, consent=True)
    assert {doc.path for doc in report.documents} == {"guide.md", "notes.txt"}
    assert all(doc.source_kind == "archive" for doc in report.documents)
    assert all(doc.untrusted for doc in report.documents)

    slip = tmp_path / "slip.zip"
    with zipfile.ZipFile(slip, "w") as zf:
        zf.writestr("../evil.md", "# evil\n")
        zf.writestr("safe.md", "# safe\n")
    report = dc.DocumentCorpus().discover_archive(slip, consent=True)
    assert report.documents == []
    assert any("traversal" in item["reason"] for item in report.skipped)

    tar_path = tmp_path / "docs.tar"
    with tarfile.open(tar_path, "w") as tf:
        data = b"# Tar doc\n"
        info = tarfile.TarInfo("tar.md")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("link.md")
        link.type = tarfile.SYMTYPE
        link.linkname = "tar.md"
        tf.addfile(link)
    report = dc.DocumentCorpus().discover_archive(tar_path, consent=True)
    assert report.documents == []
    assert any("symlink" in item["reason"] for item in report.skipped)

    limits = dc.CorpusLimits(max_archive_files=1)
    report = dc.DocumentCorpus(limits).discover_archive(safe, consent=True)
    assert report.documents == []
    assert any("max-files" in item["reason"] for item in report.skipped)


def test_pdf_office_fail_closed_and_fake_extractor(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    office = tmp_path / "doc.docx"
    office.write_bytes(b"PK\x03\x04 fake")
    unavailable = dc.DocumentCorpus(extractor=lambda data, name, kind: {"ok": False,
                                       "reason": "optional-extractor-unavailable"})
    report = unavailable.discover(consent=True, explicit_files=[pdf, office])
    assert report.documents == []
    assert len(report.skipped) == 2
    assert all("optional-extractor" in item["reason"] for item in report.skipped)

    fake = dc.DocumentCorpus(extractor=lambda data, name, kind: {
        "ok": True, "text": "# Extracted\n\nOptional extractor text.",
        "content_type": "text/plain"})
    report = fake.discover(consent=True, explicit_files=[pdf])
    assert len(report.documents) == 1
    assert report.documents[0].text.startswith("# Extracted")
    assert report.documents[0].title == "Extracted"


def test_git_docs_read_only_ref_and_commit_provenance(tmp_path):
    repo = _git_repo(tmp_path)
    _write(repo / "docs" / "guide.md", "# Guide\n\nUncommitted working change.\n")
    report = dc.DocumentCorpus().discover_git(repo, ref="HEAD", consent=True)
    guide = next(doc for doc in report.documents if doc.path == "docs/guide.md")
    assert guide.source_kind == "git"
    assert guide.git_ref == "HEAD"
    assert len(guide.git_commit) == 40
    assert "Committed content" in guide.text
    assert "Uncommitted" not in guide.text
    assert all(doc.untrusted for doc in report.documents)
    with pytest.raises(dc.ConsentRequiredError):
        dc.DocumentCorpus().discover_git(repo, ref="HEAD")


def test_urls_require_injected_reader_and_never_mark_trusted(tmp_path):
    calls = []

    def reader(url):
        calls.append(url)
        return {"url": url, "title": "Fetched", "content_type": "text/plain",
                "content": "# Fetched\n\nremote text\n"}

    report = dc.DocumentCorpus().discover(
        consent=True, urls=["https://example.invalid/doc"], url_reader=reader)
    assert calls == ["https://example.invalid/doc"]
    assert len(report.documents) == 1
    doc = report.documents[0]
    assert doc.source_kind == "url" and doc.url.endswith("/doc")
    assert doc.untrusted is True and doc.sha256
    missing = dc.DocumentCorpus().discover(
        consent=True, urls=["https://example.invalid/doc"])
    assert missing.documents == []
    assert any(item["reason"] == "url-reader-missing" for item in missing.skipped)
    bad_scheme = dc.DocumentCorpus().discover(
        consent=True, urls=["file:///etc/passwd"], url_reader=reader)
    assert any(item["reason"] == "invalid-url-scheme" for item in bad_scheme.skipped)


def test_bounds_fail_closed_and_oversize_file(tmp_path):
    root = _project(tmp_path)
    limits = dc.CorpusLimits(max_files=1, max_total_bytes=100000)
    report = dc.DocumentCorpus(limits).discover(consent=True, project_roots=[root])
    assert len(report.documents) <= 1
    assert report.bounded is True and report.complete is False
    assert any("max-files-or-total-bytes" in item["reason"] for item in report.skipped)

    big = tmp_path / "big.txt"
    big.write_text("x" * 100, encoding="utf-8")
    report = dc.DocumentCorpus(dc.CorpusLimits(max_file_bytes=10)).discover(
        consent=True, explicit_files=[big])
    assert report.documents == []
    assert any(item["reason"] == "max-file-bytes" for item in report.skipped)


def test_static_no_network_or_content_execution_guards():
    source = (Path(__file__).resolve().parents[1]
              / "nl_coding_agent" / "core" / "document_corpus.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("import requests", "from requests", "urllib.request",
                      "import socket", "http.client", "httpx", "webbrowser",
                      "os.system(", "subprocess.popen(", "eval(", "exec(",
                      "shell=true", "pip install", "git push", "git commit",
                      "download"):
        assert forbidden not in lowered, forbidden
    assert "untrusted" in lowered and "consent" in lowered
    assert "subprocess.run" in lowered

"""Deterministic offline documentation reconciliation on DocumentCorpus (D2).

Read-only analysis of already-ingested untrusted documents. It never edits,
executes, follows, installs or resolves anything; findings are advisory evidence.
Optional run history is persisted in the additive doc_reconciliation_runs table.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from nl_coding_agent.core.requirement_extraction import (
        RequirementExtractor,
        _documents,
        _normalize,
    )
except Exception:  # pragma: no cover - import cycle fallback
    RequirementExtractor = None
    _documents = None
    _normalize = lambda value: str(value or "").strip().lower()

MAX_DOCUMENTS = 500
MAX_FINDINGS = 300
MAX_EXCERPT_CHARS = 400
_COUNTERPART_LIMIT = 10
_BT = chr(96)
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.IGNORECASE)
_PATH_RE = re.compile(
    r"(?<![\w/])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,8})")
_CODE_SPAN_RE = re.compile(_BT + "([^" + _BT + "]+)" + _BT)
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_COMMAND_RE = re.compile(
    r"^\s*(?:[$>]\s*)?([A-Za-z][A-Za-z0-9_.-]{1,40})\b")
_KNOWN_COMMANDS = frozenset({
    "cd", "echo", "mkdir", "rmdir", "rm", "cp", "mv", "cat", "ls", "pwd",
    "python", "python3", "py", "pip", "pytest", "npm", "pnpm", "yarn", "node",
    "git", "docker", "make", "cargo", "go", "dotnet", "java", "javac",
    "powershell", "pwsh", "bash", "sh", "cmd", "curl", "wget",
})
_STALE_PATH_PARTS = frozenset({
    "archive", "archived", "old", "legacy", "deprecated", "obsolete",
    "superseded", "backup", "backups", "draft", "drafts", "stale", "v1",
    "v2", "trash", "attic",
})
_STALE_TEXT_RE = re.compile(
    r"\b(deprecated|obsolete|superseded|legacy|do\s+not\s+use|no\s+longer\s+"
    r"(?:valid|maintained|supported)|out\s+of\s+date)\b", re.IGNORECASE)
_VERSION_TOKEN_RE = re.compile(
    r"(?:[-_.\s]*(?:v|version[-_.\s]*)?\d+(?:\.\d+){0,3}|[-_.\s]*(?:old|legacy|"
    r"deprecated|draft|copy|final|current|new))$", re.IGNORECASE)
_AUTHORITY_ORDER = ("readme", "agents", "spec", "architecture", "roadmap",
                    "checklist")


class DocumentReconciliationError(ValueError):
    code = "doc-reconciliation-error"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", "replace")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _stable_id(category: str, title: str, detail: str, primary: str = "") -> str:
    return "dr-" + _sha("|".join((category, title, detail, primary)))[:16]


def _line_of(text: str, offset: int) -> int:
    offset = max(0, min(int(offset), len(text)))
    return text.count("\n", 0, offset) + 1


def _excerpt(text: str, offset: int, length: int = 180) -> str:
    start = max(0, min(int(offset), len(text)))
    value = re.sub(r"\s+", " ", text[start:start + max(1, int(length))]).strip()
    if len(value) > MAX_EXCERPT_CHARS:
        value = value[:MAX_EXCERPT_CHARS - 15].rstrip() + " [truncated]"
    return value


def _doc_ref(doc: Mapping) -> dict:
    return {"document_id": doc.get("document_id"), "path": doc.get("path"),
            "url": doc.get("url"), "title": doc.get("title"),
            "sha256": doc.get("sha256")}


def _normalized_path(value: str) -> str:
    return str(value or "").replace("\\", "/").lstrip("./").lower()


@dataclass(frozen=True)
class ReconciliationFinding:
    id: str
    category: str
    severity: str
    title: str
    detail: str
    documents: tuple[dict, ...] = ()
    counterparts: tuple[dict, ...] = ()
    excerpt: str = ""
    excerpt_sha256: str = ""
    line: int = 0
    offset: int = 0
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"id": self.id, "category": self.category,
                "severity": self.severity, "title": self.title,
                "detail": self.detail,
                "documents": [dict(item) for item in self.documents],
                "counterparts": [dict(item) for item in self.counterparts],
                "excerpt": self.excerpt,
                "excerpt_sha256": self.excerpt_sha256,
                "line": int(self.line), "offset": int(self.offset),
                "evidence": list(self.evidence),
                "source_document_ids": [item.get("document_id") for item in self.documents],
                "source_paths": [item.get("path") for item in self.documents if item.get("path")],
                "source_urls": [item.get("url") for item in self.documents if item.get("url")],
                "counterpart_ids": [item.get("document_id") for item in self.counterparts],
                "auto_resolved": False, "executed": False}


@dataclass
class ReconciliationReport:
    report_id: str
    report_hash: str
    corpus_hash: str
    findings: tuple[ReconciliationFinding, ...] = ()
    coverage: dict = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    created_at: str = ""
    run_id: int | None = None
    project_ref: str = ""

    @property
    def counts(self) -> dict:
        result = {}
        for finding in self.findings:
            result[finding.category] = result.get(finding.category, 0) + 1
        return dict(sorted(result.items()))

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)

    @property
    def ok(self) -> bool:
        return not self.findings

    @property
    def high_severity(self) -> tuple[ReconciliationFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "high")

    def to_dict(self) -> dict:
        return {"schema_version": 1, "tool": "doc_reconciliation",
                "untrusted_marker": "UNTRUSTED: reconciliation findings are derived evidence",
                "report_id": self.report_id, "report_hash": self.report_hash,
                "content_hash": self.report_hash,
                "corpus_hash": self.corpus_hash, "created_at": self.created_at,
                "run_id": self.run_id, "project_ref": self.project_ref,
                "counts": self.counts, "findings_total": len(self.findings),
                "findings": [item.to_dict() for item in self.findings],
                "coverage": dict(self.coverage),
                "limitations": list(self.limitations),
                "unknowns": list(self.unknowns),
                "auto_resolved": False, "executed": False}


class DocumentReconciler:
    """Read-only deterministic reconciliation between docs and available evidence."""

    def __init__(self, *, max_documents: int = MAX_DOCUMENTS,
                 max_findings: int = MAX_FINDINGS):
        self.max_documents = max(1, min(int(max_documents), MAX_DOCUMENTS))
        self.max_findings = max(1, min(int(max_findings), MAX_FINDINGS))

    def reconcile(self, corpus, project_root=None, *,
                  source_evidence=None, dependency_evidence=None,
                  test_evidence=None, git_evidence=None, persist: bool = False,
                  project_id: int | None = None, project_ref: str = "",
                  db_path=None) -> ReconciliationReport:
        raw = getattr(corpus, "documents", corpus)
        if hasattr(corpus, "documents"):
            docs = _documents(corpus) if _documents else []
            duplicates = list(getattr(corpus, "duplicates", []) or [])
            corpus_complete = bool(getattr(corpus, "complete", True))
            corpus_bounded = bool(getattr(corpus, "bounded", False))
        elif isinstance(corpus, Mapping):
            docs = _documents(corpus) if _documents else []
            duplicates = list(corpus.get("duplicates") or [])
            corpus_complete = bool(corpus.get("complete", True))
            corpus_bounded = bool(corpus.get("bounded", False))
        else:
            docs = _documents(raw) if _documents else []
            duplicates = []
            corpus_complete, corpus_bounded = True, False
        docs = docs[:self.max_documents]
        bounded = len(docs) < len(_documents(corpus)) if _documents else False
        corpus_hash = _sha("|".join(str(doc.get("sha256") or "") for doc in docs))
        findings: list[ReconciliationFinding] = []
        limitations: list[str] = []
        unknowns: list[str] = []
        coverage = {"documents": len(docs), "duplicates": len(duplicates),
                    "corpus_complete": corpus_complete,
                    "corpus_bounded": corpus_bounded,
                    "project_root_supplied": project_root is not None,
                    "source_evidence_supplied": source_evidence is not None,
                    "dependency_evidence_supplied": dependency_evidence is not None,
                    "test_evidence_supplied": test_evidence is not None,
                    "git_evidence_supplied": git_evidence is not None}
        if corpus_bounded or not corpus_complete:
            limitations.append("corpus is bounded/incomplete; reconciliation is partial")
        if not docs:
            unknowns.append("no documents supplied")
            return self._report(findings, coverage, limitations, unknowns,
                                corpus_hash, project_ref, persist, project_id,
                                db_path, bounded, docs)
        root = Path(project_root).expanduser() if project_root else None
        file_paths, file_texts = self._project_files(root, limitations, unknowns)
        deps = self._dependencies(root, dependency_evidence, limitations, unknowns)
        tests = self._tests(root, test_evidence, limitations, unknowns)
        source_paths = self._source_paths(source_evidence, file_paths, root, limitations)
        if git_evidence is None:
            unknowns.append("no Git history evidence supplied; version currency unchecked")
        # duplicate documents from corpus
        for duplicate in duplicates[:100]:
            duplicate_path = str(duplicate.get("path") or
                                 duplicate.get("duplicate_of") or "")
            duplicate_doc = next((doc for doc in docs
                                  if str(doc.get("path") or "") == duplicate_path),
                                 None)
            if duplicate_doc is None:
                duplicate_doc = {"document_id": "doc-" + _sha(duplicate_path)[:16],
                                 "path": duplicate_path or None, "url": None,
                                 "title": Path(duplicate_path).name if duplicate_path else "",
                                 "sha256": str(duplicate.get("sha256") or ""),
                                 "text": ""}
            findings.append(self._finding(
                "duplicate_document", "low", "Duplicate document content",
                "Document content duplicates another source and may diverge.",
                duplicate_doc, excerpt="", counterparts=[],
                evidence=(str(duplicate.get("sha256") or ""),)))
        # stale documents
        authorities = [doc for doc in docs if self._is_authoritative(doc)]
        for doc in docs:
            stale_reason = self._stale_reason(doc)
            if stale_reason:
                findings.append(self._finding(
                    "stale_document", "medium",
                    "Stale or non-authoritative documentation",
                    stale_reason, doc,
                    counterparts=[_doc_ref(a) for a in authorities[:3]]))
        # version conflicts by logical title/path
        groups: dict[str, list[dict]] = {}
        for doc in docs:
            key = self._logical_key(doc)
            groups.setdefault(key, []).append(doc)
        for key, group in groups.items():
            hashes = {doc.get("sha256") for doc in group}
            if len(group) > 1 and len(hashes) > 1:
                primary = group[0]
                findings.append(self._finding(
                    "version_conflict", "high", "Conflicting document versions",
                    "Multiple documents share the same logical identity with "
                    "different content.", primary,
                    counterparts=[_doc_ref(item) for item in group[1:]],
                    evidence=tuple(sorted(str(item.get("sha256") or "")
                                          for item in group))))
        # Extract referenced paths/commands + requirements.
        path_refs = []
        command_refs = []
        bare_path_re = re.compile(r"(?<![\w/])([A-Za-z0-9_.-]+\.(?:md|markdown|py|js|ts|json|ya?ml|toml|txt|sh|ps1|bat|html?))\b", re.IGNORECASE)
        bare_command_re = re.compile(r"\b(?:run|execute|invoke)\s+([A-Za-z][A-Za-z0-9_.-]{2,60})", re.IGNORECASE)
        command_noise = {"the", "this", "that", "tests", "test", "code",
                         "project", "app", "server", "build", "command"}
        for doc in docs:
            text = str(doc.get("text") or "")
            for match in _PATH_RE.finditer(text):
                path_refs.append((doc, match.group(1), match.start()))
            for match in bare_path_re.finditer(text):
                path_refs.append((doc, match.group(1), match.start()))
            for match in bare_command_re.finditer(text):
                command = match.group(1)
                if command.lower() not in command_noise:
                    command_refs.append((doc, command, match.start(), command))
            for match in _CODE_SPAN_RE.finditer(text):
                value = match.group(1).strip()
                if self._looks_like_path(value):
                    path_refs.append((doc, value, match.start()))
                command = _COMMAND_RE.match(value)
                if command and command.group(1) not in ("http", "https"):
                    command_refs.append((doc, value, match.start(), command.group(1)))
        checked_paths = 0
        seen_refs = set()
        for doc, ref, offset in path_refs:
            normalized = _normalized_path(ref)
            if not normalized or normalized in seen_refs:
                continue
            seen_refs.add(normalized)
            if normalized.startswith(("http", "mailto:")):
                continue
            if root is None and source_paths is None:
                unknowns.append("path reference " + ref + ": no project source evidence")
                continue
            checked_paths += 1
            exists = ((root is not None and (root / normalized).exists())
                      or (source_paths is not None and normalized in source_paths))
            if not exists:
                findings.append(self._finding(
                    "obsolete_instruction", "medium",
                    "Referenced path or file is missing",
                    "Documentation references a path/file that does not exist: " + ref,
                    doc, offset=offset, evidence=(normalized,)))
        checked_commands = 0
        for doc, value, offset, command in command_refs:
            checked_commands += 1
            if command in _KNOWN_COMMANDS or shutil.which(command):
                continue
            findings.append(self._finding(
                "obsolete_instruction", "low",
                "Referenced command may be unavailable",
                "Documentation references a command not found on PATH: " + command,
                doc, offset=offset, evidence=(command,)))
        coverage.update({"path_references_checked": checked_paths,
                         "commands_checked": checked_commands,
                         "source_files_available": len(file_paths),
                         "dependencies_available": len(deps),
                         "tests_available": len(tests)})
        # Missing documentation
        if root is not None:
            names = {_normalized_path(Path(str(doc.get("path") or "")).name)
                     for doc in docs if doc.get("path")}
            for expected, label in (("readme.md", "README"),):
                if expected not in names:
                    findings.append(self._finding(
                        "missing_documentation", "low",
                        "Missing " + label + " documentation",
                        "No " + label + " document was found in the corpus.",
                        None, evidence=(expected,)))
            if not any(str(doc.get("path") or "").lower().startswith(("docs/", "doc/"))
                       for doc in docs):
                findings.append(self._finding(
                    "missing_documentation", "low",
                    "Missing docs directory documentation",
                    "No docs/ document was found in the corpus.", None))
        # Contradictory requirements from extracted items.
        extraction = (RequirementExtractor().extract({"documents": docs})
                      if RequirementExtractor else None)
        if extraction is not None:
            findings.extend(self._contradictions(extraction, docs))
            dep_items = [item for item in extraction.items
                         if item.kind == "dependency" and item.dependency_name]
            for item in dep_items[:50]:
                name = item.dependency_name.lower().split("/")[0]
                if deps and name not in deps and root is not None:
                    doc = next((d for d in docs if d.get("document_id") ==
                                item.document_id), None)
                    findings.append(self._finding(
                        "doc_dependency_mismatch", "low",
                        "Documented dependency is not declared",
                        "Documentation declares dependency not found in manifests: " + name,
                        doc, offset=item.offset, evidence=(name,)))
        # Test/document references
        test_paths = {_normalized_path(item) for item in tests}
        for doc, ref, offset in path_refs:
            normalized = _normalized_path(ref)
            if not normalized.startswith(("tests/", "test_", "spec/")):
                continue
            if test_paths and normalized not in test_paths:
                findings.append(self._finding(
                    "doc_test_mismatch", "medium",
                    "Documented test path is missing",
                    "Documentation references a test path not present in test evidence: "
                    + ref, doc, offset=offset, evidence=(normalized,)))
        # Git evidence: doc commit currency.
        if git_evidence is not None and docs:
            history = self._git_history(git_evidence, limitations, unknowns)
            if history:
                for doc in docs:
                    path = _normalized_path(doc.get("path") or "")
                    commits = history.get(path) or history.get("*") or []
                    commits = [str(item) for item in commits]
                    if commits and doc.get("git_commit") and str(
                            doc.get("git_commit")) not in commits:
                        findings.append(self._finding(
                            "doc_git_mismatch", "medium",
                            "Document may be stale against Git history",
                            "Document commit is not in supplied Git history for " + path,
                            doc, evidence=tuple(commits[:3])))
        # deterministic bounded findings
        unique = {}
        for finding in findings:
            unique.setdefault(finding.id, finding)
        findings = sorted(unique.values(), key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item.severity, 9),
            item.category, item.documents[0].get("path") if item.documents else "",
            item.id))
        if len(findings) > self.max_findings:
            bounded = True
            findings = findings[:self.max_findings]
            limitations.append("finding cap reached; report truncated")
        if extraction is not None:
            coverage["requirements_items"] = len(extraction.items)
            coverage["requirements_explicit"] = extraction.explicit_count
        return self._report(findings, coverage, limitations, unknowns,
                            corpus_hash, project_ref, persist, project_id,
                            db_path, bounded, docs)

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _is_authoritative(doc) -> bool:
        candidates = [str(item).lower() for item in
                      (doc.get("authority_candidates") or ())]
        return any(item in _AUTHORITY_ORDER for item in candidates) and not \
            any(part in _STALE_PATH_PARTS for part in
                _normalized_path(doc.get("path") or "").split("/"))

    @staticmethod
    def _stale_reason(doc) -> str:
        path = _normalized_path(doc.get("path") or "")
        parts = set(path.split("/"))
        stale_parts = sorted(parts & _STALE_PATH_PARTS)
        text = str(doc.get("text") or "")
        match = _STALE_TEXT_RE.search(text)
        candidates = [str(item).lower() for item in
                      (doc.get("authority_candidates") or ())]
        if stale_parts:
            return "path indicates a stale/archived document: " + ", ".join(stale_parts)
        if match:
            return "content marks itself as stale: " + match.group(0)
        return ""

    @staticmethod
    def _logical_key(doc) -> str:
        raw = str(doc.get("path") or doc.get("title") or "")
        name = raw.replace("\\", "/").rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0].lower()
        stem = re.sub(r"[-_.\s]+", "-", stem).strip("-")
        return _VERSION_TOKEN_RE.sub("", stem).strip("-") or stem

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        value = str(value).strip()
        if not value or " " in value or value.startswith(("http://", "https://")):
            return False
        return "/" in value or bool(re.search(
            r"\.(md|markdown|txt|rst|py|js|ts|json|ya?ml|toml|cfg|ini|sh|ps1|bat|env|html?)$",
            value, re.IGNORECASE))

    def _finding(self, category, severity, title, detail, doc, *,
                 counterparts=None, excerpt=None, offset=0,
                 evidence=()) -> ReconciliationFinding:
        doc = doc or {}
        text = str(doc.get("text") or "")
        excerpt_value = (excerpt if excerpt is not None else
                         _excerpt(text, offset) if text else "")
        documents = (_doc_ref(doc),) if doc else ()
        counterpart_values = tuple(counterparts or ())
        primary = str(doc.get("document_id") or doc.get("path") or "")
        finding_id = _stable_id(category, title, detail, primary)
        return ReconciliationFinding(
            id=finding_id, category=category, severity=severity,
            title=title, detail=detail, documents=documents,
            counterparts=counterpart_values[: _COUNTERPART_LIMIT],
            excerpt=excerpt_value, excerpt_sha256=_sha(excerpt_value),
            line=_line_of(text, offset) if text else 0, offset=int(offset),
            evidence=tuple(str(item) for item in evidence[:20]))

    @staticmethod
    def _project_files(root, limitations, unknowns):
        paths = set()
        texts = {}
        if root is None:
            return paths, texts
        if not root.exists() or not root.is_dir():
            unknowns.append("project root does not exist")
            return paths, texts
        count = 0
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(name for name in dirnames
                                 if name.lower() not in {
                                     ".git", ".hg", ".svn", ".workspace", "build",
                                     "dist", "node_modules", "python", "data",
                                     "__pycache__", ".pytest_cache"})
            for filename in sorted(filenames)[:1000]:
                path = Path(dirpath) / filename
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                except OSError:
                    continue
                rel = _normalized_path(path.relative_to(root).as_posix())
                paths.add(rel)
                count += 1
                if count > 5000:
                    limitations.append("project file walk capped at 5000 files")
                    return paths, texts
        return paths, texts

    @staticmethod
    def _source_paths(source_evidence, file_paths, root, limitations):
        if source_evidence is None:
            return None
        if isinstance(source_evidence, Mapping):
            values = source_evidence.get("paths") or source_evidence.get("files")
        else:
            values = source_evidence
        if values is None:
            limitations.append("source evidence supplied without paths")
            return None
        return {_normalized_path(item) for item in values or ()}

    @staticmethod
    def _dependencies(root, dependency_evidence, limitations, unknowns):
        names = set()
        if dependency_evidence is not None:
            if isinstance(dependency_evidence, Mapping):
                values = (dependency_evidence.get("declared") or
                          dependency_evidence.get("dependencies") or
                          dependency_evidence.get("names") or [])
                if not values:
                    limitations.append("dependency evidence supplied without names")
            else:
                values = dependency_evidence
            names.update(str(item).strip().lower() for item in values or () if item)
            return names
        if root is None:
            unknowns.append("no dependency evidence or project root supplied")
            return names
        manifest = root / "requirements.txt"
        if manifest.is_file():
            try:
                for line in manifest.read_text(encoding="utf-8",
                                               errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        names.add(re.split(r"[<>=!~\[\s]", line, 1)[0].lower())
            except OSError as exc:
                limitations.append("requirements manifest unreadable: " + str(exc))
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r'^\s*["\']?([A-Za-z0-9_.-]+)["\']?\s*[<>=!~]', 
                                         text, re.MULTILINE):
                    names.add(match.group(1).lower())
            except OSError:
                pass
        if not names:
            unknowns.append("dependency evidence unavailable")
        return names

    @staticmethod
    def _tests(root, test_evidence, limitations, unknowns):
        paths = set()
        if test_evidence is not None:
            if isinstance(test_evidence, Mapping):
                values = test_evidence.get("paths") or test_evidence.get("files") or []
            else:
                values = test_evidence
            paths.update(_normalized_path(item) for item in values or ())
            return paths
        if root is None:
            unknowns.append("no test evidence or project root supplied")
            return paths
        tests_root = root / "tests"
        if tests_root.is_dir():
            for path in sorted(tests_root.rglob("test_*.py"))[:1000]:
                try:
                    paths.add(_normalized_path(path.relative_to(root).as_posix()))
                except ValueError:
                    continue
        if not paths:
            unknowns.append("test evidence unavailable")
        return paths

    @staticmethod
    def _git_history(git_evidence, limitations, unknowns):
        if isinstance(git_evidence, Mapping):
            raw = git_evidence.get("paths") or git_evidence.get("history")
            if raw is None and not any(key in git_evidence for key in
                                       ("paths", "history", "commits")):
                raw = git_evidence
            if isinstance(raw, Mapping):
                result = {}
                for path, commits in raw.items():
                    if isinstance(commits, Mapping):
                        commits = commits.get("commits") or []
                    result[_normalized_path(path)] = list(commits or ())
                return result
            if isinstance(raw, Mapping) is False and raw is not None:
                return {"*": list(raw)}
            unknowns.append("git evidence supplied in unsupported shape")
            return {}
        if isinstance(git_evidence, (list, tuple)):
            return {"*": list(git_evidence)}
        limitations.append("git evidence supplied in unsupported shape")
        return {}

    def _contradictions(self, extraction, docs):
        findings = []
        by_doc = {doc.get("document_id"): doc for doc in docs}
        items = [item for item in extraction.items
                 if item.kind in ("requirement", "constraint")]
        negatives = []
        positives = []
        for item in items:
            lowered = item.text.lower()
            negated = bool(re.search(r"\b(must\s+not|shall\s+not|not\s+allowed|"
                                     r"prohibited|never|no\s+longer|do\s+not)\b",
                                     lowered))
            base = re.sub(r"\b(must\s+not|shall\s+not|must|shall|should|required|"
                          r"not\s+allowed|prohibited|never|no\s+longer|do\s+not)\b",
                          " ", lowered)
            base = re.sub(r"\s+", " ", base).strip()
            tokens = set(re.findall(r"[a-z0-9_]+", base))
            if len(tokens) < 2:
                continue
            (negatives if negated else positives).append((item, tokens))
        for neg_item, neg_tokens in negatives:
            for pos_item, pos_tokens in positives:
                overlap = len(neg_tokens & pos_tokens) / max(
                    len(neg_tokens | pos_tokens), 1)
                if overlap < 0.6:
                    continue
                doc = by_doc.get(neg_item.document_id)
                counterpart_doc = by_doc.get(pos_item.document_id)
                counterparts = ([_doc_ref(counterpart_doc)]
                                if counterpart_doc else [])
                findings.append(self._finding(
                    "contradictory_requirement", "high",
                    "Contradictory requirement",
                    "One document requires a behavior another document forbids.",
                    doc, counterparts=counterparts,
                    offset=neg_item.offset,
                    evidence=(neg_item.id, pos_item.id)))
                if len(findings) >= _COUNTERPART_LIMIT:
                    return findings
        return findings

    def _report(self, findings, coverage, limitations, unknowns, corpus_hash,
                project_ref, persist, project_id, db_path, bounded, docs):
        if bounded:
            coverage["bounded"] = True
        payload = {"corpus_hash": corpus_hash,
                   "findings": [item.to_dict() for item in findings],
                   "coverage": coverage,
                   "limitations": sorted(set(limitations)),
                   "unknowns": sorted(set(unknowns))}
        report_hash = _sha(_canonical(payload))
        report_id = "drr-" + report_hash[:16]
        report = ReconciliationReport(
            report_id=report_id, report_hash=report_hash,
            corpus_hash=corpus_hash, findings=tuple(findings),
            coverage=dict(coverage),
            limitations=tuple(sorted(set(limitations))),
            unknowns=tuple(sorted(set(unknowns))),
            created_at=_now(), project_ref=str(project_ref or ""))
        if persist:
            report.run_id = save_reconciliation_run(
                report, project_id=project_id, project_ref=project_ref,
                db_path=db_path)
        return report


def _connect(db_path=None):
    from nl_coding_agent.persistence.database import init_db
    return init_db(Path(db_path) if db_path else None)


def save_reconciliation_run(report: ReconciliationReport, *,
                            project_id: int | None = None,
                            project_ref: str = "",
                            db_path=None) -> int:
    payload = report.to_dict()
    payload["run_id"] = None
    conn = _connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO doc_reconciliation_runs (project_id, project_ref, "
                "corpus_hash, report_hash, report_json, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (int(project_id) if project_id is not None else None,
                 str(project_ref or report.project_ref or ""),
                 report.corpus_hash, report.report_hash,
                 json.dumps(payload, ensure_ascii=False, sort_keys=True),
                 report.created_at or _now()))
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_reconciliation_runs(*, project_id: int | None = None,
                             limit: int = 50, db_path=None) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    query = "SELECT * FROM doc_reconciliation_runs"
    params = []
    if project_id is not None:
        query += " WHERE project_id=?"
        params.append(int(project_id))
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    conn = _connect(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
        return [_run_from_row(row) for row in rows]
    finally:
        conn.close()


def get_reconciliation_run(run_id: int, *, db_path=None) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM doc_reconciliation_runs WHERE id=?",
                           (int(run_id),)).fetchone()
        return _run_from_row(row) if row else None
    finally:
        conn.close()


def _run_from_row(row) -> dict:
    data = dict(row)
    try:
        data["report"] = json.loads(data.pop("report_json") or "{}")
    except (TypeError, ValueError):
        data["report"] = {}
    return data


def reconcile(corpus, project_root=None, **kwargs) -> ReconciliationReport:
    return DocumentReconciler().reconcile(corpus, project_root, **kwargs)

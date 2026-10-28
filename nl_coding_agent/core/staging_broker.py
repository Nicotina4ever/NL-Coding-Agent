"""Fail-closed staging of scoped TEXT edits (SPEC-28, source-review patch).

No model-facing tool may write directly to the final project when using this
broker. This protects against accidental tool writes, NOT arbitrary subprocesses
or malicious code executing with the user's OS privileges.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from nl_coding_agent.core.workspace import snapshot_workspace, diff_snapshots, out_of_scope_paths
from nl_coding_agent.core.code_integrity_gate import detect_stub, detect_weak_test
from nl_coding_agent.core.recovery_store import sha256_text, _atomic_write


class StagingRejected(RuntimeError):
    pass


def _workspace(stage_dir: Path) -> Path:
    return stage_dir / "workspace"


def _manifest_path(stage_dir: Path) -> Path:
    return stage_dir / "manifest.json"


def _read(stage_dir: Path) -> dict:
    return json.loads(_manifest_path(stage_dir).read_text(encoding="utf-8"))


def _save(stage_dir: Path, manifest: dict) -> None:
    _atomic_write(_manifest_path(stage_dir), json.dumps(manifest, ensure_ascii=False).encode("utf-8"))


def _safe_path(root: Path, rel: str) -> Path:
    if not rel or Path(rel).is_absolute() or Path(rel).drive or "\\" in rel:
        raise StagingRejected(f"Invalid relative filename: {rel!r}")
    dst = root / rel
    resolved = dst.resolve()
    if not resolved.is_relative_to(root):
        raise StagingRejected(f"Path escapes root: {rel!r}")
    if dst.is_symlink():
        raise StagingRejected(f"Symlink forbidden: {rel!r}")
    return dst


def stage_candidate(project_root: Path | str, mission_id: int, scope_paths: list[str]) -> Path:
    """Create a small source-only workspace; no Python/vendor/model checkpoints."""
    root = Path(project_root).resolve()
    if not scope_paths:
        raise StagingRejected("Missing explicit write scope")
    basedir = root / "data" / "staging"
    basedir.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=f"mission-{mission_id}-", dir=basedir)).resolve()
    sandbox = _workspace(stage_dir)
    sandbox.mkdir(parents=True)
    baseline = snapshot_workspace(root)
    for rel, content in baseline.items():
        src = _safe_path(root, rel)
        if src.is_symlink() or not src.is_file():
            continue
        target = _safe_path(sandbox, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    manifest = {
        "version": 2,
        "project_root": str(root),
        "scope": scope_paths,
        "baseline": baseline,
        "validated": False,
        "verified": False,
        "changed": {},
    }
    _save(stage_dir, manifest)
    return stage_dir


def validate_candidate(stage_dir: Path, baseline_path: Path | str | None = None, scope_paths: list[str] | None = None) -> dict:
    """Validate the staged delta. Never trust candidate tests as the sole oracle."""
    stage_dir = Path(stage_dir).resolve()
    m = _read(stage_dir)
    root = Path(m["project_root"]).resolve()
    scope = scope_paths if scope_paths is not None else m["scope"]
    base = m["baseline"]
    staged = snapshot_workspace(_workspace(stage_dir))
    _, changed = diff_snapshots(base, staged)
    errors: list[str] = []
    not_allowed = out_of_scope_paths(changed, scope)
    if not_allowed:
        errors.append(f"Out-of-scope changes: {not_allowed}")
    forbidden_roots = ("python/", "crewai/", "crewai-tools/", ".git/", "data/", "logs/")
    delta = {}
    for rel in changed:
        if rel.lower().startswith(forbidden_roots):
            errors.append(f"Protected path: {rel}")
            continue
        try:
            _safe_path(root, rel)
            _safe_path(_workspace(stage_dir), rel)
        except StagingRejected as exc:
            errors.append(str(exc))
            continue
        old = base.get(rel)
        new = staged.get(rel)
        if new is None and old is not None:
            errors.append(f"Deletion not permitted by unattended broker: {rel}")
        if rel.endswith((".py", ".pyi")) and new is not None and detect_stub(new, old):
            errors.append(f"Destructive code change or invalid syntax: {rel}")
        if rel.startswith("tests/") and old is not None and new is not None and detect_weak_test(old, new):
            errors.append(f"Weakened test: {rel}")
        delta[rel] = {
            "before": sha256_text(old) if old is not None else None,
            "after": sha256_text(new) if new is not None else None,
        }
    if not changed:
        errors.append("Candidate has no changes")
    m["changed"] = delta
    m["validated"] = not errors
    m["verified"] = False
    _save(stage_dir, m)
    return {"valid": not errors, "errors": errors, "changed_paths": changed,
            "unauthorized": not_allowed, "stub_files": [p for p in changed if any(p in s for s in errors)],
            "weak_tests": [p for p in changed if any(f"Weakened test: {p}" in s for s in errors)]}


def mark_verified(stage_dir: Path, *, passed: bool, evidence: str) -> None:
    """Bind test results to exact validated candidate hashes."""
    m = _read(Path(stage_dir))
    if not m.get("validated") or not passed or not evidence.strip():
        raise StagingRejected("Only independently tested candidates can be marked verified")
    staged = snapshot_workspace(_workspace(Path(stage_dir)))
    for rel, hashes in m["changed"].items():
        actual = sha256_text(staged[rel]) if rel in staged else None
        if actual != hashes["after"]:
            raise StagingRejected(f"Candidate changed after validation: {rel}")
    m["verified"] = True
    m["evidence"] = evidence[:2000]
    _save(Path(stage_dir), m)


def promote_staged(stage_dir: Path, project_root: Path | str) -> dict:
    """Reject changed destination hashes before any write; journal and CAS files.

    File-level os.replace is atomic on the same filesystem. Multi-file changes
    are *recoverable*, not globally atomic; an interrupted journal blocks resume.
    """
    stage_dir = Path(stage_dir).resolve()
    m = _read(stage_dir)
    root = Path(project_root).resolve()
    if root != Path(m["project_root"]).resolve():
        raise StagingRejected("Different project root")
    if not (m.get("validated") and m.get("verified")):
        raise StagingRejected("Unvalidated or untested candidate cannot be promoted")
    if (stage_dir / "promotion-journal.json").exists():
        raise StagingRejected("Existing promotion journal: reconcile before retry")
    staged = snapshot_workspace(_workspace(stage_dir))
    delta = m["changed"]
    if not delta:
        raise StagingRejected("No changes")
    violations = out_of_scope_paths(list(delta), m["scope"])
    if violations:
        raise StagingRejected(f"Out-of-scope promotion denied: {violations}")
    # Full preflight: if someone touched a destination meanwhile, refuse all.
    for rel, hashes in delta.items():
        dest = _safe_path(root, rel)
        candidate = _safe_path(_workspace(stage_dir), rel)
        if not candidate.is_file():
            raise StagingRejected(f"No staged file for {rel}")
        actual = sha256_text(dest.read_text(encoding="utf-8")) if dest.exists() else None
        current_candidate = sha256_text(candidate.read_text(encoding="utf-8"))
        if actual != hashes["before"] or current_candidate != hashes["after"]:
            raise StagingRejected(f"CAS conflict or unvalidated change: {rel}")
    journal = stage_dir / "promotion-journal.json"
    _atomic_write(journal, json.dumps({"project_root": str(root), "changed": delta, "status": "in-progress"}).encode("utf-8"))
    written = []
    try:
        for rel in delta:
            dest = _safe_path(root, rel)
            current = sha256_text(dest.read_text(encoding="utf-8")) if dest.exists() else None
            if current != delta[rel]["before"]:
                raise StagingRejected(f"CAS conflict during promotion: {rel}")
            payload = _safe_path(_workspace(stage_dir), rel).read_bytes()
            _atomic_write(dest, payload)
            written.append(rel)
        journal.unlink()
        m["promoted"] = True
        _save(stage_dir, m)
        return {"promoted": written, "blocked": [], "reason": []}
    except Exception:
        # Keep journal for explicit reconciliation; NEVER guess which files can
        # be restored after concurrent human edits.
        raise


def rollback_from_staged(stage_dir: Path, project_root: Path | str, baseline_path: Path | str | None = None) -> dict:
    """Rollback only the exact post-images in this stage; preserve newer edits."""
    stage_dir = Path(stage_dir).resolve()
    m = _read(stage_dir)
    root = Path(project_root).resolve()
    if root != Path(m["project_root"]).resolve():
        raise StagingRejected("Different project root")
    result: dict[str, list[str]] = {"restored": [], "blocked": [], "reason": []}
    for rel, hashes in m.get("changed", {}).items():
        try:
            p = _safe_path(root, rel)
            current = sha256_text(p.read_text(encoding="utf-8")) if p.exists() else None
            if current == hashes["before"]:
                result["restored"].append(rel)
                continue
            if current != hashes["after"]:
                raise StagingRejected(f"Human/concurrent edit preserved: {rel}")
            old = m["baseline"].get(rel)
            if old is None:
                p.unlink(missing_ok=True)
            else:
                _atomic_write(p, old.encode("utf-8"))
            result["restored"].append(rel)
        except (StagingRejected, OSError) as exc:
            result["blocked"].append(rel)
            result["reason"].append(str(exc))
    if not result["blocked"]:
        (stage_dir / "promotion-journal.json").unlink(missing_ok=True)
    return result

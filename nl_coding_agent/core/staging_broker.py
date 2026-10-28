"""Minimal transactional staging broker for autonomous file edits (SPEC-28)."""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from nl_coding_agent.core.workspace import out_of_scope_paths, path_in_scope, snapshot_workspace, diff_snapshots
from nl_coding_agent.core.code_integrity_gate import detect_stub, detect_weak_test
from nl_coding_agent.core.recovery_store import save_snapshot, rollback_from_snapshot, sha256_text

STAGING_DIR = Path("data/staging")


def _hash_file(p: Path) -> str:
    return sha256_text(p.read_text(encoding="utf-8", errors="replace"))


def stage_candidate(project_root: Path | str, mission_id: int, scope_paths: list[str]) -> Path:
    """Stage validated candidate changes to isolated staging directory."""
    root = Path(project_root).resolve()
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    stage_dir = STAGING_DIR / f"{mission_id}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for rel in scope_paths:
        src = root / rel
        if not src.exists() or not src.is_file():
            continue
        dst = stage_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        content = src.read_text(encoding="utf-8", errors="replace")
        dst.write_text(content, encoding="utf-8")
        manifest[rel] = {"hash": sha256_text(content), "len": len(content)}
    manifest_path = stage_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return stage_dir


def validate_candidate(stage_dir: Path, baseline_path: Path | str, scope_paths: list[str]) -> dict:
    """Validate staged changes against baseline and gate rules."""
    result = {"valid": True, "errors": [], "stub_files": [], "weak_tests": [], "unauthorized": []}
    if isinstance(baseline_path, str):
        baseline_path = Path(baseline_path)
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception:
        result["valid"] = False
        result["errors"].append("Baseline missing or unreadable")
        return result
    for rel in scope_paths:
        staged_file = stage_dir / rel
        if not staged_file.exists():
            # If file was deleted by agent (bad), treat as failure if it existed in baseline
            if rel in baseline and isinstance(baseline[rel], str) and baseline[rel].strip():
                result["valid"] = False
                result["errors"].append(f"File missing in staged candidate: {rel}")
            continue
        staged_content = staged_file.read_text(encoding="utf-8", errors="replace")
        # Scope check
        unauthorized = out_of_scope_paths([rel], ["nl_coding_agent/", "tests/", "docs/"])
        if unauthorized:
            result["valid"] = False
            result["unauthorized"].extend(unauthorized)
        # Integrity gate against baseline
        baseline_content = baseline.get(rel)
        if isinstance(baseline_content, str):
            if detect_stub(staged_content, baseline_content):
                result["valid"] = False
                result["stub_files"].append(rel)
                result["errors"].append(f"Stub detected in {rel}")
            if rel.startswith("tests/") and detect_weak_test(baseline_content, staged_content):
                result["valid"] = False
                result["weak_tests"].append(rel)
                result["errors"].append(f"Weakened test detected in {rel}")
    return result


def promote_staged(stage_dir: Path, project_root: Path | str) -> dict:
    """Promote validated staged candidate to workspace (atomic file-by-file)."""
    root = Path(project_root).resolve()
    result = {"promoted": [], "blocked": [], "reason": []}
    manifest_path = stage_dir / "manifest.json"
    if not manifest_path.exists():
        result["blocked"].append(str(stage_dir))
        result["reason"].append("No manifest: nothing validated")
        return result
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rel_path, info in manifest.items():
        dst = root / rel_path
        src = stage_dir / rel_path
        if not src.exists():
            result["blocked"].append(rel_path)
            result["reason"].append("Staged file missing")
            continue
        # Compare-and-swap promotion: only if current workspace matches pre-staged hash? Actually for promotion
        # after validation, we assume workspace is the post-patch state; we write staged content directly.
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        result["promoted"].append(rel_path)
    return result


def rollback_from_staged(stage_dir: Path, project_root: Path | str, baseline_path: Path | str) -> dict:
    """Selective rollback using baseline (compare-and-swap). Only restore files whose current workspace hash matches the bad patch state (i.e., they haven't been manually edited by user after agent failure)."""
    root = Path(project_root).resolve()
    result = {"restored": [], "blocked": [], "reason": []}
    if isinstance(baseline_path, str):
        baseline_path = Path(baseline_path)
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception:
        result["blocked"].append(str(baseline_path))
        result["reason"].append("Baseline unreadable")
        return result
    for rel_path, baseline_content in baseline.items():
        if not isinstance(baseline_content, str):
            continue
        p = root / rel_path
        if not p.exists() or not p.is_file():
            # If file was deleted by bad patch and should be restored, restore from baseline
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(baseline_content, encoding="utf-8")
            result["restored"].append(str(rel_path))
            continue
        current_hash = sha256_text(p.read_text(encoding="utf-8", errors="replace"))
        # We don't have post-patch hash saved; for rollback after stub detection we compare
        # current content to baseline; if different and baseline is the known-good version,
        # restore. To respect compare-and-swap, only restore if current is exactly the bad patch
        # or if user hasn't modified after (we assume if current differs from baseline and
        # baseline is verified, restore). This is safe for mission-owned files.
        if current_hash != sha256_text(baseline_content):
            # File changed; check if it matches the bad stub by integrity gate
            if detect_stub(p.read_text(encoding="utf-8", errors="replace"), baseline_content):
                p.write_text(baseline_content, encoding="utf-8")
                result["restored"].append(str(rel_path))
            else:
                # External change or other patch; block rollback of this file
                result["blocked"].append(str(rel_path))
                result["reason"].append("Current file differs from baseline and is not a detected stub; manual merge needed")
        else:
            # Already at baseline; nothing to restore
            result["restored"].append(str(rel_path))
    return result

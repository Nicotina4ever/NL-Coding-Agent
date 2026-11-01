"""Incremental conversation checkpoints with optional file restoration.

Checkpoints are intentionally separate from chat rewind: deleting later chat
messages does not touch files, and restoring files does not silently rewrite the
conversation. Git projects use hidden refs and do not modify the working index;
non-Git projects use a bounded archive fallback.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from nl_coding_agent.persistence import database


class CheckpointError(RuntimeError):
    pass


EXCLUDED_PARTS = {".git", ".workspace", "node_modules", "data", "build", "dist",
                  "__pycache__", ".pytest_cache", "da_eliminare"}


def _git(root: Path, args: list[str], *, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, **(env or {})})


def _is_git(root: Path) -> bool:
    return (root / ".git").exists() and _git(root, ["rev-parse", "--is-inside-work-tree"]).returncode == 0


def _retention() -> int:
    try:
        value = int(database.get_setting("chat.checkpoint_retention", "10") or "10")
    except Exception:
        value = 10
    return max(1, min(value, 100))


def _project_root(project_id: int) -> Path:
    conn = database.init_db()
    try:
        row = conn.execute("SELECT root FROM projects WHERE id=?", (int(project_id),)).fetchone()
    finally:
        conn.close()
    if not row or not Path(row["root"]).is_dir():
        raise CheckpointError("project root is unavailable")
    return Path(row["root"]).resolve()


def _insert(project_id: int, session_id: str, message_id: int | None, kind: str,
            *, git_ref: str | None, archive_path: str | None, manifest: dict) -> dict:
    conn = database.init_db()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO chat_checkpoints(session_id, project_id, message_id, kind, "
                "git_ref, archive_path, manifest_json) VALUES (?,?,?,?,?,?,?)",
                (str(session_id), int(project_id), message_id, str(kind),
                 git_ref, archive_path, json.dumps(manifest, ensure_ascii=False)))
            checkpoint_id = int(cur.lastrowid)
            rows = conn.execute(
                "SELECT id, git_ref, archive_path FROM chat_checkpoints "
                "WHERE session_id=? ORDER BY id DESC", (str(session_id),)).fetchall()
            for old in rows[_retention():]:
                conn.execute("DELETE FROM chat_checkpoints WHERE id=?", (old["id"],))
        row = conn.execute("SELECT * FROM chat_checkpoints WHERE id=?", (checkpoint_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def create(project_id: int, session_id: str, *, message_id: int | None = None,
           kind: str = "manual") -> dict:
    root = _project_root(project_id)
    if _is_git(root):
        return _create_git(root, project_id, session_id, message_id, kind)
    return _create_archive(root, project_id, session_id, message_id, kind)


def _create_git(root: Path, project_id: int, session_id: str, message_id: int | None,
                kind: str) -> dict:
    ref = f"refs/nl-checkpoints/{session_id}/{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    index_fd, index_path = tempfile.mkstemp(prefix="nl-checkpoint-index-")
    os.close(index_fd)
    os.unlink(index_path)
    env = {"GIT_INDEX_FILE": index_path,
           "GIT_AUTHOR_NAME": "NL Code Checkpoint",
           "GIT_AUTHOR_EMAIL": "checkpoint@nlcode.local",
           "GIT_COMMITTER_NAME": "NL Code Checkpoint",
           "GIT_COMMITTER_EMAIL": "checkpoint@nlcode.local"}
    try:
        head = _git(root, ["rev-parse", "HEAD"])
        if head.returncode == 0:
            tree_base = _git(root, ["read-tree", "HEAD"], env=env)
            if tree_base.returncode != 0:
                raise CheckpointError("cannot initialize checkpoint index: " + tree_base.stderr[-400:])
            parent = ["-p", head.stdout.strip()]
        else:
            parent = []
        added = _git(root, ["add", "-A", "--", "."], env=env)
        if added.returncode != 0:
            raise CheckpointError("cannot capture working tree: " + added.stderr[-400:])
        tree = _git(root, ["write-tree"], env=env)
        if tree.returncode != 0:
            raise CheckpointError("cannot write checkpoint tree: " + tree.stderr[-400:])
        commit = _git(root, ["commit-tree", tree.stdout.strip(), *parent,
                             "-m", "NL Code checkpoint " + str(kind)], env=env)
        if commit.returncode != 0:
            raise CheckpointError("cannot create checkpoint commit: " + commit.stderr[-400:])
        sha = commit.stdout.strip()
        update = _git(root, ["update-ref", ref, sha])
        if update.returncode != 0:
            raise CheckpointError("cannot register checkpoint ref: " + update.stderr[-400:])
        return _insert(project_id, session_id, message_id, kind, git_ref=ref,
                       archive_path=None, manifest={"files": "git-working-tree", "sha": sha})
    finally:
        try:
            os.unlink(index_path)
        except OSError:
            pass


def _create_archive(root: Path, project_id: int, session_id: str, message_id: int | None,
                    kind: str) -> dict:
    target_dir = database.db_path().parent / "chat_checkpoints"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / (session_id + "-" + datetime.now().strftime("%Y%m%d%H%M%S%f") + ".tar.gz")
    with tarfile.open(path, "w:gz") as archive:
        for item in root.rglob("*"):
            if item == root or any(part in EXCLUDED_PARTS for part in item.relative_to(root).parts):
                continue
            if item.is_file():
                archive.add(item, arcname=item.relative_to(root).as_posix(), recursive=False)
    return _insert(project_id, session_id, message_id, kind, git_ref=None,
                   archive_path=str(path), manifest={"files": "archive"})


def list_for(project_id: int, session_id: str, limit: int = 50) -> list[dict]:
    conn = database.init_db()
    try:
        rows = conn.execute(
            "SELECT * FROM chat_checkpoints WHERE project_id=? AND session_id=? "
            "ORDER BY id DESC LIMIT ?", (int(project_id), str(session_id), int(limit))).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def restore(project_id: int, checkpoint_id: int) -> dict:
    conn = database.init_db()
    try:
        row = conn.execute("SELECT * FROM chat_checkpoints WHERE id=? AND project_id=?",
                           (int(checkpoint_id), int(project_id))).fetchone()
    finally:
        conn.close()
    if not row:
        raise CheckpointError("checkpoint not found for this project")
    root = _project_root(project_id)
    project = {"id": project_id}
    # Capture the current state first so the restore is reversible.
    safety = create(project_id, str(row["session_id"]), kind="before-restore")
    if row["git_ref"]:
        if not _is_git(root):
            raise CheckpointError("checkpoint requires the original Git project")
        target = row["git_ref"]
        checkout = _git(root, ["restore", "--source", target, "--worktree", "--", "."])
        if checkout.returncode != 0:
            raise CheckpointError("Git restore failed: " + checkout.stderr[-500:])
        tree = _git(root, ["ls-tree", "-r", "--name-only", target])
        tracked = {line for line in tree.stdout.splitlines() if line}
        quarantined = []
        from nl_coding_agent.core.quarantine import quarantine_paths
        for item in root.rglob("*"):
            if item == root or any(part in EXCLUDED_PARTS for part in item.relative_to(root).parts):
                continue
            if item.is_file() and item.relative_to(root).as_posix() not in tracked:
                quarantined.append(item)
        if quarantined:
            quarantine_paths(root, quarantined, reason=f"checkpoint-{checkpoint_id}-restore")
        return {"ok": True, "checkpoint_id": int(checkpoint_id), "safety_checkpoint": safety,
                "git_ref": target, "quarantined": [str(item) for item in quarantined]}
    archive_path = Path(str(row["archive_path"] or ""))
    if not archive_path.is_file():
        raise CheckpointError("checkpoint archive is missing")
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.extractall(root, filter="data")
    return {"ok": True, "checkpoint_id": int(checkpoint_id), "safety_checkpoint": safety,
            "archive": str(archive_path)}

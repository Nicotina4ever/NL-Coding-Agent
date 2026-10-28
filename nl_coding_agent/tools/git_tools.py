"""Git tools for repository inspection and change tracking."""
from __future__ import annotations

import subprocess
from pathlib import Path


def get_git_status(project_root: Path | str) -> str:
    """Return 'git status --short' output for project_root."""
    root = Path(project_root).resolve()
    try:
        r = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            return r.stdout.strip() or "Clean working tree (no modifications)."
        return f"Git error (code {r.returncode}): {r.stderr.strip()}"
    except Exception as e:
        return f"Failed to execute git: {e}"


def get_git_diff(project_root: Path | str, cached: bool = False) -> str:
    """
    Return unified diff for modifications in project_root.
    Also includes newly created files so reviewers can inspect full additions.
    """
    root = Path(project_root).resolve()
    cmd = ["git", "diff"]
    if cached:
        cmd.append("--cached")
    try:
        r = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        diff_text = r.stdout or ""

        # Also capture untracked new files (marked with ?? in git status)
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if status_proc.returncode == 0:
            untracked = []
            for line in status_proc.stdout.splitlines():
                if line.startswith("?? "):
                    untracked_path = line[3:].strip().strip('"')
                    full_p = root / untracked_path
                    # Only include python or text code files under nl_coding_agent or tests
                    if full_p.is_file() and (untracked_path.startswith("nl_coding_agent") or untracked_path.startswith("tests")):
                        try:
                            content = full_p.read_text(encoding="utf-8", errors="replace")
                            untracked.append(f"\n--- /dev/null\n+++ b/{untracked_path}\n" + "\n".join("+" + l for l in content.splitlines()))
                        except Exception:
                            pass
            if untracked:
                diff_text += "\n\n=== NEW UNTRACKED FILES ===\n" + "\n".join(untracked)

        return diff_text.strip() or "(No diff)"
    except Exception as e:
        return f"Failed to get git diff: {e}"

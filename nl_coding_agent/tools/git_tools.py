"""Git tools for repository inspection and change tracking."""
from __future__ import annotations

import subprocess
from pathlib import Path

from nl_coding_agent.tools.shell import decode_output

_GIT_ENV = {
    "GIT_PAGER": "cat",
    "PAGER": "cat",
    "LC_ALL": "C.UTF-8",
    "LANG": "C.UTF-8",
}


def _run_git(root: Path, args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    import os

    env = dict(os.environ)
    for key, value in _GIT_ENV.items():
        env.setdefault(key, value)
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=False,
            timeout=timeout,
            env=env,
            stdin=subprocess.DEVNULL,
        )
        return r.returncode, decode_output(r.stdout), decode_output(r.stderr)
    except Exception as e:
        return -1, "", str(e)


def get_git_status(project_root: Path | str) -> str:
    """Return 'git status --short' output for project_root."""
    root = Path(project_root).resolve()
    code, out, err = _run_git(root, ["status", "--short", "--", "."], timeout=15)
    if code == 0:
        return out.strip() or "Clean working tree (no modifications)."
    return f"Git error (code {code}): {err.strip()}"


def get_git_diff(project_root: Path | str, cached: bool = False) -> str:
    """
    Return unified diff for modifications in project_root.
    Also includes newly created source/test files so reviewers can inspect full additions.
    """
    root = Path(project_root).resolve()
    args = ["diff"]
    if cached:
        args.append("--cached")
    args.extend(["--", "."])

    code, diff_text, err = _run_git(root, args)
    if code != 0:
        return f"Failed to get git diff: {err.strip()}"

    code, status_text, _ = _run_git(root, ["status", "--porcelain", "--", "."], timeout=15)
    if code == 0:
        untracked = []
        for line in status_text.splitlines():
            if not line.startswith("?? "):
                continue
            untracked_path = line[3:].strip().strip('"').replace("\\", "/")
            full_p = root / untracked_path
            if not full_p.is_file():
                continue
            if not (untracked_path.startswith("nl_coding_agent") or untracked_path.startswith("tests")):
                continue
            try:
                content = full_p.read_text(encoding="utf-8", errors="replace")
                untracked.append(
                    f"\n--- /dev/null\n+++ b/{untracked_path}\n"
                    + "\n".join("+" + line for line in content.splitlines())
                )
            except Exception:
                pass
        if untracked:
            diff_text += "\n\n=== NEW UNTRACKED FILES ===\n" + "\n".join(untracked)

    return diff_text.strip() or "(No diff)"

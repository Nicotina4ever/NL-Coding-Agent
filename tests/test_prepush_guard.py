"""Pre-push guard tests: temporary Git repos only, no network, no canonical hook."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "prepush_guard.py"
SECRET = "AKIAABCDEFGHIJKLMNOP"
SYNTHETIC = "sk-proj-" + "abcdefghijklmnopqrstuvwx"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=60)


def _init(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# clean\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


def _run(repo: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), *args],
        input=stdin, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120, env={**os.environ,
                                            "PYTHONDONTWRITEBYTECODE": "1"})


def _json(repo: Path, *args: str) -> tuple[subprocess.CompletedProcess, dict]:
    completed = _run(repo, *args, "--json")
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        payload = {}
    return completed, payload


def test_clean_repo_passes_all_scopes(tmp_path):
    repo = _init(tmp_path)
    for mode in ("scan-staged", "scan-head", "scan-history", "scan-all"):
        completed, payload = _json(repo, mode)
        assert completed.returncode == 0, (mode, completed.stderr)
        assert payload["ok"] is True and payload["blocked"] is False
        assert payload["no_push"] is True and payload["no_network"] is True
        assert payload["history_rewritten"] is False


def test_staged_secret_blocks_and_never_prints_value(tmp_path):
    repo = _init(tmp_path)
    (repo / "secrets.txt").write_text("aws_key = " + SECRET + "\n", encoding="utf-8")
    _git(repo, "add", "secrets.txt")
    completed, payload = _json(repo, "scan-staged")
    assert completed.returncode == 1
    assert payload["blocked"] is True
    assert payload["counts"]["blocking"] >= 1
    assert SECRET not in completed.stdout and SECRET not in completed.stderr
    assert SECRET not in json.dumps(payload)
    assert all("evidence" in finding for finding in payload["findings"])
    assert payload["findings"][0]["evidence"]["sha256_12"]
    assert payload["exit_code"] == 1


def test_tracked_and_history_secret_block(tmp_path):
    repo = _init(tmp_path)
    (repo / "config.py").write_text("TOKEN = \"" + SECRET + "\"\n", encoding="utf-8")
    _git(repo, "add", "config.py")
    _git(repo, "commit", "-q", "-m", "add secret")
    completed, payload = _json(repo, "scan-head")
    assert completed.returncode == 1 and payload["blocked"] is True
    completed, payload = _json(repo, "scan-history")
    assert completed.returncode == 1 and payload["blocked"] is True
    assert payload["findings"][0]["scope"] == "history"
    assert SECRET not in completed.stdout
    # Removing it from the working tree does not hide the historical leak.
    (repo / "config.py").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "remove secret")
    completed, payload = _json(repo, "scan-head")
    assert completed.returncode == 0
    completed, payload = _json(repo, "scan-history")
    assert completed.returncode == 1


def test_large_blob_runtime_database_and_log_paths_block(tmp_path):
    repo = _init(tmp_path)
    (repo / "python").mkdir()
    (repo / "python" / "runtime.txt").write_text("runtime copy\n", encoding="utf-8")
    (repo / "data").mkdir()
    (repo / "data" / "app.sqlite3").write_text("db\n", encoding="utf-8")
    (repo / "build").mkdir()
    (repo / "build" / "out.log").write_text("log\n", encoding="utf-8")
    big = repo / "large.bin"
    big.write_bytes(b"x" * (5 * 1024 * 1024 + 128))
    _git(repo, "add", "python", "data", "build", "large.bin")
    completed, payload = _json(repo, "scan-staged")
    assert completed.returncode == 1
    rules = {(item["path"], item["rule"]) for item in payload["findings"] if item["blocking"]}
    assert any("runtime.txt" in path for path, _rule in rules)
    assert any("app.sqlite3" in path for path, _rule in rules)
    assert any("out.log" in path for path, _rule in rules)
    assert any("large.bin" in path for path, _rule in rules)


def test_allowlisted_synthetic_fixture_passes_with_redaction(tmp_path):
    repo = _init(tmp_path)
    (repo / "tests").mkdir()
    fixture = repo / "tests" / "secret_fixture.py"
    fixture.write_text("VALUE = \"" + SYNTHETIC + "\"\n", encoding="utf-8")
    _git(repo, "add", "tests/secret_fixture.py")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"fixtures": [{
        "sha256": hashlib.sha256(SYNTHETIC.encode()).hexdigest(),
        "path_prefix": "tests/",
        "reason": "synthetic fixture for prepush guard tests",
    }]}), encoding="utf-8")
    completed, payload = _json(repo, "--allowlist", str(allowlist), "scan-staged")
    assert completed.returncode == 0, completed.stderr
    assert payload["ok"] is True
    assert payload["counts"]["allowlisted"] >= 1
    assert SYNTHETIC not in completed.stdout
    assert any(item["allowlisted"] for item in payload["findings"])
    # An allowlist path outside tests/ is refused.
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"fixtures": [{
        "sha256": hashlib.sha256(SYNTHETIC.encode()).hexdigest(),
        "path_prefix": "src/", "reason": "not synthetic"}]}), encoding="utf-8")
    completed = _run(repo, "--allowlist", str(bad), "scan-staged")
    assert completed.returncode == 2


def test_hook_mode_blocks_staged_and_preserves_clean_exit(tmp_path):
    repo = _init(tmp_path)
    stdin = "refs/heads/main " + "a" * 40 + " refs/heads/main " + "0" * 40 + "\n"
    completed = _run(repo, "hook", stdin=stdin)
    assert completed.returncode == 0, completed.stderr
    (repo / "secrets.txt").write_text("aws_key = " + SECRET + "\n", encoding="utf-8")
    _git(repo, "add", "secrets.txt")
    completed = _run(repo, "hook", stdin=stdin)
    assert completed.returncode == 1
    assert "BLOCKED" in completed.stderr
    assert SECRET not in completed.stdout and SECRET not in completed.stderr


def test_install_hook_dry_run_force_and_backup_in_temp_repo(tmp_path):
    repo = _init(tmp_path)
    target = repo / ".git" / "hooks" / "pre-push"
    completed = _run(repo, "install-hook")
    assert completed.returncode == 0
    assert target.exists() is False
    assert "Dry-print only" in completed.stdout
    completed = _run(repo, "install-hook", "--force")
    assert completed.returncode == 0
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "prepush_guard" in content and " hook " in content
    assert target.stat().st_size > 20
    first = target.read_text(encoding="utf-8")
    completed = _run(repo, "install-hook", "--force", "--backup")
    assert completed.returncode == 0
    backups = list(target.parent.glob("pre-push.bak.*"))
    assert backups
    assert target.read_text(encoding="utf-8") == first


def test_reports_json_and_markdown_redacted(tmp_path):
    repo = _init(tmp_path)
    (repo / "secrets.txt").write_text("aws_key = " + SECRET + "\n", encoding="utf-8")
    _git(repo, "add", "secrets.txt")
    reports = tmp_path / "out"
    completed = _run(repo, "scan-staged", "--json-out", str(reports / "guard.json"),
                     "--markdown-out", str(reports / "guard.md"))
    assert completed.returncode == 1
    payload = json.loads((reports / "guard.json").read_text(encoding="utf-8"))
    assert payload["blocked"] is True
    assert SECRET not in (reports / "guard.json").read_text(encoding="utf-8")
    markdown = (reports / "guard.md").read_text(encoding="utf-8")
    assert "BLOCKED" in markdown and SECRET not in markdown


def test_bad_repo_and_static_no_push_network_or_history_write():
    completed = subprocess.run([sys.executable, str(SCRIPT), "--repo",
                                str(REPO / "does-not-exist"), "scan-staged"],
                               capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert completed.returncode == 2
    source = SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("import requests", "from requests", "urllib.request",
                      "http.client", "import socket", "import urllib",
                      "git push", "git commit", "git fetch", "git tag",
                      "filter-branch", "reflog expire", "update-ref",
                      "os.remove(", ".unlink(", "shutil.rmtree"):
        assert forbidden not in lowered, forbidden
    assert "read-only" in lowered and "history_rewritten" in lowered

r"""SH-07 acceptance runner (C3e).

Tier A (default, fake mode): runs the deterministic two-consecutive-mission
supervisor test suite plus the read-only diagnostic gate, and writes machine-readable
evidence under .workspace/build/phase3/evidence/. No Ollama/model call and no live DB write.

Tier B (live mode, NOT executed by default): requires --confirm-live and an isolated
git worktree outside the repository, a temporary NL_DATA_DIR, local-only model
configuration, and no cloud/network grants. It runs two supervised missions with real
local models, records machine-readable evidence, and never commits anything.

Usage examples:
  python\python.exe scripts\run_supervisor_sh07.py                     # Tier A fake
  python\python.exe scripts\run_supervisor_sh07.py --json
  # Tier B (only after explicit human authorization; never in CI):
  python\python.exe scripts\run_supervisor_sh07.py --mode live --confirm-live \
      --worktree <C:\temp\nl-sh07-worktree>

Exit codes: 0 = evidence PASS, 1 = evidence FAIL, 2 = environment/usage refusal
(live mode NOT executed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from nl_coding_agent.core.workspace import WORKSPACE_DIRNAME  # noqa: E402

DEFAULT_EVIDENCE_ROOT = REPO_ROOT / WORKSPACE_DIRNAME / "build" / "phase3" / "evidence"
SH07_TESTS = REPO_ROOT / "tests" / "test_supervisor_sh07.py"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_supervisor.py"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str], *, cwd: Path | None = None,
         env: dict | None = None, timeout: int = 1800) -> dict:
    started = time.monotonic()
    completed = subprocess.run(
        command, cwd=str(cwd or REPO_ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, stdin=subprocess.DEVNULL,
    )
    return {
        "command": [str(part) for part in command],
        "exit_code": int(completed.returncode),
        "duration_s": round(time.monotonic() - started, 2),
        "stdout_tail": str(completed.stdout or "")[-8000:],
        "stderr_tail": str(completed.stderr or "")[-4000:],
    }


def _git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30, stdin=subprocess.DEVNULL,
    )
    return str(completed.stdout or "").strip()


def _git_ok(args: list[str], cwd: Path) -> bool:
    completed = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30, stdin=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _fake_env() -> tuple[dict, Path]:
    data = Path(tempfile.mkdtemp(prefix="nl-sh07-fake-data-"))
    env = dict(os.environ)
    env.update({
        "NL_DATA_DIR": str(data),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "QT_QPA_PLATFORM": "offscreen",
        "NO_COLOR": "1",
    })
    return env, data


def run_fake(evidence_root: Path) -> dict:
    evidence_dir = evidence_root / ("sh07-fake-" + _stamp())
    evidence_dir.mkdir(parents=True, exist_ok=False)
    env, data_dir = _fake_env()
    pytest_result = {"exit_code": 1, "duration_s": 0.0}
    verifier_result = {"exit_code": 1, "duration_s": 0.0}
    try:
        pytest_result = _run(
            [sys.executable, "-m", "pytest", "-q", str(SH07_TESTS),
             "-p", "no:cacheprovider"],
            env=env, timeout=1800,
        )
        verifier_env = dict(os.environ)
        verifier_env.pop("NL_DATA_DIR", None)
        verifier_result = _run(
            [sys.executable, str(VERIFY_SCRIPT), "--project", str(REPO_ROOT),
             "--json"],
            env=verifier_env, timeout=120,
        )
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
    verifier_payload: dict = {}
    try:
        verifier_payload = json.loads(verifier_result.get("stdout_tail") or "{}")
    except ValueError:
        verifier_payload = {}
    ok = pytest_result["exit_code"] == 0 and verifier_result["exit_code"] == 0
    payload = {
        "tier": "A",
        "mode": "fake",
        "ok": bool(ok),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": _git(["rev-parse", "HEAD"], REPO_ROOT),
        "repository": str(REPO_ROOT),
        "test_file": str(SH07_TESTS),
        "test_file_sha256": _sha256(SH07_TESTS),
        "pytest": pytest_result,
        "verifier": {**verifier_result, "report": verifier_payload},
        "evidence_dir": str(evidence_dir),
        "limitations": [
            "Tier A uses a scripted fake model seam; it does not prove local-model "
            "self-build reliability.",
            "Tier B (real local Ollama models on an isolated worktree) remains required "
            "before NL-BP-063 can be marked verified.",
        ],
    }
    (evidence_dir / "evidence.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (evidence_dir / "pytest.txt").write_text(
        str(pytest_result.get("stdout_tail") or "")
        + "\n" + str(pytest_result.get("stderr_tail") or ""),
        encoding="utf-8")
    (evidence_dir / "verifier.json").write_text(
        json.dumps(verifier_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (evidence_dir / "summary.md").write_text(
        "# SH-07 Tier A evidence\n\n"
        "- ok: " + str(ok) + "\n"
        "- timestamp: " + payload["timestamp_utc"] + "\n"
        "- git HEAD: " + payload["git_head"] + "\n"
        "- Tier A tests: " + str(pytest_result.get("exit_code")) + "\n"
        "- diagnostic gate: " + str(verifier_result.get("exit_code")) + "\n\n"
        "Tier B is pending and requires explicit authorization.\n",
        encoding="utf-8")
    payload["evidence_dir"] = str(evidence_dir)
    return payload


def validate_live_environment(worktree: Path | None) -> dict:
    """Validate every Tier B precondition before any model/network use."""
    if worktree is None:
        raise SystemExit("ERROR: --mode live requires --worktree <isolated git worktree path>")
    worktree = Path(worktree).expanduser().resolve()
    if not worktree.is_dir():
        raise SystemExit("ERROR: worktree does not exist: " + str(worktree))
    if worktree == REPO_ROOT:
        raise SystemExit("ERROR: live mode must not run in the main repository checkout")
    if worktree.is_relative_to(REPO_ROOT) or REPO_ROOT.is_relative_to(worktree):
        raise SystemExit("ERROR: worktree must be outside the repository tree")
    if not (worktree / ".git").exists():
        raise SystemExit("ERROR: not a git worktree: " + str(worktree))
    top = Path(_git(["rev-parse", "--show-toplevel"], worktree)).resolve()
    if top != worktree:
        raise SystemExit("ERROR: worktree does not resolve to its own git root")
    if _git(["status", "--porcelain"], worktree):
        raise SystemExit("ERROR: worktree must be clean before the acceptance run")
    repo_head = _git(["rev-parse", "HEAD"], REPO_ROOT)
    worktree_head = _git(["rev-parse", "HEAD"], worktree)
    if not repo_head or repo_head != worktree_head:
        raise SystemExit(
            "ERROR: worktree HEAD " + worktree_head
            + " does not match repository HEAD " + repo_head)
    return {"worktree": str(worktree), "head": worktree_head}


def _refuse_unless_local_only(project_root: Path) -> dict:
    """Fail unless cloud/network are denied and every configured model is local."""
    from nl_coding_agent.core import permissions
    from nl_coding_agent.core.permissions import is_cloud_model, is_remote_endpoint

    policy = permissions.get_policy(None)
    for scope in ("cloud", "network"):
        if policy.get(scope):
            raise SystemExit(
                "ERROR: live SH-07 refuses granted " + scope.upper()
                + " permission; revoke it in the temporary app data first.")
    for scope in ("read", "write", "execute"):
        if not policy.get(scope):
            raise SystemExit("ERROR: missing required permission scope: " + scope)
    models_config: dict = {}
    config_path = Path(os.environ.get("NL_MODELS_CONFIG")
                       or (REPO_ROOT / "config" / "models.yaml"))
    try:
        import yaml

        models_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise SystemExit("ERROR: cannot read model config " + str(config_path) + ": " + str(exc))
    roles = models_config.get("roles") or {}
    fallback = roles.get("fallback_cloud") or {}
    if fallback.get("enabled"):
        raise SystemExit("ERROR: cloud fallback is enabled; live SH-07 requires local-only")
    # Only ACTIVE roles count: a disabled fallback (enabled: false) may name a cloud
    # model without enabling cloud escalation. Roles without an explicit enabled flag
    # are active by default.
    active_roles = [
        role for role in roles.values()
        if isinstance(role, dict) and role.get("enabled", True) is not False
    ]
    model_names = [str(role.get("model") or "") for role in active_roles]
    cloud_models = [name for name in model_names if name and is_cloud_model(name)]
    if cloud_models:
        raise SystemExit("ERROR: cloud model configured for a role: " + ", ".join(cloud_models))
    for provider_id, provider in (models_config.get("providers") or {}).items():
        if not isinstance(provider, dict) or not provider.get("enabled", True):
            continue
        base_url = str(provider.get("base_url") or "")
        if is_remote_endpoint(base_url):
            raise SystemExit("ERROR: remote provider endpoint enabled: " + str(provider_id)
                             + " " + base_url)
    from nl_coding_agent.models import ollama_registry

    if not ollama_registry.check_ollama_reachable():
        raise SystemExit("ERROR: local Ollama is not reachable; live SH-07 requires it")
    available = {model.name for model in ollama_registry.list_models()}
    required = [
        str(role.get("model") or "").removeprefix("ollama/")
        for role in active_roles
        if role.get("model")
    ]
    missing = sorted({name for name in required if name and name not in available})
    if missing:
        raise SystemExit("ERROR: required local model(s) not installed: " + ", ".join(missing))
    return {
        "permissions": dict(policy),
        "model_config": str(config_path),
        "required_models": sorted(set(required)),
        "available_model_count": len(available),
    }


_IMPLEMENTATION_SUFFIXES = (
    ".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg",
    ".bat", ".ps1", ".sh", ".js", ".mjs", ".ts", ".tsx", ".css", ".qss",
)
_IMPLEMENTATION_PREFIXES = ("tests/", "scripts/", "nl_coding_agent/", "installer/")


def has_implementation_change(paths) -> bool:
    """True when at least one changed path is code/test evidence, not Markdown."""
    for raw in paths or ():
        rel = str(raw or "").replace("\\", "/").lstrip("./").lower()
        if not rel or rel.endswith((".md", ".rst", ".txt")):
            continue
        if rel.endswith(_IMPLEMENTATION_SUFFIXES):
            return True
        if rel.startswith(_IMPLEMENTATION_PREFIXES):
            return True
    return False


def run_live(worktree: Path | None, evidence_root: Path) -> dict:
    info = validate_live_environment(worktree)
    worktree = Path(info["worktree"])
    data_dir = Path(tempfile.mkdtemp(prefix="nl-sh07-live-data-"))
    os.environ["NL_DATA_DIR"] = str(data_dir)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTHONUTF8"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from nl_coding_agent.persistence import database
    from nl_coding_agent.persistence import supervisor_store as store
    from nl_coding_agent.persistence.missions import list_missions

    database.init_db().close()
    environment = _refuse_unless_local_only(worktree)
    evidence_dir = evidence_root / ("sh07-live-" + _stamp())
    evidence_dir.mkdir(parents=True, exist_ok=False)
    from nl_coding_agent.core.supervisor import run_supervisor

    started = time.monotonic()
    try:
        result = run_supervisor(
            worktree, mode="automatic", max_missions=2,
            config_overrides={"max_attempts_per_requirement": 2},
        )
        duration = round(time.monotonic() - started, 2)
        project_id = result.get("project_id")
        missions = list_missions(int(project_id)) if project_id is not None else []
        queue = store.list_queue(int(project_id)) if project_id is not None else []
        backlog = store.list_backlog() if project_id is not None else []
        evidence_rows = []
        for mission in missions:
            evidence_rows.extend(store.list_evidence(int(mission["id"])))
        git_diff = _git(["diff"], worktree)
        git_status = _git(["status", "--porcelain"], worktree)
        db_copy = evidence_dir / "supervisor.sqlite3"
        try:
            shutil.copy2(Path(database.db_path()), db_copy)
        except Exception:
            db_copy = None
        def _changed_paths(mission: dict) -> list[str]:
            try:
                parsed = json.loads(mission.get("changed_paths") or "[]")
            except Exception:
                parsed = []
            return [str(item) for item in parsed] if isinstance(parsed, list) else []

        completed_missions = [
            m for m in missions
            if m.get("harness_version") == 2 and str(m.get("status")) == "completed"
        ]
        implementation_missions = [
            m for m in completed_missions if has_implementation_change(_changed_paths(m))
        ]
        ok = (
            str(result.get("status")) == "completed"
            and int(result.get("completed") or 0) >= 2
            and len(completed_missions) >= 2
            and len(implementation_missions) == len(completed_missions)
        )
        payload = {
            "tier": "B",
            "mode": "live",
            "ok": bool(ok),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "duration_s": duration,
            "worktree": str(worktree),
            "worktree_head": info["head"],
            "repository": str(REPO_ROOT),
            "result": result,
            "environment": environment,
            "missions": missions,
            "queue": queue,
            "backlog": backlog,
            "evidence_rows": evidence_rows,
            "git_status": git_status,
            "git_diff_sha256": hashlib.sha256(git_diff.encode("utf-8")).hexdigest(),
            "quality_gate": {
                "completed_missions": len(completed_missions),
                "implementation_missions": len(implementation_missions),
                "changed_paths": {
                    str(m.get("id")): _changed_paths(m) for m in completed_missions
                },
            },
            "database_copy": str(db_copy) if db_copy else None,
        }
        (evidence_dir / "evidence.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")
        (evidence_dir / "git.diff").write_text(git_diff, encoding="utf-8")
        (evidence_dir / "summary.md").write_text(
            "# SH-07 Tier B live evidence\n\n"
            "- ok: " + str(ok) + "\n"
            "- worktree: " + str(worktree) + "\n"
            "- head: " + info["head"] + "\n"
            "- supervisor status: " + str(result.get("status")) + "\n"
            "- completed missions: " + str(result.get("completed")) + "\n"
            "- duration_s: " + str(duration) + "\n\n"
            "No commit was created; the worktree was left untouched for inspection.\n",
            encoding="utf-8")
        payload["evidence_dir"] = str(evidence_dir)
        return payload
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SH-07 acceptance runner (Tier A fake / Tier B live)")
    parser.add_argument("--mode", choices=["fake", "live"], default="fake")
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--worktree", default=None)
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    evidence_root = Path(args.evidence_root).expanduser().resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    if args.mode == "live":
        if not args.confirm_live:
            print("ERROR: live SH-07 requires --confirm-live (explicit human authorization).",
                  file=sys.stderr)
            return 2
        try:
            payload = run_live(Path(args.worktree) if args.worktree else None, evidence_root)
        except SystemExit as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except Exception as exc:  # noqa: BLE001 - acceptance boundary
            print("ERROR: live SH-07 failed to run: " + str(exc), file=sys.stderr)
            return 1
    else:
        payload = run_fake(evidence_root)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print("SH-07 " + payload["tier"] + " (" + payload["mode"] + "): "
              + ("PASS" if payload["ok"] else "FAIL"))
        print("Evidence: " + str(payload.get("evidence_dir")))
        if payload["tier"] == "A":
            print("Tier B (real local models) remains pending explicit authorization.")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI entry point — preserves doctor/audit/work/status commands."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from crewai import Agent, Crew, LLM, Process, Task

from nl_coding_agent.core.workspace import logs_root, state_root

APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODELS = APP_ROOT / "config" / "models.yaml"
DEFAULT_PROJECT = APP_ROOT / "config" / "voicebridge.yaml"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def raw_model_name(crewai_model: str) -> str:
    return crewai_model.split("/", 1)[1] if crewai_model.startswith("ollama/") else crewai_model


def ollama_stop(crewai_model: str) -> None:
    model = raw_model_name(crewai_model)
    try:
        subprocess.run(["ollama", "stop", model], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False, timeout=30)
    except Exception:
        pass


def make_llm(role_cfg: dict, base_url: str) -> LLM:
    """Build the CrewAI LLM after the fail-closed cloud/network permission gate."""
    from nl_coding_agent.core.permissions import assert_model_permitted

    assert_model_permitted(role_cfg["model"], base_url)
    return LLM(model=role_cfg["model"], base_url=base_url,
                temperature=role_cfg.get("temperature", 0.1))


def ensure_project(project_cfg: dict) -> Path:
    project = project_cfg.get("project") or {}
    root_value = project.get("root")
    if not root_value:
        raise SystemExit("Project root not configured")
    root = Path(root_value).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Project root not found: {root}")
    return root


def protected(project_cfg: dict) -> set[Path]:
    return {Path(p).resolve() for p in project_cfg["project"].get("protected_paths", [])}


def scan_repo(project_cfg: dict, max_files: int = 2500) -> dict:
    """Legacy scanner — kept for CLI compatibility."""
    root = ensure_project(project_cfg)
    ignore = set(project_cfg["project"].get("ignore_names", []))
    protected_paths = protected(project_cfg)
    files = []; dirs = set(); extensions = {}; md_files = []

    for p in root.rglob("*"):
        try:
            rp = p.resolve()
        except Exception:
            continue
        if any(part in ignore for part in p.parts):
            continue
        if rp in protected_paths:
            continue
        if p.is_dir():
            dirs.add(str(p.relative_to(root)))
            continue
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        files.append(rel)
        ext = p.suffix.lower() or "<none>"
        extensions[ext] = extensions.get(ext, 0) + 1
        if p.suffix.lower() in {".md", ".txt"}:
            md_files.append(rel)
        if len(files) >= max_files:
            break

    top_files = []
    for name in ("AGENTS.md", "README.md", "README.txt", "pyproject.toml", "requirements.txt",
                  "Cargo.toml", "package.json", "pnpm-lock.yaml", "package-lock.json",
                  "CMakeLists.txt", "Makefile", "docker-compose.yml", "docker-compose.yaml"):
        if (root / name).exists():
            top_files.append(name)

    return {"project_root": str(root), "file_count_sampled": len(files),
            "extensions": dict(sorted(extensions.items(), key=lambda kv: (-kv[1], kv[0]))[:40]),
            "top_level_build_files": top_files, "documentation_files": md_files[:200],
            "files_sample": files[:500]}


def read_docs(project_cfg: dict, max_chars: int = 140_000) -> str:
    root = ensure_project(project_cfg)
    ignore = set(project_cfg["project"].get("ignore_names", []))
    protected_paths = protected(project_cfg)
    chunks = []; used = 0
    candidates = []
    for p in root.rglob("*"):
        if any(part in ignore for part in p.parts):
            continue
        try:
            if p.resolve() in protected_paths:
                continue
        except Exception:
            continue
        if p.is_file() and p.suffix.lower() in {".md", ".txt"}:
            candidates.append(p)
    candidates.sort(key=lambda p: (
        0 if p.name.lower() in {"agents.md", "readme.md", "architecture.md", "requirements.md"} else 1,
        len(p.parts), str(p).lower(),
    ))
    for p in candidates:
        if used >= max_chars:
            break
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        remaining = max_chars - used
        text = text[:remaining]
        rel = p.relative_to(root)
        chunk = f"\n\n===== FILE: {rel} =====\n{text}"
        chunks.append(chunk)
        used += len(chunk)
    return "".join(chunks)


def save_state(project_name: str, stage: str, content: str) -> Path:
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)
    folder = state_root() / safe_name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stage}.md"
    path.write_text(content, encoding="utf-8")
    return path


def kickoff_single(agent: Agent, task: Task) -> str:
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
    result = crew.kickoff()
    return str(result)


def doctor(models_cfg: dict, project_cfg: dict) -> int:
    print("=== NL Coding Agent / DOCTOR ===")
    print(f"Python: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")
    try:
        import crewai
        print(f"CrewAI: OK ({getattr(crewai, '__version__', 'not exposed')})")
    except Exception as e:
        print(f"CrewAI: ERROR: {e}"); return 2

    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30)
        print("Ollama: OK" if r.returncode == 0 else "Ollama: ERROR")
        if r.stdout: print(r.stdout)
    except Exception as e:
        print(f"Ollama: ERROR: {e}"); return 3

    try:
        root = ensure_project(project_cfg)
        print(f"Project: OK -> {root}")
    except SystemExit as e:
        print(f"Project: not configured ({e})")

    try:
        required = []
        for role, cfg in models_cfg["roles"].items():
            if role == "fallback_cloud" and not cfg.get("enabled", False):
                continue
            required.append(raw_model_name(cfg["model"]))
        listed = r.stdout if 'r' in locals() else ""
        for model in required:
            status = "OK" if model in listed else "NOT FOUND"
            print(f"Model {model}: {status}")
    except Exception:
        pass

    print("Doctor complete.")
    return 0


def audit(models_cfg: dict, project_cfg: dict) -> int:
    project = project_cfg["project"]["name"]
    root = ensure_project(project_cfg)
    repo_map = scan_repo(project_cfg)
    docs = read_docs(project_cfg)
    architect_cfg = models_cfg["roles"]["architect"]
    base_url = models_cfg["ollama"]["base_url"]
    llm = make_llm(architect_cfg, base_url)
    agent = Agent(
        role="Senior Software Architect",
        goal="Understand the repository and produce a realistic completion plan without modifying any files.",
        backstory="You are the lead architect. Distinguish implemented, incomplete, and spec-only items. Never invent test results.",
        llm=llm, verbose=True, allow_delegation=False,
    )
    prompt = f"""
Repository: {root}

READ-ONLY AUDIT PHASE.
Do not propose changes as if already applied.
Do not declare tests passed if not run.

REPO MAP:
{json.dumps(repo_map, indent=2, ensure_ascii=False)}

AVAILABLE DOCUMENTATION:
{docs}

Produce a Markdown report with:
1. Detected architecture; 2. Components and languages; 3. Module status;
4. Inconsistencies; 5. Completion priorities; 6. Ordered tasks with deps;
7. Files each task touches; 8. Build/test commands; 9. Integration risks;
10. Recommended FIRST concrete change.

Be conservative: write "to verify" when you cannot know from the provided material.
"""
    task = Task(description=prompt,
                expected_output="Detailed Markdown technical audit and ordered backlog.",
                agent=agent)
    try:
        result = kickoff_single(agent, task)
        path = save_state(project, "audit", result)
        print(f"\nAUDIT SAVED: {path}")
        return 0
    finally:
        if models_cfg["ollama"].get("unload_after_stage", True):
            ollama_stop(architect_cfg["model"])


def work(models_cfg: dict, project_cfg: dict, goal: str) -> int:
    project = project_cfg["project"]["name"]
    root = ensure_project(project_cfg)
    audit_path = state_root() / "".join(c if c.isalnum() or c in "-_" else "_" for c in project) / "audit.md"
    if not audit_path.exists():
        raise SystemExit("Run AUDIT first: state/.../audit.md does not exist yet")
    audit_text = audit_path.read_text(encoding="utf-8", errors="replace")
    base_url = models_cfg["ollama"]["base_url"]
    dev_cfg = models_cfg["roles"]["developer"]
    dev_llm = make_llm(dev_cfg, base_url)
    developer = Agent(
        role="Implementation Developer",
        goal="Prepare a concrete, verifiable change without scope creep.",
        backstory="You have an approved audit and a specific goal. Produce a file-by-file change plan, completion criteria and tests. In this bootstrap version you have no write tools: do not pretend to have modified files.",
        llm=dev_llm, verbose=True, allow_delegation=False,
    )
    dev_task = Task(
        description=f"""
PROJECT: {root}
AUDIT:\n{audit_text}
USER GOAL:\n{goal}

Produce a concrete Implementation Specification:
- scope; - files to read/modify/create; - interfaces; - change order; - automated tests;
- manual verifications; - risks and rollback; - definition of done.

IMPORTANT: This is the bootstrap version. Do not claim to have written or executed code.
""",
        expected_output="Implementation Specification Markdown ready for a coder with file access.",
        agent=developer,
    )
    try:
        dev_result = kickoff_single(developer, dev_task)
        spec_path = save_state(project, "implementation_spec", dev_result)
        print(f"\nSPEC SAVED: {spec_path}")
    finally:
        if models_cfg["ollama"].get("unload_after_stage", True):
            ollama_stop(dev_cfg["model"])

    rev_cfg = models_cfg["roles"]["reviewer"]
    rev_llm = make_llm(rev_cfg, base_url)
    reviewer = Agent(
        role="Code Review & Integration Gatekeeper",
        goal="Block incomplete, conflicting, or unverifiable plans before repository modification.",
        backstory="You are the gatekeeper. Check deps, compatibility, tests, regressions. Reject the spec if needed.",
        llm=rev_llm, verbose=True, allow_delegation=False,
    )
    review_task = Task(
        description=f"""
GOAL:\n{goal}
IMPLEMENTATION SPEC:\n{dev_result}

Review the spec. Return:
- APPROVE or REJECT on the first line;
- blocking issues; - missing deps; - potential conflicts; - missing tests; - required changes;
- integration criteria.

Do not declare tests run.
""",
        expected_output="APPROVE/REJECT verdict with technical review.",
        agent=reviewer,
    )
    try:
        review_result = kickoff_single(reviewer, review_task)
        review_path = save_state(project, "review", review_result)
        print(f"\nREVIEW SAVED: {review_path}")
        print("\nNOTE: bootstrap stops here intentionally.")
        return 0
    finally:
        if models_cfg["ollama"].get("unload_after_stage", True):
            ollama_stop(rev_cfg["model"])


def status(project_cfg: dict, config_path: Path | None = None) -> int:
    """Show legacy per-project CLI state; works without a machine-local project config.

    A portable install intentionally does not ship ``config/voicebridge.yaml`` (it
    contains a machine-local external project root). Status must therefore degrade
    gracefully instead of raising KeyError when no project is configured.
    """
    configured = (project_cfg or {}).get("project") or {}
    project = configured.get("name")
    if not project:
        print("Project: not configured")
        if config_path is not None:
            print(f"Project config: {config_path} (missing or has no project entry)")
        print("No state created yet. Open a project in the GUI or pass --project-config <file>.")
        return 0
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project)
    folder = state_root() / safe_name
    print(f"Project: {project}")
    print(f"State: {folder}")
    if not folder.exists():
        print("No state created yet.")
        return 0
    for p in sorted(folder.glob("*.md")):
        stat = p.stat()
        print(f"- {p.name}: {stat.st_size} bytes, {datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')}")
    return 0


# --------------------------------------------------------------------------- #
# Stage-3 persistent supervisor surfaces (C3d)
# --------------------------------------------------------------------------- #

_SUPERVISOR_COMMANDS = ("run", "start", "stop", "pause", "resume", "status",
                        "index", "recover", "advance-stage")


def supervisor_exit_code(status: str) -> int:
    """Documented supervisor CLI exit codes (plan section 9.1)."""
    text = str(status or "").strip().lower()
    if text in ("completed", "idle", "off"):
        return 0
    if text in ("waiting_for_resources", "waiting_for_approval"):
        return 4
    if text in ("stopped", "paused", "stopping", "lease-lost", "lease_lost"):
        return 3
    if text in ("blocked", "failed", "already-running", "already_running"):
        return 1
    return 2


def _print_supervisor_json(payload) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _supervisor_open_project(root: Path) -> dict:
    from nl_coding_agent.projects.registry import open_project

    return open_project(root)


def _launch_detached(command: list[str], log_path: Path) -> int:
    """Start one detached supervisor process (not an OS service; documented limitation)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = log_path.open("a", encoding="utf-8")
    creationflags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags = int(subprocess.DETACHED_PROCESS) | int(
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            command,
            cwd=str(APP_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
        )
    finally:
        stream.close()
    return int(process.pid)


def _cmd_supervisor_run(args, *, detach: bool = False) -> int:
    root = Path(args.project).resolve()
    mode = str(getattr(args, "mode", None) or "automatic")
    if mode == "assisted" and not getattr(args, "confirm_assisted", False):
        print(
            "ERROR: --mode assisted requires --confirm-assisted (assisted autonomy "
            "asks for explicit consent at risky boundaries).",
            file=sys.stderr,
        )
        return 2
    max_missions = int(getattr(args, "max_missions", 1) or 1)
    if detach:
        command = [
            sys.executable, "nl_agent.py", "supervisor", "run",
            "--project", str(root), "--mode", mode,
            "--max-missions", str(max_missions),
        ]
        for flag, value in (("--dev-model", getattr(args, "dev_model", None)),
                            ("--reviewer-model", getattr(args, "reviewer_model", None)),
                            ("--debug-model", getattr(args, "debug_model", None))):
            if value:
                command.extend([flag, value])
        log_path = logs_root() / "supervisor.log"
        try:
            pid = _launch_detached(command, log_path)
        except Exception as exc:
            print(f"ERROR: could not start the detached supervisor: {exc}", file=sys.stderr)
            return 2
        payload = {"ok": True, "detached": True, "pid": pid,
                   "log": str(log_path), "command": command}
        if getattr(args, "json", False):
            _print_supervisor_json(payload)
        else:
            print(f"Supervisor started (pid {pid}); log: {log_path}")
        return 0
    from nl_coding_agent.core.supervisor import run_supervisor

    try:
        result = run_supervisor(
            root,
            mode=mode,
            max_missions=max_missions,
            developer_model=getattr(args, "dev_model", None),
            reviewer_model=getattr(args, "reviewer_model", None),
            debug_model=getattr(args, "debug_model", None),
            pipeline=getattr(args, "pipeline", None),
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"ERROR: supervisor run failed: {exc}", file=sys.stderr)
        return 2
    status = str(result.get("status") or "blocked")
    if getattr(args, "json", False):
        _print_supervisor_json(result)
    else:
        print(f"Supervisor status: {status}")
        for mission in result.get("missions") or []:
            print(
                f"  Mission #{mission.get('id')}: {mission.get('status')} "
                f"{mission.get('verdict') or ''} {mission.get('diff_stat') or ''}"
            )
        if result.get("stopped_reason"):
            print(f"Stopped: {result['stopped_reason']}")
        if result.get("retry_after_s"):
            print(f"Retry after: {result['retry_after_s']}s")
        print(f"Resume command: {result.get('resume_command') or ''}")
    return supervisor_exit_code(status)


def _cmd_supervisor_start(args) -> int:
    root = Path(args.project).resolve()
    mode = str(getattr(args, "mode", None) or "automatic")
    try:
        project = _supervisor_open_project(root)
        from nl_coding_agent.persistence import database

        key = "supervisor.project." + str(int(project["id"]))
        config = database.get_json_setting(key)
        config["mode"] = mode
        database.set_json_setting(key, config)
    except Exception as exc:
        print(f"ERROR: cannot persist supervisor mode: {exc}", file=sys.stderr)
        return 2
    return _cmd_supervisor_run(args, detach=True)


def _cmd_supervisor_control(args, command: str) -> int:
    root = Path(args.project).resolve()
    reason = str(getattr(args, "reason", "") or "")
    try:
        from nl_coding_agent.core.supervisor import supervisor_command

        result = supervisor_command(
            root, command, requested_by="cli", reason=reason,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"ERROR: supervisor {command} failed: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        _print_supervisor_json(result)
    else:
        print(f"Supervisor {command} command accepted: {result}")
    return 0 if result.get("ok", True) else 1


def _cmd_supervisor_status(args) -> int:
    root = Path(args.project).resolve()
    try:
        from nl_coding_agent.core.supervisor import supervisor_status

        status = supervisor_status(root)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"ERROR: supervisor status failed: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        _print_supervisor_json(status)
    else:
        run = status.get("run") or {}
        print(f"Supervisor status: {run.get('status') or status.get('status') or 'idle'}")
        print(f"Mode: {status.get('mode')}  Pipeline: {status.get('pipeline', 'sequential')}"
              f"  Project: {status.get('root')}")
        print(f"Program stage: {status.get('program_stage')}")
        flows = status.get("flow_runs") or []
        if flows:
            print(f"Flow runs: {len(flows)} (latest {flows[0].get('flow_id')} "
                  f"{flows[0].get('status')})")
        print(f"Queue counts: {status.get('queue_counts') or {}}")
        lease = status.get("lease")
        if lease:
            print(f"Lease: {lease.get('owner_id')} pid {lease.get('owner_pid')} "
                  f"until {lease.get('expires_at')}")
        else:
            print("Lease: free")
        print(f"Resume command: {status.get('resume_command') or ''}")
    return 0


def _cmd_supervisor_approvals(args) -> int:
    from nl_coding_agent.core.supervisor import Supervisor
    try:
        supervisor = Supervisor(Path(args.project).resolve())
        action = str(getattr(args, "approvals_command", "list"))
        if action == "list":
            payload = {"ok": True, "approvals": supervisor.list_approvals()}
        else:
            if not getattr(args, "id", None):
                print("ERROR: approvals approve/deny requires --id", file=sys.stderr)
                return 2
            payload = supervisor.decide_approval(
                int(args.id), approved=(action == "approve"),
                decided_by=str(getattr(args, "decided_by", "human") or "human"),
                reason=str(getattr(args, "reason", "") or ""))
    except Exception as exc:
        print(f"ERROR: supervisor approvals failed: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        _print_supervisor_json(payload)
    else:
        for approval in payload.get("approvals", []):
            print(f"#{approval.get('id')} {approval.get('status')} {approval.get('action')} mission={approval.get('mission_id')}")
        if "decision" in payload:
            print(f"Approval #{payload.get('approval_id')}: {payload.get('decision')}")
    return 0 if payload.get("ok", True) else 1


def _cmd_supervisor_index(args) -> int:
    root = Path(args.project).resolve()
    from nl_coding_agent.core import backlog

    try:
        index = backlog.load_project_index(root)
    except backlog.BacklogError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    stage = backlog.current_program_stage(
        index, override=None,
    )
    payload = {
        "ok": True,
        "source": index.source_path,
        "fingerprint": index.source_fingerprint,
        "schema_version": index.schema_version,
        "requirements": len(index.requirements),
        "stages": [
            {"stage": item.stage, "name": item.name, "status": item.status,
             "depends_on_stages": list(item.depends_on_stages)}
            for item in index.stages
        ],
        "current_stage": (
            {"stage": stage.stage, "name": stage.name, "status": stage.status}
            if stage is not None else None
        ),
        "warnings": list(index.warnings),
    }
    exit_code = 0
    do_sync = bool(getattr(args, "sync", False))
    do_check = bool(getattr(args, "check", False)) or not (
        do_sync or getattr(args, "show_next", False)
    )
    do_next = bool(getattr(args, "show_next", False))
    project_id = None
    if do_sync or do_next:
        try:
            project = _supervisor_open_project(root)
            project_id = int(project["id"])
        except Exception as exc:
            payload["project_error"] = str(exc)
            exit_code = 2
    if do_sync and project_id is not None:
        payload["sync"] = backlog.sync_backlog_mirror(project_id, index)
    if do_next and project_id is not None:
        try:
            selected = backlog.select_next_requirement(
                project_id, project_root=root, index=index,
            )
            payload["next"] = selected
        except backlog.BacklogError as exc:
            payload["ok"] = False
            payload["error"] = str(exc)
            exit_code = 2
    if getattr(args, "json", False):
        _print_supervisor_json(payload)
    else:
        print(f"Backlog: {payload['source']}")
        print(f"Schema: {payload['schema_version']}  Requirements: {payload['requirements']}")
        current = payload["current_stage"]
        print("Current stage: " + (
            f"{current['stage']} - {current['name']} [{current['status']}]"
            if current else "(none; program complete)"
        ))
        for warning in payload["warnings"]:
            print(f"WARNING: {warning}")
        if do_next:
            next_item = payload.get("next")
            if next_item:
                print(f"Next: {next_item['requirement_id']} - {next_item['title']}")
            else:
                print("Next: (no eligible requirement in the current stage)")
    return exit_code


def _cmd_supervisor_recover(args) -> int:
    root = Path(args.project).resolve()
    try:
        from nl_coding_agent.core.supervisor import Supervisor

        supervisor = Supervisor(root)
        if getattr(args, "dry_run", False):
            report = supervisor.preflight().to_dict()
            payload = {"ok": bool(report.get("ok")), "dry_run": True,
                       "preflight": report}
            exit_code = 0 if report.get("ok") else 2
        else:
            actions = supervisor.reconcile()
            payload = {"ok": True, "dry_run": False, "actions": actions}
            exit_code = 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"ERROR: supervisor recovery failed: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        _print_supervisor_json(payload)
    else:
        if payload.get("dry_run"):
            report = payload["preflight"]
            print("Recovery preflight: " + ("OK" if report.get("ok") else "BLOCKED"))
            for blocker in report.get("blockers") or []:
                print(f"  BLOCKER: {blocker}")
            for warning in report.get("warnings") or []:
                print(f"  WARNING: {warning}")
        else:
            print("Recovery actions: " + (", ".join(payload["actions"]) or "none"))
    return exit_code


def _cmd_supervisor_advance_stage(args) -> int:
    root = Path(args.project).resolve()
    if not getattr(args, "confirm", False):
        print(
            "ERROR: advance-stage requires --confirm and recorded evidence; human/backend only.",
            file=sys.stderr,
        )
        return 2
    evidence = list(getattr(args, "evidence", None) or [])
    if not evidence:
        print("ERROR: advance-stage requires at least one --evidence path.", file=sys.stderr)
        return 2
    try:
        project = _supervisor_open_project(root)
        from nl_coding_agent.core import backlog
        from nl_coding_agent.persistence import database

        index = backlog.load_project_index(root)
        wanted = int(args.stage)
        stages = {stage.stage: stage for stage in index.stages}
        if wanted not in stages:
            print(f"ERROR: program stage {wanted} does not exist in the index.",
                  file=sys.stderr)
            return 2
        key = "supervisor.project." + str(int(project["id"]))
        config = database.get_json_setting(key)
        config["program_stage_override"] = wanted
        config["advanced_by"] = "cli"
        config["advance_evidence"] = evidence
        database.set_json_setting(key, config)
        database.log_event(
            database.init_db(), "Program stage override recorded: " + str(wanted),
            source="supervisor", project_id=int(project["id"]),
            event_kind="advance-stage",
            payload=json.dumps({"stage": wanted, "evidence": evidence}),
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"ERROR: advance-stage failed: {exc}", file=sys.stderr)
        return 2
    payload = {"ok": True, "program_stage_override": wanted, "evidence": evidence}
    if getattr(args, "json", False):
        _print_supervisor_json(payload)
    else:
        print(f"Program stage override recorded: {wanted} (evidence: {', '.join(evidence)})")
    return 0


def _dispatch_supervisor(args) -> int:
    command = str(getattr(args, "supervisor_command", "") or "").strip().lower()
    if command == "run":
        return _cmd_supervisor_run(args)
    if command == "start":
        return _cmd_supervisor_start(args)
    if command in ("stop", "pause", "resume"):
        return _cmd_supervisor_control(args, command)
    if command == "status":
        return _cmd_supervisor_status(args)
    if command == "approvals":
        return _cmd_supervisor_approvals(args)
    if command == "index":
        return _cmd_supervisor_index(args)
    if command == "recover":
        return _cmd_supervisor_recover(args)
    if command == "advance-stage":
        return _cmd_supervisor_advance_stage(args)
    print(f"ERROR: unknown supervisor command: {command}", file=sys.stderr)
    return 2



# ---------------------------------------------------------------------------
# Goal Mode G2 CLI (persist only; no mission/model execution)
# ---------------------------------------------------------------------------
GOAL_GROUP_EPILOG = (
    "Goal commands persist local goals/milestones only. They never create, start "
    "or run missions, agents or models, and there are no execution flags. Goal "
    "data lives in the NL_DATA_DIR application database; there is no reset "
    "command - use a temporary NL_DATA_DIR to isolate a run."
)


def _goal_app():
    from nl_coding_agent.app.services import AppServices
    return AppServices()


def _goal_project_id(value):
    if value in (None, ""):
        return None, None
    text = str(value).strip()
    try:
        return int(text), None
    except ValueError:
        pass
    path = Path(text).expanduser()
    if not path.is_dir():
        return None, "project path/ID not found: " + text
    try:
        from nl_coding_agent.projects.registry import open_project
        return int(open_project(path)["id"]), None
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        return None, "cannot open project: " + str(exc)


def _goal_error_payload(payload: dict) -> dict:
    error = payload.get("error") if isinstance(payload, dict) else None
    return error if isinstance(error, dict) else {
        "code": "error", "type": "Error", "message": str(error or payload)}


def _goal_emit(payload: dict, as_json: bool, text_lines) -> int:
    ok = bool(payload.get("ok"))
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    elif ok:
        lines = text_lines() if callable(text_lines) else list(text_lines or [])
        for line in lines:
            print(line)
    if not ok:
        error = _goal_error_payload(payload)
        print("ERROR [" + str(error.get("code")) + "]: "
              + str(error.get("message")), file=sys.stderr)
        return 1
    return 0


def _read_goal_plan(plan_path: str):
    if plan_path == "-":
        raw = sys.stdin.read()
    else:
        path = Path(plan_path).expanduser()
        if not path.is_file():
            return None, "plan file not found: " + str(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            return None, "cannot read plan file: " + str(exc)
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return None, "plan is not valid JSON: " + str(exc)
    if isinstance(data, dict) and isinstance(data.get("milestones"), list):
        data = data["milestones"]
    if not isinstance(data, list):
        return None, "plan JSON must be a list of milestone objects (or {milestones:[...]})"
    return data, None


def _dispatch_goal(args) -> int:
    services = _goal_app()
    try:
        return _dispatch_goal_with(args, services)
    finally:
        try:
            services._db.close()
        except Exception:
            pass


def _dispatch_goal_with(args, services) -> int:
    command = str(getattr(args, "goal_command", "") or "").strip().lower()
    as_json = bool(getattr(args, "json", False))
    if command == "create":
        payload = {}
        if getattr(args, "from_file", None):
            try:
                payload = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                print("ERROR: cannot read create file: " + str(exc), file=sys.stderr)
                return 2
            if not isinstance(payload, dict):
                print("ERROR: create file must contain a JSON object", file=sys.stderr)
                return 2
        objective = getattr(args, "objective", None) or getattr(
            args, "objective_opt", None) or payload.get("objective")
        if not objective:
            print("ERROR: goal create requires an objective", file=sys.stderr)
            return 2
        project_id, error = _goal_project_id(
            getattr(args, "project", None) or payload.get("project_id")
            or payload.get("project"))
        if error:
            print("ERROR: " + error, file=sys.stderr)
            return 2
        references = dict(payload.get("reference_metadata") or {})
        for item in getattr(args, "reference", None) or []:
            if "=" not in str(item):
                print("ERROR: --reference must be KEY=VALUE", file=sys.stderr)
                return 2
            key, value = str(item).split("=", 1)
            references[key.strip()] = value.strip()
        if getattr(args, "reference_file", None):
            try:
                loaded = json.loads(Path(args.reference_file).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                print("ERROR: cannot read reference file: " + str(exc), file=sys.stderr)
                return 2
            if not isinstance(loaded, dict):
                print("ERROR: reference file must be a JSON object", file=sys.stderr)
                return 2
            references.update(loaded)
        acceptance = list(payload.get("acceptance_criteria") or [])
        acceptance.extend(getattr(args, "acceptance", None) or [])
        dependencies = list(payload.get("dependencies") or [])
        dependencies.extend(getattr(args, "dependency", None) or [])
        attachments = list(payload.get("attachments") or [])
        attachments.extend(getattr(args, "attachment", None) or [])
        result = services.goal_create(
            objective,
            title=getattr(args, "title", None) or payload.get("title"),
            project_id=project_id,
            acceptance_criteria=acceptance,
            priority=getattr(args, "priority", None) or payload.get("priority") or "P1",
            dependencies=dependencies, attachments=attachments,
            reference_metadata=references,
            template_id=payload.get("template_id"),
            template_version=payload.get("template_version"),
            source=payload.get("source") or "", origin=payload.get("origin") or "user")
        goal = result.get("goal") or {}
        return _goal_emit(result, as_json, lambda: [
            "Goal #" + str(goal.get("id")) + " created: " + str(goal.get("title"))
            + " [" + str(goal.get("status")) + ", " + str(goal.get("priority")) + "]"])

    if command == "list":
        project_id, error = _goal_project_id(getattr(args, "project", None))
        if error:
            print("ERROR: " + error, file=sys.stderr)
            return 2
        result = services.goal_list(project_id=project_id,
                                    status=getattr(args, "status", None),
                                    priority=getattr(args, "priority", None),
                                    limit=getattr(args, "limit", 200),
                                    offset=getattr(args, "offset", 0))
        goals = result.get("goals") or []
        return _goal_emit(result, as_json, lambda: [
            "#{:<3} {:<10} {:<3} {}".format(goal.get("id", ""), goal.get("status", ""),
                                            goal.get("priority", ""),
                                            goal.get("title", ""))
            for goal in goals] or ["No goals."])

    if command == "show":
        result = services.goal_get(args.goal_id)
        goal = result.get("goal") or {}
        if not result.get("ok"):
            return _goal_emit(result, as_json, [])
        milestones = services.goal_milestones(args.goal_id).get("milestones") or []
        return _goal_emit(result, as_json, lambda: [
            "Goal #" + str(goal.get("id")) + ": " + str(goal.get("title")),
            "Status: " + str(goal.get("status")) + "  Priority: "
            + str(goal.get("priority")) + "  Project: " + str(goal.get("project_id")),
            "Objective: " + str(goal.get("objective")),
            "Acceptance criteria: " + json.dumps(goal.get("acceptance_criteria") or []),
            "Dependencies: " + json.dumps(goal.get("dependencies") or []),
            "Milestones (" + str(len(milestones)) + "):",
        ] + ["  #" + str(item.get("id")) + " [" + str(item.get("status")) + "] "
             + str(item.get("title")) for item in milestones])

    if command in ("activate", "pause", "resume", "cancel", "unblock"):
        result = getattr(services, "goal_" + command)(args.goal_id)
        goal = result.get("goal") or {}
        return _goal_emit(result, as_json, lambda: [
            "Goal #" + str(args.goal_id) + ": " + str(goal.get("status"))])

    if command == "block":
        result = services.goal_block(args.goal_id, reason=getattr(args, "reason", ""))
        goal = result.get("goal") or {}
        return _goal_emit(result, as_json, lambda: [
            "Goal #" + str(args.goal_id) + " blocked (" + str(goal.get("status")) + ")"])

    if command == "decompose":
        plan_path = getattr(args, "plan", None)
        if not plan_path and sys.stdin.isatty():
            print("ERROR: goal decompose requires --plan FILE or --plan - (stdin)",
                  file=sys.stderr)
            return 2
        plan, error = _read_goal_plan(plan_path or "-")
        if error:
            print("ERROR: " + error, file=sys.stderr)
            return 2
        result = services.goal_decompose(args.goal_id, plan)
        milestones = result.get("milestones") or []
        return _goal_emit(result, as_json, lambda: [
            "Goal #" + str(args.goal_id) + " decomposed: "
            + str(len(milestones)) + " milestone(s)"] + [
            "  #" + str(item.get("id")) + " " + str(item.get("title"))
            + " deps=" + json.dumps(item.get("dependencies") or [])
            for item in milestones])

    if command == "next":
        goal_id = getattr(args, "goal_id", None)
        project_id, error = _goal_project_id(getattr(args, "project", None))
        if error:
            print("ERROR: " + error, file=sys.stderr)
            return 2
        result = services.goal_next_work(goal_id=goal_id, project_id=project_id,
                                         limit=getattr(args, "limit", 20))
        work = result.get("work") or []
        return _goal_emit(result, as_json, lambda: [
            "Next work (" + str(len(work)) + "):"] + [
            "  goal #" + str(item.get("goal_id")) + " milestone #"
            + str(item.get("milestone_id")) + " " + str(item.get("title"))
            for item in work] if work else ["Next work: none eligible."])

    if command == "progress":
        if getattr(args, "goal_id", None):
            result = services.goal_progress(args.goal_id)
            progress = result.get("progress") or {}
            return _goal_emit(result, as_json, lambda: [
                "Goal #" + str(args.goal_id) + ": " + str(progress.get("status")),
                "Milestones: " + str(progress.get("milestones_completed")) + "/"
                + str(progress.get("milestones_total")) + " ("
                + str(progress.get("progress_percent")) + "%)",
                "Eligible next work: " + json.dumps(progress.get("eligible_next_work") or [])])
        project_id, error = _goal_project_id(getattr(args, "project", None))
        if error:
            print("ERROR: " + error, file=sys.stderr)
            return 2
        result = services.goal_progress_summary(project_id=project_id)
        summary = result.get("summary") or {}
        return _goal_emit(result, as_json, lambda: [
            "Goals: " + str(summary.get("goals_total")) + "  Milestones: "
            + str(summary.get("milestones_completed")) + "/"
            + str(summary.get("milestones_total")),
            "By status: " + json.dumps(summary.get("goals_by_status") or {})])

    print("ERROR: unknown goal command: " + command, file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="NL Coding Agent CLI")
    parser.add_argument("--models", default=str(DEFAULT_MODELS))
    parser.add_argument("--project-config", default=str(DEFAULT_PROJECT))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("audit")
    w = sub.add_parser("work")
    w.add_argument("--goal", required=True)
    sub.add_parser("status")

    # Roadmap command
    rm = sub.add_parser("roadmap", help="Show the next self-build mission from docs/NEXT_SELF_BUILD_MISSION.md")
    rm.add_argument("--project", default=".")

    # Autonomous mission command
    m = sub.add_parser("mission", help="Execute or resume an autonomous multi-agent mission")
    m.add_argument("--project", default=".")
    m.add_argument("--goal", help="Goal of the mission")
    m.add_argument("--resume", type=int, help="Resume an existing mission by ID")
    m.add_argument("--list", action="store_true", help="List missions")
    m.add_argument("--show", type=int, help="Show details for a mission ID")
    m.add_argument("--stop-after", choices=["developer", "tester"], help="Stop after a stage (for recovery testing)")
    m.add_argument("--dev-model", help="Override the developer model")
    m.add_argument("--reviewer-model", help="Override the reviewer model")
    m.add_argument("--debug-model", help="Override the debugger model")

    # Self-build command
    sb = sub.add_parser("selfbuild", help="Run autonomous self-development on NL Coding Agent itself")
    sb.add_argument("--goal", help="Goal of the self-build mission")
    sb.add_argument("--from-roadmap", action="store_true", help="Use docs/NEXT_SELF_BUILD_MISSION.md")
    sb.add_argument("--autonomous", "--loop", dest="autonomous", action="store_true",
                    help="Deprecated: bounded compatibility loop delegated to the persistent supervisor (use 'supervisor run')")
    sb.add_argument("--resume", type=int, help="Resume this mission before selecting new work")
    sb.add_argument("--max-missions", type=int, default=1,
                    help="Maximum missions in one autonomous run (1-5, default 1)")
    sb.add_argument("--project", default=str(APP_ROOT), help="Project root (defaults to this application)")
    sb.add_argument("--stop-after", choices=["developer", "tester"], help="Stop after a stage (for recovery testing)")
    sb.add_argument("--dev-model", help="Override the developer model")
    sb.add_argument("--reviewer-model", help="Override the reviewer model")
    sb.add_argument("--debug-model", help="Override the debugger model")

    # Persistent supervisor command group (stage 3)
    sv = sub.add_parser(
        "supervisor", help="Persistent autonomous supervisor (lease/heartbeat/queue)"
    )
    svs = sv.add_subparsers(dest="supervisor_command", required=True)

    def _add_common(p):
        p.add_argument("--project", default=".")
        p.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    run_p = svs.add_parser("run", help="Run the supervisor loop (bounded by --max-missions)")
    _add_common(run_p)
    run_p.add_argument("--mode", choices=["off", "assisted", "automatic"], default="automatic")
    run_p.add_argument("--max-missions", type=int, default=1)
    run_p.add_argument("--confirm-assisted", action="store_true",
                       help="Required to run --mode assisted from the CLI")
    run_p.add_argument("--dev-model", help="Override the developer model")
    run_p.add_argument("--reviewer-model", help="Override the reviewer model")
    run_p.add_argument("--debug-model", help="Override the debugger model")
    run_p.add_argument("--pipeline", choices=["sequential", "flow"], default=None,
                       help="Execution pipeline (default: persisted/sequential)")

    start_p = svs.add_parser("start", help="Persist the mode and start a detached supervisor process")
    _add_common(start_p)
    start_p.add_argument("--mode", choices=["off", "assisted", "automatic"], default="automatic")
    start_p.add_argument("--max-missions", type=int, default=1)
    start_p.add_argument("--confirm-assisted", action="store_true")
    start_p.add_argument("--dev-model", help="Override the developer model")
    start_p.add_argument("--reviewer-model", help="Override the reviewer model")
    start_p.add_argument("--debug-model", help="Override the debugger model")
    start_p.add_argument("--pipeline", choices=["sequential", "flow"], default=None,
                         help="Execution pipeline (default: persisted/sequential)")

    stop_p = svs.add_parser("stop", help="Request a graceful supervisor stop")
    _add_common(stop_p)
    stop_p.add_argument("--reason", default="")
    for name, help_text in (
        ("pause", "Pause the supervisor at the next mission boundary"),
        ("resume", "Clear pause/stop flags and allow the supervisor to continue"),
        ("status", "Show supervisor mode/run/lease/queue status"),
    ):
        command_p = svs.add_parser(name, help=help_text)
        _add_common(command_p)

    approvals_p = svs.add_parser("approvals", help="List/decide durable flow approvals (human/backend only)")
    _add_common(approvals_p)
    approvals_p.add_argument("approvals_command", choices=["list", "approve", "deny"])
    approvals_p.add_argument("--id", type=int)
    approvals_p.add_argument("--reason", default="")
    approvals_p.add_argument("--decided-by", default="human")

    index_p = svs.add_parser("index", help="Check/sync the indexed blueprint backlog")
    _add_common(index_p)
    index_p.add_argument("--check", action="store_true", help="Validate the index (default)")
    index_p.add_argument("--sync", action="store_true", help="Sync the SQLite backlog mirror")
    index_p.add_argument("--show-next", action="store_true", help="Print the next eligible requirement")

    recover_p = svs.add_parser("recover", help="Reconcile supervisor queue/stage/journal state")
    _add_common(recover_p)
    recover_p.add_argument("--dry-run", action="store_true",
                           help="Only report the preflight; do not repair anything")

    advance_p = svs.add_parser(
        "advance-stage", help="Explicitly advance the program stage (human/backend only)"
    )
    _add_common(advance_p)
    advance_p.add_argument("--stage", type=int, required=True)
    advance_p.add_argument("--evidence", action="append", default=[])
    advance_p.add_argument("--confirm", action="store_true")

    # Goal Mode G2 command group (persist only; no autonomous execution)
    goal = sub.add_parser(
        "goal", help="Goal Mode: durable goals/milestones (no autonomous execution)",
        description="Create and manage durable goals and milestones. This command "
                    "group never creates, starts or runs missions, agents or models.",
        epilog=GOAL_GROUP_EPILOG)
    gs = goal.add_subparsers(dest="goal_command", required=True)

    create_p = gs.add_parser("create", help="Create a durable goal")
    create_p.add_argument("objective", nargs="?", default=None)
    create_p.add_argument("--objective", dest="objective_opt", default=None)
    create_p.add_argument("--title", default=None)
    create_p.add_argument("--project", default=None,
                          help="Project path or numeric project id (optional)")
    create_p.add_argument("--priority", choices=["P0", "P1", "P2", "P3"], default="P1")
    create_p.add_argument("--acceptance", action="append", default=[],
                          help="Acceptance criterion (repeatable)")
    create_p.add_argument("--dependency", action="append", type=int, default=[],
                          help="Existing goal id to depend on (repeatable)")
    create_p.add_argument("--attachment", action="append", default=[],
                          help="Attachment reference (repeatable; stored as text)")
    create_p.add_argument("--reference", action="append", default=[],
                          metavar="KEY=VALUE", help="Reference metadata (repeatable)")
    create_p.add_argument("--reference-file", default=None,
                          help="JSON object file added to reference metadata")
    create_p.add_argument("--from-file", default=None,
                          help="JSON object with objective/title/criteria/etc.")
    create_p.add_argument("--json", action="store_true")

    list_p = gs.add_parser("list", help="List goals (priority ordered)")
    list_p.add_argument("--project", default=None)
    list_p.add_argument("--status", choices=list(("planned", "active", "paused",
                                                 "blocked", "completed", "cancelled")),
                        default=None)
    list_p.add_argument("--priority", choices=["P0", "P1", "P2", "P3"], default=None)
    list_p.add_argument("--limit", type=int, default=200)
    list_p.add_argument("--offset", type=int, default=0)
    list_p.add_argument("--json", action="store_true")

    show_p = gs.add_parser("show", help="Show one goal and its milestones")
    show_p.add_argument("goal_id", type=int)
    show_p.add_argument("--json", action="store_true")

    for name, help_text in (("activate", "Activate a planned goal"),
                            ("pause", "Pause an active goal"),
                            ("resume", "Resume a paused goal"),
                            ("unblock", "Unblock a blocked goal"),
                            ("cancel", "Cancel a non-terminal goal")):
        lifecycle = gs.add_parser(name, help=help_text)
        lifecycle.add_argument("goal_id", type=int)
        lifecycle.add_argument("--json", action="store_true")

    block_p = gs.add_parser("block", help="Block a goal explicitly")
    block_p.add_argument("goal_id", type=int)
    block_p.add_argument("--reason", default="")
    block_p.add_argument("--json", action="store_true")

    decompose_p = gs.add_parser("decompose", help="Create milestones from a JSON plan")
    decompose_p.add_argument("goal_id", type=int)
    decompose_p.add_argument("--plan", default=None,
                             help="JSON plan file, or - for stdin (required)")
    decompose_p.add_argument("--json", action="store_true")

    next_p = gs.add_parser("next", help="List eligible next milestones")
    next_p.add_argument("--goal-id", type=int, default=None)
    next_p.add_argument("--project", default=None)
    next_p.add_argument("--limit", type=int, default=20)
    next_p.add_argument("--json", action="store_true")

    progress_p = gs.add_parser("progress", help="Goal progress or overall summary")
    progress_p.add_argument("goal_id", nargs="?", type=int, default=None)
    progress_p.add_argument("--project", default=None)
    progress_p.add_argument("--json", action="store_true")

    # GUI subcommand
    sub.add_parser("gui")

    args = parser.parse_args(argv)

    if args.command == "goal":
        return _dispatch_goal(args)

    if args.command == "supervisor":
        return _dispatch_supervisor(args)

    if args.command == "roadmap":
        from nl_coding_agent.core.roadmap import format_mission, next_mission
        try:
            mission = next_mission(Path(args.project).resolve())
        except FileNotFoundError as exc:
            raise SystemExit(str(exc))
        print(format_mission(mission))
        return 0

    if args.command == "mission":
        from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
        from nl_coding_agent.persistence.missions import (
            create_mission, get_mission, get_tasks, list_missions,
            set_mission_project,
        )
        from nl_coding_agent.projects.registry import open_project
        root = Path(args.project).resolve()
        project = open_project(root)

        if args.list:
            for mission in list_missions():
                harness = mission.get("harness_version")
                harness_label = f"v{harness}" if harness is not None else "legacy"
                stage_label = "stage" if mission.get("staging_dir") else "-"
                print(
                    f"#{mission['id']:>3}  {mission['status']:<11}  "
                    f"{harness_label:<6}  {stage_label:<5}  "
                    f"{mission.get('title', '')[:70]}"
                )
            return 0

        if args.show:
            mission = get_mission(args.show)
            if not mission:
                raise SystemExit(f"Mission #{args.show} not found")
            print(json.dumps({**mission, "tasks": get_tasks(args.show)}, indent=2, ensure_ascii=False))
            return 0

        if args.resume:
            m_id = args.resume
            mission = get_mission(m_id)
            if not mission:
                raise SystemExit(f"Mission #{m_id} not found")
            if mission.get("harness_version") != 2:
                raise SystemExit(
                    f"Mission #{m_id} predates the staged-candidate harness; "
                    "create a new mission instead "
                    "(legacy missions cannot be resumed safely)."
                )
            if mission.get("project_id") is None:
                set_mission_project(m_id, project["id"])
        else:
            if not args.goal:
                raise SystemExit("Error: --goal is required for new missions")
            m_id = create_mission(
                project_id=project["id"], title=args.goal[:50], goal=args.goal,
            )

        print(f"=== Running Multi-Agent Mission #{m_id} on {root} ===")
        orch = MultiAgentOrchestrator(root)
        res = orch.run_mission(
            mission_id=m_id,
            goal=args.goal,
            developer_model=args.dev_model,
            reviewer_model=args.reviewer_model,
            debug_model=args.debug_model,
            stop_after=args.stop_after,
        )
        print(f"Mission Status: {res['status']}")
        if res.get("error"):
            print(f"Error: {res['error']}")
        if res.get("diff_stat"):
            print(f"Diff: {res['diff_stat']}")
        if res.get("review"):
            print(f"Review: {res['review']}")
        return 0 if res["status"] == "completed" else 1

    if args.command == "selfbuild":
        root = Path(args.project).resolve()
        if args.autonomous:
            print(
                "WARNING: 'selfbuild --autonomous' is deprecated in stage 3; use "
                "'nl_agent.py supervisor run' (the persistent supervisor). "
                "Delegating through the compatibility shim.",
                file=sys.stderr,
            )
            if args.goal:
                raise SystemExit("Error: --autonomous selects work from durable state/roadmap; do not pass --goal")
            from nl_coding_agent.core.mission_lock import MissionLockError, mission_lock
            from nl_coding_agent.core.relocation import (
                RelocationError,
                check_selfbuild_readiness,
            )
            from nl_coding_agent.core.selfbuild_runner import run_autonomous
            from nl_coding_agent.persistence.database import db_path

            try:
                readiness = check_selfbuild_readiness(
                    db_path(), db_path().parent / "selfbuild_state.json", root
                )
            except RelocationError as exc:
                print(f"ERROR: cannot verify project relocation state: {exc}")
                return 2
            if not readiness["ok"]:
                print(
                    "ERROR: project relocation is not reconciled for " + str(root)
                    + "; refusing to start Self-Build Mode."
                )
                for message in readiness["errors"]:
                    print(f"  - {message}")
                return 2
            for message in readiness["warnings"]:
                print(f"WARNING: {message}")

            lock_path = db_path().parent / "selfbuild.lock"
            try:
                with mission_lock(-1, path=lock_path):
                    result = run_autonomous(
                        root,
                        max_missions=args.max_missions,
                        resume_mission_id=args.resume,
                        developer_model=args.dev_model,
                        reviewer_model=args.reviewer_model,
                        debug_model=args.debug_model,
                        stop_after=args.stop_after,
                    )
            except MissionLockError as exc:
                print(f"Self-Build Mode is already running: {exc}")
                return 1
            print(f"Self-Build Mode Status: {result['status']}")
            for mission in result.get("missions", []):
                print(
                    f"  Mission #{mission['id']}: {mission['status']} "
                    f"{mission.get('verdict') or ''} {mission.get('diff_stat') or ''}"
                )
            if result.get("stopped_reason"):
                print(f"Stopped: {result['stopped_reason']}")
            print(f"Resume command: {result['resume_command']}")
            return 0 if result["status"] in ("completed", "idle") else 1

        from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator
        from nl_coding_agent.core.roadmap import format_mission, next_mission
        from nl_coding_agent.persistence.missions import create_mission
        from nl_coding_agent.projects.registry import open_project
        project = open_project(root)
        goal = args.goal
        title = None
        if args.from_roadmap or not goal:
            try:
                roadmap = next_mission(root)
            except FileNotFoundError as exc:
                raise SystemExit(str(exc))
            goal = roadmap["goal"]
            title = roadmap["title"]
            print(format_mission(roadmap))
        if not goal:
            raise SystemExit("Error: provide --goal or --from-roadmap")
        title = title or f"Self-Build: {goal[:40]}"
        m_id = create_mission(project_id=project["id"], title=title, goal=goal)
        print(f"=== Starting Autonomous Self-Build Mission #{m_id} on {root} ===")
        orch = MultiAgentOrchestrator(root)
        res = orch.run_mission(
            mission_id=m_id,
            goal=goal,
            developer_model=args.dev_model,
            reviewer_model=args.reviewer_model,
            debug_model=args.debug_model,
            stop_after=args.stop_after,
        )
        print(f"Self-Build Mission #{m_id} Status: {res['status']}")
        if res.get("error"):
            print(f"Error: {res['error']}")
        if res.get("diff_stat"):
            print(f"Diff: {res['diff_stat']}")
        print(f"Review verdict: {res.get('verdict') or res.get('review', '')}")
        return 0 if res["status"] == "completed" else 1

    if args.command == "gui":
        from nl_coding_agent.gui.main import run_gui
        return run_gui()

    if not Path(args.models).exists():
        if args.command == "doctor":
            print("=== NL Coding Agent / DOCTOR ===")
            print(f"Python: {sys.executable}")
            import crewai
            print(f"CrewAI: OK ({getattr(crewai, '__version__', 'not exposed')})")
            try:
                r = subprocess.run(
                    ["ollama", "list"], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=30,
                )
                print("Ollama: OK" if r.returncode == 0 else "Ollama: ERROR")
                if r.stdout: print(r.stdout)
            except Exception as e:
                print(f"Ollama: ERROR: {e}")
            print("Doctor complete (no config loaded).")
            return 0
        raise SystemExit(f"Models config not found: {args.models}")

    models_cfg = load_yaml(Path(args.models))
    project_cfg = load_yaml(Path(args.project_config))

    if args.command == "doctor":
        return doctor(models_cfg, project_cfg)
    if args.command == "audit":
        return audit(models_cfg, project_cfg)
    if args.command == "work":
        return work(models_cfg, project_cfg, args.goal)
    if args.command == "status":
        return status(project_cfg, Path(args.project_config))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

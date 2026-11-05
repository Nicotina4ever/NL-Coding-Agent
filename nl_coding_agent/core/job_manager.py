"""Project-scoped background jobs with bounded logs and no implicit shell.

This is the local equivalent of a developer's background terminal: an explicit
argv vector runs in the project root, its output is persisted under
``data/jobs/<project_id>/`` and status survives an engine restart as evidence
(orphaned PIDs are reported as unknown, never guessed alive).

Safety rules:
- no shell interpolation; argv is passed directly to ``subprocess.Popen``;
- Workspace Write/Auto Review use bounded project commands; Full Access accepts
  OS-user executables without an extra allowlist;
- PowerShell ``-Command`` and encoded commands are rejected; only a project
  script via ``-File`` is accepted;
- commands are project-scoped, bounded by count/time/args, and require the
  global mode; legacy approval flags do not authorize or block execution.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from nl_coding_agent.persistence import database


class JobError(ValueError):
    pass


_ALLOWED = {
    "python", "python.exe", "py", "py.exe", "pytest", "pytest.exe",
    "npm", "npm.cmd", "node", "node.exe", "git", "git.exe",
    "pwsh", "pwsh.exe", "powershell", "powershell.exe",
    "cmd", "cmd.exe",
}
_MAX_JOBS = 8
_MAX_ARGS = 64
_MAX_ARG_CHARS = 4096
_MAX_LOG_BYTES = 200_000
_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()


def _jobs_root() -> Path:
    return database.data_root() / "jobs"


def _project_dir(project_id: int) -> Path:
    path = _jobs_root() / str(int(project_id))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _record_path(project_id: int, job_id: str) -> Path:
    return _project_dir(project_id) / (str(job_id) + ".json")


def _log_path(project_id: int, job_id: str) -> Path:
    return _project_dir(project_id) / (str(job_id) + ".log")


def _write_record(project_id: int, record: dict) -> None:
    target = _record_path(project_id, record["id"])
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def _read_record(project_id: int, job_id: str) -> dict | None:
    path = _record_path(project_id, job_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _project_script(root: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise JobError("Script is outside the project root") from None
    if not candidate.is_file():
        raise JobError("Script does not exist: " + value)
    return candidate


def _check_argv(argv: list[str], root: Path) -> list[str]:
    if not isinstance(argv, list) or not argv:
        raise JobError("argv must be a non-empty list")
    if len(argv) > _MAX_ARGS:
        raise JobError("Too many arguments")
    clean = [str(item) for item in argv]
    if any(not item or "\x00" in item or len(item) > _MAX_ARG_CHARS for item in clean):
        raise JobError("Invalid argument")
    from nl_coding_agent.core import permissions
    permissions.require(permissions.EXECUTE)
    if permissions.get_access_mode() == permissions.ACCESS_FULL_ACCESS:
        return clean
    executable = Path(clean[0]).name.lower()
    if executable not in _ALLOWED:
        raise JobError("Executable is not allowlisted: " + executable)
    if executable in {"pwsh", "pwsh.exe", "powershell", "powershell.exe"}:
        lowered = [item.lower() for item in clean]
        if {"-command", "-c", "-encodedcommand", "-ec"} & set(lowered):
            raise JobError("PowerShell command strings are not allowed; run a project script with -File")
        if "-file" in lowered:
            index = lowered.index("-file")
            if index + 1 >= len(clean):
                raise JobError("PowerShell -File requires an existing script")
            _project_script(root, clean[index + 1])
    if executable in {"python", "python.exe", "py", "py.exe"}:
        lowered = [item.lower() for item in clean]
        if "-c" in lowered:
            raise JobError("Python inline -c is not allowed; run a project script")
        if "-m" not in lowered:
            script = next((item for item in clean[1:] if not item.startswith("-")), None)
            if script is None:
                raise JobError("Python requires a project script")
            _project_script(root, script)
    if executable in {"node", "node.exe"}:
        lowered = [item.lower() for item in clean]
        if {"-e", "--eval"} & set(lowered):
            raise JobError("Node inline evaluation is not allowed; run a project script")
        script = next((item for item in clean[1:] if not item.startswith("-")), None)
        if script is None:
            raise JobError("Node requires a project script")
        _project_script(root, script)
    if executable in {"cmd", "cmd.exe"}:
        lowered = [item.lower() for item in clean]
        if "/c" not in lowered:
            raise JobError("cmd requires /c and a project script")
        index = lowered.index("/c")
        if index + 1 >= len(clean):
            raise JobError("cmd /c requires an existing script")
        _project_script(root, clean[index + 1])
    return clean


def start_job(project_id: int, root: str | Path, argv: list[str], *,
              label: str = "", timeout_s: int = 900) -> dict:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise JobError("Project root does not exist")
    clean = _check_argv(argv, root_path)
    if shutil.which(clean[0]) is None and clean[0].lower() not in {"python", "python.exe", "py", "py.exe"}:
        raise JobError("Executable is not available: " + clean[0])
    with _LOCK:
        active = [item for item in _JOBS.values()
                  if item.get("project_id") == int(project_id)
                  and item.get("status") in ("running", "starting")]
        if len(active) >= _MAX_JOBS:
            raise JobError("Too many running jobs for this project")
        job_id = "job-" + uuid.uuid4().hex[:12]
        log = _log_path(int(project_id), job_id)
        record = {
            "id": job_id, "project_id": int(project_id),
            "label": str(label or clean[0])[:200],
            "argv": clean, "cwd": str(root_path),
            "status": "starting", "exit_code": None,
            "started_at": time.time(), "finished_at": None,
            "log_path": str(log), "timeout_s": max(5, min(int(timeout_s), 3600)),
        }
        log_file = None
        try:
            log_file = log.open("ab")
            flags = 0
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            process = subprocess.Popen(  # noqa: S603 - fixed allowlisted argv, shell=False
                clean, cwd=str(root_path), stdin=subprocess.DEVNULL,
                stdout=log_file, stderr=subprocess.STDOUT,
                creationflags=flags, close_fds=True,
            )
        except Exception as exc:
            raise JobError("Could not start job: " + str(exc)) from exc
        finally:
            if log_file is not None:
                try:
                    log_file.close()
                except Exception:
                    pass
        record.update({"pid": int(process.pid), "status": "running"})
        _JOBS[job_id] = record
        _write_record(int(project_id), record)

    def monitor() -> None:
        try:
            process.wait(timeout=record["timeout_s"])
            code = process.returncode
            status = "completed" if code == 0 else "failed"
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                pass
            code, status = None, "timed-out"
        with _LOCK:
            current = _JOBS.get(job_id)
            if current is not None:
                current.update({"status": status, "exit_code": code,
                                "finished_at": time.time(), "pid": None})
                _write_record(int(project_id), current)

    threading.Thread(target=monitor, name="nl-job-" + job_id, daemon=True).start()
    return dict(record)


def list_jobs(project_id: int) -> list[dict]:
    with _LOCK:
        records = {item["id"]: dict(item) for item in _JOBS.values()
                   if item.get("project_id") == int(project_id)}
    for path in _project_dir(int(project_id)).glob("job-*.json"):
        if path.stem in records:
            continue
        data = _read_record(int(project_id), path.stem)
        if not data:
            continue
        if data.get("status") in ("running", "starting") and not _alive(int(data.get("pid") or 0)):
            data["status"] = "unknown"
            data["pid"] = None
            _write_record(int(project_id), data)
        records[path.stem] = data
    return sorted(records.values(), key=lambda item: item.get("started_at") or 0, reverse=True)


def get_job(project_id: int, job_id: str) -> dict:
    with _LOCK:
        item = _JOBS.get(str(job_id))
        if item is not None and item.get("project_id") == int(project_id):
            return dict(item)
    data = _read_record(int(project_id), str(job_id))
    if not data or data.get("project_id") != int(project_id):
        raise JobError("Job not found")
    if data.get("status") in ("running", "starting") and not _alive(int(data.get("pid") or 0)):
        data["status"] = "unknown"
        data["pid"] = None
        _write_record(int(project_id), data)
    return data


def output(project_id: int, job_id: str, *, max_bytes: int = 20_000) -> dict:
    record = get_job(project_id, job_id)
    path = _log_path(int(project_id), str(job_id))
    if not path.is_file():
        return {"job": record, "output": "", "truncated": False}
    data = path.read_bytes()
    limit = max(1, min(int(max_bytes), _MAX_LOG_BYTES))
    truncated = len(data) > limit
    text = data[-limit:].decode("utf-8", errors="replace")
    return {"job": record, "output": text, "truncated": truncated}


def stop_job(project_id: int, job_id: str) -> dict:
    record = get_job(project_id, job_id)
    pid = int(record.get("pid") or 0)
    if pid:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _alive(pid):
            time.sleep(0.2)
        if _alive(pid):
            try:
                os.kill(pid, 9)
            except OSError:
                pass
    with _LOCK:
        current = _JOBS.get(str(job_id))
        if current is not None:
            current.update({"status": "stopped", "exit_code": None, "pid": None,
                            "finished_at": time.time()})
            _write_record(int(project_id), current)
            record = dict(current)
    return record

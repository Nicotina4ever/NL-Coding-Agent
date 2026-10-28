"""Single-writer mission lock.

Two missions must never modify the same working tree concurrently.  The GUI uses
a sequential scheduler, but the CLI can be launched more than once; this file
lock makes the invariant real across processes.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from nl_coding_agent.persistence.database import db_path


class MissionLockError(RuntimeError):
    pass


def _lock_path() -> Path:
    return db_path().parent / "mission.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def acquire(mission_id: int, path: Path | None = None) -> Path:
    path = path or _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "pid": os.getpid(),
        "mission_id": mission_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    })

    for attempt in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            return path
        except FileExistsError:
            info = _read_lock(path)
            pid = int(info.get("pid") or 0)
            age = time.time() - path.stat().st_mtime
            if pid and not _pid_alive(pid):
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            if not pid and age > 3600:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            owner = f"pid {pid}" if pid else "unknown owner"
            raise MissionLockError(
                f"Another mission is already writing to this workspace ({owner}, "
                f"mission #{info.get('mission_id', '?')}). Wait for it to finish."
            )
    raise MissionLockError("Could not acquire the mission write lock.")


def release(mission_id: int | None = None, path: Path | None = None) -> None:
    path = path or _lock_path()
    info = _read_lock(path)
    if info.get("pid") != os.getpid():
        return
    if mission_id is not None and info.get("mission_id") != mission_id:
        return
    try:
        path.unlink()
    except OSError:
        pass


@contextmanager
def mission_lock(mission_id: int, path: Path | None = None) -> Iterator[None]:
    acquire(mission_id, path=path)
    try:
        yield
    finally:
        release(mission_id, path=path)


def lock_status() -> dict | None:
    path = _lock_path()
    if not path.exists():
        return None
    info = _read_lock(path)
    info["path"] = str(path)
    info["alive"] = _pid_alive(int(info.get("pid") or 0))
    return info

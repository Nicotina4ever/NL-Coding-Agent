"""Resource scheduler — sequential by default, resource-aware."""
from __future__ import annotations

import threading
import queue
from dataclasses import dataclass, field
from typing import Callable, Any
from datetime import datetime


@dataclass
class ScheduledTask:
    id: str
    fn: Callable[[], Any]
    label: str = ""
    status: str = "pending"
    result: Any = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class SequentialScheduler:
    """
    Runs tasks one at a time in a background thread.
    Suitable for local LLM workloads on single-GPU machines.
    """

    def __init__(self):
        self._queue: queue.Queue[ScheduledTask | None] = queue.Queue()
        self._tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="scheduler")
        self._thread.start()

    def submit(self, task_id: str, fn: Callable[[], Any], label: str = "") -> ScheduledTask:
        task = ScheduledTask(id=task_id, fn=fn, label=label)
        with self._lock:
            self._tasks[task_id] = task
        self._queue.put(task)
        return task

    def get_task(self, task_id: str) -> ScheduledTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[ScheduledTask]:
        with self._lock:
            return list(self._tasks.values())

    def _worker(self):
        while True:
            task = self._queue.get()
            if task is None:
                break
            task.status = "running"
            task.started_at = datetime.utcnow().isoformat()
            try:
                task.result = task.fn()
                task.status = "done"
            except Exception as e:
                task.error = str(e)
                task.status = "error"
            finally:
                task.finished_at = datetime.utcnow().isoformat()
            self._queue.task_done()

    def shutdown(self):
        self._queue.put(None)
        self._thread.join(timeout=5)


# Global scheduler instance
_scheduler: SequentialScheduler | None = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> SequentialScheduler:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = SequentialScheduler()
        return _scheduler

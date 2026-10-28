"""Task Graph, dependency resolution, and write collision prevention."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class CyclicDependencyError(Exception):
    pass


class TaskCollisionError(Exception):
    pass


@dataclass
class TaskNode:
    task_id: int
    title: str
    description: str
    agent_role: str
    depends_on: list[int] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed, blocked


class TaskGraph:
    """Manages an acyclic dependency graph of tasks and enforces writer isolation."""

    def __init__(self):
        self.nodes: dict[int, TaskNode] = {}

    def add_task(
        self,
        task_id: int,
        title: str,
        description: str,
        agent_role: str,
        depends_on: list[int] | None = None,
        write_paths: list[str] | None = None,
        status: str = "pending",
    ) -> TaskNode:
        node = TaskNode(
            task_id=task_id,
            title=title,
            description=description,
            agent_role=agent_role,
            depends_on=list(depends_on or []),
            write_paths=list(write_paths or []),
            status=status,
        )
        self.nodes[task_id] = node
        self.validate()
        return node

    def validate(self) -> None:
        """Verify no cycles exist in task dependencies."""
        visited: dict[int, int] = {}  # 0: visiting, 1: visited

        def dfs(node_id: int):
            state = visited.get(node_id)
            if state == 0:
                raise CyclicDependencyError(f"Cycle detected involving task {node_id}")
            if state == 1:
                return

            visited[node_id] = 0
            for dep in self.nodes.get(node_id, TaskNode(0, "", "", "")).depends_on:
                if dep in self.nodes:
                    dfs(dep)
            visited[node_id] = 1

        for nid in list(self.nodes.keys()):
            if nid not in visited:
                dfs(nid)

    def get_ready_tasks(self) -> list[TaskNode]:
        """Return tasks that are 'pending' and whose dependencies are all 'completed'."""
        ready = []
        for node in self.nodes.values():
            if node.status != "pending":
                continue
            deps_ok = True
            for dep_id in node.depends_on:
                dep_node = self.nodes.get(dep_id)
                if not dep_node or dep_node.status != "completed":
                    deps_ok = False
                    break
            if deps_ok:
                ready.append(node)
        return ready

    def check_collision(self, active_task: TaskNode, candidate_task: TaskNode) -> bool:
        """
        Check if candidate_task writes to any paths that active_task is also writing to.
        Returns True if collision detected.
        """
        active_writes = {Path(p).as_posix().lower() for p in active_task.write_paths}
        candidate_writes = {Path(p).as_posix().lower() for p in candidate_task.write_paths}

        overlapping = active_writes.intersection(candidate_writes)
        return len(overlapping) > 0

    def can_run_concurrently(self, running_tasks: list[TaskNode], candidate: TaskNode) -> bool:
        """Enforce single-writer rule across tasks on the same working tree."""
        for running in running_tasks:
            if self.check_collision(running, candidate):
                return False
        return True

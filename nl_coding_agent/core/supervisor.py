"""Persistent stage-3 supervisor core (C3c).

Non-LLM policy/service that owns the durable loop:

  preflight -> lease -> reconcile -> select/enqueue/claim -> mission ->
  classify -> evidence/queue/backlog -> stop/pause -> terminal run state

The supervisor never talks to a model directly: it drives
MultiAgentOrchestrator.run_mission() (the staged-candidate harness) and records
durable outcomes. Everything needed to resume lives in SQLite; there is no chat
or TODO-list dependency.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from nl_coding_agent.core import backlog, promotion, resource_gate
from nl_coding_agent.core.mission_lock import MissionLockError, lock_status, mission_lock
from nl_coding_agent.core.run_control import RunControl, RunStopped
from nl_coding_agent.persistence import database, supervisor_store as store
from nl_coding_agent.persistence.database import db_path
from nl_coding_agent.persistence.missions import (
    create_mission,
    find_mission_by_staging_dir,
    get_active_mission_for_requirement,
    get_mission,
    list_missions,
    mark_mission_started,
    update_mission_status,
)

__all__ = [
    "SupervisorConfig", "PreflightReport", "Outcome",
    "SupervisorError", "SupervisorBlocked", "LeaseConflict",
    "Supervisor", "run_supervisor", "supervisor_status", "supervisor_command",
    "resume_command",
]

RESUMABLE_QUEUE_STATES = ("RUNNING", "VERIFYING", "REVIEWING", "CLAIMED")
ACTIVE_MISSION_STATUSES = ("pending", "running", "interrupted")
LEGACY_RESUMABLE_STATUSES = ("running", "interrupted", "pending")

#: Promotion/queue failure codes that must never be retried automatically.
HARD_BLOCK_CODES = frozenset({
    "cas_conflict", "cas-conflict", "rollback_conflict", "rollback-conflict",
    "legacy_mission", "legacy-mission", "review_rejected", "review-rejected",
    "byte-invariant", "byte_invariant", "promotion-conflict", "promotion_failed",
    "not-verified", "stage-invalid", "stage_mismatch", "journal-present",
})
REPAIRABLE_TOKENS = (
    "candidate rejected", "candidate-rejected", "verification failed",
    "verification_failed", "no workspace change", "outside the declared write scope",
    "repair budget",
)
RESOURCE_TOKENS = (
    "not reachable", "connection", "connectionerror", "timeout", "timed out",
    "429", "quota", "rate limit", "gpu", "vram", "model is not available",
)
APPROVAL_TOKENS = (
    "permission denied", "explicit cloud grant", "explicit network grant",
    "requires an explicit", "cloud escalation", "network access is not granted",
)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class SupervisorConfig:
    mode: str = "off"
    max_missions_per_run: int = 1
    max_attempts_per_requirement: int = 2
    max_wall_time_s: int = 3600
    mission_wall_time_s: int = 1800
    heartbeat_interval_s: float = 5.0
    lease_ttl_s: float = 30.0
    idle_wait_s: float = 30.0
    backoff_schedule_s: tuple[int, ...] = (30, 120, 600, 1800)
    max_consecutive_failures: int = 2
    allowed_cloud_models: tuple[str, ...] = ()
    backlog_path: str = "docs/product-blueprint/INDEX.json"
    program_stage_override: int | None = None
    fail_fast_on_block: bool = True
    developer_model: str | None = None
    reviewer_model: str | None = None
    debug_model: str | None = None
    architect_model: str | None = None
    pipeline: str = "sequential"
    work_source: str = "backlog"

    @classmethod
    def load(cls, project_id: int | None, *, overrides: dict | None = None) -> "SupervisorConfig":
        merged: dict = {}
        try:
            merged.update(database.get_json_setting("supervisor.global"))
            if project_id is not None:
                merged.update(
                    database.get_json_setting("supervisor.project." + str(int(project_id)))
                )
        except Exception:
            merged = {}
        if overrides:
            merged.update({key: value for key, value in overrides.items() if value is not None})
        defaults = cls()
        kwargs: dict = {}
        for name in cls.__dataclass_fields__:  # type: ignore[attr-defined]
            value = merged.get(name, getattr(defaults, name))
            kwargs[name] = value
        if "backoff_schedule_s" in kwargs:
            try:
                kwargs["backoff_schedule_s"] = tuple(
                    max(0, int(item)) for item in kwargs["backoff_schedule_s"]
                )
            except (TypeError, ValueError):
                raise SupervisorError("backoff_schedule_s must be a list of integers")
        if "allowed_cloud_models" in kwargs:
            kwargs["allowed_cloud_models"] = tuple(str(item) for item in (kwargs["allowed_cloud_models"] or ()))
        config = cls(**kwargs)
        config.validate()
        return config

    def to_dict(self) -> dict:
        data = asdict(self)
        data["backoff_schedule_s"] = list(self.backoff_schedule_s)
        data["allowed_cloud_models"] = list(self.allowed_cloud_models)
        return data

    def validate(self) -> None:
        if self.work_source not in ("backlog", "goals"):
            raise SupervisorError("work_source must be backlog or goals")
        if self.mode not in store.RUN_MODES:
            raise SupervisorError("Invalid supervisor mode: " + repr(self.mode))
        if not 1 <= int(self.max_missions_per_run) <= 5:
            raise SupervisorError("max_missions_per_run must be within 1..5")
        if not 1 <= int(self.max_attempts_per_requirement) <= 5:
            raise SupervisorError("max_attempts_per_requirement must be within 1..5")
        if float(self.max_wall_time_s) <= 0:
            raise SupervisorError("max_wall_time_s must be positive")
        if float(self.mission_wall_time_s) <= 0:
            raise SupervisorError("mission_wall_time_s must be positive")
        if float(self.heartbeat_interval_s) <= 0:
            raise SupervisorError("heartbeat_interval_s must be positive")
        if float(self.lease_ttl_s) < float(self.heartbeat_interval_s):
            raise SupervisorError("lease_ttl_s must be >= heartbeat_interval_s")
        if not self.backoff_schedule_s:
            raise SupervisorError("backoff_schedule_s must not be empty")
        if self.program_stage_override is not None and int(self.program_stage_override) < 1:
            raise SupervisorError("program_stage_override must be a positive integer")
        if not str(self.backlog_path or "").strip():
            raise SupervisorError("backlog_path must not be empty")
        if str(self.pipeline or "") not in ("sequential", "flow"):
            raise SupervisorError("Invalid supervisor pipeline: " + repr(self.pipeline))


@dataclass
class PreflightReport:
    ok: bool
    project_id: int
    root: str
    mode: str
    program_stage: int | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recovery: list[str] = field(default_factory=list)
    lease: dict | None = None
    backlog: dict = field(default_factory=dict)
    permissions: dict = field(default_factory=dict)
    models: dict = field(default_factory=dict)
    git: dict = field(default_factory=dict)
    resume_command: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Outcome:
    queue_state: str | None
    failure_class: str | None = None
    failure_signature: str | None = None
    retry_after_s: int | None = None
    mission_result: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "queue_state": self.queue_state,
            "failure_class": self.failure_class,
            "failure_signature": self.failure_signature,
            "retry_after_s": self.retry_after_s,
            "mission_result": dict(self.mission_result or {}),
        }


class SupervisorError(RuntimeError):
    """Base class for supervisor contract failures."""


class SupervisorBlocked(SupervisorError):
    """The supervisor cannot safely continue; caller must surface the reason."""


class LeaseConflict(SupervisorError):
    """Another live supervisor owns the project lease."""


# --------------------------------------------------------------------------- #
# Small pure helpers
# --------------------------------------------------------------------------- #

def resume_command(project_root: str | Path, *, mode: str | None = None,
                   max_missions: int | None = None, work_source: str | None = None) -> str:
    command = (
        'python\\python.exe nl_agent.py supervisor run '
        '--project "' + str(Path(project_root).resolve()) + '"'
    )
    if mode and mode != "off":
        command += " --mode " + str(mode)
    if max_missions is not None:
        command += " --max-missions " + str(int(max_missions))
    if work_source is not None:
        command += " --work-source " + str(work_source)
    return command


def _transition_path(current: str, target: str) -> list[str] | None:
    """Shortest allowed state path (excluding current) or None when unreachable."""
    if current == target:
        return []
    queue: list[tuple[str, list[str]]] = [(current, [])]
    seen = {current}
    while queue:
        node, path = queue.pop(0)
        for nxt in store.QUEUE_TRANSITIONS.get(node, ()):
            if nxt in seen:
                continue
            if nxt == target:
                return path + [nxt]
            seen.add(nxt)
            queue.append((nxt, path + [nxt]))
    return None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _truncate(value: str, limit: int = 4000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "... [truncated]"


# --------------------------------------------------------------------------- #
# Supervisor
# --------------------------------------------------------------------------- #

class Supervisor:
    """Durable non-LLM supervisor for one project (C3c scope: single mission loop)."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        project_id: int | None = None,
        config: SupervisorConfig | None = None,
        orchestrator_factory: Callable | None = None,
        event_sink: Callable | None = None,
        control: RunControl | None = None,
        resource_decider: Callable | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.root = Path(project_root).resolve()
        self.project_id = int(project_id) if project_id is not None else None
        self._config_explicit = config is not None
        self.config = config or SupervisorConfig.load(self.project_id)
        if not self._config_explicit:
            self.config.validate()
        self.orchestrator_factory = orchestrator_factory
        self.event_sink = event_sink
        self.control = control or RunControl()
        self.control.add_checkpoint_hook(self._on_checkpoint)
        self._resource_decider = resource_decider or resource_gate.decide
        self._clock = clock or time.monotonic

        self.owner_id = uuid.uuid4().hex
        self.owner_pid = os.getpid()
        self.owner_host = socket.gethostname() or "unknown-host"

        self.run_id: int | None = None
        self.lease: store.Lease | None = None
        self.machine_lease: store.Lease | None = None

        self._lease_lost = False
        self._heartbeat_failures = 0
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

        self._index: backlog.BacklogIndex | None = None
        self._backlog_report: dict = {}
        self._resource_wait: resource_gate.ResourceDecision | None = None
        self._checkpoints: list[str] = []
        self._completed = 0
        self._failed = 0
        self._results: list[dict] = []
        self._executors: dict[int, object] = {}
        self._flow_runner = None
        self._active_goal_item = None

    # ------------------------------------------------------------ diagnostics

    def _on_checkpoint(self, stage: str) -> None:
        self._checkpoints.append(str(stage))
        if self._active_goal_item is not None:
            from nl_coding_agent.core.goals import GoalService
            allowed, reason = GoalService().execution_context(
                self._active_goal_item["payload"], int(self.project_id))
            if not allowed:
                raise RunStopped(str(stage), reason)

    @property
    def checkpoints(self) -> list[str]:
        return list(self._checkpoints)

    def _event(self, message: str, *, level: str = "info", kind: str = "supervisor",
               mission_id: int | None = None, payload: dict | None = None) -> None:
        payload = dict(payload or {})
        payload.setdefault("run_id", self.run_id)
        payload.setdefault("owner_id", self.owner_id)
        try:
            conn = database.init_db()
            try:
                database.log_event(
                    conn, message, source="supervisor", level=level,
                    payload=json.dumps(payload, ensure_ascii=False, default=str),
                    project_id=self.project_id, mission_id=mission_id,
                    correlation_id=self.owner_id, event_kind=kind,
                )
            finally:
                conn.close()
        except Exception:
            pass
        if self.event_sink is not None:
            try:
                self.event_sink({
                    "source": "supervisor", "level": level, "message": message,
                    "payload": payload,
                })
            except Exception:
                pass

    def _ensure_project(self) -> int:
        if self.project_id is None:
            from nl_coding_agent.projects.registry import open_project

            project = open_project(self.root)
            self.project_id = int(project["id"])
            if not self._config_explicit:
                self.config = SupervisorConfig.load(self.project_id)
        return int(self.project_id)

    def _resume_command(self) -> str:
        return resume_command(
            self.root, mode=self.config.mode,
            max_missions=self.config.max_missions_per_run,
            work_source=self.config.work_source,
        )

    # ---------------------------------------------------------------- lease

    def acquire(self) -> store.Lease:
        self._ensure_project()
        try:
            self.lease = store.acquire_lease(
                int(self.project_id),
                owner_id=self.owner_id,
                owner_pid=self.owner_pid,
                owner_host=self.owner_host,
                ttl_s=float(self.config.lease_ttl_s),
            )
        except store.LeaseConflict as exc:
            raise LeaseConflict(str(exc)) from exc
        self._lease_lost = False
        self._event("Supervisor lease acquired", payload={"expires_at": self.lease.expires_at})
        return self.lease

    def _adopt_machine_lease(self) -> None:
        """Refresh the local machine-slot handle from the durable row (typed Lease)."""
        raw = store.get_machine_lease(resource_gate.INFERENCE_RESOURCE)
        if raw is None:
            self.machine_lease = None
            return
        self.machine_lease = store.Lease(
            project_id=0,
            owner_id=str(raw.get("owner_id") or ""),
            version=int(raw.get("version") or 0),
            expires_at=str(raw.get("expires_at") or ""),
        )

    def heartbeat(self) -> store.Lease | None:
        """Renew the project lease (and machine slot); None means the lease was lost."""
        if self.lease is None:
            return self.machine_lease if self._renew_machine_slot() else None
        renewed = store.renew_lease(
            int(self.project_id),
            owner_id=self.owner_id,
            version=self.lease.version,
            ttl_s=float(self.config.lease_ttl_s),
        )
        if renewed is None:
            self._lease_lost = True
            self.control.request_stop("lease lost")
            self._event("Supervisor lease lost; stopping after the current safe point",
                        level="error", kind="lease-lost")
            return None
        self.lease = renewed
        if self.machine_lease is not None:
            self._renew_machine_slot()
        return renewed

    def _renew_machine_slot(self) -> bool:
        if self.machine_lease is None:
            return False
        if not store.renew_machine_lease(
                resource_gate.INFERENCE_RESOURCE, owner_id=self.owner_id,
                version=self.machine_lease.version, ttl_s=float(self.config.lease_ttl_s)):
            self.machine_lease = None
            self._lease_lost = True
            self.control.request_stop("machine inference lease lost")
            self._event("Machine inference lease lost", level="warning", kind="lease-lost")
            return False
        # Renewal increments the persisted CAS version; the next heartbeat must use it.
        self._adopt_machine_lease()
        return self.machine_lease is not None

    def _heartbeat_loop(self) -> None:
        interval = max(0.2, float(self.config.heartbeat_interval_s))
        while not self._heartbeat_stop.wait(interval):
            try:
                renewed = self.heartbeat()
            except Exception as exc:  # pragma: no cover - defensive
                renewed = None
                self._heartbeat_failures += 1
                self._event("Heartbeat failed: " + str(exc), level="warning", kind="heartbeat")
            else:
                self._heartbeat_failures = 0
            if renewed is None and self._heartbeat_failures >= 10:
                # A transient SQLite lock must not strand a still-valid lease.
                # Only declare loss once the durable lease has actually expired.
                expires = getattr(self.lease, "expires_at", None) if self.lease else None
                try:
                    from datetime import datetime
                    if expires and datetime.fromisoformat(str(expires)) > datetime.now():
                        continue
                except (TypeError, ValueError):
                    pass
                self._lease_lost = True
                self.control.request_stop("heartbeat failed")
                return

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="supervisor-heartbeat", daemon=True,
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        thread = self._heartbeat_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        self._heartbeat_thread = None

    def release(self) -> None:
        self._stop_heartbeat()
        if self.machine_lease is not None:
            try:
                store.release_machine_lease(
                    resource_gate.INFERENCE_RESOURCE, owner_id=self.owner_id
                )
            except Exception:
                pass
            self.machine_lease = None
        if self.lease is not None:
            try:
                store.release_lease(int(self.project_id), owner_id=self.owner_id)
            except Exception:
                pass
            self.lease = None

    # ------------------------------------------------------------- backlog

    def sync_backlog(self) -> dict:
        self._ensure_project()
        override = None
        default_relative = str(Path("docs") / "product-blueprint" / "INDEX.json")
        configured = str(self.config.backlog_path or "").strip()
        if configured and configured.replace("\\", "/").lstrip("./") != default_relative.replace("\\", "/"):
            override = configured
        try:
            index = backlog.load_project_index(self.root, override=override)
        except backlog.BacklogError as exc:
            raise SupervisorBlocked("Backlog index is not usable: " + str(exc)) from exc
        prior = ""
        try:
            prior = backlog.mirror_source_fingerprint(self.project_id)
        except Exception:
            prior = ""
        report = backlog.sync_backlog_mirror(self.project_id, index)
        self._index = index
        self._backlog_report = dict(report)
        if prior and prior != index.source_fingerprint:
            self._backlog_report["changed_since_last_sync"] = True
        return self._backlog_report

    def _current_stage(self) -> backlog.ProgramStage | None:
        if self._index is None:
            return None
        return backlog.current_program_stage(
            self._index, override=self.config.program_stage_override
        )

    def select_next(self) -> dict | None:
        self._ensure_project()
        if self._index is None:
            self.sync_backlog()
        in_flight: set[str] = set()
        for item in store.list_queue(int(self.project_id)):
            if item.get("state") not in store.QUEUE_TERMINAL_STATES:
                if item.get("requirement_id"):
                    in_flight.add(str(item["requirement_id"]))
        for mission in list_missions(int(self.project_id)):
            if mission.get("status") in ACTIVE_MISSION_STATUSES and mission.get("requirement_id"):
                in_flight.add(str(mission["requirement_id"]))
        try:
            return backlog.select_next_requirement(
                int(self.project_id), project_root=self.root, index=self._index,
                config=self.config, in_flight_requirement_ids=in_flight,
            )
        except backlog.BacklogError as exc:
            raise SupervisorBlocked("Backlog selection failed: " + str(exc)) from exc

    def enqueue_next(self) -> int | None:
        if self.config.work_source == "goals":
            from nl_coding_agent.core.goals import GoalService
            decision = GoalService().select_execution(int(self.project_id))
            self._event("Goal continuation selection", kind="goal-selection", payload=decision)
            selected = decision["selected"]
            if selected is None:
                return None
            return store.enqueue_mission(
                int(self.project_id), requirement_id=None, goal=selected["goal"],
                priority=selected["priority"], idempotency_key=selected["idempotency_key"],
                max_attempts=self.config.max_attempts_per_requirement,
                budget={"wall_time_s": self.config.mission_wall_time_s},
                payload=selected["payload"])
        selected = self.select_next()
        if selected is None:
            return None
        project_id = int(self.project_id)
        existing = store.find_queue_item(project_id, selected["idempotency_key"])
        if existing is not None:
            return int(existing["id"])
        mission_payload = dict(selected.get("mission") or {})
        queue_id = store.enqueue_mission(
            project_id,
            requirement_id=selected["requirement_id"],
            goal=selected["goal"],
            priority=selected["priority"],
            idempotency_key=selected["idempotency_key"],
            max_attempts=int(selected["max_attempts"]),
            budget=dict(mission_payload.get("budget") or {}),
            payload=mission_payload,
        )
        self._set_backlog(selected["requirement_id"], "READY")
        self._event(
            "Enqueued requirement " + selected["requirement_id"] + " as queue #" + str(queue_id),
            kind="queue", payload={"requirement_id": selected["requirement_id"],
                                   "queue_id": queue_id},
        )
        return queue_id

    # ------------------------------------------------------------- preflight

    def _git_state(self) -> dict:
        state = {"head": "", "dirty": None, "untracked": None, "error": ""}
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=str(self.root),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10, check=False,
            )
            if head.returncode == 0:
                state["head"] = str(head.stdout or "").strip()
            status = subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(self.root),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10, check=False,
            )
            if status.returncode == 0:
                lines = [line for line in str(status.stdout or "").splitlines() if line.strip()]
                state["dirty"] = len(lines)
                state["untracked"] = sum(1 for line in lines if line.startswith("??"))
        except (OSError, subprocess.SubprocessError) as exc:
            state["error"] = str(exc)
        return state

    def preflight(self) -> PreflightReport:
        self._ensure_project()
        project_id = int(self.project_id)
        report = PreflightReport(
            ok=True, project_id=project_id, root=str(self.root),
            mode=self.config.mode, resume_command=self._resume_command(),
        )
        self._resource_wait = None

        if self.config.mode == "off":
            report.warnings.append("Autonomy mode is off; the supervisor will not run missions.")

        # 1. relocation readiness (read-only guard against a stale/renamed root)
        try:
            from nl_coding_agent.core.relocation import check_selfbuild_readiness

            application_root = Path(__file__).resolve().parents[2]
            is_application_root = Path(self.root).resolve() == application_root
            readiness = check_selfbuild_readiness(
                db_path(), db_path().parent / "selfbuild_state.json", self.root,
                require_state=is_application_root,
            )
            if not readiness.get("ok", True):
                report.blockers.append(
                    "Project relocation state is not reconciled: "
                    + "; ".join(readiness.get("errors") or ["unknown relocation error"])
                )
            report.warnings.extend(readiness.get("warnings") or [])
        except Exception as exc:
            report.blockers.append("Relocation readiness check failed: " + str(exc))

        # 2. existing lease (report; the real CAS acquisition happens in acquire())
        try:
            held = store.get_lease(project_id)
        except store.StoreError as exc:
            report.blockers.append("Cannot read supervisor lease: " + str(exc))
            held = None
        report.lease = held
        if held is not None and held.get("owner_id") != self.owner_id:
            report.warnings.append(
                "Supervisor lease currently held by owner " + str(held.get("owner_id"))
                + " (pid " + str(held.get("owner_pid")) + "); acquisition will fail closed "
                "while it is live."
            )

        # 3. promotion journals / stages must be reconciled before any model call
        try:
            blocking = promotion.preflight(self.root, mission_lookup=find_mission_by_staging_dir)
        except Exception as exc:
            report.blockers.append("Promotion preflight failed: " + str(exc))
            blocking = []
        for message in blocking:
            report.blockers.append("Unresolved candidate promotion state: " + str(message))
        if blocking:
            report.resume_command = resume_command(
                self.root, mode=self.config.mode, max_missions=1,
                work_source=self.config.work_source
            )

        # 4. stale stage sweep (never journals, never non-terminal missions)
        try:
            removed = promotion.sweep_stale_stages(
                self.root, mission_lookup=find_mission_by_staging_dir
            )
            if removed:
                report.recovery.extend("Removed stale stage " + str(path) for path in removed)
        except Exception as exc:
            report.warnings.append("Stale stage sweep failed: " + str(exc))

        # 5. working-tree lock
        try:
            lock = lock_status()
        except Exception as exc:
            report.warnings.append("Could not read mission lock state: " + str(exc))
            lock = None
        if lock is not None:
            if lock.get("alive"):
                report.blockers.append(
                    "Working tree is locked by live process pid " + str(lock.get("pid"))
                    + " (mission #" + str(lock.get("mission_id")) + ")."
                )
            else:
                report.warnings.append(
                    "Stale mission lock from pid " + str(lock.get("pid")) + "; it will be reclaimed."
                )

        # 6. legacy missions are never resumed by this supervisor
        try:
            resumable = [
                mission for mission in list_missions(project_id)
                if mission.get("status") in LEGACY_RESUMABLE_STATUSES
            ]
        except store.StoreError as exc:
            report.blockers.append("Cannot list missions: " + str(exc))
            resumable = []
        legacy = [
            mission for mission in resumable
            if mission.get("harness_version") != promotion.HARNESS_VERSION
        ]
        for mission in legacy:
            report.warnings.append(
                "Legacy mission #" + str(mission["id"]) + " predates the staged-candidate "
                "harness and is excluded."
            )

        if self.config.work_source == "goals":
            from nl_coding_agent.core.goals import GoalService
            report.backlog = {"work_source": "goals",
                              "selection": GoalService().select_execution(project_id)}
        else:
            # 7. backlog index load + sync (fail-closed; never roadmap fallback)
            try:
                backlog_report = self.sync_backlog()
                stage = self._current_stage()
                report.program_stage = stage.stage if stage is not None else None
                report.backlog = {
                    "source": str(self._index.source_path if self._index is not None else ""),
                    "fingerprint": str(self._index.source_fingerprint if self._index is not None else ""),
                    "requirements": len(self._index.requirements) if self._index is not None else 0,
                    "program_stage": report.program_stage,
                    "report": backlog_report,
                }
                if backlog_report.get("changed_since_last_sync"):
                    report.warnings.append("Backlog index changed since the last sync; mirror updated.")
                if stage is None:
                    report.warnings.append(
                        "No selectable program stage remains; use supervisor advance-stage with evidence."
                    )
            except (SupervisorBlocked, backlog.BacklogError) as exc:
                report.blockers.append(str(exc))
                report.backlog = {"error": str(exc)}

        # 8. permissions
        try:
            from nl_coding_agent.core import permissions

            policy = permissions.get_policy(project_id)
            required = (permissions.READ, permissions.WRITE, permissions.EXECUTE)
            missing = [scope for scope in required if not policy.get(scope)]
            report.permissions = {
                "policy": dict(policy),
                "missing": missing,
                "delete": bool(policy.get(permissions.DELETE)),
                "network": bool(policy.get(permissions.NETWORK)),
                "cloud": bool(policy.get(permissions.CLOUD)),
            }
            for scope in missing:
                report.blockers.append(
                    "Missing required permission grant: " + scope.upper()
                    + " (permissions are human/backend owned)."
                )
        except Exception as exc:
            report.blockers.append("Permission policy check failed: " + str(exc))

        # 9. model availability + route permissions
        try:
            decision = self._resource_decider(self.config, project_id=project_id)
        except Exception as exc:
            decision = resource_gate.ResourceDecision(
                "wait", "Resource gate failed: " + str(exc),
                int(self.config.backoff_schedule_s[0]), {"error": str(exc)},
            )
        report.models = decision.to_dict()
        if decision.action == "blocked":
            report.blockers.append(decision.reason)
        elif decision.action == "wait":
            report.warnings.append(decision.reason)
            self._resource_wait = decision

        # 10. budget/config sanity
        try:
            self.config.validate()
        except SupervisorError as exc:
            report.blockers.append("Invalid supervisor configuration: " + str(exc))

        # 11. git state (read-only evidence)
        report.git = self._git_state()
        if report.git.get("dirty"):
            report.warnings.append(
                "Working tree has " + str(report.git["dirty"]) + " pre-existing change(s); "
                "they are recorded, never discarded."
            )

        # 12. legacy data/selfbuild.lock from the bounded runner
        legacy_lock = db_path().parent / "selfbuild.lock"
        if legacy_lock.exists():
            info: dict = {}
            try:
                info = json.loads(legacy_lock.read_text(encoding="utf-8"))
            except Exception:
                info = {}
            pid = int(info.get("pid") or 0)
            if pid and store._pid_alive(pid):
                report.blockers.append(
                    "Legacy Self-Build runner is still active (pid " + str(pid) + ")."
                )
            else:
                try:
                    legacy_lock.unlink()
                    report.recovery.append("Removed stale legacy selfbuild.lock")
                except OSError as exc:
                    report.warnings.append("Could not remove stale selfbuild.lock: " + str(exc))

        # 13. machine inference slot
        try:
            machine = store.get_machine_lease(resource_gate.INFERENCE_RESOURCE)
        except store.StoreError:
            machine = None
        if machine is not None:
            report.warnings.append(
                "Machine inference slot is currently held by " + str(machine.get("owner_id"))
                + "; the run will wait for it."
            )

        report.ok = not report.blockers
        self._event(
            "Preflight " + ("PASSED" if report.ok else "BLOCKED"),
            level="info" if report.ok else "warning", kind="preflight",
            payload=report.to_dict(),
        )
        return report

    # ------------------------------------------------------------- reconcile

    def _transition(self, queue_id: int, target: str | None, *, token: str | None,
                    mission_id: int | None = None,
                    failure_class: str | None = None,
                    failure_signature: str | None = None,
                    increment_attempts: bool = False,
                    extra: dict | None = None) -> bool:
        if target is None:
            return False
        item = store.get_queue_item(int(queue_id))
        if item is None:
            return False
        path = _transition_path(str(item["state"]), str(target))
        if path is None:
            raise SupervisorError(
                "Illegal mission_queue transition: " + str(item["state"]) + " -> " + str(target)
            )
        fields: dict = {}
        if mission_id is not None:
            fields["mission_id"] = int(mission_id)
        if failure_class is not None:
            fields["failure_class"] = str(failure_class)
        if failure_signature is not None:
            fields["failure_signature"] = str(failure_signature)
        if extra:
            fields.update(extra)
        if not path:
            if not fields:
                return True
            return store.update_queue_item(queue_id, claim_token=token, **fields)
        for index, state in enumerate(path):
            ok = store.update_queue_item(
                queue_id, claim_token=token, state=state,
                increment_attempts=(increment_attempts and index == len(path) - 1),
                **fields,
            )
            if not ok:
                return False
        return True

    def _set_backlog(self, requirement_id: str | None, status: str,
                     mission_id: int | None = None, note: str | None = None) -> None:
        if not requirement_id:
            return
        try:
            store.set_backlog_progress(
                str(requirement_id), supervisor_status=status,
                mission_id=mission_id, note=note,
            )
        except Exception as exc:
            self._event("Backlog progress update failed: " + str(exc),
                        level="warning", kind="backlog")

    def _classify_mission_text(self, mission: dict) -> str:
        promotion_status = str(mission.get("promotion_status") or "").lower()
        summary = str(mission.get("result_summary") or mission.get("last_error") or "")
        if promotion_status in HARD_BLOCK_CODES:
            return "HARD_BLOCK"
        lowered = summary.lower()
        if any(token in lowered for token in APPROVAL_TOKENS):
            return "WAIT_APPROVAL"
        if any(token in lowered for token in RESOURCE_TOKENS):
            return "WAIT_RESOURCE"
        if any(token in lowered for token in HARD_BLOCK_CODES):
            return "HARD_BLOCK"
        if any(token in lowered for token in REPAIRABLE_TOKENS):
            return "REPAIRABLE"
        return "HARD_BLOCK"

    def reconcile(self) -> list[str]:
        """Repair queue/backlog/run rows from durable facts (idempotent, no model calls)."""
        self._ensure_project()
        project_id = int(self.project_id)
        actions: list[str] = []
        actions.extend(self._reconcile_flow_runs())

        previous = store.get_active_run(project_id)
        if previous is not None and int(previous["id"]) != int(self.run_id or -1):
            store.update_run(int(previous["id"]), status="RECOVERING",
                             stopped_reason="recovered by supervisor " + self.owner_id)
            store.finish_run(int(previous["id"]), status="STOPPED",
                             reason="Recovered crashed supervisor run")
            actions.append("marked crashed run #" + str(previous["id"]) + " STOPPED")

        active_requirements: set[str] = set()
        for item in store.list_queue(
            project_id, states=("CLAIMED", "RUNNING", "VERIFYING", "REVIEWING")
        ):
            queue_id = int(item["id"])
            token = item.get("claim_token")
            requirement_id = item.get("requirement_id")
            mission_id = item.get("mission_id")
            mission = get_mission(int(mission_id)) if mission_id else None
            if mission is None and requirement_id:
                adopted = get_active_mission_for_requirement(str(requirement_id))
                if adopted is not None:
                    mission = adopted
                    mission_id = int(adopted["id"])
                    store.update_queue_item(queue_id, claim_token=token,
                                            mission_id=mission_id)
                    actions.append("adopted mission #" + str(mission_id) + " for queue #" + str(queue_id))
            if mission is None:
                target = "READY" if str(item["state"]) == "CLAIMED" else "INTERRUPTED"
                if self._transition(queue_id, target, token=token):
                    actions.append("queue #" + str(queue_id) + " -> " + target)
                continue
            if requirement_id:
                active_requirements.add(str(requirement_id))
            mission_id = int(mission["id"])
            status = str(mission.get("status") or "pending")
            if status == "completed" and (item.get("payload") or {}).get("work_source") == "goals":
                from nl_coding_agent.core.goals import GoalService
                if not GoalService.mission_verified(mission_id):
                    self._transition(queue_id, "BLOCKED", token=token, mission_id=mission_id,
                                     failure_class="HARD_BLOCK")
                    actions.append("blocked goal mission without verification evidence")
                    continue
            if status == "completed":
                self._transition(queue_id, "VERIFIED", token=token, mission_id=mission_id)
                self._set_backlog(requirement_id, "VERIFIED", mission_id)
                self._record_evidence(
                    mission_id, queue_id, "recovery",
                    {"state": "mission-completed-recovered"},
                )
                actions.append("queue #" + str(queue_id) + " -> VERIFIED (mission #"
                               + str(mission_id) + " completed)")
            elif status in ("blocked", "failed"):
                failure_class = self._classify_mission_text(mission)
                attempts = int(item.get("attempts") or 0)
                if failure_class == "REPAIRABLE" and attempts < int(item.get("max_attempts") or 1):
                    self._transition(queue_id, "NEEDS_FIX", token=token,
                                     mission_id=mission_id, failure_class=failure_class)
                    self._set_backlog(requirement_id, "NEEDS_FIX", mission_id)
                    actions.append("queue #" + str(queue_id) + " -> NEEDS_FIX")
                else:
                    failure_class = "BUDGET_EXHAUSTED" if failure_class == "REPAIRABLE" else failure_class
                    self._transition(queue_id, "BLOCKED", token=token,
                                     mission_id=mission_id, failure_class=failure_class)
                    self._set_backlog(requirement_id, "BLOCKED", mission_id)
                    actions.append("queue #" + str(queue_id) + " -> BLOCKED (" + failure_class + ")")
            elif status == "interrupted":
                self._transition(queue_id, "INTERRUPTED", token=token, mission_id=mission_id)
                self._set_backlog(requirement_id, "IN_FLIGHT", mission_id)
                actions.append("queue #" + str(queue_id) + " -> INTERRUPTED")
            else:
                # A recovered owner must re-claim this mission, not select an
                # unclaimable RUNNING row forever. The durable mission is reused.
                self._transition(queue_id, "INTERRUPTED", token=token, mission_id=mission_id)
                self._set_backlog(requirement_id, "IN_FLIGHT", mission_id)
                actions.append("adopted resumable queue #" + str(queue_id))

        from nl_coding_agent.core.goals import GoalService
        for item in store.list_queue(project_id):
            if item["state"] == "VERIFIED" and (item.get("payload") or {}).get("work_source") == "goals":
                GoalService().accept_execution(item)
            if item.get("state") not in store.QUEUE_TERMINAL_STATES and item.get("requirement_id"):
                active_requirements.add(str(item["requirement_id"]))
        try:
            rows = store.list_backlog()
        except store.StoreError:
            rows = []
        for row in rows:
            if row.get("supervisor_status") == "IN_FLIGHT" and row.get("requirement_id") not in active_requirements:
                self._set_backlog(row.get("requirement_id"), "READY")
                actions.append("backlog " + str(row.get("requirement_id")) + " -> READY")
        if actions:
            self._event("Supervisor reconcile: " + "; ".join(actions), kind="reconcile",
                        payload={"actions": actions})
        return actions

    # ---------------------------------------------------------------- status

    def _latest_run(self) -> dict | None:
        try:
            conn = database.init_db()
            try:
                row = conn.execute(
                    "SELECT * FROM supervisor_runs WHERE project_id=? ORDER BY id DESC LIMIT 1",
                    (int(self.project_id),),
                ).fetchone()
                if row is None:
                    return None
                return store.get_run(int(row["id"]))
            finally:
                conn.close()
        except Exception:
            return None

    def status(self) -> dict:
        self._ensure_project()
        project_id = int(self.project_id)
        run = store.get_active_run(project_id) or self._latest_run()
        effective_source = ((run or {}).get("config") or {}).get("work_source", self.config.work_source)
        queue = store.list_queue(project_id, limit=100)
        counts: dict[str, int] = {}
        for item in queue:
            counts[str(item["state"])] = counts.get(str(item["state"]), 0) + 1
        stage = None
        if effective_source == "backlog":
            try:
                if self._index is None:
                    self.sync_backlog()
                current = self._current_stage()
                stage = current.stage if current is not None else None
            except Exception:
                stage = None
        return {
            "status": str((run or {}).get("status") or "idle"),
            "mode": self.config.mode,
            "project_id": project_id,
            "root": str(self.root),
            "run": run,
            "lease": store.get_lease(project_id),
            "queue": queue,
            "queue_counts": counts,
            "program_stage": stage,
            "config": self.config.to_dict(),
            "pipeline": self.config.pipeline,
            "work_source": effective_source,
            "flow_runs": store.list_flow_runs(project_id=project_id)[:20],
            "approvals": store.pending_approvals(project_id),
            "resume_command": resume_command(
                self.root, mode=self.config.mode,
                max_missions=self.config.max_missions_per_run, work_source=effective_source),
        }

    # ------------------------------------------------------------ approvals

    def list_approvals(self, status: str | None = None) -> list[dict]:
        self._ensure_project()
        return store.list_approvals(int(self.project_id), status=status)

    def pending_approvals(self) -> list[dict]:
        self._ensure_project()
        return store.pending_approvals(int(self.project_id))

    def decide_approval(self, approval_id: int, *, approved: bool,
                        decided_by: str, reason: str = "") -> dict:
        """Human/backend decision; no model may call this."""
        self._ensure_project()
        approval = store.get_approval(int(approval_id))
        if approval is None:
            return {"ok": False, "error": "Approval not found: " + str(approval_id)}
        if str(approval.get("status")) != "pending":
            return {"ok": False, "error": "Approval is not pending", "approval": approval}
        scope = approval.get("scope") or {}
        ok = store.decide_approval(int(approval_id), approved=approved,
                                   decided_by=str(decided_by), reason=str(reason))
        mission_id = approval.get("mission_id")
        queue_id = scope.get("queue_id")
        flow_id = scope.get("flow_id")
        decision = "approved" if approved else "denied"
        if queue_id is not None:
            try:
                store.update_queue_item(
                    int(queue_id), state="READY" if approved else "BLOCKED",
                    failure_class=None if approved else "WAIT_APPROVAL")
            except Exception:
                pass
        if not approved and mission_id is not None:
            try:
                update_mission_status(int(mission_id), "blocked")
            except Exception:
                pass
        if mission_id is not None:
            try:
                store.record_evidence(
                    int(mission_id), kind="approval",
                    record_key="approval:" + str(approval_id),
                    payload={"decision": decision, "decided_by": str(decided_by),
                             "flow_id": flow_id, "reason": str(reason)[:2000]})
            except Exception:
                pass
        self._event("Approval #" + str(approval_id) + " " + decision + " by " + str(decided_by),
                    kind="approval", level="info" if approved else "warning",
                    payload={"approval_id": int(approval_id), "decision": decision,
                             "flow_id": flow_id, "queue_id": queue_id})
        return {"ok": bool(ok), "approval_id": int(approval_id), "decision": decision,
                "flow_id": flow_id, "queue_id": queue_id, "mission_id": mission_id}

    def flow_approval_state(self, flow_id: str) -> str:
        self._ensure_project()
        return store.flow_approval_outcome(str(flow_id))

    # ------------------------------------------------------------- control

    def _refresh_control_from_store(self) -> None:
        if self.run_id is None:
            return
        run = store.get_run(int(self.run_id))
        if run is None:
            return
        if int(run.get("stop_requested") or 0) and not self.control.stop_requested:
            self.control.request_stop("stop requested through supervisor_runs flag")
        if int(run.get("pause_requested") or 0) and not self.control.pause_requested:
            self.control.request_pause()

    def _process_commands(self) -> None:
        if self.project_id is None:
            return
        pending = store.take_pending_commands(int(self.project_id), self.run_id)
        for command in pending:
            name = str(command.get("command") or "").lower()
            if name == "stop":
                reason = "stop command #" + str(command.get("id")) + " by " + str(command.get("requested_by"))
                if not self.control.stop_requested:
                    self.control.request_stop(reason)
                if self.run_id is not None:
                    store.set_run_flags(int(self.run_id), stop=True)
                self._event("Stop requested: " + reason, kind="command")
            elif name == "pause":
                self.control.request_pause()
                if self.run_id is not None:
                    store.set_run_flags(int(self.run_id), pause=True)
                self._event("Pause requested (honoured at the mission boundary)", kind="command")
            elif name == "resume":
                self.control.clear_pause()
                if self.run_id is not None:
                    store.set_run_flags(int(self.run_id), pause=False)
                self._event("Resume requested", kind="command")
        self._refresh_control_from_store()

    def request_stop(self, *, requested_by: str = "human", reason: str = "") -> dict:
        self._ensure_project()
        run = store.get_active_run(int(self.project_id))
        run_id = int(run["id"]) if run is not None else None
        command_id = store.request_command(
            int(self.project_id), "stop", requested_by=requested_by, run_id=run_id,
        )
        if run_id is not None:
            store.set_run_flags(run_id, stop=True)
        self.control.request_stop(reason or ("stop requested by " + str(requested_by)))
        self._event("Stop command accepted", kind="command",
                    payload={"run_id": run_id, "command_id": command_id})
        return {"ok": True, "command_id": command_id, "run_id": run_id}

    def request_pause(self, *, requested_by: str = "human") -> dict:
        self._ensure_project()
        run = store.get_active_run(int(self.project_id))
        run_id = int(run["id"]) if run is not None else None
        command_id = store.request_command(
            int(self.project_id), "pause", requested_by=requested_by, run_id=run_id,
        )
        if run_id is not None:
            store.set_run_flags(run_id, pause=True)
        self.control.request_pause()
        self._event("Pause command accepted", kind="command",
                    payload={"run_id": run_id, "command_id": command_id})
        return {"ok": True, "command_id": command_id, "run_id": run_id}

    # ----------------------------------------------------------- execution

    def _build_orchestrator(self):
        if self.orchestrator_factory is not None:
            return self.orchestrator_factory(self.root)
        from nl_coding_agent.agents.orchestrator import MultiAgentOrchestrator

        return MultiAgentOrchestrator(self.root, project_id=self.project_id)

    def _reconcile_flow_runs(self, *, exclude_mission_ids=()) -> list[str]:
        """Finalize provably abandoned Flow rows; never touch a live owner."""
        project_id = int(self.project_id)
        active: list[str] = []
        runner = self._flow_runner
        if runner is not None:
            try:
                active = list(runner.active_flow_ids())
            except Exception:
                active = []
        try:
            actions = store.reconcile_flow_runs(
                project_id=project_id, active_flow_ids=active,
                exclude_mission_ids=exclude_mission_ids,
            )
        except Exception as exc:
            self._event("Flow reconciliation failed: " + str(exc), level="warning",
                        kind="flow-reconciliation")
            return []
        for action in actions:
            self._event(action, kind="flow-reconciliation")
        return actions

    def _finalize_unexpected_failure(self, mission_id: int, exc: Exception,
                                     *, source: str, method: str,
                                     flow_id: str | None = None) -> dict:
        """Persist traceback + fail mission coherently after an escaped exception."""
        from nl_coding_agent.core.failure_evidence import (
            capture_exception,
            record_exception,
            record_running_task_failures,
        )

        payload = capture_exception(
            exc, source=source, method=method, mission_id=mission_id,
            flow_id=flow_id, phase="supervisor",
        )
        record_exception(
            mission_id, exc, source=source, method=method,
            flow_id=flow_id, phase="supervisor",
        )
        record_running_task_failures(
            mission_id, exc, source=source,
            traceback_text=payload.get("traceback") or "",
        )
        executor = self._executors.get(int(mission_id))
        result: dict | None = None
        if executor is not None:
            try:
                result = executor.finalize({
                    "status": "failed",
                    "error": payload["exception_type"] + ": " + payload["message"],
                    "error_code": "executor_exception",
                    "failure_stage": method,
                    "exception_type": payload["exception_type"],
                    "error_traceback": payload["traceback"],
                })
            except Exception:
                result = None
        if result is None:
            from nl_coding_agent.persistence.missions import (
                update_mission_result,
            )
            summary = ("Mission failed during " + source + "/" + method + ": "
                       + payload["exception_type"] + ": " + payload["message"])
            try:
                update_mission_result(
                    mission_id, "failed", result_summary=summary,
                    review_verdict=None, diff_stat="", changed_paths=[],
                )
            except Exception:
                pass
            result = {"status": "failed", "mission_id": int(mission_id),
                      "error": summary, "code": "executor_exception",
                      "flow_id": flow_id}
        if flow_id:
            try:
                store.finish_flow_run(
                    flow_id, "FAILED", error_code="executor_exception",
                    error_message=payload["exception_type"] + ": " + payload["message"],
                    last_method="exception",
                )
            except Exception:
                pass
        return result

    def _build_executor(self, mission_id: int, goal: str):
        """Return the MissionStageExecutor for flow mode, or None (sequential)."""
        if self.config.pipeline == "sequential":
            return None
        key = int(mission_id)
        cached = self._executors.get(key)
        if cached is not None:
            return cached
        from nl_coding_agent.agents.supervisor_executor import SupervisorMissionExecutor

        executor = SupervisorMissionExecutor(
            self._build_orchestrator(), key, str(goal or ""),
            control=self.control,
            developer_model=self.config.developer_model,
            reviewer_model=self.config.reviewer_model,
            debug_model=self.config.debug_model,
            architect_model=self.config.architect_model,
        )
        self._executors[key] = executor
        return executor

    def _invoke_mission(self, mission_id: int, goal: str | None) -> dict:
        """Dispatch to the configured pipeline (sequential default remains untouched)."""
        with self.control.observe_mission_stop(mission_id):
            if str(self.config.pipeline) == "flow":
                return self._invoke_flow_mission(mission_id, goal)
            return self._invoke_orchestrator(mission_id, goal)

    def _invoke_flow_mission(self, mission_id: int, goal: str | None) -> dict:
        """Execute one mission through MissionFlow; the supervisor finalizes status."""
        mission = get_mission(mission_id) or {}
        effective_goal = str(goal or mission.get("goal") or "").strip()
        from nl_coding_agent.flows.supervisor_flow import SupervisorRunFlow

        executor = None
        result = None
        try:
            self._reconcile_flow_runs(exclude_mission_ids=(int(mission_id),))
            mark_mission_started(int(mission_id))
            with mission_lock(int(mission_id)):
                if self._flow_runner is None:
                    self._flow_runner = SupervisorRunFlow(self)
                outcome = self._flow_runner.run_mission(int(mission_id), effective_goal)
                executor = outcome.get("executor")
                if executor is None:
                    current = get_mission(int(mission_id)) or {}
                    result = {
                        "status": str(current.get("status") or "interrupted"),
                        "mission_id": int(mission_id),
                        "pipeline": "flow",
                        "error": current.get("result_summary"),
                    }
                else:
                    result = executor.finalize(outcome.get("flow_result") or {})
        except RunStopped as exc:
            if executor is None:
                executor = self._executors.get(int(mission_id))
            try:
                result = (executor.finalize({"status": "interrupted", "error": str(exc)})
                          if executor is not None
                          else {"status": "interrupted", "error": str(exc)})
            except Exception:
                result = {"status": "interrupted", "error": str(exc)}
        except MissionLockError as exc:
            update_mission_status(int(mission_id), "blocked")
            result = {"status": "blocked", "error": str(exc), "code": "mission-lock"}
        except Exception as exc:  # noqa: BLE001 - classified by the supervisor
            from nl_coding_agent.core.permissions import PermissionDenied

            if isinstance(exc, PermissionDenied):
                try:
                    update_mission_status(int(mission_id), "blocked")
                except Exception:
                    pass
                result = {"status": "blocked", "error": "Permission denied: " + str(exc),
                          "code": "permission-denied"}
            else:
                result = self._finalize_unexpected_failure(
                    int(mission_id), exc, source="supervisor",
                    method="_invoke_flow_mission",
                    flow_id=(get_mission(int(mission_id)) or {}).get("flow_id"),
                )
        if not isinstance(result, dict):
            result = {"status": "failed", "error": "Flow executor returned a non-dict result"}
        result.setdefault("mission_id", int(mission_id))
        result["pipeline"] = "flow"
        return result

    def _invoke_orchestrator(self, mission_id: int, goal: str | None) -> dict:
        mission = get_mission(mission_id) or {}
        effective_goal = str(goal or mission.get("goal") or "").strip()
        try:
            orchestrator = self._build_orchestrator()
            result = orchestrator.run_mission(
                mission_id=int(mission_id),
                goal=effective_goal,
                developer_model=self.config.developer_model,
                reviewer_model=self.config.reviewer_model,
                debug_model=self.config.debug_model,
                architect_model=self.config.architect_model,
                control=self.control,
            )
        except RunStopped as exc:
            return {"status": "interrupted", "error": str(exc), "mission_id": mission_id}
        except Exception as exc:  # noqa: BLE001 - classified by the supervisor
            from nl_coding_agent.core.permissions import PermissionDenied

            if isinstance(exc, PermissionDenied):
                return {
                    "status": "blocked",
                    "error": "Permission denied: " + str(exc),
                    "code": "permission-denied",
                    "mission_id": mission_id,
                }
            return {
                "status": "failed",
                "error": str(exc),
                "code": type(exc).__name__,
                "mission_id": mission_id,
            }
        if not isinstance(result, dict):
            return {"status": "failed", "error": "Orchestrator returned a non-dict result",
                    "mission_id": mission_id}
        result.setdefault("mission_id", mission_id)
        return result

    def execute_mission(self, mission_id: int) -> dict:
        """Execute one mission via the orchestrator (resource slot + permissions enforced)."""
        self._ensure_project()
        decision = self._resource_decider(self.config, project_id=int(self.project_id))
        if decision.action != "run":
            return {"status": "blocked" if decision.action == "blocked" else "waiting_for_resources",
                    "error": decision.reason, "mission_id": int(mission_id)}
        acquired = resource_gate.acquire_inference_slot(
            self.owner_id, self.owner_pid, self.owner_host,
            ttl_s=float(self.config.lease_ttl_s),
        )
        if not acquired:
            return {"status": "waiting_for_resources",
                    "error": "Machine inference slot is busy.", "mission_id": int(mission_id)}
        self._adopt_machine_lease()
        heartbeat_owned = self._heartbeat_thread is None or not self._heartbeat_thread.is_alive()
        if heartbeat_owned:
            self._start_heartbeat()
        try:
            return self._invoke_mission(int(mission_id), None)
        finally:
            if heartbeat_owned:
                self._stop_heartbeat()
            resource_gate.release_inference_slot(self.owner_id)
            self.machine_lease = None

    def _ensure_mission(self, item: dict, token: str) -> int:
        queue_id = int(item["id"])
        if (item.get("payload") or {}).get("work_source") == "goals":
            return store.bind_goal_mission(
                queue_id, project_id=int(self.project_id), claim_token=token,
                supervisor_run_id=self.run_id)
        mission_id = item.get("mission_id")
        if mission_id:
            mission = get_mission(int(mission_id))
            if mission is not None:
                return int(mission["id"])
        requirement_id = item.get("requirement_id")
        if requirement_id:
            adopted = get_active_mission_for_requirement(str(requirement_id))
            if adopted is not None:
                mission_id = int(adopted["id"])
                store.update_queue_item(queue_id, claim_token=token, mission_id=mission_id)
                return mission_id
        payload = dict(item.get("payload") or {})
        title = str(payload.get("title") or (
            "[" + str(requirement_id) + "] supervised mission"
            if requirement_id else "Supervised mission #" + str(queue_id)
        ))[:200]
        mission_id = create_mission(
            int(self.project_id), title, str(item.get("goal") or ""),
            requirement_id=str(requirement_id) if requirement_id else None,
            supervisor_run_id=self.run_id,
        )
        store.update_queue_item(queue_id, claim_token=token, mission_id=int(mission_id))
        self._event("Created mission #" + str(mission_id) + " for queue #" + str(queue_id),
                    kind="mission", mission_id=int(mission_id),
                    payload={"requirement_id": requirement_id})
        return int(mission_id)

    def _next_queue_item(self) -> dict | None:
        project_id = int(self.project_id)
        items = store.list_queue(project_id)
        filtered = []
        for item in items:
            source = (item.get("payload") or {}).get("work_source", "backlog")
            if source != self.config.work_source:
                continue
            if source == "goals":
                from nl_coding_agent.core.goals import GoalService
                allowed, reason = GoalService().execution_context(item["payload"], project_id)
                if not allowed:
                    if item["state"] not in store.QUEUE_TERMINAL_STATES:
                        self._event("Goal execution deferred: " + reason, kind="goal-deferred",
                                    payload={"queue_id": item["id"], "reason": reason})
                    continue
            filtered.append(item)
        items = filtered
        for state in RESUMABLE_QUEUE_STATES:
            for item in items:
                if str(item["state"]) == state:
                    return item
        for item in items:
            if str(item["state"]) in ("READY", "NEEDS_FIX", "INTERRUPTED"):
                return item
        queue_id = self.enqueue_next()
        if queue_id is None:
            return None
        return store.get_queue_item(int(queue_id))

    def _remaining_backoff(self, item: dict) -> float:
        scheduled = str(item.get("scheduled_at") or "")
        if not scheduled:
            return 0.0
        try:
            target = datetime.fromisoformat(scheduled)
        except ValueError:
            return 0.0
        return max(0.0, (target - datetime.now()).total_seconds())

    def execute_queue_item(self, queue_item: dict) -> Outcome:
        project_id = int(self.project_id)
        fresh = store.get_queue_item(int(queue_item["id"])) or dict(queue_item)
        if str(fresh["state"]) not in store.QUEUE_CLAIMABLE_STATES:
            return Outcome(None, "NOT_CLAIMABLE", None, None,
                           {"state": str(fresh["state"])})

        if (fresh.get("payload") or {}).get("work_source") == "goals":
            from nl_coding_agent.core.goals import GoalService
            allowed, reason = GoalService().execution_context(fresh["payload"], project_id)
            if not allowed:
                return Outcome("BLOCKED", "HARD_BLOCK", None, None, {"error": reason})
        decision = self._resource_decider(self.config, project_id=project_id)
        if decision.action == "wait":
            return Outcome("WAIT_RESOURCE", "WAIT_RESOURCE", None,
                           int(decision.retry_after_s or 0), {"resource": decision.to_dict()})
        if decision.action == "blocked":
            return Outcome("WAIT_APPROVAL", "WAIT_APPROVAL", None, None,
                           {"resource": decision.to_dict()})
        if not resource_gate.acquire_inference_slot(
            self.owner_id, self.owner_pid, self.owner_host,
            ttl_s=float(self.config.lease_ttl_s),
        ):
            return Outcome("WAIT_RESOURCE", "WAIT_RESOURCE", None,
                           int(self.config.backoff_schedule_s[0]),
                           {"reason": "Machine inference slot is busy."})
        self._adopt_machine_lease()
        # Reuse a durable claim token when re-claiming a retried/resumed row; the queue
        # CAS accepts NULL-or-matching tokens and this supervisor owns the lease.
        token = str(fresh.get("claim_token") or uuid.uuid4().hex)
        try:
            if not store.claim_queue_item(int(fresh["id"]), claim_token=token,
                                          owner_id=self.owner_id):
                return Outcome(None, "CLAIM_LOST", None, None,
                               {"error": "Queue claim was lost before execution."})
            mission_id = self._ensure_mission(fresh, token)
            if not store.update_queue_item(
                int(fresh["id"]), claim_token=token, state="RUNNING",
                mission_id=mission_id, increment_attempts=True,
            ):
                return Outcome(None, "CLAIM_LOST", None, None,
                               {"error": "Queue transition to RUNNING failed."})
            self._set_backlog(fresh.get("requirement_id"), "IN_FLIGHT", mission_id)
            self._event(
                "Starting mission #" + str(mission_id) + " for queue #" + str(fresh["id"]),
                kind="mission", mission_id=mission_id,
                payload={"requirement_id": fresh.get("requirement_id")},
            )
            self._active_goal_item = (fresh if (fresh.get("payload") or {}).get("work_source") == "goals"
                                      else None)
            result = self._invoke_mission(mission_id, str(fresh.get("goal") or ""))
            if self._active_goal_item is not None and result.get("status") == "completed":
                from nl_coding_agent.core.goals import GoalService
                if not GoalService.mission_verified(mission_id):
                    return Outcome("BLOCKED", "HARD_BLOCK", None, None,
                                   {"status": "blocked", "error": "Goal mission lacks independent harness evidence"})
            return self.classify(result)
        finally:
            self._active_goal_item = None
            resource_gate.release_inference_slot(self.owner_id)
            self.machine_lease = None

    # --------------------------------------------------------- classification

    def _failure_signature(self, result: dict, failure_class: str) -> str:
        failing: list[str] = []
        for run in (result.get("verification_runs") or []):
            try:
                if int(run.get("passed") or 0) == 0:
                    failing.append(str(run.get("command") or ""))
            except (TypeError, ValueError):
                continue
        material = "|".join((
            failure_class,
            str(result.get("status") or ""),
            str(result.get("promotion_status") or ""),
            str(result.get("code") or ""),
            re.sub(r"\d+", "#", str(result.get("error") or ""))[:800],
            "|".join(sorted(failing)),
        ))
        return _sha256_text(material)

    def classify(self, mission_result: dict) -> Outcome:
        result = dict(mission_result or {})
        status = str(result.get("status") or "failed").strip().lower()
        if status == "completed":
            return Outcome("VERIFIED", "VERIFIED", None, None, result)
        if status == "interrupted":
            return Outcome("INTERRUPTED", "INTERRUPTED", None, None, result)
        error = str(result.get("error") or "")
        lowered = error.lower()
        promotion_status = str(result.get("promotion_status") or "").lower()
        if any(token in lowered for token in APPROVAL_TOKENS) or promotion_status in (
            "not_verified", "not-verified"
        ):
            failure_class = "WAIT_APPROVAL"
        elif any(token in lowered for token in RESOURCE_TOKENS):
            failure_class = "WAIT_RESOURCE"
        elif promotion_status in HARD_BLOCK_CODES or any(
            token in lowered for token in HARD_BLOCK_CODES
        ):
            failure_class = "HARD_BLOCK"
        elif any(token in lowered for token in REPAIRABLE_TOKENS):
            failure_class = "REPAIRABLE"
        elif status == "blocked":
            failure_class = "HARD_BLOCK"
        else:
            failure_class = "REPAIRABLE"
        signature = self._failure_signature(result, failure_class)
        queue_state = {
            "REPAIRABLE": "NEEDS_FIX",
            "HARD_BLOCK": "BLOCKED",
        }.get(failure_class)
        retry_after = None
        if failure_class == "WAIT_RESOURCE":
            retry_after = int(self.config.backoff_schedule_s[0])
        return Outcome(queue_state, failure_class, signature, retry_after, result)

    # ------------------------------------------------------------- evidence

    def _record_evidence(self, mission_id: int, queue_id: int | None, kind: str,
                         payload: dict, *, record_key: str | None = None,
                         sha256: str | None = None, path: str | None = None) -> None:
        try:
            store.record_evidence(
                int(mission_id), kind=kind,
                record_key=record_key or kind,
                payload=payload, queue_id=queue_id, sha256=sha256, path=path,
            )
        except Exception as exc:
            self._event("Evidence write failed: " + str(exc), level="warning", kind="evidence")

    def _record_result_evidence(self, mission_id: int, queue_id: int,
                                outcome: Outcome) -> None:
        result = dict(outcome.mission_result or {})
        changed = list(result.get("changed_paths") or [])
        diff = str(result.get("mission_diff") or "")
        self._record_evidence(
            mission_id, queue_id, "diff",
            {"changed_paths": changed, "diff_stat": str(result.get("diff_stat") or ""),
             "sha256": _sha256_text(diff)},
            record_key="diff", sha256=_sha256_text(diff),
        )
        verification = []
        for run in (result.get("verification_runs") or []):
            verification.append({
                "command": str(run.get("command") or ""),
                "passed": bool(run.get("passed")),
                "exit_code": run.get("exit_code"),
            })
        self._record_evidence(
            mission_id, queue_id, "verification",
            {"passed": bool(result.get("status") == "completed"),
             "runs": verification},
            record_key="verification",
        )
        promotion_status = str(result.get("promotion_status") or "")
        if str(result.get("status") or "") == "completed" or result.get("verdict"):
            self._record_evidence(
                mission_id, queue_id, "review",
                {"verdict": str(result.get("verdict") or ""),
                 "notes": _truncate(str(result.get("review") or ""), 2000)},
                record_key="review",
            )
        if str(result.get("status") or "") == "completed" or promotion_status in (
            "promoted", "promoting", "cas_conflict", "cas-conflict",
            "rollback_conflict", "rollback-conflict", "promotion_failed",
        ):
            self._record_evidence(
                mission_id, queue_id, "promotion",
                {"promotion_status": promotion_status,
                 "changed_paths": changed},
                record_key="promotion",
            )
        if outcome.failure_class and outcome.failure_class != "VERIFIED":
            if outcome.failure_class == "BUDGET_EXHAUSTED":
                self._record_evidence(
                    mission_id, queue_id, "budget",
                    {"failure_class": outcome.failure_class,
                     "failure_signature": outcome.failure_signature,
                     "reason": _truncate(str(result.get("error") or ""))},
                    record_key="budget",
                )
            self._record_evidence(
                mission_id, queue_id, "failure",
                {"failure_class": outcome.failure_class,
                 "failure_signature": outcome.failure_signature,
                 "reason": _truncate(str(result.get("error") or ""), 2000)},
                record_key="failure",
            )

    # ------------------------------------------------------------ outcomes

    def _create_approval_for_outcome(self, queue_item: dict, outcome: Outcome) -> None:
        result = outcome.mission_result or {}
        error = str(result.get("error") or "").lower()
        action = "cloud" if "cloud" in error else "network"
        try:
            store.create_approval(
                int(self.project_id), action=action,
                scope={"requirement_id": queue_item.get("requirement_id"),
                       "queue_id": queue_item.get("id"),
                       "reason": _truncate(str(result.get("error") or ""), 500)},
                reason="Supervisor requested escalation for a blocked model route.",
                mission_id=queue_item.get("mission_id"),
                requested_by="supervisor",
            )
        except Exception as exc:
            self._event("Could not create approval request: " + str(exc),
                        level="warning", kind="approval")

    def record_outcome(self, queue_item: dict, outcome: Outcome) -> dict:
        """Persist queue/backlog/evidence/run transitions for one mission outcome."""
        queue_id = int(queue_item["id"])
        fresh = store.get_queue_item(queue_id) or dict(queue_item)
        token = fresh.get("claim_token")
        mission_id = fresh.get("mission_id")
        requirement_id = fresh.get("requirement_id")
        result = dict(outcome.mission_result or {})
        attempts = int(fresh.get("attempts") or 0)
        max_attempts = int(fresh.get("max_attempts") or self.config.max_attempts_per_requirement)
        notification: dict = {
            "id": mission_id,
            "queue_id": queue_id,
            "requirement_id": requirement_id,
            "status": result.get("status"),
            "verdict": result.get("verdict"),
            "diff_stat": result.get("diff_stat"),
            "error": result.get("error"),
            "queue_state": outcome.queue_state,
            "failure_class": outcome.failure_class,
        }

        if outcome.failure_class in ("CLAIM_LOST", "NOT_CLAIMABLE"):
            self._event("Queue row is not claimable yet ("
                         + str(outcome.failure_class) + "); it will be reconciled",
                         level="warning", kind="queue")
            return notification

        if outcome.queue_state == "VERIFIED":
            self._transition(queue_id, "VERIFIED", token=token, mission_id=mission_id)
            self._set_backlog(requirement_id, "VERIFIED", mission_id)
            if (fresh.get("payload") or {}).get("work_source") == "goals":
                from nl_coding_agent.core.goals import GoalService
                accepted = GoalService().accept_execution(fresh)
                notification["milestone_verified"] = accepted
            self._completed += 1
            store.update_run(int(self.run_id), missions_completed=self._completed)
            if mission_id:
                self._record_result_evidence(int(mission_id), queue_id, outcome)
            self._event("Mission completed and verified", kind="outcome",
                        mission_id=mission_id, payload=notification)
            return notification

        if outcome.queue_state == "INTERRUPTED":
            self._transition(queue_id, "INTERRUPTED", token=token, mission_id=mission_id)
            self._set_backlog(requirement_id, "IN_FLIGHT", mission_id)
            self._event("Mission interrupted at a safe point; candidate retained",
                        level="warning", kind="outcome", mission_id=mission_id,
                        payload=notification)
            return notification

        if outcome.failure_class == "WAIT_RESOURCE":
            self._transition(queue_id, "INTERRUPTED", token=token, mission_id=mission_id,
                             failure_class="WAIT_RESOURCE",
                             failure_signature=outcome.failure_signature)
            self._set_backlog(requirement_id, "IN_FLIGHT", mission_id)
            self._event("Waiting for local resources; checkpoint kept",
                        level="warning", kind="outcome", mission_id=mission_id,
                        payload=notification)
            return notification

        if outcome.failure_class == "WAIT_APPROVAL":
            self._transition(queue_id, "INTERRUPTED", token=token, mission_id=mission_id,
                             failure_class="WAIT_APPROVAL",
                             failure_signature=outcome.failure_signature)
            self._set_backlog(requirement_id, "IN_FLIGHT", mission_id)
            self._create_approval_for_outcome(fresh, outcome)
            self._event("Waiting for human approval before the next attempt",
                        level="warning", kind="outcome", mission_id=mission_id,
                        payload=notification)
            return notification

        if outcome.failure_class == "REPAIRABLE":
            if attempts >= max_attempts:
                outcome.failure_class = "BUDGET_EXHAUSTED"
                outcome.queue_state = "BLOCKED"
                self._transition(queue_id, "BLOCKED", token=token, mission_id=mission_id,
                                 failure_class="BUDGET_EXHAUSTED",
                                 failure_signature=outcome.failure_signature)
                self._set_backlog(requirement_id, "BLOCKED", mission_id,
                                  note="attempt budget exhausted")
                self._failed += 1
                store.update_run(int(self.run_id), missions_failed=self._failed)
                if mission_id:
                    self._record_result_evidence(int(mission_id), queue_id, outcome)
                notification["queue_state"] = "BLOCKED"
                notification["failure_class"] = "BUDGET_EXHAUSTED"
                self._event("Requirement blocked: attempt budget exhausted",
                            level="warning", kind="outcome", mission_id=mission_id,
                            payload=notification)
                return notification
            delay = 0
            try:
                schedule = [int(item) for item in self.config.backoff_schedule_s]
                index = min(max(attempts - 1, 0), len(schedule) - 1)
                delay = max(0, schedule[index])
            except (TypeError, ValueError):
                delay = 0
            scheduled_at = None
            if delay:
                from datetime import timedelta

                scheduled_at = (datetime.now() + timedelta(seconds=delay)).isoformat(timespec="seconds")
            self._transition(queue_id, "NEEDS_FIX", token=token, mission_id=mission_id,
                             failure_class="REPAIRABLE",
                             failure_signature=outcome.failure_signature)
            self._transition(queue_id, "READY", token=token, mission_id=mission_id,
                             extra={"scheduled_at": scheduled_at})
            self._set_backlog(requirement_id, "NEEDS_FIX", mission_id)
            self._failed += 1
            store.update_run(int(self.run_id), missions_failed=self._failed)
            if mission_id:
                self._record_result_evidence(int(mission_id), queue_id, outcome)
            self._event("Repairable failure; re-queued after backoff",
                        level="warning", kind="outcome", mission_id=mission_id,
                        payload=notification)
            return notification

        # HARD_BLOCK / BUDGET_EXHAUSTED / unknown -> terminal blocked, fail-fast
        if outcome.failure_class not in ("HARD_BLOCK", "BUDGET_EXHAUSTED"):
            outcome.failure_class = "HARD_BLOCK"
        self._transition(queue_id, "BLOCKED", token=token, mission_id=mission_id,
                         failure_class=outcome.failure_class,
                         failure_signature=outcome.failure_signature)
        self._set_backlog(requirement_id, "BLOCKED", mission_id,
                          note=_truncate(str(result.get("error") or ""), 500))
        self._failed += 1
        store.update_run(int(self.run_id), missions_failed=self._failed)
        if mission_id:
            self._record_result_evidence(int(mission_id), queue_id, outcome)
        notification["failure_class"] = outcome.failure_class
        notification["queue_state"] = "BLOCKED"
        self._event("Requirement blocked (fail-fast)", level="warning", kind="outcome",
                    mission_id=mission_id, payload=notification)
        return notification

    # ------------------------------------------------------------------ loop

    def tick(self) -> dict:
        """Run one loop iteration (select/claim/execute/record or a wait state)."""
        self._process_commands()
        if self._lease_lost:
            return {"status": "lease-lost", "reason": "lease lost"}
        if self.control.stop_requested:
            return {"status": "stopped", "reason": self.control.stop_reason or "stop requested"}
        if self.control.pause_requested:
            return {"status": "paused", "reason": "pause requested"}
        decision = self._resource_decider(self.config, project_id=int(self.project_id))
        if decision.action == "wait":
            return {"status": "waiting_for_resources", "reason": decision.reason,
                    "retry_after_s": decision.retry_after_s}
        if decision.action == "blocked":
            return {"status": "blocked", "reason": decision.reason}
        queue_item = self._next_queue_item()
        if queue_item is None:
            return {"status": "idle" if self.config.work_source == "goals" else "completed",
                    "reason": "No eligible approved work remains."}
        remaining = self._remaining_backoff(queue_item)
        if remaining > 0:
            time.sleep(min(remaining, 5.0))
        outcome = self.execute_queue_item(queue_item)
        if self._lease_lost:
            return {"status": "lease-lost", "reason": "lease lost",
                    "outcome": outcome.to_dict()}
        record = self.record_outcome(queue_item, outcome)
        return {
            "status": "mission",
            "outcome": outcome.to_dict(),
            "record": record,
            "queue_state": outcome.queue_state,
            "failure_class": outcome.failure_class,
            "retry_after_s": outcome.retry_after_s,
        }

    def run(self, *, max_missions: int | None = None) -> dict:
        self._ensure_project()
        if self.config.mode == "off":
            return {
                "status": "off", "mode": "off", "project_id": self.project_id,
                "root": str(self.root), "missions": [],
                "stopped_reason": "Autonomy mode is off.",
                "resume_command": self._resume_command(),
            }
        report = self.preflight()
        if not report.ok:
            return {
                "status": "blocked", "mode": self.config.mode,
                "project_id": self.project_id, "root": str(self.root),
                "missions": [], "preflight": report.to_dict(),
                "stopped_reason": "; ".join(report.blockers),
                "resume_command": report.resume_command or self._resume_command(),
            }
        try:
            self.acquire()
        except LeaseConflict as exc:
            return {
                "status": "already-running", "mode": self.config.mode,
                "project_id": self.project_id, "root": str(self.root),
                "missions": [], "error": str(exc),
                "stopped_reason": str(exc),
                "resume_command": "python\\python.exe nl_agent.py supervisor status --project \""
                                  + str(self.root) + "\"",
            }

        limit = int(max_missions or self.config.max_missions_per_run)
        self.run_id = store.start_run(
            int(self.project_id), mode=self.config.mode,
            config=self.config.to_dict(), owner_id=self.owner_id,
            owner_pid=self.owner_pid,
        )
        self._event("Supervisor run started", kind="run-start",
                    payload={"mode": self.config.mode, "limit": limit})
        recovery: list[str] = []
        status = "completed"
        reason = ""
        retry_after: int | None = None
        try:
            store.update_run(int(self.run_id), status="RECOVERING")
            recovery = self.reconcile()
            store.update_run(int(self.run_id), status="RUNNING", heartbeat_at=_now())
            self._start_heartbeat()
            deadline = self._clock() + float(self.config.max_wall_time_s)
            consecutive_failures = 0
            while True:
                self._process_commands()
                if self._lease_lost:
                    status = "lease-lost"
                    reason = "Supervisor lease lost; another owner must reconcile."
                    break
                if self.control.stop_requested:
                    status = "stopped"
                    reason = self.control.stop_reason or "stop requested"
                    break
                if self.control.pause_requested:
                    status = "paused"
                    reason = "Pause requested; honoured at the mission boundary."
                    break
                if self._clock() >= deadline:
                    status = "stopped"
                    reason = "Wall-clock budget exhausted; resume to continue."
                    break
                if self._completed >= limit:
                    status = "completed"
                    reason = "Reached the requested limit of " + str(limit) + " mission(s)."
                    break
                decision = self._resource_decider(self.config, project_id=int(self.project_id))
                if decision.action == "wait":
                    status = "waiting_for_resources"
                    reason = decision.reason
                    retry_after = decision.retry_after_s
                    break
                if decision.action == "blocked":
                    status = "blocked"
                    reason = decision.reason
                    break
                queue_item = self._next_queue_item()
                if queue_item is None:
                    status = "idle" if self.config.work_source == "goals" else "completed"
                    reason = "No eligible approved work remains for " + self.config.work_source
                    break
                remaining = self._remaining_backoff(queue_item)
                if remaining > 0:
                    time.sleep(min(remaining, 5.0))
                outcome = self.execute_queue_item(queue_item)
                if self._lease_lost:
                    status = "lease-lost"
                    reason = "Supervisor lease lost; another owner must reconcile."
                    break
                record = self.record_outcome(queue_item, outcome)
                self._results.append(record)
                if outcome.queue_state == "VERIFIED":
                    consecutive_failures = 0
                    continue
                if outcome.queue_state == "INTERRUPTED":
                    if self.control.pause_requested:
                        status = "paused"
                        reason = "Pause honoured after mission interruption."
                    else:
                        status = "stopped"
                        reason = "Mission interrupted at a safe checkpoint."
                    break
                if outcome.failure_class == "WAIT_RESOURCE":
                    status = "waiting_for_resources"
                    reason = str((outcome.mission_result or {}).get("error") or "resources unavailable")
                    retry_after = outcome.retry_after_s
                    break
                if outcome.failure_class == "WAIT_APPROVAL":
                    status = "waiting_for_approval"
                    reason = "Human approval required (cloud/network/risky action)."
                    break
                if outcome.failure_class in ("HARD_BLOCK", "BUDGET_EXHAUSTED"):
                    status = "blocked"
                    reason = "Requirement blocked; fail-fast (no unrelated work started)."
                    break
                if outcome.failure_class == "REPAIRABLE":
                    consecutive_failures += 1
                    if consecutive_failures >= int(self.config.max_consecutive_failures):
                        status = "blocked"
                        reason = "Consecutive failure budget exhausted."
                        break
                    continue
                if outcome.failure_class in ("CLAIM_LOST", "NOT_CLAIMABLE"):
                    consecutive_failures += 1
                    if consecutive_failures >= int(self.config.max_consecutive_failures):
                        status = "blocked"
                        reason = "Repeated queue claim losses."
                        break
                    self.reconcile()
                    continue
                status = "blocked"
                reason = "Unclassified mission outcome; stopping fail-closed."
                break
        except SupervisorBlocked as exc:
            status = "blocked"
            reason = str(exc)
        except Exception as exc:  # noqa: BLE001 - terminal fail-closed
            status = "blocked"
            reason = "Supervisor error: " + str(exc)
            self._event(reason, level="error", kind="error")
        finally:
            self._stop_heartbeat()
            try:
                store.update_run(
                    int(self.run_id), missions_completed=self._completed,
                    missions_failed=self._failed,
                )
                if status == "paused":
                    store.update_run(int(self.run_id), status="PAUSED")
                if status == "lease-lost":
                    store.update_run(int(self.run_id), status="RECOVERING",
                                     stopped_reason=reason)
                terminal = {
                    "completed": "COMPLETED", "blocked": "BLOCKED",
                }.get(status, "STOPPED")
                if status == "lease-lost":
                    terminal = "STOPPED"
                store.finish_run(int(self.run_id), status=terminal, reason=reason)
            except Exception:
                pass
            self._event("Supervisor run finished: " + status + (
                " (" + reason + ")" if reason else ""), kind="run-end",
                payload={"status": status, "reason": reason,
                         "completed": self._completed, "failed": self._failed})
            self.release()

        final_run = store.get_run(int(self.run_id)) if self.run_id else None
        return {
            "status": status,
            "mode": self.config.mode,
            "project_id": self.project_id,
            "root": str(self.root),
            "run_id": self.run_id,
            "run": final_run,
            "missions": list(self._results),
            "completed": self._completed,
            "failed": self._failed,
            "recovery": recovery,
            "preflight": report.to_dict(),
            "stopped_reason": reason,
            "retry_after_s": retry_after,
            "resume_command": self._resume_command(),
            "queue": store.list_queue(int(self.project_id), limit=20),
            "pipeline": self.config.pipeline,
            "work_source": self.config.work_source,
            "flow_runs": store.list_flow_runs(project_id=int(self.project_id))[:20],
            "checkpoints": self.checkpoints,
        }

    def run_once(self) -> dict:
        return self.run(max_missions=1)


# --------------------------------------------------------------------------- #
# Module-level facade (CLI/GUI use this in C3d)
# --------------------------------------------------------------------------- #

def run_supervisor(
    project_root: str | Path,
    *,
    project_id: int | None = None,
    mode: str | None = None,
    max_missions: int | None = None,
    once: bool = False,
    developer_model: str | None = None,
    reviewer_model: str | None = None,
    debug_model: str | None = None,
    config_overrides: dict | None = None,
    orchestrator_factory: Callable | None = None,
    event_sink: Callable | None = None,
    control: RunControl | None = None,
    resource_decider: Callable | None = None,
    pipeline: str | None = None,
    work_source: str | None = None,
) -> dict:
    root = Path(project_root).resolve()
    if project_id is None:
        from nl_coding_agent.projects.registry import open_project

        project_id = int(open_project(root)["id"])
    overrides = dict(config_overrides or {})
    if mode is not None:
        overrides["mode"] = mode
    if max_missions is not None:
        overrides["max_missions_per_run"] = int(max_missions)
    for key, value in (("developer_model", developer_model),
                       ("reviewer_model", reviewer_model),
                       ("debug_model", debug_model)):
        if value is not None:
            overrides[key] = value
    if work_source is not None:
        overrides["work_source"] = str(work_source)
    if pipeline is not None:
        overrides["pipeline"] = str(pipeline)
    config = SupervisorConfig.load(project_id, overrides=overrides)
    supervisor = Supervisor(
        root, project_id=project_id, config=config,
        orchestrator_factory=orchestrator_factory, event_sink=event_sink,
        control=control, resource_decider=resource_decider,
    )
    if once:
        return supervisor.run_once()
    return supervisor.run(max_missions=max_missions)


def supervisor_status(project_root: str | Path, *, project_id: int | None = None) -> dict:
    root = Path(project_root).resolve()
    from nl_coding_agent.projects.registry import open_project

    if project_id is None:
        project_id = int(open_project(root)["id"])
    config = SupervisorConfig.load(project_id)
    return Supervisor(root, project_id=project_id, config=config).status()


def supervisor_command(project_root: str | Path, command: str, *,
                       requested_by: str = "cli", reason: str = "") -> dict:
    root = Path(project_root).resolve()
    from nl_coding_agent.projects.registry import open_project

    project_id = int(open_project(root)["id"])
    config = SupervisorConfig.load(project_id)
    supervisor = Supervisor(root, project_id=project_id, config=config)
    name = str(command or "").strip().lower()
    if name == "stop":
        return supervisor.request_stop(requested_by=requested_by, reason=reason)
    if name == "pause":
        return supervisor.request_pause(requested_by=requested_by)
    if name == "resume":
        run = store.get_active_run(project_id)
        run_id = int(run["id"]) if run is not None else None
        if run_id is not None:
            store.set_run_flags(run_id, pause=False, stop=False)
        command_id = store.request_command(
            project_id, "resume", requested_by=requested_by, run_id=run_id,
        )
        return {"ok": True, "command_id": command_id, "run_id": run_id}
    if name == "kick":
        run = store.get_active_run(project_id)
        command_id = store.request_command(
            project_id, "kick", requested_by=requested_by,
            run_id=int(run["id"]) if run is not None else None,
        )
        return {"ok": True, "command_id": command_id}
    if name == "status":
        return supervisor.status()
    raise SupervisorError("Unsupported supervisor command: " + repr(command))

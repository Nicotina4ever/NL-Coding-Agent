"""C4d: capability-aware role -> ModelBinding routing (no silent cloud fallback).

ModelRouter resolves project/global role bindings/fallback chain, filters by measured
capabilities and resource availability, and calls permissions.assert_model_permitted
before returning a binding; build_llm() is the only LLM construction point and repeats
the permission gate. Bindings are immutable snapshots with no secrets.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Callable, Mapping

from nl_coding_agent.core import permissions
from nl_coding_agent.core.permissions import PermissionDenied, is_cloud_model, is_remote_endpoint
from nl_coding_agent.models import capabilities as capabilities_module
from nl_coding_agent.persistence import database

__all__ = [
    "ModelBinding", "RouteRefused", "RouteResourceUnavailable",
    "ModelRouter", "binding_from_mapping", "historical_performance",
]


class RouteRefused(RuntimeError):
    """No permitted/available binding satisfies the role requirements."""

    def __init__(self, reason: str, *, missing_capabilities=(), refused=(),
                 wait_resource: bool = False) -> None:
        super().__init__(str(reason))
        self.reason = str(reason)
        self.missing_capabilities = tuple(missing_capabilities)
        self.refused = tuple(refused)
        self.wait_resource = bool(wait_resource)


class RouteResourceUnavailable(RouteRefused):
    """The selected binding exists but the inference resource is not available."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ModelBinding:
    role: str
    provider_id: str
    model_name: str
    base_url: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    capabilities: Mapping[str, Any] = field(default_factory=dict)
    capability_sources: Mapping[str, str] = field(default_factory=dict)
    source: str = "role_config"
    measured_at: str = ""
    config_sha256: str = ""
    selection: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.role or "").strip():
            raise ValueError("ModelBinding.role is required")
        if not str(self.model_name or "").strip():
            raise ValueError("ModelBinding.model_name is required")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params or {})))
        object.__setattr__(self, "capabilities", MappingProxyType(dict(self.capabilities or {})))
        object.__setattr__(self, "capability_sources", MappingProxyType(dict(self.capability_sources or {})))
        object.__setattr__(self, "selection", MappingProxyType(dict(self.selection or {})))

    @property
    def is_cloud(self) -> bool:
        return is_cloud_model(self.model_name) or is_remote_endpoint(self.base_url)

    def to_dict(self) -> dict:
        return {
            "role": self.role, "provider_id": self.provider_id,
            "model_name": self.model_name, "base_url": self.base_url,
            "params": dict(self.params),
            "capabilities": dict(self.capabilities),
            "capability_sources": dict(self.capability_sources),
            "source": self.source, "measured_at": self.measured_at,
            "config_sha256": self.config_sha256,
            "selection": dict(self.selection),
        }


def binding_from_mapping(role: str, data: Mapping[str, Any], *,
                         source: str = "role_config") -> ModelBinding:
    if not isinstance(data, Mapping):
        raise ValueError("Model binding must be a mapping")
    return ModelBinding(
        role=str(role), provider_id=str(data.get("provider_id") or "ollama"),
        model_name=str(data.get("model_name") or data.get("model") or ""),
        base_url=str(data.get("base_url") or ""),
        params=dict(data.get("params") or {}),
        capabilities=dict(data.get("capabilities") or {}),
        capability_sources=dict(data.get("capability_sources") or {}),
        source=str(data.get("source") or source),
        measured_at=str(data.get("measured_at") or ""),
        config_sha256=str(data.get("config_sha256") or ""),
        selection=dict(data.get("selection") or {}),
    )


def _role_config_hash(role_config: Mapping[str, Any]) -> str:
    payload = json.dumps(role_config, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def historical_performance(project_id: int | None = None) -> dict[str, dict]:
    """Aggregate real attempt outcomes by role+model for results-based selection.

    The source is the existing task_attempts metadata (model, duration, usage) joined
    to tasks/missions; no new store is created and missing cost is not invented.
    """
    database.init_db().close()
    conn = database.init_db()
    try:
        clauses = []
        params: list[Any] = []
        if project_id is not None:
            clauses.append("t.mission_id IN (SELECT id FROM missions WHERE project_id=?)")
            params.append(int(project_id))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            "SELECT t.agent_role, a.status AS attempt_status, a.metadata_json, "
            "m.review_verdict, m.promotion_status "
            "FROM task_attempts a JOIN tasks t ON t.id=a.task_id "
            "LEFT JOIN missions m ON m.id=t.mission_id" + where,
            tuple(params),
        ).fetchall()
    except Exception:
        return {}
    finally:
        conn.close()
    stats: dict[str, dict] = {}
    for row in rows:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
        except Exception:
            metadata = {}
        route = str(metadata.get("model") or "").strip()
        if not route:
            continue
        provider, _, model_name = route.partition("/")
        if not model_name:
            provider, model_name = "ollama", route
        role = str(row["agent_role"] or "")
        key = role + "::" + model_name
        item = stats.setdefault(key, {
            "role": role, "model_name": model_name, "provider_id": provider,
            "attempts": 0, "successes": 0, "failures": 0,
            "duration_total_s": 0.0, "duration_count": 0,
            "tokens_total": 0, "cost_usd": None,
            "approved_missions": 0,
        })
        item["attempts"] += 1
        if str(row["attempt_status"] or "") == "completed":
            item["successes"] += 1
        else:
            item["failures"] += 1
        duration = metadata.get("duration_s")
        if isinstance(duration, (int, float)):
            item["duration_total_s"] += float(duration)
            item["duration_count"] += 1
        usage = metadata.get("usage") or {}
        tokens = usage.get("total_tokens") if isinstance(usage, Mapping) else None
        if isinstance(tokens, (int, float)):
            item["tokens_total"] += int(tokens)
        cost = metadata.get("cost_usd")
        if isinstance(cost, (int, float)):
            item["cost_usd"] = float(item["cost_usd"] or 0.0) + float(cost)
        if str(row["review_verdict"] or "").upper() == "APPROVE":
            item["approved_missions"] += 1
    for item in stats.values():
        count = int(item["duration_count"] or 0)
        item["avg_duration_s"] = round(item["duration_total_s"] / count, 3) if count else None
        item["success_rate"] = round(item["successes"] / item["attempts"], 3) if item["attempts"] else 0.0
    return stats


class ModelRouter:
    """Deterministic role routing with capabilities + permissions + resource gate."""

    def __init__(self, *, role_bindings: Mapping[str, Any] | None = None,
                 fallback_chain: list[Any] | None = None,
                 project_roles: Mapping[str, Any] | None = None,
                 project_id: int | None = None,
                 capability_records: Mapping[tuple[str, str], Any] | None = None,
                 resource_gate: Callable[[], Any] | None = None) -> None:
        self.role_bindings = dict(role_bindings or {})
        self.project_roles = dict(project_roles or {})
        self.fallback_chain = list(fallback_chain or [])
        self.project_id = int(project_id) if project_id is not None else None
        self._capability_records = dict(capability_records or {})
        self.resource_gate = resource_gate
        self.refusals: list[dict] = []

    # ------------------------------------------------------------ resolution

    def _candidates(self, role: str, override: Mapping | None) -> list[ModelBinding]:
        candidates: list[ModelBinding] = []
        if override is not None:
            candidates.append(binding_from_mapping(role, override, source="explicit_override"))
            return candidates
        project = self.project_roles.get(role)
        if project is not None:
            candidates.append(binding_from_mapping(role, project, source="project_override"))
        configured = self.role_bindings.get(role)
        if configured is not None:
            candidates.append(binding_from_mapping(role, configured, source="role_config"))
        for item in self.fallback_chain:
            if isinstance(item, ModelBinding):
                candidates.append(item)
            elif isinstance(item, Mapping) and item.get("role") in (None, role):
                candidates.append(binding_from_mapping(role, item, source="fallback"))
        return candidates

    def _capabilities_for(self, binding: ModelBinding) -> capabilities_module.CapabilitySet:
        injected = self._capability_records.get(
            (binding.provider_id, binding.model_name)
        )
        return capabilities_module.load_capabilities(
            binding.provider_id, binding.model_name, records=injected,
        )

    def _check_resource(self) -> None:
        if self.resource_gate is None:
            return
        decision = self.resource_gate()
        if decision is None:
            return
        action = str(getattr(decision, "action", "run"))
        if action == "wait":
            raise RouteResourceUnavailable(
                "Inference resource unavailable: " + str(getattr(decision, "reason", "")),
                wait_resource=True,
            )
        if action == "blocked":
            raise RouteRefused(
                "Inference resource blocked: " + str(getattr(decision, "reason", "")),
            )

    def resolve(self, role: str, *, required_capabilities=(),
                override: Mapping | None = None) -> ModelBinding:
        self._check_resource()
        candidates = self._candidates(str(role), override)
        if not candidates:
            raise RouteRefused("No model binding configured for role " + repr(role))
        missing_all: list[str] = []
        permission_error: PermissionDenied | None = None
        refusals: list[str] = []
        for binding in candidates:
            capability_set = self._capabilities_for(binding)
            ok, missing = capability_set.satisfies(tuple(required_capabilities or ()))
            if not ok:
                missing_all.extend(missing)
                refusals.append(binding.model_name + ": missing " + ",".join(missing))
                continue
            try:
                permissions.assert_model_permitted(
                    binding.model_name, binding.base_url, self.project_id,
                )
            except PermissionDenied as exc:
                permission_error = exc
                refusals.append(binding.model_name + ": permission denied")
                continue
            snapshot = binding.to_dict()
            snapshot["capabilities"] = capability_set.to_dict()["capabilities"]
            snapshot["capability_sources"] = {
                name: str(entry.get("source") or "")
                for name, entry in snapshot["capabilities"].items()
            }
            snapshot["measured_at"] = _now_iso()
            snapshot["config_sha256"] = _role_config_hash(
                {"role": role, "binding": snapshot["model_name"],
                 "capabilities": snapshot["capabilities"]}
            )
            return ModelBinding(**snapshot)
        self.refusals.append({"role": str(role), "reasons": refusals})
        if permission_error is not None and not any(
            not (is_cloud_model(candidate.model_name) or is_remote_endpoint(candidate.base_url))
            for candidate in candidates
        ):
            raise permission_error
        raise RouteRefused(
            "No permitted model binding for role " + repr(role)
            + (" (missing capabilities: " + ",".join(sorted(set(missing_all))) + ")"
               if missing_all else ""),
            missing_capabilities=tuple(sorted(set(missing_all))),
            refused=tuple(refusals),
        )

    # -------------------------------------------------------------- building

    def build_llm(self, binding: ModelBinding):
        """Only LLM construction point; repeats the permission gate before construction."""
        permissions.assert_model_permitted(
            binding.model_name, binding.base_url, self.project_id,
        )
        from crewai import LLM

        kwargs: dict[str, Any] = {"model": binding.model_name}
        if binding.base_url:
            kwargs["base_url"] = binding.base_url
        if "temperature" in binding.params:
            kwargs["temperature"] = binding.params["temperature"]
        return LLM(**kwargs)

    # -------------------------------------------------------------- selection

    def auto_select(self, role: str, candidates: list[Mapping[str, Any]], *,
                    required_capabilities=(), project_id: int | None = None,
                    max_cost_usd: float | None = None,
                    prefer_capabilities=("tool_calling", "structured_output")) -> ModelBinding:
        """Rank explicit candidate models by measured capabilities and real past outcomes.

        This never invents candidates and never silently falls back: the caller passes
        the models it is willing to run (e.g. the live Ollama list), and the returned
        binding records the score, history and capability evidence used to pick it.
        """
        role = str(role)
        stats = historical_performance(project_id)
        ranked: list[tuple[float, ModelBinding, dict]] = []
        refusals: list[str] = []
        for item in candidates:
            candidate = dict(item)
            if "model" in candidate and "model_name" not in candidate:
                candidate["model_name"] = candidate["model"]
            provider = str(candidate.get("provider_id") or "ollama")
            model_name = str(candidate.get("model_name") or "").strip()
            if not model_name:
                continue
            binding = binding_from_mapping(role, {**candidate, "provider_id": provider,
                                                  "model_name": model_name},
                                           source="auto_ranked")
            capability_set = self._capabilities_for(binding)
            ok, missing = capability_set.satisfies(tuple(required_capabilities or ()))
            if not ok:
                refusals.append(model_name + ": missing " + ",".join(missing))
                continue
            try:
                permissions.assert_model_permitted(
                    binding.model_name, binding.base_url, project_id if project_id is not None else self.project_id,
                )
            except PermissionDenied as exc:
                refusals.append(model_name + ": permission denied")
                continue
            history = stats.get(role + "::" + model_name, {})
            attempts = int(history.get("attempts") or 0)
            successes = int(history.get("successes") or 0)
            avg_duration = float(history.get("avg_duration_s") or 0.0)
            success_rate = (successes / attempts) if attempts else 0.5
            cap_score = sum(1 for cap in prefer_capabilities if capability_set.supports(cap))
            score = success_rate * 50 + min(successes * 5, 25) + cap_score * 5
            if avg_duration:
                score -= min(avg_duration, 120.0) * 0.05
            cost = history.get("cost_usd")
            if max_cost_usd is not None:
                # Local inference is billed at 0; unknown cloud cost is not assumed free.
                if binding.is_cloud and cost is None:
                    refusals.append(model_name + ": cost unknown")
                    continue
                effective_cost = float(cost or 0.0)
                if effective_cost > float(max_cost_usd):
                    refusals.append(model_name + ": cost over cap")
                    continue
            capabilities = capability_set.to_dict()["capabilities"]
            selection = {
                "strategy": "measured_capabilities+historical_results",
                "score": round(score, 3),
                "attempts": attempts,
                "successes": successes,
                "success_rate": round(success_rate, 3),
                "avg_duration_s": round(avg_duration, 3),
                "capability_score": cap_score,
                "required_capabilities": list(required_capabilities or ()),
                "max_cost_usd": max_cost_usd,
            }
            ranked.append((
                score,
                replace(binding, source="auto_ranked", selection=selection,
                        capabilities=capabilities,
                        capability_sources={name: str(entry.get("source") or "")
                                            for name, entry in capabilities.items()}),
                history,
            ))
        if not ranked:
            raise RouteRefused(
                "Auto model selection found no permitted candidate for role " + repr(role)
                + (" (" + "; ".join(refusals) + ")" if refusals else ""),
                refused=tuple(refusals),
            )
        ranked.sort(key=lambda row: (-row[0], row[1].model_name))
        return ranked[0][1]

    # -------------------------------------------------------------- snapshots

    @staticmethod
    def ensure_snapshot_schema() -> None:
        conn = database.init_db()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mission_model_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mission_id INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        binding_json TEXT NOT NULL,
                        config_sha256 TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(mission_id, role)
                    )
                    """
                )
        finally:
            conn.close()

    def record_mission_snapshot(self, mission_id: int,
                                bindings: Mapping[str, ModelBinding]) -> int:
        self.ensure_snapshot_schema()
        stamp = _now_iso()
        written = 0
        conn = database.init_db()
        try:
            with conn:
                for role, binding in bindings.items():
                    payload = binding.to_dict()
                    payload["snapshot_of"] = "model_router"
                    conn.execute(
                        """
                        INSERT INTO mission_model_snapshots
                            (mission_id, role, binding_json, config_sha256, created_at)
                        VALUES (?,?,?,?,?)
                        ON CONFLICT(mission_id, role) DO UPDATE SET
                            binding_json=excluded.binding_json,
                            config_sha256=excluded.config_sha256,
                            created_at=excluded.created_at
                        """,
                        (int(mission_id), str(role),
                         json.dumps(payload, sort_keys=True, ensure_ascii=False),
                         str(payload.get("config_sha256") or ""), stamp),
                    )
                    written += 1
        finally:
            conn.close()
        return written

    def load_mission_snapshot(self, mission_id: int) -> dict[str, dict]:
        self.ensure_snapshot_schema()
        conn = database.init_db()
        try:
            rows = conn.execute(
                "SELECT * FROM mission_model_snapshots WHERE mission_id=?",
                (int(mission_id),),
            ).fetchall()
        finally:
            conn.close()
        return {
            str(row["role"]): json.loads(str(row["binding_json"])) for row in rows
        }

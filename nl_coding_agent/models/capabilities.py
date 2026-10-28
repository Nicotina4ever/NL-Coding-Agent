"""C4d: evidence-based model capability records (measured > declared > unknown).

Order in which records are stored does not matter: measured True always wins; a
declared/unknown record never satisfies a requirement. Probes are caller-supplied
callables executed only on explicit human/CLI action; this module performs no
network/model call itself and adds no telemetry.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping

from nl_coding_agent.persistence import database

CAPABILITIES = ("tool_calling", "structured_output", "vision", "audio", "context")
STATES = ("measured", "declared", "unknown", "unavailable")
__all__ = [
    "CAPABILITIES", "STATES", "CapabilityError", "CapabilityRecord",
    "CapabilitySet", "ensure_schema", "record_capabilities", "load_capabilities",
    "capability_set_for", "probe_capabilities", "records_from_declared",
]


class CapabilityError(ValueError):
    """Invalid capability record."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_schema() -> None:
    conn = database.init_db()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_capabilities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    backend_version TEXT,
                    capability TEXT NOT NULL,
                    state TEXT NOT NULL,
                    evidence_kind TEXT,
                    probe_id TEXT,
                    measured_at TEXT,
                    hardware_fingerprint TEXT,
                    context_limit INTEGER,
                    latency_ms REAL,
                    source TEXT NOT NULL DEFAULT 'probe',
                    UNIQUE(provider_id, model_name, capability)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_model_caps_model "
                "ON model_capabilities(provider_id, model_name)"
            )
    finally:
        conn.close()


@dataclass(frozen=True)
class CapabilityRecord:
    provider_id: str
    model_name: str
    capability: str
    state: str
    backend_version: str = ""
    evidence_kind: str = ""
    probe_id: str = ""
    measured_at: str = ""
    hardware_fingerprint: str = ""
    context_limit: int | None = None
    latency_ms: float | None = None
    source: str = "probe"

    def __post_init__(self) -> None:
        if self.capability not in CAPABILITIES:
            raise CapabilityError("Unknown capability: " + repr(self.capability))
        if self.state not in STATES:
            raise CapabilityError("Unknown capability state: " + repr(self.state))
        if not str(self.provider_id or "").strip() or not str(self.model_name or "").strip():
            raise CapabilityError("provider_id and model_name are required")

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id, "model_name": self.model_name,
            "backend_version": self.backend_version, "capability": self.capability,
            "state": self.state, "evidence_kind": self.evidence_kind,
            "probe_id": self.probe_id, "measured_at": self.measured_at,
            "hardware_fingerprint": self.hardware_fingerprint,
            "context_limit": self.context_limit, "latency_ms": self.latency_ms,
            "source": self.source,
        }


@dataclass(frozen=True)
class CapabilitySet:
    provider_id: str
    model_name: str
    records: Mapping[str, CapabilityRecord] = field(default_factory=dict)

    def state(self, capability: str) -> str:
        record = self.records.get(capability)
        return str(record.state) if record is not None else "unknown"

    def supports(self, capability: str) -> bool:
        """Only a measured positive record is a pass; declared/unknown never pass."""
        record = self.records.get(capability)
        return record is not None and record.state == "measured"

    def satisfies(self, required) -> tuple[bool, tuple[str, ...]]:
        missing = tuple(cap for cap in required if not self.supports(cap))
        return not missing, missing

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id, "model_name": self.model_name,
            "capabilities": {
                name: {"state": record.state, "source": record.source,
                       "evidence_kind": record.evidence_kind,
                       "measured_at": record.measured_at}
                for name, record in self.records.items()
            },
        }


def record_capabilities(records: list[CapabilityRecord]) -> int:
    ensure_schema()
    written = 0
    conn = database.init_db()
    try:
        with conn:
            for record in records:
                conn.execute(
                    """
                    INSERT INTO model_capabilities
                        (provider_id, model_name, backend_version, capability, state,
                         evidence_kind, probe_id, measured_at, hardware_fingerprint,
                         context_limit, latency_ms, source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(provider_id, model_name, capability) DO UPDATE SET
                        backend_version=excluded.backend_version,
                        state=excluded.state,
                        evidence_kind=excluded.evidence_kind,
                        probe_id=excluded.probe_id,
                        measured_at=excluded.measured_at,
                        hardware_fingerprint=excluded.hardware_fingerprint,
                        context_limit=excluded.context_limit,
                        latency_ms=excluded.latency_ms,
                        source=excluded.source
                    """,
                    (record.provider_id, record.model_name, record.backend_version,
                     record.capability, record.state, record.evidence_kind,
                     record.probe_id, record.measured_at, record.hardware_fingerprint,
                     record.context_limit, record.latency_ms, record.source),
                )
                written += 1
    finally:
        conn.close()
    return written


def _row_to_record(row) -> CapabilityRecord:
    return CapabilityRecord(
        provider_id=str(row["provider_id"]), model_name=str(row["model_name"]),
        capability=str(row["capability"]), state=str(row["state"]),
        backend_version=str(row["backend_version"] or ""),
        evidence_kind=str(row["evidence_kind"] or ""),
        probe_id=str(row["probe_id"] or ""),
        measured_at=str(row["measured_at"] or ""),
        hardware_fingerprint=str(row["hardware_fingerprint"] or ""),
        context_limit=row["context_limit"], latency_ms=row["latency_ms"],
        source=str(row["source"] or "probe"),
    )


def load_capabilities(provider_id: str, model_name: str,
                      *, records: Mapping[str, CapabilityRecord] | None = None) -> CapabilitySet:
    if isinstance(records, CapabilitySet):
        return records
    if records is not None:
        return CapabilitySet(str(provider_id), str(model_name), dict(records))
    ensure_schema()
    conn = database.init_db()
    try:
        rows = conn.execute(
            "SELECT * FROM model_capabilities WHERE provider_id=? AND model_name=?",
            (str(provider_id), str(model_name)),
        ).fetchall()
    finally:
        conn.close()
    return CapabilitySet(str(provider_id), str(model_name),
                         {str(row["capability"]): _row_to_record(row) for row in rows})


def capability_set_for(provider_id: str, model_name: str) -> CapabilitySet:
    return load_capabilities(provider_id, model_name)


def probe_capabilities(provider_id: str, model_name: str,
                       probes: Mapping[str, Callable[[], object]], *,
                       backend_version: str = "", hardware_fingerprint: str = "",
                       probe_id: str = "") -> list[CapabilityRecord]:
    """Run caller-supplied probes explicitly; failures become unavailable/unknown."""
    records: list[CapabilityRecord] = []
    stamp = _now_iso()
    for capability in CAPABILITIES:
        probe = probes.get(capability)
        if probe is None:
            records.append(CapabilityRecord(
                provider_id, model_name, capability, "unknown",
                backend_version=backend_version, evidence_kind="not_probed",
                probe_id=probe_id, measured_at=stamp,
                hardware_fingerprint=hardware_fingerprint, source="probe",
            ))
            continue
        try:
            result = probe()
        except Exception as exc:  # noqa: BLE001 - probe failure is evidence
            records.append(CapabilityRecord(
                provider_id, model_name, capability, "unavailable",
                backend_version=backend_version, evidence_kind="probe_error",
                probe_id=probe_id, measured_at=stamp,
                hardware_fingerprint=hardware_fingerprint,
                latency_ms=None, source="probe",
            ))
            continue
        supported = bool(result.get("supported")) if isinstance(result, Mapping) else bool(result)
        context_limit = result.get("context_limit") if isinstance(result, Mapping) else None
        latency = result.get("latency_ms") if isinstance(result, Mapping) else None
        records.append(CapabilityRecord(
            provider_id, model_name, capability,
            "measured" if supported else "unavailable",
            backend_version=backend_version, evidence_kind="probe",
            probe_id=probe_id, measured_at=stamp,
            hardware_fingerprint=hardware_fingerprint,
            context_limit=int(context_limit) if context_limit is not None else None,
            latency_ms=float(latency) if latency is not None else None,
            source="probe",
        ))
    return records


def records_from_declared(provider_id: str, model_name: str,
                          declared: list[str], *, source: str = "declared") -> list[CapabilityRecord]:
    stamp = _now_iso()
    return [
        CapabilityRecord(provider_id, model_name, cap, "declared",
                         evidence_kind="model_metadata", measured_at=stamp,
                         source=source)
        for cap in CAPABILITIES if cap in set(declared)
    ]

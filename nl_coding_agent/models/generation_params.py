"""Persistent per-model/per-role generation parameters.

Only explicitly configured values are stored. Unconfigured values are omitted
from LLM requests so the provider/Ollama server keeps its own defaults.
Context length (num_ctx) is deliberately not accepted here: it belongs to the
Ollama application settings, never to NL Coding Agent.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from nl_coding_agent.persistence import database

ALLOWED: dict[str, tuple[str, float | int | None, float | int | None]] = {
    # name: (kind, minimum, maximum)
    "temperature": ("float", 0.0, 2.0),
    "top_p": ("float", 0.0, 1.0),
    "top_k": ("int", 0, 1000),
    "min_p": ("float", 0.0, 1.0),
    "repeat_penalty": ("float", 0.0, 5.0),
    "repeat_last_n": ("int", -1, 4096),
    "seed": ("int", -1, 2**63 - 1),
    "max_tokens": ("int", 1, 1_000_000),
    "num_predict": ("int", -1, 1_000_000),
    "frequency_penalty": ("float", -2.0, 2.0),
    "presence_penalty": ("float", -2.0, 2.0),
    "tfs_z": ("float", 0.0, 10.0),
    "typical_p": ("float", 0.0, 1.0),
    "mirostat": ("int", 0, 2),
    "mirostat_tau": ("float", 0.0, 10.0),
    "mirostat_eta": ("float", 0.0, 1.0),
}
#: Keys that must never be accepted from model/role settings.
FORBIDDEN = {"num_ctx", "context_length", "context_window"}


class GenerationParamsError(ValueError):
    """Invalid generation parameter or scope."""


def _ensure_schema() -> None:
    conn = database.get_connection()
    try:
        with conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS model_generation_params (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       scope TEXT NOT NULL,
                       provider_id TEXT NOT NULL DEFAULT 'ollama',
                       model_name TEXT NOT NULL DEFAULT '',
                       role TEXT NOT NULL DEFAULT '',
                       params_json TEXT NOT NULL DEFAULT '{}',
                       updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                       UNIQUE(scope, provider_id, model_name, role)
                   )"""
            )
    finally:
        conn.close()


def normalize_model(model_name: str) -> str:
    text = str(model_name or "").strip()
    return text.split("/", 1)[1] if text.startswith("ollama/") else text


def validate_params(params: Mapping[str, Any] | None) -> dict:
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise GenerationParamsError("Generation parameters must be an object")
    result: dict[str, Any] = {}
    for raw_key, value in params.items():
        key = str(raw_key).strip()
        if key in FORBIDDEN:
            raise GenerationParamsError(
                f"{key} is owned by Ollama application settings and cannot be set here")
        if key not in ALLOWED:
            raise GenerationParamsError("Unsupported generation parameter: " + key)
        if value is None:
            continue
        kind, minimum, maximum = ALLOWED[key]
        if kind == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise GenerationParamsError(key + " must be a number")
            numeric: float | int = float(value)
        else:
            if isinstance(value, bool):
                raise GenerationParamsError(key + " must be an integer")
            if isinstance(value, float) and not value.is_integer():
                raise GenerationParamsError(key + " must be an integer")
            try:
                numeric = int(value)
            except (TypeError, ValueError) as exc:
                raise GenerationParamsError(key + " must be an integer") from exc
        if minimum is not None and numeric < minimum:
            raise GenerationParamsError(f"{key} must be >= {minimum}")
        if maximum is not None and numeric > maximum:
            raise GenerationParamsError(f"{key} must be <= {maximum}")
        result[key] = numeric
    return result


def _row(scope: str, provider_id: str, model_name: str, role: str) -> dict:
    _ensure_schema()
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM model_generation_params WHERE scope=? AND provider_id=? "
            "AND model_name=? AND role=?",
            (scope, provider_id, model_name, role),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {}
    try:
        data = json.loads(str(row["params_json"] or "{}"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def save_params(params: Mapping[str, Any] | None, *, scope: str = "model",
                provider_id: str = "ollama", model_name: str = "",
                role: str = "") -> dict:
    """Persist a complete parameter set; ``None`` removes a key."""
    scope = str(scope)
    if scope not in ("global", "role", "model"):
        raise GenerationParamsError("scope must be global, role or model")
    provider_id = str(provider_id or "ollama")
    model_name = normalize_model(model_name) if scope == "model" else ""
    role = str(role or "") if scope == "role" else ""
    if scope == "model" and not model_name:
        raise GenerationParamsError("model scope requires model_name")
    if scope == "role" and not role:
        raise GenerationParamsError("role scope requires role")
    current = _row(scope, provider_id, model_name, role)
    incoming = validate_params(params)
    for key, value in (params or {}).items():
        if value is None:
            current.pop(str(key), None)
    current.update(incoming)
    _ensure_schema()
    conn = database.get_connection()
    try:
        with conn:
            if not current:
                conn.execute(
                    "DELETE FROM model_generation_params WHERE scope=? AND provider_id=? "
                    "AND model_name=? AND role=?",
                    (scope, provider_id, model_name, role),
                )
            else:
                conn.execute(
                    """INSERT INTO model_generation_params
                       (scope, provider_id, model_name, role, params_json, updated_at)
                       VALUES (?,?,?,?,?,datetime('now'))
                       ON CONFLICT(scope, provider_id, model_name, role) DO UPDATE SET
                           params_json=excluded.params_json, updated_at=excluded.updated_at""",
                    (scope, provider_id, model_name, role,
                     json.dumps(current, sort_keys=True)),
                )
    finally:
        conn.close()
    return current


def effective_params(*, model_name: str = "", role: str = "",
                     provider_id: str = "ollama") -> dict:
    """Merge global -> role -> model; later scopes override explicitly."""
    merged: dict = {}
    merged.update(_row("global", provider_id, "", ""))
    if role:
        merged.update(_row("role", provider_id, "", str(role)))
    model = normalize_model(model_name)
    if model:
        merged.update(_row("model", provider_id, model, ""))
    return validate_params(merged)


def list_params() -> list[dict]:
    _ensure_schema()
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM model_generation_params ORDER BY scope, provider_id, model_name, role"
        ).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["params"] = json.loads(item.pop("params_json") or "{}")
        except ValueError:
            item["params"] = {}
        result.append(item)
    return result

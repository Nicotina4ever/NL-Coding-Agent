"""Typed read-only research tool descriptors (stage 7 research R4).

Descriptors only: no execution implementation, transport, model or network import.
They map the research tools to the existing capability taxonomy/scope kinds so a
future model/agent tool surface can route them through ResearchService and the
permission/auto-review boundary.

There is deliberately NO write, install, publish, upload or downloader tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from nl_coding_agent.core import permissions

TOOL_WEB_SEARCH = "web_search"
TOOL_WEB_FETCH = "web_fetch"
TOOL_GITHUB_LOOKUP = "github_lookup"
TOOL_HUGGINGFACE_LOOKUP = "huggingface_lookup"
READ_ONLY_TOOL_NAMES = (TOOL_WEB_SEARCH, TOOL_WEB_FETCH,
                        TOOL_GITHUB_LOOKUP, TOOL_HUGGINGFACE_LOOKUP)
FORBIDDEN_TOOL_TOKENS = ("write", "install", "publish", "upload", "download",
                         "push", "delete", "post", "patch", "shell", "exec")


class ResearchToolError(ValueError):
    """Raised for invalid/duplicate/unsafe research tool descriptors."""


@dataclass(frozen=True, slots=True)
class ResearchToolDescriptor:
    name: str
    description: str
    capability: str
    scope_kind: str
    input_schema: Mapping
    output_schema: Mapping
    read_only: bool = True
    network: bool = True
    requires_citation: bool = True
    provenance_required: bool = True
    annotations: Mapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ResearchToolError("tool name must be non-empty")
        object.__setattr__(self, "name", self.name.strip())
        if self.read_only is not True:
            raise ResearchToolError("research tools are read-only: " + self.name)
        try:
            capability = permissions.normalize_capability(self.capability)
        except ValueError as exc:
            raise ResearchToolError("invalid capability for " + self.name + ": "
                                    + str(exc)) from exc
        object.__setattr__(self, "capability", capability)
        try:
            permissions._validate_scope_kind(self.scope_kind)  # noqa: SLF001
        except ValueError as exc:
            raise ResearchToolError("invalid scope for " + self.name + ": "
                                    + str(exc)) from exc
        if not isinstance(self.input_schema, Mapping) or not self.input_schema:
            raise ResearchToolError("input schema is required: " + self.name)
        if not isinstance(self.output_schema, Mapping) or not self.output_schema:
            raise ResearchToolError("output schema is required: " + self.name)
        for token in FORBIDDEN_TOOL_TOKENS:
            if token in self.name.lower():
                raise ResearchToolError("forbidden tool name: " + self.name)
        object.__setattr__(self, "input_schema", dict(self.input_schema))
        object.__setattr__(self, "output_schema", dict(self.output_schema))
        object.__setattr__(self, "annotations", dict(self.annotations or {}))

    def describe(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "capability": self.capability,
            "scope_kind": self.scope_kind,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "read_only": True,
            "network": bool(self.network),
            "requires_citation": bool(self.requires_citation),
            "provenance_required": bool(self.provenance_required),
            "annotations": dict(self.annotations),
        }


_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 2000},
        "search_type": {"type": "string",
                        "enum": ["web", "docs", "code", "academic", "news"]},
        "provider": {"type": "string"},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "required": ["query"],
    "additionalProperties": False,
}
_FETCH_SCHEMA = {
    "type": "object",
    "properties": {"url": {"type": "string", "format": "uri",
                           "pattern": "^https?://"}},
    "required": ["url"],
    "additionalProperties": False,
}
_GITHUB_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": [
            "repository", "readme", "contents", "license", "branches", "tags", "commits",
            "issues", "releases", "workflows", "file_contents",
            "search_repositories"]},
        "full_name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"},
        "query": {"type": "string"},
        "path": {"type": "string"},
        "ref": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    "required": ["action"],
    "additionalProperties": False,
}
_HF_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": [
            "search_models", "search_datasets", "search_spaces", "model_info",
            "dataset_info", "space_info", "model_card", "files", "license_info"]},
        "query": {"type": "string"},
        "repo_id": {"type": "string"},
        "revision": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    "required": ["action"],
    "additionalProperties": False,
}
_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string",
                    "enum": ["allowed", "needs_approval", "denied",
                             "unavailable", "error"]},
        "capability": {"type": "string"},
        "reason": {"type": "string"},
        "payload": {"type": "object"},
        "untrusted": {"type": "boolean"},
        "citations": {"type": "array", "items": {"type": "object"}},
        "provenance": {"type": "object"},
    },
    "required": ["outcome", "capability"],
    "additionalProperties": True,
}

RESEARCH_TOOL_DESCRIPTORS: tuple[ResearchToolDescriptor, ...] = (
    ResearchToolDescriptor(
        name=TOOL_WEB_SEARCH,
        description="Route a read-only web search through declared providers; no writes.",
        capability=permissions.CAPABILITY_WEB_SEARCH,
        scope_kind=permissions.SCOPE_PROJECT,
        input_schema=_SEARCH_SCHEMA, output_schema=_RESULT_SCHEMA,
        annotations={"read_only": True, "untrusted_results": True}),
    ResearchToolDescriptor(
        name=TOOL_WEB_FETCH,
        description="Fetch one public URL under policy and store provenance/citation.",
        capability=permissions.CAPABILITY_WEB_FETCH,
        scope_kind=permissions.SCOPE_EXTERNAL_RESOURCE,
        input_schema=_FETCH_SCHEMA, output_schema=_RESULT_SCHEMA,
        annotations={"read_only": True, "untrusted_content": True,
                     "requires_network_grant": True}),
    ResearchToolDescriptor(
        name=TOOL_GITHUB_LOOKUP,
        description="Read-only GitHub REST lookup (repository/readme/issues/...).",
        capability=permissions.CAPABILITY_WEB_FETCH,
        scope_kind=permissions.SCOPE_EXTERNAL_RESOURCE,
        input_schema=_GITHUB_SCHEMA, output_schema=_RESULT_SCHEMA,
        annotations={"read_only": True, "provider": "github",
                     "untrusted_content": True}),
    ResearchToolDescriptor(
        name=TOOL_HUGGINGFACE_LOOKUP,
        description="Read-only Hugging Face Hub lookup (search/model/files/...).",
        capability=permissions.CAPABILITY_WEB_FETCH,
        scope_kind=permissions.SCOPE_EXTERNAL_RESOURCE,
        input_schema=_HF_SCHEMA, output_schema=_RESULT_SCHEMA,
        annotations={"read_only": True, "provider": "huggingface",
                     "no_checkpoint_retrieval": True, "untrusted_content": True}),
)


class ResearchToolRegistry:
    """Small typed registry for research tool descriptors (no execution)."""

    def __init__(self) -> None:
        self._tools: dict[str, ResearchToolDescriptor] = {}

    def register(self, descriptor: ResearchToolDescriptor) -> ResearchToolDescriptor:
        if not isinstance(descriptor, ResearchToolDescriptor):
            raise ResearchToolError("research registry accepts typed descriptors only")
        if descriptor.name in self._tools:
            raise ResearchToolError("duplicate research tool: " + descriptor.name)
        self._tools[descriptor.name] = descriptor
        return descriptor

    def get(self, name: str) -> ResearchToolDescriptor | None:
        return self._tools.get(str(name))

    def all(self) -> tuple[ResearchToolDescriptor, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))

    def describe_all(self) -> list[dict]:
        return [descriptor.describe() for descriptor in self.all()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return str(name) in self._tools


def research_tool(name: str) -> ResearchToolDescriptor | None:
    for descriptor in RESEARCH_TOOL_DESCRIPTORS:
        if descriptor.name == name:
            return descriptor
    return None


def register_research_tools(registry=None) -> ResearchToolRegistry:
    """Populate a registry (or return a new typed one) with read-only descriptors.

    Compatible with a ResearchToolRegistry, a dict-like mapping, a list, or any
    object exposing .register(descriptor).
    """
    created = registry is None
    target = registry if not created else ResearchToolRegistry()
    for descriptor in RESEARCH_TOOL_DESCRIPTORS:
        if isinstance(target, dict):
            if descriptor.name in target:
                raise ResearchToolError("duplicate research tool: " + descriptor.name)
            target[descriptor.name] = descriptor
        elif hasattr(target, "register") and callable(target.register):
            target.register(descriptor)
        elif hasattr(target, "append") and callable(target.append):
            target.append(descriptor)
        else:
            raise ResearchToolError("unsupported tool registry type")
    return target if created else target


def describe_research_tools() -> list[dict]:
    return [descriptor.describe() for descriptor in RESEARCH_TOOL_DESCRIPTORS]

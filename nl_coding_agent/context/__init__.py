"""Context Engine for NL Code (P1).

Modules:
* ``budget`` — measured, degradable prompt budget and extractive compaction;
* ``profile`` — persisted project profile and selective file retrieval;
* ``memory`` — durable cross-mission project memory;
* ``engine`` — the facade consumed by Chat and the mission orchestrator.
"""
from nl_coding_agent.context.engine import ContextEngine, MissionContext, ProjectProfile
from nl_coding_agent.context.budget import ChatBudget, compact_chat, estimate_tokens

__all__ = [
    "ChatBudget", "ContextEngine", "MissionContext", "ProjectProfile",
    "compact_chat", "estimate_tokens",
]

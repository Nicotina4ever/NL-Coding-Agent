"""C4b CrewAI Flow integration package (app-owned state/persistence/events).

The modules here are intentionally unreachable from the supervisor and the
default sequential orchestrator until C4c wires the Flow executor behind an
explicit pipeline flag. Importing this package has no side effects.
"""
__all__: list[str] = []

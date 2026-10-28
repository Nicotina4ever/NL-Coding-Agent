# Tool, Safety and Self-Modification Policy

## Tool permissions

Classify operations:
- READ: file/list/search/status.
- WRITE_REVERSIBLE: patch/create tracked source files.
- EXECUTE_SAFE: tests/build/lint/status.
- EXECUTE_RISKY: installers, network changes, migration scripts, destructive commands.
- DESTRUCTIVE: delete/reset/clean operations.

Normal autonomous mode may perform READ, WRITE_REVERSIBLE and known-safe verification inside the
active project.

Risky/destructive operations require policy approval.

## Workspace boundaries

The active project root is the default boundary.

Symlinks/junctions and resolved paths must not silently escape the project boundary.

Protected/vendor paths in the Coding Agent workspace:
- python/
- crewAI/
- crewAI-tools/
- user backup archives
- model/cache locations outside the project

## Git

Git is the preferred lightweight rollback mechanism.

Before a coding mission:
- inspect clean/dirty state;
- never silently discard user changes;
- record pre-existing changes;
- keep agent changes distinguishable.

Do not run destructive `git reset --hard` or `git clean -fdx` autonomously.

## Self-modification

Self-build changes must be treated as candidate updates.

A running GUI should not attempt to hot-reload arbitrary rewritten core modules.
Preferred flow:
- produce candidate source;
- execute tests in child process;
- review diff;
- mark update ready;
- restart application to load the new version.

## Cloud escalation

Cloud fallback is off by default.
The UI must show when a model is cloud-backed.
Project policy controls whether source content can leave the machine.

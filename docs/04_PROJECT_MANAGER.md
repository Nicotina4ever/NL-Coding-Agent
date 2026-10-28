# Automatic Project Manager

## Goal

A project is opened by choosing a folder. The application creates its own internal profile.
The user does not create a YAML file.

## ProjectProfile

At minimum:
- stable project id;
- display name;
- root path;
- detected Git root;
- languages;
- frameworks/build systems;
- documentation files;
- instruction files;
- candidate build/test commands;
- ignored/generated/vendor paths;
- risk flags;
- last scan hash/time;
- project-specific policy overrides.

## Discovery stages

1. Fast filesystem signature scan.
2. Read high-value metadata files.
3. Read existing README/AGENTS/GEMINI/docs indexes.
4. Infer candidate verification commands.
5. Ask an Architect model only for semantic interpretation that static discovery cannot provide.
6. Persist results.

Do not send the entire repository to an LLM by default.

## Documentation priority

High priority:
- AGENTS.md / GEMINI.md
- README*
- ARCHITECTURE*
- REQUIREMENTS*
- DESIGN*
- TODO*
- ROADMAP*
- docs indexes
- build manifests

Then perform targeted code retrieval according to the mission.

## Project-local metadata

Do not require modifying third-party repositories.

By default, keep NL Coding Agent metadata in its own SQLite database.
An optional `.nlca/` directory may later be offered for teams that want portable project metadata,
but it must be opt-in.

## Re-scan

Use fingerprints/mtime/manifest hashes so reopening a large repository does not require repeating
all semantic analysis.

Allow:
- Quick refresh.
- Full rescan.

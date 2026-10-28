# SPEC-18 — Persistenza SQLite e schema concettuale

Il database esistente è la fonte primaria dello stato, non file Markdown rigenerati. Evitare doppia architettura e controllare schema reale prima di migrare. Usare migrazioni con versioni, transazioni, FK, indici e checkpoint/backup ragionevoli senza duplicazioni massive.

Entità suggerite (non imporre nomi nuovi se equivalenti esistono):

- `projects`: id, canonical_path, stack_metadata, git metadata, last_scan.
- `goals`: project_id, goal_user_defined/proposed, target, policy, criteria, status.
- `milestones`: goal_id, dependencies, outcome, gate state.
- `tasks`: milestone/goal, dependency graph, owner, write scope, acceptance, status.
- `missions`: task_id, provider/model/prompt config snapshot, start/end, state, idempotency key, resume token.
- `mission_events`: event append-only + timestamp, stage, payload reference.
- `tool_calls`: command/patch metadata, scope, exit status, log refs.
- `artifacts`: diff, test file, screenshot, transcript, logs, attachements hashes, refs, ownership.
- `verification_runs`: command, exit code, tests count, env/version, evidence URI.
- `reviews`: decision, evidence refs, comment, reviewer model/version.
- `models`, `providers`, `agent_profiles`, `agent_assignments`, `measurements`.
- `settings_overrides`, `media_attachments`, `downloads`, `owned_assets`.

Separare percorsi degli allegati da contenuto binario massivo nel DB; SQLite per metadata, journal e link hash, con deduplica e ownership. Transaction boundaries e recovery atomici: `MISSION COMPLETED` solo dopo commit evidenza e gate. Non cancellare history per ridurre spazio salvo policy utente. Export/import della roadmap e config con versioni, separato da dati/segreti.

Dopo ogni modifica di schema fare test migrazione dal DB esistente e rollback/failure. Documentare compatibility release e niente delete di tabelle senza conferma.

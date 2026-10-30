# Database

## Engine

PostgreSQL (`pgvector/pgvector:pg16` image) for deployed environments; SQLite for local runs and tests. Models in
`backend/app/models.py`. Schema changes go through Alembic (`backend/migrations/`, revisions `0001` initial schema,
`0002` knowledge documents and embeddings, `0003` notification email outbox, `0004` vision analyses, `0005` workflow
runs and agent conflicts, `0006` append-only audit trail). The Docker image runs `alembic upgrade head` before starting and sets
`SITEGUARD_AUTO_CREATE_SCHEMA=false`; local runs and tests still use `create_all`. `tests/test_migrations.py` fails
if a model change has no migration.

```bash
cd backend && alembic revision --autogenerate -m "describe change"   # then review the file
alembic upgrade head
```

## Tables (implemented)

organizations, users, memberships, projects, sites, incidents, incident_events, evidence, documents,
document_chunks, chunk_embeddings, agent_runs, risk_assessments, capa_actions (with `escalation_level`),
approval_events, verification_records, audit_events, notifications, notification_deliveries (email outbox: channel,
status, attempts, last_error, next_attempt_at, sent_at; one row per notification and channel), vision_analyses (one
analyzer run over one image: evidence SHA-256, task, analyzer, model, model and taxonomy versions, status,
preprocessing, image-quality flags, thresholds used, limitations), vision_observations (label, category, confidence,
threshold, `above_threshold`, normalized box/polygon, analyzer note, review status with reviewer, time and note) and
vision_calibrations (detection threshold per label for a project or one of its sites, with reason and author).

RCA and compliance outputs are stored as structured JSON in `agent_runs.output` for the pilot rather than in
separate rca_cases / compliance_findings tables.

## Knowledge documents (revision 0002)

`documents` carries the processing state and provenance of every source: `status` (`PENDING` → `PROCESSING` →
`READY` or `FAILED`, with `error`), `file_name`, `content_type`, `size_bytes`, `storage_key` (the original file,
stored like evidence), `page_count`, `parser`, `version`, `effective_date`, `tags` (JSON list), `sha256` of the
original bytes, `uploaded_by` and `processed_at`. The same `sha256` and `version` in the same organization and
project is a duplicate and is not ingested twice. Only `READY` documents are searchable.

`document_chunks` keep `ordinal`, `section` (the nearest heading), `page` (PDF page, null for other formats), `text`,
`suspicious` (instruction-like content) and `content_sha256`.

`chunk_embeddings` hold one vector per (chunk, model, model_version): `dim`, `content_sha256` of the text that was
embedded and `vector`. The column is pgvector `vector` on PostgreSQL (the migration enables the extension) and JSON on
SQLite. A chunk is re-embedded when its text checksum changes; switching to a new model or version adds new rows
and leaves the old ones until they are deleted. The API embeds missing chunks at startup and on
`POST /documents/reindex`. No ANN index yet: exact distance is fine at pilot scale; add HNSW when a semantic model
is chosen (DECISIONS 017).

## Append-only audit trail (revision 0006)

Triggers refuse `UPDATE` and `DELETE` on `audit_events`, and `TRUNCATE` on PostgreSQL, with the message
`audit_events is append-only`. The application only ever inserts audit events; the triggers make the same true for
every other database client (a console session, a script, a compromised service account without the owner role).
Dropping the table or the trigger still needs the table owner, so the database owner role must stay separate from
the role the API runs as in deployed environments. Local runs and tests that build the schema with `create_all` do
not have the triggers; `tests/test_migrations.py` (SQLite) and `tests/test_postgres.py` check them on migrated
databases. Downgrading to `0005` removes them.

## Workflows and conflicts (revision 0005)

`workflow_runs` hold one triage or investigation run of the agent workflow: `organization_id`, `incident_id`,
`kind` (`TRIAGE` or `INVESTIGATION`), `status` (`RUNNING`, `PAUSED`, `FAILED`, `COMPLETED`, `CANCELLED`) with
`status_reason`, `provider`, `current_stage`, `stages` (per stage: status `PENDING` / `RUNNING` / `SUCCEEDED` /
`FAILED` / `SKIPPED` / `ERROR`, attempts, agent run id, error, timestamps), `state` (the validated output of every
finished stage, which a resume continues from), `pause_after`, `pause_requested`, `uncertainty` (confidence, review
reasons and open questions across agents), `lease_expires_at` (a RUNNING workflow whose lease passed is treated as
crashed and can be resumed), `started_by`, `created_at`, `updated_at`, `finished_at`.

`agent_conflicts` hold one recorded disagreement: `organization_id`, `incident_id`, `workflow_id`, `kind`,
`summary`, `details` (both sides), `refs`, `status` (`OPEN`, `RESOLVED`, `SUPERSEDED`), `resolution`,
`resolved_by`, `resolved_at`, `created_at`. Rows are never deleted; a later investigation marks still-open rows
`SUPERSEDED` with a note.

## Knowledge graph (derived, no tables)

The optional knowledge graph (docs/ARCHITECTURE.md#knowledge-graph) adds no tables and no migration. `graph-sync`
reads organizations, projects, sites, memberships, users, incidents, evidence, documents, document_chunks (to resolve
cited `chunk:` refs), agent_runs, capa_actions, approval_events and verification_records, and never writes to them.
The graph can be dropped and rebuilt from PostgreSQL at any time; each node and relationship names its source row in
`source_table` / `source_id`.

## Scoping

Every incident, document and audit event has `organization_id`. `memberships` give a role per organization, either
for all projects (`project_id` null) or one project. All routes resolve user -> membership -> organization ->
project -> resource on the server; a resource outside the caller's scope returns 404.

## Rules

UUID string keys, timezone-aware timestamps, foreign keys and indexes on scoping columns.

## Sensitive data

Evidence bytes live outside the database under random keys (`SITEGUARD_EVIDENCE_DIR`, Blob Storage in Azure);
the database keeps filename, type, size, SHA-256 and uploader. Request bodies are never logged.

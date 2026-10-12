# Database

## Engine

PostgreSQL (`pgvector/pgvector:pg16` image) for deployed environments; SQLite for local runs and tests. Models in
`backend/app/models.py`. Schema changes go through Alembic (`backend/migrations/`, revisions `0001` initial
schema, `0002` knowledge documents and embeddings, `0003` notification email outbox). The Docker image runs `alembic upgrade head` before starting
and sets `SITEGUARD_AUTO_CREATE_SCHEMA=false`; local runs and tests still use `create_all`. `tests/test_migrations.py` fails if a model change has no migration.

```bash
cd backend && alembic revision --autogenerate -m "describe change"   # then review the file
alembic upgrade head
```

## Tables (implemented)

organizations, users, memberships, projects, sites, incidents, incident_events, evidence, documents,
document_chunks, chunk_embeddings, agent_runs, risk_assessments, capa_actions (with `escalation_level`), approval_events,
verification_records, audit_events, notifications, notification_deliveries (email outbox: channel, status,
attempts, last_error, next_attempt_at, sent_at; one row per notification and channel).

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

## Scoping

Every incident, document and audit event has `organization_id`. `memberships` give a role per organization, either
for all projects (`project_id` null) or one project. All routes resolve user -> membership -> organization ->
project -> resource on the server; a resource outside the caller's scope returns 404.

## Rules

UUID string keys, timezone-aware timestamps, foreign keys and indexes on scoping columns.

## Sensitive data

Evidence bytes live outside the database under random keys (`SITEGUARD_EVIDENCE_DIR`, Blob Storage in Azure);
the database keeps filename, type, size, SHA-256 and uploader. Request bodies are never logged.

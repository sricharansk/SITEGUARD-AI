# Database

## Engine

PostgreSQL (`pgvector/pgvector:pg16` image) for deployed environments; SQLite for local runs and tests. Models in
`backend/app/models.py`.

## Migrations

Alembic owns the schema (`backend/app/migrations/`, config `backend/alembic.ini`). The API runs `upgrade head` on
startup (`app.core.db.run_migrations`); `make migrate` does the same from the command line. A database created by
the 0.1.0 pilot with `create_all` (tables present, no `alembic_version`) is stamped at the baseline revision `0001`
and then upgraded, so pilot data is kept. After changing `models.py`, run `make revision m="what changed"`, review
the generated file and commit it; `tests/test_migrations.py` fails if models and migrations drift apart, and checks
downgrade to base and back.

## Tables (implemented)

organizations, users, memberships, projects, sites, incidents, incident_events, evidence, documents,
document_chunks, agent_runs, risk_assessments, capa_actions, approval_events, verification_records, audit_events.

RCA and compliance outputs are stored as structured JSON in `agent_runs.output` for the pilot rather than in
separate rca_cases / compliance_findings tables. Embeddings are not stored yet (retrieval is BM25).

## Scoping

Every incident, document and audit event has `organization_id`. `memberships` give a role per organization, either
for all projects (`project_id` null) or one project. All routes resolve user -> membership -> organization ->
project -> resource on the server; a resource outside the caller's scope returns 404.

## Rules

UUID string keys, timezone-aware timestamps, foreign keys and indexes on scoping columns.

## Sensitive data

Evidence bytes live outside the database under random keys (`SITEGUARD_EVIDENCE_DIR`, Blob Storage in Azure);
the database keeps filename, type, size, SHA-256 and uploader. Request bodies are never logged.

# Database

## Engine

PostgreSQL (`pgvector/pgvector:pg16` image) for deployed environments; SQLite for local runs and tests. Models in
`backend/app/models.py`. Schema changes go through Alembic (`backend/migrations/`, initial revision `0001`). The
Docker image runs `alembic upgrade head` before starting and sets `SITEGUARD_AUTO_CREATE_SCHEMA=false`; local
runs and tests still use `create_all`. `tests/test_migrations.py` fails if a model change has no migration.

```bash
cd backend && alembic revision --autogenerate -m "describe change"   # then review the file
alembic upgrade head
```

## Tables (implemented)

organizations, users, memberships, projects, sites, incidents, incident_events, evidence, documents,
document_chunks, agent_runs, risk_assessments, capa_actions (with `escalation_level`), approval_events,
verification_records, audit_events, notifications.

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

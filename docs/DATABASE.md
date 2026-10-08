# Database

## Engine

PostgreSQL (`pgvector/pgvector:pg16` image) for deployed environments; SQLite for local runs and tests. Models in
`backend/app/models.py`. Tables are created at startup with `create_all` in the pilot; Alembic migrations are the
next step before any shared environment holds data that must survive schema changes (see DECISIONS 006).

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

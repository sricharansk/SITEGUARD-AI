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

## Tables

Blueprint Part 7 lists the target entities. Status today:

| Entity | Status |
|---|---|
| organizations, users, memberships, projects, sites | Implemented |
| project_members | Covered by `memberships.project_id` (a membership scoped to one project) |
| incidents, incident_events, evidence | Implemented |
| documents, document_chunks | Implemented; `documents.version` holds the version (no separate document_versions table) |
| embeddings | Not yet (retrieval is BM25; Prompt 11) |
| agent_runs | Implemented; each run stores its typed output, trace and review reasons |
| agent_outputs, rca_cases, rca_hypotheses, requirements, compliance_findings | Stored as validated JSON in `agent_runs.output` (schemas in `app/agents/schemas.py`) rather than separate tables |
| risk_assessments, capa_actions, approval_events, verification_records, audit_events | Implemented |
| notifications | Not yet (Prompt 24) |

## Incident data

Every incident has the Blueprint's minimum fields: id, organization_id, project_id, site_id, title, description,
category, domain (safety / quality / both), severity, status, occurred_at, reported_at, location, reporter_id,
immediate_actions, created_at, updated_at, plus a human-readable `reference` (SG-YYYY-####), activity,
people_involved, closed_at and `is_synthetic`.

## Migration rule

Every schema change: (1) update this file; (2) create an Alembic revision; (3) test upgrade and downgrade
(`tests/test_migrations.py`); (4) test the affected flows.

## Scoping

Every incident, document and audit event has `organization_id`. `memberships` give a role per organization, either
for all projects (`project_id` null) or one project. All routes resolve user -> membership -> organization ->
project -> resource on the server; a resource outside the caller's scope returns 404.

## Rules

UUID string keys, timezone-aware timestamps, foreign keys and indexes on scoping columns.

## Sensitive data

Evidence bytes live outside the database under random keys (`SITEGUARD_EVIDENCE_DIR`, Blob Storage in Azure);
the database keeps filename, type, size, SHA-256 and uploader. Request bodies are never logged.

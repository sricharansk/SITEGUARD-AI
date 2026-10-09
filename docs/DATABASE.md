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
| embeddings | Implemented as `chunk_embeddings` (revision `0002`) |
| agent_runs | Implemented; each run stores its typed output, trace and review reasons |
| agent_outputs, rca_cases, rca_hypotheses, requirements, compliance_findings | Stored as validated JSON in `agent_runs.output` (schemas in `app/agents/schemas.py`) rather than separate tables |
| risk_assessments, capa_actions, approval_events, verification_records, audit_events | Implemented |
| notifications, notification_deliveries | Implemented (revision `0003`): one in-app row per recipient with a unique `dedupe_key`; one email outbox row per notification with status, attempts, last error and next attempt |
| vision_analyses, vision_observations, vision_calibrations | Implemented (revision `0004`); see "Vision (revision 0004)" |

## Incident data

Every incident has the Blueprint's minimum fields: id, organization_id, project_id, site_id, title, description,
category, domain (safety / quality / both), severity, status, occurred_at, reported_at, location, reporter_id,
immediate_actions, created_at, updated_at, plus a human-readable `reference` (SG-YYYY-####), activity,
people_involved, closed_at and `is_synthetic`.

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
is chosen (DECISIONS O5).

## Vision (revision 0004)

`vision_analyses` record one analyzer run over one image: `organization_id`, `project_id`, `incident_id`,
`evidence_id` and the `evidence_sha256` that was checked before analysis; `task` (`PPE_HAZARD` or `DEFECT`);
`analyzer`, `model`, `model_version` and `taxonomy_version`; `status` (`COMPLETED` or `FAILED`, with `error`);
`preprocessing` (format, original size, orientation corrected, metadata removed, analysis size), `image_quality`
(measurements and flags), `thresholds` (the threshold and its source for every label), `limitations`, `duration_ms`
and `requested_by`. A failed analysis keeps its row and has no observations.

`vision_observations` hold every detection the analyzer reported for a taxonomy label, also those below threshold:
`category`, `label`, `confidence`, the `threshold` applied and `above_threshold`, a normalized `box` (`x`, `y`,
`w`, `h` as fractions of the oriented image) and `polygon` where the analyzer segments, the analyzer's own `note`
(untrusted text), and the human review: `review_status` (`UNREVIEWED`, `CONFIRMED`, `REJECTED`), `reviewed_by`,
`reviewed_at`, `review_note`. Earlier review decisions stay in `audit_events`.

`vision_calibrations` hold a project threshold (`site_id` null) or a site threshold for one label, with `reason`
and `updated_by`. One row per project, site and label is kept by the service.

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

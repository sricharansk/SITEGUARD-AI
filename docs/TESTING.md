# Testing

Run: `make test` (or `cd backend && pytest -q`, 88 tests). Lint and types: `make lint`. CI runs backend lint, types and
tests; frontend typecheck, build and dependency audit; then builds the Docker image, runs the browser tests against
it and resolves every open incident with `scripts/resolve_all.py` (`.github/workflows/ci.yml`).

## Implemented

| File | Covers |
|---|---|
| tests/test_risk.py | Every matrix cell, band boundaries, invalid inputs, determinism |
| tests/test_lifecycle.py | Allowed path, rejected shortcuts, CLOSED only from PENDING_VERIFICATION |
| tests/test_rag.py | Chunking, injection detection, ranking, tenant and project scoping |
| tests/test_agents.py | Triage fixtures (obvious, mixed, insufficient evidence, near miss), tool allowlist, budget, provider failure and invalid output fallback, invented citations removed, poisoned document not cited, Claude provider request shape and refusal fallback (mocked) |
| tests/test_api.py | Error envelope, login, validation, tenant isolation, RBAC, evidence validation, invalid transitions, full E2E incident -> investigation -> review -> work -> failed and passed verification -> closure -> audit, critical closure permission, agent failure with manual continuation, dashboard and search |

| tests/test_notifications.py | Review/assignment/failed-verification notifications, two-level overdue escalation and its idempotency, endpoint permissions |
| tests/test_evaluation.py | Runs the gold-set evaluation and red-team suite: no CRITICAL case under-rated, workflow invariants, 100% red-team containment, accuracy regression floors, every taxonomy class labelled |
| tests/test_migrations.py | Alembic migrations build exactly the schema in `models.py`, and downgrade |
| tests/test_datasets.py | OSHA SIR pipeline on a synthetic fixture: column validation, construction filter, dedupe, date filter, OIICS mapping, no employer data in outputs; dataset registry completeness |
| frontend/e2e/workflow.spec.ts | Browser: report -> AI investigation -> PM blocked from critical approval -> HSE approval -> work -> independent verification -> decisions on any AI conflicts -> closure -> report downloads as PDF and Word; knowledge upload with passages and sections, cited grounded answer, insufficient-evidence answer; investigation paused after triage and resumed, photo checked with the baseline analyzer (states its limits), knowledge graph shown as disabled; email outbox viewed by the auditor (no addresses, no admin buttons), delivery run and retry by the administrator, hidden from site engineers; dashboard, lists, action queue, knowledge, audit; cross-tenant URL returns NOT_FOUND |

| tests/test_hardening.py | Login throttle (429 with Retry-After, per account and client, unknown emails counted, success clears), security headers, oversized and chunked bodies refused before authentication |
| tests/test_config_validation.py | Startup refuses unsafe staging/production settings (secret strength and placeholders, demo seeding, non-PostgreSQL, CORS, http URLs, SMTP without STARTTLS, smtp in local/test); developer environments keep their defaults |
| tests/test_ops_scripts.py | `scripts/backup.py` file handling (archive round trip, path traversal and symlinks refused, URL to libpq env without the password in argv); `scripts/smoke_test.py` against the API; `scripts/dependency_audit.py` exception handling |
| tests/test_knowledge.py | PDF/DOCX/Markdown parsing with page and section provenance, FAILED documents for unparseable and hostile files without orphan files, upload size and type checks, isolated parser limits, chunk strategies, embeddings (every chunk, idempotent, re-embed on change, retries, dimension checks), labelled queries (hybrid hit@3 ≥ 0.85 and not below lexical), citation metadata on hits, project and tenant isolation for search and answers, org-wide document permission, grounded answers (cited, insufficient, conflicting, unsupported claims removed, provider fallback, poisoned sources excluded), injection-like headings flagged, untrusted blocks cannot be closed |
| tests/test_reports.py | Investigation report as Word and PDF carries the same content as Markdown (AI label, disclaimer, closure blockers, tables), checksum header and audit per format, format validation, tenant 404 and 401, renderer structure and Unicode handling |
| tests/test_delivery.py | Email outbox: a delivery queued with each notification, sent with an incident link, not sent twice; backoff, dead letter, admin retry (409 unless FAILED/SKIPPED), workflow unaffected; disabled adapter skips; outbox and retry permissions and tenant 404; SMTP adapter uses STARTTLS and login; delivery job |
| tests/test_vision.py | Image preprocessing (orientation, metadata removal, downscaling, quality flags), hostile and mismatched images refused, taxonomy, baseline analysis says what it cannot do, thresholds and site calibration, analyzer failure stored as FAILED, tampered evidence refused and audited, validation, authorization and tenant 404, review records who and why, agents cite only confirmed observations and question unreviewed ones, report section, closed incidents frozen, rate limit, Claude vision adapter request shape |
| tests/test_graph.py | Knowledge graph: every entity and relationship type built from one incident driven through evidence, investigation, review, rejection, verification with evidence, a project document and a project-scoped membership; the Prompt 28 gate (every node and relationship resolves to its PostgreSQL row, field and agent run); idempotent sync (second run creates and deletes nothing, identical snapshot); deleted evidence, agent runs and people leave the graph with their relationships; tenant isolation (separate person nodes per organization, purge of one tenant leaves the other intact, node takeover refused); project and tenant filtering of the neighbourhood even against a bad store answer; both endpoints (success, audit, `include_ai`, validation, 401/403/404, 409 when disabled); the job and its purge of deleted organizations; unsafe Neo4j settings refused; the Neo4j adapter with a fake driver (only fixed allowlisted Cypher, every value a parameter, MERGE on id, constraints, driver errors as 503). `test_neo4j_integration` runs the adapter against a real Neo4j when `SITEGUARD_TEST_NEO4J_URI` (plus `_USER`, `_PASSWORD`) is set (CI `neo4j` job): exact property round-trip, idempotency, deletion, tenant isolation and the same neighbourhood as the in-memory store |
| tests/test_workflows.py | Checkpoint after every stage; pause after a stage and resume with the stored state; pause requested mid-run; cancel keeps stored stages; one active workflow per incident; bounded retries then FAILED stage; crash after CAPA resumes without duplicating actions; failure inside a stage rolls back and is resumable; expired lease; severity, domain, risk, safety/quality, source-document and vision conflicts stored with both sides, superseded by a later run and blocking closure until resolved; endpoint validation, authorization and tenant isolation; closure blocked until each conflict has a decision, the workspace and report show conflicts and decisions, and a second resume or cancel that loaded stale state is refused |
| tests/test_postgres.py | Migrations on PostgreSQL + pgvector match the models; hybrid search with the `vector` column (CI `postgres` job; needs `SITEGUARD_TEST_POSTGRES_URL`) |
| tests/test_backup_restore.py | PostgreSQL backup and restore drill (CI `postgres` job; needs `SITEGUARD_TEST_POSTGRES_URL` and the PostgreSQL client tools) |

## CI jobs

`backend` (lint incl. scripts, types, tests) · `postgres` (migrations + `alembic check` on PostgreSQL, pgvector search, restore drill) · `neo4j` (knowledge graph adapter against Neo4j 5.26) ·
`dependency-audit` (lock file and npm; also weekly) · `infrastructure` (Bicep build/lint, actionlint with shellcheck,
staging compose config) · `frontend` (typecheck, build) · `docker` (image, smoke test, browser tests, full
resolution run).

## Evaluation

`make eval` (or `cd backend && python -m app.evaluation --out ../docs/EVALUATION.md`) scores the agents on
`data/eval/incidents_gold.yaml` (24 dev + 24 held-out test cases, synthetic, covering all 20 classes) and runs the
10-case red-team suite. Results: [EVALUATION.md](EVALUATION.md). The rules were tuned once on dev errors only; the
test split is the headline number.

## Browser tests

```bash
make web && make run            # or: make up (Docker)
cd frontend && npx playwright install chromium
E2E_BASE_URL=http://localhost:8000 npx playwright test   # SCREENSHOT_DIR=../docs/screenshots to refresh images
```

## Not yet implemented

Load tests; scoring the Claude provider on the gold set in CI (needs an API key); red-team prompts against a live
model; real-data evaluation (blocked in the build sandbox, see DATASETS.md).

## Definition of Done

Tests, lint, type check and build pass for the affected scope.

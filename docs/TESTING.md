# Testing

Run: `make test` (or `cd backend && pytest -q`). Lint and types: `make lint`. CI runs both, the PostgreSQL +
pgvector integration tests, a Docker build and an end-to-end smoke run of `scripts/demo_walkthrough.py`
(`.github/workflows/ci.yml`). Tests use SQLite and the
rules provider; they never call a live model or external service.

## Implemented

| File | Covers |
|---|---|
| tests/test_risk.py | Every matrix cell, band boundaries, invalid inputs, determinism |
| tests/test_lifecycle.py | Allowed path, rejected shortcuts, CLOSED only from PENDING_VERIFICATION |
| tests/test_rag.py | Chunking, injection detection, ranking, tenant and project scoping |
| tests/test_knowledge.py | PDF and DOCX upload with page/section provenance, FAILED documents, parser selection, chunk strategies (tables never split), hit citation metadata, project isolation, every chunk embedded, duplicate uploads, idempotent and changed-content re-embedding, embedding retries and dimension checks, labelled-query hit rate (hybrid ≥ 0.85 and ≥ lexical), grounded answers, insufficient and conflicting evidence, unsupported and invented claims removed, provider fallback with poisoned source excluded, endpoint validation and authorization |
| tests/test_postgres.py | PostgreSQL + pgvector: migrations match models, extension enabled, vector distance search. Runs when `SITEGUARD_TEST_POSTGRES_URL` is set (CI `postgres` job), skipped otherwise |
| tests/test_agents.py | Triage fixtures (obvious, mixed, insufficient evidence, near miss), tool allowlist, budget, provider failure and invalid output fallback, invented citations removed, poisoned document not cited, Claude provider request shape and refusal fallback (mocked) |
| tests/test_migrations.py | Migrations produce exactly the model schema, pilot databases are stamped without data loss, downgrade to base and back |
| tests/test_dataset_registry.py | Every registered dataset has licence and commercial-use fields; non-commercial licences are marked as such; downloaded entries need a checksum |
| tests/test_docs.py | Source-of-truth documents exist; every API route, role and error code in the code is documented |
| tests/test_api.py | Login rate limit, security headers, unsafe production settings refused, error envelope, login, validation, tenant isolation, RBAC, evidence validation, invalid transitions, full E2E incident -> investigation -> review -> work -> failed and passed verification -> closure -> audit, critical closure permission, agent failure with manual continuation, dashboard and search |

## Blueprint test plan (Part 11) and status

| Area | Status |
|---|---|
| Unit: risk matrix, state transitions, permission checks, validation, chunkers, agent schemas | Implemented |
| Unit: parsers (PDF/DOCX), embedding retry and idempotency | Implemented (`tests/test_knowledge.py`); API idempotency keys not yet (Prompt 37) |
| Integration: API + database, authentication, RAG, agent orchestration, CAPA | Implemented |
| Integration: PostgreSQL + pgvector | Implemented (`tests/test_postgres.py`, CI `postgres` job) |
| Integration: object storage | Not yet (local disk only) |
| E2E: login → project → incident → evidence → AI analysis → approval → CAPA → verification → closure | API-level (`test_end_to_end_incident_to_verified_closure`, walkthrough script); browser E2E when the web app exists |

## AI evaluation (not yet, Prompt 40)

Metrics: retrieval precision/recall; citation coverage; structured-output validity; unsupported-claim rate;
expert-rated RCA quality; risk agreement; actionability; agent task completion; latency; cost.

## Red-team cases

| Case | Status |
|---|---|
| Prompt injection | Unit-tested (poisoned document flagged and not cited) |
| Insufficient evidence | Unit-tested (triage fixture) |
| Model/provider timeout | Unit-tested (provider failure fallback) |
| Conflicting documents | Unit-tested (`test_conflicting_sources_are_reported`) |
| Invented citations and unsupported claims in answers | Unit-tested |
| False compliance request, severe incident, false-negative PPE detection, duplicate tool invocation | Not yet (Prompt 41) |

## Definition of Done

Tests, lint, type check and build pass for the affected scope.
